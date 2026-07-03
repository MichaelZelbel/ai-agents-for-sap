from pattern1.feedback import Decision, FeedbackStore


def approvals(store, vendor, n):
    for i in range(n):
        store.record(Decision(f"D-{i}", vendor, "approved"))


def test_learns_the_cost_center_a_human_moved_an_invoice_to():
    store = FeedbackStore()
    assert store.cost_center_for("Marketing Vendor") is None
    store.record(Decision("INV-1", "Marketing Vendor", "corrected",
                          reason="marketing campaign, not operations",
                          corrected_cost_center="CC-2000"))
    assert store.cost_center_for("Marketing Vendor") == "CC-2000"
    # The most recent correction wins.
    store.record(Decision("INV-2", "Marketing Vendor", "corrected", corrected_cost_center="CC-1000"))
    assert store.cost_center_for("Marketing Vendor") == "CC-1000"
    # Another vendor is unaffected.
    assert store.cost_center_for("Some Other Vendor") is None


def test_notes_are_per_vendor_newest_first_and_capped():
    store = FeedbackStore()
    for i in range(5):
        store.record(Decision(f"INV-{i}", "Vendor X", "rejected", reason=f"reason {i}"))
    store.record(Decision("INV-Y", "Vendor Y", "rejected", reason="unrelated"))
    notes = store.notes_for("Vendor X", limit=3)
    assert notes == ["reason 4", "reason 3", "reason 2"]
    assert "unrelated" not in notes


def test_override_rate_counts_corrected_and_rejected():
    store = FeedbackStore()
    approvals(store, "V", 8)
    store.record(Decision("R", "V", "rejected", reason="wrong"))
    store.record(Decision("C", "V", "corrected", corrected_cost_center="CC-2000"))
    overrides, total, rate = store.override_rate(window=50)
    assert (overrides, total) == (2, 10)
    assert rate == 0.2


def test_review_fires_only_when_the_rate_crosses_the_threshold():
    store = FeedbackStore()
    # 9 clean, 1 override: 10% over 10 decisions.
    approvals(store, "V", 9)
    store.record(Decision("R", "V", "rejected", reason="check the PO"))
    assert store.review_needed(threshold=0.20) is None  # 10% is under 20%
    # Push it over: three more overrides -> 4 / 13 ~ 31%.
    for i in range(3):
        store.record(Decision(f"R{i}", "V", "rejected", reason=f"issue {i}"))
    digest = store.review_needed(threshold=0.20)
    assert digest is not None
    assert digest.rate > 0.20
    assert digest.overrides == 4
    # The digest carries the overrides and their reasons for the reviewer.
    assert all(item["decision"] in ("corrected", "rejected") for item in digest.recent)
    assert any("check the PO" in item["reason"] for item in digest.recent)


def test_review_stays_quiet_on_a_tiny_sample():
    store = FeedbackStore()
    store.record(Decision("R", "V", "rejected", reason="one bad one"))
    # 100% override rate, but only one decision: not enough to raise a review.
    assert store.review_needed(threshold=0.20, min_total=10) is None


def test_persistence_round_trips(tmp_path):
    store = FeedbackStore()
    store.record(Decision("INV-1", "Vendor X", "corrected", reason="why", corrected_cost_center="CC-2000"))
    store.record(Decision("INV-2", "Vendor X", "approved"))
    path = tmp_path / "feedback.jsonl"
    store.save(path)
    reloaded = FeedbackStore.load(path)
    assert len(reloaded) == 2
    assert reloaded.cost_center_for("Vendor X") == "CC-2000"
    assert reloaded.notes_for("Vendor X") == ["why"]


def test_load_missing_file_is_empty():
    assert len(FeedbackStore.load("does-not-exist.jsonl")) == 0
