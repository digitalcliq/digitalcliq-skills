---
name: performance-report
description: Build a marketing performance report with key metrics, trend analysis, wins and misses, and prioritized optimization recommendations. Use when wrapping a campaign, when preparing weekly, monthly, or quarterly channel summaries for stakeholders, or when you need data translated into an executive summary with next-period priorities.
---

<!-- Local vault copy is canonical for DigitalCLIQ; marketing-plugin ships an identical base version. Customize here. -->

# Performance Report

> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](../../CONNECTORS.md).

Generate a marketing performance report with key metrics, trend analysis, insights, and optimization recommendations.

## Trigger

User runs `/performance-report` or asks for a marketing report, performance analysis, campaign results, or metrics summary.

## Inputs

1. **Report type** -- determine which type of report the user needs:
   - **Campaign report** -- performance of a specific campaign
   - **Channel report** -- performance across a specific channel (email, social, paid, SEO, etc.)
   - **Content performance** -- how content pieces are performing
   - **Overall marketing report** -- cross-channel summary (weekly, monthly, quarterly)
   - **Custom** -- user-defined scope

2. **Time period** -- the reporting window (last week, last month, last quarter, custom date range)

3. **Data source**:
   - If marketing analytics is connected, discover what accounts and platforms are available, then pull performance data automatically
   - If not connected: ask the user to provide metrics. Prompt with: "Please paste or share your performance data. I can work with spreadsheets, CSV data, dashboard screenshots described in text, or just the key numbers."

4. **Comparison period** (optional) -- prior period or year-over-year for trend context

5. **Stakeholder audience** (optional) -- who will read this report (executive summary style vs. detailed analyst view)

---

## Anomaly Investigation Loop

This is the most important upgrade to standard reporting. Do not simply note that a metric is up or down -- investigate WHY before writing conclusions.

After pulling all metrics, scan for anomalies: any metric that is outside its normal range (>15% deviation from the prior period trend, or significantly off target).

For each anomaly found:

```
Step 1: Identify the anomaly
  "Leads dropped 22% in May vs. April"

Step 2: Narrow the scope
  Pull additional data to isolate WHERE the drop occurred:
  - Which channel contributed most to the drop?
  - Which specific campaign, ad set, or content piece?
  - Which date range within the period?

Step 3: Find the cause
  Look for correlated events:
  - Budget changes on that date?
  - Creative rotation or ad fatigue?
  - Algorithm changes or platform issues?
  - Competitor activity spike?
  - Seasonal pattern consistent with prior years?

Step 4: Classify the cause
  - Operational (something we did or stopped doing)
  - External (platform, market, seasonality)
  - Data issue (tracking gap, attribution change)

Step 5: Document in the report with cause, not just symptom
```

Example of the difference:
- Without loop: "Leads dropped 22% in May."
- With loop: "Leads dropped 22% in May, concentrated in Cars.com (down 61%). Traced to a budget cap that fired on May 14th after the campaign overspent in the first two weeks. The broader market showed normal volume -- this was fully operational."

Run this loop for any metric that is >15% off prior period or >10% off target. Surface anomalies with their root cause in the report, not just as flagged numbers.

---

## Report Structure

### 1. Executive Summary
- 2-3 sentence overview of performance in the period
- Headline metric with trend direction (up/down/flat vs. prior period)
- One key win and one area of concern (with root cause from the Anomaly Investigation Loop)

### 2. Key Metrics Dashboard

| Metric | This Period | Prior Period | Change | Target | Status |
|--------|------------|--------------|--------|--------|--------|

Status indicators:
- On track (meeting or exceeding target)
- At risk (below target but within acceptable range)
- Off track (significantly below target)

### 3. Trend Analysis
- Performance trend over the period (week-over-week or month-over-month)
- Notable inflection points with root cause (from Anomaly Investigation Loop)
- Seasonal or cyclical patterns observed
- Comparison to benchmarks or targets

### 4. What Worked
- Top 3-5 wins with specific data
- Why these performed well (hypothesis or confirmed cause)
- How to replicate or scale

### 5. What Needs Improvement
- Bottom 3-5 performers with specific data
- Root cause (from Anomaly Investigation Loop, not just hypothesis)
- Recommended fixes with expected impact

### 6. Insights and Observations
- Patterns in the data not obvious from the metrics alone
- Audience behavior insights
- Content or creative themes that resonated
- External factors that influenced performance

### 7. Recommendations
For each recommendation:
- What to do
- Why (linked to a specific finding with root cause)
- Expected impact (high, medium, low)
- Effort to implement (high, medium, low)
- Priority (immediate, next sprint, next quarter)

Prioritize recommendations in a 2x2 matrix:

| | Low Effort | High Effort |
|---|---|---|
| **High Impact** | Do first | Plan for next sprint |
| **Low Impact** | Do if time allows | Deprioritize |

### 8. Next Period Focus
- Top 3 priorities for the upcoming period
- Tests or experiments to run
- Targets for key metrics

---

## Metric Definitions and Benchmarks

### Email Marketing

| Metric | Definition | Benchmark Range |
|--------|-----------|----------------|
| Delivery rate | Emails delivered / emails sent | 95-99% |
| Open rate | Unique opens / emails delivered | 15-30% |
| Click-through rate (CTR) | Unique clicks / emails delivered | 2-5% |
| Click-to-open rate (CTOR) | Unique clicks / unique opens | 10-20% |
| Unsubscribe rate | Unsubscribes / emails delivered | <0.5% |
| Conversion rate | Conversions / emails delivered | 1-5% |

### Paid Advertising

| Metric | Definition |
|--------|-----------|
| Click-through rate (CTR) | Clicks / impressions |
| Cost per click (CPC) | Total spend / clicks |
| Conversion rate | Conversions / clicks |
| Cost per acquisition (CPA) | Total spend / conversions |
| Return on ad spend (ROAS) | Revenue / ad spend |

### SEO / Organic Search

| Metric | Definition |
|--------|-----------|
| Organic sessions | Visits from organic search |
| Keyword rankings | Position for target keywords |
| Organic CTR | Clicks / impressions in search results |
| Backlinks | Number of external sites linking to you |
| Organic conversion rate | Organic conversions / organic sessions |

### Overall Marketing / Pipeline

| Metric | Definition |
|--------|-----------|
| Marketing qualified leads (MQLs) | Leads meeting marketing qualification criteria |
| MQL to SQL conversion rate | SQLs / MQLs |
| Pipeline generated | Dollar value of opportunities created |
| Customer acquisition cost (CAC) | Total marketing + sales cost / new customers |
| Marketing-sourced revenue | Revenue from marketing-originated deals |

---

## Reporting Templates by Cadence

### Weekly Marketing Report
- Top 3 metrics with week-over-week change
- What worked this week (1-2 points with data)
- What needs attention (1-2 points with root cause)
- This week's priorities (3-5 action items)

### Monthly Marketing Report
1. Executive summary (3-5 sentences)
2. Key metrics dashboard (table with MoM and target comparison)
3. Channel-by-channel performance summary
4. Campaign highlights and results
5. Anomaly investigation findings (root causes for all significant deviations)
6. What worked and what did not
7. Recommendations and next month priorities
8. Budget spend vs. plan

### Quarterly Business Review (QBR)
1. Quarter performance vs. goals
2. Year-to-date trajectory
3. Channel ROI analysis
4. Campaign performance summary
5. Anomaly patterns across the quarter (recurring issues vs. one-time events)
6. Competitive and market observations
7. Strategic recommendations for next quarter
8. Budget request and allocation plan
9. Key experiments and learnings

---

## Attribution Modeling Basics

| Model | How It Works | Best For |
|-------|-------------|----------|
| Last touch | 100% credit to last interaction | Understanding final conversion triggers |
| First touch | 100% credit to first interaction | Understanding top-of-funnel effectiveness |
| Linear | Equal credit to all touchpoints | Fair representation of all channels |
| Time decay | More credit to touchpoints closer to conversion | Balanced view favoring recent interactions |
| Position-based (U-shaped) | 40% first, 40% last, 20% middle | Valuing both discovery and conversion |

Start with last-touch attribution if you have no model in place. Compare first-touch and last-touch to understand which channels drive awareness vs. conversion.

---

## DigitalCLIQ Design System (mandatory)

<!-- design-system-block v1 · do not edit per-skill · source: Resources/design-system/ -->

Every file this skill ships (PDF, DOCX, XLSX, PPTX, HTML) is built to `Resources/design-system/Design-System.md` and must pass the `Resources/design-system/Visual-QA.md` render gate before it is declared done. This section overrides any conflicting styling instruction elsewhere in this skill.

1. **Read first.** `Resources/design-system/Design-System.md` plus the Branding and render-gate sections of `Context/vault-facts.md`, before generating anything.
2. **Palette.** Digital Blue `#405FAB`, Sky Blue `#6B9DD4`, Warm Grey `#949592`, dark navys `#070A15` / `#10162A` / `#151E37` / Card Navy `#131B30`, Callout Tint `#EDF2F9`, Card White `#FBFBFD`, Tile Blue `#2E4780`, borders `#D8E1F0`. No color outside the Design-System token table. Tier/score/status coding uses palette treatments only (Sky Blue family = strong, Warm Grey = weak, Digital Blue = emphasis) with explicit text labels carrying the meaning. OEM brand colors inside client-specific charts are the only exception. Never legacy `#0D1B2A`-era navys, never default chart rainbows (red/orange/green).
3. **Fonts.** Dosis carries structure (headings, stats, labels), Roboto Slab carries reading (body). Confirm they resolve before generating (`system_profiler SPFontsDataType | grep -ci dosis` > 0); install from `Resources/brand-assets/fonts/` if missing. Arial/Calibri/Helvetica in output = FAIL.
4. **Logo.** WHITE knockout `Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png` on blue/dark backgrounds ONLY; FULL-COLOR `Resources/brand-assets/classic-digital-cliq-logo-solid-1000px-wide copy.png` on white/light ONLY. Default header = Digital Blue masthead band (~0.6in) with the white logo (~0.35in tall) left-aligned. A missing logo fails loudly, never silently.
5. **Cover.** The canonical cover comes from `Resources/design-system/templates/` (`cover-portrait.html` for documents, `cover-16x9.html` for decks). Never hand-build a cover per file.
6. **Visual-first.** Build pages from the Design-System component library: stat cards, stat bands, callout bars, icon tiles, numbered list cards, comparison splits, ghost numerals, running furniture. A wall-of-text page is a DEFECT. Max ~55% of any page as body text.
7. **Render gate.** `python3 Resources/design-system/templates/render_check.py <file>`, then visually READ every rendered page against the Visual-QA checklist. Fix in the generator, re-render, repeat until two consecutive fully-clean passes. Report passes run and defects caught to Drew.
8. **Staging.** Deliverables land in `outputs/` first, then file to the owning client's `Projects/{CODE}/deliverables/` (creative to `social-assets/` / `blog-assets/`). Never the Desktop, never next to the input file.

## After the Report

Ask: "Would you like me to:
- Create a slide-ready summary of these results?
- Draft a stakeholder email with the key takeaways?
- Dive deeper into any specific metric or channel?
- Set up a reporting template you can reuse next period?"

## Final QA Gate: deliverable-reviewer agent (MANDATORY, added 2026-08-13)

Runs AFTER the deliverable is generated and post_flight.py passes, BEFORE filing/presenting. post_flight.py is mechanical; this gate is the human-style read.

1. **Write a facts manifest** next to the deliverable in `outputs/`: a JSON list of every number, name, date, and claim that appears in the deliverable, each as `{"value": ..., "label": "where it appears", "source": "tool/file/URL it came from"}`. Build it from data already in context, never re-fetch anything just for the manifest.
2. **Spawn the `deliverable-reviewer` agent** (fresh eyes, it did not write the report). Pass in the prompt: the absolute path(s) of the finished deliverable file(s), the manifest path, and any skill-specific checks from this SKILL.md. It renders every page, reads them all, cross-checks figures against the manifest, and reviews tone/copy.
3. **Auto-fix every finding** in the source generator or data (never by hand-editing the output), re-render, and re-run the agent once. Max 2 review passes. If CRITICAL or MAJOR findings remain after pass 2, the ship is BLOCKED: report the remaining findings to Drew verbatim instead of presenting the file as done.
4. The run summary MUST include a **QA line**: what the reviewer caught and what was fixed, or "QA: clean on first pass (N pages read, M figures verified)". Never silently skip the gate; if the agent could not run, say so explicitly in the delivery message.
