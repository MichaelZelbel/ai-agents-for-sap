"""Run Pattern 2 (invoice triage) against the fake SAP.

    python run_agent.py                 # triage INV-1001 offline (no key)
    python run_agent.py --doc INV-1002  # triage a different document
    python run_agent.py --triager llm    # use a real model via OpenRouter
    python run_agent.py --confirm yes    # auto-confirm the routing (scripted)
    python run_agent.py --confirm no --rationale "this is a credit note"  # reject with a reason
    python run_agent.py --confirm no --correct-category not_an_invoice     # reject, name the right one

The learning loop: a rejection reason (or a named correction) is remembered per
vendor in feedback.jsonl. The next document from that vendor is classified with those
past corrections folded into the prompt, and the run prints the override rate. When
that rate crosses --override-threshold, it prints a review, so a human looks because
the number moved.

You need no SAP account and no API key for the default run. Everything runs in memory,
and the classifier is a deterministic stand-in by default.
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

from sap_client import Document, MockSapClient  # noqa: E402

from learning import CorrectionMemory  # noqa: E402
from triage import (  # noqa: E402
    CATEGORIES,
    DEFAULT_REVIEWER,
    HumanDecision,
    LlmTriager,
    route,
    run_triage,
)

FEEDBACK_FILE = HERE / "feedback.jsonl"


def rule_based_complete(document: Document) -> str:
    """A deterministic stand-in for the model. It returns one of CATEGORIES so
    the flow runs offline with no API key. A small invoice with tax reads as a
    purchase-order invoice; a small one without as a direct expense; anything
    with no amount as not an invoice. Crude on purpose: the guard, route(),
    still refuses any label it does not know."""
    if document.gross_amount <= 0:
        return "not_an_invoice"
    if document.tax_amount > 0 and document.gross_amount >= 1000:
        return "po_invoice"
    return "direct_expense"


def make_confirmer(mode: str, reviewer: str, rationale: str | None, correct_cat: str | None):
    corrected = correct_cat or ""

    def confirm(document, category, next_step) -> HumanDecision:
        print(f"\nDocument {document.doc_id} from {document.vendor}")
        print(f"  gross {document.gross_amount} {document.currency}")
        print(f"\nThe agent classifies it as: {category}")
        print(f"The router (deterministic guard) sends it to: {next_step}")
        if mode == "yes":
            print(f"\nHuman decision: CONFIRMED (auto) by {reviewer}")
            return HumanDecision(True, reviewer, rationale or "")
        if mode == "no":
            reason = rationale or "auto-reject (scripted)"
            note = f", corrected to {corrected}" if corrected else ""
            print(f"\nHuman decision: REJECTED (auto) by {reviewer}{note}")
            return HumanDecision(False, reviewer, reason, corrected)
        answer = input("\nConfirm this routing? [y/N] ").strip().lower()
        confirmed = answer in {"y", "yes"}
        prompt = (
            "Any note for the record? (optional) "
            if confirmed
            else "Why? (a note for the learning loop) "
        )
        reason = rationale or input(prompt).strip()
        return HumanDecision(confirmed, reviewer, reason, "" if confirmed else corrected)

    return confirm


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Pattern 2 (invoice triage).")
    parser.add_argument("--doc", default="INV-1001", help="document id to triage")
    parser.add_argument(
        "--triager",
        choices=["rule", "llm"],
        default="rule",
        help="rule = offline deterministic; llm = a real model via OpenRouter",
    )
    parser.add_argument("--model", default=None, help="override the OpenRouter model")
    parser.add_argument(
        "--confirm", choices=["ask", "yes", "no"], default="ask", help="human decision"
    )
    parser.add_argument(
        "--reviewer",
        default=DEFAULT_REVIEWER,
        help="the named human who decides (goes on the record)",
    )
    parser.add_argument(
        "--rationale",
        default=None,
        help="the reviewer's reason, recorded with their decision for the learning loop",
    )
    parser.add_argument(
        "--correct-category",
        default=None,
        choices=list(CATEGORIES),
        help="reject the routing and name the category it should have been",
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

    client = MockSapClient()
    document = client.read_document(args.doc)

    if args.triager == "llm":
        triager = (
            LlmTriager(model=args.model, store=store)
            if args.model
            else LlmTriager(store=store)
        )
    else:
        # The offline classifier reads the document, not the prompt string, and
        # returns a category. It plugs in behind the same interface as the model.
        triager = LlmTriager(
            complete=lambda prompt: rule_based_complete(document), store=store
        )

    result = run_triage(
        triager,
        document,
        confirm=make_confirmer(
            args.confirm, args.reviewer, args.rationale, args.correct_category
        ),
        reviewer=args.reviewer,
        store=store,
    )

    print("\n" + "=" * 48)
    print(f"Outcome: {result.outcome}")
    print(f"Routed as: {result.category} -> {result.next_step}")

    print("\nKnown categories and their routes:")
    for known in CATEGORIES:
        print(f"  {known:<16} -> {route(known)}")

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
            print(f"  {item['item_id']:<10} {item['entity']:<22} {item['decision']}: {why}")


if __name__ == "__main__":
    main()
