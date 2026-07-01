"""The narrator: the agent's "draft" step.

This is where the AI reads the enriched requisition and drafts two things: a
short risk narrative and a recommendation. It only drafts. It gets no vote on
the outcome. The deterministic guard decides, and a human approves. So a wrong
or over-confident draft cannot approve anything.

Two narrators ship here, both behind the same `Narrator` interface:

* `RuleBasedNarrator` is deterministic and runs offline with no API key. It is
  the default, so the CLI and the tests work with no model and no network.
* `LlmBackedNarrator` asks a real model (via OpenRouter) to write the narrative.
  Pass your own `complete` callable to test it offline, exactly as the model is
  injected in Pattern 1.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from .models import Policy, Requisition, Supplier


@dataclass(frozen=True)
class RiskDraft:
    """What the AI produces: a narrative and a recommendation. Advisory only."""

    narrative: str
    recommendation: str


class Narrator(Protocol):
    def draft(
        self, requisition: Requisition, supplier: Supplier, policy: Policy
    ) -> RiskDraft:
        """Draft a risk narrative and a recommendation. Drafts only; decides nothing."""
        ...


def _observations(
    requisition: Requisition, supplier: Supplier, policy: Policy
) -> list[str]:
    """Plain facts both narrators lean on. Facts, not decisions."""
    notes: list[str] = []
    notes.append(
        f"Supplier {supplier.name} ({supplier.country}) has a "
        f"{supplier.risk_rating} risk rating."
    )
    notes.append(
        "Supplier is on the approved vendor list."
        if supplier.approved_vendor
        else "Supplier is NOT on the approved vendor list."
    )
    if requisition.amount > policy.manager_limit:
        notes.append(
            f"Amount {requisition.amount} {requisition.currency} is above the "
            f"manager limit of {policy.manager_limit}."
        )
    else:
        notes.append(
            f"Amount {requisition.amount} {requisition.currency} is within the "
            f"manager limit of {policy.manager_limit}."
        )
    if (
        requisition.category in policy.contract_required_categories
        and "contract" not in requisition.attached_documents
    ):
        notes.append(
            f"Category '{requisition.category}' requires a contract, but none is "
            "attached."
        )
    return notes


class RuleBasedNarrator:
    """Writes a plain narrative from the observations. Deterministic, offline.

    It reads like something a careful analyst would jot down. It never claims
    the request is approved, because approval is not its job.
    """

    def draft(
        self, requisition: Requisition, supplier: Supplier, policy: Policy
    ) -> RiskDraft:
        notes = _observations(requisition, supplier, policy)
        narrative = " ".join(notes)
        # The recommendation is a suggestion for the human, never a decision.
        higher_risk = (
            supplier.risk_rating == "high"
            or not supplier.approved_vendor
            or requisition.amount > policy.manager_limit
        )
        if higher_risk:
            recommendation = (
                "Suggest a closer review before approval. See the guard flags "
                "for the binding checks."
            )
        else:
            recommendation = (
                "Looks routine on the face of it. The guard flags are the "
                "binding checks; defer to them."
            )
        return RiskDraft(narrative=narrative, recommendation=recommendation)


# --- Model-backed narrator ---------------------------------------------------

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# A cheap, reliable default. Each draft costs a fraction of a cent. Free models
# (ids ending ":free") also work but are heavily rate-limited.
DEFAULT_MODEL = "openai/gpt-4o-mini"

_SYSTEM = (
    "You are a careful procurement analyst. You read an enriched purchase "
    "requisition and draft a short risk narrative and a recommendation. You "
    "only draft: a deterministic guard decides and a human approves before "
    "anything happens. Do not claim the request is approved. Reply with JSON only."
)


class NarratorError(RuntimeError):
    """The model returned something we could not turn into a draft."""


def build_prompt(
    requisition: Requisition, supplier: Supplier, policy: Policy
) -> str:
    """The instruction we hand the model. Plain, and it shows the facts."""
    docs = ", ".join(requisition.attached_documents) or "none"
    facts = "\n".join(f"- {note}" for note in _observations(requisition, supplier, policy))
    return (
        "Draft a risk narrative and a recommendation for this purchase "
        "requisition.\n\n"
        "Requisition:\n"
        f"- id: {requisition.request_id}\n"
        f"- requester: {requisition.requester}\n"
        f"- named approver: {requisition.approver}\n"
        f"- category: {requisition.category}\n"
        f"- description: {requisition.description}\n"
        f"- amount: {requisition.amount} {requisition.currency}\n"
        f"- attached documents: {docs}\n\n"
        f"Policy {policy.policy_id} version {policy.version}. Manager limit "
        f"{policy.manager_limit}. Contract required for categories: "
        f"{', '.join(policy.contract_required_categories)}.\n\n"
        "Observations:\n"
        f"{facts}\n\n"
        "Reply with ONLY a JSON object of this shape, no prose:\n"
        '{"narrative": "short paragraph", "recommendation": "one or two sentences"}'
    )


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the JSON object out of the model's reply, code fence or not."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise NarratorError(f"model did not return JSON: {text[:200]!r}")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise NarratorError(f"model returned invalid JSON: {text[:200]!r}") from exc


def parse_draft(raw: str) -> RiskDraft:
    """Turn the model's JSON reply into a RiskDraft. Structural checks only;
    the business rules are the guard's job."""
    data = _extract_json(raw)
    narrative = data.get("narrative")
    recommendation = data.get("recommendation")
    if not isinstance(narrative, str) or not narrative.strip():
        raise NarratorError(f"model gave no narrative: {raw[:200]!r}")
    if not isinstance(recommendation, str) or not recommendation.strip():
        raise NarratorError(f"model gave no recommendation: {raw[:200]!r}")
    return RiskDraft(narrative=narrative.strip(), recommendation=recommendation.strip())


class LlmBackedNarrator:
    """Asks a model to write the narrative and the recommendation.

    Pass your own `complete` callable to test or to swap providers. By default it
    calls OpenRouter using the OPENROUTER_API_KEY environment variable.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        complete: Callable[[str], str] | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self._complete = complete or self._call_openrouter

    def draft(
        self, requisition: Requisition, supplier: Supplier, policy: Policy
    ) -> RiskDraft:
        raw = self._complete(build_prompt(requisition, supplier, policy))
        return parse_draft(raw)

    def _call_openrouter(self, prompt: str) -> str:
        if not self._api_key:
            raise NarratorError(
                "set OPENROUTER_API_KEY to use the model-backed narrator"
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
            raise NarratorError(f"could not reach the model: {exc}") from exc
        return payload["choices"][0]["message"]["content"]
