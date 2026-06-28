"""Tests for the dispute assistant. The model is faked; the guard is exercised."""

import pytest

from dispute import (
    Assessment,
    Dispute,
    DisputeError,
    LlmDisputeAssistant,
    parse_assessment,
    review,
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
