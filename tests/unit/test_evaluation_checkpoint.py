"""Unit tests for the M8 evaluation checkpoint (M8-C2).

Scope: the checkpoint in isolation (M8_SPEC §3.1) — order-independent content-addressed
identity, A0 empty by construction, an empty checkpoint shared across arms, distinct
identities for distinct memories, read-only formation, and immutability. The held-out
set (C3), the attempt (C5), and the runner (C8) are not under test here.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from velith.arms.identity import Arm
from velith.episodes.episode import Episode, VerdictState
from velith.episodes.store import EpisodeStore
from velith.evaluation.checkpoint import Checkpoint, form_checkpoint
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


def _memory(path: Path) -> EpisodeMemory:
    return EpisodeMemory(path)


def test_a0_checkpoint_is_empty(tmp_path: Path) -> None:
    """A0 is memoryless: its checkpoint is empty regardless of stored experience."""
    path = tmp_path / "episodes.jsonl"
    _populate(path, [_episode("a", arm=Arm.A0), _episode("b", arm=Arm.A1)])

    checkpoint = form_checkpoint(Arm.A0, _memory(path))
    assert checkpoint.is_empty
    assert len(checkpoint) == 0


def test_empty_checkpoint_shares_one_identity_across_arms(tmp_path: Path) -> None:
    """A0 and empty A1/A2 all yield the same empty checkpoint identity (§3.1)."""
    empty = tmp_path / "empty.jsonl"
    _populate(empty, [])

    a0 = form_checkpoint(Arm.A0, _memory(empty))
    a1 = form_checkpoint(Arm.A1, _memory(empty))
    a2 = form_checkpoint(Arm.A2, _memory(empty))
    assert a0.is_empty and a1.is_empty and a2.is_empty
    assert a0.identity == a1.identity == a2.identity


def test_checkpoint_identity_is_order_independent(tmp_path: Path) -> None:
    """Persistence order must not change the checkpoint identity (§3.1)."""
    episodes = [_episode("a", arm=Arm.A1), _episode("b", arm=Arm.A1), _episode("c", arm=Arm.A1)]
    forward, reverse = tmp_path / "f.jsonl", tmp_path / "r.jsonl"
    _populate(forward, episodes)
    _populate(reverse, list(reversed(episodes)))

    assert form_checkpoint(Arm.A1, _memory(forward)).identity == (
        form_checkpoint(Arm.A1, _memory(reverse)).identity
    )


def test_identical_experience_yields_identical_checkpoint(tmp_path: Path) -> None:
    """The same episodes and arm always produce the same checkpoint."""
    episodes = [_episode("a", arm=Arm.A1), _episode("b", arm=Arm.A1)]
    one, two = tmp_path / "one.jsonl", tmp_path / "two.jsonl"
    _populate(one, episodes)
    _populate(two, episodes)

    first, second = form_checkpoint(Arm.A1, _memory(one)), form_checkpoint(Arm.A1, _memory(two))
    assert first.identity == second.identity
    assert [e.content_hash for e in first.memory.episodes] == [
        e.content_hash for e in second.memory.episodes
    ]


def test_distinct_memories_have_distinct_identities(tmp_path: Path) -> None:
    """A1 and A2 filter the same experience differently, so identities differ (§3.1)."""
    # A model-gap PASSED is admitted by A1 but excluded by A2, so the memories differ.
    a1_path = tmp_path / "a1.jsonl"
    _populate(
        a1_path,
        [
            _episode("verified", VerdictState.PASSED, arm=Arm.A1, secondary=True),
            _episode("model-gap", VerdictState.PASSED, arm=Arm.A1, secondary=False),
        ],
    )
    a2_path = tmp_path / "a2.jsonl"
    _populate(
        a2_path,
        [
            _episode("verified", VerdictState.PASSED, arm=Arm.A2, secondary=True),
            _episode("model-gap", VerdictState.PASSED, arm=Arm.A2, secondary=False),
        ],
    )

    a1 = form_checkpoint(Arm.A1, _memory(a1_path))
    a2 = form_checkpoint(Arm.A2, _memory(a2_path))
    assert len(a1) == 2
    assert len(a2) == 1
    assert a1.identity != a2.identity


def test_forming_a_checkpoint_is_read_only(tmp_path: Path) -> None:
    """Forming a checkpoint writes and mutates nothing (§3.1)."""
    path = tmp_path / "episodes.jsonl"
    _populate(path, [_episode("a", arm=Arm.A1), _episode("b", arm=Arm.A1)])
    before = path.read_bytes()

    for _ in range(3):
        form_checkpoint(Arm.A1, _memory(path))

    assert path.read_bytes() == before


def test_checkpoint_is_immutable(tmp_path: Path) -> None:
    """A formed checkpoint cannot shift (§3.1)."""
    path = tmp_path / "episodes.jsonl"
    _populate(path, [_episode("a", arm=Arm.A1)])
    checkpoint = form_checkpoint(Arm.A1, _memory(path))

    assert isinstance(checkpoint, Checkpoint)
    for field, value in (("identity", "x"), ("arm", Arm.A2)):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(checkpoint, field, value)
