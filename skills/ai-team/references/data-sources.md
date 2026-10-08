# Data sources (the only places the team pulls from)

All commands run from the vault root. `GD` = `python3 .claude/skills/ai-team/scripts/gdata.py`. Shift folder = `outputs/ai-team/{YYYY-MM-DD}/` (the date the shift runs); it leaves the vault at the first shift on or after the 15th of the next month (Retention, in the CRM section).

No browser (two exceptions, both desktop tasks that run before the shift: `semrush-prepull`, see the Semrush ladder, and `vendor-dash-read`, see Vendor dashboards). No CAPTCHA solving. No logins. If a source is missing, say "no data since {date}" and move on. Never estimate a missing number.

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

Who changed what: `python3 .claude/skills/ai-team/scripts/changes.py --date {date}` turns each export's `change_events_14d` tab into `data/changes_{STORE}.md` and `data/changes.json` (every change since the last shift, grouped by who made it; times in the account time zone). The tab keeps the newest 200 changes, and the digest says TRUNCATED when a window reaches past them. Save any tab you read with `gdata.py sheet` that no script saves (search_terms_7d, keywords_7d, adgroup_7d, ads_policy_issues): `Write` the printed rows to `data/{STORE}_{tab}.txt` and cite that file, never the live Sheet.

Each account runs `scripts/ads_export.gs` nightly into its own Google Sheet, filed in `DigitalCLIQ Shared Drive / Internal / Ads Exports` (folder `1XiijjRoYMDlX_XiNBLTo8CcxCcr44GHb`). Read with `GD sheet-tabs --id {id}` then `GD sheet --id {id} --range 'campaign_daily_30d!A1:N2000'`. Always read the `meta` tab first: if `last_run` is older than 26 hours, the export is stale, say so.

| Store | Ads CID | Export Sheet id |
|---|---|---|
| MCP | 346-925-5700 | `1BOTg4rKHz3P99EOGbNBK_ZCoN1YPJHeX6kP58XIqh0c` (script id 12338479, installed 2026-09-18, runs daily 12:00 to 1:00 AM account time) |
| NOI | 724-338-3586 | `1C9bf6Ede7xbeDzK2gLlQ4L0MoVeQfRoogrFRNx1FN-U` (script id 12355410, installed 2026-09-19, runs daily 12:00 to 1:00 AM account time) |
| ATLAS | 462-332-6582 | `19l16Y6Sn3817ScpxhsEHRKdW4r-iy0vXNmj_JEnvaPE` (script id 12343060, installed 2026-09-19, runs daily 12:00 to 1:00 AM account time) |

Tabs: `meta`, `campaign_daily_30d`, `adgroup_7d`, `search_terms_7d`, `keywords_7d`, `conversions_by_action_7d`, `change_events_14d`, `ads_policy_issues`. Cost columns are already in dollars.

All three accounts (MCP, NOI, ATLAS) run `ads_export_v2.gs` since 2026-09-23 (same tabs plus `ad_text_7d`; installed through Drew's Chrome on his go, no re-authorization needed) also write every enabled search ad in an enabled campaign and ad group with headlines, descriptions, pinned slots, final URL, approval, and 7-day delivery. `python3 .claude/skills/ai-team/scripts/ad_text_check.py --store ALL --out outputs/ai-team/{date}/data` scans it in one call; ATLAS gets federal citations only; responsive search ads only (Performance Max, vehicle listing ads, and promotion or callout assets are not covered yet).

Shaq diagnoses and recommends. Nothing in any Ads account changes without Drew's explicit "go" in Slack, and never on the same night.

## Vendor dashboards (Shaq, added 2026-09-28)

Two vendors run [[New Century BMW]]'s paid search in their own Google Ads accounts, and neither gives us access (Drew, 2026-09-28: that is fine; watch what they share). [[NabThat]] runs the English campaigns and shares a Data Studio (Looker Studio) dashboard by view link; [[Constellation]] runs the multicultural campaigns and the vehicle listing ads and shares only a monthly Sheet. The sources, their box labels, budgets and sheet ids live in `.claude/skills/ai-team/vendor-dashboards.json`; to turn on a new dashboard (Constellation's, when it comes), paste its view link there and set `status` to `active`.

**The read.** The desktop scheduled task `vendor-dash-read` (every day about 12:45 AM, weekends too, so Monday has Friday to Sunday) opens each active dashboard in the Claude Browser (Chrome only if the Claude Browser fails), sets the date preset, and appends the page text to `outputs/ai-team/vendor-dash/{date}/reads.jsonl`: window `yesterday` (the Yesterday preset), window `mtd` (This month to date, or Last month on the 1st), and on the 2nd and 3rd `last_month`. Read only: the link opens without a sign-in, and the task never signs in, never clicks Edit, Share, Download or Request access. Data Studio's robots.txt allows automated access, and a view link read twice a night is ordinary viewing; the real risks are the vendor changing the sharing or the layout, and the script catches both.

**The script.** `python3 .claude/skills/ai-team/scripts/vendor_dash.py status --date {date}` (Magic, tip-off, no network) says whether the read happened and every window showed the right dates. `python3 .claude/skills/ai-team/scripts/vendor_dash.py report --date {date}` (Shaq, one call) validates the reads, pulls GA4 and both vendor sheets read-only, and writes `data/vendor_ppc_NCBMW.md` and `data/vendor_ppc.json` plus the saved sources (`data/vendor_ppc_ga4_NCBMW.json`, `data/vendor_sheet_{source}.json`). Exit 2 means a read is missing or invalid or a pull failed; its `FOR MAGIC` lines say which and carry the Missing tonight wording.

**What the numbers are.**
- The dashboard has no Cost box. Spend is implied: clicks x Avg. CPC (converted), good to about half a cent per click. Always say "implied".
- `Sessions`, `Engagement rate` and `keyEvents:asc_form_submission` on NabThat's dashboard are the WHOLE website in GA4, not NabThat's traffic (verified 2026-09-28: Sep 1 to 27 the dashboard read 13,275 sessions and 70 form submissions; GA4 had 13,011 and 71 across all channels, and 6,762 and 19 from Paid Search, which includes Constellation). Never credit them to NabThat.
- The yesterday window is read about 45 minutes after midnight, so it is preliminary. The script compares it with the same weekday last week, read at the same hour (the lag cancels), and settles the day before from the month-to-date change (approximate, labeled).
- Pace: month to date straight-lined, plus NabThat's fee (15.0% on its own sheet), against the $28,000 a month including fees in the July budget reconciliation. NabThat's own sheet shows July $30,216 and August $30,458 including fees, so the cap is a question for Drew until he rules on it.
- Credit split: GA4 names only Constellation's vehicle listing ads (UTM `constellation_2026_BMWWR_VLA`). NabThat's campaigns and Constellation's Performance Max and branding all land in GA4's untagged `google / cpc` bucket ((organic), (not set)), because neither vendor's Ads account is linked to GA4 property 487046736. The script splits that bucket three ways (by clicks, by spend, and by the vehicle listing ads' measured visit rate) and reports the range. Sep 1 to 27, 2026: NabThat about 70% (64% by spend, 71% by visit rate, 74% by clicks) of 3,409 untagged paid visits and 80 key events. It is an estimate, always said as one, until the vendors link their Ads accounts to GA4.
- Constellation's monthly Sheet (`New Century Stores Monthly Report`, tabs `{Month} {YYYY} (By Language)`, block `New Century BMW (SEM)`) lands after a month closes; until the current month's tab exists, the split uses the newest month's daily pace and says so. The `Jul-Sep` and `Oct-Dec` tabs are from 2024. Constellation's Tuesday email (`New Century BMW_OB_{date}.pdf`) is an inventory pricing report, not ad results.

## CRM (Nick)

**Primary path: scheduled report emails.** Each CRM emails its report to Drew, a Gmail filter files it under the `Morning_CRM` label, and Nick reads the label. Drew never fetches anything. `GD mail-ls --days 3` lists what landed (sender, subject, date, attachment names, a text preview); `GD mail-get --id {msg id} --out ~/.cache/digitalcliq-ai-team/crm/{STORE}/` saves the attachments and body text. On a Monday shift use `--days 4`.

| Store | CRM | Sender to look for | Status 2026-09-17 |
|---|---|---|---|
| SBMW | MomentumCRM | `DoNotReply@drive.sterlingbmw.com`, subject "Morning CRM Sterling BMW", PDF `KeyPerformanceIndicator_{epoch}.pdf`, Monday to Friday at 12:10 AM Pacific (no weekend email; Monday's runs through Sunday). It is Momentum's KPI Summary, month to date through yesterday, at department level only: Internet, Inbound, Showroom, Lease Retention, OEM, Outbound, Appraisal, Financial, Service, Parts. There are no per-source rows, so it gives store and department totals, never lead sources. Drew is adding the Lead Source Report to the same schedule; until it lands, source-level SBMW exists only when Drew drops a Lead Source Report in `CRM Drop/SBMW`. The Sterling BMW Loader (dashboard v2, 2026-09-29) reads the same email read only and never moves or relabels it. Older "Morning CRM Executive Summary Sterling BMW" emails (`executiveSnapshot_*.pdf`) are the retired format: ignore them. | Live |
| NOI | VinSolutions | `reportscheduler@motosnap.com`, subject "Morning CRM NOI Lead Reports ROI", leads month to date. Scheduled 2026-09-17, test received 3:38pm that day. | Live |
| NCBMW | Reynolds FOCUS | No FOCUS email (CAPTCHA on pull, Drew has no scheduling rights). Use BMW NA's `Edward.McRae@bmwna.com` emails instead: "Lead Conversion - {Mon} MTD", "{Mon} MTD RDRs" daily. (Constellation's weekly `reports@helloconstellation.com` email is an inventory pricing report with no leads in it, checked 2026-09-28; Shaq's vendor section covers Constellation.) These are NOT under the label; run `GD mail-ls --days 3 --any-label --query "from:bmwna.com OR from:helloconstellation.com"` too. Without `--any-label` the query only searches inside the label and always comes back empty: that bug made NCBMW read as "no CRM data since 2026-09-17" for four shifts while BMW NA's Lead Conversion (9/22) and daily RDR mails (through 9/23) and Constellation's weekly report (9/22) were all arriving. Drew may drop a FOCUS export in `CRM Drop/NCBMW` about weekly; when one appears, backfill the days it covers. | Partial, weekly CRM depth at best |
| MCP | Tekion | No Tekion email (Drew cannot schedule in Tekion; the store's Tekion admin has to). Drew may drop a Tekion export in `CRM Drop/MCP` about weekly (he is at the store Thursdays); when one appears, backfill the days it covers. | Weekly manual drop until the store schedules it |

The month-to-date reports (SBMW, NOI) restate the whole month each night. Nick derives the day's numbers by comparing to the previous night's file in the prior shift folder; on the first night there is no daily delta, only MTD.

The trailing 4-week baseline does not come from earlier shift folders (changed 2026-10-07): it comes from `outputs/ai-team/ledgers/shift-ledger.jsonl`, which never leaves the vault. `ledgers.py shift append` writes one row per shift, target date and store at the final whistle, and each shift's CRM snapshot rides on one of them per store as month-to-date fields: `crm_period_end`, `crm_leads`, `crm_good_leads` (NOI only), `crm_appointments`, `crm_shows`, `crm_sold`, `crm_cost`, with `sources.crm` naming the file or "override". Daily counts are the step between consecutive period ends in the same month (the later shift wins when two carry the same period end); the first period end of a month is its own count from the 1st, because the month-to-date resets, and the old month's days after its last period end (Sep 30, 2026 for SBMW and NOI, since the 12:10 AM report on the 1st already counts October) are a gap, never a negative step. The ledger holds store totals only; source and model comparisons use the `crm_mtd` files still in the shift folders and the previous month pack's `crm.by_source`. The full method and an example are in `.claude/agents/nick.md` step 2.

**Retention (added 2026-10-07).** Shift folders, for every source and not just the CRM, stay in the vault until the first shift on or after the 15th of the next month. Then `month_close.py close` zips the month's day folders and the dated `vendor-dash/`, `cars-sbmw/` and `gm-notes/` folders into `~/Desktop/DigitalCLIQ Vault Archive/{YYYY-MM}/`, checks every file in the zips, and removes them from the vault, so the folders always reach back at least 14 days and normally no more than about 46. A lookback longer than 14 days reads `outputs/ai-team/ledgers/` (shift ledger, month packs, vendor month-end) or `outputs/ai-team/monthly/{YYYY-MM}.md`, never an old shift folder. The scripts that read the newest earlier copy of a file with no date limit (`cars_watch.py`, `dash_check.py`, `vendor_dash.py`) keep working because close leaves those newest copies in place as carries. Semrush raw files (`data/semrush_*`, `data/seo_join_*.json`, `data/value_line.json`) go in their own `ai-team-{YYYY-MM}-semrush-cache.zip` until Drew rules on the Semrush Terms of Service 30-day cache limit (3.3); inside the shift the Semrush ladder's 7 and 30 day limits below still apply.

The label filter also catches unrelated mail (a "RYAN ASK" thread on 2026-09-15). Ignore anything that is not a CRM or OEM report and tell Magic so the filter gets tightened.

**Fallback path: manual drop.** `DigitalCLIQ Shared Drive / Internal / CRM Drop / {STORE}` (created 2026-09-17), for a day when an email did not arrive and Drew drops a file by hand. Check it after the label. List with `GD drive-ls --folder {id} --processed` (`--days 4` on a Monday; see the next paragraph), download with `GD drive-get --id {file id} --out ~/.cache/digitalcliq-ai-team/crm/{STORE}/{filename}`.

**Dashboard loaders empty the drop folders (added 2026-09-29).** NCBMW's drop-folder loader (installed 2026-09-28) and the Sterling BMW Loader (installed 2026-09-29, runs hourly) move every loaded file into the store folder's `_processed` subfolder within hours, and McPeek's dashboard v2 loader will do the same within 15 minutes once Drew installs it. So a file Drew dropped is usually NOT in the store folder by shift time. `GD drive-ls --folder {store folder id} --processed` lists the store folder plus every file in its `_processed` modified or created in the last 3 days (`--days 4` on a Monday), each row tagged `"in": "drop folder"` or `"in": "_processed"`; it finds `_processed` by name, so it works for a store whose id is not recorded yet, and it hides the loaders' own `[temp] ...` scratch copies. Treat files from either place modified since the last shift as new. A file named `[loaded] ...` still in a store folder is a normal drop the loader could not move (Drive refused the move): read it like any other. `_processed` ids: NCBMW `1hKODGHQayAebAn31Nc900-3piTDMsrCz`, SBMW `1JgN_0VcGMTMkeyIGNOobv2CNuJouuVZY`; MCP's is created by the dashboard's `setupDashboard` (it prints the id). `_needs a look` holds files the loader refused (unrecognized, or customer lists): never read customer lists from it, and never read SBMW's at all (those failed the Sterling loader's own checks: wrong store, scope or date range, or totals that do not add up).

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

Connector caveat (root cause found 2026-09-23): players get the tool list from the start of Magic's current turn, and connectors load a few seconds after turn 1 begins, so every shift that spawned the team in turn 1 left all players with zero connector tools, whatever was signed in. SKILL.md now spawns the team on a later turn, and Magic runs `usage.py --tools` right after the spawn. If Luka still has no Meta tools after one respawn (SKILL.md step 2), Magic pulls the standard set from the lead session into `outputs/ai-team/{date}/data/meta_*.json` (campaigns with status, budget, and ad set flight end dates; campaign insights for yesterday, last 7, and prior 7 days; delivery errors; activity log 14 days). Worthy: only the due files `data/semrush_source.md` lists as FAILED or omits.

Call budget: 25 connector calls per shift. Pull campaign-level insights for all stores in one call where the tool allows, then drill only into what moved. Save every raw response to `outputs/ai-team/{date}/data/meta_*.json` so nobody re-pulls.

Context worth knowing: [[Nissan of Irvine|NOI]] weekend blast plus $800/mo Facebook and Instagram boosts went live 2026-09-19. SBMW Paid Social was flagged 2026-09-18 by the daily GA4 report as high sessions, near-zero key events; Kobe and Luka should settle whether that is traffic quality or tracking.

## SEO / GEO / AEO (Worthy)

**Access (fixed 2026-09-23).** Semrush comes through the claude.ai connector, which the Terminal CLI names `mcp__claude_ai_Semrush__*` (`execute_report`, `get_report_schema`, `position_tracking`, `site_audit`, `projects`, `organic_research`, `keyword_research`). Tools are deferred: run ToolSearch `select:mcp__claude_ai_Semrush__execute_report,mcp__claude_ai_Semrush__get_report_schema` first. The user-scope server `semrush` (`mcp__semrush__*`) was never authenticated and only offers `authenticate`; ignore it. Every "no Semrush" night through 2026-09-23 had one cause: the players were spawned in Magic's first turn, before connectors load. SKILL.md now spawns them on a later turn.

**Semrush ladder (Drew's rule, 2026-09-19, rebuilt 2026-09-28: Worthy gets Semrush himself, and if the connector fails, a browser reads it).** Every Semrush file in `data/` is logged in `data/semrush_source.md` as `{file} | {rung} | {HH:MM} | {units}` (or `FAILED | {reason}`, or `{file} | reused from {D} | 0 units`, meaning the file is `outputs/ai-team/{D}/data/{file}`), and nobody re-pulls a file listed there. Rung labels are historical: `3a`/`3b` are the pre-pull, `1` is Worthy, `2` is Magic.
1. **Pre-shift pull, 12:35 AM** (desktop scheduled task `semrush-prepull`, Mon to Fri, runs in the Claude desktop app, which always has the connector): connector first (`3a pre-pull connector`); for any due file the connector could not produce, it reads the same Semrush pages in Drew's signed-in Chrome (`3b pre-pull browser`, read only: never a credential, never a CAPTCHA, never a click that changes the account). Drew approved the browser fallback on 2026-09-28 knowing the Terms of Service caution (3.3(p) and 3.3(r)).
2. **Worthy's own connector** in the shift (`mcp__claude_ai_Semrush__*`, present whenever Magic spawns after a passing `usage.py --turn-check`): only files the pre-pull did not list, plus draft and on-demand calls (`1 Worthy connector`).
3. **Magic's connector** when Worthy has no tools after one respawn (`2 Magic connector`).
4. **Nothing fresh:** Worthy uses the newest Semrush files from the last 7 days with their dates, GA4-only past that, never anything past 30 days (ToS 3.3). Data gaps names the reason and the fix.

**Unit budget (corrected 2026-09-28 from measured `metadata.usage.api_units`).** About 50,000 units a month, shared with every daytime Semrush use. The 2026-09-23 table under-priced two reports: the Position Tracking overview costs 100 to 300 per campaign (900 for the four), and `resource_organic` with nine export columns cost 800 to 1,000 per store for 20 rows (not 200), which put 9/28 at about 5,700 units. New plan, about 23,650 a month: Monday 3,400 (overview 900 plus keywords 2,500 max), Thursday 900 (overview only), Tuesday, Wednesday and Friday nothing (`seo_join.py` and `value_line.py` read files up to 7 days old), draft nights one question pull (about 400, two a week at most), first Monday of the month 1,550 more (rank history plus lost keywords). Log every call's units; reprice after the first Monday. `tracking_position_organic` costs 100 units per ROW: on demand only, `display_limit` 10 or less.

**Recipes.** All through `execute_report` with `report` and `params`; check `get_report_schema` before changing a param.

| When | Report | Params | Units (measured 2026-09-28 unless marked) |
|---|---|---|---|
| Monday and Thursday | `tracking_overview_organic` | `{"campaign_id":"<id>","url":"*.<domain>/*"}` per campaign below | 900 for the four |
| Monday | `resource_organic`, brand terms excluded | `{"target":"<domain>","database":"us","display_limit":10,"display_sort":"traffic_desc","export_columns":["keyword","position","previous_position","volume","url","traffic","position_type"],"display_filter":[{"field":"keyword","operation":"contains","sign":"-","value":"<brand>"}]}` (one filter entry per brand term; entries combine as AND) | about 50 per row, 500 per store max (unconfirmed at 7 columns; log it) |
| First Monday of the month | `resource_organic`, lost keywords | same plus `"display_positions":"lost","display_sort":"volume_desc","display_limit":5` | about 250 per store |
| First Monday of the month | `resource_rank_history` | `{"target":"<domain>","database":"us","display_limit":6,"display_sort":"date_desc"}`, default columns | 60 to 70 per store |
| Draft nights, two a week at most | `phrase_questions` | `{"phrase":"<seed>","database":"us","display_limit":10,...}` | 400 |
| On Drew's go only | `site_audit` info | `{"id":<project_id>}` | about 100 |
| On demand | `tracking_position_organic` | overview params plus `"display_limit":10` | 100 per row |
| Dropped | `resource_organic_unique` (top pages) | | too costly for what it added |

Brand terms to exclude (misspellings included): SBMW "sterling", "stearling"; NCBMW "century", "centry"; NOI "nissan of irvine", "nissanofirvine", "irvine nissan" (not "irvine" alone: "nissan dealer irvine" is a non-brand term worth keeping); MCP "mcpeek"; ATLAS "atlas".

**Position Tracking campaigns** (id format `{project_id}_{campaign_number}`; the API cannot list them, these came from Semrush's own emails):

| Store | Project | campaign_id | Location | Note |
|---|---|---|---|---|
| SBMW | 24960897 | `24960897_3046666` | Orange County, CA, desktop | Only 10 keywords, loaded 2025-06-06; 6 do not rank. Needs a refresh by Drew. |
| NCBMW | 29670819 | `29670819_5048343` | United States | |
| NOI | 29776292 | `29776292_4882073` | Irvine, CA | 4 Nissan competitors tracked |
| ATLAS | 25619865 | `25619865_3269620` | United States | |
| MCP | 29478388 | none | | No Position Tracking campaign; Drew's call |

**Files (so nobody re-pulls and `seo_join.py` can read them).** Write each response's `data` text exactly as returned (semicolon rows with the header line): `data/semrush_kw_{STORE}.csv` (the Monday non-brand `resource_organic`), `data/semrush_lost_{STORE}.csv`; JSON reports as `data/semrush_pt_{STORE}.json` (tracking overview, with `rung`, `pulled_at`, and `api_units` added), `data/semrush_audit_{STORE}.json`, `data/semrush_rank_history.json`, `data/semrush_ideas_{seed}.csv`. Browser reads (rung 3b) go to `data/semrush_web_pt_{STORE}.json` (values exactly as the page showed them) and `data/semrush_organic_positions.md` (the format `seo_join.py` already reads). Every file gets one line in `data/semrush_source.md`. A file from a Tuesday, Wednesday or Friday shift is normally the Monday or Thursday pull from up to 7 days earlier: `seo_join.py` finds it on its own.

**Semrush email digest (added 2026-09-29).** The pre-pull's step 4 reads every Semrush email from the last 4 days in Gmail (rank alerts, weekly Position Tracking, Site Audit, Backlink Audit, On Page SEO Checker, Maps rank, Listings, blog ideas) and writes `data/semrush_email_digest.md`: a `Flags for Worthy` list, then one section per store, one bullet per email tagged `[msg {id}]`. It costs 0 API units and runs every weeknight, so on Tuesday, Wednesday and Friday it is the only fresh Semrush signal. Worthy reads the digests from the last 7 days, cites them as "Semrush email, {date}", and uses them for what the API does not give (Site Health, backlink toxicity, Maps rank, On Page ideas). Drew does not read these emails himself; anything worth his attention goes in the brief.

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

Signals: RED when the CRM source says the CRM tab is empty or carries a `CHECK:` note, when leads month to date are 0 after the 3rd, or when a CRM headline card or a paid vendor block names a month before the last closed month. Exception (2026-09-29): Pixel Motion emails Sterling's co-op files for a month about the 15th of the next month, so SBMW's Pixel Motion block may show the month before the last closed month through the 20th without a flag (on Oct 1 to 20 August is current; RED from Oct 21, or at once if it is two months behind). The grace is `ppc_due_day` in the script's `DASHBOARDS`, SBMW only, and matches the v2 feed's own `ppc.pixel.dueBy`; NCBMW and MCP have none. AMBER when an SEO card names a month before the last closed month, when the SEO months end before the last closed month or were never built, or when the dashboard's `updated` stamp is more than 3 days old. The gross "estimate" wording is by design and never flagged; the top-level `seoMonth` is blank on all three by design and never read. Sterling's fixes point at the Ingest Log tab of its Sheet, because the Sterling BMW Loader fills that Sheet from the nightly KPI Summary email, Pixel Motion's "Sterling BMW Coop Files {Month}" email and `CRM Drop/SBMW`; nothing is pasted by hand. If Drew ever turns on the Sterling dashboard's optional `DASH_KEY`, the endpoint answers "not authorized" without `?key=` and SBMW reads NO DATA every night until dash_check passes the key (not built; see the comment above `DASHBOARDS`).

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
