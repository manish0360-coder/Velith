"""Frozen response-scale EMM for the M9 analysis (M9-C9 / P2 item 9, spec §3.5.4, handoff §6).

This module computes the **Estimated Marginal Mean difference on the response scale** and
its **analytic first-order delta-method standard error** for one adjacent-arm comparison.
It is a pure, total transformation ``GeeFit -> EmmResult``.

It computes **no** Z statistic, **no** p-value, **no** Holm correction, **no** GO/NO-GO, and
**no** failure classification; it reads **no** observation, record, binder, completeness,
pre-registration, sink, memory, or runner surface. Those belong to other milestones.

**The estimand (spec §3.5.4, frozen).** Both arms are evaluated over the *same*
pre-registered checkpoint grid, and the inverse-logit is applied **before** averaging::

    EMM_a    = (1/K) * sum_{k=1..K} sigma(eta_a(x_k))
    EMM_diff = EMM_treatment - EMM_reference

Response-scale averaging is not interchangeable with linear-predictor averaging:
``mean(sigma(eta_k)) != sigma(mean(eta_k))`` whenever ``b_checkpoint != 0``, because sigma
is nonlinear (Jensen). The centered-grid identity ``mean(x_k) = 0`` therefore does **not**
collapse this estimand to an evaluation at ``x = 0``, and does **not** reduce the gradient
to a constant contrast vector such as ``[0, 0, 1]``. Both collapses are forbidden.

**A0 (RD ruling, Interpretation A).** OED-2's single observed A0 row at
``checkpoint_id_c = 0`` describes the **fitted design data**; it does not restrict
evaluation of the fitted regression surface to ``x = 0``. The frozen EMM formula explicitly
indexes ``p_hat(arm=0, checkpoint=k)``, and frozen handoff §6 declares
``eta(a, x_k) = b0 + b_checkpoint*x_k + b_arm*a``, so A0 is evaluated at every
pre-registered ``x_k``. The §3.5.4 phrase "while A0 stays constant" is descriptive
experimental-design prose attached to the *trend* estimand, not the operative EMM
definition.

**Determinism (handoff §7).** The grid is traversed in the frozen schedule order
``k = 1..K`` as published by ``GeeFit.checkpoint_values``; every sum accumulates in that
fixed order; the quadratic form is evaluated in fixed index order. No numpy, no randomness,
no external state — pure Python arithmetic end to end.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from velith.analysis.gee import DESIGN_COLUMNS, Comparison, GeeFit


class EmmError(Exception):
    """Raised on a structural/invariant failure in the EMM transformation.

    A loud halt for malformed input or a violated upstream invariant. It is **not** a
    statistical outcome and never carries an inferential disposition: the frozen §3.5.7
    failure set belongs to C8, and GO/NO-GO belongs to C7/C10.
    """


def inverse_logit(eta: float) -> float:
    """Overflow-safe inverse-logit ``sigma(eta) = 1 / (1 + e^-eta)`` (handoff §7).

    The branch on the sign of ``eta`` is exact and parameter-free: it exists only so that
    ``exp`` is never evaluated on a large positive argument. It introduces no tolerance,
    threshold, or tunable constant.

    Natural IEEE-754 saturation to exactly ``0.0`` or ``1.0`` for large ``|eta|`` is
    expected and deliberately **not** clamped, floored, or epsilon-adjusted; the frozen
    plan authorizes no such constant, and inventing one would be a researcher degree of
    freedom (§3.5.10).
    """
    if eta >= 0.0:
        return 1.0 / (1.0 + math.exp(-eta))
    exp_eta = math.exp(eta)
    return exp_eta / (1.0 + exp_eta)


@dataclass(frozen=True)
class EmmResult:
    """The frozen response-scale EMM contrast for one adjacent-arm comparison.

    ``gradient`` is published because handoff §10 requires the analytic gradient itself to
    be verifiable against an independent derivation, and because it is the deterministic
    provenance of ``standard_error``. It is not an additional estimand.

    Carries no Z, no p-value, and no decision: those are downstream (C10).
    """

    comparison: Comparison
    design_columns: tuple[str, ...]
    checkpoint_count: int
    emm_treatment: float
    emm_reference: float
    emm_difference: float
    gradient: tuple[float, ...]
    standard_error: float


def _mean(values: Sequence[float]) -> float:
    """``(1/K) * sum(values)`` accumulated in the caller's fixed order.

    Division by ``K`` is used rather than multiplication by a precomputed ``1/K``: the two
    agree as real numbers, and division carries a single correctly-rounded operation where
    reciprocal-then-multiply carries two. Pinned here so every EMM term uses one reduction.
    """
    total = 0.0
    for value in values:
        total += value
    return total / len(values)


def _linear_predictor(params: tuple[float, ...], *, x: float, arm: float) -> float:
    """The frozen linear predictor ``eta(a, x_k)`` (handoff §6), bound positionally.

    A1 vs A0 (additive)    : ``b0 + b_checkpoint*x + b_arm*a``
    A2 vs A1 (interaction) : ``b0 + b_checkpoint*x + b_arm*a + b_interaction*(x*a)``

    The caller has already asserted ``design_columns``, so the positional binding of
    ``params`` to ``(intercept, checkpoint_id_c, arm[, checkpoint_id_c:arm])`` is verified
    rather than assumed.
    """
    eta = params[0] + params[1] * x + params[2] * arm
    if len(params) == 4:
        eta += params[3] * (x * arm)
    return eta


def _quadratic_form(
    gradient: tuple[float, ...], cov_robust: tuple[tuple[float, ...], ...]
) -> float:
    """``g^T V g`` over the **complete** covariance, evaluated in fixed index order.

    Every off-diagonal term participates: a diagonal-only or arm-block-only reduction is a
    different quantity and is forbidden (handoff §6).
    """
    total = 0.0
    for i, g_i in enumerate(gradient):
        row = cov_robust[i]
        for j, g_j in enumerate(gradient):
            total += g_i * row[j] * g_j
    return total


def _validate(fit: GeeFit) -> tuple[str, ...]:
    """Structural validation of the incoming fit; returns the expected design columns.

    Shape and binding only. Statistical invariants established by C8 — convergence and a
    positive-definite robust covariance — are relied upon rather than re-litigated here
    (handoff §10); this module introduces no statistical policy of its own.
    """
    expected = DESIGN_COLUMNS.get(fit.comparison)
    if expected is None:
        raise EmmError(f"unknown comparison: {fit.comparison!r}")
    if fit.design_columns != expected:
        raise EmmError(
            f"design_columns {fit.design_columns!r} do not match the frozen order "
            f"{expected!r} for comparison {fit.comparison.value}"
        )
    width = len(expected)
    if len(fit.params) != width:
        raise EmmError(
            f"expected {width} coefficients for {fit.comparison.value}, got {len(fit.params)}"
        )
    if len(fit.cov_robust) != width or any(len(row) != width for row in fit.cov_robust):
        raise EmmError(
            f"cov_robust must be {width}x{width} for {fit.comparison.value}; "
            f"got {len(fit.cov_robust)} rows"
        )
    if len(fit.checkpoint_values) < 2:
        raise EmmError(
            "EMM is the K>1 procedure; checkpoint_values must carry at least 2 "
            f"positions, got {len(fit.checkpoint_values)}"
        )
    if not all(math.isfinite(value) for value in fit.params):
        raise EmmError(f"non-finite coefficient in params: {fit.params!r}")
    if not all(math.isfinite(value) for row in fit.cov_robust for value in row):
        raise EmmError("non-finite entry in cov_robust")
    if not all(math.isfinite(value) for value in fit.checkpoint_values):
        raise EmmError(f"non-finite checkpoint value: {fit.checkpoint_values!r}")
    return expected


def compute_emm(fit: GeeFit) -> EmmResult:
    """Compute the frozen response-scale EMM difference and its delta-method SE.

    Pure function of ``fit``: identical input yields an identical result. Raises
    :class:`EmmError` on malformed input or a violated upstream invariant.

    A zero standard error is returned as exactly ``0.0`` and is **not** converted into a
    failure: in saturated regimes every ``d_a(k)`` may underflow to zero, making the
    gradient the zero vector. Detecting that regime is neither C9's estimand nor C9's
    failure set; it is the caller's concern (C10).
    """
    expected = _validate(fit)
    checkpoint_values = fit.checkpoint_values
    params = fit.params

    # Both arms are evaluated over the SAME pre-registered grid (RD ruling, Interpretation
    # A). Treatment is the arm = 1 level and reference the arm = 0 level, per the frozen
    # treatment coding (A0=0/A1=1 for A1vA0; A1=0/A2=1 for A2vA1).
    p_treatment: list[float] = []
    p_reference: list[float] = []
    for x in checkpoint_values:
        p_treatment.append(inverse_logit(_linear_predictor(params, x=x, arm=1.0)))
        p_reference.append(inverse_logit(_linear_predictor(params, x=x, arm=0.0)))

    # Response-scale averaging: transform first, then average. Never sigma(mean(eta)).
    emm_treatment = _mean(p_treatment)
    emm_reference = _mean(p_reference)
    emm_difference = emm_treatment - emm_reference

    # Chain rule through the logit link: d_a(k) = p_a(k) * (1 - p_a(k)).
    d_treatment = [p * (1.0 - p) for p in p_treatment]
    d_reference = [p * (1.0 - p) for p in p_reference]
    d_diff = [dt - dr for dt, dr in zip(d_treatment, d_reference, strict=True)]

    # Analytic gradient of EMM_diff w.r.t. the COMPLETE coefficient vector (handoff §6),
    # entry-by-entry in design_columns order. Finite differences are forbidden.
    gradient_entries = [
        _mean(d_diff),
        _mean([d * x for d, x in zip(d_diff, checkpoint_values, strict=True)]),
        _mean(d_treatment),
    ]
    if fit.comparison is Comparison.A2_VS_A1:
        gradient_entries.append(
            _mean([d * x for d, x in zip(d_treatment, checkpoint_values, strict=True)])
        )
    gradient = tuple(gradient_entries)

    quadratic_form = _quadratic_form(gradient, fit.cov_robust)
    if quadratic_form < 0.0:
        # C8 guarantees a positive-definite robust covariance on the success path, so
        # g^T V g is mathematically non-negative. A negative value means that invariant was
        # violated upstream. It is surfaced, never repaired by max(0, q) or abs(q):
        # clamping would fabricate a standard error out of an invalid covariance.
        raise EmmError(
            f"invariant violated: g^T V_robust g = {quadratic_form!r} is negative for "
            f"{fit.comparison.value}; the robust covariance is not positive semi-definite"
        )
    standard_error = math.sqrt(quadratic_form)

    return EmmResult(
        comparison=fit.comparison,
        design_columns=expected,
        checkpoint_count=len(checkpoint_values),
        emm_treatment=emm_treatment,
        emm_reference=emm_reference,
        emm_difference=emm_difference,
        gradient=gradient,
        standard_error=standard_error,
    )
