---
name: auto-trends
description: Generate a branded PDF automotive market trend report covering new/used vehicle sales, service/fixed ops, and parts trends with 6-month and 12-month outlooks. Default region is Southern California. Use when Drew says /auto-trends, "market trend report", "auto market outlook", or asks how the car market / fixed ops / parts business is trending (market-wide, not a specific client).
argument-hint: [optional region, e.g. "Southern California" or "Dallas-Fort Worth"]
allowed-tools: WebSearch, Read, Write, Bash(python3 *), Bash(pip3 install *), Task
---

> [!important] Pre-flight: load the facts ledger FIRST
> Before doing anything else, read `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Context/vault-facts.md` and obey it. It is the source of truth for: output location (always the vault `outputs/` folder, never the Desktop or the input file's directory), the canonical working folder (the vault root, never an old/legacy folder), the DigitalCLIQ Master calendar, the canonical logo path, and correct client/competitor names (e.g. "BMW of Buena Park (AutoNation)" not "Shelly BMW"; LOGO Cargo is a hostile competitor, not an Atlas partner). Validate every output path and every client/competitor name against the ledger before writing. If a fact you need is missing from the ledger, do not guess: check the vault and flag it.

# Automotive Market Trend Report Generator

Generate a professional, branded PDF report analyzing current automotive industry trends. Covers New Vehicle Sales, Used Vehicle Sales, Service/Fixed Operations, and Parts. Includes 6-month and 12-month outlooks. Output is a PDF report branded by DigitalCLIQ.

**Script paths.** This skill's scripts sit in its own folder. Run them as `"${CLAUDE_SKILL_DIR}/<file>"`, always double-quoted. If ${CLAUDE_SKILL_DIR} did not expand, use the Base directory printed when this skill loaded. Never search the disk for the skill (no `find`), and never edit the installed copy during a run (see "Generator fixes during a run" in Step 5).

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
> The generator (`generate_trends_report.py`) is HTML + CSS rendered by Chrome headless `--print-to-pdf` (180-second timeout; a failure raises an error that names the engine and carries Chrome's stderr). WeasyPrint runs only when `AUTO_TRENDS_ENGINE=weasyprint` is set: it does not load on this Mac (no libgobject/pango), and do not install pango or Homebrew to make it load, because that silently switches engines and reflows layouts tuned on Chrome. The generator is built from the Design-System component library (reference implementation: `outputs/ncbmw_used_car_strategy_2026-07-10.html` and `Resources/design-system/templates/tokens.css`). NEVER reportlab for this report. The final page is always a "Who We Are" closing page (agency blurb + Drew Moon, drewmoon@digitalcliq.com).

## Process

### Step 1: Check Dependencies

Ensure the render + validation toolchain is present, and confirm the brand fonts resolve:
```
python3 -c "import pdfplumber, fitz" 2>&1 || pip3 install pdfplumber pymupdf
# Brand fonts (Dosis + Roboto Slab) must be installed for HTML rendering:
system_profiler SPFontsDataType 2>/dev/null | grep -qi dosis || cp "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/fonts/"Dosis-*.ttf "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/fonts/"Roboto-Slab-*.ttf ~/Library/Fonts/
```
The generator embeds the fonts via `@font-face` from the vault archive, so Chrome renders them even if the system install lags.

### Step 2: Determine Region

- If `$ARGUMENTS` is provided and non-empty, use it as the geographic region (e.g., "Dallas-Fort Worth", "Chicago Metro", "Northeast US")
- If no argument is given, default to **"Southern California"**
- Store the region string for use in search queries and report metadata

### Step 3: Research Phase, Web Searches

**PARALLEL RESEARCH (DEFAULT):** Launch 5 foreground Task agents in a SINGLE message, one per category below: (1) New Vehicle Sales, (2) Used Vehicle Sales, (3) Service / Fixed Operations, (4) Parts, (5) Strategic / Macro. Each agent runs only its own numbered searches, applies the Period discipline block below to every stat, and returns structured JSON in its final message:

```json
{"category": "...",
 "findings": [{"stat": "...", "value": "...", "source": "Publisher, report name",
               "url": "https://...", "published": "YYYY-MM-DD",
               "period": "YYYY-MM | YYYY-Qn | YYYY-Hn | YYYY | YTD",
               "kind": "actual | forecast | estimate | market-implied",
               "geo": "US | CA | SoCal"}],
 "narrative_points": ["..."]}
```

Paste the Period discipline block into every agent prompt verbatim. The main context runs no searches itself; it merges the 5 payloads into the Step 4 JSON. An agent that gets thin results retries with reworded queries before returning, it never returns empty without noting what it tried.

> [!important] Period discipline (every stat, every run)
> 1. Every stat carries a **publication date** (the day the page went up, `published: YYYY-MM-DD`) and a **data period** (the month, quarter, half or year the number measures). A stat without both is not usable.
> 2. An `actual` published before its period ended is either the wrong year or a forecast. Reject it and keep searching. The 9/5 edition shipped an "August" ATP ($49,077) from an article published 2025-09-10, and a J.D. Power forecast presented as an actual.
> 3. If this month's figure is not out yet, use the latest published month and say so in the copy ("July 2026 data"). Never relabel last year's same-month print as this year's.
> 4. Label forecasts and market-implied odds as such, in `kind` and in the words that print next to the number ("forecast", "projected", "odds").
> 5. Check every same-month figure against its publication year. Early in a month, search results surface last year's edition of the same monthly report first.
> 6. Any "record", "peak" or "high" in prose needs its as-of date in the same sentence ("a record $812 for any August, per NADA's September 4 2026 Market Beat").

Run the following targeted web searches. For each, extract specific numbers, percentages, trend directions, and source names, plus the page URL, its publication date and the data period. Adapt search queries to include the current year.

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

For each search result, note the **publisher, URL, publication date and data period** for the sources page.

**Merging the five payloads.** When two findings give different figures for the same metric, the one with the later `published` date wins, provided it passes Period discipline. Never keep the older figure "for internal consistency" (that is how $49,077 beat $49,855 on 9/5). A figure carried over from last month's archive counts only after it is re-found at its source with its publication date.

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
      "caption": "One bolded lead sentence stating the headline finding. Then one or two sentences of context.",
      "source": "Publisher, report name", "url": "https://...", "published": "YYYY-MM-DD",
      "period": "YYYY-MM", "kind": "actual"
    },
    "headline_stats": [
      {"value": "16.1-16.5M", "label": "Mid-2026 new-vehicle SAAR", "source": "Cox Automotive, June 2026",
       "url": "https://...", "published": "YYYY-MM-DD", "period": "2026-06", "kind": "actual"},
      {"value": "$30,200", "label": "Avg used retail price", "source": "CarGurus, May 2026",
       "url": "https://...", "published": "YYYY-MM-DD", "period": "2026-05", "kind": "actual"},
      {"value": "-9.3%", "label": "SoCal Q1 new-vehicle registrations YoY", "source": "CNCDA, Q1 2026",
       "url": "https://...", "published": "YYYY-MM-DD", "period": "2026-Q1", "kind": "actual"},
      {"value": "34.9 wks", "label": "Median income to buy a new car", "source": "Cox Affordability Index, June 2026",
       "url": "https://...", "published": "YYYY-MM-DD", "period": "2026-05", "kind": "actual"}
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
        {"label": "Metric Name", "value": "Value", "trend": "up|down|flat", "detail": "Brief explanation (Publisher, Month YYYY).", "source": "Publisher, report name", "url": "https://...", "published": "YYYY-MM-DD", "period": "YYYY-MM", "kind": "actual"},
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
        {"label": "Metric Name", "value": "Value", "trend": "up|down|flat", "detail": "Brief explanation (Publisher, Month YYYY).", "source": "Publisher, report name", "url": "https://...", "published": "YYYY-MM-DD", "period": "YYYY-MM", "kind": "actual"},
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
      {"label": "Metric Name", "value": "Value", "trend": "up|down|flat", "detail": "Brief explanation (Publisher, Month YYYY).", "source": "Publisher, report name", "url": "https://...", "published": "YYYY-MM-DD", "period": "YYYY-MM", "kind": "actual"},
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
      "caption": "Bolded lead sentence for the dark stat band. Then the so-what for the dealer.",
      "source": "Publisher, report name", "url": "https://...", "published": "YYYY-MM-DD",
      "period": "YYYY-Qn", "kind": "actual"
    },
    "summary": "Overview paragraph.",
    "metrics": [
      {"label": "Metric Name", "value": "Value", "trend": "up|down|flat", "detail": "Brief explanation (Publisher, Month YYYY).", "source": "Publisher, report name", "url": "https://...", "published": "YYYY-MM-DD", "period": "YYYY-MM", "kind": "actual"},
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
      {"label": "Metric Name", "value": "Value", "trend": "up|down|flat", "detail": "Brief explanation (Publisher, Month YYYY).", "source": "Publisher, report name", "url": "https://...", "published": "YYYY-MM-DD", "period": "YYYY-MM", "kind": "actual"},
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
- **Every claim carries its receipts.** Each hero, headline stat and metric carries `source`, `url` (the exact page the number came from), `published` (YYYY-MM-DD), `period` (YYYY-MM | YYYY-Qn | YYYY-Hn | YYYY | YTD) and `kind` (actual | forecast | estimate | market-implied), straight from the research payload. `detail` stays prose and must end with the citation `(Publisher, Month YYYY)`: the generator prints that citation as the stat card's source line, and a detail without one now prints an empty source slot instead of a chopped caption. The values `https://...` and `YYYY-MM-DD` above are schema placeholders; the claims check treats them as missing.
- A forecast or market-implied figure says so where it prints: its `label` (or the hero caption) uses "forecast", "projected" or "odds".
- **Every headline number and every editorial phrase comes from THIS run.** The generator holds no hardcoded stats: `executive_summary.hero`, `executive_summary.headline_stats`, `executive_summary.throughline`, `fixed_ops.hero`, each section's `headline`, and `metadata.period_label` must be filled fresh each month. Omitted fields degrade gracefully (the fixed-ops band disappears, headlines fall back to generic section titles) rather than reprinting a prior month, so an unfilled field shows up as a thinner page, not as stale data with a real source citation under it.
- `headline` on a section is the editorial angle for the month (e.g. "Softening volume, record prices"). Rewrite it every run to match what the data actually says.
- If a data point was not found, omit the metric or write "Data not available for this period" in the detail field
- Each metrics array should have 3-6 items covering the most important KPIs
- OEM highlights should cover at least 4-5 major brands
- Sources list should include every source referenced in the report, each as "Publisher, report name, Month D YYYY" (the publication date, not a bare year)
- All text should be written in a professional, analytical tone suitable for dealership executives

### Step 4b: Claims check (run before generating)

```
python3 "${CLAUDE_SKILL_DIR}/validate_claims.py" /tmp/auto_trends_data.json
```

It checks every hero, headline stat and metric for: a named source, a real URL and a publication date (ERROR when missing); a publication date after today's report date (ERROR); an `actual` published before its period ended or began, which means the wrong year or a forecast (ERROR; YTD and partial-period tokens pass); staleness (monthly figures over 120 days old, quarterly or half-year over 200, annual exempt); forecast wording without `kind: forecast` and the reverse; and "record / peak / high" claims in the overview, throughline, key trends and risks with no as-of date. It also lists prose figures that have no structured claim behind them.

**It is WARN-ONLY this cycle:** it prints problems to stderr and exits 0. When it prints any ERROR or WARN line, fix the DATA (re-research the missing URL or date, correct the period or kind, move to the latest published month, add the as-of date) and re-run it until it is clean or every remaining line is explained in the Step 6 summary. Never edit the checker or pass around it. `--strict` (or `AUTO_TRENDS_CLAIMS=strict`) turns errors into exit 1; that becomes the default once an edition ships clean.

### Step 5: Generate PDF

Determine the output filename using today's date:
```
Auto_Trends_Report_YYYY-MM-DD.pdf
```

Run the PDF generator. It reads the JSON and emits the component-based HTML (cover → executive summary → new/used/fixed-ops/parts → strategic outlook → sources → Who We Are), then renders to PDF via Chrome headless. It runs the Step 4b claims check again (same warn-only rule) and writes the facts manifest `Auto_Trends_Report_YYYY-MM-DD.facts.json` next to the PDF from the structured claims. **All deliverables go to `outputs/`** (per project workflow conventions, never `02_Reports/`, the Desktop, or next to the input file):
```
python3 "${CLAUDE_SKILL_DIR}/generate_trends_report.py" \
    /tmp/auto_trends_data.json \
    "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/Auto_Trends_Report_YYYY-MM-DD.pdf" \
    "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png"
```

Replace `YYYY-MM-DD` with the actual current date. Output is ~9 pages.

After generating, run the mandatory [[Visual-QA]] render gate: rasterize every page (`render_check.py`) and visually READ each one. A page that is mostly paragraphs FAILS, rebuild it with components. Fix, re-render, repeat until two consecutive clean passes.

**Generator fixes during a run.** Try a data-side fix first (for example a trailing `(Publisher, Month YYYY)` on a detail string, or a shorter caption). If the generator itself must change, copy the skill's scripts to a scratch folder, patch the scratch copy and render from it. Never edit the installed copy under `${CLAUDE_SKILL_DIR}` and never patch `~/Desktop/Skills`: nothing runs those edits next month. Save the change as a diff, `diff -u "${CLAUDE_SKILL_DIR}/generate_trends_report.py" "<scratch>/generate_trends_report.py" > "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/auto-trends-patches/YYYY-MM-DD.diff"` (make the folder if needed), and list it in the Step 6 summary so Drew can land it in the `~/Desktop/digitalcliq-skills` repo.

### Step 5b: Generate the distribution assets

The PDF is not the canonical asset. The BLOG POST is. HTML ranks in Google and is what AI answer engines (ChatGPT, Perplexity, AI Overviews) can cite; a PDF does neither. The PDF is the download and the LinkedIn native document.

Run the companion generator against the SAME JSON:
```
python3 "${CLAUDE_SKILL_DIR}/generate_blog_assets.py" \
    /tmp/auto_trends_data.json \
    "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs" \
    "Auto_Trends_Report_YYYY-MM-DD.pdf"
```

It emits three things:
1. `Auto_Trends_Report_YYYY-MM-DD_blog.html`: paste-ready Squarespace article body plus Article and FAQPage JSON-LD. Structured for AI citation: key-numbers table high on the page, question-phrased H2s, every stat with an inline named source and date.
2. `Auto_Trends_Report_YYYY-MM-DD_publishing-kit.md`: SEO fields (title, slug, meta description, excerpt, tags), the LinkedIn post copy and first comment, the email copy, and the publish checklist.
3. `Intelligence/market/auto-trends/YYYY-MM.json`: the archived research payload.
4. `Intelligence/market/auto-trends/Market-Read.md`: the ROLLING canonical market note, overwritten every run. This is the vault-facing artifact: `Context/vault-facts.md` points every skill at it, so monthly client reports, forecasts, lead scoring, paid-media audits, morning briefings, and content skills read it instead of re-researching the market. A raw JSON archive is invisible to Obsidian search and wikilinks; this file is not.
5. `Intelligence/market/auto-trends/README.md`: the archive index with a headline-trend table across every month on disk.

Both markdown files are generated, never hand-edited. If a figure is wrong, fix it in the research step and regenerate.

**The archive is what makes this a series.** On every run after the first, read the most recent archived JSON BEFORE researching. Use it to (a) target the research at what changed rather than rediscovering the market from zero, which cuts search volume substantially, and (b) state month-over-month movement in the copy ("SAAR 15.8M, down from 16.1M last month"). The archive is a checklist of metrics to refresh, never a source: re-verify every carried-forward figure at its original publisher, with its publication date, before it goes back into the report. If no archive exists yet, note that this is the baseline run.

Render-gate the blog HTML too. First the deterministic pre-check, every run:
```
python3 "${CLAUDE_SKILL_DIR}/validate_claims.py" --blog-html "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/Auto_Trends_Report_YYYY-MM-DD_blog.html"
```
It confirms every JSON-LD block parses and that the page has no em dashes and no placeholder tokens. It is warn-only (exit 0): fix any line it prints in the data or generator and re-run. Then, in an attended run, open the HTML in the Claude Browser pane at 1000px and 390px widths and READ both (same two-clean-passes rule). Never launch a background headless Chrome for the blog screenshots. An unattended scheduled run skips the visual pass and says in its summary that the HTML visual gate was not run.

> [!warning] Never publish on Drew's behalf
> This skill produces DRAFT copy for LinkedIn, the blog, and email. It never posts, publishes, or sends. Hand Drew the publishing kit and let him decide.

### Step 6: Report Results

Display a concise summary to the user:
- Report title and region
- Date ranges covered (6-month and 12-month)
- Number of data sources referenced
- One highlight from each major section (New, Used, Service, Parts)
- Month-over-month movement versus the archived prior run, or "baseline run" if none
- Claims check: "clean", or each remaining ERROR/WARN line and why it stands; plus the blog pre-check result (and, on an unattended run, "HTML visual gate not run unattended")
- Any generator patch diff saved under `outputs/auto-trends-patches/`
- All output file paths: PDF, blog HTML, publishing kit, facts manifest

Keep the summary to 8-10 lines. The deliverables are the PDF plus the blog HTML and publishing kit.


## Self-Validation (MANDATORY: final step before reporting success)

After the deliverable is generated, run the shared post-flight validator on the final file. This step is not optional and runs on every invocation:

```bash
python3 "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/post_flight.py" \
  "<final output path>" --min-pages 8
```

It verifies four things and exits non-zero if any fail:
1. **Branding**: the DigitalCLIQ logo is actually embedded in the file (image objects present on every PDF page). A black tile with no logo image is a FAILURE, not a fallback.
2. **Location**: the file is inside `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/`. Anywhere else (especially the Desktop) fails.
3. **Page count**: at least 8 pages; fewer means a section silently failed or the report is truncated.
4. **No placeholder data**: template tokens like `{dealer_name}`, literal `YYYY-MM-DD`, "PLACEHOLDER", or lorem ipsum anywhere in the deliverable fail.

**On failure: retry once with a fallback, then fail loudly:**
1. Diagnose from the validator output. Common fixes: the logo must load from the canonical path `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png`; a file saved outside `outputs/` must be moved there and re-validated; a placeholder hit means a data section came back empty, re-fetch that data, do not paper over it.
2. Regenerate the deliverable ONCE and re-run the validator.
3. If it still fails: STOP. Show the user the validator output verbatim and state that the report FAILED validation. Never report success, never present the file as the final deliverable, and never wrap this step in try/except or `|| true` that hides the failure.


## Final QA Gate: deliverable-reviewer agent (MANDATORY, added 2026-08-13)

Runs AFTER the deliverable is generated and post_flight.py passes, BEFORE filing/presenting. post_flight.py is mechanical; this gate is the human-style read.

1. **Facts manifest.** The generator already wrote `Auto_Trends_Report_YYYY-MM-DD.facts.json` next to the PDF: one entry per hero, headline stat and stat card, each with `id, value, label, source, url, published, period, kind, page`. Do not rewrite it by hand. Append only the prose figures the claims check listed under INFO (overview, throughline, key trends, outlooks), each as `{"value": ..., "label": "where it appears", "source": ..., "url": ..., "published": ..., "origin": "prose"}` from data already in context. Entries marked `origin: prose` survive a re-render; generator entries are rebuilt every time. Never write "see row" as a source.
2. **Spawn the `deliverable-reviewer` agent** (fresh eyes, it did not write the report). Pass in the prompt: the absolute path(s) of the finished deliverable file(s), the manifest path, and any skill-specific checks from this SKILL.md. It renders every page, reads them all, cross-checks figures against the manifest, and reviews tone/copy. Skill-specific check to include: for the two hero bands and the four headline stats, fetch each manifest `url` with Bash (`curl -sL --max-time 20 "<url>"`), and confirm the page carries the figure and a publication date matching `published`. A page that shows the figure under a different year, or a different figure for the same period, is MAJOR (that is the 9/5 failure). A page curl cannot load (403, paywall, bot wall) or whose date cannot be found is MINOR: list it in the QA line, it does not block.
3. **Auto-fix every finding** in the data, or in a scratch copy of the generator per "Generator fixes during a run" (never by hand-editing the output, never in the installed copy), re-render, and re-run the agent once. Max 2 review passes. If CRITICAL or MAJOR findings remain after pass 2, the ship is BLOCKED: report the remaining findings to Drew verbatim instead of presenting the file as done.
4. The run summary MUST include a **QA line**: what the reviewer caught and what was fixed, or "QA: clean on first pass (N pages read, M figures verified)". Never silently skip the gate; if the agent could not run, say so explicitly in the delivery message.
