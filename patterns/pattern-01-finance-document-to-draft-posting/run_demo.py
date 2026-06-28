"""Run Pattern 1 end to end against the fake, governed SAP.

    python run_demo.py                 # asks you to approve
    python run_demo.py --approve yes   # auto-approve (scripted)
    python run_demo.py --approve no    # auto-reject (scripted)
    python run_demo.py --doc INV-1002

You need no SAP account. Everything runs in memory.
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

from sap_client import GovernedSapClient, MockSapClient  # noqa: E402

from pattern1.flow import run_pattern1  # noqa: E402
from pattern1.proposer import LlmBackedProposer, RuleBasedProposer  # noqa: E402
from pattern1.validator import default_config  # noqa: E402


def show(document, posting, validation) -> None:
    print(f"\nDocument {document.doc_id} from {document.vendor}")
    print(f"  gross {document.gross_amount} {document.currency}")
    print("\nThe agent proposes this posting:")
    for line in posting.lines:
        print(f"  {line.side:<6} {line.account}  {line.amount} {posting.currency}")
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
    parser = argparse.ArgumentParser(description="Run Pattern 1 end to end.")
    parser.add_argument("--doc", default="INV-1001", help="document id to post")
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
    args = parser.parse_args()

    if args.proposer == "llm":
        proposer = (
            LlmBackedProposer(model=args.model) if args.model else LlmBackedProposer()
        )
    else:
        proposer = RuleBasedProposer()

    client = GovernedSapClient(
        MockSapClient(), entitlements={"read", "stage", "confirm"}
    )

    result = run_pattern1(
        client,
        proposer,
        args.doc,
        posting_date="2026-06-27",
        config=default_config(),
        approve=make_approver(args.approve),
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
        print(f"  {entry.operation:<8} {entry.target:<12} {entry.outcome}")


if __name__ == "__main__":
    main()
