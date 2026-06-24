"""Hermetic end-to-end test of the spike: propose -> verify -> log (C8).

Wires the REAL verifier and store to a mocked proposer — a real ``ProposerAgent``
backed by a stub transport, so no Ollama and no network are touched and CI stays
hermetic (M1 spec §14). Proves each grounded verdict is logged, and that the
verify->log path is reproducible for a recorded proposal: the same verdict AND the
same content hash on re-run (D16.1).
"""

from __future__ import annotations

import difflib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from velith.agent.proposer import ProposerAgent
from velith.episodes.episode import Episode, VerdictState
from velith.episodes.store import EpisodeStore
from velith.harness.verifier_sandbox import VerifierSandbox
from velith.llm.client import OllamaClient
from velith.runner.spike import run_spike
from velith.task import load_fixture_task

# tests/integration/test_spike_episode.py -> parents[1] is tests/
_FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"
_CALCULATOR = _FIXTURES_ROOT / "calc_add_bug" / "calculator.py"

# A unified diff with deliberately wrong context: extracted as a patch, but it does
# not apply -> PATCH_APPLY_FAILED.
_MALFORMED_PATCH = (
    "--- a/calculator.py\n"
    "+++ b/calculator.py\n"
    "@@ -1,1 +1,1 @@\n"
    "-this line is not in the real file\n"
    "+replacement\n"
)


def _patch(replacement: str) -> str:
    original = _CALCULATOR.read_text(encoding="utf-8")
    modified = original.replace("a - b", replacement)
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile="a/calculator.py",
            tofile="b/calculator.py",
        )
    )


def _proposer_returning(completion_text: str) -> ProposerAgent:
    """A real proposer whose model call is fully canned (no network)."""

    def transport(url: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "model": "stub-model:tag",
            "response": completion_text,
            "prompt_eval_count": 7,
            "eval_count": 9,
        }

    client = OllamaClient(host="http://stub", transport=transport)
    return ProposerAgent(client=client, model="stub-model", temperature=0.0)


def _run_spike(
    store_dir: Path, completion_text: str, seed: int = 0
) -> tuple[Episode, EpisodeStore]:
    task = load_fixture_task(fixtures_root=_FIXTURES_ROOT)
    store = EpisodeStore(store_dir / "episodes.jsonl")
    proposer = _proposer_returning(completion_text)
    with VerifierSandbox() as sandbox:
        episode = run_spike(task, seed, proposer, sandbox, store, velith_version="test")
    return episode, store


def test_good_patch_logs_a_passed_episode(tmp_path: Path) -> None:
    episode, store = _run_spike(tmp_path, _patch("a + b"))
    assert episode.verdict_state == VerdictState.PASSED
    assert episode.model == "stub-model"  # the mocked model — never a real Ollama
    assert episode.verify_hash()
    assert store.read_all() == [episode]  # persisted and re-readable with hash check


def test_applying_patch_that_does_not_fix_logs_failed(tmp_path: Path) -> None:
    episode, _ = _run_spike(tmp_path, _patch("a * b"))
    assert episode.verdict_state == VerdictState.FAILED
    assert episode.verify_hash()


def test_malformed_patch_logs_patch_apply_failed(tmp_path: Path) -> None:
    episode, _ = _run_spike(tmp_path, _MALFORMED_PATCH)
    assert episode.verdict_state == VerdictState.PATCH_APPLY_FAILED
    assert episode.verify_hash()


def test_no_diff_completion_logs_no_patch(tmp_path: Path) -> None:
    episode, _ = _run_spike(tmp_path, "I could not find a bug to fix.")
    assert episode.verdict_state == VerdictState.NO_PATCH
    assert episode.patch == ""
    assert episode.verify_hash()


def test_recorded_proposal_is_reproducible(tmp_path: Path) -> None:
    completion = _patch("a + b")
    first, _ = _run_spike(tmp_path / "run_a", completion)
    second, _ = _run_spike(tmp_path / "run_b", completion)
    assert first.verdict_state == second.verdict_state == VerdictState.PASSED
    # D16.1: a recorded proposal re-verified and re-logged yields the same hash.
    assert first.content_hash == second.content_hash
