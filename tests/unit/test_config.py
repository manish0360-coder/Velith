"""Unit tests for the validated :class:`Settings` object.

M3-C1 scope: the episode-index path setting (M3_SPEC §6.3). The setting carries a
safe default so the system loads with no ``.env`` present (M0 invariant), and is
overridable via the ``VELITH_EPISODE_INDEX_PATH`` environment variable. Broader
config load/validation behaviour is covered by the M0 sanity test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from velith.core.config import Settings, get_settings


def test_episode_index_path_defaults_under_data_episodes() -> None:
    """The index path defaults into the gitignored episode data directory."""
    get_settings.cache_clear()
    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()
    assert settings.episode_index_path == Path("data/episodes/episodes.db")


def test_episode_index_path_is_overridable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """``VELITH_EPISODE_INDEX_PATH`` overrides the default index location."""
    monkeypatch.setenv("VELITH_EPISODE_INDEX_PATH", "data/episodes/custom-index.db")
    get_settings.cache_clear()
    try:
        settings = Settings()
    finally:
        get_settings.cache_clear()
    assert settings.episode_index_path == Path("data/episodes/custom-index.db")
