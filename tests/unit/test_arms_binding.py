"""Unit tests for the M7 arm-to-filter binding (M7-C3).

Scope: the binding in isolation (M7_SPEC §3.1) — totality and injectivity over the
closed arm set, that naming the arm determines the filter, that the frozen memoryless
A0 has no retention policy, and that neither the resolved binding nor the table can
shift after resolution. The active-arm setting (C4) and the memory view (C5) are not
under test here and must not exist yet.
"""

from __future__ import annotations

import dataclasses
import inspect
from typing import cast

import pytest

from velith.arms.binding import ARM_FILTERS, ArmBinding, BindingError, resolve_binding
from velith.arms.filters import UnfilteredWriteFilter, VerifiedWriteFilter, WriteFilter
from velith.arms.identity import M7_ARMS, Arm


def test_binding_is_total_over_the_closed_arm_set() -> None:
    """Every M7 arm resolves to exactly one filter (§3.1)."""
    assert set(ARM_FILTERS) == set(M7_ARMS)
    for arm in M7_ARMS:
        assert resolve_binding(arm).write_filter is ARM_FILTERS[arm]


def test_binding_is_injective() -> None:
    """Every filter belongs to exactly one arm - no two arms share a policy."""
    filters = [ARM_FILTERS[arm] for arm in M7_ARMS]
    assert len({id(policy) for policy in filters}) == len(M7_ARMS)
    assert len({type(policy) for policy in filters}) == len(M7_ARMS)


def test_naming_the_arm_determines_the_filter() -> None:
    """The arm alone names the retention policy (§3.1)."""
    assert isinstance(resolve_binding(Arm.A1).write_filter, UnfilteredWriteFilter)
    assert isinstance(resolve_binding(Arm.A2).write_filter, VerifiedWriteFilter)


def test_resolution_is_stable_across_calls() -> None:
    """Resolving the same arm twice yields the same arm and the same filter."""
    for arm in M7_ARMS:
        first, second = resolve_binding(arm), resolve_binding(arm)
        assert first == second
        assert first.arm is second.arm
        assert first.write_filter is second.write_filter


def test_a0_has_no_retention_policy_and_fails_loudly() -> None:
    """The frozen memoryless baseline is not an M7 arm; asking is a declaration error."""
    assert Arm.A0 not in ARM_FILTERS
    with pytest.raises(BindingError, match="A0"):
        resolve_binding(Arm.A0)


def test_resolution_takes_the_arm_and_nothing_else() -> None:
    """No task/attempt/query/outcome parameter exists to select a policy dynamically."""
    assert list(inspect.signature(resolve_binding).parameters) == ["arm"]


def test_resolved_binding_is_immutable() -> None:
    """A resolved binding cannot shift mid-run - reassignment fails loudly (§3.1)."""
    binding = resolve_binding(Arm.A1)
    for field, value in (("arm", Arm.A2), ("write_filter", VerifiedWriteFilter())):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(binding, field, value)
    assert binding == ArmBinding(arm=Arm.A1, write_filter=ARM_FILTERS[Arm.A1])


def test_the_binding_table_cannot_be_rebound() -> None:
    """The arm -> filter table is read-only, so no arm can be re-bound at runtime."""
    mutable = cast(dict[Arm, WriteFilter], ARM_FILTERS)
    with pytest.raises(TypeError):
        mutable[Arm.A1] = VerifiedWriteFilter()
    with pytest.raises(TypeError):
        del mutable[Arm.A2]
    with pytest.raises(TypeError):
        mutable[Arm.A0] = UnfilteredWriteFilter()
    assert isinstance(ARM_FILTERS[Arm.A1], UnfilteredWriteFilter)
    assert Arm.A0 not in ARM_FILTERS
