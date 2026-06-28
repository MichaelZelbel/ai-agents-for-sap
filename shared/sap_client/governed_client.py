"""The governance layer: the leash a real enterprise puts on an agent.

It wraps any SapClient and adds four controls:

1. Entitlements         -- the agent may only do operations it is allowed to do.
2. Write-hold           -- a posting cannot be booked until a human has approved it.
3. Propagated identity  -- every call is attributed to the agent's principal.
4. Tamper-evident audit -- the log is hash-chained, so any later edit is detectable.

In a real company this would be a shared platform service. Here it is a thin,
readable stand-in so you can see the shape of the control in code.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .errors import NotApprovedError, NotEntitledError
from .interface import SapClient
from .models import Document, PostingResult, ProposedPosting, StagedPosting

GENESIS = "genesis"


@dataclass(frozen=True)
class AuditEntry:
    operation: str
    target: str
    outcome: str
    actor: str
    entry_hash: str  # chains this entry to the one before it


def _chain_hash(
    prev_hash: str, operation: str, target: str, outcome: str, actor: str
) -> str:
    """The hash of one entry, mixed with the hash of the entry before it. Change any
    past field and every hash after it stops matching."""
    h = hashlib.sha256()
    h.update(prev_hash.encode("utf-8"))
    h.update("\x1f".join([operation, target, outcome, actor]).encode("utf-8"))
    return h.hexdigest()


class GovernedSapClient:
    """Wraps a SapClient and enforces entitlements, approval, identity, and audit."""

    def __init__(
        self,
        inner: SapClient,
        *,
        entitlements: set[str],
        actor: str = "invoice-agent@nordwind",
        require_approval: bool = True,
    ) -> None:
        self._inner = inner
        self._entitlements = set(entitlements)
        self._actor = actor
        self._require_approval = require_approval
        self._approvals: dict[str, str] = {}
        self.audit_log: list[AuditEntry] = []

    def read_document(self, doc_id: str) -> Document:
        self._require("read", doc_id)
        doc = self._inner.read_document(doc_id)
        self._log("read", doc_id, "ok")
        return doc

    def stage_posting(self, posting: ProposedPosting) -> StagedPosting:
        self._require("stage", posting.doc_id)
        staged = self._inner.stage_posting(posting)
        self._log("stage", staged.staged_id, "ok")
        return staged

    def record_approval(self, staged_id: str, approver: str) -> None:
        """Record a human's approval of a staged posting."""
        self._approvals[staged_id] = approver
        self._log("approve", staged_id, f"by:{approver}")

    def confirm_posting(self, staged_id: str) -> PostingResult:
        self._require("confirm", staged_id)
        if self._require_approval and staged_id not in self._approvals:
            self._log("confirm", staged_id, "blocked:not_approved")
            raise NotApprovedError(staged_id)
        result = self._inner.confirm_posting(staged_id)
        self._log("confirm", staged_id, f"posted:{result.posting_id}")
        return result

    def verify_audit(self) -> bool:
        """Recompute the whole chain. Returns False if any entry was changed."""
        prev = GENESIS
        for entry in self.audit_log:
            expected = _chain_hash(
                prev, entry.operation, entry.target, entry.outcome, entry.actor
            )
            if expected != entry.entry_hash:
                return False
            prev = entry.entry_hash
        return True

    def _require(self, operation: str, target: str) -> None:
        if operation not in self._entitlements:
            self._log(operation, target, "blocked:not_entitled")
            raise NotEntitledError(operation)

    def _log(self, operation: str, target: str, outcome: str) -> None:
        prev = self.audit_log[-1].entry_hash if self.audit_log else GENESIS
        entry_hash = _chain_hash(prev, operation, target, outcome, self._actor)
        self.audit_log.append(
            AuditEntry(
                operation=operation,
                target=target,
                outcome=outcome,
                actor=self._actor,
                entry_hash=entry_hash,
            )
        )
