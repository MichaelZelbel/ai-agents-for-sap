"""The deterministic entitlement guard: fixed rules, no AI.

This is the leash. The agent may propose any next step, but the guard alone
decides what happens to it. The guard reads the proposed step and the gathered
entitlement snapshot, then returns exactly one verdict:

* allow          the step is in policy and inside the entitlement limit. It may
                 be staged for a one-click human confirm.
* needs-approval the step is plausible but crosses a policy line, e.g. a covered
                 repair at a site the plan does not list, or a cost over the
                 approval limit. A supervisor must sign off.
* deny           the step is not permitted at all, e.g. a warranty replacement on
                 an asset that is out of warranty.

The rules are plain code you can read, test, and trust. The model never gets a
vote on the verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import CaseContext, GuardDecision, ProposedStep


@dataclass(frozen=True)
class GuardConfig:
    """Policy knobs for the guard. Kept small and explicit."""

    # A covered action at or below this cost can be allowed outright. Above it,
    # a supervisor must approve.
    approval_limit: Decimal = Decimal("800.00")


def default_config() -> GuardConfig:
    return GuardConfig(approval_limit=Decimal("800.00"))


def evaluate(
    context: CaseContext, step: ProposedStep, *, config: GuardConfig
) -> GuardDecision:
    """Evaluate a proposed step against the entitlement snapshot and policy.

    Returns one verdict with a short reason. The order matters: hard denials are
    checked before softer needs-approval cases, so a warranty claim on an expired
    asset is denied outright rather than sent up for approval.
    """
    entitlement = context.entitlement
    site = context.case.site

    # An escalation is always the safe fallback. Route it to a supervisor.
    if step.kind == "escalate":
        return GuardDecision(
            verdict="needs-approval",
            reason="Step is an explicit escalation. Route to a supervisor.",
        )

    # Rejecting a claim writes nothing that costs money, but it is customer
    # facing, so a human still confirms it. Treat it as an allowed staged action.
    if step.kind == "reject_claim":
        return GuardDecision(
            verdict="allow",
            reason="Rejecting a claim is reversible and costs nothing. Confirm and send.",
        )

    # A warranty replacement is only valid while the asset is in warranty.
    if step.kind == "replace_under_warranty" and not entitlement.in_warranty:
        return GuardDecision(
            verdict="deny",
            reason=(
                f"Asset {entitlement.asset_id} is out of warranty "
                f"(expired {entitlement.expires_on}). Warranty replacement is not covered."
            ),
        )

    # A covered action at a site the plan does not list needs a supervisor.
    if site not in entitlement.covered_sites:
        return GuardDecision(
            verdict="needs-approval",
            reason=(
                f"Site {site} is not on the covered list for plan "
                f"{entitlement.plan}. A supervisor must approve an out-of-site repair."
            ),
        )

    # Cost over the entitlement limit needs a supervisor even when in policy.
    limit = min(config.approval_limit, entitlement.approval_limit)
    if step.estimated_cost > limit:
        return GuardDecision(
            verdict="needs-approval",
            reason=(
                f"Estimated cost {step.estimated_cost} exceeds the approval limit "
                f"{limit}. A supervisor must sign off."
            ),
        )

    # In warranty, in a covered site, under the limit. Allow, then a human
    # confirms the write.
    return GuardDecision(
        verdict="allow",
        reason=(
            f"In policy: in warranty, site {site} covered, cost {step.estimated_cost} "
            f"within limit {limit}. Stage for a one-click confirm."
        ),
    )
