"""Tax code, cost center, and reading-confidence guards, plus the determination
that fills the codes in."""

from dataclasses import replace
from decimal import Decimal

from sap_client import Document, GovernedSapClient, MockSapClient

from pattern1.determination import determine_tax_code
from pattern1.flow import run_pattern1
from pattern1.proposer import RuleBasedProposer
from pattern1.validator import default_config, validate_posting

FULL_ACCESS = {"read", "stage", "confirm"}


def _doc(net, tax, gross, *, vendor="Office Supplies Co", confidence=None) -> Document:
    return Document(
        doc_id="D-1",
        vendor=vendor,
        currency="EUR",
        net_amount=Decimal(net),
        tax_amount=Decimal(tax),
        gross_amount=Decimal(gross),
        document_date="2026-06-27",
        confidence=confidence,
    )


def _full_config(mock: MockSapClient, *, min_confidence=None):
    return replace(
        default_config(),
        known_vendors=mock.known_vendors(),
        known_tax_codes=mock.known_tax_codes(),
        active_cost_centers=mock.active_cost_centers(),
        min_confidence=min_confidence,
    )


def test_determine_tax_code_reads_the_rate():
    assert determine_tax_code(_doc("1000.00", "190.00", "1190.00")) == "V1"
    assert determine_tax_code(_doc("1000.00", "70.00", "1070.00")) == "V2"
    assert determine_tax_code(_doc("1000.00", "0.00", "1000.00")) == "V0"
    # An unrecognised rate cannot be mapped and must be flagged.
    assert determine_tax_code(_doc("1000.00", "150.00", "1150.00")) == "V?"


def _run(mock, doc, *, config, cost_center="CC-1000"):
    mock.register_document(doc)
    client = GovernedSapClient(mock, entitlements=FULL_ACCESS)
    return run_pattern1(
        client, RuleBasedProposer(), doc.doc_id,
        posting_date="2026-06-27", config=config, cost_center=cost_center,
        approve=lambda *a: True,
    )


def test_standard_invoice_passes_every_check():
    mock = MockSapClient()
    result = _run(mock, _doc("1000.00", "190.00", "1190.00"), config=_full_config(mock))
    assert result.outcome == "posted"


def test_unrecognised_tax_rate_is_refused():
    mock = MockSapClient()
    result = _run(mock, _doc("1000.00", "150.00", "1150.00"), config=_full_config(mock))
    assert result.outcome == "rejected_by_validator"
    assert any("tax code" in r.lower() for r in result.validation.reasons)


def test_inactive_cost_center_is_refused():
    mock = MockSapClient()
    result = _run(
        mock, _doc("1000.00", "190.00", "1190.00"),
        config=_full_config(mock), cost_center="CC-9999",
    )
    assert result.outcome == "rejected_by_validator"
    assert any("cost center" in r.lower() for r in result.validation.reasons)


def test_low_confidence_is_held_for_review():
    mock = MockSapClient()
    doc = _doc("1000.00", "190.00", "1190.00", confidence=0.2)
    result = _run(mock, doc, config=_full_config(mock, min_confidence=0.5))
    assert result.outcome == "rejected_by_validator"
    assert any("confidence" in r.lower() for r in result.validation.reasons)


def test_high_confidence_passes():
    mock = MockSapClient()
    doc = _doc("1000.00", "190.00", "1190.00", confidence=0.97)
    result = _run(mock, doc, config=_full_config(mock, min_confidence=0.5))
    assert result.outcome == "posted"


def test_seeded_invoices_still_post_under_full_config():
    mock = MockSapClient()
    client = GovernedSapClient(mock, entitlements=FULL_ACCESS)
    for doc_id in ("INV-1001", "INV-1002"):
        result = run_pattern1(
            client, RuleBasedProposer(), doc_id,
            posting_date="2026-06-27", config=_full_config(mock, min_confidence=0.5),
            approve=lambda *a: True,
        )
        assert result.outcome == "posted", doc_id
