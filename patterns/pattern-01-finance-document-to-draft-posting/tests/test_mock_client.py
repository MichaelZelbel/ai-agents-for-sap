from decimal import Decimal

import pytest

from sap_client import (
    Document,
    DocumentNotFoundError,
    MockSapClient,
    PostingLine,
    ProposedPosting,
    StagedPostingNotFoundError,
)


def make_posting(doc_id: str = "INV-1001") -> ProposedPosting:
    return ProposedPosting(
        doc_id=doc_id,
        posting_date="2026-06-27",
        currency="EUR",
        lines=[
            PostingLine(account="600000", side="debit", amount=Decimal("1000.00")),
            PostingLine(account="154000", side="debit", amount=Decimal("190.00")),
            PostingLine(account="160000", side="credit", amount=Decimal("1190.00")),
        ],
    )


def test_read_document_returns_seeded_document():
    client = MockSapClient()
    doc = client.read_document("INV-1001")
    assert isinstance(doc, Document)
    assert doc.doc_id == "INV-1001"
    assert doc.currency == "EUR"
    assert doc.gross_amount == Decimal("1190.00")
    assert doc.net_amount == Decimal("1000.00")
    assert doc.tax_amount == Decimal("190.00")


def test_read_unknown_document_raises():
    client = MockSapClient()
    with pytest.raises(DocumentNotFoundError):
        client.read_document("NOPE")


def test_stage_posting_returns_staged_with_id():
    client = MockSapClient()
    staged = client.stage_posting(make_posting())
    assert staged.staged_id
    assert staged.status == "staged"
    assert staged.posting.doc_id == "INV-1001"


def test_confirm_posting_marks_posted_with_posting_id():
    client = MockSapClient()
    staged = client.stage_posting(make_posting())
    result = client.confirm_posting(staged.staged_id)
    assert result.status == "posted"
    assert result.posting_id
    assert result.doc_id == "INV-1001"


def test_confirm_unknown_staged_raises():
    client = MockSapClient()
    with pytest.raises(StagedPostingNotFoundError):
        client.confirm_posting("does-not-exist")
