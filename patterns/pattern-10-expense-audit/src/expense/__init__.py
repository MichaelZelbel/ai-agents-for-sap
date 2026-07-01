"""Pattern 10: Expense Report Audit with Policy Guardrails.

An agent drafts a per line verdict on a travel and expense report. A
deterministic guard makes the real decision against the current, versioned
policy. Compliant lines go to fast approval. A failed check routes to the
manager. A repeat or high value violation escalates to compliance. A human
approves exceptions, and the log records which policy version was applied.
"""

from .models import (
    ExpenseLine,
    ExpenseReport,
    LineVerdict,
    Policy,
    RouteDecision,
)
from .auditor import (
    AuditResult,
    LlmBackedDrafter,
    RuleBasedDrafter,
    audit_report,
    default_policy,
    guard_line,
    route_line,
)

__all__ = [
    "ExpenseLine",
    "ExpenseReport",
    "Policy",
    "LineVerdict",
    "RouteDecision",
    "AuditResult",
    "RuleBasedDrafter",
    "LlmBackedDrafter",
    "default_policy",
    "guard_line",
    "route_line",
    "audit_report",
]
