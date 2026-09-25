"""The held-out VerificationManifest (D29; M8 evaluation identity v2 §3).

The VerificationManifest ``VM(Π)`` maps each task of the **held-out evaluation
population** ``Π`` (the tasks of the :class:`HeldOutEvaluationSet` under evaluation) to
its TaskSpec digest, carried in ``CorpusTask.handle`` (D28 Option D). It is held-out-only:
available-partition tasks are never included, and available-task TaskSpec lineage remains
deferred (not solved by this module).

``verification_manifest_hash`` is the SHA-256 of the canonical serialization of the
mapping. It reuses the repository's existing canonical rule
(:func:`velith.episodes.episode.compute_content_hash`: sorted keys, tight separators,
``ensure_ascii=False``, UTF-8), so no new serialization format exists.

Construction fails closed with :class:`VerificationManifestError` on an empty population,
any duplicate task identity (whether its digests agree or differ), a digest that is not
64 lowercase hex characters, a TaskSpec absent from the store, or stored bytes that do not
re-hash to their digest. The TaskSpec schema is not interpreted (it is undecided, D26).
This module computes identity only: no statistic, no verdict.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, Protocol

from velith.corpus.loader import CorpusTask
from velith.episodes.episode import compute_content_hash

#: A TaskSpec digest is a lowercase SHA-256 hex digest (64 chars).
_SHA256_HEX: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


class VerificationManifestError(Exception):
    """Raised when a VerificationManifest cannot be constructed (fail closed)."""


class TaskSpecStore(Protocol):
    """Structural interface for a content-addressed TaskSpec byte store."""

    def read(self, digest: str) -> bytes | None:
        """Return the bytes stored under ``digest``, or ``None`` if absent."""
        ...


@dataclass(frozen=True)
class VerificationManifest:
    """An immutable ``task_identity -> TaskSpec digest`` mapping over a held-out population.

    ``entries`` is sorted by task identity; the hash does not depend on population order.
    """

    entries: tuple[tuple[str, str], ...]

    def as_mapping(self) -> dict[str, str]:
        """The manifest as a plain ``task_identity -> TaskSpec digest`` mapping."""
        return dict(self.entries)

    @property
    def verification_manifest_hash(self) -> str:
        """SHA-256 of the canonical serialization of the mapping (M8 identity v2 §3.2)."""
        return compute_content_hash(self.as_mapping())


def build_verification_manifest(
    population: Iterable[CorpusTask], store: TaskSpecStore
) -> VerificationManifest:
    """Construct ``VM(Π)`` for a held-out population, failing closed (§3.3)."""
    mapping: dict[str, str] = {}
    for task in population:
        identity = task.identity
        digest = task.handle
        if identity in mapping:
            agreement = "the same" if mapping[identity] == digest else "a different"
            raise VerificationManifestError(
                f"duplicate task identity {identity} in the held-out population "
                f"(with {agreement} TaskSpec digest)"
            )
        if not _SHA256_HEX.match(digest):
            raise VerificationManifestError(
                f"task {identity} carries an invalid TaskSpec digest: {digest!r}"
            )
        content = store.read(digest)
        if content is None:
            raise VerificationManifestError(f"missing TaskSpec {digest} for task {identity}")
        if hashlib.sha256(content).hexdigest() != digest:
            raise VerificationManifestError(
                f"stored TaskSpec content does not re-hash to its digest {digest} "
                f"(task {identity})"
            )
        mapping[identity] = digest
    if not mapping:
        raise VerificationManifestError(
            "empty held-out population: an evaluation over zero tasks has no "
            "verification contract"
        )
    return VerificationManifest(entries=tuple(sorted(mapping.items())))
