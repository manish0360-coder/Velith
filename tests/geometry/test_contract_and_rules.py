"""Identity v2, the consumer check (spec F r3 §4), requirement parsing (§3), G-RULE precedence (§5)
and D35 (component versions): unit tests on synthetic inputs, no kernel needed except where noted.
"""

from __future__ import annotations

import copy
import json
from decimal import Decimal
from typing import Any

import pytest

import velith
from tests.geometry._cases import CASES, payload
from velith.api.contract import (
    IDENTITY_VERSION,
    ContractError,
    VerifierIdentity,
    content_hash_of,
    from_wire,
    identity_view,
)
from velith.api.geometry_contract import (
    GeometryEngineeringResult,
    GeometryReason,
    GeometryTask,
    RequirementError,
    StepArtifact,
    canonical_requirements,
    facts_hash,
    from_bundle,
)
from velith.api.swe import SWE_VERIFIER_VERSION
from velith.geometry import rules
from velith.geometry.verifier import GeometryVerifier

# --- D35 ---------------------------------------------------------------------------------------

T4B_HASH = "sha256:6c2babe95dfa51f142494ef7633322d68eed8983a775faa048f1060cee0317a0"
T5B_RESULT_ID = "2ac44842-2b16-5dbe-ae75-028dd4d44a26"


def test_d35_swe_identity_is_unchanged_by_the_release() -> None:
    """D35 r2: with Velith at 0.2.0, the SWE component stays 0.1.0 and T4-B/T5b reproduce."""
    from velith.api.contract import DesignArtifactRef, derive_id
    from velith.api.swe import SweVerifier

    assert velith.__version__ == "0.2.0" != SWE_VERIFIER_VERSION == "0.1.0"
    with SweVerifier(network_isolation=False, flake_rerun_count=3) as swe:
        identity = swe.identity
    artifact = DesignArtifactRef(
        media_type="application/vnd.velith.swe-patch+json",
        ref="cdf5e4da-da47-5e52-b845-448ab5cc6bb1",
        content_hash="sha256:ff39e80e72505b345d649cb5254e242490db0bf3ca67bcaed50d3274e11cae95",
    )
    view = identity_view(identity, artifact)
    assert view["identity_version"] == IDENTITY_VERSION
    assert content_hash_of(view) == T4B_HASH
    assert derive_id(T4B_HASH) == T5B_RESULT_ID


# --- requirements (§3) -----------------------------------------------------------------------


def test_requirements_defaults_and_exact_text() -> None:
    canonical = canonical_requirements(
        {
            "requirements_schema_version": "0.2.0",
            "holes": [
                {
                    "diameter_mm": "0.1984375",
                    "diameter_tol_mm": "0.000001",
                    "count": "1",
                    "kind": "blind",
                }
            ],
        }
    )
    assert canonical["plausible_size_mm"] == ["0.100000", "2000.000000"]
    assert canonical["holes"][0]["diameter_mm"] == "0.1984375"  # 1/128 in, never rounded
    assert canonical["length_tol_mm"] == "0.000001"
    assert "envelope_max_mm" not in canonical


@pytest.mark.parametrize(
    "bad",
    [
        {"requirements_schema_version": "0.1.0"},
        {"requirements_schema_version": "0.2.0", "extra": "1"},
        {"requirements_schema_version": "0.2.0", "envelope_max_mm": ["10", "10"]},
        {"requirements_schema_version": "0.2.0", "envelope_max_mm": ["10", "10", "6.6\n"]},
        {"requirements_schema_version": "0.2.0", "plausible_size_mm": ["100", "10"]},
        {"requirements_schema_version": "0.2.0", "expected_solids": "0"},
        {"requirements_schema_version": "0.2.0", "length_tol_mm": "0.0000005"},
        {
            "requirements_schema_version": "0.2.0",
            "holes": [
                {"diameter_mm": "6.0", "diameter_tol_mm": "0.5", "count": "1", "kind": "through"},
                {"diameter_mm": "6.4", "diameter_tol_mm": "0.1", "count": "1", "kind": "through"},
            ],
        },
    ],
)
def test_requirements_rejections(bad: dict[str, Any]) -> None:
    with pytest.raises(RequirementError):
        canonical_requirements(bad)


def test_hole_order_does_not_change_the_canonical_form() -> None:
    holes = CASES["BP-04"][1]["holes"]
    a = canonical_requirements({**CASES["BP-04"][1], "holes": holes})
    b = canonical_requirements({**CASES["BP-04"][1], "holes": list(reversed(holes))})
    assert a == b


# --- rules (§2, §5) -----------------------------------------------------------------------------


def _solid(**overrides: Any) -> dict[str, Any]:
    solid = {
        "valid": True,
        "closed": True,
        "volume_mm3": 1000.0,
        "area_mm2": 600.0,
        "genus": 0,
        "bbox_min": [0.0, 0.0, 0.0],
        "bbox_max": [10.0, 10.0, 10.0],
        "faces": {"plane": 6, "cylinder": 0, "cone": 0, "other": 0},
        "holes": [],
        "non_hole_cylindrical_faces": 0,
    }
    solid.update(overrides)
    return solid


def _raw(**overrides: Any) -> rules.RawMeasurement:
    document = {
        "protocol": "g0-child-1",
        "status": "MEASURED",
        "length_units": ["millimetre"],
        "shape": {"solids": 1, "shells": 1, "faces": 6},
        "solids": [_solid()],
        "cross_check": {"performed": True, "max_rel_diff": 1e-6},
    }
    document.update(overrides)
    return rules.RawMeasurement.model_validate_json(json.dumps(document))


REQ = canonical_requirements({"requirements_schema_version": "0.2.0", "holes_exhaustive": "false"})


def _reason(raw: rules.RawMeasurement) -> GeometryReason | None:
    return rules.evaluate(
        raw, REQ, artifact_content_hash="sha256:" + "0" * 64, annotations={}
    ).reason


def test_rule_precedence_on_synthetic_measurements() -> None:
    assert _reason(_raw()) is None
    assert _reason(_raw(length_units=["furlong"])) is GeometryReason.UNIT_UNRECOGNIZED
    assert _reason(_raw(length_units=[])) is GeometryReason.UNIT_UNRECOGNIZED
    assert _reason(_raw(solids=[])) is GeometryReason.NOT_A_CLOSED_SOLID
    assert _reason(_raw(solids=[_solid(), _solid()])) is GeometryReason.SOLID_COUNT_MISMATCH
    assert _reason(_raw(solids=[_solid(valid=False)])) is GeometryReason.INVALID_TOPOLOGY
    assert _reason(_raw(solids=[_solid(closed=False)])) is GeometryReason.INVALID_TOPOLOGY
    big = _solid(bbox_max=[3000.0, 10.0, 10.0])
    assert _reason(_raw(solids=[big])) is GeometryReason.UNIT_IMPLAUSIBLE
    disagreement = {"performed": True, "max_rel_diff": 2e-4}
    assert _reason(_raw(cross_check=disagreement)) is GeometryReason.MASS_PROPERTY_DISAGREEMENT
    # unit plausibility precedes the cross-check, which is then not even required
    assert not rules.cross_check_required(_raw(solids=[big]), REQ)


def test_missing_cross_check_after_rules_1_to_7_is_a_protocol_error() -> None:
    with pytest.raises(rules.WorkerProtocolError):
        _reason(_raw(cross_check={"performed": False, "max_rel_diff": None}))


def test_exact_boundary_comparison() -> None:
    assert rules.within("6.600001", "6.600000", "0.000001")  # float would say False
    assert not rules.within("6.600002", "6.600000", "0.000001")
    assert rules.at_most("45.000001", "45.000000", "0.000001")
    assert not rules.at_most("50.000000", "45.000000", "0.000001")


def test_quantize_signed_zero() -> None:
    assert rules.quantize(-0.0, "length_mm") == "0.000000"
    assert rules.quantize(-1e-12, "length_mm") == "0.000000"
    assert rules.quantize(-1e-6, "length_mm") == "-0.000001"


def test_direction_sign_canonicalization() -> None:
    hole = {
        "axis_dir": [0.0, 0.0, -1.0],
        "axis_point_mm": [1.0, 2.0, 0.0],
        "through": False,
        "segments": [{"diameter_mm": 10.0, "depth_mm": 2.0}, {"diameter_mm": 6.0, "depth_mm": 8.0}],
    }
    raw = _raw(
        solids=[_solid(holes=[hole], faces={"plane": 6, "cylinder": 2, "cone": 0, "other": 0})]
    )
    facts = rules.evaluate(
        raw, REQ, artifact_content_hash="sha256:" + "0" * 64, annotations={}
    ).facts
    assert facts is not None
    reported = facts["solids"][0]["holes"][0]
    assert reported["axis_dir"] == ["0.000000", "0.000000", "1.000000"]
    assert [s["diameter_mm"] for s in reported["segments"]] == ["6.000000", "10.000000"]


def test_counterbore_stack_does_not_match_a_single_hole_requirement() -> None:
    hole = {
        "axis_dir": [0.0, 0.0, 1.0],
        "axis_point_mm": [1.0, 2.0, 0.0],
        "through": True,
        "segments": [{"diameter_mm": 6.6, "depth_mm": 6.0}, {"diameter_mm": 11.0, "depth_mm": 4.0}],
    }
    raw = _raw(solids=[_solid(holes=[hole])])
    req = canonical_requirements(
        {
            "requirements_schema_version": "0.2.0",
            "holes": [
                {"diameter_mm": "6.6", "diameter_tol_mm": "0.01", "count": "1", "kind": "through"}
            ],
        }
    )
    evaluation = rules.evaluate(
        raw, req, artifact_content_hash="sha256:" + "0" * 64, annotations={}
    )
    assert evaluation.reason is GeometryReason.REQUIREMENT_NOT_MET


# --- identity v2 and the consumer check (§4), with a real verified result --------------------


@pytest.fixture(scope="module")
def bp01(verifier: GeometryVerifier) -> GeometryEngineeringResult:
    stem, declared, _e, _f = CASES["BP-01"]
    outcome = verifier.evaluate(
        GeometryTask(task_id="identity", requirements=declared), StepArtifact(payload=payload(stem))
    )
    assert isinstance(outcome, GeometryEngineeringResult)
    return outcome


def test_bundle_round_trip(bp01: GeometryEngineeringResult) -> None:
    bundle = json.loads(json.dumps(bp01.bundle()))
    received = from_bundle(bundle, step_bytes=payload("BP-01"))
    assert received.result_id == bp01.result_id
    assert received.content_hash == bp01.content_hash
    assert bundle["result"]["verifier"] == {
        "component": "velith-geometry-verifier",
        "version": "0.2.0",
    }


def _tampered(bundle: dict[str, Any], path: tuple[Any, ...], value: Any) -> dict[str, Any]:
    copied = copy.deepcopy(bundle)
    node = copied
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return copied


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("geometry_facts", "solids", 0, "volume_mm3"), "1.000"),
        (("geometry_facts", "conformance", 0, "result"), "NOT_MET"),
        (("result", "design_artifact", "media_type"), "application/vnd.velith.swe-patch+json"),
        (("result", "geometry_facts", "media_type"), "application/json"),
        (("result", "verifier", "version"), "0.2.1"),
        (("result", "verified"), 1),
        (("bundle_schema_version",), "0.1.0"),
    ],
)
def test_consumer_check_rejects_tampering(
    bp01: GeometryEngineeringResult, path: tuple[Any, ...], value: Any
) -> None:
    with pytest.raises(ContractError):
        from_bundle(_tampered(json.loads(json.dumps(bp01.bundle())), path, value))


def test_consumer_check_rejects_wrong_step_bytes(bp01: GeometryEngineeringResult) -> None:
    with pytest.raises(ContractError):
        from_bundle(bp01.bundle(), step_bytes=payload("BP-02"))


def test_no_downgrade_between_v1_and_v2(bp01: GeometryEngineeringResult) -> None:
    v2_wire = bp01.to_wire()
    with pytest.raises(ContractError):
        from_wire(v2_wire)  # the v1 consumer refuses the sixth field
    v1_like = {k: v for k, v in v2_wire.items() if k != "geometry_facts"}
    with pytest.raises(ContractError):
        from_bundle(
            {"bundle_schema_version": "0.2.0", "result": v1_like, "geometry_facts": bp01.facts}
        )


def test_facts_domain_is_strings_only() -> None:
    with pytest.raises(ContractError):
        facts_hash({"a": 1})
    with pytest.raises(ContractError):
        facts_hash({"a": "x\ud800"})
    assert facts_hash({"a": ["x", {"b": "y"}]}).startswith("sha256:")


def test_identity_is_independent_of_the_verifier_instance(bp01: GeometryEngineeringResult) -> None:
    assert bp01.verifier == VerifierIdentity(component="velith-geometry-verifier", version="0.2.0")
    assert Decimal(bp01.facts["solids"][0]["volume_mm3"]) > 0
