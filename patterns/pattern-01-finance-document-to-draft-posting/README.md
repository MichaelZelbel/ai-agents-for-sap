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

(Coming soon. This example is being built and tested before these steps are written.)

## Folders

```
src/       the agent and the four-step flow
tests/     tests that prove each step works
prompts/   Claude Code prompts to build or change this example
```

## Status

Not built yet. This README will be filled in once the example runs end to end.
