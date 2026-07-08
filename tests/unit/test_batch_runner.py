"""Unit tests for the batch runner, cold arm A0 (M5-C5).

Hermetic: a stub proposer and a stub verifier (no model, no sandbox, no network).
Scope: available tasks are swept and persisted through the guarded boundary tagged
arm A0; held-out tasks are never persisted; the cost guard halts the sweep loudly;
and the deterministic per-task seed drives the proposal.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from velith.agent.proposer import Proposal
from velith.batch.adapter import FixtureTaskAdapter
from velith.batch.budget import CostBudgetError, CostGuard
from velith.batch.provenance import RunProvenance, derive_task_seed
from velith.batch.runner import COLD_ARM, run_batch
from velith.corpus.heldout import GuardedEpisodeWriter, HeldOutLock
from velith.corpus.loader import CorpusTask, LoadedCorpus
from velith.corpus.manifest import CorpusManifest, Partition, PartitionEntry
from velith.episodes.episode import VerdictState
from velith.episodes.store import EpisodeStore
from velith.harness.verifier_sandbox import Verdict
from velith.task import Task


class _StubProposer:
    def __init__(self, patch: str = "--- a/x\n+++ b/x\n") -> None:
        self._patch = patch
        self.seeds: list[int] = []

    def propose(self, task: Task, seed: int) -> Proposal:
        self.seeds.append(seed)
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


def _corpus() -> LoadedCorpus:
    entries = [
        PartitionEntry(label="avail-1", material="M-a1", partition=Partition.AVAILABLE),
        PartitionEntry(label="avail-2", material="M-a2", partition=Partition.AVAILABLE),
        PartitionEntry(label="held", material="M-h", partition=Partition.HELD_OUT),
    ]
    manifest = CorpusManifest.from_entries(entries)
    tasks = tuple(
        CorpusTask(label=e.label, material=e.material, handle="h", partition=e.partition)
        for e in entries
    )
    return LoadedCorpus(tasks=tasks, manifest=manifest)


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


def _writer(corpus: LoadedCorpus, tmp_path: Path) -> tuple[GuardedEpisodeWriter, EpisodeStore]:
    store = EpisodeStore(tmp_path / "e.jsonl", tmp_path / "e.db")
    return GuardedEpisodeWriter(HeldOutLock(corpus.manifest), store), store


def test_sweeps_available_and_persists_with_cold_arm(tmp_path: Path) -> None:
    corpus = _corpus()
    writer, store = _writer(corpus, tmp_path)
    episodes = run_batch(
        corpus,
        _provenance(corpus.manifest.manifest_hash),
        proposer=_StubProposer(),
        verifier=_StubVerifier(),
        writer=writer,
        adapter=FixtureTaskAdapter(),
        guard=CostGuard(0, 1, 0),
        velith_version="0.0.0",
    )
    assert len(episodes) == 2  # only the two available tasks
    assert all(episode.arm == COLD_ARM for episode in episodes)
    assert len(store.read_all()) == 2


def test_held_out_is_never_persisted(tmp_path: Path) -> None:
    corpus = _corpus()
    writer, store = _writer(corpus, tmp_path)
    run_batch(
        corpus,
        _provenance(corpus.manifest.manifest_hash),
        proposer=_StubProposer(),
        verifier=_StubVerifier(),
        writer=writer,
        adapter=FixtureTaskAdapter(),
        guard=CostGuard(0, 1, 0),
        velith_version="0.0.0",
    )
    # Three corpus tasks, one held-out -> exactly two persisted; the held-out never enters.
    assert len(store.read_all()) == 2


def test_cost_guard_halts_sweep_loudly(tmp_path: Path) -> None:
    corpus = _corpus()
    writer, store = _writer(corpus, tmp_path)
    with pytest.raises(CostBudgetError):
        run_batch(
            corpus,
            _provenance(corpus.manifest.manifest_hash, max_tasks=1),
            proposer=_StubProposer(),
            verifier=_StubVerifier(),
            writer=writer,
            adapter=FixtureTaskAdapter(),
            guard=CostGuard(max_tasks=1, max_attempts_per_task=1, max_tokens=0),
            velith_version="0.0.0",
        )
    # The first task was persisted before the budget tripped on the second.
    assert len(store.read_all()) == 1


def test_seed_is_the_deterministic_per_task_seed(tmp_path: Path) -> None:
    corpus = _corpus()
    writer, _ = _writer(corpus, tmp_path)
    proposer = _StubProposer()
    run_batch(
        corpus,
        _provenance(corpus.manifest.manifest_hash),
        proposer=proposer,
        verifier=_StubVerifier(),
        writer=writer,
        adapter=FixtureTaskAdapter(),
        guard=CostGuard(0, 1, 0),
        velith_version="0.0.0",
    )
    available = [task for task in corpus.tasks if task.partition is Partition.AVAILABLE]
    assert proposer.seeds == [derive_task_seed(task.identity, 0) for task in available]
