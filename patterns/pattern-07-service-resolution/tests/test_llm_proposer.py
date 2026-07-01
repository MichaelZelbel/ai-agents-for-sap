"""Tests for the model-backed proposer.

These never call a real model: we inject a `complete` callable, so the suite runs
offline with no API key. The one real call would live in an opt-in script, not in
the test suite.
"""

from decimal import Decimal

import pytest

from service import (
    MockServiceSource,
    default_config,
)
from service.guard import evaluate
from service.proposer import LlmBackedProposer, ProposerError, parse_step

GOOD_JSON = (
    '{"kind": "replace_under_warranty", "part_id": "PRT-STATOR", '
    '"estimated_cost": "420.00", "rationale": "In warranty, covered failure."}'
)


def test_llm_proposal_is_allowed_by_the_guard():
    context = MockServiceSource().gather_context("CASE-501")
    proposer = LlmBackedProposer(complete=lambda prompt: GOOD_JSON)
    step = proposer.propose(context)
    decision = evaluate(context, step, config=default_config())
    assert decision.verdict == "allow"
    assert step.estimated_cost == Decimal("420.00")


def test_parses_json_inside_a_code_fence():
    context = MockServiceSource().gather_context("CASE-501")
    fenced = "Here you go:\n```json\n" + GOOD_JSON + "\n```"
    step = parse_step(fenced, context=context)
    assert step.kind == "replace_under_warranty"
    assert step.part_id == "PRT-STATOR"
    assert step.estimated_cost == Decimal("420.00")


def test_a_denied_proposal_is_caught_by_the_guard():
    # The model proposes a warranty replacement on an out-of-warranty asset. The
    # proposer accepts it structurally, but the deterministic guard denies it.
    context = MockServiceSource().gather_context("CASE-503")
    denied_json = (
        '{"kind": "replace_under_warranty", "part_id": "PRT-WINDING", '
        '"estimated_cost": "510.00", "rationale": "Just replace it."}'
    )
    step = LlmBackedProposer(complete=lambda prompt: denied_json).propose(context)
    decision = evaluate(context, step, config=default_config())
    assert decision.verdict == "deny"


def test_bad_step_kind_raises():
    context = MockServiceSource().gather_context("CASE-501")
    bad = '{"kind": "teleport_part", "estimated_cost": "10.00"}'
    proposer = LlmBackedProposer(complete=lambda prompt: bad)
    with pytest.raises(ProposerError):
        proposer.propose(context)


def test_non_json_output_raises():
    context = MockServiceSource().gather_context("CASE-501")
    proposer = LlmBackedProposer(complete=lambda prompt: "sorry, no idea")
    with pytest.raises(ProposerError):
        proposer.propose(context)


def test_missing_api_key_raises_when_called(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    context = MockServiceSource().gather_context("CASE-501")
    proposer = LlmBackedProposer()
    with pytest.raises(ProposerError):
        proposer.propose(context)
