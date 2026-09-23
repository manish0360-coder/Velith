"""Content-addressed analysis result record for M9 (M9-C12 / P2 item 13, handoff §9).

This module **records** an already-computed analysis. It is the last value in the M9
executor chain and the only one that touches the filesystem on the results side.

It computes **no** statistic: every number it stores was produced by C3-C11. It does not
recompute p-values, re-run Holm, reach a second GO/NO-GO decision, alter or clip a p-value,
reinterpret a ``GeeFailure``, detect separation, threshold a standard error, read the M8
evaluation sink, or write through ``GuardedEpisodeWriter``, the episode store, or memory.

**Identity (RD ruling Q2 — complete-artifact hashing).** The identity covers the *entire*
payload, excluding only the ``identity`` field itself::

    payload = record.to_dict()
    payload.pop("identity", None)
    identity = compute_content_hash(payload)

``compute_content_hash`` is the project's existing canonical serialization (sorted keys,
tight separators, UTF-8, SHA-256) already used by the frozen episode, the M8 evaluation
provenance, and the M9 pre-registration — reused here per handoff §9, never reimplemented.
Because the hash boundary is the whole payload, changing **any** component — a p-value, a
Holm threshold, the decision, the completeness metadata, or any provenance field — yields a
different identity.

**Provenance (handoff §9).** The record is reproducible from the pre-registration
``identity``, the ordered checkpoint identities, the held-out ``manifest_hash``, the
selected ``evaluation_identity`` set, the implementation version, the statistical-library
name and version, the configuration, and the deterministic seed/index construction.

**Persistence (RD ruling Q3 — segregation only).** ``write_result_record`` takes an
explicit ``results_dir`` supplied by the caller; no ``Settings`` field, no configuration
plumbing. The record is written once to ``{results_dir}/{identity}.json`` and an existing
target raises :class:`FileExistsError` — the file is opened with mode ``"x"``, so the
write-once check is atomic rather than a check-then-write race.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Final

from velith import __version__
from velith.analysis.completeness import CompletenessResult
from velith.analysis.decision import DecisionResult
from velith.analysis.gee import SolverProvenance
from velith.analysis.holm import HolmResult
from velith.analysis.preregistration import PreRegistration
from velith.episodes.episode import compute_content_hash
from velith.evaluation.record import EvaluationRecord

#: The statistical library named by handoff §9 / OED-3. Present only on the K>1 GEE path;
#: the frozen K=1 McNemar procedure uses the standard library alone.
STATISTICAL_LIBRARY: Final[str] = "statsmodels"


class ResultRecordError(Exception):
    """Raised on a structural failure while assembling or verifying a result record.

    A loud halt for malformed input or a failed integrity check. It is never a statistical
    outcome: GO / NO-GO / VOID are decided upstream and only recorded here.
    """


def extract_evaluation_identities(records: Iterable[EvaluationRecord]) -> tuple[str, ...]:
    """The unique ``evaluation_identity`` set, deterministically sorted (handoff §9).

    Taken directly from the supplied records — the binder is not modified and no join key
    is recomputed. Duplicates collapse; the order is lexicographic so the value is stable
    across processes and machines.
    """
    return tuple(sorted({record.evaluation_identity for record in records}))


@dataclass(frozen=True)
class HypothesisRecord:
    """One hypothesis exactly as Holm decided it (C6) — recorded, never re-derived."""

    label: str
    p_value: float
    rank: int
    threshold: float
    rejected: bool


@dataclass(frozen=True)
class AnalysisProvenance:
    """The handoff §9 provenance block.

    The statistical-library and solver fields are ``None`` / empty on the frozen K=1 path,
    which fits no GEE and therefore has no solver configuration to record.
    """

    preregistration_identity: str
    checkpoint_identities: tuple[str, ...]
    manifest_hash: str
    evaluation_identities: tuple[str, ...]
    implementation_version: str
    eval_seed: int
    checkpoint_values: tuple[float, ...]
    statistical_library: str | None
    statistical_library_version: str | None
    numpy_version: str | None
    solver_configuration: tuple[tuple[str, str], ...]
    thread_configuration: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class AnalysisResultRecord:
    """The immutable, content-addressed record of one completed M9 analysis.

    ``hypotheses`` preserves the Holm ordering (ascending rank) with each hypothesis's
    p-value and threshold stored exactly as computed upstream.
    """

    outcome: str
    reason: str
    alpha: float
    family_size: int
    hypotheses: tuple[HypothesisRecord, ...]
    completeness_status: str
    n_included_tasks: int
    included_task_identities: tuple[str, ...]
    excluded_task_identities: tuple[str, ...]
    provenance: AnalysisProvenance
    identity: str

    def to_dict(self) -> dict[str, Any]:
        """The complete payload as plain JSON-serializable data, identity included."""
        return asdict(self)

    def compute_identity(self) -> str:
        """The content-addressed identity over the complete payload minus ``identity``."""
        payload = self.to_dict()
        payload.pop("identity", None)
        return compute_content_hash(payload)

    def verify_identity(self) -> bool:
        """Return ``True`` iff the stored identity matches the recomputed identity."""
        return self.identity == self.compute_identity()


def _solver_configuration(provenance: SolverProvenance) -> tuple[tuple[str, str], ...]:
    """The recorded solver configuration as ordered, JSON-stable key/value pairs."""
    return (
        ("family", provenance.family),
        ("link", provenance.link),
        ("cov_struct", provenance.cov_struct),
        ("cov_type", provenance.cov_type),
        ("maxiter", str(provenance.maxiter)),
        ("ctol", repr(provenance.ctol)),
        ("start_params", provenance.start_params),
    )


def build_result_record(
    *,
    preregistration: PreRegistration,
    completeness: CompletenessResult,
    holm_result: HolmResult,
    decision: DecisionResult,
    evaluation_records: Iterable[EvaluationRecord],
    solver_provenance: SolverProvenance | None = None,
    checkpoint_values: Sequence[float] = (),
) -> AnalysisResultRecord:
    """Assemble the immutable result record from already-computed upstream values.

    Every field is copied from its upstream source; nothing is recomputed, reinterpreted,
    or adjusted. The identity is computed last, over the complete payload.
    """
    provenance = AnalysisProvenance(
        preregistration_identity=preregistration.identity,
        checkpoint_identities=tuple(preregistration.checkpoint_identities),
        manifest_hash=preregistration.manifest_hash,
        evaluation_identities=extract_evaluation_identities(evaluation_records),
        implementation_version=__version__,
        eval_seed=preregistration.eval_seed,
        checkpoint_values=tuple(checkpoint_values),
        statistical_library=None if solver_provenance is None else STATISTICAL_LIBRARY,
        statistical_library_version=(
            None if solver_provenance is None else solver_provenance.statsmodels_version
        ),
        numpy_version=None if solver_provenance is None else solver_provenance.numpy_version,
        solver_configuration=(
            () if solver_provenance is None else _solver_configuration(solver_provenance)
        ),
        thread_configuration=(
            () if solver_provenance is None else tuple(solver_provenance.thread_env)
        ),
    )
    hypotheses = tuple(
        HypothesisRecord(
            label=entry.label,
            p_value=entry.p_value,
            rank=entry.rank,
            threshold=entry.threshold,
            rejected=entry.rejected,
        )
        for entry in holm_result.decisions
    )
    draft = AnalysisResultRecord(
        outcome=decision.outcome.value,
        reason=decision.reason,
        alpha=holm_result.alpha,
        family_size=holm_result.family_size,
        hypotheses=hypotheses,
        completeness_status=completeness.status.value,
        n_included_tasks=completeness.n,
        included_task_identities=tuple(completeness.included_task_identities),
        excluded_task_identities=tuple(completeness.excluded_task_identities),
        provenance=provenance,
        identity="",
    )
    # ``replace`` preserves the nested dataclasses; rebuilding from ``to_dict()`` would
    # substitute plain dicts for AnalysisProvenance and HypothesisRecord.
    return replace(draft, identity=draft.compute_identity())


def serialize_result_record(record: AnalysisResultRecord) -> str:
    """The record as canonical JSON — the same serialization the identity is taken over."""
    return json.dumps(
        record.to_dict(),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def write_result_record(record: AnalysisResultRecord, results_dir: Path | str) -> Path:
    """Write the record once to ``{results_dir}/{identity}.json`` (handoff §9).

    ``results_dir`` is supplied explicitly by the caller — this module reads no ``Settings``
    and adds no configuration. The results location is segregated from the experience log
    and the evaluation sink by construction: nothing here imports a write surface.

    Raises :class:`FileExistsError` if the target already exists — a result record is never
    overwritten. Raises :class:`ResultRecordError` if the record's identity does not match
    its payload.
    """
    if not record.verify_identity():
        raise ResultRecordError(
            "refusing to write a result record whose stored identity does not match its "
            "recomputed content-addressed identity"
        )
    directory = Path(results_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{record.identity}.json"
    # Mode "x" makes the write-once check atomic: it raises FileExistsError itself rather
    # than leaving a check-then-write window.
    with target.open("x", encoding="utf-8") as handle:
        handle.write(serialize_result_record(record) + "\n")
    return target
