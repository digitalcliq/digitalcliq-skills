---
name: monthly-client-report
description: Generate a branded DigitalCLIQ monthly performance report for a client. Pulls the PREVIOUS month's GA4 traffic (incl. social referral), Google/Meta paid media, SEMRUSH SEO, CRM lead data scored against NADA close rates, Google + Yelp reputation, and regional NADA/economic data for the client's state. Surfaces "DigitalCLIQ & {client} wins this month" from vault visit notes. Renders a tight 2-3 page PDF, self-reviews it, and files it to the client folder. Use when Drew says /monthly-client-report, "monthly report for [client]", or schedules a monthly client report.
argument-hint: "<client code | name | website>  [--month YYYY-MM]"
allowed-tools: Agent, Read, Write, Glob, Grep, Bash(python3 *), Bash(pip3 install *), Bash(mkdir *), Bash(mv *), Bash(ls *)
---

> [!important] Pre-flight: load the facts ledger FIRST
> Read `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Context/vault-facts.md` and obey it before anything else. It is the source of truth for: the `outputs/` path, the canonical logo (WHITE mark on blue masthead only), and correct client/competitor names (e.g. "BMW of Buena Park (AutoNation)" not "Shelly BMW"; LOGO Cargo is a HOSTILE Atlas competitor, never a partner). Vault names beat web research.

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
2. Load `reference/client_registry.json`. Match the arg against `code`, `aliases`, or `domains` (lowercase, strip `www.`/`https://`). If a website was given and isn't in the registry, infer brand/city from the site + a quick WebSearch, then proceed.
3. Default `--month` to the **previous calendar month** (today is the 1st/2nd when scheduled). Build `month_label` ("May 2026") and the date range.
4. From the matched client read: `city`, `state`, `brand`, `brand_tier`, `ga4_property`, `semrush_project`, `domains`, `review_name`, `crm`, `owner`.
5. **State logic for regional data:** use `state` from the registry. If blank (e.g. CDHD), read `Projects/{CODE}/README.md` to find the city, then map city→state (Anaheim→California, Las Vegas→Nevada, etc.). The regional pull keys off this state.
6. If `ga4_property` is `""` → omit Traffic. If `semrush_project` is `""` and the client isn't a dealer in Semrush → omit SEO (or run a domain-only `domain_organic` if a domain exists). Non-auto `brand_tier` ("non-auto") → skip the NADA lead benchmark and pull **local small-business/economic** context instead of NADA auto data.

Post the attachment reminder (above). Wait for `go`.

---

## Step 1: Fan out data agents in ONE message (all `model: "sonnet"`)

Send a SINGLE message with these `Agent` calls so they run concurrently. Each is self-contained (subagents don't see this chat) and returns **only** a JSON object. Skip any agent whose section is omitted per Step 0.

### A. GA4 Traffic agent  → `traffic`
> Pull **{MONTH}** (full month, {DATE_RANGE}) traffic-acquisition data from GA4 for **{CLIENT}** (property `p{GA4_PROPERTY}`), and the prior month for MoM comparison.
> Load via ToolSearch in one call: `mcp__claude-in-chrome__tabs_context_mcp`, `tabs_create_mcp`, `navigate`, `get_page_text`.
> Steps: `tabs_context_mcp(createIfEmpty:true)` → `tabs_create_mcp` (claim your OWN tab) → `navigate` to
> `https://analytics.google.com/analytics/web/#/p{GA4_PROPERTY}/reports/explorer?params=_u.dateOption%3DcustomDateRange...&r=lifecycle-traffic-acquisition-v2` (set the custom range to the report month) → `Bash: sleep 20` → `get_page_text`; retry up to 3×.
> Extract per channel: Channel, Sessions, Share %, Engaged sessions, Engagement rate, Key events. **Break out social referral** (Organic Social + any Facebook/Instagram/YouTube/TikTok referral) explicitly. Compute MoM % on total sessions.
> Return ONLY: `{"available":true,"kpis":[{"label","value","sub","status"}],"channels":[{"Channel","Sessions","Share","Eng Rate","Key Events"}],"social_referral":"Facebook N, Instagram N...","insights":[{"text","type"}]}`. On failure return `{"available":false}`.

### B. SEO agent (SEMRUSH)  → `seo`   *(skip if no semrush_project AND no domain)*
> Pull SEMRUSH SEO for **{DOMAIN}** (project `{SEMRUSH_PROJECT}`), database `us`, for {MONTH}.
> Load `mcp__781ea802-...__execute_report` + `get_report_schema` via ToolSearch. Flow: discovery → schema → execute.
> 1. `domain_rank` {domain, database:"us"} → organic_keywords, organic_traffic, authority.
> 2. `domain_organic` four ways (display_positions rise|fall|new|lost, display_limit:8) for the month → top ~8 movers with keyword/position/change/volume/type.
> 3. `siteaudit_research` for the project → health %. Omit if it errors.
> Return ONLY: `{"available":true,"kpis":[{"label","value","sub","status"}],"movers":[{"Keyword","Position","Change","Volume","Type"}],"insights":[{"text","type"}]}`. On failure `{"available":false}`.

### C. Reputation agent (Google + Yelp)  → `reputation`
> Pull current online reputation for **{REVIEW_NAME}** in **{CITY}, {STATE}**. Fresh live every run.
> WebSearch `"{REVIEW_NAME}" {city} reviews` to confirm the Google listing + Yelp page, then use the Chrome MCP (`navigate` + `get_page_text`) to read each.
> Capture per platform: overall star rating, total review count, and the delta vs the value stored in `Projects/{CODE}/reporting/reputation-baseline.json` if it exists (else delta "" and WRITE that file with this month's values for next time). Read the last ~20 reviews per platform for recurring positive and negative themes (3-4 each).
> Return ONLY: `{"available":true,"platforms":[{"name":"Google","rating":"4.3","reviews":"1,840","delta":"+0.1"},{"name":"Yelp",...}],"themes_positive":[...],"themes_negative":[...],"insights":[{"text","type"}]}`.

### D. Regional market agent  → `regional`
> Pull current automotive market + economic data for **{STATE}** (the client is in {CITY}, {STATE}; brand {BRAND}). If brand_tier is "non-auto", pull **local small-business/consumer** economic context for {STATE} instead of auto data.
> WebSearch in parallel: `{STATE} new vehicle registrations sales {YEAR}`, `{STATE} auto incentive spend transaction price {YEAR}`, `{STATE} economy consumer {MONTH} {YEAR}`. Pull 3-5 stats, each with a named source + date. Tie 1-2 narrative points to how it affects {CLIENT}'s {BRAND} mix.
> Return ONLY: `{"available":true,"state":"{STATE}","headline":"...","stats":[{"stat","value","source"}],"narrative":["...","..."]}`.

### E. Wins agent (vault)  → `wins`
> Surface what DigitalCLIQ did for **{CLIENT}** ({CODE}) during **{MONTH}** from the vault. NO web, NO MCP, read files only.
> Read `Projects/{CODE}/README.md` → the **Running Context Log** and **Monthly Wins / Challenges Log** sections; collect entries dated within {MONTH}. Read `Projects/{CODE}/visit-notes/*.md` for any dated in {MONTH}. Grep `Daily/{YEAR}-{MM}-*.md` for lines tagged/mentioning the client. Dedupe.
> Write in Drew's teammate voice: specific work, specific outcomes, no fluff. Return ONLY: `{"items":["concrete win 1","..."],"challenges":["in-flight / next-up item","..."]}`. 3-6 items max.

> [!note] Paid media has no live API (Google Ads CIDs aren't captured; Meta is the only ads MCP). Paid comes from Drew's **attached ad/spend file**: the main loop parses it in Step 2, not a subagent.

---

## Step 2: Lead Mix + Leads (score-leads) + Paid (attached file), in the main loop

**Lead Mix by Category (renders near the TOP of the report)**: if Drew attached a CRM file, run the helper. It reuses score-leads' cross-CRM ingest + NADA source-type classifier to bucket every source into Walk-in/Showroom, Phone, Internet (1st-party), Website Chat, 3rd-party Marketplace, OEM/Factory, Conquest/Data-list, Owned/Repeat, and Unknown/Unattributed:
```bash
python3 /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/monthly-client-report/lead_mix.py "<attached CRM file>"
```
It prints JSON (`total_leads`, `total_sold`, `categories[]`, `phone_tracked`). Drop it straight into the merged JSON as `lead_mix` and add one insight (which categories dominate volume vs which actually close). If `phone_tracked` is false, the generator auto-notes that phone-ups aren't tracked as a source. This is the executive lead breakdown Drew wants prominent. If no CRM file, omit `lead_mix`.

**Leads (detailed, NADA benchmark)**: if Drew attached a CRM file, run the existing scorer (it handles VinSolutions/Momentum/Tekion/PDF/CSV and the NADA benchmark by brand tier):
```bash
python3 /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/score-leads/score_leads.py \
  --raw "<attached CRM file>" "/tmp/mcr_leads_{CODE}.xlsx" "{CLIENT}" "{MONTH}" --no-rollup
```
Read its printed SUMMARY block (close rate, per-source grades, vs-benchmark verdict) and shape the `leads` JSON: `summary`, `kpis`, `nada` ({store_close_rate, benchmark, verdict, status}), `sources` (top 5-6), `insights`. If no CRM file: omit `leads`.

**Paid**: if Drew attached an ad/spend file (CSV/PDF), parse it (python `csv`/`openpyxl`, or the Read tool for PDF) into `paid`: spend, clicks, conversions, CPA, conv rate as `kpis`; top campaigns as `sources`; 1-2 reallocation `insights`. If no file: omit `paid`.

---

## Step 3: Merge to JSON

Build `/tmp/mcr_{CODE}_{MONTH}.json` with: `metadata` (client_name, client_code, month_label, city, state, brand), `exec_summary` (3-4 sentence teammate-voice narrative synthesizing the month, the most important things, what moved, what's next), then `traffic`, `paid`, `seo`, `leads`, `reputation`, `regional`, `wins`. **Omit any section that came back `available:false` or empty**, the generator renders only what's present. Never include `digitalcliq@gmail.com` (the generator hard-rejects it; use `drewmoon@digitalcliq.com`).

## Step 4: Render

```bash
python3 /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/monthly-client-report/generate_monthly_report.py \
  "/tmp/mcr_{CODE}_{MONTH}.json" \
  "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/MonthlyReport_{ClientShort}_{YYYY-MM}.pdf" \
  "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png"
```

The generator builds the report on the canonical design-system pipeline: hand-authored HTML + CSS (tokens, component library, canonical `cover-portrait.html` dark cover, running furniture) rendered by WeasyPrint when importable, else Chrome headless `--print-to-pdf` (the documented fallback, no install needed). Fonts embed via `@font-face` from `Resources/brand-assets/fonts/` and the render FAILS loudly if a brand font or logo is missing, no silent substitution. Output: dark cover + 2-3 light interior pages; sections auto-pack and gracefully omit anything missing.

## Step 5: Self-review loop (the "would Drew like it" gate). MANDATORY

As of 2026-08-13 this review is performed by the shared **`deliverable-reviewer` agent** (fresh eyes: it did not write the report), not by the main loop reading its own work. Before spawning it, write a **facts manifest** JSON next to the PDF in `outputs/`: every number, name, date, and claim in the report as `{"value": ..., "label": "where it appears", "source": "tool/file it came from"}`, built from data already in context (never re-fetch for the manifest). Then spawn the agent with: the PDF's absolute path, the manifest path, and checks 1-8 below as the skill-specific checklist. The agent runs render_check.py, reads every page, cross-checks figures against the manifest, and reports findings. The MAIN LOOP fixes every finding in the generator or the JSON (never by hand-editing the output), re-renders, and re-runs the agent, until **two consecutive fully-clean passes** (cap: 3 agent runs; if CRITICAL/MAJOR findings remain, ship is BLOCKED and the findings go to Drew verbatim). The run summary must include a QA line: what the reviewer caught and what was fixed, or "QA: clean (N pages read, M figures verified)". The report-specific checks the agent must apply:

1. **Numbers reconcile** across sections (e.g. paid-search sessions ≈ paid conversions story; lead totals match the close-rate math). No contradictions.
2. **No empty/orphan sections, no placeholders**, no "{token}" or literal YYYY-MM.
3. **Logos render** crisp: WHITE knockout on the dark cover, FULL-COLOR mark in the interior running furniture (never swapped). Colors on-palette per the Design-System token table only. Headings/stats render as Dosis and body as Roboto Slab; a Helvetica/Arial-looking render = FAIL (fonts did not embed).
4. **Names correct** per the facts ledger (client + any competitor). BMW of Buena Park = AutoNation; LOGO Cargo = hostile, not partner.
5. **Voice** sounds like a DigitalCLIQ teammate, not generic AI. Specific names, specific consequences. No em dashes. Not a wall of text.
6. **Wins section** reflects the actual vault work for the month, not vague filler.
6b. **Recency + real-world sanity check (REQUIRED):** every vault-sourced claim in wins/challenges must still be TRUE as of the report month, not just present in a note. Check the date on the source note and whether a later note supersedes it (a vendor "flagged as a problem" in an old note may have been cancelled since). If a claim is stale, unverifiable, or names a vendor/program whose status you cannot confirm is current, cut it from the client PDF and surface it to Drew for confirmation rather than shipping it. Vault presence is necessary but not sufficient.
7. **Client-facing sanitization (REQUIRED):** this PDF is written to be handed to the client's GM. Strip anything internal-only before it ships: candid margin/gross commentary ("gross is soft"), pressure on the dealer principal, legal/settlement or review-removal matters, vendor contract gripes framed as complaints, and NEVER name an individual employee negatively (generalize "the finance office", not "Josh"). Positive employee shout-outs are fine. When in doubt, cut it and mention it to Drew verbally.
8. **Length** is 2-3 pages. If it sprawled to 4+, tighten the JSON (fewer table rows, shorter insights) and re-render.

Then run the shared validator:
```bash
python3 /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/post_flight.py "<pdf path>" --min-pages 2
```
On failure: diagnose from the output, fix the real cause (re-fetch empty data, fix logo path, move file into `outputs/`), regenerate ONCE, re-validate. Never report success on a failed validation. Never wrap this in `|| true`.

## Step 6: File + present

1. `mkdir -p Projects/{CODE}/deliverables` and `mv` the final PDF from `outputs/` into `Projects/{CODE}/deliverables/`. (outputs/ is staging; per facts ledger rule 17 finished client deliverables get filed to the owning client folder.)
2. Append a one-line entry to `Projects/{CODE}/README.md` Running Context Log noting the monthly report was generated, with the [[deliverables/...]] wikilink.
3. Hand Drew the file path + a 3-5 bullet executive summary of what's inside. **Nothing leaves to the client until Drew says so.**

---

## Scheduling (1st/2nd of the month)

When Drew wants these automated, use the `schedule` skill to create a cloud routine per client, e.g. on the 2nd at 7am: `/monthly-client-report mcp`. Set the scheduled run's **model to Sonnet** so the automated monthly fires cheap. Note: scheduled runs can't receive chat attachments, so a fully-automated run will omit the leads/paid sections that need Drew's files unless the CRM/ad export is dropped into a known folder first, for those, schedule a reminder instead of a headless run, or wire the export to `01_Inbox/` and point Step 2 there.

## Speed & token rules (DO NOT VIOLATE)
- All data agents launch in ONE message, all `model: "sonnet"`.
- Main loop never calls `navigate`/`execute_report`/`WebSearch` directly, only subagents do.
- Each GA4/reputation agent claims its OWN Chrome tab; never touch another agent's tab.
- Omit missing sections; never fabricate. Always deliver with whatever data IS available.

## Final QA Gate: deliverable-reviewer agent (MANDATORY, added 2026-08-13)

Runs AFTER the deliverable is generated and post_flight.py passes, BEFORE filing/presenting. post_flight.py is mechanical; this gate is the human-style read.

1. **Write a facts manifest** next to the deliverable in `outputs/`: a JSON list of every number, name, date, and claim that appears in the deliverable, each as `{"value": ..., "label": "where it appears", "source": "tool/file/URL it came from"}`. Build it from data already in context, never re-fetch anything just for the manifest.
2. **Spawn the `deliverable-reviewer` agent** (fresh eyes, it did not write the report). Pass in the prompt: the absolute path(s) of the finished deliverable file(s), the manifest path, and any skill-specific checks from this SKILL.md. It renders every page, reads them all, cross-checks figures against the manifest, and reviews tone/copy.
3. **Auto-fix every finding** in the source generator or data (never by hand-editing the output), re-render, and re-run the agent once. Max 2 review passes. If CRITICAL or MAJOR findings remain after pass 2, the ship is BLOCKED: report the remaining findings to Drew verbatim instead of presenting the file as done.
4. The run summary MUST include a **QA line**: what the reviewer caught and what was fixed, or "QA: clean on first pass (N pages read, M figures verified)". Never silently skip the gate; if the agent could not run, say so explicitly in the delivery message.
