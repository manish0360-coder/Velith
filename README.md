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
