# Velith M0 — containerized verifier shell.
#
# This image is the *container shell* that M2 will later harden into the
# deterministic SWE verifier. In M0 it contains NO verification, agent, model,
# or dataset logic — only the project's Python toolchain, capable of running
# pytest inside a pinned Linux environment.
#
# Base image is pinned to a specific patch tag (no `latest`); reproducibility
# starts at M0 (§6).
FROM python:3.12.7-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# The M1 verifier applies candidate patches with `git apply` and isolates state via
# `git reset --hard` / `git clean -fd` on a disposable workspace (M1 spec §13,
# handoff §4.4 / RK3). The slim base image has no git, so install it here. This is
# the explicitly-permitted M1 Dockerfile modification (M1 spec §4).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (better layer caching). The package build needs the
# metadata, the readme, and the source tree.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install ".[dev]"

# Tests are not part of the installed package; copy them in for execution.
COPY tests/ ./tests/

# Default action: run the sanity test suite inside the container. CI overrides
# this command for the lint and type-check steps.
CMD ["pytest"]
