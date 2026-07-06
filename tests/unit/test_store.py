"""Unit tests for the append-only JSONL episode store (C2).

These pin the C2 Definition of Done and rollback conditions (handoff §5/§6):
append then read returns the record with its hash verified, the store is
append-only and order-preserving, writes are durable across store instances, and
a tampered record is detected loudly on read (I2).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from velith.episodes.episode import Episode, VerdictState
from velith.episodes.index import EpisodeIndex, record_digest
from velith.episodes.store import EpisodeIntegrityError, EpisodeStore, RecordIntegrityError


def _sample_episode(
    *,
    task_id: str = "fix-bug-001",
    patch: str = "--- a/x.py\n+++ b/x.py\n",
) -> Episode:
    """A complete, deterministic episode (fixed timestamp) for store tests."""
    return Episode.build(
        task_id=task_id,
        seed=0,
        model="qwen2.5-coder",
        model_version="qwen2.5-coder:7b@sha256-abc",
        prompt="Fix the failing test.",
        patch=patch,
        verdict_state=VerdictState.PASSED,
        verdict_output="1 passed in 0.01s",
        prompt_tokens=12,
        completion_tokens=34,
        latency_seconds=1.5,
        verify_seconds=2.5,
        velith_version="0.0.0+gabc123",
        timestamp="2026-06-24T00:00:00+00:00",
    )


def test_append_then_read_round_trips(tmp_path: Path) -> None:
    store = EpisodeStore(tmp_path / "episodes.jsonl")
    episode = _sample_episode()
    written_path = store.append(episode)
    assert written_path.exists()
    records = store.read_all()
    assert records == [episode]
    assert records[0].verify_hash()


def test_append_is_append_only_and_preserves_order(tmp_path: Path) -> None:
    store = EpisodeStore(tmp_path / "episodes.jsonl")
    first = _sample_episode(task_id="task-a", patch="--- a/a.py\n+++ b/a.py\n")
    second = _sample_episode(task_id="task-b", patch="--- a/b.py\n+++ b/b.py\n")
    store.append(first)
    store.append(second)
    records = store.read_all()
    # Both present, in append order, and the first record is unchanged.
    assert records == [first, second]


def test_append_creates_missing_parent_directory(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir" / "episodes.jsonl"
    EpisodeStore(target).append(_sample_episode())
    assert target.exists()


def test_read_all_on_missing_file_returns_empty(tmp_path: Path) -> None:
    store = EpisodeStore(tmp_path / "does_not_exist.jsonl")
    assert store.read_all() == []


def test_records_persist_across_store_instances(tmp_path: Path) -> None:
    path = tmp_path / "episodes.jsonl"
    EpisodeStore(path).append(_sample_episode())
    # A brand-new store object reads the data back: it was durably on disk, not
    # held in the first instance's memory.
    reopened = EpisodeStore(path)
    assert reopened.read_all() == [_sample_episode()]


def test_read_all_raises_on_a_tampered_record(tmp_path: Path) -> None:
    path = tmp_path / "episodes.jsonl"
    store = EpisodeStore(path)
    store.append(_sample_episode())
    raw = path.read_text(encoding="utf-8")
    # Mutate a hashed content field (verdict_output) without recomputing the hash.
    tampered = raw.replace("1 passed in 0.01s", "0 passed (faked result)")
    assert tampered != raw, "guard: the tampering replacement must actually occur"
    path.write_text(tampered, encoding="utf-8")
    with pytest.raises(EpisodeIntegrityError):
        store.read_all()


def test_read_all_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "episodes.jsonl"
    store = EpisodeStore(path)
    store.append(_sample_episode())
    # A stray blank line (e.g. an editor appending whitespace) must be ignored.
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n")
    assert store.read_all() == [_sample_episode()]


# --- M3-C3: dual-write to the derived index + record-level integrity digest ---


def test_append_dual_writes_to_index(tmp_path: Path) -> None:
    """With an index path, append mirrors the episode into the SQLite projection."""
    path = tmp_path / "episodes.jsonl"
    index_path = tmp_path / "episodes.db"
    episode = _sample_episode()
    EpisodeStore(path, index_path).append(episode)

    with EpisodeIndex(index_path) as index:
        row = index.get(episode.content_hash)
    assert row is not None
    assert row.content_hash == episode.content_hash
    assert row.record_digest == record_digest(episode.model_dump_json())


def test_content_hash_and_log_line_unchanged_by_index_presence(tmp_path: Path) -> None:
    """The log line and content hash are identical with or without an index (§5.7)."""
    without = tmp_path / "without.jsonl"
    with_index = tmp_path / "with.jsonl"
    episode = _sample_episode()
    EpisodeStore(without).append(episode)
    EpisodeStore(with_index, tmp_path / "with.db").append(episode)

    assert without.read_text(encoding="utf-8") == with_index.read_text(encoding="utf-8")
    assert EpisodeStore(without).read_all()[0].content_hash == episode.content_hash


def test_backward_compat_read_of_preexisting_log_without_index(tmp_path: Path) -> None:
    """A pre-existing log with no index file still reads and re-hashes (skips digest)."""
    path = tmp_path / "episodes.jsonl"
    # Log written by a log-only store (no index), as an M1/M2 record would be.
    EpisodeStore(path).append(_sample_episode())
    # A store configured with an index path whose db does not yet exist must still
    # read the log verbatim, without inventing an index or failing.
    store = EpisodeStore(path, tmp_path / "absent.db")
    assert store.read_all() == [_sample_episode()]


def test_read_all_detects_record_digest_tampering(tmp_path: Path) -> None:
    """Tampering a provenance field (outside the content hash) is caught by the digest."""
    path = tmp_path / "episodes.jsonl"
    index_path = tmp_path / "episodes.db"
    store = EpisodeStore(path, index_path)
    store.append(_sample_episode())

    raw = path.read_text(encoding="utf-8")
    # `latency_seconds` is OUTSIDE the content-hash boundary (D16.1/D21): mutating it
    # leaves `content_hash` valid, so only the full-record digest can catch it.
    assert '"latency_seconds":1.5' in raw, "guard: provenance field present"
    tampered = raw.replace('"latency_seconds":1.5', '"latency_seconds":9.9')
    assert tampered != raw
    path.write_text(tampered, encoding="utf-8")

    with pytest.raises(RecordIntegrityError):
        store.read_all()
