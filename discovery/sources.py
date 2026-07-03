"""Where the register comes from.

`RepositorySource` is the one contract: return the custom objects of a system.
`MockRepositorySource` seeds a realistic fake system so everything runs offline.
`AbapRepositorySource` is the shape of a real reader: it maps an ABAP repository
into the same `CustomObject` list, through an injectable `transport` so you can
point it at your tenant (or a fake one in a test). The README explains which
repository tables and services a real transport reads. Treat it as a recipe to
verify against your own system, not a guaranteed connector.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .models import CustomObject


class RepositorySource(Protocol):
    def system_name(self) -> str: ...
    def objects(self) -> list[CustomObject]: ...


class MockRepositorySource:
    """A fictional but realistic mid-sized manufacturer, 'Nordwind'. Its custom
    objects cluster around the finance jobs this book already builds agents for:
    a bespoke three-way-match tolerance table, a custom approval-lane field, a
    hand-rolled tax rule, a triage cockpit, and a barely-used dispute router."""

    def system_name(self) -> str:
        return "Nordwind Production (S/4HANA, on-prem)"

    def objects(self) -> list[CustomObject]:
        return [
            CustomObject(
                name="ZTHREEWAY_TOL",
                obj_type="table",
                package="ZFI_AP",
                description="Per-vendor three-way-match tolerances (quantity and price).",
                author="M.WEBER",
                depends_on=("LFA1",),
                monthly_uses=4100,
                standard_alternative="MM tolerance keys (transaction OMR6) may already cover this.",
                detail="fields: vendor, qty_tolerance, price_tolerance, valid_from",
            ),
            CustomObject(
                name="ZZ_APPROVAL_LANE",
                obj_type="custom_field",
                package="ZFI_AP",
                description="Approval-lane classification stamped on the invoice header.",
                author="M.WEBER",
                depends_on=("BKPF",),
                monthly_uses=None,
                detail="append field on standard table BKPF; values: STANDARD, HIGH_VALUE, EXCEPTION",
            ),
            CustomObject(
                name="Z_TAX_DETERMINE_NW",
                obj_type="function_module",
                package="ZFI_TAX",
                description="Bespoke tax code determination for a legacy vendor group.",
                author="A.SCHMIDT",
                depends_on=("ZTAX_RULES", "T007A"),
                monthly_uses=900,
                standard_alternative="Standard tax determination via the condition technique / tax codes.",
                detail="called from the invoice-posting enhancement ZEI_INVOICE_POST",
            ),
            CustomObject(
                name="ZTAX_RULES",
                obj_type="table",
                package="ZFI_TAX",
                description="Custom tax-rule lookup for the legacy vendor group.",
                author="A.SCHMIDT",
                depends_on=(),
                monthly_uses=900,
                detail="fields: vendor_group, country, tax_code, rate",
            ),
            CustomObject(
                name="ZFI_TRIAGE",
                obj_type="transaction",
                package="ZFI_AP",
                description="AP triage cockpit: route an incoming document to the right desk.",
                author="M.WEBER",
                depends_on=("ZFI_TRIAGE_PROG",),
                monthly_uses=3200,
                standard_alternative="Consider standard workflow inbox or Joule triage before extending this.",
                detail="dialog transaction over program ZFI_TRIAGE_PROG",
            ),
            CustomObject(
                name="ZFI_TRIAGE_PROG",
                obj_type="program",
                package="ZFI_AP",
                description="The program behind the triage cockpit; classifies and routes documents.",
                author="M.WEBER",
                depends_on=("ZTHREEWAY_TOL", "BKPF"),
                monthly_uses=3200,
                detail="ABAP report; classifies po_invoice / direct_expense / not_an_invoice",
            ),
            CustomObject(
                name="Z_I_OPEN_AP_ITEMS",
                obj_type="cds_view",
                package="ZFI_AP",
                description="Analytical view of open accounts-payable items with aging buckets.",
                author="R.KHAN",
                depends_on=("BSIK", "LFA1"),
                monthly_uses=15000,
                detail="CDS view consumed by a Fiori list and several reports",
            ),
            CustomObject(
                name="ZCL_DISPUTE_ROUTER",
                obj_type="class",
                package="ZFI_AP",
                description="Bespoke routing logic for vendor disputes.",
                author="(left the company)",
                depends_on=("ZTHREEWAY_TOL",),
                monthly_uses=3,
                standard_alternative="SAP Dispute Management (FSCM) covers most of this.",
                detail="barely used; owner gone; a retirement candidate",
            ),
            CustomObject(
                name="ZEI_INVOICE_POST",
                obj_type="enhancement",
                package="ZFI_TAX",
                description="BAdI implementation on invoice posting; injects the bespoke tax rule.",
                author="A.SCHMIDT",
                depends_on=("Z_TAX_DETERMINE_NW",),
                monthly_uses=900,
                detail="implements a standard posting BAdI; the clean-core risk to watch",
            ),
        ]


class AbapRepositorySource:
    """A real reader, by shape. Give it a `transport` that runs a read against your
    system and returns rows, and it maps them into the same `CustomObject` list.

    A `transport` is any callable `(query_name, params) -> list[dict]`. In a real
    deployment it wraps one of: an RFC call (for example a whitelisted read of the
    repository tables), a released OData/CDS service that exposes repository
    metadata, or an export from the ABAP Development Tools. Which one, and which
    exact objects you are allowed to read, is tenant-specific: verify it against
    your own system and authorizations before trusting it.

    This maps the core object directory (TADIR). Descriptions, table fields, real
    usage, and custom fields on standard tables each need an extra read (see the
    README); this reference brings back the objects and their packages so you have
    a spine to hang the rest on.
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
