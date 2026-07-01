"""Run Pattern 4 (dispute assistant) against a sample vendor message.

    python run_agent.py                 # read the sample dispute, draft a reply
    python run_agent.py --case duplicate    # a different sample dispute
    python run_agent.py --assistant llm      # assess with a real model

You need no SAP account and no API key for the default run. The assistant is a
deterministic stand-in by default. Either way the agent only suggests: it drafts
a reply for a human to send and takes no action itself.
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

from dispute import Dispute, LlmDisputeAssistant, review  # noqa: E402

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
    args = parser.parse_args()

    dispute = SAMPLES[args.case]

    if args.assistant == "llm":
        assistant = (
            LlmDisputeAssistant(model=args.model)
            if args.model
            else LlmDisputeAssistant()
        )
    else:
        assistant = LlmDisputeAssistant(
            complete=lambda prompt: rule_based_complete(args.case, dispute)
        )

    recommendation = review(assistant.assess(dispute))

    print(f"\nDispute {dispute.dispute_id} from {dispute.vendor}")
    print(f"  message: {dispute.message}")
    print(f"\nThe agent classifies it as: {recommendation.category}")
    print("\nDraft reply (for a human to review and send):")
    for line in recommendation.reply.splitlines():
        print(f"  {line}")

    print("\n" + "=" * 48)
    print(f"Action taken by the agent: {recommendation.action_taken}")
    print("This agent only suggests. A human decides whether to send the reply.")


if __name__ == "__main__":
    main()
