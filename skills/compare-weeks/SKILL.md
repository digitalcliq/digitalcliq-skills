---
name: compare-weeks
description: Compare two weekly CRM lead reports side by side, layer in live GA4 website analytics, and generate a branded DigitalCLIQ PDF showing what changed, why, and what to do next. Use when Drew says /compare-weeks, "compare weeks", "week over week", "compare the last two CRM/lead reports", "what changed since last week", or drops two weekly lead CSVs in 01_Inbox.
argument-hint: (no arguments — auto-detects two CSV files in 01_Inbox)
allowed-tools: Read, Write, Glob, Grep, Bash(python3 *), Bash(pip3 install *), WebSearch, mcp__claude-in-chrome__tabs_context_mcp, mcp__claude-in-chrome__tabs_create_mcp, mcp__claude-in-chrome__navigate, mcp__claude-in-chrome__read_page, mcp__claude-in-chrome__get_page_text, mcp__claude-in-chrome__find, mcp__claude-in-chrome__computer, mcp__claude-in-chrome__javascript_tool, mcp__claude-in-chrome__form_input, Task
---

> [!important] Pre-flight: load the facts ledger FIRST
> Before doing anything else, read `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Context/vault-facts.md` and obey it. It is the source of truth for: output location (always the vault `outputs/` folder, never the Desktop or the input file's directory), the canonical working folder (the vault root, never an old/legacy folder), the DigitalCLIQ Master calendar, the canonical logo path, and correct client/competitor names (e.g. "BMW of Buena Park (AutoNation)" not "Shelly BMW"; LOGO Cargo is a hostile competitor, not an Atlas partner). Validate every output path and every client/competitor name against the ledger before writing. If a fact you need is missing from the ledger, do not guess: check the vault and flag it.

# Compare Weeks: Weekly CRM Lead Comparison + GA4 Overlay

Compare two weekly CRM lead exports side by side, overlay Google Analytics 4 website data for the same period, and produce a branded DigitalCLIQ PDF report showing changes, insights, and recommendations.

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

## Client Dealerships and CRMs

| Dealership | CRM | GA4 Property |
|---|---|---|
| **Sterling BMW** | **MomentumCRM** | sterlingbmw.com |
| **Nissan of Irvine** | **VinSolutions** | nissanofirvine.com |
| **McPeek CDJR** | **Tekion** | mcpeeksdodgeanaheim.com |
| **J Star CDJR** | **DealerSocket** | jstarcdjrofanaheim.com |

## Process

### Step 0: Resolve Input Files

Look in `01_Inbox/` for exactly two CSV files that appear to be weekly CRM lead exports.

1. Glob `01_Inbox/*.csv` for matching files
2. Sort by date range in filename to identify Week 1 (earlier) and Week 2 (later)
3. Auto-detect the CRM format (Tekion, VinSolutions, MomentumCRM, DealerSocket) from column headers
4. Auto-detect the dealership from filenames or data content
5. If not exactly 2 CSVs found, ask the user which files to compare

### Parallel Execution (DEFAULT)

Steps 1 and 2 run CONCURRENTLY, not in sequence. As soon as Step 0 identifies the dealership, launch a foreground Task agent to pull GA4 (Step 2's playbook: own browser tab via `tabs_create_mcp`, navigate the property, extract both weeks' metrics, return structured JSON). While that agent works, the main context parses and compares the two CRM files (Step 1). Merge when both finish, then proceed to Step 3. If the GA4 agent hits a disconnected Chrome or a login wall, it says so explicitly in its JSON (`"ga4_available": false` with the reason), the report proceeds without GA4 but NEVER silently; the gap is named in the PDF and in the summary to the user.

### Step 1: Parse & Compare CRM Data

Read both CSV files. For each, extract:
- Total Leads, Bad Leads, Duplicate Leads, Good Leads
- Sold count and Sale Rate
- Engagement %, Appointment %, Show Rate
- Per-source breakdown (by Lead Source Group + Source Name)

Compare Week 1 vs Week 2:
- Overall totals with deltas and % change
- Top 5-8 movers (biggest positive and negative changes)
- Source-by-source full comparison table
- BDC performance metrics (outreach volume, engagement, appointments)

### Step 2: Pull GA4 Website Data

Open the dealership's GA4 property in Chrome browser:
1. Navigate to Traffic Acquisition report
2. Set date range to match the CSV period (both weeks combined)
3. Extract channel-level data: Sessions, Engaged Sessions, Engagement Rate, Avg Engagement Time, Key Events
4. Navigate to Landing Page report
5. Extract top landing pages with engagement metrics
6. Note any anomalies: low engagement times, (not set) pages, high bounce channels

### Step 3: Generate Analysis

Combine CRM + GA4 data to produce:
1. **Executive Summary**: 3-4 bullet overview of what happened
2. **Key Movers**: Sources with biggest changes, with possible explanations
3. **GA4 Website Layer**: Traffic trends, channel health, landing page issues
4. **BDC Performance**: Outreach and response metrics comparison
5. **Concerns & Red Flags**: Things that need attention
6. **Strategic Recommendations**: High-level next steps

### Step 4: Generate Branded PDF

Run `python3 compare_weeks.py` with the analysis data embedded (JSON file argument or stdin). The script lives at:
```
/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/compare-weeks/compare_weeks.py
```

The generator is the design-system HTML pipeline: it builds the report as HTML + CSS from the canonical component library (cover per `templates/cover-portrait.html`, stat cards, callout bars, branded tables, numbered list cards, running furniture, tokens.css colors only), embeds Dosis and Roboto Slab via `@font-face` from `Resources/brand-assets/fonts/`, and renders via WeasyPrint when importable, else Chrome headless `--print-to-pdf` (the sanctioned fallback). Missing fonts or logos fail loudly. Long tables paginate automatically with repeated headers and a "table continued" label.

Output goes to:
```
/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/
```

Filename format: `{Dealership}_Weekly_Comparison_{Week1Start}-{Week2End}.pdf`

Then run the Visual-QA render gate (see the Design System section above): `python3 Resources/design-system/templates/render_check.py <pdf>`, read every rendered page, fix defects in `compare_weeks.py`, and repeat until two consecutive clean passes.

### Step 5: Confirm

Tell the user the PDF path and summarize the key findings.


## Self-Validation (MANDATORY: final step before reporting success)

After the deliverable is generated, run the shared post-flight validator on the final file. This step is not optional and runs on every invocation:

```bash
python3 /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/post_flight.py \
  "<final output path>" --min-pages 3
```

It verifies four things and exits non-zero if any fail:
1. **Branding**: the DigitalCLIQ logo is actually embedded in the file (image objects present on every PDF page). A black tile with no logo image is a FAILURE, not a fallback.
2. **Location**: the file is inside `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/`. Anywhere else (especially the Desktop) fails.
3. **Page count**: at least 3 pages; fewer means a section silently failed or the report is truncated.
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
