from learning import Correction, CorrectionMemory


def approvals(mem, entity, n):
    for i in range(n):
        mem.record(Correction(entity, f"D-{i}", "approved"))


def test_learned_field_is_the_latest_structured_correction_for_an_entity():
    mem = CorrectionMemory()
    assert mem.learned_field("ACME", "cost_center") is None
    mem.record(Correction("ACME", "INV-1", "corrected", reason="marketing",
                          fields={"cost_center": "CC-2000"}))
    assert mem.learned_field("ACME", "cost_center") == "CC-2000"
    mem.record(Correction("ACME", "INV-2", "corrected", fields={"cost_center": "CC-1000"}))
    assert mem.learned_field("ACME", "cost_center") == "CC-1000"  # most recent wins
    assert mem.learned_field("NOVA", "cost_center") is None       # other entity
    assert mem.learned_field("ACME", "tax_code") is None          # other field


def test_examples_prefer_the_same_entity_and_are_overrides_only():
    mem = CorrectionMemory()
    mem.record(Correction("ACME", "A", "approved"))  # not an override
    for i in range(4):
        mem.record(Correction("ACME", f"R-{i}", "rejected", reason=f"r{i}"))
    mem.record(Correction("NOVA", "N", "rejected", reason="unrelated"))
    ex = mem.examples_for("ACME", limit=3)
    assert all(e.entity == "ACME" and e.decision in ("corrected", "rejected") for e in ex)
    assert "unrelated" not in [e.reason for e in ex]


def test_examples_rank_by_relevance_not_recency():
    mem = CorrectionMemory()
    mem.record(Correction("ACME", "OLD", "rejected", reason="close", amount="1000.00"))
    mem.record(Correction("ACME", "NEW", "rejected", reason="far", amount="9000.00"))
    ex = mem.examples_for("ACME", amount="1010.00", limit=2)
    assert ex[0].reason == "close"  # amount-similar beats more-recent


def test_examples_are_deduplicated():
    mem = CorrectionMemory()
    for i in range(3):
        mem.record(Correction("ACME", f"R-{i}", "rejected", reason="same", proposed="same"))
    assert len(mem.examples_for("ACME", limit=4)) == 1


def test_override_rate_and_review_trigger():
    mem = CorrectionMemory()
    approvals(mem, "ACME", 9)
    mem.record(Correction("ACME", "R", "rejected", reason="check the PO"))
    assert mem.review_needed(threshold=0.20) is None  # 10% under 20%
    for i in range(3):
        mem.record(Correction("ACME", f"R{i}", "rejected", reason=f"issue {i}"))
    digest = mem.review_needed(threshold=0.20)
    assert digest is not None and digest.rate > 0.20 and digest.overrides == 4
    assert any("check the PO" in item["reason"] for item in digest.recent)


def test_review_is_quiet_on_a_tiny_sample():
    mem = CorrectionMemory()
    mem.record(Correction("ACME", "R", "rejected", reason="one bad one"))
    assert mem.review_needed(threshold=0.20, min_total=10) is None


def test_persistence_round_trips(tmp_path):
    mem = CorrectionMemory()
    mem.record(Correction("ACME", "INV-1", "corrected", reason="why",
                          fields={"cost_center": "CC-2000"}, amount="1190.00"))
    mem.record(Correction("ACME", "INV-2", "approved"))
    path = tmp_path / "memory.jsonl"
    mem.save(path)
    back = CorrectionMemory.load(path)
    assert len(back) == 2
    assert back.learned_field("ACME", "cost_center") == "CC-2000"
    assert [e.reason for e in back.examples_for("ACME")] == ["why"]
