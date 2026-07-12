# M5_IMPLEMENTATION_HANDOFF

**Project:** Velith
**Milestone:** M5 — batch runner and the cold baseline arm (A0).
**Document type:** Frozen implementation handoff. It is *extracted from* `docs/M5_SPEC.md` (FINAL,
frozen) and adds no design. Every clause traces to a spec section. Engineering manufactures only what
is written here; a genuine contradiction with the frozen spec **stops work and is reported** — it never
licenses editing the spec or this handoff.
**Status:** Ready for engineering.
**Date:** 2026-07-06.
**Extracted from:** `docs/M5_SPEC.md` §1–§8. **Governing decisions:** D6, D7, D8, D9, D12, D13, D14,
D15, D16.1, D16.2, D16.4, D16.5, D16.7, D18, D21, D22, D23. Future guidance D24/D25 is **not**
implemented (D23).
**Manufacturing-pipeline position:** Specification → **Implementation Handoff (this document)** → One
Atomic Commit → Docker Verification → Commit → Review → Next Commit.

---

## 1. Objective

Turn the single-task loop into a **batch sweep** over the corpus, recording the **cold baseline arm
(A0)** — the no-memory baseline the compounding experiment measures against (M5_SPEC §1, D6/D7/D8). M5
is **composition, not a rewrite**: it orchestrates the frozen proposer, verifier, and episode store
over the frozen M4 corpus, persisting **only through the frozen M4 guarded persistence boundary** so
held-out experience can never leak at scale (D8). It stays **domain-neutral** (D9/D22): the runner
treats materials and verification handles as opaque, with all domain specifics behind a registered
adapter interface.

## 2. Scope

**In scope (M5_SPEC §2/§3):**

1. A **batch runner** sweeping the corpus's *available* partition through `propose → verify → log`,
   producing one episode per attempted task (§3.1).
2. The **cold baseline arm (A0)** — no memory read or written; recorded on each episode via the frozen
   `arm` provenance field (§3.2; D7).
3. A **task-materialization adapter seam** — a domain-neutral interface turning a `CorpusTask`'s opaque
   handle into the concrete inputs the frozen proposer and verifier consume, with the existing single
   fixture as the reference adapter (§3.3).
4. A **single fixed base-model selection seam** (one non-saturating model, D8 §1/D16.5) and a **hard,
   deterministic cost guard** with resource limits (budget, attempt limits, timeout, token limits, or
   equivalent) that halts loudly and is recorded as experiment identity (§3.4, D16.4).
5. A **batch/run provenance** record — the sweep's *experiment identity*: corpus manifest hash, arm,
   base-model identity, **cost-guard budget/limits**, and **batch seed** — with each task's seed
   **deterministically derived from (task identity, batch seed)** (§3.5).

**Out of scope — hard boundaries (M5_SPEC §8):** the retrieval substrate (M6); write-filter arms A1/A2
(M7); anti-grounding A3 and ablation A4 (D7); frozen checkpointed evaluation (M8); pre-registration
freeze (M9); Stage-1 statistics/go-no-go (M10); multi-model routing/selection policy beyond one fixed
base model; concrete real-dataset adapters/ETL (registrations behind §3.3); any change to frozen M0–M4;
calibration; the second vertical; distributed/parallel-scale infrastructure (D14); and everything in
D15. **Future principles D24/D25 are not implemented (D23).**

M5 uses **Python standard library plus the frozen M0–M4 packages** only; it introduces **no new
dependency**, and therefore **no Docker, compose, or CI change**.

## 3. Files allowed to change

Nothing outside this list may be touched. Module names follow M5_SPEC ("names are indicative"); the new
`batch` package is the domain-neutral home for the M5 seams.

| Path | Commit(s) | Nature |
|---|---|---|
| `src/velith/core/config.py` | M5-C1 | Extend (additive settings only): base-model binding, batch seed, and cost-guard limits (M5_SPEC §3.4/§3.5). |
| `.env.example` | M5-C1 | Document the new `VELITH_*` batch settings. |
| `tests/unit/test_config.py` | M5-C1 | Extend: defaults + overrides of the new settings. |
| `src/velith/batch/__init__.py` | M5-C2 | **New**: package marker for the M5 batch layer. |
| `src/velith/batch/provenance.py` | M5-C2 | **New**: deterministic per-task seed + batch/run provenance record (§3.5). |
| `tests/unit/test_batch_provenance.py` | M5-C2 | **New**: seed-determinism and provenance-identity tests. |
| `src/velith/batch/budget.py` | M5-C3 | **New**: the hard deterministic cost guard (§3.4). |
| `src/velith/batch/model.py` | M5-C3 | **New**: single fixed base-model selection seam composing the frozen LLM client (§3.4). |
| `tests/unit/test_batch_budget.py` | M5-C3 | **New**: cost-guard unit tests. |
| `tests/unit/test_batch_model.py` | M5-C3 | **New**: base-model-seam unit tests. |
| `src/velith/batch/adapter.py` | M5-C4 | **New**: neutral task-materialization interface + fixture reference adapter (§3.3). |
| `tests/unit/test_batch_adapter.py` | M5-C4 | **New**: adapter unit tests. |
| `src/velith/batch/runner.py` | M5-C5 | **New**: the batch runner (§3.1/§3.2), composing injected collaborators. |
| `tests/unit/test_batch_runner.py` | M5-C5 | **New**: hermetic runner tests (mocked proposer, stub verifier). |
| `tests/integration/test_m5_batch_a0.py` | M5-C6 | **New**: hermetic end-to-end A0 acceptance (§6). |
| `README.md` | M5-C7 | Add the "M5 — batch runner and the cold baseline arm (A0)" section. |

## 4. Files forbidden to change

- **Frozen M4 corpus layer — composed, never modified:** `src/velith/corpus/manifest.py`,
  `src/velith/corpus/loader.py`, `src/velith/corpus/heldout.py`. The runner writes **only** through the
  M4 `GuardedEpisodeWriter` (M5_SPEC §4/§5).
- **Frozen M1–M3 seams — composed, never modified:** `src/velith/episodes/**`,
  `src/velith/harness/verifier_sandbox.py`, `src/velith/llm/client.py`, `src/velith/agent/proposer.py`,
  `src/velith/task.py`, and `src/velith/runner/spike.py` (the frozen single-task reference — M5 adds a
  new `runner`/`batch` module beside it, never edits it).
- **Infra (no new dependency):** `docker/verifier.Dockerfile`, `docker-compose.yml`,
  `.github/workflows/**`, `pyproject.toml`, `.pre-commit-config.yaml` (M5_SPEC §2/§7).
- **Frozen record:** `docs/DECISIONS.md`, `docs/M5_SPEC.md`, and all earlier frozen specs/handoffs.
- **Freeze-Milestone-only:** `docs/PROJECT_STATE.md`, `docs/NOTES.md` — updated only at the M5 Freeze
  Milestone by the Research Director, never inside an M5 code commit.
- **Unrelated:** all Node/Next files.
- **Per commit:** any file not in that commit's row of §3.

## 5. Dependency graph

Strictly linear; one atomic commit at a time. No commit begins before its predecessor is committed
green.

```
M5-C1 (config: base model, batch seed, cost-guard limits)
   │
   ▼
M5-C2 (batch/provenance.py: deterministic per-task seed + run provenance)
   │      seed = f(content-addressed task identity, batch seed); records experiment identity
   ▼
M5-C3 (batch/budget.py + batch/model.py: cost guard + single fixed base-model seam)
   │
   ▼
M5-C4 (batch/adapter.py: neutral materialization interface + fixture reference adapter)
   │
   ▼
M5-C5 (batch/runner.py: sweep available -> adapter -> proposer -> verifier -> guarded writer, arm=A0)
   │      composes C2-C4 and the frozen M1-M4 collaborators by injection
   ▼
M5-C6 (integration: hermetic end-to-end A0 acceptance)
   │
   ▼
M5-C7 (docs: README M5 section)
```

Invariants carried across the chain: the runner persists **only** through the M4 guarded boundary;
A0 reads/writes **no** memory; each task's seed is a deterministic function of `(task identity, batch
seed)`, identical across arms regardless of execution order or retries.

## 6. Commit breakdown

Each commit is atomic, conventional, and independently green.

**M5-C1 — `feat: batch run settings`**
Additive `Settings` for the fixed base-model binding, the **batch seed**, and the **cost-guard limits**
(budget, attempt limits, timeout, token limits, or equivalent — M5_SPEC §3.4/§3.5). Safe defaults so
the system loads with no `.env` (M0 invariant). Document the `VELITH_*` variables; extend
`test_config.py` for default + override.

**M5-C2 — `feat: deterministic per-task seed and run provenance`**
New `batch/provenance.py`: a **deterministic per-task seed** computed from the content-addressed task
identity (M4 `task_identity`) and the batch seed, and a **batch/run provenance** record capturing the
experiment identity — corpus manifest hash, arm (A0), base-model identity, cost-guard budget/limits,
and batch seed (M5_SPEC §3.5). No new episode identity field (D21/D22 hold). Unit tests: the per-task
seed is deterministic and **independent of execution order and retries** (same `(identity, batch seed)`
→ same seed); differing identities or batch seeds differ; provenance records **all** experiment-identity
fields including the budget/limits.

**M5-C3 — `feat: cost guard and fixed base-model seam`**
New `batch/budget.py`: a **hard, deterministic cost guard** that halts the sweep **loudly** when any
configured limit is reached, never emitting a partial/misleading result. New `batch/model.py`: a
single-owner **base-model selection seam** binding one fixed model, composing the frozen LLM client
without modifying it. Unit tests: the guard trips at each limit and admits work strictly below it;
the model seam returns the one configured base model.

**M5-C4 — `feat: task-materialization adapter seam`**
New `batch/adapter.py`: a domain-neutral **interface** that materializes, from a `CorpusTask`'s opaque
material and handle, the proposer context and a verifiable frozen `Task`; plus a **reference adapter**
over the existing single fixture (D16.3). The runner depends on the interface only; domain specifics
live entirely behind it (M5_SPEC §3.3). Unit tests: the reference adapter yields the frozen inputs;
the runner-facing surface exposes no domain detail; a non-software `CorpusTask` is accepted opaquely.

**M5-C5 — `feat: batch runner (cold arm A0)`**
New `batch/runner.py`: the batch runner (M5_SPEC §3.1/§3.2). It draws the **available** tasks from the
frozen M4 loader, drives each through the adapter → proposer → verifier, and persists the resulting
episode **through the frozen `GuardedEpisodeWriter`**, tagging the cold-baseline arm (A0). It accepts
its collaborators (proposer, verifier, guarded writer, adapter, cost guard) **by injection** so it is
hermetically testable; it is bounded by the cost guard and emits the run provenance. Unit tests (mocked
proposer, **stub verifier**): available tasks are swept and persisted via the guarded boundary with
`arm = A0`; held-out/unknown tasks are never persisted; the cost guard halts the sweep loudly; the
per-task seed drives the proposal deterministically regardless of order.

**M5-C6 — `test: hermetic m5 batch A0 acceptance`**
New `tests/integration/test_m5_batch_a0.py` (hermetic; mocked proposer, stub verifier, no network): an
end-to-end sweep over a fixture corpus — available-only persistence through the frozen store, `arm =
A0` on every episode, held-out never persisted, A0 cold (no memory), the cost guard halting loudly, the
deterministic seed identical across re-runs and retries, run provenance recording the full experiment
identity (incl. budget/limits), and a **non-software** corpus sweeping through the identical path.
Covers M5_SPEC §6 DoD 1–6.

**M5-C7 — `docs: document batch runner and cold arm A0`**
Add the "M5 — batch runner and the cold baseline arm (A0)" section to `README.md` (the batch runner,
A0, the adapter seam, the cost guard, deterministic per-task seeding, run provenance, and the new
settings; the bounded **live** sweep documented as the local acceptance step, D16.2). No
`PROJECT_STATE`/`NOTES` edits.

## 7. Docker verification gates (run after every commit, before it is made)

The identical containerized sequence M1–M4 used. A commit is made **only** when all four are green:

```
docker compose run --rm verifier bash -lc \
  "ruff check . && ruff format --check . && mypy src tests && pytest -q"
```

- `ruff check .` — lint (E,F,I,N,UP,B,SIM,RUF; line-length 100).
- `ruff format --check .` — formatting.
- `mypy src tests` — `--strict`.
- `pytest -q` — full suite.

**CI stays hermetic (D16.2).** M5's runner tests inject a **mocked proposer and a stub verifier**, so
they exercise no live model and no network and add **no** `CAP_SYS_ADMIN`-gated path — `pytest -q`
reports **zero M5-attributable skips**. The bounded **live** sweep (real proposer + real verifier) is a
documented **local** acceptance step, not a CI gate (mirroring the M1 live acceptance).

## 8. Rollback condition for every commit

Uniform trigger, applied per commit: **if any of the four gates in §7 is red, or the commit's own
acceptance assertions fail, do not commit.** Discard the working tree for that commit
(`git restore`/`git checkout --`), and either fix within the *same* atomic commit or stop. Per-commit
specifics:

- **M5-C1** — roll back if config fails to load with no `.env`, if a default/override test fails, or if
  any gate is red.
- **M5-C2** — roll back if the per-task seed depends on execution order or retries, if it is not a
  function of `(task identity, batch seed)`, if provenance omits any experiment-identity field
  (especially the cost-guard budget/limits or batch seed), or if any gate is red.
- **M5-C3** — roll back if the cost guard fails to halt loudly at a limit, admits work past a limit, or
  emits a partial result; if the model seam is not bound to a single fixed model; or if any gate is red.
- **M5-C4** — roll back if the adapter exposes domain detail to the runner, if the reference adapter
  does not yield the frozen proposer/verifier inputs, or if any gate is red.
- **M5-C5** — roll back if any episode is persisted outside the M4 guarded boundary, if a held-out or
  unknown task is ever persisted, if A0 reads/writes memory, if `arm != A0`, if the cost guard is not
  honored, if `runner/spike.py` (or any frozen file) is modified, or if any gate is red.
- **M5-C6** — roll back if any acceptance assertion (available-only, A0 cold, held-out never persisted,
  cost-guard halt, seed determinism across order/retries, provenance identity, domain-neutral sweep)
  fails, or if any gate is red.
- **M5-C7** — roll back if docs introduce a claim not verified by C1–C6, or if any gate is red.

**Frozen-spec guard:** if a rollback is caused by a genuine contradiction with `docs/M5_SPEC.md` (not a
mere bug), **stop immediately and report the contradiction to the Research Director.** Do not edit the
frozen spec or this handoff to make the code pass, and do not introduce D24/D25 to resolve it (D23).

## 9. Definition of Done

Extracted from M5_SPEC §6; M5 is done when all hold, verified in-container and in CI:

1. The batch runner sweeps the available partition end to end, one episode per attempted task, each
   persisted **through the M4 guarded boundary** and tagged `arm = A0`.
2. Held-out is never attempted or persisted — the runner draws only available tasks and the guarded
   boundary refuses held-out/unknown identities (D8).
3. A0 is cold — no memory read or written; each task's seed is deterministically derived from `(task
   identity, batch seed)`, so a re-run is independent and the task's evaluation is identical across arms
   regardless of execution order or retries (D8/D16.1).
4. The cost guard bounds the sweep deterministically and halts loudly without writing a partial or
   misleading episode.
5. The batch/run provenance records the corpus manifest hash, the arm, the base-model identity, the
   cost-guard budget/limits, and the batch seed — uniquely identifying the sweep as an experiment.
6. Domain-neutrality holds — a synthetic non-software corpus sweeps through the identical path via the
   reference adapter; the runner inspects no materials or handles directly.
7. No frozen M0–M4 file is modified; the only additions are the new M5 components and additive
   `core/config.py` settings. D24/D25 are not implemented (D23).
8. All four gates are green in the container and CI; commits are atomic and conventional. A bounded
   live sweep is the documented local acceptance step (CI stays hermetic, D16.2).

**Freeze Milestone (Research Director, after DoD 1–8):** update `docs/PROJECT_STATE.md` and
`docs/NOTES.md`, then tag `m5-complete`. These are not M5 code commits.

## 10. Risks

Extracted from M5_SPEC §5/§7:

- **Unguarded write path.** Any episode persisted outside the M4 boundary would let held-out leak at
  scale. *Mitigation:* the runner persists **only** through `GuardedEpisodeWriter` (§5); enforced by the
  C5/C6 tests.
- **Seed non-determinism.** A seed that depends on order or retries would make arms incomparable.
  *Mitigation:* seed = deterministic `f(task identity, batch seed)` (C2); order/retry-invariance is a
  rollback trigger.
- **Incomplete experiment identity.** Omitting the cost-guard budget/limits from provenance would make
  a run non-reproducible as an experiment. *Mitigation:* provenance records the full identity (C2/§3.5).
- **Domain leakage.** The runner inspecting materials/handles would break neutrality. *Mitigation:* all
  domain specifics behind the §3.3 adapter interface; a non-software corpus test.
- **Scope creep** into memory, arms A1/A2, or multi-model routing. *Held off by* §2/§8.
- **Live-model batch behavior** (throughput/timeout at scale) — an operational acceptance concern, not
  architectural (see §11).

## 11. Prototype gate (conditional — not required)

Per M5_SPEC §7, M5 orchestrates already-verified components and asserts **no unproven environmental
mechanism**; its logic (batching, the cold-arm rule, the deterministic cost guard, run provenance,
deterministic seeding) is pure composition. The one candidate unknown — **live-model batch
throughput/latency within the cost budget** — is an *operational acceptance* concern already covered by
the M1 live-acceptance pattern. The Prototype Gate is therefore **not required (no-op)**; it fires only
if Scientific Review judges batch-scale live behavior a load-bearing unknown, in which case a single
bounded live sweep discharges it before freeze. Proceed directly to M5-C1.

---

*End of handoff. Engineering begins at M5-C1 only after the Research Director authorizes it; one atomic
commit at a time, stopping for review after each. Future principles D24/D25 are not implemented (D23).*
