"""Unit tests for the M9 completeness assessment (M9-C3 / P2, §3.5.1 / OED-7).

Deterministic, synthetic fixtures only — no real M8 held-out data. Pins the frozen
two-tier rule, the OED-7 empty-dataset VOID, OED-2 A0-not-replicated, data-integrity
errors, determinism, and the boundary (VOID is never a NO-GO; no statistical surfaces).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from velith.analysis import completeness as completeness_mod
from velith.analysis.completeness import (
    CompletenessError,
    CompletenessResult,
    CompletenessStatus,
    ObservedCell,
    assess_completeness,
)

_A0_CP = hashlib.sha256(b"empty-checkpoint").hexdigest()
_CPS = (hashlib.sha256(b"cp1").hexdigest(), hashlib.sha256(b"cp2").hexdigest())
_TASKS = (hashlib.sha256(b"task1").hexdigest(), hashlib.sha256(b"task2").hexdigest())


def _full_cells(task: str) -> list[ObservedCell]:
    """A fully-covered task: A0 once (OED-2) + A1/A2 for every checkpoint."""
    cells = [ObservedCell(task, "A0", _A0_CP)]
    for cp in _CPS:
        cells.append(ObservedCell(task, "A1", cp))
        cells.append(ObservedCell(task, "A2", cp))
    return cells


def _assess(observed: list[ObservedCell], *, run_complete: bool = True) -> CompletenessResult:
    return assess_completeness(
        task_identities=_TASKS,
        checkpoint_identities=_CPS,
        a0_checkpoint_identity=_A0_CP,
        evaluation_run_complete=run_complete,
        observed=observed,
    )


def test_fully_complete_dataset_is_complete() -> None:
    observed = _full_cells(_TASKS[0]) + _full_cells(_TASKS[1])
    result = _assess(observed)
    assert result.status is CompletenessStatus.COMPLETE
    assert result.n == 2
    assert result.included_task_identities == tuple(sorted(_TASKS))
    assert result.excluded_task_identities == ()


def test_one_incomplete_task_is_complete_case_excluded() -> None:
    # task2 is missing one A2 cell -> excluded; task1 fully covered -> included.
    observed = [
        *_full_cells(_TASKS[0]),
        ObservedCell(_TASKS[1], "A0", _A0_CP),
        ObservedCell(_TASKS[1], "A1", _CPS[0]),
        ObservedCell(_TASKS[1], "A1", _CPS[1]),
        ObservedCell(_TASKS[1], "A2", _CPS[0]),
    ]
    result = _assess(observed)
    assert result.status is CompletenessStatus.COMPLETE
    assert result.n == 1
    assert result.included_task_identities == (_TASKS[0],)
    assert result.excluded_task_identities == (_TASKS[1],)


def test_global_incomplete_is_void() -> None:
    result = _assess(_full_cells(_TASKS[0]) + _full_cells(_TASKS[1]), run_complete=False)
    assert result.status is CompletenessStatus.VOID_GLOBAL_INCOMPLETE
    assert result.n == 0


def test_zero_remaining_tasks_is_void_not_nogo() -> None:
    # Both tasks missing cells -> all excluded -> n=0 -> VOID (OED-7), never a NO-GO.
    observed = [ObservedCell(_TASKS[0], "A0", _A0_CP), ObservedCell(_TASKS[1], "A0", _A0_CP)]
    result = _assess(observed)
    assert result.status is CompletenessStatus.VOID_EMPTY
    assert result.n == 0
    assert "NO_GO" not in {s.value for s in CompletenessStatus}


def test_a0_not_replicated_across_checkpoints() -> None:
    # A0 at a real checkpoint identity (as if replicated across K) is a data-integrity error.
    observed = [*_full_cells(_TASKS[0]), ObservedCell(_TASKS[0], "A0", _CPS[0])]
    with pytest.raises(CompletenessError):
        _assess(observed)


def test_a0_required_only_once() -> None:
    # A single A0 cell + full A1/A2 across K satisfies the task (A0 not required K times).
    result = assess_completeness(
        task_identities=(_TASKS[0],),
        checkpoint_identities=_CPS,
        a0_checkpoint_identity=_A0_CP,
        evaluation_run_complete=True,
        observed=_full_cells(_TASKS[0]),
    )
    assert result.status is CompletenessStatus.COMPLETE
    assert result.n == 1


def test_duplicate_cell_is_rejected() -> None:
    observed = [*_full_cells(_TASKS[0]), ObservedCell(_TASKS[0], "A0", _A0_CP)]
    with pytest.raises(CompletenessError):
        _assess(observed)


def test_unknown_task_arm_checkpoint_are_rejected() -> None:
    for bad in (
        ObservedCell("z" * 64, "A1", _CPS[0]),
        ObservedCell(_TASKS[0], "A9", _CPS[0]),
        ObservedCell(_TASKS[0], "A1", "f" * 64),
    ):
        with pytest.raises(CompletenessError):
            _assess([bad])


def test_empty_checkpoint_schedule_is_rejected() -> None:
    with pytest.raises(CompletenessError):
        assess_completeness(
            task_identities=_TASKS,
            checkpoint_identities=(),
            a0_checkpoint_identity=_A0_CP,
            evaluation_run_complete=True,
            observed=[],
        )


def test_output_is_deterministic() -> None:
    observed = _full_cells(_TASKS[0]) + _full_cells(_TASKS[1])
    assert _assess(observed) == _assess(list(reversed(observed)))


def test_completeness_has_no_statistical_or_heldout_surfaces() -> None:
    source = Path(completeness_mod.__file__).read_text(encoding="utf-8")
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
        assert forbidden not in source, f"completeness must not reference: {forbidden}"
