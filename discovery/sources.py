"""Where the landscape model comes from.

`RepositorySource` is the core contract: return the custom objects of a system. A
source may also offer a `profile()` (modules), `processes()`, and `interfaces()` to
fill out the landscape; `build_register` picks those up when present.

`MockRepositorySource` seeds a realistic fake system so everything runs offline.
`JsonRepositorySource` loads a register you saved or hand-authored, so anyone who
cannot run an ABAP connector can still use every feature. `AbapRepositorySource` is
the shape of a real reader: it maps an ABAP repository into the same objects through
an injectable `transport`, so you can point it at your tenant (or a fake one in a
test). The README explains which repository tables and services a real transport
reads, and where each enriched field (usage, clean-core level) comes from. Treat it
as a recipe to verify against your own system, not a guaranteed connector.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from .models import (
    CustomObject,
    InterfaceInfo,
    LandscapeProfile,
    ObjectRegister,
    ProcessInfo,
)


class RepositorySource(Protocol):
    def system_name(self) -> str: ...
    def objects(self) -> list[CustomObject]: ...


class MockRepositorySource:
    """A fictional but realistic mid-sized manufacturer, 'Nordwind'. Its custom
    objects, processes, and interfaces cluster around the finance jobs this book
    already builds agents for, with a spread of clean-core levels so the analyses
    have something honest to say: one Level-D risk, one differentiating keeper, one
    dead-wood retirement candidate, and several standard-replaceable customizations."""

    def system_name(self) -> str:
        return "Nordwind Production (S/4HANA, on-prem)"

    def profile(self) -> LandscapeProfile:
        return LandscapeProfile(
            product="SAP S/4HANA 2023, on-prem",
            modules_in_use=("FI", "CO", "MM"),
            modules_not_used=("EWM", "TM", "PP"),
            detail="Finance-heavy landscape; accounts payable is the custom hot spot.",
        )

    def processes(self) -> list[ProcessInfo]:
        return [
            ProcessInfo(
                name="Accounts payable invoice-to-pay",
                area="P2P",
                variants=4,
                deviation_from_standard="custom triage cockpit and per-vendor tolerance table",
                monthly_volume=3200,
                manual_rework="high",
                kpis=("throughput", "exceptions", "days-to-post"),
                objects=("ZFI_TRIAGE", "ZFI_TRIAGE_PROG", "ZTHREEWAY_TOL", "Z_TAX_DETERMINE_NW"),
                detail="Highest-volume, most manual process; the prime automation target.",
            ),
            ProcessInfo(
                name="Three-way match",
                area="P2P",
                variants=2,
                deviation_from_standard="custom tolerance keys instead of standard OMR6",
                monthly_volume=2100,
                manual_rework="medium",
                kpis=("first-time-match rate",),
                objects=("ZTHREEWAY_TOL",),
            ),
            ProcessInfo(
                name="Vendor dispute handling",
                area="P2P",
                variants=1,
                deviation_from_standard="bespoke routing class instead of SAP Dispute Management",
                monthly_volume=40,
                manual_rework="high",
                kpis=("resolution time",),
                objects=("ZCL_DISPUTE_ROUTER",),
                detail="Low volume; a poor automation candidate despite the manual effort.",
            ),
        ]

    def interfaces(self) -> list[InterfaceInfo]:
        return [
            InterfaceInfo(
                name="Bank statement import",
                itype="IDoc",
                direction="inbound",
                external_system="Hausbank",
                criticality="high",
                detail="Daily electronic bank statement into cash application.",
            ),
            InterfaceInfo(
                name="Supplier portal invoices",
                itype="OData",
                direction="inbound",
                external_system="Supplier portal",
                criticality="medium",
                depends_on=("ZFI_TRIAGE_PROG",),
            ),
        ]

    def objects(self) -> list[CustomObject]:
        return [
            CustomObject(
                name="ZTHREEWAY_TOL",
                obj_type="table",
                package="ZFI_AP",
                description="Per-vendor three-way-match tolerances (quantity and price).",
                author="M.WEBER",
                business_owner="AP lead",
                depends_on=("LFA1",),
                monthly_uses=4100,
                last_used="2026-06",
                complexity=2,
                standard_alternative="MM tolerance keys (transaction OMR6) may already cover this.",
                replacement_type="config",
                criticality="high",
                business_value="medium",
                remediation_effort="medium",
                detail="fields: vendor, qty_tolerance, price_tolerance, valid_from",
            ),
            CustomObject(
                name="ZZ_APPROVAL_LANE",
                obj_type="custom_field",
                package="ZFI_AP",
                description="Approval-lane classification stamped on the invoice header.",
                author="M.WEBER",
                business_owner="AP lead",
                depends_on=("BKPF",),
                monthly_uses=None,
                clean_core_level="B",
                extension_mechanism="classic_api",
                business_value="medium",
                detail="append field on standard table BKPF; values: STANDARD, HIGH_VALUE, EXCEPTION",
            ),
            CustomObject(
                name="Z_TAX_DETERMINE_NW",
                obj_type="function_module",
                package="ZFI_TAX",
                description="Bespoke tax code determination for a legacy vendor group.",
                author="A.SCHMIDT",
                business_owner="Tax team",
                depends_on=("ZTAX_RULES", "T007A"),
                monthly_uses=900,
                last_used="2026-06",
                complexity=3,
                clean_core_level="B",
                extension_mechanism="classic_api",
                standard_alternative="Standard tax determination via the condition technique / tax codes.",
                replacement_type="config",
                criticality="high",
                business_value="medium",
                remediation_effort="high",
                detail="called from the invoice-posting enhancement ZEI_INVOICE_POST",
            ),
            CustomObject(
                name="ZTAX_RULES",
                obj_type="table",
                package="ZFI_TAX",
                description="Custom tax-rule lookup for the legacy vendor group.",
                author="A.SCHMIDT",
                business_owner="Tax team",
                depends_on=(),
                monthly_uses=900,
                business_value="medium",
                detail="fields: vendor_group, country, tax_code, rate",
            ),
            CustomObject(
                name="ZFI_TRIAGE",
                obj_type="transaction",
                package="ZFI_AP",
                description="AP triage cockpit: route an incoming document to the right desk.",
                author="M.WEBER",
                business_owner="AP lead",
                depends_on=("ZFI_TRIAGE_PROG",),
                monthly_uses=3200,
                last_used="2026-06",
                complexity=4,
                standard_alternative="Standard workflow inbox or a Joule triage agent before extending this.",
                replacement_type="sap_build",
                criticality="high",
                business_value="medium",
                remediation_effort="high",
                detail="dialog transaction over program ZFI_TRIAGE_PROG",
            ),
            CustomObject(
                name="ZFI_TRIAGE_PROG",
                obj_type="program",
                package="ZFI_AP",
                description="The program behind the triage cockpit; classifies and routes documents.",
                author="M.WEBER",
                business_owner="AP lead",
                depends_on=("ZTHREEWAY_TOL", "BKPF"),
                monthly_uses=3200,
                last_used="2026-06",
                complexity=5,
                clean_core_level="B",
                extension_mechanism="classic_api",
                business_value="medium",
                detail="ABAP report; classifies po_invoice / direct_expense / not_an_invoice",
            ),
            CustomObject(
                name="Z_I_OPEN_AP_ITEMS",
                obj_type="cds_view",
                package="ZFI_AP",
                description="Analytical view of open accounts-payable items with aging buckets.",
                author="R.KHAN",
                business_owner="Controlling",
                depends_on=("BSIK", "LFA1"),
                monthly_uses=15000,
                last_used="2026-06",
                complexity=2,
                clean_core_level="A",
                extension_mechanism="released_api",
                business_value="high",
                detail="CDS view on released interfaces; consumed by a Fiori list and several reports",
            ),
            CustomObject(
                name="ZCL_DISPUTE_ROUTER",
                obj_type="class",
                package="ZFI_AP",
                description="Bespoke routing logic for vendor disputes.",
                author="(left the company)",
                business_owner="(unowned)",
                depends_on=("ZTHREEWAY_TOL",),
                monthly_uses=3,
                last_used="2025-11",
                complexity=3,
                standard_alternative="SAP Dispute Management (FSCM) covers most of this.",
                replacement_type="config",
                criticality="low",
                business_value="low",
                remediation_effort="low",
                detail="barely used; owner gone; a retirement candidate",
            ),
            CustomObject(
                name="ZEI_INVOICE_POST",
                obj_type="enhancement",
                package="ZFI_TAX",
                description="Implicit enhancement on invoice posting; injects the bespoke tax rule.",
                author="A.SCHMIDT",
                business_owner="Tax team",
                depends_on=("Z_TAX_DETERMINE_NW",),
                monthly_uses=900,
                last_used="2026-06",
                complexity=3,
                clean_core_level="D",
                extension_mechanism="implicit_enhancement",
                non_released_touched=("standard invoice-posting flow",),
                criticality="high",
                business_value="medium",
                remediation_effort="high",
                detail="implicit enhancement point in the posting logic; the clean-core risk to watch",
            ),
        ]


class JsonRepositorySource:
    """Load a register a reader exported (`--save`) or hand-authored as JSON. This is
    the bridge to real systems for anyone who cannot run an ABAP connector: dump your
    landscape into the schema and every analysis, diagram, and the skill work on it."""

    def __init__(self, path: str | Path) -> None:
        self._register = ObjectRegister.from_json(Path(path).read_text(encoding="utf-8"))

    def system_name(self) -> str:
        return self._register.system

    def objects(self) -> list[CustomObject]:
        return list(self._register.objects)

    def profile(self) -> LandscapeProfile:
        return self._register.profile

    def processes(self) -> list[ProcessInfo]:
        return list(self._register.processes)

    def interfaces(self) -> list[InterfaceInfo]:
        return list(self._register.interfaces)


class AbapRepositorySource:
    """A real reader, by shape. Give it a `transport` that runs a read against your
    system and returns rows, and it maps them into the same `CustomObject` list.

    A `transport` is any callable `(query_name, params) -> list[dict]`. In a real
    deployment it wraps one of: an RFC call (a whitelisted read of the repository
    tables), a released OData/CDS service that exposes repository metadata, or an
    export from the ABAP Development Tools. Which one, and which exact objects you are
    allowed to read, is tenant-specific: verify it against your own system and
    authorizations before trusting it.

    This maps the core object directory (TADIR). The enriched fields each need an
    extra read, and this is where the real SAP tools earn their keep (see the README):
      - usage (monthly_uses/last_used): ST03N / UPL / SCMON usage statistics.
      - clean_core_level / extension_mechanism / successor_api: the ATC clean-core
        check and SAP's released-API classification (github.com/SAP/abap-atc-cr-cv-s4hc).
      - dependencies / blast radius: a repository dependency crawl (the territory of
        the Custom Code Migration app, smartShift, Panaya, LiveCompare).
      - standard_alternative / simplification impact: SAP Readiness Check.
    This reference brings back the objects and their packages so you have a spine to
    hang the rest on.
    """

    # TADIR object codes -> our register types. Not exhaustive; extend per tenant.
    _TYPE_MAP = {
        "TABL": "table",
        "PROG": "program",
        "FUGR": "function_module",
        "TRAN": "transaction",
        "CLAS": "class",
        "DDLS": "cds_view",
        "ENHO": "enhancement",
        "ENHS": "enhancement",
    }

    def __init__(self, transport: Callable[[str, dict], list[dict]], *, system: str) -> None:
        self._transport = transport
        self._system = system

    def system_name(self) -> str:
        return self._system

    def objects(self) -> list[CustomObject]:
        # Customer-namespace objects from the repository object directory. A real
        # transport turns this into the right RFC/OData/CDS read for your system.
        rows = self._transport(
            "repository_objects",
            {"namespace": ("Z*", "Y*"), "source": "TADIR"},
        )
        out: list[CustomObject] = []
        for row in rows:
            obj_type = self._TYPE_MAP.get(str(row.get("object", "")).upper())
            if obj_type is None:
                continue  # a type this reference does not map yet
            out.append(
                CustomObject(
                    name=str(row.get("obj_name", "")),
                    obj_type=obj_type,  # type: ignore[arg-type]
                    package=str(row.get("devclass", "")),
                    description=str(row.get("description", "")),
                    author=str(row.get("author", "")),
                )
            )
        return out
