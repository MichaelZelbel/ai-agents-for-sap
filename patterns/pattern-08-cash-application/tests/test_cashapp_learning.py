"""Tests for the shared self-learning loop wired into cash application.

The loop keys on the payment's customer. A human decision is remembered per
customer, the override rate counts it, and past overrides are folded into the
model-backed matcher's prompt. These run offline: no store persistence to disk,
and the matcher's `complete` callable is injected.
"""

from learning import CorrectionMemory

from cashapp.flow import HumanDecision, run_cash_application
from cashapp.guard import default_config
from cashapp.ledger import MockArLedger
from cashapp.proposer import LlmBackedMatcher, RuleBasedMatcher
from cashapp.samples import get_payment

REASON = "customer disputes INV-5002, do not clear yet"


def reject_with_reason(*_args) -> HumanDecision:
    return HumanDecision(False, REASON)


def _seed_one_rejection(store: CorrectionMemory):
    """Run PAY-9001 (a clean guard MATCH) to the human, who rejects with a reason.
    Returns the payment so callers can key on its customer/amount."""
    payment = get_payment("PAY-9001")
    result = run_cash_application(
        MockArLedger(),
        RuleBasedMatcher(),
        payment,
        config=default_config(),
        approve=reject_with_reason,
        store=store,
    )
    assert result.outcome == "rejected_by_human"
    return payment


def test_rejection_is_recorded_and_counts_as_an_override():
    store = CorrectionMemory()
    _seed_one_rejection(store)

    assert len(store) == 1
    overrides, total, rate = store.override_rate()
    assert (overrides, total) == (1, 1)
    assert rate == 1.0


def test_examples_for_returns_a_past_override_for_the_customer():
    store = CorrectionMemory()
    payment = _seed_one_rejection(store)

    examples = store.examples_for(payment.customer, payment.amount)
    assert len(examples) == 1
    e = examples[0]
    assert e.entity == payment.customer
    assert e.item_id == payment.payment_id
    assert e.decision == "rejected"
    assert "disputes" in e.reason
    assert "INV-5001" in e.proposed  # the set the agent proposed to clear


def test_matcher_prompt_includes_a_past_example():
    store = CorrectionMemory()
    payment = _seed_one_rejection(store)

    captured = {}

    def spy_complete(prompt: str) -> str:
        captured["prompt"] = prompt
        return (
            '{"invoice_ids": ["INV-5001", "INV-5002", "INV-5003"], '
            '"note": "ok"}'
        )

    matcher = LlmBackedMatcher(complete=spy_complete, store=store)
    # A fresh ledger, so the customer's open invoices are all available again.
    matcher.propose(payment, MockArLedger().open_invoices())

    prompt = captured["prompt"]
    assert "Past human corrections and rejections for this customer" in prompt
    assert "disputes" in prompt


def test_approval_is_recorded_but_is_not_an_override():
    store = CorrectionMemory()
    result = run_cash_application(
        MockArLedger(),
        RuleBasedMatcher(),
        get_payment("PAY-9001"),
        config=default_config(),
        approve=lambda *_a: HumanDecision(True),
        store=store,
    )
    assert result.outcome == "cleared"
    assert len(store) == 1
    overrides, total, _rate = store.override_rate()
    assert (overrides, total) == (0, 1)
