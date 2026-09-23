"""End-to-end M10 execution over a synthetic held-out sink (M10-C1).

Synthetic fixtures only — **no real held-out M8 data is read**. Exercises the executor
driving the frozen M9 pipeline from a sealed pre-registration and an `EvaluationSink` to a
persisted `AnalysisResultRecord`, across both branches, both VOID dispositions, the frozen
GeeFailure disposition, write-once persistence, determinism, and sink immutability.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest

from velith.analysis.executor import ExecutionError, run_m10_analysis
from velith.analysis.preregistration import PreRegistration
from velith.analysis.result_record import AnalysisResultRecord
from velith.arms.identity import Arm
from velith.episodes.episode import VerdictState
from velith.evaluation.provenance import EvaluationProvenance
from velith.evaluation.record import EvaluationRecord
from velith.evaluation.sink import EvaluationSink

PassedRule = Callable[[int, str, int | None], bool]

_MEMORY_ARMS = (Arm.A1.value, Arm.A2.value)
_KGT1_TASKS = 24


def _hex(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


_A0_CHECKPOINT = _hex("a0-empty-checkpoint")


def _prereg(checkpoint_count: int, *, manifest: str = "manifest") -> PreRegistration:
    return PreRegistration.build(
        manifest_hash=_hex(manifest),
        checkpoint_identities=tuple(_hex(f"cp{i}") for i in range(1, checkpoint_count + 1)),
        base_model="synthetic-base",
        eval_seed=7,
        max_tasks=64,
        max_attempts_per_task=1,
        max_tokens=2048,
    )


def _record(
    prereg: PreRegistration, *, checkpoint: str, arm: str, task: str, passed: bool
) -> EvaluationRecord:
    identity = EvaluationProvenance(
        checkpoint_identity=checkpoint,
        manifest_hash=prereg.manifest_hash,
        arm=arm,
        base_model=prereg.base_model,
        eval_seed=prereg.eval_seed,
        max_tasks=prereg.max_tasks,
        max_attempts_per_task=prereg.max_attempts_per_task,
        max_tokens=prereg.max_tokens,
    ).identity
    return EvaluationRecord(
        evaluation_identity=identity,
        arm=arm,
        task_identity=task,
        seed=prereg.eval_seed,
        verdict_state=VerdictState.PASSED if passed else VerdictState.FAILED,
        prompt_tokens=10,
        completion_tokens=20,
        model="synthetic-model",
        model_version="1",
    )


def _tasks(count: int) -> tuple[str, ...]:
    return tuple(_hex(f"task-{index}") for index in range(count))


def _records(
    prereg: PreRegistration, tasks: tuple[str, ...], rule: PassedRule
) -> list[EvaluationRecord]:
    records: list[EvaluationRecord] = []
    for index, task in enumerate(tasks):
        records.append(
            _record(
                prereg,
                checkpoint=_A0_CHECKPOINT,
                arm=Arm.A0.value,
                task=task,
                passed=rule(index, Arm.A0.value, None),
            )
        )
        for position, checkpoint in enumerate(prereg.checkpoint_identities, start=1):
            for arm in _MEMORY_ARMS:
                records.append(
                    _record(
                        prereg,
                        checkpoint=checkpoint,
                        arm=arm,
                        task=task,
                        passed=rule(index, arm, position),
                    )
                )
    return records


def _k1_go_rule(task_index: int, arm: str, checkpoint_index: int | None) -> bool:
    """16 tasks: A0 never passes, A1 passes 0-7, A2 passes 0-14 -> Holm rejects both."""
    if arm == Arm.A0.value:
        return False
    if arm == Arm.A1.value:
        return task_index < 8
    return task_index < 15


def _kgt1_rule(task_index: int, arm: str, checkpoint_index: int | None) -> bool:
    """Deterministic, checkpoint-varying verdicts — the design C8's GEE tests fit."""
    if arm == Arm.A0.value:
        return task_index % 4 == 0
    position = 0 if checkpoint_index is None else checkpoint_index
    if arm == Arm.A1.value:
        return (task_index + position) % 3 != 0
    return (task_index + 2 * position) % 5 != 0


def _sink(root: Path, records: list[EvaluationRecord]) -> EvaluationSink:
    sink = EvaluationSink(root / "sink" / "evaluations.jsonl")
    for record in records:
        sink.append(record)
    return sink


def _run(
    root: Path,
    *,
    checkpoint_count: int,
    rule: PassedRule,
    task_count: int,
    manifest: str = "manifest",
    run_complete: bool = True,
    drop_a2: bool = False,
    results_name: str = "results",
) -> AnalysisResultRecord:
    prereg = _prereg(checkpoint_count, manifest=manifest)
    tasks = _tasks(task_count)
    records = _records(prereg, tasks, rule)
    if drop_a2:
        records = [r for r in records if r.arm != Arm.A2.value]
    return run_m10_analysis(
        preregistration=prereg,
        evaluation_sink=_sink(root, records),
        results_dir=root / results_name,
        a0_checkpoint_identity=_A0_CHECKPOINT,
        task_identities=tasks,
        evaluation_run_complete=run_complete,
    )


# ---------------------------------------------------------------------------
# Complete paths
# ---------------------------------------------------------------------------


def test_k1_complete_execution_persists_a_go_record(tmp_path: Path) -> None:
    record = _run(tmp_path, checkpoint_count=1, rule=_k1_go_rule, task_count=16)
    assert record.outcome == "GO"
    assert record.family_size == 2
    assert len(record.hypotheses) == 2
    assert record.n_included_tasks == 16
    assert record.completeness_status == "COMPLETE"
    assert record.verify_identity()
    # K=1 fits no GEE, so no statistical library is recorded.
    assert record.provenance.statistical_library is None
    assert (tmp_path / "results" / f"{record.identity}.json").exists()


def test_kgt1_complete_execution_persists_a_four_test_record(tmp_path: Path) -> None:
    record = _run(tmp_path, checkpoint_count=3, rule=_kgt1_rule, task_count=_KGT1_TASKS)
    assert record.outcome in ("GO", "NO_GO")
    assert record.family_size == 4
    assert len(record.hypotheses) == 4
    assert record.n_included_tasks == _KGT1_TASKS
    assert record.provenance.statistical_library == "statsmodels"
    assert record.provenance.statistical_library_version == "0.15.0"
    assert record.provenance.checkpoint_values == (-1.0, 0.0, 1.0)
    assert record.verify_identity()
    assert (tmp_path / "results" / f"{record.identity}.json").exists()


# ---------------------------------------------------------------------------
# VOID dispositions
# ---------------------------------------------------------------------------


def test_global_incomplete_execution_persists_a_void_record(tmp_path: Path) -> None:
    record = _run(tmp_path, checkpoint_count=1, rule=_k1_go_rule, task_count=8, run_complete=False)
    assert record.outcome == "VOID"
    assert record.completeness_status == "VOID_GLOBAL_INCOMPLETE"
    assert record.hypotheses == ()
    assert record.family_size == 0
    assert record.n_included_tasks == 0
    assert record.verify_identity()
    assert (tmp_path / "results" / f"{record.identity}.json").exists()


def test_n_zero_execution_persists_a_void_record_not_a_no_go(tmp_path: Path) -> None:
    record = _run(tmp_path, checkpoint_count=1, rule=_k1_go_rule, task_count=6, drop_a2=True)
    assert record.outcome == "VOID"
    assert record.outcome != "NO_GO"
    assert record.completeness_status == "VOID_EMPTY"
    assert record.hypotheses == ()
    assert record.family_size == 0
    assert record.verify_identity()


def test_kgt1_void_routes_through_the_kgt1_decision(tmp_path: Path) -> None:
    record = _run(tmp_path, checkpoint_count=3, rule=_kgt1_rule, task_count=6, run_complete=False)
    assert record.outcome == "VOID"
    assert record.hypotheses == ()
    assert record.provenance.statistical_library is None


# ---------------------------------------------------------------------------
# GeeFailure disposition
# ---------------------------------------------------------------------------


def test_gee_failure_execution_yields_the_frozen_no_go(tmp_path: Path) -> None:
    # One task gives the robust sandwich a single group, so V_robust is rank-deficient by
    # construction -> frozen 3.5.7 -> both models contribute p = 1.0 -> NO-GO.
    record = _run(tmp_path, checkpoint_count=3, rule=_kgt1_rule, task_count=1)
    assert record.outcome == "NO_GO"
    assert record.family_size == 4
    assert tuple(h.p_value for h in record.hypotheses) == (1.0, 1.0, 1.0, 1.0)
    assert not any(h.rejected for h in record.hypotheses)
    assert record.verify_identity()


# ---------------------------------------------------------------------------
# Persistence, determinism, identity sensitivity
# ---------------------------------------------------------------------------


def test_second_execution_into_the_same_directory_is_refused(tmp_path: Path) -> None:
    prereg = _prereg(1)
    tasks = _tasks(16)
    records = _records(prereg, tasks, _k1_go_rule)
    results_dir = tmp_path / "results"

    def run(sink_root: Path) -> AnalysisResultRecord:
        # A fresh sink root each time: re-appending to one sink would duplicate every
        # record and fail in the binder long before the write-once check is reached.
        return run_m10_analysis(
            preregistration=prereg,
            evaluation_sink=_sink(sink_root, records),
            results_dir=results_dir,
            a0_checkpoint_identity=_A0_CHECKPOINT,
            task_identities=tasks,
            evaluation_run_complete=True,
        )

    first = run(tmp_path / "one")
    with pytest.raises(FileExistsError):
        run(tmp_path / "two")
    assert [p.name for p in results_dir.iterdir()] == [f"{first.identity}.json"]


def test_identical_inputs_yield_an_identical_result_identity(tmp_path: Path) -> None:
    first = _run(tmp_path / "a", checkpoint_count=1, rule=_k1_go_rule, task_count=16)
    second = _run(tmp_path / "b", checkpoint_count=1, rule=_k1_go_rule, task_count=16)
    assert first.identity == second.identity
    assert first.to_dict() == second.to_dict()


def test_kgt1_execution_is_deterministic(tmp_path: Path) -> None:
    first = _run(tmp_path / "a", checkpoint_count=3, rule=_kgt1_rule, task_count=_KGT1_TASKS)
    second = _run(tmp_path / "b", checkpoint_count=3, rule=_kgt1_rule, task_count=_KGT1_TASKS)
    assert first.identity == second.identity
    assert first.to_dict() == second.to_dict()


def test_a_changed_analytical_input_changes_the_identity(tmp_path: Path) -> None:
    baseline = _run(tmp_path / "a", checkpoint_count=1, rule=_k1_go_rule, task_count=16)
    fewer = _run(tmp_path / "b", checkpoint_count=1, rule=_k1_go_rule, task_count=12)
    assert fewer.identity != baseline.identity
    other_manifest = _run(
        tmp_path / "c",
        checkpoint_count=1,
        rule=_k1_go_rule,
        task_count=16,
        manifest="other-manifest",
    )
    assert other_manifest.identity != baseline.identity


def test_execution_leaves_the_evaluation_sink_untouched(tmp_path: Path) -> None:
    prereg = _prereg(1)
    tasks = _tasks(16)
    sink = _sink(tmp_path, _records(prereg, tasks, _k1_go_rule))
    before = sink.path.read_bytes()

    record = run_m10_analysis(
        preregistration=prereg,
        evaluation_sink=sink,
        results_dir=tmp_path / "results",
        a0_checkpoint_identity=_A0_CHECKPOINT,
        task_identities=tasks,
        evaluation_run_complete=True,
    )

    assert sink.path.read_bytes() == before
    assert record.verify_identity()
    # The only artifact written is the single terminal result record.
    assert [p.name for p in (tmp_path / "results").iterdir()] == [f"{record.identity}.json"]


def test_a_structural_error_writes_no_result(tmp_path: Path) -> None:
    prereg = _prereg(1)
    tasks = _tasks(8)
    foreign = _records(_prereg(1, manifest="other"), tasks, _k1_go_rule)
    with pytest.raises(ExecutionError):
        run_m10_analysis(
            preregistration=prereg,
            evaluation_sink=_sink(tmp_path, foreign),
            results_dir=tmp_path / "results",
            a0_checkpoint_identity=_A0_CHECKPOINT,
            task_identities=tasks,
            evaluation_run_complete=True,
        )
    assert not (tmp_path / "results").exists()
