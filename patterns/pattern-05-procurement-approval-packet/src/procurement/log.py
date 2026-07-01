"""A small tamper-evident audit log for the packet flow.

Every action the agent takes is logged: reading the requisition, drafting the
narrative, running the guard, staging the packet, and recording the human's
decision. The log is hash-chained, so any later edit to a past entry is
detectable, the same idea as the shared governed client.

The packet flow does not write to the SAP posting boundary, so it keeps its own
small log here rather than reusing the posting-oriented GovernedSapClient.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

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


class PacketAuditLog:
    """An append-only, hash-chained log. One instance per run."""

    def __init__(self, actor: str = "procurement-agent@nordwind") -> None:
        self._actor = actor
        self.entries: list[AuditEntry] = []

    def record(self, operation: str, target: str, outcome: str) -> None:
        prev = self.entries[-1].entry_hash if self.entries else GENESIS
        entry_hash = _chain_hash(prev, operation, target, outcome, self._actor)
        self.entries.append(
            AuditEntry(
                operation=operation,
                target=target,
                outcome=outcome,
                actor=self._actor,
                entry_hash=entry_hash,
            )
        )

    def verify(self) -> bool:
        """Recompute the whole chain. Returns False if any entry was changed."""
        prev = GENESIS
        for entry in self.entries:
            expected = _chain_hash(
                prev, entry.operation, entry.target, entry.outcome, entry.actor
            )
            if expected != entry.entry_hash:
                return False
            prev = entry.entry_hash
        return True
