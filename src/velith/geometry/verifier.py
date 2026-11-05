"""G0 geometry verifier: parent side of the isolated measurement worker (spec F r3 §5-§6).

:class:`GeometryVerifier` implements Noetica's ``Verifier`` protocol for one ``model/step`` design
artifact and declared requirements. It never imports ``OCP``: measurement runs in a child process
(``velith.geometry._kernel``) under resource limits, and the parent classifies every abnormal exit
from **structured, parent-side observations only** (CH3-W1): its own wall-clock timeout flag, the
``wait4`` status, rusage CPU time, the sizes of the worker's output and stderr files measured by the
parent, and one reserved exit code. Child-written text is never read for classification; stderr is
kept, bounded, in the local diagnostic record for humans.

Abnormal exits produce nothing (G-ABEXIT): every classification raises
:class:`GeometryExecutionError` with no ``GeometryEngineeringResult``, no
``GeometryUnverifiedOutcome`` and no wire object, so a consumer cannot reach a positive outcome.

Deployment gate (spec §6): a container plus a seccomp profile is mandatory before any networked or
multi-tenant deployment. A compromised worker can choose its exit code (that only changes the
diagnostic label); it cannot produce a result without a valid protocol document, which the parent
validates and re-derives every fact and verdict from.
"""

from __future__ import annotations

import json
import os
import platform
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any, Final

from noetica.interfaces.provenance import Provenance
from noetica.interfaces.verification import Verdict, VerdictStatus
from pydantic import ValidationError

from velith import __version__
from velith.api.contract import ContractError, VerifierIdentity
from velith.api.geometry_contract import (
    BINDING,
    BINDING_VERSION,
    GEOMETRY_VERIFIER_COMPONENT,
    GEOMETRY_VERIFIER_VERSION,
    IDENTITY_PLATFORM,
    KERNEL_VERSION,
    PLATFORM_POLICY,
    QUANTIZATION_RULE,
    GeometryEngineeringResult,
    GeometryTask,
    GeometryUnverifiedOutcome,
    StepArtifact,
    geometry_result,
)
from velith.geometry import annotation_scan, rules
from velith.geometry._protocol import EXIT_MEMORY, WORKER_MODULE

PROVENANCE_TRANSFORM: Final[str] = "velith.geometry._kernel.measure"
STDERR_TAIL_BYTES: Final[int] = 4096
DEFAULT_DIAG_DIR: Final[Path] = Path("data/geometry_diag")
_POLL_SECONDS: Final[float] = 0.05


@dataclass(frozen=True)
class WorkerLimits:
    """Worker limits (spec §6 defaults; tune at C3 from measurements). ``RLIMIT_CPU`` counts all
    threads, and OCCT meshing is multithreaded."""

    address_space_bytes: int = 2 * 1024**3
    cpu_soft_s: int = 60
    cpu_hard_s: int = 65
    wall_timeout_s: float = 120.0
    output_bytes: int = 8 * 1024**2

    def child_json(self) -> str:
        values = asdict(self)
        values.pop("wall_timeout_s")
        return json.dumps(values, sort_keys=True)


class GeometryExecutionError(Exception):
    """An abnormal worker exit (or an unsupported platform). Never a grounded outcome: no result,
    no outcome, no wire object. ``diagnostic`` is the retained local record."""

    def __init__(self, classification: str, diagnostic: Mapping[str, Any]) -> None:
        super().__init__(classification)
        self.classification = classification
        self.diagnostic = dict(diagnostic)


def classify(
    status: int,
    *,
    timed_out: bool,
    cpu_seconds: float,
    output_bytes: int,
    stderr_bytes: int,
    limits: WorkerLimits,
) -> str | None:
    """Structured parent-side classification of the worker's exit (spec F r3 §6), in order.

    ``None`` means a normal exit (code 0 within the output limit); the protocol document is then
    validated separately (``PROTOCOL_ERROR`` if it is missing or invalid).
    """
    if timed_out:
        return "WALL_TIMEOUT"
    if os.WIFSIGNALED(status):
        number = os.WTERMSIG(status)
        if number == signal.SIGXCPU:
            return "CPU_LIMIT"
        if number == signal.SIGKILL and cpu_seconds >= limits.cpu_soft_s:
            return "CPU_LIMIT"  # hard CPU limit, evidenced by rusage
        if number == signal.SIGXFSZ:
            return "OUTPUT_LIMIT"
        try:
            return f"SIGNAL_{signal.Signals(number).name}"
        except ValueError:
            return f"SIGNAL_{number}"
    if max(output_bytes, stderr_bytes) >= limits.output_bytes:
        return "OUTPUT_LIMIT"  # CPython ignores SIGXFSZ; the parent sees a full-size file
    code = os.WEXITSTATUS(status)
    if code == EXIT_MEMORY:
        return "MEMORY_LIMIT"
    if code != 0:
        return f"NONZERO_EXIT_{code}"
    return None


def _binding_kernel_version() -> str | None:
    try:
        files = metadata.files(BINDING) or []
    except metadata.PackageNotFoundError:
        return None
    for entry in files:
        name = Path(str(entry)).name
        if name.startswith("libTKernel") and ".so." in name:
            return name.split(".so.", 1)[1]
    return None


def platform_support() -> str | None:
    """``None`` if this host is the identity-supported platform with the pinned wheel (spec §6,
    R-API-3); otherwise the reason. Checked before any parsing."""
    if not (sys.platform == "linux" and platform.machine() == "x86_64"):
        host = f"{sys.platform}/{platform.machine()}"
        return f"identity platform is {IDENTITY_PLATFORM}; this host is {host}"
    try:
        installed = metadata.version(BINDING)
    except metadata.PackageNotFoundError:
        return f"{BINDING} is not installed (install velith[geometry])"
    if installed != BINDING_VERSION:
        return f"{BINDING} {installed} installed; {BINDING_VERSION} pinned"
    kernel = _binding_kernel_version()
    if kernel != KERNEL_VERSION:
        return f"OCCT {kernel} found in the binding; {KERNEL_VERSION} pinned"
    return None


def _reject_constant(token: str) -> Any:
    raise ValueError(f"non-finite JSON token {token}")


class GeometryVerifier:
    """The G0 verifier (D34). Noetica ``Verifier`` protocol: :meth:`verify`.

    ``worker_command`` replaces the worker invocation (tests only); the verifier appends
    ``LIMITS_JSON STEP_PATH OUT_PATH REQUIREMENTS_JSON``. ``diag_dir=None`` disables the
    diagnostic record.
    """

    def __init__(
        self,
        *,
        limits: WorkerLimits | None = None,
        diag_dir: Path | None = DEFAULT_DIAG_DIR,
        worker_command: Sequence[str] | None = None,
        platform_check: Callable[[], str | None] = platform_support,
    ) -> None:
        self._limits = limits or WorkerLimits()
        self._diag_dir = diag_dir
        self._worker_command = list(worker_command or [sys.executable, "-I", "-m", WORKER_MODULE])
        self._platform_check = platform_check

    @property
    def identity(self) -> VerifierIdentity:
        """``verifier`` on the wire: the geometry component at its own version (D35 r2 item 1)."""
        return VerifierIdentity(
            component=GEOMETRY_VERIFIER_COMPONENT, version=GEOMETRY_VERIFIER_VERSION
        )

    @property
    def limits(self) -> WorkerLimits:
        return self._limits

    # -- worker ------------------------------------------------------------------------------

    def _diagnostic(
        self, classification: str, artifact: StepArtifact, **observed: Any
    ) -> dict[str, Any]:
        return {
            "classification": classification,
            "input_sha256": artifact.content_hash,
            "kernel_version": KERNEL_VERSION,
            "binding": BINDING,
            "binding_version": BINDING_VERSION,
            "quantization_rule": QUANTIZATION_RULE,
            "platform": IDENTITY_PLATFORM,
            "platform_policy": PLATFORM_POLICY,
            "limits": asdict(self._limits),
            **observed,
        }

    def _fail(self, classification: str, diagnostic: dict[str, Any]) -> GeometryExecutionError:
        if self._diag_dir is not None:
            self._diag_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            name = f"{diagnostic['input_sha256'].removeprefix('sha256:')}__{stamp}.json"
            with open(self._diag_dir / name, "x", encoding="utf-8") as handle:  # write-once
                json.dump(diagnostic, handle, indent=1, sort_keys=True)
        return GeometryExecutionError(classification, diagnostic)

    def measure(self, task: GeometryTask, artifact: StepArtifact) -> rules.RawMeasurement:
        """Run the isolated worker once and return its validated document.

        Raises :class:`GeometryExecutionError` for ``PLATFORM_UNSUPPORTED`` (before parsing) and
        for every abnormal exit.
        """
        unsupported = self._platform_check()
        if unsupported is not None:
            raise self._fail(
                "PLATFORM_UNSUPPORTED",
                self._diagnostic("PLATFORM_UNSUPPORTED", artifact, detail=unsupported),
            )
        with tempfile.TemporaryDirectory(prefix="velith-g0-") as workdir:
            step_path = os.path.join(workdir, "input.step")
            out_path = os.path.join(workdir, "out.json")
            err_path = os.path.join(workdir, "stderr.txt")
            with open(step_path, "wb") as handle:
                handle.write(artifact.payload)
            command = [
                *self._worker_command,
                self._limits.child_json(),
                step_path,
                out_path,
                json.dumps(task.requirements, sort_keys=True),
            ]
            started = time.monotonic()
            timed_out = False
            with open(err_path, "wb") as stderr:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=stderr,
                    cwd=workdir,
                )
                deadline = started + self._limits.wall_timeout_s
                while True:
                    pid, status, usage = os.wait4(process.pid, os.WNOHANG)
                    if pid:
                        break
                    if time.monotonic() > deadline:
                        process.kill()
                        pid, status, usage = os.wait4(process.pid, 0)
                        timed_out = True
                        break
                    time.sleep(_POLL_SECONDS)
                process.returncode = (
                    -os.WTERMSIG(status) if os.WIFSIGNALED(status) else os.WEXITSTATUS(status)
                )
            wall = time.monotonic() - started
            cpu = usage.ru_utime + usage.ru_stime
            output_size = os.path.getsize(out_path) if os.path.exists(out_path) else 0
            stderr_size = os.path.getsize(err_path)
            with open(err_path, "rb") as handle:
                handle.seek(max(0, stderr_size - STDERR_TAIL_BYTES))
                tail = handle.read().decode("utf-8", "replace")
            observed = {
                "raw_status": status,
                "signal": os.WTERMSIG(status) if os.WIFSIGNALED(status) else None,
                "exit_code": os.WEXITSTATUS(status) if os.WIFEXITED(status) else None,
                "wall_s": round(wall, 3),
                "cpu_s": round(cpu, 3),
                "max_rss_kib": usage.ru_maxrss,
                "output_bytes": output_size,
                "stderr_bytes": stderr_size,
                "stderr_tail": tail,  # for humans only; never classified
            }
            classification = classify(
                status,
                timed_out=timed_out,
                cpu_seconds=cpu,
                output_bytes=output_size,
                stderr_bytes=stderr_size,
                limits=self._limits,
            )
            if classification is None:
                try:
                    with open(out_path, encoding="utf-8") as handle:
                        text = handle.read()  # the whole document (bounded by RLIMIT_FSIZE)
                    json.loads(text, parse_constant=_reject_constant)
                    return rules.RawMeasurement.model_validate_json(text)
                except (OSError, ValueError, ValidationError):
                    classification = "PROTOCOL_ERROR"
            raise self._fail(classification, self._diagnostic(classification, artifact, **observed))

    # -- verification ------------------------------------------------------------------------

    def evaluate(
        self, task: GeometryTask, artifact: StepArtifact
    ) -> GeometryEngineeringResult | GeometryUnverifiedOutcome:
        """Verify ``artifact`` against ``task.requirements`` (G-RULE, spec §5).

        Returns a verified result or an outcome with the first failing reason. Raises
        :class:`GeometryExecutionError` on any abnormal worker exit (no result, no outcome).
        """
        if not isinstance(task, GeometryTask) or not isinstance(artifact, StepArtifact):
            raise ContractError("evaluate expects a GeometryTask and a StepArtifact")
        started = time.monotonic()
        raw = self.measure(task, artifact)
        try:
            evaluation = rules.evaluate(
                raw,
                task.requirements,
                artifact_content_hash=artifact.content_hash,
                annotations=annotation_scan.scan(artifact.payload),
            )
        except ValueError as exc:  # internally inconsistent worker document
            raise self._fail(
                "PROTOCOL_ERROR", self._diagnostic("PROTOCOL_ERROR", artifact, detail=str(exc))
            ) from exc
        if evaluation.reason is not None:
            return GeometryUnverifiedOutcome(
                task_id=task.task_id,
                verdict=VerdictStatus.FAILED,
                reason=evaluation.reason,
                facts=evaluation.facts,
            )
        assert evaluation.facts is not None
        provenance = Provenance(
            source=GEOMETRY_VERIFIER_COMPONENT,
            transform=PROVENANCE_TRANSFORM,
            inputs=(task.task_id, artifact.content_hash),
            attributes={
                "velith_version": __version__,
                "duration_seconds": round(time.monotonic() - started, 3),
            },
        )
        return geometry_result(
            task, artifact, evaluation.facts, verifier=self.identity, provenance=provenance
        )

    def verify(self, task: Any, candidate: Any) -> Verdict:
        """Noetica ``Verifier`` protocol: ``PASSED`` (confidence 1.0, exact) or ``FAILED`` with
        ``detail.reason``. ``GeometryExecutionError`` propagates: it is not a grounded outcome."""
        outcome = self.evaluate(task, candidate)
        if isinstance(outcome, GeometryEngineeringResult):
            return Verdict(status=VerdictStatus.PASSED, confidence=1.0, detail={})
        return Verdict(
            status=VerdictStatus.FAILED, confidence=1.0, detail={"reason": outcome.reason.value}
        )
