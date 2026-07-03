"""The Pattern 2 flow: tie the triage steps together.

    read -> classify -> route (deterministic guard) -> (human confirms) -> hand off

The rule of the pattern lives in `route()`: a label the router does not know is
refused, so a stray answer from the model can never send a document down the wrong
path. Here we add the human in the loop and the learning loop around it.

The human confirms the routing or rejects it. When they reject, the reason they
type is the signal the loop reads: it is remembered per vendor and folded into the
next document from that vendor, so the classifier does not repeat the mistake. A
reviewer can also *correct* the routing (name the category it should have been),
which is remembered the same way. Nothing is learned that lets a bad label bypass
the router.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Union

from learning import Correction, CorrectionMemory
from sap_client import Document

from .triage import Triager, route

# The default identity to attribute a decision to when a caller only says yes/no.
DEFAULT_REVIEWER = "a.schmidt@nordwind"


@dataclass(frozen=True)
class HumanDecision:
    """What a person decided about a proposed routing, and why.

    The rationale is the point. When a reviewer rejects or corrects a routing, the
    reason they type is the signal the learning loop reads to improve the classifier.

    Setting `corrected_category` means "reject this label, it should have been this
    one instead." That is remembered per vendor like a rejection, but it also tells
    the loop what the right answer was.
    """

    confirmed: bool
    reviewer: str = DEFAULT_REVIEWER
    rationale: str = ""
    corrected_category: str = ""


# Called to get a human decision. May return a HumanDecision (who, and why), or a
# bare bool (True to confirm, False to reject) when the caller has nothing to add.
Confirm = Callable[[Document, str, str], Union[HumanDecision, bool]]


def _as_decision(result: Union[HumanDecision, bool], reviewer: str) -> HumanDecision:
    if isinstance(result, HumanDecision):
        return result
    return HumanDecision(confirmed=bool(result), reviewer=reviewer)


@dataclass(frozen=True)
class TriageResult:
    outcome: str  # "confirmed", "corrected", or "rejected_by_human"
    category: str  # the category the routing was settled on
    next_step: str  # where the router sends it


def run_triage(
    triager: Triager,
    document: Document,
    *,
    confirm: Confirm,
    reviewer: str = DEFAULT_REVIEWER,
    store: Optional[CorrectionMemory] = None,
) -> TriageResult:
    """Read a document, classify it, route it through the deterministic guard, ask a
    human to confirm, and record the decision for the learning loop."""
    category = triager.classify(document)
    next_step = route(category)  # the guard: refuses any label it does not know

    decision = _as_decision(confirm(document, category, next_step), reviewer)

    if decision.confirmed:
        _remember(store, document, "approved", category, next_step, decision, "")
        return TriageResult(outcome="confirmed", category=category, next_step=next_step)

    corrected = decision.corrected_category
    if corrected and corrected != category:
        # The human named the category it should have been. Route the corrected label
        # through the same guard, so even a human's edit must be one the router knows.
        new_step = route(corrected)
        change = f"category {category} -> {corrected}"
        _remember(
            store, document, "corrected", corrected, new_step, decision, change
        )
        return TriageResult(
            outcome="corrected", category=corrected, next_step=new_step
        )

    # A human rejected the routing. Keep the reason: it is what the loop reads.
    _remember(store, document, "rejected", category, next_step, decision, "")
    return TriageResult(
        outcome="rejected_by_human", category=category, next_step=next_step
    )


def _summarize_document(d: Document) -> str:
    return f"net {d.net_amount}, tax {d.tax_amount}, gross {d.gross_amount} {d.currency}"


def _remember(
    store: Optional[CorrectionMemory],
    document: Document,
    kind: str,
    category: str,
    next_step: str,
    decision: HumanDecision,
    correction: str,
) -> None:
    """Record the decision as a teachable example: the document, the category and
    destination the agent proposed, and what the human did about it. That is what the
    loop learns from, and it feeds the override rate. There is no deterministic
    learned field for this pattern, so `fields` stays empty."""
    if store is None:
        return
    store.record(
        Correction(
            entity=document.vendor,
            item_id=document.doc_id,
            decision=kind,
            reason=decision.rationale,
            context=_summarize_document(document),
            proposed=f"{category} -> {next_step}",
            correction=correction,
            amount=str(document.gross_amount),
            fields={},
        )
    )
