"""Unit tests for the M7 arm memory view (M7-C5).

Scope: the projection in isolation (M7_SPEC §3.3/§6.5/§6.6) — the fixed order
(Episode Store -> Arm Filter -> Memory Snapshot), arm scoping, read-only behaviour
over the frozen store, snapshot immutability, and exact snapshot identity independent
of persistence order. The shared retriever (stage 4) is untouched here; the permanent
D7 invariant check is C6 and the end-to-end acceptance is C7.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from velith.arms.binding import resolve_binding
from velith.arms.identity import Arm
from velith.arms.memory_view import ArmMemoryView
from velith.corpus.heldout import GuardedEpisodeWriter, HeldOutError, HeldOutLock
from velith.corpus.manifest import CorpusManifest, Partition, PartitionEntry, task_identity
from velith.episodes.episode import Episode, VerdictState
from velith.episodes.store import EpisodeStore
from velith.retrieval.memory import EpisodeMemory


def _episode(
    prompt: str,
    state: VerdictState = VerdictState.PASSED,
    *,
    arm: Arm = Arm.A1,
    secondary: bool | None = True,
    flaky: bool = False,
) -> Episode:
    return Episode.build(
        task_id="t",
        seed=0,
        model="m",
        model_version="v",
        prompt=prompt,
        patch="diff",
        verdict_state=state,
        verdict_output="out",
        prompt_tokens=1,
        completion_tokens=2,
        latency_seconds=1.0,
        verify_seconds=2.0,
        velith_version="0.0.0",
        arm=arm.value,
        secondary_passed=secondary,
        flaky=flaky,
        timestamp="2026-07-06T00:00:00+00:00",
    )


def _populate(path: Path, episodes: list[Episode]) -> None:
    store = EpisodeStore(path)
    for episode in episodes:
        store.append(episode)


def _view(path: Path, arm: Arm) -> ArmMemoryView:
    return ArmMemoryView(resolve_binding(arm), EpisodeMemory(path))


def _mixed_outcomes(arm: Arm) -> list[Episode]:
    """One episode per interesting (verdict, secondary, flaky) combination."""
    return [
        _episode("pass", VerdictState.PASSED, arm=arm),
        _episode("pass-no-secondary", VerdictState.PASSED, arm=arm, secondary=None),
        _episode("pass-model-gap", VerdictState.PASSED, arm=arm, secondary=False),
        _episode("fail", VerdictState.FAILED, arm=arm, secondary=False),
        _episode("apply-failed", VerdictState.PATCH_APPLY_FAILED, arm=arm),
        _episode("no-patch", VerdictState.NO_PATCH, arm=arm),
        _episode("flaky-pass", VerdictState.PASSED, arm=arm, flaky=True),
    ]


def test_projection_scopes_to_the_arm(tmp_path: Path) -> None:
    """Stage 1 scopes the store by the frozen ``arm`` provenance (§3.3)."""
    path = tmp_path / "episodes.jsonl"
    mine = _episode("mine", arm=Arm.A1)
    _populate(path, [mine, _episode("theirs", arm=Arm.A2), _episode("cold", arm=Arm.A0)])

    snapshot = _view(path, Arm.A1).snapshot()
    assert [e.content_hash for e in snapshot.episodes] == [mine.content_hash]


def test_unfiltered_arm_retains_every_one_of_its_episodes(tmp_path: Path) -> None:
    """A1 admits every outcome category of its own arm."""
    path = tmp_path / "episodes.jsonl"
    episodes = _mixed_outcomes(Arm.A1)
    _populate(path, episodes)

    snapshot = _view(path, Arm.A1).snapshot()
    assert {e.content_hash for e in snapshot.episodes} == {e.content_hash for e in episodes}


def test_verified_arm_retains_only_verified_signal(tmp_path: Path) -> None:
    """A2 admits exactly the verified successes and verified failures (§3.2)."""
    path = tmp_path / "episodes.jsonl"
    episodes = _mixed_outcomes(Arm.A2)
    _populate(path, episodes)

    snapshot = _view(path, Arm.A2).snapshot()
    admitted = {e.prompt for e in snapshot.episodes}
    assert admitted == {"pass", "pass-no-secondary", "fail"}


def test_arms_differ_only_where_their_filters_differ(tmp_path: Path) -> None:
    """Over identical experience, A2's memory is exactly A1's minus the excluded (§6.6)."""
    a1_path, a2_path = tmp_path / "a1.jsonl", tmp_path / "a2.jsonl"
    _populate(a1_path, _mixed_outcomes(Arm.A1))
    _populate(a2_path, _mixed_outcomes(Arm.A2))

    a1 = {e.prompt for e in _view(a1_path, Arm.A1).snapshot().episodes}
    a2 = {e.prompt for e in _view(a2_path, Arm.A2).snapshot().episodes}
    assert a2 < a1
    assert a1 - a2 == {"pass-model-gap", "apply-failed", "no-patch", "flaky-pass"}


def test_projection_is_read_only(tmp_path: Path) -> None:
    """The log is byte-unchanged: no write, append, delete, mutation, or re-order."""
    path = tmp_path / "episodes.jsonl"
    _populate(path, _mixed_outcomes(Arm.A2))
    before = path.read_bytes()

    for _ in range(3):
        _view(path, Arm.A2).snapshot()

    assert path.read_bytes() == before


def test_no_grounding_record_is_deleted_by_filtering(tmp_path: Path) -> None:
    """Filtering is admission into memory, never deletion from the log (D2/D3)."""
    path = tmp_path / "episodes.jsonl"
    episodes = _mixed_outcomes(Arm.A2)
    _populate(path, episodes)

    snapshot = _view(path, Arm.A2).snapshot()
    assert len(snapshot) < len(episodes)  # the filter excluded some from memory
    stored = EpisodeStore(path).read_all()
    assert [e.content_hash for e in stored] == [e.content_hash for e in episodes]


def test_snapshot_is_immutable(tmp_path: Path) -> None:
    """The snapshot is fixed once formed - never mutated, appended to, or re-filtered."""
    path = tmp_path / "episodes.jsonl"
    _populate(path, _mixed_outcomes(Arm.A1))
    snapshot = _view(path, Arm.A1).snapshot()

    assert isinstance(snapshot.episodes, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(snapshot, "episodes", ())


def test_identical_episodes_and_arm_yield_an_identical_snapshot(tmp_path: Path) -> None:
    """Repeated projection over unchanged experience is byte-identical (§6.6)."""
    path = tmp_path / "episodes.jsonl"
    _populate(path, _mixed_outcomes(Arm.A2))

    first = _view(path, Arm.A2).snapshot()
    second = _view(path, Arm.A2).snapshot()
    assert first == second
    assert [e.model_dump_json() for e in first.episodes] == [
        e.model_dump_json() for e in second.episodes
    ]


def test_snapshot_is_independent_of_persistence_order(tmp_path: Path) -> None:
    """Persistence order must not leak into the snapshot (§6.6, D8/D16.1/D18)."""
    episodes = _mixed_outcomes(Arm.A2)
    forward, reverse = tmp_path / "forward.jsonl", tmp_path / "reverse.jsonl"
    _populate(forward, episodes)
    _populate(reverse, list(reversed(episodes)))

    ordered = _view(forward, Arm.A2).snapshot()
    shuffled = _view(reverse, Arm.A2).snapshot()
    assert [e.model_dump_json() for e in ordered.episodes] == [
        e.model_dump_json() for e in shuffled.episodes
    ]


def test_snapshot_order_is_content_addressed(tmp_path: Path) -> None:
    """The canonical order depends only on episode content (§6.6)."""
    path = tmp_path / "episodes.jsonl"
    _populate(path, _mixed_outcomes(Arm.A1))

    episodes = _view(path, Arm.A1).snapshot().episodes
    assert list(episodes) == sorted(episodes, key=lambda e: (e.content_hash, e.model_dump_json()))


def test_memory_is_held_out_free_by_the_inherited_guarantee(tmp_path: Path) -> None:
    """Held-out experience was never persisted, so no arm's memory can surface it (D8)."""
    manifest = CorpusManifest.from_entries(
        [
            PartitionEntry(label="avail", material="M-avail", partition=Partition.AVAILABLE),
            PartitionEntry(label="held", material="M-held", partition=Partition.HELD_OUT),
        ]
    )
    path = tmp_path / "episodes.jsonl"
    writer = GuardedEpisodeWriter(HeldOutLock(manifest), EpisodeStore(path))

    available = _episode("available", arm=Arm.A1)
    writer.persist(task_identity("M-avail"), available)
    with pytest.raises(HeldOutError):
        writer.persist(task_identity("M-held"), _episode("held-out", arm=Arm.A1))

    snapshot = _view(path, Arm.A1).snapshot()
    assert [e.content_hash for e in snapshot.episodes] == [available.content_hash]
