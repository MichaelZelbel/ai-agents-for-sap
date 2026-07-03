"""The Pattern 3 flow: tie the steps together.

    match (AI) -> guard (arithmetic) -> (human releases or holds)

The rule of the pattern lives here: if the guard fails, the invoice is held and a
human is never asked; if the guard passes, a named human decides to release it or
hold it. Every human decision is remembered per vendor, so the matcher learns from
what reviewers held, and the override rate is watched.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Optional, Union

from learning import Correction, CorrectionMemory

from .threeway import Line, MatchResult, invoice_total, three_way_match

# The default identity to attribute a decision to when a caller only says yes/no.
DEFAULT_REVIEWER = "a.schmidt@nordwind"

# The vendor this desk works. This pattern's models (Line) carry no vendor field, so
# the learning loop keys on this one fixed supplier string -- the same one the
# console's Three-Way Match Desk uses.
DEFAULT_VENDOR = "Contoso Office Supplies"


@dataclass(frozen=True)
class HumanDecision:
    """What a person decided about a matched, guard-cleared invoice, and why.

    The rationale is the point. When a reviewer holds an invoice the arithmetic
    passed, the reason they type is the signal the learning loop reads to improve
    the line matcher next time.
    """

    released: bool
    reviewer: str = DEFAULT_REVIEWER
    rationale: str = ""


# Called to get a human decision. May return a HumanDecision (who, and why), or a
# bare bool (True to release, False to hold) when the caller has nothing to add.
Release = Callable[
    [list[Line], list[Line], list[int], MatchResult], Union[HumanDecision, bool]
]


def _as_decision(result: Union[HumanDecision, bool], reviewer: str) -> HumanDecision:
    if isinstance(result, HumanDecision):
        return result
    return HumanDecision(released=bool(result), reviewer=reviewer)


@dataclass(frozen=True)
class FlowResult:
    outcome: str  # "released", "held_by_guard", or "held_by_human"
    match: MatchResult
    mapping: list[int]


def _summarize_documents(invoice: list[Line], po: list[Line]) -> str:
    inv = "; ".join(
        f"{ln.quantity}x {ln.description} @ {ln.unit_price}" for ln in invoice
    )
    return f"invoice [{inv}] vs {len(po)} PO lines, total {invoice_total(invoice)}"


def _summarize_mapping(invoice: list[Line], po: list[Line], mapping: list[int]) -> str:
    parts = []
    for i, j in enumerate(mapping):
        ordered = po[j].description if 0 <= j < len(po) else "(no match)"
        parts.append(f"'{invoice[i].description}' -> '{ordered}'")
    return "; ".join(parts)


def run_threeway(
    matcher,
    invoice: list[Line],
    po: list[Line],
    received: list[Decimal],
    *,
    approve: Release,
    vendor: str = DEFAULT_VENDOR,
    case_id: str = "MATCH",
    tolerance: Decimal = Decimal("0.01"),
    reviewer: str = DEFAULT_REVIEWER,
    store: Optional[CorrectionMemory] = None,
) -> FlowResult:
    mapping = matcher.match(invoice, po, vendor=vendor)
    result = three_way_match(invoice, po, received, mapping, tolerance=tolerance)
    if result.status == "FAIL":
        # The arithmetic did not agree. Hold it; do not ask a human.
        return FlowResult(outcome="held_by_guard", match=result, mapping=mapping)

    decision = _as_decision(approve(invoice, po, mapping, result), reviewer)
    kind = "approved" if decision.released else "rejected"
    _remember(store, vendor, case_id, kind, decision, invoice, po, mapping)
    outcome = "released" if decision.released else "held_by_human"
    return FlowResult(outcome=outcome, match=result, mapping=mapping)


def _remember(
    store: Optional[CorrectionMemory],
    vendor: str,
    case_id: str,
    kind: str,
    decision: HumanDecision,
    invoice: list[Line],
    po: list[Line],
    mapping: list[int],
) -> None:
    """Record the decision as a teachable example: the documents, how the agent
    matched the lines, and what the human did about it. That is what the loop learns
    from, and it feeds the override rate. There is no deterministic learned field for
    this pattern; a line mapping is judgment, not an exact default."""
    if store is None:
        return
    store.record(
        Correction(
            entity=vendor,
            item_id=case_id,
            decision=kind,
            reason=decision.rationale,
            context=_summarize_documents(invoice, po),
            proposed=_summarize_mapping(invoice, po, mapping),
            correction="",
            amount=str(invoice_total(invoice)),
        )
    )
