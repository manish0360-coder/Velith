"""Fixtures for the G0 tests: a verifier that writes no diagnostic records unless asked."""

from __future__ import annotations

import pytest

from velith.geometry.verifier import GeometryVerifier


@pytest.fixture(scope="session")
def verifier() -> GeometryVerifier:
    return GeometryVerifier(diag_dir=None)
