"""The object register runs offline: build it, query it, check it, ground with it."""

from discovery.models import CustomObject, ObjectRegister
from discovery.register import (
    RETIREMENT_THRESHOLD,
    build_register,
    fit_to_standard_findings,
    to_grounding,
)
from discovery.sources import AbapRepositorySource, MockRepositorySource


def test_build_register_from_the_mock_system():
    reg = build_register(MockRepositorySource())
    assert "Nordwind" in reg.system
    assert len(reg.objects) >= 8
    counts = reg.counts()
    assert counts.get("table", 0) >= 1
    assert counts.get("custom_field", 0) >= 1
    assert counts.get("transaction", 0) >= 1


def test_search_finds_the_custom_parts_of_a_job():
    reg = build_register(MockRepositorySource())
    hits = {o.name for o in reg.search("three-way")}
    assert "ZTHREEWAY_TOL" in hits


def test_dependents_walk_the_relationships():
    reg = build_register(MockRepositorySource())
    dependents = {o.name for o in reg.dependents_of("ZTHREEWAY_TOL")}
    # the triage program and the dispute router both read the tolerance table
    assert "ZFI_TRIAGE_PROG" in dependents
    assert "ZCL_DISPUTE_ROUTER" in dependents


def test_fit_to_standard_flags_standard_matches_and_dead_wood():
    reg = build_register(MockRepositorySource())
    findings = " ".join(fit_to_standard_findings(reg))
    assert "ZTHREEWAY_TOL" in findings  # has a standard alternative
    assert "ZCL_DISPUTE_ROUTER" in findings  # barely used, retirement candidate


def test_grounding_focus_includes_the_objects_and_their_dependencies():
    reg = build_register(MockRepositorySource())
    grounding = to_grounding(reg, focus="tax")
    assert "Z_TAX_DETERMINE_NW" in grounding
    assert "ZTAX_RULES" in grounding  # a dependency of the tax function, pulled in
    assert "do not invent" in grounding.lower() or "not invent" in grounding.lower()


def test_grounding_admits_when_it_has_nothing():
    reg = build_register(MockRepositorySource())
    grounding = to_grounding(reg, focus="payroll")
    assert "payroll" in grounding.lower()
    assert "nothing custom" in grounding.lower()


def test_retirement_threshold_is_honest_about_low_usage():
    reg = ObjectRegister(
        system="test",
        objects=(
            CustomObject("ZQUIET", "class", "ZX", "rarely used", monthly_uses=RETIREMENT_THRESHOLD - 1),
            CustomObject("ZBUSY", "class", "ZX", "used a lot", monthly_uses=RETIREMENT_THRESHOLD + 100),
        ),
    )
    findings = " ".join(fit_to_standard_findings(reg))
    assert "ZQUIET" in findings
    assert "ZBUSY" not in findings


def test_real_source_maps_repository_rows_through_a_fake_transport():
    # AbapRepositorySource is testable offline: feed it a fake transport that
    # returns TADIR-shaped rows and check the mapping, no SAP needed.
    def fake_transport(query, params):
        assert query == "repository_objects"
        return [
            {"object": "TABL", "obj_name": "ZORDERS", "devclass": "ZSD", "author": "X", "description": "d"},
            {"object": "TRAN", "obj_name": "ZSD01", "devclass": "ZSD", "author": "X", "description": "d"},
            {"object": "SICF", "obj_name": "ZNODE", "devclass": "ZSD", "author": "X"},  # unmapped type
        ]

    source = AbapRepositorySource(fake_transport, system="Test Tenant")
    reg = build_register(source)
    names = {o.name for o in reg.objects}
    assert names == {"ZORDERS", "ZSD01"}  # the SICF row is skipped, not guessed at
    assert reg.by_name("ZORDERS").obj_type == "table"
