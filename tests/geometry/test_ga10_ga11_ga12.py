"""GA10 (annotation disclosure), GA11 (identity platform gate), GA12 (D35 version pin).

GA12 pins the D35 r2 tuple per component version. Changing any member (kernel, binding,
quantization rule, platform policy) without bumping ``GEOMETRY_VERIFIER_VERSION`` fails here, and
so does a version bump without a new pinned row.
"""

from __future__ import annotations

import json
import platform
import sys
from importlib import metadata

import pytest

from tests.geometry._cases import CASES, DATA, PARTS, payload
from velith.api import geometry_contract as contract
from velith.api.geometry_contract import GeometryEngineeringResult, GeometryTask, StepArtifact
from velith.geometry import annotation_scan
from velith.geometry import verifier as verifier_module
from velith.geometry.verifier import GeometryExecutionError, GeometryVerifier

# --- GA10 ----------------------------------------------------------------------------------------

PMI_VECTORS = [
    json.loads(line)
    for line in (DATA / "PMI_annotation_vectors.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]


@pytest.mark.parametrize("vector", PMI_VECTORS, ids=lambda v: v["file"])
def test_ga10_annotation_vectors(vector: dict[str, object]) -> None:
    name = str(vector["file"])
    path = DATA / name if name.startswith("PMI_") else PARTS / name
    assert annotation_scan.scan(path.read_bytes()) == vector["annotations"]


def test_ga10_synthetic_counts_and_never_evaluated() -> None:
    counts = annotation_scan.scan((DATA / "PMI_synthetic_ap242.step").read_bytes())
    assert counts == {
        "dimensional": "2",
        "tolerance": "3",
        "datum": "2",
        "presentation": "2",
        "evaluated": "false",
    }
    tricky = b"DATA;\n#1=PRODUCT('GEOMETRIC_TOLERANCE(',''); /* DATUM( */ ENDSEC;"
    assert annotation_scan.scan(tricky)["tolerance"] == "0"
    assert annotation_scan.scan(tricky)["datum"] == "0"


def test_ga10_facts_disclose_annotations(verifier: GeometryVerifier) -> None:
    stem, declared, _e, _f = CASES["BP-01"]
    outcome = verifier.evaluate(
        GeometryTask(task_id="ga10", requirements=declared), StepArtifact(payload=payload(stem))
    )
    assert isinstance(outcome, GeometryEngineeringResult)
    assert outcome.facts["annotations"]["evaluated"] == "false"


# --- GA11 ----------------------------------------------------------------------------------------


def _unstartable() -> GeometryVerifier:
    # If the gate let the worker start, this command would fail with a different classification.
    return GeometryVerifier(
        diag_dir=None, worker_command=[sys.executable, "-c", "raise SystemExit(9)"]
    )


def test_ga11_unsupported_machine_is_refused_before_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(platform, "machine", lambda: "aarch64")
    with pytest.raises(GeometryExecutionError) as caught:
        _unstartable().evaluate(
            GeometryTask(task_id="ga11", requirements=CASES["BP-01"][1]),
            StepArtifact(payload=payload("BP-01")),
        )
    assert caught.value.classification == "PLATFORM_UNSUPPORTED"


def test_ga11_unpinned_binding_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    real = metadata.version
    monkeypatch.setattr(
        metadata,
        "version",
        lambda name: "7.9.3.1.1" if name == contract.BINDING else real(name),
    )
    with pytest.raises(GeometryExecutionError) as caught:
        _unstartable().evaluate(
            GeometryTask(task_id="ga11", requirements=CASES["BP-01"][1]),
            StepArtifact(payload=payload("BP-01")),
        )
    assert caught.value.classification == "PLATFORM_UNSUPPORTED"


def test_ga11_this_host_is_supported_and_facts_carry_the_platform(
    verifier: GeometryVerifier,
) -> None:
    assert verifier_module.platform_support() is None
    stem, declared, _e, _f = CASES["BP-01"]
    outcome = verifier.evaluate(
        GeometryTask(task_id="ga11", requirements=declared), StepArtifact(payload=payload(stem))
    )
    assert isinstance(outcome, GeometryEngineeringResult)
    measurement = outcome.facts["measurement"]
    assert measurement["platform"] == "linux-x86_64"
    assert measurement["platform_policy"] == "temporary-identity-restriction-1"


# --- GA12 ----------------------------------------------------------------------------------------

#: D35 r2 item 4: (kernel version, binding version, quantization rule, platform policy) per
#: geometry-verifier version. A new tuple needs a new version and a new row.
PINNED: dict[str, tuple[str, str, str, str]] = {
    "0.2.0": ("8.0.1", "8.0.1.1.0", "q-1", "temporary-identity-restriction-1"),
}


def current_tuple() -> tuple[str, str, str, str]:
    return (
        contract.KERNEL_VERSION,
        contract.BINDING_VERSION,
        contract.QUANTIZATION_RULE,
        contract.PLATFORM_POLICY,
    )


def pin_holds(version: str, members: tuple[str, str, str, str]) -> bool:
    return PINNED.get(version) == members


def test_ga12_pinned_tuple_matches_the_contract() -> None:
    assert pin_holds(contract.GEOMETRY_VERIFIER_VERSION, current_tuple())


def test_ga12_installed_binding_matches_the_pin() -> None:
    assert metadata.version(contract.BINDING) == PINNED[contract.GEOMETRY_VERIFIER_VERSION][1]


@pytest.mark.parametrize("index", range(4))
def test_ga12_any_unbumped_member_change_fails(index: int) -> None:
    changed = list(current_tuple())
    changed[index] = changed[index] + "-changed"
    assert not pin_holds(
        contract.GEOMETRY_VERIFIER_VERSION, (changed[0], changed[1], changed[2], changed[3])
    )


def test_ga12_version_bump_without_a_row_fails() -> None:
    assert not pin_holds("0.2.1", current_tuple())
