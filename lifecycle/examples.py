"""A fleet of agents caught at different points in their lives, so the gate has
something to rule on. Each ties to a pattern from the book."""

from __future__ import annotations

from .models import AgentManifest, AgentMetrics

FLEET: list[tuple[AgentManifest, AgentMetrics]] = [
    # Running well at draft-first for two months: ready to earn a narrow autonomy.
    (
        AgentManifest(
            name="invoice-posting",
            purpose="Post clean vendor invoices to draft, human approves.",
            autonomy="draft_first",
            prompt_version="v4",
            model="openai/gpt-4o-mini",
            owner_process="Elena (AP lead)",
            owner_agent="Raj (platform)",
            owner_control="Internal Audit",
            owner_ops="Run team",
        ),
        AgentMetrics(weeks_at_level=9, override_rate=0.02, audit_clean=True, exceptions_per_week=6, monthly_uses=3200),
    ),
    # New but healthy at suggest-only: ready to start staging drafts.
    (
        AgentManifest(
            name="expense-audit",
            purpose="Flag expense-policy violations for a human auditor.",
            autonomy="suggest_only",
            prompt_version="v2",
            model="openai/gpt-4o-mini",
            owner_process="T&E manager",
            owner_agent="Raj (platform)",
            owner_control="Internal Audit",
            owner_ops="Run team",
        ),
        AgentMetrics(weeks_at_level=6, override_rate=0.03, audit_clean=True, exceptions_per_week=4, monthly_uses=900),
    ),
    # Rejected too often: not a promotion case, a calibration case.
    (
        AgentManifest(
            name="dispute-copilot",
            purpose="Draft replies to vendor disputes for a human to send.",
            autonomy="suggest_only",
            prompt_version="v1",
            model="openai/gpt-4o-mini",
            owner_process="AP disputes",
            owner_agent="Raj (platform)",
            owner_control="Internal Audit",
            owner_ops="Run team",
        ),
        AgentMetrics(weeks_at_level=5, override_rate=0.24, audit_clean=True, exceptions_per_week=10, monthly_uses=400),
    ),
    # Only two weeks at its rung: hold, keep gathering evidence.
    (
        AgentManifest(
            name="three-way-match",
            purpose="Match PO, goods receipt, and invoice before posting.",
            autonomy="draft_first",
            prompt_version="v3",
            model="openai/gpt-4o-mini",
            owner_process="Procurement ops",
            owner_agent="Raj (platform)",
            owner_control="Internal Audit",
            owner_ops="Run team",
        ),
        AgentMetrics(weeks_at_level=2, override_rate=0.03, audit_clean=True, exceptions_per_week=5, monthly_uses=1500),
    ),
    # Barely used after seven months: dead wood, retire it.
    (
        AgentManifest(
            name="legacy-dispute-router",
            purpose="Route disputes by a bespoke rule (superseded).",
            autonomy="bounded_auto",
            prompt_version="v1",
            model="openai/gpt-4o-mini",
            owner_process="(unassigned)",
            owner_agent="(left the company)",
            owner_control="Internal Audit",
            owner_ops="Run team",
        ),
        AgentMetrics(weeks_at_level=30, override_rate=0.01, audit_clean=True, exceptions_per_week=1, monthly_uses=8),
    ),
    # A standard capability now covers the job: retire and move to standard.
    (
        AgentManifest(
            name="cash-application",
            purpose="Match incoming payments to open receivables.",
            autonomy="draft_first",
            prompt_version="v2",
            model="openai/gpt-4o-mini",
            owner_process="AR lead",
            owner_agent="Raj (platform)",
            owner_control="Internal Audit",
            owner_ops="Run team",
            standard_now_covers=True,
        ),
        AgentMetrics(weeks_at_level=20, override_rate=0.04, audit_clean=True, exceptions_per_week=7, monthly_uses=2600),
    ),
]
