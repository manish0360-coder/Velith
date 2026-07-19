"""Unit tests for M7 arm identity (M7-C1).

Scope: identity in isolation — the closed M7 arm set, the presence and immutability
of the frozen A0, the absence of A3/A4, and the fact that an arm's recorded value is
the frozen ``arm`` provenance value (M7_SPEC §3.1). Filter logic (C2), the
arm-to-filter binding (C3), and memory access (C5) are *not* under test here and must
not exist yet.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import velith.arms
from velith.arms.identity import M7_ARMS, Arm
from velith.batch.runner import COLD_ARM
from velith.episodes.episode import Episode, VerdictState


def test_m7_arm_set_is_closed_to_a1_and_a2() -> None:
    """The M7 arm set is exactly A1 and A2, in that order (§3.1)."""
    assert M7_ARMS == (Arm.A1, Arm.A2)


def test_a0_is_present_unmodified_and_not_an_m7_arm() -> None:
    """A0 is present and carries the frozen value, but is not an arm M7 introduces."""
    assert Arm.A0.value == COLD_ARM  # the frozen M5 cold-baseline identifier
    assert Arm.A0 not in M7_ARMS


def test_a3_and_a4_are_absent() -> None:
    """The out-of-scope D7 arms A3/A4 do not exist in M7 (§8)."""
    assert {arm.value for arm in Arm} == {"A0", "A1", "A2"}
    for absent in ("A3", "A4"):
        with pytest.raises(ValueError, match=absent):
            Arm(absent)


def test_recorded_value_is_the_frozen_provenance_value() -> None:
    """An arm is written verbatim into the frozen episode ``arm`` field."""
    episode = Episode.build(
        task_id="t",
        seed=0,
        model="m",
        model_version="v",
        prompt="p",
        patch="d",
        verdict_state=VerdictState.PASSED,
        verdict_output="1 passed",
        prompt_tokens=1,
        completion_tokens=2,
        latency_seconds=1.0,
        verify_seconds=2.0,
        velith_version="0.0.0",
        secondary_passed=True,
        flaky=False,
        timestamp="2026-07-06T00:00:00+00:00",
        arm=Arm.A1.value,
    )
    assert episode.arm == "A1"
    assert Arm(episode.arm) is Arm.A1


def test_identity_module_holds_no_filter_binding_or_memory_logic() -> None:
    """C1 is identity only: the module imports nothing from ``velith`` (handoff §6)."""
    assert velith.arms.__file__ is not None
    source = (Path(velith.arms.__file__).parent / "identity.py").read_text(encoding="utf-8")
    imports = [
        line
        for line in source.splitlines()
        if line.startswith(("import ", "from ")) and "velith" in line
    ]
    assert imports == []
