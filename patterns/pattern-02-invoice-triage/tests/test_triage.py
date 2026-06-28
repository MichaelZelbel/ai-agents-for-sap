"""Tests for the triage box. No real model call: we inject `complete`."""

import pytest

from sap_client import MockSapClient

from triage import LlmTriager, TriageError, route


def test_route_maps_each_known_category():
    assert route("po_invoice") == "three-way match"
    assert route("direct_expense") == "post directly"
    assert route("not_an_invoice") == "send to a person"


def test_route_refuses_an_unknown_label():
    with pytest.raises(TriageError):
        route("send_everything_to_the_ceo")


def test_classify_picks_the_category_out_of_a_chatty_reply():
    doc = MockSapClient().read_document("INV-1001")
    triager = LlmTriager(complete=lambda prompt: "This looks like a direct_expense.")
    assert triager.classify(doc) == "direct_expense"


def test_classify_rejects_a_label_it_does_not_know():
    doc = MockSapClient().read_document("INV-1001")
    triager = LlmTriager(complete=lambda prompt: "banana")
    with pytest.raises(TriageError):
        triager.classify(doc)


def test_a_made_up_category_cannot_route():
    # The model "hallucinates" a category. classify rejects it, and even if a label
    # slipped through, route() would refuse it. Two gates, same as Pattern 1.
    doc = MockSapClient().read_document("INV-1001")
    triager = LlmTriager(complete=lambda prompt: "route_to_mars")
    with pytest.raises(TriageError):
        triager.classify(doc)
