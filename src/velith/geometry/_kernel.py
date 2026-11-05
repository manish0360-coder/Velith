"""G0 measurement worker: the only module that imports ``OCP`` (spec F r3 §6-§7).

Run only as a child process by :class:`velith.geometry.verifier.GeometryVerifier`::

    python -I -m velith.geometry._kernel LIMITS_JSON STEP_PATH OUT_PATH REQUIREMENTS_JSON

Bootstrap order: resource limits are applied first, then ``OCP`` is imported (lazily, inside the
measuring functions), then the file is read and measured. The worker writes exactly one JSON
document (protocol ``g0-child-1``, :class:`velith.geometry.rules.RawMeasurement`) to ``OUT_PATH``
and exits 0. Any kernel fault ends the process abnormally; a ``MemoryError`` exits with the
reserved code ``EXIT_MEMORY``. The parent never trusts this process for anything but the
document, which it validates before use; abnormal exits produce no result (G-ABEXIT).

Measurement definitions (spec §2): validity is ``BRepCheck_Analyzer.IsValid()``; closed means every
shell of the solid is closed; genus comes from Euler-Poincare ``V - E + F - R = 2(S - G)`` with R
the inner wires; the bounding box is exact (``BRepBndLib.AddOptimal``, no triangulation, no shape
tolerance); a hole is a maximal coaxial stack of concave cylindrical faces covering a full 2*pi.
"""

from __future__ import annotations

import json
import math
import os
import resource
import sys
from typing import Any

from velith.geometry._protocol import EXIT_MEMORY, PROTOCOL_TAG

_TWO_PI = 2.0 * math.pi
_ANGLE_TOLERANCE = 1e-9  # rad: full-revolution coverage (spec §2)
_RADIUS_RELATIVE_TOLERANCE = 1e-9  # same radius per segment (spec §2)
_AXIS_DIGITS = 9  # direction grouping
_FOOT_DIGITS = 6  # axis foot-point grouping, mm
_TOUCH_MM = 1e-7  # segments that touch along the axis belong to one stack
_THROUGH_PROBE_MM = 0.01  # probe distance beyond each stack end (spec §2)
_CLASSIFIER_TOLERANCE = 1e-7


def _apply_limits(limits: dict[str, int]) -> None:
    resource.setrlimit(resource.RLIMIT_AS, (limits["address_space_bytes"],) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (limits["cpu_soft_s"], limits["cpu_hard_s"]))
    resource.setrlimit(resource.RLIMIT_FSIZE, (limits["output_bytes"],) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _finite(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("non-finite kernel value (kernel fault)")
    return float(value)


def _count(shape: Any, kind: Any) -> int:
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as ShapeMap
    from OCP.TopExp import TopExp

    shapes = ShapeMap()
    TopExp.MapShapes_s(shape, kind, shapes)
    return int(shapes.Extent())


def _unique(shape: Any, kind: Any) -> list[Any]:
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as ShapeMap
    from OCP.TopExp import TopExp

    shapes = ShapeMap()
    TopExp.MapShapes_s(shape, kind, shapes)
    return [shapes.FindKey(index) for index in range(1, shapes.Extent() + 1)]


def _classify(solid: Any, x: float, y: float, z: float) -> Any:
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt

    return BRepClass3d_SolidClassifier(solid, gp_Pnt(x, y, z), _CLASSIFIER_TOLERANCE).State()


def _cylinder_records(solid: Any) -> tuple[list[dict[str, Any]], int]:
    """One record per cylindrical face: axis line, radius, axial interval, coverage, concavity."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    from OCP.TopAbs import TopAbs_FACE, TopAbs_OUT
    from OCP.TopoDS import TopoDS

    records: list[dict[str, Any]] = []
    cylinders = 0
    for face_shape in _unique(solid, TopAbs_FACE):
        surface = BRepAdaptor_Surface(TopoDS.Face(face_shape))
        if surface.GetType() != GeomAbs_Cylinder:
            continue
        cylinders += 1
        cylinder = surface.Cylinder()
        radius = _finite(cylinder.Radius())
        axis = cylinder.Axis()
        d, o = axis.Direction(), axis.Location()
        u0, u1 = surface.FirstUParameter(), surface.LastUParameter()
        v0, v1 = surface.FirstVParameter(), surface.LastVParameter()
        um, vm = (u0 + u1) / 2.0, (v0 + v1) / 2.0
        point = surface.Value(um, vm)
        on_axis = (o.X() + d.X() * vm, o.Y() + d.Y() * vm, o.Z() + d.Z() * vm)
        step = 0.5 * min(radius, 1.0) / radius  # 0.5 * min(r, 1 mm) toward the axis
        probe = (
            point.X() + (on_axis[0] - point.X()) * step,
            point.Y() + (on_axis[1] - point.Y()) * step,
            point.Z() + (on_axis[2] - point.Z()) * step,
        )
        concave = _classify(solid, *probe) == TopAbs_OUT
        direction = (d.X(), d.Y(), d.Z())
        sign = 1.0 if direction > (0.0, 0.0, 0.0) else -1.0
        dx, dy, dz = (sign * c for c in direction)
        offset = o.X() * dx + o.Y() * dy + o.Z() * dz
        foot = (o.X() - offset * dx, o.Y() - offset * dy, o.Z() - offset * dz)
        low, high = sorted((sign * v0 + offset, sign * v1 + offset))
        records.append(
            {
                "axis_key": (
                    tuple(round(c, _AXIS_DIGITS) for c in (dx, dy, dz)),
                    tuple(round(c, _FOOT_DIGITS) for c in foot),
                ),
                "direction": (_finite(dx), _finite(dy), _finite(dz)),
                "foot": tuple(_finite(c) for c in foot),
                "radius": radius,
                "low": _finite(low),
                "high": _finite(high),
                "coverage": u1 - u0,
                "concave": concave,
            }
        )
    return records, cylinders


def _cluster_radii(records: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    clusters: list[list[dict[str, Any]]] = []
    for record in sorted(records, key=lambda item: item["radius"]):
        if clusters:
            reference = clusters[-1][0]["radius"]
            if abs(record["radius"] - reference) <= _RADIUS_RELATIVE_TOLERANCE * max(
                record["radius"], reference
            ):
                clusters[-1].append(record)
                continue
        clusters.append([record])
    return clusters


def _segments(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Full-revolution concave segments on one axis line; returns (segments, faces used)."""
    segments: list[dict[str, Any]] = []
    used = 0
    for cluster in _cluster_radii(records):
        by_interval: dict[tuple[float, float], list[dict[str, Any]]] = {}
        for record in cluster:
            key = (round(record["low"], 7), round(record["high"], 7))
            by_interval.setdefault(key, []).append(record)
        pieces = []
        for faces in by_interval.values():
            coverage = sum(face["coverage"] for face in faces)
            if (
                all(face["concave"] for face in faces)
                and abs(coverage - _TWO_PI) <= _ANGLE_TOLERANCE
            ):
                pieces.append(
                    {
                        "radius": faces[0]["radius"],
                        "low": min(face["low"] for face in faces),
                        "high": max(face["high"] for face in faces),
                        "faces": len(faces),
                    }
                )
        pieces.sort(key=lambda piece: piece["low"])
        merged: list[dict[str, Any]] = []
        for piece in pieces:  # same radius, touching along the axis (e.g. split by a cross hole)
            if merged and abs(piece["low"] - merged[-1]["high"]) <= _TOUCH_MM:
                merged[-1]["high"] = max(merged[-1]["high"], piece["high"])
                merged[-1]["faces"] += piece["faces"]
            else:
                merged.append(dict(piece))
        for piece in merged:
            used += piece["faces"]
        segments.extend(merged)
    return segments, used


def _holes(solid: Any) -> tuple[list[dict[str, Any]], int]:
    from OCP.TopAbs import TopAbs_OUT

    records, cylinder_faces = _cylinder_records(solid)
    by_axis: dict[Any, list[dict[str, Any]]] = {}
    for record in records:
        by_axis.setdefault(record["axis_key"], []).append(record)
    holes: list[dict[str, Any]] = []
    used_faces = 0
    for axis_records in by_axis.values():
        segments, used = _segments(axis_records)
        used_faces += used
        segments.sort(key=lambda segment: segment["low"])
        stacks: list[list[dict[str, Any]]] = []
        for segment in segments:
            if stacks and abs(segment["low"] - stacks[-1][-1]["high"]) <= _TOUCH_MM:
                stacks[-1].append(segment)
            else:
                stacks.append([segment])
        dx, dy, dz = axis_records[0]["direction"]
        fx, fy, fz = axis_records[0]["foot"]
        for stack in stacks:
            low, high = stack[0]["low"], stack[-1]["high"]

            through = all(
                _classify(solid, fx + dx * t, fy + dy * t, fz + dz * t) == TopAbs_OUT
                for t in (low - _THROUGH_PROBE_MM, high + _THROUGH_PROBE_MM)
            )
            holes.append(
                {
                    "axis_dir": [dx, dy, dz],
                    "axis_point_mm": [fx, fy, fz],
                    "through": through,
                    "segments": [
                        {
                            "diameter_mm": _finite(2.0 * segment["radius"]),
                            "depth_mm": _finite(segment["high"] - segment["low"]),
                        }
                        for segment in stack
                    ],
                }
            )
    return holes, cylinder_faces - used_faces


def _measure_solid(solid: Any) -> dict[str, Any]:
    from OCP.Bnd import Bnd_Box
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_VERTEX, TopAbs_WIRE
    from OCP.TopoDS import TopoDS

    volume = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, volume)
    area = GProp_GProps()
    BRepGProp.SurfaceProperties_s(solid, area)
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(solid, box, False, False)
    low, high = box.CornerMin(), box.CornerMax()
    shells = _unique(solid, TopAbs_SHELL)
    vertices, edges = _count(solid, TopAbs_VERTEX), _count(solid, TopAbs_EDGE)
    faces, wires = _count(solid, TopAbs_FACE), _count(solid, TopAbs_WIRE)
    inner_wires = wires - faces
    euler = vertices - edges + faces - inner_wires
    face_types = {"plane": 0, "cylinder": 0, "cone": 0, "other": 0}
    for face in _unique(solid, TopAbs_FACE):
        kind = BRepAdaptor_Surface(TopoDS.Face(face)).GetType()
        name = {GeomAbs_Plane: "plane", GeomAbs_Cylinder: "cylinder", GeomAbs_Cone: "cone"}.get(
            kind, "other"
        )
        face_types[name] += 1
    holes, non_hole = _holes(solid)
    return {
        "valid": bool(BRepCheck_Analyzer(solid).IsValid()),
        "closed": bool(shells) and all(bool(BRep_Tool.IsClosed_s(shell)) for shell in shells),
        "volume_mm3": _finite(volume.Mass()),
        "area_mm2": _finite(area.Mass()),
        "genus": (2 * len(shells) - euler) // 2,
        "bbox_min": [_finite(low.X()), _finite(low.Y()), _finite(low.Z())],
        "bbox_max": [_finite(high.X()), _finite(high.Y()), _finite(high.Z())],
        "faces": face_types,
        "holes": holes,
        "non_hole_cylindrical_faces": non_hole,
    }


def _mesh_volume(solid: Any) -> float:
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    total = 0.0
    for face_shape in _unique(solid, TopAbs_FACE):
        face = TopoDS.Face(face_shape)
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        if triangulation is None:
            raise RuntimeError("tessellation produced no triangulation (kernel fault)")
        transform = location.Transformation()
        reversed_face = face.Orientation() == TopAbs_REVERSED
        for index in range(1, triangulation.NbTriangles() + 1):
            a, b, c = triangulation.Triangle(index).Get()
            if reversed_face:
                b, c = c, b
            p = [triangulation.Node(k).Transformed(transform) for k in (a, b, c)]
            total += (
                p[0].X() * (p[1].Y() * p[2].Z() - p[1].Z() * p[2].Y())
                - p[0].Y() * (p[1].X() * p[2].Z() - p[1].Z() * p[2].X())
                + p[0].Z() * (p[1].X() * p[2].Y() - p[1].Y() * p[2].X())
            ) / 6.0
    return _finite(total)


def measure(path: str, requirements: dict[str, Any]) -> dict[str, Any]:
    """Read and measure one STEP file; return the ``g0-child-1`` document."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.collections import Sequence_TCollection_AsciiString as AsciiSequence
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID

    from velith.geometry import rules

    reader = STEPControl_Reader()
    if reader.ReadFile(path) != IFSelect_RetDone:
        return {"protocol": PROTOCOL_TAG, "status": "PARSE_FAILED"}
    length, angle, solid_angle = AsciiSequence(), AsciiSequence(), AsciiSequence()
    reader.FileUnits(length, angle, solid_angle)
    units = [str(length.Value(i).ToCString()) for i in range(1, length.Length() + 1)]
    try:
        transferred = reader.TransferRoots()
    except Exception:  # transfer raising is a parse failure (spec §5 rule 1)
        return {"protocol": PROTOCOL_TAG, "status": "PARSE_FAILED"}
    if transferred == 0 or reader.NbShapes() == 0:
        return {"protocol": PROTOCOL_TAG, "status": "NO_GEOMETRY", "length_units": units}
    shape = reader.OneShape()
    if shape.IsNull():
        return {"protocol": PROTOCOL_TAG, "status": "NO_GEOMETRY", "length_units": units}
    solids = _unique(shape, TopAbs_SOLID)
    document: dict[str, Any] = {
        "protocol": PROTOCOL_TAG,
        "status": "MEASURED",
        "length_units": units,
        "shape": {
            "solids": len(solids),
            "shells": _count(shape, TopAbs_SHELL),
            "faces": _count(shape, TopAbs_FACE),
        },
        "solids": [_measure_solid(solid) for solid in solids],
        "cross_check": {"performed": False, "max_rel_diff": None},
    }
    measured = rules.RawMeasurement.model_validate_json(json.dumps(document, allow_nan=False))
    if rules.cross_check_required(measured, requirements):
        BRepMesh_IncrementalMesh(
            shape,
            rules.CROSS_CHECK_LINEAR_DEFLECTION_MM,
            False,
            rules.CROSS_CHECK_ANGULAR_DEFLECTION_RAD,
            True,
        )
        worst = 0.0
        for solid, facts in zip(solids, document["solids"], strict=True):
            exact = facts["volume_mm3"]
            worst = max(worst, abs(_mesh_volume(solid) - exact) / abs(exact))
        document["cross_check"] = {"performed": True, "max_rel_diff": _finite(worst)}
    return document


def main(argv: list[str]) -> int:
    limits = json.loads(argv[0])
    _apply_limits(limits)  # before OCP is imported
    step_path, out_path = argv[1], argv[2]
    requirements = json.loads(argv[3])
    document = measure(step_path, requirements)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, allow_nan=False, sort_keys=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except MemoryError:
        os._exit(EXIT_MEMORY)
