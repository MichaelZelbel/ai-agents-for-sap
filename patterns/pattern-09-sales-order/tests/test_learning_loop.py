"""The self-learning loop, at the flow level.

Every human decision on a staged order is remembered per customer. A rejection's
reason is folded into the model's prompt for the next request from that customer,
and every decision feeds the override rate that raises a review when it climbs.
"""

from salesorder import (
    GovernedSalesClient,
    HumanDecision,
    LlmBackedProposer,
    MockSalesClient,
    RuleBasedProposer,
    build_prompt,
    default_config,
    load_products,
    load_requests,
    run_pattern9,
)

from learning import Correction, CorrectionMemory


def _client():
    return GovernedSalesClient(MockSalesClient(), entitlements={"stage", "release"})


def _run(request_id, store, approve):
    return run_pattern9(
        _client(),
        RuleBasedProposer(),
        load_requests()[request_id],
        config=default_config(),
        approve=approve,
        store=store,
    )


def test_a_rejection_is_recorded_and_counted_in_the_override_rate():
    store = CorrectionMemory()
    # REQ-1 is a clean order the guard passes, so the human is reached.
    result = _run(
        "REQ-1",
        store,
        lambda *a: HumanDecision(approved=False, rationale="wrong SKU, not the usual"),
    )
    assert result.outcome == "rejected_by_human"
    assert len(store) == 1

    overrides, total, rate = store.override_rate()
    assert (overrides, total) == (1, 1)
    assert rate == 1.0

    # The rejection was recorded against the customer, with the reason kept.
    recorded = store.examples_for("ACME")
    assert len(recorded) == 1
    assert recorded[0].decision == "rejected"
    assert recorded[0].reason == "wrong SKU, not the usual"
    assert recorded[0].item_id == "REQ-1"


def test_examples_for_returns_a_past_override_for_the_customer():
    store = CorrectionMemory()
    _run("REQ-1", store, lambda *a: HumanDecision(approved=True))  # approved, not an override
    _run(
        "REQ-1",
        store,
        lambda *a: HumanDecision(approved=False, rationale="hold, credit review"),
    )
    examples = store.examples_for("ACME")
    # Only the rejection is a learnable override; the approval is not.
    assert len(examples) == 1
    assert examples[0].decision == "rejected"
    assert examples[0].entity == "ACME"
    assert examples[0].reason == "hold, credit review"


def test_the_llm_prompt_includes_a_past_example_when_the_store_has_one():
    store = CorrectionMemory()
    store.record(
        Correction(
            entity="ACME",
            item_id="REQ-0",
            decision="rejected",
            reason="the 'usual' is BRK-100, not VALVE-9",
            context="Send me 100 of the usual by month end.",
            proposed="100 x VALVE-9; total 14000.00 EUR",
            amount="14000.00",
        )
    )

    captured = {}

    def complete(prompt: str) -> str:
        captured["prompt"] = prompt
        return (
            '{"items": [{"sku": "BRK-100", "quantity": 100}], '
            '"requested_delivery": "2026-06-30", "discount_pct": "0", '
            '"ship_to_country": "DE"}'
        )

    proposer = LlmBackedProposer(complete=complete, store=store)
    proposer.extract(load_requests()["REQ-1"], catalog=load_products())

    prompt = captured["prompt"]
    assert "Past human corrections and rejections for this customer" in prompt
    assert "the 'usual' is BRK-100, not VALVE-9" in prompt
    assert "100 x VALVE-9" in prompt


def test_build_prompt_without_examples_is_unchanged():
    # With no store, the offline path folds in nothing.
    prompt = build_prompt(load_requests()["REQ-1"], load_products())
    assert "Past human corrections and rejections" not in prompt
