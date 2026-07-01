# Pattern 6: Close Orchestration and Blocker Prediction

## What this pattern does

A month-end close is a graph of dependent tasks. An agent reads the close
tasks (owner, deadline, status, dependencies) plus a few signals (posted late
last period, a backed-up queue, an overloaded owner). It scores which tasks
are likely to block the critical path and ranks them by impact. It does
**not** change the plan by itself.

This is a suggest-only pattern. The flow has these steps:

1. **Score** — the agent scores each task's chance of blocking the close.
2. **Rank** — tasks are ranked by impact, highest first.
3. **Guard** — a fixed, deterministic rule turns a score into a proposed
   mitigation: a reminder, a re-sequence, or an escalation.
4. **Stage** — each intervention is staged with a before/after preview.
5. **Approve** — the close manager says yes or no.
6. **Apply** — only after a yes, the in-memory plan is updated.

The rule of the pattern: **the model only scores; a deterministic guard
decides the mitigation; nothing changes the plan until a human approves.**
Every high-impact intervention is logged with a trace id and the actor.

## How to run

Set up the environment once (see [docs/getting-started.md](../../docs/getting-started.md)). Then, from this folder:

```
python run_agent.py                # predict and preview; nothing changes
python run_agent.py --approve      # apply the top intervention to the plan
python run_agent.py --scorer llm   # score with a real model (needs a key)
```

The default run needs no API key. Run the tests from the repo root with `pytest`.

## What is inside

```
src/close/models.py       the frozen data models (Decimal money)
src/close/plan.py         seeds the sample plan; applies an approved change
src/close/scorer.py       the "score" step (rule-based; swap in an LLM)
src/close/mitigation.py   the deterministic guard: score -> mitigation
src/close/flow.py         ties the steps together, with staging and a log
tests/                    tests that prove each step and the whole flow
run_agent.py              run it end to end
prompts/                  Claude Code prompts to change or extend it
```

## Sample data

Five close tasks in one dependency chain:

```
reconcile bank -> post accruals -> run allocations -> close subledgers -> publish
```

"Post accruals" is the clearly at-risk task. It was late last period, its
queue is backed up, and its owner is overloaded. It sits early in the chain,
so if it slips the whole close slips. The agent scores it highest and the
guard proposes an escalation.

## The scorer is injectable

The scoring step is the only place a model may weigh in, and it is injectable.
Tests pass a plain `complete` callable, so the whole suite runs offline with
no API key. The default scorer is deterministic, so `run_agent.py` needs no
key. An optional OpenRouter-backed scorer (`OPENROUTER_API_KEY`, model
`openai/gpt-4o-mini`) plugs in behind the same interface. It is never required.

## Status

Built and tested. The suggest-only flow runs end to end in memory. The score
step is deterministic today so it runs offline; an LLM-backed scorer plugs in
behind the same interface.
