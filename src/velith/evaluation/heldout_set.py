"""Read-only access to the held-out evaluation set (M8-C3).

The generalization measure is the **held-out** partition of the frozen corpus (M4):
an arm cannot have memorized what the guarded boundary structurally prevented it from
retaining (D8), so held-out performance reflects generalization, not recall (M8_SPEC
§3.2). This module surfaces exactly those tasks, through the frozen M4 loader's
held-out view, together with the manifest hash that fixes the split.

It is **read-only** (the loader only reads) and **domain-neutral** (D9/D22): a task's
``material`` and verification ``handle`` are opaque and never inspected here. Reading
these tasks is the one place the program deliberately touches held-out material; the
outcome never re-enters experience — that guarantee lives in the sink (M8-C6), not
here. Standard library plus the frozen M4 corpus loader.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from velith.corpus.loader import CorpusTask, load_corpus
from velith.corpus.manifest import Partition


@dataclass(frozen=True)
class HeldOutEvaluationSet:
    """The held-out tasks to evaluate against, plus the manifest hash fixing the split.

    Immutable and read-only. ``manifest_hash`` binds any evaluation over this set to the
    exact split it was measured on: evaluating a changed split is a different, separately
    identified evaluation (M8_SPEC §3.2).
    """

    tasks: tuple[CorpusTask, ...]
    manifest_hash: str

    def __len__(self) -> int:
        return len(self.tasks)

    def __iter__(self) -> Iterator[CorpusTask]:
        return iter(self.tasks)


def load_heldout_set(corpus_path: Path, partition_spec_path: Path) -> HeldOutEvaluationSet:
    """Load the held-out partition as the evaluation set (read-only).

    Composes the frozen M4 loader and keeps only the held-out tasks; available tasks are
    never surfaced. Carries the frozen manifest hash so results are comparable only within
    the same split.
    """
    loaded = load_corpus(corpus_path, partition_spec_path)
    held_out = tuple(task for task in loaded.tasks if task.partition is Partition.HELD_OUT)
    return HeldOutEvaluationSet(tasks=held_out, manifest_hash=loaded.manifest.manifest_hash)
