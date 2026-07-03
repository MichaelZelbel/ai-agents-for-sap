"""Pattern 4: a vendor-dispute assistant, built from scratch.

A vendor writes in: "you only paid 1,070 on invoice INV-1001 but it was for 1,190,
please pay the difference." Someone in accounts payable has to read it, work out what
kind of dispute it is, and write back. This agent helps with that, and it teaches a
different safety level from the others.

The invoice agent could write to SAP, behind approval. This one cannot do anything at
all. It only reads and suggests: it classifies the dispute and drafts a reply. A human
reads the draft and decides whether to send it. That is the lowest, safest rung of
autonomy, suggest-only, and it is the right rung for a job that is all judgement and
words.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional, Protocol, Union

from learning import Correction, CorrectionMemory

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"

CATEGORIES = ("duplicate", "short_payment", "price", "not_received", "other")

# The default identity to attribute a decision to when a caller only says send/discard.
DEFAULT_REVIEWER = "a.schmidt@nordwind"


@dataclass(frozen=True)
class Dispute:
    dispute_id: str
    vendor: str
    message: str


@dataclass(frozen=True)
class Assessment:
    category: str
    reply: str


@dataclass(frozen=True)
class Recommendation:
    """What the agent hands a human: a category, a draft reply, and proof that the
    agent itself did nothing. action_taken is always False; this agent only suggests."""

    category: str
    reply: str
    action_taken: bool = False


class DisputeError(RuntimeError):
    """The model returned something we cannot use as an assessment."""


class DisputeAssistant(Protocol):
    def assess(self, dispute: Dispute) -> Assessment:
        ...


def _render_examples(examples) -> str:
    """Turn past human decisions for this vendor into worked examples for the prompt:
    what the dispute said, what category the agent chose, and what the human did about
    the draft. This is how the loop reaches the model: it sees what reviewers discarded
    (and why) last time and does not repeat the same misread. The guard still checks the
    result, so an example can only make the draft better, never bypass a rule."""
    if not examples:
        return ""
    blocks = []
    for e in examples:
        lines = [f"- Dispute: {e.context or '(no summary)'}"]
        if e.proposed:
            lines.append(f"  The agent classified it as: {e.proposed}")
        if e.decision == "corrected":
            lines.append(f"  A human corrected it: {e.correction or e.reason}")
        else:
            lines.append("  A human rejected the draft, did not send it.")
        if e.reason:
            lines.append(f"  Reason: {e.reason}")
        blocks.append("\n".join(lines))
    return (
        "Past human corrections and rejections for this vendor. Learn from them:\n"
        + "\n".join(blocks)
        + "\n\n"
    )


def build_prompt(dispute: Dispute, examples=None) -> str:
    """The instruction we hand the model.

    `examples` are past human decisions for this vendor (rejections and their reasons),
    folded in as worked examples. This is the learning loop for the model path: the
    agent sees what reviewers discarded last time and does not repeat it. The guard
    (review) still checks the result, so an example can only make the draft better."""
    return (
        "A vendor has raised a dispute about a payment. Read it, classify it, and "
        "draft a short, polite reply for a human to review.\n\n"
        f"Vendor: {dispute.vendor}\n"
        f"Message: {dispute.message}\n\n"
        f"{_render_examples(examples)}"
        "Category must be exactly one of: " + ", ".join(CATEGORIES) + ".\n"
        "Reply with ONLY JSON of this shape:\n"
        '{"category": "short_payment", "reply": "Dear ..., thank you for ..."}'
    )


def parse_assessment(raw: str) -> Assessment:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise DisputeError(f"model did not return JSON: {raw[:160]!r}")
    try:
        data = json.loads(raw[start : end + 1])
        return Assessment(category=str(data["category"]), reply=str(data["reply"]))
    except (json.JSONDecodeError, KeyError) as exc:
        raise DisputeError(f"bad assessment from model: {raw[:160]!r}") from exc


def review(assessment: Assessment) -> Recommendation:
    """The guard. The category must be one we recognise and the reply must not be
    empty. The agent takes no action; it returns a draft for a human to send."""
    if assessment.category not in CATEGORIES:
        raise DisputeError(f"unknown category: {assessment.category!r}")
    if not assessment.reply.strip():
        raise DisputeError("the draft reply is empty")
    return Recommendation(category=assessment.category, reply=assessment.reply)


# --- the flow: assess -> review (guard) -> human decides -> remember ---------- #


@dataclass(frozen=True)
class HumanDecision:
    """What a person decided about a drafted reply, and why.

    This pattern is suggest-only, so the human decision is not approve-then-post but
    send-the-draft or discard-it. `sent=True` means the reviewer marked the draft sent
    (an approval of the agent's read); `sent=False` means they discarded it (a rejection).
    A discard's reason is the learning signal: it is what the loop reads to improve the
    next classification for this vendor. The agent itself still takes no action."""

    sent: bool
    reviewer: str = DEFAULT_REVIEWER
    reason: str = ""


# Called to get a human decision. May return a HumanDecision (who, and why), or a bare
# bool (True to send the draft, False to discard it) when the caller has nothing to add.
Decide = Callable[[Dispute, Recommendation], Union["HumanDecision", bool]]


def _as_decision(result: Union[HumanDecision, bool], reviewer: str) -> HumanDecision:
    if isinstance(result, HumanDecision):
        return result
    return HumanDecision(sent=bool(result), reviewer=reviewer)


@dataclass(frozen=True)
class DisputeResult:
    outcome: str  # "sent" or "discarded" (what the human did with the draft)
    recommendation: Recommendation


def _summarize_dispute(d: Dispute) -> str:
    msg = d.message.strip().replace("\n", " ")
    if len(msg) > 160:
        msg = msg[:157] + "..."
    return f"from {d.vendor}: {msg}"


def _remember(
    store: Optional[CorrectionMemory],
    dispute: Dispute,
    recommendation: Recommendation,
    kind: str,
    decision: HumanDecision,
) -> None:
    """Record the human decision as a teachable example: what the dispute said, what
    category the agent chose, and what the human did with the draft. A discard's reason
    is the signal the loop learns from, and every decision feeds the override rate."""
    if store is None:
        return
    store.record(
        Correction(
            entity=dispute.vendor,
            item_id=dispute.dispute_id,
            decision=kind,
            reason=decision.reason,
            context=_summarize_dispute(dispute),
            proposed=recommendation.category,
            correction="",
            amount="",
        )
    )


def run_dispute(
    assistant: "DisputeAssistant",
    dispute: Dispute,
    *,
    decide: Decide,
    reviewer: str = DEFAULT_REVIEWER,
    store: Optional[CorrectionMemory] = None,
) -> DisputeResult:
    """Tie the suggest-only flow together: the agent classifies and drafts, the guard
    checks, a human marks the draft sent or discards it, and the move is remembered.

    The agent still takes no action. `run_dispute` records the human's decision for the
    learning loop; sending the reply, if it happens, is the human's doing, not the agent's."""
    recommendation = review(assistant.assess(dispute))
    decision = _as_decision(decide(dispute, recommendation), reviewer)
    kind = "approved" if decision.sent else "rejected"
    _remember(store, dispute, recommendation, kind, decision)
    return DisputeResult(
        outcome="sent" if decision.sent else "discarded",
        recommendation=recommendation,
    )


class LlmDisputeAssistant:
    """Reads a dispute and proposes a category and a draft reply. Inject `complete`
    to test; by default it calls OpenRouter using OPENROUTER_API_KEY."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        complete: Callable[[str], str] | None = None,
        store: Optional[CorrectionMemory] = None,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self._complete = complete or self._call_openrouter
        # Optional CorrectionMemory. When set, past decisions for the vendor are
        # folded into the prompt so the model learns from them.
        self._store = store

    def assess(self, dispute: Dispute) -> Assessment:
        examples = self._store.examples_for(dispute.vendor) if self._store else None
        return parse_assessment(self._complete(build_prompt(dispute, examples=examples)))

    def _call_openrouter(self, prompt: str) -> str:
        if not self._api_key:
            raise DisputeError("set OPENROUTER_API_KEY to use the model-backed assistant")
        body = json.dumps(
            {
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            OPENROUTER_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise DisputeError(f"could not reach the model: {exc}") from exc
        return payload["choices"][0]["message"]["content"]
