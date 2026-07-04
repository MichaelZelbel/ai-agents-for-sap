"""The enriched landscape model, offline: JSON round-trips, clean core classifies,
and the fit-to-standard scorecard ranks honestly."""

import pytest

from discovery.cleancore import classify, level_counts, level_d_exposure
from discovery.models import (
    CustomObject,
    InterfaceInfo,
    ObjectRegister,
    ProcessInfo,
    RegisterFormatError,
)
from discovery.register import build_register
from discovery.scorecard import (
    BUSY_THRESHOLD,
    decommission_candidates,
    fit_to_standard_scorecard,
    retention_candidates,
)
from discovery.sources import JsonRepositorySource, MockRepositorySource


def _mock():
    return build_register(MockRepositorySource())


# --- JSON persistence ---------------------------------------------------------

def test_json_round_trip_preserves_the_whole_landscape():
    reg = _mock()
    reg2 = ObjectRegister.from_json(reg.to_json())
    assert reg2.system == reg.system
    assert [o.to_dict() for o in reg2.objects] == [o.to_dict() for o in reg.objects]
    assert [p.to_dict() for p in reg2.processes] == [p.to_dict() for p in reg.processes]
    assert [i.to_dict() for i in reg2.interfaces] == [i.to_dict() for i in reg.interfaces]
    assert reg2.profile.to_dict() == reg.profile.to_dict()


def test_json_round_trip_keeps_none_usage_and_empty_tuples():
    reg = ObjectRegister(
        system="t",
        objects=(CustomObject("ZX", "class", "ZP", "d", monthly_uses=None, depends_on=()),),
    )
    reg2 = ObjectRegister.from_json(reg.to_json())
    o = reg2.objects[0]
    assert o.monthly_uses is None
    assert o.depends_on == ()


def test_json_source_loads_a_saved_register(tmp_path):
    path = tmp_path / "register.json"
    path.write_text(_mock().to_json(), encoding="utf-8")
    reg = build_register(JsonRepositorySource(path))
    assert reg.by_name("ZTHREEWAY_TOL") is not None
    assert len(reg.processes) == 3
    assert reg.profile.modules_in_use  # profile survived the round trip through the source


def test_malformed_json_fails_loudly():
    with pytest.raises(RegisterFormatError):
        ObjectRegister.from_json("{ not json")
    with pytest.raises(RegisterFormatError):
        ObjectRegister.from_json('{"system": "t"}')  # no objects
    with pytest.raises(RegisterFormatError):
        ObjectRegister.from_dict({"system": "t", "objects": [{"package": "z"}]})  # object has no name


# --- clean core ---------------------------------------------------------------

def test_clean_core_derives_the_level_from_the_mechanism():
    a = CustomObject("ZA", "cds_view", "ZP", "d", extension_mechanism="released_api")
    b = CustomObject("ZB", "class", "ZP", "d", extension_mechanism="badi")
    d = CustomObject("ZD", "enhancement", "ZP", "d", extension_mechanism="implicit_enhancement")
    assert classify(a).level == "A" and classify(a).upgrade_safe
    assert classify(b).level == "B" and classify(b).upgrade_safe
    assert classify(d).level == "D" and not classify(d).upgrade_safe


def test_clean_core_flags_c_when_it_reaches_into_internal_objects():
    c = CustomObject(
        "ZC", "program", "ZP", "d",
        extension_mechanism="classic_api",
        non_released_touched=("some SAP-internal include",),
    )
    assert classify(c).level == "C"


def test_clean_core_respects_an_explicit_level():
    o = CustomObject("ZE", "class", "ZP", "d", clean_core_level="A", extension_mechanism="modification")
    assert classify(o).level == "A"  # authored level wins over the derived one


def test_clean_core_rollup_and_level_d_exposure():
    reg = _mock()
    counts = level_counts(reg)
    assert counts.get("D", 0) == 1
    assert counts.get("A", 0) >= 1
    exposure = {o.name for o, _ in level_d_exposure(reg)}
    assert exposure == {"ZEI_INVOICE_POST"}


# --- fit-to-standard scorecard ------------------------------------------------

def test_scorecard_ranks_retire_first_and_keep_last():
    scores = fit_to_standard_scorecard(_mock())
    assert scores[0].obj.name == "ZCL_DISPUTE_ROUTER"
    assert scores[0].move == "retire" and scores[0].tier == "easy"
    assert scores[-1].move == "keep"
    moves = [s.move for s in scores]
    assert moves.index("retire") < moves.index("replace") < moves.index("re_platform")


def test_scorecard_reasons_carry_the_real_numbers():
    by_name = {s.obj.name: s for s in fit_to_standard_scorecard(_mock())}
    disputes = by_name["ZCL_DISPUTE_ROUTER"]
    assert any("3/mo" in r for r in disputes.reasons)  # the actual usage figure
    assert any("nothing else depends" in r for r in disputes.reasons)
    # the Level-D object must move onto a released API, and says why
    repl = by_name["ZEI_INVOICE_POST"]
    assert repl.move == "re_platform"
    assert any("Level D" in r for r in repl.reasons)


def test_high_remediation_effort_keeps_a_move_out_of_easy():
    by_name = {s.obj.name: s for s in fit_to_standard_scorecard(_mock())}
    # Z_TAX_DETERMINE_NW is modest usage / one dependent, but high effort is recorded
    assert by_name["Z_TAX_DETERMINE_NW"].tier != "easy"


def test_decommission_and_retention_pick_the_right_objects():
    reg = _mock()
    assert {o.name for o in decommission_candidates(reg)} == {"ZCL_DISPUTE_ROUTER"}
    retained = {o.name for o in retention_candidates(reg)}
    assert "Z_I_OPEN_AP_ITEMS" in retained  # Level A, heavily used, no standard equivalent
    assert "ZCL_DISPUTE_ROUTER" not in retained  # dead wood is not a keeper
