"""The segregated held-out evaluation record (M8-C6).

An :class:`EvaluationRecord` is the persisted **measurement** of one held-out attempt.
It carries the **deterministic verifier verdict** (with the held-out secondary /
model-gap signal, D21) across the frozen verdict taxonomy (D16.7), plus **only** the
already-frozen deterministic token counts (``prompt_tokens``, ``completion_tokens``)
recorded verbatim (M8_SPEC §3.4). It records **no model score and no LLM-as-judge**
(D3/D11), **no new metric, no aggregate, and no non-deterministic quantity** — the
excluded timing fields never appear as a result.

A record is **not an episode** and is **never experience**: it carries no
``content_hash`` and is written only to the segregated evaluation sink (M8-C6), never
through the frozen ``GuardedEpisodeWriter``. It also carries the content-addressed
``evaluation_identity`` (computed by M8-C7, supplied by the runner in M8-C8) so results
are only ever compared within the same checkpoint and split (M8_SPEC §3.5). Standard
library plus pydantic and the frozen episode verdict taxonomy (read-only).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from velith.episodes.episode import VerdictState
from velith.evaluation.attempt import AttemptOutcome


class EvaluationRecord(BaseModel):
    """One held-out measurement: the grounded verdict, its identity, and token counts.

    Frozen and ``extra="forbid"`` — a measurement is immutable and cannot grow undeclared
    fields. ``protected_namespaces=()`` permits the ``model`` / ``model_version``
    provenance field names (these are *identity* strings, never a model-produced score).
    """

    model_config = ConfigDict(frozen=True, extra="forbid", protected_namespaces=())

    # Content-addressed identity of the evaluation this record belongs to (M8-C7/C8).
    evaluation_identity: str
    # Identity of the measurement: which arm attempted which held-out task, at what seed.
    arm: str
    task_identity: str
    seed: int
    # The grounded verifier verdict and the held-out secondary (model-gap) signal (D21).
    verdict_state: VerdictState
    secondary_passed: bool | None = None
    flaky: bool = False
    # Already-frozen deterministic token counts, recorded verbatim (M8_SPEC §3.4).
    prompt_tokens: int
    completion_tokens: int
    # Provenance of the producing model (identity strings, not a score).
    model: str
    model_version: str

    @classmethod
    def from_outcome(cls, outcome: AttemptOutcome, evaluation_identity: str) -> EvaluationRecord:
        """Build a record from an attempt outcome and its evaluation identity."""
        return cls(
            evaluation_identity=evaluation_identity,
            arm=outcome.arm.value,
            task_identity=outcome.task_identity,
            seed=outcome.seed,
            verdict_state=outcome.verdict_state,
            secondary_passed=outcome.secondary_passed,
            flaky=outcome.flaky,
            prompt_tokens=outcome.prompt_tokens,
            completion_tokens=outcome.completion_tokens,
            model=outcome.model,
            model_version=outcome.model_version,
        )
