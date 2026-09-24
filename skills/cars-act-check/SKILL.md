---
name: cars-act-check
description: One-click California CARS Act (SB 766, Cal. Civ. Code § 1784.20 et seq., effective 2026-10-01) compliance suite for DigitalCLIQ dealership clients. Fans out parallel subagents for website monitoring, a 110-point ad compliance scan (statute plus CNCDA guidance), record retention backup to the client's Google Drive, and violation alerts, then a final reviewer agent verifies everything before delivery. Also generates per-client first-communication templates (CRM-aware), a customizable compliance policy, and a role-based training program. Use whenever Drew says /cars-act-check, "CARS Act", "SB 766", "cars act check for [client]", "is [client] CARS compliant", or a scheduled CARS check fires. Syntax: /cars-act-check -{client} [-policy | -training | -first-comm | -full].
---

# CARS Act Check

> Before anything else, read `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Context/vault-facts.md` and obey it (output paths, client codes, logo path). Deliverables stage in vault `outputs/`, then file to the client's folder under `Projects/{CODE}/deliverables/`.

**Design principle: scripts do the work, agents read only summaries.** The crawl, the hash cache, and all deterministic rule checks are pure Python. Agents handle only judgment calls (prominence, chat widgets, ad creative), archiving, and the final review. Never read raw crawled HTML into context. Read `findings.json` counts first, then only the entries needed to verify or summarize.

## Legal basis (verify once per quarter)

California CARS Act = SB 766, signed 2025-10-06, operative **2026-10-01**, codified at Cal. Civ. Code § 1784.20 et seq. Core sections: § 1784.40 prohibited misrepresentations (thirteen categories, (a) to (m)), § 1784.41 mandatory disclosures (total price in ads and in the first written communication, payment totals, lower-payment notice, add-on optionality), § 1784.42 add-on benefit rule and 10-day vendor payment, § 1784.43 three-day right to cancel (used vehicles $50,000 or less), § 1784.44 recordkeeping (2-year retention). Operational layer: the CNCDA CARS Act Compliance Guide v1.2 (2026-08-07) and Webinar FAQ (2026-08-31), digested in the vault at `Resources/automotive-guidelines/cncda-cars-act-guidance.md` (PDFs beside it) and folded into `references/cars-act-law.md`, `references/crm-first-comm.md`, `references/inspection-points.md` (points 101 to 110), and `config/rules.json`. Read `references/cars-act-law.md` before writing any finding, alert, policy, or training content; cite CNCDA as "CNCDA Guide Part N" or "CNCDA FAQ QN". **Mode switch:** if today < 2026-10-01, run in READINESS mode (findings are labeled "gap to close before Oct 1", not "violation"). On/after, ENFORCEMENT mode.

## Invocation and client resolution

`/cars-act-check -sterling bmw` → fuzzy-match the argument against the vault client roster in `CLAUDE.md` / `Context/vault-facts.md` (e.g. "sterling bmw" → SBMW). Resolve from `Projects/{CODE}/`:

- Primary website domain(s) and inventory sitemap URL
- CRM in use (needed for first-comm templates)
- Google Drive client folder ID (for retention backups; if missing, ask Drew once and save it to the client profile)
- Brand (BMW/Nissan/CDJR/etc.) for OEM-specific overlay checks

If the client can't be resolved to exactly one code, ask Drew before doing anything. Never guess a domain.

Flags: no flag = **audit mode** (default, the schedulable one). `-policy`, `-training`, `-first-comm` run only that generator. `-full` = audit + all three generators.

## Browser Surface Order (mandatory, retooled 2026-09-04)

<!-- browser-surface-block v1 · Claude Browser is the primary crawl surface; Chrome is a fallback only -->

Every live page visit in this skill runs on the **built-in Claude Browser** (the in-app Browser pane, tools `mcp__Claude_Browser__*`). Drew's real Chrome via the extension (`mcp__claude-in-chrome__*`) is a fallback, never the default. Do not open the extension, call `list_connected_browsers`, or ask which browser to use unless the Claude Browser has genuinely failed on a page as defined below.

| Tier | Surface | When |
|------|---------|------|
| 1 (default) | **Claude Browser** (`mcp__Claude_Browser__*`) | Every model-driven page visit (Agent B judgment pass, Agent R spot-verification). Open with `preview_start {url}` (or `tabs_create` + `navigate` for a fresh tab), extract with `javascript_tool` / `read_network_requests` / `get_page_text`, always with `tabId`. No user approval needed. |
| 2 (fallback) | **Server fetch** (`scripts/crawl.py`, python with a Chrome UA) | Already the default for Agent A's bulk crawl. Also the first fallback when the Claude Browser cannot render one of Agent B's pages: fetch the page to `$DATA` and judge from the saved extract where the point allows it. |
| 3 (last resort) | **Chrome extension** (`mcp__claude-in-chrome__*`) | Only when BOTH tier 1 and tier 2 failed on the same page (pane hung twice AND server fetch 403/blocked). Needs a one-time user approval; if the extension is not connected, write `{"point_id": ..., "severity": "manual", "summary": "surface_exhausted", "url": ...}` to `browser_findings.json` and move on, do not stall the run. |

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

## Paths and state

- `SKILL=<this skill dir>`; scripts in `$SKILL/scripts/`, rules in `$SKILL/config/rules.json`
- `DATA=<scratchpad>/cars-act-{CODE}/`: per-run working data (disposable)
- `VAULT=/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ`
- `STATE=$VAULT/Projects/{CODE}/cars-act-state/`: hash cache, prior findings, retention manifest. Persists; enables run-over-run diff and the token-slim incremental crawl.

## Audit mode: parallel fan-out

Spawn agents A through D **in parallel**. Each writes its output as JSON to `$DATA/` and nothing else to the main context. Then run the Final Reviewer (agent R) serially.

### Agent A: Crawl + deterministic scan (Bash only)

```bash
python3 "$SKILL/scripts/crawl.py" --domain {domain} --out "$DATA" --state "$STATE"   # 3 workers, 0.7s pacing, NEVER raise above 4
python3 "$SKILL/scripts/checks.py" --data "$DATA" --rules "$SKILL/config/rules.json" --state "$STATE"
```

Token-slim rules (this runs often, so this matters):
1. `crawl.py` is **incremental**: it hashes each page body and only re-downloads/re-checks pages whose content hash changed since `$STATE/hashcache.json`, plus new URLs and a rotating 10% re-verify sample. First run per client is full; steady-state runs typically touch < 15% of pages.
2. All machine-checkable inspection points (roughly 70 of the 110, tagged `machine` in `config/rules.json`) run in Python. Agent A reads only the printed counts and exits.
3. If crawl.py exits 3 (circuit breaker, site refusing connections): STOP all requests, probe once per minute, tell Drew immediately. Same politeness rule as mcpeeks-site-watch; a hot crawl once took a production site down.

### Agent B: Browser judgment pass (agent-only points, capped at ~8 pages)

Inspection points tagged `agent` in `references/inspection-points.md` need eyes: total-price prominence vs teaser prices, chat widget behavior on price questions, digital retailing tool payment displays, pre-consent trackers on comms surfaces. Use the Claude Browser (`mcp__Claude_Browser__*`, per the Browser Surface Order above; the Chrome extension is tier 3 only): `mcp__Claude_Browser__tabs_create` → `tabId`, then `navigate` / `javascript_tool` / `read_network_requests` with that `tabId` on every call; a fresh tab for the pre-consent tracker check so no consent state carries over. Page budget: homepage, 1 SRP, 2 VDPs (1 new, 1 used $50k or less), specials page, finance page, 1 digital-retailing flow, 1 Spanish-language page if the site has one. Write findings to `$DATA/browser_findings.json` as `{point_id, severity, url, summary, evidence}`.

### Agent C: Ad creative scan

Scan **off-site** advertising against the same rules: active Meta campaigns via the Meta Ads MCP (creative text + linked landing pages), Google Ads copy if exported in the client folder, and any third-party listings pages (Cars.com/Autotrader/CarGurus profile pages) named in the client profile. Every ad that references a specific vehicle or states a monetary amount or financing term must carry the total price disclosure (§ 1784.41(a)); a lease or payment ad that identifies a unit counts (CNCDA FAQ Q19), employee social posts count (FAQ Q20), and third-party listings fed from the dealer's inventory are the dealer's ads (FAQ Q15). Output `$DATA/ad_findings.json`. If no ad platform access, record `"skipped": true` with the reason; never silently skip.

### Agent D: Record retention archiver (§ 1784.44)

Build the audit-ready archive so the client can always prove what was advertised and communicated:
1. Snapshot every page the crawl flagged as advertising a specific vehicle or price (compact text extract + price block, not full HTML) into `$DATA/retention/{YYYY-MM-DD}/pages.jsonl`.
2. Snapshot current ad creatives from Agent C's pulls.
3. Include the client's current first-communication templates from `Projects/{CODE}/cars-act-templates/` if present.
4. Zip and upload to the client's Google Drive folder under `CARS-Act-Retention/{YYYY-MM-DD}.zip` via the Google Drive MCP. Update `$STATE/retention-manifest.json` (date, file ID, page count, checksum). Retention target: keep at least 24 months of snapshots; never delete old ones.

### Agent R: Final Reviewer (MANDATORY, runs after A through D)

Fresh-eyes agent, standard deliverable-reviewer pattern:
1. Merge all `*_findings.json`, dedupe, verify every finding cites a real inspection point ID and a real code section from `references/cars-act-law.md`. A finding with a made-up citation is itself a CRITICAL defect.
2. Spot-verify 5 findings against their evidence URLs (fetch just those pages: server fetch first, the Claude Browser with its own `tabId` if a page needs rendering; never the Chrome extension unless both failed).
3. Diff against `$STATE/prior_findings.json`: label NEW, RECURRING, RESOLVED.
4. Confirm Agent D's Drive upload really exists (list the Drive folder).
5. Review the report draft for tone, accuracy, em dashes (auto-fail), and design-system compliance.
Max 2 passes; if CRITICAL findings remain, ship is BLOCKED and Drew gets the findings verbatim.

## Violation alerts + report

`python3 "$SKILL/scripts/report.py" --data "$DATA" --state "$STATE" --out "$VAULT/outputs"` assembles `CARS_Act_Check_{CODE}_{date}.md`. Prepend a 5 to 8 sentence executive summary: worst exposure first, NEW vs last run, what resolved, one-line record-retention status. Every finding renders as: **what's wrong → citation → exactly how to fix it** (no guesswork, per the alert spec). Frame fixes as GM/leadership discussion topics, not directives. Render to branded PDF via the standing Chrome headless `--print-to-pdf` pipeline (a local render step, not web browsing; the Browser Surface Order does not apply to it) and the DigitalCLIQ report HTML shell, file to `Projects/{CODE}/deliverables/`, and upload a copy next to the retention archive in Drive.

Alert escalation: any CRITICAL finding (severity table in `references/inspection-points.md`) gets called out in the final message to Drew above the fold, with the URL and the fix. In ENFORCEMENT mode, CRITICAL findings should be treated as same-day items.

## Generator modes (read `references/cars-act-law.md` first, always)

- **`-first-comm`**: Read `references/crm-first-comm.md`, resolve the client's CRM, and generate ready-to-paste first-response templates (email + SMS, plus the consent-only SMS opt-in text and the AI-chat transfer notice) that satisfy § 1784.41(a)(3) on the first substantive reply: total price merge field in the message body, verbatim fee sentence, expiration date, no payment figure, and CRM-specific setup instructions (which template slot, which merge fields, how to force the auto-responder into either the price-merge or bare-receipt configuration CNCDA describes). Save to `Projects/{CODE}/cars-act-templates/` and deliver as a branded PDF.
- **`-policy`**: Fill `assets/policy-template.md` with the client's name, brand, CRM, and DMV license details from the client profile. Deliver as branded PDF with a cover note that it requires attorney review before adoption.
- **`-training`**: Fill `assets/training-outline.md` per role (Sales, F&I, BDC, Marketing) with client-specific examples pulled from that client's own recent findings when available (real findings train better than hypotheticals). Deliver as branded PDF; optionally a short quiz per role.

## DigitalCLIQ Design System (mandatory)

<!-- design-system-block v1 · do not edit per-skill · source: Resources/design-system/ -->

Every file this skill ships (PDF, DOCX, XLSX, PPTX, HTML) is built to `Resources/design-system/Design-System.md` and must pass the `Resources/design-system/Visual-QA.md` render gate before it is declared done. Read the Design-System and the Branding/render-gate sections of `Context/vault-facts.md` before generating anything. Palette, fonts (Dosis headings, Roboto Slab body), logo rules, canonical covers, visual-first pages, and the render gate all apply exactly as in the other DigitalCLIQ skills. Deliverables stage in `outputs/`, then file to `Projects/{CODE}/deliverables/`. Client deliverables are actual PDFs, never HTML.

## Token budget

Audit mode target < 60k output tokens per run. Agent A ≈ 0 (scripts). Agent B capped at ~8 pages. Agent C reads ad text only, never full landing pages (crawl already covered those). Agent D is bash + Drive calls. Agent R reads one merged findings file + 5 spot checks. Steady-state incremental runs should land well under budget; the first run per client will be the expensive one.

## Final message to Drew

Lead with finding counts by severity and the top 3 exposures (URL + citation + fix), then NEW vs RESOLVED, then retention backup confirmation (Drive file + page count), then the QA line from Agent R ("QA: clean on first pass" or what was caught and fixed), then anything needing his input. One screen, no padding, no em dashes.
