"""Run Pattern 1 end to end against the fake, governed SAP.

    python run_agent.py                        # asks you to approve
    python run_agent.py --approve yes          # auto-approve (scripted)
    python run_agent.py --approve no           # auto-reject (scripted)
    python run_agent.py --doc INV-1002         # a different seeded invoice
    python run_agent.py --doc INV-1003         # a broken invoice the guard refuses
    python run_agent.py --invoice-file my-invoice.json   # your own invoice (fields)
    python run_agent.py --invoice-file invoice.pdf       # your own invoice (PDF/image)
    python run_agent.py --proposer llm         # use a real model via OpenRouter

You need no SAP account. Everything runs in memory. To read a PDF or image invoice,
or to use --proposer llm, put your key in a file named .env next to this script:
OPENROUTER_API_KEY=sk-or-...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

# Make the shared SAP layer and this pattern importable when run directly.
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(REPO / "shared"))

from sap_client import (  # noqa: E402
    Document,
    GovernedSapClient,
    MockSapClient,
    extract_document,
)

from pattern1.flow import run_pattern1  # noqa: E402
from pattern1.proposer import LlmBackedProposer, RuleBasedProposer  # noqa: E402
from pattern1.validator import default_config  # noqa: E402


def load_dotenv() -> None:
    """Read KEY=VALUE lines from a .env file next to this script into the
    environment, so your OpenRouter key persists on disk and every run and
    every tool can see it. Values already set in the environment win.
    """
    env_file = HERE / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def load_invoice_file(path: str) -> Document:
    """Load one invoice you can post.

    A .json file is read straight into a Document. Any other file (a PDF or an
    image of an invoice) is read by a vision model via OpenRouter, the same
    "document reader" step a real deployment runs before the agent ever sees it.
    """
    if path.lower().endswith(".json"):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return Document(
            doc_id=str(data["doc_id"]),
            vendor=str(data["vendor"]),
            currency=str(data["currency"]),
            net_amount=Decimal(str(data["net_amount"])),
            tax_amount=Decimal(str(data["tax_amount"])),
            gross_amount=Decimal(str(data["gross_amount"])),
            document_date=str(data["document_date"]),
        )
    return extract_document(path)


def show(document, posting, validation) -> None:
    print(f"\nDocument {document.doc_id} from {document.vendor}")
    conf = "" if document.confidence is None else f", read confidence {document.confidence:.2f}"
    print(f"  gross {document.gross_amount} {document.currency}{conf}")
    print("\nThe agent proposes this posting:")
    for line in posting.lines:
        print(f"  {line.side:<6} {line.account}  {line.amount} {posting.currency}")
    print(f"  tax code {posting.tax_code}  cost center {posting.cost_center}")
    print(f"\nThe validator says: {validation.status}")
    for reason in validation.reasons:
        print(f"  - {reason}")


def make_approver(mode: str):
    def approve(document, posting, validation) -> bool:
        show(document, posting, validation)
        if mode == "yes":
            print("\nHuman decision: APPROVED (auto)")
            return True
        if mode == "no":
            print("\nHuman decision: REJECTED (auto)")
            return False
        answer = input("\nApprove this posting? [y/N] ").strip().lower()
        return answer in {"y", "yes"}

    return approve


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Run Pattern 1 end to end.")
    parser.add_argument("--doc", default="INV-1001", help="document id to post")
    parser.add_argument(
        "--invoice-file",
        default=None,
        help="path to a JSON file with your own invoice (overrides --doc)",
    )
    parser.add_argument(
        "--approve", choices=["ask", "yes", "no"], default="ask", help="human decision"
    )
    parser.add_argument(
        "--proposer",
        choices=["rule", "llm"],
        default="rule",
        help="rule = offline deterministic; llm = a real model via OpenRouter",
    )
    parser.add_argument("--model", default=None, help="override the OpenRouter model")
    parser.add_argument(
        "--auto-onboard",
        action="store_true",
        help="if the vendor is not in the master, add it before posting",
    )
    parser.add_argument(
        "--cost-center",
        default="CC-1000",
        help="cost center for the expense line (CC-1000/CC-2000 are active)",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.5,
        help="reject a read invoice below this confidence (0 turns the check off)",
    )
    args = parser.parse_args()

    if args.proposer == "llm":
        proposer = (
            LlmBackedProposer(model=args.model) if args.model else LlmBackedProposer()
        )
    else:
        proposer = RuleBasedProposer()

    mock = MockSapClient()
    doc_id = args.doc
    if args.invoice_file:
        invoice = load_invoice_file(args.invoice_file)
        mock.register_document(invoice)
        doc_id = invoice.doc_id

    # Onboarding a vendor is a master-data change. In a real company it is a
    # separate role from posting; here you can opt in with --auto-onboard.
    document = mock.read_document(doc_id)
    if args.auto_onboard and not mock.is_known_vendor(document.vendor):
        mock.add_business_partner(document.vendor)
        print(f"Onboarded vendor to the Business Partner master: {document.vendor}")

    client = GovernedSapClient(mock, entitlements={"read", "stage", "confirm"})

    config = replace(
        default_config(),
        known_vendors=mock.known_vendors(),
        known_tax_codes=mock.known_tax_codes(),
        active_cost_centers=mock.active_cost_centers(),
        min_confidence=args.min_confidence if args.min_confidence > 0 else None,
    )
    result = run_pattern1(
        client,
        proposer,
        doc_id,
        posting_date="2026-06-27",
        config=config,
        approve=make_approver(args.approve),
        cost_center=args.cost_center,
    )

    print("\n" + "=" * 48)
    print(f"Outcome: {result.outcome}")
    if result.posting_result is not None:
        print(f"Booked as: {result.posting_result.posting_id}")
    if result.outcome == "rejected_by_validator":
        print("The rules rejected it. The human was never asked.")
        for reason in result.validation.reasons:
            print(f"  - {reason}")

    print("\nAudit trail (every call the agent made):")
    for entry in client.audit_log:
        print(
            f"  {entry.actor}  {entry.operation:<8} {entry.target:<12} {entry.outcome}"
        )
    print(f"\nAudit intact (hash chain verifies): {client.verify_audit()}")


if __name__ == "__main__":
    main()
