"""Unit tests for the frozen one-sided Wald executor (M9-C10 / P2, spec §3.5.4).

Deterministic synthetic fixtures only — no held-out outcome is ever a fixture (handoff §10).

The p-value is cross-checked against ``scipy.stats.norm.sf`` by exact equality rather than
by an independently coded normal tail: the frozen contract names ``norm.sf`` as the
computation itself, so agreement with it is the specification, not an approximation target.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest
from scipy.stats import norm

from velith.analysis import wald as wald_mod
from velith.analysis.emm import EmmResult
from velith.analysis.gee import DESIGN_COLUMNS, Comparison
from velith.analysis.wald import InferenceError, WaldResult, compute_wald, one_sided_wald


def _emm(delta: float, se: float) -> EmmResult:
    """A synthetic EmmResult carrying exactly the two fields C10 consumes."""
    return EmmResult(
        comparison=Comparison.A1_VS_A0,
        design_columns=DESIGN_COLUMNS[Comparison.A1_VS_A0],
        checkpoint_count=3,
        emm_treatment=0.6,
        emm_reference=0.6 - delta,
        emm_difference=delta,
        gradient=(0.1, 0.0, 0.2),
        standard_error=se,
    )


# ---------------------------------------------------------------------------
# Finite positive standard error — the ordinary rule
# ---------------------------------------------------------------------------


def test_positive_finite_standard_error() -> None:
    result = compute_wald(_emm(0.2, 0.05))
    assert result.delta_emm == 0.2
    assert result.se_emm == 0.05
    assert result.z_stat == 0.2 / 0.05
    assert result.p_value == float(norm.sf(result.z_stat))
    assert 0.0 < result.p_value < 0.5


def test_negative_delta_yields_a_large_p_value() -> None:
    result = compute_wald(_emm(-0.2, 0.05))
    assert result.z_stat == -0.2 / 0.05
    assert result.p_value == float(norm.sf(result.z_stat))
    assert result.p_value > 0.5


def test_zero_delta_with_positive_standard_error() -> None:
    result = compute_wald(_emm(0.0, 0.05))
    assert result.z_stat == 0.0
    assert result.p_value == float(norm.sf(0.0))
    assert result.p_value == pytest.approx(0.5, abs=1e-15)


@pytest.mark.parametrize("z", [-6.0, -2.5, -1.0, 0.0, 1.0, 2.5, 4.0, 8.0])
def test_p_value_matches_scipy_norm_sf_exactly(z: float) -> None:
    se = 0.05
    result = compute_wald(_emm(z * se, se))
    assert result.z_stat == pytest.approx(z, abs=1e-12)
    # Exact equality against the mandated computation, evaluated at the realised z.
    assert result.p_value == float(norm.sf(result.z_stat))


def test_tiny_positive_standard_error_uses_the_ordinary_rule() -> None:
    delta, se = 1e-3, 1e-13
    result = compute_wald(_emm(delta, se))
    # No minimum-SE threshold: the quotient is taken exactly as-is.
    assert result.se_emm == se
    assert result.z_stat == delta / se
    assert math.isfinite(result.z_stat)
    assert result.z_stat > 1e9
    assert result.p_value == float(norm.sf(result.z_stat))


def test_tiny_negative_delta_with_tiny_standard_error() -> None:
    delta, se = -1e-3, 1e-13
    result = compute_wald(_emm(delta, se))
    assert result.z_stat == delta / se
    assert result.p_value == float(norm.sf(result.z_stat))
    assert result.p_value == pytest.approx(1.0, abs=1e-12)


# ---------------------------------------------------------------------------
# Zero standard error — exact cases, never 0/0
# ---------------------------------------------------------------------------


def test_zero_standard_error_with_positive_delta() -> None:
    result = compute_wald(_emm(0.25, 0.0))
    assert result.z_stat == math.inf
    assert result.p_value == 0.0


def test_zero_standard_error_with_negative_delta() -> None:
    result = compute_wald(_emm(-0.25, 0.0))
    assert result.z_stat == -math.inf
    assert result.p_value == 1.0


def test_zero_standard_error_with_zero_delta() -> None:
    result = compute_wald(_emm(0.0, 0.0))
    # Deterministic representation for the 0/0 case; never an actual division.
    assert result.z_stat == 0.0
    assert not math.isnan(result.z_stat)
    assert result.p_value == 1.0


def test_zero_standard_error_never_produces_nan() -> None:
    for delta in (-1.0, -1e-300, 0.0, 1e-300, 1.0):
        result = compute_wald(_emm(delta, 0.0))
        assert not math.isnan(result.z_stat)
        assert not math.isnan(result.p_value)
        assert result.p_value in (0.0, 1.0)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_delta_is_rejected(bad: float) -> None:
    with pytest.raises(InferenceError, match="emm_difference must be finite"):
        compute_wald(_emm(bad, 0.05))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_standard_error_is_rejected(bad: float) -> None:
    with pytest.raises(InferenceError, match="standard_error must be finite"):
        compute_wald(_emm(0.2, bad))


@pytest.mark.parametrize("bad", [-1e-300, -0.05, -1.0])
def test_negative_standard_error_is_rejected(bad: float) -> None:
    with pytest.raises(InferenceError, match="non-negative"):
        compute_wald(_emm(0.2, bad))


def test_negative_zero_standard_error_is_accepted_as_zero() -> None:
    # -0.0 is not less than 0.0 in IEEE-754, so it takes the exact zero-SE path.
    result = compute_wald(_emm(0.25, -0.0))
    assert result.z_stat == math.inf
    assert result.p_value == 0.0


# ---------------------------------------------------------------------------
# No clipping, no correction
# ---------------------------------------------------------------------------


def test_p_value_boundaries_are_exact_and_not_clipped() -> None:
    # An epsilon floor/ceiling would make these strictly interior. They must not be.
    assert compute_wald(_emm(0.25, 0.0)).p_value == 0.0
    assert compute_wald(_emm(-0.25, 0.0)).p_value == 1.0


def test_far_tail_p_value_is_not_floored() -> None:
    result = compute_wald(_emm(1.0, 1e-9))
    assert result.z_stat == 1.0 / 1e-9
    assert result.p_value == float(norm.sf(result.z_stat))
    assert result.p_value == 0.0


def test_inputs_are_echoed_through_unmodified() -> None:
    emm = _emm(0.137, 0.041)
    result = compute_wald(emm)
    assert result.delta_emm == emm.emm_difference
    assert result.se_emm == emm.standard_error
    # C10 never mutates its input.
    assert emm.emm_difference == 0.137
    assert emm.standard_error == 0.041


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_repeated_execution_is_identical() -> None:
    emm = _emm(0.31, 0.07)
    first = compute_wald(emm)
    second = compute_wald(emm)
    assert first == second
    assert first.z_stat == second.z_stat
    assert first.p_value == second.p_value


# ---------------------------------------------------------------------------
# Responsibility / import boundary
# ---------------------------------------------------------------------------


def test_wald_imports_no_forbidden_layer() -> None:
    source = Path(wald_mod.__file__).read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    forbidden = (
        "velith.analysis.gee",
        "velith.analysis.binder",
        "velith.analysis.completeness",
        "velith.analysis.encoding",
        "velith.analysis.preregistration",
        "velith.analysis.prereg_store",
        "velith.analysis.holm",
        "velith.analysis.decision",
        "velith.analysis.mcnemar",
        "velith.analysis.result_record",
        "velith.evaluation.sink",
        "velith.evaluation.record",
        "velith.evaluation.runner",
        "velith.episodes.store",
        "velith.retrieval.memory",
        "statsmodels",
        "numpy",
    )
    overlap = imported & set(forbidden)
    assert not overlap, f"forbidden imports: {overlap}"


def test_wald_defines_no_multiplicity_or_decision_surface() -> None:
    public = {name for name in dir(wald_mod) if not name.startswith("_")}
    for forbidden in (
        "holm_bonferroni",
        "HolmResult",
        "decide_k1",
        "DecisionOutcome",
        "compute_emm",
        "fit_gee",
        "classify_failure",
    ):
        assert forbidden not in public
    assert not any("adjust" in name.lower() for name in public)
    assert not any("rank" in name.lower() for name in public)
    assert not any(name.upper() in {"GO", "NO_GO", "ALPHA"} for name in public)


def test_result_carries_exactly_the_contract_fields() -> None:
    assert set(WaldResult.__dataclass_fields__) == {
        "delta_emm",
        "se_emm",
        "z_stat",
        "p_value",
    }


# ---------------------------------------------------------------------------
# The shared one-sided Wald primitive (M9-C11 refactor)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("delta", "se"),
    [
        (0.2, 0.05),
        (-0.2, 0.05),
        (0.0, 0.05),
        (1e-3, 1e-13),
        (0.25, 0.0),
        (-0.25, 0.0),
        (0.0, 0.0),
    ],
)
def test_compute_wald_delegates_to_the_shared_primitive(delta: float, se: float) -> None:
    result = compute_wald(_emm(delta, se))
    z_stat, p_value = one_sided_wald(delta, se)
    # One implementation of the frozen arithmetic, shared with the trend tests.
    assert result.z_stat == z_stat
    assert result.p_value == p_value


def test_primitive_returns_the_frozen_zero_se_dispositions() -> None:
    assert one_sided_wald(0.25, 0.0) == (math.inf, 0.0)
    assert one_sided_wald(-0.25, 0.0) == (-math.inf, 1.0)
    assert one_sided_wald(0.0, 0.0) == (0.0, 1.0)


def test_primitive_uses_the_ordinary_rule_at_positive_se() -> None:
    z_stat, p_value = one_sided_wald(0.2, 0.05)
    assert z_stat == 0.2 / 0.05
    assert p_value == float(norm.sf(z_stat))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_primitive_validates_both_inputs(bad: float) -> None:
    with pytest.raises(InferenceError, match="estimate must be finite"):
        one_sided_wald(bad, 0.05)
    with pytest.raises(InferenceError, match="standard_error must be finite"):
        one_sided_wald(0.2, bad)


def test_primitive_rejects_a_negative_standard_error() -> None:
    with pytest.raises(InferenceError, match="non-negative"):
        one_sided_wald(0.2, -0.05)


def test_estimate_name_labels_the_message_without_changing_arithmetic() -> None:
    with pytest.raises(InferenceError, match="beta_checkpoint must be finite"):
        one_sided_wald(float("nan"), 0.05, estimate_name="beta_checkpoint")
    # The label is cosmetic: the numbers are identical whatever it is called.
    assert one_sided_wald(0.2, 0.05) == one_sided_wald(0.2, 0.05, estimate_name="beta")


def test_compute_wald_preserves_the_emm_specific_message() -> None:
    with pytest.raises(InferenceError, match="emm_difference must be finite"):
        compute_wald(_emm(float("nan"), 0.05))
