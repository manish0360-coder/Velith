"""Unit tests for the M8 evaluation record and sink (M8-C6).

Scope (M8_SPEC §3.4): the record carries the deterministic verdict + secondary + frozen
token counts and **no model score**; the sink round-trips records, is **distinct from the
experience log**, is **not a memory source**, and **never touches the guarded boundary**.
The evaluation identity (C7), runner (C8), and the permanent invariant (C9) are not under
test here.
"""

from __future__ import annotations

import ast
from pathlib import Path

import velith.evaluation
from velith.arms.identity import Arm
from velith.episodes.episode import Episode, VerdictState
from velith.episodes.store import EpisodeStore
from velith.evaluation.attempt import AttemptOutcome
from velith.evaluation.record import EvaluationRecord
from velith.evaluation.sink import EvaluationSink

_MEASUREMENT_FIELDS = {
    "evaluation_identity",
    "arm",
    "task_identity",
    "seed",
    "verdict_state",
    "secondary_passed",
    "flaky",
    "prompt_tokens",
    "completion_tokens",
    "model",
    "model_version",
}


def _outcome(
    arm: Arm = Arm.A1,
    state: VerdictState = VerdictState.PASSED,
    secondary: bool | None = True,
) -> AttemptOutcome:
    return AttemptOutcome(
        arm=arm,
        task_identity="id-held",
        seed=7,
        verdict_state=state,
        secondary_passed=secondary,
        flaky=False,
        prompt_tokens=11,
        completion_tokens=22,
        model="mock-model",
        model_version="mock-1",
    )


def test_record_carries_verdict_secondary_and_token_counts() -> None:
    """The measurement is the grounded verdict + secondary + frozen token counts (§3.4)."""
    record = EvaluationRecord.from_outcome(_outcome(), evaluation_identity="eval-x")
    assert record.verdict_state is VerdictState.PASSED
    assert record.secondary_passed is True
    assert record.prompt_tokens == 11
    assert record.completion_tokens == 22
    assert record.evaluation_identity == "eval-x"
    assert record.arm == "A1"


def test_record_has_no_model_score_or_new_metric() -> None:
    """No LLM-as-judge / model score / non-deterministic quantity is recorded (§3.4)."""
    assert set(EvaluationRecord.model_fields) == _MEASUREMENT_FIELDS
    forbidden = ("score", "reward", "rating", "confidence", "logprob", "judge", "duration")
    for name in EvaluationRecord.model_fields:
        assert not any(token in name for token in forbidden)


def test_from_outcome_maps_every_field() -> None:
    """The record faithfully mirrors the attempt outcome (§3.4)."""
    outcome = _outcome(arm=Arm.A2, state=VerdictState.FAILED, secondary=False)
    record = EvaluationRecord.from_outcome(outcome, evaluation_identity="eval-y")
    assert record.arm == "A2"
    assert record.verdict_state is VerdictState.FAILED
    assert record.secondary_passed is False
    assert record.task_identity == outcome.task_identity
    assert record.seed == outcome.seed
    assert record.model == "mock-model"


def test_sink_round_trips_records(tmp_path: Path) -> None:
    """The sink appends and reads back records as measurements, not episodes (§3.4)."""
    sink = EvaluationSink(tmp_path / "eval" / "heldout.jsonl")
    r1 = EvaluationRecord.from_outcome(_outcome(Arm.A0), evaluation_identity="e")
    r2 = EvaluationRecord.from_outcome(_outcome(Arm.A2, VerdictState.FAILED, False), "e")
    sink.append(r1)
    sink.append(r2)

    read = sink.read_all()
    assert read == (r1, r2)
    assert all(isinstance(x, EvaluationRecord) for x in read)


def test_sink_is_distinct_from_the_experience_log(tmp_path: Path) -> None:
    """Records land in the sink, never in the experience log (§3.4)."""
    episode_log = tmp_path / "episodes.jsonl"
    store = EpisodeStore(episode_log)  # the experience log — must stay empty
    sink = EvaluationSink(tmp_path / "eval" / "heldout.jsonl")

    sink.append(EvaluationRecord.from_outcome(_outcome(), evaluation_identity="e"))

    assert sink.path != episode_log
    assert not episode_log.exists() or episode_log.read_text(encoding="utf-8") == ""
    assert not store.read_all()  # nothing leaked into experience


def test_sink_record_is_not_a_valid_episode(tmp_path: Path) -> None:
    """A sink line is a measurement, not an episode — it has no content hash (§3.4)."""
    sink = EvaluationSink(tmp_path / "heldout.jsonl")
    sink.append(EvaluationRecord.from_outcome(_outcome(), evaluation_identity="e"))

    line = sink.path.read_text(encoding="utf-8").splitlines()[0]
    assert "content_hash" not in line
    # It cannot be read back as a frozen Episode (missing required identity fields).
    try:
        Episode.model_validate_json(line)
        raised = False
    except Exception:
        raised = True
    assert raised


def test_record_and_sink_never_reference_the_guarded_boundary() -> None:
    """Structurally, no record can reach the experience path (§3.4, D8)."""
    assert velith.evaluation.__file__ is not None
    eval_dir = Path(velith.evaluation.__file__).parent
    for module in ("record.py", "sink.py"):
        imported: set[str] = set()
        for node in ast.walk(ast.parse((eval_dir / module).read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.add(node.module)
                imported.update(f"{node.module}.{a.name}" for a in node.names)
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
        assert "velith.corpus.heldout" not in imported
        assert not any("GuardedEpisodeWriter" in name for name in imported)
