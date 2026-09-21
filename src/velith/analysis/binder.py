"""Deterministic record->observation join for the M9 analysis (M9-C4 / P2 binder).

The binder is the structural boundary between validated M8 evaluation records and the
canonical ``task x checkpoint x arm`` observation representation the later statistical
executors consume. It performs **join and validation only** — no statistic, no
aggregation, no completeness classification (C3 owns that), no GO/NO-GO, no held-out
execution, no memory writes.

Join key (handoff §5): a record is bound to a pre-registered evaluation via the frozen
``EvaluationProvenance(...).identity`` — the only sanctioned key. The binder reconstructs
the expected identity for each pre-registered (checkpoint, arm):

* **A1/A2** — one expected identity per pre-registered checkpoint identity (ordinal 1..K).
* **A0 (OED-2 / OED-9)** — **exactly one** expected identity, built from the supplied
  concrete A0 empty-checkpoint identity; A0 is never iterated over the A1/A2 schedule and
  never replicated across K.

``checkpoint_id_c`` (the mean-centered model covariate) is **not** assigned here — that is
the statistical layer's concern (§6). The binder records only the raw ordinal
``checkpoint_index`` (1..K for A1/A2; ``None`` for A0's single time-invariant observation).

Memory independence (§12/OED-9): A0's empty-checkpoint identity arrives **only** through the
explicit ``a0_checkpoint_identity`` argument; the binder imports no memory/retrieval,
checkpoint-storage, sink, or runner machinery. (It uses the frozen ``EvaluationProvenance``
identity type and the ``EvaluationRecord`` value type, and delegates endpoint encoding to
C3 ``encode_record`` — never redefining endpoint semantics.)
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from velith.analysis.encoding import encode_record
from velith.analysis.preregistration import PreRegistration
from velith.arms.identity import Arm
from velith.evaluation.provenance import EvaluationProvenance
from velith.evaluation.record import EvaluationRecord

#: A concrete content-addressed identity is a lowercase SHA-256 hex digest (64 chars).
_SHA256_HEX: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


class BinderError(Exception):
    """Raised on a structural/data-integrity failure in the record->observation join."""


@dataclass(frozen=True)
class Observation:
    """One canonical analysis observation (structural; carries no statistic).

    ``checkpoint_index`` is the 1-based ordinal position in the pre-registered schedule for
    A1/A2, and ``None`` for A0's single time-invariant observation (OED-2). ``endpoint`` is
    the C3 binary endpoint (``PASSED`` = 1, else 0). ``checkpoint_id_c`` is intentionally
    absent — the statistical layer derives it (§6).
    """

    task_identity: str
    arm: str
    checkpoint_identity: str
    checkpoint_index: int | None
    endpoint: int


@dataclass(frozen=True)
class _Expected:
    arm: str
    checkpoint_identity: str
    checkpoint_index: int | None


def _provenance_identity(prereg: PreRegistration, *, checkpoint_identity: str, arm: str) -> str:
    """The sanctioned join key for one (checkpoint, arm): ``EvaluationProvenance.identity``."""
    return EvaluationProvenance(
        checkpoint_identity=checkpoint_identity,
        manifest_hash=prereg.manifest_hash,
        arm=arm,
        base_model=prereg.base_model,
        eval_seed=prereg.eval_seed,
        max_tasks=prereg.max_tasks,
        max_attempts_per_task=prereg.max_attempts_per_task,
        max_tokens=prereg.max_tokens,
    ).identity


def _expected_identities(
    prereg: PreRegistration, a0_checkpoint_identity: str
) -> dict[str, _Expected]:
    """Reconstruct the pre-registered ``evaluation_identity -> (arm, checkpoint, index)`` map."""
    if not _SHA256_HEX.match(a0_checkpoint_identity):
        raise BinderError(
            "a0_checkpoint_identity is not a concrete content-addressed SHA-256 hex digest: "
            f"{a0_checkpoint_identity!r}"
        )
    expected: dict[str, _Expected] = {}

    def _register(identity: str, entry: _Expected) -> None:
        if identity in expected:
            raise BinderError(
                f"expected-identity collision between {expected[identity]} and {entry}"
            )
        expected[identity] = entry

    # A0: exactly ONE expected identity (OED-2/OED-9) — never iterated over the schedule.
    _register(
        _provenance_identity(prereg, checkpoint_identity=a0_checkpoint_identity, arm=Arm.A0.value),
        _Expected(Arm.A0.value, a0_checkpoint_identity, None),
    )
    # A1/A2: one expected identity per pre-registered checkpoint (ordinal 1..K).
    for index, checkpoint_identity in enumerate(prereg.checkpoint_identities, start=1):
        for arm in (Arm.A1.value, Arm.A2.value):
            _register(
                _provenance_identity(prereg, checkpoint_identity=checkpoint_identity, arm=arm),
                _Expected(arm, checkpoint_identity, index),
            )
    return expected


def bind_observations(
    preregistration: PreRegistration,
    records: Iterable[EvaluationRecord],
    *,
    a0_checkpoint_identity: str,
) -> tuple[Observation, ...]:
    """Join evaluation records to the canonical observation set (deterministic).

    Each record is bound by its ``evaluation_identity`` against the pre-registered expected
    set. A record whose identity is not expected, whose declared ``arm`` disagrees with the
    expected arm, whose ``task_identity`` is not a concrete content-addressed identity, or
    that duplicates an already-bound ``(evaluation_identity, task_identity)`` cell raises
    :class:`BinderError` — never silently dropped. Output is sorted deterministically.
    """
    expected = _expected_identities(preregistration, a0_checkpoint_identity)
    seen: set[tuple[str, str]] = set()
    observations: list[Observation] = []
    for record in records:
        entry = expected.get(record.evaluation_identity)
        if entry is None:
            raise BinderError(
                "record with an unexpected evaluation_identity (not in the pre-registered set): "
                f"task={record.task_identity!r} arm={record.arm!r} "
                f"evaluation_identity={record.evaluation_identity!r}"
            )
        if record.arm != entry.arm:
            raise BinderError(
                f"record arm {record.arm!r} disagrees with the expected arm {entry.arm!r} for "
                f"evaluation_identity {record.evaluation_identity!r}"
            )
        if not _SHA256_HEX.match(record.task_identity):
            raise BinderError(
                "record task_identity is not a concrete content-addressed SHA-256 hex digest: "
                f"{record.task_identity!r}"
            )
        key = (record.evaluation_identity, record.task_identity)
        if key in seen:
            raise BinderError(f"duplicate observation for cell {key}")
        seen.add(key)
        observations.append(
            Observation(
                task_identity=record.task_identity,
                arm=entry.arm,
                checkpoint_identity=entry.checkpoint_identity,
                checkpoint_index=entry.checkpoint_index,
                endpoint=encode_record(record),
            )
        )
    observations.sort(
        key=lambda obs: (
            obs.task_identity,
            obs.arm,
            -1 if obs.checkpoint_index is None else obs.checkpoint_index,
            obs.checkpoint_identity,
        )
    )
    return tuple(observations)
