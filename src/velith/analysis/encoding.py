"""Binary endpoint encoding for the M9 analysis (M9-C3 / P2, §3.5.1).

The single frozen endpoint: a ``PASSED`` verifier verdict encodes ``1`` and every other
verdict in the frozen taxonomy (D16.7) encodes ``0``. This is a pure, deterministic
transform of the already-frozen verdict — it computes no statistic, aggregates nothing,
and mutates no source record. It is the endpoint encoder the (later) binder calls when
building the per-task observation representation (handoff §5); M9-C3 provides the encoding
only, not the record-to-observation join (that is `binder.py`, a later milestone).

Boundary: this module consumes the frozen verdict/record *types* only. It never reads the
evaluation sink or any live held-out state, writes no memory, and computes no statistic.
"""

from __future__ import annotations

from typing import Final

from velith.episodes.episode import VerdictState
from velith.evaluation.record import EvaluationRecord

#: A ``PASSED`` verdict encodes 1; every other frozen verdict encodes 0 (§3.5.1).
PASSED_ENDPOINT: Final[int] = 1
NON_PASSED_ENDPOINT: Final[int] = 0


class EncodingError(Exception):
    """Raised on a malformed verdict outside the frozen taxonomy (data-integrity)."""


def encode_verdict(state: VerdictState) -> int:
    """Encode a frozen verdict as the binary endpoint: ``PASSED`` -> 1, else -> 0 (§3.5.1).

    Raises :class:`EncodingError` if ``state`` is not a member of the frozen
    :class:`VerdictState` taxonomy — a malformed verdict is a loud data-integrity failure,
    never silently coerced.
    """
    if not isinstance(state, VerdictState):
        raise EncodingError(f"not a frozen VerdictState: {state!r}")
    return PASSED_ENDPOINT if state is VerdictState.PASSED else NON_PASSED_ENDPOINT


def encode_record(record: EvaluationRecord) -> int:
    """Encode an evaluation record's verdict as the binary endpoint (§3.5.1).

    Reads only ``record.verdict_state``; the record is immutable and is not mutated.
    """
    return encode_verdict(record.verdict_state)
