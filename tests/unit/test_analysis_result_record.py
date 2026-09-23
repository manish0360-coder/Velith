"""Unit tests for the content-addressed analysis result record (M9-C12 / P2, handoff §9).

Deterministic synthetic fixtures only — no held-out outcome is ever a fixture (handoff §10).

Pins complete-artifact hashing (the identity covers the whole payload except ``identity``),
deterministic sorted ``evaluation_identity`` extraction, exact retention of upstream
p-values / thresholds / provenance, write-once persistence under an explicitly supplied
``results_dir``, and the separation invariant (no memory, episode-writer, store, or sink
import).
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest

from velith import __version__
from velith.analysis import result_record as record_mod
from velith.analysis.completeness import CompletenessResult, CompletenessStatus
from velith.analysis.decision import (
    KGT1_HYPOTHESIS_LABELS,
    DecisionOutcome,
    DecisionResult,
    decide_kgt1,
)
from velith.analysis.gee import SolverProvenance
from velith.analysis.holm import HolmResult, LabeledPValue, holm_bonferroni
from velith.analysis.preregistration import PreRegistration
from velith.analysis.result_record import (
    STATISTICAL_LIBRARY,
    AnalysisResultRecord,
    ResultRecordError,
    build_result_record,
    extract_evaluation_identities,
    serialize_result_record,
    write_result_record,
)
from velith.episodes.episode import VerdictState, compute_content_hash
from velith.evaluation.record import EvaluationRecord

_P_VALUES = (0.0001, 0.0002, 0.0003, 0.0004)


def _hex(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _prereg() -> PreRegistration:
    return PreRegistration.build(
        manifest_hash=_hex("manifest"),
        checkpoint_identities=(_hex("cp1"), _hex("cp2")),
        base_model="synthetic-base",
        eval_seed=7,
        max_tasks=10,
        max_attempts_per_task=1,
        max_tokens=2048,
    )


def _record(evaluation_identity: str, task: str) -> EvaluationRecord:
    return EvaluationRecord(
        evaluation_identity=evaluation_identity,
        arm="A1",
        task_identity=task,
        seed=7,
        verdict_state=VerdictState.PASSED,
        prompt_tokens=10,
        completion_tokens=20,
        model="synthetic-model",
        model_version="1",
    )


def _records() -> list[EvaluationRecord]:
    return [
        _record(_hex("eval-b"), _hex("t2")),
        _record(_hex("eval-a"), _hex("t1")),
        _record(_hex("eval-b"), _hex("t3")),  # duplicate identity, different task
    ]


def _completeness() -> CompletenessResult:
    return CompletenessResult(CompletenessStatus.COMPLETE, (_hex("t1"), _hex("t2")), (), 2)


def _holm(p_values: tuple[float, ...] = _P_VALUES) -> HolmResult:
    family = [
        LabeledPValue(label, p) for label, p in zip(KGT1_HYPOTHESIS_LABELS, p_values, strict=True)
    ]
    return holm_bonferroni(family)


def _solver() -> SolverProvenance:
    return SolverProvenance(
        statsmodels_version="0.15.0",
        numpy_version="2.5.3",
        family="Binomial",
        link="logit",
        cov_struct="Exchangeable",
        cov_type="robust",
        maxiter=100,
        ctol=1e-8,
        start_params="None",
        thread_env=(("OMP_NUM_THREADS", "1"), ("PYTHONHASHSEED", "0")),
    )


def _decision(holm: HolmResult) -> DecisionResult:
    return decide_kgt1(completeness_status=CompletenessStatus.COMPLETE, holm_result=holm)


def _build(**overrides: Any) -> AnalysisResultRecord:
    holm = overrides.pop("holm_result", None)
    if holm is None:
        holm = _holm()
    kwargs: dict[str, Any] = {
        "preregistration": _prereg(),
        "completeness": _completeness(),
        "holm_result": holm,
        "decision": _decision(holm),
        "evaluation_records": _records(),
        "solver_provenance": _solver(),
        "checkpoint_values": (-0.5, 0.5),
    }
    kwargs.update(overrides)
    return build_result_record(**kwargs)


# ---------------------------------------------------------------------------
# 1-2. Construction and immutability
# ---------------------------------------------------------------------------


def test_valid_record_construction() -> None:
    record = _build()
    assert record.outcome == DecisionOutcome.GO.value
    assert record.alpha == 0.01
    assert record.family_size == 4
    assert len(record.hypotheses) == 4
    assert record.completeness_status == "COMPLETE"
    assert record.n_included_tasks == 2
    assert record.identity != ""
    assert len(record.identity) == 64
    assert record.verify_identity()


def test_record_is_frozen() -> None:
    record = _build()
    # The attribute name is held in a variable so this stays a runtime immutability
    # check rather than a static assignment needing a type-checker suppression.
    outcome_field = "outcome"
    with pytest.raises(FrozenInstanceError):
        setattr(record, outcome_field, "NO_GO")
    manifest_field = "manifest_hash"
    with pytest.raises(FrozenInstanceError):
        setattr(record.provenance, manifest_field, "x")


# ---------------------------------------------------------------------------
# 3-5, 17. Canonical identity over the complete artifact
# ---------------------------------------------------------------------------


def test_identity_is_deterministic_across_repeated_construction() -> None:
    assert _build().identity == _build().identity
    assert _build() == _build()


def test_identity_excludes_only_the_identity_field() -> None:
    record = _build()
    payload = record.to_dict()
    assert "identity" in payload
    payload.pop("identity")
    assert record.identity == compute_content_hash(payload)
    # A tampered stored identity does not change the recomputed one.
    tampered = replace(record, identity="0" * 64)
    assert tampered.compute_identity() == record.identity
    assert not tampered.verify_identity()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("outcome", "NO_GO"),
        ("reason", "different reason"),
        ("alpha", 0.05),
        ("family_size", 2),
        ("completeness_status", "VOID_EMPTY"),
        ("n_included_tasks", 99),
        ("included_task_identities", ()),
        ("excluded_task_identities", (_hex("t9"),)),
    ],
)
def test_changing_any_top_level_field_changes_identity(field: str, value: Any) -> None:
    base = _build()
    mutated = replace(base, **{field: value})
    assert mutated.compute_identity() != base.identity


def test_changing_a_p_value_changes_identity() -> None:
    base = _build()
    other = _build(holm_result=_holm((0.0001, 0.0002, 0.0003, 0.009)))
    assert other.identity != base.identity


def test_changing_a_provenance_field_changes_identity() -> None:
    base = _build()
    mutated_provenance = replace(base.provenance, manifest_hash=_hex("other-manifest"))
    mutated = replace(base, provenance=mutated_provenance)
    assert mutated.compute_identity() != base.identity


def test_changing_the_solver_provenance_changes_identity() -> None:
    base = _build()
    other = _build(solver_provenance=replace(_solver(), numpy_version="9.9.9"))
    assert other.identity != base.identity


def test_serialization_is_the_canonical_form() -> None:
    record = _build()
    serialized = serialize_result_record(record)
    assert serialized.startswith("{")
    assert ", " not in serialized  # tight separators
    assert '"identity":' in serialized


# ---------------------------------------------------------------------------
# 6. Deterministic, sorted, unique evaluation_identity extraction
# ---------------------------------------------------------------------------


def test_evaluation_identities_are_unique_sorted_and_deterministic() -> None:
    identities = extract_evaluation_identities(_records())
    assert identities == tuple(sorted({_hex("eval-a"), _hex("eval-b")}))
    assert len(identities) == 2  # the duplicate collapsed
    assert identities == extract_evaluation_identities(list(reversed(_records())))


def test_evaluation_identities_land_in_provenance() -> None:
    record = _build()
    assert record.provenance.evaluation_identities == extract_evaluation_identities(_records())


def test_empty_record_set_yields_an_empty_identity_set() -> None:
    assert extract_evaluation_identities([]) == ()


# ---------------------------------------------------------------------------
# 7-8. Provenance and upstream values retained exactly
# ---------------------------------------------------------------------------


def test_provenance_fields_are_retained() -> None:
    prereg = _prereg()
    record = _build(preregistration=prereg)
    provenance = record.provenance
    assert provenance.preregistration_identity == prereg.identity
    assert provenance.checkpoint_identities == tuple(prereg.checkpoint_identities)
    assert provenance.manifest_hash == prereg.manifest_hash
    assert provenance.eval_seed == prereg.eval_seed
    assert provenance.implementation_version == __version__
    assert provenance.statistical_library == STATISTICAL_LIBRARY == "statsmodels"
    assert provenance.statistical_library_version == "0.15.0"
    assert provenance.numpy_version == "2.5.3"
    assert provenance.checkpoint_values == (-0.5, 0.5)
    assert dict(provenance.solver_configuration)["maxiter"] == "100"
    assert dict(provenance.solver_configuration)["cov_type"] == "robust"
    assert dict(provenance.thread_configuration)["OMP_NUM_THREADS"] == "1"


def test_p_values_and_thresholds_are_retained_exactly() -> None:
    holm = _holm()
    record = _build(holm_result=holm)
    for stored, upstream in zip(record.hypotheses, holm.decisions, strict=True):
        assert stored.label == upstream.label
        assert stored.p_value == upstream.p_value
        assert stored.rank == upstream.rank
        assert stored.threshold == upstream.threshold
        assert stored.rejected == upstream.rejected
    assert {h.label for h in record.hypotheses} == set(KGT1_HYPOTHESIS_LABELS)


def test_k1_path_records_no_statistical_library() -> None:
    record = _build(solver_provenance=None, checkpoint_values=())
    assert record.provenance.statistical_library is None
    assert record.provenance.statistical_library_version is None
    assert record.provenance.numpy_version is None
    assert record.provenance.solver_configuration == ()
    assert record.provenance.thread_configuration == ()
    assert record.verify_identity()


# ---------------------------------------------------------------------------
# 9. GO / NO_GO / VOID are representable
# ---------------------------------------------------------------------------


def test_go_is_representable() -> None:
    assert _build().outcome == "GO"


def test_no_go_is_representable() -> None:
    holm = _holm((0.0001, 0.0002, 0.0003, 0.02))
    record = _build(holm_result=holm)
    assert record.outcome == "NO_GO"
    assert record.verify_identity()


# --- VOID: no Holm family, no fabricated statistics (spec 3.5.1 / 3.5.11) ---


def _void_completeness(
    status: CompletenessStatus = CompletenessStatus.VOID_EMPTY,
    excluded: tuple[str, ...] = (),
) -> CompletenessResult:
    return CompletenessResult(status, (), excluded, 0)


def _build_void(
    *,
    status: CompletenessStatus = CompletenessStatus.VOID_EMPTY,
    excluded: tuple[str, ...] = (),
    preregistration: PreRegistration | None = None,
) -> AnalysisResultRecord:
    """A VOID record built with no HolmResult at all — never a fabricated one."""
    return build_result_record(
        preregistration=_prereg() if preregistration is None else preregistration,
        completeness=_void_completeness(status, excluded),
        decision=decide_kgt1(completeness_status=status),
        evaluation_records=_records(),
    )


def test_void_record_is_built_without_a_holm_result() -> None:
    record = _build_void(excluded=(_hex("t1"), _hex("t2")))
    assert record.outcome == "VOID"
    assert record.hypotheses == ()
    assert record.family_size == 0
    assert record.n_included_tasks == 0
    assert record.included_task_identities == ()
    assert record.excluded_task_identities == (_hex("t1"), _hex("t2"))
    assert record.completeness_status == "VOID_EMPTY"
    assert record.verify_identity()


def test_void_record_fabricates_no_p_value_or_threshold() -> None:
    record = _build_void()
    assert record.hypotheses == ()
    assert record.family_size == 0
    # to_dict() preserves the frozen tuple representation; canonical JSON renders it as
    # an empty array. Neither carries a p-value or a per-test threshold.
    assert record.to_dict()["hypotheses"] == ()
    serialized = serialize_result_record(record)
    assert '"hypotheses":[]' in serialized
    assert '"p_value"' not in serialized
    assert '"threshold"' not in serialized
    # The pre-registered family-wise level is design provenance, declared before the run;
    # it is not a computed per-test threshold.
    assert record.alpha == _prereg().alpha == 0.01


def test_void_record_identity_is_deterministic() -> None:
    assert _build_void().identity == _build_void().identity
    assert _build_void() == _build_void()


def test_void_identity_changes_with_meaningful_content() -> None:
    base = _build_void(excluded=(_hex("t1"),))
    more_excluded = _build_void(excluded=(_hex("t1"), _hex("t2")))
    assert more_excluded.identity != base.identity
    global_incomplete = _build_void(status=CompletenessStatus.VOID_GLOBAL_INCOMPLETE)
    assert global_incomplete.completeness_status == "VOID_GLOBAL_INCOMPLETE"
    assert global_incomplete.identity != base.identity


def test_void_identity_differs_from_a_decided_record() -> None:
    assert _build_void().identity != _build().identity


def test_void_refuses_a_supplied_holm_family() -> None:
    with pytest.raises(ResultRecordError, match="no Holm"):
        build_result_record(
            preregistration=_prereg(),
            completeness=_void_completeness(),
            decision=decide_kgt1(completeness_status=CompletenessStatus.VOID_EMPTY),
            evaluation_records=_records(),
            holm_result=_holm(),
        )


@pytest.mark.parametrize("p_values", [_P_VALUES, (0.0001, 0.0002, 0.0003, 0.02)])
def test_decided_outcomes_require_a_holm_result(p_values: tuple[float, ...]) -> None:
    decision = _decision(_holm(p_values))
    assert decision.outcome is not DecisionOutcome.VOID
    with pytest.raises(ResultRecordError, match="required"):
        build_result_record(
            preregistration=_prereg(),
            completeness=_completeness(),
            decision=decision,
            evaluation_records=_records(),
        )


def test_void_record_persists_with_write_once_semantics(tmp_path: Path) -> None:
    record = _build_void()
    target = write_result_record(record, tmp_path)
    assert target == tmp_path / f"{record.identity}.json"
    assert list(tmp_path.iterdir()) == [target]
    with pytest.raises(FileExistsError):
        write_result_record(record, tmp_path)


# ---------------------------------------------------------------------------
# 10-13. Write-once persistence under an explicit results_dir
# ---------------------------------------------------------------------------


def test_persistence_writes_identity_named_file(tmp_path: Path) -> None:
    record = _build()
    target = write_result_record(record, tmp_path)
    assert target == tmp_path / f"{record.identity}.json"
    assert target.exists()
    assert target.read_text(encoding="utf-8").rstrip("\n") == serialize_result_record(record)


def test_persistence_creates_missing_directories(tmp_path: Path) -> None:
    nested = tmp_path / "results" / "m9"
    record = _build()
    target = write_result_record(record, nested)
    assert target.parent == nested


def test_existing_file_raises_file_exists_error(tmp_path: Path) -> None:
    record = _build()
    write_result_record(record, tmp_path)
    with pytest.raises(FileExistsError):
        write_result_record(record, tmp_path)


def test_persistence_does_not_overwrite(tmp_path: Path) -> None:
    record = _build()
    target = write_result_record(record, tmp_path)
    original = target.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_result_record(record, tmp_path)
    assert target.read_text(encoding="utf-8") == original


def test_results_dir_is_supplied_explicitly(tmp_path: Path) -> None:
    record = _build()
    first = write_result_record(record, tmp_path / "a")
    second = write_result_record(record, str(tmp_path / "b"))
    assert first.parent != second.parent
    assert first.name == second.name


def test_tampered_record_is_refused_before_writing(tmp_path: Path) -> None:
    tampered = replace(_build(), identity="0" * 64)
    with pytest.raises(ResultRecordError, match="does not match"):
        write_result_record(tampered, tmp_path)
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# 14-16. Boundary: no config, no memory, no experience surfaces
# ---------------------------------------------------------------------------


def _imports() -> set[str]:
    source = Path(record_mod.__file__).read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def _imported_names() -> set[str]:
    """Every name bound by an import in result_record.py — the real import surface."""
    source = Path(record_mod.__file__).read_text(encoding="utf-8")
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import | ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def test_result_record_imports_no_memory_or_episode_writer() -> None:
    imported = _imports()
    for forbidden in ("velith.memory", "velith.episodes.writer"):
        assert forbidden not in imported, f"result_record must not import {forbidden}"


def test_result_record_imports_no_experience_or_sink_surface() -> None:
    imported = _imports()
    forbidden = (
        "velith.episodes.store",
        "velith.episodes.index",
        "velith.evaluation.sink",
        "velith.evaluation.runner",
        "velith.retrieval.memory",
        "velith.arms.memory_view",
    )
    overlap = imported & set(forbidden)
    assert not overlap, f"forbidden imports: {overlap}"


def test_result_record_adds_no_configuration_plumbing() -> None:
    # Import-level check only: a source-text scan would false-positive on this module's
    # own docstring, which states that it reads no Settings.
    imported = _imports()
    assert "velith.core.config" not in imported
    assert not any(name.endswith(".config") for name in imported)
    source = Path(record_mod.__file__).read_text(encoding="utf-8")
    assert "get_settings" not in source


def test_result_record_defines_no_statistical_surface() -> None:
    public = {name for name in dir(record_mod) if not name.startswith("_")}
    for forbidden in (
        "holm_bonferroni",
        "decide_k1",
        "decide_kgt1",
        "compute_emm",
        "compute_wald",
        "compute_trend",
        "fit_gee",
        "mcnemar_test",
        "classify_failure",
    ):
        assert forbidden not in public
    # Checked on the real import surface, never on source text: a text scan matches this
    # module's own docstring, which names the write surface it exists to stay away from.
    assert "GuardedEpisodeWriter" not in _imported_names()
    assert "GuardedEpisodeWriter" not in public
