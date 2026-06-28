"""Pattern 3: the three-way match.

Before an invoice is allowed through, it must agree with two other documents:

* the purchase order  -- did we order this, at this price and quantity?
* the goods receipt   -- did we actually receive it?

The hard part is lining the invoice up against the purchase order, because the same
item is worded differently on each ("Ergonomic office chair" vs "Office chairs,
ergonomic"). That matching is a real job for the model. The checking that follows,
quantities and money agreeing within tolerance, is firm arithmetic, and that stays
deterministic. AI to match, rules to decide.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"


@dataclass(frozen=True)
class Line:
    description: str
    quantity: Decimal
    unit_price: Decimal


@dataclass(frozen=True)
class MatchResult:
    status: str  # "PASS" or "FAIL"
    reasons: list[str]


class MatcherError(RuntimeError):
    """The model returned a line mapping we could not use."""


class LineMatcher(Protocol):
    def match(self, invoice: list[Line], po: list[Line]) -> list[int]:
        """For each invoice line, the index of the purchase-order line it matches,
        or -1 if none."""
        ...


def three_way_match(
    invoice: list[Line],
    po: list[Line],
    gr_received: list[Decimal],
    mapping: list[int],
    *,
    tolerance: Decimal = Decimal("0.01"),
) -> MatchResult:
    """The deterministic guard. Given a line mapping (from the model), check that
    every invoice line agrees with its purchase-order line and with what was received."""
    reasons: list[str] = []
    if len(mapping) != len(invoice):
        return MatchResult("FAIL", ["mapping does not cover every invoice line"])
    seen: set[int] = set()
    for i, inv in enumerate(invoice):
        j = mapping[i]
        if j < 0 or j >= len(po):
            reasons.append(f"invoice line '{inv.description}' has no purchase-order line")
            continue
        if j in seen:
            reasons.append(f"two invoice lines matched the same purchase-order line {j}")
        seen.add(j)
        ordered = po[j]
        received = gr_received[j] if j < len(gr_received) else Decimal("0")
        if inv.quantity != ordered.quantity:
            reasons.append(
                f"'{inv.description}': invoice qty {inv.quantity} != ordered {ordered.quantity}"
            )
        if received != inv.quantity:
            reasons.append(
                f"'{inv.description}': received {received} != invoiced {inv.quantity}"
            )
        if abs(inv.unit_price - ordered.unit_price) > tolerance:
            reasons.append(
                f"'{inv.description}': price {inv.unit_price} != ordered {ordered.unit_price}"
            )
    return MatchResult("PASS" if not reasons else "FAIL", reasons)


def build_prompt(invoice: list[Line], po: list[Line]) -> str:
    inv = "\n".join(f"  {i}: {ln.description}" for i, ln in enumerate(invoice))
    ordered = "\n".join(f"  {j}: {ln.description}" for j, ln in enumerate(po))
    return (
        "Match each invoice line to the purchase-order line that means the same item.\n"
        "The wording differs; match on meaning.\n\n"
        f"Invoice lines:\n{inv}\n\n"
        f"Purchase-order lines:\n{ordered}\n\n"
        "Reply with ONLY JSON of this shape, where mapping[i] is the purchase-order "
        "index for invoice line i, or -1 if there is no match:\n"
        '{"mapping": [0, 1]}'
    )


def parse_mapping(raw: str, *, invoice_len: int) -> list[int]:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise MatcherError(f"model did not return JSON: {raw[:160]!r}")
    try:
        data = json.loads(raw[start : end + 1])
        mapping = [int(x) for x in data["mapping"]]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise MatcherError(f"bad mapping from model: {raw[:160]!r}") from exc
    if len(mapping) != invoice_len:
        raise MatcherError("model mapping does not cover every invoice line")
    return mapping


class LlmLineMatcher:
    """Asks a model to match invoice lines to purchase-order lines. Inject `complete`
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

    def match(self, invoice: list[Line], po: list[Line]) -> list[int]:
        raw = self._complete(build_prompt(invoice, po))
        return parse_mapping(raw, invoice_len=len(invoice))

    def _call_openrouter(self, prompt: str) -> str:
        if not self._api_key:
            raise MatcherError("set OPENROUTER_API_KEY to use the model-backed matcher")
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
            raise MatcherError(f"could not reach the model: {exc}") from exc
        return payload["choices"][0]["message"]["content"]
