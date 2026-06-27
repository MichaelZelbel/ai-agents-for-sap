"""The Pattern 1 flow: tie the four steps together.

    read -> propose -> validate -> (human approves) -> write

The rule of the pattern lives here: if the validator fails, the human is
never asked; if the human says no, nothing is written. A posting is booked
only when the rules pass AND a human approves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from sap_client import Document, GovernedSapClient, PostingResult, ProposedPosting

from .proposer import Proposer
from .validator import ValidationResult, ValidatorConfig, validate_posting

# Called to get a human decision. Returns True to approve, False to reject.
Approve = Callable[[Document, ProposedPosting, ValidationResult], bool]


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
) -> FlowResult:
    document = client.read_document(doc_id)
    posting = proposer.propose(document, posting_date=posting_date)

    validation = validate_posting(document, posting, config=config)
    if validation.status == "FAIL":
        # The rules failed. Do not stage, do not ask a human.
        return FlowResult(outcome="rejected_by_validator", validation=validation)

    staged = client.stage_posting(posting)

    if not approve(document, posting, validation):
        return FlowResult(
            outcome="rejected_by_human",
            validation=validation,
            staged_id=staged.staged_id,
        )

    client.record_approval(staged.staged_id, approver="human")
    result = client.confirm_posting(staged.staged_id)
    return FlowResult(
        outcome="posted",
        validation=validation,
        posting_result=result,
        staged_id=staged.staged_id,
    )
