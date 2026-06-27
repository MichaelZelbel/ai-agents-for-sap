"""The one contract every SAP client obeys.

An agent never touches SAP directly. It talks to something that implements
this interface: the fake one for the book, a governed wrapper, or (later)
a real SAP client. Same three methods every time.
"""

from __future__ import annotations

from typing import Protocol

from .models import Document, PostingResult, ProposedPosting, StagedPosting


class SapClient(Protocol):
    def read_document(self, doc_id: str) -> Document:
        """Return the source document, or raise DocumentNotFoundError."""
        ...

    def stage_posting(self, posting: ProposedPosting) -> StagedPosting:
        """Hold a proposed posting at the boundary. Does not book it."""
        ...

    def confirm_posting(self, staged_id: str) -> PostingResult:
        """Book a staged posting. Raises StagedPostingNotFoundError if unknown."""
        ...
