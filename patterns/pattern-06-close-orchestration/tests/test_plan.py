"""Tests for the plan: the sample data and applying an approved change."""

from decimal import Decimal

import pytest

from close.models import Mitigation
from close.plan import apply_intervention, seed_close_plan


def test_sample_plan_has_five_tasks_in_a_chain():
    plan = seed_close_plan()
    assert len(plan.tasks) == 5
    # The chain runs T-01 -> T-02 -> T-03 -> T-04 -> T-05.
    assert plan.get("T-02").depends_on == ("T-01",)
    assert plan.get("T-05").depends_on == ("T-04",)


def test_money_is_decimal():
    plan = seed_close_plan()
    for task in plan.tasks:
        assert isinstance(task.impact, Decimal)


def test_resequence_returns_a_new_plan_with_moved_deadline():
    plan = seed_close_plan()
    mit = Mitigation(
        task_id="T-03",
        action="resequence",
        detail="bring forward",
        before_deadline="2026-07-04",
        after_deadline="2026-07-03",
    )
    new_plan = apply_intervention(plan, mit)
    assert new_plan.get("T-03").deadline == "2026-07-03"
    # The original plan is untouched. Frozen means no hidden mutation.
    assert plan.get("T-03").deadline == "2026-07-04"


def test_reminder_does_not_change_the_plan():
    plan = seed_close_plan()
    mit = Mitigation(task_id="T-03", action="remind", detail="nudge")
    new_plan = apply_intervention(plan, mit)
    assert new_plan.get("T-03").deadline == plan.get("T-03").deadline


def test_plan_is_frozen():
    plan = seed_close_plan()
    with pytest.raises(Exception):
        plan.tasks = ()
