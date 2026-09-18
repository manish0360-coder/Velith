"""Write-once, segregated persistence for the M9 pre-registration (M9-C2 / P1).

The store writes the single immutable pre-registration to its own location (M9_SPEC §5),
**distinct from the experience log and the evaluation sink** (§3.3/§3.4). It never imports
the episode store, the evaluation sink, or any held-out record surface — a pre-registration
cannot reach the experience path, and this store reads no held-out outcome.

Write-once and never mutated (§3.3): re-writing the *same* identity is idempotent; writing
a *different* identity to an existing location is refused. Reads verify integrity by
recomputing the content-addressed identity.
"""

from __future__ import annotations

from pathlib import Path

from velith.analysis.preregistration import PreRegistration, PreRegistrationError


class PreRegistrationStore:
    """An append-once JSON store for the immutable M9 pre-registration record."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        """The pre-registration location (distinct from the experience log and sink)."""
        return self._path

    def exists(self) -> bool:
        """Return ``True`` iff a pre-registration has already been written."""
        return self._path.exists()

    def write(self, prereg: PreRegistration) -> None:
        """Write the pre-registration once; refuse to mutate a different one (§3.3).

        Idempotent for an identical identity; raises :class:`PreRegistrationError` if a
        pre-registration with a different identity already exists, or if ``prereg`` fails
        its own integrity check.
        """
        if not prereg.verify_identity():
            raise PreRegistrationError(
                "refusing to write a pre-registration whose stored identity does not match "
                "its recomputed content-addressed identity"
            )
        if self._path.exists():
            existing = self.read()
            if existing.identity != prereg.identity:
                raise PreRegistrationError(
                    "refusing to mutate a frozen pre-registration: existing identity "
                    f"{existing.identity} != {prereg.identity}"
                )
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(prereg.model_dump_json() + "\n", encoding="utf-8")

    def read(self) -> PreRegistration:
        """Load the stored pre-registration and verify its content-addressed integrity."""
        if not self._path.exists():
            raise PreRegistrationError(f"no pre-registration at {self._path}")
        loaded = PreRegistration.model_validate_json(self._path.read_text(encoding="utf-8"))
        if not loaded.verify_identity():
            raise PreRegistrationError(
                "pre-registration integrity check failed: stored identity "
                f"{loaded.identity} != recomputed {loaded.compute_identity()}"
            )
        return loaded
