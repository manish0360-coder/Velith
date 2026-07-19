"""The arm-to-filter binding: one retention policy per run, fixed (M7-C3).

Binds each arm to **exactly one** write-filter (M7_SPEC §3.1). The mapping is:

* **total** over the closed M7 arm set — every admitted arm has exactly one filter;
* **injective** — every filter belongs to exactly one arm;
* **immutable for the lifetime of a run** — resolved once when the run's identity is
  fixed, and never changed, re-bound, overridden, or selected dynamically thereafter:
  not per task, per attempt, per query, or in response to any observed outcome.

The immutability is not ergonomics. A filter that could shift mid-run would make the
manipulated variable non-constant *within* an arm, so the recorded ``arm`` provenance
would no longer identify what the memory contains and the A1/A2 contrast (D6/D7)
would be uninterpretable. Resolution therefore depends on the arm and nothing else,
and a resolved binding cannot be mutated.

``A0`` is deliberately unbound: the frozen cold baseline is memoryless (M5), so it has
no retention policy to name. Asking for its filter is a declaration error, not a
default — an undeclared or ambiguous retention policy must fail loudly.

Scope: the binding only. The active-arm setting is M7-C4 and the memory view is
M7-C5. Standard library plus the M7 arm identity and write-filter policies.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from velith.arms.filters import UnfilteredWriteFilter, VerifiedWriteFilter, WriteFilter
from velith.arms.identity import M7_ARMS, Arm


class BindingError(Exception):
    """Raised when an arm has no declared retention policy (M7_SPEC §3.1)."""


#: The total, injective arm -> write-filter table, read-only so it cannot be
#: re-bound at runtime. The filters are stateless, so one shared instance per arm is
#: the whole policy.
ARM_FILTERS: Final[Mapping[Arm, WriteFilter]] = MappingProxyType(
    {
        Arm.A1: UnfilteredWriteFilter(),
        Arm.A2: VerifiedWriteFilter(),
    }
)


@dataclass(frozen=True)
class ArmBinding:
    """A run's resolved retention policy: one arm, one filter, fixed for its lifetime.

    Frozen: once the run's identity is fixed, neither the arm nor its filter can be
    reassigned. Any attempt fails loudly rather than silently shifting the manipulated
    variable mid-run.
    """

    arm: Arm
    write_filter: WriteFilter


def resolve_binding(arm: Arm) -> ArmBinding:
    """Resolve ``arm`` to its single write-filter, once, for the run's lifetime.

    Takes the arm and nothing else: there is no task, attempt, query, or outcome
    parameter through which a policy could be selected dynamically.

    Raises:
        BindingError: if ``arm`` has no declared retention policy — notably the frozen
            memoryless baseline ``A0``, which is not an M7 arm.
    """
    if arm not in ARM_FILTERS:
        raise BindingError(
            f"arm {arm.value!r} has no declared retention policy; "
            f"the closed M7 arm set is {[member.value for member in M7_ARMS]}"
        )
    return ArmBinding(arm=arm, write_filter=ARM_FILTERS[arm])
