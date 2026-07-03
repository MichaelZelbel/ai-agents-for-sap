"""The Pattern 1 flow: tie the four steps together.

    read -> propose -> validate -> (human approves) -> write

The rule of the pattern lives here: if the validator fails, the human is
never asked; if the human says no, nothing is written. A posting is booked
only when the rules pass AND a human approves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Union

from sap_client import Document, GovernedSapClient, PostingResult, ProposedPosting

from .determination import DEFAULT_COST_CENTER, apply_determination
from .feedback import Decision, FeedbackStore
from .proposer import Proposer
from .validator import ValidationResult, ValidatorConfig, validate_posting

# The default identity to attribute a decision to when a caller only says yes/no.
DEFAULT_APPROVER = "a.schmidt@nordwind"


@dataclass(frozen=True)
class HumanDecision:
    """What a person decided about a staged posting, and why.

    The rationale is the point. When a reviewer rejects or corrects a draft, the
    reason they type is the signal the learning loop reads to improve the agent.
    That is why it lives on the record, not in someone's head.

    A reviewer can also *correct* the draft, not just accept or refuse it. Setting
    `corrected_cost_center` means "approve, but book it against this cost center
    instead." The guard re-checks the corrected posting, and the correction is
    remembered, so the next invoice from this vendor is proposed with it applied.
    """

    approved: bool
    approver: str = DEFAULT_APPROVER
    rationale: str = ""
    corrected_cost_center: str = ""


# Called to get a human decision. May return a HumanDecision (who, and why), or a
# bare bool (True to approve, False to reject) when the caller has nothing to add.
Approve = Callable[
    [Document, ProposedPosting, ValidationResult], Union[HumanDecision, bool]
]


def _as_decision(result: Union[HumanDecision, bool], approver: str) -> HumanDecision:
    if isinstance(result, HumanDecision):
        return result
    return HumanDecision(approved=bool(result), approver=approver)


@dataclass(frozen=True)
class FlowResult:
    outcome: str  # "posted", "rejected_by_validator", or "rejected_by_human"
    validation: ValidationResult
    posting_result: Optional[PostingResult] = None
    staged_id: Optional[str] = None


def run_pattern1(
    client: GovernedSapClient,
    proposer: Proposer,
    doc_id: str,
    *,
    posting_date: str,
    config: ValidatorConfig,
    approve: Approve,
    cost_center: str = DEFAULT_COST_CENTER,
    approver: str = DEFAULT_APPROVER,
    store: Optional[FeedbackStore] = None,
) -> FlowResult:
    document = client.read_document(doc_id)
    posting = proposer.propose(document, posting_date=posting_date)
    # The learning loop, part one: if a human has already moved this vendor's
    # invoices to a cost center, propose it with that applied. The validator still
    # checks it below, so a wrong learned value is caught like any other.
    learned_cc = store.cost_center_for(document.vendor) if store else None
    posting = apply_determination(document, posting, cost_center=learned_cc or cost_center)

    validation = validate_posting(document, posting, config=config)
    if validation.status == "FAIL":
        # The rules failed. Do not stage, do not ask a human.
        return FlowResult(outcome="rejected_by_validator", validation=validation)

    staged = client.stage_posting(posting)

    proposed = posting  # what the agent proposed, remembered as the example's "before"
    decision = _as_decision(approve(document, posting, validation), approver)
    if not decision.approved:
        # A human said no. Keep the reason: it is what the learning loop reads.
        client.record_rejection(
            staged.staged_id, approver=decision.approver, rationale=decision.rationale
        )
        _remember(store, document, doc_id, "rejected", decision, proposed, "")
        return FlowResult(
            outcome="rejected_by_human",
            validation=validation,
            staged_id=staged.staged_id,
        )

    kind = "approved"
    correction = ""
    if decision.corrected_cost_center and decision.corrected_cost_center != posting.cost_center:
        # The human corrected the draft. Re-check it: even a human's edit must
        # pass the guard before it can be booked.
        correction = f"cost center {posting.cost_center} -> {decision.corrected_cost_center}"
        corrected = apply_determination(
            document, posting, cost_center=decision.corrected_cost_center
        )
        recheck = validate_posting(document, corrected, config=config)
        if recheck.status == "FAIL":
            client.record_rejection(
                staged.staged_id,
                approver=decision.approver,
                rationale=f"correction refused by the guard: {recheck.reasons[0]}",
            )
            _remember(store, document, doc_id, "rejected", decision, proposed, "")
            return FlowResult(
                outcome="rejected_by_validator",
                validation=recheck,
                staged_id=staged.staged_id,
            )
        staged = client.stage_posting(corrected)
        posting, validation, kind = corrected, recheck, "corrected"

    # A named human approved, with an optional note. Both go on the record.
    client.record_approval(
        staged.staged_id, approver=decision.approver, rationale=decision.rationale
    )
    result = client.confirm_posting(staged.staged_id)
    _remember(store, document, doc_id, kind, decision, proposed, correction)
    return FlowResult(
        outcome="posted",
        validation=validation,
        posting_result=result,
        staged_id=staged.staged_id,
    )


def _summarize_document(d: Document) -> str:
    return f"net {d.net_amount}, tax {d.tax_amount}, gross {d.gross_amount} {d.currency}"


def _summarize_posting(p: ProposedPosting) -> str:
    lines = "; ".join(f"{ln.side} {ln.account} {ln.amount}" for ln in p.lines)
    return f"{lines}; tax {p.tax_code}; cost center {p.cost_center}"


def _remember(
    store: Optional[FeedbackStore],
    document: Document,
    doc_id: str,
    kind: str,
    decision: HumanDecision,
    proposed: ProposedPosting,
    correction: str,
) -> None:
    """Record the decision as a teachable example: the invoice, what the agent
    proposed, and what the human did about it. That is what the loop learns from,
    on any field, plus it feeds the override rate."""
    if store is None:
        return
    store.record(
        Decision(
            doc_id=doc_id,
            vendor=document.vendor,
            decision=kind,
            reason=decision.rationale,
            corrected_cost_center=(
                decision.corrected_cost_center if kind == "corrected" else ""
            ),
            invoice=_summarize_document(document),
            proposed=_summarize_posting(proposed),
            correction=correction,
            gross=str(document.gross_amount),
        )
    )
