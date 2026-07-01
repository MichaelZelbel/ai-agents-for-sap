"""Tests for the model-backed drafter.

These never call a real model: we inject a `complete` callable, so the suite
runs offline with no API key. They prove the draft is only a draft, and that a
wrong draft never changes the guard's decision.
"""

from decimal import Decimal

import pytest

from expense import ExpenseLine, LlmBackedDrafter, default_policy, route_line
from expense.auditor import DrafterError, parse_verdict

LINE = ExpenseLine(
    line_id="L2",
    category="lodging",
    claimed_amount=Decimal("240.00"),
    receipt_total=Decimal("240.00"),
    date="2026-06-13",
)

GOOD_JSON = '{"compliant": false, "reasons": ["over the lodging cap"]}'


def test_drafter_parses_a_clean_verdict():
    drafter = LlmBackedDrafter(complete=lambda prompt: GOOD_JSON)
    verdict = drafter.draft(LINE, policy=default_policy())
    assert verdict.drafted_compliant is False
    assert "over the lodging cap" in verdict.reasons


def test_parses_json_inside_a_code_fence():
    fenced = "Here you go:\n```json\n" + GOOD_JSON + "\n```"
    verdict = parse_verdict(fenced, line=LINE)
    assert verdict.drafted_compliant is False


def test_a_wrong_draft_does_not_change_the_guard():
    # The model "hallucinates" that an over per diem line is compliant. The guard
    # still fails it and routes it away from fast approval. The draft has no vote.
    liar = LlmBackedDrafter(
        complete=lambda prompt: '{"compliant": true, "reasons": ["looks fine"]}'
    )
    verdict = liar.draft(LINE, policy=default_policy())
    decision = route_line(LINE, policy=default_policy(), verdict=verdict)
    assert verdict.drafted_compliant is True
    assert decision.compliant is False
    assert decision.route == "manager"
    assert decision.drafted_compliant is True  # the guess is kept for the log


def test_bad_model_output_raises():
    drafter = LlmBackedDrafter(complete=lambda prompt: "sorry, no idea")
    with pytest.raises(DrafterError):
        drafter.draft(LINE, policy=default_policy())


def test_missing_api_key_raises_when_called(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    drafter = LlmBackedDrafter()
    with pytest.raises(DrafterError):
        drafter.draft(LINE, policy=default_policy())
