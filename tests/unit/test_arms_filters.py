"""Unit tests for the M7 write-filter policies (M7-C2).

Scope: the two admission predicates in isolation (M7_SPEC §3.2). Pins the exact A2
boundary over the **closed** verdict taxonomy (D16.7) crossed with both secondary
states and the flake flag, the unconditional A1 admission, purity/determinism, and
domain-neutrality. The arm-to-filter binding (C3) and the memory view (C5) are not
under test here and must not exist yet.
"""

from __future__ import annotations

import itertools

import pytest

from velith.arms.filters import (
    UnfilteredWriteFilter,
    VerifiedWriteFilter,
    is_verified_failure,
    is_verified_success,
)
from velith.episodes.episode import Episode, VerdictState

#: The closed verdict taxonomy (D16.7) and the three secondary states.
ALL_STATES: tuple[VerdictState, ...] = tuple(VerdictState)
ALL_SECONDARY: tuple[bool | None, ...] = (True, False, None)
ALL_FLAKY: tuple[bool, ...] = (False, True)


def _episode(
    state: VerdictState,
    secondary: bool | None = True,
    flaky: bool = False,
    *,
    prompt: str = "fix the bug",
    patch: str = "diff --git a b",
) -> Episode:
    """Build an episode differing only in the fields a filter may consult."""
    return Episode.build(
        task_id="t",
        seed=0,
        model="m",
        model_version="v",
        prompt=prompt,
        patch=patch,
        verdict_state=state,
        verdict_output="out",
        prompt_tokens=1,
        completion_tokens=2,
        latency_seconds=1.0,
        verify_seconds=2.0,
        velith_version="0.0.0",
        secondary_passed=secondary,
        flaky=flaky,
        timestamp="2026-07-06T00:00:00+00:00",
    )


def _expected_verified(state: VerdictState, secondary: bool | None, flaky: bool) -> bool:
    """The frozen A2 boundary, restated independently of the implementation."""
    if flaky:
        return False
    if state is VerdictState.PASSED:
        return secondary is not False
    return state is VerdictState.FAILED


def test_unfiltered_admits_every_combination() -> None:
    """A1 retains everything: every verdict, both secondary states, flaky or not."""
    unfiltered = UnfilteredWriteFilter()
    for state, secondary, flaky in itertools.product(ALL_STATES, ALL_SECONDARY, ALL_FLAKY):
        assert unfiltered.admits(_episode(state, secondary, flaky)) is True


def test_verified_admission_is_exact_over_the_closed_taxonomy() -> None:
    """A2 admits exactly the two defined categories across the whole product space."""
    verified = VerifiedWriteFilter()
    for state, secondary, flaky in itertools.product(ALL_STATES, ALL_SECONDARY, ALL_FLAKY):
        assert verified.admits(_episode(state, secondary, flaky)) is _expected_verified(
            state, secondary, flaky
        )


@pytest.mark.parametrize("secondary", [True, None])
def test_verified_admits_uncontradicted_pass(secondary: bool | None) -> None:
    """A verified success is PASSED with the secondary True or absent."""
    episode = _episode(VerdictState.PASSED, secondary)
    assert is_verified_success(episode) is True
    assert VerifiedWriteFilter().admits(episode) is True


def test_verified_excludes_model_gap_pass() -> None:
    """PASSED refuted by the held-out secondary is the model gap (D21) - excluded."""
    episode = _episode(VerdictState.PASSED, False)
    assert is_verified_success(episode) is False
    assert VerifiedWriteFilter().admits(episode) is False


@pytest.mark.parametrize("secondary", [True, False, None])
def test_verified_admits_failure_regardless_of_secondary(secondary: bool | None) -> None:
    """FAILED is a real measurement; no success claim exists to contradict (D16.7)."""
    episode = _episode(VerdictState.FAILED, secondary)
    assert is_verified_failure(episode) is True
    assert VerifiedWriteFilter().admits(episode) is True


@pytest.mark.parametrize(
    "state",
    [VerdictState.PATCH_APPLY_FAILED, VerdictState.NO_PATCH, VerdictState.INFRA_ERROR],
)
def test_verified_excludes_unverified_outcomes(state: VerdictState) -> None:
    """No verification occurred, so there is no grounded signal to retain."""
    verified = VerifiedWriteFilter()
    for secondary in ALL_SECONDARY:
        episode = _episode(state, secondary)
        assert is_verified_success(episode) is False
        assert is_verified_failure(episode) is False
        assert verified.admits(episode) is False


@pytest.mark.parametrize("state", [VerdictState.PASSED, VerdictState.FAILED])
def test_verified_excludes_flaky_even_when_otherwise_qualifying(state: VerdictState) -> None:
    """An untrustworthy measurement is not verified signal (D17)."""
    verified = VerifiedWriteFilter()
    assert verified.admits(_episode(state, True, flaky=False)) is True
    assert verified.admits(_episode(state, True, flaky=True)) is False


def test_filters_are_pure_and_deterministic() -> None:
    """Repeated evaluation of the same episode yields the same decision."""
    unfiltered, verified = UnfilteredWriteFilter(), VerifiedWriteFilter()
    for state, secondary, flaky in itertools.product(ALL_STATES, ALL_SECONDARY, ALL_FLAKY):
        episode = _episode(state, secondary, flaky)
        assert {unfiltered.admits(episode) for _ in range(3)} == {unfiltered.admits(episode)}
        assert {verified.admits(episode) for _ in range(3)} == {verified.admits(episode)}


def test_admission_depends_solely_on_the_neutral_triple() -> None:
    """Opaque content is never inspected - a non-software episode filters identically."""
    unfiltered, verified = UnfilteredWriteFilter(), VerifiedWriteFilter()
    for state, secondary, flaky in itertools.product(ALL_STATES, ALL_SECONDARY, ALL_FLAKY):
        software = _episode(state, secondary, flaky)
        non_software = _episode(
            state,
            secondary,
            flaky,
            prompt="melody:C-E-G;bpm=120",
            patch="dish:soup;salt=2g",
        )
        assert unfiltered.admits(software) == unfiltered.admits(non_software)
        assert verified.admits(software) == verified.admits(non_software)
