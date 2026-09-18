"""Unit tests for the M9 pre-registration record (M9-C2 / P1).

Deterministic, synthetic fixtures only — no real M8 held-out data or outcomes. These pin
the frozen P1 contract: content-addressed identity stability, exact concrete checkpoint
binding, rejection of non-concrete bindings, the declared frozen plan fields (incl. OED-2
A0 handling and OED-7 n=0 VOID), immutability, and deterministic serialization.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from velith.analysis import preregistration as prereg
from velith.analysis.preregistration import PreRegistration, PreRegistrationError


def _cid(seed: str) -> str:
    """A synthetic but well-formed content-addressed identity (SHA-256 hex)."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _build(**overrides: object) -> PreRegistration:
    kwargs: dict[str, object] = {
        "manifest_hash": _cid("manifest"),
        "checkpoint_identities": (_cid("cp1"), _cid("cp2"), _cid("cp3")),
        "base_model": "qwen2.5-coder",
        "eval_seed": 0,
        "max_tasks": 0,
        "max_attempts_per_task": 1,
        "max_tokens": 0,
    }
    kwargs.update(overrides)
    return PreRegistration.build(**kwargs)  # type: ignore[arg-type]


def test_encoding_is_deterministic() -> None:
    assert _build().identity == _build().identity


def test_identity_is_content_addressed_and_stable() -> None:
    pr = _build()
    assert pr.verify_identity()
    assert pr.identity == pr.compute_identity()
    assert len(pr.identity) == 64


def test_exact_checkpoint_binding_preserves_order() -> None:
    ordered = (_cid("cp1"), _cid("cp2"), _cid("cp3"))
    pr = _build(checkpoint_identities=ordered)
    assert pr.checkpoint_identities == ordered


def test_checkpoint_order_change_yields_new_identity() -> None:
    a = _build(checkpoint_identities=(_cid("cp1"), _cid("cp2")))
    b = _build(checkpoint_identities=(_cid("cp2"), _cid("cp1")))
    assert a.identity != b.identity


def test_checkpoint_membership_change_yields_new_identity() -> None:
    a = _build(checkpoint_identities=(_cid("cp1"), _cid("cp2")))
    b = _build(checkpoint_identities=(_cid("cp1"), _cid("cp2"), _cid("cp3")))
    assert a.identity != b.identity


def test_non_concrete_checkpoint_is_rejected() -> None:
    for bad in ("final", "checkpoint_3", "3", "LATEST", _cid("cp1")[:-1]):
        with pytest.raises(ValidationError):
            _build(checkpoint_identities=(bad,))


def test_empty_checkpoint_schedule_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _build(checkpoint_identities=())


def test_non_concrete_manifest_hash_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _build(manifest_hash="not-a-hash")


def test_required_plan_fields_are_frozen_values() -> None:
    pr = _build()
    assert pr.spec_version == "m9-spec-frozen-oed7"
    assert pr.primary_endpoint == "binary_passed"
    assert pr.alpha == 0.01
    assert pr.statistic_identifier == prereg.STATISTIC_IDENTIFIER
    assert pr.decision_rule == "holm_all_reject_go_else_nogo"
    assert pr.missing_data_rule == "complete_case_exclusion"
    assert pr.global_incomplete_disposition == "VOID"
    assert pr.k1_family_size == 2
    assert pr.kgt1_family_size == 4
    assert pr.arms == ("A0", "A1", "A2")


def test_oed7_empty_dataset_disposition_is_void() -> None:
    assert _build().empty_dataset_disposition == "VOID"


def test_oed2_a0_treatment_is_represented() -> None:
    pr = _build()
    assert pr.a0_time_invariant is True
    assert pr.a0_checkpoint_id_c == 0


def test_statistic_identifier_closed_set_enforced() -> None:
    with pytest.raises(PreRegistrationError):
        _build(statistic_identifier="some_other_test")


def test_alpha_is_enforced_to_frozen_value() -> None:
    with pytest.raises(PreRegistrationError):
        _build(alpha=0.05)


def test_record_is_immutable() -> None:
    pr = _build()
    with pytest.raises(ValidationError):
        pr.alpha = 0.05  # type: ignore[misc]


def test_serialization_is_deterministic_and_round_trips() -> None:
    pr = _build()
    first = pr.model_dump_json()
    assert first == _build().model_dump_json()
    restored = PreRegistration.model_validate_json(first)
    assert restored == pr
    assert restored.verify_identity()


def test_declared_plan_lives_in_record_not_core_settings() -> None:
    # Corrected M9-C2 boundary: the declared statistic identifier and decision threshold
    # (M9_SPEC §5) are carried by the immutable PreRegistration record, never by core
    # Settings — preserving the M8 invariant that Settings holds no statistic/threshold/
    # decision knob (M8_SPEC §5).
    from velith.core.config import Settings

    forbidden = ("statistic", "threshold", "decision", "pvalue", "p_value", "effect", "go_no_go")
    for name in Settings.model_fields:
        assert not any(token in name for token in forbidden), name
    assert "prereg_path" in Settings.model_fields
    record = _build()
    assert record.statistic_identifier == prereg.STATISTIC_IDENTIFIER
    assert record.alpha == 0.01


def test_analysis_p1_does_not_import_heldout_surfaces() -> None:
    # Sealed-from-results: the P1 modules must not reference the evaluation sink/records
    # or the episode store (no path to held-out outcomes / the experience log).
    import velith.analysis.prereg_store as store_mod

    sources = Path(prereg.__file__).read_text(encoding="utf-8")
    sources += Path(store_mod.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "evaluation.sink",
        "evaluation.record",
        "evaluation.runner",
        "episodes.store",
        "EvaluationSink",
        "EvaluationRecord",
        "GuardedEpisodeWriter",
    ):
        assert forbidden not in sources, f"P1 must not reference held-out surface: {forbidden}"
