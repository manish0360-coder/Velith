"""The held-out evaluation layer (M8).

The program's first **measurement** instrument: it evaluates each arm (A0, A1, A2)
against the **held-out** partition at a **frozen checkpoint**, through one identical,
deterministic harness, and records the per-task outcome as a **segregated evaluation
measurement** that can never become experience (M8_SPEC §1).

Everything here is **read-only** against memory and the experience log and
**domain-neutral** (D9/D22). The held-out lock is preserved: evaluation reads held-out
tasks to attempt them, but an outcome is written only to the evaluation sink, and the
frozen guarded boundary still fail-closes on a held-out identity (D8). M8 **measures**;
it does not conclude - no statistic, no decision (D22; M9/M10). Standard library plus
the frozen M0-M7 packages.
"""
