# Pattern 4: Dispute Assistant

## What this pattern does

A vendor writes in: "you only paid 1,070 on invoice INV-1001 but it was for 1,190, please pay the difference." Someone in accounts payable has to read it, work out what kind of dispute it is, and write back. This agent helps with that.

It teaches a different safety level from the others. The invoice agent could write to SAP, behind approval. This one cannot do anything at all. It only reads and suggests: it classifies the dispute and drafts a reply. A human reads the draft and decides whether to send it. That is the lowest, safest rung of autonomy — suggest-only — and it is the right rung for a job that is all judgement and words.

The flow has three steps:

1. **Assess** — the agent reads the dispute, classifies it, and drafts a reply.
2. **Guard** — a fixed review (not the AI) checks the category is one we recognise and the draft is not empty.
3. **Suggest** — the agent hands a human the category and the draft. It takes no action; `action_taken` is always `False`.

The rule of the pattern: **the agent only suggests.** Nothing is sent until a human sends it.

## How to run

Set up the environment once (see [docs/getting-started.md](../../docs/getting-started.md)). Then, from this folder:

```
python run_agent.py                    # read the sample dispute, draft a reply
python run_agent.py --case duplicate   # a different sample dispute
python run_agent.py --case not_received
python run_agent.py --assistant llm    # assess with a real model via OpenRouter
```

The default run needs no API key: the assistant is a deterministic stand-in. Run the tests from the repo root with `pytest`.

## What is inside

```
src/dispute/dispute.py      the assess step (LLM-backed) and the review guard
tests/                      tests that prove the guard and the suggest-only rule
run_agent.py                 run it end to end against sample vendor disputes
prompts/                    Claude Code prompts to change or extend it
```

## Status

Built and tested. The three-step flow runs end to end against sample disputes. The "assess" step is a deterministic stand-in by default so it runs offline; an LLM-backed assistant plugs in behind the same interface via `--assistant llm` and `OPENROUTER_API_KEY`. The agent stays suggest-only either way: it drafts a reply for a human and takes no action itself.
