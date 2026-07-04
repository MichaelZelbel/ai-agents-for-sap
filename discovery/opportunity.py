"""The AI-agent opportunity map: which of your processes are the best candidates
for an agent, and which of the book's ten patterns fits each one.

The signal is the same one a process-intelligence tool (SAP Signavio) surfaces and
the same one Chapter 20 teaches: automation pays where high volume meets repetitive,
rule-shaped, manual/rework-heavy work. Low-volume work, however manual, is a poor
candidate, and this says so. Each opportunity is mapped to a pattern in the Part III
catalog so the reader goes straight from "where" to "which shape to build".
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import ObjectRegister, ProcessInfo

# Below this monthly volume, automating a process rarely pays, whatever the manual
# effort per case. It caps the opportunity at "weak".
LOW_VOLUME = 100
HIGH_VOLUME = 1000

# Keyword -> the best-fit catalog pattern and its agent shape. First match wins.
# Shapes are the four from Appendix A / the pro-code skill.
_PATTERN_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("three way match", "three-way", "goods receipt match"), "Pattern 3: Three-Way Match Verification", "match and check"),
    (("cash application", "incoming payment", "bank statement", "remittance"), "Pattern 8: Cash Application", "match and check"),
    (("triage", "route", "classify"), "Pattern 2: Document Triage and Routing", "classify and route"),
    (("dispute",), "Pattern 4: Dispute Resolution Copilot", "suggest only"),
    (("expense", "travel"), "Pattern 10: Expense Report Audit", "suggest only"),
    (("sales order", "order intake", "customer request"), "Pattern 9: Sales Order Proposal", "propose and post"),
    (("procurement", "approval packet", "requisition"), "Pattern 5: Procurement Approval Packet", "propose and post"),
    (("close", "month end", "period close"), "Pattern 6: Close Orchestration", "suggest only"),
    (("service", "resolution", "entitlement"), "Pattern 7: Service Resolution Assist", "suggest only"),
    (("invoice", "posting", "accounts payable", "invoice-to-pay", "p2p"), "Pattern 1: Finance Document-to-Draft Posting", "propose and post"),
)


@dataclass(frozen=True)
class Opportunity:
    process: ProcessInfo
    score: int  # 0..4
    tier: str  # strong / moderate / weak
    pattern: str
    shape: str
    reasons: tuple[str, ...]


def _match_pattern(process: ProcessInfo) -> tuple[str, str]:
    # Match on the process name and area, not its linked objects: an object name like
    # ZCL_DISPUTE_ROUTER would otherwise pull an invoice process toward "routing".
    hay = f"{process.name} {process.area}".lower()
    for keywords, pattern, shape in _PATTERN_RULES:
        if any(k in hay for k in keywords):
            return pattern, shape
    return "no clear catalog pattern; treat as a custom shape", "propose and post"


def opportunity_for(process: ProcessInfo) -> Opportunity:
    reasons: list[str] = []
    volume = process.monthly_volume
    score = 0

    if volume is None:
        reasons.append("volume not measured")
    elif volume >= HIGH_VOLUME:
        score += 2
        reasons.append(f"high volume ({volume}/mo)")
    elif volume >= LOW_VOLUME:
        score += 1
        reasons.append(f"moderate volume ({volume}/mo)")
    else:
        reasons.append(f"low volume ({volume}/mo), so the payoff is limited whatever the effort")

    if process.manual_rework == "high":
        score += 2
        reasons.append("heavily manual / rework-heavy work to hand off")
    elif process.manual_rework == "medium":
        score += 1
        reasons.append("some manual effort to hand off")

    if process.deviation_from_standard:
        reasons.append("rule-shaped: it already runs on firm, written rules")

    low_volume = volume is not None and volume < LOW_VOLUME
    if low_volume:
        tier = "weak"
    elif score >= 3:
        tier = "strong"
    elif score == 2:
        tier = "moderate"
    else:
        tier = "weak"

    pattern, shape = _match_pattern(process)
    return Opportunity(
        process=process, score=score, tier=tier, pattern=pattern, shape=shape,
        reasons=tuple(reasons),
    )


def opportunity_map(register: ObjectRegister) -> list[Opportunity]:
    """Every process scored and ranked, strongest opportunity first."""
    order = {"strong": 0, "moderate": 1, "weak": 2}
    opps = [opportunity_for(p) for p in register.processes]
    opps.sort(key=lambda o: (order.get(o.tier, 3), -o.score, o.process.name))
    return opps


def render_opportunities(opps: list[Opportunity]) -> str:
    lines = ["AI-agent opportunity map (strongest first)", ""]
    for o in opps:
        lines.append(f"  {o.process.name}")
        lines.append(f"        opportunity: {o.tier}   ->   {o.pattern} ({o.shape})")
        for r in o.reasons:
            lines.append(f"        - {r}")
        lines.append("")
    lines.append(
        "Start with the strongest, and build it as the named pattern. Low-volume work "
        "is a weak candidate even when it is manual: automate where the volume is."
    )
    return "\n".join(lines).rstrip() + "\n"
