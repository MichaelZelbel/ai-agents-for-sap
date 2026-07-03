"""Run Pattern 6 end to end against the in-memory close plan.

    python run_agent.py                 # predict and preview; nothing changes
    python run_agent.py --approve       # apply the top intervention to the plan
    python run_agent.py --scorer llm    # score with a real model via OpenRouter
    python run_agent.py --reset-feedback  # start the learning loop from empty

The learning loop: every apply or dismiss is remembered per owner in feedback.jsonl.
Because this is PREDICTION memory (which transfers poorly across periods), the model
folds those past decisions back in only as weak priors, and the deterministic guard
plus the human still decide. The run prints the override rate, and raises a review
when it crosses --override-threshold, so a person looks because the number moved.

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

from learning import CorrectionMemory  # noqa: E402

FEEDBACK_FILE = HERE / "feedback.jsonl"


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


def make_approver(auto: bool, rationale: str | None = None):
    def approve(staged, plan):
        show_intervention(staged, plan)
        if auto:
            print("\nHuman decision: APPROVED (auto)")
            return True, (rationale or "")
        answer = input("\nApply this intervention? [y/N] ").strip().lower()
        approved = answer in {"y", "yes"}
        reason = rationale or input(
            "Why? (a note for the learning loop) "
        ).strip()
        return approved, reason

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
    parser.add_argument(
        "--rationale",
        default=None,
        help="the reviewer's reason, recorded with their decision for the learning loop",
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

    if args.scorer == "llm":
        scorer = (
            LlmBackedScorer(model=args.model, store=store)
            if args.model
            else LlmBackedScorer(store=store)
        )
    else:
        # The rule-based scorer is deterministic and does not read the store.
        scorer = RuleBasedScorer()

    plan = seed_close_plan()
    log = InterventionLog()

    ranked, staged = predict_and_stage(plan, scorer)
    show_ranking(plan, ranked)

    if not staged:
        print("\nNo task clears the guard's threshold. No intervention proposed.")
    else:
        top = staged[0]
        if not args.approve:
            show_intervention(top, plan)
            print("\nPreview only. Re-run with --approve to apply it to the plan.")
        else:
            result = run_intervention(
                plan,
                top,
                approve=make_approver(True, args.rationale),
                log=log,
                store=store,
            )

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

    # The learning loop: keep the decision, report the override rate, and raise a
    # review if it has crossed the line. Prediction memory transfers poorly, so this
    # is a watch on the human's workload, not a lever that changes the plan.
    store.save(FEEDBACK_FILE)
    overrides, total, rate = store.override_rate()
    print(
        f"\nOverride (dismissal) rate: {overrides}/{total} = {rate:.0%} "
        f"(threshold {args.override_threshold:.0%})"
    )
    digest = store.review_needed(threshold=args.override_threshold)
    if digest is not None:
        print(
            f"\n*** REVIEW NEEDED: override rate {digest.rate:.0%} is above "
            f"{digest.threshold:.0%} over the last {digest.total} decisions. ***"
        )
        print("Recent dismissals for a human to read (the signal, not the calendar):")
        for item in digest.recent[-5:]:
            why = item["reason"] or "(no reason given)"
            print(f"  {item['item_id']:<8} owner {item['entity']:<8} {item['decision']}: {why}")


if __name__ == "__main__":
    main()
