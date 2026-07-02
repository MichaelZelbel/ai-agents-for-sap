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
    # Master data and thresholds. Each is None by default, meaning "not supplied,
    # skip that check", so the validator stays usable without a full mock behind it.
    known_vendors: frozenset[str] | None = None
    known_tax_codes: dict[str, Decimal] | None = None
    active_cost_centers: frozenset[str] | None = None
    min_confidence: float | None = None
    rate_tolerance: Decimal = Decimal("0.005")


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

    if config.known_vendors is not None and document.vendor not in config.known_vendors:
        reasons.append(f"Vendor not in master data: {document.vendor}.")

    if config.known_tax_codes is not None:
        code = posting.tax_code
        if code not in config.known_tax_codes:
            reasons.append(f"Tax code {code or '(none)'} is not a valid tax code.")
        elif document.net_amount != 0:
            actual = document.tax_amount / document.net_amount
            expected = config.known_tax_codes[code]
            if abs(actual - expected) > config.rate_tolerance:
                reasons.append(
                    f"Tax code {code} means {expected}, but the invoice tax rate is "
                    f"{actual.quantize(Decimal('0.001'))}."
                )

    if (
        config.active_cost_centers is not None
        and posting.cost_center not in config.active_cost_centers
    ):
        reasons.append(
            f"Cost center {posting.cost_center or '(none)'} does not exist or is not active."
        )

    if (
        config.min_confidence is not None
        and document.confidence is not None
        and document.confidence < config.min_confidence
    ):
        reasons.append(
            f"Low reading confidence {document.confidence:.2f} (needs "
            f"{config.min_confidence:.2f}); the document should be reviewed by a human."
        )

    status = "PASS" if not reasons else "FAIL"
    return ValidationResult(status=status, reasons=reasons)
