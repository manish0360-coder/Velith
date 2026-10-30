"""Engineering API v0 contract: types, identity, canonical hashing, validation (D33, API-0 C1).

The normative text is ``docs/API_V0_SPEC.md``. This module implements its contract core and
nothing else: no verifier is invoked, nothing is proposed, nothing is persisted. Turning a
sandbox verdict into :class:`VerificationEvidence` is C2; packaging is C3; the demo is C4.

Wire contract (spec §1, R-WIRE). An ``EngineeringResult`` crosses the Layer 3 -> Layer 4 boundary
as exactly five fields — ``result_id``, ``content_hash``, ``verified``, ``verifier`` and
``design_artifact`` — the shape of Mini Prometheus' consumed stub. Evidence, ``task_id`` and
provenance stay local to Velith (R-EVID).

Identity (spec §3, Option B + ID-1). The identity view is the wire object without ``result_id`` and
``content_hash``, plus the contract constant ``identity_version``. It is serialized canonically —
``json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)``, UTF-8 — and hashed with
SHA-256 through Noetica's ``canonical_sha256`` (D30 item 3: no new hashing mechanism in Velith).
``result_id = uuid5(NS_VELITH_API, content_hash)``. A consumer holding only the wire object and the
two pinned constants can recompute both. ``result_id`` identifies the deterministic content claim
and its artifact, not a verification run: separate runs of the same claim share it (ID-1).

Security scope (spec §4). Recomputing the hash detects accidental changes, and changes made to a
covered field without recomputing the hash and ids. It does not stop an actor who recomputes them,
and it provides no authenticity, no non-repudiation and no proof that verification occurred.

Verification rule (spec §2, R-RULE). A public result exists only if the verdict is ``PASSED``, the
primary was not flaky over at least two reruns, the held-out secondary suite ran and passed
(``secondary_passed is True``), and network isolation was on. This is deliberately stricter than the
frozen M7 rule ``velith.arms.filters.is_verified_success``, which also admits
``secondary_passed is None``; M7 is not changed.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from enum import Enum
from typing import Any, Final, Literal

from noetica.interfaces.provenance import Provenance
from noetica.interfaces.verification import VerdictStatus
from noetica.provenance.identity import canonical_sha256
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from velith.episodes.episode import VerdictState

# --- Contract constants (spec §3.1, P-CONST) ------------------------------------------------

#: Domain-separation tag of the result identity view. Not transmitted; pinned by both sides.
IDENTITY_VERSION: Final[str] = "velith-engineering-result-identity-v1"

#: The name the API namespace is derived from: ``uuid5(NAMESPACE_URL, NS_VELITH_API_NAME)``.
NS_VELITH_API_NAME: Final[str] = "https://github.com/manish0360-coder/Velith#engineering-api"

#: The namespace for every deterministic API id (artifact ``ref`` and ``result_id``).
NS_VELITH_API: Final[uuid.UUID] = uuid.UUID("924036ea-946e-57d4-9a75-e94278f979aa")

#: The only design-artifact media type in v0: a software patch payload (canonical JSON).
MEDIA_TYPE_SWE_PATCH: Final[str] = "application/vnd.velith.swe-patch+json"

#: The v0 verifier component name carried in ``verifier.component``.
SWE_VERIFIER_COMPONENT: Final[str] = "velith-swe-verifier"

#: Version of the design-artifact payload shape.
ARTIFACT_SCHEMA_VERSION: Final[str] = "0.1.0"

#: Minimum primary-test runs for "not flaky" to be a measurement rather than a default.
MIN_FLAKE_RERUNS: Final[int] = 2

#: The wire field set, exactly the consumed stub's ``required`` list (R-WIRE).
WIRE_FIELDS: Final[frozenset[str]] = frozenset(
    {"result_id", "content_hash", "verified", "verifier", "design_artifact"}
)

#: Fields of the wire object outside the identity view (spec §3.3): the hash and its derivative.
IDENTITY_EXCLUDED_WIRE_FIELDS: Final[frozenset[str]] = frozenset({"result_id", "content_hash"})

CONTENT_HASH_PATTERN: Final[str] = r"^sha256:[0-9a-f]{64}$"
SEMVER_PATTERN: Final[str] = r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$"

_CONTENT_HASH_RE: Final[re.Pattern[str]] = re.compile(CONTENT_HASH_PATTERN)

#: Noetica's verdict taxonomy for each frozen Velith verdict state (same members, by value).
VERDICT_STATUS_BY_STATE: Final[Mapping[VerdictState, VerdictStatus]] = {
    state: VerdictStatus(state.value) for state in VerdictState
}


# --- Canonical hashing (spec §3.4) ----------------------------------------------------------


class ContractError(ValueError):
    """A value violates the API v0 contract (shape, identity or integrity)."""


def _check_identity_safe(value: object, path: str = "$") -> None:
    """Refuse anything outside the identity value domain: ASCII-keyed objects, strings, booleans.

    Numbers (so floats, NaN and infinities), nulls and arrays never occur in a v0 identity view or
    artifact payload. Refusing them keeps the canonical form inside the subset on which the
    Velith, Noetica and Mini Prometheus serializers are byte-identical (spec §3.2, F2).
    """
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key.isascii():
                raise ContractError(f"{path}: keys must be ASCII strings, got {key!r}")
            _check_identity_safe(item, f"{path}.{key}")
        return
    if isinstance(value, bool | str):
        return
    raise ContractError(f"{path}: unsupported identity value type {type(value).__name__}")


def content_hash_of(value: Mapping[str, Any]) -> str:
    """Return ``"sha256:" + canonical_sha256(value)`` after the identity-domain check."""
    plain = dict(value)
    _check_identity_safe(plain)
    return "sha256:" + canonical_sha256(plain)


def derive_id(content_hash: str) -> str:
    """Return ``str(uuid5(NS_VELITH_API, content_hash))`` for a ``sha256:``-prefixed hash."""
    if not _CONTENT_HASH_RE.match(content_hash):
        raise ContractError(f"not a sha256 content hash: {content_hash!r}")
    return str(uuid.uuid5(NS_VELITH_API, content_hash))


def _is_canonical_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False


# --- Value types ----------------------------------------------------------------------------

_FROZEN: Final[ConfigDict] = ConfigDict(frozen=True, extra="forbid", strict=True)


class EngineeringTask(BaseModel):
    """One software engineering task, by id (in-process only in v0; spec §1)."""

    model_config = _FROZEN

    task_id: str = Field(min_length=1)
    domain: Literal["software"] = "software"


class SwePatch(BaseModel):
    """A candidate change as a unified diff."""

    model_config = _FROZEN

    format: Literal["unified_diff"] = "unified_diff"
    text: str = Field(min_length=1)


class SwePatchPayload(BaseModel):
    """The design-artifact payload: the design only, never the verification claim (spec §1)."""

    model_config = _FROZEN

    artifact_schema_version: Literal["0.1.0"] = "0.1.0"
    domain: Literal["software"] = "software"
    task_id: str = Field(min_length=1)
    patch: SwePatch


class DesignArtifactRef(BaseModel):
    """The wire view of a design artifact: ``{media_type, ref, content_hash}``."""

    model_config = _FROZEN

    media_type: str = Field(min_length=1)
    ref: str
    content_hash: str = Field(pattern=CONTENT_HASH_PATTERN)

    @model_validator(mode="after")
    def _ref_is_canonical_uuid(self) -> DesignArtifactRef:
        if not _is_canonical_uuid(self.ref):
            raise ValueError(f"ref must be a lowercase hyphenated UUID, got {self.ref!r}")
        return self


class DesignArtifact(BaseModel):
    """A Velith design artifact: media type plus payload; hash and id are derived (spec §3.5)."""

    model_config = _FROZEN

    media_type: Literal["application/vnd.velith.swe-patch+json"] = (
        "application/vnd.velith.swe-patch+json"
    )
    payload: SwePatchPayload

    @property
    def content_hash(self) -> str:
        """``sha256:`` + the canonical SHA-256 of the payload (equals sha256 of its bytes)."""
        return content_hash_of(self.payload.model_dump(mode="json"))

    @property
    def artifact_id(self) -> str:
        """``uuid5(NS_VELITH_API, content_hash)``."""
        return derive_id(self.content_hash)

    def reference(self) -> DesignArtifactRef:
        """The wire view carried inside an ``EngineeringResult``."""
        return DesignArtifactRef(
            media_type=self.media_type, ref=self.artifact_id, content_hash=self.content_hash
        )


class VerifierIdentity(BaseModel):
    """``verifier`` on the wire: which component, at which version, makes the claim."""

    model_config = _FROZEN

    component: str = Field(min_length=1)
    version: str = Field(pattern=SEMVER_PATTERN)


class UnverifiedReason(str, Enum):
    """Why a verification produced no public result (closed; precedence = declaration order)."""

    VERDICT_NOT_PASSED = "VERDICT_NOT_PASSED"
    FLAKY = "FLAKY"
    SECONDARY_FAILED = "SECONDARY_FAILED"
    SECONDARY_ABSENT = "SECONDARY_ABSENT"
    ISOLATION_DISABLED = "ISOLATION_DISABLED"
    INSUFFICIENT_RERUNS = "INSUFFICIENT_RERUNS"


class VerificationEvidence(BaseModel):
    """The grounded measurement behind a claim. Local to Velith; never on the wire (R-EVID)."""

    model_config = _FROZEN

    verdict_status: VerdictStatus
    flaky: bool
    flake_rerun_count: int = Field(ge=1)
    secondary_passed: bool | None
    network_isolated: bool


def unverified_reason(evidence: VerificationEvidence) -> UnverifiedReason | None:
    """Apply the public verification rule (spec §2); ``None`` means the evidence qualifies.

    Stricter than the frozen M7 ``is_verified_success``: ``secondary_passed is None`` (no secondary
    suite ran) is ``SECONDARY_ABSENT`` here, while M7 admits it as a verified success.
    """
    if evidence.verdict_status is not VerdictStatus.PASSED:
        return UnverifiedReason.VERDICT_NOT_PASSED
    if evidence.flaky:
        return UnverifiedReason.FLAKY
    if evidence.secondary_passed is False:
        return UnverifiedReason.SECONDARY_FAILED
    if evidence.secondary_passed is None:
        return UnverifiedReason.SECONDARY_ABSENT
    if not evidence.network_isolated:
        return UnverifiedReason.ISOLATION_DISABLED
    if evidence.flake_rerun_count < MIN_FLAKE_RERUNS:
        return UnverifiedReason.INSUFFICIENT_RERUNS
    return None


class UnverifiedOutcome(BaseModel):
    """A verification that licenses no public claim. Never crosses the wire."""

    model_config = _FROZEN

    task_id: str = Field(min_length=1)
    verdict: VerdictStatus
    reason: UnverifiedReason


# --- Identity view (spec §3.2-§3.5) ----------------------------------------------------------


def identity_view(verifier: VerifierIdentity, design_artifact: DesignArtifactRef) -> dict[str, Any]:
    """The Option B identity view: the wire fields minus ``{result_id, content_hash}``, plus the
    contract constant ``identity_version``. Every key is ASCII and every leaf a string except
    ``verified``."""
    return {
        "identity_version": IDENTITY_VERSION,
        "verified": True,
        "verifier": {"component": verifier.component, "version": verifier.version},
        "design_artifact": {
            "media_type": design_artifact.media_type,
            "ref": design_artifact.ref,
            "content_hash": design_artifact.content_hash,
        },
    }


class _WireClaim(BaseModel):
    """The five wire fields plus the integrity checks a consumer can perform (spec §3.6)."""

    model_config = ConfigDict(
        frozen=True, extra="forbid", strict=True, arbitrary_types_allowed=True
    )

    result_id: str
    content_hash: str = Field(pattern=CONTENT_HASH_PATTERN)
    verified: Literal[True]
    verifier: VerifierIdentity
    design_artifact: DesignArtifactRef

    @field_validator("verified", mode="before")
    @classmethod
    def _verified_is_the_boolean_true(cls, value: object) -> object:
        # Literal[True] alone admits 1 (1 == True); the stub's `const: true` does not.
        if value is not True:
            raise ValueError("verified must be the JSON boolean true")
        return value

    @model_validator(mode="after")
    def _identity_is_consistent(self) -> _WireClaim:
        if not _is_canonical_uuid(self.result_id):
            raise ValueError(f"result_id must be a lowercase hyphenated UUID: {self.result_id!r}")
        expected_hash = content_hash_of(identity_view(self.verifier, self.design_artifact))
        if self.content_hash != expected_hash:
            raise ValueError("content_hash does not match the recomputed identity view")
        if self.result_id != derive_id(self.content_hash):
            raise ValueError("result_id is not uuid5(NS_VELITH_API, content_hash)")
        if self.design_artifact.ref != derive_id(self.design_artifact.content_hash):
            raise ValueError("design_artifact.ref is not uuid5(NS_VELITH_API, its content_hash)")
        return self

    def to_wire(self) -> dict[str, Any]:
        """The wire object: exactly the five stub fields, JSON-ready."""
        return {
            "result_id": self.result_id,
            "content_hash": self.content_hash,
            "verified": True,
            "verifier": self.verifier.model_dump(mode="json"),
            "design_artifact": self.design_artifact.model_dump(mode="json"),
        }


class ReceivedEngineeringResult(_WireClaim):
    """A wire object as received: shape- and integrity-checked, but only a claim.

    Passing :func:`from_wire` shows the covered fields are mutually consistent. It does not show
    who produced them, and it never becomes a producer-side :class:`EngineeringResult`.
    """


class EngineeringResult(_WireClaim):
    """A verified engineering result (producer side); build via :func:`result_from_verification`.

    Besides the wire fields it carries local-only ``task_id``, ``evidence`` and ``provenance``. The
    validator re-applies the verification rule to ``evidence``, so a result whose recorded evidence
    fails the rule cannot exist. It cannot stop in-process code from fabricating evidence values.
    """

    task_id: str = Field(min_length=1)
    evidence: VerificationEvidence
    provenance: Provenance

    @model_validator(mode="after")
    def _evidence_qualifies(self) -> EngineeringResult:
        reason = unverified_reason(self.evidence)
        if reason is not None:
            raise ValueError(f"evidence fails the public verification rule: {reason.value}")
        return self


def result_from_verification(
    task: EngineeringTask,
    artifact: DesignArtifact,
    evidence: VerificationEvidence,
    *,
    verifier: VerifierIdentity,
    provenance: Provenance,
) -> EngineeringResult | UnverifiedOutcome:
    """The single producer path: a public result if the evidence qualifies, else an outcome.

    ``verified`` is never a parameter: it is implied by returning an :class:`EngineeringResult`.
    Raises :class:`ContractError` if the artifact does not belong to ``task``.
    """
    if artifact.payload.task_id != task.task_id or artifact.payload.domain != task.domain:
        raise ContractError("design artifact does not belong to the engineering task")
    reason = unverified_reason(evidence)
    if reason is not None:
        return UnverifiedOutcome(
            task_id=task.task_id, verdict=evidence.verdict_status, reason=reason
        )
    ref = artifact.reference()
    content_hash = content_hash_of(identity_view(verifier, ref))
    return EngineeringResult(
        result_id=derive_id(content_hash),
        content_hash=content_hash,
        verified=True,
        verifier=verifier,
        design_artifact=ref,
        task_id=task.task_id,
        evidence=evidence,
        provenance=provenance,
    )


def from_wire(wire: Mapping[str, Any]) -> ReceivedEngineeringResult:
    """Validate a received wire object (spec §3.6) and return it as a claim.

    Raises :class:`ContractError` on any shape or integrity violation: a missing or extra field,
    ``verified`` not ``true``, a malformed UUID or hash, or a hash/id that does not recompute.
    """
    try:
        return ReceivedEngineeringResult.model_validate(dict(wire))
    except ValidationError as exc:
        raise ContractError(f"not a valid EngineeringResult wire object: {exc}") from exc
