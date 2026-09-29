#!/usr/bin/env python3
"""Who changed what: a per-store digest of Google Ads and Meta account changes since the last shift.
Standard library only. Read only (one Sheets read per Ads export when no local copy exists).

  C = python3 .claude/skills/ai-team/scripts/changes.py
  C --date D                  digest for the shift folder outputs/ai-team/D/
  C --date D --since ISO      start the window here instead of the previous shift's start
  C --date D --until ISO      end the window here instead of this shift's start
  C --date D --out DIR        write the digest (and any pulled raw file) to DIR instead of D/data/
  C --date D --no-pull        use saved files only, never read the Sheet
  C --date D --refresh        read the Sheet even when a saved copy is on disk
  C --date D --stores MCP,NOI only these stores
  C selftest                  offline checks in a temp folder, touches nothing real

Window. From the previous shift folder's start (the first "Start:" or "Tip-off:" time in its
shift-log.md, else 01:00 that day) up to this shift's start (same rule). Monday's previous shift is
Friday's, so the weekend is inside the window. No shift folder in the last 7 days: 48 hours back
(on a Monday, Friday 01:00). Per Google Ads store the window opens a little earlier when the
previous shift's export ran before that shift started (its export last_run): changes made between
the export and the tip-off were invisible to that shift, so they belong to tonight. Rows at or after
the window end are left for the next shift, so each change shows up on exactly one night.

Google Ads source. The export Sheet's change_events_14d tab (ads_export_v2.gs: newest 200 changes in
the last 14 days, times in the account time zone). A saved copy in the output folder or in
D/data/ ({STORE}_change_events_14d.txt, ads-dump style header line plus JSON rows) is used first;
otherwise the tab and the meta tab are read through gdata.py's token and the raw rows are saved as
{STORE}_change_events_14d.txt next to the digest, so nobody re-pulls. The Sheet ids come from
references/data-sources.md (same table ledgers.py ads-dump reads).

Meta source. Whatever Luka (or Magic's fallback) saved in D/data/: meta_*activity*.json (the raw
ads_account_get_activity_logs response, exactly as returned, is best) or meta_*activity*.md (a table
with Date/time, Actor, Event, Object, Detail). No such file: the digest says "no Meta activity file"
and quotes any activity summary line found inside meta_*.json. Stores come from campaign names and
from the id and store fields in meta_*.json; account-wide events (billing, image library) and
campaigns whose name names no store go to changes_ACCOUNT.md. The Meta account id is never written.

Actors, one class per change, fixed wording (never paraphrase these in a finding):
  drew                  Drew, by hand (user_email drewmoon@digitalcliq.com, or Meta "Drew C Moon")
  drew_recommendation   Drew applied a Google recommendation (client type GOOGLE_ADS_RECOMMENDATIONS
                        with Drew's email): a person clicked Apply. NOT auto-apply.
  auto_apply            Google auto-apply (GOOGLE_ADS_RECOMMENDATIONS_SUBSCRIPTION or the user
                        "Recommendations Auto-Apply"): nobody clicked anything. NOT Drew.
  person_recommendation another named person applied a recommendation (email printed)
  person                another named person (email or Meta name printed)
  script                a Google Ads script (GOOGLE_ADS_SCRIPTS; the email it runs as is printed)
  automated_rule        an automated rule (Google Ads GOOGLE_ADS_AUTOMATED_RULE, Meta rules)
  google_internal       Google internal tool with no person attached
  meta_system           Meta's own system (delivery starts, review results, auto audiences, billing)
  unknown               the log does not say who

Writes (to D/data/ or --out):
  changes_{STORE}.md    for SBMW, NCBMW, NOI, MCP, ATLAS (plus CHC and ACCOUNT when Meta has any):
                        store, then platform, then actor, then time; identical rows within 10
                        minutes collapse to one line with a count; older rows from the same export
                        summarized under "Earlier" (context, already covered by earlier shifts)
  changes.json          window, sources, every in-window change as its own row, per-actor counts,
                        the earlier summary, and coverage notes (stale, truncated, missing)
  {STORE}_change_events_14d.txt  raw rows, only when this run read the Sheet
Prints a short summary. Exit 0, or 2 when an Ads export store had no readable change data
(the files are still written and say which), 1 on a usage error.
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.parse

try:
    from zoneinfo import ZoneInfo
    PT = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover
    PT = None

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
EMDASH, ENDASH = chr(8212), chr(8211)  # written as chr() so this file never holds one

STORES = ("SBMW", "NCBMW", "NOI", "MCP", "ATLAS")
EXTRA_BUCKETS = ("CHC", "ACCOUNT")
DREW_EMAILS = {"drewmoon@digitalcliq.com"}
DREW_META_NAME = re.compile(r"^drew(\s+c\.?)?(\s+moon)?$", re.I)
EXPORT_LIMIT = 200          # ads_export_v2.gs: ORDER BY change_date_time DESC LIMIT 200
STALE_HOURS = 26
FALLBACK_HOURS = 48
PREV_SHIFT_MAX_DAYS = 7
COLLAPSE_GAP_S = 600
EARLIER_MAX_LINES = 12

ACTORS = [
    ("drew", "Drew, by hand",
     "Drew made these himself. Not Google, not auto-apply."),
    ("drew_recommendation", "Drew applied a Google recommendation",
     "Drew clicked Apply on a Google recommendation: a person decided. This is NOT auto-apply."),
    ("auto_apply", "Google auto-apply",
     "Google's Recommendations Auto-Apply subscription made these. Nobody clicked anything. This is NOT Drew."),
    ("person_recommendation", "Another person applied a Google recommendation",
     "A named person (not Drew) clicked Apply on a Google recommendation. Name them exactly."),
    ("person", "Another person",
     "A named person, not Drew, made these. Name them exactly."),
    ("script", "A Google Ads script",
     "A script made these, running as the email shown. The team's export script only reads, so this is another script."),
    ("automated_rule", "An automated rule",
     "An automated rule in the account made these, not a person at the time."),
    ("google_internal", "Google internal tool, no person recorded",
     "Google's own systems logged these with no person attached."),
    ("meta_system", "Meta, automatic",
     "Meta's own system: delivery starts, review results, auto-built audiences, billing. Not a person."),
    ("unknown", "Unknown actor",
     "The log does not say who. Write 'unknown', never guess."),
]
ACTOR_ORDER = [a[0] for a in ACTORS]
ACTOR_LABEL = {a[0]: a[1] for a in ACTORS}
ACTOR_MEANS = {a[0]: a[2] for a in ACTORS}

SURFACE = {
    "GOOGLE_ADS_WEB_CLIENT": "Google Ads website",
    "GOOGLE_ADS_MOBILE_APP": "Google Ads phone app",
    "GOOGLE_ADS_EDITOR": "Google Ads Editor",
    "GOOGLE_ADS_BULK_UPLOAD": "bulk upload",
    "GOOGLE_ADS_API": "Google Ads API",
    "GOOGLE_ADS_RECOMMENDATIONS": "Recommendations page",
    "GOOGLE_ADS_RECOMMENDATIONS_SUBSCRIPTION": "auto-apply subscription",
    "GOOGLE_ADS_SCRIPTS": "script",
    "GOOGLE_ADS_AUTOMATED_RULE": "automated rule",
    "AUTOMATED_RULE": "automated rule",
    "SEARCH_ADS_360_SYNC": "Search Ads 360 sync",
    "SEARCH_ADS_360_POST": "Search Ads 360",
    "INTERNAL_TOOL": "Google internal tool",
}
RESOURCE = {
    "CAMPAIGN": "campaign setting",
    "CAMPAIGN_BUDGET": "budget",
    "AD_GROUP": "ad group",
    "AD_GROUP_AD": "ad",
    "AD": "ad text",
    "AD_GROUP_CRITERION": "ad group targeting",
    "CAMPAIGN_CRITERION": "campaign targeting",
    "AD_GROUP_BID_MODIFIER": "bid adjustment",
    "ASSET": "asset",
    "CUSTOMER_ASSET": "account-level asset",
    "CAMPAIGN_ASSET": "campaign asset",
    "AD_GROUP_ASSET": "ad group asset",
    "ASSET_SET": "asset set",
    "ASSET_SET_ASSET": "asset set item",
    "CAMPAIGN_ASSET_SET": "campaign asset set",
    "FEED": "feed",
    "FEED_ITEM": "feed item",
    "CAMPAIGN_FEED": "campaign feed",
    "AD_GROUP_FEED": "ad group feed",
}
FIELD_WORDS = {
    "status": "status (on, paused, removed)",
    "amountMicros": "daily budget amount",
    "totalAmountMicros": "total budget amount",
    "geoTargetTypeSetting.positiveGeoTargetType": "location option (presence or interest)",
    "geoTargetTypeSetting.negativeGeoTargetType": "excluded-location option",
    "networkSettings.targetContentNetwork": "Display Network on or off",
    "networkSettings.targetSearchNetwork": "search partners on or off",
    "networkSettings.targetGoogleSearch": "Google Search on or off",
    "manualCpc.enhancedCpcEnabled": "Enhanced CPC",
    "maximizeConversions.targetCpaMicros": "target CPA",
    "maximizeConversionValue.targetRoas": "target ROAS",
    "targetSpend.cpcBidCeilingMicros": "max CPC bid limit",
    "biddingStrategyType": "bid strategy",
    "assetAutomationSettings": "automatically created assets setting",
    "aiMaxSetting.enableAiMax": "AI Max",
    "responsiveSearchAd.headlines": "RSA headlines",
    "responsiveSearchAd.descriptions": "RSA descriptions",
    "responsiveSearchAd.path1": "display path",
    "responsiveSearchAd.path2": "display path",
    "addedByGoogleAds": "added-by-Google flag",
    "cpcBidMicros": "keyword bid",
    "finalUrls": "final URLs",
    "textAsset.text": "text",
    "calloutAsset.calloutText": "callout text",
    "sitelinkAsset.linkText": "sitelink text",
    "sitelinkAsset.description1": "sitelink description",
    "sitelinkAsset.description2": "sitelink description",
    "fieldType": "asset type",
    "keyword.text": "keyword text",
    "keyword.matchType": "match type",
    "negative": "negative flag",
    "brandList.sharedSet": "brand list",
    "startDate": "start date",
    "endDate": "end date",
    "name": "name",
}
ID_FIELDS = {"id", "resourceName", "criterionId", "campaign", "adGroup", "asset", "ad"}

META_STORE_PATTERNS = [
    ("NCBMW", r"\bncbmw\b|new century|\bcentury\b"),
    ("SBMW", r"\bsbmw\b|sterling"),
    ("NOI", r"\bnoi\b|nissan|irvine"),
    ("MCP", r"\bmcp\b|mcpeek|\bcdjr\b|\bdodge\b|\bjeep\b|\bram\b|chrysler"),
    ("ATLAS", r"\batlas\b"),
    ("CHC", r"\bchc\b|covina|chevrolet|\bchevy\b"),
]
META_ACCOUNT_NAME = re.compile(r"^\(?MAIN\)?\s*\d{6,}$|^\d{9,}$", re.I)
META_ACCOUNT_EVENTS = re.compile(r"billed|images? (added|edited)|payment method|account (spending|status)|"
                                 r"user (added|removed)", re.I)
META_ACCOUNT_OBJECTS = ("account", "ad account", "the account", "account library")


# ---------------------------------------------------------------- small helpers

def die(msg, code=1):
    print("changes.py: " + msg, file=sys.stderr)
    sys.exit(code)


def clean(s):
    """No em or en dashes in anything this script writes; collapse whitespace."""
    s = "" if s is None else str(s)
    s = s.replace(EMDASH, "-").replace(ENDASH, "-").replace("\u202f", " ").replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", s).strip()


def iso_date(s):
    try:
        return dt.date.fromisoformat(s)
    except (TypeError, ValueError):
        die("bad date %r, use YYYY-MM-DD" % s)


def local(d):
    """Aware datetime in Pacific time (naive input is taken as Pacific)."""
    if d.tzinfo is None:
        return d.replace(tzinfo=PT)
    return d.astimezone(PT)


def at(day, h=1, m=0, s=0):
    return dt.datetime(day.year, day.month, day.day, h, m, s, tzinfo=PT)


def fmt_time(d, seconds=True):
    d = local(d)
    h12 = d.hour % 12 or 12
    t = "%d:%02d:%02d" % (h12, d.minute, d.second) if seconds else "%d:%02d" % (h12, d.minute)
    return "%s %d/%d %s%s" % (d.strftime("%a"), d.month, d.day, t, "am" if d.hour < 12 else "pm")


def fmt_clock(d):
    d = local(d)
    h12 = d.hour % 12 or 12
    return "%d:%02d:%02d%s" % (h12, d.minute, d.second, "am" if d.hour < 12 else "pm")


def fmt_span(a, b):
    if b is None or a == b:
        return fmt_time(a)
    if local(a).date() == local(b).date():
        return "%s to %s" % (fmt_time(a), fmt_clock(b))
    return "%s to %s" % (fmt_time(a), fmt_time(b))


def parse_any_time(s, tz=None):
    """Parse the time formats seen in exports, shift logs and Meta logs. Returns aware or None."""
    if s is None:
        return None
    s = clean(s).replace(" at ", " ").replace("~", "")
    if not s:
        return None
    zone = tz or PT
    iso = s.replace("Z", "+00:00")
    iso = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", iso)
    try:
        d = dt.datetime.fromisoformat(iso)
        return d.astimezone(PT) if d.tzinfo else d.replace(tzinfo=zone).astimezone(PT)
    except ValueError:
        pass
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%Y %I:%M %p", "%m/%d/%Y %I:%M:%S %p",
              "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%Y-%m-%d %I:%M %p", "%Y-%m-%d %I:%M:%S %p"):
        try:
            return dt.datetime.strptime(s, f).replace(tzinfo=zone).astimezone(PT)
        except ValueError:
            continue
    # "2026-09-18 07:46-08:01 AM" (a range written by hand): the first time, with the AM/PM at the end
    m = re.match(r"(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?(?:\s*-\s*\d{1,2}:\d{2})?\s*(AM|PM)?", s, re.I)
    if m:
        h = int(m.group(2))
        ap = (m.group(5) or "").upper()
        if ap == "PM" and h < 12:
            h += 12
        if ap == "AM" and h == 12:
            h = 0
        y, mo, da = (int(x) for x in m.group(1).split("-"))
        return dt.datetime(y, mo, da, h, int(m.group(3)), int(m.group(4) or 0), tzinfo=zone).astimezone(PT)
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?", s, re.I)
    if m:
        h = int(m.group(4))
        ap = (m.group(7) or "").upper()
        if ap == "PM" and h < 12:
            h += 12
        if ap == "AM" and h == 12:
            h = 0
        return dt.datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)), h, int(m.group(5)),
                           int(m.group(6) or 0), tzinfo=zone).astimezone(PT)
    return None


def rel(root, p):
    """Vault-relative path for files inside the vault, absolute otherwise."""
    try:
        r = os.path.relpath(p, root)
    except ValueError:
        return p
    return os.path.abspath(p) if r.startswith("..") else r


def write_text(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(clean_block(text))


def clean_block(text):
    return text.replace(EMDASH, "-").replace(ENDASH, "-")


# ---------------------------------------------------------------- the shift window

START_WORDS = re.compile(r"\bstart|tip-?off|started_at|began", re.I)
ISO_DT = re.compile(r"(\d{4}-\d{2}-\d{2})[T ](\d{1,2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?\s*(Z|[+-]\d{2}:?\d{2})?")
CLOCK = re.compile(r"(?<![\d:.])(\d{1,2}):(\d{2})(?::(\d{2}))?(?![\d:])\s*(am|pm)?", re.I)


def parse_shift_start(text, day):
    """First start or tip-off time in a shift log. ISO timestamps win; a bare HH:MM is on the folder's day."""
    for line in text.splitlines()[:80]:
        if not START_WORDS.search(line):
            continue
        m = ISO_DT.search(line)
        if m:
            stamp = "%sT%02d:%s:%s" % (m.group(1), int(m.group(2)), m.group(3), m.group(4) or "00")
            if m.group(5):
                stamp += m.group(5)
            got = parse_any_time(stamp)
            if got:
                return got
        m = CLOCK.search(line)
        if m:
            h = int(m.group(1))
            ap = (m.group(4) or "").lower()
            if ap == "pm" and h < 12:
                h += 12
            if ap == "am" and h == 12:
                h = 0
            if h > 23 or int(m.group(2)) > 59:
                continue
            return at(day, h, int(m.group(2)), int(m.group(3) or 0))
    return None


def shift_folders(root):
    base = os.path.join(root, "outputs", "ai-team")
    out = []
    for p in glob.glob(os.path.join(base, "????-??-??")):
        name = os.path.basename(p)
        try:
            d = dt.date.fromisoformat(name)
        except ValueError:
            continue
        if os.path.exists(os.path.join(p, "shift-log.md")) or os.path.exists(os.path.join(p, "brief.md")):
            out.append((d, p))
    return sorted(out)


def shift_start(root, day):
    p = os.path.join(root, "outputs", "ai-team", day.isoformat(), "shift-log.md")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return parse_shift_start(f.read(), day)
    except OSError:
        return None


def find_window(root, day, since_arg=None, until_arg=None):
    w = {"notes": []}
    if until_arg:
        until = parse_any_time(until_arg)
        if not until:
            die("bad --until %r" % until_arg)
        w["until_basis"] = "--until"
    else:
        until = shift_start(root, day)
        if until:
            w["until_basis"] = "this shift's start in %s/shift-log.md" % day.isoformat()
        else:
            until = at(day)
            w["until_basis"] = "01:00 on %s (no start time in this shift's log yet)" % day.isoformat()
    w["until"] = until
    w["prev_shift"] = None
    if since_arg:
        since = parse_any_time(since_arg if re.search(r"\d:\d", since_arg) else since_arg + "T00:00")
        if not since:
            die("bad --since %r" % since_arg)
        w["since_basis"] = "--since"
    else:
        prev = [(d, p) for d, p in shift_folders(root)
                if d < day and (day - d).days <= PREV_SHIFT_MAX_DAYS]
        if prev:
            pd, _pp = prev[-1]
            w["prev_shift"] = pd.isoformat()
            since = shift_start(root, pd)
            if since:
                w["since_basis"] = "the %s shift's start (its shift-log.md)" % pd.isoformat()
            else:
                since = at(pd)
                w["since_basis"] = "01:00 on %s (the previous shift; no start time in its log)" % pd.isoformat()
        elif day.weekday() == 0:
            since = at(day - dt.timedelta(days=3))
            w["since_basis"] = "Friday 01:00 (Monday, no shift folder found in the last %d days)" % PREV_SHIFT_MAX_DAYS
        else:
            since = until - dt.timedelta(hours=FALLBACK_HOURS)
            w["since_basis"] = "%d hours back (no shift folder found in the last %d days)" % (
                FALLBACK_HOURS, PREV_SHIFT_MAX_DAYS)
    w["since"] = since
    if since >= until:
        die("window is empty: since %s is not before until %s" % (since.isoformat(), until.isoformat()))
    if local(since).weekday() >= 4 and (until - since).days >= 2:
        w["notes"].append("weekend inside the window")
    return w


# ---------------------------------------------------------------- Google Ads rows

def ads_sheet_ids(root):
    p = os.path.join(root, ".claude", "skills", "ai-team", "references", "data-sources.md")
    try:
        with open(p, encoding="utf-8") as f:
            ref = f.read()
    except OSError:
        return {}
    return dict(re.findall(r"^\|\s*([A-Z]+)\s*\|\s*[\d-]{8,}\s*\|\s*`([A-Za-z0-9_-]{20,})`", ref, re.M))


def classify_ads(email, client_type):
    """(actor class, surface) for one change_event row. Order matters: the client type decides
    auto-apply, recommendation, script and rule before the email does."""
    e = clean(email)
    el = e.lower()
    ct = clean(client_type).upper()
    surface = SURFACE.get(ct, ct.lower().replace("_", " ") if ct else "tool not recorded")
    is_drew = el in DREW_EMAILS
    if ct == "GOOGLE_ADS_RECOMMENDATIONS_SUBSCRIPTION" or "auto-apply" in el or "auto apply" in el:
        return "auto_apply", surface
    if ct == "GOOGLE_ADS_RECOMMENDATIONS":
        if is_drew:
            return "drew_recommendation", surface
        if "@" in e:
            return "person_recommendation", surface
        return "unknown", "Recommendations page, no person recorded"
    if ct == "GOOGLE_ADS_SCRIPTS":
        return "script", surface
    if ct in ("GOOGLE_ADS_AUTOMATED_RULE", "AUTOMATED_RULE"):
        return "automated_rule", surface
    if is_drew:
        if ct == "INTERNAL_TOOL":
            return "drew", "Google internal tool under Drew's login (asset records logged while he edited)"
        return "drew", surface
    if ct == "INTERNAL_TOOL" and ("@" not in e or el.endswith("@google.com")):
        return "google_internal", surface
    if "@" in e:
        return "person", surface
    if ct == "INTERNAL_TOOL":
        return "google_internal", surface
    return "unknown", surface


def describe_ads(rtype, op, fields):
    """Plain words for one row: (thing, verb, [field words])."""
    f = [x for x in fields if x]
    fs = set(f)
    kw = "keyword.text" in fs
    thing = RESOURCE.get(rtype, rtype.lower().replace("_", " ") if rtype else "unknown resource")
    if rtype == "CAMPAIGN_CRITERION":
        if "brandList.sharedSet" in fs:
            thing = "brand list exclusion"
        elif kw:
            thing = "campaign negative keyword"
        elif any(x.startswith("location") or x.startswith("proximity") for x in fs):
            thing = "location target"
        elif "negative" in fs:
            thing = "campaign exclusion (kind not in the export)"
    elif rtype == "AD_GROUP_CRITERION":
        if kw:
            thing = "negative keyword" if ("negative" in fs and op == "CREATE") else "keyword"
        elif fs == {"status"}:
            thing = "keyword or ad group target"
    elif rtype == "ASSET" and "textAsset.text" in fs and op == "CREATE":
        thing = "text asset"
    verb = {"CREATE": "added", "UPDATE": "changed", "REMOVE": "removed"}.get(op, (op or "changed").lower())
    words = []
    if op == "UPDATE":
        for x in f:
            if x in ID_FIELDS:
                continue
            w = FIELD_WORDS.get(x, x)
            if w not in words:
                words.append(w)
    return thing, verb, words


def col_index(header):
    want = {"time": "changedatetime", "email": "useremail", "client": "clienttype",
            "rtype": "changeresourcetype", "op": "resourcechangeoperation", "fields": "changedfields",
            "campaign": "campaignname"}
    norm = [re.sub(r"[^a-z]", "", str(h).lower()) for h in header]
    idx = {}
    for key, token in want.items():
        idx[key] = next((i for i, h in enumerate(norm) if h.endswith(token) or token in h), None)
    defaults = {"time": 0, "email": 1, "client": 2, "rtype": 3, "op": 4, "fields": 5, "campaign": 6}
    for k, v in defaults.items():
        if idx[k] is None:
            idx[k] = v
    return idx


def parse_change_file(text):
    """Saved change_events file: optional '=== ... ===' header line, then JSON rows (a list, or a
    dict with rows/values). Returns (rows, header info)."""
    info = {}
    body = text
    first = text.split("\n", 1)[0]
    if first.startswith("==="):
        body = text.split("\n", 1)[1] if "\n" in text else ""
        m = re.search(r"export last_run ([0-9][0-9:\- T/]+[0-9])", first)
        if m:
            info["last_run"] = m.group(1).strip()
        m = re.search(r"account_timezone ([A-Za-z_]+/[A-Za-z_]+)", first)
        if m:
            info["account_timezone"] = m.group(1)
        m = re.search(r"saved by ([^,]+?) (\d{4}-\d{2}-\d{2}T[\d:]+(?:[+-]\d{2}:\d{2})?)", first)
        if m:
            info["saved_by"], info["saved_at"] = m.group(1), m.group(2)
    data = json.loads(body) if body.strip() else []
    if isinstance(data, dict):
        info.setdefault("last_run", data.get("last_run"))
        data = data.get("rows") or data.get("values") or []
    return data, info


def meta_tab_info(rows):
    kv = {}
    for r in rows or []:
        if r and len(r) >= 2:
            kv[str(r[0]).strip()] = str(r[1]).strip()
    return {"last_run": kv.get("last_run"), "account_timezone": kv.get("account_timezone")}


def local_meta_tab(dirs, store):
    """last_run and timezone from a saved meta tab (health.py writes {STORE}_ads_meta.json)."""
    for d in dirs:
        p = os.path.join(d, "%s_ads_meta.json" % store)
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return meta_tab_info(json.load(f).get("rows")), p
            except (OSError, ValueError, AttributeError):
                continue
    return {}, None


def gdata_fetch(sheet_id, rng):
    sys.path.insert(0, HERE)
    import gdata  # noqa: E402  (same folder, read-only Sheets scope)
    url = "https://sheets.googleapis.com/v4/spreadsheets/%s/values/%s" % (sheet_id, urllib.parse.quote(rng, safe=""))
    return gdata.api(url).get("values", [])


def load_ads_store(ctx, store, sheet_id):
    """Rows for one store: saved copy first, else the Sheet (then saved). Never guesses."""
    src = {"store": store, "sheet": True, "status": "ok", "notes": []}
    dirs = ctx["dirs"]
    name = "%s_change_events_14d" % store
    local_path = None
    if not ctx["refresh"]:
        for d in dirs:
            for ext in (".txt", ".json"):
                p = os.path.join(d, name + ext)
                if os.path.exists(p):
                    local_path = p
                    break
            if local_path:
                break
    rows, info = None, {}
    if local_path:
        try:
            with open(local_path, encoding="utf-8") as f:
                rows, info = parse_change_file(f.read())
            src["file"] = rel(ctx["root"], local_path)
            src["pulled"] = False
        except (OSError, ValueError) as e:
            src["notes"].append("saved copy %s unreadable: %s" % (rel(ctx["root"], local_path), e))
            rows = None
    if rows is None and ctx["pull"]:
        try:
            meta_rows = ctx["fetch"](sheet_id, "meta!A1:F60")
            rows = ctx["fetch"](sheet_id, "change_events_14d!A1:G300")
            info = meta_tab_info(meta_rows)
            stamp = dt.datetime.now(PT).isoformat(timespec="seconds")
            head = "=== %s change_events_14d, saved by changes.py %s, export last_run %s, account_timezone %s ===\n" % (
                store, stamp, info.get("last_run"), info.get("account_timezone"))
            out = os.path.join(ctx["out"], name + ".txt")
            write_text(out, head + json.dumps(rows, indent=0) + "\n")
            src["file"] = rel(ctx["root"], out)
            src["pulled"] = True
            src["pulled_at"] = stamp
        except BaseException as e:  # gdata.die raises SystemExit; never let one store end the run
            msg = " ".join(str(e).split())[:200] if str(e) else type(e).__name__
            src["status"] = "failed"
            src["notes"].append("Sheet read failed: %s" % msg)
            rows = None
    if rows is None:
        if src["status"] != "failed":
            src["status"] = "missing"
            src["notes"].append("no saved change_events_14d copy and --no-pull set")
        return src, []
    if not info.get("last_run") or not info.get("account_timezone"):
        extra, p = local_meta_tab(dirs, store)
        if extra.get("last_run") and not info.get("last_run"):
            info["last_run"] = extra["last_run"]
            src["notes"].append("export last_run taken from %s" % rel(ctx["root"], p))
        if extra.get("account_timezone") and not info.get("account_timezone"):
            info["account_timezone"] = extra["account_timezone"]
    tzname = info.get("account_timezone") or "America/Los_Angeles"
    try:
        tz = ZoneInfo(tzname)
    except Exception:
        tz = PT
        src["notes"].append("unknown account time zone %r, read as Pacific" % tzname)
    src["account_timezone"] = tzname
    lr = parse_any_time(info.get("last_run"), tz) if info.get("last_run") else None
    src["export_last_run"] = lr.isoformat() if lr else None
    changes = []
    if rows:
        idx = col_index(rows[0])
        for r in rows[1:]:
            if not r:
                continue

            def cell(k):
                i = idx[k]
                return clean(r[i]) if i is not None and i < len(r) else ""
            t = parse_any_time(cell("time"), tz)
            if not t:
                src["notes"].append("row with unreadable time skipped: %r" % cell("time"))
                continue
            email, client = cell("email"), cell("client")
            actor, surface = classify_ads(email, client)
            rtype, op = cell("rtype").upper(), cell("op").upper()
            fields = [x.strip() for x in cell("fields").split(",") if x.strip()]
            thing, verb, words = describe_ads(rtype, op, fields)
            changes.append({
                "platform": "google_ads", "store": store, "time": t.isoformat(), "time_local": fmt_time(t),
                "_t": t, "actor_class": actor, "actor_label": ACTOR_LABEL[actor], "actor_detail": email or None,
                "client_type": client or None, "surface": surface, "resource_type": rtype or None,
                "resource": thing, "operation": op or None, "changed_fields": fields, "changed_plain": words,
                "what": "%s %s%s" % (thing, verb, (": " + ", ".join(words)) if words else ""),
                "campaign": cell("campaign") or None,
            })
    changes.sort(key=lambda c: c["_t"])
    src["export_rows"] = len(changes)
    src["export_oldest"] = changes[0]["time"] if changes else None
    src["export_newest"] = changes[-1]["time"] if changes else None
    src["truncated"] = len(changes) >= EXPORT_LIMIT
    return src, changes


def prev_export_last_run(ctx, store):
    """When the previous shift's Ads export ran (the newest change that shift could see)."""
    prev = ctx["window"].get("prev_shift")
    if not prev:
        return None, None
    d = os.path.join(ctx["root"], "outputs", "ai-team", prev, "data")
    p = os.path.join(d, "changes.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                v = json.load(f)["stores"][store]["google_ads"].get("export_last_run")
            if v:
                return parse_any_time(v), rel(ctx["root"], p)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
    info, mp = local_meta_tab([d], store)
    if info.get("last_run"):
        return parse_any_time(info["last_run"]), rel(ctx["root"], mp)
    for name in ("%s_campaign_daily_30d.txt" % store, "%s_change_events_14d.txt" % store):
        q = os.path.join(d, name)
        if os.path.exists(q):
            try:
                with open(q, encoding="utf-8") as f:
                    m = re.search(r"export last_run ([0-9][0-9:\- T/]+[0-9])", f.readline())
                if m:
                    return parse_any_time(m.group(1)), rel(ctx["root"], q)
            except OSError:
                pass
    return None, None


# ---------------------------------------------------------------- Meta activity

def _json_loose(s):
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return None


EVENT_KEYS = ("event_type", "translated_event_type", "actor_name", "actor", "when", "event_time",
              "date_time_in_timezone", "datetime")


def find_event_lists(obj, depth=0):
    if depth > 6:
        return []
    if isinstance(obj, str):
        s = obj.strip()
        if s[:1] in "[{":
            return find_event_lists(_json_loose(s), depth + 1)
        return []
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj) and any(any(k in x for k in EVENT_KEYS) for x in obj):
            return [obj]
        out = []
        for x in obj:
            out += find_event_lists(x, depth + 1)
        return out
    if isinstance(obj, dict):
        out = []
        for v in obj.values():
            out += find_event_lists(v, depth + 1)
        return out
    return []


def money(v, currency="USD"):
    try:
        return "%s %.2f" % (currency, float(v) / 100.0)
    except (TypeError, ValueError):
        return None


def summarize_extra(extra):
    """old to new from Meta's extra_data, whitelisted: never image URLs, request ids or IPs."""
    x = extra if isinstance(extra, dict) else _json_loose(extra)
    if not isinstance(x, dict):
        return ""
    typ = x.get("type")
    nv, ov = x.get("new_value"), x.get("old_value")
    if typ == "targets_spec" and isinstance(nv, list):
        parts = []
        for item in nv[:4]:
            if isinstance(item, dict):
                label = clean(item.get("content", "")).rstrip(":")
                kids = item.get("children") or []
                val = clean(", ".join(str(k) for k in kids))
                if label.lower().startswith("placement"):
                    val = "%d placements" % (val.count(",") + 1) if val else ""
                parts.append("%s %s" % (label, val[:60]) if val else label)
        return "targeting: " + "; ".join(p for p in parts if p)
    if isinstance(nv, dict) and nv.get("type") == "payment_amount":
        amt = money(nv.get("new_value"), nv.get("currency", "USD"))
        extra_word = clean(nv.get("additional_value") or "")
        return ("budget %s %s" % (amt, extra_word)).strip() if amt else ""
    if typ == "payment_amount":
        a, b = money(ov, x.get("currency", "USD")), money(nv, x.get("currency", "USD"))
        return "%s to %s" % (a or "none", b or "none")
    if isinstance(nv, (str, int, float)) and not isinstance(nv, bool):
        if isinstance(ov, (str, int, float)) and ov not in ("", None):
            return "%s to %s" % (clean(ov), clean(nv))
        return clean(nv)
    return ""


def split_actor(actor):
    """'Drew C Moon (Power Editor)' -> ('Drew C Moon', 'Power Editor')."""
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", actor or "")
    if m:
        return clean(m.group(1)), clean(m.group(2))
    return clean(actor), ""


def classify_meta(name, actor_id, app, rule_info=None):
    n = clean(name)
    if rule_info or re.search(r"\brule", app or "", re.I) or re.search(r"\brule", n, re.I):
        return "automated_rule"
    if n.lower() in ("meta", "facebook", "meta platforms") or (str(actor_id or "") == "0" and not DREW_META_NAME.match(n)):
        return "meta_system"
    if not n:
        return "unknown"
    if DREW_META_NAME.match(n):
        return "drew"
    return "person"


def normalize_meta(ev):
    t = None
    for k in ("event_time", "date_time_in_timezone", "datetime", "when", "time", "date"):
        if ev.get(k):
            t = parse_any_time(ev.get(k))
            if t:
                break
    name = ev.get("actor_name")
    app = ev.get("application_name") or ""
    if name is None and ev.get("actor"):
        name, app2 = split_actor(ev.get("actor"))
        app = app or app2
    extra = ev.get("extra_data")
    xd = extra if isinstance(extra, dict) else (_json_loose(extra) if isinstance(extra, str) else None)
    rule = xd.get("rule_info") if isinstance(xd, dict) else None
    event = clean(ev.get("translated_event_type") or ev.get("event_type") or ev.get("event") or "")
    obj = clean(ev.get("object_name") or ev.get("object") or "")
    detail = summarize_extra(xd) if xd is not None else clean(ev.get("detail") or "")
    if not event and ev.get("what"):
        event = clean(ev.get("what"))
    cid = None
    if isinstance(xd, dict):
        c = xd.get("campaign_id")
        if isinstance(c, dict):
            c = c.get("new") or c.get("mutation_input")
        cid = str(c) if c else None
    return {"_t": t, "actor_name": clean(name), "actor_id": str(ev.get("actor_id") or ""), "app": clean(app),
            "event": event, "object": obj, "object_id": str(ev.get("object_id") or "") or None,
            "object_type": clean(ev.get("object_type") or ""), "detail": detail, "parent_id": cid,
            "rule": rule}


def parse_meta_md(text):
    """Markdown table: Date/time | Actor | Event | Object | Detail (first header row decides columns)."""
    out, cols = [], None
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            cols = None
            continue
        cells = [clean(c) for c in s.strip("|").split("|")]
        if cols is None:
            low = [c.lower() for c in cells]
            if any("actor" in c for c in low) and any("date" in c or "time" in c or "when" in c for c in low):
                cols = low
            continue
        if all(re.fullmatch(r":?-{2,}:?", c or "---") for c in cells):
            continue
        row = dict(zip(cols, cells))

        def pick(*keys):
            for k in cols:
                if any(w in k for w in keys):
                    return row.get(k, "")
            return ""
        obj = pick("object", "campaign", "name")
        if obj.lower() in ("same", "ditto", '"', "same as above", "as above") and out:
            obj = out[-1]["object"]
        out.append({"when": pick("date", "time", "when"), "actor": pick("actor", "who"),
                    "event": pick("event", "what", "change"), "object": obj,
                    "detail": pick("detail", "note")})
    return out


def meta_store_hints(ctx):
    """id and name to store, from every meta_*.json in tonight's and the last few shifts' data."""
    ids, names = {}, {}

    def walk(o, key=None, depth=0):
        if depth > 8:
            return
        if isinstance(o, dict):
            st = o.get("store")
            if isinstance(st, str) and st.upper() in STORES + ("CHC",):
                if o.get("id"):
                    ids[str(o["id"])] = st.upper()
                if o.get("name"):
                    names[clean(o["name"]).lower()] = st.upper()
                if key and not key.startswith("_"):
                    names[clean(key).lower()] = st.upper()
            for k, v in o.items():
                walk(v, k, depth + 1)
        elif isinstance(o, list):
            for v in o:
                walk(v, key, depth + 1)
    dirs = list(ctx["dirs"])
    for d, p in shift_folders(ctx["root"]):
        if d < ctx["day"] and (ctx["day"] - d).days <= 14:
            dirs.append(os.path.join(p, "data"))
    for d in dirs:
        for p in glob.glob(os.path.join(d, "meta_*.json")):
            try:
                with open(p, encoding="utf-8") as f:
                    walk(json.load(f))
            except (OSError, ValueError):
                continue
    return ids, names


def store_from_name(name):
    hits = [s for s, pat in META_STORE_PATTERNS if re.search(pat, name or "", re.I)]
    if len(hits) == 1:
        return hits[0]
    return None


def load_meta(ctx):
    """Meta events from files Luka saved. Returns (source info, normalized events)."""
    files = []
    for d in ctx["dirs"]:
        for pat in ("meta_*activity*.json", "meta_*activity*.md", "meta_activity*.json", "meta_activity*.md"):
            for p in glob.glob(os.path.join(d, pat)):
                if p not in files:
                    files.append(p)
    src = {"files": [], "status": "no_file", "notes": []}
    raw = []
    for p in sorted(files):
        try:
            with open(p, encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            src["notes"].append("%s unreadable: %s" % (rel(ctx["root"], p), e))
            continue
        evs = []
        if p.endswith(".md"):
            evs = parse_meta_md(text)
        else:
            data = _json_loose(text)
            for lst in find_event_lists(data):
                evs += lst
        src["files"].append({"file": rel(ctx["root"], p), "events": len(evs)})
        raw += evs
    if not files:
        summary = []
        for d in ctx["dirs"]:
            for p in sorted(glob.glob(os.path.join(d, "meta_*.json"))):
                data = _json_loose(open(p, encoding="utf-8").read()) if os.path.exists(p) else None

                def walk(o, depth=0):
                    if depth > 5 or not isinstance(o, dict):
                        return
                    for k, v in o.items():
                        if "activity" in k.lower():
                            txt = v if isinstance(v, str) else json.dumps(v)
                            summary.append("%s (%s): %s" % (rel(ctx["root"], p), k, clean(txt)[:300]))
                        elif isinstance(v, dict):
                            walk(v, depth + 1)
                walk(data)
        src["summary_lines"] = summary
        return src, []
    src["status"] = "ok"
    events, seen, bad = [], set(), 0
    for ev in raw:
        n = normalize_meta(ev)
        if not n["_t"]:
            bad += 1
            continue
        key = (n["_t"].isoformat(), n["actor_name"], n["event"], n["object"])
        if key in seen:
            continue
        seen.add(key)
        events.append(n)
    if bad:
        src["notes"].append("%d Meta events with no readable time skipped" % bad)
    events.sort(key=lambda e: e["_t"])
    # Stores: saved campaign ids and names first, then names, then parents, then create-with inference.
    ids, names = meta_store_hints(ctx)
    obj_store = {k: (v, "saved campaign id") for k, v in ids.items()}
    name_store = {}

    def remember(e):
        if e.get("store") and e["store"] != "ACCOUNT":
            carried = e["store_basis"] if e["store_basis"].startswith("inferred") else "same object as an earlier event"
            if e["object_id"]:
                obj_store.setdefault(e["object_id"], (e["store"], carried))
            if e["object"]:
                name_store.setdefault(e["object"].lower(), (e["store"], carried))

    for e in events:
        obj_low = (e["object"] or "").lower()
        if (META_ACCOUNT_NAME.match(e["object"] or "") or obj_low in META_ACCOUNT_OBJECTS
                or (not store_from_name(e["object"] or e["event"]) and META_ACCOUNT_EVENTS.search(e["event"]))):
            e["store"], e["store_basis"] = "ACCOUNT", "account-wide"
            e["object"], e["object_id"] = "the DigitalCLIQ Meta account", None
            continue
        st = None
        basis = ""
        if e["object_id"] and e["object_id"] in obj_store:
            st, basis = obj_store[e["object_id"]]
        elif obj_low in names:
            st, basis = names[obj_low], "saved campaign name"
        elif store_from_name(e["object"]):
            st, basis = store_from_name(e["object"]), "name"
        elif not e["object"] and store_from_name(e["event"]):
            st, basis = store_from_name(e["event"]), "name in the event text"
        elif e["parent_id"] and e["parent_id"] in obj_store:
            st, basis = obj_store[e["parent_id"]][0], "its ad set"
        if st:
            e["store"], e["store_basis"] = st, basis
            remember(e)
    # Ad sets and ads created within 2 minutes of a campaign by the same person and tool: same store,
    # marked inferred; later events on the same object (id or name) carry it.
    creates = [e for e in events if e.get("store") not in (None, "ACCOUNT") and re.search(r"campaign created", e["event"], re.I)]
    for _round in range(2):
        for e in events:
            if e.get("store"):
                continue
            if e["parent_id"] and e["parent_id"] in obj_store:
                st, b = obj_store[e["parent_id"]]
                e["store"], e["store_basis"] = st, (b if b.startswith("inferred") else "its ad set")
            elif e["object_id"] and e["object_id"] in obj_store:
                e["store"], e["store_basis"] = obj_store[e["object_id"]]
            elif e["object"] and e["object"].lower() in name_store:
                e["store"], e["store_basis"] = name_store[e["object"].lower()]
            elif re.search(r"created", e["event"], re.I):
                near = [c for c in creates if c["actor_name"] == e["actor_name"] and c["app"] == e["app"]
                        and abs((c["_t"] - e["_t"]).total_seconds()) <= 120]
                if near:
                    e["store"] = near[0]["store"]
                    e["store_basis"] = "inferred: created with campaign '%s'" % near[0]["object"]
            remember(e)
    for e in events:
        if not e.get("store"):
            e["store"], e["store_basis"] = "ACCOUNT", "no store in the name"
    out = []
    for e in events:
        actor = classify_meta(e["actor_name"], e["actor_id"], e["app"], e["rule"])
        who = e["actor_name"] or None
        out.append({
            "platform": "meta", "store": e["store"], "store_basis": e["store_basis"],
            "time": e["_t"].isoformat(), "time_local": fmt_time(e["_t"]), "_t": e["_t"],
            "actor_class": actor, "actor_label": ACTOR_LABEL[actor], "actor_detail": who,
            "surface": e["app"] or None, "event": e["event"], "object": e["object"] or None,
            "object_id": e["object_id"] if e["store"] != "ACCOUNT" or e["store_basis"] != "account-wide" else None,
            "what": clean("%s%s" % (e["event"], (": " + e["detail"]) if e["detail"] else "")),
        })
    return src, out


# ---------------------------------------------------------------- digest assembly

def collapse(rows, key):
    """Identical rows (same key) within COLLAPSE_GAP_S of each other become one run."""
    runs = {}
    for r in sorted(rows, key=lambda r: (key(r), r["_t"])):
        k = key(r)
        lst = runs.setdefault(k, [])
        if lst and (r["_t"] - lst[-1][-1]["_t"]).total_seconds() <= COLLAPSE_GAP_S:
            lst[-1].append(r)
        else:
            lst.append([r])
    flat = [run for lst in runs.values() for run in lst]
    return sorted(flat, key=lambda run: run[0]["_t"])


def ads_line(run):
    c = run[0]
    n = len(run)
    span = fmt_span(run[0]["_t"], run[-1]["_t"])
    camp = 'campaign "%s"' % c["campaign"] if c["campaign"] else "account level (no campaign on the row)"
    count = "%d x " % n if n > 1 else ""
    return "- %s: %s%s, %s [%s]" % (span, count, c["what"], camp, c["surface"])


def meta_line(run):
    c = run[0]
    n = len(run)
    span = fmt_span(run[0]["_t"], run[-1]["_t"])
    count = "%d x " % n if n > 1 else ""
    if not c["object"]:
        obj = "object not named"
    else:
        obj = c["object"] if '"' in c["object"] else '"%s"' % c["object"]
    tail = " [%s]" % c["surface"] if c["surface"] else ""
    basis = ""
    if c.get("store_basis", "").startswith("inferred"):
        basis = " (store %s)" % c["store_basis"]
    return "- %s: %s%s, %s%s%s" % (span, count, c["what"], obj, tail, basis)


def actor_groups(rows):
    """[(actor class, detail or None, rows)] in the fixed actor order; people split by name."""
    out = []
    for a in ACTOR_ORDER:
        sel = [r for r in rows if r["actor_class"] == a]
        if not sel:
            continue
        if a in ("person", "person_recommendation", "script", "automated_rule", "unknown"):
            for who in sorted({r.get("actor_detail") or "" for r in sel}):
                out.append((a, who or None, [r for r in sel if (r.get("actor_detail") or "") == who]))
        else:
            out.append((a, None, sel))
    return out


def actor_heading(a, who, n):
    label = ACTOR_LABEL[a]
    if who and a != "drew":
        label = "%s: %s" % (label, who)
    return "### %s (%d)\n%s" % (label, n, ACTOR_MEANS[a])


def earlier_summary(rows):
    """Older rows grouped by day and actor: context the earlier shifts already covered."""
    groups = {}
    for r in rows:
        k = (local(r["_t"]).date(), r["actor_class"], r.get("actor_detail") if r["actor_class"] not in ("drew", "drew_recommendation", "auto_apply", "meta_system",
                                                            "google_internal") else None)
        groups.setdefault(k, []).append(r)
    out = []
    for (day, a, who), lst in sorted(groups.items(), key=lambda kv: max(r["_t"] for r in kv[1]), reverse=True):
        lst.sort(key=lambda r: r["_t"])
        places = []
        for r in lst:
            p = r.get("campaign") or r.get("object")
            if p and p not in places:
                places.append(p)
        things = []
        for r in lst:
            t = r.get("resource") or r.get("event")
            if t and t not in things:
                things.append(t)
        out.append({"day": day.isoformat(), "actor_class": a, "actor_label": ACTOR_LABEL[a], "actor_detail": who,
                     "count": len(lst), "first": lst[0]["time"], "last": lst[-1]["time"],
                     "first_local": fmt_time(lst[0]["_t"]), "last_local": fmt_clock(lst[-1]["_t"]),
                     "what": things[:4], "where": places[:3]})
    return out


def earlier_lines(items):
    lines = []
    for it in items[:EARLIER_MAX_LINES]:
        who = it["actor_label"] + (": " + it["actor_detail"] if it["actor_detail"] else "")
        span = it["first_local"] if it["first"] == it["last"] else "%s to %s" % (it["first_local"], it["last_local"])
        where = ("; " + ", ".join('"%s"' % w for w in it["where"])) if it["where"] else ""
        what = ", ".join(w if len(w) <= 120 else w[:117] + "..." for w in it["what"])
        lines.append("- %s: %s, %d change%s (%s)%s" % (span, who, it["count"], "" if it["count"] == 1 else "s",
                                                      what, where))
    if len(items) > EARLIER_MAX_LINES:
        lines.append("- ... %d more day-and-actor groups in changes.json" % (len(items) - EARLIER_MAX_LINES))
    return lines


def by_actor_counts(rows):
    c = {}
    for r in rows:
        k = r["actor_class"] if r["actor_class"] in ("drew", "drew_recommendation", "auto_apply", "meta_system",
                                                       "google_internal") else "%s: %s" % (
            r["actor_class"], r.get("actor_detail") or "not recorded")
        c[k] = c.get(k, 0) + 1
    return c


def short_counts(rows):
    parts = []
    for a, who, lst in actor_groups(rows):
        label = ACTOR_LABEL[a] + ((" " + who) if who and a != "drew" else "")
        first, last = lst[0]["_t"], lst[-1]["_t"]
        parts.append("%s %d (%s)" % (label, len(lst), fmt_span(first, last) if first != last else fmt_time(first)))
    return "; ".join(parts)


def strip_private(rows):
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]


def build(root, day, since_arg=None, until_arg=None, out=None, pull=True, refresh=False, stores=None,
          fetch=None, quiet=False):
    data_dir = os.path.join(root, "outputs", "ai-team", day.isoformat(), "data")
    out = os.path.abspath(out) if out else data_dir
    os.makedirs(out, exist_ok=True)
    dirs = [out] + ([data_dir] if os.path.abspath(data_dir) != out else [])
    win = find_window(root, day, since_arg, until_arg)
    ctx = {"root": root, "day": day, "dirs": dirs, "out": out, "pull": pull, "refresh": refresh,
           "fetch": fetch or gdata_fetch, "window": win}
    since, until = win["since"], win["until"]
    sheets = ads_sheet_ids(root)
    want = [s.upper() for s in (stores or STORES)]
    result = {"date": day.isoformat(), "generated_at": dt.datetime.now(PT).isoformat(timespec="seconds"),
              "window": {"since": since.isoformat(), "until": until.isoformat(), "since_local": fmt_time(since),
                         "until_local": fmt_time(until), "since_basis": win["since_basis"],
                         "until_basis": win["until_basis"], "previous_shift": win["prev_shift"],
                         "time_zone": "America/Los_Angeles", "notes": win["notes"]},
              "actor_classes": {a: {"label": ACTOR_LABEL[a], "means": ACTOR_MEANS[a]} for a in ACTOR_ORDER},
              "stores": {}, "notes": []}
    exit_code = 0
    per_store = {}
    for st in want:
        g = {"status": "not_exported", "changes": [], "earlier": [], "later_ignored": 0, "notes": []}
        if st in sheets:
            src, rows = load_ads_store(ctx, st, sheets[st])
            g.update({k: v for k, v in src.items() if k not in ("store", "sheet", "notes")})
            g["notes"] = list(src["notes"])
            s_since = since
            g["since"] = since.isoformat()
            g["since_basis"] = win["since_basis"]
            if not since_arg:
                plr, where = prev_export_last_run(ctx, st)
                if plr and since - dt.timedelta(hours=6) <= plr < since:
                    s_since = plr
                    g["since"] = plr.isoformat()
                    g["since_basis"] = "the previous shift's Ads export (last_run %s, from %s)" % (fmt_time(plr), where)
            g["since_local"] = fmt_time(s_since)
            if src["status"] in ("failed", "missing"):
                exit_code = 2
                g["notes"].append("no Google Ads change data for %s tonight; say 'no change log since %s', never guess"
                                  % (st, fmt_time(s_since, seconds=False)))
            else:
                inw = [r for r in rows if s_since <= r["_t"] < until]
                g["changes"] = inw
                g["earlier"] = earlier_summary([r for r in rows if r["_t"] < s_since])
                g["later_ignored"] = sum(1 for r in rows if r["_t"] >= until)
                lr = parse_any_time(g.get("export_last_run")) if g.get("export_last_run") else None
                if lr is None:
                    g["freshness"] = "unknown"
                    g["notes"].append("export last_run unknown (saved without the meta tab); the newest change "
                                      "row is %s" % (fmt_time(rows[-1]["_t"]) if rows else "none"))
                elif (until - lr).total_seconds() > STALE_HOURS * 3600:
                    g["freshness"] = "stale"
                    g["notes"].append("STALE: the export last ran %s, more than %d hours before this shift; changes "
                                      "after that are not visible" % (fmt_time(lr), STALE_HOURS))
                elif lr > until:
                    g["freshness"] = "later export"
                    g["notes"].append("replayed from a later export (last_run %s); rows at or after %s left out"
                                      % (fmt_time(lr), fmt_time(until)))
                else:
                    g["freshness"] = "fresh"
                    g["notes"].append("export last ran %s: changes after that land in the next shift's digest"
                                      % fmt_time(lr))
                if g.get("truncated") and rows and s_since < rows[0]["_t"]:
                    g["notes"].append("TRUNCATED: the export keeps only the newest %d changes and reaches back to %s; "
                                      "changes between %s and then are not visible" % (
                                          EXPORT_LIMIT, fmt_time(rows[0]["_t"]), fmt_time(s_since)))
                    g["coverage_complete"] = False
                elif lr and s_since < lr - dt.timedelta(days=14):
                    g["notes"].append("the export covers 14 days only; the window starts earlier")
                    g["coverage_complete"] = False
                else:
                    g["coverage_complete"] = True
            g["by_actor"] = by_actor_counts(g["changes"])
        else:
            g["notes"].append("no Google Ads export on file for %s (not in references/data-sources.md)" % st)
        per_store[st] = {"google_ads": g}
    msrc, mrows = load_meta(ctx)
    buckets = list(want) + [b for b in EXTRA_BUCKETS if any(r["store"] == b for r in mrows)]
    for st in buckets:
        per_store.setdefault(st, {"google_ads": None})
        rows = [r for r in mrows if r["store"] == st]
        m = {"status": msrc["status"], "files": msrc["files"], "notes": list(msrc["notes"]),
             "changes": [r for r in rows if since <= r["_t"] < until],
             "earlier": earlier_summary([r for r in rows if r["_t"] < since]),
             "later_ignored": sum(1 for r in rows if r["_t"] >= until)}
        if msrc["status"] == "no_file":
            m["notes"].append("no Meta activity file in data/")
            if msrc.get("summary_lines"):
                m["summary_lines"] = msrc["summary_lines"]
        elif mrows and max(r["_t"] for r in mrows) < since:
            m["notes"].append("the newest Meta event on file is %s, before this window" % fmt_time(max(r["_t"] for r in mrows)))
        m["by_actor"] = by_actor_counts(m["changes"])
        per_store[st]["meta"] = m
    # Write the files.
    written = []
    for st, blk in per_store.items():
        md = render_store_md(st, day, win, blk)
        p = os.path.join(out, "changes_%s.md" % st)
        write_text(p, md)
        written.append(p)
        js = {}
        for plat in ("google_ads", "meta"):
            b = blk.get(plat)
            if b is None:
                js[plat] = None
                continue
            b2 = dict(b)
            b2["changes"] = strip_private(b["changes"])
            js[plat] = b2
        result["stores"][st] = js
    if msrc["status"] == "no_file":
        result["notes"].append("no Meta activity file: Luka saves the raw ads_account_get_activity_logs response as "
                               "data/meta_activity.json")
    jp = os.path.join(out, "changes.json")
    write_text(jp, json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    written.append(jp)
    if not quiet:
        print_summary(root, day, win, per_store, msrc, written)
    return result, written, exit_code


def render_store_md(st, day, win, blk):
    g, m = blk.get("google_ads"), blk.get("meta")
    title = {"ACCOUNT": "Meta changes not tied to one store"}.get(st, "%s account changes" % st)
    lines = ["---", "type: ai-team-data", "date: %s" % day.isoformat(), "status: final",
             "tags: [ai-team, change-digest]", "store: %s" % st, "---",
             "# %s, %s to %s PT" % (title, fmt_time(win["since"], False), fmt_time(win["until"], False)),
             "",
             "Window: since %s, until %s (%s)." % (win["since_basis"], win["until_basis"],
                                                   ", ".join(win["notes"]) if win["notes"] else "no weekend"),
             "",
             "Read this first: every line names who made the change. \"Drew, by hand\" means Drew did it himself. "
             "\"Drew applied a Google recommendation\" means Drew clicked Apply: a person decided. Only \"Google "
             "auto-apply\" means nobody clicked anything. Never call a Drew line auto-apply, never call an auto-apply "
             "line Drew's, and quote the time shown.", ""]
    if g is not None:
        lines.append("## Google Ads")
        if g["status"] == "not_exported":
            lines += ["No Google Ads export for this store.", ""]
        elif g["status"] in ("failed", "missing"):
            lines += ["No change data tonight: " + "; ".join(g["notes"]), ""]
        else:
            lines.append("Source: %s (%s). Window for this store starts %s (%s)." % (
                g.get("file"), "read from the Sheet tonight" if g.get("pulled") else "saved copy",
                g["since_local"], g["since_basis"]))
            for n in g["notes"]:
                lines.append("Note: " + n + ".")
            lines.append("")
            if not g["changes"]:
                lines += ["No Google Ads changes in the window.", ""]
            else:
                lines += ["%d change%s: %s." % (len(g["changes"]), "" if len(g["changes"]) == 1 else "s",
                                                 short_counts(g["changes"])), ""]
                for a, who, rows in actor_groups(g["changes"]):
                    lines.append(actor_heading(a, who, len(rows)))
                    for run in collapse(rows, lambda r: (r["what"], r["campaign"] or "", r["surface"])):
                        lines.append(ads_line(run))
                    lines.append("")
            if g["earlier"]:
                lines.append("### Earlier in the same export (context only: earlier shifts covered these, never report them as new)")
                lines += earlier_lines(g["earlier"])
                lines.append("")
            if g.get("later_ignored"):
                lines += ["%d change%s after the window end left for the next shift." % (
                    g["later_ignored"], "" if g["later_ignored"] == 1 else "s"), ""]
    if m is not None:
        lines.append("## Meta")
        if m["status"] == "no_file":
            lines.append("No Meta activity file in data/. Luka saves the raw ads_account_get_activity_logs response "
                         "as data/meta_activity.json; until then Meta changes are unknown for this window, not zero.")
            for s in m.get("summary_lines", [])[:3]:
                lines.append("Summary found instead (not a per-event log): " + s)
            lines.append("")
        else:
            lines.append("Source: %s." % ", ".join("%s (%d events)" % (f["file"], f["events"]) for f in m["files"]))
            for n in m["notes"]:
                lines.append("Note: " + n + ".")
            lines.append("")
            if not m["changes"]:
                lines += ["No Meta changes in the window for this bucket.", ""]
            else:
                lines += ["%d event%s: %s." % (len(m["changes"]), "" if len(m["changes"]) == 1 else "s",
                                                short_counts(m["changes"])), ""]
                for a, who, rows in actor_groups(m["changes"]):
                    lines.append(actor_heading(a, who, len(rows)))
                    for run in collapse(rows, lambda r: (r["what"], r["object"] or "", r["surface"] or "")):
                        lines.append(meta_line(run))
                    lines.append("")
            if m["earlier"]:
                lines.append("### Earlier Meta events on file (context only, never report them as new)")
                lines += earlier_lines(m["earlier"])
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def print_summary(root, day, win, per_store, msrc, written):
    print("changes.py %s: window %s to %s PT (since %s)" % (
        day.isoformat(), fmt_time(win["since"]), fmt_time(win["until"]), win["since_basis"]))
    for st, blk in per_store.items():
        g = blk.get("google_ads")
        if g is None:
            continue
        if g["status"] == "not_exported":
            line = "no Google Ads export on file"
        elif g["status"] in ("failed", "missing"):
            line = "Google Ads: NO DATA (%s)" % "; ".join(g["notes"])[:200]
        else:
            flags = []
            if g.get("freshness") in ("stale", "unknown"):
                flags.append(g["freshness"].upper())
            if g.get("coverage_complete") is False:
                flags.append("PARTIAL COVERAGE")
            src = "pulled" if g.get("pulled") else "saved copy"
            line = "Google Ads %d%s%s [%s%s]" % (
                len(g["changes"]), ": " if g["changes"] else "", short_counts(g["changes"]), src,
                (", " + ", ".join(flags)) if flags else "")
        print("  %-6s %s" % (st, line))
    if msrc["status"] == "no_file":
        print("  Meta   no Meta activity file in data/ (save the raw ads_account_get_activity_logs response as "
              "data/meta_activity.json)")
    else:
        tot = sum(len(b["meta"]["changes"]) for b in per_store.values() if b.get("meta"))
        parts = ["%s %d" % (st, len(b["meta"]["changes"])) for st, b in per_store.items()
                 if b.get("meta") and b["meta"]["changes"]]
        print("  Meta   %d event%s in the window%s (from %s)" % (
            tot, "" if tot == 1 else "s", (": " + ", ".join(parts)) if parts else "",
            ", ".join(f["file"] for f in msrc["files"])))
    folder = os.path.dirname(written[-1]) if written else ""
    print("  wrote %s/: %s" % (rel(root, folder), ", ".join(os.path.basename(p) for p in written)))


# ---------------------------------------------------------------- selftest

def selftest():
    ok = [0]

    def check(cond, msg):
        if not cond:
            raise AssertionError(msg)
        ok[0] += 1

    # 1. actor classes, including the lesson from 2026-09-23 (Drew applying a recommendation is not auto-apply)
    cases = [
        (("drewmoon@digitalcliq.com", "GOOGLE_ADS_WEB_CLIENT"), "drew"),
        (("drewmoon@digitalcliq.com", "GOOGLE_ADS_MOBILE_APP"), "drew"),
        (("drewmoon@digitalcliq.com", "INTERNAL_TOOL"), "drew"),
        (("drewmoon@digitalcliq.com", "GOOGLE_ADS_RECOMMENDATIONS"), "drew_recommendation"),
        (("Recommendations Auto-Apply", "GOOGLE_ADS_RECOMMENDATIONS_SUBSCRIPTION"), "auto_apply"),
        (("Recommendations Auto-Apply", ""), "auto_apply"),
        (("drewmoon@digitalcliq.com", "GOOGLE_ADS_RECOMMENDATIONS_SUBSCRIPTION"), "auto_apply"),
        (("rep@store.com", "GOOGLE_ADS_RECOMMENDATIONS"), "person_recommendation"),
        (("drewmoon@digitalcliq.com", "GOOGLE_ADS_SCRIPTS"), "script"),
        (("", "GOOGLE_ADS_AUTOMATED_RULE"), "automated_rule"),
        (("", "INTERNAL_TOOL"), "google_internal"),
        (("someone@google.com", "INTERNAL_TOOL"), "google_internal"),
        (("rep@store.com", "GOOGLE_ADS_WEB_CLIENT"), "person"),
        (("", "GOOGLE_ADS_WEB_CLIENT"), "unknown"),
        (("", "GOOGLE_ADS_RECOMMENDATIONS"), "unknown"),
    ]
    for (email, ct), want in cases:
        got = classify_ads(email, ct)[0]
        check(got == want, "classify_ads(%r, %r) = %s, want %s" % (email, ct, got, want))
    check(classify_meta("Drew C Moon", "655", "Power Editor") == "drew", "meta Drew")
    check(classify_meta("Meta", "0", "") == "meta_system", "meta system")
    check(classify_meta("Pat Jones", "77", "Ads Manager") == "person", "meta person")
    check(classify_meta("Drew C Moon", "655", "Automated Rules") == "automated_rule", "meta rule")

    # 2. shift-log start formats
    day = dt.date(2026, 9, 29)
    for text, want in [("- 01:00 PDT tip-off. Mode shift.", (1, 0, 0)),
                       ("- **Tip-off:** 01:00 PDT, Tuesday 2026-09-29", (1, 0, 0)),
                       ("**Tip-off:** 01:02 PDT · **Whistle:** 02:35 PDT", (1, 2, 0)),
                       ("- Start: 01:03:12 PDT", (1, 3, 12)),
                       ("started_at: 2026-09-29T01:00:07-07:00", (1, 0, 7)),
                       ("- Start: 2026-09-29 01:04:55 PDT (real clock)", (1, 4, 55))]:
        got = parse_shift_start("---\ndate: 2026-09-29\n---\n" + text, day)
        check(got is not None and (got.hour, got.minute, got.second) == want, "shift start %r -> %r" % (text, got))
    check(parse_shift_start("- 01:0x CARS watch\n- Start: 01:00 PDT", day).minute == 0, "01:0x ignored")

    # 3. describe rows
    check(describe_ads("CAMPAIGN_CRITERION", "CREATE", ["brandList.sharedSet", "campaign", "negative"])[0]
          == "brand list exclusion", "brand list")
    check(describe_ads("CAMPAIGN_BUDGET", "UPDATE", ["amountMicros"])[2] == ["daily budget amount"], "budget words")
    check(describe_ads("AD_GROUP_CRITERION", "REMOVE", ["keyword.text", "negative", "status"])[0] == "keyword", "kw remove")

    tmp = tempfile.mkdtemp(prefix="changes-selftest-")
    try:
        root = tmp
        ref = os.path.join(root, ".claude", "skills", "ai-team", "references")
        os.makedirs(ref)
        with open(os.path.join(ref, "data-sources.md"), "w") as f:
            f.write("| MCP | 346-925-5700 | `SHEETMCPxxxxxxxxxxxxxxxxxxxx` (x) |\n"
                    "| NOI | 724-338-3586 | `SHEETNOIxxxxxxxxxxxxxxxxxxxx` (x) |\n")
        base = os.path.join(root, "outputs", "ai-team")
        fri, mon = dt.date(2026, 9, 25), dt.date(2026, 9, 28)
        for d, start in ((fri, "01:00"), (mon, "01:00")):
            os.makedirs(os.path.join(base, d.isoformat(), "data"))
            with open(os.path.join(base, d.isoformat(), "shift-log.md"), "w") as f:
                f.write("# Shift log\n\n- Start: %s PDT\n" % start)
        with open(os.path.join(base, fri.isoformat(), "data", "MCP_ads_meta.json"), "w") as f:
            json.dump({"rows": [["last_run", "2026-09-25 0:52:37"], ["account_timezone", "America/Los_Angeles"]]}, f)

        # 4. window: Monday since Friday's start, MCP since Friday's export
        w = find_window(root, mon)
        check(w["since"] == at(fri) and w["until"] == at(mon), "monday window %r" % w)
        check("weekend inside the window" in w["notes"], "weekend note")
        lone = tempfile.mkdtemp(prefix="changes-lone-")
        check(find_window(lone, dt.date(2026, 9, 29))["since"] == at(dt.date(2026, 9, 29)) - dt.timedelta(hours=48),
              "48h fallback")
        check(find_window(lone, mon)["since"] == at(fri), "monday fallback friday")
        shutil.rmtree(lone, ignore_errors=True)

        hdr = ["changeEvent_changeDateTime", "changeEvent_userEmail", "changeEvent_clientType",
               "changeEvent_changeResourceType", "changeEvent_resourceChangeOperation", "changeEvent_changedFields",
               "campaign_name"]
        rows = [hdr,
                ["2026-09-28 0:30:00", "drewmoon@digitalcliq.com", "GOOGLE_ADS_WEB_CLIENT", "CAMPAIGN", "UPDATE",
                 "status", "PMax"],                                                     # in window (before 01:00)
                ["2026-09-28 1:00:00", "drewmoon@digitalcliq.com", "GOOGLE_ADS_WEB_CLIENT", "CAMPAIGN", "UPDATE",
                 "status", "PMax"],                                                     # at until: next shift
                ["2026-09-25 17:07:16", "Recommendations Auto-Apply", "GOOGLE_ADS_RECOMMENDATIONS_SUBSCRIPTION",
                 "CAMPAIGN", "UPDATE", "maximizeConversions.targetCpaMicros", "PMax"]]
        rows += [["2026-09-25 17:01:38", "Recommendations Auto-Apply", "GOOGLE_ADS_RECOMMENDATIONS_SUBSCRIPTION",
                  "AD_GROUP_CRITERION", "REMOVE", "adGroup,keyword.text,negative,status", "Search " + EMDASH + " New"]] * 11
        rows += [["2026-09-26 9:00:00", "drewmoon@digitalcliq.com", "GOOGLE_ADS_RECOMMENDATIONS", "CAMPAIGN_BUDGET",
                  "UPDATE", "amountMicros", "PMax"],
                 ["2026-09-26 10:00:00", "", "GOOGLE_ADS_SCRIPTS", "CAMPAIGN", "UPDATE", "status", "Brand"],
                 ["2026-09-26 11:00:00", "rep@store.com", "GOOGLE_ADS_WEB_CLIENT", "AD", "UPDATE",
                  "responsiveSearchAd.headlines", "Brand"],
                 ["2026-09-25 0:55:00", "drewmoon@digitalcliq.com", "GOOGLE_ADS_WEB_CLIENT", "CAMPAIGN_BUDGET",
                  "UPDATE", "amountMicros", "PMax"],                                    # after Friday's export: tonight
                 ["2026-09-24 13:34:21", "drewmoon@digitalcliq.com", "GOOGLE_ADS_WEB_CLIENT", "CAMPAIGN_BUDGET",
                  "UPDATE", "amountMicros", "PMax"]]                                     # earlier: context only
        dd = os.path.join(base, mon.isoformat(), "data")
        with open(os.path.join(dd, "MCP_change_events_14d.txt"), "w") as f:
            f.write("=== MCP change_events_14d, saved by changes.py 2026-09-28T01:01:00-07:00, export last_run "
                    "2026-09-28 0:52:33, account_timezone America/Los_Angeles ===\n" + json.dumps(rows, indent=0))
        meta_raw = [
            {"event_type": "Ad set budget updated", "actor_id": "655557912", "actor_name": "Drew C Moon",
             "object_id": "111", "object_name": "NOI | Traffic | Fall", "application_name": "Power Editor",
             "datetime": "9/26/2026 at 9:15\u202fAM",
             "extra_data": json.dumps({"type": "payment_amount", "old_value": 1800, "new_value": 2500,
                                       "currency": "USD", "ip": "10.0.0.1"})},
            {"event_type": "Ad delivered", "actor_id": "0", "actor_name": "Meta", "object_id": "222",
             "object_name": "New Awareness Ad", "application_name": "", "datetime": "9/26/2026 at 9:20\u202fAM",
             "extra_data": json.dumps({"campaign_id": 111, "new_value": "Started delivery"})},
            {"event_type": "Account billed", "actor_id": "0", "actor_name": "Meta", "object_id": "123456789012345",
             "object_name": "(MAIN)123456789012345", "application_name": "", "datetime": "9/27/2026 at 12:57\u202fAM",
             "extra_data": "{}"},
            {"event_type": "Ad set run status updated", "actor_id": "9", "actor_name": "Pat Jones",
             "object_id": "333", "object_name": "Sterling BMW | Service", "application_name": "Ads Manager",
             "datetime": "9/27/2026 at 3:00\u202fPM", "extra_data": json.dumps({"old_value": "Active", "new_value": "Paused"})},
            {"event_type": "Campaign created", "actor_id": "655557912", "actor_name": "Drew C Moon",
             "object_id": "444", "object_name": "Mystery Campaign", "application_name": "Power Editor",
             "datetime": "9/20/2026 at 8:00\u202fAM", "extra_data": "{}"},
        ]
        with open(os.path.join(dd, "meta_activity.json"), "w") as f:
            json.dump({"result": json.dumps(meta_raw)}, f)

        def fake_fetch(sheet_id, rng):
            if rng.startswith("meta"):
                return [["last_run", "2026-09-28 0:50:00"], ["account_timezone", "America/Los_Angeles"]]
            return [hdr, ["2026-09-26 5:24:24", "drewmoon@digitalcliq.com", "GOOGLE_ADS_MOBILE_APP", "CAMPAIGN",
                          "UPDATE", "status", "NOI-PMAX"]]
        res, written, code = build(root, mon, fetch=fake_fetch, quiet=True)
        check(code == 0, "exit code %s" % code)
        mcp = res["stores"]["MCP"]["google_ads"]
        classes = [c["actor_class"] for c in mcp["changes"]]
        check(mcp["since"].startswith("2026-09-25T00:52:37"), "MCP since from Friday's export: %s" % mcp["since"])
        check(len(mcp["changes"]) == 17, "MCP in-window rows %d" % len(mcp["changes"]))
        check(classes.count("auto_apply") == 12 and classes.count("drew") == 2, "classes %r" % classes)
        check(classes.count("drew_recommendation") == 1 and classes.count("script") == 1 and classes.count("person") == 1,
              "other classes %r" % classes)
        check(mcp["later_ignored"] == 1, "row at until left for the next shift")
        check(len(mcp["earlier"]) == 1 and mcp["earlier"][0]["count"] == 1, "earlier %r" % mcp["earlier"])
        check(mcp["freshness"] == "fresh" and mcp["pulled"] is False, "fresh saved copy")
        noi = res["stores"]["NOI"]["google_ads"]
        check(noi["pulled"] is True and len(noi["changes"]) == 1, "NOI pulled %r" % noi)
        check(os.path.exists(os.path.join(dd, "NOI_change_events_14d.txt")), "raw pull saved")
        again, _, _ = build(root, mon, pull=False, quiet=True)
        check(len(again["stores"]["NOI"]["google_ads"]["changes"]) == 1 and
              again["stores"]["NOI"]["google_ads"]["pulled"] is False, "saved pull re-read offline")
        check(res["stores"]["SBMW"]["google_ads"]["status"] == "not_exported", "SBMW no export")
        md = open(os.path.join(dd, "changes_MCP.md")).read()
        check("11 x keyword removed" in md, "collapsed auto-apply keyword removals")
        check("This is NOT auto-apply." in md and "This is NOT Drew." in md, "actor meanings present")
        check(md.index("### Drew, by hand") < md.index("### Drew applied a Google recommendation")
              < md.index("### Google auto-apply"), "actor order")
        check("Fri 9/25 5:07:16pm" in md, "local time shown")
        # Meta
        noi_meta = res["stores"]["NOI"]["meta"]["changes"]
        check(len(noi_meta) == 2, "NOI Meta events %r" % noi_meta)
        check(noi_meta[0]["actor_class"] == "drew" and "USD 18.00 to USD 25.00" in noi_meta[0]["what"], "Meta budget")
        check(noi_meta[1]["actor_class"] == "meta_system" and noi_meta[1]["store_basis"] == "its ad set", "parent map")
        check(res["stores"]["SBMW"]["meta"]["changes"][0]["actor_detail"] == "Pat Jones", "Meta person named")
        acct = res["stores"]["ACCOUNT"]["meta"]
        check(acct["changes"][0]["object"] == "the DigitalCLIQ Meta account", "account-wide")
        check(acct["earlier"] and acct["earlier"][0]["actor_class"] == "drew", "earlier Meta")
        for p in written + [os.path.join(dd, "changes.json")]:
            txt = open(p, encoding="utf-8").read()
            check(EMDASH not in txt and ENDASH not in txt, "no em dash in %s" % p)
            check("123456789012345" not in txt, "Meta account id never written (%s)" % p)
            check("10.0.0.1" not in txt, "no Meta request data (%s)" % p)
        # truncation and staleness
        big = [hdr] + [["2026-09-27 12:%02d:00" % (i % 60), "drewmoon@digitalcliq.com", "GOOGLE_ADS_WEB_CLIENT",
                        "AD", "UPDATE", "responsiveSearchAd.headlines", "Brand"] for i in range(200)]
        with open(os.path.join(dd, "MCP_change_events_14d.txt"), "w") as f:
            f.write("=== MCP change_events_14d, export last_run 2026-09-26 12:00:00 ===\n" + json.dumps(big))
        res2, _, _ = build(root, mon, pull=False, quiet=True)
        g2 = res2["stores"]["MCP"]["google_ads"]
        check(g2["truncated"] and g2["coverage_complete"] is False, "truncated flagged")
        check(g2["freshness"] == "stale", "stale flagged")
        os.remove(os.path.join(dd, "NOI_change_events_14d.txt"))
        res3, _, code3 = build(root, mon, pull=False, quiet=True)
        check(code3 == 2 and res3["stores"]["NOI"]["google_ads"]["status"] == "missing", "missing -> exit 2")
        os.remove(os.path.join(dd, "meta_activity.json"))
        res4, _, _ = build(root, mon, pull=False, quiet=True)
        check(res4["stores"]["MCP"]["meta"]["status"] == "no_file", "no Meta file")
        check("No Meta activity file" in open(os.path.join(dd, "changes_MCP.md")).read(), "no Meta file in md")
        # Meta markdown table
        tbl = ("| Date/time (account tz) | Actor | Event | Object | Detail |\n|---|---|---|---|---|\n"
               "| 9/26/2026 8:01 AM | Meta | Ad delivered | Nissan Fall | Started delivery |\n"
               "| 9/26/2026 7:46 AM | Drew C Moon (Power Editor) | Campaign created | Nissan Fall | |\n"
               "| 9/26/2026 8:05 AM | Meta | Ad status updated | same | Pending Review to Active |\n")
        with open(os.path.join(dd, "meta_activity_log.md"), "w") as f:
            f.write(tbl)
        res5, _, _ = build(root, mon, pull=False, quiet=True)
        m5 = res5["stores"]["NOI"]["meta"]["changes"]
        check(len(m5) == 3 and m5[0]["actor_class"] == "drew" and m5[0]["surface"] == "Power Editor", "md table %r" % m5)
        check(m5[2]["object"] == "Nissan Fall" and m5[2]["actor_class"] == "meta_system", "ditto row %r" % m5[2])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("changes.py selftest: %d checks passed" % ok[0])


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description="Who changed what in Google Ads and Meta since the last shift.")
    ap.add_argument("cmd", nargs="?", default="build", choices=("build", "selftest"))
    ap.add_argument("--date", help="shift date YYYY-MM-DD (the folder outputs/ai-team/{date}/)")
    ap.add_argument("--since", help="window start, ISO (default: the previous shift's start)")
    ap.add_argument("--until", help="window end, ISO (default: this shift's start)")
    ap.add_argument("--out", help="output folder (default: outputs/ai-team/{date}/data)")
    ap.add_argument("--no-pull", action="store_true", help="saved files only, never read the Sheet")
    ap.add_argument("--refresh", action="store_true", help="read the Sheet even when a saved copy exists")
    ap.add_argument("--stores", help="comma list, default all five")
    ap.add_argument("--root", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.cmd == "selftest":
        selftest()
        return 0
    if not a.date:
        die("--date is required")
    if PT is None:
        die("zoneinfo not available in this Python")
    root = os.path.abspath(a.root) if a.root else DEFAULT_ROOT
    stores = [s.strip().upper() for s in a.stores.split(",")] if a.stores else None
    if stores:
        bad = [s for s in stores if s not in STORES]
        if bad:
            die("unknown store %s. Known: %s" % (", ".join(bad), ", ".join(STORES)))
    _res, _written, code = build(root, iso_date(a.date), a.since, a.until, a.out, pull=not a.no_pull,
                                 refresh=a.refresh, stores=stores)
    return code


if __name__ == "__main__":
    sys.exit(main())
