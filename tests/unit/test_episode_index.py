"""Unit tests for the derived SQLite episode index (M3-C2).

Scope: the index in isolation — create/open, upsert + query by each neutral field
and by time range, ``rebuild_from_log`` identity, record-digest population, and
domain-neutrality of the schema. The index is a rebuildable projection of the
authoritative JSONL log (M3_SPEC §4.1-§4.2, §6.2, §9). These tests write log lines
directly (``Episode.model_dump_json``) to keep C2 independent of the store (C3).
"""

from __future__ import annotations

from pathlib import Path

from velith.episodes.episode import Episode, VerdictState
from velith.episodes.index import (
    INDEX_COLUMNS,
    EpisodeIndex,
    EpisodeIndexRow,
    record_digest,
)


def _make_episode(
    *,
    task_id: str = "calc_add_bug",
    seed: int = 0,
    model: str = "qwen2.5-coder",
    verdict_state: VerdictState = VerdictState.PASSED,
    secondary_passed: bool | None = True,
    flaky: bool = False,
    timestamp: str = "2026-07-06T00:00:00+00:00",
    patch: str = "diff --git a b",
) -> Episode:
    """Build a valid, fully-populated episode for indexing tests."""
    return Episode.build(
        task_id=task_id,
        seed=seed,
        model=model,
        model_version="test-1",
        prompt="fix the bug",
        patch=patch,
        verdict_state=verdict_state,
        verdict_output="1 passed",
        prompt_tokens=10,
        completion_tokens=20,
        latency_seconds=1.0,
        verify_seconds=2.0,
        velith_version="0.0.0",
        secondary_passed=secondary_passed,
        flaky=flaky,
        timestamp=timestamp,
    )


def _write_log(path: Path, episodes: list[Episode]) -> None:
    """Write episodes to a JSONL log exactly as the store would (one line each)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for episode in episodes:
            handle.write(episode.model_dump_json() + "\n")


def test_create_and_get_roundtrip(tmp_path: Path) -> None:
    """A newly created index stores and returns a row by content hash."""
    episode = _make_episode()
    with EpisodeIndex(tmp_path / "episodes.db") as index:
        index.upsert(EpisodeIndexRow.from_episode(episode))
        row = index.get(episode.content_hash)
    assert row is not None
    assert row == EpisodeIndexRow.from_episode(episode)


def test_query_by_each_neutral_field(tmp_path: Path) -> None:
    """Every neutral accessor selects the expected episodes."""
    passed = _make_episode(
        task_id="task_a",
        seed=1,
        model="model_x",
        verdict_state=VerdictState.PASSED,
        secondary_passed=True,
        flaky=False,
        timestamp="2026-07-06T01:00:00+00:00",
    )
    failed = _make_episode(
        task_id="task_b",
        seed=2,
        model="model_y",
        verdict_state=VerdictState.FAILED,
        secondary_passed=False,
        flaky=True,
        timestamp="2026-07-06T02:00:00+00:00",
        patch="diff --git c d",
    )
    no_secondary = _make_episode(
        task_id="task_a",
        seed=3,
        model="model_x",
        verdict_state=VerdictState.NO_PATCH,
        secondary_passed=None,
        flaky=False,
        timestamp="2026-07-06T03:00:00+00:00",
        patch="",
    )
    with EpisodeIndex(tmp_path / "episodes.db") as index:
        for episode in (passed, failed, no_secondary):
            index.upsert(EpisodeIndexRow.from_episode(episode))

        assert {r.content_hash for r in index.by_task("task_a")} == {
            passed.content_hash,
            no_secondary.content_hash,
        }
        assert [r.content_hash for r in index.by_state("FAILED")] == [failed.content_hash]
        assert [r.content_hash for r in index.by_model("model_y")] == [failed.content_hash]
        assert [r.content_hash for r in index.by_seed(1)] == [passed.content_hash]
        assert [r.content_hash for r in index.by_flaky(True)] == [failed.content_hash]
        assert [r.content_hash for r in index.by_secondary_passed(None)] == [
            no_secondary.content_hash
        ]
        assert [r.content_hash for r in index.by_secondary_passed(False)] == [failed.content_hash]
        assert [
            r.content_hash
            for r in index.by_time_range("2026-07-06T01:30:00+00:00", "2026-07-06T02:30:00+00:00")
        ] == [failed.content_hash]


def test_rebuild_from_log_is_identical_to_incremental(tmp_path: Path) -> None:
    """Dropping and rebuilding from the log yields identical index state (§4.2)."""
    episodes = [
        _make_episode(seed=1, timestamp="2026-07-06T01:00:00+00:00"),
        _make_episode(seed=2, timestamp="2026-07-06T02:00:00+00:00", patch="diff x"),
        _make_episode(seed=3, timestamp="2026-07-06T03:00:00+00:00", patch="diff y"),
    ]
    log_path = tmp_path / "episodes.jsonl"
    _write_log(log_path, episodes)

    with EpisodeIndex(tmp_path / "episodes.db") as index:
        for episode in episodes:
            index.upsert(EpisodeIndexRow.from_episode(episode))
        incremental = index.all_rows()

        index.rebuild_from_log(log_path)
        rebuilt = index.all_rows()

    assert rebuilt == incremental
    assert len(rebuilt) == len(episodes)


def test_rebuild_on_fresh_index_matches_log(tmp_path: Path) -> None:
    """A fresh index rebuilt from the log contains exactly the log's episodes."""
    episodes = [
        _make_episode(seed=1, timestamp="2026-07-06T01:00:00+00:00"),
        _make_episode(seed=2, timestamp="2026-07-06T02:00:00+00:00", patch="diff x"),
    ]
    log_path = tmp_path / "episodes.jsonl"
    _write_log(log_path, episodes)

    with EpisodeIndex(tmp_path / "episodes.db") as index:
        index.rebuild_from_log(log_path)
        rows = index.all_rows()

    assert {r.content_hash for r in rows} == {e.content_hash for e in episodes}


def test_record_digest_column_populated_and_distinct_from_content_hash(tmp_path: Path) -> None:
    """Each row carries a record digest distinct from the content hash (§9)."""
    episode = _make_episode()
    with EpisodeIndex(tmp_path / "episodes.db") as index:
        index.upsert(EpisodeIndexRow.from_episode(episode))
        row = index.get(episode.content_hash)
    assert row is not None
    assert row.record_digest == record_digest(episode.model_dump_json())
    assert row.record_digest != episode.content_hash


def test_upsert_is_idempotent(tmp_path: Path) -> None:
    """Re-indexing the same episode leaves a single row unchanged."""
    episode = _make_episode()
    with EpisodeIndex(tmp_path / "episodes.db") as index:
        index.upsert(EpisodeIndexRow.from_episode(episode))
        index.upsert(EpisodeIndexRow.from_episode(episode))
        rows = index.all_rows()
    assert len(rows) == 1


def test_schema_is_domain_neutral(tmp_path: Path) -> None:
    """The index holds only the closed neutral field set — no domain columns (§4.4)."""
    with EpisodeIndex(tmp_path / "episodes.db") as index:
        cursor = index._conn.execute("PRAGMA table_info(episodes)")
        columns = {record["name"] for record in cursor.fetchall()}
    assert columns == set(INDEX_COLUMNS)
    for forbidden in ("patch", "prompt", "verdict_output", "model_version", "arm"):
        assert forbidden not in columns
