---
name: mcpeeks-site-watch
description: Twice-weekly (Mon/Fri) automated compliance + accuracy + health watch for McPeek's CDJR of Anaheim (mcpeeks.com). Crawls all VDPs via sitemap, runs 25 dealer-principal checks (CA pricing-stack law, CARS Act total price per CNCDA guidance, FTC Pricing Transparency FAQs and the 2026-09-30 FTC staff remarks on the doc fee, prominence, CTAs, and in-transit status, verbatim fee disclaimer, Call-for-Price and price-gating CTAs, installed-item exclusions, repealed cancellation-option wording, MSRP-as-price, lease accuracy, photos/spin media, Lighthouse, scripts/cookies, CIPA pre-consent trackers, SSL, domain redirects, phones), diffs week-over-week, and ships a DigitalCLIQ-branded Excel workbook written for the General Manager (Summary, Fix List, Scorecard, per-vehicle detail tabs, Phone Checklist, What Changed) to the McPeek's Google Drive folder. Use when Drew says /mcpeeks-site-watch, "McPeeks site check", "run the McPeeks audit", or the scheduled Mon/Fri task fires.
---

# McPeek's Site Watch

> Before anything else, read `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Context/vault-facts.md` and obey it (output paths, client codes, logo path). Deliverables stage in vault `outputs/`, then file to `Projects/MCP/deliverables/`.

**Audience: the deliverable is read by McPeek's General Manager ([[Stewart Benjamin]]) and owner ([[Frank Busalacchi]]), not by Drew and not by a developer.** Every sentence the workbook carries (the executive summary you write, the check names, the fix wording) is plain English at GM level: what it costs the store, who fixes it, how. No check IDs without a name next to them, no crawler jargon, no VIN lists without a reason. Rule 23 applies.

**Design principle: scripts do the work, the model reads only summaries.**
The crawl, all 15 deterministic checks, SSL/redirect/Lighthouse, the run
assembly, and the Excel build are pure Python/CLI. The model's ONLY jobs are:
(a) a small browser pass for the 3 checks that need a real browser (C03
prominence, C16 cookies, C17 pre-consent trackers), (b) a capped photo
spot-check, (c) writing the GM executive summary from `run_summary.md`. **Never Read raw crawled HTML or inventory.json into context**: read
`findings.json` `counts` first, then only the finding entries you must verify.

Site facts (verified 2026-07): Pixel Motion platform. mcpeeksdodgeanaheim.com
301s to www.mcpeeks.com (canonical). Inventory sitemap:
`https://www.mcpeeks.com/inventory-sitemap.xml`, VDP pattern
`/inventory/display/{cond}/{year}/{make}/{model}/{VIN}` (~390 VDPs incl. RAM
4500/5500 chassis cabs: sitemap-driven crawl reaches them even though nav
routes to Work Truck Solutions). Each VDP has schema.org `Vehicle` JSON-LD
(VIN, condition, offers.price) and a pricing box labeled
`MSRP / McPeeks Discount / Total Savings / Selling Price` with rebates itemized
as `$1000 - <name> . Exp. MM/DD/YYYY` in the description. Server-fetch works
(no 403) with a Chrome UA.

## Browser Surface Order (mandatory, retooled 2026-09-04)

<!-- browser-surface-block v1 · Claude Browser is the primary crawl surface; Chrome is a fallback only -->

Every live page visit in this skill runs on the **built-in Claude Browser** (the in-app Browser pane, tools `mcp__Claude_Browser__*`). Drew's real Chrome via the extension (`mcp__claude-in-chrome__*`) is a fallback, never the default. Do not open the extension, call `list_connected_browsers`, or ask which browser to use unless the Claude Browser has genuinely failed on a page as defined below.

| Tier | Surface | When |
|------|---------|------|
| 1 (default) | **Claude Browser** (`mcp__Claude_Browser__*`) | Every model-driven page visit (Phase 2: C03, C16, C17, C12 spot-check). Open with `preview_start {url}` (or `tabs_create` + `navigate` for a fresh tab), extract with `javascript_tool` / `read_network_requests` / `get_page_text`, always with `tabId`. No user approval needed. |
| 2 (fallback) | **Server fetch** (`scripts/crawl.py`, python urllib with a Chrome UA) | Already the default for the bulk crawl (mcpeeks.com accepts it). Also the first fallback when the Claude Browser cannot render one of the Phase 2 pages: save the HTML to `$DATA` and re-run the extractor. |
| 3 (last resort) | **Chrome extension** (`mcp__claude-in-chrome__*`) | Only when BOTH tier 1 and tier 2 failed on the same page (pane hung twice AND server fetch 403/blocked). Needs a one-time user approval; if the extension is not connected, record the check as `{"check": ..., "severity": "manual", "summary": "surface_exhausted"}` in `browser_findings.json` and move on, do not stall the run. |

**Retry rule for tier 1.** A page gets at most two fresh attempts on the Claude Browser: the first in the current tab, the second in a brand-new tab (`tabs_create`, then `navigate`) after closing the stuck one. If `javascript_tool` still times out or returns empty on the second attempt, cascade. Never loop a third time on the same surface.

**Tab discipline.** The Claude Browser is ONE pane with many tabs. Create your tab with `tabs_create` (or take the `tabId` that `preview_start` returns), and pass that `tabId` on EVERY subsequent call (`navigate`, `javascript_tool`, `read_network_requests`, `tabs_close`). A call without `tabId` acts on whichever tab is fronted. Consent-state checks need a FRESH tab (`tabs_create`) so no cookie banner state carries over. Close the tab when done.

**Tool name mapping** (older notes used the Chrome extension names; they map 1:1):

| Chrome extension (tier 3) | Claude Browser (tier 1, use this) |
|---|---|
| `tabs_context_mcp` | `mcp__Claude_Browser__tabs_context` |
| `tabs_create_mcp` | `mcp__Claude_Browser__tabs_create` |
| `tabs_close_mcp` | `mcp__Claude_Browser__tabs_close` |
| `navigate` | `mcp__Claude_Browser__navigate` |
| `javascript_tool` | `mcp__Claude_Browser__javascript_tool` |
| `read_page` / `find` / `get_page_text` / `read_network_requests` / `computer` | same names under `mcp__Claude_Browser__` |

Any bare mention of `javascript_tool`, `navigate`, `read_network_requests`, or `tabs_*` elsewhere in this skill means the Claude Browser version unless the text says "Chrome extension".

## Paths

- `SKILL=<this skill dir>`; scripts in `$SKILL/scripts/`, config in `$SKILL/config/`
- `DATA=<scratchpad>/mcpeeks-run/`: per-run working data (disposable)
- `VAULT=/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ` (the live vault root per vault-facts; never `~/Documents`, never the frozen copy)
- `STATE=$VAULT/Projects/MCP/site-watch-state/`: first-seen VINs, snapshots, history (persists; enables week-over-week diff and inventory aging). McPeek's client code is **MCP** (confirmed in vault CLAUDE.md roster).
- Outputs stage in `$VAULT/outputs/`, then copy to `$VAULT/Projects/MCP/deliverables/`.

## Phase 1: Crawl + deterministic checks (Bash only, no model reads)

```bash
python3 "$SKILL/scripts/crawl.py" --out "$DATA"    # defaults: 3 workers, 0.7s pacing. NEVER raise workers above 4
python3 "$SKILL/scripts/checks.py" --data "$DATA" --skill "$SKILL" --state "$STATE"
python3 "$SKILL/scripts/sitehealth.py" --skill "$SKILL" --data "$DATA"   # SSL + redirects + Lighthouse (~6 min; add --skip-lighthouse only if node/npx missing)
```

> [!warning] Crawl politeness is a hard rule. On 2026-07-26 a 10-worker crawl
> coincided with the production site going down (origin refused all
> connections for everyone). The defaults (3 workers + pacing, ~15-20 min) are
> deliberate. If crawl.py exits 3 (circuit breaker: site down/refusing), STOP
> all requests, probe once per minute from Bash, and tell Drew immediately,
> do not resume until the site answers 200 and never twice in a row.

Covers checks C01–C02, C04–C13, C15, C18–C19, C21, C22–C25. Read only the printed
counts. If crawl.py exits 2 (>20% fetch failures but site is up), follow the
multi-strategy fallback: retry once, then switch to the Claude Browser pane
(`mcp__Claude_Browser__preview_start`, then `javascript_tool` same-origin
`fetch()` with `tabId`) to fetch the sitemap + failing pages, then, only if
the pane failed twice, the Chrome extension (`mcp__claude-in-chrome__*`). Do
NOT hand-crawl hundreds of pages in-context; fetch, save to `$DATA`, and
re-run the extractor.

## Phase 2: Browser pass (the only model-driven crawling; ~4 pages total)

Use the Claude Browser (`mcp__Claude_Browser__*`, per the Browser Surface
Order above; the Chrome extension is tier 3 only). Fresh tab so no consent
state carries over: `mcp__Claude_Browser__tabs_create` → `tabId`, then pass
that `tabId` on every call below.

1. **C17 CIPA pre-consent + C16 cookies**: `mcp__Claude_Browser__navigate
   {url: "https://www.mcpeeks.com/", tabId}` and DO NOT click the ComplyAuto
   banner. `mcp__Claude_Browser__read_network_requests {tabId}` and record
   tracker hosts that already fired (google-analytics collect, doubleclick,
   facebook, tiktok, bing, etc.). Count `set-cookie`s / `document.cookie` via
   `mcp__Claude_Browser__javascript_tool {tabId}`. Repeat once on one SRP in
   another fresh tab. Compare cookie count to the previous snapshot number in
   `$STATE/snapshot.json`.
2. **C03 prominence**: on 2 VDPs (1 new w/ rebates, 1 used; pick from
   findings.json URLs), run `$SKILL/scripts/prominence.js` via
   `mcp__Claude_Browser__javascript_tool {tabId}`.
   Flag if the largest/boldest price is NOT the all-in selling price (e.g. MSRP
   or a post-rebate teaser renders bigger), or if a qualified price lacks nearby
   qualification.
3. **C12 wrong-photo spot-check**: pick 8 VDPs rotating by VIN hash (plus any
   flagged placeholder ones), download hero images with curl to `$DATA/imgs/`,
   Read each image, verify it plausibly matches year/make/model/color from the
   record. 8 max per run: coverage accumulates across runs.

Write everything from this phase as a JSON array of findings
(`{check, severity, url, vin, summary}`: severity: C03/C17 = "compliance",
C12 = "data_accuracy", C16 = "hygiene") to `$DATA/browser_findings.json`.

**C20 phone verification cannot be automated**: Claude cannot place calls.
The report auto-appends a manual call checklist of every number found on the
site. Numbers are diffed run-over-run so new/changed numbers stand out.

## Phase 3: Assemble, write the GM summary, build the Excel, QA, file

```bash
python3 "$SKILL/scripts/report.py" --data "$DATA" --state "$STATE"
```

`report.py` merges every finding source, diffs against the previous snapshot,
classifies each change (NEW because a vehicle just arrived vs a new issue on an
existing unit; RESOLVED because it was fixed on the page vs the vehicle sold),
ranks the Fix List, writes `$DATA/report.json` (the workbook's only input) and
`$DATA/run_summary.md` (the only file you read), and updates state. Read
`run_summary.md`; never open `report.json` or `findings.json` in full.

1. **Write the executive summary** to `$DATA/exec_summary.txt`: 5 to 8
   sentences, one paragraph, in the voice of a trusted advisor briefing the GM.
   Order: worst legal exposure first with one concrete example (vehicle, VIN,
   dollars), then what is new since last run, then what cleared and whether it
   cleared by fix or by turnover, then the one or two health items. Name the
   fixer for each item (Pixel Motion, ComplyAuto, inventory manager). No check
   IDs, no jargon, no em dashes. `build_workbook.py` refuses to run without it.
2. **Build the workbook**:

   ```bash
   python3 "$SKILL/scripts/build_workbook.py" --data "$DATA" --out "$VAULT/outputs"
   ```

   Produces `outputs/McPeeks_Site_Watch_YYYY-MM-DD.xlsx` plus the facts
   manifest `outputs/McPeeks_Site_Watch_YYYY-MM-DD.facts.json` (every count,
   date, VIN example and summary figure with its source) for the QA gate. Tabs,
   in reading order: **Summary** (stat band, area status, executive summary,
   top 3 fixes, how to read), **Fix List** (one row per problem type: what, why
   it matters to the store, who fixes it, the fix, example vehicle), **Scorecard**
   (all 25 checks, this run vs last, ACTION / WATCH / CLEAR / MANUAL),
   **Legal & Pricing**, **Inventory Accuracy**, **Site Health** (per-item detail
   with page links, filterable), **Phone Checklist** (blank columns for the
   person making the test calls), **What Changed** (new items with the reason,
   turnover summarized by check, in-place fixes listed). The GM-language text
   for every check lives in `scripts/check_catalog.py`; edit wording there,
   never in the workbook. `--prepared-for` defaults to the GM named in
   `Projects/MCP/README.md` Key contacts.
3. **Validate + render gate**: `python3 "$VAULT/.claude/skills/post_flight.py"
   <xlsx> --min-sheets 8`, then the Design-System render gate below (Excel
   renders every sheet to PNG; read every page). Then the Final QA Gate.
4. **Upload** to the McPeek's Drive folder (ID `1ccXwQ0zZOi_iwwSJNjIBVSalNu58lIUp`)
   via the Google Drive MCP `create_file`, name
   `McPeeks_Site_Watch_YYYY-MM-DD.xlsx`. If binary upload fails, say so and
   leave the file in `outputs/` for Drew to drop in manually; do not substitute
   a Google Doc, the tabs are the deliverable.
5. **File** the `.xlsx` and `.facts.json` to `$VAULT/Projects/MCP/deliverables/`
   and append a one-line entry (date, counts by area, top fix) to
   `Projects/MCP/context-log.md`. State/history is already updated by report.py.

## Final message to Drew

Lead with counts by area (Legal & Pricing / Inventory Accuracy / Site Health)
and the top 3 Fix List rows with owners, then NEW vs RESOLVED split by reason
(fixed vs sold), then the render-gate + QA lines, then anything needing his
input (empty disclaimer template, missing domains in domains.txt, stale
lease_programs.json, the call checklist, Node missing for Lighthouse). One
screen, no padding. Link the xlsx in `outputs/` and the Drive upload.

## Config Drew maintains

- `config/domains.txt`: currently only the 7 known domains; needs the full ~50
- `config/fee_disclaimer_template.txt`: paste exact approved language (until then C04 checks CA statutory elements only)
- `config/approved_vendors.txt`: approved script vendors; C15 flags everything else (FourEyes intentionally absent)
- `config/lease_programs.json`: optional desking rates for C09 payment recompute; without it C09 falls back to internal-consistency checks only (C08 catches summary-vs-disclaimer math)

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

## Token budget

Target < 50k output tokens per run. Phase 1 ≈ 0 (scripts). Phase 2 is capped at
~4 Claude Browser pages + 8 images. Phase 3 reads one compact brief (`run_summary.md`)
and the rendered sheet PNGs for the gate. Do not
spawn subagents for this skill; a single linear pass is cheaper and fast enough
(~10–15 min wall clock, dominated by Lighthouse).


## Final QA Gate: deliverable-reviewer agent (MANDATORY, added 2026-08-13)

Runs AFTER the deliverable is generated and post_flight.py passes, BEFORE filing/presenting. post_flight.py is mechanical; this gate is the human-style read.

1. **Write a facts manifest** next to the deliverable in `outputs/`: a JSON list of every number, name, date, and claim that appears in the deliverable, each as `{"value": ..., "label": "where it appears", "source": "tool/file/URL it came from"}`. Build it from data already in context, never re-fetch anything just for the manifest.
2. **Spawn the `deliverable-reviewer` agent** (fresh eyes, it did not write the report). Pass in the prompt: the absolute path(s) of the finished deliverable file(s), the manifest path, and any skill-specific checks from this SKILL.md. It renders every page, reads them all, cross-checks figures against the manifest, and reviews tone/copy.
3. **Auto-fix every finding** in the source generator or data (never by hand-editing the output), re-render, and re-run the agent once. Max 2 review passes. If CRITICAL or MAJOR findings remain after pass 2, the ship is BLOCKED: report the remaining findings to Drew verbatim instead of presenting the file as done.
4. The run summary MUST include a **QA line**: what the reviewer caught and what was fixed, or "QA: clean on first pass (N pages read, M figures verified)". Never silently skip the gate; if the agent could not run, say so explicitly in the delivery message.
