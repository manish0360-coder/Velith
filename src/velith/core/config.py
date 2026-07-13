"""Configuration for Velith.

A single validated :class:`Settings` object sourced from the environment is the
*only* sanctioned way to read configuration (M0 §7). There are no scattered
``os.getenv`` calls or magic numbers elsewhere in the project.

Invalid configuration fails loudly at construction (M0 §10): an unknown value
raises :class:`pydantic.ValidationError` immediately rather than silently
defaulting to something wrong. A misconfigured system refuses to start.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "ci", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LogFormat = Literal["json", "console"]


class Settings(BaseSettings):
    """Validated, immutable application settings.

    Every field carries a safe default, so the object loads and validates with
    no ``.env`` present. Values are read from environment variables prefixed
    with ``VELITH_`` (e.g. ``VELITH_LOG_LEVEL``). The object is frozen: there is
    no global mutable state to drift (M0 §7).
    """

    model_config = SettingsConfigDict(
        env_prefix="VELITH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    app_name: str = "velith"
    environment: Environment = "development"
    log_level: LogLevel = "INFO"
    log_format: LogFormat = "json"

    # --- M1 settings (extends M0; M1 spec §4 / handoff §4.8) ---
    # Ollama reachability and model. The host targets host.docker.internal so the
    # in-container spike reaches the host's Ollama (D16.2). The model is overridable
    # via VELITH_OLLAMA_MODEL to whatever the operator has pulled (Q5/D16.5).
    ollama_host: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen2.5-coder"
    ollama_timeout_seconds: float = 120.0

    # Verifier wall-clock budget for hidden-test execution.
    verifier_timeout_seconds: float = 60.0

    # Append-only JSONL episode store path (host-mounted + gitignored in C9).
    episode_path: Path = Path("data/episodes/episodes.jsonl")

    # --- M2 settings (verifier hardening; M2_SPEC §4) ---
    # Number of times the primary hidden test is re-run for flake detection.
    # Placeholder in M2-C1 (the pinned-environment commit); consumed by the flake
    # loop in M2-C3.
    flake_rerun_count: int = 3

    # Run the Phase-2 hidden-test step network-isolated (`unshare -n`, needs
    # CAP_SYS_ADMIN). Mandatory in production; if the mechanism is unavailable the
    # verifier raises rather than running untrusted code unisolated (D19).
    verifier_network_isolation: bool = True

    # --- M3 settings (indexed episode store; M3_SPEC §6.3) ---
    # Path to the derived SQLite index over the episode log. The JSONL log
    # (`episode_path`) stays authoritative; this index is a rebuildable
    # projection of it (M3_SPEC §4.1-§4.2), consumed from M3-C2 onward. It lives
    # under the same host-mounted, gitignored `data/episodes/` directory.
    episode_index_path: Path = Path("data/episodes/episodes.db")

    # --- M4 settings (task corpus + held-out lock; M4_SPEC §5) ---
    # Path-only locators for the corpus and its partition. These declare *where*
    # the inputs live; no partition logic lives here (that is the manifest and
    # loader, M4-C2/M4-C3). Each has a safe default so the system still loads with
    # no `.env` (M0 invariant).
    # Root of the task corpus source (opaque task materials); read by the loader (M4-C3).
    corpus_path: Path = Path("data/corpus")
    # Content-addressed partition manifest (available/held-out assignment + hash);
    # written and read by the manifest (M4-C2) and consulted by the loader (M4-C3).
    corpus_manifest_path: Path = Path("data/corpus/manifest.json")
    # The declared partition specification (the pre-committed available/held-out
    # split) from which the manifest is materialized; consumed by the manifest (M4-C2).
    corpus_partition_spec_path: Path = Path("data/corpus/partition.json")

    # --- M5 settings (batch runner + cold baseline arm A0; M5_SPEC §3.4/§3.5) ---
    # The fixed base model for a batch sweep (one non-saturating model; D8 §1). Recorded
    # in the run provenance as part of the experiment identity; consumed from M5-C2/C3.
    batch_base_model: str = "qwen2.5-coder"
    # The run's batch seed. Each task's seed is deterministically derived from
    # (task identity, batch seed) in M5-C2; recorded in the run provenance.
    batch_seed: int = 0
    # Cost-guard limits (M5_SPEC §3.4) — deterministic resource bounds enforced by the
    # guard in M5-C3 and recorded as experiment identity; `0` means "unbounded". Per-step
    # timeouts reuse `ollama_timeout_seconds` / `verifier_timeout_seconds`.
    batch_max_tasks: int = 0
    batch_max_attempts_per_task: int = 1
    batch_max_tokens: int = 0

    # --- M6 settings (shared retrieval substrate; M6_SPEC §5) ---
    # Number of neighbours the retriever returns (a deterministic bound); consumed by
    # the retriever (M6-C5).
    retrieval_top_k: int = 5
    # The single fixed, deterministic, domain-neutral embedding component used by the
    # shared substrate (no routing; one component); consumed by the embedding seam (M6-C3).
    retrieval_embedder: str = "hashed-ngram"
    # The read-only episode memory the retriever reads (M6_SPEC §3.1), defaulting to the
    # frozen M3 episode log. Read-only — M6 never writes here; consumed by the memory
    # source (M6-C4).
    retrieval_memory_path: Path = Path("data/episodes/episodes.jsonl")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance.

    Constructed once and cached. Construction performs validation, so the first
    call is where invalid configuration surfaces. The cache holds a single
    immutable instance; it is an accessor, not mutable global state.
    """
    return Settings()
