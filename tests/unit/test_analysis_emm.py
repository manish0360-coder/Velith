"""Unit tests for the frozen response-scale EMM (M9-C9 / P2, spec §3.5.4, handoff §6).

Deterministic synthetic fixtures only — no held-out outcome is ever a fixture (handoff §10).

Expected values are computed inside the tests by an **independent** formulation: the naive
``1/(1+exp(-eta))`` rather than the production sign-branched form, and central finite
differences rather than the analytic gradient. The tests therefore falsify the
implementation instead of restating it. Finite differences are permitted here and forbidden
in production (handoff §6).

The most important test in this module is
``test_a0_is_evaluated_over_the_grid_not_held_at_x_zero``: it pins the RD's A1/A0 ruling
(Interpretation A) and the response-scale estimand against regression to the
linear-predictor collapse ``sigma(mean(eta))`` or the ``[0, 0, 1]`` contrast shortcut.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from velith.analysis import emm as emm_mod
from velith.analysis.emm import EmmError, EmmResult, compute_emm, inverse_logit
from velith.analysis.gee import (
    DESIGN_COLUMNS,
    Comparison,
    GeeFit,
    SolverProvenance,
    centered_checkpoint_values,
)

_PROVENANCE = SolverProvenance(
    statsmodels_version="0.15.0",
    numpy_version="2.5.3",
    family="Binomial",
    link="logit",
    cov_struct="Exchangeable",
    cov_type="robust",
    maxiter=100,
    ctol=1e-8,
    start_params="None",
    thread_env=(("OMP_NUM_THREADS", "1"),),
)


def _identity(size: int) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(1.0 if r == c else 0.0 for c in range(size)) for r in range(size))


def _fit(
    comparison: Comparison,
    params: tuple[float, ...],
    *,
    cov_robust: tuple[tuple[float, ...], ...] | None = None,
    checkpoint_values: tuple[float, ...] | None = None,
    design_columns: tuple[str, ...] | None = None,
) -> GeeFit:
    """A synthetic GeeFit carrying exactly the fields C9 consumes."""
    columns = DESIGN_COLUMNS[comparison] if design_columns is None else design_columns
    grid = centered_checkpoint_values(3) if checkpoint_values is None else checkpoint_values
    cov = _identity(len(params)) if cov_robust is None else cov_robust
    return GeeFit(
        comparison=comparison,
        design_columns=columns,
        checkpoint_values=grid,
        params=params,
        cov_robust=cov,
        n_tasks=12,
        n_observations=48,
        converged=True,
        provenance=_PROVENANCE,
    )


def _naive_expit(eta: float) -> float:
    """Independent inverse-logit used only to cross-check the production branch."""
    return 1.0 / (1.0 + math.exp(-eta))


def _eta_a1_vs_a0(params: tuple[float, ...], x: float, arm: float) -> float:
    return params[0] + params[1] * x + params[2] * arm


def _eta_a2_vs_a1(params: tuple[float, ...], x: float, arm: float) -> float:
    return params[0] + params[1] * x + params[2] * arm + params[3] * (x * arm)


# ---------------------------------------------------------------------------
# A. A1 vs A0 — response-scale EMM over the shared grid
# ---------------------------------------------------------------------------


def test_a1_vs_a0_emm_is_the_response_scale_average_over_the_grid() -> None:
    xs = centered_checkpoint_values(4)
    params = (0.7, 0.9, 1.1)
    result = compute_emm(_fit(Comparison.A1_VS_A0, params, checkpoint_values=xs))

    expected_ref = sum(_naive_expit(_eta_a1_vs_a0(params, x, 0.0)) for x in xs) / len(xs)
    expected_trt = sum(_naive_expit(_eta_a1_vs_a0(params, x, 1.0)) for x in xs) / len(xs)

    assert result.emm_reference == pytest.approx(expected_ref, abs=1e-15)
    assert result.emm_treatment == pytest.approx(expected_trt, abs=1e-15)
    assert result.emm_difference == pytest.approx(expected_trt - expected_ref, abs=1e-15)
    assert result.checkpoint_count == 4
    assert result.comparison is Comparison.A1_VS_A0
    assert result.design_columns == ("intercept", "checkpoint_id_c", "arm")


def test_a0_is_evaluated_over_the_grid_not_held_at_x_zero() -> None:
    """RD ruling, Interpretation A: A0 is evaluated at every pre-registered x_k.

    OED-2's single observed A0 row at checkpoint_id_c = 0 describes the fitted design
    data; it does not pin evaluation of the fitted surface to x = 0. Were A0 held at
    x = 0, emm_reference would equal sigma(b0) exactly.
    """
    xs = centered_checkpoint_values(3)
    params = (1.0, 1.0, 0.5)  # b0 = 1, b_checkpoint = 1 -> A0 varies across the grid
    result = compute_emm(_fit(Comparison.A1_VS_A0, params, checkpoint_values=xs))

    held_at_zero = inverse_logit(params[0])
    over_the_grid = sum(_naive_expit(params[0] + params[1] * x) for x in xs) / len(xs)

    assert result.emm_reference == pytest.approx(over_the_grid, abs=1e-15)
    assert result.emm_reference != pytest.approx(held_at_zero, abs=1e-6)
    # sigma is concave for eta > 0, so the response-scale average sits strictly below.
    assert result.emm_reference < held_at_zero


def test_response_scale_average_differs_from_linear_predictor_average() -> None:
    """mean(sigma(eta)) != sigma(mean(eta)) — the estimand must not collapse."""
    xs = centered_checkpoint_values(5)
    params = (1.2, 0.8, 0.4)
    result = compute_emm(_fit(Comparison.A1_VS_A0, params, checkpoint_values=xs))

    mean_eta_ref = sum(_eta_a1_vs_a0(params, x, 0.0) for x in xs) / len(xs)
    # On a centred grid the linear-predictor average is exactly b0.
    assert mean_eta_ref == pytest.approx(params[0], abs=1e-15)

    collapsed = _naive_expit(mean_eta_ref)
    assert abs(result.emm_reference - collapsed) > 1e-3
    assert abs(result.emm_treatment - _naive_expit(mean_eta_ref + params[2])) > 1e-3


def test_centered_grid_sums_to_zero_yet_estimand_is_not_collapsed() -> None:
    for k in (2, 3, 4, 5, 8):
        assert sum(centered_checkpoint_values(k)) == pytest.approx(0.0, abs=1e-15)

    xs = centered_checkpoint_values(4)
    params = (0.9, 1.5, 0.6)
    result = compute_emm(_fit(Comparison.A1_VS_A0, params, checkpoint_values=xs))
    # The [0, 0, 1] contrast shortcut would make the gradient independent of x_k.
    assert result.gradient[0] != 0.0
    assert result.gradient[1] != 0.0
    assert result.gradient != (0.0, 0.0, 1.0)


# ---------------------------------------------------------------------------
# B. A2 vs A1 — interaction model
# ---------------------------------------------------------------------------


def test_a2_vs_a1_emm_uses_the_interaction_model() -> None:
    xs = centered_checkpoint_values(4)
    params = (-0.3, 0.6, 0.8, 0.45)
    result = compute_emm(_fit(Comparison.A2_VS_A1, params, checkpoint_values=xs))

    expected_ref = sum(_naive_expit(_eta_a2_vs_a1(params, x, 0.0)) for x in xs) / len(xs)
    expected_trt = sum(_naive_expit(_eta_a2_vs_a1(params, x, 1.0)) for x in xs) / len(xs)

    assert result.emm_reference == pytest.approx(expected_ref, abs=1e-15)
    assert result.emm_treatment == pytest.approx(expected_trt, abs=1e-15)
    assert result.emm_difference == pytest.approx(expected_trt - expected_ref, abs=1e-15)
    assert len(result.gradient) == 4
    assert result.design_columns == (
        "intercept",
        "checkpoint_id_c",
        "arm",
        "checkpoint_id_c:arm",
    )


def test_interaction_coefficient_changes_the_estimand() -> None:
    xs = centered_checkpoint_values(4)
    without = compute_emm(_fit(Comparison.A2_VS_A1, (0.1, 0.5, 0.7, 0.0), checkpoint_values=xs))
    with_ix = compute_emm(_fit(Comparison.A2_VS_A1, (0.1, 0.5, 0.7, 0.9), checkpoint_values=xs))
    assert without.emm_difference != with_ix.emm_difference
    assert without.gradient[3] != with_ix.gradient[3]


# ---------------------------------------------------------------------------
# Analytic gradient vs an independent derivation (central finite differences)
# ---------------------------------------------------------------------------


def _emm_difference(
    comparison: Comparison, params: tuple[float, ...], xs: tuple[float, ...]
) -> float:
    return compute_emm(_fit(comparison, params, checkpoint_values=xs)).emm_difference


def _numeric_gradient(
    comparison: Comparison, params: tuple[float, ...], xs: tuple[float, ...]
) -> tuple[float, ...]:
    step = 1e-6
    entries: list[float] = []
    for index in range(len(params)):
        up = list(params)
        down = list(params)
        up[index] += step
        down[index] -= step
        forward = _emm_difference(comparison, tuple(up), xs)
        backward = _emm_difference(comparison, tuple(down), xs)
        entries.append((forward - backward) / (2.0 * step))
    return tuple(entries)


@pytest.mark.parametrize(
    ("comparison", "params"),
    [
        (Comparison.A1_VS_A0, (0.4, 0.7, 1.3)),
        (Comparison.A1_VS_A0, (-1.1, 0.5, 0.2)),
        (Comparison.A2_VS_A1, (0.2, 0.6, 0.9, 0.5)),
        (Comparison.A2_VS_A1, (-0.8, -0.4, 1.2, -0.7)),
    ],
)
def test_analytic_gradient_matches_central_finite_differences(
    comparison: Comparison, params: tuple[float, ...]
) -> None:
    xs = centered_checkpoint_values(4)
    analytic = compute_emm(_fit(comparison, params, checkpoint_values=xs)).gradient
    numeric = _numeric_gradient(comparison, params, xs)
    assert len(analytic) == len(params)
    for exact, approximate in zip(analytic, numeric, strict=True):
        assert exact == pytest.approx(approximate, abs=1e-7)


def test_zero_effect_gradient_closed_form_anchor() -> None:
    # Every eta is 0, so p = 0.5 and d = 0.25 exactly on both arms.
    result = compute_emm(_fit(Comparison.A1_VS_A0, (0.0, 0.0, 0.0)))
    assert result.emm_reference == 0.5
    assert result.emm_treatment == 0.5
    assert result.emm_difference == 0.0
    assert result.gradient == (0.0, 0.0, 0.25)


def test_flat_checkpoint_slope_zeroes_only_the_checkpoint_entry() -> None:
    # b_checkpoint = 0 -> d_diff is constant, and mean(x_k) = 0 kills entry 1 exactly.
    result = compute_emm(_fit(Comparison.A1_VS_A0, (0.0, 0.0, 1.0)))
    p_trt = _naive_expit(1.0)
    d_trt = p_trt * (1.0 - p_trt)
    assert result.gradient[1] == 0.0
    assert result.gradient[0] == pytest.approx(d_trt - 0.25, abs=1e-15)
    assert result.gradient[2] == pytest.approx(d_trt, abs=1e-15)


# ---------------------------------------------------------------------------
# F. Covariance propagation
# ---------------------------------------------------------------------------


def test_standard_error_is_the_full_quadratic_form() -> None:
    cov = (
        (0.30, 0.05, -0.02),
        (0.05, 0.20, 0.03),
        (-0.02, 0.03, 0.40),
    )
    result = compute_emm(_fit(Comparison.A1_VS_A0, (0.5, 0.8, 1.0), cov_robust=cov))
    g = result.gradient
    expected = sum(g[i] * cov[i][j] * g[j] for i in range(len(g)) for j in range(len(g)))
    assert result.standard_error == pytest.approx(math.sqrt(expected), abs=1e-15)


def test_off_diagonal_covariance_entries_change_the_standard_error() -> None:
    params = (0.5, 0.8, 1.0)
    diagonal = ((0.30, 0.0, 0.0), (0.0, 0.20, 0.0), (0.0, 0.0, 0.40))
    with_off = ((0.30, 0.09, 0.07), (0.09, 0.20, 0.05), (0.07, 0.05, 0.40))
    se_diag = compute_emm(_fit(Comparison.A1_VS_A0, params, cov_robust=diagonal)).standard_error
    se_full = compute_emm(_fit(Comparison.A1_VS_A0, params, cov_robust=with_off)).standard_error
    # A diagonal-only reduction is a different quantity and must not be substituted.
    assert se_diag != se_full
    assert se_diag > 0.0
    assert se_full > 0.0


def test_covariance_scale_propagates_into_the_standard_error() -> None:
    params = (0.5, 0.8, 1.0)
    base = compute_emm(_fit(Comparison.A1_VS_A0, params)).standard_error
    scaled_cov = tuple(tuple(4.0 * v for v in row) for row in _identity(3))
    scaled = compute_emm(_fit(Comparison.A1_VS_A0, params, cov_robust=scaled_cov)).standard_error
    assert scaled == pytest.approx(2.0 * base, abs=1e-15)


# ---------------------------------------------------------------------------
# E. Design-column binding and structural validation
# ---------------------------------------------------------------------------


def test_wrong_design_column_order_is_rejected() -> None:
    bad = ("intercept", "arm", "checkpoint_id_c")
    with pytest.raises(EmmError, match="frozen order"):
        compute_emm(_fit(Comparison.A1_VS_A0, (0.1, 0.2, 0.3), design_columns=bad))


def test_missing_interaction_column_is_rejected() -> None:
    bad = ("intercept", "checkpoint_id_c", "arm")
    with pytest.raises(EmmError, match="frozen order"):
        compute_emm(_fit(Comparison.A2_VS_A1, (0.1, 0.2, 0.3, 0.4), design_columns=bad))


def test_unexpected_extra_column_is_rejected() -> None:
    bad = ("intercept", "checkpoint_id_c", "arm", "unexpected")
    with pytest.raises(EmmError, match="frozen order"):
        compute_emm(_fit(Comparison.A1_VS_A0, (0.1, 0.2, 0.3), design_columns=bad))


def test_coefficient_dimensionality_is_validated() -> None:
    with pytest.raises(EmmError, match="coefficients"):
        compute_emm(_fit(Comparison.A1_VS_A0, (0.1, 0.2, 0.3, 0.4)))


@pytest.mark.parametrize(
    "cov",
    [
        ((1.0, 0.0), (0.0, 1.0)),
        ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        ((1.0, 0.0), (0.0, 1.0), (0.0, 0.0)),
    ],
)
def test_covariance_dimensionality_is_validated(
    cov: tuple[tuple[float, ...], ...],
) -> None:
    with pytest.raises(EmmError, match="cov_robust must be"):
        compute_emm(_fit(Comparison.A1_VS_A0, (0.1, 0.2, 0.3), cov_robust=cov))


@pytest.mark.parametrize("values", [(), (0.0,)])
def test_k_less_than_two_is_rejected(values: tuple[float, ...]) -> None:
    with pytest.raises(EmmError, match="K>1"):
        compute_emm(_fit(Comparison.A1_VS_A0, (0.1, 0.2, 0.3), checkpoint_values=values))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_inputs_are_rejected(bad: float) -> None:
    rows = [list(row) for row in _identity(3)]
    rows[1][1] = bad
    bad_cov = tuple(tuple(row) for row in rows)
    bad_grid = (-1.0, bad, 1.0)

    with pytest.raises(EmmError, match="non-finite"):
        compute_emm(_fit(Comparison.A1_VS_A0, (0.1, bad, 0.3)))
    with pytest.raises(EmmError, match="non-finite"):
        compute_emm(_fit(Comparison.A1_VS_A0, (0.1, 0.2, 0.3), cov_robust=bad_cov))
    with pytest.raises(EmmError, match="non-finite"):
        compute_emm(_fit(Comparison.A1_VS_A0, (0.1, 0.2, 0.3), checkpoint_values=bad_grid))


# ---------------------------------------------------------------------------
# G. Numerical behaviour — saturation, zero and tiny SE, no clamping
# ---------------------------------------------------------------------------


def test_inverse_logit_is_overflow_safe_in_both_directions() -> None:
    assert inverse_logit(1000.0) == 1.0
    assert inverse_logit(-1000.0) == 0.0
    assert inverse_logit(0.0) == 0.5
    assert inverse_logit(1.0) == pytest.approx(_naive_expit(1.0), abs=1e-15)
    assert inverse_logit(-1.0) == pytest.approx(_naive_expit(-1.0), abs=1e-15)


def test_probabilities_are_not_clamped_away_from_the_boundaries() -> None:
    # An epsilon floor or clip would make these strictly interior. They must not be.
    assert inverse_logit(800.0) == 1.0
    assert inverse_logit(-800.0) == 0.0


def test_both_arms_saturated_yields_exactly_zero_standard_error() -> None:
    result = compute_emm(_fit(Comparison.A1_VS_A0, (1000.0, 0.0, 1000.0)))
    assert result.emm_reference == 1.0
    assert result.emm_treatment == 1.0
    assert result.emm_difference == 0.0
    assert result.gradient == (0.0, 0.0, 0.0)
    # Zero SE passes through untouched: no epsilon, no failure, no reclassification.
    assert result.standard_error == 0.0
    assert isinstance(result, EmmResult)


def test_tiny_but_nonzero_standard_error_is_not_floored() -> None:
    result = compute_emm(_fit(Comparison.A1_VS_A0, (30.0, 0.0, 1.0)))
    assert 0.0 < result.standard_error < 1e-10


def test_large_negative_logits_saturate_to_zero_probability() -> None:
    result = compute_emm(_fit(Comparison.A1_VS_A0, (-1000.0, 0.0, -1000.0)))
    assert result.emm_reference == 0.0
    assert result.emm_treatment == 0.0
    assert result.standard_error == 0.0


# ---------------------------------------------------------------------------
# H. Invariant violation
# ---------------------------------------------------------------------------


def test_negative_quadratic_form_is_surfaced_not_clamped() -> None:
    not_psd = ((-1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    with pytest.raises(EmmError, match="invariant violated"):
        compute_emm(_fit(Comparison.A1_VS_A0, (0.0, 0.0, 1.0), cov_robust=not_psd))


def test_zero_quadratic_form_is_not_treated_as_an_invariant_violation() -> None:
    zeros = tuple(tuple(0.0 for _ in range(3)) for _ in range(3))
    result = compute_emm(_fit(Comparison.A1_VS_A0, (0.5, 0.8, 1.0), cov_robust=zeros))
    assert result.standard_error == 0.0


# ---------------------------------------------------------------------------
# I. Determinism
# ---------------------------------------------------------------------------


def test_repeated_execution_is_identical() -> None:
    fit = _fit(Comparison.A2_VS_A1, (0.3, 0.7, 1.1, 0.4))
    first = compute_emm(fit)
    second = compute_emm(fit)
    assert first == second
    assert first.gradient == second.gradient
    assert first.standard_error == second.standard_error


def test_grid_is_traversed_as_supplied() -> None:
    xs = centered_checkpoint_values(4)
    params = (0.6, 0.9, 0.7)
    ordered = compute_emm(_fit(Comparison.A1_VS_A0, params, checkpoint_values=xs))
    reversed_grid = compute_emm(
        _fit(Comparison.A1_VS_A0, params, checkpoint_values=tuple(reversed(xs)))
    )
    # The estimand is a mean, so a permuted grid agrees mathematically; the supplied
    # order is nonetheless what is actually traversed and summed.
    assert ordered.emm_difference == pytest.approx(reversed_grid.emm_difference, abs=1e-15)


# ---------------------------------------------------------------------------
# J. Module boundary
# ---------------------------------------------------------------------------


def test_emm_imports_no_forbidden_layer() -> None:
    source = Path(emm_mod.__file__).read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    forbidden = (
        "velith.analysis.binder",
        "velith.analysis.completeness",
        "velith.analysis.encoding",
        "velith.analysis.preregistration",
        "velith.analysis.prereg_store",
        "velith.analysis.holm",
        "velith.analysis.decision",
        "velith.analysis.mcnemar",
        "velith.analysis.trend",
        "velith.analysis.result_record",
        "velith.evaluation.sink",
        "velith.evaluation.record",
        "velith.evaluation.runner",
        "velith.episodes.store",
        "velith.retrieval.memory",
        "statsmodels",
        "numpy",
        "scipy",
        "scipy.stats",
    )
    overlap = imported & set(forbidden)
    assert not overlap, f"forbidden imports: {overlap}"


def test_emm_defines_no_inference_or_decision_surface() -> None:
    public = {name for name in dir(emm_mod) if not name.startswith("_")}
    for forbidden in (
        "holm_bonferroni",
        "decide_k1",
        "mcnemar_test",
        "fit_gee",
        "classify_failure",
    ):
        assert forbidden not in public
    assert not any("p_value" in name or "pvalue" in name for name in public)
    assert not any(name.lower() in {"z", "z_score", "zscore"} for name in public)
    assert not any(name.upper() in {"GO", "NO_GO"} for name in public)


def test_result_carries_no_test_statistic_fields() -> None:
    assert set(EmmResult.__dataclass_fields__) == {
        "comparison",
        "design_columns",
        "checkpoint_count",
        "emm_treatment",
        "emm_reference",
        "emm_difference",
        "gradient",
        "standard_error",
    }
