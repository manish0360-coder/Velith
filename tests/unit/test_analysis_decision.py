"""Unit tests for the GO/NO-GO decision executors (M9-C7 K=1 §3.5.5; M9-C11 K>1 §3.5.8).

Deterministic, synthetic-only. Pins the frozen K=1 rule (GO iff both K=1 McNemar
hypotheses reject under Holm), the VOID dispositions (global-incomplete §3.5.1, n=0 OED-7
§3.5.11), K=1-family dispatch, malformed-input rejection, and that the module recomputes
neither McNemar nor Holm.

The K>1 section pins the frozen four-hypothesis family and its declaration order, the
§3.5.7 model-failure disposition (``p = 1.0`` for both of a failed model's hypotheses),
the four-test Holm ladder, GO iff all four reject, and that the K=1 and K>1 executors
refuse each other's families.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from velith.analysis import decision as decision_mod
from velith.analysis.completeness import CompletenessStatus
from velith.analysis.decision import (
    KGT1_EMM_A1_VS_A0,
    KGT1_EMM_A2_VS_A1,
    KGT1_HYPOTHESIS_LABELS,
    KGT1_INTERACTION_A2_VS_A1,
    KGT1_TREND_A1_VS_A0,
    MODEL_FAILURE_P_VALUE,
    ComparisonPValues,
    DecisionError,
    DecisionOutcome,
    DecisionResult,
    build_kgt1_family,
    comparison_label,
    decide_k1,
    decide_kgt1,
)
from velith.analysis.holm import HolmResult, LabeledPValue, holm_bonferroni

_A1A0 = comparison_label("A1", "A0")
_A2A1 = comparison_label("A2", "A1")


def _holm(p_a1a0: float, p_a2a1: float) -> HolmResult:
    return holm_bonferroni([LabeledPValue(_A1A0, p_a1a0), LabeledPValue(_A2A1, p_a2a1)])


def _decide(p_a1a0: float, p_a2a1: float) -> DecisionResult:
    return decide_k1(
        completeness_status=CompletenessStatus.COMPLETE, holm_result=_holm(p_a1a0, p_a2a1)
    )


def test_both_reject_is_go() -> None:
    result = _decide(0.001, 0.001)
    assert result.outcome is DecisionOutcome.GO
    assert result.rejected_labels == frozenset({_A1A0, _A2A1})


def test_first_rejects_second_not_is_nogo() -> None:
    result = _decide(0.001, 0.5)
    assert result.outcome is DecisionOutcome.NO_GO
    assert result.rejected_labels == frozenset({_A1A0})


def test_second_rejects_first_not_is_nogo() -> None:
    result = _decide(0.5, 0.001)
    assert result.outcome is DecisionOutcome.NO_GO
    assert result.rejected_labels == frozenset({_A2A1})


def test_neither_rejects_is_nogo() -> None:
    result = _decide(0.4, 0.6)
    assert result.outcome is DecisionOutcome.NO_GO
    assert result.rejected_labels == frozenset()


def test_alpha_boundary_both_reject_is_go() -> None:
    # Holm two-test boundary: p(1)=0.005 and p(2)=0.01 both reject inclusively.
    result = _decide(0.005, 0.01)
    assert result.outcome is DecisionOutcome.GO


def test_global_incomplete_is_void() -> None:
    result = decide_k1(completeness_status=CompletenessStatus.VOID_GLOBAL_INCOMPLETE)
    assert result.outcome is DecisionOutcome.VOID
    assert "incomplete" in result.reason


def test_empty_dataset_n0_is_void_not_nogo() -> None:
    result = decide_k1(completeness_status=CompletenessStatus.VOID_EMPTY)
    assert result.outcome is DecisionOutcome.VOID
    # n=0 (OED-7) is a procedural halt, never an inferential GO/NO-GO. Compare on the
    # enum value so mypy does not flag a (trivially-true) non-overlapping identity check.
    assert result.outcome.value not in {DecisionOutcome.GO.value, DecisionOutcome.NO_GO.value}


def test_complete_requires_holm_result() -> None:
    with pytest.raises(DecisionError):
        decide_k1(completeness_status=CompletenessStatus.COMPLETE, holm_result=None)


def test_k1_dispatch_rejects_k_gt_1_family() -> None:
    # A four-hypothesis Holm family is the K>1 path, not owned by the K=1 executor.
    four = holm_bonferroni(
        [
            LabeledPValue("EMM_A1A0", 0.001),
            LabeledPValue("TREND_A1A0", 0.001),
            LabeledPValue("EMM_A2A1", 0.001),
            LabeledPValue("INT_A2A1", 0.001),
        ]
    )
    with pytest.raises(DecisionError):
        decide_k1(completeness_status=CompletenessStatus.COMPLETE, holm_result=four)


def test_wrong_family_labels_rejected() -> None:
    wrong = holm_bonferroni([LabeledPValue("A1>A0", 0.001), LabeledPValue("A9>A8", 0.001)])
    with pytest.raises(DecisionError):
        decide_k1(completeness_status=CompletenessStatus.COMPLETE, holm_result=wrong)


def test_deterministic_repeated_execution() -> None:
    assert _decide(0.001, 0.004) == _decide(0.001, 0.004)


def test_decision_does_not_recompute_mcnemar_or_holm() -> None:
    source = Path(decision_mod.__file__).read_text(encoding="utf-8")
    imports = "\n".join(
        line for line in source.splitlines() if line.startswith(("import ", "from "))
    )
    for forbidden in (
        "holm_bonferroni",
        "mcnemar",
        "assess_completeness",
        "bind_observations",
        "encode_record",
        "math",
        "gee",
        "emm",
        "trend",
        "statsmodels",
        "numpy",
        "scipy",
    ):
        assert forbidden not in imports, f"decision must not import/recompute: {forbidden}"


# ---------------------------------------------------------------------------
# K>1 four-test family and decision (M9-C11, §3.5.6 / §3.5.8)
# ---------------------------------------------------------------------------


def _kgt1_holm(p1: float, p2: float, p3: float, p4: float) -> HolmResult:
    return holm_bonferroni(
        build_kgt1_family(
            a1_vs_a0=ComparisonPValues(p1, p2),
            a2_vs_a1=ComparisonPValues(p3, p4),
        )
    )


def _decide4(p1: float, p2: float, p3: float, p4: float) -> DecisionResult:
    return decide_kgt1(
        completeness_status=CompletenessStatus.COMPLETE,
        holm_result=_kgt1_holm(p1, p2, p3, p4),
    )


def test_frozen_four_hypothesis_labels() -> None:
    assert KGT1_HYPOTHESIS_LABELS == (
        KGT1_EMM_A1_VS_A0,
        KGT1_TREND_A1_VS_A0,
        KGT1_EMM_A2_VS_A1,
        KGT1_INTERACTION_A2_VS_A1,
    )
    assert KGT1_EMM_A1_VS_A0 == "A1>A0:emm"
    assert KGT1_TREND_A1_VS_A0 == "A1>A0:trend"
    assert KGT1_EMM_A2_VS_A1 == "A2>A1:emm"
    assert KGT1_INTERACTION_A2_VS_A1 == "A2>A1:interaction"
    assert len(set(KGT1_HYPOTHESIS_LABELS)) == 4


def test_family_is_assembled_in_frozen_declaration_order() -> None:
    family = build_kgt1_family(
        a1_vs_a0=ComparisonPValues(0.01, 0.02),
        a2_vs_a1=ComparisonPValues(0.03, 0.04),
    )
    assert tuple(pv.label for pv in family) == KGT1_HYPOTHESIS_LABELS
    assert tuple(pv.p_value for pv in family) == (0.01, 0.02, 0.03, 0.04)


def test_model_failure_contributes_p_one_for_both_of_its_hypotheses() -> None:
    assert MODEL_FAILURE_P_VALUE == 1.0
    family = build_kgt1_family(a1_vs_a0=None, a2_vs_a1=ComparisonPValues(0.001, 0.002))
    values = {pv.label: pv.p_value for pv in family}
    assert values[KGT1_EMM_A1_VS_A0] == 1.0
    assert values[KGT1_TREND_A1_VS_A0] == 1.0
    assert values[KGT1_EMM_A2_VS_A1] == 0.001
    assert values[KGT1_INTERACTION_A2_VS_A1] == 0.002


def test_both_models_failing_gives_a_family_of_ones() -> None:
    family = build_kgt1_family(a1_vs_a0=None, a2_vs_a1=None)
    assert tuple(pv.p_value for pv in family) == (1.0, 1.0, 1.0, 1.0)
    outcome = decide_kgt1(
        completeness_status=CompletenessStatus.COMPLETE,
        holm_result=holm_bonferroni(family),
    )
    assert outcome.outcome is DecisionOutcome.NO_GO


def test_all_four_reject_is_go() -> None:
    result = _decide4(0.0001, 0.0002, 0.0003, 0.0004)
    assert result.outcome is DecisionOutcome.GO
    assert result.rejected_labels == frozenset(KGT1_HYPOTHESIS_LABELS)


def test_three_of_four_rejecting_is_no_go() -> None:
    result = _decide4(0.0001, 0.0002, 0.0003, 0.02)
    assert result.outcome is DecisionOutcome.NO_GO
    assert len(result.rejected_labels) == 3


def test_first_step_failure_rejects_nothing() -> None:
    # 0.003 > alpha/4 = 0.0025, so Holm stops at the first step.
    result = _decide4(0.003, 0.003, 0.003, 0.003)
    assert result.outcome is DecisionOutcome.NO_GO
    assert result.rejected_labels == frozenset()


def test_four_test_holm_thresholds_are_the_frozen_ladder() -> None:
    holm = _kgt1_holm(0.0001, 0.0002, 0.0003, 0.0004)
    assert holm.family_size == 4
    assert holm.alpha == 0.01
    thresholds = tuple(d.threshold for d in holm.decisions)
    assert thresholds == (0.01 / 4, 0.01 / 3, 0.01 / 2, 0.01 / 1)


def test_zero_p_value_from_a_saturated_fit_is_consumed_as_emitted() -> None:
    # C10 emits p = 0.0 when SE == 0 and delta > 0. C11 must not override or clip it.
    family = build_kgt1_family(
        a1_vs_a0=ComparisonPValues(0.0, 0.0),
        a2_vs_a1=ComparisonPValues(0.0, 0.0),
    )
    assert tuple(pv.p_value for pv in family) == (0.0, 0.0, 0.0, 0.0)
    result = _decide4(0.0, 0.0, 0.0, 0.0)
    assert result.outcome is DecisionOutcome.GO


def test_kgt1_void_dispositions() -> None:
    incomplete = decide_kgt1(completeness_status=CompletenessStatus.VOID_GLOBAL_INCOMPLETE)
    assert incomplete.outcome is DecisionOutcome.VOID
    assert incomplete.rejected_labels == frozenset()
    empty = decide_kgt1(completeness_status=CompletenessStatus.VOID_EMPTY)
    assert empty.outcome is DecisionOutcome.VOID
    assert empty.rejected_labels == frozenset()


def test_kgt1_complete_requires_a_holm_result() -> None:
    with pytest.raises(DecisionError, match="requires a Holm result"):
        decide_kgt1(completeness_status=CompletenessStatus.COMPLETE)


def test_kgt1_refuses_the_k1_family() -> None:
    with pytest.raises(DecisionError, match="four-hypothesis"):
        decide_kgt1(
            completeness_status=CompletenessStatus.COMPLETE,
            holm_result=_holm(0.001, 0.001),
        )


def test_k1_refuses_the_kgt1_family() -> None:
    with pytest.raises(DecisionError, match="two-hypothesis"):
        decide_k1(
            completeness_status=CompletenessStatus.COMPLETE,
            holm_result=_kgt1_holm(0.001, 0.001, 0.001, 0.001),
        )


def test_kgt1_refuses_a_four_family_with_wrong_labels() -> None:
    wrong = holm_bonferroni([LabeledPValue(f"bogus-{index}", 0.001) for index in range(4)])
    with pytest.raises(DecisionError, match="does not match the frozen K>1"):
        decide_kgt1(completeness_status=CompletenessStatus.COMPLETE, holm_result=wrong)


def test_kgt1_deterministic_repeated_execution() -> None:
    assert _decide4(0.0001, 0.002, 0.003, 0.004) == _decide4(0.0001, 0.002, 0.003, 0.004)
