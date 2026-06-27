# SAP Client Layer

All patterns talk to SAP through this one layer. Never directly.

## The plan

Three parts:

1. **The interface** — one simple contract that says what an agent can ask SAP to do (read a document, stage a posting, confirm a posting).
2. **The fake SAP** (`MockSapClient`) — the default. It pretends to be SAP so examples run for free, with no SAP account.
3. **The control wrapper** (`GovernedSapClient`) — wraps either client and adds the controls a real company needs: check the agent is allowed, hold writes for approval, and log every call.

To use a real SAP system later, you add a real client behind the same interface. Nothing else in the pattern changes.

## Status

Not built yet. Built and tested in Phase 1.
