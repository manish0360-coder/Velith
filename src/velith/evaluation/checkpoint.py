"""The evaluation checkpoint: a frozen capture of an arm's memory (M8-C2).

A checkpoint pins **what an arm knows** at the moment of evaluation, so that a held-out
evaluation is **reproducible** (the same checkpoint always yields the same memory) and
**comparable** (every arm and every re-run is scored against a fixed state, not a moving
one) — M8_SPEC §3.1.

It composes the frozen M7 arm memory view: for a memory-bearing arm (A1, A2) the memory
is that arm's snapshot over the accumulated experience; **A0's checkpoint is empty by
construction** — the memoryless baseline — so all three arms pass through the identical
checkpoint machinery.

**Checkpoint identity is order-independent and content-addressed.** It derives from the
*content* of the memory captured — the sorted multiset of admitted episode identities
(`content_hash`) — so it does **not** depend on the order in which experience was
accumulated, persisted, or presented (D8/D16.1/D18). The identity deliberately excludes
the arm: two checkpoints are the same **iff they hold the same episodes**, so an empty
checkpoint has one identity shared by every arm (the foundation of the empty-checkpoint
bit-for-bit prompt identity required in §3.3).

Forming a checkpoint is a **read** of frozen experience: it writes and mutates nothing
(the M7 arm memory view is read-only). Standard library plus the frozen M7 arm layer and
the M6 read-only memory source.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from velith.arms.binding import resolve_binding
from velith.arms.identity import Arm
from velith.arms.memory_view import ArmMemoryView
from velith.retrieval.memory import EpisodeMemory, MemorySnapshot

#: The empty memory snapshot shared by every empty checkpoint (A0 always).
_EMPTY_MEMORY: MemorySnapshot = MemorySnapshot(episodes=())


def _memory_identity(memory: MemorySnapshot) -> str:
    """Return the order-independent, content-addressed identity of a memory snapshot.

    Derived from the sorted multiset of episode ``content_hash`` values, so it depends
    only on *which* episodes the memory holds — never on their order. An empty memory
    yields a fixed constant identity, identical for every arm.
    """
    digest = hashlib.sha256()
    for content_hash in sorted(episode.content_hash for episode in memory.episodes):
        digest.update(content_hash.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


@dataclass(frozen=True)
class Checkpoint:
    """A frozen, content-addressed capture of an arm's memory at an evaluation point.

    Immutable: once formed, neither the memory nor the identity can shift, so every
    evaluation and re-run against this checkpoint sees the same state.
    """

    arm: Arm
    memory: MemorySnapshot
    identity: str

    def __len__(self) -> int:
        return len(self.memory)

    @property
    def is_empty(self) -> bool:
        """Return ``True`` iff this checkpoint holds no memory (A0 always)."""
        return len(self.memory) == 0


def form_checkpoint(arm: Arm, source: EpisodeMemory) -> Checkpoint:
    """Form the frozen checkpoint for ``arm`` over the experience in ``source``.

    A0 is memoryless, so its checkpoint is the empty memory regardless of ``source``;
    A1/A2 capture their write-filtered memory snapshot via the frozen arm memory view.
    Read-only: forming a checkpoint writes and mutates nothing.
    """
    if arm is Arm.A0:
        memory = _EMPTY_MEMORY
    else:
        memory = ArmMemoryView(resolve_binding(arm), source).snapshot()
    return Checkpoint(arm=arm, memory=memory, identity=_memory_identity(memory))
