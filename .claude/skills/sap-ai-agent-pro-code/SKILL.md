---
name: sap-ai-agent-pro-code
description: Build an SAP AI agent the pro-code, governed way — a model proposes, deterministic rules guard, a human approves, then it writes. Use when building or extending a Python SAP agent, adding or reworking a pattern in the AI-Agents-for-SAP repo, or scaffolding a propose-then-guard agent against a real or stand-in SAP. The companion skill to the book "AI Agents for SAP" (patterns 1 to 10).
---

# Build an SAP AI agent (pro-code)

This skill builds SAP AI agents the way the book *AI Agents for SAP* does: a small, governed Python agent where **the AI proposes, deterministic rules decide, a human approves, and only then does it write.** It matches the companion repo `github.com/MichaelZelbel/ai-agents-for-sap` (patterns 1 to 10). Reuse its shapes and conventions; do not reinvent them.

The one rule under everything: **never let the model's output be the final word on an action.** The model proposes. A deterministic guard that cannot be talked into anything checks the result. A human approves real writes. This is what makes an AI agent safe to point at a system of record.

House-style note: this skill shapes *how* an agent is built (the pattern, the conventions, the tests), not *what* the answer is. When the reader is building their own version of a pattern for learning, build fresh from the spec in front of you; the finished `patterns/` folder is only for comparison afterward.

## Step 1: pick the shape

Almost every job is one of four shapes. Identify it first, then build from the matching shape. All ten catalog patterns are instances of these four.

1. **Propose and post** (e.g. Pattern 1 finance posting, Pattern 9 sales order). Read a document, the AI proposes a write, a validator checks it, a human approves, it writes. Use when the job creates or changes a record.
2. **Classify and route** (e.g. Pattern 2 document triage). The AI picks a known category, firm rules route it and refuse any unknown label. Use when the job decides which path something takes.
3. **Match and check** (e.g. Pattern 3 three-way match, Pattern 8 cash application). The AI matches records worded differently, firm rules confirm the numbers agree. Use when records must agree before proceeding.
4. **Suggest only** (e.g. Pattern 4 dispute assistant, Pattern 10 expense audit). The AI reads and drafts, a human acts. The agent takes no action itself (`action_taken=False`). Use for words-and-judgement jobs.

## Step 2: set the autonomy by the risk

Match the freedom to the danger. A words-and-judgement job earns **suggest-only**. A job that changes a record earns a **deterministic guard plus a human approval** before any write. Start low; widen only on evidence (low override rate, clean audit, controls holding).

## Step 3: build the parts (reuse these shapes)

Money is always `Decimal`, never float. Frozen dataclasses for the models. Zero runtime dependencies: the model call uses stdlib `urllib`. Every external call is injectable so tests run offline.

**The proposer (the AI's job).** Behind a `Proposer` Protocol. An LLM-backed proposer calls OpenRouter (OpenAI-compatible chat completions), reads `OPENROUTER_API_KEY` from the environment, default model `openai/gpt-4o-mini`, and parses the model's JSON into typed objects with structural checks only (the business rules are the guard's job). Accept an injectable `complete: Callable[[str], str]` so tests pass a fake reply and need no key or network. Ship a deterministic rule-based proposer too, so the flow runs offline.

**Determination (deterministic, not the model's guess).** Values that a real ERP determines by configuration — the tax code, the cost center — are set by a small deterministic step between propose and validate, not guessed by the AI. Read the tax code off the invoice's own rate; assign a default active cost center. Then the guard checks them against master data. This keeps the codes as trustworthy as the balance check and works for both the rule and LLM proposers.

**The validator / deterministic guard (the decision).** Pure Python rules, returns a result with `status` ("PASS"/"FAIL") and a list of machine-readable `reasons`. It never calls the model and gives the same answer every time. It checks the proposal against the source and against master data. A full guard checks, as applicable:
- the posting balances (debits == credits within a small `Decimal` tolerance) and the total matches the document gross;
- accounts are on the allowed list; amounts are positive; the date and ids are present and consistent;
- the **vendor is in the Business Partner master** (else refuse: "Vendor not in master data");
- the **tax code is known and its rate matches** the invoice's actual net/tax rate;
- the **cost center exists and is active**;
- for a document read from a scan, the **reading confidence** is above a threshold (else hold for a human);
- for match-and-check: quantities and money agree across all documents; for classify-and-route: the category is one of the known set.

**Master data on the stand-in SAP.** `MockSapClient` seeds not just documents but a vendor master (`known_vendors`, `add_business_partner`), valid tax codes with rates (`known_tax_codes`), and active cost centers (`active_cost_centers`). Master-data changes (onboarding a vendor) are a separate capability from posting — segregation of duties.

**The governed boundary.** `GovernedSapClient` wraps any `SapClient` and enforces four controls:
- **Entitlements** (least privilege): only granted operations run; others are refused and logged.
- **Write-hold**: `confirm` is blocked until a human `record_approval`.
- **Propagated identity**: every audit entry is stamped with the agent's `actor` (principal).
- **Tamper-evident audit**: entries are hash-chained; `verify_audit()` recomputes the chain and returns False if any past entry changed.

**The SAP client.** A `SapClient` Protocol with `read_document`, `stage_posting`, `confirm_posting`. `MockSapClient` is the in-memory stand-in for free, offline runs. `S4SapClient` is the real one: same interface, with the actual OData calls behind an injectable `transport` (testable without a tenant; the tenant-specific mapping lives in one place). A real `confirm` books a real journal entry and needs a licensed S/4HANA.

**The flow.** `read -> propose -> determine -> validate -> (if PASS) stage -> human approve -> confirm`. If the validator fails, the human is never asked. If the human says no, nothing is written.

## Step 4: read a real document (optional)

To go from typed fields to a real invoice, add a document reader: one call to a vision-capable model via OpenRouter that returns the fields as JSON, with a `confidence`. Report the numbers as printed (never "fix" them; the guard catches a broken invoice). For a PDF, include OpenRouter's file-parser plugin (`{"id":"file-parser","pdf":{"engine":"pdf-text"}}`) so the PDF actually reaches the model. Keep it injectable for offline tests. If the model cannot read the file, it returns an error rather than guessing.

## Step 5: tests first, and run them

Tests inject a fake `complete` (and a fake `transport` for the real client), so the whole suite runs offline with no API key. Always include:
- the validator refuses each bad case (unbalanced, wrong currency, forbidden account, total mismatch, unknown category, quantities disagree, vendor not in master, invalid/mismatched tax code, inactive cost center, low confidence);
- a *wrong* model proposal is caught by the validator (a successful prompt injection still fails the guard);
- no write without approval, and a human rejection writes nothing;
- entitlements refuse and log out-of-scope calls;
- the audit chain verifies, and tampering is detected;
- onboarding an unknown vendor then posting succeeds;
- (capstone) the whole flow runs through `S4SapClient` with a faked transport.

Run `pytest` from the repo root and keep it green. Then verify one real run with a key set, and show the real output.

## Step 6: run it end to end

Each pattern ships a `run_agent.py` with these conventions: `--doc <id>` (a seeded document), `--invoice-file <path>` (a JSON of fields, or a PDF/image the reader extracts), `--approve ask|yes|no` (human decision; `ask` prompts interactively), `--proposer rule|llm`, `--model`, and where they apply `--auto-onboard` (add an unknown vendor to the master before posting, the automated master-data step), `--cost-center`, `--min-confidence`. It loads `OPENROUTER_API_KEY` from a `.env` file next to it (see traps). It prints the document, the proposal, the guard verdict, the outcome, and the audit trail.

## Optional: give it a face

A shared operator console (`console/`) fits any pattern, because they share the propose -> guard -> approve -> log shape. Each pattern implements a small adapter (`inbox`, `detail`, `act`) that returns a neutral contract (an inbox, and a detail with a proposal, a verdict, actions, and a trail); one static page renders any of them. Add an adapter to put a new pattern behind the same console.

## Conventions and traps

- Secrets come from a **`.env` file** next to `run_agent.py`, read into the environment at startup (a session `export`/`$env:` does not persist and a freshly spawned shell never inherits it). `.env` is git-ignored. Never hard-code or commit a key; leak-check before any commit.
- Free OpenRouter models (`...:free`) are heavily rate-limited (429); a cheap model like `openai/gpt-4o-mini` is a fraction of a cent per call and reliable.
- The model can be wrong or hostile. The guard makes that harmless: it checks the *result* against the source and master data, not against anything the model said. That is the prompt-injection defense.
- Onboarding a vendor (`--auto-onboard`) crosses a segregation-of-duties line: creating a Business Partner is a different role from posting to it. Convenient for testing; in production it is gated.
- Keep each pattern self-contained under `patterns/pattern-NN-name/src` with its own tests; add its `src` to `pyproject.toml` `pythonpath`, and use `--import-mode=importlib` so duplicate test-file names across patterns do not collide.

## Reference

Matches `github.com/MichaelZelbel/ai-agents-for-sap`: patterns 1 to 10 (finance posting, document triage, three-way match, dispute assistant, procurement packet, close orchestration, service resolution, cash application, sales order, expense audit), each self-contained, plus `shared/sap_client/` holding the interface, models, mock (with master data), governed wrapper, real client, and the document reader (`extract`), and a shared operator `console/`. To swap the model to SAP's Generative AI Hub, replace the proposer's model call behind the same `Proposer` interface; everything downstream is unchanged.
