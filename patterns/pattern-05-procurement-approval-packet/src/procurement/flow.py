"""The Pattern 5 flow: assemble the packet, then let a human decide.

    read -> enrich -> draft (AI) -> guard (rules) -> stage packet -> (human decides)

The rule of the pattern lives here. The AI drafts the narrative, but the
deterministic guard sets the route, and the packet is only STAGED. It does not
change the requisition record. A human approver reads the packet and decides.
High-risk or policy-deviation cases route to escalation. The decision and the
policy version are logged.
"""

from __future__ import annotations

from dataclasses import dataclass

from .data import default_policy, seed_requisitions, seed_suppliers
from .guard import GuardConfig, default_guard_config, run_guard
from .log import PacketAuditLog
from .models import Packet, Policy, Requisition, Supplier
from .narrator import Narrator, RuleBasedNarrator


@dataclass(frozen=True)
class PacketResult:
    packet: Packet
    log: PacketAuditLog


def assemble_packet(
    request_id: str,
    narrator: Narrator | None = None,
    *,
    requisitions: dict[str, Requisition] | None = None,
    suppliers: dict[str, Supplier] | None = None,
    policy: Policy | None = None,
    config: GuardConfig | None = None,
    log: PacketAuditLog | None = None,
) -> PacketResult:
    """Build the approval packet for one requisition and stage it.

    The requisition record is read only. The packet is the artifact we stage;
    the record is never touched. If a caller passes no narrator, we default to
    the offline rule-based one, so this works with no key.
    """
    requisitions = requisitions or seed_requisitions()
    suppliers = suppliers or seed_suppliers()
    policy = policy or default_policy()
    config = config or default_guard_config()
    narrator = narrator or RuleBasedNarrator()
    log = log or PacketAuditLog()

    if request_id not in requisitions:
        raise KeyError(f"unknown requisition: {request_id}")
    requisition = requisitions[request_id]
    log.record("read", request_id, "ok")

    supplier = suppliers.get(requisition.supplier_id)
    if supplier is None:
        raise KeyError(f"unknown supplier: {requisition.supplier_id}")

    # The AI drafts. It gets no vote on the route.
    draft = narrator.draft(requisition, supplier, policy)
    log.record("draft", request_id, "narrative_drafted")

    # The deterministic guard decides the route.
    guard = run_guard(requisition, supplier, policy, config=config)
    log.record("guard", request_id, f"route:{guard.route}")

    packet = Packet(
        request_id=request_id,
        requisition=requisition,
        supplier=supplier,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        risk_narrative=draft.narrative,
        recommendation=draft.recommendation,
        flags=guard.flags,
        route=guard.route,
    )

    # Stage the packet. This does NOT change the requisition record.
    log.record("stage_packet", request_id, f"policy:{policy.version}")
    return PacketResult(packet=packet, log=log)


def record_decision(
    packet: Packet,
    *,
    approver: str,
    approved: bool,
    log: PacketAuditLog,
) -> str:
    """Record a human's decision on a staged packet. Logs the policy version.

    A packet routed to "blocked_missing_docs" cannot be approved: the missing
    document must be supplied first. Approving it anyway is refused here, so the
    block is not just advisory.
    """
    if approved and packet.route == "blocked_missing_docs":
        log.record(
            "decision", packet.request_id, "refused:blocked_missing_docs"
        )
        return "refused_blocked"

    outcome = "approved" if approved else "rejected"
    log.record(
        "decision",
        packet.request_id,
        f"{outcome}:by:{approver}:policy:{packet.policy_version}",
    )
    return outcome
