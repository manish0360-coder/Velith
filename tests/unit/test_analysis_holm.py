"""Unit tests for the sequential Holm-Bonferroni procedure (M9-C6 / P2, §3.5.6).

Deterministic, synthetic p-values only — independent of C5. Pins the frozen step-down Holm
at alpha=0.01: ascending order, thresholds alpha/(m-i+1), inclusive boundary, stop-at-first-non-
rejection, deterministic ties, validation, and that the procedure is genuinely Holm (not a
fixed Bonferroni threshold). C6 computes rejections only — no GO/NO-GO.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from velith.analysis import holm as holm_mod
from velith.analysis.holm import ALPHA, HolmError, LabeledPValue, holm_bonferroni


def _fam(*pairs: tuple[str, float]) -> list[LabeledPValue]:
    return [LabeledPValue(label, p) for label, p in pairs]


def _rejected(*pairs: tuple[str, float]) -> frozenset[str]:
    return holm_bonferroni(_fam(*pairs)).rejected_labels


def test_alpha_is_fixed_001() -> None:
    assert ALPHA == 0.01


def test_empty_family_rejected() -> None:
    with pytest.raises(HolmError):
        holm_bonferroni([])


def test_single_pvalue_at_alpha_boundary_inclusive() -> None:
    assert _rejected(("h", 0.01)) == frozenset({"h"})  # p == alpha/1, inclusive
    assert _rejected(("h", 0.0100001)) == frozenset()


def test_two_test_thresholds_005_and_01() -> None:
    # m=2: thresholds 0.005 then 0.01, both inclusive.
    assert _rejected(("a", 0.005), ("b", 0.01)) == frozenset({"a", "b"})
    assert _rejected(("a", 0.0050001), ("b", 0.01)) == frozenset()  # first fails -> stop


def test_four_test_thresholds() -> None:
    # m=4 thresholds: 0.0025, 0.003333, 0.005, 0.01.
    result = holm_bonferroni(_fam(("a", 0.002), ("b", 0.003), ("c", 0.004), ("d", 0.009)))
    assert [round(d.threshold, 6) for d in result.decisions] == [0.0025, 0.003333, 0.005, 0.01]
    assert result.rejected_labels == frozenset({"a", "b", "c", "d"})


def test_p_zero_rejected_p_one_not() -> None:
    assert _rejected(("z", 0.0)) == frozenset({"z"})
    assert _rejected(("o", 1.0)) == frozenset()


def test_all_rejected() -> None:
    assert _rejected(("a", 0.001), ("b", 0.001), ("c", 0.001), ("d", 0.001)) == frozenset(
        {"a", "b", "c", "d"}
    )


def test_none_rejected() -> None:
    assert _rejected(("a", 0.2), ("b", 0.3), ("c", 0.4), ("d", 0.5)) == frozenset()


def test_stop_at_first_non_rejection_blocks_later_significant() -> None:
    # sorted [0.001, 0.008, 0.009]; thresholds 0.003333, 0.005, 0.01.
    # H(1) rejected; H(2)=0.008 > 0.005 -> STOP; H(3)=0.009 <= its own 0.01 but is BLOCKED.
    assert _rejected(("a", 0.001), ("b", 0.008), ("c", 0.009)) == frozenset({"a"})


def test_is_holm_not_fixed_bonferroni() -> None:
    # m=4: Holm rejects {a,b,c} (0.002<=0.0025, 0.003<=0.00333, 0.004<=0.005);
    # a fixed Bonferroni alpha/m=0.0025 would reject only {a}. This distinguishes Holm.
    assert _rejected(("a", 0.002), ("b", 0.003), ("c", 0.004), ("d", 0.5)) == frozenset(
        {"a", "b", "c"}
    )


def test_order_independent_and_deterministic() -> None:
    forward = _fam(("a", 0.004), ("b", 0.002), ("c", 0.5), ("d", 0.003))
    r1 = holm_bonferroni(forward)
    r2 = holm_bonferroni(list(reversed(forward)))
    assert r1 == r2
    # decisions are emitted in ascending (p_value, label) order.
    assert [d.p_value for d in r1.decisions] == [0.002, 0.003, 0.004, 0.5]


def test_tied_pvalues_are_deterministic_by_label() -> None:
    result = holm_bonferroni(_fam(("b", 0.004), ("a", 0.004)))
    assert [d.label for d in result.decisions] == ["a", "b"]  # tie broken by label


def test_duplicate_labels_rejected() -> None:
    with pytest.raises(HolmError):
        holm_bonferroni(_fam(("dup", 0.01), ("dup", 0.02)))


def test_invalid_pvalues_rejected() -> None:
    for bad in (float("nan"), float("inf"), -0.1, 1.1):
        with pytest.raises(HolmError):
            holm_bonferroni(_fam(("x", bad)))


def test_rank_and_threshold_recorded() -> None:
    result = holm_bonferroni(_fam(("a", 0.001), ("b", 0.02)))
    ranks = {d.label: (d.rank, d.threshold, d.rejected) for d in result.decisions}
    assert ranks["a"] == (1, 0.005, True)
    assert ranks["b"] == (2, 0.01, False)


def test_holm_has_no_decision_or_statistical_surfaces() -> None:
    source = Path(holm_mod.__file__).read_text(encoding="utf-8")
    imports = "\n".join(
        line for line in source.splitlines() if line.startswith(("import ", "from "))
    )
    for forbidden in (
        "mcnemar",
        "gee",
        "emm",
        "trend",
        "decision",
        "completeness",
        "binder",
        "statsmodels",
        "numpy",
        "scipy",
        "evaluation",
        "velith",
    ):
        assert forbidden not in imports, f"holm must not import: {forbidden}"
