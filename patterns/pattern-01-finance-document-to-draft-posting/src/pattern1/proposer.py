"""The proposer: the agent's "propose" step.

This is where the AI reads a document and suggests a posting. Two proposers
ship here, both behind the same `Proposer` interface:

* `RuleBasedProposer` is deterministic and runs offline with no API key. It is
  handy for tests and for seeing the flow without a model.
* `LlmBackedProposer` asks a real model (via OpenRouter) to read the invoice
  and propose the posting. The model only proposes; validate, approve, and
  write are unchanged, so a wrong proposal is caught by the deterministic
  validator and never booked.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from sap_client import Document, PostingLine, ProposedPosting

EXPENSE_ACCOUNT = "600000"
INPUT_TAX_ACCOUNT = "154000"
PAYABLE_ACCOUNT = "160000"


class Proposer(Protocol):
    def propose(self, document: Document, *, posting_date: str) -> ProposedPosting:
        """Suggest a posting for a document. Proposes only; books nothing."""
        ...


class RuleBasedProposer:
    """Maps a vendor invoice to the standard three-line posting.

    Debit expense (net) + debit input tax (tax), credit accounts payable
    (gross). Deterministic, so it always proposes a balanced posting.
    """

    def propose(self, document: Document, *, posting_date: str) -> ProposedPosting:
        return ProposedPosting(
            doc_id=document.doc_id,
            posting_date=posting_date,
            currency=document.currency,
            lines=[
                PostingLine(EXPENSE_ACCOUNT, "debit", document.net_amount),
                PostingLine(INPUT_TAX_ACCOUNT, "debit", document.tax_amount),
                PostingLine(PAYABLE_ACCOUNT, "credit", document.gross_amount),
            ],
        )


# --- Model-backed proposer ---------------------------------------------------

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# A cheap, reliable default. Each proposal costs a fraction of a cent. Free
# models (ids ending ":free") also work but are heavily rate-limited.
DEFAULT_MODEL = "openai/gpt-4o-mini"

_SYSTEM = (
    "You are a careful accounts-payable assistant. You read a vendor invoice and "
    "propose the bookkeeping posting. You only propose; a human approves before "
    "anything is booked. Reply with JSON only."
)


class ProposerError(RuntimeError):
    """The model returned something we could not turn into a posting."""


def build_prompt(document: Document, posting_date: str) -> str:
    """The instruction we hand the model. Plain, and it shows the chart of accounts."""
    return (
        "Propose the posting for this vendor invoice.\n\n"
        "Invoice:\n"
        f"- document id: {document.doc_id}\n"
        f"- vendor: {document.vendor}\n"
        f"- currency: {document.currency}\n"
        f"- net amount: {document.net_amount}\n"
        f"- tax amount: {document.tax_amount}\n"
        f"- gross amount: {document.gross_amount}\n\n"
        "Chart of accounts you may use:\n"
        f"- {EXPENSE_ACCOUNT}: expense\n"
        f"- {INPUT_TAX_ACCOUNT}: input tax\n"
        f"- {PAYABLE_ACCOUNT}: accounts payable\n\n"
        "Rules: debit the expense account for the net amount, debit input tax for the "
        "tax amount, and credit accounts payable for the gross amount. Debits must "
        "equal credits.\n\n"
        "Reply with ONLY a JSON object of this shape, no prose:\n"
        '{"lines": [{"account": "600000", "side": "debit", "amount": "1000.00"}]}'
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


def parse_posting(
    raw: str, *, document: Document, posting_date: str
) -> ProposedPosting:
    """Turn the model's JSON reply into a ProposedPosting. Structural checks only;
    the business rules are the validator's job."""
    data = _extract_json(raw)
    lines: list[PostingLine] = []
    for item in data.get("lines", []):
        side = item.get("side")
        if side not in ("debit", "credit"):
            raise ProposerError(f"bad side in model output: {item!r}")
        try:
            amount = Decimal(str(item["amount"]))
        except (KeyError, InvalidOperation) as exc:
            raise ProposerError(f"bad amount in model output: {item!r}") from exc
        lines.append(PostingLine(str(item.get("account", "")), side, amount))
    if not lines:
        raise ProposerError("model proposed no lines")
    return ProposedPosting(
        doc_id=document.doc_id,
        posting_date=posting_date,
        currency=document.currency,
        lines=lines,
    )


class LlmBackedProposer:
    """Asks a model to read the invoice and propose the posting.

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

    def propose(self, document: Document, *, posting_date: str) -> ProposedPosting:
        raw = self._complete(build_prompt(document, posting_date))
        return parse_posting(raw, document=document, posting_date=posting_date)

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
