"""Normative test vectors T1-T5b of the Engineering API v0 (D33; API_V0_SPEC §3.7).

These literals are the ratified contract. They are shared with consumers (Mini Prometheus pins its
own copies of the constants and reproduces T4-B/T5b without importing Velith), so a failure here
means the producer drifted from the contract — never "update the expected value".

Each vector is reproduced twice: through the production path (Noetica ``canonical_sha256``) and
through an independent standard-library restatement, so the two cannot drift together.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from noetica.interfaces.provenance import Provenance
from noetica.interfaces.verification import VerdictStatus
from noetica.provenance.identity import canonical_sha256

from velith.api import (
    IDENTITY_VERSION,
    MEDIA_TYPE_SWE_PATCH,
    NS_VELITH_API,
    NS_VELITH_API_NAME,
    SWE_VERIFIER_COMPONENT,
    DesignArtifact,
    EngineeringResult,
    EngineeringTask,
    SwePatch,
    SwePatchPayload,
    VerificationEvidence,
    VerifierIdentity,
    content_hash_of,
    derive_id,
    from_wire,
    result_from_verification,
)

T1_INPUT: dict[str, Any] = {}
T1_HASH = "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"

T2_INPUT: dict[str, Any] = {
    "z": "naïve—Δ",
    "a": [1, 2, {"y": None, "b": False}],
    "m": 'line\nbreak\t"q"\\',
}
T2_HASH = "sha256:a338311feee0b463f81a46a0e8b1438289f18a4638ea0579eda98be18be0f624"

T3_PATCH = (
    "--- a/calculator.py\n"
    "+++ b/calculator.py\n"
    "@@ -1,3 +1,3 @@\n"
    " # mypy: ignore-errors\n"
    " def add(a: int, b: int) -> int:\n"
    "-    return a - b\n"
    "+    return a + b\n"
)
T3_CANONICAL = (
    '{"artifact_schema_version":"0.1.0","domain":"software","patch":{"format":"unified_diff",'
    '"text":"--- a/calculator.py\\n+++ b/calculator.py\\n@@ -1,3 +1,3 @@\\n # mypy: ignore-errors'
    '\\n def add(a: int, b: int) -> int:\\n-    return a - b\\n+    return a + b\\n"},'
    '"task_id":"calc_add_bug"}'
)
T3_HASH = "sha256:ff39e80e72505b345d649cb5254e242490db0bf3ca67bcaed50d3274e11cae95"
T5A_REF = "cdf5e4da-da47-5e52-b845-448ab5cc6bb1"

T4B_CANONICAL = (
    '{"design_artifact":{"content_hash":"sha256:ff39e80e72505b345d649cb5254e242490db0bf3ca67bcae'
    'd50d3274e11cae95","media_type":"application/vnd.velith.swe-patch+json","ref":"cdf5e4da-da47-'
    '5e52-b845-448ab5cc6bb1"},"identity_version":"velith-engineering-result-identity-v1",'
    '"verified":true,"verifier":{"component":"velith-swe-verifier","version":"0.1.0"}}'
)
T4B_HASH = "sha256:6c2babe95dfa51f142494ef7633322d68eed8983a775faa048f1060cee0317a0"
T5B_RESULT_ID = "2ac44842-2b16-5dbe-ae75-028dd4d44a26"

NS_LITERAL = "924036ea-946e-57d4-9a75-e94278f979aa"


def _stdlib_canonical(value: Any) -> str:
    """Independent restatement of the canonical serialization (API_V0_SPEC §3.4)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _stdlib_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_stdlib_canonical(value).encode("utf-8")).hexdigest()


def _t3_artifact() -> DesignArtifact:
    return DesignArtifact(
        payload=SwePatchPayload(task_id="calc_add_bug", patch=SwePatch(text=T3_PATCH))
    )


def _t4b_result() -> EngineeringResult:
    result = result_from_verification(
        EngineeringTask(task_id="calc_add_bug"),
        _t3_artifact(),
        VerificationEvidence(
            verdict_status=VerdictStatus.PASSED,
            flaky=False,
            flake_rerun_count=3,
            secondary_passed=True,
            network_isolated=True,
        ),
        verifier=VerifierIdentity(component=SWE_VERIFIER_COMPONENT, version="0.1.0"),
        provenance=Provenance(source="test", transform="vector"),
    )
    assert isinstance(result, EngineeringResult)
    return result


def test_constants_are_the_ratified_literals() -> None:
    assert IDENTITY_VERSION == "velith-engineering-result-identity-v1"
    assert MEDIA_TYPE_SWE_PATCH == "application/vnd.velith.swe-patch+json"
    assert SWE_VERIFIER_COMPONENT == "velith-swe-verifier"
    assert str(NS_VELITH_API) == NS_LITERAL
    assert uuid.uuid5(uuid.NAMESPACE_URL, NS_VELITH_API_NAME) == NS_VELITH_API


def test_t1_t2_serializer_vectors() -> None:
    """T1/T2 pin the serializer only (T2 is deliberately not a valid identity view)."""
    assert "sha256:" + canonical_sha256(T1_INPUT) == T1_HASH == _stdlib_hash(T1_INPUT)
    assert "sha256:" + canonical_sha256(T2_INPUT) == T2_HASH == _stdlib_hash(T2_INPUT)
    assert content_hash_of(T1_INPUT) == T1_HASH


def test_t3_artifact_payload_and_t5a_ref() -> None:
    artifact = _t3_artifact()
    payload = artifact.payload.model_dump(mode="json")
    assert _stdlib_canonical(payload) == T3_CANONICAL
    assert artifact.content_hash == T3_HASH == _stdlib_hash(payload)
    # sha256 of the canonical bytes, i.e. the bytes-hash rule for a stored canonical artifact.
    assert "sha256:" + hashlib.sha256(T3_CANONICAL.encode("utf-8")).hexdigest() == T3_HASH
    assert artifact.artifact_id == T5A_REF == derive_id(T3_HASH)
    assert str(uuid.uuid5(uuid.UUID(NS_LITERAL), T3_HASH)) == T5A_REF


def test_t4b_identity_and_t5b_result_id_from_the_producer() -> None:
    result = _t4b_result()
    assert result.content_hash == T4B_HASH
    assert result.result_id == T5B_RESULT_ID
    assert result.design_artifact.ref == T5A_REF
    assert result.design_artifact.content_hash == T3_HASH


def test_t4b_reproduced_from_the_wire_object_alone() -> None:
    """The consumer-side recomputation (§3.6) with only the stdlib and the two literals."""
    wire = json.loads(json.dumps(_t4b_result().to_wire()))
    view = {k: v for k, v in wire.items() if k not in {"result_id", "content_hash"}}
    view["identity_version"] = "velith-engineering-result-identity-v1"
    assert _stdlib_canonical(view) == T4B_CANONICAL
    assert _stdlib_hash(view) == wire["content_hash"] == T4B_HASH
    assert str(uuid.uuid5(uuid.UUID(NS_LITERAL), wire["content_hash"])) == wire["result_id"]
    assert str(uuid.uuid5(uuid.UUID(NS_LITERAL), T3_HASH)) == wire["design_artifact"]["ref"]
    assert from_wire(wire).result_id == T5B_RESULT_ID
