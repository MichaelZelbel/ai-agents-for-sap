"""Tests for the shared self-learning loop wired into Pattern 7.

The loop keeps every human decision (confirm or decline) as a worked example,
keyed by the recurring entity this pattern turns on: the asset model. A decline is
counted toward the override rate and folded into the next proposal's prompt so the
model learns from it. The deterministic guard still decides, so a learned example
can only make a proposal better, never bypass a rule.

These run offline: the rule-based proposer and an injected `complete` keep them
key-free and deterministic.
"""

from decimal import Decimal

from learning import Correction, CorrectionMemory

from service import (
    GovernedServiceSource,
    MockServiceSource,
    RuleBasedProposer,
    default_config,
    run_pattern7,
)
from service.proposer import LlmBackedProposer, build_prompt

# CASE-501 is the allow case: in warranty, covered site, part in stock.
CASE_501_MODEL = "NordDrive 3kW"


def _governed():
    return GovernedServiceSource(
        MockServiceSource(), entitlements={"read", "stage", "execute"}
    )


def _always(value):
    return lambda context, step, decision: value


def test_a_decline_is_recorded_and_counts_toward_the_override_rate():
    store = CorrectionMemory()
    result = run_pattern7(
        _governed(),
        RuleBasedProposer(),
        "CASE-501",
        config=default_config(),
        confirm=_always(False),  # the human declines the staged step
        store=store,
    )
    assert result.outcome == "declined_by_human"

    # One decision recorded, and it is an override (a decline).
    assert len(store) == 1
    overrides, total, rate = store.override_rate()
    assert (overrides, total) == (1, 1)
    assert rate == 1.0

    # It was filed under the asset model, with the step's cost as the amount.
    recorded = store.examples_for(CASE_501_MODEL)[0]
    assert recorded.entity == CASE_501_MODEL
    assert recorded.item_id == "CASE-501"
    assert recorded.decision == "rejected"
    assert recorded.amount == "420.00"


def test_a_confirm_is_recorded_but_does_not_count_as_an_override():
    store = CorrectionMemory()
    result = run_pattern7(
        _governed(),
        RuleBasedProposer(),
        "CASE-501",
        config=default_config(),
        confirm=_always(True),  # the human confirms
        store=store,
    )
    assert result.outcome == "done"
    overrides, total, _rate = store.override_rate()
    assert (overrides, total) == (0, 1)  # recorded, but not an override


def test_examples_for_returns_a_past_override():
    store = CorrectionMemory()
    store.record(
        Correction(
            entity=CASE_501_MODEL,
            item_id="CASE-401",
            decision="rejected",
            reason="Stator was replaced last month; check wiring, not the stator.",
            context="Motor overheats, asset NordDrive 3kW",
            proposed="replace_under_warranty part PRT-STATOR, est. cost 420.00",
            amount="420.00",
        )
    )
    examples = store.examples_for(CASE_501_MODEL, Decimal("420.00"))
    assert len(examples) == 1
    assert examples[0].item_id == "CASE-401"
    assert examples[0].decision == "rejected"


def test_llm_prompt_includes_a_past_example_when_the_store_has_one():
    store = CorrectionMemory()
    store.record(
        Correction(
            entity=CASE_501_MODEL,
            item_id="CASE-401",
            decision="rejected",
            reason="Stator was replaced last month; check wiring, not the stator.",
            context="Motor overheats, asset NordDrive 3kW",
            proposed="replace_under_warranty part PRT-STATOR, est. cost 420.00",
            amount="420.00",
        )
    )
    context = MockServiceSource().gather_context("CASE-501")

    captured = {}

    def complete(prompt: str) -> str:
        captured["prompt"] = prompt
        return (
            '{"kind": "dispatch_technician", "part_id": null, '
            '"estimated_cost": "0.00", "rationale": "Inspect wiring first."}'
        )

    proposer = LlmBackedProposer(complete=complete, store=store)
    proposer.propose(context)

    prompt = captured["prompt"]
    assert "Past human corrections and declines for this asset model" in prompt
    assert "Stator was replaced last month" in prompt
    assert "A human declined it" in prompt


def test_prompt_without_examples_has_no_learning_block():
    # No store, no examples: the prompt must be exactly the base instruction, so the
    # offline injected path is unchanged when nothing has been learned yet.
    context = MockServiceSource().gather_context("CASE-501")
    assert "Past human corrections and declines" not in build_prompt(context)
