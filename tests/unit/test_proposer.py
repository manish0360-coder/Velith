"""Unit tests for the mocked LLM path (C5: Ollama client; C6 adds the proposer).

This is the project's mocked-llm-client test home (M1 spec §4). C5 establishes the
reusable transport-mocking scaffolding (``_StubTransport``) and pins the thin
``OllamaClient`` adapter contract against it; C6 adds the proposer's tests here using
the same scaffolding. No test in this file touches a real Ollama — CI stays hermetic
(M1 spec §14).

D32 / F-1 adds the patch-extraction regression tests at the end of this file: the
former ``strip()`` deleted a trailing blank context line, so ``git apply`` rejected
correct patches (pilot evidence: P2-11 U arm, P3-01, P3-10; P1-T1 is a guard case).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from velith.agent.proposer import (
    Proposal,
    ProposerAgent,
    _extract_patch,
    _final_hunk_shortfall,
    _hunk_counts,
)
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


# --- D32 / F-1: patch extraction keeps counted blank context lines ---------------

_CASES_FILE = Path(__file__).resolve().parents[1] / "fixtures" / "f1_extract" / "cases.json"
_CASES: dict[str, dict[str, Any]] = {
    c["case"]: c for c in json.loads(_CASES_FILE.read_text(encoding="utf-8"))["cases"]
}
_FENCE_TAGS = frozenset({"diff", "patch", "udiff", "python"})


def _former_extract(text: str) -> str:
    """The pre-D32 extraction, verbatim, kept as the behavioural reference."""
    if "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end != -1:
            lines = text[start:end].splitlines()
            if lines and lines[0].strip().lower() in _FENCE_TAGS:
                lines = lines[1:]
            candidate = "\n".join(lines).strip()
            if candidate:
                return candidate + "\n"
    stripped = text.strip()
    if stripped.startswith(("diff --git", "--- ", "@@")):
        return stripped + "\n"
    return ""


def _git_apply_check(tmp_path: Path, rel: str, content: str, patch: str) -> bool:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    result = subprocess.run(
        ["git", "-C", str(tmp_path), "apply", "--check", "-"],
        input=patch.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


@pytest.mark.parametrize("case", ["P2-11-U", "P3-01", "P3-10"])
def test_real_false_negatives_now_apply(case: str, tmp_path: Path) -> None:
    c = _CASES[case]
    fixed = _extract_patch(c["completion"])
    former = _former_extract(c["completion"])
    assert fixed == former + " \n"  # exactly one line restored: the blank context line
    assert _git_apply_check(tmp_path / "fixed", c["path"], c["source_window"], fixed)
    assert not _git_apply_check(tmp_path / "former", c["path"], c["source_window"], former)


def test_p1_t1_surplus_blank_line_is_still_dropped(tmp_path: Path) -> None:
    c = _CASES["P1-T1"]
    out = _extract_patch(c["completion"])
    assert out == _former_extract(c["completion"])
    assert not out.endswith("\n \n")
    # It still does not apply, for a reason unrelated to F-1: the model's context
    # omits four import lines that the source file contains.
    assert not _git_apply_check(tmp_path, c["path"], c["source_window"], out)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("@@ -1,5 +1,5 @@", (5, 5)),
        ("@@ -349,11 +349,13 @@ def write(self, table):", (11, 13)),
        ("@@ -1 +1 @@", (1, 1)),
        ("@@ -0,0 +1,2 @@", (0, 2)),
        ("@@ -1,x +1,2 @@", None),
        ("@@ -x +y @@", None),
        ("@@ garbage", None),
    ],
)
def test_hunk_counts(header: str, expected: tuple[int, int] | None) -> None:
    assert _hunk_counts(header) == expected


def test_shortfall_counts_context_minus_plus_and_ignores_no_newline_marker() -> None:
    lines = ["--- a/m.py", "+++ b/m.py", "@@ -1,3 +1,3 @@", " a", "-b", "+B", "\\ No newline"]
    assert _final_hunk_shortfall(lines) == 1
    assert _final_hunk_shortfall([*lines, " c"]) == 0
    assert _final_hunk_shortfall(["no hunk here"]) == 0


_SYNTHETIC = [
    # blank context line at the end of the final hunk: restored
    ("```diff\n--- a/m.py\n+++ b/m.py\n@@ -1,3 +1,3 @@\n a\n-b\n+B\n \n```", True),
    # surplus whitespace beyond the hunk's count: still stripped
    ("```diff\n--- a/m.py\n+++ b/m.py\n@@ -1,2 +1,2 @@\n a\n-b\n+B\n \n \n```", False),
    # malformed header (non-numeric ranges): former behaviour
    ("```diff\n--- a/m.py\n+++ b/m.py\n@@ -x +y @@\n a\n \n```", False),
    # unfenced raw diff with a counted blank context line: restored
    ("--- a/m.py\n+++ b/m.py\n@@ -1,3 +1,3 @@\n a\n-b\n+B\n \n", True),
    # leading whitespace and trailing spaces on the last content line: former behaviour
    ("```\n\n  --- a/m.py\n+++ b/m.py\n@@ -1,2 +1,2 @@\n a\n-b\n+B   \n\n```", False),
    # no patch at all
    ("I cannot produce a diff.", False),
    ("```python\nprint('hi')\n```", False),
]


@pytest.mark.parametrize(("text", "restored"), _SYNTHETIC)
def test_only_counted_blank_context_lines_change_behaviour(text: str, restored: bool) -> None:
    former = _former_extract(text)
    if restored:
        assert _extract_patch(text) == former + " \n"
    else:
        assert _extract_patch(text) == former
