"""Velith runner: the M1 spike orchestrator and CLI.

This subpackage holds :mod:`velith.runner.spike` — the single place that knows the
order of operations for one ``propose -> verify -> log`` episode, plus its CLI
entrypoint. It owns control flow only; the work is done by the proposer, verifier,
and store through their public contracts (M1 spec §8).
"""
