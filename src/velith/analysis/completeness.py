"""Completeness assessment for the M9 analysis (M9-C3 / P2, §3.5.1 / OED-7).

Implements the frozen two-tier completeness rule, plus the OED-7 empty-dataset disposition
and data-integrity validation — deterministically and computing no statistic:

* **Global incompleteness (§3.5.1):** if the M8 evaluation run did not complete for the
  full pre-registered held-out set, the pre-registration is **VOID** (a hard stop; M10
  cannot run). Whether the run completed is a fact about the M8 run, supplied by the caller
  (``evaluation_run_complete``) from M8's own status — this module does not *infer* it and
  invents no detection heuristic.
* **Per-task complete-case (§3.5.1):** if a task is missing any required
  ``task x checkpoint x arm`` cell, that whole task is excluded (complete-case). The number
  of included tasks ``n`` is reported.
* **Empty dataset (OED-7, §3.5.11):** if ``n = 0`` after complete-case exclusion, the
  outcome is **VOID** — a procedural halt, never an inferential NO-GO.
* **Data-integrity errors:** duplicate cells, unknown task/arm/checkpoint, or an A0 cell at
  a non-A0 checkpoint raise :class:`CompletenessError` (loud, typed).

OED-2 (frozen): A0 is time-invariant — exactly **one** required A0 cell per task, at A0's
single empty-checkpoint identity, **not** replicated across the K checkpoints; A1 and A2
each require one cell per pre-registered checkpoint.

Boundary: this module operates on the pre-registered design and an :class:`ObservedCoverage`
of ``(task, arm, checkpoint_identity)`` keys — abstractions the caller builds. It reads no
evaluation sink or live held-out state, writes no memory, and reaches no statistical or
GO/NO-GO decision (VOID is not NO-GO).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from velith.arms.identity import Arm

_ARM_VALUES: frozenset[str] = frozenset(arm.value for arm in Arm)


class CompletenessError(Exception):
    """Raised on a structural or data-integrity failure in the coverage (loud, typed)."""


class CompletenessStatus(str, Enum):
    """The completeness classification (no inferential NO-GO is produced here)."""

    COMPLETE = "COMPLETE"
    VOID_GLOBAL_INCOMPLETE = "VOID_GLOBAL_INCOMPLETE"
    VOID_EMPTY = "VOID_EMPTY"


@dataclass(frozen=True)
class ObservedCell:
    """One observed coverage key: an arm evaluated a task at a checkpoint identity.

    For A0 the ``checkpoint_identity`` is A0's single empty-checkpoint identity (OED-2);
    for A1/A2 it is a pre-registered content-addressed checkpoint identity.
    """

    task_identity: str
    arm: str
    checkpoint_identity: str


@dataclass(frozen=True)
class CompletenessResult:
    """The deterministic completeness outcome: status, included/excluded tasks, and ``n``."""

    status: CompletenessStatus
    included_task_identities: tuple[str, ...]
    excluded_task_identities: tuple[str, ...]
    n: int


def _required_cells(
    task: str, checkpoint_identities: tuple[str, ...], a0_checkpoint_identity: str
) -> set[tuple[str, str, str]]:
    """The required coverage for one task (OED-2: A0 once; A1/A2 once per checkpoint)."""
    cells: set[tuple[str, str, str]] = {(task, Arm.A0.value, a0_checkpoint_identity)}
    for checkpoint in checkpoint_identities:
        cells.add((task, Arm.A1.value, checkpoint))
        cells.add((task, Arm.A2.value, checkpoint))
    return cells


def assess_completeness(
    *,
    task_identities: tuple[str, ...],
    checkpoint_identities: tuple[str, ...],
    a0_checkpoint_identity: str,
    evaluation_run_complete: bool,
    observed: Iterable[ObservedCell],
) -> CompletenessResult:
    """Classify the coverage under the frozen completeness rule (§3.5.1 / OED-7).

    ``task_identities`` is the full pre-registered held-out set; ``checkpoint_identities``
    the ordered pre-registered schedule; ``a0_checkpoint_identity`` A0's single empty
    checkpoint (OED-2); ``evaluation_run_complete`` the M8 run status (caller-supplied);
    ``observed`` the observed ``(task, arm, checkpoint_identity)`` coverage. Deterministic:
    all returned task lists are sorted.
    """
    if len(set(task_identities)) != len(task_identities):
        raise CompletenessError("duplicate task identity in the held-out set")
    if not checkpoint_identities:
        raise CompletenessError("empty pre-registered checkpoint schedule")
    if len(set(checkpoint_identities)) != len(checkpoint_identities):
        raise CompletenessError("duplicate checkpoint identity in the schedule")

    task_set = set(task_identities)
    checkpoint_set = set(checkpoint_identities)
    seen: set[tuple[str, str, str]] = set()
    observed_by_task: dict[str, set[tuple[str, str, str]]] = {}
    for cell in observed:
        key = (cell.task_identity, cell.arm, cell.checkpoint_identity)
        if key in seen:
            raise CompletenessError(f"duplicate observed cell: {key}")
        seen.add(key)
        if cell.task_identity not in task_set:
            raise CompletenessError(f"observed cell for an unknown task: {cell.task_identity!r}")
        if cell.arm not in _ARM_VALUES:
            raise CompletenessError(f"observed cell for an unknown arm: {cell.arm!r}")
        if cell.arm == Arm.A0.value:
            if cell.checkpoint_identity != a0_checkpoint_identity:
                raise CompletenessError(
                    "A0 observed at a non-A0 checkpoint (A0 is time-invariant, not replicated "
                    f"across checkpoints): {cell.checkpoint_identity!r}"
                )
        elif cell.checkpoint_identity not in checkpoint_set:
            raise CompletenessError(
                f"observed {cell.arm} cell at an unknown checkpoint: {cell.checkpoint_identity!r}"
            )
        observed_by_task.setdefault(cell.task_identity, set()).add(key)

    if not evaluation_run_complete:
        return CompletenessResult(CompletenessStatus.VOID_GLOBAL_INCOMPLETE, (), (), 0)

    included: list[str] = []
    excluded: list[str] = []
    for task in task_identities:
        required = _required_cells(task, checkpoint_identities, a0_checkpoint_identity)
        if required <= observed_by_task.get(task, set()):
            included.append(task)
        else:
            excluded.append(task)

    if not included:
        return CompletenessResult(CompletenessStatus.VOID_EMPTY, (), tuple(sorted(excluded)), 0)
    return CompletenessResult(
        CompletenessStatus.COMPLETE, tuple(sorted(included)), tuple(sorted(excluded)), len(included)
    )
