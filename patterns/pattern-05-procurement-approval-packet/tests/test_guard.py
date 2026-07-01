"""Tests for the deterministic guard. No AI, no network, no key.

The guard is the leash. These prove it passes a clean, in-policy request and
rejects the out-of-policy ones: missing contract over the threshold, and a
segregation-of-duties violation.
"""

from decimal import Decimal

from procurement import (
    default_guard_config,
    default_policy,
    run_guard,
    seed_requisitions,
    seed_suppliers,
)


def _lookup(request_id):
    reqs = seed_requisitions()
    sups = seed_suppliers()
    req = reqs[request_id]
    return req, sups[req.supplier_id], default_policy()


def test_clean_request_routes_to_auto_review():
    req, sup, policy = _lookup("REQ-2001")
    result = run_guard(req, sup, policy, config=default_guard_config())
    assert result.route == "auto_review"
    assert result.flags == ()
    assert result.policy_version == "2026.2"


def test_missing_contract_over_threshold_is_blocked():
    req, sup, policy = _lookup("REQ-2002")
    result = run_guard(req, sup, policy, config=default_guard_config())
    # A missing required document blocks; it cannot proceed as is.
    assert result.route == "blocked_missing_docs"
    joined = " ".join(result.flags)
    assert "requires a contract" in joined
    assert "exceeds the manager limit" in joined


def test_segregation_of_duties_violation_escalates():
    req, sup, policy = _lookup("REQ-2003")
    result = run_guard(req, sup, policy, config=default_guard_config())
    assert result.route == "escalation"
    assert any("Segregation of duties" in flag for flag in result.flags)


def test_over_threshold_alone_escalates():
    # Same clean request, but nudged just over the manager limit with a
    # contract still attached. Over the threshold escalates, not blocks.
    req, sup, policy = _lookup("REQ-2001")
    over = req.__class__(
        request_id=req.request_id,
        requester=req.requester,
        approver=req.approver,
        category=req.category,
        description=req.description,
        amount=Decimal("6000.00"),
        currency=req.currency,
        supplier_id=req.supplier_id,
        attached_documents=req.attached_documents,
    )
    result = run_guard(over, sup, policy, config=default_guard_config())
    assert result.route == "escalation"
    assert any("exceeds the manager limit" in flag for flag in result.flags)
