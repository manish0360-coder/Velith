"""Unit tests for the fixed base-model selection seam (M5-C3).

Scope: the seam binds exactly one fixed base model and returns it (M5_SPEC §3.4).
"""

from __future__ import annotations

from velith.batch.model import FixedBaseModel


def test_selects_the_one_configured_base_model() -> None:
    seam = FixedBaseModel(model="qwen2.5-coder")
    assert seam.select() == "qwen2.5-coder"


def test_binds_exactly_one_model() -> None:
    # Each seam binds an independent single model and returns only its own.
    assert FixedBaseModel("model-a").select() == "model-a"
    assert FixedBaseModel("model-b").select() == "model-b"
