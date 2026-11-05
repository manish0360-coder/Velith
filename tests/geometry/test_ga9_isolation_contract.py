"""GA9: the isolation contract (spec F r3 §6; CH3-W1), against the production parent.

Every abnormal worker exit is classified from structured parent-side observations only, produces no
result and no outcome (``GeometryExecutionError``), leaves the parent alive, and writes one bounded,
write-once diagnostic record. The 14 cases are the r3 reference-harness cases: two normal reads by
the production worker, two real OCCT meshing faults on NC-04, and ten scripted failing workers
(``hostile_child.py``), including stderr text that tries to steer the classification.
"""

from __future__ import annotations

import inspect
import json
import os
import signal
import sys
from pathlib import Path

import pytest

from tests.geometry._cases import CASES, payload
from velith.api.geometry_contract import (
    GeometryEngineeringResult,
    GeometryTask,
    GeometryUnverifiedOutcome,
    StepArtifact,
)
from velith.geometry.verifier import (
    STDERR_TAIL_BYTES,
    GeometryExecutionError,
    GeometryVerifier,
    WorkerLimits,
    classify,
)

HOSTILE = str(Path(__file__).resolve().parent / "hostile_child.py")
#: Short limits so the suite stays fast (the r3 harness used the same).
FAST = WorkerLimits(cpu_soft_s=5, cpu_hard_s=7, wall_timeout_s=10.0)
LONG_CPU = WorkerLimits(cpu_soft_s=120, cpu_hard_s=125, wall_timeout_s=150.0)
TASK = GeometryTask(task_id="ga9", requirements={"requirements_schema_version": "0.2.0"})


def _hostile(mode: str, tmp_path: Path, limits: WorkerLimits = FAST) -> GeometryVerifier:
    return GeometryVerifier(
        limits=limits, diag_dir=tmp_path, worker_command=[sys.executable, "-I", HOSTILE, mode]
    )


ABNORMAL = [
    ("cpu_loop", "BP-01", FAST, {"CPU_LIMIT"}),
    ("wall_hang", "BP-01", FAST, {"WALL_TIMEOUT"}),
    ("memory", "BP-01", FAST, {"MEMORY_LIMIT"}),
    ("garbage", "BP-01", FAST, {"PROTOCOL_ERROR"}),
    ("flood", "BP-01", FAST, {"OUTPUT_LIMIT"}),
    ("stderr_flood", "BP-01", FAST, {"OUTPUT_LIMIT"}),
    ("spoof_efbig_text", "BP-01", FAST, {"NONZERO_EXIT_1"}),
    ("spoof_memory_text", "BP-01", FAST, {"NONZERO_EXIT_1"}),
    ("trailing_after_64k", "BP-01", FAST, {"PROTOCOL_ERROR"}),
    ("exit0_at_limit", "BP-01", FAST, {"OUTPUT_LIMIT"}),
    ("nan_token", "BP-01", FAST, {"PROTOCOL_ERROR"}),
    ("mesh", "NC-04", FAST, {"CPU_LIMIT", "SIGNAL_SIGSEGV", "SIGNAL_SIGABRT", "MEMORY_LIMIT"}),
    ("mesh", "NC-04", LONG_CPU, {"SIGNAL_SIGSEGV", "SIGNAL_SIGABRT", "MEMORY_LIMIT"}),
]


@pytest.mark.parametrize(
    ("mode", "stem", "limits", "expected"),
    ABNORMAL,
    ids=[f"{m}-{'long' if lim is LONG_CPU else 'fast'}" for m, _s, lim, _e in ABNORMAL],
)
def test_abnormal_exit_gives_no_result(
    mode: str, stem: str, limits: WorkerLimits, expected: set[str], tmp_path: Path
) -> None:
    artifact = StepArtifact(payload=payload(stem))
    with pytest.raises(GeometryExecutionError) as caught:
        _hostile(mode, tmp_path, limits).evaluate(TASK, artifact)
    error = caught.value
    assert error.classification in expected
    records = list(tmp_path.glob("*.json"))
    assert len(records) == 1  # write-once diagnostic record
    record = json.loads(records[0].read_text(encoding="utf-8"))
    assert record["classification"] == error.classification
    assert record["input_sha256"] == artifact.content_hash
    assert len(record["stderr_tail"].encode("utf-8")) <= STDERR_TAIL_BYTES * 4  # bounded
    assert "geometry_facts" not in record and "result_id" not in record


def test_spoofed_text_is_retained_but_never_classified(tmp_path: Path) -> None:
    with pytest.raises(GeometryExecutionError) as caught:
        _hostile("spoof_efbig_text", tmp_path).evaluate(
            TASK, StepArtifact(payload=payload("BP-01"))
        )
    assert caught.value.classification == "NONZERO_EXIT_1"
    assert "File too large" in caught.value.diagnostic["stderr_tail"]


def test_normal_reads_by_the_production_worker(verifier: GeometryVerifier) -> None:
    stem, declared, _expected, _failing = CASES["BP-01"]
    ok = verifier.evaluate(
        GeometryTask(task_id="ga9-bp01", requirements=declared), StepArtifact(payload=payload(stem))
    )
    assert isinstance(ok, GeometryEngineeringResult)
    parse_failed = verifier.evaluate(TASK, StepArtifact(payload=payload("NC-03")))
    assert isinstance(parse_failed, GeometryUnverifiedOutcome)  # a normal exit, not an error
    assert parse_failed.reason.value == "PARSE_FAILED"


def test_classifier_reads_no_child_text() -> None:
    parameters = set(inspect.signature(classify).parameters)
    assert parameters == {
        "status",
        "timed_out",
        "cpu_seconds",
        "output_bytes",
        "stderr_bytes",
        "limits",
    }


def test_classifier_table() -> None:
    limits = WorkerLimits()
    full = limits.output_bytes

    def c(status: int, **kw: object) -> str | None:
        args: dict[str, object] = {
            "timed_out": False,
            "cpu_seconds": 0.0,
            "output_bytes": 0,
            "stderr_bytes": 0,
            "limits": limits,
        }
        args.update(kw)
        return classify(status, **args)  # type: ignore[arg-type]

    exit1 = 1 << 8
    assert c(0, timed_out=True) == "WALL_TIMEOUT"
    assert c(signal.SIGXCPU) == "CPU_LIMIT"
    assert c(signal.SIGKILL, cpu_seconds=float(limits.cpu_soft_s)) == "CPU_LIMIT"
    assert c(signal.SIGKILL, cpu_seconds=0.5) == "SIGNAL_SIGKILL"
    assert c(signal.SIGXFSZ) == "OUTPUT_LIMIT"
    assert c(signal.SIGSEGV) == "SIGNAL_SIGSEGV"
    assert c(exit1, output_bytes=full) == "OUTPUT_LIMIT"
    assert c(exit1, stderr_bytes=full) == "OUTPUT_LIMIT"
    assert c(0, output_bytes=full) == "OUTPUT_LIMIT"
    assert c(3 << 8) == "MEMORY_LIMIT"
    assert c(exit1) == "NONZERO_EXIT_1"
    assert c(0, output_bytes=10) is None


def test_parent_survives_and_keeps_working(tmp_path: Path, verifier: GeometryVerifier) -> None:
    """After an abnormal exit the same parent process verifies a valid part normally."""
    with pytest.raises(GeometryExecutionError):
        _hostile("garbage", tmp_path).evaluate(TASK, StepArtifact(payload=payload("BP-01")))
    stem, declared, _expected, _failing = CASES["BP-02"]
    outcome = verifier.evaluate(
        GeometryTask(task_id="after", requirements=declared), StepArtifact(payload=payload(stem))
    )
    assert isinstance(outcome, GeometryEngineeringResult)
    assert os.getpid() > 0
