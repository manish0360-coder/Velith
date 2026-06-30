"""Unit tests for the deterministic verifier sandbox (C4).

These pin the C4 Definition of Done and rollback conditions (handoff §5/§6) with
REAL local execution against the C3 fixture: a good patch passes, a patch that
applies but does not fix fails, a malformed patch is PATCH_APPLY_FAILED, the test
timeout maps to FAILED, verification is deterministic given a fixed patch (reset
before run isolates intervening filesystem mutation), an infrastructure fault
raises rather than returning a verdict, and the committed fixture is never touched.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from velith.core.config import get_settings
from velith.episodes.episode import VerdictState
from velith.harness import verifier_sandbox as _verifier_sandbox
from velith.harness.verifier_sandbox import SandboxExecutionError, Verdict, VerifierSandbox
from velith.task import FIXTURE_TASK_ID, Task, load_fixture_task

# tests/unit/test_verifier_sandbox.py -> parents[1] is tests/
_FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"
_TASK_DIR = _FIXTURES_ROOT / FIXTURE_TASK_ID


@pytest.fixture(autouse=True)
def _network_isolation_off_by_default(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # The verdict-logic tests here are not about isolation; default it OFF so they
    # never require CAP_SYS_ADMIN (CI-safe). The isolation tests opt in explicitly.
    monkeypatch.setenv("VELITH_VERIFIER_NETWORK_ISOLATION", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _fixture_task() -> Task:
    return load_fixture_task(fixtures_root=_FIXTURES_ROOT)


def _patch(replacement: str) -> str:
    """Build a valid unified diff that rewrites the buggy line of calculator.py."""
    original = (_TASK_DIR / "calculator.py").read_text(encoding="utf-8")
    modified = original.replace("a - b", replacement)
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        modified.splitlines(keepends=True),
        fromfile="a/calculator.py",
        tofile="b/calculator.py",
    )
    return "".join(diff)


def test_good_patch_passes() -> None:
    with VerifierSandbox() as sandbox:
        verdict = sandbox.verify(_fixture_task(), _patch("a + b"))
    assert verdict.state == VerdictState.PASSED
    assert verdict.secondary_passed is None  # M1 placeholder; M2 populates it
    assert verdict.duration_seconds >= 0.0


def test_applying_patch_that_does_not_fix_fails() -> None:
    with VerifierSandbox() as sandbox:
        verdict = sandbox.verify(_fixture_task(), _patch("a * b"))
    assert verdict.state == VerdictState.FAILED


def test_malformed_patch_is_patch_apply_failed() -> None:
    with VerifierSandbox() as sandbox:
        verdict = sandbox.verify(_fixture_task(), "this is not a valid diff\n")
    assert verdict.state == VerdictState.PATCH_APPLY_FAILED


def test_test_timeout_maps_to_failed() -> None:
    task = _fixture_task().model_copy(
        update={"hidden_test_command": ("python", "-c", "import time; time.sleep(5)")}
    )
    with VerifierSandbox(timeout_seconds=0.5) as sandbox:
        verdict = sandbox.verify(task, _patch("a + b"))
    assert verdict.state == VerdictState.FAILED
    assert "budget" in verdict.output


def test_reset_before_run_isolates_state() -> None:
    task = _fixture_task()
    patch = _patch("a + b")
    with VerifierSandbox() as sandbox:
        first = sandbox.verify(task, patch)
        workspace = sandbox.workspace
        assert workspace is not None
        # Intervening mutation: a stray file and a clobbered tracked file.
        (workspace / "stray.txt").write_text("junk", encoding="utf-8")
        (workspace / "calculator.py").write_text("# clobbered\n", encoding="utf-8")
        second = sandbox.verify(task, patch)
    assert first.state == VerdictState.PASSED
    assert second.state == VerdictState.PASSED


def test_infra_fault_raises_rather_than_returning_a_verdict() -> None:
    task = _fixture_task().model_copy(update={"repo_path": Path("/does/not/exist/repo")})
    with VerifierSandbox() as sandbox, pytest.raises(SandboxExecutionError):
        sandbox.verify(task, "")


def test_committed_fixture_is_never_modified() -> None:
    source_before = (_TASK_DIR / "calculator.py").read_text(encoding="utf-8")
    with VerifierSandbox() as sandbox:
        sandbox.verify(_fixture_task(), _patch("a + b"))
    assert (_TASK_DIR / "calculator.py").read_text(encoding="utf-8") == source_before


def test_verdict_is_immutable_value_object() -> None:
    verdict = Verdict(state=VerdictState.PASSED, output="ok", duration_seconds=0.1)
    assert verdict.state == VerdictState.PASSED
    assert verdict.secondary_passed is None


def test_verdict_output_is_timing_normalized() -> None:
    with VerifierSandbox() as sandbox:
        verdict = sandbox.verify(_fixture_task(), _patch("a + b"))
    # The volatile pytest duration must not survive (D16.1: reproducible content hash).
    assert re.search(r"in \d+\.\d+s", verdict.output) is None
    assert "in <duration>" in verdict.output


# --- M2-C1: pinned deterministic execution environment -----------------------


def test_deterministic_env_is_injected_into_the_test_process() -> None:
    # Override the hidden-test command with one that asserts the pinned env is
    # present; it exits 0 (-> PASSED) only if the verifier injected the env (D18).
    env_check = (
        "import os; "
        "assert os.environ['PYTHONHASHSEED'] == '0'; "
        "assert os.environ['TZ'] == 'UTC'; "
        "assert os.environ['LC_ALL'] == 'C'; "
        "assert os.environ['PYTHONDONTWRITEBYTECODE'] == '1'"
    )
    task = _fixture_task().model_copy(update={"hidden_test_command": ("python", "-c", env_check)})
    with VerifierSandbox() as sandbox:
        verdict = sandbox.verify(task, _patch("a + b"))
    assert verdict.state == VerdictState.PASSED


def test_verify_output_is_deterministic_for_a_fixed_patch() -> None:
    # Determinism Level 3 for a fixed patch: same verdict and identical output.
    task = _fixture_task()
    patch = _patch("a + b")
    with VerifierSandbox() as sandbox:
        first = sandbox.verify(task, patch)
        second = sandbox.verify(task, patch)
    assert first.state == second.state == VerdictState.PASSED
    assert first.output == second.output


# --- M2-C2: two-phase network-isolated test execution ------------------------


def test_isolation_disabled_runs_without_unshare() -> None:
    with VerifierSandbox(network_isolation=False) as sandbox:
        verdict = sandbox.verify(_fixture_task(), _patch("a + b"))
    assert verdict.state == VerdictState.PASSED


def test_phase2_blocks_network_egress() -> None:
    if not _verifier_sandbox._network_isolation_available():
        pytest.skip("network isolation requires CAP_SYS_ADMIN / unshare -n (unavailable here)")
    egress = (
        "import socket\n"
        "socket.setdefaulttimeout(4)\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 53))\n"
        "    raise SystemExit('EGRESS REACHED')\n"
        "except OSError:\n"
        "    pass\n"
    )
    task = _fixture_task().model_copy(update={"hidden_test_command": ("python", "-c", egress)})
    with VerifierSandbox(network_isolation=True) as sandbox:
        verdict = sandbox.verify(task, _patch("a + b"))
    # The egress attempt fails inside the isolated namespace -> the check exits 0.
    assert verdict.state == VerdictState.PASSED


def test_isolation_required_but_unavailable_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_verifier_sandbox, "_network_isolation_available", lambda: False)
    with VerifierSandbox(network_isolation=True) as sandbox, pytest.raises(SandboxExecutionError):
        sandbox.verify(_fixture_task(), _patch("a + b"))


# --- M2-C3: flake detection and provenance -----------------------------------


def test_flake_detection_flags_a_nondeterministic_test() -> None:
    # The flaky fixture alternates pass/fail across the reruns -> flaky=True.
    task = _fixture_task().model_copy(
        update={"hidden_test_command": ("python", "-m", "pytest", "-q", "test_flake.py")},
    )
    with VerifierSandbox(network_isolation=False) as sandbox:
        verdict = sandbox.verify(task, _patch("a + b"))
    assert verdict.flaky is True


def test_deterministic_primary_is_not_flaky() -> None:
    with VerifierSandbox(network_isolation=False) as sandbox:
        verdict = sandbox.verify(_fixture_task(), _patch("a + b"))
    assert verdict.state == VerdictState.PASSED
    assert verdict.flaky is False
