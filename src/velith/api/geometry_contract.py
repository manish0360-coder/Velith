"""Engineering API v0.2 geometry contract: G0 exact-geometry conformance (D34, D35; F r3 §1-§4).

The normative text is the frozen Gate 0 specification ``F_ENGINEERING_API_V0_2_SPEC_r3.md`` (owner
decision record 2026-11-05, rev 2). This module holds the geometry *contract* only: constants,
declared-requirement parsing (§3), the facts hash and the v2 result identity (§4), the bundle
and its consumer check. It never imports ``velith.geometry`` or ``OCP``; measuring is done there.

Scope (D34). G0 reports exact, quantized measurements of a declared STEP B-rep and checks them
against requirements the customer declared. It makes no FEA, GD&T, tolerance-inference, design or
manufacturability claim, and it never derives requirements from the model.

Identity (spec §4). Facts are hashed as ``"sha256:" + canonical_sha256(facts)`` through Noetica, as
the v1 identity is (no new hashing mechanism). The v2 identity view is the wire object without
``result_id`` and ``content_hash``, plus ``identity_version = IDENTITY_VERSION_V2``. A v1 wire
object (no ``geometry_facts``) can never pass :func:`from_bundle`, and a geometry wire object can
never pass the v1 :func:`velith.api.contract.from_wire` (it carries a sixth field).
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from decimal import Decimal, Inexact, localcontext
from enum import Enum
from typing import Any, Final, Literal

from noetica.interfaces.provenance import Provenance
from noetica.interfaces.verification import VerdictStatus
from noetica.provenance.identity import canonical_sha256
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from velith.api.contract import (
    CONTENT_HASH_PATTERN,
    ContractError,
    DesignArtifactRef,
    VerifierIdentity,
    content_hash_of,
    derive_id,
)

# --- Contract constants (spec F r3 §1, §2, §4, §6; D35) ----------------------------------------

#: Domain-separation tag of the v2 result identity view (spec §4). Pinned by both sides.
IDENTITY_VERSION_V2: Final[str] = "velith-engineering-result-identity-v2"
#: The design-artifact media type admitted by G0: one STEP file (ISO 10303-21), raw bytes.
MEDIA_TYPE_STEP: Final[str] = "model/step"
#: The media type of a ``GeometryFacts`` document.
MEDIA_TYPE_GEOMETRY_FACTS: Final[str] = "application/vnd.velith.geometry-facts+json"
#: ``verifier.component`` of the geometry verifier.
GEOMETRY_VERIFIER_COMPONENT: Final[str] = "velith-geometry-verifier"
#: Component version (D35 r2 item 1). Bumped on any change of the pinned tuple (D35 item 3, GA12).
GEOMETRY_VERIFIER_VERSION: Final[str] = "0.2.0"
FACTS_SCHEMA_VERSION: Final[str] = "0.2.0"
REQUIREMENTS_SCHEMA_VERSION: Final[str] = "0.2.0"
BUNDLE_SCHEMA_VERSION: Final[str] = "0.2.0"
#: Quantization rule id (spec §2, q-1) and annotation-scan rule id (a-1).
QUANTIZATION_RULE: Final[str] = "q-1"
ANNOTATION_SCAN_RULE: Final[str] = "a-1"
#: Pinned measurement kernel and binding (spec E; D35 pin tuple).
KERNEL: Final[str] = "OCCT"
KERNEL_VERSION: Final[str] = "8.0.1"
BINDING: Final[str] = "cadquery-ocp-novtk"
BINDING_VERSION: Final[str] = "8.0.1.1.0"
#: The temporary identity-supported platform (spec §6, Director qualification 1).
IDENTITY_PLATFORM: Final[str] = "linux-x86_64"
PLATFORM_POLICY: Final[str] = "temporary-identity-restriction-1"
#: Input size cap for a STEP payload (spec §1 / §6), bytes.
MAX_STEP_BYTES: Final[int] = 64 * 1024 * 1024
#: The facts' length quantum (q-1): tolerances below it cannot be evaluated against the facts.
LENGTH_QUANTUM: Final[Decimal] = Decimal("0.000001")
LENGTH_QUANTUM_DIGITS: Final[int] = 6
#: ``plausible_size_mm`` hard limits (spec §3), mm.
PLAUSIBLE_HARD_LIMITS: Final[tuple[Decimal, Decimal]] = (Decimal("0.001"), Decimal("10000"))
HOLE_KINDS: Final[tuple[str, ...]] = ("through", "blind")

_DECIMAL_RE: Final[re.Pattern[str]] = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]+)?")
_COUNT_RE: Final[re.Pattern[str]] = re.compile(r"[1-9][0-9]*")

# --- Declared requirements (spec F r3 §3; CH3-R1, CH3-R2) --------------------------------------


class RequirementError(ContractError):
    """A declared requirement violates its field grammar or the document structure (spec §3)."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field


def _decimal(value: object, field: str) -> Decimal:
    # fullmatch: no sign, no exponent, no whitespace, ASCII digits only. Never rounded.
    if not isinstance(value, str) or not _DECIMAL_RE.fullmatch(value):
        raise RequirementError(field, f"not an unsigned decimal string: {value!r}")
    return Decimal(value)


def canonical_decimal_text(value: Decimal) -> str:
    """Exact text of a non-negative decimal with at least 6 fraction digits; zeros beyond the 6th
    are removed. ``6.6`` -> ``6.600000``; ``0.1984375`` -> ``0.1984375``. Never rounds."""
    integer, _, fraction = format(value, "f").partition(".")
    fraction = fraction.rstrip("0")
    fraction = fraction.ljust(LENGTH_QUANTUM_DIGITS, "0")
    return f"{integer}.{fraction}"


def parse_length(value: object, field: str) -> str:
    """LENGTH kind: an exact positive decimal in mm (no fraction-digit cap)."""
    number = _decimal(value, field)
    if number <= 0:
        raise RequirementError(field, f"length must be > 0: {value!r}")
    return canonical_decimal_text(number)


def parse_tolerance(value: object, field: str) -> str:
    """TOLERANCE kind: as LENGTH, and at least the 1e-6 mm facts quantum."""
    number = _decimal(value, field)
    if number < LENGTH_QUANTUM:
        raise RequirementError(field, f"tolerance below the 1e-6 mm facts quantum: {value!r}")
    return canonical_decimal_text(number)


def parse_count(value: object, field: str) -> str:
    """COUNT kind: a positive integer string without leading zeros."""
    if not isinstance(value, str) or not _COUNT_RE.fullmatch(value):
        raise RequirementError(field, f"not a positive integer string: {value!r}")
    return value


def parse_bool(value: object, field: str) -> str:
    if value not in ("true", "false"):
        raise RequirementError(field, f"not 'true' or 'false': {value!r}")
    return str(value)


def parse_hole_kind(value: object, field: str) -> str:
    if value not in HOLE_KINDS:
        raise RequirementError(field, f"not one of {HOLE_KINDS}: {value!r}")
    return str(value)


def _exact_context_precision(*operands: str) -> int:
    return sum(len(operand) for operand in operands) + 2


def windows_overlap(nominal_a: str, tol_a: str, nominal_b: str, tol_b: str) -> bool:
    """Closed intervals ``[n-t, n+t]`` intersect, in exact decimal arithmetic."""
    with localcontext() as ctx:
        ctx.prec = _exact_context_precision(nominal_a, tol_a, nominal_b, tol_b)
        ctx.traps[Inexact] = True
        return abs(Decimal(nominal_a) - Decimal(nominal_b)) <= Decimal(tol_a) + Decimal(tol_b)


_TOP_LEVEL_DEFAULTS: Final[Mapping[str, Any]] = {
    "expected_solids": "1",
    "plausible_size_mm": ["0.1", "2000"],
    "length_tol_mm": "0.000001",
    "holes": [],
    "holes_exhaustive": "true",
}
_TOP_LEVEL_FIELDS: Final[frozenset[str]] = frozenset(
    {"requirements_schema_version", "envelope_max_mm", *_TOP_LEVEL_DEFAULTS}
)
_HOLE_PARSERS: Final[Mapping[str, Any]] = {
    "diameter_mm": parse_length,
    "diameter_tol_mm": parse_tolerance,
    "count": parse_count,
    "kind": parse_hole_kind,
    "depth_mm": parse_length,
    "depth_tol_mm": parse_tolerance,
}
_HOLE_REQUIRED: Final[tuple[str, ...]] = ("diameter_mm", "diameter_tol_mm", "count", "kind")


def _length_list(value: object, field: str, size: int) -> list[str]:
    if not isinstance(value, list) or len(value) != size:
        raise RequirementError(field, f"must be a list of {size} decimal strings")
    return [parse_length(item, f"{field}[{index}]") for index, item in enumerate(value)]


def _hole(value: object, index: int) -> dict[str, str]:
    field = f"holes[{index}]"
    if not isinstance(value, dict):
        raise RequirementError(field, "must be an object")
    unknown = set(value) - set(_HOLE_PARSERS)
    if unknown:
        raise RequirementError(field, f"unknown fields {sorted(unknown)}")
    missing = [name for name in _HOLE_REQUIRED if name not in value]
    if missing:
        raise RequirementError(field, f"missing {missing}")
    if ("depth_mm" in value) != ("depth_tol_mm" in value):
        raise RequirementError(field, "depth_mm and depth_tol_mm go together")
    return {
        name: _HOLE_PARSERS[name](item, f"{field}.{name}") for name, item in sorted(value.items())
    }


def _reject_ambiguous_holes(holes: list[dict[str, str]]) -> None:
    """CH3-R2: two same-kind entries whose diameter windows intersect, and whose depth windows also
    intersect (or either has no depth), are ambiguous: one hole could satisfy both."""
    for i, first in enumerate(holes):
        for second in holes[i + 1 :]:
            if first["kind"] != second["kind"]:
                continue
            if not windows_overlap(
                first["diameter_mm"],
                first["diameter_tol_mm"],
                second["diameter_mm"],
                second["diameter_tol_mm"],
            ):
                continue
            if (
                "depth_mm" in first
                and "depth_mm" in second
                and not windows_overlap(
                    first["depth_mm"],
                    first["depth_tol_mm"],
                    second["depth_mm"],
                    second["depth_tol_mm"],
                )
            ):
                continue
            raise RequirementError("holes", f"ambiguous: entries {first} and {second} overlap")


def canonical_requirements(document: object) -> dict[str, Any]:
    """Parse declared requirements per field kind (spec F r3 §3) and return the canonical form.

    Defaults are materialized; ``envelope_max_mm`` stays absent when absent; holes are sorted by
    diameter value, then by their canonical JSON. Raises :class:`RequirementError`.
    """
    if not isinstance(document, dict):
        raise RequirementError("$", "requirements must be an object")
    unknown = set(document) - _TOP_LEVEL_FIELDS
    if unknown:
        raise RequirementError("$", f"unknown fields {sorted(unknown)}")
    if document.get("requirements_schema_version") != REQUIREMENTS_SCHEMA_VERSION:
        raise RequirementError(
            "requirements_schema_version", f"must be {REQUIREMENTS_SCHEMA_VERSION!r}"
        )
    merged = {**_TOP_LEVEL_DEFAULTS, **document}
    lower, upper = _length_list(merged["plausible_size_mm"], "plausible_size_mm", 2)
    hard_low, hard_high = PLAUSIBLE_HARD_LIMITS
    if not hard_low <= Decimal(lower) < Decimal(upper) <= hard_high:
        raise RequirementError("plausible_size_mm", f"need {hard_low} <= min < max <= {hard_high}")
    holes_value = merged["holes"]
    if not isinstance(holes_value, list):
        raise RequirementError("holes", "must be a list")
    holes = [_hole(item, index) for index, item in enumerate(holes_value)]
    holes.sort(key=lambda hole: (Decimal(hole["diameter_mm"]), json.dumps(hole, sort_keys=True)))
    _reject_ambiguous_holes(holes)
    canonical: dict[str, Any] = {
        "requirements_schema_version": REQUIREMENTS_SCHEMA_VERSION,
        "expected_solids": parse_count(merged["expected_solids"], "expected_solids"),
        "plausible_size_mm": [lower, upper],
        "length_tol_mm": parse_tolerance(merged["length_tol_mm"], "length_tol_mm"),
        "holes": holes,
        "holes_exhaustive": parse_bool(merged["holes_exhaustive"], "holes_exhaustive"),
    }
    if "envelope_max_mm" in document:
        canonical["envelope_max_mm"] = _length_list(
            document["envelope_max_mm"], "envelope_max_mm", 3
        )
    return canonical


# --- Facts hashing (spec §2, §4) ---------------------------------------------------------------


def _check_facts_domain(value: object, path: str = "$") -> None:
    """Facts encoding: ASCII-keyed objects, lists, and string leaves only (spec §2)."""
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key.isascii():
                raise ContractError(f"{path}: facts keys must be ASCII strings, got {key!r}")
            _check_facts_domain(item, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _check_facts_domain(item, f"{path}[{index}]")
        return
    if isinstance(value, str):
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ContractError(f"{path}: lone surrogate in a facts string")
        return
    raise ContractError(f"{path}: every facts leaf is a string, got {type(value).__name__}")


def facts_hash(facts: Mapping[str, Any]) -> str:
    """``"sha256:" + canonical_sha256(facts)`` after the facts-domain check."""
    plain = dict(facts)
    _check_facts_domain(plain)
    return "sha256:" + canonical_sha256(plain)


# --- Value types (spec §1) -----------------------------------------------------------------------

_FROZEN: Final[ConfigDict] = ConfigDict(frozen=True, extra="forbid", strict=True)


def _is_canonical_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False


class StepArtifact(BaseModel):
    """A ``DesignArtifact`` variant: one STEP file as raw bytes (spec §1). Hash = sha256(bytes)."""

    model_config = _FROZEN

    media_type: Literal["model/step"] = "model/step"
    payload: bytes = Field(min_length=1, max_length=MAX_STEP_BYTES)

    @property
    def content_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.payload).hexdigest()

    @property
    def artifact_id(self) -> str:
        return derive_id(self.content_hash)

    def reference(self) -> DesignArtifactRef:
        return DesignArtifactRef(
            media_type=self.media_type, ref=self.artifact_id, content_hash=self.content_hash
        )


class GeometryTask(BaseModel):
    """A geometry engineering task: an id plus declared requirements (canonicalized on input)."""

    model_config = _FROZEN

    task_id: str = Field(min_length=1)
    domain: Literal["geometry"] = "geometry"
    requirements: dict[str, Any]

    @field_validator("requirements", mode="before")
    @classmethod
    def _canonical(cls, value: object) -> dict[str, Any]:
        return canonical_requirements(value)


class GeometryFactsRef(BaseModel):
    """``geometry_facts`` on the wire: ``{media_type, ref, content_hash}`` (spec §4)."""

    model_config = _FROZEN

    media_type: Literal["application/vnd.velith.geometry-facts+json"]
    ref: str
    content_hash: str = Field(pattern=CONTENT_HASH_PATTERN)


class GeometryReason(str, Enum):
    """G-RULE reasons (spec §5); precedence = declaration order (the first failing one wins)."""

    PARSE_FAILED = "PARSE_FAILED"
    NO_GEOMETRY = "NO_GEOMETRY"
    UNIT_UNRECOGNIZED = "UNIT_UNRECOGNIZED"
    NOT_A_CLOSED_SOLID = "NOT_A_CLOSED_SOLID"
    SOLID_COUNT_MISMATCH = "SOLID_COUNT_MISMATCH"
    INVALID_TOPOLOGY = "INVALID_TOPOLOGY"
    UNIT_IMPLAUSIBLE = "UNIT_IMPLAUSIBLE"
    MASS_PROPERTY_DISAGREEMENT = "MASS_PROPERTY_DISAGREEMENT"
    REQUIREMENT_NOT_MET = "REQUIREMENT_NOT_MET"


class GeometryUnverifiedOutcome(BaseModel):
    """A geometry verification that licenses no claim. Never crosses the wire. ``facts`` is the
    diagnostic facts document when geometry was measured (never a claim)."""

    model_config = _FROZEN

    task_id: str = Field(min_length=1)
    verdict: VerdictStatus
    reason: GeometryReason
    facts: dict[str, Any] | None = None


# --- Identity v2 (spec §4) -----------------------------------------------------------------------


def identity_view_v2(
    verifier: VerifierIdentity, design_artifact: DesignArtifactRef, geometry_facts: GeometryFactsRef
) -> dict[str, Any]:
    """The v2 identity view: wire minus {result_id, content_hash}, plus {identity_version}."""
    return {
        "identity_version": IDENTITY_VERSION_V2,
        "verified": True,
        "verifier": {"component": verifier.component, "version": verifier.version},
        "design_artifact": {
            "media_type": design_artifact.media_type,
            "ref": design_artifact.ref,
            "content_hash": design_artifact.content_hash,
        },
        "geometry_facts": {
            "media_type": geometry_facts.media_type,
            "ref": geometry_facts.ref,
            "content_hash": geometry_facts.content_hash,
        },
    }


def facts_reference(facts: Mapping[str, Any]) -> GeometryFactsRef:
    content_hash = facts_hash(facts)
    return GeometryFactsRef(
        media_type="application/vnd.velith.geometry-facts+json",
        ref=derive_id(content_hash),
        content_hash=content_hash,
    )


def _all_conformance_met(facts: Mapping[str, Any]) -> bool:
    entries = facts.get("conformance")
    return isinstance(entries, list) and all(
        isinstance(entry, dict) and entry.get("result") == "MET" for entry in entries
    )


class _GeometryWireClaim(BaseModel):
    """The six v2 wire fields and every integrity check a consumer can perform (spec §4)."""

    model_config = ConfigDict(
        frozen=True, extra="forbid", strict=True, arbitrary_types_allowed=True
    )

    result_id: str
    content_hash: str = Field(pattern=CONTENT_HASH_PATTERN)
    verified: Literal[True]
    verifier: VerifierIdentity
    design_artifact: DesignArtifactRef
    geometry_facts: GeometryFactsRef

    @field_validator("verified", mode="before")
    @classmethod
    def _verified_is_the_boolean_true(cls, value: object) -> object:
        if value is not True:
            raise ValueError("verified must be the JSON boolean true")
        return value

    @model_validator(mode="after")
    def _identity_is_consistent(self) -> _GeometryWireClaim:
        if self.design_artifact.media_type != MEDIA_TYPE_STEP:
            raise ValueError(f"design_artifact.media_type must be {MEDIA_TYPE_STEP!r}")
        if self.verifier.component != GEOMETRY_VERIFIER_COMPONENT:
            raise ValueError(f"verifier.component must be {GEOMETRY_VERIFIER_COMPONENT!r}")
        if not _is_canonical_uuid(self.result_id):
            raise ValueError(f"result_id must be a lowercase hyphenated UUID: {self.result_id!r}")
        view = identity_view_v2(self.verifier, self.design_artifact, self.geometry_facts)
        if self.content_hash != content_hash_of(view):
            raise ValueError("content_hash does not match the recomputed v2 identity view")
        if self.result_id != derive_id(self.content_hash):
            raise ValueError("result_id is not uuid5(NS_VELITH_API, content_hash)")
        if self.design_artifact.ref != derive_id(self.design_artifact.content_hash):
            raise ValueError("design_artifact.ref is not uuid5(NS_VELITH_API, its content_hash)")
        if self.geometry_facts.ref != derive_id(self.geometry_facts.content_hash):
            raise ValueError("geometry_facts.ref is not uuid5(NS_VELITH_API, its content_hash)")
        return self

    def to_wire(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "content_hash": self.content_hash,
            "verified": True,
            "verifier": self.verifier.model_dump(mode="json"),
            "design_artifact": self.design_artifact.model_dump(mode="json"),
            "geometry_facts": self.geometry_facts.model_dump(mode="json"),
        }


def _check_facts_against_wire(claim: _GeometryWireClaim, facts: Mapping[str, Any]) -> None:
    if facts_hash(facts) != claim.geometry_facts.content_hash:
        raise ValueError("geometry_facts content_hash does not match the facts document")
    artifact = facts.get("artifact")
    if not isinstance(artifact, dict) or artifact.get("content_hash") != (
        claim.design_artifact.content_hash
    ):
        raise ValueError("facts.artifact.content_hash differs from design_artifact.content_hash")
    if facts.get("facts_schema_version") != FACTS_SCHEMA_VERSION:
        raise ValueError(f"facts_schema_version must be {FACTS_SCHEMA_VERSION!r}")
    if not _all_conformance_met(facts):
        raise ValueError("a verified claim requires every conformance entry to be MET")


class ReceivedGeometryResult(_GeometryWireClaim):
    """A bundle as received: integrity-checked, but only a claim (integrity, not authenticity)."""

    facts: dict[str, Any]

    @model_validator(mode="after")
    def _facts_match(self) -> ReceivedGeometryResult:
        _check_facts_against_wire(self, self.facts)
        return self


class GeometryEngineeringResult(_GeometryWireClaim):
    """A verified geometry result (producer side). Local only: task_id, facts, provenance."""

    task_id: str = Field(min_length=1)
    facts: dict[str, Any]
    provenance: Provenance

    @model_validator(mode="after")
    def _facts_match(self) -> GeometryEngineeringResult:
        _check_facts_against_wire(self, self.facts)
        return self

    def bundle(self) -> dict[str, Any]:
        """The only cross-layer form of a geometry result (spec §1 ``ResultBundle``)."""
        return {
            "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
            "result": self.to_wire(),
            "geometry_facts": self.facts,
        }


def geometry_result(
    task: GeometryTask,
    artifact: StepArtifact,
    facts: Mapping[str, Any],
    *,
    verifier: VerifierIdentity,
    provenance: Provenance,
) -> GeometryEngineeringResult:
    """The single producer path for a verified geometry result (derivation order, spec §4)."""
    design_ref = artifact.reference()
    facts_ref = facts_reference(facts)
    content_hash = content_hash_of(identity_view_v2(verifier, design_ref, facts_ref))
    return GeometryEngineeringResult(
        result_id=derive_id(content_hash),
        content_hash=content_hash,
        verified=True,
        verifier=verifier,
        design_artifact=design_ref,
        geometry_facts=facts_ref,
        task_id=task.task_id,
        facts=dict(facts),
        provenance=provenance,
    )


_BUNDLE_FIELDS: Final[frozenset[str]] = frozenset(
    {"bundle_schema_version", "result", "geometry_facts"}
)


def from_bundle(
    bundle: Mapping[str, Any], *, step_bytes: bytes | None = None
) -> ReceivedGeometryResult:
    """Consumer check (spec §4, steps 1-7). Raises :class:`ContractError` on any violation.

    Dispatch is by media type: only a ``model/step`` design artifact with a geometry-facts reference
    is accepted, so a v1 (software) wire object cannot be presented as a geometry result.
    """
    if set(bundle) != _BUNDLE_FIELDS:
        raise ContractError(f"bundle fields must be exactly {sorted(_BUNDLE_FIELDS)}")
    if bundle["bundle_schema_version"] != BUNDLE_SCHEMA_VERSION:
        raise ContractError(f"bundle_schema_version must be {BUNDLE_SCHEMA_VERSION!r}")
    wire, facts = bundle["result"], bundle["geometry_facts"]
    if not isinstance(wire, dict) or not isinstance(facts, dict):
        raise ContractError("bundle result and geometry_facts must be objects")
    design = wire.get("design_artifact")
    geometry = wire.get("geometry_facts")
    if not isinstance(design, dict) or design.get("media_type") != MEDIA_TYPE_STEP:
        raise ContractError(f"dispatch: design_artifact.media_type must be {MEDIA_TYPE_STEP!r}")
    if not isinstance(geometry, dict) or geometry.get("media_type") != MEDIA_TYPE_GEOMETRY_FACTS:
        raise ContractError(
            f"dispatch: geometry_facts.media_type must be {MEDIA_TYPE_GEOMETRY_FACTS!r}"
        )
    try:
        received = ReceivedGeometryResult.model_validate({**wire, "facts": facts})
    except ValidationError as exc:
        raise ContractError(f"not a valid geometry ResultBundle: {exc}") from exc
    if step_bytes is not None and (
        "sha256:" + hashlib.sha256(step_bytes).hexdigest() != received.design_artifact.content_hash
    ):
        raise ContractError("the held STEP bytes do not match design_artifact.content_hash")
    return received
