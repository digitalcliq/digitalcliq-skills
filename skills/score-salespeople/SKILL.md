---
name: score-salespeople
description: Score and rank individual automotive salesperson performance from CRM lead exports. Generates a DigitalCLIQ-branded Excel scorecard with composite 1–10 scores, tier rankings (A/B/C/D), and per-rep coaching flags. Mirrors the score-leads methodology applied to salespeople instead of lead sources.
---

> [!important] Pre-flight: load the facts ledger FIRST
> Before doing anything else, read `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Context/vault-facts.md` and obey it. It is the source of truth for: output location (always the vault `outputs/` folder, never the Desktop or the input file's directory), the canonical working folder (the vault root, never an old/legacy folder), the DigitalCLIQ Master calendar, the canonical logo path, and correct client/competitor names (e.g. "BMW of Buena Park (AutoNation)" not "Shelly BMW"; LOGO Cargo is a hostile competitor, not an Atlas partner). Validate every output path and every client/competitor name against the ledger before writing. If a fact you need is missing from the ledger, do not guess: check the vault and flag it.

# score-salespeople

DigitalCLIQ's automotive dealership salesperson performance scoring tool. Scores individual salespeople on a 1–10 scale using a relative methodology that mirrors the score-leads skill, applied to salesperson performance instead of lead source performance.

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

## When to use this skill

Trigger when the user wants to:

- Evaluate individual salesperson performance from CRM lead data
- Identify top and bottom performers on the sales floor
- Generate coaching insights for GMs and GSMs
- Compare salespeople on response handling, appointment setting, show rates, and closing

Triggers also include any mention of: "score the sales floor," "rank my salespeople," "salesperson scorecard," "who's working leads best," or uploading a CRM lead export with a request to evaluate the sales team.

## Inputs

1. **Dealership name** (e.g., "McPeek CDJR of Anaheim")
2. **CRM platform**: Tekion or VINSolutions (v1: Tekion only; VINSolutions stub returns "not yet supported")
3. **CRM export files**: one of two shapes:
   - **Aggregated:** Tekion "User Activity Report - By Sales Rep" (one row per salesperson, totals computed by Tekion). Easiest to pull, supports the 10-factor methodology.
   - **Per-lead:** Tekion lead export + activity log (two files joined on lead_id). Supports response time. Heavier setup.
4. **Report period**: defaults to trailing 30 days ending today

## Parallel Multi-Store Runs (DEFAULT for 2+ stores)

When exports for more than one store are provided, launch one foreground Task agent per store in a SINGLE message. Each agent runs the full pipeline for its store (adapter → normalize → score → Excel → post-flight validation) and returns the output path, tier counts, and validation result as JSON. The main context reports all scorecards together; one store's missing column never blocks the others, it is reported per-store, loudly.

## Methodology

Each salesperson is scored on a 1–10 scale, normalized against the top performer in the report period. The factor set depends on which input shape you provide.

### Aggregated path (Tekion User Activity Report). 10 factors

| Factor | Weight | What it measures |
|---|---|---|
| Sale Conversion Rate | 25% | Sold ÷ Good Leads |
| Appointment Set Rate | 12% | Appointments Scheduled ÷ Good Leads |
| Appointment Show Rate | 12% | Appointments Shown ÷ Appointments Scheduled |
| Sales Volume | 10% | Raw Sold count (split deals count as .5) |
| Task Completion Rate | 10% | Completed Tasks ÷ Total Tasks (pipeline discipline) |
| Activity per Lead | 8% | (Calls + Texts + Emails) ÷ Good Leads (hustle) |
| Call Connection Rate | 8% | Calls Contacted ÷ Calls Out (phone QUALITY, not just volume) |
| Appt Confirmation Rate | 8% | Appointments Confirmed ÷ Scheduled (best predictor of show rate) |
| Tasks Overdue (inverse) | 4% | Lower-is-better; inverse-normalized |
| Video Adoption | 3% | Video Sent Leads ÷ Good Leads |

### Per-lead path (lead export + activity log). 5 factors

| Factor | Weight | What it measures |
|---|---|---|
| Sale Conversion Rate | 40% | Deals closed ÷ leads owned at creation |
| Appointment Show Rate | 20% | Appointments shown ÷ appointments set |
| Sales Volume | 15% | Raw count of closed deals |
| Appointment Set Rate | 15% | Appointments set ÷ leads owned at creation |
| Response Time | 10% | Median first-response time, inverse-normalized |

### Role classification (aggregated path)

Tekion User Activity Reports include BDC, sales managers, the "Other" unattributed-lead bucket, and placeholder accounts alongside salespeople. The engine auto-classifies each row:

- **BDC / appt coordinator:** `total_tasks ≥ 100 AND good_leads < 5`, OR `tasks_per_lead > 30`. Surfaced on a dedicated "BDC / Non-Sales" tab; not scored against the salesperson rubric.
- **Other bucket:** Name is "Other" / "Unassigned" / "House Deal". Surfaced separately; flagged as a routing-rule problem if it holds a meaningful share of leads.
- **Placeholder:** Zero leads, near-zero tasks, no sales. Filtered silently. (Or via `--exclude <name>` for manual override.)
- **Duplicate accounts:** Full-uppercase variants of a normal-case name are filtered as duplicates.

Each scored salesperson then gets a 1-10 composite and a tier:
**A (8-10)** · **B (5-7)** · **C (3-4)** · **D (1-2)**.

### Exclusions

- **Salespeople with fewer than 25 leads in the period** are not scored; shown separately on the "Not Scored" tab.
- **Credit application leads** are excluded from per-lead denominators (paperwork, not pipeline).
- **Auto-responses** are excluded from response-time calculation (per-lead path only).

### What is NOT in this methodology

- **No new/used boost** applied at the salesperson level (mix is a management decision).
- **No gross profit weighting in v1.** Captured in raw data for future versions.

## Output

DigitalCLIQ-branded Excel workbook styled per the Design System block above (rows 1-2 Digital Blue `#405FAB` masthead with white knockout logo, white Dosis 14 sheet title, and report date on EVERY visible sheet; Digital Blue header rows; Dosis/Roboto Slab fonts; alternating White / Callout Tint body rows), saved to `DigitalCLIQ/outputs/`:

1. Summary (styled first tab: key stats as large Dosis / Sky Blue cells, top performer callout, how-to-read notes)
2. Methodology (factor weights, tier definitions, score interpretation)
3. Salesperson Scorecard (the headline)
4. Factor Detail
5. Coaching Flags
6. BDC / Non-Sales Roles (aggregated path only)
7. Other (Unattributed) (aggregated path, if present)
8. Not Scored (below 25-lead minimum + filtered placeholders)
9. Raw Data

## Pipeline

```
CRM exports → CRM-specific adapter → Normalized Lead schema
            → Scoring engine (CRM-agnostic)
            → Coaching flag generator
            → DigitalCLIQ Excel builder → DigitalCLIQ/outputs/
```

## Versioning

- **v1 (current):** Tekion CSV exports, manual run, McPeek as first client
- **v2 (planned):** Tekion APC API integration for real-time pull
- **v3 (planned):** VINSolutions adapter, additional clients

## Cross-skill consistency

Scoring methodology matches `score-leads` exactly in structure:

- Same 1–10 scale
- Same normalization (relative to top performer)
- Same tier definitions (A/B/C/D)
- Same composite formula structure
- Differs only in *which* factors are measured and *whether* the new/used boost applies

A salesperson scoring a 7 means roughly the same thing as a lead source scoring a 7: 70% of the top performer's composite for that store in that period.

## Standing notes

- DigitalCLIQ branding required on all outputs, per the Design System block above (palette tokens, Dosis/Roboto Slab, canonical logo paths under `Resources/brand-assets/`)
- Tier fills are palette treatments only (A = Digital Blue, B = Sky Blue, C = Callout Tint, D = Warm Grey); the A/B/C/D letter in the cell is the explicit text label that carries the meaning
- Output files go to `DigitalCLIQ/outputs/`
- Drew prefers direct, copy-paste-ready outputs with minimal preamble

## How to run

**Aggregated path** (Tekion User Activity Report, easiest):
```bash
python3 .claude/skills/score-salespeople/scripts/scoring_engine.py \
    --tekion-user-activity "<user_activity_report.csv>" \
    --store "McPeek CDJR" \
    --period-days 30
```

**Per-lead path** (Tekion lead export + activity log, includes response time):
```bash
python3 .claude/skills/score-salespeople/scripts/scoring_engine.py \
    --tekion-leads "<lead_export.csv>" \
    --tekion-activities "<activity_log.csv>" \
    --store "McPeek CDJR" \
    --period-days 30
```

**Optional flags:**
- `--min-volume N`: change the 25-lead minimum
- `--exclude "Name"`: force a user into the placeholder bucket (repeat for multiple)
- `--end-date YYYY-MM-DD`: anchor period to a past date
- `--output <path.xlsx>`: override the default outputs path

The orchestrator entry point lives at `scripts/scoring_engine.py`. It calls the right Tekion adapter for the input shape, normalizes, scores, generates coaching flags, and writes the Excel workbook.


## Self-Validation (MANDATORY: final step before reporting success)

After the deliverable is generated, run the shared post-flight validator on the final file. This step is not optional and runs on every invocation:

```bash
python3 /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/post_flight.py \
  "<final output path>" --min-sheets 2
```

It verifies four things and exits non-zero if any fail:
1. **Branding**: the DigitalCLIQ logo is actually embedded in the file (an image in xl/media inside the workbook). A black tile with no logo image is a FAILURE, not a fallback.
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
