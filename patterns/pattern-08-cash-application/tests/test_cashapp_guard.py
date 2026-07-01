"""Tests for the deterministic guard: it decides, not the AI."""

from decimal import Decimal

from cashapp.guard import check_match, default_config
from cashapp.ledger import MockArLedger
from cashapp.models import ProposedMatch
from cashapp.samples import get_payment


def test_clean_multi_invoice_with_credit_note_reconciles():
    ledger = MockArLedger()
    payment = get_payment("PAY-9001")  # 1850.00
    proposal = ProposedMatch(
        payment_id="PAY-9001",
        invoice_ids=("INV-5001", "INV-5002", "INV-5003"),  # 1200 + 800 - 150
    )
    verdict = check_match(payment, proposal, ledger, config=default_config())
    assert verdict.verdict == "MATCH"
    assert verdict.matched_total == Decimal("1850.00")
    assert verdict.difference == Decimal("0.00")


def test_short_payment_is_flagged_partial():
    ledger = MockArLedger()
    payment = get_payment("PAY-9002")  # 1500.00 against INV-5005 (2000)
    proposal = ProposedMatch(payment_id="PAY-9002", invoice_ids=("INV-5005",))
    verdict = check_match(payment, proposal, ledger, config=default_config())
    assert verdict.verdict == "PARTIAL"
    assert verdict.difference == Decimal("-500.00")


def test_overpayment_is_flagged_overpaid():
    ledger = MockArLedger()
    payment = get_payment("PAY-9003")  # 650.00 against INV-5004 (500)
    proposal = ProposedMatch(payment_id="PAY-9003", invoice_ids=("INV-5004",))
    verdict = check_match(payment, proposal, ledger, config=default_config())
    assert verdict.verdict == "OVERPAID"
    assert verdict.difference == Decimal("150.00")


def test_unknown_invoice_is_rejected():
    ledger = MockArLedger()
    payment = get_payment("PAY-9001")
    proposal = ProposedMatch(payment_id="PAY-9001", invoice_ids=("INV-9999",))
    verdict = check_match(payment, proposal, ledger, config=default_config())
    assert verdict.verdict == "REJECT"


def test_empty_proposal_is_rejected():
    ledger = MockArLedger()
    payment = get_payment("PAY-9001")
    proposal = ProposedMatch(payment_id="PAY-9001", invoice_ids=())
    verdict = check_match(payment, proposal, ledger, config=default_config())
    assert verdict.verdict == "REJECT"


def test_duplicate_invoice_in_proposal_is_rejected():
    ledger = MockArLedger()
    payment = get_payment("PAY-9001")
    proposal = ProposedMatch(
        payment_id="PAY-9001", invoice_ids=("INV-5001", "INV-5001")
    )
    verdict = check_match(payment, proposal, ledger, config=default_config())
    assert verdict.verdict == "REJECT"


def test_already_cleared_payment_is_rejected():
    ledger = MockArLedger()
    payment = get_payment("PAY-9001")
    proposal = ProposedMatch(
        payment_id="PAY-9001", invoice_ids=("INV-5001", "INV-5002", "INV-5003")
    )
    ledger.clear("PAY-9001", ("INV-5001", "INV-5002", "INV-5003"))
    verdict = check_match(payment, proposal, ledger, config=default_config())
    assert verdict.verdict == "REJECT"
    assert any("already cleared" in r.lower() for r in verdict.reasons)
