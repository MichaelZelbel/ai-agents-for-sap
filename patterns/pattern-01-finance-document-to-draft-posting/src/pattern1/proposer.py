"""The proposer: the agent's "propose" step.

In the book this is where the AI reads a document and suggests a posting.
The default here is a plain rule-based proposer, so the example runs offline
with no API key. An LLM-backed proposer plugs in behind the same Proposer
interface, and everything downstream (validate, approve, write) is unchanged.
"""

from __future__ import annotations

from typing import Protocol

from sap_client import Document, PostingLine, ProposedPosting

EXPENSE_ACCOUNT = "600000"
INPUT_TAX_ACCOUNT = "154000"
PAYABLE_ACCOUNT = "160000"


class Proposer(Protocol):
    def propose(self, document: Document, *, posting_date: str) -> ProposedPosting:
        """Suggest a posting for a document. Proposes only; books nothing."""
        ...


class RuleBasedProposer:
    """Maps a vendor invoice to the standard three-line posting.

    Debit expense (net) + debit input tax (tax), credit accounts payable
    (gross). Deterministic, so it always proposes a balanced posting.
    """

    def propose(self, document: Document, *, posting_date: str) -> ProposedPosting:
        return ProposedPosting(
            doc_id=document.doc_id,
            posting_date=posting_date,
            currency=document.currency,
            lines=[
                PostingLine(EXPENSE_ACCOUNT, "debit", document.net_amount),
                PostingLine(INPUT_TAX_ACCOUNT, "debit", document.tax_amount),
                PostingLine(PAYABLE_ACCOUNT, "credit", document.gross_amount),
            ],
        )
