"""Unit tests for the mocked LLM path (C5: Ollama client; C6 adds the proposer).

This is the project's mocked-llm-client test home (M1 spec §4). C5 establishes the
reusable transport-mocking scaffolding (``_StubTransport``) and pins the thin
``OllamaClient`` adapter contract against it; C6 adds the proposer's tests here using
the same scaffolding. No test in this file touches a real Ollama — CI stays hermetic
(M1 spec §14).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from velith.agent.proposer import Proposal, ProposerAgent
from velith.llm.client import Completion, ModelUnavailableError, OllamaClient
from velith.task import Task


class _StubTransport:
    """A fake transport: returns a canned Ollama reply and records the request.

    Reused by C6 to build an ``OllamaClient`` whose completion text the proposer
    parses, without any network or model server.
    """

    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = response
        self.last_url: str | None = None
        self.last_payload: Mapping[str, Any] | None = None

    def __call__(self, url: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.last_url = url
        self.last_payload = payload
        return self.response


def test_generate_returns_completion_and_metadata() -> None:
    stub = _StubTransport(
        {
            "model": "qwen2.5-coder:7b",
            "response": "a candidate patch",
            "prompt_eval_count": 11,
            "eval_count": 22,
            "done": True,
        }
    )
    client = OllamaClient(host="http://stub", transport=stub)
    completion = client.generate(prompt="fix it", model="qwen2.5-coder", seed=0, temperature=0.0)

    assert isinstance(completion, Completion)
    assert completion.text == "a candidate patch"
    assert completion.model == "qwen2.5-coder"
    assert completion.model_version == "qwen2.5-coder:7b"
    assert completion.prompt_tokens == 11
    assert completion.completion_tokens == 22
    assert completion.latency_seconds >= 0.0


def test_generate_sends_a_well_formed_non_streaming_request() -> None:
    stub = _StubTransport({"model": "m", "response": "x", "prompt_eval_count": 1, "eval_count": 1})
    client = OllamaClient(host="http://stub/", transport=stub)
    client.generate(prompt="p", model="m", seed=7, temperature=0.0)

    assert stub.last_url == "http://stub/api/generate"
    assert stub.last_payload is not None
    assert stub.last_payload["model"] == "m"
    assert stub.last_payload["prompt"] == "p"
    assert stub.last_payload["stream"] is False
    assert stub.last_payload["options"] == {"seed": 7, "temperature": 0.0}


def test_infra_failure_raises_model_unavailable() -> None:
    def boom(url: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        raise OSError("connection refused")

    client = OllamaClient(host="http://stub", transport=boom)
    with pytest.raises(ModelUnavailableError):
        client.generate(prompt="x", model="m", seed=0, temperature=0.0)


def test_malformed_response_raises_model_unavailable() -> None:
    client = OllamaClient(host="http://stub", transport=_StubTransport({"unexpected": "shape"}))
    with pytest.raises(ModelUnavailableError):
        client.generate(prompt="x", model="m", seed=0, temperature=0.0)


# --- C6: proposer agent ------------------------------------------------------

_DIFF = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-bad\n+good\n"
_TASK = Task(
    task_id="t",
    repo_path=Path("/unused-in-proposer"),
    prompt="Fix the bug; reply with a unified diff patch only.",
    hidden_test_command=("python", "-m", "pytest", "-q"),
)


def _proposer_returning(completion_text: str) -> ProposerAgent:
    """Build a proposer backed by an OllamaClient whose reply is fully canned."""
    stub = _StubTransport(
        {
            "model": "m:tag",
            "response": completion_text,
            "prompt_eval_count": 3,
            "eval_count": 5,
        }
    )
    client = OllamaClient(host="http://stub", transport=stub)
    return ProposerAgent(client=client, model="m", temperature=0.0)


def test_propose_extracts_a_fenced_diff() -> None:
    proposer = _proposer_returning(f"Here you go:\n```diff\n{_DIFF}```\n")
    proposal = proposer.propose(_TASK, seed=0)

    assert isinstance(proposal, Proposal)
    assert proposal.has_patch
    assert proposal.patch.strip().startswith("--- a/x.py")
    assert "+good" in proposal.patch
    # metadata flows through from the completion
    assert proposal.prompt == _TASK.prompt
    assert proposal.model == "m"
    assert proposal.model_version == "m:tag"
    assert proposal.prompt_tokens == 3
    assert proposal.completion_tokens == 5


def test_propose_extracts_a_raw_unfenced_diff() -> None:
    proposal = _proposer_returning(_DIFF).propose(_TASK, seed=0)
    assert proposal.has_patch
    assert proposal.patch.strip().startswith("--- a/x.py")


def test_propose_with_no_diff_returns_no_patch_marker() -> None:
    proposal = _proposer_returning("I cannot find a bug to fix here.").propose(_TASK, seed=0)
    assert not proposal.has_patch
    assert proposal.patch == ""


def test_propose_propagates_model_unavailable_rather_than_no_patch() -> None:
    def boom(url: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        raise OSError("ollama down")

    proposer = ProposerAgent(client=OllamaClient(host="http://stub", transport=boom), model="m")
    with pytest.raises(ModelUnavailableError):
        proposer.propose(_TASK, seed=0)
