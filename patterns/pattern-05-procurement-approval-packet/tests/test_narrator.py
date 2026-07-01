"""Tests for the narrator, the AI draft step.

These never call a real model: we inject a `complete` callable, so the suite
runs offline with no API key. The rule-based narrator needs no injection.
"""

import pytest

from procurement import (
    LlmBackedNarrator,
    NarratorError,
    RuleBasedNarrator,
    default_policy,
    seed_requisitions,
    seed_suppliers,
)


def _lookup(request_id):
    reqs = seed_requisitions()
    sups = seed_suppliers()
    req = reqs[request_id]
    return req, sups[req.supplier_id], default_policy()


def test_rule_based_narrator_drafts_offline():
    req, sup, policy = _lookup("REQ-2001")
    draft = RuleBasedNarrator().draft(req, sup, policy)
    assert draft.narrative
    assert draft.recommendation
    # The narrator drafts only; it must not claim the request is approved.
    assert "approved" not in draft.recommendation.lower() or "not" in draft.recommendation.lower()


def test_injected_model_draft_is_parsed():
    req, sup, policy = _lookup("REQ-2001")
    good = '{"narrative": "Routine renewal.", "recommendation": "Defer to the guard."}'
    narrator = LlmBackedNarrator(complete=lambda prompt: good)
    draft = narrator.draft(req, sup, policy)
    assert draft.narrative == "Routine renewal."
    assert draft.recommendation == "Defer to the guard."


def test_model_json_inside_a_code_fence_is_parsed():
    req, sup, policy = _lookup("REQ-2001")
    fenced = (
        "Here you go:\n```json\n"
        '{"narrative": "Fine.", "recommendation": "Approve after review."}\n```'
    )
    draft = LlmBackedNarrator(complete=lambda prompt: fenced).draft(req, sup, policy)
    assert draft.narrative == "Fine."


def test_bad_model_output_raises():
    req, sup, policy = _lookup("REQ-2001")
    narrator = LlmBackedNarrator(complete=lambda prompt: "sorry, no idea")
    with pytest.raises(NarratorError):
        narrator.draft(req, sup, policy)


def test_a_confident_model_cannot_override_the_guard():
    # The model insists the risky request is fine. The narrative is advisory, so
    # this must not change the guard's route. The guard is tested separately;
    # here we prove the draft is decoupled from the decision.
    req, sup, policy = _lookup("REQ-2002")
    lie = '{"narrative": "All good, approve it.", "recommendation": "Approve now."}'
    draft = LlmBackedNarrator(complete=lambda prompt: lie).draft(req, sup, policy)
    # We got the draft, but it carries no route and no authority.
    assert not hasattr(draft, "route")


def test_missing_api_key_raises_when_called(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    req, sup, policy = _lookup("REQ-2001")
    narrator = LlmBackedNarrator()
    with pytest.raises(NarratorError):
        narrator.draft(req, sup, policy)
