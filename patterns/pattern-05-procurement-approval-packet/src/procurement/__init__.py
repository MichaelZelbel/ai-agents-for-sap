"""Pattern 5: Policy-Aware Procurement Approval Packet.

A thin requisition comes in. The agent assembles an approval packet: the
supplier profile, the applicable policy citation with its version, risk flags,
and a recommended path. The AI drafts the narrative and recommendation. A
deterministic guard decides. A human approves. Every action is logged.
"""

from .models import (
    Packet,
    Policy,
    Requisition,
    Supplier,
)
from .data import (
    default_policy,
    seed_requisitions,
    seed_suppliers,
)
from .narrator import (
    LlmBackedNarrator,
    Narrator,
    NarratorError,
    RuleBasedNarrator,
    RiskDraft,
)
from .guard import GuardResult, GuardConfig, default_guard_config, run_guard
from .flow import PacketResult, assemble_packet, record_decision
from .log import AuditEntry, PacketAuditLog

__all__ = [
    "Requisition",
    "Supplier",
    "Policy",
    "Packet",
    "seed_requisitions",
    "seed_suppliers",
    "default_policy",
    "Narrator",
    "RuleBasedNarrator",
    "LlmBackedNarrator",
    "NarratorError",
    "RiskDraft",
    "GuardResult",
    "GuardConfig",
    "default_guard_config",
    "run_guard",
    "PacketResult",
    "assemble_packet",
    "record_decision",
    "AuditEntry",
    "PacketAuditLog",
]
