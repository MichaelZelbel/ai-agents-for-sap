"""The SAP client layer: one interface, a fake default, a governed wrapper."""

from .errors import (
    DocumentNotFoundError,
    NotApprovedError,
    NotEntitledError,
    SapClientError,
    StagedPostingNotFoundError,
)
from .extract import ExtractionError, extract_document, parse_document
from .governed_client import AuditEntry, GovernedSapClient
from .interface import SapClient
from .mock_client import MockSapClient
from .s4_client import S4SapClient
from .models import (
    Document,
    PostingLine,
    PostingResult,
    ProposedPosting,
    Side,
    StagedPosting,
)

__all__ = [
    "SapClient",
    "MockSapClient",
    "S4SapClient",
    "GovernedSapClient",
    "AuditEntry",
    "Document",
    "PostingLine",
    "PostingResult",
    "ProposedPosting",
    "Side",
    "StagedPosting",
    "SapClientError",
    "DocumentNotFoundError",
    "StagedPostingNotFoundError",
    "NotEntitledError",
    "NotApprovedError",
    "extract_document",
    "parse_document",
    "ExtractionError",
]
