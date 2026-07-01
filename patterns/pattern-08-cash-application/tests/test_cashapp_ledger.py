"""Tests for the fake AR ledger, including its idempotency guarantee."""

import pytest

from cashapp.ledger import ClearingError, MockArLedger


def test_open_invoices_are_seeded():
    ledger = MockArLedger()
    ids = {inv.invoice_id for inv in ledger.open_invoices()}
    assert {"INV-5001", "INV-5002", "INV-5003", "INV-5004", "INV-5005"} <= ids


def test_clearing_removes_invoices_from_the_open_pool():
    ledger = MockArLedger()
    ledger.clear("PAY-9001", ("INV-5001", "INV-5002"))
    remaining = {inv.invoice_id for inv in ledger.open_invoices()}
    assert "INV-5001" not in remaining
    assert "INV-5002" not in remaining
    assert "INV-5004" in remaining


def test_same_payment_cannot_clear_twice():
    ledger = MockArLedger()
    ledger.clear("PAY-9001", ("INV-5001",))
    assert ledger.is_payment_cleared("PAY-9001")
    with pytest.raises(ClearingError):
        ledger.clear("PAY-9001", ("INV-5002",))


def test_same_invoice_cannot_clear_twice():
    ledger = MockArLedger()
    ledger.clear("PAY-9001", ("INV-5001",))
    with pytest.raises(ClearingError):
        ledger.clear("PAY-9002", ("INV-5001",))


def test_clearing_an_unknown_invoice_is_refused():
    ledger = MockArLedger()
    with pytest.raises(ClearingError):
        ledger.clear("PAY-9001", ("INV-9999",))
