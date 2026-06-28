"""Tests for the three-way match. The matcher's model is faked here; the arithmetic
guard is exercised for real."""

from decimal import Decimal

import pytest

from threeway import Line, LlmLineMatcher, MatcherError, parse_mapping, three_way_match

# Same items, worded differently on the invoice and the purchase order.
PO = [
    Line("Ergonomic office chair", Decimal("10"), Decimal("120.00")),
    Line("Standing desk", Decimal("4"), Decimal("350.00")),
]
INVOICE = [
    Line("Office chairs, ergonomic", Decimal("10"), Decimal("120.00")),
    Line("Desk, sit-stand", Decimal("4"), Decimal("350.00")),
]
RECEIVED = [Decimal("10"), Decimal("4")]
GOOD_MAPPING = [0, 1]


def test_a_clean_match_passes():
    result = three_way_match(INVOICE, PO, RECEIVED, GOOD_MAPPING)
    assert result.status == "PASS"
    assert result.reasons == []


def test_a_price_that_does_not_match_the_order_fails():
    overpriced = [INVOICE[0], Line("Desk, sit-stand", Decimal("4"), Decimal("390.00"))]
    result = three_way_match(overpriced, PO, RECEIVED, GOOD_MAPPING)
    assert result.status == "FAIL"
    assert any("price" in r for r in result.reasons)


def test_goods_not_fully_received_fails():
    short = [Decimal("8"), Decimal("4")]  # only 8 of 10 chairs arrived
    result = three_way_match(INVOICE, PO, short, GOOD_MAPPING)
    assert result.status == "FAIL"
    assert any("received" in r for r in result.reasons)


def test_an_invoice_line_with_no_order_fails():
    result = three_way_match(INVOICE, PO, RECEIVED, [0, -1])
    assert result.status == "FAIL"
    assert any("no purchase-order line" in r for r in result.reasons)


def test_two_invoice_lines_pointing_at_one_order_line_fails():
    result = three_way_match(INVOICE, PO, RECEIVED, [0, 0])
    assert result.status == "FAIL"


def test_the_matcher_feeds_the_guard():
    matcher = LlmLineMatcher(complete=lambda prompt: '{"mapping": [0, 1]}')
    mapping = matcher.match(INVOICE, PO)
    assert mapping == GOOD_MAPPING
    assert three_way_match(INVOICE, PO, RECEIVED, mapping).status == "PASS"


def test_a_garbled_mapping_is_rejected():
    with pytest.raises(MatcherError):
        parse_mapping("the model rambled instead of returning json", invoice_len=2)
