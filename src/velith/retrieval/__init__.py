"""Domain-neutral, read-only retrieval substrate (M6).

The retrieval layer fetches the top-k most relevant prior episodes from the accumulated
experience, deterministically and read-only, composing the frozen M3 store and modifying
nothing (M6_SPEC §3). Materials, queries, and the optional retrieval context are treated
as opaque, content-addressed data — never parsed as software (D9/D22).
"""

from __future__ import annotations
