# PROJECT STATE

**Project:** Velith
**Document type:** Living status record. Captures the repository's *verified* state at each
milestone boundary. Updated at milestone close, never improvised mid-implementation.
**Last updated:** 2026-07-06
**Current tag:** `m5-complete`
**Branch:** `main` — green end to end, pushed.

---

## 1. Current state

**M0 — complete and certified** (`m0-complete`). Containerized skeleton: pinned Docker build,
in-container pytest, a single validated `Settings` object, structured logging, and hermetic CI
green from a fresh clone. The foundation every later milestone assumes.

**M1 — complete and certified** (`m1-complete`). The irreducible core of the program is now real
on the ground: for a single engineering task, a local model **proposes** a candidate patch, a
containerized verifier **disposes** of it against a hidden test, and the outcome is persisted as a
provenance-complete, content-hashed **episode** that survives container exit. The central
`propose → verify → log` loop is connected end to end and reproducible.

M1 is a spike, not a system: one fixture task, one model, an append-only JSONL store. Breadth,
scale, memory, experiment arms, and the compounding experiment are explicitly later milestones and
were deliberately not built.

**M2 — complete and certified** (`m2-complete`). The single `VerifierSandbox.verify` seam is now
hardened so the verdict is trustworthy as the program's exact ground truth: the hidden test runs in
**two phases** (Phase 1 network ON prep; Phase 2 network OFF via `unshare -n` under `CAP_SYS_ADMIN`);
a **pinned environment** reaches **Determinism Level 4** (R2/D18); the primary test is re-run N times
for **flake detection**, recording the `flaky` provenance flag (R1/R5 — excluded from the content
hash, no new verdict state); and a **held-out secondary** suite, re-materialized from the pristine
fixture after patch apply, populates the model-gap signal `secondary_passed` (identity — inside the
hash). Isolation is mandatory: untrusted code is never run unisolated. This was a *hardening, not a
rewrite* (RK8) — proposer, LLM client, and store are unchanged.

**M3 — complete and certified** (`m3-complete`). The accumulated episodes are now **queryable and
integrity-checked** with no change to episode identity. The append-only JSONL log remains the single
source of truth; alongside it the store maintains a **derived SQLite index** — a rebuildable
projection keyed on neutral, domain-agnostic fields only (`task_id`, verdict `state`, `timestamp`,
`model`, `seed`, `flaky`, `secondary_passed`, `content_hash`) — plus a **record-level integrity
digest** distinct from `content_hash` (it covers the full serialized record, identity + provenance,
M3_SPEC §9). Reads re-verify both digests; the change/`patch`, prompt, and source are never indexed,
so the store is fully domain-neutral (D22 / §4.4). This was a *storage hardening, not a rewrite*: the
proposer, LLM client, verifier, and the `Episode` identity schema are unchanged.

**M4 — complete and certified** (`m4-complete`). The loop is lifted from one fixture task to a
**corpus** under a **mechanically-enforced held-out lock** that no experience path can cross (D8). A
domain-neutral loader materializes many `CorpusTask` values — each an opaque *material* and
*verification handle* the loader never inspects — labeled with a partition (`available` | `held_out`)
drawn from a **content-addressed manifest** whose stable hash freezes the split. The `HeldOutLock`
(keyed on content-addressed identity, so relabeling cannot cross) and a single **guarded persistence
boundary** compose the frozen M3 store: available-task episodes are delegated byte-for-byte unchanged,
while a held-out or unknown task raises `HeldOutError` (fail-closed). This was *composition, not a
rewrite* — no M0–M3 contract was modified.

**M5 — complete and certified** (`m5-complete`). The loop is lifted from one task to a **batch sweep**
over the corpus, recording the **cold baseline arm (A0)** — the no-memory baseline the compounding
experiment measures against (D6/D7). A new `batch` layer draws the corpus's **available** tasks, drives
each through `propose → verify → log`, and persists every episode **only** through the frozen M4 guarded
boundary (held-out can never leak). Each task's seed is a deterministic function of its content-addressed
identity and the run's batch seed (identical across arms regardless of order or retries); the sweep is
bounded by a hard **cost guard**; and a **run-provenance** record captures the experiment identity —
corpus manifest hash, arm, base model, batch seed, and the cost-guard budget/limits. Domain specifics
live behind a neutral task-materialization adapter. This was *composition, not a rewrite* — no M0–M4
contract was modified.

## 2. M1 objectives and achievements

Every M1 engineering goal was met:

- **Model-proposal capability** introduced as a bounded component — a thin Ollama adapter over
  stdlib `urllib`, never the architecture (D9, D16.4).
- **Verifier execution path** made real — apply a candidate patch with pinned `git apply` and run
  the hidden test suite inside the container, returning a structured `Verdict`. This is the single
  seam M2 will harden (network isolation, flake detection, bit-for-bit determinism).
- **Provenance-complete `Episode`** — all M1 spec §9.1 fields, with a SHA-256 content hash over a
  canonical serialization (sort-keys, tight separators, UTF-8) that excludes volatile timing,
  protecting D16.1.
- **Orchestrator (`spike`)** — wires proposer → verifier → store into one CLI command and is the
  single owner of operation order (§8); CLI shell split from the importable orchestration function.
- **M0 invariant preserved** — the verdict is produced inside the container; the host is never the
  source of truth (D3).
- **CI stays hermetic** — no model server in CI; the live model path is a documented local
  acceptance step, not a gate.

**Definition of Done — all satisfied.** A live in-container run wrote one complete episode that
survived `--rm` with a verifying hash; the verify→log path is reproducible for a recorded proposal
(same verdict and same hash); all four grounded verdicts (`PASSED`, `FAILED`, `PATCH_APPLY_FAILED`,
`NO_PATCH`) are reachable as exit-0 outcomes and `INFRA_ERROR` aborts non-zero and logs loudly; the
four gates (`ruff check`, `ruff format --check`, `mypy --strict`, `pytest`) are green in the
container; only the permitted M0 files were modified; the milestone is tagged.

## 3. Repository status

M1 added, alongside the M0 skeleton:

```
src/velith/
├── task.py                       # Task value type + single-fixture loader
├── episodes/{episode,store}.py   # Episode schema + content hash; append-only JSONL store
├── harness/verifier_sandbox.py   # Deterministic verifier (the M2 hardening seam)
├── llm/client.py                 # Thin Ollama adapter (the M5 routing seam)
├── agent/proposer.py             # ProposerAgent + minimal patch extraction
└── runner/spike.py               # Orchestrator + CLI
tests/
├── unit/{test_episode,test_store,test_task,test_verifier_sandbox,test_proposer}.py
├── integration/test_spike_episode.py   # hermetic, mocked proposer, real verify→log
└── fixtures/calc_add_bug/        # minimal buggy repo + deterministic hidden test
```

Permitted M0 modifications used: `core/config.py` (M1 settings), `docker-compose.yml` (episode
bind-mount + `host.docker.internal`), `.gitignore` (`/data/episodes/`), `README.md` (M1 usage), and
`docker/verifier.Dockerfile` (`git`). No other M0 source or build file was changed.

**Commit ledger (atomic, conventional, none combined):**

| Commit | Subject |
|---|---|
| `539a770` | feat: episode schema + content hash (C1) |
| `f4eb74c` | fix: replace ambiguous en dash with ASCII hyphen (RUF003) |
| `4fd365d` | feat: episode store, jsonl append-only (C2) |
| `fb5fec1` | feat: task type + minimal fixture (C3) |
| `a424499` | feat: verifier sandbox (C4) |
| `7d7b787` | feat: ollama client, thin adapter (C5) |
| `df9bae7` | feat: proposer agent (C6) |
| `b165219` | feat: spike orchestrator + CLI (C7) |
| `f399e7e` | fix: normalize verifier output timing for reproducible content hash (D16.1) |
| `dd30f5c` | test: hermetic spike integration (C8) |
| `59ddd14` | build: episode volume + gitignore (C9) |
| `ffed330` | docs: M1 run + record/replay usage (C10) |

**Live acceptance:** model `qwen2.5:3b`, verdict `NO_PATCH`, `hash_ok = True`, exit 0, episode
persisted — a valid grounded outcome confirming the loop end to end. The `INFRA_ERROR` path was
independently exercised (a reasoning model exceeding the request timeout produced a loud non-zero
abort with no episode written).

## 4. Known limitations and deferred work

Recorded for the M2 team; full categorization is in the M1 close-out review. Highlights:

- The proposer's prompt is the task's prompt material only (no source embedded), so a live run may
  not produce an applying patch — by design (the dataset/prompt enrichment is M4). Grounded
  outcomes (`NO_PATCH`/`PATCH_APPLY_FAILED`) are still logged and correct.
- Patch extraction is deliberately minimal; diffs wrapped in non-standard headers (e.g. a
  `git format-patch` header) are treated as `NO_PATCH`.
- The exception taxonomy (`ModelUnavailableError`, `SandboxExecutionError`, `EpisodeIntegrityError`)
  is not yet unified under a shared base error.
- `Episode` still emits the benign pydantic `model_`-namespace warning (`Completion` and `Proposal`
  set `protected_namespaces=()`; `Episode` does not). Non-fatal, but noise in gate output.
- `velith_version` provenance uses the package version; a git ref is unavailable at runtime
  in-container (the image copies sources, not `.git`).
- The default Ollama request timeout (120s) is too short for multi-minute reasoning models; it is
  configurable via `VELITH_OLLAMA_TIMEOUT_SECONDS`.

## 5. M2 objectives, achievements, and verification

Every M2 engineering goal (M2_SPEC §2/§3) was met, confined to the hardening seam:

- **Network-isolated Phase 2** — the primary and secondary test commands run wrapped in `unshare -n`
  under `CAP_SYS_ADMIN` (Fallback B, R3/D19); the mandatory-isolation invariant raises
  `SandboxExecutionError` (-> `INFRA_ERROR`) rather than ever running untrusted code unisolated.
- **Pinned environment -> Determinism Level 4** (R2/D18) — `PYTHONHASHSEED=0`, `TZ=UTC`, `LC_ALL=C`,
  `PYTHONDONTWRITEBYTECODE=1` injected into the test subprocess; M1 output normalization retained.
- **Flake detection** (R1/R5/D17/D21) — the primary is re-run N times (default 3) and reconciled; a
  disagreement sets `flaky=True` with a loud structured warning and a nominal verdict. No `FLAKY`
  state; `flaky` is persisted as provenance and excluded from the content hash.
- **Held-out secondary / model-gap** (§9/D21) — `secondary_passed` populated from a suite
  re-materialized from the pristine fixture after patch apply (anti-wireheading), and carried inside
  the content hash via the C7 mapping.
- **Seam preserved** (RK8) — `agent/proposer.py`, `llm/client.py`, `episodes/store.py` unmodified;
  `episodes/episode.py` and `runner/spike.py` touched only by the sanctioned `flaky` field + one-line
  passthrough.

**Commit ledger (atomic, conventional):**

| Commit | Subject |
|---|---|
| `d75f641` | feat: pinned deterministic execution environment (M2-C1) |
| `b800394` | feat: two-phase network-isolated test execution (M2-C2) |
| `8a8d171` | feat: flake detection and provenance (M2-C3) |
| `baed002` | feat: held-out secondary suite and model-gap signal (M2-C4) |
| `a315dea` | docs: document hardened verifier (M2-C5) |

**Definition of Done — all satisfied (M2_SPEC §3/§14).** Two-phase isolation works under
`CAP_SYS_ADMIN` with a passing Phase-2 no-egress control; Determinism Level 4 holds and a varying
`flaky` does not change the content hash; flake detection records `flaky` as provenance with no new
state; `secondary_passed` is populated with the secondary tamper-proofed; the taxonomy is unchanged;
all four gates are green in the container and CI. **Verification evidence:** local
`docker compose run --rm verifier` — `ruff check`, `ruff format --check`, `mypy src tests`, and
`pytest -q` (zero skips -> `test_phase2_blocks_network_egress` executed under `CAP_SYS_ADMIN`) all
green; GitHub Actions CI #19-#23 green on `main` (RM-CI resolved, see `docs/NOTES.md`).

## 6. M3 objectives, achievements, and verification

Every M3 engineering goal (M3_SPEC §2/§5, handoff §9) was met, confined to the storage/access seam:

- **Derived, rebuildable index** (M3_SPEC §4.1-§4.2) — a new `episodes/index.py` maintains an embedded
  SQLite projection of the log, keyed by `content_hash`, with `rebuild_from_log` reconstructing it
  from the authoritative log alone. The JSONL log stays the single source of truth; the index is
  never trusted over it.
- **Domain-neutral query surface** (M3_SPEC §6.2, D22 / §4.4) — typed accessors retrieve episodes by
  each neutral field (`task_id`, `state`, `timestamp`, `model`, `seed`, `flaky`, `secondary_passed`,
  `content_hash`) and by time range. No domain field (patch/prompt/source) is indexed.
- **Record-level integrity digest** (M3_SPEC §9) — each row carries a `record_digest` over the full
  serialized record, distinct from the identity `content_hash`. Reads raise `EpisodeIntegrityError`
  on a content-hash mismatch and `RecordIntegrityError` on a record-digest mismatch (e.g. tampering
  with a provenance field the content hash excludes). Corruption is loud, never silent.
- **Identity untouched, determinism preserved** (M3_SPEC §5.7 / §8) — index presence changes no
  `content_hash` and no log line; a varying `flaky` stays inert to identity (D21). The `Episode`
  identity schema, proposer, LLM client, and verifier are unchanged.
- **Config** (M3_SPEC §6.3) — the index path is a single validated setting,
  `VELITH_EPISODE_INDEX_PATH` (default `data/episodes/episodes.db`), under the gitignored
  `data/episodes/`.

**Commit ledger (atomic, conventional):**

| Commit | Subject |
|---|---|
| `4be35af` | feat: episode index path setting (M3-C1) |
| `8a6c062` | feat: sqlite episode index (derived projection) (M3-C2) |
| `3b45b56` | feat: dual-write store with record-level integrity digest (M3-C3) |
| `9def1b5` | test: hermetic m3 store+index acceptance (M3-C4) |
| `2d2da18` | docs: document indexed episode store (M3-C5) |



**Definition of Done — all satisfied (M3_SPEC §5, handoff §9).** Existing M1/M2 episodes read back and
re-hash unchanged (1); append updates log + index, and the index drops and rebuilds from the log to an
identical state (2); episodes are retrievable by every neutral field and by time range with
`content_hash` re-verified on read (3); a record-level digest is stored and byte-level corruption is
detected loudly and distinctly (4); no domain field is indexed and a synthetic non-software episode
flows through the identical path (5); the categorical verdict is encoded without a binary-only
worldview and no quantitative field was built (6, D22); the index and digest change no `content_hash`
and `flaky` stays inert (7); all four gates are green in the container and CI (8). **Verification
evidence:** local `docker compose run --rm verifier` — `ruff check`, `ruff format --check`,
`mypy src tests`, `pytest -q` all green across M3-C1..C5; the store/index adds no
network-isolation-gated test, so `pytest -q` reports zero M3-attributable skips (handoff §7).

## 7. M4 objectives, achievements, and verification

Every M4 engineering goal (M4_SPEC §2/§8, handoff §9) was met, confined to a new domain-neutral corpus
layer composed onto the frozen store:

- **Content-addressed partition manifest** (M4_SPEC §3.1) — `corpus/manifest.py` maps each
  content-addressed task identity to exactly one partition (`available` | `held_out`) and exposes a
  stable `manifest_hash` that is identical for the same split and changes iff the split changes.
  Identity is a hash of opaque material, independent of the mutable display label.
- **Domain-neutral corpus loader** (M4_SPEC §3.2) — `corpus/loader.py` materializes many `CorpusTask`
  values from a corpus source, each labeled with its partition from the manifest; materials and the
  verification handle are opaque (carried verbatim, never parsed). `task.py` is unmodified; a
  non-software corpus loads through the identical path.
- **Held-out lock + guarded persistence boundary** (M4_SPEC §3.3 / §4) — `corpus/heldout.py` provides
  the single authoritative exclusion predicate (`HeldOutLock`) and the single guarded writer
  (`GuardedEpisodeWriter`) into the frozen `EpisodeStore`: available-task episodes are delegated
  byte-for-byte unchanged; a held-out task or an identity absent from the manifest raises
  `HeldOutError` (fail-closed). Mechanical enforcement at one chokepoint, never convention.
- **Composition, not modification** — the frozen episode schema, store, index, task type, verifier,
  LLM client, and orchestrator are untouched; the only M0–M3 change is additive `core/config.py`
  settings. Future principles D24/D25 are recorded but not implemented (D23).

**Commit ledger (atomic, conventional):**

| Commit | Subject |
|---|---|
| `aa9ac62` | feat: corpus and partition settings (M4-C1) |
| `24c6a5b` | feat: content-addressed corpus manifest (M4-C2) |
| `45c584e` | feat: domain-neutral task corpus loader (M4-C3) |
| `960661b` | feat: held-out lock and guarded persistence (M4-C4) |
| `98fd3b2` | test: verify M4 corpus integration (M4-C5) |
| `11d132b` | docs: document M4 task corpus and held-out lock (M4-C6) |

The M4 specification freeze (D23–D25) is recorded separately in commit `a9bce19`.

**Definition of Done — all satisfied (M4_SPEC §2/§8, handoff §9).** A corpus of many tasks loads into
domain-neutral values without the loader inspecting materials or the handle (1); every task carries a
partition label assigned deterministically by the content-addressed manifest (2); the held-out lock's
predicate is authoritative and content-addressed, robust to relabeling (3); the single guarded boundary
refuses held-out and unknown identities and delegates available-task episodes to the frozen store
byte-identically (4); the partition is frozen by a manifest hash that is stable and changes iff the
split changes (5); a synthetic non-software corpus loads, partitions, and locks through the identical
path (6); no frozen M0–M3 file is modified and the only `core/config.py` change is additive (7); all
four gates are green in the container and CI (8). **Verification evidence:** `docker compose run --rm
verifier` — `ruff check`, `ruff format --check`, `mypy src tests`, `pytest -q` all green across
M4-C1..C6; M4 adds no network-isolation-gated test, so `pytest -q` reports zero M4-attributable skips
(handoff §7).

## 8. M5 objectives, achievements, and verification

Every M5 engineering goal (M5_SPEC §2/§6, handoff §9) was met, confined to a new domain-neutral `batch`
layer composed onto the frozen substrate:

- **Batch runner, cold arm A0** (M5_SPEC §3.1/§3.2) — `batch/runner.py` sweeps the available partition,
  drives each task through the frozen proposer → verifier, tags every episode `arm = A0`, and persists
  **only** through the frozen `GuardedEpisodeWriter`. Held-out tasks are skipped and independently
  refused by the boundary (fail-closed). Collaborators are injected, so the sweep is hermetically
  testable; the M1 spike remains the frozen single-task reference.
- **Deterministic per-task seeding** (M5_SPEC §3.5) — `batch/provenance.py` derives each task's seed
  from its content-addressed identity and the batch seed, so evaluation is identical across arms
  regardless of execution order or retries.
- **Cost guard** (M5_SPEC §3.4) — `batch/budget.py` bounds the sweep by deterministic limits (max
  tasks, attempts, tokens; `0` unbounded), admitting work strictly below each limit and halting loudly
  (`CostBudgetError`) at it, never writing a partial episode.
- **Task-materialization adapter** (M5_SPEC §3.3) — `batch/adapter.py` materializes a verifiable frozen
  `Task` from an opaque `CorpusTask`; the reference adapter is the single fixture (D16.3); real-dataset
  adapters remain deferred registrations.
- **Run provenance and fixed base model** (M5_SPEC §3.4/§3.5) — the `RunProvenance` experiment identity
  (corpus manifest hash, arm, base model, batch seed, cost-guard budget/limits) is emitted to the log;
  `batch/model.py` binds one fixed base model (no routing).
- **Composition, not modification** — the frozen episode schema, store, index, task type, verifier, LLM
  client, corpus layer, and the M1 spike are untouched; the only M0–M4 change is additive
  `core/config.py` settings. Future principles D24/D25 are recorded but not implemented (D23).

**Commit ledger (atomic, conventional):**

| Commit | Subject |
|---|---|
| `ee2de93` | feat: batch run settings (M5-C1) |
| `e31da38` | feat: deterministic batch provenance (M5-C2) |
| `1358e14` | feat: cost guard and fixed model seam (M5-C3) |
| `97b467f` | feat: task materialization adapter seam (M5-C4) |
| `ebe0336` | feat: batch runner arm A0 (M5-C5) |
| `407c46c` | test: verify batch runner arm A0 (M5-C6) |
| `73561bd` | docs: document batch runner and cold baseline arm (M5-C7) |

**Definition of Done — all satisfied (M5_SPEC §6, handoff §9).** The runner sweeps the available
partition end to end, one episode per task, each persisted through the guarded boundary tagged arm A0
(1); held-out is never attempted or persisted (2); A0 is cold and deterministically seeded, independent
of order and retries (3); the cost guard halts the sweep loudly without a partial episode (4); the run
provenance records the full experiment identity including the cost-guard budget/limits (5); a synthetic
non-software corpus sweeps through the identical path (6); no frozen M0–M4 file is modified and the only
`core/config.py` change is additive (7); all four gates are green in the container and CI, with the
runner tests injecting a mocked proposer and stub verifier so there are zero M5-attributable skips and
the bounded live sweep is the documented local acceptance step (8, D16.2).

## 9. Readiness for M6

M6 is the **shared retrieval substrate** (D6/D7/D12): the memory the verified/unfiltered write-filter
arms (M7) will read, holding the retriever/embedder/top-k identical across A1 and A2 so grounding is the
only manipulated variable (D7). The batch runner, cold baseline A0, deterministic seeding, cost guard,
and run provenance are now the durable substrate M6+ builds on; A0 remains the memoryless baseline the
compounding experiment measures against. The JSONL log stays authoritative, the index a rebuildable
projection, the held-out partition mechanically enforced, and every experience write passes the single
guarded boundary. No M5 work blocks M6.

**Repository is M6-ready.** Begin M6 only against its own ratified engineering specification and
implementation handoff, in the same atomic, gate-verified workflow used for M1–M5.
