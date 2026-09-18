"""Unit tests for the write-once M9 pre-registration store (M9-C2 / P1).

Deterministic, synthetic fixtures only — no real M8 held-out data or outcomes. These pin
write-once immutability, round-trip load/store, integrity verification, and segregation
of the pre-registration location.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from velith.analysis.prereg_store import PreRegistrationStore
from velith.analysis.preregistration import PreRegistration, PreRegistrationError


def _cid(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _build(**overrides: object) -> PreRegistration:
    kwargs: dict[str, object] = {
        "manifest_hash": _cid("manifest"),
        "checkpoint_identities": (_cid("cp1"), _cid("cp2")),
        "base_model": "qwen2.5-coder",
        "eval_seed": 0,
        "max_tasks": 0,
        "max_attempts_per_task": 1,
        "max_tokens": 0,
    }
    kwargs.update(overrides)
    return PreRegistration.build(**kwargs)  # type: ignore[arg-type]


def test_write_then_read_round_trips(tmp_path: Path) -> None:
    store = PreRegistrationStore(tmp_path / "analysis" / "preregistration.json")
    pr = _build()
    assert not store.exists()
    store.write(pr)
    assert store.exists()
    assert store.read() == pr


def test_rewriting_identical_prereg_is_idempotent(tmp_path: Path) -> None:
    store = PreRegistrationStore(tmp_path / "preregistration.json")
    pr = _build()
    store.write(pr)
    store.write(pr)  # must not raise; identical identity
    assert store.read() == pr


def test_writing_a_different_prereg_is_refused(tmp_path: Path) -> None:
    store = PreRegistrationStore(tmp_path / "preregistration.json")
    store.write(_build(checkpoint_identities=(_cid("cp1"),)))
    with pytest.raises(PreRegistrationError):
        store.write(_build(checkpoint_identities=(_cid("cp2"),)))


def test_read_missing_raises(tmp_path: Path) -> None:
    store = PreRegistrationStore(tmp_path / "preregistration.json")
    with pytest.raises(PreRegistrationError):
        store.read()


def test_tampered_content_fails_integrity_on_read(tmp_path: Path) -> None:
    path = tmp_path / "preregistration.json"
    store = PreRegistrationStore(path)
    pr = _build()
    store.write(pr)
    # Tamper a hashed field while leaving the stored identity unchanged.
    tampered = pr.model_copy(update={"base_model": "tampered-model"})
    path.write_text(tampered.model_dump_json() + "\n", encoding="utf-8")
    with pytest.raises(PreRegistrationError):
        store.read()


def test_store_location_is_segregated(tmp_path: Path) -> None:
    store = PreRegistrationStore(tmp_path / "analysis" / "preregistration.json")
    assert store.path.name == "preregistration.json"
    assert "analysis" in store.path.parts
