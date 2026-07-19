"""The arm memory view: what an arm's memory *is* (M7-C5).

A read-only, deterministic projection applying the **fixed and total** projection
order of M7_SPEC §3.3::

    Episode Store  ->  Arm Filter  ->  Memory Snapshot  ->  Shared Retriever

Each stage is entered exactly once, in this order, with no stage skipped, reordered,
merged, or re-entered:

1. **Episode Store** — the frozen authoritative record, read through its verified
   read surface (the frozen M6 :class:`EpisodeMemory`, which composes
   ``EpisodeStore.read_all``) and scoped to the arm by the frozen ``arm`` provenance.
   This is the **only** source of experience: this view takes no other input, so no
   episode can enter downstream of it.
2. **Arm Filter** — the arm's bound write-filter (M7-C3) is applied. This is the
   **only** stage at which admission is decided, and therefore the **only** stage at
   which the arms differ.
3. **Memory Snapshot** — the admitted episodes are fixed as an immutable
   :class:`MemorySnapshot`, never mutated, appended to, re-ordered, or re-filtered.

Stage 4 is deliberately *not* implemented here. The snapshot is handed to the
**unchanged** shared M6 retriever; this module neither substitutes, re-configures,
wraps, nor parameterises it, because arm-dependent selection at or after retrieval
would make retrieval itself arm-dependent and void D7 (M7_SPEC §3.4).

**Read-only.** Nothing here writes, appends to, deletes from, mutates, or re-orders
the episode log, the derived index, or any episode. Filtering is *admission into an
arm's memory*, never deletion of a grounding record: every grounded outcome remains
in the authoritative log exactly as the frozen store wrote it (D2/D3/D16.7).

**Deterministic.** Identical persisted episodes plus an identical arm always produce
an identical snapshot — the same admitted episodes in the same order — independent of
interpreter hash seeding and of the order in which experience was presented or
persisted. Admitted episodes are therefore placed in a canonical **content-addressed**
order rather than inheriting log order, which would otherwise leak persistence order
into the snapshot (M7_SPEC §6.6; D8/D16.1/D18).

**Held-out safety is inherited, not re-derived.** The view reads only experience
already persisted through the frozen M4/M5 guarded boundary, so it is held-out-free by
construction (D8); it adds no path that could reintroduce held-out experience.

Standard library plus the frozen M6 memory source and the M7 binding.
"""

from __future__ import annotations

from velith.arms.binding import ArmBinding
from velith.episodes.episode import Episode
from velith.retrieval.memory import EpisodeMemory, MemorySnapshot


def _canonical_order(episode: Episode) -> tuple[str, str]:
    """Return the content-addressed sort key giving a total, stable order.

    ``content_hash`` is the episode's identity (D16.1/D21). Two episodes may share it
    while differing in provenance excluded from the hash boundary (timestamp, timings,
    ``flaky``), so the full canonical record breaks that tie — the key is total, and
    the resulting order depends only on episode content, never on persistence order.
    """
    return (episode.content_hash, episode.model_dump_json())


class ArmMemoryView:
    """An arm's memory: the store, scoped to the arm and filtered by its policy.

    Read-only and deterministic. Construction fixes the run's retention policy (the
    resolved, immutable :class:`ArmBinding`) and the memory source; nothing else can
    influence what the snapshot contains.
    """

    def __init__(self, binding: ArmBinding, source: EpisodeMemory) -> None:
        self._binding = binding
        self._source = source

    @property
    def binding(self) -> ArmBinding:
        """The run's resolved arm and write-filter, fixed for its lifetime."""
        return self._binding

    def snapshot(self) -> MemorySnapshot:
        """Project the store through this arm's filter into an immutable snapshot.

        Applies stages 1-3 of the fixed projection order, exactly once each and in
        order. Writes nothing.
        """
        # Stage 1 - Episode Store: the only source of experience, scoped to the arm.
        stored = self._source.snapshot().episodes
        scoped = [episode for episode in stored if episode.arm == self._binding.arm.value]

        # Stage 2 - Arm Filter: the only stage deciding admission, and the only stage
        # at which the arms differ.
        admitted = [episode for episode in scoped if self._binding.write_filter.admits(episode)]

        # Stage 3 - Memory Snapshot: fixed, immutable, canonically ordered.
        return MemorySnapshot(episodes=tuple(sorted(admitted, key=_canonical_order)))
