"""A fake SAP system that runs in memory, for free, with no SAP account.

It seeds a few invoices, lets you stage a posting, and lets you confirm it.
It is deliberately simple: just enough to run the patterns end to end.
"""

from __future__ import annotations

from decimal import Decimal
from itertools import count

from .errors import DocumentNotFoundError, StagedPostingNotFoundError
from .models import Document, PostingResult, ProposedPosting, StagedPosting


def _seed_documents() -> dict[str, Document]:
    docs = [
        Document(
            doc_id="INV-1001",
            vendor="Office Supplies Co",
            currency="EUR",
            net_amount=Decimal("1000.00"),
            tax_amount=Decimal("190.00"),
            gross_amount=Decimal("1190.00"),
            document_date="2026-06-20",
        ),
        Document(
            doc_id="INV-1002",
            vendor="Cloud Hosting Ltd",
            currency="EUR",
            net_amount=Decimal("500.00"),
            tax_amount=Decimal("95.00"),
            gross_amount=Decimal("595.00"),
            document_date="2026-06-21",
        ),
    ]
    return {d.doc_id: d for d in docs}


class MockSapClient:
    """In-memory stand-in for SAP. Implements the SapClient interface."""

    def __init__(self) -> None:
        self._documents = _seed_documents()
        self._staged: dict[str, StagedPosting] = {}
        self._posted: dict[str, PostingResult] = {}
        self._staged_seq = count(1)
        self._posting_seq = count(1)

    def read_document(self, doc_id: str) -> Document:
        try:
            return self._documents[doc_id]
        except KeyError:
            raise DocumentNotFoundError(doc_id) from None

    def stage_posting(self, posting: ProposedPosting) -> StagedPosting:
        staged_id = f"STG-{next(self._staged_seq):04d}"
        staged = StagedPosting(staged_id=staged_id, posting=posting)
        self._staged[staged_id] = staged
        return staged

    def confirm_posting(self, staged_id: str) -> PostingResult:
        staged = self._staged.get(staged_id)
        if staged is None:
            raise StagedPostingNotFoundError(staged_id)
        result = PostingResult(
            posting_id=f"DOC-{next(self._posting_seq):010d}",
            doc_id=staged.posting.doc_id,
        )
        self._posted[staged_id] = result
        return result
