"""GA5 / G-a: import isolation (spec F r3 §7).

- A fresh ``python -I`` process importing ``velith.api`` loads neither ``OCP`` nor
  ``velith.geometry``.
- Importing the parent-side verifier and the pure rule modules does not load ``OCP``.
- Statically, ``velith/geometry/_kernel.py`` is the only source file that imports ``OCP``, and no
  ``velith.api`` source imports ``velith.geometry``.

(Velith has no import-linter configuration; these tests enforce the same contracts.)
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "velith"
PROBE = (
    "import importlib, json, sys; importlib.import_module(sys.argv[1]); "
    "print(json.dumps(sorted(m for m in sys.modules if m == 'OCP' or m.startswith(('OCP.', "
    "'velith.geometry')))))"
)


def _loaded(module: str) -> list[str]:
    proc = subprocess.run(
        [sys.executable, "-I", "-c", PROBE, module], capture_output=True, text=True, check=True
    )
    loaded: list[str] = json.loads(proc.stdout.strip().splitlines()[-1])
    return loaded


def test_velith_api_loads_no_geometry_and_no_ocp() -> None:
    assert _loaded("velith.api") == []


@pytest.mark.parametrize(
    "module",
    ["velith.geometry.verifier", "velith.geometry.rules", "velith.geometry.annotation_scan"],
)
def test_parent_side_modules_load_no_ocp(module: str) -> None:
    assert not [name for name in _loaded(module) if name == "OCP" or name.startswith("OCP.")]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_only_the_worker_imports_ocp() -> None:
    importers = sorted(
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if any(name == "OCP" or name.startswith("OCP.") for name in _imports(path))
    )
    assert importers == ["geometry/_kernel.py"]


def test_api_sources_never_import_velith_geometry() -> None:
    for path in (SRC / "api").glob("*.py"):
        assert not [n for n in _imports(path) if n.startswith("velith.geometry")], path
