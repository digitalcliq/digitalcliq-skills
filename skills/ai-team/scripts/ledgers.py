#!/usr/bin/env python3
"""Ledgers for the DigitalCLIQ AI night shift. Standard library only.

Three ledgers share this script, all under outputs/ai-team/ledgers/:
  vendor-watch.json     Vendor Waste Watch: lead vendors billing with zero or near-zero leads, per store
  asks.json             Asks and wins: every ask the team raises, from the day raised to the day closed
  shift-ledger.jsonl    one summary row per store per target date per shift night
plus month-pack-{YYYY-MM}.json/.md (month to date per store, with coverage) for monthly-client-report,
and vendor-month-end-{YYYY-MM}.json/.md (keep-or-cut list per store).

Every command is one plain call from the vault root, writes its own files, prints a short summary.
  L = python3 .claude/skills/ai-team/scripts/ledgers.py

Vendor Waste Watch
  L vendor seed [--force]                seed the rows verified 2026-09-23 (NOI, from the shift files)
  L vendor scan --date D                 read D/data/crm_mtd_*.json and upsert every source that bills
                                         with zero leads, or with 2 or fewer leads on 500+ dollars
  L vendor update --store S --vendor V --date D [--spend N --leads N --sold N --as-of D --source T]
                  [--status open|confirmed-live|cut|kept|closed --note T --bench-category C --ask A2]
  L vendor list [--store S] [--month M] [--all] [--date D]
  L vendor month-end --month M           keep-or-cut list per store; close rates graded against the NADA
                                         table in the score-leads skill (reference/nada_benchmarks.json)
Asks and wins
  L asks seed [--force]
  L asks add --store S --owner O --label L --ask T --evidence T --date D [--needs-store]
             [--if-skipped T --done-when T --vendors V1,V2]
  L asks update --id A3 --date D [--evidence T --ask T --owner O ...] [--no-raise]
  L asks close --id A3 --date D --evidence T [--win T]
  L asks withdraw --id A3 --date D --reason T
  L asks list [--status open|closed|withdrawn|all] [--store S]
  L asks aging --date D [--out PATH]     brief blocks: Asks aging, Closed tonight, GM requests due
  L asks request --id A3 --date D        GM-level request skeleton for Drew to forward (nothing is sent)
  L asks request --due --date D          one skeleton for every ask that is due
  Owner is "Drew", "store: {role}" or "team: {player}". --needs-store marks an ask that waits on store
  staff; after 3 business days open it shows under GM requests due.
Shift ledger and month pack
  L shift append --date D                rows for every target date found in outputs/ai-team/D/
  L shift backfill --from D --to D
  L shift set --date D --store S --field F --value V --source T [--target-date D]
  L shift set --file PATH                bulk overrides, a JSON list of the same keys
  L shift list [--date D]
  L month --month YYYY-MM                month-pack-{M}.json and .md
  L ads-dump --date D                    save each Ads export Sheet's campaign_daily_30d (and meta tab)
                                         to D/data/{STORE}_campaign_daily_30d.txt (read-only, gdata auth)
CRM snapshot contract
  L crm-shape                            print the crm_mtd_{STORE}.json shape Nick writes every night
  L crm-check --file PATH                validate one snapshot against it
  L crm-correct --shift D --store S --source X --field cost --value 0 --reason T
Self test
  L selftest                             offline checks in a temp folder, touches nothing real

Text flags (--ask, --evidence, --win, --reason, --note, --source, --if-skipped, --done-when) also take
a file: add -file to the flag name (--evidence-file PATH), or pass the value "@PATH". Inside a
double-quoted argument the shell eats "$6,853" into ",853": write "6,853 dollars" or use a file.
Shell-damaged text is refused, as in slack.py.

Laws: aggregates only (text holding a phone number or email is refused), never em dashes (replaced
on write), never estimate (a missing source stays null and coverage says so).
"""
import argparse
import ast
import datetime as dt
import glob
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
ROOT = DEFAULT_ROOT
EMDASH, ENDASH = chr(8212), chr(8211)  # written as chr() so this file never holds one

STORES = ("SBMW", "NCBMW", "NOI", "MCP", "ATLAS")
# Names and tiers as in monthly-client-report reference/client_registry.json (Atlas is "Atlas" there).
STORE_NAMES = {"SBMW": "Sterling BMW", "NCBMW": "New Century BMW", "NOI": "Nissan of Irvine",
               "MCP": "McPeek Dodge Chrysler Jeep Ram of Anaheim", "ATLAS": "Atlas Shippers International"}
STORE_TIER = {"SBMW": "luxury", "NCBMW": "luxury", "NOI": "mainstream", "MCP": "mainstream", "ATLAS": "non-auto"}
VENDOR_STATUSES = ("open", "confirmed-live", "cut", "kept", "closed")
ASK_STATUSES = ("open", "closed", "withdrawn")
NEAR_ZERO_LEADS = 2
NEAR_ZERO_COST = 500.0
GM_REQUEST_BUSINESS_DAYS = 3
BENCH_BAND = 0.10  # same +/-10% band score-leads uses for Above / At / Below

# Meta campaigns whose names do not carry a store. The three finished boosted posts are NOI's
# (outputs/ai-team/2026-09-23/brief.md, data/meta_adsets.json). ledgers/meta-store-map.json adds more.
DEFAULT_META_MAP = {
    "120246868226640042": "NOI",   # Post: "Have you been to our new building? ..."
    "120251467985470042": "NOI",   # Post: "Still driving the same car you've had for years? ..."
    "120248615180530042": "NOI",   # [6/13/2026] Promoting nissanofirvine.com/specials/
}

# Same guards slack.py uses (Law 4 and the shell dollar bug), copied so this file stands alone.
PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_EDGE = r"(?:^|(?<=[\s(\[{'\"*_~+/-]))"
DOLLAR_DAMAGE = [
    re.compile(_EDGE + r"[.,]\d"),
    re.compile(_EDGE + r"/(?:day|mo|month|week|wk|yr|year)\b", re.I),
    re.compile(r"/bin/(?:z|ba)?sh(?![A-Za-z])"),
]

ROW_FIELDS = [
    "date", "target_date", "store",
    "ga4_sessions", "ga4_engaged_sessions", "ga4_key_events", "clean_key_events", "key_events_note",
    "organic_sessions", "ai_sessions", "ai_referrals_28d", "ga4_channels",
    "gads_cost", "gads_clicks", "gads_impressions", "gads_conversions",
    "meta_spend", "meta_clicks", "meta_landing_page_views",
    "crm_period_end", "crm_leads", "crm_good_leads", "crm_appointments", "crm_shows", "crm_sold",
    "crm_cost", "crm_live_vendor_cost",
    "notes", "sources",
]
OVERRIDABLE = [f for f in ROW_FIELDS if f not in ("date", "target_date", "store", "ga4_channels", "notes", "sources")]
CRM_ROW_FIELDS = ("crm_period_end", "crm_leads", "crm_good_leads", "crm_appointments", "crm_shows",
                  "crm_sold", "crm_cost", "crm_live_vendor_cost")

CRM_SHAPE = {
    "schema": "crm_mtd.v1",
    "store": "NOI",
    "crm": "VinSolutions",
    "report": "Lead Source ROI",
    "source_file": "Report-7275.xlsx",
    "period_start": "2026-09-01",
    "period_end": "2026-09-22",
    "generated_at": "2026-09-23T00:26",
    "pulled_by": "nick",
    "pulled_at_shift": "2026-09-23",
    "source_kind": "vendor",
    "headline": {"leads": 511, "good_leads": 397, "appointments": 64, "shows": 42, "sold": 53,
                 "cost": 14322.0, "live_vendor_cost": 9163.0},
    "definitions": {"leads": "Total Leads", "good_leads": "Good Leads", "appointments": "Appts Set",
                    "shows": "Appts Shown", "sold": "Sold from Leads", "cost": "Total Cost (report TOTAL row)"},
    "by_source": [
        {"source": "Cargurus", "leads": 60, "good_leads": 36, "appointments": 7, "shows": 5, "sold": 3,
         "cost": 2250.0, "vendor_status": "active"},
        {"source": "Auto Credit Express", "leads": 0, "good_leads": 0, "appointments": 0, "shows": 0,
         "sold": 0, "cost": 3850.0, "vendor_status": "unconfirmed"},
    ],
    "notes": ["Costco, Pownder, Radio inactive per Drew 2026-09-19; excluded from live_vendor_cost."],
}
CRM_SHAPE_RULES = [
    "One file per live store per night: outputs/ai-team/{date}/data/crm_mtd_{STORE}.json, written after the report is read.",
    "Aggregates only. Never a customer name, phone, email, or a row copied from the export (Law 4).",
    "period_start and period_end are the first and last full days of activity the report covers "
    "(a report generated 00:26 on 9/23 covers through 9/22), YYYY-MM-DD.",
    "headline.leads and headline.sold are required; every other number may be null when the CRM does not report it. "
    "Never estimate a missing number.",
    "source_kind is 'vendor' when by_source rows are lead sources or vendors (VinSolutions, Tekion), 'category' "
    "when they are pipeline categories (MomentumCRM KPI Summary). SBMW: leads = Prospects Created, "
    "appointments = Appts Created, shows = Shows, sold = Sold (DMS).",
    "by_source[].cost is the CRM's own cost for that source this month (null when the CRM carries no cost). "
    "vendor_status is active, inactive-per-drew, or unconfirmed.",
    "The 2026-09-22 files (VinSolutions by_source/totals, Momentum by_category/totals) are still read; new files use this shape.",
]

EMBEDDED_PATTERNS = [  # fallback copy of score-leads BENCHMARK_CATEGORY_PATTERNS, 2026-09-23
    ("data_list", ["financial services", "bmw financial", "fs list", "conquest", "equity mining",
                   "data list", "in market", "back in market", "first watch", "hot list"]),
    ("walk_in", ["walk-in", "walk in", "walkin", "showroom", "show room", "desk", "phone-up", "phone up",
                 "drove by", "drive by", "floor up", "location"]),
    ("owned_equity", ["repeat", "previous customer", "referral", "service drive", "service dept",
                      "service referral", "service", "loyalty", "be-back", "be back", "equity"]),
    ("phone", ["phone", "call", "click to call", "click-to-call"]),
    ("third_party", ["autotrader", "auto trader", "cars.com", "carscom", "cargurus", "car gurus", "edmunds",
                     "truecar", "true car", "carfax", "third party", "third-party", "3rd party"]),
    ("oem", ["bmw oem", "bmwusa", "bmw usa", "bmw group", "bmw na", "factory", "maco", "oem",
             "manufacturer", "nissan usa", "nissanusa", "choose nissan", "vpp", "usa leads"]),
    ("chat", ["gubagoo", "gobagoo", "podium", "roadster", "chat", "virtual retail", "carnow", "activengage"]),
    ("website", ["website", "dealer website", "apollo", "internet", "web lead", "google", "form", "vdp"]),
]


# ---------------------------------------------------------------- basics

def die(msg, code=1):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(code)


def P(*parts):
    return os.path.join(ROOT, "outputs", "ai-team", *parts)


def LP(name):
    return P("ledgers", name)


def rel(path):
    try:
        return os.path.relpath(path, ROOT)
    except ValueError:
        return path


def scrub(obj):
    """Never em dashes (Rule 14): replace them anywhere in data about to be written."""
    if isinstance(obj, str):
        s = re.sub(r"\s*" + EMDASH + r"\s*", " - ", obj)
        s = re.sub(r"(\S)" + ENDASH + r"(\S)", r"\1-\2", s)
        return s.replace(ENDASH, "-")
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()}
    return obj


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(scrub(data), f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def save_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(scrub(text))
    os.replace(tmp, path)


def iso(s, what="date"):
    try:
        return dt.date.fromisoformat(str(s)).isoformat()
    except ValueError:
        die("%s must be YYYY-MM-DD, got %r" % (what, s))


def month_of(s):
    if not re.match(r"^\d{4}-\d{2}$", str(s or "")):
        die("--month must be YYYY-MM, got %r" % s)
    return s


def month_days(month):
    y, m = int(month[:4]), int(month[5:7])
    first = dt.date(y, m, 1)
    nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
    return [(first + dt.timedelta(days=i)).isoformat() for i in range((nxt - first).days)]


def daterange(a, b):
    a, b = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
    return [(a + dt.timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def business_days(a, b):
    """Weekdays after a, up to and including b."""
    a, b = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
    n, cur = 0, a
    while cur < b:
        cur += dt.timedelta(days=1)
        if cur.weekday() < 5:
            n += 1
    return n


def num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip().replace("$", "").replace(",", "")
    if s == "" or s.lower() in ("none", "null", "n/a", "na", "-"):
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return int(f) if (f.is_integer() and "." not in s) else f


def money(v):
    n = num(v)
    return None if n is None else round(float(n), 2)


def fmt_money(v):
    return "n/a" if v is None else "$" + format(round(v, 2), ",.2f").replace(".00", "")


def fmt_num(v):
    if v is None:
        return "n/a"
    if isinstance(v, float) and not v.is_integer():
        return format(round(v, 2), ",")
    return format(int(v), ",")


def add(a, b):
    if b is None:
        return a
    return b if a is None else a + b


def text_arg(args, name, required=False, shell_checked=True):
    """--name VALUE, --name @PATH, or --name-file PATH. PII refused; shell-eaten dollars refused."""
    val = getattr(args, name, None)
    fval = getattr(args, name + "_file", None)
    from_file = False
    if fval:
        val, from_file = open(fval, encoding="utf-8").read(), True
    elif isinstance(val, str) and val.startswith("@") and os.path.exists(val[1:]):
        val, from_file = open(val[1:], encoding="utf-8").read(), True
    if val is None:
        if required:
            die("--%s (or --%s-file) is required" % (name.replace("_", "-"), name.replace("_", "-")))
        return None
    val = scrub(val.strip())
    if PHONE.search(val) or EMAIL.search(val):
        die("refused: --%s looks like it holds a phone number or email address. Aggregates only (Law 4)."
            % name.replace("_", "-"))
    if shell_checked and not from_file:
        for rx in DOLLAR_DAMAGE:
            m = rx.search(val)
            if m:
                die("refused: --%s looks shell-mangled near %r. The shell eats $ amounts inside double quotes. "
                    "Write '6,853 dollars' or use --%s-file." % (name.replace("_", "-"), val[m.start():m.start() + 12],
                                                                name.replace("_", "-")))
    return val


def store_arg(s, allow_all=False):
    s = (s or "").strip().upper()
    if allow_all and s == "ALL":
        return s
    if s not in STORES:
        die("--store must be one of %s%s, got %r" % (", ".join(STORES), " or ALL" if allow_all else "", s))
    return s


# ---------------------------------------------------------------- shift folders and source files

def shift_dates():
    out = []
    for p in glob.glob(P("20??-??-??")):
        if os.path.isdir(p):
            out.append(os.path.basename(p))
    return sorted(out)


def data_dirs(date):
    """The shift's data folders, oldest first: data/, then run2/data/ and later runs (a later run wins)."""
    base = P(date)
    dirs = []
    if os.path.isdir(os.path.join(base, "data")):
        dirs.append(os.path.join(base, "data"))
    runs = sorted(glob.glob(os.path.join(base, "run*", "data")),
                  key=lambda p: int(re.sub(r"\D", "", os.path.basename(os.path.dirname(p))) or 0))
    return dirs + [d for d in runs if os.path.isdir(d)]


def ga4_files(dirs):
    out = []
    for d in dirs:
        for p in sorted(glob.glob(os.path.join(d, "ga4_*.json")) + glob.glob(os.path.join(d, "*", "ga4_*.json"))):
            m = re.match(r"^ga4_([A-Za-z]+)\.json$", os.path.basename(p))
            if m and m.group(1).upper() in STORES:
                out.append((m.group(1).upper(), p))
    return out


def ads_files(dirs):
    out = {}
    for d in dirs:
        for p in sorted(glob.glob(os.path.join(d, "*_campaign_daily_30d.*"))):
            m = re.match(r"^([A-Za-z]+)_campaign_daily_30d\.(txt|json)$", os.path.basename(p))
            if m and m.group(1).upper() in STORES:
                out[m.group(1).upper()] = p
    return out


def meta_files(dirs):
    out = []
    for d in dirs:
        out += sorted(glob.glob(os.path.join(d, "meta_campaigns*.json")))
    return out


def crm_files(dirs):
    out = {}
    for d in dirs:
        for p in sorted(glob.glob(os.path.join(d, "crm_mtd_*.json"))):
            m = re.match(r"^crm_mtd_([A-Za-z]+)\.json$", os.path.basename(p))
            if m and m.group(1).upper() in STORES:
                out[m.group(1).upper()] = p
    return out


# ---------------------------------------------------------------- GA4

def ga4_day(pack, date):
    ymd = date.replace("-", "")
    rows = [r for r in (pack.get("channel_daily_last7") or []) if str(r.get("date")) == ymd]
    if not rows:
        return None
    out = {"sessions": 0, "engaged": 0, "key_events": 0, "channels": {}}
    for r in rows:
        ch = r.get("sessionDefaultChannelGroup") or "(other)"
        s, e, k = num(r.get("sessions")) or 0, num(r.get("engagedSessions")) or 0, num(r.get("keyEvents")) or 0
        out["sessions"] += s
        out["engaged"] += e
        out["key_events"] += k
        c = out["channels"].setdefault(ch, {"sessions": 0, "engaged": 0, "key_events": 0})
        c["sessions"] += s
        c["engaged"] += e
        c["key_events"] += k
    out["organic"] = out["channels"].get("Organic Search", {}).get("sessions", 0)
    out["ai"] = out["channels"].get("AI Assistant", {}).get("sessions", 0)
    return out


# ---------------------------------------------------------------- Google Ads export dumps

def ads_rows(path):
    text = open(path, encoding="utf-8").read()
    i = text.find("[")
    if i < 0:
        return []
    arr, _ = json.JSONDecoder().raw_decode(text[i:])
    if not arr or not isinstance(arr[0], list):
        return []
    head = arr[0]
    return [dict(zip(head, r)) for r in arr[1:] if isinstance(r, list)]


def ads_by_date(rows):
    out = {}
    for r in rows:
        d = str(r.get("segments_date") or "")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
            continue
        a = out.setdefault(d, {"cost": 0.0, "clicks": 0, "impressions": 0, "conversions": 0.0, "campaigns": {}})
        cost, clicks = money(r.get("metrics_cost")) or 0.0, num(r.get("metrics_clicks")) or 0
        imp, conv = num(r.get("metrics_impressions")) or 0, float(num(r.get("metrics_conversions")) or 0)
        a["cost"] += cost
        a["clicks"] += clicks
        a["impressions"] += imp
        a["conversions"] += conv
        c = a["campaigns"].setdefault(r.get("campaign_name") or r.get("campaign_id") or "?",
                                      {"cost": 0.0, "clicks": 0, "impressions": 0, "conversions": 0.0})
        c["cost"] += cost
        c["clicks"] += clicks
        c["impressions"] += imp
        c["conversions"] += conv
    return out


# ---------------------------------------------------------------- Meta

def meta_map():
    m = dict(DEFAULT_META_MAP)
    m.update(load_json(LP("meta-store-map.json"), {}) or {})
    return m


def meta_store(name, cid, explicit, mapping):
    if explicit and str(explicit).upper() in STORES:
        return str(explicit).upper()
    if cid and str(cid) in mapping:
        return mapping[str(cid)]
    n = (name or "").lower()
    if "ncbmw" in n or "new century" in n:
        return "NCBMW"
    if "sbmw" in n or "sterling" in n:
        return "SBMW"
    if "nissan" in n or "irvine" in n:
        return "NOI"
    if "atlas" in n:
        return "ATLAS"
    if "mcpeek" in n or re.match(r"^mcp\b", n):
        return "MCP"
    return "UNMAPPED"


def meta_extract(path, mapping=None):
    """(covered daily dates, campaign-day records) from any of the shapes the shift has saved."""
    mapping = mapping if mapping is not None else meta_map()
    d = load_json(path, None)
    covered, recs = set(), []

    def lpv_of(r):
        for k in ("landing_page_views", "lpv", "omni_landing_page_view"):
            if num(r.get(k)) is not None:
                return num(r.get(k))
        for k in ("result", "results"):
            m = re.search(r"landing page views\s+(\d+)", str(r.get(k) or ""), re.I)
            if m:
                return int(m.group(1))
        return None

    def rec(date, r, parent=None):
        parent = parent or {}
        if not isinstance(r, dict) or not re.match(r"^\d{4}-\d{2}-\d{2}$", str(date or "")):
            return
        name = r.get("name") or parent.get("name")
        cid = r.get("id") or r.get("campaign_id") or parent.get("id")
        if not name and not cid:
            return
        spend = None
        for k in ("spend", "spend_usd", "amount_spent"):
            if money(r.get(k)) is not None:
                spend = money(r.get(k))
                break
        if spend is None:
            return
        recs.append({"date": date, "id": str(cid or ""), "name": name or "",
                     "store": meta_store(name, cid, r.get("store") or parent.get("store"), mapping),
                     "spend": spend, "clicks": num(r.get("clicks")), "lpv": lpv_of(r)})

    if not isinstance(d, dict):
        return covered, recs
    if isinstance(d.get("campaigns"), list):
        m = re.search(r"time_range (\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2}), time_increment 1", str(d.get("call", "")))
        if m:
            covered |= set(daterange(m.group(1), m.group(2)))
        for c in d["campaigns"]:
            for day in (c.get("daily") or []):
                if isinstance(day, dict) and day.get("date"):
                    covered.add(day["date"])
                    rec(day["date"], day, c)
    for k, v in d.items():
        if not isinstance(v, list):
            continue
        m = re.match(r"^daily(?:_(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2}))?$", k)
        if m:
            if m.group(1):
                covered |= set(daterange(m.group(1), m.group(2)))
            for r in v:
                if isinstance(r, dict) and r.get("date"):
                    covered.add(r["date"])
                    rec(r["date"], r)
            continue
        m = re.match(r"^yesterday_(\d{4}-\d{2}-\d{2})$", k)
        if m:
            covered.add(m.group(1))
            for r in v:
                rec(m.group(1), r)
    if isinstance(d.get("rows"), list):
        m = re.search(r"yesterday (\d{4}-\d{2}-\d{2})", str(d.get("window", "")))
        if m:
            covered.add(m.group(1))
            for r in d["rows"]:
                rec(m.group(1), r)
    return covered, recs


def meta_store_day(recs, store, date):
    out = {"spend": 0.0, "clicks": 0, "lpv": 0, "campaigns": {}}
    for r in recs:
        if r["date"] == date and r["store"] == store:
            out["spend"] += r["spend"] or 0
            out["clicks"] += r["clicks"] or 0
            out["lpv"] += r["lpv"] or 0
            c = out["campaigns"].setdefault(r["name"] or r["id"], {"spend": 0.0, "clicks": 0, "lpv": 0})
            c["spend"] += r["spend"] or 0
            c["clicks"] += r["clicks"] or 0
            c["lpv"] += r["lpv"] or 0
    return out


# ---------------------------------------------------------------- CRM snapshots

def crm_corrections():
    return (load_json(LP("crm-corrections.json"), {"corrections": []}) or {}).get("corrections", [])


def crm_normalize(d, shift=None, store=None):
    """One shape for every snapshot: the crm_mtd.v1 contract, or the two 2026-09-22 legacy shapes."""
    store = (d.get("store") or store or "").upper()
    out = {"store": store, "crm": d.get("crm"), "report": d.get("report"), "source_file": d.get("source_file"),
           "period_start": d.get("period_start"), "period_end": d.get("period_end"),
           "source_kind": d.get("source_kind"), "headline": {}, "by_source": [], "notes": list(d.get("notes") or [])}
    if not out["period_end"]:
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", str(d.get("date_range", "")))
        if len(dates) >= 2:
            out["period_start"], out["period_end"] = dates[0], dates[1]
    t = d.get("totals") or {}
    if d.get("schema") == "crm_mtd.v1" or "headline" in d:
        h = d.get("headline") or {}
        out["headline"] = {k: num(h.get(k)) for k in ("leads", "good_leads", "appointments", "shows", "sold",
                                                       "cost", "live_vendor_cost")}
        for r in d.get("by_source") or []:
            out["by_source"].append({"source": r.get("source"), "leads": num(r.get("leads")),
                                     "good_leads": num(r.get("good_leads")), "appointments": num(r.get("appointments")),
                                     "shows": num(r.get("shows")), "sold": num(r.get("sold")),
                                     "cost": money(r.get("cost")), "vendor_status": r.get("vendor_status"),
                                     "note": r.get("note")})
    elif "by_source" in d:  # VinSolutions Lead Source ROI, 2026-09-22
        out["source_kind"] = out["source_kind"] or "vendor"
        out["headline"] = {"leads": num(t.get("total_leads")), "good_leads": num(t.get("good_leads")),
                           "appointments": num(t.get("appts_set")), "shows": num(t.get("appts_shown")),
                           "sold": num(t.get("sold_from_leads")), "cost": money(t.get("total_cost")),
                           "live_vendor_cost": money(t.get("live_vendor_cost"))}
        for r in d["by_source"]:
            out["by_source"].append({"source": r.get("source"), "leads": num(r.get("total_leads")),
                                     "good_leads": num(r.get("good_leads")), "appointments": num(r.get("appts_set")),
                                     "shows": num(r.get("appts_shown")), "sold": num(r.get("sold_from_leads")),
                                     "cost": money(r.get("total_cost")), "vendor_status": None, "note": r.get("note")})
    elif "by_category" in d:  # MomentumCRM KPI Summary, 2026-09-22
        out["source_kind"] = out["source_kind"] or "category"
        out["headline"] = {"leads": num(t.get("prospects_created")), "good_leads": None,
                           "appointments": num(t.get("appts_created")), "shows": num(t.get("shows")),
                           "sold": num(t.get("sold_dms")), "cost": None, "live_vendor_cost": None}
        for r in d["by_category"]:
            out["by_source"].append({"source": r.get("category"), "leads": num(r.get("prospects_created")),
                                     "good_leads": None, "appointments": num(r.get("appts_created")),
                                     "shows": num(r.get("shows")), "sold": num(r.get("sold_dms")), "cost": None,
                                     "vendor_status": None, "note": r.get("note")})
    for c in crm_corrections():
        if c.get("shift") == shift and str(c.get("store", "")).upper() == store:
            for r in out["by_source"]:
                if str(r.get("source", "")).lower() == str(c.get("source", "")).lower() and c.get("field") in r:
                    r[c["field"]] = c.get("value")
                    out["notes"].append("corrected %s %s to %s: %s" % (r["source"], c["field"], c.get("value"),
                                                                      c.get("reason", "")))
    return out


def crm_problems(d):
    probs = []
    if d.get("schema") != "crm_mtd.v1":
        probs.append("schema is not crm_mtd.v1 (legacy files are still read, new ones should say crm_mtd.v1)")
    if str(d.get("store", "")).upper() not in STORES:
        probs.append("store must be one of " + ", ".join(STORES))
    for k in ("period_start", "period_end"):
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(d.get(k) or "")):
            probs.append("%s must be YYYY-MM-DD" % k)
    h = d.get("headline") or {}
    for k in ("leads", "sold"):
        if k not in h:
            probs.append("headline.%s is required (null only when the CRM does not report it)" % k)
    for k, v in h.items():
        if v is not None and num(v) is None:
            probs.append("headline.%s must be a number or null" % k)
    if d.get("source_kind") not in ("vendor", "category"):
        probs.append("source_kind must be vendor or category")
    for i, r in enumerate(d.get("by_source") or []):
        if not r.get("source"):
            probs.append("by_source[%d] has no source" % i)
    blob = json.dumps(d)
    if PHONE.search(blob) or EMAIL.search(blob):
        probs.append("holds something that looks like a phone number or email: aggregates only (Law 4)")
    if EMDASH in blob:
        probs.append("holds an em dash")
    return probs


def crm_snapshots(month=None):
    """Every normalized CRM snapshot across the shift folders: (shift, path, normalized)."""
    out = []
    for sd in shift_dates():
        for store, p in crm_files(data_dirs(sd)).items():
            try:
                n = crm_normalize(load_json(p, {}), sd, store)
            except (ValueError, OSError):
                continue
            if month and not str(n.get("period_end") or "").startswith(month):
                continue
            out.append((sd, p, n))
    return out


# ---------------------------------------------------------------- shift ledger

def read_ledger():
    path = LP("shift-ledger.jsonl")
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def write_ledger(rows):
    path = LP("shift-ledger.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rows = sorted(rows, key=lambda r: (r["date"], r["target_date"], STORES.index(r["store"])))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(scrub(r), ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def load_overrides():
    return (load_json(LP("shift-overrides.json"), {"overrides": []}) or {}).get("overrides", [])


def build_rows(date):
    dirs = data_dirs(date)
    if not dirs:
        return [], {"note": "no data folder in outputs/ai-team/%s" % date}
    ga4 = {}
    for store, p in ga4_files(dirs):
        pack = load_json(p, {}) or {}
        t = pack.get("target_date")
        if t:
            ga4[(store, t)] = (p, pack)
    targets = sorted({t for (_, t) in ga4}) or [(dt.date.fromisoformat(date) - dt.timedelta(days=1)).isoformat()]
    primary = max(targets)
    ads = {s: (p, ads_by_date(ads_rows(p))) for s, p in ads_files(dirs).items()}
    mapping = meta_map()
    metas = [(p,) + meta_extract(p, mapping) for p in meta_files(dirs)]
    crm = {}
    for s, p in crm_files(dirs).items():
        crm[s] = (p, crm_normalize(load_json(p, {}), date, s))
    overrides = [o for o in load_overrides() if o.get("date") == date]
    stats = {"targets": targets, "ga4": 0, "gads": 0, "meta": 0, "crm": 0, "overrides": 0, "unmapped_meta": 0}
    rows = []
    for t in targets:
        for s in STORES:
            row = {k: None for k in ROW_FIELDS}
            row.update({"date": date, "target_date": t, "store": s, "notes": [], "sources": {}})
            g = ga4.get((s, t))
            if g:
                day = ga4_day(g[1], t)
                if day:
                    row.update({"ga4_sessions": day["sessions"], "ga4_engaged_sessions": day["engaged"],
                                "ga4_key_events": day["key_events"], "organic_sessions": day["organic"],
                                "ai_sessions": day["ai"],
                                "ga4_channels": {c: [v["sessions"], v["key_events"]] for c, v in sorted(day["channels"].items())}})
                    refs = g[1].get("ai_engine_referrals_last28")
                    if isinstance(refs, list):
                        row["ai_referrals_28d"] = sum(num(r.get("sessions")) or 0 for r in refs)
                    row["sources"]["ga4"] = rel(g[0])
                    stats["ga4"] += 1
                if g[1].get("errors"):
                    row["notes"].append("ga4 errors: %s" % "; ".join(str(e) for e in g[1]["errors"])[:300])
            if s in ads:
                day = ads[s][1].get(t)
                if day:
                    row.update({"gads_cost": round(day["cost"], 2), "gads_clicks": day["clicks"],
                                "gads_impressions": day["impressions"], "gads_conversions": round(day["conversions"], 2)})
                    row["sources"]["gads"] = rel(ads[s][0])
                    stats["gads"] += 1
                else:
                    row["notes"].append("ads dump %s has no rows for %s" % (os.path.basename(ads[s][0]), t))
            covering = [m for m in metas if t in m[1]]
            if covering:
                mp, _cov, recs = covering[-1]
                md = meta_store_day(recs, s, t)
                row.update({"meta_spend": round(md["spend"], 2), "meta_clicks": md["clicks"],
                            "meta_landing_page_views": md["lpv"]})
                row["sources"]["meta"] = rel(mp)
                stats["meta"] += 1
                if s == STORES[0]:
                    stats["unmapped_meta"] += sum(1 for r in recs if r["date"] == t and r["store"] == "UNMAPPED")
            if s in crm:
                p, n = crm[s]
                pe = n.get("period_end")
                if pe == t or (t == primary and pe not in targets):
                    h = n["headline"]
                    row.update({"crm_period_end": pe, "crm_leads": h.get("leads"), "crm_good_leads": h.get("good_leads"),
                                "crm_appointments": h.get("appointments"), "crm_shows": h.get("shows"),
                                "crm_sold": h.get("sold"), "crm_cost": h.get("cost"),
                                "crm_live_vendor_cost": h.get("live_vendor_cost")})
                    row["sources"]["crm"] = rel(p)
                    stats["crm"] += 1
            for o in overrides:
                if str(o.get("store", "")).upper() != s:
                    continue
                if (o.get("target_date") or primary) != t:
                    continue
                row[o["field"]] = o.get("value")
                row["sources"].setdefault("overrides", []).append("%s: %s" % (o["field"], o.get("source", "")))
                stats["overrides"] += 1
                if o["field"] in CRM_ROW_FIELDS and "crm" not in row["sources"]:
                    stats["crm"] += 1
                    row["sources"]["crm"] = "override"
            rows.append(row)
    return rows, stats


def cmd_shift_append(args, quiet=False):
    date = iso(args.date)
    rows, stats = build_rows(date)
    ledger = [r for r in read_ledger() if r.get("date") != date]
    write_ledger(ledger + rows)
    if not quiet:
        if not rows:
            print("shift append %s: %s, nothing written" % (date, stats.get("note")))
        else:
            n = len(STORES) * len(stats["targets"])
            print("shift append %s: %d rows, target %s. ga4 %d/%d, gads %d/%d, meta %d/%d%s, crm %d, overrides %d. "
                  "Ledger now %d rows." % (date, len(rows), ", ".join(stats["targets"]), stats["ga4"], n,
                                          stats["gads"], len(stats["targets"]) * 3, stats["meta"], n,
                                          " (%d unmapped campaign rows)" % stats["unmapped_meta"] if stats["unmapped_meta"] else "",
                                          stats["crm"], stats["overrides"], len(ledger) + len(rows)))
    return rows


def cmd_shift_backfill(args):
    a, b = iso(args.from_date, "--from"), iso(args.to_date, "--to")
    done = []
    for sd in shift_dates():
        if a <= sd <= b:
            ns = argparse.Namespace(date=sd)
            rows = cmd_shift_append(ns, quiet=True)
            done.append((sd, len(rows)))
    for sd, n in done:
        print("  %s: %d rows" % (sd, n))
    print("shift backfill %s to %s: %d shift folders, %d rows. Ledger now %d rows."
          % (a, b, len(done), sum(n for _, n in done), len(read_ledger())))


def parse_value(v):
    if v is None:
        return None
    s = str(v).strip()
    if s.lower() in ("null", "none", ""):
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    n = num(s)
    return n if n is not None and re.match(r"^[\d$,.\-]+$", s) else s


def cmd_shift_set(args):
    items = []
    if args.file:
        items = load_json(args.file, [])
        if not isinstance(items, list):
            die("--file must hold a JSON list of overrides")
    else:
        if not (args.date and args.store and args.field):
            die("shift set needs --date --store --field --value --source, or --file")
        items = [{"date": args.date, "store": args.store, "field": args.field, "value": args.value,
                  "source": text_arg(args, "source", required=True), "target_date": args.target_date}]
    ovs = load_overrides()
    touched = set()
    for it in items:
        date = iso(it.get("date"))
        store = store_arg(it.get("store"))
        field = it.get("field")
        if field not in OVERRIDABLE:
            die("--field %r is not overridable. Choose from: %s" % (field, ", ".join(OVERRIDABLE)))
        src = scrub(str(it.get("source") or "").strip())
        if not src:
            die("every override needs a source (file and line it came from)")
        if PHONE.search(src) or EMAIL.search(src):
            die("refused: source text looks like it holds a phone number or email address")
        tdate = iso(it["target_date"]) if it.get("target_date") else None
        value = it.get("value") if args.file else parse_value(it.get("value"))
        ovs = [o for o in ovs if not (o["date"] == date and o["store"] == store and o["field"] == field
                                       and (o.get("target_date") or None) == tdate)]
        ovs.append({"date": date, "store": store, "target_date": tdate, "field": field, "value": value,
                    "source": src, "set_at": dt.datetime.now().isoformat(timespec="seconds")})
        touched.add(date)
    save_json(LP("shift-overrides.json"), {"_about": "Hand-entered values for shift-ledger rows, each with its source. "
                                           "Applied on every shift append, so a re-run keeps them.",
                                           "overrides": sorted(ovs, key=lambda o: (o["date"], o["store"], o["field"]))})
    for d in sorted(touched):
        cmd_shift_append(argparse.Namespace(date=d), quiet=True)
    print("shift set: %d override(s) saved for %s, rows rebuilt. %d overrides on file."
          % (len(items), ", ".join(sorted(touched)), len(ovs)))


def cmd_shift_list(args):
    rows = read_ledger()
    if args.date:
        rows = [r for r in rows if r["date"] == iso(args.date)]
    for r in rows:
        print("%s > %s %-5s sess %s ke %s%s org %s ai %s | gads %s clk %s conv %s | meta %s | crm %s leads %s sold %s"
              % (r["date"], r["target_date"], r["store"], fmt_num(r["ga4_sessions"]), fmt_num(r["ga4_key_events"]),
                 " (clean %s)" % fmt_num(r["clean_key_events"]) if r.get("clean_key_events") is not None else "",
                 fmt_num(r["organic_sessions"]), fmt_num(r["ai_sessions"]), fmt_money(r["gads_cost"]),
                 fmt_num(r["gads_clicks"]), fmt_num(r["gads_conversions"]), fmt_money(r["meta_spend"]),
                 r.get("crm_period_end") or "n/a", fmt_num(r["crm_leads"]), fmt_num(r["crm_sold"])))
    print("shift list: %d rows" % len(rows))


# ---------------------------------------------------------------- month pack

def coverage(days_with, month):
    days = month_days(month)
    have = sorted(d for d in set(days_with) if d in days)
    return {"days": have, "count": len(have), "days_in_month": len(days),
            "missing": [d for d in days if d not in have], "complete": len(have) == len(days),
            "first": have[0] if have else None, "last": have[-1] if have else None}


def harvest_ga4(month):
    best = {}
    for sd in shift_dates():
        for store, p in ga4_files(data_dirs(sd)):
            pack = load_json(p, {}) or {}
            rank = (str(pack.get("pulled_at") or sd), p)
            for r in pack.get("channel_daily_last7") or []:
                ymd = str(r.get("date") or "")
                if len(ymd) != 8:
                    continue
                d = "%s-%s-%s" % (ymd[:4], ymd[4:6], ymd[6:])
                if not d.startswith(month):
                    continue
                cur = best.get((store, d))
                if cur is None or rank > cur[0]:
                    best[(store, d)] = (rank, p, pack)
    out = {}
    for (store, d), (_rank, p, pack) in best.items():
        out.setdefault(store, {})[d] = (p, ga4_day(pack, d))
    return out


def harvest_ads(month):
    best = {}
    for sd in shift_dates():
        for store, p in ads_files(data_dirs(sd)).items():
            for d, day in ads_by_date(ads_rows(p)).items():
                if d.startswith(month):
                    best[(store, d)] = (p, day)  # later shift folders win
    out = {}
    for (store, d), v in best.items():
        out.setdefault(store, {})[d] = v
    return out


def harvest_meta(month):
    mapping = meta_map()
    best = {}
    for sd in shift_dates():
        for p in meta_files(data_dirs(sd)):
            cov, recs = meta_extract(p, mapping)
            for d in cov:
                if d.startswith(month):
                    best[d] = (p, recs)
    return best


def cmd_month(args):
    month = month_of(args.month)
    ledger = [r for r in read_ledger() if str(r.get("target_date", "")).startswith(month)]
    ga4 = harvest_ga4(month)
    ads = harvest_ads(month)
    meta = harvest_meta(month)
    snaps = crm_snapshots(month)
    vendors = [v for v in (load_json(LP("vendor-watch.json"), {"rows": []}) or {}).get("rows", []) if v.get("month") == month]
    asks = (load_json(LP("asks.json"), {"asks": []}) or {}).get("asks", [])
    pack = {"schema": "month-pack.v1", "month": month, "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
            "how_to_use": ("A source covers the month for a store only when stores[STORE][source].coverage.complete is true "
                           "(GA4, Google Ads, Meta: every day of the month present; CRM: a month-to-date snapshot from the "
                           "first to the last day of the month). Otherwise pull that source live as before. Store keys are "
                           "the ai-team codes; the monthly-client-report registry code Atlas is ATLAS here."),
            "built_from": ["outputs/ai-team/{date}/data/ga4_{STORE}.json channel_daily_last7 (latest pull wins per day)",
                           "outputs/ai-team/{date}/data/{STORE}_campaign_daily_30d.* (latest shift wins per day)",
                           "outputs/ai-team/{date}/data/meta_campaigns*.json daily windows (latest shift wins per day)",
                           "outputs/ai-team/{date}/data/crm_mtd_{STORE}.json and CRM overrides in the shift ledger",
                           "outputs/ai-team/ledgers/shift-ledger.jsonl, vendor-watch.json, asks.json"],
            "stores": {}}
    through = []
    for s in STORES:
        st = {"name": STORE_NAMES[s]}
        # GA4
        days = ga4.get(s, {})
        g = {"coverage": coverage([d for d, v in days.items() if v[1]], month),
             "totals": {"sessions": 0, "engaged_sessions": 0, "key_events": 0, "organic_sessions": 0, "ai_sessions": 0},
             "channels": {}, "daily": [], "clean_key_events": {}, "key_events_notes": [], "sources": sorted({rel(v[0]) for v in days.values()})}
        for d in sorted(days):
            day = days[d][1]
            if not day:
                continue
            g["totals"]["sessions"] += day["sessions"]
            g["totals"]["engaged_sessions"] += day["engaged"]
            g["totals"]["key_events"] += day["key_events"]
            g["totals"]["organic_sessions"] += day["organic"]
            g["totals"]["ai_sessions"] += day["ai"]
            for c, v in day["channels"].items():
                cc = g["channels"].setdefault(c, {"sessions": 0, "engaged_sessions": 0, "key_events": 0})
                cc["sessions"] += v["sessions"]
                cc["engaged_sessions"] += v["engaged"]
                cc["key_events"] += v["key_events"]
            g["daily"].append({"date": d, "sessions": day["sessions"], "key_events": day["key_events"],
                               "organic": day["organic"], "ai": day["ai"]})
        for r in sorted((r for r in ledger if r["store"] == s), key=lambda r: (r["target_date"], r["date"])):
            if r.get("clean_key_events") is not None:
                g["clean_key_events"][r["target_date"]] = r["clean_key_events"]
            if r.get("key_events_note"):
                g["key_events_notes"].append("%s: %s" % (r["target_date"], r["key_events_note"]))
        g["totals"]["engagement_rate"] = round(g["totals"]["engaged_sessions"] / g["totals"]["sessions"], 4) if g["totals"]["sessions"] else None
        st["ga4"] = g
        through += g["coverage"]["days"][-1:]
        # Google Ads
        days = ads.get(s, {})
        a = {"coverage": coverage(days.keys(), month),
             "totals": {"cost": 0.0, "clicks": 0, "impressions": 0, "conversions": 0.0}, "campaigns": {}, "daily": [],
             "sources": sorted({rel(v[0]) for v in days.values()}),
             "note": "conversions are the account's primary conversion actions as exported; check the asks ledger for "
                     "stores whose conversions are page views"}
        for d in sorted(days):
            day = days[d][1]
            for k in ("cost", "clicks", "impressions", "conversions"):
                a["totals"][k] += day[k]
            for c, v in day["campaigns"].items():
                cc = a["campaigns"].setdefault(c, {"cost": 0.0, "clicks": 0, "impressions": 0, "conversions": 0.0})
                for k in cc:
                    cc[k] += v[k]
            a["daily"].append({"date": d, "cost": round(day["cost"], 2), "clicks": day["clicks"],
                               "conversions": round(day["conversions"], 2)})
        a["totals"] = {k: round(v, 2) for k, v in a["totals"].items()}
        a["campaigns"] = [dict(name=c, **{k: round(v, 2) for k, v in vals.items()})
                          for c, vals in sorted(a["campaigns"].items(), key=lambda kv: -kv[1]["cost"])]
        if not days:
            a["note"] = "no Google Ads export for this store in the shift folders"
        st["google_ads"] = a
        through += a["coverage"]["days"][-1:]
        # Meta (one account; a covered day with no campaigns for this store is a real zero)
        m = {"coverage": coverage(meta.keys(), month), "totals": {"spend": 0.0, "clicks": 0, "landing_page_views": 0},
             "campaigns": {}, "daily": [], "sources": sorted({rel(v[0]) for v in meta.values()}),
             "note": "split by store from campaign names plus ledgers/meta-store-map.json; reach is not summed"}
        for d in sorted(meta):
            md = meta_store_day(meta[d][1], s, d)
            m["totals"]["spend"] += md["spend"]
            m["totals"]["clicks"] += md["clicks"]
            m["totals"]["landing_page_views"] += md["lpv"]
            for c, v in md["campaigns"].items():
                cc = m["campaigns"].setdefault(c, {"spend": 0.0, "clicks": 0, "lpv": 0})
                for k in cc:
                    cc[k] += v[k]
            m["daily"].append({"date": d, "spend": round(md["spend"], 2), "clicks": md["clicks"], "lpv": md["lpv"]})
        m["totals"]["spend"] = round(m["totals"]["spend"], 2)
        m["campaigns"] = [dict(name=c, spend=round(v["spend"], 2), clicks=v["clicks"], landing_page_views=v["lpv"])
                          for c, v in sorted(m["campaigns"].items(), key=lambda kv: -kv[1]["spend"])]
        st["meta"] = m
        through += m["coverage"]["days"][-1:]
        # CRM: latest month-to-date snapshot
        cands = [(n["period_end"] or "", 1, rel(p), n) for (_sd, p, n) in snaps if n["store"] == s]
        for r in ledger:
            if r["store"] == s and r.get("crm_period_end") and str(r["crm_period_end"]).startswith(month) \
                    and r.get("sources", {}).get("crm") == "override":
                n = {"store": s, "crm": None, "report": None, "source_file": None, "period_start": month + "-01",
                     "period_end": r["crm_period_end"], "source_kind": None, "by_source": [], "notes": [],
                     "headline": {"leads": r.get("crm_leads"), "good_leads": r.get("crm_good_leads"),
                                  "appointments": r.get("crm_appointments"), "shows": r.get("crm_shows"),
                                  "sold": r.get("crm_sold"), "cost": r.get("crm_cost"),
                                  "live_vendor_cost": r.get("crm_live_vendor_cost")}}
                srcs = [x for x in r["sources"].get("overrides", []) if x.startswith("crm")]
                files = sorted(set(x.split(": ", 1)[-1].split(", ")[0] for x in srcs))
                cands.append((r["crm_period_end"], 0, "; ".join(files) + " (hand-entered, see shift-overrides.json)", n))
        c = {"coverage": {"period_start": None, "period_end": None, "complete": False}, "headline": None,
             "by_source": [], "source": None}
        if cands:
            pe, _pri, src, n = sorted(cands, key=lambda x: (x[0], x[1]))[-1]
            days_m = month_days(month)
            c = {"coverage": {"period_start": n.get("period_start"), "period_end": pe,
                              "complete": n.get("period_start") == days_m[0] and pe == days_m[-1]},
                 "crm": n.get("crm"), "report": n.get("report"), "source_file": n.get("source_file"),
                 "source_kind": n.get("source_kind"), "headline": n["headline"], "by_source": n["by_source"],
                 "notes": n.get("notes", []), "source": src}
            through.append(pe)
        st["crm"] = c
        st["vendor_watch"] = [{k: v.get(k) for k in ("id", "vendor", "status", "mtd_spend", "mtd_leads", "mtd_sold",
                                                    "as_of", "first_flagged", "note")} for v in vendors if v["store"] == s]
        st["open_asks"] = [{"id": x["id"], "label": x["label"], "owner": x["owner"], "first_raised": x["first_raised"]}
                           for x in asks if x["status"] == "open" and x["store"] in (s, "ALL")
                           and not str(x.get("owner", "")).startswith("team:")]
        st["wins"] = [{"id": x["id"], "date": x.get("closed_date"), "win": x.get("win"), "evidence": x.get("closure_evidence")}
                      for x in asks if x.get("win") and str(x.get("closed_date") or "").startswith(month) and x["store"] in (s, "ALL")]
        st["ledger_rows"] = len([r for r in ledger if r["store"] == s])
        pack["stores"][s] = st
    pack["through"] = max(through) if through else None
    out_json = LP("month-pack-%s.json" % month)
    save_json(out_json, pack)
    save_text(LP("month-pack-%s.md" % month), month_pack_md(pack))
    print("month %s: wrote %s and .md, through %s." % (month, rel(out_json), pack["through"]))
    for s in STORES:
        st = pack["stores"][s]
        print("  %-5s ga4 %2d/%d days, gads %2d, meta %2d, crm %s%s" % (
            s, st["ga4"]["coverage"]["count"], st["ga4"]["coverage"]["days_in_month"],
            st["google_ads"]["coverage"]["count"], st["meta"]["coverage"]["count"],
            st["crm"]["coverage"]["period_end"] or "none",
            ", COMPLETE: " + ", ".join(k for k in ("ga4", "google_ads", "meta", "crm") if st[k]["coverage"]["complete"])
            if any(st[k]["coverage"]["complete"] for k in ("ga4", "google_ads", "meta", "crm")) else ""))


def _span(cov):
    if not cov["count"]:
        return "no days"
    return "%d of %d days (%s to %s)%s" % (cov["count"], cov["days_in_month"], cov["first"], cov["last"],
                                          ", complete" if cov["complete"] else ", not complete")


def month_pack_md(pack):
    L = ["---", "type: ai-team-month-pack", "date: %s" % pack["generated_at"][:10], "status: generated",
         "tags: [ai-team, ledgers, monthly-report]", "---", "",
         "# AI team month pack, %s" % pack["month"], "",
         "Built by `ledgers.py month` from the night-shift folders, month to date through %s. " % pack["through"]
         + "A source covers the month only when its coverage is complete; monthly-client-report pulls live otherwise.", ""]
    for s, st in pack["stores"].items():
        g, a, m, c = st["ga4"], st["google_ads"], st["meta"], st["crm"]
        L.append("## [[%s]] (%s)" % (s if s != "ATLAS" else "Atlas", st["name"]))
        L.append("- GA4: %s. Sessions %s, key events %s, Organic Search %s, AI Assistant %s." % (
            _span(g["coverage"]), fmt_num(g["totals"]["sessions"]), fmt_num(g["totals"]["key_events"]),
            fmt_num(g["totals"]["organic_sessions"]), fmt_num(g["totals"]["ai_sessions"])))
        if g["clean_key_events"]:
            L.append("  - Clean key events (Kobe): " + ", ".join("%s %s" % (d, v) for d, v in sorted(g["clean_key_events"].items())))
        for n in g["key_events_notes"][-2:]:
            L.append("  - Key events caveat: " + n)
        if a["coverage"]["count"]:
            L.append("- Google Ads: %s. Cost %s, clicks %s, conversions %s." % (
                _span(a["coverage"]), fmt_money(a["totals"]["cost"]), fmt_num(a["totals"]["clicks"]),
                fmt_num(a["totals"]["conversions"])))
        else:
            L.append("- Google Ads: no export in the shift folders.")
        L.append("- Meta: %s. Spend %s, clicks %s, landing page views %s." % (
            _span(m["coverage"]), fmt_money(m["totals"]["spend"]), fmt_num(m["totals"]["clicks"]),
            fmt_num(m["totals"]["landing_page_views"])))
        if c.get("headline"):
            h = c["headline"]
            L.append("- CRM: %s to %s%s. Leads %s, sold %s, cost %s. Source: %s." % (
                c["coverage"]["period_start"], c["coverage"]["period_end"],
                ", complete" if c["coverage"]["complete"] else ", not complete", fmt_num(h.get("leads")),
                fmt_num(h.get("sold")), fmt_money(h.get("cost")), c.get("source")))
        else:
            L.append("- CRM: no snapshot this month.")
        if st["vendor_watch"]:
            L.append("- Vendor watch: " + "; ".join("%s %s %s, %s MTD, %s leads" % (
                v["id"], v["vendor"], v["status"], fmt_money(v["mtd_spend"]), fmt_num(v["mtd_leads"]))
                for v in st["vendor_watch"]))
        if st["open_asks"]:
            L.append("- Open asks: " + ", ".join("%s %s" % (x["id"], x["label"]) for x in st["open_asks"]))
        L.append("- Wins this month: " + ("; ".join("%s %s (%s)" % (w["date"], w["win"], w["id"]) for w in st["wins"])
                                           if st["wins"] else "none closed with a win yet"))
        L.append("")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- Vendor Waste Watch

def vendor_load():
    return load_json(LP("vendor-watch.json"), None) or {
        "_about": ("Vendor Waste Watch. One row per store, vendor and month for a lead vendor billing with zero or "
                   "near-zero leads. Status: open (flagged, unconfirmed by the store), confirmed-live, cut, kept, "
                   "closed (not live, or no longer a concern). Rows stay open and unconfirmed until the store "
                   "confirms the vendor is live."), "rows": []}


def next_id(rows, prefix):
    n = [int(r["id"][len(prefix):]) for r in rows if str(r.get("id", "")).startswith(prefix) and r["id"][len(prefix):].isdigit()]
    return "%s%d" % (prefix, (max(n) if n else 0) + 1)


def vendor_find(rows, store, vendor, month):
    key = re.sub(r"\s+", " ", vendor.strip().lower())
    for r in rows:
        if r["store"] == store and r["month"] == month and re.sub(r"\s+", " ", r["vendor"].strip().lower()) == key:
            return r
    return None


def vendor_upsert(data, store, vendor, month, date, point=None, status=None, note=None, bench=None, ask=None,
                  first_flagged=None):
    rows = data["rows"]
    row = vendor_find(rows, store, vendor, month)
    created = False
    if row is None:
        prior = [r for r in rows if r["store"] == store and r["vendor"].lower() == vendor.lower() and r["month"] < month]
        row = {"id": next_id(rows, "V"), "store": store, "vendor": vendor, "month": month, "status": "open",
               "first_flagged": first_flagged or (min(r["first_flagged"] for r in prior) if prior else date),
               "last_seen": date, "mtd_spend": None, "mtd_leads": None, "mtd_sold": None, "as_of": None,
               "source_file": None, "note": None, "bench_category": None, "ask_id": None,
               "history": [], "status_history": [{"date": date, "status": "open", "note": "flagged"}]}
        rows.append(row)
        created = True
    if point:
        row["history"] = [h for h in row["history"] if h.get("as_of") != point.get("as_of")] + [point]
        row["history"].sort(key=lambda h: (h.get("as_of") or "", h.get("date") or ""))
        last = row["history"][-1]
        row.update({"mtd_spend": last.get("spend"), "mtd_leads": last.get("leads"), "mtd_sold": last.get("sold"),
                    "as_of": last.get("as_of"), "source_file": last.get("source")})
    row["last_seen"] = max(row.get("last_seen") or date, date)
    if status and status != row["status"]:
        if status not in VENDOR_STATUSES:
            die("--status must be one of " + ", ".join(VENDOR_STATUSES))
        row["status"] = status
        row["status_history"].append({"date": date, "status": status, "note": note})
    if note:
        row["note"] = note
    if bench:
        row["bench_category"] = bench
    if ask:
        row["ask_id"] = ask
    return row, created


def vendor_seed_rows():
    run2 = "outputs/ai-team/2026-09-19/run2/nick.md"
    f22 = "outputs/ai-team/2026-09-22/data/crm_mtd_NOI.json (VinSolutions Report-1087.xlsx)"
    n23 = "outputs/ai-team/2026-09-23/nick.md (VinSolutions Report-7275.xlsx)"
    def pts(a, b, c, d):
        out = []
        if a is not None:
            out.append({"date": "2026-09-19", "as_of": "2026-09-17", "spend": a, "leads": 0, "sold": 0,
                        "source": "VinSolutions Report-6543.xlsx as cited in " + run2})
        out += [{"date": "2026-09-19", "as_of": "2026-09-18", "spend": b, "leads": 0, "sold": 0,
                 "source": "VinSolutions Report-7897.xlsx, " + run2},
                {"date": "2026-09-22", "as_of": "2026-09-21", "spend": c, "leads": 0, "sold": 0, "source": f22},
                {"date": "2026-09-23", "as_of": "2026-09-22", "spend": d, "leads": 0, "sold": 0, "source": n23}]
        return out
    drew = ("Drew in Slack 2026-09-19 (outputs/ai-team/2026-09-19/run2/shift-log.md, 11:10): not active at NOI, "
            "VinSolutions cost page is stale, ignore the cost. The cost page still needs cleaning.")
    return [
        ("Auto Credit Express", pts(3000, 3150, 3650, 3850), "open", None, "third_party",
         "score-leads would class this name as website by default; set to third_party as a finance-referral lead vendor"),
        ("TrueCar", pts(2340, 2457, 2847, 3003), "open", None, "third_party", None),
        ("Costco", pts(None, 945, 1095, 1155), "closed", drew.replace("not active at NOI", "likely not used at NOI"), None, None),
        ("Pownder", pts(None, 1638, 1898, 2002), "closed", drew, None, None),
        ("Radio", pts(None, 1638, 1898, 2002), "closed", drew, None, None),
    ]


def cmd_vendor_seed(args):
    path = LP("vendor-watch.json")
    if os.path.exists(path) and not args.force:
        die("vendor-watch.json already exists; use --force to rebuild the seed rows (other rows are kept)")
    data = vendor_load()
    if args.force:
        names = {v[0].lower() for v in vendor_seed_rows()}
        data["rows"] = [r for r in data["rows"] if not (r["store"] == "NOI" and r["month"] == "2026-09"
                                                         and r["vendor"].lower() in names)]
    for vendor, points, status, note, bench, bench_note in vendor_seed_rows():
        row, _ = vendor_upsert(data, "NOI", vendor, "2026-09", "2026-09-19", bench=bench, first_flagged="2026-09-19",
                               ask="A2" if status == "open" else None)
        for p in points:
            vendor_upsert(data, "NOI", vendor, "2026-09", p["date"], point=p)
        if status != "open":
            vendor_upsert(data, "NOI", vendor, "2026-09", "2026-09-19", status=status, note=note)
        if bench_note:
            row["bench_note"] = bench_note
    save_json(path, data)
    corr = load_json(LP("crm-corrections.json"), {"corrections": []})
    if not any(c.get("shift") == "2026-09-22" and c.get("source") == "CarFax" for c in corr["corrections"]):
        corr["_about"] = "Known errors in saved crm_mtd files, applied when the ledgers read them. The files stay as written."
        corr["corrections"].append({"shift": "2026-09-22", "store": "NOI", "source": "CarFax", "field": "cost", "value": 0,
                                    "reason": "3,150.66 was CarFax Total Front Gross mislabeled as cost; the report's "
                                              "Total Cost column reads 0 both nights",
                                    "evidence": "outputs/ai-team/2026-09-23/nick.md, NOI vendor cost note"})
        save_json(LP("crm-corrections.json"), corr)
    open_rows = [r for r in data["rows"] if r["status"] == "open"]
    print("vendor seed: %d rows (%d open unconfirmed, %d closed). NOI Auto Credit Express + TrueCar MTD: "
          "$5,340 thru 9/17, $5,607 thru 9/18, $6,497 thru 9/21, $6,853 thru 9/22, zero leads. 1 CRM correction on file."
          % (len(data["rows"]), len(open_rows), len(data["rows"]) - len(open_rows)))


def flagged(src):
    cost, leads = src.get("cost"), src.get("leads")
    if not cost or cost <= 0 or leads is None:
        return False
    return leads == 0 or (leads <= NEAR_ZERO_LEADS and cost >= NEAR_ZERO_COST)


def cmd_vendor_scan(args):
    date = iso(args.date)
    files = crm_files(data_dirs(date))
    if not files:
        print("vendor scan %s: no crm_mtd_*.json in outputs/ai-team/%s/data, nothing to do" % (date, date))
        return
    data = vendor_load()
    new, upd, cleared = [], [], []
    for store, p in sorted(files.items()):
        n = crm_normalize(load_json(p, {}), date, store)
        if n.get("source_kind") == "category" or not n.get("period_end"):
            continue
        month = n["period_end"][:7]
        for src in n["by_source"]:
            existing = vendor_find(data["rows"], store, src["source"] or "", month)
            if not flagged(src) and existing is None:
                continue
            point = {"date": date, "as_of": n["period_end"], "spend": src.get("cost"), "leads": src.get("leads"),
                     "sold": src.get("sold"), "source": "%s (%s)" % (rel(p), n.get("source_file") or "CRM report")}
            row, created = vendor_upsert(data, store, src["source"], month, date, point=point)
            (new if created else upd).append("%s %s" % (row["id"], row["vendor"]))
            if not flagged(src):
                cleared.append("%s %s now %s leads" % (row["id"], row["vendor"], fmt_num(src.get("leads"))))
    save_json(LP("vendor-watch.json"), data)
    print("vendor scan %s: %d file(s), %d new row(s)%s, %d updated%s." % (
        date, len(files), len(new), " (" + ", ".join(new) + ")" if new else "", len(upd),
        "; no longer zero-lead: " + ", ".join(cleared) if cleared else ""))


def cmd_vendor_update(args):
    date = iso(args.date)
    store = store_arg(args.store)
    month = month_of(args.month) if args.month else (iso(args.as_of)[:7] if args.as_of else date[:7])
    data = vendor_load()
    point = None
    if any(v is not None for v in (args.spend, args.leads, args.sold)):
        point = {"date": date, "as_of": iso(args.as_of) if args.as_of else date,
                 "spend": money(args.spend), "leads": num(args.leads), "sold": num(args.sold),
                 "source": text_arg(args, "source", required=True)}
    row, created = vendor_upsert(data, store, args.vendor.strip(), month, date, point=point, status=args.status,
                                 note=text_arg(args, "note"), bench=args.bench_category, ask=args.ask)
    save_json(LP("vendor-watch.json"), data)
    print("vendor update: %s %s %s %s %s, %s MTD, %s leads, %s sold, as of %s." % (
        "created" if created else "updated", row["id"], store, row["vendor"], row["status"],
        fmt_money(row["mtd_spend"]), fmt_num(row["mtd_leads"]), fmt_num(row["mtd_sold"]), row["as_of"] or "n/a"))


def vendor_line(r, ref=None):
    ref = ref or r.get("last_seen")
    days = (dt.date.fromisoformat(ref) - dt.date.fromisoformat(r["first_flagged"])).days if ref else None
    st = "open (unconfirmed)" if r["status"] == "open" else r["status"]
    return "%s %s %s, %s: %s MTD, %s leads, %s sold as of %s. Flagged %s, %s days. Source: %s" % (
        r["id"], r["store"], r["vendor"], st, fmt_money(r["mtd_spend"]), fmt_num(r["mtd_leads"]),
        fmt_num(r["mtd_sold"]), r["as_of"] or "n/a", r["first_flagged"], days, r["source_file"])


def cmd_vendor_list(args):
    rows = vendor_load()["rows"]
    if args.store:
        rows = [r for r in rows if r["store"] == store_arg(args.store)]
    if args.month:
        rows = [r for r in rows if r["month"] == month_of(args.month)]
    if not args.all:
        rows = [r for r in rows if r["status"] in ("open", "confirmed-live")]
    for r in rows:
        print("- " + vendor_line(r, iso(args.date) if args.date else None))
    print("vendor list: %d row(s)%s" % (len(rows), "" if args.all else " open or confirmed-live (--all for every row)"))


def load_bench():
    """NADA close-rate table and source-type classifier from the score-leads skill, or None."""
    cands = sorted(glob.glob(os.path.expanduser(
        "~/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/*/*/skills/score-leads/reference/nada_benchmarks.json")),
        key=os.path.getmtime, reverse=True)
    cands.append(os.path.expanduser("~/Desktop/Skills/skills/score-leads/reference/nada_benchmarks.json"))
    for p in cands:
        try:
            data = load_json(p, None)
        except (ValueError, OSError):
            continue
        if not data or "close_rate_benchmarks" not in data:
            continue
        patterns, pfrom, min_leads = None, "embedded copy (score_leads.py not parsed)", 10
        py = os.path.join(os.path.dirname(os.path.dirname(p)), "score_leads.py")
        try:
            tree = ast.parse(open(py, encoding="utf-8").read())
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    names = [getattr(t, "id", None) for t in node.targets]
                    if "BENCHMARK_CATEGORY_PATTERNS" in names:
                        patterns, pfrom = ast.literal_eval(node.value), py
                    if "MIN_BENCHMARK_LEADS" in names:
                        min_leads = ast.literal_eval(node.value)
        except (OSError, SyntaxError, ValueError):
            pass
        return {"path": p, "data": data, "patterns": patterns or EMBEDDED_PATTERNS, "patterns_from": pfrom,
                "min_leads": min_leads, "version": data.get("_meta", {}).get("version"),
                "updated": data.get("_meta", {}).get("last_updated")}
    return None


def bench_for(bench, source, tier, override=None):
    if not bench:
        return {"category": override, "rate": None, "label": "benchmark not loaded", "source": None}
    cat = override
    if not cat:
        name = (source or "").lower()
        cat = "website"
        for c, pats in bench["patterns"]:
            if any(p in name for p in pats):
                cat = c
                break
    cdef = bench["data"]["close_rate_benchmarks"]["categories"].get(cat) or {}
    rate = cdef.get(tier) if tier in ("luxury", "mainstream", "powersports") else None
    label = "%s, %s: %s" % (cdef.get("label", cat), tier, ("%.0f%%" % (rate * 100)) if rate is not None else
                           ("not applicable (non-auto)" if tier == "non-auto" else "no benchmark"))
    return {"category": cat, "rate": rate, "label": label, "support": cdef.get("support"), "source": cdef.get("source")}


def verdict(e, bench, min_leads):
    st, spend, leads, sold = e["status"], e["spend"], e["leads"], e["sold"]
    if st == "closed":
        return "clean up the cost page (not live per Drew)" if "Drew" in (e.get("note") or "") else "closed"
    if st == "cut":
        return "cut (done)"
    if st == "kept":
        return "keep (Drew's call)"
    if spend and spend > 0 and (leads or 0) == 0:
        return "cut" if st == "confirmed-live" else "confirm it is live, then cut"
    if not leads:
        return "no leads, no cost"
    close = (sold or 0) / leads
    if leads < min_leads:
        return "low volume, review next month"
    if bench["rate"] is None:
        return "keep (no benchmark for this source type)"
    if close <= bench["rate"] * (1 - BENCH_BAND):
        return "review: closes below benchmark"
    return "keep"


def cmd_vendor_month_end(args):
    month = month_of(args.month)
    bench = load_bench()
    rows = [r for r in vendor_load()["rows"] if r["month"] == month]
    snaps = {}
    for sd, p, n in crm_snapshots(month):
        if n.get("source_kind") == "category":
            continue
        if n["store"] not in snaps or (n["period_end"] or "") >= (snaps[n["store"]][2]["period_end"] or ""):
            snaps[n["store"]] = (sd, p, n)
    yard = None
    if bench:
        y = bench["data"].get("cost_yardsticks", {}).get("ad_cost_per_new_unit_usd", {})
        if y.get("value"):
            yard = {"value": y["value"], "source": y.get("source")}
    out = {"schema": "vendor-month-end.v1", "month": month, "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
           "benchmark": ({"file": bench["path"], "version": bench["version"], "last_updated": bench["updated"],
                          "classifier": bench["patterns_from"], "min_leads": bench["min_leads"],
                          "cost_per_sale_yardstick": yard} if bench else "benchmark not loaded"),
           "rules": ["zero leads on real cost: confirm it is live, then cut (cut once the store confirms it is live)",
                     "closes 10%% or more below its NADA source-type benchmark on %s+ leads: review" % (bench["min_leads"] if bench else 10),
                     "close rate uses good leads when the CRM reports them, else total leads",
                     "closed rows the store or Drew said are not live: clean up the CRM cost page"],
           "stores": {}}
    for s in STORES:
        entries = []
        seen = set()
        snap = snaps.get(s)
        tier = STORE_TIER[s]
        for r in [r for r in rows if r["store"] == s]:
            src = None
            if snap:
                src = next((x for x in snap[2]["by_source"] if (x["source"] or "").lower() == r["vendor"].lower()), None)
            use_snap = src is not None and (snap[2]["period_end"] or "") > (r.get("as_of") or "")
            e = {"vendor": r["vendor"], "id": r["id"], "status": r["status"], "note": r.get("note"),
                 "spend": src["cost"] if use_snap else r["mtd_spend"],
                 "leads": ((src.get("good_leads") if src.get("good_leads") is not None else src.get("leads")) if use_snap else r["mtd_leads"]),
                 "sold": src["sold"] if use_snap else r["mtd_sold"],
                 "as_of": snap[2]["period_end"] if use_snap else r["as_of"],
                 "source": rel(snap[1]) if use_snap else r["source_file"], "bench_override": r.get("bench_category")}
            entries.append(e)
            seen.add(r["vendor"].lower())
        if snap:
            for x in snap[2]["by_source"]:
                if (x["source"] or "").lower() in seen or not x.get("cost"):
                    continue
                entries.append({"vendor": x["source"], "id": None, "status": "not flagged", "note": None,
                                "spend": x["cost"], "leads": x["good_leads"] if x.get("good_leads") is not None else x["leads"],
                                "sold": x["sold"], "as_of": snap[2]["period_end"], "source": rel(snap[1]), "bench_override": None})
        for e in entries:
            b = bench_for(bench, e["vendor"], tier, e.pop("bench_override"))
            if e["status"] == "closed":
                b = {"category": None, "rate": None, "label": "n/a (not live)", "source": None}
            e["cost_per_lead"] = round(e["spend"] / e["leads"], 2) if e["spend"] and e["leads"] else None
            e["cost_per_sale"] = round(e["spend"] / e["sold"], 2) if e["spend"] and e["sold"] else None
            e["close_rate"] = round(e["sold"] / e["leads"], 4) if e["leads"] and e["sold"] is not None else None
            e["benchmark"] = b
            e["verdict"] = verdict(e, b, bench["min_leads"] if bench else 10)
            if yard and e["cost_per_sale"] and e["cost_per_sale"] > yard["value"]:
                e["verdict"] += "; cost per sale above the NADA ad cost per new unit"
        entries.sort(key=lambda e: -(e["spend"] or 0))
        out["stores"][s] = {"tier": tier, "crm_snapshot": rel(snap[1]) if snap else None,
                            "crm_period_end": snap[2]["period_end"] if snap else None, "vendors": entries}
    save_json(LP("vendor-month-end-%s.json" % month), out)
    save_text(LP("vendor-month-end-%s.md" % month), vendor_month_end_md(out, bench))
    n = sum(len(v["vendors"]) for v in out["stores"].values())
    cut = sum(1 for v in out["stores"].values() for e in v["vendors"] if e["verdict"].startswith(("cut", "confirm")))
    print("vendor month-end %s: %d vendor line(s) across %d store(s), %d cut or confirm-then-cut. Benchmark: %s. Wrote %s and .md."
          % (month, n, sum(1 for v in out["stores"].values() if v["vendors"]), cut,
             ("%s (v%s, updated %s)" % (rel(bench["path"]) if bench["path"].startswith(ROOT) else bench["path"].replace(os.path.expanduser("~"), "~"),
                                         bench["version"], bench["updated"])) if bench else "benchmark not loaded",
             rel(LP("vendor-month-end-%s.json" % month))))


def vendor_month_end_md(out, bench):
    L = ["---", "type: ai-team-vendor-month-end", "date: %s" % out["generated_at"][:10], "status: generated",
         "tags: [ai-team, ledgers, vendor-watch]", "---", "",
         "# Vendor keep-or-cut list, %s" % out["month"], ""]
    if bench:
        L.append("Close rates graded against the NADA and industry table in the score-leads skill (`%s`, version %s, "
                 "updated %s); source types from `%s`. Cost per sale yardstick: %s." % (
                     os.path.basename(bench["path"]), bench["version"], bench["updated"],
                     os.path.basename(bench["patterns_from"]) if os.path.sep in bench["patterns_from"] else bench["patterns_from"],
                     ("NADA ad cost per new unit $%s (%s)" % (out["benchmark"]["cost_per_sale_yardstick"]["value"],
                                                            out["benchmark"]["cost_per_sale_yardstick"]["source"]))
                     if out["benchmark"].get("cost_per_sale_yardstick") else "not loaded"))
    else:
        L.append("Benchmark not loaded: the score-leads nada_benchmarks.json was not found, so no close rate is graded.")
    L.append("")
    for s, st in out["stores"].items():
        if not st["vendors"]:
            continue
        L.append("## [[%s]]" % (s if s != "ATLAS" else "Atlas"))
        L.append("CRM snapshot: %s, through %s." % (st["crm_snapshot"] or "none", st["crm_period_end"] or "n/a"))
        L.append("")
        L.append("| Vendor | Status | MTD spend | Leads | Sold | Cost per lead | Cost per sale | Close | Benchmark | Verdict |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for e in st["vendors"]:
            L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                e["vendor"], e["status"], fmt_money(e["spend"]), fmt_num(e["leads"]), fmt_num(e["sold"]),
                fmt_money(e["cost_per_lead"]), fmt_money(e["cost_per_sale"]),
                ("%.1f%%" % (e["close_rate"] * 100)) if e["close_rate"] is not None else "n/a",
                e["benchmark"]["label"], e["verdict"]))
        L.append("")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- Asks and wins

def asks_load():
    return load_json(LP("asks.json"), None) or {
        "_about": ("Asks and wins. Every ask the team raises, from the day raised to the day closed. Owner is Drew, "
                   "'store: {role}' or 'team: {player}'. needs_store asks that sit 3+ business days get a GM-level "
                   "request draft in outputs/ai-team/asks/requests/ for Drew to forward. A closed ask with a 'win' is a "
                   "dated, sourced win for the monthly report."), "asks": []}


def ask_get(data, aid):
    for a in data["asks"]:
        if a["id"].upper() == str(aid).upper():
            return a
    die("no ask %s in asks.json" % aid)


def cmd_asks_add(args):
    date = iso(args.date)
    data = asks_load()
    a = {"id": next_id(data["asks"], "A"), "store": store_arg(args.store, allow_all=True),
         "owner": text_arg(args, "owner", required=True), "needs_store": bool(args.needs_store),
         "label": text_arg(args, "label", required=True), "ask": text_arg(args, "ask", required=True),
         "evidence": text_arg(args, "evidence", required=True), "if_skipped": text_arg(args, "if_skipped"),
         "done_when": text_arg(args, "done_when"), "first_raised": iso(args.first_raised) if args.first_raised else date,
         "last_raised": date, "raised": sorted({date, iso(args.first_raised) if args.first_raised else date}),
         "status": "open", "closed_date": None, "closure_evidence": None, "win": None, "withdrawn_reason": None,
         "vendor_ids": [v.strip() for v in (args.vendors or "").split(",") if v.strip()], "requests": [],
         "source": text_arg(args, "source"), "history": [{"date": date, "action": "added"}]}
    data["asks"].append(a)
    save_json(LP("asks.json"), data)
    print("asks add: %s %s '%s' raised %s, owner %s%s." % (a["id"], a["store"], a["label"], a["first_raised"],
                                                          a["owner"], ", needs the store" if a["needs_store"] else ""))


def cmd_asks_update(args):
    date = iso(args.date)
    data = asks_load()
    a = ask_get(data, args.id)
    changed = []
    for f in ("ask", "evidence", "owner", "label", "if_skipped", "done_when"):
        v = text_arg(args, f)
        if v is not None and v != a.get(f):
            if f == "evidence" and a.get("evidence"):
                a.setdefault("evidence_history", []).append({"date": a["last_raised"], "evidence": a["evidence"]})
            a[f] = v
            changed.append(f)
    if args.store:
        a["store"] = store_arg(args.store, allow_all=True)
        changed.append("store")
    if args.needs_store is not None:
        a["needs_store"] = args.needs_store == "yes"
        changed.append("needs_store")
    note = text_arg(args, "note")
    if not args.no_raise and a["status"] == "open":
        a["last_raised"] = max(a["last_raised"], date)
        a["raised"] = sorted(set(a["raised"]) | {date})
    a["history"].append({"date": date, "action": "raised" if not args.no_raise else "edited",
                         "changed": changed, "note": note})
    save_json(LP("asks.json"), data)
    print("asks update: %s %s, %s, open %d days%s." % (a["id"], a["label"], a["status"],
                                                      (dt.date.fromisoformat(date) - dt.date.fromisoformat(a["first_raised"])).days,
                                                      ", changed " + ", ".join(changed) if changed else ""))


def cmd_asks_close(args):
    date = iso(args.date)
    data = asks_load()
    a = ask_get(data, args.id)
    if a["status"] != "open":
        die("%s is already %s" % (a["id"], a["status"]))
    a.update({"status": "closed", "closed_date": date, "closure_evidence": text_arg(args, "evidence", required=True),
              "win": text_arg(args, "win")})
    a["history"].append({"date": date, "action": "closed"})
    save_json(LP("asks.json"), data)
    print("asks close: %s %s closed %s after %d days%s." % (
        a["id"], a["label"], date, (dt.date.fromisoformat(date) - dt.date.fromisoformat(a["first_raised"])).days,
        ", win recorded for the monthly report" if a["win"] else ""))


def cmd_asks_withdraw(args):
    date = iso(args.date)
    data = asks_load()
    a = ask_get(data, args.id)
    if a["status"] != "open":
        die("%s is already %s" % (a["id"], a["status"]))
    a.update({"status": "withdrawn", "closed_date": date, "withdrawn_reason": text_arg(args, "reason", required=True)})
    a["history"].append({"date": date, "action": "withdrawn"})
    save_json(LP("asks.json"), data)
    print("asks withdraw: %s %s withdrawn %s." % (a["id"], a["label"], date))


def cmd_asks_list(args):
    data = asks_load()
    rows = data["asks"]
    st = args.status or "open"
    if st != "all":
        rows = [a for a in rows if a["status"] == st]
    if args.store:
        s = store_arg(args.store, allow_all=True)
        rows = [a for a in rows if a["store"] in (s, "ALL")]
    for a in rows:
        extra = ""
        if a["status"] == "closed":
            extra = " Closed %s: %s" % (a["closed_date"], a["closure_evidence"])
        elif a["status"] == "withdrawn":
            extra = " Withdrawn %s: %s" % (a["closed_date"], a["withdrawn_reason"])
        print("- %s [%s] %s, %s. Owner %s%s. Raised %s to %s (%d times).%s" % (
            a["id"], a["store"], a["label"], a["status"], a["owner"], ", needs the store" if a["needs_store"] else "",
            a["first_raised"], a["last_raised"], len(a["raised"]), extra))
    print("asks list: %d %s ask(s)" % (len(rows), st))


def aging_blocks(data, date):
    older = [a for a in data["asks"] if a["status"] == "open" and a["first_raised"] < date]
    older.sort(key=lambda a: (a["first_raised"], int(a["id"][1:])))
    closed = [a for a in data["asks"] if a["status"] in ("closed", "withdrawn") and a.get("closed_date") == date]
    due = []
    L = ["### Asks aging", ""]
    if not older:
        L.append("- None carried over.")
    for a in older:
        days = (dt.date.fromisoformat(date) - dt.date.fromisoformat(a["first_raised"])).days
        bd = business_days(a["first_raised"], date)
        tag = ""
        if a["needs_store"]:
            drafted = [r for r in a.get("requests", []) if r.get("date")]
            if drafted:
                tag = ", GM request drafted %s" % drafted[-1]["date"]
            elif bd >= GM_REQUEST_BUSINESS_DAYS:
                tag = ", GM request due"
                due.append(a)
        L.append("- %s, %s, open %d day%s, %s%s" % (a["id"], a["label"], days, "" if days == 1 else "s",
                                                    a["owner"], tag))
    L += ["", "### Closed tonight", ""]
    if not closed:
        L.append("- Nothing closed tonight.")
    for a in closed:
        if a["status"] == "closed":
            L.append("- %s, %s: closed. %s%s" % (a["id"], a["label"], a["closure_evidence"],
                                                 (" Win: " + a["win"]) if a.get("win") else ""))
        else:
            L.append("- %s, %s: withdrawn. %s" % (a["id"], a["label"], a["withdrawn_reason"]))
    L += ["", "### GM requests due", ""]
    if not due:
        L.append("- None due.")
    for a in due:
        L.append("- %s, %s: %d business days waiting on the store. Draft with `ledgers.py asks request --id %s --date %s`."
                 % (a["id"], a["label"], business_days(a["first_raised"], date), a["id"], date))
    new = [a["id"] for a in data["asks"] if a["first_raised"] == date and a["status"] == "open"]
    return "\n".join(L) + "\n", older, closed, due, new


def cmd_asks_aging(args):
    date = iso(args.date)
    text, older, closed, due, new = aging_blocks(asks_load(), date)
    if args.out:
        save_text(os.path.join(ROOT, args.out) if not os.path.isabs(args.out) else args.out, text)
    print(text)
    print("asks aging %s: %d carried over, %d closed or withdrawn tonight, %d GM request(s) due, new tonight: %s%s"
          % (date, len(older), len(closed), len(due), ", ".join(new) or "none",
             (". Wrote " + args.out) if args.out else ""))


def request_text(a, date):
    s = a["store"]
    link = "Atlas" if s == "ATLAS" else s
    bd = business_days(a["first_raised"], date)
    return "\n".join([
        "---", "type: gm-request", "date: %s" % date, "status: draft", "tags: [ai-team, asks, gm-request]",
        "project: %s" % link, "ask: %s" % a["id"], "---", "",
        "# %s: %s" % (STORE_NAMES.get(s, s), a["label"]), "",
        "> [!note] Draft for [[Drew Moon]] to edit and forward. Nothing was sent.", "",
        "**To:** General Manager, [[%s]] (%s)" % (link, STORE_NAMES.get(s, s)),
        "**From:** [[Drew Moon]], [[DigitalCLIQ]]",
        "**Re:** %s" % a["label"], "",
        "%% Magic: rewrite the paragraphs below for a GM reading on a phone. Plain words, every number dated and "
        "sourced, no em dashes, no customer data, no one named who is not in the store README. Then delete this line. %%", "",
        "We need one thing from the store: %s" % a["ask"], "",
        "Why it matters: %s" % a["evidence"], "",
        "If it waits: %s" % (a.get("if_skipped") or "%% Magic: what it costs the store to wait, one sentence %%"), "",
        "What done looks like: %s" % (a.get("done_when") or "%% Magic: how we will know it is done, one sentence %%"), "",
        ("Who at the store: the store's %s." % a["owner"][len("store: "):]) if a["owner"].startswith("store: ")
        else "Who at the store: %% Magic: the role that owns this at the store, from the store README %%", "",
        "---", "",
        "Ledger: ask %s, first raised %s, raised on %d night%s, %d business days open as of %s. Source: `outputs/ai-team/ledgers/asks.json`."
        % (a["id"], a["first_raised"], len(a["raised"]), "" if len(a["raised"]) == 1 else "s", bd, date), ""])


def cmd_asks_request(args):
    date = iso(args.date)
    data = asks_load()
    if args.due:
        targets = aging_blocks(data, date)[3]
    elif args.id:
        targets = [ask_get(data, args.id)]
    else:
        die("asks request needs --id A3 or --due")
    out_dir = args.out_dir or P("asks", "requests")
    written = []
    for a in targets:
        if a["status"] != "open":
            die("%s is %s, no request needed" % (a["id"], a["status"]))
        path = os.path.join(out_dir, "%s-%s.md" % (date, a["id"]))
        save_text(path, request_text(a, date))
        a.setdefault("requests", [])
        a["requests"] = [r for r in a["requests"] if r.get("date") != date] + [{"date": date, "path": rel(path)}]
        written.append(rel(path))
    save_json(LP("asks.json"), data)
    for w in written:
        print("  " + w)
    print("asks request %s: %d draft(s) written for Drew to forward, nothing sent." % (date, len(written)))


def asks_seed_rows():
    b = "outputs/ai-team/%s/brief.md"
    return [
        dict(store="MCP", owner="Drew", needs_store=False, label="MCP auto-apply",
             ask="Check whether Google Ads Recommendations Auto-Apply is still enabled on McPeek's account, decide whether it stays on, and review the 20 keywords it removed on 2026-09-18.",
             evidence="Change log: Recommendations Auto-Apply removed 20 keywords on 2026-09-18 at 17:01 (11 New CDJR OEM, 9 Brand), changed the content network setting on both Search campaigns 2026-09-16 and Enhanced CPC 2026-09-17. MCP only; NOI and Atlas show no auto-apply rows. Source: outputs/ai-team/2026-09-23/data/mcp_autoapply_findings.md.",
             if_skipped="Google keeps changing keywords and settings on its own schedule and the team finds out afterward.",
             done_when="Drew confirms the setting (off, or on by choice) and the 20 removed keywords are reviewed.",
             raised=["2026-09-19", "2026-09-21", "2026-09-23"], source=b % "2026-09-19" + ", Needs your call"),
        dict(store="NOI", owner="Drew", needs_store=True, label="NOI vendors Auto Credit Express and TrueCar",
             ask="Confirm with the store whether Auto Credit Express and TrueCar are live NOI vendors.",
             evidence="VinSolutions Lead Source ROI: $6,853 month to date between them through 2026-09-22 (Auto Credit Express $3,850, TrueCar $3,003), zero leads (Report-7275.xlsx, outputs/ai-team/2026-09-23/nick.md). $5,607 through 9/18 (2026-09-19/run2/nick.md), $6,497 through 9/21 (2026-09-22/data/crm_mtd_NOI.json). Vendor watch V1, V2.",
             if_skipped="Another month of spend on nothing, or a wrong cost page the team keeps reporting.",
             done_when="The store says live or not live for each; live rows go to cut or keep, dead rows get cleaned off the cost page.",
             raised=["2026-09-19", "2026-09-21", "2026-09-22", "2026-09-23"], vendor_ids=["V1", "V2"],
             source="outputs/ai-team/2026-09-19/run2/brief.md, Needs your call"),
        dict(store="SBMW", owner="store: GA4 admin", needs_store=True, label="SBMW service page view counted as a key event",
             ask="Un-mark schedule_service_page_view as a key event in Sterling BMW's GA4, and check whether form_submit and generate_lead are one form tagged twice.",
             evidence="58 of 75 GA4 key events on 2026-09-22 were schedule_service_page_view, a page view; without it, 17 submissions against 16 CRM prospects the same day. form_submit and generate_lead matched 7 and 7 on 9/22 and 40 and 40 on the week (outputs/ai-team/2026-09-23/kobe.md). The double tag was first noted 2026-09-19 (2026-09-19/brief.md, huddles).",
             if_skipped="SBMW conversion numbers cannot go in a client report.",
             done_when="Only real lead actions are key events in SBMW's GA4.",
             raised=["2026-09-23"], source=b % "2026-09-23" + ", Action items 3"),
        dict(store="MCP", owner="store: GA4 admin", needs_store=True, label="MCP inventory page views counted as key events",
             ask="Un-mark the new and used VLP and VDP visit events (and their lowercase duplicates) as key events in McPeek's GA4; keep real lead actions only.",
             evidence="481 key events on 149 sessions on 2026-09-22 (323%), driven by new_VLP_visit, used_VLP_visit, new_VDP_visit, used_VDP_visit and lowercase copies (outputs/ai-team/2026-09-23/kobe.md). 3,843 key events on 1,105 sessions in the week to 9/18 (2026-09-19/run2/brief.md).",
             if_skipped="No McPeek's GA4 conversion number means anything, including in the monthly report.",
             done_when="MCP key events fall to real form and call actions (roughly 8 to 14 a week per the 2026-09-19 brief).",
             raised=["2026-09-19", "2026-09-21", "2026-09-22", "2026-09-23"],
             source="outputs/ai-team/2026-09-19/run2/brief.md, Action items 5"),
        dict(store="NCBMW", owner="store: site or GTM owner", needs_store=True, label="NCBMW tracking break since 9/1",
             ask="Check the GTM publish history around 2026-09-01 on New Century's site and run a test lead through GA4 DebugView.",
             evidence="Key-event rate 1.86% on 2026-09-22, day 22 of a collapse that started about 9/1; the events themselves are clean form and call events, so it reads as a real break (outputs/ai-team/2026-09-23/kobe.md, data/ga4_NCBMW.json).",
             if_skipped="New Century's reporting stays wrong and nobody can say whether its paid traffic converts.",
             done_when="A test lead shows in DebugView and the key-event rate returns to the 2 to 6% band.",
             raised=["2026-09-22", "2026-09-23"], source=b % "2026-09-22" + ", Action items 4"),
        dict(store="NCBMW", owner="Drew (Meta edit access)", needs_store=False, label="NCBMW Meta ad UTM tags",
             ask="Add UTM parameters to the NCBMW Meta traffic ad's destination URL; Luka wrote the exact string.",
             evidence="$106.83 spent since 2026-09-04 lands in GA4 as untagged Facebook and Instagram referral traffic, zero rows for its campaign (outputs/ai-team/2026-09-23/luka.md, data/meta_adsets.json).",
             if_skipped="That campaign stays invisible in reporting.",
             done_when="GA4 shows sessions under the campaign's own utm_campaign.",
             raised=["2026-09-22", "2026-09-23"], source=b % "2026-09-22" + ", Action items 5"),
        dict(store="NOI", owner="Drew (Meta edit access)", needs_store=False, label="NOI archive three finished boosted posts",
             ask="Archive the three finished NOI boosted posts so they stop reading ACTIVE.",
             evidence="Ad set flights ended 2026-06-01, 2026-06-20 and 2026-08-15; status still ACTIVE, $0 spend, no errors (outputs/ai-team/2026-09-23/data/meta_adsets.json). First spotted as expired in 2026-09-19/run2/brief.md.",
             if_skipped="Cosmetic only, no money involved; they get re-flagged every night.",
             done_when="The three campaigns read archived or completed.",
             raised=["2026-09-19", "2026-09-23"], source="outputs/ai-team/2026-09-19/run2/brief.md, Needs your call"),
        dict(store="NOI", owner="Drew", needs_store=False, label="NOI park or fix three $0 Meta campaigns",
             ask="Park or fix three Meta campaigns at $0 spend for 14 straight days ($46 a day budgeted, never delivered).",
             evidence="outputs/ai-team/2026-09-22/brief.md, Needs your call and Action items 7.",
             raised=["2026-09-22", "2026-09-23"], source=b % "2026-09-22" + ", Needs your call",
             withdraw=("2026-09-23", "Wrong framing. They are finished boosted posts: flights ended 2026-06-01, 2026-06-20 and 2026-08-15, and an ended flight neither spends nor errors, so no money was ever at risk. Replaced by the archive ask (A7). Source: outputs/ai-team/2026-09-23/shift-log.md 01:31, data/meta_adsets.json.")),
        dict(store="NCBMW", owner="Drew", needs_store=False, label="NCBMW report routing",
             ask="Chase the New Century report routing (FOCUS, BMW NA and Constellation mail all looked stopped on 2026-09-17).",
             evidence=b % "2026-09-23" + ", Action items 7.",
             raised=["2026-09-23"], source=b % "2026-09-23" + ", Action items 7",
             withdraw=("2026-09-23", "Wrong ask. The feeds never stopped: gdata.py mail-ls without --any-label searched only inside the Morning_CRM label and hid BMW NA's Lead Conversion (9/22), the daily RDR mails (through 9/23) and Constellation's weekly report (9/22). A script usage bug, now documented in references/data-sources.md.")),
        dict(store="MCP", owner="store: Tekion admin", needs_store=True, label="MCP Tekion export",
             ask="Get McPeek's Tekion lead report scheduled to email nightly; the store's Tekion admin has to set it up (Drew is at the store Thursdays).",
             evidence="No MCP CRM data ever; Tekion has never been scheduled (outputs/ai-team/2026-09-23/nick.md, references/data-sources.md). 57 ad phone calls in 7 days to 9/22 cannot be traced to leads or sales (2026-09-23/brief.md).",
             if_skipped="McPeek's ad numbers stay cost per call with no idea what the calls became.",
             done_when="A Tekion report lands under the Morning_CRM label.",
             raised=["2026-09-22", "2026-09-23"], source=b % "2026-09-22" + ", Missing tonight"),
        dict(store="ALL", owner="Drew", needs_store=False, label="Content topic pick",
             ask="Pick one of the open content topics or say none this week.",
             evidence="Four topic briefs waiting since 2026-09-22, a fifth added 2026-09-23 (outputs/ai-team/topics.json).",
             raised=["2026-09-22", "2026-09-23"], source=b % "2026-09-22" + ", Compliance gate",
             close=("2026-09-23", "Drew picked T3 (Jeep Wagoneer S, MCP) on 2026-09-23: outputs/ai-team/topics.json status picked, picked_at 2026-09-23.", None)),
        dict(store="NOI", owner="Drew", needs_store=False, label="NOI Gas Models decision",
             ask="Decide on NOI Gas Models: rebuild it with calls as the conversion, or leave it off.",
             evidence="Paused and spending nothing, change log clean (outputs/ai-team/2026-09-23/brief.md). 26 ad calls went uncounted the week to 9/21 (2026-09-22/brief.md). $1,008 Friday to Sunday 9/18 to 9/20 with zero conversions before the pause (2026-09-21/brief.md).",
             if_skipped="No urgency while paused; the decision stays open.",
             done_when="Drew says rebuild (with calls as the goal) or leave it off.",
             raised=["2026-09-19", "2026-09-21", "2026-09-22", "2026-09-23"], source=b % "2026-09-19" + ", Needs your call"),
        dict(store="NCBMW", owner="Drew", needs_store=True, label="NCBMW other Meta advertiser",
             ask="Find out who else runs Meta ads for New Century: two campaigns in NCBMW's GA4 are not in the DigitalCLIQ account.",
             evidence="\"Service - Attack - Page Engagers & Website Visitors | Meta\" and an Instagram campaign with an id DigitalCLIQ does not own (outputs/ai-team/2026-09-22/brief.md).",
             if_skipped="NCBMW paid social reporting mixes someone else's spend with ours.",
             done_when="The owner of the two campaigns is known.",
             raised=["2026-09-22", "2026-09-23"], source=b % "2026-09-22" + ", Needs your call"),
        dict(store="ATLAS", owner="Drew", needs_store=False, label="Atlas real lead conversion",
             ask="Set up a real lead conversion for Atlas in Google Ads and GA4, after a live DebugView test of generate_lead.",
             evidence="Ads counts About Us page views as its only conversion (47 in 7 days to 9/22); GA4 generate_lead fired 192 times on 167 contact-page sessions with 100% engagement, which looks like page load (outputs/ai-team/2026-09-23/brief.md, huddles). Carried in 2026-09-23/shift-log.md.",
             if_skipped="Atlas's roughly $184 a week in Ads spend cannot be judged.",
             done_when="A tested lead action is the primary conversion in Ads and the only key event in GA4.",
             raised=["2026-09-19", "2026-09-22", "2026-09-23"], source=b % "2026-09-19" + ", Needs your call"),
        dict(store="SBMW", owner="Drew", needs_store=False, label="SBMW budget sheet tab",
             ask="Tell Nick which tab of Sterling BMW's budget sheet holds spend by source.",
             evidence="The Summary tab is a quarterly rollup, so cost per lead by source is unavailable (outputs/ai-team/2026-09-23/nick.md, brief Missing tonight).",
             if_skipped="No cost per lead or cost per sale for SBMW, and no vendor watch there.",
             done_when="Nick reads source-level spend for SBMW.",
             raised=["2026-09-23"], source=b % "2026-09-23" + ", Missing tonight"),
        dict(store="ALL", owner="team: Magic", needs_store=False, label="Semrush and Meta in player sessions",
             ask="Confirm Worthy loads Semrush and Luka loads Meta in their own sessions after the turn-break spawn fix.",
             evidence="No Semrush or Meta in teammate sessions on 2026-09-19, 09-21, 09-22 and 09-23; root cause and fix written into SKILL.md step 1 and references/data-sources.md on 2026-09-23.",
             done_when="usage.py --tools exits 0 on a shift (Worthy has Semrush, Luka has Meta).",
             raised=["2026-09-19", "2026-09-21", "2026-09-22", "2026-09-23"], source=b % "2026-09-19" + ", Needs your call"),
        dict(store="ALL", owner="team: Magic", needs_store=False, label="slack.py eats dollar amounts",
             ask="Stop the shell from eating dollar amounts in Slack posts.",
             evidence="\"$6,497\" posted as \",497\" on 2026-09-22 (outputs/ai-team/2026-09-23/shift-log.md, Worth fixing 1).",
             raised=["2026-09-23"], source="outputs/ai-team/2026-09-23/shift-log.md, Worth fixing before the next shift",
             close=("2026-09-23", "slack.py now refuses shell-damaged --text and points to --file (dollar_damage guard in scripts/slack.py; Slack section of references/data-sources.md).", None)),
        dict(store="ALL", owner="team: Shaq", needs_store=False, label="Ads budget column backfilled",
             ask="Stop using campaign_daily_30d campaignBudget_amount for pacing, or fix ads_export.gs so it records the budget per day.",
             evidence="It read a flat $300 across every day, including both days a budget change was recorded; Shaq withdrew a pacing stat built on it (outputs/ai-team/2026-09-23/shift-log.md, Worth fixing 3).",
             done_when="Pacing uses a per-day budget source, or the column is dropped from pacing.",
             raised=["2026-09-23"], source="outputs/ai-team/2026-09-23/shift-log.md, Worth fixing before the next shift"),
    ]


def cmd_asks_seed(args):
    path = LP("asks.json")
    if os.path.exists(path) and not args.force:
        die("asks.json already exists; use --force to rebuild it from the seed (every later change is lost)")
    data = asks_load()
    data["asks"] = []
    for i, s in enumerate(asks_seed_rows(), 1):
        raised = sorted(s["raised"])
        a = {"id": "A%d" % i, "store": s["store"], "owner": s["owner"], "needs_store": s["needs_store"],
             "label": s["label"], "ask": s["ask"], "evidence": s["evidence"], "if_skipped": s.get("if_skipped"),
             "done_when": s.get("done_when"), "first_raised": raised[0], "last_raised": raised[-1], "raised": raised,
             "status": "open", "closed_date": None, "closure_evidence": None, "win": None, "withdrawn_reason": None,
             "vendor_ids": s.get("vendor_ids", []), "requests": [], "source": s["source"],
             "history": [{"date": "2026-09-23", "action": "seeded from the 2026-09-23 brief and shift log; first raised = earliest brief"}]}
        if s.get("withdraw"):
            a.update({"status": "withdrawn", "closed_date": s["withdraw"][0], "withdrawn_reason": s["withdraw"][1]})
        if s.get("close"):
            a.update({"status": "closed", "closed_date": s["close"][0], "closure_evidence": s["close"][1], "win": s["close"][2]})
        data["asks"].append(a)
    save_json(path, data)
    c = {k: sum(1 for a in data["asks"] if a["status"] == k) for k in ASK_STATUSES}
    print("asks seed: %d asks (%d open, %d closed, %d withdrawn). %d need the store." % (
        len(data["asks"]), c["open"], c["closed"], c["withdrawn"],
        sum(1 for a in data["asks"] if a["needs_store"] and a["status"] == "open")))


# ---------------------------------------------------------------- Ads export dump (read-only)

def cmd_ads_dump(args):
    date = iso(args.date)
    sys.path.insert(0, HERE)
    import gdata  # noqa: E402  (same auth the players use; read-only Sheets scope)
    import urllib.parse
    ref = open(os.path.join(HERE, "..", "references", "data-sources.md"), encoding="utf-8").read()
    ids = re.findall(r"^\|\s*([A-Z]+)\s*\|\s*[\d-]{8,}\s*\|\s*`([A-Za-z0-9_-]{20,})`", ref, re.M)
    if not ids:
        die("no Ads export Sheet ids found in references/data-sources.md")
    out_dir = P(date, "data")
    os.makedirs(out_dir, exist_ok=True)
    now = dt.datetime.now()
    for store, sid in ids:
        def values(rng):
            url = "https://sheets.googleapis.com/v4/spreadsheets/%s/values/%s" % (sid, urllib.parse.quote(rng, safe=""))
            return gdata.api(url).get("values", [])
        try:
            meta = values("meta!A1:B30")
            rows = values("campaign_daily_30d!A1:N2000")
        except Exception as e:  # keep going, never guess
            print("  %s: FAILED %s" % (store, str(e)[:200]))
            continue
        last_run = next((r[1] for r in meta if len(r) > 1 and str(r[0]).strip().lower() == "last_run"), None)
        stale = ""
        lr = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M:%S"):
            try:
                lr = dt.datetime.strptime(str(last_run).replace("Z", "").split(".")[0].strip(), fmt)
                break
            except (ValueError, TypeError):
                continue
        if lr is None:
            stale = " (last_run unreadable)" if last_run else " (no last_run in meta tab)"
        elif (now - lr).total_seconds() > 26 * 3600:
            stale = " STALE (older than 26 hours)"
        path = os.path.join(out_dir, "%s_campaign_daily_30d.txt" % store)
        head = "=== %s campaign_daily_30d, saved by ledgers.py ads-dump %s, export last_run %s%s ===\n" % (
            store, now.isoformat(timespec="seconds"), last_run, stale)
        save_text(path, head + json.dumps(rows, indent=0) + "\n")
        dates = sorted({r[0] for r in rows[1:] if r})
        print("  %s: %d rows, %s to %s, last_run %s%s -> %s" % (store, len(rows) - 1, dates[0] if dates else "n/a",
                                                               dates[-1] if dates else "n/a", last_run, stale, rel(path)))
    print("ads-dump %s: done. Run `ledgers.py shift append --date %s` to fold it into the ledger." % (date, date))


# ---------------------------------------------------------------- CRM helpers

def cmd_crm_shape(_args):
    print(json.dumps({"example": CRM_SHAPE, "rules": CRM_SHAPE_RULES}, indent=1))


def cmd_crm_check(args):
    d = load_json(args.file, None)
    if d is None:
        die("cannot read %s" % args.file)
    probs = crm_problems(d)
    n = crm_normalize(d, None, d.get("store"))
    print("crm-check %s: %s. Reads as %s %s to %s, leads %s, sold %s, %d source rows." % (
        rel(os.path.abspath(args.file)), "OK" if not probs else "%d problem(s)" % len(probs), n["store"],
        n.get("period_start"), n.get("period_end"), fmt_num(n["headline"].get("leads")),
        fmt_num(n["headline"].get("sold")), len(n["by_source"])))
    for p in probs:
        print("  - " + p)
    if probs and d.get("schema") == "crm_mtd.v1":
        sys.exit(1)


def cmd_crm_correct(args):
    corr = load_json(LP("crm-corrections.json"), {"corrections": []})
    corr.setdefault("_about", "Known errors in saved crm_mtd files, applied when the ledgers read them. The files stay as written.")
    item = {"shift": iso(args.shift), "store": store_arg(args.store), "source": args.source_name, "field": args.field,
            "value": parse_value(args.value), "reason": text_arg(args, "reason", required=True),
            "evidence": text_arg(args, "evidence")}
    corr["corrections"] = [c for c in corr["corrections"] if not (c["shift"] == item["shift"] and c["store"] == item["store"]
                                                                  and c["source"].lower() == item["source"].lower()
                                                                  and c["field"] == item["field"])] + [item]
    save_json(LP("crm-corrections.json"), corr)
    print("crm-correct: %s %s %s %s set to %s when read. %d correction(s) on file." % (
        item["shift"], item["store"], item["source"], item["field"], item["value"], len(corr["corrections"])))


# ---------------------------------------------------------------- self test

def cmd_selftest(_args):
    global ROOT
    real_root = ROOT
    tmp = tempfile.mkdtemp(prefix="ledgers-selftest-")
    ROOT = tmp
    results = []

    def check(name, cond, detail=""):
        results.append((name, bool(cond), detail))

    import io
    import contextlib

    def expect_exit(fn, *a):
        try:
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                fn(*a)
        except SystemExit as e:
            return e.code not in (0, None)
        return False

    quiet = contextlib.redirect_stdout(io.StringIO())
    try:
        d1 = P("2026-09-02", "data")
        os.makedirs(os.path.join(d1, "d0901"))
        ga4 = {"store": "NOI", "target_date": "2026-09-01", "pulled_at": "2026-09-02T01:00:00", "errors": [],
               "channel_daily_last7": [
                   {"date": "20260831", "sessionDefaultChannelGroup": "Direct", "sessions": 50, "engagedSessions": 5, "keyEvents": 1},
                   {"date": "20260901", "sessionDefaultChannelGroup": "Direct", "sessions": 100, "engagedSessions": 10, "keyEvents": 2},
                   {"date": "20260901", "sessionDefaultChannelGroup": "Organic Search", "sessions": 40, "engagedSessions": 20, "keyEvents": 3},
                   {"date": "20260901", "sessionDefaultChannelGroup": "AI Assistant", "sessions": 2, "engagedSessions": 1, "keyEvents": 0}],
               "ai_engine_referrals_last28": [{"sessionSource": "chatgpt.com", "sessions": 30}, {"sessionSource": "copilot.com", "sessions": 1}]}
        save_json(os.path.join(d1, "ga4_NOI.json"), ga4)
        save_json(os.path.join(d1, "ga4_organic_NOI.json"), {"store": "NOI", "target_date": "2026-09-01"})
        head = ["segments_date", "campaign_id", "campaign_name", "campaign_status", "campaign_advertisingChannelType",
                "campaignBudget_amount", "metrics_impressions", "metrics_clicks", "metrics_cost", "metrics_conversions"]
        ads = [head, ["2026-09-01", "1", "NOI-PMAX", "ENABLED", "PERFORMANCE_MAX", "82", "1000", "30", "40.5", "1"],
               ["2026-09-01", "2", "NOI | Value", "ENABLED", "SEARCH", "72", "300", "45", "118.25", "18.5"],
               ["2026-08-31", "2", "NOI | Value", "ENABLED", "SEARCH", "72", "100", "5", "10", "0"]]
        save_text(os.path.join(d1, "NOI_campaign_daily_30d.txt"), "=== NOI campaign_daily_30d ===\n" + json.dumps(ads))
        save_json(os.path.join(d1, "meta_campaigns.json"), {"yesterday_2026-09-01": [
            {"name": "Post: \"Come get yours at Nissan of Irvine\"", "id": "9", "spend_usd": "20.50", "clicks": 100, "omni_landing_page_view": 80},
            {"name": "NCBMW | Traffic", "id": "8", "spend_usd": "6.46", "clicks": 20, "omni_landing_page_view": 19},
            {"name": "Mystery post", "id": "7", "spend_usd": "1.00", "clicks": 1}]})
        crm = json.loads(json.dumps(CRM_SHAPE))
        crm.update({"period_start": "2026-09-01", "period_end": "2026-09-01", "pulled_at_shift": "2026-09-02"})
        save_json(os.path.join(d1, "crm_mtd_NOI.json"), crm)
        with quiet:
            cmd_shift_append(argparse.Namespace(date="2026-09-02"))
        rows = read_ledger()
        noi = next(r for r in rows if r["store"] == "NOI")
        check("shift append writes one row per store", len(rows) == 5, len(rows))
        check("ga4 target-day sums", (noi["ga4_sessions"], noi["organic_sessions"], noi["ai_sessions"], noi["ga4_key_events"],
                                      noi["ai_referrals_28d"]) == (142, 40, 2, 5, 31), noi)
        check("ads target-day sums", (noi["gads_cost"], noi["gads_clicks"], noi["gads_conversions"]) == (158.75, 75, 19.5), noi)
        check("meta split by store", noi["meta_spend"] == 20.5 and next(r for r in rows if r["store"] == "NCBMW")["meta_spend"] == 6.46)
        check("meta covered day is a real zero", next(r for r in rows if r["store"] == "SBMW")["meta_spend"] == 0.0)
        check("crm headline attached", (noi["crm_leads"], noi["crm_sold"], noi["crm_period_end"]) == (511, 53, "2026-09-01"))
        with quiet:
            cmd_shift_append(argparse.Namespace(date="2026-09-02"))
        check("shift append is idempotent", len(read_ledger()) == 5)
        with quiet:
            cmd_shift_set(argparse.Namespace(file=None, date="2026-09-02", store="NOI", field="clean_key_events", value="4",
                                             source="kobe.md line 24", source_file=None, target_date=None))
            cmd_shift_append(argparse.Namespace(date="2026-09-02"))
        noi = next(r for r in read_ledger() if r["store"] == "NOI")
        check("override survives a re-append", noi["clean_key_events"] == 4 and "overrides" in noi["sources"], noi["sources"])
        check("bad override field refused", expect_exit(cmd_shift_set, argparse.Namespace(
            file=None, date="2026-09-02", store="NOI", field="date", value="x", source="y", source_file=None, target_date=None)))
        # vendor watch
        with quiet:
            cmd_vendor_scan(argparse.Namespace(date="2026-09-02"))
            cmd_vendor_scan(argparse.Namespace(date="2026-09-02"))
        vw = vendor_load()["rows"]
        check("vendor scan flags the zero-lead vendor only", [r["vendor"] for r in vw] == ["Auto Credit Express"], vw)
        check("vendor scan is idempotent", len(vw) == 1 and len(vw[0]["history"]) == 1)
        with quiet:
            cmd_vendor_update(argparse.Namespace(date="2026-09-03", store="NOI", vendor="auto credit express", month=None,
                                                 spend=None, leads=None, sold=None, as_of=None, source=None, source_file=None,
                                                 status="confirmed-live", note="store confirmed", note_file=None,
                                                 bench_category=None, ask=None))
        vw = vendor_load()["rows"]
        check("vendor update changes status, matches name loosely", vw[0]["status"] == "confirmed-live" and len(vw) == 1)
        check("business days Fri to Wed is 3", business_days("2026-09-18", "2026-09-23") == 3)
        check("business days Sat to Wed is 3", business_days("2026-09-19", "2026-09-23") == 3)
        # asks
        base = dict(store="NOI", owner="store: GM", label="Test ask " + EMDASH + " dash", ask="Do the thing.", ask_file=None,
                    evidence="Seen in kobe.md.", evidence_file=None, if_skipped=None, if_skipped_file=None,
                    done_when=None, done_when_file=None, needs_store=True, vendors="V1", source=None, source_file=None,
                    owner_file=None, label_file=None)
        with quiet:
            cmd_asks_add(argparse.Namespace(date="2026-09-18", first_raised=None, **base))
            cmd_asks_add(argparse.Namespace(date="2026-09-21", first_raised=None, **dict(base, needs_store=False, label="Second")))
        data = asks_load()
        check("asks add assigns A1, A2", [a["id"] for a in data["asks"]] == ["A1", "A2"])
        check("em dash scrubbed on write", EMDASH not in open(LP("asks.json"), encoding="utf-8").read())
        check("PII refused", expect_exit(cmd_asks_add, argparse.Namespace(
            date="2026-09-21", first_raised=None, **dict(base, evidence="call 714-555-0100 back"))))
        check("shell-eaten dollars refused", expect_exit(cmd_asks_add, argparse.Namespace(
            date="2026-09-21", first_raised=None, **dict(base, evidence="Costs ,853 with zero leads"))))
        text, older, closed, due, new = aging_blocks(asks_load(), "2026-09-23")
        check("aging lists carried asks oldest first", [a["id"] for a in older] == ["A1", "A2"], text)
        check("GM request due after 3 business days", [a["id"] for a in due] == ["A1"], text)
        check("aging line format", "- A1, Test ask - dash, open 5 days, store: GM, GM request due" in text, text)
        with quiet:
            cmd_asks_request(argparse.Namespace(date="2026-09-23", id="A1", due=False, out_dir=None))
            cmd_asks_close(argparse.Namespace(id="A2", date="2026-09-23", evidence="Done, see nick.md.", evidence_file=None,
                                              win="Store fixed it on 9/23.", win_file=None))
        req = open(P("asks", "requests", "2026-09-23-A1.md"), encoding="utf-8").read()
        check("request draft says nothing was sent", "Nothing was sent" in req and "General Manager" in req)
        check("request draft has no em dash", EMDASH not in req)
        text, older, closed, due, new = aging_blocks(asks_load(), "2026-09-23")
        check("closed tonight block", "- A2, Second: closed. Done, see nick.md. Win: Store fixed it on 9/23." in text, text)
        check("drafted request stops the due flag", not due and "GM request drafted 2026-09-23" in text, text)
        # month pack
        with quiet:
            cmd_month(argparse.Namespace(month="2026-09"))
        pack = load_json(LP("month-pack-2026-09.json"))
        st = pack["stores"]["NOI"]
        check("month pack ga4 coverage and totals", st["ga4"]["coverage"]["days"] == ["2026-09-01"]
              and st["ga4"]["totals"]["sessions"] == 142 and not st["ga4"]["coverage"]["complete"], st["ga4"]["coverage"])
        check("month pack ads excludes other months", st["google_ads"]["totals"]["cost"] == 158.75)
        check("month pack crm from snapshot", st["crm"]["headline"]["leads"] == 511 and not st["crm"]["coverage"]["complete"])
        check("month pack wins", len(st["wins"]) == 1 and st["wins"][0]["id"] == "A2")
        check("month pack md has no em dash", EMDASH not in open(LP("month-pack-2026-09.md"), encoding="utf-8").read())
        # legacy CRM shapes and meta shapes
        legacy = {"store": "NOI", "date_range": "2026-09-01 to 2026-09-21 (run)", "by_source": [
            {"source": "TrueCar", "total_leads": 0, "good_leads": 0, "sold_from_leads": 0, "appts_set": 0, "appts_shown": 0, "total_cost": 2847}],
            "totals": {"total_leads": 479, "good_leads": 368, "appts_set": 64, "appts_shown": 42, "sold_from_leads": 50, "total_cost": 13578}}
        n = crm_normalize(legacy, "x", "NOI")
        check("legacy VinSolutions shape reads", (n["period_end"], n["headline"]["leads"], n["headline"]["sold"],
                                                  n["by_source"][0]["cost"]) == ("2026-09-21", 479, 50, 2847.0), n)
        mom = {"store": "SBMW", "date_range": "2026-09-01 to 2026-09-21", "by_category": [{"category": "Internet", "prospects_created": 575, "sold_dms": 25}],
               "totals": {"prospects_created": 906, "appts_created": 138, "shows": 85, "sold_dms": 88}}
        n = crm_normalize(mom, "x", "SBMW")
        check("legacy Momentum shape reads", (n["headline"]["leads"], n["headline"]["sold"], n["source_kind"]) == (906, 88, "category"))
        check("contract example validates", crm_problems(CRM_SHAPE) == [], crm_problems(CRM_SHAPE))
        mfile = os.path.join(tmp, "m.json")
        save_json(mfile, {"call": "ads_get_ad_entities level=campaign, time_range 2026-09-08..2026-09-10, time_increment 1",
                          "campaigns": [{"id": "120246868226640042", "name": "Post: \"Have you been to our new building?\"", "store": "unconfirmed",
                                         "daily": [{"date": "2026-09-09", "spend": 4.0, "clicks": 2, "lpv": 1}]}]})
        cov, recs = meta_extract(mfile, dict(DEFAULT_META_MAP))
        check("meta campaigns-with-daily shape and id map", len(cov) == 3 and recs[0]["store"] == "NOI", (cov, recs))
        save_json(mfile, {"window": "yesterday 2026-09-18", "rows": [{"id": "1", "name": "NCBMW | T", "spend": 9.95,
                                                                     "result": "landing page views 33"}, {"note": "others 0"}]})
        cov, recs = meta_extract(mfile, {})
        check("meta rows+window shape", cov == {"2026-09-18"} and recs[0]["lpv"] == 33 and len(recs) == 1, recs)
        check("script source has no em dash", EMDASH not in open(os.path.abspath(__file__), encoding="utf-8").read())
    finally:
        ROOT = real_root
        shutil.rmtree(tmp, ignore_errors=True)
    bad = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print("%s  %s%s" % ("PASS" if ok else "FAIL", name, "" if ok else "  " + str(detail)[:400]))
    print("selftest: %d/%d passed%s" % (len(results) - len(bad), len(results), "" if not bad else ", %d FAILED" % len(bad)))
    sys.exit(1 if bad else 0)


# ---------------------------------------------------------------- CLI

def add_text(p, name, help_=None):
    flag = "--" + name.replace("_", "-")
    p.add_argument(flag, dest=name, help=help_)
    p.add_argument(flag + "-file", dest=name + "_file")


def main():
    global ROOT
    ap = argparse.ArgumentParser(description="AI team ledgers: vendor watch, asks and wins, shift ledger, month pack.")
    ap.add_argument("--root", default=DEFAULT_ROOT, help=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("vendor").add_subparsers(dest="sub", required=True)
    p = v.add_parser("seed"); p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_vendor_seed)
    p = v.add_parser("scan"); p.add_argument("--date", required=True); p.set_defaults(fn=cmd_vendor_scan)
    p = v.add_parser("update")
    for a in ("--store", "--vendor", "--date"):
        p.add_argument(a, required=True)
    for a in ("--spend", "--leads", "--sold", "--as-of", "--month", "--bench-category", "--ask"):
        p.add_argument(a)
    p.add_argument("--status", choices=VENDOR_STATUSES)
    add_text(p, "source")
    add_text(p, "note")
    p.set_defaults(fn=cmd_vendor_update)
    p = v.add_parser("list")
    p.add_argument("--store"); p.add_argument("--month"); p.add_argument("--date"); p.add_argument("--all", action="store_true")
    p.set_defaults(fn=cmd_vendor_list)
    p = v.add_parser("month-end"); p.add_argument("--month", required=True); p.set_defaults(fn=cmd_vendor_month_end)

    a = sub.add_parser("asks").add_subparsers(dest="sub", required=True)
    p = a.add_parser("seed"); p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_asks_seed)
    p = a.add_parser("add")
    p.add_argument("--store", required=True); p.add_argument("--date", required=True)
    p.add_argument("--first-raised"); p.add_argument("--needs-store", action="store_true"); p.add_argument("--vendors")
    for t in ("owner", "label", "ask", "evidence", "if_skipped", "done_when", "source"):
        add_text(p, t)
    p.set_defaults(fn=cmd_asks_add)
    p = a.add_parser("update")
    p.add_argument("--id", required=True); p.add_argument("--date", required=True); p.add_argument("--store")
    p.add_argument("--needs-store", choices=("yes", "no")); p.add_argument("--no-raise", action="store_true")
    for t in ("owner", "label", "ask", "evidence", "if_skipped", "done_when", "note"):
        add_text(p, t)
    p.set_defaults(fn=cmd_asks_update)
    p = a.add_parser("close")
    p.add_argument("--id", required=True); p.add_argument("--date", required=True)
    add_text(p, "evidence"); add_text(p, "win")
    p.set_defaults(fn=cmd_asks_close)
    p = a.add_parser("withdraw")
    p.add_argument("--id", required=True); p.add_argument("--date", required=True); add_text(p, "reason")
    p.set_defaults(fn=cmd_asks_withdraw)
    p = a.add_parser("list"); p.add_argument("--status", choices=ASK_STATUSES + ("all",)); p.add_argument("--store")
    p.set_defaults(fn=cmd_asks_list)
    p = a.add_parser("aging"); p.add_argument("--date", required=True); p.add_argument("--out")
    p.set_defaults(fn=cmd_asks_aging)
    p = a.add_parser("request"); p.add_argument("--date", required=True); p.add_argument("--id")
    p.add_argument("--due", action="store_true"); p.add_argument("--out-dir", help=argparse.SUPPRESS)
    p.set_defaults(fn=cmd_asks_request)

    s = sub.add_parser("shift").add_subparsers(dest="sub", required=True)
    p = s.add_parser("append"); p.add_argument("--date", required=True); p.set_defaults(fn=cmd_shift_append)
    p = s.add_parser("backfill"); p.add_argument("--from", dest="from_date", required=True)
    p.add_argument("--to", dest="to_date", required=True); p.set_defaults(fn=cmd_shift_backfill)
    p = s.add_parser("set")
    for x in ("--date", "--store", "--field", "--value", "--target-date", "--file"):
        p.add_argument(x)
    add_text(p, "source")
    p.set_defaults(fn=cmd_shift_set)
    p = s.add_parser("list"); p.add_argument("--date"); p.set_defaults(fn=cmd_shift_list)

    p = sub.add_parser("month"); p.add_argument("--month", required=True); p.set_defaults(fn=cmd_month)
    p = sub.add_parser("ads-dump"); p.add_argument("--date", required=True); p.set_defaults(fn=cmd_ads_dump)
    p = sub.add_parser("crm-shape"); p.set_defaults(fn=cmd_crm_shape)
    p = sub.add_parser("crm-check"); p.add_argument("--file", required=True); p.set_defaults(fn=cmd_crm_check)
    p = sub.add_parser("crm-correct")
    for x in ("--shift", "--store", "--field", "--value"):
        p.add_argument(x, required=True)
    p.add_argument("--source", dest="source_name", required=True)
    add_text(p, "reason"); add_text(p, "evidence")
    p.set_defaults(fn=cmd_crm_correct)
    p = sub.add_parser("selftest"); p.set_defaults(fn=cmd_selftest)

    args = ap.parse_args()
    ROOT = os.path.abspath(args.root)
    args.fn(args)


if __name__ == "__main__":
    main()
