"""Content-addressed corpus partition manifest (M4-C2).

The manifest represents the corpus partition assignment — each **content-addressed
task identity** mapped to exactly one partition, ``available`` or ``held_out`` — and
exposes a **stable content hash** over that assignment so the split is frozen and
reproducible (M4_SPEC §3.1, D8). Identity is content-addressed: it is a hash of a
task's opaque identity *material* and is independent of any mutable display *label*,
so relabeling a task cannot move it across the partition (M4_SPEC §3.3).

This module is domain-neutral (D9, D22): ``material`` is opaque text; the manifest
never inspects or interprets it. It is a pure value object — no filesystem, no model,
and no coupling to the frozen M0-M3 episode substrate.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum


class Partition(str, Enum):
    """The closed set of corpus partitions (M4_SPEC §3.1)."""

    AVAILABLE = "available"
    HELD_OUT = "held_out"


class CorpusManifestError(Exception):
    """Raised when a partition assignment is inconsistent.

    For example, one task identity assigned to two partitions. A loud, typed
    failure — never silent (each task must resolve to exactly one partition).
    """


def task_identity(material: str) -> str:
    """Return the content-addressed identity of a task from its opaque *material*.

    A SHA-256 over the identity material only. The material is domain-neutral and
    opaque (D9/D22); by contract it excludes any mutable display label, so that
    relabeling a task cannot change its identity (M4_SPEC §3.3).
    """
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PartitionEntry:
    """A declared partition assignment for one task.

    ``label`` is the mutable display name and is **excluded** from identity;
    ``material`` is the opaque identity content that is hashed; ``partition`` is the
    declared assignment.
    """

    label: str
    material: str
    partition: Partition

    @property
    def identity(self) -> str:
        """The content-addressed identity of this entry (excludes ``label``)."""
        return task_identity(self.material)


class CorpusManifest:
    """An immutable, content-addressed map from task identity to partition.

    Built from declared entries; exposes a stable ``manifest_hash`` over the
    assignment (M4_SPEC §3.1). A pure value object — no filesystem, no model, and no
    coupling to the frozen episode substrate.
    """

    def __init__(self, assignment: Mapping[str, Partition]) -> None:
        self._assignment: dict[str, Partition] = dict(assignment)

    @classmethod
    def from_entries(cls, entries: Iterable[PartitionEntry]) -> CorpusManifest:
        """Build a manifest from declared entries, keyed on content-addressed identity.

        Relabeling (same ``material``, different ``label``) collapses to one identity.
        Assigning one identity to two partitions is a conflict and raises
        :class:`CorpusManifestError` — each task resolves to exactly one partition.
        """
        assignment: dict[str, Partition] = {}
        for entry in entries:
            identity = entry.identity
            existing = assignment.get(identity)
            if existing is not None and existing != entry.partition:
                raise CorpusManifestError(
                    f"task identity {identity} assigned to both "
                    f"{existing.value!r} and {entry.partition.value!r}"
                )
            assignment[identity] = entry.partition
        return cls(assignment)

    def _canonical(self) -> dict[str, str]:
        return {ident: self._assignment[ident].value for ident in sorted(self._assignment)}

    @property
    def manifest_hash(self) -> str:
        """A stable SHA-256 over the sorted identity -> partition assignment.

        Stable across repeated construction from the same assignment; changes if and
        only if the assignment changes (M4_SPEC §3.1).
        """
        canonical = json.dumps(
            self._canonical(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def partition_of(self, identity: str) -> Partition | None:
        """Return the partition for a content-addressed identity, or ``None`` if absent."""
        return self._assignment.get(identity)

    def identities(self) -> frozenset[str]:
        """The set of content-addressed identities in the manifest."""
        return frozenset(self._assignment)

    def to_dict(self) -> dict[str, str]:
        """A canonical, JSON-serializable view of the assignment (sorted by identity)."""
        return self._canonical()

    @classmethod
    def from_dict(cls, data: Mapping[str, str]) -> CorpusManifest:
        """Rebuild a manifest from a serialized assignment (inverse of :meth:`to_dict`)."""
        return cls({ident: Partition(value) for ident, value in data.items()})
