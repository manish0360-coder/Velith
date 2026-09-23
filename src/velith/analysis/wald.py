"""Frozen one-sided Wald inference for the M9 analysis (M9-C10 / P2, spec §3.5.4).

This module turns one C9 EMM contrast into its pre-registered one-sided test statistic and
p-value. It is a pure, total transformation ``EmmResult -> WaldResult``.

**The frozen test (spec §3.5.4).** For the EMM superiority estimand::

    Z = EMM_diff / SE(EMM_diff)
    p = 1 - Phi(Z)

the alternative being ``EMM_diff > 0``. The upper-tail probability is taken from the
**survival function** ``norm.sf`` rather than ``1 - norm.cdf``: the two agree
mathematically, but ``1 - cdf`` loses all significant digits in the far upper tail where
``cdf`` rounds to ``1.0``, and the frozen procedure compares p-values against thresholds as
small as ``0.01/4``. No manual series expansion or approximation is used.

**Zero standard error.** C9 emits ``SE = 0.0`` faithfully when every ``d_a(k)`` underflows
in a saturated regime; ``Z`` is then not defined by division. The frozen disposition is
applied by exact case rather than by computing ``0/0``:

======================  ==========  ===========
condition               ``z_stat``  ``p_value``
======================  ==========  ===========
``SE = 0, delta > 0``   ``+inf``    ``0.0``
``SE = 0, delta = 0``   ``0.0``     ``1.0``
``SE = 0, delta < 0``   ``-inf``    ``1.0``
======================  ==========  ===========

No epsilon, no minimum-SE threshold, no clipping, no ``abs()``, and no numerical
correction is applied anywhere: a tiny-but-positive ``SE`` takes the ordinary
``delta / se`` path unchanged.

**Boundary.** C10 computes a single statistic and a single p-value. It performs **no**
Holm correction, **no** p-value adjustment, **no** hypothesis ranking, **no** GO/NO-GO
decision, and **no** GEE failure reclassification; it reads **no** GeeFit, observation,
binder, completeness, pre-registration, sink, memory, or runner surface. Multiplicity
belongs to the frozen Holm executor and the decision belongs to the decision executor.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.stats import norm

from velith.analysis.emm import EmmResult


class InferenceError(Exception):
    """Raised on a structural/invariant failure in the Wald transformation.

    A loud halt for malformed input. It is **not** a statistical outcome and never carries
    an inferential disposition: the frozen §3.5.7 failure set belongs to C8, and GO/NO-GO
    belongs to the decision executor.
    """


@dataclass(frozen=True)
class WaldResult:
    """The frozen one-sided Wald statistic and p-value for one EMM contrast.

    ``delta_emm`` and ``se_emm`` are echoed through unmodified so the statistic is
    reproducible from the result alone. Carries no Holm rank, no adjusted p-value, and no
    decision.
    """

    delta_emm: float
    se_emm: float
    z_stat: float
    p_value: float


def compute_wald(emm: EmmResult) -> WaldResult:
    """Compute the frozen one-sided Wald test for one C9 EMM contrast.

    Pure function of ``emm``: identical input yields an identical result. Raises
    :class:`InferenceError` if the EMM difference or standard error is non-finite, or if
    the standard error is negative.
    """
    delta_emm = emm.emm_difference
    se_emm = emm.standard_error

    if not math.isfinite(delta_emm):
        raise InferenceError(f"emm_difference must be finite, got {delta_emm!r}")
    if not math.isfinite(se_emm):
        raise InferenceError(f"standard_error must be finite, got {se_emm!r}")
    if se_emm < 0.0:
        raise InferenceError(f"standard_error must be non-negative, got {se_emm!r}")

    if se_emm > 0.0:
        # The ordinary rule, applied at every positive SE however small: no threshold,
        # no floor, no clipping. A tiny SE legitimately yields a very large |Z|.
        z_stat = delta_emm / se_emm
        p_value = float(norm.sf(z_stat))
    elif delta_emm > 0.0:
        z_stat = math.inf
        p_value = 0.0
    elif delta_emm < 0.0:
        z_stat = -math.inf
        p_value = 1.0
    else:
        z_stat = 0.0
        p_value = 1.0

    return WaldResult(
        delta_emm=delta_emm,
        se_emm=se_emm,
        z_stat=z_stat,
        p_value=p_value,
    )
