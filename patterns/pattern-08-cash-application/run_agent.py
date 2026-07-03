"""Run Pattern 8 (Cash Application) against the fake AR ledger.

    python run_agent.py --payment PAY-9001            # show the match and verdict
    python run_agent.py --payment PAY-9001 --approve   # clear a clean match
    python run_agent.py --payment PAY-9002            # a short / partial payment
    python run_agent.py --payment PAY-9003            # an overpayment

You need no SAP account and no API key. The default matcher is deterministic
and runs offline. To use a real model instead, set OPENROUTER_API_KEY and pass
--matcher llm.

The learning loop: a human's decision (a rejection reason above all) is remembered
per customer in feedback.jsonl. The next payment from that customer is proposed with
those past decisions folded into the model's prompt, and the run prints the override
rate. When that rate crosses --override-threshold, it prints a review, so a human
looks because the number moved. Pass --reset-feedback to start from empty.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make this pattern and the shared learning loop importable when run directly.
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(REPO / "shared"))

from learning import CorrectionMemory  # noqa: E402

from cashapp.flow import HumanDecision, run_cash_application  # noqa: E402
from cashapp.guard import default_config  # noqa: E402
from cashapp.ledger import MockArLedger  # noqa: E402
from cashapp.proposer import LlmBackedMatcher, RuleBasedMatcher  # noqa: E402
from cashapp.samples import SAMPLE_PAYMENTS, get_payment  # noqa: E402

FEEDBACK_FILE = HERE / "feedback.jsonl"


def show(payment, proposal, verdict) -> None:
    print(f"\nPayment {payment.payment_id} from {payment.customer}")
    print(f"  amount {payment.amount} {payment.currency}  value date {payment.value_date}")
    print("  remittance advice:")
    for line in payment.remittance:
        print(f"    {line.reference}  {line.amount}")

    print("\nThe agent proposes clearing these invoices:")
    for invoice_id in proposal.invoice_ids or ["(none)"]:
        print(f"  {invoice_id}")
    print(f"  note: {proposal.note}")

    print(f"\nThe guard says: {verdict.verdict}")
    print(f"  matched total {verdict.matched_total}, difference {verdict.difference}")
    for reason in verdict.reasons:
        print(f"  - {reason}")


def make_approver(auto_approve: bool):
    def approve(payment, proposal, verdict) -> HumanDecision:
        show(payment, proposal, verdict)
        if auto_approve:
            print("\nHuman decision: APPROVED (auto)")
            return HumanDecision(True)
        answer = input("\nApprove this clearing? [y/N] ").strip().lower()
        approved = answer in {"y", "yes"}
        # On a rejection, capture the reason: it is the signal the loop reads.
        reason = "" if approved else input("Why? (a note for the learning loop) ").strip()
        return HumanDecision(approved, reason)

    return approve


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Pattern 8 (Cash Application).")
    parser.add_argument(
        "--payment",
        default="PAY-9001",
        help=f"payment id to process (sample ids: {', '.join(SAMPLE_PAYMENTS)})",
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="auto-approve a clean match and clear it",
    )
    parser.add_argument(
        "--matcher",
        choices=["rule", "llm"],
        default="rule",
        help="rule = offline deterministic; llm = a real model via OpenRouter",
    )
    parser.add_argument("--model", default=None, help="override the OpenRouter model")
    parser.add_argument(
        "--override-threshold",
        type=float,
        default=0.2,
        help="raise a review when the override rate climbs above this (0..1)",
    )
    parser.add_argument(
        "--reset-feedback",
        action="store_true",
        help="start the learning loop from empty (ignore feedback.jsonl)",
    )
    args = parser.parse_args()

    payment = get_payment(args.payment)
    if payment is None:
        print(f"Unknown payment id: {args.payment}")
        print(f"Try one of: {', '.join(SAMPLE_PAYMENTS)}")
        raise SystemExit(2)

    store = (
        CorrectionMemory()
        if args.reset_feedback
        else CorrectionMemory.load(FEEDBACK_FILE)
    )

    if args.matcher == "llm":
        matcher = (
            LlmBackedMatcher(model=args.model, store=store)
            if args.model
            else LlmBackedMatcher(store=store)
        )
    else:
        matcher = RuleBasedMatcher()

    ledger = MockArLedger()

    result = run_cash_application(
        ledger,
        matcher,
        payment,
        config=default_config(),
        approve=make_approver(args.approve),
        store=store,
    )

    # If --approve was not passed, the flow only reaches the human on a MATCH.
    # For a non-match we still want to print the proposal and verdict.
    if result.outcome == "routed_to_specialist" and not args.approve:
        show(payment, result.proposal, result.verdict)

    print("\n" + "=" * 48)
    print(f"Outcome: {result.outcome}")
    if result.clearing is not None:
        print(f"Cleared as: {result.clearing.clearing_id}")
        print(f"  invoices: {', '.join(result.clearing.invoice_ids)}")
    if result.outcome == "routed_to_specialist":
        print("The guard did not confirm a clean match. Routed to an AR specialist.")
        print("No human was asked to approve a clearing.")

    print("\nLog (every step the agent took):")
    for entry in (result.log.entries if result.log else []):
        print(f"  {entry}")

    # The learning loop: keep the decision, report the override rate, and raise a
    # review if it has crossed the line. This is the whole point of persisting.
    store.save(FEEDBACK_FILE)
    overrides, total, rate = store.override_rate()
    print(
        f"\nOverride rate: {overrides}/{total} = {rate:.0%} "
        f"(threshold {args.override_threshold:.0%})"
    )
    digest = store.review_needed(threshold=args.override_threshold)
    if digest is not None:
        print(
            f"\n*** REVIEW NEEDED: override rate {digest.rate:.0%} is above "
            f"{digest.threshold:.0%} over the last {digest.total} decisions. ***"
        )
        print("Recent overrides for a human to read (the signal, not the calendar):")
        for item in digest.recent[-5:]:
            why = item["reason"] or "(no reason given)"
            print(f"  {item['item_id']:<10} {item['entity']:<22} {item['decision']}: {why}")


if __name__ == "__main__":
    main()
