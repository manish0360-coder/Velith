"""Unit tests for the task-materialization adapter seam (M5-C4).

Scope: the reference adapter yields the frozen verifiable ``Task`` (both proposal
context and verification handle), it conforms to the neutral interface, and it accepts
a non-software corpus task opaquely without inspecting its content (M5_SPEC §3.3).
"""

from __future__ import annotations

from velith.batch.adapter import FixtureTaskAdapter, TaskAdapter
from velith.corpus.loader import CorpusTask
from velith.corpus.manifest import Partition
from velith.task import Task


def _corpus_task(material: str = "MAT-1") -> CorpusTask:
    return CorpusTask(label="t", material=material, handle="h", partition=Partition.AVAILABLE)


def test_reference_adapter_materializes_a_verifiable_frozen_task() -> None:
    task = FixtureTaskAdapter().materialize(_corpus_task())
    assert isinstance(task, Task)
    assert task.prompt  # proposal context for the proposer
    assert task.hidden_test_command  # verification handle for the verifier


def test_reference_adapter_conforms_to_the_interface() -> None:
    adapter: TaskAdapter = FixtureTaskAdapter()
    assert isinstance(adapter.materialize(_corpus_task()), Task)


def test_non_software_corpus_task_is_accepted_opaquely() -> None:
    # A non-software material is accepted without inspection; the adapter yields the
    # frozen fixture Task regardless of the corpus task's opaque content (M5_SPEC §3.3).
    task = FixtureTaskAdapter().materialize(_corpus_task(material="notes:C-E-G;bpm:120"))
    assert isinstance(task, Task)
