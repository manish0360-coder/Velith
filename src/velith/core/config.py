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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance.

    Constructed once and cached. Construction performs validation, so the first
    call is where invalid configuration surfaces. The cache holds a single
    immutable instance; it is an accessor, not mutable global state.
    """
    return Settings()
