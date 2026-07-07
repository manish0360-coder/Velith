"""Hard deterministic cost guard for a batch sweep (M5-C3).

Bounds a sweep by deterministic resource limits (M5_SPEC §3.4): the number of tasks
attempted, attempts per task, and a cumulative token budget. A limit of ``0`` means
unbounded. The guard halts the sweep **loudly** (raises :class:`CostBudgetError`) at a
limit, and admits work strictly below each limit. Standard library only.
"""

from __future__ import annotations


class CostBudgetError(Exception):
    """Raised when a cost-guard limit is reached — loud, never silent (M5_SPEC §3.4)."""


class CostGuard:
    """A stateful, deterministic bound on a batch sweep's resource use.

    Constructed with the sweep's limits (``0`` means unbounded). It tracks the tasks
    started and the tokens charged, and refuses (raises) work at or beyond any limit.
    """

    def __init__(self, max_tasks: int, max_attempts_per_task: int, max_tokens: int) -> None:
        self._max_tasks = max_tasks
        self._max_attempts_per_task = max_attempts_per_task
        self._max_tokens = max_tokens
        self._tasks_started = 0
        self._tokens_charged = 0

    def start_task(self) -> None:
        """Admit a new task, or raise if the task budget is exhausted."""
        if self._max_tasks and self._tasks_started >= self._max_tasks:
            raise CostBudgetError(f"task budget reached (max_tasks={self._max_tasks})")
        self._tasks_started += 1

    def check_attempt(self, attempts_already_made: int) -> None:
        """Admit another attempt for the current task, or raise at the attempt limit."""
        if self._max_attempts_per_task and attempts_already_made >= self._max_attempts_per_task:
            raise CostBudgetError(
                f"attempt limit reached (max_attempts_per_task={self._max_attempts_per_task})"
            )

    def charge_tokens(self, tokens: int) -> None:
        """Account ``tokens`` against the budget, or raise if it would be exceeded."""
        if self._max_tokens and self._tokens_charged + tokens > self._max_tokens:
            raise CostBudgetError(f"token budget reached (max_tokens={self._max_tokens})")
        self._tokens_charged += tokens
