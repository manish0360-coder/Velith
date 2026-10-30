"""Integration: real sandbox verification -> API v0 result or outcome (D33, API-0 C2).

Runs the frozen ``VerifierSandbox`` on the ``calc_add_bug`` fixture through ``SweVerifier``. The
six required cases must pass without skips inside the verifier container (``CAP_SYS_ADMIN`` for
``unshare -n``); outside it, the isolation-dependent cases skip with an explicit reason, as the
frozen ``test_phase2_blocks_network_egress`` does.

1. correct patch          -> EngineeringResult (PASSED, unflaky, secondary True, isolated, 3 runs)
2. "cheating" patch       -> UnverifiedOutcome(SECONDARY_FAILED)  (the model gap, D21)
3. wrong patch            -> UnverifiedOutcome(VERDICT_NOT_PASSED) (FAILED)
4. malformed patch        -> UnverifiedOutcome(VERDICT_NOT_PASSED) (PATCH_APPLY_FAILED)
5. isolation off          -> UnverifiedOutcome(ISOLATION_DISABLED)
6. one primary run        -> UnverifiedOutcome(INSUFFICIENT_RERUNS)
plus K2: an infrastructure fault propagates and produces nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from noetica.interfaces.verification import VerdictStatus

from velith.api import (
    EngineeringResult,
    EngineeringTask,
    SwePatch,
    SwePatchPayload,
    UnverifiedOutcome,
    UnverifiedReason,
    from_wire,
)
from velith.api.contract import DesignArtifact
from velith.api.swe import SweVerifier
from velith.harness import verifier_sandbox as _verifier_sandbox
from velith.harness.verifier_sandbox import SandboxExecutionError, VerifierSandbox
from velith.task import FIXTURE_TASK_ID

_FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"
_CALCULATOR = _FIXTURES_ROOT / FIXTURE_TASK_ID / "calculator.py"

#: The T3 vector patch (API_V0_SPEC §3.7).
_T3_PATCH = (
    "--- a/calculator.py\n"
    "+++ b/calculator.py\n"
    "@@ -1,3 +1,3 @@\n"
    " # mypy: ignore-errors\n"
    " def add(a: int, b: int) -> int:\n"
    "-    return a - b\n"
    "+    return a + b\n"
)
_T3_HASH = "sha256:ff39e80e72505b345d649cb5254e242490db0bf3ca67bcaed50d3274e11cae95"
_T5A_REF = "cdf5e4da-da47-5e52-b845-448ab5cc6bb1"

#: Wrong context: extracted as a patch, but ``git apply`` rejects it -> PATCH_APPLY_FAILED.
_MALFORMED_PATCH = (
    "--- a/calculator.py\n"
    "+++ b/calculator.py\n"
    "@@ -1,3 +1,3 @@\n"
    " # this context line does not exist\n"
    " def add(a: int, b: int) -> int:\n"
    "-    return a - b\n"
    "+    return a + b\n"
)

needs_isolation = pytest.mark.skipif(
    not _verifier_sandbox._network_isolation_available(),
    reason="network isolation requires CAP_SYS_ADMIN / unshare -n (run in the verifier container)",
)


def _replacing(expression: str) -> str:
    """The T3 patch with ``expression`` in place of the fix (checked against the fixture)."""
    original = _CALCULATOR.read_text(encoding="utf-8")
    assert "    return a - b\n" in original
    return _T3_PATCH.replace("+    return a + b\n", f"+    return {expression}\n")


def _artifact(patch: str) -> DesignArtifact:
    return DesignArtifact(
        payload=SwePatchPayload(task_id=FIXTURE_TASK_ID, patch=SwePatch(text=patch))
    )


def _task() -> EngineeringTask:
    return EngineeringTask(task_id=FIXTURE_TASK_ID)


def _evaluate(
    patch: str, *, network_isolation: bool = True, flake_rerun_count: int = 3
) -> EngineeringResult | UnverifiedOutcome:
    with SweVerifier(
        fixtures_root=_FIXTURES_ROOT,
        network_isolation=network_isolation,
        flake_rerun_count=flake_rerun_count,
    ) as verifier:
        return verifier.evaluate(_task(), _artifact(patch))


@needs_isolation
def test_correct_patch_produces_a_verified_engineering_result() -> None:
    with SweVerifier(
        fixtures_root=_FIXTURES_ROOT, network_isolation=True, flake_rerun_count=3
    ) as verifier:
        first = verifier.evaluate(_task(), _artifact(_T3_PATCH))
        second = verifier.evaluate(_task(), _artifact(_T3_PATCH))
    assert isinstance(first, EngineeringResult)
    assert isinstance(second, EngineeringResult)
    assert first.evidence.verdict_status is VerdictStatus.PASSED
    assert first.evidence.flaky is False
    assert first.evidence.secondary_passed is True
    assert first.evidence.network_isolated is True
    assert first.evidence.flake_rerun_count == 3
    assert first.design_artifact.content_hash == _T3_HASH
    assert first.design_artifact.ref == _T5A_REF
    assert first.task_id == FIXTURE_TASK_ID
    # The wire object is the five-field contract and passes the consumer-side checks.
    wire = json.loads(json.dumps(first.to_wire()))
    assert from_wire(wire).result_id == first.result_id
    # ID-1: a second run of the same claim has the same content identity.
    assert (second.result_id, second.content_hash) == (first.result_id, first.content_hash)
    assert first.provenance.inputs == (FIXTURE_TASK_ID, _T3_HASH)


@needs_isolation
def test_cheating_patch_is_the_model_gap_not_a_result() -> None:
    outcome = _evaluate(_replacing("5"))
    assert isinstance(outcome, UnverifiedOutcome)
    assert outcome.verdict is VerdictStatus.PASSED  # the primary passed...
    assert outcome.reason is UnverifiedReason.SECONDARY_FAILED  # ...the held-out suite refuted it


@needs_isolation
def test_wrong_patch_is_not_passed() -> None:
    outcome = _evaluate(_replacing("a * b"))
    assert isinstance(outcome, UnverifiedOutcome)
    assert outcome.verdict is VerdictStatus.FAILED
    assert outcome.reason is UnverifiedReason.VERDICT_NOT_PASSED


@needs_isolation
def test_malformed_patch_is_not_passed() -> None:
    outcome = _evaluate(_MALFORMED_PATCH)
    assert isinstance(outcome, UnverifiedOutcome)
    assert outcome.verdict is VerdictStatus.PATCH_APPLY_FAILED
    assert outcome.reason is UnverifiedReason.VERDICT_NOT_PASSED


def test_correct_patch_without_isolation_is_not_a_public_result() -> None:
    outcome = _evaluate(_T3_PATCH, network_isolation=False)
    assert isinstance(outcome, UnverifiedOutcome)
    assert outcome.verdict is VerdictStatus.PASSED
    assert outcome.reason is UnverifiedReason.ISOLATION_DISABLED


@needs_isolation
def test_correct_patch_with_one_primary_run_is_not_a_public_result() -> None:
    outcome = _evaluate(_T3_PATCH, flake_rerun_count=1)
    assert isinstance(outcome, UnverifiedOutcome)
    assert outcome.verdict is VerdictStatus.PASSED
    assert outcome.reason is UnverifiedReason.INSUFFICIENT_RERUNS


def test_infrastructure_fault_propagates_and_produces_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fault(self: VerifierSandbox, task: object, patch: str) -> object:
        raise SandboxExecutionError("simulated infrastructure fault")

    monkeypatch.setattr(VerifierSandbox, "verify", _fault)
    with pytest.raises(SandboxExecutionError, match="simulated"):
        _evaluate(_T3_PATCH)
