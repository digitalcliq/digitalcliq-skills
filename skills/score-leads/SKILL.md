---
name: score-leads
description: Score and rank automotive dealership lead sources from CRM e-commerce reports. Accepts PDF, CSV, or Excel files. Outputs a branded Excel scorecard from DigitalCLIQ with 1-10 scoring, A/B/C/D tier rankings, and a NADA/industry close-rate benchmark layer that grades the store and each source against national benchmarks by brand tier.
argument-hint: [file-path to CRM report (PDF, CSV, or Excel)]
allowed-tools: Read, Bash(python3 *), Bash(/opt/homebrew/bin/pdftotext *), Task
---

> [!important] Pre-flight: load the facts ledger FIRST
> Before doing anything else, read `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Context/vault-facts.md` and obey it. It is the source of truth for: output location (always the vault `outputs/` folder, never the Desktop or the input file's directory), the canonical working folder (the vault root, never an old/legacy folder), the DigitalCLIQ Master calendar, the canonical logo path, and correct client/competitor names (e.g. "BMW of Buena Park (AutoNation)" not "Shelly BMW"; LOGO Cargo is a hostile competitor, not an Atlas partner). Validate every output path and every client/competitor name against the ledger before writing. If a fact you need is missing from the ledger, do not guess: check the vault and flag it.

# Lead Source Scoring: Automotive Dealerships

Score lead providers and lead sources from a CRM e-commerce report. Each source gets a 1-10 score and A/B/C/D tier ranking based on conversion performance. On top of the score, a **NADA / national-industry benchmark layer** grades the store's overall close rate and each source's close rate against the industry rate for its source type and brand tier. Output is a formatted Excel spreadsheet branded by DigitalCLIQ.

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

- Tier chips keep their explicit text labels (`A`/`B`/`C`/`D`, and `Above`/`At`/`Below`/`Low vol`/`N/A` on the benchmark flags), color is treatment only: A = Digital Blue, B = Sky Blue, C = Warm Grey, D = Navy Deep. Never red/green/orange severity coding.
- The workbook's four tabs, in order, are **Summary**, **Lead Source Scores**, **NADA Benchmarks**, and **Methodology** (data columns are skill logic, not styling). The workbook opens on the Summary tab.
- The **Summary** first tab (Design-System §4) carries the title block, key stats as large Dosis cells with Sky Blue numbers, the store self-score banner, tier mix, top sources, and the how-to-read notes (tier + benchmark legends). The Lead Source Scores tab repeats the self-score banner above the data and keeps the credit-app disclaimer next to the shaded rows it explains.

## Scoring Weights

| Factor | Weight | Why |
|--------|--------|-----|
| Sale Conversion Rate | 40% | #1 goal: selling cars |
| Appointment Show Rate | 20% | Real buying intent |
| Sales Volume | 15% | Raw deal count matters |
| Appointment Set Rate | 15% | Customer engagement |
| Contact Rate | 10% | Signal, but noisy |

Scoring is **relative**: each source is scored against the best performer in that report.

## New vs Used Car Adjustment

Each source is classified as **New** or **Used** based on its name:

- **Used car sources** (3rd-party marketplaces): AutoTrader, CARFAX, CarGurus, Cars.com
- **New car sources** (everything else): Dealer website, OEM/factory, TrueCar, Costco, Meta, trade-in tools, paid social, Auto Club, Edmunds, TradePending

New car leads naturally close at a lower rate than used car leads because used inventory is 1-of-1 (unique VIN, miles, price). To compensate, **new car sources get a 1.5x boost on sale conversion rate** before scoring. The Sale % column in the output shows the actual (unadjusted) rate, the boost is applied internally only.

## Tiers

- **A (8-10):** Top performer
- **B (5-7):** Solid source
- **C (3-4):** Underperforming
- **D (1-2):** Poor ROI

## NADA / Industry Benchmark Layer

The 1-10 score above is **relative** (each source vs the best in this report). Layered **alongside** it, never changing the score, is an **absolute** benchmark that answers "are we good by industry standards?"

- **Source-type benchmarks.** Each source is classified into a type (internet/website, phone, walk-in/showroom, third-party marketplace, OEM/factory, owned equity, chat). Its actual close rate is compared only to the NADA/industry close rate for **its own type**: walk-ins (~25%) are never judged against the internet-lead benchmark (~10%).
- **Brand-tier aware.** The store's franchise is auto-detected from its name and mapped to **luxury** (BMW, Lexus, Mercedes, etc.), **mainstream** (Nissan, CDJR, Chevy, etc.), or **powersports** (Harley, etc.). Luxury benchmarks run slightly higher. Unknown names default to mainstream.
- **Flags.** The `vs Bench` column shows **Above** (10%+ over benchmark), **At** (within ±10%), **Below** (10%+ under), **Low vol** (under 10 leads, too small to judge), or **N/A** (data lists / credit apps, not acquisition sources).
- **Store self-score.** A banner at the top of the scorecard grades the store's actual close rate against the rate industry would be expected to deliver **on this report's lead mix**: a lead-weighted average of each source's own source-type benchmark. This auto-adjusts: an internet-only e-commerce export is judged against the internet/marketplace/chat blend (lower), while a full-source scorecard with walk-ins and owned equity is held to a higher bar. Credit apps and OEM/FS data lists are excluded from the store rate (not inbound buy-leads), so list loads don't deflate it. Example: "6.8% close on acquisition leads vs 10.4% expected for this lead mix. BELOW by 3.6 pts (excludes 534 data-list/credit-app leads)."
- **All numbers are sourced and editable.** Every benchmark, its support strength (Strong / Moderate / Estimate), and its citation live in `reference/nada_benchmarks.json` and appear on the **NADA Benchmarks** tab. DigitalCLIQ maintains this file and refreshes it when new NADA data publishes (currently the 2025 reference set).

The script loads the reference file automatically; no extra arguments are needed. If the reference file is missing it degrades gracefully to relative-only scoring.

## Fast Path (DEFAULT: one command, low token cost)

Do NOT read the raw file into context and do NOT hand-write a transform. The skill auto-detects the CRM format locally and does everything, ingest, normalize, score, Excel, AND post-flight validation, in ONE command:

```
python3 /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/score-leads/score_leads.py \
  --raw "<raw_file>" "<output_path>" "<store_name>" "<date_range>" [--rollup|--no-rollup]
```

It prints a ~8-line `SUMMARY` block (store, detected format, sources scored, store self-score, tier counts, **validation: PASSED/FAILED**, output path). Read that summary and report it. Do NOT open the workbook to verify and do NOT run post_flight separately, validation is built in. If the summary says `validation: FAILED` (or the command exits non-zero), the run failed: diagnose from the printed validator output, fix, and re-run; never report success on failed validation.

- **Auto-detected formats:** VinSolutions Lead Source ROI, Momentum E-Commerce Statistics, Tekion Lead Source Report, the native normalized schema, and **PDF** (best-effort single-table parse). Tekion is rolled up to canonical vendors by default (it splits every source New/Used); the others stay per-source. Use `--rollup` to consolidate fragmented marketplace variants (e.g. a Momentum export with 18 AutoTrader sub-products → one AutoTrader.com row), or `--no-rollup` to force granular. Roll-up rules live in `reference/canonical_vendors.json`.
- **Store name** drives brand-tier detection, pass the real dealer name (e.g. "Sterling BMW", "McPeek Chrysler Dodge Jeep Ram").
- **Unknown format / unparseable PDF:** the command errors and prints the headers (or a "too few rows" message). Add an adapter in `ingest.py` (preferred) or fall back to the manual path below.

**Multiple stores = parallel:** If given CRM exports for 2+ stores, launch one foreground Task agent per store in a SINGLE message. Each agent runs the one-command fast path (validation included) and returns `{"store": ..., "output": ..., "summary": "<the SUMMARY block>"}`. The main context reports all scorecards together. One store's bad file never blocks the others.

## Manual Path (only if the fast path can't read the file)

Read `references/manual-path.md` and follow it exactly. Only enter this path after the fast path has actually failed to read the input file.

## Self-Validation (built in: runs automatically)

`score_leads.py` runs the shared post-flight validator on the finished file as the last step of every run (both `--raw` and the normalized path) and reports `validation: PASSED/FAILED` in the SUMMARY, exiting non-zero on failure. You do NOT need a separate validator call. (Pass `--no-validate` only for throwaway test outputs written outside `outputs/`.)

The workbook has four sheets: **Summary** (first), **Lead Source Scores**, **NADA Benchmarks**, and **Methodology**.

The validator verifies four things and exits non-zero if any fail:
1. **Branding**: the DigitalCLIQ logo is actually embedded in the file (an image in xl/media inside the workbook). A bare Digital Blue masthead with no logo image is a FAILURE, not a fallback.
2. **Location**: the file is inside `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/`. Anywhere else (especially the Desktop) fails.
3. **Sheet count**: at least 4 sheets (Summary, Scores, NADA Benchmarks, Methodology); fewer means a section silently failed or the report is truncated.
4. **No placeholder data**: template tokens like `{dealer_name}`, literal `YYYY-MM-DD`, "PLACEHOLDER", or lorem ipsum anywhere in the deliverable fail.

**On failure: retry once with a fallback, then fail loudly:**
1. Diagnose from the validator output. Common fixes: the logo must load from the canonical path `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png`; a file saved outside `outputs/` must be moved there and re-validated; a placeholder hit means a data section came back empty, re-fetch that data, do not paper over it.
2. Regenerate the deliverable ONCE and re-run the validator.
3. If it still fails: STOP. Show the user the validator output verbatim and state that the report FAILED validation. Never report success, never present the file as the final deliverable, and never wrap this step in try/except or `|| true` that hides the failure.

## Optional ROI + GA4 layer (added 2026-07-26)

When Drew asks to layer campaign costs / ROI / cost-per-lead onto a scorecard, use `scripts/roi_layer_ncbmw.py` as the reference implementation (built for the NCBMW July 2026 run). It reads the raw CRM CSV + the finished scorecard, maps every CRM source to the vendor that bills for it, and adds: ROI Summary, Vendor ROI (cost, CPL, cost/sale, net, ROI as live formulas so "NO DATA" cost cells recalc when filled), Cost Ledger, and a GA4 Traffic vs Spend tab (spend share vs session share vs key-event share).

Per-store setup that MUST be edited: the `LEDGER` (monthly costs from the client's budget sheet), the `GROUPS` source-to-vendor mapping, and the GA4 TSV. Rules learned on the first run:
- Cost cells with no budget line get the literal text `NO DATA` (grey chip); all derived columns use `IF(ISNUMBER(...))` so Drew can fill them later.
- Traffic drivers (PPC, Constellation-style awareness spend) get their own section, never judge them on a CRM source row; judge on GA4 session/key-event share vs spend share.
- GA4 pull order: Zapier `google_analytics_4_run_report_for_a_property` first; if quota/auth blocked, analytics.google.com via Drew's Chrome (property ids in `Context/connector-ids.md`).
- Deliver as a native Google Sheet when asked: see the `xlsx-to-google-sheet-pipeline` memory (mounted-Drive copy + Chrome "Save as Google Sheets"; ASCII-only clipboard pastes).
- ALWAYS tell Drew about every error hit during the run (his standing rule), and never delete/replace files in client Drive folders without telling him first.


## Final QA Gate: deliverable-reviewer agent (MANDATORY, added 2026-08-13)

Runs AFTER the deliverable is generated and post_flight.py passes, BEFORE filing/presenting. post_flight.py is mechanical; this gate is the human-style read.

1. **Write a facts manifest** next to the deliverable in `outputs/`: a JSON list of every number, name, date, and claim that appears in the deliverable, each as `{"value": ..., "label": "where it appears", "source": "tool/file/URL it came from"}`. Build it from data already in context, never re-fetch anything just for the manifest.
2. **Spawn the `deliverable-reviewer` agent** (fresh eyes, it did not write the report). Pass in the prompt: the absolute path(s) of the finished deliverable file(s), the manifest path, and any skill-specific checks from this SKILL.md. It renders every page, reads them all, cross-checks figures against the manifest, and reviews tone/copy.
3. **Auto-fix every finding** in the source generator or data (never by hand-editing the output), re-render, and re-run the agent once. Max 2 review passes. If CRITICAL or MAJOR findings remain after pass 2, the ship is BLOCKED: report the remaining findings to Drew verbatim instead of presenting the file as done.
4. The run summary MUST include a **QA line**: what the reviewer caught and what was fixed, or "QA: clean on first pass (N pages read, M figures verified)". Never silently skip the gate; if the agent could not run, say so explicitly in the delivery message.
