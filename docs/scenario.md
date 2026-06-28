# The running scenario — Nordwind Fertigung GmbH

The book follows one fictional company so every example builds on the last.

**Nordwind Fertigung GmbH** is a mid-sized German manufacturer. Its accounts-payable (AP) team is
buried in incoming vendor invoices. Each invoice has to be read, matched to the right accounts, and
posted to SAP — by hand, one at a time. That is slow, repetitive, and error-prone. It is the perfect
first job for an agent.

Nordwind is the **buyer** (the company running the agent). The invoices come **from vendors** (for
example "Office Supplies Co", "Cloud Hosting Ltd") **to** Nordwind.

## The seeded data

For now the example invoices live in code, in
[`shared/sap_client/mock_client.py`](../shared/sap_client/mock_client.py) (`_seed_documents`):

| Document | Vendor | Net | Tax | Gross | Currency |
|---|---|---|---|---|---|
| INV-1001 | Office Supplies Co | 1000.00 | 190.00 | 1190.00 | EUR |
| INV-1002 | Cloud Hosting Ltd | 500.00 | 95.00 | 595.00 | EUR |

As later patterns are added (three-way match, dispute resolution), the shared scenario data grows —
purchase orders, goods receipts, and dispute cases — and moves into a `data/` folder so all patterns
draw from one consistent Nordwind world.

## Why a fake SAP

So you can run everything for free, with no SAP account, while still seeing the real shape: an agent
proposes, deterministic rules check it, a human approves, and only then does anything get written —
through a governed layer that logs every call. Swap the fake SAP for a real one later and the agent
code does not change.
