# PROJECT STATE

**Project:** Velith
**Document type:** Living status record. Captures the repository's *verified* state at each
milestone boundary. Updated at milestone close, never improvised mid-implementation.
**Last updated:** 2026-07-06
**Current tag:** `m3-complete`
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

## 7. Readiness for M4

M4 is the **dataset loader + mechanically-enforced held-out lock** (D8/D12): real task ingestion and a
hash-checked exclusion that no arm's memory can cross. The indexed, integrity-checked episode store is
now the durable substrate M4+ reads and writes; queries by neutral field and time range are available
to later consumers, and the record digest protects stored experience. The JSONL log stays
authoritative and the SQLite index remains a rebuildable projection. No M3 work blocks M4.

**Repository is M4-ready.** Begin M4 only against its own ratified engineering specification and
implementation handoff, in the same atomic, gate-verified workflow used for M1–M3.
