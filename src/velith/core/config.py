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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance.

    Constructed once and cached. Construction performs validation, so the first
    call is where invalid configuration surfaces. The cache holds a single
    immutable instance; it is an accessor, not mutable global state.
    """
    return Settings()
