# Landscape intelligence: make Claude Code an expert on your system

An agent is only as good as what it knows about *your* system. The generic patterns
in this repo assume a clean, stand-in SAP. Your real system has custom tables, custom
fields on standard tables, bespoke function modules, a triage transaction someone
wrote in 2014, and a dispute class nobody remembers. An AI that does not know those
builds a generic agent that fits nobody.

This package builds a **landscape register**: a structured inventory of a specific SAP
system, rich enough to reason over like an analyst. Each custom object carries its
clean-core level (A/B/C/D), its usage, its dependencies, and the standard capability
that might replace it; the register also holds the module profile, the business
processes, and the interfaces. Save it as `register.json`, hand it to Claude Code with
the **`sap-landscape-intelligence`** skill, and ask anything.

This is the honest, book-scale version of what Nova Intelligence and Conduct AI do
commercially: a grounded landscape inventory plus an AI that reasons over it.

## Run it (all offline, no key)

```
python discovery/explore.py                          # what is custom, at a glance
python discovery/explore.py --cleancore              # clean-core level (A/B/C/D) per object
python discovery/explore.py --scorecard              # fit-to-standard: keep/replace/re-platform/retire
python discovery/explore.py --standard               # custom vs the standard objects it leans on
python discovery/explore.py --opportunities          # where to build AI agents, mapped to the patterns
python discovery/explore.py --governance             # clean-core risk (Level C/D) by owner
python discovery/explore.py --impact ZTHREEWAY_TOL   # what depends on an object
python discovery/explore.py --diagram --focus "tax"  # a mermaid dependency graph
python discovery/explore.py --design "three-way match"   # grounded brief + process + BPMN for Signavio
python discovery/explore.py --ask "three-way match"  # the custom objects that touch a job
python discovery/explore.py --ask "..." --llm        # a grounded, plain-language answer
python discovery/explore.py --save register.json     # save the whole landscape (+ landscape.md)
python discovery/explore.py --from register.json --scorecard   # analyze YOUR saved landscape
```

`--llm` reads your OpenRouter key from a `.env` file; everything else needs no key and
no network.

## Make Claude Code your landscape analyst

The register is the knowledge; Claude Code is the analyst. Save the landscape, then talk:

```
python discovery/explore.py --save register.json
```

That writes `register.json` (the source of truth) and `landscape.md` (a readable brief).
With the `sap-landscape-intelligence` skill installed, Claude Code reads them and runs
the CLI for facts, so you can ask open-ended questions and get grounded answers: how to
get more fit-to-standard, where to build AI agents and which pattern fits, "build me that
agent", or an AI governance model for the landscape. No server, no MCP: Claude Code reads
the file and runs the CLI. (You could wrap the CLI in an MCP server for Claude Desktop or
a headless service, but you do not need to for Claude Code with the repo.)

## Point it at a real tenant

`MockRepositorySource` seeds a fake system so this all runs offline. For your own, either
**hand-author or export a `register.json`** in the schema and pass `--from`, or fill the
same shape from your ABAP repository via `AbapRepositorySource` (a `transport` that reads
your repository and returns rows).

What a real read supplies, and where the offline model is only faithful teaching data:

- **The object directory `TADIR`** (type, package, author), and definitions from
  `DD02L/DD03L`, `TRDIR/TFDIR/TSTC/SEOCLASS/DDLDEPENDENCY`. The spine `AbapRepositorySource`
  maps.
- **Real usage** over 12-13 months from `ST03N` / UPL / SCMON. This is what makes the
  retirement and fit-to-standard signals real rather than sampled.
- **Clean-core level and successor APIs** from the **ATC clean-core check** and SAP's public
  released-API classification (`github.com/SAP/abap-atc-cr-cv-s4hc`). This module mirrors
  those rules offline; a live tenant gets the authoritative verdict.
- **Dependencies / blast radius** from a repository dependency crawl (the territory of the
  Custom Code Migration app, smartShift, Panaya, LiveCompare).
- **Standard-alternative and simplification impact** from **SAP Readiness Check**; **process**
  fidelity from **SAP Signavio Process Insights**.

Treat `AbapRepositorySource` as a recipe to verify against your own system and
authorizations, not a guaranteed connector. The mock runs today; the real read is your
integration step, the same way the agents swap `MockSapClient` for a real S/4HANA client.

## Honest limits

- This inventories the **static** landscape: what exists, what it leans on, and a proposed
  process shape. It is **not process mining**. To see how a process actually runs (the real
  flow, the waits, the rework), use SAP Signavio Process Insights against a live system.
- The clean-core levels and the fit-to-standard scorecard rank **ease and risk, not
  correctness**. Whether a standard capability truly replaces a custom object, and whether
  an object is safe to retire, are decisions for someone who knows both. The register raises
  the question honestly; a human answers it.
