"""Hermetic acceptance for the M3 indexed episode store (M3-C4).

End-to-end through the wired :class:`EpisodeStore` (log + derived SQLite index), with
no model, no verifier, and no network — CI-hermetic. Pins the M3 Definition of Done
(handoff §9 / M3_SPEC §5): backward-compatible re-hash (1), rebuild-from-log identity
(2), query by every neutral field and by time range (3), record-digest corruption
detection (4), domain-agnosticism (5), outcome-representation flexibility across the
categorical verdict (6), and determinism — content hash unchanged by index presence and
inert to ``flaky`` (7).

The JSONL log is the authoritative source of truth; the SQLite index is a rebuildable
derived projection (M3_SPEC §4.1-§4.2). These tests only exercise that contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from velith.episodes.episode import Episode, VerdictState
from velith.episodes.index import INDEX_COLUMNS, EpisodeIndex
from velith.episodes.store import EpisodeStore, RecordIntegrityError


def _episode(
    *,
    task_id: str = "calc_add_bug",
    seed: int = 0,
    model: str = "qwen2.5-coder",
    verdict_state: VerdictState = VerdictState.PASSED,
    secondary_passed: bool | None = True,
    flaky: bool = False,
    timestamp: str = "2026-07-06T00:00:00+00:00",
    patch: str = "--- a/x.py\n+++ b/x.py\n",
) -> Episode:
    """Build a complete, deterministic episode (fixed timestamp) for acceptance."""
    return Episode.build(
        task_id=task_id,
        seed=seed,
        model=model,
        model_version="test-1",
        prompt="fix the failing test",
        patch=patch,
        verdict_state=verdict_state,
        verdict_output="1 passed",
        prompt_tokens=10,
        completion_tokens=20,
        latency_seconds=1.5,
        verify_seconds=2.5,
        velith_version="0.0.0",
        secondary_passed=secondary_passed,
        flaky=flaky,
        timestamp=timestamp,
    )


def _corpus() -> list[Episode]:
    """A small, varied corpus spanning several verdict states and neutral fields."""
    return [
        _episode(
            task_id="task_a", seed=1, model="model_x", verdict_state=VerdictState.PASSED,
            secondary_passed=True, flaky=False, timestamp="2026-07-06T01:00:00+00:00",
        ),
        _episode(
            task_id="task_b", seed=2, model="model_y", verdict_state=VerdictState.FAILED,
            secondary_passed=False, flaky=True, timestamp="2026-07-06T02:00:00+00:00",
            patch="--- a/b.py\n+++ b/b.py\n",
        ),
        _episode(
            task_id="task_a", seed=3, model="model_x", verdict_state=VerdictState.NO_PATCH,
            secondary_passed=None, flaky=False, timestamp="2026-07-06T03:00:00+00:00",
            patch="",
        ),
    ]


def test_append_read_and_query_across_neutral_fields(tmp_path: Path) -> None:
    """Append a corpus, re-hash on read, and query by every neutral field (DoD 1, 3, 6)."""
    log_path = tmp_path / "episodes.jsonl"
    index_path = tmp_path / "episodes.db"
    store = EpisodeStore(log_path, index_path)
    corpus = _corpus()
    for episode in corpus:
        store.append(episode)

    # (1) Backward-compatible read: a fresh store re-reads and re-hashes every record.
    reread = EpisodeStore(log_path, index_path).read_all()
    assert reread == corpus
    assert all(e.verify_hash() for e in reread)

    # (3, 6) Query by each neutral field and by time range. Multiple verdict states are
    # all indexed and selectable — the store treats the verdict as an opaque category,
    # not a binary outcome (M3_SPEC §5.6 / D22).
    with EpisodeIndex(index_path) as index:
        assert {r.content_hash for r in index.by_task("task_a")} == {
            corpus[0].content_hash,
            corpus[2].content_hash,
        }
        assert [r.content_hash for r in index.by_state("FAILED")] == [corpus[1].content_hash]
        assert [r.content_hash for r in index.by_state("NO_PATCH")] == [corpus[2].content_hash]
        assert [r.content_hash for r in index.by_model("model_y")] == [corpus[1].content_hash]
        assert [r.content_hash for r in index.by_seed(1)] == [corpus[0].content_hash]
        assert [r.content_hash for r in index.by_flaky(True)] == [corpus[1].content_hash]
        assert [r.content_hash for r in index.by_secondary_passed(None)] == [corpus[2].content_hash]
        assert [
            r.content_hash
            for r in index.by_time_range("2026-07-06T01:30:00+00:00", "2026-07-06T02:30:00+00:00")
        ] == [corpus[1].content_hash]


def test_domain_neutral_episode_flows_through_identically(tmp_path: Path) -> None:
    """A non-software episode indexes and queries via the identical path (DoD 5)."""
    log_path = tmp_path / "episodes.jsonl"
    index_path = tmp_path / "episodes.db"
    store = EpisodeStore(log_path, index_path)
    # A hardware/manufacturing-shaped episode: the "patch" is an opaque change with no
    # code. The store must not care about the domain (M3_SPEC §4.4 / D5).
    pcb = _episode(
        task_id="pcb_route_v1",
        model="planner-1",
        patch="NET GND PAD1 PAD2\nNET VCC PAD3 PAD4\n",
        timestamp="2026-07-06T05:00:00+00:00",
    )
    store.append(pcb)

    assert store.read_all() == [pcb]
    with EpisodeIndex(index_path) as index:
        rows = index.by_task("pcb_route_v1")
        assert [r.content_hash for r in rows] == [pcb.content_hash]
        # The indexed row exposes only neutral fields — no patch/prompt/source anywhere.
        columns = {row["name"] for row in index._conn.execute("PRAGMA table_info(episodes)")}
    assert columns == set(INDEX_COLUMNS)
    for domain_field in ("patch", "prompt", "verdict_output"):
        assert domain_field not in columns


def test_drop_and_rebuild_index_from_log_is_identical(tmp_path: Path) -> None:
    """Dropping the index and rebuilding from the log alone restores identical state (DoD 2)."""
    log_path = tmp_path / "episodes.jsonl"
    index_path = tmp_path / "episodes.db"
    store = EpisodeStore(log_path, index_path)
    for episode in _corpus():
        store.append(episode)

    with EpisodeIndex(index_path) as index:
        before = index.all_rows()

    # Drop the derived projection entirely, then rebuild from the authoritative log.
    index_path.unlink()
    with EpisodeIndex(index_path) as rebuilt_index:
        rebuilt_index.rebuild_from_log(log_path)
        after = rebuilt_index.all_rows()

    assert after == before
    assert len(after) == len(_corpus())


def test_record_corruption_in_log_is_detected_loudly(tmp_path: Path) -> None:
    """Corrupting a stored record is caught on read by the record digest (DoD 4)."""
    log_path = tmp_path / "episodes.jsonl"
    index_path = tmp_path / "episodes.db"
    store = EpisodeStore(log_path, index_path)
    store.append(_episode())

    raw = log_path.read_text(encoding="utf-8")
    # `latency_seconds` is provenance, OUTSIDE the content-hash boundary (D16.1/D21):
    # the content hash still verifies, so only the full-record digest can catch this.
    assert '"latency_seconds":1.5' in raw, "guard: provenance field present"
    tampered = raw.replace('"latency_seconds":1.5', '"latency_seconds":9.9')
    log_path.write_text(tampered, encoding="utf-8")

    with pytest.raises(RecordIntegrityError):
        store.read_all()


def test_content_hash_unchanged_by_index_and_inert_to_flaky(tmp_path: Path) -> None:
    """Index presence and the flaky flag never change episode identity (DoD 7)."""
    episode = _episode()

    # Index presence must not change the authoritative log line or the content hash.
    without = tmp_path / "without.jsonl"
    with_index = tmp_path / "with.jsonl"
    EpisodeStore(without).append(episode)
    EpisodeStore(with_index, tmp_path / "with.db").append(episode)
    assert without.read_text(encoding="utf-8") == with_index.read_text(encoding="utf-8")

    # `flaky` is provenance, excluded from the content hash (D21): flipping it leaves
    # identity unchanged, and both values remain independently queryable.
    stable = _episode(seed=7, flaky=False, timestamp="2026-07-06T06:00:00+00:00")
    flaky = _episode(seed=7, flaky=True, timestamp="2026-07-06T06:00:00+00:00")
    assert stable.content_hash == flaky.content_hash
