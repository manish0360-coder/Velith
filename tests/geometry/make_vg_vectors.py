"""Generate the normative VG-1..VG-12 vectors (spec F r3 §6) from the G0 implementation.

Run once, review, and commit the output; ``test_vg_vectors.py`` then pins every value:

    python -m tests.geometry.make_vg_vectors > tests/geometry/data/vg_vectors.json

Each vector is one ``G0-BENCH-01`` case: the facts hash and the result identity for verified
cases, the reason (and diagnostic facts hash, if any) for the others.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from tests.geometry._cases import CASES, payload
from velith.api.geometry_contract import (
    GeometryEngineeringResult,
    GeometryTask,
    StepArtifact,
    facts_hash,
)
from velith.geometry.verifier import GeometryVerifier


def vectors() -> dict[str, Any]:
    verifier = GeometryVerifier(diag_dir=None)
    out: dict[str, Any] = {}
    for number, (case, (stem, declared, _expected, _failing)) in enumerate(CASES.items(), start=1):
        artifact = StepArtifact(payload=payload(stem))
        outcome = verifier.evaluate(GeometryTask(task_id=case, requirements=declared), artifact)
        entry: dict[str, Any] = {"vector": f"VG-{number}", "artifact": artifact.content_hash}
        if isinstance(outcome, GeometryEngineeringResult):
            entry |= {
                "outcome": "VERIFIED",
                "facts_hash": outcome.geometry_facts.content_hash,
                "content_hash": outcome.content_hash,
                "result_id": outcome.result_id,
            }
        else:
            entry |= {
                "outcome": outcome.reason.value,
                "facts_hash": facts_hash(outcome.facts) if outcome.facts else None,
            }
        out[case] = entry
    return {"vector_set": "VG-1..VG-12", "spec": "Engineering API v0.2 F r3 §6", "vectors": out}


if __name__ == "__main__":
    json.dump(vectors(), sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")
