"""Engineering API v0 software verifier: sandbox verdict -> API evidence (D33, API-0 C2).

``SweVerifier`` is Velith's software-engineering oracle behind Noetica's ``Verifier`` protocol
(Law 15; D30 item 3). It wraps the frozen M2 ``VerifierSandbox`` without modifying it and turns one
grounded sandbox verdict into :class:`~velith.api.contract.VerificationEvidence`, then into a public
:class:`~velith.api.contract.EngineeringResult` or an
:class:`~velith.api.contract.UnverifiedOutcome` through the single producer path
:func:`~velith.api.contract.result_from_verification`.

K1 (ratified). The sandbox keeps its isolation flag and rerun count private and its verdict does not
record them. ``SweVerifier`` therefore constructs the sandbox itself, passing both values explicitly
through the sandbox's public constructor, and reports exactly those values as evidence. With
isolation on, the sandbox either runs every test command under ``unshare -n`` or raises; it never
runs them unisolated.

K2 (ratified). An infrastructure fault (``SandboxExecutionError``) propagates. It is not a grounded
outcome (D16.7), so no result, no outcome and no record is produced for it.

This module is deliberately not re-exported by ``velith.api``: importing the contract must not load
the harness. Import it as ``velith.api.swe``.
"""

from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import Any, Final

from noetica.interfaces.provenance import Provenance
from noetica.interfaces.verification import Verdict

from velith import __version__
from velith.api.contract import (
    SWE_VERIFIER_COMPONENT,
    VERDICT_STATUS_BY_STATE,
    ContractError,
    DesignArtifact,
    EngineeringResult,
    EngineeringTask,
    UnverifiedOutcome,
    VerificationEvidence,
    VerifierIdentity,
    result_from_verification,
)
from velith.core.config import get_settings
from velith.harness.verifier_sandbox import Verdict as SandboxVerdict
from velith.harness.verifier_sandbox import VerifierSandbox
from velith.task import FIXTURE_TASK_ID, Task, load_fixture_task

#: The provenance ``transform``: the frozen seam that produced the grounded verdict.
PROVENANCE_TRANSFORM: Final[str] = "velith.harness.VerifierSandbox.verify"


def resolve_task(task: EngineeringTask, *, fixtures_root: Path | None = None) -> Task:
    """Resolve an API task to the frozen Velith ``Task`` it names.

    v0 resolves exactly one software task, the ``calc_add_bug`` fixture. ``fixtures_root``
    defaults to ``tests/fixtures`` relative to the working directory (the repository root, or
    ``/app`` in the verifier container), so the verifier is usable only where the fixtures exist.
    """
    if task.domain != "software" or task.task_id != FIXTURE_TASK_ID:
        raise ContractError(f"unsupported engineering task in v0: {task.domain}/{task.task_id}")
    return load_fixture_task(fixtures_root)


def evidence_from_sandbox_verdict(
    verdict: SandboxVerdict, *, flake_rerun_count: int, network_isolated: bool
) -> VerificationEvidence:
    """Map one sandbox verdict to API evidence. Pure: no I/O, no defaults.

    ``flake_rerun_count`` and ``network_isolated`` must be the values supplied to the sandbox that
    produced ``verdict`` (K1); the verdict itself does not record them.
    """
    return VerificationEvidence(
        verdict_status=VERDICT_STATUS_BY_STATE[verdict.state],
        flaky=verdict.flaky,
        flake_rerun_count=flake_rerun_count,
        secondary_passed=verdict.secondary_passed,
        network_isolated=network_isolated,
    )


class SweVerifier:
    """The v0 software verifier. Use as a context manager, or call :meth:`close`.

    Configuration left as ``None`` is resolved once from the validated ``Settings``
    (``verifier_timeout_seconds``, ``verifier_network_isolation``, ``flake_rerun_count``), as the
    frozen spike does for the timeout; explicitly supplied values are kept. The resolved values are
    passed explicitly to the one ``VerifierSandbox`` this instance owns.
    """

    def __init__(
        self,
        *,
        fixtures_root: Path | None = None,
        timeout_seconds: float | None = None,
        network_isolation: bool | None = None,
        flake_rerun_count: int | None = None,
    ) -> None:
        if timeout_seconds is None or network_isolation is None or flake_rerun_count is None:
            settings = get_settings()
            if timeout_seconds is None:
                timeout_seconds = settings.verifier_timeout_seconds
            if network_isolation is None:
                network_isolation = settings.verifier_network_isolation
            if flake_rerun_count is None:
                flake_rerun_count = settings.flake_rerun_count
        if flake_rerun_count < 1:
            raise ValueError(f"flake_rerun_count must be at least 1, got {flake_rerun_count}")
        self._fixtures_root = fixtures_root
        self._network_isolation: bool = network_isolation
        self._flake_rerun_count: int = flake_rerun_count
        self._sandbox = VerifierSandbox(
            timeout_seconds,
            network_isolation=self._network_isolation,
            flake_rerun_count=self._flake_rerun_count,
        )

    @property
    def network_isolation(self) -> bool:
        """The isolation flag supplied to the sandbox."""
        return self._network_isolation

    @property
    def flake_rerun_count(self) -> int:
        """The primary-test rerun count supplied to the sandbox."""
        return self._flake_rerun_count

    @property
    def identity(self) -> VerifierIdentity:
        """``verifier`` on the wire: this component at the running Velith version."""
        return VerifierIdentity(component=SWE_VERIFIER_COMPONENT, version=__version__)

    def __enter__(self) -> SweVerifier:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Remove the sandbox's disposable workspace."""
        self._sandbox.close()

    def _measure(
        self, task: EngineeringTask, artifact: DesignArtifact
    ) -> tuple[VerificationEvidence, SandboxVerdict]:
        """Run the sandbox once on the artifact's patch. ``SandboxExecutionError`` propagates."""
        if artifact.payload.task_id != task.task_id or artifact.payload.domain != task.domain:
            raise ContractError("design artifact does not belong to the engineering task")
        sandbox_verdict = self._sandbox.verify(
            resolve_task(task, fixtures_root=self._fixtures_root), artifact.payload.patch.text
        )
        evidence = evidence_from_sandbox_verdict(
            sandbox_verdict,
            flake_rerun_count=self._flake_rerun_count,
            network_isolated=self._network_isolation,
        )
        return evidence, sandbox_verdict

    def evaluate(
        self, task: EngineeringTask, artifact: DesignArtifact
    ) -> EngineeringResult | UnverifiedOutcome:
        """Verify ``artifact`` for ``task``: a public result if the evidence qualifies, else an
        outcome. Raises ``SandboxExecutionError`` on an infrastructure fault (K2)."""
        evidence, sandbox_verdict = self._measure(task, artifact)
        provenance = Provenance(
            source=SWE_VERIFIER_COMPONENT,
            transform=PROVENANCE_TRANSFORM,
            inputs=(task.task_id, artifact.content_hash),
            attributes={
                "velith_version": __version__,
                "duration_seconds": sandbox_verdict.duration_seconds,
            },
        )
        return result_from_verification(
            task, artifact, evidence, verifier=self.identity, provenance=provenance
        )

    def verify(self, task: Any, candidate: Any) -> Verdict:
        """Noetica ``Verifier`` protocol: the grounded verdict as a Noetica ``Verdict``.

        ``confidence`` stays 1.0 (the software oracle is exact); the measurement-quality and
        model-gap signals are carried in ``detail`` rather than hidden (Law 16).
        """
        if not isinstance(task, EngineeringTask) or not isinstance(candidate, DesignArtifact):
            raise ContractError("verify expects an EngineeringTask and a DesignArtifact")
        evidence, _ = self._measure(task, candidate)
        return Verdict(
            status=evidence.verdict_status,
            detail={
                "flaky": evidence.flaky,
                "flake_rerun_count": evidence.flake_rerun_count,
                "secondary_passed": evidence.secondary_passed,
                "network_isolated": evidence.network_isolated,
            },
        )
