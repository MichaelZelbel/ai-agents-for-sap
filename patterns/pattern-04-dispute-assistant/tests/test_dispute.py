"""Tests for the dispute assistant. The model is faked; the guard is exercised."""

import pytest

from learning import Correction, CorrectionMemory

from dispute import (
    Assessment,
    Dispute,
    DisputeError,
    HumanDecision,
    LlmDisputeAssistant,
    parse_assessment,
    review,
    run_dispute,
)

DISPUTE = Dispute(
    dispute_id="DSP-1",
    vendor="Office Supplies Co",
    message="You only paid 1,070 EUR on invoice INV-1001 but it was for 1,190 EUR. "
    "Please pay the difference.",
)

GOOD_JSON = '{"category": "short_payment", "reply": "Dear Office Supplies Co, thank you for reaching out..."}'


def test_review_accepts_a_known_category_with_a_draft():
    rec = review(Assessment(category="short_payment", reply="Dear vendor, ..."))
    assert rec.category == "short_payment"
    assert rec.action_taken is False  # the agent only suggests


def test_review_rejects_an_unknown_category():
    with pytest.raises(DisputeError):
        review(Assessment(category="pay_them_immediately", reply="done"))


def test_review_rejects_an_empty_draft():
    with pytest.raises(DisputeError):
        review(Assessment(category="other", reply="   "))


def test_assistant_feeds_the_guard():
    assistant = LlmDisputeAssistant(complete=lambda prompt: GOOD_JSON)
    rec = review(assistant.assess(DISPUTE))
    assert rec.category == "short_payment"
    assert rec.reply
    assert rec.action_taken is False


def test_a_non_json_reply_is_rejected():
    with pytest.raises(DisputeError):
        parse_assessment("I think this is a short payment, sorry no json")


# --- the self-learning loop --------------------------------------------------- #


def test_a_discard_is_recorded_and_counts_as_an_override():
    """A human discarding the draft is a rejection: it is remembered per vendor and it
    shows up in the override rate the review watch reads."""
    store = CorrectionMemory()
    assistant = LlmDisputeAssistant(complete=lambda prompt: GOOD_JSON)
    result = run_dispute(
        assistant,
        DISPUTE,
        decide=lambda dispute, rec: HumanDecision(
            sent=False, reviewer="a.schmidt@nordwind", reason="wrong category"
        ),
        store=store,
    )
    assert result.outcome == "discarded"
    assert len(store) == 1
    overrides, total, rate = store.override_rate()
    assert (overrides, total, rate) == (1, 1, 1.0)


def test_examples_for_returns_a_past_override():
    store = CorrectionMemory()
    store.record(
        Correction(
            entity="Office Supplies Co",
            item_id="DSP-0",
            decision="rejected",
            reason="this was actually a price dispute",
            context="from Office Supplies Co: short payment on INV-1001",
            proposed="short_payment",
        )
    )
    examples = store.examples_for("Office Supplies Co")
    assert len(examples) == 1
    assert examples[0].reason == "this was actually a price dispute"


def test_the_assistant_folds_a_past_example_into_the_prompt():
    """When the store holds a past override for the vendor, the assistant's prompt
    carries it, so the model can learn from it. We capture the prompt via the injected
    complete= and assert the past reason and category appear."""
    store = CorrectionMemory()
    store.record(
        Correction(
            entity="Office Supplies Co",
            item_id="DSP-0",
            decision="rejected",
            reason="this was actually a price dispute",
            context="from Office Supplies Co: short payment on INV-1001",
            proposed="short_payment",
        )
    )
    seen = {}

    def capture(prompt: str) -> str:
        seen["prompt"] = prompt
        return GOOD_JSON

    assistant = LlmDisputeAssistant(complete=capture, store=store)
    assistant.assess(DISPUTE)
    prompt = seen["prompt"]
    assert "Past human corrections and rejections for this vendor" in prompt
    assert "this was actually a price dispute" in prompt
    assert "short_payment" in prompt


def test_no_store_means_no_examples_block():
    """The offline / no-store path is unchanged: the examples block is absent."""
    seen = {}

    def capture(prompt: str) -> str:
        seen["prompt"] = prompt
        return GOOD_JSON

    LlmDisputeAssistant(complete=capture).assess(DISPUTE)
    assert "Past human corrections and rejections" not in seen["prompt"]
