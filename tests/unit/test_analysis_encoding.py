"""Unit tests for the M9 binary endpoint encoding (M9-C3 / P2, §3.5.1).

Deterministic, synthetic fixtures only — no real M8 held-out data. Pins the frozen
endpoint (PASSED -> 1, every other verdict -> 0), record non-mutation, malformed-input
rejection, and the boundary (no held-out/memory/statistical surfaces).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from velith.analysis import encoding
from velith.analysis.encoding import EncodingError, encode_record, encode_verdict
from velith.episodes.episode import VerdictState
from velith.evaluation.record import EvaluationRecord


def _record(state: VerdictState) -> EvaluationRecord:
    return EvaluationRecord(
        evaluation_identity="e" * 64,
        arm="A1",
        task_identity="t" * 64,
        seed=0,
        verdict_state=state,
        prompt_tokens=0,
        completion_tokens=0,
        model="qwen2.5-coder",
        model_version="0.0.0",
    )


def test_passed_encodes_one() -> None:
    assert encode_verdict(VerdictState.PASSED) == 1


def test_every_non_passed_encodes_zero() -> None:
    for state in VerdictState:
        if state is VerdictState.PASSED:
            continue
        assert encode_verdict(state) == 0


def test_encode_record_uses_verdict_state() -> None:
    assert encode_record(_record(VerdictState.PASSED)) == 1
    assert encode_record(_record(VerdictState.FAILED)) == 0


def test_encoding_is_deterministic() -> None:
    for state in VerdictState:
        assert encode_verdict(state) == encode_verdict(state)


def test_encode_record_does_not_mutate_source() -> None:
    record = _record(VerdictState.PASSED)
    snapshot = record.model_dump_json()
    encode_record(record)
    assert record.model_dump_json() == snapshot


def test_malformed_verdict_is_rejected() -> None:
    for bad in ("PASSED", 1, None, object()):
        with pytest.raises(EncodingError):
            encode_verdict(bad)  # type: ignore[arg-type]


def test_encoding_does_not_touch_heldout_or_statistical_surfaces() -> None:
    source = Path(encoding.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "evaluation.sink",
        "EvaluationSink",
        "episodes.store",
        "GuardedEpisodeWriter",
        "evaluation.runner",
        "statsmodels",
        "p_value",
        "pvalue",
        "GEE",
        "EMM",
    ):
        assert forbidden not in source, f"encoding must not reference: {forbidden}"
