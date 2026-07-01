"""Tests for the deterministic entitlement guard.

The guard is the leash. These tests pin its verdicts so a change to the rules is
visible. The AI is never involved here.
"""

from decimal import Decimal

from service import MockServiceSource, default_config
from service.guard import evaluate
from service.models import ProposedStep


def _step(case_id, kind, cost, part_id=None):
    return ProposedStep(
        case_id=case_id,
        kind=kind,
        part_id=part_id,
        estimated_cost=Decimal(cost),
        rationale="test",
    )


def test_in_warranty_covered_site_under_limit_is_allowed():
    context = MockServiceSource().gather_context("CASE-501")
    step = _step("CASE-501", "replace_under_warranty", "420.00", "PRT-STATOR")
    decision = evaluate(context, step, config=default_config())
    assert decision.verdict == "allow"
    assert decision.reason


def test_uncovered_site_needs_approval():
    context = MockServiceSource().gather_context("CASE-502")
    step = _step("CASE-502", "replace_under_warranty", "260.00", "PRT-GEARSEAL")
    decision = evaluate(context, step, config=default_config())
    assert decision.verdict == "needs-approval"
    assert "not on the covered list" in decision.reason.lower()


def test_out_of_warranty_replacement_is_denied():
    context = MockServiceSource().gather_context("CASE-503")
    step = _step("CASE-503", "replace_under_warranty", "510.00", "PRT-WINDING")
    decision = evaluate(context, step, config=default_config())
    assert decision.verdict == "deny"
    assert "out of warranty" in decision.reason.lower()


def test_cost_over_limit_needs_approval():
    # In warranty and a covered site, but the estimate crosses the approval limit.
    context = MockServiceSource().gather_context("CASE-501")
    step = _step("CASE-501", "replace_under_warranty", "5000.00", "PRT-STATOR")
    decision = evaluate(context, step, config=default_config())
    assert decision.verdict == "needs-approval"
    assert "limit" in decision.reason.lower()


def test_cost_check_uses_decimal_not_float():
    # 800.00 is exactly the limit and must be allowed. 800.01 must not. A float
    # comparison here is where a cent slips through.
    context = MockServiceSource().gather_context("CASE-501")
    at_limit = _step("CASE-501", "replace_under_warranty", "800.00", "PRT-STATOR")
    over_limit = _step("CASE-501", "replace_under_warranty", "800.01", "PRT-STATOR")
    assert evaluate(context, at_limit, config=default_config()).verdict == "allow"
    assert (
        evaluate(context, over_limit, config=default_config()).verdict
        == "needs-approval"
    )


def test_escalate_always_needs_approval():
    context = MockServiceSource().gather_context("CASE-501")
    step = _step("CASE-501", "escalate", "0.00")
    decision = evaluate(context, step, config=default_config())
    assert decision.verdict == "needs-approval"


def test_reject_claim_is_allowed_as_reversible():
    context = MockServiceSource().gather_context("CASE-503")
    step = _step("CASE-503", "reject_claim", "0.00")
    decision = evaluate(context, step, config=default_config())
    assert decision.verdict == "allow"
