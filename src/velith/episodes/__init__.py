"""Velith episodes: the provenance-complete record of one task attempt (M1).

This subpackage owns the :class:`~velith.episodes.episode.Episode` schema and its
canonical content hash (M1 spec §9.1 / §9.1.1), and — from C2 — the append-only
JSONL store. It contains no agent, model, or verification logic; an episode is a
record of what happened, not the machinery that produced it.
"""
