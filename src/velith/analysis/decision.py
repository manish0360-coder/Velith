"""K=1 GO/NO-GO decision executor for the M9 analysis (M9-C7 / P2, §3.5.5).

The frozen K=1 decision maps the upstream completeness status (C3) and the two-test
Holm-Bonferroni result (C6) to a single deterministic outcome:

* **VOID** if the M8 evaluation was globally incomplete (§3.5.1) or if complete-case
  exclusion left ``n = 0`` tasks (OED-7 / §3.5.11) — a procedural halt, never a NO-GO.
* **GO** iff the analysis is COMPLETE and **both** frozen K=1 comparisons —
  ``H_a1: P(A1) > P(A0)`` and ``H_a2: P(A2) > P(A1)`` — reject under the two-test Holm
  procedure (§3.5.5).
* **NO-GO** for a COMPLETE analysis where not both reject.

C7 owns ONLY this decision mapping. It does **not** recompute McNemar (C5) or Holm (C6),
does not implement GEE/EMM/trend or the K>1 decision (§3.5.8, a later milestone), and
performs no held-out access or memory writes. K=1 has no GEE model-failure state (§3.5.7 is
K>1); a family that is not the two-hypothesis K=1 family is refused (K>1 is not owned here).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from velith.analysis.completeness import CompletenessStatus
from velith.analysis.holm import HolmResult
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
