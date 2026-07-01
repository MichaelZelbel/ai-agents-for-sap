"""Run Pattern 7 end to end against the fake, governed service source.

    python run_agent.py                     # CASE-501, asks you to confirm
    python run_agent.py --case CASE-502     # needs-approval, sent to a supervisor
    python run_agent.py --case CASE-503     # denied by the guard
    python run_agent.py --confirm yes       # auto-confirm the staged action
    python run_agent.py --confirm no        # auto-decline
    python run_agent.py --proposer llm      # use a real model via OpenRouter

You need no SAP account and no API key. Everything runs in memory, and the
proposer is a deterministic stand-in by default.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make this pattern's src importable when run directly.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

from service import (  # noqa: E402
    GovernedServiceSource,
    LlmBackedProposer,
    MockServiceSource,
    RuleBasedProposer,
    default_config,
    run_pattern7,
)


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


def make_confirmer(mode: str):
    def confirm(context, step, decision) -> bool:
        show(context, step, decision)
        if mode == "yes":
            print("\nHuman decision: CONFIRMED (auto)")
            return True
        if mode == "no":
            print("\nHuman decision: DECLINED (auto)")
            return False
        answer = input("\nConfirm this staged action? [y/N] ").strip().lower()
        return answer in {"y", "yes"}

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
    args = parser.parse_args()

    if args.proposer == "llm":
        proposer = (
            LlmBackedProposer(model=args.model) if args.model else LlmBackedProposer()
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
        confirm=make_confirmer(args.confirm),
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


if __name__ == "__main__":
    main()
