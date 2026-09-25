"""M2 container verifier feasibility probe (Step 2) -- experiment plumbing only.

Runs ONE repository-level benchmark task inside its sealed, digest-pinned published
container and classifies a candidate patch as PASSED / FAILED / PATCH_APPLY_FAILED /
INFRA_ERROR, using a baseline control run in a second fresh container from the same
digest. The baseline is what separates a broken environment from a wrong patch: a
failure present at baseline belongs to the environment, a failure that appears only
after the candidate belongs to the candidate.

This is a feasibility probe, NOT the production verifier. It writes no Episode, no
memory, no evaluation sink, no pre-registration and no analysis result. Its evidence is
written only to an operator-supplied directory OUTSIDE the repository and is not a
verdict of record. The benchmark task specification is also kept outside the
repository; no benchmark data is embedded here.

It imports nothing from ``velith``. The frozen deterministic environment
(``_DETERMINISTIC_ENV``), the ``Verdict`` field set, the ``VerdictState`` values and the
presence of ``SandboxExecutionError`` are read from the frozen source with ``ast``, so
they are reused rather than redefined, and the probe runs on a host Python without
installing Velith.

Usage (run from WSL; output paths must be outside the repository):

    python3 probe.py fetch-spec --instance ID --out SPEC.json ...
    python3 probe.py run --spec SPEC.json --case A --out-dir RUNS
    python3 probe.py compare RUNS/F1/evidence.json RUNS/F2/evidence.json
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shlex
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree

REPO_ROOT = Path(__file__).resolve().parents[2]
JUNIT_PATH = "/tmp/velith-junit.xml"
MAX_JUNIT_BYTES = 10_000_000
DATASET_ROWS_URL = "https://datasets-server.huggingface.co/rows"
NEUTRAL_COMMENT = "# velith-probe: behavior-neutral change (acceptance case B)"

PASSED = "PASSED"
FAILED = "FAILED"
PATCH_APPLY_FAILED = "PATCH_APPLY_FAILED"
INFRA_ERROR = "INFRA_ERROR"

_SPEC_KEYS = (
    "instance_id",
    "repo",
    "base_commit",
    "patch",
    "test_patch",
    "fail_to_pass",
    "pass_to_pass",
    "test_files",
    "protected_paths",
    "image",
    "digest",
    "platform",
    "repo_dir",
    "python",
)

#: Container exit codes set by the in-container script (see ``_SCRIPT``).
_EXIT_STATUS: dict[int, str] = {
    0: "RAN",
    90: "BASE_IDENTITY_MISMATCH",
    91: "BASE_IDENTITY_MISMATCH",
    92: "PATCH_APPLY_FAILED",
    93: "TEST_PATCH_FAILED",
    94: "FAULT_INJECTION_FAILED",
    95: "TAMPER_FAILED",
    96: "REPO_DIR_MISSING",
    98: "RESTORE_FAILED",
}

_CHILD_STATE = {"failure": "failed", "error": "error", "skipped": "skipped"}
_SEVERITY = {"passed": 0, "skipped": 1, "failed": 2, "error": 3}

_DIFF_FILE = re.compile(r"^diff --git a/.* b/(.*)$", re.MULTILINE)
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")

_INSPECT_IMAGE = "{{json .RepoDigests}}|{{.Os}}/{{.Architecture}}|{{.Id}}"
_INSPECT_STATE = "{{.State.ExitCode}}|{{.State.OOMKilled}}|{{.HostConfig.NetworkMode}}"

# The whole in-container procedure. Order is the ratified one: sealed environment ->
# candidate patch -> restore pristine protected surface -> remove candidate-added
# runner configuration -> apply test_patch -> run tests. No install, no build.
_SCRIPT = """\
cd @@REPO_DIR@@ || exit 96
BASE=@@BASE@@
echo "VELITH_HEAD $(git rev-parse HEAD)"
echo "VELITH_PARENT $(git rev-parse HEAD^1)"
[ "$(git rev-parse HEAD^1)" = "$BASE" ] || exit 90
[ -z "$(git status --porcelain)" ] || exit 91
@@FAULT@@
if [ -s /tmp/velith/candidate.patch ]; then
  git apply /tmp/velith/candidate.patch || exit 92
fi
@@TAMPER@@
for p in @@PROTECTED@@; do
  if git cat-file -e "$BASE:$p" 2>/dev/null; then
    git checkout -q "$BASE" -- "$p" || exit 98
  else
    rm -f -- "$p"
  fi
done
git ls-files --others -z | while IFS= read -r -d '' f; do
  case "${f##*/}" in
    conftest.py|pytest.ini|.pytest.ini|setup.cfg|tox.ini|pyproject.toml)
      rm -f -- "$f"
      echo "VELITH_REMOVED $f"
      ;;
  esac
done
git apply /tmp/velith/test.patch || exit 93
for p in @@PROTECTED@@; do
  if [ -e "$p" ]; then
    echo "VELITH_SURFACE $(sha256sum -- "$p")"
  else
    echo "VELITH_SURFACE absent $p"
  fi
done
export PATH="@@PYBIN@@:$PATH"
@@TEST_ARGV@@
echo "VELITH_PYTEST_EXIT $?"
@@PYTHON@@ - <<'PY'
import socket
try:
    socket.create_connection(("1.1.1.1", 53), timeout=3).close()
    print("VELITH_NET connected")
except OSError as exc:
    print("VELITH_NET blocked", type(exc).__name__, exc.errno)
PY
exit 0
"""

# Acceptance cases D / D0 only: simulates a candidate that tampers with the protected
# surface and tries to wirehead the runner with a force-pass hook. Runs immediately
# after the candidate patch, i.e. exactly where a tampering patch would act.
_TAMPER = """\
hook='import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    outcome.get_result().outcome = "passed"
'
for p in @@PROTECTED@@; do
  [ -f "$p" ] || continue
  case "${p##*/}" in
    conftest.py) printf '\\n%s\\n' "$hook" >> "$p" || exit 95 ;;
    *) printf '\\n# velith-tamper\\n' >> "$p" || exit 95 ;;
  esac
done
printf '%s\\n' "$hook" > conftest.py || exit 95
printf '[pytest]\\naddopts = -p no:cacheprovider\\n' > pytest.ini || exit 95
echo "VELITH_TAMPERED"
"""


class ProbeError(Exception):
    """A probe precondition failed; the probe stops and reports rather than guessing."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def outside_repo(path: Path) -> Path:
    """Refuse any probe input/output path inside the Velith repository."""
    resolved = path.expanduser().resolve()
    if resolved == REPO_ROOT or resolved.is_relative_to(REPO_ROOT):
        raise ProbeError(f"path must be outside the repository: {resolved}")
    return resolved


def _module_tree(relative: str) -> ast.Module:
    return ast.parse((REPO_ROOT / relative).read_text(encoding="utf-8"))


def read_frozen_contract() -> dict[str, Any]:
    """Read the frozen M2 contract from source, so nothing is redefined here."""
    sandbox = _module_tree("src/velith/harness/verifier_sandbox.py")
    episode = _module_tree("src/velith/episodes/episode.py")
    env: dict[str, str] | None = None
    verdict_fields: list[str] = []
    has_sandbox_error = False
    for node in sandbox.body:
        is_env = (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "_DETERMINISTIC_ENV"
        )
        if is_env and node.value is not None:
            env = ast.literal_eval(node.value)
        if isinstance(node, ast.ClassDef) and node.name == "Verdict":
            verdict_fields = [
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            ]
        if isinstance(node, ast.ClassDef) and node.name == "SandboxExecutionError":
            has_sandbox_error = True
    states: list[str] = []
    for node in episode.body:
        if isinstance(node, ast.ClassDef) and node.name == "VerdictState":
            states = [
                stmt.value.value
                for stmt in node.body
                if isinstance(stmt, ast.Assign)
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
            ]
    if env is None or not verdict_fields or not states or not has_sandbox_error:
        raise ProbeError("frozen M2 contract not found in source -- STOP and report")
    return {"env": env, "verdict_fields": verdict_fields, "states": states}


def patch_files(patch: str) -> list[str]:
    """Files touched by a unified diff, as the official harness extracts them."""
    return sorted(set(_DIFF_FILE.findall(patch)))


def neutral_patch(patch: str) -> str:
    """Case B input: the reference hunks with every change replaced by one comment.

    The result applies at the same place as the reference fix but changes no behavior,
    so FAIL_TO_PASS must stay unresolved. Supported only for in-place Python edits.
    """
    unsupported = ("new file mode", "deleted file mode", "rename from", "Binary files")
    lines = patch.splitlines()
    if any(line.startswith(unsupported) for line in lines):
        raise ProbeError("neutral patch supports in-place edits only")
    if any(not path.endswith(".py") for path in patch_files(patch)):
        raise ProbeError("neutral patch supports Python files only")
    out: list[str] = []
    shift = 0
    index = 0
    while index < len(lines):
        match = _HUNK.match(lines[index])
        if match is None:
            out.append(lines[index])
            index += 1
            continue
        old_start = int(match.group(1))
        old_len = int(match.group(2) or "1")
        index += 1
        body: list[str] = []
        while index < len(lines) and not lines[index].startswith(("@@", "diff --git")):
            body.append(lines[index])
            index += 1
        new_body: list[str] = []
        inserted = 0
        in_addition = False
        for line in body:
            if line.startswith("+"):
                if not in_addition:
                    new_body.append("+" + NEUTRAL_COMMENT)
                    inserted += 1
                in_addition = True
                continue
            in_addition = False
            new_body.append(" " + line[1:] if line.startswith("-") else line)
        header = f"@@ -{old_start},{old_len} +{old_start + shift},{old_len + inserted} @@"
        out.append(header + match.group(5))
        out.extend(new_body)
        shift += inserted
    return "\n".join(out) + "\n"


def _as_list(value: object) -> list[str]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list):
        raise ProbeError(f"expected a list of test ids, got {type(parsed).__name__}")
    return [str(item) for item in parsed]


def fetch_row(dataset: str, instance_id: str) -> dict[str, Any]:
    """Fetch one task row from the public dataset API (host phase, network on)."""
    for offset in range(0, 10_000, 100):
        query = urllib.parse.urlencode(
            {
                "dataset": dataset,
                "config": "default",
                "split": "test",
                "offset": offset,
                "length": 100,
            }
        )
        with urllib.request.urlopen(f"{DATASET_ROWS_URL}?{query}", timeout=60) as response:
            payload = json.load(response)
        rows = payload.get("rows", [])
        if not rows:
            break
        for entry in rows:
            if entry["row"].get("instance_id") == instance_id:
                return dict(entry["row"])
    raise ProbeError(f"{instance_id} not found in {dataset}")


def cmd_fetch_spec(args: argparse.Namespace) -> int:
    out = outside_repo(Path(args.out))
    if out.exists():
        raise ProbeError(f"refusing to overwrite {out}")
    row = fetch_row(args.dataset, args.instance)
    test_patch = str(row["test_patch"])
    gold = str(row["patch"])
    touched = patch_files(test_patch)
    protected = sorted(set(touched) | set(args.protected_config))
    overlap = set(protected) & set(patch_files(gold))
    if overlap:
        raise ProbeError(f"protected paths overlap the reference patch: {sorted(overlap)}")
    spec = {
        "spec_version": 1,
        "dataset": args.dataset,
        "instance_id": row["instance_id"],
        "repo": row["repo"],
        "base_commit": row["base_commit"],
        "patch": gold,
        "test_patch": test_patch,
        "fail_to_pass": _as_list(row["FAIL_TO_PASS"]),
        "pass_to_pass": _as_list(row["PASS_TO_PASS"]),
        "test_files": [path for path in touched if path.endswith(".py")],
        "protected_paths": protected,
        "image": args.image,
        "digest": args.digest,
        "platform": args.platform,
        "repo_dir": args.repo_dir,
        "python": args.python,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"spec written: {out}")
    print(f"required tests: {len(spec['fail_to_pass'])} F2P + {len(spec['pass_to_pass'])} P2P")
    print(f"protected paths: {protected}")
    return 0


def load_spec(path: Path) -> dict[str, Any]:
    spec = json.loads(path.read_text(encoding="utf-8"))
    missing = [key for key in _SPEC_KEYS if key not in spec]
    if missing:
        raise ProbeError(f"spec is missing keys: {missing}")
    overlap = set(spec["protected_paths"]) & set(patch_files(spec["patch"]))
    if overlap:
        raise ProbeError(f"protected paths overlap the reference patch: {sorted(overlap)}")
    return dict(spec)


def docker(*args: str, timeout: float = 600.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def verify_image(spec: dict[str, Any]) -> tuple[bool, str, str]:
    """Pull by digest and verify identity and platform before any container exists."""
    ref = f"{spec['image']}@{spec['digest']}"
    pulled = docker("pull", "--platform", spec["platform"], ref, timeout=3600.0)
    if pulled.returncode != 0:
        return False, "", f"pull failed: {pulled.stderr.strip()}"
    inspected = docker("image", "inspect", ref, "--format", _INSPECT_IMAGE)
    if inspected.returncode != 0:
        return False, "", f"inspect failed: {inspected.stderr.strip()}"
    digests_json, platform, image_id = inspected.stdout.strip().split("|")
    if ref not in json.loads(digests_json):
        return False, image_id, "RepoDigests does not contain the pinned digest"
    if platform != spec["platform"]:
        return False, image_id, f"platform {platform} != {spec['platform']}"
    return True, image_id, ""


def test_argv(spec: dict[str, Any]) -> list[str]:
    return [
        spec["python"],
        "-m",
        "pytest",
        "-rA",
        f"--junitxml={JUNIT_PATH}",
        *spec["test_files"],
    ]


def build_script(spec: dict[str, Any], *, tamper: bool, fault_cmd: str | None) -> str:
    protected = " ".join(shlex.quote(path) for path in spec["protected_paths"])
    script = _SCRIPT
    for token, value in (
        ("@@REPO_DIR@@", shlex.quote(spec["repo_dir"])),
        ("@@BASE@@", shlex.quote(spec["base_commit"])),
        ("@@FAULT@@", f"{fault_cmd} || exit 94" if fault_cmd else ""),
        ("@@TAMPER@@", _TAMPER if tamper else ""),
        ("@@PROTECTED@@", protected),
        ("@@PYBIN@@", str(PurePosixPath(spec["python"]).parent)),
        ("@@TEST_ARGV@@", shlex.join(test_argv(spec))),
        ("@@PYTHON@@", shlex.quote(spec["python"])),
    ):
        script = script.replace(token, value)
    return script


def nodeid_key(nodeid: str) -> tuple[str, str]:
    """Map a pytest node id to the JUnit ``(classname, name)`` pair pytest writes."""
    base, bracket, params = nodeid.partition("[")
    parts = base.split("::")
    module = parts[0].removesuffix(".py").replace("/", ".")
    classname = ".".join([module, *parts[1:-1]])
    return classname, parts[-1] + bracket + params


def junit_outcomes(path: Path, required: list[str]) -> tuple[dict[str, str] | None, int]:
    """Per-required-test outcome from JUnit XML, plus the count of collection failures.

    Returns ``None`` when there is no usable report. A DOCTYPE is refused so a hostile
    report cannot expand entities on the host.
    """
    if not path.is_file():
        return None, 0
    data = path.read_bytes()
    if len(data) > MAX_JUNIT_BYTES or b"<!DOCTYPE" in data:
        return None, 0
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        return None, 0
    seen: dict[tuple[str, str], str] = {}
    collection_failures = 0
    for case in root.iter("testcase"):
        state = "passed"
        for child in case:
            if child.tag == "error" and child.get("message") == "collection failure":
                collection_failures += 1
            observed = _CHILD_STATE.get(child.tag)
            if observed is not None and _SEVERITY[observed] > _SEVERITY[state]:
                state = observed
        key = (case.get("classname", ""), case.get("name", ""))
        previous = seen.get(key, "passed")
        seen[key] = state if _SEVERITY[state] >= _SEVERITY[previous] else previous
    outcomes = {nodeid: seen.get(nodeid_key(nodeid), "missing") for nodeid in required}
    return outcomes, collection_failures


def _text(raw: object) -> str:
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return raw if isinstance(raw, str) else ""


def _markers(stdout: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for line in stdout.splitlines():
        if line.startswith("VELITH_"):
            key, _, value = line.partition(" ")
            found.setdefault(key, []).append(value.strip())
    return found


def _first(markers: dict[str, list[str]], key: str) -> str:
    return markers.get(key, [""])[0]


def _run_status(*, timed_out: bool, oom_killed: bool, exit_code: int) -> str:
    if timed_out:
        return "TIMEOUT"
    if oom_killed:
        return "RESOURCE_KILLED"
    return _EXIT_STATUS.get(exit_code, "CONTAINER_FAILED")


def _failed_run(status: str, detail: str) -> dict[str, Any]:
    return {
        "deterministic": {"status": status, "outcomes": None, "collection_failures": 0},
        "diagnostics": {"detail": detail.strip()},
    }


def run_container(
    spec: dict[str, Any],
    *,
    role: str,
    candidate_patch: str,
    tamper: bool,
    fault_cmd: str | None,
    env: dict[str, str],
    limits: dict[str, Any],
    workdir: Path,
) -> dict[str, Any]:
    """One fresh, network-less container from the pinned digest; always destroyed."""
    stage = workdir / role / "velith"
    stage.mkdir(parents=True)
    (stage / "test.patch").write_text(spec["test_patch"], encoding="utf-8")
    (stage / "candidate.patch").write_text(candidate_patch, encoding="utf-8")
    script = build_script(spec, tamper=tamper, fault_cmd=fault_cmd)
    (stage / "run.sh").write_text(script, encoding="utf-8")
    flags = [
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        str(limits["pids"]),
        "--memory",
        str(limits["memory"]),
        "--memory-swap",
        str(limits["memory"]),
        "--cpus",
        str(limits["cpus"]),
        "--platform",
        spec["platform"],
    ]
    for name, value in sorted(env.items()):
        flags.extend(("-e", f"{name}={value}"))
    ref = f"{spec['image']}@{spec['digest']}"
    created = docker("create", *flags, "--entrypoint", "/bin/bash", ref, "/tmp/velith/run.sh")
    if created.returncode != 0:
        return _failed_run("CONTAINER_START_FAILED", created.stderr)
    container = created.stdout.strip()
    junit_file = workdir / role / "junit.xml"
    stdout = ""
    timed_out = False
    started = time.monotonic()
    try:
        copied = docker("cp", str(stage), f"{container}:/tmp/")
        if copied.returncode != 0:
            return _failed_run("CONTAINER_START_FAILED", copied.stderr)
        try:
            finished = docker("start", "-a", container, timeout=float(limits["timeout_seconds"]))
            stdout = finished.stdout + finished.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = _text(exc.stdout)
            docker("kill", container)
        state = docker("inspect", container, "--format", _INSPECT_STATE).stdout.strip()
        docker("cp", f"{container}:{JUNIT_PATH}", str(junit_file))
    finally:
        docker("rm", "-f", container)
    duration = round(time.monotonic() - started, 3)
    (workdir / role / "stdout.txt").write_text(stdout, encoding="utf-8")
    exit_code, oom_killed, network_mode = state.split("|")
    if network_mode != "none":
        raise ProbeError(f"container ran with network mode {network_mode!r} -- STOP")
    markers = _markers(stdout)
    required = [*spec["fail_to_pass"], *spec["pass_to_pass"]]
    outcomes, collection_failures = junit_outcomes(junit_file, required)
    status = _run_status(
        timed_out=timed_out,
        oom_killed=oom_killed == "true",
        exit_code=int(exit_code),
    )
    mapped = 0 if outcomes is None else sum(v != "missing" for v in outcomes.values())
    return {
        "deterministic": {
            "status": status,
            "exit_code": int(exit_code),
            "oom_killed": oom_killed == "true",
            "network_mode": network_mode,
            "head": _first(markers, "VELITH_HEAD"),
            "parent": _first(markers, "VELITH_PARENT"),
            "tampered": "VELITH_TAMPERED" in markers,
            "removed": sorted(markers.get("VELITH_REMOVED", [])),
            "surface": markers.get("VELITH_SURFACE", []),
            "pytest_exit": _first(markers, "VELITH_PYTEST_EXIT"),
            "net_probe": _first(markers, "VELITH_NET"),
            "collection_failures": collection_failures,
            "mapped_required": mapped,
            "outcomes": outcomes,
        },
        "diagnostics": {"container": container, "duration_seconds": duration},
    }


def classify(
    spec: dict[str, Any], baseline: dict[str, Any], candidate: dict[str, Any]
) -> tuple[str, str, str]:
    """Baseline control first: the candidate is only judged in a proven-healthy env."""
    fail_to_pass = list(spec["fail_to_pass"])
    pass_to_pass = list(spec["pass_to_pass"])
    required = [*fail_to_pass, *pass_to_pass]
    base = baseline["deterministic"]
    if base["status"] != "RAN":
        return INFRA_ERROR, "BASELINE_" + base["status"], ""
    base_outcomes = base["outcomes"]
    if base_outcomes is None:
        return INFRA_ERROR, "BASELINE_UNHEALTHY", "no_junit_result"
    base_missing = [test for test in required if base_outcomes[test] == "missing"]
    if base_missing and base["collection_failures"] == 0:
        return INFRA_ERROR, "RESULT_MAPPING", f"{len(base_missing)} required ids unmapped"
    if any(base_outcomes[test] != "passed" for test in pass_to_pass):
        return INFRA_ERROR, "BASELINE_UNHEALTHY", "pass_to_pass_not_passed"
    if any(base_outcomes[test] == "passed" for test in fail_to_pass):
        return INFRA_ERROR, "BASELINE_UNHEALTHY", "fail_to_pass_passed_at_baseline"
    cand = candidate["deterministic"]
    if cand["status"] == "PATCH_APPLY_FAILED":
        return PATCH_APPLY_FAILED, "CANDIDATE_PATCH_DID_NOT_APPLY", ""
    if cand["status"] == "TIMEOUT":
        return FAILED, "CANDIDATE_TIMEOUT", ""
    if cand["status"] == "RESOURCE_KILLED":
        return INFRA_ERROR, "RESOURCE_KILLED", "prototype_only_production_ruling_pending"
    if cand["status"] != "RAN":
        return INFRA_ERROR, "CANDIDATE_" + cand["status"], ""
    cand_outcomes = cand["outcomes"]
    if cand_outcomes is None:
        return FAILED, "RESULT_ABSENT_AFTER_CANDIDATE", ""
    cand_missing = [test for test in required if cand_outcomes[test] == "missing"]
    if cand_missing and cand["collection_failures"] == 0:
        return INFRA_ERROR, "RESULT_MAPPING", f"{len(cand_missing)} required ids unmapped"
    passed = sum(cand_outcomes[test] == "passed" for test in required)
    if passed == len(required):
        return PASSED, "ALL_REQUIRED_PASSED", f"{passed}/{len(required)}"
    return FAILED, "REQUIRED_TESTS_NOT_PASSED", f"{passed}/{len(required)}"


def verdict_projection(
    contract: dict[str, Any], classification: str, reason: str, duration: float
) -> dict[str, Any] | None:
    """Prove the outcome fits the frozen Verdict; INFRA_ERROR is raised, never returned."""
    if classification not in contract["states"]:
        raise ProbeError(f"{classification} is not a frozen VerdictState value -- STOP")
    if classification == INFRA_ERROR:
        return None
    projection = {
        "state": classification,
        "output": reason,
        "secondary_passed": None,
        "flaky": False,
        "duration_seconds": duration,
    }
    if sorted(projection) != sorted(contract["verdict_fields"]):
        raise ProbeError("Verdict field set differs from the frozen contract -- STOP")
    return projection


def _case_inputs(spec: dict[str, Any], case: str) -> tuple[str, bool]:
    gold = str(spec["patch"])
    if case == "B":
        return neutral_patch(gold), False
    if case == "D0":
        return "", True
    return gold, case == "D"


def _velith_commit() -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def cmd_run(args: argparse.Namespace) -> int:
    spec = load_spec(outside_repo(Path(args.spec)))
    run_dir = outside_repo(Path(args.out_dir)) / (args.run_label or args.case)
    if run_dir.exists():
        raise ProbeError(f"refusing to overwrite {run_dir}")
    if args.case == "C" and not args.fault_cmd:
        raise ProbeError("case C requires --fault-cmd")
    run_dir.mkdir(parents=True)
    contract = read_frozen_contract()
    candidate_patch, tamper = _case_inputs(spec, args.case)
    limits = {
        "memory": args.memory,
        "cpus": args.cpus,
        "pids": args.pids,
        "timeout_seconds": args.timeout,
    }
    image_ok, image_id, image_detail = verify_image(spec)
    baseline: dict[str, Any] | None = None
    candidate: dict[str, Any] | None = None
    if image_ok:
        shared = {"env": contract["env"], "limits": limits, "workdir": run_dir}
        baseline = run_container(
            spec,
            role="baseline",
            candidate_patch="",
            tamper=False,
            fault_cmd=args.fault_cmd,
            **shared,
        )
        candidate = run_container(
            spec,
            role="candidate",
            candidate_patch=candidate_patch,
            tamper=tamper,
            fault_cmd=args.fault_cmd,
            **shared,
        )
        classification, reason, detail = classify(spec, baseline, candidate)
    else:
        classification, reason, detail = INFRA_ERROR, "IMAGE_IDENTITY_MISMATCH", image_detail
    duration = 0.0
    if candidate is not None:
        duration = float(candidate["diagnostics"].get("duration_seconds", 0.0))
    protected = list(spec["protected_paths"])
    evidence = {
        "note": "M2 container prototype feasibility evidence -- NOT a verdict of record",
        "deterministic": {
            "instance_id": spec["instance_id"],
            "repo": spec["repo"],
            "base_commit": spec["base_commit"],
            "image": spec["image"],
            "digest": spec["digest"],
            "platform": spec["platform"],
            "image_id": image_id,
            "case": args.case,
            "candidate_patch_sha256": sha256_text(candidate_patch),
            "test_patch_sha256": sha256_text(spec["test_patch"]),
            "protected_paths": protected,
            "protected_set_sha256": sha256_text("\n".join(protected)),
            "test_argv": test_argv(spec),
            "deterministic_env": contract["env"],
            "limits": limits,
            "fault_cmd": args.fault_cmd,
            "tamper": tamper,
            "velith_commit": _velith_commit(),
            "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "baseline": None if baseline is None else baseline["deterministic"],
            "candidate": None if candidate is None else candidate["deterministic"],
            "classification": classification,
            "reason": reason,
            "detail": detail,
        },
        "diagnostics": {
            "baseline": None if baseline is None else baseline["diagnostics"],
            "candidate": None if candidate is None else candidate["diagnostics"],
        },
        "verdict_projection": verdict_projection(contract, classification, reason, duration),
        "production_mapping": (
            "INFRA_ERROR is raised as SandboxExecutionError, never returned"
            if classification == INFRA_ERROR
            else "returned as the frozen Verdict (see verdict_projection)"
        ),
    }
    evidence_file = run_dir / "evidence.json"
    evidence_file.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", "utf-8")
    summary = {
        "case": args.case,
        "classification": classification,
        "reason": reason,
        "detail": detail,
        "evidence": str(evidence_file),
    }
    print(json.dumps(summary, indent=2))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    first = json.loads(Path(args.first).read_text(encoding="utf-8"))["deterministic"]
    second = json.loads(Path(args.second).read_text(encoding="utf-8"))["deterministic"]
    differing = sorted(
        key for key in first.keys() | second.keys() if first.get(key) != second.get(key)
    )
    print(json.dumps({"identical": not differing, "differing_fields": differing}, indent=2))
    return 0 if not differing else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="M2 container verifier feasibility probe")
    commands = parser.add_subparsers(dest="command", required=True)

    fetch = commands.add_parser("fetch-spec", help="write a task spec outside the repo")
    fetch.add_argument("--instance", required=True)
    fetch.add_argument("--out", required=True)
    fetch.add_argument("--dataset", default="SWE-bench/SWE-bench_Verified")
    fetch.add_argument("--image", required=True)
    fetch.add_argument("--digest", required=True)
    fetch.add_argument("--platform", required=True)
    fetch.add_argument("--repo-dir", required=True)
    fetch.add_argument("--python", required=True)
    fetch.add_argument("--protected-config", action="append", default=[])
    fetch.set_defaults(handler=cmd_fetch_spec)

    run = commands.add_parser("run", help="run one acceptance case")
    run.add_argument("--spec", required=True)
    run.add_argument("--case", required=True, choices=("A", "B", "C", "D", "D0", "E"))
    run.add_argument("--out-dir", required=True)
    run.add_argument("--run-label")
    run.add_argument("--fault-cmd")
    run.add_argument("--memory", default="4g")
    run.add_argument("--cpus", default="2")
    run.add_argument("--pids", type=int, default=512)
    run.add_argument("--timeout", type=float, default=900.0)
    run.set_defaults(handler=cmd_run)

    compare = commands.add_parser("compare", help="compare two runs' deterministic evidence")
    compare.add_argument("first")
    compare.add_argument("second")
    compare.set_defaults(handler=cmd_compare)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except ProbeError as exc:
        print(f"probe error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
