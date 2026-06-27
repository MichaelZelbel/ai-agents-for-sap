# AI Agents for SAP — Book Code

Companion code for the book **AI Agents for SAP**.

This repo holds ready-to-run examples of the agent patterns from the book. You clone it, run an example, and change it with Claude Code.

## How the examples run

The examples talk to a **fake SAP system** that lives inside this repo. You do **not** need a real SAP account to run them.

This is on purpose. In a real company, an agent does not connect straight to SAP. It goes through one controlled layer that checks what the agent is allowed to do, holds writes for approval, and logs every call. This repo copies that shape, so what you build here looks like how it is really done.

If you later have a real SAP tenant, you swap the fake SAP layer for a real one. The rest of the example stays the same.

## What is inside

```
patterns/   one folder per pattern from the book (code, tests, prompts)
shared/     the SAP client layer shared by all patterns (fake + governed)
docs/       setup and how-to-run notes
```

## Getting started

See [docs/getting-started.md](docs/getting-started.md).

## Status

Work in progress. Each example is built and run end to end before it is marked done. If it is in here and marked ready, it works.

## License

Private for now. A license will be added before this repo is shared with readers.
