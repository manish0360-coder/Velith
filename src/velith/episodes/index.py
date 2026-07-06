"""SQLite index over the episode log — a derived, rebuildable projection (M3-C2).

The append-only JSONL log (:mod:`velith.episodes.store`) remains the single
authoritative source of truth. This index is a *projection* of it: it can be
dropped and reconstructed from the log alone (:meth:`EpisodeIndex.rebuild_from_log`),
so it is never trusted over the log (M3_SPEC §4.1-§4.2).

It holds one row per episode over the **closed neutral field set** (M3_SPEC §6.2)
— ``task_id``, ``state``, ``timestamp``, ``model``, ``seed``, ``flaky``,
``secondary_passed``, ``content_hash`` — plus a record-level integrity digest
(:func:`record_digest`) that is distinct from ``Episode.content_hash`` (M3_SPEC §9).

The store is **domain-neutral**: the change/``patch``, the prompt, and any source
are never indexed (M3_SPEC §3, §4.4). This module imports :class:`Episode` only,
never :mod:`velith.episodes.store`, so no import cycle is introduced.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from velith.episodes.episode import Episode

# The closed neutral-field set (M3_SPEC §6.2) plus the integrity digest (§9). This
# is the complete column set of the index; no domain field appears here.
INDEX_COLUMNS: tuple[str, ...] = (
    "content_hash",
    "task_id",
    "state",
    "timestamp",
    "model",
    "seed",
    "flaky",
    "secondary_passed",
    "record_digest",
)


def record_digest(serialized_record: str) -> str:
    """Return the SHA-256 hex digest of a full serialized episode record.

    Distinct from ``Episode.content_hash``: the content hash covers *identity*
    only and deliberately excludes provenance (D16.1/D21), whereas this digest
    covers the entire serialized record (identity *and* provenance) so that
    storage-level corruption is detectable (M3_SPEC §9).
    """
    return hashlib.sha256(serialized_record.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EpisodeIndexRow:
    """One indexed row: the neutral fields (M3_SPEC §6.2) plus the record digest."""

    task_id: str
    state: str
    timestamp: str
    model: str
    seed: int
    flaky: bool
    secondary_passed: bool | None
    content_hash: str
    record_digest: str

    @classmethod
    def from_episode(cls, episode: Episode) -> EpisodeIndexRow:
        """Project an episode onto the neutral row, computing its record digest.

        Only neutral fields are read; ``patch``, ``prompt``, and ``verdict_output``
        are never copied into the index (M3_SPEC §4.4). The digest is taken over
        the episode's canonical serialization, matching what the store persists.
        """
        return cls(
            task_id=episode.task_id,
            state=episode.verdict_state.value,
            timestamp=episode.timestamp,
            model=episode.model,
            seed=episode.seed,
            flaky=episode.flaky,
            secondary_passed=episode.secondary_passed,
            content_hash=episode.content_hash,
            record_digest=record_digest(episode.model_dump_json()),
        )


def _optional_bool_to_db(value: bool | None) -> int | None:
    return None if value is None else int(value)


class EpisodeIndex:
    """An embedded SQLite index over the episode log, keyed by ``content_hash``.

    The index is a rebuildable projection (M3_SPEC §4.2): it may be dropped and
    reconstructed from the authoritative log at any time. Query accessors return
    neutral rows; episode materialization stays in the store (M3_SPEC §6.1).
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    # --- lifecycle -------------------------------------------------------
    def close(self) -> None:
        """Close the underlying connection."""
        self._conn.close()

    def __enter__(self) -> EpisodeIndex:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS episodes (
                content_hash     TEXT PRIMARY KEY,
                task_id          TEXT NOT NULL,
                state            TEXT NOT NULL,
                timestamp        TEXT NOT NULL,
                model            TEXT NOT NULL,
                seed             INTEGER NOT NULL,
                flaky            INTEGER NOT NULL,
                secondary_passed INTEGER,
                record_digest    TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    # --- writes ----------------------------------------------------------
    def upsert(self, row: EpisodeIndexRow) -> None:
        """Insert or replace one indexed row, keyed by ``content_hash``.

        Idempotent: re-indexing the same episode leaves the index unchanged.
        """
        self._conn.execute(
            """
            INSERT INTO episodes
                (content_hash, task_id, state, timestamp, model, seed, flaky,
                 secondary_passed, record_digest)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(content_hash) DO UPDATE SET
                task_id          = excluded.task_id,
                state            = excluded.state,
                timestamp        = excluded.timestamp,
                model            = excluded.model,
                seed             = excluded.seed,
                flaky            = excluded.flaky,
                secondary_passed = excluded.secondary_passed,
                record_digest    = excluded.record_digest
            """,
            (
                row.content_hash,
                row.task_id,
                row.state,
                row.timestamp,
                row.model,
                row.seed,
                int(row.flaky),
                _optional_bool_to_db(row.secondary_passed),
                row.record_digest,
            ),
        )
        self._conn.commit()

    def rebuild_from_log(self, log_path: Path) -> None:
        """Drop all rows and reconstruct the index from the log alone (§4.2).

        A missing log means nothing has been written yet and yields an empty
        index. The log is the sole input; no prior index state is trusted.
        """
        self._conn.execute("DELETE FROM episodes")
        if log_path.exists():
            with log_path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    stripped = raw_line.strip()
                    if not stripped:
                        continue
                    episode = Episode.model_validate_json(stripped)
                    self.upsert(EpisodeIndexRow.from_episode(episode))
        self._conn.commit()

    # --- reads -----------------------------------------------------------
    def get(self, content_hash: str) -> EpisodeIndexRow | None:
        """Return the row for a content hash, or ``None`` if absent."""
        cursor = self._conn.execute(
            "SELECT * FROM episodes WHERE content_hash = ?", (content_hash,)
        )
        record = cursor.fetchone()
        return None if record is None else self._to_row(record)

    def by_task(self, task_id: str) -> list[EpisodeIndexRow]:
        """Rows whose ``task_id`` matches, ordered deterministically."""
        return self._select("WHERE task_id = ?", (task_id,))

    def by_state(self, state: str) -> list[EpisodeIndexRow]:
        """Rows whose verdict ``state`` matches."""
        return self._select("WHERE state = ?", (state,))

    def by_model(self, model: str) -> list[EpisodeIndexRow]:
        """Rows whose proposing ``model`` matches."""
        return self._select("WHERE model = ?", (model,))

    def by_seed(self, seed: int) -> list[EpisodeIndexRow]:
        """Rows whose ``seed`` matches."""
        return self._select("WHERE seed = ?", (seed,))

    def by_flaky(self, flaky: bool) -> list[EpisodeIndexRow]:
        """Rows whose ``flaky`` provenance flag matches."""
        return self._select("WHERE flaky = ?", (int(flaky),))

    def by_secondary_passed(self, secondary_passed: bool | None) -> list[EpisodeIndexRow]:
        """Rows whose ``secondary_passed`` matches (``None`` selects SQL NULL)."""
        if secondary_passed is None:
            return self._select("WHERE secondary_passed IS NULL", ())
        return self._select("WHERE secondary_passed = ?", (int(secondary_passed),))

    def by_time_range(self, start: str, end: str) -> list[EpisodeIndexRow]:
        """Rows whose ISO-8601 ``timestamp`` lies within ``[start, end]`` inclusive."""
        return self._select("WHERE timestamp >= ? AND timestamp <= ?", (start, end))

    def all_rows(self) -> list[EpisodeIndexRow]:
        """Every indexed row, in the same deterministic order as the accessors."""
        return self._select("", ())

    # --- internals -------------------------------------------------------
    def _select(self, where: str, params: Sequence[object]) -> list[EpisodeIndexRow]:
        query = f"SELECT * FROM episodes {where} ORDER BY timestamp, content_hash"
        cursor = self._conn.execute(query, tuple(params))
        return [self._to_row(record) for record in cursor.fetchall()]

    @staticmethod
    def _to_row(record: sqlite3.Row) -> EpisodeIndexRow:
        raw_secondary = record["secondary_passed"]
        return EpisodeIndexRow(
            task_id=record["task_id"],
            state=record["state"],
            timestamp=record["timestamp"],
            model=record["model"],
            seed=record["seed"],
            flaky=bool(record["flaky"]),
            secondary_passed=None if raw_secondary is None else bool(raw_secondary),
            content_hash=record["content_hash"],
            record_digest=record["record_digest"],
        )
