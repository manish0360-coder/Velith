"""The M9 pre-registration record and its content-addressed identity (M9-C2 / P1).

An immutable :class:`PreRegistration` encodes the frozen M9 **experiment design**
(M9_SPEC §3.1) and **analysis plan** (§3.2/§3.5) as a single record carrying a
**content-addressed identity** computed by the *same* canonical serialization the frozen
episode and M8 evaluation identity use (§3.3, D16.1/D18): sorted keys, tight separators,
UTF-8, SHA-256. The same plan always yields the same identity; any change to any
component — an arm, the split, a checkpoint identity, checkpoint membership or order, the
endpoint, the statistic, or the threshold — yields a new identity.

This module **declares** the plan; it runs no statistic (that is M10). It is sealed from
results (§3.4): it imports only the canonical hash utility and the frozen ``Arm`` set,
never the evaluation sink/records or the episode store, and it reads no held-out outcome.

Checkpoint binding is by **concrete content-addressed M8 checkpoint identity** only — a
SHA-256 hex digest — never a semantic label, name, ordinal position, or mutable alias
(§3.1, RD checkpoint-binding ruling). Non-concrete bindings are refused at construction.
"""

from __future__ import annotations

import re
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, field_validator

from velith.arms.identity import Arm
from velith.episodes.episode import compute_content_hash

# --- Frozen M9 plan constants (transcribed from m9-spec-frozen-oed7; not decisions) ----
#: The frozen M9 specification lineage this pre-registration is extracted from.
SPEC_VERSION: Final[str] = "m9-spec-frozen-oed7"
#: The single verifier-derived endpoint: PASSED = 1, every other verdict = 0 (§3.5.1).
PRIMARY_ENDPOINT: Final[str] = "binary_passed"
#: The closed-set statistic identifier: K>1 GEE (EMM + trend) and K=1 exact McNemar (§3.5).
STATISTIC_IDENTIFIER: Final[str] = "m9_kgt1_gee_emm_trend__k1_exact_mcnemar__holm"
#: The pre-committed family-wise go/no-go level (§3.5.4-§3.5.8).
ALPHA: Final[float] = 0.01
#: The GO/NO-GO rule: GO iff every confirmatory hypothesis is rejected under Holm (§3.5.8).
DECISION_RULE: Final[str] = "holm_all_reject_go_else_nogo"
#: Per-task complete-case exclusion for missing task-checkpoint-arm records (§3.5.1).
MISSING_DATA_RULE: Final[str] = "complete_case_exclusion"
#: Global M8 incompleteness voids the analysis (§3.5.1).
GLOBAL_INCOMPLETE_DISPOSITION: Final[str] = "VOID"
#: OED-7 (§3.5.11): n=0 after complete-case exclusion is a procedural VOID, not a NO-GO.
EMPTY_DATASET_DISPOSITION: Final[str] = "VOID"
#: Confirmatory Holm family sizes: two tests for K=1, four for K>1 (§3.5.5/§3.5.6).
K1_FAMILY_SIZE: Final[int] = 2
KGT1_FAMILY_SIZE: Final[int] = 4
#: OED-2 (§3.5.3): A0 is time-invariant — one observation per task, not replicated across K.
A0_TIME_INVARIANT: Final[bool] = True
#: OED-2 (§3.5.3): A0's single observation enters the K>1 model at checkpoint_id_c = 0.
A0_CHECKPOINT_ID_C: Final[int] = 0

#: The closed arm set in pre-registration order (frozen A0/A1/A2).
ARMS: Final[tuple[str, ...]] = (Arm.A0.value, Arm.A1.value, Arm.A2.value)

#: A concrete content-addressed identity is a lowercase SHA-256 hex digest (64 chars).
_SHA256_HEX: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")

#: Closed set of admissible declared statistic identifiers (M9_SPEC §5).
_ALLOWED_STATISTICS: Final[frozenset[str]] = frozenset({STATISTIC_IDENTIFIER})


class PreRegistrationError(Exception):
    """Raised on an invalid, non-concrete, or mutating pre-registration operation."""


class PreRegistration(BaseModel):
    """An immutable, content-addressed M9 pre-registration (design + analysis plan).

    Frozen and ``extra="forbid"``: the record cannot be mutated or grow undeclared
    fields. Construct via :meth:`build`, which stamps the frozen plan constants and
    computes the identity; direct construction is for deserialization where the identity
    is supplied (and re-verified via :meth:`verify_identity`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # --- Experiment design (§3.1) ---
    spec_version: str
    arms: tuple[str, ...]
    manifest_hash: str
    checkpoint_identities: tuple[str, ...]
    base_model: str
    eval_seed: int
    max_tasks: int
    max_attempts_per_task: int
    max_tokens: int
    # --- Analysis-plan declaration (§3.2/§3.5) ---
    primary_endpoint: str
    statistic_identifier: str
    alpha: float
    decision_rule: str
    missing_data_rule: str
    global_incomplete_disposition: str
    empty_dataset_disposition: str
    k1_family_size: int
    kgt1_family_size: int
    a0_time_invariant: bool
    a0_checkpoint_id_c: int
    # --- Content-addressed identity (derived; excluded from the hashed content) ---
    identity: str

    @field_validator("checkpoint_identities")
    @classmethod
    def _validate_checkpoints(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("checkpoint schedule must contain at least one checkpoint identity")
        for checkpoint in value:
            if not _SHA256_HEX.match(checkpoint):
                raise ValueError(
                    "checkpoint identity is not a concrete content-addressed SHA-256 hex "
                    f"digest: {checkpoint!r}"
                )
        return value

    @field_validator("manifest_hash")
    @classmethod
    def _validate_manifest(cls, value: str) -> str:
        if not _SHA256_HEX.match(value):
            raise ValueError(
                f"manifest_hash is not a concrete content-addressed SHA-256 hex digest: {value!r}"
            )
        return value

    def _content(self) -> dict[str, Any]:
        """The declared components hashed into the identity (everything but ``identity``)."""
        content = self.model_dump()
        content.pop("identity")
        return content

    def compute_identity(self) -> str:
        """Return the content-addressed identity over the declared components (§3.3)."""
        return compute_content_hash(self._content())

    def verify_identity(self) -> bool:
        """Return ``True`` iff the stored identity matches the recomputed identity."""
        return self.identity == self.compute_identity()

    @classmethod
    def build(
        cls,
        *,
        manifest_hash: str,
        checkpoint_identities: tuple[str, ...],
        base_model: str,
        eval_seed: int,
        max_tasks: int,
        max_attempts_per_task: int,
        max_tokens: int,
        statistic_identifier: str = STATISTIC_IDENTIFIER,
        alpha: float = ALPHA,
    ) -> PreRegistration:
        """Assemble a pre-registration from the design inputs and the frozen plan.

        The analysis-plan fields are stamped from the frozen constants; the statistic
        identifier is validated against the closed set and the threshold against the
        frozen ``ALPHA`` (M9_SPEC §5) — the frozen scientific decisions are enforced, not
        chosen. The identity is computed over all declared components.
        """
        if statistic_identifier not in _ALLOWED_STATISTICS:
            raise PreRegistrationError(
                f"statistic_identifier {statistic_identifier!r} is not in the closed set "
                f"{sorted(_ALLOWED_STATISTICS)}"
            )
        if alpha != ALPHA:
            raise PreRegistrationError(
                f"alpha {alpha!r} is not the frozen family-wise level {ALPHA!r}"
            )
        draft = cls(
            spec_version=SPEC_VERSION,
            arms=ARMS,
            manifest_hash=manifest_hash,
            checkpoint_identities=tuple(checkpoint_identities),
            base_model=base_model,
            eval_seed=eval_seed,
            max_tasks=max_tasks,
            max_attempts_per_task=max_attempts_per_task,
            max_tokens=max_tokens,
            primary_endpoint=PRIMARY_ENDPOINT,
            statistic_identifier=statistic_identifier,
            alpha=alpha,
            decision_rule=DECISION_RULE,
            missing_data_rule=MISSING_DATA_RULE,
            global_incomplete_disposition=GLOBAL_INCOMPLETE_DISPOSITION,
            empty_dataset_disposition=EMPTY_DATASET_DISPOSITION,
            k1_family_size=K1_FAMILY_SIZE,
            kgt1_family_size=KGT1_FAMILY_SIZE,
            a0_time_invariant=A0_TIME_INVARIANT,
            a0_checkpoint_id_c=A0_CHECKPOINT_ID_C,
            identity="",
        )
        return draft.model_copy(update={"identity": draft.compute_identity()})
