# Pattern 3: Three-Way Match

## What this pattern does

Before an invoice is allowed through, it must agree with two other documents: the purchase order (did we order this, at this price and quantity?) and the goods receipt (did we actually receive it?).

The hard part is lining the invoice up against the purchase order, because the same item is worded differently on each ("Ergonomic office chair" vs "Office chairs, ergonomic"). That matching is a real job for the model. The checking that follows — quantities and money agreeing within tolerance — is firm arithmetic, and that stays deterministic.

The flow has two steps:

1. **Match** — the agent maps each invoice line to the purchase-order line that means the same item.
2. **Guard** — a fixed arithmetic check (not the AI) confirms every matched line agrees on quantity, receipt, and price. If a number does not agree, the invoice is held, not paid.

The rule of the pattern: **AI to match, rules to decide.** A wrong match cannot make the numbers agree, so the guard still catches it.

## How to run

Set up the environment once (see [docs/getting-started.md](../../docs/getting-started.md)). Then, from this folder:

```
python run_agent.py                    # a clean match: it passes
python run_agent.py --case overpriced  # a price mismatch: the guard fails it
python run_agent.py --case short       # goods not fully received: the guard fails it
python run_agent.py --matcher llm      # match lines with a real model via OpenRouter
```

The default run needs no API key: the line matcher is a deterministic stand-in and the arithmetic guard is always real. Run the tests from the repo root with `pytest`.

## What is inside

```
src/threeway/threeway.py    the match step (LLM-backed) and the arithmetic guard
tests/                      tests that prove the guard on clean and broken invoices
run_agent.py                 run it end to end against a sample invoice, order, and receipt
prompts/                    Claude Code prompts to change or extend it
```

## Status

Built and tested. The two-step flow runs end to end against a sample invoice, purchase order, and goods receipt. The "match" step is a deterministic stand-in by default so it runs offline; an LLM-backed matcher plugs in behind the same interface via `--matcher llm` and `OPENROUTER_API_KEY`. The arithmetic guard is deterministic and runs the same either way.
