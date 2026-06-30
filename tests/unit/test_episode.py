"""Unit tests for the Episode schema and canonical content hash (C1).

These tests pin the C1 Definition of Done and rollback conditions (M1 handoff
§5/§6): every §9.1 field is present, the hash is stable across identical content
and across machines, it *excludes* the volatile timing fields (protecting D16.1),
it *changes* when content changes, and tampering is detectable on read (I2).
"""

from __future__ import annotations

from typing import Any

import pytest

from velith.episodes.episode import (
    DEFAULT_ARM,
    HASH_BOUNDARY_FIELDS,
    HASH_EXCLUDED_FIELDS,
    Episode,
    VerdictState,
    compute_content_hash,
)


def _base_kwargs() -> dict[str, Any]:
    """A complete, valid set of build() arguments for one episode."""
    kwargs: dict[str, Any] = {
        "task_id": "fix-bug-001",
        "seed": 0,
        "model": "qwen2.5-coder",
        "model_version": "qwen2.5-coder:7b@sha256-abc",
        "prompt": "Fix the failing test in module x.",
        "patch": "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-bad\n+good\n",
        "verdict_state": VerdictState.PASSED,
        "verdict_output": "1 passed in 0.01s",
        "prompt_tokens": 12,
        "completion_tokens": 34,
        "latency_seconds": 1.5,
        "verify_seconds": 2.5,
        "velith_version": "0.0.0+gabc123",
        "timestamp": "2026-06-24T00:00:00+00:00",
    }
    return kwargs


def test_build_produces_a_verifiable_episode() -> None:
    """build() fills every field, sets a non-empty hash, and verify_hash() holds."""
    episode = Episode.build(**_base_kwargs())
    assert episode.content_hash  # non-empty
    assert episode.verify_hash()
    assert episode.arm == DEFAULT_ARM
    assert episode.secondary_passed is None  # M1 placeholder; M2 populates it


def test_schema_fields_partition_into_boundary_and_excluded() -> None:
    """Every §9.1 field is either hashed or explicitly excluded — none dropped (RK12)."""
    all_fields = set(Episode.model_fields)
    boundary = set(HASH_BOUNDARY_FIELDS)
    excluded = set(HASH_EXCLUDED_FIELDS)
    assert boundary.isdisjoint(excluded), "a field cannot be both hashed and excluded"
    assert all_fields == boundary | excluded, "schema and hash boundary must agree exactly"


def test_verdict_taxonomy_is_the_closed_set() -> None:
    """The verdict states are exactly the §10 set (D16.7)."""
    assert {state.value for state in VerdictState} == {
        "PASSED",
        "FAILED",
        "PATCH_APPLY_FAILED",
        "NO_PATCH",
        "INFRA_ERROR",
    }


def test_identical_content_hashes_identically() -> None:
    """Two episodes built from identical content carry the identical hash."""
    first = Episode.build(**_base_kwargs())
    second = Episode.build(**_base_kwargs())
    assert first.content_hash == second.content_hash


def test_hash_excludes_volatile_fields() -> None:
    """Differing only in timestamp/latency/verify must NOT change the hash (D16.1)."""
    baseline = Episode.build(**_base_kwargs())
    volatile = _base_kwargs()
    volatile["timestamp"] = "2099-12-31T23:59:59+00:00"
    volatile["latency_seconds"] = 999.0
    volatile["verify_seconds"] = 888.0
    volatile_variant = Episode.build(**volatile)
    assert baseline.content_hash == volatile_variant.content_hash


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("seed", 1),
        ("patch", "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-bad\n+other\n"),
        ("verdict_state", VerdictState.FAILED),
        ("prompt", "A different prompt."),
        ("prompt_tokens", 99),
        ("velith_version", "0.0.0+gdifferent"),
    ],
)
def test_hash_changes_when_a_content_field_changes(field: str, value: Any) -> None:
    """Any change to a hashed content field yields a different hash (sensitivity)."""
    baseline = Episode.build(**_base_kwargs())
    changed = _base_kwargs()
    changed[field] = value
    variant = Episode.build(**changed)
    assert baseline.content_hash != variant.content_hash


def test_tampering_is_detected_on_read() -> None:
    """Mutating a content field without recomputing the hash fails verification (I2)."""
    episode = Episode.build(**_base_kwargs())
    assert episode.verify_hash()
    tampered = episode.model_copy(update={"patch": "an injected, unverified patch"})
    assert not tampered.verify_hash()


def test_canonical_hash_is_insertion_order_independent() -> None:
    """sort_keys makes the hash independent of dict insertion order (cross-machine stability)."""
    forward = {"task_id": "t", "seed": 0, "arm": "baseline"}
    reordered = {"arm": "baseline", "seed": 0, "task_id": "t"}
    assert compute_content_hash(forward) == compute_content_hash(reordered)


def test_flaky_is_provenance_and_excluded_from_the_hash() -> None:
    """A varying `flaky` must not change the content hash (M2 R5/D21, RK4)."""
    baseline = Episode.build(**_base_kwargs())
    flaky_kwargs = _base_kwargs()
    flaky_kwargs["flaky"] = True
    flaky_variant = Episode.build(**flaky_kwargs)
    assert baseline.flaky is False
    assert flaky_variant.flaky is True
    assert baseline.content_hash == flaky_variant.content_hash
