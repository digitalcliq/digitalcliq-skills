# Data sources (the only places the team pulls from)

All commands run from the vault root. `GD` = `python3 .claude/skills/ai-team/scripts/gdata.py`. Shift folder = `outputs/ai-team/{YYYY-MM-DD}/` (the date the shift runs).

No browser. No CAPTCHA solving. No logins. If a source is missing, say "no data since {date}" and move on. Never estimate a missing number.

## GA4 (Kobe)

`GD ga4-nightly --out outputs/ai-team/{date}/data` writes one `ga4_{STORE}.json` per store and prints a summary with flagged channels. Default target date is yesterday Pacific. On a Monday shift also run it with `--date` for Friday and Saturday.

Each file holds: `channel_flags` (the last complete day, `flag_date`, which is the day before `target_date`, vs its trailing 4-week same-weekday average, flag at 25% with a 20-session floor), `channel_daily_last7`, `source_medium_last7` and `_prior7`, `key_events_by_channel_last7` and `_prior7`, `landing_pages_last7`, `paid_campaigns_last7`, `ai_engine_referrals_last28`, and `errors`.

It also writes `ga4_organic_{STORE}.json` (added 2026-09-23) for Worthy's GA4 match: `organic_landing_last28` and `_prior28` (landing page x campaign, Organic Search minus AI engines), `organic_landing_events_last28`, `ai_referrals_by_landing_last28`, and `organic_windows`. Kobe does not need to read it; it is large.

**Why the flags skip the target day (changed 2026-09-26).** The 1 AM pull reads the target day while GA4 is still processing it, so that day always reads low and every channel looked "down": a read-only re-pull of 2026-09-24 showed SBMW 808 sessions at 1 AM against 1,328 final and NCBMW 286 against 557, while the day before matched the final count exactly at all five stores. So `channel_flags` always compare `flag_date` (on a Monday the Friday, Saturday and default pulls flag Thursday, Friday and Saturday, and Tuesday's shift flags Sunday, so every day is flagged once). `target_preliminary` is true when the target is yesterday (every default run) and false on an older `--date` pull, which is already final; when it is true, the target day's own counts (in `channel_daily_last7` and the 7-day sections) are reported as "preliminary, GA4 finalizes in 24 to 48 hours". `target_date` itself is unchanged (health.py, value_line.py and seo_join.py read it). The tradeoff: a real channel drop is flagged one night later, but the flags are real.

Ad hoc: `GD ga4 --store NOI --start 2026-09-10 --end 2026-09-16 --dims sessionCampaignName --metrics sessions,keyEvents`.

Search Console (optional, not authorized yet): `GD gsc-sites` and `GD gsc-nightly --out outputs/ai-team/{date}/data` write `gsc_{STORE}.json` once Drew enables the Search Console API in the Cloud project, runs `GD auth --gsc` himself, and fills `GSC_SITES` in gdata.py. Until then both commands stop with "Search Console not authorized yet"; nothing else depends on them.

| Store | Property id |
|---|---|
| SBMW | 297584513 |
| NCBMW | 487046736 |
| NOI | 277100567 |
| MCP | 321466006 |
| ATLAS | 408152419 |

Before reporting conversions, apply [[Intelligence/processes/ga4-conversion-integrity]].

## Google Ads (Shaq)

Each account runs `scripts/ads_export.gs` nightly into its own Google Sheet, filed in `DigitalCLIQ Shared Drive / Internal / Ads Exports` (folder `1XiijjRoYMDlX_XiNBLTo8CcxCcr44GHb`). Read with `GD sheet-tabs --id {id}` then `GD sheet --id {id} --range 'campaign_daily_30d!A1:N2000'`. Always read the `meta` tab first: if `last_run` is older than 26 hours, the export is stale, say so.

| Store | Ads CID | Export Sheet id |
|---|---|---|
| MCP | 346-925-5700 | `1BOTg4rKHz3P99EOGbNBK_ZCoN1YPJHeX6kP58XIqh0c` (script id 12338479, installed 2026-09-18, runs daily 12:00 to 1:00 AM account time) |
| NOI | 724-338-3586 | `1C9bf6Ede7xbeDzK2gLlQ4L0MoVeQfRoogrFRNx1FN-U` (script id 12355410, installed 2026-09-19, runs daily 12:00 to 1:00 AM account time) |
| ATLAS | 462-332-6582 | `19l16Y6Sn3817ScpxhsEHRKdW4r-iy0vXNmj_JEnvaPE` (script id 12343060, installed 2026-09-19, runs daily 12:00 to 1:00 AM account time) |

Tabs: `meta`, `campaign_daily_30d`, `adgroup_7d`, `search_terms_7d`, `keywords_7d`, `conversions_by_action_7d`, `change_events_14d`, `ads_policy_issues`. Cost columns are already in dollars.

All three accounts (MCP, NOI, ATLAS) run `ads_export_v2.gs` since 2026-09-23 (same tabs plus `ad_text_7d`; installed through Drew's Chrome on his go, no re-authorization needed) also write every enabled search ad in an enabled campaign and ad group with headlines, descriptions, pinned slots, final URL, approval, and 7-day delivery. `python3 .claude/skills/ai-team/scripts/ad_text_check.py --store ALL --out outputs/ai-team/{date}/data` scans it in one call; ATLAS gets federal citations only; responsive search ads only (Performance Max, vehicle listing ads, and promotion or callout assets are not covered yet).

Shaq diagnoses and recommends. Nothing in any Ads account changes without Drew's explicit "go" in Slack, and never on the same night.

## CRM (Nick)

**Primary path: scheduled report emails.** Each CRM emails its report to Drew, a Gmail filter files it under the `Morning_CRM` label, and Nick reads the label. Drew never fetches anything. `GD mail-ls --days 3` lists what landed (sender, subject, date, attachment names, a text preview); `GD mail-get --id {msg id} --out ~/.cache/digitalcliq-ai-team/crm/{STORE}/` saves the attachments and body text. On a Monday shift use `--days 4`.

| Store | CRM | Sender to look for | Status 2026-09-17 |
|---|---|---|---|
| SBMW | MomentumCRM | `DoNotReply@drive.sterlingbmw.com`, subject "Morning CRM Executive Summary Sterling BMW", PDF `executiveSnapshot_*.pdf`. Rescheduled 2026-09-17 to land between midnight and 1:00am. | Live |
| NOI | VinSolutions | `reportscheduler@motosnap.com`, subject "Morning CRM NOI Lead Reports ROI", leads month to date. Scheduled 2026-09-17, test received 3:38pm that day. | Live |
| NCBMW | Reynolds FOCUS | No FOCUS email (CAPTCHA on pull, Drew has no scheduling rights). Use BMW NA's `Edward.McRae@bmwna.com` emails instead: "Lead Conversion - {Mon} MTD", "{Mon} MTD RDRs" daily, and Constellation `reports@helloconstellation.com` weekly. These are NOT under the label; run `GD mail-ls --days 3 --any-label --query "from:bmwna.com OR from:helloconstellation.com"` too. Without `--any-label` the query only searches inside the label and always comes back empty: that bug made NCBMW read as "no CRM data since 2026-09-17" for four shifts while BMW NA's Lead Conversion (9/22) and daily RDR mails (through 9/23) and Constellation's weekly report (9/22) were all arriving. Drew may drop a FOCUS export in `CRM Drop/NCBMW` about weekly; when one appears, backfill the days it covers. | Partial, weekly CRM depth at best |
| MCP | Tekion | No Tekion email (Drew cannot schedule in Tekion; the store's Tekion admin has to). Drew may drop a Tekion export in `CRM Drop/MCP` about weekly (he is at the store Thursdays); when one appears, backfill the days it covers. | Weekly manual drop until the store schedules it |

The month-to-date reports (SBMW, NOI) restate the whole month each night. Nick derives the day's numbers by comparing to the previous night's file in the prior shift folder; on the first night there is no daily delta, only MTD.

The label filter also catches unrelated mail (a "RYAN ASK" thread on 2026-09-15). Ignore anything that is not a CRM or OEM report and tell Magic so the filter gets tightened.

**Fallback path: manual drop.** `DigitalCLIQ Shared Drive / Internal / CRM Drop / {STORE}` (created 2026-09-17), for a day when an email did not arrive and Drew drops a file by hand. Check it after the label. List with `GD drive-ls --folder {id}`, download with `GD drive-get --id {file id} --out ~/.cache/digitalcliq-ai-team/crm/{STORE}/{filename}`.

| Folder | Drive id |
|---|---|
| CRM Drop | `1VOlJKEJuNprCcSFsqW-u_gpmvTptk_Gy` |
| NOI | `12gS0vexYXl7BzcnRUTUkInUOIQ1Z18l_` |
| SBMW | `1VDcMvuLU32Qnc7gC-pPu59nnKriF0pjI` |
| NCBMW | `1KrkSlj7hWlrdlJm-fWQOvQLfPkkrsocL` |
| MCP | `1_sGEL5d4cskyrXzdL5C0Jmag0neYN4iZ` |

**PII law.** CRM exports hold customer names, phones, and emails. Downloads go to `~/.cache/digitalcliq-ai-team/crm/` only, never into the vault, and Magic purges that folder at the end of the shift. Findings files, Slack, and the brief carry aggregates only: counts, rates, sources, models. Never a customer name, phone, email, or a row copied from an export.

Spend (for cost per lead and cost per sale), Google Sheets:

| Store | Budget sheet id |
|---|---|
| SBMW | 1S3JeQUkHrXsVLJEvWojYtT8e5-cNRJWbBPgqHqRDjho |
| NCBMW | 1SPV5x_LjuwHQqERWYlwC08I2Pn0hRM5plzlQNRsHO1c |
| MCP | 1Qd4CwwHsiE-hAEYuW-1IR0KHgJ-xFUQEuBMctj3Q3xk |
| NOI | none found yet, say so |

Benchmarks: close-rate benchmarks come from the `score-leads` skill's `reference/nada_benchmarks.json`, `close_rate_benchmarks.categories` (per source type and brand tier, for example website leads, luxury 0.12). Cite that file and the category's own `source`, and say "estimate" where its `support` flag says so. (Corrected 2026-09-26: the earlier line also credited a second skill that holds no benchmark logic.)

## Meta Ads (Luka)

One ad account, the DigitalCLIQ Meta account (id in [[Context/connector-ids]], never written to Slack or the brief). Every client's paid social runs through it, so Luka splits it by store from campaign names. Access is the user-scope Meta Ads MCP server `meta-ads` (registered 2026-09-19, authenticated, tool names `mcp__meta-ads__*`). The claude.ai Meta connector (`mcp__claude_ai_Meta_Ads__*`) has not appeared in the Terminal CLI since the morning of 2026-09-19; do not count on it. Confirmed 2026-09-19 from the desktop session: the connector lists `(MAIN)932166720307788`, business Digitalcliq, active and queryable. Luka reads that account only. The connector also shows an active `mcpeek ads` account owned by the McPeek Dodge business and a closed Nissan Irvine account; neither is in scope unless Drew says so. Tools are deferred until searched: run a ToolSearch for `select:mcp__meta-ads__ads_get_ad_accounts` before saying the connector is missing.

Read-only tools, the only ones Luka calls: `ads_get_ad_accounts`, `ads_get_ad_entities`, `ads_insights_performance_trend`, `ads_insights_anomaly_signal`, `ads_insights_advertiser_context`, `ads_insights_industry_benchmark`, `ads_insights_auction_ranking_benchmarks`, `ads_get_creatives`, `ads_get_creative_ads`, `ads_get_ad_preview`, `ads_get_customconversions`, `ads_get_datasets`, `ads_get_dataset_quality`, `ads_get_dataset_stats`, `ads_get_errors`, `ads_get_opportunity_score`, `ads_account_get_activity_logs`, `ads_get_field_context`, `ads_get_help_article`. Every create, update, delete, activate, boost, and upload tool on that connector is denied in `.claude/settings.json`; a refusal is the guardrail, not a bug.

Connector caveat (root cause found 2026-09-23): players get the tool list from the start of Magic's current turn, and connectors load a few seconds after turn 1 begins, so every shift that spawned the team in turn 1 left all players with zero connector tools, whatever was signed in. SKILL.md now spawns the team on a later turn, and Magic runs `usage.py --tools` right after the spawn. If Luka still has no Meta tools, Magic pulls the standard set from the lead session into `outputs/ai-team/{date}/data/meta_*.json` (campaigns with status, budget, and ad set flight end dates; campaign insights for yesterday, last 7, and prior 7 days; delivery errors; activity log 14 days). Same rule for Worthy and Semrush.

Call budget: 25 connector calls per shift. Pull campaign-level insights for all stores in one call where the tool allows, then drill only into what moved. Save every raw response to `outputs/ai-team/{date}/data/meta_*.json` so nobody re-pulls.

Context worth knowing: [[Nissan of Irvine|NOI]] weekend blast plus $800/mo Facebook and Instagram boosts went live 2026-09-19. SBMW Paid Social was flagged 2026-09-18 by the daily GA4 report as high sessions, near-zero key events; Kobe and Luka should settle whether that is traffic quality or tracking.

## SEO / GEO / AEO (Worthy)

**Access (fixed 2026-09-23).** Semrush comes through the claude.ai connector, which the Terminal CLI names `mcp__claude_ai_Semrush__*` (`execute_report`, `get_report_schema`, `position_tracking`, `site_audit`, `projects`, `organic_research`, `keyword_research`). Tools are deferred: run ToolSearch `select:mcp__claude_ai_Semrush__execute_report,mcp__claude_ai_Semrush__get_report_schema` first. The user-scope server `semrush` (`mcp__semrush__*`) was never authenticated and only offers `authenticate`; ignore it. Every "no Semrush" night through 2026-09-23 had one cause: the players were spawned in Magic's first turn, before connectors load. SKILL.md now spawns them on a later turn.

**Semrush ladder (Drew's rule, 2026-09-19, updated 2026-09-23). Stop at the first rung that answers and write which rung fed each number:**
1. Worthy's own `mcp__claude_ai_Semrush__*` tools.
2. `usage.py --tools` shows Worthy without Semrush: Magic pulls the nightly set below from the lead session into `outputs/ai-team/{date}/data/` and tells Worthy.
3. Magic has no connector either: Magic, and only Magic, may read semrush.com in Drew's signed-in Chrome, read only, never a credential. Caution found 2026-09-23: Semrush's Terms of Service (updated 2026-08-25) section 3.3(p) bars scraping and 3.3(r) bars feeding Semrush content into an AI outside Semrush's official integrations, so this rung carries account risk; it has never been used, and Drew has been asked whether to retire it.
4. Nothing worked: "no Semrush since {date}" under Data gaps; organic health is GA4-only that night.

**Unit budget.** The plan (Pro level; history reports return 403) carries about 50,000 API units a month, shared with every daytime Semrush use, and it ran dry on 2026-08-13, 09-07 and 09-14 when the shift pulled about 1,600 to 3,000 units a night. Caps: weeknights 500, plus 400 on a night Worthy drafts a picked topic (one question or related-keyword pull); Monday 4,000; rank history once a month (300). Never re-pull what a shift folder from the last 7 days already holds (`seo_join.py` finds it on its own). `tracking_position_organic` costs 100 units per ROW: on demand only, always `display_limit` 10 or less. Semrush data may not be cached longer than a month (ToS 3.3), so never carry a Semrush file forward past 30 days.

**Recipes (verified 2026-09-23; units measured unless marked).** All through `execute_report` with `report` and `params`; check `get_report_schema` before changing a param.

| When | Report | Params | Units |
|---|---|---|---|
| Nightly | `tracking_overview_organic` | `{"campaign_id":"<id>","url":"*.<domain>/*"}` per campaign below | 100 each, 400 |
| Monday | `resource_organic`, brand terms excluded | `{"target":"<domain>","database":"us","display_limit":20,"display_sort":"traffic_desc","export_columns":["keyword","position","previous_position","volume","url","traffic","intent","position_type","timestamp"],"display_filter":[{"field":"keyword","operation":"contains","sign":"-","value":"<brand>"}]}` (one filter entry per brand term; entries combine as AND) | 10 per row, 200 per store |
| Monday | `resource_organic`, lost keywords | same plus `"display_positions":"lost","display_sort":"volume_desc","display_limit":10` | 100 per store |
| Monday | `resource_organic_unique` (top pages) | `{"target":"<domain>","database":"us","display_limit":15,"display_sort":"traffic_desc"}`, never `display_date` | 150 per store |
| Monday | `site_audit` info | `{"id":<project_id>}` | about 100 (not yet measured) |
| Monday, for topics | `phrase_questions` / `phrase_related` | `{"phrase":"<seed>","database":"us","display_limit":10,...}` one seed topic a week | 40 per row (published, not measured) |
| Monthly (first Monday) | `resource_rank_history` | `{"target":"<domain>","database":"us","display_limit":6,"display_sort":"date_desc"}`, default columns | 60 per store |
| On demand | `tracking_position_organic` | overview params plus `"display_limit":10` | 100 per row |

Brand terms to exclude (misspellings included): SBMW "sterling", "stearling"; NCBMW "century", "centry"; NOI "nissan of irvine", "nissanofirvine" (not "irvine" alone: "nissan dealer irvine" is a non-brand term worth keeping); MCP "mcpeek"; ATLAS "atlas".

**Position Tracking campaigns** (id format `{project_id}_{campaign_number}`; the API cannot list them, these came from Semrush's own emails):

| Store | Project | campaign_id | Location | Note |
|---|---|---|---|---|
| SBMW | 24960897 | `24960897_3046666` | Orange County, CA, desktop | Only 10 keywords, loaded 2025-06-06; 6 do not rank. Needs a refresh by Drew. |
| NCBMW | 29670819 | `29670819_5048343` | United States | |
| NOI | 29776292 | `29776292_4882073` | Irvine, CA | 4 Nissan competitors tracked |
| ATLAS | 25619865 | `25619865_3269620` | United States | |
| MCP | 29478388 | none | | No Position Tracking campaign; Drew's call |

**Files (so nobody re-pulls and `seo_join.py` can read them).** Write each response's `data` text exactly as returned (semicolon rows with the header line): `data/semrush_kw_{STORE}.csv` (the Monday non-brand `resource_organic`), `data/semrush_lost_{STORE}.csv`, `data/semrush_pages_{STORE}.csv`; JSON reports as `data/semrush_pt_{STORE}.json` (tracking overview), `data/semrush_audit_{STORE}.json`, `data/semrush_rank_history.json`, `data/semrush_ideas_{seed}.csv`.

**GA4 match.** `python3 .claude/skills/ai-team/scripts/seo_join.py --date {date}` joins `ga4_organic_{STORE}.json` with the newest `semrush_kw_{STORE}.csv` from the last 7 days (the older `semrush_organic_positions.md` is the fallback) and `gsc_{STORE}.json` when it exists, per normalized landing page. It writes `data/seo_join_{STORE}.json` and `data/seo_join.md`, and prints which inputs were missing. Flags: `EST_NO_TRAFFIC`, `GA4_WIN_NO_KW`, `MOVE_MATCH`, `AEO_PROOF`, `LEAD_LEAK` (meanings in `.claude/agents/worthy.md`).

**Web-UI-only Semrush features** (no API or connector report): Organic Traffic Insights (Semrush's own GA/GSC link), SEO Ideas, Topic Research, Keyword Strategy Builder. If Drew wants them in the team's work, he exports them to `01_Inbox/` and Worthy reads the file.

Google Trends and OEM press rooms via WebFetch (`defuddle` is not installed on this machine). Radar backlog: `Intelligence/market/future-rank-radar.md`.

## CARS web watch (Magic)

`python3 .claude/skills/ai-team/scripts/cars_watch.py --rotation` uses the cars-act-check skill's own crawler and machine rules (3 workers, 0.7 s pacing, circuit breaker) with caps of 400 URLs and 8 minutes, plus two watch rules (W01 rebates inside the advertised price, W02 price-gating buttons). Output goes to `outputs/ai-team/{date}/data/cars_{STORE}/` (`summary.md`, `run.json`); it never touches `Projects/{CODE}/cars-act-state/` or Drive, and the full `/cars-act-check` run (browser pass, retention zip, PDF) stays something Drew starts. Measured on NOI 2026-09-23: 399 URLs in 5.5 minutes, no blocks. SBMW (sterlingbmw.com) returns Cloudflare 403 to plain fetches, so the desktop scheduled task `cars-watch-sbmw-browser` (Drew approved 2026-09-23; Mondays about 12:20 AM, Claude Browser, up to 12 public pages) writes Monday's SBMW run before the shift; Magic's Monday rotation sees it and reports it instead of re-crawling. If the desktop app was closed at that hour, the task runs on next launch and Monday reports "blocked" plus the newest browser run from the last 7 days. NCBMW is scanned every Tuesday by plain fetch. CHC is covinahillschevrolet.com (from the CHC context log; the README has no domain).

## Client dashboards (Magic, added 2026-09-26)

The three client dashboards are Apps Script web apps: each `/exec` endpoint returns the JSON the store's GM sees. `python3 .claude/skills/ai-team/scripts/dash_check.py outputs/ai-team/{date}` reads all three with one plain HTTPS GET each (no login, no browser, it follows Apps Script's redirect) and writes `data/dashboards.json`: a status per store, every stale signal with its fix and how many days it has been open, a ready "Missing tonight" line, and the fields for one aging ask. It never opens or writes a Sheet. Exit 2 means a dashboard did not answer ("no dashboard data since {date}"). Endpoints come from the morning-coffee skill's `references/sources.md`; the script's `DASHBOARDS` table and this one change together.

| Store | Dashboard | Endpoint (plain GET) | Backing Sheet (Drew's fix) |
|---|---|---|---|
| SBMW | Sterling BMW | `https://script.google.com/macros/s/AKfycbxVJugSl93A9egpeeXymBMEzBv6M5yWMxs-Prn-VEP-MM0ragBhWDP0xdKXDlAl_ijgJQ/exec` | `1Ki2RjJUc4AN4A-ZFgqNLQpENDySVjgULR4xG6UTSpCU` |
| NCBMW | New Century BMW | `https://script.google.com/macros/s/AKfycbwdi91LD8vFv5A3PDCJQ4BIm4TWkzDWei49G_dCf0fnxfMucDHORapSKtLcnoQ9aMpyWA/exec` | `1JJcHIC1253Dtpp50OGIRhgNCw-g-DqRgkETIJa8okAE` |
| MCP | McPeek CDJR | `https://script.google.com/macros/s/AKfycbxswEKhEK-Sr98XkVe_mmFs8SqyQlsaGfzNXIAfuH2EatFJixHtUnX3nfhyqFoKPRjl/exec` | `12vhp5FyujzOpCVcIspPszmhbLxy3FwnsjJ4UxKbFXpA` |

Signals: RED when the CRM source says the CRM tab is empty or carries a `CHECK:` note, when leads month to date are 0 after the 3rd, or when a CRM headline card or a paid vendor block names a month before the last closed month. AMBER when an SEO card names a month before the last closed month, when the SEO months end before the last closed month or were never built, or when the dashboard's `updated` stamp is more than 3 days old. The gross "estimate" wording is by design and never flagged; the top-level `seoMonth` is blank on all three by design and never read.

This is a dashboard freshness check, not a measurement rule: it never feeds `health.py` or the Measurement health block, so a stale paste never blocks a store's valid GA4 and Ads numbers. Its lines go under Missing tonight.

## Rulebook (Magic)

Order of authority: federal, then California, then OEM, stricter wins.
1. `Resources/automotive-guidelines/federal-ad-rules-index.md`
2. `Resources/automotive-guidelines/ca-cars-act-sb766-index.md` (CARS Act effective 2026-10-01)
3. OEM quick references in `Resources/automotive-guidelines/`: `bmw-quick-reference.md` for SBMW and NCBMW, `nissan-quick-reference.md` for NOI, `cdjr-quick-reference.md` for MCP. The Stellantis Marketing Covenant is NOT filed in the vault yet (checked 2026-09-17); until Drew drops it, MCP reviews cite the CDJR quick reference and say the covenant was not checked. ATLAS gets general FTC truth-in-advertising review (`ftc-advertising-compliance.md`).

## Slack

`python3 .claude/skills/ai-team/scripts/slack.py post --as {magic|kobe|shaq|luka|worthy|nick} --file PATH [--thread TS] [--tag-drew]` (use `--file` for anything with a dollar amount: in `--text "..."` the shell eats `$6,497` into `,497`, and slack.py refuses the damaged text)
`python3 .claude/skills/ai-team/scripts/slack.py read --hours 24` (Drew's replies, "go" approvals, factory doc drops; top-level posts only, add `--thread TS` for replies)
`python3 .claude/skills/ai-team/scripts/slack.py picks --ledger outputs/ai-team/topics.json --apply` (tip-off: marks topics Drew tapped a checkmark on as picked)
`python3 .claude/skills/ai-team/scripts/slack.py post-topics --ledger outputs/ai-team/topics.json` (after the brief: each new open topic as its own top-level message Drew can tap or reply "pick" under)
