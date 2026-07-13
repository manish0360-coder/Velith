"""Deterministic, domain-neutral embedding and similarity (M6-C3).

The single shared component that maps opaque text into a comparable space under a fixed
similarity metric (M6_SPEC §3.3). It is **deterministic** — the same opaque input yields
the same representation with no sampling and no run-to-run drift — and **domain-neutral**:
it embeds opaque content via content-addressed hashing (``hashlib.blake2b``, not the
randomized builtin ``hash``), so the representation is independent of process and
``PYTHONHASHSEED``, and it never interprets a domain (D9/D22). There is exactly **one**
component (no routing); a higher-fidelity embedder is a registration behind
:class:`Embedder` and is out of scope (M6_SPEC §8). Standard library only.
"""

from __future__ import annotations

import hashlib
from typing import Protocol

#: Dimensionality of the reference embedding's integer vector.
_DIMENSIONS = 256
#: Opaque n-gram width over the encoded bytes.
_NGRAM = 3

#: A deterministic embedding: a fixed-length vector of non-negative integer counts.
Embedding = tuple[int, ...]

#: Canonical identity of the single fixed reference embedder (config ``retrieval_embedder``).
EMBEDDER_NAME = "hashed-ngram"


class EmbedderError(Exception):
    """Raised when an unsupported embedder identity is requested.

    M6_SPEC §3.3 admits exactly one component (no routing); an unrecognised identity is a
    loud, typed failure — never silent.
    """


class Embedder(Protocol):
    """The single shared embedding/similarity interface (M6_SPEC §3.3)."""

    def embed(self, text: str) -> Embedding:
        """Map opaque ``text`` to its deterministic representation."""
        ...

    def similarity(self, a: Embedding, b: Embedding) -> int:
        """Return the fixed, deterministic similarity between two representations."""
        ...


def _bucket(gram: bytes) -> int:
    return int.from_bytes(hashlib.blake2b(gram, digest_size=8).digest(), "big") % _DIMENSIONS


class HashedNgramEmbedder:
    """The deterministic reference embedder (M6_SPEC §3.3).

    Embeds opaque text as a fixed-length vector of content-addressed byte-n-gram counts,
    and scores similarity by integer dot product. Deterministic and process-independent:
    it uses ``hashlib`` (not the randomized builtin ``hash``) and integer arithmetic only,
    so there is no run-to-run or cross-process drift. It never interprets a domain.
    """

    def embed(self, text: str) -> Embedding:
        """Return the deterministic integer-count representation of opaque ``text``."""
        vector = [0] * _DIMENSIONS
        data = text.encode("utf-8")
        for i in range(max(1, len(data) - _NGRAM + 1)):
            vector[_bucket(data[i : i + _NGRAM])] += 1
        return tuple(vector)

    def similarity(self, a: Embedding, b: Embedding) -> int:
        """Return the integer dot product of two representations (fixed metric)."""
        return sum(x * y for x, y in zip(a, b, strict=True))


def get_embedder(name: str) -> Embedder:
    """Return the single shared embedder for ``name`` (M6_SPEC §3.3; no routing).

    Exactly one component is supported; an unrecognised identity raises
    :class:`EmbedderError` (fail loud, M0 §10). This is a single-valued binding of the
    configured ``retrieval_embedder`` identity to the one reference component — not routing.
    """
    if name != EMBEDDER_NAME:
        raise EmbedderError(
            f"unsupported embedder {name!r}; the only component is {EMBEDDER_NAME!r}"
        )
    return HashedNgramEmbedder()
