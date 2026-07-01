"""Data models for the sales order boundary.

Money is always a Decimal, never a float. Order values that round with binary
floats are how money and trust go missing. Every model here is a frozen
dataclass, so a proposed order cannot be mutated after it is proposed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Customer:
    """A customer master record."""

    customer_id: str
    name: str
    ship_to_country: str  # the country we expect this customer to ship to
    has_credit_record: bool  # a new customer has none
    credit_limit: Decimal  # remaining credit headroom; zero if no record
    max_discount_pct: Decimal  # the highest discount this customer may get


@dataclass(frozen=True)
class Product:
    """A product master record with stock and price."""

    sku: str
    name: str
    unit_price: Decimal
    stock_qty: int
    restricted: bool  # a restricted product needs extra clearance


@dataclass(frozen=True)
class RequestedItem:
    """One product and quantity the AI extracted from the request text."""

    sku: str
    quantity: int


@dataclass(frozen=True)
class OrderLine:
    """One priced line of a draft order."""

    sku: str
    name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal  # quantity * unit_price, after any discount


@dataclass(frozen=True)
class DraftOrder:
    """An order the agent proposes. Nothing is released until it is confirmed."""

    request_id: str
    customer_id: str
    currency: str
    requested_delivery: str  # ISO date, e.g. "2026-06-30"
    discount_pct: Decimal
    ship_to_country: str
    lines: list[OrderLine]
    order_total: Decimal


@dataclass(frozen=True)
class StagedOrder:
    """A draft order held at the boundary, waiting to be released."""

    staged_id: str
    order: DraftOrder
    status: str = "staged"


@dataclass(frozen=True)
class ReleaseResult:
    """The result of a released (confirmed) order handed to fulfillment."""

    order_id: str
    request_id: str
    status: str = "released"
