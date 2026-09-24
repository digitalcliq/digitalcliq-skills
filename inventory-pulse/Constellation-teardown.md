---
type: reference
date: 2026-08-06
status: active
tags: [inventory-pulse, competitive-intelligence, constellation, reverse-engineering]
---

Teardown of the Constellation "On-Brand Inventory Report" PDF that [[New Century BMW]] receives (sample: `New Century BMW_OB_2026-08-04.pdf`, 8 pages, rendered HTML-to-PDF via headless Chrome). [[Drew Moon]] liked the product and had it rebuilt as **DigitalCLIQ Inventory Pulse** (skill: `.claude/skills/inventory-pulse/`) to sell to other clients. NCBMW is deliberately excluded: they already get this from the vendor.

## What the vendor report contains

1. **Cover + pricing summary**: filter chips (OEM, models, status, radius), 5 computed insight bullets, competitive set with distances.
2. **Lease offers, this month vs last month**: per dealer/model/trim, first-seen date, $/mo with green-to-red heat by rank, change chips (no change / new this month / up $272), full terms, side-by-side prior month. Client rows highlighted. Unparseable fields shown as `$?`.
3. **Finance offers**: same treatment on APR/term/MSRP.
4. **MSRP by popularity, 120 days**: delisted units by year/make/model/trim/MSRP with avg days on market. Requires longitudinal VIN tracking.
5. **Minimum MSRP matrix**: model/trim rows x dealer columns, min in-stock price, count at min, age range, rank shaded.
6. **Per-VIN table**: MSRP, advertised price, disc/markup, DOM, dealer.

## Key architecture insight

Sections 2-4 are impossible from a one-shot crawl: they need a persistent snapshot store (first-seen registry, VIN diffing for delistings and DOM). Inventory Pulse builds that store from day one (date-keyed snapshots per the compliance-audit lesson); the movement view carries a "data logging began" note until 120 days of history exist. Twice-monthly runs (5th anchor, 20th pulse) mature the data 2x faster than monthly.

## DigitalCLIQ deviations from the vendor product

- Output is a branded Google Sheet in the client's [[Google Drive]] folder, not a PDF.
- Rankings use **effective monthly cost** ((DAS + remaining payments) / term), not the advertised teaser payment. Defeats down-payment games.
- CDJR honesty layer: Call-for-Price counted as a finding, conditional (stacked-rebate) payments labeled, sub-10k mileage teasers flagged.
- Rank shading uses the [[Design-System]] palette (Sky Blue = low, Warm Grey = high) with ranks also in text, never the vendor's green-to-red rainbow (banned by the design system).
- Model year resolved dynamically from live inventory (2026/2027 changeover safe).

Clients and competitive sets are hardcoded in `config/clients.json`: [[Sterling BMW]] vs Crevier/Irvine/Long Beach BMW; [[McPeek Chrysler Dodge RAM of Anaheim|McPeek's CDJR]] vs Orange Coast/Huntington Beach/Puente Hills; [[Nissan of Irvine]] vs Tustin/Costa Mesa/Orange. Drew set these 2026-08-06.
