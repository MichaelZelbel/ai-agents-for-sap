"""Tests for the end-to-end packet flow.

Offline: the default rule-based narrator needs no key. These prove the packet
is staged (the record is untouched), the policy version is cited and logged,
the human decision is recorded, and a blocked packet cannot be approved.
"""

from procurement import (
    PacketAuditLog,
    RuleBasedNarrator,
    assemble_packet,
    record_decision,
    seed_requisitions,
)


def test_clean_packet_is_staged_and_record_unchanged():
    before = seed_requisitions()["REQ-2001"]
    result = assemble_packet("REQ-2001")
    packet = result.packet
    assert packet.status == "staged"
    assert packet.route == "auto_review"
    assert packet.policy_version == "2026.2"
    # The requisition inside the packet is the same record, unchanged.
    assert packet.requisition == before
    # The staging is logged and the chain verifies.
    ops = [e.operation for e in result.log.entries]
    assert ops == ["read", "draft", "guard", "stage_packet"]
    assert result.log.verify()


def test_bad_case_routes_and_is_flagged():
    result = assemble_packet("REQ-2002")
    packet = result.packet
    assert packet.route == "blocked_missing_docs"
    assert packet.flags  # not empty


def test_approval_is_recorded_with_policy_version():
    log = PacketAuditLog()
    result = assemble_packet("REQ-2001", RuleBasedNarrator(), log=log)
    outcome = record_decision(
        result.packet, approver="bob", approved=True, log=log
    )
    assert outcome == "approved"
    last = log.entries[-1]
    assert last.operation == "decision"
    assert "approved:by:bob" in last.outcome
    assert "policy:2026.2" in last.outcome
    assert log.verify()


def test_rejection_is_recorded():
    log = PacketAuditLog()
    result = assemble_packet("REQ-2003", log=log)
    outcome = record_decision(
        result.packet, approver="manager", approved=False, log=log
    )
    assert outcome == "rejected"
    assert "rejected:by:manager" in log.entries[-1].outcome


def test_blocked_packet_cannot_be_approved():
    log = PacketAuditLog()
    result = assemble_packet("REQ-2002", log=log)  # missing contract -> blocked
    outcome = record_decision(
        result.packet, approver="dave", approved=True, log=log
    )
    # The block is not just advisory: approving it is refused.
    assert outcome == "refused_blocked"
    assert "refused:blocked_missing_docs" in log.entries[-1].outcome
    assert log.verify()
