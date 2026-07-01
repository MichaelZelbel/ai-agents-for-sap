"""Run Pattern 3 (three-way match) against a sample invoice, order, and receipt.

    python run_agent.py                 # a clean match: it passes
    python run_agent.py --case overpriced   # a price mismatch: it fails
    python run_agent.py --case short        # goods not fully received: it fails
    python run_agent.py --matcher llm        # match lines with a real model

You need no SAP account and no API key for the default run. The line matcher is
a deterministic stand-in by default; the arithmetic guard is always real.
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

from threeway import Line, LlmLineMatcher, three_way_match  # noqa: E402

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Pattern 3 (three-way match).")
    parser.add_argument(
        "--case",
        choices=["clean", "overpriced", "short"],
        default="clean",
        help="clean = passes; overpriced/short = the guard catches it",
    )
    parser.add_argument(
        "--matcher",
        choices=["rule", "llm"],
        default="rule",
        help="rule = offline deterministic; llm = a real model via OpenRouter",
    )
    parser.add_argument("--model", default=None, help="override the OpenRouter model")
    args = parser.parse_args()

    invoice, received = sample(args.case)

    if args.matcher == "llm":
        matcher = LlmLineMatcher(model=args.model) if args.model else LlmLineMatcher()
    else:
        matcher = LlmLineMatcher(complete=lambda prompt: rule_based_complete(invoice))

    mapping = matcher.match(invoice, PO)
    result = three_way_match(invoice, PO, received, mapping)

    print(f"\nCase: {args.case}")
    print("\nThe matcher (AI) lines invoice up against the purchase order:")
    for i, j in enumerate(mapping):
        ordered = PO[j].description if 0 <= j < len(PO) else "(no match)"
        print(f"  invoice '{invoice[i].description}'  ->  order '{ordered}'")

    print(f"\nThe guard (arithmetic) says: {result.status}")
    for reason in result.reasons:
        print(f"  - {reason}")

    print("\n" + "=" * 48)
    if result.status == "PASS":
        print("Every line agrees on quantity, receipt, and price. Cleared.")
    else:
        print("A number did not agree. The invoice is held, not paid.")


if __name__ == "__main__":
    main()
