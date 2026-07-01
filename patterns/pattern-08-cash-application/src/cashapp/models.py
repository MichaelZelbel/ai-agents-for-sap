"""Data models for cash application.

Money is always a Decimal, never a float. Cash application is arithmetic on
customer money. Binary floats lose cents, and lost cents are unexplained
differences an auditor will ask about.

All models are frozen dataclasses. A payment or an invoice does not change
under you while the guard is checking it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Invoice:
    """One open item on the customer's account: an unpaid receivable."""

    invoice_id: str
    customer: str
    currency: str
    amount: Decimal  # positive for a receivable, negative for a credit note
    due_date: str  # ISO date, e.g. "2026-06-20"

    @property
    def is_credit_note(self) -> bool:
        return self.amount < 0


@dataclass(frozen=True)
class RemittanceLine:
    """One line the customer's remittance advice says the payment pays for.

    The reference is the invoice id the customer quoted. It may be wrong or
    missing. The AI reads it as a hint. The guard trusts only the amounts.
    """

    reference: str
    amount: Decimal


@dataclass(frozen=True)
class Payment:
    """An incoming payment plus the remittance advice that came with it."""

    payment_id: str
    customer: str
    currency: str
    amount: Decimal
    value_date: str  # ISO date the money arrived
    remittance: tuple[RemittanceLine, ...] = ()


@dataclass(frozen=True)
class ProposedMatch:
    """The AI's proposal: which invoices this payment clears.

    The AI proposes only. Nothing is cleared until the guard passes and a human
    approves. `invoice_ids` are the open items the AI believes the payment pays.
    """

    payment_id: str
    invoice_ids: tuple[str, ...]
    note: str = ""  # the AI's short plain-language reasoning


@dataclass(frozen=True)
class MatchResult:
    """The result of clearing a matched set against the AR ledger."""

    clearing_id: str
    payment_id: str
    invoice_ids: tuple[str, ...]
    status: str = "cleared"
