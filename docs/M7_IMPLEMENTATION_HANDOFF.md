# M7_IMPLEMENTATION_HANDOFF

**Project:** Velith
**Milestone:** M7 — write-filter policies (arms A1 and A2) over the identical shared retrieval substrate.
**Document type:** Frozen implementation handoff. It is *extracted from* `docs/M7_SPEC.md` (frozen) and
adds no design. Every clause traces to a spec section. Engineering manufactures only what is written
here; a genuine contradiction with the frozen spec **stops work and is reported** — it never licenses
editing the spec or this handoff.
**Status:** Ready for engineering.
**Date:** 2026-07-06.
**Extracted from:** `docs/M7_SPEC.md` §1–§8. **Governing decisions:** D1, D2, D3, D5, D6, D7, D8, D9,
D11, D12, D14, D15, D16.7, D17, D18, D21, D22, D23. Future guidance D24/D25 is **not** implemented (D23).
**Manufacturing-pipeline position:** Specification → Scientific Review → **Prototype Gate (§11 —
assessed not required)** → Implementation Handoff (this document) → One Atomic Commit → Docker
Verification → Commit → Review → Next Commit.

---

## 1. Objective

Build the **write-filter** — the policy deciding which grounded experience is *retained in an arm's
memory* (M7_SPEC §1) — as two arms over an unchanged retrieval substrate: **A1 (unfiltered)**, the
RAG/null control, and **A2 (verified)**, the verification-filtered treatment. This is the load-bearing
manipulation of the program (D6/D7); the decisive contrast is **A2 strictly beats A1**, and it is
meaningful only if the arms are identical in every respect except the filter. D7 is explicit that A1 and
A2 **must share the identical retriever, embedder, and top-k**, and that *if their retrievers ever
differ, the experiment is void*.

M7 is **composition, not a rewrite** (§1): it adds no store, changes no verdict, deletes no grounding
record, and modifies no frozen M0–M6 contract. It reads the frozen M3 episode store, applies a filter,
and hands an immutable snapshot to the **unchanged M6 retriever**. It is **domain-neutral** (D9/D22): a
filter decides admission from the episode's neutral, already-grounded outcome fields — never by
interpreting task content.

## 2. Scope

**In scope (M7_SPEC §2/§3):**

1. A closed set of **write-filter policies** — A1 (unfiltered) and A2 (verified) — each a deterministic,
   domain-neutral admission predicate over an already-persisted episode (§3.2).
2. **Arm identity** for A1 and A2, recorded through the frozen `arm` provenance field alongside the
   frozen A0, with a **total, injective, run-immutable arm → filter binding** (§3.1).
3. An **arm memory view** applying the fixed projection order **Episode Store → Arm Filter → Memory
   Snapshot → Shared Retriever** (§3.3).
4. The **D7 shared-retrieval invariant**, structural and guarded by a **permanent check** (§3.4).

**Out of scope — hard boundaries (M7_SPEC §2/§8):** **arm execution and memory-conditioned proposing**
(M7 defines *what each arm's memory is*, it does not run the arms or condition attempts on retrieved
episodes); any change to the A0 runner or its memoryless behaviour; **any per-arm retrieval variation** —
substituting, re-configuring, or wrapping the M6 retriever/embedder/top-k per arm is forbidden and would
void D7; arms A3/A4 (D7); frozen checkpointed evaluation (M8); pre-registration freeze (M9); Stage-1
statistics/go-no-go (M10) — M7 evaluates, compares, and computes **no** statistic and draws no conclusion
about compounding; deleting, mutating, re-ordering, or re-writing any grounding record; generating or
consuming quantitative metrics (D22); multi-model routing; concrete real-dataset adapters; calibration
(I6); the second vertical (D5 rung 2); everything in D15; any modification of frozen M0–M6.
**D24/D25 are not implemented (D23).**

M7 uses **Python standard library plus the frozen M0–M6 packages** only — its seams are pure, in-process,
deterministic predicate logic over fields the frozen episode already carries (M7_SPEC §7). It introduces
**no new dependency**, and therefore **no Docker, compose, or CI change**.

## 3. Files allowed to change

Nothing outside this list may be touched. Module names follow M7_SPEC ("architecture only"; the new
`arms` package is the domain-neutral home for arm identity, filters, binding, and the memory view).

| Path | Commit(s) | Nature |
|---|---|---|
| `src/velith/arms/__init__.py` | M7-C1 | **New**: package marker for the write-filter/arm layer. |
| `src/velith/arms/identity.py` | M7-C1 | **New**: the closed M7 arm set — A1, A2 — alongside the frozen A0 (§3.1). |
| `tests/unit/test_arms_identity.py` | M7-C1 | **New**: arm-identity tests. |
| `src/velith/arms/filters.py` | M7-C2 | **New**: the two write-filter policies as deterministic, domain-neutral admission predicates (§3.2). |
| `tests/unit/test_arms_filters.py` | M7-C2 | **New**: admission/exclusion tests over the closed verdict taxonomy. |
| `src/velith/arms/binding.py` | M7-C3 | **New**: the total, injective, run-immutable arm → filter binding (§3.1). |
| `tests/unit/test_arms_binding.py` | M7-C3 | **New**: binding totality/injectivity/immutability tests. |
| `src/velith/core/config.py` | M7-C4 | Extend (additive setting only): the **active arm** (M7_SPEC §5). |
| `.env.example` | M7-C4 | Document the new `VELITH_*` active-arm setting. |
| `tests/unit/test_config.py` | M7-C4 | Extend: default + override of the new setting. |
| `src/velith/arms/memory_view.py` | M7-C5 | **New**: the arm memory view — Episode Store → Arm Filter → Memory Snapshot (§3.3). |
| `tests/unit/test_arms_memory_view.py` | M7-C5 | **New**: projection-order, read-only, and snapshot-identity tests. |
| `tests/unit/test_arms_shared_retrieval_invariant.py` | M7-C6 | **New**: the **permanent check** that every arm's retrieval configuration is identical (§3.4, D7). |
| `tests/integration/test_m7_write_filters.py` | M7-C7 | **New**: hermetic end-to-end acceptance for the M7 DoD (§6). |
| `README.md` | M7-C8 | Add the "M7 — write-filter policies (A1/A2)" section. |

## 4. Files forbidden to change

- **Frozen M6 retrieval substrate — used strictly as-is:** `src/velith/retrieval/**`. M7 supplies a
  filtered memory view to an **unchanged** shared retriever. Substituting, re-configuring, wrapping, or
  parameterising the retriever/embedder/top-k per arm is forbidden — it would void D7 (M7_SPEC §3.4/§8).
- **Frozen M5 batch layer — including the A0 runner:** `src/velith/batch/**`. M7 does not execute arms
  and does not touch A0 (M7_SPEC §2/§8). No frozen provenance field is added or altered (§4).
- **Frozen M3/M4 substrate — composed read-only, never modified:** `src/velith/episodes/**`,
  `src/velith/corpus/**`. M7 uses only their read surfaces (`Episode`, `verdict_state`,
  `secondary_passed`, `flaky`, `arm`, `content_hash`, the store read operations) and the guarded
  boundary's held-out guarantee.
- **Frozen M1/M2 seams:** `src/velith/harness/verifier_sandbox.py`, `src/velith/llm/client.py`,
  `src/velith/agent/proposer.py`, `src/velith/task.py`, `src/velith/runner/spike.py`.
- **Infra (no new dependency):** `docker/verifier.Dockerfile`, `docker-compose.yml`,
  `.github/workflows/**`, `pyproject.toml`, `.pre-commit-config.yaml` (M7_SPEC §2).
- **Frozen record:** `docs/DECISIONS.md`, `docs/M7_SPEC.md`, and all earlier frozen specs/handoffs.
- **Freeze-Milestone-only:** `docs/PROJECT_STATE.md`, `docs/NOTES.md` — updated only at the M7 Freeze
  Milestone by the Research Director, never inside an M7 code commit.
- **Unrelated:** all Node/Next files.
- **Per commit:** any file not in that commit's row of §3.

## 5. Dependency graph (implementation order)

Strictly linear; one atomic commit at a time. No commit begins before its predecessor is committed green.
**The Prototype Gate is assessed not required (§11) and does not gate M7-C1.**

```
M7-C1 (arms/identity.py: the closed arm set A1, A2 alongside frozen A0)
   │
   ▼
M7-C2 (arms/filters.py: A1 unfiltered + A2 verified admission predicates)
   │
   ▼
M7-C3 (arms/binding.py: total, injective, run-immutable arm → filter binding)
   │
   ▼
M7-C4 (config: the active arm, validated against the closed set)
   │
   ▼
M7-C5 (arms/memory_view.py: Episode Store → Arm Filter → Memory Snapshot; composes C1+C2+C3)
   │
   ▼
M7-C6 (permanent check: arms share the identical retriever/embedder/top-k — D7)
   │
   ▼
M7-C7 (integration: hermetic M7 write-filter acceptance)
   │
   ▼
M7-C8 (docs: README M7 section)
```

Invariants carried across the chain: retrieval is **identical across arms** — the write-filter is the
sole difference (D7); filters are **deterministic and domain-neutral**, deciding admission solely from
(`verdict_state`, `secondary_passed`, `flaky`); the **projection order is fixed** and no arm-dependent
selection occurs at or after the retriever; **no grounding record is deleted, mutated, or re-ordered**;
held-out experience is absent from every arm's memory; A0 remains memoryless and unchanged.

## 6. Commit breakdown (atomic; one logically complete unit each)

**M7-C1 — `feat: m7 arm identity`**
New `arms/identity.py`: the **closed** M7 arm set — **A1 (unfiltered memory)** and **A2 (verified
memory)** — alongside the frozen **A0** (cold, memoryless), expressed so an arm is recorded through the
**frozen** `arm` provenance field (M7_SPEC §3.1). Identity only: no filter logic, no binding, no memory
access. Unit tests: the M7 arm set is closed to A1/A2; A0 is present and unmodified; A3/A4 are absent
(§8); an arm's recorded value is the frozen provenance value.

**M7-C2 — `feat: write-filter policies`**
New `arms/filters.py`: the two **deterministic, domain-neutral admission predicates** over an
already-persisted episode, reading only neutral grounded outcome provenance and never inspecting
material, prompt, or change (M7_SPEC §3.2).

- **A1 — unfiltered:** admits **every** episode regardless of outcome — every verdict category,
  contradicted or uncontradicted by the secondary, flaky or not.
- **A2 — verified:** admits **exactly** a *verified success* (`PASSED` **and** `secondary_passed` `True`
  or absent/`None`) and a *verified failure* (`FAILED`), **and nothing else**. Excludes `PASSED` with
  `secondary_passed` `False` (the model gap, D21), `PATCH_APPLY_FAILED`, `NO_PATCH`, `INFRA_ERROR`, and
  **every** episode flagged `flaky` in **any** category (D17).

Admission is decided **solely** by the triple (`verdict_state`, `secondary_passed`, `flaky`). Unit tests:
A1 admits every category; A2's admission/exclusion is exact across the **closed** verdict taxonomy and
both secondary states; `flaky` excludes an otherwise-qualifying `PASSED` and `FAILED`; predicates are
pure and deterministic; no domain parsing occurs.

**M7-C3 — `feat: arm to filter binding`**
New `arms/binding.py`: the **total, injective** mapping from arm to write-filter — every admitted arm has
exactly one filter and every filter exactly one arm — **resolved once when the run's identity is fixed
and immutable for the run's lifetime**, never changed, re-bound, overridden, or selected dynamically per
task, attempt, query, or observed outcome (M7_SPEC §3.1). Unit tests: the mapping is total and injective
over the closed arm set; naming the arm determines the filter; a rebinding/mutation attempt after
resolution fails loudly; no run can carry an undeclared, ambiguous, or shifting retention policy.

**M7-C4 — `feat: active arm setting`**
Additive `Settings` for the **active arm** (M7_SPEC §5), validated against the closed arm set, with safe
defaults (M0 invariant: loads with no `.env`). Document the `VELITH_*` variable; extend `test_config.py`
for default + override + rejection of an unknown arm. **No per-arm retrieval setting is added** — top-k,
embedder identity, and memory source remain the single shared M6 configuration (§5, forbidden). No
behaviour beyond declaration.

**M7-C5 — `feat: arm memory view`**
New `arms/memory_view.py`: the read-only, deterministic projection applying the **fixed and total** order
**Episode Store → Arm Filter → Memory Snapshot** (M7_SPEC §3.3), each stage entered exactly once, none
skipped, reordered, merged, or re-entered, with **no episode entering from any source other than the
store**. The store is read through its verified read surface scoped to the arm; the bound filter is the
**only** stage deciding admission; the admitted episodes are fixed as an **immutable** snapshot, never
mutated, appended to, re-ordered, or re-filtered. Unit tests: the projection order holds; the view writes
nothing and mutates/re-orders/deletes no grounding record (log, index, and guarded boundary unchanged);
**identical persisted episodes plus an identical arm always produce an identical snapshot** — the same
admitted episodes in the same order — independent of interpreter hash seeding and of the order in which
experience was presented or persisted (§6.6); two arms over the same store differ only where their
filters differ; the snapshot is held-out-free by the inherited M4/M5 guarantee.

**M7-C6 — `test: arms share the identical retrieval substrate`**
New `tests/unit/test_arms_shared_retrieval_invariant.py`: the **permanent check** D7's consequences
require (M7_SPEC §3.4) — A1 and A2 retrieve through the **identical** retriever, embedder, and top-k, and
the write-filter is the only difference. Asserts the arm layer neither substitutes, re-configures, wraps,
nor parameterises the M6 substrate per arm, and that no arm-dependent selection occurs at or after the
retriever. A divergence is **not** a degradation but a **void experiment** and must **fail loudly**.

**M7-C7 — `test: hermetic m7 write-filter acceptance`**
New `tests/integration/test_m7_write_filters.py` (hermetic; no model, no network — the M6 reference
embedding is in-process): end-to-end over the frozen M3 store through both arms — A1 admits every
episode; A2 admits exactly verified successes and verified failures and excludes the model-gap `PASSED`,
`PATCH_APPLY_FAILED`, `NO_PATCH`, and every `flaky` episode; the fixed projection order holds; identical
persisted episodes + identical arm yield an identical snapshot; both arms retrieve through the identical
shared substrate; neither arm's memory contains a held-out episode; the grounding log is byte-unchanged
after both arms run; A0 is neither depended upon nor modified; and a **non-software** memory filters and
retrieves through the identical path. Covers M7_SPEC §6 DoD 1–8.

**M7-C8 — `docs: document write-filter policies`**
Add the "M7 — write-filter policies (A1/A2)" section to `README.md` (the closed arm set, the exact A2
admission boundary, the immutable arm→filter binding, the fixed projection order, the shared-retrieval
invariant, and the new active-arm setting). Claims only what C1–C7 verify. No `PROJECT_STATE`/`NOTES`
edits.

## 7. Docker verification gates (run after every commit, before it is made)

The identical containerized sequence M1–M6 used. A commit is made **only** when all four are green:

```
docker compose run --rm verifier bash -lc \
  "ruff check . && ruff format --check . && mypy src tests && pytest -q"
```

- `ruff check .` — lint (E,F,I,N,UP,B,SIM,RUF; line-length 100).
- `ruff format --check .` — formatting.
- `mypy src tests` — `--strict`.
- `pytest -q` — full suite.

**CI stays hermetic.** M7's seams are pure in-process predicate logic and a read-only projection; no live
model, no network, no `CAP_SYS_ADMIN`-gated path is added — `pytest -q` reports **zero M7-attributable
skips**. No new dependency, so no Docker/compose/CI file changes.

## 8. Rollback condition for every commit

Uniform trigger, applied per commit: **if any of the four gates in §7 is red, or the commit's own
acceptance assertions fail, do not commit.** Discard the working tree for that commit
(`git restore`/`git checkout --`), and either fix within the *same* atomic commit or stop. Per-commit
specifics:

- **M7-C1** — roll back if the M7 arm set is not closed to A1/A2, if A0 is altered, if A3/A4 appear, if
  an arm is not recorded through the frozen `arm` provenance, or if any gate is red.
- **M7-C2** — roll back if A1 excludes any episode; if A2 admits or excludes anything other than the
  exact §3.2 categories (notably: admitting `PASSED` with `secondary_passed` `False`, admitting
  `PATCH_APPLY_FAILED`/`NO_PATCH`/`INFRA_ERROR`, or admitting any `flaky` episode); if admission consults
  anything beyond (`verdict_state`, `secondary_passed`, `flaky`); if a predicate is non-deterministic or
  parses a domain; or if any gate is red.
- **M7-C3** — roll back if the mapping is not total or not injective, if a filter can be re-bound,
  overridden, or selected dynamically after the run's identity is fixed, if a run can carry an
  undeclared/ambiguous retention policy, or if any gate is red.
- **M7-C4** — roll back if config fails to load with no `.env`, if an unknown arm is accepted, if **any
  per-arm retrieval setting** is introduced (forbidden, §5), if a default/override test fails, or if any
  gate is red.
- **M7-C5** — roll back if the projection order is violated (a stage skipped, reordered, merged, or
  re-entered, or an episode entering from any source other than the store); if the view writes to,
  mutates, deletes, or re-orders the store/index/episodes; if the snapshot is mutable or non-identical
  for identical episodes + identical arm; if a held-out episode surfaces; or if any gate is red.
- **M7-C6** — roll back if the arms' retrieval configuration is not provably identical, if any arm
  substitutes/re-configures/wraps/parameterises the M6 substrate, if arm-dependent selection occurs at or
  after the retriever, if the check does not fail loudly on divergence, or if any gate is red.
- **M7-C7** — roll back if any acceptance assertion (A1/A2 admission exactness, projection order,
  snapshot identity, shared substrate, held-out-free memory, unchanged grounding log, A0 untouched,
  domain-neutral flow) fails, or if any gate is red.
- **M7-C8** — roll back if docs introduce a claim not verified by C1–C7, or if any gate is red.

**Frozen-spec guard (stop condition).** If a rollback is caused by a **genuine contradiction with
`docs/M7_SPEC.md`** (not a mere bug) — for example, the fixed projection order cannot be realized without
modifying the frozen M6 retriever, or an arm-scoped memory cannot be produced without mutating the frozen
store — **stop immediately and report the contradiction to the Research Director.** Do not edit the
frozen spec or this handoff to make the code pass, do not reinterpret the architecture, do not relax the
A2 admission boundary, and do not introduce D24/D25 to resolve it (D23).

## 9. Definition of Done (mapping to M7_SPEC §6)

M7 is done when all hold, verified in-container and in CI:

1. Two **write-filter policies** exist — A1 (unfiltered) and A2 (verified) — each a deterministic,
   domain-neutral admission predicate over an already-persisted episode, reading only neutral grounded
   outcome provenance — **§6.1** (C2).
2. **A1 admits every episode** of its arm regardless of outcome — every verdict category, contradicted or
   not, flaky or not — **§6.2** (C2; acceptance C7).
3. **A2 admits exactly the two defined categories and nothing else** — verified success (`PASSED` with
   `secondary_passed` `True` or absent) and verified failure (`FAILED`) — excluding model-gap `PASSED`
   (D21), `PATCH_APPLY_FAILED`, `NO_PATCH`, `INFRA_ERROR`, and every `flaky` episode (D17), decided
   solely by (`verdict_state`, `secondary_passed`, `flaky`) — **§6.3** (C2; acceptance C7).
4. Each arm is bound to **exactly one** filter by a total, injective mapping **fixed when the run's
   identity is fixed and immutable for the run's lifetime**, surfaced through the frozen `arm`
   provenance — **§6.4** (C1+C3; setting C4).
5. The **arm memory view** applies the fixed order **Episode Store → Arm Filter → Memory Snapshot →
   Shared Retriever** with no stage skipped/reordered/re-entered and no episode from any other source;
   log, index, and guarded boundary unmodified; **no grounding record deleted, mutated, or re-ordered** —
   **§6.5** (C5; acceptance C7).
6. **Snapshot identity is exact and reproducible** — identical persisted episodes + identical arm always
   produce an identical snapshot (same episodes, same order) across processes, runs, and machines,
   independent of hash seeding and persistence order (D8/D16.1/D18); two arms differ **only** where their
   filters differ — **§6.6** (C5; acceptance C7).
7. The **D7 invariant holds and is permanently checked** — A1 and A2 retrieve through the identical
   retriever, embedder, and top-k; the write-filter is the only difference; divergence fails loudly —
   **§6.7** (C6).
8. **Held-out safety and A0 are preserved** — no arm's memory contains a held-out episode; A0 remains
   memoryless and unchanged — **§6.8** (C5/C7; enforced by §4).
9. **Domain-neutrality and determinism hold** — a non-software memory filters and retrieves through the
   identical path; no frozen M0–M6 file is modified, the only additions being the M7 policy/view seams
   and additive configuration; all four gates green in the container and CI with zero M7-attributable
   skips — **§6.9** (every commit; acceptance C7).

**Freeze Milestone (Research Director, after DoD 1–9):** update `docs/PROJECT_STATE.md` and
`docs/NOTES.md`, then tag `m7-complete`. These are not M7 code commits.

## 10. Risks

Extracted from M7_SPEC §3, §5, and §8:

- **Per-arm retriever divergence — the fatal risk.** If the arms' retrieval ever differs, the experiment
  is **void**, not merely degraded (D7). *Mitigation:* the invariant is structural — the arm supplies only
  a filtered memory view to an unchanged shared retriever; `src/velith/retrieval/**` is forbidden (§4);
  the permanent check (C6) fails loudly; no per-arm retrieval setting may exist (§5).
- **Arm-dependent selection leaking past the filter stage.** Filtering during or after retrieval would
  make retrieval itself arm-dependent and void D7. *Mitigation:* the fixed projection order (C5); the
  C5/C6 rollback triggers.
- **A mutable arm → filter binding.** A filter that shifted mid-run would make the manipulated variable
  non-constant within an arm, so the recorded `arm` would no longer identify what the memory contains and
  the A1/A2 contrast would be uninterpretable. *Mitigation:* total, injective, run-immutable binding (C3).
- **Mutation or loss of the grounding record.** Filtering is *admission into memory*, never deletion.
  *Mitigation:* read-only projection over the frozen store (C5); `episodes/**` forbidden (§4); acceptance
  asserts the log is byte-unchanged (C7).
- **Snapshot non-determinism.** Non-identical snapshots for identical inputs would break D8/D16.1/D18 and
  the arm contrast. *Mitigation:* deterministic projection and immutable snapshot (C5); explicit DoD 6.
- **Held-out leakage.** *Mitigation:* the projection reads only experience already persisted through the
  frozen M4/M5 guarded boundary — held-out-free by construction; M7 adds no reintroduction path (C5/C7).
- **Scope creep into arm execution.** Wiring memory into proposing is M7's stated boundary violation.
  *Mitigation:* `batch/**` forbidden (§4); §2/§8 out-of-scope; no runner is touched.
- **A0 disturbance.** *Mitigation:* `batch/**` forbidden (§4); M7 executes no arm.

## 11. Prototype gate handling (assessed NOT REQUIRED before M7-C1)

Per M7_SPEC §7, M7 asserts **no unproven environmental mechanism**. Its seams are pure, in-process,
deterministic predicate logic over neutral fields the frozen episode already carries, plus a read-only
projection over the already-verified M3 store and the already-proven M6 substrate — whose retrieval
determinism was established by the **discharged M6 Prototype Gate**. Nothing new depends on the
environment, the filesystem, or a model.

- **Assessment: the Prototype Gate is a no-op for M7 and does not gate M7-C1.** Engineering proceeds
  directly from the frozen specification on the Research Director's authorization.
- It fires **only** if the Research Director judges some M7 assertion a load-bearing unknown — most
  plausibly the A2 admission boundary (§3.2), which M7_SPEC records as a *scientific ratification*
  question rather than a feasibility one, and which was settled at Scientific Review rather than by
  prototype.
- If, during engineering, a load-bearing unknown is nonetheless discovered, that is a **stop condition**:
  report it to the Research Director under §8's frozen-spec guard. Do not prototype it inside a commit,
  do not edit the frozen spec, do not reinterpret the architecture, and do not introduce D24/D25 (D23).

---

*End of handoff. Engineering begins at M7-C1 only after the Research Director authorizes it; one atomic
commit at a time, stopping for review after each. Composition over modification; the architecture is
frozen; implementation is extracted from `docs/M7_SPEC.md` only. Future principles D24/D25 are not
implemented (D23).*
