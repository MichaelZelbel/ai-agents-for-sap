# Chapter map — what to run for each chapter

This maps the book's chapters to what you run in this repo. Browser-only chapters (the low-code Joule
work) have no code here — you do them in SAP. Code chapters point to a folder you run.

Status: ✅ ready · 🔜 coming (built before its chapter is written).

| Ch | Title (short) | In this repo | Status |
|----|---------------|--------------|--------|
| 1 | Your first SAP agent | — (browser: SAP AI Launchpad) | n/a |
| 2 | Why agents on SAP are different | — (reading) | n/a |
| 3 | The two ways to build | — (reading) | n/a |
| 4 | Build a Joule AI assistant | — (browser: Joule Studio) | n/a |
| 5 | Ground it on your content | — (browser: Joule Studio) | n/a |
| 6 | Give it a real SAP skill | — (browser: Joule Studio) | n/a |
| 7 | Where low-code stops | — (reading) | n/a |
| 8 | Set up Claude Code | — (your machine) | n/a |
| 9 | Build the invoice-posting agent | `patterns/pattern-01-finance-document-to-draft-posting/` (`run_demo.py`) | ✅ (model wiring 🔜) |
| 10 | The leash on your AI (governed boundary) | `shared/sap_client/governed_client.py` | ✅ |
| 11 | From a diagram to a working agent | `diagrams/` + the diagram→agent prompt | 🔜 |
| 12 | Extend it: three-way match | `patterns/pattern-02-three-way-match/` | 🔜 |
| 13 | Build from scratch: dispute copilot | `patterns/pattern-03-dispute-resolution/` | 🔜 |
| 14 | Make it safe (security/governance) | `shared/sap_client/` (read against) | ✅ |
| 15 | Capstone — prototype to a real tenant | swap notes + `shared/sap_client/` real client | 🔜 |
| 16 | What to measure | tests + metrics notes | 🔜 |
| 17 | Find your next opportunity | — (method) | n/a |
| 18 | The future | — (reading) | n/a |

Run anything with the steps in [getting-started.md](getting-started.md). The running example
(Nordwind) is described in [scenario.md](scenario.md).
