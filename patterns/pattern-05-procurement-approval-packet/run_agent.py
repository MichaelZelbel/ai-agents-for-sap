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

from learning import Correction, CorrectionMemory  # noqa: E402
from procurement import (  # noqa: E402
    LlmBackedNarrator,
    PacketAuditLog,
    RuleBasedNarrator,
    assemble_packet,
    record_decision,
)

FEEDBACK_FILE = HERE / "feedback.jsonl"


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
        "--reject",
        action="store_true",
        help="record a rejection decision for the staged packet",
    )
    parser.add_argument(
        "--approver", default="manager", help="who records the decision"
    )
    parser.add_argument(
        "--rationale", default="", help="the reviewer's reason, for the override rate"
    )
    parser.add_argument(
        "--override-threshold",
        type=float,
        default=0.2,
        help="raise a review when the override rate climbs above this (0..1)",
    )
    parser.add_argument(
        "--reset-feedback",
        action="store_true",
        help="start the override-rate history from empty",
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

    store = CorrectionMemory() if args.reset_feedback else CorrectionMemory.load(FEEDBACK_FILE)
    req, sup = result.packet.requisition, result.packet.supplier
    ctx = f"{req.category} {req.amount} {req.currency}"

    if args.approve or args.reject:
        approved = args.approve and not args.reject
        outcome = record_decision(
            result.packet, approver=args.approver, approved=approved, log=log
        )
        print("\n" + "=" * 52)
        if outcome in ("approved", "rejected"):
            print(f"Human decision: {outcome.upper()} by {args.approver}")
            store.record(Correction(
                entity=sup.name, item_id=result.packet.request_id, decision=outcome,
                reason=args.rationale, context=ctx,
                proposed=result.packet.recommendation, amount=str(req.amount),
            ))
        elif outcome == "refused_blocked":
            print("Approval REFUSED: packet is blocked on a missing document.")
            print("Supply the required document, then re-run.")
    else:
        print("\n" + "=" * 52)
        print("Packet staged. A human approver decides. Re-run with --approve or --reject.")

    print("\nAudit trail (every action the agent took):")
    for entry in log.entries:
        print(
            f"  {entry.actor}  {entry.operation:<13} {entry.target:<10} {entry.outcome}"
        )
    print(f"\nAudit intact (hash chain verifies): {log.verify()}")

    # The override-rate half of the shared loop. This pattern's decision is made by
    # deterministic policy and the AI narrative is only advisory, so folding past
    # corrections into the draft would polish prose, not change the decision. What
    # is worth watching is how often humans reject the packet: a rising rate is the
    # signal to review the policy, so that half of the loop we keep.
    store.save(FEEDBACK_FILE)
    overrides, total, rate = store.override_rate()
    print(f"\nRejection rate: {overrides}/{total} = {rate:.0%} "
          f"(threshold {args.override_threshold:.0%})")
    digest = store.review_needed(threshold=args.override_threshold)
    if digest is not None:
        print(f"\n*** REVIEW NEEDED: rejection rate {digest.rate:.0%} is above "
              f"{digest.threshold:.0%} over the last {digest.total} decisions. ***")
        for item in digest.recent[-5:]:
            why = item["reason"] or "(no reason given)"
            print(f"  {item['item_id']:<10} {item['entity']:<24} {item['decision']}: {why}")


if __name__ == "__main__":
    main()
