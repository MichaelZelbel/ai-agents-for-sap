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
    """

    approved: bool
    approver: str = DEFAULT_APPROVER
    rationale: str = ""


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
) -> FlowResult:
    document = client.read_document(doc_id)
    posting = proposer.propose(document, posting_date=posting_date)
    # Deterministic tax and cost-center determination, then the rules check both.
    posting = apply_determination(document, posting, cost_center=cost_center)

    validation = validate_posting(document, posting, config=config)
    if validation.status == "FAIL":
        # The rules failed. Do not stage, do not ask a human.
        return FlowResult(outcome="rejected_by_validator", validation=validation)

    staged = client.stage_posting(posting)

    decision = _as_decision(approve(document, posting, validation), approver)
    if not decision.approved:
        # A human said no. Keep the reason: it is what the learning loop reads.
        client.record_rejection(
            staged.staged_id, approver=decision.approver, rationale=decision.rationale
        )
        return FlowResult(
            outcome="rejected_by_human",
            validation=validation,
            staged_id=staged.staged_id,
        )

    # A named human approved, with an optional note. Both go on the record.
    client.record_approval(
        staged.staged_id, approver=decision.approver, rationale=decision.rationale
    )
    result = client.confirm_posting(staged.staged_id)
    return FlowResult(
        outcome="posted",
        validation=validation,
        posting_result=result,
        staged_id=staged.staged_id,
    )
