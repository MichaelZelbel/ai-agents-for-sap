from decimal import Decimal

import pytest

from sap_client import (
    GovernedSapClient,
    MockSapClient,
    NotApprovedError,
    NotEntitledError,
    PostingLine,
    ProposedPosting,
)

FULL_ACCESS = {"read", "stage", "confirm"}


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


def governed(entitlements=FULL_ACCESS, require_approval=True) -> GovernedSapClient:
    return GovernedSapClient(
        MockSapClient(), entitlements=entitlements, require_approval=require_approval
    )


def test_read_allowed_when_entitled():
    client = governed()
    doc = client.read_document("INV-1001")
    assert doc.doc_id == "INV-1001"


def test_read_blocked_when_not_entitled():
    client = governed(entitlements={"stage", "confirm"})
    with pytest.raises(NotEntitledError):
        client.read_document("INV-1001")


def test_confirm_blocked_without_approval():
    client = governed()
    staged = client.stage_posting(make_posting())
    with pytest.raises(NotApprovedError):
        client.confirm_posting(staged.staged_id)


def test_confirm_allowed_after_approval():
    client = governed()
    staged = client.stage_posting(make_posting())
    client.record_approval(staged.staged_id, approver="alice")
    result = client.confirm_posting(staged.staged_id)
    assert result.status == "posted"
    assert result.posting_id


def test_audit_log_records_every_call():
    client = governed()
    staged = client.stage_posting(make_posting())
    client.record_approval(staged.staged_id, approver="alice")
    client.confirm_posting(staged.staged_id)
    operations = [entry.operation for entry in client.audit_log]
    assert operations == ["stage", "approve", "confirm"]


def test_blocked_calls_are_logged():
    client = governed(entitlements={"stage", "confirm"})
    with pytest.raises(NotEntitledError):
        client.read_document("INV-1001")
    last = client.audit_log[-1]
    assert last.operation == "read"
    assert "not_entitled" in last.outcome
