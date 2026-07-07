"""Unit tests for the domain-neutral task corpus loader (M4-C3).

Scope: loading many partitioned tasks from a corpus source (M4_SPEC §3.2); the
partition comes from the manifest; materials and the verification handle are opaque
(carried verbatim, never interpreted); a synthetic non-software corpus loads through
the identical path; and an under-declared corpus is rejected loudly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from velith.corpus.loader import CorpusLoaderError, load_corpus
from velith.corpus.manifest import Partition, task_identity

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "corpus_min"


def _write_corpus(root: Path, descriptors: list[dict[str, str]], split: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "corpus.json").write_text(json.dumps(descriptors), encoding="utf-8")
    (root / "partition.json").write_text(json.dumps(split), encoding="utf-8")


def test_loads_multiple_tasks_with_partition_labels() -> None:
    loaded = load_corpus(_FIXTURE, _FIXTURE / "partition.json")
    assert len(loaded.tasks) == 3
    by_label = {task.label: task for task in loaded.tasks}
    assert by_label["bracket-v1"].partition is Partition.AVAILABLE
    assert by_label["gear-v2"].partition is Partition.HELD_OUT
    assert by_label["panel-v1"].partition is Partition.AVAILABLE


def test_partition_comes_from_the_manifest() -> None:
    loaded = load_corpus(_FIXTURE, _FIXTURE / "partition.json")
    for task in loaded.tasks:
        assert loaded.manifest.partition_of(task.identity) is task.partition


def test_materials_and_handles_are_carried_verbatim(tmp_path: Path) -> None:
    # A non-software corpus with arbitrary opaque materials loads through the identical
    # path; the loader never interprets material or handle content (M4_SPEC §3.2, D22).
    descriptors = [
        {"label": "alpha", "material": "shape=circle;r=5;color=red", "handle": "opaque-handle-1"},
        {"label": "beta", "material": "melody:C-E-G;tempo:120", "handle": "opaque-handle-2"},
    ]
    split = {"shape=circle;r=5;color=red": "held_out", "melody:C-E-G;tempo:120": "available"}
    _write_corpus(tmp_path, descriptors, split)

    loaded = load_corpus(tmp_path, tmp_path / "partition.json")
    by_label = {task.label: task for task in loaded.tasks}
    assert by_label["alpha"].material == "shape=circle;r=5;color=red"
    assert by_label["alpha"].handle == "opaque-handle-1"
    assert by_label["alpha"].partition is Partition.HELD_OUT
    assert by_label["beta"].partition is Partition.AVAILABLE


def test_identity_is_content_addressed(tmp_path: Path) -> None:
    _write_corpus(
        tmp_path,
        [{"label": "x", "material": "MAT-1", "handle": "h"}],
        {"MAT-1": "held_out"},
    )
    loaded = load_corpus(tmp_path, tmp_path / "partition.json")
    assert loaded.tasks[0].identity == task_identity("MAT-1")


def test_task_absent_from_partition_spec_raises(tmp_path: Path) -> None:
    empty_split: dict[str, str] = {}  # MAT-1 is not declared
    _write_corpus(tmp_path, [{"label": "x", "material": "MAT-1", "handle": "h"}], empty_split)
    with pytest.raises(CorpusLoaderError):
        load_corpus(tmp_path, tmp_path / "partition.json")


def test_missing_corpus_file_raises(tmp_path: Path) -> None:
    (tmp_path / "partition.json").write_text("{}", encoding="utf-8")
    with pytest.raises(CorpusLoaderError):
        load_corpus(tmp_path, tmp_path / "partition.json")


def test_manifest_hash_is_stable_across_loads() -> None:
    first = load_corpus(_FIXTURE, _FIXTURE / "partition.json")
    second = load_corpus(_FIXTURE, _FIXTURE / "partition.json")
    assert first.manifest.manifest_hash == second.manifest.manifest_hash
