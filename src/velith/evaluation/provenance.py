"""The content-addressed evaluation identity (M8-C7).

:class:`EvaluationProvenance` is the **identity of one held-out evaluation** (M8_SPEC
§3.5): the checkpoint identity (§3.1), the held-out manifest hash (§3.2), the arm, the
base model, the evaluation seed, and the cost-guard limits. It carries a
**content-addressed** ``identity`` over exactly those components, so:

* the **same** evaluation always yields the **same** identity, and any change to **any**
  component yields a **new** identity; and
* results are only ever comparable **within the same checkpoint and split** — a
  different checkpoint identity or a different manifest hash is a different evaluation.

It is a standalone identity record; it adds no field to the episode identity (D21/D22)
and computes **no statistic and no decision** (D22). The hashing mirrors the frozen
episode's canonical serialization (sorted keys, tight separators, UTF-8, SHA-256) so the
identity is stable across processes and machines (D16.1/D18). Standard library only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationProvenance:
    """The experiment identity of one held-out evaluation (M8_SPEC §3.5).

    Immutable. ``identity`` is a pure, content-addressed function of the components
    below; two provenances are the same evaluation iff every component matches.
    """

    checkpoint_identity: str
    manifest_hash: str
    arm: str
    base_model: str
    eval_seed: int
    max_tasks: int
    max_attempts_per_task: int
    max_tokens: int

    def to_dict(self) -> dict[str, str | int]:
        """A JSON-serializable view of the full evaluation identity's components."""
        return {
            "checkpoint_identity": self.checkpoint_identity,
            "manifest_hash": self.manifest_hash,
            "arm": self.arm,
            "base_model": self.base_model,
            "eval_seed": self.eval_seed,
            "max_tasks": self.max_tasks,
            "max_attempts_per_task": self.max_attempts_per_task,
            "max_tokens": self.max_tokens,
        }

    @property
    def identity(self) -> str:
        """The content-addressed identity: SHA-256 over the canonical components.

        Canonical serialization (sorted keys, tight separators, UTF-8) so the identity
        depends only on the component *values*, never on field order or formatting.
        """
        canonical = json.dumps(
            self.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
