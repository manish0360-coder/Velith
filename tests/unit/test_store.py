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
from velith.episodes.store import EpisodeIntegrityError, EpisodeStore


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
