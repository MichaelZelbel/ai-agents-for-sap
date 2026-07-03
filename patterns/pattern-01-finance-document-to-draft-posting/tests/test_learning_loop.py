"""The self-correcting loop, at the flow level.

A human correction is remembered per vendor and folded into the next invoice from
that vendor, and a human's edit still has to pass the deterministic guard.
"""

from dataclasses import replace
from decimal import Decimal

from sap_client import Document, GovernedSapClient, MockSapClient

from learning import CorrectionMemory
from pattern1.flow import HumanDecision, run_pattern1
from pattern1.proposer import RuleBasedProposer

FULL_ACCESS = {"read", "stage", "confirm"}


def _config(mock):
    from pattern1.validator import default_config
    return replace(
        default_config(),
        known_vendors=mock.known_vendors(),
        known_tax_codes=mock.known_tax_codes(),
        active_cost_centers=mock.active_cost_centers(),
    )


def _run(client, mock, doc_id, store, approve):
    return run_pattern1(
        client, RuleBasedProposer(), doc_id,
        posting_date="2026-06-27", config=_config(mock),
        approve=approve, store=store,
    )


def test_a_correction_is_remembered_and_applied_to_the_next_invoice():
    mock = MockSapClient()
    # A second invoice from the same vendor as INV-1001 (Office Supplies Co).
    mock.register_document(Document("INV-1009", "Office Supplies Co", "EUR",
                                    Decimal("2000.00"), Decimal("380.00"),
                                    Decimal("2380.00"), "2026-06-28"))
    client = GovernedSapClient(mock, entitlements=FULL_ACCESS)
    store = CorrectionMemory()

    # 1) A human approves INV-1001 but moves it to CC-2000 (marketing).
    r1 = _run(client, mock, "INV-1001", store,
              lambda *a: HumanDecision(True, rationale="marketing campaign, not ops",
                                       corrected_cost_center="CC-2000"))
    assert r1.outcome == "posted"
    assert store.learned_field("Office Supplies Co", "cost_center") == "CC-2000"

    # 2) The next invoice from that vendor is proposed with CC-2000 already applied,
    #    with no human correction this time. The human just sees the right draft.
    seen = {}

    def watch_and_approve(document, posting, validation):
        seen["cost_center"] = posting.cost_center
        return HumanDecision(True)

    r2 = _run(client, mock, "INV-1009", store, watch_and_approve)
    assert r2.outcome == "posted"
    assert seen["cost_center"] == "CC-2000"  # learned, not the CC-1000 default


def test_a_human_edit_still_has_to_pass_the_guard():
    mock = MockSapClient()
    client = GovernedSapClient(mock, entitlements=FULL_ACCESS)
    store = CorrectionMemory()
    # The human "corrects" INV-1001 to a cost center that does not exist.
    r = _run(client, mock, "INV-1001", store,
             lambda *a: HumanDecision(True, corrected_cost_center="CC-9999"))
    assert r.outcome == "rejected_by_validator"
    assert any("Cost center CC-9999" in reason for reason in r.validation.reasons)
    # The bad edit was not learned as a preference.
    assert store.learned_field("Office Supplies Co", "cost_center") is None


def test_every_decision_is_counted_for_the_override_rate():
    mock = MockSapClient()
    client = GovernedSapClient(mock, entitlements=FULL_ACCESS)
    store = CorrectionMemory()
    _run(client, mock, "INV-1001", store, lambda *a: HumanDecision(True))            # approved
    _run(client, mock, "INV-1002", store, lambda *a: HumanDecision(False, rationale="hold"))  # rejected
    overrides, total, rate = store.override_rate()
    assert (overrides, total) == (1, 2)
    assert rate == 0.5
