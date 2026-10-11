"""The proposer agent (M1 spec §5/§7, handoff §4.6).

``ProposerAgent`` turns a :class:`~velith.task.Task` into a candidate
:class:`Proposal`: it sends the task's prompt to the thin LLM client and performs
**minimal** extraction of a diff-shaped patch from the completion. It depends on the
client *abstraction*, not on Ollama directly (the M5 routing seam, D9/§8).

Minimal extraction only (handoff §4.6 / RK2). The model is instructed to reply with a
unified diff; extraction prefers a fenced code block, else accepts a raw diff that
begins with a diff marker, else yields no patch. There is deliberately no regex zoo,
no "repair the diff" heuristics, no multi-branch parsing — that elaborate parsing is
the MiniNoetica ``analyze()`` debt this milestone avoids.

Outcome discipline (§7). ``propose`` always returns a ``Proposal``. If the model
yields no usable patch, the proposal carries an empty patch (the ``NO_PATCH`` marker,
surfaced by :attr:`Proposal.has_patch`) rather than raising. An infrastructure
failure of the model call is *not* a no-patch outcome — it propagates as
``ModelUnavailableError`` for the orchestrator to map to ``INFRA_ERROR``.

Scope: no memory, no retrieval, no multiple attempts, no self-critique (later
milestones). The prompt is the task's prompt material; enriching that material (e.g.
embedding source files) is a Task/fixture concern, keeping this agent within its
declared dependencies (llm/client, task, core/logging).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from velith.core.logging import get_logger
from velith.llm.client import OllamaClient
from velith.task import Task

logger = get_logger(__name__)

# Opening-fence language tags stripped from a fenced code block, if present.
_FENCE = "```"
_FENCE_LANGUAGE_TAGS = frozenset({"diff", "patch", "udiff", "python"})

# A raw (unfenced) completion is treated as a patch only if it begins with one of
# these unified-diff markers.
_DIFF_PREFIXES = ("diff --git", "--- ", "@@")


class Proposal(BaseModel):
    """A candidate patch plus the exact prompt and call metadata.

    ``patch`` is the extracted diff, or empty when the model produced no usable
    patch (the NO_PATCH marker — see :attr:`has_patch`). ``protected_namespaces=()``
    permits the ``model_version`` field name.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", protected_namespaces=())

    patch: str
    prompt: str
    prompt_tokens: int
    completion_tokens: int
    latency_seconds: float
    model: str
    model_version: str

    @property
    def has_patch(self) -> bool:
        """True iff a non-empty candidate patch was extracted."""
        return bool(self.patch.strip())


def _hunk_counts(header: str) -> tuple[int, int] | None:
    """(old, new) line counts of a ``@@ -a[,b] +c[,d] @@`` header, or None if malformed."""
    parts = header.split(" ")
    if len(parts) < 4 or parts[3] != "@@" or parts[1][:1] != "-" or parts[2][:1] != "+":
        return None
    old_start, _, old_count = parts[1][1:].partition(",")
    new_start, _, new_count = parts[2][1:].partition(",")
    counts = (old_count or "1", new_count or "1")
    if not all(s.isdigit() for s in (old_start, new_start, *counts)):
        return None
    return int(counts[0]), int(counts[1])


def _final_hunk_shortfall(lines: list[str]) -> int:
    """Context lines the last hunk's own header still expects after ``lines`` end."""
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith("@@"):
            counts = _hunk_counts(lines[i])
            if counts is None:
                return 0
            old_left, new_left = counts
            for line in lines[i + 1 :]:
                if line.startswith("\\"):
                    continue
                if line.startswith("-"):
                    old_left -= 1
                elif line.startswith("+"):
                    new_left -= 1
                else:
                    old_left -= 1
                    new_left -= 1
            return max(0, min(old_left, new_left))
    return 0


def _trim(text: str) -> str:
    """Trim surrounding whitespace without deleting diff content (D32 / F-1).

    Identical to ``text.strip()`` unless the final hunk's own header still counts lines
    that ``strip()`` would delete. Those trailing whitespace-only lines are kept,
    because a single-space line is how a unified diff encodes a blank context line; it
    is not padding. Nothing is added, reordered or rewritten: the kept lines are the
    model's own bytes.
    """
    lines = text.lstrip().splitlines()
    tail: list[str] = []
    while lines and not lines[-1].strip():
        tail.insert(0, lines.pop())
    keep = _final_hunk_shortfall(lines)
    if keep == 0 or not tail:
        return text.strip()
    return "\n".join(lines + tail[:keep])


def _extract_patch(text: str) -> str:
    """Minimally extract a diff-shaped patch from a completion, or '' if none."""
    if _FENCE in text:
        start = text.find(_FENCE) + len(_FENCE)
        end = text.find(_FENCE, start)
        if end != -1:
            lines = text[start:end].splitlines()
            if lines and lines[0].strip().lower() in _FENCE_LANGUAGE_TAGS:
                lines = lines[1:]
            candidate = _trim("\n".join(lines))
            if candidate:
                return candidate + "\n"
    stripped = _trim(text)
    if stripped.startswith(_DIFF_PREFIXES):
        return stripped + "\n"
    return ""


class ProposerAgent:
    """Turn a task into a candidate Proposal via the thin LLM client."""

    def __init__(self, client: OllamaClient, model: str, temperature: float = 0.0) -> None:
        self._client = client
        self._model = model
        self._temperature = temperature

    def propose(self, task: Task, seed: int) -> Proposal:
        """Return a Proposal for ``task``; never raises on a no-patch completion."""
        prompt = task.prompt
        completion = self._client.generate(
            prompt=prompt,
            model=self._model,
            seed=seed,
            temperature=self._temperature,
        )
        proposal = Proposal(
            patch=_extract_patch(completion.text),
            prompt=prompt,
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
            latency_seconds=completion.latency_seconds,
            model=completion.model,
            model_version=completion.model_version,
        )
        logger.info(
            "proposal produced",
            extra={
                "event": "proposal_produced",
                "task_id": task.task_id,
                "has_patch": proposal.has_patch,
                "completion_tokens": proposal.completion_tokens,
            },
        )
        return proposal
