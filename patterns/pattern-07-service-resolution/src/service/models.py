"""Data models for the service resolution boundary.

Money is always a Decimal, never a float. Warranty caps and repair estimates are
money. Rounding with binary floats is how a cap gets crossed by a cent and nobody
notices. Every model here is a frozen dataclass, so a gathered snapshot cannot be
edited after the fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

# The next step the agent may propose.
StepKind = Literal[
    "replace_under_warranty",
    "repair_billable",
    "dispatch_technician",
    "reject_claim",
    "escalate",
]

# What the deterministic guard decides about a proposed step.
Verdict = Literal["allow", "needs-approval", "deny"]


@dataclass(frozen=True)
class Asset:
    """A serviceable asset, e.g. an industrial motor."""

    asset_id: str
    model: str
    site: str
    installed_on: str  # ISO date, e.g. "2025-01-10"


@dataclass(frozen=True)
class Entitlement:
    """The warranty or contract terms that cover an asset."""

    asset_id: str
    plan: str  # e.g. "standard-warranty"
    in_warranty: bool
    covered_sites: frozenset[str]
    # The most a single covered action may cost before a supervisor must sign off.
    approval_limit: Decimal
    expires_on: str  # ISO date


@dataclass(frozen=True)
class Incident:
    """One prior incident logged against the asset."""

    incident_id: str
    opened_on: str  # ISO date
    summary: str


@dataclass(frozen=True)
class Part:
    """A replacement part and whether it is on hand."""

    part_id: str
    name: str
    in_stock: bool
    unit_cost: Decimal


@dataclass(frozen=True)
class ServiceCase:
    """The case a customer opened, before the agent touches it."""

    case_id: str
    asset_id: str
    reported_symptom: str
    site: str


@dataclass(frozen=True)
class CaseContext:
    """Everything the agent gathered for a case. A read-only snapshot."""

    case: ServiceCase
    asset: Asset
    entitlement: Entitlement
    incidents: list[Incident] = field(default_factory=list)
    parts: list[Part] = field(default_factory=list)


@dataclass(frozen=True)
class ProposedStep:
    """A step the agent proposes. Nothing acts until the guard allows and a human
    confirms."""

    case_id: str
    kind: StepKind
    part_id: str | None
    estimated_cost: Decimal
    rationale: str


@dataclass(frozen=True)
class GuardDecision:
    """The deterministic guard's verdict on a proposed step, with a short reason."""

    verdict: Verdict
    reason: str


@dataclass(frozen=True)
class StagedAction:
    """A step held at the boundary, waiting for one-click human confirmation."""

    staged_id: str
    step: ProposedStep
    status: str = "staged"


@dataclass(frozen=True)
class ActionResult:
    """The result of a confirmed (executed) step."""

    action_id: str
    case_id: str
    status: str = "done"
