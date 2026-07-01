"""Sample incoming payments for one customer, Nordwind Retail GmbH.

The open invoices they refer to are seeded in the ledger (see ledger.py):

    INV-5001  1200.00
    INV-5002   800.00
    INV-5003  -150.00   (credit note)
    INV-5004   500.00
    INV-5005  2000.00

Three payments, one of each shape the guard must handle:

* PAY-9001  clean multi-invoice match. Pays INV-5001 + INV-5002 minus the
            INV-5003 credit note: 1200 + 800 - 150 = 1850. Reconciles exactly.
* PAY-9002  short / partial. Remittance quotes INV-5005 (2000) but only 1500
            arrived. The guard flags a partial and routes it.
* PAY-9003  overpayment. Remittance quotes INV-5004 (500) but 650 arrived.
            The guard flags an overpayment and routes it.
"""

from __future__ import annotations

from decimal import Decimal

from .models import Payment, RemittanceLine

CUSTOMER = "Nordwind Retail GmbH"


def _seed_payments() -> dict[str, Payment]:
    payments = [
        Payment(
            payment_id="PAY-9001",
            customer=CUSTOMER,
            currency="EUR",
            amount=Decimal("1850.00"),
            value_date="2026-06-25",
            remittance=(
                RemittanceLine("INV-5001", Decimal("1200.00")),
                RemittanceLine("INV-5002", Decimal("800.00")),
                RemittanceLine("INV-5003", Decimal("-150.00")),
            ),
        ),
        Payment(
            payment_id="PAY-9002",
            customer=CUSTOMER,
            currency="EUR",
            amount=Decimal("1500.00"),
            value_date="2026-06-26",
            remittance=(RemittanceLine("INV-5005", Decimal("2000.00")),),
        ),
        Payment(
            payment_id="PAY-9003",
            customer=CUSTOMER,
            currency="EUR",
            amount=Decimal("650.00"),
            value_date="2026-06-26",
            remittance=(RemittanceLine("INV-5004", Decimal("500.00")),),
        ),
    ]
    return {p.payment_id: p for p in payments}


SAMPLE_PAYMENTS = _seed_payments()


def get_payment(payment_id: str) -> Payment | None:
    """Look up a sample payment by id. None if unknown."""
    return SAMPLE_PAYMENTS.get(payment_id)
