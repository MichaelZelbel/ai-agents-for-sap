"""The document reader: turn an invoice file into a Document with one model call.

These tests inject a fake model reply, so they run offline with no key and no
network. The live call to OpenRouter is exercised only when you actually pass a
real image or PDF at the command line.
"""

from decimal import Decimal

import pytest
from sap_client import Document, ExtractionError, extract_document, parse_document

GOOD_REPLY = (
    'Here you go:\n```json\n'
    '{"doc_id": "INV-777", "vendor": "Acme GmbH", "currency": "EUR", '
    '"net_amount": "1000.00", "tax_amount": "190.00", "gross_amount": "1190.00", '
    '"document_date": "2026-06-20"}\n```'
)


def test_parse_document_pulls_fields_from_a_messy_reply():
    doc = parse_document(GOOD_REPLY)
    assert isinstance(doc, Document)
    assert doc.doc_id == "INV-777"
    assert doc.vendor == "Acme GmbH"
    assert doc.net_amount == Decimal("1000.00")
    assert doc.gross_amount == Decimal("1190.00")


def test_extract_document_uses_injected_model():
    # complete() stands in for the model call; the file is never opened.
    doc = extract_document("invoice.pdf", complete=lambda path: GOOD_REPLY)
    assert doc.doc_id == "INV-777"
    assert doc.currency == "EUR"


def test_extract_reports_the_numbers_as_printed_even_when_they_do_not_add_up():
    # The reader must not "fix" a broken invoice; the guard catches that later.
    reply = (
        '{"doc_id": "INV-800", "vendor": "Meridian", "currency": "EUR", '
        '"net_amount": "1000.00", "tax_amount": "190.00", "gross_amount": "1200.00", '
        '"document_date": "2026-06-22"}'
    )
    doc = extract_document("scan.png", complete=lambda path: reply)
    assert doc.net_amount + doc.tax_amount != doc.gross_amount


def test_unsupported_file_type_is_refused():
    with pytest.raises(ExtractionError):
        extract_document("invoice.docx")  # no complete: real path, bad extension


def test_reply_without_json_raises():
    with pytest.raises(ExtractionError):
        parse_document("I could not read that invoice, sorry.")
