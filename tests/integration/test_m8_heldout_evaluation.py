"""Hermetic acceptance for M8 — frozen checkpointed held-out evaluation (M8-C10).

End-to-end through the wired M8 seams — checkpoint (C2), held-out set (C3), context
assembly (C4), memory-conditioned attempt (C5), record + sink (C6), provenance (C7), and
the cost-guarded runner (C8) — over the frozen M3 store and the unchanged M6 substrate,
with no model and no network (mocked proposer + stub verifier, in-process embedding). Pins
the M8 Definition of Done (M8_SPEC §6 DoD 1-8):

* A0/A1/A2 evaluate on held-out through the **identical** harness (2), and at an **empty
  checkpoint** the attempt input is **bit-for-bit identical** across arms (2);
* the recorded outcome is the **deterministic verifier verdict** (with secondary) plus the
  frozen token counts and **no model score** (4);
* records land **only** in the segregated sink; **no held-out episode enters any arm's
  memory or the experience log** and the guarded boundary fail-closes (5);
* evaluation is **deterministic** for a fixed (arm, checkpoint, task, seed) (6);
* the **evaluation identity is content-addressed** (7);
* **no statistic is computed** (8); and a **non-software** held-out set evaluates through
  the identical path (domain-neutral).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from velith.agent.proposer import Proposal
from velith.arms.identity import Arm
from velith.batch.budget import CostGuard
from velith.corpus.heldout import GuardedEpisodeWriter, HeldOutError, HeldOutLock
from velith.corpus.loader import CorpusTask
from velith.corpus.manifest import CorpusManifest, Partition, PartitionEntry, task_identity
from velith.episodes.episode import Episode, VerdictState
from velith.episodes.store import EpisodeStore
from velith.evaluation.attempt import HeldOutAttempt
from velith.evaluation.checkpoint import Checkpoint, form_checkpoint
from velith.evaluation.heldout_set import HeldOutEvaluationSet
from velith.evaluation.provenance import EvaluationProvenance
from velith.evaluation.record import EvaluationRecord
from velith.evaluation.runner import run_heldout_evaluation
from velith.evaluation.sink import EvaluationSink
from velith.harness.verifier_sandbox import Verdict
from velith.retrieval.embedding import EMBEDDER_NAME, get_embedder
from velith.retrieval.memory import EpisodeMemory
from velith.retrieval.retriever import Retriever
from velith.task import Task

_MANIFEST_HASH = "manifest-hash-1"


class RecordingProposer:
    """Records each conditioned task; returns a fixed proposal (no model score)."""

    def __init__(self) -> None:
        self.seen: list[Task] = []

    def propose(self, task: Task, seed: int) -> Proposal:
        self.seen.append(task)
        return Proposal(
            patch="--- a/x\n+++ b/x\n",
            prompt=task.prompt,
            prompt_tokens=10,
            completion_tokens=20,
            latency_seconds=1.0,
            model="mock-model",
            model_version="mock-1",
        )


class StubVerifier:
    def verify(self, task: Task, patch: str) -> Verdict:
        return Verdict(
            state=VerdictState.PASSED,
            output="1 passed",
            secondary_passed=True,
            flaky=False,
            duration_seconds=2.0,
        )


class OneTaskAdapter:
    def materialize(self, corpus_task: CorpusTask) -> Task:
        return Task(
            task_id="t",
            repo_path=Path("tests/fixtures/calc_add_bug"),
            prompt="base task prompt",
            hidden_test_command=("python", "-m", "pytest", "-q"),
        )


def _heldout_set(materials: list[str]) -> HeldOutEvaluationSet:
    tasks = tuple(
        CorpusTask(label=m, material=m, handle="H", partition=Partition.HELD_OUT) for m in materials
    )
    return HeldOutEvaluationSet(tasks=tasks, manifest_hash=_MANIFEST_HASH)


def _attempt(proposer: RecordingProposer | None = None) -> HeldOutAttempt:
    return HeldOutAttempt(
        proposer=proposer if proposer is not None else RecordingProposer(),
        verifier=StubVerifier(),
        retriever=Retriever(get_embedder(EMBEDDER_NAME), 5),
        adapter=OneTaskAdapter(),
        eval_seed=0,
    )


def _checkpoint(arm: Arm, memory_path: Path) -> Checkpoint:
    return form_checkpoint(arm, EpisodeMemory(memory_path))


def _provenance(checkpoint: Checkpoint) -> EvaluationProvenance:
    return EvaluationProvenance(
        checkpoint_identity=checkpoint.identity,
        manifest_hash=_MANIFEST_HASH,
        arm=checkpoint.arm.value,
        base_model="qwen2.5-coder",
        eval_seed=0,
        max_tasks=0,
        max_attempts_per_task=1,
        max_tokens=0,
    )


def _run(arm: Arm, heldout: HeldOutEvaluationSet, tmp_path: Path) -> tuple[EvaluationRecord, ...]:
    checkpoint = _checkpoint(arm, tmp_path / "none.jsonl")
    sink = EvaluationSink(tmp_path / f"{arm.value}.jsonl")
    return run_heldout_evaluation(
        checkpoint,
        heldout,
        _provenance(checkpoint),
        attempt=_attempt(),
        sink=sink,
        guard=CostGuard(0, 1, 0),
    )


def test_all_three_arms_evaluate_heldout_through_the_identical_harness(tmp_path: Path) -> None:
    """DoD 2: A0/A1/A2 each sweep the held-out set through the one runner."""
    heldout = _heldout_set(["M-a", "M-b"])
    for arm in (Arm.A0, Arm.A1, Arm.A2):
        records = _run(arm, heldout, tmp_path / arm.value)
        assert len(records) == 2
        assert all(r.arm == arm.value for r in records)


def test_empty_checkpoint_attempts_are_bit_identical_across_arms(tmp_path: Path) -> None:
    """DoD 2: at an empty checkpoint the conditioned attempt input is identical (§3.3)."""
    task = CorpusTask(label="h", material="M-held", handle="H", partition=Partition.HELD_OUT)
    prompts: list[str] = []
    for arm in (Arm.A0, Arm.A1, Arm.A2):
        proposer = RecordingProposer()
        checkpoint = _checkpoint(arm, tmp_path / "none.jsonl")
        _attempt(proposer).attempt(checkpoint, task)
        prompts.append(proposer.seen[0].prompt)
    assert prompts[0] == prompts[1] == prompts[2]


def test_recorded_outcome_is_verdict_with_token_counts_and_no_model_score(tmp_path: Path) -> None:
    """DoD 4: the measurement is the verifier verdict + secondary + token counts."""
    records = _run(Arm.A1, _heldout_set(["M-a"]), tmp_path)
    record = records[0]
    assert record.verdict_state is VerdictState.PASSED
    assert record.secondary_passed is True
    assert record.prompt_tokens == 10
    assert record.completion_tokens == 20
    forbidden = ("score", "reward", "rating", "confidence", "logprob", "judge")
    assert not any(token in name for name in EvaluationRecord.model_fields for token in forbidden)


def test_records_land_only_in_the_sink_never_the_experience_log(tmp_path: Path) -> None:
    """DoD 5: evaluation writes only to the sink; the experience log is untouched."""
    episode_log = tmp_path / "episodes.jsonl"
    store = EpisodeStore(episode_log)
    checkpoint = _checkpoint(Arm.A2, tmp_path / "none.jsonl")
    sink = EvaluationSink(tmp_path / "eval.jsonl")

    run_heldout_evaluation(
        checkpoint,
        _heldout_set(["M-a", "M-b"]),
        _provenance(checkpoint),
        attempt=_attempt(),
        sink=sink,
        guard=CostGuard(0, 1, 0),
    )

    assert len(sink.read_all()) == 2
    assert not store.read_all()
    assert not episode_log.exists() or episode_log.read_text(encoding="utf-8") == ""


def test_no_heldout_episode_enters_memory_and_boundary_failcloses(tmp_path: Path) -> None:
    """DoD 5: held-out is never persisted as experience and the boundary fail-closes (D8)."""
    manifest = CorpusManifest.from_entries(
        [
            PartitionEntry(label="avail", material="M-avail", partition=Partition.AVAILABLE),
            PartitionEntry(label="held", material="M-held", partition=Partition.HELD_OUT),
        ]
    )
    episode_log = tmp_path / "episodes.jsonl"
    writer = GuardedEpisodeWriter(HeldOutLock(manifest), EpisodeStore(episode_log))
    available = _episode("available experience", Arm.A1)
    writer.persist(task_identity("M-avail"), available)
    with pytest.raises(HeldOutError):
        writer.persist(task_identity("M-held"), _episode("held-out leak", Arm.A1))

    # Evaluate held-out; the A1 checkpoint memory holds only the available episode.
    checkpoint = _checkpoint(Arm.A1, episode_log)
    assert [e.content_hash for e in checkpoint.memory.episodes] == [available.content_hash]
    run_heldout_evaluation(
        checkpoint,
        _heldout_set(["M-held"]),
        _provenance(checkpoint),
        attempt=_attempt(),
        sink=EvaluationSink(tmp_path / "eval.jsonl"),
        guard=CostGuard(0, 1, 0),
    )
    # The experience memory is unchanged after evaluation — no held-out leaked in.
    after = EpisodeMemory(episode_log).snapshot()
    assert [e.content_hash for e in after.episodes] == [available.content_hash]


def test_evaluation_is_deterministic_for_fixed_inputs(tmp_path: Path) -> None:
    """DoD 6: the same (arm, checkpoint, task, seed) yields the same records."""
    heldout = _heldout_set(["M-a", "M-b"])
    first = _run(Arm.A1, heldout, tmp_path / "run1")
    second = _run(Arm.A1, heldout, tmp_path / "run2")
    assert first == second


def test_evaluation_identity_is_content_addressed(tmp_path: Path) -> None:
    """DoD 7: records carry the content-addressed identity, bound to checkpoint + split."""
    checkpoint = _checkpoint(Arm.A1, tmp_path / "none.jsonl")
    provenance = _provenance(checkpoint)
    records = _run(Arm.A1, _heldout_set(["M-a"]), tmp_path)
    assert {r.evaluation_identity for r in records} == {provenance.identity}
    # A different arm is a different evaluation identity.
    other = _checkpoint(Arm.A2, tmp_path / "none.jsonl")
    assert _provenance(other).identity != provenance.identity


def test_runner_returns_per_task_records_only_no_statistic(tmp_path: Path) -> None:
    """DoD 8: the result is per-task measurements only — no aggregate is computed."""
    records = _run(Arm.A1, _heldout_set(["M-a", "M-b", "M-c"]), tmp_path)
    assert len(records) == 3
    assert all(isinstance(r, EvaluationRecord) for r in records)


def test_non_software_heldout_set_evaluates_through_the_identical_path(tmp_path: Path) -> None:
    """Domain-neutral: a non-software held-out set evaluates identically (D9/D22)."""
    heldout = _heldout_set(["melody:C-E-G;bpm=120", "dish:soup;salt=2g"])
    records = _run(Arm.A2, heldout, tmp_path)
    assert len(records) == 2
    assert {r.task_identity for r in records} == {t.identity for t in heldout}


def _episode(prompt: str, arm: Arm) -> Episode:
    return Episode.build(
        task_id="t",
        seed=0,
        model="m",
        model_version="v",
        prompt=prompt,
        patch="diff",
        verdict_state=VerdictState.PASSED,
        verdict_output="out",
        prompt_tokens=1,
        completion_tokens=2,
        latency_seconds=1.0,
        verify_seconds=2.0,
        velith_version="0.0.0",
        arm=arm.value,
        secondary_passed=True,
        flaky=False,
        timestamp="2026-07-06T00:00:00+00:00",
    )
