---
name: sap-landscape-intelligence
description: Turn Claude Code into an analyst of a specific SAP landscape, grounded on its register. Step 3 of the landscape workflow (sap-landscape-analyze is steps 1 and 2). Use when the user asks about their own SAP system's custom code, clean core / fit-to-standard, what to retire or keep, where to build AI agents, how to design one for their landscape, or an AI governance model. Reads register.json / landscape.md and runs the discovery CLI for facts. The commercial analogs are Nova Intelligence and Conduct AI; this is the DIY version from the book "AI Agents for SAP" (Chapter 28).
---

# SAP Landscape Intelligence

This skill makes you an expert on **one specific SAP landscape**, the one that was
analyzed into an **object register**. Without that register you are generic about
SAP; with it you answer about *their* SAP, using their object names, their clean-core
levels, their processes. The register is the knowledge; you are the analyst; the
`discovery/` CLI computes the facts so nothing is guessed.

This is the honest, book-scale analog of Nova Intelligence and Conduct AI: a grounded
landscape inventory plus an AI that reasons over it.

## Rule 1: ground first, every time

Before you answer anything about the landscape, load it and use only what is there.

- The knowledge is `register.json` (source of truth) and `landscape.md` (readable
  brief) in the workspace, produced by `python discovery/explore.py --save register.json`.
- **No `register.json` yet?** Switch to the `sap-landscape-analyze` skill first: it
  walks the user through mapping their landscape (mock, hand-authored, or a tenant
  read) and enriching it with their BPML and Signavio exports. Then come back here.
- Read them. For a large register, pull the relevant slice instead of the whole file:
  `python discovery/explore.py --from register.json --grounding --focus "<job>"`, or grep.
- **Never invent an object name.** If something the user needs is not in the register,
  say so plainly. That honesty is the whole point of grounding.
- Every command below takes `--from register.json` to run against the user's own
  landscape (omit it and it runs against the seeded Nordwind demo).

## Rule 2: know the vocabulary (clean core)

Clean core is the spine of every answer. SAP classifies each extension into a level:

- **Level A** released/public APIs and released extension points. Upgrade-safe. The target.
- **Level B** classic but SAP-nominated: legacy APIs, user-exits, BAdIs, classic frameworks.
- **Level C** partially compliant; reaches into SAP-internal objects. Higher risk.
- **Level D** core modifications, implicit enhancements, direct table writes. Not recommended.

"Released API first" is the principle: prefer standard config and released APIs; treat
custom as the exception that must earn its place. When you need the real SAP standard,
point the user at the **Business Accelerator Hub** (released APIs/CDS), and for live
fidelity the **ABAP Test Cockpit clean-core check**, the **Custom Code Migration app**,
**SAP Readiness Check**, and **SAP Signavio Process Insights**. The book's Appendix E
(seven-layer reference architecture) and Appendix D (tenant validation checklist) are
your governance references.

## Rule 3: run the tools, do not guess

The `discovery/` CLI computes the facts. Run the right one, then reason over its output.

- `--cleancore` clean-core level (A/B/C/D) per object, with why.
- `--scorecard` fit-to-standard, ranked: keep / replace / re-platform / retire, with reasons.
- `--standard` what is custom vs the standard objects it leans on.
- `--opportunities` where to build AI agents, each mapped to a pattern in the catalog.
- `--governance` the clean-core risk (Level C/D) by owner.
- `--impact NAME` what depends on an object, and what it depends on.
- `--diagram --focus "<job>"` a mermaid dependency graph.
- `--design "<job>"` a grounded design brief + a proposed process as mermaid and BPMN 2.0.

## The methods (answer these the book's way)

**"What is custom / standard here?"** Read `landscape.md`; run `--standard`. State what is
custom and which standard objects it leans on.

**"How do we get more fit-to-standard?"** Run `--scorecard` and `--governance`. Build a
**phased roadmap**: retire the easy, low-use, no-dependent objects first (they are free
wins); then the standard-replaceable ones (name the standard target and the effort); then
re-platform the Level-C/D risks onto released APIs. Use `--impact` to check the ripple
before you sequence anything. Keep the genuinely differentiating custom (high value, real
usage, no standard equivalent). Always: this ranks ease and risk, not correctness, so a
human who knows both must rule.

**"Where should we use AI agents?"** Run `--opportunities`. It ranks processes by volume x
manual x rule-shaped and maps each to a pattern (Part III catalog). Recommend the strongest,
name the pattern and its shape, and say plainly that low-volume work is a weak candidate
even when it is manual.

**"Build me such an agent."** Invoke the **`sap-ai-agent-pro-code`** skill to build it, but
ground it on this landscape: the objects it should use (from the register, keyed the way
their table is keyed, not a standard table they never had), and a proposed process from
`--design "<job>"` (mermaid + BPMN for Signavio / SAP Build). Never name an object that is
not in the register.

**"Suggest an AI governance model."** Instantiate the book's governance stack for *this*
landscape: draft-first (the AI proposes, a deterministic guard decides, a human approves,
everything is logged), the autonomy ladder (Chapter 17, start low and earn each rung), the
seven-layer responsibilities (Appendix E), and the tenant validation gates (Appendix D).
Tie each to the actual risky objects `--governance` surfaced (name owners for the Level-D
exposure, cap new Level-D extensions).

## Honest limits

Say these when they apply. The register is a **static** analysis: the diagrams draw the
design and the landscape (what exists, what it leans on, a proposed process), **not process
mining** (how the process runs from event logs). Real usage over 12-13 months, a real
dependency crawl, and reconstructed business logic need a **live tenant** and the SAP tools
named above; offline, usage and clean-core levels are faithful teaching data, not a live
verdict. The scorecard ranks ease and risk, not correctness. You raise the question honestly;
a human rules.
