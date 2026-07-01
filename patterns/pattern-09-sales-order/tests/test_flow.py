"""Tests for the whole flow and the governance controls.

These prove the rule of the pattern: a flagged order never reaches the human,
a rejected order is never released, and a clean approved order is released with
a tamper-evident audit trail.
"""

import pytest

from salesorder import (
    GovernedSalesClient,
    MockSalesClient,
    RuleBasedProposer,
    default_config,
    load_requests,
    run_pattern9,
)
from salesorder.errors import NotApprovedError, NotEntitledError


def _client():
    return GovernedSalesClient(
        MockSalesClient(), entitlements={"stage", "release"}
    )


def _run(request_id, approve):
    client = _client()
    result = run_pattern9(
        client,
        RuleBasedProposer(),
        load_requests()[request_id],
        config=default_config(),
        approve=approve,
    )
    return client, result


def test_clean_order_approved_is_released():
    client, result = _run("REQ-1", approve=lambda *a: True)
    assert result.outcome == "released"
    assert result.release_result is not None
    assert result.release_result.order_id.startswith("SO-")


def test_clean_order_rejected_is_not_released():
    client, result = _run("REQ-1", approve=lambda *a: False)
    assert result.outcome == "rejected_by_human"
    assert result.release_result is None


def test_flagged_order_never_reaches_the_human():
    calls = []

    def approve(*args):
        calls.append(args)
        return True

    client, result = _run("REQ-2", approve=approve)
    assert result.outcome == "flagged_by_guard"
    assert calls == []  # the human was never asked
    # Nothing was staged, so the audit shows no stage or release.
    assert all(e.operation not in ("stage", "release") for e in client.audit_log)


def test_release_without_approval_is_blocked():
    client = _client()
    order_request = load_requests()["REQ-1"]
    proposer = RuleBasedProposer()
    from salesorder import price_order

    extracted = proposer.extract(order_request, catalog=client.catalog)
    order = price_order(order_request, extracted, catalog=client.catalog)
    staged = client.stage_order(order)
    # Skip record_approval on purpose. The release-hold must block it.
    with pytest.raises(NotApprovedError):
        client.release_order(staged.staged_id)


def test_missing_entitlement_is_blocked():
    client = GovernedSalesClient(MockSalesClient(), entitlements={"stage"})
    order_request = load_requests()["REQ-1"]
    proposer = RuleBasedProposer()
    from salesorder import price_order

    extracted = proposer.extract(order_request, catalog=client.catalog)
    order = price_order(order_request, extracted, catalog=client.catalog)
    staged = client.stage_order(order)
    client.record_approval(staged.staged_id, approver="sales-manager")
    with pytest.raises(NotEntitledError):
        client.release_order(staged.staged_id)


def test_audit_trail_is_intact_after_a_release():
    client, result = _run("REQ-1", approve=lambda *a: True)
    assert result.outcome == "released"
    assert client.verify_audit() is True
    operations = [e.operation for e in client.audit_log]
    assert operations == ["stage", "approve", "release"]


def test_audit_tampering_is_detected():
    client, _ = _run("REQ-1", approve=lambda *a: True)
    # Tamper with a past entry. The hash chain must no longer verify.
    bad = client.audit_log[0]
    client.audit_log[0] = type(bad)(
        operation="release",  # was "stage"
        target=bad.target,
        outcome=bad.outcome,
        actor=bad.actor,
        entry_hash=bad.entry_hash,
    )
    assert client.verify_audit() is False
