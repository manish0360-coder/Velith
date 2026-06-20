# Velith — M0 skeleton

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
