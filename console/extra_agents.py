"""Console adapters for Patterns 3 through 10.

serve.py ships Patterns 1 and 2 inline to keep its story short. This module adds
the other eight so one console covers the whole catalog. Each class fills the same
neutral contract serve.py already defines, agent_id/title/actor plus inbox(),
detail(id), and act(action, id), and drives each pattern's own runnable code with
its OFFLINE, deterministic proposer, so the console needs no OpenRouter key.

Two honest asymmetries the console surfaces as-is:
  - Patterns 5, 7, and 9 have a governed client with a hash-chained audit log, so
    they report audit_ok True/False. The rest have a plainer trail (audit_ok=None).
  - Patterns 3, 4, 6, 8, 10 have no SAP write-back in this repo, so their human
    decision is recorded in the console's own state, not posted to a mock system.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

for _p in (
    "pattern-03-three-way-match",
    "pattern-04-dispute-assistant",
    "pattern-05-procurement-approval-packet",
    "pattern-06-close-orchestration",
    "pattern-07-service-resolution",
    "pattern-08-cash-application",
    "pattern-09-sales-order",
    "pattern-10-expense-audit",
):
    _src = str(REPO / "patterns" / _p / "src")
    if _src not in sys.path:
        sys.path.insert(0, _src)

# Pattern imports (offline paths only). Aliased where names repeat across patterns.
from threeway import Line, LlmLineMatcher, three_way_match  # noqa: E402
from dispute import Dispute, DisputeError, LlmDisputeAssistant, review  # noqa: E402
from procurement import (  # noqa: E402
    PacketAuditLog,
    RuleBasedNarrator,
    assemble_packet,
    record_decision,
    seed_requisitions,
    seed_suppliers,
)
from close.flow import InterventionLog, predict_and_stage, run_intervention  # noqa: E402
from close.plan import seed_close_plan  # noqa: E402
from close.scorer import RuleBasedScorer  # noqa: E402
from service import GovernedServiceSource, MockServiceSource, run_pattern7  # noqa: E402
from service import RuleBasedProposer as ServiceProposer  # noqa: E402
from service import default_config as service_config  # noqa: E402
from service.guard import evaluate as service_evaluate  # noqa: E402
from cashapp.flow import run_cash_application  # noqa: E402
from cashapp.guard import check_match  # noqa: E402
from cashapp.guard import default_config as cash_config  # noqa: E402
from cashapp.ledger import MockArLedger  # noqa: E402
from cashapp.proposer import RuleBasedMatcher  # noqa: E402
from cashapp.samples import SAMPLE_PAYMENTS  # noqa: E402
from salesorder import GovernedSalesClient, MockSalesClient, guard_order, load_requests, price_order  # noqa: E402
from salesorder import RuleBasedProposer as SalesProposer  # noqa: E402
from salesorder import default_config as sales_config  # noqa: E402
from expense.auditor import RuleBasedDrafter, audit_report, sample_reports  # noqa: E402
from expense.auditor import default_policy as expense_policy  # noqa: E402


def _dec(d: Decimal) -> str:
    return f"{d:.2f}"


# --------------------------------------------------------------------------- #
# Pattern 3: three-way match
# --------------------------------------------------------------------------- #

_P3_PO = [
    Line("Ergonomic office chair", Decimal("10"), Decimal("120.00")),
    Line("Standing desk", Decimal("4"), Decimal("350.00")),
]
_P3_INV = [
    Line("Office chairs, ergonomic", Decimal("10"), Decimal("120.00")),
    Line("Desk, sit-stand", Decimal("4"), Decimal("350.00")),
]


class ThreeWayMatchAgent:
    agent_id = "threeway"
    title = "Three-Way Match Desk"
    actor = "match-agent@nordwind"
    accepts_upload = False
    inbox_label = "Invoices to match"

    def __init__(self) -> None:
        self.vendor = "Contoso Office Supplies"
        self.cases = {
            "MATCH-CLEAN": (_P3_INV, [Decimal("10"), Decimal("4")]),
            "MATCH-OVERPRICED": (
                [_P3_INV[0], Line("Desk, sit-stand", Decimal("4"), Decimal("390.00"))],
                [Decimal("10"), Decimal("4")],
            ),
            "MATCH-SHORT": (_P3_INV, [Decimal("8"), Decimal("4")]),
        }
        self.released: set[str] = set()
        self.held: set[str] = set()

    def _run(self, cid):
        invoice, received = self.cases[cid]
        matcher = LlmLineMatcher(
            complete=lambda prompt: json.dumps({"mapping": list(range(len(invoice)))})
        )
        mapping = matcher.match(invoice, _P3_PO)
        return invoice, received, mapping, three_way_match(invoice, _P3_PO, received, mapping)

    def _total(self, invoice) -> Decimal:
        return sum((ln.quantity * ln.unit_price for ln in invoice), Decimal("0"))

    def _status(self, cid, result):
        if cid in self.released:
            return "posted"
        if cid in self.held:
            return "rejected"
        return "ready" if result.status == "PASS" else "exception"

    def inbox(self):
        items = []
        for cid in self.cases:
            invoice, _r, _m, result = self._run(cid)
            items.append({
                "id": cid, "primary": self.vendor,
                "secondary": f"{_dec(self._total(invoice))} EUR",
                "status": self._status(cid, result),
                "reason": result.reasons[0] if result.reasons else "",
            })
        return items

    def detail(self, cid):
        invoice, received, mapping, result = self._run(cid)
        status = self._status(cid, result)
        rows = []
        for i, inv in enumerate(invoice):
            j = mapping[i]
            ordered = _P3_PO[j] if 0 <= j < len(_P3_PO) else None
            rows.append([
                inv.description,
                ordered.description if ordered else "(no match)",
                str(inv.quantity),
                str(received[j]) if ordered and j < len(received) else "-",
                _dec(inv.unit_price),
                _dec(ordered.unit_price) if ordered else "-",
            ])
        audit = [f"matched   line {i + 1} -> order {mapping[i] + 1}" for i in range(len(invoice))]
        audit.append(f"guard     {result.status}")
        if cid in self.released:
            audit.append(f"released  {cid} · human (console)")
        if cid in self.held:
            audit.append(f"held      {cid} · human (console)")
        result_text = "Released to posting." if cid in self.released else (
            "Held for the buyer." if cid in self.held else "")
        return {
            "id": cid, "title": f"{cid} · {self.vendor}",
            "header": [["Vendor", self.vendor], ["PO lines", str(len(_P3_PO))],
                       ["Invoice total", f"{_dec(self._total(invoice))} EUR"], ["Tolerance", "0.01"]],
            "proposal_title": "Proposed line match",
            "columns": ["Invoice line", "Order line", "Inv qty", "Received", "Inv price", "Ord price"],
            "rows": rows,
            "note": "The AI matches lines by meaning; the arithmetic guard checks quantity, receipt, and price within tolerance.",
            "verdict": result.status,
            "verdict_label": "Match guard: cleared" if result.status == "PASS" else "Match guard: held",
            "reasons": list(result.reasons), "status": status,
            "actions": [
                {"action": "approve", "label": "Approve & release", "style": "approve", "enabled": status == "ready"},
                {"action": "reject", "label": "Hold invoice", "style": "reject", "enabled": status in ("ready", "exception")},
            ],
            "result": result_text, "audit": audit, "audit_ok": None,
        }

    def act(self, action, cid):
        if action == "approve":
            _i, _r, _m, result = self._run(cid)
            if result.status == "PASS":
                self.released.add(cid)
        elif action == "reject":
            self.held.add(cid)
        return self.detail(cid)


# --------------------------------------------------------------------------- #
# Pattern 4: dispute copilot (suggest-only)
# --------------------------------------------------------------------------- #

class DisputeAgent:
    agent_id = "dispute"
    title = "Dispute Copilot"
    actor = "dispute-agent@nordwind"
    accepts_upload = False
    inbox_label = "Open disputes"

    def __init__(self) -> None:
        self.samples = {
            "DSP-1": ("short_payment", Dispute("DSP-1", "Office Supplies Co",
                "You only paid 1,070 EUR on invoice INV-1001 but it was for 1,190 EUR. Please advise.")),
            "DSP-2": ("duplicate", Dispute("DSP-2", "Cloud Hosting Ltd",
                "We received two payments for invoice INV-1002. One of them looks like a duplicate.")),
            "DSP-3": ("not_received", Dispute("DSP-3", "Parts Warehouse GmbH",
                "Your records say the goods were delivered, but we never received them. Please hold payment.")),
        }
        self.sent: set[str] = set()
        self.discarded: set[str] = set()

    def _reply(self, d) -> str:
        return (f"Dear {d.vendor}, thank you for reaching out. We have received your message "
                "and a colleague is reviewing the details now. We will come back to you shortly "
                "with the outcome. Best regards, Accounts Payable")

    def _run(self, did):
        case, d = self.samples[did]
        payload = json.dumps({"category": case, "reply": self._reply(d)})
        assistant = LlmDisputeAssistant(complete=lambda prompt: payload)
        try:
            return d, review(assistant.assess(d)), "PASS", []
        except DisputeError as exc:
            return d, None, "FAIL", [str(exc)]

    def _status(self, did, verdict):
        if did in self.sent:
            return "done"
        if did in self.discarded:
            return "rejected"
        return "ready" if verdict == "PASS" else "exception"

    def inbox(self):
        items = []
        for did, (_case, d) in self.samples.items():
            _d, rec, verdict, reasons = self._run(did)
            items.append({
                "id": did, "primary": d.vendor,
                "secondary": rec.category if rec else "refused",
                "status": self._status(did, verdict),
                "reason": reasons[0] if reasons else "",
            })
        return items

    def detail(self, did):
        d, rec, verdict, reasons = self._run(did)
        status = self._status(did, verdict)
        cat = rec.category if rec else "(refused)"
        audit = [f"classified  {did:<7} as {cat}",
                 f"guard       {did:<7} {verdict}",
                 "agent       took no action (suggest-only)"]
        if did in self.sent:
            audit.append(f"human       marked draft sent · {self.actor}")
        if did in self.discarded:
            audit.append(f"human       discarded draft · {self.actor}")
        result_text = "Draft marked sent by a human." if did in self.sent else (
            "Draft discarded." if did in self.discarded else "")
        return {
            "id": did, "title": f"{did} · {d.vendor}",
            "header": [["Vendor", d.vendor], ["Category", cat], ["Autonomy", "suggest-only"]],
            "proposal_title": "Proposed classification & draft reply",
            "columns": ["Field", "Value"],
            "rows": [["Category", cat], ["Action taken", "none (suggest-only)"]],
            "note": ("Draft reply for a human to review and send: " + rec.reply) if rec else "",
            "verdict": verdict,
            "verdict_label": "Guard: draft ready for a human" if verdict == "PASS" else "Guard: refused",
            "reasons": reasons, "status": status,
            "actions": [
                {"action": "approve", "label": "Mark draft sent", "style": "approve", "enabled": verdict == "PASS" and status == "ready"},
                {"action": "reject", "label": "Discard draft", "style": "reject", "enabled": status == "ready"},
            ],
            "result": result_text, "audit": audit, "audit_ok": None,
        }

    def act(self, action, did):
        if action == "approve":
            _d, _rec, verdict, _r = self._run(did)
            if verdict == "PASS":
                self.sent.add(did)
        elif action == "reject":
            self.discarded.add(did)
        return self.detail(did)


# --------------------------------------------------------------------------- #
# Pattern 5: procurement approval packet
# --------------------------------------------------------------------------- #

class ProcurementAgent:
    agent_id = "procurement"
    title = "Procurement Approvals"
    actor = "procurement-agent@nordwind"
    accepts_upload = False
    inbox_label = "Requisitions"

    _ROUTE_LABEL = {
        "auto_review": "In policy — ready for approval",
        "escalation": "Escalate — policy deviation",
        "blocked_missing_docs": "Blocked — required document missing",
    }

    def __init__(self) -> None:
        self.reqs = seed_requisitions()
        self.sups = seed_suppliers()
        self._rt: dict[str, tuple] = {}   # id -> (packet, log)
        self._state: dict[str, str] = {}  # id -> outcome string

    def _rt_for(self, rid):
        if rid not in self._rt:
            log = PacketAuditLog()
            packet = assemble_packet(rid, RuleBasedNarrator(), log=log).packet
            self._rt[rid] = (packet, log)
        return self._rt[rid]

    def _status(self, rid, packet):
        st = self._state.get(rid)
        if st == "approved":
            return "posted"
        if st in ("rejected", "refused_blocked"):
            return "rejected"
        return "ready" if packet.route == "auto_review" else "exception"

    def inbox(self):
        items = []
        for rid, req in self.reqs.items():
            packet, _log = self._rt_for(rid)
            items.append({
                "id": rid, "primary": req.description,
                "secondary": f"{req.amount} {req.currency} · {req.category} · {self.sups[req.supplier_id].name}",
                "status": self._status(rid, packet),
                "reason": packet.flags[0] if packet.flags else "",
            })
        return items

    def detail(self, rid):
        packet, log = self._rt_for(rid)
        req = self.reqs[rid]
        sup = self.sups[req.supplier_id]
        status = self._status(rid, packet)
        rows = [[f"Flag {i + 1}", f] for i, f in enumerate(packet.flags)] or [["All checks", "No policy flags tripped"]]
        audit = [f"{e.actor}  {e.operation:<13} {e.target:<10} {e.outcome}" for e in log.entries]
        st = self._state.get(rid)
        result_text = {
            "approved": f"APPROVED by {self.actor}",
            "rejected": f"REJECTED by {self.actor}",
            "refused_blocked": "Refused: blocked on a missing document.",
        }.get(st, "")
        if st == "approved":
            # A human can approve an escalation; once decided, do not keep flashing the deviation red.
            verdict, verdict_label = "PASS", "Approved by a human"
        else:
            verdict = "PASS" if packet.route == "auto_review" else "FAIL"
            verdict_label = self._ROUTE_LABEL[packet.route]
        return {
            "id": rid, "title": f"{rid} · {req.description}",
            "header": [["Requester", req.requester], ["Named approver", req.approver],
                       ["Category", req.category], ["Amount", f"{req.amount} {req.currency}"],
                       ["Supplier", f"{sup.name} ({sup.country})"],
                       ["Approved vendor", "yes" if sup.approved_vendor else "no"],
                       ["Documents", ", ".join(req.attached_documents) or "none"],
                       ["Policy", f"{packet.policy_id} v{packet.policy_version}"], ["Route", packet.route]],
            "proposal_title": f"Approval packet {packet.request_id} (staged; record unchanged)",
            "columns": ["Check", "Finding"], "rows": rows,
            "note": f"{packet.risk_narrative} — {packet.recommendation}",
            "verdict": verdict, "verdict_label": verdict_label,
            "reasons": list(packet.flags), "status": status,
            "actions": [
                {"action": "approve", "label": "Approve", "style": "approve",
                 "enabled": packet.route != "blocked_missing_docs" and st is None},
                {"action": "reject", "label": "Reject", "style": "reject", "enabled": st is None},
            ],
            "result": result_text, "audit": audit, "audit_ok": log.verify(),
        }

    def act(self, action, rid):
        packet, log = self._rt_for(rid)
        if self._state.get(rid) is None:
            if action == "approve":
                self._state[rid] = record_decision(packet, approver=self.actor, approved=True, log=log)
            elif action == "reject":
                self._state[rid] = record_decision(packet, approver=self.actor, approved=False, log=log)
        return self.detail(rid)


# --------------------------------------------------------------------------- #
# Pattern 6: close orchestration
# --------------------------------------------------------------------------- #

class CloseAgent:
    agent_id = "close"
    title = "Close Cockpit"
    actor = "close-agent@nordwind"
    accepts_upload = False
    inbox_label = "Close tasks"

    _LABEL = {
        "escalate": "High risk — escalate to the close manager",
        "resequence": "At risk — resequence the deadline",
        "remind": "Watch — reminder proposed",
    }

    def __init__(self) -> None:
        self._plan = seed_close_plan()
        self._log = InterventionLog()
        self._scorer = RuleBasedScorer()
        self._state: dict[str, str] = {}   # task_id -> outcome

    def _predict(self):
        ranked, staged = predict_and_stage(self._plan, self._scorer)
        by_task = {r.prediction.task_id: r for r in ranked}
        staged_by = {s.mitigation.task_id: s for s in staged}
        return by_task, staged_by

    def _status(self, tid, task, staged_by):
        st = self._state.get(tid)
        if st == "applied":
            return "posted"
        if st == "rejected_by_human":
            return "rejected"
        if task.status == "done":
            return "done"
        return "exception" if tid in staged_by else "ready"

    def inbox(self):
        by_task, staged_by = self._predict()
        items = []
        for task in self._plan.tasks:
            pred = by_task[task.task_id].prediction
            items.append({
                "id": task.task_id, "primary": task.name,
                "secondary": f"{task.owner} · due {task.deadline} · {task.impact} · {task.status}",
                "status": self._status(task.task_id, task, staged_by),
                "reason": pred.reasons[0] if (task.task_id in staged_by and pred.reasons) else "",
            })
        return items

    def detail(self, tid):
        by_task, staged_by = self._predict()
        entry = by_task[tid]
        task = self._plan.get(tid)
        pred, mit = entry.prediction, entry.mitigation
        staged = staged_by.get(tid)
        status = self._status(tid, task, staged_by)
        before = mit.before_deadline if (mit and mit.before_deadline) else task.deadline
        after = mit.after_deadline if (mit and mit.after_deadline) else "(no change)"
        audit = [f"{e.trace_id}  {e.actor}  {e.operation:<10} {e.target:<10} {e.outcome}" for e in self._log.entries]
        st = self._state.get(tid)
        result_text = ""
        if st == "applied":
            result_text = f"Applied {mit.action if mit else 'intervention'}; {tid} deadline now {task.deadline}."
            verdict, verdict_label = "PASS", "Intervention applied"
        elif st == "rejected_by_human":
            result_text = "Dismissed by a human."
            verdict, verdict_label = "PASS", "Dismissed by a human"
        else:
            verdict = "FAIL" if staged else "PASS"
            verdict_label = self._LABEL.get(mit.action if mit else "", "On track")
        return {
            "id": tid, "title": f"{tid} · {task.name}",
            "header": [["Owner", task.owner], ["Status", task.status], ["Deadline", task.deadline],
                       ["Impact", f"{task.impact}"], ["Depends on", ", ".join(task.depends_on) or "none"],
                       ["Block score", f"{pred.score}"], ["Proposed action", mit.action if mit else "none"]],
            "proposal_title": (f"Proposed intervention {staged.staged_id}: {mit.action} {tid}"
                               if staged else "No intervention — task on track"),
            "columns": ["Field", "Before", "After"],
            "rows": [["Deadline", before, after]],
            "note": mit.detail if mit else "",
            "verdict": verdict,
            "verdict_label": verdict_label,
            "reasons": list(pred.reasons), "status": status,
            "actions": [
                {"action": "approve", "label": "Apply intervention", "style": "approve",
                 "enabled": staged is not None and st is None},
                {"action": "reject", "label": "Dismiss", "style": "reject",
                 "enabled": staged is not None and st is None},
            ],
            "result": result_text, "audit": audit, "audit_ok": None,
        }

    def act(self, action, tid):
        _by, staged_by = self._predict()
        staged = staged_by.get(tid)
        if staged is not None and self._state.get(tid) is None:
            approved = action == "approve"
            res = run_intervention(self._plan, staged, approve=lambda s, p: approved, log=self._log)
            self._plan = res.plan
            self._state[tid] = res.outcome
        return self.detail(tid)


# --------------------------------------------------------------------------- #
# Pattern 7: service resolution
# --------------------------------------------------------------------------- #

_P7_MAP = {
    "allow": ("PASS", "ALLOW", "ready"),
    "needs-approval": ("FAIL", "NEEDS-APPROVAL", "exception"),
    "deny": ("FAIL", "DENY", "rejected"),
}


class ServiceAgent:
    agent_id = "service"
    title = "Service Resolution Assist"
    actor = "service-agent@nordwind"
    accepts_upload = False
    inbox_label = "Service cases"
    CASE_IDS = ["CASE-501", "CASE-502", "CASE-503"]

    def __init__(self) -> None:
        self._proposer = ServiceProposer()
        self._config = service_config()
        self._done: dict[str, tuple] = {}   # id -> (FlowResult, source)

    def _compute(self, cid):
        src = GovernedServiceSource(MockServiceSource(), entitlements={"read"})
        ctx = src.gather_context(cid)
        step = self._proposer.propose(ctx)
        return ctx, step, service_evaluate(ctx, step, config=self._config)

    def _status(self, cid, dec):
        if cid in self._done:
            res, _s = self._done[cid]
            return "done" if res.outcome == "done" else "rejected"
        return _P7_MAP[dec.verdict][2]

    def inbox(self):
        items = []
        for cid in self.CASE_IDS:
            ctx, _step, dec = self._compute(cid)
            items.append({
                "id": cid, "primary": ctx.case.site,
                "secondary": ctx.case.reported_symptom,
                "status": self._status(cid, dec),
                "reason": dec.reason if dec.verdict != "allow" else "",
            })
        return items

    def detail(self, cid):
        ctx, step, dec = self._compute(cid)
        vp, vlabel, _base = _P7_MAP[dec.verdict]
        status = self._status(cid, dec)
        if cid in self._done:
            res, src = self._done[cid]
            audit = [f"{e.actor}  {e.operation:<8} {e.target:<12} {e.outcome}" for e in src.audit_log]
            audit_ok = src.verify_audit()
            result_text = (f"Executed as {res.action_result.action_id}" if res.outcome == "done"
                           else "Declined by a human — nothing executed.")
        else:
            audit, audit_ok, result_text = [], None, ""
        acts_on = dec.verdict == "allow" and cid not in self._done
        return {
            "id": cid, "title": f"{cid} · {ctx.case.site}",
            "header": [["Case", ctx.case.case_id], ["Site", ctx.case.site],
                       ["Symptom", ctx.case.reported_symptom],
                       ["Asset", f"{ctx.asset.asset_id} ({ctx.asset.model})"],
                       ["Plan", ctx.entitlement.plan], ["In warranty", str(ctx.entitlement.in_warranty)],
                       ["Approval limit", str(ctx.entitlement.approval_limit)]],
            "proposal_title": "Proposed next step",
            "columns": ["Step", "Part", "Est. cost", "Rationale"],
            "rows": [[step.kind, step.part_id or "-", str(step.estimated_cost), step.rationale]],
            "note": dec.reason,
            "verdict": vp, "verdict_label": f"Guard: {vlabel}", "reasons": [dec.reason], "status": status,
            "actions": [
                {"action": "approve", "label": "Confirm & execute", "style": "approve", "enabled": acts_on},
                {"action": "reject", "label": "Decline", "style": "reject", "enabled": acts_on},
            ],
            "result": result_text, "audit": audit, "audit_ok": audit_ok,
        }

    def act(self, action, cid):
        if cid not in self._done:
            _c, _s, dec = self._compute(cid)
            if dec.verdict == "allow":
                src = GovernedServiceSource(MockServiceSource(), entitlements={"read", "stage", "execute"})
                res = run_pattern7(src, self._proposer, cid, config=self._config,
                                   confirm=lambda *_: action == "approve")
                self._done[cid] = (res, src)
        return self.detail(cid)


# --------------------------------------------------------------------------- #
# Pattern 8: cash application
# --------------------------------------------------------------------------- #

_P8_MAP = {"MATCH": ("PASS", "ready"), "PARTIAL": ("FAIL", "exception"),
           "OVERPAID": ("FAIL", "exception"), "REJECT": ("FAIL", "rejected")}


class CashAppAgent:
    agent_id = "cashapp"
    title = "Cash Application"
    actor = "ar-agent@nordwind"
    accepts_upload = False
    inbox_label = "Incoming payments"

    def __init__(self) -> None:
        self._matcher = RuleBasedMatcher()
        self._config = cash_config()
        self._ledger = MockArLedger()       # one ledger per session: clearing is idempotent
        self._done: dict[str, object] = {}  # id -> FlowResult

    def _compute(self, pid):
        pay = SAMPLE_PAYMENTS[pid]
        proposal = self._matcher.propose(pay, self._ledger.open_invoices())
        return pay, proposal, check_match(pay, proposal, self._ledger, config=self._config)

    def _status(self, pid, verdict):
        if pid in self._done:
            return "posted" if self._done[pid].outcome == "cleared" else "rejected"
        return _P8_MAP[verdict.verdict][1]

    def inbox(self):
        items = []
        for pid, pay in SAMPLE_PAYMENTS.items():
            _p, _pr, verdict = self._compute(pid)
            items.append({
                "id": pid, "primary": pay.customer,
                "secondary": f"{pay.amount} {pay.currency}",
                "status": self._status(pid, verdict),
                "reason": verdict.reasons[0] if (verdict.verdict != "MATCH" and verdict.reasons) else "",
            })
        return items

    def detail(self, pid):
        pay = SAMPLE_PAYMENTS[pid]
        if pid in self._done:
            # Show the verdict from the moment of clearing; the ledger has moved on.
            res = self._done[pid]
            proposal, verdict = res.proposal, res.verdict
            inv_by = {}
            audit = list(res.log.entries) if res.log else []
            result_text = (f"Cleared as {res.clearing.clearing_id} → {', '.join(res.clearing.invoice_ids)}"
                           if res.outcome == "cleared" else "Rejected by a human.")
        else:
            _p, proposal, verdict = self._compute(pid)
            inv_by = {inv.invoice_id: inv for inv in self._ledger.open_invoices()}
            audit, result_text = [], ""
        status = self._status(pid, verdict)
        rows = [[iid, str(inv_by[iid].amount) if iid in inv_by else "(cleared)",
                 "yes" if (iid in inv_by and inv_by[iid].is_credit_note) else "-"]
                for iid in proposal.invoice_ids] or [["(none)", "-", "-"]]
        return {
            "id": pid, "title": f"{pid} · {pay.customer}",
            "header": [["Payment", pay.payment_id], ["Customer", pay.customer],
                       ["Amount", f"{pay.amount} {pay.currency}"], ["Value date", pay.value_date],
                       ["Matched total", str(verdict.matched_total)], ["Difference", str(verdict.difference)]],
            "proposal_title": f"Proposed clearing — {proposal.note}",
            "columns": ["Invoice", "Amount", "Credit note?"], "rows": rows,
            "note": "; ".join(verdict.reasons),
            "verdict": _P8_MAP[verdict.verdict][0], "verdict_label": verdict.verdict,
            "reasons": list(verdict.reasons), "status": status,
            "actions": [
                {"action": "approve", "label": "Approve & clear", "style": "approve",
                 "enabled": verdict.is_match and pid not in self._done},
                {"action": "reject", "label": "Reject", "style": "reject",
                 "enabled": verdict.is_match and pid not in self._done},
            ],
            "result": result_text, "audit": audit, "audit_ok": None,
        }

    def act(self, action, pid):
        if pid not in self._done:
            _p, _pr, verdict = self._compute(pid)
            if verdict.is_match:
                res = run_cash_application(self._ledger, self._matcher, SAMPLE_PAYMENTS[pid],
                                           config=self._config, approve=lambda *_: action == "approve")
                self._done[pid] = res
        return self.detail(pid)


# --------------------------------------------------------------------------- #
# Pattern 9: sales order
# --------------------------------------------------------------------------- #

class SalesOrderAgent:
    agent_id = "salesorder"
    title = "Sales Order Desk"
    actor = "sales-agent@nordwind"
    accepts_upload = False
    inbox_label = "Customer requests"

    def __init__(self) -> None:
        self._requests = load_requests()
        self._proposer = SalesProposer()
        self._config = sales_config()
        self._clients: dict[str, object] = {}   # id -> GovernedSalesClient
        self._done: dict[str, tuple] = {}        # id -> (outcome, order_id|None)

    def _client(self, rid):
        if rid not in self._clients:
            self._clients[rid] = GovernedSalesClient(MockSalesClient(), entitlements={"stage", "release"})
        return self._clients[rid]

    def _compute(self, rid):
        client = self._client(rid)
        req = self._requests[rid]
        extracted = self._proposer.extract(req, catalog=client.catalog)
        order = price_order(req, extracted, catalog=client.catalog)
        guard = guard_order(order, customers=client.customers, catalog=client.catalog, config=self._config)
        return req, order, guard, client

    def _status(self, rid, guard):
        st = self._done.get(rid)
        if st and st[0] == "released":
            return "posted"
        if st and st[0] == "rejected":
            return "rejected"
        return "ready" if guard.status == "PASS" else "exception"

    def inbox(self):
        items = []
        for rid, req in self._requests.items():
            _r, _o, guard, _c = self._compute(rid)
            items.append({
                "id": rid, "primary": req.customer_id,
                "secondary": (req.text[:70] + "…") if len(req.text) > 70 else req.text,
                "status": self._status(rid, guard),
                "reason": guard.reasons[0] if (guard.status != "PASS" and guard.reasons) else "",
            })
        return items

    def detail(self, rid):
        req, order, guard, client = self._compute(rid)
        status = self._status(rid, guard)
        customer = client.customers.get(req.customer_id)
        cust_label = f"{customer.name} ({req.customer_id})" if customer else req.customer_id
        rows = [[str(l.quantity), l.sku, l.name, f"{l.unit_price} {order.currency}",
                 f"{l.line_total} {order.currency}"] for l in order.lines] or [["-", "(no valid lines)", "-", "-", "-"]]
        st = self._done.get(rid)
        audit = [f"{e.actor}  {e.operation:<8} {e.target:<14} {e.outcome}" for e in client.audit_log]
        audit_ok = client.verify_audit() if client.audit_log else None
        result_text = ""
        if st and st[0] == "released":
            result_text = f"Released to fulfillment as {st[1]}."
        elif st and st[0] == "rejected":
            result_text = "Rejected by a human."
        return {
            "id": rid, "title": f"{rid} · {cust_label}",
            "header": [["Request", req.request_id], ["Customer", cust_label], ["Ship-to", order.ship_to_country],
                       ["Requested delivery", order.requested_delivery], ["Discount", f"{order.discount_pct}%"]],
            "proposal_title": "Proposed draft sales order",
            "columns": ["Qty", "SKU", "Name", "Unit price", "Line total"], "rows": rows,
            "note": f"Order total: {order.order_total} {order.currency}",
            "verdict": "PASS" if guard.status == "PASS" else "FAIL",
            "verdict_label": "In policy — ready to release" if guard.status == "PASS" else "Flagged by guard — needs human review",
            "reasons": list(guard.reasons), "status": status,
            "actions": [
                {"action": "approve", "label": "Approve & release", "style": "approve",
                 "enabled": guard.status == "PASS" and rid not in self._done},
                {"action": "reject", "label": "Reject", "style": "reject",
                 "enabled": guard.status == "PASS" and rid not in self._done},
            ],
            "result": result_text, "audit": audit, "audit_ok": audit_ok,
        }

    def act(self, action, rid):
        if rid not in self._done:
            _req, order, guard, client = self._compute(rid)
            if guard.status == "PASS":
                if action == "approve":
                    staged = client.stage_order(order)
                    client.record_approval(staged.staged_id, approver="sales-manager")
                    release = client.release_order(staged.staged_id)
                    self._done[rid] = ("released", release.order_id)
                elif action == "reject":
                    self._done[rid] = ("rejected", None)
        return self.detail(rid)


# --------------------------------------------------------------------------- #
# Pattern 10: expense audit
# --------------------------------------------------------------------------- #

class ExpenseAgent:
    agent_id = "expense"
    title = "Expense Audit"
    actor = "expense-agent@nordwind"
    accepts_upload = False
    inbox_label = "Expense reports"

    def __init__(self) -> None:
        self._reports = sample_reports()
        self._policy = expense_policy()
        self._drafter = RuleBasedDrafter()
        self._done: dict[str, str] = {}

    def _run(self, rid):
        rpt = self._reports[rid]
        return rpt, audit_report(rpt, policy=self._policy, drafter=self._drafter)

    def _status(self, rid, result):
        st = self._done.get(rid)
        if st == "approved":
            return "posted"
        if st == "rejected":
            return "rejected"
        return "exception" if any(not d.compliant for d in result.decisions) else "ready"

    def inbox(self):
        items = []
        for rid, rpt in self._reports.items():
            _r, result = self._run(rid)
            viol = [d for d in result.decisions if not d.compliant]
            items.append({
                "id": rid, "primary": rpt.employee,
                "secondary": f"{len(rpt.lines)} lines · {rpt.currency}",
                "status": self._status(rid, result),
                "reason": f"{len(viol)} line(s) need review" if viol else "",
            })
        return items

    def detail(self, rid):
        rpt, result = self._run(rid)
        status = self._status(rid, result)
        rows = []
        for line, d in zip(rpt.lines, result.decisions):
            rows.append([line.line_id, line.category, f"{line.claimed_amount} {rpt.currency}",
                         f"{line.receipt_total} {rpt.currency}", line.date,
                         "COMPLIANT" if d.compliant else "VIOLATION", d.route, d.approver])
        violations = [d for d in result.decisions if not d.compliant]
        reasons = [f"{d.line_id}: {c}" for d in result.decisions for c in d.failed_checks]
        st = self._done.get(rid)
        if st == "approved":
            verdict, verdict_label, result_text = "PASS", "Exceptions approved by a human", "Exceptions approved."
        elif st == "rejected":
            verdict, verdict_label, result_text = "PASS", "Report rejected", "Report rejected."
        else:
            verdict = "FAIL" if violations else "PASS"
            verdict_label = (f"{len(violations)} line(s) need human review" if violations
                             else "All lines compliant — fast approval")
            result_text = ""
        return {
            "id": rid, "title": f"{rid} · {rpt.employee}",
            "header": [["Report", rpt.report_id], ["Employee", rpt.employee],
                       ["Currency", rpt.currency], ["Policy", self._policy.version]],
            "proposal_title": f"Per-line audit against policy {self._policy.version}",
            "columns": ["Line", "Category", "Claim", "Receipt", "Date", "Verdict", "Route", "Approver"],
            "rows": rows,
            "note": "Routes: " + ", ".join(f"{d.line_id}->{d.route}" for d in result.decisions),
            "verdict": verdict, "verdict_label": verdict_label,
            "reasons": reasons, "status": status,
            "actions": [
                {"action": "approve", "label": "Approve exceptions", "style": "approve",
                 "enabled": bool(violations) and st is None},
                {"action": "reject", "label": "Reject report", "style": "reject", "enabled": st is None},
            ],
            "result": result_text, "audit": list(result.log), "audit_ok": None,
        }

    def act(self, action, rid):
        if self._done.get(rid) is None:
            if action == "approve":
                self._done[rid] = "approved"
            elif action == "reject":
                self._done[rid] = "rejected"
        return self.detail(rid)


EXTRA_AGENT_CLASSES = [
    ThreeWayMatchAgent, DisputeAgent, ProcurementAgent, CloseAgent,
    ServiceAgent, CashAppAgent, SalesOrderAgent, ExpenseAgent,
]


def build_extra_agents():
    """Instantiate the eight adapters, skipping any that fail to construct so one
    broken pattern never takes the whole console down."""
    agents = []
    for cls in EXTRA_AGENT_CLASSES:
        try:
            agents.append(cls())
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[console] skipping {cls.__name__}: {exc}")
    return agents
