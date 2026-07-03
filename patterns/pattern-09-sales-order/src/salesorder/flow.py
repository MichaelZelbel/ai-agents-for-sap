"""The Pattern 9 flow: tie the steps together.

    read request -> extract -> price -> guard -> (human approves) -> release

The rule of the pattern lives here: if the guard flags the order, the human is
never asked to approve a release; if the human says no, nothing is released. A
draft order is released to fulfillment only when the guard passes AND a human
sales manager approves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Union

from learning import Correction, CorrectionMemory

from .data import CustomerRequest
from .governed_client import GovernedSalesClient
from .guard import GuardConfig, GuardResult, guard_order
from .models import DraftOrder, ReleaseResult
from .proposer import ExtractedRequest, Proposer, price_order

# The default identity a decision is attributed to when a caller only says yes/no.
DEFAULT_APPROVER = "sales-manager"


@dataclass(frozen=True)
class HumanDecision:
    """What a sales manager decided about a staged order, and why.

    The rationale is the point. When a manager rejects a draft, the reason they
    type is the signal the learning loop reads: it is folded into the prompt for
    the next request from this customer, so the agent does not re-propose the
    order that was just refused (the "usual" that mapped to the wrong SKU, a
    quantity the customer never orders). That is why the reason lives on the
    record, not in someone's head.
    """

    approved: bool
    approver: str = DEFAULT_APPROVER
    rationale: str = ""


# Called to get a human decision. May return a HumanDecision (who, and why), or a
# bare bool (True to approve, False to reject) when the caller has nothing to add.
Approve = Callable[
    [CustomerRequest, DraftOrder, GuardResult], Union[HumanDecision, bool]
]


def _as_decision(result: Union[HumanDecision, bool], approver: str) -> HumanDecision:
    if isinstance(result, HumanDecision):
        return result
    return HumanDecision(approved=bool(result), approver=approver)


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
    approver: str = DEFAULT_APPROVER,
    store: Optional[CorrectionMemory] = None,
) -> FlowResult:
    extracted = proposer.extract(request, catalog=client.catalog)
    order = price_order(request, extracted, catalog=client.catalog)

    guard = guard_order(
        order, customers=client.customers, catalog=client.catalog, config=config
    )
    if guard.status == "FLAG":
        # The guard flagged it. Do not stage, do not ask for a release approval.
        # No human decision was taken, so there is nothing to learn from here.
        return FlowResult(
            outcome="flagged_by_guard",
            extracted=extracted,
            order=order,
            guard=guard,
        )

    staged = client.stage_order(order)

    decision = _as_decision(approve(request, order, guard), approver)
    if not decision.approved:
        # A human said no. Keep the reason: it is what the learning loop reads.
        _remember(store, request, order, "rejected", decision)
        return FlowResult(
            outcome="rejected_by_human",
            extracted=extracted,
            order=order,
            guard=guard,
            staged_id=staged.staged_id,
        )

    client.record_approval(staged.staged_id, approver=decision.approver)
    result = client.release_order(staged.staged_id)
    _remember(store, request, order, "approved", decision)
    return FlowResult(
        outcome="released",
        extracted=extracted,
        order=order,
        guard=guard,
        release_result=result,
        staged_id=staged.staged_id,
    )


def _summarize_request(request: CustomerRequest) -> str:
    text = request.text.strip().replace("\n", " ")
    return text if len(text) <= 160 else text[:157] + "..."


def _summarize_order(order: DraftOrder) -> str:
    lines = "; ".join(f"{ln.quantity} x {ln.sku}" for ln in order.lines) or "(no lines)"
    return (
        f"{lines}; total {order.order_total} {order.currency}; "
        f"discount {order.discount_pct}%; ship-to {order.ship_to_country}"
    )


def _remember(
    store: Optional[CorrectionMemory],
    request: CustomerRequest,
    order: DraftOrder,
    decision_kind: str,
    decision: HumanDecision,
) -> None:
    """Record the human's decision as a teachable example: the request, what the
    agent proposed, and what the human did about it. A rejection's reason is the
    signal the loop learns from; every decision also feeds the override rate."""
    if store is None:
        return
    store.record(
        Correction(
            entity=order.customer_id,
            item_id=request.request_id,
            decision=decision_kind,
            reason=decision.rationale,
            context=_summarize_request(request),
            proposed=_summarize_order(order),
            correction="",
            amount=str(order.order_total),
        )
    )
