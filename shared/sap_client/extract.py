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
import urllib.error
import urllib.request
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .models import Document

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# A cheap, vision-capable default. The same model the proposer uses can also read
# an invoice image. A fraction of a cent per invoice.
DEFAULT_MODEL = "openai/gpt-4o-mini"

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
    "document_date. No prose.\n\n"
    "Rules:\n"
    "- doc_id is the invoice or document number printed on it.\n"
    "- currency is the ISO 4217 code, for example EUR, USD, GBP.\n"
    "- amounts are plain decimal strings: no currency symbols, no thousands "
    "separators, a dot for the decimal point.\n"
    "- net is the amount before tax, tax is the tax amount, gross is the total due.\n"
    "- document_date is the invoice date in YYYY-MM-DD form.\n"
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
    try:
        return Document(
            doc_id=str(data["doc_id"]),
            vendor=str(data["vendor"]),
            currency=str(data["currency"]),
            net_amount=Decimal(str(data["net_amount"])),
            tax_amount=Decimal(str(data["tax_amount"])),
            gross_amount=Decimal(str(data["gross_amount"])),
            document_date=str(data["document_date"]),
        )
    except KeyError as exc:
        raise ExtractionError(f"model reply is missing a field: {exc}") from exc
    except InvalidOperation as exc:
        raise ExtractionError(f"model returned a non-numeric amount: {exc}") from exc


def _make_openrouter_caller(model: str, api_key: str) -> Callable[[Path], str]:
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
        if is_pdf:
            # Without this, OpenRouter does not parse the PDF for models that do not
            # natively accept files, and the model answers with nothing to read.
            # pdf-text is free and works for text-based PDFs (mistral-ocr for scans).
            request["plugins"] = [{"id": "file-parser", "pdf": {"engine": "pdf-text"}}]
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
    complete: Callable[[Path], str] | None = None,
) -> Document:
    """Read an invoice file (image or PDF) into a Document with one model call.

    Inject `complete` (a callable taking the file path and returning the model's
    text reply) to test offline or to use a different provider.
    """
    path = Path(path)
    if path.suffix.lower() not in _MIME:
        raise ExtractionError(
            f"unsupported invoice file type: {path.suffix!r}. "
            f"Use one of: {', '.join(sorted(_MIME))}, or a .json file of fields."
        )
    if complete is None:
        complete = _make_openrouter_caller(
            model, api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY", "")
        )
    return parse_document(complete(path))
