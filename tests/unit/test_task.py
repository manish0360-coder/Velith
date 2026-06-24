"""Unit tests for the M1 fixture Task descriptor and loader (C3).

These pin the C3 Definition of Done (handoff §5/§6): the fixture task loads, the
Task exposes the repo path, prompt material, and hidden-test invocation, and the
fixture files exist on disk. The hidden test's *failure on the unpatched repo* is
the verifier's concern and is confirmed directly by the C3 acceptance command —
the fixture is intentionally excluded from this suite (tests/fixtures/conftest.py).
"""

from __future__ import annotations

from pathlib import Path

from velith.task import FIXTURE_TASK_ID, HIDDEN_TEST_FILE, Task, load_fixture_task

# tests/unit/test_task.py -> parents[1] is tests/, so fixtures live alongside.
_FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"


def test_loader_returns_the_single_fixture_task() -> None:
    task = load_fixture_task(fixtures_root=_FIXTURES_ROOT)
    assert isinstance(task, Task)
    assert task.task_id == FIXTURE_TASK_ID


def test_task_exposes_repo_prompt_and_hidden_test_invocation() -> None:
    task = load_fixture_task(fixtures_root=_FIXTURES_ROOT)
    assert task.repo_path == _FIXTURES_ROOT / FIXTURE_TASK_ID
    assert "calculator.py" in task.prompt
    assert "pytest" in task.hidden_test_command
    assert task.hidden_test_command[-1] == HIDDEN_TEST_FILE


def test_fixture_repo_contains_buggy_source_and_hidden_test() -> None:
    task = load_fixture_task(fixtures_root=_FIXTURES_ROOT)
    assert (task.repo_path / "calculator.py").is_file()
    assert (task.repo_path / HIDDEN_TEST_FILE).is_file()
