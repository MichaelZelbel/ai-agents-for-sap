# Nordwind Production (S/4HANA, on-prem): landscape brief

This is your analyzed SAP landscape. When you answer questions or build for it, use only the objects, processes, and interfaces named here. Do not invent names; if something you need is not here, say so instead of guessing.

## Profile

- Product: SAP S/4HANA 2023, on-prem
- Modules in use: FI, CO, MM
- Modules not in use: EWM, TM, PP
- Finance-heavy landscape; accounts payable is the custom hot spot.

## Custom objects

- **ZEI_INVOICE_POST** (enhancement, package ZFI_TAX): Implicit enhancement on invoice posting; injects the bespoke tax rule. [clean core Level D, ~900/mo, owner Tax team]. Depends on: Z_TAX_DETERMINE_NW.
- **ZFI_TRIAGE_PROG** (program, package ZFI_AP): The program behind the triage cockpit; classifies and routes documents. [clean core Level B, ~3200/mo, owner AP lead]. Depends on: ZTHREEWAY_TOL, BKPF.
- **ZZ_APPROVAL_LANE** (custom_field, package ZFI_AP): Approval-lane classification stamped on the invoice header. [clean core Level B, usage n/a, owner AP lead]. Depends on: BKPF.
- **Z_TAX_DETERMINE_NW** (function_module, package ZFI_TAX): Bespoke tax code determination for a legacy vendor group. [clean core Level B, ~900/mo, owner Tax team]. Depends on: ZTAX_RULES, T007A. Standard alternative: Standard tax determination via the condition technique / tax codes.
- **Z_I_OPEN_AP_ITEMS** (cds_view, package ZFI_AP): Analytical view of open accounts-payable items with aging buckets. [clean core Level A, ~15000/mo, owner Controlling]. Depends on: BSIK, LFA1.
- **ZCL_DISPUTE_ROUTER** (class, package ZFI_AP): Bespoke routing logic for vendor disputes. [clean core n/a, ~3/mo, owner (unowned)]. Depends on: ZTHREEWAY_TOL. Standard alternative: SAP Dispute Management (FSCM) covers most of this.
- **ZFI_TRIAGE** (transaction, package ZFI_AP): AP triage cockpit: route an incoming document to the right desk. [clean core n/a, ~3200/mo, owner AP lead]. Depends on: ZFI_TRIAGE_PROG. Standard alternative: Standard workflow inbox or a Joule triage agent before extending this.
- **ZTAX_RULES** (table, package ZFI_TAX): Custom tax-rule lookup for the legacy vendor group. [clean core n/a, ~900/mo, owner Tax team].
- **ZTHREEWAY_TOL** (table, package ZFI_AP): Per-vendor three-way-match tolerances (quantity and price). [clean core n/a, ~4100/mo, owner AP lead]. Depends on: LFA1. Standard alternative: MM tolerance keys (transaction OMR6) may already cover this.

## Business processes

- **Accounts payable invoice-to-pay** (P2P): ~3200/mo, high manual effort. Deviation: custom triage cockpit and per-vendor tolerance table. Objects: ZFI_TRIAGE, ZFI_TRIAGE_PROG, ZTHREEWAY_TOL, Z_TAX_DETERMINE_NW.
- **Three-way match** (P2P): ~2100/mo, medium manual effort. Deviation: custom tolerance keys instead of standard OMR6. Objects: ZTHREEWAY_TOL.
- **Vendor dispute handling** (P2P): ~40/mo, high manual effort. Deviation: bespoke routing class instead of SAP Dispute Management. Objects: ZCL_DISPUTE_ROUTER.

## Interfaces

- **Bank statement import** (IDoc, inbound) to Hausbank, criticality high.
- **Supplier portal invoices** (OData, inbound) to Supplier portal, criticality medium. Depends on: ZFI_TRIAGE_PROG.
