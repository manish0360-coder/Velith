"""Unit tests for the deterministic top-k retriever (M6-C5).

Scope: identical ``(query, memory snapshot, top_k)`` yields the identical ordered result;
ranking is by similarity; ties break deterministically on ``content_hash``; the retriever
is read-only (no mutation, no fabrication); top-k bounds the result; and exactly one
shared retriever/embedder/top-k exists — no per-arm variation (M6_SPEC §3.4/§3.5).
"""

from __future__ import annotations

from velith.episodes.episode import Episode, VerdictState
from velith.retrieval.embedding import HashedNgramEmbedder
from velith.retrieval.memory import MemorySnapshot
from velith.retrieval.query import derive_query
from velith.retrieval.retriever import Retriever


def _episode(prompt: str, seed: int, patch: str = "--- a/x\n+++ b/x\n") -> Episode:
    return Episode.build(
        task_id="t",
        seed=seed,
        model="m",
        model_version="v",
        prompt=prompt,
        patch=patch,
        verdict_state=VerdictState.PASSED,
        verdict_output="1 passed",
        prompt_tokens=1,
        completion_tokens=2,
        latency_seconds=1.0,
        verify_seconds=2.0,
        velith_version="0.0.0",
        secondary_passed=True,
        flaky=False,
        timestamp="2026-07-06T00:00:00+00:00",
    )


def _memory(episodes: list[Episode]) -> MemorySnapshot:
    return MemorySnapshot(episodes=tuple(episodes))


def _retriever(top_k: int) -> Retriever:
    return Retriever(HashedNgramEmbedder(), top_k)


def test_retrieval_is_deterministic() -> None:
    memory = _memory([_episode("alpha task", 1), _episode("beta task", 2), _episode("gamma", 3)])
    query = derive_query("alpha task")
    first = _retriever(2).retrieve(query, memory)
    second = _retriever(2).retrieve(query, memory)
    assert [e.content_hash for e in first] == [e.content_hash for e in second]


def test_ranks_the_matching_episode_first() -> None:
    match = _episode("aaa aaa", 1)
    other = _episode("zzz zzz", 2)
    memory = _memory([other, match])  # deliberately out of order
    result = _retriever(2).retrieve(derive_query("aaa aaa"), memory)
    assert result[0].content_hash == match.content_hash


def test_ties_break_on_content_hash() -> None:
    # Same prompt -> equal similarity to any query -> ties broken by content_hash.
    a = _episode("same", 1, patch="diff a")
    b = _episode("same", 2, patch="diff b")
    memory = _memory([a, b])
    result = _retriever(2).retrieve(derive_query("anything"), memory)
    expected = sorted([a, b], key=lambda e: e.content_hash)
    assert [e.content_hash for e in result] == [e.content_hash for e in expected]


def test_top_k_bounds_the_result() -> None:
    memory = _memory([_episode("a", 1), _episode("b", 2), _episode("c", 3)])
    assert len(_retriever(2).retrieve(derive_query("a"), memory)) == 2
    # A top_k larger than the memory returns all episodes.
    assert len(_retriever(10).retrieve(derive_query("a"), memory)) == 3


def test_retriever_is_read_only() -> None:
    episodes = [_episode("alpha", 1), _episode("beta", 2)]
    memory = _memory(episodes)
    before = memory.episodes
    result = _retriever(2).retrieve(derive_query("alpha"), memory)
    assert memory.episodes == before  # snapshot unchanged (read-only)
    # The result is a subset of the snapshot — nothing fabricated.
    assert {e.content_hash for e in result} <= {e.content_hash for e in episodes}


def test_single_shared_retriever_no_per_arm_variation() -> None:
    memory = _memory([_episode("alpha", 1), _episode("beta", 2)])
    query = derive_query("alpha")
    first = Retriever(HashedNgramEmbedder(), 2).retrieve(query, memory)
    second = Retriever(HashedNgramEmbedder(), 2).retrieve(query, memory)
    assert [e.content_hash for e in first] == [e.content_hash for e in second]
