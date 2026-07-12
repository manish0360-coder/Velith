Phase 0: Development environment ready (Git, WSL2, Docker, Ollama)

## M2-C2 — verifier network-isolation capability (CAP_SYS_ADMIN)

The verifier isolates the Phase-2 hidden-test step from the network with `unshare -n`
(M2_SPEC §10, D19 / Fallback B), granted via `cap_add: [SYS_ADMIN]` in
`docker-compose.yml`. The R3 feasibility prototype confirmed unprivileged `unshare -rn`
is blocked by the Docker Desktop / WSL2 seccomp profile, so the capability is mandatory.

Capability-gating is permanent and honest: isolation-dependent tests **run** where
CAP_SYS_ADMIN is present and **skip-with-reason** where it is not — never silently
passed. The verifier refuses to run untrusted code unisolated: if isolation is required
but the capability is absent, `verify` raises `SandboxExecutionError` (→ `INFRA_ERROR`).

Environment support — record for future contributors:

- Local Docker Desktop / WSL2: **SUPPORTED** (R3 prototype, Fallback B passed). At the M2
  freeze, `docker compose run --rm verifier pytest -q` ran with **zero skips**, so
  `test_phase2_blocks_network_egress` **executed and passed** under CAP_SYS_ADMIN — the
  Phase-2 no-egress control is verified locally.
- GitHub Actions CI: **CONFIRMED GREEN (RM-CI RESOLVED).** All five M2 workflow runs are
  green on `main` — CI #19 (`d75f641`, pinned env), #20 (`b800394`, two-phase isolation),
  #21 (`8a8d171`, flake detection), #22 (`baed002`, held-out secondary), #23 (`a315dea`,
  docs). The isolation-dependent test is permanently capability-gated (runs where
  CAP_SYS_ADMIN is granted, skip-with-reason otherwise — never silently passed, M2_SPEC
  §11); the local Docker Desktop run above is the authoritative CAP_SYS_ADMIN acceptance
  gate. M2 verification gates (M2_SPEC §3/§14) are satisfied.

## M3 — indexed episode store (freeze)

M3 adds a derived, queryable index over the episode log without touching episode identity
(M3_SPEC frozen; handoff M3-C1..C5). Record for future contributors:

- **Authority.** The append-only JSONL log (`data/episodes/episodes.jsonl`) is the single source of
  truth. The SQLite index (`data/episodes/episodes.db`, `VELITH_EPISODE_INDEX_PATH`) is a
  *rebuildable projection*: if it is ever lost or diverges, delete it and call
  `EpisodeIndex.rebuild_from_log` — it is never trusted over the log (M3_SPEC §4.1-§4.2). Both files
  live under the gitignored `data/episodes/`. A store constructed without an index path keeps the
  exact M1/M2 log-only behaviour, so pre-existing logs read back unchanged.
- **Two digests, distinct on purpose.** `content_hash` is *identity* and excludes provenance
  (`timestamp`, `latency_seconds`, `verify_seconds`, `flaky`; D16.1/D21). `record_digest` (held in
  the index) covers the *full serialized record* and catches corruption of exactly those excluded
  provenance fields. Reads raise `EpisodeIntegrityError` and `RecordIntegrityError` respectively —
  never conflate them.
- **Domain-neutral by contract.** Only neutral fields are indexed; patch, prompt, and source are
  opaque (D22 / §4.4). This keeps the store reusable for non-software rungs of the D5 ladder — a
  synthetic non-software episode indexes and queries through the identical path (acceptance test).
- **Freeze certification.** M3-C1..C5 implemented, Docker-verified, committed and pushed; all four
  gates (`ruff check`, `ruff format --check`, `mypy src tests`, `pytest -q`) green with zero
  M3-attributable skips. Milestone tagged `m3-complete`.

## M4 — task corpus and held-out lock (freeze)

M4 adds a domain-neutral corpus layer without touching any M0–M3 contract (M4_SPEC frozen under D23;
handoff M4-C1..C6). Record for future contributors:

- **Domain-neutral by contract.** A task is an opaque `material` (identity content) plus an opaque
  verification `handle`; the loader and lock never inspect either. Identity is a SHA-256 of the
  material, independent of the mutable display label — so relabeling cannot move a task across the
  partition (M4_SPEC §3.3). This keeps the corpus reusable for non-software rungs of the D5 ladder.
- **The manifest freezes the split.** The content-addressed manifest maps identity →
  `available`/`held_out` and carries a stable `manifest_hash`: same split → same hash, changed split →
  new hash. A concrete real-dataset source (e.g. SWE-bench) is a registered adapter conforming to the
  neutral loader contract — not built in M4 (M4_SPEC §3.2/§6).
- **One guarded chokepoint.** `GuardedEpisodeWriter` is the only experience-path writer into the frozen
  `EpisodeStore`: it delegates available-task episodes byte-for-byte and raises `HeldOutError` on a
  held-out or unknown identity (fail-closed, D8). The frozen store is composed, never modified — proven
  by a byte-identity acceptance test.
- **Settings note.** The loader consumes `VELITH_CORPUS_PATH` and `VELITH_CORPUS_PARTITION_SPEC_PATH`;
  `VELITH_CORPUS_MANIFEST_PATH` is declared as the manifest location, and in M4 the manifest is produced
  in-memory (`LoadedCorpus.manifest`) — persistence to that path is left to a later milestone.
- **Freeze certification.** M4-C1..C6 implemented, Docker-verified, committed and pushed; all four
  gates (`ruff check`, `ruff format --check`, `mypy src tests`, `pytest -q`) green with zero
  M4-attributable skips. Milestone tagged `m4-complete`. Future principles D24/D25 recorded, not
  implemented (D23).

## M5 — batch runner and cold baseline arm A0 (freeze)

M5 adds a domain-neutral `batch` layer without touching any M0–M4 contract (M5_SPEC frozen; handoff
M5-C1..C7). Record for future contributors:

- **One guarded write path.** The batch runner persists episodes **only** through the frozen M4
  `GuardedEpisodeWriter`; it never calls the store directly. Held-out is skipped by the partition filter
  and independently refused by the boundary (fail-closed, D8). This is the load-bearing invariant that
  keeps held-out from leaking at scale.
- **A0 is cold; seeding is deterministic.** The cold baseline arm reads and writes no memory. Each
  task's seed is `derive_task_seed(task_identity, batch_seed)` — a pure function, so a task's evaluation
  is identical across arms regardless of execution order or retries (D8/D16.1). A0 is the memoryless
  baseline the compounding experiment measures against.
- **Cost guard is the sweep's bound.** `CostGuard` enforces deterministic limits (max tasks, attempts,
  tokens; `0` unbounded), admits work strictly below each limit, and halts loudly (`CostBudgetError`)
  without writing a partial episode. The budget/limits are recorded in the run provenance as part of the
  experiment identity.
- **Domain specifics live behind the adapter.** The runner inspects no materials; `TaskAdapter`
  materializes a verifiable frozen `Task` from an opaque `CorpusTask`. The reference adapter is the
  single fixture (D16.3); a concrete real-dataset adapter (e.g. SWE-bench) is a deferred registration.
  Because M5 uses the single fixture, all episodes carry the fixture `task_id`; per-task identity and
  seeding still differ via the corpus identity.
- **CI stays hermetic.** The batch tests inject a mocked proposer and a stub verifier — no model, no
  network, no `CAP_SYS_ADMIN` path — so `pytest -q` reports zero M5-attributable skips. The bounded
  **live** sweep (real proposer + verifier) is the documented local acceptance step (D16.2).
- **Freeze certification.** M5-C1..C7 implemented, Docker-verified, committed and pushed; all four gates
  (`ruff check`, `ruff format --check`, `mypy src tests`, `pytest -q`) green with zero M5-attributable
  skips. Milestone tagged `m5-complete`. Future principles D24/D25 recorded, not implemented (D23).
