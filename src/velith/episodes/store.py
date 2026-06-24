"""Append-only JSONL persistence for episodes (M1 spec §7, handoff §4.2).

The store is the durable home of the program's grounded experience: each
:class:`~velith.episodes.episode.Episode` is appended as one JSON line and read
back with its content hash verified (invariant I2). It is deliberately the
simplest thing that is durable and tamper-evident — no index, no database, no
query-by-arm/seed/checkpoint (those are M3).

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

logger = get_logger(__name__)


class EpisodeIntegrityError(Exception):
    """Raised when a stored episode's content hash does not verify on read (I2).

    A typed, loud failure (M0 §10): a corrupt or tampered record is never skipped
    silently. The shared ``velith`` base-error hierarchy (M1 spec §11) is
    introduced by the later commit that first needs the model/sandbox errors; this
    error stands on its own until then.
    """


class EpisodeStore:
    """An append-only JSONL store of episodes at a single configured path."""

    def __init__(self, path: Path) -> None:
        self._path = path

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
        return self._path

    def read_all(self) -> list[Episode]:
        """Return every persisted episode, verifying each content hash (I2).

        A missing file means nothing has been written yet and yields an empty
        list. A record whose hash does not verify raises
        :class:`EpisodeIntegrityError` — corruption is loud, never silent.
        """
        if not self._path.exists():
            return []
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
                episodes.append(episode)
        return episodes
