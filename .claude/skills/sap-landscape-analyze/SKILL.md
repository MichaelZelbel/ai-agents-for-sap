---
name: sap-landscape-analyze
description: Guided analysis of an SAP landscape into a register.json Claude Code can reason over. Use when the user wants to analyze, map, or inventory their SAP system, start the landscape workflow, connect the register to their tenant, or add enterprise documentation (a business process master list, Signavio BPMN exports) to the analysis. Steps 1 and 2 of the landscape workflow; sap-landscape-intelligence is step 3.
---

# Analyze an SAP landscape (steps 1 and 2)

You are guiding the user through building their landscape register: the file that
makes every later answer about *their* SAP instead of a generic one. The workflow has
three steps; this skill walks steps 1 and 2, then hands off:

1. **Map** the landscape into `register.json` (this skill).
2. **Enrich** it with what the enterprise already knows (this skill).
3. **Analyze**: ask anything, find agent opportunities, design, govern
   (the `sap-landscape-intelligence` skill).

Work conversationally: one step at a time, confirm before writing files, and after
every write **verify** by reloading (`python discovery/explore.py --from register.json`)
and showing the summary. Never claim a connection or data you do not have.

## Step 1: map the landscape

Ask which source applies (offer all three; do not assume):

**A. The mock (start here, works today).** No SAP needed:
```
python discovery/explore.py --save register.json
```
That writes `register.json` and `landscape.md` for Nordwind, the seeded demo
landscape. Good for learning the workflow before pointing it at anything real.

**B. Their own landscape, by hand or export (the pragmatic real path).** Copy
`discovery/samples/nordwind-register.json` as a template and fill it with their
objects. Offer to do the tedious part: if they can paste or drop an export (a TADIR
extract, a custom-code list from the Custom Code Migration app, an ATC result, a
spreadsheet of Z-objects), read it and write the entries into `register.json`
yourself, then validate by reloading. Ask for the fields that matter most as you go:
monthly usage, what each object depends on, who owns it, and any known standard
alternative. Partial is fine; the analyses degrade honestly (they say "usage not
measured" rather than guessing).

**C. A live tenant read (the integration step).** Be honest: there is no magic
connector. `AbapRepositorySource` in `discovery/sources.py` is the documented recipe:
they provide a `transport` callable that reads their repository (a whitelisted RFC
read, a released OData/CDS service, or an ADT export) and it maps TADIR rows into the
register. Walk them through what each enriched field needs: usage from ST03N/UPL/SCMON,
clean-core levels from the ATC clean-core check, standard alternatives from SAP
Readiness Check. What they may read depends on their authorizations; say so.

After any of the three: run the reload check and show the user their landscape summary.

## Step 2: enrich with what the enterprise already knows

Ask what documentation exists. Most enterprises have more than they think:

- **A business process master list (BPML)** in Excel: have them export it as CSV (or
  read the Excel yourself and write the CSV), then:
  `python discovery/explore.py --from register.json --ingest bpml.csv --save register.json`
- **Signavio / SAP Build process diagrams** exported as BPMN 2.0:
  `python discovery/explore.py --from register.json --ingest process.bpmn --save register.json`
- **Anything else** (Word, wiki, slides): read it and convert what it says about
  processes into the CSV shape (name, area, monthly_volume, manual_rework,
  deviation_from_standard, objects, detail), then ingest that.

A diagram carries no volumes, so after a BPMN ingest ask the user for the two numbers
the opportunity map needs per process: **monthly volume** and **manual effort**
(low/medium/high). Write them into the register (edit the JSON, reload to verify).
`discovery/samples/nordwind-processes.csv` shows the CSV shape.

## Hand off to step 3

When `register.json` loads cleanly and the user is satisfied with what it holds, tell
them the landscape is ready and switch to the `sap-landscape-intelligence` skill: ask
anything, `--opportunities`, `--scorecard`, `--governance`, `--design`. Suggest the
first question based on what you saw in their landscape (for example the biggest
Level-D risk or the highest-volume manual process).
