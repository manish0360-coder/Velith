"""Deterministic per-task seeding and batch/run provenance (M5-C2).

Two domain-neutral pieces for the batch sweep (M5_SPEC §3.5):

* :func:`derive_task_seed` — each task's seed is a **deterministic function of its
  content-addressed identity (M4_SPEC §3.3) and the run's batch seed**, so a task's
  seed is identical across experimental arms regardless of execution order or retries
  (D8).
* :class:`RunProvenance` — the **experiment identity** of one sweep: the frozen corpus
  manifest hash, the arm, the base-model identity, the batch seed, and the cost-guard
  budget/limits.

This module composes M4's content-addressed identity and adds no field to the episode
identity (D21/D22 boundaries hold). Standard library only.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

# Keep derived seeds non-negative and within signed 64-bit, matching the episode's
# integer seed field and the SQLite index column.
_SEED_MASK = (1 << 63) - 1


def derive_task_seed(task_identity: str, batch_seed: int) -> int:
    """Return the deterministic per-task seed for ``(task_identity, batch_seed)``.

    A pure function of the content-addressed task identity (M4_SPEC §3.3) and the
    run's batch seed, so the seed is identical across arms regardless of execution
    order or retries (M5_SPEC §3.5, D8). Non-negative and within signed 64-bit.
    """
    key = f"{task_identity}:{batch_seed}"
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & _SEED_MASK


@dataclass(frozen=True)
class RunProvenance:
    """The experiment identity of one batch sweep (M5_SPEC §3.5).

    Records the frozen corpus split (its manifest hash), the arm, the base-model
    identity, the batch seed, and the cost-guard budget/limits. A standalone record;
    it adds no field to the episode identity (D21/D22).
    """

    corpus_manifest_hash: str
    arm: str
    base_model: str
    batch_seed: int
    max_tasks: int
    max_attempts_per_task: int
    max_tokens: int

    def to_dict(self) -> dict[str, str | int]:
        """A JSON-serializable view of the full experiment identity."""
        return {
            "corpus_manifest_hash": self.corpus_manifest_hash,
            "arm": self.arm,
            "base_model": self.base_model,
            "batch_seed": self.batch_seed,
            "max_tasks": self.max_tasks,
            "max_attempts_per_task": self.max_attempts_per_task,
            "max_tokens": self.max_tokens,
        }
