"""Engineering API v0 producer demonstration and record writer.

D33, API-0 C4a; API_V0_SPEC §6.1-§6.2.

Runs the real ``calc_add_bug`` task through ``velith.api.swe.SweVerifier`` (the frozen M2 sandbox,
network isolation on, three primary runs) and:

1. requires the correct T3 patch to produce a verified ``EngineeringResult`` whose identity equals
   the normative vectors (API_V0_SPEC §3.7): T3, T5a, T4-B and T5b;
2. requires a wrong patch and a malformed patch to produce ``UnverifiedOutcome(VERDICT_NOT_PASSED)``
   and to write no record;
3. writes one record per verified run to ``data/api_v0/<result_id>__<run-utc>.json`` with exclusive
   creation (never overwriting), containing exactly the wire object, ``task_id``, evidence and the
   Noetica-serialized provenance (§6.2), then re-reads it and checks it.

Run in the verifier container with ``tools/`` mounted read-only and ``data/api_v0`` mounted to a
persistent host directory (compose mounts only ``data/episodes``):

    docker compose run --rm -v "$PWD/tools:/app/tools:ro" \
        -v "$PWD/data/api_v0:/app/data/api_v0" verifier python tools/api_v0_demo.py

Fail-closed: every check prints PASS or FAIL; the exit code is non-zero if any check fails or
anything unexpected happens. It needs ``CAP_SYS_ADMIN`` for ``unshare -n`` (granted by compose).
It does not call Mini Prometheus and claims nothing about manufacturing or physical design.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from noetica.interfaces.verification import VerdictStatus
from noetica.provenance.identity import serialize_provenance

import velith
from velith.api import (
    EngineeringResult,
    EngineeringTask,
    SwePatch,
    SwePatchPayload,
    UnverifiedOutcome,
    UnverifiedReason,
    from_wire,
)
from velith.api.contract import DesignArtifact
from velith.api.swe import SweVerifier

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_ROOT = ROOT / "tests" / "fixtures"
RECORDS_DIR = ROOT / "data" / "api_v0"
TASK_ID = "calc_add_bug"

#: Settled configuration (C4a authorization).
RELEASE_VERSION = "0.1.0"
NETWORK_ISOLATION = True
FLAKE_RERUN_COUNT = 3

#: Normative vectors, copied from API_V0_SPEC §3.7 (pinned in tests/unit/test_api_vectors.py).
T3_PATCH = (
    "--- a/calculator.py\n"
    "+++ b/calculator.py\n"
    "@@ -1,3 +1,3 @@\n"
    " # mypy: ignore-errors\n"
    " def add(a: int, b: int) -> int:\n"
    "-    return a - b\n"
    "+    return a + b\n"
)
T3_HASH = "sha256:ff39e80e72505b345d649cb5254e242490db0bf3ca67bcaed50d3274e11cae95"
T5A_REF = "cdf5e4da-da47-5e52-b845-448ab5cc6bb1"
T4B_HASH = "sha256:6c2babe95dfa51f142494ef7633322d68eed8983a775faa048f1060cee0317a0"
T5B_RESULT_ID = "2ac44842-2b16-5dbe-ae75-028dd4d44a26"

#: Negative patches (API_V0_SPEC §6.1; as in tests/integration/test_spike_episode.py): a patch
#: that applies but does not fix the bug, and one whose context does not exist in the file.
WRONG_PATCH = T3_PATCH.replace("+    return a + b\n", "+    return a * b\n")
MALFORMED_PATCH = (
    "--- a/calculator.py\n"
    "+++ b/calculator.py\n"
    "@@ -1,1 +1,1 @@\n"
    "-this line is not in the real file\n"
    "+replacement\n"
)

#: §6.2: a record holds exactly the wire object and the local task/evidence/provenance fields.
RECORD_KEYS = frozenset({"wire", "task_id", "evidence", "provenance"})

failures: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    print(("PASS  " if ok else "FAIL  ") + label + ("" if ok or not detail else f" :: {detail}"))
    if not ok:
        failures.append(label)
    return ok


def artifact(patch: str) -> DesignArtifact:
    return DesignArtifact(payload=SwePatchPayload(task_id=TASK_ID, patch=SwePatch(text=patch)))


def record_files() -> set[str]:
    return {p.name for p in RECORDS_DIR.iterdir() if p.is_file()}


def evaluate(verifier: SweVerifier, patch: str) -> EngineeringResult | UnverifiedOutcome:
    return verifier.evaluate(EngineeringTask(task_id=TASK_ID), artifact(patch))


def check_configuration() -> bool:
    ok = check(
        velith.__version__ == RELEASE_VERSION,
        f"velith version is {RELEASE_VERSION}",
        velith.__version__,
    )
    ok &= check(RECORDS_DIR.is_dir(), f"records directory {RECORDS_DIR} exists")
    ok &= check(
        os.path.ismount(RECORDS_DIR),
        "records directory is a mount (records persist after the container exits)",
        "run with -v ./data/api_v0:/app/data/api_v0",
    )
    return ok


def check_negative(verifier: SweVerifier, label: str, patch: str, expected: VerdictStatus) -> None:
    before = record_files()
    outcome = evaluate(verifier, patch)
    check(
        isinstance(outcome, UnverifiedOutcome)
        and outcome.verdict is expected
        and outcome.reason is UnverifiedReason.VERDICT_NOT_PASSED,
        f"{label} -> UnverifiedOutcome({expected.value}, VERDICT_NOT_PASSED)",
        f"{outcome!r}",
    )
    check(record_files() == before, f"{label}: no record is written")


def check_verified(result: EngineeringResult | UnverifiedOutcome) -> EngineeringResult | None:
    if not check(
        isinstance(result, EngineeringResult),
        "correct T3 patch -> verified EngineeringResult",
        f"{result!r}",
    ):
        return None
    assert isinstance(result, EngineeringResult)
    evidence = result.evidence
    check(
        evidence.verdict_status is VerdictStatus.PASSED
        and evidence.flaky is False
        and evidence.secondary_passed is True
        and evidence.network_isolated is NETWORK_ISOLATION
        and evidence.flake_rerun_count == FLAKE_RERUN_COUNT,
        "evidence: PASSED, not flaky, secondary passed, isolated, 3 primary runs",
        f"{evidence!r}",
    )
    check(result.verifier.version == RELEASE_VERSION, "verifier.version is 0.1.0")
    check(result.design_artifact.content_hash == T3_HASH, "artifact content_hash == T3")
    check(result.design_artifact.ref == T5A_REF, "artifact ref == T5a")
    check(result.content_hash == T4B_HASH, "result content_hash == T4-B", result.content_hash)
    check(result.result_id == T5B_RESULT_ID, "result_id == T5b", result.result_id)
    return result


def build_record(result: EngineeringResult) -> dict[str, Any]:
    return {
        "wire": result.to_wire(),
        "task_id": result.task_id,
        "evidence": result.evidence.model_dump(mode="json"),
        "provenance": serialize_provenance(result.provenance),
    }


def write_record(result: EngineeringResult) -> Path | None:
    run_utc = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = RECORDS_DIR / f"{result.result_id}__{run_utc}.json"
    text = json.dumps(build_record(result), sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    created = False
    try:
        with path.open("x", encoding="utf-8") as handle:  # exclusive: never overwrite
            created = True
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        check(False, "record file name is new (exclusive creation)", str(path))
        return None
    except OSError as exc:
        if created:  # remove only the partial file this run created
            path.unlink(missing_ok=True)
        check(False, "record is written completely", f"{path}: {exc!r}")
        return None
    check(True, f"record written exclusively: {path.name}")
    return path


def check_record(path: Path) -> None:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    check(set(loaded) == RECORD_KEYS, "record holds exactly wire, task_id, evidence, provenance")
    received = from_wire(loaded["wire"])
    check(
        received.content_hash == T4B_HASH and received.result_id == T5B_RESULT_ID,
        "re-read record: wire passes the consumer checks and equals T4-B/T5b",
    )
    check(loaded["task_id"] == TASK_ID, "re-read record: task_id is calc_add_bug")
    check(
        set(loaded["provenance"])
        == {"source", "transform", "inputs", "attributes", "schema_version"}
        and loaded["provenance"]["inputs"] == [TASK_ID, T3_HASH],
        "re-read record: Noetica provenance form, inputs = (task_id, T3)",
    )


def check_content_identity() -> None:
    """ID-1: every record of this claim carries the identical wire object."""
    wires = []
    for path in sorted(RECORDS_DIR.glob(f"{T5B_RESULT_ID}__*.json")):
        wires.append(json.loads(path.read_text(encoding="utf-8"))["wire"])
    check(
        bool(wires) and all(w == wires[0] for w in wires),
        f"all {len(wires)} record(s) for result_id {T5B_RESULT_ID} share one wire object (ID-1)",
    )


def main() -> int:
    try:
        if check_configuration():
            with SweVerifier(
                fixtures_root=FIXTURES_ROOT,
                network_isolation=NETWORK_ISOLATION,
                flake_rerun_count=FLAKE_RERUN_COUNT,
            ) as verifier:
                check_negative(verifier, "wrong patch", WRONG_PATCH, VerdictStatus.FAILED)
                check_negative(
                    verifier, "malformed patch", MALFORMED_PATCH, VerdictStatus.PATCH_APPLY_FAILED
                )
                before = record_files()
                result = check_verified(evaluate(verifier, T3_PATCH))
            if result is not None and not failures:
                path = write_record(result)
                if path is not None:
                    check(
                        record_files() - before == {path.name},
                        "exactly one new record file",
                    )
                    check_record(path)
                    check_content_identity()
            elif result is not None:
                print("NO-WRITE  a check failed, so no record is written for this run")
    except Exception as exc:  # fail closed on anything unexpected
        traceback.print_exc()
        failures.append(f"unexpected error: {exc!r}")
    print(f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
