# M7_SPEC — Write-filter policies (arms A1 and A2)

**Project:** Velith
**Milestone:** M7 — the **experience-retention policy** becomes the single manipulated variable: two
write-filters, unfiltered (A1) and verification-filtered (A2), over an identical shared retrieval
substrate.
**Document type:** Engineering contract — **architecture only**. Extracted from the ratified
constitution (`DECISIONS.md`), the vision (`VISION.md`), and the roadmap (D12). It contains no
implementation, no pseudocode, no code, no handoff, no commit plan, no tests, and no migration plan.
Once frozen it is immutable; the M7 implementation is *extracted from* it and never redesigns it.
**Status:** DRAFT — first complete draft, pending Scientific Review.
**Date:** 2026-07-06.
**Depends on:** `m6-complete` (frozen read-only deterministic retrieval substrate), atop the frozen M5
batch runner and cold arm A0, M4 corpus/held-out lock, M3 episode store/index, and M1/M2 loop.
**Governing decisions:** D1, D2, D3, D5, D6, D7, D8, D9, D11, D12, D14, D15, D16.7, D17, D18, D21,
D22, D23. Future guidance D24/D25 is **not** implemented (D23).

> **Manufacturing-pipeline position:** Specification → Scientific Review → Feasibility Prototype
> (conditional) → Research Director Review → Freeze Specification → Implementation Handoff →
> Engineering → Verification → Freeze Milestone. This document is the Specification artifact.

---

## 1. Purpose

M5 established the memoryless cold baseline **A0**. M6 established the **single shared, read-only,
deterministic retrieval substrate**. M7 supplies the one remaining piece the compounding experiment
requires, and nothing more: the **write-filter** — the policy deciding which grounded experience is
*retained in an arm's memory*.

This is the load-bearing manipulation of the entire program (D6/D7). The decisive contrast is **A2
strictly beats A1**: if verification-filtered memory does no better than unfiltered memory, the honest
verdict is that retrieval alone explains any gain and grounding adds nothing. For that contrast to mean
anything, the two arms must be identical in every respect except the filter — D7 is explicit that A1 and
A2 **must share the identical retriever, embedder, and top-k**, and that *if their retrievers ever
differ, the experiment is void*. M7 therefore holds M6's substrate fixed and varies only retention.

M7 is **composition, not a rewrite**. It adds no store, changes no verdict, deletes no grounding record,
and modifies no frozen M0–M6 contract. It is **domain-neutral** (D9/D22): a filter decides admission
from the episode's neutral, already-grounded outcome fields, never by interpreting task content.

## 2. Scope — what M7 is

1. A closed set of **write-filter policies** — **A1 (unfiltered)** and **A2 (verified)** — each a
   deterministic, domain-neutral admission predicate over an already-persisted episode.
2. **Arm identity** for A1 and A2, recorded through the frozen `arm` provenance field alongside the
   frozen A0, with a **fixed, recorded arm → filter binding** so a run's retention policy is explicit.
3. An **arm memory view** — a read-only, deterministic projection that scopes the persisted experience
   to an arm and applies that arm's write-filter, yielding the memory snapshot the **shared M6
   substrate** retrieves over.
4. The **D7 shared-retrieval invariant**, enforced structurally and by a permanent check: every arm uses
   the identical retriever, embedder, and top-k; the write-filter is the **only** difference.

**Boundary of this milestone.** M7 defines *what each arm's memory is*. It does **not** execute the
arms and does **not** condition proposals on retrieved memory — exactly as M6 built retrieval without
wiring it into any arm. Arm execution (memory-conditioned attempts over the corpus) composes these
frozen pieces later and is out of scope here (§8). Scientific Review is invited to rule explicitly on
this boundary.

## 3. Architecture

Four domain-neutral seams composing the frozen substrate. No new architecture is introduced beyond the
one manipulation D12/D15 assigns to M7.

**3.1 Arm identity.** M7 admits exactly two new arms — **A1 (unfiltered memory)** and **A2 (verified
memory)** — recorded on each episode through the **frozen** `arm` provenance field, alongside the frozen
**A0** (cold, memoryless), which is untouched. The arm set is closed for M7; the anti-grounding (A3) and
ablation (A4) arms of D7 are out of scope (§8). Each arm is bound to exactly one write-filter by a
**fixed, recorded mapping**, so naming the arm names the retention policy — no run can carry an
ambiguous or undeclared filter.

The mapping is **total, injective, and immutable for the lifetime of a run.** Every admitted arm has
exactly one filter and every filter exactly one arm; the binding is resolved once when the run's identity
is fixed and **cannot be changed, re-bound, overridden, or selected dynamically thereafter** — not per
task, per attempt, per query, or in response to any observed outcome. A run therefore has exactly one
retention policy for its entire duration. This is not ergonomics: a filter that could shift mid-run would
make the manipulated variable non-constant within the arm, so the recorded `arm` would no longer identify
what the memory contains, and the A1/A2 contrast (D6/D7) would be uninterpretable.

**3.2 Write-filter policies.** A write-filter is a **deterministic, domain-neutral admission predicate**
over an already-persisted episode. It reads only neutral, already-grounded outcome provenance — the
verdict state, the held-out secondary (model-gap) signal, and the flake flag — and never inspects the
task's material, prompt, or change (D9/D22).

- **A1 — unfiltered.** Admits **every** episode of the arm regardless of outcome — every verdict
  category, contradicted or uncontradicted by the secondary, flaky or not. This is the RAG/null control
  (D7): it isolates what plain retrieval of experience contributes, with no grounding filter.
- **A2 — verified.** Admits only **grounded, trustworthy verification signal** — exactly the two
  categories defined below, and nothing else.

**Definition — verified success.** An episode is a *verified success* when **both** hold:

1. its verdict state is **`PASSED`** — the sole admitted success category; and
2. the held-out secondary signal **does not contradict** it, i.e. `secondary_passed` is `True` or absent
   (`None`, no secondary was run). `secondary_passed` **`False`** is **excluded**: the primary suite
   passed while the held-out suite refuted it, which is precisely the model gap (D21) — a solution that
   satisfies the visible test without solving the task. Retaining it as knowledge would seed memory with
   the exact wireheading the program exists to detect.

**Definition — verified failure.** An episode is a *verified failure* when its verdict state is
**`FAILED`** — the sole admitted failure category. `FAILED` means a candidate was produced, applied, and
actually **disposed of by the verifier**: the hidden test ran and returned a negative result. This is a
real measurement of reality, first-class learning data, never an error (D16.7). The secondary signal does
not gate admission here, because there is no success claim for the held-out suite to contradict.

**Excluded from A2 — the exhaustive complement.** Over the closed verdict taxonomy (D16.7):

- **`PATCH_APPLY_FAILED`** — a candidate existed but never reached the hidden test, so **no verification
  occurred**. There is no grounded outcome to learn from, only a mechanical failure to apply.
- **`NO_PATCH`** — no candidate was produced at all; nothing was verified.
- **`INFRA_ERROR`** — not a grounded outcome in the first place but a failure of the loop itself (D16.7),
  and by the frozen loop's contract it does not arise as retained experience.
- **Any episode flagged `flaky`**, in **every** category above — including an otherwise-qualifying
  `PASSED` or `FAILED`. Flake detection marks the *measurement* as untrustworthy (D17), and an
  untrustworthy measurement is by definition not verified signal. This is exactly the downstream use of
  `flaky` provenance that D17 anticipated for memory policies.

A2's admission is therefore decided **solely** by the triple (`verdict_state`, `secondary_passed`,
`flaky`) — all neutral, already-grounded provenance the frozen episode carries — and never by inspecting
task material, prompt, or change (D9/D22).

The exact admission boundary of A2 is the scientific heart of the experiment and is stated here for
Scientific Review to ratify or refine before freeze.

**3.3 Arm memory view.** A read-only, deterministic projection that (a) scopes persisted experience to a
single arm and (b) applies that arm's write-filter, producing the memory snapshot the shared substrate
retrieves over.

**The projection order is fixed and total:**

> **Episode Store → Arm Filter → Memory Snapshot → Shared Retriever**

Each stage is entered exactly once, in this order, with no stage skipped, reordered, merged, or
re-entered:

1. **Episode Store** — the frozen authoritative record is read through its verified read surface, scoped
   to the arm. This is the **only** source of experience; nothing enters the pipeline downstream of it.
2. **Arm Filter** — the arm's bound write-filter (§3.2) is applied to those episodes. This is the **only**
   stage at which admission is decided, and therefore the **only** stage at which the arms differ.
3. **Memory Snapshot** — the admitted episodes are fixed as an immutable snapshot. Once formed it is
   never mutated, appended to, re-ordered, or re-filtered.
4. **Shared Retriever** — the unchanged M6 substrate (§3.4) ranks over that snapshot and returns top-k.

The ordering carries the experiment's validity. Filtering strictly **before** the snapshot, and the
snapshot strictly **before** retrieval, is what makes the write-filter the sole manipulated variable: no
arm-dependent selection may occur at or after stage 4, since filtering *during* or *after* retrieval
would make the retrieval step itself arm-dependent and void D7. Equally, no episode may enter at stages
2–4 from any source other than stage 1.

Two invariants make this composition safe:

- **The grounding record stays complete and immutable.** Filtering is *admission into an arm's memory*,
  never deletion or mutation of a grounding record. Every grounded outcome remains in the authoritative
  episode log exactly as the frozen store wrote it (D2/D3/D16.7). The log, the derived index, and the
  guarded persistence boundary are unchanged.
- **Held-out safety is inherited, not re-derived.** The projection reads only experience already
  persisted through the frozen M4/M5 guarded boundary, so it is held-out-free by construction (D8); M7
  adds no path that could reintroduce held-out experience.

**3.4 The shared-retrieval invariant (D7).** Every arm retrieves through the **one** M6
retriever/embedder/top-k. Retrieval is not parameterised by arm, and no arm may substitute, re-configure,
or wrap the substrate. This invariant is **structural** — the arm supplies only a filtered memory view to
an unchanged shared retriever — and is additionally guarded by a **permanent check** that the arms'
retrieval configuration is identical, as D7's consequences require. A divergence is not a degradation but
a **void experiment**, and must fail loudly.

The four compose along the fixed order of §3.3: *arm identity → its bound write-filter → arm memory view
(Episode Store → Arm Filter → Memory Snapshot) → the single shared M6 retrieval substrate*.

## 4. Interfaces (composition contract — shape only)

Stated as responsibilities and composition, not signatures or code.

**Consumes (frozen, unchanged):**

- **M3** — the `Episode` and its neutral outcome provenance (verdict state, held-out secondary signal,
  flake flag, `arm`, `content_hash`) and the store's read surface. Read-only.
- **M4/M5** — the guarded persistence boundary and its held-out guarantee; the frozen `arm` field and the
  run-provenance record, which already carries the arm and therefore, through the fixed binding of §3.1,
  the retention policy. **No frozen provenance field is added or altered.**
- **M6** — the read-only memory source, the query derivation, the single shared embedder, and the
  deterministic top-k retriever, used **as-is**.

**Provides (new, domain-neutral):**

- The **write-filter policies** A1 and A2 (§3.2) and the **arm → filter binding** (§3.1).
- The **arm memory view** (§3.3).
- The **shared-retrieval invariant** guard (§3.4).

**Invariants.** Retrieval is identical across arms — the write-filter is the sole difference (D7).
Filters are deterministic and domain-neutral. No grounding record is deleted, mutated, or re-ordered.
Held-out experience remains absent from every arm's memory. A0 remains memoryless and unchanged. The
verdict taxonomy (D16.7) and episode identity (D21) are untouched.

## 5. Configuration

Additive, validated settings only (M0 invariant: safe defaults, loads with no `.env`). No setting alters
any frozen behaviour.

- **Active arm** — which arm (and therefore, by the fixed binding, which write-filter) a run operates
  under. The closed M7 set is A1 and A2; A0 remains the frozen memoryless baseline.

**Deliberately absent (and forbidden):** any *per-arm* retrieval setting. Top-k, the embedder identity,
and the memory source remain the single shared M6 configuration for every arm. Introducing an arm-scoped
retrieval knob would void D7 and is out of scope (§8).

## 6. Definition of Done

M7 is complete when all of the following hold (verified in-container and in CI at Verification):

1. Two **write-filter policies** exist — A1 (unfiltered) and A2 (verified) — each a deterministic,
   domain-neutral admission predicate over an already-persisted episode, reading only neutral grounded
   outcome provenance.
2. **A1 admits every episode** of its arm regardless of outcome — every verdict category, contradicted or
   not, flaky or not (the RAG/null control, D7).
3. **A2 admits exactly the two defined categories and nothing else** (§3.2): a *verified success*
   (`PASSED` with `secondary_passed` `True` or absent) and a *verified failure* (`FAILED`). It excludes
   `PASSED` contradicted by the held-out secondary (`secondary_passed` `False`, the model gap, D21),
   `PATCH_APPLY_FAILED`, `NO_PATCH`, `INFRA_ERROR`, and **every** episode flagged `flaky` in any category
   (D17). Admission is decided solely by (`verdict_state`, `secondary_passed`, `flaky`).
4. Each arm is bound to **exactly one** write-filter by a total, injective mapping that is **fixed when
   the run's identity is fixed and immutable for the run's lifetime** — never re-bound or selected
   dynamically per task, attempt, query, or observed outcome — surfaced through the frozen `arm`
   provenance; no run can carry an undeclared, ambiguous, or shifting retention policy.
5. The **arm memory view** applies the fixed projection order **Episode Store → Arm Filter → Memory
   Snapshot → Shared Retriever** (§3.3), with no stage skipped, reordered, or re-entered, and no episode
   entering from any source other than the store; the log, index, and guarded boundary are unmodified;
   **no grounding record is deleted, mutated, or re-ordered**.
6. **Snapshot identity is exact and reproducible**: identical persisted episodes plus an identical arm
   **always** produce an identical memory snapshot — the same admitted episodes in the same order,
   byte-for-byte equivalent — across processes, runs, and machines, independent of interpreter hash
   seeding and of the order in which experience was presented or persisted (D8/D16.1/D18). Two arms over
   the same store differ **only** where their write-filters differ.
7. The **D7 invariant holds and is permanently checked**: A1 and A2 retrieve through the identical
   retriever, embedder, and top-k; the write-filter is the only difference; divergence fails loudly.
8. **Held-out safety and A0 are preserved** — no arm's memory contains a held-out episode, and A0 remains
   memoryless and unchanged.
9. **Domain-neutrality and determinism hold** — a non-software memory filters and retrieves through the
   identical path; no frozen M0–M6 file is modified, the only additions being the M7 policy/view seams
   and additive configuration; all four gates (`ruff check`, `ruff format --check`, `mypy --strict`,
   `pytest`) are green in the container and CI, with zero M7-attributable skips; the milestone is tagged
   `m7-complete`.

## 7. Prototype Gate assessment (conditional pipeline stage)

M7 asserts **no unproven environmental mechanism.** Its seams are pure, in-process, deterministic
predicate logic over neutral fields the frozen episode already carries, plus a read-only projection over
the already-verified M3 store and the already-proven M6 substrate — whose retrieval determinism was
established by the discharged M6 Prototype Gate. Nothing new depends on the environment, the filesystem,
or a model.

**Assessment: the Prototype Gate is not required (no-op).** It fires only if Scientific Review judges
some M7 assertion a load-bearing unknown — most plausibly the A2 admission boundary of §3.2, which is a
*scientific* ratification question rather than a feasibility one, and is better settled in review than by
prototype. Absent such a finding, engineering proceeds directly from the frozen specification.

## 8. Out-of-scope

Deferred by the roadmap (D12) and by design (D15); naming them fixes the M7 boundary:

- **Arm execution and memory-conditioned proposing** — M7 defines what each arm's memory *is*; running
  the arms and conditioning attempts on retrieved episodes composes these frozen pieces later (§2).
- **Any change to the A0 runner or its memoryless behaviour**, and any modification of the frozen M0–M6
  contracts.
- **Any per-arm retrieval variation** — substituting, re-configuring, or wrapping the M6
  retriever/embedder/top-k per arm is forbidden; it would void D7.
- **The anti-grounding arm A3 and the ablation arm A4** (D7).
- **Frozen checkpointed held-out evaluation (M8)**, **pre-registration freeze (M9)**, and **Stage-1
  statistics / go-no-go (M10)** — M7 produces arms; it does not evaluate, compare, or compute any
  statistic, and it draws no conclusion about compounding.
- **Deleting, mutating, re-ordering, or re-writing any grounding record** — the episode log is immutable
  (D2/D3).
- **Generating or consuming quantitative metrics** (D22), multi-model routing, concrete real-dataset
  adapters, calibration (I6), the second vertical (D5 rung 2), and everything in D15.
- **Future principles D24/D25** — recorded guidance only, not implemented (D23).

---

## Freeze

On the Research Director's freeze this document becomes immutable. The M7 implementation handoff is
produced next, extracted from this specification, and the M7 engineering that follows manufactures only
what is written here. This specification stops at the M7 architectural boundary and does not speculate
beyond M7.
