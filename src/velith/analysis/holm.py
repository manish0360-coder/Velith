"""Sequential Holm-Bonferroni multiple-testing procedure for the M9 analysis (M9-C6 / P2).

The frozen step-down Holm-Bonferroni at family-wise ``alpha = 0.01`` (§3.5.6 for the K>1
four-test family; the K=1 two-test family uses the identical procedure with ``m = 2``). It
controls the family-wise error rate over a family of labeled p-values and reports, per
hypothesis, whether it is **rejected**. It computes **no** GO/NO-GO decision — that is
``decision.py`` (§4.12), which maps "all rejected" to GO.

Procedure (§3.5.6): order the ``m`` p-values ascending ``p(1) <= ... <= p(m)``; reject
sequentially, **stopping at the first non-rejection**: reject ``H(i)`` iff
``p(i) <= alpha / (m - i + 1)``. For ``m = 4`` the thresholds are ``0.01/4, 0.01/3, 0.01/2,
0.01/1``; for ``m = 2`` they are ``0.005, 0.01``. The alpha boundary is **inclusive**. Ties are
ordered deterministically by ``(p_value, label)``.

``alpha`` is fixed at 0.01 (never configurable); the family size ``m`` is the number of p-values
supplied (2 for K=1, 4 for K>1). C6 owns ONLY this procedure — no McNemar/GEE/EMM/trend, no
completeness, no GO/NO-GO, no held-out access, no memory writes.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

#: The frozen family-wise error rate (§3.5.6). Not configurable.
ALPHA: Final[float] = 0.01


class HolmError(Exception):
    """Raised on a malformed Holm family (empty, duplicate labels, invalid p-values)."""


@dataclass(frozen=True)
class LabeledPValue:
    """One hypothesis's p-value, tagged with its comparison identity (preserved in output)."""

    label: str
    p_value: float


@dataclass(frozen=True)
class HolmDecision:
    """The per-hypothesis Holm outcome: its ascending rank, threshold, and rejection."""

    label: str
    p_value: float
    rank: int
    threshold: float
    rejected: bool


@dataclass(frozen=True)
class HolmResult:
    """The deterministic Holm outcome over a family (decisions in ascending order)."""

    alpha: float
    family_size: int
    decisions: tuple[HolmDecision, ...]

    @property
    def rejected_labels(self) -> frozenset[str]:
        """The set of rejected hypothesis labels (factual; not a GO/NO-GO decision)."""
        return frozenset(decision.label for decision in self.decisions if decision.rejected)


def holm_bonferroni(pvalues: Sequence[LabeledPValue]) -> HolmResult:
    """Apply the frozen step-down Holm-Bonferroni at ``alpha = 0.01`` over ``pvalues`` (§3.5.6).

    ``m`` is ``len(pvalues)``. The p-values are ordered ascending (ties broken by label);
    hypotheses are rejected sequentially while ``p(i) <= alpha / (m - i + 1)`` and the procedure
    stops at the first non-rejection. Raises :class:`HolmError` on an empty family, duplicate
    labels, or a p-value that is NaN, infinite, or outside ``[0, 1]``.
    """
    if not pvalues:
        raise HolmError("Holm family is empty; at least one hypothesis is required")
    labels = [pv.label for pv in pvalues]
    if len(set(labels)) != len(labels):
        raise HolmError("duplicate hypothesis label in the Holm family")
    for pv in pvalues:
        if math.isnan(pv.p_value) or math.isinf(pv.p_value) or not (0.0 <= pv.p_value <= 1.0):
            raise HolmError(f"invalid p-value for {pv.label!r}: {pv.p_value!r}")

    m = len(pvalues)
    ordered = sorted(pvalues, key=lambda pv: (pv.p_value, pv.label))
    decisions: list[HolmDecision] = []
    still_rejecting = True
    for rank, pv in enumerate(ordered, start=1):
        threshold = ALPHA / (m - rank + 1)
        if still_rejecting and pv.p_value <= threshold:
            rejected = True
        else:
            rejected = False
            still_rejecting = False
        decisions.append(HolmDecision(pv.label, pv.p_value, rank, threshold, rejected))
    return HolmResult(ALPHA, m, tuple(decisions))
