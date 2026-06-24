"""The Episode record and its canonical content hash (M1 spec §9.1 / §9.1.1).

An :class:`Episode` is a provenance-complete account of one ``propose → verify →
log`` attempt: the task, the proposal, the verdict, and the cost/timing signals,
plus a SHA-256 ``content_hash`` over the episode's *content* fields so tampering
is detectable on read (invariant I2).

Two rules are **frozen here and defined nowhere else** (this module is the single
authority, M1 spec §9.1.1):

1. **Canonical serialization** — ``json.dumps(content, sort_keys=True,
   ensure_ascii=False, separators=(",", ":"))``, UTF-8 encoded, then SHA-256.
   A naive dump is not stable across machines (dict ordering, whitespace,
   non-ASCII), which would make the hash drift; this rule removes that drift.
2. **The hash boundary** — the hash covers content fields only and **excludes**
   the volatile/timing fields (``timestamp``, ``latency_seconds``,
   ``verify_seconds``) and ``content_hash`` itself. Excluding them is mandatory,
   not stylistic: D16.1 requires that the *same recorded proposal* re-verified
   twice yields the same verdict **and the same hash**, which is impossible if
   wall-clock fields are inside the boundary (RK14).

Scope (M1 handoff §4.1): schema + hash only. No storage I/O, no querying, no
indexing, no arm logic — the ``arm`` field exists for forward-compatibility with
D7's experiment arms but nothing keys off it in M1.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Final

from pydantic import BaseModel, ConfigDict


class VerdictState(str, Enum):
    """The closed set of task-attempt outcomes (M1 spec §10, D16.7).

    Only ``INFRA_ERROR`` is an error (the loop could not run); the other four are
    valid *grounded outcomes* that must be logged, never raised. This vocabulary
    lives here because the episode schema is the earliest module with no internal
    dependencies and an episode's verdict is fundamentally recorded data.
    """

    PASSED = "PASSED"
    FAILED = "FAILED"
    PATCH_APPLY_FAILED = "PATCH_APPLY_FAILED"
    NO_PATCH = "NO_PATCH"
    INFRA_ERROR = "INFRA_ERROR"


# The single fixed ``arm`` value for M1. The field exists for forward-compat with
# D7's arms (A0–A4); no arm logic is built until M5+ — this is just a constant.
DEFAULT_ARM: Final[str] = "baseline"

# The hash boundary, defined once. Content fields that ARE hashed:
HASH_BOUNDARY_FIELDS: Final[tuple[str, ...]] = (
    "task_id",
    "seed",
    "arm",
    "model",
    "model_version",
    "prompt",
    "patch",
    "verdict_state",
    "verdict_output",
    "secondary_passed",
    "prompt_tokens",
    "completion_tokens",
    "velith_version",
)

# Fields recorded in the episode but deliberately OUTSIDE the hash boundary
# (volatile/timing + the hash itself). See §9.1.1 / RK14.
HASH_EXCLUDED_FIELDS: Final[tuple[str, ...]] = (
    "timestamp",
    "latency_seconds",
    "verify_seconds",
    "content_hash",
)


def compute_content_hash(content: Mapping[str, Any]) -> str:
    """Return the SHA-256 hex digest of ``content`` under the canonical rule.

    ``content`` must contain exactly the hash-boundary fields. The serialization
    is sorted and tightly separated so the same content always hashes the same,
    regardless of insertion order or machine.
    """
    canonical = json.dumps(
        content,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class Episode(BaseModel):
    """A provenance-complete, content-hashed record of one task attempt.

    Frozen and ``extra="forbid"``: an episode is immutable once built and cannot
    silently grow undeclared fields. Construct via :meth:`build`, which computes
    the ``content_hash`` for you; direct construction is for tests/deserialization
    where the hash is supplied.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # --- Content fields (INSIDE the hash boundary) ---
    task_id: str
    seed: int
    arm: str = DEFAULT_ARM
    model: str
    model_version: str
    prompt: str
    patch: str
    verdict_state: VerdictState
    verdict_output: str
    secondary_passed: bool | None = None
    prompt_tokens: int
    completion_tokens: int
    velith_version: str

    # --- Provenance/timing fields (OUTSIDE the hash boundary) ---
    timestamp: str
    latency_seconds: float
    verify_seconds: float

    # --- Integrity (OUTSIDE the boundary; derived from the content fields) ---
    content_hash: str

    def content_for_hash(self) -> dict[str, Any]:
        """Project this episode onto exactly the hash-boundary fields."""
        content: dict[str, Any] = {name: getattr(self, name) for name in HASH_BOUNDARY_FIELDS}
        # Serialize the enum by its string value for a stable, explicit payload.
        content["verdict_state"] = self.verdict_state.value
        return content

    def compute_hash(self) -> str:
        """Recompute this episode's content hash from its content fields."""
        return compute_content_hash(self.content_for_hash())

    def verify_hash(self) -> bool:
        """Return ``True`` iff the stored ``content_hash`` matches the content."""
        return self.compute_hash() == self.content_hash

    @classmethod
    def build(
        cls,
        *,
        task_id: str,
        seed: int,
        model: str,
        model_version: str,
        prompt: str,
        patch: str,
        verdict_state: VerdictState,
        verdict_output: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_seconds: float,
        verify_seconds: float,
        velith_version: str,
        arm: str = DEFAULT_ARM,
        secondary_passed: bool | None = None,
        timestamp: str | None = None,
    ) -> Episode:
        """Assemble an episode and compute its content hash.

        The orchestrator (C7) calls this with the proposal, verdict, and run
        context. ``timestamp`` defaults to the current UTC time in ISO-8601;
        ``secondary_passed`` stays ``None`` in M1 (M2 populates it).
        """
        resolved_timestamp = timestamp if timestamp is not None else datetime.now(UTC).isoformat()
        # Build with a placeholder hash, then compute the real one from the
        # content fields. content_hash is outside the boundary, so the
        # placeholder cannot influence the result.
        draft = cls(
            task_id=task_id,
            seed=seed,
            arm=arm,
            model=model,
            model_version=model_version,
            prompt=prompt,
            patch=patch,
            verdict_state=verdict_state,
            verdict_output=verdict_output,
            secondary_passed=secondary_passed,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            velith_version=velith_version,
            timestamp=resolved_timestamp,
            latency_seconds=latency_seconds,
            verify_seconds=verify_seconds,
            content_hash="",
        )
        return draft.model_copy(update={"content_hash": draft.compute_hash()})
