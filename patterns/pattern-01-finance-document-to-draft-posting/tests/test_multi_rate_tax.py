"""Mixed-rate invoices: a hotel bill that mixes 7%, 19% and a 0% tourism levy.

A single net/tax/gross can never foot such a document. The reader reports a
per-rate breakdown, the proposer books one expense+tax pair per rate, and the
validator reconciles every bucket. These tests run offline (no model, no key).
"""

from dataclasses import replace
from decimal import Decimal

import pytest
from sap_client import Document, TaxLine, extract_document, parse_document

from pattern1.determination import apply_determination, determine_tax_code
from pattern1.proposer import RuleBasedProposer
from pattern1.validator import default_config, validate_posting

# The real HOTEL SCHICK invoice: room 400,00 gross at 7% (net 373,83 + tax 26,17),
# breakfast 20,00 gross at 19% (net 16,81 + tax 3,19), and an 8,00 tourism levy at
# 0%. Parts sum to 428,00. German number format on purpose.
HOTEL_REPLY = (
    '{"doc_id": "26/7610", "vendor": "Hotel Schick", "currency": "EUR", '
    '"gross_amount": "428,00", "document_date": "2026-06-30", "confidence": 0.9, '
    '"tax_lines": ['
    '{"rate": 0.07, "net": "373,83", "tax": "26,17"}, '
    '{"rate": 0.19, "net": "16,81", "tax": "3,19"}, '
    '{"rate": 0, "net": "8,00", "tax": "0"}]}'
)


def hotel_document() -> Document:
    return extract_document("hotel.pdf", complete=lambda path: HOTEL_REPLY)


def config_with_codes():
    return replace(
        default_config(),
        known_tax_codes={"V0": Decimal("0.00"), "V2": Decimal("0.07"), "V1": Decimal("0.19")},
    )


# --- the reader ---------------------------------------------------------------

def test_reader_parses_the_tax_breakdown():
    doc = hotel_document()
    assert len(doc.tax_lines) == 3
    assert doc.tax_lines[0] == TaxLine(Decimal("0.07"), Decimal("373.83"), Decimal("26.17"))
    assert doc.tax_lines[2].rate == Decimal("0")


def test_reader_derives_totals_from_the_breakdown_when_they_are_omitted():
    # net and tax are not in the reply; they come from the buckets and foot to gross.
    doc = hotel_document()
    assert doc.net_amount == Decimal("398.64")
    assert doc.tax_amount == Decimal("29.36")
    assert doc.gross_amount == Decimal("428.00")
    assert doc.net_amount + doc.tax_amount == doc.gross_amount


def test_reader_accepts_a_percentage_rate_and_normalises_it():
    reply = (
        '{"doc_id": "X", "vendor": "V", "currency": "EUR", "gross_amount": "107.00", '
        '"document_date": "2026-06-30", '
        '"tax_lines": [{"rate": "7%", "net": "100.00", "tax": "7.00"}]}'
    )
    doc = extract_document("x.pdf", complete=lambda p: reply)
    assert doc.tax_lines[0].rate == Decimal("0.07")


@pytest.mark.parametrize(
    "printed, expected",
    [
        ("390,64", "390.64"),      # bare German decimal
        ("1.234,56", "1234.56"),   # European grouping
        ("1,234.56", "1234.56"),   # US grouping
        ("1000.00", "1000.00"),    # already plain
        ("€ 428,00", "428.00"),    # currency symbol and space
    ],
)
def test_reader_parses_locale_number_formats(printed, expected):
    reply = (
        '{"doc_id": "X", "vendor": "V", "currency": "EUR", '
        f'"net_amount": "{printed}", "tax_amount": "0", "gross_amount": "{printed}", '
        '"document_date": "2026-06-30"}'
    )
    doc = parse_document(reply)
    assert doc.net_amount == Decimal(expected)


# --- the validator ------------------------------------------------------------

def test_hotel_invoice_passes_end_to_end():
    doc = hotel_document()
    posting = apply_determination(doc, RuleBasedProposer().propose(doc, posting_date="2026-06-30"))
    result = validate_posting(doc, posting, config=config_with_codes())
    assert result.status == "PASS", result.reasons


def test_proposer_books_one_pair_per_rate_and_balances():
    doc = hotel_document()
    posting = RuleBasedProposer().propose(doc, posting_date="2026-06-30")
    debits = sum(l.amount for l in posting.lines if l.side == "debit")
    credits = sum(l.amount for l in posting.lines if l.side == "credit")
    assert debits == credits == Decimal("428.00")
    # two expense debits with tax + one expense debit at 0% (no tax line) + credit
    assert len(posting.lines) == 6
    assert all(l.amount > 0 for l in posting.lines)


def test_determination_labels_every_rate():
    assert determine_tax_code(hotel_document()) == "V2+V1+V0"


def test_validator_fails_when_a_bucket_does_not_foot():
    doc = hotel_document()
    broken = replace(doc, tax_lines=(TaxLine(Decimal("0.07"), Decimal("373.83"), Decimal("40.00")),
                                     doc.tax_lines[1], doc.tax_lines[2]))
    posting = apply_determination(broken, RuleBasedProposer().propose(broken, posting_date="2026-06-30"))
    result = validate_posting(broken, posting, config=config_with_codes())
    assert result.status == "FAIL"
    assert any("does not foot" in r for r in result.reasons)


def test_validator_fails_when_breakdown_does_not_reconcile_to_totals():
    doc = hotel_document()
    # Same lines, but claim a net total that the buckets do not sum to.
    mismatched = replace(doc, net_amount=Decimal("500.00"))
    posting = RuleBasedProposer().propose(doc, posting_date="2026-06-30")
    result = validate_posting(mismatched, posting, config=config_with_codes())
    assert result.status == "FAIL"
    assert any("does not sum" in r or "does not equal" in r for r in result.reasons)


def test_validator_fails_on_an_unknown_rate():
    doc = hotel_document()
    weird = replace(doc, tax_lines=(TaxLine(Decimal("0.11"), Decimal("100.00"), Decimal("11.00")),))
    weird = replace(weird, net_amount=Decimal("100.00"), tax_amount=Decimal("11.00"),
                    gross_amount=Decimal("111.00"))
    posting = RuleBasedProposer().propose(weird, posting_date="2026-06-30")
    result = validate_posting(weird, posting, config=config_with_codes())
    assert result.status == "FAIL"
    assert any("tax code" in r.lower() for r in result.reasons)


# --- the single-rate path is unchanged ---------------------------------------

def test_single_rate_invoice_still_works():
    doc = Document("INV-1", "Acme", "EUR", Decimal("1000.00"), Decimal("190.00"),
                   Decimal("1190.00"), "2026-06-30")
    posting = apply_determination(doc, RuleBasedProposer().propose(doc, posting_date="2026-06-30"))
    result = validate_posting(doc, posting, config=config_with_codes())
    assert result.status == "PASS", result.reasons
    assert len(posting.lines) == 3
    assert determine_tax_code(doc) == "V1"
