# Vendor ROI Methodology

## Core Metrics

### Cost per Lead (CPL)
```
CPL = Vendor Spend / Leads from that Vendor
```
Lower is better. Measures acquisition cost.

### Cost per Sale (CPS)
```
CPS = Vendor Spend / Sales from that Vendor      (shown as "-" when Sales = 0)
```
The primary ROI metric: it carries both volume and quality. Never show infinity, and never put text other than "-" in a number column.

### Close Rate
```
Good Leads = Leads - Duplicates - Invalid
Close Rate = Sales / Good Leads
```
The same definition score-leads uses. Measures lead quality.

## Operational Sources (ask before any ROI math)

Some high-close sources are not marketing. They log buyers who are already in the store.

### Ask Drew about
- Any source over 20% close rate whose name matches `credit|walk|referral|repeat|dms|service|showroom` (the facts check enforces this list).
- Credit applications (showroom walk-ins filling out a credit app; 25-35% close is the tell).
- Phone-up logs that include service calls or existing customers.
- Chat-to-sales handoffs logged when the customer is already with a salesperson.
- Any high-close source with $0 spend.

### How to handle
- Credit applications get their own "Credit App" row at ingestion (`data_ingestion.md`), before the website match.
- Drew decides: keep (set `confirmed_by_drew` on the source in the facts file) or exclude (add it to `definitions.excluded_sources`).
- Excluded sources never appear in Vendor ROI or Reallocation rows; the Vendor ROI note row names them.
- State the exclusion on page one in the lead definition line.

## Efficiency Tiering

Tiers are based on cost per sale. The cut-offs and the $1,500 zero-sale review floor are a **DigitalCLIQ planning assumption**, not a published benchmark; the Methodology note says so.

| Row condition | Tier | Rating | Note | Treatment | Action |
|---|---|---|---|---|---|
| CPS under $500 | TIER 1 | STAR | | Sky Blue fill, white bold text | Invest more |
| CPS $500 to $999 | TIER 2 | GOOD | | Callout Tint fill, Digital Blue text | Maintain or grow |
| CPS $1,000 to $1,499 | TIER 3 | AVG | | No fill | Monitor |
| CPS $1,500 or more | TIER 4 | REVIEW | | Warm Grey fill, white text | Cut or restructure |
| Spend $1,500 or more, leads > 0, 0 sales | TIER 4 | REVIEW | "0 sales on $X" | Warm Grey fill, white text | First on the CUT list |
| Spend under $1,500, leads > 0, 0 sales | NO SALES YET | NO SALES YET | | Warm Grey text | Watch; one sale would still cost under $1,500 |
| Spend > 0, 0 CRM leads | UNMEASURED | UNMEASURED | "No CRM leads" | Warm Grey italic text | Require attribution proof |
| $0 spend in a table where others have spend | NO SPEND | NO SPEND | | Warm Grey text | Not graded on cost |

When no vendor in the table has spend (close-rate-only data), cost tiers are not applied.

### Tier Assignment Logic
The script is the source of truth; run `verify_workbook.py tiers <facts.json>` and copy its Tier, Rating, Note and row order. The logic:
```python
def tier_rule(spend, leads, sales, table_has_cost=True):
    if spend <= 0:
        return 'NO SPEND' if table_has_cost else None
    if leads <= 0:
        return 'UNMEASURED'              # note: No CRM leads
    if sales <= 0:
        return 'TIER 4' if spend >= 1500 else 'NO SALES YET'   # TIER 4 note: 0 sales on $X
    cps = spend / sales
    if cps < 500:  return 'TIER 1'
    if cps < 1000: return 'TIER 2'
    if cps < 1500: return 'TIER 3'
    return 'TIER 4'
```
Rows are sorted by CPS ascending; rows without a CPS go last.

## Reallocation Strategy Rules

1. **Budget neutral**: total proposed spend equals total current spend. The value is in moving money, not adding it.
2. **CUT order**: paid lines with leads and zero sales first (largest spend first), then TIER 4 by CPS (worst first), then UNMEASURED. `verify_workbook.py tiers` prints this order. Reduce, do not eliminate, unless Drew says so.
3. **UNMEASURED**: a vendor that cannot show CRM leads proves attribution or loses budget.
4. **Invest in TIER 1 and 2**: project with each vendor's own CPL and close rate.
5. **Contract minimums**: note them; do not cut below them.
6. **Project conservatively**: existing CPL and close rates, no assumed improvement.

### Impact Projection Formula
```
Additional leads from $X in Vendor A = $X / Vendor A's CPL
Additional sales                     = Additional leads x Vendor A's close rate
Lost leads from $Y cut in Vendor B   = $Y / Vendor B's CPL
Lost sales                           = Lost leads x Vendor B's close rate
Net impact                           = Gains - Losses
```

## Spend Categories

Not all marketing spend produces trackable leads. Classify each budget line:

| Category | Generates Trackable Leads? | Notes |
|---|---|---|
| 3rd-party lead providers | YES | Core lead gen, measurable in CRM |
| PPC / search ads | INDIRECT | Drives website traffic, then website leads |
| Social media ads | INDIRECT | Awareness plus some direct leads |
| Email campaigns | INDIRECT | Nurture and conquest |
| Website platform | INFRASTRUCTURE | Required, does not generate leads by itself |
| Chat tools | YES (small) | Leads from chat |
| Call tracking | INFRASTRUCTURE | Measurement tool |
| TV / radio | BRAND | No direct lead attribution |
| Events / sponsorships | BRAND | Community presence |
| Data / analytics tools | INFRASTRUCTURE | Mastermind, Data Clover, etc. |
| Direct mail | INDIRECT | Some trackable through unique codes |

Lead-generating spend is often only about 25-40% of the total budget (DigitalCLIQ planning assumption, not a published benchmark). The rest supports lead gen but cannot be measured directly in CRM reports.
