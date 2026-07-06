# M3_SPEC — Indexed, queryable, integrity-checked episode store

**Project:** Velith
**Milestone:** M3 — the provenance-complete episode store becomes indexed, queryable, and integrity-checked.
**Document type:** Frozen engineering contract. Once frozen, this specification is immutable; the M3 implementation is *extracted from* it and never redesigns it. A genuine architectural contradiction found during engineering is reported and stops work — it does not license editing this document in place.
**Status:** FINAL — ready for freeze.
**Date:** 2026-07-06.
**Depends on:** M2 frozen (`m2-complete`).
**Governing decisions:** D2, D3, D5, D9, D11, D12, D15, D16.1, D16.6, D16.7, D18, D21, **D22 (recorded)**.

> This specification incorporates the Research Director's six final decisions closing Research Gate 1
> (2026-07-06). No further architecture review is in scope. The manufacturing pipeline it is drafted
> against is: Research → Architecture Gate → Specification → Scientific Review → **Feasibility
> Prototype (conditional Prototype Gate)** → Research Director Review → Freeze Specification →
> Implementation Handoff → Engineering → Verification → Freeze Milestone.

---

## 1. Purpose

M1 produced a provenance-complete, content-hashed **episode** persisted as an append-only JSONL log
(D16.6). M2 made the verdict *inside* each episode trustworthy as the program's exact ground truth
(D18/D19/D21). M3 makes the **accumulated body of episodes usable and durable**: retrievable by
neutral fields, and protected against silent storage-level corruption — **without altering episode
identity and without teaching the store anything about the engineering domain.**

M3 is a storage/access hardening, not a rewrite (the M2 ethos, RK8). The proposer, the LLM client,
the verifier, and the `Episode` **identity** schema are unchanged. Everything M3 adds is a *derived,
rebuildable projection* over an unchanged authoritative log.

---

## 2. Scope — what M3 is

1. A **queryable index** over the episode log, keyed on domain-agnostic, neutral fields only.
2. A minimal **query surface** (a thin Python API) to retrieve episodes by those fields and by time
   range.
3. A **record-level integrity digest** — distinct from `content_hash` — that covers the entire
   serialized episode record (identity *and* provenance), detecting storage corruption or tampering
   that the identity hash by design does not (D21).
4. Preservation of every M1/M2 invariant: the log remains the single source of truth; reads still
   re-verify `content_hash` (D3, M1 §9); existing M1/M2 episodes remain readable and re-hash
   identically.

---

## 3. Non-goals — what M3 is explicitly not

- **No database server, no network dependency.** The index is embedded and local (SQLite). The
  store must not acquire a service to run against (D12/D15 minimal-abstraction discipline; the M2
  isolation ethos).
- **No query language / DSL.** A small, fixed set of typed accessors, not a general query engine.
- **No domain-specific indexing.** The change/`patch` is **opaque**; prompt text, source, diff
  contents, and any engineering-domain semantics are neither indexed nor interpreted. The store
  stays **completely domain-neutral** (Director decision 5) so a non-software episode from a later
  rung of the ladder (D5) travels the identical path.
- **No quantitative outcome field built in M3.** Quantitative measurements are future grounded
  evidence from the verifier (D22); M3 only refrains from foreclosing an additive field later. It
  builds none (Director decision 4).
- **No cross-episode learning, ranking, aggregation-for-decisions, retrieval-for-memory, or
  experiment arms.** Retrieval only. The shared retrieval substrate and write-filter policies are
  M6/M7 (D12); M3 must not anticipate them.
- **No change to identity fields or to `content_hash` semantics** (M2_SPEC §15). M3 must not alter
  what an episode *is*.
- **No new verdict state** (D16.7, D17).

---

## 4. Ratified design decisions (Research Gate 1 closed, 2026-07-06)

These are binding inputs, not open questions. They resolve every open question carried by the M3
draft.

**4.1 — JSONL is the authoritative source of truth.** The append-only JSONL episode log
(`./data/episodes/…`, D16.6) remains the single ground-truth record. No other store is trusted over
it. (Director decision 1.)

**4.2 — The SQLite index is a rebuildable derived projection.** The index is a *projection* of the
log: it can be deleted and reconstructed from the log alone, yielding an identical index state. It
is never authoritative; on any detected divergence, the log wins and the index is rebuilt. (Director
decision 2.)

**4.3 — P4/D22 is recorded and binds this spec.** The store is outcome-representation-flexible: it
indexes only neutral, domain-agnostic fields and makes no design choice that forecloses a future,
additive, non-identity, deterministic quantitative field — while building no such field in M3.
(D22; Director decision 3 and 4.)

**4.4 — The Episode Store is completely domain-neutral.** Only the neutral fields in §6.2 are
indexed. Nothing derived from patch, prompt, or source is indexed or interpreted. (Director decision
5.)

**4.5 — The conditional Prototype Gate stays in the pipeline.** M3 asserts one potentially-unproven
mechanism (embedded-index durability over the Docker/WSL2 bind mount); §10 records how the Gate is
discharged. (Director decision 6.)

---

## 5. Definition of Done

M3 is complete when **all** of the following hold and are verified in-container and in CI:

1. **Backward compatibility.** Every existing M1/M2 episode in the log is readable through the new
   store and re-hashes to its original `content_hash` unchanged. No log record is rewritten.
2. **Index correctness.** Appending an episode writes the log record and updates the index; the
   index can be dropped and fully rebuilt from the log alone (`rebuild_from_log`), yielding an
   identical index state.
3. **Query surface.** Episodes are retrievable by each neutral field (§6.2) and by time range,
   returning fully-materialized episodes whose `content_hash` is re-verified on read; a hash
   mismatch fails loudly (M1 invariant, D3).
4. **Record integrity.** A record-level digest (§9) is computed and stored for every episode; a
   byte-level corruption of a stored record is **detected** on read and reported loudly, distinct
   from and additional to the `content_hash` check.
5. **Domain-agnosticism proven.** No index column or query path references patch, prompt, source, or
   any domain field; a synthetic non-software episode indexes and queries through the identical path
   (asserted by test).
6. **Outcome flexibility preserved.** The schema and index encode the categorical verdict without
   hard-coding a binary-only worldview; adding a future deterministic quantitative field (D22) would
   be additive and non-identity — demonstrated by design, asserted by a schema/migration test, and
   built no further in M3.
7. **Determinism preserved.** Introducing the index and digest changes no `content_hash`; the D18
   Level-4 reproducibility of the verify→log path is intact (a varying `flaky` still leaves the
   content hash unchanged, D21).
8. **Gates.** `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` are green in the
   container and in CI; only permitted files are changed; commits are atomic and conventional; the
   milestone is tagged `m3-complete`.

---

## 6. Interfaces (shape only — the handoff specifies signatures)

**6.1 — Components.**

- A **query/index component** (working name `episodes/index.py`) exposing typed read accessors over
  the neutral fields plus time range, and a `rebuild_from_log()` operation. No SQL is surfaced to
  callers.
- The existing **store** (`episodes/store.py`) gains an append path that (a) writes the log record
  exactly as today, (b) updates the index, and (c) computes and persists the record digest (§9). The
  M1/M2 store contract (append-only log, hash-verified read) is a strict, superset-preserving
  extension — its existing behavior is unchanged.

**6.2 — Permitted index fields (closed set, domain-neutral).**

`task_id`, `state` (the verdict — D16.7), `timestamp`, `model`, `seed`, `flaky`,
`secondary_passed`, `content_hash`.

No field derived from `patch`, `prompt`, or source is permitted. This set is **closed for M3**; an
addition requires a superseding decision. A future deterministic quantitative field (D22), if ever
added, is additive and non-identity and does not reopen this set retroactively.

**6.3 — Config.** An index-path setting (mirroring the episode-log path convention) and, if adopted
in the handoff, a flag to force index rebuild. Defaults must keep the system loading with no `.env`
present (M0 invariant).

---

## 7. Anticipated repository changes (for the handoff — not authored here)

- **New:** `src/velith/episodes/index.py` — embedded SQLite index, typed query accessors, and
  `rebuild_from_log`.
- **Extended:** `src/velith/episodes/store.py` — append dual-writes log + index and computes/persists
  the record digest; kept minimal.
- **Possibly extended:** `src/velith/core/config.py` — index path (+ optional rebuild flag).
- **Unchanged (must remain so):** `agent/proposer.py`, `llm/client.py`,
  `harness/verifier_sandbox.py`, `runner/spike.py` (at most a one-line store-call passthrough), and
  the **identity** portion of `episodes/episode.py`. Per §9 the record digest is stored in the index,
  not in the episode record, so `episodes/episode.py` is expected to require **no change**.
- **Tests:** index round-trip; rebuild-from-log identity; corruption detection; backward-compat
  re-hash of existing episodes; domain-agnosticism assertion; determinism preservation.
- **Docs:** README M3 section; PROJECT_STATE at freeze.

The exact file list, function signatures, and atomic commit sequence are the handoff's concern and
are produced only after this specification is frozen.

---

## 8. Determinism and identity invariants (inherited, non-negotiable)

- **`content_hash` = identity.** It covers the reproducible identity of an episode and excludes
  volatile provenance (timing, `flaky`) per D16.1/D21. M3 adds **nothing** to it and changes
  **nothing** about it.
- **The index never enters identity.** No index-derived value is hashed into `content_hash`; the
  index is a projection, not a source (§4.2).
- **Reads re-verify identity.** Every episode read back through the store re-computes and checks its
  `content_hash`; a mismatch is loud and fatal (D3, M1 §9). The record digest (§9) is an *additional*
  check, not a replacement.

---

## 9. Record-level integrity digest

**Purpose.** `content_hash` protects *identity* and deliberately excludes provenance (D16.1/D21), so
it cannot detect corruption of the excluded fields or of the serialized record as stored. D21
anticipated this: full-record tamper-evidence is "a separate record-level digest (an M3 storage
concern), never the content hash." M3 provides it.

**Definition.** For each episode, a digest is computed over the **canonical serialized bytes of the
full record as written to the log line** (identity *and* provenance). It is distinct from, and
computed independently of, `content_hash`.

**Storage.** The digest is stored **in the SQLite index** (the derived projection), not in the JSONL
record. This keeps the log line byte-identical to M1/M2 (backward compatibility, §5.1), avoids a
self-referential digest-of-itself, and requires no change to the episode identity schema.

**Detection.** On read, the store recomputes the digest from the log-line bytes and compares it to
the digest held in the index; a mismatch signals a corrupted or tampered record and is reported
loudly, alongside (and independent of) the `content_hash` check.

**Threat model — stated honestly.** This detects post-append corruption of a stored record (bit-rot,
partial write, out-of-band edit) whenever a trusted index digest exists to compare against. It is
*not* a defense against simultaneous, consistent corruption of both the log and the index, nor a
cryptographic anti-forgery guarantee; those are outside M3's scope. On a full
`rebuild_from_log`, the digest is recomputed from the (assumed-good) log, so the log remains the
root of trust — consistent with §4.1. `content_hash` independently re-verifies identity on every
read, so identity corruption is caught even across a rebuild.

---

## 10. Prototype Gate assessment (conditional stage, Director decision 6)

M3 asserts exactly one mechanism that may be environmentally unproven: **embedded single-file SQLite
index behavior over the Docker Desktop / WSL2 bind mount** — write durability, read-after-write, and
any file-locking under the `--rm` disposable-container lifecycle.

**Assessment:** the Prototype Gate is **armed but expected to be a no-op.** Because the log is
authoritative and the index is a rebuildable projection (§4.1/§4.2), the worst-case blast radius of a
mount quirk is an index rebuild, not data loss. If Scientific Review nonetheless deems the mount
interaction non-obvious, the Gate is discharged by a **one-command prototype** that writes N episodes
through the store, drops the index, rebuilds it from the log, and asserts identical index state over
the mounted volume — a red result returns the spec to Specification and never proceeds to
Engineering. No other M3 assertion requires prototyping.

---

## 11. Risks and mitigations

- **Dual-write inconsistency (log vs. index).** Mitigated structurally: the index is a rebuildable
  projection; on any detected divergence the log wins and the index is rebuilt (§4.2). Inconsistency
  is repairable by construction, never a data-loss event.
- **Digest / identity confusion.** `content_hash` (identity, provenance-excluded) and the record
  digest (integrity, provenance-included) are named, documented (§9), and tested as distinct, so a
  future contributor cannot conflate them and reintroduce timing into identity.
- **Embedded-store behavior over the bind mount.** Bounded by §10 and by the log-authoritative
  design; the Prototype Gate is the release valve.
- **Scope creep into query DSL / analytics / retrieval-for-memory.** Held off by §3; M3 is retrieval
  by neutral fields only, and the retrieval substrate remains M6 (D12).
- **Premature quantitative field.** Avoided: D22 flexibility is honored by *not foreclosing* a future
  field, while building none in M3 (§3, §5.6, Director decision 4).

---

## 12. Verification (how M3 is proven at the Verification stage)

Confined to the same atomic, gate-verified workflow used for M1 and M2:

1. Each atomic commit passes `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` in
   the container before it is made.
2. The DoD (§5) is demonstrated by the M3 test set: index round-trip and rebuild-from-log identity;
   corruption detection via the record digest; backward-compat re-hash of every existing M1/M2
   episode; a domain-agnosticism assertion; and a determinism-preservation assertion (content hashes
   unchanged, varying `flaky` inert).
3. CI runs the identical containerized sequence and gates the build on green.
4. Only after green: tag `m3-complete` and update PROJECT_STATE at the Freeze Milestone stage.

---

## 13. Freeze

On the Research Director's freeze, this document is immutable. The M3 implementation handoff is
produced next, extracted from this specification, and the M3 engineering that follows manufactures
only what is written here.
