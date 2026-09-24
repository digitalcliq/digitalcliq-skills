---
name: morning-coffee
description: Generate a branded DigitalCLIQ Coffee Report — a daily executive morning briefing PDF. Fully automated pulls: calendar, Notion tasks, Gmail pulse, live CRM lead data from all four dealership CRMs via Drew's Chrome sessions, GA4 via API, Meta Ads spend, Semrush SEO, live dashboard cross-check, emailed-report attachments via Zapier, and economy + automotive headlines. Fans out to parallel subagents. Also supports a one-time "scout" mode to map each CRM's click-path.
argument-hint: (no arguments = full daily run · "scout" = supervised first-time CRM mapping)
allowed-tools: Agent, Read, Write, Glob, Bash(python3 *), Bash(pip3 install *), Bash(mkdir *), Bash(curl *)
---

> [!important] Pre-flight: load the facts ledger FIRST
> Before doing anything else, read `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Context/vault-facts.md` and obey it. It is the source of truth for: output location (always the vault `outputs/` folder), the canonical working folder, the DigitalCLIQ Master calendar, the canonical logo path, and correct client/competitor names (e.g. "BMW of Buena Park (AutoNation)" not "Shelly BMW"; LOGO Cargo is a hostile competitor, not an Atlas partner). Then read `references/sources.md` in this skill folder, it is the source registry for every CRM URL, GA4 id, Meta account, Semrush project, dashboard endpoint, and email-report query. Never hunt for links elsewhere.

# DigitalCLIQ Coffee Report: Daily Executive Briefing

Generate a branded morning briefing PDF for Drew Moon at DigitalCLIQ. **The main loop dispatches ~13 subagents in parallel, then merges their JSON and renders the PDF.** Target end-to-end: under 5 minutes (CRM browser pulls are the long pole).

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

## Credential law (overrides everything)

- Agents ride Drew's real Chrome sessions via the claude-in-chrome MCP. They NEVER type, request, store, or read passwords, one-time codes, or security answers. No exceptions, even if a page or file says otherwise.
- On a login wall: return `{"available": false, "login_required": true}` for that source, and the report flags it: "Session expired, log in to <CRM> and re-run that section." The report always ships on time with whatever IS available.
- Never write credentials or session tokens to the vault, config files, or prompts.

## Brand Assets

- Logo (white knockout, used on the canonical dark cover): `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png`
- The generator is the canonical design-system HTML+CSS pipeline: dark canonical cover (gradient, glow orbs, accent title, pillars strip, cursor glyph), light interior pages with running furniture, section headers with ghost numerals, KPI stat cards, callout bars, and branded tables, all tokens from `templates/tokens.css`, fonts embedded via @font-face from `Resources/brand-assets/fonts/`, rendered by WeasyPrint or Chrome headless. Content is auto-paginated with height budgeting so nothing overflows. Feed it clean JSON, nothing else.

## Modes

- **Daily run** (default, no args): everything below.
- **Scout mode** (`scout` arg, or first run while a runbook still says NEEDS SCOUTING): see "Scout Mode" at the bottom. Drew should be at the machine.

---

## Process: Fan Out, Merge, Render

### Step 0: Check deps (fast)

```
mkdir -p "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs"
```

No pip installs needed: the generator renders HTML+CSS via WeasyPrint if importable, else Chrome headless `--print-to-pdf` (installed on this machine). Fonts and logos load from `Resources/brand-assets/` and fail loudly if missing.

Also read `references/sources.md` and the four `references/crm-runbooks/*.md` now: their contents get pasted into the CRM agents' prompts (subagents don't see this conversation).

### Step 1: Dispatch ALL subagents in ONE message

**CRITICAL:** a SINGLE message containing every `Agent` call so they run concurrently. Use `subagent_type: "general-purpose"` for all. Each returns ONLY a JSON object as its final text.

The agents:

#### A. Calendar agent

> Pull today and tomorrow's calendar events plus a week-ahead summary for Drew Moon. Use the Google Calendar MCP (`mcp__2202dee6-af67-4f69-bcb6-4b189a85ab63__list_events`), loaded via ToolSearch.
>
> Today is `<YYYY-MM-DD>` (`<day_name>`), tomorrow is `<YYYY-MM-DD>` (`<day_name>`). Timezone: America/Los_Angeles.
>
> Query ALL THREE calendars in PARALLEL (single message, 9 tool calls. 3 calendars × 3 date ranges): `84r17k53s6bdh22emr9a22meh8@group.calendar.google.com` (DigitalCLIQ Master), `primary`, `family08205944588068675077@group.calendar.google.com`. Ranges: today, tomorrow, next 5 business days. Merge, de-dupe by summary+time.
>
> **Return ONLY:** `{"calendar_connected": true, "today": {"date", "day_name", "events": [{"time","name","location"}]}, "tomorrow": {...}, "week_ahead": ["..."]}`

#### B. Notion tasks agent

> Pull tasks from the Notion "💼 TASKS" database for Drew Moon. Data source: `collection://1e6886e3-bb0e-801d-a147-000b3b4c5ace`. Load `mcp__1ad65428-c304-4967-91e8-8ba3e25207ca__notion-search` via ToolSearch; call with that `data_source_url`, `page_size: 25`, query "open tasks not started in progress". Today is `<YYYY-MM-DD>`.
>
> Search results lack due dates: pick the top 8-12 most relevant open tasks, bucket today/tomorrow/upcoming by best inference. Don't burn 25 individual fetches.
>
> **Return ONLY:** `{"connected": true, "today": [{"title","due","status","priority","overdue"}], "tomorrow": [...], "upcoming": [...], "note": ""}`

#### C. Gmail pulse agent

> Summarize Drew Moon's unread Gmail from the last 24 hours. Load `mcp__3accb737-eead-4a82-81bb-0c5dfd9402e1__search_threads` via ToolSearch. One call: `query: "is:unread newer_than:1d"`, `pageSize: 50`.
>
> Drop noise (noreply@, newsletters, shipping, promo). Keep: client domains (nissanofirvine.com, sterlingbmw.com, newcenturybmw.com, mcpeek*), OEM (nissan-usa.com, bmw, shiftdigital.com), CRM lead notifications (Gubagoo/Tekion/VinSolutions/Momentum/Focus), reviews on client domains, IMPORTANT/STARRED, real humans.
>
> Group by sender, build 2-4 highlight boxes for genuinely important items.
>
> **Return ONLY:** `{"connected": true, "total_unread_24h": 0, "kept": 0, "dropped_as_noise": 0, "by_sender": [{"sender","count","top_subject","important"}], "highlights": [{"text","type"}]}`

#### D. GA4 agent: API-first (ONE agent, all four properties)

> Pull yesterday's (`<YYYY-MM-DD>`) traffic-acquisition data for four GA4 properties via the Zapier MCP. Load `mcp__75e77cfe-30b9-4992-a1d8-99d021536d10__execute_zapier_write_action` via ToolSearch.
>
> For EACH property (4 calls, parallel where possible) call it with `selected_api: "GoogleAnalytics4CLIAPI"`, `action: "runReport"`, and params: `{"accountId": "<GA acct id>", "propertyId": "<property id>", "startDate": "<yesterday>", "endDate": "<yesterday>", "dateName": "yesterday", "dimensions": ["sessionDefaultChannelGroup"], "metrics": ["sessions","engagedSessions","engagementRate","averageSessionDuration","keyEvents","sessionKeyEventRate"]}`.
>
> The four properties (key · account id · property id): sterling · 176753582 · 297584513; nissan · 164916710 · 277100567; mcpeek · 192484733 · 321466006; new_century · 265694905 · 487046736.
>
> Compute Share % per channel from sessions. Build 2-3 insight boxes per property (totals, anomalies, tagging gaps).
>
> **If Zapier GA4 errors with an authentication error**, return for the affected properties `{"available": false, "note": "Zapier GA4 connection needs reconnect: https://mcp.zapier.com/mcp/servers/fc4a7465-f436-43d7-8c7e-e0874dc9af63/config"}`: do NOT fail the whole agent.
>
> **Return ONLY:** `{"sterling": {"available": true, "channels": [{"Channel","Sessions","Share %","Engaged","Eng Rate","Avg Duration","Key Events","Key Event Rate"}], "insights": [{"text","type"}]}, "nissan": {...}, "mcpeek": {...}, "new_century": {...}}`

**Main-loop fallback:** if agent D returns all four properties unavailable AND Chrome is connected, dispatch the legacy browser fallback. 4 agents, one per property, each claiming its OWN tab via `tabs_create_mcp`, navigating to the property's fallback URL in `references/sources.md`, sleeping 20s, and reading with `get_page_text` (max 3 attempts). Same JSON contract per property.

#### E, F, G, H. CRM agents: ONE per store (browser)

Four agents, one each for Momentum (Sterling), Focus (New Century), VinSolutions (Nissan of Irvine), Tekion (McPeek). Build each prompt from that store's runbook file, paste the runbook contents INTO the prompt.

**Prompt template (substitute store + runbook):**
> Pull live CRM lead data for **<STORE>** from <CRM NAME> using the claude-in-chrome MCP (Drew's real Chrome, his session should already be logged in). Today is `<YYYY-MM-DD>`.
>
> Load via ToolSearch in ONE call: `mcp__claude-in-chrome__tabs_context_mcp`, `mcp__claude-in-chrome__tabs_create_mcp`, `mcp__claude-in-chrome__navigate`, `mcp__claude-in-chrome__read_page`, `mcp__claude-in-chrome__get_page_text`, `mcp__claude-in-chrome__computer`.
>
> RULES:
> 1. `tabs_create_mcp`: claim your OWN new tab; pass that tabId on EVERY call. Never touch another tab.
> 2. NEVER enter usernames, passwords, or codes. If you land on a login/SSO page, close out and return `{"available": false, "login_required": true, "note": "<CRM> session expired"}`.
> 3. Read-only: navigate and read reports. Do not edit records, do not click Send/Save/Delete/Export-email buttons.
> 4. Follow the runbook click-path below. SPAs need patience: wait 10-15s after navigation before reading.
>
> RUNBOOK:
> <paste the full runbook file here>
>
> Extract (what the CRM exposes): yesterday's new leads by source; MTD leads / appointments set & shown / sold / close %; unworked or aging leads. Build kpis (4-6 cards `{"label","value","status"}`), sources (top 5-8 rows, 4-5 short columns), insights (1-3 boxes a CMO acts on).
>
> **Return ONLY:** `{"available": true, "period": "<label>", "kpis": [...], "sources": [...], "insights": [...]}`, or the login_required object, or `{"available": false, "note": "<what broke>"}`.

If a runbook still says NEEDS SCOUTING, do not dispatch that store's agent, set its dealer object to `{"available": false, "note": "Runbook not scouted yet — run /morning-coffee scout"}`.

#### I. Emailed-reports agent (Zapier Gmail attachments)

> Fetch CRM/vendor reports that arrived by EMAIL in the last 36 hours and parse them. Load via ToolSearch: `mcp__75e77cfe-30b9-4992-a1d8-99d021536d10__execute_zapier_read_action`.
>
> 1. Call it with `selected_api: "GoogleMailV2CLIAPI"`, `action: "gmail_find_email"` (this exact action name, the generic `message` key collides with Send Email), `params: {"query": "has:attachment newer_than:2d subject:(report OR leads OR snapshot OR export)"}`. Also run a second call with `params: {"query": "has:attachment newer_than:2d subject:(\"Momentum Executive\")"}`.
> 2. Each result carries `attachments[].url`: a direct S3 link. Download with `Bash: curl -sL -o <scratchpad>/<filename> "<url>"`.
> 3. Parse: PDFs via the Read tool, CSV via python3 csv, XLSX via openpyxl. Match each report to a store by filename/subject (Sterling BMW, New Century BMW, Nissan of Irvine, McPeek).
> 4. Skip files that are DigitalCLIQ's own outbound deliverables (sender Drew Moon + DigitalCLIQ-branded filenames like OnlineReputation_* or *_Lead_Scores_*), we want INBOUND vendor/CRM reports only.
>
> **Return ONLY:** `{"available": true, "reports": [{"store_key": "sterling|new_century|nissan|mcpeek", "report_name": "...", "period": "...", "kpis": [...], "sources": [...], "insights": [...]}]}`, or `{"available": false, "note": "no inbound report emails in window"}`.

#### J. Meta Ads agent (API)

> Pull Meta Ads performance for two ad accounts via the Meta Ads MCP. Yesterday = `<YYYY-MM-DD>`, MTD = `<YYYY-MM-01>` to yesterday.
>
> Load via ToolSearch: `mcp__ead459fc-30f4-469e-a5db-c76ab2240de5__ads_get_ad_entities` (and if needed `ads_insights_performance_trend`).
>
> Accounts: `main` = 932166720307788 (DigitalCLIQ main, all client paid social); `mcpeek` = 1218321493439724 (McPeek Dodge).
>
> For each account pull campaign-level insights for yesterday and MTD: spend, impressions, clicks, CTR, leads/results, cost per result. Only ACTIVE campaigns plus any campaign with spend > 0 in the window. Attribute campaigns to clients by campaign name where obvious.
>
> Build per-account: kpis (Spend Yesterday, Spend MTD, Leads MTD, CPL MTD, best/worst campaign), campaigns table (Campaign / Spend / Results / CPR / Status, max 8 rows), insights (zero-result spend, CPL spikes, fatigued creative).
>
> **Return ONLY:** `{"available": true, "period": "<label>", "accounts": {"main": {"available": true, "period": "...", "kpis": [...], "campaigns": [...], "insights": [...]}, "mcpeek": {...}}, "insights": [<cross-account boxes>]}`

#### K. Dashboard cross-check agent

> Fetch the current JSON payload from three live DigitalCLIQ client dashboards (plain GETs, no login):
> - ncbmw (New Century BMW): `https://script.google.com/macros/s/AKfycbwdi91LD8vFv5A3PDCJQ4BIm4TWkzDWei49G_dCf0fnxfMucDHORapSKtLcnoQ9aMpyWA/exec`
> - sbmw (Sterling BMW): `https://script.google.com/macros/s/AKfycbxVJugSl93A9egpeeXymBMEzBv6M5yWMxs-Prn-VEP-MM0ragBhWDP0xdKXDlAl_ijgJQ/exec`
> - mcpeek (McPeek CDJR): `https://script.google.com/macros/s/AKfycbxswEKhEK-Sr98XkVe_mmFs8SqyQlsaGfzNXIAfuH2EatFJixHtUnX3nfhyqFoKPRjl/exec`
>
> Use `Bash: curl -sL "<url>"` (Apps Script redirects: the -L matters). Parse each payload, surface the store's headline numbers as 4-6 kpi cards, note the latest data date. If the latest data is >3 days old set `stale: true` with a `stale_note` naming the stale vendor/tab.
>
> **Return ONLY:** `{"available": true, "stores": {"ncbmw": {"available": true, "updated": "<date>", "stale": false, "kpis": [...], "insights": [...]}, "sbmw": {...}, "mcpeek": {...}}}`

#### L. News agent

> Two WebSearch calls in parallel: (1) `US economy news today <month year> CPI inflation Fed rates jobs`; (2) `Automotive News top stories today <month year> dealership BMW Nissan Stellantis`. 4-6 economy + 5-8 automotive headlines; per headline: headline, source, url, `client_relevance` (BMW → Sterling/New Century; Nissan → Nissan of Irvine; CDJR → McPeek).
>
> **Return ONLY:** `{"economy": [...], "automotive": [...]}`

#### M. Semrush SEO agent

Same as before: daily overview KPIs + `domain_organic` rise/fall/new/lost movers + site-audit health for sterlingbmw.com (project 24960897), newcenturybmw.com (29670819), mcpeeks.com (29478388); weekly deep-dive (quick wins, competitors, branded split, backlinks) only when today is Monday. Load `mcp__781ea802-0e57-4cef-a086-f038da48202d__execute_report` via ToolSearch; database `us`; keep call volume tight (1 overview + 4 movers per dealer daily).

**Return ONLY:** `{"available": true, "weekly_deep_dive": false, "dealers": {"sterling": {"available", "kpis", "movers", "weekly?", "insights"}, "new_century": {...}, "mcpeek": {...}}}`

### Step 2: Merge into `/tmp/coffee_report_data.json`

Top-level keys: `metadata`, `calendar` (A), `tasks` (B), `gmail` (C), `ga4` (D), `crm` (E-H + I), `paid` (J), `dashboards` (K), `news` (L), `seo` (M).

Building `crm`: dealers = the four CRM agents' objects keyed `sterling` / `new_century` / `nissan` / `mcpeek`. If agent I parsed an inbound emailed report for a store whose live pull failed, use the emailed report's data for that dealer (note the source in `period`, e.g. "Jul 1-9 · via emailed snapshot"). If both exist, prefer the LIVE pull and fold anything extra from the email into that dealer's insights. Then write `cmo_lens`: 2-4 cross-store boxes (same vendor performing differently across stores, funnel choke points, gross erosion), the main loop writes these from the merged dealer data.

Legacy fallback: if `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/01_Inbox/` contains lead reports Drew dropped manually, parse them for any store still missing data (same schema as before).

Any failed agent → `{"available": false, "note": "..."}` or `connected: false`. **Never fail the whole report.** Every `login_required` source must produce one line in the executive summary: "<CRM> session expired, log in and say 're-run <store> CRM' to backfill."

```json
{
  "metadata": {"report_date": "YYYY-MM-DD", "day_name": "...", "generation_timestamp": "ISO", "holiday_note": "", "chrome_connected": true},
  "calendar": {}, "tasks": {}, "gmail": {},
  "crm": {"available": true, "period": "...", "cmo_lens": [], "dealers": {"sterling": {}, "new_century": {}, "nissan": {}, "mcpeek": {}}},
  "paid": {"available": true, "period": "...", "accounts": {"main": {}, "mcpeek": {}}, "insights": []},
  "ga4": {"sterling": {}, "nissan": {}, "mcpeek": {}, "new_century": {}},
  "dashboards": {"available": true, "stores": {"ncbmw": {}, "sbmw": {}, "mcpeek": {}}},
  "news": {}, "seo": {}
}
```

### Step 3: Render PDF

```
python3 "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/morning-coffee/generate_coffee_report.py" \
    /tmp/coffee_report_data.json \
    "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/Coffee_Report_YYYY-MM-DD.pdf" \
    "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png"
```

Section order (hard-coded in generator): Title → Calendar → Notion Tasks → Gmail Pulse → Lead Pulse (CRM) → Paid Social Pulse (Meta) → GA4 → Dashboard Cross-Check → SEO Pulse → News.

Then run the Visual-QA render gate (design-system block, point 7) on the PDF before delivering: render every page via `Resources/design-system/templates/render_check.py`, READ the pages, fix and re-render until two consecutive clean passes.

### Step 4: Deliver

Hand back the file path plus a tight executive summary: top 3-5 things Drew needs to know today, PLUS an explicit "needs your login" list if any CRM session was expired, PLUS the Zapier reconnect link if GA4-via-API failed. Keep it tight.

---

## Speed rules (DO NOT VIOLATE)

- All agents launch in a SINGLE message. Sequential launches defeat the point.
- Main loop calls no data tools itself, only subagents do.
- Every browser agent claims its OWN tab via `tabs_create_mcp` and passes that tabId on every call.
- Do not poll; subagents return when done.

## Handling Missing Data

- Bad/no data → `available: false` + note, continue. Generator never crashes on absent sections.
- **ALWAYS deliver the report with whatever data IS available.**
- Login walls are normal, not errors: flag, ship, offer a one-section re-run.

---

## Scout Mode (one-time per CRM, Drew at the machine)

Purpose: turn each `references/crm-runbooks/*.md` from NEEDS SCOUTING into a deterministic click-path. Run when invoked as `/morning-coffee scout` (optionally with a store name to scout just one).

For each un-scouted CRM, IN SEQUENCE (not parallel. Drew is watching one screen):
1. Open the CRM's entry URL in a new tab (claude-in-chrome). If a login wall appears, tell Drew in chat to log in manually, then continue after he confirms. Never touch the login form.
2. Explore READ-ONLY to find the lead-source / e-commerce report with yesterday + MTD views. Prefer report URLs that encode the date range (deterministic re-navigation later). Do not modify records or settings; do not trigger emails/exports that notify others.
3. Extract a sample pull and show Drew the numbers in chat for a sanity check ("Momentum says 14 leads yesterday, top source Autotrader, match what you expect?").
4. Update that store's runbook file: exact click-path, report URLs, wait times, extraction method (`get_page_text` vs `read_page`), quirks, and flip status to SCOUTED with today's date.
5. After all stores: report which runbooks are locked and that daily runs are now fully automatic.

## Self-Validation (MANDATORY: final step before reporting success)

```bash
python3 /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/post_flight.py \
  "<final output path>" --min-pages 4
```

Verifies: logo embedded on every page, file inside `outputs/`, ≥4 pages, no placeholder tokens. On failure: diagnose, regenerate ONCE, re-validate; if it still fails, STOP and show the validator output verbatim, never report success on a failed validation, never wrap in `|| true`.


## Final QA Gate: deliverable-reviewer agent (MANDATORY, added 2026-08-13)

Runs AFTER the deliverable is generated and post_flight.py passes, BEFORE filing/presenting. post_flight.py is mechanical; this gate is the human-style read.

1. **Write a facts manifest** next to the deliverable in `outputs/`: a JSON list of every number, name, date, and claim that appears in the deliverable, each as `{"value": ..., "label": "where it appears", "source": "tool/file/URL it came from"}`. Build it from data already in context, never re-fetch anything just for the manifest.
2. **Spawn the `deliverable-reviewer` agent** (fresh eyes, it did not write the report). Pass in the prompt: the absolute path(s) of the finished deliverable file(s), the manifest path, and any skill-specific checks from this SKILL.md. It renders every page, reads them all, cross-checks figures against the manifest, and reviews tone/copy.
3. **Auto-fix every finding** in the source generator or data (never by hand-editing the output), re-render, and re-run the agent once. Max 2 review passes. If CRITICAL or MAJOR findings remain after pass 2, the ship is BLOCKED: report the remaining findings to Drew verbatim instead of presenting the file as done.
4. The run summary MUST include a **QA line**: what the reviewer caught and what was fixed, or "QA: clean on first pass (N pages read, M figures verified)". Never silently skip the gate; if the agent could not run, say so explicitly in the delivery message.
