"""Unit tests for the held-out VerificationManifest and the TaskSpec byte store (D29).

Pins ``docs/M8_IDENTITY_V2_SPEC.md`` §3: the canonical ``task_identity -> TaskSpec digest``
mapping, its SHA-256 under the repository's existing canonical rule, and every fail-closed
construction rule (§3.3). The TaskSpec schema is undecided (D26), so TaskSpecs here are
schema-free bytes. Hermetic; no real task is executed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from velith.corpus.loader import CorpusTask, load_corpus
from velith.corpus.manifest import Partition
from velith.episodes.episode import compute_content_hash
from velith.evaluation.verification_manifest import (
    VerificationManifestError,
    build_verification_manifest,
)
from velith.taskspec.store import FilesystemTaskSpecStore, TaskSpecStoreError

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _blob(tag: str) -> bytes:
    return f"velith-synthetic-taskspec:{tag}\n".encode()


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class InMemoryTaskSpecStore:
    """A content-addressed TaskSpec byte store held in memory (test double)."""

    def __init__(self, *blobs: bytes) -> None:
        self._blobs = {_digest(b): b for b in blobs}

    def read(self, digest: str) -> bytes | None:
        return self._blobs.get(digest)


def _task(material: str, handle: str) -> CorpusTask:
    return CorpusTask(
        label=material, material=material, handle=handle, partition=Partition.HELD_OUT
    )


_A, _B = _blob("a"), _blob("b")
_STORE = InMemoryTaskSpecStore(_A, _B)


def test_manifest_maps_task_identity_to_taskspec_digest() -> None:
    tasks = [_task("M-1", _digest(_A)), _task("M-2", _digest(_B))]
    manifest = build_verification_manifest(tasks, _STORE)
    assert manifest.as_mapping() == {t.identity: t.handle for t in tasks}


def test_hash_is_the_existing_canonical_content_hash() -> None:
    """No new serialization format: the hash is ``compute_content_hash`` of the mapping."""
    tasks = [_task("M-1", _digest(_A)), _task("M-2", _digest(_B))]
    manifest = build_verification_manifest(tasks, _STORE)
    expected_json = json.dumps(
        manifest.as_mapping(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    assert manifest.verification_manifest_hash == compute_content_hash(manifest.as_mapping())
    assert manifest.verification_manifest_hash == _digest(expected_json.encode("utf-8"))


def test_hash_is_independent_of_population_order() -> None:
    tasks = [_task("M-1", _digest(_A)), _task("M-2", _digest(_B))]
    forward = build_verification_manifest(tasks, _STORE)
    backward = build_verification_manifest(list(reversed(tasks)), _STORE)
    assert forward == backward
    assert forward.verification_manifest_hash == backward.verification_manifest_hash


def test_empty_population_is_rejected() -> None:
    with pytest.raises(VerificationManifestError, match="empty held-out population"):
        build_verification_manifest([], _STORE)


def test_duplicate_task_identity_with_the_same_digest_is_rejected() -> None:
    tasks = [_task("M-1", _digest(_A)), _task("M-1", _digest(_A))]
    with pytest.raises(VerificationManifestError, match="with the same TaskSpec digest"):
        build_verification_manifest(tasks, _STORE)


def test_duplicate_task_identity_with_different_digests_is_rejected() -> None:
    tasks = [_task("M-1", _digest(_A)), _task("M-1", _digest(_B))]
    with pytest.raises(VerificationManifestError, match="with a different TaskSpec digest"):
        build_verification_manifest(tasks, _STORE)


@pytest.mark.parametrize("bad", ["", "H", "not-a-digest", "A" * 64, "a" * 63, "g" * 64])
def test_invalid_digest_is_rejected(bad: str) -> None:
    with pytest.raises(VerificationManifestError, match="invalid TaskSpec digest"):
        build_verification_manifest([_task("M-1", bad)], _STORE)


def test_missing_taskspec_is_rejected() -> None:
    absent = _digest(_blob("never-stored"))
    with pytest.raises(VerificationManifestError, match="missing TaskSpec"):
        build_verification_manifest([_task("M-1", absent)], _STORE)


def test_content_that_does_not_rehash_to_its_digest_is_rejected() -> None:
    class TamperedStore:
        def read(self, digest: str) -> bytes | None:
            return b"tampered content"

    with pytest.raises(VerificationManifestError, match="does not re-hash"):
        build_verification_manifest([_task("M-1", _digest(_A))], TamperedStore())


def test_filesystem_store_reads_by_digest_and_reports_absence(tmp_path: Path) -> None:
    (tmp_path / _digest(_A)).write_bytes(_A)
    store = FilesystemTaskSpecStore(tmp_path)
    assert store.read(_digest(_A)) == _A
    assert store.read(_digest(_B)) is None


@pytest.mark.parametrize("bad", ["", "../outside", "A" * 64, "a" * 65])
def test_filesystem_store_refuses_malformed_digests(tmp_path: Path, bad: str) -> None:
    with pytest.raises(TaskSpecStoreError):
        FilesystemTaskSpecStore(tmp_path).read(bad)


def test_fixture_corpus_is_on_the_universal_v2_path() -> None:
    """``corpus_min`` handles are synthetic digests resolving in the fixture store (§9)."""
    corpus = load_corpus(_FIXTURES / "corpus_min", _FIXTURES / "corpus_min" / "partition.json")
    store = FilesystemTaskSpecStore(_FIXTURES / "taskspecs")
    manifest = build_verification_manifest(corpus.tasks, store)
    assert len(manifest.entries) == len(corpus.tasks)
    assert all(len(digest) == 64 for _, digest in manifest.entries)
