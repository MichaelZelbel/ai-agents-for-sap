# Pattern 8: Cash Application / Incoming Payment Matching

## What this pattern does

An agent reads an incoming payment and its remittance advice, looks at the
customer's open invoices, and proposes which invoices the payment clears. It
does **not** clear anything by itself.

The shape here is **match-and-check**:

1. **Propose** — the agent pairs the payment to a set of open invoices,
   reading the remittance references and accounting for a credit note.
2. **Guard** — a deterministic guard (not the AI) confirms the matched set
   reconciles to the payment within a small tolerance. It flags short/partial
   payments and overpayments, refuses anything that does not reconcile, and
   refuses to clear the same payment or invoice twice (idempotency).
3. **Approve** — a human approves a clean match. Exceptions route to an AR
   specialist instead. The human is never asked to approve an exception.
4. **Clear** — only after a yes, the clearing posts to the fake AR ledger.

The rule of the pattern: **nothing clears until the guard confirms a match
AND a human approves.** Every step is logged.

## How to run

Set up the environment once (see the repo's getting-started docs). Then, from
this folder:

```
python run_agent.py --payment PAY-9001            # show the match and the verdict
python run_agent.py --payment PAY-9001 --approve   # clear a clean match
python run_agent.py --payment PAY-9002            # a short / partial payment (routed)
python run_agent.py --payment PAY-9003            # an overpayment (routed)
```

No SAP account and no API key are needed. The default matcher is deterministic
and runs offline. To use a real model instead, set `OPENROUTER_API_KEY` and
pass `--matcher llm`.

Run the tests from the repo root with `pytest`.

## The sample data

One customer, Nordwind Retail GmbH, with these open items:

| Invoice   | Amount   | Note        |
|-----------|----------|-------------|
| INV-5001  | 1200.00  |             |
| INV-5002  |  800.00  |             |
| INV-5003  | -150.00  | credit note |
| INV-5004  |  500.00  |             |
| INV-5005  | 2000.00  |             |

Three payments, one of each shape the guard must handle:

* **PAY-9001** — clean multi-invoice match. Pays INV-5001 + INV-5002 minus the
  INV-5003 credit note: 1200 + 800 − 150 = **1850**. Reconciles exactly.
* **PAY-9002** — short / partial. Remittance quotes INV-5005 (2000) but only
  **1500** arrived. Flagged PARTIAL and routed.
* **PAY-9003** — overpayment. Remittance quotes INV-5004 (500) but **650**
  arrived. Flagged OVERPAID and routed.

## What is inside

```
src/cashapp/models.py     the money-safe data models (frozen, Decimal only)
src/cashapp/ledger.py     the fake AR ledger; clears once, never twice
src/cashapp/proposer.py   the "propose" step (rule-based default; LLM optional)
src/cashapp/guard.py      the deterministic guard that decides MATCH / exception
src/cashapp/flow.py       ties the steps together and logs every one
src/cashapp/samples.py    the seeded payments
tests/                    tests that prove each step and the whole flow
run_agent.py              run it end to end
prompts/                  Claude Code prompts to change or extend it
```

## Why the guard, not the AI, decides

The AI reads messy remittance text and proposes a match. That is genuinely
useful and genuinely fallible. So the AI only proposes. The guard is plain
arithmetic on Decimals you can read, test, and trust: it sums the matched
invoices, compares to the payment within tolerance, and refuses anything that
does not reconcile. A wrong proposal is caught there and never clears. Money is
a `Decimal` everywhere, never a float, so cents do not go missing.

## Status

Built and tested. The match-and-check flow runs end to end against the fake AR
ledger. The "propose" step is rule-based by default so it runs offline; an
LLM-backed matcher plugs in behind the same interface via `--matcher llm`.
