"""The M9 statistical procedure is byte-identical under evaluation identity v2 (D29).

M9 Amendment VM2 changes identity and version plumbing only: GEE, EMM, Wald, trend,
McNemar, Holm, completeness (complete-case, VOID, OED-7), encoding and the K=1 / K>1
decision rules are unchanged. This test pins each of the nine statistical modules to its
SHA-256 at the frozen baseline ``1b0b7a09a41299ade38027cd17215fa42c2a7b09`` (tags
``m8-identity-v2-frozen`` / ``m9-spec-frozen-oed7-vm2``). Any byte change fails loudly.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import velith.analysis

#: SHA-256 of each M9 statistical module at the frozen baseline (1b0b7a0).
_FROZEN_STATISTICS_SHA256 = {
    "completeness": "80dfdadf4501a55f09edd7b0d8b9c19964e0fc7039db519dd541fd789fbb63b1",
    "decision": "5c159cbb0d50fed2e7c909e06e33983df1e30417abcdcc49795beaa1a70b02b7",
    "emm": "db02220719cba3859cf768d67716ad1ec84b850ebcab989668fe3c29594d8d1a",
    "encoding": "4fef68f3fdf44eaf23432882170cdfee9be462b131a4de81aaad23a8c87e47cd",
    "gee": "66f0e74004c4cd0a5a9f2287585690bc62ef12aa2366c27572d40c1281f3fa18",
    "holm": "44f6dad677a52efc0e2ab6c323913daf39dd6f3439addb40116742222072b5be",
    "mcnemar": "b65b066d2bfb3e8b14f7428052fadebfebc94d5a3b140f1025030cfb2b8eaae1",
    "trend": "6e814ddd3af3ecfe03b687a08cacfd53f4518cbfae8b3083ff6d3e99a8c71aa3",
    "wald": "9a28e334d58b00e15e700249ddeca53c52aa38d074b010a69ff3995b5e496f23",
}


@pytest.mark.parametrize("module", sorted(_FROZEN_STATISTICS_SHA256))
def test_statistical_module_is_byte_identical_to_the_frozen_baseline(module: str) -> None:
    assert velith.analysis.__file__ is not None
    source = Path(velith.analysis.__file__).parent / f"{module}.py"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == _FROZEN_STATISTICS_SHA256[module]
