"""Parent/worker protocol constants (spec F r3 §6), shared by ``_kernel`` and ``verifier``."""

from __future__ import annotations

from typing import Final

#: Tag of the one JSON document the worker writes.
PROTOCOL_TAG: Final[str] = "g0-child-1"
#: Reserved exit code: emitted only by the worker bootstrap's top-level ``MemoryError`` handler.
#: CPython itself uses 1 (uncaught exception), 2 (usage) and 120 (flush failure at exit).
EXIT_MEMORY: Final[int] = 3
#: Worker module run as ``python -I -m velith.geometry._kernel``.
WORKER_MODULE: Final[str] = "velith.geometry._kernel"
