"""The self-learning loop for Pattern 6, at the flow and scorer level.

This pattern is PREDICTION (blocker-risk scoring), the weakest fit for a learned loop:
close dynamics shift period to period, so a past dismissal transfers poorly. The loop
here is therefore deliberately cautious. It remembers every human apply/dismiss per
owner, folds dismissals back into the model's prompt only as weak priors, and leans on
the deterministic guard and the human to keep the final say. Nothing the loop learns
can move the plan on its own.

The model-backed test never calls a real model: we inject a `complete` callable, so
the suite runs offline with no API key.
"""

from decimal import Decimal

from close.flow import InterventionLog, predict_and_stage, run_intervention
from close.plan import seed_close_plan
from close.scorer import LlmBackedScorer, RuleBasedScorer

from learning import Correction, CorrectionMemory


def _top_stage(plan):
    _, staged = predict_and_stage(plan, RuleBasedScorer())
    assert staged, "expected at least one staged intervention in the sample plan"
    return staged[0]


def test_a_dismissal_is_recorded_and_counts_as_an_override():
    plan = seed_close_plan()
    top = _top_stage(plan)
    store = CorrectionMemory()
    log = InterventionLog()

    result = run_intervention(
        plan,
        top,
        approve=lambda s, p: (False, "owner is on leave, we will handle it manually"),
        log=log,
        store=store,
    )
    assert result.outcome == "rejected_by_human"
    assert len(store) == 1
    overrides, total, rate = store.override_rate()
    assert (overrides, total) == (1, 1)
    assert rate == 1.0


def test_an_apply_is_recorded_but_is_not_an_override():
    plan = seed_close_plan()
    top = _top_stage(plan)
    store = CorrectionMemory()

    # A bare bool still works (backwards compatible) and counts as an apply, not an
    # override.
    run_intervention(plan, top, approve=lambda s, p: True, log=InterventionLog(), store=store)
    overrides, total, _ = store.override_rate()
    assert (overrides, total) == (0, 1)


def test_examples_for_returns_a_past_override_for_the_owner():
    plan = seed_close_plan()
    top = _top_stage(plan)
    owner = plan.get(top.mitigation.task_id).owner
    store = CorrectionMemory()

    run_intervention(
        plan,
        top,
        approve=lambda s, p: (False, "dismiss, this one was a false alarm"),
        log=InterventionLog(),
        store=store,
    )

    examples = store.examples_for(owner)
    assert examples
    assert examples[0].entity == owner
    assert examples[0].decision == "rejected"
    assert "false alarm" in examples[0].reason
    # The proposed field carries the task id, score, and action, per the pattern.
    assert top.mitigation.task_id in examples[0].proposed


def test_scorer_prompt_includes_a_past_dismissal_for_the_owner():
    plan = seed_close_plan()
    owner = plan.get("T-02").owner
    store = CorrectionMemory()
    store.record(
        Correction(
            entity=owner,
            item_id="T-02",
            decision="rejected",
            reason="dismissed last period, the risk did not land",
            context="Post accruals",
            proposed="T-02 score 0.90 -> escalate",
            amount="250000.00",
        )
    )

    captured = {}

    def complete(prompt: str) -> str:
        captured["prompt"] = prompt
        return '{"scores": [{"task_id": "T-02", "score": "0.50"}]}'

    scorer = LlmBackedScorer(complete=complete, store=store)
    scorer.score(plan)

    prompt = captured["prompt"]
    assert "Past human corrections and dismissals" in prompt
    assert "dismissed last period" in prompt
    assert owner in prompt


def test_scorer_prompt_has_no_examples_block_when_store_is_empty():
    plan = seed_close_plan()
    store = CorrectionMemory()

    captured = {}

    def complete(prompt: str) -> str:
        captured["prompt"] = prompt
        return '{"scores": [{"task_id": "T-02", "score": "0.50"}]}'

    LlmBackedScorer(complete=complete, store=store).score(plan)
    assert "Past human corrections and dismissals" not in captured["prompt"]
