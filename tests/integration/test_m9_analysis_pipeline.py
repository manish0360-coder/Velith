"""End-to-end composition and determinism for the M9 analysis pipeline (M9-C13).

Synthetic fixtures only — no held-out outcome, no real M8 evaluation, no memory or
experience write, no repository state mutated. Persistence is exercised only through the
frozen C12 API against ``tmp_path``.

This module introduces **no statistic**. It wires the already-frozen executors together
through their real public APIs and asserts the *composition*:

    PreRegistration -> records -> binder -> completeness
        -> K=1: McNemar x2 -> Holm(2) -> decide_k1
        -> K>1: GEE x2 -> EMM/Wald + trend -> Holm(4) -> decide_kgt1
        -> AnalysisResultRecord

The K=1 fixtures are small and one-directional, so their exact McNemar p-values follow from
the frozen procedure and are asserted exactly. The K>1 fixtures assert structure, branch,
provenance and determinism — never an invented numeric outcome.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest

from velith.analysis.binder import Observation, bind_observations
from velith.analysis.completeness import (
    CompletenessResult,
    CompletenessStatus,
    ObservedCell,
    assess_completeness,
)
from velith.analysis.decision import (
    KGT1_HYPOTHESIS_LABELS,
    ComparisonPValues,
    DecisionOutcome,
    DecisionResult,
    build_kgt1_family,
    comparison_label,
    decide_k1,
    decide_kgt1,
)
from velith.analysis.emm import compute_emm
from velith.analysis.gee import Comparison, GeeFailure, GeeFit, SolverProvenance, fit_gee
from velith.analysis.holm import HolmError, HolmResult, LabeledPValue, holm_bonferroni
from velith.analysis.mcnemar import mcnemar_test
from velith.analysis.preregistration import PreRegistration
from velith.analysis.result_record import (
    AnalysisResultRecord,
    build_result_record,
    serialize_result_record,
    write_result_record,
)
from velith.analysis.trend import compute_trend
from velith.analysis.wald import compute_wald
from velith.arms.identity import Arm
from velith.episodes.episode import VerdictState
from velith.evaluation.provenance import EvaluationProvenance
from velith.evaluation.record import EvaluationRecord

#: ``(task_index, arm, checkpoint_index) -> passed``. ``checkpoint_index`` is ``None`` for
#: A0's single time-invariant observation (OED-2).
PassedRule = Callable[[int, str, int | None], bool]

_MEMORY_ARMS = (Arm.A1.value, Arm.A2.value)


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


def _evaluation_identity(prereg: PreRegistration, checkpoint_identity: str, arm: str) -> str:
    """The sanctioned join key — the same construction the binder reconstructs."""
    return EvaluationProvenance(
        checkpoint_identity=checkpoint_identity,
        manifest_hash=prereg.manifest_hash,
        arm=arm,
        base_model=prereg.base_model,
        eval_seed=prereg.eval_seed,
        max_tasks=prereg.max_tasks,
        max_attempts_per_task=prereg.max_attempts_per_task,
        max_tokens=prereg.max_tokens,
    ).identity


def _record(
    prereg: PreRegistration, *, checkpoint_identity: str, arm: str, task: str, passed: bool
) -> EvaluationRecord:
    return EvaluationRecord(
        evaluation_identity=_evaluation_identity(prereg, checkpoint_identity, arm),
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
    """Build the full record set for the pre-registered design.

    A0 (OED-2) gets exactly **one** record per task at its own empty-checkpoint identity —
    never replicated across the schedule. A1/A2 get one per ordered checkpoint.
    """
    records: list[EvaluationRecord] = []
    for index, task in enumerate(tasks):
        records.append(
            _record(
                prereg,
                checkpoint_identity=_A0_CHECKPOINT,
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
                        checkpoint_identity=checkpoint,
                        arm=arm,
                        task=task,
                        passed=rule(index, arm, position),
                    )
                )
    return records


def _index_rule(passed: dict[str, set[int]]) -> PassedRule:
    """A checkpoint-invariant rule: an arm passes a task iff its index is listed."""

    def rule(task_index: int, arm: str, checkpoint_index: int | None) -> bool:
        return task_index in passed[arm]

    return rule


def _bind(
    prereg: PreRegistration,
    tasks: tuple[str, ...],
    records: list[EvaluationRecord],
    *,
    run_complete: bool = True,
) -> tuple[tuple[Observation, ...], CompletenessResult]:
    observations = bind_observations(prereg, records, a0_checkpoint_identity=_A0_CHECKPOINT)
    completeness = assess_completeness(
        task_identities=tasks,
        checkpoint_identities=prereg.checkpoint_identities,
        a0_checkpoint_identity=_A0_CHECKPOINT,
        evaluation_run_complete=run_complete,
        observed=[
            ObservedCell(obs.task_identity, obs.arm, obs.checkpoint_identity)
            for obs in observations
        ],
    )
    return observations, completeness


def _included(
    observations: tuple[Observation, ...], completeness: CompletenessResult
) -> list[Observation]:
    included = set(completeness.included_task_identities)
    return [obs for obs in observations if obs.task_identity in included]


# ---------------------------------------------------------------------------
# The two frozen branches, composed from the real executors
# ---------------------------------------------------------------------------


def _k1_holm(observations: list[Observation]) -> tuple[HolmResult, tuple[float, float]]:
    a1_vs_a0 = mcnemar_test(observations, superior_arm=Arm.A1.value, reference_arm=Arm.A0.value)
    a2_vs_a1 = mcnemar_test(observations, superior_arm=Arm.A2.value, reference_arm=Arm.A1.value)
    family = [
        LabeledPValue(comparison_label(Arm.A1.value, Arm.A0.value), a1_vs_a0.p_value),
        LabeledPValue(comparison_label(Arm.A2.value, Arm.A1.value), a2_vs_a1.p_value),
    ]
    return holm_bonferroni(family), (a1_vs_a0.p_value, a2_vs_a1.p_value)


def _fit_comparison(
    observations: list[Observation], comparison: Comparison, checkpoint_count: int
) -> GeeFit | GeeFailure:
    arms = {comparison.reference_arm, comparison.superior_arm}
    subset = [obs for obs in observations if obs.arm in arms]
    return fit_gee(subset, comparison=comparison, checkpoint_count=checkpoint_count)


def _comparison_pvalues(outcome: GeeFit | GeeFailure) -> ComparisonPValues | None:
    """Route one fitted comparison to its two p-values; ``None`` is the frozen 3.5.7 case.

    The GeeFailure disposition belongs to C11; this helper only routes and never classifies.
    """
    if isinstance(outcome, GeeFailure):
        return None
    emm_p = compute_wald(compute_emm(outcome)).p_value
    trend_p = compute_trend(outcome).p_value
    return ComparisonPValues(emm_p, trend_p)


def _kgt1_holm(
    observations: list[Observation], checkpoint_count: int
) -> tuple[HolmResult, SolverProvenance | None, tuple[float, ...]]:
    first = _fit_comparison(observations, Comparison.A1_VS_A0, checkpoint_count)
    second = _fit_comparison(observations, Comparison.A2_VS_A1, checkpoint_count)
    family = build_kgt1_family(
        a1_vs_a0=_comparison_pvalues(first),
        a2_vs_a1=_comparison_pvalues(second),
    )
    fitted: GeeFit | None = None
    for candidate in (first, second):
        if isinstance(candidate, GeeFit):
            fitted = candidate
            break
    provenance = None if fitted is None else fitted.provenance
    checkpoint_values = () if fitted is None else fitted.checkpoint_values
    return holm_bonferroni(family), provenance, checkpoint_values


def _record_for(
    prereg: PreRegistration,
    completeness: CompletenessResult,
    holm: HolmResult | None,
    decision: DecisionResult,
    records: list[EvaluationRecord],
    *,
    solver_provenance: SolverProvenance | None = None,
    checkpoint_values: tuple[float, ...] = (),
) -> AnalysisResultRecord:
    return build_result_record(
        preregistration=prereg,
        completeness=completeness,
        holm_result=holm,
        decision=decision,
        evaluation_records=records,
        solver_provenance=solver_provenance,
        checkpoint_values=checkpoint_values,
    )


# ---------------------------------------------------------------------------
# A. K=1 complete path
# ---------------------------------------------------------------------------

#: 16 tasks: A0 never passes; A1 passes 0-7; A2 passes 0-14. All discordance is
#: one-directional, so the exact McNemar p-values are 1/2^8 and 1/2^7.
_K1_GO: dict[str, set[int]] = {
    Arm.A0.value: set(),
    Arm.A1.value: set(range(8)),
    Arm.A2.value: set(range(15)),
}

#: 8 tasks giving one-directional discordance of 4 and 2 -> p = 1/16 and 1/4.
_K1_NO_GO: dict[str, set[int]] = {
    Arm.A0.value: {0, 1},
    Arm.A1.value: set(range(6)),
    Arm.A2.value: set(range(8)),
}


def _run_k1(
    passed: dict[str, set[int]], task_count: int = 16, *, manifest: str = "manifest"
) -> tuple[DecisionResult, AnalysisResultRecord, tuple[float, float]]:
    prereg = _prereg(1, manifest=manifest)
    tasks = _tasks(task_count)
    records = _records(prereg, tasks, _index_rule(passed))
    observations, completeness = _bind(prereg, tasks, records)
    holm, pvalues = _k1_holm(_included(observations, completeness))
    decision = decide_k1(completeness_status=completeness.status, holm_result=holm)
    record = _record_for(prereg, completeness, holm, decision, records)
    return decision, record, pvalues


def test_k1_complete_path_reaches_go_with_exact_mcnemar_p_values() -> None:
    decision, record, (p_a1a0, p_a2a1) = _run_k1(_K1_GO)

    # Exact one-sided McNemar: one-directional discordance of 8 and 7 (spec 3.5.5).
    assert p_a1a0 == 1 / 2**8
    assert p_a2a1 == 1 / 2**7

    assert decision.outcome is DecisionOutcome.GO
    assert record.outcome == "GO"
    assert record.family_size == 2
    assert len(record.hypotheses) == 2
    assert record.n_included_tasks == 16
    assert record.completeness_status == "COMPLETE"
    assert record.verify_identity()
    # K=1 fits no GEE, so no statistical library or centred grid is recorded.
    assert record.provenance.statistical_library is None
    assert record.provenance.checkpoint_values == ()


def test_k1_complete_path_reaches_no_go_when_holm_does_not_reject() -> None:
    decision, record, (p_a1a0, p_a2a1) = _run_k1(_K1_NO_GO, task_count=8)
    assert p_a1a0 == 1 / 2**4
    assert p_a2a1 == 1 / 2**2
    assert decision.outcome is DecisionOutcome.NO_GO
    assert record.outcome == "NO_GO"
    assert record.verify_identity()


def test_k1_a0_is_not_replicated_across_the_schedule() -> None:
    prereg = _prereg(1)
    tasks = _tasks(4)
    observations, _ = _bind(prereg, tasks, _records(prereg, tasks, _index_rule(_K1_GO)))
    a0 = [obs for obs in observations if obs.arm == Arm.A0.value]
    assert len(a0) == len(tasks)
    assert {obs.checkpoint_index for obs in a0} == {None}
    assert {obs.checkpoint_identity for obs in a0} == {_A0_CHECKPOINT}


# ---------------------------------------------------------------------------
# B. K>1 complete path
# ---------------------------------------------------------------------------


def _kgt1_rule(task_index: int, arm: str, checkpoint_index: int | None) -> bool:
    """Deterministic, checkpoint-varying synthetic verdicts (no randomness, no seed)."""
    if arm == Arm.A0.value:
        return task_index % 4 == 0
    position = 0 if checkpoint_index is None else checkpoint_index
    if arm == Arm.A1.value:
        return (task_index + position) % 3 != 0
    return (task_index + 2 * position) % 5 != 0


#: The task count C8's in-container-verified GEE fixtures use with this same rule at K=3.
#: A smaller design does not fit, and then no GeeFit exists to record provenance from.
_KGT1_TASKS = 24


def _run_kgt1(
    *, task_count: int = _KGT1_TASKS, checkpoint_count: int = 3, manifest: str = "manifest"
) -> tuple[DecisionResult, AnalysisResultRecord, HolmResult]:
    prereg = _prereg(checkpoint_count, manifest=manifest)
    tasks = _tasks(task_count)
    records = _records(prereg, tasks, _kgt1_rule)
    observations, completeness = _bind(prereg, tasks, records)
    holm, provenance, checkpoint_values = _kgt1_holm(
        _included(observations, completeness), checkpoint_count
    )
    decision = decide_kgt1(completeness_status=completeness.status, holm_result=holm)
    record = _record_for(
        prereg,
        completeness,
        holm,
        decision,
        records,
        solver_provenance=provenance,
        checkpoint_values=checkpoint_values,
    )
    return decision, record, holm


def test_kgt1_complete_path_composes_the_four_test_family() -> None:
    decision, record, holm = _run_kgt1()

    assert holm.family_size == 4
    assert holm.alpha == 0.01
    assert {d.label for d in holm.decisions} == set(KGT1_HYPOTHESIS_LABELS)
    # The frozen Holm ladder for m = 4.
    assert tuple(d.threshold for d in holm.decisions) == (
        0.01 / 4,
        0.01 / 3,
        0.01 / 2,
        0.01 / 1,
    )
    # A frozen synthetic fixture decides its own outcome; only the branch is asserted.
    assert decision.outcome in (DecisionOutcome.GO, DecisionOutcome.NO_GO)
    assert record.outcome == decision.outcome.value
    assert record.family_size == 4
    assert record.n_included_tasks == _KGT1_TASKS
    assert record.verify_identity()


def test_kgt1_records_the_gee_solver_provenance() -> None:
    # Provenance can only come from a GeeFit, so assert the fixture actually fits first:
    # a failure here points at the design, not at the C12 provenance contract.
    prereg = _prereg(3)
    tasks = _tasks(_KGT1_TASKS)
    observations, completeness = _bind(prereg, tasks, _records(prereg, tasks, _kgt1_rule))
    included = _included(observations, completeness)
    assert isinstance(_fit_comparison(included, Comparison.A1_VS_A0, 3), GeeFit)
    assert isinstance(_fit_comparison(included, Comparison.A2_VS_A1, 3), GeeFit)

    _, record, _ = _run_kgt1()
    provenance = record.provenance
    assert provenance.statistical_library == "statsmodels"
    assert provenance.statistical_library_version is not None
    assert dict(provenance.solver_configuration)["cov_type"] == "robust"
    assert dict(provenance.solver_configuration)["maxiter"] == "100"
    # x_k = k - (K+1)/2 for K = 3.
    assert provenance.checkpoint_values == (-1.0, 0.0, 1.0)


def test_kgt1_a0_enters_once_per_task_while_a1_spans_the_schedule() -> None:
    prereg = _prereg(3)
    tasks = _tasks(6)
    observations, _ = _bind(prereg, tasks, _records(prereg, tasks, _kgt1_rule))
    a0 = [obs for obs in observations if obs.arm == Arm.A0.value]
    a1 = [obs for obs in observations if obs.arm == Arm.A1.value]
    # OED-2: one A0 observation per task, three A1 observations per task.
    assert len(a0) == 6
    assert len(a1) == 18
    assert {obs.checkpoint_index for obs in a0} == {None}
    assert {obs.checkpoint_index for obs in a1} == {1, 2, 3}


# ---------------------------------------------------------------------------
# C/D. VOID dispositions
# ---------------------------------------------------------------------------


def _run_void_global_incomplete() -> tuple[DecisionResult, AnalysisResultRecord]:
    prereg = _prereg(1)
    tasks = _tasks(8)
    records = _records(prereg, tasks, _index_rule(_K1_GO))
    _, completeness = _bind(prereg, tasks, records, run_complete=False)
    decision = decide_k1(completeness_status=completeness.status)
    return decision, _record_for(prereg, completeness, None, decision, records)


def _run_void_empty() -> tuple[tuple[str, ...], DecisionResult, AnalysisResultRecord]:
    prereg = _prereg(1)
    tasks = _tasks(6)
    records = _records(prereg, tasks, _index_rule(_K1_GO))
    # Drop every A2 record: each task is missing a cell, so all are excluded -> n = 0.
    surviving = [r for r in records if r.arm != Arm.A2.value]
    _, completeness = _bind(prereg, tasks, surviving)
    decision = decide_k1(completeness_status=completeness.status)
    record = _record_for(prereg, completeness, None, decision, surviving)
    return tasks, decision, record


def test_global_incomplete_run_is_void_and_records_without_a_holm_family() -> None:
    prereg = _prereg(1)
    tasks = _tasks(8)
    records = _records(prereg, tasks, _index_rule(_K1_GO))
    _, completeness = _bind(prereg, tasks, records, run_complete=False)

    assert completeness.status is CompletenessStatus.VOID_GLOBAL_INCOMPLETE
    assert completeness.n == 0
    # VOID short-circuits: the decision is reached with no Holm family at all.
    decision = decide_k1(completeness_status=completeness.status)
    assert decision.outcome is DecisionOutcome.VOID
    assert decision.rejected_labels == frozenset()
    assert decide_kgt1(completeness_status=completeness.status).outcome is DecisionOutcome.VOID

    _, record = _run_void_global_incomplete()
    assert record.outcome == "VOID"
    assert record.hypotheses == ()
    assert record.family_size == 0
    assert record.completeness_status == "VOID_GLOBAL_INCOMPLETE"
    assert record.verify_identity()


def test_n_zero_after_complete_case_exclusion_is_void_not_no_go() -> None:
    tasks, decision, record = _run_void_empty()

    assert decision.outcome is DecisionOutcome.VOID
    # n=0 is a procedural halt, never an inferential NO-GO (OED-7 / 3.5.11). Compared on
    # the enum value so mypy does not flag a trivially-true non-overlapping identity check.
    assert decision.outcome.value not in {DecisionOutcome.GO.value, DecisionOutcome.NO_GO.value}
    assert record.outcome == "VOID"
    assert record.completeness_status == "VOID_EMPTY"
    assert record.n_included_tasks == 0
    assert record.included_task_identities == ()
    assert record.excluded_task_identities == tuple(sorted(tasks))
    assert record.verify_identity()


def test_void_record_fabricates_no_statistics() -> None:
    _, _, record = _run_void_empty()
    assert record.hypotheses == ()
    assert record.family_size == 0
    # to_dict() preserves the frozen tuple representation; canonical JSON renders it as
    # an empty array. Neither carries a p-value or a per-test threshold.
    assert record.to_dict()["hypotheses"] == ()
    assert '"hypotheses":[]' in serialize_result_record(record)
    assert '"p_value"' not in serialize_result_record(record)
    assert '"threshold"' not in serialize_result_record(record)
    # A VOID run computes no test, so C6 refuses the empty family — which is exactly why
    # the record carries no Holm family rather than a fabricated one.
    with pytest.raises(HolmError):
        holm_bonferroni([])


def test_void_record_identity_is_deterministic_end_to_end() -> None:
    _, first_decision, first_record = _run_void_empty()
    _, second_decision, second_record = _run_void_empty()
    assert first_decision == second_decision
    assert first_record.identity == second_record.identity
    assert first_record.to_dict() == second_record.to_dict()


def test_the_two_void_dispositions_have_distinct_identities() -> None:
    _, incomplete = _run_void_global_incomplete()
    _, _, empty = _run_void_empty()
    assert incomplete.completeness_status != empty.completeness_status
    assert incomplete.identity != empty.identity


def test_void_record_persists_with_write_once_semantics(tmp_path: Path) -> None:
    _, _, record = _run_void_empty()
    target = write_result_record(record, tmp_path)
    assert target == tmp_path / f"{record.identity}.json"
    assert list(tmp_path.iterdir()) == [target]
    with pytest.raises(FileExistsError):
        write_result_record(record, tmp_path)


# ---------------------------------------------------------------------------
# E. GeeFailure disposition
# ---------------------------------------------------------------------------


def test_gee_failure_contributes_p_one_and_yields_no_go() -> None:
    # A single task gives the robust sandwich a single group, so its meat matrix is one
    # outer product and V_robust is rank-deficient by construction -> frozen 3.5.7.
    prereg = _prereg(3)
    tasks = _tasks(1)
    records = _records(prereg, tasks, _kgt1_rule)
    observations, completeness = _bind(prereg, tasks, records)
    assert completeness.status is CompletenessStatus.COMPLETE
    assert completeness.n == 1

    included = _included(observations, completeness)
    first = _fit_comparison(included, Comparison.A1_VS_A0, 3)
    second = _fit_comparison(included, Comparison.A2_VS_A1, 3)
    assert isinstance(first, GeeFailure)
    assert isinstance(second, GeeFailure)

    family = build_kgt1_family(
        a1_vs_a0=_comparison_pvalues(first),
        a2_vs_a1=_comparison_pvalues(second),
    )
    # Frozen 3.5.7: a failed model contributes p = 1.0 for both of its hypotheses.
    assert tuple(pv.p_value for pv in family) == (1.0, 1.0, 1.0, 1.0)

    holm = holm_bonferroni(family)
    decision = decide_kgt1(completeness_status=completeness.status, holm_result=holm)
    assert decision.outcome is DecisionOutcome.NO_GO
    assert decision.rejected_labels == frozenset()


# ---------------------------------------------------------------------------
# F. Determinism — the primary C13 requirement
# ---------------------------------------------------------------------------


def test_k1_pipeline_is_deterministic_end_to_end() -> None:
    first_decision, first_record, _ = _run_k1(_K1_GO)
    second_decision, second_record, _ = _run_k1(_K1_GO)
    assert first_decision == second_decision
    assert first_record.identity == second_record.identity
    assert first_record.to_dict() == second_record.to_dict()
    assert first_record == second_record


def test_kgt1_pipeline_is_deterministic_end_to_end() -> None:
    first_decision, first_record, first_holm = _run_kgt1()
    second_decision, second_record, second_holm = _run_kgt1()
    assert first_decision == second_decision
    assert first_holm == second_holm
    assert first_record.identity == second_record.identity
    assert first_record.to_dict() == second_record.to_dict()


# ---------------------------------------------------------------------------
# G. Identity sensitivity — content addressing, not accidental determinism
# ---------------------------------------------------------------------------


def test_a_different_manifest_yields_a_different_result_identity() -> None:
    baseline = _run_k1(_K1_GO)[1]
    other = _run_k1(_K1_GO, manifest="another-manifest")[1]
    assert other.provenance.manifest_hash != baseline.provenance.manifest_hash
    assert other.identity != baseline.identity


def test_a_different_verdict_yields_a_different_result_identity() -> None:
    baseline = _run_k1(_K1_GO)[1]
    altered = dict(_K1_GO)
    altered[Arm.A1.value] = set(range(7))  # one fewer A1 pass changes the McNemar counts
    other = _run_k1(altered)[1]
    assert other.identity != baseline.identity


def test_a_different_outcome_yields_a_different_result_identity() -> None:
    go_record = _run_k1(_K1_GO)[1]
    no_go_record = _run_k1(_K1_NO_GO, task_count=8)[1]
    assert go_record.outcome != no_go_record.outcome
    assert go_record.identity != no_go_record.identity


def test_kgt1_identity_differs_from_the_k1_identity() -> None:
    k1 = _run_k1(_K1_GO)[1]
    kgt1 = _run_kgt1()[1]
    assert k1.family_size != kgt1.family_size
    assert k1.identity != kgt1.identity


# ---------------------------------------------------------------------------
# H. Result-record boundary and side-effect safety
# ---------------------------------------------------------------------------


def test_record_carries_upstream_values_verbatim() -> None:
    prereg = _prereg(1)
    tasks = _tasks(16)
    records = _records(prereg, tasks, _index_rule(_K1_GO))
    observations, completeness = _bind(prereg, tasks, records)
    holm, _ = _k1_holm(_included(observations, completeness))
    decision = decide_k1(completeness_status=completeness.status, holm_result=holm)
    record = _record_for(prereg, completeness, holm, decision, records)

    # C12 records; it does not recompute. Every stored value is its upstream value.
    for stored, upstream in zip(record.hypotheses, holm.decisions, strict=True):
        assert (stored.label, stored.p_value) == (upstream.label, upstream.p_value)
        assert (stored.rank, stored.threshold) == (upstream.rank, upstream.threshold)
        assert stored.rejected is upstream.rejected
    assert record.outcome == decision.outcome.value
    assert record.reason == decision.reason
    assert record.alpha == holm.alpha
    assert record.provenance.preregistration_identity == prereg.identity
    assert record.provenance.checkpoint_identities == prereg.checkpoint_identities
    expected_identities = tuple(sorted({r.evaluation_identity for r in records}))
    assert record.provenance.evaluation_identities == expected_identities


def test_persistence_round_trip_uses_only_the_supplied_directory(tmp_path: Path) -> None:
    record = _run_k1(_K1_GO)[1]
    target = write_result_record(record, tmp_path)
    assert target == tmp_path / f"{record.identity}.json"
    assert list(tmp_path.iterdir()) == [target]
    # Write-once: a second write of the same analysis is refused, never overwritten.
    with pytest.raises(FileExistsError):
        write_result_record(record, tmp_path)


def test_running_the_pipeline_writes_nothing(tmp_path: Path) -> None:
    decision, record, _ = _run_k1(_K1_GO)
    assert decision.outcome is DecisionOutcome.GO
    assert record.verify_identity()
    # The whole analysis performs no write until persistence is explicitly invoked.
    assert list(tmp_path.iterdir()) == []
