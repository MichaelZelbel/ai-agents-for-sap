"""Tests for the deterministic guard that turns a score into a mitigation."""

from decimal import Decimal

from close.models import BlockerPrediction
from close.mitigation import propose_mitigation
from close.plan import seed_close_plan


def _prediction(task_id: str, score: str) -> BlockerPrediction:
    return BlockerPrediction(task_id=task_id, score=Decimal(score))


def test_low_score_proposes_nothing():
    plan = seed_close_plan()
    assert propose_mitigation(plan, _prediction("T-03", "0.10")) is None


def test_mid_score_proposes_a_reminder():
    plan = seed_close_plan()
    mit = propose_mitigation(plan, _prediction("T-03", "0.35"))
    assert mit is not None
    assert mit.action == "remind"
    # A reminder does not move the plan.
    assert mit.after_deadline is None


def test_higher_score_proposes_a_resequence_with_before_after():
    plan = seed_close_plan()
    mit = propose_mitigation(plan, _prediction("T-03", "0.60"))
    assert mit.action == "resequence"
    task = plan.get("T-03")
    assert mit.before_deadline == task.deadline
    assert mit.after_deadline is not None
    # The new deadline is earlier than the old one.
    assert mit.after_deadline < mit.before_deadline


def test_high_score_proposes_an_escalation():
    plan = seed_close_plan()
    mit = propose_mitigation(plan, _prediction("T-02", "0.90"))
    assert mit.action == "escalate"
    assert mit.after_deadline is None


def test_mitigation_is_deterministic():
    plan = seed_close_plan()
    a = propose_mitigation(plan, _prediction("T-02", "0.90"))
    b = propose_mitigation(plan, _prediction("T-02", "0.90"))
    assert a == b
