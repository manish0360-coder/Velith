"""Domain-neutral task corpus loader (M4-C3).

Materializes many domain-neutral task values (:class:`CorpusTask`) from a corpus
source, each labeled with its partition from the content-addressed manifest
(M4_SPEC §3.2). It generalizes M1's single-fixture loading to a corpus **without
modifying the frozen** ``task.py``, and it is domain-neutral (D9, D22): a task's
``material`` and its verification ``handle`` are opaque — the loader hashes the
material for identity (content-addressing, not interpretation) and carries the
handle verbatim, never parsing either as diff/test/domain content.

The neutral corpus source read here (a ``corpus.json`` of task descriptors plus a
declared partition specification) is the loader *contract*. A concrete real-dataset
adapter (e.g. SWE-bench) is a registration conforming to this contract and is out of
scope (M4_SPEC §3.2/§6). Standard library only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from velith.corpus.manifest import CorpusManifest, Partition, PartitionEntry, task_identity

CORPUS_FILE = "corpus.json"


class CorpusLoaderError(Exception):
    """Raised when the corpus source or partition specification is malformed or
    incomplete (for example, a task with no declared partition). Loud, typed,
    never silent."""


@dataclass(frozen=True)
class CorpusTask:
    """A domain-neutral task value (M4_SPEC §3.2).

    ``label`` is the mutable display id; ``material`` is opaque identity content
    (content-addressed); ``handle`` is the opaque verification handle (never
    interpreted here); ``partition`` is assigned from the manifest.
    """

    label: str
    material: str
    handle: str
    partition: Partition

    @property
    def identity(self) -> str:
        """The content-addressed identity of this task (excludes ``label``)."""
        return task_identity(self.material)


@dataclass(frozen=True)
class LoadedCorpus:
    """The result of loading a corpus: the partitioned tasks and the frozen manifest."""

    tasks: tuple[CorpusTask, ...]
    manifest: CorpusManifest


@dataclass(frozen=True)
class _Descriptor:
    label: str
    material: str
    handle: str


def load_corpus(corpus_path: Path, partition_spec_path: Path) -> LoadedCorpus:
    """Load a corpus from ``corpus_path``, partitioned by the declared split.

    Reads the neutral task descriptors and the declared partition specification,
    builds the content-addressed manifest (M4-C2), and returns the partitioned tasks
    each labeled with its partition **from the manifest**. Every task must have a
    declared partition; a task absent from the specification raises
    :class:`CorpusLoaderError` (each task resolves to exactly one partition).
    """
    descriptors = _read_descriptors(corpus_path)
    declared = _read_partition_spec(partition_spec_path)

    entries: list[PartitionEntry] = []
    for descriptor in descriptors:
        partition = declared.get(descriptor.material)
        if partition is None:
            raise CorpusLoaderError(
                f"task {descriptor.label!r} has no declared partition in {partition_spec_path}"
            )
        entries.append(
            PartitionEntry(
                label=descriptor.label,
                material=descriptor.material,
                partition=partition,
            )
        )

    manifest = CorpusManifest.from_entries(entries)
    tasks = tuple(
        CorpusTask(
            label=descriptor.label,
            material=descriptor.material,
            handle=descriptor.handle,
            partition=_require_partition(manifest, descriptor.material),
        )
        for descriptor in descriptors
    )
    return LoadedCorpus(tasks=tasks, manifest=manifest)


def _read_descriptors(corpus_path: Path) -> list[_Descriptor]:
    corpus_file = corpus_path / CORPUS_FILE
    if not corpus_file.exists():
        raise CorpusLoaderError(f"corpus file not found: {corpus_file}")
    raw = json.loads(corpus_file.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise CorpusLoaderError(f"corpus must be a JSON array: {corpus_file}")
    descriptors: list[_Descriptor] = []
    for item in raw:
        if not isinstance(item, dict):
            raise CorpusLoaderError(f"corpus entry must be a JSON object: {item!r}")
        try:
            descriptors.append(
                _Descriptor(
                    label=str(item["label"]),
                    material=str(item["material"]),
                    handle=str(item["handle"]),
                )
            )
        except KeyError as exc:
            raise CorpusLoaderError(f"corpus entry missing field {exc}: {item!r}") from exc
    return descriptors


def _read_partition_spec(partition_spec_path: Path) -> dict[str, Partition]:
    if not partition_spec_path.exists():
        raise CorpusLoaderError(f"partition spec not found: {partition_spec_path}")
    raw = json.loads(partition_spec_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CorpusLoaderError(f"partition spec must be a JSON object: {partition_spec_path}")
    declared: dict[str, Partition] = {}
    for material, label in raw.items():
        try:
            declared[str(material)] = Partition(label)
        except ValueError as exc:
            raise CorpusLoaderError(f"invalid partition {label!r} for {material!r}") from exc
    return declared


def _require_partition(manifest: CorpusManifest, material: str) -> Partition:
    partition = manifest.partition_of(task_identity(material))
    if partition is None:
        raise CorpusLoaderError(f"no partition for material {material!r}")
    return partition
