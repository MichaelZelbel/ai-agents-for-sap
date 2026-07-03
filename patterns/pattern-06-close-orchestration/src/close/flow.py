"""The Pattern 6 flow: tie the steps together.

    score -> rank -> propose mitigation -> stage -> (human approves) -> apply

The rule of the pattern lives here: the model only scores; a deterministic
guard turns a score into a proposed mitigation; nothing changes the plan
until a human approves the staged intervention; every high-impact
intervention is logged with a trace id and the actor.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import count
from typing import Callable, Optional, Tuple, Union

from learning import Correction, CorrectionMemory

from .mitigation import propose_mitigation
from .models import (
    BlockerPrediction,
    ClosePlan,
    InterventionResult,
    Mitigation,
    StagedIntervention,
)
from .plan import apply_intervention
from .scorer import Scorer

# Called to get a human decision on a staged intervention. Returns True to apply and
# False to dismiss, or a (decision, reason) pair when the human has a note. The reason
# a person types when they dismiss is the signal the learning loop reads.
Approve = Callable[
    [StagedIntervention, ClosePlan], Union[bool, Tuple[bool, str]]
]

# A mitigation counts as high impact when its task's money at stake is at or
# above this line. High-impact interventions are always logged.
HIGH_IMPACT_AT = Decimal("100000.00")


@dataclass(frozen=True)
class LogEntry:
    """One line of the audit trail."""

    trace_id: str
    actor: str
    operation: str
    target: str
    outcome: str


class InterventionLog:
    """A plain, append-only log with a trace id per entry.

    A real system would use the shared governed audit. Here it is a small,
    readable stand-in so you can see the shape of the control in code.
    """

    def __init__(self, actor: str = "close-agent@nordwind") -> None:
        self._actor = actor
        self._seq = count(1)
        self.entries: list[LogEntry] = []

    def record(self, operation: str, target: str, outcome: str) -> str:
        trace_id = f"TRC-{next(self._seq):06d}"
        self.entries.append(
            LogEntry(
                trace_id=trace_id,
                actor=self._actor,
                operation=operation,
                target=target,
                outcome=outcome,
            )
        )
        return trace_id


@dataclass(frozen=True)
class Prediction:
    """A prediction paired with the mitigation the guard proposes for it."""

    prediction: BlockerPrediction
    mitigation: Optional[Mitigation]


def predict_and_stage(
    plan: ClosePlan, scorer: Scorer
) -> tuple[list[Prediction], list[StagedIntervention]]:
    """Score the plan, rank by impact, and stage a mitigation for each task
    that clears the guard's threshold. Stages only. Applies nothing.
    """
    scores = {p.task_id: p for p in scorer.score(plan)}

    ranked: list[Prediction] = []
    for task in plan.tasks:
        prediction = scores.get(
            task.task_id,
            BlockerPrediction(task_id=task.task_id, score=Decimal("0.00")),
        )
        mitigation = propose_mitigation(plan, prediction)
        ranked.append(Prediction(prediction=prediction, mitigation=mitigation))

    # Rank by impact of the underlying task, then by score. Highest first.
    ranked.sort(
        key=lambda item: (plan.get(item.prediction.task_id).impact, item.prediction.score),
        reverse=True,
    )

    staged: list[StagedIntervention] = []
    seq = count(1)
    for item in ranked:
        if item.mitigation is None:
            continue
        staged.append(
            StagedIntervention(
                staged_id=f"STG-{next(seq):04d}",
                prediction=item.prediction,
                mitigation=item.mitigation,
            )
        )
    return ranked, staged


def _decision(result: Union[bool, Tuple[bool, str]]) -> Tuple[bool, str]:
    """Normalize a human decision. The approve callable may return a bare bool, or a
    (approved, reason) pair when it has a note for the learning loop."""
    if isinstance(result, tuple):
        approved = bool(result[0])
        reason = str(result[1]) if len(result) > 1 else ""
        return approved, reason
    return bool(result), ""


def run_intervention(
    plan: ClosePlan,
    staged: StagedIntervention,
    *,
    approve: Approve,
    log: InterventionLog,
    store: Optional[CorrectionMemory] = None,
) -> InterventionResult:
    """Ask a human to approve one staged intervention, then apply or not.

    Only on approval is the in-memory plan updated. A high-impact intervention
    is logged either way, with its trace id and the actor. Every human decision,
    apply or dismiss, is remembered for the learning loop when a `store` is given.
    """
    task = plan.get(staged.mitigation.task_id)
    high_impact = task.impact >= HIGH_IMPACT_AT

    approved, reason = _decision(approve(staged, plan))

    if not approved:
        if high_impact:
            log.record("intervene", staged.staged_id, "rejected_by_human")
        # A human dismissed the intervention. Their reason is the signal.
        _remember(store, plan, staged, "rejected", reason)
        return InterventionResult(
            staged_id=staged.staged_id, outcome="rejected_by_human", plan=plan
        )

    new_plan = apply_intervention(plan, staged.mitigation)
    if high_impact:
        log.record(
            "intervene",
            staged.staged_id,
            f"applied:{staged.mitigation.action}",
        )
    _remember(store, plan, staged, "approved", reason)
    return InterventionResult(
        staged_id=staged.staged_id, outcome="applied", plan=new_plan
    )


def _summarize_task(task) -> str:
    return (
        f"{task.name}, owner {task.owner}, impact {task.impact}, "
        f"status {task.status}, deadline {task.deadline}"
    )


def _remember(
    store: Optional[CorrectionMemory],
    plan: ClosePlan,
    staged: StagedIntervention,
    decision: str,
    reason: str,
) -> None:
    """Record the human's apply/dismiss as a teachable example and count it toward the
    override rate. The entity is the task owner. `proposed` carries the task id, the
    score, and the proposed action; a dismissal's reason is what the loop learns.

    Note: this is PREDICTION memory, which transfers poorly across periods (the scorer
    folds it back in only as a weak prior). So the loop stays cautious by design, and
    the deterministic guard and the human still make every call."""
    if store is None:
        return
    task = plan.get(staged.mitigation.task_id)
    store.record(
        Correction(
            entity=task.owner,
            item_id=task.task_id,
            decision=decision,
            reason=reason,
            context=_summarize_task(task),
            proposed=(
                f"{task.task_id} score {staged.prediction.score} "
                f"-> {staged.mitigation.action}"
            ),
            correction="",
            amount=str(task.impact),
        )
    )
