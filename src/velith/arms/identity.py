"""Arm identity: the closed M7 arm set alongside the frozen A0 (M7-C1).

Scope (M7_SPEC §3.1 / handoff §6 M7-C1): **identity only** — no filter logic
(M7-C2), no arm-to-filter binding (M7-C3), and no memory access (M7-C5). This module
names the arms and nothing else, so it deliberately imports nothing from ``velith``.

An arm is recorded on each episode through the **frozen** ``arm`` provenance field,
so :class:`Arm` is a ``str`` enum and its members *are* the recorded values — no
translation layer exists or is needed.

Three arms are named here:

* ``A0`` — the frozen cold baseline (memoryless, M5). It is **untouched** by M7 and
  is *not* a member of the M7 arm set; it is present so the M7 arms are stated
  alongside it. Its value is fixed by the frozen ``batch.runner.COLD_ARM``; that
  module is not imported (it pulls in the whole propose/verify chain), so agreement
  is pinned by a permanent test instead.
* ``A1`` — unfiltered memory: the RAG/null control (D7).
* ``A2`` — verified memory: the verification-filtered treatment (D7).

The M7 arm set is **closed** to A1 and A2. The anti-grounding arm A3 and the
ablation arm A4 of D7 are out of scope (M7_SPEC §8) and are absent by construction.
"""

from __future__ import annotations

from enum import Enum
from typing import Final


class Arm(str, Enum):
    """An experiment arm, identified by its frozen ``arm`` provenance value (D7).

    A ``str`` enum because the member is written verbatim into the frozen episode's
    ``arm`` field; ``Arm.A1`` and ``"A1"`` are interchangeable at that boundary.
    """

    #: The frozen cold baseline: no memory read or written (M5). Not an M7 arm.
    A0 = "A0"
    #: Unfiltered memory - every episode retained regardless of outcome (D7).
    A1 = "A1"
    #: Verified memory - only trustworthy grounded verification signal (D7).
    A2 = "A2"


#: The **closed** M7 arm set (M7_SPEC §3.1). A0 is excluded: it is the frozen
#: memoryless baseline, not an arm M7 introduces. A3/A4 are out of scope (§8).
M7_ARMS: Final[tuple[Arm, ...]] = (Arm.A1, Arm.A2)
