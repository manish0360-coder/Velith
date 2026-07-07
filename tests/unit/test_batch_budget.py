"""Unit tests for the batch cost guard (M5-C3).

Scope: the guard admits work strictly below each limit and trips loudly at it, across
the task budget, the per-task attempt limit, and the cumulative token budget; a limit
of 0 is unbounded (M5_SPEC §3.4).
"""

from __future__ import annotations

import pytest

from velith.batch.budget import CostBudgetError, CostGuard


def test_task_budget_admits_below_and_trips_at_limit() -> None:
    guard = CostGuard(max_tasks=2, max_attempts_per_task=0, max_tokens=0)
    guard.start_task()
    guard.start_task()
    with pytest.raises(CostBudgetError):
        guard.start_task()


def test_attempt_limit_admits_below_and_trips_at_limit() -> None:
    guard = CostGuard(max_tasks=0, max_attempts_per_task=2, max_tokens=0)
    guard.check_attempt(0)
    guard.check_attempt(1)
    with pytest.raises(CostBudgetError):
        guard.check_attempt(2)


def test_token_budget_admits_up_to_and_trips_when_exceeded() -> None:
    guard = CostGuard(max_tasks=0, max_attempts_per_task=0, max_tokens=100)
    guard.charge_tokens(60)
    guard.charge_tokens(40)  # cumulative 100 == budget, still admitted
    with pytest.raises(CostBudgetError):
        guard.charge_tokens(1)  # 101 > 100 trips


def test_zero_limits_mean_unbounded() -> None:
    guard = CostGuard(max_tasks=0, max_attempts_per_task=0, max_tokens=0)
    for _ in range(1000):
        guard.start_task()
    guard.check_attempt(10_000)
    guard.charge_tokens(10_000_000)  # no raise under unbounded limits
