"""The Pattern 9 flow: tie the steps together.

    read request -> extract -> price -> guard -> (human approves) -> release

The rule of the pattern lives here: if the guard flags the order, the human is
never asked to approve a release; if the human says no, nothing is released. A
draft order is released to fulfillment only when the guard passes AND a human
sales manager approves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .data import CustomerRequest
from .governed_client import GovernedSalesClient
from .guard import GuardConfig, GuardResult, guard_order
from .models import DraftOrder, ReleaseResult
from .proposer import ExtractedRequest, Proposer, price_order

# Called to get a human decision. Returns True to approve, False to reject.
Approve = Callable[[CustomerRequest, DraftOrder, GuardResult], bool]


@dataclass(frozen=True)
class FlowResult:
    outcome: str  # "released", "flagged_by_guard", or "rejected_by_human"
    extracted: ExtractedRequest
    order: DraftOrder
    guard: GuardResult
    release_result: Optional[ReleaseResult] = None
    staged_id: Optional[str] = None


def run_pattern9(
    client: GovernedSalesClient,
    proposer: Proposer,
    request: CustomerRequest,
    *,
    config: GuardConfig,
    approve: Approve,
) -> FlowResult:
    extracted = proposer.extract(request, catalog=client.catalog)
    order = price_order(request, extracted, catalog=client.catalog)

    guard = guard_order(
        order, customers=client.customers, catalog=client.catalog, config=config
    )
    if guard.status == "FLAG":
        # The guard flagged it. Do not stage, do not ask for a release approval.
        return FlowResult(
            outcome="flagged_by_guard",
            extracted=extracted,
            order=order,
            guard=guard,
        )

    staged = client.stage_order(order)

    if not approve(request, order, guard):
        return FlowResult(
            outcome="rejected_by_human",
            extracted=extracted,
            order=order,
            guard=guard,
            staged_id=staged.staged_id,
        )

    client.record_approval(staged.staged_id, approver="sales-manager")
    result = client.release_order(staged.staged_id)
    return FlowResult(
        outcome="released",
        extracted=extracted,
        order=order,
        guard=guard,
        release_result=result,
        staged_id=staged.staged_id,
    )
