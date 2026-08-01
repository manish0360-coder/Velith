# M8_SPEC — Frozen checkpointed held-out evaluation (arms A0, A1, A2)

**Project:** Velith
**Milestone:** M8 — the arms are **measured for generalization**: each of A0, A1, and A2 is evaluated
against the **held-out** partition at **frozen checkpoints**, through one identical, deterministic
evaluation harness, without any held-out experience ever entering memory.
**Document type:** Engineering contract — **architecture only**. Extracted from the ratified
constitution (`DECISIONS.md`), the vision (`VISION.md`), and the roadmap (D12). It contains no
implementation, no pseudocode, no code, no handoff, no commit plan, no tests, and no migration plan.
Once frozen it is immutable; the M8 implementation is *extracted from* it and never redesigns it.
**Status:** DRAFT — first complete draft, pending Scientific Review.
**Date:** 2026-07-06.
**Depends on:** `m7-complete` (frozen write-filter arms A1/A2 over the identical shared retrieval
substrate), atop the frozen M6 retrieval substrate, M5 batch runner and cold arm A0, M4 corpus and
held-out lock, M3 episode store/index, and M1/M2 loop and hardened verifier.
**Governing decisions:** D1, D2, D3, D5, D6, D7, D8, D9, D11, D12, D14, D15, D16.1, D16.2, D16.7, D17,
D18, D21, D22, D23. Future guidance D24/D25 is **not** implemented (D23).

> **Manufacturing-pipeline position:** Specification → Scientific Review → Feasibility Prototype
> (conditional) → Research Director Review → Freeze Specification → Implementation Handoff →
> Engineering → Verification → Freeze Milestone. This document is the Specification artifact.

---

## 1. Purpose

M5 recorded the memoryless baseline **A0**. M6 built the read-only retrieval substrate. M7 defined the
two memory arms **A1 (unfiltered)** and **A2 (verified)** as write-filters over that identical
substrate. What none of them did is **measure whether any of this generalizes**: retrieval has been
wired into no attempt, and no arm has yet been scored on tasks it could not have memorized. M8 supplies
exactly that instrument, and nothing more: a **frozen, checkpointed, held-out evaluation** of A0, A1,
and A2.

This is the program's moment of truth (D1/D6). The compounding hypothesis is that verification-filtered
memory (A2) generalizes to **held-out** tasks better than unfiltered memory (A1), which in turn beats no
memory (A0) — and that the gap widens as experience accumulates. To measure that honestly, three things
are non-negotiable. The measure must be **held-out**, so it reflects generalization and not recall (D8).
It must be **the deterministic verifier's verdict on the held-out hidden test**, never a model's opinion
of its own work (D3/D11 — no LLM-as-judge). And it must be **frozen at a checkpoint**, so every arm is
scored against the same fixed state of its own knowledge and the number is reproducible (D16.1/D18).

M8 is **composition, not a rewrite**. It adds no store, changes no verdict taxonomy, defines no new arm,
and modifies no frozen M0–M7 contract. It is **domain-neutral** (D9/D22): the held-out task, the
retrieved memory, and the recorded outcome are opaque, content-addressed data, and the evaluation
harness never interprets task content. Crucially, M8 **preserves the held-out lock**: it *reads*
held-out tasks to attempt them, but a held-out outcome is recorded only as a segregated **evaluation
measurement** and can never become experience — the frozen guarded boundary still fail-closes (D8).

## 2. Scope — what M8 is

1. A **checkpoint** — a frozen, content-addressed capture of an arm's memory state at an evaluation
   point, immutable and deterministic, against which the arm is scored. A0's checkpoint is empty by
   construction.
2. A **held-out evaluation set** — the held-out partition (M4), read through the frozen loader as the
   generalization measure, and never admitted into any arm's memory.
3. A **memory-conditioned held-out attempt** — the single evaluation attempt path, identical for all
   three arms: A0 attempts memorylessly (the frozen cold path); A1 and A2 condition the frozen proposer
   on their retrieved memory at the checkpoint (the frozen M6 retriever over the M7 arm memory view),
   read-only. The arm's memory is the **only** thing that differs.
4. A **segregated evaluation record** — held-out outcomes written to an evaluation sink that is **not**
   a memory source and never the experience path; the recorded measurement is the deterministic verifier
   verdict (with the held-out secondary), never a model score (D3/D11).
5. **Evaluation provenance** — a content-addressed evaluation identity (checkpoint identity, held-out
   manifest hash, arm, base model, evaluation seed, cost-guard limits) that makes each held-out
   evaluation reproducible and comparable across arms at the same checkpoint.

**Boundary of this milestone.** M8 **measures**; it does not **conclude**. It computes no comparative
statistic, no aggregate, no effect size, and no go/no-go — it records per-task held-out outcomes and
their evaluation identity, and stops (D22). It does not run the **experience-accumulation** loop that
grows an arm's memory by attempting the *available* partition (that memory-writing execution remains
deferred, M7_SPEC §8); M8 evaluates whatever experience exists at the checkpoint, and at an empty
checkpoint A0, A1, and A2 coincide — the honest cold-start control. **The memory-conditioned attempt
(§3.3) belongs in M8** — the Research Director has ruled it here, not in a prior milestone: M7 is frozen
and must not be reopened, and M8 is the program's first measurement milestone, so the attempt that first
makes a memory arm measurable is an M8 concern. No frozen milestone is redesigned to accommodate it.

## 3. Architecture

Five domain-neutral seams composing the frozen substrate. No new architecture is introduced beyond the
one instrument D12/D15 assigns to M8, and no frozen M0–M7 contract is reopened.

**3.1 Checkpoint.** A checkpoint is a **frozen, content-addressed capture of an arm's memory state** at
the moment of evaluation — concretely, the arm's M7 memory snapshot (the arm memory view over the
experience accumulated so far), fixed and immutable. It exists so that evaluation is **reproducible**
(the same checkpoint always yields the same memory) and **comparable** (every arm, and every re-run, is
scored against a pinned state rather than a moving one).

**Checkpoint identity is order-independent.** A checkpoint's identity is derived from the *content* of
the memory it captures — the content-addressed set of admitted episode identities — computed canonically
so that it does **not** depend on the order in which experience was accumulated, persisted, or presented.
Two checkpoints are the same iff they hold the same episodes, regardless of history; this inherits the
M7 arm-memory-view guarantee that identical episodes plus an identical arm yield an identical, canonically
ordered snapshot (D8/D16.1/D18).

**A0's checkpoint is empty by construction** — the memoryless baseline — and all three arms pass through
the identical checkpoint machinery. An **empty checkpoint** (A0 always, and A1/A2 before any experience
has accumulated) is the same empty snapshot for every arm, with the same identity; §3.3 requires that
evaluation at an empty checkpoint therefore produces **bit-for-bit identical prompts** across A0, A1, and
A2. A checkpoint is a *read* of frozen experience; forming one writes and mutates nothing.

**3.2 Held-out evaluation set.** The evaluation set is the **held-out** partition of the frozen corpus
(M4), obtained through the frozen loader's held-out view. It is the generalization measure precisely
because no experience path was ever allowed to write it into memory (D8): an arm cannot have memorized
what it was structurally prevented from retaining. M8 **reads** these tasks in order to attempt them,
and this is the one place the program deliberately touches held-out material — under the strict guarantee
of §3.4 that the *outcome* never re-enters experience. The held-out split is fixed by its manifest hash
(M4); evaluating against a changed split is a different, separately identified evaluation.

**3.3 Memory-conditioned held-out attempt.** The single evaluation attempt path, **identical for all
three arms**. Against a held-out task, the harness produces one grounded attempt through the frozen
`propose → verify` loop (M1/M2): for **A0** the proposal is memoryless (the existing cold path); for
**A1** and **A2** the proposal is **conditioned on the arm's retrieved memory** — the frozen M6
retriever, run over the arm's M7 memory view at the checkpoint (§3.1), supplies the relevant prior
episodes as read-only attempt context. This is the first milestone in which retrieved memory actually
informs an attempt, and it is confined to **read-only held-out evaluation**. It stays in M8, not M7: M7
is frozen, and M8 is the program's first measurement milestone, so the attempt that makes a memory arm
measurable belongs here.

**Prompt and context assembly — only memory content may differ.** The attempt's prompt is assembled by a
single fixed procedure shared by all three arms: a **fixed** task portion, derived only from the held-out
task, plus a **memory-context portion** built by a **fixed, deterministic** rendering of the arm's
retrieved episodes into attempt context. The task portion, the ordering, the delimiters, the framing
text, and the assembly procedure are **byte-identical across A0, A1, and A2**; the *only* thing that may
vary between arms is the **content of the retrieved memory** placed in the memory-context portion. For
A0, and for A1/A2 at an **empty checkpoint**, the retrieved memory is empty and the memory-context
portion is therefore identical, so the assembled prompt is **bit-for-bit identical** across all three
arms — the cold-start control is exact, not approximate. Any prompt difference that is not wholly
explained by differing retrieved-memory content is an **invalid measurement** (§3.5).

The arm's memory is thus the **only** difference between the three runs of the harness; everything else —
the proposer, the verifier, the held-out task, the per-task seed, and the assembly procedure — is
identical, so any difference in held-out outcome is attributable to memory alone (D6/D7). The per-task
attempt is deterministically seeded from the held-out task identity and the evaluation seed (§3.5), so
evaluation is reproducible to the determinism level the grounding signal already meets (D18).
Retrieval during evaluation uses the frozen M6 embedder in a **stateless, no-cache** mode: it holds no
state across tasks or arms and consults no cross-attempt cache, so a retrieval for one arm or task can
never influence another and every retrieval is a pure function of its checkpoint and query. The frozen
proposer and verifier are **used as-is and modified in no way** — conditioning is the caller assembling
context, not a change to any frozen interface.

**3.4 Segregated evaluation record.** A held-out outcome is recorded to an **evaluation sink that is not
a memory source and is never the experience path**. Two properties make this safe and make the
measurement meaningful:

- **Held-out can never become experience.** Evaluation outcomes are written only to the evaluation sink,
  never through the frozen `GuardedEpisodeWriter`; and were one ever mis-routed there, the guarded
  boundary still **fail-closes** on the held-out identity (D8). The held-out lock is therefore preserved
  by construction *and* independently enforced — evaluation adds no path by which held-out experience
  could leak into any arm's memory.
- **The measurement is the verifier's verdict, never a model's opinion.** The recorded held-out outcome
  is the deterministic verifier verdict on the held-out hidden test (with the held-out secondary /
  model-gap signal, D21), across the frozen verdict taxonomy (D16.7) — never a model score and never an
  LLM-as-judge (D3/D11). What is stored is a grounded measurement of reality.
- **Only already-frozen deterministic quantitative fields may accompany the verdict.** The evaluation
  record may carry the **deterministic** quantitative fields the frozen M3 `Episode` already defines —
  the token counts (`prompt_tokens`, `completion_tokens`), which live inside the content-hash boundary
  and are therefore reproducible — recorded verbatim as they already are. M8 introduces **no new metric**,
  computes **no aggregate or statistic**, and records **no non-deterministic quantity** as a measurement
  (the excluded timing fields `latency_seconds`/`verify_seconds` remain provenance, never a result). This
  admits nothing beyond what M3 already grounds (D22; D3).

**3.5 Evaluation provenance and the held-out-safety invariant.** Each held-out evaluation carries a
**content-addressed evaluation identity** — the checkpoint identity (§3.1), the held-out manifest hash
(§3.2), the arm, the base model, the evaluation seed, and the cost-guard limits — recorded alongside the
per-task outcomes so the whole evaluation is reproducible and so results are only ever compared **within
the same checkpoint and held-out split**. The invariant M8 must never violate: evaluation is
**read-only against memory and the experience log**, writes only to the segregated sink, **admits no
held-out episode into any arm's memory**, uses the **identical harness** across A0/A1/A2, and
**computes no statistic and reaches no decision** (D22; M10). A violation of any of these is not a
degradation but an **invalid measurement**, and must fail loudly.

The five compose as: *checkpoint (frozen arm memory) → held-out evaluation set → memory-conditioned
held-out attempt (identical harness) → segregated evaluation record → evaluation provenance*.

## 4. Interfaces (composition contract — shape only)

Stated as responsibilities and composition, not signatures or code.

**Consumes (frozen, unchanged):**

- **M1/M2** — the `propose → verify` loop and the hardened, deterministic verifier (two-phase isolation,
  flake detection, held-out secondary), used as-is to produce each held-out attempt's grounded verdict.
- **M3** — the `Episode` and its neutral outcome provenance, and the store's read surface. Read-only.
- **M4** — the frozen corpus loader's **held-out** view and the manifest hash; the held-out lock and the
  guarded persistence boundary, whose fail-closed guarantee M8 relies on and does not weaken.
- **M5** — the deterministic per-task seeding and run-provenance patterns, and the cold arm A0 attempt
  path, reused for evaluation. **No frozen provenance field is added or altered.**
- **M6/M7** — the single shared retriever/embedder/top-k and the arm memory view, used **as-is** to form
  a checkpoint and to supply read-only attempt context; the write-filters and the D7 shared-retrieval
  invariant are untouched.

**Provides (new, domain-neutral):**

- The **checkpoint** (§3.1) and the **held-out evaluation set** access (§3.2).
- The **memory-conditioned held-out attempt** harness, identical across A0/A1/A2 (§3.3).
- The **segregated evaluation record** and sink (§3.4) and the **evaluation provenance / identity**
  (§3.5).

**Invariants.** Evaluation is held-out and read-only against memory and the experience log. No held-out
episode enters any arm's memory; the guarded boundary still fail-closes. The measurement is the
deterministic verifier verdict, never a model score (D3/D11). The harness is identical across the three
arms — the arm's memory is the sole difference (D6/D7). Evaluation is deterministic to the grounding
signal's determinism level (D18) and its identity is content-addressed. No statistic is computed and no
decision is made (D22). A0 remains memoryless; the verdict taxonomy (D16.7) and episode identity (D21)
are unchanged.

## 5. Configuration

Additive, validated settings only (M0 invariant: safe defaults, loads with no `.env`). No setting alters
any frozen behaviour.

- **Evaluation seed** — the fixed seed from which each held-out task's per-attempt seed is deterministically
  derived, recorded in the evaluation provenance as part of its identity.
- **Evaluation sink location** — where the segregated held-out evaluation records are written; distinct
  from the experience log and never a memory source.
- **Evaluation cost-guard limits** — deterministic bounds on the held-out evaluation sweep (e.g. maximum
  held-out tasks, attempts, tokens; `0` unbounded), recorded as part of the evaluation identity, reusing
  the frozen M5 cost-guard discipline.

**Deliberately absent (and forbidden):** any per-arm retrieval setting (it would void D7, M7_SPEC §5);
any setting that would route a held-out outcome into the experience path or a memory source; and any
statistic, threshold, or decision parameter (that is M9/M10).

## 6. Definition of Done

M8 is complete when all of the following hold (verified in-container and in CI at Verification):

1. A **checkpoint** captures an arm's memory state as a frozen, content-addressed, immutable snapshot
   whose identity is **order-independent** (the same episodes yield the same checkpoint regardless of
   accumulation or persistence order); the same experience always yields the same checkpoint, and A0's
   checkpoint is empty by construction.
2. Each of **A0, A1, and A2** is evaluated on the **held-out** partition through **one identical
   harness**, so the arm's memory is the only difference between the three evaluations. The prompt is
   assembled by a single fixed procedure in which **only the retrieved-memory content may differ** across
   arms; at an **empty checkpoint** the assembled prompt is **bit-for-bit identical** across A0, A1, and
   A2.
3. The **memory-conditioned held-out attempt** produces a grounded verdict via the frozen `propose →
   verify` loop: A0 memoryless; A1/A2 conditioned read-only on their retrieved memory at the checkpoint,
   with the frozen proposer and verifier modified in no way. Retrieval during evaluation is **stateless
   and cache-free** — it holds no state across tasks or arms — so no attempt can influence another.
4. Every held-out outcome is the **deterministic verifier verdict** on the held-out hidden test (with the
   held-out secondary / model-gap signal, D21) across the frozen taxonomy — **never** a model score or
   LLM-as-judge (D3/D11). The record may carry only the **already-frozen deterministic** quantitative
   fields M3 defines (the token counts inside the content-hash boundary), verbatim; M8 introduces no new
   metric and computes no statistic (D22).
5. Held-out outcomes are written **only** to the segregated evaluation sink; **no held-out episode enters
   any arm's memory or the experience log**, and the frozen guarded boundary still fail-closes on a
   held-out identity (D8).
6. Evaluation is **deterministic** to the grounding signal's determinism level (D18): the same arm,
   checkpoint, held-out task, and evaluation seed always yield the same recorded outcome, independent of
   execution order and retries (D16.1).
7. Each evaluation records a **content-addressed evaluation identity** (checkpoint identity, held-out
   manifest hash, arm, base model, evaluation seed, cost-guard limits), so results are reproducible and
   comparable only within the same checkpoint and split; the sweep is bounded by the evaluation cost
   guard and halts loudly without a partial record.
8. **No statistic is computed and no decision is made** — M8 records per-task held-out measurements and
   their identity, and nothing more (D22; M9/M10 out of scope).
9. **Domain-neutrality and determinism hold** — a non-software held-out set evaluates through the
   identical path; no frozen M0–M7 file is modified, the only additions being the M8 evaluation seams and
   additive configuration; all four gates (`ruff check`, `ruff format --check`, `mypy --strict`,
   `pytest`) are green in the container and CI, with zero M8-attributable skips (the harness is hermetic:
   the live held-out sweep is the documented local acceptance step, D16.2); the milestone is tagged
   `m8-complete`.

## 7. Prototype Gate assessment (conditional pipeline stage)

M8 introduces **no unproven environmental mechanism.** Its seams compose already-proven parts: the M6
retriever's determinism (established by the discharged M6 Prototype Gate), the M2 verifier's L4
determinism and network isolation, the M1 loop, and the M5 seeding and cost-guard discipline. The one
genuinely new composition — feeding retrieved memory into a held-out attempt as read-only context — is
deterministic prompt assembly over a frozen checkpoint; the underlying model attempt is reproducible only
to the determinism level the grounding signal already meets (D18), which is the **same** envelope A0's
existing live sweep operates in, not a new mechanism.

**Assessment: the Prototype Gate is not required (no-op).** It fires only if Scientific Review judges
some M8 assertion a load-bearing unknown — the plausible candidate being whether the memory-conditioned
attempt (§3.3) preserves the established determinism envelope end-to-end, which a narrow feasibility
prototype (identical held-out outcome for a fixed arm, checkpoint, task, and seed) could confirm if Review
wishes. Absent such a finding, engineering proceeds directly from the frozen specification.

## 8. Out-of-scope

Deferred by the roadmap (D12) and by design (D15); naming them fixes the M8 boundary:

- **Any statistic, aggregate, effect size, comparison, or go/no-go decision** — M8 records per-task
  held-out measurements only; **Stage-1 statistics and the go/no-go gate are M10**, and the
  **pre-registration freeze is M9**.
- **The experience-accumulation loop** — running an arm on the *available* partition to **grow** its
  memory (memory-*writing* execution) is not built here; M8 evaluates whatever experience exists at the
  checkpoint (M7_SPEC §8).
- **Any admission of held-out experience into memory**, any change to the held-out lock or the guarded
  boundary, and any change to the A0 runner's memoryless behaviour.
- **Any per-arm retrieval variation** — substituting, re-configuring, or wrapping the M6
  retriever/embedder/top-k per arm is forbidden; it would void D7.
- **Any new arm** beyond A0/A1/A2 — the anti-grounding arm A3 and the ablation arm A4 (D7) remain
  deferred.
- **Any LLM-as-judge or model-derived score** as an evaluation measurement — the held-out measure is the
  deterministic verifier verdict alone (D3/D11).
- **Deleting, mutating, re-ordering, or re-writing any grounding record** — the episode log is immutable
  (D2/D3).
- **Multi-model routing, concrete real-dataset adapters, calibration (I6), the second vertical (D5 rung
  2), and everything in D15.**
- **Future principles D24/D25** — recorded guidance only, not implemented (D23).

---

## Freeze

On the Research Director's freeze this document becomes immutable. The M8 implementation handoff is
produced next, extracted from this specification, and the M8 engineering that follows manufactures only
what is written here. This specification stops at the M8 architectural boundary and does not speculate
beyond M8.
