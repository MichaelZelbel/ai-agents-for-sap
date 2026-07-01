# Pattern 9: Sales Order Proposal from a Customer Request

## What this pattern does

A customer request arrives as free text, for example:

> "send me 200 of the usual brackets and 20 of the new clamps, need them by month end"

An agent reads the text and proposes a draft sales order. It does **not** release
anything to fulfillment by itself.

The flow has these steps:

1. **Extract** — the AI reads the free text and pulls out products, quantities, and terms.
2. **Price** — deterministic code turns the extracted intent into a priced draft order.
3. **Guard** — a fixed set of rules (not the AI) decides if the draft is in policy.
4. **Approve** — a human sales manager says yes or no.
5. **Release** — only after a yes, the order is released to fulfillment.

The rule of the pattern: **nothing is released until a human approves.**

The AI only extracts intent. Pricing, the policy check, approval, and release are
deterministic or human. So a wrong extraction cannot release a bad order.

## What the guard checks

The guard flags an order that breaks any of these rules:

- The customer must exist and be within credit. A new customer with no credit record is flagged.
- Every product must be valid and in stock.
- Any discount must be within the customer's authority.
- The order value must be within threshold.
- A restricted product is flagged for clearance.
- An unusual ship-to country is flagged for review.

## How to run

Set up the environment once (see the repo's getting-started docs). Then, from this folder:

```
python run_agent.py --request REQ-1            # a known customer, clean and in stock
python run_agent.py --request REQ-1 --approve  # the guard passes; the manager approves; it releases
python run_agent.py --request REQ-2            # a new customer over threshold; flagged
python run_agent.py --request REQ-3            # a known customer, but short on stock; flagged
```

No SAP account and no API key are needed. The default proposer is deterministic and
runs offline. Pass `--proposer llm` to use a real model via OpenRouter (set
`OPENROUTER_API_KEY` first).

Run the tests from the repo root with `pytest`.

## What is inside

```
src/salesorder/data.py             sample customers, products, and requests
src/salesorder/models.py           frozen dataclasses; money is Decimal, never float
src/salesorder/proposer.py         the "extract" step (deterministic; swap in an LLM)
src/salesorder/guard.py            the fixed rules that pass or flag a draft order
src/salesorder/mock_client.py      the in-memory sales system
src/salesorder/governed_client.py  entitlements, release-hold, identity, tamper-evident audit
src/salesorder/flow.py             ties the steps together
tests/                             tests that prove each step and the whole flow
run_agent.py                       run it end to end
prompts/                           Claude Code prompts to change or extend it
```

## Status

Built and tested. The flow runs end to end against the fake, governed sales system.
The "extract" step is deterministic today so it runs offline; an LLM-backed proposer
plugs in behind the same interface.
