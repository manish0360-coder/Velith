"""Velith G0: exact-geometry conformance for one STEP file (D34; Engineering API v0.2).

Optional: requires the ``geometry`` extra (``cadquery-ocp-novtk``). Modules:

- ``velith.geometry.verifier`` - :class:`GeometryVerifier` (parent side; never imports OCP);
- ``velith.geometry.rules`` - quantization, facts, G-RULE and conformance (pure Python);
- ``velith.geometry.annotation_scan`` - annotation disclosure, rule a-1 (pure Python);
- ``velith.geometry._kernel`` - the isolated measurement worker, the only ``OCP`` importer.

This package root imports nothing, so the worker starts without loading the contract layers twice.
``velith.api`` never imports this package.
"""
