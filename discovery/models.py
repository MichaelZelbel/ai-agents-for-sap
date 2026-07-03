"""The object register model: a structured inventory of a system's custom objects.

Deliberately small. A `CustomObject` is one entry (a Z-table, a custom field on a
standard table, a bespoke function module, a custom transaction, and so on). An
`ObjectRegister` is the whole set, with a few queries an AI (or you) can lean on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


def _norm(text: str) -> str:
    """Lower-case and treat hyphens, underscores, and slashes as spaces, so
    'three-way match', 'three_way_match', and 'three way match' all match."""
    return re.sub(r"[-_/]+", " ", text.lower())

ObjectType = Literal[
    "table",
    "custom_field",
    "program",
    "function_module",
    "transaction",
    "cds_view",
    "class",
    "enhancement",
]


@dataclass(frozen=True)
class CustomObject:
    """One custom object in the system, with just enough to ground an AI.

    `depends_on` names the objects or standard tables it reads or calls, so the
    register carries relationships, not just a flat list. `monthly_uses` is real
    usage where a system can report it (None means "not measured"); low usage is a
    signal for fit-to-standard. `standard_alternative` names an SAP-standard
    capability that may already cover this, if one is known.
    """

    name: str
    obj_type: ObjectType
    package: str
    description: str
    author: str = ""
    depends_on: tuple[str, ...] = ()
    monthly_uses: int | None = None
    standard_alternative: str = ""
    detail: str = ""  # free text, e.g. "appended to BSEG" or "fields: vendor, qty_tol"


@dataclass(frozen=True)
class ObjectRegister:
    """The whole inventory for one system, plus a few queries."""

    system: str
    objects: tuple[CustomObject, ...]

    def of_type(self, obj_type: ObjectType) -> tuple[CustomObject, ...]:
        return tuple(o for o in self.objects if o.obj_type == obj_type)

    def by_name(self, name: str) -> CustomObject | None:
        for o in self.objects:
            if o.name.upper() == name.upper():
                return o
        return None

    def search(self, term: str) -> tuple[CustomObject, ...]:
        """Every object whose name, description, or detail carries all the words in
        the term. Forgiving about hyphens and spacing, so a plain-English question
        finds objects whose names run the words together (ZTHREEWAY_TOL)."""
        words = [w for w in _norm(term).split() if w]
        if not words:
            return ()
        out = []
        for o in self.objects:
            hay = _norm(f"{o.name} {o.description} {o.detail}")
            if all(w in hay for w in words):
                out.append(o)
        return tuple(out)

    def dependents_of(self, name: str) -> tuple[CustomObject, ...]:
        """Custom objects that depend on the given object (reverse dependencies)."""
        return tuple(
            o for o in self.objects if any(d.upper() == name.upper() for d in o.depends_on)
        )

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for o in self.objects:
            out[o.obj_type] = out.get(o.obj_type, 0) + 1
        return out
