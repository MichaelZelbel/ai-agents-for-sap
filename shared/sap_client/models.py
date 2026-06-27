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
class Document:
    """A source finance document, e.g. a vendor invoice."""

    doc_id: str
    vendor: str
    currency: str
    net_amount: Decimal
    tax_amount: Decimal
    gross_amount: Decimal
    document_date: str  # ISO date, e.g. "2026-06-20"


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
