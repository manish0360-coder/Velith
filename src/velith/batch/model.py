"""Single fixed base-model selection seam for a batch sweep (M5-C3).

The single owner of model selection for the batch: it binds exactly one fixed,
non-saturating base model (D8 §1, M5_SPEC §3.4). The selected model is used with the
frozen LLM client downstream (which the seam composes, never modifies). Multi-model
routing/selection policy is out of scope (M5_SPEC §8). Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FixedBaseModel:
    """The one fixed base model bound for a batch sweep (M5_SPEC §3.4)."""

    model: str

    def select(self) -> str:
        """Return the single fixed base-model identity for this sweep."""
        return self.model
