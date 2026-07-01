"""The deterministic guard: fixed rules, no AI.

This is the leash. The agent may *extract* and *propose* anything, but a draft
order only passes if it obeys every rule here. The rules are plain code you can
read, test, and trust. The model never gets a vote.

The guard checks that the customer exists and is within credit, that every
product is valid and in stock, that the pricing and any discount are within
authority, and that the order value is within threshold. It flags the
out-of-policy cases the brief calls out: a new customer with no credit record,
an oversized discount, a restricted product, and an unusual ship-to.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .data import CustomerMaster, ProductCatalog
from .models import Customer, DraftOrder


@dataclass(frozen=True)
class GuardConfig:
    value_threshold: Decimal  # orders above this need extra sign-off
    allowed_ship_to: frozenset[str]  # countries we ship to without a flag


def default_config() -> GuardConfig:
    """Sensible defaults for the book's example orders."""
    return GuardConfig(
        value_threshold=Decimal("25000.00"),
        allowed_ship_to=frozenset({"DE", "AT", "CH"}),
    )


@dataclass(frozen=True)
class GuardResult:
    status: str  # "PASS" or "FLAG"
    reasons: list[str]  # empty on PASS; one line per issue on FLAG


def guard_order(
    order: DraftOrder,
    *,
    customers: CustomerMaster,
    catalog: ProductCatalog,
    config: GuardConfig,
) -> GuardResult:
    """Check a draft order against the master data and the rules."""
    reasons: list[str] = []

    customer = customers.get(order.customer_id)
    if customer is None:
        reasons.append(f"Customer {order.customer_id} is not in the master.")
    else:
        _check_customer(order, customer, reasons)

    if not order.lines:
        reasons.append("Order has no valid lines.")

    _check_products(order, catalog, reasons)

    if order.discount_pct < 0:
        reasons.append("Discount percent cannot be negative.")

    if order.order_total > config.value_threshold:
        reasons.append(
            f"Order value {order.order_total} {order.currency} is over the "
            f"threshold of {config.value_threshold} {order.currency}."
        )

    if order.ship_to_country not in config.allowed_ship_to:
        reasons.append(
            f"Ship-to country {order.ship_to_country} is unusual and needs review."
        )

    if any(line.quantity <= 0 for line in order.lines):
        reasons.append("Every line quantity must be positive.")

    if not order.requested_delivery.strip():
        reasons.append("Requested delivery date is missing.")

    status = "PASS" if not reasons else "FLAG"
    return GuardResult(status=status, reasons=reasons)


def _check_customer(
    order: DraftOrder, customer: Customer, reasons: list[str]
) -> None:
    if not customer.has_credit_record:
        reasons.append(
            f"Customer {customer.customer_id} has no credit record "
            "(new customer)."
        )
    elif order.order_total > customer.credit_limit:
        reasons.append(
            f"Order value {order.order_total} {order.currency} exceeds the "
            f"credit limit {customer.credit_limit} {order.currency}."
        )
    if order.discount_pct > customer.max_discount_pct:
        reasons.append(
            f"Discount {order.discount_pct}% is over this customer's authority "
            f"of {customer.max_discount_pct}%."
        )


def _check_products(
    order: DraftOrder, catalog: ProductCatalog, reasons: list[str]
) -> None:
    for line in order.lines:
        product = catalog.get(line.sku)
        if product is None:
            reasons.append(f"Product {line.sku} is not in the catalog.")
            continue
        if product.restricted:
            reasons.append(
                f"Product {line.sku} ({product.name}) is restricted and needs "
                "clearance."
            )
        if line.quantity > product.stock_qty:
            reasons.append(
                f"Product {line.sku} is short: {line.quantity} requested, "
                f"{product.stock_qty} in stock."
            )
