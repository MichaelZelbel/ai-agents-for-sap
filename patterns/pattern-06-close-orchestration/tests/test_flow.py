"""Tests for the whole flow: predict, stage, approve or reject, log."""

from decimal import Decimal

from close.flow import (
    InterventionLog,
    predict_and_stage,
    run_intervention,
)
from close.plan import seed_close_plan
from close.scorer import RuleBasedScorer


def test_ranking_puts_the_at_risk_task_on_top_of_the_staged_list():
    plan = seed_close_plan()
    ranked, staged = predict_and_stage(plan, RuleBasedScorer())
    assert staged
    # T-02 is the highest scoring at-risk task and clears the guard.
    assert staged[0].mitigation.task_id == "T-02"


def test_ranking_is_by_impact_highest_first():
    plan = seed_close_plan()
    ranked, _ = predict_and_stage(plan, RuleBasedScorer())
    impacts = [plan.get(item.prediction.task_id).impact for item in ranked]
    assert impacts == sorted(impacts, reverse=True)


def test_approval_applies_the_change_to_the_plan():
    plan = seed_close_plan()
    _, staged = predict_and_stage(plan, RuleBasedScorer())
    log = InterventionLog()
    top = staged[0]

    result = run_intervention(
        plan, top, approve=lambda s, p: True, log=log
    )
    assert result.outcome == "applied"
    # The at-risk task gets escalated. Escalation does not move its deadline,
    # so we prove application by a resequence case below. Here the plan is the
    # returned one and the original is unchanged.
    assert result.plan is not plan


def test_rejection_leaves_the_plan_untouched():
    plan = seed_close_plan()
    _, staged = predict_and_stage(plan, RuleBasedScorer())
    log = InterventionLog()
    top = staged[0]

    result = run_intervention(
        plan, top, approve=lambda s, p: False, log=log
    )
    assert result.outcome == "rejected_by_human"
    # Same plan object flows through untouched.
    assert result.plan is plan


def test_resequence_moves_the_deadline_only_after_approval():
    plan = seed_close_plan()
    _, staged = predict_and_stage(plan, RuleBasedScorer())
    log = InterventionLog()
    # Find a staged resequence to prove the plan edit lands.
    reseq = [s for s in staged if s.mitigation.action == "resequence"]
    assert reseq, "expected at least one resequence in the sample plan"
    target = reseq[0]
    before = plan.get(target.mitigation.task_id).deadline

    result = run_intervention(plan, target, approve=lambda s, p: True, log=log)
    after = result.plan.get(target.mitigation.task_id).deadline
    assert after == target.mitigation.after_deadline
    assert after < before


def test_high_impact_intervention_is_logged_with_a_trace_id():
    plan = seed_close_plan()
    _, staged = predict_and_stage(plan, RuleBasedScorer())
    log = InterventionLog()
    top = staged[0]  # T-02, impact 250000, high impact

    run_intervention(plan, top, approve=lambda s, p: True, log=log)
    assert len(log.entries) == 1
    entry = log.entries[0]
    assert entry.trace_id.startswith("TRC-")
    assert entry.actor == "close-agent@nordwind"
    assert entry.outcome.startswith("applied")


def test_scoring_never_edits_the_plan_on_its_own():
    # Staging produces no plan change. Only run_intervention with approval does.
    plan = seed_close_plan()
    before = tuple(t.deadline for t in plan.tasks)
    predict_and_stage(plan, RuleBasedScorer())
    after = tuple(t.deadline for t in plan.tasks)
    assert before == after
