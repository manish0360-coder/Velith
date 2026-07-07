"""Hermetic acceptance for the M4 corpus + held-out lock (M4-C5).

End-to-end through the wired M4 components — corpus loader, content-addressed
manifest, held-out lock, and the guarded persistence boundary over the frozen M3
store — with no model, no verifier, and no network. Pins the M4 acceptance criteria
(M4_SPEC §8): a corpus loads partitioned; the lock excludes exactly the held-out
set and is content-addressed (relabeling cannot cross); the guarded boundary refuses
held-out and persists available via the frozen store byte-identically; the manifest
hash is stable and changes iff the split changes; and a synthetic non-software corpus
flows through the identical path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from velith.corpus.heldout import GuardedEpisodeWriter, HeldOutError, HeldOutLock
from velith.corpus.loader import load_corpus
from velith.corpus.manifest import Partition, task_identity
from velith.episodes.episode import Episode, VerdictState
from velith.episodes.index import EpisodeIndex
from velith.episodes.store import EpisodeStore

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "corpus_min"


def _episode(task_id: str) -> Episode:
    return Episode.build(
        task_id=task_id,
        seed=0,
        model="m",
        model_version="v",
        prompt="p",
        patch="--- a/x\n+++ b/x\n",
        verdict_state=VerdictState.PASSED,
        verdict_output="1 passed",
        prompt_tokens=1,
        completion_tokens=2,
        latency_seconds=1.0,
        verify_seconds=2.0,
        velith_version="0.0.0",
        secondary_passed=True,
        flaky=False,
        timestamp="2026-07-06T00:00:00+00:00",
    )


def _write_corpus(root: Path, descriptors: list[dict[str, str]], split: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "corpus.json").write_text(json.dumps(descriptors), encoding="utf-8")
    (root / "partition.json").write_text(json.dumps(split), encoding="utf-8")


def test_corpus_loads_partitioned_and_lock_excludes_exactly_the_held_out_set() -> None:
    loaded = load_corpus(_FIXTURE, _FIXTURE / "partition.json")
    assert len(loaded.tasks) > 1
    lock = HeldOutLock(loaded.manifest)

    held_out = {task.identity for task in loaded.tasks if task.partition is Partition.HELD_OUT}
    assert len(held_out) == 1  # exactly the gear task in the fixture
    for task in loaded.tasks:
        assert lock.is_held_out(task.identity) == (task.identity in held_out)


def test_guarded_boundary_persists_available_and_refuses_held_out(tmp_path: Path) -> None:
    loaded = load_corpus(_FIXTURE, _FIXTURE / "partition.json")
    store = EpisodeStore(tmp_path / "e.jsonl", tmp_path / "e.db")
    writer = GuardedEpisodeWriter(HeldOutLock(loaded.manifest), store)
    by_label = {task.label: task for task in loaded.tasks}

    available = by_label["bracket-v1"]
    held_out = by_label["gear-v2"]
    writer.persist(available.identity, _episode(available.label))
    with pytest.raises(HeldOutError):
        writer.persist(held_out.identity, _episode(held_out.label))

    persisted = store.read_all()
    assert [episode.task_id for episode in persisted] == ["bracket-v1"]


def test_available_persist_is_byte_identical_to_direct_store(tmp_path: Path) -> None:
    loaded = load_corpus(_FIXTURE, _FIXTURE / "partition.json")
    available = next(task for task in loaded.tasks if task.partition is Partition.AVAILABLE)
    episode = _episode(available.label)

    a_log, a_db = tmp_path / "a.jsonl", tmp_path / "a.db"
    writer = GuardedEpisodeWriter(HeldOutLock(loaded.manifest), EpisodeStore(a_log, a_db))
    writer.persist(available.identity, episode)

    b_log, b_db = tmp_path / "b.jsonl", tmp_path / "b.db"
    EpisodeStore(b_log, b_db).append(episode)

    assert a_log.read_bytes() == b_log.read_bytes()
    with EpisodeIndex(a_db) as index_a, EpisodeIndex(b_db) as index_b:
        assert index_a.all_rows() == index_b.all_rows()


def test_manifest_hash_is_stable_and_changes_iff_split_changes(tmp_path: Path) -> None:
    first = load_corpus(_FIXTURE, _FIXTURE / "partition.json").manifest.manifest_hash
    second = load_corpus(_FIXTURE, _FIXTURE / "partition.json").manifest.manifest_hash
    assert first == second  # stable across loads

    descriptors = [
        {"label": "x", "material": "MX", "handle": "h"},
        {"label": "y", "material": "MY", "handle": "h"},
    ]
    _write_corpus(tmp_path / "c1", descriptors, {"MX": "available", "MY": "held_out"})
    _write_corpus(tmp_path / "c2", descriptors, {"MX": "held_out", "MY": "available"})
    _write_corpus(tmp_path / "c3", descriptors, {"MX": "available", "MY": "held_out"})

    hash1 = load_corpus(tmp_path / "c1", tmp_path / "c1" / "partition.json").manifest.manifest_hash
    hash2 = load_corpus(tmp_path / "c2", tmp_path / "c2" / "partition.json").manifest.manifest_hash
    hash3 = load_corpus(tmp_path / "c3", tmp_path / "c3" / "partition.json").manifest.manifest_hash
    assert hash1 != hash2  # a changed split changes the hash
    assert hash1 == hash3  # the same split yields the same hash


def test_non_software_corpus_flows_through_the_identical_path(tmp_path: Path) -> None:
    descriptors = [
        {"label": "melody-1", "material": "notes:C-E-G;bpm:120", "handle": "harmony-ok"},
        {"label": "recipe-1", "material": "dish:soup;salt:2g", "handle": "tastes-ok"},
    ]
    split = {"notes:C-E-G;bpm:120": "available", "dish:soup;salt:2g": "held_out"}
    _write_corpus(tmp_path / "art", descriptors, split)

    loaded = load_corpus(tmp_path / "art", tmp_path / "art" / "partition.json")
    store = EpisodeStore(tmp_path / "e.jsonl", tmp_path / "e.db")
    writer = GuardedEpisodeWriter(HeldOutLock(loaded.manifest), store)
    by_label = {task.label: task for task in loaded.tasks}

    writer.persist(by_label["melody-1"].identity, _episode("melody-1"))
    with pytest.raises(HeldOutError):
        writer.persist(by_label["recipe-1"].identity, _episode("recipe-1"))
    assert [episode.task_id for episode in store.read_all()] == ["melody-1"]


def test_relabeling_cannot_cross_the_partition_end_to_end(tmp_path: Path) -> None:
    split = {"SECRET": "held_out"}
    corpus_a = [{"label": "held-A", "material": "SECRET", "handle": "h"}]
    corpus_b = [{"label": "RENAMED", "material": "SECRET", "handle": "h"}]
    _write_corpus(tmp_path / "a", corpus_a, split)
    _write_corpus(tmp_path / "b", corpus_b, split)

    loaded_a = load_corpus(tmp_path / "a", tmp_path / "a" / "partition.json")
    loaded_b = load_corpus(tmp_path / "b", tmp_path / "b" / "partition.json")
    assert loaded_a.manifest.manifest_hash == loaded_b.manifest.manifest_hash

    identity = task_identity("SECRET")
    for index, loaded in enumerate((loaded_a, loaded_b)):
        store = EpisodeStore(tmp_path / f"e{index}.jsonl", tmp_path / f"e{index}.db")
        writer = GuardedEpisodeWriter(HeldOutLock(loaded.manifest), store)
        assert HeldOutLock(loaded.manifest).is_held_out(identity)
        with pytest.raises(HeldOutError):
            writer.persist(identity, _episode("held"))
        assert store.read_all() == []
