"""A small operator console for the agents: an SAP-Fiori-flavored cockpit.

Run it:

    python console/serve.py

Then open http://localhost:8000 in your browser. No SAP account, no API key, no
dependencies. Everything runs in memory against the fake, governed SAP, using the
same propose -> guard -> approve -> log shape the whole book is built on.

This first version is wired to Pattern 1 (invoice posting). Because every pattern
shares that shape, the same console generalises: implement the small Agent adapter
below for another pattern and point the server at it.
"""

from __future__ import annotations

import json
import sys
import webbrowser
from dataclasses import replace
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "shared"))
sys.path.insert(0, str(REPO / "patterns" / "pattern-01-finance-document-to-draft-posting" / "src"))

from sap_client import Document, GovernedSapClient, MockSapClient  # noqa: E402

from pattern1.determination import apply_determination  # noqa: E402
from pattern1.proposer import RuleBasedProposer  # noqa: E402
from pattern1.validator import default_config, validate_posting  # noqa: E402


def _money(d: Decimal) -> str:
    return f"{d:.2f}"


class InvoicePostingAgent:
    """The Pattern 1 agent, as the console sees it: an inbox of documents, a
    proposal and a verdict per document, and approve / reject / onboard actions.

    Another pattern only has to offer the same four calls to reuse the console.
    """

    title = "Nordwind AP Cockpit"
    actor = "invoice-agent@nordwind"

    def __init__(self) -> None:
        self.mock = MockSapClient()
        # An invoice from a vendor SAP does not know yet, to show the exception.
        self.mock.register_document(
            Document(
                doc_id="EXT-2001",
                vendor="Helvetica Print AG",
                currency="EUR",
                net_amount=Decimal("800.00"),
                tax_amount=Decimal("152.00"),
                gross_amount=Decimal("952.00"),
                document_date="2026-06-25",
            )
        )
        self.client = GovernedSapClient(
            self.mock, entitlements={"read", "stage", "confirm"}, actor=self.actor
        )
        self.proposer = RuleBasedProposer()
        self.doc_ids = ["INV-1001", "INV-1002", "INV-1003", "EXT-2001"]
        self.posted: dict[str, str] = {}
        self.rejected: set[str] = set()

    def _config(self):
        return replace(
            default_config(),
            known_vendors=self.mock.known_vendors(),
            known_tax_codes=self.mock.known_tax_codes(),
            active_cost_centers=self.mock.active_cost_centers(),
        )

    def _prep(self, doc_id: str):
        doc = self.mock.read_document(doc_id)
        posting = apply_determination(
            doc, self.proposer.propose(doc, posting_date="2026-06-27")
        )
        verdict = validate_posting(doc, posting, config=self._config())
        return doc, posting, verdict

    def _status(self, doc_id: str, verdict) -> str:
        if doc_id in self.posted:
            return "posted"
        if doc_id in self.rejected:
            return "rejected"
        return "ready" if verdict.status == "PASS" else "exception"

    def inbox(self) -> dict:
        items = []
        for doc_id in self.doc_ids:
            doc, _posting, verdict = self._prep(doc_id)
            items.append(
                {
                    "id": doc.doc_id,
                    "vendor": doc.vendor,
                    "amount": _money(doc.gross_amount),
                    "currency": doc.currency,
                    "status": self._status(doc_id, verdict),
                    "reason": verdict.reasons[0] if verdict.reasons else "",
                }
            )
        return {"title": self.title, "actor": self.actor, "items": items}

    def detail(self, doc_id: str) -> dict:
        doc, posting, verdict = self._prep(doc_id)
        status = self._status(doc_id, verdict)
        unknown_vendor = any("master data" in r for r in verdict.reasons)
        return {
            "id": doc.doc_id,
            "vendor": doc.vendor,
            "currency": doc.currency,
            "net": _money(doc.net_amount),
            "tax": _money(doc.tax_amount),
            "gross": _money(doc.gross_amount),
            "date": doc.document_date,
            "confidence": doc.confidence,
            "tax_code": posting.tax_code,
            "cost_center": posting.cost_center,
            "lines": [
                {"account": ln.account, "side": ln.side, "amount": _money(ln.amount)}
                for ln in posting.lines
            ],
            "verdict": verdict.status,
            "reasons": list(verdict.reasons),
            "status": status,
            "can_onboard": status == "exception" and unknown_vendor,
            "posting_id": self.posted.get(doc_id, ""),
            "audit": [
                {"op": e.operation, "target": e.target, "outcome": e.outcome, "actor": e.actor}
                for e in self.client.audit_log
            ],
            "audit_ok": self.client.verify_audit(),
        }

    def approve(self, doc_id: str) -> dict:
        doc = self.client.read_document(doc_id)
        posting = apply_determination(
            doc, self.proposer.propose(doc, posting_date="2026-06-27")
        )
        verdict = validate_posting(doc, posting, config=self._config())
        if verdict.status != "PASS":
            return self.detail(doc_id)
        staged = self.client.stage_posting(posting)
        self.client.record_approval(staged.staged_id, approver="human (console)")
        result = self.client.confirm_posting(staged.staged_id)
        self.posted[doc_id] = result.posting_id
        return self.detail(doc_id)

    def reject(self, doc_id: str) -> dict:
        self.rejected.add(doc_id)
        return self.detail(doc_id)

    def onboard(self, doc_id: str) -> dict:
        doc = self.mock.read_document(doc_id)
        self.mock.add_business_partner(doc.vendor)  # the master-data step
        return self.detail(doc_id)


AGENT = InvoicePostingAgent()


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, status=200, ctype="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _doc_id(self):
        qs = parse_qs(urlparse(self.path).query)
        return (qs.get("id") or [""])[0]

    def do_GET(self):
        route = urlparse(self.path).path
        if route in ("/", "/index.html"):
            self._send((HERE / "index.html").read_bytes(), ctype="text/html; charset=utf-8")
        elif route == "/api/inbox":
            self._send(AGENT.inbox())
        elif route == "/api/document":
            self._send(AGENT.detail(self._doc_id()))
        else:
            self._send({"error": "not found"}, status=404)

    def do_POST(self):
        route = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        doc_id = payload.get("id", "")
        actions = {"/api/approve": AGENT.approve, "/api/reject": AGENT.reject, "/api/onboard": AGENT.onboard}
        if route in actions:
            self._send(actions[route](doc_id))
        else:
            self._send({"error": "not found"}, status=404)

    def log_message(self, *args):  # keep the console quiet
        pass


def main() -> None:
    port = 8000
    url = f"http://localhost:{port}"
    print(f"{AGENT.title} running at {url}  (Ctrl+C to stop)")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    ThreadingHTTPServer(("localhost", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
