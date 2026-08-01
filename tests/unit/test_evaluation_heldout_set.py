"""Unit tests for the M8 held-out evaluation set (M8-C3).

Scope: read-only access to the held-out partition in isolation (M8_SPEC §3.2) — only
held-out tasks are surfaced (no available leak), the manifest hash is carried, access is
read-only and domain-neutral, and an empty held-out split yields an empty set. The
checkpoint (C2), the attempt (C5), and the runner (C8) are not under test here.
"""

from __future__ import annotations

import json
from pathlib import Path

from velith.corpus.manifest import Partition
from velith.evaluation.heldout_set import load_heldout_set


def _write_corpus(
    root: Path, descriptors: list[dict[str, str]], partition: dict[str, str]
) -> tuple[Path, Path]:
    """Write a neutral corpus.json and partition spec; return their paths."""
    root.mkdir(parents=True, exist_ok=True)
    corpus_file = root / "corpus.json"
    corpus_file.write_text(json.dumps(descriptors), encoding="utf-8")
    spec_file = root / "partition.json"
    spec_file.write_text(json.dumps(partition), encoding="utf-8")
    return root, spec_file


def test_only_heldout_tasks_are_surfaced(tmp_path: Path) -> None:
    """Available tasks never leak into the evaluation set (§3.2)."""
    corpus_path, spec_path = _write_corpus(
        tmp_path / "corpus",
        [
            {"label": "a", "material": "M-a", "handle": "H-a"},
            {"label": "b", "material": "M-b", "handle": "H-b"},
            {"label": "c", "material": "M-c", "handle": "H-c"},
        ],
        {"M-a": "available", "M-b": "held_out", "M-c": "held_out"},
    )

    held = load_heldout_set(corpus_path, spec_path)
    assert {task.material for task in held} == {"M-b", "M-c"}
    assert all(task.partition is Partition.HELD_OUT for task in held)
    assert len(held) == 2


def test_manifest_hash_is_carried(tmp_path: Path) -> None:
    """The set carries the frozen manifest hash fixing the split (§3.2)."""
    corpus_path, spec_path = _write_corpus(
        tmp_path / "corpus",
        [{"label": "a", "material": "M-a", "handle": "H-a"}],
        {"M-a": "held_out"},
    )

    held = load_heldout_set(corpus_path, spec_path)
    assert isinstance(held.manifest_hash, str)
    assert held.manifest_hash != ""


def test_access_is_read_only(tmp_path: Path) -> None:
    """Loading the held-out set writes and mutates nothing on disk."""
    corpus_path, spec_path = _write_corpus(
        tmp_path / "corpus",
        [
            {"label": "a", "material": "M-a", "handle": "H-a"},
            {"label": "b", "material": "M-b", "handle": "H-b"},
        ],
        {"M-a": "available", "M-b": "held_out"},
    )
    before = {p: p.read_bytes() for p in corpus_path.iterdir()}

    for _ in range(3):
        load_heldout_set(corpus_path, spec_path)

    assert {p: p.read_bytes() for p in corpus_path.iterdir()} == before


def test_non_software_heldout_set_loads_identically(tmp_path: Path) -> None:
    """Opaque, non-software materials surface through the identical path (D9/D22)."""
    corpus_path, spec_path = _write_corpus(
        tmp_path / "corpus",
        [
            {"label": "melody", "material": "melody:C-E-G;bpm=120", "handle": "listen:C-E-G"},
            {"label": "dish", "material": "dish:soup;salt=2g", "handle": "taste:soup"},
        ],
        {"melody:C-E-G;bpm=120": "held_out", "dish:soup;salt=2g": "available"},
    )

    held = load_heldout_set(corpus_path, spec_path)
    assert {task.material for task in held} == {"melody:C-E-G;bpm=120"}


def test_empty_heldout_split_yields_empty_set(tmp_path: Path) -> None:
    """A split with no held-out task yields an empty evaluation set."""
    corpus_path, spec_path = _write_corpus(
        tmp_path / "corpus",
        [{"label": "a", "material": "M-a", "handle": "H-a"}],
        {"M-a": "available"},
    )

    held = load_heldout_set(corpus_path, spec_path)
    assert len(held) == 0
    assert tuple(held) == ()
