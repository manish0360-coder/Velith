# Velith Engineering API v0 — Specification

**Status:** Ratified by the Research Director (spec r4 + ID-1, 2026-10-30); recorded as **D33**.
**Milestone:** API-0 — outside the M-sequence; software domain only.
**Owner:** Velith (Layer 3). **Consumer:** Mini Prometheus (Layer 4).
**Governs:** `src/velith/api/`. Frozen M1–M9 behavior is not changed by anything here.

Labels: **[PROVEN]** = observed in code or command output at ratification;
**[ASSUMED]**; **[UNRESOLVED]**.

---

## 0. Decision register

| ID | Decision |
|---|---|
| D33 | Engineering API v0: software domain only, outside the M-sequence. Velith owns `EngineeringTask`, `EngineeringResult`, `DesignArtifact`. |
| VER | Velith version `0.1.0`, git tag `v0.1.0`, distributed by git tag only (no package index). Applied in C3. |
| WIRE | The wire object is exactly the five fields of Mini Prometheus' consumed stub. That schema is not changed or expanded. |
| ID-B | Identity view = wire object minus `{result_id, content_hash}`, plus `identity_version`; canonical JSON → SHA-256 → `sha256:` prefix; `result_id = uuid5(NS_VELITH_API, content_hash)`. |
| ID-1 | `result_id`/`content_hash` identify the **deterministic content claim and its artifact**, not a verification run or a local record. Separate runs may share both while keeping distinct local records. |
| CONST | `IDENTITY_VERSION`, `NS_VELITH_API`, media type (§3.1). |
| VEC | T1–T3, T4-B, T5a, T5b (§3.7) are normative. |
| SEC | §4 wording. |
| RULE | Strict public verification rule (§2), deliberately stricter than the frozen M7 rule; M7 unchanged. |
| EVID | Evidence and provenance stay off the wire; full records are kept locally (§6.2). |
| MP-CONST | Mini Prometheus keeps its own pinned copies of `IDENTITY_VERSION` and `NS_VELITH_API` and never imports Velith for its identity check; the shared vectors verify agreement. |
| PY | Velith keeps `requires-python = "==3.12.*"`. |
| DEMO | Software-only demo; no call into any manufacturing pipeline. |
| GUARD | A Mini Prometheus media-type guard is mandatory before RM6 integration. |
| FROZEN | M1–M9 frozen; SFG **DEFERRED, NOT VERIFIED**; physical/manufacturing claims closed under D5/D12/D31. |

---

## 1. Scope and types

- Ownership: Velith (D30 §1). Mini Prometheus' stub
  `contracts/schemas/consumed/velith/engineering_result.schema.json` (contracts 0.4.0) is a pinned
  consumer copy and stays unchanged.
- `velith.api` imports pinned `noetica` 1.0.0 and frozen Velith domain types only. It never imports
  `mini_prometheus`, `miniflywire` or `velith.analysis` (D30 §4).

| Type | Fields | Notes |
|---|---|---|
| `EngineeringTask` | `task_id` (non-empty), `domain: Literal["software"]` | In-process only; no wire form (TaskSpec schema undecided, D26). v0 resolves only `calc_add_bug` (C2). |
| `DesignArtifact` | `media_type` (closed: `application/vnd.velith.swe-patch+json`), `payload` | `payload = {artifact_schema_version:"0.1.0", domain:"software", task_id, patch:{format:"unified_diff", text}}`. `content_hash` and `artifact_id` are derived. The payload is the design only, never the claim. |
| `EngineeringResult` (producer) | wire: `result_id`, `content_hash`, `verified: true`, `verifier {component, version}`, `design_artifact {media_type, ref, content_hash}`; local: `task_id`, `evidence`, `provenance` | |
| `UnverifiedOutcome` | `task_id`, `verdict`, `reason` | `reason` ∈ `VERDICT_NOT_PASSED`, `FLAKY`, `SECONDARY_FAILED`, `SECONDARY_ABSENT`, `ISOLATION_DISABLED`, `INSUFFICIENT_RERUNS` (precedence in that order). Never on the wire. |
| `ReceivedEngineeringResult` | the five wire fields | Built by `from_wire()`. A claim as received; never upgraded to a producer-side result. |

Unsupported in v0: a portable task wire format; LLM proposal; any non-software domain; signatures;
evidence transmission.

---

## 2. Verification rule

`verified` holds only if, for one `VerifierSandbox.verify(task, patch)`
(`harness/verifier_sandbox.py`):

1. `state == PASSED`;
2. `flaky is False`, with `flake_rerun_count ≥ 2` (default 3, `core/config.py`);
3. `secondary_passed is True`;
4. `verifier_network_isolation is True` (default, `core/config.py`).

Otherwise the result is an `UnverifiedOutcome` with the first failing reason.

**Divergence from M7 (deliberate).** The frozen `is_verified_success` (`arms/filters.py`) accepts
`secondary_passed is None`. The public rule rejects it. M7 is not changed. `_run_secondary` returns
`None` exactly when `not task.secondary_test_command` [PROVEN]; such a task gets
`UnverifiedOutcome(SECONDARY_ABSENT)` from the API while M7 counts the same verdict as a verified
success. This is the documented divergence, not a contradiction. Tasks with no secondary suite
cannot produce a public result in v0.

**Accepted limitation.** The secondary suite runs once, with no flake detection [PROVEN].

**No hardcoded claim.** The only producer path is `result_from_verification(...)`, returning
`EngineeringResult | UnverifiedOutcome`; `verified` is never a parameter. A validator re-applies the
rule to `evidence`, so a result whose recorded evidence fails it cannot be built. This does not stop
in-process code from fabricating evidence values.

---

## 3. Option B identity

### 3.1 Constants

- `IDENTITY_VERSION = "velith-engineering-result-identity-v1"`
- `NS_VELITH_API = 924036ea-946e-57d4-9a75-e94278f979aa`
  = `uuid5(NAMESPACE_URL, "https://github.com/manish0360-coder/Velith#engineering-api")`
- `MEDIA_TYPE_SWE_PATCH = "application/vnd.velith.swe-patch+json"`

### 3.2 Identity-view fields

| Path | Type | Source | Constraint |
|---|---|---|---|
| `identity_version` | string | contract constant, not on the wire | equals `IDENTITY_VERSION` |
| `verified` | boolean | wire | `true` |
| `verifier.component` | string | wire | non-empty (v0: `velith-swe-verifier`) |
| `verifier.version` | string | wire | `^(0\|[1-9]\d*)\.(0\|[1-9]\d*)\.(0\|[1-9]\d*)$` |
| `design_artifact.media_type` | string | wire | non-empty |
| `design_artifact.ref` | string | wire | lowercase hyphenated UUID (`str(uuid.UUID)`) |
| `design_artifact.content_hash` | string | wire | `^sha256:[0-9a-f]{64}$` |

ASCII keys only; no numbers, floats or nulls; every leaf a string except `verified`.

### 3.3 Excluded fields

| Field | Reason |
|---|---|
| `content_hash` | the output; self-referential |
| `result_id` | derived from `content_hash`; circular |
| `task_id` | not on the wire; bound indirectly through the artifact payload, checkable only by a payload holder |
| `evidence` | not on the wire; nearly constant under §2; kept in the local record |
| `provenance` | not on the wire; volatile (D16.1/D21) |

### 3.4 Procedure

`IDENTITY_VERSION` is a domain-separation tag taken by each side from its pinned contract; never
transmitted. A changed identity rule means a new version and a new hash lineage. On a mismatch the
consumer rejects; it never tries other versions.

1. Build the view; reject forbidden value types.
2. `s = json.dumps(view, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.
3. UTF-8 encode; SHA-256; `"sha256:"` + lowercase hex.

Producer: `"sha256:" + noetica.provenance.identity.canonical_sha256(view)`. Consumer:
`mini_prometheus._hashing.content_hash(view)` or a byte-equivalent copy. Equivalent on every vector
[PROVEN].

### 3.5 Derivation order (no cycles)

1. `artifact_hash = "sha256:" + canonical_sha256(payload)`
2. `ref = str(uuid5(NS_VELITH_API, artifact_hash))`
3. assemble the view
4. `content_hash = H(view)`
5. `result_id = str(uuid5(NS_VELITH_API, content_hash))`

The uuid5 name is the full prefixed string, UTF-8. Identical patch, task and Velith version give an
identical identity (ID-1).

### 3.6 Consumer check

Mini Prometheus keeps its own literal copies of `IDENTITY_VERSION` and `NS_VELITH_API`; it does not
import `velith` for this check.

1. Validate `W` against the stub (Draft 2020-12) and parse both UUIDs explicitly (Mini Prometheus'
   `_validate` checks neither UUID format nor `engineering_result` [PROVEN]).
2. `H(identity_view(W)) == W.content_hash`
3. `str(uuid5(NS, W.content_hash)) == W.result_id`
4. `str(uuid5(NS, W.design_artifact.content_hash)) == W.design_artifact.ref`

### 3.7 Shared test vectors (normative; pinned in `tests/unit/test_api_vectors.py`)

| ID | Input | Expected |
|---|---|---|
| T1 | `{}` | `sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a` |
| T2 (serializer only) | `{"z":"naïve—Δ","a":[1,2,{"y":null,"b":false}],"m":"line\nbreak\t\"q\"\\"}` | `sha256:a338311feee0b463f81a46a0e8b1438289f18a4638ea0579eda98be18be0f624` |
| T3 | `{"artifact_schema_version":"0.1.0","domain":"software","patch":{"format":"unified_diff","text":"--- a/calculator.py\n+++ b/calculator.py\n@@ -1,3 +1,3 @@\n # mypy: ignore-errors\n def add(a: int, b: int) -> int:\n-    return a - b\n+    return a + b\n"},"task_id":"calc_add_bug"}` | `sha256:ff39e80e72505b345d649cb5254e242490db0bf3ca67bcaed50d3274e11cae95` |
| T5a | `uuid5(NS, T3)` | `cdf5e4da-da47-5e52-b845-448ab5cc6bb1` |
| T4-B | `{"design_artifact":{"content_hash":"sha256:ff39e80e72505b345d649cb5254e242490db0bf3ca67bcaed50d3274e11cae95","media_type":"application/vnd.velith.swe-patch+json","ref":"cdf5e4da-da47-5e52-b845-448ab5cc6bb1"},"identity_version":"velith-engineering-result-identity-v1","verified":true,"verifier":{"component":"velith-swe-verifier","version":"0.1.0"}}` | `sha256:6c2babe95dfa51f142494ef7633322d68eed8983a775faa048f1060cee0317a0` |
| T5b | `uuid5(NS, T4-B)` | `2ac44842-2b16-5dbe-ae75-028dd4d44a26` |

### 3.8 What the hash binds

It binds `verified`, `verifier`, and the artifact's `media_type`, `ref` and `content_hash` strings,
under the identity version. It does **not** expose, validate or retrieve the artifact payload; a
consumer without the payload can neither check it against `content_hash` nor see its `task_id`.

---

## 4. Hash security

Recomputing the hash detects accidental corruption and changes to covered fields made **without**
recomputing the hash and ids. The algorithm and constants are public: anyone who can modify the wire
object can recompute `content_hash`, `result_id` and `ref` consistently, and the check will pass. It
never covers the excluded fields, nor the artifact payload unless the consumer holds it. It does
**not** establish authenticity, non-repudiation (no signature or key), or that verification
occurred: `verified: true` is a covered value, not evidence of an event. Mini Prometheus receives a
**trusted assertion** by the named verifier; trust rests on the channel and the producer.

---

## 5. Python and packaging

- Velith requires `==3.12.*`; Mini Prometheus' CI and verifier image use Python 3.11 [PROVEN].
  Mini Prometheus must provide 3.12 before RM6 integration testing. The v0 demo uses a throwaway
  3.12 virtual environment.
- Packaging scope: `noetica @ git+https://github.com/manish0360-coder/Noetica-agent-lab@v1.0.0`
  with `[tool.hatch.metadata] allow-direct-references = true` (C1); `src/velith/py.typed`, version
  `0.1.0`, the wheel gate `tools/verify_installed_wheel.py` modelled on Noetica's (C3); the
  packaged schema `src/velith/api/schemas/engineering_result.v1.schema.json` (C1).

---

## 6. Demo, records, governance

### 6.1 Demo (C4)

1. In Velith's verifier container, the correct `calc_add_bug` patch produces a genuine
   `EngineeringResult` (wire JSON + local full record); the negative patches from
   `tests/integration/test_spike_episode.py` produce `UnverifiedOutcome`.
2. In a throwaway 3.12 virtual environment: validate the wire JSON against Mini Prometheus' stub;
   run the §3.6 check with Mini Prometheus' `_hashing.content_hash` and pinned literal constants,
   without importing `velith`; load the result into
   `contracts/python/consumed/velith/engineering_result_schema.py`.

The demo must not call `from_engineering_result` or `run_from_velith`, nor import
`mini_prometheus.orchestration`, `manufacturing_*` or `integrations`; a static import check enforces
this. It does not demonstrate manufacturing, manufacturability, physical design, signatures, or
evidence audit by Mini Prometheus.

### 6.2 Local records

A dedicated git-ignored directory `data/api_v0/`, separate from `src/`, `tests/`, `docs/` and frozen
evidence including `data/episodes/`. One record per run (wire object + `task_id` + evidence +
provenance), named `<result_id>__<run-utc>.json`, written once and never overwritten. Compose mounts
only `./data/episodes`, so the demo runs with `-v ./data/api_v0:/app/data/api_v0`. The `.gitignore`
entry is added in C4 (today only `/data/episodes/` is ignored [PROVEN]).

### 6.3 Governance

D4/D5 allow the software rung only. Mechanical and manufacturing results stay closed under
D5/D12/D31 until a valid M10 go/no-go or an explicit decision superseding D5/D12. With SFG
**DEFERRED, NOT VERIFIED**, M10 has no valid basis for that decision.

---

## 7. Acceptance

### API v0

- **V1** producer reproduces T1–T3, T4-B, T5a/b via Noetica and asserts the constants.
- **V2** consumer reproduces T4-B/T5b from wire JSON with only Mini Prometheus' hashing, `uuid5` and
  pinned literals (C4).
- **V3** valid wire objects pass the stub and §3.6; a single-field change without recomputation fails.
- **V4** each failing condition maps to its reason (`None` → `SECONDARY_ABSENT`, `False` →
  `SECONDARY_FAILED`); hand-built results with failing evidence are rejected.
- **V5** `VerdictState` ↔ Noetica `VerdictStatus` mapping is total.
- **V6** import boundary holds; the demo's forbidden-import check passes.
- **V7** the Velith gate is green, existing tests unchanged.
- **V8** `git diff --name-only 29fd12f -- src tests` lists only `src/velith/__init__.py` (C3) plus new
  `api/`, `py.typed` and `test_api_*` paths.
- **V9** the wheel gate passes on 3.12 (C3).
- **V10** records land only in `data/api_v0/`, untracked, never overwritten (C4).
- **G1** the Noetica and Velith tags are fetchable from the Docker build, CI and the demo
  environment (implementation-time packaging gate).

### RM6 (future; not part of v0)

R1 Mini Prometheus 3.12 environment with goldens re-verified (gate). R2 media-type guard in
`from_engineering_result` (Mini Prometheus-owned physical-design allowlist; software media types
refused explicitly; negative test). R3 fix the fixture `tests/conftest.py::velith_result`
(`velith-swe-verifier` with `model/step`). R4 pinned literal constants + T4-B/T5b test. R5 adapter
performs §3.6. R6 pin `velith` at `v0.1.0`. R7 a real physical result stays closed by governance.

### Commit plan

C0 docs (this file, D33) · C1 contract core · C2 `SweVerifier` adapter (sandbox verdict →
`VerificationEvidence`) · C3 packaging · C4 demo.

---

## 8. Implementation notes (no contract change)

### C1 — contract core

- `result_from_verification(task, artifact, evidence, *, verifier, provenance)` takes
  `VerificationEvidence`. C2 adds the adapter from a `VerifierSandbox` verdict to evidence; the
  producer path stays this single function.
- `verified` is checked as the JSON boolean `true` before type validation, because `Literal[True]`
  alone admits `1`; the stub's `const: true` does not.
- The packaged schema is self-contained (no `$id`, inlined `$defs`) and constraint-equivalent to the
  stub. Velith has no JSON Schema validator dependency; the schema is checked structurally against
  the code constants (`tests/unit/test_api_contract.py`), and validated with a real validator on
  the Mini Prometheus side (V2, RM6).

### C2 — `SweVerifier` adapter (`src/velith/api/swe.py`)

- **K1 (ratified).** `VerifierSandbox` keeps its isolation flag and rerun count private, and its
  `Verdict` does not record them. `SweVerifier` therefore constructs the sandbox itself and passes
  both values explicitly through the sandbox's public constructor; the evidence reports exactly
  those values. Omitted values are resolved once from `Settings` (`verifier_timeout_seconds`,
  `verifier_network_isolation`, `flake_rerun_count`), the timeout exactly as the frozen spike
  resolves it; explicitly supplied values are kept. A rerun count below 1 is refused. With
  isolation on, the sandbox either runs every test command under `unshare -n` or raises; it never
  runs them unisolated. No private attribute is read and no frozen M2 file is modified.
- **K2 (ratified).** `SandboxExecutionError` propagates (D16.7). An infrastructure fault produces no
  `EngineeringResult`, no `UnverifiedOutcome` and no record. `VERDICT_NOT_PASSED` therefore covers
  only grounded verdicts (`FAILED`, `PATCH_APPLY_FAILED`; `NO_PATCH` is unreachable in v0 because
  `SwePatch.text` is non-empty).
- **Task resolution (K4).** `resolve_task` accepts only `software/calc_add_bug` and resolves the
  fixture under `tests/fixtures` relative to the working directory (or an injected
  `fixtures_root`). `SweVerifier` is therefore usable only where the fixtures exist — the
  repository or the verifier container — and not from an installed wheel alone.
- **Version (K5).** Until C3, `verifier.version` is `velith.__version__ = "0.0.0"`, so a real run
  cannot reproduce T4-B; the integration tests pin the T3 artifact hash and content-identity
  determinism instead.
- **Protocol.** `SweVerifier.verify(task, candidate)` implements Noetica's `Verifier` protocol and
  returns a Noetica `Verdict` with `confidence = 1.0` (exact software oracle) and `flaky`,
  `flake_rerun_count`, `secondary_passed` and `network_isolated` in `detail` (Law 16).
- **Provenance (local only).** `source = "velith-swe-verifier"`,
  `transform = "velith.harness.VerifierSandbox.verify"`, `inputs = (task_id, artifact content hash)`,
  `attributes = {velith_version, duration_seconds}`.
- **Import boundary.** `velith.api` stays contract-only and does not re-export `swe`; importing it
  loads neither `velith.harness` nor `velith.core.config` (`tests/unit/test_api_swe.py`).
