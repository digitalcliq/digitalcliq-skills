---
name: auto-trends
description: Generate a branded PDF automotive market trend report covering new/used vehicle sales, service/fixed ops, and parts trends with 6-month and 12-month outlooks. Default region is Southern California. Use when Drew says /auto-trends, "market trend report", "auto market outlook", or asks how the car market / fixed ops / parts business is trending (market-wide, not a specific client).
argument-hint: [optional region, e.g. "Southern California" or "Dallas-Fort Worth"]
allowed-tools: WebSearch, Read, Write, Bash(python3 *), Bash(pip3 install *), Task
---

> [!important] Pre-flight: load the facts ledger FIRST
> Before doing anything else, read `/Users/drewmoon/Desktop/DigitalCLIQ Brain/DigitalCLIQ Brain/Context/vault-facts.md` and obey it. It is the source of truth for: output location (always the vault `outputs/` folder, never the Desktop or the input file's directory), the canonical working folder (the vault root, never an old/legacy folder), the DigitalCLIQ Master calendar, the canonical logo path, and correct client/competitor names (e.g. "BMW of Buena Park (AutoNation)" not "Shelly BMW"; LOGO Cargo is a hostile competitor, not an Atlas partner). Validate every output path and every client/competitor name against the ledger before writing. If a fact you need is missing from the ledger, do not guess: check the vault and flag it.

# Automotive Market Trend Report Generator

Generate a professional, branded PDF report analyzing current automotive industry trends. Covers New Vehicle Sales, Used Vehicle Sales, Service/Fixed Operations, and Parts. Includes 6-month and 12-month outlooks. Output is a PDF report branded by DigitalCLIQ.

**Developed by DigitalCLIQ: Digital Strategy & Development**

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

> [!note] Skill-specific build facts (must not contradict the block above)
> The generator (`generate_trends_report.py`) is HTML + CSS rendered by WeasyPrint (or Chrome headless `--print-to-pdf` fallback), built from the Design-System component library (reference implementation: `outputs/ncbmw_used_car_strategy_2026-07-10.html` and `Resources/design-system/templates/tokens.css`). NEVER reportlab for this report. The final page is always a "Who We Are" closing page (agency blurb + Drew Moon, drewmoon@digitalcliq.com).

## Process

### Step 1: Check Dependencies

Ensure the render + validation toolchain is present, and confirm the brand fonts resolve:
```
python3 -c "import pdfplumber, fitz" 2>&1 || pip3 install pdfplumber pymupdf
# Brand fonts (Dosis + Roboto Slab) must be installed for HTML rendering:
system_profiler SPFontsDataType 2>/dev/null | grep -qi dosis || cp "/Users/drewmoon/Desktop/DigitalCLIQ Brain/DigitalCLIQ Brain/Resources/brand-assets/fonts/"Dosis-*.ttf "/Users/drewmoon/Desktop/DigitalCLIQ Brain/DigitalCLIQ Brain/Resources/brand-assets/fonts/"Roboto-Slab-*.ttf ~/Library/Fonts/
```
The generator embeds the fonts via `@font-face` from the vault archive, so Chrome renders them even if the system install lags.

### Step 2: Determine Region

- If `$ARGUMENTS` is provided and non-empty, use it as the geographic region (e.g., "Dallas-Fort Worth", "Chicago Metro", "Northeast US")
- If no argument is given, default to **"Southern California"**
- Store the region string for use in search queries and report metadata

### Step 3: Research Phase, Web Searches

**PARALLEL RESEARCH (DEFAULT):** Launch 5 foreground Task agents in a SINGLE message, one per category below: (1) New Vehicle Sales, (2) Used Vehicle Sales, (3) Service / Fixed Operations, (4) Parts, (5) Strategic / Macro. Each agent runs only its own numbered searches, verifies each stat has a named source and date, and returns structured JSON in its final message: `{"category": ..., "findings": [{"stat": ..., "value": ..., "source": ..., "date": ...}], "narrative_points": [...]}`. The main context runs no searches itself; it merges the 5 payloads into the Step 4 JSON. An agent that gets thin results retries with reworded queries before returning, it never returns empty without noting what it tried.

Run the following targeted web searches. For each, extract specific numbers, percentages, trend directions, and source names. Adapt search queries to include the current year.

**New Vehicle Sales (3-4 searches):**
1. `"new vehicle sales United States SAAR [current year]"`: SAAR, total volume, month-over-month
2. `"new car average transaction price incentives days supply [current year]"`: ATPs, incentive spend, inventory days
3. `"[region] new car sales trends [current year]"`: regional market specifics
4. `"OEM brand sales [current year] BMW Nissan Toyota Honda Stellantis Ford"`: brand-level highlights

**Used Vehicle Sales (2-3 searches):**
5. `"used car prices wholesale retail Manheim index [current year]"`: Manheim index, wholesale/retail pricing
6. `"used vehicle inventory CPO certified pre-owned [current year] trends"`: CPO volume, age/mileage mix, inventory
7. `"[region] used car market [current year]"`: regional used market data

**Service / Fixed Operations (2-3 searches):**
8. `"dealership fixed operations service trends effective labor rate [current year]"`: ELR, RO counts, customer pay vs warranty
9. `"auto technician shortage service retention dealership [current year]"`: labor market, retention, wages
10. `"EV service readiness dealership [current year]"`: EV servicing impact

**Parts (2 searches):**
11. `"auto parts market trends OEM aftermarket margins [current year]"`: parts margins, competition
12. `"automotive parts supply chain EV parts impact [current year]"`: supply chain, EV disruption

**Strategic / Macro (1-2 searches):**
13. `"automotive industry outlook risks opportunities [current year]"`: macro trends, interest rates, tariffs
14. `"Cox Automotive automotive forecast [current year]"`: analyst forecasts and projections

For each search result, note the **source name and date** for the sources page.

### Step 4: Synthesize into JSON

Write a structured JSON file to `/tmp/auto_trends_data.json` using this schema:

```json
{
  "metadata": {
    "report_title": "Automotive Market Trend Report",
    "region": "Southern California",
    "generation_date": "YYYY-MM-DD",
    "period_label": "July 2026",
    "oem_period_label": "First-half 2026 read",
    "date_range_6mo": "Month YYYY - Month YYYY",
    "date_range_12mo": "Month YYYY - Month YYYY"
  },
  "executive_summary": {
    "overview": "2-3 sentence market overview paragraph summarizing the current state.",
    "hero": {
      "value": "15.8M units",
      "caption": "One bolded lead sentence stating the headline finding. Then one or two sentences of context."
    },
    "headline_stats": [
      {"value": "16.1-16.5M", "label": "Mid-2026 new-vehicle SAAR", "source": "Cox Automotive, June 2026"},
      {"value": "$30,200", "label": "Avg used retail price", "source": "CarGurus, May 2026"},
      {"value": "-9.3%", "label": "SoCal Q1 new-vehicle registrations YoY", "source": "CNCDA, Q1 2026"},
      {"value": "34.9 wks", "label": "Median income to buy a new car", "source": "Cox Affordability Index"}
    ],
    "throughline": "The single argument the whole report supports, in 2-3 sentences.",
    "key_trends": [
      "First key trend headline with supporting data",
      "Second key trend headline with supporting data",
      "Third key trend headline with supporting data",
      "Fourth key trend (optional)",
      "Fifth key trend (optional)"
    ]
  },
  "new_vehicle_sales": {
    "section_title": "New Vehicle Sales Trends",
    "national": {
      "summary": "2-3 sentence national overview.",
      "metrics": [
        {"label": "Metric Name", "value": "Value", "trend": "up|down|flat", "detail": "Brief explanation"},
        ...
      ]
    },
    "oem_highlights": [
      {"brand": "Brand Name", "detail": "1-2 sentence brand summary"},
      ...
    ],
    "regional": {
      "summary": "Regional findings paragraph.",
      "metrics": [
        {"label": "Metric Name", "value": "Value", "trend": "up|down|flat", "detail": "Brief explanation"},
        ...
      ]
    },
    "outlook_6mo": "Short-term outlook paragraph.",
    "outlook_12mo": "Medium-term outlook paragraph."
  },
  "used_vehicle_sales": {
    "section_title": "Used Vehicle Sales Trends",
    "summary": "Overview paragraph.",
    "metrics": [
      {"label": "Metric Name", "value": "Value", "trend": "up|down|flat", "detail": "Brief explanation"},
      ...
    ],
    "regional": {
      "summary": "Regional findings.",
      "metrics": []
    },
    "outlook_6mo": "Short-term outlook paragraph.",
    "outlook_12mo": "Medium-term outlook paragraph."
  },
  "fixed_ops": {
    "section_title": "Service & Fixed Operations Trends",
    "headline": "Editorial page headline for THIS month, e.g. 'A record, but share-losing, engine'.",
    "hero": {
      "value": "67% vs 28%",
      "caption": "Bolded lead sentence for the dark stat band. Then the so-what for the dealer."
    },
    "summary": "Overview paragraph.",
    "metrics": [
      {"label": "Metric Name", "value": "Value", "trend": "up|down|flat", "detail": "Brief explanation"},
      ...
    ],
    "ev_readiness": "EV service readiness paragraph.",
    "technician_market": "Technician shortage and wage paragraph.",
    "outlook_6mo": "Short-term outlook paragraph.",
    "outlook_12mo": "Medium-term outlook paragraph."
  },
  "parts": {
    "section_title": "Parts Trends",
    "summary": "Overview paragraph.",
    "metrics": [
      {"label": "Metric Name", "value": "Value", "trend": "up|down|flat", "detail": "Brief explanation"},
      ...
    ],
    "oem_vs_aftermarket": "Commentary paragraph on OEM vs aftermarket dynamics.",
    "ev_impact": "Commentary paragraph on EV impact on parts business.",
    "outlook_6mo": "Short-term outlook paragraph.",
    "outlook_12mo": "Medium-term outlook paragraph."
  },
  "strategic_outlook": {
    "section_title": "Strategic Outlook",
    "short_term": [
      "6-month implication or action item",
      "Another implication",
      ...
    ],
    "medium_term": [
      "12-month positioning recommendation",
      "Another recommendation",
      ...
    ],
    "risks": [
      "Key risk to monitor",
      "Another risk",
      ...
    ],
    "opportunities": [
      "Key opportunity to pursue",
      "Another opportunity",
      ...
    ]
  },
  "sources": [
    "Source Name, Date or Quarter",
    "Another Source, Date",
    ...
  ]
}
```

**Rules for JSON content:**
- Use real data found in searches. Do not fabricate numbers.
- **Every headline number and every editorial phrase comes from THIS run.** The generator holds no hardcoded stats: `executive_summary.hero`, `executive_summary.headline_stats`, `executive_summary.throughline`, `fixed_ops.hero`, each section's `headline`, and `metadata.period_label` must be filled fresh each month. Omitted fields degrade gracefully (the fixed-ops band disappears, headlines fall back to generic section titles) rather than reprinting a prior month, so an unfilled field shows up as a thinner page, not as stale data with a real source citation under it.
- `headline` on a section is the editorial angle for the month (e.g. "Softening volume, record prices"). Rewrite it every run to match what the data actually says.
- If a data point was not found, omit the metric or write "Data not available for this period" in the detail field
- Each metrics array should have 3-6 items covering the most important KPIs
- OEM highlights should cover at least 4-5 major brands
- Sources list should include every source referenced in the report
- All text should be written in a professional, analytical tone suitable for dealership executives

### Step 5: Generate PDF

Determine the output filename using today's date:
```
Auto_Trends_Report_YYYY-MM-DD.pdf
```

Run the PDF generator. It reads the JSON and emits the component-based HTML (cover → executive summary → new/used/fixed-ops/parts → strategic outlook → sources → Who We Are), then renders to PDF via WeasyPrint or Chrome headless. **All deliverables go to `outputs/`** (per project workflow conventions, never `02_Reports/`, the Desktop, or next to the input file):
```
python3 "/Users/drewmoon/Desktop/DigitalCLIQ Brain/DigitalCLIQ Brain/.claude/skills/auto-trends/generate_trends_report.py" \
    /tmp/auto_trends_data.json \
    "/Users/drewmoon/Desktop/DigitalCLIQ Brain/DigitalCLIQ Brain/outputs/Auto_Trends_Report_YYYY-MM-DD.pdf" \
    "/Users/drewmoon/Desktop/DigitalCLIQ Brain/DigitalCLIQ Brain/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png"
```

Replace `YYYY-MM-DD` with the actual current date. Output is ~9 pages.

After generating, run the mandatory [[Visual-QA]] render gate: rasterize every page (`render_check.py`) and visually READ each one. A page that is mostly paragraphs FAILS, rebuild it with components. Fix, re-render, repeat until two consecutive clean passes.

### Step 5b: Generate the distribution assets

The PDF is not the canonical asset. The BLOG POST is. HTML ranks in Google and is what AI answer engines (ChatGPT, Perplexity, AI Overviews) can cite; a PDF does neither. The PDF is the download and the LinkedIn native document.

Run the companion generator against the SAME JSON:
```
python3 "/Users/drewmoon/Desktop/DigitalCLIQ Brain/DigitalCLIQ Brain/.claude/skills/auto-trends/generate_blog_assets.py" \
    /tmp/auto_trends_data.json \
    "/Users/drewmoon/Desktop/DigitalCLIQ Brain/DigitalCLIQ Brain/outputs" \
    "Auto_Trends_Report_YYYY-MM-DD.pdf"
```

It emits three things:
1. `Auto_Trends_Report_YYYY-MM-DD_blog.html`: paste-ready Squarespace article body plus Article and FAQPage JSON-LD. Structured for AI citation: key-numbers table high on the page, question-phrased H2s, every stat with an inline named source and date.
2. `Auto_Trends_Report_YYYY-MM-DD_publishing-kit.md`: SEO fields (title, slug, meta description, excerpt, tags), the LinkedIn post copy and first comment, the email copy, and the publish checklist.
3. `Intelligence/market/auto-trends/YYYY-MM.json`: the archived research payload.
4. `Intelligence/market/auto-trends/Market-Read.md`: the ROLLING canonical market note, overwritten every run. This is the vault-facing artifact: `Context/vault-facts.md` points every skill at it, so monthly client reports, forecasts, lead scoring, paid-media audits, morning briefings, and content skills read it instead of re-researching the market. A raw JSON archive is invisible to Obsidian search and wikilinks; this file is not.
5. `Intelligence/market/auto-trends/README.md`: the archive index with a headline-trend table across every month on disk.

Both markdown files are generated, never hand-edited. If a figure is wrong, fix it in the research step and regenerate.

**The archive is what makes this a series.** On every run after the first, read the most recent archived JSON BEFORE researching. Use it to (a) target the research at what changed rather than rediscovering the market from zero, which cuts search volume substantially, and (b) state month-over-month movement in the copy ("SAAR 15.8M, down from 16.1M last month"). If no archive exists yet, note that this is the baseline run.

Render-gate the blog HTML too: screenshot it with Chrome headless at 1000px and 390px widths and READ both. Same two-clean-passes rule.

> [!warning] Never publish on Drew's behalf
> This skill produces DRAFT copy for LinkedIn, the blog, and email. It never posts, publishes, or sends. Hand Drew the publishing kit and let him decide.

### Step 6: Report Results

Display a concise summary to the user:
- Report title and region
- Date ranges covered (6-month and 12-month)
- Number of data sources referenced
- One highlight from each major section (New, Used, Service, Parts)
- Month-over-month movement versus the archived prior run, or "baseline run" if none
- All output file paths: PDF, blog HTML, publishing kit

Keep the summary to 8-10 lines. The deliverables are the PDF plus the blog HTML and publishing kit.


## Self-Validation (MANDATORY: final step before reporting success)

After the deliverable is generated, run the shared post-flight validator on the final file. This step is not optional and runs on every invocation:

```bash
python3 /Users/drewmoon/Desktop/DigitalCLIQ Brain/DigitalCLIQ Brain/.claude/skills/post_flight.py \
  "<final output path>" --min-pages 8
```

It verifies four things and exits non-zero if any fail:
1. **Branding**: the DigitalCLIQ logo is actually embedded in the file (image objects present on every PDF page). A black tile with no logo image is a FAILURE, not a fallback.
2. **Location**: the file is inside `/Users/drewmoon/Desktop/DigitalCLIQ Brain/DigitalCLIQ Brain/outputs/`. Anywhere else (especially the Desktop) fails.
3. **Page count**: at least 8 pages; fewer means a section silently failed or the report is truncated.
4. **No placeholder data**: template tokens like `{dealer_name}`, literal `YYYY-MM-DD`, "PLACEHOLDER", or lorem ipsum anywhere in the deliverable fail.

**On failure: retry once with a fallback, then fail loudly:**
1. Diagnose from the validator output. Common fixes: the logo must load from the canonical path `/Users/drewmoon/Desktop/DigitalCLIQ Brain/DigitalCLIQ Brain/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png`; a file saved outside `outputs/` must be moved there and re-validated; a placeholder hit means a data section came back empty, re-fetch that data, do not paper over it.
2. Regenerate the deliverable ONCE and re-run the validator.
3. If it still fails: STOP. Show the user the validator output verbatim and state that the report FAILED validation. Never report success, never present the file as the final deliverable, and never wrap this step in try/except or `|| true` that hides the failure.


## Final QA Gate: deliverable-reviewer agent (MANDATORY, added 2026-08-13)

Runs AFTER the deliverable is generated and post_flight.py passes, BEFORE filing/presenting. post_flight.py is mechanical; this gate is the human-style read.

1. **Write a facts manifest** next to the deliverable in `outputs/`: a JSON list of every number, name, date, and claim that appears in the deliverable, each as `{"value": ..., "label": "where it appears", "source": "tool/file/URL it came from"}`. Build it from data already in context, never re-fetch anything just for the manifest.
2. **Spawn the `deliverable-reviewer` agent** (fresh eyes, it did not write the report). Pass in the prompt: the absolute path(s) of the finished deliverable file(s), the manifest path, and any skill-specific checks from this SKILL.md. It renders every page, reads them all, cross-checks figures against the manifest, and reviews tone/copy.
3. **Auto-fix every finding** in the source generator or data (never by hand-editing the output), re-render, and re-run the agent once. Max 2 review passes. If CRITICAL or MAJOR findings remain after pass 2, the ship is BLOCKED: report the remaining findings to Drew verbatim instead of presenting the file as done.
4. The run summary MUST include a **QA line**: what the reviewer caught and what was fixed, or "QA: clean on first pass (N pages read, M figures verified)". Never silently skip the gate; if the agent could not run, say so explicitly in the delivery message.
