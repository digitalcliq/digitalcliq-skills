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

Example: `LOYALTY|ACQ_FEE|TTL`
