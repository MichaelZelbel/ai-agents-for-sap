"""The vendor master (Business Partners): you cannot post to a vendor SAP does not
know, and onboarding one is a separate, deliberate step."""

from dataclasses import replace
from decimal import Decimal

from sap_client import Document, GovernedSapClient, MockSapClient

from pattern1.flow import run_pattern1
from pattern1.proposer import RuleBasedProposer
from pattern1.validator import default_config, validate_posting

FULL_ACCESS = {"read", "stage", "confirm"}


def _outside_invoice() -> Document:
    return Document(
        doc_id="EXT-1",
        vendor="A Vendor SAP Has Never Heard Of",
        currency="EUR",
        net_amount=Decimal("1000.00"),
        tax_amount=Decimal("190.00"),
        gross_amount=Decimal("1190.00"),
        document_date="2026-06-27",
    )


def test_seeded_vendors_are_known():
    mock = MockSapClient()
    assert mock.is_known_vendor("Office Supplies Co")
    assert not mock.is_known_vendor("A Vendor SAP Has Never Heard Of")


def test_validator_flags_a_vendor_not_in_master():
    mock = MockSapClient()
    doc = _outside_invoice()
    posting = RuleBasedProposer().propose(doc, posting_date="2026-06-27")
    config = replace(default_config(), known_vendors=mock.known_vendors())
    result = validate_posting(doc, posting, config=config)
    assert result.status == "FAIL"
    assert any("not in master data" in r for r in result.reasons)


def test_validator_skips_the_check_when_no_master_supplied():
    # default_config has no vendor master, so the check does not run (back-compat).
    doc = _outside_invoice()
    posting = RuleBasedProposer().propose(doc, posting_date="2026-06-27")
    result = validate_posting(doc, posting, config=default_config())
    assert result.status == "PASS"


def test_unknown_vendor_invoice_is_refused_before_the_human():
    mock = MockSapClient()
    mock.register_document(_outside_invoice())
    client = GovernedSapClient(mock, entitlements=FULL_ACCESS)
    config = replace(default_config(), known_vendors=mock.known_vendors())
    approve_calls = []

    result = run_pattern1(
        client,
        RuleBasedProposer(),
        "EXT-1",
        posting_date="2026-06-27",
        config=config,
        approve=lambda *a: approve_calls.append(a) or True,
    )
    assert result.outcome == "rejected_by_validator"
    assert approve_calls == []


def test_onboarding_the_vendor_then_posting_succeeds():
    mock = MockSapClient()
    mock.register_document(_outside_invoice())
    mock.add_business_partner("A Vendor SAP Has Never Heard Of")  # the master-data step
    client = GovernedSapClient(mock, entitlements=FULL_ACCESS)
    config = replace(default_config(), known_vendors=mock.known_vendors())

    result = run_pattern1(
        client,
        RuleBasedProposer(),
        "EXT-1",
        posting_date="2026-06-27",
        config=config,
        approve=lambda *a: True,
    )
    assert result.outcome == "posted"
