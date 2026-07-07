"""Task-materialization adapter seam (M5-C4).

The one seam where domain specifics are permitted, entirely behind a domain-neutral
interface (M5_SPEC §3.3). :class:`TaskAdapter` materializes, from a domain-neutral
:class:`~velith.corpus.loader.CorpusTask` (opaque ``material`` and verification
``handle``), the concrete input the frozen components consume: a verifiable
:class:`~velith.task.Task`, which carries both the proposal context (its ``prompt``)
for the proposer and the verification handle (its ``repo_path`` + hidden-test command)
for the verifier.

The runner depends on the **interface** only; it never inspects materials or handles.
:class:`FixtureTaskAdapter` is the reference adapter over the single fixture (D16.3);
a concrete real-dataset adapter (e.g. SWE-bench) is a registration behind this same
interface and is out of scope (M5_SPEC §3.3/§8). Standard library only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from velith.corpus.loader import CorpusTask
from velith.task import Task, load_fixture_task


class TaskAdapter(Protocol):
    """Domain-neutral seam: materialize a verifiable :class:`Task` from a ``CorpusTask``."""

    def materialize(self, corpus_task: CorpusTask) -> Task:
        """Return the verifiable frozen task for ``corpus_task`` (M5_SPEC §3.3)."""
        ...


class FixtureTaskAdapter:
    """Reference adapter over the single fixture (D16.3).

    Every corpus task materializes to the one frozen fixture :class:`Task`; the corpus
    task's opaque content is never inspected. Real-dataset adapters are registrations
    behind :class:`TaskAdapter`, out of scope here.
    """

    def __init__(self, fixtures_root: Path | None = None) -> None:
        self._fixtures_root = fixtures_root

    def materialize(self, corpus_task: CorpusTask) -> Task:
        """Materialize the single fixture task, opaque to ``corpus_task``'s content."""
        return load_fixture_task(self._fixtures_root)
