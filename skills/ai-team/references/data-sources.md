# Data sources (the only places the team pulls from)

All commands run from the vault root. `GD` = `python3 .claude/skills/ai-team/scripts/gdata.py`. Shift folder = `outputs/ai-team/{YYYY-MM-DD}/` (the date the shift runs).

No browser. No CAPTCHA solving. No logins. If a source is missing, say "no data since {date}" and move on. Never estimate a missing number.

## GA4 (Kobe)

`GD ga4-nightly --out outputs/ai-team/{date}/data` writes one `ga4_{STORE}.json` per store and prints a summary with flagged channels. Default target date is yesterday Pacific. On a Monday shift also run it with `--date` for Friday and Saturday.

Each file holds: `channel_flags` (target day vs trailing 4-week same-weekday average, flag at 25% with a 20-session floor), `channel_daily_last7`, `source_medium_last7` and `_prior7`, `key_events_by_channel_last7` and `_prior7`, `landing_pages_last7`, `paid_campaigns_last7`, `ai_engine_referrals_last28`, and `errors`.

Ad hoc: `GD ga4 --store NOI --start 2026-09-10 --end 2026-09-16 --dims sessionCampaignName --metrics sessions,keyEvents`.

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

Shaq diagnoses and recommends. Nothing in any Ads account changes without Drew's explicit "go" in Slack, and never on the same night.

## CRM (Nick)

**Primary path: scheduled report emails.** Each CRM emails its report to Drew, a Gmail filter files it under the `Morning_CRM` label, and Nick reads the label. Drew never fetches anything. `GD mail-ls --days 3` lists what landed (sender, subject, date, attachment names, a text preview); `GD mail-get --id {msg id} --out ~/.cache/digitalcliq-ai-team/crm/{STORE}/` saves the attachments and body text. On a Monday shift use `--days 4`.

| Store | CRM | Sender to look for | Status 2026-09-17 |
|---|---|---|---|
| SBMW | MomentumCRM | `DoNotReply@drive.sterlingbmw.com`, subject "Morning CRM Executive Summary Sterling BMW", PDF `executiveSnapshot_*.pdf`. Rescheduled 2026-09-17 to land between midnight and 1:00am. | Live |
| NOI | VinSolutions | `reportscheduler@motosnap.com`, subject "Morning CRM NOI Lead Reports ROI", leads month to date. Scheduled 2026-09-17, test received 3:38pm that day. | Live |
| NCBMW | Reynolds FOCUS | No FOCUS email (CAPTCHA on pull, Drew has no scheduling rights). Use BMW NA's `Edward.McRae@bmwna.com` emails instead: "Lead Conversion - {Mon} MTD", "{Mon} MTD RDRs" daily, and Constellation `reports@helloconstellation.com` weekly. These are NOT under the label; run `mail-ls --query "from:bmwna.com OR from:helloconstellation.com"` too. Drew may drop a FOCUS export in `CRM Drop/NCBMW` about weekly; when one appears, backfill the days it covers. | Partial, weekly CRM depth at best |
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

Benchmarks: NADA close-rate logic from the `score-leads` and `compare-weeks` skills.

## Meta Ads (Luka)

One ad account, the DigitalCLIQ Meta account (id in [[Context/connector-ids]], never written to Slack or the brief). Every client's paid social runs through it, so Luka splits it by store from campaign names. Access is the Meta Ads MCP, two ways: the user-scope server `meta-ads` (registered 2026-09-19, tool names `mcp__meta-ads__*`, so teammates load it from settings) or the claude.ai connector in the lead session. Confirmed 2026-09-19 from the desktop session: the connector lists `(MAIN)932166720307788`, business Digitalcliq, active and queryable. Luka reads that account only. The connector also shows an active `mcpeek ads` account owned by the McPeek Dodge business and a closed Nissan Irvine account; neither is in scope unless Drew says so. Tools are deferred until searched: run a ToolSearch for `select:mcp__meta-ads__ads_get_ad_accounts` before saying the connector is missing.

Read-only tools, the only ones Luka calls: `ads_get_ad_accounts`, `ads_get_ad_entities`, `ads_insights_performance_trend`, `ads_insights_anomaly_signal`, `ads_insights_advertiser_context`, `ads_insights_industry_benchmark`, `ads_insights_auction_ranking_benchmarks`, `ads_get_creatives`, `ads_get_creative_ads`, `ads_get_ad_preview`, `ads_get_customconversions`, `ads_get_datasets`, `ads_get_dataset_quality`, `ads_get_dataset_stats`, `ads_get_errors`, `ads_get_opportunity_score`, `ads_account_get_activity_logs`, `ads_get_field_context`, `ads_get_help_article`. Every create, update, delete, activate, boost, and upload tool on that connector is denied in `.claude/settings.json`; a refusal is the guardrail, not a bug.

Connector caveat (learned 2026-09-19 dry run): claude.ai connectors load in Magic's session and did not load in the teammate sessions (Worthy had no Semrush). If the Meta tools are not in your session, do not stop: tell Magic in Slack, and Magic runs the standard pull from its own session into `outputs/ai-team/{date}/data/meta_*.json` for you to read. Same rule for Worthy and Semrush.

Call budget: 25 connector calls per shift. Pull campaign-level insights for all stores in one call where the tool allows, then drill only into what moved. Save every raw response to `outputs/ai-team/{date}/data/meta_*.json` so nobody re-pulls.

Context worth knowing: [[Nissan of Irvine|NOI]] weekend blast plus $800/mo Facebook and Instagram boosts went live 2026-09-19. SBMW Paid Social was flagged 2026-09-18 by the daily GA4 report as high sessions, near-zero key events; Kobe and Luka should settle whether that is traffic quality or tracking.

## SEO / GEO / AEO (Worthy)

Semrush MCP (`domain_overview`, `organic_research`, `keyword_research`, `position_tracking`, `get_report_schema`, `execute_report`), reachable two ways: the user-scope server `semrush` (registered 2026-09-19 so teammates load it from settings; tool names `mcp__semrush__*`) or the claude.ai connector in the lead session.

**Semrush ladder (Drew's rule, 2026-09-19). Work it top down, stop at the first rung that answers, and write which rung fed each number:**
1. Tools are deferred until searched. Run a ToolSearch for `select:mcp__semrush__domain_overview` (and the claude.ai-prefixed name) before saying the connector is missing.
2. Still nothing: post it in Slack and ask Magic. Magic runs the standard pulls from the lead session into `outputs/ai-team/{date}/data/semrush_*.json`.
3. Magic has no connector either: Magic, and only Magic, opens semrush.com in Drew's already-signed-in Chrome (the lead session starts with `--chrome`), reads Domain Overview and the store's Position Tracking project, saves the figures with the page name and date to `data/semrush_manual_{STORE}.md`, and touches nothing else. Read only. If Chrome is not connected, Semrush is signed out, or a login or CAPTCHA appears, stop: nobody types a credential.
4. Nothing worked: "no Semrush since {date}" in the data gaps, organic health is GA4-only that night. Credits are limited: at most 6 `execute_report` calls per store per shift, and none that repeat a pull already saved in a prior shift folder. Google Trends and OEM press rooms via web fetch (`defuddle parse <url> --md`). Search Console is not available yet.

Radar backlog: `Intelligence/market/future-rank-radar.md`.

## Rulebook (Magic)

Order of authority: federal, then California, then OEM, stricter wins.
1. `Resources/automotive-guidelines/federal-ad-rules-index.md`
2. `Resources/automotive-guidelines/ca-cars-act-sb766-index.md` (CARS Act effective 2026-10-01)
3. OEM quick references in `Resources/automotive-guidelines/`: `bmw-quick-reference.md` for SBMW and NCBMW, `nissan-quick-reference.md` for NOI, `cdjr-quick-reference.md` for MCP. The Stellantis Marketing Covenant is NOT filed in the vault yet (checked 2026-09-17); until Drew drops it, MCP reviews cite the CDJR quick reference and say the covenant was not checked. ATLAS gets general FTC truth-in-advertising review (`ftc-advertising-compliance.md`).

## Slack

`python3 .claude/skills/ai-team/scripts/slack.py post --as {magic|kobe|shaq|luka|worthy|nick} --text "..." [--thread TS] [--tag-drew]`
`python3 .claude/skills/ai-team/scripts/slack.py read --hours 24` (Drew's replies, "go" approvals, factory doc drops)
