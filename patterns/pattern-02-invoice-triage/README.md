# Pattern 2: Invoice Triage

## What this pattern does

An incoming accounts-payable document arrives. An agent reads it and classifies it into one of a few known categories. It does **not** decide the next step by itself. A fixed router turns the category into the next step, and refuses any label it does not recognise, so a stray answer from the model can never send a document down the wrong path.

The flow has three steps:

1. **Classify** — the agent suggests a category (`po_invoice`, `direct_expense`, or `not_an_invoice`).
2. **Guard** — a fixed router (not the AI) turns a known category into its next step and refuses anything else.
3. **Route** — the document goes to the next step: three-way match, post directly, or send to a person.

The rule of the pattern: **a made-up category cannot route a document anywhere.** The model proposes; firm rules guard it.

## How to run

Set up the environment once (see [docs/getting-started.md](../../docs/getting-started.md)). Then, from this folder:

```
python run_agent.py                  # triage INV-1001 offline (no key)
python run_agent.py --doc INV-1002   # triage a different document
python run_agent.py --triager llm    # classify with a real model via OpenRouter
```

The default run needs no API key: the classifier is a deterministic stand-in. Run the tests from the repo root with `pytest`.

## What is inside

```
src/triage/triage.py        the classify step (LLM-backed; deterministic stand-in in run_agent)
process/accounts-payable.bpmn  the process diagram; the spec the agent must agree with
tests/                      tests that prove the guard and that the diagram matches the agent
run_agent.py                 run it end to end
prompts/                    Claude Code prompts to change or extend it
```

The shared fake SAP layer (documents, models) lives in [shared/sap_client/](../../shared/sap_client/).

## Status

Built and tested. The three-step flow runs end to end. The "classify" step is a deterministic stand-in by default so it runs offline; an LLM-backed classifier plugs in behind the same interface via `--triager llm` and `OPENROUTER_API_KEY`. A BPMN test proves the process diagram and the agent's categories stay in step.
