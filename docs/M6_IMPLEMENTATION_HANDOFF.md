# M6_IMPLEMENTATION_HANDOFF

**Project:** Velith
**Milestone:** M6 — shared retrieval substrate (read-only, deterministic).
**Document type:** Frozen implementation handoff. It is *extracted from* `docs/M6_SPEC.md` (FINAL,
frozen) and adds no design. Every clause traces to a spec section. Engineering manufactures only what
is written here; a genuine contradiction with the frozen spec **stops work and is reported** — it never
licenses editing the spec or this handoff.
**Status:** Ready for engineering.
**Date:** 2026-07-06.
**Extracted from:** `docs/M6_SPEC.md` §1–§8. **Governing decisions:** D1, D2, D3, D5, D6, D7, D8, D9,
D11, D12, D13, D14, D15, D16.1, D16.3, D18, D21, D22, D23. Future guidance D24/D25 is **not**
implemented (D23).
**Manufacturing-pipeline position:** Specification → **Feasibility Prototype (Prototype Gate, §11)** →
Implementation Handoff (this document) → One Atomic Commit → Docker Verification → Commit → Review →
Next Commit.

---

## 1. Objective

Build the **shared retrieval substrate** (M6_SPEC §1): a read-only, deterministic way to fetch the
top-k most relevant prior episodes from the accumulated grounded experience, so the future
memory-bearing arms (M7) can share an **identical retriever, embedder, and top-k** and differ only by
write-filter (D7). M6 builds retrieval and only retrieval — it writes nothing, filters nothing, learns
nothing, evaluates nothing, and does not alter A0. It is **composition, not a rewrite**: it reads the
frozen M3 episode store/index as memory, derives its query from the frozen M4 content-addressed
identity and M5 task material (plus an optional opaque context, M6_SPEC §3.2), and modifies no frozen
contract. It is **domain-neutral** (D9/D22): memory, query, and the optional context are treated as
opaque, content-addressed data — never parsed as software.

## 2. Scope

**In scope (M6_SPEC §2/§3):**

1. A **read-only memory source** — a projection over the frozen M3 store/index that yields a memory
   snapshot, mutating nothing (§3.1).
2. A **query derivation** from a task's required opaque **material** (M4 `task_identity`) **plus an
   optional opaque retrieval context** that M6 admits but neither generates nor consumes (§3.2).
3. A **single shared, deterministic, domain-neutral embedding/similarity** interface with one
   deterministic reference component and a fixed metric (§3.3).
4. A **deterministic top-k retriever** with **content-addressed tie-breaking** on `content_hash`,
   read-only over a provided memory snapshot (§3.4).
5. The **one shared retriever/embedder/top-k** (§3.5, D7) — not wired into any arm; A0 untouched.

**Out of scope — hard boundaries (M6_SPEC §8):** write-filter policies and arms A1/A2 (M7); A3/A4 (D7);
frozen checkpointed evaluation (M8); pre-registration freeze (M9); Stage-1 statistics/go-no-go (M10);
any **learning** or memory-update logic; any use of retrieval by an arm or any change to the A0 runner;
multi-model routing; a concrete high-fidelity embedder / ANN index / vector DB (deferred registration
behind the neutral interface); **generating or consuming quantitative metrics** (M6 only *admits* the
optional context); any modification of frozen M0–M5; and everything in D15. **D24/D25 are not
implemented (D23).**

M6 uses **Python standard library plus the frozen M0–M5 packages** only (the reference
embedding/similarity is deterministic and in-process, M6_SPEC §3.3/§7); it introduces **no new
dependency**, and therefore **no Docker, compose, or CI change**.

## 3. Files allowed to change

Nothing outside this list may be touched. Module names follow M6_SPEC ("architecture only"; the new
`retrieval` package is the domain-neutral home).

| Path | Commit(s) | Nature |
|---|---|---|
| `src/velith/core/config.py` | M6-C1 | Extend (additive settings only): top-k, embedder identity, memory source location (M6_SPEC §5). |
| `.env.example` | M6-C1 | Document the new `VELITH_*` retrieval settings. |
| `tests/unit/test_config.py` | M6-C1 | Extend: defaults + overrides of the new settings. |
| `src/velith/retrieval/__init__.py` | M6-C2 | **New**: package marker for the read-only retrieval layer. |
| `src/velith/retrieval/query.py` | M6-C2 | **New**: query derivation from required material + optional opaque context (§3.2). |
| `tests/unit/test_retrieval_query.py` | M6-C2 | **New**: query-derivation tests. |
| `src/velith/retrieval/embedding.py` | M6-C3 | **New**: single shared deterministic domain-neutral embedding/similarity interface + reference component (§3.3). |
| `tests/unit/test_retrieval_embedding.py` | M6-C3 | **New**: embedding/similarity tests. |
| `src/velith/retrieval/memory.py` | M6-C4 | **New**: read-only memory source projecting the frozen M3 store/index (§3.1). |
| `tests/unit/test_retrieval_memory.py` | M6-C4 | **New**: read-only memory-source tests. |
| `src/velith/retrieval/retriever.py` | M6-C5 | **New**: deterministic top-k retriever with content-addressed tie-break (§3.4/§3.5). |
| `tests/unit/test_retrieval_retriever.py` | M6-C5 | **New**: retriever tests. |
| `tests/integration/test_m6_retrieval.py` | M6-C6 | **New**: hermetic end-to-end retrieval acceptance (§6). |
| `README.md` | M6-C7 | Add the "M6 — shared retrieval substrate" section. |

## 4. Files forbidden to change

- **Frozen M5 batch layer — including the A0 runner:** `src/velith/batch/**`. Retrieval is **not**
  wired into any arm and the A0 runner is untouched (M6_SPEC §3.5/§8). Reading `RunProvenance`/`batch`
  types is not permitted as a modification vector.
- **Frozen M3/M4 substrate — composed read-only, never modified:** `src/velith/episodes/**`,
  `src/velith/corpus/**`. M6 uses only their read surfaces (`Episode`, `content_hash`, `task_identity`,
  the store/index read operations).
- **Frozen M1/M2 seams:** `src/velith/harness/verifier_sandbox.py`, `src/velith/llm/client.py`,
  `src/velith/agent/proposer.py`, `src/velith/task.py`, `src/velith/runner/spike.py`.
- **Infra (no new dependency):** `docker/verifier.Dockerfile`, `docker-compose.yml`,
  `.github/workflows/**`, `pyproject.toml`, `.pre-commit-config.yaml` (M6_SPEC §2).
- **Frozen record:** `docs/DECISIONS.md`, `docs/M6_SPEC.md`, and all earlier frozen specs/handoffs.
- **Freeze-Milestone-only:** `docs/PROJECT_STATE.md`, `docs/NOTES.md` — updated only at the M6 Freeze
  Milestone by the Research Director, never inside an M6 code commit.
- **Unrelated:** all Node/Next files.
- **Per commit:** any file not in that commit's row of §3.

## 5. Dependency graph (implementation order)

Strictly linear; one atomic commit at a time. No commit begins before its predecessor is committed
green. **The Prototype Gate (§11) is discharged before M6-C1.**

```
Prototype Gate (§11): embedding determinism established  →  green required to proceed
   │
   ▼
M6-C1 (config: top-k, embedder identity, memory source location)
   │
   ▼
M6-C2 (retrieval/query.py: query = required material + optional opaque context)
   │
   ▼
M6-C3 (retrieval/embedding.py: single shared deterministic domain-neutral embedding/similarity)
   │
   ▼
M6-C4 (retrieval/memory.py: read-only memory source over the frozen store/index)
   │
   ▼
M6-C5 (retrieval/retriever.py: deterministic top-k, content-addressed tie-break; composes C2+C3+C4)
   │
   ▼
M6-C6 (integration: hermetic deterministic-retrieval acceptance)
   │
   ▼
M6-C7 (docs: README M6 section)
```

Invariants carried across the chain: retrieval is **read-only** (never writes/mutates the frozen store,
index, or episodes); there is exactly **one** shared retriever/embedder/top-k; retrieval is a **pure,
deterministic, content-addressed** function of `(query, memory snapshot, top-k)`; the optional context
is opaque and neither generated nor consumed; the A0 runner is untouched.

## 6. Commit breakdown (atomic; one logically complete unit each)

**M6-C1 — `feat: retrieval settings`**
Additive `Settings` for **top-k**, the **embedder identity** (single fixed deterministic component),
and the **memory source location** (defaulting to the frozen episode store/index path), with safe
defaults (M0 invariant). Document the `VELITH_*` variables; extend `test_config.py` for default +
override. No behaviour beyond declaration.

**M6-C2 — `feat: retrieval query derivation`**
New `retrieval/query.py`: derive a deterministic, domain-neutral query from a task's **required opaque
material** (M4 `task_identity`) **plus an optional opaque retrieval context** (M6_SPEC §3.2). Material
and context are opaque bytes; the derivation parses neither as any domain, and M6 neither generates nor
consumes the context. Unit tests: derivation is deterministic; a material-only query equals the
baseline path; an optional context is admitted opaquely and changes the query only as opaque input; no
domain parsing occurs.

**M6-C3 — `feat: deterministic embedding/similarity`**
New `retrieval/embedding.py`: a single shared, **deterministic, domain-neutral** embedding/similarity
interface with one in-process reference component and a fixed metric (M6_SPEC §3.3). Unit tests: the
same opaque input always yields the same representation (no run-to-run drift); the similarity metric is
fixed and deterministic; the component is single (no routing) and never interprets a domain.

**M6-C4 — `feat: read-only retrieval memory source`**
New `retrieval/memory.py`: a **read-only** projection over the frozen M3 store/index that yields a
memory snapshot of prior episodes for retrieval, composing the frozen read surface and **mutating
nothing** (M6_SPEC §3.1). Unit tests: the source only reads (no write/re-order/mutation of the store,
index, or episodes); it serves a stable snapshot read-only; it surfaces no held-out episode (relying on
the M4/M5 guarantee that held-out was never persisted).

**M6-C5 — `feat: deterministic top-k retriever`**
New `retrieval/retriever.py`: the single shared retriever composing query (C2), embedding (C3), and
memory (C4) to return the **top-k** most similar prior episodes, with **content-addressed
tie-breaking** on `content_hash`, **read-only** (M6_SPEC §3.4/§3.5). Unit tests: identical
`(query, memory snapshot, top-k)` yields the identical ordered result; ties break deterministically on
`content_hash`; the retriever writes nothing and mutates no frozen artifact; exactly one shared
retriever/embedder/top-k exists (no per-arm variation).

**M6-C6 — `test: hermetic m6 retrieval acceptance`**
New `tests/integration/test_m6_retrieval.py` (hermetic; no model, no network, in-process deterministic
embedding): end-to-end deterministic retrieval over a memory snapshot — identical inputs → identical
ordered top-k; a material-only query and a query with an optional opaque context both behave
deterministically; a non-software memory retrieves through the identical path; the memory holds no
held-out episode; and the A0 runner is neither imported as a write path nor modified. Covers M6_SPEC §6
DoD 1–7.

**M6-C7 — `docs: document shared retrieval substrate`**
Add the "M6 — shared retrieval substrate" section to `README.md` (read-only retrieval, query =
required material + optional opaque context, the single shared deterministic embedder, deterministic
top-k with content-addressed tie-break, and the new settings). No `PROJECT_STATE`/`NOTES` edits.

## 7. Docker verification gates (run after every commit, before it is made)

The identical containerized sequence M1–M5 used. A commit is made **only** when all four are green:

```
docker compose run --rm verifier bash -lc \
  "ruff check . && ruff format --check . && mypy src tests && pytest -q"
```

- `ruff check .` — lint (E,F,I,N,UP,B,SIM,RUF; line-length 100).
- `ruff format --check .` — formatting.
- `mypy src tests` — `--strict`.
- `pytest -q` — full suite.

**CI stays hermetic.** The reference embedding is in-process and deterministic (no live model, no
network); M6 adds no `CAP_SYS_ADMIN`-gated path — `pytest -q` reports **zero M6-attributable skips**.
No new dependency, so no Docker/compose/CI file changes.

## 8. Rollback condition for every commit

Uniform trigger, applied per commit: **if any of the four gates in §7 is red, or the commit's own
acceptance assertions fail, do not commit.** Discard the working tree for that commit
(`git restore`/`git checkout --`), and either fix within the *same* atomic commit or stop. Per-commit
specifics:

- **M6-C1** — roll back if config fails to load with no `.env`, if a default/override test fails, or if
  any gate is red.
- **M6-C2** — roll back if query derivation is non-deterministic, if a material-only query differs from
  the baseline, if the optional context is generated/consumed rather than admitted opaquely, if any
  input is parsed as a domain, or if any gate is red.
- **M6-C3** — roll back if the same opaque input yields differing representations (any run-to-run
  drift), if more than one embedding component/route exists, if a domain is interpreted, or if any gate
  is red.
- **M6-C4** — roll back if the memory source writes to, re-orders, or mutates the store/index/episodes;
  if it surfaces a held-out episode; or if any gate is red.
- **M6-C5** — roll back if retrieval is non-deterministic, if tie-breaking is not content-addressed on
  `content_hash`, if the retriever writes or mutates any frozen artifact, if more than one shared
  retriever/embedder/top-k exists, or if any gate is red.
- **M6-C6** — roll back if any acceptance assertion (deterministic top-k, optional-context determinism,
  domain-neutral flow, held-out-free memory, A0 untouched) fails, or if any gate is red.
- **M6-C7** — roll back if docs introduce a claim not verified by C1–C6, or if any gate is red.

**Frozen-spec guard (stop condition).** If a rollback is caused by a **genuine contradiction with
`docs/M6_SPEC.md`** (not a mere bug) — for example, no admissible deterministic embedding mechanism can
satisfy §3.3/§7, or read-only retrieval cannot be achieved without modifying the frozen store —
**stop immediately and report the contradiction to the Research Director.** Do not edit the frozen spec
or this handoff to make the code pass, do not reinterpret the architecture, and do not introduce
D24/D25 to resolve it (D23).

## 9. Definition of Done (mapping to M6_SPEC §6)

M6 is done when all hold, verified in-container and in CI:

1. A **read-only** retrieval substrate returns the top-k relevant prior episodes for a query (required
   material + optional opaque context that M6 admits but does not generate/consume), composing the
   frozen M3 store/index and mutating nothing — **§6.1** (delivered by C4+C5; query by C2).
2. Retrieval is **deterministic** with **content-addressed tie-breaking** on `content_hash` — **§6.2**
   (C5; acceptance C6).
3. The embedding/similarity component is a **single shared, deterministic, domain-neutral** interface
   with no run-to-run drift — **§6.3** (C3).
4. The substrate is the **one shared retriever/embedder/top-k** (no per-arm variation) — **§6.4**
   (C5, D7).
5. **A0 is unchanged**; no frozen M0–M5 file is modified; the only additions are the read-only
   retrieval component and additive `core/config.py` settings — **§6.5** (all commits; enforced by §4).
6. **Domain-neutrality holds** — a non-software memory retrieves through the identical path; neither
   query nor memory is parsed as a domain — **§6.6** (C2/C3/C6).
7. **Held-out safety preserved** — retrieval reads only persisted (available) experience, surfaces no
   held-out episode, and operates read-only over a provided snapshot — **§6.7** (C4/C6).
8. All four gates are green in the container and CI; commits atomic and conventional — **§6.8**
   (every commit).

**Freeze Milestone (Research Director, after DoD 1–8):** update `docs/PROJECT_STATE.md` and
`docs/NOTES.md`, then tag `m6-complete`. These are not M6 code commits.

## 10. Risks

Extracted from M6_SPEC §7 and the composition boundary:

- **Embedding non-determinism.** The load-bearing risk (M6_SPEC §7): if the embedding/similarity
  mechanism is not bit-reproducible, retrieval is non-deterministic and the D7/D8 invariants fail.
  *Mitigation:* the Prototype Gate (§11) must be green before C1; the reference embedding is in-process
  and deterministic.
- **Accidental write / mutation of frozen memory.** Retrieval must never modify the store/index.
  *Mitigation:* read-only memory source (C4); enforced by §4 and the C4/C5 rollback triggers.
- **Per-arm retriever divergence.** More than one retriever/embedder/top-k would void D7.
  *Mitigation:* a single shared substrate (C5, §3.5); no arm wiring in M6.
- **Optional-context scope creep.** The context must be admitted opaquely, not generated/consumed or
  interpreted as metrics. *Mitigation:* §3.2 boundary; C2 rollback trigger; §8 out-of-scope.
- **A0 disturbance.** *Mitigation:* `batch/**` is forbidden (§4); M6 wires retrieval into nothing.
- **Held-out leakage via reads.** *Mitigation:* memory is held-out-free by the M4/M5 write guarantee;
  M6 adds no reintroduction path (C4/C6).

## 11. Prototype gate handling (REQUIRED before M6-C1)

Per M6_SPEC §7, M6 asserts one load-bearing unproven mechanism — **the determinism and reproducibility
of the embedding/similarity component** — on which the D7 "identical retriever across arms" invariant
and D8/D16.1 reproducibility depend. The Prototype Gate is therefore **armed and REQUIRED**, and is
discharged **before M6-C1**:

- A narrow feasibility prototype must establish that the chosen embedding/similarity mechanism yields
  **deterministic, reproducible retrieval** — the same query over the same memory snapshot returns the
  identical ordered top-k — to the determinism level the grounding signal already meets (D18).
- **Green** → proceed to M6-C1 and the linear chain (§5).
- **Red** → **stop**: the mechanism must be chosen so determinism holds; do not proceed to Engineering
  on an unproven embedder. If no admissible mechanism can satisfy the frozen §3.3/§7 determinism
  requirement, that is a contradiction with the frozen spec — **report it to the Research Director**
  (do not edit the spec, do not reinterpret, do not introduce D24/D25). This mirrors the R3 prototype
  that established M2's isolation mechanism. No other M6 assertion requires prototyping.

---

*End of handoff. Engineering begins at M6-C1 only after the Prototype Gate is green and the Research
Director authorizes it; one atomic commit at a time, stopping for review after each. Composition over
modification; the architecture is frozen; implementation is extracted from `docs/M6_SPEC.md` only.
Future principles D24/D25 are not implemented (D23).*
