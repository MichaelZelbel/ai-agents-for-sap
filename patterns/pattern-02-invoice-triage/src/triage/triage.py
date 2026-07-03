"""Pattern 2: the "triage" box from the accounts-payable flow.

An incoming document arrives. The AI reads it and classifies it into one of a few
known categories. A deterministic router turns that label into the next step, and
refuses any label it does not recognise, so a stray answer from the model can never
send a document down the wrong path.

Same shape as Pattern 1: the model proposes (here, a category), firm rules guard it.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any, Protocol

from sap_client import Document

CATEGORIES = ("po_invoice", "direct_expense", "not_an_invoice")

ROUTES = {
    "po_invoice": "three-way match",
    "direct_expense": "post directly",
    "not_an_invoice": "send to a person",
}

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"


class TriageError(RuntimeError):
    """The model returned a category we do not recognise."""


class Triager(Protocol):
    def classify(self, document: Document) -> str:
        """Return one of CATEGORIES for a document."""
        ...


def route(category: str) -> str:
    """The deterministic guard. A known category maps to its next step; anything
    else is refused, so a bad label cannot route a document somewhere wrong."""
    if category not in ROUTES:
        raise TriageError(f"unknown category: {category!r}")
    return ROUTES[category]


def _render_examples(examples) -> str:
    """Turn past human overrides for this vendor into worked examples for the prompt:
    what came in, what the agent proposed, and that a human corrected or rejected the
    routing, with their reason. This is how the loop reaches the model: it sees where
    it misclassified this vendor last time and does not repeat it. The deterministic
    router still refuses any label it does not know, so an example can only make the
    category better, never bypass the guard."""
    if not examples:
        return ""
    blocks = []
    for e in examples:
        lines = [f"- Document: {e.context or '(no summary)'}"]
        if e.proposed:
            lines.append(f"  The agent proposed: {e.proposed}")
        if e.decision == "corrected":
            lines.append(f"  A human corrected it: {e.correction or e.reason}")
        else:
            lines.append("  A human rejected that routing.")
        if e.reason:
            lines.append(f"  Reason: {e.reason}")
        blocks.append("\n".join(lines))
    return (
        "Past human corrections and rejections for this vendor. Learn from them and "
        "do not repeat the same mistake:\n" + "\n".join(blocks) + "\n\n"
    )


def build_prompt(document: Document, examples=None) -> str:
    """The instruction we hand the model.

    `examples` are past human overrides for this vendor (corrections and rejections),
    folded in as worked examples so the classifier learns from what reviewers changed
    last time. The router still guards the result, so an example only sharpens the
    category, it never bypasses a rule."""
    return (
        "Classify this incoming accounts-payable document.\n\n"
        f"- vendor: {document.vendor}\n"
        f"- currency: {document.currency}\n"
        f"- net: {document.net_amount}\n"
        f"- tax: {document.tax_amount}\n"
        f"- gross: {document.gross_amount}\n\n"
        f"{_render_examples(examples)}"
        "Reply with ONE word, exactly one of: " + ", ".join(CATEGORIES) + ".\n"
        "po_invoice = a vendor invoice that references a purchase order; "
        "direct_expense = a small invoice with no purchase order; "
        "not_an_invoice = anything that is not an invoice."
    )


class LlmTriager:
    """Asks a model to classify the document. Pass `complete` to test or swap
    providers; by default it calls OpenRouter using OPENROUTER_API_KEY."""

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
        # Optional CorrectionMemory. When set, past corrections and rejections for the
        # vendor are folded into the prompt so the classifier learns from them.
        self._store = store

    def classify(self, document: Document) -> str:
        examples = (
            self._store.examples_for(document.vendor, document.gross_amount)
            if self._store
            else None
        )
        raw = self._complete(build_prompt(document, examples=examples)).strip().lower()
        for category in CATEGORIES:
            if category in raw:
                return category
        raise TriageError(f"model did not return a known category: {raw[:120]!r}")

    def _call_openrouter(self, prompt: str) -> str:
        if not self._api_key:
            raise TriageError("set OPENROUTER_API_KEY to use the model-backed triager")
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
            raise TriageError(f"could not reach the model: {exc}") from exc
        return payload["choices"][0]["message"]["content"]
