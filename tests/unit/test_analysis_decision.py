"""Unit tests for the K=1 GO/NO-GO decision executor (M9-C7 / P2, §3.5.5).

Deterministic, synthetic-only. Pins the frozen K=1 rule (GO iff both K=1 McNemar
hypotheses reject under Holm), the VOID dispositions (global-incomplete §3.5.1, n=0 OED-7
§3.5.11), K=1-family dispatch, malformed-input rejection, and that C7 recomputes neither
McNemar nor Holm.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from velith.analysis import decision as decision_mod
from velith.analysis.completeness import CompletenessStatus
from velith.analysis.decision import (
    DecisionError,
    DecisionOutcome,
    DecisionResult,
    comparison_label,
    decide_k1,
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
