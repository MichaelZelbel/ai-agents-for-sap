"""Run Pattern 5 end to end against the seeded, in-memory procurement data.

    python run_agent.py                          # assemble the packet for REQ-2001
    python run_agent.py --request REQ-2002       # missing contract, over threshold
    python run_agent.py --request REQ-2003       # segregation-of-duties violation
    python run_agent.py --request REQ-2001 --approve   # record an approval

You need no SAP account and no API key. The narrative is drafted by an offline,
deterministic stand-in by default, so everything runs in memory. Pass
--narrator llm to use a real model via OpenRouter (needs OPENROUTER_API_KEY).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the shared SAP layer and this pattern importable when run directly.
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(REPO / "shared"))

from procurement import (  # noqa: E402
    LlmBackedNarrator,
    PacketAuditLog,
    RuleBasedNarrator,
    assemble_packet,
    record_decision,
)


def show(packet) -> None:
    req = packet.requisition
    sup = packet.supplier
    print(f"\nApproval packet for {packet.request_id}  (STAGED, record unchanged)")
    print(f"  requester: {req.requester}   named approver: {req.approver}")
    print(f"  category:  {req.category}")
    print(f"  amount:    {req.amount} {req.currency}")
    print(f"  supplier:  {sup.name} ({sup.country}), risk {sup.risk_rating}, "
          f"approved vendor: {sup.approved_vendor}")
    print(f"  documents: {', '.join(req.attached_documents) or 'none'}")

    print(f"\nPolicy cited: {packet.policy_id} version {packet.policy_version}")

    print("\nAI-drafted risk narrative (advisory only):")
    print(f"  {packet.risk_narrative}")
    print("AI-drafted recommendation (advisory only):")
    print(f"  {packet.recommendation}")

    print("\nGuard flags (deterministic, these decide):")
    if packet.flags:
        for flag in packet.flags:
            print(f"  - {flag}")
    else:
        print("  - none")

    print(f"\nRoute: {packet.route}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Pattern 5 end to end.")
    parser.add_argument("--request", default="REQ-2001", help="requisition id")
    parser.add_argument(
        "--approve",
        action="store_true",
        help="record an approval decision for the staged packet",
    )
    parser.add_argument(
        "--approver", default="manager", help="who records the decision"
    )
    parser.add_argument(
        "--narrator",
        choices=["rule", "llm"],
        default="rule",
        help="rule = offline deterministic; llm = a real model via OpenRouter",
    )
    parser.add_argument("--model", default=None, help="override the OpenRouter model")
    args = parser.parse_args()

    if args.narrator == "llm":
        narrator = (
            LlmBackedNarrator(model=args.model) if args.model else LlmBackedNarrator()
        )
    else:
        narrator = RuleBasedNarrator()

    log = PacketAuditLog()
    result = assemble_packet(args.request, narrator, log=log)
    show(result.packet)

    if args.approve:
        outcome = record_decision(
            result.packet, approver=args.approver, approved=True, log=log
        )
        print("\n" + "=" * 52)
        if outcome == "approved":
            print(f"Human decision: APPROVED by {args.approver}")
        elif outcome == "refused_blocked":
            print("Approval REFUSED: packet is blocked on a missing document.")
            print("Supply the required document, then re-run.")
    else:
        print("\n" + "=" * 52)
        print("Packet staged. A human approver decides. Re-run with --approve to sign off.")

    print("\nAudit trail (every action the agent took):")
    for entry in log.entries:
        print(
            f"  {entry.actor}  {entry.operation:<13} {entry.target:<10} {entry.outcome}"
        )
    print(f"\nAudit intact (hash chain verifies): {log.verify()}")


if __name__ == "__main__":
    main()
