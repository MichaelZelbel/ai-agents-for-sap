"""The SAP client layer: one interface, a fake default, a governed wrapper."""

from .errors import (
    DocumentNotFoundError,
    NotApprovedError,
    NotEntitledError,
    SapClientError,
    StagedPostingNotFoundError,
)
from .governed_client import AuditEntry, GovernedSapClient
from .interface import SapClient
from .mock_client import MockSapClient
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
]
