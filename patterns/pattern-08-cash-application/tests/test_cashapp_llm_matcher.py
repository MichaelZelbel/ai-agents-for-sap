"""Tests for the model-backed matcher.

These never call a real model. We inject a `complete` callable, so the suite
runs offline with no API key. The one real call lives in run_agent.py behind
--matcher llm, not in the test suite.
"""

from decimal import Decimal

import pytest

from cashapp.guard import check_match, default_config
from cashapp.ledger import MockArLedger
from cashapp.proposer import LlmBackedMatcher, MatcherError, parse_match
from cashapp.samples import get_payment

GOOD_JSON = (
    '{"invoice_ids": ["INV-5001", "INV-5002", "INV-5003"], '
    '"note": "pays two invoices minus the credit note"}'
)


def test_llm_proposal_passes_the_guard():
    ledger = MockArLedger()
    payment = get_payment("PAY-9001")
    matcher = LlmBackedMatcher(complete=lambda prompt: GOOD_JSON)
    proposal = matcher.propose(payment, ledger.open_invoices())
    verdict = check_match(payment, proposal, ledger, config=default_config())
    assert verdict.verdict == "MATCH"
    assert proposal.invoice_ids == ("INV-5001", "INV-5002", "INV-5003")


def test_parses_json_inside_a_code_fence():
    payment = get_payment("PAY-9001")
    fenced = "Sure:\n```json\n" + GOOD_JSON + "\n```"
    proposal = parse_match(fenced, payment=payment)
    assert proposal.invoice_ids[0] == "INV-5001"
    assert proposal.note


def test_a_wrong_proposal_is_caught_by_the_guard():
    # The model "hallucinates" a set that does not reconcile to the payment.
    # The parser accepts it structurally, but the deterministic guard refuses
    # to call it a match, so nothing clears.
    ledger = MockArLedger()
    payment = get_payment("PAY-9001")  # 1850.00
    wrong = '{"invoice_ids": ["INV-5001"], "note": "guessing"}'  # only 1200
    proposal = LlmBackedMatcher(complete=lambda prompt: wrong).propose(
        payment, ledger.open_invoices()
    )
    verdict = check_match(payment, proposal, ledger, config=default_config())
    assert verdict.verdict != "MATCH"
    assert verdict.matched_total == Decimal("1200.00")


def test_bad_model_output_raises():
    payment = get_payment("PAY-9001")
    matcher = LlmBackedMatcher(complete=lambda prompt: "no idea, sorry")
    with pytest.raises(MatcherError):
        matcher.propose(payment, [])


def test_missing_api_key_raises_when_called(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    payment = get_payment("PAY-9001")
    matcher = LlmBackedMatcher()
    with pytest.raises(MatcherError):
        matcher.propose(payment, [])
