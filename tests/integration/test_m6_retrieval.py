"""Hermetic acceptance for the M6 shared retrieval substrate (M6-C6).

End-to-end through the wired M6 seams — query derivation, the single deterministic
embedder, the read-only memory source, and the top-k retriever — over the frozen M3
episode store, with no model and no network (in-process deterministic embedding). Pins
the M6 Definition of Done (M6_SPEC §6): deterministic top-k retrieval that is read-only
and content-addressed (1, 2); a single shared deterministic embedder/retriever/top-k
(3, 4); a material-only query and a query with an optional opaque context both behave
deterministically; a non-software memory retrieves through the identical path (6); the
memory holds no held-out episode (7); and the A0 runner is neither depended upon nor
modified (5).
"""

from __future__ import annotations

from pathlib import Path

import pytest

import velith.retrieval
from velith.corpus.heldout import GuardedEpisodeWriter, HeldOutError, HeldOutLock
from velith.corpus.manifest import CorpusManifest, Partition, PartitionEntry, task_identity
from velith.episodes.episode import Episode, VerdictState
from velith.episodes.store import EpisodeStore
from velith.retrieval.embedding import EMBEDDER_NAME, get_embedder
from velith.retrieval.memory import EpisodeMemory
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


def _populate(path: Path, episodes: list[Episode]) -> None:
    store = EpisodeStore(path)
    for episode in episodes:
        store.append(episode)


def test_end_to_end_deterministic_retrieval_is_read_only(tmp_path: Path) -> None:
    path = tmp_path / "episodes.jsonl"
    _populate(path, [_episode("alpha task", 1), _episode("beta task", 2), _episode("gamma", 3)])
    before = path.read_bytes()

    memory = EpisodeMemory(path).snapshot()
    retriever = Retriever(get_embedder(EMBEDDER_NAME), 2)
    first = retriever.retrieve(derive_query("alpha task"), memory)
    second = retriever.retrieve(derive_query("alpha task"), memory)

    assert [e.content_hash for e in first] == [e.content_hash for e in second]
    assert len(first) == 2
    assert path.read_bytes() == before  # end-to-end read-only: the log is unchanged


def test_material_only_and_contextual_queries_are_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "episodes.jsonl"
    _populate(path, [_episode("alpha", 1), _episode("beta", 2)])
    memory = EpisodeMemory(path).snapshot()
    retriever = Retriever(get_embedder(EMBEDDER_NAME), 2)

    material_a = retriever.retrieve(derive_query("alpha"), memory)
    material_b = retriever.retrieve(derive_query("alpha"), memory)
    assert [e.content_hash for e in material_a] == [e.content_hash for e in material_b]

    context_a = retriever.retrieve(derive_query("alpha", "prior:PASSED"), memory)
    context_b = retriever.retrieve(derive_query("alpha", "prior:PASSED"), memory)
    assert [e.content_hash for e in context_a] == [e.content_hash for e in context_b]


def test_non_software_memory_retrieves_through_the_identical_path(tmp_path: Path) -> None:
    path = tmp_path / "episodes.jsonl"
    _populate(path, [_episode("melody:C-E-G;bpm=120", 1), _episode("dish:soup;salt=2g", 2)])
    memory = EpisodeMemory(path).snapshot()

    result = Retriever(get_embedder(EMBEDDER_NAME), 2).retrieve(
        derive_query("melody:C-E-G;bpm=120"), memory
    )
    assert len(result) == 2
    assert {e.content_hash for e in result} <= {e.content_hash for e in memory.episodes}


def test_memory_holds_no_held_out_episode(tmp_path: Path) -> None:
    # Persist an available episode through the frozen guarded boundary; a held-out task is
    # refused and never persisted, so the memory retrieval reads is held-out-free (D8).
    manifest = CorpusManifest.from_entries(
        [
            PartitionEntry(label="avail", material="M-avail", partition=Partition.AVAILABLE),
            PartitionEntry(label="held", material="M-held", partition=Partition.HELD_OUT),
        ]
    )
    path = tmp_path / "episodes.jsonl"
    store = EpisodeStore(path, tmp_path / "episodes.db")
    writer = GuardedEpisodeWriter(HeldOutLock(manifest), store)

    available = _episode("alpha", 1)
    writer.persist(task_identity("M-avail"), available)
    with pytest.raises(HeldOutError):
        writer.persist(task_identity("M-held"), _episode("beta", 2))

    memory = EpisodeMemory(path).snapshot()
    assert [e.content_hash for e in memory.episodes] == [available.content_hash]
    result = Retriever(get_embedder(EMBEDDER_NAME), 5).retrieve(derive_query("alpha"), memory)
    assert {e.content_hash for e in result} == {available.content_hash}


def test_retrieval_does_not_depend_on_the_a0_runner() -> None:
    # The retrieval substrate never references the batch/A0 runner (M6_SPEC §3.5/§8).
    assert velith.retrieval.__file__ is not None
    retrieval_dir = Path(velith.retrieval.__file__).parent
    for source in retrieval_dir.glob("*.py"):
        assert "velith.batch" not in source.read_text(encoding="utf-8")
