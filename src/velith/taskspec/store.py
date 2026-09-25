"""A schema-agnostic, content-addressed TaskSpec byte store (D28; M8 identity v2 §3.3).

A TaskSpec is addressed by its **digest**: the lowercase SHA-256 hex of its stored bytes,
carried in ``CorpusTask.handle`` (D28 Option D). This store only reads bytes by digest.
It deliberately knows **nothing** about a TaskSpec's schema: the TaskSpec schema is not
decided (D26), and none is needed to bind the verification contract into evaluation
identity. Whether stored bytes actually re-hash to their digest is checked by the
VerificationManifest builder for every store implementation
(:mod:`velith.evaluation.verification_manifest`), so the check cannot be bypassed by an
alternative store.

Populating the store (admitting TaskSpecs) is outside this module. Standard library only.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

#: A TaskSpec digest is a lowercase SHA-256 hex digest (64 chars).
_SHA256_HEX: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


class TaskSpecStoreError(Exception):
    """Raised when a store is asked for a malformed digest (loud, typed)."""


class FilesystemTaskSpecStore:
    """Read-only TaskSpec bytes stored as ``<root>/<digest>`` files."""

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        """The directory holding the content-addressed TaskSpec files."""
        return self._root

    def read(self, digest: str) -> bytes | None:
        """Return the bytes stored under ``digest``, or ``None`` if absent.

        A malformed digest is refused before any filesystem access, so a digest can never
        address a path outside the store root.
        """
        if not _SHA256_HEX.match(digest):
            raise TaskSpecStoreError(f"not a concrete SHA-256 hex TaskSpec digest: {digest!r}")
        path = self._root / digest
        if not path.is_file():
            return None
        return path.read_bytes()
