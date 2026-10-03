#!/usr/bin/env python3
"""Ledgers for the DigitalCLIQ AI night shift. Standard library only.

Four ledgers share this script, all under outputs/ai-team/ledgers/:
  vendor-watch.json     Vendor Waste Watch: lead vendors billing with zero or near-zero leads, per store
  asks.json             Asks and wins: every ask the team raises, from the day raised to the day closed
  rulings.json          Drew's standing rulings: answers that stay answered, so nobody asks again
  shift-ledger.jsonl    one summary row per store per target date per shift night
  settled.json          settled findings: reported and explained once, spot-checked nightly, never re-reported
  coaching.json         Magic's per-shift coaching record per player, with the promotion track
plus month-pack-{YYYY-MM}.json/.md (month to date per store, with coverage) for monthly-client-report,
and vendor-month-end-{YYYY-MM}.json/.md (keep-or-cut list per store).

Every command is one plain call from the vault root, writes its own files, prints a short summary.
  L = python3 .claude/skills/ai-team/scripts/ledgers.py

Vendor Waste Watch
  L vendor seed [--force]                seed the rows verified 2026-09-23 (NOI, from the shift files)
  L vendor scan --date D                 read D/data/crm_mtd_*.json and upsert every source that bills
                                         with zero leads, or with 2 or fewer leads on 500+ dollars
  L vendor update --store S --vendor V --date D [--spend N --leads N --sold N --as-of D --source T]
                  [--status open|confirmed-live|cut|kept|closed|ignored --note T --bench-category C --ask A2]
                                         ignored = Drew said ignore the cost; a new month's row for the same
                                         store and vendor starts ignored too
  L vendor list [--store S] [--month M] [--all] [--date D]
  L vendor month-end --month M           keep-or-cut list per store; close rates graded against the NADA
                                         table in the score-leads skill (reference/nada_benchmarks.json)
Asks and wins
  L asks seed [--force]
  L asks add --store S --owner O --label L --ask T --evidence T --date D [--needs-store]
             [--if-skipped T --done-when T --vendors V1,V2]
  L asks update --id A3 --date D [--evidence T --ask T --owner O ...] [--no-raise] [--trip-wire T]
  L asks close --id A3 --date D --evidence T [--win T]
  L asks withdraw --id A3 --date D --reason T
  L asks park --id A3 --date D [--days 14] --reason T
                                         status parked: off the aging list until park_until (date + days)
  L asks apply-answers --file PATH --date D [--dry-run]
                                         apply slack.py ask-answers JSON: done closes, drop withdraws and
                                         adds a ruling, park parks 14 days, note goes in the ask's history.
                                         Reads {"answers": [...]} or a bare list; each item: id, decision
                                         (done|drop|park|note, or go, x, zzz, white_check_mark), ts (or reply_ts,
                                         slack_ts), how ("reaction :x:", "reply"), text, answered_at, days, lane.
                                         An answer from outside Slack has no ts; its how says where. Re-applying
                                         the same file changes nothing.
  L asks list [--status open|closed|withdrawn|parked|all] [--store S]
  L asks aging --date D [--out PATH] [--friday]
                                         brief blocks: Asks aging, Closed tonight, GM requests due, and
                                         Stuck (Friday digest) on a Friday or with --friday
  L asks request --id A3 --date D        GM-level request skeleton for Drew to forward (nothing is sent)
  L asks request --due --date D          one skeleton for every ask that is due
  Owner is "Drew", "store: {role}" or "team: {player}". --needs-store marks an ask that waits on store
  staff; after 3 business days open it shows under GM requests due.
  Stuck: a Drew-owned ask raised 3+ times since Drew last answered it leaves the nightly list for the
  Friday digest; an update with --trip-wire (cost jump, deadline inside a week, new fact) brings it back
  that night. A raise on an ask a standing ruling applies to is refused with a warning naming the ruling.
Standing rulings
  L rulings add --store S --lane L --ruling T --source T [--date D] [--asks A2,A21] [--expires D]
                 --lane is all, or one or more of kobe,shaq,luka,worthy,nick,magic (comma list).
                 --expires D: the ruling stops applying on D. The same store and text twice is one ruling.
  L rulings list [--store S] [--lane L] [--date D] [--all] [--md]
                 --md prints one compact block to paste into spawn prompts (expired ones only with --all)
Shift ledger and month pack
  L shift append --date D                rows for every target date found in outputs/ai-team/D/
  L shift backfill --from D --to D
  L shift set --date D --store S --field F --value V --source T [--target-date D]
  L shift set --file PATH                bulk overrides, a JSON list of the same keys
  L shift list [--date D]
  L month --month YYYY-MM                month-pack-{M}.json and .md
  L week --date D [--out DIR]            Saturday wrap: Mon to Fri before D vs the week before, per store,
                                         to outputs/ai-team/D/data/week.md and week.json
  L ads-dump --date D                    save each Ads export Sheet's campaign_daily_30d (and meta tab)
                                         to D/data/{STORE}_campaign_daily_30d.txt (read-only, gdata auth)
CRM snapshot contract
  L crm-shape                            print the crm_mtd_{STORE}.json shape Nick writes every night
  L crm-check --file PATH                validate one snapshot against it
  L crm-correct --shift D --store S --source X --field cost --value 0 --reason T
Shift log clock (added 2026-09-28: real times from the machine clock, never estimates)
  L log --date D --text T [--mode shift|dry-run]
                                         append "- HH:MM PDT T" to outputs/ai-team/D/shift-log.md (America/Los_Angeles,
                                         PST in winter); creates the file with the standard header when missing
  L log --date D --start                 "- Start: HH:MM PDT (Weekday, mode shift)"
  L log --date D --end                   the final whistle "- End: HH:MM PDT" (tipoff.sh closes the session two minutes
                                         after it sees a new End line, so it is the last thing written)
  L log --stamp-only                     print the current "HH:MM PDT"
Settled findings (added 2026-09-28: no repeating a finding night after night; the spot checks go on)
  L settled add --store S --lane L --subject T --keywords a,b --finding T --source T --reopen-if T --date D
                [--owner P --first-seen D]
  L settled check --date D --id S3 --still-true yes|no --note T [--by P]
                                         a player's nightly spot check: updates last_checked; "no" reopens the item
                                         and prints a FOR MAGIC line
  L settled update --id S3 --date D [--status settled|reopened|retired --finding T --source T --reopen-if T
                   --subject T --keywords a,b --lane L --owner P --store S --note T]
  L settled list [--lane P] [--store S] [--date D] [--all] [--md]
                                         --md prints one compact block for spawn prompts; without it, the list ends with
                                         who checked tonight and who did not
  L settled scan --file PATH [--lane P]  lines in a findings file that read like a settled item without citing its id
  L settled seed [--force]               the items that repeated in the 2026-09-22 to 09-28 briefs and shift logs
Coaching and promotion track (added 2026-09-28)
  L coach add --player P --date D [--bounce CAUSE --factual yes|no]... [--self-caught N] [--thought-ahead T]...
              [--peer-catch T]... --note T
                                         one entry per player per shift (a second add for the same date replaces it);
                                         prints PROMOTION when the entry earns the next level
  L coach list --player P [--last 5] [--md]    level, streak and recent notes, for the spawn prompt
  L coach scorecard [--md] [--date D]          every player: level, clean streak, factual and wording bounces in the
                                               last 10 shifts, self-catches, thought-ahead, next level and what is missing
  L coach level --player P --level L --date D --reason T    set a level by hand (Magic's or Drew's call)
  L coach seed [--force]                       backfill 2026-09-22 to 09-28 from the shift logs' bounce lines
  Levels: rookie (a new player; starter after 5 clean shifts in a row), starter (the current five), senior (10 clean
  shifts in a row and 3 thought-ahead items Magic confirmed, both at starter), captain (20 clean shifts in a row as
  senior and 2 peer-review catches of real problems). A factual bounce (wrong number, unsourced claim, wrong actor,
  wrong window) resets the streak; a wording bounce does not.
Self test
  L selftest                             offline checks in a temp folder, touches nothing real

Text flags (--ask, --evidence, --win, --reason, --note, --source, --if-skipped, --done-when, --ruling,
--trip-wire, --text, --subject, --finding, --reopen-if) also take
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
VENDOR_STATUSES = ("open", "confirmed-live", "cut", "kept", "closed", "ignored")
VENDOR_CARRY = ("ignored",)  # a new month's row starts with this status when last month's row had it
ASK_STATUSES = ("open", "closed", "withdrawn", "parked")
LANES = ("all", "kobe", "shaq", "luka", "worthy", "nick", "magic")
STUCK_RAISES = 3        # Drew-owned ask raised this many times with no answer from Drew: Friday digest
PARK_DAYS = 14
HINT_WORDS = 3          # shared distinctive words before asks add/update says a ruling may cover an ask
HINT_STOP = set("""about above after again against along also another around asked asking because been
before being below between both cannot change changed check confirm could daily does doing done during each
either every first from further have having here into just keeps later least month months more most night
nights other ours over raise raised same should since some still store stores such than that their them then
there these they this those through today tonight under until very were what when where whether which while
with within without would""".split())
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


# ---------------------------------------------------------------- week pack (Saturday wrap)

def week_window(date):
    """Saturday's shift (date D) covers Monday to Friday of the week that ends the day before D.
    Any other date: Monday of the week holding D - 1, through D - 1."""
    end = dt.date.fromisoformat(iso(date)) - dt.timedelta(days=1)
    start = end - dt.timedelta(days=end.weekday())
    return start.isoformat(), end.isoformat()


def harvest_span(fn, days):
    """Run a month harvester for every month the days touch and keep only those days."""
    out = {}
    for m in sorted({d[:7] for d in days}):
        got = fn(m)
        for k, v in got.items():
            if isinstance(v, dict) and k in STORES:
                out.setdefault(k, {}).update({d: x for d, x in v.items() if d in days})
            elif k in days:
                out[k] = v
    return out


def crm_week(store, days, snaps):
    """CRM change across the days, from month-to-date snapshots: end minus base, per month part."""
    fields = ("leads", "appointments", "shows", "sold")
    parts, total = [], {f: 0 for f in fields}
    for m in sorted({d[:7] for d in days}):
        md = [d for d in days if d.startswith(m)]
        mine = [(n["period_end"], sd, p, n) for (sd, p, n) in snaps
                if n["store"] == store and str(n.get("period_end") or "").startswith(m) and n.get("headline")]
        ends = [x for x in mine if md[0] <= x[0] <= md[-1]]
        if not ends:
            parts.append({"month": m, "days": [md[0], md[-1]], "status": "no snapshot inside these days"})
            continue
        e = sorted(ends, key=lambda x: (x[0], x[1]))[-1]
        if md[0].endswith("-01"):
            b, base_end = None, None
        else:
            bases = [x for x in mine if x[0] < md[0]]
            if not bases:
                parts.append({"month": m, "days": [md[0], md[-1]], "status": "no snapshot before %s to subtract" % md[0],
                              "end_snapshot": rel(e[2])})
                continue
            b = sorted(bases, key=lambda x: (x[0], x[1]))[-1]
            base_end = b[0]
        inc = {}
        for f in fields:
            ev = e[3]["headline"].get(f)
            bv = b[3]["headline"].get(f) if b else 0
            inc[f] = (ev - bv) if isinstance(ev, (int, float)) and isinstance(bv, (int, float)) else None
        first = (dt.date.fromisoformat(base_end) + dt.timedelta(days=1)).isoformat() if base_end else md[0]
        parts.append({"month": m, "covers": [first, e[0]], "increment": inc, "end_snapshot": rel(e[2]),
                      "base_snapshot": rel(b[2]) if b else "month start", "status": "ok"})
        for f in fields:
            total[f] = None if (total[f] is None or inc[f] is None) else total[f] + inc[f]
    ok = [p for p in parts if p["status"] == "ok"]
    return {"parts": parts, "total": total if ok else None,
            "covers": [ok[0]["covers"][0], ok[-1]["covers"][1]] if ok else None}


def _pct(a, b):
    return None if not b or a is None else round((a - b) / b * 100, 1)


def cmd_week(args):
    date = iso(args.date)
    start, end = week_window(date)
    days = daterange(start, end)
    pstart, pend = [(dt.date.fromisoformat(x) - dt.timedelta(days=7)).isoformat() for x in (start, end)]
    pdays = daterange(pstart, pend)
    ga4 = harvest_span(harvest_ga4, days + pdays)
    ads = harvest_span(harvest_ads, days + pdays)
    meta = harvest_span(harvest_meta, days + pdays)
    snaps = crm_snapshots()
    ledger = read_ledger()
    asks = (load_json(LP("asks.json"), {"asks": []}) or {}).get("asks", [])
    shifts = [d for d in shift_dates() if start < d <= date]
    pack = {"schema": "week-pack.v1", "shift_date": date, "week": [start, end], "prior_week": [pstart, pend],
            "preliminary_day": end, "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
            "how_to_use": ("Monday to Friday totals per store from the night-shift folders, against the same five "
                           "days a week earlier. %s is the newest day and preliminary (read at 1 AM); the prior week is "
                           "final. A source with fewer than five days is partial and says which days it has. CRM is "
                           "the change between month-to-date snapshots, with the days it actually covers." % end),
            "shifts_this_week": [{"date": d, "brief": rel(os.path.join(ROOT, "outputs", "ai-team", d, "brief.md"))
                                  if os.path.exists(os.path.join(ROOT, "outputs", "ai-team", d, "brief.md")) else None}
                                 for d in shifts],
            "stores": {}}

    def sum_days(src, store, dd, keys):
        have = [d for d in dd if store in src and d in src[store] and src[store][d][1]]
        tot = {k: 0 for k in keys}
        for d in have:
            for k in keys:
                tot[k] += src[store][d][1][k]
        return {"days": have, "totals": {k: round(v, 2) for k, v in tot.items()}}

    def meta_days(store, dd):
        have = [d for d in dd if d in meta]
        tot = {"spend": 0.0, "clicks": 0, "lpv": 0}
        for d in have:
            md = meta_store_day(meta[d][1], store, d)
            for k in tot:
                tot[k] += md[k]
        return {"days": have, "totals": {"spend": round(tot["spend"], 2), "clicks": tot["clicks"],
                                         "landing_page_views": tot["lpv"]}}

    def back7(have):
        # the prior week is compared on the same weekdays this week has, never 4 days against 5
        return [(dt.date.fromisoformat(d) - dt.timedelta(days=7)).isoformat() for d in have]

    def pair(fn):
        w = fn(days)
        return {"week": w, "prior": fn(back7(w["days"]))}

    for s in STORES:
        st = {"name": STORE_NAMES[s]}
        g_keys = ("sessions", "engaged", "key_events", "organic", "ai")
        st["ga4"] = pair(lambda dd: sum_days(ga4, s, dd, g_keys))
        st["ga4"]["clean_key_events"] = {r["target_date"]: r["clean_key_events"] for r in ledger
                                         if r["store"] == s and r["target_date"] in days
                                         and r.get("clean_key_events") is not None}
        st["ga4"]["key_events_notes"] = sorted({"%s: %s" % (r["target_date"], r["key_events_note"]) for r in ledger
                                                if r["store"] == s and r["target_date"] in days and r.get("key_events_note")})
        a_keys = ("cost", "clicks", "impressions", "conversions")
        st["google_ads"] = pair(lambda dd: sum_days(ads, s, dd, a_keys))
        st["meta"] = pair(lambda dd: meta_days(s, dd))
        st["crm"] = {"week": crm_week(s, days, snaps), "prior": crm_week(s, pdays, snaps)}
        st["asks_opened"] = [{"id": x["id"], "label": x["label"]} for x in asks
                             if x["store"] in (s, "ALL") and start <= str(x.get("first_raised") or "") <= date]
        st["asks_closed"] = [{"id": x["id"], "label": x["label"], "status": x["status"], "win": x.get("win")}
                             for x in asks if x["store"] in (s, "ALL") and x["status"] in ("closed", "withdrawn")
                             and start <= str(x.get("closed_date") or "") <= date]
        pack["stores"][s] = st
    out = args.out or os.path.join(ROOT, "outputs", "ai-team", date, "data")
    save_json(os.path.join(out, "week.json"), pack)
    save_text(os.path.join(out, "week.md"), week_md(pack))
    print("week %s to %s (vs %s to %s): wrote %s/week.md and week.json from %d shift folder(s)."
          % (start, end, pstart, pend, rel(out), len(shifts)))
    for s in STORES:
        st = pack["stores"][s]
        print("  %-5s ga4 %d/5 days, gads %d/5, meta %d/5, crm %s" % (
            s, len(st["ga4"]["week"]["days"]), len(st["google_ads"]["week"]["days"]), len(st["meta"]["week"]["days"]),
            "%s to %s" % tuple(st["crm"]["week"]["covers"]) if st["crm"]["week"]["covers"] else "none"))


def week_md(pack):
    start, end = pack["week"]
    pstart, pend = pack["prior_week"]

    def span(days, n=5):
        if not days:
            return "no days"
        return "all five days" if len(days) == n else "%d of %d days (%s)" % (
            len(days), n, ", ".join(dt.date.fromisoformat(d).strftime("%a %-m/%-d") for d in days))

    def vs(a, b, f):
        p = _pct(a, b)
        return "%s vs %s%s" % (f(a), f(b), "" if p is None else " (%+.1f%%)" % p)

    lab = lambda d: dt.date.fromisoformat(d).strftime("%a %-m/%-d")
    L = ["---", "type: ai-team-week-pack", "date: %s" % pack["shift_date"], "status: generated",
         "tags: [ai-team, ledgers, weekly-wrap]", "---", "",
         "# AI team week pack, %s to %s" % (lab(start), lab(end)), "",
         "Built by `ledgers.py week` for the Saturday wrap. This week (%s to %s) against the week before (%s to %s). "
         "%s is preliminary (read at 1 AM), so every week total that includes it is preliminary too; the prior week "
         "is final. Each prior-week figure is summed on the same weekdays this week has, so a partial source "
         "still compares like for like; its day list shows what is missing." % (lab(start), lab(end), lab(pstart), lab(pend), lab(end)), "",
         "Shifts this week: " + (", ".join("%s%s" % (lab(x["date"]), "" if x["brief"] else " (no brief)")
                                           for x in pack["shifts_this_week"]) or "none"), ""]
    for s, st in pack["stores"].items():
        L.append("## [[%s]] (%s)" % (s if s != "ATLAS" else "Atlas", st["name"]))
        g, gp = st["ga4"]["week"], st["ga4"]["prior"]
        if g["days"]:
            L.append("- GA4, %s: sessions %s; key events %s; Organic Search %s; AI Assistant %s. Prior week read on %s." % (
                span(g["days"]), vs(g["totals"]["sessions"], gp["totals"]["sessions"], fmt_num),
                vs(g["totals"]["key_events"], gp["totals"]["key_events"], fmt_num),
                vs(g["totals"]["organic"], gp["totals"]["organic"], fmt_num),
                vs(g["totals"]["ai"], gp["totals"]["ai"], fmt_num), span(gp["days"])))
        else:
            L.append("- GA4: no pulls this week.")
        if st["ga4"]["clean_key_events"]:
            L.append("  - Clean key events (Kobe): " + ", ".join(
                "%s %s" % (lab(d), v) for d, v in sorted(st["ga4"]["clean_key_events"].items())))
        for n in st["ga4"]["key_events_notes"][-2:]:
            L.append("  - Key events caveat: " + n)
        a, ap = st["google_ads"]["week"], st["google_ads"]["prior"]
        if a["days"]:
            L.append("- Google Ads, %s: cost %s; clicks %s; conversions %s. Prior week read on %s." % (
                span(a["days"]), vs(a["totals"]["cost"], ap["totals"]["cost"], fmt_money),
                vs(a["totals"]["clicks"], ap["totals"]["clicks"], fmt_num),
                vs(a["totals"]["conversions"], ap["totals"]["conversions"], fmt_num), span(ap["days"])))
        else:
            L.append("- Google Ads: no export in this week's shift folders.")
        m, mp = st["meta"]["week"], st["meta"]["prior"]
        if m["days"]:
            L.append("- Meta, %s: spend %s; clicks %s; landing page views %s. Prior week read on %s." % (
                span(m["days"]), vs(m["totals"]["spend"], mp["totals"]["spend"], fmt_money),
                vs(m["totals"]["clicks"], mp["totals"]["clicks"], fmt_num),
                vs(m["totals"]["landing_page_views"], mp["totals"]["landing_page_views"], fmt_num), span(mp["days"])))
        else:
            L.append("- Meta: no Meta pull this week.")
        c, cp = st["crm"]["week"], st["crm"]["prior"]
        if c["total"]:
            t = c["total"]
            L.append("- CRM, %s to %s: leads %s, appointments %s, shows %s, sold %s%s." % (
                lab(c["covers"][0]), lab(c["covers"][1]), fmt_num(t["leads"]), fmt_num(t["appointments"]),
                fmt_num(t["shows"]), fmt_num(t["sold"]),
                ". Prior week %s to %s: leads %s, sold %s" % (lab(cp["covers"][0]), lab(cp["covers"][1]),
                                                              fmt_num(cp["total"]["leads"]), fmt_num(cp["total"]["sold"]))
                if cp["total"] else ". No prior-week CRM to compare"))
            for p in c["parts"]:
                if p["status"] != "ok":
                    L.append("  - CRM gap %s to %s: %s." % (lab(p["days"][0]), lab(p["days"][1]), p["status"]))
        else:
            L.append("- CRM: no usable snapshots this week (%s)." % "; ".join(p["status"] for p in c["parts"]))
        if st["asks_opened"]:
            L.append("- Asks raised this week: " + ", ".join("%s %s" % (x["id"], x["label"]) for x in st["asks_opened"]))
        if st["asks_closed"]:
            L.append("- Closed this week: " + ", ".join("%s %s (%s%s)" % (x["id"], x["label"], x["status"],
                                                                      ", win" if x["win"] else "")
                                                        for x in st["asks_closed"]))
        L.append("")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- Vendor Waste Watch

VENDOR_ABOUT = ("Vendor Waste Watch. One row per store, vendor and month for a lead vendor billing with zero or "
                "near-zero leads. Status: open (flagged, unconfirmed by the store), confirmed-live, cut, kept, "
                "closed (not live, or no longer a concern), ignored (Drew said ignore the cost; the next month's "
                "row for the same store and vendor starts ignored too, so it is never raised again). Rows stay "
                "open and unconfirmed until the store confirms the vendor is live.")


def vendor_load():
    data = load_json(LP("vendor-watch.json"), None) or {"rows": []}
    data["_about"] = VENDOR_ABOUT
    return data


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
        last = sorted(prior, key=lambda r: r["month"])[-1] if prior else None
        if last and last.get("status") in VENDOR_CARRY and not status:
            row["status"] = last["status"]
            row["note"] = last.get("note")
            row["status_history"].append({"date": date, "status": last["status"],
                                          "note": "carried from %s (%s): %s" % (last["id"], last["month"], last.get("note"))})
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
    if st == "ignored":
        return "ignore per Drew (cost page stale), clean up the cost page"
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
            if e["status"] in ("closed", "ignored"):
                b = {"category": None, "rate": None, "label": "n/a (not live)" if e["status"] == "closed"
                     else "n/a (ignored per Drew)", "source": None}
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

ASKS_ABOUT = ("Asks and wins. Every ask the team raises, from the day raised to the day closed. Owner is Drew, "
              "'store: {role}' or 'team: {player}'. needs_store asks that sit 3+ business days get a GM-level "
              "request draft in outputs/ai-team/asks/requests/ for Drew to forward. A closed ask with a 'win' is a "
              "dated, sourced win for the monthly report. Status parked hides an ask from the aging list until "
              "park_until. drew_answers lists every answer Drew gave (Slack ts, or where he gave it); a Drew-owned "
              "ask raised 3+ times since his last answer is stuck and goes to the Friday digest. An ask a ruling in "
              "rulings.json applies to is never raised again.")


def asks_load():
    data = load_json(LP("asks.json"), None) or {"asks": []}
    data["_about"] = ASKS_ABOUT
    return data


def ask_find(data, aid):
    for a in data["asks"]:
        if a["id"].upper() == str(aid).strip().upper():
            return a
    return None


def ask_get(data, aid):
    a = ask_find(data, aid)
    if a is None:
        die("no ask %s in asks.json" % aid)
    return a


def days_open(a, date):
    return (dt.date.fromisoformat(date) - dt.date.fromisoformat(a["first_raised"])).days


def ask_live(a, date):
    """Open, or parked with its park_until reached (it comes back on park_until)."""
    return a["status"] == "open" or (a["status"] == "parked" and (a.get("park_until") or "") <= date)


def drew_answer_dates(a):
    ds = [x.get("date") for x in a.get("drew_answers") or [] if x.get("date")]
    ds += [h.get("date") for h in a.get("history") or [] if h.get("action") in ("drew-note", "drew-answer")]
    return sorted(d for d in ds if d)


def raises_unanswered(a):
    """Raise dates after Drew's last answer on this ask (every raise when he never answered)."""
    ans = drew_answer_dates(a)
    return [d for d in sorted(a.get("raised") or []) if not ans or d > ans[-1]]


def is_stuck(a):
    return str(a.get("owner", "")).startswith("Drew") and len(raises_unanswered(a)) >= STUCK_RAISES


def trip_wire_on(a, date):
    return next((h["trip_wire"] for h in reversed(a.get("history") or [])
                 if h.get("date") == date and h.get("trip_wire")), None)


def ask_park(a, date, days, reason):
    until = (dt.date.fromisoformat(date) + dt.timedelta(days=int(days))).isoformat()
    a.update({"status": "parked", "park_until": until, "parked_date": date, "park_reason": reason})
    a["history"].append({"date": date, "action": "parked", "until": until, "note": reason})
    return until


# ---------------------------------------------------------------- Standing rulings

RULINGS_ABOUT = ("Drew's standing rulings. An answer Drew gave once stays answered: nobody raises its subject as "
                 "an ask or a finding again. lane is who must read it (all, or player names). applies_to_asks are the "
                 "asks it settles; a raise on one of them is refused. expires is the date it stops applying (null = "
                 "standing). Add with ledgers.py rulings add; players read ledgers.py rulings list --md.")


def rulings_load():
    data = load_json(LP("rulings.json"), None) or {"rulings": []}
    data["_about"] = RULINGS_ABOUT
    return data


def lanes_arg(s):
    lanes = [x.strip().lower() for x in re.split(r"[,\s+]+", str(s or "")) if x.strip()]
    bad = [x for x in lanes if x not in LANES]
    if not lanes or bad:
        die("--lane must be all, or one or more of %s (comma list), got %r" % (", ".join(LANES[1:]), s))
    return ["all"] if "all" in lanes else sorted(set(lanes), key=LANES.index)


def ids_arg(s):
    return [x.strip().upper() for x in re.split(r"[,\s]+", str(s or "")) if x.strip()]


def ruling_active(r, date):
    return not r.get("expires") or r["expires"] > date


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def ruling_add(data, store, lanes, text, source, date, asks=None, expires=None, added=None):
    """(ruling, created). Same store and text as a ruling on file: that one, with any new asks and lanes merged."""
    asks = [x for x in (asks or []) if x]
    for r in data["rulings"]:
        if r["store"] == store and _norm(r["ruling"]) == _norm(text):
            r["applies_to_asks"] = sorted(set(r.get("applies_to_asks") or []) | set(asks),
                                          key=lambda x: int(x[1:]) if x[1:].isdigit() else 0)
            if "all" not in r["lane"]:
                r["lane"] = ["all"] if "all" in lanes else sorted(set(r["lane"]) | set(lanes), key=LANES.index)
            return r, False
    m = re.search(r"\bts[:\s]+(\d{9,}\.\d{6})\b", source or "")
    r = {"id": next_id(data["rulings"], "R"), "date": date, "store": store, "lane": lanes, "ruling": text,
         "source": source, "slack_ts": m.group(1) if m else None, "applies_to_asks": asks, "expires": expires,
         "added": added or dt.date.today().isoformat()}
    data["rulings"].append(r)
    return r, True


def rulings_for_ask(a, rulings, date):
    return [r for r in rulings if ruling_active(r, date) and a["id"].upper() in [x.upper() for x in r.get("applies_to_asks") or []]]


def _words(s):
    s = re.sub(r"'s\b", "", str(s or "").lower().replace(chr(8217), "'"))
    return {w for w in re.findall(r"[a-z0-9][a-z0-9.&-]*[a-z0-9]", s) if len(w) >= 5 and w not in HINT_STOP}


def ruling_hints(store, text, rulings, date, skip=()):
    """Active rulings for the same store that share HINT_WORDS or more distinctive words with the text."""
    out = []
    mine = _words(text)
    for r in rulings:
        if r["id"] in skip or not ruling_active(r, date):
            continue
        if not (store == "ALL" or r["store"] in (store, "ALL")):
            continue
        shared = sorted(mine & _words(r["ruling"]))
        if len(shared) >= HINT_WORDS:
            out.append((r, shared))
    return out


def ruling_line(r):
    lanes = "all lanes" if "all" in r["lane"] else " + ".join(r["lane"])
    extra = []
    if r.get("applies_to_asks"):
        extra.append("Settles " + ", ".join(r["applies_to_asks"]) + ".")
    if r.get("expires"):
        extra.append("Until %s." % r["expires"])
    return "%s %s, %s (%s): %s%s Source: %s." % (r["id"], r["store"], lanes, r["date"], r["ruling"].rstrip(),
                                               "" if r["ruling"].rstrip().endswith(".") else ".",
                                               r["source"].rstrip(". ")) + ("" if not extra else " " + " ".join(extra))


def cmd_rulings_add(args):
    date = iso(args.date) if args.date else dt.date.today().isoformat()
    store = store_arg(args.store, allow_all=True)
    lanes = lanes_arg(args.lane)
    text = text_arg(args, "ruling", required=True)
    source = text_arg(args, "source", required=True)
    asks = ids_arg(args.asks)
    expires = iso(args.expires, "--expires") if args.expires else None
    data = rulings_load()
    r, created = ruling_add(data, store, lanes, text, source, date, asks, expires)
    save_json(LP("rulings.json"), data)
    print("rulings add: %s %s %s, lanes %s%s." % ("added" if created else "already on file as", r["id"], r["store"],
                                                  ", ".join(r["lane"]), ", settles " + ", ".join(r["applies_to_asks"])
                                                  if r["applies_to_asks"] else ""))
    adata = asks_load() if os.path.exists(LP("asks.json")) else {"asks": []}
    for aid in asks:
        a = ask_find(adata, aid)
        if a is None:
            print("WARNING: %s is not in asks.json; the ruling keeps it anyway." % aid)
        elif a["status"] in ("open", "parked"):
            print("  %s is still %s: settle it with `ledgers.py asks withdraw --id %s --date %s --reason "
                  "\"Settled by ruling %s\"` (any raise is now refused)." % (aid, a["status"], aid,
                                                                           dt.date.today().isoformat(), r["id"]))


def rulings_md(rows, date, filters):
    head = "**Drew's standing rulings** (%d%s, as of %s%s). Settled: never raise these as asks or findings, cite " \
           "the ruling id instead. New data that contradicts one goes to Magic once, with the evidence." % (
               len(rows), "" if filters.get("all") else " active", date,
               "".join(", %s %s" % (k, v) for k, v in filters.items() if v and k != "all"))
    return "\n".join([head] + (["- " + ruling_line(r) for r in rows] or ["- None on file."])) + "\n"


def cmd_rulings_list(args):
    date = iso(args.date) if args.date else dt.date.today().isoformat()
    rows = rulings_load()["rulings"]
    if not args.all:
        rows = [r for r in rows if ruling_active(r, date)]
    store = store_arg(args.store, allow_all=True) if args.store else None
    if store:
        rows = [r for r in rows if store == "ALL" or r["store"] in (store, "ALL")]
    lane = None
    if args.lane:
        ls = lanes_arg(args.lane)
        if len(ls) != 1:
            die("rulings list --lane takes one lane")
        lane = ls[0]
        rows = [r for r in rows if "all" in r["lane"] or lane in r["lane"]]
    if args.md:
        print(rulings_md(rows, date, {"store": store, "lane": lane, "all": args.all}), end="")
        return
    for r in rows:
        print("- " + ruling_line(r))
    print("rulings list: %d %sruling(s)%s" % (len(rows), "" if args.all else "active ",
                                              "" if args.all else " (--all adds expired ones)"))


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
    for r, shared in ruling_hints(a["store"], " ".join([a["label"], a["ask"]]), rulings_load()["rulings"], date):
        print("WARNING: ruling %s may already settle %s (shared words: %s). Read it: %s If it does, withdraw %s "
              "citing %s." % (r["id"], a["id"], ", ".join(shared), ruling_line(r), a["id"], r["id"]))


def raise_refused(a, date, rulings):
    """Warnings for a raise that must not count: a ruling applies, or the ask is still parked."""
    out = []
    for r in rulings_for_ask(a, rulings, date):
        out.append("WARNING: %s is settled by ruling %s (%s, %s): raise not counted. Withdraw it: "
                   "`ledgers.py asks withdraw --id %s --date %s --reason \"Settled by ruling %s\"`. %s"
                   % (a["id"], r["id"], r["store"], r["date"], a["id"], date, r["id"], ruling_line(r)))
    if a["status"] == "parked" and (a.get("park_until") or "") > date:
        out.append("WARNING: %s is parked until %s (%s): raise not counted." % (a["id"], a["park_until"],
                                                                               a.get("park_reason") or "no reason"))
    return out


def cmd_asks_update(args):
    date = iso(args.date)
    data = asks_load()
    a = ask_get(data, args.id)
    rulings = rulings_load()["rulings"]
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
    trip = text_arg(args, "trip_wire")
    action = "raised" if not args.no_raise else "edited"
    if not args.no_raise and a["status"] in ("closed", "withdrawn"):
        die("%s is %s; do not raise it again (check rulings list). Use --no-raise to edit its text." % (a["id"], a["status"]))
    warnings = []
    if not args.no_raise and a["status"] in ("open", "parked"):
        warnings = raise_refused(a, date, rulings)
        if warnings:
            action = "raise-refused"
        else:
            if a["status"] == "parked":  # park_until reached: back on the list
                a["status"] = "open"
                a["history"].append({"date": date, "action": "unparked", "note": "park_until %s reached" % a.get("park_until")})
            a["last_raised"] = max(a["last_raised"], date)
            a["raised"] = sorted(set(a["raised"]) | {date})
    h = {"date": date, "action": action, "changed": changed, "note": note}
    if warnings:
        h["refused_by"] = [r["id"] for r in rulings_for_ask(a, rulings, date)] or ["parked"]
    if trip:
        h["trip_wire"] = trip
    a["history"].append(h)
    save_json(LP("asks.json"), data)
    for w in warnings:
        print(w)
    if not warnings and action == "raised" and not rulings_for_ask(a, rulings, date):
        for r, shared in ruling_hints(a["store"], " ".join([a["label"], a["ask"]]), rulings, date):
            print("WARNING: ruling %s may already settle %s (shared words: %s). If it does, withdraw %s citing %s, "
                  "or add %s to the ruling's asks." % (r["id"], a["id"], ", ".join(shared), a["id"], r["id"], a["id"]))
    stuck = is_stuck(a) and a["status"] == "open" and not warnings
    print("asks update: %s %s, %s, open %d days%s%s%s." % (
        a["id"], a["label"], a["status"], days_open(a, date), ", changed " + ", ".join(changed) if changed else "",
        ", raise not counted" if warnings else "",
        (", trip wire: back on tonight's list" if trip else ", stuck (raised %d times since Drew last answered): "
         "Friday digest only" % len(raises_unanswered(a))) if stuck else ""))


def ask_close(a, date, evidence, win=None):
    a.update({"status": "closed", "closed_date": date, "closure_evidence": evidence, "win": win})
    a["history"].append({"date": date, "action": "closed", "note": evidence})


def ask_withdraw(a, date, reason):
    a.update({"status": "withdrawn", "closed_date": date, "withdrawn_reason": reason})
    a["history"].append({"date": date, "action": "withdrawn", "note": reason})


def cmd_asks_close(args):
    date = iso(args.date)
    data = asks_load()
    a = ask_get(data, args.id)
    if a["status"] not in ("open", "parked"):
        die("%s is already %s" % (a["id"], a["status"]))
    ask_close(a, date, text_arg(args, "evidence", required=True), text_arg(args, "win"))
    save_json(LP("asks.json"), data)
    print("asks close: %s %s closed %s after %d days%s." % (
        a["id"], a["label"], date, days_open(a, date), ", win recorded for the monthly report" if a["win"] else ""))


def cmd_asks_withdraw(args):
    date = iso(args.date)
    data = asks_load()
    a = ask_get(data, args.id)
    if a["status"] not in ("open", "parked"):
        die("%s is already %s" % (a["id"], a["status"]))
    ask_withdraw(a, date, text_arg(args, "reason", required=True))
    save_json(LP("asks.json"), data)
    print("asks withdraw: %s %s withdrawn %s." % (a["id"], a["label"], date))


def cmd_asks_park(args):
    date = iso(args.date)
    days = int(args.days if args.days is not None else PARK_DAYS)
    if days < 1:
        die("--days must be 1 or more")
    data = asks_load()
    a = ask_get(data, args.id)
    if a["status"] not in ("open", "parked"):
        die("%s is already %s" % (a["id"], a["status"]))
    until = ask_park(a, date, days, text_arg(args, "reason", required=True))
    save_json(LP("asks.json"), data)
    print("asks park: %s %s parked %s, back on the aging list %s (%d days)." % (a["id"], a["label"], date, until, days))


# Words slack.py ask-answers may use for each decision (checkmark = done or go, X = drop, zzz = park).
DECISIONS = {"done": ("done", "go", "close", "closed", "yes", "approved", "white_check_mark", "heavy_check_mark",
                      "check", "checkmark", "+1"),
             "drop": ("drop", "dropped", "no", "x", "heavy_multiplication_x", "negative_squared_cross_mark",
                      "withdraw", "withdrawn", "kill", "never"),
             "park": ("park", "parked", "later", "snooze", "zzz", "sleeping"),
             "note": ("note", "comment", "reply", "question", "info")}


def answer_fields(x):
    """One ask-answers item in any of the shapes slack.py may write, as a flat dict (or None)."""
    if not isinstance(x, dict):
        return None
    aid = x.get("id") or x.get("ask") or x.get("ask_id")
    raw = str(x.get("decision") or x.get("action") or x.get("answer") or x.get("kind") or "").strip().lower()
    raw = raw.strip(":").split("::")[0]  # ":+1::skin-tone-2:" -> "+1"
    decision = next((k for k, words in DECISIONS.items() if raw in words), None)
    ts = x.get("ts") or x.get("reply_ts") or x.get("answer_ts") or x.get("slack_ts") or x.get("ask_ts")
    date = x.get("date") or x.get("answered_at") or x.get("when")
    date = str(date)[:10] if date and re.match(r"^\d{4}-\d{2}-\d{2}", str(date)) else None
    text = x.get("text") or x.get("reply_text") or x.get("reply") or x.get("note") or None
    if text and not isinstance(text, str):
        text = None
    if text:
        text = scrub(" ".join(text.split()))
        if PHONE.search(text) or EMAIL.search(text):
            text = "(text withheld: it looked like it held a phone number or email address)"
    return {"id": str(aid or "").strip().upper(), "decision": decision, "raw": raw, "ts": str(ts) if ts else None,
            "source": str(x.get("how") or x.get("source") or x.get("via") or ("reply" if text else "answer")).strip(),
            "date": date, "text": text, "days": x.get("days"), "lane": x.get("lane") or x.get("lanes")}


def answers_from(raw):
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for k in ("answers", "decisions", "settled"):
            if isinstance(raw.get(k), list):
                return raw[k]
        if raw.get("id"):
            return [raw]
    return []


def cmd_asks_apply_answers(args):
    date = iso(args.date)
    raw = load_json(args.file, None)
    if raw is None:
        die("cannot read %s" % args.file)
    items = answers_from(raw)
    data, rdata = asks_load(), rulings_load()
    lines, n = [], {"closed": 0, "withdrawn": 0, "parked": 0, "noted": 0, "rulings": 0, "skipped": 0}
    for x in items:
        f = answer_fields(x)
        if f is None or not f["id"]:
            lines.append("  skipped: an item with no ask id (%r)" % (str(x)[:80],))
            n["skipped"] += 1
            continue
        a = ask_find(data, f["id"])
        if a is None:
            lines.append("  %s skipped: not in asks.json" % f["id"])
            n["skipped"] += 1
            continue
        if f["decision"] is None:
            lines.append("  %s skipped: decision %r is not done, drop, park or note" % (a["id"], f["raw"]))
            n["skipped"] += 1
            continue
        said = f["date"] or date
        where = ("Slack %s %s" % (f["source"], f["ts"])) if f["ts"] else f["source"]
        prior = a.get("drew_answers") or []
        if any(p.get("decision") == f["decision"] and p.get("ts") == f["ts"] and (f["ts"] or p.get("text") == f["text"])
               for p in prior):
            lines.append("  %s skipped: this %s (%s) is already applied" % (a["id"], f["decision"], where))
            n["skipped"] += 1
            continue
        if f["decision"] in ("done", "drop", "park") and a["status"] not in ("open", "parked"):
            lines.append("  %s skipped: %s arrived but the ask is already %s" % (a["id"], f["decision"], a["status"]))
            n["skipped"] += 1
            continue
        if f["decision"] == "done":
            ask_close(a, date, "Drew, %s" % where)
            lines.append("  %s closed: Drew, %s" % (a["id"], where))
            n["closed"] += 1
        elif f["decision"] == "drop":
            ask_withdraw(a, date, "Drew said drop, %s" % said)
            lanes = [s for s in re.split(r"[,\s+]+", ",".join(f["lane"]) if isinstance(f["lane"], list)
                                         else str(f["lane"] or "")) if s.lower() in LANES]
            lanes = ["all"] if not lanes or "all" in lanes else sorted({s.lower() for s in lanes}, key=LANES.index)
            text = "Drew dropped %s (%s) on %s: do not raise it again." % (a["id"], a["label"], said)
            if f["text"]:
                text += ' His words: "%s"' % f["text"][:300]
            src = ("Drew in #ai-team, %s, %s, ts %s" % (said, f["source"], f["ts"])) if f["ts"] else \
                "Drew, %s, %s" % (said, f["source"])
            r, created = ruling_add(rdata, a["store"], lanes, text, src, said, [a["id"]])
            a.setdefault("ruling_ids", [])
            if r["id"] not in a["ruling_ids"]:
                a["ruling_ids"].append(r["id"])
            n["withdrawn"] += 1
            n["rulings"] += 1 if created else 0
            lines.append("  %s withdrawn (Drew said drop, %s), ruling %s %s" % (a["id"], said, r["id"],
                                                                              "added" if created else "already on file"))
        elif f["decision"] == "park":
            days = int(num(f["days"]) or PARK_DAYS)
            until = ask_park(a, date, days, "Drew said park, %s, %s" % (said, where))
            lines.append("  %s parked until %s (Drew, %s)" % (a["id"], until, where))
            n["parked"] += 1
        else:
            if not f["text"]:
                lines.append("  %s skipped: a note with no text" % a["id"])
                n["skipped"] += 1
                continue
            a["history"].append({"date": date, "action": "drew-note", "note": f["text"], "said": said,
                                 "source": where, "slack_ts": f["ts"]})
            lines.append("  %s noted (Drew, %s): %s" % (a["id"], where, f["text"][:120]))
            n["noted"] += 1
        a.setdefault("drew_answers", []).append({"date": said, "applied": date, "decision": f["decision"],
                                                 "source": f["source"], "ts": f["ts"], "text": f["text"]})
    changed = sum(v for k, v in n.items() if k != "skipped")
    if changed and not args.dry_run:
        save_json(LP("asks.json"), data)
        if n["rulings"]:
            save_json(LP("rulings.json"), rdata)
    for line in lines:
        print(line)
    print("asks apply-answers %s: %d answer(s) read, %d closed, %d withdrawn (%d new ruling(s)), %d parked, %d noted, "
          "%d skipped.%s" % (date, len(items), n["closed"], n["withdrawn"], n["rulings"], n["parked"], n["noted"],
                             n["skipped"], " Dry run: nothing written." if args.dry_run else
                             ("" if changed else " Nothing to write.")))


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
        elif a["status"] == "parked":
            extra = " Parked %s until %s: %s" % (a.get("parked_date"), a.get("park_until"), a.get("park_reason"))
        print("- %s [%s] %s, %s. Owner %s%s. Raised %s to %s (%d times).%s" % (
            a["id"], a["store"], a["label"], a["status"], a["owner"], ", needs the store" if a["needs_store"] else "",
            a["first_raised"], a["last_raised"], len(a["raised"]), extra))
    print("asks list: %d %s ask(s)" % (len(rows), st))


def _gm_tag(a, date):
    """(tag, due) for a needs_store ask."""
    if not a["needs_store"]:
        return "", False
    drafted = [r for r in a.get("requests", []) if r.get("date")]
    if drafted:
        return ", GM request drafted %s" % drafted[-1]["date"], False
    if business_days(a["first_raised"], date) >= GM_REQUEST_BUSINESS_DAYS:
        return ", GM request due", True
    return "", False


def aging_report(data, date, friday=None, rulings=None):
    """Every block and list the brief needs. Parked asks stay off until park_until; a Drew-owned ask raised
    STUCK_RAISES+ times since his last answer moves to the Friday digest (back early on a trip wire tonight);
    an ask a ruling settles is never listed, it gets a warning instead."""
    rulings = rulings_load()["rulings"] if rulings is None else rulings
    friday = dt.date.fromisoformat(date).weekday() == 4 if friday is None else friday
    warnings, settled = [], []
    live = []
    for a in data["asks"]:
        if not ask_live(a, date) or a["first_raised"] > date:
            continue
        rs = rulings_for_ask(a, rulings, date)
        if rs:
            settled.append(a)
            warnings.append("WARNING: %s (%s) is still %s but ruling %s settles it; not listed. Withdraw it: "
                            "`ledgers.py asks withdraw --id %s --date %s --reason \"Settled by ruling %s\"`."
                            % (a["id"], a["label"], a["status"], ", ".join(r["id"] for r in rs), a["id"], date, rs[0]["id"]))
            continue
        live.append(a)
    carried = sorted((a for a in live if a["first_raised"] < date), key=lambda a: (a["first_raised"], int(a["id"][1:])))
    stuck = [a for a in carried if is_stuck(a) and not trip_wire_on(a, date)]
    older = [a for a in carried if a not in stuck]
    closed = [a for a in data["asks"] if a["status"] in ("closed", "withdrawn") and a.get("closed_date") == date]
    parked_tonight = [a for a in data["asks"] if a["status"] == "parked" and a.get("parked_date") == date]
    parked_away = [a for a in data["asks"] if a["status"] == "parked" and (a.get("park_until") or "") > date]
    due = []
    L = ["### Asks aging", ""]
    if not older:
        L.append("- None carried over.")
    for a in older:
        days = days_open(a, date)
        tag, is_due = _gm_tag(a, date)
        if is_due:
            due.append(a)
        if a["status"] == "parked":
            tag += ", back from parking (parked %s to %s)" % (a.get("parked_date"), a.get("park_until"))
        trip = trip_wire_on(a, date)
        if trip and is_stuck(a):
            tag += ", stuck but back tonight: %s" % trip
        L.append("- %s, %s, open %d day%s, %s%s" % (a["id"], a["label"], days, "" if days == 1 else "s",
                                                    a["owner"], tag))
    L += ["", "### Closed tonight", ""]
    if not closed and not parked_tonight:
        L.append("- Nothing closed tonight.")
    for a in closed:
        if a["status"] == "closed":
            L.append("- %s, %s: closed. %s%s" % (a["id"], a["label"], a["closure_evidence"],
                                                 (" Win: " + a["win"]) if a.get("win") else ""))
        else:
            L.append("- %s, %s: withdrawn. %s" % (a["id"], a["label"], a["withdrawn_reason"]))
    for a in parked_tonight:
        L.append("- %s, %s: parked until %s. %s" % (a["id"], a["label"], a["park_until"], a.get("park_reason") or ""))
    L += ["", "### GM requests due", ""]
    if not due:
        L.append("- None due.")
    for a in due:
        L.append("- %s, %s: %d business days waiting on the store. Draft with `ledgers.py asks request --id %s --date %s`."
                 % (a["id"], a["label"], business_days(a["first_raised"], date), a["id"], date))
    if friday:
        L += ["", "### Stuck (Friday digest)", ""]
        if not stuck:
            L.append("- Nothing stuck this week.")
        for a in stuck:
            un = raises_unanswered(a)
            last = drew_answer_dates(a)
            tag, _ = _gm_tag(a, date)
            L.append("- %s, %s, open %d days, %s: raised %d times %s, stuck since %s%s. Done, drop or park?" % (
                a["id"], a["label"], days_open(a, date), a["owner"], len(un),
                "since Drew's answer on %s" % last[-1] if last else "with no answer from Drew",
                un[STUCK_RAISES - 1], tag))
    new = [a["id"] for a in data["asks"] if a["first_raised"] == date and a["status"] == "open" and a not in settled]
    return {"text": "\n".join(L) + "\n", "older": older, "closed": closed, "due": due, "new": new, "stuck": stuck,
            "parked": parked_away, "parked_tonight": parked_tonight, "settled": settled, "warnings": warnings,
            "friday": friday}


def aging_blocks(data, date):
    """(text, older, closed, due, new), as before; the full report is aging_report()."""
    r = aging_report(data, date)
    return r["text"], r["older"], r["closed"], r["due"], r["new"]


def cmd_asks_aging(args):
    date = iso(args.date)
    r = aging_report(asks_load(), date, friday=True if getattr(args, "friday", False) else None)
    if args.out:
        save_text(os.path.join(ROOT, args.out) if not os.path.isabs(args.out) else args.out, r["text"])
    print(r["text"])
    for w in r["warnings"]:
        print(w)
    print("asks aging %s: %d carried over, %d closed or withdrawn tonight, %d GM request(s) due, new tonight: %s; "
          "%d parked off the list%s, %d stuck %s%s"
          % (date, len(r["older"]), len(r["closed"]), len(r["due"]), ", ".join(r["new"]) or "none",
             len(r["parked"]), " (%d tonight)" % len(r["parked_tonight"]) if r["parked_tonight"] else "",
             len(r["stuck"]), ("in the Friday digest above" if r["friday"] else "held for the Friday digest")
             + (" (%s)" % ", ".join(a["id"] for a in r["stuck"]) if r["stuck"] else ""),
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


# ---------------------------------------------------------------- shift log clock (added 2026-09-28)
# On 2026-09-28 every shift-log time after 01:12 was an estimate that ran late (the shift really ran 01:00 to
# 01:17). Times in the log now come from the machine clock in Pacific time, never from memory.

_CLOCK = None  # the selftest sets a fixed clock here; the CLI always reads the real one


def pacific_from_utc(utc):
    """Pacific wall time for an aware UTC datetime, US rules since 2007 (fallback when zoneinfo is missing)."""
    y = utc.year
    mar = dt.datetime(y, 3, 8, 10, tzinfo=dt.timezone.utc)  # second Sunday of March, 2 AM PST
    start = mar + dt.timedelta(days=(6 - mar.weekday()) % 7)
    nov = dt.datetime(y, 11, 1, 9, tzinfo=dt.timezone.utc)  # first Sunday of November, 2 AM PDT
    end = nov + dt.timedelta(days=(6 - nov.weekday()) % 7)
    dst = start <= utc < end
    return utc.astimezone(dt.timezone(dt.timedelta(hours=-7 if dst else -8), "PDT" if dst else "PST"))


def pacific_now():
    """The real wall clock in Pacific time (PDT or PST by date)."""
    if _CLOCK is not None:
        return _CLOCK()
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("America/Los_Angeles"))
    except Exception:  # no tz database on this machine
        return pacific_from_utc(dt.datetime.now(dt.timezone.utc))


def clock_stamp(now=None):
    now = now or pacific_now()
    return "%s %s" % (now.strftime("%H:%M"), now.tzname() or "PT")


def shift_log_header(date, mode="shift"):
    day = dt.date.fromisoformat(date).strftime("%A")
    return ("---\ntype: shift-log\ndate: %s\nstatus: active\ntags: [ai-team, shift-log]\n---\n"
            "# Shift log %s (%s, %s)\n\n" % (date, date, mode, day))


def cmd_log(args):
    now = pacific_now()
    stamp = clock_stamp(now)
    if args.stamp_only:
        print(stamp)
        return
    if not args.date:
        die("log needs --date YYYY-MM-DD (the shift folder), except with --stamp-only")
    date = iso(args.date)
    text = text_arg(args, "text")
    if len([x for x in (text is not None, args.start, args.end) if x]) != 1:
        die("log needs exactly one of --text TEXT (or --text-file PATH), --start, --end; or --stamp-only")
    if text is not None:
        text = " ".join(text.split())
        if not text:
            die("--text is empty")
        m = re.match(r"^(end|start)\s*:", text, re.I)
        if m:
            die("write the %s line with `ledgers.py log --date %s --%s`: it becomes '- %s: HH:MM PDT' at the start "
                "of the line, which is what tipoff.sh watches for" % (m.group(1).lower(), date, m.group(1).lower(),
                                                                      m.group(1).capitalize()))
        line = "- %s %s" % (stamp, text)
    elif args.start:
        line = "- Start: %s (%s, mode %s)" % (stamp, dt.date.fromisoformat(date).strftime("%A"), args.mode)
    else:
        line = "- End: %s" % stamp
    path = P(date, "shift-log.md")
    created = not os.path.exists(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    prefix = shift_log_header(date, args.mode) if created else ""
    started = None
    if not created:
        with open(path, "rb") as f:
            f.seek(0, 2)
            if f.tell():
                f.seek(-1, 2)
                if f.read(1) != b"\n":
                    prefix = "\n"
        starts = re.findall(r"^- Start:\s*(\d{1,2}):(\d{2})", open(path, encoding="utf-8").read(), re.M)
        if starts:
            started = int(starts[-1][0]) * 60 + int(starts[-1][1])
    with open(path, "a", encoding="utf-8") as f:
        f.write(scrub(prefix + line + "\n"))
    extra = ""
    if args.end:
        extra = " tipoff.sh closes the session about two minutes after it sees this line; write nothing after it."
        if started is not None:
            mins = (now.hour * 60 + now.minute - started) % (24 * 60)
            extra = " Shift ran %02d:%02d to %s, %d minutes." % (started // 60, started % 60, stamp, mins) + extra
    print("log: %s line written to %s%s.%s" % (stamp, rel(path), " (created with the standard header)" if created else "",
                                                extra))
    if now.date().isoformat() != date:
        print("note: it is %s in Pacific time; the line went into the %s shift folder." % (now.date().isoformat(), date))


# ---------------------------------------------------------------- Settled findings (added 2026-09-28)

SETTLED_STATUSES = ("settled", "reopened", "retired")
SETTLED_STALE_DAYS = 3
SETTLED_ABOUT = ("Settled findings (Drew, 2026-09-28: no repeating the same finding night after night, but the spot "
                 "checks go on). Each item is a finding the team already reported and explained. The lanes listed "
                 "never report it as news and never open a huddle on it; they cite its id. The owner spot-checks it "
                 "every shift with the normal pulls and logs `ledgers.py settled check`: 'no' (the reopen condition is "
                 "met, or the finding stopped being true) reopens it and it goes to Magic as news. Magic adds items "
                 "with settled add and re-settles, edits or retires them with settled update. Drew's own answers "
                 "live in rulings.json, not here.")


def settled_load():
    data = load_json(LP("settled.json"), None) or {"settled": []}
    data["_about"] = SETTLED_ABOUT
    return data


def settled_get(data, sid):
    for it in data["settled"]:
        if it["id"].upper() == str(sid).strip().upper():
            return it
    die("no settled item %s in settled.json" % sid)


def clean_text(val, flag, shell_checked=True):
    """The text_arg checks for list-valued flags: em dashes scrubbed, PII and shell-eaten dollars refused."""
    val = scrub(" ".join(str(val or "").split()))
    if PHONE.search(val) or EMAIL.search(val):
        die("refused: %s looks like it holds a phone number or email address. Aggregates only (Law 4)." % flag)
    if shell_checked:
        for rx in DOLLAR_DAMAGE:
            m = rx.search(val)
            if m:
                die("refused: %s looks shell-mangled near %r. The shell eats $ amounts inside double quotes. "
                    "Write '6,853 dollars' or use a -file flag." % (flag, val[m.start():m.start() + 12]))
    return val


def keywords_arg(s):
    out, seen = [], set()
    for k in str(s or "").split(","):
        k = clean_text(k, "--keywords", shell_checked=False)
        if k and k.lower() not in seen:
            seen.add(k.lower())
            out.append(k)
    if not out:
        die("--keywords needs at least one word or phrase (comma list); scan matches an item on two of them")
    return out


def player_arg(s, flag="--by"):
    ls = lanes_arg(s)
    if len(ls) != 1 or ls[0] == "all":
        die("%s takes one player name (kobe, shaq, luka, worthy, nick or magic), got %r" % (flag, s))
    return ls[0]


def settled_owner(it):
    return it.get("owner") or (it["lane"][0] if it.get("lane") and it["lane"][0] != "all" else "magic")


def settled_line(it, date=None, sources=True):
    others = [x for x in it["lane"] if x != settled_owner(it)]
    who = "check: %s%s" % (settled_owner(it), (" (also " + ", ".join(others) + ")") if others else "")
    checked = it.get("last_checked") or "never"
    stale = ""
    if date and it["status"] == "settled":
        if not it.get("last_checked") or (dt.date.fromisoformat(date) - dt.date.fromisoformat(it["last_checked"])).days > SETTLED_STALE_DAYS:
            stale = ", NOT CHECKED since %s" % checked
    head = "%s %s, %s, settled %s, last checked %s%s" % (it["id"], it["store"], who, it["settled_on"], checked, stale)
    if it["status"] == "reopened":
        last = next((c for c in reversed(it.get("checks") or []) if c.get("still_true") is False), {})
        head = "%s. REOPENED %s by %s: %s. This is news: Magic verifies it and decides" % (
            head, it.get("reopened_on"), last.get("by") or "?", (last.get("note") or "").rstrip("."))
    elif it["status"] == "retired":
        head += ". RETIRED %s" % (it.get("retired_on") or "")
    fin = it["finding"].rstrip()
    return "%s. %s: %s%s Reopen if: %s.%s" % (
        head, it["subject"].rstrip(". "), fin, "" if fin.endswith(".") else ".", it["reopen_if"].rstrip(". "),
        (" Source: %s." % it["source"].rstrip(". ")) if sources else "")


def settled_add_item(data, store, lanes, subject, keywords, finding, source, reopen_if, date, first_seen=None,
                     owner=None, last_checked=None):
    """(item, created). Same store and subject as an item on file: that item, with new lanes and keywords merged."""
    for it in data["settled"]:
        if it["store"] == store and _norm(it["subject"]) == _norm(subject) and it["status"] != "retired":
            if "all" not in it["lane"]:
                it["lane"] = ["all"] if "all" in lanes else sorted(set(it["lane"]) | set(lanes), key=LANES.index)
            have = {k.lower() for k in it["keywords"]}
            it["keywords"] += [k for k in keywords if k.lower() not in have]
            return it, False
    owner = owner or (lanes[0] if lanes[0] != "all" else "magic")
    it = {"id": next_id(data["settled"], "S"), "store": store, "lane": lanes, "owner": owner, "subject": subject,
          "keywords": keywords, "first_seen": first_seen or date, "settled_on": date, "finding": finding,
          "source": source, "reopen_if": reopen_if, "last_checked": last_checked or date, "status": "settled",
          "checks": [], "history": [{"date": date, "action": "settled"}]}
    data["settled"].append(it)
    return it, True


def cmd_settled_add(args):
    date = iso(args.date) if args.date else dt.date.today().isoformat()
    store = store_arg(args.store, allow_all=True)
    lanes = lanes_arg(args.lane)
    owner = player_arg(args.owner, "--owner") if args.owner else None
    data = settled_load()
    it, created = settled_add_item(
        data, store, lanes, text_arg(args, "subject", required=True), keywords_arg(args.keywords),
        text_arg(args, "finding", required=True), text_arg(args, "source", required=True),
        text_arg(args, "reopen_if", required=True), date,
        first_seen=iso(args.first_seen, "--first-seen") if args.first_seen else None, owner=owner)
    save_json(LP("settled.json"), data)
    print("settled add: %s %s %s, lanes %s, owner %s. Players see it in `settled list --md` from tonight." % (
        "added" if created else "already on file as", it["id"], it["store"], ", ".join(it["lane"]), settled_owner(it)))
    for r, shared in ruling_hints(store, " ".join([it["subject"], it["finding"]]), rulings_load()["rulings"], date):
        print("NOTE: ruling %s may cover the same ground (shared words: %s). A ruling from Drew outranks a settled "
              "item; retire %s if the ruling already says it." % (r["id"], ", ".join(shared), it["id"]))


def cmd_settled_check(args):
    date = iso(args.date)
    data = settled_load()
    it = settled_get(data, args.id)
    if it["status"] == "retired":
        die("%s is retired (%s); there is nothing to check" % (it["id"], it.get("retired_on")))
    still = args.still_true == "yes"
    by = player_arg(args.by) if args.by else None
    note = text_arg(args, "note", required=True)
    it["checks"] = [c for c in it.get("checks") or [] if not (c.get("date") == date and c.get("by") == by)]
    it["checks"].append({"date": date, "still_true": still, "by": by, "note": note})
    it["last_checked"] = max(it.get("last_checked") or date, date)
    if not still and it["status"] == "settled":
        it["status"] = "reopened"
        it["reopened_on"] = date
        it["history"].append({"date": date, "action": "reopened", "by": by, "note": note})
    save_json(LP("settled.json"), data)
    if not still:
        print("FOR MAGIC: %s REOPENED on %s by %s (%s, %s): %s. Reopen condition on file: %s. What was settled: %s "
              "This goes in your findings tonight as news, with the file that shows the change. Magic verifies it, "
              "then briefs it or re-settles it with `ledgers.py settled update --id %s --date %s --status settled "
              "--finding-file PATH --note TEXT`." % (
                  it["id"], date, by or "a player", it["store"], it["subject"], note.rstrip("."),
                  it["reopen_if"].rstrip("."), it["finding"], it["id"], date))
    elif it["status"] == "reopened":
        print("settled check: %s still true on %s per %s, but it has been REOPENED since %s; only Magic re-settles it "
              "(`settled update --id %s --status settled`)." % (it["id"], date, by or "a player", it.get("reopened_on"),
                                                                 it["id"]))
    else:
        print("settled check: %s (%s, %s) still true on %s per %s. Nothing to report on it tonight: leave it out "
              "of your findings as news." % (it["id"], it["store"], it["subject"], date, by or "a player"))


def cmd_settled_update(args):
    date = iso(args.date)
    data = settled_load()
    it = settled_get(data, args.id)
    changed = []
    for f in ("subject", "finding", "source", "reopen_if"):
        v = text_arg(args, f)
        if v is not None and v != it.get(f):
            it[f] = v
            changed.append(f)
    if args.store:
        it["store"] = store_arg(args.store, allow_all=True)
        changed.append("store")
    if args.lane:
        it["lane"] = lanes_arg(args.lane)
        changed.append("lane")
    if args.owner:
        it["owner"] = player_arg(args.owner, "--owner")
        changed.append("owner")
    if args.keywords:
        it["keywords"] = keywords_arg(args.keywords)
        changed.append("keywords")
    if args.status and args.status != it["status"]:
        it["status"] = args.status
        changed.append("status")
        if args.status == "settled":
            it["settled_on"] = date
            it["last_checked"] = date
        elif args.status == "reopened":
            it["reopened_on"] = date
        else:
            it["retired_on"] = date
    note = text_arg(args, "note")
    it["history"].append({"date": date, "action": "updated", "changed": changed, "note": note})
    save_json(LP("settled.json"), data)
    print("settled update: %s %s, %s%s." % (it["id"], it["subject"], it["status"],
                                           ", changed " + ", ".join(changed) if changed else ", nothing changed"))


def settled_filter(rows, store=None, lane=None):
    if store and store != "ALL":
        rows = [r for r in rows if r["store"] in (store, "ALL")]
    if lane:
        rows = [r for r in rows if "all" in r["lane"] or lane in r["lane"] or lane == "magic"]
    return rows


def settled_md(rows, date, lane=None, store=None):
    you = lane if lane and lane != "magic" else "{you}"
    # the example id is one this player actually owns, so nobody copies a check onto someone else's item
    owned = [r["id"] for r in rows if lane and r.get("owner") == lane]
    example = owned[0] if owned else "Sx"
    head = ("**Settled findings** (%d, as of %s%s%s). Already reported and explained: never report one as news, "
            "never open a huddle on it, cite its id. Keep running your lane's normal pulls every shift; the settled list changes what you report, not what you check; "
            "for each item you own (\"check: %s\"), log one line tonight: `python3 .claude/skills/ai-team/scripts/"
            "ledgers.py settled check --date %s --id %s --still-true yes --note \"what you checked, with the file\" "
            "--by %s`. Answer no only when the reopen condition is met or the finding stopped being true; that "
            "reopens it and it goes to Magic as news. Sources for each item: `ledgers.py settled list`." % (
                len(rows), date, (", lane " + lane) if lane else "", (", store " + store) if store else "",
                you, date, example, you))
    lines = ["- " + settled_line(r, date, sources=False) for r in rows] or ["- None on file."]
    return "\n".join([head] + lines) + "\n"


def cmd_settled_list(args):
    date = iso(args.date) if args.date else dt.date.today().isoformat()
    rows = settled_load()["settled"]
    if not args.all:
        rows = [r for r in rows if r["status"] != "retired"]
    store = store_arg(args.store, allow_all=True) if args.store else None
    lane = player_arg(args.lane, "--lane") if args.lane else None
    rows = settled_filter(rows, store, lane)
    if args.md:
        print(settled_md(rows, date, lane, store), end="")
        return
    for r in rows:
        print("- " + settled_line(r, date))
    live = [r for r in rows if r["status"] == "settled"]
    tonight = [r for r in live if (r.get("last_checked") or "") >= date]
    reopened = [r for r in rows if r["status"] == "reopened"]
    unchecked = [r for r in live if r not in tonight]
    print("settled list %s: %d item(s), %d checked tonight, %d not checked tonight%s, %d reopened%s" % (
        date, len(rows), len(tonight), len(unchecked),
        " (" + ", ".join("%s owner %s" % (r["id"], settled_owner(r)) for r in unchecked) + ")" if unchecked else "",
        len(reopened), " (" + ", ".join("%s on %s" % (r["id"], r.get("reopened_on")) for r in reopened) + ")"
        if reopened else ""))


def settled_hits(text, it):
    """Keywords of a settled item found in one piece of text; empty unless at least two hit (one for a single keyword)."""
    t = " ".join(str(text).lower().split())
    kws = it.get("keywords") or []
    hit = [k for k in kws if k.lower() in t]
    return hit if kws and len(hit) >= min(2, len(kws)) else []


def cmd_settled_scan(args):
    date = iso(args.date) if args.date else dt.date.today().isoformat()
    try:
        lines = open(args.file, encoding="utf-8").read().splitlines()
    except OSError as e:
        die("cannot read %s: %s" % (args.file, e))
    items = settled_filter([r for r in settled_load()["settled"] if r["status"] == "settled"], None,
                           player_arg(args.lane, "--lane") if args.lane else None)
    found = 0
    for it in items:
        cite = re.compile(r"\b%s\b" % re.escape(it["id"]), re.I)
        hits = []
        for n, line in enumerate(lines, 1):
            if cite.search(line):
                continue
            kw = settled_hits(line, it)
            if kw:
                hits.append((n, kw, line.strip()))
        if hits:
            found += 1
            n, kw, line = hits[0]
            print("- %s (%s, %s): %d line(s) read like it without citing %s, first at line %d (%s): %s" % (
                it["id"], it["store"], it["subject"], len(hits), it["id"], n, ", ".join(kw), line[:160]))
    print("settled scan %s: %d settled item(s) may be repeated as news in %s. Cite the id with tonight's check "
          "result, or say what changed." % (date, found, rel(os.path.abspath(args.file))))


def settled_seed_rows():
    b = "outputs/ai-team/%s/"
    return [
        dict(store="NOI", lane="shaq,nick", owner="shaq", first_seen="2026-09-22", settled_on="2026-09-28",
             subject="NOI ad calls cannot be matched to VinSolutions leads",
             keywords="calls from ads, phone, VinSolutions, Value-Payment, call-in, forwarding number, Gas Models",
             finding="Google counts real calls from NOI's ads (Value-Payment 57 calls Sep 17 to 23, 56 Sep 18 to 24, "
                     "53 Sep 21 to 27; Gas Models 26 in the week to 9/21) and VinSolutions' Lead Source ROI report "
                     "has no phone or call-in bucket to check them against. It is a measurement gap, not a mismatch. "
                     "The one open question for the store: do ad calls get logged as leads.",
             source=b % "2026-09-28" + "brief.md (Shaq and Nick on phone calls, settled); " + b % "2026-09-28"
                    + "shaq.md line 82; " + b % "2026-09-25" + "nick.md line 20; " + b % "2026-09-24"
                    + "brief.md; " + b % "2026-09-22" + "nick.md line 92",
             reopen_if="VinSolutions adds a phone or lead-type split, a call log or call-tracking source arrives, "
                       "or Drew or the store answers whether ad calls are logged as leads"),
        dict(store="MCP", lane="shaq,nick", owner="nick", first_seen="2026-09-23", settled_on="2026-09-23",
             subject="MCP ad calls cannot be checked against leads (no CRM)",
             keywords="MCP, McPeek, calls, Tekion, CRM",
             finding="McPeek's search ads log real calls (57 in the 7 days to 9/22, 74 Sep 18 to 24) and MCP has no "
                     "CRM feed at all, because Tekion has never been scheduled (A10). Until it is, MCP's figures are "
                     "cost per call, not cost per lead. Closed as no data, not as a finding either way.",
             source=b % "2026-09-23" + "brief.md (Shaq and Nick on MCP, closed as no data); " + b % "2026-09-25"
                    + "brief.md; " + b % "2026-09-28" + "brief.md; ask A10",
             reopen_if="a Tekion report or any other MCP CRM data arrives (A10 closes)"),
        dict(store="NOI", lane="luka,kobe", owner="luka", first_seen="2026-09-22", settled_on="2026-09-25",
             subject="NOI boosted post landing page views far above GA4 sessions",
             keywords="boosted post, landing page view, LPV, Reels, in-app, NOI",
             finding="Meta's landing page views on NOI's boosted post run far above the GA4 sessions tied to it (211 "
                     "vs 53 in the week to 9/21, 89 vs 4 on 9/22, 88 vs 3 on 9/23), at under a second per visit. "
                     "Settled 9/25: Instagram Reels took $118.22 of $130.57 and 407 of 428 landing page views "
                     "(Sep 18 to 24), scroll-through traffic in the in-app browser, not a tracking break. Budget held "
                     "flat; moving it off Reels or to a harder goal waits on Drew at the next creative refresh.",
             source=b % "2026-09-23" + "brief.md; " + b % "2026-09-24" + "shift-log.md 01:09 ruling; "
                    + b % "2026-09-25" + "brief.md and data/meta_noi_placements.json; " + b % "2026-09-28"
                    + "luka.md line 96 (carryover, nothing new)",
             reopen_if="the post's placement, goal, budget or creative changes in the activity log, its GA4 engaged "
                       "sessions rise above a handful a day, or Drew asks for the DebugView test"),
        dict(store="NOI", lane="luka", owner="luka", first_seen="2026-09-22", settled_on="2026-09-23",
             subject="Three finished NOI boosted posts at zero spend",
             keywords="finished, boosted posts, A7, archive, dormant, zero spend, $0, 46",
             finding="The three NOI boosted posts at $0 spend are finished, not broken: their ad set flights ended "
                     "2026-06-01, 2026-06-20 and 2026-08-15. Status still reads ACTIVE, with no spend and no errors, "
                     "so no money is at risk. Archiving them is ask A7 (Drew, Meta edit access). Never report them as "
                     "dormant campaigns or dead budget.",
             source=b % "2026-09-23" + "shift-log.md 01:31 and data/meta_adsets.json; " + b % "2026-09-25"
                    + "shift-log.md Bounce 2 (re-reported as new); ask A7",
             reopen_if="any of the three spends money or its status or flight changes; retire this item when A7 closes"),
        dict(store="SBMW", lane="worthy,kobe,nick", owner="worthy", first_seen="2026-09-24", settled_on="2026-09-28",
             subject="Sterling new-inventory search page has organic visits and no leads",
             keywords="SRP, search page, search-results, LEAD_LEAK, new-inventory, new-car, SBMW, Sterling",
             finding="Sterling's new-inventory search page draws organic visits with zero key events (378 in the 28 "
                     "days to 9/23; 367 with 282 engaged to 9/27). Settled 9/28 as normal browsing: the lead form "
                     "most likely sits on the vehicle page or a modal, not the list (Kobe's read, not tested live). "
                     "No CRM tags leads by landing page, so it cannot be closed from CRM data.",
             source=b % "2026-09-28" + "brief.md (search pages with no leads, settled), worthy.md lines 27 and 54, "
                    "kobe.md line 50; opened " + b % "2026-09-24" + "worthy.md line 72, carried " + b % "2026-09-25"
                    + "worthy.md line 40",
             reopen_if="the search page gets a lead form or call to action, Sterling's vehicle-page leads drop, or "
                       "its organic sessions move 25% or more against the prior 28 days"),
        dict(store="NOI", lane="worthy,kobe,nick", owner="worthy", first_seen="2026-09-24", settled_on="2026-09-28",
             subject="NOI new-inventory search page has organic visits and no leads",
             keywords="SRP, search page, search-results, LEAD_LEAK, new-inventory, new-car, NOI",
             finding="NOI's new-inventory search page shows organic visits with zero key events (71 in the 28 days to "
                     "9/23, 77 to 9/27). Settled 9/28 as bounce, not a tracking gap: NOI's inventory pages run 3 to 11% "
                     "engagement.",
             source=b % "2026-09-28" + "brief.md (search pages with no leads, settled), kobe.md line 50; "
                    + b % "2026-09-24" + "worthy.md; " + b % "2026-09-25" + "worthy.md line 40",
             reopen_if="the page's engagement rises above 20% with still no key events, or its organic sessions move "
                       "25% or more against the prior 28 days"),
        dict(store="NCBMW", lane="kobe,worthy,nick", owner="kobe", first_seen="2026-09-22", settled_on="2026-09-28",
             subject="NCBMW website lead tracking collapsed since about 9/1",
             keywords="NCBMW, New Century, key-event rate, key events, collapsed, tracking break, since 9/1, Sep 1",
             finding="New Century's key-event rate collapsed around 9/1 (1.6% of visits in the week to 9/21, 1.8% Sep "
                     "21 to 27, against about 17% before). The events that do fire are clean form and call events, so "
                     "it reads as a real break on the site or in GTM. The health board tracks it every night (RED, days "
                     "broken) and ask A5 carries the fix (GM request drafted 9/25). It also explains NCBMW's inventory "
                     "pages with zero key events. A hands-on fix, not a nightly finding.",
             source="data/health.md in the 2026-09-24, 09-25 and 09-28 shift folders (RED, 24, 25 and 28 days "
                    "broken); " + b % "2026-09-23" + "kobe.md; " + b % "2026-09-28" + "brief.md (Kobe: a hands-on "
                    "fix, not another nightly flag); ask A5",
             reopen_if="the health board's NCBMW color or top issue changes, a test lead shows in DebugView, a GTM or "
                       "site change turns up, or A5 closes"),
        dict(store="ATLAS", lane="kobe,shaq,worthy", owner="kobe", first_seen="2026-09-22", settled_on="2026-09-23",
             subject="Atlas conversions are page loads, not leads",
             keywords="Atlas, generate_lead, /contact, About Us, branch_locator, page load",
             finding="Atlas has no real lead count on either side. GA4's generate_lead fires when /contact loads (209 "
                     "on 183 sessions in the week to 9/21, 135 on 122 visits Sep 21 to 27, 100% engagement), and "
                     "Google Ads counts About Us and branch-locator page views as its conversions. The health board "
                     "tracks it (RED) and ask A14 carries the fix. Every Atlas conversion number is unusable until a "
                     "tested lead action is primary; no nightly huddle on it.",
             source=b % "2026-09-22" + "brief.md (Kobe, Shaq and Magic on Atlas); " + b % "2026-09-23"
                    + "brief.md (both sides soft); " + b % "2026-09-28" + "data/health.md; ask A14",
             reopen_if="A14 closes, the Ads primary conversion or the GA4 key events change, or the health board's "
                       "Atlas color or top issue changes"),
        dict(store="NCBMW", lane="luka", owner="luka", first_seen="2026-09-24", settled_on="2026-09-25",
             subject="NCBMW static image ad barely delivers beside the video",
             keywords="static, ENGLISH, video, NCBMW, New Century, creative",
             finding="In New Century's Meta traffic campaign the static image ad ('ENGLISH') barely delivers beside its "
                     "video twin ('ENGLISH VIDEO'): 41 cents in the two weeks to 9/23, $0.32 of $55.98 Sep 18 to 24, "
                     "$1.55 of $55.62 Sep 21 to 27. The auction already routes spend to the video. Retire or refresh "
                     "it at the next creative refresh, on Drew's go.",
             source=b % "2026-09-24" + "luka.md line 81; " + b % "2026-09-25" + "luka.md line 85 (settled); "
                    + b % "2026-09-28" + "luka.md lines 48 and 96 (carryover, nothing new)",
             reopen_if="the static ad passes 10% of the campaign's 7-day spend, either ad's status changes, or a new "
                       "creative is added"),
        dict(store="NOI", lane="nick", owner="nick", first_seen="2026-09-22", settled_on="2026-09-28",
             subject="Nissan Third Party has sold nothing this month",
             keywords="Nissan Third Party, third party, zero sold, none sold, 0 sold",
             finding="Nissan Third Party (OEM-run third-party classifieds) is NOI's second-largest lead source and has "
                     "sold none all month: 78 leads through 9/21, 83 through 9/22, 87 through 9/23, 89 through 9/24, "
                     "96 through 9/27. It belongs on the month-end keep-or-cut list and in the monthly report, not in "
                     "the nightly brief.",
             source=b % "2026-09-22" + "nick.md line 37; " + b % "2026-09-28" + "nick.md line 37; briefs 2026-09-22 "
                    "to 2026-09-28, store by store",
             reopen_if="it records a sale, its leads swing 25% or more against the trailing average, or the month "
                       "closes (vendor month-end grades it)"),
        dict(store="SBMW", lane="nick", owner="nick", first_seen="2026-09-22", settled_on="2026-09-28",
             subject="Sterling Internet leads close far below the luxury benchmark",
             keywords="Internet, SBMW, Sterling, close, benchmark, 12%",
             finding="Sterling's Internet category closes around 4 to 5% (575 prospects at 4.3% through 9/21, 4.6% "
                     "through 9/22 and 9/24, 5.2% through 9/27) against a 12% luxury benchmark, while Showroom closes "
                     "on target. Momentum's report has no vendor split, so the weak source cannot be named until the "
                     "store sends a source report (A23). Standing context for the monthly report.",
             source="briefs " + b % "2026-09-22" + "brief.md, 2026-09-23, 2026-09-25 and 2026-09-28 (SBMW, store by "
                    "store); ask A23",
             reopen_if="the Internet close rate leaves the 3 to 7% range, or a Momentum report split by lead source "
                       "arrives (A23)"),
    ]


def cmd_settled_seed(args):
    path = LP("settled.json")
    if os.path.exists(path) and not args.force:
        die("settled.json already exists; use --force to add any seed item that is missing (items on file are kept)")
    data = settled_load()
    added = []
    for s in settled_seed_rows():
        it, created = settled_add_item(
            data, s["store"], lanes_arg(s["lane"]), s["subject"], keywords_arg(s["keywords"]), s["finding"],
            s["source"], s["reopen_if"], s["settled_on"], first_seen=s["first_seen"], owner=s["owner"],
            last_checked="2026-09-28")
        if created:
            it["history"] = [{"date": "2026-09-28", "action": "seeded from the 2026-09-22 to 2026-09-28 briefs and "
                                                            "shift logs (items that repeated on two or more nights)"}]
            added.append(it["id"])
    save_json(path, data)
    print("settled seed: %d item(s) added (%s), %d on file." % (len(added), ", ".join(added) or "none",
                                                                len(data["settled"])))


# ---------------------------------------------------------------- Coaching and promotion track (added 2026-09-28)

LEVELS = ("rookie", "starter", "senior", "captain")
TEAM_PLAYERS = ("kobe", "shaq", "luka", "worthy", "nick")
TEAM_START = "2026-09-19"
STARTER_STREAK = 5          # rookie to starter (not set by Drew; Magic can also set a level with coach level)
SENIOR_STREAK = 10
SENIOR_THOUGHT_AHEAD = 3
CAPTAIN_STREAK = 20
CAPTAIN_PEER_CATCHES = 2    # "peer reviews that caught real issues": two, counted as senior
COACH_ABOUT = ("Coaching and promotion track (Drew, 2026-09-28: Magic is middle management and coaches the players, "
               "who work like diligent analysts and earn promotions). One history entry per player per shift, written "
               "by Magic with ledgers.py coach add: bounces (cause, factual true or false), self_caught (mistakes the "
               "player caught before Magic did), thought_ahead (forward-looking items Magic confirmed), peer_catches "
               "(real problems the player caught in someone else's work), coach_note. A factual bounce (a wrong "
               "number, an unsourced claim, a wrong actor, a wrong window) resets the clean streak; a wording bounce "
               "does not. guessed marks backfilled entries where the factual or wording call was a judgment.")
COACH_RULES = {
    "rookie": "A new player. Magic re-verifies everything. Starter after %d consecutive clean shifts, or when Magic "
              "sets it with coach level." % STARTER_STREAK,
    "starter": "Magic re-verifies every number that reaches the brief. Senior after %d consecutive clean shifts and "
               "%d thought-ahead items Magic confirmed, both counted at this level." % (SENIOR_STREAK, SENIOR_THOUGHT_AHEAD),
    "senior": "Magic spot-checks three numbers, the player leads huddles in the lane and peer-reviews one other lane. "
              "Captain after %d consecutive clean shifts as senior and %d peer-review catches of real problems as "
              "senior." % (CAPTAIN_STREAK, CAPTAIN_PEER_CATCHES),
    "captain": "Clears a peer's file for Magic: middle management in training. Top of the ladder.",
}


def coach_load():
    data = load_json(LP("coaching.json"), None) or {"players": {}}
    data["_about"] = COACH_ABOUT
    data["rules"] = COACH_RULES
    return data


def coach_name(s):
    name = str(s or "").strip().lower()
    if not re.match(r"^[a-z][a-z0-9_-]{1,23}$", name) or name == "all":
        die("--player must be a player name like kobe, got %r" % s)
    return name


def coach_player(data, name, date=None, create=True):
    p = data["players"].get(name)
    if p is None:
        if not create:
            die("no coaching record for %s" % name)
        lvl, since = ("starter", TEAM_START) if name in TEAM_PLAYERS else ("rookie", date or dt.date.today().isoformat())
        # streak_from: the first shift date that counts at this level (a joining shift counts; a promotion shift
        # counted toward the level it earned, so the new level starts counting the next day)
        p = {"level": lvl, "level_since": since, "streak_from": since,
             "level_history": [{"date": since, "level": lvl, "reason": "on the team since %s" % since
                                if lvl == "starter" else "new player"}], "history": []}
        data["players"][name] = p
    return p


def _factual(h):
    return [b for b in h.get("bounces") or [] if b.get("factual")]


def _day_after(date):
    return (dt.date.fromisoformat(date) + dt.timedelta(days=1)).isoformat()


def coach_stats(p, upto=None):
    hist = sorted(p.get("history") or [], key=lambda h: h["date"])
    if upto:
        hist = [h for h in hist if h["date"] <= upto]
    streak = 0
    for h in reversed(hist):
        if _factual(h):
            break
        streak += 1
    since = p.get("level_since") or ""
    count_from = p.get("streak_from") or (_day_after(since) if since else "")
    at_level = [h for h in hist if h["date"] >= count_from]
    streak_lvl = min(streak, len(at_level))
    last10 = hist[-10:]
    s = {"shifts": len(hist), "streak": streak, "streak_at_level": streak_lvl, "level": p["level"],
         "level_since": since,
         "factual_last10": sum(len(_factual(h)) for h in last10),
         "wording_last10": sum(1 for h in last10 for b in h.get("bounces") or [] if not b.get("factual")),
         "self_caught_last10": sum(int(h.get("self_caught") or 0) for h in last10),
         "self_caught_total": sum(int(h.get("self_caught") or 0) for h in hist),
         "thought_ahead_total": sum(len(h.get("thought_ahead") or []) for h in hist),
         "thought_ahead_at_level": sum(len(h.get("thought_ahead") or []) for h in at_level),
         "peer_total": sum(len(h.get("peer_catches") or []) for h in hist),
         "peer_at_level": sum(len(h.get("peer_catches") or []) for h in at_level),
         "last_date": hist[-1]["date"] if hist else None}
    lvl, missing = p["level"], []
    if lvl == "rookie":
        nxt = "starter"
        if streak_lvl < STARTER_STREAK:
            missing.append("%d more clean shift%s in a row (%d of %d)" % (
                STARTER_STREAK - streak_lvl, "" if STARTER_STREAK - streak_lvl == 1 else "s", streak_lvl, STARTER_STREAK))
    elif lvl == "starter":
        nxt = "senior"
        if streak_lvl < SENIOR_STREAK:
            missing.append("%d more clean shift%s in a row (%d of %d)" % (
                SENIOR_STREAK - streak_lvl, "" if SENIOR_STREAK - streak_lvl == 1 else "s", streak_lvl, SENIOR_STREAK))
        if s["thought_ahead_at_level"] < SENIOR_THOUGHT_AHEAD:
            k = SENIOR_THOUGHT_AHEAD - s["thought_ahead_at_level"]
            missing.append("%d more confirmed thought-ahead item%s (%d of %d)" % (
                k, "" if k == 1 else "s", s["thought_ahead_at_level"], SENIOR_THOUGHT_AHEAD))
    elif lvl == "senior":
        nxt = "captain"
        if streak_lvl < CAPTAIN_STREAK:
            missing.append("%d more clean shift%s in a row as senior (%d of %d)" % (
                CAPTAIN_STREAK - streak_lvl, "" if CAPTAIN_STREAK - streak_lvl == 1 else "s", streak_lvl, CAPTAIN_STREAK))
        if s["peer_at_level"] < CAPTAIN_PEER_CATCHES:
            k = CAPTAIN_PEER_CATCHES - s["peer_at_level"]
            missing.append("%d more peer-review catch%s of a real problem (%d of %d)" % (
                k, "" if k == 1 else "es", s["peer_at_level"], CAPTAIN_PEER_CATCHES))
    else:
        nxt = None
    s["next_level"], s["missing"] = nxt, missing
    s["eligible"] = bool(nxt) and not missing
    return s


def coach_next_text(s):
    if not s["next_level"]:
        return "top level"
    if s["eligible"]:
        return "%s: eligible now" % s["next_level"]
    return "%s: needs %s" % (s["next_level"], " and ".join(s["missing"]))


def coach_promote(p, date, reason):
    p["level"] = LEVELS[LEVELS.index(p["level"]) + 1]
    p["level_since"], p["streak_from"] = date, _day_after(date)
    p.setdefault("level_history", []).append({"date": date, "level": p["level"], "reason": reason})


def coach_entry_line(h):
    f = _factual(h)
    w = [b for b in h.get("bounces") or [] if not b.get("factual")]
    parts = []
    if not f and not w:
        parts.append("clean")
    def causes(bs):
        if len(bs) == 1:
            return bs[0]["cause"].rstrip(".")
        return " ".join("(%d) %s." % (i, b["cause"].rstrip(".")) for i, b in enumerate(bs, 1)).rstrip(".")

    if f:
        parts.append("%d factual bounce%s: %s" % (len(f), "" if len(f) == 1 else "s", causes(f)))
    if w:
        parts.append("%d wording bounce%s: %s" % (len(w), "" if len(w) == 1 else "s", causes(w)))
    if h.get("self_caught"):
        parts.append("self-caught %d" % h["self_caught"])
    if h.get("thought_ahead"):
        parts.append("thought ahead: " + "; ".join(h["thought_ahead"]))
    if h.get("peer_catches"):
        parts.append("peer catch: " + "; ".join(h["peer_catches"]))
    note = (h.get("coach_note") or "").rstrip()
    return "%s: %s.%s" % (h["date"], ". ".join(x.rstrip(".") for x in parts),
                          (" Magic: " + note + ("" if note.endswith(".") else ".")) if note else "")


def coach_add_entry(data, name, date, bounces, self_caught, thought_ahead, peer, note, guessed=None, source=None):
    """Write one shift's entry (replacing any entry for the same date); returns (entry, replaced, promotions)."""
    p = coach_player(data, name, date)
    h = {"date": date, "bounces": bounces, "self_caught": int(self_caught or 0), "thought_ahead": thought_ahead,
         "peer_catches": peer, "coach_note": note}
    if source:
        h["source"] = source
    if guessed:
        h["guessed"] = guessed
    old = [x for x in p["history"] if x["date"] == date]
    p["history"] = sorted([x for x in p["history"] if x["date"] != date] + [h], key=lambda x: x["date"])
    promos = []
    s = coach_stats(p)
    while s["eligible"]:
        reason = "%d clean shifts in a row at %s" % (s["streak_at_level"], p["level"])
        if p["level"] == "starter":
            reason += ", %d confirmed thought-ahead items" % s["thought_ahead_at_level"]
        if p["level"] == "senior":
            reason += ", %d peer-review catches" % s["peer_at_level"]
        coach_promote(p, date, reason)
        promos.append((p["level"], reason))
        s = coach_stats(p)
    return h, bool(old), promos


def cmd_coach_add(args):
    date = iso(args.date)
    name = coach_name(args.player)
    causes, facts = args.bounce or [], args.factual or []
    if len(causes) != len(facts):
        die("give one --factual yes|no for each --bounce (got %d bounce(s), %d factual flag(s))" % (len(causes), len(facts)))
    bounces = [{"cause": clean_text(c, "--bounce"), "factual": f == "yes"} for c, f in zip(causes, facts)]
    if any(not b["cause"] for b in bounces):
        die("--bounce needs the cause in a few words")
    if (args.self_caught or 0) < 0:
        die("--self-caught must be 0 or more")
    ta = [clean_text(x, "--thought-ahead") for x in args.thought_ahead or [] if str(x).strip()]
    peer = [clean_text(x, "--peer-catch") for x in args.peer_catch or [] if str(x).strip()]
    data = coach_load()
    new = name not in data["players"]
    h, replaced, promos = coach_add_entry(data, name, date, bounces, args.self_caught, ta, peer,
                                          text_arg(args, "note", required=True))
    save_json(LP("coaching.json"), data)
    p = data["players"][name]
    s = coach_stats(p)
    print("coach add: %s %s %s (%d bounce(s), %d factual; self-caught %d; %d thought-ahead). Level %s, clean streak "
          "%d shift(s); next %s.%s" % (
              "replaced" if replaced else "recorded", name, date, len(bounces), len(_factual(h)), h["self_caught"],
              len(ta), p["level"], s["streak"], coach_next_text(s),
              " New player: starts as %s." % LEVELS[0] if new and name not in TEAM_PLAYERS else ""))
    for lvl, reason in promos:
        print("PROMOTION: %s is now %s as of %s (%s). Put one line in the brief so Drew sees who earned it." % (
            name, lvl, date, reason))


def cmd_coach_level(args):
    date = iso(args.date)
    name = coach_name(args.player)
    data = coach_load()
    p = coach_player(data, name, date)
    reason = text_arg(args, "reason", required=True)
    old = p["level"]
    p["level"], p["level_since"], p["streak_from"] = args.level, date, _day_after(date)
    p.setdefault("level_history", []).append({"date": date, "level": args.level, "reason": reason, "set_by_hand": True})
    save_json(LP("coaching.json"), data)
    print("coach level: %s %s to %s as of %s (%s)." % (name, old, args.level, date, reason))


def cmd_coach_list(args):
    name = coach_name(args.player)
    data = coach_load()
    p = data["players"].get(name)
    if p is None:
        lvl = "starter" if name in TEAM_PLAYERS else "rookie"
        print("**Coaching notes for %s** (%s): none on file yet." % (name.capitalize(), lvl) if args.md else
              "coach list: no coaching notes for %s yet (%s)." % (name, lvl))
        return
    s = coach_stats(p, iso(args.date) if args.date else None)
    hist = sorted(p["history"], key=lambda h: h["date"])
    if args.date:
        hist = [h for h in hist if h["date"] <= iso(args.date)]
    recent = list(reversed(hist[-max(1, args.last):]))
    if args.md:
        print("**Coaching notes for %s** (%s since %s; clean streak %d shift%s; next %s). Read these before you start "
              "tonight and fix the habit behind every bounce; a factual bounce (wrong number, unsourced claim, wrong "
              "actor, wrong window) resets your streak." % (
                  name.capitalize(), p["level"], p.get("level_since"), s["streak"], "" if s["streak"] == 1 else "s",
                  coach_next_text(s)))
        for h in recent:
            print("- " + coach_entry_line(h))
        if not recent:
            print("- None on file yet.")
        return
    for h in recent:
        print("- " + coach_entry_line(h))
    print("coach list: %s, %s since %s, clean streak %d, %d shift(s) on file; next %s." % (
        name, p["level"], p.get("level_since"), s["streak"], s["shifts"], coach_next_text(s)))


def cmd_coach_scorecard(args):
    data = coach_load()
    upto = iso(args.date) if args.date else None
    names = list(TEAM_PLAYERS) + sorted(n for n in data["players"] if n not in TEAM_PLAYERS)
    rows = []
    for n in names:
        p = data["players"].get(n) or {"level": "starter" if n in TEAM_PLAYERS else "rookie",
                                       "level_since": TEAM_START, "streak_from": TEAM_START, "history": []}
        rows.append((n, p, coach_stats(p, upto)))
    asof = upto or max([s["last_date"] for _, _, s in rows if s["last_date"]] or [dt.date.today().isoformat()])
    if args.md:
        print("**Team scorecard** (as of %s; bounces and self-catches over each player's last 10 shifts)" % asof)
        print("")
        print("| Player | Level | Clean streak | Factual bounces (last 10) | Wording bounces (last 10) | Self-catches "
              "(last 10) | Thought-ahead (this level) | Peer catches | Next level: what is missing |")
        print("|---|---|---|---|---|---|---|---|---|")
        for n, p, s in rows:
            print("| %s | %s | %d | %d | %d | %d | %d | %d | %s |" % (
                n.capitalize(), p["level"], s["streak"], s["factual_last10"], s["wording_last10"],
                s["self_caught_last10"], s["thought_ahead_at_level"], s["peer_total"], coach_next_text(s)))
        print("")
        print("A factual bounce (a wrong number, an unsourced claim, a wrong actor, a wrong window) resets the streak; a "
              "wording bounce does not. Senior: %d clean shifts in a row and %d confirmed thought-ahead items. Captain: "
              "%d clean shifts in a row as senior and %d peer-review catches. Source: outputs/ai-team/ledgers/"
              "coaching.json." % (SENIOR_STREAK, SENIOR_THOUGHT_AHEAD, CAPTAIN_STREAK, CAPTAIN_PEER_CATCHES))
        return
    for n, p, s in rows:
        print("- %s: %s since %s, clean streak %d, last 10 shifts %d factual and %d wording bounce(s), self-caught %d, "
              "thought-ahead %d at this level, peer catches %d, %d shift(s) on file. Next %s." % (
                  n, p["level"], p.get("level_since"), s["streak"], s["factual_last10"], s["wording_last10"],
                  s["self_caught_last10"], s["thought_ahead_at_level"], s["peer_total"], s["shifts"], coach_next_text(s)))
    print("coach scorecard: %d player(s) as of %s." % (len(rows), asof))


def coach_seed_rows():
    """Backfill 2026-09-22 to 2026-09-28 from the shift logs' bounce lines. (date, player, bounces, self_caught,
    thought_ahead, peer_catches, note, source, guessed)"""
    L = "outputs/ai-team/%s/shift-log.md"
    F, W = True, False
    return [
        ("2026-09-22", "kobe", [], 1, [], [],
         "Clean file, every flag checked against the pull. You called Atlas tracking clean on the first pass while "
         "/contact logged 209 leads on 183 sessions at 100% engagement; compare key events to sessions page by page "
         "before you call any store clean.",
         L % "2026-09-22" + " 01:11; 2026-09-22/kobe.md line 92",
         "self-catch counted from kobe.md line 92 ('got wrong on my first pass'); it surfaced in the Atlas huddle Magic opened"),
        ("2026-09-22", "shaq",
         [("Wrong window: $1,240 was Thu to Sun 9/17 to 9/20, not Fri to Sun ($1,007.67); called Gas Models zero real "
           "calls when conversions_by_action_7d showed 26 calls from ads and 9 clicks to call outside primary", F)],
         0, [], [],
         "Read the all-conversions column before you call a campaign dead, and put the exact date window on every "
         "dollar figure.",
         L % "2026-09-22" + " 01:08 BOUNCE 1; 2026-09-22/bounce-shaq-1.txt", None),
        ("2026-09-22", "luka", [], 0,
         ["Spotted two Meta campaigns in NCBMW's GA4 that are not in the DigitalCLIQ account (became A13)"], [],
         "Passed first time, landing page views checked against GA4. Good instinct following the NCBMW traffic that "
         "was not ours.",
         L % "2026-09-22" + " 01:10",
         "thought-ahead credit is a judgment from the 01:10 log line (follow-up became ask A13)"),
        ("2026-09-22", "worthy",
         [("Called the i3 BMW's third Neue Klasse (second, per the release cited), bmwblog date conflict, AI-referral "
           "ranking backwards (NOI is lowest at 47), MCP AI referrals called thin, SBMW top-3 misread (78 to 82)", F)],
         0, [], [],
         "The Semrush math was right; the misses were in reading your own sources. Reread the headline of any release "
         "you cite and sort a ranking before you describe it.",
         L % "2026-09-22" + " 01:09 BOUNCE 2; 2026-09-22/bounce-worthy-1.txt", None),
        ("2026-09-22", "nick",
         [("NOI cost still carried $4,891 Drew said to ignore (live $8,687); SBMW category rows (902, 89) did not foot "
           "to the totals (906, 88); two Shaq huddles left open", F)],
         0, [], [],
         "Apply Drew's rulings before you total anything, and foot every table to the report's own totals before you "
         "send it.",
         L % "2026-09-22" + " BOUNCE 3; 2026-09-22/bounce-nick-1.txt", None),
        ("2026-09-23", "kobe",
         [("Wrong campaign ID in the Luka huddle (the branding campaign cited as the boosted post's twin); SBMW "
           "reconciliation close missing from Report to Magic; Luka huddle not logged in kobe.md", F)],
         0, [], [],
         "The SBMW service-page-view find was the catch of the night. Copy IDs from the file, never from memory, and "
         "log every huddle in your file the moment it closes.",
         L % "2026-09-23" + " 01:17", None),
        ("2026-09-23", "shaq",
         [("PMax pacing denominator suspect; '$0 row (no row at all)' contradicted itself; conversions read about 52 "
           "and 50.997; the 9/22 PMax budget change was Drew applying a recommendation, not the auto-apply "
           "subscription", F)],
         1, ["Flagged that campaignBudget_amount is a current value backfilled over history, so pacing built on it is "
             "unsafe (became A18, fixed 9/24)"], [],
         "Good catch on the budget column, and you withdrew the stat yourself. Name the actor on every change from "
         "change_events (Drew, Drew applying a recommendation, or auto-apply) and use one conversion figure per "
         "campaign.",
         L % "2026-09-23" + " 01:17 and 01:20, Worth fixing 3; 2026-09-23/brief.md",
         "self-catch = the withdrawn pacing stat (Worth fixing 3)"),
        ("2026-09-23", "luka",
         [("Recommendation 1 still framed the three zero-spend campaigns as park-or-fix after the headline was "
           "corrected", W)],
         1, [], [],
         "You fixed it before the bounce landed, which is the habit we want. When a headline changes, reread every "
         "section that depends on it before you report ready.",
         L % "2026-09-23" + " 01:16",
         "classed wording: the headline facts were right and the stale line was already fixed when the bounce landed"),
        ("2026-09-23", "worthy",
         [("Unsourced 'this week' on Semrush previous_position; AI Overview count not scoped to unique top-40 "
           "keywords", W)],
         0, [], [],
         "Every keyword figure checked out row by row. Claim only the time frame the source states.",
         L % "2026-09-23" + " 01:18",
         "the log clears worthy.md 'with one wording fix'; counted as the night's fifth bounce and classed wording"),
        ("2026-09-23", "nick",
         [("DealerWebsite line gave two different figures; Report to Magic asked for the eventName breakdown already "
           "received; huddle status left as [PENDING]; headline buried the resolved reconciliation", F)],
         0, [], [],
         "The SBMW reconciliation with Kobe was real work. One figure per line, update Report to Magic before you say "
         "ready, and reach teammates with SendMessage only (the Agent tool spawns strangers).",
         L % "2026-09-23" + " 01:18; .claude/agents/nick.md (Agent tool, 2026-09-23)", None),
        ("2026-09-24", "kobe", [], 0,
         ["Escalated the Ads-to-GA4 click gap at MCP and NOI (MCP (not set) google/cpc 30 sessions in 7 days, NOI PMax "
          "45 clicks vs 11 sessions), which became A19"], [],
         "Clean file and a real escalation with the next step attached. Keep bringing the fix with the problem.",
         L % "2026-09-24" + " 01:06 and 01:10", None),
        ("2026-09-24", "shaq",
         [("NOI Value-Payment lost impression share to budget on 5 of 7 days, not 0% on 4 of 5; New CDJR lost 42, 65 "
           "and 90%, not '90% most days'; 'no web-lead action exists' went further than the tab shows", F)],
         0, [], [],
         "Quote the actual spread instead of 'most days', and say only what the tab can show (actions with activity, "
         "not the full action list).",
         L % "2026-09-24" + " 01:07 Bounce 2; 2026-09-24/bounce-shaq.txt", None),
        ("2026-09-24", "luka", [], 0, [], [],
         "Your numbers matched my re-pull. You saved a pointer file instead of the raw pull, so the ledger read Meta 0 "
         "of 5 tonight: save every raw pull to data/meta_*.json.",
         L % "2026-09-24" + " 01:08 and Summary", None),
        ("2026-09-24", "worthy",
         [("T3 Wagoneer S draft: the 2026 skip called confirmed against your own 2026 EPA data; 'native, no adapter' "
           "wrong for existing cars; unsourced comparatives; a report stated as fact; an em dash", F),
          ("worthy.md: SBMW LEAD_LEAK is the new-car SRP (378/0), not the used SRP; NOI ranked keywords 26 to 28, not "
           "28 to 30", F)],
         0, [], [],
         "Two bounces in one night. Before you report ready, recheck every page name and every before-and-after pair "
         "against the file, and write reported news as reported. The wrong Atlas domain cost about 100 Semrush units: "
         "read the store README first.",
         L % "2026-09-24" + " 01:07 Bounce 1 and 01:08 Bounce 3; 2026-09-24/bounce-worthy-t3.txt", None),
        ("2026-09-24", "nick", [], 0,
         ["Found BMW NA's regional emails as a partial New Century source while FOCUS is missing (69 leads, 5 sold "
          "through 9/22)"], [],
         "Clean file, vendor deltas verified. Check that a file is missing before you say it is (ga4_NOI.json was "
         "there).",
         L % "2026-09-24" + " 01:12; 2026-09-24/brief.md NCBMW",
         "thought-ahead credit is a judgment: the BMW NA find became the NCBMW stand-in source"),
        ("2026-09-25", "kobe", [], 0, [], [],
         "Your 9/24 numbers held against my wrong lag call; credit to you. But 'Sterling 40% under a normal Thursday' "
         "was the newest day and filled in to 1,328 by 9/28: call the newest day preliminary and flag the last "
         "complete day.",
         L % "2026-09-25" + " 01:13 CORRECTION; 2026-09-28/brief.md correction", None),
        ("2026-09-25", "shaq",
         [("Tagged Drew directly; wrong Calls-from-ads definition; called the 9/24 MCP 14-ad flag a discrepancy when "
           "it is on disk (2026-09-24/data/ad_text_MCP.md)", F),
          ("MCP PMax 'zero conversions 9/24' was backfill lag (9/23 went 0 to 5, 9/22 9 to 14 between exports)", F)],
         0, [], [],
         "The newest day is never final in Ads either: compare it with last night's export before you call a zero. "
         "Only Magic tags Drew.",
         L % "2026-09-25" + " Bounce 1 and Bounce 4", None),
        ("2026-09-25", "luka",
         [("Reported NOI's three finished boosted posts (A7, corrected 9/23) as a new dormant-campaign finding", F)],
         0, [], [],
         "The Reels placement split settled a four-night argument; great work. Check the asks and the settled list "
         "before calling anything new: A7 was already on file.",
         L % "2026-09-25" + " Bounce 2",
         "classed factual: it restated a corrected claim as a new finding"),
        ("2026-09-25", "worthy", [], 1,
         ["Said an Atlas organic drop with rising rankings needs a site audit if it repeats; it repeated Thursday to "
          "Saturday (confirmed 9/28)"], [],
         "Clean night, every gate condition applied, and a good call on source age for the LEAF piece.",
         L % "2026-09-25" + " Gate line; 2026-09-25/brief.md (Worthy, Atlas)",
         "self-catch = caught that the LEAF redesign sources were 13 to 15 months old and wrote T4 as an explainer"),
        ("2026-09-25", "nick",
         [("Set 56 calls over 7 days against 16 leads from one day (535 was month to date through 9/23)", F)],
         0, [], [],
         "Match the windows before you compare: 7 days against 7 days, month to date against month to date.",
         L % "2026-09-25" + " Bounce 3", None),
        ("2026-09-28", "kobe", [], 1, [], [],
         "Cleared first time, and you caught your own weekday labels on channel_flags before I did. Your call to treat "
         "NCBMW as a hands-on fix is now settled item S7.",
         L % "2026-09-28" + " 01:44; 2026-09-28/kobe.md lines 56 and 69", None),
        ("2026-09-28", "shaq",
         [("NOI-PMAX paused by Drew from the phone app 9/25 05:24, not by itself (wrong actor); 9/25 called Saturday; "
           "'settled' used for asks still open; missed the MCP PMax delivery collapse 9/25 to 27", F)],
         0, [], [],
         "Good catch on the 5:07pm Friday auto-apply change. Every change needs its actor from change_events, and the "
         "biggest move in the account leads the file. Five nights running with a factual bounce: slow down on the "
         "last read before you say ready.",
         L % "2026-09-28" + " 01:24; 2026-09-28/post-bounce-shaq.txt", None),
        ("2026-09-28", "luka",
         [("Wording (first bounce; detail not saved in the shift folder)", W),
          ("Wording (second bounce; detail not saved in the shift folder)", W)],
         0, ["Said the three carryovers (boosted post placement, NCBMW static ad, A7) had held three shifts with nothing "
             "new to learn and need Drew's go, not another night of checks (now settled S3, S4, S9)"], [],
         "Your numbers were right both times; the bounces were wording. Your carryover call is why the settled list "
         "exists.",
         L % "2026-09-28" + " 01:28; 2026-09-28/luka.md line 96",
         "both causes classed wording per the log ('second wording bounce'); thought-ahead credit is a judgment"),
        ("2026-09-28", "worthy",
         [("Unsourced 'near-zero competition' on Rogue keywords; Atlas key events used to rule out a tracking break "
           "although /contact counts page loads; cut pulls called pending", F),
          ("Sent the Atlas site-audit proposal to Magic without posting it in #ai-team first", W)],
         0, [], ["Showed 9/24 had filled in (Sterling organic 234 vs 96, New Century 89 vs 30), which overturned "
                 "Magic's Friday ruling"],
         "You were right about Thursday and I was wrong; that is the kind of check that gets you promoted. Still, no "
         "claim without a pull behind it: worthy.md line 44 kept three absence claims with no saved query.",
         L % "2026-09-28" + " 01:36 and 01:47; 2026-09-28/post-worthy-bounce.txt, post-worthy-audit.txt",
         "the log lists three causes and the summary two bounces; the second is my reading of post-worthy-audit.txt "
         "(process, wording); the peer catch is a judgment"),
        ("2026-09-28", "nick", [], 0, [], [],
         "Cleared first time: the vendor totals footed (4,650 plus 3,627 = 8,277) and SBMW read clean. Ruling R3 now "
         "says stop raising the Auto Credit Express and TrueCar costs.",
         L % "2026-09-28" + " 01:39", None),
    ]


def cmd_coach_seed(args):
    path = LP("coaching.json")
    if os.path.exists(path) and not args.force:
        die("coaching.json already exists; use --force to rewrite the 2026-09-22 to 2026-09-28 backfill entries "
            "(later entries are kept)")
    data = coach_load()
    n = 0
    for date, name, bounces, sc, ta, peer, note, source, guessed in coach_seed_rows():
        coach_add_entry(data, name, date, [{"cause": c, "factual": f} for c, f in bounces], sc, ta, peer, note,
                        guessed=guessed, source=source)
        n += 1
    save_json(path, data)
    parts = []
    for name in TEAM_PLAYERS:
        s = coach_stats(data["players"][name])
        parts.append("%s streak %d" % (name, s["streak"]))
    print("coach seed: %d shift entries for %d players (2026-09-22 to 2026-09-28). %s." % (
        n, len(TEAM_PLAYERS), ", ".join(parts)))


# ---------------------------------------------------------------- self test

def cmd_selftest(_args):
    global ROOT, _CLOCK
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

        # standing rulings, park, apply-answers, stuck, ruling blocks a raise (added 2026-09-28)
        def run(fn, **kw):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                fn(argparse.Namespace(**kw))
            return buf.getvalue()

        rk = dict(ruling_file=None, source_file=None, date="2026-09-19", asks=None, expires=None)
        r1 = "Constellation runs Sterling Meta spend until October."
        run(cmd_rulings_add, store="SBMW", lane="luka,magic", ruling=r1,
            source="Drew in #ai-team, 2026-09-19, ts 1789841289.951349", **dict(rk, asks="A21"))
        rl = rulings_load()["rulings"]
        check("rulings add: R1, two lanes, Slack ts, asks", len(rl) == 1 and rl[0]["id"] == "R1" and rl[0]["lane"] == ["luka", "magic"]
              and rl[0]["slack_ts"] == "1789841289.951349" and rl[0]["applies_to_asks"] == ["A21"] and rl[0]["expires"] is None, rl)
        o = run(cmd_rulings_add, store="sbmw", lane="magic", ruling=r1.replace(" ", "  "), source="again", **rk)
        check("rulings add: same store and text stays one ruling", len(rulings_load()["rulings"]) == 1 and "already on file as R1" in o, o)
        check("rulings add: bad lane refused", expect_exit(cmd_rulings_add, argparse.Namespace(
            store="NOI", lane="lebron", ruling="x", source="y", **rk)))
        check("rulings add: shell-eaten dollars refused", expect_exit(cmd_rulings_add, argparse.Namespace(
            store="NOI", lane="nick", ruling="Ignore the ,853 on the cost page", source="y", **rk)))
        run(cmd_rulings_add, store="ALL", lane="all", ruling="Aggregates only in #ai-team.", source="Drew, 2026-09-20",
            **dict(rk, date="2026-09-20"))
        run(cmd_rulings_add, store="NOI", lane="nick", ruling="Old rule that ran out.", source="Drew, 2026-09-01",
            **dict(rk, date="2026-09-01", expires="2026-09-15"))
        md = run(cmd_rulings_list, store=None, lane=None, date="2026-09-24", all=False, md=True)
        check("rulings list --md: one compact block, expired left out",
              md.startswith("**Drew's standing rulings** (2 active, as of 2026-09-24)") and
              "- R1 SBMW, luka + magic (2026-09-19): %s Source: Drew in #ai-team, 2026-09-19, ts 1789841289.951349. "
              "Settles A21." % r1 in md and "R3" not in md and EMDASH not in md, md)
        o = run(cmd_rulings_list, store="NOI", lane="kobe", date="2026-09-24", all=False, md=False)
        check("rulings list: store and lane filters, all-lane rulings always show",
              "- R2 ALL, all lanes" in o and "R1" not in o and "R3" not in o and "1 active ruling(s)" in o, o)
        o = run(cmd_rulings_list, store=None, lane=None, date="2026-09-24", all=True, md=False)
        check("rulings list --all adds expired ones", "R3" in o and "3 ruling(s)" in o, o)

        dk = dict(base, owner="Drew", needs_store=False, vendors=None)
        for lab in ("Gas Models call", "Boosted posts archive", "Old radio question", "Budget tab", "Tekion setup",
                    "Sterling Meta owner", "Pre-qualify line"):
            run(cmd_asks_add, date="2026-09-21", first_raised=None,
                **dict(dk, label=lab, ask="Decide on the %s." % lab.lower(), store="SBMW" if "Sterling" in lab else "NOI"))
        check("new asks are A3 to A9", [a["id"] for a in asks_load()["asks"]][-7:] == ["A%d" % i for i in range(3, 10)])
        up = dict(store=None, needs_store=None, no_raise=False)
        run(cmd_asks_update, id="A3", date="2026-09-22", **up)
        o = run(cmd_asks_update, id="A3", date="2026-09-23", **up)
        check("update says stuck at the third raise", "stuck (raised 3 times since Drew last answered): Friday digest only" in o, o)
        r = aging_report(asks_load(), "2026-09-24")
        check("stuck: leaves the nightly list, no digest on a Thursday", [a["id"] for a in r["stuck"]] == ["A3"]
              and "- A3," not in r["text"] and "Stuck (Friday digest)" not in r["text"], r["text"])
        r = aging_report(asks_load(), "2026-09-24", friday=True)
        check("stuck: --friday prints the digest", "### Stuck (Friday digest)" in r["text"] and
              "- A3, Gas Models call, open 3 days, Drew: raised 3 times with no answer from Drew, stuck since 2026-09-23. "
              "Done, drop or park?" in r["text"], r["text"])
        check("stuck: a Friday date prints the digest by itself", aging_report(asks_load(), "2026-09-25")["friday"]
              and "### Stuck (Friday digest)" in aging_report(asks_load(), "2026-09-25")["text"])
        o = run(cmd_asks_aging, date="2026-09-24", out=None, friday=False)
        check("aging summary counts stuck and parked", "1 stuck held for the Friday digest (A3)" in o and "0 parked off the list" in o, o)
        run(cmd_asks_update, id="A3", date="2026-09-24", trip_wire="deadline 10/1 inside a week", **up)
        r = aging_report(asks_load(), "2026-09-24")
        check("trip wire brings a stuck ask back that night",
              "- A3, Gas Models call, open 3 days, Drew, stuck but back tonight: deadline 10/1 inside a week" in r["text"], r["text"])
        # park
        run(cmd_asks_park, id="A4", date="2026-09-23", days=14, reason="Drew: after the October launch", reason_file=None)
        a4 = ask_find(asks_load(), "A4")
        check("park: status parked, park_until = date + 14", a4["status"] == "parked" and a4["park_until"] == "2026-10-07"
              and a4["history"][-1]["action"] == "parked", a4)
        r = aging_report(asks_load(), "2026-09-23")
        check("park: shows under Closed tonight the night it is parked",
              "- A4, Boosted posts archive: parked until 2026-10-07. Drew: after the October launch" in r["text"], r["text"])
        r = aging_report(asks_load(), "2026-10-06")
        check("park: off the aging list until park_until", "A4" not in r["text"] and [a["id"] for a in r["parked"]] == ["A4"], r["text"])
        o = run(cmd_asks_update, id="A4", date="2026-09-24", **up)
        check("park: a raise while parked is not counted", "raise not counted" in o and ask_find(asks_load(), "A4")["raised"] == ["2026-09-21"], o)
        r = aging_report(asks_load(), "2026-10-07")
        check("park: back on the list on park_until", "- A4, Boosted posts archive, open 16 days, Drew, back from parking "
              "(parked 2026-09-23 to 2026-10-07)" in r["text"], r["text"])
        check("park: a closed ask cannot be parked", expect_exit(cmd_asks_park, argparse.Namespace(
            id="A2", date="2026-09-24", days=14, reason="x", reason_file=None)))
        # a ruling blocks the raise
        o = run(cmd_rulings_add, store="SBMW", lane="magic", ruling=r1, source="again", **dict(rk, asks="A8"))
        check("rulings add merges new asks into the ruling on file", rulings_load()["rulings"][0]["applies_to_asks"] == ["A8", "A21"]
              and "A8 is still open" in o, o)
        o = run(cmd_asks_update, id="A8", date="2026-09-24", **up)
        a8 = ask_find(asks_load(), "A8")
        check("ruling blocks the raise and names the ruling", o.startswith("WARNING: A8 is settled by ruling R1")
              and a8["raised"] == ["2026-09-21"] and a8["history"][-1]["action"] == "raise-refused"
              and a8["history"][-1]["refused_by"] == ["R1"], o)
        r = aging_report(asks_load(), "2026-09-24")
        check("aging leaves a ruling-settled ask out and warns", "- A8," not in r["text"]
              and any(w.startswith("WARNING: A8 (Sterling Meta owner) is still open but ruling R1 settles it") for w in r["warnings"]), r["warnings"])
        o = run(cmd_asks_add, date="2026-09-24", first_raised=None,
                **dict(dk, store="SBMW", label="Sterling Meta spend owner", ask="Who pays for Sterling Meta spend before October?"))
        check("asks add warns when a ruling may already cover it",
              "WARNING: ruling R1 may already settle A10 (shared words: october, spend, sterling)" in o, o)
        # apply-answers: done, drop, park, note
        afile = os.path.join(tmp, "ask_answers.json")
        save_json(afile, {"answers": [
            {"id": "A7", "decision": "done", "how": "reaction :white_check_mark:", "slack_ts": "1790000000.000100",
             "answered_at": "2026-09-24"},
            {"id": "A5", "decision": "drop", "how": "reply", "ts": "1790000000.000200", "text": "drop it, radio is gone",
             "answered_at": "2026-09-24"},
            {"id": "A9", "decision": "park", "how": "reaction :zzz:", "slack_ts": "1790000000.000300"},
            {"id": "A6", "decision": "note", "how": "reply", "ts": "1790000000.000400", "text": "Ask Nick, it is the Q3 tab"},
            {"id": "A99", "decision": "done"}, {"id": "A3", "decision": "maybe"}]})
        o = run(cmd_asks_apply_answers, file=afile, date="2026-09-24", dry_run=False)
        d = asks_load()
        a5, a6, a7, a9 = (ask_find(d, x) for x in ("A5", "A6", "A7", "A9"))
        check("apply-answers done: closed with Drew's Slack evidence", a7["status"] == "closed" and a7["closed_date"] == "2026-09-24"
              and a7["closure_evidence"] == "Drew, Slack reaction :white_check_mark: 1790000000.000100", a7)
        drop_r = [x for x in rulings_load()["rulings"] if x["applies_to_asks"] == ["A5"]]
        check("apply-answers drop: withdrawn and a ruling added", a5["status"] == "withdrawn"
              and a5["withdrawn_reason"] == "Drew said drop, 2026-09-24" and len(drop_r) == 1 and drop_r[0]["store"] == "NOI"
              and "radio is gone" in drop_r[0]["ruling"] and drop_r[0]["slack_ts"] == "1790000000.000200"
              and a5["ruling_ids"] == [drop_r[0]["id"]], (a5, drop_r))
        check("apply-answers park: parked 14 days", a9["status"] == "parked" and a9["park_until"] == "2026-10-08", a9)
        check("apply-answers note: in history as a Drew note, status unchanged", a6["status"] == "open"
              and a6["history"][-1]["action"] == "drew-note" and a6["history"][-1]["note"] == "Ask Nick, it is the Q3 tab", a6)
        check("apply-answers skips an unknown ask and an unknown decision", "A99 skipped: not in asks.json" in o
              and "A3 skipped: decision 'maybe'" in o and "6 answer(s) read, 1 closed, 1 withdrawn (1 new ruling(s)), "
              "1 parked, 1 noted, 2 skipped." in o, o)
        before = (open(LP("asks.json"), encoding="utf-8").read(), open(LP("rulings.json"), encoding="utf-8").read())
        o = run(cmd_asks_apply_answers, file=afile, date="2026-09-25", dry_run=False)
        check("apply-answers is idempotent", "0 closed, 0 withdrawn (0 new ruling(s)), 0 parked, 0 noted, 6 skipped" in o
              and before == (open(LP("asks.json"), encoding="utf-8").read(), open(LP("rulings.json"), encoding="utf-8").read()), o)
        save_json(afile, [{"id": "A6", "decision": "done", "how": "reply", "ts": "1790000000.000500"}])
        o = run(cmd_asks_apply_answers, file=afile, date="2026-09-25", dry_run=True)
        check("apply-answers --dry-run writes nothing", "Dry run: nothing written" in o and ask_find(asks_load(), "A6")["status"] == "open", o)
        save_json(afile, [{"id": "A3", "decision": "note", "text": "Leave it paused", "date": "2026-09-24",
                           "source": "Claude Code session"}])
        run(cmd_asks_apply_answers, file=afile, date="2026-09-24", dry_run=False)
        a3 = ask_find(asks_load(), "A3")
        check("a Drew answer resets stuck", not is_stuck(a3) and raises_unanswered(a3) == []
              and a3["drew_answers"][-1]["source"] == "Claude Code session", a3)
        check("answer text with a phone number is withheld",
              answer_fields({"id": "A1", "decision": "note", "text": "call 714-555-0100"})["text"].startswith("(text withheld"))
        # vendor ignored status carries into the next month
        with quiet:
            cmd_vendor_update(argparse.Namespace(date="2026-09-28", store="NOI", vendor="Auto Credit Express", month=None,
                                                 spend=None, leads=None, sold=None, as_of=None, source=None, source_file=None,
                                                 status="ignored", note="Drew: cost page stale (R3)", note_file=None,
                                                 bench_category=None, ask=None))
        vd = vendor_load()
        row, created = vendor_upsert(vd, "NOI", "Auto Credit Express", "2026-10", "2026-10-02")
        check("vendor ignored status carries into the next month", created and row["status"] == "ignored"
              and "carried from V1 (2026-09)" in row["status_history"][-1]["note"], row)
        check("vendor ignored verdict", verdict({"status": "ignored", "spend": 3850.0, "leads": 0, "sold": 0}, {"rate": None}, 10)
              .startswith("ignore per Drew"))
        check("rulings and asks files hold no em dash", EMDASH not in open(LP("rulings.json"), encoding="utf-8").read()
              and EMDASH not in open(LP("asks.json"), encoding="utf-8").read())

        # shift log clock, settled findings, coaching (added 2026-09-28)
        utc = dt.timezone.utc

        def at(y, mo, d, h, mi):
            return pacific_from_utc(dt.datetime(y, mo, d, h, mi, tzinfo=utc))

        check("clock: PDT in September", clock_stamp(at(2026, 9, 29, 8, 4)) == "01:04 PDT")
        check("clock: PST in December", clock_stamp(at(2026, 12, 1, 9, 0)) == "01:00 PST")
        check("clock: DST starts 2026-03-08 at 2 AM", clock_stamp(at(2026, 3, 8, 9, 59)) == "01:59 PST"
              and clock_stamp(at(2026, 3, 8, 10, 0)) == "03:00 PDT")
        check("clock: DST ends 2026-11-01 at 2 AM", clock_stamp(at(2026, 11, 1, 8, 59)) == "01:59 PDT"
              and clock_stamp(at(2026, 11, 1, 9, 0)) == "01:00 PST")
        try:
            from zoneinfo import ZoneInfo
            z = ZoneInfo("America/Los_Angeles")
            same = all(clock_stamp(pacific_from_utc(x)) == clock_stamp(x.astimezone(z)) for x in (
                dt.datetime(2026, m, 15, h, 30, tzinfo=utc) for m in range(1, 13) for h in (0, 9, 17)))
        except Exception:
            same = True
        check("clock: the fallback agrees with the tz database all year", same)
        now = [at(2026, 9, 29, 8, 0)]
        _CLOCK = lambda: now[0]  # noqa: E731
        lk = dict(stamp_only=False, start=False, end=False, mode="shift", text=None, text_file=None)
        o = run(cmd_log, date="2026-09-29", **dict(lk, start=True))
        log_path = P("2026-09-29", "shift-log.md")
        body = open(log_path, encoding="utf-8").read()
        check("log --start creates the log with the standard header",
              body == "---\ntype: shift-log\ndate: 2026-09-29\nstatus: active\ntags: [ai-team, shift-log]\n---\n"
                      "# Shift log 2026-09-29 (shift, Tuesday)\n\n- Start: 01:00 PDT (Tuesday, mode shift)\n"
              and "created with the standard header" in o, body)
        now[0] = at(2026, 9, 29, 8, 4)
        run(cmd_log, date="2026-09-29", **dict(lk, text="tip-off posted " + EMDASH + " five on the floor"))
        body = open(log_path, encoding="utf-8").read()
        check("log --text appends '- HH:MM PDT text' from the clock, em dash scrubbed",
              body.endswith("\n- 01:04 PDT tip-off posted - five on the floor\n") and EMDASH not in body, body)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("- a hand-typed line with no newline")
        tf = os.path.join(tmp, "logline.txt")
        save_text(tf, "Nick: NOI vendors $8,277 month to date\n")
        now[0] = at(2026, 9, 29, 8, 9)
        run(cmd_log, date="2026-09-29", **dict(lk, text_file=tf))
        body = open(log_path, encoding="utf-8").read()
        check("log --text-file keeps dollars and fixes a missing newline",
              body.endswith("no newline\n- 01:09 PDT Nick: NOI vendors $8,277 month to date\n"), body[-120:])
        check("log refuses shell-eaten dollars", expect_exit(cmd_log, argparse.Namespace(
            date="2026-09-29", **dict(lk, text="Nick: vendors ,277 month to date"))))
        check("log refuses an End line typed as text", expect_exit(cmd_log, argparse.Namespace(
            date="2026-09-29", **dict(lk, text="End: 01:17 PDT"))))
        check("log needs exactly one of --text, --start, --end", expect_exit(cmd_log, argparse.Namespace(
            date="2026-09-29", **dict(lk, start=True, end=True))))
        now[0] = at(2026, 9, 29, 8, 17)
        o = run(cmd_log, date="2026-09-29", **dict(lk, end=True))
        body = open(log_path, encoding="utf-8").read()
        check("log --end writes the final whistle tipoff.sh watches for",
              body.endswith("\n- End: 01:17 PDT\n") and len(re.findall(r"^- End:", body, re.M)) == 1
              and "Shift ran 01:00 to 01:17 PDT, 17 minutes." in o, o)
        o = run(cmd_log, date=None, **dict(lk, stamp_only=True))
        check("log --stamp-only prints the time only", o == "01:17 PDT\n", o)
        _CLOCK = None

        sk = dict(subject=None, subject_file=None, finding=None, finding_file=None, source=None, source_file=None,
                  reopen_if=None, reopen_if_file=None, owner=None, first_seen=None, date="2026-09-28")
        run(cmd_settled_add, store="NOI", lane="shaq,nick", keywords="calls from ads, VinSolutions, phone, Value-Payment",
            **dict(sk, subject="NOI ad calls vs VinSolutions", finding="VinSolutions has no phone bucket; a measurement gap.",
                   source="2026-09-28/brief.md", reopen_if="VinSolutions adds a phone split", owner="shaq"))
        o = run(cmd_settled_add, store="noi", lane="kobe", keywords="Phone, forwarding number",
                **dict(sk, subject="NOI ad calls vs  VinSolutions", finding="x", source="y", reopen_if="z"))
        sd = settled_load()["settled"]
        check("settled add: S1 with owner, lanes, keywords; the same store and subject stays one item",
              len(sd) == 1 and sd[0]["id"] == "S1" and sd[0]["owner"] == "shaq" and sd[0]["lane"] == ["kobe", "shaq", "nick"]
              and sd[0]["keywords"] == ["calls from ads", "VinSolutions", "phone", "Value-Payment", "forwarding number"]
              and sd[0]["status"] == "settled" and "already on file as S1" in o, (sd, o))
        run(cmd_settled_add, store="SBMW", lane="worthy", keywords="SRP, search page, Sterling",
            **dict(sk, subject="Sterling SRP no leads", finding="Normal browsing.", source="worthy.md",
                   reopen_if="the SRP gets a form", first_seen="2026-09-24"))
        check("settled add refuses empty keywords", expect_exit(cmd_settled_add, argparse.Namespace(
            store="NOI", lane="luka", keywords=" , ", **dict(sk, subject="a", finding="b", source="c", reopen_if="d"))))
        ck = dict(note=None, note_file=None)
        o = run(cmd_settled_check, date="2026-09-29", id="S1", still_true="yes", by="shaq",
                **dict(ck, note="53 calls again, still no phone bucket (crm_mtd_NOI.json)"))
        run(cmd_settled_check, date="2026-09-29", id="s1", still_true="yes", by="shaq", **dict(ck, note="rechecked"))
        s1 = settled_load()["settled"][0]
        check("settled check yes: last_checked moves, one check per player per night, still settled",
              s1["last_checked"] == "2026-09-29" and len(s1["checks"]) == 1 and s1["checks"][0]["note"] == "rechecked"
              and s1["status"] == "settled" and "Nothing to report on it tonight" in o, (s1, o))
        o = run(cmd_settled_check, date="2026-09-29", id="S2", still_true="no", by="worthy",
                **dict(ck, note="Sterling added a lead form to the SRP"))
        s2 = settled_load()["settled"][1]
        check("settled check no: reopens it and prints a line for Magic", s2["status"] == "reopened"
              and s2["reopened_on"] == "2026-09-29" and o.startswith("FOR MAGIC: S2 REOPENED on 2026-09-29 by worthy"), o)
        md = run(cmd_settled_list, lane="shaq", store=None, date="2026-09-29", all=False, md=True)
        check("settled list --md --lane: one compact block, that lane only",
              md.startswith("**Settled findings** (1, as of 2026-09-29, lane shaq)")
              and "- S1 NOI, check: shaq (also kobe, nick), settled 2026-09-28, last checked 2026-09-29. NOI ad calls vs "
                  "VinSolutions: VinSolutions has no phone bucket; a measurement gap. Reopen if: VinSolutions adds a "
                  "phone split.\n" in md and "S2" not in md and "--by shaq" in md and "Source: 2026" not in md, md)
        o = run(cmd_settled_list, lane="shaq", store=None, date="2026-09-29", all=False, md=False)
        check("settled list (plain) keeps the sources for Magic", "phone split. Source: 2026-09-28/brief.md." in o, o)
        md = run(cmd_settled_list, lane=None, store=None, date="2026-09-29", all=False, md=True)
        check("settled list --md shows a reopened item as news", "S2 SBMW, check: worthy" in md
              and "REOPENED 2026-09-29 by worthy: Sterling added a lead form to the SRP" in md, md)
        o = run(cmd_settled_list, lane=None, store=None, date="2026-09-30", all=False, md=False)
        check("settled list: who checked tonight and who did not", "2 item(s), 0 checked tonight, 1 not checked tonight "
              "(S1 owner shaq), 1 reopened (S2 on 2026-09-29)" in o, o)
        md = run(cmd_settled_list, lane=None, store=None, date="2026-10-05", all=False, md=True)
        check("settled list flags an item nobody checked for days", "NOT CHECKED since 2026-09-29" in md, md)
        fnd = os.path.join(tmp, "shaq.md")
        save_text(fnd, "## Findings\n- Value-Payment logged 53 calls from ads; VinSolutions has no phone bucket.\n"
                       "- S1 still true: 53 calls, VinSolutions has no phone split.\n- MCP PMax clicks fell.\n")
        o = run(cmd_settled_scan, file=fnd, lane="shaq", date="2026-09-29")
        check("settled scan flags a repeat that does not cite the id, skips the line that does",
              "- S1 (NOI, NOI ad calls vs VinSolutions): 1 line(s) read like it without citing S1, first at line 2" in o
              and "1 settled item(s) may be repeated" in o, o)
        uk = dict(status=None, store=None, lane=None, owner=None, keywords=None, subject=None, subject_file=None,
                  finding=None, finding_file=None, source=None, source_file=None, reopen_if=None, reopen_if_file=None,
                  note=None, note_file=None)
        run(cmd_settled_update, id="S2", date="2026-09-30",
            **dict(uk, status="settled", finding="The new SRP form converts nothing yet.", note="Magic re-settled"))
        run(cmd_settled_update, id="S1", date="2026-09-30", **dict(uk, status="retired", note="VinSolutions split arrived"))
        sd = settled_load()["settled"]
        check("settled update: re-settle and retire", sd[1]["status"] == "settled" and sd[1]["settled_on"] == "2026-09-30"
              and sd[1]["finding"].startswith("The new SRP form") and sd[0]["status"] == "retired"
              and sd[0]["retired_on"] == "2026-09-30", sd)
        o = run(cmd_settled_list, lane=None, store=None, date="2026-09-30", all=False, md=False)
        check("settled list leaves a retired item out unless --all", "- S1" not in o and "- S2" in o
              and "- S1" in run(cmd_settled_list, lane=None, store=None, date="2026-09-30", all=True, md=False), o)
        check("settled check refuses a retired item", expect_exit(cmd_settled_check, argparse.Namespace(
            date="2026-09-30", id="S1", still_true="yes", by="shaq", **dict(ck, note="x"))))
        check("settled.json holds no em dash", EMDASH not in open(LP("settled.json"), encoding="utf-8").read())

        kk = dict(bounce=None, factual=None, self_caught=0, thought_ahead=None, peer_catch=None, note_file=None)
        o = "".join(run(cmd_coach_add, player="Rook", date=d, **dict(kk, note="clean night"))
                    for d in daterange("2026-10-01", "2026-10-05"))
        rp = coach_load()["players"]["rook"]
        check("coach: a new player starts as rookie and makes starter after 5 clean shifts",
              rp["level"] == "starter" and rp["level_since"] == "2026-10-05" and "New player: starts as rookie" in o
              and "PROMOTION: rook is now starter as of 2026-10-05" in o, (rp.get("level_history"), o))
        run(cmd_coach_add, player="rook", date="2026-10-06",
            **dict(kk, bounce=["wrong window on the Ads total"], factual=["yes"], note="Label every window."))
        run(cmd_coach_add, player="rook", date="2026-10-07",
            **dict(kk, bounce=["buried the headline"], factual=["no"], self_caught=1, note="Lead with the point."))
        s = coach_stats(coach_load()["players"]["rook"])
        check("coach: a factual bounce resets the streak, a wording bounce does not", s["streak"] == 1
              and s["factual_last10"] == 1 and s["wording_last10"] == 1 and s["self_caught_last10"] == 1, s)
        for i, d in enumerate(daterange("2026-10-08", "2026-10-15")):
            run(cmd_coach_add, player="rook", date=d,
                **dict(kk, thought_ahead=["risk %d building" % i] if i < 2 else None, note="ok"))
        s = coach_stats(coach_load()["players"]["rook"])
        check("coach: 9 clean shifts and 2 thought-ahead items is not senior yet",
              coach_load()["players"]["rook"]["level"] == "starter" and coach_next_text(s) ==
              "senior: needs 1 more clean shift in a row (9 of 10) and 1 more confirmed thought-ahead item (2 of 3)",
              coach_next_text(s))
        o = run(cmd_coach_add, player="rook", date="2026-10-16",
                **dict(kk, thought_ahead=["CARS Act deadline on the pre-qualified ad"], note="Good look ahead."))
        rp = coach_load()["players"]["rook"]
        check("coach: 10 clean shifts in a row plus 3 thought-ahead items makes senior", rp["level"] == "senior"
              and "PROMOTION: rook is now senior as of 2026-10-16 (10 clean shifts in a row at starter, 3 confirmed "
                  "thought-ahead items)" in o, o)
        s = coach_stats(rp)
        check("coach: a senior's next step is captain, counted from the promotion", coach_next_text(s) ==
              "captain: needs 20 more clean shifts in a row as senior (0 of 20) and 2 more peer-review catches of a "
              "real problem (0 of 2)", coach_next_text(s))
        o = run(cmd_coach_add, player="rook", date="2026-10-16",
                **dict(kk, thought_ahead=["CARS Act deadline on the pre-qualified ad"], peer_catch=["caught a wrong window"],
                       note="Replaced."))
        rp = coach_load()["players"]["rook"]
        check("coach add twice on one date replaces the entry", o.startswith("coach add: replaced rook 2026-10-16")
              and len([h for h in rp["history"] if h["date"] == "2026-10-16"]) == 1
              and rp["history"][-1]["peer_catches"] == ["caught a wrong window"] and rp["level"] == "senior", o)
        check("coach add refuses a bounce with no factual flag", expect_exit(cmd_coach_add, argparse.Namespace(
            player="rook", date="2026-10-17", **dict(kk, bounce=["x", "y"], factual=["yes"], note="n"))))
        check("coach add refuses the player name all", expect_exit(cmd_coach_add, argparse.Namespace(
            player="all", date="2026-10-17", **dict(kk, note="n"))))
        line = coach_entry_line({"date": "2026-10-17", "bounces": [{"cause": "wrong window", "factual": True},
                                                                  {"cause": "wrong actor.", "factual": True}],
                                 "coach_note": "Name the actor"})
        check("coach entry line numbers two bounces", line == "2026-10-17: 2 factual bounces: (1) wrong window. "
              "(2) wrong actor. Magic: Name the actor.", line)
        md = run(cmd_coach_list, player="rook", last=2, md=True, date=None)
        check("coach list --md: level, streak, newest notes first",
              md.startswith("**Coaching notes for Rook** (senior since 2026-10-16; clean streak 10 shifts; next captain: needs")
              and md.count("\n- ") == 2 and "\n- 2026-10-16: clean. thought ahead: CARS Act deadline on the pre-qualified "
              "ad. peer catch: caught a wrong window. Magic: Replaced.\n" in md, md)
        md = run(cmd_coach_scorecard, md=True, date=None)
        check("coach scorecard --md: the five plus anyone new, one row each",
              "| Player | Level | Clean streak |" in md and "| Kobe | starter | 0 | 0 | 0 | 0 | 0 | 0 | senior: needs 10 more "
              "clean shifts in a row (0 of 10) and 3 more confirmed thought-ahead items (0 of 3) |" in md
              and "| Rook | senior | 10 | 0 | 1 | 1 | 0 | 1 | captain: needs 20 more" in md, md)
        run(cmd_coach_level, player="rook", level="starter", date="2026-10-18",
            reason="Magic: back to full checks after two misses", reason_file=None)
        rp = coach_load()["players"]["rook"]
        check("coach level sets a level by hand with a reason", rp["level"] == "starter"
              and rp["level_history"][-1].get("set_by_hand") and rp["level_since"] == "2026-10-18", rp["level_history"][-1])
        os.remove(LP("settled.json"))
        os.remove(LP("coaching.json"))
        o = run(cmd_settled_seed, force=False)
        sd = settled_load()["settled"]
        check("settled seed: S1 to S11, each with a source, a reopen condition and keywords",
              [x["id"] for x in sd] == ["S%d" % i for i in range(1, 12)] and all(
                  x["source"] and x["reopen_if"] and len(x["keywords"]) >= 2 and x["last_checked"] == "2026-09-28"
                  and x["status"] == "settled" for x in sd), o)
        check("settled seed refuses to run twice without --force",
              expect_exit(cmd_settled_seed, argparse.Namespace(force=False)))
        o = run(cmd_settled_seed, force=True)
        check("settled seed --force adds nothing already on file", "0 item(s) added" in o
              and len(settled_load()["settled"]) == 11, o)
        o = run(cmd_coach_seed, force=False)
        streaks = {n: coach_stats(p)["streak"] for n, p in coach_load()["players"].items()}
        check("coach seed: the 9/22 to 9/28 backfill gives the real streaks",
              streaks == {"kobe": 3, "shaq": 0, "luka": 1, "worthy": 0, "nick": 1} and "25 shift entries" in o, (streaks, o))
        check("coaching.json and settled.json hold no em dash",
              EMDASH not in open(LP("coaching.json"), encoding="utf-8").read()
              and EMDASH not in open(LP("settled.json"), encoding="utf-8").read())
        check("script source has no em dash", EMDASH not in open(os.path.abspath(__file__), encoding="utf-8").read())
    finally:
        ROOT = real_root
        _CLOCK = None
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
    ap = argparse.ArgumentParser(description="AI team ledgers: vendor watch, asks and wins, rulings, settled findings, "
                                             "coaching, shift ledger, shift log clock, month pack.")
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
    for t in ("owner", "label", "ask", "evidence", "if_skipped", "done_when", "note", "trip_wire"):
        add_text(p, t)
    p.set_defaults(fn=cmd_asks_update)
    p = a.add_parser("close")
    p.add_argument("--id", required=True); p.add_argument("--date", required=True)
    add_text(p, "evidence"); add_text(p, "win")
    p.set_defaults(fn=cmd_asks_close)
    p = a.add_parser("withdraw")
    p.add_argument("--id", required=True); p.add_argument("--date", required=True); add_text(p, "reason")
    p.set_defaults(fn=cmd_asks_withdraw)
    p = a.add_parser("park")
    p.add_argument("--id", required=True); p.add_argument("--date", required=True)
    p.add_argument("--days", type=int, default=PARK_DAYS); add_text(p, "reason")
    p.set_defaults(fn=cmd_asks_park)
    p = a.add_parser("apply-answers")
    p.add_argument("--file", required=True); p.add_argument("--date", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_asks_apply_answers)
    p = a.add_parser("list"); p.add_argument("--status", choices=ASK_STATUSES + ("all",)); p.add_argument("--store")
    p.set_defaults(fn=cmd_asks_list)
    p = a.add_parser("aging"); p.add_argument("--date", required=True); p.add_argument("--out")
    p.add_argument("--friday", action="store_true", help="print the Stuck (Friday digest) block on any day")
    p.set_defaults(fn=cmd_asks_aging)
    p = a.add_parser("request"); p.add_argument("--date", required=True); p.add_argument("--id")
    p.add_argument("--due", action="store_true"); p.add_argument("--out-dir", help=argparse.SUPPRESS)
    p.set_defaults(fn=cmd_asks_request)

    r = sub.add_parser("rulings").add_subparsers(dest="sub", required=True)
    p = r.add_parser("add")
    p.add_argument("--store", required=True); p.add_argument("--lane", required=True)
    p.add_argument("--date"); p.add_argument("--asks"); p.add_argument("--expires")
    add_text(p, "ruling"); add_text(p, "source")
    p.set_defaults(fn=cmd_rulings_add)
    p = r.add_parser("list")
    p.add_argument("--store"); p.add_argument("--lane"); p.add_argument("--date")
    p.add_argument("--all", action="store_true"); p.add_argument("--md", action="store_true")
    p.set_defaults(fn=cmd_rulings_list)

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
    p = sub.add_parser("week"); p.add_argument("--date", required=True); p.add_argument("--out")
    p.set_defaults(fn=cmd_week)
    p = sub.add_parser("ads-dump"); p.add_argument("--date", required=True); p.set_defaults(fn=cmd_ads_dump)
    p = sub.add_parser("crm-shape"); p.set_defaults(fn=cmd_crm_shape)
    p = sub.add_parser("crm-check"); p.add_argument("--file", required=True); p.set_defaults(fn=cmd_crm_check)
    p = sub.add_parser("crm-correct")
    for x in ("--shift", "--store", "--field", "--value"):
        p.add_argument(x, required=True)
    p.add_argument("--source", dest="source_name", required=True)
    add_text(p, "reason"); add_text(p, "evidence")
    p.set_defaults(fn=cmd_crm_correct)

    p = sub.add_parser("log", help="append a real-clock line to outputs/ai-team/{date}/shift-log.md")
    p.add_argument("--date"); p.add_argument("--stamp-only", action="store_true")
    p.add_argument("--start", action="store_true"); p.add_argument("--end", action="store_true")
    p.add_argument("--mode", choices=("shift", "dry-run"), default="shift")
    add_text(p, "text")
    p.set_defaults(fn=cmd_log)

    t = sub.add_parser("settled").add_subparsers(dest="sub", required=True)
    p = t.add_parser("add")
    p.add_argument("--store", required=True); p.add_argument("--lane", required=True); p.add_argument("--owner")
    p.add_argument("--keywords", required=True); p.add_argument("--date"); p.add_argument("--first-seen")
    for x in ("subject", "finding", "source", "reopen_if"):
        add_text(p, x)
    p.set_defaults(fn=cmd_settled_add)
    p = t.add_parser("check")
    p.add_argument("--date", required=True); p.add_argument("--id", required=True)
    p.add_argument("--still-true", required=True, choices=("yes", "no")); p.add_argument("--by")
    add_text(p, "note")
    p.set_defaults(fn=cmd_settled_check)
    p = t.add_parser("update")
    p.add_argument("--id", required=True); p.add_argument("--date", required=True)
    p.add_argument("--status", choices=SETTLED_STATUSES); p.add_argument("--store"); p.add_argument("--lane")
    p.add_argument("--owner"); p.add_argument("--keywords")
    for x in ("subject", "finding", "source", "reopen_if", "note"):
        add_text(p, x)
    p.set_defaults(fn=cmd_settled_update)
    p = t.add_parser("list")
    p.add_argument("--lane"); p.add_argument("--store"); p.add_argument("--date")
    p.add_argument("--all", action="store_true"); p.add_argument("--md", action="store_true")
    p.set_defaults(fn=cmd_settled_list)
    p = t.add_parser("scan"); p.add_argument("--file", required=True); p.add_argument("--lane"); p.add_argument("--date")
    p.set_defaults(fn=cmd_settled_scan)
    p = t.add_parser("seed"); p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_settled_seed)

    c = sub.add_parser("coach").add_subparsers(dest="sub", required=True)
    p = c.add_parser("add")
    p.add_argument("--player", required=True); p.add_argument("--date", required=True)
    p.add_argument("--bounce", action="append"); p.add_argument("--factual", action="append", choices=("yes", "no"))
    p.add_argument("--self-caught", type=int, default=0)
    p.add_argument("--thought-ahead", action="append"); p.add_argument("--peer-catch", action="append")
    add_text(p, "note")
    p.set_defaults(fn=cmd_coach_add)
    p = c.add_parser("list")
    p.add_argument("--player", required=True); p.add_argument("--last", type=int, default=5)
    p.add_argument("--md", action="store_true"); p.add_argument("--date")
    p.set_defaults(fn=cmd_coach_list)
    p = c.add_parser("scorecard"); p.add_argument("--md", action="store_true"); p.add_argument("--date")
    p.set_defaults(fn=cmd_coach_scorecard)
    p = c.add_parser("level")
    p.add_argument("--player", required=True); p.add_argument("--level", required=True, choices=LEVELS)
    p.add_argument("--date", required=True); add_text(p, "reason")
    p.set_defaults(fn=cmd_coach_level)
    p = c.add_parser("seed"); p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_coach_seed)

    p = sub.add_parser("selftest"); p.set_defaults(fn=cmd_selftest)

    args = ap.parse_args()
    ROOT = os.path.abspath(args.root)
    args.fn(args)


if __name__ == "__main__":
    main()
