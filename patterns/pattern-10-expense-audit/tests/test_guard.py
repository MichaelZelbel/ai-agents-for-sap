"""Tests for the deterministic guard and the routing.

No AI, no key, no network. These prove the guard owns the real decision and
that lines route to the right place against the current policy.
"""

from decimal import Decimal

from expense import (
    ExpenseLine,
    ExpenseReport,
    RuleBasedDrafter,
    audit_report,
    default_policy,
    guard_line,
    route_line,
)
from expense.auditor import approver_for, sample_reports


def _line(**kw) -> ExpenseLine:
    base = dict(
        line_id="L1",
        category="meals",
        claimed_amount=Decimal("42.00"),
        receipt_total=Decimal("42.00"),
        date="2026-06-12",
    )
    base.update(kw)
    return ExpenseLine(**base)


def test_compliant_line_passes_the_guard():
    ok, failed = guard_line(_line(), policy=default_policy())
    assert ok is True
    assert failed == ()


def test_receipt_must_equal_claim():
    ok, failed = guard_line(
        _line(receipt_total=Decimal("40.00")), policy=default_policy()
    )
    assert ok is False
    assert any("does not equal" in f for f in failed)


def test_over_per_diem_is_a_violation():
    ok, failed = guard_line(
        _line(category="lodging", claimed_amount=Decimal("240.00"),
              receipt_total=Decimal("240.00")),
        policy=default_policy(),
    )
    assert ok is False
    assert any("exceeds the" in f for f in failed)


def test_missing_receipt_above_threshold_is_a_violation():
    ok, failed = guard_line(
        _line(claimed_amount=Decimal("90.00"), receipt_total=Decimal("0.00")),
        policy=default_policy(),
    )
    assert ok is False
    assert any("receipt required" in f for f in failed)


def test_disallowed_category_is_a_violation():
    ok, failed = guard_line(
        _line(category="entertainment", claimed_amount=Decimal("10.00"),
              receipt_total=Decimal("10.00")),
        policy=default_policy(),
    )
    assert ok is False
    assert any("not allowed" in f for f in failed)


def test_date_outside_period_is_a_violation():
    ok, failed = guard_line(_line(date="2026-07-05"), policy=default_policy())
    assert ok is False
    assert any("outside the period" in f for f in failed)


def test_approver_tier_scales_with_amount():
    policy = default_policy()
    assert approver_for(Decimal("50.00"), policy) == "team_lead"
    assert approver_for(Decimal("300.00"), policy) == "manager"
    assert approver_for(Decimal("900.00"), policy) == "director"
    assert approver_for(Decimal("5000.00"), policy) == "compliance"


def test_compliant_line_routes_to_fast_approval():
    d = route_line(_line(), policy=default_policy())
    assert d.route == "fast_approval"
    assert d.compliant is True


def test_first_violation_routes_to_manager():
    d = route_line(
        _line(category="lodging", claimed_amount=Decimal("240.00"),
              receipt_total=Decimal("240.00")),
        policy=default_policy(),
        prior_failures=0,
    )
    assert d.route == "manager"


def test_repeat_violation_escalates_to_compliance():
    d = route_line(
        _line(category="lodging", claimed_amount=Decimal("240.00"),
              receipt_total=Decimal("240.00")),
        policy=default_policy(),
        prior_failures=1,
    )
    assert d.route == "compliance"


def test_high_value_violation_escalates_to_compliance():
    d = route_line(
        _line(category="transport", claimed_amount=Decimal("1500.00"),
              receipt_total=Decimal("1500.00")),
        policy=default_policy(),
        prior_failures=0,
    )
    # Over the per diem cap and over the high value threshold: straight to compliance.
    assert d.route == "compliance"


def test_policy_version_is_recorded_on_every_decision():
    result = audit_report(
        sample_reports()["EXP-2001"],
        policy=default_policy(),
        drafter=RuleBasedDrafter(),
    )
    assert result.policy_version == "2026.06"
    for decision in result.decisions:
        assert decision.policy_version == "2026.06"
    assert all("policy 2026.06" in entry for entry in result.log)


def test_sample_report_hits_all_three_routes():
    result = audit_report(
        sample_reports()["EXP-2001"],
        policy=default_policy(),
        drafter=RuleBasedDrafter(),
    )
    routes = [d.route for d in result.decisions]
    assert routes[0] == "fast_approval"  # compliant meal
    assert routes[1] == "manager"  # first violation: over per diem
    assert routes[2] == "compliance"  # second violation: repeat offender


def test_a_newer_policy_can_change_the_route():
    # Raise the lodging cap in a new policy version. The same over per diem line
    # now passes. The guard reads the current policy, so the route flips.
    from dataclasses import replace

    base = default_policy()
    relaxed = replace(
        base,
        version="2026.07",
        per_diem_caps={**base.per_diem_caps, "lodging": Decimal("300.00")},
    )
    line = ExpenseLine(
        line_id="L2",
        category="lodging",
        claimed_amount=Decimal("240.00"),
        receipt_total=Decimal("240.00"),
        date="2026-06-13",
    )
    old = route_line(line, policy=base)
    new = route_line(line, policy=relaxed)
    assert old.route == "manager"
    assert new.route == "fast_approval"
    assert new.policy_version == "2026.07"
