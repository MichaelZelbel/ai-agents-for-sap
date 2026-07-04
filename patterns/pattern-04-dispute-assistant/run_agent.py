"""Run Pattern 4 (dispute assistant) against a sample vendor message.

    python run_agent.py                      # read the sample dispute, draft a reply
    python run_agent.py --case duplicate     # a different sample dispute
    python run_agent.py --assistant llm      # assess with a real model
    python run_agent.py --decision send      # mark the draft sent (approve the read)
    python run_agent.py --decision discard --reason "wrong category, this is a price dispute"
    python run_agent.py --reset-feedback     # start the learning loop from empty

You need no SAP account and no API key for the default run. The assistant is a
deterministic stand-in by default. Either way the agent only suggests: it drafts
a reply for a human to send and takes no action itself.

The learning loop: a discard's reason is remembered per vendor in feedback.jsonl.
The next dispute from that vendor is assessed with those past corrections folded into
the prompt, and the run prints the override rate. When that rate crosses
--override-threshold, it prints a review, so a human looks because the number moved.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the shared SAP layer and this pattern importable when run directly.
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(REPO / "shared"))

from dotenv_loader import load_dotenv  # noqa: E402

# One key, every pattern: load the nearest .env from here up to the repo root.
load_dotenv(HERE)

from learning import CorrectionMemory  # noqa: E402

from dispute import (  # noqa: E402
    DEFAULT_REVIEWER,
    Dispute,
    HumanDecision,
    LlmDisputeAssistant,
    run_dispute,
)

FEEDBACK_FILE = HERE / "feedback.jsonl"

# A few sample disputes, keyed by the case they illustrate.
SAMPLES = {
    "short_payment": Dispute(
        dispute_id="DSP-1",
        vendor="Office Supplies Co",
        message="You only paid 1,070 EUR on invoice INV-1001 but it was for "
        "1,190 EUR. Please pay the difference.",
    ),
    "duplicate": Dispute(
        dispute_id="DSP-2",
        vendor="Cloud Hosting Ltd",
        message="We have received two payments for invoice INV-1002. One of them "
        "looks like a duplicate. Please advise.",
    ),
    "not_received": Dispute(
        dispute_id="DSP-3",
        vendor="Parts Warehouse GmbH",
        message="Your team says the goods were delivered, but we never received "
        "them. Can you hold payment until this is sorted out?",
    ),
}

# What the deterministic stand-in classifies each sample as.
RULE_CATEGORY = {
    "short_payment": "short_payment",
    "duplicate": "duplicate",
    "not_received": "not_received",
}


def rule_based_complete(case: str, dispute: Dispute) -> str:
    """A deterministic stand-in for the model. It returns the JSON shape the model
    would, with a fixed category for the case and a plain draft reply. review()
    still guards it: an unknown category or an empty draft would be refused."""
    category = RULE_CATEGORY.get(case, "other")
    reply = (
        f"Dear {dispute.vendor},\n\n"
        "Thank you for reaching out. We have received your message and a "
        "colleague is reviewing the details now. We will come back to you "
        "shortly with the outcome.\n\nBest regards,\nAccounts Payable"
    )
    return json.dumps({"category": category, "reply": reply})


def show(dispute, recommendation) -> None:
    print(f"\nDispute {dispute.dispute_id} from {dispute.vendor}")
    print(f"  message: {dispute.message}")
    print(f"\nThe agent classifies it as: {recommendation.category}")
    print("\nDraft reply (for a human to review and send):")
    for line in recommendation.reply.splitlines():
        print(f"  {line}")


def make_decider(mode: str, reviewer: str, reason: str | None):
    def decide(dispute, recommendation) -> HumanDecision:
        show(dispute, recommendation)
        if mode == "send":
            print(f"\nHuman decision: SENT (auto) by {reviewer}")
            return HumanDecision(True, reviewer, reason or "")
        if mode == "discard":
            why = reason or "auto-discard (scripted)"
            print(f"\nHuman decision: DISCARDED (auto) by {reviewer}")
            return HumanDecision(False, reviewer, why)
        answer = input("\nSend this draft? [y/N] ").strip().lower()
        sent = answer in {"y", "yes"}
        prompt = (
            "Any note for the record? (optional) "
            if sent
            else "Why discard it? (a note for the learning loop) "
        )
        note = reason or input(prompt).strip()
        return HumanDecision(sent, reviewer, note)

    return decide


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Pattern 4 (dispute assistant).")
    parser.add_argument(
        "--case",
        choices=sorted(SAMPLES),
        default="short_payment",
        help="which sample dispute to read",
    )
    parser.add_argument(
        "--assistant",
        choices=["rule", "llm"],
        default="rule",
        help="rule = offline deterministic; llm = a real model via OpenRouter",
    )
    parser.add_argument("--model", default=None, help="override the OpenRouter model")
    parser.add_argument(
        "--decision",
        choices=["ask", "send", "discard"],
        default="ask",
        help="the human's decision on the draft (send = approve, discard = reject)",
    )
    parser.add_argument(
        "--reviewer",
        default=DEFAULT_REVIEWER,
        help="the named human who decides (goes on the learning record)",
    )
    parser.add_argument(
        "--reason",
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

    dispute = SAMPLES[args.case]

    store = (
        CorrectionMemory()
        if args.reset_feedback
        else CorrectionMemory.load(FEEDBACK_FILE)
    )

    if args.assistant == "llm":
        assistant = (
            LlmDisputeAssistant(model=args.model, store=store)
            if args.model
            else LlmDisputeAssistant(store=store)
        )
    else:
        assistant = LlmDisputeAssistant(
            complete=lambda prompt: rule_based_complete(args.case, dispute),
            store=store,
        )

    result = run_dispute(
        assistant,
        dispute,
        decide=make_decider(args.decision, args.reviewer, args.reason),
        reviewer=args.reviewer,
        store=store,
    )

    print("\n" + "=" * 48)
    print(f"Outcome: the human {result.outcome} the draft.")
    print(f"Action taken by the agent: {result.recommendation.action_taken}")
    print("This agent only suggests. A human decides whether to send the reply.")

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
            print(f"  {item['item_id']:<10} {item['entity']:<22} {item['decision']}: {why}")


if __name__ == "__main__":
    main()
