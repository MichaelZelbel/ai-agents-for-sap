"""Run Pattern 6 end to end against the in-memory close plan.

    python run_agent.py                 # predict and preview; nothing changes
    python run_agent.py --approve       # apply the top intervention to the plan
    python run_agent.py --scorer llm    # score with a real model via OpenRouter

You need no SAP account and no API key for the default run. Everything runs
in memory.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the shared layer and this pattern importable when run directly.
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(REPO / "shared"))

from close.flow import (  # noqa: E402
    InterventionLog,
    predict_and_stage,
    run_intervention,
)
from close.plan import seed_close_plan  # noqa: E402
from close.scorer import LlmBackedScorer, RuleBasedScorer  # noqa: E402


def show_ranking(plan, ranked) -> None:
    print(f"\nClose plan for {plan.period}. Ranked predicted blockers:")
    for item in ranked:
        pred = item.prediction
        task = plan.get(pred.task_id)
        action = item.mitigation.action if item.mitigation else "none"
        print(
            f"  {task.task_id}  score {pred.score}  impact {task.impact} "
            f"{task.owner:<6} {task.name}  -> {action}"
        )
        for reason in pred.reasons:
            print(f"        - {reason}")


def show_intervention(staged, plan) -> None:
    task = plan.get(staged.mitigation.task_id)
    mit = staged.mitigation
    print("\n" + "-" * 48)
    print(f"Proposed intervention {staged.staged_id} for {task.task_id} '{task.name}'")
    print(f"  action: {mit.action}")
    print(f"  detail: {mit.detail}")
    if mit.before_deadline or mit.after_deadline:
        print(f"  before: deadline {mit.before_deadline}")
        print(f"  after:  deadline {mit.after_deadline}")
    else:
        print("  before/after: no change to the plan (a nudge only)")


def make_approver(auto: bool):
    def approve(staged, plan) -> bool:
        show_intervention(staged, plan)
        if auto:
            print("\nHuman decision: APPROVED (auto)")
            return True
        answer = input("\nApply this intervention? [y/N] ").strip().lower()
        return answer in {"y", "yes"}

    return approve


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Pattern 6 end to end.")
    parser.add_argument(
        "--approve",
        action="store_true",
        help="apply the top staged intervention to the in-memory plan",
    )
    parser.add_argument(
        "--scorer",
        choices=["rule", "llm"],
        default="rule",
        help="rule = offline deterministic; llm = a real model via OpenRouter",
    )
    parser.add_argument("--model", default=None, help="override the OpenRouter model")
    args = parser.parse_args()

    if args.scorer == "llm":
        scorer = LlmBackedScorer(model=args.model) if args.model else LlmBackedScorer()
    else:
        scorer = RuleBasedScorer()

    plan = seed_close_plan()
    log = InterventionLog()

    ranked, staged = predict_and_stage(plan, scorer)
    show_ranking(plan, ranked)

    if not staged:
        print("\nNo task clears the guard's threshold. No intervention proposed.")
        return

    top = staged[0]

    if not args.approve:
        show_intervention(top, plan)
        print("\nPreview only. Re-run with --approve to apply it to the plan.")
        return

    result = run_intervention(plan, top, approve=make_approver(True), log=log)

    print("\n" + "=" * 48)
    print(f"Outcome: {result.outcome}")
    if result.outcome == "applied":
        task = result.plan.get(top.mitigation.task_id)
        print(f"New plan state for {task.task_id}: deadline {task.deadline}")

    print("\nIntervention log (high-impact interventions):")
    if not log.entries:
        print("  (none logged)")
    for entry in log.entries:
        print(
            f"  {entry.trace_id}  {entry.actor}  {entry.operation:<10} "
            f"{entry.target:<10} {entry.outcome}"
        )


if __name__ == "__main__":
    main()
