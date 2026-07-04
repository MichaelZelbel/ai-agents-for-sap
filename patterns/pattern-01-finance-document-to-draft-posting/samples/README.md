# Sample invoice for the document reader

`sample-hotel-invoice.pdf` is a realistic PDF invoice you can feed to the agent's
document reader from Chapter 8:

```
python ../run_agent.py --invoice-file samples/sample-hotel-invoice.pdf
```

A vision model reads the PDF and returns the fields the agent posts (vendor,
currency, net, tax, gross, date). It is a hotel bill with mixed VAT rates (7% on
the room and tourism levy, 19% on breakfast), so it exercises the messy-invoice
path, not just a clean one.

The billed company (Nordwind Fertigung GmbH), the tax number, the bank account,
the invoice number, and the date are all fictional demo values. You need no SAP
account and no real data to run it.
