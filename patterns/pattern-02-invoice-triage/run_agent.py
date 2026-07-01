"""Run Pattern 2 (invoice triage) against the fake SAP.

    python run_agent.py                 # triage INV-1001 offline (no key)
    python run_agent.py --doc INV-1002  # triage a different document
    python run_agent.py --triager llm    # use a real model via OpenRouter

You need no SAP account and no API key for the default run. Everything runs
in memory, and the classifier is a deterministic stand-in by default.
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

from triage import CATEGORIES, LlmTriager, route  # noqa: E402


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
    args = parser.parse_args()

    client = MockSapClient()
    document = client.read_document(args.doc)

    if args.triager == "llm":
        triager = LlmTriager(model=args.model) if args.model else LlmTriager()
    else:
        # The offline classifier reads the document, not the prompt string, and
        # returns a category. It plugs in behind the same interface as the model.
        triager = LlmTriager(complete=lambda prompt: rule_based_complete(document))

    category = triager.classify(document)
    next_step = route(category)

    print(f"\nDocument {document.doc_id} from {document.vendor}")
    print(f"  gross {document.gross_amount} {document.currency}")
    print(f"\nThe agent classifies it as: {category}")
    print(f"The router (deterministic guard) sends it to: {next_step}")

    print("\n" + "=" * 48)
    print("Known categories and their routes:")
    for known in CATEGORIES:
        print(f"  {known:<16} -> {route(known)}")


if __name__ == "__main__":
    main()
