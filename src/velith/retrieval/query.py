"""Deterministic, domain-neutral query derivation for retrieval (M6-C2).

M6_SPEC §3.2. A query is derived from a task's required opaque **material** (its
content-addressed identity content, M4) and an **optional** opaque **retrieval context**
that M6 admits but neither generates nor consumes. Material and context are opaque
bytes-as-text; the derivation parses neither as diffs, tests, or any domain content
(D9/D22). With no context, the query representation is the material alone — identical to
the baseline read path. Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass

# Fixed opaque delimiter joining material and optional context. Neither side is parsed;
# the delimiter only makes the combined representation a deterministic function of both.
_CONTEXT_SEPARATOR = "\x00"


@dataclass(frozen=True)
class Query:
    """A deterministic, domain-neutral retrieval query (M6_SPEC §3.2).

    ``material`` is the required opaque identity content of the target task; ``context``
    is an optional opaque retrieval context — admitted, but never generated or consumed
    by M6. Both are opaque; nothing here interprets either as any domain.
    """

    material: str
    context: str | None = None

    def representation(self) -> str:
        """Return the deterministic opaque representation the embedder will consume.

        A pure function of ``(material, context)``. With no context this is the material
        alone (identical to the baseline path); with context, material and context are
        joined by a fixed opaque delimiter — neither is parsed.
        """
        if self.context is None:
            return self.material
        return self.material + _CONTEXT_SEPARATOR + self.context


def derive_query(material: str, context: str | None = None) -> Query:
    """Derive a retrieval query from required opaque material and optional context.

    The single derivation entry point (M6_SPEC §3.2): ``material`` is required;
    ``context`` is optional and opaque. M6 neither generates nor consumes the context —
    it only admits it so later milestones (M7–M10) are not artificially constrained.
    """
    return Query(material=material, context=context)
