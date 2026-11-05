"""Hermetic unit tests for the API v0 software verifier adapter (D33, API-0 C2).

No sandbox is run here. These pin: the pure sandbox-verdict -> evidence mapping (every verdict
state, ``flaky``, every ``secondary_passed`` value); K1, that the values reported as evidence are
exactly the values supplied to the sandbox, resolved from Settings when omitted; task resolution;
the pre-run artifact/task check; Noetica ``Verifier`` protocol conformance; and that importing the
contract package does not load the harness.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, ClassVar

import pytest
from noetica.interfaces.verification import Verdict, VerdictStatus, Verifier

from velith.api import (
    SWE_VERIFIER_COMPONENT,
    ContractError,
    DesignArtifact,
    EngineeringTask,
    SwePatch,
    SwePatchPayload,
    UnverifiedReason,
    unverified_reason,
)
from velith.api import swe as api_swe
from velith.api.swe import (
    SWE_VERIFIER_VERSION,
    SweVerifier,
    evidence_from_sandbox_verdict,
    resolve_task,
)
from velith.core.config import get_settings
from velith.episodes.episode import VerdictState
from velith.harness.verifier_sandbox import Verdict as SandboxVerdict
from velith.harness.verifier_sandbox import VerifierSandbox
from velith.task import FIXTURE_TASK_ID

_FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"


def _sandbox_verdict(
    state: VerdictState, *, flaky: bool = False, secondary: bool | None = True
) -> SandboxVerdict:
    return SandboxVerdict(
        state=state, output="out", secondary_passed=secondary, flaky=flaky, duration_seconds=0.5
    )


def _artifact(task_id: str = FIXTURE_TASK_ID) -> DesignArtifact:
    return DesignArtifact(
        payload=SwePatchPayload(task_id=task_id, patch=SwePatch(text="--- a\n+++ b\n"))
    )


# --- Evidence mapping (pure) -----------------------------------------------------------------


@pytest.mark.parametrize("state", list(VerdictState))
def test_every_sandbox_state_maps_to_the_same_noetica_status(state: VerdictState) -> None:
    evidence = evidence_from_sandbox_verdict(
        _sandbox_verdict(state), flake_rerun_count=3, network_isolated=True
    )
    assert evidence.verdict_status is VerdictStatus(state.value)


@pytest.mark.parametrize("flaky", [False, True])
@pytest.mark.parametrize("secondary", [True, False, None])
@pytest.mark.parametrize("isolated", [True, False])
@pytest.mark.parametrize("reruns", [1, 3])
def test_mapping_copies_the_verdict_and_reports_the_supplied_configuration(
    flaky: bool, secondary: bool | None, isolated: bool, reruns: int
) -> None:
    evidence = evidence_from_sandbox_verdict(
        _sandbox_verdict(VerdictState.PASSED, flaky=flaky, secondary=secondary),
        flake_rerun_count=reruns,
        network_isolated=isolated,
    )
    assert evidence.flaky is flaky
    assert evidence.secondary_passed is secondary
    assert evidence.network_isolated is isolated
    assert evidence.flake_rerun_count == reruns


def test_flaky_and_absent_secondary_are_not_verified() -> None:
    flaky = evidence_from_sandbox_verdict(
        _sandbox_verdict(VerdictState.PASSED, flaky=True),
        flake_rerun_count=3,
        network_isolated=True,
    )
    absent = evidence_from_sandbox_verdict(
        _sandbox_verdict(VerdictState.PASSED, secondary=None),
        flake_rerun_count=3,
        network_isolated=True,
    )
    assert unverified_reason(flaky) is UnverifiedReason.FLAKY
    assert unverified_reason(absent) is UnverifiedReason.SECONDARY_ABSENT


# --- K1: the values reported are the values supplied to the sandbox -------------------------


class _RecordingSandbox(VerifierSandbox):
    """Records the constructor arguments the adapter passes; behaves as the real sandbox."""

    calls: ClassVar[list[dict[str, Any]]] = []

    def __init__(
        self,
        timeout_seconds: float = 60.0,
        *,
        network_isolation: bool | None = None,
        flake_rerun_count: int | None = None,
    ) -> None:
        type(self).calls.append(
            {
                "timeout_seconds": timeout_seconds,
                "network_isolation": network_isolation,
                "flake_rerun_count": flake_rerun_count,
            }
        )
        super().__init__(
            timeout_seconds,
            network_isolation=network_isolation,
            flake_rerun_count=flake_rerun_count,
        )


@pytest.fixture
def recording(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    _RecordingSandbox.calls = []
    monkeypatch.setattr(api_swe, "VerifierSandbox", _RecordingSandbox)
    return _RecordingSandbox.calls


def test_omitted_configuration_is_resolved_from_settings_and_passed_explicitly(
    recording: list[dict[str, Any]],
) -> None:
    get_settings.cache_clear()
    settings = get_settings()
    with SweVerifier() as verifier:
        assert verifier.network_isolation is settings.verifier_network_isolation
        assert verifier.flake_rerun_count == settings.flake_rerun_count
    assert recording == [
        {
            "timeout_seconds": settings.verifier_timeout_seconds,
            "network_isolation": settings.verifier_network_isolation,
            "flake_rerun_count": settings.flake_rerun_count,
        }
    ]


def test_explicit_configuration_is_passed_through_unchanged(
    recording: list[dict[str, Any]],
) -> None:
    with SweVerifier(timeout_seconds=5.0, network_isolation=False, flake_rerun_count=2) as v:
        assert (v.network_isolation, v.flake_rerun_count) == (False, 2)
    assert recording == [
        {"timeout_seconds": 5.0, "network_isolation": False, "flake_rerun_count": 2}
    ]


def test_timeout_alone_resolves_from_settings_when_the_rest_is_explicit(
    recording: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VELITH_VERIFIER_TIMEOUT_SECONDS", "17.5")
    get_settings.cache_clear()
    try:
        with SweVerifier(network_isolation=False, flake_rerun_count=2):
            pass
    finally:
        get_settings.cache_clear()
    assert recording == [
        {"timeout_seconds": 17.5, "network_isolation": False, "flake_rerun_count": 2}
    ]


@pytest.mark.parametrize("reruns", [0, -1])
def test_rerun_count_below_one_is_refused(reruns: int) -> None:
    with pytest.raises(ValueError, match="flake_rerun_count"):
        SweVerifier(network_isolation=False, flake_rerun_count=reruns)


def test_identity_is_the_swe_component_at_its_component_version() -> None:
    # D35 r2: the wire version is the SWE component constant, not the package version.
    with SweVerifier(network_isolation=False, flake_rerun_count=3) as verifier:
        assert verifier.identity.component == SWE_VERIFIER_COMPONENT
        assert verifier.identity.version == SWE_VERIFIER_VERSION == "0.1.0"


# --- Task resolution and pre-run checks -------------------------------------------------------


def test_resolves_only_the_v0_fixture_task() -> None:
    task = resolve_task(EngineeringTask(task_id=FIXTURE_TASK_ID), fixtures_root=_FIXTURES_ROOT)
    assert task.task_id == FIXTURE_TASK_ID
    assert task.repo_path == _FIXTURES_ROOT / FIXTURE_TASK_ID
    assert task.secondary_test_command  # v0 tasks must carry a held-out secondary suite
    with pytest.raises(ContractError, match="unsupported"):
        resolve_task(EngineeringTask(task_id="other_task"))


def _refuse_to_run(self: VerifierSandbox, task: object, patch: str) -> SandboxVerdict:
    raise AssertionError("the sandbox must not run")


def test_unknown_task_is_refused_before_any_sandbox_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(VerifierSandbox, "verify", _refuse_to_run)
    with (
        SweVerifier(network_isolation=False, flake_rerun_count=3) as verifier,
        pytest.raises(ContractError),
    ):
        verifier.evaluate(EngineeringTask(task_id="other_task"), _artifact("other_task"))


def test_mismatched_artifact_is_refused_before_any_sandbox_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(VerifierSandbox, "verify", _refuse_to_run)
    with (
        SweVerifier(network_isolation=False, flake_rerun_count=3) as verifier,
        pytest.raises(ContractError, match="does not belong"),
    ):
        verifier.evaluate(EngineeringTask(task_id=FIXTURE_TASK_ID), _artifact("other_task"))


# --- Noetica Verifier protocol ------------------------------------------------------------------


def test_conforms_to_the_noetica_verifier_protocol() -> None:
    with SweVerifier(network_isolation=False, flake_rerun_count=3) as verifier:
        assert isinstance(verifier, Verifier)


def test_protocol_verify_reports_status_and_signals_in_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fixed(self: VerifierSandbox, task: object, patch: str) -> SandboxVerdict:
        return _sandbox_verdict(VerdictState.PASSED, flaky=False, secondary=False)

    monkeypatch.setattr(VerifierSandbox, "verify", _fixed)
    with SweVerifier(
        fixtures_root=_FIXTURES_ROOT, network_isolation=True, flake_rerun_count=3
    ) as v:
        verdict = v.verify(EngineeringTask(task_id=FIXTURE_TASK_ID), _artifact())
    assert isinstance(verdict, Verdict)
    assert verdict.status is VerdictStatus.PASSED
    assert verdict.confidence == 1.0
    assert dict(verdict.detail) == {
        "flaky": False,
        "flake_rerun_count": 3,
        "secondary_passed": False,
        "network_isolated": True,
    }


def test_protocol_verify_refuses_foreign_inputs() -> None:
    with (
        SweVerifier(network_isolation=False, flake_rerun_count=3) as verifier,
        pytest.raises(ContractError),
    ):
        verifier.verify("calc_add_bug", "patch text")


# --- Import boundary: the contract package does not load the harness --------------------------


def test_importing_the_contract_does_not_load_the_harness() -> None:
    probe = (
        "import sys, velith.api; "
        "loaded = sorted(m for m in sys.modules "
        "if m.startswith(('velith.harness', 'velith.api.swe', 'velith.core.config'))); "
        "print(loaded); sys.exit(1 if loaded else 0)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ),
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
