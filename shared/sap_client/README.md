# SAP Client Layer

All patterns talk to SAP through this one layer. Never directly.

## The plan

Three parts:

1. **The interface** — one simple contract that says what an agent can ask SAP to do (read a document, stage a posting, confirm a posting).
2. **The fake SAP** (`MockSapClient`) — the default. It pretends to be SAP so examples run for free, with no SAP account.
3. **The control wrapper** (`GovernedSapClient`) — wraps either client and adds the controls a real company needs: check the agent is allowed, hold writes for approval, and log every call.

To use a real SAP system later, you add a real client behind the same interface. Nothing else in the pattern changes.

## What is inside

```
interface.py        the SapClient contract (read / stage / confirm)
models.py           Document, ProposedPosting, StagedPosting, PostingResult
mock_client.py      MockSapClient: the in-memory fake SAP
governed_client.py  GovernedSapClient: entitlements, write-hold, audit log
errors.py           the errors the layer can raise
```

## Status

Built and tested. The interface, the fake client, and the governed wrapper all work and are covered by tests. A real SAP client behind the same interface is a later step.
