"""Unit tests for the validated :class:`Settings` object.

Covers the milestone-added settings: the M3 episode-index path (M3_SPEC §6.3) and
the M4 corpus/partition locators (M4_SPEC §5). Each carries a safe default so the
system loads with no ``.env`` present (M0 invariant) and is overridable via its
``VELITH_*`` environment variable. Broader config load/validation behaviour is
covered by the M0 sanity test.
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


def test_corpus_settings_default_under_data_corpus() -> None:
    """The M4 corpus locators default under the `data/corpus` tree (M4_SPEC §5)."""
    get_settings.cache_clear()
    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()
    assert settings.corpus_path == Path("data/corpus")
    assert settings.corpus_manifest_path == Path("data/corpus/manifest.json")
    assert settings.corpus_partition_spec_path == Path("data/corpus/partition.json")


def test_corpus_settings_are_overridable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each M4 corpus locator is overridable via its ``VELITH_*`` variable."""
    monkeypatch.setenv("VELITH_CORPUS_PATH", "data/other-corpus")
    monkeypatch.setenv("VELITH_CORPUS_MANIFEST_PATH", "data/other-corpus/m.json")
    monkeypatch.setenv("VELITH_CORPUS_PARTITION_SPEC_PATH", "data/other-corpus/p.json")
    get_settings.cache_clear()
    try:
        settings = Settings()
    finally:
        get_settings.cache_clear()
    assert settings.corpus_path == Path("data/other-corpus")
    assert settings.corpus_manifest_path == Path("data/other-corpus/m.json")
    assert settings.corpus_partition_spec_path == Path("data/other-corpus/p.json")
