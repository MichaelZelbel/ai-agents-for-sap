"""Domain models for the procurement approval packet.

Money is always a Decimal, never a float. A purchase threshold compared with a
binary float is how a spend limit quietly leaks. Every model is a frozen
dataclass, so a packet you built cannot be mutated behind your back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class Supplier:
    """A supplier profile. Thin on purpose, like a real master-data record."""

    supplier_id: str
    name: str
    country: str
    approved_vendor: bool  # is this supplier on the approved vendor list
    risk_rating: str  # "low", "medium", or "high", from the vendor screen


@dataclass(frozen=True)
class Requisition:
    """A purchase requisition. It arrives thin: the agent enriches it, never
    changes it. The record here is read only, the source of truth."""

    request_id: str
    requester: str
    approver: str  # the person asked to sign off
    category: str  # e.g. "software", "hardware", "services"
    description: str
    amount: Decimal
    currency: str
    supplier_id: str
    # ids of documents attached to the request, e.g. "contract", "quote".
    attached_documents: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Policy:
    """A procurement policy, with its version. We cite the version in the packet
    and in the log, so a later policy change never rewrites what was decided."""

    policy_id: str
    version: str  # e.g. "2026.2". Cited in the packet and the audit log.
    # spend thresholds per approval tier, in the policy currency.
    manager_limit: Decimal
    director_limit: Decimal
    # categories that require a signed contract on file before approval.
    contract_required_categories: tuple[str, ...]


@dataclass(frozen=True)
class Packet:
    """The assembled approval packet. This is the primary artifact.

    It is staged for a human. It does NOT change the requisition record. It
    carries the enriched view, the policy citation, the AI-drafted narrative,
    the deterministic flags, and where the guard routed the request.
    """

    request_id: str
    requisition: Requisition
    supplier: Supplier
    policy_id: str
    policy_version: str
    risk_narrative: str  # drafted by the AI. Advisory only.
    recommendation: str  # drafted by the AI. Advisory only.
    flags: tuple[str, ...]  # from the deterministic guard. These decide.
    route: str  # "auto_review", "escalation", or "blocked_missing_docs".
    status: str = "staged"
