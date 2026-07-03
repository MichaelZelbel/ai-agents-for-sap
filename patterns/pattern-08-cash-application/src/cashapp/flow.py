"""The cash-application flow: tie the steps together.

    read open items -> propose match -> guard -> (human approves) -> clear

The rule of the pattern lives here. If the guard does not return MATCH, the
human is never asked to approve a clearing. Exceptions (partial, overpaid,
rejected) route to an AR specialist instead. If the human says no, nothing
clears. A clearing posts only when the guard says MATCH and a human approves.

Every step is logged so you can see exactly what the agent did and why.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Union

from learning import Correction, CorrectionMemory

from .guard import GuardConfig, GuardVerdict, check_match
from .ledger import ClearingError, ClearingResult, MockArLedger
from .models import Payment, ProposedMatch
from .proposer import Matcher


@dataclass(frozen=True)
class HumanDecision:
    """What a person decided about a proposed clearing, and why.

    The rationale is the point. When a reviewer rejects a proposed match, the
    reason they type is the signal the learning loop reads to improve the agent
    for this customer. That is why it lives on the record, not in someone's head.
    """

    approved: bool
    rationale: str = ""


# Called to get a human decision. May return a HumanDecision (approve/reject, and
# why) or a bare bool (True to approve, False to reject) when there is nothing to add.
Approve = Callable[
    [Payment, ProposedMatch, GuardVerdict], Union["HumanDecision", bool]
]


def _as_decision(result: Union[HumanDecision, bool]) -> HumanDecision:
    if isinstance(result, HumanDecision):
        return result
    return HumanDecision(approved=bool(result))

# Called with an exception so it can be routed to a person. Payment id and a
# short reason. Returns nothing. Here it just records; in a real system it
# would open a work item for an AR specialist.
RouteException = Callable[[Payment, GuardVerdict], None]


@dataclass
class CashAppLog:
    """A plain, append-only log of what the agent did on one payment."""

    entries: list[str] = field(default_factory=list)

    def add(self, step: str, detail: str) -> None:
        self.entries.append(f"{step}: {detail}")


@dataclass(frozen=True)
class FlowResult:
    outcome: str  # see below
    verdict: GuardVerdict
    proposal: ProposedMatch
    clearing: Optional[ClearingResult] = None
    log: Optional[CashAppLog] = None
    # outcomes:
    #   "cleared"              -- guard matched, human approved, ledger cleared
    #   "rejected_by_human"    -- guard matched, human declined
    #   "routed_to_specialist" -- guard returned PARTIAL / OVERPAID / REJECT
    #   "clearing_failed"      -- ledger refused at the last moment (idempotency)


def _default_router(log: CashAppLog) -> RouteException:
    def route(payment: Payment, verdict: GuardVerdict) -> None:
        log.add(
            "route",
            f"payment {payment.payment_id} -> AR specialist ({verdict.verdict})",
        )

    return route


def run_cash_application(
    ledger: MockArLedger,
    matcher: Matcher,
    payment: Payment,
    *,
    config: GuardConfig,
    approve: Approve,
    route_exception: Optional[RouteException] = None,
    store: Optional[CorrectionMemory] = None,
) -> FlowResult:
    log = CashAppLog()
    router = route_exception or _default_router(log)

    open_invoices = ledger.open_invoices()
    log.add("read", f"{len(open_invoices)} open invoices for {payment.customer}")

    proposal = matcher.propose(payment, open_invoices)
    log.add(
        "propose",
        f"invoices {list(proposal.invoice_ids) or 'none'} -- {proposal.note}",
    )

    verdict = check_match(payment, proposal, ledger, config=config)
    log.add("guard", f"{verdict.verdict} -- {'; '.join(verdict.reasons)}")

    if not verdict.is_match:
        # The guard did not confirm a clean match. Do not ask a human to
        # approve a clearing. Route the exception to a person instead.
        router(payment, verdict)
        return FlowResult(
            outcome="routed_to_specialist",
            verdict=verdict,
            proposal=proposal,
            log=log,
        )

    decision = _as_decision(approve(payment, proposal, verdict))
    if not decision.approved:
        # A human said no. Keep the reason: it is what the learning loop reads,
        # per customer, so the agent proposes better next time.
        log.add("approve", "human declined -- nothing cleared")
        _remember(store, payment, proposal, "rejected", decision)
        return FlowResult(
            outcome="rejected_by_human",
            verdict=verdict,
            proposal=proposal,
            log=log,
        )

    # A human approved this clearing. Record the decision either way, so the
    # override rate counts approvals as well as rejections.
    log.add("approve", "human approved")
    _remember(store, payment, proposal, "approved", decision)
    try:
        clearing = ledger.clear(payment.payment_id, proposal.invoice_ids)
    except ClearingError as exc:
        # The ledger refused at the last moment. Idempotency held. Log and route.
        log.add("clear", f"refused -- {exc}")
        router(payment, verdict)
        return FlowResult(
            outcome="clearing_failed",
            verdict=verdict,
            proposal=proposal,
            log=log,
        )

    log.add("clear", f"posted {clearing.clearing_id} for {list(clearing.invoice_ids)}")
    return FlowResult(
        outcome="cleared",
        verdict=verdict,
        proposal=proposal,
        clearing=clearing,
        log=log,
    )


def _summarize_payment(payment: Payment) -> str:
    remit = (
        ", ".join(f"{line.reference} {line.amount}" for line in payment.remittance)
        or "no remittance"
    )
    return f"{payment.amount} {payment.currency}; remittance: {remit}"


def _summarize_proposal(proposal: ProposedMatch) -> str:
    ids = ", ".join(proposal.invoice_ids) or "none"
    note = f" -- {proposal.note}" if proposal.note else ""
    return f"invoices {ids}{note}"


def _remember(
    store: Optional[CorrectionMemory],
    payment: Payment,
    proposal: ProposedMatch,
    decision: str,
    human: HumanDecision,
) -> None:
    """Record the human decision as a teachable example, keyed by the customer:
    what the payment looked like, which invoices the agent proposed to clear, and
    what the human did about it. That is what the loop learns from, plus it feeds
    the override rate."""
    if store is None:
        return
    store.record(
        Correction(
            entity=payment.customer,
            item_id=payment.payment_id,
            decision=decision,
            reason=human.rationale,
            context=_summarize_payment(payment),
            proposed=_summarize_proposal(proposal),
            correction="",
            amount=str(payment.amount),
        )
    )
