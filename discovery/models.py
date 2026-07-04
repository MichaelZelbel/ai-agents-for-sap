"""The landscape model: a structured inventory of a system's custom objects, its
processes, its interfaces, and its module profile.

Small on purpose, but rich enough that an AI grounded on it can reason like an SAP
landscape analyst: what is custom, which custom objects break clean core and how
badly, what a standard capability could replace, and where the automation
opportunities are. A `CustomObject` is one entry (a Z-table, a bespoke function
module, a BAdI implementation, and so on). An `ObjectRegister` is the whole
landscape, with a few queries an AI (or you) can lean on, and JSON so you can save
it, share it, and reload it anywhere.

The clean-core fields mirror SAP's public extensibility classification (the four
levels A/B/C/D and the extension mechanisms), so the offline model teaches the real
vocabulary. See discovery/cleancore.py for the rules and the source.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

SCHEMA = "sap-landscape/v1"


class RegisterFormatError(ValueError):
    """Raised when a register loaded from JSON is missing required fields or is
    otherwise malformed, so a bad file fails loudly instead of silently."""


def _norm(text: str) -> str:
    """Lower-case and treat hyphens, underscores, and slashes as spaces, so
    'three-way match', 'three_way_match', and 'three way match' all match."""
    return re.sub(r"[-_/]+", " ", text.lower())


def _tuple(value: Any) -> tuple[str, ...]:
    """Read a JSON list (or None) back into a tuple of strings."""
    if not value:
        return ()
    return tuple(str(v) for v in value)


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

# SAP's clean-core extensibility levels. "" means not yet classified.
#   A = released/public APIs and released extension points (highest upgrade stability)
#   B = classic but SAP-nominated APIs, user-exits, BAdIs, classic frameworks
#   C = partially compliant, access to SAP-internal objects, higher risk
#   D = not recommended: core modifications, implicit enhancements, direct table writes
CleanCoreLevel = Literal["", "A", "B", "C", "D"]

# How the object extends SAP. Drives the clean-core level (see cleancore.py).
ExtensionMechanism = Literal[
    "",
    "released_api",
    "classic_api",
    "badi",
    "user_exit",
    "implicit_enhancement",
    "modification",
    "direct_table_write",
]

# What kind of standard capability could replace a custom object.
ReplacementType = Literal["", "config", "released_api", "fiori_app", "sap_build"]

# Coarse low/medium/high bands, kept as plain strings ("" = not assessed).
Band = Literal["", "low", "medium", "high"]


@dataclass(frozen=True)
class CustomObject:
    """One custom object in the system, with enough to ground an AI analyst.

    The first four fields identify it. `depends_on` names the objects or standard
    tables it reads or calls, so the register carries relationships, not just a flat
    list. `monthly_uses` is real usage where a system can report it (None means "not
    measured"); low usage is a signal for retirement. The clean-core fields say how
    this object extends SAP and how safe that is; `standard_alternative` names an
    SAP-standard capability that may already cover it. The signal bands
    (criticality, business_value, remediation_effort) are coarse on purpose.
    """

    name: str
    obj_type: ObjectType
    package: str
    description: str
    author: str = ""  # technical author / developer
    business_owner: str = ""  # who owns the business need
    depends_on: tuple[str, ...] = ()
    monthly_uses: int | None = None
    last_used: str = ""  # "YYYY-MM" or ""
    complexity: int | None = None  # a coarse size/complexity rating; None = unknown
    clean_core_level: CleanCoreLevel = ""
    extension_mechanism: ExtensionMechanism = ""
    non_released_touched: tuple[str, ...] = ()  # SAP-internal objects it reaches into
    successor_api: str = ""  # the released API SAP names as the successor, if any
    standard_alternative: str = ""
    replacement_type: ReplacementType = ""
    criticality: Band = ""
    business_value: Band = ""
    remediation_effort: Band = ""
    detail: str = ""  # free text, e.g. "appended to BSEG" or "fields: vendor, qty_tol"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "obj_type": self.obj_type,
            "package": self.package,
            "description": self.description,
            "author": self.author,
            "business_owner": self.business_owner,
            "depends_on": list(self.depends_on),
            "monthly_uses": self.monthly_uses,
            "last_used": self.last_used,
            "complexity": self.complexity,
            "clean_core_level": self.clean_core_level,
            "extension_mechanism": self.extension_mechanism,
            "non_released_touched": list(self.non_released_touched),
            "successor_api": self.successor_api,
            "standard_alternative": self.standard_alternative,
            "replacement_type": self.replacement_type,
            "criticality": self.criticality,
            "business_value": self.business_value,
            "remediation_effort": self.remediation_effort,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CustomObject":
        if not d.get("name") or not d.get("obj_type"):
            raise RegisterFormatError(
                f"custom object needs a name and obj_type: {d!r}"
            )
        return cls(
            name=str(d["name"]),
            obj_type=str(d["obj_type"]),  # type: ignore[arg-type]
            package=str(d.get("package", "")),
            description=str(d.get("description", "")),
            author=str(d.get("author", "")),
            business_owner=str(d.get("business_owner", "")),
            depends_on=_tuple(d.get("depends_on")),
            monthly_uses=d.get("monthly_uses"),
            last_used=str(d.get("last_used", "")),
            complexity=d.get("complexity"),
            clean_core_level=str(d.get("clean_core_level", "")),  # type: ignore[arg-type]
            extension_mechanism=str(d.get("extension_mechanism", "")),  # type: ignore[arg-type]
            non_released_touched=_tuple(d.get("non_released_touched")),
            successor_api=str(d.get("successor_api", "")),
            standard_alternative=str(d.get("standard_alternative", "")),
            replacement_type=str(d.get("replacement_type", "")),  # type: ignore[arg-type]
            criticality=str(d.get("criticality", "")),  # type: ignore[arg-type]
            business_value=str(d.get("business_value", "")),  # type: ignore[arg-type]
            remediation_effort=str(d.get("remediation_effort", "")),  # type: ignore[arg-type]
            detail=str(d.get("detail", "")),
        )


@dataclass(frozen=True)
class ProcessInfo:
    """One business process in scope, with the signals a fit-to-standard and an
    automation-opportunity analysis lean on."""

    name: str
    area: str = ""  # O2C / P2P / R2R / AP invoice-to-pay ...
    variants: int | None = None
    deviation_from_standard: str = ""  # how it differs from SAP best practice
    monthly_volume: int | None = None  # documents/cases a month
    manual_rework: Band = ""  # how manual/rework-heavy the process is
    kpis: tuple[str, ...] = ()
    objects: tuple[str, ...] = ()  # custom object names that support this process
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "area": self.area,
            "variants": self.variants,
            "deviation_from_standard": self.deviation_from_standard,
            "monthly_volume": self.monthly_volume,
            "manual_rework": self.manual_rework,
            "kpis": list(self.kpis),
            "objects": list(self.objects),
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ProcessInfo":
        if not d.get("name"):
            raise RegisterFormatError(f"process needs a name: {d!r}")
        return cls(
            name=str(d["name"]),
            area=str(d.get("area", "")),
            variants=d.get("variants"),
            deviation_from_standard=str(d.get("deviation_from_standard", "")),
            monthly_volume=d.get("monthly_volume"),
            manual_rework=str(d.get("manual_rework", "")),  # type: ignore[arg-type]
            kpis=_tuple(d.get("kpis")),
            objects=_tuple(d.get("objects")),
            detail=str(d.get("detail", "")),
        )


@dataclass(frozen=True)
class InterfaceInfo:
    """One integration/interface, with what it connects and what it leans on."""

    name: str
    itype: str = ""  # RFC / IDoc / OData / API / file
    direction: str = ""  # inbound / outbound / bidirectional
    external_system: str = ""
    criticality: Band = ""
    depends_on: tuple[str, ...] = ()  # custom objects it relies on
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "itype": self.itype,
            "direction": self.direction,
            "external_system": self.external_system,
            "criticality": self.criticality,
            "depends_on": list(self.depends_on),
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "InterfaceInfo":
        if not d.get("name"):
            raise RegisterFormatError(f"interface needs a name: {d!r}")
        return cls(
            name=str(d["name"]),
            itype=str(d.get("itype", "")),
            direction=str(d.get("direction", "")),
            external_system=str(d.get("external_system", "")),
            criticality=str(d.get("criticality", "")),  # type: ignore[arg-type]
            depends_on=_tuple(d.get("depends_on")),
            detail=str(d.get("detail", "")),
        )


@dataclass(frozen=True)
class LandscapeProfile:
    """System-level shape: which SAP product, which modules are in use, which are
    not. Tells the AI the outline of the landscape, not only the Z-objects."""

    product: str = ""  # "S/4HANA on-prem", "ECC 6.0", ...
    modules_in_use: tuple[str, ...] = ()
    modules_not_used: tuple[str, ...] = ()
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "product": self.product,
            "modules_in_use": list(self.modules_in_use),
            "modules_not_used": list(self.modules_not_used),
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LandscapeProfile":
        return cls(
            product=str(d.get("product", "")),
            modules_in_use=_tuple(d.get("modules_in_use")),
            modules_not_used=_tuple(d.get("modules_not_used")),
            detail=str(d.get("detail", "")),
        )


@dataclass(frozen=True)
class ObjectRegister:
    """The whole landscape for one system, plus a few queries."""

    system: str
    objects: tuple[CustomObject, ...]
    profile: LandscapeProfile = field(default_factory=LandscapeProfile)
    processes: tuple[ProcessInfo, ...] = ()
    interfaces: tuple[InterfaceInfo, ...] = ()

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "system": self.system,
            "profile": self.profile.to_dict(),
            "objects": [o.to_dict() for o in self.objects],
            "processes": [p.to_dict() for p in self.processes],
            "interfaces": [i.to_dict() for i in self.interfaces],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent) + "\n"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ObjectRegister":
        if "system" not in d or "objects" not in d:
            raise RegisterFormatError(
                "a register needs 'system' and 'objects' fields"
            )
        if not isinstance(d["objects"], list):
            raise RegisterFormatError("'objects' must be a list")
        return cls(
            system=str(d["system"]),
            objects=tuple(CustomObject.from_dict(o) for o in d["objects"]),
            profile=LandscapeProfile.from_dict(d.get("profile", {}) or {}),
            processes=tuple(ProcessInfo.from_dict(p) for p in d.get("processes", []) or []),
            interfaces=tuple(InterfaceInfo.from_dict(i) for i in d.get("interfaces", []) or []),
        )

    @classmethod
    def from_json(cls, text: str) -> "ObjectRegister":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RegisterFormatError(f"not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise RegisterFormatError("a register file must be a JSON object")
        return cls.from_dict(data)
