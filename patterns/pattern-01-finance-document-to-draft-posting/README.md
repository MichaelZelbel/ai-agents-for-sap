# Pattern 1: Finance Document to Draft Posting

## What this pattern does

An agent reads a finance document (for example, an invoice) and proposes a draft posting. It does **not** post anything by itself.

The flow has four steps:

1. **Propose** — the agent suggests a posting.
2. **Check** — a fixed set of rules (not the AI) decides if the posting is allowed.
3. **Approve** — a human says yes or no.
4. **Write** — only after a yes, the posting is sent to SAP (here, the fake SAP).

The rule of the pattern: **nothing is posted until a human approves.**

## How to run

Set up the environment once (see [docs/getting-started.md](../../docs/getting-started.md)). Then, from this folder:

```
python run_agent.py --approve yes    # rules pass, you approve, it books
python run_agent.py --approve no     # you reject; nothing is booked
python run_agent.py                  # asks you to approve
```

Run the tests from the repo root with `pytest`.

## What is inside

```
src/pattern1/proposer.py    the "propose" step (rule-based; swap in an LLM)
src/pattern1/validator.py   the fixed rules that pass or fail a posting
src/pattern1/flow.py        ties the four steps together
tests/                      tests that prove each step and the whole flow
run_agent.py                 run it end to end
prompts/                    Claude Code prompts to change or extend it
```

The shared fake/governed SAP layer lives in [shared/sap_client/](../../shared/sap_client/).

## Status

Built and tested. The four-step flow runs end to end against the fake, governed SAP. The "propose" step is rule-based today so it runs offline; an LLM-backed proposer plugs in behind the same interface (next step).
