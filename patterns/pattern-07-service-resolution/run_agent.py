"""Run Pattern 7 end to end against the fake, governed service source.

    python run_agent.py                     # CASE-501, asks you to confirm
    python run_agent.py --case CASE-502     # needs-approval, sent to a supervisor
    python run_agent.py --case CASE-503     # denied by the guard
    python run_agent.py --confirm yes       # auto-confirm the staged action
    python run_agent.py --confirm no        # auto-decline
    python run_agent.py --confirm no --reason "wrong part, gearbox not stator"
    python run_agent.py --proposer llm      # use a real model via OpenRouter
    python run_agent.py --reset-feedback    # start the learning loop from empty

The learning loop: every human decision (confirm or decline) is remembered per
asset model in feedback.jsonl. A decline reason is folded into the next proposal
for that asset model, and the run prints the override rate. When that rate crosses
--override-threshold, it prints a review, so a human looks because the number moved.

You need no SAP account and no API key. Everything runs in memory, and the
proposer is a deterministic stand-in by default.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make this pattern's src and the shared layer importable when run directly.
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(REPO / "shared"))

from learning import CorrectionMemory  # noqa: E402

from service import (  # noqa: E402
    GovernedServiceSource,
    HumanConfirmation,
    LlmBackedProposer,
    MockServiceSource,
    RuleBasedProposer,
    default_config,
    run_pattern7,
)

FEEDBACK_FILE = HERE / "feedback.jsonl"


def show(context, step, decision) -> None:
    case = context.case
    ent = context.entitlement
    print(f"\nCase {case.case_id} at {case.site}")
    print(f"  symptom: {case.reported_symptom}")
    print(f"\nGathered context:")
    print(f"  asset:       {context.asset.asset_id} ({context.asset.model})")
    print(
        f"  entitlement: {ent.plan}, in warranty {ent.in_warranty}, "
        f"expires {ent.expires_on}"
    )
    print(f"  covered sites: {', '.join(sorted(ent.covered_sites))}")
    print(f"  approval limit: {ent.approval_limit}")
    if context.incidents:
        print("  prior incidents:")
        for inc in context.incidents:
            print(f"    - {inc.incident_id}: {inc.summary}")
    if context.parts:
        print("  parts:")
        for part in context.parts:
            stock = "in stock" if part.in_stock else "out of stock"
            print(f"    - {part.part_id} {part.name} ({stock}, {part.unit_cost})")

    print("\nThe agent proposes this next step:")
    print(f"  kind: {step.kind}")
    if step.part_id:
        print(f"  part: {step.part_id}")
    print(f"  estimated cost: {step.estimated_cost}")
    print(f"  rationale: {step.rationale}")

    print(f"\nThe entitlement guard says: {decision.verdict}")
    print(f"  - {decision.reason}")


def make_confirmer(mode: str, reason: str | None):
    def confirm(context, step, decision) -> HumanConfirmation:
        show(context, step, decision)
        if mode == "yes":
            print("\nHuman decision: CONFIRMED (auto)")
            return HumanConfirmation(True, reason or "")
        if mode == "no":
            note = reason or "auto-decline (scripted)"
            print("\nHuman decision: DECLINED (auto)")
            return HumanConfirmation(False, note)
        answer = input("\nConfirm this staged action? [y/N] ").strip().lower()
        confirmed = answer in {"y", "yes"}
        prompt = (
            "Any note for the record? (optional) "
            if confirmed
            else "Why? (a note for the learning loop) "
        )
        note = reason or input(prompt).strip()
        return HumanConfirmation(confirmed, note)

    return confirm


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Pattern 7 end to end.")
    parser.add_argument("--case", default="CASE-501", help="case id to resolve")
    parser.add_argument(
        "--confirm", choices=["ask", "yes", "no"], default="ask", help="human decision"
    )
    parser.add_argument(
        "--proposer",
        choices=["rule", "llm"],
        default="rule",
        help="rule = offline deterministic stand-in; llm = a real model via OpenRouter",
    )
    parser.add_argument("--model", default=None, help="override the OpenRouter model")
    parser.add_argument(
        "--reason",
        default=None,
        help="the reviewer's note, recorded with their decision for the learning loop",
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
        help="start the learning loop from empty (ignore feedback.jsonl)",
    )
    args = parser.parse_args()

    store = (
        CorrectionMemory() if args.reset_feedback else CorrectionMemory.load(FEEDBACK_FILE)
    )

    if args.proposer == "llm":
        proposer = (
            LlmBackedProposer(model=args.model, store=store)
            if args.model
            else LlmBackedProposer(store=store)
        )
    else:
        proposer = RuleBasedProposer()

    source = GovernedServiceSource(
        MockServiceSource(), entitlements={"read", "stage", "execute"}
    )

    result = run_pattern7(
        source,
        proposer,
        args.case,
        config=default_config(),
        confirm=make_confirmer(args.confirm, args.reason),
        store=store,
    )

    # A needs-approval or deny verdict never reaches the confirmer, so show the
    # gathered context and verdict here for those outcomes.
    if result.outcome in {"denied_by_guard", "sent_to_supervisor"}:
        show(result.context, result.step, result.decision)

    print("\n" + "=" * 48)
    print(f"Outcome: {result.outcome}")
    if result.action_result is not None:
        print(f"Executed as: {result.action_result.action_id}")
    if result.outcome == "denied_by_guard":
        print("The guard denied it. No human was asked. Nothing was staged.")
    if result.outcome == "sent_to_supervisor":
        print("Beyond the agent's authority. Sent to a supervisor for approval.")

    print("\nAudit trail (every call the agent made):")
    for entry in source.audit_log:
        print(
            f"  {entry.actor}  {entry.operation:<8} {entry.target:<12} {entry.outcome}"
        )
    print(f"\nAudit intact (hash chain verifies): {source.verify_audit()}")

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
            print(f"  {item['item_id']:<10} {item['entity']:<18} {item['decision']}: {why}")


if __name__ == "__main__":
    main()
