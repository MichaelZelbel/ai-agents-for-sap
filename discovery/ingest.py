"""Pull what your enterprise already knows into the register.

Most companies already hold landscape knowledge outside SAP: a business process
master list (BPML) kept in a spreadsheet, and process diagrams modeled in SAP
Signavio and exported as BPMN 2.0. This module ingests both, deterministically:

- `processes_from_csv` reads a BPML exported as CSV (save your Excel sheet as CSV).
- `processes_from_bpmn` reads a BPMN 2.0 file (a Signavio or SAP Build export) and
  turns each process into a register entry, its tasks listed as the detail.
- `merge_processes` folds the new entries into a register: an entry with the same
  name replaces the old one, everything else is appended.

For any other format (a raw Excel file, a Word document, a wiki page), let Claude
Code read it and convert it to this CSV shape first; the deterministic path stays
small and testable, and the AI handles the mess at the edge.
"""

from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

from .models import ObjectRegister, ProcessInfo, RegisterFormatError

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"

# BPMN task flavors we list as steps. Localnames, so any prefix works.
_TASK_TAGS = {
    "task",
    "userTask",
    "serviceTask",
    "manualTask",
    "scriptTask",
    "businessRuleTask",
    "sendTask",
    "receiveTask",
    "callActivity",
}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def processes_from_bpmn(path: str | Path) -> list[ProcessInfo]:
    """Each `process` in a BPMN 2.0 file as a register entry. The tasks become the
    detail, so the register knows the steps the diagram names. Volumes and manual
    effort are not in a diagram; add those yourself (or answer the analyze skill's
    questions), or the opportunity map will honestly say "volume not measured"."""
    path = Path(path)
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise RegisterFormatError(f"{path.name} is not valid XML: {exc}") from exc
    if _local(root.tag) != "definitions":
        raise RegisterFormatError(f"{path.name} is not a BPMN file (no definitions root)")

    out: list[ProcessInfo] = []
    for proc in root.iter(f"{{{BPMN_NS}}}process"):
        name = proc.get("name") or proc.get("id") or path.stem
        steps = [
            el.get("name") or el.get("id", "")
            for el in proc.iter()
            if _local(el.tag) in _TASK_TAGS
        ]
        steps = [s for s in steps if s]
        detail = f"imported from {path.name}"
        if steps:
            detail += "; steps: " + ", ".join(steps)
        out.append(ProcessInfo(name=name, detail=detail))
    if not out:
        raise RegisterFormatError(f"{path.name} holds no process elements")
    return out


def _norm_header(header: str) -> str:
    return header.strip().lower().replace(" ", "_").replace("-", "_")


def _split_list(value: str) -> tuple[str, ...]:
    return tuple(v.strip() for v in value.split(";") if v.strip())


def _int_or_none(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def processes_from_csv(path: str | Path) -> list[ProcessInfo]:
    """A business process master list from CSV. Flexible about headers (case and
    spacing are forgiven); `name` is required, the rest is optional:
    name, area, variants, monthly_volume, manual_rework, deviation_from_standard,
    kpis (semicolon separated), objects (semicolon separated), detail."""
    path = Path(path)
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise RegisterFormatError(f"{path.name} has no header row")
        headers = {_norm_header(h): h for h in reader.fieldnames}
        if "name" not in headers and "process" not in headers:
            raise RegisterFormatError(
                f"{path.name} needs a 'name' (or 'process') column; found: "
                + ", ".join(reader.fieldnames)
            )
        name_col = headers.get("name") or headers["process"]

        def get(row: dict, key: str) -> str:
            col = headers.get(key)
            return (row.get(col) or "").strip() if col else ""

        out: list[ProcessInfo] = []
        for row in reader:
            name = (row.get(name_col) or "").strip()
            if not name:
                continue
            out.append(
                ProcessInfo(
                    name=name,
                    area=get(row, "area"),
                    variants=_int_or_none(get(row, "variants")),
                    deviation_from_standard=get(row, "deviation_from_standard")
                    or get(row, "deviation"),
                    monthly_volume=_int_or_none(get(row, "monthly_volume"))
                    if get(row, "monthly_volume")
                    else _int_or_none(get(row, "volume")),
                    manual_rework=get(row, "manual_rework"),  # type: ignore[arg-type]
                    kpis=_split_list(get(row, "kpis")),
                    objects=_split_list(get(row, "objects")),
                    detail=get(row, "detail") or f"imported from {path.name}",
                )
            )
    if not out:
        raise RegisterFormatError(f"{path.name} holds no process rows")
    return out


def ingest_file(path: str | Path) -> list[ProcessInfo]:
    """Ingest one file by suffix: .bpmn/.xml as BPMN 2.0, .csv as a BPML export."""
    suffix = Path(path).suffix.lower()
    if suffix in (".bpmn", ".xml"):
        return processes_from_bpmn(path)
    if suffix == ".csv":
        return processes_from_csv(path)
    raise RegisterFormatError(
        f"cannot ingest {Path(path).name}: use .bpmn/.xml (a Signavio export) or .csv "
        "(a BPML export). For anything else, convert it to that CSV shape first."
    )


def merge_processes(register: ObjectRegister, incoming: list[ProcessInfo]) -> ObjectRegister:
    """Fold ingested processes into the register. Same name (case-insensitive)
    replaces the existing entry; new names are appended. Objects are untouched."""
    by_name = {p.name.upper(): p for p in register.processes}
    for p in incoming:
        by_name[p.name.upper()] = p
    merged = tuple(sorted(by_name.values(), key=lambda p: p.name.upper()))
    return replace(register, processes=merged)
