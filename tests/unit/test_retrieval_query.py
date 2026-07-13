"""Unit tests for retrieval query derivation (M6-C2).

Scope: derivation is deterministic; a material-only query equals the baseline path; an
optional context is admitted opaquely (carried verbatim, never parsed) and changes the
query only as opaque input (M6_SPEC §3.2).
"""

from __future__ import annotations

from velith.retrieval.query import derive_query


def test_derivation_is_deterministic() -> None:
    assert derive_query("material-1") == derive_query("material-1")
    baseline = derive_query("material-1").representation()
    assert derive_query("material-1").representation() == baseline
    with_ctx = derive_query("material-1", "ctx").representation()
    assert derive_query("material-1", "ctx").representation() == with_ctx


def test_material_only_query_equals_baseline() -> None:
    # With no context, the representation is the material alone (baseline read path).
    assert derive_query("material-1").representation() == "material-1"
    assert derive_query("material-1", None).representation() == "material-1"


def test_optional_context_is_admitted_opaquely() -> None:
    material = "shape:circle;r=5"
    context = "prior:PASSED;metric=0.9"
    representation = derive_query(material, context).representation()
    # Both material and context are carried verbatim (opaque), never parsed.
    assert material in representation
    assert context in representation
    # Supplying context changes the query only as opaque input.
    assert representation != derive_query(material).representation()


def test_different_context_yields_different_query() -> None:
    material = "m"
    rep_a = derive_query(material, "ctx-a").representation()
    rep_b = derive_query(material, "ctx-b").representation()
    assert rep_a != rep_b


def test_non_software_material_and_context_carried_verbatim() -> None:
    # A non-software material and context are carried opaquely (domain-neutral).
    representation = derive_query("melody:CEG", "recipe:soup").representation()
    assert "melody:CEG" in representation
    assert "recipe:soup" in representation
