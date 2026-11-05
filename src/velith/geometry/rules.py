"""G0 rule evaluation: quantization q-1, facts assembly, G-RULE precedence, conformance (spec F r3).

Pure Python over a measured-facts structure (spec §6): no ``OCP`` import, no I/O. The child worker
(``velith.geometry._kernel``) produces a :class:`RawMeasurement`; the parent validates it, quantizes
it into a ``GeometryFacts`` document and applies the verification rule here. The worker reuses
:func:`cross_check_required` so the mesh cross-check is gated by the same code as rule 7.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, Inexact, localcontext
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from velith.api.geometry_contract import (
    ANNOTATION_SCAN_RULE,
    BINDING,
    BINDING_VERSION,
    FACTS_SCHEMA_VERSION,
    IDENTITY_PLATFORM,
    KERNEL,
    KERNEL_VERSION,
    MEDIA_TYPE_STEP,
    PLATFORM_POLICY,
    QUANTIZATION_RULE,
    GeometryReason,
)

#: q-1 fraction digits per quantity kind (spec §2).
QUANTA: Final[Mapping[str, int]] = {"length_mm": 6, "area_mm2": 4, "volume_mm3": 3, "direction": 6}
#: Mesh cross-check parameters (spec §2 ``measurement.cross_check``; rule 8 threshold).
CROSS_CHECK_LINEAR_DEFLECTION_MM: Final[float] = 0.001
CROSS_CHECK_ANGULAR_DEFLECTION_RAD: Final[float] = 0.05
CROSS_CHECK_MAX_REL_DIFF: Final[Decimal] = Decimal("0.0001")
#: Length-unit names (as reported by the STEP reader) that G0 recognizes (rule 3).
RECOGNIZED_LENGTH_UNITS: Final[frozenset[str]] = frozenset(
    {"millimetre", "centimetre", "metre", "micrometre", "inch", "foot"}
)


def quantize(value: float, kind: str) -> str:
    """Rule q-1: correctly rounded fixed-point text; an all-zero result is never signed."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("quantize: number required")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("quantize: non-finite value")
    text = format(number, f".{QUANTA[kind]}f")
    if text.startswith("-") and set(text[1:]) <= {"0", "."}:
        text = text[1:]
    return text


def within(measured: str, nominal: str, tolerance: str) -> bool:
    """``|measured - nominal| <= tolerance`` in exact decimal arithmetic (never binary floats)."""
    with localcontext() as ctx:
        ctx.prec = len(measured) + len(nominal) + len(tolerance) + 2
        ctx.traps[Inexact] = True
        return abs(Decimal(measured) - Decimal(nominal)) <= Decimal(tolerance)


def at_most(measured: str, maximum: str, tolerance: str) -> bool:
    """``measured <= maximum + tolerance`` in exact decimal arithmetic (envelope rule)."""
    with localcontext() as ctx:
        ctx.prec = len(measured) + len(maximum) + len(tolerance) + 2
        ctx.traps[Inexact] = True
        return Decimal(measured) <= Decimal(maximum) + Decimal(tolerance)


# --- The worker's output document (validated before use; spec §6) ------------------------------

_STRICT: Final[ConfigDict] = ConfigDict(frozen=True, extra="forbid", strict=True)
Vector = tuple[float, float, float]


class RawSegment(BaseModel):
    model_config = _STRICT
    diameter_mm: float = Field(gt=0)
    depth_mm: float = Field(ge=0)


class RawHole(BaseModel):
    """One maximal coaxial stack of concave full-revolution cylindrical faces (spec §2)."""

    model_config = _STRICT
    axis_dir: Vector
    axis_point_mm: Vector
    through: bool
    segments: tuple[RawSegment, ...] = Field(min_length=1)


class RawFaces(BaseModel):
    model_config = _STRICT
    plane: int = Field(ge=0)
    cylinder: int = Field(ge=0)
    cone: int = Field(ge=0)
    other: int = Field(ge=0)


class RawSolid(BaseModel):
    model_config = _STRICT
    valid: bool
    closed: bool
    volume_mm3: float
    area_mm2: float
    genus: int
    bbox_min: Vector
    bbox_max: Vector
    faces: RawFaces
    holes: tuple[RawHole, ...]
    non_hole_cylindrical_faces: int = Field(ge=0)


class RawShape(BaseModel):
    model_config = _STRICT
    solids: int = Field(ge=0)
    shells: int = Field(ge=0)
    faces: int = Field(ge=0)


class RawCrossCheck(BaseModel):
    model_config = _STRICT
    performed: bool
    max_rel_diff: float | None = None


class RawMeasurement(BaseModel):
    """The worker protocol document ``g0-child-1``. Floats are the kernel's exact doubles."""

    model_config = _STRICT
    protocol: Literal["g0-child-1"]
    status: Literal["PARSE_FAILED", "NO_GEOMETRY", "MEASURED"]
    length_units: tuple[str, ...] = ()
    shape: RawShape | None = None
    solids: tuple[RawSolid, ...] = ()
    cross_check: RawCrossCheck = RawCrossCheck(performed=False)


# --- Facts assembly (spec §2) ------------------------------------------------------------------


def _q3(values: Sequence[float], kind: str) -> list[str]:
    return [quantize(value, kind) for value in values]


def _canonical_direction(direction: Vector) -> tuple[Vector, bool]:
    """Sign canonicalization: the first component that is nonzero after quantization is positive."""
    for component in direction:
        text = quantize(component, "direction")
        if text != "0.000000":
            if text.startswith("-"):
                return (-direction[0], -direction[1], -direction[2]), True
            return direction, False
    return direction, False


def _hole_facts(hole: RawHole) -> dict[str, Any]:
    direction, flipped = _canonical_direction(hole.axis_dir)
    segments = list(reversed(hole.segments)) if flipped else list(hole.segments)
    return {
        "axis_dir": _q3(direction, "direction"),
        "axis_point_mm": _q3(hole.axis_point_mm, "length_mm"),
        "kind": "through" if hole.through else "blind",
        "segments": [
            {
                "diameter_mm": quantize(segment.diameter_mm, "length_mm"),
                "depth_mm": quantize(segment.depth_mm, "length_mm"),
            }
            for segment in segments
        ],
    }


def _hole_sort_key(hole: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        [Decimal(x) for x in hole["axis_dir"]],
        [Decimal(x) for x in hole["axis_point_mm"]],
        hole["kind"],
        [(Decimal(s["diameter_mm"]), Decimal(s["depth_mm"])) for s in hole["segments"]],
    )


def bbox_size(solid: RawSolid) -> list[str]:
    return _q3(
        [hi - lo for lo, hi in zip(solid.bbox_min, solid.bbox_max, strict=True)], "length_mm"
    )


def _solid_facts(index: int, solid: RawSolid) -> dict[str, Any]:
    holes = sorted((_hole_facts(hole) for hole in solid.holes), key=_hole_sort_key)
    return {
        "index": str(index),
        "valid": "true" if solid.valid else "false",
        "closed": "true" if solid.closed else "false",
        "volume_mm3": quantize(solid.volume_mm3, "volume_mm3"),
        "area_mm2": quantize(solid.area_mm2, "area_mm2"),
        "genus": str(solid.genus),
        "bbox_mm": {"min": _q3(solid.bbox_min, "length_mm"), "size": bbox_size(solid)},
        "faces": {
            "plane": str(solid.faces.plane),
            "cylinder": str(solid.faces.cylinder),
            "cone": str(solid.faces.cone),
            "other": str(solid.faces.other),
        },
        "holes": holes,
        "non_hole_cylindrical_faces": str(solid.non_hole_cylindrical_faces),
    }


def measurement_block(length_units: Sequence[str]) -> dict[str, Any]:
    return {
        "kernel": KERNEL,
        "kernel_version": KERNEL_VERSION,
        "binding": BINDING,
        "binding_version": BINDING_VERSION,
        "quantization_rule": QUANTIZATION_RULE,
        "annotation_scan_rule": ANNOTATION_SCAN_RULE,
        "platform": IDENTITY_PLATFORM,
        "platform_policy": PLATFORM_POLICY,
        "length_unit": "mm",
        "source_length_units": list(length_units),
        "quantization": {"length_mm": "0.000001", "area_mm2": "0.0001", "volume_mm3": "0.001"},
        "cross_check": {
            "method": "tessellation_volume",
            "linear_deflection_mm": "0.001",
            "angular_deflection_rad": "0.05",
            "max_rel_diff": "0.0001",
        },
    }


# --- G-RULE (spec §5) ----------------------------------------------------------------------------


def units_recognized(raw: RawMeasurement) -> bool:
    return bool(raw.length_units) and all(
        unit in RECOGNIZED_LENGTH_UNITS for unit in raw.length_units
    )


def plausible(raw: RawMeasurement, requirements: Mapping[str, Any]) -> bool:
    """Rule 7: every quantized bbox dimension of every solid lies in ``plausible_size_mm``."""
    low, high = (Decimal(x) for x in requirements["plausible_size_mm"])
    return all(low <= Decimal(size) <= high for solid in raw.solids for size in bbox_size(solid))


def _first_reason_before_cross_check(
    raw: RawMeasurement, requirements: Mapping[str, Any]
) -> GeometryReason | None:
    """Rules 1-7, in order."""
    if raw.status == "PARSE_FAILED":
        return GeometryReason.PARSE_FAILED
    if raw.status == "NO_GEOMETRY" or raw.shape is None:
        return GeometryReason.NO_GEOMETRY
    if not units_recognized(raw):
        return GeometryReason.UNIT_UNRECOGNIZED
    if not raw.solids and (raw.shape.shells > 0 or raw.shape.faces > 0):
        return GeometryReason.NOT_A_CLOSED_SOLID
    if len(raw.solids) != int(requirements["expected_solids"]):
        return GeometryReason.SOLID_COUNT_MISMATCH
    if any(not (solid.valid and solid.closed) for solid in raw.solids):
        return GeometryReason.INVALID_TOPOLOGY
    if not plausible(raw, requirements):
        return GeometryReason.UNIT_IMPLAUSIBLE
    return None


def cross_check_required(raw: RawMeasurement, requirements: Mapping[str, Any]) -> bool:
    """The worker meshes only when rules 1-7 pass: meshing an implausibly scaled part was
    OOM-killed at Gate 0, which is why rule 7 precedes rule 8 (spec §5)."""
    return _first_reason_before_cross_check(raw, requirements) is None


def _union_size(solids: Sequence[Mapping[str, Any]]) -> list[str]:
    sizes: list[str] = []
    for axis in range(3):
        lows = [Decimal(solid["bbox_mm"]["min"][axis]) for solid in solids]
        highs = [
            Decimal(solid["bbox_mm"]["min"][axis]) + Decimal(solid["bbox_mm"]["size"][axis])
            for solid in solids
        ]
        sizes.append(format(max(highs) - min(lows), "f"))
    return sizes


def conformance(
    solids: Sequence[Mapping[str, Any]], requirements: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Conformance entries (spec §3 matching), in canonical order."""
    entries: list[dict[str, Any]] = [
        {
            "id": "solids",
            "result": "MET" if len(solids) == int(requirements["expected_solids"]) else "NOT_MET",
            "measured_count": str(len(solids)),
        }
    ]
    if "envelope_max_mm" in requirements:
        size = _union_size(solids)
        met = all(
            at_most(measured, maximum, requirements["length_tol_mm"])
            for measured, maximum in zip(size, requirements["envelope_max_mm"], strict=True)
        )
        entries.append(
            {"id": "envelope", "result": "MET" if met else "NOT_MET", "measured_mm": size}
        )
    stacks = [hole for solid in solids for hole in solid["holes"]]
    single = [hole for hole in stacks if len(hole["segments"]) == 1]
    for index, declared in enumerate(requirements["holes"]):
        matches = 0
        for hole in single:
            segment = hole["segments"][0]
            if hole["kind"] != declared["kind"]:
                continue
            if not within(
                segment["diameter_mm"], declared["diameter_mm"], declared["diameter_tol_mm"]
            ):
                continue
            if "depth_mm" in declared and not within(
                segment["depth_mm"], declared["depth_mm"], declared["depth_tol_mm"]
            ):
                continue
            matches += 1
        entries.append(
            {
                "id": f"holes[{index}]",
                "result": "MET" if matches == int(declared["count"]) else "NOT_MET",
                "measured_count": str(matches),
            }
        )
    if requirements["holes_exhaustive"] == "true":
        declared_total = sum(int(declared["count"]) for declared in requirements["holes"])
        entries.append(
            {
                "id": "holes_exhaustive",
                "result": "MET" if len(stacks) == declared_total else "NOT_MET",
                "measured_count": str(len(stacks)),
            }
        )
    return entries


@dataclass(frozen=True)
class Evaluation:
    """The G-RULE outcome: ``reason is None`` means verified. ``facts`` is ``None`` only when no
    geometry was measured (rules 1-2)."""

    reason: GeometryReason | None
    facts: dict[str, Any] | None


class WorkerProtocolError(ValueError):
    """The worker's document is internally inconsistent (classified ``PROTOCOL_ERROR``)."""


def evaluate(
    raw: RawMeasurement,
    requirements: Mapping[str, Any],
    *,
    artifact_content_hash: str,
    annotations: Mapping[str, str],
) -> Evaluation:
    """Apply G-RULE (spec §5) and assemble the facts document (spec §2)."""
    reason = _first_reason_before_cross_check(raw, requirements)
    if reason in (GeometryReason.PARSE_FAILED, GeometryReason.NO_GEOMETRY):
        return Evaluation(reason=reason, facts=None)
    solids = [_solid_facts(index, solid) for index, solid in enumerate(raw.solids)]
    facts: dict[str, Any] = {
        "facts_schema_version": FACTS_SCHEMA_VERSION,
        "artifact": {"media_type": MEDIA_TYPE_STEP, "content_hash": artifact_content_hash},
        "measurement": measurement_block(raw.length_units),
        "solids": solids,
        "annotations": dict(annotations),
        "requirements": dict(requirements),
        "conformance": [],
    }
    if reason is not None:
        return Evaluation(reason=reason, facts=facts)
    if not raw.cross_check.performed or raw.cross_check.max_rel_diff is None:
        raise WorkerProtocolError("rules 1-7 passed but the worker performed no cross-check")
    if not math.isfinite(raw.cross_check.max_rel_diff):
        raise WorkerProtocolError("non-finite cross-check value")
    if Decimal(repr(raw.cross_check.max_rel_diff)) > CROSS_CHECK_MAX_REL_DIFF:
        return Evaluation(reason=GeometryReason.MASS_PROPERTY_DISAGREEMENT, facts=facts)
    facts["conformance"] = conformance(solids, requirements)
    if any(entry["result"] != "MET" for entry in facts["conformance"]):
        return Evaluation(reason=GeometryReason.REQUIREMENT_NOT_MET, facts=facts)
    return Evaluation(reason=None, facts=facts)
