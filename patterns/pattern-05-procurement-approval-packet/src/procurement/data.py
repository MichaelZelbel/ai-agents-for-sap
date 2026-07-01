"""Sample data seeded inside the pattern, so it runs with no SAP account.

Three requisitions tell the story:

* REQ-2001 is clean and in policy: approved vendor, under the threshold, a
  contract on file, requester and approver are different people.
* REQ-2002 buys software over the threshold with no contract attached. The
  guard should flag missing docs and the amount.
* REQ-2003 is a segregation-of-duties violation: the requester is also the
  named approver. The guard should catch that even though the amount is small.
"""

from __future__ import annotations

from decimal import Decimal

from .models import Policy, Requisition, Supplier


def seed_suppliers() -> dict[str, Supplier]:
    suppliers = [
        Supplier(
            supplier_id="SUP-100",
            name="Contoso Cloud GmbH",
            country="DE",
            approved_vendor=True,
            risk_rating="low",
        ),
        Supplier(
            supplier_id="SUP-200",
            name="Nimbus Analytics Inc",
            country="US",
            approved_vendor=True,
            risk_rating="medium",
        ),
        Supplier(
            supplier_id="SUP-300",
            name="Bright Office Supplies",
            country="DE",
            approved_vendor=True,
            risk_rating="low",
        ),
    ]
    return {s.supplier_id: s for s in suppliers}


def seed_requisitions() -> dict[str, Requisition]:
    reqs = [
        Requisition(
            request_id="REQ-2001",
            requester="alice",
            approver="bob",
            category="software",
            description="Annual cloud backup subscription renewal",
            amount=Decimal("4200.00"),
            currency="EUR",
            supplier_id="SUP-100",
            attached_documents=("quote", "contract"),
        ),
        Requisition(
            request_id="REQ-2002",
            requester="carol",
            approver="dave",
            category="software",
            description="New analytics platform, enterprise tier",
            amount=Decimal("18000.00"),
            currency="EUR",
            supplier_id="SUP-200",
            attached_documents=("quote",),  # no contract, and it is over the limit
        ),
        Requisition(
            request_id="REQ-2003",
            requester="erin",
            approver="erin",  # same person requests and approves: SoD violation
            category="hardware",
            description="Two standing desks for the team room",
            amount=Decimal("900.00"),
            currency="EUR",
            supplier_id="SUP-300",
            attached_documents=("quote",),
        ),
    ]
    return {r.request_id: r for r in reqs}


def default_policy() -> Policy:
    """The book's example procurement policy. Version is cited everywhere."""
    return Policy(
        policy_id="PROC-POLICY",
        version="2026.2",
        manager_limit=Decimal("5000.00"),
        director_limit=Decimal("25000.00"),
        contract_required_categories=("software", "services"),
    )
