"""Unit tests for the frozen gap-widens trend tests (M9-C11 / P2, spec §3.5.4).

Deterministic synthetic fixtures only — no held-out outcome is ever a fixture (handoff §10).

Pins the frozen coefficient selection (``checkpoint_id_c`` for A1vA0, ``checkpoint_id_c:arm``
for A2vA1), binding by design-column **name** rather than by a bare index, the robust
standard error ``sqrt(V[i][i])``, delegation to the single shared Wald primitive, the
structural halts, and the boundary (no Holm, no decision, no EMM, no separation guard).
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest
from scipy.stats import norm

from velith.analysis import trend as trend_mod
from velith.analysis.gee import DESIGN_COLUMNS, Comparison, GeeFit, SolverProvenance
from velith.analysis.trend import TREND_COLUMNS, TrendError, TrendResult, compute_trend
from velith.analysis.wald import InferenceError, one_sided_wald

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


def _diag(values: tuple[float, ...]) -> tuple[tuple[float, ...], ...]:
    size = len(values)
    return tuple(tuple(values[r] if r == c else 0.0 for c in range(size)) for r in range(size))


def _fit(
    comparison: Comparison,
    params: tuple[float, ...],
    *,
    cov_robust: tuple[tuple[float, ...], ...] | None = None,
    design_columns: tuple[str, ...] | None = None,
) -> GeeFit:
    """A synthetic GeeFit carrying exactly the fields C11 trend consumes."""
    columns = DESIGN_COLUMNS[comparison] if design_columns is None else design_columns
    cov = _diag((1.0,) * len(params)) if cov_robust is None else cov_robust
    return GeeFit(
        comparison=comparison,
        design_columns=columns,
        checkpoint_values=(-1.0, 0.0, 1.0),
        params=params,
        cov_robust=cov,
        n_tasks=12,
        n_observations=48,
        converged=True,
        provenance=_PROVENANCE,
    )


# ---------------------------------------------------------------------------
# Frozen coefficient selection, bound by design-column name
# ---------------------------------------------------------------------------


def test_frozen_trend_columns() -> None:
    assert TREND_COLUMNS[Comparison.A1_VS_A0] == "checkpoint_id_c"
    assert TREND_COLUMNS[Comparison.A2_VS_A1] == "checkpoint_id_c:arm"
    assert set(TREND_COLUMNS) == set(DESIGN_COLUMNS)


def test_a1_vs_a0_uses_the_checkpoint_coefficient() -> None:
    # Distinct coefficients: only index 1 (checkpoint_id_c) is the frozen trend estimand.
    fit = _fit(Comparison.A1_VS_A0, (0.1, 0.2, 0.3), cov_robust=_diag((1.0, 4.0, 9.0)))
    result = compute_trend(fit)
    assert result.coefficient_name == "checkpoint_id_c"
    assert result.estimate == 0.2
    assert result.standard_error == 2.0  # sqrt(4.0)
    assert result.z_stat == pytest.approx(0.1, abs=1e-15)
    assert result.comparison is Comparison.A1_VS_A0


def test_a2_vs_a1_uses_the_interaction_coefficient() -> None:
    # Distinct coefficients: index 3 (checkpoint_id_c:arm), never index 1.
    fit = _fit(
        Comparison.A2_VS_A1,
        (0.1, 0.2, 0.3, 0.4),
        cov_robust=_diag((1.0, 4.0, 9.0, 16.0)),
    )
    result = compute_trend(fit)
    assert result.coefficient_name == "checkpoint_id_c:arm"
    assert result.estimate == 0.4
    assert result.standard_error == 4.0  # sqrt(16.0)
    assert result.z_stat == pytest.approx(0.1, abs=1e-15)


def test_standard_error_ignores_off_diagonal_covariance() -> None:
    # A single-coefficient Wald uses only V[i][i]; off-diagonals must not participate.
    diagonal = _diag((1.0, 4.0, 9.0))
    with_off = tuple(tuple(0.7 if r != c else diagonal[r][c] for c in range(3)) for r in range(3))
    plain = compute_trend(_fit(Comparison.A1_VS_A0, (0.1, 0.2, 0.3), cov_robust=diagonal))
    offset = compute_trend(_fit(Comparison.A1_VS_A0, (0.1, 0.2, 0.3), cov_robust=with_off))
    assert plain.standard_error == offset.standard_error == 2.0
    assert plain.p_value == offset.p_value


# ---------------------------------------------------------------------------
# The frozen one-sided statistic, delegated to the shared primitive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("beta", [-2.0, -0.5, 0.0, 0.5, 3.0])
def test_p_value_matches_the_shared_wald_primitive(beta: float) -> None:
    fit = _fit(Comparison.A1_VS_A0, (0.1, beta, 0.3), cov_robust=_diag((1.0, 4.0, 9.0)))
    result = compute_trend(fit)
    expected_z, expected_p = one_sided_wald(beta, 2.0)
    assert result.z_stat == expected_z
    assert result.p_value == expected_p
    assert result.p_value == float(norm.sf(result.z_stat))


def test_positive_trend_yields_a_small_p_value() -> None:
    fit = _fit(Comparison.A1_VS_A0, (0.0, 4.0, 0.0), cov_robust=_diag((1.0, 1.0, 1.0)))
    result = compute_trend(fit)
    assert result.z_stat == 4.0
    assert result.p_value < 0.001


def test_negative_trend_yields_a_large_p_value() -> None:
    fit = _fit(Comparison.A1_VS_A0, (0.0, -4.0, 0.0), cov_robust=_diag((1.0, 1.0, 1.0)))
    result = compute_trend(fit)
    assert result.z_stat == -4.0
    assert result.p_value > 0.999


def test_zero_trend_gives_one_half() -> None:
    fit = _fit(Comparison.A1_VS_A0, (0.0, 0.0, 0.0), cov_robust=_diag((1.0, 1.0, 1.0)))
    result = compute_trend(fit)
    assert result.z_stat == 0.0
    assert result.p_value == pytest.approx(0.5, abs=1e-15)


def test_extreme_coefficient_is_not_guarded_or_clipped() -> None:
    # No separation guard, no SE floor, no p-value override: the rule applies as written.
    fit = _fit(Comparison.A1_VS_A0, (0.0, 51.0, 0.0), cov_robust=_diag((1.0, 1e-24, 1.0)))
    result = compute_trend(fit)
    assert result.standard_error == math.sqrt(1e-24)
    assert result.z_stat == 51.0 / math.sqrt(1e-24)
    assert result.p_value == 0.0


# ---------------------------------------------------------------------------
# Structural halts
# ---------------------------------------------------------------------------


def test_wrong_design_column_order_is_rejected() -> None:
    bad = ("intercept", "arm", "checkpoint_id_c")
    with pytest.raises(TrendError, match="frozen"):
        compute_trend(_fit(Comparison.A1_VS_A0, (0.1, 0.2, 0.3), design_columns=bad))


def test_missing_interaction_column_is_rejected() -> None:
    bad = ("intercept", "checkpoint_id_c", "arm")
    with pytest.raises(TrendError, match="frozen"):
        compute_trend(_fit(Comparison.A2_VS_A1, (0.1, 0.2, 0.3, 0.4), design_columns=bad))


def test_coefficient_dimensionality_is_validated() -> None:
    with pytest.raises(TrendError, match="coefficients"):
        compute_trend(_fit(Comparison.A1_VS_A0, (0.1, 0.2, 0.3, 0.4)))


def test_covariance_dimensionality_is_validated() -> None:
    bad = ((1.0, 0.0), (0.0, 1.0))
    with pytest.raises(TrendError, match="cov_robust must be"):
        compute_trend(_fit(Comparison.A1_VS_A0, (0.1, 0.2, 0.3), cov_robust=bad))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_variance_is_rejected(bad: float) -> None:
    with pytest.raises(TrendError, match="non-finite robust variance"):
        compute_trend(_fit(Comparison.A1_VS_A0, (0.1, 0.2, 0.3), cov_robust=_diag((1.0, bad, 1.0))))


def test_negative_variance_is_surfaced_not_clamped() -> None:
    with pytest.raises(TrendError, match="invariant violated"):
        compute_trend(
            _fit(Comparison.A1_VS_A0, (0.1, 0.2, 0.3), cov_robust=_diag((1.0, -4.0, 1.0)))
        )


def test_non_finite_coefficient_surfaces_from_the_shared_primitive() -> None:
    bad = float("nan")
    with pytest.raises(InferenceError, match="checkpoint_id_c must be finite"):
        compute_trend(_fit(Comparison.A1_VS_A0, (0.1, bad, 0.3)))


def test_zero_variance_takes_the_frozen_zero_se_path() -> None:
    # C8 guarantees a positive-definite covariance, so this cannot arise from a real fit;
    # if it ever did, the frozen zero-SE disposition applies unchanged.
    positive = compute_trend(
        _fit(Comparison.A1_VS_A0, (0.0, 1.0, 0.0), cov_robust=_diag((1.0, 0.0, 1.0)))
    )
    assert positive.standard_error == 0.0
    assert positive.z_stat == math.inf
    assert positive.p_value == 0.0


# ---------------------------------------------------------------------------
# Determinism and boundary
# ---------------------------------------------------------------------------


def test_repeated_execution_is_identical() -> None:
    fit = _fit(Comparison.A2_VS_A1, (0.1, 0.2, 0.3, 0.4))
    assert compute_trend(fit) == compute_trend(fit)


def test_trend_imports_no_forbidden_layer() -> None:
    source = Path(trend_mod.__file__).read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    forbidden = (
        "velith.analysis.holm",
        "velith.analysis.decision",
        "velith.analysis.emm",
        "velith.analysis.binder",
        "velith.analysis.completeness",
        "velith.analysis.encoding",
        "velith.analysis.preregistration",
        "velith.analysis.prereg_store",
        "velith.analysis.mcnemar",
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
    # The Wald arithmetic is reused, never reimplemented here.
    assert "velith.analysis.wald" in imported


def test_trend_defines_no_multiplicity_or_decision_surface() -> None:
    public = {name for name in dir(trend_mod) if not name.startswith("_")}
    for forbidden in (
        "holm_bonferroni",
        "HolmResult",
        "decide_k1",
        "decide_kgt1",
        "DecisionOutcome",
        "compute_emm",
        "fit_gee",
        "classify_failure",
    ):
        assert forbidden not in public
    assert not any(name.upper() in {"GO", "NO_GO", "ALPHA"} for name in public)


def test_result_carries_exactly_the_contract_fields() -> None:
    assert set(TrendResult.__dataclass_fields__) == {
        "comparison",
        "coefficient_name",
        "estimate",
        "standard_error",
        "z_stat",
        "p_value",
    }
