"""Hermetic acceptance for the M7 write-filter policies (M7-C7).

End-to-end through the wired M7 seams — arm identity, the two write-filters, the
run-immutable arm->filter binding, and the arm memory view — composed onto the frozen
M3 store and the **unchanged** M6 retrieval substrate, with no model and no network
(the M6 reference embedding is in-process). Pins the M7 Definition of Done
(M7_SPEC §6):

* A1 admits every episode of its arm (2); A2 admits exactly verified successes and
  verified failures and excludes the model-gap ``PASSED``, ``PATCH_APPLY_FAILED``,
  ``NO_PATCH``, and every ``flaky`` episode (1, 3).
* The arm->filter binding is total and immutable; A0 has no policy (4).
* The fixed projection order Episode Store -> Arm Filter -> Memory Snapshot ->
  Shared Retriever holds; the grounding log is byte-unchanged; no record is deleted,
  mutated, or re-ordered (5).
* Identical persisted episodes + identical arm yield an identical snapshot (6).
* Both arms retrieve through the identical shared substrate (7).
* No arm's memory contains a held-out episode; A0 is neither depended upon nor
  modified (8).
* A non-software memory filters and retrieves through the identical path (9).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

import velith.arms
from velith.arms.binding import BindingError, resolve_binding
from velith.arms.identity import M7_ARMS, Arm
from velith.arms.memory_view import ArmMemoryView
from velith.corpus.heldout import GuardedEpisodeWriter, HeldOutError, HeldOutLock
from velith.corpus.manifest import CorpusManifest, Partition, PartitionEntry, task_identity
from velith.episodes.episode import Episode, VerdictState
from velith.episodes.store import EpisodeStore
from velith.retrieval.embedding import EMBEDDER_NAME, get_embedder
from velith.retrieval.memory import EpisodeMemory
from velith.retrieval.query import derive_query
from velith.retrieval.retriever import Retriever


def _episode(
    prompt: str,
    state: VerdictState = VerdictState.PASSED,
    *,
    arm: Arm = Arm.A1,
    secondary: bool | None = True,
    flaky: bool = False,
    patch: str = "--- a/x\n+++ b/x\n",
) -> Episode:
    return Episode.build(
        task_id="t",
        seed=0,
        model="m",
        model_version="v",
        prompt=prompt,
        patch=patch,
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


def _all_outcomes(arm: Arm) -> list[Episode]:
    """One episode per interesting (verdict, secondary, flaky) combination for an arm."""
    return [
        _episode("verified-pass", VerdictState.PASSED, arm=arm),
        _episode("verified-pass-no-secondary", VerdictState.PASSED, arm=arm, secondary=None),
        _episode("model-gap-pass", VerdictState.PASSED, arm=arm, secondary=False),
        _episode("verified-fail", VerdictState.FAILED, arm=arm, secondary=False),
        _episode("apply-failed", VerdictState.PATCH_APPLY_FAILED, arm=arm, patch=""),
        _episode("no-patch", VerdictState.NO_PATCH, arm=arm, patch=""),
        _episode("infra-error", VerdictState.INFRA_ERROR, arm=arm, patch=""),
        _episode("flaky-pass", VerdictState.PASSED, arm=arm, flaky=True),
        _episode("flaky-fail", VerdictState.FAILED, arm=arm, flaky=True),
    ]


def _populate(path: Path, episodes: list[Episode]) -> None:
    store = EpisodeStore(path)
    for episode in episodes:
        store.append(episode)


def _view(path: Path, arm: Arm) -> ArmMemoryView:
    return ArmMemoryView(resolve_binding(arm), EpisodeMemory(path))


#: The A2-admitted subset of ``_all_outcomes`` — verified success + verified failure.
VERIFIED_ADMITTED = {"verified-pass", "verified-pass-no-secondary", "verified-fail"}


def test_a1_retains_every_episode_of_its_arm(tmp_path: Path) -> None:
    """DoD 2: the unfiltered control admits every outcome category."""
    path = tmp_path / "episodes.jsonl"
    episodes = _all_outcomes(Arm.A1)
    _populate(path, episodes)

    snapshot = _view(path, Arm.A1).snapshot()
    assert {e.content_hash for e in snapshot.episodes} == {e.content_hash for e in episodes}


def test_a2_retains_exactly_verified_signal(tmp_path: Path) -> None:
    """DoD 1/3: A2 admits exactly verified successes and failures, nothing else."""
    path = tmp_path / "episodes.jsonl"
    _populate(path, _all_outcomes(Arm.A2))

    snapshot = _view(path, Arm.A2).snapshot()
    assert {e.prompt for e in snapshot.episodes} == VERIFIED_ADMITTED


def test_a2_excludes_model_gap_unverified_and_flaky(tmp_path: Path) -> None:
    """DoD 3: the exhaustive A2 exclusion, verified end-to-end."""
    path = tmp_path / "episodes.jsonl"
    _populate(path, _all_outcomes(Arm.A2))

    admitted = {e.prompt for e in _view(path, Arm.A2).snapshot().episodes}
    for excluded in (
        "model-gap-pass",
        "apply-failed",
        "no-patch",
        "infra-error",
        "flaky-pass",
        "flaky-fail",
    ):
        assert excluded not in admitted


def test_binding_is_total_and_immutable_and_a0_has_no_policy() -> None:
    """DoD 4: every M7 arm binds to one filter; A0 has no retention policy."""
    for arm in M7_ARMS:
        binding = resolve_binding(arm)
        assert binding.arm is arm
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(binding, "write_filter", resolve_binding(arm).write_filter)
    with pytest.raises(BindingError, match="A0"):
        resolve_binding(Arm.A0)


def test_projection_order_holds_and_the_log_is_unchanged(tmp_path: Path) -> None:
    """DoD 5: Store -> Filter -> Snapshot; the grounding log is byte-unchanged."""
    path = tmp_path / "episodes.jsonl"
    episodes = _all_outcomes(Arm.A2)
    _populate(path, episodes)
    before = path.read_bytes()

    snapshot = _view(path, Arm.A2).snapshot()

    # Filter ran (memory is a strict subset), yet the store is intact and ordered.
    assert 0 < len(snapshot) < len(episodes)
    assert path.read_bytes() == before
    stored = EpisodeStore(path).read_all()
    assert [e.content_hash for e in stored] == [e.content_hash for e in episodes]


def test_identical_episodes_and_arm_yield_identical_snapshot(tmp_path: Path) -> None:
    """DoD 6: the snapshot is exact and independent of persistence order."""
    episodes = _all_outcomes(Arm.A2)
    forward, reverse = tmp_path / "f.jsonl", tmp_path / "r.jsonl"
    _populate(forward, episodes)
    _populate(reverse, list(reversed(episodes)))

    a = _view(forward, Arm.A2).snapshot()
    b = _view(reverse, Arm.A2).snapshot()
    assert [e.model_dump_json() for e in a.episodes] == [e.model_dump_json() for e in b.episodes]


def test_both_arms_retrieve_through_the_identical_substrate(tmp_path: Path) -> None:
    """DoD 7: one shared retriever/embedder/top-k ranks both arms' memories."""
    path = tmp_path / "episodes.jsonl"
    _populate(path, _all_outcomes(Arm.A1) + _all_outcomes(Arm.A2))

    # The identical retriever instance is applied to each arm's filtered snapshot;
    # only the memory (the write-filter's output) differs.
    retriever = Retriever(get_embedder(EMBEDDER_NAME), 5)
    query = derive_query("verified-pass")

    a1_memory = _view(path, Arm.A1).snapshot()
    a2_memory = _view(path, Arm.A2).snapshot()
    a1_hits = retriever.retrieve(query, a1_memory)
    a2_hits = retriever.retrieve(query, a2_memory)

    # Deterministic through the shared substrate.
    assert [e.content_hash for e in a1_hits] == [
        e.content_hash for e in retriever.retrieve(query, a1_memory)
    ]
    # Every retrieved episode came from that arm's own filtered memory.
    assert {e.content_hash for e in a1_hits} <= {e.content_hash for e in a1_memory.episodes}
    assert {e.content_hash for e in a2_hits} <= {e.content_hash for e in a2_memory.episodes}


def test_no_arm_memory_contains_a_held_out_episode(tmp_path: Path) -> None:
    """DoD 8: held-out was never persisted, so no arm can surface it."""
    manifest = CorpusManifest.from_entries(
        [
            PartitionEntry(label="avail", material="M-avail", partition=Partition.AVAILABLE),
            PartitionEntry(label="held", material="M-held", partition=Partition.HELD_OUT),
        ]
    )
    path = tmp_path / "episodes.jsonl"
    writer = GuardedEpisodeWriter(HeldOutLock(manifest), EpisodeStore(path))

    available = _episode("available", VerdictState.PASSED, arm=Arm.A2)
    writer.persist(task_identity("M-avail"), available)
    with pytest.raises(HeldOutError):
        writer.persist(task_identity("M-held"), _episode("held", VerdictState.PASSED, arm=Arm.A2))

    for arm in M7_ARMS:
        snapshot = _view(path, arm).snapshot()
        assert all(e.prompt != "held" for e in snapshot.episodes)
    assert {e.content_hash for e in _view(path, Arm.A2).snapshot().episodes} == {
        available.content_hash
    }


def test_a0_runner_is_neither_depended_upon_nor_modified() -> None:
    """DoD 8: the arm layer never imports the frozen A0/batch runner."""
    assert velith.arms.__file__ is not None
    for source in Path(velith.arms.__file__).parent.glob("*.py"):
        assert "velith.batch" not in source.read_text(encoding="utf-8")


def test_non_software_memory_filters_and_retrieves_identically(tmp_path: Path) -> None:
    """DoD 9: domain-neutral - a non-software memory flows through the identical path."""
    path = tmp_path / "episodes.jsonl"
    _populate(
        path,
        [
            _episode("melody:C-E-G;bpm=120", VerdictState.PASSED, arm=Arm.A2),
            _episode("melody:D-F-A;bpm=90", VerdictState.FAILED, arm=Arm.A2, secondary=False),
            _episode("melody:E-G-B;bpm=60", VerdictState.PASSED, arm=Arm.A2, secondary=False),
        ],
    )

    snapshot = _view(path, Arm.A2).snapshot()
    # The model-gap PASSED is excluded; the verified pass and verified fail remain.
    assert {e.prompt for e in snapshot.episodes} == {
        "melody:C-E-G;bpm=120",
        "melody:D-F-A;bpm=90",
    }
    hits = Retriever(get_embedder(EMBEDDER_NAME), 2).retrieve(
        derive_query("melody:C-E-G;bpm=120"), snapshot
    )
    assert {e.content_hash for e in hits} <= {e.content_hash for e in snapshot.episodes}
