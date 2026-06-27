"""The deterministic validator: fixed rules, no AI.

This is the leash. The agent may *propose* anything, but a posting only
passes if it obeys every rule here. The rules are plain code you can read,
test, and trust. The model never gets a vote.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sap_client import Document, ProposedPosting


@dataclass(frozen=True)
class ValidatorConfig:
    allowed_accounts: frozenset[str]
    tolerance: Decimal = Decimal("0.01")


def default_config() -> ValidatorConfig:
    """A small chart of accounts for the book's example postings."""
    return ValidatorConfig(
        allowed_accounts=frozenset({"600000", "154000", "160000"}),
        tolerance=Decimal("0.01"),
    )


@dataclass(frozen=True)
class ValidationResult:
    status: str  # "PASS" or "FAIL"
    reasons: list[str]


def validate_posting(
    document: Document, posting: ProposedPosting, *, config: ValidatorConfig
) -> ValidationResult:
    """Check a proposed posting against its source document and the rules."""
    reasons: list[str] = []

    debits = [line.amount for line in posting.lines if line.side == "debit"]
    credits = [line.amount for line in posting.lines if line.side == "credit"]
    total_debit = sum(debits, Decimal("0"))
    total_credit = sum(credits, Decimal("0"))

    if not debits or not credits:
        reasons.append("Posting must have at least one debit and one credit line.")

    if abs(total_debit - total_credit) > config.tolerance:
        reasons.append(
            f"Posting does not balance: debits {total_debit} vs credits {total_credit}."
        )

    if posting.currency != document.currency:
        reasons.append(
            f"Currency {posting.currency} does not match document currency "
            f"{document.currency}."
        )

    if abs(total_credit - document.gross_amount) > config.tolerance:
        reasons.append(
            f"Posting total {total_credit} does not match document gross "
            f"{document.gross_amount}."
        )

    bad_accounts = sorted(
        {line.account for line in posting.lines if line.account not in config.allowed_accounts}
    )
    if bad_accounts:
        reasons.append(f"Account(s) not allowed: {', '.join(bad_accounts)}.")

    if any(line.amount <= 0 for line in posting.lines):
        reasons.append("Every line amount must be positive.")

    if not posting.posting_date.strip():
        reasons.append("Posting date is missing.")

    if posting.doc_id != document.doc_id:
        reasons.append(
            f"Posting document id {posting.doc_id} does not match {document.doc_id}."
        )

    status = "PASS" if not reasons else "FAIL"
    return ValidationResult(status=status, reasons=reasons)
