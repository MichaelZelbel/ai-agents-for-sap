"""Prove the BPMN model and the agent agree.

The diagram a real SAP team draws (in Signavio or SAP Build) is the spec. This test
parses the exported BPMN 2.0 and checks that the branches out of the Triage gateway
are exactly the categories the agent classifies into, and that each one routes
somewhere. If someone edits the process, this test tells you the agent is now out of
step with it.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

from triage import CATEGORIES

BPMN = Path(__file__).resolve().parents[1] / "process" / "accounts-payable.bpmn"
NS = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}


def _branches() -> dict[str, str]:
    """Map each gateway branch label to the name of the task it routes to."""
    proc = ET.parse(BPMN).getroot().find("bpmn:process", NS)
    task_name = {t.get("id"): t.get("name") for t in proc.findall("bpmn:task", NS)}
    gateway = proc.find("bpmn:exclusiveGateway", NS)
    out_ids = {o.text for o in gateway.findall("bpmn:outgoing", NS)}
    branches = {}
    for flow in proc.findall("bpmn:sequenceFlow", NS):
        if flow.get("id") in out_ids:
            branches[flow.get("name")] = task_name.get(flow.get("targetRef"))
    return branches


def test_the_diagram_has_a_triage_task():
    names = {t.get("name") for t in ET.parse(BPMN).getroot().iter(f"{{{NS['bpmn']}}}task")}
    assert "Triage document" in names


def test_diagram_branches_are_exactly_the_agents_categories():
    assert set(_branches()) == set(CATEGORIES)


def test_every_branch_routes_to_a_named_next_step():
    for label, target in _branches().items():
        assert target, f"branch {label!r} routes nowhere"
