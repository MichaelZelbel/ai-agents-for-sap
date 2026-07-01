"""The close plan: seed the sample data and apply an approved change.

The plan is frozen. `apply_intervention` never mutates in place. It builds a
new plan with the one task changed. That is the only way the plan changes,
and it only runs after a human approves.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from .models import ClosePlan, CloseTask, Mitigation


def seed_close_plan() -> ClosePlan:
    """Five close tasks with one dependency chain and one clearly at-risk task.

    The chain: reconcile bank -> post accruals -> run allocations ->
    close subledgers -> publish results. Accruals is the at-risk task. It was
    late last period, its queue is backed up, and its owner is overloaded. It
    sits early in the chain, so if it slips the whole close slips.
    """
    return ClosePlan(
        period="2026-06",
        tasks=(
            CloseTask(
                task_id="T-01",
                name="Reconcile bank accounts",
                owner="alice",
                deadline="2026-07-02",
                status="done",
                impact=Decimal("50000.00"),
            ),
            CloseTask(
                task_id="T-02",
                name="Post accruals",
                owner="bob",
                deadline="2026-07-03",
                status="not_started",
                impact=Decimal("250000.00"),
                depends_on=("T-01",),
                late_last_period=True,
                queue_backed_up=True,
                owner_overloaded=True,
            ),
            CloseTask(
                task_id="T-03",
                name="Run cost allocations",
                owner="carol",
                deadline="2026-07-04",
                status="not_started",
                impact=Decimal("120000.00"),
                depends_on=("T-02",),
            ),
            CloseTask(
                task_id="T-04",
                name="Close subledgers",
                owner="dave",
                deadline="2026-07-05",
                status="not_started",
                impact=Decimal("80000.00"),
                depends_on=("T-03",),
                queue_backed_up=True,
                late_last_period=True,
            ),
            CloseTask(
                task_id="T-05",
                name="Publish results",
                owner="erin",
                deadline="2026-07-06",
                status="not_started",
                impact=Decimal("300000.00"),
                depends_on=("T-04",),
            ),
        ),
    )


def apply_intervention(plan: ClosePlan, mitigation: Mitigation) -> ClosePlan:
    """Return a new plan with the mitigation applied to its one task.

    A reminder or an escalation does not change any field on the plan. A
    resequence moves the task's deadline earlier. Either way we return a fresh,
    frozen plan so the change is explicit and never a hidden mutation.
    """
    new_tasks = []
    for task in plan.tasks:
        if task.task_id == mitigation.task_id and mitigation.after_deadline:
            new_tasks.append(replace(task, deadline=mitigation.after_deadline))
        else:
            new_tasks.append(task)
    return ClosePlan(period=plan.period, tasks=tuple(new_tasks))
