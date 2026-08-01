"""The memory-conditioned held-out attempt (M8-C5).

The single evaluation attempt path, **identical for all three arms** (M8_SPEC §3.3).
Against a held-out task it produces one grounded outcome through the frozen
``propose -> verify`` loop (M1/M2):

* **A0** attempts memorylessly — its checkpoint memory is empty, retrieval returns
  nothing, and the assembled prompt is the task portion alone (the frozen cold path).
* **A1 / A2** condition the proposal on their retrieved memory at the checkpoint — the
  frozen M6 retriever over the arm's memory snapshot supplies the relevant prior
  episodes, which the fixed assembly (M8-C4) renders into read-only attempt context.

The arm's memory is the **only** difference between the three runs: the proposer, the
verifier, the held-out task, the per-task seed, and the assembly procedure are identical.
Conditioning is **the caller assembling context** — the assembled prompt becomes the
proposer's input via an immutable copy of the frozen :class:`Task`; the frozen proposer
and verifier interfaces are **used as-is and modified in no way**.

Retrieval is **stateless / no-cache**: the injected retriever is a pure function of
``(query, snapshot)`` and the attempt holds no state across tasks or arms, so no attempt
can influence another. The per-task seed is derived deterministically from the held-out
task identity and the evaluation seed (reusing the frozen M5 ``derive_task_seed``), so the
attempt is reproducible to the determinism level the grounding signal already meets (D18).

The outcome recorded here is the **deterministic verifier verdict** (with the held-out
secondary), never a model score (D3/D11); it is wrapped into a segregated evaluation
record by M8-C6 and never becomes experience (D8). Standard library plus the frozen
M1/M2/M4/M5/M6 seams and the M8 checkpoint and context assembly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from velith.agent.proposer import Proposal
from velith.arms.identity import Arm
from velith.batch.adapter import TaskAdapter
from velith.batch.provenance import derive_task_seed
from velith.corpus.loader import CorpusTask
from velith.episodes.episode import VerdictState
from velith.evaluation.checkpoint import Checkpoint
from velith.evaluation.context import assemble_context
from velith.harness.verifier_sandbox import Verdict
from velith.retrieval.query import derive_query
from velith.retrieval.retriever import Retriever
from velith.task import Task


class Proposer(Protocol):
    """Structural interface for the injected proposer (the frozen ``ProposerAgent``).

    Declared here so the evaluation layer depends on the proposer's *shape*, not on the
    frozen A0 batch runner (M8_SPEC §8: A0 is neither depended upon nor modified).
    """

    def propose(self, task: Task, seed: int) -> Proposal:
        """Return a candidate proposal for ``task`` at ``seed``."""
        ...


class Verifier(Protocol):
    """Structural interface for the injected verifier (the frozen ``VerifierSandbox``)."""

    def verify(self, task: Task, patch: str) -> Verdict:
        """Dispose of ``patch`` against ``task`` and return the grounded verdict."""
        ...


@dataclass(frozen=True)
class AttemptOutcome:
    """The grounded outcome of one memory-conditioned held-out attempt.

    Carries the deterministic verifier verdict and the held-out secondary signal, the
    deterministic token counts, and the identity fields that bind the outcome to a
    (arm, held-out task, seed). It is **not** an episode and is never persisted as
    experience; M8-C6 wraps it into a segregated evaluation record.
    """

    arm: Arm
    task_identity: str
    seed: int
    verdict_state: VerdictState
    secondary_passed: bool | None
    flaky: bool
    prompt_tokens: int
    completion_tokens: int
    model: str
    model_version: str


class HeldOutAttempt:
    """The single identical harness that attempts a held-out task under an arm.

    The collaborators are injected (the frozen proposer, verifier, the one shared M6
    retriever, and the task adapter), so the harness is hermetically testable and — by
    construction — identical across arms. It holds no per-attempt state.
    """

    def __init__(
        self,
        *,
        proposer: Proposer,
        verifier: Verifier,
        retriever: Retriever,
        adapter: TaskAdapter,
        eval_seed: int,
    ) -> None:
        self._proposer = proposer
        self._verifier = verifier
        self._retriever = retriever
        self._adapter = adapter
        self._eval_seed = eval_seed

    def attempt(self, checkpoint: Checkpoint, corpus_task: CorpusTask) -> AttemptOutcome:
        """Attempt ``corpus_task`` under ``checkpoint``'s arm and memory, read-only.

        Retrieves the arm's memory at the checkpoint (empty for A0), assembles the fixed
        prompt with only that memory varying, and drives the frozen ``propose -> verify``
        loop. Writes nothing.
        """
        seed = derive_task_seed(corpus_task.identity, self._eval_seed)

        # Stateless retrieval over the frozen checkpoint memory (empty for A0).
        query = derive_query(corpus_task.material)
        retrieved = self._retriever.retrieve(query, checkpoint.memory)

        # Condition by assembling context onto an immutable copy of the frozen task;
        # the proposer/verifier interfaces are untouched.
        base_task = self._adapter.materialize(corpus_task)
        assembled = assemble_context(base_task.prompt, retrieved)
        conditioned_task = base_task.model_copy(update={"prompt": assembled.prompt})

        proposal = self._proposer.propose(conditioned_task, seed)
        if proposal.has_patch:
            verdict = self._verifier.verify(conditioned_task, proposal.patch)
            state = verdict.state
            secondary_passed = verdict.secondary_passed
            flaky = verdict.flaky
        else:
            state = VerdictState.NO_PATCH
            secondary_passed = None
            flaky = False

        return AttemptOutcome(
            arm=checkpoint.arm,
            task_identity=corpus_task.identity,
            seed=seed,
            verdict_state=state,
            secondary_passed=secondary_passed,
            flaky=flaky,
            prompt_tokens=proposal.prompt_tokens,
            completion_tokens=proposal.completion_tokens,
            model=proposal.model,
            model_version=proposal.model_version,
        )
