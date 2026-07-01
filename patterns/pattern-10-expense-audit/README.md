# Pattern 10: Expense Report Audit with Policy Guardrails

## What this pattern does

An agent audits a travel and expense report line by line. For each line it
**drafts** whether the line matches policy and why. It does **not** decide.

The shape is classify and route. Four steps per line:

1. **Draft** — the AI guesses if the line is compliant, with reasons.
2. **Guard** — a deterministic check reads the **current, versioned policy** and
   makes the real decision. The AI never gets a vote.
3. **Route** — a compliant line goes to fast approval. A failed check routes to
   the manager. A repeat or high value violation escalates to compliance.
4. **Approve** — a human approves exceptions. Nothing about a violation is auto
   approved.

The rule of the pattern: **the guard decides against the policy in force, and
the log records which policy version judged each line.**

## What the guard checks

Reading the current `Policy` object, for every line:

- the receipt total equals the claimed amount,
- a receipt is present when the amount is at or above the receipt threshold,
- the category is allowed,
- the per diem or category cap is respected,
- the date falls inside the reporting period,
- and the correct approver tier is assigned for the amount.

Change the policy version (raise a cap, shift the period) and the same report
can route differently. The version travels into the log so an auditor can always
tell which rules applied.

## How to run

Set up the environment once (see [docs/getting-started.md](../../docs/getting-started.md)).
Then, from this folder:

```
python run_agent.py                    # audit the sample report, offline
python run_agent.py --report EXP-2001  # pick a report by id
python run_agent.py --drafter llm      # use a real model via OpenRouter
```

No SAP account and no API key are needed. The default drafter is a deterministic
stand in, so it runs in memory and offline. The model-backed drafter is optional
and never required: set `OPENROUTER_API_KEY` and pass `--drafter llm` to use it.

Run the tests from the repo root with `pytest`.

## What is inside

```
src/expense/models.py     frozen dataclasses: line, report, policy, verdict, route
src/expense/auditor.py    the drafters, the deterministic guard, routing, sample data
tests/                    tests that prove the guard decides and the routing is right
run_agent.py              run it end to end
prompts/                  Claude Code prompts to change or extend it
```

The sample data is one report with a compliant line, an over per diem line, and
a missing receipt line, plus a versioned policy object.

## Status

Built and tested. The draft, guard, route, approve flow runs end to end offline.
The "draft" step is deterministic today so it needs no key; an LLM-backed drafter
plugs in behind the same interface and only ever drafts.
