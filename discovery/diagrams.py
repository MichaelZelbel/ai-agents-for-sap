"""Draw the landscape and design for it.

Two deterministic, offline drawings:
- `dependency_mermaid` renders the register as a mermaid graph, custom objects and
  the standard objects they lean on styled apart.
- `propose_process` builds a small process model grounded on the register, and
  `process_mermaid` / `process_bpmn` render it as a mermaid flowchart and as BPMN 2.0
  XML you import into SAP Signavio or SAP Build Process Automation (they lay it out on
  import). `design_brief` combines the grounding, the process, and the fit-to-standard
  scorecard for one job.

This draws the design and the landscape from the static register (what exists, what
it leans on, a proposed process shape). It is not process mining: it does not show
how the process actually runs from event logs. For that you use SAP Signavio Process
Insights against a live system.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .models import ObjectRegister, _norm
from .register import to_grounding
from .scorecard import FitScore, fit_to_standard_scorecard

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


def _mid(name: str) -> str:
    """A mermaid-safe node id."""
    return re.sub(r"\W+", "_", name).strip("_") or "n"


def dependency_mermaid(register: ObjectRegister, *, focus: str = "") -> str:
    """A mermaid dependency graph of the register. Custom objects are solid; the
    standard SAP objects they lean on are dashed, so clean core reads at a glance."""
    objects = register.objects
    if focus:
        hit = list(register.search(focus))
        needed = {o.name.upper() for o in hit}
        for o in hit:
            needed.update(d.upper() for d in o.depends_on)
        objects = tuple(o for o in register.objects if o.name.upper() in needed)

    custom_names = {o.name.upper() for o in register.objects}
    lines = ["graph LR"]
    standard: set[str] = set()
    for o in objects:
        lines.append(f'    {_mid(o.name)}["{o.name}"]')
        for dep in o.depends_on:
            lines.append(f"    {_mid(o.name)} --> {_mid(dep)}")
            if dep.upper() not in custom_names:
                standard.add(dep)
    for s in sorted(standard):
        lines.append(f'    {_mid(s)}(["{s}"])')
    lines.append("    classDef standard stroke-dasharray: 4 3;")
    if standard:
        lines.append("    class " + ",".join(_mid(s) for s in sorted(standard)) + " standard;")
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class ProcessStep:
    id: str
    name: str


@dataclass(frozen=True)
class Branch:
    label: str
    to: ProcessStep


@dataclass(frozen=True)
class ProcessModel:
    id: str
    name: str
    start_name: str
    task: ProcessStep
    gateway_name: str
    branches: tuple[Branch, ...]
    grounded_on: tuple[str, ...]


def propose_process(register: ObjectRegister, focus: str) -> ProcessModel:
    """A proposed process for a job, grounded on the register's objects. Deterministic
    templates for the jobs the book knows; a generic propose-and-route shape otherwise."""
    hit = list(register.search(focus))
    grounded = tuple(o.name for o in hit)
    lead = f" (uses {grounded[0]})" if grounded else ""
    key = _norm(focus)

    if "three way" in key or "match" in key:
        return ProcessModel(
            id="three_way_match", name="Three-way match", start_name="Invoice arrives",
            task=ProcessStep("match", f"Three-way match{lead}"),
            gateway_name="Within tolerance?",
            branches=(
                Branch("within_tolerance", ProcessStep("post", "Draft posting, approve, write")),
                Branch("over_tolerance", ProcessStep("buyer", "Route to a buyer")),
                Branch("missing_receipt", ProcessStep("hold", "Hold for goods receipt")),
            ),
            grounded_on=grounded,
        )
    if "triage" in key or "route" in key or "classify" in key:
        return ProcessModel(
            id="document_triage", name="Document triage", start_name="Document arrives",
            task=ProcessStep("triage", f"Triage document{lead}"),
            gateway_name="Document type?",
            branches=(
                Branch("po_invoice", ProcessStep("threeway", "Three-way match")),
                Branch("direct_expense", ProcessStep("post", "Draft posting, approve, write")),
                Branch("not_an_invoice", ProcessStep("person", "Send to a person")),
            ),
            grounded_on=grounded,
        )
    return ProcessModel(
        id="proposed_process", name=focus.strip() or "Proposed process",
        start_name="Case arrives",
        task=ProcessStep("assess", f"Assess the case{lead}"),
        gateway_name="Which path?",
        branches=(
            Branch("standard", ProcessStep("apply", "Apply the standard path, approve, write")),
            Branch("exception", ProcessStep("person", "Send to a person")),
        ),
        grounded_on=grounded,
    )


def validate_process(model: ProcessModel, register: ObjectRegister) -> list[str]:
    """Findings that would make the process malformed or dishonest: too few branches,
    duplicate ids, a branch that routes nowhere, or an invented Z*/Y* object name in a
    step (the guard against an LLM-proposed process naming objects that do not exist)."""
    findings: list[str] = []
    if len(model.branches) < 2:
        findings.append("a gateway needs at least two branches")
    ids = [model.task.id] + [b.to.id for b in model.branches]
    if len(ids) != len(set(ids)):
        findings.append("step ids must be unique")
    for b in model.branches:
        if not b.to.name.strip():
            findings.append(f"branch {b.label!r} routes to an unnamed step")
    names = [model.start_name, model.task.name] + [b.to.name for b in model.branches]
    for token in re.findall(r"\b[ZY][A-Z0-9_]{2,}\b", " ".join(names)):
        if register.by_name(token) is None:
            findings.append(f"step names an object not in the register: {token}")
    return findings


def process_mermaid(model: ProcessModel) -> str:
    lines = ["flowchart TD", f'    start(["{model.start_name}"])', f'    {model.task.id}["{model.task.name}"]']
    lines.append(f'    gw{{"{model.gateway_name}"}}')
    lines.append(f"    start --> {model.task.id}")
    lines.append(f"    {model.task.id} --> gw")
    for b in model.branches:
        lines.append(f'    gw -- "{b.label}" --> {b.to.id}["{b.to.name}"]')
    return "\n".join(lines) + "\n"


def process_bpmn(model: ProcessModel) -> str:
    """BPMN 2.0 XML for the proposed process, shaped exactly like the repo's static
    accounts-payable.bpmn, so it parses the same way and imports into Signavio / SAP
    Build (which lay it out on import; no diagram-interchange coordinates needed)."""
    ET.register_namespace("bpmn", BPMN_NS)
    ET.register_namespace("xsi", XSI_NS)

    def q(tag: str) -> str:
        return f"{{{BPMN_NS}}}{tag}"

    defs = ET.Element(
        q("definitions"),
        {"id": f"{model.id}_defs", "targetNamespace": "http://nordwind.example/proposed"},
    )
    proc = ET.SubElement(
        defs, q("process"), {"id": model.id, "name": model.name, "isExecutable": "false"}
    )

    f_start = "flow_start_task"
    f_gateway = "flow_task_gateway"

    start = ET.SubElement(proc, q("startEvent"), {"id": "start", "name": model.start_name})
    ET.SubElement(start, q("outgoing")).text = f_start

    task = ET.SubElement(proc, q("task"), {"id": model.task.id, "name": model.task.name})
    ET.SubElement(task, q("incoming")).text = f_start
    ET.SubElement(task, q("outgoing")).text = f_gateway

    gw = ET.SubElement(proc, q("exclusiveGateway"), {"id": "route", "name": model.gateway_name})
    ET.SubElement(gw, q("incoming")).text = f_gateway
    for b in model.branches:
        ET.SubElement(gw, q("outgoing")).text = f"flow_{b.label}"

    for b in model.branches:
        ET.SubElement(proc, q("task"), {"id": b.to.id, "name": b.to.name})

    ET.SubElement(proc, q("sequenceFlow"), {"id": f_start, "sourceRef": "start", "targetRef": model.task.id})
    ET.SubElement(proc, q("sequenceFlow"), {"id": f_gateway, "sourceRef": model.task.id, "targetRef": "route"})
    for b in model.branches:
        flow = ET.SubElement(
            proc, q("sequenceFlow"),
            {"id": f"flow_{b.label}", "name": b.label, "sourceRef": "route", "targetRef": b.to.id},
        )
        cond = ET.SubElement(flow, q("conditionExpression"), {f"{{{XSI_NS}}}type": "bpmn:tFormalExpression"})
        cond.text = f"category == '{b.label}'"

    xml = ET.tostring(defs, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml + "\n"


@dataclass(frozen=True)
class DesignBrief:
    focus: str
    grounding_md: str
    process: ProcessModel
    mermaid: str
    bpmn: str
    scorecard: tuple[FitScore, ...]

    def to_markdown(self) -> str:
        lines = [f"# Design for: {self.focus}", "", "## Your objects for this job", "", self.grounding_md.strip(), ""]
        lines += ["## Proposed process", "", "```mermaid", self.mermaid.strip(), "```", ""]
        if self.scorecard:
            lines += ["## Fit-to-standard for these objects", ""]
            for s in self.scorecard:
                lines.append(f"- **{s.obj.name}**: {s.move} ({s.tier}). " + "; ".join(s.reasons))
            lines.append("")
        lines += [
            "> This draws a proposed design from the static register. It is not process "
            "mining, and it does not show how the process runs today. Validate against your "
            "tenant, and let a human rule on any fit-to-standard call.",
        ]
        return "\n".join(lines).rstrip() + "\n"


def design_brief(register: ObjectRegister, focus: str) -> DesignBrief:
    process = propose_process(register, focus)
    matched = {o.name for o in register.search(focus)}
    scorecard = tuple(s for s in fit_to_standard_scorecard(register) if s.obj.name in matched)
    return DesignBrief(
        focus=focus,
        grounding_md=to_grounding(register, focus=focus),
        process=process,
        mermaid=process_mermaid(process),
        bpmn=process_bpmn(process),
        scorecard=scorecard,
    )
