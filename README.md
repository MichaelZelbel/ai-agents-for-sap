# AI Agents for SAP — Book Code

![CI](https://github.com/MichaelZelbel/ai-agents-for-sap/actions/workflows/ci.yml/badge.svg)

Companion code for the book **AI Agents for SAP**.

This repo holds ready-to-run examples of the agent patterns from the book. You clone it, run an
example, and build on it with Claude Code — exactly as the book leads you through, step by step.

## How the examples run

The examples talk to a **fake SAP system** that lives inside this repo. You do **not** need a real
SAP account to run them.

This is on purpose. In a real company, an agent does not connect straight to SAP. It goes through one
controlled layer that checks what the agent is allowed to do, holds writes for approval, and logs
every call. This repo copies that shape, so what you build here looks like how it is really done.

If you later have a real SAP tenant, you swap the fake SAP layer for a real one. The rest of the
example stays the same.

## The running example

The book follows one company — **Nordwind Fertigung GmbH** — and its incoming-invoice problem. See
[docs/scenario.md](docs/scenario.md).

## What you need

- **Python 3.11 or newer.** That is it to run the examples. (Later chapters add a model API key and,
  if you want, a cheap always-on server.)

## Quick start

```bash
git clone https://github.com/MichaelZelbel/ai-agents-for-sap.git
cd ai-agents-for-sap
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows
pip install pytest
pytest                           # all tests pass = the examples work
```

Then run the first agent end to end:

```bash
cd patterns/pattern-01-finance-document-to-draft-posting
python run_demo.py --approve yes    # rules pass, you approve, it books
python run_demo.py --approve no     # you reject; nothing is booked
python run_demo.py                  # asks you to approve
```

Full setup notes: [docs/getting-started.md](docs/getting-started.md).

## What is inside

```
patterns/   one folder per pattern from the book (code, tests, prompts)
shared/     the SAP client layer shared by all patterns (fake + governed)
diagrams/   the process diagrams used as build specs (added with the pro-code chapters)
docs/       setup, the running scenario, and the chapter map
```

## Which chapter runs what

See [docs/CHAPTERS.md](docs/CHAPTERS.md) — it maps each book chapter to exactly what to run here.

## Status

Work in progress, built alongside the book. Every example is built and run end to end, with passing
tests, before it is marked ready. If it is in here and the tests are green, it works.

## License

[MIT](LICENSE). Use it, adapt it, build on it.
