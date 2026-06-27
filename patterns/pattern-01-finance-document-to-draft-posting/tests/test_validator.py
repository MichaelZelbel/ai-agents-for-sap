from decimal import Decimal

from sap_client import Document, PostingLine, ProposedPosting

from pattern1.validator import default_config, validate_posting

DOC = Document(
    doc_id="INV-1001",
    vendor="Office Supplies Co",
    currency="EUR",
    net_amount=Decimal("1000.00"),
    tax_amount=Decimal("190.00"),
    gross_amount=Decimal("1190.00"),
    document_date="2026-06-20",
)


def posting(lines, doc_id="INV-1001", currency="EUR", posting_date="2026-06-27"):
    return ProposedPosting(
        doc_id=doc_id, posting_date=posting_date, currency=currency, lines=lines
    )


def good_lines():
    return [
        PostingLine("600000", "debit", Decimal("1000.00")),
        PostingLine("154000", "debit", Decimal("190.00")),
        PostingLine("160000", "credit", Decimal("1190.00")),
    ]


def reasons_text(result):
    return " ".join(result.reasons).lower()


def test_passes_for_correct_posting():
    result = validate_posting(DOC, posting(good_lines()), config=default_config())
    assert result.status == "PASS"
    assert result.reasons == []


def test_fails_when_unbalanced():
    lines = [
        PostingLine("600000", "debit", Decimal("1000.00")),
        PostingLine("160000", "credit", Decimal("900.00")),
    ]
    result = validate_posting(DOC, posting(lines), config=default_config())
    assert result.status == "FAIL"
    assert "balance" in reasons_text(result)


def test_fails_when_currency_mismatch():
    result = validate_posting(
        DOC, posting(good_lines(), currency="USD"), config=default_config()
    )
    assert result.status == "FAIL"
    assert "currency" in reasons_text(result)


def test_fails_when_total_does_not_match_document_gross():
    lines = [
        PostingLine("600000", "debit", Decimal("900.00")),
        PostingLine("160000", "credit", Decimal("900.00")),
    ]
    result = validate_posting(DOC, posting(lines), config=default_config())
    assert result.status == "FAIL"
    assert "gross" in reasons_text(result)


def test_fails_when_account_not_allowed():
    lines = [
        PostingLine("999999", "debit", Decimal("1190.00")),
        PostingLine("160000", "credit", Decimal("1190.00")),
    ]
    result = validate_posting(DOC, posting(lines), config=default_config())
    assert result.status == "FAIL"
    assert "account" in reasons_text(result)


def test_fails_when_amount_not_positive():
    lines = [
        PostingLine("600000", "debit", Decimal("1190.00")),
        PostingLine("154000", "debit", Decimal("0.00")),
        PostingLine("160000", "credit", Decimal("1190.00")),
    ]
    result = validate_posting(DOC, posting(lines), config=default_config())
    assert result.status == "FAIL"
    assert "positive" in reasons_text(result)


def test_fails_when_posting_date_missing():
    result = validate_posting(
        DOC, posting(good_lines(), posting_date=""), config=default_config()
    )
    assert result.status == "FAIL"
    assert "date" in reasons_text(result)


def test_collects_multiple_reasons():
    lines = [
        PostingLine("600000", "debit", Decimal("1000.00")),
        PostingLine("160000", "credit", Decimal("900.00")),
    ]
    result = validate_posting(
        DOC, posting(lines, currency="USD"), config=default_config()
    )
    assert result.status == "FAIL"
    assert "currency" in reasons_text(result)
    assert "balance" in reasons_text(result)
    assert len(result.reasons) >= 2
