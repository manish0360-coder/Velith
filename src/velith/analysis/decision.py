"""GO/NO-GO decision executors for the M9 analysis (M9-C7 K=1 §3.5.5; M9-C11 K>1 §3.5.8).

The frozen K=1 decision maps the upstream completeness status (C3) and the two-test
Holm-Bonferroni result (C6) to a single deterministic outcome:

* **VOID** if the M8 evaluation was globally incomplete (§3.5.1) or if complete-case
  exclusion left ``n = 0`` tasks (OED-7 / §3.5.11) — a procedural halt, never a NO-GO.
* **GO** iff the analysis is COMPLETE and **both** frozen K=1 comparisons —
  ``H_a1: P(A1) > P(A0)`` and ``H_a2: P(A2) > P(A1)`` — reject under the two-test Holm
  procedure (§3.5.5).
* **NO-GO** for a COMPLETE analysis where not both reject.

The frozen K>1 decision (M9-C11, §3.5.8) is the additive sibling ``decide_kgt1``: **GO iff
all four** confirmatory hypotheses reject under the same four-test Holm family (§3.5.6),
with the identical VOID short-circuit. ``build_kgt1_family`` assembles that family and
carries the frozen §3.5.7 model-failure disposition (a failed model contributes ``p = 1.0``
for both of its hypotheses).

This module owns ONLY these decision mappings. It recomputes **no** statistic — not
McNemar (C5), Holm (C6), GEE (C8), EMM (C9), Wald (C10), or trend (C11) — applies no
second multiplicity correction, introduces no effect-size requirement, minimum p-value,
standard-error threshold, or separation guard, and performs no held-out access or memory
writes. Each executor refuses a Holm family that is not its own frozen family, so the K=1
and K>1 paths cannot be crossed. K=1 has no GEE model-failure state (§3.5.7 is K>1).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from velith.analysis.completeness import CompletenessStatus
from velith.analysis.holm import HolmResult, LabeledPValue
from velith.arms.identity import Arm


class DecisionError(Exception):
    """Raised on malformed decision input (wrong Holm family, missing result, bad status)."""


class DecisionOutcome(str, Enum):
    """The frozen decision vocabulary: GO / NO-GO (inferential) or VOID (procedural halt)."""

    GO = "GO"
    NO_GO = "NO_GO"
    VOID = "VOID"


def comparison_label(superior: str, reference: str) -> str:
    """The canonical label for a pairwise comparison ``superior > reference``."""
    return f"{superior}>{reference}"


#: The frozen K=1 ordered-hypothesis comparisons (§3.5.5): both must reject for GO.
K1_ORDERED_COMPARISONS: Final[tuple[tuple[str, str], ...]] = (
    (Arm.A1.value, Arm.A0.value),
    (Arm.A2.value, Arm.A1.value),
)


@dataclass(frozen=True)
class DecisionResult:
    """The deterministic K=1 decision: outcome, a human-readable reason, and rejected labels."""

    outcome: DecisionOutcome
    reason: str
    rejected_labels: frozenset[str]


def decide_k1(
    *, completeness_status: CompletenessStatus, holm_result: HolmResult | None = None
) -> DecisionResult:
    """Map the completeness status and the two-test Holm result to the frozen K=1 outcome.

    ``VOID`` short-circuits before the Holm result is consulted. For a ``COMPLETE`` analysis
    a ``HolmResult`` is required, its family must be exactly the two frozen K=1 comparisons,
    and GO holds iff both reject. Deterministic; recomputes no statistic.
    """
    if completeness_status is CompletenessStatus.VOID_GLOBAL_INCOMPLETE:
        return DecisionResult(
            DecisionOutcome.VOID, "global M8 evaluation incomplete (VOID, §3.5.1)", frozenset()
        )
    if completeness_status is CompletenessStatus.VOID_EMPTY:
        return DecisionResult(
            DecisionOutcome.VOID,
            "n=0 after complete-case exclusion (VOID, OED-7 / §3.5.11)",
            frozenset(),
        )
    if completeness_status is not CompletenessStatus.COMPLETE:
        raise DecisionError(f"unknown completeness status: {completeness_status!r}")

    if holm_result is None:
        raise DecisionError("a COMPLETE analysis requires a Holm result")
    if holm_result.family_size != 2:
        raise DecisionError(
            "the K=1 decision requires the two-hypothesis Holm family; got family_size="
            f"{holm_result.family_size} (K>1 is not owned by the K=1 executor)"
        )
    expected = frozenset(comparison_label(sup, ref) for sup, ref in K1_ORDERED_COMPARISONS)
    labels = frozenset(decision.label for decision in holm_result.decisions)
    if labels != expected:
        raise DecisionError(
            f"Holm family {sorted(labels)} does not match the frozen K=1 comparisons "
            f"{sorted(expected)}"
        )

    rejected = holm_result.rejected_labels
    if expected <= rejected:
        return DecisionResult(
            DecisionOutcome.GO, "both K=1 McNemar hypotheses reject under Holm (§3.5.5)", rejected
        )
    return DecisionResult(
        DecisionOutcome.NO_GO, "not all K=1 hypotheses reject under Holm (§3.5.5)", rejected
    )


_A1_VS_A0: Final[str] = comparison_label(Arm.A1.value, Arm.A0.value)
_A2_VS_A1: Final[str] = comparison_label(Arm.A2.value, Arm.A1.value)

#: The frozen K>1 confirmatory hypotheses (§3.5.6), labelled from the shared comparison
#: vocabulary so the arm pairing is defined once.
KGT1_EMM_A1_VS_A0: Final[str] = f"{_A1_VS_A0}:emm"
KGT1_TREND_A1_VS_A0: Final[str] = f"{_A1_VS_A0}:trend"
KGT1_EMM_A2_VS_A1: Final[str] = f"{_A2_VS_A1}:emm"
KGT1_INTERACTION_A2_VS_A1: Final[str] = f"{_A2_VS_A1}:interaction"

#: Exactly four hypotheses, in frozen declaration order (§3.5.6).
KGT1_HYPOTHESIS_LABELS: Final[tuple[str, ...]] = (
    KGT1_EMM_A1_VS_A0,
    KGT1_TREND_A1_VS_A0,
    KGT1_EMM_A2_VS_A1,
    KGT1_INTERACTION_A2_VS_A1,
)

#: The frozen §3.5.7 disposition: a failed GEE model contributes ``p = 1.0`` for **both**
#: of its hypotheses, which deterministically produces NO-GO.
MODEL_FAILURE_P_VALUE: Final[float] = 1.0


@dataclass(frozen=True)
class ComparisonPValues:
    """The two p-values one fitted adjacent-arm comparison contributes to the family.

    ``trend_p_value`` is the ``checkpoint_id_c`` coefficient test for A1 vs A0 and the
    ``checkpoint_id_c:arm`` interaction test for A2 vs A1 (§3.5.4).
    """

    emm_p_value: float
    trend_p_value: float


def build_kgt1_family(
    *,
    a1_vs_a0: ComparisonPValues | None,
    a2_vs_a1: ComparisonPValues | None,
) -> tuple[LabeledPValue, ...]:
    """Assemble the frozen four-hypothesis Holm family (§3.5.6) in declaration order.

    ``None`` for a comparison encodes the frozen §3.5.7 model-failure disposition: that
    model's **two** p-values are defined as ``1.0``. The caller passes ``None`` iff C8
    returned a ``GeeFailure``. This function never inspects a fit, never reclassifies a
    valid ``GeeFit``, and never examines separation, parameter magnitude, standard-error
    magnitude, or p-value magnitude.
    """
    failed = ComparisonPValues(MODEL_FAILURE_P_VALUE, MODEL_FAILURE_P_VALUE)
    first = failed if a1_vs_a0 is None else a1_vs_a0
    second = failed if a2_vs_a1 is None else a2_vs_a1
    return (
        LabeledPValue(KGT1_EMM_A1_VS_A0, first.emm_p_value),
        LabeledPValue(KGT1_TREND_A1_VS_A0, first.trend_p_value),
        LabeledPValue(KGT1_EMM_A2_VS_A1, second.emm_p_value),
        LabeledPValue(KGT1_INTERACTION_A2_VS_A1, second.trend_p_value),
    )


def decide_kgt1(
    *, completeness_status: CompletenessStatus, holm_result: HolmResult | None = None
) -> DecisionResult:
    """Map the completeness status and the four-test Holm result to the frozen K>1 outcome.

    §3.5.8: **GO iff all four** pre-registered hypotheses are significant after the
    Holm-Bonferroni correction of §3.5.6; every other outcome is NO-GO. ``VOID``
    short-circuits first (§3.5.1; OED-7 / §3.5.11) and is a procedural halt, never a NO-GO.

    Additive sibling of :func:`decide_k1`. Deterministic; recomputes no statistic.
    """
    if completeness_status is CompletenessStatus.VOID_GLOBAL_INCOMPLETE:
        return DecisionResult(
            DecisionOutcome.VOID, "global M8 evaluation incomplete (VOID, §3.5.1)", frozenset()
        )
    if completeness_status is CompletenessStatus.VOID_EMPTY:
        return DecisionResult(
            DecisionOutcome.VOID,
            "n=0 after complete-case exclusion (VOID, OED-7 / §3.5.11)",
            frozenset(),
        )
    if completeness_status is not CompletenessStatus.COMPLETE:
        raise DecisionError(f"unknown completeness status: {completeness_status!r}")

    if holm_result is None:
        raise DecisionError("a COMPLETE analysis requires a Holm result")
    if holm_result.family_size != len(KGT1_HYPOTHESIS_LABELS):
        raise DecisionError(
            "the K>1 decision requires the four-hypothesis Holm family; got family_size="
            f"{holm_result.family_size} (K=1 is not owned by the K>1 executor)"
        )
    expected = frozenset(KGT1_HYPOTHESIS_LABELS)
    labels = frozenset(decision.label for decision in holm_result.decisions)
    if labels != expected:
        raise DecisionError(
            f"Holm family {sorted(labels)} does not match the frozen K>1 hypotheses "
            f"{sorted(expected)}"
        )

    rejected = holm_result.rejected_labels
    if expected <= rejected:
        return DecisionResult(
            DecisionOutcome.GO, "all four K>1 hypotheses reject under Holm (§3.5.8)", rejected
        )
    return DecisionResult(
        DecisionOutcome.NO_GO, "not all K>1 hypotheses reject under Holm (§3.5.8)", rejected
    )
