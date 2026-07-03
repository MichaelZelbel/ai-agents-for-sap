"""A shared operator console for the agents: an SAP-Fiori-flavored cockpit.

Run it:

    python console/serve.py

Then open http://localhost:8000. No SAP account, no dependencies, all in memory.

Every pattern in this repo shares one shape: the AI proposes, a deterministic guard
checks, a human decides, and the move is logged. So one console fits them all. Each
agent below fills the same neutral contract, an inbox and a detail with a proposal, a
verdict, some actions, and a trail, and the same page renders any of them. This build
ships two agents to prove it: Pattern 1 (invoice posting) and Pattern 2 (document
triage). Pick between them in the top bar. Adding a third is one more adapter.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import webbrowser
from dataclasses import replace
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
PATTERN1 = REPO / "patterns" / "pattern-01-finance-document-to-draft-posting"
sys.path.insert(0, str(REPO / "shared"))
sys.path.insert(0, str(PATTERN1 / "src"))
sys.path.insert(0, str(REPO / "patterns" / "pattern-02-invoice-triage" / "src"))

from sap_client import (  # noqa: E402
    Document,
    ExtractionError,
    GovernedSapClient,
    MockSapClient,
    extract_document,
)

from pattern1.determination import apply_determination  # noqa: E402
from pattern1.proposer import RuleBasedProposer  # noqa: E402
from pattern1.validator import default_config, validate_posting  # noqa: E402
from triage import CATEGORIES, ROUTES, TriageError, route  # noqa: E402


def load_dotenv() -> None:
    """Read the OpenRouter key from a .env file so 'drop a PDF' can call the model."""
    for env_file in (PATTERN1 / ".env", REPO / ".env"):
        if not env_file.exists():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _money(d: Decimal) -> str:
    return f"{d:.2f}"


class DocumentAgent:
    """Shared plumbing: an in-memory SAP with an inbox of documents, and the drop-a-PDF
    upload. Subclasses implement inbox(), detail(id), and act(action, id)."""

    agent_id = ""
    title = ""
    actor = ""
    # Only the invoice-shaped agents accept a dropped PDF (read by the vision model).
    # The rest work from their seeded inbox, so the console hides the drop zone for them.
    accepts_upload = False
    inbox_label = "Inbox"

    def __init__(self) -> None:
        self.mock = MockSapClient()
        self.doc_ids: list[str] = ["INV-1001", "INV-1002", "INV-1003"]
        self.setup()

    def setup(self) -> None:  # subclasses add demo documents
        pass

    def upload(self, filename: str, content: bytes) -> dict:
        suffix = Path(filename).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
            tf.write(content)
            temp_path = tf.name
        try:
            doc = extract_document(temp_path)
        except ExtractionError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": f"could not read the file: {exc}"}
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
        self.mock.register_document(doc)
        if doc.doc_id not in self.doc_ids:
            self.doc_ids.insert(0, doc.doc_id)
        return {"ok": True, "id": doc.doc_id}


class InvoicePostingAgent(DocumentAgent):
    """Pattern 1: read an invoice, propose a posting, guard it, approve, post."""

    agent_id = "invoice"
    title = "Nordwind AP Cockpit"
    actor = "invoice-agent@nordwind"
    accepts_upload = True
    inbox_label = "Invoice inbox"

    def setup(self) -> None:
        self.mock.register_document(
            Document("EXT-2001", "Helvetica Print AG", "EUR", Decimal("800.00"),
                     Decimal("152.00"), Decimal("952.00"), "2026-06-25")
        )
        self.doc_ids.append("EXT-2001")
        self.client = GovernedSapClient(
            self.mock, entitlements={"read", "stage", "confirm"}, actor=self.actor
        )
        self.proposer = RuleBasedProposer()
        self.posted: dict[str, str] = {}
        self.rejected: set[str] = set()

    def _config(self):
        return replace(
            default_config(),
            known_vendors=self.mock.known_vendors(),
            known_tax_codes=self.mock.known_tax_codes(),
            active_cost_centers=self.mock.active_cost_centers(),
            min_confidence=0.5,
        )

    def _prep(self, doc_id):
        doc = self.mock.read_document(doc_id)
        posting = apply_determination(doc, self.proposer.propose(doc, posting_date="2026-06-27"))
        return doc, posting, validate_posting(doc, posting, config=self._config())

    def _status(self, doc_id, verdict):
        if doc_id in self.posted:
            return "posted"
        if doc_id in self.rejected:
            return "rejected"
        return "ready" if verdict.status == "PASS" else "exception"

    def inbox(self):
        items = []
        for did in self.doc_ids:
            doc, _p, verdict = self._prep(did)
            items.append({"id": doc.doc_id, "primary": doc.vendor,
                          "secondary": f"{_money(doc.gross_amount)} {doc.currency}",
                          "status": self._status(did, verdict),
                          "reason": verdict.reasons[0] if verdict.reasons else ""})
        return items

    def detail(self, doc_id):
        doc, posting, verdict = self._prep(doc_id)
        status = self._status(doc_id, verdict)
        header = [["Date", doc.document_date], ["Net", _money(doc.net_amount)],
                  ["Tax", _money(doc.tax_amount)], ["Gross", f"{_money(doc.gross_amount)} {doc.currency}"]]
        if doc.confidence is not None:
            header.append(["Read confidence", f"{doc.confidence * 100:.0f}%"])
        can_onboard = status == "exception" and any("master data" in r for r in verdict.reasons)
        actions = [
            {"action": "approve", "label": "Approve & Post", "style": "approve", "enabled": status == "ready"},
            {"action": "reject", "label": "Reject", "style": "reject", "enabled": status in ("ready", "exception")},
        ]
        if can_onboard:
            actions.append({"action": "onboard", "label": "Onboard vendor", "style": "onboard", "enabled": True})
        result = ""
        if status == "posted":
            result = f"Posted as {self.posted[doc_id]}"
        elif status == "rejected":
            result = "Rejected. Nothing was written."
        audit = [f"{e.operation:<8} {e.target:<14} {e.outcome} · {e.actor}" for e in self.client.audit_log]
        return {
            "id": doc.doc_id, "title": f"{doc.doc_id} · {doc.vendor}", "header": header,
            "proposal_title": "Proposed posting",
            "columns": ["Side", "Account", "Amount"],
            "rows": [[ln.side, ln.account, f"{_money(ln.amount)} {doc.currency}"] for ln in posting.lines],
            "note": f"Tax code {posting.tax_code} · Cost center {posting.cost_center}",
            "verdict": verdict.status, "verdict_label": f"Guard: {verdict.status}",
            "reasons": list(verdict.reasons), "status": status, "actions": actions, "result": result,
            "audit": audit, "audit_ok": self.client.verify_audit() if audit else None,
        }

    def act(self, action, doc_id):
        if action == "approve":
            doc = self.client.read_document(doc_id)
            posting = apply_determination(doc, self.proposer.propose(doc, posting_date="2026-06-27"))
            if validate_posting(doc, posting, config=self._config()).status == "PASS":
                staged = self.client.stage_posting(posting)
                self.client.record_approval(staged.staged_id, approver="human (console)")
                self.posted[doc_id] = self.client.confirm_posting(staged.staged_id).posting_id
        elif action == "reject":
            self.rejected.add(doc_id)
        elif action == "onboard":
            self.mock.add_business_partner(self.mock.read_document(doc_id).vendor)
        return self.detail(doc_id)


class TriageAgent(DocumentAgent):
    """Pattern 2: read a document, classify it, and route it. No posting at all."""

    agent_id = "triage"
    title = "AP Triage Desk"
    actor = "triage-agent@nordwind"

    def setup(self) -> None:
        self.confirmed: dict[str, str] = {}
        self.rejected: set[str] = set()

    def _classify(self, doc):
        # A crude offline classifier (same idea as the pattern's rule stand-in): a
        # document with no amount is not an invoice; a larger one references a PO.
        if doc.gross_amount == 0:
            return "not_an_invoice"
        return "po_invoice" if doc.gross_amount >= Decimal("1000") else "direct_expense"

    def _route(self, category):
        try:
            return route(category), ""
        except TriageError as exc:
            return "", str(exc)

    def _status(self, doc_id):
        if doc_id in self.confirmed:
            return "done"
        if doc_id in self.rejected:
            return "rejected"
        return "ready"

    def inbox(self):
        items = []
        for did in self.doc_ids:
            doc = self.mock.read_document(did)
            category = self._classify(doc)
            dest, err = self._route(category)
            items.append({"id": did, "primary": doc.vendor,
                          "secondary": f"{_money(doc.gross_amount)} {doc.currency}",
                          "status": "exception" if err else self._status(did),
                          "reason": err})
        return items

    def detail(self, doc_id):
        doc = self.mock.read_document(doc_id)
        category = self._classify(doc)
        dest, err = self._route(category)
        status = "exception" if err else self._status(doc_id)
        audit = [f"classified  {doc_id:<14} as {category}"]
        if not err:
            audit.append(f"router      {doc_id:<14} accepted -> {dest}")
        if doc_id in self.confirmed:
            audit.append(f"confirmed   {doc_id:<14} routed -> {self.confirmed[doc_id]} · human (console)")
        result = ""
        if doc_id in self.confirmed:
            result = f"Confirmed. Routed to: {self.confirmed[doc_id]}"
        elif doc_id in self.rejected:
            result = "Rejected. Sent back for manual triage."
        return {
            "id": doc_id, "title": f"{doc_id} · {doc.vendor}",
            "header": [["Vendor", doc.vendor], ["Net", _money(doc.net_amount)],
                       ["Tax", _money(doc.tax_amount)], ["Gross", f"{_money(doc.gross_amount)} {doc.currency}"]],
            "proposal_title": "Proposed routing",
            "columns": ["Category", "Routes to"],
            "rows": [[category, dest or "(refused)"]],
            "note": "The model proposes a category; the router only accepts one of: " + ", ".join(CATEGORIES),
            "verdict": "FAIL" if err else "PASS",
            "verdict_label": "Router: refused" if err else "Router: accepted",
            "reasons": [err] if err else [], "status": status,
            "actions": [
                {"action": "confirm", "label": "Confirm routing", "style": "approve", "enabled": status == "ready"},
                {"action": "reject", "label": "Reject", "style": "reject", "enabled": status == "ready"},
            ],
            "result": result, "audit": audit, "audit_ok": None,
        }

    def act(self, action, doc_id):
        if action == "confirm":
            doc = self.mock.read_document(doc_id)
            dest, err = self._route(self._classify(doc))
            if not err:
                self.confirmed[doc_id] = dest
        elif action == "reject":
            self.rejected.add(doc_id)
        return self.detail(doc_id)


load_dotenv()
AGENTS: dict[str, DocumentAgent] = {a.agent_id: a for a in (InvoicePostingAgent(), TriageAgent())}

# Patterns 3-10 live in console/extra_agents.py (one adapter each). Merge them in.
sys.path.insert(0, str(HERE))
try:
    from extra_agents import build_extra_agents  # noqa: E402

    for _agent in build_extra_agents():
        AGENTS[_agent.agent_id] = _agent
except Exception as exc:  # pragma: no cover - the two built-in agents still work
    print(f"[console] extra agents unavailable: {exc}")

DEFAULT_AGENT = "invoice"


def pick(name):
    return AGENTS.get(name or DEFAULT_AGENT, AGENTS[DEFAULT_AGENT])


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, status=200, ctype="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _q(self, key):
        return (parse_qs(urlparse(self.path).query).get(key) or [""])[0]

    def do_GET(self):
        route_ = urlparse(self.path).path
        if route_ in ("/", "/index.html"):
            self._send((HERE / "index.html").read_bytes(), ctype="text/html; charset=utf-8")
        elif route_ == "/api/agents":
            self._send([
                {"id": a.agent_id, "title": a.title, "actor": a.actor,
                 "accepts_upload": a.accepts_upload, "inbox_label": a.inbox_label}
                for a in AGENTS.values()
            ])
        elif route_ == "/api/inbox":
            self._send({"items": pick(self._q("agent")).inbox()})
        elif route_ == "/api/document":
            self._send(pick(self._q("agent")).detail(self._q("id")))
        else:
            self._send({"error": "not found"}, status=404)

    def do_POST(self):
        route_ = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        agent = pick(payload.get("agent"))
        if route_ == "/api/upload":
            content = base64.b64decode(payload.get("content_base64", ""))
            self._send(agent.upload(payload.get("filename", "invoice.pdf"), content))
        elif route_ == "/api/act":
            self._send(agent.act(payload.get("action", ""), payload.get("id", "")))
        else:
            self._send({"error": "not found"}, status=404)

    def log_message(self, *args):
        pass


def main() -> None:
    url = "http://localhost:8000"
    print(f"Operator console running at {url}  (Ctrl+C to stop)")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    ThreadingHTTPServer(("localhost", 8000), Handler).serve_forever()


if __name__ == "__main__":
    main()
