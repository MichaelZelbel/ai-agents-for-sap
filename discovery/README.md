# Understand your system before you build

An agent is only as good as what it knows about *your* system. The generic patterns
in this repo assume a clean, stand-in SAP. Your real system has custom tables, custom
fields on standard tables, bespoke function modules, a triage transaction someone
wrote in 2014, and a dispute class nobody remembers. An AI that does not know those
will build a generic agent that fits nobody.

This package builds an **object register**: a structured inventory of what is custom
in a system. You use it three ways.

- **Ground an AI in your system**, so a build uses your object names, not invented ones.
- **Ask your system** which custom objects handle a job ("how is three-way match done here?").
- **Check fit-to-standard**, so you question custom before you automate it.

Everything runs offline against a seeded fake system. Point it at a real one by
implementing the source (below).

## Run it

```
python discovery/explore.py                          # what is custom, at a glance
python discovery/explore.py --ask "three-way match"  # the custom objects that touch it
python discovery/explore.py --ask "three-way match" --llm   # a grounded, plain-language answer
python discovery/explore.py --grounding --focus "tax" --out system.md
python discovery/explore.py --fit-to-standard        # where SAP standard may replace custom
```

`--llm` reads your OpenRouter key from a `.env` file (the same one the agents use).
The rest needs no key and no network.

## Ground Claude Code with it

The point of the register is to hand it to the AI that builds your agents. Write a
focused grounding brief and keep it where Claude Code will read it:

```
python discovery/explore.py --grounding --focus "three-way match" --out SYSTEM.md
```

Then, when you build, tell Claude Code to use it: *"Read SYSTEM.md for how this system
handles three-way match, and build the agent against those objects. Do not invent
table or field names; if something you need is not in SYSTEM.md, ask."* Now the agent
comes out fit to your system, not to a generic one.

## Point it at a real tenant

`MockRepositorySource` seeds a fake system so this all runs offline. A real system fills
the same `CustomObject` shape from its ABAP repository. `AbapRepositorySource` is the
reference: give it a `transport` that reads your repository and returns rows, and it maps
them into the register.

What a real transport reads (verify against your own tenant and authorizations):

- **The object directory, `TADIR`** — every repository object, its type, package, and
  author. Filter to the customer namespace (`Z*`, `Y*`) or your custom packages. This is
  the spine `AbapRepositorySource` already maps.
- **Tables and fields, `DD02L` / `DD02T` / `DD03L`** — custom table definitions and their
  fields, and custom fields (append structures) added to standard tables.
- **Programs `TRDIR`, function modules `TFDIR`, transactions `TSTC`, classes `SEOCLASS`,
  CDS views `DDLDEPENDENCY`, enhancements and BAdI implementations** — for names,
  descriptions, and what calls what.
- **Real usage** — where your system can report it (workload statistics, `ST03`, or
  usage-and-procedure logging), so the register knows what is actually used. This is
  what makes the fit-to-standard and retirement signals honest.

How the transport talks to SAP is a tenant decision: a whitelisted RFC read, a released
OData or CDS service that exposes repository metadata, or an export from the ABAP
Development Tools. Which objects you may read, and how, depends on your system and your
authorizations. Treat `AbapRepositorySource` as a recipe to verify, not a guaranteed
connector. The mock runs today; the real read is your integration step, the same way the
agents swap `MockSapClient` for a real S/4HANA client.

## Honest limits

- This inventories the **static** repository: what exists and what it depends on. It is
  not process mining. To see how a process actually *runs* (the real flow, the waits,
  the rework), use a process-mining tool such as SAP Signavio; the register tells you
  which custom objects a process touches, not the live execution path.
- Fit-to-standard here is a **heuristic**, a prompt to check, not a ruling. Whether a
  standard capability truly replaces a custom object is a decision for someone who knows
  both. The register raises the question honestly; a human answers it.
