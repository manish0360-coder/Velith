"""Frozen gap-widens trend tests for the M9 analysis (M9-C11 / P2 item 10, spec §3.5.4).

This module turns one C8 ``GeeFit`` into the frozen one-sided Wald test on that
comparison's **trend coefficient**. It is a pure transformation ``GeeFit -> TrendResult``.

**The estimands (spec §3.5.4, semantic lock).** "Gap widens" is defined exclusively on the
model's log-odds-ratio scale:

* **A1 vs A0 (additive):** the ``checkpoint_id_c`` coefficient ``beta_checkpoint`` — the
  per-unit-checkpoint change in log-odds; alternative ``beta_checkpoint > 0``.
* **A2 vs A1 (interaction):** the ``checkpoint_id_c:arm`` coefficient ``beta_interaction``
  — the difference in learning rate between A2 and A1; alternative ``beta_interaction >= 0``.

Neither asserts that the raw probability difference is non-decreasing. Both alternatives
are upper-tailed, so both take the identical one-sided statistic ``Z = beta / SE(beta)``,
``p = 1 - Phi(Z)``; the ``> 0`` versus ``>= 0`` wording does not change the computation.

**Reuse, not duplication.** The arithmetic is not reimplemented here: it is delegated to
``wald.one_sided_wald``, the single implementation of the frozen one-sided Wald rule shared
with the C10 EMM tests. Its zero-SE disposition and validation apply unchanged.

**Standard error.** ``SE(beta) = sqrt(V_robust[i][i])`` taken from the **robust sandwich**
covariance of the same fitted GEE; model-based standard errors are never used (§3.5.3).
The index ``i`` is resolved **by design-column name** against the frozen ``DESIGN_COLUMNS``
order, which is asserted first, so the binding is never a bare positional assumption.

**Boundary.** No Holm, no multiplicity, no GO/NO-GO, no EMM, no model refitting, and no
reclassification of a valid ``GeeFit``. Separation, parameter magnitude, tiny SE, and
p-value magnitude are **not** inspected here: a ``GeeFit`` that satisfies the literal frozen
§3.5.7 predicates is authoritative and is consumed normally.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from velith.analysis.gee import DESIGN_COLUMNS, Comparison, GeeFit
from velith.analysis.wald import one_sided_wald

#: The frozen trend coefficient per comparison (§3.5.4), named by its design column so the
#: coefficient is bound by name rather than by a bare index.
TREND_COLUMNS: Final[dict[Comparison, str]] = {
    Comparison.A1_VS_A0: "checkpoint_id_c",
    Comparison.A2_VS_A1: "checkpoint_id_c:arm",
}


class TrendError(Exception):
    """Raised on a structural/invariant failure in the trend transformation.

    A loud halt for a malformed fit or a violated upstream invariant. It is **not** a
    statistical outcome: the frozen §3.5.7 failure set belongs to C8, and GO/NO-GO to the
    decision executor. Non-finite or negative-SE *numeric* inputs surface as
    :class:`velith.analysis.wald.InferenceError` from the shared primitive.
    """


@dataclass(frozen=True)
class TrendResult:
    """The frozen one-sided Wald test on one comparison's trend coefficient.

    ``estimate`` and ``standard_error`` are echoed through so the statistic is reproducible
    from the result alone. Carries no Holm rank, no adjusted p-value, and no decision.
    """

    comparison: Comparison
    coefficient_name: str
    estimate: float
    standard_error: float
    z_stat: float
    p_value: float


def compute_trend(fit: GeeFit) -> TrendResult:
    """Compute the frozen gap-widens trend test for one fitted comparison.

    Pure function of ``fit``: identical input yields an identical result. Raises
    :class:`TrendError` on a malformed fit or a violated upstream invariant.
    """
    trend_column = TREND_COLUMNS.get(fit.comparison)
    if trend_column is None:
        raise TrendError(f"unknown comparison: {fit.comparison!r}")

    expected_columns = DESIGN_COLUMNS[fit.comparison]
    if fit.design_columns != expected_columns:
        raise TrendError(
            f"design_columns {fit.design_columns!r} do not match the frozen "
            f"order {expected_columns!r} for {fit.comparison.value}"
        )
    width = len(expected_columns)
    if len(fit.params) != width:
        raise TrendError(f"expected {width} coefficients, got {len(fit.params)}")
    if len(fit.cov_robust) != width or any(len(row) != width for row in fit.cov_robust):
        raise TrendError(f"cov_robust must be {width}x{width}, got {len(fit.cov_robust)} rows")

    index = expected_columns.index(trend_column)
    estimate = fit.params[index]
    variance = fit.cov_robust[index][index]
    if not math.isfinite(variance):
        raise TrendError(f"non-finite robust variance for {trend_column!r}: {variance!r}")
    if variance < 0.0:
        # C8 guarantees a positive-definite robust covariance on the success path, so a
        # negative variance means that invariant was violated upstream. Surfaced, never
        # repaired: clamping would fabricate a standard error from an invalid covariance.
        raise TrendError(
            f"invariant violated: robust variance for {trend_column!r} is negative "
            f"({variance!r}); the robust covariance is not positive semi-definite"
        )

    standard_error = math.sqrt(variance)
    z_stat, p_value = one_sided_wald(estimate, standard_error, estimate_name=trend_column)
    return TrendResult(
        comparison=fit.comparison,
        coefficient_name=trend_column,
        estimate=estimate,
        standard_error=standard_error,
        z_stat=z_stat,
        p_value=p_value,
    )
