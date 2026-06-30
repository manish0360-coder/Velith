"""The deterministic verifier sandbox (M1 spec §7/§10, handoff §4.4).

``VerifierSandbox`` is the single seam where a candidate patch is *disposed of*: it
applies the patch to a disposable copy of the task's repository and runs the hidden
test suite **inside the container**, returning a structured :class:`Verdict`. No
model is involved and nothing here judges correctness with a model — the verdict is
computed by ``git apply`` + running the hidden tests (D3, D16.7). This is the seam
M2 hardens (network isolation of the test step, flake detection, bit-for-bit
determinism); M1 keeps it functional, not hardened.

Determinism by isolation (M1 spec §7). The sandbox operates on a **disposable copy**
of the fixture repo — never the committed fixture under ``tests/fixtures/`` — held
as a git repository. Before each verification it restores a clean baseline with
``git reset --hard`` then ``git clean -fd``, guarded by an asserted working-directory
check that refuses to run those destructive commands unless the target is the
disposable workspace under the system temp dir with its own ``.git`` (RK13). The
patch-apply mechanism is pinned to ``git apply``; a clean non-apply maps to
``PATCH_APPLY_FAILED`` and is an *outcome*, never an exception.

Outcome vs. error (D16.7). A test failure, a non-applying patch — these are verdict
states, never raised. Only an infrastructure fault (git missing, copy/exec failure)
raises :class:`SandboxExecutionError`; the orchestrator maps that to ``INFRA_ERROR``.

Configuration note (raised, not silently resolved — handoff preamble): the verifier
timeout is a ``Settings`` field added in C7 (commit plan §4.8). To keep C4 atomic and
green, the timeout is injected via the constructor with a default; the orchestrator
(C7) will read it from ``Settings`` and pass it in — the same injection pattern used
for the episode store path in C2.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from types import TracebackType
from typing import Final

from pydantic import BaseModel, ConfigDict

from velith.core.config import get_settings
from velith.core.logging import get_logger
from velith.episodes.episode import VerdictState
from velith.task import Task

logger = get_logger(__name__)

#: Default wall-clock budget for hidden-test execution (seconds). Injected here in
#: M1; sourced from validated Settings by the orchestrator at C7 (see module note).
DEFAULT_TIMEOUT_SECONDS: Final[float] = 60.0

# Hidden-test runners print a wall-clock duration (e.g. "1 passed in 0.04s") that
# varies run to run. It is stripped from the captured output so the verdict — and
# therefore the episode content hash, which includes verdict_output (M1 spec §9.1.1)
# — is reproducible for a fixed patch (D16.1). Excluding the volatile timing *fields*
# from the hash is insufficient if timing also leaks into the hashed output text.
_DURATION_RE = re.compile(r"in \d+\.\d+s")


def _normalize_test_output(text: str) -> str:
    """Strip non-deterministic timing from captured hidden-test output (D16.1)."""
    return _DURATION_RE.sub("in <duration>", text)


def _network_isolation_available() -> bool:
    """True iff ``unshare -n`` can create a network namespace here (D19).

    Requires CAP_SYS_ADMIN under Docker Desktop/WSL2 (the R3 prototype showed
    unprivileged ``unshare -rn`` is blocked by seccomp). Used to skip
    isolation-dependent tests where the capability is absent, and to refuse to run
    untrusted code unisolated when isolation is required.
    """
    try:
        proc = subprocess.run(
            ["unshare", "-n", "--", "true"],
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


# Fixed environment injected into the hidden-test process so the verdict is
# reproducible to Determinism Level 4 (M2_SPEC §7, D18): hash randomization, time
# zone, and locale are pinned, and bytecode writing is disabled. These are
# invariants, not tunables — varying them would break Level 4 — so they live here
# as a verifier constant rather than as operator-facing Settings fields.
_DETERMINISTIC_ENV: Final[dict[str, str]] = {
    "PYTHONHASHSEED": "0",
    "TZ": "UTC",
    "LC_ALL": "C",
    "PYTHONDONTWRITEBYTECODE": "1",
}


class SandboxExecutionError(Exception):
    """Raised on an infrastructure fault in the verifier (git missing, exec error).

    This is the only failure the verifier raises. Test failures and non-applying
    patches are verdict *states*, not exceptions (D16.7). The orchestrator maps this
    error to the ``INFRA_ERROR`` verdict and a non-zero exit.
    """


class Verdict(BaseModel):
    """The structured outcome of one verification.

    ``secondary_passed`` is the M2 held-out-secondary slot and stays ``None`` in M1.
    ``duration_seconds`` is the wall-clock time of the whole verify() call (the M1
    ``verify_seconds`` signal).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    state: VerdictState
    output: str
    secondary_passed: bool | None = None
    duration_seconds: float


class VerifierSandbox:
    """Apply a candidate patch and run the hidden tests on a disposable copy.

    Holds one disposable git workspace per task, created on first use and reused
    across calls (reset to a clean baseline before each verification). Use as a
    context manager, or call :meth:`close` to remove the workspace.
    """

    def __init__(
        self,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        *,
        network_isolation: bool | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        # Isolation defaults to the validated Settings value (mandatory in
        # production); tests pass it explicitly to opt in/out (D19).
        self._network_isolation = (
            network_isolation
            if network_isolation is not None
            else get_settings().verifier_network_isolation
        )
        self._root: Path | None = None
        self._workspace: Path | None = None
        self._task_id: str | None = None

    @property
    def workspace(self) -> Path | None:
        """The current disposable workspace path, or ``None`` before first verify."""
        return self._workspace

    def __enter__(self) -> VerifierSandbox:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Remove the disposable workspace and reset internal state."""
        if self._root is not None and self._root.exists():
            shutil.rmtree(self._root, ignore_errors=True)
        self._root = None
        self._workspace = None
        self._task_id = None

    def verify(self, task: Task, patch: str) -> Verdict:
        """Dispose of ``patch`` against ``task``'s hidden tests; return a Verdict.

        Deterministic given a fixed patch and task: the workspace is reset to its
        pristine baseline before the patch is applied, so prior state cannot leak.
        Raises :class:`SandboxExecutionError` only on infrastructure faults.
        """
        start = time.monotonic()
        workspace = self._ensure_workspace(task)
        self._restore_clean_state(workspace)
        logger.info(
            "verification started",
            extra={"event": "verify_started", "task_id": task.task_id},
        )

        apply_proc = self._git(["apply"], cwd=workspace, check=False, input_text=patch)
        if apply_proc.returncode != 0:
            return self._finish(VerdictState.PATCH_APPLY_FAILED, apply_proc.stderr, task, start)

        # Phase 1 (network ON) is the workspace prep above. Phase 2 runs the hidden
        # test, network-isolated when configured (D19); this may raise if isolation
        # is required but unavailable, so untrusted code is never run unisolated.
        command = self._phase2_command(task.hidden_test_command)
        try:
            test_proc = subprocess.run(
                command,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                env={**os.environ, **_DETERMINISTIC_ENV},
            )
        except subprocess.TimeoutExpired:
            message = f"hidden test exceeded the {self._timeout:.0f}s wall-clock budget"
            return self._finish(VerdictState.FAILED, message, task, start)
        except OSError as exc:
            raise SandboxExecutionError(f"failed to execute hidden test: {exc}") from exc

        state = VerdictState.PASSED if test_proc.returncode == 0 else VerdictState.FAILED
        output = _normalize_test_output((test_proc.stdout or "") + (test_proc.stderr or ""))
        return self._finish(state, output, task, start)

    # --- internals -----------------------------------------------------------

    def _phase2_command(self, hidden_test_command: tuple[str, ...]) -> list[str]:
        """Wrap the hidden-test command for Phase-2 network isolation (D19).

        With isolation on, the test runs in a fresh network namespace (``unshare -n``,
        needs CAP_SYS_ADMIN). If the capability is unavailable, raise rather than run
        untrusted code unisolated. With isolation off (a sanctioned non-production
        setting), the command runs as-is.
        """
        if not self._network_isolation:
            return list(hidden_test_command)
        if not _network_isolation_available():
            raise SandboxExecutionError(
                "network isolation is required but unavailable (needs CAP_SYS_ADMIN "
                "for `unshare -n`); refusing to run untrusted code unisolated"
            )
        return ["unshare", "-n", "--", *hidden_test_command]

    def _finish(self, state: VerdictState, output: str, task: Task, start: float) -> Verdict:
        duration = time.monotonic() - start
        logger.info(
            "verification completed",
            extra={
                "event": "verify_completed",
                "task_id": task.task_id,
                "verdict_state": state.value,
                "verify_seconds": duration,
            },
        )
        return Verdict(state=state, output=output, duration_seconds=duration)

    def _ensure_workspace(self, task: Task) -> Path:
        """Return a disposable git workspace for ``task``, creating it once."""
        if self._workspace is not None and self._task_id == task.task_id:
            return self._workspace
        if not task.repo_path.is_dir():
            raise SandboxExecutionError(f"task repo_path does not exist: {task.repo_path}")
        self.close()
        self._root = Path(tempfile.mkdtemp(prefix="velith-verifier-"))
        workspace = self._root / task.task_id
        shutil.copytree(
            task.repo_path,
            workspace,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"),
        )
        self._git(["init", "-q"], cwd=workspace)
        self._git(["add", "-A"], cwd=workspace)
        self._git(
            [
                "-c",
                "user.email=verifier@velith.local",
                "-c",
                "user.name=velith-verifier",
                "commit",
                "-q",
                "-m",
                "baseline",
            ],
            cwd=workspace,
        )
        self._workspace = workspace
        self._task_id = task.task_id
        return workspace

    def _restore_clean_state(self, workspace: Path) -> None:
        """Reset the workspace to its baseline, guarded against blast radius (RK13)."""
        self._assert_safe_workspace(workspace)
        self._git(["reset", "--hard", "-q"], cwd=workspace)
        self._git(["clean", "-f", "-d", "-q"], cwd=workspace)

    def _assert_safe_workspace(self, workspace: Path) -> None:
        """Refuse destructive git ops unless ``workspace`` is the disposable repo."""
        resolved = workspace.resolve()
        temp_root = Path(tempfile.gettempdir()).resolve()
        if temp_root not in resolved.parents:
            raise SandboxExecutionError(
                f"refusing destructive git operation outside the temp workspace: {resolved}"
            )
        if not (resolved / ".git").is_dir():
            raise SandboxExecutionError(
                f"refusing destructive git operation: not a git workspace: {resolved}"
            )

    def _git(
        self,
        args: list[str],
        cwd: Path,
        *,
        check: bool = True,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run a git command; raise SandboxExecutionError on infra fault.

        With ``check=True`` a non-zero exit is an infrastructure fault. ``git apply``
        is run with ``check=False`` so a non-applying patch is inspected and mapped to
        ``PATCH_APPLY_FAILED`` rather than raising.
        """
        try:
            proc = subprocess.run(
                ["git", *args],
                cwd=cwd,
                capture_output=True,
                text=True,
                input=input_text,
                timeout=self._timeout,
            )
        except FileNotFoundError as exc:
            raise SandboxExecutionError(
                "git not found in the container; the verifier requires it (M1 spec §13)"
            ) from exc
        except OSError as exc:
            raise SandboxExecutionError(f"git execution failed: {exc}") from exc
        if check and proc.returncode != 0:
            raise SandboxExecutionError(f"git {args[0]} failed: {proc.stderr.strip()}")
        return proc
