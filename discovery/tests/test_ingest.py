"""Ingesting enterprise knowledge: a Signavio-style BPMN export and a BPML CSV
both become register processes, and merging replaces by name."""

import pytest

from discovery.ingest import (
    ingest_file,
    merge_processes,
    processes_from_bpmn,
    processes_from_csv,
)
from discovery.models import RegisterFormatError
from discovery.register import build_register
from discovery.sources import MockRepositorySource

BPMN_PATH = "patterns/pattern-02-invoice-triage/process/accounts-payable.bpmn"


def test_bpmn_ingest_reads_the_process_and_its_steps():
    procs = processes_from_bpmn(BPMN_PATH)
    assert len(procs) == 1
    p = procs[0]
    assert p.name == "Accounts Payable Intake"
    assert "Triage document" in p.detail
    assert "accounts-payable.bpmn" in p.detail
    assert p.monthly_volume is None  # a diagram carries no volumes; stay honest


def test_bpmn_ingest_rejects_a_non_bpmn_file(tmp_path):
    bad = tmp_path / "x.bpmn"
    bad.write_text("<notbpmn/>", encoding="utf-8")
    with pytest.raises(RegisterFormatError):
        processes_from_bpmn(bad)


def test_csv_ingest_is_forgiving_about_headers(tmp_path):
    f = tmp_path / "bpml.csv"
    f.write_text(
        "Process,Area,Volume,Manual Rework,Objects\n"
        "Order-to-cash billing,O2C,5400,medium,ZBILL_BLOCK;ZBILL_LOG\n",
        encoding="utf-8",
    )
    procs = processes_from_csv(f)
    assert len(procs) == 1
    p = procs[0]
    assert p.name == "Order-to-cash billing"
    assert p.monthly_volume == 5400
    assert p.manual_rework == "medium"
    assert p.objects == ("ZBILL_BLOCK", "ZBILL_LOG")


def test_csv_ingest_requires_a_name_column(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("area,volume\nP2P,10\n", encoding="utf-8")
    with pytest.raises(RegisterFormatError):
        processes_from_csv(f)


def test_ingest_file_dispatches_by_suffix(tmp_path):
    assert ingest_file(BPMN_PATH)[0].name == "Accounts Payable Intake"
    with pytest.raises(RegisterFormatError):
        ingest_file(tmp_path / "notes.docx")


def test_merge_replaces_by_name_and_appends_new():
    reg = build_register(MockRepositorySource())
    before = {p.name for p in reg.processes}
    assert "Accounts payable invoice-to-pay" in before

    from discovery.models import ProcessInfo

    merged = merge_processes(
        reg,
        [
            ProcessInfo(name="ACCOUNTS PAYABLE INVOICE-TO-PAY", monthly_volume=9999),
            ProcessInfo(name="Order-to-cash billing", area="O2C"),
        ],
    )
    names = [p.name for p in merged.processes]
    # replaced case-insensitively, not duplicated
    assert sum("INVOICE-TO-PAY" in n.upper() for n in names) == 1
    updated = next(p for p in merged.processes if "invoice-to-pay" in p.name.lower())
    assert updated.monthly_volume == 9999
    assert "Order-to-cash billing" in names
    # objects untouched
    assert len(merged.objects) == len(reg.objects)
