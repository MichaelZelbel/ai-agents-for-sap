"""Tests for the model-backed proposer.

These never call a real model: we inject a `complete` callable, so the suite
runs offline with no API key. The one real call would live in a separate,
opt-in script, not in the test suite.
"""

from decimal import Decimal

import pytest

from salesorder import (
    LlmBackedProposer,
    ProposerError,
    default_config,
    guard_order,
    load_products,
    load_requests,
    parse_extraction,
    price_order,
)
from salesorder.data import load_customers

GOOD_JSON = (
    '{"items": ['
    '{"sku": "BRK-100", "quantity": 200},'
    '{"sku": "CLMP-50", "quantity": 20}],'
    '"requested_delivery": "2026-06-30", "discount_pct": "0", '
    '"ship_to_country": "DE"}'
)


def test_llm_extraction_prices_and_passes_the_guard():
    catalog = load_products()
    request = load_requests()["REQ-1"]
    proposer = LlmBackedProposer(complete=lambda prompt: GOOD_JSON)
    extracted = proposer.extract(request, catalog=catalog)
    order = price_order(request, extracted, catalog=catalog)
    result = guard_order(
        order, customers=load_customers(), catalog=catalog, config=default_config()
    )
    assert result.status == "PASS"
    assert len(order.lines) == 2


def test_parses_json_inside_a_code_fence():
    fenced = "Sure:\n```json\n" + GOOD_JSON + "\n```"
    extracted = parse_extraction(fenced)
    assert extracted.items[0].sku == "BRK-100"
    assert extracted.items[0].quantity == 200
    assert extracted.discount_pct == Decimal("0")


def test_a_wrong_extraction_is_caught_by_the_guard():
    # The model "hallucinates" a huge quantity of a restricted, short product.
    # The proposer accepts it structurally, but the deterministic guard flags it.
    catalog = load_products()
    request = load_requests()["REQ-1"]
    wrong = (
        '{"items": [{"sku": "VALVE-9", "quantity": 99999}], '
        '"requested_delivery": "2026-06-30", "discount_pct": "0", '
        '"ship_to_country": "DE"}'
    )
    extracted = LlmBackedProposer(complete=lambda p: wrong).extract(
        request, catalog=catalog
    )
    order = price_order(request, extracted, catalog=catalog)
    result = guard_order(
        order, customers=load_customers(), catalog=catalog, config=default_config()
    )
    assert result.status == "FLAG"


def test_bad_model_output_raises():
    request = load_requests()["REQ-1"]
    proposer = LlmBackedProposer(complete=lambda prompt: "sorry, no idea")
    with pytest.raises(ProposerError):
        proposer.extract(request, catalog=load_products())


def test_empty_items_raises():
    request = load_requests()["REQ-1"]
    empty = '{"items": [], "requested_delivery": "", "discount_pct": "0"}'
    proposer = LlmBackedProposer(complete=lambda prompt: empty)
    with pytest.raises(ProposerError):
        proposer.extract(request, catalog=load_products())


def test_missing_api_key_raises_when_called(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    request = load_requests()["REQ-1"]
    proposer = LlmBackedProposer()
    with pytest.raises(ProposerError):
        proposer.extract(request, catalog=load_products())
