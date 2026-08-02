"""The segregated evaluation sink (M8-C6).

Held-out evaluation records are written **only** here — to a location **distinct from
the experience log** that is **never a memory source** and **never the experience path**
(M8_SPEC §3.4). This is the structural guarantee that preserves the held-out lock (D8):
a held-out outcome is recorded as a measurement and can never become experience, because

* the sink is a plain append-only JSONL of :class:`EvaluationRecord` values — **not** an
  :class:`~velith.episodes.store.EpisodeStore`, so nothing here is retrievable as memory;
  and
* the sink **never** imports or calls the frozen ``GuardedEpisodeWriter`` or the episode
  store's write surface — a record cannot reach the experience path even by accident.

The sink adds no path by which held-out experience could leak into any arm's memory.
Standard library plus the M8 evaluation record.
"""

from __future__ import annotations

from pathlib import Path

from velith.evaluation.record import EvaluationRecord


class EvaluationSink:
    """An append-only JSONL sink for held-out evaluation records.

    It writes measurements and nothing else. It is deliberately not a memory source: its
    read surface returns :class:`EvaluationRecord` values (never episodes), so the
    retriever can never consume it.
    """

    def __init__(self, sink_path: Path) -> None:
        self._sink_path = sink_path

    @property
    def path(self) -> Path:
        """The sink's file location (distinct from the experience log)."""
        return self._sink_path

    def append(self, record: EvaluationRecord) -> None:
        """Append one evaluation record as a JSONL line. Writes only to the sink path."""
        self._sink_path.parent.mkdir(parents=True, exist_ok=True)
        with self._sink_path.open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json() + "\n")

    def read_all(self) -> tuple[EvaluationRecord, ...]:
        """Return the recorded measurements (for inspection/acceptance) — not memory.

        Returns :class:`EvaluationRecord` values, never episodes, so this read surface can
        never be used as a retrieval memory source. A missing sink yields no records.
        """
        if not self._sink_path.exists():
            return ()
        with self._sink_path.open("r", encoding="utf-8") as handle:
            return tuple(
                EvaluationRecord.model_validate_json(line) for line in handle if line.strip()
            )
