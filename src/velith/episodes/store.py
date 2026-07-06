"""Append-only JSONL persistence for episodes (M1 spec §7, handoff §4.2).

The store is the durable home of the program's grounded experience: each
:class:`~velith.episodes.episode.Episode` is appended as one JSON line and read
back with its content hash verified (invariant I2). The append-only JSONL log is
the authoritative source of truth; from M3 the store additionally maintains a
*derived*, rebuildable SQLite index projection (M3_SPEC §4.1-§4.2) and a
record-level integrity digest (§9). Neither is ever trusted over the log: the log
is written and ``fsync``-ed first, and the index is a projection that can be
rebuilt from the log at any time. A store constructed without an index path keeps
the exact M1/M2 log-only behaviour.

Durability & partial-write safety (M1 spec §11): an episode is serialized to a
single complete line (terminated by a newline) which is written, flushed, and
``fsync``-ed before :meth:`EpisodeStore.append` returns. The record is therefore
on disk before the caller proceeds, and a crash cannot leave a half-line that
would later fail hash verification.

Configuration note (raised, not silently resolved — handoff preamble): the M1
spec lists this component as depending on ``config`` for the episode path, but the
``episode_path`` setting is added to ``Settings`` in C7 (the commit plan). To keep
C2 atomic and green without pulling C7's config change forward, the store receives
its target path by constructor injection; the orchestrator (C7) reads the path
from the validated ``Settings`` and supplies it here. This mirrors M0's existing
injection pattern in ``core/logging.py`` (accept the dependency, don't reach for a
global).
"""

from __future__ import annotations

import os
from pathlib import Path

from velith.core.logging import get_logger
from velith.episodes.episode import Episode
from velith.episodes.index import EpisodeIndex, EpisodeIndexRow, record_digest

logger = get_logger(__name__)


class EpisodeIntegrityError(Exception):
    """Raised when a stored episode's content hash does not verify on read (I2).

    A typed, loud failure (M0 §10): a corrupt or tampered record is never skipped
    silently. The shared ``velith`` base-error hierarchy (M1 spec §11) is
    introduced by the later commit that first needs the model/sandbox errors; this
    error stands on its own until then.
    """


class RecordIntegrityError(Exception):
    """Raised when a stored record's integrity digest disagrees with the index (M3).

    Distinct from :class:`EpisodeIntegrityError`, which covers the identity
    ``content_hash``. This covers the *full-record* digest (identity + provenance,
    M3_SPEC §9), so it catches corruption of the provenance fields the content hash
    deliberately excludes (``timestamp``, ``latency_seconds``, ``verify_seconds``,
    ``flaky`` — D16.1/D21). Loud, never silent.
    """


class EpisodeStore:
    """An append-only JSONL store of episodes, optionally mirrored by a derived index.

    The JSONL log at ``path`` is authoritative. When ``index_path`` is supplied, each
    append also upserts the episode's neutral projection and record digest into the
    SQLite index (M3_SPEC §6.1, §9), and reads verify that digest when the index holds
    a matching row. When ``index_path`` is ``None`` the store is log-only, identical to
    M1/M2.
    """

    def __init__(self, path: Path, index_path: Path | None = None) -> None:
        self._path = path
        self._index_path = index_path

    @property
    def path(self) -> Path:
        """The JSONL file this store appends to and reads from."""
        return self._path

    def append(self, episode: Episode) -> Path:
        """Durably append one episode as a JSON line; return the file path.

        Append-only: existing records are never read, rewritten, or mutated. The
        complete line is flushed and ``fsync``-ed before returning (§11).
        """
        line = episode.model_dump_json() + "\n"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        logger.info(
            "episode appended",
            extra={
                "event": "episode_appended",
                "path": str(self._path),
                "task_id": episode.task_id,
                "verdict_state": episode.verdict_state.value,
                "content_hash": episode.content_hash,
            },
        )
        # The authoritative log is now on disk; update the derived index projection
        # (M3_SPEC §4.1-§4.2). If this step failed the log would still be complete and
        # the index rebuildable from it, so the log's authority is never at risk.
        if self._index_path is not None:
            with EpisodeIndex(self._index_path) as index:
                index.upsert(EpisodeIndexRow.from_episode(episode))
        return self._path

    def read_all(self) -> list[Episode]:
        """Return every persisted episode, verifying each content hash (I2).

        A missing file means nothing has been written yet and yields an empty
        list. A record whose hash does not verify raises
        :class:`EpisodeIntegrityError` — corruption is loud, never silent.
        """
        if not self._path.exists():
            return []
        # Load the index's record digests once, if an index exists. A missing index
        # (log-only store, or a pre-existing log not yet indexed) simply skips the
        # digest check — the log remains authoritative and readable (M3_SPEC §9).
        expected_digests: dict[str, str] = {}
        if self._index_path is not None and self._index_path.exists():
            with EpisodeIndex(self._index_path) as index:
                expected_digests = {row.content_hash: row.record_digest for row in index.all_rows()}
        episodes: list[Episode] = []
        with self._path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                episode = Episode.model_validate_json(stripped)
                if not episode.verify_hash():
                    raise EpisodeIntegrityError(
                        f"content hash mismatch at {self._path}:{line_number} "
                        f"(task_id={episode.task_id!r})"
                    )
                expected_digest = expected_digests.get(episode.content_hash)
                if (
                    expected_digest is not None
                    and record_digest(episode.model_dump_json()) != expected_digest
                ):
                    raise RecordIntegrityError(
                        f"record digest mismatch at {self._path}:{line_number} "
                        f"(task_id={episode.task_id!r})"
                    )
                episodes.append(episode)
        return episodes
