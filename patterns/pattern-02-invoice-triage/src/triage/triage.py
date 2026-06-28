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
from typing import Protocol

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


def build_prompt(document: Document) -> str:
    return (
        "Classify this incoming accounts-payable document.\n\n"
        f"- vendor: {document.vendor}\n"
        f"- currency: {document.currency}\n"
        f"- net: {document.net_amount}\n"
        f"- tax: {document.tax_amount}\n"
        f"- gross: {document.gross_amount}\n\n"
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
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self._complete = complete or self._call_openrouter

    def classify(self, document: Document) -> str:
        raw = self._complete(build_prompt(document)).strip().lower()
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
