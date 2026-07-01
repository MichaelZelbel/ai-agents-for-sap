"""The deterministic mitigation: turn a score plus signals into an action.

This is the guard. The model scores, but this plain code decides what to do
about a score. No model gets a vote here. The thresholds are fixed and
readable, so the same score and signals always yield the same mitigation.

The three actions:

* remind      -- a nudge. Does not move the plan.
* resequence  -- bring the deadline forward so slack is protected. Moves the plan.
* escalate    -- raise it to the close manager. Does not move the plan.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from .models import BlockerPrediction, ClosePlan, Mitigation

# Fixed thresholds. Below REMIND, nothing is proposed.
REMIND_AT = Decimal("0.30")
RESEQUENCE_AT = Decimal("0.55")
ESCALATE_AT = Decimal("0.80")

# How many days a resequence brings a deadline forward.
RESEQUENCE_DAYS = 1


def _bring_forward(deadline: str, days: int) -> str:
    parsed = date.fromisoformat(deadline)
    return (parsed - timedelta(days=days)).isoformat()


def propose_mitigation(
    plan: ClosePlan, prediction: BlockerPrediction
) -> Mitigation | None:
    """Map one prediction to one proposed mitigation. Deterministic.

    Returns None when the score is below the remind threshold. Nothing to do.
    """
    if prediction.score < REMIND_AT:
        return None

    task = plan.get(prediction.task_id)

    if prediction.score >= ESCALATE_AT:
        return Mitigation(
            task_id=task.task_id,
            action="escalate",
            detail=(
                f"Escalate '{task.name}' (owner {task.owner}) to the close "
                f"manager. Score {prediction.score} is high risk."
            ),
        )

    if prediction.score >= RESEQUENCE_AT:
        after = _bring_forward(task.deadline, RESEQUENCE_DAYS)
        return Mitigation(
            task_id=task.task_id,
            action="resequence",
            detail=(
                f"Bring '{task.name}' forward to protect the critical path. "
                f"Deadline {task.deadline} -> {after}."
            ),
            before_deadline=task.deadline,
            after_deadline=after,
        )

    return Mitigation(
        task_id=task.task_id,
        action="remind",
        detail=f"Remind {task.owner} about '{task.name}' due {task.deadline}.",
    )
