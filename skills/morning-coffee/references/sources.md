# Coffee Report: Source Registry

Single source of truth for every data source the Coffee Report pulls. Built 2026-07-15 from Drew's Chrome bookmarks (read from `~/Library/Application Support/Google/Chrome/Default/AccountBookmarks`), `Context/connector-ids.md`, and live connector enumeration. If a URL or id here goes stale, fix it HERE, agents read this file, not the bookmarks.

## CRM systems (browser pulls via claude-in-chrome)

Each agent claims its OWN Chrome tab. Sessions ride Drew's real Chrome logins. NEVER enter credentials, on a login wall, return `{"available": false, "login_required": true}` and move on.

| Store | Dealer key | CRM | Entry URL | Runbook |
|---|---|---|---|---|
| Sterling BMW | `sterling` | Momentum (UDC) | `http://sterlingbmwmom.udccrm.com/acrm/servlet/login` | `crm-runbooks/sbmw-momentum.md` |
| New Century BMW | `new_century` | Focus (Reynolds & Reynolds) | `https://cm.dealer.reyrey.net/` | `crm-runbooks/ncbmw-focus.md` |
| Nissan of Irvine | `nissan` | VinSolutions (Cox) | `https://vinsolutions.app.coxautoinc.com/vinconnect/` | `crm-runbooks/noi-vinsolutions.md` |
| McPeek CDJR | `mcpeek` | Tekion | `https://app.tekioncloud.com/` | `crm-runbooks/mcp-tekion.md` |

## GA4 (API-first via Zapier, browser fallback)

Zapier action: `google_analytics_4_run_report_for_a_property` (selected_api `GoogleAnalytics4CLIAPI`, action key `runReport`). Requires BOTH `accountId` and `propertyId`. Raw `_zap_raw_request` is blocked on this plan, use the structured action only.

| Store | GA account id | Property id | Browser fallback URL |
|---|---|---|---|
| Sterling BMW | `176753582` | `297584513` | `https://analytics.google.com/analytics/web/#/p297584513/reports/explorer?params=_u.dateOption%3Dyesterday&r=lifecycle-traffic-acquisition-v2` |
| Nissan of Irvine | `164916710` | `277100567` | `https://analytics.google.com/analytics/web/#/p277100567/reports/explorer?params=_u.dateOption%3Dyesterday&r=lifecycle-traffic-acquisition-v2` |
| McPeek CDJR | `192484733` | `321466006` | `https://analytics.google.com/analytics/web/#/p321466006/reports/explorer?params=_u.dateOption%3Dyesterday&r=lifecycle-traffic-acquisition-v2` |
| New Century BMW | `265694905` | `487046736` | `https://analytics.google.com/analytics/web/#/p487046736/reports/explorer?params=_u.dateOption%3Dyesterday&r=lifecycle-traffic-acquisition-v2` |

Standard pull: dimensions `["sessionDefaultChannelGroup"]`, metrics `["sessions","engagedSessions","engagementRate","averageSessionDuration","keyEvents","sessionKeyEventRate"]`, start=end=yesterday, `dateName: "yesterday"`.

Resolved 2026-07-19: the Zapier GA4 connection auth error from 2026-07-15 is fixed. Drew reconnected the account. The API path is the primary GA4 pull again. Keep the browser fallback wired as a defensive backstop, but do not report GA4 as blocked. If the auth error ever returns, reconnect at https://mcp.zapier.com/mcp/servers/fc4a7465-f436-43d7-8c7e-e0874dc9af63/config.

## Meta Ads (Meta Ads MCP: direct API)

Enumerated live 2026-07-15 via `ads_get_ad_accounts`. Only active + queryable accounts listed.

| Account key | Name | Ad account id | Covers |
|---|---|---|---|
| `main` | DigitalCLIQ (Main) | `932166720307788` | All client paid social except McPeek |
| `mcpeek` | McPeek Dodge | `1218321493439724` | McPeek CDJR |

Closed/skip: `42582586` (Mode 2), `746931666216776` (old Nissan Irvine). City Church (`590327600198324`) is not a Coffee Report client.

## Semrush (Semrush MCP: direct API)

| Store | Domain | Project id | Site audit |
|---|---|---|---|
| Sterling BMW | sterlingbmw.com | `24960897` | yes |
| New Century BMW | newcenturybmw.com | `29670819` | yes |
| McPeek CDJR | mcpeeks.com | `29478388` | yes |

Position tracking NOT used (expensive, not gathering). Movers come from `domain_organic` rise/fall/new/lost.

## Live dashboard endpoints (plain HTTPS GET, no auth session needed)

Apps Script web-app endpoints return the dashboard's current JSON payload.

| Store key | Store | Endpoint |
|---|---|---|
| `ncbmw` | New Century BMW | `https://script.google.com/macros/s/AKfycbwdi91LD8vFv5A3PDCJQ4BIm4TWkzDWei49G_dCf0fnxfMucDHORapSKtLcnoQ9aMpyWA/exec` |
| `sbmw` | Sterling BMW | `https://script.google.com/macros/s/AKfycbxVJugSl93A9egpeeXymBMEzBv6M5yWMxs-Prn-VEP-MM0ragBhWDP0xdKXDlAl_ijgJQ/exec` |
| `mcpeek` | McPeek CDJR | `https://script.google.com/macros/s/AKfycbxswEKhEK-Sr98XkVe_mmFs8SqyQlsaGfzNXIAfuH2EatFJixHtUnX3nfhyqFoKPRjl/exec` |

Backing sheets (for reference only): NCBMW `1JJcHIC1253Dtpp50OGIRhgNCw-g-DqRgkETIJa8okAE`, SBMW `1Ki2RjJUc4AN4A-ZFgqNLQpENDySVjgULR4xG6UTSpCU`, McPeek `12vhp5FyujzOpCVcIspPszmhbLxy3FwnsjJ4UxKbFXpA`.

Staleness rule: if the payload's latest data date is more than 3 days old, set `stale: true` with a `stale_note`.

## Emailed CRM reports (Zapier Gmail: attachment pull, verified working 2026-07-15)

Flow: `execute_zapier_read_action` with `selected_api: "GoogleMailV2CLIAPI"`, `action: "gmail_find_email"` (use this exact action name, the key `message` collides with Send Email), query below → response includes `attachments[].url` (S3, directly `curl`-able) → download to scratchpad → parse.

Search query template (last 36h):

```
has:attachment newer_than:2d {sender_or_subject_filter}
```

Known emailed reports (extend as new ones appear):

| Report | Matches | Store |
|---|---|---|
| Momentum Executive New Car Snapshot | `subject:("Momentum Executive")` | Sterling BMW |
| LEADME conquest email reports | `from:secure-response.net` | varies |

Sweep query for anything new: `has:attachment newer_than:2d subject:(report OR leads OR snapshot OR export)`, then match filenames/subjects to stores by name.

## Other ids

- Google Calendar: DigitalCLIQ Master `84r17k53s6bdh22emr9a22meh8@group.calendar.google.com`, plus `primary` and family calendar (see SKILL.md agent A).
- Notion TASKS db data source: `collection://1e6886e3-bb0e-801d-a147-000b3b4c5ace`.
- Zapier MCP config page (reconnect broken app auth): `https://mcp.zapier.com/mcp/servers/fc4a7465-f436-43d7-8c7e-e0874dc9af63/config`.
