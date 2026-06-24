"""The M1 fixture task descriptor (M1 spec §5, handoff §4.3).

A :class:`Task` is a typed value object describing ONE engineering task: its id,
the working repository to operate on, the prompt material handed to the proposer,
and the exact hidden-test invocation the verifier runs to dispose of a candidate
patch.

M1 has exactly one task, backed by a minimal hand-built fixture (a buggy repo plus
a deterministic hidden test, D16.3). This fixture is NOT a benchmark and must never
be used as one (D16.3, D8) — real SWE-bench Verified tasks and the dataset loader
arrive at M4. There is deliberately no dataset loading and no multiple-task logic
here; this module has no internal Velith dependencies.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

#: The id of the single M1 fixture task (also the fixture directory name).
FIXTURE_TASK_ID: Final[str] = "calc_add_bug"

#: Where fixtures live, resolved against the current working directory — which is
#: the repo root (/app) inside the verifier container. Tests inject an explicit
#: root so resolution never depends on the caller's CWD.
DEFAULT_FIXTURES_ROOT: Final[Path] = Path("tests/fixtures")

#: The hidden-test file inside the fixture repo, run by the verifier.
HIDDEN_TEST_FILE: Final[str] = "test_calculator.py"

_FIXTURE_PROMPT: Final[str] = (
    "The function `add(a, b)` in `calculator.py` must return the sum of its two "
    "integer arguments, but it currently returns the wrong value. Fix the bug in "
    "`calculator.py` so that `add` returns `a + b`. Reply with a unified diff patch "
    "only."
)


class Task(BaseModel):
    """One engineering task: what to fix, where, and how it is judged.

    Frozen and ``extra="forbid"`` — a task descriptor is immutable and cannot grow
    undeclared fields. ``hidden_test_command`` is the exact argv the verifier runs
    inside the (copied) working repo; ``repo_path`` is the source the verifier
    copies — it never operates on this path in place.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    repo_path: Path
    prompt: str
    hidden_test_command: tuple[str, ...]


def load_fixture_task(fixtures_root: Path | None = None) -> Task:
    """Return the single M1 fixture task.

    ``fixtures_root`` defaults to ``tests/fixtures`` relative to the current working
    directory (the repo root inside the container). A config-driven fixtures
    location is out of M1 scope (the dataset loader is M4); injection keeps this
    loader self-contained with no internal dependency.
    """
    root = fixtures_root if fixtures_root is not None else DEFAULT_FIXTURES_ROOT
    return Task(
        task_id=FIXTURE_TASK_ID,
        repo_path=root / FIXTURE_TASK_ID,
        prompt=_FIXTURE_PROMPT,
        hidden_test_command=("python", "-m", "pytest", "-q", HIDDEN_TEST_FILE),
    )
