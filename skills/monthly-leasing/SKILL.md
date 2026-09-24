---
name: monthly-leasing
description: Visit dealership websites live via browser, extract new vehicle lease specials by brand, and output a DigitalCLIQ-branded Excel report with per-brand tabs. Covers Nissan, BMW, CDJR, Chevrolet, Lexus, and Ford dealers in Southern California.
argument-hint: <brand(s)> [YYYY-MM] — e.g. "nissan", "cdjr ford", "all-oc-dealers", "2026-03 bmw"
allowed-tools: Read, Write, Bash(python3 *), Bash(pip3 install *), Bash(curl *), ToolSearch, Task, mcp__claude-in-chrome__list_connected_browsers, mcp__claude-in-chrome__select_browser, mcp__claude-in-chrome__tabs_context_mcp, mcp__claude-in-chrome__tabs_create_mcp, mcp__claude-in-chrome__navigate, mcp__claude-in-chrome__read_page, mcp__claude-in-chrome__get_page_text, mcp__claude-in-chrome__find, mcp__claude-in-chrome__computer, mcp__claude-in-chrome__javascript_tool, mcp__claude-in-chrome__form_input, mcp__claude-in-chrome__browser_batch
---

> [!important] Pre-flight: load the facts ledger FIRST
> Before doing anything else, read `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Context/vault-facts.md` and obey it. It is the source of truth for: output location (always the vault `outputs/` folder, never the Desktop or the input file's directory), the canonical working folder (the vault root, never an old/legacy folder), the DigitalCLIQ Master calendar, the canonical logo path, and correct client/competitor names (e.g. "BMW of Buena Park (AutoNation)" not "Shelly BMW"; LOGO Cargo is a hostile competitor, not an Atlas partner). Validate every output path and every client/competitor name against the ledger before writing. If a fact you need is missing from the ledger, do not guess: check the vault and flag it.

# DigitalCLIQ Monthly Lease Specials Tracker

Scrape new vehicle lease specials from dealership websites using the live MCP browser, extract offer data, and produce a branded Excel report with per-brand tabs.

**Developed by DigitalCLIQ**

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

## Data Files

All dealer, model, and alias data lives in a single JSON roster file. **Read this file first before doing anything else:**

```
/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/monthly-leasing/dealer_roster.json
```

This file contains:
- `brands`: each brand has `display_name`, `make`, `models` (model dictionary), and `dealers` (name, URL, county, state)
- `brand_aliases`: maps shorthand names to brand keys (e.g., "chevy" → "chevrolet", "all" → all 6 brands)

## Step 1: Parse Arguments

Parse `$ARGUMENTS` to extract the brand list and optional month.

1. **Month** (optional): If any token matches `YYYY-MM` format, use it as the capture month. Otherwise use the current month.
2. **Brand list** (required): All remaining tokens are brand identifiers.

For each brand token:
- Convert to lowercase
- Check `brand_aliases` first (e.g., `all` → all 6 brands, `chevy` → `chevrolet`, `dodge` → `cdjr`)
- Then check if it matches a key in `brands`
- If unrecognized, tell the user and list valid brand names

The result is an ordered, deduplicated list of brand keys to process.

**Examples:**
- `nissan` → `["nissan"]`
- `cdjr ford` → `["cdjr", "ford"]`
- `all-oc-dealers` → `["nissan", "bmw", "cdjr", "chevrolet", "lexus", "ford"]`
- `2026-03 nissan` → month=2026-03, brands=`["nissan"]`
- `chevy bmw` → `["chevrolet", "bmw"]`

Set `cap_date` to today's date in `YYYY-MM-DD` format.

## Step 2: Scrape Brands (Parallel or Sequential)

Read `references/brand-scraping.md` NOW and follow it exactly: it carries the full per-brand dealer roster, URLs, scraping order, per-platform extraction procedure, and fallback rules for this step.

## Step 3: Merge and Generate Report

After all requested brands are scraped, run the merge script and report generator:

```bash
python3 "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/monthly-leasing/merge_brand_data.py" \
    --month YYYY-MM \
    --roster "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/monthly-leasing/dealer_roster.json" \
    --output /tmp/lease_data_combined_YYYY-MM.json
```

Then generate the final Excel report (output goes to `outputs/`):

```bash
python3 "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/monthly-leasing/generate_lease_report.py" \
    /tmp/lease_data_combined_YYYY-MM.json \
    "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs" \
    --roster "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/monthly-leasing/dealer_roster.json"
```

The merge script will:
- Find all per-brand JSON files for the month in `/tmp/`
- Include brands from previous runs that still have files on disk
- Validate offers and flag issues
- Deduplicate (same dealer + model + trim + payment + term + DAS = duplicate)
- Produce a combined JSON in `/tmp/`

The report generator will:
- Build the styled `Summary` tab as the FIRST worksheet (Design-System §4): key stats as large Dosis cells with Sky Blue numbers, how-to-read note, cross-brand metrics table
- Create per-brand tabs after it (only brands with data get a tab), then `Dealers`, `Run Log`, and `README` last
- Stamp EVERY visible sheet with the rows 1-2 Digital Blue masthead: white knockout logo anchored A1 (~0.35in, true aspect), sheet title in white Dosis 14 Bold, report date on the right
- Output: `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/DigitalCLIQ_Lease_Tracker_YYYY-MM.xlsx`

## Step 4: Report Results

Display a concise summary:
- Month captured
- Number of dealers visited (this run)
- Number of lease offers found (this run)
- Count by brand
- Any dealers with 0 offers (verified)
- Path to the output Excel file

Keep summary under 15 lines. The Excel file is the deliverable.

## What to Extract + Info Flags

Read `references/extraction-spec.md` for the full field list (LEASE ONLY rules) and the disclaimer info-flag scan table before extracting any offer.

## Important Notes

- **Homepage AND specials page**: scrape the homepage, then ALWAYS also load a dedicated monthly/lease/specials page. Never conclude a dealer has no offers from the homepage alone. The full lineup almost always lives on the specials page, not the homepage.
- **Read banner images**: offers are usually rendered as text inside banner images. Enumerate the banner image URLs, download them, and `Read` the pixels. Never judge an image offer by its filename or alt text, that is the #1 cause of false zeros.
- **Lease only**: skip finance APR offers, "$ off MSRP"/net-cost/sale-price purchase deals, used vehicles, service coupons. Many tiles/banners show lease AND finance side by side, only capture the lease portion.
- **Model dictionary**: always match against the dictionary in `dealer_roster.json` before recording a model name.
- **Disclaimers are critical**: always capture them. If behind a click, open it. If inside a banner image, read it off the image (crop+upscale the fine print). If not legible, note it.
- **VIN tracking**: capture VIN when available. Flag missing VINs in parse_note.
- **Screenshots often blocked**: many dealer pages never reach `document_idle`, so `screenshot`/`get_page_text` time out. That is NOT evidence of "no offers". Fall back to `javascript_tool` (enumerate image URLs + DOM text) plus download-and-`Read` of the banner images.
- **Be patient with page loads**: dealer sites are often slow. Wait 3-4 seconds after navigation.
- **No fabrication**: if you can't extract a field, leave it as 0 or "" and note it in parse_note.
- **No premature zeros**: `verified_zero` requires positively reading real specials-page content (text + banner images) that shows no lease. If you couldn't confirm (page failed, only checked homepage), use `needs_human_review` instead. Mid/late month, a dealer with truly zero lease specials is rare, re-check the banner images before recording zero.
- **Parallel scraping**: when 2+ brands requested, run the 2·0 pre-flight once, then spawn one foreground Task agent per brand for concurrent scraping. Each agent MUST ToolSearch-load the Chrome tools, then create its own browser tab via `mcp__claude-in-chrome__tabs_create_mcp`. Do NOT use `run_in_background`. Each agent returns JSON in its response; main context writes intermediate files to `/tmp/`.
- **Browser trouble = switch, don't stall**: 2 failed attempts on the browser (per dealer, or on the pre-flight probe) means switch to HTTP fallback mode via curl. Never touch the in-app Browser pane / preview tools. Never end a run with zero data because Chrome wouldn't cooperate; HTTP mode always works on these sites.
- **Output convention**: intermediate data (per-brand JSONs, combined JSON) goes to `/tmp/`. The final Excel report is the deliverable and goes to `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/`.
- **DigitalCLIQ credit**: every row must have source_credit = "DigitalCLIQ"


## Self-Validation (MANDATORY: final step before reporting success)

After the deliverable is generated, run the shared post-flight validator on the final file. This step is not optional and runs on every invocation:

```bash
python3 /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/post_flight.py \
  "<final output path>" --min-sheets 2
```

It verifies four things and exits non-zero if any fail:
1. **Branding**: the DigitalCLIQ logo is actually embedded in the file (an image in xl/media inside the workbook). A Digital Blue masthead with no logo image is a FAILURE, not a fallback.
2. **Location**: the file is inside `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/`. Anywhere else (especially the Desktop) fails.
3. **Sheet count**: at least 2 sheets; fewer means a section silently failed or the report is truncated.
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
