"""GA1 and GA2 on ``G0-BENCH-01`` Tier 1 (spec F r3 §9; benchmark manifest D §2).

GA1: BP-01..04 VERIFIED, and their facts equal the kernel-free ground truth (``ground_truth.json``,
closed form from ``parts.json``). The comparison is made at two levels:

- the worker's raw kernel values: volume within 1e-9 relative; bounding box, hole diameters and
  depths within 1e-6 mm; solid, planar-face and hole counts and genus exact;
- the facts document: every quantized string equals rule q-1 applied to the truth value.

(Volume is quantized to 1e-3 mm^3, so the 1e-9 relative criterion can only apply to raw values; the
quantized facts must then equal the quantized truth exactly.)

GA2: CR-01..03 give REQUIREMENT_NOT_MET with the expected failing conformance entries; NC-01..05
give the reasons of D §2; zero VERIFIED negatives.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.geometry._cases import CASES, DATA, payload
from velith.api.geometry_contract import (
    GeometryEngineeringResult,
    GeometryTask,
    GeometryUnverifiedOutcome,
    StepArtifact,
)
from velith.geometry import rules
from velith.geometry.verifier import GeometryVerifier

TRUTH: dict[str, Any] = json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8"))[
    "parts"
]
AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}
GA1_PARTS = ["BP-01", "BP-02", "BP-03", "BP-04", "CR-02-GEOM"]


def _task(case: str) -> tuple[GeometryTask, StepArtifact]:
    default: tuple[str, dict[str, Any], str, tuple[str, ...]] = (
        case,
        {"requirements_schema_version": "0.2.0"},
        "",
        (),
    )
    stem, declared, _expected, _failing = CASES.get(case, default)
    return (
        GeometryTask(task_id=case, requirements=declared),
        StepArtifact(payload=payload(stem)),
    )


@pytest.mark.parametrize("stem", GA1_PARTS)
def test_ga1_raw_kernel_values_equal_ground_truth(stem: str, verifier: GeometryVerifier) -> None:
    task, artifact = _task(stem)
    raw = verifier.measure(task, artifact)
    truth = TRUTH[stem]
    assert raw.status == "MEASURED"
    assert len(raw.solids) == truth["solids"] == 1
    solid = raw.solids[0]
    assert abs(solid.volume_mm3 - truth["volume_mm3"]) <= 1e-9 * truth["volume_mm3"]
    size = [hi - lo for lo, hi in zip(solid.bbox_min, solid.bbox_max, strict=True)]
    assert all(abs(a - b) <= 1e-6 for a, b in zip(size, truth["bbox_mm"], strict=True))
    assert solid.genus == truth["genus"]
    assert solid.faces.plane == truth["planar_faces"]
    assert solid.closed is truth["closed"] is True
    measured = sorted(
        (
            tuple(abs(c) for c in hole.axis_dir),
            hole.segments[0].diameter_mm,
            hole.segments[0].depth_mm,
            hole.through,
        )
        for hole in solid.holes
    )
    expected = sorted(
        (AXES[h["axis"]], float(h["diameter_mm"]), float(h["depth_mm"]), h["through"])
        for h in truth["holes"]
    )
    assert len(measured) == len(expected) == truth["hole_count"]
    for (axis, diameter, depth, through), (t_axis, t_diameter, t_depth, t_through) in zip(
        measured, expected, strict=True
    ):
        assert axis == t_axis and through is t_through
        assert abs(diameter - t_diameter) <= 1e-6 and abs(depth - t_depth) <= 1e-6
    assert all(len(hole.segments) == 1 for hole in solid.holes)


@pytest.mark.parametrize("case", ["BP-01", "BP-02", "BP-03", "BP-04"])
def test_ga1_verified_and_facts_equal_quantized_truth(
    case: str, verifier: GeometryVerifier
) -> None:
    task, artifact = _task(case)
    outcome = verifier.evaluate(task, artifact)
    assert isinstance(outcome, GeometryEngineeringResult)
    truth = TRUTH[CASES[case][0]]
    solid = outcome.facts["solids"][0]
    assert solid["volume_mm3"] == rules.quantize(truth["volume_mm3"], "volume_mm3")
    assert solid["bbox_mm"]["size"] == [rules.quantize(x, "length_mm") for x in truth["bbox_mm"]]
    assert solid["genus"] == str(truth["genus"])
    assert solid["faces"]["plane"] == str(truth["planar_faces"])
    facts_holes = sorted(
        (h["segments"][0]["diameter_mm"], h["segments"][0]["depth_mm"], h["kind"])
        for h in solid["holes"]
    )
    truth_holes = sorted(
        (
            rules.quantize(h["diameter_mm"], "length_mm"),
            rules.quantize(h["depth_mm"], "length_mm"),
            "through" if h["through"] else "blind",
        )
        for h in truth["holes"]
    )
    assert facts_holes == truth_holes
    assert all(entry["result"] == "MET" for entry in outcome.facts["conformance"])


def test_ga1_pocket_fillets_are_not_holes(verifier: GeometryVerifier) -> None:
    """BP-03: 4 concave quarter-cylinder pocket corners must not be reported as holes."""
    task, artifact = _task("BP-03")
    outcome = verifier.evaluate(task, artifact)
    assert isinstance(outcome, GeometryEngineeringResult)
    solid = outcome.facts["solids"][0]
    assert len(solid["holes"]) == 2
    assert solid["non_hole_cylindrical_faces"] == "4"


@pytest.mark.parametrize("case", [c for c in CASES if c.startswith(("CR", "NC"))])
def test_ga2_negatives(case: str, verifier: GeometryVerifier) -> None:
    _stem, _declared, expected, failing = CASES[case]
    task, artifact = _task(case)
    outcome = verifier.evaluate(task, artifact)
    assert isinstance(outcome, GeometryUnverifiedOutcome), "a negative case must never be VERIFIED"
    assert outcome.reason.value == expected
    if failing:
        assert outcome.facts is not None
        not_met = tuple(e["id"] for e in outcome.facts["conformance"] if e["result"] != "MET")
        assert not_met == failing
