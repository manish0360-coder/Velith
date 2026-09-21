"""K=1 exact one-sided McNemar executor for the M9 analysis (M9-C5 / P2, §3.5.5).

The frozen K=1 statistical primitive: for an adjacent-arm comparison ``X > Y`` over paired
binary endpoints, compute the exact one-sided McNemar p-value.

Over the shared task set, the discordant counts are:

* ``x = count(X = 1, Y = 0)`` — evidence for ``X > Y``;
* ``y = count(X = 0, Y = 1)``;
* ``discordant = x + y``.

Conditional on ``discordant``, under the null the number of x-type discordances is
``Binomial(discordant, 0.5)``; the one-sided p-value for the alternative
``P(X_pass) > P(Y_pass)`` is ``p = P(B >= x) = sum_{i=x}^{discordant} C(discordant, i) *
0.5**discordant``, computed **exactly** from integer binomial coefficients — no continuity
correction, no normal/chi-square approximation, no two-sided-halving. If ``discordant == 0``,
``p = 1.0`` (§3.5.5).

Scope (handoff §4.7): C5 owns **only** this exact-McNemar computation over the canonical C4
:class:`~velith.analysis.binder.Observation` set. It does **not** apply Holm-Bonferroni
(``holm.py``, §4.11), reach a GO/NO-GO decision (``decision.py``, §4.12), orchestrate the two
K=1 comparisons, classify completeness (C3, §3.5.1), or run any GEE/EMM/trend (K>1). The
caller supplies the ``(superior, reference)`` arm pair; the executor returns one comparison's
exact result.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from velith.analysis.binder import Observation
from velith.arms.identity import Arm

_ARM_VALUES: frozenset[str] = frozenset(arm.value for arm in Arm)


class McNemarError(Exception):
    """Raised on a structural/data-integrity failure preparing the K=1 McNemar input."""


@dataclass(frozen=True)
class McNemarResult:
    """The exact one-sided McNemar outcome for one adjacent-arm comparison (X = superior)."""

    superior_arm: str
    reference_arm: str
    x: int
    y: int
    discordant: int
    p_value: float


def _paired_endpoints(
    observations: Iterable[Observation], superior_arm: str, reference_arm: str
) -> tuple[dict[str, int], dict[str, int]]:
    """Collect ``task -> endpoint`` for the two arms, validating the K=1 structural contract."""
    superior: dict[str, int] = {}
    reference: dict[str, int] = {}
    for obs in observations:
        if obs.arm == superior_arm:
            target = superior
        elif obs.arm == reference_arm:
            target = reference
        else:
            continue
        if obs.endpoint not in (0, 1):
            raise McNemarError(
                f"non-binary endpoint {obs.endpoint!r} for task {obs.task_identity!r}"
            )
        if obs.checkpoint_index not in (None, 1):
            raise McNemarError(
                "K=1 McNemar received a K>1 observation "
                f"(checkpoint_index={obs.checkpoint_index!r}) for task {obs.task_identity!r}"
            )
        if obs.task_identity in target:
            raise McNemarError(f"duplicate {obs.arm} observation for task {obs.task_identity!r}")
        target[obs.task_identity] = obs.endpoint
    return superior, reference


def mcnemar_test(
    observations: Iterable[Observation], *, superior_arm: str, reference_arm: str
) -> McNemarResult:
    """Exact one-sided McNemar p-value for ``superior_arm`` > ``reference_arm`` (§3.5.5).

    Requires the superior and reference arms to cover the **same** task set (complete pairs);
    completeness/complete-case is C3's responsibility, so an incomplete pairing raises rather
    than being silently classified. Deterministic: the result is a pure function of the
    endpoints.
    """
    if superior_arm not in _ARM_VALUES:
        raise McNemarError(f"unknown superior arm: {superior_arm!r}")
    if reference_arm not in _ARM_VALUES:
        raise McNemarError(f"unknown reference arm: {reference_arm!r}")
    if superior_arm == reference_arm:
        raise McNemarError(f"superior and reference arms must differ: {superior_arm!r}")

    superior, reference = _paired_endpoints(observations, superior_arm, reference_arm)
    if superior.keys() != reference.keys():
        raise McNemarError(
            "superior and reference arms do not cover the same task set (incomplete pairs); "
            "completeness/complete-case is C3's responsibility, not C5's"
        )

    x = sum(1 for task in superior if superior[task] == 1 and reference[task] == 0)
    y = sum(1 for task in superior if superior[task] == 0 and reference[task] == 1)
    discordant = x + y
    if discordant == 0:
        p_value = 1.0
    else:
        tail = sum(math.comb(discordant, i) for i in range(x, discordant + 1))
        p_value = tail / (2**discordant)
    return McNemarResult(superior_arm, reference_arm, x, y, discordant, p_value)
