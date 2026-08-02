"""Unit tests for the M8 held-out evaluation runner (M8-C8).

Hermetic (mocked proposer + stub verifier). Pins M8_SPEC §3.5/§5: the sweep evaluates the
held-out set end to end and writes to the sink only; the cost guard halts loudly with no
partial record; nothing reaches the experience log or any memory source; A0/A1/A2 run
through the identical runner; and a provenance that does not match the checkpoint/split
fails loudly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from velith.agent.proposer import Proposal
from velith.arms.identity import Arm
from velith.batch.budget import CostBudgetError, CostGuard
from velith.corpus.loader import CorpusTask
from velith.corpus.manifest import Partition
from velith.episodes.episode import VerdictState
from velith.episodes.store import EpisodeStore
from velith.evaluation.attempt import HeldOutAttempt
from velith.evaluation.checkpoint import Checkpoint, form_checkpoint
from velith.evaluation.heldout_set import HeldOutEvaluationSet
from velith.evaluation.provenance import EvaluationProvenance
from velith.evaluation.runner import EvaluationError, run_heldout_evaluation
from velith.evaluation.sink import EvaluationSink
from velith.harness.verifier_sandbox import Verdict
from velith.retrieval.embedding import EMBEDDER_NAME, get_embedder
from velith.retrieval.memory import EpisodeMemory
from velith.retrieval.retriever import Retriever
from velith.task import Task

_MANIFEST_HASH = "manifest-hash-1"


class StubProposer:
    def propose(self, task: Task, seed: int) -> Proposal:
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


def _heldout_set(n: int) -> HeldOutEvaluationSet:
    tasks = tuple(
        CorpusTask(label=f"h{i}", material=f"M-{i}", handle="H", partition=Partition.HELD_OUT)
        for i in range(n)
    )
    return HeldOutEvaluationSet(tasks=tasks, manifest_hash=_MANIFEST_HASH)


def _attempt(eval_seed: int = 0) -> HeldOutAttempt:
    return HeldOutAttempt(
        proposer=StubProposer(),
        verifier=StubVerifier(),
        retriever=Retriever(get_embedder(EMBEDDER_NAME), 5),
        adapter=OneTaskAdapter(),
        eval_seed=eval_seed,
    )


def _checkpoint(arm: Arm, tmp_path: Path) -> Checkpoint:
    return form_checkpoint(arm, EpisodeMemory(tmp_path / "none.jsonl"))


def _provenance(
    checkpoint: Checkpoint, *, max_tasks: int = 0, max_tokens: int = 0
) -> EvaluationProvenance:
    return EvaluationProvenance(
        checkpoint_identity=checkpoint.identity,
        manifest_hash=_MANIFEST_HASH,
        arm=checkpoint.arm.value,
        base_model="qwen2.5-coder",
        eval_seed=0,
        max_tasks=max_tasks,
        max_attempts_per_task=1,
        max_tokens=max_tokens,
    )


def test_sweep_evaluates_heldout_end_to_end_writing_to_sink_only(tmp_path: Path) -> None:
    """Every held-out task yields one record in the sink under the evaluation identity."""
    checkpoint = _checkpoint(Arm.A1, tmp_path)
    heldout = _heldout_set(3)
    provenance = _provenance(checkpoint)
    sink = EvaluationSink(tmp_path / "eval" / "heldout.jsonl")

    records = run_heldout_evaluation(
        checkpoint,
        heldout,
        provenance,
        attempt=_attempt(),
        sink=sink,
        guard=CostGuard(0, 1, 0),
    )

    assert len(records) == 3
    assert sink.read_all() == records
    assert {r.evaluation_identity for r in records} == {provenance.identity}
    assert {r.task_identity for r in records} == {t.identity for t in heldout}


def test_cost_guard_halts_loudly_with_no_partial_record(tmp_path: Path) -> None:
    """A task-budget limit halts the sweep loudly; only complete records are written."""
    checkpoint = _checkpoint(Arm.A1, tmp_path)
    sink = EvaluationSink(tmp_path / "heldout.jsonl")

    with pytest.raises(CostBudgetError):
        run_heldout_evaluation(
            checkpoint,
            _heldout_set(3),
            _provenance(checkpoint, max_tasks=1),
            attempt=_attempt(),
            sink=sink,
            guard=CostGuard(1, 1, 0),
        )

    written = sink.read_all()
    assert len(written) == 1  # exactly the first task; no partial record for the halted task


def test_token_budget_halt_writes_no_record_for_the_halted_task(tmp_path: Path) -> None:
    """Charging before writing means a token-budget halt leaves no partial record."""
    checkpoint = _checkpoint(Arm.A1, tmp_path)
    sink = EvaluationSink(tmp_path / "heldout.jsonl")

    # Each attempt charges 30 tokens; a 10-token budget halts on the very first task.
    with pytest.raises(CostBudgetError):
        run_heldout_evaluation(
            checkpoint,
            _heldout_set(2),
            _provenance(checkpoint, max_tokens=10),
            attempt=_attempt(),
            sink=sink,
            guard=CostGuard(0, 1, 10),
        )

    assert sink.read_all() == ()  # nothing written


def test_nothing_is_written_to_the_experience_log(tmp_path: Path) -> None:
    """The runner writes only to the sink, never to the experience log (D8)."""
    checkpoint = _checkpoint(Arm.A2, tmp_path)
    episode_log = tmp_path / "episodes.jsonl"
    store = EpisodeStore(episode_log)

    run_heldout_evaluation(
        checkpoint,
        _heldout_set(2),
        _provenance(checkpoint),
        attempt=_attempt(),
        sink=EvaluationSink(tmp_path / "eval.jsonl"),
        guard=CostGuard(0, 1, 0),
    )

    assert not store.read_all()
    assert not episode_log.exists() or episode_log.read_text(encoding="utf-8") == ""


def test_all_three_arms_run_through_the_identical_runner(tmp_path: Path) -> None:
    """A0, A1, and A2 each sweep through the same function (D6/D7)."""
    for arm in (Arm.A0, Arm.A1, Arm.A2):
        checkpoint = _checkpoint(arm, tmp_path)
        sink = EvaluationSink(tmp_path / f"{arm.value}.jsonl")
        records = run_heldout_evaluation(
            checkpoint,
            _heldout_set(2),
            _provenance(checkpoint),
            attempt=_attempt(),
            sink=sink,
            guard=CostGuard(0, 1, 0),
        )
        assert len(records) == 2
        assert all(r.arm == arm.value for r in records)


def test_mismatched_provenance_fails_loudly(tmp_path: Path) -> None:
    """A provenance that does not identify this checkpoint/split/arm is refused (§3.5)."""
    checkpoint = _checkpoint(Arm.A1, tmp_path)
    sink = EvaluationSink(tmp_path / "heldout.jsonl")

    wrong_checkpoint = EvaluationProvenance(
        checkpoint_identity="not-this-checkpoint",
        manifest_hash=_MANIFEST_HASH,
        arm=Arm.A1.value,
        base_model="qwen2.5-coder",
        eval_seed=0,
        max_tasks=0,
        max_attempts_per_task=1,
        max_tokens=0,
    )
    with pytest.raises(EvaluationError):
        run_heldout_evaluation(
            checkpoint,
            _heldout_set(1),
            wrong_checkpoint,
            attempt=_attempt(),
            sink=sink,
            guard=CostGuard(0, 1, 0),
        )
    assert sink.read_all() == ()  # refused before any write
