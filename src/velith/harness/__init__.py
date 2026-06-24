"""Velith harness: the deterministic verifier seam (M1).

This subpackage owns :class:`~velith.harness.verifier_sandbox.VerifierSandbox` —
the single, bounded place where a candidate patch is applied and the hidden test
suite is run to produce a grounded :class:`~velith.harness.verifier_sandbox.Verdict`.
It is the seam M2 hardens (network isolation, flake detection, bit-for-bit
determinism). It contains no model and never judges correctness with a model (D3).
"""
