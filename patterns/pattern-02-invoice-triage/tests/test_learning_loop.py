"""The self-learning loop for triage, at the flow level.

A human rejection (or a named correction) of a routing is remembered per vendor,
counts toward the override rate, and is folded into the next document's prompt so
the classifier learns from what the reviewer changed. No real model call: we inject
`complete`, and the offline path passes the prompt through so we can inspect it.
"""

from decimal import Decimal

from sap_client import Document, MockSapClient

from learning import CorrectionMemory
from triage import HumanDecision, LlmTriager, run_triage


def _triager(store, category="direct_expense", capture=None):
    """A classifier whose model reply is fixed. When `capture` is a list, the prompt
    it was handed is appended, so a test can assert what the classifier saw."""

    def complete(prompt):
        if capture is not None:
            capture.append(prompt)
        return category

    return LlmTriager(complete=complete, store=store)


def test_a_rejection_is_recorded_and_counts_toward_the_override_rate():
    mock = MockSapClient()
    doc = mock.read_document("INV-1001")
    store = CorrectionMemory()

    r = run_triage(
        _triager(store),
        doc,
        confirm=lambda *a: HumanDecision(False, rationale="this is a credit note"),
        store=store,
    )
    assert r.outcome == "rejected_by_human"

    # The rejection is on the record, keyed by the vendor, with the reason kept.
    assert len(store) == 1
    overrides, total, rate = store.override_rate()
    assert (overrides, total) == (1, 1)
    assert rate == 1.0

    # A confirmation counts too, but not as an override.
    run_triage(_triager(store), doc, confirm=lambda *a: HumanDecision(True), store=store)
    overrides, total, _ = store.override_rate()
    assert (overrides, total) == (1, 2)


def test_examples_for_returns_a_past_override():
    store = CorrectionMemory()
    doc = MockSapClient().read_document("INV-1001")  # vendor: Office Supplies Co
    run_triage(
        _triager(store),
        doc,
        confirm=lambda *a: HumanDecision(False, rationale="not a PO invoice"),
        store=store,
    )
    examples = store.examples_for("Office Supplies Co")
    assert len(examples) == 1
    assert examples[0].decision == "rejected"
    assert examples[0].reason == "not a PO invoice"


def test_the_prompt_includes_a_past_example_when_the_store_has_one():
    store = CorrectionMemory()
    # A second document from the same vendor as INV-1001 (Office Supplies Co).
    doc2 = Document(
        "INV-1010", "Office Supplies Co", "EUR",
        Decimal("500.00"), Decimal("95.00"), Decimal("595.00"), "2026-06-30",
    )
    doc1 = MockSapClient().read_document("INV-1001")

    # 1) A human rejects the first document's routing with a reason.
    run_triage(
        _triager(store),
        doc1,
        confirm=lambda *a: HumanDecision(False, rationale="always a direct expense"),
        store=store,
    )

    # 2) The next document from that vendor is classified with the past rejection
    #    folded into the prompt. We capture the prompt the classifier was handed.
    seen: list[str] = []
    run_triage(
        _triager(store, capture=seen),
        doc2,
        confirm=lambda *a: HumanDecision(True),
        store=store,
    )
    prompt = seen[0]
    assert "Past human corrections and rejections for this vendor" in prompt
    assert "always a direct expense" in prompt


def test_a_named_correction_is_remembered_as_such():
    store = CorrectionMemory()
    doc = MockSapClient().read_document("INV-1001")
    r = run_triage(
        _triager(store, category="po_invoice"),
        doc,
        confirm=lambda *a: HumanDecision(
            False, rationale="no PO here", corrected_category="direct_expense"
        ),
        store=store,
    )
    assert r.outcome == "corrected"
    assert r.category == "direct_expense"
    assert r.next_step == "post directly"
    examples = store.examples_for("Office Supplies Co")
    assert examples[0].decision == "corrected"
    assert "po_invoice -> direct_expense" in examples[0].correction
