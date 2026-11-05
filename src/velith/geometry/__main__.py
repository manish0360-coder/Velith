"""Command line: ``python -m velith.geometry verify STEP_FILE REQUIREMENTS_JSON``.

Prints one JSON document to stdout and exits with:

- 0: verified, the ``ResultBundle`` (spec F r3 §1);
- 1: unverified, ``{"outcome": "UNVERIFIED", "reason": ..., "facts": ...}`` (diagnostic only);
- 2: abnormal worker exit, ``{"outcome": "EXECUTION_ERROR", "classification": ...}``, nothing else;
- 3: invalid input (requirements or artifact), ``{"outcome": "INVALID_INPUT", "error": ...}``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from velith.api.contract import ContractError
from velith.api.geometry_contract import GeometryEngineeringResult, GeometryTask, StepArtifact
from velith.geometry.verifier import DEFAULT_DIAG_DIR, GeometryExecutionError, GeometryVerifier


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m velith.geometry")
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser(
        "verify", help="verify one STEP file against declared requirements"
    )
    verify.add_argument("step_file", type=Path)
    verify.add_argument("requirements_json", type=Path)
    verify.add_argument("--task-id", default="g0-cli")
    verify.add_argument("--diag-dir", type=Path, default=DEFAULT_DIAG_DIR)
    args = parser.parse_args(argv)

    try:
        task = GeometryTask(
            task_id=args.task_id,
            requirements=json.loads(args.requirements_json.read_text(encoding="utf-8")),
        )
        artifact = StepArtifact(payload=args.step_file.read_bytes())
    except (OSError, ValueError, ValidationError, ContractError) as exc:
        print(json.dumps({"outcome": "INVALID_INPUT", "error": str(exc)}, indent=1))
        return 3
    try:
        outcome = GeometryVerifier(diag_dir=args.diag_dir).evaluate(task, artifact)
    except GeometryExecutionError as exc:
        print(
            json.dumps(
                {"outcome": "EXECUTION_ERROR", "classification": exc.classification}, indent=1
            )
        )
        return 2
    if isinstance(outcome, GeometryEngineeringResult):
        print(json.dumps(outcome.bundle(), indent=1, sort_keys=True))
        return 0
    print(
        json.dumps(
            {"outcome": "UNVERIFIED", "reason": outcome.reason.value, "facts": outcome.facts},
            indent=1,
            sort_keys=True,
        )
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
