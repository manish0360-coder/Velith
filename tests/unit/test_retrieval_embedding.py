"""Unit tests for deterministic embedding/similarity (M6-C3).

Scope: the same opaque input always yields the same representation (no run-to-run
drift); the similarity metric is fixed and deterministic; the component is single (no
routing); and opaque non-software input is embedded without interpretation (M6_SPEC §3.3).
"""

from __future__ import annotations

import pytest

from velith.retrieval.embedding import (
    EMBEDDER_NAME,
    Embedder,
    EmbedderError,
    HashedNgramEmbedder,
    get_embedder,
)


def test_embed_is_deterministic() -> None:
    embedder = HashedNgramEmbedder()
    assert embedder.embed("material-1") == embedder.embed("material-1")
    # A fresh component yields the identical representation (no run-to-run drift).
    assert HashedNgramEmbedder().embed("material-1") == embedder.embed("material-1")


def test_embedding_is_a_fixed_length_integer_vector() -> None:
    embedder = HashedNgramEmbedder()
    vector = embedder.embed("anything opaque")
    assert all(isinstance(count, int) for count in vector)  # integer arithmetic only
    assert len(vector) == len(embedder.embed("other"))  # fixed dimensionality


def test_similarity_is_fixed_and_deterministic() -> None:
    embedder = HashedNgramEmbedder()
    a = embedder.embed("alpha material")
    b = embedder.embed("beta material")
    assert embedder.similarity(a, b) == embedder.similarity(a, b)
    assert embedder.similarity(a, b) == embedder.similarity(b, a)  # symmetric fixed metric
    assert isinstance(embedder.similarity(a, b), int)  # integer metric, no float drift


def test_get_embedder_binds_single_component_no_routing() -> None:
    embedder: Embedder = get_embedder(EMBEDDER_NAME)
    assert isinstance(embedder, HashedNgramEmbedder)
    with pytest.raises(EmbedderError):
        get_embedder("some-other-embedder")


def test_non_software_input_is_embedded_opaquely() -> None:
    # A non-software opaque string is embedded deterministically, without interpretation.
    first = HashedNgramEmbedder().embed("melody:C-E-G;bpm=120")
    second = HashedNgramEmbedder().embed("melody:C-E-G;bpm=120")
    assert first == second
    assert all(isinstance(count, int) for count in first)
