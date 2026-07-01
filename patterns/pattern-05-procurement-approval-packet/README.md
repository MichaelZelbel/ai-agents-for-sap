# Pattern 5: Policy-Aware Procurement Approval Packet

## What this pattern does

A purchase requisition arrives thin. An agent assembles an approval **packet**: the supplier profile, the applicable policy citation **with its version**, risk flags, and a recommended path. It does **not** change the requisition record.

The flow has five steps:

1. **Enrich** — pull the supplier profile and the policy for this request.
2. **Draft** — the AI writes a risk narrative and a recommendation. Advisory only.
3. **Guard** — a fixed set of rules (not the AI) sets the route.
4. **Stage** — the packet is staged as the primary artifact. The record is untouched.
5. **Decide** — a human approver reads the packet and signs off, or it escalates.

The rule of the pattern: **the AI drafts, the deterministic guard decides, and a human approves.** The packet is staged; it never rewrites the request.

The guard checks three things, straight from the policy:

- Required documentation is present (software and services need a contract).
- The amount against the manager spend threshold.
- Segregation of duties: the requester must not be the named approver.

High-risk or policy-deviation cases route to escalation. A missing required document blocks the packet: it cannot be approved until the document is supplied. The decision and the policy version are logged.

## How to run

Set up the environment once (see [docs/getting-started.md](../../docs/getting-started.md)). Then, from this folder:

```
python run_agent.py                        # clean, in-policy request (REQ-2001)
python run_agent.py --request REQ-2002      # missing contract, over the threshold
python run_agent.py --request REQ-2003      # segregation-of-duties violation
python run_agent.py --request REQ-2001 --approve   # record an approval
```

No SAP account and no API key are needed. The narrative is drafted offline by a deterministic stand-in by default. To use a real model, pass `--narrator llm` with `OPENROUTER_API_KEY` set.

Run the tests from the repo root with `pytest`.

## What is inside

```
src/procurement/models.py     the frozen dataclasses (Decimal money)
src/procurement/data.py       the seeded sample requisitions, suppliers, policy
src/procurement/narrator.py   the "draft" step (rule-based; swap in an LLM)
src/procurement/guard.py      the fixed rules that set the route
src/procurement/log.py        a hash-chained, tamper-evident audit log
src/procurement/flow.py       assembles the packet and records the decision
tests/                        tests that prove the guard and the whole flow
run_agent.py                  run it end to end
prompts/                      Claude Code prompts to change or extend it
```

The shared fake/governed SAP layer lives in [shared/sap_client/](../../shared/sap_client/). This pattern stages a packet rather than posting to SAP, so it keeps its own small audit log built on the same hash-chain idea.

## Status

Built and tested. The five-step flow runs end to end on seeded data. The "draft" step is rule-based today so it runs offline; an LLM-backed narrator plugs in behind the same interface, and the deterministic guard decides the route regardless of what the model drafts.
