---
name: dealership-paid-media-audit
description: Run a paid media waste audit on automotive dealership ad data. Analyzes spend across Google Ads, Meta Ads, Microsoft Ads, GA4, third-party vendors, and OEM co-op reporting to identify underperforming spend, benchmark against NADA/brand-tier LTV data, and generate a branded DigitalCLIQ Excel workbook with suggestions for the GM/GSM discussion.
argument-hint: --client "<name>" --source <googleads|meta|microsoft|ga4|coop> --file <path> --period YYYY-MM
allowed-tools: Read, Write, Glob, Grep, Bash(python3 *), Bash(pip3 install *), Task, mcp__claude-in-chrome__tabs_context_mcp, mcp__claude-in-chrome__tabs_create_mcp, mcp__claude-in-chrome__tabs_close_mcp, mcp__claude-in-chrome__navigate, mcp__claude-in-chrome__read_page, mcp__claude-in-chrome__get_page_text, mcp__claude-in-chrome__find, mcp__claude-in-chrome__javascript_tool
---

> [!important] Pre-flight: load the facts ledger FIRST
> Before doing anything else, read `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Context/vault-facts.md` and obey it. It is the source of truth for: output location (always the vault `outputs/` folder, never the Desktop or the input file's directory), the canonical working folder (the vault root, never an old/legacy folder), the DigitalCLIQ Master calendar, the canonical logo path, and correct client/competitor names (e.g. "BMW of Buena Park (AutoNation)" not "Shelly BMW"; LOGO Cargo is a hostile competitor, not an Atlas partner). Validate every output path and every client/competitor name against the ledger before writing. If a fact you need is missing from the ledger, do not guess: check the vault and flag it.

# Paid Media Waste Audit, DigitalCLIQ

Run a paid media waste audit on automotive dealership ad data. Analyzes spend across Google Ads, Meta Ads, Microsoft Ads, GA4, third-party vendors, and OEM co-op reporting to identify underperforming spend, benchmark against NADA/brand-tier LTV data, and generate a branded DigitalCLIQ Excel workbook with suggestions for the GM/GSM discussion.

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

## Trigger Phrases

- "paid media audit"
- "ad waste analysis"
- "digital marketing efficiency"
- "Google Ads audit"
- "ad spend analysis"
- "media waste report"
- "paid search audit"
- "SEM audit"
- "dealership ad review"

## Invocation

```
/paid-media-audit --client "Nissan of Irvine" --source googleads --file 01_Inbox/google_ads_march.csv --period 2026-03
```

### Arguments

| Flag | Required | Description |
|---|---|---|
| `--client` | Yes | Dealership name (used for branding, tier detection, delta tracking) |
| `--source` | Yes | Source type: `googleads`, `metaads`, `microsoftads`, `ga4`, `thirdparty`, `oem`, `crm` |
| `--file` | Yes | Path to the source data file (CSV or Excel). Check `01_Inbox/` first. |
| `--period` | Yes | Report period in `YYYY-MM` format |
| `--compare-prior` | No | Include delta tab comparing against most recent prior run |
| `--browser` | No | Pull Google Ads data via Chrome browser instead of requiring CSV files |

Multiple sources can be combined in one run:
```
/paid-media-audit \
  --client "Sterling BMW" \
  --source googleads --file 01_Inbox/google.csv \
  --source metaads --file 01_Inbox/meta.csv \
  --period 2026-03 \
  --compare-prior
```

## Pipeline

```
0. EXTRACT   (Optional) Pull data from Google Ads via browser — no manual export needed
1. INGEST    Parse source file(s) → normalize to internal schema
2. CLASSIFY  Assign funnel stage to every campaign/keyword
3. AUDIT     Run 6 waste detection rules + funnel allocation analysis
4. REPORT    Generate branded 10-tab Excel workbook
```

### Phase 0: Browser-Based Google Ads Extraction (EXTRACT)

**PARALLEL EXTRACTION (DEFAULT):** When extracting from more than one source or report (Google Ads campaigns, Google Ads search terms, GA4 export, Microsoft Ads, third-party vendor reports), launch one foreground Task agent per source/report in a SINGLE message. Each agent creates its OWN browser tab via `tabs_create_mcp`, extracts its one report, saves its CSV to `01_Inbox/` with the standard filename, and returns `{"source": ..., "file": ..., "rows": N}` or `{"source": ..., "blocked": "<reason>"}` in its final message. A blocked source never halts the others, the main context collects what landed, prints the manual-export instructions only for the sources that failed, and proceeds to ingest with what exists (naming the gaps in the report).

When `--browser` is included OR no Google Ads CSV files are provided, Claude uses the
Chrome MCP tools to extract data directly from the Google Ads UI. This eliminates the
need for the user to manually export CSV files.

**Prerequisites:**
- User must be logged into Google Ads in Chrome
- Claude in Chrome extension must be active

**Extraction Steps (Claude executes these via Chrome MCP):**

1. **Navigate** to `https://ads.google.com` via `navigate` tool
2. **Identify the correct account**: use `javascript_tool` to extract account list if
   multiple accounts are present. Ask user to confirm which account if ambiguous.
3. **Set date range** to the `--period` month (e.g., March 1–31 2026)
4. **Extract Campaign Report:**
   - Navigate to Campaigns tab
   - Use `javascript_tool` to extract the campaign table data (campaign name, status,
     type, spend, impressions, clicks, conversions, conv value, CTR, avg CPC, bid strategy)
   - Save as CSV to `01_Inbox/{client_slug}_campaigns_{period}.csv`
5. **Extract Search Terms Report:**
   - Navigate to Insights & Reports > Search Terms (or Keywords > Search Terms)
   - Use `javascript_tool` to extract the search terms table (search term, match type,
     clicks, impressions, CTR, avg CPC, cost, conversions, conv rate)
   - Save as CSV to `01_Inbox/{client_slug}_search_terms_{period}.csv`
6. **Proceed to Phase 1** with the extracted files as `--source googleads` inputs

**Fallback:** If browser extraction fails (auth issues, UI changes, etc.), print the
exact manual export instructions and ask the user to drop the files in `01_Inbox/`.

**Manual export instructions (fallback):**
```
Google Ads → Campaigns tab → set date range → Download icon (⬇️) → CSV
Columns needed: Campaign, Campaign status, Campaign type, Clicks, Impressions,
Cost, Conversions, Conv. value, CTR, Avg. CPC, Bid strategy type

Google Ads → Keywords → Search Terms → set date range → Download icon (⬇️) → CSV
Columns needed: Search term, Match type, Clicks, Impressions, CTR, Avg. CPC,
Cost, Conversions, Conv. rate
```

### How to Run

When this skill is invoked, run the pipeline via:

```bash
python3 /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/dealership-paid-media-audit/scripts/run_audit.py \
  --client "<client_name>" \
  --source <source> --file <filepath> \
  --period <YYYY-MM> \
  [--compare-prior]
```

For multiple sources, repeat `--source` and `--file` flags in matching order.

### Deduplication: Campaign + Search Term Overlap

When both a campaign-level report AND a search-term report are provided from the same
ad platform (Google Ads, Meta, Microsoft), the engine automatically:

1. **Uses campaign-level rows as source of truth** for spend, conversions, impressions
2. **Zeros out spend on search-term rows** to prevent double-counting
3. **Preserves search-term text** for bleed analysis (Rule 4) using original values
4. **Filters out removed/paused $0 campaigns** from ad platforms
5. **Falls back to campaign "Conversions" field** for `leads_total` when individual
   lead components (form fills, calls) aren't broken out

This means you can safely feed both exports and the engine will sort it out.

### Input

Files should be in `01_Inbox/` (check there first). Accepts CSV and Excel (.xlsx) files.

| Platform | Expected export |
|---|---|
| Google Ads | Campaign report + search terms report (both recommended, engine deduplicates) |
| Meta Ads | Ads Manager export |
| Microsoft Ads | Standard export |
| GA4 | **Explore report export**: Landing Page + Source/Medium + Events (specific template, see below) |
| Third-party | Dealer.com, Sincro, AutoTrader, Cars.com, etc. |
| OEM | NNAnet, Stellantis Dealer Connect, BMW CenterNet co-op reports |
| CRM | **Ingested but NOT cross-matched** (methodology TBD) |

### GA4 Export Template

The GA4 ingest expects a specific Explore report format:
1. Open GA4 > Explore > Free Form
2. **Rows:** Landing page, Session source/medium
3. **Values:** Sessions, Engaged sessions, Event count, Conversions/Key events
4. Add VDP view, form submit, and call events as metrics if available
5. Export as CSV

The ingest validates required columns and fails gracefully with setup instructions if the export doesn't match.

### CRM Source: NOT YET CROSS-MATCHED

The `--source crm` flag ingests CRM data (VinSolutions, Elead, DealerSocket) but does **not** perform cross-source matching to ad campaigns. CRM data appears in the Raw Data tab only.

Cross-source matching (for true CPS and PVR calculations) requires further discussion on:
- Join key methodology (UTM parameters vs phone number vs timestamp proximity)
- Walk-in traffic attribution handling
- Confidence thresholds for fuzzy matches

### Output

Branded Excel workbook saved to `outputs/`:
```
outputs/{client_slug}_paid-media-audit_{YYYY-MM}.xlsx
```

### Excel Tabs

1. **Cover / Read Me**: Client info, data sources, benchmark sources, disclaimer
2. **Executive Summary**: Total spend, leads, CPL, waste %, top 3 discussion topics
3. **Waste Audit**: Line-by-line flagged items with severity and waste amount
4. **Funnel Allocation**: Spend by funnel stage vs. industry-typical ranges
5. **Source Performance**: Per-platform breakdown
6. **Vendor ROI**: CPL by vendor with benchmark comparison
7. **Funnel KPI Detail**: VDP views, form fills, calls, VDP-to-lead %
8. **Suggestions**: Prioritized discussion items (observation / worth discussing / context needed / risk)
9. **Delta vs. Prior**: MoM changes (only with `--compare-prior`)
10. **Raw Data**: Cleaned source data for auditability

Every visible tab (all 10) opens with the Design-System §4 rows-1-2 masthead: Digital Blue band across the used columns, white knockout logo anchored A1 (~0.35in), sheet title in white Dosis 14 Bold, report date right-aligned. Content starts at row 3 or below; tabular tabs freeze panes just under their header row. Palette, fonts, header rows, and alternating White/Callout-Tint body rows are token-compliant everywhere.

### Waste Rules Applied

1. **Zero-conversion spend**: Campaigns with spend above threshold and zero leads
2. **Low VDP-to-lead**: High VDP traffic but poor conversion (threshold varies by brand tier)
3. **High-spend/low-return**: Top 20% spend, bottom 30% CPL
4. **Search term bleed**: Irrelevant queries consuming budget
5. **Geo waste**: Spend outside market radius with no conversions
6. **Device/hour waste**: Disproportionate spend-to-conversion ratios

### Brand Tier Benchmarks

Auto-detected from client name. Uses NADA/Cox/J.D. Power benchmarks:
- **Luxury** (BMW, Mercedes, Audi, Lexus). CPL ceiling ~$85
- **Mainstream Import** (Toyota, Honda, Nissan, Hyundai, Kia). CPL ceiling ~$55
- **Domestic Truck/SUV** (Ford, Chevy, RAM, Jeep). CPL ceiling ~$65
- **Domestic Car** (Chrysler, Dodge, Buick). CPL ceiling ~$45

Benchmarks stored in `config/ltv_benchmarks.json` with source attribution. Flagged if >12 months old.

### Suggestion Tone

Every suggestion follows a strict format:
- **Observation:** What the data shows
- **Worth discussing:** Possible action framed as a question
- **Context needed:** What the GM/GSM knows that data doesn't
- **Potential risk:** What could go wrong without discussion

Never outputs "you should" or "reallocate X to Y." Always framed as discussion starters.

### Ad and Landing-Page Compliance Cross-Check (not a waste rule, added 2026-10-08)

Paid search, Performance Max, and paid social ads that state a price, payment, or savings figure are dealer advertisements under the FTC's September 2026 Pricing Transparency FAQs (Q3), and the dealer, the agency, and the platform share responsibility for the price shown (Q12). While reading the ad-copy and landing-page exports:

- A price, payment, or "save $X" in headline, description, sitelink, or asset text must match the landing page and VDP (FTC FAQ Q12; CA price parity). A mismatch is a **Potential risk** row in Suggestions, never silently fixed.
- A landing page where MSRP, a payment, or a conditional price is bigger or higher than the actual price, or where the price is gated behind a "Get ePrice" or "Unlock" CTA, goes to `/brand-check` (its FTC Pricing Transparency overlay) and is named in the Executive Summary as a compliance item, not a waste item.
- Ad copy that quotes a doc-fee-excluded price, a finance-conditioned price, or "$0 due at signing" with a fee due is flagged the same way (FTC FAQ Q5, Q6, Q8).
- AI-generated ad assets (Performance Max image or text generation) carry the same duty; note any asset the platform generated that misstates a unit, price, or availability (FTC staff remarks 2026-09-30).

Source and detail: `Resources/automotive-guidelines/ftc-advertising-compliance.md`. Keep the tone of the Suggestion format: observation, worth discussing, context needed, potential risk.

### Delta Tracking

Each run is saved to `runs/{client_slug}_{period}.json`. When `--compare-prior` is used, the most recent prior-period file is loaded for MoM comparison.

## File Structure

```
.claude/skills/dealership-paid-media-audit/
  SKILL.md                          # This file
  config/
    ltv_benchmarks.json             # NADA/brand-tier LTV benchmarks
    column_mappings.json            # Per-source column name mappings
    waste_thresholds.json           # Configurable waste detection thresholds
  scripts/
    run_audit.py                    # Main CLI entry point
    ingest.py                       # Unified ingest module (all sources)
    classify_funnel.py              # Funnel stage classifier
    audit_engine.py                 # Waste audit rules + analysis
    report_builder.py               # Branded Excel generator
  runs/                             # Prior-period snapshots for delta tracking
```


## Self-Validation (MANDATORY: final step before reporting success)

After the deliverable is generated, run the shared post-flight validator on the final file. This step is not optional and runs on every invocation:

```bash
python3 /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/post_flight.py \
  "<final output path>" --min-sheets 5
```

It verifies four things and exits non-zero if any fail:
1. **Branding**: the DigitalCLIQ logo is actually embedded in the file (an image in xl/media inside the workbook). A bare Digital Blue masthead with no logo image is a FAILURE, not a fallback.
2. **Location**: the file is inside `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/`. Anywhere else (especially the Desktop) fails.
3. **Sheet count**: at least 5 sheets; fewer means a section silently failed or the report is truncated.
4. **No placeholder data**: template tokens like `{dealer_name}`, literal `YYYY-MM-DD`, "PLACEHOLDER", or lorem ipsum anywhere in the deliverable fail.

**On failure: retry once with a fallback, then fail loudly:**
1. Diagnose from the validator output. Common fixes: the logo must load from the canonical path `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png`; a file saved outside `outputs/` must be moved there and re-validated; a placeholder hit means a data section came back empty, re-fetch that data, do not paper over it.
2. Regenerate the deliverable ONCE and re-run the validator.
3. If it still fails: STOP. Show the user the validator output verbatim and state that the report FAILED validation. Never report success, never present the file as the final deliverable, and never wrap this step in try/except or `|| true` that hides the failure.


## Final QA Gate: deliverable-reviewer agent (MANDATORY, added 2026-08-13)

Runs AFTER the deliverable is generated and post_flight.py passes, BEFORE filing/presenting. post_flight.py is mechanical; this gate is the human-style read.

1. **Write a facts manifest** next to the deliverable in `outputs/`: a JSON list of every number, name, date, and claim that appears in the deliverable, each as `{"value": ..., "label": "where it appears", "source": "tool/file/URL it came from"}`. Build it from data already in context, never re-fetch anything just for the manifest.
2. **Spawn the `deliverable-reviewer` agent** (fresh eyes, it did not write the report). Pass in the prompt: the absolute path(s) of the finished deliverable file(s), the manifest path, and any skill-specific checks from this SKILL.md. It renders every page, reads them all, cross-checks figures against the manifest, and reviews tone/copy.
3. **Auto-fix every finding** in the source generator or data (never by hand-editing the output), re-render, and re-run the agent once. Max 2 review passes. If CRITICAL or MAJOR findings remain after pass 2, the ship is BLOCKED: report the remaining findings to Drew verbatim instead of presenting the file as done.
4. The run summary MUST include a **QA line**: what the reviewer caught and what was fixed, or "QA: clean on first pass (N pages read, M figures verified)". Never silently skip the gate; if the agent could not run, say so explicitly in the delivery message.
