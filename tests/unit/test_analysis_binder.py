"""Unit tests for the M9 record->observation binder (M9-C4 / P2).

Deterministic, synthetic fixtures only — no real M8 held-out data. Pins the frozen join
(EvaluationProvenance.identity), OED-2/OED-9 A0 single-observation handling, concrete
checkpoint/arm/task validation, duplicate rejection, deterministic ordering, C3 endpoint
delegation, and the boundary (no completeness/statistics/memory).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from velith.analysis import binder as binder_mod
from velith.analysis.binder import BinderError, Observation, bind_observations
from velith.analysis.encoding import encode_record
from velith.analysis.preregistration import PreRegistration
from velith.episodes.episode import VerdictState
from velith.evaluation.provenance import EvaluationProvenance
from velith.evaluation.record import EvaluationRecord


def _order_key(obs: Observation) -> tuple[str, str, int, str]:
    index = -1 if obs.checkpoint_index is None else obs.checkpoint_index
    return (obs.task_identity, obs.arm, index, obs.checkpoint_identity)


_A0_CP = hashlib.sha256(b"a0-empty-checkpoint").hexdigest()
_CPS = (hashlib.sha256(b"cp1").hexdigest(), hashlib.sha256(b"cp2").hexdigest())
_TASK = hashlib.sha256(b"task1").hexdigest()
_TASK2 = hashlib.sha256(b"task2").hexdigest()


def _prereg() -> PreRegistration:
    return PreRegistration.build(
        manifest_hash=hashlib.sha256(b"manifest").hexdigest(),
        checkpoint_identities=_CPS,
        base_model="qwen2.5-coder",
        eval_seed=0,
        max_tasks=0,
        max_attempts_per_task=1,
        max_tokens=0,
    )


def _eval_identity(prereg: PreRegistration, checkpoint_identity: str, arm: str) -> str:
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


def _record(
    prereg: PreRegistration,
    checkpoint_identity: str,
    arm: str,
    *,
    task: str = _TASK,
    verdict: VerdictState = VerdictState.PASSED,
    evaluation_identity: str | None = None,
) -> EvaluationRecord:
    return EvaluationRecord(
        evaluation_identity=evaluation_identity or _eval_identity(prereg, checkpoint_identity, arm),
        arm=arm,
        task_identity=task,
        seed=0,
        verdict_state=verdict,
        prompt_tokens=0,
        completion_tokens=0,
        model="qwen2.5-coder",
        model_version="0.0.0",
    )


def test_valid_a0_record() -> None:
    pr = _prereg()
    obs = bind_observations(pr, [_record(pr, _A0_CP, "A0")], a0_checkpoint_identity=_A0_CP)
    assert obs == (Observation(_TASK, "A0", _A0_CP, None, 1),)


def test_valid_a1_and_a2_single_checkpoint() -> None:
    pr = _prereg()
    a1 = bind_observations(pr, [_record(pr, _CPS[0], "A1")], a0_checkpoint_identity=_A0_CP)
    a2 = bind_observations(pr, [_record(pr, _CPS[0], "A2")], a0_checkpoint_identity=_A0_CP)
    assert a1 == (Observation(_TASK, "A1", _CPS[0], 1, 1),)
    assert a2 == (Observation(_TASK, "A2", _CPS[0], 1, 1),)


def test_valid_multi_checkpoint_a1_and_a2() -> None:
    pr = _prereg()
    records = [_record(pr, cp, arm) for cp in _CPS for arm in ("A1", "A2")]
    obs = bind_observations(pr, records, a0_checkpoint_identity=_A0_CP)
    a1 = [o for o in obs if o.arm == "A1"]
    a2 = [o for o in obs if o.arm == "A2"]
    assert [o.checkpoint_index for o in a1] == [1, 2]
    assert [o.checkpoint_index for o in a2] == [1, 2]
    assert [o.checkpoint_identity for o in a1] == list(_CPS)


def test_a0_produces_exactly_one_observation_not_replicated() -> None:
    pr = _prereg()  # K = 2
    records = [_record(pr, _A0_CP, "A0")] + [
        _record(pr, cp, arm) for cp in _CPS for arm in ("A1", "A2")
    ]
    obs = bind_observations(pr, records, a0_checkpoint_identity=_A0_CP)
    a0 = [o for o in obs if o.arm == "A0"]
    assert len(a0) == 1
    assert a0[0].checkpoint_index is None
    assert a0[0].checkpoint_identity == _A0_CP  # supplied identity preserved


def test_wrong_a0_identity_does_not_silently_match() -> None:
    pr = _prereg()
    wrong_a0 = hashlib.sha256(b"WRONG-a0").hexdigest()
    # A record built with the correct A0 identity is unexpected under a wrong supplied A0 id.
    with pytest.raises(BinderError):
        bind_observations(pr, [_record(pr, _A0_CP, "A0")], a0_checkpoint_identity=wrong_a0)


def test_unknown_checkpoint_identity_rejected() -> None:
    pr = _prereg()
    off_schedule = hashlib.sha256(b"cp99").hexdigest()
    with pytest.raises(BinderError):
        bind_observations(pr, [_record(pr, off_schedule, "A1")], a0_checkpoint_identity=_A0_CP)


def test_wrong_arm_rejected() -> None:
    pr = _prereg()
    # evaluation_identity says (cp1, A1) but the record declares arm A2.
    rec = _record(pr, _CPS[0], "A1")
    inconsistent = rec.model_copy(update={"arm": "A2"})
    with pytest.raises(BinderError):
        bind_observations(pr, [inconsistent], a0_checkpoint_identity=_A0_CP)


def test_malformed_task_identity_rejected() -> None:
    pr = _prereg()
    bad = _record(pr, _CPS[0], "A1", task="not-a-content-address")
    with pytest.raises(BinderError):
        bind_observations(pr, [bad], a0_checkpoint_identity=_A0_CP)


def test_unexpected_evaluation_identity_rejected() -> None:
    pr = _prereg()
    garbage = _record(pr, _CPS[0], "A1", evaluation_identity="0" * 64)
    with pytest.raises(BinderError):
        bind_observations(pr, [garbage], a0_checkpoint_identity=_A0_CP)


def test_duplicate_observation_rejected() -> None:
    pr = _prereg()
    dup = [_record(pr, _CPS[0], "A1"), _record(pr, _CPS[0], "A1")]
    with pytest.raises(BinderError):
        bind_observations(pr, dup, a0_checkpoint_identity=_A0_CP)


def test_malformed_a0_checkpoint_identity_rejected() -> None:
    pr = _prereg()
    with pytest.raises(BinderError):
        bind_observations(pr, [], a0_checkpoint_identity="not-a-hash")


def test_deterministic_ordering() -> None:
    pr = _prereg()
    records = [_record(pr, _A0_CP, "A0", task=_TASK2)] + [
        _record(pr, cp, arm, task=task)
        for task in (_TASK, _TASK2)
        for cp in _CPS
        for arm in ("A1", "A2")
    ]
    records.append(_record(pr, _A0_CP, "A0", task=_TASK))
    forward = bind_observations(pr, records, a0_checkpoint_identity=_A0_CP)
    reverse = bind_observations(pr, list(reversed(records)), a0_checkpoint_identity=_A0_CP)
    assert forward == reverse
    assert list(forward) == sorted(forward, key=_order_key)


def test_endpoint_delegates_to_c3_encoding() -> None:
    pr = _prereg()
    passed = _record(pr, _CPS[0], "A1", verdict=VerdictState.PASSED)
    failed = _record(pr, _CPS[1], "A1", verdict=VerdictState.FAILED)
    obs = bind_observations(pr, [passed, failed], a0_checkpoint_identity=_A0_CP)
    by_cp = {o.checkpoint_index: o.endpoint for o in obs}
    assert by_cp[1] == encode_record(passed) == 1
    assert by_cp[2] == encode_record(failed) == 0


def test_binder_performs_no_completeness_classification() -> None:
    # Given only a partial coverage (A0 alone), the binder still returns the bound
    # observation without raising VOID / excluding / classifying — completeness is C3's.
    pr = _prereg()
    obs = bind_observations(pr, [_record(pr, _A0_CP, "A0")], a0_checkpoint_identity=_A0_CP)
    assert len(obs) == 1


def test_binder_has_no_statistical_or_memory_surfaces() -> None:
    source = Path(binder_mod.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "velith.retrieval",
        "velith.evaluation.checkpoint",
        "velith.evaluation.sink",
        "velith.evaluation.runner",
        "EvaluationSink",
        "GuardedEpisodeWriter",
        "assess_completeness",
        "statsmodels",
        "p_value",
        "pvalue",
        "mcnemar",
        "holm",
    ):
        assert forbidden not in source, f"binder must not reference: {forbidden}"
