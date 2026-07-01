"""The governance layer: the leash a real enterprise puts on a service agent.

It wraps any service source and adds four controls:

1. Entitlements       -- the agent may only do operations it is allowed to do.
2. Confirm-hold       -- an action cannot execute until a human has confirmed it.
3. Propagated identity -- every call is attributed to the agent's principal.
4. Tamper-evident audit -- the log is hash-chained, so any later edit is detectable.

In a real company this would be a shared platform service. Here it is a thin,
readable stand-in so you can see the shape of the control in code.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .errors import NotConfirmedError, NotEntitledError
from .models import ActionResult, CaseContext, ProposedStep, StagedAction

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


class GovernedServiceSource:
    """Wraps a service source and enforces entitlements, confirmation, identity,
    and audit."""

    def __init__(
        self,
        inner,
        *,
        entitlements: set[str],
        actor: str = "service-agent@nordwind",
        require_confirmation: bool = True,
    ) -> None:
        self._inner = inner
        self._entitlements = set(entitlements)
        self._actor = actor
        self._require_confirmation = require_confirmation
        self._confirmations: dict[str, str] = {}
        self.audit_log: list[AuditEntry] = []

    def gather_context(self, case_id: str) -> CaseContext:
        self._require("read", case_id)
        context = self._inner.gather_context(case_id)
        # Log the entitlement snapshot alongside the read, so the audit shows what
        # the guard was later evaluated against.
        ent = context.entitlement
        snapshot = (
            f"plan:{ent.plan};in_warranty:{ent.in_warranty};"
            f"expires:{ent.expires_on}"
        )
        self._log("read", case_id, f"ok;{snapshot}")
        return context

    def stage_action(self, step: ProposedStep) -> StagedAction:
        self._require("stage", step.case_id)
        staged = self._inner.stage_action(step)
        self._log("stage", staged.staged_id, f"kind:{step.kind}")
        return staged

    def record_confirmation(self, staged_id: str, approver: str) -> None:
        """Record a human's confirmation of a staged action."""
        self._confirmations[staged_id] = approver
        self._log("confirm", staged_id, f"by:{approver}")

    def execute_action(self, staged_id: str) -> ActionResult:
        self._require("execute", staged_id)
        if self._require_confirmation and staged_id not in self._confirmations:
            self._log("execute", staged_id, "blocked:not_confirmed")
            raise NotConfirmedError(staged_id)
        result = self._inner.execute_action(staged_id)
        self._log("execute", staged_id, f"done:{result.action_id}")
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
