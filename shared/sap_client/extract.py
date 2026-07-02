"""Read an invoice image or PDF into a Document, with one model call.

This is the "document reader" the book keeps mentioning. In a real deployment,
an extractor turns a PDF or a scan into structured fields before any agent sees
it. Here that step is a single call to a vision-capable model via OpenRouter: it
looks at the invoice and returns the fields as JSON. It does no arithmetic and no
bookkeeping. It only reports what the document says. The agent, the validator,
and the human do the rest, unchanged.

Pass your own `complete` callable to test offline or to swap providers. By default
it calls OpenRouter using the OPENROUTER_API_KEY environment variable.
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .models import Document, TaxLine

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# A cheap, vision-capable default. The same model the proposer uses can also read
# an invoice image. A fraction of a cent per invoice.
DEFAULT_MODEL = "openai/gpt-4o-mini"
# Scanned or photographed invoices (like a hotel bill) have no text layer, so OCR
# is the safe default. Override with pdf_engine="pdf-text" (cheaper) for PDFs that
# already carry selectable text, or "native" for models that read PDFs directly.
DEFAULT_PDF_ENGINE = "mistral-ocr"

_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".pdf": "application/pdf",
}

_SYSTEM = (
    "You read a vendor invoice and report its fields. You do not do arithmetic and "
    "you do not do bookkeeping. You report only what the document shows. JSON only."
)

_INSTRUCTION = (
    "Read the attached vendor invoice and return ONLY a JSON object with these "
    "keys: doc_id, vendor, currency, net_amount, tax_amount, gross_amount, "
    "document_date, confidence, tax_lines. No prose.\n\n"
    "Rules:\n"
    "- doc_id is the invoice or document number printed on it.\n"
    "- currency is the ISO 4217 code, for example EUR, USD, GBP.\n"
    "- amounts are plain decimal strings with a dot for the decimal point and no "
    "currency symbols. If the invoice prints European format (1.234,56), convert the "
    "format only, not the value (1234.56).\n"
    "- net is the amount before tax, tax is the tax amount, gross is the total due.\n"
    "- document_date is the invoice date in YYYY-MM-DD form.\n"
    "- confidence is a number from 0 to 1 for how sure you are you read the invoice "
    "correctly. Be honest: a clean document is near 1, a blurry or partial scan is low.\n"
    "- tax_lines is the per-rate VAT breakdown. Many invoices (hotels, catering) mix "
    "rates, and one net/tax/gross cannot describe them. Return one object "
    '{"rate": 0.07, "net": "373.83", "tax": "26.17"} per rate the invoice shows, using '
    "the rate as a fraction (0.07 for 7%). Include any line that carries no VAT as a "
    "0-rate entry, so the parts sum to the gross. If the invoice has a single rate, "
    "return one entry or an empty list.\n"
    "- Report the numbers exactly as printed. Do not correct or recompute them. If "
    "the totals do not add up, report them anyway; the agent's guard will catch it.\n"
    "- If you cannot actually see the invoice, do not guess. Return "
    '{"error": "no readable invoice"} and nothing else.'
)


class ExtractionError(RuntimeError):
    """The model returned something we could not turn into a Document."""


def _data_url(path: Path) -> tuple[str, str]:
    mime = _MIME.get(path.suffix.lower())
    if mime is None:
        raise ExtractionError(
            f"unsupported invoice file type: {path.suffix!r}. "
            f"Use one of: {', '.join(sorted(_MIME))}."
        )
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return mime, f"data:{mime};base64,{encoded}"


def _content_part(path: Path) -> dict[str, Any]:
    """Build the message content part for an image or a PDF."""
    mime, url = _data_url(path)
    if mime == "application/pdf":
        # OpenRouter parses the PDF server-side for models that accept files.
        return {"type": "file", "file": {"filename": path.name, "file_data": url}}
    return {"type": "image_url", "image_url": {"url": url}}


def _normalize_separators(cleaned: str) -> str:
    """Turn a locale-formatted number (already stripped to digits and separators)
    into a plain dot-decimal string. Format only; the value never changes."""
    if "," in cleaned and "." in cleaned:
        # Whichever separator appears last is the decimal point.
        if cleaned.rfind(",") > cleaned.rfind("."):
            return cleaned.replace(".", "").replace(",", ".")  # 1.234,56 -> 1234.56
        return cleaned.replace(",", "")  # 1,234.56 -> 1234.56
    if "," in cleaned:
        head, _, tail = cleaned.rpartition(",")
        if len(tail) == 2 and head.lstrip("-").isdigit():
            return head + "." + tail  # 390,64 -> 390.64
        return cleaned.replace(",", "")  # 1,234 -> 1234 (thousands)
    return cleaned


def _parse_amount(raw: Any, *, field: str) -> Decimal:
    """Parse a money value the model reported, tolerant of locale formatting.

    Handles "1000.00", European "1.234,56", US "1,234.56", a bare "390,64", and
    stray currency symbols or spaces. This normalises *format* only; the value is
    never changed, so "report the numbers as printed" still holds.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise ExtractionError(
            f"the model returned no {field}; it may not have found that value on the document"
        )
    if isinstance(raw, (int, float)):
        return Decimal(str(raw))
    cleaned = re.sub(r"[^0-9,.\-]", "", str(raw).strip())
    if not cleaned or cleaned.strip("-.,") == "":
        raise ExtractionError(f"the model returned a non-numeric {field}: {raw!r}")
    try:
        return Decimal(_normalize_separators(cleaned))
    except InvalidOperation as exc:
        raise ExtractionError(f"the model returned a bad number for {field}: {raw!r}") from exc


def _parse_rate(raw: Any) -> Decimal:
    """A tax rate as a fraction. Accepts 7, "7%", "0.07"; all become Decimal('0.07')."""
    if raw is None:
        raise ExtractionError("a tax line is missing its rate")
    value = _parse_amount(str(raw).replace("%", ""), field="tax rate")
    return value / Decimal("100") if value > 1 else value


def _parse_tax_lines(raw: Any) -> tuple[TaxLine, ...]:
    """Parse the optional per-rate VAT breakdown. Absent or empty means single-rate."""
    if not raw:
        return ()
    lines = []
    for item in raw:
        lines.append(
            TaxLine(
                rate=_parse_rate(item.get("rate")),
                net=_parse_amount(item.get("net"), field="a tax line net"),
                tax=_parse_amount(item.get("tax", "0"), field="a tax line tax"),
            )
        )
    return tuple(lines)


def parse_document(raw: str) -> Document:
    """Turn the model's JSON reply into a Document. Structural checks only."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ExtractionError(f"model did not return JSON: {raw[:200]!r}")
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"model returned invalid JSON: {raw[:200]!r}") from exc
    if "error" in data and "doc_id" not in data:
        raise ExtractionError(f"model could not read the invoice: {data['error']!r}")

    def _has(key: str) -> bool:
        return key in data and data[key] not in (None, "")

    try:
        confidence = data.get("confidence")
        tax_lines = _parse_tax_lines(data.get("tax_lines"))
        # For a mixed-rate invoice the totals may be left out; derive them from the
        # breakdown so net + tax always foots to gross.
        net = (
            _parse_amount(data["net_amount"], field="net_amount")
            if _has("net_amount")
            else sum((line.net for line in tax_lines), Decimal("0"))
        )
        tax = (
            _parse_amount(data["tax_amount"], field="tax_amount")
            if _has("tax_amount")
            else sum((line.tax for line in tax_lines), Decimal("0"))
        )
        gross = (
            _parse_amount(data["gross_amount"], field="gross_amount")
            if _has("gross_amount")
            else net + tax
        )
        return Document(
            doc_id=str(data["doc_id"]),
            vendor=str(data["vendor"]),
            currency=str(data["currency"]),
            net_amount=net,
            tax_amount=tax,
            gross_amount=gross,
            document_date=str(data["document_date"]),
            # A reading from a real document carries a confidence; default to fully
            # confident if the model did not give one, so a missing score never blocks.
            confidence=float(confidence) if confidence is not None else 1.0,
            tax_lines=tax_lines,
        )
    except KeyError as exc:
        raise ExtractionError(f"model reply is missing a field: {exc}") from exc
    except (InvalidOperation, ValueError) as exc:
        raise ExtractionError(f"model returned a bad number: {exc}") from exc


def _make_openrouter_caller(
    model: str, api_key: str, pdf_engine: str = DEFAULT_PDF_ENGINE
) -> Callable[[Path], str]:
    def call(path: Path) -> str:
        if not api_key:
            raise ExtractionError(
                "set OPENROUTER_API_KEY to read invoice files with a model"
            )
        is_pdf = path.suffix.lower() == ".pdf"
        request: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _INSTRUCTION},
                        _content_part(path),
                    ],
                },
            ],
            "temperature": 0,
        }
        if is_pdf and pdf_engine != "native":
            # Without this, OpenRouter does not parse the PDF for models that do not
            # natively accept files, and the model answers with nothing to read.
            # mistral-ocr reads scans and photos; pdf-text is cheaper but only works
            # on PDFs that already have a text layer.
            request["plugins"] = [{"id": "file-parser", "pdf": {"engine": pdf_engine}}]
        body = json.dumps(request).encode("utf-8")
        req = urllib.request.Request(
            OPENROUTER_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ExtractionError(f"could not reach the model: {exc}") from exc
        return payload["choices"][0]["message"]["content"]

    return call


def extract_document(
    path: str | Path,
    *,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    pdf_engine: str = DEFAULT_PDF_ENGINE,
    complete: Callable[[Path], str] | None = None,
) -> Document:
    """Read an invoice file (image or PDF) into a Document with one model call.

    Inject `complete` (a callable taking the file path and returning the model's
    text reply) to test offline or to use a different provider. `pdf_engine` picks
    how a PDF is parsed: "mistral-ocr" (default, reads scans), "pdf-text" (cheaper,
    text-layer PDFs only), or "native" (let the model read the PDF itself).
    """
    path = Path(path)
    if path.suffix.lower() not in _MIME:
        raise ExtractionError(
            f"unsupported invoice file type: {path.suffix!r}. "
            f"Use one of: {', '.join(sorted(_MIME))}, or a .json file of fields."
        )
    if complete is None:
        complete = _make_openrouter_caller(
            model,
            api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY", ""),
            pdf_engine,
        )
    return parse_document(complete(path))
