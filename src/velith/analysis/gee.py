"""Frozen K>1 GEE fit for the M9 analysis (M9-C8 / P2 item 8, spec §3.5.3, handoff §6-§7).

This module is the **typed adapter** isolating ``statsmodels`` behind a frozen result value
(handoff OED-6). It does exactly one thing: build the pre-registered explicit design matrix
for one adjacent-arm comparison and fit the frozen GEE over it.

It computes **no** EMM (C9), **no** trend p-value (C10), **no** Holm correction (C6), and
**no** GO/NO-GO (C7) — it surfaces the fitted coefficient vector, the robust sandwich
covariance, and the typed §3.5.7 failure state those layers consume.

Frozen construction (spec §3.5.3, handoff §6/OED-4):

* family ``Binomial`` with the **logit** link; working correlation ``Exchangeable``;
  ``task_id`` as the group identifier; **robust sandwich** covariance
  (``cov_type='robust'``) — model-based standard errors are never used.
* Solver: ``maxiter=100``, ``ctol=1e-8``, ``start_params=None``.
* ``checkpoint_id_c`` is the ordered checkpoint index ``1..K`` mean-centered by
  subtracting ``(K+1)/2``.
* ``arm`` is treatment coded (A1 vs A0: A0=0, A1=1; A2 vs A1: A1=0, A2=1).
* **A0 is time-invariant (OED-2):** exactly **one** A0 row per task at
  ``checkpoint_id_c = 0``, **never** replicated across the K checkpoints.
* Two distinct model formulas (OED-2, frozen): A1 vs A0 is **additive**
  ``verdict ~ checkpoint_id_c + arm`` (3-D coefficient vector); A2 vs A1 carries the
  interaction ``verdict ~ checkpoint_id_c + arm + checkpoint_id_c * arm`` (4-D).

The statsmodels **array API** is used exclusively (numpy ``endog``/``exog``/``groups``); no
formula string, patsy, or formulaic appears at the call site, so the design-matrix column
order is fixed here rather than by a library parser (handoff OED-4). The column order is
published as :attr:`GeeFit.design_columns` so the downstream analytic EMM gradient (handoff
§6) can be mapped entry-by-entry onto the fitted coefficient vector.

Determinism (handoff §7/OED-5): the thread and hash environment is established by the pinned
image and is only **recorded** here, never set. Row order materially affects the fit at
machine precision, so rows are emitted in a single deterministic order and task groups are
mapped to contiguous integer codes in sorted task order.
"""

from __future__ import annotations

import math
import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Final

import numpy as np
import statsmodels
from statsmodels.genmod.cov_struct import Exchangeable
from statsmodels.genmod.families import Binomial
from statsmodels.genmod.generalized_estimating_equations import GEE

from velith.analysis.binder import Observation
from velith.arms.identity import Arm

#: Frozen solver configuration (spec §3.5.3, handoff §7/OED-4). Not tunable.
MAXITER: Final[int] = 100
CTOL: Final[float] = 1e-8
COV_TYPE: Final[str] = "robust"
FAMILY_NAME: Final[str] = "Binomial"
LINK_NAME: Final[str] = "logit"
COV_STRUCT_NAME: Final[str] = "Exchangeable"

#: The frozen A0 covariate value (OED-2): A0 enters once, at the centered index mean.
A0_CHECKPOINT_ID_C: Final[float] = 0.0

#: Environment variables recorded in provenance (handoff §7/OED-5); never set here.
_RECORDED_ENV: Final[tuple[str, ...]] = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "PYTHONHASHSEED",
)


class GeeError(Exception):
    """Raised on a structural/data-integrity failure in the GEE input (handoff §8).

    A corrupt or malformed design is a loud halt, never an inferential outcome: it is
    distinct from :class:`GeeFailure`, which is the frozen §3.5.7 *statistical* failure
    state and does carry an inferential disposition downstream.
    """


class Comparison(Enum):
    """The two frozen adjacent-arm comparisons (spec §3.5.2), each with its own model."""

    A1_VS_A0 = "A1_VS_A0"
    A2_VS_A1 = "A2_VS_A1"

    @property
    def superior_arm(self) -> str:
        """The treatment-coded ``arm = 1`` level."""
        return Arm.A1.value if self is Comparison.A1_VS_A0 else Arm.A2.value

    @property
    def reference_arm(self) -> str:
        """The treatment-coded ``arm = 0`` level."""
        return Arm.A0.value if self is Comparison.A1_VS_A0 else Arm.A1.value


class GeeFailureReason(Enum):
    """The frozen §3.5.7 failure set. Every member maps downstream to ``p = 1.0``."""

    NON_CONVERGENCE = "NON_CONVERGENCE"
    SINGULAR_ROBUST_COVARIANCE = "SINGULAR_ROBUST_COVARIANCE"
    NON_FINITE_ESTIMATE = "NON_FINITE_ESTIMATE"


#: Explicit design-matrix column order per comparison (handoff §6/OED-4). The analytic EMM
#: gradient is defined entry-by-entry against exactly this order.
DESIGN_COLUMNS: Final[dict[Comparison, tuple[str, ...]]] = {
    Comparison.A1_VS_A0: ("intercept", "checkpoint_id_c", "arm"),
    Comparison.A2_VS_A1: ("intercept", "checkpoint_id_c", "arm", "checkpoint_id_c:arm"),
}


@dataclass(frozen=True)
class SolverProvenance:
    """The recorded computational configuration of one fit (handoff §7/§9).

    Carries no scientific quantity: it exists so the analysis result record can be
    reproduced from the pinned image, and nothing here is an estimand.
    """

    statsmodels_version: str
    numpy_version: str
    family: str
    link: str
    cov_struct: str
    cov_type: str
    maxiter: int
    ctol: float
    start_params: str
    thread_env: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class GeeFit:
    """A successfully fitted frozen GEE (no §3.5.7 failure condition holds).

    ``params`` follows :attr:`design_columns` exactly. ``cov_robust`` is the robust
    sandwich covariance over the same order. ``checkpoint_values`` is the frozen
    mean-centered index ``x_k`` for ``k = 1..K``, published so downstream EMM never
    re-derives the centering.
    """

    comparison: Comparison
    design_columns: tuple[str, ...]
    checkpoint_values: tuple[float, ...]
    params: tuple[float, ...]
    cov_robust: tuple[tuple[float, ...], ...]
    n_tasks: int
    n_observations: int
    converged: bool
    provenance: SolverProvenance


@dataclass(frozen=True)
class GeeFailure:
    """A frozen §3.5.7 model failure. Downstream defines this model's two p-values as 1.0."""

    comparison: Comparison
    reason: GeeFailureReason
    detail: str
    n_tasks: int
    n_observations: int
    provenance: SolverProvenance


@dataclass(frozen=True)
class GeeDesign:
    """The explicit design handed to the solver (handoff OED-4: array API, no formula).

    Materialized as its own value so the frozen construction — column order, treatment
    coding, mean-centering, and the single non-replicated A0 row — is directly verifiable
    rather than buried inside the fit call.
    """

    comparison: Comparison
    columns: tuple[str, ...]
    checkpoint_values: tuple[float, ...]
    endog: tuple[float, ...]
    exog: tuple[tuple[float, ...], ...]
    groups: tuple[int, ...]
    task_identities: tuple[str, ...]


def centered_checkpoint_values(checkpoint_count: int) -> tuple[float, ...]:
    """The frozen mean-centered checkpoint covariate ``x_k = k - (K+1)/2`` for ``k=1..K``.

    Published as the single definition of the centering so no downstream module re-derives
    it (handoff §6/§7 "deterministic, pinned").
    """
    if checkpoint_count < 1:
        raise GeeError(f"checkpoint_count must be >= 1, got {checkpoint_count}")
    mean_index = (checkpoint_count + 1) / 2
    return tuple(float(k) - mean_index for k in range(1, checkpoint_count + 1))


def _provenance() -> SolverProvenance:
    return SolverProvenance(
        statsmodels_version=str(statsmodels.__version__),
        numpy_version=str(np.__version__),
        family=FAMILY_NAME,
        link=LINK_NAME,
        cov_struct=COV_STRUCT_NAME,
        cov_type=COV_TYPE,
        maxiter=MAXITER,
        ctol=CTOL,
        start_params="None",
        thread_env=tuple((name, os.environ.get(name, "unset")) for name in _RECORDED_ENV),
    )


def classify_failure(
    *,
    converged: bool,
    params: Sequence[float],
    cov_robust: Sequence[Sequence[float]],
) -> GeeFailureReason | None:
    """Apply the frozen §3.5.7 failure set to one fitted model; ``None`` means usable.

    The three conditions are evaluated in the only order that is well defined: a model that
    did not converge has no trustworthy estimates to inspect, and a matrix carrying
    non-finite entries cannot be meaningfully tested for singularity. The ordering carries
    **no inferential weight** — §3.5.7 assigns all three the identical disposition
    (``p = 1.0``), so which member is reported changes the recorded reason only.

    "Singular" is applied as *not numerically positive definite*, decided by a Cholesky
    factorization. This is the parameter-free reading: it introduces no rank tolerance,
    condition-number cutoff, or any other tunable that would be a researcher degree of
    freedom (§3.5.10). A negative covariance diagonal is reported as a non-finite estimate
    because the standard error it implies, ``sqrt(V_ii)``, is not finite.
    """
    if not converged:
        return GeeFailureReason.NON_CONVERGENCE
    if not all(math.isfinite(value) for value in params):
        return GeeFailureReason.NON_FINITE_ESTIMATE
    if not all(math.isfinite(value) for row in cov_robust for value in row):
        return GeeFailureReason.NON_FINITE_ESTIMATE
    if any(row[index] < 0.0 for index, row in enumerate(cov_robust)):
        return GeeFailureReason.NON_FINITE_ESTIMATE
    try:
        np.linalg.cholesky(np.asarray(cov_robust, dtype=np.float64))
    except np.linalg.LinAlgError:
        return GeeFailureReason.SINGULAR_ROBUST_COVARIANCE
    return None


def _design_row(
    comparison: Comparison, *, is_superior: bool, checkpoint_id_c: float
) -> tuple[float, ...]:
    """One explicit design-matrix row, in :data:`DESIGN_COLUMNS` order."""
    arm = 1.0 if is_superior else 0.0
    if comparison is Comparison.A1_VS_A0:
        return (1.0, checkpoint_id_c, arm)
    return (1.0, checkpoint_id_c, arm, checkpoint_id_c * arm)


def _validate_and_order(
    observations: Iterable[Observation], comparison: Comparison, checkpoint_count: int
) -> tuple[Observation, ...]:
    """Validate the balanced design and return the rows in a single deterministic order.

    This is **design-matrix well-formedness**, not the §3.5.1 completeness rule: C3 decides
    which tasks are included and C4 performs the record join. C8 only refuses to fit a
    design it cannot construct — a malformed design is a loud halt (handoff §8), never a
    silently dropped row and never an inferential outcome.
    """
    superior, reference = comparison.superior_arm, comparison.reference_arm
    reference_is_time_invariant = comparison is Comparison.A1_VS_A0
    cells: dict[tuple[str, str, int | None], Observation] = {}
    for observation in observations:
        if observation.arm not in (superior, reference):
            raise GeeError(
                f"observation arm {observation.arm!r} is outside comparison {comparison.value} "
                f"({reference!r} vs {superior!r}); the caller must partition by comparison"
            )
        if observation.endpoint not in (0, 1):
            raise GeeError(
                f"endpoint must be the binary 0/1 encoding, got {observation.endpoint!r} "
                f"for task {observation.task_identity!r}"
            )
        index = observation.checkpoint_index
        is_time_invariant_row = reference_is_time_invariant and observation.arm == reference
        if is_time_invariant_row:
            if index is not None:
                raise GeeError(
                    "A0 is time-invariant (OED-2) and must carry checkpoint_index None, got "
                    f"{index!r} for task {observation.task_identity!r} — A0 is never "
                    "replicated across the checkpoint schedule"
                )
        elif index is None or not 1 <= index <= checkpoint_count:
            raise GeeError(
                f"checkpoint_index {index!r} is outside the pre-registered schedule "
                f"1..{checkpoint_count} for arm {observation.arm!r}, task "
                f"{observation.task_identity!r}"
            )
        key = (observation.task_identity, observation.arm, index)
        if key in cells:
            raise GeeError(f"duplicate observation for design cell {key}")
        cells[key] = observation

    if not cells:
        raise GeeError("no observations supplied; the GEE design is empty")

    tasks = sorted({task for task, _, _ in cells})
    for task in tasks:
        for arm in (reference, superior):
            expected: tuple[int | None, ...] = (
                (None,)
                if reference_is_time_invariant and arm == reference
                else tuple(range(1, checkpoint_count + 1))
            )
            missing = [index for index in expected if (task, arm, index) not in cells]
            if missing:
                raise GeeError(
                    f"unbalanced design: task {task!r} arm {arm!r} is missing checkpoint "
                    f"indices {missing}: complete-case exclusion (spec 3.5.1) is C3's "
                    "responsibility and must be applied before fitting"
                )
    return tuple(
        cells[key]
        for key in sorted(cells, key=lambda k: (k[0], k[1], -1 if k[2] is None else k[2]))
    )


def build_design(
    observations: Iterable[Observation],
    *,
    comparison: Comparison,
    checkpoint_count: int,
) -> GeeDesign:
    """Build the frozen explicit design matrix for one adjacent-arm comparison.

    ``checkpoint_count`` is ``K`` read from the pre-registered schedule and passed in
    explicitly: the design is never inferred from the observed data, so a truncated record
    set cannot silently re-center the covariate. K=1 is rejected — the frozen procedure
    routes it to the exact McNemar path (§3.5.5), never to GEE.
    """
    if checkpoint_count < 2:
        raise GeeError(
            f"GEE is the K>1 procedure; checkpoint_count={checkpoint_count} must route to the "
            "frozen K=1 exact McNemar path (spec 3.5.5)"
        )
    ordered = _validate_and_order(observations, comparison, checkpoint_count)
    checkpoint_values = centered_checkpoint_values(checkpoint_count)
    task_identities = tuple(sorted({o.task_identity for o in ordered}))
    task_codes = {task: code for code, task in enumerate(task_identities)}
    return GeeDesign(
        comparison=comparison,
        columns=DESIGN_COLUMNS[comparison],
        checkpoint_values=checkpoint_values,
        endog=tuple(float(o.endpoint) for o in ordered),
        exog=tuple(
            _design_row(
                comparison,
                is_superior=o.arm == comparison.superior_arm,
                checkpoint_id_c=(
                    A0_CHECKPOINT_ID_C
                    if o.checkpoint_index is None
                    else checkpoint_values[o.checkpoint_index - 1]
                ),
            )
            for o in ordered
        ),
        groups=tuple(task_codes[o.task_identity] for o in ordered),
        task_identities=task_identities,
    )


def fit_gee(
    observations: Iterable[Observation],
    *,
    comparison: Comparison,
    checkpoint_count: int,
) -> GeeFit | GeeFailure:
    """Fit the frozen K>1 GEE for one adjacent-arm comparison (spec §3.5.3).

    Returns :class:`GeeFit` when no §3.5.7 condition holds, otherwise
    :class:`GeeFailure`. A malformed design raises :class:`GeeError` instead — that is
    corrupt input, not a statistical failure.
    """
    design = build_design(observations, comparison=comparison, checkpoint_count=checkpoint_count)
    provenance = _provenance()
    n_tasks, n_observations = len(design.task_identities), len(design.endog)

    try:
        fitted = GEE(
            np.asarray(design.endog, dtype=np.float64),
            np.asarray(design.exog, dtype=np.float64),
            np.asarray(design.groups, dtype=np.int64),
            family=Binomial(),
            cov_struct=Exchangeable(),
        ).fit(maxiter=MAXITER, ctol=CTOL, start_params=None, cov_type=COV_TYPE)
        params: tuple[float, ...] = tuple(float(value) for value in fitted.params)
        cov_robust: tuple[tuple[float, ...], ...] = tuple(
            tuple(float(value) for value in row) for row in fitted.cov_robust
        )
        converged = bool(fitted.converged)
    except Exception as exc:
        # A fit that terminates in an exception produced no estimates, so it has not
        # converged; it is reported inside the frozen §3.5.7 failure set. This is
        # the conservative direction — the disposition is p=1.0, which can only ever yield
        # NO-GO and can never manufacture a GO.
        return GeeFailure(
            comparison=comparison,
            reason=GeeFailureReason.NON_CONVERGENCE,
            detail=f"{type(exc).__name__}: {exc}",
            n_tasks=n_tasks,
            n_observations=n_observations,
            provenance=provenance,
        )

    reason = classify_failure(converged=converged, params=params, cov_robust=cov_robust)
    if reason is not None:
        return GeeFailure(
            comparison=comparison,
            reason=reason,
            detail=f"frozen spec 3.5.7 condition met: {reason.value}",
            n_tasks=n_tasks,
            n_observations=n_observations,
            provenance=provenance,
        )
    return GeeFit(
        comparison=comparison,
        design_columns=design.columns,
        checkpoint_values=design.checkpoint_values,
        params=params,
        cov_robust=cov_robust,
        n_tasks=n_tasks,
        n_observations=n_observations,
        converged=converged,
        provenance=provenance,
    )
