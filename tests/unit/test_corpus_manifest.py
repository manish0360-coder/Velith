"""Unit tests for the content-addressed corpus partition manifest (M4-C2).

Scope: the manifest in isolation (M4_SPEC §3.1) — hash stability, hash changes iff
the split changes, content-addressed identity (relabeling does not move a task), and
each task resolving to exactly one partition. Pure value object; no filesystem.
"""

from __future__ import annotations

import pytest

from velith.corpus.manifest import (
    CorpusManifest,
    CorpusManifestError,
    Partition,
    PartitionEntry,
    task_identity,
)


def _entries() -> list[PartitionEntry]:
    return [
        PartitionEntry(label="task-a", material="alpha", partition=Partition.AVAILABLE),
        PartitionEntry(label="task-b", material="beta", partition=Partition.HELD_OUT),
        PartitionEntry(label="task-c", material="gamma", partition=Partition.AVAILABLE),
    ]


def test_manifest_hash_is_stable_across_repeated_builds() -> None:
    first = CorpusManifest.from_entries(_entries())
    second = CorpusManifest.from_entries(_entries())
    assert first.manifest_hash == second.manifest_hash


def test_manifest_hash_is_independent_of_entry_order() -> None:
    entries = _entries()
    forward = CorpusManifest.from_entries(entries)
    backward = CorpusManifest.from_entries(list(reversed(entries)))
    assert forward.manifest_hash == backward.manifest_hash


def test_manifest_hash_changes_iff_split_changes() -> None:
    base = CorpusManifest.from_entries(_entries())

    # Move one task to the other partition -> different hash.
    moved = _entries()
    moved[1] = PartitionEntry(label="task-b", material="beta", partition=Partition.AVAILABLE)
    assert CorpusManifest.from_entries(moved).manifest_hash != base.manifest_hash

    # Add a task -> different hash.
    added = [
        *_entries(),
        PartitionEntry(label="task-d", material="delta", partition=Partition.HELD_OUT),
    ]
    assert CorpusManifest.from_entries(added).manifest_hash != base.manifest_hash


def test_identity_is_content_addressed_relabeling_does_not_move_a_task() -> None:
    # Same material, different display label -> same content-addressed identity.
    assert task_identity("beta") == task_identity("beta")
    relabeled = [
        PartitionEntry(label="renamed-b", material="beta", partition=Partition.HELD_OUT),
        PartitionEntry(label="task-a", material="alpha", partition=Partition.AVAILABLE),
    ]
    manifest = CorpusManifest.from_entries(relabeled)
    # The held-out task remains held-out under its identity, regardless of label.
    assert manifest.partition_of(task_identity("beta")) is Partition.HELD_OUT


def test_relabeling_collapses_to_one_identity() -> None:
    # Two entries, same material, different labels, same partition -> one identity.
    entries = [
        PartitionEntry(label="b1", material="beta", partition=Partition.HELD_OUT),
        PartitionEntry(label="b2", material="beta", partition=Partition.HELD_OUT),
    ]
    manifest = CorpusManifest.from_entries(entries)
    assert manifest.identities() == {task_identity("beta")}


def test_each_task_resolves_to_exactly_one_partition() -> None:
    manifest = CorpusManifest.from_entries(_entries())
    assert manifest.partition_of(task_identity("alpha")) is Partition.AVAILABLE
    assert manifest.partition_of(task_identity("beta")) is Partition.HELD_OUT
    assert manifest.partition_of("unknown-identity") is None


def test_conflicting_partition_assignment_raises() -> None:
    conflict = [
        PartitionEntry(label="b", material="beta", partition=Partition.AVAILABLE),
        PartitionEntry(label="b-again", material="beta", partition=Partition.HELD_OUT),
    ]
    with pytest.raises(CorpusManifestError):
        CorpusManifest.from_entries(conflict)


def test_to_dict_from_dict_round_trip_preserves_hash() -> None:
    manifest = CorpusManifest.from_entries(_entries())
    rebuilt = CorpusManifest.from_dict(manifest.to_dict())
    assert rebuilt.manifest_hash == manifest.manifest_hash
    assert rebuilt.to_dict() == manifest.to_dict()
