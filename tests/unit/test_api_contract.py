"""Engineering API v0 contract tests (D33; API_V0_SPEC §1-§4, acceptance V3-V6, V8 scope).

Pins: the five-field wire contract; the Option B identity view and its exclusions; consumer-side
integrity checks; the public verification rule and its documented divergence from the frozen M7
rule; the closed ``UnverifiedOutcome`` reasons; content identity (ID-1); the packaged schema; the
Velith -> Noetica verdict mapping; and the import boundary.
"""

from __future__ import annotations

import ast
import copy
import itertools
import json
import os
import subprocess
import sys
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
from noetica.interfaces.provenance import Provenance
from noetica.interfaces.verification import VerdictStatus
from pydantic import ValidationError

from velith.api import (
    CONTENT_HASH_PATTERN,
    IDENTITY_VERSION,
    SEMVER_PATTERN,
    SWE_VERIFIER_COMPONENT,
    VERDICT_STATUS_BY_STATE,
    WIRE_FIELDS,
    ContractError,
    DesignArtifact,
    EngineeringResult,
    EngineeringTask,
    ReceivedEngineeringResult,
    SwePatch,
    SwePatchPayload,
    UnverifiedOutcome,
    UnverifiedReason,
    VerificationEvidence,
    VerifierIdentity,
    content_hash_of,
    derive_id,
    from_wire,
    identity_view,
    result_from_verification,
    unverified_reason,
)
from velith.arms.filters import is_verified_success
from velith.episodes.episode import Episode, VerdictState

_API_DIR = Path(__file__).resolve().parents[2] / "src" / "velith" / "api"
_PATCH = (
    "--- a/calculator.py\n+++ b/calculator.py\n@@ -1 +1 @@\n"
    "-    return a - b\n+    return a + b\n"
)


def _evidence(**overrides: Any) -> VerificationEvidence:
    fields: dict[str, Any] = {
        "verdict_status": VerdictStatus.PASSED,
        "flaky": False,
        "flake_rerun_count": 3,
        "secondary_passed": True,
        "network_isolated": True,
    }
    fields.update(overrides)
    return VerificationEvidence(**fields)


def _artifact(task_id: str = "calc_add_bug") -> DesignArtifact:
    return DesignArtifact(payload=SwePatchPayload(task_id=task_id, patch=SwePatch(text=_PATCH)))


def _verifier(version: str = "0.1.0") -> VerifierIdentity:
    return VerifierIdentity(component=SWE_VERIFIER_COMPONENT, version=version)


def _produce(evidence: VerificationEvidence | None = None) -> EngineeringResult | UnverifiedOutcome:
    return result_from_verification(
        EngineeringTask(task_id="calc_add_bug"),
        _artifact(),
        evidence if evidence is not None else _evidence(),
        verifier=_verifier(),
        provenance=Provenance(source="test", transform="contract"),
    )


def _result() -> EngineeringResult:
    result = _produce()
    assert isinstance(result, EngineeringResult)
    return result


def _wire() -> dict[str, Any]:
    """The wire object as a consumer receives it: serialized to JSON text and parsed back."""
    parsed: dict[str, Any] = json.loads(json.dumps(_result().to_wire()))
    return parsed


# --- Wire contract (R-WIRE) -------------------------------------------------------------------


def test_wire_object_is_exactly_the_five_stub_fields() -> None:
    wire = _wire()
    assert set(wire) == WIRE_FIELDS
    assert set(wire["verifier"]) == {"component", "version"}
    assert set(wire["design_artifact"]) == {"media_type", "ref", "content_hash"}
    assert wire["verified"] is True
    assert "task_id" not in wire and "evidence" not in wire and "provenance" not in wire


def test_valid_wire_object_round_trips_as_a_received_claim() -> None:
    received = from_wire(_wire())
    assert isinstance(received, ReceivedEngineeringResult)
    assert not isinstance(received, EngineeringResult)
    assert received.to_wire() == _wire()


@pytest.mark.parametrize("field", sorted(WIRE_FIELDS))
def test_missing_wire_field_is_rejected(field: str) -> None:
    wire = _wire()
    del wire[field]
    with pytest.raises(ContractError):
        from_wire(wire)


@pytest.mark.parametrize("extra", ["evidence", "task_id", "provenance", "schema_version"])
def test_extra_wire_field_is_rejected(extra: str) -> None:
    wire = _wire()
    wire[extra] = {}
    with pytest.raises(ContractError):
        from_wire(wire)


def test_extra_nested_field_is_rejected() -> None:
    wire = _wire()
    wire["design_artifact"]["payload"] = "x"
    with pytest.raises(ContractError):
        from_wire(wire)


@pytest.mark.parametrize("value", [False, "true", 1, None])
def test_verified_must_be_literal_true(value: object) -> None:
    wire = _wire()
    wire["verified"] = value
    with pytest.raises(ContractError):
        from_wire(wire)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("verifier", "component"), "other-verifier"),
        (("verifier", "version"), "0.1.1"),
        (("design_artifact", "media_type"), "model/step"),
        (("design_artifact", "content_hash"), "sha256:" + "b" * 64),
        (("design_artifact", "ref"), "55555555-5555-5555-5555-555555555555"),
        (("content_hash",), "sha256:" + "a" * 64),
        (("result_id",), "44444444-4444-4444-4444-444444444444"),
    ],
)
def test_single_field_change_without_recomputation_is_detected(
    path: tuple[str, ...], value: str
) -> None:
    wire = _wire()
    target = wire
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ContractError):
        from_wire(wire)


def test_consistent_recomputation_passes_so_the_hash_is_not_authenticity() -> None:
    """API_V0_SPEC §4: an actor who recomputes the hash and ids defeats the check."""
    wire = _wire()
    forged = copy.deepcopy(wire)
    forged["verifier"]["component"] = "someone-else"
    view = {k: v for k, v in forged.items() if k not in {"result_id", "content_hash"}}
    view["identity_version"] = IDENTITY_VERSION
    forged["content_hash"] = content_hash_of(view)
    forged["result_id"] = derive_id(forged["content_hash"])
    assert from_wire(forged).verifier.component == "someone-else"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("result_id",), "2AC44842-2B16-5DBE-AE75-028DD4D44A26"),
        (("result_id",), "not-a-uuid"),
        (("design_artifact", "ref"), "{cdf5e4da-da47-5e52-b845-448ab5cc6bb1}"),
        (("content_hash",), "SHA256:" + "0" * 64),
        (("verifier", "version"), "0.1.0+local"),
        (("verifier", "component"), ""),
        (("design_artifact", "media_type"), ""),
    ],
)
def test_malformed_wire_values_are_rejected(path: tuple[str, ...], value: str) -> None:
    wire = _wire()
    target = wire
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ContractError):
        from_wire(wire)


# --- Identity view (Option B, §3) ------------------------------------------------------------


def test_identity_view_is_wire_minus_hash_and_id_plus_identity_version() -> None:
    result = _result()
    view = identity_view(result.verifier, result.design_artifact)
    wire = result.to_wire()
    expected = {k: v for k, v in wire.items() if k not in {"result_id", "content_hash"}}
    expected["identity_version"] = IDENTITY_VERSION
    assert view == expected
    assert result.content_hash == content_hash_of(view)
    assert result.result_id == derive_id(result.content_hash)


def test_local_only_fields_do_not_enter_identity() -> None:
    """ID-1: runs differing only in local evidence/provenance share the content identity."""
    first = _produce(_evidence(flake_rerun_count=3))
    second = result_from_verification(
        EngineeringTask(task_id="calc_add_bug"),
        _artifact(),
        _evidence(flake_rerun_count=5),
        verifier=_verifier(),
        provenance=Provenance(source="another-run", transform="contract"),
    )
    assert isinstance(first, EngineeringResult) and isinstance(second, EngineeringResult)
    assert first.evidence != second.evidence
    assert (first.result_id, first.content_hash) == (second.result_id, second.content_hash)


def test_verifier_version_and_artifact_enter_identity() -> None:
    base = _result()
    other_version = result_from_verification(
        EngineeringTask(task_id="calc_add_bug"),
        _artifact(),
        _evidence(),
        verifier=_verifier("0.2.0"),
        provenance=Provenance(source="test", transform="contract"),
    )
    other_task = result_from_verification(
        EngineeringTask(task_id="other_task"),
        _artifact("other_task"),
        _evidence(),
        verifier=_verifier(),
        provenance=Provenance(source="test", transform="contract"),
    )
    assert isinstance(other_version, EngineeringResult)
    assert isinstance(other_task, EngineeringResult)
    assert len({base.content_hash, other_version.content_hash, other_task.content_hash}) == 3


@pytest.mark.parametrize(
    "value",
    [
        {"x": 1.0},
        {"x": float("nan")},
        {"x": 1},
        {"x": None},
        {"x": ["a"]},
        {"ключ": "non-ascii key"},
        {1: "non-string key"},
    ],
)
def test_identity_domain_refuses_values_outside_the_canonical_subset(value: Any) -> None:
    with pytest.raises(ContractError):
        content_hash_of(value)


def test_derive_id_requires_a_prefixed_content_hash() -> None:
    with pytest.raises(ContractError):
        derive_id("0" * 64)


# --- Verification rule (§2) ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"verdict_status": VerdictStatus.FAILED}, UnverifiedReason.VERDICT_NOT_PASSED),
        ({"verdict_status": VerdictStatus.PATCH_APPLY_FAILED}, UnverifiedReason.VERDICT_NOT_PASSED),
        ({"verdict_status": VerdictStatus.NO_PATCH}, UnverifiedReason.VERDICT_NOT_PASSED),
        ({"verdict_status": VerdictStatus.INFRA_ERROR}, UnverifiedReason.VERDICT_NOT_PASSED),
        ({"flaky": True}, UnverifiedReason.FLAKY),
        ({"secondary_passed": False}, UnverifiedReason.SECONDARY_FAILED),
        ({"secondary_passed": None}, UnverifiedReason.SECONDARY_ABSENT),
        ({"network_isolated": False}, UnverifiedReason.ISOLATION_DISABLED),
        ({"flake_rerun_count": 1}, UnverifiedReason.INSUFFICIENT_RERUNS),
    ],
)
def test_each_failing_condition_yields_its_unverified_outcome(
    overrides: dict[str, Any], reason: UnverifiedReason
) -> None:
    outcome = _produce(_evidence(**overrides))
    assert isinstance(outcome, UnverifiedOutcome)
    assert outcome.reason is reason
    assert outcome.task_id == "calc_add_bug"


def test_reason_precedence_is_the_declared_order() -> None:
    order = list(UnverifiedReason)
    failing: dict[UnverifiedReason, dict[str, Any]] = {
        UnverifiedReason.VERDICT_NOT_PASSED: {"verdict_status": VerdictStatus.FAILED},
        UnverifiedReason.FLAKY: {"flaky": True},
        UnverifiedReason.SECONDARY_FAILED: {"secondary_passed": False},
        UnverifiedReason.SECONDARY_ABSENT: {"secondary_passed": None},
        UnverifiedReason.ISOLATION_DISABLED: {"network_isolated": False},
        UnverifiedReason.INSUFFICIENT_RERUNS: {"flake_rerun_count": 1},
    }
    assert set(failing) == set(order)
    same_field = {UnverifiedReason.SECONDARY_FAILED, UnverifiedReason.SECONDARY_ABSENT}
    for first, second in itertools.combinations(order, 2):
        if {first, second} == same_field:
            continue  # both are values of secondary_passed; they cannot fail together
        combined = {**failing[second], **failing[first]}
        assert unverified_reason(_evidence(**combined)) is first


def test_only_fully_qualifying_evidence_produces_a_result() -> None:
    for status, flaky, secondary, isolated, reruns in itertools.product(
        list(VerdictStatus), [False, True], [True, False, None], [True, False], [1, 2, 3]
    ):
        evidence = _evidence(
            verdict_status=status,
            flaky=flaky,
            secondary_passed=secondary,
            network_isolated=isolated,
            flake_rerun_count=reruns,
        )
        produced = _produce(evidence)
        qualifies = (
            status is VerdictStatus.PASSED
            and not flaky
            and secondary is True
            and isolated
            and reruns >= 2
        )
        assert isinstance(produced, EngineeringResult) is qualifies


def test_public_rule_is_stricter_than_frozen_m7_on_absent_secondary() -> None:
    """Documented divergence (§2): M7 admits secondary_passed=None; the public API does not."""
    episode = Episode.build(
        task_id="t",
        seed=0,
        model="m",
        model_version="v",
        prompt="p",
        patch="d",
        verdict_state=VerdictState.PASSED,
        verdict_output="out",
        prompt_tokens=1,
        completion_tokens=1,
        latency_seconds=1.0,
        verify_seconds=1.0,
        velith_version="0.0.0",
        secondary_passed=None,
        timestamp="2026-10-30T00:00:00+00:00",
    )
    assert is_verified_success(episode) is True
    outcome = _produce(_evidence(secondary_passed=None))
    assert isinstance(outcome, UnverifiedOutcome)
    assert outcome.reason is UnverifiedReason.SECONDARY_ABSENT


def test_result_with_failing_evidence_cannot_be_constructed_directly() -> None:
    good = _result()
    fields = {name: getattr(good, name) for name in EngineeringResult.model_fields}
    fields["evidence"] = _evidence(secondary_passed=None)
    with pytest.raises(ValidationError, match="SECONDARY_ABSENT"):
        EngineeringResult(**fields)


def test_result_with_inconsistent_identity_cannot_be_constructed_directly() -> None:
    good = _result()
    fields = {name: getattr(good, name) for name in EngineeringResult.model_fields}
    fields["content_hash"] = "sha256:" + "a" * 64
    with pytest.raises(ValidationError, match="content_hash"):
        EngineeringResult(**fields)


def test_artifact_must_belong_to_the_task() -> None:
    with pytest.raises(ContractError):
        result_from_verification(
            EngineeringTask(task_id="calc_add_bug"),
            _artifact("other_task"),
            _evidence(),
            verifier=_verifier(),
            provenance=Provenance(source="test", transform="contract"),
        )


def test_non_software_domain_is_unsupported() -> None:
    with pytest.raises(ValidationError):
        EngineeringTask.model_validate({"task_id": "t", "domain": "mechanical"})
    with pytest.raises(ValidationError):
        DesignArtifact.model_validate(
            {"media_type": "model/step", "payload": _artifact().payload.model_dump()}
        )


# --- Verdict taxonomy mapping (V5) ------------------------------------------------------------


def test_verdict_mapping_is_total_and_value_preserving() -> None:
    assert set(VERDICT_STATUS_BY_STATE) == set(VerdictState)
    assert {status.value for status in VerdictStatus} == {state.value for state in VerdictState}
    for state, status in VERDICT_STATUS_BY_STATE.items():
        assert status.value == state.value


# --- Packaged schema -------------------------------------------------------------------------


def _schema() -> dict[str, Any]:
    text = (
        resources.files("velith.api")
        .joinpath("schemas/engineering_result.v1.schema.json")
        .read_text(encoding="utf-8")
    )
    loaded: dict[str, Any] = json.loads(text)
    return loaded


def test_packaged_schema_matches_the_wire_contract() -> None:
    schema = _schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"]) == WIRE_FIELDS
    assert schema["properties"]["verified"] == {"const": True}
    artifact = schema["properties"]["design_artifact"]
    assert artifact["additionalProperties"] is False
    assert (
        set(artifact["required"])
        == set(artifact["properties"])
        == {
            "media_type",
            "ref",
            "content_hash",
        }
    )
    defs = schema["$defs"]
    assert defs["ContentHash"]["pattern"] == CONTENT_HASH_PATTERN
    assert defs["SemVer"]["pattern"] == SEMVER_PATTERN
    assert defs["Uuid"] == {"type": "string", "format": "uuid"}
    assert defs["ProducedBy"]["additionalProperties"] is False
    assert set(defs["ProducedBy"]["required"]) == {"component", "version"}


# --- Import boundary (V6; D30 item 4) --------------------------------------------------------

_FORBIDDEN_ROOTS = ("mini_prometheus", "miniflywire", "velith.analysis", "statsmodels")


def test_api_sources_import_no_forbidden_module() -> None:
    for source in sorted(_API_DIR.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert not name.startswith(_FORBIDDEN_ROOTS), f"{source.name} imports {name}"


def test_importing_the_api_loads_no_forbidden_module() -> None:
    probe = (
        "import sys, velith.api; "
        f"bad = sorted(m for m in sys.modules if m.startswith({_FORBIDDEN_ROOTS!r})); "
        "print(bad); sys.exit(1 if bad else 0)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ),
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
