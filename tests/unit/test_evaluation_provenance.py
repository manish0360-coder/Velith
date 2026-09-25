"""Unit tests for the M8 evaluation provenance / identity (M8-C7).

Scope (M8_SPEC §3.5): the content-addressed evaluation identity in isolation — it is
stable and content-addressed, changes iff any component changes, and binds results to a
single checkpoint and split. The runner (C8) and the permanent invariant (C9) are not
under test here.
"""

from __future__ import annotations

import dataclasses

import pytest

from velith.evaluation.provenance import (
    IDENTITY_VERSION,
    EvaluationProvenance,
    EvaluationProvenanceError,
)

_VM_HASH = "a" * 64

#: The ten identity-v2 components and a distinct replacement value for each (D29).
_COMPONENT_CHANGES = {
    "identity_version": "m8-evaluation-identity-v1",
    "verification_manifest_hash": "b" * 64,
    "checkpoint_identity": "other-checkpoint",
    "manifest_hash": "other-manifest",
    "arm": "A2",
    "base_model": "other-model",
    "eval_seed": 999,
    "max_tasks": 7,
    "max_attempts_per_task": 3,
    "max_tokens": 50000,
}


def _provenance() -> EvaluationProvenance:
    return EvaluationProvenance(
        checkpoint_identity="ckpt-1",
        manifest_hash="manifest-1",
        arm="A1",
        base_model="qwen2.5-coder",
        eval_seed=0,
        max_tasks=0,
        max_attempts_per_task=1,
        max_tokens=0,
        verification_manifest_hash=_VM_HASH,
    )


def test_identity_is_content_addressed_and_stable() -> None:
    """The identity is a deterministic SHA-256 hex over the components (§3.5)."""
    identity = _provenance().identity
    assert isinstance(identity, str)
    assert len(identity) == 64
    assert int(identity, 16) >= 0  # valid hex digest
    # Stable across independent, equal instances and repeat calls.
    assert _provenance().identity == _provenance().identity
    assert _provenance().identity == identity


def test_all_components_are_present() -> None:
    """The identity records exactly the required components (§3.5)."""
    assert set(_provenance().to_dict()) == set(_COMPONENT_CHANGES)


@pytest.mark.parametrize(
    "changed",
    [
        dataclasses.replace(_provenance(), checkpoint_identity="other-checkpoint"),
        dataclasses.replace(_provenance(), manifest_hash="other-manifest"),
        dataclasses.replace(_provenance(), arm="A2"),
        dataclasses.replace(_provenance(), base_model="other-model"),
        dataclasses.replace(_provenance(), eval_seed=999),
        dataclasses.replace(_provenance(), max_tasks=7),
        dataclasses.replace(_provenance(), max_attempts_per_task=3),
        dataclasses.replace(_provenance(), max_tokens=50000),
        dataclasses.replace(_provenance(), verification_manifest_hash="b" * 64),
        dataclasses.replace(_provenance(), identity_version="m8-evaluation-identity-v1"),
    ],
)
def test_identity_changes_when_any_component_changes(changed: EvaluationProvenance) -> None:
    """Any change to any component yields a new identity (§3.5)."""
    assert changed.identity != _provenance().identity


def test_identity_is_unchanged_by_equal_components() -> None:
    """Same components -> same identity, regardless of construction (§3.5)."""
    a = _provenance()
    b = dataclasses.replace(_provenance())
    assert a == b
    assert a.identity == b.identity


def test_identity_binds_results_to_one_checkpoint_and_split() -> None:
    """A different checkpoint or manifest hash is a different evaluation (§3.5)."""
    base = _provenance()
    other_checkpoint = dataclasses.replace(base, checkpoint_identity="ckpt-2")
    other_split = dataclasses.replace(base, manifest_hash="manifest-2")
    assert other_checkpoint.identity != base.identity
    assert other_split.identity != base.identity


def test_identity_v2_payload_has_exactly_ten_keys_and_the_v2_version() -> None:
    """The v2 payload is exactly the ten D29 keys; classifier identity is not one."""
    payload = _provenance().to_dict()
    assert len(payload) == 10
    assert payload["identity_version"] == IDENTITY_VERSION == "m8-evaluation-identity-v2"
    assert payload["verification_manifest_hash"] == _VM_HASH
    assert not any("classifier" in key for key in payload)


@pytest.mark.parametrize("bad", ["", "not-a-hash", "A" * 64, "a" * 63])
def test_non_concrete_verification_manifest_hash_is_rejected(bad: str) -> None:
    """A missing or malformed verification manifest hash fails closed (D29 case 13)."""
    with pytest.raises(EvaluationProvenanceError):
        dataclasses.replace(_provenance(), verification_manifest_hash=bad)
