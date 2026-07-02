"""Data models for the (fake or real) SAP boundary.

Money is always a Decimal, never a float. Finance code that rounds with
binary floats is how cents go missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

Side = Literal["debit", "credit"]


@dataclass(frozen=True)
class TaxLine:
    """One tax bucket of an invoice: a rate and the net and tax booked at it.

    A plain invoice has one rate. A hotel or catering bill mixes several (a room
    at 7%, breakfast at 19%, a tourism levy at 0%), and a single net/tax/gross can
    never foot such a document. When the reader finds a printed VAT breakdown it
    reports one TaxLine per rate, and the parts sum to the gross.
    """

    rate: Decimal  # a fraction, e.g. Decimal("0.07") for 7%
    net: Decimal
    tax: Decimal


@dataclass(frozen=True)
class Document:
    """A source finance document, e.g. a vendor invoice."""

    doc_id: str
    vendor: str
    currency: str
    net_amount: Decimal
    tax_amount: Decimal
    gross_amount: Decimal
    document_date: str  # ISO date, e.g. "2026-06-20"
    # How sure the reader is it read the document right (0..1). None means "read
    # from clean fields, not from a scan", so confidence does not apply.
    confidence: float | None = None
    # The per-rate VAT breakdown, when the invoice mixes tax rates. Empty means
    # single-rate: use net_amount / tax_amount / gross_amount as before.
    tax_lines: tuple[TaxLine, ...] = ()


@dataclass(frozen=True)
class PostingLine:
    """One debit or credit line of a posting."""

    account: str
    side: Side
    amount: Decimal


@dataclass(frozen=True)
class ProposedPosting:
    """A posting the agent proposes. Nothing is booked until it is confirmed."""

    doc_id: str
    posting_date: str
    currency: str
    lines: list[PostingLine]
    # Filled in by tax and cost-center determination (see determination.py), then
    # checked by the validator against master data.
    tax_code: str = ""
    cost_center: str = ""


@dataclass(frozen=True)
class StagedPosting:
    """A posting held at the SAP boundary, waiting to be confirmed."""

    staged_id: str
    posting: ProposedPosting
    status: str = "staged"


@dataclass(frozen=True)
class PostingResult:
    """The result of a confirmed (booked) posting."""

    posting_id: str
    doc_id: str
    status: str = "posted"
