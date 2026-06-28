"""A real-SAP client: the same interface as the mock, against real S/4HANA.

This is the swap that takes the agent off your laptop. It implements the exact same
SapClient interface as MockSapClient, so the agent, the governed boundary, the
validator, and the flow do not change at all. Only the inner client changes.

The actual OData calls go through a `transport` you provide for your tenant. That is
deliberate: the exact OData services and field names differ by API and S/4HANA release
(see SAP's API Business Hub), so the one place that knows your tenant's API is the
transport, and everything above it stays the same. This client's job is just to map
your tenant's responses to and from the agent's types.

A real confirm_posting books a real journal entry, so it needs a licensed S/4HANA and
an authorised service user. The trial systems in the early chapters will not post.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from decimal import Decimal

from .models import Document, PostingResult, ProposedPosting, StagedPosting

# A transport maps a named operation + its arguments to a normalised result dict.
# You implement it against your tenant's OData APIs.
Transport = Callable[[str, dict], dict]


def _needs_a_transport(operation: str, args: dict) -> dict:
    raise NotImplementedError(
        "S4SapClient needs a transport that calls your S/4HANA OData APIs. "
        "Pass transport=... mapping the operations 'read_document', "
        "'park_journal_entry', and 'post_journal_entry' to your tenant's calls. "
        "See SAP API Business Hub for the services your release exposes."
    )


class S4SapClient:
    """Talks to a real S/4HANA through a transport you supply for your tenant."""

    def __init__(
        self,
        *,
        base_url: str = "",
        token: str | None = None,
        transport: Transport | None = None,
    ) -> None:
        self.base_url = base_url or os.environ.get("SAP_BASE_URL", "")
        self.token = token or os.environ.get("SAP_TOKEN", "")
        self._transport = transport or _needs_a_transport

    def read_document(self, doc_id: str) -> Document:
        data = self._transport("read_document", {"doc_id": doc_id})
        return Document(
            doc_id=str(data["doc_id"]),
            vendor=str(data["vendor"]),
            currency=str(data["currency"]),
            net_amount=Decimal(str(data["net_amount"])),
            tax_amount=Decimal(str(data["tax_amount"])),
            gross_amount=Decimal(str(data["gross_amount"])),
            document_date=str(data["document_date"]),
        )

    def stage_posting(self, posting: ProposedPosting) -> StagedPosting:
        # Park the journal entry: created as a draft in SAP, not yet booked.
        data = self._transport("park_journal_entry", _as_journal_entry(posting))
        return StagedPosting(staged_id=str(data["parked_id"]), posting=posting)

    def confirm_posting(self, staged_id: str) -> PostingResult:
        # Post the parked entry: this is the real write that books it.
        data = self._transport("post_journal_entry", {"parked_id": staged_id})
        return PostingResult(
            posting_id=str(data["document_number"]),
            doc_id=str(data.get("doc_id", "")),
        )


def _as_journal_entry(posting: ProposedPosting) -> dict:
    """The agent's posting, as a plain dict your transport turns into an OData payload."""
    return {
        "doc_id": posting.doc_id,
        "posting_date": posting.posting_date,
        "currency": posting.currency,
        "lines": [
            {"account": line.account, "side": line.side, "amount": str(line.amount)}
            for line in posting.lines
        ],
    }
