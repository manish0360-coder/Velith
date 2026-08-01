# M8_IMPLEMENTATION_HANDOFF

**Project:** Velith
**Milestone:** M8 — frozen checkpointed held-out evaluation of arms A0, A1, and A2.
**Document type:** Frozen implementation handoff. It is *extracted from* `docs/M8_SPEC.md` (frozen) and
adds no design. Every clause traces to a spec section. Engineering manufactures only what is written
here; a genuine contradiction with the frozen spec **stops work and is reported** — it never licenses
editing the spec or this handoff.
**Status:** Ready for engineering.
**Date:** 2026-07-06.
**Extracted from:** `docs/M8_SPEC.md` §1–§8. **Governing decisions:** D1, D2, D3, D5, D6, D7, D8, D9,
D11, D12, D14, D15, D16.1, D16.2, D16.7, D17, D18, D21, D22, D23. Future guidance D24/D25 is **not**
implemented (D23).
**Manufacturing-pipeline position:** Specification → Scientific Review → **Prototype Gate (§11 —
assessed not required)** → Implementation Handoff (this document) → One Atomic Commit → Docker
Verification → Commit → Review → Next Commit.

---

## 1. Objective

Build the **frozen checkpointed held-out evaluation** instrument (M8_SPEC §1): measure each of **A0**
(memoryless), **A1** (unfiltered memory), and **A2** (verified memory) against the **held-out**
partition, at a **frozen checkpoint**, through **one identical deterministic harness**, and record the
per-task held-out outcome as a **segregated evaluation measurement** that can never become experience.

This is the program's first measurement milestone (D1/D6): retrieval finally informs a real attempt, but
only in **read-only held-out evaluation**. The honest measure is (a) **held-out**, so it reflects
generalization not recall (D8); (b) **the deterministic verifier's verdict** on the held-out hidden
test, never a model's opinion (D3/D11 — no LLM-as-judge); and (c) **frozen at a checkpoint**, so every
arm is scored against the same pinned state and the number is reproducible (D16.1/D18).

M8 is **composition, not a rewrite** (§1): it adds no store, changes no verdict taxonomy, defines no new
arm, and modifies no frozen M0–M7 contract. It **preserves the held-out lock** — it reads held-out tasks
to attempt them, but a held-out outcome is written only to the evaluation sink and the frozen
`GuardedEpisodeWriter` still fail-closes on a held-out identity (D8). It is **domain-neutral** (D9/D22):
task, retrieved memory, and recorded outcome are opaque, content-addressed data; the harness never
interprets task content.

## 2. Scope

**In scope (M8_SPEC §2/§3):**

1. A **checkpoint** — a frozen, content-addressed, **order-independent** capture of an arm's memory state
   (the M7 arm memory view), A0's empty by construction (§3.1).
2. A **held-out evaluation set** — read-only access to the held-out partition via the frozen M4 loader
   (§3.2).
3. A **deterministic prompt/context assembly** in which **only retrieved-memory content may differ**
   across arms, byte-identical otherwise, and bit-for-bit identical at an empty checkpoint (§3.3).
4. A **memory-conditioned held-out attempt** — one identical harness: A0 memoryless; A1/A2 conditioned
   read-only on their checkpoint memory via the frozen M6 retriever used **stateless / no-cache**;
   driving the frozen `propose → verify` loop unchanged (§3.3).
5. A **segregated evaluation record + sink** — the deterministic verifier verdict (with held-out
   secondary) plus only the already-frozen deterministic token counts; written to a sink that is **not**
   a memory source and never the experience path (§3.4).
6. **Evaluation provenance / identity** — a content-addressed evaluation identity, and a cost-guarded
   held-out sweep runner composing all of the above (§3.5, §5).

**Out of scope — hard boundaries (M8_SPEC §2/§8):** any **statistic, aggregate, effect size, comparison,
or go/no-go** (Stage-1 statistics/go-no-go is **M10**; pre-registration freeze is **M9**); the
**experience-accumulation loop** that grows memory on the *available* partition (memory-*writing*
execution stays deferred, M7_SPEC §8); any admission of held-out experience into memory or any change to
the held-out lock, the guarded boundary, or the A0 runner; **any per-arm retrieval variation** (voids
D7); any new arm beyond A0/A1/A2 (A3/A4 deferred); **any LLM-as-judge or model-derived score** as a
measurement; deleting/mutating/re-ordering any grounding record; multi-model routing; concrete
real-dataset adapters; calibration (I6); the second vertical (D5 rung 2); everything in D15. **D24/D25
are not implemented (D23).**

M8 uses **Python standard library plus the frozen M0–M7 packages** only; the reference embedding is
in-process and the evaluation sink is JSONL. It introduces **no new dependency**, and therefore **no
Docker, compose, or CI change**.

## 3. Files allowed to change

Nothing outside this list may be touched. Module names follow M8_SPEC ("architecture only"; the new
`evaluation` package is the domain-neutral home for the held-out evaluation instrument).

| Path | Commit(s) | Nature |
|---|---|---|
| `src/velith/core/config.py` | M8-C1 | Extend (additive settings only): evaluation seed, evaluation sink location, evaluation cost-guard limits (M8_SPEC §5). |
| `.env.example` | M8-C1 | Document the new `VELITH_EVAL_*` settings. |
| `tests/unit/test_config.py` | M8-C1 | Extend: defaults + overrides of the new settings. |
| `src/velith/evaluation/__init__.py` | M8-C2 | **New**: package marker for the held-out evaluation layer. |
| `src/velith/evaluation/checkpoint.py` | M8-C2 | **New**: order-independent, content-addressed capture of an arm's memory (composes the M7 arm memory view); A0 empty (§3.1). |
| `tests/unit/test_evaluation_checkpoint.py` | M8-C2 | **New**: checkpoint identity/order-independence/empty tests. |
| `src/velith/evaluation/heldout_set.py` | M8-C3 | **New**: read-only access to the held-out partition via the frozen M4 loader (§3.2). |
| `tests/unit/test_evaluation_heldout_set.py` | M8-C3 | **New**: held-out-only access tests. |
| `src/velith/evaluation/context.py` | M8-C4 | **New**: deterministic prompt/context assembly — only memory content differs; empty → bit-identical (§3.3). |
| `tests/unit/test_evaluation_context.py` | M8-C4 | **New**: assembly determinism / bit-identity tests. |
| `src/velith/evaluation/attempt.py` | M8-C5 | **New**: the single memory-conditioned held-out attempt; stateless retrieval; frozen `propose → verify` (§3.3). |
| `tests/unit/test_evaluation_attempt.py` | M8-C5 | **New**: identical-harness / A0-memoryless / stateless tests (mocked proposer + stub verifier). |
| `src/velith/evaluation/record.py` | M8-C6 | **New**: the segregated `EvaluationRecord` (verdict + secondary + frozen deterministic token counts) (§3.4). |
| `src/velith/evaluation/sink.py` | M8-C6 | **New**: the evaluation sink — not a memory source, never the experience path (§3.4). |
| `tests/unit/test_evaluation_record_sink.py` | M8-C6 | **New**: record content + sink-segregation tests. |
| `src/velith/evaluation/provenance.py` | M8-C7 | **New**: content-addressed evaluation identity (§3.5). |
| `tests/unit/test_evaluation_provenance.py` | M8-C7 | **New**: evaluation-identity tests. |
| `src/velith/evaluation/runner.py` | M8-C8 | **New**: the cost-guarded held-out sweep composing C2–C7 for one arm + checkpoint (§3.5, §5). |
| `tests/unit/test_evaluation_runner.py` | M8-C8 | **New**: sweep / cost-guard / no-partial-record tests. |
| `tests/unit/test_evaluation_heldout_safety_invariant.py` | M8-C9 | **New**: the **permanent check** — no held-out into memory, identical harness, stateless, no statistic (§3.5). |
| `tests/integration/test_m8_heldout_evaluation.py` | M8-C10 | **New**: hermetic end-to-end evaluation acceptance (§6). |
| `README.md` | M8-C11 | Add the "M8 — frozen checkpointed held-out evaluation" section. |

## 4. Files forbidden to change

- **Frozen M7 arm layer — used strictly as-is:** `src/velith/arms/**`. M8 forms a checkpoint from the arm
  memory view and reads the arm's write-filter through it; it does not modify identity, filters, binding,
  or the memory view (M8_SPEC §3.1/§4).
- **Frozen M6 retrieval substrate — used strictly as-is, stateless:** `src/velith/retrieval/**`. M8 uses
  the single shared retriever/embedder/top-k unchanged and never substitutes, re-configures, wraps, or
  parameterises it per arm — that would void D7 (M8_SPEC §8).
- **Frozen M5 batch layer — including the A0 runner and the cost guard:** `src/velith/batch/**`. M8 reuses
  the cold A0 attempt path and the `CostGuard` by composition, and modifies neither. **No frozen
  provenance field is added or altered.**
- **Frozen M4 corpus / held-out lock:** `src/velith/corpus/**`. M8 reads only the held-out view and relies
  on the guarded boundary's fail-closed guarantee; it weakens neither.
- **Frozen M1/M2 loop and verifier:** `src/velith/agent/proposer.py`, `src/velith/harness/verifier_sandbox.py`,
  `src/velith/llm/client.py`, `src/velith/task.py`, `src/velith/runner/spike.py`,
  `src/velith/episodes/**`. Used as-is to produce each held-out attempt's grounded verdict; the proposer
  and verifier interfaces are not modified.
- **Infra (no new dependency):** `docker/verifier.Dockerfile`, `docker-compose.yml`,
  `.github/workflows/**`, `pyproject.toml`, `.pre-commit-config.yaml` (M8_SPEC §2).
- **Frozen record:** `docs/DECISIONS.md`, `docs/M8_SPEC.md`, and all earlier frozen specs/handoffs.
- **Freeze-Milestone-only:** `docs/PROJECT_STATE.md`, `docs/NOTES.md` — updated only at the M8 Freeze
  Milestone by the Research Director, never inside an M8 code commit.
- **Unrelated:** all Node/Next files.
- **Per commit:** any file not in that commit's row of §3.

## 5. Dependency graph (implementation order)

Strictly linear; one atomic commit at a time. No commit begins before its predecessor is committed green.
**The Prototype Gate is assessed not required (§11) and does not gate M8-C1.**

```
M8-C1 (config: evaluation seed, sink location, evaluation cost-guard limits)
   │
   ▼
M8-C2 (evaluation/checkpoint.py: order-independent content-addressed capture of arm memory; A0 empty)
   │
   ▼
M8-C3 (evaluation/heldout_set.py: read-only held-out access via the frozen M4 loader)
   │
   ▼
M8-C4 (evaluation/context.py: deterministic assembly; only memory content differs; empty → bit-identical)
   │
   ▼
M8-C5 (evaluation/attempt.py: memory-conditioned held-out attempt; stateless retrieval; frozen loop)
   │
   ▼
M8-C6 (evaluation/record.py + sink.py: segregated EvaluationRecord; sink is never memory/experience)
   │
   ▼
M8-C7 (evaluation/provenance.py: content-addressed evaluation identity)
   │
   ▼
M8-C8 (evaluation/runner.py: cost-guarded held-out sweep; composes C2–C7; halts loudly, no partial)
   │
   ▼
M8-C9 (permanent check: no held-out into memory; identical harness; stateless; no statistic)
   │
   ▼
M8-C10 (integration: hermetic held-out evaluation acceptance)
   │
   ▼
M8-C11 (docs: README M8 section)
```

Invariants carried across the chain: evaluation is **held-out** and **read-only** against memory and the
experience log; it writes **only** to the segregated sink; **no held-out episode enters any arm's
memory** (the guarded boundary still fail-closes); the measurement is the **deterministic verifier
verdict, never a model score** (D3/D11); the **harness is identical** across A0/A1/A2 with the arm's
memory as the sole difference (D6/D7); retrieval is **stateless / no-cache**; evaluation is
**deterministic** to the grounding signal's level (D18) with a **content-addressed identity**; **no
statistic is computed and no decision is made** (D22); A0 stays memoryless and untouched.

## 6. Commit breakdown (atomic; one logically complete unit each)

**M8-C1 — `feat: evaluation settings`**
Additive `Settings` for the **evaluation seed**, the **evaluation sink location** (distinct from the
experience log, never a memory source), and the **evaluation cost-guard limits** (max held-out tasks,
attempts, tokens; `0` unbounded), each with safe defaults (M0 invariant). Document the `VELITH_EVAL_*`
variables; extend `test_config.py` for default + override. **No per-arm retrieval setting and no
statistic/threshold/decision parameter** (M8_SPEC §5, forbidden). No behaviour beyond declaration.

**M8-C2 — `feat: evaluation checkpoint`**
New `evaluation/checkpoint.py`: a frozen, **content-addressed, order-independent** capture of an arm's
memory state at an evaluation point, formed by composing the frozen M7 arm memory view (M8_SPEC §3.1).
Its identity derives from the content-addressed **set** of admitted episode identities, so it is
independent of accumulation/persistence order; **A0's checkpoint is empty by construction**. Forming a
checkpoint writes and mutates nothing. Unit tests: identical episodes → identical checkpoint identity
regardless of order; A0 (and empty A1/A2) yield the same empty checkpoint with the same identity;
checkpoint formation is read-only.

**M8-C3 — `feat: held-out evaluation set access`**
New `evaluation/heldout_set.py`: read-only access to the **held-out** partition through the frozen M4
loader's held-out view, carrying the manifest hash (M8_SPEC §3.2). Reads only; opaque materials, never
inspected. Unit tests: only held-out tasks are surfaced (no available task leaks in); the manifest hash
is carried; access is read-only and domain-neutral (a non-software held-out set flows identically).

**M8-C4 — `feat: deterministic evaluation context assembly`**
New `evaluation/context.py`: the single fixed procedure assembling an attempt's prompt/context from a
**fixed task portion** (held-out task only) plus a **fixed, deterministic rendering** of the arm's
retrieved episodes (M8_SPEC §3.3). The task portion, ordering, delimiters, framing, and procedure are
**byte-identical across arms**; only the **retrieved-memory content** may vary. Unit tests: assembly is
deterministic; **empty retrieved memory → bit-for-bit identical output across A0/A1/A2**; two different
memories differ **only** in the memory-context portion; no domain parsing occurs.

**M8-C5 — `feat: memory-conditioned held-out attempt`**
New `evaluation/attempt.py`: the single evaluation attempt path, **identical for all three arms**,
composing C2–C4 with the frozen `propose → verify` loop (M1/M2). A0 attempts memorylessly (the frozen
cold path); A1/A2 retrieve their checkpoint memory via the frozen M6 retriever used **stateless /
no-cache** (no state across tasks or arms, no cross-attempt cache), assemble context (C4), and drive the
**unchanged** frozen proposer and verifier. The per-task seed is derived deterministically from the
held-out task identity and the evaluation seed. Unit tests (mocked proposer + stub verifier — hermetic):
the harness is identical across arms with memory the sole input difference; at an empty checkpoint all
three produce the identical assembled attempt input; retrieval holds no cross-attempt state; the frozen
proposer/verifier are invoked unmodified.

**M8-C6 — `feat: segregated evaluation record and sink`**
New `evaluation/record.py` and `evaluation/sink.py`: the `EvaluationRecord` carries the **deterministic
verifier verdict** (with the held-out secondary / model-gap signal, D21) across the frozen taxonomy
(D16.7), plus **only** the already-frozen deterministic token counts (`prompt_tokens`,
`completion_tokens`) recorded verbatim — no new metric, no aggregate, no non-deterministic quantity
(M8_SPEC §3.4). The sink writes records to a location **distinct from the experience log** and is **never
a memory source**; records never pass through the frozen `GuardedEpisodeWriter`. Unit tests: the record
holds the verdict + secondary + token counts and no model score; the sink is not readable as memory and
is distinct from the experience log; a held-out outcome is never routed to the experience path.

**M8-C7 — `feat: evaluation provenance`**
New `evaluation/provenance.py`: a **content-addressed evaluation identity** recording the checkpoint
identity, the held-out manifest hash, the arm, the base model, the evaluation seed, and the cost-guard
limits (M8_SPEC §3.5). Same evaluation → same identity; any change to a component → new identity. Unit
tests: identity is stable and content-addressed; it changes iff a component changes; it binds results to
a single checkpoint and split.

**M8-C8 — `feat: held-out evaluation runner`**
New `evaluation/runner.py`: the cost-guarded held-out sweep for one **(arm, checkpoint)**, composing
C2–C7 — read the held-out set, run the identical attempt per task, write each `EvaluationRecord` to the
sink under the evaluation identity — bounded by the frozen M5 `CostGuard` (composed, not modified),
halting **loudly** at a limit **without writing a partial record** (M8_SPEC §3.5/§5). Unit tests (mocked
proposer + stub verifier): the sweep evaluates the held-out set end to end and writes to the sink only;
the cost guard halts loudly with no partial record; nothing is written to the experience log or any
memory source; A0/A1/A2 run through the identical runner.

**M8-C9 — `test: held-out safety and identical-harness invariant`**
New `tests/unit/test_evaluation_heldout_safety_invariant.py`: the **permanent check** (M8_SPEC §3.5) —
`evaluation/**` never writes through `GuardedEpisodeWriter` or into any memory source; the guarded
boundary still fail-closes on a held-out identity even if a record were mis-routed; the harness is
identical across A0/A1/A2 (arm memory the sole difference); retrieval is stateless/no-cache; and **no
statistic, aggregate, or decision** is computed. A violation is an **invalid measurement** and must
**fail loudly**. Includes a non-vacuity assertion (a deliberately mis-routed/held-out write is caught).

**M8-C10 — `test: hermetic m8 held-out evaluation acceptance`**
New `tests/integration/test_m8_heldout_evaluation.py` (hermetic; no model, no network — mocked proposer +
stub verifier, in-process embedding): end-to-end over a checkpoint — A0/A1/A2 evaluated on held-out
through the identical harness; empty-checkpoint attempts bit-for-bit identical across arms; the recorded
outcome is the deterministic verifier verdict (with secondary) plus frozen token counts and **no model
score**; records land only in the segregated sink; **no held-out episode enters any arm's memory or the
experience log** and the guarded boundary fail-closes; evaluation is deterministic for a fixed
(arm, checkpoint, task, seed); the evaluation identity is content-addressed; **no statistic is
computed**; a non-software held-out set evaluates through the identical path. Covers M8_SPEC §6 DoD 1–8.

**M8-C11 — `docs: document held-out evaluation`**
Add the "M8 — frozen checkpointed held-out evaluation" section to `README.md` (checkpoints, the held-out
measure, the identical memory-conditioned harness, the segregated sink, the deterministic-verdict
measurement, the evaluation identity, and the new `VELITH_EVAL_*` settings). Claims only what C1–C10
verify. No `PROJECT_STATE`/`NOTES` edits.

## 7. Docker verification gates (run after every commit, before it is made)

The identical containerized sequence M1–M7 used. A commit is made **only** when all four are green:

```
docker compose run --rm verifier bash -lc \
  "ruff check . && ruff format --check . && mypy src tests && pytest -q"
```

- `ruff check .` — lint (E,F,I,N,UP,B,SIM,RUF; line-length 100).
- `ruff format --check .` — formatting.
- `mypy src tests` — `--strict`.
- `pytest -q` — full suite.

**CI stays hermetic.** The evaluation tests inject a mocked proposer and a stub verifier and use the
in-process embedding — no live model, no network, no `CAP_SYS_ADMIN`-gated path — so `pytest -q` reports
**zero M8-attributable skips**. The bounded **live** held-out sweep (real proposer + verifier) is the
documented local acceptance step (D16.2). No new dependency, so no Docker/compose/CI file changes.

## 8. Rollback condition for every commit

Uniform trigger, applied per commit: **if any of the four gates in §7 is red, or the commit's own
acceptance assertions fail, do not commit.** Discard the working tree for that commit
(`git restore`/`git checkout --`), and either fix within the *same* atomic commit or stop. Per-commit
specifics:

- **M8-C1** — roll back if config fails to load with no `.env`, if a per-arm retrieval or a
  statistic/threshold/decision setting is introduced (forbidden, §5), if a default/override test fails,
  or if any gate is red.
- **M8-C2** — roll back if checkpoint identity depends on accumulation/persistence order, if identical
  episodes yield different checkpoints, if A0's checkpoint is non-empty, if checkpoint formation writes or
  mutates anything, or if any gate is red.
- **M8-C3** — roll back if any available task is surfaced, if the manifest hash is dropped, if access
  writes or mutates the corpus, if a domain is parsed, or if any gate is red.
- **M8-C4** — roll back if assembly is non-deterministic, if an empty checkpoint does not yield
  bit-for-bit identical output across arms, if anything other than the memory-context portion varies with
  memory, if a domain is parsed, or if any gate is red.
- **M8-C5** — roll back if the harness differs across arms by anything other than memory, if A0 is not
  memoryless, if retrieval holds cross-attempt state or consults a cache, if the frozen proposer/verifier
  is modified, if the attempt is non-deterministic for a fixed (arm, checkpoint, task, seed), or if any
  gate is red.
- **M8-C6** — roll back if the record carries a model score or any non-deterministic/new metric, if the
  sink is readable as a memory source, if it coincides with the experience log, if a record can reach the
  `GuardedEpisodeWriter`, or if any gate is red.
- **M8-C7** — roll back if the evaluation identity is not content-addressed, if it fails to change when a
  component changes, if it omits a required component, or if any gate is red.
- **M8-C8** — roll back if the sweep writes to the experience log or a memory source, if the cost guard
  does not halt loudly, if a partial record is written, if the runner is not identical across arms, or if
  any gate is red.
- **M8-C9** — roll back if the invariant is not provably enforced (a held-out/mis-routed write is not
  caught, the harness is not identical, retrieval is stateful, or a statistic is computed), if the check
  does not fail loudly, or if any gate is red.
- **M8-C10** — roll back if any acceptance assertion (identical harness, empty-checkpoint bit-identity,
  deterministic-verdict measurement, sink segregation, held-out-free memory, determinism, content-addressed
  identity, no statistic, domain-neutral flow) fails, or if any gate is red.
- **M8-C11** — roll back if docs introduce a claim not verified by C1–C10, or if any gate is red.

**Frozen-spec guard (stop condition).** If a rollback is caused by a **genuine contradiction with
`docs/M8_SPEC.md`** (not a mere bug) — for example, memory-conditioning cannot be achieved without
modifying the frozen proposer/verifier interface, or a held-out attempt cannot be recorded without a path
that could re-enter experience — **stop immediately and report the contradiction to the Research
Director.** Do not edit the frozen spec or this handoff to make the code pass, do not reinterpret the
architecture, do not weaken the held-out lock, do not introduce an LLM-as-judge, and do not introduce
D24/D25 to resolve it (D23).

## 9. Definition of Done (mapping to M8_SPEC §6)

M8 is done when all hold, verified in-container and in CI:

1. A **checkpoint** captures an arm's memory as a frozen, content-addressed, **order-independent**,
   immutable snapshot; identical episodes → identical checkpoint regardless of order; A0's is empty —
   **§6.1** (C2).
2. **A0, A1, A2** are evaluated on **held-out** through **one identical harness** in which only
   retrieved-memory content may differ, and an **empty checkpoint yields bit-for-bit identical prompts** —
   **§6.2** (C3+C4+C5; acceptance C10).
3. The **memory-conditioned attempt** produces a grounded verdict via the frozen `propose → verify` loop
   (A0 memoryless; A1/A2 read-only conditioned), the frozen proposer/verifier unmodified, retrieval
   **stateless/cache-free** — **§6.3** (C5).
4. Every outcome is the **deterministic verifier verdict** (with held-out secondary, D21) across the
   frozen taxonomy — **never** a model score/LLM-as-judge — carrying only the already-frozen deterministic
   token counts, no new metric or statistic — **§6.4** (C6).
5. Outcomes are written **only** to the segregated sink; **no held-out episode enters any arm's memory or
   the experience log**, and the guarded boundary still fail-closes — **§6.5** (C6/C8; enforced C9).
6. Evaluation is **deterministic** to the grounding level (D18): same (arm, checkpoint, task, seed) →
   same recorded outcome, independent of order/retries — **§6.6** (C5/C8; acceptance C10).
7. Each evaluation records a **content-addressed evaluation identity** (checkpoint identity, manifest
   hash, arm, base model, evaluation seed, cost-guard limits); the sweep is cost-bounded and halts loudly
   with no partial record — **§6.7** (C7/C8).
8. **No statistic is computed and no decision is made** — per-task measurements and their identity only —
   **§6.8** (C6–C8; enforced C9).
9. **Domain-neutrality and determinism hold** — a non-software held-out set evaluates through the
   identical path; no frozen M0–M7 file is modified, the only additions being the M8 evaluation seams and
   additive configuration; all four gates green in the container and CI with zero M8-attributable skips —
   **§6.9** (every commit; acceptance C10).

**Freeze Milestone (Research Director, after DoD 1–9):** update `docs/PROJECT_STATE.md` and
`docs/NOTES.md`, then tag `m8-complete`. These are not M8 code commits.

## 10. Risks

Extracted from M8_SPEC §3, §5, §7, and the composition boundary:

- **Held-out leakage into memory — the fatal risk.** If a held-out outcome ever became experience, the
  generalization measure is destroyed (D8). *Mitigation:* the sink is not a memory source and never the
  experience path; records never touch `GuardedEpisodeWriter`, which still fail-closes; `corpus/**` and
  `arms/**` are forbidden (§4); the permanent check (C9) catches a mis-route.
- **LLM-as-judge creep.** Recording a model score as a measurement would void the ground truth (D3/D11).
  *Mitigation:* the record carries only the verifier verdict + secondary + frozen token counts (C6); §8
  stop condition; §8 out-of-scope.
- **Harness divergence across arms.** Any difference other than memory confounds the measurement (D6/D7).
  *Mitigation:* one identical attempt/runner (C5/C8); the fixed assembly where only memory content differs
  (C4); the empty-checkpoint bit-identity check (C4/C10); the permanent check (C9).
- **Non-deterministic evaluation.** Cross-attempt retrieval state, a cache, or order dependence would
  break reproducibility (D16.1/D18). *Mitigation:* stateless/no-cache retrieval and deterministic seeding
  (C5); order-independent checkpoint identity (C2).
- **Conditioning cannot compose the frozen proposer.** If memory context cannot be supplied without
  modifying the frozen proposer/verifier, that is a **stop condition**, not a modification. *Mitigation:*
  conditioning is caller-side context assembly (C4); §8 frozen-spec guard.
- **Scope creep into statistics or accumulation.** Computing an aggregate, or growing memory on available,
  is out of scope. *Mitigation:* `batch/**` forbidden (§4); no statistic/decision setting (§5); the
  permanent check (C9); §8 out-of-scope.
- **Per-arm retriever divergence.** *Mitigation:* `retrieval/**` forbidden (§4); the substrate is used
  stateless and unchanged; no per-arm retrieval setting.

## 11. Prototype gate handling (assessed NOT REQUIRED before M8-C1)

Per M8_SPEC §7, M8 introduces **no unproven environmental mechanism**. Its seams compose already-proven
parts: the M6 retriever's determinism (discharged M6 Prototype Gate), the M2 verifier's L4 determinism
and isolation, the M1 loop, and the M5 seeding and cost-guard discipline. The one new composition —
feeding retrieved memory into a held-out attempt as read-only context — is deterministic prompt assembly
over a frozen checkpoint; the underlying model attempt is reproducible only to the determinism level the
grounding signal already meets (D18), the **same** envelope A0's existing live sweep operates in.

- **Assessment: the Prototype Gate is a no-op for M8 and does not gate M8-C1.** Engineering proceeds
  directly from the frozen specification on the Research Director's authorization.
- It fires **only** if the Research Director judges some M8 assertion a load-bearing unknown — the
  plausible candidate being whether the memory-conditioned attempt (§3.3) preserves the established
  determinism envelope end-to-end (a narrow prototype: identical held-out outcome for a fixed arm,
  checkpoint, task, and seed).
- If, during engineering, a load-bearing unknown is nonetheless discovered, that is a **stop condition**:
  report it to the Research Director under §8's frozen-spec guard. Do not prototype it inside a commit,
  do not edit the frozen spec, do not reinterpret the architecture, and do not introduce D24/D25 (D23).

---

*End of handoff. Engineering begins at M8-C1 only after the Research Director authorizes it; one atomic
commit at a time, stopping for review after each. Composition over modification; the architecture is
frozen; implementation is extracted from `docs/M8_SPEC.md` only. Future principles D24/D25 are not
implemented (D23).*
