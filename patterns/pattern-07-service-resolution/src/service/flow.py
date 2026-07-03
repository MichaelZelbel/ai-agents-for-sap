"""The Pattern 7 flow: tie the steps together.

    gather -> propose -> guard -> (route by verdict) -> (human confirms) -> act

The rule of the pattern lives here. The action hierarchy:

* allow          read-only recommendation stands, and the routine in-policy
                 action is STAGED for a one-click human confirm. Nothing is done
                 until the human confirms.
* needs-approval nothing is staged for the agent. The step is sent to a
                 supervisor. The default remains the read-only recommendation.
* deny           the step is refused outright. No staging, no supervisor write.

The deterministic guard decides the verdict. The AI never does. A human confirms
anything that writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Union

from learning import Correction, CorrectionMemory

from .governed import GovernedServiceSource
from .guard import GuardConfig, evaluate
from .models import ActionResult, CaseContext, GuardDecision, ProposedStep
from .proposer import Proposer


@dataclass(frozen=True)
class HumanConfirmation:
    """What a person decided about a staged step, and why.

    The reason is the point. When a reviewer declines a staged step, the note they
    type is the signal the learning loop reads to improve the agent. That is why it
    lives on the record, not in someone's head. A bare bool still works when the
    caller has nothing to add.
    """

    confirmed: bool
    reason: str = ""


# Called to get a human confirmation. May return a HumanConfirmation (confirm/decline
# plus why), or a bare bool (True to confirm, False to decline) when there is no note.
Confirm = Callable[
    [CaseContext, ProposedStep, GuardDecision], Union[HumanConfirmation, bool]
]


def _as_confirmation(result: Union[HumanConfirmation, bool]) -> HumanConfirmation:
    if isinstance(result, HumanConfirmation):
        return result
    return HumanConfirmation(confirmed=bool(result))


@dataclass(frozen=True)
class FlowResult:
    outcome: str  # see the strings set below
    context: CaseContext
    step: ProposedStep
    decision: GuardDecision
    action_result: Optional[ActionResult] = None
    staged_id: Optional[str] = None


def run_pattern7(
    source: GovernedServiceSource,
    proposer: Proposer,
    case_id: str,
    *,
    config: GuardConfig,
    confirm: Confirm,
    store: Optional[CorrectionMemory] = None,
) -> FlowResult:
    context = source.gather_context(case_id)
    step = proposer.propose(context)
    decision = evaluate(context, step, config=config)

    if decision.verdict == "deny":
        # Refused outright. Nothing is staged and no human is asked to confirm.
        return FlowResult(
            outcome="denied_by_guard",
            context=context,
            step=step,
            decision=decision,
        )

    if decision.verdict == "needs-approval":
        # Beyond the agent's authority. Route to a supervisor. The read-only
        # recommendation stands, but the agent stages nothing.
        return FlowResult(
            outcome="sent_to_supervisor",
            context=context,
            step=step,
            decision=decision,
        )

    # allow: stage the routine in-policy action for a one-click confirm.
    staged = source.stage_action(step)

    confirmation = _as_confirmation(confirm(context, step, decision))
    if not confirmation.confirmed:
        # A human declined. Keep the reason: it is what the learning loop reads.
        _remember(store, context, step, "rejected", confirmation.reason)
        return FlowResult(
            outcome="declined_by_human",
            context=context,
            step=step,
            decision=decision,
            staged_id=staged.staged_id,
        )

    source.record_confirmation(staged.staged_id, approver="human")
    result = source.execute_action(staged.staged_id)
    _remember(store, context, step, "approved", confirmation.reason)
    return FlowResult(
        outcome="done",
        context=context,
        step=step,
        decision=decision,
        action_result=result,
        staged_id=staged.staged_id,
    )


def _summarize_context(context: CaseContext) -> str:
    case = context.case
    return (
        f"{case.reported_symptom} asset {context.asset.model} at {case.site}, "
        f"in warranty {context.entitlement.in_warranty}"
    )


def _summarize_step(step: ProposedStep) -> str:
    part = f" part {step.part_id}" if step.part_id else ""
    return f"{step.kind}{part}, est. cost {step.estimated_cost}"


def _remember(
    store: Optional[CorrectionMemory],
    context: CaseContext,
    step: ProposedStep,
    decision: str,
    reason: str,
) -> None:
    """Record the human decision as a teachable example: the case, what the agent
    proposed, and what the human did about it. The recurring entity this pattern
    turns on is the asset model, so corrections cluster there and feed the next
    proposal plus the override rate."""
    if store is None:
        return
    store.record(
        Correction(
            entity=context.asset.model,
            item_id=context.case.case_id,
            decision=decision,
            reason=reason,
            context=_summarize_context(context),
            proposed=_summarize_step(step),
            correction="",
            amount=str(step.estimated_cost),
        )
    )
