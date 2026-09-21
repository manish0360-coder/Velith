"""Unit tests for the K=1 exact one-sided McNemar executor (M9-C5 / P2, §3.5.5).

Deterministic, synthetic fixtures only — no real M8 held-out data. Pins the exact
integer-binomial p-value (no continuity correction, no approximation), the one-sided
direction X > Y, the zero-discordance rule, validation, and the boundary (no Holm, no
GO/NO-GO, no completeness classification).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from velith.analysis import mcnemar as mcnemar_mod
from velith.analysis.binder import Observation
from velith.analysis.mcnemar import McNemarError, McNemarResult, mcnemar_test

_CP = hashlib.sha256(b"cp1").hexdigest()


def _task(n: int) -> str:
    return hashlib.sha256(f"task{n}".encode()).hexdigest()


def _obs(
    pairs: list[tuple[int, int]], *, superior: str = "A1", reference: str = "A0"
) -> list[Observation]:
    """Build K=1 observations from (superior_endpoint, reference_endpoint) pairs, one per task."""
    observations: list[Observation] = []
    for i, (sup, ref) in enumerate(pairs):
        task = _task(i)
        observations.append(Observation(task, superior, _CP, 1, sup))
        observations.append(Observation(task, reference, _CP, 1, ref))
    return observations


def _run(
    pairs: list[tuple[int, int]], *, superior: str = "A1", reference: str = "A0"
) -> McNemarResult:
    return mcnemar_test(
        _obs(pairs, superior=superior, reference=reference),
        superior_arm=superior,
        reference_arm=reference,
    )


def test_known_case_exact_p_value() -> None:
    # x=3, y=0, discordant=3 -> p = C(3,3)/2^3 = 1/8 = 0.125
    result = _run([(1, 0), (1, 0), (1, 0)])
    assert (result.x, result.y, result.discordant) == (3, 0, 3)
    assert result.p_value == 0.125


def test_opposite_direction_case() -> None:
    # x=0, y=3 -> p = P(B>=0) = 1.0 (no evidence for superior > reference)
    result = _run([(0, 1), (0, 1), (0, 1)])
    assert (result.x, result.y) == (0, 3)
    assert result.p_value == 1.0


def test_zero_discordance_is_one() -> None:
    result = _run([(1, 1), (0, 0), (1, 1)])
    assert result.discordant == 0
    assert result.p_value == 1.0


def test_x_zero() -> None:
    result = _run([(0, 1), (0, 1)])
    assert result.x == 0 and result.discordant == 2
    assert result.p_value == 1.0


def test_y_zero() -> None:
    # x=2, y=0, discordant=2 -> p = C(2,2)/4 = 0.25
    result = _run([(1, 0), (1, 0)])
    assert (result.x, result.y) == (2, 0)
    assert result.p_value == 0.25


def test_all_concordant() -> None:
    result = _run([(1, 1), (0, 0)])
    assert result.discordant == 0 and result.p_value == 1.0


def test_mixed_concordant_and_discordant() -> None:
    # pairs: (1,0),(1,0),(0,1),(1,1),(0,0) -> x=2, y=1, discordant=3
    # p = (C(3,2)+C(3,3))/8 = (3+1)/8 = 0.5
    result = _run([(1, 0), (1, 0), (0, 1), (1, 1), (0, 0)])
    assert (result.x, result.y, result.discordant) == (2, 1, 3)
    assert result.p_value == 0.5


def test_no_continuity_correction() -> None:
    # x=2,y=0,n=2 -> exact 0.25; a continuity-corrected/normal approx would differ.
    assert _run([(1, 0), (1, 0)]).p_value == 0.25


def test_direction_is_x_gt_y() -> None:
    # Same underlying (A1, A0) data viewed with the superior/reference roles swapped.
    forward = _run([(1, 0), (1, 0), (0, 1)], superior="A1", reference="A0")
    reverse = _run([(0, 1), (0, 1), (1, 0)], superior="A0", reference="A1")
    assert (forward.x, forward.y) == (2, 1)
    assert (reverse.x, reverse.y) == (1, 2)
    # Swapping superior/reference swaps x <-> y and preserves the discordant count.
    assert forward.x == reverse.y
    assert forward.y == reverse.x
    assert forward.discordant == reverse.discordant == 3
    # The test is ONE-SIDED (p = P(B >= x)), so p is NOT symmetric under the x<->y swap.
    assert forward.p_value == 0.5  # P(B >= 2 | n=3)
    assert reverse.p_value == 0.875  # P(B >= 1 | n=3)
    assert forward.p_value != reverse.p_value


def test_duplicate_task_rejected() -> None:
    obs = [*_obs([(1, 0)]), Observation(_task(0), "A1", _CP, 1, 1)]
    with pytest.raises(McNemarError):
        mcnemar_test(obs, superior_arm="A1", reference_arm="A0")


def test_invalid_endpoint_rejected() -> None:
    obs = [Observation(_task(0), "A1", _CP, 1, 2), Observation(_task(0), "A0", _CP, None, 0)]
    with pytest.raises(McNemarError):
        mcnemar_test(obs, superior_arm="A1", reference_arm="A0")


def test_k_greater_than_one_observation_rejected() -> None:
    obs = [Observation(_task(0), "A1", _CP, 2, 1), Observation(_task(0), "A0", _CP, None, 0)]
    with pytest.raises(McNemarError):
        mcnemar_test(obs, superior_arm="A1", reference_arm="A0")


def test_incomplete_pairs_rejected_not_classified() -> None:
    # superior has a task the reference lacks -> C5 raises (completeness is C3's, not C5's).
    obs = [Observation(_task(0), "A1", _CP, 1, 1), Observation(_task(1), "A0", _CP, None, 0)]
    with pytest.raises(McNemarError):
        mcnemar_test(obs, superior_arm="A1", reference_arm="A0")


def test_same_arm_rejected() -> None:
    with pytest.raises(McNemarError):
        mcnemar_test([], superior_arm="A1", reference_arm="A1")


def test_deterministic_repeated_execution() -> None:
    pairs = [(1, 0), (0, 1), (1, 1), (1, 0)]
    assert _run(pairs) == _run(pairs)


def test_result_is_deterministic_regardless_of_input_order() -> None:
    obs = _obs([(1, 0), (0, 1), (1, 0)])
    first = mcnemar_test(obs, superior_arm="A1", reference_arm="A0")
    second = mcnemar_test(list(reversed(obs)), superior_arm="A1", reference_arm="A0")
    assert first == second


def test_a2_vs_a1_comparison_supported() -> None:
    result = _run([(1, 0), (1, 0)], superior="A2", reference="A1")
    assert result.superior_arm == "A2" and result.reference_arm == "A1"
    assert result.p_value == 0.25


def test_mcnemar_imports_no_holm_decision_stats_or_memory() -> None:
    # Scan only import statements (docstring prose legitimately names what C5 excludes).
    source = Path(mcnemar_mod.__file__).read_text(encoding="utf-8")
    imports = "\n".join(
        line for line in source.splitlines() if line.startswith(("import ", "from "))
    )
    for forbidden in (
        "holm",
        "decision",
        "gee",
        "emm",
        "trend",
        "completeness",
        "statsmodels",
        "numpy",
        "scipy",
        "evaluation.sink",
        "evaluation.runner",
        "GuardedEpisodeWriter",
        "retrieval",
    ):
        assert forbidden not in imports, f"mcnemar must not import: {forbidden}"
