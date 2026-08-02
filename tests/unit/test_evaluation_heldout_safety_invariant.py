"""The permanent held-out-safety and identical-harness invariant (M8-C9).

M8_SPEC §3.5 states the invariant M8 must never violate: evaluation is read-only against
memory and the experience log, writes only to the segregated sink, admits no held-out
episode into any arm's memory, uses the identical harness across A0/A1/A2, holds retrieval
stateless, and computes no statistic and reaches no decision. A violation is an **invalid
measurement** and must **fail loudly**.

This module is that permanent check. It pins the invariant several ways:

* **Structurally** — no ``evaluation`` module imports the frozen ``GuardedEpisodeWriter``
  or the held-out lock, so a record can never reach the experience path; and no
  ``evaluation`` module defines a statistic/aggregate/decision.
* **Behaviourally** — over an empty checkpoint the attempt outcome is identical across
  A0/A1/A2 except the arm label (memory is the sole difference); retrieval holds no
  cross-attempt state; and an invalid measurement (mis-routed held-out write, or a
  provenance that does not match the checkpoint/split) fails loudly.
* **Non-vacuously** — the frozen guarded boundary is shown to still fail-close on a
  held-out identity, so the safety net is real.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

import velith.evaluation
from velith.agent.proposer import Proposal
from velith.arms.identity import Arm
from velith.batch.budget import CostGuard
from velith.corpus.heldout import GuardedEpisodeWriter, HeldOutError, HeldOutLock
from velith.corpus.loader import CorpusTask
from velith.corpus.manifest import CorpusManifest, Partition, PartitionEntry, task_identity
from velith.episodes.episode import Episode, VerdictState
from velith.episodes.store import EpisodeStore
from velith.evaluation.attempt import HeldOutAttempt
from velith.evaluation.checkpoint import form_checkpoint
from velith.evaluation.heldout_set import HeldOutEvaluationSet
from velith.evaluation.provenance import EvaluationProvenance
from velith.evaluation.runner import EvaluationError, run_heldout_evaluation
from velith.evaluation.sink import EvaluationSink
from velith.harness.verifier_sandbox import Verdict
from velith.retrieval.embedding import EMBEDDER_NAME, get_embedder
from velith.retrieval.memory import EpisodeMemory
from velith.retrieval.retriever import Retriever
from velith.task import Task

#: Tokens that would signal a statistic, aggregate, or decision — forbidden in M8 (D22).
_FORBIDDEN_NAME_TOKENS = (
    "mean",
    "median",
    "average",
    "aggregate",
    "statistic",
    "pvalue",
    "p_value",
    "effect",
    "significan",
    "decision",
    "go_no_go",
    "threshold",
    "ttest",
    "anova",
    "correlation",
    "summarize",
    "tally",
)


# --- structural helpers ------------------------------------------------------------


def _evaluation_modules() -> list[Path]:
    assert velith.evaluation.__file__ is not None
    return sorted(Path(velith.evaluation.__file__).parent.glob("*.py"))


def _imported_names(source: Path) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    return imported


def _defined_names(source: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
    return names


# --- runtime stubs (hermetic) ------------------------------------------------------


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


def _attempt() -> HeldOutAttempt:
    return HeldOutAttempt(
        proposer=StubProposer(),
        verifier=StubVerifier(),
        retriever=Retriever(get_embedder(EMBEDDER_NAME), 5),
        adapter=OneTaskAdapter(),
        eval_seed=0,
    )


def _held_task(material: str = "M-held") -> CorpusTask:
    return CorpusTask(label="h", material=material, handle="H", partition=Partition.HELD_OUT)


# --- structural invariants ---------------------------------------------------------


def test_evaluation_never_imports_the_guarded_boundary() -> None:
    """No record can reach the experience path: the guarded writer is never imported."""
    for module in _evaluation_modules():
        imported = _imported_names(module)
        assert "velith.corpus.heldout" not in imported, module.name
        assert not any("GuardedEpisodeWriter" in name for name in imported), module.name


def test_evaluation_defines_no_statistic_or_decision() -> None:
    """No evaluation module defines a statistic, aggregate, or decision (D22)."""
    for module in _evaluation_modules():
        for name in _defined_names(module):
            lowered = name.lower()
            assert not any(
                token in lowered for token in _FORBIDDEN_NAME_TOKENS
            ), f"{module.name} defines {name!r}, which looks like a statistic/decision"


def test_retrieval_holds_no_cross_attempt_cache() -> None:
    """The shared retriever exposes no cache state (retrieval is stateless)."""
    retriever = Retriever(get_embedder(EMBEDDER_NAME), 5)
    assert not any("cache" in attr.lower() for attr in vars(retriever))


# --- behavioural invariants --------------------------------------------------------


def test_identical_harness_memory_is_the_sole_difference(tmp_path: Path) -> None:
    """Over an empty checkpoint, A0/A1/A2 outcomes match except the arm label (§3.3)."""
    empty = EpisodeMemory(tmp_path / "none.jsonl")
    task = _held_task()
    harness = _attempt()

    outcomes = {
        arm: harness.attempt(form_checkpoint(arm, empty), task) for arm in (Arm.A0, Arm.A1, Arm.A2)
    }
    # Normalise the arm field; everything else (seed, verdict, tokens, model) is identical.
    normalised = {dataclasses.replace(o, arm=Arm.A0) for o in outcomes.values()}
    assert len(normalised) == 1
    assert {o.arm for o in outcomes.values()} == {Arm.A0, Arm.A1, Arm.A2}


def test_retrieval_is_stateless_under_interleaving(tmp_path: Path) -> None:
    """Interleaved attempts never influence one another (§3.3, D16.1)."""
    checkpoint = form_checkpoint(Arm.A1, EpisodeMemory(tmp_path / "none.jsonl"))
    harness = _attempt()
    task_a, task_b = _held_task("M-a"), _held_task("M-b")

    first = harness.attempt(checkpoint, task_a)
    harness.attempt(checkpoint, task_b)
    again = harness.attempt(checkpoint, task_a)
    assert first == again


def test_guarded_boundary_still_failcloses_on_heldout(tmp_path: Path) -> None:
    """Non-vacuity: the frozen boundary still refuses a held-out identity (D8)."""
    manifest = CorpusManifest.from_entries(
        [PartitionEntry(label="held", material="M-held", partition=Partition.HELD_OUT)]
    )
    writer = GuardedEpisodeWriter(HeldOutLock(manifest), EpisodeStore(tmp_path / "episodes.jsonl"))
    episode = Episode.build(
        task_id="t",
        seed=0,
        model="m",
        model_version="v",
        prompt="p",
        patch="d",
        verdict_state=VerdictState.PASSED,
        verdict_output="o",
        prompt_tokens=1,
        completion_tokens=2,
        latency_seconds=1.0,
        verify_seconds=2.0,
        velith_version="0.0.0",
        secondary_passed=True,
        flaky=False,
        timestamp="2026-07-06T00:00:00+00:00",
    )
    with pytest.raises(HeldOutError):
        writer.persist(task_identity("M-held"), episode)


def test_invalid_measurement_fails_loudly(tmp_path: Path) -> None:
    """A provenance that does not match the checkpoint/split is refused before any write."""
    checkpoint = form_checkpoint(Arm.A1, EpisodeMemory(tmp_path / "none.jsonl"))
    heldout = HeldOutEvaluationSet(tasks=(_held_task(),), manifest_hash="manifest-1")
    sink = EvaluationSink(tmp_path / "eval.jsonl")
    wrong = EvaluationProvenance(
        checkpoint_identity="not-this-checkpoint",
        manifest_hash="manifest-1",
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
            heldout,
            wrong,
            attempt=_attempt(),
            sink=sink,
            guard=CostGuard(0, 1, 0),
        )
    assert sink.read_all() == ()  # refused before any write
