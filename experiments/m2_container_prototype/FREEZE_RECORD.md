# M2 Container Verifier — Feasibility Freeze Record

Status: **FROZEN — prototype feasibility evidence (CONDITIONAL APPROVAL, conditions satisfied below)**
Date: 2026-09-25
Scope: feasibility experiment only. This record is not a production specification and does not
authorize production implementation. M0–M10 remain frozen.

## 1. Evidence identity

| Item | Value |
|---|---|
| `probe_sha256` | `560834d559fbf1063c7ad33afa675abac59535e45469bc0d9da3e8254f138e1f` |
| `evidence_manifest_sha256` | `30c59a45db9e06556bc0a0529b290d43c7a4163066b3b3a4c138f97eaa6255f7` |
| Probe | `experiments/m2_container_prototype/probe.py` |
| Velith commit at execution | `e04d7f90a742a3c6278a2fd937803abdd1567ac8` |

The evidence (per-case `evidence.json`, container stdout, JUnit reports, and the task
specification) is retained outside the repository. The manifest is the SHA-256 list of
every file under `runs/` plus `flask-5014.json`, produced by:

```
cd ~/velith-prototype
find runs flask-5014.json -type f -print0 | sort -z | xargs -0 sha256sum > evidence-manifest.sha256
sha256sum evidence-manifest.sha256
```

No benchmark data is stored in the repository.

## 2. Environment

| Item | Value |
|---|---|
| Benchmark instance | `pallets__flask-5014` |
| Image | `swebench/sweb.eval.x86_64.pallets_1776_flask-5014` |
| Pinned digest | `sha256:eaf597005c159361cb8ee26018fb3741b320f331065f0c95726d83ccf2f1fba4` |
| Platform | `linux/amd64` |
| Repository | `/testbed` |
| Base commit | `7ee9ceb71e868944a46e1ff00b506772a53a4f1d` |
| Image HEAD | `966bb873e3a1e42d857362a17f5af2533dfd8f46` (`HEAD^1 == base_commit` confirmed) |
| Environment | `/opt/miniconda3/envs/testbed` |
| Python / pytest | 3.11.10 / 7.3.0 |
| Network | `none` |

## 3. Results

| Case | Description | Outcome |
|---|---|---|
| A | gold patch | PASSED 60/60 |
| B | behavior-neutral non-fix patch | FAILED 59/60 — exactly the FAIL_TO_PASS test failed |
| C | environment fault (Werkzeug removed) in both containers | INFRA_ERROR / BASELINE_UNHEALTHY / no JUnit result |
| D | gold patch + test/configuration tampering | PASSED 60/60 — tampering neutralized |
| D0 | tampering without fix | FAILED 59/60 — exactly the FAIL_TO_PASS test failed |
| E | network isolation | PASSED 60/60; `network_mode=none`; outbound probe blocked (`OSError 101`) |
| F1 / F2 | repeat of A | PASSED 60/60 each; deterministic comparison identical (`differing_fields=[]`) |

Cross-case evidence audit: `RESULT: ALL CHECKS OK`.
Determinism comparisons: A vs F1, A vs F2, F1 vs F2 identical; A vs E identical excluding the
case label.

## 4. Demonstrated

1. Sealed, digest-pinned, network-less execution of one real repository-level task.
2. Baseline control separates environment faults built into the tested image from candidate
   failure for the tested cases.
3. Correct PASSED, FAILED and INFRA_ERROR outcomes for the exercised paths.
4. The listed file-level tampering methods are neutralized.
5. Repeated outcomes are reproducible on one host.

## 5. Exact scope

- Task: `pallets__flask-5014`
- Required tests: 1 FAIL_TO_PASS + 59 PASS_TO_PASS = 60 (dataset-declared; all 60 IDs present
  in the JUnit report)
- D/D0 tampering scope:
  - `tests/test_blueprints.py`
  - `pyproject.toml`
  - `tox.ini`
  - `tests/conftest.py`
  - candidate-added `pytest.ini` / `.pytest.ini` / `setup.cfg` / `conftest.py` in the tested
    surface

## 6. Not demonstrated

- anything beyond this task;
- candidate-only infrastructure faults;
- candidate code manipulating pytest/JUnit during execution;
- `pytest.py`/import-path hijacking;
- general official-harness fidelity;
- timeout semantics;
- OOM semantics;
- cross-host reproducibility;
- real-container malicious-control effectiveness beyond the tested removal/hash evidence;
- generalization to other repositories, tasks, or test frameworks.

## 7. Limitations carried forward (L1–L12, as established by the Scientific Review)

- **L1 candidate-only faults** — a one-off infrastructure fault in the candidate run alone is
  scored as candidate FAILED.
- **L2 timeout/OOM** — candidate-only timeout (FAILED) and OOM (INFRA_ERROR) have no ruling
  and never occurred in the real runs.
- **L3 code manipulating pytest during test execution** — candidate code can rewrite pytest
  behavior or the JUnit report while tests run.
- **L4 import-path hijacking** — `python -m pytest` places the repository root first on the
  import path, so a candidate-added `pytest.py` replaces pytest (shown on the host, not in the
  container). Known open hole.
- **L5 protected-set rule** — the protected set was hand-picked; legitimate candidate edits to
  protected files are silently reverted.
- **L6 harness fidelity** — skipping conda activation and using `-m` was validated only for
  this task, by agreement with the dataset labels.
- **L7 tampering control** — the hijack actually changing results was shown only in the mock
  environment.
- **L8 untested verdict paths** — P2P regression, patch-apply failure, timeout and
  result-mapping failure were not exercised in the real container.
- **L9 weak determinism evidence** — one host, n=3, a deterministic suite, no flake handling.
- **L10 scope** — one task, pytest only; tasks with no P2P tests have no baseline health
  signal.
- **L11 trusted labels** — dataset labels are taken as correct; checked per task only through
  the gold patch.
- **L12 self-reported evidence** — evidence markers are printed from inside the candidate's
  container.

## 8. Additional recorded facts

- The environment's Python executable was invoked directly rather than through conda
  activation.
- This was empirically validated only for this task.
- The prototype's candidate-only OOM behavior (INFRA_ERROR) is not a production scientific
  rule.
- M0–M10 remain frozen.

## 9. Scientific Review ruling (preserved verbatim)

**CONDITIONAL APPROVAL**, no rerun and no probe change. Conditions:

1. **Scope in the freeze record.** It must state the lists below word for word, restrict D/D0
   to the tested methods, and list L4 as a known open hole.
2. **Keep the evidence.** Record a SHA-256 manifest of the run folders and the spec together
   with the probe hash, so the evidence stays checkable.
3. **Record the conflict of interest.** At your discretion, have a reviewer who didn't write
   the code (e.g. Gemini) confirm against the retained evidence.

**Demonstrated:**

- Sealed, pinned, network-less execution of one real task.
- The baseline control separates environment faults built into the image from candidate
  failure.
- Correct PASSED, FAILED and INFRA_ERROR verdicts.
- The listed file-level tampering methods are neutralized.
- Outcomes are reproducible on one host.

**Not demonstrated:**

- Anything beyond this task.
- Handling of faults that hit only the candidate run.
- Resistance to code that manipulates pytest while tests run, or to import-path hijacking.
- Fidelity to the official harness in general.
- Correct timeout and OOM verdicts.
- Reproducibility on other hosts.
- The tampering control in the real container.

**Still unresolved for production:** L1–L12, plus the Task contract change and how the
verifier is launched.

**M0–M10:** stay frozen. Nothing here calls for changing them.

**Repository:** once conditions 1 and 2 are met, it may go to a separate commit
authorization, for `probe.py` only.

## 10. Condition status

| Condition | Status |
|---|---|
| 1. Scope in the freeze record | Satisfied by §§4–7 of this record (D/D0 restricted to §5; L4 recorded as a known open hole). |
| 2. Evidence retention | Satisfied: `evidence_manifest_sha256` and `probe_sha256` recorded in §1. |
| 3. Conflict of interest | Recorded: `probe.py`, the evidence-audit script, and the mock controls were written by the same agent that performed the Scientific Review. Non-author confirmation is at the Research Director's discretion; none is recorded here. |
