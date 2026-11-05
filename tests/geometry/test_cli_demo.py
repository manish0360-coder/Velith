"""The M1 demo: ``python -m velith.geometry verify part.step req.json`` (readiness report §4).

Prints a ``ResultBundle`` (exit 0) for a conforming part, an unverified outcome (exit 1) for CR-02,
an execution-error classification and nothing else (exit 2) when the worker cannot run, and an
input error (exit 3) for invalid requirements.
"""

from __future__ import annotations

import json
import platform
from pathlib import Path

import pytest

from tests.geometry._cases import CASES, PARTS
from velith.api.geometry_contract import from_bundle
from velith.geometry.__main__ import main


def _run(
    case: str, tmp_path: Path, capsys: pytest.CaptureFixture[str], **override: object
) -> tuple[int, dict[str, object]]:
    stem, declared, _e, _f = CASES[case]
    requirements = tmp_path / "req.json"
    requirements.write_text(json.dumps({**declared, **override}), encoding="utf-8")
    code = main(
        [
            "verify",
            str(PARTS / f"{stem}.step"),
            str(requirements),
            "--diag-dir",
            str(tmp_path / "d"),
        ]
    )
    printed: dict[str, object] = json.loads(capsys.readouterr().out)
    return code, printed


def test_verified_part_prints_a_valid_bundle(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, printed = _run("BP-01", tmp_path, capsys)
    assert code == 0
    from_bundle(printed, step_bytes=(PARTS / "BP-01.step").read_bytes())


def test_contradicting_requirements_print_an_unverified_outcome(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, printed = _run("CR-02", tmp_path, capsys)
    assert code == 1
    assert printed["outcome"] == "UNVERIFIED" and printed["reason"] == "REQUIREMENT_NOT_MET"


def test_execution_error_prints_only_the_classification(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(platform, "machine", lambda: "arm64")
    code, printed = _run("BP-01", tmp_path, capsys)
    assert code == 2
    assert printed == {"outcome": "EXECUTION_ERROR", "classification": "PLATFORM_UNSUPPORTED"}


def test_invalid_requirements_are_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, printed = _run("BP-01", tmp_path, capsys, expected_solids="01")
    assert code == 3 and printed["outcome"] == "INVALID_INPUT"
