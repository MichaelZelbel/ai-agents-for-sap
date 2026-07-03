"""Run Pattern 9 end to end against the fake, governed sales system.

    python run_agent.py --request REQ-1              # show extraction, draft, flags
    python run_agent.py --request REQ-1 --approve     # release a clean order
    python run_agent.py --request REQ-2               # a flagged order (over policy)
    python run_agent.py --request REQ-3               # a flagged order (short stock)
    python run_agent.py --request REQ-1 --reject --rationale "wrong SKU, not the usual"

The learning loop: every decision (a release or a rejection reason) is remembered
per customer in feedback.jsonl. The next request from that customer is extracted
with the past rejections folded into the model's prompt, and the run prints the
override rate. When that rate crosses --override-threshold, it prints a review so
a human looks because the number moved.

You need no SAP account and no API key. Everything runs in memory with the
deterministic proposer. Pass --proposer llm to use a real model via OpenRouter.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make this pattern and the shared learning layer importable when run directly.
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(REPO / "shared"))

from learning import CorrectionMemory  # noqa: E402

from salesorder import (  # noqa: E402
    GovernedSalesClient,
    HumanDecision,
    LlmBackedProposer,
    MockSalesClient,
    RuleBasedProposer,
    default_config,
    load_requests,
    run_pattern9,
)

FEEDBACK_FILE = HERE / "feedback.jsonl"


def show(request, extracted, order, guard) -> None:
    print(f"\nRequest {request.request_id} from customer {request.customer_id}")
    print(f'  text: "{request.text}"')

    print("\nThe agent extracted these items:")
    for item in extracted.items:
        print(f"  {item.quantity} x {item.sku}")
    print(f"  requested delivery: {extracted.requested_delivery}")
    print(f"  discount: {extracted.discount_pct}%")
    print(f"  ship-to: {extracted.ship_to_country}")

    print("\nThe agent proposes this draft order:")
    for line in order.lines:
        print(
            f"  {line.quantity:>4} x {line.sku:<8} {line.name:<16} "
            f"{line.line_total} {order.currency}"
        )
    print(f"  order total: {order.order_total} {order.currency}")

    print(f"\nThe guard says: {guard.status}")
    for reason in guard.reasons:
        print(f"  - {reason}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Pattern 9 end to end.")
    parser.add_argument("--request", default="REQ-1", help="request id to process")
    parser.add_argument(
        "--approve",
        action="store_true",
        help="sales manager approves the release (only reached if the guard passes)",
    )
    parser.add_argument(
        "--reject",
        action="store_true",
        help="sales manager rejects the release; --rationale is the learning signal",
    )
    parser.add_argument(
        "--rationale",
        default=None,
        help="the manager's reason, recorded with their decision for the learning loop",
    )
    parser.add_argument(
        "--proposer",
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

    requests = load_requests()
    request = requests.get(args.request)
    if request is None:
        known = ", ".join(sorted(requests))
        parser.error(f"unknown request {args.request!r}. Known ids: {known}")

    store = (
        CorrectionMemory()
        if args.reset_feedback
        else CorrectionMemory.load(FEEDBACK_FILE)
    )

    if args.proposer == "llm":
        proposer = (
            LlmBackedProposer(model=args.model, store=store)
            if args.model
            else LlmBackedProposer(store=store)
        )
    else:
        proposer = RuleBasedProposer()

    client = GovernedSalesClient(
        MockSalesClient(), entitlements={"stage", "release"}
    )

    def approve(_request, order, guard) -> HumanDecision:
        # The guard passed, so we reach the human. Show the draft, then decide.
        show(_request, result_extracted["value"], order, guard)
        if args.reject:
            reason = args.rationale or "rejected (scripted)"
            print(f"\nSales manager decision: REJECTED ({reason})")
            return HumanDecision(approved=False, rationale=reason)
        if args.approve:
            print("\nSales manager decision: APPROVED")
            return HumanDecision(approved=True, rationale=args.rationale or "")
        print("\nSales manager decision: not approved (pass --approve to release)")
        return HumanDecision(approved=False, rationale=args.rationale or "")

    # Extract once here so the printout shows the same extraction the flow uses.
    result_extracted = {"value": proposer.extract(request, catalog=client.catalog)}

    result = run_pattern9(
        client,
        proposer,
        request,
        config=default_config(),
        approve=approve,
        store=store,
    )

    # If the guard flagged it, approve() was never called, so print here.
    if result.outcome == "flagged_by_guard":
        show(request, result.extracted, result.order, result.guard)

    print("\n" + "=" * 52)
    print(f"Outcome: {result.outcome}")
    if result.release_result is not None:
        print(f"Released to fulfillment as: {result.release_result.order_id}")
    if result.outcome == "flagged_by_guard":
        print("The guard flagged it. The sales manager was never asked to release.")
    if result.outcome == "rejected_by_human":
        print("The sales manager did not approve. Nothing was released.")

    print("\nAudit trail (every call the agent made):")
    for entry in client.audit_log:
        print(
            f"  {entry.actor}  {entry.operation:<8} {entry.target:<14} {entry.outcome}"
        )
    print(f"\nAudit intact (hash chain verifies): {client.verify_audit()}")

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
            print(
                f"  {item['item_id']:<10} {item['entity']:<10} {item['decision']}: {why}"
            )


if __name__ == "__main__":
    main()
