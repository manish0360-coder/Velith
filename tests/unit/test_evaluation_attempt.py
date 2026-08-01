"""Unit tests for the M8 memory-conditioned held-out attempt (M8-C5).

Hermetic: a mocked proposer records the task it is handed and returns a fixed proposal;
a stub verifier returns a fixed verdict — no model, no network, in-process embedding.
Pins M8_SPEC §3.3: the harness is identical across arms with memory the sole input
difference; an empty checkpoint yields the identical assembled attempt input across
A0/A1/A2; retrieval holds no cross-attempt state; A0 attempts memorylessly; and the
frozen proposer/verifier are driven unmodified.
"""

from __future__ import annotations

from pathlib import Path

from velith.agent.proposer import Proposal
from velith.arms.binding import resolve_binding
from velith.arms.identity import Arm
from velith.corpus.loader import CorpusTask
from velith.corpus.manifest import Partition
from velith.episodes.episode import Episode, VerdictState
from velith.episodes.store import EpisodeStore
from velith.evaluation.attempt import HeldOutAttempt
from velith.evaluation.checkpoint import form_checkpoint
from velith.harness.verifier_sandbox import Verdict
from velith.retrieval.embedding import EMBEDDER_NAME, get_embedder
from velith.retrieval.memory import EpisodeMemory
from velith.retrieval.retriever import Retriever
from velith.task import Task


class RecordingProposer:
    """Records each task it is asked to propose for; returns a fixed proposal."""

    def __init__(self) -> None:
        self.seen: list[Task] = []

    def propose(self, task: Task, seed: int) -> Proposal:
        self.seen.append(task)
        return Proposal(
            patch="--- a/x\n+++ b/x\n",
            prompt=task.prompt,
            prompt_tokens=11,
            completion_tokens=22,
            latency_seconds=1.0,
            model="mock-model",
            model_version="mock-1",
        )


class StubVerifier:
    """Returns a fixed grounded verdict for any patch."""

    def verify(self, task: Task, patch: str) -> Verdict:
        return Verdict(
            state=VerdictState.PASSED,
            output="1 passed",
            secondary_passed=True,
            flaky=False,
            duration_seconds=2.0,
        )


class OneTaskAdapter:
    """A minimal adapter materializing a fixed verifiable task, opaque to the corpus task."""

    def __init__(self, prompt: str = "base task prompt") -> None:
        self._prompt = prompt

    def materialize(self, corpus_task: CorpusTask) -> Task:
        return Task(
            task_id="t",
            repo_path=Path("tests/fixtures/calc_add_bug"),
            prompt=self._prompt,
            hidden_test_command=("python", "-m", "pytest", "-q"),
        )


def _episode(prompt: str, arm: Arm) -> Episode:
    return Episode.build(
        task_id="t",
        seed=0,
        model="m",
        model_version="v",
        prompt=prompt,
        patch="diff",
        verdict_state=VerdictState.PASSED,
        verdict_output="out",
        prompt_tokens=1,
        completion_tokens=2,
        latency_seconds=1.0,
        verify_seconds=2.0,
        velith_version="0.0.0",
        arm=arm.value,
        secondary_passed=True,
        flaky=False,
        timestamp="2026-07-06T00:00:00+00:00",
    )


def _corpus_task(material: str = "M-held") -> CorpusTask:
    return CorpusTask(label="held", material=material, handle="H", partition=Partition.HELD_OUT)


def _attempt(
    proposer: RecordingProposer, verifier: StubVerifier, eval_seed: int = 0
) -> HeldOutAttempt:
    return HeldOutAttempt(
        proposer=proposer,
        verifier=verifier,
        retriever=Retriever(get_embedder(EMBEDDER_NAME), 5),
        adapter=OneTaskAdapter(),
        eval_seed=eval_seed,
    )


def _populate(path: Path, episodes: list[Episode]) -> None:
    store = EpisodeStore(path)
    for episode in episodes:
        store.append(episode)


def test_empty_checkpoint_yields_identical_attempt_input_across_arms(tmp_path: Path) -> None:
    """A0/A1/A2 at an empty checkpoint hand the proposer a bit-identical task (§3.3)."""
    empty = tmp_path / "empty.jsonl"
    _populate(empty, [])
    task = _corpus_task()

    prompts: list[str] = []
    for arm in (Arm.A0, Arm.A1, Arm.A2):
        proposer = RecordingProposer()
        checkpoint = form_checkpoint(arm, EpisodeMemory(empty))
        _attempt(proposer, StubVerifier()).attempt(checkpoint, task)
        prompts.append(proposer.seen[0].prompt)

    assert prompts[0] == prompts[1] == prompts[2]


def test_a0_attempts_memorylessly(tmp_path: Path) -> None:
    """A0's prompt is the task portion alone, even when experience exists (§3.3)."""
    path = tmp_path / "episodes.jsonl"
    _populate(path, [_episode("prior alpha", Arm.A1), _episode("prior beta", Arm.A1)])
    task = _corpus_task()

    a0_proposer = RecordingProposer()
    a0_ckpt = form_checkpoint(Arm.A0, EpisodeMemory(path))
    _attempt(a0_proposer, StubVerifier()).attempt(a0_ckpt, task)

    empty_proposer = RecordingProposer()
    empty_ckpt = form_checkpoint(Arm.A0, EpisodeMemory(tmp_path / "none.jsonl"))
    _attempt(empty_proposer, StubVerifier()).attempt(empty_ckpt, task)

    assert "prior alpha" not in a0_proposer.seen[0].prompt
    assert a0_proposer.seen[0].prompt == empty_proposer.seen[0].prompt


def test_memory_conditions_the_prompt_for_a_memory_arm(tmp_path: Path) -> None:
    """A1 with experience conditions the proposer on its retrieved memory (§3.3)."""
    path = tmp_path / "episodes.jsonl"
    _populate(path, [_episode("prior alpha", Arm.A1), _episode("prior beta", Arm.A1)])

    proposer = RecordingProposer()
    checkpoint = form_checkpoint(Arm.A1, EpisodeMemory(path))
    _attempt(proposer, StubVerifier()).attempt(checkpoint, _corpus_task())

    conditioned = proposer.seen[0].prompt
    assert "base task prompt" in conditioned
    assert "prior alpha" in conditioned or "prior beta" in conditioned


def test_outcome_is_the_verifier_verdict_with_token_counts(tmp_path: Path) -> None:
    """The outcome carries the deterministic verdict, secondary, and token counts (§3.4)."""
    path = tmp_path / "episodes.jsonl"
    _populate(path, [])
    outcome = _attempt(RecordingProposer(), StubVerifier()).attempt(
        form_checkpoint(Arm.A1, EpisodeMemory(path)), _corpus_task()
    )
    assert outcome.arm is Arm.A1
    assert outcome.verdict_state is VerdictState.PASSED
    assert outcome.secondary_passed is True
    assert outcome.flaky is False
    assert outcome.prompt_tokens == 11
    assert outcome.completion_tokens == 22
    assert outcome.task_identity == _corpus_task().identity


def test_attempt_is_deterministic_and_stateless(tmp_path: Path) -> None:
    """Repeat and interleaved attempts do not influence one another (§3.3, D16.1)."""
    path = tmp_path / "episodes.jsonl"
    _populate(path, [_episode("prior alpha", Arm.A1)])
    checkpoint = form_checkpoint(Arm.A1, EpisodeMemory(path))
    harness = _attempt(RecordingProposer(), StubVerifier())

    task_a, task_b = _corpus_task("M-a"), _corpus_task("M-b")
    first_a = harness.attempt(checkpoint, task_a)
    _ = harness.attempt(checkpoint, task_b)
    second_a = harness.attempt(checkpoint, task_a)
    assert first_a == second_a


def test_the_binding_backed_checkpoint_conditions_a2(tmp_path: Path) -> None:
    """A2's verified memory conditions its attempt through the shared substrate (§3.3)."""
    path = tmp_path / "episodes.jsonl"
    _populate(path, [_episode("verified alpha", Arm.A2)])
    # Sanity: A2 binds to a filter and its checkpoint is non-empty here.
    assert resolve_binding(Arm.A2).arm is Arm.A2
    proposer = RecordingProposer()
    checkpoint = form_checkpoint(Arm.A2, EpisodeMemory(path))
    _attempt(proposer, StubVerifier()).attempt(checkpoint, _corpus_task())
    assert "verified alpha" in proposer.seen[0].prompt
