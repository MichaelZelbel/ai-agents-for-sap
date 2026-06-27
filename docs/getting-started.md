# Getting Started

## What you need

- A computer with Python 3.11 or newer, **or** a cheap cloud server (VPS) that comes with Claude Code.
- That is it. You do not need a real SAP account to run the examples.

## Steps

1. Clone this repo.
2. Open the folder for the pattern you want, for example `patterns/pattern-01-finance-document-to-draft-posting/`.
3. Follow the `README.md` inside that folder. It tells you how to run the example and how to change it with Claude Code.

## How the examples are organized

Each pattern folder has the same shape:

```
src/       the agent and the pattern code
tests/     the tests that prove the pattern works
prompts/   the Claude Code prompts to build, change, or extend the example
```

## The fake SAP system

All patterns share one SAP layer in `shared/sap_client/`. It pretends to be SAP so you can run everything for free. It also shows the control layer a real company would put between an agent and SAP.

(Setup details will be filled in as each pattern is built.)
