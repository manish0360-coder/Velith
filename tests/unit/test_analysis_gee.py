"""Unit tests for the frozen K>1 GEE executor (M9-C8 / P2, spec §3.5.3/§3.5.7, handoff §6-§7).

Deterministic synthetic fixtures only — no held-out outcome is ever a fixture (handoff §10).
Pins the frozen model construction (explicit design matrix, column order, treatment coding,
mean-centering, OED-2 non-replicated A0), the pinned solver configuration, repeated-execution
determinism, the §3.5.7 failure set, the structural-halt boundary, and the module boundary
(no EMM, trend, Holm, or GO/NO-GO logic lives here).
"""

from __future__ import annotations

import ast
import hashlib
import math
from pathlib import Path
from typing import Any

import pytest

from velith.analysis import gee as gee_mod
from velith.analysis.binder import Observation
from velith.analysis.gee import (
    A0_CHECKPOINT_ID_C,
    COV_TYPE,
    CTOL,
    DESIGN_COLUMNS,
    MAXITER,
    Comparison,
    GeeError,
    GeeFailure,
    GeeFailureReason,
    GeeFit,
    build_design,
    centered_checkpoint_values,
    classify_failure,
    fit_gee,
)
from velith.arms.identity import Arm

_A0_CP = hashlib.sha256(b"empty-checkpoint").hexdigest()


def _column(exog: tuple[tuple[float, ...], ...], index: int) -> tuple[float, ...]:
    """One design-matrix column, by position in the frozen column order."""
    return tuple(row[index] for row in exog)


def _task(index: int) -> str:
    return hashlib.sha256(f"task-{index}".encode()).hexdigest()


def _checkpoint(index: int) -> str:
    return hashlib.sha256(f"cp-{index}".encode()).hexdigest()


def _obs(task: str, arm: str, index: int | None, endpoint: int) -> Observation:
    return Observation(
        task_identity=task,
        arm=arm,
        checkpoint_identity=_A0_CP if index is None else _checkpoint(index),
        checkpoint_index=index,
        endpoint=endpoint,
    )


def _a1_vs_a0(k: int = 3, n_tasks: int = 24) -> list[Observation]:
    """A1-vs-A0 fixture: one A0 row per task (OED-2) plus A1 across the K checkpoints."""
    observations: list[Observation] = []
    for t in range(n_tasks):
        observations.append(_obs(_task(t), Arm.A0.value, None, 1 if t % 4 == 0 else 0))
        for index in range(1, k + 1):
            observations.append(
                _obs(_task(t), Arm.A1.value, index, 0 if (t + index) % 3 == 0 else 1)
            )
    return observations


def _a2_vs_a1(k: int = 3, n_tasks: int = 24) -> list[Observation]:
    """A2-vs-A1 fixture: both arms are time-varying, one row per ordered checkpoint."""
    observations: list[Observation] = []
    for t in range(n_tasks):
        for index in range(1, k + 1):
            observations.append(
                _obs(_task(t), Arm.A1.value, index, 0 if (t + index) % 3 == 0 else 1)
            )
            observations.append(
                _obs(_task(t), Arm.A2.value, index, 0 if (t + 2 * index) % 5 == 0 else 1)
            )
    return observations


# ---------------------------------------------------------------------------
# K>1 boundary and the frozen mean-centred covariate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("checkpoint_count", [0, 1])
def test_k1_and_below_are_rejected(checkpoint_count: int) -> None:
    # K=1 routes to the frozen exact McNemar path (§3.5.5); GEE must never accept it.
    with pytest.raises(GeeError):
        build_design(
            _a1_vs_a0(k=1), comparison=Comparison.A1_VS_A0, checkpoint_count=checkpoint_count
        )
    with pytest.raises(GeeError):
        fit_gee(_a1_vs_a0(k=1), comparison=Comparison.A1_VS_A0, checkpoint_count=checkpoint_count)


@pytest.mark.parametrize(
    ("k", "expected"),
    [
        (2, (-0.5, 0.5)),
        (3, (-1.0, 0.0, 1.0)),
        (4, (-1.5, -0.5, 0.5, 1.5)),
        (5, (-2.0, -1.0, 0.0, 1.0, 2.0)),
    ],
)
def test_checkpoint_index_is_mean_centered(k: int, expected: tuple[float, ...]) -> None:
    values = centered_checkpoint_values(k)
    assert values == expected
    assert sum(values) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Explicit design matrix (handoff OED-4): column order, coding, OED-2 A0
# ---------------------------------------------------------------------------


def test_a1_vs_a0_design_is_additive_with_frozen_column_order() -> None:
    design = build_design(_a1_vs_a0(), comparison=Comparison.A1_VS_A0, checkpoint_count=3)
    assert design.columns == ("intercept", "checkpoint_id_c", "arm")
    assert design.columns == DESIGN_COLUMNS[Comparison.A1_VS_A0]
    assert all(len(row) == 3 for row in design.exog)  # no interaction column in the additive model
    assert set(_column(design.exog, 0)) == {1.0}


def test_a2_vs_a1_design_carries_the_interaction_column() -> None:
    design = build_design(_a2_vs_a1(), comparison=Comparison.A2_VS_A1, checkpoint_count=3)
    assert design.columns == ("intercept", "checkpoint_id_c", "arm", "checkpoint_id_c:arm")
    assert design.columns == DESIGN_COLUMNS[Comparison.A2_VS_A1]
    assert all(len(row) == 4 for row in design.exog)
    # The interaction column is exactly the product of its two parents.
    assert all(row[3] == row[1] * row[2] for row in design.exog)


def test_a0_enters_once_per_task_at_checkpoint_id_c_zero() -> None:
    k, n_tasks = 3, 24
    design = build_design(
        _a1_vs_a0(k=k, n_tasks=n_tasks), comparison=Comparison.A1_VS_A0, checkpoint_count=k
    )
    a0_rows = [row for row in design.exog if row[2] == 0.0]
    a1_rows = [row for row in design.exog if row[2] == 1.0]
    # OED-2: exactly ONE A0 row per task -- never replicated across the K checkpoints.
    assert len(a0_rows) == n_tasks
    assert len(a1_rows) == n_tasks * k
    assert len(design.exog) == n_tasks * (k + 1)
    assert {row[1] for row in a0_rows} == {A0_CHECKPOINT_ID_C}
    assert A0_CHECKPOINT_ID_C == 0.0


def test_a1_covariate_values_are_the_centered_schedule() -> None:
    design = build_design(_a1_vs_a0(), comparison=Comparison.A1_VS_A0, checkpoint_count=3)
    a1_values = {row[1] for row in design.exog if row[2] == 1.0}
    assert sorted(a1_values) == [-1.0, 0.0, 1.0]
    assert design.checkpoint_values == centered_checkpoint_values(3)


def test_treatment_coding_is_frozen_for_both_comparisons() -> None:
    assert Comparison.A1_VS_A0.reference_arm == Arm.A0.value
    assert Comparison.A1_VS_A0.superior_arm == Arm.A1.value
    assert Comparison.A2_VS_A1.reference_arm == Arm.A1.value
    assert Comparison.A2_VS_A1.superior_arm == Arm.A2.value

    ordered = sorted(
        _a2_vs_a1(n_tasks=2),
        key=lambda o: (o.task_identity, o.arm, o.checkpoint_index or -1),
    )
    design = build_design(ordered, comparison=Comparison.A2_VS_A1, checkpoint_count=3)
    arm_column = _column(design.exog, 2)
    assert set(arm_column) == {0.0, 1.0}
    for observation, coded in zip(ordered, arm_column, strict=True):
        assert coded == (1.0 if observation.arm == Arm.A2.value else 0.0)


def test_groups_are_contiguous_codes_in_sorted_task_order() -> None:
    design = build_design(_a1_vs_a0(n_tasks=5), comparison=Comparison.A1_VS_A0, checkpoint_count=3)
    assert design.task_identities == tuple(sorted(design.task_identities))
    assert sorted(set(design.groups)) == list(range(5))
    assert all(isinstance(code, int) for code in design.groups)


# ---------------------------------------------------------------------------
# Fit: family/link/covariance, solver pins, determinism
# ---------------------------------------------------------------------------


def test_a1_vs_a0_fit_succeeds_with_the_frozen_configuration() -> None:
    result = fit_gee(_a1_vs_a0(), comparison=Comparison.A1_VS_A0, checkpoint_count=3)
    assert isinstance(result, GeeFit)
    assert result.converged is True
    assert result.design_columns == DESIGN_COLUMNS[Comparison.A1_VS_A0]
    assert len(result.params) == 3  # [b0, b_checkpoint, b_arm] -- 3-D (handoff §6)
    assert len(result.cov_robust) == 3
    assert all(len(row) == 3 for row in result.cov_robust)
    assert result.n_tasks == 24
    assert result.n_observations == 24 * 4


def test_a2_vs_a1_fit_yields_the_four_dimensional_coefficient_vector() -> None:
    result = fit_gee(_a2_vs_a1(), comparison=Comparison.A2_VS_A1, checkpoint_count=3)
    assert isinstance(result, GeeFit)
    # [b0, b_checkpoint, b_arm, b_interaction] -- 4-D (handoff §6)
    assert len(result.params) == 4
    assert len(result.cov_robust) == 4
    assert all(len(row) == 4 for row in result.cov_robust)


def test_provenance_records_the_frozen_model_and_solver_configuration() -> None:
    result = fit_gee(_a1_vs_a0(), comparison=Comparison.A1_VS_A0, checkpoint_count=3)
    assert isinstance(result, GeeFit)
    provenance = result.provenance
    assert provenance.family == "Binomial"
    assert provenance.link == "logit"
    assert provenance.cov_struct == "Exchangeable"
    assert provenance.cov_type == COV_TYPE == "robust"
    assert provenance.maxiter == MAXITER == 100
    assert provenance.ctol == CTOL == 1e-8
    assert provenance.start_params == "None"
    assert provenance.statsmodels_version == "0.15.0"
    assert dict(provenance.thread_env).keys() == {
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "PYTHONHASHSEED",
    }


def test_binomial_default_link_is_logit_in_the_pinned_statsmodels() -> None:
    # The frozen plan names the logit link; the adapter relies on the family default.
    from statsmodels.genmod.families import Binomial

    assert Binomial().link.__class__.__name__.lower() == "logit"


def test_repeated_execution_is_bitwise_identical() -> None:
    first = fit_gee(_a1_vs_a0(), comparison=Comparison.A1_VS_A0, checkpoint_count=3)
    second = fit_gee(_a1_vs_a0(), comparison=Comparison.A1_VS_A0, checkpoint_count=3)
    assert isinstance(first, GeeFit) and isinstance(second, GeeFit)
    assert first.params == second.params
    assert first.cov_robust == second.cov_robust
    assert first == second


def test_input_order_does_not_change_the_result() -> None:
    observations = _a1_vs_a0()
    shuffled = list(reversed(observations))
    ordered_fit = fit_gee(observations, comparison=Comparison.A1_VS_A0, checkpoint_count=3)
    shuffled_fit = fit_gee(shuffled, comparison=Comparison.A1_VS_A0, checkpoint_count=3)
    assert isinstance(ordered_fit, GeeFit) and isinstance(shuffled_fit, GeeFit)
    # Row order perturbs the solver at machine precision, so the adapter fixes it.
    assert ordered_fit.params == shuffled_fit.params
    assert ordered_fit.cov_robust == shuffled_fit.cov_robust


# ---------------------------------------------------------------------------
# Frozen §3.5.7 failure set
# ---------------------------------------------------------------------------


def _identity(size: int) -> tuple[tuple[float, ...], ...]:
    return tuple(
        tuple(1.0 if row == column else 0.0 for column in range(size)) for row in range(size)
    )


def test_healthy_fit_reports_no_failure() -> None:
    assert classify_failure(converged=True, params=(0.0,) * 3, cov_robust=_identity(3)) is None


def test_non_convergence_is_a_failure() -> None:
    assert (
        classify_failure(converged=False, params=(0.0,) * 3, cov_robust=_identity(3))
        is GeeFailureReason.NON_CONVERGENCE
    )


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_coefficient_or_covariance_is_a_failure(bad: float) -> None:
    assert (
        classify_failure(converged=True, params=(0.0, bad, 0.0), cov_robust=_identity(3))
        is GeeFailureReason.NON_FINITE_ESTIMATE
    )
    cov = [list(row) for row in _identity(3)]
    cov[1][1] = bad
    assert (
        classify_failure(converged=True, params=(0.0,) * 3, cov_robust=cov)
        is GeeFailureReason.NON_FINITE_ESTIMATE
    )


def test_negative_variance_is_a_non_finite_standard_error() -> None:
    cov = [list(row) for row in _identity(2)]
    cov[0][0] = -1.0  # sqrt(V_ii) is not finite
    assert (
        classify_failure(converged=True, params=(0.0,) * 2, cov_robust=cov)
        is GeeFailureReason.NON_FINITE_ESTIMATE
    )


def test_singular_robust_covariance_is_a_failure() -> None:
    # Rank-deficient but positive semi-definite: finite everywhere, yet singular.
    singular = ((1.0, 1.0), (1.0, 1.0))
    assert all(math.isfinite(value) for row in singular for value in row)
    # Determinant is exactly zero: finite and non-negative on the diagonal, yet singular.
    assert singular[0][0] * singular[1][1] - singular[0][1] * singular[1][0] == 0.0
    assert (
        classify_failure(converged=True, params=(0.0,) * 2, cov_robust=singular)
        is GeeFailureReason.SINGULAR_ROBUST_COVARIANCE
    )


def test_every_failure_reason_is_reachable_and_distinct() -> None:
    assert {reason.value for reason in GeeFailureReason} == {
        "NON_CONVERGENCE",
        "SINGULAR_ROBUST_COVARIANCE",
        "NON_FINITE_ESTIMATE",
    }


def test_solver_exception_is_surfaced_as_a_model_failure_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Exploding:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def fit(self, *args: Any, **kwargs: Any) -> Any:
            raise ValueError("singular matrix encountered during solve")

    monkeypatch.setattr(gee_mod, "GEE", _Exploding)
    result = fit_gee(_a1_vs_a0(), comparison=Comparison.A1_VS_A0, checkpoint_count=3)
    assert isinstance(result, GeeFailure)
    assert result.reason is GeeFailureReason.NON_CONVERGENCE
    assert "ValueError" in result.detail
    assert "singular matrix" in result.detail
    assert result.n_tasks == 24


def test_model_failure_is_not_an_exception_and_carries_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _NotConverged:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def fit(self, *args: Any, **kwargs: Any) -> Any:
            class _Result:
                params = (0.0, 0.0, 0.0)
                cov_robust = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
                converged = False

            return _Result()

    monkeypatch.setattr(gee_mod, "GEE", _NotConverged)
    result = fit_gee(_a1_vs_a0(), comparison=Comparison.A1_VS_A0, checkpoint_count=3)
    assert isinstance(result, GeeFailure)
    assert result.reason is GeeFailureReason.NON_CONVERGENCE
    assert result.provenance.maxiter == MAXITER


# ---------------------------------------------------------------------------
# Structural halts (handoff §8): corrupt input is never an inferential outcome
# ---------------------------------------------------------------------------


def test_replicated_a0_is_rejected() -> None:
    # OED-2: A0 at a real checkpoint ordinal would replicate it across K.
    observations = [*_a1_vs_a0(), _obs(_task(0), Arm.A0.value, 1, 1)]
    with pytest.raises(GeeError, match="time-invariant"):
        build_design(observations, comparison=Comparison.A1_VS_A0, checkpoint_count=3)


def test_duplicate_observation_is_rejected() -> None:
    observations = [*_a1_vs_a0(), _obs(_task(0), Arm.A0.value, None, 0)]
    with pytest.raises(GeeError, match="duplicate"):
        build_design(observations, comparison=Comparison.A1_VS_A0, checkpoint_count=3)


def test_foreign_arm_is_rejected() -> None:
    observations = [*_a1_vs_a0(), _obs(_task(0), Arm.A2.value, 1, 1)]
    with pytest.raises(GeeError, match="outside comparison"):
        build_design(observations, comparison=Comparison.A1_VS_A0, checkpoint_count=3)


@pytest.mark.parametrize("endpoint", [-1, 2, 5])
def test_non_binary_endpoint_is_rejected(endpoint: int) -> None:
    observations = [*_a1_vs_a0(n_tasks=2), _obs(_task(99), Arm.A1.value, 1, endpoint)]
    with pytest.raises(GeeError, match="binary"):
        build_design(observations, comparison=Comparison.A1_VS_A0, checkpoint_count=3)


@pytest.mark.parametrize("index", [0, 4, 7])
def test_checkpoint_index_outside_the_schedule_is_rejected(index: int) -> None:
    observations = [*_a1_vs_a0(n_tasks=2), _obs(_task(99), Arm.A1.value, index, 1)]
    with pytest.raises(GeeError, match="outside the pre-registered schedule"):
        build_design(observations, comparison=Comparison.A1_VS_A0, checkpoint_count=3)


def test_unbalanced_design_is_rejected_not_silently_dropped() -> None:
    observations = [o for o in _a1_vs_a0(n_tasks=3) if o.checkpoint_index != 2]
    with pytest.raises(GeeError, match="unbalanced design"):
        build_design(observations, comparison=Comparison.A1_VS_A0, checkpoint_count=3)


def test_missing_a0_row_is_rejected() -> None:
    observations = [o for o in _a1_vs_a0(n_tasks=3) if o.arm != Arm.A0.value]
    with pytest.raises(GeeError, match="unbalanced design"):
        build_design(observations, comparison=Comparison.A1_VS_A0, checkpoint_count=3)


def test_empty_observation_set_is_rejected() -> None:
    with pytest.raises(GeeError, match="empty"):
        build_design([], comparison=Comparison.A1_VS_A0, checkpoint_count=3)


# ---------------------------------------------------------------------------
# Module boundary: no EMM, trend, Holm, decision, memory, or sink surfaces here
# ---------------------------------------------------------------------------


def test_gee_imports_no_downstream_or_forbidden_module() -> None:
    source = Path(gee_mod.__file__).read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    forbidden = (
        "velith.analysis.emm",
        "velith.analysis.trend",
        "velith.analysis.holm",
        "velith.analysis.decision",
        "velith.analysis.mcnemar",
        "velith.analysis.completeness",
        "velith.analysis.result_record",
        "velith.evaluation.sink",
        "velith.episodes.store",
        "velith.retrieval.memory",
        "scipy.stats",
    )
    assert imported.isdisjoint(forbidden), f"forbidden imports: {imported & set(forbidden)}"


def test_gee_defines_no_pvalue_emm_or_decision_surface() -> None:
    public = {name for name in dir(gee_mod) if not name.startswith("_")}
    for forbidden in ("holm_bonferroni", "emm_difference", "decide_k1", "mcnemar_test"):
        assert forbidden not in public
    assert not any("p_value" in name or "pvalue" in name for name in public)
    # GO/NO-GO is C7's; the GEE layer only surfaces the typed failure state.
    assert not any(name.upper() in {"GO", "NO_GO"} for name in public)
