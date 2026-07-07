"""Domain-neutral batch layer for the cold baseline sweep (M5).

The batch layer runs the corpus through propose -> verify -> log at scale under the
cold baseline arm (A0), writing only through the frozen M4 guarded persistence
boundary (M5_SPEC §3, D8). It composes the frozen M0-M4 packages and modifies none.
"""

from __future__ import annotations
