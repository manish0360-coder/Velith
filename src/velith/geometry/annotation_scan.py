"""Annotation disclosure, rule a-1 (D34 r2 item 3; spec F r3 §2). Pure Python; nothing is evaluated.

A lexical count of PMI / annotation entity-type names in the ``DATA`` section of an ISO 10303-21
file, after string literals and comments are removed (so names inside them are never counted).
Each name occurrence counts once, including each name inside a complex instance. The counts are
disclosed in ``GeometryFacts.annotations`` and are never used in ``verified``, conformance or
requirements.
"""

from __future__ import annotations

import re
from typing import Final

_STRING: Final[re.Pattern[str]] = re.compile(r"'(?:[^']|'')*'")
_COMMENT: Final[re.Pattern[str]] = re.compile(r"/\*.*?\*/", re.S)
_NAME: Final[re.Pattern[str]] = re.compile(r"(?<![A-Z0-9_#])([A-Z][A-Z0-9_]*)\s*\(")
_DIMENSIONAL: Final[frozenset[str]] = frozenset(
    {
        "DIMENSIONAL_SIZE",
        "DIMENSIONAL_LOCATION",
        "ANGULAR_SIZE",
        "ANGULAR_LOCATION",
        "DIMENSIONAL_SIZE_WITH_PATH",
        "DIMENSIONAL_LOCATION_WITH_PATH",
        "DIMENSIONAL_CHARACTERISTIC_REPRESENTATION",
    }
)


def category(name: str) -> str | None:
    if name in _DIMENSIONAL:
        return "dimensional"
    if (
        name == "GEOMETRIC_TOLERANCE"
        or name.startswith("GEOMETRIC_TOLERANCE_")
        or name.endswith("_TOLERANCE")
    ):
        return "tolerance"
    if name.startswith(("DATUM", "PLACED_DATUM")):
        return "datum"
    if name == "DRAUGHTING_CALLOUT" or name.startswith(("ANNOTATION_", "TESSELLATED_ANNOTATION")):
        return "presentation"
    return None


def scan(raw: bytes) -> dict[str, str]:
    """Return ``{dimensional, tolerance, datum, presentation, evaluated="false"}`` as strings."""
    text = raw.decode("utf-8", errors="replace").upper()
    start = text.find("DATA;")
    data = text[start + 5 :] if start >= 0 else ""
    data = _COMMENT.sub(" ", _STRING.sub("''", data))
    counts = {"dimensional": 0, "tolerance": 0, "datum": 0, "presentation": 0}
    for match in _NAME.finditer(data):
        found = category(match.group(1))
        if found is not None:
            counts[found] += 1
    return {key: str(value) for key, value in counts.items()} | {"evaluated": "false"}
