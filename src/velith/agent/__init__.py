"""Velith agent: the proposer (M1).

This subpackage holds :class:`~velith.agent.proposer.ProposerAgent`, which turns a
task into a candidate :class:`~velith.agent.proposer.Proposal` via the thin LLM
client. In M1 it is a single bounded component — no memory, retrieval, multiple
attempts, or self-critique (those are later milestones).
"""
