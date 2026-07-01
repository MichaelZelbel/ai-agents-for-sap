"""The governance layer: the leash a real enterprise puts on an agent.

It wraps a MockSalesClient and adds four controls:

1. Entitlements         -- the agent may only do operations it is allowed to do.
2. Release-hold         -- an order cannot be released until a human has approved it.
3. Propagated identity  -- every call is attributed to the agent's principal.
4. Tamper-evident audit -- the log is hash-chained, so any later edit is detectable.

In a real company this would be a shared platform service. Here it is a thin,
readable stand-in so you can see the shape of the control in code.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .errors import NotApprovedError, NotEntitledError
from .mock_client import MockSalesClient
from .models import DraftOrder, ReleaseResult, StagedOrder

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
    """The hash of one entry, mixed with the hash of the entry before it. Change
    any past field and every hash after it stops matching."""
    h = hashlib.sha256()
    h.update(prev_hash.encode("utf-8"))
    h.update("\x1f".join([operation, target, outcome, actor]).encode("utf-8"))
    return h.hexdigest()


class GovernedSalesClient:
    """Wraps a sales client and enforces entitlements, approval, identity, audit."""

    def __init__(
        self,
        inner: MockSalesClient,
        *,
        entitlements: set[str],
        actor: str = "sales-agent@nordwind",
        require_approval: bool = True,
    ) -> None:
        self._inner = inner
        self._entitlements = set(entitlements)
        self._actor = actor
        self._require_approval = require_approval
        self._approvals: dict[str, str] = {}
        self.audit_log: list[AuditEntry] = []

    # Read access to master data, logged like any other operation.
    @property
    def customers(self):
        return self._inner.customers

    @property
    def catalog(self):
        return self._inner.catalog

    def stage_order(self, order: DraftOrder) -> StagedOrder:
        self._require("stage", order.request_id)
        staged = self._inner.stage_order(order)
        self._log("stage", staged.staged_id, "ok")
        return staged

    def record_approval(self, staged_id: str, approver: str) -> None:
        """Record a human's approval of a staged order."""
        self._approvals[staged_id] = approver
        self._log("approve", staged_id, f"by:{approver}")

    def release_order(self, staged_id: str) -> ReleaseResult:
        self._require("release", staged_id)
        if self._require_approval and staged_id not in self._approvals:
            self._log("release", staged_id, "blocked:not_approved")
            raise NotApprovedError(staged_id)
        result = self._inner.release_order(staged_id)
        self._log("release", staged_id, f"released:{result.order_id}")
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
