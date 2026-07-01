# Pattern 7: Service Resolution Assist with Entitlement Guardrails

## What this pattern does

A service case opens. An agent gathers the context and proposes the next step. It does **not** act by itself. A deterministic guard decides what is allowed, and a human confirms anything that writes.

The shape is **suggest-only**:

1. **Gather** — the agent pulls the asset record, the entitlement/warranty terms, prior incidents, and parts availability from a small fake source.
2. **Propose** — the AI suggests one next step (for example, replace under warranty).
3. **Guard** — a fixed set of rules (not the AI) evaluates the step against the entitlement terms and policy and returns one verdict: **allow**, **needs-approval**, or **deny**, with a short reason.
4. **Route** — read-only recommendations are the default. An in-policy routine action is **staged** for a one-click human confirm. Anything out of policy or over an entitlement limit goes to a **supervisor**.
5. **Confirm** — a human confirms anything that writes. Only then does the action execute.

The rule of the pattern: **the AI only proposes; a deterministic guard decides, and nothing writes until a human confirms.** The entitlement snapshot and the decision are logged in a tamper-evident audit chain.

## The action hierarchy

| Guard verdict | What happens | Who acts |
| --- | --- | --- |
| `allow` | The routine in-policy action is staged for a one-click confirm. | A human confirms, then it executes. |
| `needs-approval` | Nothing is staged. The read-only recommendation stands. | A supervisor must approve. |
| `deny` | Refused outright. No staging, no supervisor write. | Nobody. |

## How to run

Set up the environment once (see [docs/getting-started.md](../../docs/getting-started.md)). Then, from this folder:

```
python run_agent.py                     # CASE-501 in-warranty, you confirm, it executes
python run_agent.py --case CASE-502     # repair at an uncovered site -> needs-approval
python run_agent.py --case CASE-503     # out-of-warranty claim -> deny
python run_agent.py --confirm yes       # auto-confirm the staged action
python run_agent.py --confirm no        # decline; nothing executes
```

No SAP account and no API key are needed. Everything runs in memory, and the proposer is a deterministic stand-in by default. To use a real model, set `OPENROUTER_API_KEY` and pass `--proposer llm`.

Run the tests from the repo root with `pytest`.

## The three sample cases

| Case | Situation | Guard verdict |
| --- | --- | --- |
| `CASE-501` | In-warranty motor failure, part on hand, covered site. | `allow` |
| `CASE-502` | In-warranty repair, but at a site the plan does not cover. | `needs-approval` |
| `CASE-503` | Warranty claim on an asset whose warranty expired. | `deny` |

## What is inside

```
src/service/models.py     the frozen dataclasses (money is Decimal)
src/service/source.py     the small fake source; seeds the three cases
src/service/proposer.py   the "propose" step (deterministic default; swap in an LLM)
src/service/guard.py      the deterministic entitlement guard (allow/needs-approval/deny)
src/service/governed.py   entitlements, confirm-hold, identity, tamper-evident audit
src/service/flow.py       ties the steps together and routes by verdict
src/service/errors.py     boundary errors
tests/                    tests that prove each step and the whole flow
run_agent.py              run it end to end
prompts/                  Claude Code prompts to change or extend it
```

## Status

Built and tested. The suggest-only flow runs end to end against the fake, governed source. The "propose" step is a deterministic stand-in today so it runs offline; an LLM-backed proposer plugs in behind the same interface. The guard is plain, deterministic code, so the verdict never depends on the model.
