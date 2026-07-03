"""The self-learning loop for Pattern 3, at the flow and matcher level.

A human hold is remembered per vendor and folded into the next invoice from that
vendor, and every decision is counted for the override rate. There is no
deterministic learned field here: a line mapping is judgment, not an exact default,
so the loop reaches the model through worked examples in the prompt.
"""

from decimal import Decimal

from learning import CorrectionMemory
from threeway import (
    DEFAULT_VENDOR,
    HumanDecision,
    Line,
    LlmLineMatcher,
    build_prompt,
    run_threeway,
)

PO = [
    Line("Ergonomic office chair", Decimal("10"), Decimal("120.00")),
    Line("Standing desk", Decimal("4"), Decimal("350.00")),
]
INVOICE = [
    Line("Office chairs, ergonomic", Decimal("10"), Decimal("120.00")),
    Line("Desk, sit-stand", Decimal("4"), Decimal("350.00")),
]
RECEIVED = [Decimal("10"), Decimal("4")]


def _matcher(store=None):
    # A deterministic stand-in for the model: identity mapping, returned as JSON.
    return LlmLineMatcher(
        complete=lambda prompt: '{"mapping": [0, 1]}',
        store=store,
        vendor=DEFAULT_VENDOR,
    )


def test_a_hold_is_recorded_and_counts_toward_the_override_rate():
    store = CorrectionMemory()
    # The guard passes on the clean case, so the human is asked; here they hold it.
    run_threeway(
        _matcher(store), INVOICE, PO, RECEIVED,
        approve=lambda *a: HumanDecision(False, rationale="desk model is wrong"),
        case_id="MATCH-CLEAN", store=store,
    )
    # A second, released decision, to show the rate counts only the override.
    run_threeway(
        _matcher(store), INVOICE, PO, RECEIVED,
        approve=lambda *a: HumanDecision(True),
        case_id="MATCH-CLEAN-2", store=store,
    )
    overrides, total, rate = store.override_rate()
    assert (overrides, total) == (1, 2)
    assert rate == 0.5


def test_examples_for_returns_the_past_override():
    store = CorrectionMemory()
    run_threeway(
        _matcher(store), INVOICE, PO, RECEIVED,
        approve=lambda *a: HumanDecision(False, rationale="desk model is wrong"),
        case_id="MATCH-CLEAN", store=store,
    )
    examples = store.examples_for(DEFAULT_VENDOR, invoice_total := INVOICE[0].quantity)
    assert len(examples) == 1
    assert examples[0].decision == "rejected"
    assert examples[0].reason == "desk model is wrong"
    assert examples[0].proposed  # the mapping summary was captured


def test_the_matcher_prompt_includes_a_past_example():
    store = CorrectionMemory()
    # Seed one hold for this vendor.
    run_threeway(
        _matcher(store), INVOICE, PO, RECEIVED,
        approve=lambda *a: HumanDecision(False, rationale="desk model is wrong"),
        case_id="MATCH-CLEAN", store=store,
    )
    # Capture the prompt the matcher builds on the next run via the injected path.
    seen = {}

    def capture(prompt: str) -> str:
        seen["prompt"] = prompt
        return '{"mapping": [0, 1]}'

    matcher = LlmLineMatcher(complete=capture, store=store, vendor=DEFAULT_VENDOR)
    matcher.match(INVOICE, PO, vendor=DEFAULT_VENDOR)
    assert "Past human corrections and rejections for this vendor" in seen["prompt"]
    assert "desk model is wrong" in seen["prompt"]


def test_build_prompt_folds_examples_when_given():
    # The prompt builder is where the loop reaches the model; assert directly.
    store = CorrectionMemory()
    run_threeway(
        _matcher(store), INVOICE, PO, RECEIVED,
        approve=lambda *a: HumanDecision(False, rationale="held for review"),
        case_id="MATCH-CLEAN", store=store,
    )
    examples = store.examples_for(DEFAULT_VENDOR)
    plain = build_prompt(INVOICE, PO)
    learned = build_prompt(INVOICE, PO, examples=examples)
    assert "Past human corrections" not in plain
    assert "Past human corrections" in learned
    assert "held for review" in learned
