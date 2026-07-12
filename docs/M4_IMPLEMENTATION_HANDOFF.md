# M4_IMPLEMENTATION_HANDOFF

**Project:** Velith
**Milestone:** M4 — task corpus loader and mechanically-enforced held-out lock.
**Document type:** Frozen implementation handoff. It is *extracted from* `docs/M4_SPEC.md` (FINAL,
frozen under D23) and adds no design. Every clause traces to a spec section. Engineering manufactures
only what is written here; a genuine contradiction with the frozen spec **stops work and is reported**
— it never licenses editing the spec or this handoff.
**Status:** Ready for engineering.
**Date:** 2026-07-06.
**Extracted from:** `docs/M4_SPEC.md` §1–§8. **Governing decisions:** D4, D5, D8, D9, D12, D15, D16.3,
D21, D22, D23; future guidance D24/D25 is **not** implemented (D23).
**Manufacturing-pipeline position:** Specification → **Implementation Handoff (this document)** → One
Atomic Commit → Docker Verification → Commit → Review → Next Commit.

---

## 1. Objective

Lift the loop from one fixture task (D16.3) to a **corpus** of grounded tasks, and install the
**mechanically-enforced held-out lock** (D8, condition 3) so held-out task identities can never enter
any experience/memory path (M4_SPEC §1). Both are **domain-neutral**: a task is an opaque
specification plus a verification handle owned by the verifier; the loader and lock never inspect task
materials or the verification mechanism (D9, D22). M4 builds **directly on the frozen M3 store** by
composition — the append-only JSONL log and its derived index are used unchanged (M4_SPEC §1, §4).

## 2. Scope

**In scope (M4_SPEC §2/§3):**

1. A **content-addressed corpus manifest** assigning each task identity to exactly one partition —
   *available* or *held-out* — with a stable manifest hash that freezes the split (§3.1).
2. A **task corpus loader** that materializes many domain-neutral task values from a corpus source,
   labeled by partition, treating materials and the verification handle as opaque (§3.2).
3. A **held-out lock and single guarded persistence boundary**: one authoritative exclusion predicate
   keyed on content-addressed task identity, and the only writer into the frozen `EpisodeStore` on the
   experience path — it raises loudly on a held-out task's episode and delegates available-task
   episodes to the frozen store unchanged (§3.3).

**Out of scope — hard boundaries (M4_SPEC §6):** the batch runner and cold baseline A0 (M5), model
routing/cost guard (M5), the retrieval substrate (M6), write-filter arms A1/A2 (M7), frozen
checkpointed evaluation (M8), pre-registration freeze (M9), Stage-1 statistics/go-no-go (M10); any
specific dataset ETL/download pipeline beyond the neutral loader contract — a concrete adapter such as
SWE-bench is a **registration, not architected or built in M4**; any change to frozen M0–M3 contracts;
calibration; the second vertical; and everything in D15. **Future principles D24/D25 are recorded
guidance only and are not implemented (D23).**

M4 is **pure in-process logic over local files** that composes the already-verified M3 store: it adds
**no new dependency**, and therefore **no Docker, compose, or CI change** (M4_SPEC §7).

## 3. Files allowed to change

Nothing outside this list may be touched. Each file is bound to the commit(s) that may edit it. Module
names follow M4_SPEC §5 ("names are indicative"); the `corpus` package is the domain-neutral home.

| Path | Commit(s) | Nature |
|---|---|---|
| `src/velith/core/config.py` | M4-C1 | Extend (additive settings only): corpus source, manifest location, partition specification (M4_SPEC §5/§6.3-analogue). |
| `.env.example` | M4-C1 | Document the new `VELITH_*` corpus settings. |
| `tests/unit/test_config.py` | M4-C1 | Extend: defaults + overrides of the new settings. |
| `src/velith/corpus/__init__.py` | M4-C2 | **New**: package marker for the domain-neutral corpus components. |
| `src/velith/corpus/manifest.py` | M4-C2 | **New**: content-addressed partition manifest + stable hash (§3.1). |
| `tests/unit/test_corpus_manifest.py` | M4-C2 | **New**: manifest unit tests. |
| `src/velith/corpus/loader.py` | M4-C3 | **New**: domain-neutral corpus loader yielding partitioned task values (§3.2). |
| `tests/unit/test_corpus_loader.py` | M4-C3 | **New**: loader unit tests. |
| `tests/fixtures/corpus_min/**` | M4-C3 | **New**: a synthetic, domain-neutral fixture corpus for hermetic tests. |
| `src/velith/corpus/heldout.py` | M4-C4 | **New**: held-out lock predicate + single guarded persistence boundary composing the frozen `EpisodeStore` (§3.3). |
| `tests/unit/test_heldout_lock.py` | M4-C4 | **New**: lock + guarded-boundary unit tests. |
| `tests/integration/test_m4_corpus_heldout.py` | M4-C5 | **New**: hermetic end-to-end acceptance (§2/§8). |
| `README.md` | M4-C6 | Add the "M4 — corpus and held-out lock" section. |

## 4. Files forbidden to change

Editing any of these is out of scope and, for the frozen artifacts, a violation of the freeze.

- **Frozen M3 substrate — composed, never modified:** `src/velith/episodes/episode.py`,
  `src/velith/episodes/store.py`, `src/velith/episodes/index.py` (M4_SPEC §4). The held-out boundary
  wraps `EpisodeStore`; it must not alter it.
- **Frozen task/verifier/model seams:** `src/velith/task.py`, `src/velith/harness/verifier_sandbox.py`,
  `src/velith/llm/client.py`, `src/velith/agent/proposer.py`, `src/velith/runner/spike.py`
  (M4_SPEC §5).
- **Infra (no new dependency):** `docker/verifier.Dockerfile`, `docker-compose.yml`,
  `.github/workflows/**`, `pyproject.toml`, `.pre-commit-config.yaml` (M4_SPEC §2/§7).
- **Frozen record:** `docs/DECISIONS.md`, `docs/M4_SPEC.md`, `docs/M3_SPEC.md`, `docs/M2_SPEC.md`,
  and the earlier frozen handoffs/specs.
- **Freeze-Milestone-only:** `docs/PROJECT_STATE.md`, `docs/NOTES.md` — updated only at the M4 Freeze
  Milestone by the Research Director, never inside an M4 code commit.
- **Unrelated:** all Node/Next files (`app/`, `components/`, `lib/`, `package.json`, etc.).
- **Per commit:** any file not in that commit's row of §3.

## 5. Dependency graph

Strictly linear; one atomic commit at a time. No commit may begin before its predecessor is committed
green.

```
M4-C1 (config: corpus + partition settings)
   │
   ▼
M4-C2 (corpus/manifest.py: content-addressed partition + stable hash)
   │      the partition source of truth for C3 and C4
   ▼
M4-C3 (corpus/loader.py: partitioned, domain-neutral task values)
   │      depends on C2 (partition labels) and C1 (locations)
   ▼
M4-C4 (corpus/heldout.py: exclusion predicate + guarded persistence boundary)
   │      depends on C2 (identity/partition); composes the FROZEN EpisodeStore
   ▼
M4-C5 (integration: hermetic corpus + held-out acceptance)
   │      depends on C2-C4
   ▼
M4-C6 (docs: README M4 section)
          depends on C5 (documents verified behaviour)
```

Partition vocabulary is closed for M4: **available** | **held-out** (M4_SPEC §3.1). Task identity is
**content-addressed** — a hash over the task's identity material, independent of any mutable display
label, so relabeling cannot move a task across the partition (M4_SPEC §3.3; the exact identity-material
selection is an engineering detail bounded by this invariant, not an architecture choice).

## 6. Commit breakdown

Each commit is atomic, conventional, and independently green. No commit combines concerns.

**M4-C1 — `feat: corpus and partition settings`**
Add additive, validated settings to `Settings` for the corpus source location, the manifest location,
and the partition specification (M4_SPEC §5). Each carries a safe default so the system still loads
with no `.env` (M0 invariant). Document the new `VELITH_*` variables in `.env.example`; extend
`tests/unit/test_config.py` for default + env override.

**M4-C2 — `feat: content-addressed corpus manifest`**
New `corpus/manifest.py`: represent the partition assignment (each task identity → *available* |
*held-out*) and expose a **stable content hash** over that assignment (M4_SPEC §3.1). Identity is
content-addressed so relabeling cannot cross the partition. Unit tests in `test_corpus_manifest.py`:
the manifest hash is stable across repeated loads; it changes **iff** the split changes; the identity
key is content-addressed (relabeling a task's display label does not move it); each task resolves to
exactly one partition.

**M4-C3 — `feat: domain-neutral task corpus loader`**
New `corpus/loader.py`: materialize **many** domain-neutral task values from a corpus source, each
labeled with its partition from the manifest (M4_SPEC §3.2). Materials and the verification handle are
**opaque** — the loader parses no diff/test/domain content. It generalizes M1's single-fixture loading
**without modifying `task.py`**. Add a synthetic, domain-neutral fixture corpus under
`tests/fixtures/corpus_min/`. Unit tests in `test_corpus_loader.py`: loads N > 1 tasks with partition
labels; never inspects materials; a synthetic non-software corpus loads through the identical path.

**M4-C4 — `feat: held-out lock and guarded persistence boundary`**
New `corpus/heldout.py`: the single authoritative **exclusion predicate** keyed on content-addressed
task identity, and the single **guarded persistence boundary** that composes the frozen `EpisodeStore`
— it **raises loudly** rather than persist a held-out task's episode, and delegates available-task
episodes to the frozen store unchanged (M4_SPEC §3.3, §4). It must fail closed: an episode whose task
identity is absent from the frozen manifest is refused, never silently admitted (single-chokepoint
invariant, §4; D8). Unit tests in `test_heldout_lock.py`: the predicate is authoritative and
content-addressed (relabel cannot cross); the boundary raises on held-out and on unknown identity; a
delegated available-task episode yields a log line and derived index row **byte-for-byte identical** to
a direct M3 append (M3 composed, not altered).

**M4-C5 — `test: hermetic m4 corpus+heldout acceptance`**
New `tests/integration/test_m4_corpus_heldout.py` (hermetic; no model, no verifier, no network
isolation): a corpus loads partitioned; the lock excludes exactly the held-out set; the guarded
boundary refuses held-out and persists available via the frozen store byte-identically; the manifest
hash is stable and changes iff the split changes; a synthetic non-software corpus flows identically.
Covers M4_SPEC §8 acceptance criteria 1–7 and the §2 Definition of Done.

**M4-C6 — `docs: document corpus loader and held-out lock`**
Add the "M4 — corpus and held-out lock" section to `README.md` (the corpus loader, the
partition/manifest and its hash, the held-out lock + guarded boundary, and the new settings). No
`PROJECT_STATE`/`NOTES` edits — those are the Freeze Milestone step.

## 7. Docker verification gates (run after every commit, before it is made)

The identical containerized sequence M1–M3 used. A commit is made **only** when all four are green in
the container:

```
docker compose run --rm verifier bash -lc \
  "ruff check . && ruff format --check . && mypy src tests && pytest -q"
```

- `ruff check .` — lint (E,F,I,N,UP,B,SIM,RUF; line-length 100).
- `ruff format --check .` — formatting.
- `mypy src tests` — `--strict` per config.
- `pytest -q` — full suite.

**Zero-skip expectation:** M4 adds **no** isolation-gated tests (it introduces no network-isolation
dependency), so `pytest -q` reports **zero skips attributable to M4**. An M4 test that depends on
`CAP_SYS_ADMIN` or the network is a defect.

## 8. Rollback condition for every commit

Uniform trigger, applied per commit: **if any of the four gates in §7 is red, or the commit's own
acceptance assertions fail, do not commit.** Discard the working tree for that commit
(`git restore`/`git checkout --`), and either fix within the *same* atomic commit or stop. Per-commit
specifics:

- **M4-C1** — roll back if config fails to load with no `.env`, if a default/override test fails, or if
  any gate is red.
- **M4-C2** — roll back if the manifest hash is unstable across loads, if it fails to change when the
  split changes, if the identity key is not content-addressed (relabel moves a task), or if any gate is
  red.
- **M4-C3** — roll back if the loader inspects task materials/verification handle, if it modifies
  `task.py`, if a non-software synthetic corpus does not load through the identical path, or if any
  gate is red.
- **M4-C4** — roll back if a held-out or unknown-identity episode is ever persisted, if the predicate is
  not content-addressed, if a delegated available-task episode is **not** byte-identical to a direct M3
  append, if `EpisodeStore` is modified rather than composed, or if any gate is red.
- **M4-C5** — roll back if any acceptance assertion (partitioned load, exact exclusion, byte-identical
  delegation, manifest-hash stability, domain-neutral flow) fails, or if any gate is red.
- **M4-C6** — roll back if docs introduce a claim not verified by C1–C5, or if any gate is red.

**Frozen-spec guard:** if a rollback is caused by a genuine contradiction with `docs/M4_SPEC.md` (not a
mere bug), **stop immediately and report the contradiction to the Research Director.** Do not edit the
frozen spec or this handoff to make the code pass, and do not introduce D24/D25 to resolve it (D23).

## 9. Definition of Done

Extracted from M4_SPEC §2/§8; M4 is done when all hold, verified in-container and in CI:

1. A corpus of many tasks loads into domain-neutral task values, replacing the single-fixture
   assumption, without the loader inspecting materials or the verification handle.
2. Every loaded task carries a partition label — *available* or *held-out* — assigned by the
   content-addressed manifest, deterministically and reproducibly.
3. The held-out lock exposes one authoritative exclusion predicate, keyed on content-addressed task
   identity, robust to relabeling.
4. A single guarded persistence boundary is the only experience-path writer into the frozen store: it
   raises on held-out (and unknown) tasks and delegates available-task episodes to the frozen
   `EpisodeStore` unchanged.
5. The partition is frozen by a manifest hash that is stable across runs and changes iff the split
   changes.
6. Domain-neutrality is demonstrated: a synthetic non-software corpus loads, partitions, and locks
   through the identical path.
7. No frozen M0–M3 file is modified; the only `core/config.py` change is additive settings.
8. All four gates are green in the container and CI; commits are atomic and conventional.

**Freeze Milestone (Research Director, after DoD 1–8):** update `docs/PROJECT_STATE.md` and
`docs/NOTES.md`, then tag `m4-complete`. These are not M4 code commits.

## 10. Risks

Extracted from M4_SPEC §7:

- **Chokepoint leakage.** More than one experience-path writer would let held-out leak in. *Mitigation:*
  exactly one guarded persistence boundary (§3.3/§4); the frozen store is never written on the
  experience path except through it — enforced by the C4 tests and the byte-identity check.
- **Identity smuggling.** A mutable string id could relabel a held-out task into the available set.
  *Mitigation:* content-addressed identity (C2/C4); relabel-cannot-cross is a rollback trigger.
- **Domain-neutrality erosion.** Temptation to inspect task materials (software test shape).
  *Mitigation:* opaque materials/handle; software lives only in a (deferred) registered adapter.
- **Split drift.** An unhashed partition cannot be mechanically frozen. *Mitigation:* the
  content-addressed manifest hash freezes the split (C2).
- **Coupling to frozen M3.** Enforcement must not require editing the frozen store. *Mitigation:* the
  guarded boundary **composes** `EpisodeStore` (wrapper), never modifies it (§4; C4 byte-identity test).
- **Non-determinism in partitioning.** A per-run RNG split would be unreproducible. *Mitigation:*
  hash-derived, deterministic assignment (C2).

## 11. Prototype gate (conditional — not required)

Per M4_SPEC §7, M4 asserts **no** unproven environmental mechanism: it is pure in-process logic over
local files that composes the already-verified M3 store. The Prototype Gate is therefore **not
required (no-op)**; it fires only if Scientific Review identifies a load-bearing unproven assumption,
which none is anticipated. Proceed directly to M4-C1.

---

*End of handoff. Engineering begins at M4-C1 only after the Research Director authorizes it; one atomic
commit at a time, stopping for review after each. Future principles D24/D25 are not implemented in M4
(D23).*
