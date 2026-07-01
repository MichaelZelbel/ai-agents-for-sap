"""Tests for the offline, rule-based matcher."""

from cashapp.ledger import MockArLedger
from cashapp.proposer import RuleBasedMatcher
from cashapp.samples import get_payment


def test_matches_on_remittance_references():
    ledger = MockArLedger()
    payment = get_payment("PAY-9001")
    proposal = RuleBasedMatcher().propose(payment, ledger.open_invoices())
    assert set(proposal.invoice_ids) == {"INV-5001", "INV-5002", "INV-5003"}


def test_falls_back_to_a_reconciling_subset_when_no_references():
    ledger = MockArLedger()
    payment = get_payment("PAY-9003")  # 650.00, remittance quotes INV-5004 only
    # Strip the remittance so the matcher must search by amount.
    from dataclasses import replace

    bare = replace(payment, remittance=())
    proposal = RuleBasedMatcher().propose(bare, ledger.open_invoices())
    # 500 (INV-5004) minus 150 (INV-5003 credit note) sums to 350, not 650;
    # 800 (INV-5002) minus 150 = 650 does reconcile.
    total = sum(
        ledger.get_invoice(i).amount for i in proposal.invoice_ids
    )
    assert str(total) == "650.00"


def test_proposes_nothing_when_no_set_fits():
    ledger = MockArLedger()
    payment = get_payment("PAY-9002")  # 1500.00, no open subset sums to it
    from dataclasses import replace

    bare = replace(payment, remittance=())
    proposal = RuleBasedMatcher().propose(bare, ledger.open_invoices())
    assert proposal.invoice_ids == ()
