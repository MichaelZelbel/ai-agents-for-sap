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
        # A deliberately broken invoice: the stated total (gross) does not match
        # its own line items. Net plus tax is 1190, but gross says 1200. The agent
        # will still propose a posting, and the validator will refuse it because
        # the posting cannot balance. Use it to see an exception case.
        Document(
            doc_id="INV-1003",
            vendor="Meridian Interiors GmbH",
            currency="EUR",
            net_amount=Decimal("1000.00"),
            tax_amount=Decimal("190.00"),
            gross_amount=Decimal("1200.00"),
            document_date="2026-06-22",
        ),
    ]
    return {d.doc_id: d for d in docs}


def _seed_business_partners() -> set[str]:
    """The vendor master: who SAP already knows. You cannot post to a vendor that
    is not a Business Partner here, just like a real system. Seeded with the
    vendors of the sample invoices, so those post and an outside vendor does not."""
    return {"Office Supplies Co", "Cloud Hosting Ltd", "Meridian Interiors GmbH"}


def _seed_tax_codes() -> dict[str, Decimal]:
    """Valid tax codes and the rate each one means. A posting must carry a known
    code, and the code has to match the invoice's actual tax rate."""
    return {
        "V0": Decimal("0.00"),  # no tax
        "V1": Decimal("0.19"),  # standard rate
        "V2": Decimal("0.07"),  # reduced rate
    }


def _seed_cost_centers() -> set[str]:
    """Cost centers that exist and are active. A posting to an unknown or blocked
    cost center is refused."""
    return {"CC-1000", "CC-2000"}


class MockSapClient:
    """In-memory stand-in for SAP. Implements the SapClient interface."""

    def __init__(self) -> None:
        self._documents = _seed_documents()
        self._business_partners = _seed_business_partners()
        self._tax_codes = _seed_tax_codes()
        self._cost_centers = _seed_cost_centers()
        self._staged: dict[str, StagedPosting] = {}
        self._posted: dict[str, PostingResult] = {}
        self._staged_seq = count(1)
        self._posting_seq = count(1)

    def register_document(self, document: Document) -> None:
        """Add (or replace) a document, e.g. one loaded from your own file."""
        self._documents[document.doc_id] = document

    def known_vendors(self) -> frozenset[str]:
        """The current Business Partner master (vendor names SAP knows)."""
        return frozenset(self._business_partners)

    def is_known_vendor(self, name: str) -> bool:
        return name in self._business_partners

    def add_business_partner(self, name: str) -> None:
        """Onboard a vendor into the master. In a real company this is a master-data
        team's job, gated so a posting agent cannot do it alone."""
        self._business_partners.add(name)

    def known_tax_codes(self) -> dict[str, Decimal]:
        """The valid tax codes and their rates."""
        return dict(self._tax_codes)

    def active_cost_centers(self) -> frozenset[str]:
        """The cost centers that exist and are active."""
        return frozenset(self._cost_centers)

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
