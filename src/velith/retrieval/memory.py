"""Read-only memory source over the frozen episode store (M6-C4).

The retriever's memory is the experience already persisted through the frozen M5 guarded
boundary — the M3 episode log, read **only** (M6_SPEC §3.1). This source composes the
frozen read surface (:meth:`EpisodeStore.read_all`) and **mutates nothing**: it never
writes, re-orders, or modifies the store, the index, or any episode, and it exposes no
write path. Because held-out experience was never persisted (M4/M5, D8), the memory is
held-out-free by construction, and this source adds no path that could reintroduce it.
Standard library plus the frozen M3 store.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from velith.episodes.episode import Episode
from velith.episodes.store import EpisodeStore


@dataclass(frozen=True)
class MemorySnapshot:
    """An immutable, read-only view of the prior episodes available for retrieval.

    Captured at read time; the tuple is stable and never mutated. It surfaces exactly the
    episodes persisted through the frozen guarded boundary — nothing fabricated, and (by
    the M4/M5 write guarantee) no held-out episode.
    """

    episodes: tuple[Episode, ...]

    def __len__(self) -> int:
        return len(self.episodes)


class EpisodeMemory:
    """A read-only projection over the frozen episode store (M6_SPEC §3.1).

    Composes :meth:`EpisodeStore.read_all` to serve an immutable :class:`MemorySnapshot`.
    It exposes no write path and never mutates the store, the index, or any episode.
    """

    def __init__(self, memory_path: Path) -> None:
        self._memory_path = memory_path

    def snapshot(self) -> MemorySnapshot:
        """Return an immutable snapshot of the prior episodes (read-only).

        Reads via the frozen store's verified read surface (each episode's content hash is
        re-verified on read, the M1 invariant). Writes nothing; a missing log yields an
        empty snapshot.
        """
        episodes = EpisodeStore(self._memory_path).read_all()
        return MemorySnapshot(episodes=tuple(episodes))
