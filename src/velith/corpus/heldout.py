"""Held-out lock and guarded persistence boundary (M4-C4).

Two domain-neutral pieces enforce the D8 held-out discipline (M4_SPEC §3.3, §4):

* :class:`HeldOutLock` — the single authoritative exclusion predicate, keyed on
  **content-addressed task identity** (never a mutable display label), so relabeling
  a task cannot move it across the partition.
* :class:`GuardedEpisodeWriter` — the single guarded persistence boundary, the only
  experience-path writer into the frozen
  :class:`~velith.episodes.store.EpisodeStore`. It **raises loudly** rather than
  persist a held-out task's episode, **fails closed** on a task identity absent from
  the manifest, and delegates an available task's episode to the frozen store
  unchanged (composition, never modification).

Domain-neutral (D9/D22): identity is opaque content; nothing here inspects task
materials or the verification handle. It composes the frozen M3 store and the frozen
episode schema; it modifies neither.
"""

from __future__ import annotations

from pathlib import Path

from velith.corpus.manifest import CorpusManifest, Partition
from velith.episodes.episode import Episode
from velith.episodes.store import EpisodeStore


class HeldOutError(Exception):
    """Raised by the guarded boundary when persistence is not permitted.

    Two cases, both loud and never silent: the task is held-out (must never enter
    experience/memory, D8), or its identity is absent from the frozen manifest and
    therefore cannot be certified available (fail-closed, M4_SPEC §4).
    """


class HeldOutLock:
    """The authoritative held-out exclusion predicate (M4_SPEC §3.3).

    Keyed on content-addressed task identity. A pure query over the frozen manifest;
    it holds no state beyond it and never inspects task materials (D22).
    """

    def __init__(self, manifest: CorpusManifest) -> None:
        self._manifest = manifest

    def partition_of(self, identity: str) -> Partition | None:
        """The partition for a content-addressed identity, or ``None`` if unknown."""
        return self._manifest.partition_of(identity)

    def is_held_out(self, identity: str) -> bool:
        """True iff the identity is present and assigned to the held-out partition."""
        return self._manifest.partition_of(identity) is Partition.HELD_OUT

    def is_available(self, identity: str) -> bool:
        """True iff the identity is present and assigned to the available partition."""
        return self._manifest.partition_of(identity) is Partition.AVAILABLE


class GuardedEpisodeWriter:
    """The single guarded persistence boundary into the frozen episode store.

    The only experience-path writer into :class:`EpisodeStore`. It composes the store
    (never modifies it): an available task's episode is delegated unchanged; a
    held-out task's episode raises; an identity absent from the manifest raises
    (fail-closed). This is the single chokepoint (M4_SPEC §4, D8).
    """

    def __init__(self, lock: HeldOutLock, store: EpisodeStore) -> None:
        self._lock = lock
        self._store = store

    def persist(self, identity: str, episode: Episode) -> Path:
        """Persist ``episode`` for task ``identity`` iff that task is available.

        Delegates to the frozen store for an available task; raises
        :class:`HeldOutError` for a held-out task or for an identity absent from the
        manifest (fail-closed). Returns the store path on success.
        """
        partition = self._lock.partition_of(identity)
        if partition is None:
            raise HeldOutError(
                f"task identity {identity} is absent from the corpus manifest; "
                f"refusing to persist (fail-closed)"
            )
        if partition is Partition.HELD_OUT:
            raise HeldOutError(
                f"task identity {identity} is held-out; refusing to persist to experience"
            )
        return self._store.append(episode)
