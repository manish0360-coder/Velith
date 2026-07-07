# Velith

Project skeleton and environment validation. M0 proves the full toolchain runs
end-to-end on the verified environment — Docker build, containerized pytest,
configuration load, structured logging, and CI green from a fresh clone —
**before any agent, model, dataset, or verification logic exists**. The sanity
check inside the container is a placeholder whose only job is to prove the pipe
is connected.

> This README documents how to *run and reproduce* M0. The project's *why* and
> *how* live in their own documents (`docs/VISION.md`, `docs/DECISIONS.md`).

## Prerequisites

- **WSL2 + Ubuntu** — all container builds and test execution happen in the
  Linux environment, not native Windows.
- **Docker** with the Compose v2 plugin (`docker compose ...`).
- **Git**.

Optional, for local editor tooling and pre-commit only (never the source of
truth for a verdict):

- **Python 3.12** on the host.
- **Ollama** is assumed present for later milestones but is **not used in M0**.

## Run it (one command)

From a fresh clone, on WSL2/Ubuntu, build the container and run the sanity
check to green:

```bash
docker compose run --rm --build verifier
```

This builds the image from `docker/verifier.Dockerfile` and runs the sanity
test **inside the container**. The host Python is never used to produce the
verdict.

### Interpreting the result

- **Green** — the command exits `0` and pytest reports all tests passed. This
  proves: Docker builds, the Linux container runs the project's Python, pytest
  executes inside the container, configuration loads and validates, and
  structured logging emits. The foundation is sound.
- **Red** — the command exits non-zero and the underlying cause is printed.
  A red result means the foundation is broken and must be fixed before any
  later milestone, which all assume this path works.

## Configuration

Configuration is a single validated object (`src/velith/core/config.py`),
sourced from environment variables prefixed `VELITH_`. All settings have safe
defaults, so the system loads with no `.env` present; an invalid value fails
loudly at startup. See `.env.example` for the documented variables. Copy it to
`.env` (gitignored) to override locally:

```bash
cp .env.example .env
```

## Local development (optional)

To run the same lint/type/format gates the container and CI run, and to enable
the pre-commit hooks:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

Continuous integration (`.github/workflows/ci.yml`) runs the identical
containerized sequence — `ruff check`, `ruff format --check`, `mypy --strict`,
and the sanity test — on every push and pull request, gating the build on
green.

## M1 — the spike: propose → verify → log

M1 runs **one** engineering task end to end: a local model **proposes** a
candidate patch, a containerized verifier **disposes** of it against a hidden
test, and the outcome is logged as a provenance-complete, content-hashed
**episode** that survives container exit. It is a spike (one task, one model),
not a system.

### Additional prerequisite

- **Ollama** running on the host with a code model pulled. The default model is
  `qwen2.5-coder`; override it with `VELITH_OLLAMA_MODEL` to whatever you have
  installed:

```bash
ollama pull qwen2.5-coder              # or your preferred local coder model
export VELITH_OLLAMA_MODEL=qwen2.5-coder
```

### Run it

```bash
docker compose run --rm verifier python -m velith.runner.spike --task calc_add_bug --seed 0
```

The loop runs **inside the container** (the verdict is never produced on the
host) and prints a one-line summary:

```
PASSED episode -> data/episodes/episodes.jsonl (hash <sha256>)
```

The episode is appended to `./data/episodes/episodes.jsonl` on the host
(bind-mounted, gitignored) and **survives `--rm`**.

### How the container reaches Ollama (`host.docker.internal`)

The spike runs in the container, but Ollama runs on the host. The container
reaches it at `host.docker.internal` (configurable via `VELITH_OLLAMA_HOST`,
default `http://host.docker.internal:11434`). `docker-compose.yml` makes that
name resolvable with:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

Docker Desktop resolves it automatically; the explicit mapping keeps it
portable. If Ollama is unreachable the run aborts loudly with `INFRA_ERROR` and
a non-zero exit — it never logs a misleading episode.

### Outcomes (verdict taxonomy)

A run **succeeds** (exit `0`) for any *grounded* verdict — the loop ran and
produced a result worth learning from:

- `PASSED` — patch applied, hidden tests passed.
- `FAILED` — patch applied, hidden tests ran and did not pass. **A valid
  outcome, not an error.**
- `PATCH_APPLY_FAILED` — the candidate patch did not apply cleanly.
- `NO_PATCH` — the model produced no usable patch.

Only `INFRA_ERROR` (Ollama unreachable, container fault) is an error: it aborts
with a non-zero exit and is logged loudly, with no episode written.

### Record / replay reproducibility

The model step is stochastic, so M1 does **not** gate on "same seed → same
patch." What M1 guarantees is that the **verify → log path is reproducible given
a recorded proposal**: re-running verification and logging on a *fixed* patch
yields the **same verdict and the same `content_hash`**.

This holds because:

- The verifier operates on a disposable copy of the fixture repo, reset to a
  clean baseline before each run, so prior state cannot leak.
- The content hash covers the episode's content fields only. Volatile timing —
  `timestamp`, `latency_seconds`, `verify_seconds` — is **excluded** from the
  hash, and non-deterministic timing in the captured test output is normalized,
  so a fixed proposal always hashes identically.

You can confirm this deterministic spine without a model at all — the hermetic
integration test exercises the real verify→log path with a mocked proposer and
asserts a stable verdict and hash:

```bash
docker compose run --rm verifier pytest -q tests/integration/test_spike_episode.py
```

### Inspecting logged episodes

```bash
cat data/episodes/episodes.jsonl
```

Each line is one episode: the task, the exact prompt, the candidate patch, the
verdict and raw test output, token/latency provenance, and the `content_hash`
that is re-verified whenever episodes are read back.

## M2 — the hardened verifier

M2 makes the verifier trustworthy as the program's exact ground truth: the verdict is
produced under a pinned, network-isolated, two-phase execution; flaky tests are
detected and flagged; and a held-out secondary suite surfaces the software "model gap."
The verdict taxonomy is unchanged — `PASSED`, `FAILED`, `PATCH_APPLY_FAILED`,
`NO_PATCH`, `INFRA_ERROR`.

### Requirement: `CAP_SYS_ADMIN`

The verifier isolates the test-execution step from the network with `unshare -n`, which
requires the `CAP_SYS_ADMIN` capability. `docker-compose.yml` grants it to the verifier
container:

```yaml
cap_add:
  - SYS_ADMIN
```

Isolation is **mandatory**: if the capability is unavailable, the verifier raises
(`INFRA_ERROR`) rather than running untrusted code with network access. The R3
prototype found that unprivileged `unshare -rn` is blocked by the Docker Desktop / WSL2
seccomp profile, so this capability is the supported mechanism (see `docs/NOTES.md` for
the environment record).

### Two-phase execution

- **Phase 1 (network ON):** workspace and dependency preparation.
- **Phase 2 (network OFF):** the hidden tests run wrapped in `unshare -n`, so generated
  code cannot reach the network.

### Determinism Level 4

The verdict is reproducible to **Level 4** — same *execution environment*. The test
process runs with a pinned environment (`PYTHONHASHSEED=0`, `TZ=UTC`, `LC_ALL=C`) in the
pinned base image, so the verdict, its normalized output, and the `content_hash` are
bit-for-bit reproducible for a fixed patch.

### Flake detection (`flaky`)

The primary test is run several times (`VELITH_FLAKE_RERUN_COUNT`, default `3`). If the
runs disagree, the measurement is untrustworthy: the episode is flagged `flaky=True` and
a loud log is emitted. Flakiness is **provenance, not a verdict** — no new verdict state
is introduced, and `flaky` is **excluded from the `content_hash`** (it can vary between
re-runs, so hashing it would break reproducibility).

### Held-out secondary suite (`secondary_passed`)

After the primary verdict, the verifier runs a **held-out secondary** suite — extra
cases never shown to the model. A patch that games the visible test (e.g. hardcoding the
expected value) passes the primary but fails the secondary, recorded as
`secondary_passed=False`: the **model gap**. The secondary suite is re-materialized from
the pristine fixture *after* the patch is applied, so a candidate patch cannot tamper
with the held-out check. Unlike `flaky`, `secondary_passed` is part of episode identity
(inside the `content_hash`).

### Relevant settings

- `VELITH_VERIFIER_NETWORK_ISOLATION` — isolate the test step (default `true`).
- `VELITH_FLAKE_RERUN_COUNT` — primary-test reruns for flake detection (default `3`).

## M3 — the indexed episode store

M3 makes the accumulated episodes **queryable and durable** without changing what an
episode *is*. The append-only JSONL log stays the single source of truth; alongside it
the store maintains a **derived SQLite index** that is a *rebuildable projection* of the
log — it can be deleted and reconstructed from the log at any time, and is never trusted
over it. Episode identity (the `content_hash`) is untouched.

### Query surface

Episodes are indexed on **neutral, domain-agnostic fields only** — `task_id`, verdict
`state`, `timestamp`, `model`, `seed`, `flaky`, `secondary_passed`, and `content_hash` —
and are retrievable by each of those fields and by time range. The change/`patch`, the
prompt, and any source are **never indexed**: the store carries no knowledge of the
engineering domain, so a non-software episode is indexed and queried through the exact
same path.

### Record-level integrity digest

Each indexed row also carries a `record_digest`: a SHA-256 over the **full serialized
record** (identity *and* provenance). It is distinct from the `content_hash`, which
covers identity only and deliberately excludes provenance (`timestamp`,
`latency_seconds`, `verify_seconds`, `flaky`). On read, the store re-verifies both — a
`content_hash` mismatch raises `EpisodeIntegrityError`, and a record-digest mismatch (for
example, tampering with a provenance field the content hash excludes) raises
`RecordIntegrityError`. Corruption is loud, never silent.

### Rebuilding the index

Because the index is a projection, it can always be rebuilt from the authoritative log:

```python
from pathlib import Path
from velith.episodes.index import EpisodeIndex

with EpisodeIndex(Path("data/episodes/episodes.db")) as index:
    index.rebuild_from_log(Path("data/episodes/episodes.jsonl"))
```

A store constructed without an index path keeps the exact M1/M2 log-only behaviour, so
existing logs remain readable unchanged.

### Relevant settings

- `VELITH_EPISODE_INDEX_PATH` — location of the derived SQLite index (default
  `data/episodes/episodes.db`, under the same gitignored `data/episodes/` directory as
  the log).

## M4 — the task corpus and held-out lock

M4 lifts the loop from one fixture task to a **corpus**, under a mechanically-enforced
held-out partition that no experience path can cross. It is **domain-neutral**: a task is
an opaque *material* (its identity content) plus an opaque *verification handle*, and the
corpus layer never inspects either. Nothing about M0–M3 changes — M4 composes the frozen
episode store.

### Corpus loader

`load_corpus(corpus_path, partition_spec_path)` reads a neutral corpus source (a
`corpus.json` of task descriptors) and a declared partition specification, and returns a
`LoadedCorpus`: the partitioned `CorpusTask` values and the content-addressed manifest.
Each task carries a `label` (display id), an opaque `material`, an opaque `handle`, and its
`partition` — assigned **from the manifest**, never from the mutable label. Materials and
handles are carried verbatim; the loader parses no diff/test/domain content, so a
non-software corpus loads through the identical path. A concrete real-dataset adapter
(e.g. SWE-bench) is a registration conforming to this contract and is outside M4 scope.

### Content-addressed partition and its hash

A task's **identity** is a SHA-256 over its opaque material, independent of the mutable
display label — so renaming a task cannot move it across the partition. The manifest maps
identity → partition (`available` | `held_out`) and exposes a stable `manifest_hash` over
that assignment: identical for the same split, and different the moment the split changes.
This freezes the split reproducibly.

### Held-out lock and guarded persistence boundary

`HeldOutLock` is the single authoritative exclusion predicate, keyed on content-addressed
identity. `GuardedEpisodeWriter` is the **only** experience-path writer into the frozen
episode store: `persist(identity, episode)` delegates an available task's episode to the
store unchanged (byte-for-byte identical to a direct append), and raises `HeldOutError` for
a held-out task or for an identity absent from the manifest (**fail-closed**). Enforcement
is a raised error at one chokepoint — mechanical, never convention.

```python
from pathlib import Path

from velith.corpus.heldout import GuardedEpisodeWriter, HeldOutLock
from velith.corpus.loader import load_corpus
from velith.episodes.store import EpisodeStore

loaded = load_corpus(Path("data/corpus"), Path("data/corpus/partition.json"))
store = EpisodeStore(Path("data/episodes/episodes.jsonl"), Path("data/episodes/episodes.db"))
writer = GuardedEpisodeWriter(HeldOutLock(loaded.manifest), store)

# writer.persist(task.identity, episode): an available task is stored unchanged;
# a held-out or unknown task raises HeldOutError (fail-closed).
```

### Relevant settings

- `VELITH_CORPUS_PATH` — root of the task corpus source (default `data/corpus`); read by
  the loader.
- `VELITH_CORPUS_PARTITION_SPEC_PATH` — the declared partition specification (default
  `data/corpus/partition.json`); read by the loader.
- `VELITH_CORPUS_MANIFEST_PATH` — location for the content-addressed manifest (default
  `data/corpus/manifest.json`). In M4 the manifest is produced in-memory by the loader
  (`LoadedCorpus.manifest`).
