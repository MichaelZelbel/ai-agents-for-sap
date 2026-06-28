"""Capstone: the same flow runs against the real-SAP client, with only the inner
client swapped. The transport is faked here, so this needs no licensed tenant. In
production the transport makes the real OData calls and confirm books a real journal
entry. The agent, the governed boundary, the validator, and the flow are unchanged.
"""

from sap_client import GovernedSapClient, S4SapClient

from pattern1.flow import run_pattern1
from pattern1.proposer import RuleBasedProposer
from pattern1.validator import default_config


def fake_s4(operation: str, args: dict) -> dict:
    """Stands in for a real S/4HANA. Your transport would call OData here instead."""
    if operation == "read_document":
        return {
            "doc_id": args["doc_id"],
            "vendor": "Office Supplies Co",
            "currency": "EUR",
            "net_amount": "1000.00",
            "tax_amount": "190.00",
            "gross_amount": "1190.00",
            "document_date": "2026-06-20",
        }
    if operation == "park_journal_entry":
        return {"parked_id": "PARK-1"}
    if operation == "post_journal_entry":
        return {"document_number": "5100000001", "doc_id": "INV-1001"}
    raise AssertionError(f"unexpected operation: {operation}")


def test_the_whole_flow_runs_against_the_real_sap_client():
    client = GovernedSapClient(
        S4SapClient(base_url="https://my-s4.example", transport=fake_s4),
        entitlements={"read", "stage", "confirm"},
    )

    result = run_pattern1(
        client,
        RuleBasedProposer(),
        "INV-1001",
        posting_date="2026-06-27",
        config=default_config(),
        approve=lambda document, posting, validation: True,
    )

    # Same outcome as the mock, now with a SAP-style document number from confirm.
    assert result.outcome == "posted"
    assert result.posting_result.posting_id == "5100000001"
    # Same governance: identity, approval, and a tamper-evident audit, all unchanged.
    assert client.verify_audit() is True
    assert [e.operation for e in client.audit_log] == ["read", "stage", "approve", "confirm"]
