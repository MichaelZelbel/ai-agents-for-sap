"""Tests for the deterministic guard.

The guard is the leash. These tests prove it passes a clean order and flags each
out-of-policy case the brief calls out.
"""

from decimal import Decimal

from salesorder import (
    RuleBasedProposer,
    default_config,
    guard_order,
    load_products,
    load_requests,
    price_order,
)
from salesorder.data import load_customers


def _order_for(request_id: str):
    requests = load_requests()
    catalog = load_products()
    request = requests[request_id]
    extracted = RuleBasedProposer().extract(request, catalog=catalog)
    return price_order(request, extracted, catalog=catalog), catalog


def test_clean_order_passes():
    order, catalog = _order_for("REQ-1")
    result = guard_order(
        order,
        customers=load_customers(),
        catalog=catalog,
        config=default_config(),
    )
    assert result.status == "PASS"
    assert result.reasons == []


def test_new_customer_with_no_credit_is_flagged():
    order, catalog = _order_for("REQ-2")
    result = guard_order(
        order,
        customers=load_customers(),
        catalog=catalog,
        config=default_config(),
    )
    assert result.status == "FLAG"
    assert any("no credit record" in r for r in result.reasons)


def test_over_threshold_is_flagged():
    # REQ-2 is 300 valves + 100 brackets, well over the 25000 threshold.
    order, catalog = _order_for("REQ-2")
    result = guard_order(
        order,
        customers=load_customers(),
        catalog=catalog,
        config=default_config(),
    )
    assert any("over the threshold" in r for r in result.reasons)


def test_restricted_product_is_flagged():
    order, catalog = _order_for("REQ-2")  # REQ-2 orders the restricted valve
    result = guard_order(
        order,
        customers=load_customers(),
        catalog=catalog,
        config=default_config(),
    )
    assert any("restricted" in r for r in result.reasons)


def test_out_of_stock_is_flagged():
    # REQ-3 asks for 100 clamps; only 40 are in stock.
    order, catalog = _order_for("REQ-3")
    result = guard_order(
        order,
        customers=load_customers(),
        catalog=catalog,
        config=default_config(),
    )
    assert result.status == "FLAG"
    assert any("short" in r for r in result.reasons)


def test_oversized_discount_is_flagged():
    # Build a draft for the known customer, then push the discount past authority.
    order, catalog = _order_for("REQ-1")
    over = type(order)(
        request_id=order.request_id,
        customer_id=order.customer_id,
        currency=order.currency,
        requested_delivery=order.requested_delivery,
        discount_pct=Decimal("25.00"),  # ACME's authority is 10%
        ship_to_country=order.ship_to_country,
        lines=order.lines,
        order_total=order.order_total,
    )
    result = guard_order(
        over,
        customers=load_customers(),
        catalog=catalog,
        config=default_config(),
    )
    assert any("over this customer's authority" in r for r in result.reasons)


def test_unusual_ship_to_is_flagged():
    order, catalog = _order_for("REQ-1")
    faraway = type(order)(
        request_id=order.request_id,
        customer_id=order.customer_id,
        currency=order.currency,
        requested_delivery=order.requested_delivery,
        discount_pct=order.discount_pct,
        ship_to_country="US",  # not in the allowed set
        lines=order.lines,
        order_total=order.order_total,
    )
    result = guard_order(
        faraway,
        customers=load_customers(),
        catalog=catalog,
        config=default_config(),
    )
    assert any("unusual" in r for r in result.reasons)
