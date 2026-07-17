"""Unit tests for the read-only retrieval memory source (M6-C4).

Scope: the source reads the frozen episode store and serves an immutable snapshot; it
mutates nothing (the log is unchanged and no index artifact is created by reading); it
is stable across calls; and it surfaces exactly the persisted episodes — nothing
fabricated (M6_SPEC §3.1).
"""

from __future__ import annotations

from pathlib import Path

from velith.episodes.episode import Episode, VerdictState
from velith.episodes.store import EpisodeStore
from velith.retrieval.memory import EpisodeMemory


def _episode(seed: int, patch: str = "--- a/x\n+++ b/x\n") -> Episode:
    return Episode.build(
        task_id="t",
        seed=seed,
        model="m",
        model_version="v",
        prompt="p",
        patch=patch,
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


def _populate(path: Path, episodes: list[Episode]) -> None:
    store = EpisodeStore(path)
    for episode in episodes:
        store.append(episode)


def test_snapshot_returns_persisted_episodes(tmp_path: Path) -> None:
    path = tmp_path / "episodes.jsonl"
    episodes = [_episode(1), _episode(2, patch="diff b")]
    _populate(path, episodes)

    snapshot = EpisodeMemory(path).snapshot()
    assert len(snapshot) == 2
    assert {e.content_hash for e in snapshot.episodes} == {e.content_hash for e in episodes}


def test_snapshot_is_read_only_and_does_not_mutate(tmp_path: Path) -> None:
    path = tmp_path / "episodes.jsonl"
    _populate(path, [_episode(1)])
    before = path.read_bytes()

    EpisodeMemory(path).snapshot()

    assert path.read_bytes() == before  # the authoritative log is unchanged
    assert not (tmp_path / "episodes.db").exists()  # reading creates no index artifact


def test_snapshot_is_stable_across_calls(tmp_path: Path) -> None:
    path = tmp_path / "episodes.jsonl"
    _populate(path, [_episode(1), _episode(2, patch="diff b")])
    memory = EpisodeMemory(path)
    assert memory.snapshot().episodes == memory.snapshot().episodes


def test_missing_memory_yields_empty_snapshot(tmp_path: Path) -> None:
    snapshot = EpisodeMemory(tmp_path / "absent.jsonl").snapshot()
    assert len(snapshot) == 0
    assert snapshot.episodes == ()


def test_snapshot_surfaces_only_persisted_episodes(tmp_path: Path) -> None:
    # The source adds nothing: the snapshot is exactly what was persisted through the
    # guarded boundary (held-out-free by construction upstream, M4/M5/D8).
    path = tmp_path / "episodes.jsonl"
    episodes = [
        _episode(1),
        _episode(2, patch="diff b"),
        _episode(3, patch="diff c"),
    ]
    _populate(path, episodes)

    snapshot = EpisodeMemory(path).snapshot()
    assert [e.content_hash for e in snapshot.episodes] == [e.content_hash for e in episodes]
