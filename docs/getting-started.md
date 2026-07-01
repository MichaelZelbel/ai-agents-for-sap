# Getting Started

## What you need

- Python 3.11 or newer, **or** a cheap cloud server (VPS) that comes with Claude Code.
- That is it. You do **not** need a real SAP account to run the examples.

## Setup (once)

From the repo root:

```
python -m venv .venv
# turn the environment on:
.venv\Scripts\activate       # Windows
source .venv/bin/activate    # macOS / Linux
pip install pytest
```

## Run the tests

From the repo root:

```
pytest
```

All tests should pass. If they pass, the examples work.

## Run Pattern 1

```
cd patterns/pattern-01-finance-document-to-draft-posting
python run_agent.py --approve yes    # rules pass, you approve, it books
python run_agent.py --approve no     # you reject; nothing is booked
python run_agent.py                  # asks you to approve
```

## How each pattern is organized

```
src/         the agent and the pattern code
tests/       the tests that prove the pattern works
prompts/     Claude Code prompts to build, change, or extend the example
run_agent.py  run the whole pattern end to end
```

## The fake SAP system

All patterns share one SAP layer in `shared/sap_client/`. It pretends to be SAP so you can run everything for free. It also shows the control layer a real company puts between an agent and SAP: it checks what the agent is allowed to do, holds writes until a human approves, and logs every call.
