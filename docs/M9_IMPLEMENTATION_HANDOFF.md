# M9_IMPLEMENTATION_HANDOFF

**Project:** Velith (engineering/design-intelligence layer of MiniFlyWire → Noetica → Velith → Mini Prometheus)
**Milestone:** M9 — pre-registration of the compounding-memory experiment (A0/A1/A2) over the frozen M8 held-out evaluation.
**Document type:** Engineering execution contract. Subordinate to, and must not contradict, the immutable
`m9-spec-frozen` specification and the frozen M0–M8 contracts.
**Status:** DRAFT handoff — pending Research Director approval. **No implementation is authorized by this document.**
**Frozen source of truth:** `docs/M9_SPEC.md` at tag `m9-spec-frozen`, commit `36659cbf6ea49e76917a8b52006442b8c206169e`.
**Date:** 2026-09-18.

> This handoff **converts** the frozen scientific specification into an engineering contract. It selects no
> statistical method, changes no endpoint, and reinterprets no hypothesis. Where a required parameter cannot
> be derived unambiguously from `m9-spec-frozen`, the existing M8 implementation, or repository architecture,
> it is listed in **§15 Open Engineering Decisions** and NOT invented here.

---

## 1. Purpose

Answer one question precisely: *what must engineering build so that the frozen M9 pre-registration is created
as an immutable, content-addressed artifact, and the pre-registered analysis becomes mechanically executable
against the frozen M8 held-out records — with zero analyst discretion?*

Two responsibilities are distinguished throughout, because the frozen spec separates them:

- **P1 — Pre-registration (M9 proper).** Produce the immutable, content-addressed record of the experiment
  design (§3.1) and the analysis plan (§3.5), *sealed from results* (§3.4). This is unambiguously the M9
  milestone deliverable.
- **P2 — Analysis executor (the frozen §3.5 procedure).** The GEE/McNemar/EMM/Holm/GO-NO-GO machinery that
  `M9_SPEC §3.5` says **"M10 applies … executed nowhere in M9."** Whether the *code* for P2 is built-and-
  synthetic-tested inside the M9 milestone (never run on held-out results) or deferred to M10 is a **scope
  boundary that this handoff does not decide** — see **§15 OED-1**. Either way its contract is pinned here so
  it can never be chosen after results are seen.

## 2. Frozen source references

- `docs/M9_SPEC.md` @ `m9-spec-frozen` / `36659cb` — the authoritative plan. Section anchors used below:
  §3.1 design, §3.2 analysis-plan summary, §3.3 pre-registration identity, §3.4 sealed-from-results,
  §3.5.1 data/encoding, §3.5.2 hypotheses, §3.5.3 GEE model, §3.5.4 EMM+interaction, §3.5.5 K=1, §3.5.6 Holm
  family, §3.5.7 model failures, §3.5.8 GO/NO-GO, §3.5.9 domain neutrality, §3.5.10 zero-RDOF.
- `docs/DECISIONS.md` — D3 (no model judges), D8 (held-out lock), D9/D22 (domain-neutral), D16.1/D18
  (content-addressed determinism), D21 (anti-wireheading), D22 (binary decision reads deterministic measure).
- `docs/M8_SPEC.md` / `docs/M8_IMPLEMENTATION_HANDOFF.md` — evaluation identity (§3.5), record schema, sink.

## 3. Existing machinery to REUSE (unchanged)

All read-only; **none is modified by M9** (RK: hardening/composition, not rewrite).

| Component | Location | Reused for |
|---|---|---|
| `Arm` (A0/A1/A2 closed set) | `src/velith/arms/identity.py` | the pre-registered arms; treatment coding maps to these frozen values |
| `Checkpoint`, `form_checkpoint`, content-addressed `identity` | `src/velith/evaluation/checkpoint.py` | the concrete content-addressed checkpoint identities that the schedule binds to (§3.1) |
| `EvaluationProvenance` (+ `.identity`) | `src/velith/evaluation/provenance.py` | mapping each pre-registered (checkpoint, arm) to its content-addressed `evaluation_identity`; the design components (checkpoint_identity, manifest_hash, arm, base_model, eval_seed, cost-guard limits) |
| `EvaluationRecord` schema | `src/velith/evaluation/record.py` | the held-out measurements M10 joins on (`evaluation_identity`, `arm`, `task_identity`, `verdict_state`, …) — **schema only in M9; outcomes read only at M10** |
| `EvaluationSink.read_all()` | `src/velith/evaluation/sink.py` | M10's read surface for records (returns records, never memory) |
| `HeldOutEvaluationSet`, `load_heldout_set`, `manifest_hash` | `src/velith/evaluation/heldout_set.py` | the held-out split identity (§3.2) and task set |
| Canonical hashing (sorted keys, tight separators, UTF-8, SHA-256) | `src/velith/episodes/episode.py` (`compute_content_hash`) and the inline form in `provenance.py` | the M9 pre-registration content-addressed identity (§3.3) MUST reuse this exact serialization (D16.1/D18) |
| `Settings` pattern (additive, validated, safe defaults) | `src/velith/core/config.py` (M8 block: `eval_seed`, `eval_sink_path`, `eval_max_tasks`, `eval_max_attempts_per_task`, `eval_max_tokens`, `corpus_manifest_path`) | source of the design's base model/seed/limits/manifest; M9 adds only additive settings |
| Structured logging | `src/velith/core/logging.py` | loud, structured failure/decision logging |

**Verdict taxonomy** `VerdictState` (`src/velith/episodes/episode.py`, D16.7) is the vocabulary for the binary
encoding (`PASSED`=1, else 0). Reused, unchanged.

## 4. NEW machinery to BUILD

Proposed ownership: a new **`src/velith/analysis/`** package (Velith layer; depends only on frozen
`evaluation`, `arms`, `corpus`, `episodes` read-only; nothing depends back on it). Subject to §15 OED-1
(which parts land in M9 vs M10) and OED-8 (package name/placement).

**P1 — pre-registration (M9 deliverable):**
1. `analysis/preregistration.py` — the immutable `PreRegistration` value: the design (arms A0/A1/A2; the
   **ordered list of concrete content-addressed checkpoint identities**; base_model; eval_seed; cost-guard
   limits; manifest_hash) **and** the analysis-plan identifiers (endpoint = binary PASSED; statistic ids;
   α=0.01; Holm family; GO/NO-GO rule id). Carries a content-addressed `identity` via the reused canonical
   serialization (§3.3). Written **once** to a segregated pre-registration location, never mutated.
2. `analysis/prereg_store.py` (or a `write_once` guard) — append/write-once persistence to the
   pre-registration location, **distinct from the experience log and the evaluation sink** (§3.4, D8).
3. Additive `Settings`: `prereg_path` (record location), and the declared statistic/threshold identifiers
   (validated against a closed set; values are α=0.01, McNemar/GEE ids per §3.5).

**P2 — analysis executor (frozen §3.5 procedure; milestone per OED-1):**
4. `analysis/binder.py` — deterministic join: for the pre-registered design, compute each
   `(checkpoint_identity, arm)`→`EvaluationProvenance.identity`, select matching records from the sink,
   group by `(task_identity, checkpoint_index, arm)`; build the per-task `(A0,A1,A2)` observations across the
   K ordered checkpoints. **A0 (OED-2, frozen):** one observation per task at `checkpoint_id_c = 0`, not replicated across K; A1/A2 one per ordered checkpoint.
5. `analysis/encoding.py` — binary endpoint: `PASSED`→1, every other `VerdictState`→0 (§3.5.1).
6. `analysis/completeness.py` — the two-tier rule (§3.5.1): global M8 incompleteness → **void** (hard stop,
   M10 cannot run); per-task missing any `task×checkpoint×arm` record → **complete-case** exclusion of that
   whole task; report included `n`.
7. `analysis/mcnemar.py` — the frozen **K=1** exact one-sided McNemar (§3.5.5): discordant `b,c`; conditional
   `B~Binomial(b+c,0.5)`; `p=P(B>=b)`; `b+c=0 ⇒ p=1.0`; two-test Holm at α=0.01.
8. `analysis/gee.py` — the **K>1** GEE fit (§3.5.3) via the chosen library (OED-3): Binomial/logit/
   exchangeable, `task_id` groups, robust sandwich covariance, treatment coding, mean-centered checkpoint
   index, with **two distinct formulas (OED-2, frozen):** A1 vs A0 additive `verdict ~ checkpoint_id_c + arm`
   (A0 single obs at `checkpoint_id_c = 0`); A2 vs A1 `verdict ~ checkpoint_id_c + arm + checkpoint_id_c*arm`.
9. `analysis/emm.py` — the response-scale uniform-1/K EMM, its **analytic delta-method** SE (§6 formula
   below), Z and one-sided p (§3.5.4). No software-default EMM.
10. `analysis/trend.py` — the gap-widens trend tests (§3.5.4): A1 vs A0 → `checkpoint_id_c` coefficient
    `beta_checkpoint` (one-sided Wald, alt `> 0`); A2 vs A1 → `checkpoint_id_c*arm` coefficient
    `beta_interaction` (one-sided Wald, alt `>= 0`); each `p = 1 − Φ(Z)`.
11. `analysis/holm.py` — the four-test sequential Holm-Bonferroni at α=0.01 (§3.5.6): thresholds
    `0.01/4, 0.01/3, 0.01/2, 0.01/1`, stop at first non-rejection.
12. `analysis/decision.py` — deterministic GO/NO-GO (§3.5.8: GO iff all four reject; §3.5.5 K=1: both McNemar
    reject) and the model-failure→`p=1.0`→NO-GO rule (§3.5.7).
13. `analysis/result_record.py` — the immutable, content-addressed **analysis result / provenance** record
    (§9), written to a results location **segregated from memory and the sink** (never re-enters experience).
14. Deterministic tests + synthetic fixtures for every path (§10). **No held-out outcome is ever a fixture.**

## 5. Exact interfaces / contracts

- **Design → identities.** For each pre-registered checkpoint identity `c_i` (i=1..K in order) and each arm
  `a∈{A0,A1,A2}`, `EvaluationProvenance(checkpoint_identity=c_i, manifest_hash, arm=a, base_model, eval_seed,
  max_tasks, max_attempts_per_task, max_tokens).identity` yields the `evaluation_identity` used to select
  records. This is the *only* sanctioned join key; M10 selects records whose `evaluation_identity` ∈ the
  pre-registered set and never resolves a semantic label to a checkpoint (§3.1 RD ruling).
- **Records → observations.** Group selected records by `task_identity`; index by ordered checkpoint
  position (1..K) and arm; encode `verdict_state` via `encoding.py`. Per included task: each memory-bearing
  arm (A1, A2) contributes one observation per ordered checkpoint (`checkpoint_id_c` = mean-centered index),
  and **A0 contributes exactly one** observation at `checkpoint_id_c = 0` — OED-2 (frozen): A0's single
  empty-checkpoint identity is **not** replicated across K.
- **Sealed-from-results (M9/P1).** `preregistration.py` and its identity depend **only** on the design +
  plan identifiers — never on `EvaluationRecord` values. P1 must not import the sink read surface. (Import-
  boundary test enforces this.)
- **Executor input/output (P2).** Input: pre-registration + the record set. Output: a single deterministic
  `GO`/`NO-GO` plus the per-test p-values/thresholds as a content-addressed result record. Pure function of
  `(pre-registration identity, records)`.

## 6. Statistical execution contract (exact)

**Endpoint (§3.5.1).** Per `(task, checkpoint, arm)`: `PASSED`=1, every other `VerdictState`=0.

**K = 1 (§3.5.5).** No GEE. Two exact one-sided McNemar tests, adjacent arms:
`H_a1: P(A1)>P(A0)`, `H_a2: P(A2)>P(A1)`. For `X>Y`: `b=#(X=1,Y=0)`, `c=#(X=0,Y=1)`;
`p = sum_{i=b}^{b+c} C(b+c,i)·0.5^(b+c)`; `b+c=0 ⇒ p=1.0`. Two-test Holm at α=0.01: sort `p(1)<=p(2)`;
reject H(1) iff `p(1)<=0.005`; then H(2) iff `p(2)<=0.01`; GO iff both reject. Gap-widening is untestable for
K=1 and is **not** treated as tested or passed.

**K > 1 (§3.5.3–§3.5.8).** One GEE per adjacent-arm comparison; Binomial family, logit link, exchangeable
working correlation, `task_id` groups, robust sandwich covariance, treatment coding, `checkpoint_id_c` =
ordered index `1..K` mean-centered by subtracting `(K+1)/2`. **Two distinct formulas (OED-2, frozen):**

- **A1 vs A0 — additive:** `verdict ~ checkpoint_id_c + arm` (no interaction). A0 is time-invariant: exactly
  one A0 observation per task at `checkpoint_id_c = 0`, **not** replicated across K (A1 contributes one per
  ordered checkpoint). Coding A0=0, A1=1. Coefficient vector `β = [β0, β_checkpoint, β_arm]` (**3-D**).
- **A2 vs A1 — interaction:** `verdict ~ checkpoint_id_c + arm + checkpoint_id_c*arm`. Coding A1=0, A2=1.
  Coefficient vector `β = [β0, β_checkpoint, β_arm, β_interaction]` (**4-D**).

*Four confirmatory tests:* (1) EMM A1vA0, (2) **checkpoint trend A1vA0**, (3) EMM A2vA1, (4) interaction A2vA1.

*EMM (superiority), response scale, uniform 1/K* — both comparisons:
`EMM_diff = (1/K)·Σ_{k=1..K}[ p̂(arm=1,k) − p̂(arm=0,k) ]`, each `p̂ = σ(η)` the inverse-logit of the fitted
linear predictor. **Delta-method SE (mandatory, no software default):** `SE = sqrt(gᵀ · V_robust · g)`, where
`V_robust` is the GEE robust sandwich covariance and `g` is the analytic gradient of `EMM_diff` w.r.t. the
**complete** fitted coefficient vector of that model. With `d_a(k)=p̂(a,k)(1−p̂(a,k))`:

- **A1 vs A0 (additive, 3-D `g` over `[β0, β_checkpoint, β_arm]`),** `η(a,x_k)=β0+β_checkpoint·x_k+β_arm·a`:
```
g = (1/K)·Σ_k [ (d1(k) − d0(k)),        # ∂/∂β0
                (d1(k) − d0(k))·x_k,     # ∂/∂β_checkpoint
                 d1(k) ]                 # ∂/∂β_arm
```
- **A2 vs A1 (interaction, 4-D `g` over `[β0, β_checkpoint, β_arm, β_interaction]`),**
  `η(a,x_k)=β0+β_checkpoint·x_k+β_arm·a+β_interaction·(x_k·a)`:
```
g = (1/K)·Σ_k [ (d1(k) − d0(k)),        # ∂/∂β0
                (d1(k) − d0(k))·x_k,     # ∂/∂β_checkpoint
                 d1(k),                  # ∂/∂β_arm
                 d1(k)·x_k ]             # ∂/∂β_interaction
```
Engineering MUST map each entry to the library's exact coefficient order. Then `Z = EMM_diff/SE`,
`p = 1 − Φ(Z)`, alternative `EMM_diff > 0`. The gradient is **analytic**; finite-difference differentiation
is forbidden (introduces a step-size DOF).

*Gap-widens trend (log-odds-ratio scale, §3.5.4 semantic lock):*
- **A1 vs A0:** the `checkpoint_id_c` coefficient `beta_checkpoint`; one-sided Wald
  `Z = beta_checkpoint/SE(beta_checkpoint)` (robust covariance); `p = 1 − Φ(Z)`; alternative
  `beta_checkpoint > 0` (A0 is time-invariant, so A1's own checkpoint slope is the widening gap).
- **A2 vs A1:** the `checkpoint_id_c×arm` coefficient `beta_interaction`; one-sided Wald
  `Z = beta_interaction/SE(beta_interaction)`; `p = 1 − Φ(Z)`; alternative `beta_interaction >= 0`.

Both trend tests are defined on the log-odds-ratio scale only; neither asserts raw-probability monotonicity.

**Multiplicity (§3.5.6).** Four-test Holm-Bonferroni at family-wise α=0.01: order `p(1)<=p(2)<=p(3)<=p(4)`;
reject sequentially at `0.01/4, 0.01/3, 0.01/2, 0.01/1`, stopping at first non-rejection.

**GO/NO-GO (§3.5.8).** GO iff all four reject; else NO-GO. Deterministic.

## 7. Solver determinism

The scientific plan is frozen; M10 reproducibility requires the *computational* behavior to be pinned. The
following must be fixed **before** implementation. Values not derivable from `m9-spec-frozen` or the repo are
flagged in §15 and MUST NOT be silently chosen.

- **Statistical library + exact version** — the repo currently has **no** numeric/stats dependency (deps are
  only `pydantic`, `pydantic-settings`). GEE + robust sandwich has no in-repo implementation. → **OED-3**.
- **GEE API / estimator / covariance type** — exact class, `cov_type`, family/link/correlation objects. →
  OED-3.
- **maxiter, convergence tolerance, start_params** — pinned explicitly (no library defaults left implicit). →
  OED-4.
- **Numerical precision / BLAS determinism** — whether bit-for-bit float equality is required on the pinned
  image or a documented comparison tolerance governs p-value/decision reproducibility. → OED-5.
- **Deterministic, pinned:** treatment/reference coding (A0=0 etc.; A1=0 for A2vA1); checkpoint index `1..K`;
  mean-centering `x_k = k − (K+1)/2`; inverse-logit `σ(η)=1/(1+e^{−η})` with overflow-safe evaluation;
  analytic EMM gradient (§6); matrix ops `gᵀVg` via the pinned library. These are pinned here (not open).
- **mypy --strict** over untyped stats libraries — stub/`additional_dependencies` or scoped ignore strategy.
  → OED-6.

## 8. Failure semantics (deterministic)

Preserve every behavior the frozen spec defines; flag every gap it does not.

Defined by `m9-spec-frozen` (implement as stated):
- Global M8 evaluation incomplete → pre-registration **void**, M10 cannot run (§3.5.1).
- Missing any `task×checkpoint×arm` record → exclude that whole task (complete-case) (§3.5.1).
- GEE non-convergence, singular robust covariance, non-finite required coefficient or SE → that model's two
  p-values = `1.0` → deterministic **NO-GO** (§3.5.7).
- K=1 zero discordance (`b+c=0`) → `p=1.0` (§3.5.5).

**Not defined by the frozen spec → do NOT invent a scientific rule; see §15:**
- Zero included tasks after complete-case (`n=0`) — OED-7a.
- Zero-variance / all-concordant endpoint at K>1 (degenerate GEE design matrix) vs the §3.5.7 failure set —
  OED-7b.
- Duplicate records / duplicate `(evaluation_identity, task_identity)`; malformed verdict outside the frozen
  taxonomy; inconsistent arm records; invalid/unknown checkpoint identity not in the pre-registered schedule —
  OED-7c (these are data-integrity errors; the spec does not name their disposition).

## 9. Provenance

The analysis result (P2) is an immutable, content-addressed record reproducible from: the frozen M9
pre-registration `identity`; the concrete ordered checkpoint identities; the held-out `manifest_hash`; the
selected `evaluation_identity` set; the implementation version; the statistical-library name+version (OED-3);
the configuration; and any deterministic seed/index construction. Reuse the canonical serialization (§3).

**Separation invariant (D8/§3.4):** M9/M10 analysis writes **only** to the pre-registration location and the
segregated results location — **never** through `GuardedEpisodeWriter`, the episode store, or the evaluation
sink write surface; it never re-enters memory/experience. Enforced by an import-boundary test.

## 10. Test plan (deterministic; synthetic fixtures only — never held-out outcomes)

Unit/integration tests with tiny synthetic fixtures carrying known intermediate values: (1) K=1 McNemar
exact p; (2) K=1 zero-discordance→p=1.0; (3) K>1 GEE construction — additive A1vA0 vs interaction A2vA1 design matrices, A0 single row at
`checkpoint_id_c = 0` (not replicated), coding, centering; (4) mean-centering arithmetic; (5) treatment
coding both comparisons; (6) EMM value; (7) analytic EMM
gradient — 3-D `[β0,β_checkpoint,β_arm]` for A1vA0 and 4-D `[…,β_interaction]` for A2vA1 — vs an independent
high-precision reference; (8) delta-method `sqrt(gᵀVg)`; (9) trend tests — A1vA0 `checkpoint_id_c` Wald and
A2vA1 interaction Wald, each one-sided; (10) one-sided p-values; (11) four-test Holm ordering/stop/thresholds; (12) each
model-failure branch→NO-GO; (13) missing-task complete-case exclusion + `n`; (14) global-incomplete→void;
(15) checkpoint-identity mismatch/unknown; (16) repeated-execution determinism (identical inputs→identical
GO/NO-GO and result identity). Pre-registration tests: identity stability; any component change→new identity;
write-once immutability; sealed-from-results import boundary.

## 11. Docker verification requirements

Per locked workflow, after each commit and before it lands, all four gates green **in the container and CI**:
`docker compose run --rm --build verifier ruff check .`; `ruff format --check .`; `mypy src tests` (strict);
`pytest -q`. M9 adds no model and no network → **zero M9-attributable skips**. If a stats dependency is added
(OED-3) the image/lockfile and mypy strategy (OED-6) must keep all gates green and hermetic. CI must remain
hermetic (no held-out outcomes as fixtures; no network).

## 12. Implementation sequence (atomic; each leaves gates green)

Pending §15 resolution and RD approval. Proposed order — P1 first (unblocks freeze-of-plan), P2 after OED-3/4/5/6:
1. Additive `Settings` (`prereg_path`, statistic/threshold identifiers). 2. `preregistration.py` + identity.
3. write-once `prereg_store.py` + sealed-from-results import-boundary test. 4. `encoding.py`. 5.
`completeness.py`. 6. `binder.py`. 7. `mcnemar.py` (K=1). 8. `gee.py` (K>1) [after OED-3/4]. 9. `emm.py`
(analytic delta-method). 10. `trend.py` (A1vA0 checkpoint Wald; A2vA1 interaction Wald). 11. `holm.py`. 12. `decision.py`. 13. `result_record.py`.
14. integration + determinism tests. One atomic commit per unit; stop after each per the locked workflow.

## 13. Non-goals / forbidden changes

No reinterpretation of the hypothesis, statistic, endpoint, checkpoint binding, arms, missing-data rule, Holm,
α, or GO/NO-GO. No additional metrics/aggregates. No modification of `M9_SPEC.md`, any M8 file, the memory
system, or any frozen M0–M8 contract. **No inspection of held-out outcomes during M9.** No implementation
handoff beyond this document. M10 boundary (must NOT be authorized by M9): inspecting results; deciding
outcomes; changing hypothesis/tests/metrics; selecting checkpoints post-freeze; modifying memory/M8/spec.

## 14. Definition of Done (handoff)

This handoff is complete when it: maps every §3.5 requirement to a concrete reuse-or-build component;
pins the statistical execution contract and the analytic EMM gradient/SE; enumerates deterministic failure
behavior and separates spec-defined from spec-silent; defines provenance and the separation invariant;
specifies a synthetic-only test plan and the Docker gates; and lists every underivable parameter under §15
with nothing silently chosen. **Implementation DoD is deferred to the post-approval engineering milestone.**

## 15. OPEN ENGINEERING DECISIONS (must be resolved before implementation — not invented here)

- **OED-1 (scope boundary M9 vs M10).** `M9_SPEC §2/§3.5` states M9 *fixes* the plan and "executes nowhere;
  M10 applies it," yet this handoff's mandate enumerates the full statistical executor. Decision required:
  does the M9 milestone **build + synthetic-test** the P2 executor (never run on held-out results), or is P2
  deferred to M10 with M9 delivering only the pre-registration artifact (P1)? Recommendation (spec-faithful):
  M9 = P1 + P2 code built and tested on synthetic fixtures only; M10 = first execution on real records.
- **OED-2 (A0 empty-checkpoint → schedule index) — RESOLVED (frozen: `m9-spec-frozen-oed2` / `3d98a84`).**
  Scientific Review ruling: A0 is time-invariant with a single empty-checkpoint identity, so it yields **one**
  observation per task at `checkpoint_id_c = 0`, **not** replicated across K. The **A1 vs A0** model is
  therefore **additive** (`verdict ~ checkpoint_id_c + arm`), its gap-widens test the `checkpoint_id_c`
  coefficient; **A2 vs A1** retains the interaction model. Encoded in §4–§8 and §10 above; no open decision
  remains.
- **OED-3 (GEE library + version).** No numeric/stats dependency exists in the repo. GEE + exchangeable
  correlation + robust sandwich requires a library (canonically `statsmodels` + `numpy`/`scipy`; transitively
  `pandas`/`patsy`). Adding it is a significant footprint change to a deliberately minimal pure-pydantic
  project. Exact library and pinned versions are not derivable from the spec/repo. **RD/architecture ruling
  required.**
- **OED-4 (solver parameters).** `maxiter`, convergence tolerance, and `start_params` for the chosen GEE
  implementation must be pinned to explicit values (defaults exist but the spec pins none). Requires
  ratification once OED-3 is fixed.
- **OED-5 (numeric reproducibility standard).** Whether M9/M10 requires bit-for-bit float identity on the
  pinned image (BLAS-sensitive) or a documented comparison tolerance for p-values/decision. The frozen spec
  says "deterministic function" but iterative FP GEE may not be bit-identical across backends. Ruling needed
  on the reproducibility/verification criterion.
- **OED-6 (mypy --strict + untyped stats libs).** Strategy to keep `mypy --strict` green over statsmodels/
  numpy (partial/no stubs): pinned stub packages, `additional_dependencies`, or a scoped, justified ignore.
- **OED-7 (spec-silent failure cases).** (a) `n=0` after complete-case; (b) zero-variance/all-concordant K>1
  design vs the §3.5.7 failure set; (c) duplicate/malformed/inconsistent/unknown-checkpoint records. The
  frozen spec does not define these; a deterministic disposition must be ruled (likely "loud typed error /
  void" to match the spec's conservatism) — **do not create a statistical fallback silently.**
- **OED-8 (package placement/ownership).** Confirm the new code lives in a single Velith-layer package
  (proposed `src/velith/analysis/`), read-only-dependent on `evaluation`/`arms`/`corpus`/`episodes`, with no
  reverse dependency and no new cross-layer coupling (MiniFlyWire→Noetica→Velith→Mini Prometheus preserved).

**Until OED-1..OED-8 are resolved by the Research Director, implementation MUST NOT begin.**
