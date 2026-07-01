"""The deterministic guard: fixed arithmetic, no AI.

This is the leash. The AI may propose any set of invoices. The guard decides
whether that set is allowed to clear. It trusts only the numbers.

What the guard checks, in plain terms:

* The invoices exist and belong to the paying customer.
* The currency matches.
* The payment has not already cleared, and none of the invoices has (idempotency).
* The matched invoices sum to the payment amount, within a small tolerance.
  A credit note in the set is a negative amount, so it nets down naturally.

What the guard reports back:

* MATCH      -- the set reconciles. A human may approve it.
* PARTIAL    -- the payment is short of the matched set. Route to an AR specialist.
* OVERPAID   -- the payment is more than the matched set. Route to a specialist.
* REJECT     -- the set is invalid (unknown, wrong customer, already cleared,
                wrong currency, empty). Never clear it.

Only a MATCH may proceed to human approval. Everything else is an exception.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .ledger import MockArLedger
from .models import Payment, ProposedMatch


@dataclass(frozen=True)
class GuardConfig:
    """How much rounding slack the guard allows when reconciling."""

    tolerance: Decimal = Decimal("0.01")


def default_config() -> GuardConfig:
    return GuardConfig(tolerance=Decimal("0.01"))


@dataclass(frozen=True)
class GuardVerdict:
    """The guard's decision on a proposed match."""

    verdict: str  # "MATCH", "PARTIAL", "OVERPAID", or "REJECT"
    reasons: list[str] = field(default_factory=list)
    matched_total: Decimal = Decimal("0")
    difference: Decimal = Decimal("0")  # payment minus matched total

    @property
    def is_match(self) -> bool:
        return self.verdict == "MATCH"


def check_match(
    payment: Payment,
    proposal: ProposedMatch,
    ledger: MockArLedger,
    *,
    config: GuardConfig,
) -> GuardVerdict:
    """Decide whether the proposed set may clear this payment.

    Deterministic. Same inputs, same verdict, every time. The AI's `note` is
    never read here.
    """
    reasons: list[str] = []

    # Idempotency first. A replayed payment must never clear again.
    if ledger.is_payment_cleared(payment.payment_id):
        reasons.append(f"Payment {payment.payment_id} was already cleared.")
        return GuardVerdict(verdict="REJECT", reasons=reasons)

    if proposal.payment_id != payment.payment_id:
        reasons.append(
            f"Proposal is for {proposal.payment_id}, not {payment.payment_id}."
        )
        return GuardVerdict(verdict="REJECT", reasons=reasons)

    if not proposal.invoice_ids:
        reasons.append("Proposal matches no invoices.")
        return GuardVerdict(verdict="REJECT", reasons=reasons)

    # Duplicate ids inside one proposal are a bug, not a match.
    if len(set(proposal.invoice_ids)) != len(proposal.invoice_ids):
        reasons.append("Proposal lists the same invoice more than once.")
        return GuardVerdict(verdict="REJECT", reasons=reasons)

    matched_total = Decimal("0")
    for invoice_id in proposal.invoice_ids:
        invoice = ledger.get_invoice(invoice_id)
        if invoice is None:
            reasons.append(f"Invoice {invoice_id} does not exist.")
            continue
        if invoice.customer != payment.customer:
            reasons.append(
                f"Invoice {invoice_id} belongs to {invoice.customer}, "
                f"not {payment.customer}."
            )
            continue
        if invoice.currency != payment.currency:
            reasons.append(
                f"Invoice {invoice_id} is in {invoice.currency}, "
                f"payment is in {payment.currency}."
            )
            continue
        # A cleared invoice cannot be part of a new match (idempotency again).
        if invoice not in ledger.open_invoices():
            reasons.append(f"Invoice {invoice_id} is already cleared.")
            continue
        matched_total += invoice.amount

    if reasons:
        # Any invalid line makes the whole set unsafe. Refuse it.
        return GuardVerdict(
            verdict="REJECT", reasons=reasons, matched_total=matched_total
        )

    difference = payment.amount - matched_total

    if abs(difference) <= config.tolerance:
        return GuardVerdict(
            verdict="MATCH",
            reasons=[
                f"Payment {payment.amount} reconciles to matched total "
                f"{matched_total} within tolerance."
            ],
            matched_total=matched_total,
            difference=difference,
        )

    if difference < 0:
        # Payment is smaller than what was matched: a short / partial payment.
        return GuardVerdict(
            verdict="PARTIAL",
            reasons=[
                f"Payment {payment.amount} is short of matched total "
                f"{matched_total} by {abs(difference)}. Route to AR specialist."
            ],
            matched_total=matched_total,
            difference=difference,
        )

    # Payment is larger than what was matched: an overpayment.
    return GuardVerdict(
        verdict="OVERPAID",
        reasons=[
            f"Payment {payment.amount} exceeds matched total "
            f"{matched_total} by {difference}. Route to AR specialist."
        ],
        matched_total=matched_total,
        difference=difference,
    )
