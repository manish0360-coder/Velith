"""The M1 spike: orchestrate propose -> verify -> log for one task (handoff §4.7).

This module is the **single owner of operation order** (M1 spec §8). It is split into
two layers:

* :func:`run_spike` — the orchestration entry function. It runs the loop and returns
  the persisted :class:`~velith.episodes.episode.Episode`. It is imported **only** by
  the C8 integration test (for mock-proposer injection) and invoked by the CLI shell;
  no other module in ``src`` imports it.
* :func:`main` / the ``__main__`` block — the argument-parsing CLI shell, a terminal
  leaf imported by nothing. It constructs the real components from validated
  ``Settings``, runs the orchestration, maps the outcome to an exit code, and prints
  the single human-facing summary line.

Outcome vs. error (D16.7 / §10/§11). Any grounded verdict — ``PASSED``, ``FAILED``,
``PATCH_APPLY_FAILED``, ``NO_PATCH`` — is a successful loop: the episode is logged and
the process exits 0. Only an infrastructure fault (``ModelUnavailableError`` from the
model call, ``SandboxExecutionError`` from the verifier) aborts non-zero; it is logged
loudly and, because the loop produced no grounded verdict, no episode is persisted
(the store holds grounded outcomes only). ``NO_PATCH`` is decided here — when the
proposal carries no patch the verifier is never invoked.
"""

from __future__ import annotations

import argparse
import sys

from velith import __version__
from velith.agent.proposer import ProposerAgent
from velith.core.config import get_settings
from velith.core.logging import configure_logging, get_logger
from velith.episodes.episode import Episode, VerdictState
from velith.episodes.store import EpisodeStore
from velith.harness.verifier_sandbox import SandboxExecutionError, VerifierSandbox
from velith.llm.client import ModelUnavailableError, OllamaClient
from velith.task import Task, load_fixture_task

logger = get_logger(__name__)


def run_spike(
    task: Task,
    seed: int,
    proposer: ProposerAgent,
    sandbox: VerifierSandbox,
    store: EpisodeStore,
    *,
    velith_version: str,
) -> Episode:
    """Run one propose -> verify -> log episode and return the persisted record.

    The only place the order of operations lives. Raises ``ModelUnavailableError`` or
    ``SandboxExecutionError`` on an infrastructure fault (the CLI maps these to a
    non-zero exit); every grounded verdict is assembled into an episode and stored.
    """
    proposal = proposer.propose(task, seed)
    if proposal.has_patch:
        verdict = sandbox.verify(task, proposal.patch)
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
        secondary_passed=secondary_passed,
        flaky=flaky,
    )
    store.append(episode)
    logger.info(
        "spike completed",
        extra={
            "event": "spike_completed",
            "task_id": task.task_id,
            "verdict_state": state.value,
            "content_hash": episode.content_hash,
        },
    )
    return episode


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: ``python -m velith.runner.spike --task <id> --seed <int>``."""
    parser = argparse.ArgumentParser(
        prog="python -m velith.runner.spike",
        description="Run one propose -> verify -> log episode (the M1 spike).",
    )
    parser.add_argument("--task", required=True, help="task id (M1 has one fixture task)")
    parser.add_argument("--seed", type=int, required=True, help="sampling seed")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings)

    task = load_fixture_task()
    requested_task: str = args.task
    if requested_task != task.task_id:
        logger.error(
            "unknown task id",
            extra={"event": "unknown_task", "requested": requested_task, "available": task.task_id},
        )
        return 2

    seed: int = args.seed
    client = OllamaClient(
        host=settings.ollama_host,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    proposer = ProposerAgent(client=client, model=settings.ollama_model)
    store = EpisodeStore(settings.episode_path, settings.episode_index_path)

    try:
        with VerifierSandbox(timeout_seconds=settings.verifier_timeout_seconds) as sandbox:
            episode = run_spike(task, seed, proposer, sandbox, store, velith_version=__version__)
    except (ModelUnavailableError, SandboxExecutionError) as exc:
        logger.error(
            "spike aborted: infrastructure error",
            extra={"event": "infra_error", "task_id": task.task_id, "error": str(exc)},
        )
        return 1

    print(f"{episode.verdict_state.value} episode -> {store.path} (hash {episode.content_hash})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
