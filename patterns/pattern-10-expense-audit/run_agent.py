"""Run Pattern 10 end to end: audit an expense report against policy.

    python run_agent.py                    # audit the sample report, offline
    python run_agent.py --report EXP-2001  # pick a report by id
    python run_agent.py --drafter llm      # use a real model via OpenRouter

You need no SAP account and no API key. The default drafter is a deterministic
stand in, so everything runs in memory and offline.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make this pattern importable when run directly.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

from expense.auditor import (  # noqa: E402
    LlmBackedDrafter,
    RuleBasedDrafter,
    audit_report,
    default_policy,
    sample_reports,
)


def approve_exception(decision) -> bool:
    """A human approves an exception. Scripted here so the demo runs unattended.

    In a real deployment this is where a manager or compliance reviewer says yes
    or no. Nothing about a violation is auto approved. We record the intent.
    """
    print(f"    human review needed: {decision.approver} approves the exception? (auto: yes)")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Pattern 10 end to end.")
    parser.add_argument("--report", default="EXP-2001", help="report id to audit")
    parser.add_argument(
        "--drafter",
        choices=["rule", "llm"],
        default="rule",
        help="rule = offline deterministic; llm = a real model via OpenRouter",
    )
    parser.add_argument("--model", default=None, help="override the OpenRouter model")
    args = parser.parse_args()

    reports = sample_reports()
    report = reports.get(args.report)
    if report is None:
        print(f"No report {args.report!r}. Known: {', '.join(sorted(reports))}")
        raise SystemExit(1)

    if args.drafter == "llm":
        drafter = (
            LlmBackedDrafter(model=args.model) if args.model else LlmBackedDrafter()
        )
    else:
        drafter = RuleBasedDrafter()

    policy = default_policy()
    result = audit_report(report, policy=policy, drafter=drafter)

    print(f"\nReport {report.report_id} from {report.employee} ({report.currency})")
    print(f"Audited against policy version {policy.version} "
          f"({policy.period_start} to {policy.period_end})\n")

    for line, decision in zip(report.lines, result.decisions):
        verdict = "COMPLIANT" if decision.compliant else "VIOLATION"
        print(f"  {line.line_id}  {line.category:<10} "
              f"claim {line.claimed_amount} / receipt {line.receipt_total}  {line.date}")
        print(f"      guard: {verdict}   policy {decision.policy_version}   "
              f"-> route {decision.route}   approver {decision.approver}")
        for check in decision.failed_checks:
            print(f"        - {check}")
        if not decision.compliant:
            approve_exception(decision)
        print()

    print("=" * 60)
    print("Where each line routed:")
    for decision in result.decisions:
        print(f"  {decision.line_id}  ->  {decision.route}   "
              f"(policy {decision.policy_version}, approver {decision.approver})")

    print("\nAudit log (policy version recorded per line):")
    for entry in result.log:
        print(f"  {entry}")


if __name__ == "__main__":
    main()
