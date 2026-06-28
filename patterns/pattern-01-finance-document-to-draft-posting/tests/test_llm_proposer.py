"""Tests for the model-backed proposer.

These never call a real model: we inject a `complete` callable, so the suite
runs offline with no API key. The one real call lives in a separate, opt-in
script, not in the test suite.
"""

from decimal import Decimal

import pytest

from sap_client import MockSapClient

from pattern1.proposer import LlmBackedProposer, ProposerError, parse_posting
from pattern1.validator import default_config, validate_posting

GOOD_JSON = (
    '{"lines": ['
    '{"account": "600000", "side": "debit", "amount": "1000.00"},'
    '{"account": "154000", "side": "debit", "amount": "190.00"},'
    '{"account": "160000", "side": "credit", "amount": "1190.00"}]}'
)


def test_llm_proposal_passes_the_validator():
    doc = MockSapClient().read_document("INV-1001")
    proposer = LlmBackedProposer(complete=lambda prompt: GOOD_JSON)
    posting = proposer.propose(doc, posting_date="2026-06-27")
    result = validate_posting(doc, posting, config=default_config())
    assert result.status == "PASS"
    assert len(posting.lines) == 3


def test_parses_json_inside_a_code_fence():
    doc = MockSapClient().read_document("INV-1001")
    fenced = "Here you go:\n```json\n" + GOOD_JSON + "\n```"
    posting = parse_posting(fenced, document=doc, posting_date="2026-06-27")
    assert posting.lines[0].account == "600000"
    assert posting.lines[0].amount == Decimal("1000.00")


def test_a_wrong_proposal_is_caught_by_the_validator():
    # The model "hallucinates" an unbalanced posting. The proposer accepts it
    # structurally, but the deterministic validator rejects it. Nothing books.
    doc = MockSapClient().read_document("INV-1001")
    wrong = (
        '{"lines": ['
        '{"account": "600000", "side": "debit", "amount": "1000.00"},'
        '{"account": "160000", "side": "credit", "amount": "999.00"}]}'
    )
    posting = LlmBackedProposer(complete=lambda prompt: wrong).propose(
        doc, posting_date="2026-06-27"
    )
    result = validate_posting(doc, posting, config=default_config())
    assert result.status == "FAIL"


def test_bad_model_output_raises():
    doc = MockSapClient().read_document("INV-1001")
    proposer = LlmBackedProposer(complete=lambda prompt: "sorry, no idea")
    with pytest.raises(ProposerError):
        proposer.propose(doc, posting_date="2026-06-27")


def test_missing_api_key_raises_when_called(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    doc = MockSapClient().read_document("INV-1001")
    proposer = LlmBackedProposer()
    with pytest.raises(ProposerError):
        proposer.propose(doc, posting_date="2026-06-27")
