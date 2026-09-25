"""The cost-guarded held-out evaluation sweep (M8-C8).

``run_heldout_evaluation`` evaluates **one (arm, checkpoint)** against the held-out set,
composing the M8 seams C2-C7 (M8_SPEC §3.5/§5):

* read the **held-out** set (C3),
* run the **identical** memory-conditioned attempt per task (C5),
* wrap each grounded outcome into a segregated :class:`EvaluationRecord` (C6) under the
  content-addressed **evaluation identity** (C7), and
* write each record **only** to the segregated sink (C6),

bounded by the frozen M5 :class:`CostGuard` (composed, never modified), which halts the
sweep **loudly** (:class:`~velith.batch.budget.CostBudgetError`) at a limit. A halt
writes **no partial record**: the guard is consulted before the record is written, so the
halted task contributes nothing and every record already in the sink is complete.

The runner is **read-only** against memory and the experience log and writes **only** to
the sink — it never touches the frozen ``GuardedEpisodeWriter`` (D8). It binds every
record to a single checkpoint and split by refusing a provenance that does not match the
checkpoint, held-out set, and arm being swept (an invalid measurement fails loudly,
§3.5). A0, A1, and A2 all run through this one identical function; the arm's memory (via
its checkpoint) is the sole difference. Standard library plus the frozen M5 cost guard and
the M8 evaluation seams. It computes **no statistic and reaches no decision** (D22).

**Evaluation identity v2 (D29; ``docs/M8_IDENTITY_V2_SPEC.md`` §7).** Before the first
attempt the runner also requires ``identity_version`` to be the v2 constant, constructs the
held-out VerificationManifest from the held-out set and the TaskSpec store, and requires
its hash to equal ``provenance.verification_manifest_hash``. Any failure raises
:class:`EvaluationError` before any attempt, so no partial record is written.
"""

from __future__ import annotations

from velith.batch.budget import CostGuard
from velith.evaluation.attempt import HeldOutAttempt
from velith.evaluation.checkpoint import Checkpoint
from velith.evaluation.heldout_set import HeldOutEvaluationSet
from velith.evaluation.provenance import IDENTITY_VERSION, EvaluationProvenance
from velith.evaluation.record import EvaluationRecord
from velith.evaluation.sink import EvaluationSink
from velith.evaluation.verification_manifest import (
    TaskSpecStore,
    VerificationManifestError,
    build_verification_manifest,
)


class EvaluationError(Exception):
    """Raised when an evaluation is internally inconsistent — loud, never silent (§3.5)."""


def _require_consistent(
    provenance: EvaluationProvenance,
    checkpoint: Checkpoint,
    heldout_set: HeldOutEvaluationSet,
    taskspec_store: TaskSpecStore,
) -> None:
    """Refuse a provenance that does not identify this exact checkpoint, split, arm, and
    held-out verification manifest (identity v2)."""
    if provenance.checkpoint_identity != checkpoint.identity:
        raise EvaluationError("provenance checkpoint identity does not match the checkpoint")
    if provenance.manifest_hash != heldout_set.manifest_hash:
        raise EvaluationError("provenance manifest hash does not match the held-out split")
    if provenance.arm != checkpoint.arm.value:
        raise EvaluationError("provenance arm does not match the checkpoint arm")
    if provenance.identity_version != IDENTITY_VERSION:
        raise EvaluationError(
            f"provenance identity_version {provenance.identity_version!r} is not "
            f"{IDENTITY_VERSION!r}"
        )
    try:
        manifest = build_verification_manifest(heldout_set.tasks, taskspec_store)
    except VerificationManifestError as exc:
        raise EvaluationError(f"held-out verification manifest is invalid: {exc}") from exc
    if provenance.verification_manifest_hash != manifest.verification_manifest_hash:
        raise EvaluationError(
            "provenance verification_manifest_hash does not match the held-out set's "
            "verification manifest"
        )


def run_heldout_evaluation(
    checkpoint: Checkpoint,
    heldout_set: HeldOutEvaluationSet,
    provenance: EvaluationProvenance,
    *,
    attempt: HeldOutAttempt,
    sink: EvaluationSink,
    guard: CostGuard,
    taskspec_store: TaskSpecStore,
) -> tuple[EvaluationRecord, ...]:
    """Sweep the held-out set under ``checkpoint``'s arm, writing records to the sink.

    Returns the records written, in order. Halts loudly at a cost-guard limit without
    writing a partial record; writes only to the sink and never to the experience log.
    """
    _require_consistent(provenance, checkpoint, heldout_set, taskspec_store)

    records: list[EvaluationRecord] = []
    for corpus_task in heldout_set:
        guard.start_task()  # loud halt before any work for this task -> no partial record
        guard.check_attempt(0)  # one attempt per held-out task (as M1/M5)

        outcome = attempt.attempt(checkpoint, corpus_task)

        # Charge before writing: if the budget is exhausted the record is never written.
        guard.charge_tokens(outcome.prompt_tokens + outcome.completion_tokens)

        record = EvaluationRecord.from_outcome(outcome, provenance.identity)
        sink.append(record)
        records.append(record)
    return tuple(records)
