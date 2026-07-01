"""A fake accounts-receivable ledger that runs in memory.

It seeds one customer's open invoices, lets you read the open items, and lets
you clear a matched set against an incoming payment. It refuses to clear an
invoice twice. That last part is the idempotency guarantee cash application
needs: a replayed payment file must not clear the same receivable again.

This is deliberately small. Just enough to run the pattern end to end with no
SAP account.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import count

from .models import Invoice


class ClearingError(Exception):
    """The AR ledger refused to clear the matched set."""


@dataclass(frozen=True)
class ClearingResult:
    """The result of clearing a matched set of invoices with a payment."""

    clearing_id: str
    payment_id: str
    invoice_ids: tuple[str, ...]
    status: str = "cleared"


def _seed_invoices() -> dict[str, Invoice]:
    """One customer, Nordwind Retail GmbH, with a handful of open items.

    INV-5003 is a credit note (a negative open item). A clean payment nets it
    against the invoices it accompanies.
    """
    invoices = [
        Invoice(
            invoice_id="INV-5001",
            customer="Nordwind Retail GmbH",
            currency="EUR",
            amount=Decimal("1200.00"),
            due_date="2026-06-15",
        ),
        Invoice(
            invoice_id="INV-5002",
            customer="Nordwind Retail GmbH",
            currency="EUR",
            amount=Decimal("800.00"),
            due_date="2026-06-18",
        ),
        Invoice(
            invoice_id="INV-5003",
            customer="Nordwind Retail GmbH",
            currency="EUR",
            amount=Decimal("-150.00"),  # credit note
            due_date="2026-06-18",
        ),
        Invoice(
            invoice_id="INV-5004",
            customer="Nordwind Retail GmbH",
            currency="EUR",
            amount=Decimal("500.00"),
            due_date="2026-06-20",
        ),
        Invoice(
            invoice_id="INV-5005",
            customer="Nordwind Retail GmbH",
            currency="EUR",
            amount=Decimal("2000.00"),
            due_date="2026-06-22",
        ),
    ]
    return {inv.invoice_id: inv for inv in invoices}


class MockArLedger:
    """In-memory stand-in for the AR side of SAP.

    Read open items, look one up, and clear a matched set. Cleared items leave
    the open pool, so a second attempt on the same invoice fails.
    """

    def __init__(self) -> None:
        self._invoices = _seed_invoices()
        self._cleared_invoices: set[str] = set()
        self._cleared_payments: set[str] = set()
        self._clearings: dict[str, ClearingResult] = {}
        self._clearing_seq = count(1)

    def open_invoices(self) -> list[Invoice]:
        """The invoices still open (not yet cleared)."""
        return [
            inv
            for inv in self._invoices.values()
            if inv.invoice_id not in self._cleared_invoices
        ]

    def get_invoice(self, invoice_id: str) -> Invoice | None:
        """Look up one invoice by id, cleared or not. None if unknown."""
        return self._invoices.get(invoice_id)

    def is_payment_cleared(self, payment_id: str) -> bool:
        """True if this payment already posted a clearing."""
        return payment_id in self._cleared_payments

    def clear(
        self, payment_id: str, invoice_ids: tuple[str, ...]
    ) -> ClearingResult:
        """Clear the matched set. Refuse if the payment already cleared or any
        invoice is already cleared. This is the ledger's own last line of
        defence. The guard checks first, but the ledger never trusts that.
        """
        if payment_id in self._cleared_payments:
            raise ClearingError(f"payment {payment_id} was already cleared")
        already = sorted(i for i in invoice_ids if i in self._cleared_invoices)
        if already:
            raise ClearingError(
                f"invoice(s) already cleared: {', '.join(already)}"
            )
        unknown = sorted(i for i in invoice_ids if i not in self._invoices)
        if unknown:
            raise ClearingError(f"unknown invoice(s): {', '.join(unknown)}")

        clearing_id = f"CLR-{next(self._clearing_seq):04d}"
        result = ClearingResult(
            clearing_id=clearing_id,
            payment_id=payment_id,
            invoice_ids=tuple(invoice_ids),
        )
        self._cleared_invoices.update(invoice_ids)
        self._cleared_payments.add(payment_id)
        self._clearings[clearing_id] = result
        return result
