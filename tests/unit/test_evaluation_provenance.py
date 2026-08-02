"""Unit tests for the M8 evaluation provenance / identity (M8-C7).

Scope (M8_SPEC §3.5): the content-addressed evaluation identity in isolation — it is
stable and content-addressed, changes iff any component changes, and binds results to a
single checkpoint and split. The runner (C8) and the permanent invariant (C9) are not
under test here.
"""

from __future__ import annotations

import dataclasses

import pytest

from velith.evaluation.provenance import EvaluationProvenance

#: The eight identity components and a distinct replacement value for each.
_COMPONENT_CHANGES = {
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
