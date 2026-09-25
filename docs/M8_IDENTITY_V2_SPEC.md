# M8_IDENTITY_V2_SPEC — M8 evaluation identity v2 (successor specification)

**Project:** Velith
**Milestone:** M8 evaluation identity v2 — successor to the M8 v1 evaluation identity only.
**Document type:** Engineering contract — **identity architecture only**. It contains no implementation, no code, no commit plan, and no migration procedure. Once frozen it is immutable. The v2 implementation is extracted from it and never redesigns it.
**Status:** FROZEN — M8 identity v2 is frozen at the authorized repository governance commit that introduces this file, tagged `m8-identity-v2-frozen`. Immutable; the v2 implementation is extracted from this specification and never redesigns it.
**Drafted:** 2026-09-26. **Freeze:** the authorized repository governance commit that introduces this file (freeze date = that commit's date). **Freeze tag:** `m8-identity-v2-frozen` (points to that commit).
**Governing decision:** D29 (`docs/DECISIONS.md`). Also governed by D8, D18, D26, D27, D28.
**Source specification:** `M2-PV-R3_M8-M9-M10_IDENTITY_AMENDMENT_SPEC.md`, SHA-256 `d2c51ec15aa00f1c5924ea6aaed8e6de3f7ba286bfc27b5860b5d792b375888a`.
**Engineering baseline:** `b14d918f14d4b5bdfab6fb916811320a742eafa3`.

---

## 1. Scope and supersession

1. This specification **supersedes only the evaluation-identity portion of M8 v1**: `EvaluationProvenance` and its identity (M8_SPEC §3.5). It applies to evaluations created **after** its freeze.
2. Everything else in M8 v1 remains governed by M8 v1, unchanged:
   - checkpoint (§3.1);
   - held-out evaluation set (§3.2);
   - context assembly and attempt harness (§3.3);
   - segregated record and sink (§3.4);
   - the runner's sweep, cost guard and write order.

   The one addition is the consistency check in §7.
3. **M8 v1 is immutable.** `docs/M8_SPEC.md`, as committed at `49d9f75` and certified at `m8-complete` (`fe2b3d7`), is the historical frozen specification of the completed M8 implementation. It is not edited. v1 identities are never edited, rehashed or reinterpreted, and remain reproducible by executing the v1 code at `b14d918`.
4. The "Status: DRAFT" header of `docs/M8_SPEC.md` is a stale label, contradicted by the freeze commit, the implementation handoff ("extracted from `docs/M8_SPEC.md` (frozen)"), the `m8-complete` tag and `PROJECT_STATE.md`. This specification does not correct it; that is a separate, explicitly authorized documentation task.

## 2. Terms

| Term | Meaning |
|---|---|
| `task_identity` | SHA-256 of a task's UTF-8 `material` (M4; unchanged) |
| TaskSpec digest | Content address of a task's verification contract, carried in `CorpusTask.handle` (D28 Option D) |
| `manifest_hash` | **Existing** full-corpus partition manifest hash: SHA-256 over the sorted `task_identity → partition` of every task, available and held-out (M4; unchanged; **not renamed**) |
| Held-out evaluation population `Π` | The tasks of the `HeldOutEvaluationSet` under evaluation |
| VerificationManifest `VM(Π)` | The mapping `task_identity → TaskSpec digest` over `Π` (§3) |
| `verification_manifest_hash` | SHA-256 of the canonical serialization of `VM(Π)` (§3) |

`manifest_hash` fixes *which tasks and which split*. `verification_manifest_hash` fixes *how each held-out task is verified*. They are distinct and **not interchangeable**. A TaskSpec change leaves `manifest_hash` unchanged, because task identity depends on `material` only.

## 3. VerificationManifest

### 3.1 Population (held-out-only)
**The VerificationManifest is held-out-only.** `Π` is exactly the held-out evaluation population. Available-partition tasks are **not** included, and the VerificationManifest is never part of any available-task identity.

### 3.2 Canonicalization
The existing repository convention is reused, with no new format:
- **Serialization:** `json.dumps(VM, sort_keys=True, ensure_ascii=False, separators=(",", ":"))`, the rule of `compute_content_hash` (`src/velith/episodes/episode.py`), the corpus manifest, `EvaluationProvenance` and `PreRegistration`.
- **Sorting:** by `task_identity`, ascending code-point order (`sort_keys=True`).
- **Encoding:** UTF-8.
- **Hash:** SHA-256, lowercase hex.
- **Result:** `verification_manifest_hash = compute_content_hash(VM(Π))`.

### 3.3 Construction rules (fail closed)

| Condition | Behavior |
|---|---|
| Empty population (`Π = ∅`) | **Reject** with `VerificationManifestError`. A construction-time rule, distinct from and not altering M9 OED-7 (`n = 0` after complete-case exclusion → VOID). |
| Duplicate `task_identity`, same digest | **Reject** |
| Duplicate `task_identity`, different digests | **Reject** |
| Missing TaskSpec for a task in `Π` | **Reject** |
| Invalid digest (not `^[0-9a-f]{64}$`) | **Reject** |
| TaskSpec content does not re-hash to its digest | **Reject** (D28 fail-closed) |

## 4. Evaluation identity v2

### 4.1 Payload
The hashed `EvaluationProvenance` payload (v2) has exactly ten keys:

| Key | Status | Meaning |
|---|---|---|
| `identity_version` | **new**, constant `"m8-evaluation-identity-v2"` | Version discriminator; M8 v1 has none |
| `checkpoint_identity` | unchanged | Content-addressed checkpoint identity |
| `manifest_hash` | unchanged | Full-corpus partition manifest hash (§2) |
| `arm` | unchanged | A0, A1 or A2 |
| `base_model` | unchanged | Base model identifier |
| `eval_seed` | unchanged | Evaluation seed |
| `max_tasks` | unchanged | Cost guard |
| `max_attempts_per_task` | unchanged | Cost guard |
| `max_tokens` | unchanged | Cost guard |
| `verification_manifest_hash` | **new** | SHA-256 of `VM(Π)` (§3) |

### 4.2 Identity
```
EvaluationIdentity_v2 = SHA256_hex( UTF8( json.dumps(payload_v2, sort_keys=True,
                                              ensure_ascii=False, separators=(",", ":")) ) )
```
This is the same canonical rule as v1. The hash boundary is the full ten-key payload. `identity_version` is **inside** it.

### 4.3 Distinctness from v1
- v1 and v2 payloads always differ: in key set (`identity_version` and `verification_manifest_hash` exist only in v2) and in explicit version value.
- Their identities therefore differ, except with negligible probability under the standard SHA-256 collision-resistance assumption.

## 5. EvaluationRecord and analysis provenance

- **`EvaluationRecord` is unchanged.** `evaluation_identity` carries the v2 binding by hash inclusion: a different VerificationManifest yields a different identity, except with negligible collision probability.
- **`AnalysisProvenance` is unchanged.** It carries no plaintext `verification_manifest_hash`; the pre-registration identity and the evaluation identities cover it.

## 6. Classifier identity and available-task lineage

1. **Classifier identity is excluded.** D27 classifier identity (Velith commit, lock hash, interpreter version) enters **neither** `EvaluationProvenance.identity` nor `PreRegistration.identity`. It is recorded in verification evidence. One evaluation of record (every arm and checkpoint under one pre-registration) runs under **one** classifier identity, enforced through the evidence ledger. A classifier change is detectable at audit level, not identity level.
2. **Available-task TaskSpec lineage is deferred, not solved.** It remains an M2-PV provenance concern. Available-task verification reaches evaluation identity only through memory content, via `checkpoint_identity` (the SHA-256 over sorted memory-episode content hashes). An available-task TaskSpec change that leaves every memory episode byte-identical is **not** reflected in any identity. This specification does not close that gap.

## 7. Consistency check (M8 runner)

Before the first attempt of an evaluation, the runner must:
1. require `provenance.identity_version == "m8-evaluation-identity-v2"`;
2. construct `VM(Π)` from the held-out evaluation set under §3.3;
3. require `provenance.verification_manifest_hash == compute_content_hash(VM(Π))`.

In addition, the existing v1 checks remain: checkpoint identity, `manifest_hash` and arm.

| Case | Behavior |
|---|---|
| Match | Proceed; the sweep is unchanged |
| Mismatch | `EvaluationError`; no attempt, no record |
| Missing TaskSpec | `EvaluationError` |
| Changed TaskSpec (content ≠ digest) | `EvaluationError` |
| Missing task / extra task | Hash mismatch → `EvaluationError` |
| Duplicate task identity | `EvaluationError` |
| `identity_version` not v2 | `EvaluationError` |

All checks precede the first attempt, so no partial record is written.

## 8. Coordinated M9/M10 binding (one identity migration)

M8 identity v2, the M9 pre-registration amendment (`m9-spec-frozen-oed7-vm2`, Amendment VM2 in `docs/M9_SPEC.md`) and the M10 reconstruction amendment are **one identity migration**. They must be specified, frozen and implemented together.

### 8.1 M9
- `PreRegistration` gains `verification_manifest_hash`, with the same 64-hex validation as `manifest_hash`, and carries `spec_version = "m9-spec-frozen-oed7-vm2"`.
- Every other pre-registration field and analysis-plan constant is unchanged.
- `PreRegistration` does **not** store `identity_version`. A pre-registration whose `spec_version` is `"m9-spec-frozen-oed7-vm2"` is reconstructed **only** into identity-v2 provenance (`identity_version = "m8-evaluation-identity-v2"`).

### 8.2 M10 reconstruction requirements
There is no separate M10 specification document at baseline; M10 is governed by its handoff and the code at `e04d7f9`. Its reconstruction requirements are therefore stated here:
1. Both reconstruction sites build the v2 provenance from the pre-registration: `src/velith/analysis/binder.py` (`_provenance_identity`) and `src/velith/analysis/executor.py` (`_provenance_identity`). The whole-repository search at baseline found no other reconstruction site. Both are required to change in the same change set.
2. Each reconstruction passes the eight unchanged components from the pre-registration (with `checkpoint_identity` from the schedule, or from the supplied A0 empty-checkpoint identity), `verification_manifest_hash = preregistration.verification_manifest_hash`, and `identity_version = "m8-evaluation-identity-v2"`.
3. The executor pre-flight additionally refuses any pre-registration whose `spec_version` is not `"m9-spec-frozen-oed7-vm2"`.
4. A record binds iff its `evaluation_identity` is in the reconstructed expected set. Under the standard SHA-256 collision-resistance assumption, binding implies, except with negligible probability, equality of all ten payload components.

### 8.3 Mixed-version joins (rejected)

| Combination | Result |
|---|---|
| v1 pre-registration with v2 code | **Reject:** fails v2 validation; pre-flight `spec_version` check |
| v2 pre-registration with v1 records | **Reject:** v1 identities are not in the v2 expected set |
| v1 pre-registration with v2 records | **Reject:** v1 code rejects the v2 pre-registration (`extra="forbid"`); v2 identities are not in the v1 expected set |
| v2 with v2, different VerificationManifest | **Reject:** identities differ |

## 9. Fixtures (universal v2 path)

There is one v2 identity path for every evaluation, real or synthetic. Fixture corpora whose handles are not 64-hex digests (at baseline: `"fixture-fits"`, `"meshes-clean"`, `"clears-envelope"` in `tests/fixtures/corpus_min/corpus.json`) supply deterministic synthetic 64-hex digest handles, a test-data change only. No dual v1/v2 code path exists.

## 10. Migration policy

- No real M8 evaluation, M9 pre-registration or M10 analysis artifact exists in the repository (verified at `b14d918`).
- Therefore: **no migration procedure, no rehashing, no v1→v2 conversion.** v1 remains historical.
- Every evaluation of record created after the v2 freeze uses identity v2.

## 11. Unchanged (explicit)

- **M9 statistical formulas and decision rules:** outcome encoding (PASSED = 1, else 0), complete-case handling, global-incomplete VOID, OED-7 empty-dataset VOID, GEE, EMM, Wald inference, McNemar (K = 1), Holm correction, α = 0.01, the decision rule, and A0 time-invariance (OED-2). This specification changes identity and version plumbing, not statistical inference. The future implementation must leave the M9 statistics semantically and byte-for-byte unchanged.
- **Also unchanged:** checkpoint identity; the corpus manifest and `manifest_hash`; task identity; `EvaluationRecord`; `AnalysisProvenance`; A0/A1/A2 semantics; the attempt harness; M8 v1.

## 12. Identity acceptance cases (specification-level)

**These cases are a design/adversarial audit, not execution evidence.** "Specification-level PASS" means this specification, as written, determines the stated outcome through a traceable mechanism; hash-distinctness cases are conditional on SHA-256 collision resistance. **None is implementation-validated; no implementation exists.** All 18 become implementation acceptance tests.

| # | Case | Expected | Specification-level | Implementation-validated |
|---|---|---|---|---|
| 1 | Same evaluation, same TaskSpecs | Same identity | PASS (spec-level) | NOT VALIDATED |
| 2 | Changed image digest in one held-out TaskSpec | Different identity | PASS (spec-level) | NOT VALIDATED |
| 3 | Changed protected-surface inputs | Different identity | PASS (spec-level) | NOT VALIDATED |
| 4 | Changed test command / required tests | Different identity | PASS (spec-level) | NOT VALIDATED |
| 5 | Changed runner or config digest | Different identity | PASS (spec-level) | NOT VALIDATED |
| 6 | Changed held-out population | Different identity | PASS (spec-level) | NOT VALIDATED |
| 7 | Changed arm | Different identity | PASS (spec-level) | NOT VALIDATED |
| 8 | Changed checkpoint | Different identity | PASS (spec-level) | NOT VALIDATED |
| 9 | Changed evaluation seed | Different identity | PASS (spec-level) | NOT VALIDATED |
| 10 | Changed cost guard (any of three fields) | Different identity | PASS (spec-level) | NOT VALIDATED |
| 11 | v1 pre-registration + v2 evaluation | Reject | PASS (spec-level) | NOT VALIDATED |
| 12 | v2 pre-registration + v1 evaluation | Reject | PASS (spec-level) | NOT VALIDATED |
| 13 | Missing / empty VerificationManifest | Reject | PASS (spec-level) | NOT VALIDATED |
| 14 | Mismatched `verification_manifest_hash` | Reject before any attempt | PASS (spec-level) | NOT VALIDATED |
| 15 | Duplicate task identity, same digest | Reject | PASS (spec-level) | NOT VALIDATED |
| 16 | Duplicate task identity, different digests | Reject | PASS (spec-level) | NOT VALIDATED |
| 17 | Available-task TaskSpec change, memory unchanged | Same identity. This is the intended held-out-only boundary, **not** a claim that available-task lineage is solved (§6.2) | PASS (spec-level, per held-out-only boundary) | NOT VALIDATED |
| 18 | Different classifier version, all else equal | Same identity; the change is detectable only via the evidence ledger | PASS (spec-level, per classifier exclusion) | NOT VALIDATED |

## 13. Not claimed

This specification does not claim:
- that identity binding establishes correctness of verdicts;
- absence of result-channel forgery or semantic manipulation (accepted residuals E12/E13, governed by M2-PV);
- container-escape resistance;
- cross-machine determinism (an M2-PV acceptance requirement);
- closure of available-task lineage.

## 14. Freeze procedure

1. Ratification of this text together with its companions: the DECISIONS entry D29 and the M9 amendment block `m9-spec-frozen-oed7-vm2`.
2. A separate authorization to place the three artifacts in the repository. Proposed location for this document: `docs/M8_IDENTITY_V2_SPEC.md`, alongside the untouched `docs/M8_SPEC.md`. Then commit, then tag `m8-identity-v2-frozen`.
3. Only then, a separately authorized implementation handoff for the coordinated M8/M9/M10 migration.

*End of M8_IDENTITY_V2_SPEC — proposed amendment text.*
