"""Domain-neutral task-corpus components (M4).

The corpus layer lifts the loop from one fixture task to a corpus under a
mechanically-enforced held-out partition (M4_SPEC §3, D8). It is domain-neutral
(D9, D22): task materials and the verification handle are opaque, never inspected
or interpreted here. These components compose the frozen M0-M3 substrate and modify
none of it.
"""

from __future__ import annotations
