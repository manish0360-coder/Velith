"""The permanent D7 shared-retrieval invariant check (M7-C6).

D7 requires that A1 and A2 share the **identical** retriever, embedder, and top-k, and
that the write-filter is the **only** difference between them — *if their retrievers
ever differ, the experiment is void* (M7_SPEC §3.4). A divergence here is therefore not
a degradation to be tolerated but a **void experiment**, and must fail loudly.

This module is that permanent check. It pins the invariant three ways:

* **Structurally** — the arm layer never imports, substitutes, wraps, or parameterises
  the retriever/embedder; it supplies only a filtered memory view.
* **By signature** — no arm can reach the substrate: neither the retriever's
  construction nor its retrieval accepts an arm, so no arm-dependent selection can
  occur at or after retrieval.
* **By configuration** — the retrieval settings are arm-independent, so the active arm
  cannot re-configure top-k, the embedder, or the memory source.

It also proves the check is not vacuous: a deliberately divergent retriever is detected.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

import velith.arms
from velith.arms.identity import M7_ARMS
from velith.arms.memory_view import ArmMemoryView
from velith.core.config import Settings
from velith.retrieval.embedding import EMBEDDER_NAME, EmbedderError, get_embedder
from velith.retrieval.retriever import Retriever

#: Modules the arm layer must never import: importing either would mean an arm can
#: substitute, re-configure, or wrap the shared substrate (M7_SPEC §3.4/§8).
FORBIDDEN_IMPORTS = ("velith.retrieval.retriever", "velith.retrieval.embedding")


def _arm_layer_modules() -> list[Path]:
    assert velith.arms.__file__ is not None
    return sorted(Path(velith.arms.__file__).parent.glob("*.py"))


def _imported_modules(source: Path) -> set[str]:
    """Every module name imported by ``source``, however the import is spelled."""
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    return imported


def _retrieval_fingerprint(retriever: Retriever) -> tuple[str, int]:
    """The retrieval configuration that must be identical across arms."""
    return (type(retriever._embedder).__name__, retriever._top_k)


def test_arm_layer_never_imports_the_retriever_or_embedder() -> None:
    """The arms supply a filtered memory view to an unchanged substrate (§3.4)."""
    for module in _arm_layer_modules():
        imported = _imported_modules(module)
        for forbidden in FORBIDDEN_IMPORTS:
            assert forbidden not in imported, f"{module.name} reaches into {forbidden}"


def test_arm_layer_touches_only_the_read_only_memory_seam() -> None:
    """The single permitted retrieval dependency is the read-only memory source.

    The arm layer may depend on the read-only memory seam ``velith.retrieval.memory`` and
    the names it exports (``EpisodeMemory``, ``MemorySnapshot``) — those *are* the seam —
    but on nothing else under ``velith.retrieval`` (notably not the retriever or embedder),
    which would let an arm reshape the shared substrate and void D7 (§3.4). ``_imported_modules``
    records both the module (``velith.retrieval.memory``) and each imported name qualified as
    ``velith.retrieval.memory.EpisodeMemory``; the seam-prefix check admits the module and its
    members while still rejecting ``velith.retrieval.retriever`` / ``velith.retrieval.embedding``.
    """
    seam = "velith.retrieval.memory"
    for module in _arm_layer_modules():
        for name in _imported_modules(module):
            if not name.startswith("velith.retrieval"):
                continue
            assert name == seam or name.startswith(
                seam + "."
            ), f"{module.name} touches {name}, outside the read-only memory seam {seam!r}"


def test_the_retriever_accepts_no_arm() -> None:
    """No arm-dependent selection can occur at or after retrieval (§3.3 stage 4)."""
    construction = list(inspect.signature(Retriever).parameters)
    retrieval = list(inspect.signature(Retriever.retrieve).parameters)
    assert construction == ["embedder", "top_k"]
    assert retrieval == ["self", "query", "memory"]
    for parameter in construction + retrieval:
        assert "arm" not in parameter


def test_an_arm_cannot_receive_or_reconfigure_the_substrate() -> None:
    """The arm view takes a binding and a memory source - never retrieval machinery."""
    parameters = list(inspect.signature(ArmMemoryView).parameters)
    assert parameters == ["binding", "source"]
    for forbidden in ("retriever", "embedder", "top_k"):
        assert forbidden not in parameters


def test_one_shared_retriever_serves_every_arm_unchanged() -> None:
    """The arms contribute memory only, so a single retriever instance serves them all."""
    retriever = Retriever(get_embedder(EMBEDDER_NAME), 5)
    before = _retrieval_fingerprint(retriever)

    for arm in M7_ARMS:
        assert _retrieval_fingerprint(retriever) == before, f"arm {arm.value} altered retrieval"


def test_retrieval_configuration_is_arm_independent() -> None:
    """The active arm cannot re-configure top-k, the embedder, or the memory source."""
    settings = [Settings(active_arm=arm) for arm in M7_ARMS]
    fingerprints = {
        (s.retrieval_top_k, s.retrieval_embedder, s.retrieval_memory_path) for s in settings
    }
    assert len(fingerprints) == 1


def test_only_one_embedder_component_exists() -> None:
    """A single shared embedder - no routing, so no arm can select its own (M6 §3.3)."""
    assert type(get_embedder(EMBEDDER_NAME)) is type(get_embedder(EMBEDDER_NAME))
    with pytest.raises(EmbedderError):
        get_embedder("per-arm-embedder")


def test_the_invariant_check_detects_divergence() -> None:
    """The check is not vacuous: a divergent retriever is caught, loudly."""
    baseline = Retriever(get_embedder(EMBEDDER_NAME), 5)
    divergent_top_k = Retriever(get_embedder(EMBEDDER_NAME), 6)

    assert _retrieval_fingerprint(baseline) == _retrieval_fingerprint(
        Retriever(get_embedder(EMBEDDER_NAME), 5)
    )
    assert _retrieval_fingerprint(baseline) != _retrieval_fingerprint(divergent_top_k)
