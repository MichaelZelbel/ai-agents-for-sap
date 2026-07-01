"""Data models for the expense audit pattern.

Money is always a Decimal, never a float. Rounding travel claims with binary
floats is how reimbursements drift by a cent. Every model is a frozen
dataclass so a line, a report, or a policy cannot be mutated after it is read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Mapping

# Where a line ends up after the guard decides.
Route = Literal["fast_approval", "manager", "compliance"]


@dataclass(frozen=True)
class ExpenseLine:
    """One claimed line on an expense report."""

    line_id: str
    category: str
    claimed_amount: Decimal
    receipt_total: Decimal
    date: str  # ISO date, e.g. "2026-06-20"


@dataclass(frozen=True)
class ExpenseReport:
    """A travel and expense report, submitted by one employee."""

    report_id: str
    employee: str
    currency: str
    lines: tuple[ExpenseLine, ...]


@dataclass(frozen=True)
class Policy:
    """The current, versioned expense policy.

    The guard reads this object, never a hard coded rule. Change the policy and
    the same report can route differently. The version travels into the log so
    you can always tell which rules judged a line.
    """

    version: str
    period_start: str  # ISO date, inclusive
    period_end: str  # ISO date, inclusive
    allowed_categories: frozenset[str]
    per_diem_caps: Mapping[str, Decimal]  # category -> max claimed per line
    receipt_required_above: Decimal  # a receipt is required at or above this
    approver_tiers: tuple[tuple[Decimal, str], ...] = ()  # (threshold, approver)
    high_value_threshold: Decimal = Decimal("1000.00")


@dataclass(frozen=True)
class LineVerdict:
    """What the AI drafts for one line: a guess, plus its reasons.

    This is only a draft. The deterministic guard makes the real decision and
    can disagree. The drafter never gets a vote on the outcome.
    """

    line_id: str
    drafted_compliant: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RouteDecision:
    """The guard's real decision for one line, and where it routes."""

    line_id: str
    compliant: bool
    route: Route
    approver: str
    policy_version: str
    failed_checks: tuple[str, ...] = field(default_factory=tuple)
    drafted_compliant: bool | None = None  # what the AI had guessed, for the log
