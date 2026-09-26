---
name: dealership-forecast-tool
description: Forecast a dealership's leads and sales 6 to 12 months out and model budget scenarios (more or less spend, reallocation), with vendor cost per lead and cost per sale when a marketing budget or spend file is supplied. Use for /dealership-forecast-tool, "forecast leads", "H2 forecast", "what if we cut or increase budget", "reallocate budget". Not for scoring lead sources from a CRM export alone (score-leads), week-over-week lead comparisons (compare-weeks), monthly performance reports (monthly-client-report), or ad-platform waste audits (dealership-paid-media-audit).
---

# DigitalCLIQ Dealership Forecast Tool

Turns a store's monthly CRM lead reports and marketing budget into a lead and sales forecast, budget scenarios, vendor cost per sale and a budget-neutral reallocation, delivered as a DigitalCLIQ-branded Excel workbook written for the GM / GSM / owner.

**Paths.** This skill's scripts are `"${CLAUDE_SKILL_DIR}/scripts/<file>"` (always double-quoted). If ${CLAUDE_SKILL_DIR} did not expand, use the Base directory printed when this skill loaded. The vault root is `"/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ"` on the Mac (always double-quote it; the path has spaces) or the connected DigitalCLIQ Brain HQ folder in Cowork. `Resources/`, `Context/`, `outputs/` and `Projects/` below are relative to the vault root; run the commands from there. `<deliverable>` means `DigitalCLIQ_{CODE}_Lead_Forecast_{YYYY-MM-DD}`.

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

### Skill-specific design notes (outside the canonical block)

- Workbook styling, masthead code, tier treatments and formula patterns live in `references/excel_template.md`. Fonts are Dosis and Roboto Slab only, every fill comes from the palette, and the Tier text carries the meaning.
- Every tab gets the Digital Blue masthead with the WHITE logo. If the logo file does not load, stop the build and tell Drew; there is no logo-less fallback.
- Titles use a colon, never a dash: "Vendor ROI Analysis: 2025 Spend vs Lead Performance". No em dashes in any cell, title or note.
- Render gate for this workbook: the xlsx PIL preview draws formula text, not values, so it is a layout check only. Numbers are checked by `verify_workbook.py` against the facts file. In Cowork the render gate is a LibreOffice PDF export of the recalculated workbook (`soffice --headless --convert-to pdf`), then read every page image. On the Mac, `render_check.py` exports through Microsoft Excel and has hung on workbooks before; if it hangs, say so in the delivery message rather than skipping the gate silently.

## When to Use This Skill

- Drew wants leads or sales forecast 6 to 12 months out for one store ("forecast SBMW leads for Q4", "H2 forecast").
- Drew wants to know what more or less budget would do ("what if we cut AutoTrader 50%", "+25% budget").
- Drew wants a budget-neutral reallocation across vendors, with cost per lead and cost per sale from a budget or spend file.

Not this skill: scoring sources from a CRM export alone (score-leads), week-over-week comparisons (compare-weeks), the monthly GM report (monthly-client-report), ad-platform waste (dealership-paid-media-audit).

## Step 0: Preflight (stop early on the wrong machine)

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/preflight.py" --vault "<vault root>"
```

- Exit 0: prints the recalc command to use. Continue.
- Exit 2: this machine cannot run the models or the recalc (Python older than 3.10, or no LibreOffice). This is the normal result on Drew's Mac. **Stop and tell Drew to run this skill in Cowork.** Do not pip install here, do not improvise models in plain Python, do not skip the recalc.
- Exit 3: a capable machine missing packages. Run the printed install line (Cowork only), then re-run the preflight.
- Exit 4: the vault, the white logo or `outputs/` is not reachable. Stop; a missing logo stops the build.
- Exit 5: a capable machine where the installed xlsx skill's `scripts/recalc.py` was not found. Locate it, `export XLSX_RECALC="/full/path/to/xlsx/scripts/recalc.py"`, and re-run the preflight. The preflight also honors `XLSX_RECALC` whenever it is set. Do not skip the recalc.

Then read, in addition to the design-system files above (`Resources/design-system/Design-System.md` now, `Resources/design-system/Visual-QA.md` before the render gate), only these: the Branding and render-gate sections of `Context/vault-facts.md`, `Projects/README.md` for the client code, and `Projects/{CODE}/README.md` before naming anyone (contacts never cross clients). The workbook is written for the GM / GSM / owner.

## Required Inputs

Ask for anything missing before starting.

1. **CRM lead reports**, one per month, ideally 24 months (12 minimum). Columns per `references/data_ingestion.md`. Read each report's period start and end dates from its header, or ask Drew for them. Never guess a month from campaign names or file order.
2. **Marketing budget or spend file** with vendor-level monthly spend, for the same months.
3. **The lead definition** Drew wants: which CRM report, which lead column, and which sources are excluded. It is printed on page one and saved with the workbook.

## Pipeline

Follow these steps in order. Do not skip steps.

### Step 1: Ingest and validate
Read `references/data_ingestion.md`. Parse the reports and budget, map each file to its month from the header dates, combine, and check for missing months, zero-lead months and column mismatches. Show Drew the month mapping, the lead definition and the excluded sources, and get a yes before modeling.

Start the facts file now: `outputs/<deliverable>.facts.json` (schema: `references/facts_schema.md`) with `client`, `definitions` and `history`. Each later step adds its block (`sources`, `vendors`, `models`, `forecast`, `elasticity`, `scenarios`, `confirmations`, `manifest`); the scripts below read it.

### Step 2: Explore
Monthly leads, sales and close rate (Sales / Good Leads); provider concentration; duplicate rate; year over year when two years exist; spend-to-lead elasticity from the script (Step 4).

### Step 3: Vendor ROI
Read `references/roi_methodology.md`.
- Run the Vendor Matching Loop in `references/data_ingestion.md` until every budget line is MATCHED or UNMEASURED.
- Ask Drew about every source over 20% close rate whose name looks operational (credit app, walk-in, referral, repeat, DMS, service, showroom). Exclude or confirm each one and record the answer in the facts file.
- Get tiers, ratings, notes, row order and the CUT order from the script, never by hand:
  `python3 "${CLAUDE_SKILL_DIR}/scripts/verify_workbook.py" tiers "outputs/<deliverable>.facts.json"`

### Step 4: Forecast
Read `references/forecasting.md`. Fit Prophet, Holt-Winters and the seasonal prior (a DigitalCLIQ estimate, not NADA data). Keep every model's monthly values. A model that fails to fit is dropped, the other weights are renormalized, and the title names only the models that produced numbers. Elasticity comes from:
`python3 "${CLAUDE_SKILL_DIR}/scripts/verify_workbook.py" elasticity "outputs/<deliverable>.facts.json"`

### Step 5: Model audit (Drew confirms before the build)
`python3 "${CLAUDE_SKILL_DIR}/scripts/verify_workbook.py" audit "outputs/<deliverable>.facts.json"`
It prints each model against the ensemble and the sanity rows: the forecast total against the same months last year and against the flat average. Exit 3 means Drew must confirm: a model more than 20% from the ensemble, a forecast more than 10% from last year or the flat average, or a forecast that reverses last year's direction by more than 5%. Show him the rows, get his answer, record it in `confirmations` in the facts file, and re-run. Do not build until it exits 0.

### Step 6: Reallocation
Budget neutral. Paid lines with leads and zero sales lead the CUT list, then TIER 4 worst first, then UNMEASURED. Project with each vendor's own CPL and close rate. Rules in `references/roi_methodology.md`.

### Step 7: Facts check (mandatory, before the workbook is written)
Complete the facts file so it holds every figure the workbook will show, including the client name, the close-rate basis, every forecast month (`YYYY-MM`) and the reviewer `manifest`; these are the keys the sidecar saves in Step 10. Then:
`python3 "${CLAUDE_SKILL_DIR}/scripts/verify_workbook.py" facts "outputs/<deliverable>.facts.json"`
It stops with a list of failures when any subtotal is not the sum of its rows (spend, leads, sales, unique, dups); a Tier or Rating breaks the tier rules or rows are not sorted by cost per sale; the Executive Summary and Scenario Planner baselines differ; an excluded source sits in an included row; an operational-looking source over 20% close is neither confirmed nor excluded; CTR or CPC is an average of monthly ratios instead of pooled; '(net)' is used without a co-op row; the model title, weights or planning range disagree with the models that ran; the elasticity or its label does not match the history; or the audit still needs Drew. Fix the data, never the check.

### Step 8: Build the workbook
Read `references/excel_template.md`. Eight tabs, in order: Executive Summary, Monthly History (24-Month or 12-Month), Vendor ROI, Forecast, Scenario Planner, Budget Detail, All Providers, Reallocation Strategy. Excel formulas for every derived figure; TOTAL rows are `=SUM()`; Executive Summary KPIs reference the History totals and the Scenario Planner; Tier and Rating are formulas. Page one carries the line `Lead definition: <report> <column>; excludes <sources>; data <start> to <end>.` Save to `outputs/<deliverable>.xlsx`.

### Step 9: Recalc (at most 3 attempts)
Use the installed xlsx skill's `scripts/recalc.py`, run from that skill's `scripts/` folder (the preflight prints the exact command). Fix any error in the generator and recalc again, up to 3 attempts in total. If it still fails or LibreOffice times out a third time, stop and report the recalc output to Drew. Do not loop.

### Step 10: Numbers gate
```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/verify_workbook.py" check "outputs/<deliverable>.xlsx" \
  --facts "outputs/<deliverable>.facts.json" --write-sidecar
```
It recomputes every formula and fails with cell addresses on: a missing tab; a TOTAL cell that is typed (in any column, including formula-only columns such as Planning Low/High, +25% / -15% and Annual Total) or does not sum its rows (Month labels may be text or real Excel dates; a blank spacer row above the TOTAL and a `TOTAL:` label are still checked), and a grand total under other TOTAL rows that does not add them up; a History tab without a `{YEAR} TOTAL` row, or one whose totals differ from `history_totals` in the facts file; a Budget Detail TOTAL that differs from the History spend TOTAL for its year or from `history_totals` (a Budget Detail with no TOTAL row only warns, and its rows are tied out instead); a ratio in an Actual-year column that reads another column; a Tier or Rating that breaks the rules, a missing Tier column, or rows out of cost-per-sale order; Executive Summary, Scenario Planner and Forecast totals that disagree; a reallocation that is not budget neutral; '(net)' without a co-op row; any em dash; an estimate labelled as a statistic (the planning range called a confidence interval, elasticity called measured, the seasonal prior credited to NADA; honest disclaimers such as "not measured" or "not a confidence interval" pass), a sales elasticity row, a missing lead definition line, or a 3-model claim when fewer ran. On a pass it writes `outputs/<deliverable>.forecast.json` (the saved definitions: client, CRM, report, lead column, close-rate basis, exclusions, data window, forecast months with baseline/low/high, interval method, elasticity, the models that ran). Fix failures in the generator and rebuild; never hand-edit the workbook and never ship on exit 1.

### Step 11: Render gate
See the skill-specific design notes above. Read every page.

### Step 12: Self-validation (post_flight)
```bash
python3 "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/post_flight.py" \
  "<vault root>/outputs/<deliverable>.xlsx" --min-sheets 8
```
Checks the embedded logo, the `outputs/` location, 8 sheets and no placeholders; exit 2 on failure. In Cowork, run the same file from the connected vault folder; its location check is keyed to the Mac path, so a location-only failure there is expected: say so, and run post_flight again on the Mac before filing. On any other failure: diagnose, regenerate once, re-run; if it still fails, stop and show Drew the output verbatim.

### Step 13: Final QA gate: deliverable-reviewer agent (mandatory)
Spawn the `deliverable-reviewer` agent with the workbook path and the facts file as the manifest (its `manifest` list holds every client-facing figure as `{value, label, source}`). Tell it: the PIL preview shows formula text, not values; values are checked against the facts file and `verify_workbook.py`; the render gate is the LibreOffice PDF export. Auto-fix findings in the generator, rebuild, re-run steps 9 to 12, max 2 review passes. CRITICAL or MAJOR findings left after pass 2 block the ship: report them to Drew verbatim. If the agent cannot run in this session, say so in the delivery message and ask Drew to run the review from Claude Code before the file goes to a GM. The delivery message carries a QA line.

### Step 14: File
Copy the workbook, its `.forecast.json` sidecar and its `.facts.json` from `outputs/` to `Projects/{CODE}/deliverables/` (Rule 18). Log the run in today's Daily note and the client's context log per the vault conventions.

## Important Notes

- Always confirm the month mapping and the lead definition with Drew before modeling, and ask about operational sources before calculating ROI.
- Estimates are labelled as estimates: "Planning range, not a statistical interval", "Estimated" elasticity with its p value, "Seasonal prior (DigitalCLIQ estimate)", "DigitalCLIQ planning assumption" on the tier cut-offs. Forecasts are labelled as forecasts.
- Every market or benchmark figure needs a named source and publication date, or it does not go in the workbook.
- LotLinx and similar VIN-level ad platforms usually have no CRM leads: UNMEASURED.
- Analyze gross spend. Note OEM co-op reimbursement when a co-op row exists; '(net)' appears only then.
- With only 12 months of data, recommend a second year and explain why (seasonality, trend reliability).

## Dependencies (Cowork only)

```bash
pip install prophet statsmodels openpyxl pandas numpy scipy --break-system-packages   # Cowork only, never on the Mac
```
`verify_workbook.py` and `preflight.py` need only the standard library and openpyxl.

Regression tests for both scripts (for whoever edits them, not part of a run): `python3 "${CLAUDE_SKILL_DIR}/tests/test_forecast.py"`. They build a synthetic "Test Motors" workbook with `tests/build_sample.py` and write only to a temp dir. Real-workbook cases run only when `FORECAST_STERLING_DIR` points at a folder holding a copy of a past forecast (`sterling_orig.xlsx`, `sterling_facts.json`); client files never go into the repo.
