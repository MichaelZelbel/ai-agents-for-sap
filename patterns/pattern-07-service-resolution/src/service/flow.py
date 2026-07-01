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
from typing import Callable, Optional

from .governed import GovernedServiceSource
from .guard import GuardConfig, evaluate
from .models import ActionResult, CaseContext, GuardDecision, ProposedStep
from .proposer import Proposer

# Called to get a human confirmation. Returns True to confirm, False to decline.
Confirm = Callable[[CaseContext, ProposedStep, GuardDecision], bool]


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

    if not confirm(context, step, decision):
        return FlowResult(
            outcome="declined_by_human",
            context=context,
            step=step,
            decision=decision,
            staged_id=staged.staged_id,
        )

    source.record_confirmation(staged.staged_id, approver="human")
    result = source.execute_action(staged.staged_id)
    return FlowResult(
        outcome="done",
        context=context,
        step=step,
        decision=decision,
        action_result=result,
        staged_id=staged.staged_id,
    )
