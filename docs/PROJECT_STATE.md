# PROJECT STATE

**Project:** Velith
**Document type:** Living status record. Captures the repository's *verified* state at each
milestone boundary. Updated at milestone close, never improvised mid-implementation.
**Last updated:** 2026-07-04
**Current tag:** `m2-complete`
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

## 6. Readiness for M3

M3 extends **episode storage/indexing** without altering identity (content-hash) fields (M2_SPEC
§15): an indexed/DB episode store and query surface, and — if required — a separate record-level
integrity digest distinct from the content hash. The two-phase, pinned, isolated verifier is now the
durable substrate every later rung reuses; the persisted `flaky` provenance is available to later
consumers unchanged. No M2 work blocks M3.

**Repository is M3-ready.** Begin M3 only against its own ratified engineering specification and
implementation handoff, in the same atomic, gate-verified workflow used for M1 and M2.
