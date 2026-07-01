"""The matcher: the agent's "propose" step for cash application.

This is where the AI reads an incoming payment, its remittance advice, and the
customer's open invoices, then proposes which invoices the payment clears. Two
matchers ship here, both behind the same interface:

* `RuleBasedMatcher` is deterministic and runs offline with no API key. It
  reads the remittance references and, failing that, searches for a subset of
  open invoices that sum to the payment. It is the default so run_agent.py and
  the tests need no key.
* `LlmBackedMatcher` asks a real model (via OpenRouter) to read the same inputs
  and propose the match. The model only proposes. The deterministic guard still
  decides, a human still approves, so a wrong proposal is caught and never
  clears anything.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from decimal import Decimal
from itertools import combinations
from typing import Any, Protocol

from .models import Invoice, Payment, ProposedMatch


class Matcher(Protocol):
    def propose(
        self, payment: Payment, open_invoices: Sequence[Invoice]
    ) -> ProposedMatch:
        """Propose which invoices a payment clears. Proposes only, clears nothing."""
        ...


class MatcherError(RuntimeError):
    """The matcher could not turn its input or the model reply into a proposal."""


# --- Rule-based matcher ------------------------------------------------------


class RuleBasedMatcher:
    """A deterministic matcher, good enough to drive the flow offline.

    Strategy, in order:

    1. If the remittance advice quotes invoice ids we hold open, use those.
    2. Otherwise, search open invoices for a subset that sums to the payment
       (small sets only, so this stays cheap). Credit notes are negative and
       fall out of the arithmetic naturally.
    3. Otherwise, propose the empty set and let the guard reject it.
    """

    def __init__(self, *, max_combo: int = 4) -> None:
        self._max_combo = max_combo

    def propose(
        self, payment: Payment, open_invoices: Sequence[Invoice]
    ) -> ProposedMatch:
        open_by_id = {inv.invoice_id: inv for inv in open_invoices}

        # 1. Trust the remittance references, if they name invoices we hold.
        quoted = [
            line.reference
            for line in payment.remittance
            if line.reference in open_by_id
        ]
        if quoted:
            return ProposedMatch(
                payment_id=payment.payment_id,
                invoice_ids=tuple(quoted),
                note="Matched on the invoice ids quoted in the remittance advice.",
            )

        # 2. No usable references. Search for a subset that reconciles.
        subset = self._find_reconciling_subset(payment.amount, open_invoices)
        if subset is not None:
            return ProposedMatch(
                payment_id=payment.payment_id,
                invoice_ids=tuple(inv.invoice_id for inv in subset),
                note="No usable remittance. Found open invoices that sum to the payment.",
            )

        # 3. Nothing fits. Propose nothing and let the guard route it.
        return ProposedMatch(
            payment_id=payment.payment_id,
            invoice_ids=(),
            note="Could not find a matching set of open invoices.",
        )

    def _find_reconciling_subset(
        self, target: Decimal, invoices: Sequence[Invoice]
    ) -> list[Invoice] | None:
        for size in range(1, min(self._max_combo, len(invoices)) + 1):
            for combo in combinations(invoices, size):
                if sum((inv.amount for inv in combo), Decimal("0")) == target:
                    return list(combo)
        return None


# --- Model-backed matcher ----------------------------------------------------

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# A cheap, reliable default. Each proposal costs a fraction of a cent. Free
# models (ids ending ":free") also work but are heavily rate-limited.
DEFAULT_MODEL = "openai/gpt-4o-mini"

_SYSTEM = (
    "You are a careful accounts-receivable assistant. You read an incoming "
    "payment, its remittance advice, and the customer's open invoices, then "
    "propose which invoices the payment clears. You only propose. A "
    "deterministic guard checks your work and a human approves before anything "
    "clears. Reply with JSON only."
)


def build_prompt(payment: Payment, open_invoices: Sequence[Invoice]) -> str:
    """The instruction handed to the model. Plain, and it lists the open items."""
    remittance_lines = (
        "\n".join(
            f"  - reference {line.reference}: {line.amount}"
            for line in payment.remittance
        )
        or "  (none provided)"
    )
    invoice_lines = "\n".join(
        f"  - {inv.invoice_id}: {inv.amount} {inv.currency}"
        f"{' (credit note)' if inv.is_credit_note else ''}"
        for inv in open_invoices
    )
    return (
        "Propose which open invoices this incoming payment clears.\n\n"
        "Payment:\n"
        f"- payment id: {payment.payment_id}\n"
        f"- customer: {payment.customer}\n"
        f"- currency: {payment.currency}\n"
        f"- amount: {payment.amount}\n"
        f"- value date: {payment.value_date}\n\n"
        "Remittance advice (may be wrong or missing):\n"
        f"{remittance_lines}\n\n"
        "Open invoices for this customer:\n"
        f"{invoice_lines}\n\n"
        "A credit note is a negative amount. It nets down the matched total.\n"
        "Pick the set of invoice ids whose amounts sum to the payment amount.\n\n"
        "Reply with ONLY a JSON object of this shape, no prose:\n"
        '{"invoice_ids": ["INV-5001", "INV-5002"], "note": "why"}'
    )


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the JSON object out of the model's reply, code fence or not."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise MatcherError(f"model did not return JSON: {text[:200]!r}")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise MatcherError(f"model returned invalid JSON: {text[:200]!r}") from exc


def parse_match(raw: str, *, payment: Payment) -> ProposedMatch:
    """Turn the model's JSON reply into a ProposedMatch. Structural checks only.
    The reconciling arithmetic is the guard's job, not the parser's."""
    data = _extract_json(raw)
    ids = data.get("invoice_ids", [])
    if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids):
        raise MatcherError(f"invoice_ids must be a list of strings: {ids!r}")
    note = data.get("note", "")
    if not isinstance(note, str):
        note = str(note)
    return ProposedMatch(
        payment_id=payment.payment_id,
        invoice_ids=tuple(ids),
        note=note,
    )


class LlmBackedMatcher:
    """Asks a model to read the payment and propose the matching set.

    Pass your own `complete` callable to test or to swap providers. By default
    it calls OpenRouter using the OPENROUTER_API_KEY environment variable. It is
    never required. The rule-based matcher is the default everywhere else.
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

    def propose(
        self, payment: Payment, open_invoices: Sequence[Invoice]
    ) -> ProposedMatch:
        raw = self._complete(build_prompt(payment, open_invoices))
        return parse_match(raw, payment=payment)

    def _call_openrouter(self, prompt: str) -> str:
        if not self._api_key:
            raise MatcherError(
                "set OPENROUTER_API_KEY to use the model-backed matcher"
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
            raise MatcherError(f"could not reach the model: {exc}") from exc
        return payload["choices"][0]["message"]["content"]
