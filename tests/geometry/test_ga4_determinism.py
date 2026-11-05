"""GA4 (part that runs here): identical bytes + requirements + pinned kernel + identity platform
give identical facts, ``content_hash`` and ``result_id`` across runs and across processes.

Two separate interpreter processes with different ``PYTHONHASHSEED`` run the CLI on every verified
benchmark part and must print byte-identical bundles. The container legs of GA4 (the Velith verifier
image and the owner's WSL2 Docker) run ``test_vg_vectors.py`` inside those images.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.geometry._cases import CASES, PARTS


def _cli(case: str, seed: str, tmp_path: Path) -> bytes:
    stem, declared, _expected, _failing = CASES[case]
    requirements = tmp_path / f"{case}.json"
    requirements.write_text(json.dumps(declared), encoding="utf-8")
    env = {**os.environ, "PYTHONHASHSEED": seed}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "velith.geometry",
            "verify",
            str(PARTS / f"{stem}.step"),
            str(requirements),
            "--diag-dir",
            str(tmp_path / "diag"),
        ],
        capture_output=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout


@pytest.mark.parametrize("case", ["BP-01", "BP-02", "BP-03", "BP-04"])
def test_two_processes_identical_bundles(case: str, tmp_path: Path) -> None:
    assert _cli(case, "0", tmp_path) == _cli(case, "4242", tmp_path)
