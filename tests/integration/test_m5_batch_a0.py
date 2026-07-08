"""Hermetic acceptance for the M5 batch runner, cold arm A0 (M5-C6).

End-to-end through the wired M5 components — corpus loader/manifest, held-out lock,
guarded persistence boundary, task-materialization adapter, cost guard, run
provenance, and the batch runner — over the frozen episode store, with a stub
proposer and a stub verifier (no model, no sandbox, no network). Pins the M5
Definition of Done (M5_SPEC §6): available-only persistence through the frozen store
tagged arm A0; held-out never persisted; A0 cold and deterministically reproducible;
the cost guard halting loudly; run provenance recording the full experiment identity
(including the cost-guard budget/limits); and a non-software corpus sweeping through
the identical path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from velith.agent.proposer import Proposal
from velith.batch.adapter import FixtureTaskAdapter
from velith.batch.budget import CostBudgetError, CostGuard
from velith.batch.provenance import RunProvenance
from velith.batch.runner import COLD_ARM, run_batch
from velith.corpus.heldout import GuardedEpisodeWriter, HeldOutLock
from velith.corpus.loader import CorpusTask, LoadedCorpus, load_corpus
from velith.corpus.manifest import CorpusManifest, Partition, PartitionEntry
from velith.episodes.episode import Episode, VerdictState
from velith.episodes.store import EpisodeStore
from velith.harness.verifier_sandbox import Verdict
from velith.task import Task

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "corpus_min"


class _StubProposer:
    def __init__(self, patch: str = "--- a/x\n+++ b/x\n") -> None:
        self._patch = patch

    def propose(self, task: Task, seed: int) -> Proposal:
        return Proposal(
            patch=self._patch,
            prompt=task.prompt,
            prompt_tokens=5,
            completion_tokens=7,
            latency_seconds=0.1,
            model="stub-model",
            model_version="stub-1",
        )


class _StubVerifier:
    def verify(self, task: Task, patch: str) -> Verdict:
        return Verdict(
            state=VerdictState.PASSED,
            output="1 passed",
            secondary_passed=True,
            flaky=False,
            duration_seconds=0.2,
        )


def _provenance(manifest_hash: str, *, max_tasks: int = 0, max_tokens: int = 0) -> RunProvenance:
    return RunProvenance(
        corpus_manifest_hash=manifest_hash,
        arm=COLD_ARM,
        base_model="stub-model",
        batch_seed=0,
        max_tasks=max_tasks,
        max_attempts_per_task=1,
        max_tokens=max_tokens,
    )


def _writer(corpus: LoadedCorpus, root: Path) -> tuple[GuardedEpisodeWriter, EpisodeStore]:
    store = EpisodeStore(root / "e.jsonl", root / "e.db")
    return GuardedEpisodeWriter(HeldOutLock(corpus.manifest), store), store


def _run(
    corpus: LoadedCorpus,
    writer: GuardedEpisodeWriter,
    *,
    guard: CostGuard | None = None,
    provenance: RunProvenance | None = None,
) -> list[Episode]:
    return run_batch(
        corpus,
        provenance or _provenance(corpus.manifest.manifest_hash),
        proposer=_StubProposer(),
        verifier=_StubVerifier(),
        writer=writer,
        adapter=FixtureTaskAdapter(),
        guard=guard or CostGuard(0, 1, 0),
        velith_version="0.0.0",
    )


def test_batch_a0_sweeps_available_and_persists_through_store(tmp_path: Path) -> None:
    corpus = load_corpus(_FIXTURE, _FIXTURE / "partition.json")
    writer, store = _writer(corpus, tmp_path)

    episodes = _run(corpus, writer)

    available = [task for task in corpus.tasks if task.partition is Partition.AVAILABLE]
    assert len(episodes) == len(available) == 2
    assert all(episode.arm == COLD_ARM for episode in episodes)
    assert len(store.read_all()) == 2  # held-out never persisted


def test_batch_a0_is_cold_and_reproducible_across_runs(tmp_path: Path) -> None:
    corpus = load_corpus(_FIXTURE, _FIXTURE / "partition.json")
    writer_a, _ = _writer(corpus, tmp_path / "a")
    writer_b, _ = _writer(corpus, tmp_path / "b")

    episodes_a = _run(corpus, writer_a)
    episodes_b = _run(corpus, writer_b)

    # A0 is cold and deterministically seeded: identical content hashes across runs,
    # regardless of order or repetition (D8/D16.1).
    hashes_a = sorted(episode.content_hash for episode in episodes_a)
    hashes_b = sorted(episode.content_hash for episode in episodes_b)
    assert hashes_a == hashes_b


def test_cost_guard_halts_sweep_loudly(tmp_path: Path) -> None:
    corpus = load_corpus(_FIXTURE, _FIXTURE / "partition.json")
    writer, store = _writer(corpus, tmp_path)

    with pytest.raises(CostBudgetError):
        _run(
            corpus,
            writer,
            guard=CostGuard(max_tasks=1, max_attempts_per_task=1, max_tokens=0),
            provenance=_provenance(corpus.manifest.manifest_hash, max_tasks=1),
        )
    assert len(store.read_all()) == 1  # the first task persisted before the budget tripped


def test_run_provenance_records_full_experiment_identity() -> None:
    corpus = load_corpus(_FIXTURE, _FIXTURE / "partition.json")
    recorded = _provenance(corpus.manifest.manifest_hash, max_tasks=10, max_tokens=1000).to_dict()
    assert recorded["corpus_manifest_hash"] == corpus.manifest.manifest_hash
    assert recorded["arm"] == COLD_ARM
    assert recorded["base_model"] == "stub-model"
    assert recorded["batch_seed"] == 0
    assert recorded["max_tasks"] == 10
    assert recorded["max_attempts_per_task"] == 1
    assert recorded["max_tokens"] == 1000


def test_non_software_corpus_sweeps_through_the_identical_path(tmp_path: Path) -> None:
    entries = [
        PartitionEntry(label="melody", material="melody:CEG", partition=Partition.AVAILABLE),
        PartitionEntry(label="recipe", material="dish:soup", partition=Partition.HELD_OUT),
    ]
    manifest = CorpusManifest.from_entries(entries)
    tasks = tuple(
        CorpusTask(label=e.label, material=e.material, handle="h", partition=e.partition)
        for e in entries
    )
    corpus = LoadedCorpus(tasks=tasks, manifest=manifest)
    writer, store = _writer(corpus, tmp_path)

    episodes = _run(corpus, writer)

    assert len(episodes) == 1  # only the available (melody); held-out (recipe) excluded
    assert episodes[0].arm == COLD_ARM
    assert len(store.read_all()) == 1
