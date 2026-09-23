"""Unit tests for the M10 held-out analysis executor (M10-C1) — pre-flight and boundary.

Synthetic fixtures only; no real held-out data is read. Pins the pre-flight gate (sealed
design integrity, closed arm set, A0 empty-checkpoint identity, results segregation,
pinned thread environment, conditional statsmodels pin, evaluation-identity resolution),
the structural-error boundary, and the module boundary (no memory or experience surface,
no duplicated statistics).
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest
import statsmodels

from velith.analysis import executor as executor_mod
from velith.analysis.executor import (
    REQUIRED_STATSMODELS_VERSION,
    REQUIRED_THREAD_ENVIRONMENT,
    ExecutionError,
    expected_evaluation_identities,
    run_m10_analysis,
    run_preflight,
)
from velith.analysis.preregistration import ARMS, PreRegistration
from velith.arms.identity import Arm
from velith.episodes.episode import VerdictState
from velith.evaluation.provenance import EvaluationProvenance
from velith.evaluation.record import EvaluationRecord
from velith.evaluation.sink import EvaluationSink


def _hex(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


_A0_CHECKPOINT = _hex("a0-empty-checkpoint")


def _prereg(checkpoint_count: int = 1, *, manifest: str = "manifest") -> PreRegistration:
    return PreRegistration.build(
        manifest_hash=_hex(manifest),
        checkpoint_identities=tuple(_hex(f"cp{i}") for i in range(1, checkpoint_count + 1)),
        base_model="synthetic-base",
        eval_seed=7,
        max_tasks=64,
        max_attempts_per_task=1,
        max_tokens=2048,
    )


def _evaluation_identity(prereg: PreRegistration, checkpoint: str, arm: str) -> str:
    return EvaluationProvenance(
        checkpoint_identity=checkpoint,
        manifest_hash=prereg.manifest_hash,
        arm=arm,
        base_model=prereg.base_model,
        eval_seed=prereg.eval_seed,
        max_tasks=prereg.max_tasks,
        max_attempts_per_task=prereg.max_attempts_per_task,
        max_tokens=prereg.max_tokens,
    ).identity


def _record(
    prereg: PreRegistration, *, checkpoint: str, arm: str, task: str, passed: bool
) -> EvaluationRecord:
    return EvaluationRecord(
        evaluation_identity=_evaluation_identity(prereg, checkpoint, arm),
        arm=arm,
        task_identity=task,
        seed=prereg.eval_seed,
        verdict_state=VerdictState.PASSED if passed else VerdictState.FAILED,
        prompt_tokens=10,
        completion_tokens=20,
        model="synthetic-model",
        model_version="1",
    )


def _tasks(count: int) -> tuple[str, ...]:
    return tuple(_hex(f"task-{index}") for index in range(count))


def _k1_records(prereg: PreRegistration, tasks: tuple[str, ...]) -> list[EvaluationRecord]:
    """A0 never passes; A1 passes the first half; A2 all but the last."""
    records: list[EvaluationRecord] = []
    checkpoint = prereg.checkpoint_identities[0]
    for index, task in enumerate(tasks):
        records.append(
            _record(prereg, checkpoint=_A0_CHECKPOINT, arm=Arm.A0.value, task=task, passed=False)
        )
        records.append(
            _record(
                prereg,
                checkpoint=checkpoint,
                arm=Arm.A1.value,
                task=task,
                passed=index < len(tasks) // 2,
            )
        )
        records.append(
            _record(
                prereg,
                checkpoint=checkpoint,
                arm=Arm.A2.value,
                task=task,
                passed=index < len(tasks) - 1,
            )
        )
    return records


def _sink(tmp_path: Path, records: list[EvaluationRecord]) -> EvaluationSink:
    sink = EvaluationSink(tmp_path / "sink" / "evaluations.jsonl")
    for record in records:
        sink.append(record)
    return sink


def _results_dir(tmp_path: Path) -> Path:
    return tmp_path / "results"


def _resealed(prereg: PreRegistration, **updates: object) -> PreRegistration:
    """A pre-registration with fields changed and its identity recomputed to stay valid."""
    draft = prereg.model_copy(update={**updates, "identity": ""})
    return draft.model_copy(update={"identity": draft.compute_identity()})


# ---------------------------------------------------------------------------
# Expected evaluation-identity reconstruction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("checkpoint_count", [1, 2, 3])
def test_expected_identity_set_has_one_a0_and_two_per_checkpoint(checkpoint_count: int) -> None:
    prereg = _prereg(checkpoint_count)
    expected = expected_evaluation_identities(prereg, _A0_CHECKPOINT)
    # OED-2: A0 contributes exactly one identity, never one per checkpoint.
    assert len(expected) == 1 + 2 * checkpoint_count
    assert _evaluation_identity(prereg, _A0_CHECKPOINT, Arm.A0.value) in expected


def test_expected_identity_set_is_manifest_sensitive() -> None:
    first = expected_evaluation_identities(_prereg(2), _A0_CHECKPOINT)
    other = expected_evaluation_identities(_prereg(2, manifest="other"), _A0_CHECKPOINT)
    # The manifest hash is an input to the digest, so it is verified cryptographically.
    assert first.isdisjoint(other)


# ---------------------------------------------------------------------------
# Pre-flight gate
# ---------------------------------------------------------------------------


def _preflight(
    tmp_path: Path,
    *,
    prereg: PreRegistration | None = None,
    a0: str = _A0_CHECKPOINT,
    results_dir: Path | None = None,
) -> frozenset[str]:
    preregistration = _prereg() if prereg is None else prereg
    return run_preflight(
        preregistration=preregistration,
        evaluation_sink=_sink(tmp_path, []),
        results_dir=_results_dir(tmp_path) if results_dir is None else results_dir,
        a0_checkpoint_identity=a0,
    )


def test_preflight_passes_on_a_valid_design(tmp_path: Path) -> None:
    assert len(_preflight(tmp_path)) == 3


def test_preflight_rejects_a_tampered_identity(tmp_path: Path) -> None:
    tampered = _prereg().model_copy(update={"identity": "0" * 64})
    with pytest.raises(ExecutionError, match="integrity check failed"):
        _preflight(tmp_path, prereg=tampered)


def test_preflight_rejects_an_arm_set_outside_the_frozen_closed_set(tmp_path: Path) -> None:
    wrong_arms = _resealed(_prereg(), arms=(Arm.A0.value, Arm.A1.value))
    assert wrong_arms.verify_identity()  # internally consistent, still not the frozen set
    with pytest.raises(ExecutionError, match="closed set"):
        _preflight(tmp_path, prereg=wrong_arms)
    assert (Arm.A0.value, Arm.A1.value, Arm.A2.value) == ARMS


@pytest.mark.parametrize("bad", ["", "not-hex", "abc", "A" * 64])
def test_preflight_rejects_a_non_concrete_a0_identity(tmp_path: Path, bad: str) -> None:
    with pytest.raises(ExecutionError, match="concrete content-addressed"):
        _preflight(tmp_path, a0=bad)


def test_preflight_rejects_an_a0_identity_colliding_with_the_schedule(tmp_path: Path) -> None:
    prereg = _prereg(2)
    with pytest.raises(ExecutionError, match="collides"):
        _preflight(tmp_path, prereg=prereg, a0=prereg.checkpoint_identities[0])


def test_preflight_rejects_a_results_directory_inside_the_sink(tmp_path: Path) -> None:
    sink = _sink(tmp_path, [])
    with pytest.raises(ExecutionError, match="not segregated"):
        run_preflight(
            preregistration=_prereg(),
            evaluation_sink=sink,
            results_dir=sink.path.parent,
            a0_checkpoint_identity=_A0_CHECKPOINT,
        )


@pytest.mark.parametrize("name", [entry[0] for entry in REQUIRED_THREAD_ENVIRONMENT])
def test_preflight_rejects_a_violated_thread_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(name, "4")
    with pytest.raises(ExecutionError, match="pinned numeric environment"):
        _preflight(tmp_path)


def test_preflight_rejects_a_wrong_statsmodels_on_the_kgt1_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(statsmodels, "__version__", "9.9.9")
    with pytest.raises(ExecutionError, match="pinned statistical library"):
        _preflight(tmp_path, prereg=_prereg(2))


def test_preflight_does_not_require_statsmodels_on_the_k1_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # K=1 is the exact McNemar path and never fits a GEE, so it must not be coupled to it.
    monkeypatch.setattr(statsmodels, "__version__", "9.9.9")
    assert len(_preflight(tmp_path, prereg=_prereg(1))) == 3
    assert REQUIRED_STATSMODELS_VERSION == "0.15.0"


# ---------------------------------------------------------------------------
# Structural / data-integrity boundary — never an analytical outcome
# ---------------------------------------------------------------------------


def _execute(
    tmp_path: Path,
    prereg: PreRegistration,
    records: list[EvaluationRecord],
    tasks: tuple[str, ...],
    *,
    run_complete: bool = True,
) -> object:
    return run_m10_analysis(
        preregistration=prereg,
        evaluation_sink=_sink(tmp_path, records),
        results_dir=_results_dir(tmp_path),
        a0_checkpoint_identity=_A0_CHECKPOINT,
        task_identities=tasks,
        evaluation_run_complete=run_complete,
    )


def test_a_foreign_arm_is_a_structural_error_with_no_result_written(tmp_path: Path) -> None:
    prereg = _prereg()
    tasks = _tasks(4)
    records = _k1_records(prereg, tasks)
    records.append(
        _record(
            prereg,
            checkpoint=prereg.checkpoint_identities[0],
            arm="A9",
            task=tasks[0],
            passed=True,
        )
    )
    with pytest.raises(ExecutionError, match="outside the pre-registered set"):
        _execute(tmp_path, prereg, records, tasks)
    assert not _results_dir(tmp_path).exists()


def test_a_manifest_mismatch_is_a_structural_error(tmp_path: Path) -> None:
    prereg = _prereg()
    tasks = _tasks(4)
    # Records measured under a different manifest resolve to different identities.
    foreign = _k1_records(_prereg(manifest="other-manifest"), tasks)
    with pytest.raises(ExecutionError, match="outside the pre-registered set"):
        _execute(tmp_path, prereg, foreign, tasks)
    assert not _results_dir(tmp_path).exists()


def test_a_checkpoint_mismatch_is_a_structural_error(tmp_path: Path) -> None:
    prereg = _prereg()
    tasks = _tasks(4)
    records = _k1_records(prereg, tasks)
    records.append(
        _record(
            prereg, checkpoint=_hex("unregistered-cp"), arm=Arm.A1.value, task=tasks[0], passed=True
        )
    )
    with pytest.raises(ExecutionError, match="outside the pre-registered set"):
        _execute(tmp_path, prereg, records, tasks)


def test_structural_errors_never_fabricate_an_outcome(tmp_path: Path) -> None:
    prereg = _prereg()
    tasks = _tasks(4)
    foreign = _k1_records(_prereg(manifest="other"), tasks)
    with pytest.raises(ExecutionError) as caught:
        _execute(tmp_path, prereg, foreign, tasks)
    message = str(caught.value)
    for fabricated in ("VOID", "NO_GO", "p=1", "p_value"):
        assert fabricated not in message
    assert not _results_dir(tmp_path).exists()


# ---------------------------------------------------------------------------
# Module boundary
# ---------------------------------------------------------------------------


def _imports() -> set[str]:
    source = Path(executor_mod.__file__).read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def test_executor_imports_no_memory_or_experience_surface() -> None:
    forbidden = (
        "velith.memory",
        "velith.episodes.writer",
        "velith.episodes.store",
        "velith.episodes.index",
        "velith.retrieval.memory",
        "velith.retrieval.retriever",
        "velith.arms.memory_view",
        "velith.evaluation.runner",
        "velith.evaluation.checkpoint",
    )
    overlap = _imports() & set(forbidden)
    assert not overlap, f"forbidden imports: {overlap}"


def test_executor_writes_through_no_experience_surface() -> None:
    source = Path(executor_mod.__file__).read_text(encoding="utf-8")
    assert "GuardedEpisodeWriter" not in _imported_names()
    assert "EpisodeStore" not in _imported_names()
    # The only write surface is the frozen C12 write-once mechanism.
    assert "write_result_record" in _imported_names()
    assert source.count("write_result_record(") >= 1


def _imported_names() -> set[str]:
    source = Path(executor_mod.__file__).read_text(encoding="utf-8")
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import | ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def test_executor_reuses_the_frozen_statistics_rather_than_reimplementing_them() -> None:
    imported = _imports()
    # Every statistic is imported from its frozen module; none is defined here.
    for frozen in (
        "velith.analysis.binder",
        "velith.analysis.completeness",
        "velith.analysis.mcnemar",
        "velith.analysis.gee",
        "velith.analysis.emm",
        "velith.analysis.wald",
        "velith.analysis.trend",
        "velith.analysis.holm",
        "velith.analysis.decision",
        "velith.analysis.result_record",
    ):
        assert frozen in imported, f"executor must compose {frozen}"
    source = Path(executor_mod.__file__).read_text(encoding="utf-8")
    # No re-derivation of a frozen quantity.
    for reimplementation in ("norm.sf", "math.comb", "expit(", "cholesky", "def holm_"):
        assert reimplementation not in source


def test_executor_defines_no_new_statistical_surface() -> None:
    public = {name for name in dir(executor_mod) if not name.startswith("_")}
    for forbidden in ("ALPHA", "THRESHOLD", "EPSILON", "SE_FLOOR", "MIN_P_VALUE"):
        assert forbidden not in public
    assert not any("epsilon" in name.lower() for name in public)
    assert not any("clip" in name.lower() for name in public)
