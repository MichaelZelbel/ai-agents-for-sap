# The operator cockpit

A small, SAP-Fiori-flavored console for the agents. It gives the propose → guard →
approve → log flow a face: an inbox of documents, the agent's proposal, the guard's
verdict, action buttons, and the audit trail right there.

One console, more than one agent. Ships wired to **two** patterns, switched from the
picker in the top bar: Pattern 1 (invoice posting) and Pattern 2 (document triage).

![Pattern 1: invoice posting](console.png)

![Pattern 2: document triage, same console](console-triage.png)

## Run it

```
python console/serve.py
```

Then open <http://localhost:8000>. No SAP account, no API key, no dependencies, all in
memory. It opens your browser automatically.

## What you can do

- **Drop a real invoice.** Drag a PDF or an image onto the tile at the top of the
  inbox (or click to choose one). A vision model reads it into the fields, with a read
  confidence, and it lands in the inbox like any other document. This needs your
  OpenRouter key in a `.env` file (see the Pattern 1 README); without it the drop
  reports that it could not read the file, and the seeded documents still work offline.
- **See the inbox.** Four seeded documents, each with a status: ready, or an exception
  with its reason (a total that does not balance, a vendor not in the master).
- **Read the proposal.** The agent's posting lines, the determined tax code and cost
  center, and the guard's PASS or FAIL with reasons.
- **Approve and post**, or **reject** (nothing is written). Watch the audit trail fill
  in, read → stage → approve → confirm, and the chain report that it is untampered.
- **Onboard a vendor.** For the unknown-vendor exception, one click adds the Business
  Partner to the master and the invoice becomes ready, the way a master-data team
  resolves it.

Note: the drop-a-PDF tile and Pattern 1's tax/cost/confidence checks are on the
invoice agent; the triage agent classifies a document and routes it, with no posting
at all. Same screen, different job.

## How it generalises

Every pattern in this repo shares the same shape, so one console fits them all, and
this build proves it with two. Each agent fills one neutral contract, an inbox and a
detail with a proposal (a table), a verdict, some actions, and a trail, and the same
page renders any of them. `InvoicePostingAgent` returns posting lines and Approve /
Reject / Onboard; `TriageAgent` returns a category and its route and Confirm / Reject.
The page does not know or care which pattern it is showing.

To add a third, write one more adapter (`inbox`, `detail`, `act`) and register it in
`AGENTS`. It appears in the picker; nothing in the page changes.

Built with the Python standard library only (`http.server`) plus one static HTML page.
