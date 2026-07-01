"""Sample master data and customer requests.

Small, hand-seeded tables so the pattern runs end to end with no SAP account.
There is a known customer with a credit record, a new customer with none, a
handful of products (one restricted, one low on stock), and a few requests that
exercise the clean path and the out-of-policy paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import Customer, Product

# A customer request as it arrives: an id, who it is from, and free text.
@dataclass(frozen=True)
class CustomerRequest:
    request_id: str
    customer_id: str
    text: str


CustomerMaster = dict[str, Customer]
ProductCatalog = dict[str, Product]


def load_customers() -> CustomerMaster:
    """A tiny customer master.

    ACME is a known customer with credit headroom. NOVA is a brand new customer
    with no credit record yet, so any order for NOVA is out of policy until
    credit is set up.
    """
    customers = [
        Customer(
            customer_id="ACME",
            name="Acme Manufacturing",
            ship_to_country="DE",
            has_credit_record=True,
            credit_limit=Decimal("50000.00"),
            max_discount_pct=Decimal("10.00"),
        ),
        Customer(
            customer_id="NOVA",
            name="Nova Startup GmbH",
            ship_to_country="DE",
            has_credit_record=False,
            credit_limit=Decimal("0.00"),
            max_discount_pct=Decimal("0.00"),
        ),
    ]
    return {c.customer_id: c for c in customers}


def load_products() -> ProductCatalog:
    """A tiny product, stock, and price table.

    BRK-100 is the "usual brackets": plenty in stock. CLMP-50 is the "new clamps":
    low stock, so a large order runs it out. VALVE-9 is restricted, so it needs
    extra clearance no matter who orders it.
    """
    products = [
        Product(
            sku="BRK-100",
            name="Steel Bracket",
            unit_price=Decimal("12.50"),
            stock_qty=1000,
            restricted=False,
        ),
        Product(
            sku="CLMP-50",
            name="Quick Clamp",
            unit_price=Decimal("8.00"),
            stock_qty=40,
            restricted=False,
        ),
        Product(
            sku="VALVE-9",
            name="Pressure Valve",
            unit_price=Decimal("140.00"),
            stock_qty=200,
            restricted=True,
        ),
    ]
    return {p.sku: p for p in products}


def load_requests() -> dict[str, CustomerRequest]:
    """A few customer requests in free text.

    REQ-1: a known customer, clean and in stock.
    REQ-2: a new customer with no credit, and the value is over threshold.
    REQ-3: a known customer, but the clamp quantity is more than we have.
    """
    requests = [
        CustomerRequest(
            request_id="REQ-1",
            customer_id="ACME",
            text=(
                "Hi, please send me 200 of the usual brackets and 20 of the new "
                "clamps, need them by month end. Ship to our German plant as usual."
            ),
        ),
        CustomerRequest(
            request_id="REQ-2",
            customer_id="NOVA",
            text=(
                "We would like to order 300 pressure valves and 100 steel brackets "
                "for our first project. Delivery by 2026-07-15 please."
            ),
        ),
        CustomerRequest(
            request_id="REQ-3",
            customer_id="ACME",
            text=(
                "Follow-up order: 100 quick clamps and 50 steel brackets, "
                "delivery 2026-07-10."
            ),
        ),
    ]
    return {r.request_id: r for r in requests}
