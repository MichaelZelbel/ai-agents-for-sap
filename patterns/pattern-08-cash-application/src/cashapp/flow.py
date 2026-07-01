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
from typing import Callable, Optional

from .guard import GuardConfig, GuardVerdict, check_match
from .ledger import ClearingError, ClearingResult, MockArLedger
from .models import Payment, ProposedMatch
from .proposer import Matcher

# Called to get a human decision. Returns True to approve, False to reject.
Approve = Callable[[Payment, ProposedMatch, GuardVerdict], bool]

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

    if not approve(payment, proposal, verdict):
        log.add("approve", "human declined -- nothing cleared")
        return FlowResult(
            outcome="rejected_by_human",
            verdict=verdict,
            proposal=proposal,
            log=log,
        )

    log.add("approve", "human approved")
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
