from decimal import Decimal

from sap_client import MockSapClient

from pattern1.proposer import RuleBasedProposer
from pattern1.validator import default_config, validate_posting


def test_proposes_three_line_posting_for_invoice():
    doc = MockSapClient().read_document("INV-1001")
    posting = RuleBasedProposer().propose(doc, posting_date="2026-06-27")
    assert len(posting.lines) == 3
    assert posting.doc_id == "INV-1001"
    assert posting.currency == "EUR"


def test_proposed_posting_balances_and_matches_gross():
    doc = MockSapClient().read_document("INV-1001")
    posting = RuleBasedProposer().propose(doc, posting_date="2026-06-27")
    debits = sum((l.amount for l in posting.lines if l.side == "debit"), Decimal("0"))
    credits = sum((l.amount for l in posting.lines if l.side == "credit"), Decimal("0"))
    assert debits == credits
    assert credits == doc.gross_amount


def test_proposed_posting_passes_the_validator():
    doc = MockSapClient().read_document("INV-1001")
    posting = RuleBasedProposer().propose(doc, posting_date="2026-06-27")
    result = validate_posting(doc, posting, config=default_config())
    assert result.status == "PASS"


def test_uses_the_given_posting_date():
    doc = MockSapClient().read_document("INV-1002")
    posting = RuleBasedProposer().propose(doc, posting_date="2026-07-01")
    assert posting.posting_date == "2026-07-01"
