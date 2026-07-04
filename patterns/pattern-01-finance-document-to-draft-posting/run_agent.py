"""Run Pattern 1 end to end against the fake, governed SAP.

    python run_agent.py                        # asks you to approve
    python run_agent.py --approve yes          # auto-approve (scripted)
    python run_agent.py --approve no           # auto-reject (scripted)
    python run_agent.py --doc INV-1002         # a different seeded invoice
    python run_agent.py --doc INV-1003         # a broken invoice the guard refuses
    python run_agent.py --invoice-file my-invoice.json   # your own invoice (fields)
    python run_agent.py --invoice-file invoice.pdf       # your own invoice (PDF/image)
    python run_agent.py --proposer llm         # use a real model via OpenRouter
    python run_agent.py --approver j.doe@nordwind        # who approves (on the record)
    python run_agent.py --approve no --rationale "wrong cost center"   # reject with a reason
    python run_agent.py --approve yes --correct-cost-center CC-2000    # approve, but move it

The learning loop: a correction (or a rejection reason) is remembered per vendor in
feedback.jsonl. The next invoice from that vendor is proposed with the correction
already applied, and the run prints the override rate. When that rate crosses
--override-threshold, it prints a review, so a human looks because the number moved.

You need no SAP account. Everything runs in memory. To read a PDF or image invoice,
or to use --proposer llm, put your key in a file named .env in the repo's top
folder (copy .env.example to .env and fill it in). One .env serves every pattern:
OPENROUTER_API_KEY=sk-or-...
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

# Make the shared SAP layer and this pattern importable when run directly.
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(REPO / "shared"))

from dotenv_loader import load_dotenv  # noqa: E402

# One key, every pattern: load the nearest .env from here up to the repo root,
# so a single .env in the repo's top folder is enough for every agent.
load_dotenv(HERE)

from sap_client import (  # noqa: E402
    Document,
    GovernedSapClient,
    MockSapClient,
    extract_document,
)

from learning import CorrectionMemory  # noqa: E402
from pattern1.flow import DEFAULT_APPROVER, HumanDecision, run_pattern1  # noqa: E402
from pattern1.proposer import LlmBackedProposer, RuleBasedProposer  # noqa: E402
from pattern1.validator import default_config  # noqa: E402

FEEDBACK_FILE = HERE / "feedback.jsonl"


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


def make_approver(mode: str, approver: str, rationale: str | None, correct_cc: str | None):
    corrected = correct_cc or ""

    def approve(document, posting, validation) -> HumanDecision:
        show(document, posting, validation)
        if mode == "yes":
            note = "moved to " + corrected if corrected else ""
            print(f"\nHuman decision: APPROVED (auto) by {approver}"
                  + (f", corrected cost center to {corrected}" if corrected else ""))
            return HumanDecision(True, approver, rationale or note, corrected)
        if mode == "no":
            reason = rationale or "auto-reject (scripted)"
            print(f"\nHuman decision: REJECTED (auto) by {approver}")
            return HumanDecision(False, approver, reason)
        answer = input("\nApprove this posting? [y/N] ").strip().lower()
        approved = answer in {"y", "yes"}
        prompt = (
            "Any note for the record? (optional) "
            if approved
            else "Why? (a note for the learning loop) "
        )
        reason = rationale or input(prompt).strip()
        return HumanDecision(approved, approver, reason, corrected if approved else "")

    return approve


def main() -> None:
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
        "--approver",
        default=DEFAULT_APPROVER,
        help="the named human who decides (goes on the audit record)",
    )
    parser.add_argument(
        "--rationale",
        default=None,
        help="the reviewer's reason, recorded with their decision for the learning loop",
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
    parser.add_argument(
        "--correct-cost-center",
        default=None,
        help="approve, but move the posting to this cost center (the loop remembers it)",
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

    store = CorrectionMemory() if args.reset_feedback else CorrectionMemory.load(FEEDBACK_FILE)

    if args.proposer == "llm":
        proposer = (
            LlmBackedProposer(model=args.model, store=store)
            if args.model
            else LlmBackedProposer(store=store)
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
    learned = store.learned_field(document.vendor, "cost_center")
    if learned:
        print(f"Learned from past reviews: {document.vendor} posts to {learned}.")

    result = run_pattern1(
        client,
        proposer,
        doc_id,
        posting_date="2026-06-27",
        config=config,
        approve=make_approver(
            args.approve, args.approver, args.rationale, args.correct_cost_center
        ),
        cost_center=args.cost_center,
        approver=args.approver,
        store=store,
    )

    print("\n" + "=" * 48)
    print(f"Outcome: {result.outcome}")
    if result.posting_result is not None:
        print(f"Booked as: {result.posting_result.posting_id}")
    if result.outcome == "rejected_by_validator":
        print("The rules rejected it. The human was never asked.")
        for reason in result.validation.reasons:
            print(f"  - {reason}")

    print("\nAudit trail (who did what, and why):")
    for entry in client.audit_log:
        print(
            f"  {entry.actor:<22} {entry.operation:<8} {entry.target:<12} {entry.outcome}"
        )
        if entry.rationale:
            print(f"  {'':<22} reason: {entry.rationale}")
    print(f"\nAudit intact (hash chain verifies): {client.verify_audit()}")

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
            print(f"  {item['doc_id']:<10} {item['vendor']:<22} {item['decision']}: {why}")


if __name__ == "__main__":
    main()
