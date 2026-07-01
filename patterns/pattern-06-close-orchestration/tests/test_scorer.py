"""Tests for the scorer, rule-based and model-backed.

The model-backed tests never call a real model: we inject a `complete`
callable, so the suite runs offline with no API key.
"""

from decimal import Decimal

import pytest

from close.models import ClosePlan
from close.plan import seed_close_plan
from close.scorer import (
    LlmBackedScorer,
    RuleBasedScorer,
    ScorerError,
    parse_scores,
)


def test_at_risk_task_scores_highest():
    plan = seed_close_plan()
    scores = {p.task_id: p.score for p in RuleBasedScorer().score(plan)}
    # T-02 (post accruals) carries all three signals and sits early in the chain.
    highest = max(scores, key=scores.get)
    assert highest == "T-02"
    assert scores["T-02"] > Decimal("0.55")


def test_done_task_scores_zero():
    plan = seed_close_plan()
    scores = {p.task_id: p for p in RuleBasedScorer().score(plan)}
    assert scores["T-01"].score == Decimal("0.00")


def test_scores_are_deterministic():
    plan = seed_close_plan()
    first = RuleBasedScorer().score(plan)
    second = RuleBasedScorer().score(plan)
    assert [p.score for p in first] == [p.score for p in second]


def test_scores_stay_within_bounds():
    plan = seed_close_plan()
    for pred in RuleBasedScorer().score(plan):
        assert Decimal("0.00") <= pred.score <= Decimal("1.00")


def test_llm_scores_parse_and_clamp():
    plan = seed_close_plan()
    raw = '{"scores": [{"task_id": "T-02", "score": "1.50"}]}'
    scorer = LlmBackedScorer(complete=lambda prompt: raw)
    preds = scorer.score(plan)
    assert preds[0].task_id == "T-02"
    # A score above 1.00 is clamped.
    assert preds[0].score == Decimal("1.00")


def test_llm_score_inside_a_code_fence():
    plan = seed_close_plan()
    fenced = 'Sure:\n```json\n{"scores": [{"task_id": "T-03", "score": "0.40"}]}\n```'
    preds = parse_scores(fenced, plan=plan)
    assert preds[0].task_id == "T-03"
    assert preds[0].score == Decimal("0.40")


def test_llm_scoring_an_unknown_task_raises():
    plan = seed_close_plan()
    raw = '{"scores": [{"task_id": "T-99", "score": "0.90"}]}'
    with pytest.raises(ScorerError):
        LlmBackedScorer(complete=lambda prompt: raw).score(plan)


def test_bad_model_output_raises():
    plan = seed_close_plan()
    scorer = LlmBackedScorer(complete=lambda prompt: "no idea, sorry")
    with pytest.raises(ScorerError):
        scorer.score(plan)


def test_missing_api_key_raises_when_called(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    plan = seed_close_plan()
    scorer = LlmBackedScorer()
    with pytest.raises(ScorerError):
        scorer.score(plan)
