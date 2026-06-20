"""Shared pytest fixtures for Velith (minimal in M0).

The fixture surface is intentionally tiny here. Mocking discipline begins at M1
when the LLM enters; M0 calls nothing external.
"""

from __future__ import annotations

import pytest

from velith.core.config import Settings, get_settings


@pytest.fixture
def settings() -> Settings:
    """Return freshly-loaded, validated settings.

    The cache is cleared so the object reflects the current environment rather
    than a value cached by an earlier test.
    """
    get_settings.cache_clear()
    return get_settings()
