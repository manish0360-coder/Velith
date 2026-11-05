"""The ``G0-BENCH-01`` Tier 1 cases (frozen benchmark, HQ ``gate0/benchmark``; spec D §2).

Requirements are the declared requirements of D §2 written in the spec F r3 §3 field grammar. D §2
gives no tolerances; the hole and depth tolerances here (0.01 mm) are test inputs, well above the
1e-6 mm facts quantum and far below the smallest diameter difference in the benchmark (0.6 mm).
CR-03 declares only the envelope (``holes_exhaustive = "false"``), exactly as D §2 states it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

DATA: Final[Path] = Path(__file__).resolve().parent / "data"
PARTS: Final[Path] = DATA / "parts"


def hole(diameter: str, count: str, kind: str, **extra: str) -> dict[str, str]:
    return {
        "diameter_mm": diameter,
        "diameter_tol_mm": "0.01",
        "count": count,
        "kind": kind,
        **extra,
    }


def requirements(**fields: Any) -> dict[str, Any]:
    return {"requirements_schema_version": "0.2.0", **fields}


#: case -> (file stem, declared requirements, expected reason or "VERIFIED", failing entry ids)
CASES: Final[dict[str, tuple[str, dict[str, Any], str, tuple[str, ...]]]] = {
    "BP-01": (
        "BP-01",
        requirements(envelope_max_mm=["100", "60", "10"], holes=[hole("6.6", "4", "through")]),
        "VERIFIED",
        (),
    ),
    "BP-02": (
        "BP-02",
        requirements(
            envelope_max_mm=["80", "50", "30"],
            holes=[
                hole("8", "2", "blind", depth_mm="15", depth_tol_mm="0.01"),
                hole("10", "1", "through"),
            ],
        ),
        "VERIFIED",
        (),
    ),
    "BP-03": (
        "BP-03",
        requirements(envelope_max_mm=["120", "80", "12"], holes=[hole("8", "2", "through")]),
        "VERIFIED",
        (),
    ),
    "BP-04": (
        "BP-04",
        requirements(
            envelope_max_mm=["80", "50", "50"],
            holes=[hole("6.6", "2", "through"), hole("8.4", "1", "through")],
        ),
        "VERIFIED",
        (),
    ),
    "CR-01": (
        "BP-01",
        requirements(envelope_max_mm=["100", "60", "10"], holes=[hole("6.0", "4", "through")]),
        "REQUIREMENT_NOT_MET",
        ("holes[0]",),
    ),
    "CR-02": (
        "CR-02-GEOM",
        requirements(envelope_max_mm=["100", "60", "10"], holes=[hole("6.6", "4", "through")]),
        "REQUIREMENT_NOT_MET",
        ("holes[0]", "holes_exhaustive"),
    ),
    "CR-03": (
        "BP-04",
        requirements(envelope_max_mm=["80", "50", "45"], holes_exhaustive="false"),
        "REQUIREMENT_NOT_MET",
        ("envelope",),
    ),
    "NC-01": ("NC-01", requirements(), "NOT_A_CLOSED_SOLID", ()),
    "NC-02": ("NC-02", requirements(), "SOLID_COUNT_MISMATCH", ()),
    "NC-03": ("NC-03", requirements(), "PARSE_FAILED", ()),
    "NC-04": ("NC-04", requirements(), "UNIT_IMPLAUSIBLE", ()),
    "NC-05": ("NC-05", requirements(), "NO_GEOMETRY", ()),
}


def payload(stem: str) -> bytes:
    return (PARTS / f"{stem}.step").read_bytes()
