"""Run Pattern 8 (Cash Application) against the fake AR ledger.

    python run_agent.py --payment PAY-9001            # show the match and verdict
    python run_agent.py --payment PAY-9001 --approve   # clear a clean match
    python run_agent.py --payment PAY-9002            # a short / partial payment
    python run_agent.py --payment PAY-9003            # an overpayment

You need no SAP account and no API key. The default matcher is deterministic
and runs offline. To use a real model instead, set OPENROUTER_API_KEY and pass
--matcher llm.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make this pattern importable when run directly.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

from cashapp.flow import run_cash_application  # noqa: E402
from cashapp.guard import default_config  # noqa: E402
from cashapp.ledger import MockArLedger  # noqa: E402
from cashapp.proposer import LlmBackedMatcher, RuleBasedMatcher  # noqa: E402
from cashapp.samples import SAMPLE_PAYMENTS, get_payment  # noqa: E402


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
    def approve(payment, proposal, verdict) -> bool:
        show(payment, proposal, verdict)
        if auto_approve:
            print("\nHuman decision: APPROVED (auto)")
            return True
        answer = input("\nApprove this clearing? [y/N] ").strip().lower()
        return answer in {"y", "yes"}

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
    args = parser.parse_args()

    payment = get_payment(args.payment)
    if payment is None:
        print(f"Unknown payment id: {args.payment}")
        print(f"Try one of: {', '.join(SAMPLE_PAYMENTS)}")
        raise SystemExit(2)

    if args.matcher == "llm":
        matcher = (
            LlmBackedMatcher(model=args.model) if args.model else LlmBackedMatcher()
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


if __name__ == "__main__":
    main()
