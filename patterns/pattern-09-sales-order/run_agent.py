"""Run Pattern 9 end to end against the fake, governed sales system.

    python run_agent.py --request REQ-1              # show extraction, draft, flags
    python run_agent.py --request REQ-1 --approve     # release a clean order
    python run_agent.py --request REQ-2               # a flagged order (over policy)
    python run_agent.py --request REQ-3               # a flagged order (short stock)

You need no SAP account and no API key. Everything runs in memory with the
deterministic proposer. Pass --proposer llm to use a real model via OpenRouter.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make this pattern importable when run directly.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

from salesorder import (  # noqa: E402
    GovernedSalesClient,
    LlmBackedProposer,
    MockSalesClient,
    RuleBasedProposer,
    default_config,
    load_requests,
    run_pattern9,
)


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
        "--proposer",
        choices=["rule", "llm"],
        default="rule",
        help="rule = offline deterministic; llm = a real model via OpenRouter",
    )
    parser.add_argument("--model", default=None, help="override the OpenRouter model")
    args = parser.parse_args()

    requests = load_requests()
    request = requests.get(args.request)
    if request is None:
        known = ", ".join(sorted(requests))
        parser.error(f"unknown request {args.request!r}. Known ids: {known}")

    if args.proposer == "llm":
        proposer = (
            LlmBackedProposer(model=args.model) if args.model else LlmBackedProposer()
        )
    else:
        proposer = RuleBasedProposer()

    client = GovernedSalesClient(
        MockSalesClient(), entitlements={"stage", "release"}
    )

    def approve(_request, order, guard) -> bool:
        # The guard passed, so we reach the human. Show the draft, then decide.
        show(_request, result_extracted["value"], order, guard)
        if args.approve:
            print("\nSales manager decision: APPROVED")
            return True
        print("\nSales manager decision: not approved (pass --approve to release)")
        return False

    # Extract once here so the printout shows the same extraction the flow uses.
    result_extracted = {"value": proposer.extract(request, catalog=client.catalog)}

    result = run_pattern9(
        client,
        proposer,
        request,
        config=default_config(),
        approve=approve,
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


if __name__ == "__main__":
    main()
