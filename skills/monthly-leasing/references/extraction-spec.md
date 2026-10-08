## What to Extract (LEASE ONLY)

| Field | Description | Example |
|-------|-------------|---------|
| yr | Model year | 2025 |
| make | Brand | Nissan |
| model | Model name from dictionary | Rogue |
| trim | Trim level if visible | SV, S, xDrive30i |
| msrp | MSRP if shown | 32500 |
| pmt | Monthly payment | 299 |
| term_mo | Lease term months | 36 |
| das | Due at signing | 3999 |
| miles_yr | Annual mileage | 10000 |
| sec_dep | Security deposit | waived |
| exp | Expiration date | 3/3/2025 |
| vin | VIN if shown | |
| disclaimer_text | Full disclaimer text | |

**Exclude:** Used vehicles, service coupons, finance-only offers, APR-only offers. If a tile has both finance and lease, extract only the lease portion.

## Info Flags (Scan Disclaimers)

Scan each disclaimer for these keywords and record as pipe-delimited flags:
- `LOYALTY`: mentions loyalty
- `CONQUEST`: mentions conquest
- `ACQ_FEE`: acquisition fee
- `TTL`: tax, title, license
- `MSD`: multiple security deposits
- `TRADE_REQ`: trade required
- `APR_CREDIT`: on approved credit / tiered credit
- `DEALER_CONTRIB`: dealer contribution
- `DAS_EXCL_FEE`: the due-at-signing figure is stated as plus or excluding a doc, processing, or dealer fee (FTC FAQ Q8: upfront fees belong inside the advertised due-at-signing total; added 2026-10-08)
- `ZERO_DAS_FEE`: "$0 due at signing" or "nothing due at signing" while the disclaimer lists any fee due at signing (FTC FAQ Q8)
- `COND_INSIDE`: the payment or price already reflects a finance-conditioned, loyalty, conquest, military, or first-responder discount rather than showing it separately (FTC FAQ Q5, Q9)
- `IN_TRANSIT`: the offer unit is described as in transit, arriving soon, or in production (FTC FAQ Q10; FTC staff remarks 2026-09-30: in transit means already shipped)

The four FTC flags are competitive-intelligence signals, not legal findings: for a DigitalCLIQ client's own offer, surface them to Drew in the Step 4 message so they can be routed to `/brand-check`; for a competitor they are context only. Source: `Resources/automotive-guidelines/ftc-advertising-compliance.md`.

Example: `LOYALTY|ACQ_FEE|TTL|DAS_EXCL_FEE`
