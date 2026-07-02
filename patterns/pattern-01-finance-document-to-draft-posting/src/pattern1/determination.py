"""Tax and cost-center determination: the deterministic step between propose and
validate.

In real SAP, the tax code and the cost center are not the model's guess. They are
determined by configuration and rules. So the AI proposes the accounts and amounts,
this step fills in the tax code (from the invoice's own tax rate) and the cost
center, and then the validator checks both against master data. Deterministic in,
deterministic out.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from sap_client import Document, ProposedPosting

# The standard rate each tax code means, used to read a code off the invoice.
_STANDARD_RATES = [
    ("V0", Decimal("0.00")),
    ("V2", Decimal("0.07")),
    ("V1", Decimal("0.19")),
]
_RATE_TOLERANCE = Decimal("0.005")

DEFAULT_COST_CENTER = "CC-1000"


def determine_tax_code(document: Document) -> str:
    """Read the tax code off the invoice's own net and tax. Returns 'V?' if the
    rate is not one we recognise, so the validator can reject it."""
    if document.net_amount == 0:
        return "V0"
    rate = document.tax_amount / document.net_amount
    for code, standard in _STANDARD_RATES:
        if abs(rate - standard) <= _RATE_TOLERANCE:
            return code
    return "V?"


def apply_determination(
    document: Document,
    posting: ProposedPosting,
    *,
    cost_center: str = DEFAULT_COST_CENTER,
) -> ProposedPosting:
    """Fill in the tax code and cost center on a proposed posting."""
    return replace(
        posting,
        tax_code=determine_tax_code(document),
        cost_center=cost_center,
    )
