"""Tests for the end-to-end flow: propose -> guard -> approve -> clear."""

from cashapp.flow import run_cash_application
from cashapp.guard import default_config
from cashapp.ledger import MockArLedger
from cashapp.proposer import RuleBasedMatcher
from cashapp.samples import get_payment


def always_approve(*_args) -> bool:
    return True


def always_reject(*_args) -> bool:
    return False


def test_clean_match_clears_after_approval():
    ledger = MockArLedger()
    result = run_cash_application(
        ledger,
        RuleBasedMatcher(),
        get_payment("PAY-9001"),
        config=default_config(),
        approve=always_approve,
    )
    assert result.outcome == "cleared"
    assert result.clearing is not None
    assert result.clearing.clearing_id
    assert ledger.is_payment_cleared("PAY-9001")
    steps = [entry.split(":", 1)[0] for entry in result.log.entries]
    assert steps == ["read", "propose", "guard", "approve", "clear"]


def test_human_rejection_clears_nothing():
    ledger = MockArLedger()
    result = run_cash_application(
        ledger,
        RuleBasedMatcher(),
        get_payment("PAY-9001"),
        config=default_config(),
        approve=always_reject,
    )
    assert result.outcome == "rejected_by_human"
    assert result.clearing is None
    assert not ledger.is_payment_cleared("PAY-9001")


def test_partial_payment_routes_and_never_asks_human():
    ledger = MockArLedger()
    approve_calls = []

    def spy(*args):
        approve_calls.append(args)
        return True

    result = run_cash_application(
        ledger,
        RuleBasedMatcher(),
        get_payment("PAY-9002"),  # short payment against INV-5005
        config=default_config(),
        approve=spy,
    )
    assert result.outcome == "routed_to_specialist"
    assert result.verdict.verdict == "PARTIAL"
    assert approve_calls == []  # the human is never asked on an exception
    assert not ledger.is_payment_cleared("PAY-9002")


def test_overpayment_routes_and_never_asks_human():
    ledger = MockArLedger()
    approve_calls = []

    def spy(*args):
        approve_calls.append(args)
        return True

    result = run_cash_application(
        ledger,
        RuleBasedMatcher(),
        get_payment("PAY-9003"),  # overpayment against INV-5004
        config=default_config(),
        approve=spy,
    )
    assert result.outcome == "routed_to_specialist"
    assert result.verdict.verdict == "OVERPAID"
    assert approve_calls == []


def test_replayed_payment_does_not_clear_twice():
    ledger = MockArLedger()
    first = run_cash_application(
        ledger,
        RuleBasedMatcher(),
        get_payment("PAY-9001"),
        config=default_config(),
        approve=always_approve,
    )
    assert first.outcome == "cleared"

    # Feed the very same payment again. The guard sees it is already cleared
    # and routes it. Nothing clears a second time.
    second = run_cash_application(
        ledger,
        RuleBasedMatcher(),
        get_payment("PAY-9001"),
        config=default_config(),
        approve=always_approve,
    )
    assert second.outcome == "routed_to_specialist"
    assert second.verdict.verdict == "REJECT"
