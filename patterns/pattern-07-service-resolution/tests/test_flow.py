"""Tests for the whole Pattern 7 flow.

They prove the rule of the pattern: the AI only proposes, the deterministic guard
decides, and nothing writes until a human confirms. The offline rule-based
proposer keeps these tests deterministic and key-free.
"""

import pytest

from service import (
    GovernedServiceSource,
    MockServiceSource,
    RuleBasedProposer,
    default_config,
    run_pattern7,
)
from service.errors import NotConfirmedError


def _governed():
    return GovernedServiceSource(
        MockServiceSource(), entitlements={"read", "stage", "execute"}
    )


def _always(decision_value):
    return lambda context, step, decision: decision_value


def test_allow_then_human_confirms_executes():
    source = _governed()
    result = run_pattern7(
        source,
        RuleBasedProposer(),
        "CASE-501",
        config=default_config(),
        confirm=_always(True),
    )
    assert result.outcome == "done"
    assert result.action_result is not None
    assert result.decision.verdict == "allow"


def test_allow_but_human_declines_writes_nothing():
    source = _governed()
    result = run_pattern7(
        source,
        RuleBasedProposer(),
        "CASE-501",
        config=default_config(),
        confirm=_always(False),
    )
    assert result.outcome == "declined_by_human"
    assert result.action_result is None
    # It was staged but never executed.
    assert result.staged_id is not None


def test_needs_approval_is_sent_to_supervisor_and_stages_nothing():
    source = _governed()
    confirmed = {"called": False}

    def confirm(context, step, decision):
        confirmed["called"] = True
        return True

    result = run_pattern7(
        source,
        RuleBasedProposer(),
        "CASE-502",
        config=default_config(),
        confirm=confirm,
    )
    assert result.outcome == "sent_to_supervisor"
    assert result.decision.verdict == "needs-approval"
    assert result.action_result is None
    # The human confirmer is never reached for a needs-approval verdict.
    assert confirmed["called"] is False
    # Nothing was staged, so the only audited operation is the read.
    assert [e.operation for e in source.audit_log] == ["read"]


def test_deny_never_asks_a_human():
    source = _governed()
    confirmed = {"called": False}

    def confirm(context, step, decision):
        confirmed["called"] = True
        return True

    # CASE-503 is out of warranty. The proposer still proposes a warranty
    # replacement (the customer's claim), and the guard denies it outright.
    result = run_pattern7(
        source,
        RuleBasedProposer(),
        "CASE-503",
        config=default_config(),
        confirm=confirm,
    )
    assert result.outcome == "denied_by_guard"
    assert result.decision.verdict == "deny"
    assert confirmed["called"] is False
    assert result.action_result is None


def test_confirm_hold_blocks_execution_without_a_recorded_confirmation():
    # Execute cannot run until a human confirmation is recorded, even if the guard
    # allowed the step. This is the governance leash, tested directly.
    source = _governed()
    context = source.gather_context("CASE-501")
    step = RuleBasedProposer().propose(context)
    staged = source.stage_action(step)
    with pytest.raises(NotConfirmedError):
        source.execute_action(staged.staged_id)


def test_audit_chain_verifies_and_records_the_entitlement_snapshot():
    source = _governed()
    run_pattern7(
        source,
        RuleBasedProposer(),
        "CASE-501",
        config=default_config(),
        confirm=_always(True),
    )
    assert source.verify_audit() is True
    read_entry = source.audit_log[0]
    assert read_entry.operation == "read"
    # The entitlement snapshot is logged with the read, so the audit shows what
    # the guard was evaluated against.
    assert "in_warranty:True" in read_entry.outcome
