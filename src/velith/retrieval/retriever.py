"""Deterministic top-k retrieval over the read-only memory (M6-C5).

The single shared retriever (M6_SPEC §3.4/§3.5): given a query (M6-C2) and a read-only
memory snapshot (M6-C4), it embeds the query and each episode's opaque neutral
representation with the single shared embedder (M6-C3) and returns the top-k most similar
prior episodes. Ranking is a **pure function** of ``(query, snapshot, top_k)``; ties break
on ``content_hash`` so the order is total and content-addressed (D8/D16.1). It is
**read-only** — it embeds and ranks, writing nothing and mutating no episode, store, or
index. Exactly one retriever/embedder/top-k exists (no per-arm variation, D7). Standard
library plus the frozen M3 episode and the M6 retrieval seams.
"""

from __future__ import annotations

from velith.episodes.episode import Episode
from velith.retrieval.embedding import Embedder
from velith.retrieval.memory import MemorySnapshot
from velith.retrieval.query import Query


def _episode_text(episode: Episode) -> str:
    """The opaque neutral representation of an episode for embedding (M6_SPEC §3.3).

    The episode's prompt material, treated as opaque bytes-as-text — never parsed as any
    domain (D9/D22).
    """
    return episode.prompt


class Retriever:
    """The single shared, deterministic top-k retriever (M6_SPEC §3.4/§3.5).

    Read-only: it embeds and ranks prior episodes by similarity to a query and returns the
    top-k. It writes nothing and mutates no episode, snapshot, store, or index.
    """

    def __init__(self, embedder: Embedder, top_k: int) -> None:
        self._embedder = embedder
        self._top_k = top_k

    def retrieve(self, query: Query, memory: MemorySnapshot) -> tuple[Episode, ...]:
        """Return the top-k prior episodes most similar to ``query`` (read-only).

        Ranks by descending similarity, breaking ties on ``content_hash`` for a total,
        content-addressed order. A pure function of ``(query, memory, top_k)``.
        """
        query_vector = self._embedder.embed(query.representation())

        def sort_key(episode: Episode) -> tuple[int, str]:
            episode_vector = self._embedder.embed(_episode_text(episode))
            similarity = self._embedder.similarity(query_vector, episode_vector)
            return (-similarity, episode.content_hash)

        ranked = sorted(memory.episodes, key=sort_key)
        return tuple(ranked[: self._top_k])
