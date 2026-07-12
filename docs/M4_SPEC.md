# M4_SPEC — Task corpus loader and mechanically-enforced held-out lock

**Project:** Velith
**Milestone:** M4 — the loop lifts from one fixture task to a *corpus*, under a mechanically-enforced
held-out partition that no experience path can cross.
**Document type:** Frozen engineering contract — **architecture only**. Extracted from the ratified
constitution (`DECISIONS.md`), the vision (`VISION.md`), and the roadmap (D12). It contains no
implementation, no pseudocode, no handoff, and no code. Once frozen it is immutable; the M4
implementation is *extracted from* it and never redesigns it.
**Status:** FINAL — ready for freeze.
**Date:** 2026-07-06.
**Depends on:** `m3-complete` (frozen indexed, integrity-checked episode store).
**Governing decisions:** D2, D4, D5, D6, D7, D8, D9, D11, D12, D15, D16.3, D21, D22.

> **Manufacturing-pipeline position:** Specification → Scientific Review → Feasibility Prototype
> (conditional) → Research Director Review → Freeze Specification → Implementation Handoff →
> Engineering → Verification → Freeze Milestone. This document is the Specification artifact.

---

## 1. Purpose

M1 proved the single-task `propose → verify → log` loop; M2 hardened the verdict; M3 made the
accumulated episodes queryable and integrity-checked. M4 does two things the compounding experiment
(D6/D7/D8) cannot proceed without, and nothing more:

1. **Corpus.** It lifts the loop from one fixture task (D16.3) to a **corpus** of grounded tasks — a
   set of tasks the loop can draw from — replacing the single-fixture loader with a corpus loader.
2. **Generalization-honest discipline.** It installs the **mechanically-enforced held-out lock**
   (D8, condition 3): a partition of the corpus into an *available* set and a *held-out* set, where
   held-out task identities can **never** enter any experience/memory path — enforced in code, not by
   convention.

Both are **domain-neutral**. A task is an opaque specification plus a *verification handle* owned by
the verifier; M4's loader and lock never inspect task materials or the verification mechanism (D9,
D22). The first vertical is software (D4), but software enters only as a **registered corpus
adapter**, never as an architectural assumption — so the identical corpus machinery and held-out lock
carry unchanged up the D5 ladder toward electronics, HDL, and manufacturing intelligence (the Mini
Prometheus north star, D1/D5). M4 introduces **no software-specific assumption**.

M4 builds **directly on the frozen M3 store**: it composes the append-only JSONL log and its derived
index without modifying either.

## 2. Definition of Done

M4 is complete when all of the following hold and are verified in-container and in CI:

1. A **corpus of many tasks** loads into domain-neutral task values, replacing the single-fixture
   assumption, without the loader inspecting task materials or the verification handle.
2. Every loaded task carries a **partition label** — *available* or *held-out* — assigned by a
   content-addressed corpus manifest, deterministically and reproducibly.
3. A **held-out lock** exposes one authoritative exclusion predicate, keyed on **content-addressed
   task identity**, such that relabeling a task cannot move it across the partition.
4. A **single guarded persistence boundary** is the only way the experience path reaches the frozen
   M3 store: it refuses (raises loudly on) any attempt to persist a held-out task's episode, and
   delegates available-task episodes to the frozen `EpisodeStore` unchanged.
5. The partition is **frozen by a manifest hash** that is stable across runs and changes if and only
   if the split changes.
6. **Domain-neutrality is demonstrated:** a synthetic non-software corpus loads, partitions, and
   locks through the identical path.
7. **No frozen M0–M3 contract is modified** (episode schema, store, index, task type, verifier, LLM
   client, spike). M4 is composition, not redesign.
8. All four gates (`ruff check`, `ruff format --check`, `mypy --strict`, `pytest`) are green in the
   container and CI; commits are atomic and conventional; the milestone is tagged `m4-complete`.

## 3. Architecture

Three domain-neutral components composing the frozen substrate. No new architecture is introduced;
these are the minimal seams D12 assigned to M4.

**3.1 Content-addressed corpus manifest.** A description that assigns each task **identity** to
exactly one partition — *available* or *held-out* — and carries a stable content hash over that
assignment. The hash is the object that makes the split **frozen and reproducible**: two loads of the
same manifest yield the same partition, and the hash changes only when the split changes. (This is the
substrate the later pre-registration freeze, M9/D8 condition 2, will reference; M4 establishes it, M4
does not pre-register.)

**3.2 Task corpus loader.** Materializes **many** domain-neutral task values from a corpus source,
each labeled with its partition from the manifest. It treats each task's materials and its
verification handle as **opaque** (D9): it never parses a diff, a test, a netlist, or any
domain-specific content. A concrete corpus source — for example a real software dataset such as
SWE-bench (D4/D16.3) — is a **registered adapter** that conforms to this neutral loader contract; the
adapter is a registration, explicitly **not** part of this architecture and **not** specified here.
This generalizes M1's single-fixture loader without redesigning it.

**3.3 Held-out lock and guarded persistence boundary.** The single, authoritative enforcement point.
It (a) answers one question — *is this task held-out?* — keyed on **content-addressed task identity**
rather than a mutable string label, so identity cannot be forged by renaming (D8 condition 3); and
(b) **guards persistence**: the experience path may write an episode to the frozen M3 store **only**
through this boundary, which persists episodes for available tasks by delegating to the frozen
`EpisodeStore` unchanged, and **raises loudly** rather than persist an episode whose task is
held-out. Enforcement is a raised error at one chokepoint — **mechanical, never discipline** (D8).
The frozen log remains authoritative and its index a rebuildable projection (M3 unchanged).

The three compose as: *manifest → loader (partitioned tasks) → lock (predicate) + guarded boundary
(the only writer into the frozen store on the experience path)*.

## 4. Boundaries

- **Composition, not modification.** M4 builds on the frozen M3 store, the frozen `Episode`, and the
  frozen task value type by composing them. It modifies none of them (Boundary with D12/RK8).
- **Mechanical enforcement.** The held-out exclusion is a code guard at exactly one chokepoint, never
  a naming convention or reviewer vigilance (D8).
- **Domain-neutral.** Neither the loader nor the lock inspects task materials or the verification
  handle; software specifics live only inside a registered adapter, behind the neutral contract
  (D5/D9/D22).
- **Single write chokepoint.** On the experience path there is exactly one way an episode reaches the
  frozen store, and it passes the lock. There is no second, unguarded write path.
- **Identity is content-addressed.** The partition keys on a hash of task-identity material, so the
  lock is robust to relabeling.

## 5. Required file changes (specification only)

Stated at specification granularity — *what the eventual handoff will authorize*, not how it is built.
Names are indicative and are fixed in the handoff.

| Area | Nature | Architectural responsibility |
|---|---|---|
| Corpus manifest + loader module (new) | New, domain-neutral | Load many partitioned task values from a corpus source; carry the content-addressed manifest and its hash (§3.1–§3.2). |
| Held-out lock + guarded persistence boundary module (new) | New, domain-neutral | The authoritative exclusion predicate and the single guarded writer that composes the frozen `EpisodeStore` (§3.3). |
| `core/config.py` | Extend (additive only) | Corpus source location, manifest location, and partition specification, as validated settings with safe defaults (M0 invariant preserved). |
| Tests (new) | New | Hermetic unit + acceptance coverage of §2/§8, including a synthetic non-software corpus. |
| `README.md` (docs) | Extend | Document the corpus loader, the held-out lock, and the partition/manifest at milestone close. |

**Explicitly not changed (frozen):** `episodes/episode.py`, `episodes/store.py`, `episodes/index.py`,
`task.py`, `harness/verifier_sandbox.py`, `llm/client.py`, `runner/spike.py`, and all M0–M3
build/CI/compose files, `docs/DECISIONS.md`, `docs/M3_SPEC.md`, and the earlier frozen specs. The
`core/config.py` change is additive settings only.

## 6. Out-of-scope

Deferred by the roadmap (D12) and by design (D15); naming them fixes the M4 boundary:

- **Batch runner and the cold baseline arm A0 (M5)** — M4 delivers the corpus and the lock, not a
  runner that sweeps them; model routing and the cost guard are M5.
- **Shared retrieval substrate (M6)** and **write-filter policies A1/A2 (M7)** — no memory retrieval
  and no arm write-filters beyond the held-out partition itself.
- **Frozen checkpointed held-out evaluation (M8)** — M4 establishes the lock; it does not evaluate on
  the held-out set.
- **Pre-registration freeze (M9)** and **Stage-1 statistics / go-no-go (M10)**.
- **Any specific dataset ETL/download pipeline** beyond the neutral loader contract; a concrete
  adapter (e.g. SWE-bench) is a registration, not architected here.
- **Any change to frozen M0–M3 contracts**, calibration (I6), the second vertical (D5 rung 2), and
  everything in D15.

## 7. Risks

- **Chokepoint leakage.** If more than one path can write experience into the frozen store, held-out
  could leak in. *Mitigation:* exactly one guarded persistence boundary (§3.3, §4); the frozen store
  is never written on the experience path except through it.
- **Identity smuggling.** A mutable string id could let a held-out task be relabeled into the
  available set. *Mitigation:* the lock keys on content-addressed task identity (§3.3, D8).
- **Domain-neutrality erosion.** Temptation to inspect task materials (software test shape) in the
  loader. *Mitigation:* materials and the verification handle are opaque; software lives only in a
  registered adapter (§4).
- **Split drift.** An unhashed partition cannot be mechanically frozen. *Mitigation:* the
  content-addressed manifest hash freezes the split and changes only when the split changes (§3.1).
- **Coupling to frozen M3.** Enforcement must not require editing the frozen store. *Mitigation:* the
  guarded boundary **composes** `EpisodeStore` (wrapper), never modifies it (§4).
- **Non-determinism in partitioning.** A per-run RNG split would be unreproducible. *Mitigation:*
  partition assignment is deterministic and hash-derived (§3.1).
- **Prototype Gate (conditional pipeline stage).** M4 asserts **no** unproven environmental mechanism:
  it is pure in-process logic over local files that composes the already-verified M3 store. The
  Prototype Gate is therefore assessed **not required (no-op)**; it fires only if Scientific Review
  identifies a load-bearing unproven assumption, which none is anticipated.

## 8. Acceptance criteria

Hermetic, deterministic checks that discharge the Definition of Done:

1. A corpus of N (> 1) tasks loads into domain-neutral task values, each with a partition label, with
   the loader never reading task materials or the verification handle.
2. The held-out lock's predicate is authoritative and content-addressed: every held-out task is
   excluded and every available task admitted, and **relabeling a held-out task does not move it** into
   the available set.
3. The guarded persistence boundary **raises loudly** on a held-out task's episode and **persists an
   available task's episode by delegating to the frozen `EpisodeStore` unchanged** — the resulting log
   line and derived index row are byte-for-byte identical to a direct M3 append (M3 composed, not
   altered).
4. The manifest hash is **stable across repeated loads** and **changes iff** the partition assignment
   changes.
5. A **synthetic non-software corpus** loads, partitions, and locks through the identical path
   (domain-neutrality proven).
6. **No frozen M0–M3 file is modified** (verified by diff scope); the only `core/config.py` change is
   additive settings.
7. All four gates are green in the container and in CI; the acceptance suite adds no
   network-isolation-gated test (zero M4-attributable skips).

---

## Freeze

On the Research Director's freeze this document is immutable. The M4 implementation handoff is produced
next, extracted from this specification, and the M4 engineering that follows manufactures only what is
written here. This specification does not speculate beyond M4.
