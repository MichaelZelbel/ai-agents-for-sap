"""Tests for the deterministic rule-based proposer and pricing.

These run fully offline. They prove the extraction reads the sample requests and
that pricing uses Decimal money end to end.
"""

from decimal import Decimal

from salesorder import RuleBasedProposer, load_products, load_requests, price_order


def test_extracts_items_from_free_text():
    request = load_requests()["REQ-1"]
    extracted = RuleBasedProposer().extract(request, catalog=load_products())
    by_sku = {item.sku: item.quantity for item in extracted.items}
    assert by_sku == {"BRK-100": 200, "CLMP-50": 20}


def test_reads_an_explicit_delivery_date():
    request = load_requests()["REQ-3"]
    extracted = RuleBasedProposer().extract(request, catalog=load_products())
    assert extracted.requested_delivery == "2026-07-10"


def test_pricing_is_decimal_money():
    request = load_requests()["REQ-1"]
    catalog = load_products()
    extracted = RuleBasedProposer().extract(request, catalog=catalog)
    order = price_order(request, extracted, catalog=catalog)
    # 200 * 12.50 + 20 * 8.00 = 2500.00 + 160.00 = 2660.00
    assert order.order_total == Decimal("2660.00")
    for line in order.lines:
        assert isinstance(line.line_total, Decimal)
        assert isinstance(line.unit_price, Decimal)


def test_discount_is_applied_and_rounded():
    request = load_requests()["REQ-1"]
    catalog = load_products()
    extracted = RuleBasedProposer().extract(request, catalog=catalog)
    # Rebuild the extraction with a 10 percent discount.
    discounted = type(extracted)(
        items=extracted.items,
        requested_delivery=extracted.requested_delivery,
        discount_pct=Decimal("10.00"),
        ship_to_country=extracted.ship_to_country,
    )
    order = price_order(request, discounted, catalog=catalog)
    # 2660.00 less 10 percent = 2394.00
    assert order.order_total == Decimal("2394.00")


def test_unknown_sku_is_dropped_from_lines():
    catalog = load_products()
    request = load_requests()["REQ-1"]
    extracted = RuleBasedProposer().extract(request, catalog=catalog)
    ghost = type(extracted)(
        items=list(extracted.items) + [type(extracted.items[0])("GHOST-1", 5)],
        requested_delivery=extracted.requested_delivery,
        discount_pct=extracted.discount_pct,
        ship_to_country=extracted.ship_to_country,
    )
    order = price_order(request, ghost, catalog=catalog)
    assert all(line.sku != "GHOST-1" for line in order.lines)
