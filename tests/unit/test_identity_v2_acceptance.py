"""Implementation acceptance tests for M8 evaluation identity v2 (D29).

The 18 identity cases of ``docs/M8_IDENTITY_V2_SPEC.md`` §12, plus the runner's pre-attempt
consistency check (§7). Each test names its case. The TaskSpec schema is undecided (D26), so
cases 2-5 exercise their scenario as a change in the schema-free TaskSpec bytes: any content
change changes the TaskSpec digest, hence the VerificationManifest hash, hence both
identities. SHA-256 distinctness is conditional on collision resistance.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from velith.agent.proposer import Proposal
from velith.analysis.binder import BinderError, bind_observations
from velith.analysis.executor import ExecutionError, run_preflight
from velith.analysis.preregistration import SPEC_VERSION, PreRegistration
from velith.arms.identity import Arm
from velith.batch.budget import CostGuard
from velith.corpus.loader import CorpusTask
from velith.corpus.manifest import Partition
from velith.episodes.episode import VerdictState, compute_content_hash
from velith.evaluation.attempt import HeldOutAttempt
from velith.evaluation.checkpoint import form_checkpoint
from velith.evaluation.heldout_set import HeldOutEvaluationSet, load_heldout_set
from velith.evaluation.provenance import (
    IDENTITY_VERSION,
    EvaluationProvenance,
    EvaluationProvenanceError,
)
from velith.evaluation.record import EvaluationRecord
from velith.evaluation.runner import EvaluationError, run_heldout_evaluation
from velith.evaluation.sink import EvaluationSink
from velith.evaluation.verification_manifest import (
    VerificationManifestError,
    build_verification_manifest,
)
from velith.harness.verifier_sandbox import Verdict
from velith.retrieval.embedding import EMBEDDER_NAME, get_embedder
from velith.retrieval.memory import EpisodeMemory
from velith.retrieval.retriever import Retriever
from velith.task import Task


def _hex(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _blob(tag: str) -> bytes:
    return f"velith-synthetic-taskspec:{tag}\n".encode()


class InMemoryTaskSpecStore:
    """A content-addressed TaskSpec byte store held in memory (test double)."""

    def __init__(self, *blobs: bytes) -> None:
        self._blobs = {hashlib.sha256(b).hexdigest(): b for b in blobs}

    def read(self, digest: str) -> bytes | None:
        return self._blobs.get(digest)


def _held(material: str, content: bytes) -> CorpusTask:
    return CorpusTask(
        label=material,
        material=material,
        handle=hashlib.sha256(content).hexdigest(),
        partition=Partition.HELD_OUT,
    )


_BASE = _blob("base")
_POPULATION = (_held("M-1", _BASE), _held("M-2", _BASE))
_STORE = InMemoryTaskSpecStore(_BASE)


def _vm(tasks: tuple[CorpusTask, ...], store: InMemoryTaskSpecStore = _STORE) -> str:
    return build_verification_manifest(tasks, store).verification_manifest_hash


def _provenance(vm_hash: str) -> EvaluationProvenance:
    return EvaluationProvenance(
        checkpoint_identity=_hex("checkpoint"),
        manifest_hash=_hex("manifest"),
        arm=Arm.A1.value,
        base_model="synthetic-base",
        eval_seed=7,
        max_tasks=0,
        max_attempts_per_task=1,
        max_tokens=0,
        verification_manifest_hash=vm_hash,
    )


def _prereg(vm_hash: str) -> PreRegistration:
    return PreRegistration.build(
        manifest_hash=_hex("manifest"),
        verification_manifest_hash=vm_hash,
        checkpoint_identities=(_hex("cp1"),),
        base_model="synthetic-base",
        eval_seed=7,
        max_tasks=0,
        max_attempts_per_task=1,
        max_tokens=0,
    )


# --- cases 1-10: identity determinism and sensitivity ------------------------------


def test_case_01_same_evaluation_same_taskspecs_same_identity() -> None:
    assert _provenance(_vm(_POPULATION)).identity == _provenance(_vm(_POPULATION)).identity
    assert _prereg(_vm(_POPULATION)).identity == _prereg(_vm(_POPULATION)).identity


@pytest.mark.parametrize(
    ("case", "changed_content"),
    [
        ("02-image-digest", _blob("base|image=sha256:other")),
        ("03-protected-surface", _blob("base|protected-surface=other")),
        ("04-test-command", _blob("base|required-tests=other")),
        ("05-runner-config-digest", _blob("base|runner-config=other")),
    ],
)
def test_cases_02_to_05_taskspec_change_changes_both_identities(
    case: str, changed_content: bytes
) -> None:
    changed = (_held("M-1", changed_content), _POPULATION[1])
    store = InMemoryTaskSpecStore(_BASE, changed_content)
    base_vm, changed_vm = _vm(_POPULATION), _vm(changed, store)
    assert base_vm != changed_vm, case
    assert _provenance(base_vm).identity != _provenance(changed_vm).identity, case
    assert _prereg(base_vm).identity != _prereg(changed_vm).identity, case


def test_case_06_changed_heldout_population_changes_identity() -> None:
    grown = (*_POPULATION, _held("M-3", _BASE))
    base = _provenance(_vm(_POPULATION))
    other = dataclasses.replace(_provenance(_vm(grown)), manifest_hash=_hex("other-manifest"))
    assert base.verification_manifest_hash != other.verification_manifest_hash
    assert base.identity != other.identity


_BASE_PROVENANCE = _provenance(_vm(_POPULATION))


@pytest.mark.parametrize(
    ("case", "changed"),
    [
        ("07-arm", dataclasses.replace(_BASE_PROVENANCE, arm=Arm.A2.value)),
        (
            "08-checkpoint",
            dataclasses.replace(_BASE_PROVENANCE, checkpoint_identity=_hex("other-checkpoint")),
        ),
        ("09-eval-seed", dataclasses.replace(_BASE_PROVENANCE, eval_seed=8)),
        ("10-cost-guard-max-tasks", dataclasses.replace(_BASE_PROVENANCE, max_tasks=5)),
        (
            "10-cost-guard-max-attempts",
            dataclasses.replace(_BASE_PROVENANCE, max_attempts_per_task=2),
        ),
        ("10-cost-guard-max-tokens", dataclasses.replace(_BASE_PROVENANCE, max_tokens=4096)),
    ],
)
def test_cases_07_to_10_component_change_changes_identity(
    case: str, changed: EvaluationProvenance
) -> None:
    assert changed.identity != _BASE_PROVENANCE.identity, case


# --- cases 11-16: rejection ---------------------------------------------------------


def test_case_11_v1_preregistration_is_rejected(tmp_path: Path) -> None:
    payload = _prereg(_vm(_POPULATION)).model_dump()
    payload.pop("verification_manifest_hash")
    payload["spec_version"] = "m9-spec-frozen-oed7"
    with pytest.raises(ValidationError):
        PreRegistration.model_validate(payload)
    draft = _prereg(_vm(_POPULATION)).model_copy(
        update={"spec_version": "m9-spec-frozen-oed7", "identity": ""}
    )
    v1_lineage = draft.model_copy(update={"identity": draft.compute_identity()})
    with pytest.raises(ExecutionError, match="identity-v2 lineage"):
        run_preflight(
            preregistration=v1_lineage,
            evaluation_sink=EvaluationSink(tmp_path / "sink" / "heldout.jsonl"),
            results_dir=tmp_path / "results",
            a0_checkpoint_identity=_hex("a0"),
        )
    assert SPEC_VERSION == "m9-spec-frozen-oed7-vm2"


def test_case_12_v1_evaluation_record_cannot_bind_to_a_v2_preregistration() -> None:
    prereg = _prereg(_vm(_POPULATION))
    v1_identity = compute_content_hash(
        {
            "checkpoint_identity": prereg.checkpoint_identities[0],
            "manifest_hash": prereg.manifest_hash,
            "arm": Arm.A1.value,
            "base_model": prereg.base_model,
            "eval_seed": prereg.eval_seed,
            "max_tasks": prereg.max_tasks,
            "max_attempts_per_task": prereg.max_attempts_per_task,
            "max_tokens": prereg.max_tokens,
        }
    )
    record = EvaluationRecord(
        evaluation_identity=v1_identity,
        arm=Arm.A1.value,
        task_identity=_hex("task"),
        seed=0,
        verdict_state=VerdictState.PASSED,
        prompt_tokens=1,
        completion_tokens=1,
        model="m",
        model_version="1",
    )
    with pytest.raises(BinderError, match="unexpected evaluation_identity"):
        bind_observations(prereg, [record], a0_checkpoint_identity=_hex("a0"))


def test_case_13_missing_or_empty_verification_manifest_is_rejected() -> None:
    with pytest.raises(VerificationManifestError, match="empty held-out population"):
        build_verification_manifest((), _STORE)
    with pytest.raises(EvaluationProvenanceError):
        _provenance("")
    with pytest.raises(ValidationError):
        _prereg("")


def test_cases_15_and_16_duplicate_task_identity_is_rejected() -> None:
    same = (_held("M-1", _BASE), _held("M-1", _BASE))
    other = _blob("other")
    different = (_held("M-1", _BASE), _held("M-1", other))
    with pytest.raises(VerificationManifestError, match="the same TaskSpec digest"):
        build_verification_manifest(same, _STORE)
    with pytest.raises(VerificationManifestError, match="a different TaskSpec digest"):
        build_verification_manifest(different, InMemoryTaskSpecStore(_BASE, other))


# --- cases 17-18: ratified boundaries (Q-A/Q-E held-out-only; Q-D classifier) --------


def _write_corpus(root: Path, available_handle: str, held_handle: str) -> None:
    root.mkdir(parents=True)
    corpus = [
        {"label": "avail", "material": "M-avail", "handle": available_handle},
        {"label": "held", "material": "M-held", "handle": held_handle},
    ]
    (root / "corpus.json").write_text(json.dumps(corpus), encoding="utf-8")
    partition = {"M-avail": "available", "M-held": "held_out"}
    (root / "partition.json").write_text(json.dumps(partition), encoding="utf-8")


def test_case_17_available_task_taskspec_change_leaves_identity_unchanged(tmp_path: Path) -> None:
    """Intended held-out-only boundary; this does NOT claim available-task lineage is solved."""
    held = hashlib.sha256(_BASE).hexdigest()
    _write_corpus(tmp_path / "one", _hex("available-spec-1"), held)
    _write_corpus(tmp_path / "two", _hex("available-spec-2"), held)
    first = load_heldout_set(tmp_path / "one", tmp_path / "one" / "partition.json")
    second = load_heldout_set(tmp_path / "two", tmp_path / "two" / "partition.json")
    assert first.manifest_hash == second.manifest_hash
    assert _vm(first.tasks) == _vm(second.tasks)
    assert _provenance(_vm(first.tasks)).identity == _provenance(_vm(second.tasks)).identity


def test_case_18_classifier_identity_is_not_an_identity_component() -> None:
    payload = _provenance(_vm(_POPULATION)).to_dict()
    assert set(payload) == {
        "identity_version",
        "checkpoint_identity",
        "manifest_hash",
        "arm",
        "base_model",
        "eval_seed",
        "max_tasks",
        "max_attempts_per_task",
        "max_tokens",
        "verification_manifest_hash",
    }
    assert payload["identity_version"] == IDENTITY_VERSION
    assert not any("classifier" in key for key in payload)
    assert "classifier" not in PreRegistration.model_fields


# --- case 14 and §7: the runner's pre-attempt consistency check ----------------------


class RecordingProposer:
    def __init__(self) -> None:
        self.calls = 0

    def propose(self, task: Task, seed: int) -> Proposal:
        self.calls += 1
        return Proposal(
            patch="--- a/x\n+++ b/x\n",
            prompt=task.prompt,
            prompt_tokens=1,
            completion_tokens=1,
            latency_seconds=0.0,
            model="mock-model",
            model_version="mock-1",
        )


class StubVerifier:
    def verify(self, task: Task, patch: str) -> Verdict:
        return Verdict(state=VerdictState.PASSED, output="ok", duration_seconds=0.0)


class OneTaskAdapter:
    def materialize(self, corpus_task: CorpusTask) -> Task:
        return Task(
            task_id="t",
            repo_path=Path("tests/fixtures/calc_add_bug"),
            prompt="base task prompt",
            hidden_test_command=("python", "-m", "pytest", "-q"),
        )


def _sweep(
    tmp_path: Path,
    provenance_vm: str,
    *,
    store: InMemoryTaskSpecStore = _STORE,
    tasks: tuple[CorpusTask, ...] = _POPULATION,
    identity_version: str = IDENTITY_VERSION,
) -> tuple[RecordingProposer, EvaluationSink]:
    checkpoint = form_checkpoint(Arm.A1, EpisodeMemory(tmp_path / "none.jsonl"))
    heldout = HeldOutEvaluationSet(tasks=tasks, manifest_hash=_hex("manifest"))
    provenance = dataclasses.replace(
        _provenance(provenance_vm),
        checkpoint_identity=checkpoint.identity,
        identity_version=identity_version,
    )
    proposer = RecordingProposer()
    attempt = HeldOutAttempt(
        proposer=proposer,
        verifier=StubVerifier(),
        retriever=Retriever(get_embedder(EMBEDDER_NAME), 5),
        adapter=OneTaskAdapter(),
        eval_seed=0,
    )
    sink = EvaluationSink(tmp_path / "eval.jsonl")
    run_heldout_evaluation(
        checkpoint,
        heldout,
        provenance,
        attempt=attempt,
        sink=sink,
        guard=CostGuard(0, 1, 0),
        taskspec_store=store,
    )
    return proposer, sink


def test_matching_manifest_passes_the_runner_check(tmp_path: Path) -> None:
    proposer, sink = _sweep(tmp_path, _vm(_POPULATION))
    assert proposer.calls == len(_POPULATION)
    assert len(sink.read_all()) == len(_POPULATION)


def test_case_14_mismatched_manifest_hash_is_rejected_before_any_attempt(tmp_path: Path) -> None:
    with pytest.raises(EvaluationError, match="does not match"):
        _sweep(tmp_path, _hex("not-this-manifest"))
    assert (
        not (tmp_path / "eval.jsonl").exists()
        or not EvaluationSink(tmp_path / "eval.jsonl").read_all()
    )


@pytest.mark.parametrize(
    ("label", "tasks", "store"),
    [
        ("missing-taskspec", (_held("M-1", _blob("unstored")),), _STORE),
        ("duplicate-identity", (_held("M-1", _BASE), _held("M-1", _BASE)), _STORE),
        ("changed-taskspec", (_held("M-1", _BASE),), None),
    ],
)
def test_runner_rejects_an_invalid_manifest_before_any_attempt(
    tmp_path: Path,
    label: str,
    tasks: tuple[CorpusTask, ...],
    store: InMemoryTaskSpecStore | None,
) -> None:
    class ChangedStore(InMemoryTaskSpecStore):
        def read(self, digest: str) -> bytes | None:
            return b"changed content"

    active = ChangedStore() if store is None else store
    with pytest.raises(EvaluationError, match="held-out verification manifest is invalid"):
        _sweep(tmp_path, _vm(_POPULATION), store=active, tasks=tasks)


def test_runner_rejects_a_non_v2_identity_version(tmp_path: Path) -> None:
    with pytest.raises(EvaluationError, match="identity_version"):
        _sweep(tmp_path, _vm(_POPULATION), identity_version="m8-evaluation-identity-v1")
