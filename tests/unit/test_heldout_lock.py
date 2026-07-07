"""Unit tests for the held-out lock and guarded persistence boundary (M4-C4).

Scope: the exclusion predicate is authoritative and content-addressed (relabeling
cannot cross the partition); the guarded boundary raises on a held-out task and on an
identity absent from the manifest (fail-closed); and a delegated available-task
episode is byte-for-byte identical to a direct M3 append (M3 composed, not altered).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from velith.corpus.heldout import GuardedEpisodeWriter, HeldOutError, HeldOutLock
from velith.corpus.manifest import CorpusManifest, Partition, PartitionEntry, task_identity
from velith.episodes.episode import Episode, VerdictState
from velith.episodes.index import EpisodeIndex
from velith.episodes.store import EpisodeStore


def _manifest() -> CorpusManifest:
    return CorpusManifest.from_entries(
        [
            PartitionEntry(label="avail-v1", material="M-available", partition=Partition.AVAILABLE),
            PartitionEntry(label="held-v1", material="M-held", partition=Partition.HELD_OUT),
        ]
    )


def _episode(task_id: str = "t") -> Episode:
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


def test_lock_predicate_is_authoritative() -> None:
    lock = HeldOutLock(_manifest())
    assert lock.is_held_out(task_identity("M-held"))
    assert not lock.is_held_out(task_identity("M-available"))
    assert lock.is_available(task_identity("M-available"))
    assert not lock.is_available(task_identity("M-held"))
    assert lock.partition_of("unknown-identity") is None


def test_relabeling_cannot_cross_the_partition() -> None:
    # Same material, different display label -> same identity, same lock verdict.
    held_v1 = CorpusManifest.from_entries(
        [PartitionEntry(label="held-v1", material="M-held", partition=Partition.HELD_OUT)]
    )
    renamed = CorpusManifest.from_entries(
        [PartitionEntry(label="RENAMED", material="M-held", partition=Partition.HELD_OUT)]
    )
    identity = task_identity("M-held")
    assert HeldOutLock(held_v1).is_held_out(identity)
    assert HeldOutLock(renamed).is_held_out(identity)
    assert held_v1.manifest_hash == renamed.manifest_hash


def test_boundary_persists_available_task(tmp_path: Path) -> None:
    store = EpisodeStore(tmp_path / "e.jsonl", tmp_path / "e.db")
    writer = GuardedEpisodeWriter(HeldOutLock(_manifest()), store)
    episode = _episode()

    path = writer.persist(task_identity("M-available"), episode)
    assert path == tmp_path / "e.jsonl"
    assert store.read_all() == [episode]


def test_boundary_raises_on_held_out_and_persists_nothing(tmp_path: Path) -> None:
    store = EpisodeStore(tmp_path / "e.jsonl", tmp_path / "e.db")
    writer = GuardedEpisodeWriter(HeldOutLock(_manifest()), store)

    with pytest.raises(HeldOutError):
        writer.persist(task_identity("M-held"), _episode())
    assert store.read_all() == []


def test_boundary_fails_closed_on_unknown_identity(tmp_path: Path) -> None:
    store = EpisodeStore(tmp_path / "e.jsonl", tmp_path / "e.db")
    writer = GuardedEpisodeWriter(HeldOutLock(_manifest()), store)

    with pytest.raises(HeldOutError):
        writer.persist("identity-not-in-manifest", _episode())
    assert store.read_all() == []


def test_available_persist_is_byte_identical_to_direct_append(tmp_path: Path) -> None:
    episode = _episode()

    # Via the guarded boundary.
    a_log, a_db = tmp_path / "a.jsonl", tmp_path / "a.db"
    writer = GuardedEpisodeWriter(HeldOutLock(_manifest()), EpisodeStore(a_log, a_db))
    writer.persist(task_identity("M-available"), episode)

    # Directly to a fresh frozen store.
    b_log, b_db = tmp_path / "b.jsonl", tmp_path / "b.db"
    EpisodeStore(b_log, b_db).append(episode)

    # The authoritative log line is byte-for-byte identical.
    assert a_log.read_bytes() == b_log.read_bytes()
    # And the derived index rows are identical (M3 composed, not altered).
    with EpisodeIndex(a_db) as index_a, EpisodeIndex(b_db) as index_b:
        assert index_a.all_rows() == index_b.all_rows()
