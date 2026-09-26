---
name: monthly-client-report
description: Generate a branded DigitalCLIQ monthly performance report for a client. Pulls the PREVIOUS month's GA4 traffic (incl. social referral), Google/Meta paid media, SEMRUSH SEO, CRM lead data scored against NADA close rates, Google + Yelp reputation, and regional NADA/economic data for the client's state. Surfaces "DigitalCLIQ & {client} wins this month" from the client's vault context log. Renders a tight 2-3 page PDF, self-reviews it, and files it to the client folder. Use when Drew says /monthly-client-report, "monthly report for [client]", or schedules a monthly client report.
argument-hint: "<client code | name | website>  [--month YYYY-MM]"
allowed-tools: Agent, Read, Write, Glob, Grep, Bash(python3 *), Bash(pip3 install *), Bash(mkdir *), Bash(mv *), Bash(ls *)
---

> [!important] Pre-flight: load the facts ledger FIRST
> Read `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Context/vault-facts.md` and obey it before anything else. It is the source of truth for: the `outputs/` path, the canonical logo (WHITE mark on blue masthead only), and correct client/competitor names (e.g. "BMW of Buena Park (AutoNation)" not "Shelly BMW"; LOGO Cargo is a HOSTILE Atlas competitor, never a partner). Vault names beat web research.

> [!note] Script paths
> This skill's own scripts are written as `"${CLAUDE_SKILL_DIR}/<file>"`, always double-quoted (the installed path contains spaces). If ${CLAUDE_SKILL_DIR} did not expand, use the Base directory printed when this skill loaded. score-leads is the sibling folder `"${CLAUDE_SKILL_DIR}/../score-leads"`. The shared validator and the ai-team scripts are the only skill files in the vault: `"/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/post_flight.py"` and `"/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/ai-team/scripts/"`. Quote every path.

# DigitalCLIQ Monthly Client Report

A client-facing monthly performance report. **Lean by design:** the main loop orchestrates; the heavy data-gathering runs in parallel **Sonnet subagents** (pass `model: "sonnet"` to every `Agent` call, that's where the token volume is). The main session only resolves the client, merges JSON, renders, and does the final human read.

Target: tight **2-3 page** branded PDF. End-to-end goal under ~5 minutes.

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

## Inputs Drew provides (the skill must remind him)

This report reads TWO things from the chat that Drew attaches. **Before gathering anything, post this reminder and wait for `go`:**

> 📎 **Two attachments needed for [CLIENT]'s [MONTH] report:**
> 1. The **DigitalCLIQ working folder** for this client (so I can pull the right context).
> 2. The client's **CRM lead report** AND **ad/spend report** in **CSV or PDF** (Google Ads + any Meta).
>
> Drop them in and reply **`go`**. (GA4, SEMRUSH, reviews, and regional data I pull live myself.)

If Drew replies `go` without files, proceed with whatever IS attached and omit the sections that need a missing file (leads needs the CRM file; paid needs the ad file). Never invent numbers.

---

## Step 0: Resolve the client (no subagent, fast)

1. Parse `$ARGUMENTS`: first token = client (CODE, name fragment, or domain); optional `--month YYYY-MM`.
2. Load `"${CLAUDE_SKILL_DIR}/reference/client_registry.json"`. Match the arg against `code`, `aliases`, or `domains` (lowercase, strip `www.`/`https://`). If a website was given and isn't in the registry, infer brand/city from the site + a quick WebSearch, then proceed. If the matched registry entry has a status that starts with inactive, stop and tell Drew the client is inactive instead of building a report.
3. Default `--month` to the **previous calendar month**. Runs happen on the **3rd or later** so GA4 has every day of that month (see Step 1 A); a run on the 1st or 2nd is a partial month and must say so. Build `month_label` ("May 2026"), `YYYY-MM`, the date range, `TODAY`, and `CODE_UPPER` (the code in upper case, the ai-team store key).
4. From the matched client read: `city`, `state`, `brand`, `brand_tier`, `ga4_property`, `semrush_project`, `domains`, `review_name`, `crm`, `owner`.
5. **State logic for regional data:** use `state` from the registry. If blank, read `Projects/{CODE}/README.md` to find the city, then map city→state (Anaheim→California, Las Vegas→Nevada, etc.). The regional pull keys off this state.
6. If `ga4_property` is `""` → omit Traffic. If `semrush_project` is `""` and the client isn't a dealer in Semrush → omit SEO (or run a domain-only `domain_organic` if a domain exists). Non-auto `brand_tier` ("non-auto") → skip the NADA lead benchmark and pull **local small-business/economic** context instead of NADA auto data.

Post the attachment reminder (above). Wait for `go`.

---

<!-- ai-team month pack step, added 2026-09-23, scope and self-build updated 2026-09-26. Keep this section identical in the source copy (~/Desktop/Skills/skills/monthly-client-report/SKILL.md) and the runtime copy (skills-plugin/.../skills/monthly-client-report/SKILL.md). -->
## Step 0.5: Check the AI-team month pack for Google Ads, Meta, and CRM (never GA4)

The pack is `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/ai-team/ledgers/month-pack-{YYYY-MM}.json` for the report month. GA4 never comes from the pack (its daily coverage is partial and its key events include page views); Step 1 A pulls GA4 from the API every run.

1. **Build the pack yourself when it is missing or stale.** The night shift builds it only on a weekday 1st (Nov 1 2026 is a Sunday), so if the file is missing, or its `generated_at` date is on or before the last day of the report month (built before the month ended), run:
   ```bash
   python3 "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/ai-team/scripts/ledgers.py" month --month {YYYY-MM}
   ```
   It is standard library and writes only `outputs/ai-team/ledgers/month-pack-{YYYY-MM}.json` and `.md`. Then read the new file and write "month pack built at report time, generated_at {timestamp}" in the facts manifest. If the command fails, pull every source live as below and say so in the manifest.
2. Look up `stores[{CODE_UPPER}]` (the registry's `Atlas` is `ATLAS` there). For each source `google_ads`, `meta`, `crm` only:
   - `coverage.complete` is `true`: use the pack for that source and skip its pull (the attached ad file is not needed for Google or Meta numbers the pack covers). Every number taken from it goes in the facts manifest with `"source": "month-pack-{YYYY-MM}.json stores.{CODE}.{source}"`. For `crm`, the pack gives month-to-date totals and by-source rows; Step 2's score-leads grading still runs on an attached CRM file when there is one.
   - File missing, store missing, or `coverage.complete` is `false`: pull that source exactly as below, and write "month pack incomplete for {source}" in the manifest. Never mix pack numbers and a live pull for the same source.
<!-- end ai-team month pack step -->

---

## Step 1: Traffic from the GA4 API (main loop), then fan out data agents in ONE message (all `model: "sonnet"`)

Run A first in the main loop (about a second). Then send a SINGLE message with the `Agent` calls B-E (plus A-fb only when A failed on auth) so they run concurrently. Each agent is self-contained (subagents don't see this chat) and returns **only** a JSON object. Skip any step or agent whose section is omitted per Step 0.

### A. Traffic, main loop, GA4 Data API (no agent)  → `traffic`
```bash
python3 "${CLAUDE_SKILL_DIR}/ga4_month.py" --store {CODE_UPPER} --month {YYYY-MM}
```
- `{CODE_UPPER}` is the ai-team store key (`ATLAS` for the registry's `Atlas`). The script pulls the report month and the prior month (for MoM) through the ai-team `gdata.py` GA4 Data API client on Drew's OAuth token, checks the registry `ga4_property` against gdata's property map, and prints the `traffic` JSON on stdout in the generator's shape (`available`, `kpis`, `channels`, `social_referral`, `insights`) plus `source`, `manifest`, `notes`, and `ga4_month`, which the generator ignores. Warnings and notes also go to stderr.
- Use stdout as `traffic` as-is. Its lead KPI counts only lead-class key events (form, call, chat); it may print that count without a MoM % or hold it back when a tag changed or a tracking fault touched the month. Never swap in GA4's raw key-event count, which on most stores is mostly page-view events. Copy its `manifest` entries into the facts manifest and its `notes` into Drew's run summary.
- **Complete month means running on the 3rd or later.** GA4 finalizes each day about two days after it ends; the August reports pulled on 9/1 missed Aug 31 and overstated the session decline about 2.5x. An earlier run must add `--allow-partial`, which labels the KPI with the true range (for example "Sep 1-29", "Sep 30 still processing"). Carry that range label into the exec summary and the manifest, and never call a partial range the full month.
- **If it exits non-zero** (message on stderr, nothing on stdout):
  - `2` usage error (bad `--month` or `--today`, or an unknown store code): fix the command and re-run;
  - `3` date gate: wait for the 3rd, or re-run with `--allow-partial` as above;
  - `5` property mismatch or config: stop and tell Drew (the registry and gdata disagree on the property id, or the store has no GA4 property); never pick one yourself;
  - `6` API error: retry once, then tell Drew;
  - `4` auth failure (gdata missing, not authorized yet, or an expired or revoked token): confirm with `python3 "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/ai-team/scripts/gdata.py" status`, tell Drew to re-run `gdata.py auth` himself (OAuth steps are always Drew's), and add agent A-fb to the fan-out. Only an auth failure sends GA4 to the browser.

### A-fb. GA4 browser fallback agent  → `traffic`   *(only when A failed on auth)*
> Pull **{MONTH}** ({DATE_RANGE}) traffic-acquisition data from GA4 for **{CLIENT}** (property `p{GA4_PROPERTY}`), and the prior month for MoM comparison. Today is {TODAY}.
> **Surface order (Drew's 2026-09-04 rule):** (1) the Claude Browser (`mcp__Claude_Browser__tabs_create`, then `navigate`, `get_page_text`, passing your `tabId` on every call). If it lands on a Google sign-in page, that surface is exhausted; never type credentials. (2) Only then the Chrome extension, Drew's signed-in Chrome: load `mcp__claude-in-chrome__tabs_context_mcp`, `tabs_create_mcp`, `navigate`, `get_page_text` in ONE ToolSearch call and claim your OWN tab. There is no HTTP tier here (the GA4 UI needs a signed-in session and the API already failed). Two attempts per surface; if both surfaces fail, return `{"available":false,"note":"surface_exhausted"}`.
> `navigate` to `https://analytics.google.com/analytics/web/#/p{GA4_PROPERTY}/reports/explorer?params=_u.dateOption%3DcustomDateRange...&r=lifecycle-traffic-acquisition-v2` (set the custom range to the report month), wait about 20 seconds for the table, then `get_page_text`.
> Extract per channel: Channel, Sessions, Share %, Engaged sessions, Engagement rate. **Break out social referral** (Organic Social + any Facebook/Instagram/YouTube/TikTok referral, including `ig` and `fb` sources) explicitly. Compute MoM % on total sessions. Leave key events out unless you can break them down by event name to form, call, and chat events (the raw count includes page views). If the data ends before the month's last day, put the true range in the session KPI `sub`.
> Return ONLY: `{"available":true,"range":"Sep 1-30","kpis":[{"label","value","sub","status"}],"channels":[{"Channel","Sessions","Share","Eng Rate"}],"social_referral":"Facebook N, Instagram N...","insights":[{"text","type"}]}`. On failure return `{"available":false}`.

### B. SEO agent (AI-team value line first, then SEMRUSH)  → `seo`   *(skip if no semrush_project AND no domain)*
> SEO for **{DOMAIN}** (Semrush project `{SEMRUSH_PROJECT}`, database `us`) for {MONTH}. AI-team store key `{CODE_UPPER}`. Today is {TODAY}. Vault root: `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ`.
> **Read the AI-team files first.** Use only folders `outputs/ai-team/{date}/` dated within the last 30 days (Semrush ToS 3.3 caps caching at a month).
> - Newest `outputs/ai-team/*/data/value_line.json`: take the `stores` entry whose `store` is `{CODE_UPPER}`. Its figures carry their source file, section, and date. If `rank_history.caution` is set, treat its Semrush figures as a gap and re-pull them.
> - Newest `outputs/ai-team/*/data/seo_join_{CODE_UPPER}.json`: its `flags` (LEAD_LEAK, AEO_PROOF, GA4_WIN_NO_KW) are page-level insight material. Never quote its GA4 key events as leads (they include page-view events).
> Cite each figure's file and as-of month in `sources`. Semrush figures are estimates and GA4 figures are measured; keep those words in the copy.
> **Live SEMRUSH only for the gaps** those files leave. Load `mcp__781ea802-...__execute_report` + `get_report_schema` via ToolSearch. Flow: discovery → schema → execute.
> 1. `domain_rank` {domain, database:"us"} → organic_keywords, organic_traffic, authority.
> 2. `domain_organic` four ways (display_positions rise|fall|new|lost, display_limit:8) for the month → top ~8 movers with keyword/position/change/volume/type.
> 3. `siteaudit_research` for the project → health %. Omit if it errors.
> If no value_line.json exists within 30 days (the first one lands on the 2026-10-05 shift), pull live and set `"value_line":"none yet"`.
> Return ONLY: `{"available":true,"kpis":[{"label","value","sub","status"}],"movers":[{"Keyword","Position","Change","Volume","Type"}],"insights":[{"text","type"}],"sources":[{"figure","file_or_call","as_of"}],"value_line":"<file path> | none yet"}`. On failure `{"available":false}`.

### C. Reputation agent (Google + Yelp)  → `reputation`
> Pull current online reputation for **{REVIEW_NAME}** in **{CITY}, {STATE}**. Fresh live every run.
> WebSearch `"{REVIEW_NAME}" {city} reviews` to confirm the Google listing + Yelp page, then use the Chrome MCP (`navigate` + `get_page_text`) to read each.
> Capture per platform: overall star rating, total review count, and the delta vs the value stored in `Projects/{CODE}/reporting/reputation-baseline.json` if it exists (else delta "" and WRITE that file with this month's values for next time). Read the last ~20 reviews per platform for recurring positive and negative themes (3-4 each).
> Return ONLY: `{"available":true,"platforms":[{"name":"Google","rating":"4.3","reviews":"1,840","delta":"+0.1"},{"name":"Yelp",...}],"themes_positive":[...],"themes_negative":[...],"insights":[{"text","type"}]}`.

### D. Regional market agent  → `regional`
> Build the market context for **{STATE}** (the client is in {CITY}, {STATE}; brand {BRAND}; brand tier {BRAND_TIER}). Today is {TODAY}. If brand_tier is "non-auto", build **local small-business/consumer** economic context for {STATE} instead of auto data (same sourcing rules).
> 1. **Read the vault first:** `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Intelligence/market/auto-trends/Market-Read.md` (note its `updated:` date). Take figures only from its table rows and Headline numbers that carry a named source and a data period. Cite the UNDERLYING source with its period and published date (for example "CNCDA California Auto Outlook, Jul 20 2026"), never Market-Read alone, and set `vault_ref` to `Market-Read.md#<section heading>`.
> 2. **Never lift** (from Market-Read or anywhere): Outlook, Risks, throughline, or Opportunities prose; any claim tied to an event dated before today (a Fed meeting, a deadline, a launch) unless you confirmed the outcome; any "record", "peak", "high", or "lowest" claim without an as-of date.
> 3. **WebSearch only for the gaps:** OEM or brand items for {BRAND}, a {STATE} figure Market-Read lacks, or the whole block for a non-auto client. Every web stat needs the publisher, the data period, the published date, and the URL. Prefer the latest release; if the newest figure you found was published more than 45 days ago, say in `latest_release` whether a newer release exists.
> 4. **Rebates, tax credits, incentives, and named programs:** include one only after confirming on the program's own page that {BRAND} is on the participant list and every model you name meets the price cap and other eligibility terms, and record that in `eligibility`. Otherwise leave it out entirely. (The August NCBMW report told the GM to use California's $3,500 MyFirstEV rebate on i4/iX. BMW is not a participant and both models are over the $50,000 cap.)
> 5. Forecasts get `"kind":"forecast"` and "(forecast)" in the `stat` label. Brand or segment figures say so in the `stat` label.
> Pull 3-5 stats. Narrative: 1-2 sentences describing the market and how it touches {CLIENT}'s {BRAND} mix; no advice that depends on an unverified program. No em dashes.
> Return ONLY: `{"available":true,"state":"{STATE}","headline":"...","stats":[{"stat","value","source":"Publisher, Mon D YYYY","period","published":"YYYY-MM-DD","kind":"actual|forecast","scope":"brand|segment|state|national","vault_ref | url","latest_release"}],"narrative":["...","..."],"eligibility":[{"program","client_brand_listed":true,"cap","models_checked":[...],"url","published"}]}`. Exactly one of `vault_ref` or `url` per stat. The `source` string carries the published date itself so the rendered Source column shows it. Use `"eligibility":[]` when no program is mentioned.

### E. Wins agent (vault)  → `wins`
> Surface what DigitalCLIQ did for **{CLIENT}** ({CODE}) during **{MONTH}** ({YYYY}-{MM}) from the vault. NO web, NO MCP, read files only. Vault root: `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ`. Read only this client's files.
> 1. **Primary source, the client context log.** If `Projects/{CODE}/context-log-{YYYY}-{MM}.md` exists (the month has rolled over), read it in full. Otherwise read the whole {MONTH} section of `Projects/{CODE}/context-log.md`: Grep `^#{2,3} {YYYY}-{MM}-` and `^#{2,3} {Month YYYY}` with line numbers, Read from the `### {Month YYYY}` heading down to the next month heading (undated "Week of" entries included), then Read every dated entry the Grep found outside that range with offset/limit (other skills append `##` entries at the bottom of the file). Read the whole month; no 80-line cap here. A later "Correction" entry overrides what it corrects.
> 2. **Month pack wins.** `outputs/ai-team/ledgers/month-pack-{YYYY-MM}.json` → `stores.{CODE_UPPER}.wins` (asks closed with a win and evidence). Skip if the file is missing.
> 3. **Daily notes corroborate only.** Grep `Daily/{YYYY}-{MM}-*.md` (or the monthly archive `Daily/{YYYY}-{MM}.md`) and any `Projects/{CODE}/visit-notes/` file dated in the month for the client, to confirm or date what the log says. Never source a win from a Daily note alone. Any financial, vendor, cancellation, or refund claim found only in a Daily note goes to `questions_for_drew`, never `items` (the false SBMW August YouTube PreRoll win came from a Daily note).
> Dedupe. Write in Drew's teammate voice: specific work, specific outcomes, no fluff, no em dashes. Return ONLY: `{"items":["concrete win 1","..."],"challenges":["in-flight / next-up item","..."],"sources":[{"text":"<item or challenge>","file":"Projects/{CODE}/context-log.md","entry":"### YYYY-MM-DD · heading"}],"questions_for_drew":["..."]}`. 3-6 items max.

> [!note] Paid media has no live API (Google Ads CIDs aren't captured; Meta is the only ads MCP). Paid comes from Drew's **attached ad/spend file**: the main loop parses it in Step 2, not a subagent.

---

## Step 2: Lead Mix + Leads (score-leads) + Paid (attached file), in the main loop

**Lead Mix by Category (renders near the TOP of the report)**: if Drew attached a CRM file, run the helper. It reuses score-leads' cross-CRM ingest + NADA source-type classifier to bucket every source into Walk-in/Showroom, Phone, Internet (1st-party), Website Chat, 3rd-party Marketplace, OEM/Factory, Conquest/Data-list, Owned/Repeat, and Unknown/Unattributed:
```bash
python3 "${CLAUDE_SKILL_DIR}/lead_mix.py" "<attached CRM file>"
```
It prints JSON (`total_leads`, `total_sold`, `categories[]`, `phone_tracked`). A non-zero exit or `"available": false` is a failure, not an empty section (see the failure rule below). Drop it straight into the merged JSON as `lead_mix` and add one insight (which categories dominate volume vs which actually close). If `phone_tracked` is false, the generator auto-notes that phone-ups aren't tracked as a source. This is the executive lead breakdown Drew wants prominent. If no CRM file, omit `lead_mix`.

**Leads (detailed, NADA benchmark)**: if Drew attached a CRM file, run the existing scorer (it handles VinSolutions/Momentum/Tekion/PDF/CSV and the NADA benchmark by brand tier):
```bash
python3 "${CLAUDE_SKILL_DIR}/../score-leads/score_leads.py" \
  --raw "<attached CRM file>" "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/mcr_leads_{CODE}_{YYYY-MM}.xlsx" "{CLIENT}" "{MONTH}" --no-rollup
```
The xlsx lands in `outputs/` because score-leads runs its own post-flight, which rejects `/tmp`. It is a working file: never file it to the client folder. Read its printed SUMMARY block (close rate, per-source grades, vs-benchmark verdict) and shape the `leads` JSON: `summary`, `kpis`, `nada` ({store_close_rate, benchmark, verdict, status}), `sources` (top 5-6), `insights`. If no CRM file: omit `leads`.

**Failure rule when a CRM file IS attached.** Lead Mix and Leads are required then, not optional. If `lead_mix.py` or `score_leads.py` exits non-zero or returns `available:false`, do not drop the section: read the error, fix the real cause (for example re-export the file, or pre-normalize it to score-leads' ingest columns), re-run, and put the failure and the fix in the run summary. If it still fails, stop and ask Drew whether to ship without that section. Never omit it silently.

**Paid**: if Drew attached an ad/spend file (CSV/PDF), parse it (python `csv`/`openpyxl`, or the Read tool for PDF) into `paid`: spend, clicks, conversions, CPA, conv rate as `kpis`; top campaigns as `sources`; 1-2 reallocation `insights`. If no file: omit `paid`.

---

## Step 3: Merge to JSON

Build `/tmp/mcr_{CODE}_{MONTH}.json` with: `metadata` (client_name, client_code, month_label, city, state, brand), `exec_summary` (3-4 sentence teammate-voice narrative synthesizing the month, the most important things, what moved, what's next), then `traffic`, `paid`, `seo`, `leads`, `reputation`, `regional`, `wins`. **Omit any section that came back `available:false` or empty**, the generator renders only what's present. The one exception is `lead_mix` and `leads` when a CRM file was attached: Step 2's failure rule applies instead. No em dashes in any string. Never include `digitalcliq@gmail.com` (the generator hard-rejects it; use `drewmoon@digitalcliq.com`).

## Step 4: Render

```bash
python3 "${CLAUDE_SKILL_DIR}/generate_monthly_report.py" \
  "/tmp/mcr_{CODE}_{MONTH}.json" \
  "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/MonthlyReport_{ClientShort}_{YYYY-MM}.pdf" \
  "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png"
```

The generator builds the report on the canonical design-system pipeline: hand-authored HTML + CSS (tokens, component library, canonical `cover-portrait.html` dark cover, running furniture) rendered by Chrome headless `--print-to-pdf`, the declared engine on this Mac (WeasyPrint's system libraries are not installed; never install pango or Homebrew to change engines, because layouts are tuned on Chrome). The generator gives Chrome 180 seconds and raises an error naming the engine if it stalls, so run the generator's Bash call with a timeout of at least 200000 ms. Fonts embed via `@font-face` from `Resources/brand-assets/fonts/` and the render FAILS loudly if a brand font or logo is missing, no silent substitution. Output: dark cover + 2-3 light interior pages; sections auto-pack and gracefully omit anything missing.

## Step 5: Validate, then review (the "would Drew like it" gate). MANDATORY

Order per Rule 22: the mechanical validator first, then the reviewer.

**5a. Shared validator:**
```bash
python3 "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/post_flight.py" "<pdf path>" --min-pages 2
```
On failure: diagnose from the output, fix the real cause (re-fetch empty data, fix logo path, move file into `outputs/`), regenerate ONCE, re-validate. Never report success on a failed validation. Never wrap this in `|| true`.

**5b. Reviewer: run the Final QA Gate at the end of this skill.** The shared **`deliverable-reviewer` agent** (fresh eyes: it did not write the report) does the read, never the main loop reading its own work. That gate is the only reviewer loop for this skill: max 2 reviewer passes, stop after the first clean one, and remaining CRITICAL/MAJOR findings block the ship. The design-system block's "two consecutive fully-clean passes" (item 7) is the render_check.py render gate, which the reviewer runs inside each pass; it does not add passes. For this report the facts manifest names, per figure: GA4 from ga4_month.py's `manifest` entries (or the browser range from A-fb); pack figures as `month-pack-{YYYY-MM}.json stores.{CODE}.{source}` (plus "built at report time" when Step 0.5 built it); SEO figures with their value_line or seo_join file and as-of month, or the Semrush call; every Market Context stat with its underlying source, period, and published date; every win with its context-log file and entry date. **Pass checks 1-9 below to the reviewer verbatim; do not rewrite, drop, or soften them.** The report-specific checks the agent must apply:

1. **Numbers reconcile** across sections (e.g. paid-search sessions ≈ paid conversions story; lead totals match the close-rate math). No contradictions.
2. **No empty/orphan sections, no placeholders**, no "{token}" or literal YYYY-MM.
3. **Logos render** crisp: WHITE knockout on the dark cover, FULL-COLOR mark in the interior running furniture (never swapped). Colors on-palette per the Design-System token table only. Headings/stats render as Dosis and body as Roboto Slab; a Helvetica/Arial-looking render = FAIL (fonts did not embed).
4. **Names correct** per the facts ledger (client + any competitor). BMW of Buena Park = AutoNation; LOGO Cargo = hostile, not partner.
5. **Voice** sounds like a DigitalCLIQ teammate, not generic AI. Specific names, specific consequences. No em dashes. Not a wall of text.
6. **Wins section** reflects the actual vault work for the month, not vague filler.
6b. **Recency + real-world sanity check (REQUIRED):** every vault-sourced claim in wins/challenges must still be TRUE as of the report month, not just present in a note. Check the date on the source note and whether a later note supersedes it (a vendor "flagged as a problem" in an old note may have been cancelled since). If a claim is stale, unverifiable, or names a vendor/program whose status you cannot confirm is current, cut it from the client PDF and surface it to Drew for confirmation rather than shipping it. A financial, vendor, cancellation, or refund claim whose only source is a Daily note is always cut and asked of Drew. Vault presence is necessary but not sufficient.
7. **Client-facing sanitization (REQUIRED):** this PDF is written to be handed to the client's GM. Strip anything internal-only before it ships: candid margin/gross commentary ("gross is soft"), pressure on the dealer principal, legal/settlement or review-removal matters, vendor contract gripes framed as complaints, and NEVER name an individual employee negatively (generalize "the finance office", not "Josh"). Positive employee shout-outs are fine. When in doubt, cut it and mention it to Drew verbally.
8. **Length** is 2-3 pages. If it sprawled to 4+, tighten the JSON (fewer table rows, shorter insights) and re-render.
9. **Market Context sourcing:** every stat shows its source and a date in the rendered Source column, and forecasts say "(forecast)"; a stat without a date is a finding to fix. A rebate, tax credit, incentive, or named-program recommendation with no matching `eligibility` record (client brand listed, every named model under the cap) is CRITICAL: cut the line and tell Drew. A "record/peak/high" claim with no as-of date, or a claim about an event dated before the run date stated as upcoming, gets cut.

## Step 6: File + present

1. `mkdir -p Projects/{CODE}/deliverables` and `mv` the final PDF from `outputs/` into `Projects/{CODE}/deliverables/`. (outputs/ is staging; per facts ledger rule 17 finished client deliverables get filed to the owning client folder.)
2. Add a `### {YYYY-MM-DD} · Monthly report` entry (today's date) at the top of `Projects/{CODE}/context-log.md`, directly under the current month heading (`### {Month YYYY}` for today's month; if that heading does not exist yet, add it above the previous month's heading; a log with no month headings takes the entry above its newest entry). One or two lines: the `[[Projects/{CODE}/deliverables/{file}.pdf]]` wikilink, the month covered, and anything still waiting on Drew. Never write run history into `README.md` (the running history moved to the context log on 2026-07-13).
3. Hand Drew the file path + a 3-5 bullet executive summary of what's inside, the QA line, ga4_month.py's `notes` and any partial-range label, and every open question (the Wins agent's `questions_for_drew`, any program or incentive line that was cut). **Nothing leaves to the client until Drew says so.**

---

## Scheduling (3rd of the month or later)

When Drew wants these automated, use the `schedule` skill to create a cloud routine per client, e.g. on the 3rd at 7am (the first day GA4 has the whole prior month): `/monthly-client-report mcp`. Set the scheduled run's **model to Sonnet** so the automated monthly fires cheap. Note: scheduled runs can't receive chat attachments, so a fully-automated run will omit the leads/paid sections that need Drew's files unless the CRM/ad export is dropped into a known folder first, for those, schedule a reminder instead of a headless run, or wire the export to `01_Inbox/` and point Step 2 there.

## Speed & token rules (DO NOT VIOLATE)
- All data agents launch in ONE message, all `model: "sonnet"`.
- Main loop never calls `navigate`/`execute_report`/`WebSearch` directly, only subagents do. (The main loop does run the Bash scripts: `ga4_month.py`, the Step 0.5 pack build, `lead_mix.py`, `score_leads.py`, the generator, and `post_flight.py`.)
- Each browser agent (A-fb, reputation) claims its OWN tab and passes its `tabId` on every call; never touch another agent's tab.
- Omit missing sections; never fabricate. Always deliver with whatever data IS available.

## Final QA Gate: deliverable-reviewer agent (MANDATORY, added 2026-08-13)

Runs AFTER the deliverable is generated and post_flight.py passes, BEFORE filing/presenting. post_flight.py is mechanical; this gate is the human-style read.

1. **Write a facts manifest** next to the deliverable in `outputs/`: a JSON list of every number, name, date, and claim that appears in the deliverable, each as `{"value": ..., "label": "where it appears", "source": "tool/file/URL it came from"}`. Build it from data already in context, never re-fetch anything just for the manifest.
2. **Spawn the `deliverable-reviewer` agent** (fresh eyes, it did not write the report). Pass in the prompt: the absolute path(s) of the finished deliverable file(s), the manifest path, and any skill-specific checks from this SKILL.md. It renders every page, reads them all, cross-checks figures against the manifest, and reviews tone/copy.
3. **Auto-fix every finding** in the source generator or data (never by hand-editing the output), re-render, and re-run the agent once. Max 2 review passes. If CRITICAL or MAJOR findings remain after pass 2, the ship is BLOCKED: report the remaining findings to Drew verbatim instead of presenting the file as done.
4. The run summary MUST include a **QA line**: what the reviewer caught and what was fixed, or "QA: clean on first pass (N pages read, M figures verified)". Never silently skip the gate; if the agent could not run, say so explicitly in the delivery message.
