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
from typing import Protocol

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"

CATEGORIES = ("duplicate", "short_payment", "price", "not_received", "other")


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


def build_prompt(dispute: Dispute) -> str:
    return (
        "A vendor has raised a dispute about a payment. Read it, classify it, and "
        "draft a short, polite reply for a human to review.\n\n"
        f"Vendor: {dispute.vendor}\n"
        f"Message: {dispute.message}\n\n"
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


class LlmDisputeAssistant:
    """Reads a dispute and proposes a category and a draft reply. Inject `complete`
    to test; by default it calls OpenRouter using OPENROUTER_API_KEY."""

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

    def assess(self, dispute: Dispute) -> Assessment:
        return parse_assessment(self._complete(build_prompt(dispute)))

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
