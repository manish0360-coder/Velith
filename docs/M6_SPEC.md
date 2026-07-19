# M6_SPEC — Shared retrieval substrate

**Project:** Velith
**Milestone:** M6 — a **read-only, deterministic retrieval substrate** over the accumulated episode
memory, composed onto the frozen M5 batch/store, that later memory-bearing arms will share.
**Document type:** Frozen engineering contract — **architecture only**. Extracted from the ratified
constitution (`DECISIONS.md`), the vision (`VISION.md`), and the roadmap (D12). It contains no
implementation, no pseudocode, no code, no handoff, no commit plan, no tests, and no migration plan.
Once frozen it is immutable; the M6 implementation is *extracted from* it and never redesigns it.
**Status:** FINAL — ready for freeze.
**Date:** 2026-07-06.
**Depends on:** `m5-complete` (frozen batch runner, cold baseline arm A0, deterministic seeding, cost
guard, run provenance), atop the frozen M3 episode store/index, M4 corpus/manifest/held-out lock, and
M1/M2 loop.
**Governing decisions:** D1, D2, D3, D5, D6, D7, D8, D9, D11, D12, D13, D14, D15, D16.1, D16.3, D18,
D21, D22, D23. Future guidance D24/D25 is **not** implemented (D23).

> **Manufacturing-pipeline position:** Specification → Scientific Review → Feasibility Prototype
> (conditional) → Research Director Review → Freeze Specification → Implementation Handoff →
> Engineering → Verification → Freeze Milestone. This document is the Specification artifact.

---

## 1. Purpose

M5 established the batch sweep and the **cold baseline arm A0** — the *memoryless* baseline the
compounding experiment measures against (D6/D7). The next thing that experiment requires, and nothing
more, is a **shared retrieval substrate**: a read-only way to fetch the most relevant prior episodes
from the accumulated grounded experience (D12; the retrieval substrate is explicitly M6, D15).

M6 exists to make that read path **exactly one shared object**, so that when the memory-bearing arms
arrive (A1 unfiltered, A2 verified — M7), they can differ **only** in their write-filter while sharing
an **identical retriever, embedder, and top-k** (D7's decisive invariant). M6 therefore builds
retrieval, and only retrieval: it does not write, does not filter, does not learn, does not evaluate,
and does not alter A0.

M6 is **composition, not a rewrite**. It reads the frozen M3 episode store/index as its memory,
derives its query from the frozen M4 content-addressed task identity and the M5 task material, and
composes them without modifying any frozen contract. It is **domain-neutral** (D9/D22): the memory and
the query are treated as opaque, content-addressed data — never parsed as software — so the substrate
carries unchanged up the D5 ladder toward Mini Prometheus.

## 2. Scope — what M6 is

1. A **read-only retrieval substrate** over the accumulated episode memory (the frozen M3 store/index),
   returning the **top-k** most relevant prior episodes for a query.
2. A **deterministic, domain-neutral similarity/embedding interface** — a single shared component whose
   output is a pure function of its opaque input (same input → same representation), with a fixed
   similarity metric.
3. **Deterministic ranking with content-addressed tie-breaking** — the ordered result is a pure
   function of `(query, memory snapshot, top-k)`; ties are broken by `content_hash` so the ordering is
   total and fully reproducible (D8/D16.1).
4. A **query derivation** whose input is a task's opaque, content-addressed **material** (required; M4
   `task_identity`, M5 `CorpusTask` material) **plus an optional, opaque retrieval context** — prior
   *available* signal (for example previously available verdict `state` and/or quantitative metrics)
   that later milestones (M7–M10) may supply. Both material and context are treated as opaque,
   domain-neutral bytes; M6 itself neither generates nor consumes such context today.
5. **Read-only operation over a provided memory snapshot**, so the substrate can serve a frozen memory
   without mutation (the prerequisite the frozen checkpointed evaluation, M8, will rely on).

**Out of scope — hard boundaries (M6_SPEC §8):** write-filter policies and the memory-bearing arms
A1/A2 (M7); A3/A4 (D7); frozen checkpointed evaluation (M8); pre-registration freeze (M9); Stage-1
statistics/go-no-go (M10); any **learning** or memory-update logic; any change to the A0 runner or its
memoryless behaviour; any modification of the frozen M0–M5 contracts; multi-model routing; concrete
high-quality embedding models as anything but a deferred registration behind the neutral interface;
and everything in D15. **D24/D25 are not implemented (D23).**

## 3. Architecture

Five domain-neutral seams composing the frozen substrate. No new architecture is introduced beyond the
one seam D12/D15 assigns to M6.

**3.1 Memory source (read-only projection of the frozen store).** The retriever's memory is the
accumulated experience already persisted through the frozen M5 guarded boundary — the M3 episode
log/index, read **only**. M6 never writes, never re-orders, and never modifies the store, the index,
or any episode; it composes the frozen read surface (M3 `read_all` / the neutral query accessors).
Because held-out experience was never persisted (M4/M5, D8), the memory is held-out-free by
construction, and M6 adds no path that could reintroduce it.

**3.2 Query derivation.** The substrate derives a deterministic, domain-neutral **query** from a target
task's opaque, content-addressed **material** (required; M4 `task_identity`) **and an optional opaque
retrieval context**. The optional context is additional prior *available* signal a future milestone may
supply — for example previously available verdict `state` and/or quantitative metrics (D22) — carried
as opaque, domain-neutral bytes. M6 itself neither generates nor consumes such context (in particular,
it produces no metrics today); the interface merely **admits** it so M7–M10 are not artificially
constrained. Material and context alike are opaque; the query derivation never parses either as diffs,
tests, or any domain content (D9/D22). With no context supplied, the query is derived from material
alone, exactly as the baseline read path.

**3.3 Deterministic embedding / similarity interface.** A single shared component maps the opaque
query and the opaque neutral representation of each memory episode into a comparable space under a
fixed similarity metric. It is **deterministic** — the same opaque input yields the same
representation, with no sampling and no run-to-run drift — and **domain-neutral** (it embeds opaque
content, never interpreting a domain). The concrete embedder is a *fixed, single* component (no
multi-model routing); a higher-fidelity embedding model is a registration behind this interface and is
out of scope here (§8). Small task models such as embedders are admissible when justified (D14),
provided they satisfy the determinism and neutrality contract.

**3.4 Retriever (deterministic top-k).** Given a query and a memory snapshot, the retriever returns the
**top-k** most similar prior episodes. Ranking is a pure function of `(query, memory snapshot, top-k)`;
**ties break on `content_hash`** so the ordering is total, content-addressed, and bit-reproducible
(D8/D16.1). It returns episodes (or their content-addressed references) read from the frozen store; it
computes no verdict, writes nothing, and never mutates the memory.

**3.5 The single shared substrate (D7 invariant).** M6 delivers **exactly one** retriever, one
embedder, and one top-k. It is the sole retrieval object every future arm consumes, so A1 and A2 (M7)
can differ **only** by their write-filter — the retrieval path is held identical across arms by
construction. M6 does **not** wire retrieval into any arm and does **not** touch the A0 runner: A0
remains memoryless and unchanged.

The five compose as: *memory snapshot (read-only, frozen store) → query (opaque, content-addressed) →
shared deterministic embedding/similarity → deterministic top-k with content-addressed tie-break →
prior episodes*, entirely read-only.

## 4. Interfaces (composition contract — shape only)

Stated as responsibilities and composition, not signatures or code.

**Consumes (frozen, unchanged):**

- **M3** — the episode store/index as the **read-only** memory (`Episode`, its neutral fields, and
  `content_hash` for content-addressed tie-breaking). M6 uses only read operations.
- **M4** — `task_identity` (content-addressed identity) for query derivation, and the guarantee that
  held-out experience was never persisted.
- **M5** — the `CorpusTask` opaque material as the query source; the run/store substrate produced by
  the batch runner as the memory being read.

**Provides (new, domain-neutral):**

- A **retrieval read operation** — given a query (derived from a task's required opaque material and an
  optional opaque retrieval context) and a memory snapshot, return the deterministic top-k prior
  episodes.
- The **shared embedding/similarity interface** (§3.3) with its single deterministic reference
  component.
- The **query derivation** (§3.2), accepting required material and optional opaque retrieval context.

**Invariants.** M6 is **read-only** — it never writes to, re-orders, or mutates the frozen store,
index, or any episode. There is exactly **one** shared retriever/embedder/top-k. Retrieval is a pure,
deterministic, content-addressed function of its inputs. A0's runner and its memoryless behaviour are
untouched.

## 5. Configuration

Additive, validated settings only (M0 invariant: safe defaults, loads with no `.env`). No setting
alters any frozen behaviour.

- **Top-k** — the number of neighbours the retriever returns (a deterministic bound).
- **Embedder identity** — the single fixed, deterministic, domain-neutral embedding component used by
  the shared substrate (no routing; one component).
- **Memory source location** — the read-only episode memory the retriever reads (defaulting to the
  frozen episode store/index path already configured in M3).

These settings parametrise retrieval; they introduce no write path and no per-arm variation.

## 6. Definition of Done

M6 is complete when all of the following hold (verified in-container and in CI at Verification):

1. A **read-only** retrieval substrate returns the top-k most relevant prior episodes for a query
   (derived from required task material and an **optional** opaque retrieval context that M6 admits but
   neither generates nor consumes), composing the frozen M3 store/index and mutating nothing.
2. Retrieval is **deterministic** — identical `(query, memory snapshot, top-k)` yields the identical
   ordered result — with **content-addressed tie-breaking** on `content_hash` (D8/D16.1).
3. The embedding/similarity component is a **single shared, deterministic, domain-neutral** interface;
   the same opaque input always yields the same representation, with no run-to-run drift.
4. The substrate is the **one shared retriever/embedder/top-k** (D7): no per-arm variation exists, so
   future arms can differ only by write-filter.
5. **A0 is unchanged** — the A0 runner does not consult retrieval and remains memoryless; no frozen
   M0–M5 file is modified; the only additions are the new read-only retrieval component and additive
   `core/config.py` settings.
6. **Domain-neutrality holds** — a non-software memory retrieves through the identical path; neither
   the query nor the memory is parsed as any domain (D9/D22).
7. **Held-out safety preserved** — retrieval reads only persisted (available-partition) experience and
   cannot surface a held-out episode (they were never persisted, D8); the substrate operates read-only
   over a provided memory snapshot, so a frozen memory can be served without mutation.
8. All four gates (`ruff check`, `ruff format --check`, `mypy --strict`, `pytest`) are green in the
   container and CI; the milestone is tagged `m6-complete`. Retrieval adds no network-isolation-gated
   test, so there are zero M6-attributable skips.

## 7. Prototype Gate assessment (conditional pipeline stage)

Unlike M4/M5, M6 asserts **one load-bearing mechanism whose viability is not yet established: the
determinism and reproducibility of the embedding/similarity component.** The entire experiment's
reproducibility (D8/D16.1) and the D7 "identical retriever across arms" invariant depend on the
embedder producing stable, reproducible representations — a property that floating-point and model
execution do not guarantee for free.

**Assessment: the Prototype Gate is armed and is expected to be REQUIRED.** Before Freeze, a narrow
feasibility prototype should establish that the chosen embedding/similarity mechanism yields
**deterministic, reproducible retrieval** — the same query over the same memory snapshot returns the
identical ordered top-k — to the determinism level the grounding signal already meets (D18). A red
prototype returns the specification to Specification (the mechanism must be chosen so determinism
holds); it never proceeds to Engineering on an unproven embedder. This mirrors the R3 prototype that
established M2's isolation mechanism. No other M6 assertion requires prototyping.

## 8. Out-of-scope

Deferred by the roadmap (D12) and by design (D15); naming them fixes the M6 boundary:

- **Write-filter policies and the memory-bearing arms A1/A2 (M7)** — M6 provides the shared read path;
  it writes nothing and filters nothing. The A3/A4 arms (D7) are likewise out.
- **Any use of retrieval by an arm, and any change to the A0 runner** — A0 stays memoryless; wiring
  retrieval into a running arm is M7.
- **Frozen checkpointed held-out evaluation (M8)** — M6 can serve a read-only snapshot, but it does not
  define the freeze/checkpoint policy or evaluate anything.
- **Pre-registration freeze (M9)** and **Stage-1 statistics / go-no-go (M10)** — no statistical
  evaluation.
- **Learning or memory-update logic** — retrieval is read-only; nothing is trained, re-weighted, or
  updated.
- **Generating or consuming quantitative metrics** — M6 *admits* an optional opaque retrieval context
  (which a future milestone may populate with verdict state and/or metrics) but neither produces nor
  interprets metrics today (D22); that is future-milestone work.
- **Multi-model routing** — the embedder is a single fixed component.
- **A concrete high-fidelity embedding model / ANN index / vector database** — such a component is a
  deferred registration behind the neutral, deterministic interface, not architected here (no premature
  abstraction, D12/D15).
- **Any modification of frozen M0–M5 contracts**, calibration (I6), the second vertical (D5 rung 2),
  and everything in D15.
- **Future principles D24/D25** — recorded guidance only, not implemented (D23).

---

## Freeze

On the Research Director's freeze this document is immutable. The M6 implementation handoff is produced
next, extracted from this specification, and the M6 engineering that follows manufactures only what is
written here. This specification stops at the M6 architectural boundary and does not speculate beyond
M6.
