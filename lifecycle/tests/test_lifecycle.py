"""The gate is deterministic: the same evidence always gives the same verdict."""

import pytest

from lifecycle.examples import FLEET
from lifecycle.gate import Thresholds, evaluate
from lifecycle.models import LADDER, AgentManifest, AgentMetrics, next_level


def _manifest(level="suggest_only", **kw):
    base = dict(name="a", purpose="p", autonomy=level, prompt_version="v1", model="m")
    base.update(kw)
    return AgentManifest(**base)


def _metrics(**kw):
    base = dict(weeks_at_level=8, override_rate=0.02, audit_clean=True, exceptions_per_week=2, monthly_uses=1000)
    base.update(kw)
    return AgentMetrics(**base)


def test_ladder_is_ordered_and_climbs_one_rung():
    assert LADDER[0] == "shadow"
    assert next_level("suggest_only") == "draft_first"
    assert next_level("bounded_auto") is None


def test_unknown_autonomy_is_rejected():
    with pytest.raises(ValueError):
        _manifest(level="fully_autonomous")


def test_earned_autonomy_is_promoted():
    d = evaluate(_manifest("suggest_only"), _metrics(weeks_at_level=6, override_rate=0.03))
    assert d.verdict == "promote"
    assert d.to_level == "draft_first"


def test_too_little_runtime_holds():
    d = evaluate(_manifest("draft_first"), _metrics(weeks_at_level=2))
    assert d.verdict == "hold"


def test_high_override_is_a_review_not_a_promotion():
    d = evaluate(_manifest("suggest_only"), _metrics(override_rate=0.30))
    assert d.verdict == "review"


def test_a_broken_control_forces_a_review():
    d = evaluate(_manifest("draft_first"), _metrics(audit_clean=False))
    assert d.verdict == "review"


def test_dead_wood_is_retired():
    d = evaluate(_manifest("bounded_auto"), _metrics(weeks_at_level=30, monthly_uses=5))
    assert d.verdict == "retire"


def test_a_young_low_use_agent_is_not_retired_prematurely():
    # low usage but only 3 weeks old: hold and see, do not retire yet
    d = evaluate(_manifest("suggest_only"), _metrics(weeks_at_level=3, monthly_uses=5, override_rate=0.10))
    assert d.verdict != "retire"


def test_standard_now_covers_it_means_retire():
    d = evaluate(_manifest("draft_first", standard_now_covers=True), _metrics())
    assert d.verdict == "retire"


def test_the_top_rung_asks_for_more_evidence():
    # promoting TO bounded_auto needs 8 weeks and <=2% override; 5 weeks is not enough
    d = evaluate(_manifest("draft_first"), _metrics(weeks_at_level=5, override_rate=0.02))
    assert d.verdict == "hold"


def test_the_example_fleet_covers_every_verdict():
    verdicts = {evaluate(m, x).verdict for (m, x) in FLEET}
    assert verdicts == {"promote", "hold", "review", "retire"}
