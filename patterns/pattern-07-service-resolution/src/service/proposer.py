"""The proposer: the agent's "propose the next step" step.

This is where the AI reads the gathered context and suggests one next step. Two
proposers ship here, both behind the same `Proposer` interface:

* `RuleBasedProposer` is deterministic and runs offline with no API key. It is
  the default so run_agent.py needs no key, and it is handy for tests. It reads
  the same context a person would and picks the obvious next step.
* `LlmBackedProposer` asks a real model (via OpenRouter) to read the context and
  propose the step. The model only proposes. The deterministic guard still
  decides allow, deny, or needs-approval, and a human still confirms any write,
  so a wrong proposal is caught and never acted on.

The AI never gets a vote on the verdict. It only suggests.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from .models import CaseContext, ProposedStep

VALID_KINDS = {
    "replace_under_warranty",
    "repair_billable",
    "dispatch_technician",
    "reject_claim",
    "escalate",
}


class Proposer(Protocol):
    def propose(self, context: CaseContext) -> ProposedStep:
        """Suggest one next step for a case. Proposes only; acts on nothing."""
        ...


def _first_part_cost(context: CaseContext) -> Decimal:
    """The cost of the first listed part, or zero if the case lists none."""
    if context.parts:
        return context.parts[0].unit_cost
    return Decimal("0.00")


def _first_part_id(context: CaseContext) -> str | None:
    if context.parts:
        return context.parts[0].part_id
    return None


class RuleBasedProposer:
    """Reads the context and picks the obvious next step.

    The customer opened a warranty claim, so the obvious next step is a warranty
    replacement using the first part. This proposer does not second-guess the
    entitlement. It proposes the claim-style step and lets the deterministic guard
    decide whether it is allowed, needs a supervisor, or must be denied. That is
    the point of the pattern: the guard is the leash, not the proposer.
    Deterministic, so tests are stable.
    """

    def propose(self, context: CaseContext) -> ProposedStep:
        return ProposedStep(
            case_id=context.case.case_id,
            kind="replace_under_warranty",
            part_id=_first_part_id(context),
            estimated_cost=_first_part_cost(context),
            rationale=(
                "Customer opened a warranty claim and the symptom matches a covered "
                "failure. Propose replacing the part under warranty."
            ),
        )


# --- Model-backed proposer ---------------------------------------------------

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# A cheap, reliable default. Each proposal costs a fraction of a cent. Never
# required: the rule-based proposer is the default.
DEFAULT_MODEL = "openai/gpt-4o-mini"

_SYSTEM = (
    "You are a careful field-service assistant. You read a service case and its "
    "entitlement, then propose one next step. You only propose. A deterministic "
    "guard decides if the step is allowed, and a human confirms before anything "
    "is done. Reply with JSON only."
)


class ProposerError(RuntimeError):
    """The model returned something we could not turn into a step."""


def _render_examples(examples) -> str:
    """Turn past human declines into worked examples for the prompt: what the case
    looked like, what the agent proposed, and that a human declined it, and why.
    This is how the loop reaches the model, folded in per asset model."""
    if not examples:
        return ""
    blocks = []
    for e in examples:
        lines = [f"- Case: {e.context or '(no summary)'}"]
        if e.proposed:
            lines.append(f"  The agent proposed: {e.proposed}")
        # In this pattern the human decision is confirm or decline, so an override
        # is always a decline: the human refused the staged step.
        lines.append("  A human declined it; it was not carried out.")
        if e.reason:
            lines.append(f"  Reason: {e.reason}")
        blocks.append("\n".join(lines))
    return (
        "Past human corrections and declines for this asset model. Learn from them:\n"
        + "\n".join(blocks) + "\n\n"
    )


def build_prompt(context: CaseContext, examples=None) -> str:
    """The instruction we hand the model. Plain, and it shows the allowed steps.

    `examples` are past human declines for this asset model, folded in as worked
    examples. This is the learning loop for the model path: the agent sees what
    reviewers refused last time and does not repeat it. The deterministic guard
    still checks the result, so an example can only make the proposal better, never
    bypass a rule."""
    ent = context.entitlement
    parts = ", ".join(
        f"{p.part_id} ({p.name}, {'in stock' if p.in_stock else 'out of stock'}, "
        f"{p.unit_cost})"
        for p in context.parts
    ) or "none listed"
    incidents = ", ".join(f"{i.incident_id}: {i.summary}" for i in context.incidents)
    return (
        "Propose the next step for this service case.\n\n"
        "Case:\n"
        f"- case id: {context.case.case_id}\n"
        f"- symptom: {context.case.reported_symptom}\n"
        f"- site: {context.case.site}\n\n"
        "Asset:\n"
        f"- asset id: {context.asset.asset_id}\n"
        f"- model: {context.asset.model}\n\n"
        "Entitlement:\n"
        f"- plan: {ent.plan}\n"
        f"- in warranty: {ent.in_warranty}\n"
        f"- covered sites: {', '.join(sorted(ent.covered_sites))}\n"
        f"- approval limit: {ent.approval_limit}\n"
        f"- expires on: {ent.expires_on}\n\n"
        f"Prior incidents: {incidents or 'none'}\n"
        f"Parts: {parts}\n\n"
        f"{_render_examples(examples)}"
        "Allowed step kinds: replace_under_warranty, repair_billable, "
        "dispatch_technician, reject_claim, escalate.\n\n"
        "Reply with ONLY a JSON object of this shape, no prose:\n"
        '{"kind": "replace_under_warranty", "part_id": "PRT-STATOR", '
        '"estimated_cost": "420.00", "rationale": "why in one sentence"}'
    )


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the JSON object out of the model's reply, code fence or not."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ProposerError(f"model did not return JSON: {text[:200]!r}")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ProposerError(f"model returned invalid JSON: {text[:200]!r}") from exc


def parse_step(raw: str, *, context: CaseContext) -> ProposedStep:
    """Turn the model's JSON reply into a ProposedStep. Structural checks only;
    the entitlement rules are the guard's job."""
    data = _extract_json(raw)
    kind = data.get("kind")
    if kind not in VALID_KINDS:
        raise ProposerError(f"bad step kind in model output: {kind!r}")
    try:
        cost = Decimal(str(data.get("estimated_cost", "0")))
    except InvalidOperation as exc:
        raise ProposerError(f"bad estimated_cost in model output: {data!r}") from exc
    part_id = data.get("part_id")
    return ProposedStep(
        case_id=context.case.case_id,
        kind=kind,
        part_id=str(part_id) if part_id else None,
        estimated_cost=cost,
        rationale=str(data.get("rationale", "")),
    )


class LlmBackedProposer:
    """Asks a model to read the context and propose the step.

    Pass your own `complete` callable to test or to swap providers. By default it
    calls OpenRouter using the OPENROUTER_API_KEY environment variable. It is
    never required: run_agent.py uses the rule-based proposer unless you ask for
    the model.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        complete: Callable[[str], str] | None = None,
        store: Any | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self._complete = complete or self._call_openrouter
        # Optional CorrectionMemory. When set, past declines for this asset model
        # are folded into the prompt so the model learns from them.
        self._store = store

    def propose(self, context: CaseContext) -> ProposedStep:
        # Rank past declines by asset model, with the likely part cost as the
        # amount so similar-cost cases sort first. The step's own cost is not known
        # until the model proposes, so the first part's cost is the best proxy.
        examples = (
            self._store.examples_for(context.asset.model, _first_part_cost(context))
            if self._store
            else None
        )
        raw = self._complete(build_prompt(context, examples=examples))
        return parse_step(raw, context=context)

    def _call_openrouter(self, prompt: str) -> str:
        if not self._api_key:
            raise ProposerError(
                "set OPENROUTER_API_KEY to use the model-backed proposer"
            )
        body = json.dumps(
            {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": prompt},
                ],
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
            raise ProposerError(f"could not reach the model: {exc}") from exc
        return payload["choices"][0]["message"]["content"]
