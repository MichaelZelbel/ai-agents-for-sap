"""The proposer: the agent's "propose" step.

The AI reads a free-text customer request and extracts intent: which products,
how many, the requested delivery date, and any discount. The AI only extracts.
Pricing the lines and building the draft order is deterministic code here, and
the deterministic guard decides policy. So a wrong extraction cannot release a
bad order; it is caught downstream and never handed to fulfillment.

Two proposers ship, both behind the same `Proposer` interface:

* `RuleBasedProposer` extracts with plain keyword matching. It runs offline with
  no API key, so it is the default and it drives the tests.
* `LlmBackedProposer` asks a real model (via OpenRouter) to extract the same
  fields. The model call is injectable, so tests run offline.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from .data import CustomerRequest, ProductCatalog
from .models import DraftOrder, OrderLine, RequestedItem


@dataclass(frozen=True)
class ExtractedRequest:
    """What the AI pulled out of the free text. Intent only, not yet priced."""

    items: list[RequestedItem]
    requested_delivery: str
    discount_pct: Decimal
    ship_to_country: str


class Proposer(Protocol):
    def extract(
        self, request: CustomerRequest, *, catalog: ProductCatalog
    ) -> ExtractedRequest:
        """Read the request text and return the extracted intent. Extracts only."""
        ...


DEFAULT_CURRENCY = "EUR"
DEFAULT_DELIVERY = "2026-06-30"  # a sensible month-end fallback for the samples


def price_order(
    request: CustomerRequest,
    extracted: ExtractedRequest,
    *,
    catalog: ProductCatalog,
    currency: str = DEFAULT_CURRENCY,
) -> DraftOrder:
    """Turn extracted intent into a priced draft order. Deterministic.

    Unknown SKUs are dropped here; the guard will still flag an order with no
    lines. Discount is applied per line, then rounded to the cent.
    """
    discount_factor = (Decimal("100") - extracted.discount_pct) / Decimal("100")
    lines: list[OrderLine] = []
    total = Decimal("0.00")
    for item in extracted.items:
        product = catalog.get(item.sku)
        if product is None:
            continue
        gross = product.unit_price * Decimal(item.quantity)
        line_total = (gross * discount_factor).quantize(Decimal("0.01"))
        lines.append(
            OrderLine(
                sku=product.sku,
                name=product.name,
                quantity=item.quantity,
                unit_price=product.unit_price,
                line_total=line_total,
            )
        )
        total += line_total
    return DraftOrder(
        request_id=request.request_id,
        customer_id=request.customer_id,
        currency=currency,
        requested_delivery=extracted.requested_delivery,
        discount_pct=extracted.discount_pct,
        ship_to_country=extracted.ship_to_country,
        lines=lines,
        order_total=total.quantize(Decimal("0.01")),
    )


class RuleBasedProposer:
    """Extracts intent with plain keyword matching. Deterministic and offline.

    It matches product names and common nicknames from the sample requests, reads
    a leading quantity, and picks up an ISO delivery date if one is present.
    """

    # Nicknames the sample customers use, mapped to catalog SKUs.
    NICKNAMES = {
        "bracket": "BRK-100",
        "brackets": "BRK-100",
        "clamp": "CLMP-50",
        "clamps": "CLMP-50",
        "valve": "VALVE-9",
        "valves": "VALVE-9",
    }

    def extract(
        self, request: CustomerRequest, *, catalog: ProductCatalog
    ) -> ExtractedRequest:
        text = request.text.lower()
        items: list[RequestedItem] = []
        seen: set[str] = set()
        # Split into words, keeping quantities. For each number, walk forward to
        # the first product nickname before the next number. That pairs "200 of
        # the usual brackets" as 200 -> brackets.
        tokens = re.findall(r"\d+|[a-z\-]+", text)
        pending_qty: int | None = None
        for token in tokens:
            if token.isdigit():
                pending_qty = int(token)
                continue
            sku = self.NICKNAMES.get(token)
            if sku and pending_qty is not None and sku not in seen:
                items.append(RequestedItem(sku=sku, quantity=pending_qty))
                seen.add(sku)
                pending_qty = None

        # An explicit ISO date wins; otherwise fall back to month end.
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", request.text)
        delivery = date_match.group(0) if date_match else DEFAULT_DELIVERY

        # The rule-based stand-in never proposes a discount. Discounts come from
        # the model path or later negotiation, and the guard checks authority.
        return ExtractedRequest(
            items=items,
            requested_delivery=delivery,
            discount_pct=Decimal("0.00"),
            ship_to_country="DE",
        )


# --- Model-backed proposer ---------------------------------------------------

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# A cheap, reliable default. Each extraction costs a fraction of a cent. Free
# models (ids ending ":free") also work but are heavily rate-limited.
DEFAULT_MODEL = "openai/gpt-4o-mini"

_SYSTEM = (
    "You are a careful sales assistant. You read a customer's free-text request "
    "and extract what they want to order. You only extract; a human approves "
    "before anything is released. Reply with JSON only."
)


class ProposerError(RuntimeError):
    """The model returned something we could not turn into an extraction."""


def build_prompt(request: CustomerRequest, catalog: ProductCatalog) -> str:
    """The instruction we hand the model. Plain, and it shows the catalog."""
    catalog_lines = "\n".join(
        f"- {p.sku}: {p.name}" for p in catalog.values()
    )
    return (
        "Extract the order intent from this customer request.\n\n"
        f"Customer id: {request.customer_id}\n"
        f"Request text: {request.text}\n\n"
        "Products you may order (use the exact sku):\n"
        f"{catalog_lines}\n\n"
        "Extract the products and quantities, the requested delivery date as an "
        "ISO date (YYYY-MM-DD), any discount percent mentioned, and the ship-to "
        "country as a two-letter code. If a field is not stated, use an empty "
        "string for the date, 0 for the discount, and DE for the country.\n\n"
        "Reply with ONLY a JSON object of this shape, no prose:\n"
        '{"items": [{"sku": "BRK-100", "quantity": 200}], '
        '"requested_delivery": "2026-06-30", "discount_pct": "0", '
        '"ship_to_country": "DE"}'
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


def parse_extraction(raw: str) -> ExtractedRequest:
    """Turn the model's JSON reply into an ExtractedRequest. Structural checks
    only; the business rules are the guard's job."""
    data = _extract_json(raw)
    items: list[RequestedItem] = []
    for item in data.get("items", []):
        try:
            quantity = int(item["quantity"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProposerError(f"bad quantity in model output: {item!r}") from exc
        sku = str(item.get("sku", "")).strip()
        if not sku:
            raise ProposerError(f"missing sku in model output: {item!r}")
        items.append(RequestedItem(sku=sku, quantity=quantity))
    if not items:
        raise ProposerError("model extracted no items")
    try:
        discount = Decimal(str(data.get("discount_pct", "0") or "0"))
    except InvalidOperation as exc:
        raise ProposerError(f"bad discount in model output: {data!r}") from exc
    delivery = str(data.get("requested_delivery", "") or DEFAULT_DELIVERY)
    country = str(data.get("ship_to_country", "DE") or "DE").upper()
    return ExtractedRequest(
        items=items,
        requested_delivery=delivery,
        discount_pct=discount,
        ship_to_country=country,
    )


class LlmBackedProposer:
    """Asks a model to extract the order intent from the request text.

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

    def extract(
        self, request: CustomerRequest, *, catalog: ProductCatalog
    ) -> ExtractedRequest:
        raw = self._complete(build_prompt(request, catalog))
        return parse_extraction(raw)

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
