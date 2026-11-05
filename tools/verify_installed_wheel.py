"""Release gate (D33, API-0 C3): the ``velith`` wheel is a real, self-contained, installable
package.

Manual release gate, not part of CI. Run inside the verifier container (Python 3.12) with the
repository's ``tools/`` mounted read-only:

    docker compose run --rm -v "$PWD/tools:/app/tools:ro" verifier \
        python tools/verify_installed_wheel.py

Fail-closed: every stage either passes or records FAIL; a build, venv or installation failure stops
the gate immediately; nothing is skipped and nothing falls back to the source checkout. Exit 0 only
if every check passed. Needs network access (PyPI for pinned dependencies and the build backend,
GitHub for the Noetica tag).

Stages:
  A. build the wheel from the source tree (version read from ``src/velith/__init__.py``; no git tag)
     and audit its archive: name, metadata, required files incl. ``py.typed``, no foreign files;
  B. create a fresh virtual environment without system site-packages and prove no ``velith`` or
     ``noetica`` is importable before installation (negative control);
  C. install the wheel with its pinned dependencies (``--isolated --no-cache-dir``) and verify
     Noetica 1.0.0 and its PEP 610 git provenance (repository, ``v1.0.0``, exact commit);
  D. contract boundary: a fresh ``python -I`` process imports ``velith.api`` only; it must not load
     the harness, the adapter, settings, the analysis layer or any forbidden package, and every
     loaded ``velith`` module must come from the installed wheel;
  E. adapter packaging: a separate fresh process imports ``velith.api.swe`` (harness dependencies
     allowed); ``SweVerifier`` is a class; every loaded ``velith`` module comes from the wheel.
     ``SweVerifier`` is never instantiated and no fixture is used (K4);
  F. vectors: ``tests/unit/test_api_vectors.py`` alone, run against the installed wheel, must report
     exactly 5 passed and nothing skipped, xfailed, errored, failed or uncollected.

Geometry (G0, Engineering API v0.2; Gate 0 spec F r3 §7):
  G-a. importing ``velith.api`` loads neither ``OCP`` nor ``velith.geometry`` (part of stage D);
  G-b. after installing the hash-pinned ``geometry`` extra (``constraints/geometry-py312.txt``),
       a fresh ``python -I`` process imports ``velith.geometry.verifier`` from the venv, the binding
       is the pinned version and the host passes the identity-platform check;
  G-c. vectors: ``tests/geometry/test_vg_vectors.py`` (VG-0, VG-R and the VG-1..VG-12 benchmark
       vectors, which run the real worker) passes against the installed wheel with nothing skipped.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import venv
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "velith"
#: The release this gate certifies. Changing it is a deliberate release decision.
RELEASE_VERSION = "0.2.0"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")

EXPECTED_REQUIRES_PYTHON = "==3.12.*"
EXPECTED_RUNTIME_REQUIRES = {
    "pydantic==2.9.2",
    "pydantic-settings==2.5.2",
    "noetica @ git+https://github.com/manish0360-coder/Noetica-agent-lab@v1.0.0",
}
REQUIRED_WHEEL_FILES = {
    "velith/__init__.py",
    "velith/py.typed",
    "velith/api/__init__.py",
    "velith/api/contract.py",
    "velith/api/swe.py",
    "velith/api/geometry_contract.py",
    "velith/api/schemas/engineering_result.v1.schema.json",
    "velith/geometry/__init__.py",
    "velith/geometry/__main__.py",
    "velith/geometry/_kernel.py",
    "velith/geometry/_protocol.py",
    "velith/geometry/annotation_scan.py",
    "velith/geometry/rules.py",
    "velith/geometry/verifier.py",
}

NOETICA_VERSION = "1.0.0"
NOETICA_URL = "https://github.com/manish0360-coder/Noetica-agent-lab"
NOETICA_REVISION = "v1.0.0"
NOETICA_COMMIT = "44d380bdcadf50fec463c2840bc5d181d7e7e0f7"
PINNED_DEPENDENCIES = {"pydantic": "2.9.2", "pydantic-settings": "2.5.2"}

#: Never loaded by importing the contract package ``velith.api`` (stage D).
CONTRACT_FORBIDDEN = (
    "velith.harness",
    "velith.api.swe",
    "velith.core.config",
    "velith.analysis",
    "statsmodels",
    "mini_prometheus",
    "miniflywire",
    "velith.geometry",  # G-a
    "OCP",  # G-a
)
#: Never loaded by importing the adapter ``velith.api.swe`` (stage E).
ADAPTER_FORBIDDEN = ("velith.analysis", "statsmodels", "mini_prometheus", "miniflywire")
#: Never imported by the contract sources; the adapter may import the harness and settings.
CONTRACT_SOURCES = (
    "velith/api/__init__.py",
    "velith/api/contract.py",
    "velith/api/geometry_contract.py",
)
ALL_API_FORBIDDEN_IMPORTS = ("mini_prometheus", "miniflywire", "velith.analysis", "statsmodels")
CONTRACT_FORBIDDEN_IMPORTS = (
    *ALL_API_FORBIDDEN_IMPORTS,
    "velith.harness",
    "velith.core",
    "velith.geometry",
    "OCP",
)

EXPECTED_VECTOR_TESTS = 5

LEAK_PATTERNS = [
    re.compile(p)
    for p in (
        r"[A-Za-z]:\\(?:Users|Projects)\\",
        r"/home/[a-z]",
        r"/Users/[A-Za-z]",
        r"/mnt/[a-z]/",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"\bgh[pousr]_[A-Za-z0-9]{20,}",
        r"\bAKIA[0-9A-Z]{16}\b",
    )
]

failures: list[str] = []


class GateAbortError(Exception):
    """A stage whose failure leaves nothing meaningful to check afterwards."""


def check(ok: bool, label: str, detail: str = "") -> bool:
    print(("PASS  " if ok else "FAIL  ") + label + ("" if ok or not detail else f" :: {detail}"))
    if not ok:
        failures.append(label)
    return ok


def require(ok: bool, label: str, detail: str = "") -> None:
    if not check(ok, label, detail):
        raise GateAbortError(label)


def run(
    cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=cwd, env=env)


def tail(proc: subprocess.CompletedProcess[str]) -> str:
    return (proc.stdout[-1500:] + "\n" + proc.stderr[-2500:]).strip()


def clean_env() -> dict[str, str]:
    drop = {"PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE"}
    return {k: v for k, v in os.environ.items() if k not in drop and not k.startswith("PIP_")}


def source_version() -> str | None:
    text = (ROOT / "src" / PACKAGE / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]*)"$', text, re.MULTILINE)
    return match.group(1) if match else None


def imported_modules(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def matches(name: str, prefixes: tuple[str, ...]) -> bool:
    return any(name == p or name.startswith(p + ".") for p in prefixes)


# --- A. build + archive audit ---------------------------------------------------------------


def build_wheel(dist: Path, version: str) -> Path:
    build = run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            str(ROOT),
            "--no-deps",
            "--isolated",
            "--no-cache-dir",
            "--disable-pip-version-check",
            "-q",
            "-w",
            str(dist),
        ],
        env=clean_env(),
    )
    wheels = sorted(dist.glob(f"{PACKAGE}-*.whl"))
    require(build.returncode == 0 and len(wheels) == 1, "the wheel builds", tail(build))
    wheel = wheels[0]
    require(
        wheel.name == f"{PACKAGE}-{version}-py3-none-any.whl",
        f"the wheel is {PACKAGE}-{version}-py3-none-any.whl",
        wheel.name,
    )
    return wheel


def audit_wheel(wheel: Path, version: str) -> None:
    dist_info = f"{PACKAGE}-{version}.dist-info/"
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        outside = [n for n in names if not n.startswith((f"{PACKAGE}/", dist_info))]
        check(
            not outside,
            "the wheel contains only the velith package and its dist-info",
            f"{outside}",
        )
        missing = sorted(REQUIRED_WHEEL_FILES - set(names))
        check(
            not missing, "contract, adapter, schema and py.typed are packaged", f"missing {missing}"
        )
        junk = [
            n
            for n in names
            if any(part in ("__pycache__", ".git", "fixtures", "tests") for part in n.split("/"))
            or n.endswith((".pyc", ".pyo"))
        ]
        check(not junk, "no tests, fixtures, cache or source-control files are packaged", f"{junk}")

        metadata = archive.read(f"{dist_info}METADATA").decode("utf-8")
        header = metadata.split("\n\n", 1)[0]
        lines = [line for line in header.splitlines() if ": " in line and not line[0].isspace()]
        fields: dict[str, list[str]] = {}
        for line in lines:
            key, value = line.split(": ", 1)
            fields.setdefault(key, []).append(value)
        check(fields.get("Name") == [PACKAGE], "metadata Name is velith", f"{fields.get('Name')}")
        check(
            fields.get("Version") == [version],
            f"metadata Version is {version}",
            f"{fields.get('Version')}",
        )
        check(
            fields.get("Requires-Python") == [EXPECTED_REQUIRES_PYTHON],
            f"metadata Requires-Python is {EXPECTED_REQUIRES_PYTHON}",
            f"{fields.get('Requires-Python')}",
        )
        runtime = {r for r in fields.get("Requires-Dist", []) if "extra ==" not in r}
        check(
            runtime == EXPECTED_RUNTIME_REQUIRES,
            "runtime dependencies are exactly pydantic, pydantic-settings, noetica@v1.0.0",
            f"{sorted(runtime)}",
        )

        leaks: list[str] = []
        for name in names:
            if name.endswith("/"):
                continue
            text = archive.read(name).decode("utf-8", errors="replace")
            leaks += [f"{name}: {p.pattern}" for p in LEAK_PATTERNS if p.search(text)]
        check(not leaks, "no machine-specific path or credential material is packaged", f"{leaks}")


# --- B/C. isolated environment, installation, provenance -----------------------------------

PREINSTALL_PROBE = r"""
import importlib.util, json
print(json.dumps({m: importlib.util.find_spec(m) is not None for m in ("velith", "noetica")}))
"""

# Stage D/E probe: argv[1] = module to import, argv[2] = comma-separated forbidden prefixes.
IMPORT_PROBE = r"""
import importlib, importlib.metadata, importlib.util, inspect, json, sys, sysconfig
target, forbidden = sys.argv[1], tuple(p for p in sys.argv[2].split(",") if p)
module = importlib.import_module(target)
loaded = sorted(sys.modules)
velith_files = {
    name: getattr(mod, "__file__", None)
    for name, mod in sys.modules.items()
    if name == "velith" or name.startswith("velith.")
}
out = {
    "purelib": sysconfig.get_paths()["purelib"],
    "platlib": sysconfig.get_paths()["platlib"],
    "sys_path": sys.path,
    "velith_files": velith_files,
    "forbidden_loaded": [
        m for m in loaded if any(m == p or m.startswith(p + ".") for p in forbidden)
    ],
    "target_file": getattr(module, "__file__", None),
}
if target == "velith.api":
    import velith, noetica
    dist = importlib.metadata.distribution("noetica")
    out["velith_version"] = velith.__version__
    out["velith_metadata_version"] = importlib.metadata.version("velith")
    out["velith_record"] = sorted(str(f) for f in (importlib.metadata.files("velith") or []))
    out["noetica_version"] = noetica.__version__
    out["noetica_metadata_version"] = dist.version
    out["noetica_file"] = noetica.__file__
    out["noetica_direct_url"] = dist.read_text("direct_url.json")
    out["deps"] = {d: importlib.metadata.version(d) for d in ("pydantic", "pydantic-settings")}
    out["statsmodels_findable"] = importlib.util.find_spec("statsmodels") is not None
if target == "velith.api.swe":
    out["sweverifier_is_class"] = inspect.isclass(getattr(module, "SweVerifier", None))
print(json.dumps(out))
"""


def probe(python: str, script: Path, args: list[str], cwd: Path) -> dict[str, Any]:
    proc = run([python, "-I", str(script), *args], cwd=cwd, env=clean_env())
    require(proc.returncode == 0, f"probe `{' '.join(args) or script.name}` runs", tail(proc))
    try:
        loaded: dict[str, Any] = json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise GateAbortError(f"probe output unreadable: {exc}: {tail(proc)}") from exc
    return loaded


def under(path: str | None, root: str) -> bool:
    if not path:
        return False
    return str(Path(path).resolve()).startswith(str(Path(root).resolve()) + os.sep)


def check_import_isolation(found: dict[str, Any], stage: str) -> None:
    site = found["purelib"]
    files: dict[str, str | None] = found["velith_files"]
    bad = {name: f for name, f in files.items() if not under(f, site)}
    check(
        bool(files) and not bad,
        f"{stage}: every loaded velith module ({len(files)}) comes from the installed wheel",
        f"{bad}",
    )
    repo_paths = [p for p in found["sys_path"] if p and under(p, str(ROOT))]
    foreign_sites = [
        p
        for p in found["sys_path"]
        if p.rstrip("/").endswith(("site-packages", "dist-packages"))
        and str(Path(p).resolve())
        not in {str(Path(found["purelib"]).resolve()), str(Path(found["platlib"]).resolve())}
    ]
    check(
        not repo_paths and not foreign_sites,
        f"{stage}: no repository path and no foreign site-packages on sys.path",
        f"repo={repo_paths} foreign={foreign_sites}",
    )
    check(
        not found["forbidden_loaded"],
        f"{stage}: no forbidden module is loaded",
        f"{found['forbidden_loaded']}",
    )


def check_noetica_provenance(found: dict[str, Any]) -> None:
    check(
        found["noetica_version"] == found["noetica_metadata_version"] == NOETICA_VERSION,
        f"noetica is version {NOETICA_VERSION}",
        f"__version__={found['noetica_version']} metadata={found['noetica_metadata_version']}",
    )
    check(
        under(found["noetica_file"], found["purelib"]),
        "noetica is imported from the venv",
        found["noetica_file"],
    )
    for dep, version in PINNED_DEPENDENCIES.items():
        check(found["deps"].get(dep) == version, f"{dep} is {version}", f"{found['deps'].get(dep)}")
    check(not found["statsmodels_findable"], "the API needs no analysis stack (statsmodels absent)")
    raw = found["noetica_direct_url"]
    if not check(
        raw is not None, "noetica has PEP 610 direct_url.json provenance", "direct_url.json missing"
    ):
        return
    try:
        direct = json.loads(raw)
    except json.JSONDecodeError as exc:
        check(False, "noetica direct_url.json is valid JSON", str(exc))
        return
    vcs = direct.get("vcs_info") or {}
    expected = {
        "url": NOETICA_URL,
        "vcs": "git",
        "requested_revision": NOETICA_REVISION,
        "commit_id": NOETICA_COMMIT,
    }
    actual = {
        "url": direct.get("url"),
        "vcs": vcs.get("vcs"),
        "requested_revision": vcs.get("requested_revision"),
        "commit_id": vcs.get("commit_id"),
    }
    for field, value in expected.items():
        check(
            actual[field] == value,
            f"noetica provenance {field} is {value}",
            f"expected {value!r}, found {actual[field]!r}",
        )


def check_contract_sources(site: str) -> None:
    api_dir = Path(site) / PACKAGE / "api"
    sources = sorted(api_dir.glob("*.py"))
    check(
        len(sources) >= 3,
        "installed velith/api sources are present",
        f"{[s.name for s in sources]}",
    )
    for source in sources:
        rel = f"{PACKAGE}/api/{source.name}"
        forbidden = (
            CONTRACT_FORBIDDEN_IMPORTS if rel in CONTRACT_SOURCES else ALL_API_FORBIDDEN_IMPORTS
        )
        bad = sorted(
            m for m in imported_modules(source.read_text(encoding="utf-8")) if matches(m, forbidden)
        )
        check(not bad, f"installed {rel} imports nothing forbidden", f"{bad}")


# --- F. vectors against the installed wheel -------------------------------------------------

VECTOR_CONFTEST = '''"""Generated by tools/verify_installed_wheel.py: use the installed wheel."""
import sysconfig
from pathlib import Path

import velith
import velith.api

_SITE = Path(sysconfig.get_paths()["purelib"]).resolve()
for _module in (velith, velith.api):
    _path = Path(_module.__file__).resolve()
    if _SITE not in _path.parents:
        raise RuntimeError(f"{_module.__name__} imported from {_path}, not the installed wheel")
'''


def run_vectors(python: str, tmp: Path) -> None:
    vec_dir = tmp / "vectors"
    vec_dir.mkdir()
    shutil.copy2(ROOT / "tests" / "unit" / "test_api_vectors.py", vec_dir / "test_api_vectors.py")
    (vec_dir / "conftest.py").write_text(VECTOR_CONFTEST, encoding="utf-8")
    (vec_dir / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    junit = tmp / "vectors.xml"
    proc = run(
        [
            python,
            "-I",
            "-m",
            "pytest",
            "-q",
            "-rA",
            "-p",
            "no:cacheprovider",
            "--rootdir",
            str(vec_dir),
            "-c",
            str(vec_dir / "pytest.ini"),
            f"--junitxml={junit}",
            str(vec_dir / "test_api_vectors.py"),
        ],
        cwd=vec_dir,
        env=clean_env(),
    )
    summary = (proc.stdout.strip().splitlines() or [""])[-1]
    print(f"      vectors: {summary}")
    if not check(junit.is_file(), "the vector run produced a JUnit report", tail(proc)):
        return
    suite = ElementTree.parse(junit).getroot()
    if suite.tag == "testsuites":
        suite = suite[0]
    counts = {k: int(suite.get(k, "-1")) for k in ("tests", "failures", "errors", "skipped")}
    check(
        proc.returncode == 0
        and counts == {"tests": EXPECTED_VECTOR_TESTS, "failures": 0, "errors": 0, "skipped": 0},
        f"T1-T5b: exactly {EXPECTED_VECTOR_TESTS} passed against the installed wheel "
        "(none skipped, xfailed, errored, failed or uncollected)",
        f"exit={proc.returncode} {counts} {tail(proc)}",
    )


# --- G-b / G-c. geometry extra ----------------------------------------------------------------

GEOMETRY_PROBE = r"""
import importlib.metadata, json, sysconfig
import velith.geometry.verifier as verifier
print(json.dumps({
    "purelib": sysconfig.get_paths()["purelib"],
    "verifier_file": verifier.__file__,
    "binding_version": importlib.metadata.version("cadquery-ocp-novtk"),
    "platform_support": verifier.platform_support(),
}))
"""


def check_geometry_extra(python: str, tmp: Path, neutral: Path) -> None:
    install = run(
        [
            python,
            "-m",
            "pip",
            "install",
            "--isolated",
            "--no-cache-dir",
            "--disable-pip-version-check",
            "-q",
            "--no-deps",
            "--require-hashes",
            "-r",
            str(ROOT / "constraints" / "geometry-py312.txt"),
        ],
        cwd=neutral,
        env=clean_env(),
    )
    require(install.returncode == 0, "G-b: the hash-pinned geometry extra installs", tail(install))
    script = tmp / "geometry_probe.py"
    script.write_text(GEOMETRY_PROBE, encoding="utf-8")
    found = probe(python, script, [], neutral)
    check(
        under(found["verifier_file"], found["purelib"]),
        "G-b: velith.geometry.verifier imports from the venv",
        f"{found['verifier_file']}",
    )
    check(
        found["binding_version"] == "8.0.1.1.0" and found["platform_support"] is None,
        "G-b: the binding is the pinned 8.0.1.1.0 and the host is the identity platform",
        f"{found['binding_version']} / {found['platform_support']}",
    )
    vec_root = tmp / "geometry_vectors"
    vec_dir = vec_root / "tests" / "geometry"
    shutil.copytree(
        ROOT / "tests" / "geometry", vec_dir, ignore=shutil.ignore_patterns("__pycache__")
    )
    (vec_root / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (vec_root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    junit = tmp / "geometry_vectors.xml"
    proc = run(
        [
            python,
            "-I",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--rootdir",
            str(vec_root),
            "-c",
            str(vec_root / "pytest.ini"),
            f"--junitxml={junit}",
            str(vec_dir / "test_vg_vectors.py"),
        ],
        cwd=vec_root,
        env=clean_env(),
    )
    if not check(
        junit.is_file(), "G-c: the geometry vector run produced a JUnit report", tail(proc)
    ):
        return
    suite = ElementTree.parse(junit).getroot()
    if suite.tag == "testsuites":
        suite = suite[0]
    counts = {k: int(suite.get(k, "-1")) for k in ("tests", "failures", "errors", "skipped")}
    check(
        proc.returncode == 0
        and counts["tests"] > 0
        and counts["failures"] == counts["errors"] == counts["skipped"] == 0,
        "G-c: VG vectors pass against the installed wheel (none skipped, errored or failed)",
        f"exit={proc.returncode} {counts} {tail(proc)}",
    )


# --- main ------------------------------------------------------------------------------------


def main() -> int:
    version = source_version()
    check(
        version == RELEASE_VERSION and version is not None and bool(SEMVER.match(version)),
        f"source version is the release version {RELEASE_VERSION}",
        f"{version}",
    )
    try:
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            wheel = build_wheel(tmp / "dist", RELEASE_VERSION)
            print(f"      wheel: {wheel.name}")
            audit_wheel(wheel, RELEASE_VERSION)

            env_dir = tmp / "venv"
            venv.create(env_dir, with_pip=True, system_site_packages=False, clear=True)
            python = str(env_dir / "bin" / "python")
            require(Path(python).is_file(), "a fresh venv without system site-packages is created")
            neutral = tmp / "neutral"
            neutral.mkdir()
            pre = tmp / "preinstall_probe.py"
            pre.write_text(PREINSTALL_PROBE, encoding="utf-8")
            state = probe(python, pre, [], neutral)
            require(
                state == {"velith": False, "noetica": False},
                "negative control: neither velith nor noetica is importable before installation",
                f"{state}",
            )

            install = run(
                [
                    python,
                    "-m",
                    "pip",
                    "install",
                    "--isolated",
                    "--no-cache-dir",
                    "--disable-pip-version-check",
                    "-q",
                    "-c",
                    str(ROOT / "constraints" / "analysis-py312.txt"),
                    str(wheel),
                    "pytest==8.3.3",
                ],
                cwd=neutral,
                env=clean_env(),
            )
            require(
                install.returncode == 0,
                "the wheel and its pinned dependencies install",
                tail(install),
            )

            script = tmp / "import_probe.py"
            script.write_text(IMPORT_PROBE, encoding="utf-8")

            contract = probe(python, script, ["velith.api", ",".join(CONTRACT_FORBIDDEN)], neutral)
            site = contract["purelib"]
            check_import_isolation(contract, "D velith.api")
            check(
                contract["velith_version"]
                == contract["velith_metadata_version"]
                == RELEASE_VERSION,
                f"installed metadata, velith.__version__ and source agree on {RELEASE_VERSION}",
                f"{contract['velith_version']} / {contract['velith_metadata_version']}",
            )
            check(
                "velith/py.typed" in contract["velith_record"]
                and (Path(site) / PACKAGE / "py.typed").is_file(),
                "py.typed is installed and listed in RECORD",
            )
            check_noetica_provenance(contract)
            check_contract_sources(site)

            adapter = probe(
                python, script, ["velith.api.swe", ",".join(ADAPTER_FORBIDDEN)], neutral
            )
            check_import_isolation(adapter, "E velith.api.swe")
            check(
                under(adapter["target_file"], site) and adapter.get("sweverifier_is_class") is True,
                "velith.api.swe is packaged and SweVerifier is a class (not instantiated)",
                f"{adapter['target_file']}",
            )

            run_vectors(python, tmp)
            check_geometry_extra(python, tmp, neutral)
            check(list(neutral.iterdir()) == [], "nothing is written to the working directory")
    except GateAbortError as abort:
        # A required stage failed: it is already recorded; nothing after it is meaningful.
        print(f"ABORT {abort}")
        if not failures:
            failures.append(f"abort: {abort}")
    except Exception as exc:  # fail closed on anything unexpected, never exit 0
        traceback.print_exc()
        failures.append(f"unexpected error: {exc!r}")

    print(f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
