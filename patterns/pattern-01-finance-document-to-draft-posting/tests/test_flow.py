from decimal import Decimal

from sap_client import (
    Document,
    GovernedSapClient,
    MockSapClient,
    PostingLine,
    ProposedPosting,
)

from pattern1.flow import run_pattern1
from pattern1.proposer import RuleBasedProposer
from pattern1.validator import default_config

FULL_ACCESS = {"read", "stage", "confirm"}


def governed() -> GovernedSapClient:
    return GovernedSapClient(MockSapClient(), entitlements=FULL_ACCESS)


def always_approve(*_args) -> bool:
    return True


def always_reject(*_args) -> bool:
    return False


def test_happy_path_posts():
    client = governed()
    result = run_pattern1(
        client,
        RuleBasedProposer(),
        "INV-1001",
        posting_date="2026-06-27",
        config=default_config(),
        approve=always_approve,
    )
    assert result.outcome == "posted"
    assert result.posting_result is not None
    assert result.posting_result.posting_id
    operations = [entry.operation for entry in client.audit_log]
    assert operations == ["read", "stage", "approve", "confirm"]


def test_human_rejection_does_not_post():
    client = governed()
    result = run_pattern1(
        client,
        RuleBasedProposer(),
        "INV-1001",
        posting_date="2026-06-27",
        config=default_config(),
        approve=always_reject,
    )
    assert result.outcome == "rejected_by_human"
    assert result.posting_result is None
    operations = [entry.operation for entry in client.audit_log]
    assert "stage" in operations
    assert "confirm" not in operations


class UnbalancedProposer:
    """A bad agent: proposes a posting that does not balance or match gross."""

    def propose(self, document, *, posting_date):
        return ProposedPosting(
            doc_id=document.doc_id,
            posting_date=posting_date,
            currency=document.currency,
            lines=[
                PostingLine("600000", "debit", Decimal("1000.00")),
                PostingLine("160000", "credit", Decimal("900.00")),
            ],
        )


def test_validator_rejection_never_reaches_human():
    client = governed()
    approve_calls = []

    def spy_approve(*args):
        approve_calls.append(args)
        return True

    result = run_pattern1(
        client,
        UnbalancedProposer(),
        "INV-1001",
        posting_date="2026-06-27",
        config=default_config(),
        approve=spy_approve,
    )
    assert result.outcome == "rejected_by_validator"
    assert result.posting_result is None
    assert approve_calls == []  # the human is never asked
    operations = [entry.operation for entry in client.audit_log]
    assert "stage" not in operations
    assert "confirm" not in operations


def test_broken_seed_invoice_is_refused_by_the_guard():
    # INV-1003 states a gross that does not match its own net + tax, so even the
    # honest rule-based proposer cannot make it balance. The guard refuses it and
    # the human is never asked. This is the exception case readers can trigger.
    client = governed()
    approve_calls = []

    def spy_approve(*args):
        approve_calls.append(args)
        return True

    result = run_pattern1(
        client,
        RuleBasedProposer(),
        "INV-1003",
        posting_date="2026-06-27",
        config=default_config(),
        approve=spy_approve,
    )
    assert result.outcome == "rejected_by_validator"
    assert approve_calls == []
    assert any("does not balance" in r for r in result.validation.reasons)


def test_your_own_registered_invoice_can_post():
    # A well-formed invoice loaded from your own file (registered on the mock)
    # runs the whole flow and posts.
    mock = MockSapClient()
    mock.register_document(
        Document(
            doc_id="MY-0001",
            vendor="Your Vendor Name",
            currency="EUR",
            net_amount=Decimal("1000.00"),
            tax_amount=Decimal("190.00"),
            gross_amount=Decimal("1190.00"),
            document_date="2026-06-27",
        )
    )
    client = GovernedSapClient(mock, entitlements=FULL_ACCESS)
    result = run_pattern1(
        client,
        RuleBasedProposer(),
        "MY-0001",
        posting_date="2026-06-27",
        config=default_config(),
        approve=always_approve,
    )
    assert result.outcome == "posted"
    assert result.posting_result is not None
