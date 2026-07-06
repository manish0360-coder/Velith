# M3_IMPLEMENTATION_HANDOFF

**Project:** Velith
**Milestone:** M3 — indexed, queryable, integrity-checked episode store.
**Document type:** Frozen implementation handoff. It is *extracted from* `docs/M3_SPEC.md` (FINAL,
frozen 2026-07-06) and adds no design. Every clause traces to a spec section. Engineering
manufactures only what is written here; a genuine contradiction with the frozen spec **stops work and
is reported** — it never licenses editing the spec or this handoff.
**Status:** Ready for engineering.
**Date:** 2026-07-06.
**Extracted from:** `docs/M3_SPEC.md` §1–§13. **Governing decisions:** D3, D12, D16.1, D16.6,
D16.7, D18, D21, D22.
**Manufacturing pipeline position:** Specification → **Implementation Handoff (this document)** →
One Atomic Commit → Docker Verification → Commit → Review → Next Commit.

---

## 1. Objective

Turn the accumulated body of episodes into something **usable and durable** without altering episode
identity and without teaching the store anything about the engineering domain (M3_SPEC §1). Concretely:
add a queryable index over the append-only JSONL log, keyed on neutral fields only; add a
record-level integrity digest distinct from `content_hash`; and preserve every M1/M2 invariant (the
log stays authoritative; reads still re-verify `content_hash`). This is a storage/access hardening,
not a rewrite — the proposer, LLM client, verifier, and the `Episode` **identity** schema are
unchanged (M3_SPEC §1, §4.1–§4.2).

## 2. Scope

**In scope (M3_SPEC §2):**

1. A queryable **index** over the episode log, keyed on the closed neutral-field set (§5 below;
   M3_SPEC §6.2).
2. A minimal **query surface** — a thin Python API of typed accessors, retrieval by neutral field and
   time range (M3_SPEC §3, §6.1).
3. A **record-level integrity digest**, distinct from `content_hash`, over the full serialized record;
   stored in the index (M3_SPEC §9).
4. Preservation of all M1/M2 invariants: JSONL authoritative, index a rebuildable derived projection,
   `content_hash` re-verified on read, existing episodes re-hash identically (M3_SPEC §2.4, §4.1–§4.2,
   §8).

**Out of scope — hard boundaries (M3_SPEC §3):** no DB server or network dependency (embedded SQLite,
Python stdlib only); no query language/DSL; no domain-specific indexing (the `patch`/prompt/source are
opaque and never indexed); **no quantitative outcome field is built** (D22 flexibility is honored by
*not foreclosing* one, not by building one — M3_SPEC §3, §5.6); no learning, ranking,
aggregation-for-decisions, retrieval-for-memory, or experiment arms (M6/M7, D12); no change to identity
fields or `content_hash` semantics; no new verdict state (D16.7, D17).

**sqlite3 is Python standard library** → M3 introduces **no new dependency** and therefore **no Docker,
compose, or CI change** (M3_SPEC §3 "embedded and local"). Reaching for a non-stdlib driver is scope
creep and is forbidden.

## 3. Files allowed to change

Nothing outside this list may be touched. Each file is bound to the commit(s) that may edit it.

| Path | Commit(s) | Nature |
|---|---|---|
| `src/velith/core/config.py` | M3-C1 | Extend: add `episode_index_path` setting (M3_SPEC §6.3). |
| `.env.example` | M3-C1 | Document `VELITH_EPISODE_INDEX_PATH`. |
| `tests/unit/test_config.py` | M3-C1 | Extend: default + override of the new setting. |
| `src/velith/episodes/index.py` | M3-C2 | **New**: SQLite index component + typed accessors + `rebuild_from_log` + record-digest helper (M3_SPEC §6.1, §9). |
| `tests/unit/test_episode_index.py` | M3-C2 | **New**: index unit tests. |
| `src/velith/episodes/store.py` | M3-C3 | Extend: dual-write (log + index) and compute/persist the record digest; add digest check on read (M3_SPEC §6.1, §9). |
| `src/velith/runner/spike.py` | M3-C3 | **One line only**: inject `episode_index_path` from `Settings` into `EpisodeStore` (M3_SPEC §7 "at most a one-line store-call passthrough"). |
| `tests/unit/test_store.py` | M3-C3 | Extend: dual-write, backward-compat read, digest-mismatch detection, determinism preserved. |
| `tests/integration/test_m3_store_index.py` | M3-C4 | **New**: hermetic end-to-end acceptance (DoD §5). |
| `README.md` | M3-C5 | Add the "M3 — indexed episode store" section. |

## 4. Files forbidden to change

Editing any of these is out of scope and, for the frozen artifacts, a violation of the freeze.

- `src/velith/episodes/episode.py` — the **identity schema is frozen**; the record digest lives in the
  index, not the record, so this file must require **no change** (M3_SPEC §7, §9). Touching
  `content_hash`, `HASH_BOUNDARY_FIELDS`, or `HASH_EXCLUDED_FIELDS` is forbidden (M3_SPEC §8).
- `src/velith/harness/verifier_sandbox.py`, `src/velith/llm/client.py`,
  `src/velith/agent/proposer.py`, `src/velith/task.py` — unchanged (M3_SPEC §1, §7).
- `src/velith/runner/spike.py` **beyond the single permitted injection line** in M3-C3.
- `docker/verifier.Dockerfile`, `docker-compose.yml`, `.github/workflows/**` — no new dependency, no
  infra change (M3_SPEC §3).
- `pyproject.toml`, `.pre-commit-config.yaml` — no dependency or tooling change.
- `docs/DECISIONS.md`, `docs/M3_SPEC.md`, `docs/M2_SPEC.md`, `docs/M2_IMPLEMENTATION_HANDOFF.md`,
  `docs/VISION.md` — frozen record.
- `docs/PROJECT_STATE.md`, `docs/NOTES.md` — updated **only at the Freeze Milestone** by the Research
  Director, never inside an M3 code commit.
- All Node/Next files (`app/`, `components/`, `lib/`, `package.json`, `next.config.ts`, etc.) —
  unrelated to M3.

## 5. Dependency graph

Strictly linear; one atomic commit at a time. No commit may be started before its predecessor is
committed green.

```
M3-C1 (config: index path)
   │
   ▼
M3-C2 (episodes/index.py: index component + rebuild_from_log + digest helper)
   │      depends on C1 for the setting it is wired to; independently unit-testable via tmp paths
   ▼
M3-C3 (episodes/store.py: dual-write + record-digest integration; 1-line spike injection)
   │      depends on C2 (uses the index) and C1 (reads the setting)
   ▼
M3-C4 (integration: hermetic end-to-end acceptance)
   │      depends on C3 (exercises the wired store)
   ▼
M3-C5 (docs: README M3 section)
          depends on C4 (documents verified behavior)
```

Closed neutral-index field set (M3_SPEC §6.2), fixed for M3: `task_id`, `state` (the verdict),
`timestamp`, `model`, `seed`, `flaky`, `secondary_passed`, `content_hash`, plus the `record_digest`
integrity column (M3_SPEC §9). No field derived from `patch`, `prompt`, or source.

## 6. Commit breakdown

Each commit is atomic, conventional, and independently green. No commit combines concerns.

**M3-C1 — `feat: episode index path setting`**
Add `episode_index_path: Path = Path("data/episodes/episodes.db")` to `Settings` (mirrors the existing
`episode_path` field), document `VELITH_EPISODE_INDEX_PATH` in `.env.example`, and extend
`tests/unit/test_config.py` for default + env override. **Extraction note (no speculation):** M3_SPEC
§6.3 leaves the *rebuild flag* optional ("if adopted"); this handoff does **not** adopt a startup
rebuild flag — rebuild is the explicit `rebuild_from_log` operation (M3-C2), avoiding a startup
side-effect. Path setting only.

**M3-C2 — `feat: sqlite episode index (derived projection)`**
New `src/velith/episodes/index.py`: an embedded `sqlite3` index holding one row per episode over the
closed neutral field set + `record_digest`, with `content_hash` unique. Provide typed query accessors
(by each neutral field and by time range) returning neutral rows / `content_hash` identifiers (episode
materialization stays in the store, M3_SPEC §6.1), an `upsert(row)` operation, a `rebuild_from_log(log_path)`
operation that reconstructs the index from the log alone (M3_SPEC §4.2), and a single
`record_digest(serialized_line)` helper (M3_SPEC §9). The index imports `Episode` only (never `store`)
to avoid a cycle; it stores/returns **no** patch/prompt/source (M3_SPEC §3, §4.4). Unit tests in
`tests/unit/test_episode_index.py`: create/open, upsert + query by each field and time range,
`rebuild_from_log` identity (build → drop → rebuild → identical state), digest column populated,
domain-neutrality (no domain columns).

**M3-C3 — `feat: dual-write store with record-level integrity digest`**
Extend `EpisodeStore`: the constructor accepts the index path (injected); `append()` keeps its public
signature and writes the byte-identical JSONL line exactly as today, then computes the record digest
over that serialized line and upserts the neutral row + digest into the index (M3_SPEC §9). `read_all()`
continues to re-verify `content_hash` (unchanged, M3_SPEC §8) and additionally verifies the stored
record digest against the index when present, raising a loud, typed error on mismatch, distinct from the
`content_hash` check (M3_SPEC §9). One-line change in `runner/spike.py` to pass `episode_index_path`
from `Settings`. Extend `tests/unit/test_store.py`: dual-write populates the index; backward-compat read
of a pre-existing log without an index still works and re-hashes; digest mismatch is detected and loud;
`content_hash` is unchanged by index presence (determinism preserved, M3_SPEC §5.7).

**M3-C4 — `test: hermetic m3 store+index acceptance`**
New `tests/integration/test_m3_store_index.py` (hermetic, no model, no network isolation): append several
episodes including a synthetic **domain-neutral / non-software** episode (proves M3_SPEC §5.5), query by
neutral fields and time range, drop the index and `rebuild_from_log` → identical state (§5.2), corrupt a
stored log line → loud detection (§5.4), and assert `content_hash` values are unchanged and a varying
`flaky` leaves the hash inert (§5.7). Covers DoD items 1–7.

**M3-C5 — `docs: document indexed episode store`**
Add the "M3 — indexed episode store" section to `README.md` (query surface, record digest, `rebuild_from_log`,
the `VELITH_EPISODE_INDEX_PATH` setting). No `PROJECT_STATE`/`NOTES` edits here — those are the Freeze
Milestone step.

## 7. Docker verification gates (run after every commit, before it is made)

The identical containerized sequence M1/M2 used. A commit is made **only** when all four are green in
the container:

```
docker compose run --rm verifier bash -lc \
  "ruff check . && ruff format --check . && mypy src tests && pytest -q"
```

- `ruff check .` — lint (E,F,I,N,UP,B,SIM,RUF; line-length 100).
- `ruff format --check .` — formatting.
- `mypy src tests` — `--strict` per config.
- `pytest -q` — full suite.

**Zero-skip expectation:** M3 adds **no** isolation-gated tests (it introduces no network-isolation
dependency), so every M3 test must run in all environments — `pytest -q` reports **zero skips
attributable to M3**. An M3 test that depends on `CAP_SYS_ADMIN` or the network is a defect.

## 8. Rollback condition for every commit

Uniform trigger, applied per commit: **if any of the four gates in §7 is red, or the commit's own
acceptance assertions fail, do not commit.** Discard the working tree for that commit
(`git restore`/`git checkout --`), and either fix within the *same* atomic commit or stop. Per-commit
specifics:

- **M3-C1** — roll back if config fails to load with no `.env`, if the default/override test fails, or
  if any gate is red.
- **M3-C2** — roll back if `rebuild_from_log` is not bit-identical to the incrementally-built index, if
  any domain field appears in the schema, if a dependency cycle (`index` ↔ `store`) is introduced, or if
  any gate is red.
- **M3-C3** — roll back if any existing M1/M2 `content_hash` changes, if backward-compat read of a
  pre-index log fails, if digest mismatch is not detected loudly, if `spike.py` changes by more than the
  single injection line, or if any gate is red.
- **M3-C4** — roll back if rebuild-from-log identity, corruption detection, domain-agnosticism, or
  determinism-preservation assertions fail, or if any gate is red.
- **M3-C5** — roll back if docs introduce a claim not verified by C1–C4, or if any gate is red.

**Frozen-spec guard:** if a rollback is caused by a genuine contradiction with `docs/M3_SPEC.md`
(not a mere bug), **stop immediately and report the contradiction to the Research Director**. Do not
edit the frozen spec or this handoff to make the code pass.

## 9. Definition of Done

Extracted verbatim in substance from M3_SPEC §5; M3 is done when all hold, verified in-container and in
CI:

1. Every existing M1/M2 episode is readable through the new store and re-hashes to its original
   `content_hash`; no log record is rewritten.
2. Appending writes the log record and updates the index; the index drops and fully rebuilds from the
   log alone (`rebuild_from_log`) to an identical state.
3. Episodes are retrievable by each neutral field and by time range, returning materialized episodes
   whose `content_hash` is re-verified on read (mismatch fatal, D3).
4. A record-level digest is computed and stored for every episode; byte-level corruption of a stored
   record is detected on read and reported loudly, distinct from and additional to the `content_hash`
   check.
5. No index column or query path references patch, prompt, source, or any domain field; a synthetic
   non-software episode indexes and queries through the identical path.
6. The schema/index encode the categorical verdict without hard-coding a binary-only worldview; a
   future deterministic quantitative field (D22) would be additive and non-identity — demonstrated by
   design, and **built no further in M3**.
7. Introducing the index and digest changes no `content_hash`; D18 Level-4 reproducibility holds (a
   varying `flaky` leaves the content hash unchanged, D21).
8. All four gates green in the container and CI; only permitted files changed; commits atomic and
   conventional.

**Freeze Milestone (Research Director, after DoD 1–8):** update `docs/PROJECT_STATE.md` and
`docs/NOTES.md`, then tag `m3-complete`. These are not M3 code commits.

## 10. Risks

Extracted from M3_SPEC §11:

- **Dual-write inconsistency (log vs. index).** Mitigated structurally: the index is a rebuildable
  projection; on any divergence the log wins and the index is rebuilt (§4.2). Repairable by
  construction, never data loss.
- **Digest / identity confusion.** `content_hash` (identity, provenance-excluded) and `record_digest`
  (integrity, provenance-included) are named, documented, and tested as distinct, so timing cannot be
  reintroduced into identity.
- **Embedded SQLite over the Docker/WSL2 bind mount.** Durability / read-after-write / locking under the
  `--rm` lifecycle — bounded by the log-authoritative design and by the conditional Prototype Gate
  (§11).
- **Scope creep into DSL / analytics / retrieval-for-memory.** Held off by §2/§3; M3 is retrieval by
  neutral fields only.
- **Premature quantitative field.** Avoided: D22 flexibility is honored by *not foreclosing* a future
  field while building none (§2, DoD 6).
- **Dependency-cycle risk** (`store` ↔ `index`). Mitigated by C2: `index` imports `Episode` only.

## 11. Prototype gate (conditional — only if absolutely required)

Per M3_SPEC §10, M3 asserts exactly one potentially-unproven mechanism: **embedded single-file SQLite
index behavior over the Docker Desktop / WSL2 bind mount** (write durability, read-after-write, locking
under `--rm`). The gate is **armed but expected to be a no-op**, because the log is authoritative and the
index is a rebuildable projection (worst case = an index rebuild, not data loss).

- **Default: not required.** Proceed to M3-C1 directly.
- **Fires only if** Scientific Review flags the mount interaction as non-obvious. If so, discharge it
  **before M3-C1** with a one-command prototype: write N episodes through the store, drop the index,
  `rebuild_from_log`, and assert identical index state over the mounted volume.
- **A red prototype** is an architectural contradiction with a frozen spec: **stop and report to the
  Research Director.** Do not proceed to engineering and do not edit the spec.

---

*End of handoff. Engineering begins at M3-C1 only after the Research Director authorizes it; one atomic
commit at a time, stopping for review after each.*
