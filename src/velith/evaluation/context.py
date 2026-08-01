"""Deterministic prompt/context assembly for a held-out attempt (M8-C4).

The single fixed procedure that assembles an attempt's prompt from a **fixed task
portion** (derived only from the held-out task) plus a **fixed, deterministic rendering
of the arm's retrieved episodes** into a memory-context portion (M8_SPEC §3.3).

The architectural guarantee, on which the whole measurement rests: the task portion,
the ordering, the delimiters, the framing text, and the assembly procedure are
**byte-identical across arms** — the **only** thing that may vary is the *content of the
retrieved memory* placed in the memory-context portion. It follows that:

* for A0, and for A1/A2 at an **empty checkpoint**, the retrieved memory is empty, the
  memory-context portion is empty, and the assembled prompt is **bit-for-bit identical**
  across all three arms — the cold-start control is exact, not approximate; and
* any two arms differ in the assembled prompt **only** where their retrieved memory
  differs (a suffix), never in the task portion.

The rendering is **domain-neutral** (D9/D22): a task's material and an episode's fields
are opaque text, rendered verbatim in a fixed format and **never parsed** as diff/test/
domain content — a non-software episode renders through the identical path. Standard
library plus the frozen M3 episode schema (read-only).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from velith.episodes.episode import Episode

#: Fixed framing and delimiters. These are part of the procedure and are identical for
#: every arm; only the *content* interpolated into them may differ.
_TASK_HEADER = "# Task\n"
_MEMORY_HEADER = "\n\n# Prior experience\n"
_EPISODE_SEPARATOR = "\n---\n"


def _render_episode(episode: Episode) -> str:
    """Render one retrieved episode as opaque, fixed-format text (no parsing)."""
    return (
        f"prompt: {episode.prompt}\n"
        f"patch: {episode.patch}\n"
        f"verdict: {episode.verdict_state.value}"
    )


def _render_memory(retrieved: Sequence[Episode]) -> str:
    """Render the retrieved episodes into the memory-context portion.

    Empty retrieved memory yields the **empty string**, so an empty checkpoint
    contributes nothing and the assembled prompt collapses to the task portion alone —
    identical across arms. Episodes are rendered in the order given (already deterministic
    from the frozen retriever) under a fixed header and separator.
    """
    if not retrieved:
        return ""
    blocks = _EPISODE_SEPARATOR.join(_render_episode(episode) for episode in retrieved)
    return _MEMORY_HEADER + blocks


@dataclass(frozen=True)
class AssembledContext:
    """The assembled attempt prompt, split into its two fixed portions.

    ``task_portion`` depends **only** on the held-out task; ``memory_portion`` depends
    **only** on the retrieved memory. ``prompt`` is their fixed concatenation — the input
    the frozen proposer consumes.
    """

    task_portion: str
    memory_portion: str

    @property
    def prompt(self) -> str:
        """The assembled attempt prompt: task portion followed by memory portion."""
        return self.task_portion + self.memory_portion


def assemble_context(task_material: str, retrieved: Sequence[Episode]) -> AssembledContext:
    """Assemble the attempt prompt from the held-out task and its retrieved memory.

    Deterministic and domain-neutral: the same ``task_material`` always yields the same
    task portion, and the same ``retrieved`` always yields the same memory portion.
    """
    task_portion = _TASK_HEADER + task_material
    memory_portion = _render_memory(retrieved)
    return AssembledContext(task_portion=task_portion, memory_portion=memory_portion)
