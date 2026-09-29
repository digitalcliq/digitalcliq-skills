#!/usr/bin/env python3
"""Vendor paid-search dashboards for the DigitalCLIQ AI night shift. Standard library only.

Two vendors run New Century BMW's (NCBMW) paid search and will not give us Google Ads access. NabThat
shares a Data Studio (Looker Studio) dashboard by view link; Constellation shares only a monthly Google
Sheet. The desktop task vendor-dash-read (daily about 12:45 AM Pacific) opens every active dashboard in
the Claude Browser, sets the date preset and appends the page text to
outputs/ai-team/vendor-dash/{D}/reads.jsonl. This script turns those reads into the night's deltas for
Shaq, cross-checks them against GA4 and both vendors' sheets, and estimates how much of GA4's untagged
paid traffic belongs to each vendor.

Read the way a careful analyst reads at 1 AM:
  * the newest day (yesterday, y = D - 1) is PRELIMINARY: read about 45 minutes after midnight, Google
    Ads and GA4 keep filling it in. It is compared only with the same weekday last week, also read the
    morning after, so the lag cancels.
  * earlier days RESTATE. Tonight's month to date minus the last one minus the preliminary days in
    between is how much earlier days moved; the last complete day (y - 1) is approx settled with it.
  * nothing is estimated without saying so; a missing read says "no read since {date}".

Usage (from the vault root):
  V = python3 .claude/skills/ai-team/scripts/vendor_dash.py
  V status --date D                 no network, no writes. Per source: read present, windows valid.
                                    Exit 0 all active sources valid, 2 otherwise.
  V ingest --date D [--reads PATH] [--learn]
                                    parse and validate reads.jsonl, write vendor-dash/{D}/{source}.json,
                                    print one line per window. Exit 0 / 2. --learn also prints every
                                    label/value pair found on each page (for adding a new dashboard).
  V report --date D [--out DIR] [--no-pull]
                                    ingest (idempotent), then deltas, pace, GA4 cross-check, sheets and
                                    the credit split. Writes {out}/vendor_ppc_{STORE}.md, {out}/vendor_ppc.json
                                    and, when pulled, {out}/vendor_ppc_ga4_{STORE}.json,
                                    {out}/vendor_sheet_{source}.json and vendor-dash/{D}/{source}.sheet.json.
                                    Default out: outputs/ai-team/{D}/data. --no-pull: no network at all
                                    (gdata is never imported); the sheet and GA4 sections use the newest
                                    saved snapshot and say so. Exit 0 everything read and pulled; 2 written
                                    but a read is missing or invalid or a pull failed; 1 usage.
  V selftest                        offline checks in a temp folder, touches nothing real; prints PASS/FAIL
                                    per check, exit 0 only if all pass.
Usage errors (unknown flag, no command) exit 1. --date defaults to today Pacific. D is the shift date; y = D - 1 is "yesterday". The env var
VENDOR_DASH_ROOT overrides the vault root (the selftest uses a temp root).

Files:
  config     .claude/skills/ai-team/vendor-dashboards.json (status active = read; awaiting_link = waiting)
  reads      outputs/ai-team/vendor-dash/{D}/reads.jsonl, one JSON object per line:
             {source, window: yesterday|mtd|last_month|default, read_at, browser, url, text, attempt?, note?}.
             The last valid line per window wins; a line that is not JSON is skipped and reported.
             window "default" (optional, one per source; old nights have none) is the page as first opened,
             before any preset: Auto, the last 28 days ending yesterday (its label may read Select date range).
             It is a reference, never a window: its boxes are parsed but never checked against a date range,
             reported, required or counted as a bad line. A window whose additive boxes repeat it (two or more
             equal, and the window is not the default range) was read before the preset refreshed the
             scorecards and is invalid.
  snapshots  outputs/ai-team/vendor-dash/{D}/{source}.json (parsed values, raw text cited by line)
             outputs/ai-team/vendor-dash/{D}/{source}.sheet.json (parsed vendor sheet)
  history    every snapshot dated on or before D.

Laws: aggregates only; never writes outside outputs/ai-team/vendor-dash/ and --out; never prints or
saves tokens; never em dashes (replaced on write); every estimate says "estimated" or "approx"; missing
data says "no read since {date}" or "not pulled tonight: {reason}", never a carried-forward number.
"""
import argparse
import calendar
import contextlib
import datetime as dt
import glob
import io
import json
import math
import os
import re
import shutil
import statistics
import sys
import tempfile
import urllib.parse

try:
    from zoneinfo import ZoneInfo
    PACIFIC = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover
    PACIFIC = None

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
ROOT = os.path.abspath(os.path.expanduser(os.environ.get("VENDOR_DASH_ROOT") or DEFAULT_ROOT))
EMDASH, ENDASH, MINUS, RSQUO = chr(8212), chr(8211), chr(8722), chr(8217)  # chr() so this file never holds one
CONFIG_REL = (".claude", "skills", "ai-team", "vendor-dashboards.json")

WINDOWS = ("yesterday", "mtd", "last_month")
DEFAULT_WINDOW = "default"    # a reads.jsonl reference line: the page as first opened, never a window
WLABEL = {"yesterday": "yesterday", "mtd": "month to date", "last_month": "last month"}
MON3 = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December")
_MONRE = "|".join(MON3)
DATE_LABEL_RE = re.compile(r"^(%s) (\d{1,2}), (\d{4})\s*[-%s%s]\s*(%s) (\d{1,2}), (\d{4})$"
                           % (_MONRE, ENDASH, EMDASH, _MONRE))
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NULL_TOKENS = ("-", ENDASH, EMDASH, "no data", "null", "n/a")
NOISE = ("arrow_drop_down", "arrow_drop_up", "Privacy Policy", "Phone Calls")
SUFFIX = {"K": 1e3, "M": 1e6, "B": 1e9}
_NUM_RE = re.compile(r"^(\d+(?:\.\d+)?|\.\d+)\s*([KMBkmb])?$")
_GROUP_RE = re.compile(r"^\d{1,3}(?: \d{3})+(?:\.\d+)?\s*[KMBkmb]?$")   # 47 286 (a space as the thousands mark)
_ZERO_WIDTH_RE = re.compile("[%s%s]" % (chr(0x200b), chr(0xfeff)))
_SPACES_RE = re.compile("[\\s%s]+" % "".join(chr(c) for c in (0xa0, 0x2007, 0x2009, 0x202f)))
SIGNIN_PHRASES = ("to continue to",)
ACCESS_PHRASES = ("Request access", "You need access", "don't have access", "don" + RSQUO + "t have access",
                  "Can't access report", "Can" + RSQUO + "t access report", "permission to view")
ERROR_WORDS = ("error", "configuration", "see details", "can't", "can" + RSQUO + "t", "access")
STALE_PCT = 0.02              # tonight's month to date may sit this far (or MIN_ABS) below last night's
DEFAULT_DAYS = 28             # the dashboard's default view (Auto): the last 28 days ending yesterday
DEFAULT_MATCH_MIN = 2         # this many equal additive boxes (zeros aside) mark a read of the default view
RISE_MIN_CLICKS = 100         # floor of the one-night restatement bound (a whole day's preliminary clicks)
LATE_HOURS = 1.5              # a yesterday read later than this after midnight is "later than usual"

SAME_KEYS = ("clicks", "impressions", "implied_cost", "avg_cpc", "phone_calls", "video_views")
DAY_KEYS = ("clicks", "impressions", "implied_cost", "phone_calls", "video_views")
MIN_ABS = {"clicks": 25, "impressions": 2000, "implied_cost": 100.0, "phone_calls": 5, "video_views": 100}
MIN_BASE = {"clicks": 50, "impressions": 5000, "implied_cost": 150.0, "phone_calls": 5, "video_views": 200}
DAY_MOVE_PCT = 25.0
CPC_MOVE_PCT = 20.0
CPC_MIN_CLICKS = 50
CALLS_ZERO_MIN_CLICKS = 100
RESTATED_PCT = 10.0
RESTATED_MIN = {"clicks": 25, "implied_cost": 100.0}
PACE_TOLERANCE = 1.05
ROUGH_HOURS = 3.0
CPC_ROUNDING = 0.005          # the dashboard shows Avg. CPC rounded to the cent
GA4_RATIO_PCT = 35.0
GA4_RATIO_MIN_CLICKS = 50
GA4_MIN_HISTORY = 4
SPLIT_MAX_RANGE = 0.15
SPLIT_METHODS = ("clicks", "spend", "landing")

GA4_DIMS = ["date", "sessionCampaignName", "sessionSourceMedium"]
GA4_METRICS = ["sessions", "engagedSessions", "keyEvents", "keyEvents:asc_form_submission",
               "keyEvents:asc_click_to_call"]
GA4_MEDIA = ("google / cpc", "google / vehiclelisting")
GA4_FILTER = {"filter": {"fieldName": "sessionSourceMedium", "inListFilter": {"values": list(GA4_MEDIA)}}}
GA4_LIMIT = 10000

NAB_ROWS = {"ad spend": "ad_spend", "fees": "fees", "phone calls": "phone_calls", "lead forms": "lead_forms",
            "store visits": "store_visits", "directions": "directions", "clicks": "clicks",
            "impressions": "impressions", "vdp + srp views": "vdp_srp_views"}
SHEET_DERIVED = ("total", "fee_rate", "cpc")
CON_KEYS = ("ad_spend", "impressions", "clicks", "lead_forms", "phone_calls")

PRELIM_LABEL = "preliminary: read about 45 minutes after midnight; Google Ads and GA4 keep filling it in"
DID_NOT_RUN = ("the vendor-dash-read task did not run; the Claude app was closed or the Mac was asleep "
               "at 12:45 AM")
SIGNIN_REASON = "sign-in page (the view link now needs a login; never sign in, tell Drew)"
ACCESS_REASON = "access denied (the vendor changed sharing)"
DEFAULT_RANGE_REASON = ("the page showed its default range (Select date range): the date preset was not "
                        "applied")
DEFAULT_MATCH_REASON = ("numbers match the page's default view (%d boxes equal): the preset had not refreshed the "
                        "scorecards; retry")
GA4_NOTE = ("GA4 names only Constellation's vehicle listing ads (UTM-tagged). NabThat's campaigns and "
            "Constellation's Performance Max and branding campaigns both land in the untagged google / cpc "
            "bucket, because neither vendor's Google Ads account is linked to this GA4 property.")
KE_NOTE = ("directional: GA4 key events on this property have been questioned since the Sep 1 drop, and the "
           "counts are small")
BROWSER = {"claude-browser": "the Claude Browser", "chrome": "Chrome"}
NO_PULL = "this run used --no-pull"

KEY_LABEL = {"clicks": "clicks", "impressions": "impressions", "avg_cpc": "avg CPC", "ctr": "CTR",
             "phone_calls": "phone calls", "video_views": "video views",
             "implied_cost": "implied (clicks x avg CPC) cost", "site_sessions": "sessions",
             "site_engagement_rate": "engagement rate",
             "site_form_submissions": "form submissions (keyEvents:asc_form_submission)"}
KEY_TYPE = {"implied_cost": "cost"}   # filled from the config's metric types in load_config()


# ---------------------------------------------------------------- basics

def die(msg, code=1):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(code)


def P(*parts):
    return os.path.join(ROOT, "outputs", "ai-team", *parts)


def VD(*parts):
    return P("vendor-dash", *parts)


def rel(path):
    try:
        r = os.path.relpath(path, ROOT)
    except ValueError:
        return path
    return os.path.abspath(path) if r.startswith("..") else r


def scrub(obj):
    if isinstance(obj, str):
        s = re.sub(r"\s*" + EMDASH + r"\s*", " - ", obj)
        return s.replace(ENDASH, "-")
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()}
    return obj


def say(s=""):
    """Every stdout line goes through scrub: Magic pastes status and FOR MAGIC lines as written."""
    print(scrub(str(s)))


def norm_line(s):
    """Non-breaking, thin and doubled spaces -> one space; zero-width marks dropped."""
    return _SPACES_RE.sub(" ", _ZERO_WIDTH_RE.sub("", str(s or ""))).strip()


def ge(x, t):
    """x >= t without float noise: (4.56 - 3.80) / 3.80 * 100 is 19.999999999999996, which is 20%."""
    return round(x, 6) >= round(t, 6)


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


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def iso(s, what="--date"):
    try:
        return dt.date.fromisoformat(str(s)).isoformat()
    except ValueError:
        die("%s must be YYYY-MM-DD, got %r" % (what, s))


def shift_day(day, n):
    return (dt.date.fromisoformat(day) + dt.timedelta(days=n)).isoformat()


def days_between(a, b):
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def daterange(a, b):
    out, d = [], a
    while d <= b:
        out.append(d)
        d = shift_day(d, 1)
    return out


def wd(day):
    """'2026-09-27' -> 'Sun 9/27'."""
    d = dt.date.fromisoformat(day)
    return "%s %d/%d" % (("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[d.weekday()], d.month, d.day)


def day_of(s):
    """'20260924' or '2026-09-24' -> '2026-09-24', else None."""
    m = re.match(r"^(\d{4})-?(\d{2})-?(\d{2})$", str(s or "").strip())
    return "%s-%s-%s" % m.groups() if m else None


def pacific_now():
    return dt.datetime.now(PACIFIC) if PACIFIC else dt.datetime.now()


def pacific_today():
    return pacific_now().date()


def now_iso():
    return pacific_now().isoformat(timespec="seconds")


def month_first(day):
    return day[:8] + "01"


def dim_of(day):
    return calendar.monthrange(int(day[:4]), int(day[5:7]))[1]


def month_last(day):
    return day[:8] + "%02d" % dim_of(day)


def month_name(day):
    return "%s %s" % (MONTHS[int(day[5:7]) - 1], day[:4])


def long_day(day):
    d = dt.date.fromisoformat(day)
    return "%s %d, %d" % (MON3[d.month - 1], d.day, d.year)


def fmt_range(a, b):
    return "%s - %s" % (long_day(a), long_day(b))


def short_range(a, b):
    da, db = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
    return "%s %d - %s %d, %d" % (MON3[da.month - 1], da.day, MON3[db.month - 1], db.day, db.year)


def parse_dt(s):
    s = str(s or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return dt.datetime.fromisoformat(s)
    except ValueError:
        return None


def _local(t):
    if t.tzinfo is not None:
        t = t.astimezone(PACIFIC) if PACIFIC else t
        t = t.replace(tzinfo=None)
    return t


def read_clock(read_at):
    t = parse_dt(read_at)
    if not t:
        return None
    return _local(t).strftime("%I:%M %p").lstrip("0")


def hours_after_midnight(read_at, date):
    t = parse_dt(read_at)
    if not t:
        return None
    base = dt.datetime.combine(dt.date.fromisoformat(date), dt.time())
    return (_local(t) - base).total_seconds() / 3600.0


def read_desc(w):
    b = str(w.get("browser") or "")
    b = BROWSER.get(b, b or "an unknown browser")
    return "%s by %s" % (read_clock(w.get("read_at")) or "at an unknown time", b)


def late_note(w, D):
    """None for a normal 12:45 AM read; a sentence when the yesterday read came later than usual."""
    h = hours_after_midnight((w or {}).get("read_at"), D)
    if h is None or h <= LATE_HOURS:
        return None
    return ("this read was taken at %s, later than usual, so %s is further along than a normal night's read"
            % (read_clock(w.get("read_at")), wd(w["start"]) if w.get("start") else "the day"))


def num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    isn, x, _ = parse_num(v)
    return x if isn else None


def r2(x):
    """Round money half up (25143.30 x 1.15 = 28914.795 -> 28914.80, not the float's .79)."""
    return None if x is None else round(x + (1e-9 if x >= 0 else -1e-9), 2)


def tidy(v):
    if isinstance(v, float):
        v = r2(v)
        return int(v) if v.is_integer() else v
    return v


def cap1(s):
    return s[:1].upper() + s[1:] if s else s


# ---------------------------------------------------------------- formatting

def fnum(v):
    if v is None:
        return "n/a"
    if isinstance(v, float) and not float(v).is_integer() and abs(v) < 1000 and round(v, 1) != round(v):
        return format(round(v, 1), ",")
    return format(int(round(v)), ",")


def fint(v):
    """Whole number with commas, for estimated counts (credited sessions, key events, prorated clicks)."""
    return "n/a" if v is None else format(int(round(v)), ",")


def money(v, cents=None):
    if v is None:
        return "n/a"
    if cents is None:
        cents = abs(v) < 100
    s = format(abs(r2(v)), ",.2f") if cents else format(int(round(abs(v))), ",")
    return ("-" if v < 0 else "") + "$" + s


def share(x):
    return "n/a" if x is None else "%.1f%%" % (x * 100)


def pchg(before, after):
    if before in (None, 0) or after is None:
        return None
    return (after - before) / abs(before) * 100.0


def spc(p):
    return "new" if p is None else "%s%d%%" % ("+" if p >= 0 else "-", abs(round(p)))


def key_label(k):
    return KEY_LABEL.get(k, k.replace("_", " "))


def fval(k, v):
    if v is None:
        return "n/a"
    t = KEY_TYPE.get(k)
    if t == "cost":
        return money(v)
    if t == "money":
        return money(v, True)
    if t == "pct":
        return "%.2f%%" % v
    return fnum(v)


def fchange(k, ch):
    if ch is None:
        return "n/a"
    sign = "+" if ch >= 0 else "-"
    t = KEY_TYPE.get(k)
    if t == "cost":
        return sign + money(abs(ch))
    if t == "money":
        return sign + money(abs(ch), True)
    if t == "pct":
        return "%s%.2f points" % (sign, abs(ch))
    return sign + fnum(abs(ch))


def change_text(k, a, b):
    if a is None or b is None:
        return "%s %s vs %s" % (key_label(k), fval(k, a), fval(k, b))
    return "%s %s vs %s (%s, %s)" % (key_label(k), fval(k, a), fval(k, b), fchange(k, a - b), spc(pchg(b, a)))


def values_text(v, keys, approx=(), err=None):
    out = []
    for k in keys:
        s = "%s %s" % (key_label(k), fval(k, v.get(k)))
        if k in (approx or ()):
            s += " (approx: the page rounded it)"
        elif err is not None and v.get(k) is not None:
            s += err_text(k, err.get(k))
        out.append(s)
    return ", ".join(out)


def err_text(k, e):
    """' (approx, +/- $57.56)' for a value with a rounding error, else ''."""
    if not e:
        return ""
    t = KEY_TYPE.get(k)
    return " (approx, +/- %s)" % (money(e, True) if t in ("cost", "money") else fnum(e))


def moves_text(v, keys, err=None):
    return ", ".join("%s %s%s" % (key_label(k), fchange(k, v.get(k)), err_text(k, (err or {}).get(k))) for k in keys)


# ---------------------------------------------------------------- config

def load_config():
    path = os.path.join(ROOT, *CONFIG_REL)
    cfg = load_json(path)
    if not isinstance(cfg, dict) or not isinstance(cfg.get("sources"), list):
        die("config missing or unreadable: %s" % rel(path))
    for s in cfg["sources"]:
        for m in s.get("metrics") or []:
            KEY_TYPE.setdefault(m["key"], m.get("type"))
    return cfg


def active_sources(cfg):
    return [s for s in cfg["sources"] if s.get("status") == "active"]


def waiting_text(src):
    if src.get("status") == "awaiting_link":
        return "no dashboard yet (awaiting link)"
    return "status %s, not read" % src.get("status")


def vendor_keys(src):
    return [m["key"] for m in src.get("metrics") or [] if m.get("scope") == "vendor_ads"]


def site_keys(src):
    return [m["key"] for m in src.get("metrics") or [] if m.get("scope") == "site_ga4"]


def add_keys(src):
    """Additive vendor_ads metrics: the only ones summed, differenced or cross-checked between windows."""
    return [m["key"] for m in src.get("metrics") or [] if m.get("additive") and m.get("scope") == "vendor_ads"]


def r_keys(src):
    return add_keys(src) + ["implied_cost"]


def perf_keys(src):
    """What may be stored as NabThat's performance values (never the whole-website site_* boxes)."""
    return vendor_keys(src) + ["implied_cost", "implied_cost_err", "ctr_calc", "calls_per_100_clicks"]


def perf(v, src):
    return None if v is None else {k: v.get(k) for k in perf_keys(src)}


def expected_windows(D):
    w = ["yesterday", "mtd"]
    if dt.date.fromisoformat(D).day in (2, 3):
        w.append("last_month")
    return w


def expected_range(window, D):
    y = shift_day(D, -1)
    if window == "yesterday":
        return y, y
    if window == "mtd":
        return month_first(y), y
    last_prev = shift_day(month_first(D), -1)
    return month_first(last_prev), last_prev


def default_range(D):
    """The dashboard's default view (Auto): the last 28 days ending yesterday. On the 29th of a month that is
    also the month to date (Oct 1 - Oct 28 on 2026-10-29), so equal numbers there are no evidence."""
    y = shift_day(D, -1)
    return shift_day(y, 1 - DEFAULT_DAYS), y


# ---------------------------------------------------------------- page parsing

def parse_num(s):
    """Page or sheet text -> (is_number, value, approx). Null words (No data, a dash) are a number line
    whose value is None. $ and % and commas are dropped; K/M/B suffixes multiply and set approx."""
    return parse_num_ex(s)[:3]


def parse_num_ex(s):
    """parse_num plus the rounding error of a compact number: half a display unit ('6.4K' -> 50.0)."""
    if s is None or isinstance(s, bool):
        return False, None, False, 0.0
    if isinstance(s, (int, float)):
        return True, float(s), False, 0.0
    t = norm_line(s)
    if not t:
        return False, None, False, 0.0
    if t.lower() in NULL_TOKENS:
        return True, None, False, 0.0
    neg = False
    if len(t) > 2 and t[0] == "(" and t[-1] == ")":   # accounting negative: (0.53%)
        neg, t = True, t[1:-1].strip()
    if t[0] in ("-", MINUS):
        neg, t = True, t[1:].strip()
    if t.startswith("$"):
        t = t[1:].strip()
    if not neg and t[:1] in ("-", MINUS):
        neg, t = True, t[1:].strip()
    if t.endswith("%"):
        t = t[:-1].strip()
    t = t.replace(",", "")
    if _GROUP_RE.match(t):
        t = t.replace(" ", "")
    m = _NUM_RE.match(t)
    if not m:
        return False, None, False, 0.0
    v = float(m.group(1))
    approx = bool(m.group(2))
    half = 0.0
    if approx:
        mult = SUFFIX[m.group(2).upper()]
        dec = len(m.group(1).split(".")[1]) if "." in m.group(1) else 0
        v = round(v * mult, 6)
        half = mult * 10 ** -dec / 2.0
    return True, (-v if neg else v), approx, half


def typed(v, typ):
    if v is None:
        return None
    if typ in ("money", "pct"):
        return float(v)
    return int(v) if float(v).is_integer() else v


def new_window(status, reason=None):
    return {"status": status, "reason": reason, "label": None, "start": None, "end": None, "read_at": None,
            "browser": None, "line": None, "values": {}, "approx": [], "approx_err": {}, "new_boxes": [],
            "missing_boxes": [], "empty_boxes": [], "unrendered_boxes": []}


def page_pairs(lines):
    out = []
    for j in range(len(lines) - 1):
        if not parse_num(lines[j])[0] and parse_num(lines[j + 1])[0]:
            out.append((lines[j], lines[j + 1]))
    return out


def _label_dates(m):
    try:
        a = dt.date(int(m.group(3)), MON3.index(m.group(1)) + 1, int(m.group(2))).isoformat()
        b = dt.date(int(m.group(6)), MON3.index(m.group(4)) + 1, int(m.group(5))).isoformat()
        return a, b
    except ValueError:
        return None, None


def _signin(text):
    return ("Sign in" in text and ("Google Account" in text or "accounts.google.com" in text)) \
        or any(p in text for p in SIGNIN_PHRASES)


def _access(text):
    return any(p in text for p in ACCESS_PHRASES)


def report_id(src):
    m = re.search(r"/reporting/([0-9A-Za-z-]{8,})", str(src.get("url") or ""))
    return m.group(1) if m else None


def parse_page(text, src, window, D, learn=False):
    """One get_page_text output -> a window record (status ok or invalid with a reason).

    Lines are normalized first (non-breaking and doubled spaces). The access checks run first on any page
    that is not the report itself; a page that shows the report title and a date range label is the
    report, so an access phrase on it is a box's error, judged with that box. Boxes: a config label
    followed by a number (or a null word) is found; a label with no number after it is unrendered (read
    before it loaded) or errored (a connector error in its place); a label absent from the page is missing
    (a layout change). The window is invalid when Clicks has no number or any additive NabThat box is
    unrendered, errored or empty; missing and new boxes only raise LAYOUT.

    window "default" is the page as first opened (the reference for cross_check): its label may read Select
    date range, which then anchors the boxes (or the title line does); a date label, if shown, is kept as
    its range but never checked against one."""
    r = new_window("invalid")
    text = text if isinstance(text, str) else ""
    if not text.strip():
        r["reason"] = "empty page"
        return r
    lines = [norm_line(l) for l in text.splitlines()]
    lines = [l for l in lines if l]
    at = next((i for i, l in enumerate(lines) if DATE_LABEL_RE.match(l)), None)
    title = norm_line(src.get("title_contains"))
    has_title = bool(title) and any(title in l for l in lines)
    if window == DEFAULT_WINDOW and at is None:
        at = next((i for i, l in enumerate(lines) if l == "Select date range"), None)
        if at is None and has_title:
            at = next(i for i, l in enumerate(lines) if title in l)
    if not (has_title and at is not None):
        joined = "\n".join(lines)
        if _signin(joined):
            r["reason"] = SIGNIN_REASON
            return r
        if _access(joined):
            r["reason"] = ACCESS_REASON
            return r
    if learn:
        r["learn"] = page_pairs(lines[(at + 1) if at is not None else 0:])
    if title and not has_title:
        rid = report_id(src)
        if rid and any(l.startswith("URL:") and ("/reporting/" + rid[:8]) in l for l in lines):
            r["reason"] = ("the report had not finished loading (its URL is open but no line shows %s yet); retry"
                           % title)
        else:
            r["reason"] = "not the expected report (no line contains %s)" % title
        return r
    if at is None:
        r["reason"] = DEFAULT_RANGE_REASON if "Select date range" in lines else \
            "no date range label on the page (it may not have finished loading; retry)"
        return r
    lm = DATE_LABEL_RE.match(lines[at])
    if window == DEFAULT_WINDOW:
        start, end = _label_dates(lm) if lm else (None, None)
        if start:
            r.update(label=scrub(lines[at]), start=start, end=end)
    else:
        label = scrub(lines[at])
        start, end = _label_dates(lm)
        if not start:
            r["reason"] = "no date range label on the page (%s is not a real date)" % label
            return r
        r.update(label=label, start=start, end=end)
        exp = expected_range(window, D)
        if (start, end) != exp:
            r["reason"] = "page showed %s, expected %s" % (label, fmt_range(*exp))
            return r
    after = lines[at + 1:]
    metrics = src.get("metrics") or []
    labels = set(norm_line(m["label"]) for m in metrics)
    values, approx, aerr, missing, empty, unrendered, errored = {}, [], {}, [], [], [], []
    for mt in metrics:
        lab, key = norm_line(mt["label"]), mt["key"]
        pos = [j for j, l in enumerate(after) if l == lab]
        hit = None
        for j in pos:
            if j + 1 < len(after):
                isn, v, ap, half = parse_num_ex(after[j + 1])
                if isn:
                    hit = (v, ap, half)
                    break
        if hit:
            v, ap, half = hit
            values[key] = typed(v, mt.get("type"))
            if ap:
                approx.append(key)
                aerr[key] = half
            if v is None:
                empty.append(mt["label"])
            continue
        values[key] = None
        if not pos:
            missing.append(mt["label"])
            continue
        nxt = after[pos[0] + 1] if pos[0] + 1 < len(after) else ""
        if nxt and nxt not in labels and any(w in nxt.lower() for w in ERROR_WORDS):
            errored.append((mt["label"], nxt))
        else:
            unrendered.append(mt["label"])
    new = []
    for j in range(len(after) - 1):
        l = after[j]
        if l in labels or l in NOISE or l in new or parse_num(l)[0]:
            continue
        if parse_num(after[j + 1])[0]:
            new.append(l)
    r.update(values=values, approx=approx, approx_err=aerr, new_boxes=new, missing_boxes=missing,
             empty_boxes=empty + [l for l, _ in errored], unrendered_boxes=unrendered)
    vend = [m for m in metrics if m.get("scope") == "vendor_ads"]
    vlabels = [m["label"] for m in vend]
    vadd = [m["label"] for m in vend if m.get("additive")]
    vendor = src.get("vendor") or "the vendor"
    if metrics and all(m["label"] in missing for m in metrics):
        r["reason"] = ("none of the dashboard's number boxes were on the page (the page may not have finished "
                       "loading, or the vendor changed the dashboard); retry, and if it repeats, tell Drew")
        return r
    acc = [l for l, t in errored if l in vlabels and _access(t)]
    if acc:
        r["reason"] = "%s on the data behind %s (a box said: %s)" % (ACCESS_REASON, ", ".join(acc),
                                                                     next(t for l, t in errored if l == acc[0]))
        return r
    un = [l for l in unrendered if l in vlabels]
    if un:
        r["reason"] = "page read before the numbers finished loading (%s had no number); retry" % ", ".join(un)
        return r
    bad = [l for l in vadd if l in empty or any(l == e for e, _ in errored)]
    ck = next((m for m in vend if m["key"] == "clicks"), None)
    if ck and ck["label"] in [e for e, _ in errored] + empty and ck["label"] not in bad:
        bad.insert(0, ck["label"])
    if bad:
        r["reason"] = ("%s's boxes showed no numbers (No data or a connector error: %s): the Google Ads connector "
                       "may have failed, the data had not loaded, or the account had no activity that day"
                       % (vendor, ", ".join(bad)))
        return r
    if ck and values.get("clicks") is None:
        r["reason"] = ("the dashboard lost its %s box (the vendor changed the dashboard); restatement, pace and the "
                       "credit split need clicks" % ck["label"])
        return r
    r["status"] = "ok"
    return r


def layout_text(w):
    bits = []
    if w.get("missing_boxes"):
        bits.append("missing boxes " + ", ".join(w["missing_boxes"]))
    if w.get("new_boxes"):
        bits.append("new boxes " + ", ".join(w["new_boxes"]))
    return "; ".join(bits)


# ---------------------------------------------------------------- reads and ingest

def read_lines(path):
    """-> (entries [(line, obj)] or None when the file is missing, bad [(line, why)], {line: source of a bad
    line when it could be read})."""
    if not os.path.exists(path):
        return None, [], {}
    entries, bad, bad_src = [], [], {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for n, raw in enumerate(f, 1):
            raw = raw.lstrip(chr(0xfeff))
            if not raw.strip():
                continue
            try:
                o = json.loads(raw)
            except ValueError:
                bad.append((n, "not valid JSON (a read may have been cut off)"))
                continue
            if not isinstance(o, dict) or not o.get("source") or o.get("window") not in WINDOWS + (DEFAULT_WINDOW,):
                bad.append((n, "not a read (needs source and window yesterday, mtd, last_month or default)"))
                continue
            wrong = [k for k in ("source", "text", "browser", "read_at", "url", "note")
                     if o.get(k) is not None and not isinstance(o.get(k), str)]
            if wrong:
                bad.append((n, "field %s is not text" % ", ".join(wrong)))
                bad_src[n] = o.get("source") if isinstance(o.get("source"), str) else None
                continue
            entries.append((n, o))
    return entries, bad, bad_src


def _stale_reason(what, k, a, b):
    return ("numbers did not refresh after the date preset (%s %s %s vs %s); the page was read before it reloaded"
            % (what, key_label(k), fnum(a), b))


def _prev_mtd(sid, D, start):
    """The newest snapshot before D with a valid mtd (or last_month) window starting on `start`."""
    h = Hist(sid, shift_day(D, -1))
    for d in reversed(h.dates()):
        for w in ("mtd", "last_month"):
            x = h.win(d, w, mark=False)
            if x and x.get("start") == start:
                return d, x
    return None, None


def _mtd_drop(src, win, prev_d, prev, window="mtd"):
    """A reason when this month-to-date (or last_month) read sits below an earlier read of the same month."""
    ea, eb = val_errs(win), val_errs(prev)
    for k in add_keys(src):
        a, b = (win.get("values") or {}).get(k), (prev.get("values") or {}).get(k)
        if a is None or b is None:
            continue
        if a < b - max(MIN_ABS.get(k, 0), STALE_PCT * abs(b)) - ea.get(k, 0.0) - eb.get(k, 0.0):
            return ("numbers did not refresh after the date preset (%s %s %s is below the %s read's %s); the page "
                    "was read before it reloaded" % (WLABEL[window], key_label(k), fnum(a), prev_d, fnum(b)))
    return None


def _default_match(src, D, window, r, dref):
    """Guard 1: a reason when two or more of r's additive NabThat boxes show exactly the default view's numbers
    and the window is not the default range itself (the month to date on the 29th is: equal numbers are then
    legitimate). A zero on both sides is no evidence and does not count. dref None (old nights): None."""
    if not dref:
        return None
    drange = (dref["start"], dref["end"]) if dref.get("start") else default_range(D)
    if expected_range(window, D) == drange:
        return None
    a, b = r.get("values") or {}, dref.get("values") or {}
    n = sum(1 for k in add_keys(src) if a.get(k) is not None and a.get(k) == b.get(k) and a.get(k) != 0)
    return DEFAULT_MATCH_REASON % n if n >= DEFAULT_MATCH_MIN else None


def _mtd_rise(src, D, r, Y):
    """Guard 2 for a month-to-date candidate r, given tonight's valid yesterday read Y. R = M(D) - M(D-1) - p(y)
    is how far earlier days restated overnight (mostly y - 1 settling), so it stays well inside all of y - 1's
    preliminary clicks (floor RISE_MIN_CLICKS). Beyond that either way, after widening by the compact-number
    rounding of every value involved, the page still showed another range. Needs last night's same-month month
    to date (so never on the 2nd) and its yesterday read; otherwise None. On the 1st the month to date is last
    month in full and last night's is that month through y - 1, so the same arithmetic holds."""
    if not Y:
        return None
    D1 = y = shift_day(D, -1)
    y1 = shift_day(D, -2)
    h = Hist(src["id"], D1)
    prev = h.win(D1, "mtd", mark=False)
    if not prev or prev.get("start") != r.get("start") or prev.get("end") != y1:
        return None
    p1 = h.win(D1, "yesterday", mark=False)
    if not p1 or p1.get("start") != y1 or p1.get("end") != y1:
        return None
    c = [(w.get("values") or {}).get("clicks") for w in (r, prev, Y, p1)]
    if None in c:
        return None
    m, mp, py, pp = c
    R = m - mp - py
    e = sum(val_errs(w).get("clicks", 0.0) for w in (r, prev, Y))
    lim = max(pp + val_errs(p1).get("clicks", 0.0), RISE_MIN_CLICKS)
    approx = " (approx, +/- %s)" % fnum(e) if e else ""
    if R - e > lim:
        return ("month to date rose %s clicks%s beyond the preliminary %s, more than all of %s's preliminary %s; the "
                "page likely still showed an older range; retry" % (fnum(R), approx, wd(y), wd(y1), fnum(pp)))
    if R + e < -lim:
        return ("month to date fell %s clicks%s short of the %s read (%s) plus the preliminary %s (%s), more than all "
                "of %s's preliminary %s; the page likely still showed an older range; retry"
                % (fnum(-R), approx, D1, fnum(mp), wd(y), fnum(py), wd(y1), fnum(pp)))
    return None


def cross_check(src, D, wins, cands, dref=None):
    """A read taken before the scorecards reloaded shows the new date label over the old numbers. Catch it by
    comparing windows: no window repeats the page's default view (dref, tonight's "default" line) unless it is
    that range; tonight's month to date never falls below last night's, nor moves from it by more than the
    preliminary yesterday plus a day's restatement (guard 2); yesterday never exceeds the month to date, and
    (past the 1st) yesterday never equals the month to date or last night's month to date. Among retries, the
    last read that passes wins; when none passes, the last one is marked invalid."""
    sid, keys = src["id"], add_keys(src)
    y = shift_day(D, -1)

    def fail(w, r, why):
        r.update(status="invalid", reason=why)
        if dref and why and why.startswith(DEFAULT_MATCH_REASON.split("(")[0]):
            r["default_line"] = dref.get("line")   # the reference read it matched, cited by line
        wins[w] = r

    def settle(w, pool, problem):
        """The last candidate with no problem wins; else the last one is marked invalid. -> the winner or None."""
        good = next((r for r in reversed(pool) if problem(r) is None), None)
        if good:
            wins[w] = good
        else:
            fail(w, dict(pool[-1]), problem(pool[-1]))
        return good

    prevs = {}
    for w in ("mtd", "last_month"):
        pool = cands.get(w) or []
        prevs[w] = _prev_mtd(sid, D, pool[-1]["start"]) if pool else (None, None)

    def month_problem(w, r):
        pd, prev = prevs[w]
        return _default_match(src, D, w, r, dref) or (_mtd_drop(src, r, pd, prev, w) if prev else None)

    if cands.get("last_month"):
        settle("last_month", cands["last_month"], lambda r: month_problem("last_month", r))
    pool = cands.get("yesterday") or []
    pm_d, pm = _prev_mtd(sid, D, month_first(y))
    last_d, last_m = None, None
    h = Hist(sid, shift_day(D, -1))
    lm_win = h.win(shift_day(D, -1), "mtd", mark=False)
    if lm_win and lm_win.get("start") != lm_win.get("end"):
        last_d, last_m = shift_day(D, -1), lm_win

    def problem(r, M):
        """-> (kind, reason) for a yesterday candidate against the month to date M (None: not read or invalid)."""
        dm = _default_match(src, D, "yesterday", r, dref)
        if dm:
            return "default", dm
        v = r.get("values") or {}
        ey = val_errs(r)
        if M:
            mv, em = M.get("values") or {}, val_errs(M)
            for k in keys:
                if v.get(k) is not None and mv.get(k) is not None and v[k] > mv[k] + ey.get(k, 0) + em.get(k, 0):
                    return "over", _stale_reason("yesterday", k, v[k], "month to date %s" % fnum(mv[k]))
            both = [k for k in keys if v.get(k) is not None and mv.get(k) is not None]
            if y[8:] != "01" and len(both) >= 2 and (v.get("clicks") or 0) > 0 and all(v[k] == mv[k] for k in both):
                return "same", _stale_reason("yesterday", "clicks", v["clicks"], "month to date %s" % fnum(mv["clicks"]))
        if last_m:
            lv = last_m.get("values") or {}
            both = [k for k in keys if v.get(k) is not None and lv.get(k) is not None]
            if len(both) >= 2 and (v.get("clicks") or 0) > 0 and all(v[k] == lv[k] for k in both):
                return "last", _stale_reason("yesterday", "clicks", v["clicks"], "the %s month to date %s"
                                             % (last_d, fnum(lv["clicks"])))
            span = days_between(last_m["start"], last_m["end"]) + 1
            lc = lv.get("clicks")
            if span >= 7 and lc is not None and (v.get("clicks") or 0) > lc + ey.get("clicks", 0) + \
                    val_errs(last_m).get("clicks", 0):
                return "last", _stale_reason("yesterday", "clicks", v["clicks"], "the %s month to date %s, which "
                                             "covers %d days" % (last_d, fnum(lc), span))
        return None, None

    def yesterday_for(M):
        return next((r for r in reversed(pool) if problem(r, M)[0] is None), None)

    # month to date: the default view, the drop below last night's, then guard 2 against the yesterday read
    # that passes with this very candidate (a stale yesterday that fails against it is not used as p(y))
    M = None
    if cands.get("mtd"):
        M = settle("mtd", cands["mtd"],
                   lambda r: month_problem("mtd", r) or _mtd_rise(src, D, r, yesterday_for(r)))
    if not pool:
        return
    good = yesterday_for(M)
    if good:
        wins["yesterday"] = good
        return
    kind, why = problem(pool[-1], M)
    fail("yesterday", dict(pool[-1]), why)
    if kind == "same" and M is not None and not pm:
        # no earlier month to date to say which of the two is stale: neither is trusted
        fail("mtd", dict(M), "month to date showed the same numbers as the yesterday read (clicks %s); one of the "
                             "two was read before the page reloaded" % fnum(M["values"].get("clicks")))


def evaluate(cfg, D, reads_path, learn=False):
    """Parse every active source's reads for shift D. Nothing is written (earlier snapshots are read for
    the cross-window check)."""
    entries, bad, bad_src = read_lines(reads_path)
    exists = entries is not None
    ids = dict((s["id"], s) for s in cfg["sources"])
    keep = []
    for n, o in entries or []:
        s = ids.get(o.get("source"))
        if not s:
            bad.append((n, "source %s is not in vendor-dashboards.json" % o.get("source")))
        elif s.get("status") != "active":
            bad.append((n, "source %s is not active (status %s)" % (o.get("source"), s.get("status"))))
        else:
            keep.append((n, o))
    bad.sort()
    out = {}
    for src in active_sources(cfg):
        sid = src["id"]
        mine = [(n, o) for n, o in keep if o.get("source") == sid]
        unread = [n for n, why in bad if bad_src.get(n) in (None, sid) and "is not active" not in why]
        bad_nums = ", ".join(str(n) for n in unread)
        order = expected_windows(D)
        order += [w for w in WINDOWS if w not in order and any(o["window"] == w for _, o in mine)]
        wins, cands = {}, {}
        for w in order:
            lines = [(n, o) for n, o in mine if o["window"] == w]
            if not lines:
                if not exists:
                    why = DID_NOT_RUN
                elif unread:
                    why = "no parseable %s read; reads.jsonl line%s %s could not be parsed" % (
                        WLABEL[w], "s" if len(unread) > 1 else "", bad_nums)
                else:
                    why = "no %s read for this source in reads.jsonl" % WLABEL[w]
                wins[w] = new_window("missing", why)
                continue
            chosen = last = None
            for n, o in lines:
                r = parse_page(o.get("text"), src, w, D, learn=learn)
                r.update(read_at=o.get("read_at"), browser=o.get("browser"), line=n)
                last = r
                if r["status"] == "ok":
                    chosen = r
                    cands.setdefault(w, []).append(r)
            res = chosen or last
            wins[w] = res
            for r in cands.get(w, []) + [last]:
                r["attempts"] = len(lines)
        # the default view (the page as first opened): a reference only, never a window or a bad line; the last
        # one that parsed with its boxes wins, and one that did not is simply not used
        dref = None
        for n, o in mine:
            if o["window"] == DEFAULT_WINDOW:
                r = parse_page(o.get("text"), src, DEFAULT_WINDOW, D)
                if r["status"] == "ok":
                    r.update(read_at=o.get("read_at"), browser=o.get("browser"), line=n)
                    dref = r
        cross_check(src, D, wins, cands, dref)
        out[sid] = wins
    return {"exists": exists, "bad": bad, "sources": out, "reads_path": reads_path}


def reads_ok(cfg, D, ev):
    if not ev["exists"]:
        return False
    for src in active_sources(cfg):
        wins = ev["sources"].get(src["id"]) or {}
        if any((wins.get(w) or {}).get("status") != "ok" for w in expected_windows(D)):
            return False
    return True


def write_snapshots(D, ev):
    """vendor-dash/{D}/{source}.json per active source, only when the reads file exists."""
    if not ev["exists"]:
        return []
    paths = []
    for sid, wins in ev["sources"].items():
        clean = {w: {k: v for k, v in r.items() if k != "learn"} for w, r in wins.items()}
        snap = {"source": sid, "date": D, "yesterday": shift_day(D, -1), "ingested_at": now_iso(),
                "reads_file": rel(ev["reads_path"]), "windows": clean}
        path = VD(D, sid + ".json")
        old = load_json(path)
        if isinstance(old, dict):
            a = {k: v for k, v in old.items() if k != "ingested_at"}
            b = scrub(json.loads(json.dumps({k: v for k, v in snap.items() if k != "ingested_at"})))
            if a == b and old.get("ingested_at"):
                snap["ingested_at"] = old["ingested_at"]   # idempotent: same content, same stamp
        save_json(path, snap)
        paths.append(path)
    return paths


def window_line(sid, w, r):
    if r["status"] == "ok":
        s = "%s %s: ok, %s (line %s, read %s)" % (sid, w, r["label"], r["line"], read_desc(r))
        if layout_text(r):
            s += "; LAYOUT: " + layout_text(r)
        return s
    if r["status"] == "missing":
        return "%s %s: MISSING, %s" % (sid, w, r["reason"])
    return "%s %s: INVALID, %s (line %s)" % (sid, w, r["reason"], r.get("line"))


def cmd_status(args):
    D = iso(args.date) if args.date else pacific_today().isoformat()
    cfg = load_config()
    ev = evaluate(cfg, D, VD(D, "reads.jsonl"))
    for src in cfg["sources"]:
        head = "%s (%s, %s)" % (src["id"], src.get("vendor"), src.get("store"))
        if src.get("status") != "active":
            say("%s: %s" % (head, waiting_text(src)))
            continue
        if not ev["exists"]:
            say("%s: READ_MISSING, no read for %s: %s" % (head, D, DID_NOT_RUN))
            continue
        for w, r in ev["sources"][src["id"]].items():
            say(window_line(src["id"], w, r))
    for n, why in ev["bad"]:
        say("reads.jsonl line %d: %s, skipped" % (n, why))
    return 0 if reads_ok(cfg, D, ev) else 2


def cmd_ingest(args):
    D = iso(args.date) if args.date else pacific_today().isoformat()
    cfg = load_config()
    reads = os.path.abspath(args.reads) if args.reads else VD(D, "reads.jsonl")
    ev = evaluate(cfg, D, reads, learn=args.learn)
    paths = write_snapshots(D, ev)
    if not ev["exists"]:
        say("no reads file %s: %s" % (rel(reads), DID_NOT_RUN))
    for sid, wins in ev["sources"].items():
        for w, r in wins.items():
            if ev["exists"]:
                say(window_line(sid, w, r))
            if args.learn and r.get("learn"):
                say("  %s %s label/value pairs:" % (sid, w))
                for lab, val in r["learn"]:
                    say("    %s = %s" % (lab, val))
    for n, why in ev["bad"]:
        say("%s line %d: %s, skipped" % (rel(reads), n, why))
    for p in paths:
        say("wrote %s" % rel(p))
    return 0 if reads_ok(cfg, D, ev) else 2


# ---------------------------------------------------------------- history

class Hist(object):
    """Snapshots of one source dated on or before `upto`, loaded lazily. `used` records what was read."""

    def __init__(self, sid, upto):
        self.sid, self.upto = sid, upto
        self._snaps, self._dates, self._r = {}, None, {}
        self.used = {}

    def dates(self):
        if self._dates is None:
            found = []
            if os.path.isdir(VD()):
                for d in sorted(os.listdir(VD())):
                    if DATE_RE.match(d) and d <= self.upto and os.path.exists(VD(d, self.sid + ".json")):
                        found.append(d)
            self._dates = found
        return self._dates

    def forget(self, date):
        self._snaps[date] = None
        self._dates = [d for d in self.dates() if d != date]

    def snap(self, date):
        if not date or date > self.upto:
            return None
        if date not in self._snaps:
            s = load_json(VD(date, self.sid + ".json"))
            self._snaps[date] = s if isinstance(s, dict) else None
        return self._snaps[date]

    def win(self, date, window, mark=True):
        s = self.snap(date)
        w = ((s or {}).get("windows") or {}).get(window)
        if isinstance(w, dict) and w.get("status") == "ok":
            if mark:
                self.used.setdefault(date, {})[window] = (s.get("reads_file"), w.get("line"))
            return w
        return None

    def p(self, day):
        """The preliminary read of `day`: the yesterday window of the snapshot dated day + 1."""
        w = self.win(shift_day(day, 1), "yesterday")
        return w if w and w.get("start") == day and w.get("end") == day else None

    def M(self, date):
        return self.win(date, "mtd")

    def last_ok(self, window, before):
        for d in reversed(self.dates()):
            if d < before and self.win(d, window, mark=False):
                return d
        return None


def val_errs(w):
    """Rounding error per key: half a display unit for a compact number ('6.4K' is 6,350 to 6,450, so 50).
    A snapshot written before approx_err existed: assume one decimal of the K, M or B the page showed."""
    w = w or {}
    e = dict(w.get("approx_err") or {})
    for k in w.get("approx") or []:
        if k not in e:
            x = abs((w.get("values") or {}).get(k) or 0)
            e[k] = (1e9 if x >= 1e9 else 1e6 if x >= 1e6 else 1e3) / 20.0 if x else 0.0
    return e


def vals(w):
    """Window values plus implied cost (clicks x avg CPC). Its error: the CPC is shown rounded to the cent
    (half a cent per click), plus half a display unit when clicks or the CPC was shown compact."""
    if not w:
        return None
    v = dict(w.get("values") or {})
    e = val_errs(w)
    c, cpc, imp, calls = v.get("clicks"), v.get("avg_cpc"), v.get("impressions"), v.get("phone_calls")
    ce, pe = e.get("clicks", 0.0), CPC_ROUNDING + e.get("avg_cpc", 0.0)
    v["implied_cost"] = r2(c * cpc) if c is not None and cpc is not None else None
    if c is not None and cpc is not None:
        v["implied_cost_err"] = r2(c * pe + ce * abs(cpc) + ce * pe)
    else:
        v["implied_cost_err"] = r2(c * CPC_ROUNDING) if c is not None else None
    v["ctr_calc"] = round(c / imp * 100, 4) if c is not None and imp else None
    v["calls_per_100_clicks"] = round(calls / c * 100, 2) if calls is not None and c else None
    return v


def errs(w, keys):
    """{key: rounding error} for a window: compact-number halves, and implied cost's error."""
    e = val_errs(w)
    v = vals(w) or {}
    return {k: (v.get("implied_cost_err") or 0.0) if k == "implied_cost" else e.get(k, 0.0) for k in keys}


def approx_keys(w):
    a = set((w or {}).get("approx") or [])
    if a & {"clicks", "avg_cpc"}:
        a.add("implied_cost")
    return a


def restatement(hist, src, Dn):
    if Dn not in hist._r:
        hist._r[Dn] = _restatement(hist, src, Dn)
    return hist._r[Dn]


def _restatement(hist, src, Dn):
    M = hist.M(Dn)
    if not M:
        return {"status": "no_mtd", "why": "no valid month-to-date read in the %s snapshot" % Dn}
    prev = [d for d in hist.dates() if d < Dn and (hist.win(d, "mtd", mark=False) or {}).get("start") == M["start"]]
    if not prev:
        return {"status": "no_baseline", "why": "no baseline this month yet (the %s month to date starts %s)"
                % (Dn, M["start"])}
    Dp = prev[-1]
    Mp = hist.M(Dp)
    gap = daterange(shift_day(Mp["end"], 1), M["end"])
    read = [g for g in gap if hist.p(g)]
    unread = [g for g in gap if g not in read]
    wins = [M, Mp] + [hist.p(g) for g in read]
    vM, vP = vals(M), vals(Mp)
    vg = [vals(hist.p(g)) for g in read]
    keys = r_keys(src)
    out = {}
    for k in keys:
        parts = [vM.get(k), vP.get(k)] + [v.get(k) for v in vg]
        out[k] = None if any(x is None for x in parts) else tidy(vM[k] - vP[k] - sum(v[k] for v in vg))
    err = {k: r2(sum(errs(x, [k])[k] for x in wins)) for k in keys}
    approx = sorted(set().union(*[approx_keys(x) for x in wins]) & set(keys))
    return {"status": "ok" if not unread else "partial", "prev": Dp, "prev_label": Mp.get("label"),
            "label": M.get("label"), "gap": gap, "read": read, "unread": unread, "values": out,
            "implied_cost_err": err.get("implied_cost") if out.get("implied_cost") is not None else None,
            "err": err, "approx": approx}


def _month_end_restatement(hist, src, day):
    """The last day of a month has no same-month baseline two nights later (the 2nd starts a new month to
    date). Its one-night restatement is the 2nd's last_month read minus the 1st's month to date (on the 1st
    the month to date is the closed month in full)."""
    Dn, D1 = shift_day(day, 2), shift_day(day, 1)
    lm, m1 = hist.win(Dn, "last_month"), hist.M(D1)
    first = month_first(day)
    if not (lm and m1 and lm.get("start") == first and lm.get("end") == day and m1.get("start") == first
            and m1.get("end") == day):
        return None
    vL, v1 = vals(lm), vals(m1)
    keys = r_keys(src)
    out = {k: tidy(vL[k] - v1[k]) if None not in (vL.get(k), v1.get(k)) else None for k in keys}
    err = {k: r2(errs(lm, [k])[k] + errs(m1, [k])[k]) for k in keys}
    approx = sorted((approx_keys(lm) | approx_keys(m1)) & set(keys))
    return {"status": "ok", "prev": D1, "values": out, "err": err, "approx": approx,
            "implied_cost_err": err.get("implied_cost"), "via": "last_month"}


def settled(hist, src, day):
    """p(day) plus the restatement measured the night after it was preliminary (approx)."""
    p = hist.p(day)
    if not p:
        return None, "no preliminary read of %s (the %s snapshot is missing or invalid)" % (wd(day), shift_day(day, 1))
    Dn = shift_day(day, 2)
    R = _month_end_restatement(hist, src, day) if day == month_last(day) else None
    if R is None:
        R = restatement(hist, src, Dn)
        if R["status"] in ("no_mtd", "no_baseline"):
            why = R["why"]
            if day == month_last(day):
                why += ("; %s is the last day of its month, which settles only from the %s last-month read minus "
                        "the %s month to date" % (wd(day), Dn, shift_day(day, 1)))
            return None, why
        if R["status"] != "ok":
            return None, ("the restatement measured on %s also holds the unread %s, so it cannot be pinned to %s"
                          % (Dn, ", ".join(wd(g) for g in R["unread"]), wd(day)))
        if R["prev"] != shift_day(Dn, -1):
            return None, ("the restatement measured on %s spans more than one night (baseline %s), so it cannot be "
                          "pinned to %s" % (Dn, R["prev"], wd(day)))
    v = vals(p)
    keys = r_keys(src)
    s = {k: (tidy(v[k] + R["values"][k]) if v.get(k) is not None and R["values"].get(k) is not None else None)
         for k in keys}
    pe = errs(p, keys)
    err = {k: r2(pe[k] + (R.get("err") or {}).get(k, 0.0)) for k in keys}
    approx = sorted((approx_keys(p) | set(R.get("approx") or [])) & set(keys))
    return {"day": day, "values": s, "preliminary": {k: v.get(k) for k in keys}, "restated": dict(R["values"]),
            "prelim_snapshot": shift_day(day, 1), "restated_snapshot": Dn, "err": err, "approx": approx,
            "implied_cost_err": err.get("implied_cost") if s.get("implied_cost") is not None else None,
            "via": R.get("via", "mtd")}, None


def nab_window(hist, Dn):
    """Vendor clicks and implied cost from the 1st of y's month through y - 1 (the last complete day).
    The numbers are returned as computed, even below zero: split_section refuses to split on them."""
    y_n = shift_day(Dn, -1)
    M, p = hist.M(Dn), hist.p(y_n)
    if M and p:
        vm, vp = vals(M), vals(p)
        if None not in (vm["clicks"], vp["clicks"], vm["implied_cost"], vp["implied_cost"]):
            return {"clicks": vm["clicks"] - vp["clicks"], "implied_cost": r2(vm["implied_cost"] - vp["implied_cost"]),
                    "basis": "the %s month-to-date read minus the preliminary %s" % (Dn, wd(y_n))}
    Mp = hist.M(shift_day(Dn, -1))
    if Mp and Mp["end"] == shift_day(y_n, -1) and Mp["start"] == month_first(y_n):
        vm = vals(Mp)
        if vm["clicks"] is not None and vm["implied_cost"] is not None:
            return {"clicks": vm["clicks"], "implied_cost": vm["implied_cost"],
                    "basis": "the %s month-to-date read (tonight's pair was not both valid)" % shift_day(Dn, -1)}
    return None


def pace_calc(clicks, cpc, y, fee, cap, err=None):
    """Month to date and straight-line pace. fee None (unknown): no including-fees figure and no cap check."""
    cost = r2(clicks * cpc)
    elapsed, dim = int(y[8:]), dim_of(y)
    pace = r2(cost * dim / elapsed)
    e = r2(clicks * CPC_ROUNDING) if err is None else r2(err)
    mtd_f = r2(cost * (1 + fee)) if fee is not None else None
    pace_f = r2(pace * (1 + fee)) if fee is not None else None
    return {"implied_cost": cost, "implied_cost_err": e, "days_elapsed": elapsed,
            "days_in_month": dim, "pace_straight_line": pace, "pace_err": r2(e * dim / elapsed), "fee_rate": fee,
            "mtd_incl_fees": mtd_f, "pace_incl_fees": pace_f, "cap": cap,
            "mtd_over_cap": cap is not None and mtd_f is not None and mtd_f > cap,
            "pace_over_cap": cap is not None and pace_f is not None and pace_f > cap * PACE_TOLERANCE}


def flag(code, text, file):
    return {"code": code, "text": text, "file": file}


# ---------------------------------------------------------------- sheets

def cell(row, i):
    if not row or i < 0 or i >= len(row) or row[i] is None:
        return ""
    return str(row[i]).strip()


def cellnum(row, j):
    isn, v, _ = parse_num(cell(row, j))
    if not isn or v is None:
        return None
    return int(v) if float(v).is_integer() else v


def month_num(name):
    n = str(name or "").strip().lower()
    if len(n) < 3:
        return None
    for i, m in enumerate(MONTHS):
        if n == m.lower() or m.lower().startswith(n):
            return i + 1
    return None


def parse_nab_sheet(values, block, y):
    """NabThat's monthly sheet: the block's month columns, newest first, years inferred from y.
    Newest month = the last column whose Ad Spend is filled (a $0.00 placeholder counts as not filled). A
    blank month header is inferred as the column before it plus one month, with a note. A newest column
    with Ad Spend but no Fees yet is noted as being filled."""
    rows = values or []
    start = next((i for i, r in enumerate(rows) if cell(r, 0).upper() == block.strip().upper()), None)
    if start is None:
        raise ValueError("block %s not found" % block)
    header = rows[start]
    series = {}
    for r in rows[start + 1:]:
        if not any(cell(r, j) for j in range(len(r or []))):
            break
        first = cell(r, 0)
        if first.upper().startswith("NEW CENTURY") and first == first.upper():
            break
        key = NAB_ROWS.get(first.lower())
        if key and key not in series:
            series[key] = r
    spend = series.get("ad_spend")
    if not spend:
        raise ValueError("no Ad Spend row under %s" % block)
    filled = [j for j in range(1, len(spend)) if cellnum(spend, j)]
    if not filled:
        raise ValueError("the Ad Spend row under %s is empty" % block)
    newest = filled[-1]
    notes = []
    mnew = month_num(cell(header, newest))
    if not mnew:
        back = next((j for j in range(newest - 1, 0, -1) if month_num(cell(header, j))), None)
        if back is None or cell(header, newest):
            raise ValueError("column %d header %r is not a month" % (newest, cell(header, newest)))
        mnew = (month_num(cell(header, back)) - 1 + (newest - back)) % 12 + 1
        notes.append("column %d has no month header yet; read as %s (the month after the column before it)"
                     % (newest, MONTHS[mnew - 1]))
    year = int(y[:4]) if mnew <= int(y[5:7]) else int(y[:4]) - 1
    months = []
    for j in range(newest, 0, -1):
        yr, mm = divmod(year * 12 + (mnew - 1) - (newest - j), 12)
        mm += 1
        hdr = month_num(cell(header, j))
        if hdr is not None and hdr != mm:
            notes.append("column %d says %s, expected %s" % (j, cell(header, j), MONTHS[mm - 1]))
        v = {key: cellnum(series.get(key), j) for key in NAB_ROWS.values()}
        sp, fe, cl = v["ad_spend"], v["fees"], v["clicks"]
        v["total"] = r2(sp + fe) if sp is not None and fe is not None else None
        v["fee_rate"] = round(fe / sp, 4) if sp and fe is not None else None
        v["cpc"] = r2(sp / cl) if sp is not None and cl else None
        months.append({"ym": "%04d-%02d" % (yr, mm), "month": MONTHS[mm - 1], "year": yr, "col": j, "values": v})
    nv = months[0]["values"]
    if nv["fees"] is None or nv["clicks"] is None:
        what = [k.replace("_", " ") for k in ("fees", "clicks") if nv[k] is None]
        notes.append("the %s %d column is being filled (ad spend only so far; no %s yet)"
                     % (months[0]["month"], months[0]["year"], " or ".join(what)))
    return {"kind": "nabthat", "block": block, "months": months, "notes": notes}


def month_key(t, pattern):
    m = re.compile(pattern).match(str(t).strip())
    if not m or not month_num(m.group(1)):
        return None
    return int(m.group(2)), month_num(m.group(1))


def pick_tabs(titles, pattern, y=None):
    """Tabs matching the pattern, newest first. With y, tabs for y's month or later are left out: the sheet
    is filled after a month closes, so they are templates or half filled. The 2024 quarter tabs never count."""
    out = []
    for t in titles:
        tt = str(t).strip()
        if tt.startswith("Jul-Sep") or tt.startswith("Oct-Dec"):
            continue   # 2024 tabs, never current
        key = month_key(tt, pattern)
        if key:
            out.append((key, t))
    out.sort(key=lambda x: x[0], reverse=True)
    if y:
        cut = (int(y[:4]), int(y[5:7]))
        return [t for k, t in out if k < cut], [t for k, t in out if k >= cut]
    return [t for _, t in out], []


def pick_tab(titles, pattern, y=None):
    ok = pick_tabs(titles, pattern, y)[0]
    return ok[0] if ok else None


def _con_row(raw):
    v = {}
    for k, x in zip(CON_KEYS, raw):
        isn, n, _ = parse_num(x)
        v[k] = (int(n) if float(n).is_integer() else n) if isn and n is not None else None
    v["cpc"] = r2(v["ad_spend"] / v["clicks"]) if v["ad_spend"] is not None and v["clicks"] else None
    return v


CON_TOTAL_NAMES = ("total", "grand total")
CON_TOL = {"ad_spend": 1.0}   # counts tie within 1


def parse_con_sheet(values, block, tab):
    """Constellation's monthly tab: the SEM block's campaigns, classes, total row and summary tie-out.
    The total row is the first row after the campaigns with a blank or 'Total' name and a number under Ad
    Spend. The block ends at the total row, or at another block's header (raises: no total row). A blank
    campaign cell stays blank (never 0): the class value is then derived as the total row minus the other
    class, or left unknown, with a note. The classes must add up to the total row (spend within $1, counts
    within 1), or the tab does not parse."""
    rows = values or []
    pos = None
    for i, r in enumerate(rows):
        j = next((j for j in range(len(r or [])) if cell(r, j) == block), None)
        if j is not None:
            pos = (i, j)
            break
    if not pos:
        raise ValueError("block %s not found" % block)
    r0, c = pos
    if c < 1:
        raise ValueError("block %s has no name column to its left" % block)
    if cell(rows[r0 + 1] if r0 + 1 < len(rows) else [], c) != "Ad Spend":
        raise ValueError("no Ad Spend header under %s" % block)
    section, camps, total, notes = None, [], None, []
    for n, r in enumerate(rows[r0 + 2:], r0 + 3):
        name = cell(r, c - 1)
        raw = [cell(r, c + k) for k in range(len(CON_KEYS))]
        spend_isn, spend_v, _ = parse_num(raw[0])
        numeric = spend_isn and spend_v is not None
        if raw[0] == "Ad Spend" or raw[0].endswith("(SEM)") or name.endswith("(SEM)"):
            break   # the next block's header: this block has no total row
        if (not name or name.lower() in CON_TOTAL_NAMES) and numeric and camps:
            total = _con_row(raw)
            break
        if name and name.lower() in CON_TOTAL_NAMES:
            continue
        if name and not any(raw):
            section = name
            continue
        if name:
            row = {"section": section, "name": name,
                   "class": "vla" if "vehicle ads" in name.lower() else "untagged"}
            row.update(_con_row(raw))
            camps.append(row)
            continue
        if any(raw):
            notes.append("row %d under %s skipped (no campaign name; %s)" % (n, block, raw[0] or "text"))
    if not camps:
        raise ValueError("no campaign rows under %s" % block)
    if total is None:
        raise ValueError("no total row under %s" % block)
    totals = {}
    blanks = {}
    for cls in ("vla", "untagged"):
        mine = [x for x in camps if x["class"] == cls]
        t = {"campaigns": len(mine)}
        for k in CON_KEYS:
            miss = [x["name"] for x in mine if x[k] is None]
            blanks[(cls, k)] = miss
            t[k] = None if miss else tidy(float(sum(x[k] for x in mine)))
        totals[cls] = t
    label = {"vla": "vehicle listing ads", "untagged": "untagged campaigns"}
    for k in CON_KEYS:
        for cls, other in (("vla", "untagged"), ("untagged", "vla")):
            miss = blanks[(cls, k)]
            if not miss:
                continue
            col = k.replace("_", " ")
            if totals[other][k] is not None and total.get(k) is not None:
                totals[cls][k] = tidy(float(total[k] - totals[other][k]))
                notes.append("%s is blank for %s; %s %s derived as the total row minus the %s"
                             % (col, ", ".join(miss), label[cls], col, label[other]))
            else:
                notes.append("%s is blank for %s; %s %s unknown" % (col, ", ".join(miss), label[cls], col))
    for k in CON_KEYS:
        a, b, t = totals["vla"][k], totals["untagged"][k], total.get(k)
        if None not in (a, b, t) and abs(a + b - t) > CON_TOL.get(k, 1):
            raise ValueError("the campaign rows add to %s %s, not the total row's %s"
                             % (fnum(a + b) if k != "ad_spend" else money(a + b, True), k.replace("_", " "),
                                fnum(t) if k != "ad_spend" else money(t, True)))
    for cls in ("vla", "untagged"):
        t = totals[cls]
        t["cpc"] = r2(t["ad_spend"] / t["clicks"]) if t["ad_spend"] is not None and t["clicks"] else None
    totals["all"] = dict(total, campaigns=len(camps))
    dealer = re.sub(r"\s*\(SEM\)\s*$", "", block).strip()
    summary = None
    for i, r in enumerate(rows):
        if cell(r, 0) != dealer:
            continue
        h = next((h for h in range(i - 1, -1, -1)
                  if any(cell(rows[h], j) == "Spend" for j in range(len(rows[h] or [])))), None)
        if h is not None:
            hdr = rows[h]
            s = next(j for j in range(len(hdr)) if cell(hdr, j) == "Spend")
            width = max(len(hdr), len(r))
            nxt = next((j for j in range(s + 1, width) if cell(hdr, j)), width)
            for j in range(s, nxt):
                isn, v, _ = parse_num(cell(r, j))
                if isn and v is not None:
                    summary = v
                    break
        break
    ties = summary is not None and total["ad_spend"] is not None and abs(summary - total["ad_spend"]) <= 1.0
    m = re.match(r"^\s*([A-Za-z]+) (\d{4})", tab or "")
    mn, yr = (month_num(m.group(1)), int(m.group(2))) if m else (None, None)
    flat = {}
    for cls in ("all", "vla", "untagged"):
        for k in CON_KEYS:
            flat[k if cls == "all" else "%s_%s" % (cls, k)] = totals[cls][k]
    ym = "%04d-%02d" % (yr, mn) if mn else None
    return {"kind": "constellation", "tab": tab, "block": block, "month": MONTHS[mn - 1] if mn else None,
            "month_num": mn, "year": yr, "ym": ym, "campaigns": camps, "totals": totals,
            "summary_spend": summary, "ties": ties, "notes": notes,
            "months": [{"ym": ym, "month": MONTHS[mn - 1] if mn else None, "year": yr, "values": flat}] if ym else []}


def parse_sheet(src, values, tab, y):
    sh = src["sheet"]
    if sh.get("tab_pattern"):
        return parse_con_sheet(values, sh["block"], tab)
    return parse_nab_sheet(values, sh["block"], y)


def sheet_snapshot_dates(sid, upto):
    out = []
    if os.path.isdir(VD()):
        for d in sorted(os.listdir(VD())):
            if DATE_RE.match(d) and d <= upto and os.path.exists(VD(d, sid + ".sheet.json")):
                out.append(d)
    return out


def sheet_compare(sid, D, parsed):
    prev = [d for d in sheet_snapshot_dates(sid, D) if d < D]
    if not prev:
        return {"first": True, "prev_date": None, "new_months": [], "changed": []}
    pj = load_json(VD(prev[-1], sid + ".sheet.json")) or {}
    old = {m["ym"]: m["values"] for m in pj.get("months") or [] if m.get("ym")}
    new = {m["ym"]: m["values"] for m in parsed.get("months") or [] if m.get("ym")}
    top = max(old) if old else ""
    new_months = sorted(ym for ym in new if ym > top)
    changed = []
    for ym in sorted(set(old) & set(new)):
        for k in sorted(set(old[ym]) | set(new[ym])):
            if k in SHEET_DERIVED:
                continue
            a, b = old[ym].get(k), new[ym].get(k)
            if a is None and b is None:
                continue
            if a is None or b is None or abs(a - b) > 0.005:
                changed.append({"ym": ym, "key": k, "before": a, "after": b,
                                "delta": tidy(b - a) if a is not None and b is not None else None})
    return {"first": False, "prev_date": prev[-1], "new_months": new_months, "changed": changed}


# ---------------------------------------------------------------- pulls (read-only, through gdata.py)

def guarded(fn):
    """Run a gdata call; gdata.die raises SystemExit, so both are caught. Returns (value, reason)."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stderr(buf):
            return fn(), None
    except SystemExit as e:
        msg = buf.getvalue().strip().replace("ERROR: ", "") or "gdata stopped (exit %s)" % e.code
        return None, " ".join(msg.split())[:300]
    except Exception as e:
        return None, " ".join(str(e).split())[:300] or e.__class__.__name__


_GDATA_STUB = None   # the selftest puts a stub here: the pull paths run with no import and no network


def _gdata():
    if _GDATA_STUB is not None:
        return _GDATA_STUB
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import gdata  # noqa: E402  (same folder, read-only scopes; never imported with --no-pull)
    return gdata


MAX_TABS = 3   # Constellation: at most this many closed-month tabs are tried, newest first


def pull_sheet(src, D, y, out_dir):
    """-> (parsed or None, reason or None, raw_path or None). Constellation: closed-month tabs newest first
    (a tab for y's month or later is skipped: the sheet is filled after the month closes); the first tab
    that parses with clicks above 0 and ties to the summary table wins (else the first that parses with
    clicks), and every skipped tab is named in the notes."""
    sh = src["sheet"]
    notes = []

    def values_of(g, rng):
        res = g.api("https://sheets.googleapis.com/v4/spreadsheets/%s/values/%s"
                    % (sh["id"], urllib.parse.quote(rng, safe="")))
        return res.get("values", [])

    def work():
        g = _gdata()
        if not sh.get("tab_pattern"):
            return [{"tab": None, "range": sh["range"], "values": values_of(g, sh["range"])}]
        meta = g.api("https://sheets.googleapis.com/v4/spreadsheets/%s?fields=sheets.properties.title" % sh["id"])
        titles = [x["properties"]["title"] for x in meta.get("sheets", [])]
        ok, future = pick_tabs(titles, sh["tab_pattern"], y)
        for t in future:
            notes.append("%s tab skipped: that month has not closed yet" % t)
        if not ok:
            raise RuntimeError("no closed-month tab matches %s" % sh["tab_pattern"])
        got = []
        for t in ok[:MAX_TABS]:
            rng = "'%s'!%s" % (t, sh.get("range_cols") or "A1:AD80")
            got.append({"tab": t, "range": rng, "values": values_of(g, rng)})
            try:
                p = parse_sheet(src, got[-1]["values"], t, y)
                if (p["totals"]["all"].get("clicks") or 0) > 0 and p["ties"]:
                    break
            except ValueError:
                pass
        return got

    got, err = guarded(work)
    if err:
        return None, err, None
    chosen, fallback, last_err = None, None, None
    for g in got:
        try:
            p = parse_sheet(src, g["values"], g["tab"], y)
        except ValueError as e:
            if g["tab"]:
                notes.append("%s tab did not parse: %s" % (g["tab"], e))
            else:
                last_err = e
            continue
        if not g["tab"]:
            chosen = (g, p)
            break
        clicks = p["totals"]["all"].get("clicks") or 0
        if clicks > 0 and p["ties"]:
            chosen = (g, p)
            break
        if clicks > 0 and fallback is None:
            fallback = (g, p)
        notes.append("%s tab skipped: %s" % (g["tab"], "no clicks in the BMW block yet (a template or not filled in)"
                                             if clicks <= 0 else "its BMW total does not tie to the summary table"))
    if chosen is None and fallback is not None:
        chosen = fallback
        notes = [n for n in notes if not n.startswith(fallback[0]["tab"] + " tab skipped: its BMW")]
    use = chosen[0] if chosen else got[0]
    raw_path = os.path.join(out_dir, "vendor_sheet_%s.json" % src["id"])
    save_json(raw_path, {"source": src["id"], "sheet_title": sh.get("title"), "tab": use["tab"],
                         "range": use["range"], "pulled_at": now_iso(), "values": use["values"],
                         "tabs_tried": [g["tab"] for g in got if g["tab"]], "notes": notes})
    if not chosen:
        if got[0]["tab"]:
            return None, "read tonight, but no closed-month tab parsed (%s)" % "; ".join(notes), raw_path
        return None, "read tonight, but the sheet did not parse: %s" % last_err, raw_path
    parsed = chosen[1]
    parsed["notes"] = list(parsed.get("notes") or []) + notes
    parsed.update(source=src["id"], date=D, range=chosen[0]["range"], raw_file=rel(raw_path))
    return parsed, None, raw_path


def sheet_state(src, D, y, out_dir, no_pull, st):
    sid = src["id"]
    reason = None
    if not no_pull:
        parsed, reason, raw_path = pull_sheet(src, D, y, out_dir)
        if raw_path:
            st.written.append(raw_path)
        if parsed:
            cmp_ = sheet_compare(sid, D, parsed)
            path = VD(D, sid + ".sheet.json")
            save_json(path, parsed)
            st.written.append(path)
            return {"status": "pulled", "parsed": parsed, "date": D, "phrase": "read tonight", "compare": cmp_,
                    "file": rel(path), "raw": rel(raw_path), "reason": None}
        st.pull_failed.append("%s sheet: %s" % (src.get("vendor"), reason))
    read_but_bad = bool(reason) and reason.startswith("read tonight")
    saved = sheet_snapshot_dates(sid, D)
    if saved:
        d = saved[-1]
        if read_but_bad:
            phrase = "%s; using the %s snapshot instead" % (reason, d)
        else:
            phrase = "from the %s snapshot, not re-read tonight" % d
            if reason:
                phrase = "not pulled tonight: %s; %s" % (reason, phrase)
        return {"status": "saved", "parsed": load_json(VD(d, sid + ".sheet.json")), "date": d, "phrase": phrase,
                "compare": None, "file": rel(VD(d, sid + ".sheet.json")), "raw": None, "reason": reason}
    if read_but_bad:
        phrase = "%s; no saved snapshot yet" % reason
    else:
        phrase = "not pulled tonight: %s; no saved snapshot yet" % (reason or NO_PULL)
    return {"status": "none", "parsed": None, "date": None, "compare": None, "file": None, "raw": None,
            "reason": reason, "phrase": phrase}


def pull_ga4(store, D, y, out_dir):
    start, end = min(month_first(y), shift_day(y, -27)), y
    rows, err = guarded(lambda: _gdata().ga4_report(store, start, end, GA4_DIMS, GA4_METRICS, limit=GA4_LIMIT,
                                                    dim_filter=GA4_FILTER))
    if err:
        return None, err, None
    data = {"store": store, "shift_date": D, "pulled_at": now_iso(),
            "request": {"start": start, "end": end, "dims": GA4_DIMS, "metrics": GA4_METRICS, "limit": GA4_LIMIT,
                        "dim_filter": GA4_FILTER},
            "truncated": len(rows) >= GA4_LIMIT, "rows": rows}
    path = os.path.join(out_dir, "vendor_ppc_ga4_%s.json" % store)
    save_json(path, data)
    return data, None, path


def saved_ga4(store, D, out_dir):
    name = "vendor_ppc_ga4_%s.json" % store
    cands, seen, best = [os.path.join(out_dir, name)] + sorted(glob.glob(P("*", "data", name))), set(), None
    for c in cands:
        a = os.path.abspath(c)
        if a in seen or not os.path.exists(a):
            continue
        seen.add(a)
        d = load_json(a)
        if not isinstance(d, dict) or not isinstance(d.get("rows"), list) or not d.get("request"):
            continue
        sd = d.get("shift_date") or ""
        if sd and sd <= D and (best is None or sd > best[0]):
            best = (sd, a, d)
    return best


def ga4_state(store, D, y, out_dir, no_pull, st):
    reason = None
    if not no_pull:
        data, reason, path = pull_ga4(store, D, y, out_dir)
        if data:
            st.written.append(path)
            return {"status": "pulled", "data": data, "date": D, "file": rel(path), "reason": None,
                    "phrase": "pulled tonight"}
        st.pull_failed.append("GA4 %s: %s" % (store, reason))
    best = saved_ga4(store, D, out_dir)
    if best:
        phrase = "from the %s pull, not re-pulled tonight" % best[0]
        if reason:
            phrase = "not pulled tonight: %s; %s" % (reason, phrase)
        return {"status": "saved", "data": best[2], "date": best[0], "file": rel(best[1]), "reason": reason,
                "phrase": phrase}
    return {"status": "none", "data": None, "date": None, "file": None, "reason": reason,
            "phrase": "not pulled tonight: %s; no saved pull yet" % (reason or NO_PULL)}


# ---------------------------------------------------------------- GA4 buckets and the credit split

def ga4_bucket(row, prefix):
    sm = str(row.get("sessionSourceMedium") or "").strip().lower()
    if sm not in GA4_MEDIA:
        return None
    camp = str(row.get("sessionCampaignName") or "").strip().lower()
    if prefix and camp.startswith(prefix.lower()):
        return "tagged"
    return "untagged" if sm == "google / cpc" else None


def ga4_sum(rows, prefix, days=None):
    """Bucket totals. With days, a row whose date is missing or does not parse cannot be placed in the
    window: it is left out and counted in out['undated']."""
    out = {b: {m: 0 for m in GA4_METRICS} for b in ("untagged", "tagged")}
    out["undated"] = 0
    for r in rows or []:
        if days is not None:
            d = day_of(r.get("date"))
            if not d:
                if ga4_bucket(r, prefix):
                    out["undated"] += 1
                continue
            if d not in days:
                continue
        b = ga4_bucket(r, prefix)
        if b:
            for m in GA4_METRICS:
                out[b][m] += num(r.get(m)) or 0
    return out


def ga4_by_day(rows, prefix):
    out = {}
    for r in rows or []:
        d = day_of(r.get("date"))
        b = ga4_bucket(r, prefix)
        if not b:
            continue
        if not d:
            out["undated"] = out.get("undated", 0) + 1
            continue
        acc = out.setdefault(d, {x: {m: 0 for m in GA4_METRICS} for x in ("untagged", "tagged")})
        for m in GA4_METRICS:
            acc[b][m] += num(r.get(m)) or 0
    return out


def con_window(parsed, start, end):
    """Constellation clicks and spend for the window, from the window month's tab or the newest tab's pace.
    A class value the sheet left blank stays None."""
    days = days_between(start, end) + 1
    cy, cm = parsed["year"], parsed["month_num"]
    dim_c = calendar.monthrange(cy, cm)[1]
    factor = days / float(dim_c)
    own = (cy, cm) == (int(start[:4]), int(start[5:7]))
    if own and days == dim_c:
        basis, est = "from the %s tab" % parsed["tab"], False
    elif own:
        basis, est = "from the %s tab, prorated %d of %d days (estimated)" % (parsed["tab"], days, dim_c), True
    else:
        basis, est = ("estimated from %s %d's daily pace; replaced when the %s tab lands"
                      % (MONTHS[cm - 1], cy, month_name(start))), True
    t = parsed["totals"]
    out = {"basis": basis, "estimated": est, "factor": round(factor, 6), "tab": parsed["tab"]}
    for cls in ("vla", "untagged"):
        for k in CON_KEYS:
            x = t[cls].get(k)
            out["%s_%s" % (cls, k)] = None if x is None else x * factor
    a, b = out["vla_ad_spend"], out["untagged_ad_spend"]
    tot = (t.get("all") or {}).get("ad_spend")
    out["ad_spend"] = a + b if a is not None and b is not None else (tot * factor if tot is not None else None)
    return out


def split_compute(n_clicks, n_cost, c_vla_clicks, c_un_clicks, c_un_spend, c_spend, u, t, fee=None):
    """Three ways to split GA4's untagged google / cpc bucket between NabThat and Constellation. An input
    that is None skips the methods that need it; a share outside 0 to 1 is dropped (landing is clamped, as
    the spec says); fewer than three methods is itself a SPLIT reason."""
    U = float(u.get("sessions") or 0)
    ts = t.get("sessions") or 0
    L = ts / float(c_vla_clicks) if c_vla_clicks and ts else None
    shares, notes, skipped = {}, [], []
    if n_clicks is None or c_un_clicks is None:
        skipped.append("clicks (%s)" % ("Constellation's untagged clicks are unknown" if c_un_clicks is None
                                        else "NabThat's clicks are unknown"))
    elif n_clicks + c_un_clicks > 0:
        shares["clicks"] = n_clicks / float(n_clicks + c_un_clicks)
    if n_cost is None or c_un_spend is None:
        skipped.append("spend (%s)" % ("Constellation's untagged spend is unknown" if c_un_spend is None
                                       else "NabThat's implied cost is unknown"))
    elif n_cost + c_un_spend > 0:
        shares["spend"] = n_cost / float(n_cost + c_un_spend)
    if L is None or c_un_clicks is None:
        skipped.append("landing (%s)" % ("no VLA landing rate: %s" % (
            "Constellation's vehicle listing ad clicks are unknown" if c_vla_clicks is None else
            "GA4 shows no tagged sessions" if not ts else "no vehicle listing ad clicks")
            if L is None else "Constellation's untagged clicks are unknown"))
    elif U <= 0:
        skipped.append("landing (GA4 shows no untagged sessions)")
    else:
        raw = (U - c_un_clicks * L) / U
        shares["landing"] = min(1.0, max(0.0, raw))
        if shares["landing"] != raw:
            notes.append("the landing method gave %.3f and was clamped to %d" % (raw, shares["landing"]))
    for m in list(shares):
        if not (0.0 <= shares[m] <= 1.0):
            notes.append("the %s method gave %s, outside 0 to 100%%, and was dropped" % (m, share(shares[m])))
            skipped.append("%s (out of range)" % m)
            del shares[m]
    if not shares:
        return None

    def at(s):
        nab = {m: (u.get(m) or 0) * s for m in GA4_METRICS}
        con = {m: (t.get(m) or 0) + (1 - s) * (u.get(m) or 0) for m in GA4_METRICS}
        ke_n, ke_c = nab["keyEvents"], con["keyEvents"]
        return {"share": round(s, 4),
                "nabthat": {m: round(v, 2) for m, v in nab.items()},
                "constellation": {m: round(v, 2) for m, v in con.items()},
                "nabthat_cost_per_key_event": r2(n_cost / ke_n) if ke_n and n_cost is not None else None,
                "nabthat_cost_per_key_event_incl_fees":
                    r2(n_cost * (1 + fee) / ke_n) if ke_n and n_cost is not None and fee is not None else None,
                "constellation_cost_per_key_event": r2(c_spend / ke_c) if ke_c and c_spend is not None else None,
                "nabthat_landing_rate": round(nab["sessions"] / n_clicks, 4) if n_clicks else None}

    methods = {m: at(shares[m]) for m in SPLIT_METHODS if m in shares}
    mid = sum(shares.values()) / len(shares)
    methods["midpoint"] = at(mid)
    lo, hi = min(shares.values()), max(shares.values())
    why = []
    if round(hi - lo, 6) > SPLIT_MAX_RANGE:
        why.append("the three methods are %.0f points apart (%s to %s)" % ((hi - lo) * 100, share(lo), share(hi)))
    if len(shares) < len(SPLIT_METHODS):
        why.append("only %d of the 3 methods could be computed (skipped: %s)" % (len(shares), "; ".join(skipped)))
    nl = methods["midpoint"]["nabthat_landing_rate"]
    if L and nl is not None and (nl < L / 2 or nl > L * 2):
        why.append("NabThat's implied landing rate %s is %s the VLA landing rate %s"
                   % (share(nl), "below half" if nl < L / 2 else "above double", share(L)))
    return {"L": round(L, 4) if L is not None else None, "U_sessions": U, "shares": {k: round(v, 4) for k, v in shares.items()},
            "midpoint": round(mid, 4), "range": [round(lo, 4), round(hi, 4)], "methods": methods, "notes": notes,
            "skipped": skipped, "flag_reasons": why}


# ---------------------------------------------------------------- report: one vendor dashboard

class Store(object):
    def __init__(self, code):
        self.code = code
        self.flags, self.magic, self.missing, self.status_lines = [], [], [], []
        self.pull_failed, self.written = [], []

    def add(self, code, text, file):
        self.flags.append(flag(code, text, file))


def cap_phrase(budget, cap, media=None):
    """How an over-cap line ends. Unconfirmed cap: a question for Drew. Confirmed (budget.confirmed in the config):
    a statement naming who confirmed it, plus the likely reading gap when ad spend alone is under the cap."""
    conf = (budget or {}).get("confirmed")
    if not conf:
        return "is %s including fees still the cap?" % money(cap)
    text = "the cap includes fees (confirmed: %s)" % str(conf).rstrip(".")
    if media is not None and media <= cap:
        text += ("; ad spend alone (%s) is under %s, so the vendor may be reading the cap as ad spend only"
                 % (money(media), money(cap)))
    return text


def fee_for(src, sheet):
    """The vendor sheet's fee rate (fees / ad spend) from its newest month that has fees, else the config's
    fee_rate_fallback (None = unknown), and a phrase saying which."""
    b = src.get("budget") or {}
    parsed = (sheet or {}).get("parsed") or {}
    months = parsed.get("months") or []
    withfee = [m for m in months if (m.get("values") or {}).get("fee_rate") is not None]
    if withfee:
        m0 = withfee[0]
        v = m0["values"]
        later = "" if m0 is months[0] else " (%s %d has no fees yet)" % (months[0]["month"], months[0]["year"])
        return v["fee_rate"], "%s's sheet, %s %d (fees %s on ad spend %s)%s, %s" % (
            src.get("vendor"), m0["month"], m0["year"], money(v["fees"], True), money(v["ad_spend"], True), later,
            sheet["phrase"])
    fb = b.get("fee_rate_fallback")
    return fb, "the config fallback (%s's sheet: %s)" % (src.get("vendor"), (sheet or {}).get("phrase", "no sheet"))


def since_text(hist, w, D):
    """'no read since {date}' for one window, naming what that last good read covered."""
    d = hist.last_ok(w, D)
    if not d:
        return "no earlier read on file"
    x = hist.win(d, w, mark=False)
    span = wd(x["start"]) if w == "yesterday" else short_range(x["start"], x["end"])
    return "no read since %s (that shift's %s read covered %s)" % (d, WLABEL[w], span)


def efmt(k, e):
    return money(e, True) if KEY_TYPE.get(k) in ("cost", "money") else fnum(e)


def restated_hits(rv, err, base, day):
    """RESTATED tests, with the rounding error taken off first: implied cost moves by up to half a cent per
    click on every month-to-date read, so only a move beyond that bound counts."""
    hit = []
    for k in ("clicks", "implied_cost"):
        if rv.get(k) is None or not base.get(k):
            continue
        e = (err or {}).get(k) or 0.0
        eff = max(0.0, abs(rv[k]) - e)
        if ge(eff, RESTATED_PCT / 100.0 * abs(base[k])) and ge(eff, RESTATED_MIN[k]):
            hit.append("%s %s%s (%s of %s's preliminary %s)" % (
                key_label(k), fchange(k, rv[k]), err_text(k, e), spc(rv[k] / base[k] * 100).lstrip("+"), wd(day),
                fval(k, base[k])))
    return hit


def nab_section(src, D, hist, ev, sheet, st):
    sid, vendor, store = src["id"], src.get("vendor"), src.get("store")
    y = shift_day(D, -1)
    y1, w7, s8 = shift_day(y, -1), shift_day(y, -7), shift_day(y, -8)
    vk, sk, rk = vendor_keys(src), site_keys(src), r_keys(src)
    reads_rel = rel(ev["reads_path"])
    snap_rel = rel(VD(D, sid + ".json"))
    data = {"id": sid, "vendor": vendor, "status": "active", "kind": src.get("kind"), "url": src.get("url")}
    md = ["## %s (Data Studio dashboard, read-only)" % vendor, ""]

    # tonight's reads: status, flags, ready-to-paste missing lines
    wins = ev["sources"].get(sid) or {}
    data["tonight"] = {w: {k: r.get(k) for k in ("status", "reason", "label", "line", "read_at", "browser",
                                                  "attempts", "new_boxes", "missing_boxes", "empty_boxes",
                                                  "unrendered_boxes")} for w, r in wins.items()}
    since = {w: since_text(hist, w, D) for w in WINDOWS}
    if not ev["exists"]:
        st.add("READ_MISSING", "%s's dashboard: no read for %s: %s." % (vendor, D, DID_NOT_RUN), reads_rel)
        st.missing.append("Missing tonight: %s's dashboard (%s): %s; %s." % (vendor, store, DID_NOT_RUN,
                                                                             since["yesterday"]))
        st.status_lines.append("%s dashboard (%s): no read tonight: %s." % (vendor, store, DID_NOT_RUN))
    else:
        bits = []
        for w, r in wins.items():
            lab = WLABEL[w]
            if r["status"] == "ok":
                span = wd(r["start"]) if w == "yesterday" else short_range(r["start"], r["end"])
                bits.append("%s ok (%s)" % (lab, span))
                if layout_text(r):
                    st.add("LAYOUT", "%s's dashboard layout changed (%s read): %s. The vendor changed the dashboard; "
                           "the boxes that were found are still used." % (vendor, lab, layout_text(r)),
                           "%s line %s" % (reads_rel, r["line"]))
                continue
            if r["status"] == "missing":
                bits.append("%s MISSING" % lab)
                st.add("READ_MISSING", "%s's dashboard: %s." % (vendor, r["reason"]), reads_rel)
                st.missing.append("Missing tonight: %s's dashboard (%s), %s read: %s; %s."
                                  % (vendor, store, lab, r["reason"], since[w]))
                continue
            code = "ACCESS" if (r["reason"] == SIGNIN_REASON or str(r["reason"]).startswith(ACCESS_REASON)) \
                else "READ_INVALID"
            bits.append("%s INVALID (%s)" % (lab, r["reason"]))
            st.add(code, "%s's dashboard, %s read: %s (reads.jsonl line %s)." % (vendor, lab, r["reason"], r["line"]),
                   "%s line %s" % (reads_rel, r["line"]))
            st.missing.append("Missing tonight: %s's dashboard (%s), %s read invalid: %s; %s."
                              % (vendor, store, lab, r["reason"], since[w]))
        st.status_lines.append("%s dashboard (%s): %s." % (vendor, store, "; ".join(bits)))

    # 1. yesterday (preliminary)
    py = hist.p(y)
    vy = vals(py)
    ey = errs(py, rk) if py else {}
    late = late_note(py, D) if py else None
    md += ["### Yesterday, %s (preliminary)" % wd(y), ""]
    if py:
        md.append("- %s." % cap1(values_text(vy, vk, py.get("approx"))))
        md.append("- Cost: implied (clicks x avg CPC) %s (+/- %s)." % (money(vy["implied_cost"]),
                                                                     money(vy["implied_cost_err"], True)))
        md.append("- Read %s (%s line %s); %s." % (read_desc(py), reads_rel, py["line"], PRELIM_LABEL))
        if late:
            md.append("- Note: %s." % late)
        if vy.get("calls_per_100_clicks") is not None:
            md.append("- %s phone calls per 100 clicks." % format(vy["calls_per_100_clicks"], ".1f"))
        if vy.get("phone_calls") == 0 and (vy.get("clicks") or 0) >= CALLS_ZERO_MIN_CLICKS:
            st.add("CALLS_ZERO", "%s showed 0 phone calls on %s with %s clicks: call tracking may have broken; check "
                   "tomorrow before calling it." % (vendor, wd(y), fnum(vy["clicks"])), snap_rel)
    else:
        md.append("- No valid read of %s tonight; %s." % (wd(y), since["yesterday"]))
    data["yesterday"] = {"day": y, "values": perf(vy, src), "label": PRELIM_LABEL, "late_note": late,
                         "read": read_desc(py) if py else None, "snapshot": snap_rel if py else None}

    # 2. same weekday last week, like for like
    md += ["", "### Same weekday last week", ""]
    pw = hist.p(w7)
    same = {"day": y, "vs": w7, "available": False}
    if py and pw:
        vw = vals(pw)
        ew = errs(pw, rk)
        md.append("- %s vs %s, preliminary vs preliminary (each read the morning after):" % (wd(y), wd(w7)))
        for k in SAME_KEYS:
            md.append("  - %s" % change_text(k, vy.get(k), vw.get(k)))
        h1, h2 = hours_after_midnight(py.get("read_at"), D), hours_after_midnight(pw.get("read_at"), shift_day(w7, 1))
        rough = h1 is None or h2 is None or abs(h1 - h2) > ROUGH_HOURS
        if rough:
            md.append("- read at different hours, rough (%s vs %s)." % (read_clock(py.get("read_at")) or "unknown",
                                                                        read_clock(pw.get("read_at")) or "unknown"))
        same.update(available=True, values=perf(vw, src), rough=rough,
                    changes={k: {"now": vy.get(k), "before": vw.get(k),
                                 "change": tidy(vy[k] - vw[k]) if None not in (vy.get(k), vw.get(k)) else None,
                                 "pct": round(pchg(vw.get(k), vy.get(k)), 1) if pchg(vw.get(k), vy.get(k)) is not None else None}
                             for k in SAME_KEYS})
        src_rel = "%s and %s" % (snap_rel, rel(VD(shift_day(w7, 1), sid + ".json")))
        apx = approx_keys(py) | approx_keys(pw)
        for k in DAY_KEYS:
            a, b = vy.get(k), vw.get(k)
            if a is None or not b:
                continue
            ch = a - b
            eff = max(0.0, abs(ch) - (ey.get(k) or 0.0) - (ew.get(k) or 0.0))
            if ge(eff / abs(b) * 100, DAY_MOVE_PCT) and ge(eff, MIN_ABS[k]) and ge(b, MIN_BASE[k]):
                st.add("DAY_MOVE", "%s %s %s on %s vs %s on %s (%s, %s), preliminary vs preliminary%s%s." % (
                    vendor, key_label(k), fval(k, a), wd(y), fval(k, b), wd(w7), fchange(k, ch), spc(ch / abs(b) * 100),
                    ", read at different hours, rough" if rough else "",
                    "; approx: the page rounded it" if k in apx else ""), src_rel)
        a, b = vy.get("avg_cpc"), vw.get("avg_cpc")
        if a and b and (vy.get("clicks") or 0) >= CPC_MIN_CLICKS and (vw.get("clicks") or 0) >= CPC_MIN_CLICKS:
            pc = (a - b) / b * 100
            if ge(abs(pc), CPC_MOVE_PCT):
                st.add("CPC_MOVE", "%s avg CPC %s on %s vs %s on %s (%s), preliminary vs preliminary." % (
                    vendor, money(a, True), wd(y), money(b, True), wd(w7), spc(pc)), src_rel)
    elif not py:
        md.append("- No preliminary read tonight, so no comparison.")
    else:
        first = hist.dates()[0] if hist.dates() else D
        if first > shift_day(w7, 1):
            md.append("- no same-weekday read yet (history starts %s)." % first)
            same["why"] = "no same-weekday read yet (history starts %s)" % first
        else:
            md.append("- No valid read of %s on file (the %s snapshot is missing or invalid)." % (wd(w7), shift_day(w7, 1)))
            same["why"] = "no valid read of %s" % w7
    data["same_weekday"] = same

    # 3 and 4. restatement, then the last complete day
    R = restatement(hist, src, D)
    s1, why1 = settled(hist, src, y1)
    md += ["", "### Last complete day, %s (approx settled)" % wd(y1), ""]
    last_complete = {"day": y1, "available": bool(s1)}
    if s1:
        via = "" if s1["via"] == "mtd" else " (the %s last-month read minus the %s month to date)" % (
            s1["restated_snapshot"], shift_day(y1, 1))
        md.append("- approx: assumes tonight's restatement%s landed on that day. %s." % (
            via, cap1(values_text(s1["values"], rk, err=s1["err"]))))
        md.append("- Preliminary read %s plus restated %s." % (values_text(s1["preliminary"], ("clicks", "implied_cost")),
                                                               moves_text(s1["restated"], ("clicks", "implied_cost"))))
        s8v, why8 = settled(hist, src, s8)
        if s8v:
            md.append("- vs %s (approx settled the same way, snapshots %s and %s):" % (wd(s8), s8v["prelim_snapshot"],
                                                                                      s8v["restated_snapshot"]))
            for k in rk:
                line = change_text(k, s1["values"].get(k), s8v["values"].get(k))
                e1, e8 = s1["err"].get(k) or 0.0, s8v["err"].get(k) or 0.0
                if e1 or e8:
                    line += " (approx, +/- %s vs +/- %s)" % (efmt(k, e1), efmt(k, e8))
                md.append("  - %s" % line)
        else:
            md.append("- vs %s: not available (%s)." % (wd(s8), why8))
        last_complete.update(values=s1, vs=s8v, vs_why=why8)
    else:
        md.append("- Not computed: %s." % why1)
        last_complete["why"] = why1
    data["last_complete"] = last_complete

    md += ["", "### Restated since last read", ""]
    rest = {"status": R["status"]}
    if R["status"] == "no_mtd":
        md.append("- No valid month-to-date read tonight, so no restatement.")
    elif R["status"] == "no_baseline":
        md.append("- %s." % R["why"])
    else:
        md.append("- Baseline: the %s month-to-date read (%s). Tonight: %s." % (R["prev"], R["prev_label"], R["label"]))
        if R["status"] == "ok":
            md.append("- Earlier days moved since then (tonight's month to date minus the baseline minus the preliminary "
                      "%s): %s." % (", ".join(wd(g) for g in R["gap"]) or "days", moves_text(R["values"], rk, R["err"])))
            if R["prev"] == shift_day(D, -1):
                md.append("- Mostly %s, the previous preliminary day." % wd(y1))
        else:
            md.append("- not read: %s; together with any restatement: %s." % (
                ", ".join(wd(g) for g in R["unread"]), moves_text(R["values"], rk, R["err"])))
        rest.update(prev=R["prev"], gap=R["gap"], unread=R["unread"], values=R["values"],
                    implied_cost_err=R.get("implied_cost_err"), err=R["err"])
        base = vals(hist.p(y1))
        if R["status"] == "ok" and base:
            hit = restated_hits(R["values"], R["err"], base, y1)
            if hit:
                st.add("RESTATED", "%s's earlier days moved since the %s read: %s." % (vendor, R["prev"], "; ".join(hit)),
                       snap_rel)
    lm = hist.win(D, "last_month")
    if lm:
        prevs = []
        for d in hist.dates():
            if d >= D:
                continue
            for w in ("last_month", "mtd"):
                x = hist.win(d, w, mark=False)
                if x and x["start"] == lm["start"]:
                    prevs.append((d, x["end"], w))
        mname = month_name(lm["start"]).split(" ")[0]
        X = vals(lm)
        if prevs:
            d, xend, w = sorted(prevs)[-1]
            xw = hist.win(d, w)
            Yv = vals(xw)
            gap = daterange(shift_day(xend, 1), lm["end"]) if xend < lm["end"] else []
            readg = [g for g in gap if hist.p(g)]
            unread = [g for g in gap if g not in readg]
            vg = [vals(hist.p(g)) for g in readg]
            moved = {}
            for k in rk:
                parts = [X.get(k), Yv.get(k)] + [v.get(k) for v in vg]
                moved[k] = None if any(x is None for x in parts) else tidy(X[k] - Yv[k] - sum(v[k] for v in vg))
            merr = {k: r2(sum(errs(x, [k])[k] for x in [lm, xw] + [hist.p(g) for g in readg])) for k in rk}
            seen = "last seen %s (%s) on %s" % (values_text(Yv, rk), short_range(xw["start"], xend), d)
            if unread:
                md.append("- %s closed at %s; %s; not read: %s; together with any restatement: %s." % (
                    mname, values_text(X, rk), seen, ", ".join(wd(g) for g in unread), moves_text(moved, rk, merr)))
            elif readg:
                md.append("- %s closed at %s; %s; moved %s (after taking out the preliminary %s)." % (
                    mname, values_text(X, rk), seen, moves_text(moved, rk, merr), ", ".join(wd(g) for g in readg)))
            else:
                md.append("- %s closed at %s; %s; moved %s." % (mname, values_text(X, rk), seen,
                                                               moves_text(moved, rk, merr)))
            rest["month_close"] = {"month": lm["start"][:7], "closed": {k: X.get(k) for k in rk},
                                   "last_seen": {k: Yv.get(k) for k in rk}, "last_seen_date": d,
                                   "last_seen_end": xend, "unread": unread, "preliminary_days": readg,
                                   "moved": moved, "err": merr}
            pl = vals(hist.p(lm["end"]))
            if not gap and d == shift_day(D, -1) and pl:
                hit = restated_hits(moved, merr, pl, lm["end"])
                if hit:
                    st.add("RESTATED", "%s's %s moved since the %s read: %s." % (vendor, mname, d, "; ".join(hit)),
                           snap_rel)
        else:
            md.append("- %s closed at %s; no earlier read of that month on file." % (mname, values_text(X, rk)))
    data["restated"] = rest

    # 5. month to date and pace
    md += ["", "### Month to date and pace", ""]
    M = hist.M(D)
    budget = src.get("budget") or {}
    cap = budget.get("monthly_incl_fees")
    fee, fee_how = fee_for(src, sheet)
    mtd = {"available": False, "fee_rate": fee, "fee_source": fee_how, "cap": cap, "cap_source": budget.get("source")}
    vm = vals(M)
    if M and vm.get("clicks") is not None and vm.get("avg_cpc") is not None:
        em = errs(M, rk)
        pc = pace_calc(vm["clicks"], vm["avg_cpc"], y, fee, cap, err=em["implied_cost"])
        apx = approx_keys(M)
        mtd.update(available=True, start=M["start"], end=M["end"], values=perf(vm, src), pace=pc, approx=sorted(apx))
        prelim = "includes the preliminary %s, still filling in" % wd(M["end"])
        ap = "approx, " if "implied_cost" in apx else ""
        md.append("- %s (%d of %d days; %s): %s." % (short_range(M["start"], M["end"]), pc["days_elapsed"],
                                                     pc["days_in_month"], prelim, values_text(vm, vk, M.get("approx"))))
        md.append("- Media cost: implied (clicks x avg CPC) %s (%s+/- %s)." % (money(pc["implied_cost"]), ap,
                                                                              money(pc["implied_cost_err"], True)))
        md.append("- Straight-line pace (estimated): %s media for %s (implied (clicks x avg CPC) cost x %d / %d days, "
                  "+/- %s)." % (money(pc["pace_straight_line"]), month_name(y), pc["days_in_month"],
                                pc["days_elapsed"], money(pc["pace_err"], True)))
        if fee is None:
            md.append("- Fee rate unknown (no fee rate in %s's sheet and none in the config), so no including-fees "
                      "figure or cap check%s." % (vendor, " (the %s cap includes fees)" % money(cap) if cap is not None
                                                  else ""))
        else:
            md.append("- Fee rate %s from %s." % (share(fee), fee_how))
            md.append("- Including fees: month to date %s, straight-line pace %s (estimated)." % (
                money(pc["mtd_incl_fees"]), money(pc["pace_incl_fees"])))
            if cap is not None:
                q = cap_phrase(budget, cap, pc.get("pace_straight_line"))
                md.append("- Cap: %s a month including fees (source: %s)." % (money(cap), (budget.get("source") or "config").rstrip(".")))
                if pc["mtd_over_cap"]:
                    md.append("- Month to date including fees (%s%s) is already over the cap: %s" % (
                        ap, money(pc["mtd_incl_fees"]), q))
                    st.add("MTD_OVER_CAP", "%s's month to date including fees is %s%s (%s, which %s; implied (clicks x "
                           "avg CPC) media %s (+/- %s) plus %s fees), already over the %s cap: %s" % (
                               vendor, ap, money(pc["mtd_incl_fees"]), short_range(M["start"], M["end"]), prelim,
                               money(pc["implied_cost"]), money(pc["implied_cost_err"], True), share(fee), money(cap), q),
                           snap_rel)
                if pc["pace_over_cap"]:
                    over = (pc["pace_incl_fees"] / cap - 1) * 100
                    md.append("- Straight-line pace including fees (%s, estimated) is %d%% over the cap: %s" % (
                        money(pc["pace_incl_fees"]), round(over), q))
                    st.add("PACE_OVER_CAP", "%s's straight-line pace including fees is %s (estimated) for %s, %d%% over "
                           "the %s cap (the month to date it is built on %s): %s" % (
                               vendor, money(pc["pace_incl_fees"]), month_name(y), round(over), money(cap), prelim, q),
                           snap_rel)
                if not pc["mtd_over_cap"] and not pc["pace_over_cap"]:
                    md.append("- Month to date and pace including fees are within the cap.")
    elif M:
        md.append("- Month to date %s read, but clicks or avg CPC is missing, so no cost or pace." % M["label"])
    else:
        md.append("- No valid month-to-date read tonight; %s." % since["mtd"])
    data["mtd"] = mtd

    # daily table, last 8 days
    md += ["", "### Daily, last 8 days", ""]
    md.append("| Day | Prelim clicks | Prelim implied (clicks x avg CPC) cost | Prelim calls | Settled approx clicks "
              "| Settled approx implied (clicks x avg CPC) cost | Settled approx calls | Snapshots |")
    md.append("|---|---:|---:|---:|---:|---:|---:|---|")
    daily = []
    for d in reversed(daterange(w7, y)):
        p = hist.p(d)
        v = vals(p) or {}
        s, _ = settled(hist, src, d)
        sv = (s or {}).get("values") or {}
        snaps = []
        if p:
            snaps.append("prelim %s" % shift_day(d, 1))
        if s:
            snaps.append("restated %s" % s["restated_snapshot"])
        scost = ""
        if s:
            scost = fval("implied_cost", sv.get("implied_cost"))
            if sv.get("implied_cost") is not None and s.get("implied_cost_err"):
                scost += " (+/- %s)" % money(s["implied_cost_err"], True)
        cells = [wd(d), fval("clicks", v.get("clicks")) if p else "", fval("implied_cost", v.get("implied_cost")) if p else "",
                 fval("phone_calls", v.get("phone_calls")) if p else "", fval("clicks", sv.get("clicks")) if s else "",
                 scost, fval("phone_calls", sv.get("phone_calls")) if s else "", ", ".join(snaps) or "no read"]
        md.append("| " + " | ".join(cells) + " |")
        daily.append({"day": d, "preliminary": {k: v.get(k) for k in rk} if p else None,
                      "settled_approx": sv if s else None, "settled_err": s["err"] if s else None, "snapshots": snaps})
    data["daily"] = daily

    # whole-website boxes (never NabThat's traffic)
    md += ["", "### Whole-website boxes on %s's dashboard (not %s's traffic)" % (vendor, vendor), ""]
    note = (src.get("scope_notes") or {}).get("site_ga4")
    if note:
        md += ["> %s" % note, ""]
    site = {}
    if py:
        md.append("- Yesterday %s (preliminary): %s." % (wd(y), values_text(vy, sk, py.get("approx"))))
        site["yesterday"] = {k: vy.get(k) for k in sk}
    if M:
        md.append("- Month to date %s: %s." % (short_range(M["start"], M["end"]), values_text(vm, sk, M.get("approx"))))
        site["mtd"] = {k: vm.get(k) for k in sk}
    if not py and not M:
        md.append("- No valid read tonight.")
    data["site_boxes"] = site

    # vendor's monthly sheet
    md += ["", "### %s's monthly sheet" % vendor, ""]
    if ((sheet or {}).get("parsed") or {}).get("kind") == "constellation":
        md.append("- See the %s monthly sheet section below." % vendor)
    else:
        md += nab_sheet_md(src, sheet, st, cap)
    data["sheet"] = sheet_summary(sheet, 3)
    return md, data


def sheet_summary(sheet, n=None):
    if not sheet:
        return None
    parsed = sheet.get("parsed") or {}
    out = {"status": sheet["status"], "phrase": sheet["phrase"], "file": sheet.get("file"), "raw": sheet.get("raw"),
           "compare": sheet.get("compare")}
    if parsed.get("kind") == "nabthat":
        out["months"] = (parsed.get("months") or [])[:n] if n else parsed.get("months")
    elif parsed:
        out.update({k: parsed.get(k) for k in ("tab", "month", "year", "campaigns", "totals", "summary_spend", "ties")})
    return out


def compare_md(src, sheet, st, label_of):
    cmp_ = sheet.get("compare")
    vendor = src.get("vendor")
    if cmp_ is None:
        return ["- Change check: not re-read tonight, so no change check."]
    if cmp_["first"]:
        return ["- Change check: first read of this sheet."]
    out = []
    file = sheet.get("file")
    if cmp_["new_months"]:
        txt = "%s's sheet has a new month since the %s snapshot: %s." % (
            vendor, cmp_["prev_date"], ", ".join(label_of(ym) for ym in cmp_["new_months"]))
        st.add("SHEET_NEW_MONTH", txt, file)
        out.append("- SHEET_NEW_MONTH: " + txt)
    if cmp_["changed"]:
        parts = ["%s %s %s -> %s" % (label_of(c["ym"]), c["key"].replace("_", " "), fnum(c["before"]) if c["before"] is not None else "blank",
                                     fnum(c["after"]) if c["after"] is not None else "blank")
                 for c in cmp_["changed"][:6]]
        more = len(cmp_["changed"]) - 6
        txt = "%s's sheet changed since the %s snapshot: %s%s." % (vendor, cmp_["prev_date"], "; ".join(parts),
                                                                   "; and %d more" % more if more > 0 else "")
        st.add("SHEET_CHANGED", txt, file)
        out.append("- SHEET_CHANGED: " + txt)
    if not out:
        out.append("- Change check: no changes since the %s snapshot." % cmp_["prev_date"])
    return out


def ym_label(ym):
    return "%s %s" % (MONTHS[int(ym[5:7]) - 1], ym[:4]) if ym else "n/a"


def nab_sheet_md(src, sheet, st, cap):
    if not sheet:
        return ["- No sheet in the config."]
    parsed = sheet.get("parsed")
    if not parsed or not parsed.get("months"):
        return ["- %s." % cap1(sheet["phrase"])]
    md = ["- %s (%s block, %s)." % (cap1(sheet["phrase"]), parsed.get("block"), parsed.get("range") or src["sheet"].get("range"))]
    for mo in parsed["months"][:3]:
        v = mo["values"]
        md.append("- %s %d: ad spend %s + fees %s = %s including fees (fee rate %s); clicks %s, CPC %s; impressions %s; "
                  "phone calls %s; lead forms %s; store visits %s; directions %s; VDP + SRP views %s." % (
                      mo["month"], mo["year"], money(v["ad_spend"], True), money(v["fees"], True), money(v["total"], True),
                      share(v["fee_rate"]), fnum(v["clicks"]), money(v["cpc"], True), fnum(v["impressions"]),
                      fnum(v["phone_calls"]), fnum(v["lead_forms"]), fnum(v["store_visits"]), fnum(v["directions"]),
                      fnum(v["vdp_srp_views"])))
    withtot = [m for m in parsed["months"] if m["values"].get("total") is not None]
    newest = withtot[0] if withtot else None
    tot = newest["values"]["total"] if newest else None
    if cap is not None and tot is not None and tot > cap:
        md.append("- %s %d total including fees %s is over the %s cap: %s" % (
            newest["month"], newest["year"], money(tot, True), money(cap),
            cap_phrase(src.get("budget"), cap, newest["values"].get("ad_spend"))))
    for n in parsed.get("notes") or []:
        md.append("- Note: %s." % n)
    md += compare_md(src, sheet, st, ym_label)
    return md


# ---------------------------------------------------------------- report: split, GA4, Constellation

def nab_day_clicks(hist, src, day):
    s, _ = settled(hist, src, day)
    if s and s["values"].get("clicks") is not None:
        return s["values"]["clicks"], "settled approx"
    p = hist.p(day)
    if p and (p.get("values") or {}).get("clicks") is not None:
        return p["values"]["clicks"], "prelim"
    return None, None


def split_compute_skips(cw, t):
    out = []
    if cw.get("untagged_clicks") is None:
        out.append("Constellation's untagged clicks are unknown")
    if cw.get("untagged_ad_spend") is None:
        out.append("Constellation's untagged spend is unknown")
    if not t.get("sessions"):
        out.append("GA4 shows no tagged sessions")
    return out or ["every method came out empty"]


def split_section(nsrc, csrc, D, hist, ga4, csheet, fee, st):
    md = ["## Credit split: GA4's untagged paid visits", "", "- %s" % GA4_NOTE]
    res = {"status": "not_computed"}
    nv, cv = (nsrc or {}).get("vendor", "NabThat"), (csrc or {}).get("vendor", "Constellation")
    if not nsrc or not csrc:
        md.append("- Not computed: the config needs one active dashboard and one source with a GA4 campaign prefix.")
        return md, dict(res, why="config")
    if not ga4.get("data"):
        md.append("- Not computed: GA4 %s." % ga4["phrase"])
        return md, dict(res, why="GA4 " + ga4["phrase"])
    Dn = ga4["date"]
    y_n = shift_day(Dn, -1)
    start, end = month_first(y_n), shift_day(y_n, -1)
    as_of = "" if Dn == D else " (as of the %s shift: GA4 %s)" % (Dn, ga4["phrase"])
    if end < start:
        md.append("- Not computed%s: no complete day this month yet (%s is the 1st and is preliminary)." % (as_of, wd(y_n)))
        return md, dict(res, why="no complete day this month yet")
    req = ga4["data"].get("request") or {}
    if not (req.get("start", "9999") <= start and req.get("end", "") >= end):
        md.append("- Not computed%s: the GA4 pull covers %s to %s, not %s to %s." % (as_of, req.get("start"), req.get("end"),
                                                                                  start, end))
        return md, dict(res, why="GA4 coverage")
    nw = nab_window(hist, Dn)
    if not nw:
        md.append("- Not computed%s: no valid %s month-to-date read for %s to %s." % (as_of, nv, start, end))
        return md, dict(res, why="no NabThat month to date")
    if nw["clicks"] <= 0 or nw["implied_cost"] <= 0:
        md.append("- Not computed%s: %s's window came out at %s clicks and implied (clicks x avg CPC) %s media (%s); "
                  "a read looks wrong (a yesterday read above the month to date?), so check tonight's reads."
                  % (as_of, nv, fnum(nw["clicks"]), money(nw["implied_cost"]), nw["basis"]))
        return md, dict(res, why="%s window not above zero" % nv, nabthat=nw)
    parsed = (csheet or {}).get("parsed")
    if not parsed or not parsed.get("totals") or not parsed.get("month_num"):
        md.append("- Not computed%s: %s's sheet %s." % (as_of, cv, (csheet or {}).get("phrase", "is not configured")))
        return md, dict(res, why="no Constellation sheet")
    cw = con_window(parsed, start, end)
    neg = [k.replace("_", " ") for k in ("vla_clicks", "untagged_clicks", "vla_ad_spend", "untagged_ad_spend")
           if cw.get(k) is not None and cw[k] < 0]
    if neg:
        md.append("- Not computed%s: %s's sheet (%s tab) gives a negative %s (a credit or refund line?), so it cannot "
                  "be split." % (as_of, cv, parsed.get("tab"), ", ".join(neg)))
        return md, dict(res, why="negative Constellation input")
    days = daterange(start, end)
    g = ga4_sum(ga4["data"]["rows"], csrc.get("ga4_campaign_prefix"), set(days))
    u, t = g["untagged"], g["tagged"]
    undated = ("; %d GA4 row%s had no date and %s left out" % (g["undated"], "" if g["undated"] == 1 else "s",
                                                                "was" if g["undated"] == 1 else "were")
               if g["undated"] else "")
    if not u["sessions"]:
        md.append("- Not computed%s: GA4 returned no dated untagged google / cpc sessions for %s%s." % (
            as_of, short_range(start, end), undated))
        return md, dict(res, why="no GA4 untagged sessions in the window", undated=g["undated"])
    sp = split_compute(nw["clicks"], nw["implied_cost"], cw["vla_clicks"], cw["untagged_clicks"],
                       cw["untagged_ad_spend"], cw["ad_spend"], u, t, fee)
    if not sp:
        md.append("- Not computed%s: no clicks or spend to split (skipped: %s)." % (
            as_of, "; ".join(split_compute_skips(cw, t))))
        return md, dict(res, why="nothing to split")
    est = "approx " if cw["estimated"] else ""
    md.append("- Window%s: %s (%d complete days). %s is preliminary and is left out of both sides." % (
        as_of, short_range(start, end), len(days), wd(y_n)))
    md.append("- GA4 untagged google / cpc: %s sessions, %s engaged, about %s key events (%s form submissions, %s "
              "click-to-call). %s tagged (%s*): %s sessions, about %s key events." % (
                  fint(u["sessions"]), fint(u["engagedSessions"]), fint(u["keyEvents"]),
                  fint(u["keyEvents:asc_form_submission"]), fint(u["keyEvents:asc_click_to_call"]), cv,
                  csrc.get("ga4_campaign_prefix"), fint(t["sessions"]), fint(t["keyEvents"])))
    md.append("- %s: %s clicks, implied (clicks x avg CPC) %s media (%s)." % (nv, fint(nw["clicks"]),
                                                                             money(nw["implied_cost"]), nw["basis"]))
    md.append("- %s (%s): untagged Performance Max and branding %s%s clicks and %s%s; vehicle listing ads %s%s clicks "
              "and %s%s; total %s%s ad spend." % (
                  cv, cw["basis"], est, fint(cw["untagged_clicks"]), est, money(cw["untagged_ad_spend"]), est,
                  fint(cw["vla_clicks"]), est, money(cw["vla_ad_spend"]), est, money(cw["ad_spend"])))
    if sp["L"] is not None:
        md.append("- VLA landing rate L (estimated) = %s tagged sessions / %s%s VLA clicks = %s." % (
            fint(t["sessions"]), est, fint(cw["vla_clicks"]), share(sp["L"])))
    shares = sp["shares"]
    if undated:
        md.append("- GA4 note: %s." % undated[2:])
    md.append("- %s's share of the untagged visits (estimated): %s; midpoint %s, range %s to %s%s." % (
        nv, ", ".join("by %s %s" % (m, share(shares[m])) for m in SPLIT_METHODS if m in shares), share(sp["midpoint"]),
        share(sp["range"][0]), share(sp["range"][1]),
        "; skipped: %s" % "; ".join(sp["skipped"]) if sp.get("skipped") else ""))
    for n in (parsed.get("notes") or []):
        if "blank" in n:
            md.append("- %s sheet note: %s." % (cv, n))
    md += ["", "| Method (estimated) | %s share | %s sessions | %s key events | %s $ per key event (implied (clicks x "
           "avg CPC) media / incl fees) "
           "| %s landing rate | %s sessions | %s key events | %s $ per key event |" % (nv, nv, nv, nv, nv, cv, cv, cv),
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for m in list(SPLIT_METHODS) + ["midpoint"]:
        x = sp["methods"].get(m)
        if not x:
            continue
        md.append("| %s | %s | %s | about %s | %s / %s | %s | %s | about %s | %s |" % (
            cap1(m), share(x["share"]), fint(x["nabthat"]["sessions"]), fint(x["nabthat"]["keyEvents"]),
            money(x["nabthat_cost_per_key_event"]), money(x["nabthat_cost_per_key_event_incl_fees"]),
            share(x["nabthat_landing_rate"]), fint(x["constellation"]["sessions"]),
            fint(x["constellation"]["keyEvents"]), money(x["constellation_cost_per_key_event"])))
    mid = sp["methods"]["midpoint"]
    md += ["", "- Credited to %s at the midpoint (estimated): about %s sessions, %s engaged, about %s key events "
           "(about %s form submissions, about %s click-to-call)." % (
               nv, fint(mid["nabthat"]["sessions"]), fint(mid["nabthat"]["engagedSessions"]),
               fint(mid["nabthat"]["keyEvents"]), fint(mid["nabthat"]["keyEvents:asc_form_submission"]),
               fint(mid["nabthat"]["keyEvents:asc_click_to_call"])),
           "- Credited to %s at the midpoint (tagged plus the rest, estimated): about %s sessions, about %s key events." % (
               cv, fint(mid["constellation"]["sessions"]), fint(mid["constellation"]["keyEvents"]))]
    if sp["L"] is not None:
        md.append("- %s's implied landing rate %s (credited sessions / clicks, midpoint) vs L %s." % (
            nv, share(mid["nabthat_landing_rate"]), share(sp["L"])))
    md.append("- Cost per credited GA4 key event: %s. %s's figure is implied (clicks x avg CPC) media, and incl fees "
              "at %s; %s's fee treatment is unknown (its sheet shows ad spend only)." % (KE_NOTE, nv, share(fee), cv))
    for n in sp["notes"]:
        md.append("- Note: %s." % n)
    if sp["flag_reasons"]:
        txt = "Credit split for %s is shaky: %s." % (short_range(start, end), "; ".join(sp["flag_reasons"]))
        st.add("SPLIT", txt, ga4["file"])
        md.append("- SPLIT: " + txt)
    st.magic.append("Credit split (estimated, %s): %s gets about %s of GA4's untagged paid visits (range %s to %s), about "
                    "%s sessions and about %s key events; %s about %s sessions including its tagged vehicle listing ads."
                    % (short_range(start, end), nv, share(sp["midpoint"]), share(sp["range"][0]), share(sp["range"][1]),
                       fint(mid["nabthat"]["sessions"]), fint(mid["nabthat"]["keyEvents"]), cv,
                       fint(mid["constellation"]["sessions"])))
    res = {"status": "ok", "as_of": Dn, "window": {"start": start, "end": end, "days": len(days)},
           "nabthat": nw, "constellation": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in cw.items()},
           "ga4": {"untagged": u, "tagged": t, "undated": g["undated"], "file": ga4["file"], "phrase": ga4["phrase"]},
           "fee_rate": fee}
    res.update(sp)
    return md, res


def ga4_section(nsrc, csrc, D, hist, ga4, st):
    y = shift_day(D, -1)
    md = ["## GA4 cross-check", "", "- %s" % GA4_NOTE]
    res = {"phrase": ga4["phrase"], "file": ga4.get("file")}
    if not ga4.get("data"):
        md.append("- GA4 %s." % ga4["phrase"])
        return md, res
    req = ga4["data"].get("request") or {}
    prefix = (csrc or {}).get("ga4_campaign_prefix")
    nv, cv = (nsrc or {}).get("vendor", "NabThat"), (csrc or {}).get("vendor", "Constellation")
    md.append("- GA4 %s, %s to %s (google / cpc and google / vehiclelisting). %s is preliminary in GA4 too; the ratio "
              "check uses %s." % (ga4["phrase"], req.get("start"), req.get("end"), wd(y), wd(shift_day(y, -1))))
    if ga4["data"].get("truncated"):
        md.append("- The GA4 pull hit its row limit; totals may be short.")
    byday = ga4_by_day(ga4["data"]["rows"], prefix)
    if byday.get("undated"):
        md.append("- GA4: %d row%s had no date and %s left out of the daily table." % (
            byday["undated"], "" if byday["undated"] == 1 else "s", "was" if byday["undated"] == 1 else "were"))
        res["undated"] = byday["undated"]
    ratio, rows = {}, []
    md += ["", "| Day | %s clicks | GA4 untagged sessions | Untagged sessions per %s click | GA4 tagged %s sessions |"
           % (nv, nv, cv), "|---|---:|---:|---:|---:|"]
    for d in reversed(daterange(shift_day(y, -8), y)):
        c, how = nab_day_clicks(hist, nsrc, d) if nsrc else (None, None)
        g = byday.get(d)
        us = g["untagged"]["sessions"] if g else None
        ts = g["tagged"]["sessions"] if g else None
        r = round(us / float(c), 4) if us is not None and c else None
        ratio[d] = r
        rows.append({"day": d, "nab_clicks": c, "nab_basis": how, "untagged_sessions": us, "tagged_sessions": ts,
                     "ratio": r})
        if d >= shift_day(y, -7):
            md.append("| %s | %s | %s | %s | %s |" % (wd(d), "%s (%s)" % (fnum(c), how) if c is not None else "no read",
                                                   fnum(us) if g else "not in pull", "%.2f" % r if r is not None else "n/a",
                                                   fnum(ts) if g else "not in pull"))
    res["daily"] = rows
    y1 = shift_day(y, -1)
    base = [ratio[d] for d in daterange(shift_day(y, -8), shift_day(y, -2)) if ratio.get(d) is not None]
    md.append("")
    if len(base) < GA4_MIN_HISTORY:
        md.append("- Ratio check: baseline building (%d days)." % len(base))
        res["ratio_check"] = "baseline building (%d days)" % len(base)
    elif ratio.get(y1) is None:
        md.append("- Ratio check: no ratio for %s (a %s read or the GA4 day is missing)." % (wd(y1), nv))
        res["ratio_check"] = "no ratio for %s" % y1
    else:
        med = statistics.median(base)
        r1 = ratio[y1]
        c1, _ = nab_day_clicks(hist, nsrc, y1)
        pc = pchg(med, r1)
        md.append("- Ratio check: %s %.2f vs a median of %.2f over %s to %s (%d days), %s." % (
            wd(y1), r1, med, wd(shift_day(y, -8)), wd(shift_day(y, -2)), len(base), spc(pc)))
        res["ratio_check"] = {"day": y1, "ratio": r1, "median": round(med, 4), "days": len(base),
                              "pct": round(pc, 1) if pc is not None else None}
        if pc is not None and ge(abs(pc), GA4_RATIO_PCT) and (c1 or 0) >= GA4_RATIO_MIN_CLICKS:
            txt = ("GA4 untagged google / cpc sessions per %s click on %s was %.2f vs a median of %.2f over the %d days "
                   "before (%s): %s's clicks and GA4's untagged visits moved apart." % (nv, wd(y1), r1, med, len(base),
                                                                                       spc(pc), nv))
            st.add("GA4_RATIO", txt, ga4["file"])
            md.append("- GA4_RATIO: " + txt)
    y8 = shift_day(y, -8)
    a, b = byday.get(y1), byday.get(y8)
    if a or b:
        md.append("- %s tagged in GA4: %s %s sessions, about %s key events vs %s %s sessions, about %s key events." % (
            cv, wd(y1), fnum(a["tagged"]["sessions"]) if a else "n/a", fnum(a["tagged"]["keyEvents"]) if a else "n/a",
            wd(y8), fnum(b["tagged"]["sessions"]) if b else "n/a", fnum(b["tagged"]["keyEvents"]) if b else "n/a"))
        res["constellation_tagged"] = {"day": y1, "now": a["tagged"] if a else None, "vs": y8,
                                       "before": b["tagged"] if b else None}
    return md, res


def con_section(csrc, D, hist_active, ga4_res, csheet, st):
    cv = csrc.get("vendor")
    md = ["## %s" % cv if csrc.get("status") != "active" else "## %s monthly sheet and GA4" % cv, ""]
    data = {"id": csrc["id"], "vendor": cv, "status": csrc.get("status")}
    if csrc.get("status") != "active":
        md.append("- Dashboard: %s.%s" % (waiting_text(csrc), " Config note: %s" % csrc["note"] if csrc.get("note") else ""))
    else:
        md.append("- Dashboard: active; see its own section above.")
    parsed = (csheet or {}).get("parsed")
    if not csheet:
        md.append("- Monthly sheet: none in the config.")
    elif not parsed or not parsed.get("totals"):
        md.append("- Monthly sheet: %s." % csheet["phrase"])
    else:
        T = parsed["totals"]
        tot = T["all"]
        md.append("- Monthly sheet, %s tab, %s block (%s): %s ad spend, %s impressions, %s clicks, %s lead forms, %s phone "
                  "calls. Ties to the summary table at the top: %s%s." % (
                      parsed["tab"], parsed["block"], csheet["phrase"], money(tot["ad_spend"], True),
                      fnum(tot["impressions"]), fnum(tot["clicks"]), fnum(tot["lead_forms"]), fnum(tot["phone_calls"]),
                      "yes" if parsed["ties"] else "NO",
                      " (%s)" % money(parsed["summary_spend"], True) if parsed.get("summary_spend") is not None else ""))
        for cls, what in (("vla", "Vehicle listing ads (GA4 sees them as %s*)" % csrc.get("ga4_campaign_prefix")),
                          ("untagged", "Untagged (Performance Max and branding; GA4 cannot see their names)")):
            x = T[cls]
            md.append("- %s: %d campaign%s, %s, %s clicks, CPC %s, %s lead forms, %s phone calls." % (
                what, x["campaigns"], "" if x["campaigns"] == 1 else "s", money(x["ad_spend"], True), fnum(x["clicks"]),
                money(x["cpc"], True), fnum(x["lead_forms"]), fnum(x["phone_calls"])))
        secs = {}
        for c in parsed.get("campaigns") or []:
            secs[c["section"] or "none"] = secs.get(c["section"] or "none", 0) + (c["ad_spend"] or 0)
        md.append("- By section: %s." % "; ".join("%s %s" % (k, money(v, True)) for k, v in secs.items()))
        s = sum(c["ad_spend"] or 0 for c in parsed.get("campaigns") or [])
        if tot["ad_spend"] is not None and abs(s - tot["ad_spend"]) > 1:
            md.append("- Note: the campaign rows add to %s, not the total row's %s." % (money(s, True),
                                                                                      money(tot["ad_spend"], True)))
        for n in parsed.get("notes") or []:
            md.append("- Note: %s." % n)
        md += compare_md(csrc, csheet, st, ym_label)
    b = csrc.get("budget") or {}
    if b.get("monthly_incl_fees") is not None:
        line = "- Budget: %s a month including fees (source: %s)." % (money(b["monthly_incl_fees"]),
                                                                   (b.get("source") or "config").rstrip("."))
        if parsed and parsed.get("totals"):
            line += " %s ad spend was %s; the sheet shows no fees." % (parsed["tab"].split(" (")[0],
                                                                       money(parsed["totals"]["all"]["ad_spend"], True))
        md.append(line)
    ct = (ga4_res or {}).get("constellation_tagged")
    if ct:
        md.append("- GA4 tagged daily: %s %s sessions, about %s key events vs %s %s sessions, about %s key events." % (
            wd(ct["day"]), fnum((ct["now"] or {}).get("sessions")), fnum((ct["now"] or {}).get("keyEvents")),
            wd(ct["vs"]), fnum((ct["before"] or {}).get("sessions")), fnum((ct["before"] or {}).get("keyEvents"))))
    else:
        md.append("- GA4 tagged daily: %s." % ((ga4_res or {}).get("phrase") or "not available"))
    data["sheet"] = sheet_summary(csheet)
    return md, data


# ---------------------------------------------------------------- report: assembly

def build_store(store, srcs, D, out_dir, no_pull, ev, written_at):
    y = shift_day(D, -1)
    st = Store(store)
    sheets = {s["id"]: sheet_state(s, D, y, out_dir, no_pull, st) for s in srcs if s.get("sheet")}
    ga4 = ga4_state(store, D, y, out_dir, no_pull, st)
    csrc = next((s for s in srcs if s.get("ga4_campaign_prefix")), None)
    nsrcs = [s for s in srcs if s.get("status") == "active" and not s.get("ga4_campaign_prefix")]
    nsrc = nsrcs[0] if nsrcs else None
    out = {"sources": {}, "flags": st.flags, "for_magic": [], "missing_tonight": st.missing, "split": None, "ga4": None}
    body, hists = [], {}
    for s in srcs:
        if s.get("status") != "active":
            continue
        hist = Hist(s["id"], D)
        if not ev["exists"]:
            hist.forget(D)
        hists[s["id"]] = hist
        md, data = nab_section(s, D, hist, ev, sheets.get(s["id"]), st)
        body += md + [""]
        out["sources"][s["id"]] = data
    nhist = hists.get(nsrc["id"]) if nsrc else None
    fee = fee_for(nsrc, sheets.get(nsrc["id"]))[0] if nsrc else None
    md, out["split"] = split_section(nsrc, csrc, D, nhist, ga4, sheets.get(csrc["id"]) if csrc else None, fee, st)
    body += md + [""]
    md, out["ga4"] = ga4_section(nsrc, csrc, D, nhist, ga4, st)
    body += md + [""]
    if csrc:
        md, cdata = con_section(csrc, D, hists, out["ga4"], sheets.get(csrc["id"]), st)
        body += md + [""]
        out["sources"].setdefault(csrc["id"], cdata)
        if csrc["id"] in out["sources"] and out["sources"][csrc["id"]] is not cdata:
            out["sources"][csrc["id"]]["monthly"] = cdata
    for s in srcs:
        if s.get("status") != "active":
            st.status_lines.append("%s: %s" % (s.get("vendor"), waiting_text(s)))
    bad = ["reads.jsonl line %d was skipped: %s; a retry may have been cut short, so check the vendor-dash-read task."
           % (n, why) for n, why in ev.get("bad") or []]
    out["bad_lines"] = [[n, why] for n, why in ev.get("bad") or []]
    tail = list(st.missing) + list(st.magic) + ["Not pulled tonight: %s." % p for p in st.pull_failed]
    magic = list(st.status_lines) + bad + ["%s: %s" % (f["code"], f["text"]) for f in st.flags] + tail
    magic_md = list(st.status_lines) + bad + ["%s: %s (source: %s)" % (f["code"], f["text"], f["file"])
                                              for f in st.flags] + tail
    out["for_magic"] = magic
    # sources
    src_md = ["## Sources", "", "- Config: %s" % rel(os.path.join(ROOT, *CONFIG_REL))]
    if ev["exists"]:
        lines = []
        for s in srcs:
            for w, r in (ev["sources"].get(s["id"]) or {}).items():
                if r.get("line"):
                    lines.append("%s %s line %s" % (s["id"], w, r["line"]))
        src_md.append("- Tonight's reads: %s (%s)" % (rel(ev["reads_path"]), ", ".join(lines) or "no line for these sources"))
        for n, why in ev.get("bad") or []:
            src_md.append("- %s line %d: %s, skipped" % (rel(ev["reads_path"]), n, why))
    else:
        src_md.append("- Tonight's reads: %s is missing (%s)" % (rel(ev["reads_path"]), DID_NOT_RUN))
    for sid, hist in hists.items():
        for d in sorted(hist.used):
            used = hist.used[d]
            src_md.append("- %s: %s" % (rel(VD(d, sid + ".json")), ", ".join(
                "%s from %s line %s" % (w, used[w][0], used[w][1]) for w in sorted(used))))
    for sid, sh in sheets.items():
        if sh.get("file"):
            src_md.append("- %s sheet: %s (parsed%s)%s" % (sid, sh["file"], ", " + sh["phrase"],
                                                        "; raw values %s" % sh["raw"] if sh.get("raw") else ""))
        else:
            src_md.append("- %s sheet: %s" % (sid, sh["phrase"]))
    src_md.append("- GA4: %s" % ("%s (%s)" % (ga4["file"], ga4["phrase"]) if ga4.get("file") else ga4["phrase"]))
    head = ["# Vendor paid search, %s, shift %s" % (store, D), "", "Written at %s by vendor_dash.py report." % written_at,
            "", "## FOR MAGIC", ""] + ["- %s" % m for m in magic_md] + [""]
    text = "\n".join(head + body + src_md) + "\n"
    return out, text, st


def run_report(D, out_dir, no_pull):
    cfg = load_config()
    reads = VD(D, "reads.jsonl")
    ev = evaluate(cfg, D, reads)
    snaps = write_snapshots(D, ev)
    stores = {}
    for s in cfg["sources"]:
        stores.setdefault(s.get("store") or "UNKNOWN", []).append(s)
    written_at = pacific_now().strftime("%Y-%m-%d %I:%M %p %Z").replace(" 0", " ")
    result = {"date": D, "written_at": written_at, "stores": {}}
    written, failed, per = [], [], {}
    for store, srcs in stores.items():
        data, text, st = build_store(store, srcs, D, out_dir, no_pull, ev, written_at)
        path = os.path.join(out_dir, "vendor_ppc_%s.md" % store)
        save_text(path, text)
        result["stores"][store] = data
        written += st.written + [path]
        failed += st.pull_failed
        per[store] = st
    jpath = os.path.join(out_dir, "vendor_ppc.json")
    save_json(jpath, result)
    written.append(jpath)
    rc = 0 if reads_ok(cfg, D, ev) and not failed else 2
    return rc, result, [p for p in snaps] + written, per, cfg, ev


def cmd_report(args):
    D = iso(args.date) if args.date else pacific_today().isoformat()
    out_dir = os.path.abspath(args.out) if args.out else P(D, "data")
    rc, result, paths, per, cfg, ev = run_report(D, out_dir, args.no_pull)
    for s in cfg["sources"]:
        head = "%s (%s, %s)" % (s["id"], s.get("vendor"), s.get("store"))
        if s.get("status") != "active":
            say("%s: %s" % (head, waiting_text(s)))
        elif not ev["exists"]:
            say("%s: READ_MISSING, no read for %s: %s" % (head, D, DID_NOT_RUN))
        else:
            say("%s: %s" % (head, ", ".join("%s %s" % (w, r["status"]) for w, r in ev["sources"][s["id"]].items())))
    for n, why in ev.get("bad") or []:
        say("reads.jsonl line %d: %s, skipped" % (n, why))
    codes = [f["code"] for st in per.values() for f in st.flags]
    say("flags: %s" % (", ".join(codes) if codes else "none"))
    for p in paths:
        say("wrote %s" % rel(p))
    say("FOR MAGIC:")
    for store, data in result["stores"].items():
        for m in data["for_magic"]:
            say("  %s: %s" % (store, m))
    return rc


# ---------------------------------------------------------------- selftest fixtures (real data, 2026-09-28)

# get_page_text of NabThat's dashboard: Yesterday preset, This month to date preset, and no preset (auto)
FX_YESTERDAY = "\n".join([
    'Title: New Century BMW',
    'URL: https://datastudio.google.com/reporting/bb6b08bf-94dd-4896-8134-b6938b5231d0/page/VQ19F',
    'Source element: <body>',
    '---',
    'info',
    'Notification',
    'Looker Studio is now called Data Studio. For more, see our blog.',
    'Dismiss',
    'New Century BMW',
    'Google Ads Report - New Century BMW',
    'Sep 27, 2026 - Sep 27, 2026',
    'arrow_drop_down',
    'Phone Calls',
    'Clicks',
    '250',
    'Impressions',
    '47,286',
    'Avg. CPC (converted)',
    '$3.83',
    'CTR',
    '0.53%',
    'Phone calls',
    '8',
    'keyEvents:asc_form_submission',
    '0',
    'Views',
    '1,099',
    'Sessions',
    '430',
    'Engagement rate',
    '48.84%',
    'Privacy Policy'])
FX_MTD = "\n".join([
    'Title: New Century BMW',
    'URL: https://datastudio.google.com/reporting/bb6b08bf-94dd-4896-8134-b6938b5231d0/page/VQ19F',
    'Source element: <body>',
    '---',
    'info',
    'Notification',
    'Looker Studio is now called Data Studio. For more, see our blog.',
    'Dismiss',
    'New Century BMW',
    'Google Ads Report - New Century BMW',
    'Sep 1, 2026 - Sep 27, 2026',
    'arrow_drop_down',
    'Phone Calls',
    'Clicks',
    '6,447',
    'Impressions',
    '887,411',
    'Avg. CPC (converted)',
    '$3.90',
    'CTR',
    '0.73%',
    'Phone calls',
    '377',
    'keyEvents:asc_form_submission',
    '70',
    'Views',
    '32,094',
    'Sessions',
    '13,275',
    'Engagement rate',
    '62.27%',
    'Privacy Policy'])
FX_AUTO = "\n".join([
    'Title: New Century BMW',
    'URL: https://datastudio.google.com/reporting/bb6b08bf-94dd-4896-8134-b6938b5231d0/page/VQ19F',
    'Source element: <body>',
    '---',
    'info',
    'Notification',
    'Looker Studio is now called Data Studio. For more, see our blog.',
    'Dismiss',
    'New Century BMW',
    'Google Ads Report - New Century BMW',
    'Select date range',
    'arrow_drop_down',
    'Phone Calls',
    'Clicks',
    '6,711',
    'Impressions',
    '910,605',
    'Avg. CPC (converted)',
    '$3.85',
    'CTR',
    '0.74%',
    'Phone calls',
    '408',
    'keyEvents:asc_form_submission',
    '71',
    'Views',
    '33,280',
    'Sessions',
    '13,833',
    'Engagement rate',
    '62.38%',
    'Privacy Policy'])
# Sheets API values, 'NEW CENTURY PAID SEARCH RESULTS'!A1:AA40 (NabThat)
FX_NAB_SHEET = [[], [], [],
 ['NEW CENTURY HONDA', 'July', 'August', 'September', 'October', 'November', 'December', 'January', 'February',
  'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December', 'January',
  'February', 'March', 'April ', 'May', 'June', 'July', 'August'],
 ['Ad Spend', '$16,926.93', '$16,843.60', '$16,748.21', '$16,077.49', '$18,624.88', '$17,898.65', '$17,975.67',
  '$18,421.97', '$18,243.51', '$17,473.15', '$17,635.67', '$16,228.83', '$17,316.74', '$21,449.73', '$21,279.15',
  '$20,509.57', '$19,161.74', '$22,035.92', '$19,481.09', '$18,129.76', '$20,523.57', '$20,335.00', '$20,112.80',
  '$23,799.72', '$25,744.66', '$26,646.55'],
 ['Fees', '$2,539.04', '$2,526.54', '$2,512.23', '$2,411.62', '$2,793.73', '$2,684.80', '$2,696.35', '$2,763.30',
  '$2,736.53', '$2,620.97', '$2,645.35', '$2,434.32', '$2,597.51', '$3,217.46', '$3,191.87', '$3,076.44',
  '$2,874.26', '$3,305.39', '$2,922.16', '$2,719.46', '$3,078.54', '$3,050.25', '$3,016.92', '$3,569.96',
  '$3,861.70', '$3,996.98'],
 ['Phone Calls', '518', '662', '516', '576', '837', '952', '751', '746', '935', '844', '931', '981', '932', '967',
  '978', '1126', '958', '1113', '977', '921', '1,001', '857', '567', '379', '448', '767'],
 ['Lead Forms', '80', '53', '64', '67', '97', '83', '104', '113', '102', '126.5', '122', '106', '132', '288', '252',
  '247', '238', '283', '288', '272', '163', '190', '225', '299', '339', '394'],
 ['Store Visits', '811', '785', '547', '491', '603', '705', '744.5', '625', '749', '894', '833', '661', '805',
  '820', '765', '926', '910', '1038', '917', '937', '1,652', '1,786', '1,470', '1,371', '1,509', '2,014'],
 ['Directions', '306', '301', '254', '261', '335', '350', '355', '317', '507', '441', '618', '530', '701', '576',
  '546', '743', '615', '813', '724', '741', '750', '629', '712', '686', '694', '814'],
 ['Clicks', '4,513', '4,459', '4,037', '3,949', '4,495', '4,682', '4,444', '4,170', '4,490', '4,298', '5,409',
  '6,410', '4,751', '6,651', '5,839', '5,264', '4,722', '7,184', '5,276', '4,654', '4,881', '5,060', '5,206',
  '7,254', '9,559', '10,002'],
 ['Impressions', '266,288', '15,743', '13,627', '15,034', '34,281', '31,777', '30,800', '26,072', '32,931',
  '33,598', '49,920', '72,308', '48,415', '102,000', '284,700', '309,787', '261,034', '558,337', '323,807',
  '204,813', '434,406', '426,205', '386,433', '386,865', '560,527', '509,507'],
 ['VDP + SRP Views', '2,400', '2,230', '2,019', '2,361', '2,879', '2,543', '2,747', '2,733', '2,838', '3,065',
  '2,770', '2,866', '2,478', '2,893', '2,931', '2,873', '2,714', '3,572', '3,846', '2,567', '2,375', '1,723',
  '1,920', '2,673', '3,575', '3,910'],
 [], [], [],
 ['NEW CENTURY BMW', 'July', 'August', 'September', 'October', 'November', 'December', 'January ', 'February',
  'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December', 'January',
  'February', 'March', 'April', 'May', 'June', 'July', 'August'],
 ['Ad Spend', '$14,841.44', '$15,606.16', '$16,120.80', '$16,239.72', '$18,476.39', '$21,230.21', '$21,913.10',
  '$24,640.67', '$27,134.38', '$27,634.82', '$28,729.42', '$28,350.04', '$28,342.27', '$28,511.90', '$28,081.61',
  '$28,883.75', '$23,871.40', '$24,858.66', '$24,404.79', '$23,174.33', '$19,713.21', '$19,727.85', '$21,493.36',
  '$23,738.82', '$26,274.96', '$26,485.31'],
 ['Fees', '$2,226.22', '$2,340.92', '$2,418.12', '$2,435.96', '$2,771.46', '$3,184.53', '$3,286.97', '$3,696.10',
  '$4,070.16', '$4,145.22', '$4,309.41', '$4,252.51', '$4,251.34', '$4,276.79', '$4,212.24', '$4,332.56',
  '$3,580.71', '$3,728.80', '$3,660.72', '$3,476.15', '$2,956.98', '$2,959.18', '$3,224.00', '$3,560.82',
  '$3,941.24', '$3,972.80'],
 ['Phone Calls', '300', '368', '174', '259', '621', '727', '794', '728', '922', '779', '689', '592', '697', '563',
  '675', '868', '631', '791', '775', '639', '350', '361', '331', '366', '373', '599'],
 ['Lead Forms', '30', '53', '33', '37', '46', '42', '47', '42', '54', '60', '', '', '61', '58', '75', '67', '72',
  '76', '74', '77', '79', '70', '75', '75', '45', '49'],
 ['Store Visits', '529', '582', '626', '632', '629', '857', '839', '1,084', '1,340', '1,074', '930', '592', '1,134',
  '714', '716', '595', '670', '849', '955', '849', '1,118', '1,126', '1,318', '1,234', '1287', '1214'],
 ['Directions', '216', '136', '113', '155', '330', '336', '323', '292', '487', '607', '479', '322', '527', '436',
  '517', '500', '383', '541', '573', '450', '430', '562', '614', '517', '537', '580'],
 ['Clicks', '3,285', '4,464', '5,534', '4,830', '5,119', '5,745', '6,770', '6,509', '8,467', '8,519', '8,186',
  '7,808', '7,298', '7,617', '7,642', '7,821', '5,440', '5,549', '5,929', '5,093', '4,744', '4,707', '5,444',
  '6,436', '8,030', '8,432'],
 ['Impressions', '419,931', '317,616', '315,472', '307,675', '513,703', '666,676', '934,738', '764,669', '757,511',
  '798,469', '791,642', '450,005', '571,536', '590,205', '392,709', '322,064', '285,152', '442,957', '384,255',
  '370,969', '345.078', '350,507', '367,191', '400,283', '952,336', '1,434,044'],
 ['VDP + SRP Views', '1,643', '2,232', '2,767', '2,591', '4,721', '2,538', '7,864', '9,447', '11,542', '10,137',
  '6,856', '6,789', '9,872', '9,232', '9,917', '9,321', '7,423', '8,145', '14,528', '13,988', '17,381', '19,930',
  '19,883', '14,424', '15,077', '17,118']]
# tab titles of Constellation's 'New Century Stores Monthly Report'
FX_CON_TABS = ['Jul-Sep (New Century BMW)', 'Jul-Sep (New Century Honda)', 'Jul-Sep (New Century Mazda)', 'Sept 2024', 'Oct 2024',
 'Nov 2024', 'Dec 2024', 'Dec 2024 (By Language)', 'Oct-Dec (New Century BMW)', 'Oct-Dec (New Century Honda)',
 'Oct-Dec (New Century Mazda)', 'Jan 2025 (By Language)', 'Feb 2025 (By Language)', 'Mar 2025 (By Language)',
 'Q1 Performance', 'Apr 2025 (By Language)', 'May 2025 (By Language)', 'June 2025 (By Language)', 'Q2 Performance',
 'July 2025 (By Language)', 'Aug 2025 (By Language)', 'Sep 2025 (By Language)', 'Oct 2025 (By Language)',
 'Nov 2025 (By Language)', 'Dec 2025 (By Language)', 'Jan 2026 (By Language)', 'Feb 2026 (By Language)',
 'Mar 2026 (By Language)', 'Apr 2026 (By Language)', 'May 2026 (By Language)', 'June 2026 (By Language)',
 'July 2026 (By Language)', 'August 2026 (By Language)']
# Sheets API values, 'August 2026 (By Language)'!A1:AD80 (Constellation)
FX_CON_SHEET = [['Dealer', 'Spend', '', 'Imprs', 'Clicks', 'Lead Forms', 'Phone Calls', 'Insights'], [],
 ['New Century BMW', 'New', '$20,191.66', '1,085,237', '12,943', '15', '616',
  "New Century BMW's August performance saw a slight decline in impressions and clicks compared to July, while "
  "overall conversion activity remained strong with 15 lead forms and 616 phone calls. The account's multicultural "
  'campaigns continued to be a major driver of phone call volume, particularly Chinese/Korean campaigns, which '
  'generated a significant share of calls despite representing a smaller portion of overall traffic.'],
 ['New Century Honda', 'New', '$5,487.55', '20,002', '1,519', '0', '637',
  "New Century Honda's August performance saw impressions decline while clicks increased compared to July, "
  'indicating stronger traffic efficiency despite lower overall visibility. Phone calls also increased to 818, up '
  'from 787 in July, highlighting continued strong user intent across the account. English, Spanish, and Korean '
  'campaigns all contributed meaningfully to call volume, with the campaign mix continuing to drive strong '
  'conversion activity.'],
 ['', 'Used', '$1,466.46', '6,425', '364', '0', '178'], ['', 'Service', '$222.84', '490', '58', '0', '3'],
 ['New Century Mazda', 'New', '$8,666.66', '105,450', '5,088', '5', '621',
  "New Century Mazda's August performance saw impressions decline while clicks increased significantly compared to "
  'July, with clicks rising from 3,768 to 5,088. Phone calls also increased from 527 to 621, demonstrating '
  'stronger traffic and conversion volume despite lower overall visibility. The continued strength of the '
  'multicultural campaigns, particularly Chinese/Korean and Spanish, played an important role in driving the '
  'increase in qualified traffic and phone calls.'],
 [], ['', 'New Century BMW (SEM)'],
 ['', 'Ad Spend', 'Impressions', 'Clicks', 'Lead Forms', 'Phone Calls', '', '', 'New Century Honda (SEM)', '', '',
  '', '', '', '', 'New Century Mazda (SEM)'],
 ['', '', '', '', '', '', '', '', 'Ad Spend', 'Impressions', 'Clicks', 'Lead Forms', 'Phone Calls', '', '',
  'Ad Spend', 'Impressions', 'Clicks', 'Lead Forms', 'Phone Calls'],
 ['English', '', '', '', '', '', '', 'English'],
 ['New Century BMW :: Vehicle Ads :: New :: 2026 BMW Western Region', '$4,002.94', '1,050,451', '10,281', '11', '9',
  '', 'Performance Max :: New :: Branding :: English Browser', '$410.84', '1,436', '108', '0', '64', '',
  'English'],
 ['', '', '', '', '', '', '', 'Performance Max :: New :: Civic :: English Browser', '$406.80', '2,246', '152', '0',
  '58', '', 'Performance Max :: New :: Store Branding', '$319.37', '4,048', '78', '1', '20'],
 ['Spanish', '', '', '', '', '', '', 'Performance Max :: New :: HR-V :: English Browser', '$392.78', '2,594', '125',
  '0', '51', '', 'Performance Max :: New :: CX-50', '$109.46', '1,448', '55', '0', '14'],
 ['00-BMW-NA_PCH_InMarket_New__PMAXSpanishNew', '$3,464.87', '3,059', '183', '0', '20', '',
  'Performance Max :: New :: CR-V :: English Browser', '$394.13', '1,437', '161', '0', '63', '',
  'Performance Max :: New :: New Inventory', '$183.46', '1,344', '45', '0', '20'],
 ['Branding :: Spanish :: P1', '$206.00', '1,693', '55', '0', '1', '',
  'Performance Max :: Used :: Branding :: English Browser', '$468.44', '2,932', '115', '0', '65', '',
  'Performance Max :: New :: CPO', '$174.99', '5,401', '70', '0', '13'],
 ['Branding :: Spanish :: English Browser :: P1', '$159.63', '1,370', '40', '0', '1', '', '', '', '', '', '', '',
  '', 'Performance Max :: New :: CX-90', '$174.86', '10,302', '72', '1', '17'],
 ['00-BMW-NA_PCH_InMarket_New__PMAXSpanishX3', '$580.45', '1,437', '129', '0', '46', '', 'Spanish', '', '', '', '',
  '', '', 'Performance Max :: New :: CX-5', '$126.93', '3,386', '65', '0', '22'],
 ['', '', '', '', '', '', '', 'Performance Max :: New :: Branding :: Spanish Browser', '$2,381.83', '8,728', '565',
  '0', '304', '', 'Performance Max :: New :: CX-30', '$172.63', '1,458', '76', '0', '16'],
 ['Chinese/Korean', '', '', '', '', '', '', 'New Honda CR-V :: Moments :: Spanish', '$163.93', '570', '60', '0',
  '0'],
 ['00-BMW-NA_PCH_InMarket_New__PMAXChineseNew', '$7,223.05', '15,422', '1,286', '0', '358', '',
  'New Honda Accord :: Moments :: Spanish', '$110.36', '522', '31', '0', '0', '', 'Spanish'],
 ['Branding :: Chinese :: P1', '$1,990.12', '6,369', '469', '1', '1', '', 'Service :: Spanish', '$222.84', '490',
  '58', '0', '3', '', 'Branded Moments :: Spanish :: English Browser', '$1,760.78', '18,295', '659', '0', '39'],
 ['00-BMW-NA_PCH_InMarket_New__PMAXChineseX3', '$1,352.45', '1,437', '245', '3', '123', '',
  'Performance Max :: Used :: Branding :: Spanish Browser', '$998.02', '3,493', '249', '0', '113', '',
  'Performance Max :: New :: Branding :: Spanish :: Spanish Browser', '$1,000.73', '9,293', '1,917', '0', '68'],
 ['Branding Korean P1', '$283.65', '2,031', '69', '0', '1', '', 'New Honda Prologue :: Moments :: Spanish',
  '$51.42', '88', '13', '0', '0', '', 'Performance Max :: New :: Branding :: Spanish :: English Browser', '$968.68',
  '4,375', '634', '0', '88'],
 ['00-BMW-NA_PCH_InMarket_New__PMAXKorean', '$928.50', '1,968', '186', '0', '56', '',
  'New Honda HR-V :: Moments :: Spanish', '$45.93', '94', '13', '0', '0'],
 ['', '', '', '', '', '', '', 'New Honda Civic :: Moments :: Spanish', '$397.59', '1,059', '109', '0', '0', '',
  'Chinese/Korean'],
 ['', '$20,191.66', '1,085,237', '12,943', '15', '616', '', '', '', '', '', '', '', '',
  'Branded Moments :: Chinese Browser', '$1,750.53', '7,737', '589', '0', '45'],
 ['', '', '', '', '', '', '', 'Korean', '', '', '', '', '', '',
  'Performance Max :: New :: Chinese :: English Browser', '$1,549.24', '37,558', '623', '2', '184'],
 ['', '', '', '', '', '', '', 'Branded Moments :: Korean Browser', '$731.94', '1,228', '182', '0', '97', '',
  'Branded Moments :: Korean Browser', '$375.00', '805', '205', '1', '75'],
 [],
 ['', '', '', '', '', '', '', 'Total', '$7,176.85', '26,917', '1,941', '0', '818', '', 'Total', '$8,666.66',
  '105,450', '5088', '5', '621']]
# GA4 NCBMW Sep 1 to 27 by campaign: every google / cpc and google / vehiclelisting row plus two others
FX_GA4_ROWS = [{'engagedSessions': 2274,
  'keyEvents': 7,
  'keyEvents:asc_click_to_call': 3,
  'keyEvents:asc_form_submission': 1,
  'sessionCampaignName': 'constellation_2026_BMWWR_VLA',
  'sessionSourceMedium': 'google / cpc',
  'sessions': 3402},
 {'engagedSessions': 1322,
  'keyEvents': 52,
  'keyEvents:asc_click_to_call': 28,
  'keyEvents:asc_form_submission': 10,
  'sessionCampaignName': '(organic)',
  'sessionSourceMedium': 'google / cpc',
  'sessions': 1922},
 {'engagedSessions': 1008,
  'keyEvents': 28,
  'keyEvents:asc_click_to_call': 12,
  'keyEvents:asc_form_submission': 8,
  'sessionCampaignName': '(not set)',
  'sessionSourceMedium': 'google / cpc',
  'sessions': 1400},
 {'engagedSessions': 176,
  'keyEvents': 1,
  'keyEvents:asc_click_to_call': 1,
  'keyEvents:asc_form_submission': 0,
  'sessionCampaignName': 'constellation_2026_bmwwr_vla',
  'sessionSourceMedium': 'google / vehiclelisting',
  'sessions': 332},
 {'engagedSessions': 22,
  'keyEvents': 0,
  'keyEvents:asc_click_to_call': 0,
  'keyEvents:asc_form_submission': 0,
  'sessionCampaignName': '(referral)',
  'sessionSourceMedium': 'google / cpc',
  'sessions': 60},
 {'engagedSessions': 22,
  'keyEvents': 0,
  'keyEvents:asc_click_to_call': 0,
  'keyEvents:asc_form_submission': 0,
  'sessionCampaignName': 'constellation_2026_BMWWR_VLA',
  'sessionSourceMedium': 'google / vehiclelisting',
  'sessions': 35},
 {'engagedSessions': 19,
  'keyEvents': 0,
  'keyEvents:asc_click_to_call': 0,
  'keyEvents:asc_form_submission': 0,
  'sessionCampaignName': 'googlemybusiness',
  'sessionSourceMedium': 'google / cpc',
  'sessions': 24},
 {'engagedSessions': 3,
  'keyEvents': 0,
  'keyEvents:asc_click_to_call': 0,
  'keyEvents:asc_form_submission': 0,
  'sessionCampaignName': '(direct)',
  'sessionSourceMedium': 'google / cpc',
  'sessions': 3},
 {'engagedSessions': 1354,
  'keyEvents': 49,
  'keyEvents:asc_click_to_call': 28,
  'keyEvents:asc_form_submission': 11,
  'sessionCampaignName': '(direct)',
  'sessionSourceMedium': '(direct) / (none)',
  'sessions': 2389},
 {'engagedSessions': 343,
  'keyEvents': 11,
  'keyEvents:asc_click_to_call': 3,
  'keyEvents:asc_form_submission': 4,
  'sessionCampaignName': 'googlemybusiness',
  'sessionSourceMedium': 'google / organic',
  'sessions': 445}]


# ---------------------------------------------------------------- selftest

def _page(label, clicks, impressions, cpc, calls, views, sessions=400, eng=50.0, forms=1):
    ctr = clicks * 100.0 / impressions if impressions else 0.0
    return "\n".join([
        "Title: New Century BMW", "URL: https://datastudio.google.com/reporting/x/page/y", "Source element: <body>",
        "---", "info", "Notification", "Looker Studio is now called Data Studio. For more, see our blog.", "Dismiss",
        "New Century BMW", "Google Ads Report - New Century BMW", label, "arrow_drop_down", "Phone Calls", "Clicks",
        format(clicks, ","), "Impressions", format(impressions, ","), "Avg. CPC (converted)", "$%.2f" % cpc, "CTR",
        "%.2f%%" % ctr, "Phone calls", format(calls, ","), "keyEvents:asc_form_submission", str(forms), "Views",
        format(views, ","), "Sessions", format(sessions, ","), "Engagement rate", "%.2f%%" % eng, "Privacy Policy"])


def _read(sid, window, text, read_at):
    return json.dumps({"source": sid, "window": window, "read_at": read_at, "browser": "claude-browser",
                       "url": "https://datastudio.google.com/reporting/x", "text": text})


def _write_reads(D, lines):
    os.makedirs(VD(D), exist_ok=True)
    with open(VD(D, "reads.jsonl"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _quiet(fn, *a):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(*a)
    return rc, buf.getvalue()


class _Args(object):
    def __init__(self, **kw):
        self.date, self.reads, self.learn, self.out, self.no_pull = None, None, False, None, True
        self.__dict__.update(kw)


# synthetic month: day d is read preliminary the morning after, then settles +10 clicks the night after
def _c(day):
    return 200 + 7 * int(day[8:])


def _impr(day):
    return 40000 + 500 * int(day[8:])


def _calls(day):
    return 5 + int(day[8:]) % 4


def _views(day):
    return 1000 + 10 * int(day[8:])


_CPC = 3.80


def _mtd(y):
    days = daterange(month_first(y), y)
    return (sum(_c(d) + (10 if d < y else 0) for d in days), sum(_impr(d) for d in days),
            sum(_calls(d) for d in days), sum(_views(d) for d in days))


def _night(sid, D, extra=()):
    y = shift_day(D, -1)
    at = "%sT00:47:00-07:00" % D
    c, i, k, v = _mtd(y)
    lines = [_read(sid, "yesterday", _page(fmt_range(y, y), _c(y), _impr(y), _CPC, _calls(y), _views(y)), at),
             _read(sid, "mtd", _page(fmt_range(month_first(y), y), c, i, _CPC, k, v), at)]
    _write_reads(D, lines + list(extra))
    return _quiet(cmd_ingest, _Args(date=D))[0]


def _pg(label, clicks, cpc=3.90, impressions=None, calls=None, views=None):
    return _page(label, clicks, impressions if impressions is not None else clicks * 140, cpc,
                 calls if calls is not None else clicks // 17, views if views is not None else clicks * 5)


def _pages(sid, D, pages, at=None):
    """[(window, text)] -> reads.jsonl for shift D, then the real ingest path. -> (rc, stdout)."""
    at = at or "%sT00:47:00-07:00" % D
    _write_reads(D, [_read(sid, w, t, at) for w, t in pages])
    return _quiet(cmd_ingest, _Args(date=D))


def _relabel(text, label):
    return re.sub(r"^(%s) \d{1,2}, \d{4} - (%s) \d{1,2}, \d{4}$|^Select date range$" % (_MONRE, _MONRE), label,
                  text, count=1, flags=re.M)


class _FakeHist(object):
    """Just enough of Hist for nab_window: one month-to-date window and one preliminary day."""

    def __init__(self, m, p):
        self.m, self.pp = m, p

    def M(self, date):
        return self.m

    def p(self, day):
        return self.pp


class _Stub(object):
    """Stands in for gdata in the selftest: fixture values, or a failure like gdata.die / an HTTP error.
    tabs / con: an extra tab list and {tab: values} for Constellation's sheet."""

    def __init__(self, nab_values, fail=False, tabs=None, con=None):
        self.nab, self.fail, self.tabs, self.con = nab_values, fail, tabs, con or {}

    def api(self, url, payload=None, raw=False):
        if self.fail:
            print("ERROR: not authorized yet. Drew runs: python3 gdata.py auth", file=sys.stderr)
            sys.exit(1)
        if "fields=sheets.properties.title" in url:
            return {"sheets": [{"properties": {"title": t}} for t in (self.tabs or FX_CON_TABS)]}
        for t, v in self.con.items():
            if "/values/" in url and urllib.parse.quote(t, safe="") in url:
                return {"values": v}
        if "/values/" in url and urllib.parse.quote("August 2026 (By Language)", safe="") in url:
            return {"values": FX_CON_SHEET}
        if "/values/" in url and urllib.parse.quote("(By Language)", safe="") in url:
            return {"values": []}
        if "/values/" in url:
            return {"values": self.nab}
        raise RuntimeError("unexpected url %s" % url)

    def ga4_report(self, store, start, end, dims, metrics, limit=1000, dim_filter=None, **kw):
        if self.fail:
            raise RuntimeError("HTTP 403 from analyticsdata: denied")
        rows = []
        for d in daterange(start, end):
            for r in FX_GA4_ROWS:
                if r["sessionSourceMedium"] in GA4_MEDIA:
                    x = dict(r, date=d.replace("-", ""))
                    for m in metrics:
                        x[m] = int(round(r[m] / 27.0))
                    rows.append(x)
        return rows


def cmd_selftest(_args):
    global ROOT, _GDATA_STUB
    saved_root = ROOT
    base_cfg = load_json(os.path.join(saved_root, *CONFIG_REL)) or load_json(os.path.join(DEFAULT_ROOT, *CONFIG_REL))
    tmp = tempfile.mkdtemp(prefix="vendor-dash-selftest-")
    fails = []

    def check(cond, what):
        if not cond:
            fails.append(what)
        print("  %s %s" % ("PASS" if cond else "FAIL", what))

    def new_root(name, mutate=None):
        global ROOT
        ROOT = os.path.join(tmp, name)
        cfg = json.loads(json.dumps(base_cfg))
        for s in cfg["sources"]:   # pin the copy: only the NabThat dashboard is active
            s["status"] = "active" if s["id"] == "ncbmw-nabthat" else "awaiting_link"
        if mutate:
            mutate(cfg)
        path = os.path.join(ROOT, *CONFIG_REL)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        return load_config()

    try:
        if not base_cfg:
            check(False, "config readable at %s" % os.path.join(saved_root, *CONFIG_REL))
            return 1
        cfg = new_root("parse")
        nab = next(s for s in cfg["sources"] if s["id"] == "ncbmw-nabthat")
        con = next(s for s in cfg["sources"] if s["id"] == "ncbmw-constellation")
        sid = nab["id"]

        # 1. yesterday fixture
        r = parse_page(FX_YESTERDAY, nab, "yesterday", "2026-09-28")
        want = {"clicks": 250, "impressions": 47286, "avg_cpc": 3.83, "ctr": 0.53, "phone_calls": 8,
                "site_form_submissions": 0, "video_views": 1099, "site_sessions": 430, "site_engagement_rate": 48.84}
        check(r["status"] == "ok" and r["values"] == want and r["start"] == r["end"] == "2026-09-27"
              and not r["new_boxes"] and not r["missing_boxes"] and not r["approx"],
              "1 yesterday fixture: ok, exact values, Sep 27 to Sep 27")
        check(isinstance(r["values"]["clicks"], int) and isinstance(r["values"]["avg_cpc"], float),
              "1 counts are int, money stays float")
        # 2. mtd fixture
        r = parse_page(FX_MTD, nab, "mtd", "2026-09-28")
        r2_ = parse_page(FX_MTD, nab, "mtd", "2026-09-29")
        check(r["status"] == "ok" and r["values"]["clicks"] == 6447 and r["values"]["avg_cpc"] == 3.90,
              "2 mtd fixture valid for 2026-09-28 (6,447 clicks, $3.90)")
        check(r2_["status"] == "invalid" and "Sep 1, 2026 - Sep 27, 2026" in r2_["reason"]
              and "Sep 1, 2026 - Sep 28, 2026" in r2_["reason"], "2 mtd fixture invalid for 2026-09-29, names both ranges")
        # 3. default range
        r = parse_page(FX_AUTO, nab, "yesterday", "2026-09-28")
        check(r["status"] == "invalid" and "preset was not applied" in r["reason"], "3 auto default fixture: preset not applied")
        # 4. numbers
        check(parse_num("13.3K") == (True, 13300.0, True) and parse_num("No data") == (True, None, False)
              and parse_num(EMDASH) == (True, None, False) and parse_num("-$1,234.50") == (True, -1234.5, False)
              and parse_num("Clicks")[0] is False, "4 13.3K -> 13300 approx; No data and the em dash sign -> None")
        r = parse_page(FX_YESTERDAY.replace("Views\n1,099", "Views\n13.3K"), nab, "yesterday", "2026-09-28")
        check(r["values"]["video_views"] == 13300 and isinstance(r["values"]["video_views"], int)
              and r["approx"] == ["video_views"], "4 13.3K on the page -> 13300 with approx")
        # 5. access
        r = parse_page("Sign in\nUse your Google Account\nEmail or phone", nab, "yesterday", "2026-09-28")
        r_b = parse_page("Title: Google Drive\nYou need access\nRequest access", nab, "yesterday", "2026-09-28")
        check(r["status"] == "invalid" and r["reason"] == SIGNIN_REASON and r_b["reason"] == ACCESS_REASON
              and parse_page("", nab, "yesterday", "2026-09-28")["reason"] == "empty page",
              "5 sign-in -> invalid sign-in; Request access -> invalid access; empty -> empty page")
        # 6. layout
        t = FX_YESTERDAY.replace("Views\n1,099\n", "").replace("Engagement rate", "Cost\n$1,234.56\nEngagement rate")
        r = parse_page(t, nab, "yesterday", "2026-09-28")
        check(r["status"] == "ok" and r["missing_boxes"] == ["Views"] and r["new_boxes"] == ["Cost"]
              and r["values"]["video_views"] is None and r["values"]["clicks"] == 250,
              "6 layout: missing Views, new Cost, window still ok")
        # 7. the Phone Calls chart title
        t = FX_YESTERDAY.replace("Phone calls\n8\n", "").replace("Phone Calls\nClicks", "Phone Calls\n77\nClicks")
        r = parse_page(t, nab, "yesterday", "2026-09-28")
        check(r["values"]["phone_calls"] is None and "Phone calls" in r["missing_boxes"]
              and "Phone Calls" not in r["new_boxes"], "7 the Phone Calls chart title is never read as Phone calls")
        # 12. NabThat sheet
        ns = parse_nab_sheet(FX_NAB_SHEET, nab["sheet"]["block"], "2026-09-27")
        n0 = ns["months"][0]
        check(n0["month"] == "August" and n0["year"] == 2026 and n0["values"]["ad_spend"] == 26485.31
              and n0["values"]["fees"] == 3972.80 and n0["values"]["fee_rate"] == 0.15
              and n0["values"]["total"] == 30458.11, "12 NabThat sheet: August 2026, $26,485.31 + $3,972.80 = $30,458.11, fee 0.15")
        check(ns["months"][1]["ym"] == "2026-07" and ns["months"][1]["values"]["total"] == 30216.20
              and ns["months"][-1]["ym"] == "2024-07" and not ns["notes"],
              "12 NabThat sheet: July 2026 $30,216.20; columns step back to July 2024; BMW block, not Honda")
        # 13. Constellation tab and block
        tab = pick_tab(FX_CON_TABS, con["sheet"]["tab_pattern"])
        cs = parse_con_sheet(FX_CON_SHEET, con["sheet"]["block"], tab)
        T = cs["totals"]
        check(tab == "August 2026 (By Language)", "13 Constellation tab: August 2026 (By Language)")
        check(T["all"]["ad_spend"] == 20191.66 and T["all"]["clicks"] == 12943 and T["all"]["lead_forms"] == 15
              and T["all"]["phone_calls"] == 616 and len(cs["campaigns"]) == 10 and T["vla"]["campaigns"] == 1
              and T["untagged"]["campaigns"] == 9 and T["untagged"]["clicks"] == 2662
              and abs(T["untagged"]["ad_spend"] - 16188.72) < 0.005 and cs["ties"] is True,
              "13 Constellation block: $20,191.66, 12,943 clicks, 15 forms, 616 calls; 1 vla + 9 untagged; ties")
        # 14. GA4 buckets
        pre = con["ga4_campaign_prefix"]
        b = [ga4_bucket({"sessionCampaignName": n, "sessionSourceMedium": m}, pre) for n, m in (
            ("constellation_2026_BMWWR_VLA", "google / cpc"), ("constellation_2026_bmwwr_vla", "google / vehiclelisting"),
            ("(organic)", "google / cpc"), ("(not set)", "google / cpc"), ("(referral)", "google / cpc"),
            ("googlemybusiness", "google / cpc"), ("googlemybusiness", "google / organic"), ("(direct)", "(direct) / (none)"))]
        check(b == ["tagged", "tagged", "untagged", "untagged", "untagged", "untagged", None, None],
              "14 GA4 buckets: constellation_* tagged; (organic), (not set), (referral), googlemybusiness under cpc untagged")
        # 15. credit split, verified numbers (Sep 1 to 27 treated as settled, Constellation = August x 27/31)
        g = ga4_sum(FX_GA4_ROWS, pre)
        cw = con_window(cs, "2026-09-01", "2026-09-27")
        sp = split_compute(6447, r2(6447 * 3.90), cw["vla_clicks"], cw["untagged_clicks"], cw["untagged_ad_spend"],
                           cw["ad_spend"], g["untagged"], g["tagged"], 0.15)
        ok = (g["untagged"]["sessions"] == 3409 and g["untagged"]["keyEvents"] == 80 and g["tagged"]["sessions"] == 3769
              and abs(cw["untagged_clicks"] - 2318.5) <= 0.5 and abs(cw["untagged_ad_spend"] - 14099.85) <= 0.5
              and abs(cw["vla_clicks"] - 8954.5) <= 0.5 and abs(sp["L"] - 0.4209) <= 0.001
              and abs(sp["shares"]["clicks"] - 0.7355) <= 0.001 and abs(sp["shares"]["spend"] - 0.6407) <= 0.001
              and abs(sp["shares"]["landing"] - 0.7137) <= 0.001 and abs(sp["midpoint"] - 0.6966) <= 0.001
              and abs(sp["methods"]["landing"]["nabthat"]["keyEvents"] - 57.1) <= 0.5
              and abs(sp["methods"]["landing"]["nabthat_cost_per_key_event"] - 440) <= 1.0
              and "estimated from August 2026's daily pace" in cw["basis"] and not sp["flag_reasons"])
        check(ok, "15 credit split reproduces the verified numbers (shares .7355/.6407/.7137, mid .6966, 57.1 key events, ~$440)")
        # 11. pace
        pc = pace_calc(6447, 3.90, "2026-09-27", 0.15, 28000)
        check(pc["implied_cost"] == 25143.30 and pc["pace_straight_line"] == 27937.00
              and abs(pc["pace_incl_fees"] - 32127.55) < 0.001 and abs(pc["mtd_incl_fees"] - 28914.80) < 0.001
              and pc["pace_over_cap"] and pc["mtd_over_cap"], "11 pace: $25,143.30 -> $27,937.00 -> $32,127.55; MTD $28,914.80; both over cap")

        # 17 + 11 end to end on the real fixtures (Sep 28 shift)
        cfg = new_root("sept")
        rc, out = _quiet(cmd_status, _Args(date="2026-09-28"))
        check(rc == 2 and "did not run" in out and "READ_MISSING" in out, "17 status with no reads: exit 2, did not run")
        _write_reads("2026-09-28", [_read(sid, "yesterday", FX_YESTERDAY, "2026-09-28T00:47:00-07:00"),
                                    "{not json", _read(sid, "mtd", FX_MTD, "2026-09-28T00:48:00-07:00")])
        rc, out = _quiet(cmd_status, _Args(date="2026-09-28"))
        check(rc == 0 and "line 2: not valid JSON" in out, "17 status with valid reads: exit 0 (bad JSON line reported)")
        rc, _ = _quiet(cmd_ingest, _Args(date="2026-09-28"))
        snap = load_json(VD("2026-09-28", sid + ".json"))
        yw = snap["windows"]["yesterday"]
        check(rc == 0 and yw["values"] == want and yw["line"] == 1 and snap["windows"]["mtd"]["line"] == 3
              and "text" not in yw, "1 ingest writes the snapshot: values, line numbers, no raw text")
        ns["source"], ns["date"] = sid, "2026-09-27"
        save_json(VD("2026-09-27", sid + ".sheet.json"), ns)
        cs["source"], cs["date"] = con["id"], "2026-09-27"
        save_json(VD("2026-09-27", con["id"] + ".sheet.json"), cs)
        out_dir = os.path.join(tmp, "out-sept")
        rc, out = _quiet(cmd_report, _Args(date="2026-09-28", out=out_dir))
        res = load_json(os.path.join(out_dir, "vendor_ppc.json"))
        st = res["stores"]["NCBMW"]
        codes = [f["code"] for f in st["flags"]]
        pace = st["sources"][sid]["mtd"]["pace"]
        check(rc == 0 and "PACE_OVER_CAP" in codes and "MTD_OVER_CAP" in codes and pace["fee_rate"] == 0.15
              and abs(pace["mtd_incl_fees"] - 28914.80) < 0.001 and abs(pace["pace_incl_fees"] - 32127.55) < 0.001
              and "sheet" in st["sources"][sid]["mtd"]["fee_source"] and "gdata" not in sys.modules,
              "11 report 2026-09-28 --no-pull: fee 0.15 from the sheet snapshot, PACE_OVER_CAP and MTD_OVER_CAP")
        md = open(os.path.join(out_dir, "vendor_ppc_NCBMW.md"), encoding="utf-8").read()
        check("no same-weekday read yet (history starts 2026-09-28)" in md and "no baseline this month yet" in md
              and "from the 2026-09-27 snapshot, not re-read tonight" in md
              and "Constellation: no dashboard yet (awaiting link)" in md, "report wording: history, baseline, snapshot, awaiting")

        # 8. multi-night synthetic sequence through the real ingest path
        cfg = new_root("oct")
        nights = daterange("2026-10-05", "2026-10-13")
        rcs = [_night(sid, D) for D in nights]
        ok8, same_from = all(rc == 0 for rc in rcs), []
        for D in nights:
            h = Hist(sid, D)
            y = shift_day(D, -1)
            R = restatement(h, nab, D)
            if D == nights[0]:
                ok8 = ok8 and R["status"] == "no_baseline"
                continue
            s, _ = settled(h, nab, shift_day(y, -1))
            ok8 = ok8 and R["status"] == "ok" and R["prev"] == shift_day(D, -1) and R["values"]["clicks"] == 10 \
                and abs(R["values"]["implied_cost"] - 38.0) < 0.001 and R["values"]["impressions"] == 0 \
                and s is not None and s["values"]["clicks"] == _c(shift_day(y, -1)) + 10
            if h.p(shift_day(y, -7)):
                same_from.append(D)
        check(ok8, "8 nine nights: R = +10 clicks ($38 implied) each night, s(y-1) = p(y-1) + 10")
        check(same_from == nights[7:], "8 same-weekday comparisons appear from the 8th night (2026-10-12)")
        out_dir = os.path.join(tmp, "out-oct")
        rows = []
        for d in daterange("2026-09-15", "2026-10-12"):
            cl = _c(d) if d >= "2026-10-01" else 250
            rows.append({"date": d.replace("-", ""), "sessionCampaignName": "(organic)", "sessionSourceMedium": "google / cpc",
                         "sessions": int(cl * 0.45), "engagedSessions": int(cl * 0.3), "keyEvents": 2,
                         "keyEvents:asc_form_submission": 1, "keyEvents:asc_click_to_call": 1})
            rows.append({"date": d.replace("-", ""), "sessionCampaignName": "constellation_2026_BMWWR_VLA",
                         "sessionSourceMedium": "google / cpc", "sessions": 120, "engagedSessions": 80, "keyEvents": 1,
                         "keyEvents:asc_form_submission": 0, "keyEvents:asc_click_to_call": 1})
        save_json(P("2026-10-13", "data", "vendor_ppc_ga4_NCBMW.json"),
                  {"store": "NCBMW", "shift_date": "2026-10-13", "pulled_at": "2026-10-13T01:02:00-07:00",
                   "request": {"start": "2026-09-15", "end": "2026-10-12"}, "rows": rows})
        ns["date"] = cs["date"] = "2026-10-12"
        save_json(VD("2026-10-12", sid + ".sheet.json"), ns)
        save_json(VD("2026-10-12", con["id"] + ".sheet.json"), cs)
        _quiet(cmd_report, _Args(date="2026-10-11", out=out_dir))
        md11 = open(os.path.join(out_dir, "vendor_ppc_NCBMW.md"), encoding="utf-8").read()
        _quiet(cmd_report, _Args(date="2026-10-12", out=out_dir))
        md12 = open(os.path.join(out_dir, "vendor_ppc_NCBMW.md"), encoding="utf-8").read()
        check("no same-weekday read yet (history starts 2026-10-05)" in md11 and "preliminary vs preliminary" in md12
              and "Sun 10/11 vs Sun 10/4" in md12, "8 report: no same-weekday line on 10/11; Sun 10/11 vs Sun 10/4 on 10/12")
        rc1, _ = _quiet(cmd_report, _Args(date="2026-10-13", out=out_dir))
        md1 = open(os.path.join(out_dir, "vendor_ppc_NCBMW.md"), encoding="utf-8").read()
        res = load_json(os.path.join(out_dir, "vendor_ppc.json"))
        spl = res["stores"]["NCBMW"]["split"]
        n_exp = _mtd("2026-10-12")[0] - _c("2026-10-12")
        check(spl["status"] == "ok" and spl["window"] == {"start": "2026-10-01", "end": "2026-10-11", "days": 11}
              and spl["nabthat"]["clicks"] == n_exp and "replaced when the October 2026 tab lands" in md1
              and "Mon 10/12 vs Mon 10/5" in md1 and "(approx settled the same way" in md1,
              "8 report 10/13: split window Oct 1 - Oct 11 from MTD minus the preliminary day; settled vs settled")
        # 16. no dashes; required wording
        outs = [os.path.join(out_dir, f) for f in os.listdir(out_dir)]
        outs += glob.glob(VD("*", "*.json"))
        dirty = [f for f in outs if EMDASH in open(f, encoding="utf-8").read() or ENDASH in open(f, encoding="utf-8").read()]
        check(not dirty and "not NabThat's traffic" in md1 and "implied (clicks x avg CPC)" in md1,
              "16 outputs hold no em or en dash; md says not NabThat's traffic and implied (clicks x avg CPC)")
        # 18. identical reruns
        rc2, _ = _quiet(cmd_report, _Args(date="2026-10-13", out=out_dir))
        md2 = open(os.path.join(out_dir, "vendor_ppc_NCBMW.md"), encoding="utf-8").read()
        strip = lambda s: [l for l in s.splitlines() if not l.startswith("Written at ")]
        check(rc1 == rc2 == 0 and strip(md1) == strip(md2) and md1 != "" and md1.count("Written at ") == 1,
              "18 report twice: md identical except the written-at line")

        # 9. a missing night
        cfg = new_root("gap")
        for D in daterange("2026-10-05", "2026-10-11"):
            if D != "2026-10-09":
                _night(sid, D)
        rc, out = _quiet(cmd_status, _Args(date="2026-10-09"))
        check(rc == 2 and "READ_MISSING" in out and "did not run" in out, "9 status on the missing night: READ_MISSING, exit 2")
        out_dir = os.path.join(tmp, "out-gap")
        rc, _ = _quiet(cmd_report, _Args(date="2026-10-09", out=out_dir))
        mdg = open(os.path.join(out_dir, "vendor_ppc_NCBMW.md"), encoding="utf-8").read()
        check(rc == 2 and "READ_MISSING" in mdg and "Missing tonight:" in mdg and "no read since 2026-10-08" in mdg,
              "9 report on the missing night: READ_MISSING and a ready-to-paste Missing tonight line")
        rc, _ = _quiet(cmd_report, _Args(date="2026-10-10", out=out_dir))
        mdg = open(os.path.join(out_dir, "vendor_ppc_NCBMW.md"), encoding="utf-8").read()
        R = restatement(Hist(sid, "2026-10-10"), nab, "2026-10-10")
        want9 = _c("2026-10-08") + 20
        check(rc == 0 and R["status"] == "partial" and R["unread"] == ["2026-10-08"] and R["values"]["clicks"] == want9
              and ("not read: Thu 10/8; together with any restatement: clicks +%d" % want9) in mdg,
              "9 the next night: combined line for the unread Thu 10/8, nothing crashes")

        # 10. month boundary
        cfg = new_root("month")
        at1, at2 = "2026-10-01T00:47:00-07:00", "2026-10-02T00:47:00-07:00"
        c, i, k, v = _mtd("2026-09-30")
        _write_reads("2026-10-01", [
            _read(sid, "yesterday", _page("Sep 30, 2026 - Sep 30, 2026", _c("2026-09-30"), _impr("2026-09-30"), _CPC,
                                          _calls("2026-09-30"), _views("2026-09-30")), at1),
            _read(sid, "mtd", _page("Sep 1, 2026 - Sep 30, 2026", c, i, _CPC, k, v), at1)])
        rc_a, _ = _quiet(cmd_ingest, _Args(date="2026-10-01"))
        _write_reads("2026-10-02", [
            _read(sid, "yesterday", _page("Oct 1, 2026 - Oct 1, 2026", _c("2026-10-01"), _impr("2026-10-01"), _CPC,
                                          _calls("2026-10-01"), _views("2026-10-01")), at2),
            _read(sid, "mtd", _page("Oct 1, 2026 - Oct 1, 2026", _c("2026-10-01"), _impr("2026-10-01"), _CPC,
                                    _calls("2026-10-01"), _views("2026-10-01")), at2),
            _read(sid, "last_month", _page("Sep 1, 2026 - Sep 30, 2026", c + 10, i, _CPC, k, v), at2)])
        out_dir = os.path.join(tmp, "out-month")
        rc_b, _ = _quiet(cmd_report, _Args(date="2026-10-02", out=out_dir))
        mdm = open(os.path.join(out_dir, "vendor_ppc_NCBMW.md"), encoding="utf-8").read()
        check(rc_a == 0 and load_json(VD("2026-10-01", sid + ".json"))["windows"]["mtd"]["status"] == "ok",
              "10 D = 2026-10-01: mtd label Sep 1 - Sep 30, 2026 is valid")
        check(rc_b == 0 and "no baseline this month yet" in mdm and "September closed at clicks %s" % format(c + 10, ",") in mdm
              and "on 2026-10-01; moved clicks +10" in mdm,
              "10 D = 2026-10-02: no baseline this month yet; last_month compared with the 10/01 mtd (+10 clicks)")

        # 19. the pull paths, through a stub (gdata is never imported)
        cfg = new_root("pull")
        _write_reads("2026-09-28", [_read(sid, "yesterday", FX_YESTERDAY, "2026-09-28T00:47:00-07:00"),
                                    _read(sid, "mtd", FX_MTD, "2026-09-28T00:48:00-07:00")])
        out_dir = os.path.join(tmp, "out-pull")
        _GDATA_STUB = _Stub(FX_NAB_SHEET)
        rc, _ = _quiet(cmd_report, _Args(date="2026-09-28", out=out_dir, no_pull=False))
        mdp = open(os.path.join(out_dir, "vendor_ppc_NCBMW.md"), encoding="utf-8").read()
        res = load_json(os.path.join(out_dir, "vendor_ppc.json"))["stores"]["NCBMW"]
        saved = [os.path.exists(x) for x in (os.path.join(out_dir, "vendor_ppc_ga4_NCBMW.json"),
                                             os.path.join(out_dir, "vendor_sheet_%s.json" % sid),
                                             os.path.join(out_dir, "vendor_sheet_%s.json" % con["id"]),
                                             VD("2026-09-28", sid + ".sheet.json"), VD("2026-09-28", con["id"] + ".sheet.json"))]
        check(rc == 0 and all(saved) and "first read of this sheet" in mdp and res["split"]["status"] == "ok"
              and res["split"]["window"]["end"] == "2026-09-26" and "read tonight" in mdp,
              "19 pull (stub): raw and parsed sheets and GA4 saved, first read, split Sep 1 - Sep 26, exit 0")
        nab2 = json.loads(json.dumps(FX_NAB_SHEET))
        row = next(i for i, r in enumerate(nab2) if r and r[0] == "NEW CENTURY BMW") + 1
        nab2[row][-1] = "$26,500.00"
        _GDATA_STUB = _Stub(nab2)
        rc, _ = _quiet(cmd_report, _Args(date="2026-09-29", out=out_dir, no_pull=False))
        codes = [f["code"] for f in load_json(os.path.join(out_dir, "vendor_ppc.json"))["stores"]["NCBMW"]["flags"]]
        mdp = open(os.path.join(out_dir, "vendor_ppc_NCBMW.md"), encoding="utf-8").read()
        check(rc == 2 and "SHEET_CHANGED" in codes and "READ_MISSING" in codes and "August 2026 ad spend 26,485 -> 26,500" in mdp,
              "19 next night: SHEET_CHANGED names the moved number; no reads -> READ_MISSING, exit 2")
        _GDATA_STUB = _Stub(FX_NAB_SHEET, fail=True)
        rc, _ = _quiet(cmd_report, _Args(date="2026-09-30", out=out_dir, no_pull=False))
        mdp = open(os.path.join(out_dir, "vendor_ppc_NCBMW.md"), encoding="utf-8").read()
        check(rc == 2 and "not pulled tonight: not authorized yet" in mdp and "from the 2026-09-29 snapshot, not re-read tonight" in mdp
              and "not pulled tonight: HTTP 403" in mdp, "19 failed pulls: reason quoted, newest snapshot used and named, exit 2")
        # ---------------- review fixes, 2026-09-28: one check or more per finding
        at28 = "2026-09-28T00:47:00-07:00"
        pre = con["ga4_campaign_prefix"]
        tabp, blk = con["sheet"]["tab_pattern"], con["sheet"]["block"]
        md_sept = open(os.path.join(tmp, "out-sept", "vendor_ppc_NCBMW.md"), encoding="utf-8").read()
        js_sept = load_json(os.path.join(tmp, "out-sept", "vendor_ppc.json"))["stores"]["NCBMW"]
        md_oct = open(os.path.join(tmp, "out-oct", "vendor_ppc_NCBMW.md"), encoding="utf-8").read()
        js_oct = load_json(os.path.join(tmp, "out-oct", "vendor_ppc.json"))["stores"]["NCBMW"]
        g15 = ga4_sum(FX_GA4_ROWS, pre)
        cw15 = con_window(cs, "2026-09-01", "2026-09-27")

        def rep(D, name, **kw):
            o = os.path.join(tmp, name)
            rc_, so_ = _quiet(cmd_report, _Args(date=D, out=o, **kw))
            return (rc_, so_, open(os.path.join(o, "vendor_ppc_NCBMW.md"), encoding="utf-8").read(),
                    load_json(os.path.join(o, "vendor_ppc.json"))["stores"]["NCBMW"])

        # M1 RESTATED: a cost move inside the CPC rounding bound is not a restatement
        cfg = new_root("cpcround")
        _pages(sid, "2026-10-21", [("yesterday", _pg("Oct 20, 2026 - Oct 20, 2026", 250, 3.83)),
                                   ("mtd", _pg("Oct 1, 2026 - Oct 20, 2026", 5000, 3.80))])
        _pages(sid, "2026-10-22", [("yesterday", _pg("Oct 21, 2026 - Oct 21, 2026", 250, 3.84)),
                                   ("mtd", _pg("Oct 1, 2026 - Oct 21, 2026", 5262, 3.82))])
        rc, _, mdr, jsr = rep("2026-10-22", "out-cpcround")
        Rr = restatement(Hist(sid, "2026-10-22"), nab, "2026-10-22")
        loud = restated_hits(Rr["values"], {}, {"clicks": 250, "implied_cost": 957.5}, "2026-10-20")
        check(Rr["values"]["implied_cost"] == 140.84 and Rr["err"]["implied_cost"] == 52.56 and loud
              and "RESTATED" not in [f["code"] for f in jsr["flags"]]
              and "implied (clicks x avg CPC) cost +$141 (approx, +/- $52.56)" in mdr,
              "M1 RESTATED ignores an implied-cost move inside the CPC rounding bound (+$141 +/- $52.56)")
        # M2 + M4 month end: the last day settles from last_month; a missing 1st is named, not called a move
        lm_c, lm_i, lm_k, lm_v = _mtd("2026-10-31")
        lm_line = _read(sid, "last_month", _page("Oct 1, 2026 - Oct 31, 2026", lm_c + 10, lm_i, _CPC, lm_k, lm_v),
                        "2026-11-02T00:47:00-07:00")
        cfg = new_root("monthend")
        for D in daterange("2026-10-29", "2026-11-02"):
            _night(sid, D, [lm_line] if D == "2026-11-02" else [])
        s31, why31 = settled(Hist(sid, "2026-11-02"), nab, "2026-10-31")
        rc, _, mdme, _ = rep("2026-11-02", "out-monthend")
        lc_sec = mdme.split("### Last complete day")[1].split("### ")[0]
        check(s31 is not None and s31["values"]["clicks"] == _c("2026-10-31") + 10 and s31["via"] == "last_month"
              and "Sat 10/31 (approx settled)" in lc_sec and "Not computed" not in lc_sec,
              "M4 the last day of a month settles (the 2nd's last-month read minus the 1st's month to date)")
        cfg = new_root("monthend-miss")
        for D in daterange("2026-10-29", "2026-11-02"):
            if D != "2026-11-01":
                _night(sid, D, [lm_line] if D == "2026-11-02" else [])
        rc, _, mdmm, jsmm = rep("2026-11-02", "out-monthend-miss")
        mc = jsmm["sources"][sid]["restated"]["month_close"]
        comb = lm_c + 10 - _mtd("2026-10-30")[0]
        check(mc["last_seen_end"] == "2026-10-30" and mc["unread"] == ["2026-10-31"]
              and ("(Oct 1 - Oct 30, 2026) on 2026-10-31; not read: Sat 10/31; together with any restatement: clicks +%s"
                   % format(comb, ",")) in mdmm,
              "M2 month close with the 1st's read missing: last seen Oct 1 - Oct 30, Sat 10/31 not read (combined)")
        # M3 settled implied cost carries its error
        lc = md_oct.split("### Last complete day")[1].split("### ")[0]
        check("cost $" in lc and "(approx, +/- $" in lc and "vs +/- $" in lc and "| $" in md_oct.split("### Daily")[1]
              and "(+/- $" in md_oct.split("### Daily")[1].split("### ")[0],
              "M3 the settled implied cost prints its +/- bound (last complete day, vs line, daily table)")
        # M5 exactly 20% is 20%
        cfg = new_root("cpcmove")
        _pages(sid, "2026-10-13", [("yesterday", _pg("Oct 12, 2026 - Oct 12, 2026", 100, 3.80, 9000, 5, 300)),
                                   ("mtd", _pg("Oct 1, 2026 - Oct 12, 2026", 1000, 3.80, 90000, 50, 3000))])
        _pages(sid, "2026-10-20", [("yesterday", _pg("Oct 19, 2026 - Oct 19, 2026", 120, 4.56, 9000, 5, 300)),
                                   ("mtd", _pg("Oct 1, 2026 - Oct 19, 2026", 1800, 4.10, 160000, 90, 5000))])
        rc, _, _, jsm = rep("2026-10-20", "out-cpcmove")
        check(ge((4.56 - 3.80) / 3.80 * 100, CPC_MOVE_PCT) and "CPC_MOVE" in [f["code"] for f in jsm["flags"]],
              "M5 avg CPC $3.80 -> $4.56 (exactly +20%, 19.999999999999996 in floats) raises CPC_MOVE")

        # 6 a read taken before the numbers reloaded (new label, old numbers)
        cfg = new_root("stale")
        _pages(sid, "2026-09-21", [("yesterday", _pg("Sep 20, 2026 - Sep 20, 2026", 245)),
                                   ("mtd", _pg("Sep 1, 2026 - Sep 20, 2026", 4700))])
        _pages(sid, "2026-09-27", [("yesterday", _pg("Sep 26, 2026 - Sep 26, 2026", 240, 3.90, 36000, 13, 1200)),
                                   ("mtd", _pg("Sep 1, 2026 - Sep 26, 2026", 6187, 3.90, 840000, 360, 31000))])
        ns["date"] = cs["date"] = "2026-09-27"
        save_json(VD("2026-09-27", sid + ".sheet.json"), ns)
        save_json(VD("2026-09-27", con["id"] + ".sheet.json"), cs)
        save_json(P("2026-09-28", "data", "vendor_ppc_ga4_NCBMW.json"),
                  {"store": "NCBMW", "shift_date": "2026-09-28", "pulled_at": at28,
                   "request": {"start": "2026-08-31", "end": "2026-09-27"},
                   "rows": _Stub(FX_NAB_SHEET).ga4_report("NCBMW", "2026-08-31", "2026-09-27", GA4_DIMS, GA4_METRICS)})
        stale_y = _relabel(FX_MTD, "Sep 27, 2026 - Sep 27, 2026")
        rc_a, _ = _pages(sid, "2026-09-28", [("yesterday", stale_y), ("mtd", FX_MTD)])
        wa = load_json(VD("2026-09-28", sid + ".json"))["windows"]
        rc, _, mds, jss = rep("2026-09-28", "out-stale")
        cst = [f["code"] for f in jss["flags"]]
        check(rc_a == 2 and wa["yesterday"]["status"] == "invalid" and wa["mtd"]["status"] == "ok"
              and "yesterday clicks 6,447 vs month to date 6,447" in wa["yesterday"]["reason"]
              and "did not refresh after the date preset" in wa["yesterday"]["reason"]
              and rc == 2 and "READ_INVALID" in cst and "DAY_MOVE" not in cst
              and jss["split"]["status"] == "ok" and jss["split"]["nabthat"]["clicks"] == 6187,
              "6 yesterday label over month-to-date numbers: yesterday INVALID, no DAY_MOVE, split from last night's MTD")
        _pages(sid, "2026-09-28", [("yesterday", _relabel(FX_AUTO, "Sep 27, 2026 - Sep 27, 2026")), ("mtd", FX_MTD)])
        wb = load_json(VD("2026-09-28", sid + ".json"))["windows"]
        _pages(sid, "2026-09-28", [("yesterday", FX_YESTERDAY),
                                   ("mtd", _relabel(FX_YESTERDAY, "Sep 1, 2026 - Sep 27, 2026"))])
        wc = load_json(VD("2026-09-28", sid + ".json"))["windows"]
        _pages(sid, "2026-09-28", [("yesterday", stale_y), ("mtd", FX_AUTO)])
        wf = load_json(VD("2026-09-28", sid + ".json"))["windows"]
        _pages(sid, "2026-09-28", [("yesterday", FX_YESTERDAY), ("mtd", FX_MTD), ("yesterday", stale_y)])
        we = load_json(VD("2026-09-28", sid + ".json"))["windows"]
        check(wb["yesterday"]["status"] == "invalid" and "yesterday clicks 6,711 vs month to date 6,447" in wb["yesterday"]["reason"]
              and wc["mtd"]["status"] == "invalid" and "below the 2026-09-27 read's 6,187" in wc["mtd"]["reason"]
              and wc["yesterday"]["status"] == "ok"
              and wf["yesterday"]["status"] == "invalid" and "which covers 26 days" in wf["yesterday"]["reason"]
              and we["yesterday"]["status"] == "ok" and we["yesterday"]["line"] == 1 and we["yesterday"]["values"] == want,
              "6 default-range numbers (6,711 > MTD), an MTD below last night's, a stale yesterday with no valid MTD, "
              "and a stale retry after a good read")
        cfg = new_root("stale-nohist")
        _pages(sid, "2026-09-28", [("yesterday", stale_y), ("mtd", FX_MTD)])
        wn = load_json(VD("2026-09-28", sid + ".json"))["windows"]
        check(wn["yesterday"]["status"] == "invalid" and wn["mtd"]["status"] == "invalid"
              and "same numbers as the yesterday read" in wn["mtd"]["reason"],
              "6 with no earlier month to date, identical yesterday and MTD numbers leave neither trusted")

        # 7 / 19 / 8 boxes: no NabThat numbers, connector errors, half-rendered pages
        pairs = (("Clicks", "250"), ("Impressions", "47,286"), ("Avg. CPC (converted)", "$3.83"), ("CTR", "0.53%"),
                 ("Phone calls", "8"), ("Views", "1,099"))
        site_only, nodata, connerr = FX_YESTERDAY, FX_YESTERDAY, FX_YESTERDAY
        for lab, val in pairs:
            site_only = site_only.replace("\n%s\n%s\n" % (lab, val), "\n")
            nodata = nodata.replace("\n%s\n%s\n" % (lab, val), "\n%s\nNo data\n" % lab)
            connerr = connerr.replace("\n%s\n%s\n" % (lab, val), "\n%s\nData Set Configuration Error\nSee details\n" % lab)
        r_so = parse_page(site_only, nab, "yesterday", "2026-09-28")
        r_nd = parse_page(nodata, nab, "yesterday", "2026-09-28")
        r_ce = parse_page(connerr, nab, "yesterday", "2026-09-28")
        check(r_so["status"] == "invalid" and "lost its Clicks box" in r_so["reason"] and r_so["values"]["site_sessions"] == 430,
              "19 a page with only the whole-website boxes is not a NabThat read")
        check(r_nd["status"] == "invalid" and "showed no numbers" in r_nd["reason"] and "Clicks" in r_nd["reason"]
              and r_ce["status"] == "invalid" and "connector error" in r_ce["reason"] and "Views" in r_ce["empty_boxes"],
              "7 every NabThat box No data, or a connector error in each box: invalid, not ok")
        lines_y = FX_YESTERDAY.split("\n")
        nonum = "\n".join(l for l in lines_y if not parse_num(l)[0])
        half = "\n".join(l for i, l in enumerate(lines_y) if not (parse_num(l)[0] and lines_y[i - 1] != "Clicks"))
        r_nn = parse_page(nonum, nab, "yesterday", "2026-09-28")
        r_h = parse_page(half, nab, "yesterday", "2026-09-28")
        cfg = new_root("retry")
        _pages(sid, "2026-09-28", [("yesterday", FX_YESTERDAY), ("mtd", FX_MTD), ("yesterday", half)])
        wr = load_json(VD("2026-09-28", sid + ".json"))["windows"]["yesterday"]
        check(r_nn["status"] == "invalid" and "finished loading" in r_nn["reason"] and "vendor changed" not in r_nn["reason"]
              and r_h["status"] == "invalid" and "Impressions" in r_h["reason"]
              and wr["line"] == 1 and wr["values"] == want,
              "8 labels with no numbers read as not loaded (not a vendor change); a half-rendered retry never replaces a full read")

        # 9 credit split guards
        mwin = {"start": "2026-09-01", "end": "2026-09-27", "values": {"clicks": 6447, "avg_cpc": 3.90}}
        pwin = {"start": "2026-09-27", "end": "2026-09-27", "values": {"clicks": 6711, "avg_cpc": 3.85}}
        ga4_ok = {"data": {"rows": [dict(r, date="20260915") for r in FX_GA4_ROWS],
                           "request": {"start": "2026-08-31", "end": "2026-09-27"}},
                  "date": "2026-09-28", "file": "ga4.json", "phrase": "pulled tonight"}
        mdx, rx = split_section(nab, con, "2026-09-28", _FakeHist(mwin, pwin), ga4_ok, {"parsed": cs, "phrase": "x"},
                                0.15, Store("NCBMW"))
        spn = split_compute(-264, -694.05, cw15["vla_clicks"], cw15["untagged_clicks"], cw15["untagged_ad_spend"],
                            cw15["ad_spend"], g15["untagged"], g15["tagged"], 0.15)
        check(rx["status"] == "not_computed" and "window came out at -264 clicks" in "\n".join(mdx)
              and spn is not None and "clicks" not in spn["shares"] and "spend" not in spn["shares"]
              and any("only 1 of the 3 methods" in w for w in spn["flag_reasons"]),
              "9 no split on a NabThat window below zero; a share outside 0 to 100% is dropped and raises SPLIT")

        # 10 Constellation tab choice: closed months only, fall back past a tab that does not parse
        ok_t, fut_t = pick_tabs(FX_CON_TABS + ["October 2026 (By Language)"], tabp, "2026-10-04")
        nobmw = [r for r in FX_CON_SHEET if not any("BMW" in str(c) for c in r)]
        cfg = new_root("tabs")
        _night(sid, "2026-10-06")
        _GDATA_STUB = _Stub(FX_NAB_SHEET, tabs=FX_CON_TABS + ["September 2026 (By Language)", "October 2026 (By Language)"],
                            con={"September 2026 (By Language)": nobmw, "October 2026 (By Language)": FX_CON_SHEET})
        rep("2026-10-06", "out-tabs", no_pull=False)
        ptab = load_json(VD("2026-10-06", con["id"] + ".sheet.json")) or {}
        _night(sid, "2026-10-07")
        _GDATA_STUB = _Stub(FX_NAB_SHEET, tabs=["September 2026 (By Language)"], con={"September 2026 (By Language)": nobmw})
        rc, _, mdt, _ = rep("2026-10-07", "out-tabs", no_pull=False)
        _GDATA_STUB = None
        check(ok_t[0] == "August 2026 (By Language)" and fut_t == ["October 2026 (By Language)"]
              and ptab.get("tab") == "August 2026 (By Language)"
              and any(n.startswith("October 2026 (By Language) tab skipped: that month has not closed") for n in ptab["notes"])
              and any(n.startswith("September 2026 (By Language) tab did not parse") for n in ptab["notes"])
              and "read tonight, but no closed-month tab parsed" in mdt and "using the 2026-10-06 snapshot instead" in mdt
              and "not pulled tonight: read" not in mdt,
              "10 a tab for the current month is skipped; a tab with no BMW block falls back to August; wording says read")

        # 11 / 12 Constellation block: a Total label, a note row, a blank cell, a tie-out
        v = json.loads(json.dumps(FX_CON_SHEET))
        ti = next(i for i, r in enumerate(v) if len(r) > 1 and r[0] == "" and r[1] == "$20,191.66")
        vt = json.loads(json.dumps(v))
        vt[ti][0] = "Total"
        vt.insert(ti + 1, ["", "Budget note: Jul-Dec $22,613"])
        pt = parse_con_sheet(vt, blk, "August 2026 (By Language)")
        vs = json.loads(json.dumps(v))
        del vs[ti]
        vs += [[], ["", "New Century BMW (Social)"], ["", "Ad Spend", "Impressions", "Clicks", "Lead Forms", "Phone Calls"],
               ["Meta :: Retargeting", "$500.00", "10,000", "300", "2", "0"], ["", "$500.00", "10,000", "300", "2", "0"]]
        try:
            parse_con_sheet(vs, blk, "August 2026 (By Language)")
            e_s = ""
        except ValueError as e:
            e_s = str(e)
        check(pt["totals"]["untagged"]["clicks"] == 2662 and pt["totals"]["untagged"]["campaigns"] == 9
              and pt["totals"]["all"]["ad_spend"] == 20191.66 and pt["ties"] and e_s.startswith("no total row"),
              "11 a BMW total row labeled Total is the total, not a campaign; a missing total never borrows the next block")
        jc = next(i for i, r in enumerate(v) if r and r[0] == "00-BMW-NA_PCH_InMarket_New__PMAXChineseNew")
        jv = next(i for i, r in enumerate(v) if r and r[0].startswith("New Century BMW :: Vehicle Ads"))
        vb = json.loads(json.dumps(v))
        vb[jc][3] = ""
        pb = parse_con_sheet(vb, blk, "August 2026 (By Language)")
        vb2 = json.loads(json.dumps(vb))
        vb2[jv][3] = ""
        pb2 = parse_con_sheet(vb2, blk, "August 2026 (By Language)")
        cwb = con_window(pb2, "2026-09-01", "2026-09-27")
        spb = split_compute(6447, 25143.3, cwb["vla_clicks"], cwb["untagged_clicks"], cwb["untagged_ad_spend"],
                            cwb["ad_spend"], g15["untagged"], g15["tagged"], 0.15)
        vm_ = json.loads(json.dumps(v))
        vm_[jv][3] = "10,381"
        try:
            parse_con_sheet(vm_, blk, "August 2026 (By Language)")
            e_m = ""
        except ValueError as e:
            e_m = str(e)
        check(pb["totals"]["untagged"]["clicks"] == 2662 and any("derived" in n for n in pb["notes"])
              and pb2["totals"]["untagged"]["clicks"] is None and pb2["totals"]["vla"]["clicks"] is None
              and cwb["untagged_clicks"] is None and spb is not None and list(spb["shares"]) == ["spend"]
              and any("only 1 of the 3 methods" in w for w in spb["flag_reasons"])
              and "campaign rows add to 13,043 clicks" in e_m,
              "12 a blank cell is derived from the total or left unknown (never 0); classes must tie to the total row")

        # 13 GA4 rows with no date
        gu = ga4_sum(FX_GA4_ROWS, pre, set(daterange("2026-09-01", "2026-09-26")))
        ga4_nd = dict(ga4_ok, data={"rows": FX_GA4_ROWS, "request": ga4_ok["data"]["request"]})
        pwin2 = dict(pwin, values={"clicks": 250, "avg_cpc": 3.83})
        mdu, ru = split_section(nab, con, "2026-09-28", _FakeHist(mwin, pwin2), ga4_nd, {"parsed": cs, "phrase": "x"},
                                0.15, Store("NCBMW"))
        spl = split_compute(6447, 25143.3, cw15["vla_clicks"], cw15["untagged_clicks"], cw15["untagged_ad_spend"],
                            cw15["ad_spend"], g15["untagged"], dict(g15["tagged"], sessions=0), 0.15)
        check(gu["undated"] == 8 and gu["untagged"]["sessions"] == 0 and ru["status"] == "not_computed"
              and "8 GA4 rows had no date" in "\n".join(mdu) and spl is not None and "landing" not in spl["shares"]
              and any("only 2 of the 3 methods" in w for w in spl["flag_reasons"]),
              "13 undated GA4 rows are counted and block the split; zero tagged sessions skips the landing method")

        # 14 / 20 skipped reads.jsonl lines: BOM, unknown source, a cut-off line; reported by report too
        cfg = new_root("badlines")
        os.makedirs(VD("2026-09-28"), exist_ok=True)
        with open(VD("2026-09-28", "reads.jsonl"), "w", encoding="utf-8") as f:
            f.write(chr(0xfeff) + _read(sid, "yesterday", FX_YESTERDAY, at28) + "\n"
                    + _read("nabthat", "mtd", FX_MTD, at28) + "\n" + _read(sid, "mtd", FX_MTD, at28)[:300] + "\n")
        evb = evaluate(cfg, "2026-09-28", VD("2026-09-28", "reads.jsonl"))
        wbl = evb["sources"][sid]
        rc, outb, mdb, jsb = rep("2026-09-28", "out-badlines")
        check(wbl["yesterday"]["status"] == "ok" and wbl["mtd"]["status"] == "missing"
              and "lines 2, 3 could not be parsed" in wbl["mtd"]["reason"]
              and any("source nabthat is not in vendor-dashboards.json" in w for _, w in evb["bad"]),
              "14 a BOM is ignored; an unknown source id and a cut-off line are named in the missing window's reason")
        check("reads.jsonl line 3: not valid JSON" in outb and "reads.jsonl line 3 was skipped" in mdb
              and "line 2: source nabthat is not in vendor-dashboards.json, skipped" in mdb and len(jsb["bad_lines"]) == 2
              and "reads.jsonl line 2 was skipped: not valid JSON" in md_sept,
              "20 report prints the skipped lines and writes them to FOR MAGIC, Sources and vendor_ppc.json")

        # 15 / 23 no en dash on stdout
        cfg = new_root("dash")
        _write_reads("2026-09-28", [_read(sid, "yesterday", FX_YESTERDAY.replace("Sep 27, 2026 - Sep 27, 2026",
                                                                                  "Sep 26, 2026 %s Sep 26, 2026" % ENDASH), at28),
                                    _read(sid, "mtd", FX_MTD.replace("Sep 1, 2026 - Sep 27, 2026",
                                                                     "Sep 1, 2026 %s Sep 27, 2026" % ENDASH), at28)])
        outs_ = [_quiet(cmd_status, _Args(date="2026-09-28"))[1], _quiet(cmd_ingest, _Args(date="2026-09-28"))[1],
                 rep("2026-09-28", "out-dash")[1]]
        snapd = load_json(VD("2026-09-28", sid + ".json"))["windows"]
        check(all(ENDASH not in o and EMDASH not in o for o in outs_) and "page showed Sep 26, 2026 - Sep 26, 2026" in outs_[0]
              and snapd["mtd"]["label"] == "Sep 1, 2026 - Sep 27, 2026",
              "15 an en dash in the page label never reaches stdout (status, ingest, report)")

        # 16 compact numbers: rounding error carried; no RESTATED on it
        cfg = new_root("compact")
        _pages(sid, "2026-09-27", [("yesterday", _pg("Sep 26, 2026 - Sep 26, 2026", 240, 3.90, 36000, 13, 1200)),
                                   ("mtd", _pg("Sep 1, 2026 - Sep 26, 2026", 6187, 3.90, 840000, 360, 31000)
                                    .replace("\n6,187\n", "\n6.2K\n"))])
        _pages(sid, "2026-09-28", [("yesterday", FX_YESTERDAY), ("mtd", FX_MTD.replace("\n6,447\n", "\n6.4K\n"))])
        Rk = restatement(Hist(sid, "2026-09-28"), nab, "2026-09-28")
        rc, _, mdk, jsk = rep("2026-09-28", "out-compact")
        check(Rk["values"]["clicks"] == -50 and Rk["err"]["clicks"] == 100 and "clicks" in Rk["approx"]
              and "RESTATED" not in [f["code"] for f in jsk["flags"]] and "clicks -50 (approx, +/- 100)" in mdk
              and "approx, +/- $" in mdk.split("Media cost:")[1].split("\n")[0],
              "16 6.2K then 6.4K: R clicks -50 +/- 100, no RESTATED, implied cost marked approx")

        # 17 non-breaking and doubled spaces
        NB = chr(0xa0)
        tq = FX_YESTERDAY.replace("Sep 27, 2026 - Sep 27, 2026", "Sep" + NB + "27,  2026 - Sep 27, 2026").replace(
            "Avg. CPC (converted)", "Avg." + NB + "CPC (converted)").replace("47,286", "47" + NB + "286")
        rq = parse_page(tq, nab, "yesterday", "2026-09-28")
        check(rq["status"] == "ok" and rq["values"] == want and not rq["new_boxes"] and not rq["missing_boxes"],
              "17 non-breaking and doubled spaces in the label, a box label and a number still parse")

        # 18 access phrases: a chart error inside a good page; Looker's own no-access page; a page still loading
        ra = parse_page(FX_YESTERDAY.replace("Privacy Policy", "Data Set Configuration Error\nYou don't have access to "
                                             "this data source.\nPrivacy Policy"), nab, "yesterday", "2026-09-28")
        rb = parse_page("Title: Data Studio\n---\nCan't access report\nThe report may have been deleted or you may not "
                        "have permission to view it.", nab, "yesterday", "2026-09-28")
        rl = parse_page("Title: New Century BMW\nURL: %s\nSource element: <body>\n---\nprogress_activity" % nab["url"],
                        nab, "yesterday", "2026-09-28")
        check(ra["status"] == "ok" and ra["values"] == want and rb["reason"] == ACCESS_REASON
              and "had not finished loading" in rl["reason"],
              "18 a chart's access error inside the report is not ACCESS; Can't access report is; a loading page says retry")

        # 19b a read line whose browser is not text
        cfg = new_root("types")
        _write_reads("2026-09-28", [json.dumps(dict(json.loads(_read(sid, "yesterday", FX_YESTERDAY, at28)),
                                                    browser={"name": "chrome"})), _read(sid, "mtd", FX_MTD, at28)])
        try:
            rc, outt = _quiet(cmd_ingest, _Args(date="2026-09-28"))
        except Exception as e:   # the old crash: TypeError unhashable dict
            rc, outt = "crash %r" % e, ""
        check(rc == 2 and "field browser is not text" in outt, "19b a browser field that is not text is a skipped line, not a crash")

        # 20 NabThat sheet: a half-filled new month column
        def add_col(values, header, spend, fees=None):
            vv = json.loads(json.dumps(values))
            b0 = next(i for i, r in enumerate(vv) if r and r[0] == "NEW CENTURY BMW")
            if header is not None:
                vv[b0].append(header)
            vv[b0 + 1].append(spend)
            if fees is not None:
                vv[b0 + 2].append(fees)
            return vv
        na = parse_nab_sheet(add_col(FX_NAB_SHEET, "September", "$27,010.00"), nab["sheet"]["block"], "2026-10-04")
        nb = parse_nab_sheet(add_col(FX_NAB_SHEET, None, "$27,010.00", "$4,051.50"), nab["sheet"]["block"], "2026-10-04")
        nc = parse_nab_sheet(add_col(FX_NAB_SHEET, "September", "$0.00", "$0.00"), nab["sheet"]["block"], "2026-10-04")
        fa, fha = fee_for(nab, {"parsed": na, "phrase": "read tonight"})
        mda = "\n".join(nab_sheet_md(nab, {"parsed": na, "phrase": "read tonight", "compare": None}, Store("X"), 28000))
        check(na["months"][0]["ym"] == "2026-09" and any("being filled" in n for n in na["notes"])
              and fa == 0.15 and "August 2026" in fha and "September 2026 has no fees yet" in fha
              and "August 2026 total including fees $30,458.11 is over the $28,000 cap" in mda
              and nb["months"][0]["month"] == "September" and nb["months"][0]["values"]["fees"] == 4051.5
              and any("no month header yet" in n for n in nb["notes"]) and nc["months"][0]["ym"] == "2026-08",
              "20 NabThat sheet: a half-filled month is noted, fees come from August, the cap question stays; "
              "a blank header is inferred; a $0.00 placeholder is not a month")

        # 21 a late read says so
        cfg = new_root("late")
        _pages(sid, "2026-09-28", [("yesterday", FX_YESTERDAY), ("mtd", FX_MTD)], at="2026-09-28T07:02:00-07:00")
        rc, _, mdl, _ = rep("2026-09-28", "out-late")
        check("this read was taken at 7:02 AM, later than usual" in mdl and PRELIM_LABEL in mdl,
              "21 a 7:02 AM read keeps the preliminary label and adds that it was later than usual")

        # 22 NabThat's performance values never carry the whole-website boxes
        yv = js_sept["sources"][sid]["yesterday"]["values"]
        mv = js_sept["sources"][sid]["mtd"]["values"]
        sv_ = js_oct["sources"][sid]["same_weekday"]["values"]
        check(yv["clicks"] == 250 and mv["clicks"] == 6447 and sv_ and not any(
            k.startswith("site_") for x in (yv, mv, sv_) for k in x) and js_sept["sources"][sid]["site_boxes"]["mtd"][
                  "site_sessions"] == 13275,
              "22 vendor_ppc.json: no site_* key under yesterday, same_weekday or mtd values (only in site_boxes)")

        # 24 no read since {date}, per window
        cfg = new_root("since")
        _night(sid, "2026-10-06")
        for D in ("2026-10-07", "2026-10-08"):
            yy = shift_day(D, -1)
            _pages(sid, D, [("yesterday", _pg(fmt_range(yy, yy), _c(yy), _CPC, _impr(yy), _calls(yy), _views(yy))),
                            ("mtd", FX_AUTO)])
        rc, _, mdsn, _ = rep("2026-10-08", "out-since")
        check("month to date read invalid: %s; no read since 2026-10-06 (that shift's month to date read covered "
              "Oct 1 - Oct 5, 2026)" % DEFAULT_RANGE_REASON in mdsn and "no read since 2026-10-07" not in mdsn,
              "24 the month-to-date Missing tonight line names the last good month-to-date read (10/06)")

        # 25 usage errors exit 1
        ucodes = []
        for argv in (["report", "--date", "2026-09-28", "--bogus"], []):
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    main(argv)
                ucodes.append(None)
            except SystemExit as e:
                ucodes.append(e.code)
        check(ucodes == [1, 1], "25 usage errors (an unknown flag, no command) exit 1, not 2")

        # 27 / 28 / 29 wording: implied cost, the preliminary day inside MTD, flag sources in the md
        badimp = [l for m_ in (md_sept, md_oct, mds) for l in m_.splitlines()
                  if "$" in l and re.search(r"implied(?! \(clicks x avg CPC\))(?! landing)", l)]
        check(not badimp, "27 every dollar line that says implied says implied (clicks x avg CPC)%s"
              % ("" if not badimp else ": " + badimp[0][:80]))
        check("(27 of 30 days; includes the preliminary Sun 9/27, still filling in)" in md_sept and all(
            "includes the preliminary Sun 9/27" in f["text"] for f in js_sept["flags"]
            if f["code"] in ("MTD_OVER_CAP", "PACE_OVER_CAP")),
              "28 the MTD line and both cap flags say they include the preliminary Sun 9/27")
        check(js_sept["flags"] and all("- %s: %s (source: %s)" % (f["code"], f["text"], f["file"]) in md_sept
                                       for f in js_sept["flags"]),
              "29 every flag line in the md names its source file")

        # 30 Constellation turned on as the config note says
        def activate(c_):
            for s_ in c_["sources"]:
                if s_["id"] == con["id"]:
                    s_.update(status="active", url="https://datastudio.google.com/reporting/x/page/y",
                              title_contains="Google Ads Report - New Century BMW",
                              metrics=[m for m in nab["metrics"] if m["scope"] == "vendor_ads"])
        cfg = new_root("con-active", activate)
        _write_reads("2026-09-28", [_read(i_, w_, t_, at28) for i_ in (sid, con["id"])
                                    for w_, t_ in (("yesterday", FX_YESTERDAY), ("mtd", FX_MTD))])
        rc, _, mdc, jsc = rep("2026-09-28", "out-con-active")
        csec = mdc.split("## Constellation (Data Studio dashboard, read-only)")[1].split("\n## ")[0]
        check("Fee rate unknown" in csec and "Including fees" not in csec and not any(
            f["text"].startswith("Constellation's") for f in jsc["flags"] if f["code"] in ("MTD_OVER_CAP", "PACE_OVER_CAP"))
              and "## Constellation monthly sheet and GA4" in mdc and "\n## Constellation\n" not in mdc,
              "30 Constellation active with no fee rate: no including-fees figure or cap flag; one Constellation heading each")

        # ---------------- stale month to date (verifier case B7, 2026-09-28): the new label over the default
        # view's 28-day numbers (6,711 clicks, not 6,447) was accepted and fed RESTATED, pace, cap and the split
        D28, DF = "2026-09-28", DEFAULT_WINDOW
        stale_m = _relabel(FX_AUTO, "Sep 1, 2026 - Sep 27, 2026")
        wins_of = lambda D_: load_json(VD(D_, sid + ".json"))["windows"]

        # 31 guard 1: the default view is a reference line, never a window; a window that repeats it is invalid
        cfg = new_root("default")
        rd = parse_page(FX_AUTO, nab, DF, D28)
        rd2 = parse_page(_relabel(FX_AUTO, "Aug 31, 2026 - Sep 27, 2026"), nab, DF, D28)
        rc_d, out_d = _pages(sid, D28, [(DF, FX_AUTO), ("yesterday", FX_YESTERDAY), ("mtd", FX_MTD)])
        wd_ = wins_of(D28)
        evd = evaluate(cfg, D28, VD(D28, "reads.jsonl"))
        rc_s, out_s = _quiet(cmd_status, _Args(date=D28))
        check(rd["status"] == "ok" and rd["values"]["clicks"] == 6711 and rd["start"] is None
              and rd2["status"] == "ok" and rd2["start"] == "2026-08-31" and default_range(D28) == ("2026-08-31", "2026-09-27")
              and rc_d == 0 and rc_s == 0 and sorted(wd_) == ["mtd", "yesterday"] and not evd["bad"]
              and sorted(evd["sources"][sid]) == ["mtd", "yesterday"] and "default" not in out_d + out_s
              and "skipped" not in out_d + out_s and wd_["yesterday"]["line"] == 2 and wd_["mtd"]["line"] == 3,
              "31 a default line parses (Select date range or its own label, never checked), and is never a window, "
              "a status line or a bad line")
        rc_7, _ = _pages(sid, D28, [(DF, FX_AUTO), ("yesterday", FX_YESTERDAY), ("mtd", stale_m)])
        w7 = wins_of(D28)
        _pages(sid, D28, [(DF, FX_AUTO), ("yesterday", _relabel(FX_AUTO, "Sep 27, 2026 - Sep 27, 2026")), ("mtd", FX_MTD)])
        w7y = wins_of(D28)
        _pages(sid, D28, [(DF, FX_AUTO), ("yesterday", FX_YESTERDAY), ("mtd", stale_m), ("mtd", FX_MTD)])
        w7a = wins_of(D28)
        _pages(sid, D28, [(DF, FX_AUTO), ("yesterday", FX_YESTERDAY), ("mtd", FX_MTD), ("mtd", stale_m)])
        w7b = wins_of(D28)
        check(rc_7 == 2 and w7["mtd"]["status"] == "invalid" and w7["mtd"]["reason"] == DEFAULT_MATCH_REASON % 4
              and w7["mtd"]["default_line"] == 1 and w7["yesterday"]["status"] == "ok"
              and w7y["yesterday"]["status"] == "invalid" and w7y["yesterday"]["reason"] == DEFAULT_MATCH_REASON % 4
              and w7y["mtd"]["status"] == "ok",
              "31 with no history at all: a month to date (or yesterday) showing the default view's numbers is invalid "
              "(4 boxes equal)")
        check(w7a["mtd"]["status"] == "ok" and w7a["mtd"]["line"] == 4 and w7b["mtd"]["status"] == "ok"
              and w7b["mtd"]["line"] == 3 and w7b["mtd"]["values"]["clicks"] == 6447,
              "31 retries: the last month-to-date read that passes wins (stale then good: line 4; good then stale: line 3)")
        one_box = _pg("Sep 1, 2026 - Sep 27, 2026", 6711, 3.90, 900000, 400, 30000)
        zeros_d = _pg("Select date range", 6711, 3.85, 910605, 0, 0)
        _pages(sid, D28, [(DF, FX_AUTO), ("yesterday", FX_YESTERDAY), ("mtd", one_box)])
        w1b = wins_of(D28)
        _pages(sid, D28, [(DF, zeros_d), ("yesterday", _pg("Sep 27, 2026 - Sep 27, 2026", 250, 3.83, 47286, 0, 0)),
                          ("mtd", FX_MTD)])
        w0 = wins_of(D28)
        _pages(sid, D28, [(DF, FX_MTD), ("yesterday", FX_YESTERDAY), ("mtd", FX_MTD)])
        wrem = wins_of(D28)
        half_d = "\n".join(l for l in FX_AUTO.split("\n") if not parse_num(l)[0])
        rc_h, out_h = _pages(sid, D28, [(DF, half_d), ("yesterday", FX_YESTERDAY), ("mtd", FX_MTD)])
        check(w1b["mtd"]["status"] == "ok" and w0["yesterday"]["status"] == "ok" and w0["mtd"]["status"] == "ok"
              and wrem["mtd"]["status"] == "ok" and rc_h == 0 and "skipped" not in out_h,
              "31 no misfire: one equal box, equal zeros, a default page that remembered the month-to-date preset "
              "(its label is that range), a default read that never loaded (ignored, not a bad line)")
        D29, D28b = "2026-10-29", "2026-10-28"
        m29 = _pg("Oct 1, 2026 - Oct 28, 2026", 6000)
        cfg = new_root("default-29")
        rc29, _ = _pages(sid, D29, [(DF, _relabel(m29, "Select date range")), ("yesterday", _pg("Oct 28, 2026 - Oct 28, 2026", 230)),
                                    ("mtd", m29)])
        w29 = wins_of(D29)
        rc28, _ = _pages(sid, D28b, [(DF, _relabel(m29, "Select date range")), ("yesterday", _pg("Oct 27, 2026 - Oct 27, 2026", 230)),
                                    ("mtd", _relabel(m29, "Oct 1, 2026 - Oct 27, 2026"))])
        w28 = wins_of(D28b)
        check(default_range(D29) == ("2026-10-01", "2026-10-28") and rc29 == 0 and w29["mtd"]["status"] == "ok"
              and rc28 == 2 and w28["mtd"]["status"] == "invalid" and "default view" in w28["mtd"]["reason"],
              "31 on 10/29 the month to date IS the default range (Oct 1 - 28): equal numbers stay ok; on 10/28 they do not")

        # 32 guard 2: a month to date that moved more than a whole preliminary day beyond last night's
        cfg = new_root("rise")
        at27 = "2026-09-27T00:47:00-07:00"
        y26 = _pg("Sep 26, 2026 - Sep 26, 2026", 240, 3.85, 45000, 9, 1000)
        m26 = _pg("Sep 1, 2026 - Sep 26, 2026", 6170, 3.91, 840000, 369, 31000)
        _pages(sid, "2026-09-27", [("yesterday", y26), ("mtd", m26)], at=at27)
        rc_r, _ = _pages(sid, D28, [("yesterday", FX_YESTERDAY), ("mtd", stale_m)])
        wr7 = wins_of(D28)
        ns["date"] = cs["date"] = "2026-09-27"
        save_json(VD("2026-09-27", sid + ".sheet.json"), ns)
        save_json(VD("2026-09-27", con["id"] + ".sheet.json"), cs)
        save_json(P(D28, "data", "vendor_ppc_ga4_NCBMW.json"),
                  {"store": "NCBMW", "shift_date": D28, "pulled_at": at28,
                   "request": {"start": "2026-08-31", "end": "2026-09-27"},
                   "rows": _Stub(FX_NAB_SHEET).ga4_report("NCBMW", "2026-08-31", "2026-09-27", GA4_DIMS, GA4_METRICS)})
        rc, _, mdr7, jsr7 = rep(D28, "out-rise")
        c7 = [f["code"] for f in jsr7["flags"]]
        check(rc_r == 2 and wr7["mtd"]["status"] == "invalid" and wr7["yesterday"]["status"] == "ok"
              and wr7["mtd"]["reason"] == "month to date rose 291 clicks beyond the preliminary Sun 9/27, more than all of "
                                         "Sat 9/26's preliminary 240; the page likely still showed an older range; retry",
              "32 B7 with history and no default line: 6,711 - 6,170 - 250 = 291 clicks > Sat 9/26's 240: mtd invalid")
        check(rc == 2 and "READ_INVALID" in c7 and "RESTATED" not in c7 and "6,711" not in mdr7
              and jsr7["split"]["status"] == "ok" and jsr7["split"]["nabthat"]["clicks"] == 6170,
              "32 report: READ_INVALID, no false RESTATED, 6,711 nowhere; the split falls back to last night's month to date")
        rise = {}
        for name, mtd_pages in (("retry_sg", [stale_m, FX_MTD]), ("retry_gs", [FX_MTD, stale_m]),
                                ("same_as_last", [_relabel(m26, "Sep 1, 2026 - Sep 27, 2026")]),
                                ("legit_up", [_pg("Sep 1, 2026 - Sep 27, 2026", 6170 + 250 + 25, 3.90)]),
                                ("legit_down", [_pg("Sep 1, 2026 - Sep 27, 2026", 6170 + 250 - 30, 3.90)]),
                                ("edge", [_pg("Sep 1, 2026 - Sep 27, 2026", 6170 + 250 + 240, 3.90)]),
                                ("edge1", [_pg("Sep 1, 2026 - Sep 27, 2026", 6170 + 250 + 241, 3.90)])):
            _pages(sid, D28, [("yesterday", FX_YESTERDAY)] + [("mtd", t) for t in mtd_pages])
            rise[name] = wins_of(D28)["mtd"]
        check(rise["retry_sg"]["status"] == "ok" and rise["retry_sg"]["line"] == 3
              and rise["retry_gs"]["status"] == "ok" and rise["retry_gs"]["line"] == 2,
              "32 retries: the last month-to-date read that passes wins (stale then good: line 3; good then stale: line 2)")
        check(rise["same_as_last"]["status"] == "invalid" and rise["same_as_last"]["reason"] == (
            "month to date fell 250 clicks short of the 2026-09-27 read (6,170) plus the preliminary Sun 9/27 (250), "
            "more than all of Sat 9/26's preliminary 240; the page likely still showed an older range; retry"),
              "32 the symmetric case: a month to date that did not grow by the preliminary day (R = -250) is invalid")
        check(all(rise[k]["status"] == "ok" for k in ("legit_up", "legit_down", "edge")) and rise["edge1"]["status"] == "invalid",
              "32 legitimate restatements (+25, -30, exactly +240) stay ok; +241 is past Sat 9/26's 240")
        # a small day: the 100-click floor; a Monday after a weekend dip; the 1st and the 2nd of a month
        cfg = new_root("rise-cal")
        _pages(sid, "2026-10-06", [("yesterday", _pg("Oct 5, 2026 - Oct 5, 2026", 40)),
                                   ("mtd", _pg("Oct 1, 2026 - Oct 5, 2026", 900))])
        small = [_pages(sid, "2026-10-07", [("yesterday", _pg("Oct 6, 2026 - Oct 6, 2026", 50)),
                                            ("mtd", _pg("Oct 1, 2026 - Oct 6, 2026", 900 + 50 + r_))])[0] for r_ in (100, 101)]
        _pages(sid, "2026-10-11", [("yesterday", _pg("Oct 10, 2026 - Oct 10, 2026", 120)),
                                   ("mtd", _pg("Oct 1, 2026 - Oct 10, 2026", 2500))])
        rc_mon, _ = _pages(sid, "2026-10-12", [("yesterday", _pg("Oct 11, 2026 - Oct 11, 2026", 110)),
                                               ("mtd", _pg("Oct 1, 2026 - Oct 11, 2026", 2500 + 110 + 70))])
        _pages(sid, "2026-10-31", [("yesterday", _pg("Oct 30, 2026 - Oct 30, 2026", 230)),
                                   ("mtd", _pg("Oct 1, 2026 - Oct 30, 2026", 7000))])
        rc_1st, _ = _pages(sid, "2026-11-01", [("yesterday", _pg("Oct 31, 2026 - Oct 31, 2026", 220)),
                                               ("mtd", _pg("Oct 1, 2026 - Oct 31, 2026", 7000 + 220 + 15))])
        rc_2nd, _ = _pages(sid, "2026-11-02", [("yesterday", _pg("Nov 1, 2026 - Nov 1, 2026", 240)),
                                               ("mtd", _pg("Nov 1, 2026 - Nov 1, 2026", 240)),
                                               ("last_month", _pg("Oct 1, 2026 - Oct 31, 2026", 7240))])
        rc_1st_bad, _ = _pages(sid, "2026-11-01", [("yesterday", _pg("Oct 31, 2026 - Oct 31, 2026", 220)),
                                                   ("mtd", _pg("Oct 1, 2026 - Oct 31, 2026", 7000 + 220 + 231))])
        w1st = wins_of("2026-11-01")
        check(small == [0, 2] and rc_mon == 0 and rc_1st == 0 and rc_2nd == 0 and rc_1st_bad == 2
              and w1st["mtd"]["status"] == "invalid" and "more than all of Fri 10/30's preliminary 230" in w1st["mtd"]["reason"],
              "32 no misfire on a small day (floor 100: +100 ok, +101 not), a Monday after Saturday's dip (+70 on 120), "
              "the 1st (October in full) or the 2nd (new month); the 1st still catches +231 on Fri 10/30's 230")
        # compact numbers: the rounding of 6.2K and 6.5K widens the bound
        cfg = new_root("rise-compact")
        _pages(sid, "2026-09-27", [("yesterday", _pg("Sep 26, 2026 - Sep 26, 2026", 120)),
                                   ("mtd", _pg("Sep 1, 2026 - Sep 26, 2026", 6200).replace("\n6,200\n", "\n6.2K\n"))])
        cmp_ = {}
        for shown, true_ in (("6.5K", 6500), ("6.9K", 6900)):
            _pages(sid, D28, [("yesterday", _pg("Sep 27, 2026 - Sep 27, 2026", 150)),
                              ("mtd", _pg("Sep 1, 2026 - Sep 27, 2026", true_).replace("\n%s\n" % format(true_, ","),
                                                                                       "\n%s\n" % shown))])
            cmp_[shown] = wins_of(D28)["mtd"]
        check(cmp_["6.5K"]["status"] == "ok" and cmp_["6.5K"]["approx"] == ["clicks"]
              and cmp_["6.9K"]["status"] == "invalid" and "rose 550 clicks (approx, +/- 100) beyond" in cmp_["6.9K"]["reason"],
              "32 compact numbers: 6.2K -> 6.5K with 150 preliminary (R 150 +/- 100 on Sat's 120) stays ok; 6.9K does not")
    finally:
        ROOT = saved_root
        _GDATA_STUB = None
        shutil.rmtree(tmp, ignore_errors=True)
    check("gdata" not in sys.modules, "gdata was never imported")
    print("selftest: %s (%d failed)" % ("PASS" if not fails else "FAIL", len(fails)))
    return 1 if fails else 0


class _Parser(argparse.ArgumentParser):
    """Usage errors exit 1: the CLI reserves 2 for 'written, but a read is missing or invalid'."""

    def error(self, message):
        self.print_usage(sys.stderr)
        die(message, 1)


def main(argv=None):
    ap = _Parser(description="Vendor dashboards: reads, deltas, pace, GA4 cross-check, sheets and "
                             "the credit split. See the module docstring.")
    ap.add_argument("cmd", choices=["status", "ingest", "report", "selftest"])
    ap.add_argument("--date")
    ap.add_argument("--reads")
    ap.add_argument("--learn", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--no-pull", action="store_true")
    args = ap.parse_args(argv)
    if args.reads and args.cmd != "ingest":
        die("--reads goes with ingest only")
    if args.learn and args.cmd != "ingest":
        die("--learn goes with ingest only")
    if (args.out or args.no_pull) and args.cmd != "report":
        die("--out and --no-pull go with report only")
    return {"status": cmd_status, "ingest": cmd_ingest, "report": cmd_report, "selftest": cmd_selftest}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
