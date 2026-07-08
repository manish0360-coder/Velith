"""The batch runner for the cold baseline arm A0 (M5-C5).

Sweeps the corpus's **available** partition through `propose -> verify -> log` at
scale (M5_SPEC §3.1/§3.2), composing the frozen collaborators by injection and
persisting each episode **only** through the frozen M4 guarded persistence boundary
so held-out experience can never leak (D8). Each episode is tagged with the cold
baseline arm (A0, D7); each task's seed is the deterministic per-task seed
(M5_SPEC §3.5); and the sweep is bounded by the injected cost guard.

This module composes the frozen M0-M4 packages and modifies none of them. The M1
single-task spike remains the frozen single-task reference; this is its batch
generalization. Standard library only.
"""

from __future__ import annotations

from typing import Protocol

from velith.agent.proposer import Proposal
from velith.batch.adapter import TaskAdapter
from velith.batch.budget import CostGuard
from velith.batch.provenance import RunProvenance, derive_task_seed
from velith.core.logging import get_logger
from velith.corpus.heldout import GuardedEpisodeWriter
from velith.corpus.loader import LoadedCorpus
from velith.corpus.manifest import Partition
from velith.episodes.episode import Episode, VerdictState
from velith.harness.verifier_sandbox import Verdict
from velith.task import Task

logger = get_logger(__name__)

#: The cold baseline arm identifier (D7): no memory read or written.
COLD_ARM = "A0"


class Proposer(Protocol):
    """Structural interface for the injected proposer (the frozen ``ProposerAgent``)."""

    def propose(self, task: Task, seed: int) -> Proposal:
        """Return a candidate proposal for ``task`` at ``seed``."""
        ...


class Verifier(Protocol):
    """Structural interface for the injected verifier (the frozen ``VerifierSandbox``)."""

    def verify(self, task: Task, patch: str) -> Verdict:
        """Dispose of ``patch`` against ``task`` and return the verdict."""
        ...


def run_batch(
    corpus: LoadedCorpus,
    provenance: RunProvenance,
    *,
    proposer: Proposer,
    verifier: Verifier,
    writer: GuardedEpisodeWriter,
    adapter: TaskAdapter,
    guard: CostGuard,
    velith_version: str,
) -> list[Episode]:
    """Sweep the available partition under the cold arm A0, returning the episodes.

    Draws only available tasks; persists each episode through the guarded boundary
    (which independently refuses held-out/unknown identities); tags the cold arm; and
    is bounded by the cost guard, which halts the sweep loudly when a limit is reached.
    """
    logger.info(
        "batch run started",
        extra={"event": "batch_run_started", **provenance.to_dict()},
    )
    episodes: list[Episode] = []
    for corpus_task in corpus.tasks:
        if corpus_task.partition is not Partition.AVAILABLE:
            continue  # A0 sweeps only the available partition; held-out is never attempted
        guard.start_task()
        seed = derive_task_seed(corpus_task.identity, provenance.batch_seed)
        task = adapter.materialize(corpus_task)
        guard.check_attempt(0)  # M5 runs one attempt per task (as M1); the limit bounds retries
        proposal = proposer.propose(task, seed)
        guard.charge_tokens(proposal.prompt_tokens + proposal.completion_tokens)

        if proposal.has_patch:
            verdict = verifier.verify(task, proposal.patch)
            state = verdict.state
            verdict_output = verdict.output
            verify_seconds = verdict.duration_seconds
            secondary_passed = verdict.secondary_passed
            flaky = verdict.flaky
        else:
            state = VerdictState.NO_PATCH
            verdict_output = ""
            verify_seconds = 0.0
            secondary_passed = None
            flaky = False

        episode = Episode.build(
            task_id=task.task_id,
            seed=seed,
            model=proposal.model,
            model_version=proposal.model_version,
            prompt=proposal.prompt,
            patch=proposal.patch,
            verdict_state=state,
            verdict_output=verdict_output,
            prompt_tokens=proposal.prompt_tokens,
            completion_tokens=proposal.completion_tokens,
            latency_seconds=proposal.latency_seconds,
            verify_seconds=verify_seconds,
            velith_version=velith_version,
            arm=provenance.arm,
            secondary_passed=secondary_passed,
            flaky=flaky,
        )
        writer.persist(corpus_task.identity, episode)
        episodes.append(episode)
    return episodes
