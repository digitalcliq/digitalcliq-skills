#!/usr/bin/env python3
"""Google data access for the DigitalCLIQ AI team. Standard library only.

One OAuth login (Drew's Google account, read-only scopes) covers GA4, Sheets,
and Drive so the night shift never needs a browser or a claude.ai connector.

Secrets live OUTSIDE the vault in ~/.config/digitalcliq-ai-team/:
  google_client.json   OAuth "Desktop app" client downloaded from Google Cloud
  google_token.json    written by `gdata.py auth`, chmod 600

Commands:
  auth [--gsc]                           one-time browser consent (Drew runs this); --gsc adds Search Console
  status                                 token + per-property access check
  ga4 --store SBMW --start D --end D --dims a,b --metrics x,y [--limit N]
  ga4-nightly [--date D] --out DIR       standard nightly pull, all stores, with flags. Channel flags
                                         compare flag_date (the day before the target, the last complete
                                         day); the target day's own counts are preliminary. Also writes the
                                         organic landing sections seo_join.py reads (last 28 and prior 28
                                         days ending on the target date, AI engine sources excluded)
  gsc-sites                              Search Console properties this login can read
  gsc-nightly [--date D] --out DIR       gsc_{STORE}.json per store in GSC_SITES: page and page x query,
                                         last 28 and prior 28 days ending 3 days before the target date
  sheet-tabs --id SHEET_ID
  sheet --id SHEET_ID --range 'Tab!A1:Z500'
  drive-find --name "CRM Drop"
  drive-ls --folder FOLDER_ID [--processed [--days 3]]
                                         direct children; --processed adds files in its _processed subfolder
                                         modified or created in the last N days (the dashboard loaders move
                                         every loaded drop there), each row tagged "in"
  drive-get --id FILE_ID --out PATH      Google Sheets export as .xlsx, others raw
  mail-ls [--days 3] [--query 'from:x']  CRM report emails under the Morning_CRM label
  mail-get --id MSG_ID --out DIR         save that email's attachments + text body to DIR

Search Console setup (optional, never required by the other commands):
  1. Enable "Google Search Console API" in the same Google Cloud project as google_client.json.
  2. Drew runs `gdata.py auth --gsc` in a terminal. It asks for the usual scopes plus
     webmasters.readonly and replaces google_token.json. Plain `auth` still asks for the usual scopes only.
  3. Run `gdata.py gsc-sites`, then fill GSC_SITES below by hand (store code to siteUrl, exactly as listed).
  Until step 2 is done, gsc-sites and gsc-nightly stop with "Search Console not authorized yet" and
  everything else keeps working on the existing token.
"""
import argparse
import base64
import datetime as dt
import http.server
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

try:
    from zoneinfo import ZoneInfo
    PACIFIC = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover
    PACIFIC = None

CONFIG_DIR = os.path.expanduser("~/.config/digitalcliq-ai-team")
CLIENT_FILE = os.path.join(CONFIG_DIR, "google_client.json")
TOKEN_FILE = os.path.join(CONFIG_DIR, "google_token.json")

SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]

# Search Console is opt-in: requested only by `auth --gsc`, never added to SCOPES,
# so a token saved without it keeps working for everything else.
GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
GSC_NOT_AUTHORIZED = ("Search Console not authorized yet: Drew runs "
                      "python3 .claude/skills/ai-team/scripts/gdata.py auth --gsc")

# Store code -> Search Console siteUrl, exactly as `gdata.py gsc-sites` lists it
# (a URL-prefix property like "https://www.sterlingbmw.com/" or a domain property like
# "sc-domain:sterlingbmw.com"). Empty until Drew runs auth --gsc and fills it by hand.
GSC_SITES = {
}
GSC_PAGE_LIMIT = 500
GSC_PAGE_QUERY_LIMIT = 1000
GSC_LAG_DAYS = 3  # final Search Console data trails by about 3 days

# Gmail label that Drew's filters put the scheduled CRM report emails under.
CRM_LABEL = "Morning_CRM"

# Source of truth: Context/connector-ids.md (GA4 Inventory). Update both together.
GA4_PROPERTIES = {
    "SBMW": "297584513",
    "NCBMW": "487046736",
    "NOI": "277100567",
    "MCP": "321466006",
    "ATLAS": "408152419",
}

AI_SOURCE_REGEX = (
    "chatgpt|openai|perplexity|gemini|bard|copilot|claude|anthropic|"
    "you\\.com|phind|poe\\.com|meta\\.ai|deepseek|grok"
)
ORGANIC_KEYS = ("organic_windows", "organic_landing_last28", "organic_landing_prior28",
                "organic_landing_events_last28", "ai_referrals_by_landing_last28")
AI_SOURCE_FILTER = {"filter": {"fieldName": "sessionSource",
                               "stringFilter": {"matchType": "PARTIAL_REGEXP", "value": AI_SOURCE_REGEX}}}
# Organic Search sessions minus any AI engine source, so AI referrals are never counted twice.
ORGANIC_NON_AI_FILTER = {"andGroup": {"expressions": [
    {"filter": {"fieldName": "sessionDefaultChannelGroup",
                "stringFilter": {"matchType": "EXACT", "value": "Organic Search"}}},
    {"notExpression": AI_SOURCE_FILTER},
]}}
KEY_EVENTS_ONLY = {"filter": {"fieldName": "keyEvents",
                              "numericFilter": {"operation": "GREATER_THAN", "value": {"doubleValue": 0}}}}

# A channel is flagged when the flag day (the last complete day, see cmd_ga4_nightly) moves this
# far from its trailing 4-week same-weekday average AND the average is big enough to matter.
FLAG_PCT = 25.0
FLAG_MIN_AVG_SESSIONS = 20.0


def die(msg, code=1):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------- auth

def _load_client():
    if not os.path.exists(CLIENT_FILE):
        die("missing %s. See references/setup.md step 2." % CLIENT_FILE)
    with open(CLIENT_FILE) as f:
        data = json.load(f)
    block = data.get("installed") or data.get("web")
    if not block:
        die("google_client.json is not a Desktop app OAuth client file.")
    return block["client_id"], block["client_secret"]


def _post_form(url, fields):
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        die("token endpoint %s: %s" % (e.code, e.read().decode()[:400]))


def cmd_auth(args):
    scopes = SCOPES + ([GSC_SCOPE] if getattr(args, "gsc", False) else [])
    client_id, client_secret = _load_client()
    state = secrets.token_urlsafe(16)
    got = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>DigitalCLIQ AI team: Google access saved. Close this tab.</h2>")

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    redirect = "http://127.0.0.1:%d" % server.server_address[1]
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    })
    print("Opening the Google consent page. Sign in as the account that holds GA4 access.")
    print("If no browser opens, paste this URL:\n" + url)
    webbrowser.open(url)
    while "code" not in got and "error" not in got:
        server.handle_request()
    if got.get("error"):
        die("consent refused: " + got["error"])
    if got.get("state") != state:
        die("state mismatch, aborting.")
    tok = _post_form("https://oauth2.googleapis.com/token", {
        "code": got["code"],
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect,
        "grant_type": "authorization_code",
    })
    if "refresh_token" not in tok:
        die("Google returned no refresh token. Remove the app at myaccount.google.com/permissions and run auth again.")
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump({"refresh_token": tok["refresh_token"], "scopes": scopes,
                   "created": dt.datetime.now().isoformat()}, f)
    os.chmod(TOKEN_FILE, 0o600)
    print("Saved. Run `gdata.py status` to confirm every property answers.")


_ACCESS = {}


def access_token():
    if _ACCESS.get("token") and _ACCESS["exp"] > dt.datetime.now():
        return _ACCESS["token"]
    if not os.path.exists(TOKEN_FILE):
        die("not authorized yet. Drew runs: python3 gdata.py auth")
    client_id, client_secret = _load_client()
    with open(TOKEN_FILE) as f:
        refresh = json.load(f)["refresh_token"]
    tok = _post_form("https://oauth2.googleapis.com/token", {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    })
    _ACCESS["token"] = tok["access_token"]
    _ACCESS["exp"] = dt.datetime.now() + dt.timedelta(seconds=int(tok.get("expires_in", 3000)) - 120)
    _ACCESS["scope"] = tok.get("scope")  # space separated scopes Google actually granted, when it says
    return _ACCESS["token"]


def granted_scopes():
    """Scopes on the saved token: Google's refresh answer first, what `auth` saved as the fallback."""
    access_token()
    if _ACCESS.get("scope"):
        return set(_ACCESS["scope"].split())
    try:
        with open(TOKEN_FILE) as f:
            return set(json.load(f).get("scopes") or [])
    except (OSError, ValueError):
        return set()


def api(url, payload=None, raw=False):
    headers = {"Authorization": "Bearer " + access_token()}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read() if raw else json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:500]
        raise RuntimeError("HTTP %s from %s: %s" % (e.code, url.split("?")[0], detail))


# ---------------------------------------------------------------- GA4

def ga4_report(store, start, end, dims, metrics, limit=1000, dim_filter=None, order_metric=None,
               metric_filter=None):
    prop = GA4_PROPERTIES.get(store.upper())
    if not prop:
        die("unknown store %s. Known: %s" % (store, ", ".join(GA4_PROPERTIES)))
    body = {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "dimensions": [{"name": d} for d in dims],
        "metrics": [{"name": m} for m in metrics],
        "limit": str(limit),
    }
    if dim_filter:
        body["dimensionFilter"] = dim_filter
    if metric_filter:
        body["metricFilter"] = metric_filter
    if order_metric:
        body["orderBys"] = [{"metric": {"metricName": order_metric}, "desc": True}]
    res = api("https://analyticsdata.googleapis.com/v1beta/properties/%s:runReport" % prop, body)
    rows = []
    for r in res.get("rows", []):
        row = {}
        for d, v in zip(dims, r.get("dimensionValues", [])):
            row[d] = v.get("value")
        for m, v in zip(metrics, r.get("metricValues", [])):
            try:
                num = float(v.get("value"))
                row[m] = int(num) if num.is_integer() else round(num, 4)
            except (TypeError, ValueError):
                row[m] = v.get("value")
        rows.append(row)
    return rows


def compute_channel_flags(daily_rows, target):
    """daily_rows: [{date: YYYYMMDD, sessionDefaultChannelGroup, sessions, keyEvents}].
    Compares the given date (ga4-nightly passes flag_date) to the trailing 4 same-weekday dates."""
    tkey = target.strftime("%Y%m%d")
    prior_keys = [(target - dt.timedelta(days=7 * i)).strftime("%Y%m%d") for i in range(1, 5)]
    by = {}
    for r in daily_rows:
        ch = r.get("sessionDefaultChannelGroup") or "(unknown)"
        by.setdefault(ch, {})[r.get("date")] = r
    out = []
    for ch, days in sorted(by.items()):
        today = days.get(tkey, {})
        prior = [days.get(k, {}) for k in prior_keys]
        entry = {"channel": ch}
        for metric in ("sessions", "keyEvents"):
            val = float(today.get(metric, 0) or 0)
            avg = sum(float(p.get(metric, 0) or 0) for p in prior) / 4.0
            pct = None if avg == 0 else round((val - avg) / avg * 100.0, 1)
            entry[metric] = int(val)
            entry[metric + "_4wk_same_weekday_avg"] = round(avg, 1)
            entry[metric + "_pct_vs_avg"] = pct
        s_avg = entry["sessions_4wk_same_weekday_avg"]
        s_pct = entry["sessions_pct_vs_avg"]
        entry["flag"] = bool(s_pct is not None and s_avg >= FLAG_MIN_AVG_SESSIONS and abs(s_pct) >= FLAG_PCT)
        if entry["flag"]:
            entry["direction"] = "down" if s_pct < 0 else "up"
        out.append(entry)
    return out


def pacific_today():
    now = dt.datetime.now(PACIFIC) if PACIFIC else dt.datetime.now()
    return now.date()


def cmd_ga4(args):
    rows = ga4_report(args.store, args.start, args.end, args.dims.split(","),
                      args.metrics.split(","), limit=args.limit)
    json.dump({"store": args.store.upper(), "start": args.start, "end": args.end, "rows": rows},
              sys.stdout, indent=1)
    print()


def cmd_ga4_nightly(args):
    target = dt.date.fromisoformat(args.date) if args.date else pacific_today() - dt.timedelta(days=1)
    # Channel flags compare the last COMPLETE day, not the target. The 1 AM pull sees the target
    # day while GA4 is still processing it, so it always reads low (9/24 re-pull: SBMW 808 at 1 AM
    # vs 1,328 final, NCBMW 286 vs 557) and every channel looked "down". The day before the target
    # matched the final numbers exactly. target_date stays the target: health.py and value_line.py
    # read it, and the target day's counts are still reported, labeled preliminary.
    flag_date = target - dt.timedelta(days=1)
    # Preliminary when the target ended within the last day (every default run). A --date pull of an
    # older day (Monday's Friday and Saturday) is already final: 9/23 pulled at 1 AM 9/25 matched final.
    preliminary = (pacific_today() - target).days <= 1
    os.makedirs(args.out, exist_ok=True)
    d = lambda n: (target - dt.timedelta(days=n)).isoformat()
    t = target.isoformat()
    summary = {"target_date": t, "target_preliminary": preliminary, "flag_date": flag_date.isoformat(),
               "weekday": target.strftime("%A"), "flag_weekday": flag_date.strftime("%A"), "stores": {}}
    for store in GA4_PROPERTIES:
        pack = {"store": store, "property_id": GA4_PROPERTIES[store], "target_date": t,
                "target_preliminary": preliminary, "flag_date": flag_date.isoformat(),
                "pulled_at": dt.datetime.now().isoformat(timespec="seconds"), "errors": []}

        def grab(key, fn):
            try:
                pack[key] = fn()
            except Exception as e:  # keep going, never guess
                pack[key] = None
                pack["errors"].append("%s: %s" % (key, e))

        daily = []

        def _daily():
            # 29 days back so flag_date (target - 1) still has its four prior same-weekday days.
            rows = ga4_report(store, d(29), t, ["date", "sessionDefaultChannelGroup"],
                              ["sessions", "engagedSessions", "keyEvents"], limit=2000)
            daily.extend(rows)
            return [r for r in rows if r["date"] >= (target - dt.timedelta(days=6)).strftime("%Y%m%d")]

        grab("channel_daily_last7", _daily)
        pack["channel_flags"] = compute_channel_flags(daily, flag_date) if daily else None
        grab("source_medium_last7", lambda: ga4_report(
            store, d(6), t, ["sessionSourceMedium"],
            ["sessions", "engagedSessions", "engagementRate", "keyEvents"], 40, order_metric="sessions"))
        grab("source_medium_prior7", lambda: ga4_report(
            store, d(13), d(7), ["sessionSourceMedium"],
            ["sessions", "engagedSessions", "engagementRate", "keyEvents"], 40, order_metric="sessions"))
        grab("key_events_by_channel_last7", lambda: ga4_report(
            store, d(6), t, ["eventName", "sessionDefaultChannelGroup"], ["keyEvents"], 100,
            order_metric="keyEvents"))
        grab("key_events_by_channel_prior7", lambda: ga4_report(
            store, d(13), d(7), ["eventName", "sessionDefaultChannelGroup"], ["keyEvents"], 100,
            order_metric="keyEvents"))
        grab("landing_pages_last7", lambda: ga4_report(
            store, d(6), t, ["landingPagePlusQueryString", "sessionDefaultChannelGroup"],
            ["sessions", "engagementRate", "keyEvents"], 40, order_metric="sessions"))
        grab("paid_campaigns_last7", lambda: ga4_report(
            store, d(6), t, ["sessionCampaignName", "sessionSourceMedium"],
            ["sessions", "engagedSessions", "engagementRate", "averageSessionDuration", "keyEvents"], 40,
            dim_filter={"filter": {"fieldName": "sessionDefaultChannelGroup",
                                   "stringFilter": {"matchType": "PARTIAL_REGEXP", "value": "Paid|Cross-network"}}},
            order_metric="sessions"))
        grab("ai_engine_referrals_last28", lambda: ga4_report(
            store, d(27), t, ["sessionSource"], ["sessions", "engagedSessions", "keyEvents"], 50,
            dim_filter=AI_SOURCE_FILTER, order_metric="sessions"))
        # Organic landing pages for seo_join.py. sessionCampaignName separates Google Business
        # Profile clicks (utm_campaign googlemybusiness, scgooglemybusiness, listings) from web results.
        pack["organic_windows"] = {"last28": [d(27), t], "prior28": [d(55), d(28)]}
        grab("organic_landing_last28", lambda: ga4_report(
            store, d(27), t, ["landingPage", "sessionCampaignName"],
            ["sessions", "engagedSessions", "keyEvents"], 500,
            dim_filter=ORGANIC_NON_AI_FILTER, order_metric="sessions"))
        grab("organic_landing_prior28", lambda: ga4_report(
            store, d(55), d(28), ["landingPage", "sessionCampaignName"],
            ["sessions", "engagedSessions", "keyEvents"], 500,
            dim_filter=ORGANIC_NON_AI_FILTER, order_metric="sessions"))
        grab("organic_landing_events_last28", lambda: ga4_report(
            store, d(27), t, ["landingPage", "eventName"], ["keyEvents"], 500,
            dim_filter=ORGANIC_NON_AI_FILTER, metric_filter=KEY_EVENTS_ONLY, order_metric="keyEvents"))
        grab("ai_referrals_by_landing_last28", lambda: ga4_report(
            store, d(27), t, ["sessionSource", "landingPage"], ["sessions", "engagedSessions", "keyEvents"], 200,
            dim_filter=AI_SOURCE_FILTER, order_metric="sessions"))
        # The organic sections are large (up to 500 rows each) and only seo_join.py reads them,
        # so they go to their own file and Kobe's ga4_{STORE}.json stays the size it always was.
        organic = {k: pack[k] for k in ("store", "target_date") if k in pack}
        for k in ORGANIC_KEYS:
            if k in pack:
                organic[k] = pack.pop(k)
        organic["errors"] = [e for e in pack["errors"] if any(k in str(e) for k in ORGANIC_KEYS)]
        with open(os.path.join(args.out, "ga4_organic_%s.json" % store), "w") as f:
            json.dump(organic, f, indent=1)
        path = os.path.join(args.out, "ga4_%s.json" % store)
        with open(path, "w") as f:
            json.dump(pack, f, indent=1)
        flags = [c for c in (pack.get("channel_flags") or []) if c.get("flag")]
        summary["stores"][store] = {"file": path, "errors": pack["errors"],
                                    "flagged_channels": [{"channel": c["channel"], "direction": c["direction"],
                                                          "sessions": c["sessions"],
                                                          "avg": c["sessions_4wk_same_weekday_avg"],
                                                          "pct": c["sessions_pct_vs_avg"]} for c in flags]}
    json.dump(summary, sys.stdout, indent=1)
    print()


def cmd_status(_args):
    access_token()
    print("token: ok")
    y = (pacific_today() - dt.timedelta(days=1)).isoformat()
    for store in GA4_PROPERTIES:
        try:
            rows = ga4_report(store, y, y, [], ["sessions"])
            print("GA4 %-6s ok   sessions %s = %s" % (store, y, rows[0]["sessions"] if rows else 0))
        except Exception as e:
            print("GA4 %-6s FAIL %s" % (store, str(e)[:200]))
    if GSC_SCOPE in granted_scopes():
        print("GSC        authorized, %d store(s) mapped in GSC_SITES" % len(GSC_SITES))
    else:
        print("GSC        not authorized (optional, nothing else needs it)")


# ---------------------------------------------------------------- Search Console (optional)

GSC_API = "https://www.googleapis.com/webmasters/v3/"


def require_gsc():
    if GSC_SCOPE not in granted_scopes():
        die(GSC_NOT_AUTHORIZED)


def gsc_api(url, payload=None):
    try:
        return api(url, payload)
    except RuntimeError as e:
        msg = str(e)
        low = msg.lower()
        if "http 403" in low and ("scope" in low or "insufficient" in low):
            die(GSC_NOT_AUTHORIZED)
        if "http 403" in low and ("service_disabled" in low or "has not been used" in low):
            die("Search Console API is off in the Google Cloud project that owns google_client.json. "
                "Drew enables \"Google Search Console API\" there, then reruns this command.")
        raise


def gsc_query(site, start, end, dims, limit):
    body = {"startDate": start, "endDate": end, "dimensions": dims, "rowLimit": limit,
            "dataState": "final", "type": "web"}
    res = gsc_api(GSC_API + "sites/%s/searchAnalytics/query" % urllib.parse.quote(site, safe=""), body)
    rows = []
    for r in res.get("rows", []):
        row = dict(zip(dims, r.get("keys", [])))
        row["clicks"] = int(r.get("clicks", 0))
        row["impressions"] = int(r.get("impressions", 0))
        row["ctr"] = round(float(r.get("ctr", 0)), 4)
        row["position"] = round(float(r.get("position", 0)), 2)
        rows.append(row)
    return rows


def cmd_gsc_sites(_args):
    require_gsc()
    sites = gsc_api(GSC_API + "sites").get("siteEntry", [])
    print(json.dumps({"sites": sites, "mapped": GSC_SITES,
                      "note": "copy each store's siteUrl exactly into GSC_SITES in gdata.py"}, indent=1))


def cmd_gsc_nightly(args):
    require_gsc()
    if not GSC_SITES:
        die("GSC_SITES in gdata.py is empty: run gdata.py gsc-sites and map each store code to its siteUrl.")
    target = dt.date.fromisoformat(args.date) if args.date else pacific_today() - dt.timedelta(days=1)
    end = target - dt.timedelta(days=GSC_LAG_DAYS)
    os.makedirs(args.out, exist_ok=True)
    d = lambda n: (end - dt.timedelta(days=n)).isoformat()
    windows = {"last28": [d(27), d(0)], "prior28": [d(55), d(28)]}
    summary = {"target_date": target.isoformat(), "end_date": d(0), "windows": windows, "stores": {}}
    for store, site in GSC_SITES.items():
        pack = {"store": store, "site_url": site, "target_date": target.isoformat(), "end_date": d(0),
                "windows": windows, "data_state": "final",
                "pulled_at": dt.datetime.now().isoformat(timespec="seconds"), "errors": []}

        def grab(key, fn):
            try:
                pack[key] = fn()
            except Exception as e:  # keep going, never guess
                pack[key] = None
                pack["errors"].append("%s: %s" % (key, e))

        grab("pages_last28", lambda: gsc_query(site, d(27), d(0), ["page"], GSC_PAGE_LIMIT))
        grab("pages_prior28", lambda: gsc_query(site, d(55), d(28), ["page"], GSC_PAGE_LIMIT))
        grab("page_query_last28", lambda: gsc_query(site, d(27), d(0), ["page", "query"], GSC_PAGE_QUERY_LIMIT))
        grab("page_query_prior28", lambda: gsc_query(site, d(55), d(28), ["page", "query"], GSC_PAGE_QUERY_LIMIT))
        path = os.path.join(args.out, "gsc_%s.json" % store.upper())
        with open(path, "w") as f:
            json.dump(pack, f, indent=1)
        summary["stores"][store] = {"file": path, "errors": pack["errors"],
                                    "pages_last28": len(pack.get("pages_last28") or []),
                                    "clicks_last28": sum(r["clicks"] for r in pack.get("pages_last28") or [])}
    json.dump(summary, sys.stdout, indent=1)
    print()


# ---------------------------------------------------------------- Sheets + Drive

def cmd_sheet_tabs(args):
    res = api("https://sheets.googleapis.com/v4/spreadsheets/%s?fields=properties.title,sheets.properties" % args.id)
    print(json.dumps({"title": res["properties"]["title"],
                      "tabs": [{"title": s["properties"]["title"],
                                "rows": s["properties"]["gridProperties"].get("rowCount"),
                                "cols": s["properties"]["gridProperties"].get("columnCount")}
                               for s in res["sheets"]]}, indent=1))


def cmd_sheet(args):
    rng = urllib.parse.quote(args.range, safe="")
    res = api("https://sheets.googleapis.com/v4/spreadsheets/%s/values/%s" % (args.id, rng))
    print(json.dumps(res.get("values", []), indent=0))


DRIVE_LIST = ("https://www.googleapis.com/drive/v3/files?supportsAllDrives=true&includeItemsFromAllDrives=true"
              "&corpora=allDrives&pageSize=100&orderBy=modifiedTime%20desc"
              "&fields=files(id,name,mimeType,modifiedTime,createdTime,size,parents)&q=")
FOLDER_MIME = "application/vnd.google-apps.folder"


def cmd_drive_find(args):
    q = "name contains '%s' and trashed = false" % args.name.replace("'", "\\'")
    print(json.dumps(api(DRIVE_LIST + urllib.parse.quote(q)).get("files", []), indent=1))


def cmd_drive_ls(args):
    q = "'%s' in parents and trashed = false" % args.folder
    files = api(DRIVE_LIST + urllib.parse.quote(q)).get("files", [])
    if args.processed:
        # The CRM Drop loaders (NCBMW, SBMW, MCP) move each loaded file into the store folder's _processed
        # subfolder, so a direct-children listing misses what Drew dropped. Recent files only; "[temp] " names
        # are the loaders' own scratch copies, never a drop. _needs a look is never listed.
        for f in files:
            f["in"] = "drop folder"
        sub = [f for f in files if f["name"] == "_processed" and f["mimeType"] == FOLDER_MIME]
        if not sub:
            print("note: no _processed subfolder in %s" % args.folder, file=sys.stderr)
        else:
            since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.days)).strftime("%Y-%m-%dT%H:%M:%S")
            q = ("'%s' in parents and trashed = false and (modifiedTime > '%s' or createdTime > '%s')"
                 % (sub[0]["id"], since, since))
            for f in api(DRIVE_LIST + urllib.parse.quote(q)).get("files", []):
                if not f["name"].startswith("[temp] "):
                    f["in"] = "_processed"
                    files.append(f)
    print(json.dumps(files, indent=1))


def cmd_drive_get(args):
    meta = api("https://www.googleapis.com/drive/v3/files/%s?supportsAllDrives=true&fields=name,mimeType" % args.id)
    if meta["mimeType"] == "application/vnd.google-apps.spreadsheet":
        mime = urllib.parse.quote("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        data = api("https://www.googleapis.com/drive/v3/files/%s/export?mimeType=%s" % (args.id, mime), raw=True)
    else:
        data = api("https://www.googleapis.com/drive/v3/files/%s?alt=media&supportsAllDrives=true" % args.id, raw=True)
    out = os.path.expanduser(args.out)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "wb") as f:
        f.write(data)
    print(json.dumps({"name": meta["name"], "mimeType": meta["mimeType"], "saved": out, "bytes": len(data)}))


# ---------------------------------------------------------------- Gmail (CRM report emails)

GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me/"


def _hdr(headers, name):
    for h in headers or []:
        if h.get("name", "").lower() == name.lower():
            return h.get("value")
    return None


def _walk_parts(part, out):
    if not part:
        return
    fn = part.get("filename")
    body = part.get("body", {})
    if fn and body.get("attachmentId"):
        out["attachments"].append({"filename": fn, "mimeType": part.get("mimeType"),
                                   "size": body.get("size"), "attachmentId": body["attachmentId"]})
    elif part.get("mimeType") == "text/plain" and body.get("data") and not out.get("text"):
        out["text"] = base64.urlsafe_b64decode(body["data"] + "==").decode("utf-8", "replace")
    for sub in part.get("parts", []) or []:
        _walk_parts(sub, out)


def cmd_mail_ls(args):
    if args.any_label and not args.query:
        die("--any-label needs --query, so the search stays on report senders")
    # --any-label drops the Morning_CRM label so senders the filter does not catch (BMW NA,
    # Constellation for NCBMW) can be found; without it an extra --query only narrows the label.
    q = ("newer_than:%dd" % args.days) if args.any_label else ("label:%s newer_than:%dd" % (CRM_LABEL, args.days))
    if args.query:
        q += " (%s)" % args.query
    res = api(GMAIL + "messages?maxResults=100&q=" + urllib.parse.quote(q))
    out = []
    for m in res.get("messages", []):
        full = api(GMAIL + "messages/%s?format=full" % m["id"])
        h = full.get("payload", {}).get("headers", [])
        info = {"id": full["id"], "date": _hdr(h, "Date"), "from": _hdr(h, "From"),
                "subject": _hdr(h, "Subject"), "attachments": [], "text": None}
        _walk_parts(full.get("payload"), info)
        info["attachments"] = [{k: v for k, v in a.items() if k != "attachmentId"} for a in info["attachments"]]
        info["text_preview"] = (info.pop("text") or "")[:200].replace("\n", " ")
        out.append(info)
    print(json.dumps(out, indent=1))


def cmd_mail_get(args):
    full = api(GMAIL + "messages/%s?format=full" % args.id)
    h = full.get("payload", {}).get("headers", [])
    info = {"id": full["id"], "date": _hdr(h, "Date"), "from": _hdr(h, "From"),
            "subject": _hdr(h, "Subject"), "attachments": [], "text": None}
    _walk_parts(full.get("payload"), info)
    out_dir = os.path.expanduser(args.out)
    os.makedirs(out_dir, exist_ok=True)
    saved = []
    for a in info["attachments"]:
        blob = api(GMAIL + "messages/%s/attachments/%s" % (args.id, a["attachmentId"]))
        data = base64.urlsafe_b64decode(blob["data"] + "==")
        safe = os.path.basename(a["filename"]).replace(" ", "_")
        path = os.path.join(out_dir, safe)
        with open(path, "wb") as f:
            f.write(data)
        saved.append({"file": path, "bytes": len(data), "mimeType": a["mimeType"]})
    if info["text"]:
        path = os.path.join(out_dir, "body_%s.txt" % args.id)
        with open(path, "w") as f:
            f.write(info["text"])
        saved.append({"file": path, "bytes": len(info["text"]), "mimeType": "text/plain"})
    print(json.dumps({"id": info["id"], "date": info["date"], "from": info["from"],
                      "subject": info["subject"], "saved": saved}, indent=1))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("auth")
    a.add_argument("--gsc", action="store_true",
                   help="also ask for Search Console (webmasters.readonly); replaces the saved token")
    a.set_defaults(fn=cmd_auth)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    g = sub.add_parser("ga4")
    g.add_argument("--store", required=True)
    g.add_argument("--start", required=True)
    g.add_argument("--end", required=True)
    g.add_argument("--dims", required=True)
    g.add_argument("--metrics", required=True)
    g.add_argument("--limit", type=int, default=200)
    g.set_defaults(fn=cmd_ga4)
    n = sub.add_parser("ga4-nightly")
    n.add_argument("--date")
    n.add_argument("--out", required=True)
    n.set_defaults(fn=cmd_ga4_nightly)
    sub.add_parser("gsc-sites").set_defaults(fn=cmd_gsc_sites)
    n = sub.add_parser("gsc-nightly")
    n.add_argument("--date")
    n.add_argument("--out", required=True)
    n.set_defaults(fn=cmd_gsc_nightly)
    s = sub.add_parser("sheet-tabs")
    s.add_argument("--id", required=True)
    s.set_defaults(fn=cmd_sheet_tabs)
    s = sub.add_parser("sheet")
    s.add_argument("--id", required=True)
    s.add_argument("--range", required=True)
    s.set_defaults(fn=cmd_sheet)
    s = sub.add_parser("drive-find")
    s.add_argument("--name", required=True)
    s.set_defaults(fn=cmd_drive_find)
    s = sub.add_parser("drive-ls")
    s.add_argument("--folder", required=True)
    s.add_argument("--processed", action="store_true",
                   help="also list the folder's _processed subfolder (files modified or created in the last --days)")
    s.add_argument("--days", type=int, default=3, help="with --processed: how far back (default 3; Monday 4)")
    s.set_defaults(fn=cmd_drive_ls)
    s = sub.add_parser("drive-get")
    s.add_argument("--id", required=True)
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_drive_get)
    s = sub.add_parser("mail-ls")
    s.add_argument("--days", type=int, default=3)
    s.add_argument("--query", help="extra Gmail search terms, e.g. from:drive.sterlingbmw.com")
    s.add_argument("--any-label", action="store_true",
                   help="search all mail, not just the Morning_CRM label (needs --query)")
    s.set_defaults(fn=cmd_mail_ls)
    s = sub.add_parser("mail-get")
    s.add_argument("--id", required=True)
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_mail_get)
    args = p.parse_args()
    try:
        args.fn(args)
    except RuntimeError as e:
        die(str(e))


if __name__ == "__main__":
    main()
