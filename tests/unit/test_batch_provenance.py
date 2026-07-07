"""Unit tests for deterministic per-task seeding and run provenance (M5-C2).

Scope: the per-task seed is a deterministic function of (task identity, batch seed)
and is invariant to execution order and retries; differing identities or batch seeds
differ; and the run provenance records the full experiment identity, including the
cost-guard budget/limits (M5_SPEC §3.5).
"""

from __future__ import annotations

from velith.batch.provenance import RunProvenance, derive_task_seed
from velith.corpus.manifest import task_identity


def test_seed_is_deterministic_and_order_retry_invariant() -> None:
    identity = task_identity("MAT-1")
    first = derive_task_seed(identity, 0)
    # Re-derivation (a retry, or the same task under a different arm, or a later run
    # regardless of order) yields the same seed — it is a pure function.
    assert derive_task_seed(identity, 0) == first
    assert derive_task_seed(identity, 0) == first


def test_seed_varies_with_identity_and_batch_seed() -> None:
    id1 = task_identity("MAT-1")
    id2 = task_identity("MAT-2")
    assert derive_task_seed(id1, 0) != derive_task_seed(id2, 0)
    assert derive_task_seed(id1, 0) != derive_task_seed(id1, 1)


def test_seed_is_non_negative_signed_64_bit() -> None:
    seed = derive_task_seed(task_identity("MAT-1"), 123)
    assert 0 <= seed < (1 << 63)


def test_run_provenance_records_all_experiment_identity_fields() -> None:
    provenance = RunProvenance(
        corpus_manifest_hash="abc123",
        arm="A0",
        base_model="qwen2.5-coder",
        batch_seed=7,
        max_tasks=100,
        max_attempts_per_task=3,
        max_tokens=50000,
    )
    assert provenance.to_dict() == {
        "corpus_manifest_hash": "abc123",
        "arm": "A0",
        "base_model": "qwen2.5-coder",
        "batch_seed": 7,
        "max_tasks": 100,
        "max_attempts_per_task": 3,
        "max_tokens": 50000,
    }


def test_run_provenance_includes_cost_guard_limits() -> None:
    provenance = RunProvenance(
        corpus_manifest_hash="h",
        arm="A0",
        base_model="m",
        batch_seed=0,
        max_tasks=10,
        max_attempts_per_task=2,
        max_tokens=1000,
    )
    recorded = provenance.to_dict()
    # The cost-guard budget/limits are part of the experiment identity (M5_SPEC §3.5).
    assert recorded["max_tasks"] == 10
    assert recorded["max_attempts_per_task"] == 2
    assert recorded["max_tokens"] == 1000
