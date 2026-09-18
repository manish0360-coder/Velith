"""M9 analysis layer (Velith): pre-registration (P1) and, later, the executor (P2).

This package declares the frozen M9 analysis plan and records the pre-registration
artifact. It depends only on frozen lower layers read-only (`arms`, `episodes` hashing);
it never imports the evaluation sink/records or the episode store, and it reads no
held-out outcome (M9_SPEC §3.4). M9-C2 implements P1 only.
"""
