"""Run Pattern 3 (three-way match) against a sample invoice, order, and receipt.

    python run_agent.py                      # a clean match: guard passes, human releases
    python run_agent.py --case overpriced    # a price mismatch: the guard holds it
    python run_agent.py --case short         # goods not fully received: the guard holds it
    python run_agent.py --decision hold --rationale "wrong desk model"  # human holds it
    python run_agent.py --matcher llm        # match lines with a real model

The learning loop: every human decision (release or hold) is remembered per vendor in
feedback.jsonl. A hold, with the reviewer's reason, is folded into the next invoice
from that vendor so the matcher does not repeat the mistake, and the run prints the
override rate. When that rate crosses --override-threshold, it prints a review.

You need no SAP account and no API key for the default run. The line matcher is a
deterministic stand-in by default; the arithmetic guard is always real.
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
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
from threeway import (  # noqa: E402
    DEFAULT_REVIEWER,
    DEFAULT_VENDOR,
    HumanDecision,
    Line,
    LlmLineMatcher,
    invoice_total,
    run_threeway,
)

FEEDBACK_FILE = HERE / "feedback.jsonl"

# The vendor this desk works. The models carry no vendor field, so the learning loop
# keys on this one fixed supplier string.
VENDOR = DEFAULT_VENDOR

# The sample: the same two items, worded differently on each document.
PO = [
    Line("Ergonomic office chair", Decimal("10"), Decimal("120.00")),
    Line("Standing desk", Decimal("4"), Decimal("350.00")),
]
INVOICE = [
    Line("Office chairs, ergonomic", Decimal("10"), Decimal("120.00")),
    Line("Desk, sit-stand", Decimal("4"), Decimal("350.00")),
]
RECEIVED = [Decimal("10"), Decimal("4")]


def sample(case: str) -> tuple[list[Line], list[Decimal]]:
    """Return (invoice, goods received) for the chosen case. The purchase order
    stays fixed; the case bends the invoice or the receipt so you can see the
    guard pass and fail."""
    if case == "overpriced":
        invoice = [INVOICE[0], Line("Desk, sit-stand", Decimal("4"), Decimal("390.00"))]
        return invoice, RECEIVED
    if case == "short":
        return INVOICE, [Decimal("8"), Decimal("4")]  # only 8 of 10 chairs arrived
    return INVOICE, RECEIVED


def rule_based_complete(invoice: list[Line]) -> str:
    """A deterministic stand-in for the model. Here the sample lines are already
    in the same order on both documents, so the mapping is the identity. It
    returns JSON, exactly as the model would, and parse_mapping reads it."""
    return json.dumps({"mapping": list(range(len(invoice)))})


def make_reviewer(mode: str, reviewer: str, rationale: str | None):
    """Build the human-decision callback. Called only when the guard has passed."""

    def approve(invoice, po, mapping, result) -> HumanDecision:
        print("\nThe matcher (AI) lines the invoice up against the purchase order:")
        for i, j in enumerate(mapping):
            ordered = po[j].description if 0 <= j < len(po) else "(no match)"
            print(f"  invoice '{invoice[i].description}'  ->  order '{ordered}'")
        print(f"\nThe guard (arithmetic) says: {result.status}")
        if mode == "release":
            print(f"\nHuman decision: RELEASED (auto) by {reviewer}")
            return HumanDecision(True, reviewer, rationale or "")
        if mode == "hold":
            reason = rationale or "auto-hold (scripted)"
            print(f"\nHuman decision: HELD (auto) by {reviewer}")
            return HumanDecision(False, reviewer, reason)
        answer = input("\nRelease this invoice to posting? [y/N] ").strip().lower()
        released = answer in {"y", "yes"}
        prompt = (
            "Any note for the record? (optional) "
            if released
            else "Why hold it? (a note for the learning loop) "
        )
        reason = rationale or input(prompt).strip()
        return HumanDecision(released, reviewer, reason)

    return approve


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Pattern 3 (three-way match).")
    parser.add_argument(
        "--case",
        choices=["clean", "overpriced", "short"],
        default="clean",
        help="clean = guard passes; overpriced/short = the guard holds it",
    )
    parser.add_argument(
        "--matcher",
        choices=["rule", "llm"],
        default="rule",
        help="rule = offline deterministic; llm = a real model via OpenRouter",
    )
    parser.add_argument("--model", default=None, help="override the OpenRouter model")
    parser.add_argument(
        "--decision",
        choices=["ask", "release", "hold"],
        default="release",
        help="the human decision when the guard passes (default: release)",
    )
    parser.add_argument(
        "--reviewer",
        default=DEFAULT_REVIEWER,
        help="the named human who decides (goes on the record and the learning loop)",
    )
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

    invoice, received = sample(args.case)

    if args.matcher == "llm":
        matcher = (
            LlmLineMatcher(model=args.model, store=store, vendor=VENDOR)
            if args.model
            else LlmLineMatcher(store=store, vendor=VENDOR)
        )
    else:
        matcher = LlmLineMatcher(
            complete=lambda prompt: rule_based_complete(invoice),
            store=store,
            vendor=VENDOR,
        )

    print(f"\nCase: {args.case}   Vendor: {VENDOR}   "
          f"Invoice total: {invoice_total(invoice)} EUR")

    result = run_threeway(
        matcher,
        invoice,
        PO,
        received,
        approve=make_reviewer(args.decision, args.reviewer, args.rationale),
        vendor=VENDOR,
        case_id=f"MATCH-{args.case.upper()}",
        reviewer=args.reviewer,
        store=store,
    )

    print(f"\nThe guard (arithmetic) says: {result.match.status}")
    for reason in result.match.reasons:
        print(f"  - {reason}")

    print("\n" + "=" * 48)
    if result.outcome == "released":
        print("Every line agrees, and a human released it. Cleared to posting.")
    elif result.outcome == "held_by_guard":
        print("A number did not agree. The invoice is held, and no human was asked.")
    else:
        print("The numbers agreed, but a human held the invoice. Not paid.")

    # The learning loop: keep the decision, report the override rate, and raise a
    # review if it has crossed the line. This is the whole point of persisting.
    store.save(FEEDBACK_FILE)
    overrides, total, rate = store.override_rate()
    print(f"\nOverride rate: {overrides}/{total} = {rate:.0%} "
          f"(threshold {args.override_threshold:.0%})")
    digest = store.review_needed(threshold=args.override_threshold)
    if digest is not None:
        print(f"\n*** REVIEW NEEDED: override rate {digest.rate:.0%} is above "
              f"{digest.threshold:.0%} over the last {digest.total} decisions. ***")
        print("Recent overrides for a human to read (the signal, not the calendar):")
        for item in digest.recent[-5:]:
            why = item["reason"] or "(no reason given)"
            print(f"  {item['item_id']:<14} {item['entity']:<22} {item['decision']}: {why}")


if __name__ == "__main__":
    main()
