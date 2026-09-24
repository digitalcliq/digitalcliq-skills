# Vendor ROI Methodology

## Core Metrics

### Cost per Lead (CPL)
```
CPL = Annual Vendor Spend / Total Leads from that Vendor
```
Lower is better. Measures acquisition efficiency.

### Cost per Sale (CPS)
```
CPS = Annual Vendor Spend / Total Sales from that Vendor
```
The primary ROI metric. Accounts for both volume AND quality of leads.

### Close Rate
```
Close Rate = Total Sales / Total Leads
```
Measures lead quality. High close rate = high-intent buyers.

## Operational Artifact Exclusions

Some high-close-rate lead sources are NOT marketing-generated. They are operational processes that log already-decided buyers into the CRM system. These MUST be excluded from marketing ROI calculations.

### Common Artifacts to Ask About:
1. **Credit Applications** — Showroom walk-ins who fill out a credit app. They're already at the dealership, likely already buying. Close rates of 25-35% are a dead giveaway.
2. **Phone-Up Logs** — Some CRMs log inbound phone calls as "leads" even though they may be service calls or existing customers.
3. **Chat-to-Sales Handoffs** — If the chat tool logs a "lead" when transferring to a salesperson who already has the customer in front of them.

### How to Identify Artifacts:
- Close rate > 20% on any single source is suspicious — ask the user
- Provider names containing "Credit", "Application", "Walk-In", "Showroom" are likely artifacts
- If a source has high close rate but $0 spend, it's definitely not marketing-sourced

### How to Handle:
- Split the parent vendor into two: marketing-sourced and artifact
- Attribute $0 marketing spend to the artifact
- Only include marketing-sourced leads in ROI calculations
- Note the exclusion clearly in the report

## Efficiency Tiering

Tiers are based on Cost per Sale (CPS), the metric that best reflects true ROI:

| Tier | CPS Range | Label | Color | Action |
|------|-----------|-------|-------|--------|
| TIER 1 | < $500 | ★★★ STAR | Green | Invest more |
| TIER 2 | $500–$999 | ★★ GOOD | Light blue | Maintain or grow |
| TIER 3 | $1,000–$1,499 | ★ AVG | Default | Monitor |
| TIER 4 | ≥ $1,500 | ⚠ REVIEW | Red | Cut or restructure |
| UNMEASURED | No CRM leads | ? UNMEASURED | Orange | Require attribution proof |

### Tier Assignment Logic
```python
def assign_tier(cps):
    if pd.isna(cps) or cps == 0:
        return 'UNMEASURED'
    elif cps < 500:
        return 'TIER 1'
    elif cps < 1000:
        return 'TIER 2'
    elif cps < 1500:
        return 'TIER 3'
    else:
        return 'TIER 4'
```

## Reallocation Strategy Rules

1. **Budget Neutral**: Total proposed spend must equal total current spend. The value is in MOVING money, not adding money.
2. **Cut from Tier 4 first**: These have the worst ROI. Don't eliminate — reduce.
3. **Cut from UNMEASURED second**: If a vendor can't prove leads in CRM, they should prove it or lose budget.
4. **Invest in Tier 1/2**: Use vendor-specific CPL to project additional leads from reinvestment.
5. **Don't touch contractual minimums**: Some vendors have minimum spend requirements. Note these.
6. **Project impact conservatively**: Use existing CPL/close rates, don't assume improvement.

### Impact Projection Formula
```
Additional leads from $X investment in Vendor A = $X / Vendor A's CPL
Additional sales = Additional leads × Vendor A's close rate
Lost leads from $Y cut to Vendor B = $Y / Vendor B's CPL
Lost sales = Lost leads × Vendor B's close rate
Net impact = Gains - Losses
```

## Spend Categories

Not all marketing spend generates trackable leads. Classify each budget line:

| Category | Generates Trackable Leads? | Notes |
|---|---|---|
| 3rd-party lead providers | YES | Core lead gen — measurable in CRM |
| PPC / Search ads | INDIRECT | Drives website traffic → website leads |
| Social media ads | INDIRECT | Brand awareness + some direct leads |
| Email campaigns | INDIRECT | Nurture existing + conquest |
| Website platform | INFRASTRUCTURE | Required but doesn't "generate" leads |
| Chat tools | YES (small) | Leads from chat interactions |
| Call tracking | INFRASTRUCTURE | Measurement tool, not lead gen |
| TV/Radio | BRAND | No direct lead attribution |
| Events/Sponsorships | BRAND | Community presence, long-term |
| Data/Analytics tools | INFRASTRUCTURE | Mastermind, Data Clover, etc. |
| Direct mail | INDIRECT | Some trackable via unique codes |

The lead-generating spend (YES category) is typically only 25-40% of total marketing budget. This is normal for dealerships. The rest is infrastructure, brand, and indirect channels that support lead gen but can't be directly measured in CRM reports.
