# M5_SPEC — Batch runner and the cold baseline arm (A0)

**Project:** Velith
**Milestone:** M5 — the single-task spike becomes a **batch sweep** over the corpus, running the
**cold baseline arm (A0)** under a hard cost guard, writing only through the frozen held-out boundary.
**Document type:** Frozen engineering contract — **architecture only**. Extracted from the ratified
constitution (`DECISIONS.md`), the vision (`VISION.md`), and the roadmap (D12). It contains no
implementation, no pseudocode, no code, and no handoff. Once frozen it is immutable; the M5
implementation is *extracted from* it and never redesigns it.
**Status:** FINAL — ready for freeze.
**Date:** 2026-07-06.
**Depends on:** `m4-complete` (frozen corpus loader, content-addressed manifest, held-out lock, and
guarded persistence boundary), atop `m3-complete` / `m2-complete` / `m1-complete` / `m0-complete`.
**Governing decisions:** D6, D7, D8, D9, D11, D12, D13, D14, D15, D16.1, D16.2, D16.4, D16.5, D16.7,
D18, D21, D22, D23.

> **Manufacturing-pipeline position:** Specification → Scientific Review → Feasibility Prototype
> (conditional) → Research Director Review → Freeze Specification → Implementation Handoff →
> Engineering → Verification → Freeze Milestone. This document is the Specification artifact.

---

## 1. Purpose

M1 proved the single-task `propose → verify → log` loop; M2 hardened the verdict; M3 made episodes
queryable and integrity-checked; M4 lifted the task representation to a **corpus** under a
mechanically-enforced held-out lock. M5 does the one thing the compounding experiment (D6/D7/D8)
requires next, and nothing more: it runs the loop **at scale** over the corpus as a **batch sweep**,
recording the **cold baseline arm (A0, D7)** — the no-memory baseline against which every later,
memory-bearing arm is measured.

M5 is **composition, not a rewrite**. It orchestrates the frozen proposer, verifier, and episode
store over the frozen M4 corpus, and it persists **only through the frozen M4 guarded persistence
boundary**, so held-out experience can never leak even at scale (D8). It stays **domain-neutral**
(D9/D22): the batch runner treats task materials and verification handles as opaque, delegating all
domain specifics to a registered adapter behind a neutral contract. This keeps M5 aligned with the
Mini Prometheus north star — the same batch machinery and cold baseline carry unchanged up the D5
ladder toward electronics, HDL, and manufacturing.

## 2. Scope — what M5 is

1. A **batch runner** that sweeps the **available** partition of a loaded corpus through the frozen
   `propose → verify → log` loop, producing one episode per attempted task.
2. The **cold baseline arm (A0)** — each task attempted with **no memory** read or written; runs are
   independent. A0 is recorded on each episode via the frozen `arm` provenance field (D7; the field
   exists from M1 for exactly this, D9/§9.1).
3. A **hard cost/budget guard** — a deterministic bound on the sweep (D16.4) that halts loudly when
   exceeded, honoring D8's staged-spending discipline (Stage 1 is a cheap go/no-go).
4. A **single fixed base-model selection seam** bound to one deliberately non-saturating model
   (D8 §1, D16.5), composing the frozen LLM client. Full multi-model routing/selection policy is
   **not** built (see §8).
5. A **batch/run provenance record** tying a sweep to its corpus manifest hash, arm, base model, the
   **cost-guard budget/limits**, and the **batch seed** — the sweep's explicit *experiment identity* —
   so a batch run is identifiable and reproducible, and pre-registration-ready (D8 §2, consumed at M9).
   Each task's seed is **deterministically derived from (task identity, batch seed)**.
6. A **domain-neutral task-materialization contract** (the adapter seam) that turns a `CorpusTask`'s
   opaque handle into the concrete inputs the frozen proposer and verifier consume, with the existing
   single fixture as the reference adapter. Concrete real-dataset adapters remain registrations
   (M4_SPEC §3.2), out of scope here.

## 3. Architecture

Five domain-neutral seams composing the frozen substrate. No new architecture is introduced; these
are the minimal components D12 assigns to M5.

**3.1 Batch runner.** The single owner of *batch* operation order, generalizing the M1 single-task
spike (which remains the frozen single-task reference). It draws the corpus's **available** tasks from
the frozen M4 loader, drives each through propose → verify → log, and persists each resulting episode
**exclusively through the frozen `GuardedEpisodeWriter`** (never directly to the store). It is the
single owner of the sweep; it holds no domain knowledge.

**3.2 Cold baseline arm (A0).** A0 is *no memory*: no experience is read before an attempt and none is
carried between attempts. Because retrieval (M6) and write-filter policies (M7) do not yet exist, A0
is the only arm M5 can run, and it is the arm the compounding experiment baselines against (D6/D7).
Each episode records the cold-baseline arm in its frozen `arm` field; the verdict taxonomy is
unchanged (D16.7).

**3.3 Task-materialization adapter seam.** A domain-neutral contract that materializes, from a
`CorpusTask`'s opaque `material` and verification `handle`, the concrete inputs the frozen components
need: the proposal context for the proposer and a verifiable `Task` for the frozen verifier. The batch
runner depends on this **interface**, never on any domain; the reference adapter is the existing
single fixture (D16.3). A concrete real-dataset adapter (e.g. SWE-bench) is a **registration**
conforming to this contract and is out of scope (M4_SPEC §3.2/§6). This is the one seam where domain
specifics are permitted, and they live entirely behind the neutral interface.

**3.4 Single fixed base-model selection + cost guard.** A single-owner model-selection seam bound to
one fixed, non-saturating base model (D8 §1, D16.5), composing the frozen LLM client without modifying
it. A **hard, deterministic cost guard** bounds the sweep (D16.4) — a set of deterministic resource
limits (budget, attempt limits, timeout, token limits, or equivalent) — and halts the run **loudly**
when any bound is reached, never writing a partial or misleading episode. These budget/limits are
recorded in the run provenance (§3.5) as part of the sweep's experiment identity.

**3.5 Batch/run provenance and deterministic per-task seeding.** A lightweight record identifying a
sweep — its **experiment identity** — by the **corpus manifest hash** (the frozen split, M4_SPEC §3.1),
the arm (A0), the base-model identity, the **cost-guard budget/limits** (§3.4 — the deterministic
resource bounds: budget, attempt limits, timeout, token limits, or equivalent), and the **batch seed**.
Each task receives a **deterministic per-task seed derived from (task identity, batch seed)** — a
deterministic function of the content-addressed task identity (M4_SPEC §3.3) and the run's batch seed —
so a task's evaluation is identical across experimental arms regardless of execution order or retries
(D8). The record makes a batch run reproducible and is the object M9's pre-registration will reference.
It composes existing per-episode provenance (M1 §9.1); it introduces no new episode identity field
(D21/D22 boundaries hold).

The five compose as: *loader (available tasks) → adapter (materialize per task) → proposer → verifier →
guarded writer (persist A0 episode)*, bounded by the cost guard and summarized by the run provenance.

## 4. Interfaces (composition contract — shape only)

Stated as responsibilities and composition, not signatures or code.

**Consumes (frozen, unchanged):**

- **M4** — the corpus loader (available-partition tasks), the content-addressed manifest (its hash for
  run provenance), the held-out lock, and the **`GuardedEpisodeWriter`** as the *sole* write path.
- **M1** — the proposer and the LLM client (the base-model seam composes the client).
- **M2** — the verifier, invoked on the adapter-materialized `Task`.
- **M3** — the episode store, reached *only* via the M4 guarded boundary, and `Episode` construction
  including the `arm` provenance field.

**Provides (new, domain-neutral):**

- A **batch-run entry point** that sweeps available tasks and returns/records the produced episodes.
- The **task-materialization adapter interface** (§3.3) with the fixture reference adapter.
- The **cost guard** and the **base-model selection seam** (§3.4).
- The **batch/run provenance** record (§3.5).

**Invariant.** On the experience path there is exactly one writer into the frozen store — the M4
guarded boundary — and every persisted episode is an available-task, cold-arm episode. There is no
second, unguarded write path.

## 5. Boundaries

- **Composition, not modification.** M5 builds on frozen M0–M4 by composition and modifies none of
  them (D12/RK8). The M1 spike remains the frozen single-task reference; M5 adds a *batch* runner
  beside it.
- **Single guarded write path.** The runner persists **only** through the M4 `GuardedEpisodeWriter`;
  it never calls the store directly. Held-out leakage is therefore impossible by construction (D8).
- **Cold only.** A0 reads and writes no memory. M5 builds no retrieval and no write-filter policy.
- **Domain-neutral.** The runner and cost guard treat materials and handles as opaque; all domain
  specifics live behind the §3.3 adapter interface (D9/D22). A non-software corpus sweeps identically.
- **Single fixed base model.** One non-saturating model (D8 §1); no multi-model routing policy.
- **Bounded and single-machine.** The sweep is bounded by the cost guard and runs on one machine
  (D14); no distributed or parallel-scale infrastructure.
- **Taxonomy and identity unchanged.** Verdict taxonomy (D16.7), content-hash identity (D21), and the
  binary/quantitative separation (D22) are untouched.

## 6. Definition of Done

M5 is complete when all of the following hold and are verified in-container and in CI:

1. The batch runner sweeps the **available** partition of a loaded corpus end to end, producing one
   episode per attempted task, each persisted **through the M4 guarded boundary** and tagged with the
   cold-baseline arm (A0).
2. **Held-out is never attempted or persisted** — the runner draws only available tasks, and the
   guarded boundary is the enforcing chokepoint (a held-out or unknown identity is refused, D8).
3. **A0 is cold** — no memory is read or written before, between, or after attempts; each task's seed
   is deterministically derived from (task identity, batch seed), so a re-run is independent and the
   task's evaluation is identical across arms regardless of execution order or retries (D8/D16.1).
4. The **cost guard** bounds the sweep deterministically and, when the bound is reached, halts loudly
   without writing a partial or misleading episode.
5. The **batch/run provenance** records the corpus manifest hash, the arm, the base-model identity,
   the **cost-guard budget/limits**, and the **batch seed**, uniquely identifying the sweep as an
   experiment.
6. **Domain-neutrality holds** — a synthetic non-software corpus sweeps through the identical path via
   the reference adapter; the runner inspects no materials or handles directly.
7. **No frozen M0–M4 file is modified**; the only additions are the new M5 components and additive
   `core/config.py` settings. Future principles D24/D25 are not implemented (D23).
8. All four gates (`ruff check`, `ruff format --check`, `mypy --strict`, `pytest`) are green in the
   container and CI; the milestone is tagged `m5-complete`. A bounded live sweep is the documented
   local acceptance step (CI stays hermetic via a mocked proposer, D16.2).

## 7. Prototype Gate assessment (conditional pipeline stage)

M5 orchestrates already-verified components; its logic (batching, the cold-arm rule, the deterministic
cost guard, run provenance) asserts **no unproven environmental mechanism**. The one candidate unknown
is **live-model batch throughput/latency within the cost budget** across a corpus — an *operational
acceptance* concern, not an architectural one, and one already anticipated by M1's live-acceptance
pattern and the configurable request timeout (M1 known limitations).

**Assessment: the Prototype Gate is not required (no-op).** The hermetic path (mocked proposer) is
CI-gated as in M1, and the bounded live sweep is the acceptance step at Verification. The Gate fires
only if Scientific Review judges batch-scale live behavior a load-bearing unknown, in which case a
single bounded live sweep discharges it before freeze. No architectural assertion requires prototyping.

## 8. Out-of-scope

Deferred by the roadmap (D12) and by design (D15); naming them fixes the M5 boundary:

- **Shared retrieval substrate (M6)** and **write-filter policies A1/A2 (M7)** — no memory retrieval
  and no verified/unfiltered write filters. A0 is memoryless.
- **Anti-grounding arm A3 and ablation arm A4 (D7)** — not run; M5 is A0 only.
- **Frozen checkpointed held-out evaluation (M8)**, **pre-registration freeze (M9)**, and **Stage-1
  statistics / go-no-go (M10)** — M5 produces A0 episodes; it does not evaluate on the held-out set,
  pre-register, or compute the compounding verdict.
- **Multi-model routing and selection policy** beyond a single fixed base model — premature
  abstraction until a milestone needs multiple models (D15/D16.4).
- **Concrete real-dataset adapters** (e.g. SWE-bench ingestion/ETL) — registrations behind the §3.3
  interface, not built here (M4_SPEC §3.2/§6).
- **Any change to frozen M0–M4 contracts**, calibration (I6), the second vertical (D5 rung 2),
  distributed/parallel scale infrastructure (D14), and everything in D15.
- **Future principles D24/D25** — recorded guidance only, not implemented (D23).

---

## Freeze

On the Research Director's freeze this document is immutable. The M5 implementation handoff is produced
next, extracted from this specification, and the M5 engineering that follows manufactures only what is
written here. This specification does not speculate beyond M5.
