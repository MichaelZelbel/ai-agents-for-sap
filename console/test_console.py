"""The operator console covers all ten patterns through one neutral contract.

These tests build fresh agents per case (so approve/reject state does not leak
between tests) and assert the contract every agent must satisfy, plus the
governed-audit chains for the patterns that have one.
"""

import pytest

import serve
from extra_agents import build_extra_agents

# Patterns whose adapter drives a governed client with a hash-chained audit log,
# so a completed approve must leave a verifiable trail (audit_ok is True).
GOVERNED_AUDIT = {"invoice", "procurement", "service", "salesorder"}

CONTRACT_KEYS = {
    "id", "title", "header", "proposal_title", "columns", "rows", "note",
    "verdict", "verdict_label", "reasons", "status", "actions", "result",
    "audit", "audit_ok",
}


def fresh_agents():
    agents = [serve.InvoicePostingAgent(), serve.TriageAgent(), *build_extra_agents()]
    return {a.agent_id: a for a in agents}


def all_agent_ids():
    return list(fresh_agents().keys())


def test_all_ten_patterns_registered():
    assert len(fresh_agents()) == 10


def test_serve_registers_all_ten():
    # serve.AGENTS is what the HTTP layer serves.
    assert len(serve.AGENTS) == 10


@pytest.mark.parametrize("agent_id", all_agent_ids())
def test_inbox_and_detail_contract(agent_id):
    agent = fresh_agents()[agent_id]
    inbox = agent.inbox()
    assert inbox, f"{agent_id}: empty inbox"
    for item in inbox:
        assert {"id", "primary", "secondary", "status"} <= item.keys()
        detail = agent.detail(item["id"])
        assert CONTRACT_KEYS <= detail.keys(), f"{agent_id}: missing keys"
        assert detail["verdict"] in ("PASS", "FAIL")
        assert isinstance(detail["rows"], list) and detail["rows"]
        assert all(len(r) == len(detail["columns"]) for r in detail["rows"])
        assert isinstance(detail["actions"], list)


@pytest.mark.parametrize("agent_id", all_agent_ids())
def test_reject_is_terminal(agent_id):
    agent = fresh_agents()[agent_id]
    for item in agent.inbox():
        detail = agent.detail(item["id"])
        if any(a["action"] == "reject" and a["enabled"] for a in detail["actions"]):
            after = agent.act("reject", item["id"])
            assert after["status"] == "rejected"
            # a rejected item can no longer be approved
            assert not any(a["action"] == "approve" and a["enabled"] for a in after["actions"])
            return
    pytest.skip(f"{agent_id}: no rejectable item")


@pytest.mark.parametrize("agent_id", all_agent_ids())
def test_approve_completes_and_audit_verifies(agent_id):
    agent = fresh_agents()[agent_id]
    approvable = [it["id"] for it in agent.inbox()
                  if any(a["action"] == "approve" and a["enabled"] for a in agent.detail(it["id"])["actions"])]
    if not approvable:
        pytest.skip(f"{agent_id}: no approvable item")
    for item_id in approvable:
        after = agent.act("approve", item_id)
        assert after["status"] in ("posted", "done")
        assert after["result"], f"{agent_id}/{item_id}: approve left no result text"
        # A completed item must not show a red guard verdict next to its green result.
        assert after["verdict"] == "PASS", f"{agent_id}/{item_id}: FAIL verdict on a completed item"
        if agent_id in GOVERNED_AUDIT:
            assert after["audit"], f"{agent_id}/{item_id}: governed pattern logged nothing"
            assert after["audit_ok"] is True, f"{agent_id}/{item_id}: audit chain did not verify"
        # idempotent: approving again does not change the terminal status
        assert agent.act("approve", item_id)["status"] == after["status"]
