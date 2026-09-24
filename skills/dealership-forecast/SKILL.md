---
name: dealership-forecast
description: Run DigitalCLIQ's dealership lead forecasting and budget optimization pipeline. Analyzes CRM lead data + marketing budgets, builds 3-model ensemble forecast, generates branded Excel report with vendor ROI, reallocation strategy, and scenario planning.
argument-hint: [path-to-data-folder (optional, defaults to 01_Inbox)]
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Task
---

> [!important] Pre-flight: load the facts ledger FIRST
> Before doing anything else, read `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Context/vault-facts.md` and obey it. It is the source of truth for: output location (always the vault `outputs/` folder, never the Desktop or the input file's directory), the canonical working folder (the vault root, never an old/legacy folder), the DigitalCLIQ Master calendar, the canonical logo path, and correct client/competitor names (e.g. "BMW of Buena Park (AutoNation)" not "Shelly BMW"; LOGO Cargo is a hostile competitor, not an Atlas partner). Validate every output path and every client/competitor name against the ledger before writing. If a fact you need is missing from the ledger, do not guess: check the vault and flag it.

# DigitalCLIQ Dealership Forecast Tool

You are running DigitalCLIQ's dealership lead forecasting pipeline.

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

## Defaults

- **Input folder**: `$ARGUMENTS` if provided, otherwise `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/01_Inbox/`
- **Output folder**: `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/`
- **Script**: `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/dealership-forecast/dealership_forecast.py`

## Step 1: Install Dependencies (first run only)

```bash
pip3 install openpyxl pandas numpy scipy --break-system-packages --quiet
```

Prophet and statsmodels are optional, install only if monthly data exists:
```bash
pip3 install prophet statsmodels scikit-learn --break-system-packages --quiet
```

## Step 2: Scan Input Folder

Scan the input folder for CSV and Excel files. Show the user what you found.

Run the script in detect mode:
```bash
python3 "<script_path>" detect "<input_folder>"
```

This outputs a JSON summary: CRM type, detected dealership name, column mapping, file list, and any issues.

## Parallel Multi-Dealership Runs (DEFAULT for 2+ dealerships)

When the input folder contains data for more than one dealership, launch one foreground Task agent per dealership in a SINGLE message after the checkpoints below are resolved. Each agent runs the full pipeline for its dealership (ingest → forecast → Excel → post-flight validation) and returns the output path and validation result as JSON. The main context reports all forecasts together. One dealership's malformed CSV never blocks the others, its failure is reported per-store with the exact missing column or parse error.

## Step 3: Interactive Checkpoints

CRITICAL: The skill must STOP and confirm with the user at each checkpoint. Do NOT run the full pipeline without confirmation. If something looks wrong, ask, don't guess and generate a bad report.

### Checkpoint 1: CRM & Dealership
Show the detected CRM format and dealership name. Ask:
- "I detected [CRM] format. This looks like data for [Dealership]. Is that correct?"
- If dealership can't be detected: "What dealership is this data for?"

### Checkpoint 2: Date Range
- If date range can't be detected from filenames or headers: "What date range does this data cover? (e.g., Jan 2024 - Dec 2025)"

### Checkpoint 3: Month Mapping (monthly files only)
- If multiple files found: show month-to-file mapping, ask user to confirm

### Checkpoint 4: Artifact Sources
After parsing, show any sources with close rate > 20%. Ask:
- "These sources have unusually high close rates. Are they real marketing sources, or operational artifacts (walk-ins, service-to-sales, DMS imports, repeat customers)?"
- Common artifacts: Service Dept, Previous Customer, Repeat Customer, Referral (Walk-In), Location, Dealer Mgmt Sys, Fresh Up, Lease Return

### Checkpoint 5: Budget Data
If no cost data found in the CRM files:
- "No cost/spend data found in the CRM export. Do you have a budget spreadsheet (CSV, Excel, or PDF) I should use? If not, I'll build the report without cost-based ROI, just lead performance."

## Step 4: Run the Pipeline

Once all checkpoints are confirmed, write a config JSON and run:
```bash
python3 "<script_path>" build "<config_path>"
```

Config JSON format:
```json
{
  "dealership": "Nissan of Irvine",
  "date_start": "2024-01-01",
  "date_end": "2025-12-31",
  "crm": "vinsolutions",
  "input_files": ["01_Inbox/file1.csv"],
  "budget_file": null,
  "exclude_sources": ["Service", "Dealer Mgmt Sys"],
  "output_path": "outputs/NissanOfIrvine_DigitalCLIQ_Forecast.xlsx",
  "monthly_data": false
}
```

## Step 5: Report Results

Show a brief summary:
- Dealership name and date range
- CRM format detected
- Total good leads and sales
- Top 5 vendors by volume
- Close rate range
- Artifact sources excluded
- File path to the output workbook

Keep the summary short: the Excel file is the deliverable.

---

## CRM Format & Vendor Rollup Reference

Detect the CRM from the file headers, then read ONLY that CRM's row in
`references/crm-formats-and-vendor-rollup.md` (a comparison table covering detection,
structure, Good Leads / Sales / cost columns, number formats, and per-CRM caveats). The
same file holds the vendor rollup keyword map, artifact detection rules, and the Vendor
Matching Loop (MATCHED / POSSIBLE / UNMATCHED): run that loop until every budget line is
MATCHED or UNMEASURED before running CPL/CPS calculations.


---

## ROI Calculations

### Close Rate
`Close Rate = Sales / Good Leads`

Use Good Leads as denominator across all CRMs (per-CRM Good Leads column: see the Good Leads column of the table in `references/crm-formats-and-vendor-rollup.md`).

### Cost Per Lead / Cost Per Sale
Only calculated when cost data is available (from CRM or budget file):
- `CPL = Total Cost / Good Leads`
- `CPS = Total Cost / Sales`

### Efficiency Tiering (based on CPS when available, otherwise close rate)

**When cost data available (CPS-based):**

| Tier | CPS Range | Label | Action |
|------|-----------|-------|--------|
| TIER 1 | < $500 | STAR | Invest more |
| TIER 2 | $500-$999 | GOOD | Maintain or grow |
| TIER 3 | $1,000-$1,499 | AVG | Monitor |
| TIER 4 | >= $1,500 | REVIEW | Cut or restructure |
| UNMEASURED | No cost data | ? | Require attribution proof |

**When no cost data (close-rate-based fallback):**

| Tier | Close Rate | Label | Action |
|------|-----------|-------|--------|
| TIER 1 | >= 8% | STAR | Strong converter |
| TIER 2 | 5-7.99% | GOOD | Solid performer |
| TIER 3 | 2-4.99% | AVG | Monitor |
| TIER 4 | < 2% | REVIEW | Underperforming |
| UNMEASURED | 0 sales | ? | No conversions tracked |

### Gross Profit ROI (when available)
VinSolutions and DealerSocket provide gross profit data. When present, also calculate:
- `Profit ROI = (Total Gross - Total Cost) / Total Cost` (percentage return)
- `Avg Gross Per Sale` = Total Gross / Sales
- Include in Vendor ROI tab as additional columns

---

## Forecasting

### When Monthly Data Is Available (12+ monthly files)

Run 3-model ensemble:

**Model 1: Prophet**
```python
from prophet import Prophet
model = Prophet(
    yearly_seasonality=(True if months >= 24 else False),
    weekly_seasonality=False, daily_seasonality=False,
    changepoint_prior_scale=0.05,
    seasonality_mode='multiplicative', interval_width=0.80
)
```

**Model 2: Holt-Winters**
```python
from statsmodels.tsa.holtwinters import ExponentialSmoothing
model = ExponentialSmoothing(
    data, seasonal_periods=12,
    trend='add', seasonal='mul', damped_trend=True
)
```

**Model 3: NADA Seasonal Benchmark**
```python
nada_seasonal = {
    1: 0.88, 2: 0.94, 3: 1.08, 4: 1.04, 5: 1.02, 6: 1.00,
    7: 0.96, 8: 1.03, 9: 1.02, 10: 1.05, 11: 0.98, 12: 1.00
}
```

**Ensemble Weights:**
- 24+ months: Prophet 25%, Holt-Winters 40%, NADA 35%
- 12 months: Prophet 15%, Holt-Winters 25%, NADA 60%

### When Only Aggregate Data (no monthly breakdown)

Skip Prophet and Holt-Winters. Use NADA seasonal projection only:
- Monthly estimate = (Annual Good Leads / 12) x NADA seasonal index x YoY growth rate
- Label as "Seasonal Projection" not "Ensemble Forecast"
- Note: "Full 3-model forecast requires monthly data exports"

### Model Confidence Check

After building the ensemble, before generating scenarios:

1. Check if any single model's 12-month forecast differs from the ensemble mean by >20%.
2. If yes, surface the divergence: "Prophet is forecasting 22% above the ensemble. This usually means it detected a trend the other models don't see. Options: (a) accept current weights, (b) adjust weights, (c) investigate the driver."
3. Rebuild ensemble if weights change. Do not proceed to scenario generation until the user accepts the ensemble.

---

### Budget Scenarios (when cost data available)

- Baseline (status quo)
- +25% budget: baseline x (1 + 0.25 x elasticity)
- -15% budget: baseline x (1 - 0.15 x elasticity)
- 80% confidence intervals: forecast x 0.88 to forecast x 1.12

---

## Reallocation Strategy (when cost data available)

Build a budget-neutral reallocation proposal:

1. Identify Tier 4 and UNMEASURED vendors → propose CUTS (reduce, don't eliminate)
2. Identify Tier 1/2 vendors → propose INVESTMENTS with freed-up dollars
3. Project impact: additional leads = $reinvested / vendor CPL, additional sales = additional leads x vendor close rate
4. Lost leads/sales from cuts using the same method
5. Verify total proposed spend = total current spend (budget neutral)

When no cost data: skip reallocation tab entirely. Note in Executive Summary: "Budget reallocation analysis requires cost/spend data."

---

## Excel Workbook Specification

Generate an .xlsx workbook with up to 8 tabs. Tabs requiring cost data are omitted when no cost data is available.

### DigitalCLIQ Brand Colors (Design-System tokens only)

```python
DC_BLUE = '405FAB'      # Digital Blue — mastheads, header rows, emphasis
DC_SKY = '6B9DD4'       # Sky Blue — strong/Tier 1 treatment, accents
DC_BLACK = '000000'
DC_WHITE = 'FFFFFF'
DC_GREY = '949592'      # Warm Grey — weak/Tier 4/UNMEASURED treatment, muted labels
DC_LIGHT_BG = 'EDF2F9'  # Callout Tint — alternating body rows, input-cell fills
DC_CARD = 'FBFBFD'      # Card White
DC_ACCENT = '2E4780'    # Tile Blue — totals rows, deep accents
DC_BORDER = 'D8E1F0'    # thin cell borders
```

No color outside this token set (see the Design System section above). Never generic greens/reds/oranges/yellows for tiers, the Tier and Rating TEXT labels (TIER 1/STAR ... TIER 4/REVIEW, UNMEASURED/?) carry the meaning; fills are palette treatments only (Sky Blue = strong, Warm Grey = weak).

Fonts: Dosis (headings, titles, header rows, stat numbers), Roboto Slab (body cells). Fallback stacks may follow the brand font, never lead with Arial/Calibri.
Company: "DigitalCLIQ" (one word, CLIQ capitalized)
Tagline: "Digital Strategy & Development"

Per Design-System §4 (Excel): every visible sheet gets a rows 1-2 Digital Blue masthead with the WHITE logo anchored A1, Digital Blue header row in white Dosis (frozen), alternating White / Callout Tint body rows with thin `#D8E1F0` borders, and a styled Summary-style first tab. Charts use palette colors only.

`dealership_forecast.py` implements this on every tab (retrofit completed 2026-07-18). Shared layout: rows 1-2 masthead (Digital Blue band, white knockout logo anchored A1 at ~0.35in true aspect, sheet title in white Dosis 14 Bold merged from column C, report date right-aligned in a merged block at the band's right edge), row 3 spacer or caveat note, row 4 column header, data from row 5, `freeze_panes = A5`. All row-referenced formulas (Close Rate `=IF(C{r}>0,...)`, totals, Forecast `=SUM(B5:B16)`) are generated against this layout; if you shift any tab's rows again, shift every dependent formula with it.

### Tab 1: Executive Summary
- Tab color: DC_BLUE
- Title: "[Dealership Name], Marketing & Lead Forecast"
- Subtitle: date range, data source (CRM name), analysis type
- "Prepared by DigitalCLIQ | Digital Strategy & Development"
- KPI table with available metrics (adapts to what data exists)
- Key finding callout
- Data caveat notes (e.g., "Sales metric: Sold In Time Period (Tekion)")

### Tab 2: Monthly History (only if monthly data)
- Tab color: DC_SKY
- Columns adapt to available data

### Tab 3: Vendor ROI
- Tab color: DC_SKY
- Note about excluded artifacts
- Columns: Tier, Vendor, Good Leads, Sales, Close Rate, + Cost/CPL/CPS/Gross if available
- Sky Blue fill for Tier 1, Warm Grey fill for Tier 4 and UNMEASURED; the Tier and Rating text columns always carry the meaning, never fill color alone
- Sort by CPS ascending (or close rate descending if no cost data)

### Tab 4: Forecast (only if monthly data OR NADA projection)
- Tab color: DC_SKY
- Adapts to ensemble vs NADA-only

### Tab 5: Scenario Planner (only if cost data)
- Tab color: DC_BLUE
- Input cells: Digital Blue font, Callout Tint (`EDF2F9`) background, Digital Blue border
- ALL calculations as Excel formulas

### Tab 6: Budget Detail (only if budget file provided)
- Tab color: DC_GREY

### Tab 7: All Providers
- Tab color: DC_ACCENT
- Every source from the CRM, ungrouped, sorted by lead volume
- Shows original source names before rollup

### Tab 8: Reallocation Strategy (only if cost data)
- Tab color: DC_ACCENT (Tile Blue)

### CRITICAL Excel Rules

1. Use FORMULAS for all calculations: never hardcode
2. Division formulas need zero-protection: `=IF(D{row}>0,B{row}/D{row},"-")`
3. Alternating rows use DC_LIGHT_BG (Callout Tint `EDF2F9`) fill
4. All cells get thin `#D8E1F0` borders (no default grid look)
5. Set column widths for readability
6. Validate after saving: `python3 -c "import openpyxl; wb=openpyxl.load_workbook('file.xlsx'); [print(f'{ws.title}: OK') for ws in wb.worksheets]"`

## Output

Save to: `<output_folder>/[DealershipName]_DigitalCLIQ_Forecast.xlsx`


## Self-Validation (MANDATORY: final step before reporting success)

After the deliverable is generated, run the shared post-flight validator on the final file. This step is not optional and runs on every invocation:

```bash
python3 /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/post_flight.py \
  "<final output path>" --min-sheets 3
```

It verifies four things and exits non-zero if any fail:
1. **Branding**: the DigitalCLIQ logo is actually embedded in the file (an image in xl/media inside the workbook). A masthead band with no logo image is a FAILURE, not a fallback.
2. **Location**: the file is inside `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/`. Anywhere else (especially the Desktop) fails.
3. **Sheet count**: at least 3 sheets; fewer means a section silently failed or the report is truncated.
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
