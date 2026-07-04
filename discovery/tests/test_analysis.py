"""The analyses on top of the register: opportunity map, custom-vs-standard,
governance, and the diagrams (mermaid + valid BPMN). All offline."""

import xml.etree.ElementTree as ET

from discovery.diagrams import (
    Branch,
    ProcessModel,
    ProcessStep,
    dependency_mermaid,
    design_brief,
    process_bpmn,
    propose_process,
    validate_process,
)
from discovery.landscape import custom_vs_standard, governance_summary
from discovery.opportunity import opportunity_map
from discovery.register import build_register
from discovery.sources import MockRepositorySource

NS = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}


def _mock():
    return build_register(MockRepositorySource())


# --- opportunity map ----------------------------------------------------------

def test_opportunity_map_ranks_and_maps_to_the_pattern_catalog():
    by_name = {o.process.name: o for o in opportunity_map(_mock())}
    ap = by_name["Accounts payable invoice-to-pay"]
    assert ap.tier == "strong"
    assert ap.pattern.startswith("Pattern 1")  # driven by the process name, not its objects
    assert by_name["Three-way match"].pattern.startswith("Pattern 3")


def test_low_volume_is_a_weak_opportunity_even_when_manual():
    disputes = {o.process.name: o for o in opportunity_map(_mock())}["Vendor dispute handling"]
    assert disputes.tier == "weak"
    assert any("low volume" in r for r in disputes.reasons)
    assert disputes.pattern.startswith("Pattern 4")  # dispute copilot


# --- custom vs standard + governance ------------------------------------------

def test_custom_vs_standard_finds_the_standard_touchpoints():
    view = custom_vs_standard(_mock())
    touched = {t.name: set(t.touched_by) for t in view.touchpoints}
    assert touched["LFA1"] == {"ZTHREEWAY_TOL", "Z_I_OPEN_AP_ITEMS"}
    assert touched["BKPF"] == {"ZFI_TRIAGE_PROG", "ZZ_APPROVAL_LANE"}
    assert "ZTHREEWAY_TOL" not in touched  # it is custom, not a standard touchpoint
    assert len(view.custom) == 9


def test_governance_flags_the_level_d_risk_with_owner():
    items = {g.name: g for g in governance_summary(_mock())}
    assert "ZEI_INVOICE_POST" in items
    assert items["ZEI_INVOICE_POST"].level == "D"
    assert items["ZEI_INVOICE_POST"].business_owner == "Tax team"


# --- diagrams -----------------------------------------------------------------

def test_dependency_mermaid_styles_custom_and_standard_apart():
    m = dependency_mermaid(_mock())
    assert m.startswith("graph LR")
    assert "ZTHREEWAY_TOL --> LFA1" in m
    assert "classDef standard" in m
    # focus narrows to the tax cluster
    focused = dependency_mermaid(_mock(), focus="tax")
    assert "Z_TAX_DETERMINE_NW" in focused
    assert "ZTHREEWAY_TOL" not in focused


def test_proposed_process_is_valid_and_grounded():
    reg = _mock()
    model = propose_process(reg, "three-way match")
    assert validate_process(model, reg) == []
    assert len(model.branches) == 3


def test_validate_process_rejects_an_invented_object_name():
    reg = _mock()
    bad = ProcessModel(
        "x", "x", "start", ProcessStep("t", "Uses ZINVENTED_TABLE"), "which?",
        (Branch("a", ProcessStep("p", "Post")), Branch("b", ProcessStep("q", "Hold"))), (),
    )
    findings = validate_process(bad, reg)
    assert any("ZINVENTED_TABLE" in f for f in findings)


def test_generated_bpmn_is_valid_and_signavio_shaped():
    reg = _mock()
    model = propose_process(reg, "three-way match")
    root = ET.fromstring(process_bpmn(model))
    proc = root.find("bpmn:process", NS)
    assert proc is not None
    assert proc.find("bpmn:startEvent", NS) is not None
    gw = proc.find("bpmn:exclusiveGateway", NS)
    assert len(gw.findall("bpmn:outgoing", NS)) == len(model.branches)
    tasks = {t.get("id") for t in proc.findall("bpmn:task", NS)}
    flows = {f.get("id"): f.get("targetRef") for f in proc.findall("bpmn:sequenceFlow", NS)}
    for b in model.branches:
        assert flows[f"flow_{b.label}"] in tasks  # every branch routes to a named task


def test_design_brief_is_grounded_and_honest():
    md = design_brief(_mock(), "three-way match").to_markdown()
    assert "ZTHREEWAY_TOL" in md
    assert "```mermaid" in md
    assert "not process mining" in md.lower()
    # and its bpmn parses
    ET.fromstring(design_brief(_mock(), "three-way match").bpmn)
