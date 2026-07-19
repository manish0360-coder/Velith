"""Write-filter policies: the experiment's single manipulated variable (M7-C2).

A write-filter is a **deterministic, domain-neutral admission predicate** over an
already-persisted episode (M7_SPEC §3.2). It decides what an arm *retains in memory* —
it never deletes, mutates, or re-orders a grounding record, which stays in the
authoritative log exactly as the frozen store wrote it (D2/D3/D16.7).

Admission is decided **solely** by the triple
(``verdict_state``, ``secondary_passed``, ``flaky``) — neutral, already-grounded
outcome provenance the frozen episode already carries. No filter inspects the task's
material, prompt, or change (D9/D22), so a non-software episode filters through the
identical path.

Two policies, and only two (M7_SPEC §3.2):

* **Unfiltered** (arm A1) — admits **every** episode regardless of outcome: every
  verdict category, contradicted or uncontradicted by the secondary, flaky or not.
  This is the RAG/null control (D7): it isolates what plain retrieval of experience
  contributes, with no grounding filter.
* **Verified** (arm A2) — admits **exactly** a *verified success* and a *verified
  failure*, and nothing else. This is the verification-filtered treatment.

Scope: policies only. The arm-to-filter binding is M7-C3 and the memory view is
M7-C5, so this module deliberately names no arm. Standard library plus the frozen
episode schema only.
"""

from __future__ import annotations

from typing import Protocol

from velith.episodes.episode import Episode, VerdictState


class WriteFilter(Protocol):
    """A deterministic, domain-neutral admission predicate over a persisted episode.

    Implementations are pure: the same episode always yields the same decision, and
    nothing outside the (``verdict_state``, ``secondary_passed``, ``flaky``) triple is
    consulted.
    """

    def admits(self, episode: Episode) -> bool:
        """Return ``True`` iff this policy retains ``episode`` in the arm's memory."""
        ...


def is_verified_success(episode: Episode) -> bool:
    """Return ``True`` iff ``episode`` is a *verified success* (M7_SPEC §3.2).

    Both conditions must hold: the verdict is ``PASSED`` — the sole admitted success
    category — **and** the held-out secondary does not contradict it, i.e.
    ``secondary_passed`` is ``True`` or absent (``None``, no secondary was run).

    ``secondary_passed is False`` is excluded: the primary suite passed while the
    held-out suite refuted it, which is precisely the model gap (D21) — a solution
    satisfying the visible test without solving the task. Retaining it as knowledge
    would seed memory with the exact wireheading the program exists to detect.
    """
    return episode.verdict_state is VerdictState.PASSED and episode.secondary_passed is not False


def is_verified_failure(episode: Episode) -> bool:
    """Return ``True`` iff ``episode`` is a *verified failure* (M7_SPEC §3.2).

    The verdict is ``FAILED`` — the sole admitted failure category. It means a
    candidate was produced, applied, and actually **disposed of by the verifier**: the
    hidden test ran and returned a negative result. That is a real measurement of
    reality, first-class learning data, never an error (D16.7).

    The secondary signal does not gate admission here: there is no success claim for
    the held-out suite to contradict.
    """
    return episode.verdict_state is VerdictState.FAILED


class UnfilteredWriteFilter:
    """Arm A1's policy: retain everything — the RAG/null control (D7)."""

    def admits(self, episode: Episode) -> bool:
        """Admit every episode, in every verdict category, flaky or not."""
        return True


class VerifiedWriteFilter:
    """Arm A2's policy: retain only trustworthy grounded verification signal (D7).

    Admits exactly a verified success or a verified failure. The exhaustive complement
    is excluded (M7_SPEC §3.2):

    * ``PATCH_APPLY_FAILED`` — a candidate existed but never reached the hidden test,
      so **no verification occurred**; only a mechanical failure to apply.
    * ``NO_PATCH`` — no candidate was produced at all; nothing was verified.
    * ``INFRA_ERROR`` — not a grounded outcome but a failure of the loop itself
      (D16.7).
    * ``PASSED`` contradicted by the held-out secondary — the model gap (D21).
    * **Any** episode flagged ``flaky``, in **every** category above, including an
      otherwise-qualifying ``PASSED`` or ``FAILED``: flake detection marks the
      *measurement* as untrustworthy (D17), and an untrustworthy measurement is by
      definition not verified signal.
    """

    def admits(self, episode: Episode) -> bool:
        """Admit only an unflaky verified success or verified failure."""
        if episode.flaky:
            return False
        return is_verified_success(episode) or is_verified_failure(episode)
