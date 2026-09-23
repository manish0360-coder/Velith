"""M10 held-out analysis executor — orchestration only (M10-C1).

This module **runs** the frozen M9 analysis pipeline against a sealed pre-registration and
the frozen M8 evaluation sink. It introduces **no statistic**: every number it produces
comes from an already-frozen executor that it imports and calls.

It adds no threshold, no effect-size rule, no separation handling, no p-value clipping, no
standard-error floor, and no post-hoc reclassification. It modifies nothing in M8 or M9.

**Pre-flight (before any statistical execution).** The sealed design is verified against the
environment and the observed sink *before* a single statistic is computed:

* the pre-registration's content-addressed integrity (``verify_identity``) — the §3.4 seal
  itself is a structural property of M9-C2 (it imports no sink or record surface, enforced
  by an import-boundary test), not a runtime flag;
* the closed arm set A0/A1/A2;
* a concrete A0 empty-checkpoint identity, distinct from the A1/A2 schedule;
* results-directory segregation from the evaluation sink;
* the pinned single-thread numeric environment;
* ``statsmodels`` only when ``K > 1`` — the frozen K=1 exact McNemar path never fits a GEE
  and must not be coupled to it;
* every observed ``evaluation_identity`` resolving to the reconstructed expected set.

The manifest hash and the checkpoint identities are **not** compared as plaintext, because
neither the sink nor an evaluation record carries them. They are *inputs* to
``EvaluationProvenance.identity``, so resolving observed identities against the
reconstructed expected set is a **cryptographic** check of both: a wrong manifest or a
wrong checkpoint yields a different digest and fails to resolve.

**Structural errors are never analytical outcomes.** A malformed record, a foreign arm, an
unexpected evaluation identity, or a broken invariant raises :class:`ExecutionError` and
writes **no** result record. ``VOID`` is reserved for the two frozen completeness
conditions (§3.5.1 global-incomplete; §3.5.11 ``n = 0``) and is produced by the frozen
decision executors, never fabricated here.

**Read/write boundary.** Reads the sink and the sealed pre-registration; writes only the
segregated results directory through the frozen C12 write-once mechanism. It imports no
episode store, no ``GuardedEpisodeWriter``, and no memory or retrieval surface.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Final

from velith.analysis.binder import Observation, bind_observations
from velith.analysis.completeness import (
    CompletenessResult,
    CompletenessStatus,
    ObservedCell,
    assess_completeness,
)
from velith.analysis.decision import (
    ComparisonPValues,
    DecisionResult,
    build_kgt1_family,
    comparison_label,
    decide_k1,
    decide_kgt1,
)
from velith.analysis.emm import compute_emm
from velith.analysis.gee import Comparison, GeeFailure, GeeFit, SolverProvenance, fit_gee
from velith.analysis.holm import HolmResult, LabeledPValue, holm_bonferroni
from velith.analysis.mcnemar import mcnemar_test
from velith.analysis.preregistration import ARMS, PreRegistration
from velith.analysis.result_record import (
    AnalysisResultRecord,
    build_result_record,
    write_result_record,
)
from velith.analysis.trend import compute_trend
from velith.analysis.wald import compute_wald
from velith.arms.identity import Arm
from velith.evaluation.provenance import EvaluationProvenance
from velith.evaluation.record import EvaluationRecord
from velith.evaluation.sink import EvaluationSink

#: The pinned statistical library and version (M9 handoff OED-3). Checked only on the K>1
#: path, which is the only path that fits a GEE.
REQUIRED_STATSMODELS_VERSION: Final[str] = "0.15.0"

#: The pinned single-thread numeric environment (M9 handoff OED-5). Verified, never set.
REQUIRED_THREAD_ENVIRONMENT: Final[tuple[tuple[str, str], ...]] = (
    ("OMP_NUM_THREADS", "1"),
    ("OPENBLAS_NUM_THREADS", "1"),
    ("MKL_NUM_THREADS", "1"),
    ("PYTHONHASHSEED", "0"),
)

_SHA256_HEX: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")

_MEMORY_ARMS: Final[tuple[str, ...]] = (Arm.A1.value, Arm.A2.value)


class ExecutionError(Exception):
    """Raised on a structural/data-integrity failure in the M10 execution.

    A loud halt: the analysis does not run and **no result record is written**. This is
    never an inferential outcome — GO, NO-GO and VOID are produced only by the frozen
    decision executors from the frozen completeness and Holm inputs.
    """


# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------


def _provenance_identity(
    preregistration: PreRegistration, checkpoint_identity: str, arm: str
) -> str:
    """The frozen join key for one (checkpoint, arm) — handoff §5's only sanctioned key."""
    return EvaluationProvenance(
        checkpoint_identity=checkpoint_identity,
        manifest_hash=preregistration.manifest_hash,
        arm=arm,
        base_model=preregistration.base_model,
        eval_seed=preregistration.eval_seed,
        max_tasks=preregistration.max_tasks,
        max_attempts_per_task=preregistration.max_attempts_per_task,
        max_tokens=preregistration.max_tokens,
    ).identity


def expected_evaluation_identities(
    preregistration: PreRegistration, a0_checkpoint_identity: str
) -> frozenset[str]:
    """Reconstruct the pre-registered evaluation-identity set from the sealed design.

    A0 (OED-2) contributes exactly **one** identity, at its own empty-checkpoint identity;
    A1 and A2 contribute one per ordered checkpoint. Because the manifest hash and the
    checkpoint identity are inputs to the digest, membership in this set verifies both.
    """
    identities = {_provenance_identity(preregistration, a0_checkpoint_identity, Arm.A0.value)}
    for checkpoint in preregistration.checkpoint_identities:
        for arm in _MEMORY_ARMS:
            identities.add(_provenance_identity(preregistration, checkpoint, arm))
    return frozenset(identities)


def _verify_thread_environment() -> None:
    for name, expected in REQUIRED_THREAD_ENVIRONMENT:
        actual = os.environ.get(name)
        if actual != expected:
            raise ExecutionError(
                f"pinned numeric environment violated: {name}={actual!r}, expected {expected!r}"
            )


def _verify_statsmodels_version() -> None:
    """Verify the pinned statistical library. Imported here so K=1 never needs it."""
    import statsmodels

    version = str(statsmodels.__version__)
    if version != REQUIRED_STATSMODELS_VERSION:
        raise ExecutionError(
            f"pinned statistical library violated: statsmodels=={version}, "
            f"expected {REQUIRED_STATSMODELS_VERSION}"
        )


def _verify_results_segregation(results_dir: Path, sink_path: Path) -> None:
    results = Path(results_dir).resolve()
    sink = Path(sink_path).resolve()
    if results == sink or sink.is_relative_to(results):
        raise ExecutionError(
            f"results directory {results} is not segregated from the evaluation sink "
            f"{sink}; the analysis result must never be written into the sink"
        )


def run_preflight(
    *,
    preregistration: PreRegistration,
    evaluation_sink: EvaluationSink,
    results_dir: Path,
    a0_checkpoint_identity: str,
) -> frozenset[str]:
    """Verify the sealed design, the environment and the segregation before any statistic.

    Returns the reconstructed expected evaluation-identity set. Raises
    :class:`ExecutionError` on any violation; nothing is computed and nothing is written.
    """
    if not preregistration.verify_identity():
        raise ExecutionError(
            "pre-registration integrity check failed: stored identity "
            f"{preregistration.identity} != recomputed {preregistration.compute_identity()}"
        )
    if tuple(preregistration.arms) != ARMS:
        raise ExecutionError(
            f"pre-registered arms {tuple(preregistration.arms)!r} are not the frozen "
            f"closed set {ARMS!r}"
        )
    if not _SHA256_HEX.match(a0_checkpoint_identity):
        raise ExecutionError(
            "a0_checkpoint_identity is not a concrete content-addressed SHA-256 hex "
            f"digest: {a0_checkpoint_identity!r}"
        )
    if a0_checkpoint_identity in preregistration.checkpoint_identities:
        raise ExecutionError(
            "a0_checkpoint_identity collides with the pre-registered A1/A2 schedule; "
            "A0 is time-invariant and carries its own empty-checkpoint identity (OED-2)"
        )
    _verify_results_segregation(results_dir, evaluation_sink.path)
    _verify_thread_environment()
    if len(preregistration.checkpoint_identities) > 1:
        _verify_statsmodels_version()
    return expected_evaluation_identities(preregistration, a0_checkpoint_identity)


def _verify_records_resolve(
    records: tuple[EvaluationRecord, ...], expected: frozenset[str]
) -> None:
    """Every observed evaluation identity must resolve to the pre-registered set.

    Only the *observed to expected* direction is enforced here. A pre-registered identity
    with no records is an absence of measurement, which the frozen completeness rule
    (§3.5.1) already owns — turning it into a structural error would pre-empt a VOID or a
    complete-case exclusion that M9 defines.
    """
    unexpected = {record.evaluation_identity for record in records} - expected
    if unexpected:
        raise ExecutionError(
            f"{len(unexpected)} sink record(s) carry an evaluation_identity outside the "
            f"pre-registered set; first: {sorted(unexpected)[0]}"
        )


# ---------------------------------------------------------------------------
# The two frozen branches — composition only
# ---------------------------------------------------------------------------


def _k1_holm(observations: list[Observation]) -> HolmResult:
    a1_vs_a0 = mcnemar_test(observations, superior_arm=Arm.A1.value, reference_arm=Arm.A0.value)
    a2_vs_a1 = mcnemar_test(observations, superior_arm=Arm.A2.value, reference_arm=Arm.A1.value)
    return holm_bonferroni(
        [
            LabeledPValue(comparison_label(Arm.A1.value, Arm.A0.value), a1_vs_a0.p_value),
            LabeledPValue(comparison_label(Arm.A2.value, Arm.A1.value), a2_vs_a1.p_value),
        ]
    )


def _fit_comparison(
    observations: list[Observation], comparison: Comparison, checkpoint_count: int
) -> GeeFit | GeeFailure:
    arms = {comparison.reference_arm, comparison.superior_arm}
    subset = [obs for obs in observations if obs.arm in arms]
    return fit_gee(subset, comparison=comparison, checkpoint_count=checkpoint_count)


def _comparison_pvalues(outcome: GeeFit | GeeFailure) -> ComparisonPValues | None:
    """Route one fitted comparison to its two p-values; ``None`` is the frozen §3.5.7 case.

    A ``GeeFailure`` is handed to C11 unchanged. Separation, parameter magnitude, standard
    errors and p-value magnitude are **not** inspected: a valid ``GeeFit`` is authoritative
    and is consumed exactly as emitted.
    """
    if isinstance(outcome, GeeFailure):
        return None
    return ComparisonPValues(
        compute_wald(compute_emm(outcome)).p_value, compute_trend(outcome).p_value
    )


def _kgt1_holm(
    observations: list[Observation], checkpoint_count: int
) -> tuple[HolmResult, SolverProvenance | None, tuple[float, ...]]:
    first = _fit_comparison(observations, Comparison.A1_VS_A0, checkpoint_count)
    second = _fit_comparison(observations, Comparison.A2_VS_A1, checkpoint_count)
    family = build_kgt1_family(
        a1_vs_a0=_comparison_pvalues(first),
        a2_vs_a1=_comparison_pvalues(second),
    )
    fitted: GeeFit | None = None
    for candidate in (first, second):
        if isinstance(candidate, GeeFit):
            fitted = candidate
            break
    provenance = None if fitted is None else fitted.provenance
    checkpoint_values = () if fitted is None else fitted.checkpoint_values
    return holm_bonferroni(family), provenance, checkpoint_values


def _included(
    observations: tuple[Observation, ...], completeness: CompletenessResult
) -> list[Observation]:
    included = set(completeness.included_task_identities)
    return [obs for obs in observations if obs.task_identity in included]


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def run_m10_analysis(
    *,
    preregistration: PreRegistration,
    evaluation_sink: EvaluationSink,
    results_dir: Path,
    a0_checkpoint_identity: str,
    task_identities: tuple[str, ...],
    evaluation_run_complete: bool,
) -> AnalysisResultRecord:
    """Execute the frozen M9 analysis and persist its single terminal artifact.

    Deterministic: the same sealed pre-registration, record set, pinned environment and
    explicit inputs yield the same decision, the same canonical payload and the same
    content-addressed identity.

    ``task_identities`` is the pre-registered held-out task set and
    ``evaluation_run_complete`` the global M8 run-completion flag; both are explicit
    caller inputs because the frozen C3 completeness rule requires them and neither can be
    inferred from observed outcomes without redefining the analysis.

    Raises :class:`ExecutionError` on any structural or data-integrity violation, in which
    case no result record is written.
    """
    expected = run_preflight(
        preregistration=preregistration,
        evaluation_sink=evaluation_sink,
        results_dir=results_dir,
        a0_checkpoint_identity=a0_checkpoint_identity,
    )
    records = evaluation_sink.read_all()
    _verify_records_resolve(records, expected)

    observations = bind_observations(
        preregistration, records, a0_checkpoint_identity=a0_checkpoint_identity
    )
    completeness = assess_completeness(
        task_identities=task_identities,
        checkpoint_identities=preregistration.checkpoint_identities,
        a0_checkpoint_identity=a0_checkpoint_identity,
        evaluation_run_complete=evaluation_run_complete,
        observed=[
            ObservedCell(obs.task_identity, obs.arm, obs.checkpoint_identity)
            for obs in observations
        ],
    )

    checkpoint_count = len(preregistration.checkpoint_identities)
    holm_result: HolmResult | None = None
    solver_provenance: SolverProvenance | None = None
    checkpoint_values: tuple[float, ...] = ()
    decision: DecisionResult

    if completeness.status is CompletenessStatus.COMPLETE:
        included = _included(observations, completeness)
        if checkpoint_count == 1:
            holm_result = _k1_holm(included)
            decision = decide_k1(completeness_status=completeness.status, holm_result=holm_result)
        else:
            holm_result, solver_provenance, checkpoint_values = _kgt1_holm(
                included, checkpoint_count
            )
            decision = decide_kgt1(completeness_status=completeness.status, holm_result=holm_result)
    elif checkpoint_count == 1:
        # VOID short-circuits: no test is executed, so no Holm family exists (§3.5.11).
        decision = decide_k1(completeness_status=completeness.status)
    else:
        decision = decide_kgt1(completeness_status=completeness.status)

    record = build_result_record(
        preregistration=preregistration,
        completeness=completeness,
        decision=decision,
        evaluation_records=records,
        holm_result=holm_result,
        solver_provenance=solver_provenance,
        checkpoint_values=checkpoint_values,
    )
    write_result_record(record, results_dir)
    return record
