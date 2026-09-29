#!/usr/bin/env python3
"""Deltas for the DigitalCLIQ AI night shift: what changed since last night, read the way a careful
analyst reads data at 1 AM. Standard library only.

The shift runs at 1 AM the morning after the day it covers. So:
  * the newest day in every pull is PRELIMINARY (GA4 is still processing it, the Ads export ran minutes
    after midnight, the CRM report was generated minutes after midnight). It is quoted as preliminary and
    never gets a trend flag.
  * the days before it keep RESTATING for a while (Sterling's 9/24 read 808 GA4 sessions at 1 AM on 9/25
    and 1,328 at 1 AM on 9/28; Google Ads conversions keep landing on the click date for days).
  * the last complete day is the day before the newest one. That is the day the team trends, against the
    day before it and against the same weekday last week (dealer traffic swings by weekday, so flags use
    the same-weekday comparison only).
  * CRM files are month to date. The night's news is the increment since last night's MTD, not the MTD.

Usage (one plain call from the vault root, writes its own files, prints a short summary):
  D = python3 .claude/skills/ai-team/scripts/deltas.py
  D --date YYYY-MM-DD [--prev-date YYYY-MM-DD] [--out DIR] [--quiet]
      Compares tonight's shift folder outputs/ai-team/{date}/ with the previous shift's (default: the
      newest earlier shift folder that holds data). Per store and source, when last night's folder has no
      file, the newest earlier shift with one is used and the baseline line says so.
      Writes {out}/deltas.json and {out}/deltas.md (default out: outputs/ai-team/{date}/data/).
      Safe to re-run: Kobe after his GA4 pull, Shaq after the Ads dump, Nick after his CRM snapshots.
      Each run rewrites both files from whatever is on disk; a source not saved yet shows as missing.
  D selftest
      Offline checks in a temp folder, touches nothing real.

Sources read (never re-pulled, nothing is sent anywhere):
  GA4   data/ga4_{STORE}.json            channel_daily_last7 (date x channel: sessions, keyEvents)
  Ads   data/{STORE}_campaign_daily_30d.txt (or .json), written by ledgers.py ads-dump
  CRM   data/crm_mtd_{STORE}.json        crm_mtd.v1 (and the two 2026-09-22 legacy shapes)
  Inside a shift, every pull found (data/, data/*/, run*/data/) is merged and the latest pull wins per
  day, as in ledgers.py. Same-weekday-last-week values older than tonight's pull come from the newest
  earlier shift pull that holds that day as a complete day (the file is named in deltas.json).

Rules (constants below):
  Restated   the same day moved RESTATE_PCT (10%) or more since last night's pull AND by at least
             MIN_ABS (20 sessions, 5 key events, 5 clicks, 10 dollars, 1 conversion, 1 lead).
             "filled in" = last night called that day preliminary (expected); "changed" = a day last night
             called complete moved (worth a sentence: why?). A decrease on a complete day is worth a look.
  CRM        month-to-date numbers only grow. A decrease since last night (headline or a source) is a
             restatement of earlier days, any size of 1 or more. Two pulls through the same day that
             differ by 1 or more are a restatement too.
  Flag       last complete day vs the same weekday last week moved FLAG_PCT (25%) or more, by at least
             MIN_ABS, from a base of at least FLAG_MIN_BASE. Ads conversions are never flagged on the
             last complete day: they are still landing (conversion lag), so the comparison is biased low.

Exit codes: 0 written; 1 usage error (bad date, no shift folder); 2 written, but no earlier shift to
compare against (restatements and increments are empty).

Laws: aggregates only, never em dashes (replaced on write), never estimate (a missing file stays missing).
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

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
ROOT = DEFAULT_ROOT
EMDASH, ENDASH = chr(8212), chr(8211)  # written as chr() so this file never holds one

STORES = ("SBMW", "NCBMW", "NOI", "MCP", "ATLAS")
RESTATE_PCT = 10.0
FLAG_PCT = 25.0
MIN_ABS = {"sessions": 20, "keyEvents": 5, "clicks": 5, "cost": 10.0, "conversions": 1.0,
           "leads": 1, "good_leads": 1, "appointments": 1, "shows": 1, "sold": 1, "crm_cost": 1.0}
FLAG_MIN_BASE = {"sessions": 20, "keyEvents": 5, "clicks": 10, "cost": 20.0, "conversions": 5.0}
GA4_METRICS = ("sessions", "keyEvents")
ADS_METRICS = ("clicks", "cost", "conversions")
ADS_LAGGING = ("conversions",)
CRM_METRICS = ("leads", "good_leads", "appointments", "shows", "sold", "cost")
LABEL = {"sessions": "sessions", "keyEvents": "key events", "clicks": "clicks", "cost": "cost",
         "conversions": "conversions", "leads": "leads", "good_leads": "good leads",
         "appointments": "appointments", "shows": "shows", "sold": "sold"}
NIGHT, NIGHTS = "last night", "last night's"   # render wording; "the last shift" after a weekend
HISTORY_DAYS = 21       # how far back same-weekday-last-week values are looked up
BASELINE_DAYS = 10      # how far back a missing baseline file is looked for
MD_LINES = 3            # channel or campaign lines per block in deltas.md (the JSON has all of them)


# ---------------------------------------------------------------- basics

def die(msg, code=1):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(code)


def P(*parts):
    return os.path.join(ROOT, "outputs", "ai-team", *parts)


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


def day_of(s):
    """'20260924' or '2026-09-24' -> '2026-09-24', else None."""
    s = str(s or "").strip()
    m = re.match(r"^(\d{4})-?(\d{2})-?(\d{2})$", s)
    return "%s-%s-%s" % m.groups() if m else None


def shift_day(day, n):
    return (dt.date.fromisoformat(day) + dt.timedelta(days=n)).isoformat()


def days_between(a, b):
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def wd(day):
    """'2026-09-24' -> 'Thu 9/24'."""
    d = dt.date.fromisoformat(day)
    return "%s %d/%d" % (d.strftime("%a"), d.month, d.day)


def parse_ts(v):
    s = str(v or "").strip().replace("Z", "").split(".")[0]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M",
                "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M"):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def mtime(path):
    try:
        return dt.datetime.fromtimestamp(os.path.getmtime(path))
    except OSError:
        return dt.datetime.min


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
    return int(f) if f.is_integer() and "." not in s else f


def tidy(v):
    """Round floats for the JSON; whole floats become ints."""
    if isinstance(v, float):
        v = round(v, 2)
        return int(v) if v.is_integer() else v
    return v


def fmt(v, metric=None):
    if v is None:
        return "n/a"
    if metric in ("cost", "crm_cost"):
        return "$" + format(int(round(v)), ",")
    if isinstance(v, float) and not v.is_integer():
        return format(round(v, 1), ",")
    return format(int(round(v)), ",")


def fmt_change(change, pct, metric=None):
    sign = "+" if change > 0 else "-" if change < 0 else ""
    size = fmt(abs(change), metric)
    if pct is None:
        return "%s%s, new" % (sign, size)
    return "%s%s, %s%d%%" % (sign, size, "+" if pct > 0 else "", round(pct))


def lab(metric, v=None):
    """Label with a singular for exactly 1: '1 click', '1 key event'."""
    w = LABEL.get(metric, metric)
    if v is not None and abs(v) == 1 and w.endswith("s") and metric != "cost":
        return w[:-1]
    return w


def pct_of(before, after):
    if before in (None, 0) or after is None:
        return None
    return round((after - before) / abs(before) * 100.0, 1)


# ---------------------------------------------------------------- shift folders and files

def shift_folders():
    out = []
    for p in glob.glob(P("20??-??-??")):
        if os.path.isdir(p) and day_of(os.path.basename(p)):
            out.append(os.path.basename(p))
    return sorted(out)


def data_dirs(date):
    """data/, then data/<sub>/ (a rerun), then run2/data/ and later runs. Order does not decide the
    winner: pull timestamps do."""
    base = P(date)
    dirs = []
    main = os.path.join(base, "data")
    if os.path.isdir(main):
        dirs.append(main)
        dirs += sorted(p for p in glob.glob(os.path.join(main, "*")) if os.path.isdir(p))
    runs = sorted(glob.glob(os.path.join(base, "run*", "data")),
                  key=lambda p: int(re.sub(r"\D", "", os.path.basename(os.path.dirname(p))) or 0))
    return dirs + [d for d in runs if os.path.isdir(d)]


def files_for(date, kind, store):
    pats = {"ga4": ["ga4_%s.json" % store],
            "ads": ["%s_campaign_daily_30d.txt" % store, "%s_campaign_daily_30d.json" % store],
            "crm": ["crm_mtd_%s.json" % store]}[kind]
    out = []
    for d in data_dirs(date):
        for pat in pats:
            p = os.path.join(d, pat)
            if os.path.isfile(p):
                out.append(p)
    return out


def shift_has_data(date):
    for s in STORES:
        for k in ("ga4", "ads", "crm"):
            if files_for(date, k, s):
                return True
    return False


# ---------------------------------------------------------------- pulls

def prelim_days_for(days, pulled, flag=None, target=None):
    """A day is preliminary when the pull ran within a day of the day ending (the 1 AM rule).
    gdata.py's own target_preliminary flag wins when the file carries it."""
    if flag is True and target:
        return {target}
    if flag is False:
        return set()
    if pulled is None or pulled == dt.datetime.min:
        return {max(days)} if days else set()
    return {d for d in days if (pulled.date() - dt.date.fromisoformat(d)).days <= 1}


def load_ga4_pull(path):
    d = load_json(path)
    if not isinstance(d, dict):
        return None
    rows = d.get("channel_daily_last7")
    if not isinstance(rows, list) or not rows:
        return {"path": path, "error": "channel_daily_last7 empty or missing (%s)" %
                "; ".join(str(e)[:120] for e in (d.get("errors") or [])[:2]) or "no rows"}
    days = {}
    for r in rows:
        day = day_of(r.get("date"))
        if not day:
            continue
        rec = days.setdefault(day, {"total": {m: 0 for m in GA4_METRICS}, "names": {}})
        ch = r.get("sessionDefaultChannelGroup") or "(other)"
        n = rec["names"].setdefault(ch, {m: 0 for m in GA4_METRICS})
        for m in GA4_METRICS:
            v = num(r.get(m)) or 0
            rec["total"][m] += v
            n[m] += v
    pulled = parse_ts(d.get("pulled_at")) or mtime(path)
    target = day_of(d.get("target_date")) or (max(days) if days else None)
    return {"path": path, "pulled_at": pulled, "target": target, "days": days,
            "prelim": prelim_days_for(days, pulled, d.get("target_preliminary"), target)}


ADS_HEAD = re.compile(r"saved by ledgers\.py ads-dump (\S+), export last_run (.*?)(?: STALE| \(|\s*===)")


def load_ads_pull(path):
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return None
    head = text.split("\n", 1)[0] if text.startswith("===") else ""
    i = text.find("[")
    try:
        arr = json.JSONDecoder().raw_decode(text[i:])[0] if i >= 0 else []
    except ValueError:
        return {"path": path, "error": "not a JSON array after the header"}
    if not arr or not isinstance(arr[0], list):
        return {"path": path, "error": "no header row"}
    cols = arr[0]
    m = ADS_HEAD.search(head)
    saved = parse_ts(m.group(1)) if m else None
    last_run = parse_ts(m.group(2)) if m else None
    pulled = last_run or saved or mtime(path)
    days, names, latest = {}, {}, {}
    for r in arr[1:]:
        if not isinstance(r, list):
            continue
        row = dict(zip(cols, r))
        day = day_of(row.get("segments_date"))
        if not day:
            continue
        cid = str(row.get("campaign_id") or row.get("campaign_name") or "?")
        names[cid] = row.get("campaign_name") or cid
        if day >= latest.get(cid, ("", {}))[0]:
            latest[cid] = (day, row)
        rec = days.setdefault(day, {"total": {m2: 0 for m2 in ADS_METRICS}, "names": {}})
        n = rec["names"].setdefault(cid, {m2: 0 for m2 in ADS_METRICS})
        vals = {"clicks": num(row.get("metrics_clicks")) or 0,
                "cost": float(num(row.get("metrics_cost")) or 0),
                "conversions": float(num(row.get("metrics_conversions")) or 0)}
        for m2 in ADS_METRICS:
            rec["total"][m2] += vals[m2]
            n[m2] += vals[m2]
    settings = {cid: {"status": row.get("campaign_status"), "budget": num(row.get("campaignBudget_amount"))}
                for cid, (_, row) in latest.items()}
    return {"path": path, "pulled_at": pulled, "saved_at": saved, "last_run": last_run,
            "stale": "STALE" in head, "days": days, "names_map": names, "settings": settings,
            "prelim": prelim_days_for(days, pulled)}


def merge_pulls(pulls):
    """Latest pull wins per day. Returns a view: days, prelim, files, newest, last_complete."""
    good = [p for p in pulls if p and not p.get("error")]
    errors = [{"file": rel(p["path"]), "error": p["error"]} for p in pulls if p and p.get("error")]
    if not good:
        return {"errors": errors} if errors else None
    good.sort(key=lambda p: (p["pulled_at"], mtime(p["path"])))
    days, prelim, src, names_map, settings = {}, set(), {}, {}, {}
    for p in good:
        for day, rec in p["days"].items():
            days[day] = rec
            src[day] = p
            if day in p["prelim"]:
                prelim.add(day)
            else:
                prelim.discard(day)
        names_map.update(p.get("names_map") or {})
        settings.update(p.get("settings") or {})
    newest = max(days) if days else None
    complete = [d for d in days if d not in prelim]
    last = good[-1]
    view = {"days": days, "prelim": prelim, "newest": newest,
            "last_complete": max(complete) if complete else None,
            "files": [rel(p["path"]) for p in good], "file": rel(last["path"]),
            "pulled_at": last["pulled_at"].isoformat(timespec="seconds"),
            "day_file": {d: rel(p["path"]) for d, p in src.items()},
            "names_map": names_map, "settings": settings, "errors": errors,
            "stale": bool(last.get("stale"))}
    if last.get("last_run"):
        view["export_last_run"] = last["last_run"].isoformat(timespec="seconds")
    return view


def source_view(date, kind, store):
    loader = {"ga4": load_ga4_pull, "ads": load_ads_pull}[kind]
    paths = files_for(date, kind, store)
    if not paths:
        return None
    return merge_pulls([loader(p) for p in paths])


# ---------------------------------------------------------------- CRM snapshots

def crm_corrections():
    d = load_json(P("ledgers", "crm-corrections.json"), {}) or {}
    return d.get("corrections") or []


def crm_normalize(d, shift, store):
    out = {"crm": d.get("crm"), "report": d.get("report"), "period_start": d.get("period_start"),
           "period_end": d.get("period_end"), "generated_at": d.get("generated_at"),
           "headline": {}, "by_source": {}}
    if not out["period_end"]:
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", str(d.get("date_range", "")))
        if len(dates) >= 2:
            out["period_start"], out["period_end"] = dates[0], dates[1]
    t = d.get("totals") or {}
    if d.get("schema") == "crm_mtd.v1" or "headline" in d:
        h = d.get("headline") or {}
        out["headline"] = {k: num(h.get(k)) for k in CRM_METRICS}
        for r in d.get("by_source") or []:
            out["by_source"][str(r.get("source"))] = {k: num(r.get(k)) for k in CRM_METRICS}
            out.setdefault("vendor_status", {})[str(r.get("source"))] = r.get("vendor_status")
    elif "by_source" in d:  # VinSolutions Lead Source ROI, 2026-09-22
        keys = {"leads": "total_leads", "good_leads": "good_leads", "appointments": "appts_set",
                "shows": "appts_shown", "sold": "sold_from_leads", "cost": "total_cost"}
        out["headline"] = {k: num(t.get(v)) for k, v in keys.items()}
        for r in d["by_source"]:
            out["by_source"][str(r.get("source"))] = {k: num(r.get(v)) for k, v in keys.items()}
    elif "by_category" in d:  # MomentumCRM KPI Summary, 2026-09-22
        keys = {"leads": "prospects_created", "appointments": "appts_created", "shows": "shows",
                "sold": "sold_dms"}
        out["headline"] = {k: num(t.get(keys[k])) if k in keys else None for k in CRM_METRICS}
        for r in d["by_category"]:
            out["by_source"][str(r.get("category"))] = {k: num(r.get(keys[k])) if k in keys else None
                                                        for k in CRM_METRICS}
    for c in crm_corrections():
        if c.get("shift") == shift and str(c.get("store", "")).upper() == store:
            for name, r in out["by_source"].items():
                if name.lower() == str(c.get("source", "")).lower() and c.get("field") in r:
                    r[c["field"]] = num(c.get("value"))
    return out


def crm_view(date, store):
    best = None
    for p in files_for(date, "crm", store):
        d = load_json(p)
        if not isinstance(d, dict):
            continue
        snap = crm_normalize(d, date, store)
        if not day_of(snap.get("period_end")):
            continue
        key = (snap["period_end"], parse_ts(snap.get("generated_at")) or mtime(p), mtime(p))
        if best is None or key > best[0]:
            snap["file"] = rel(p)
            best = (key, snap)
    return best[1] if best else None


# ---------------------------------------------------------------- baselines and history

def baseline(kind, store, tonight, start):
    """Newest shift on or before `start` (and before tonight) that holds this store's file."""
    for shift in reversed(shift_folders()):
        if shift >= tonight or shift > start or days_between(shift, tonight) > BASELINE_DAYS:
            continue
        v = crm_view(shift, store) if kind == "crm" else source_view(shift, kind, store)
        if v and (kind == "crm" or v.get("days")):
            return shift, v
    return None, None


class History(object):
    """Complete-day values across recent shift pulls, for same-weekday-last-week lookups."""

    def __init__(self, tonight):
        self.tonight = tonight
        self.cache = {}

    def index(self, kind, store):
        key = (kind, store)
        if key in self.cache:
            return self.cache[key]
        loader = {"ga4": load_ga4_pull, "ads": load_ads_pull}[kind]
        best = {}
        for shift in shift_folders():
            if shift > self.tonight or days_between(shift, self.tonight) > HISTORY_DAYS:
                continue
            for p in files_for(shift, kind, store):
                pull = loader(p)
                if not pull or pull.get("error"):
                    continue
                for day, rec in pull["days"].items():
                    final = day not in pull["prelim"]
                    rank = (final, pull["pulled_at"])
                    if day not in best or rank > best[day][0]:
                        best[day] = (rank, rec, rel(p), not final)
        self.cache[key] = best
        return best

    def get(self, kind, store, view, day):
        """(record, file, preliminary) for a day: tonight's view first, then the newest complete pull."""
        if view and day in view["days"] and day not in view["prelim"]:
            return view["days"][day], view["day_file"][day], False
        hit = self.index(kind, store).get(day)
        if hit:
            return hit[1], hit[2], hit[3]
        if view and day in view["days"]:
            return view["days"][day], view["day_file"][day], True
        return None, None, None


# ---------------------------------------------------------------- comparisons

def restated(before, after, metric):
    if before is None or after is None:
        return None
    change = after - before
    if abs(change) < MIN_ABS[metric] - 1e-9:
        return None
    pct = pct_of(before, after)
    if pct is not None and abs(pct) < RESTATE_PCT:
        return None
    return change, pct


def daily_restatements(prev, cur, metrics, kind):
    """Same day, last night's pull vs tonight's. For Ads, totals use campaigns present in both exports;
    a campaign that is in only one export on overlapping days is an export change, listed separately."""
    out, export_changes = [], []
    common = sorted(set(prev["days"]) & set(cur["days"]))
    only_prev, only_cur = set(), set()
    if kind == "ads":
        pn = {n for d in common for n in prev["days"][d]["names"]}
        cn = {n for d in common for n in cur["days"][d]["names"]}
        all_prev = {n for d in prev["days"].values() for n in d["names"]}
        all_cur = {n for d in cur["days"].values() for n in d["names"]}
        only_prev = {n for n in pn if n not in all_cur}
        only_cur = {n for n in cn if n not in all_prev}
        for n in sorted(only_prev):
            export_changes.append({"campaign": prev["names_map"].get(n, n), "campaign_id": n,
                                   "change": "in last night's export, missing from tonight's",
                                   "days": [d for d in common if n in prev["days"][d]["names"]]})
        for n in sorted(only_cur):
            export_changes.append({"campaign": cur["names_map"].get(n, n), "campaign_id": n,
                                   "change": "in tonight's export on days last night's did not carry it",
                                   "days": [d for d in common if n in cur["days"][d]["names"]]})
    for day in common:
        was_prelim = day in prev["prelim"]
        a, b = prev["days"][day], cur["days"][day]
        names = sorted(set(a["names"]) | set(b["names"]))
        names = [n for n in names if n not in only_prev and n not in only_cur]
        for m in metrics:
            if kind == "ads":
                before = sum(a["names"].get(n, {}).get(m, 0) for n in names)
                after = sum(b["names"].get(n, {}).get(m, 0) for n in names)
            else:
                before, after = a["total"][m], b["total"][m]
            hit = restated(before, after, m)
            if hit:
                out.append(_restatement(kind, day, "total", None, m, before, after, hit, was_prelim))
            for n in names:
                before = a["names"].get(n, {}).get(m, 0)
                after = b["names"].get(n, {}).get(m, 0)
                hit = restated(before, after, m)
                if hit:
                    label = (cur["names_map"].get(n) or prev["names_map"].get(n) or n) if kind == "ads" else n
                    out.append(_restatement(kind, day, "campaign" if kind == "ads" else "channel", label, m,
                                            before, after, hit, was_prelim))
    return out, export_changes


def _restatement(kind, day, scope, name, metric, before, after, hit, was_prelim):
    change, pct = hit
    r = {"source": kind, "day": day, "weekday": wd(day), "scope": scope, "name": name, "metric": metric,
         "before": tidy(before), "after": tidy(after), "change": tidy(change), "pct": pct,
         "kind": "filled in" if was_prelim else "changed"}
    if kind == "ads" and metric in ADS_LAGGING:
        r["note"] = "conversion lag: conversions land on the click date for days"
    if kind == "ga4" and name == "Unassigned" and change < 0:
        r["note"] = "GA4 moves Unassigned sessions into their real channels as it finishes processing"
    if not was_prelim and change < 0 and not (kind == "ga4" and name == "Unassigned"):
        r["note"] = (r.get("note", "") + "; " if r.get("note") else "") + \
            "went DOWN on a day last night called complete: find out why"
    return r


def metric_delta(value, dod, wow, metric, lagging=False):
    e = {"value": tidy(value), "dod_value": tidy(dod), "wow_value": tidy(wow)}
    for tag, base in (("dod", dod), ("wow", wow)):
        if base is None or value is None:
            e[tag + "_change"], e[tag + "_pct"] = None, None
        else:
            e[tag + "_change"], e[tag + "_pct"] = tidy(value - base), pct_of(base, value)
    ch = e["wow_change"]
    e["direction"] = None if ch is None else "up" if ch > 0 else "down" if ch < 0 else "flat"
    pct = e["wow_pct"]
    e["flag"] = bool(not lagging and pct is not None and abs(pct) >= FLAG_PCT
                     and abs(ch) >= MIN_ABS[metric] and max(value, wow) >= FLAG_MIN_BASE[metric])
    if lagging:
        e["lagging"] = True
    return e


def day_block(kind, store, view, history, day, metrics):
    """Totals and per channel or campaign for one complete day: vs the day before, vs the same weekday
    last week."""
    rec, rec_file, _ = history.get(kind, store, view, day)
    if not rec:
        return None
    dod_day, wow_day = shift_day(day, -1), shift_day(day, -7)
    dod, dod_file, dod_pre = history.get(kind, store, view, dod_day)
    wow, wow_file, wow_pre = history.get(kind, store, view, wow_day)
    lag = ADS_LAGGING if kind == "ads" else ()
    out = {"day": day, "weekday": wd(day), "file": rec_file,
           "dod_day": dod_day, "dod_file": dod_file, "dod_preliminary": bool(dod_pre),
           "wow_day": wow_day, "wow_file": wow_file, "wow_preliminary": bool(wow_pre),
           "total": {}, "names": [], "flags": []}
    if not dod:
        out["missing"] = "no pull holds %s" % dod_day
    if not wow:
        out["missing"] = (out.get("missing", "") + "; " if out.get("missing") else "") + \
            "no pull within %d days holds %s (same weekday last week)" % (HISTORY_DAYS, wow_day)
    for m in metrics:
        out["total"][m] = metric_delta(rec["total"][m], dod["total"][m] if dod else None,
                                       wow["total"][m] if wow else None, m, m in lag)
    names = set(rec["names"]) | set((dod or {}).get("names", {})) | set((wow or {}).get("names", {}))
    nm = view.get("names_map") or {}
    for n in sorted(names):
        entry = {"name": nm.get(n, n) if kind == "ads" else n}
        if kind == "ads":
            entry["campaign_id"] = n
        for m in metrics:
            entry[m] = metric_delta(rec["names"].get(n, {}).get(m, 0),
                                    (dod["names"].get(n, {}).get(m, 0)) if dod else None,
                                    (wow["names"].get(n, {}).get(m, 0)) if wow else None, m, m in lag)
        if not any(entry[m][k] for m in metrics for k in ("value", "dod_value", "wow_value")):
            continue  # all zero on all three days: nothing to say, keeps the JSON small
        for m in metrics:
            if entry[m]["flag"]:
                out["flags"].append({"name": entry["name"], "metric": m, "value": entry[m]["value"],
                                     "wow_value": entry[m]["wow_value"], "change": entry[m]["wow_change"],
                                     "pct": entry[m]["wow_pct"], "direction": entry[m]["direction"]})
        out["names"].append(entry)
    for m in metrics:
        t = out["total"][m]
        if t["flag"]:
            out["flags"].insert(0, {"name": "store total", "metric": m, "value": t["value"],
                                    "wow_value": t["wow_value"], "change": t["wow_change"], "pct": t["wow_pct"],
                                    "direction": t["direction"]})
    out["flags"].sort(key=lambda f: (f["name"] != "store total", -abs(f["change"] or 0)))
    return out


def source_section(kind, store, tonight, start, history):
    metrics = GA4_METRICS if kind == "ga4" else ADS_METRICS
    cur = source_view(tonight, kind, store)
    sec = {"tonight_file": None, "baseline_shift": None, "baseline_file": None}
    if not cur or not cur.get("days"):
        sec["missing"] = "no %s file tonight%s" % (
            "GA4" if kind == "ga4" else "Ads export",
            " (" + "; ".join(e["error"] for e in (cur or {}).get("errors", [])) + ")" if cur else "")
        return sec
    sec.update({"tonight_file": cur["file"], "tonight_files": cur["files"], "pulled_at": cur["pulled_at"],
                "newest_day": cur["newest"], "last_complete_day": cur["last_complete"],
                "preliminary_days": sorted(cur["prelim"])})
    if cur.get("export_last_run"):
        sec["export_last_run"] = cur["export_last_run"]
    if cur.get("stale"):
        sec["stale"] = "tonight's Ads export is older than 26 hours: its newest day is not yesterday"
    if cur["errors"]:
        sec["pull_errors"] = cur["errors"]
    bshift, prev = baseline(kind, store, tonight, start)
    if prev:
        sec.update({"baseline_shift": bshift, "baseline_file": prev["file"],
                    "baseline_pulled_at": prev["pulled_at"], "baseline_last_complete_day": prev["last_complete"],
                    "baseline_preliminary_days": sorted(prev["prelim"])})
        rs, ex = daily_restatements(prev, cur, metrics, kind)
        rs.sort(key=lambda r: (r["scope"] != "total", r["kind"] != "filled in", r["day"],
                               -abs(r["change"] or 0)))
        sec["restatements"] = rs
        if ex:
            sec["export_changes"] = ex
        if kind == "ads":
            changes = []
            for cid, s in sorted(cur["settings"].items()):
                p = prev["settings"].get(cid)
                if not p:
                    continue
                name = cur["names_map"].get(cid, cid)
                if p.get("status") != s.get("status"):
                    changes.append({"campaign": name, "campaign_id": cid, "field": "status",
                                    "before": p.get("status"), "after": s.get("status")})
                if p.get("budget") is not None and s.get("budget") is not None and p["budget"] != s["budget"]:
                    changes.append({"campaign": name, "campaign_id": cid, "field": "daily budget",
                                    "before": p["budget"], "after": s["budget"]})
            if changes:
                sec["settings_changes"] = changes
        # how much last night's preliminary day(s) filled in: calibrates tonight's preliminary number
        fills = []
        for day in sorted(prev["prelim"]):
            if day in cur["days"] and day not in cur["prelim"]:
                f = {"day": day, "weekday": wd(day)}
                for m in metrics:
                    b, a = prev["days"][day]["total"][m], cur["days"][day]["total"][m]
                    f[m] = {"before": tidy(b), "after": tidy(a), "pct": pct_of(b, a)}
                fills.append(f)
        sec["prior_preliminary_filled"] = fills
    else:
        sec["baseline_missing"] = "no earlier shift within %d days holds this file" % BASELINE_DAYS
        sec["restatements"] = []
    pre = []
    for day in sorted(cur["prelim"]):
        pre.append(dict({"day": day, "weekday": wd(day)},
                        **{m: tidy(cur["days"][day]["total"][m]) for m in metrics}))
    sec["preliminary"] = pre
    lcd = cur["last_complete"]
    sec["last_complete"] = day_block(kind, store, cur, history, lcd, metrics) if lcd else None
    # days that became complete since the baseline's last complete day (Monday: Thu, Fri, Sat)
    newly = []
    if prev and lcd and prev.get("last_complete"):
        d = shift_day(prev["last_complete"], 1)
        while d <= lcd:
            if d in cur["days"] and d not in cur["prelim"]:
                rec = cur["days"][d]
                wow, wow_file, _ = history.get(kind, store, cur, shift_day(d, -7))
                entry = {"day": d, "weekday": wd(d), "wow_day": shift_day(d, -7), "wow_file": wow_file}
                for m in metrics:
                    entry[m] = metric_delta(rec["total"][m], None, wow["total"][m] if wow else None, m,
                                            kind == "ads" and m in ADS_LAGGING)
                newly.append(entry)
            d = shift_day(d, 1)
    sec["newly_complete_days"] = newly
    return sec


def crm_section(store, tonight, start):
    cur = crm_view(tonight, store)
    if not cur:
        return None
    sec = {"tonight_file": cur["file"], "crm": cur.get("crm"), "report": cur.get("report"),
           "period_start": cur["period_start"], "period_end": cur["period_end"],
           "generated_at": cur.get("generated_at"), "mtd": {k: tidy(v) for k, v in cur["headline"].items()},
           "preliminary_day": cur["period_end"],
           "preliminary_note": "the report was generated minutes after midnight; its last day can still move "
                               "(sold posts from the DMS late). Tomorrow's pull shows it as a restatement if so."}
    bshift, prev = baseline("crm", store, tonight, start)
    if not prev:
        sec["baseline_missing"] = "no earlier CRM snapshot within %d days" % BASELINE_DAYS
        sec["restatements"] = []
        return sec
    sec.update({"baseline_shift": bshift, "baseline_file": prev["file"], "baseline_period_end": prev["period_end"]})
    rs = []
    if cur["period_start"] != prev["period_start"] and cur["period_start"] > prev["period_end"]:
        span = (cur["period_start"], cur["period_end"])
        sec["month_rollover"] = ("new month: tonight's MTD starts %s, so the increment is tonight's whole MTD. "
                                 "Last night's file (through %s) was the last read of the old month."
                                 % (cur["period_start"], prev["period_end"]))
        gap = days_between(prev["period_end"], cur["period_start"]) - 1
        if gap > 0:
            sec["uncovered_days"] = [shift_day(prev["period_end"], i + 1) for i in range(gap)]
        inc = {k: tidy(cur["headline"].get(k)) for k in CRM_METRICS}
        src_inc = {n: {k: tidy(v.get(k)) for k in CRM_METRICS} for n, v in cur["by_source"].items()}
    elif cur["period_end"] < prev["period_end"]:
        sec["problem"] = ("tonight's report covers through %s but last night's covered through %s: wrong date "
                          "range on tonight's export? No increment computed." % (cur["period_end"], prev["period_end"]))
        sec["restatements"] = []
        return sec
    else:
        span = (shift_day(prev["period_end"], 1), cur["period_end"]) if cur["period_end"] > prev["period_end"] else None
        inc, src_inc = {}, {}
        for k in CRM_METRICS:
            a, b = prev["headline"].get(k), cur["headline"].get(k)
            inc[k] = tidy(b - a) if a is not None and b is not None else None
        for n in sorted(set(prev["by_source"]) | set(cur["by_source"])):
            pv, cv = prev["by_source"].get(n), cur["by_source"].get(n)
            src_inc[n] = {}
            for k in CRM_METRICS:
                a = (pv or {}).get(k)
                b = (cv or {}).get(k)
                if cv is None and a:
                    b = 0
                src_inc[n][k] = tidy(b - a) if a is not None and b is not None else None
        same = span is None
        # restatements: MTD only grows, so any decrease is a restatement; same coverage, any change is one
        for k in CRM_METRICS:
            v = inc.get(k)
            mk = "crm_cost" if k == "cost" else k
            if v is not None and ((v < 0 and abs(v) >= MIN_ABS[mk]) or (same and abs(v) >= MIN_ABS[mk])):
                rs.append({"source": "crm", "scope": "total", "name": None, "metric": k,
                           "before": tidy(prev["headline"][k]), "after": tidy(cur["headline"][k]), "change": v,
                           "through": prev["period_end"],
                           "why": "same days, different number" if same else "month to date went down"})
        for n, d in src_inc.items():
            for k in ("leads", "sold", "cost"):
                v = d.get(k)
                mk = "crm_cost" if k == "cost" else k
                if v is not None and ((v < 0 and abs(v) >= MIN_ABS[mk]) or (same and abs(v) >= MIN_ABS[mk])):
                    missing = n not in cur["by_source"]
                    rs.append({"source": "crm", "scope": "source", "name": n, "metric": k,
                               "before": tidy(prev["by_source"][n].get(k)),
                               "after": 0 if missing else tidy(cur["by_source"][n].get(k)), "change": v,
                               "through": prev["period_end"],
                               "why": "source missing from tonight's report" if missing else
                               ("same days, different number" if same else "month to date went down")})
        if same:
            sec["same_coverage"] = "both reports run through %s: no new day tonight" % cur["period_end"]
    sec["restatements"] = rs
    if span:
        ndays = days_between(span[0], span[1]) + 1
        sec["increment_days"] = {"from": span[0], "to": span[1], "days": ndays,
                                 "label": wd(span[0]) if ndays == 1 else "%s to %s" % (wd(span[0]), wd(span[1]))}
        sec["increment"] = inc
        if ndays > 1:
            sec["increment_per_day"] = {k: (round(v / float(ndays), 1) if isinstance(v, (int, float)) else None)
                                        for k, v in inc.items()}
        movers = [dict({"source": n}, **d) for n, d in src_inc.items() if d.get("leads")]
        movers.sort(key=lambda r: -abs(r["leads"] or 0))
        sec["by_source_increment"] = movers
        vs = dict(cur.get("vendor_status") or {})
        # Drew's rulings land in vendor-watch.json (status ignored or cut), sometimes after tonight's CRM file
        # was written (R3 on 2026-09-28): the ledger wins, so an ignored vendor never reads "unconfirmed".
        for vrow in (load_json(P("ledgers", "vendor-watch.json"), {}) or {}).get("rows") or []:
            if vrow.get("store") == store and vrow.get("status") in ("ignored", "cut"):
                for n in src_inc:
                    if n.strip().lower() == str(vrow.get("vendor", "")).strip().lower():
                        vs[n] = "ignored-per-drew" if vrow["status"] == "ignored" else "cut-per-drew"
        billing = [{"source": n, "cost_increment": d["cost"], "lead_increment": d.get("leads") or 0,
                    "vendor_status": vs.get(n)}
                   for n, d in src_inc.items()
                   if isinstance(d.get("cost"), (int, float)) and d["cost"] >= MIN_ABS["crm_cost"]
                   and not d.get("leads")]
        if billing:
            sec["billing_without_new_leads"] = sorted(billing, key=lambda r: -r["cost_increment"])
    return sec


# ---------------------------------------------------------------- build

def build(date, prev_date=None):
    start = prev_date
    if not start:
        earlier = [s for s in shift_folders() if s < date and shift_has_data(s)]
        start = earlier[-1] if earlier else None
    history = History(date)
    out = {"schema": "deltas.v1", "date": date, "prev_date": start,
           "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
           "gap_days": days_between(start, date) if start else None,
           "rules": {"restatement_pct": RESTATE_PCT, "min_abs": MIN_ABS, "flag_pct": FLAG_PCT,
                     "flag_min_base": FLAG_MIN_BASE, "flag_basis": "last complete day vs the same weekday last week",
                     "preliminary": "the newest day in every pull; quoted as preliminary, never flagged",
                     "ads_lagging": list(ADS_LAGGING),
                     "crm": "increment = tonight's MTD minus last night's; any MTD decrease is a restatement"},
           "stores": {}, "restatements": [], "flags": [], "missing": []}
    for store in STORES:
        st = {}
        for kind in ("ga4", "ads"):
            sec = source_section(kind, store, date, start or "0000-00-00", history)
            if kind == "ads" and not sec.get("tonight_file") and not files_for(date, "ads", store) \
                    and not (start and files_for(start, "ads", store)):
                continue  # store has no Google Ads export (SBMW, NCBMW): nothing to say
            st[kind] = sec
            if sec.get("missing"):
                out["missing"].append("%s %s: %s" % (store, kind.upper(), sec["missing"]))
            for r in sec.get("restatements", []):
                out["restatements"].append(dict({"store": store}, **r))
            lc = sec.get("last_complete") or {}
            for f in lc.get("flags", []):
                out["flags"].append(dict({"store": store, "source": kind, "day": lc["day"]}, **f))
        crm = crm_section(store, date, start or "0000-00-00")
        if crm:
            st["crm"] = crm
            for r in crm.get("restatements", []):
                out["restatements"].append(dict({"store": store}, **r))
        elif start and files_for(start, "crm", store):
            st["crm"] = {"missing": "no crm_mtd_%s.json tonight yet (last night had one)" % store}
            out["missing"].append("%s CRM: no snapshot tonight yet" % store)
        out["stores"][store] = st
    return out


# ---------------------------------------------------------------- markdown

def _r_line(r):
    what = LABEL.get(r["metric"], r["metric"])
    who = "" if r["scope"] == "total" else "%s " % r["name"]
    tail = "was preliminary %s" % NIGHT if r["kind"] == "filled in" else "a day %s called complete" % NIGHT
    return "%s%s %s -> %s (%s; %s)" % (who, what, fmt(r["before"], r["metric"]), fmt(r["after"], r["metric"]),
                                       fmt_change(r["change"], r["pct"], r["metric"]), tail)


def _restatement_lines(sec, src):
    rs = list(sec.get("restatements") or [])
    lines = []
    # Ads conversions that grew on days last night already called complete are normal conversion lag:
    # one summary line, not a line per day. A DOWN move stays itemized.
    lag = [r for r in rs if r["source"] == "ads" and r["metric"] in ADS_LAGGING and r["kind"] == "changed"
           and r["change"] > 0]
    lag_down = [r for r in rs if r["source"] == "ads" and r["metric"] in ADS_LAGGING and r["kind"] == "changed"
                and r["change"] < 0]
    rs = [r for r in rs if r not in lag and r not in lag_down]
    by_day = {}
    for r in rs:
        by_day.setdefault(r["day"], []).append(r)
    for day in sorted(by_day, reverse=True):
        items = by_day[day]
        totals = [r for r in items if r["scope"] == "total"]
        detail = [r for r in items if r["scope"] != "total"]
        # traffic lines first (sessions, clicks), biggest move first; Organic Search always makes the cut
        detail.sort(key=lambda r: (r["metric"] not in ("sessions", "clicks"), -abs(r["change"] or 0)))
        org = [r for r in detail if r["name"] == "Organic Search" and r["metric"] == "sessions"]
        if org and org[0] not in detail[:MD_LINES + 1]:
            detail.remove(org[0])
            detail.insert(MD_LINES, org[0])
        head = "%s %s: " % (src, wd(day))
        if totals:
            head += "; ".join(_r_line(r) for r in totals)
        else:
            head += "store total within 10%%, but %d %s line%s moved (%s)" % (
                len(detail), "channel" if src == "GA4" else "campaign", "" if len(detail) == 1 else "s",
                "was preliminary %s" % NIGHT if detail[0]["kind"] == "filled in" else
                "a day %s called complete" % NIGHT)
        lines.append("- " + head)
        if detail:
            shown = "; ".join("%s %s %s -> %s (%s)" % (r["name"], LABEL.get(r["metric"], r["metric"]),
                                                       fmt(r["before"], r["metric"]), fmt(r["after"], r["metric"]),
                                                       fmt_change(r["change"], r["pct"], r["metric"]))
                              for r in detail[:MD_LINES + 1])
            more = len(detail) - (MD_LINES + 1)
            lines.append("  - %s%s" % (shown, "; +%d more in deltas.json" % more if more > 0 else ""))
        if any(r["source"] == "ga4" and r["name"] == "Unassigned" and r["change"] < 0 for r in items):
            lines.append("  - Unassigned draining into real channels is GA4 finishing its processing, "
                         "not a traffic change.")
        downs = [r for r in items if r["kind"] == "changed" and r["change"] < 0
                 and not (r["source"] == "ga4" and r["name"] == "Unassigned")]
        if downs:
            lines.append("  - Went DOWN on a day already called complete: find out why before quoting it.")
    def group(items):
        days = sorted({r["day"] for r in items})
        total = 0.0
        for d in days:
            tots = [r["change"] for r in items if r["day"] == d and r["scope"] == "total"]
            total += sum(tots) if tots else sum(r["change"] for r in items if r["day"] == d)
        camp = {}
        for r in items:
            if r["scope"] != "total":
                camp[r["name"]] = camp.get(r["name"], 0) + r["change"]
        top = max(camp, key=lambda k: abs(camp[k])) if camp else None
        span = wd(days[0]) if len(days) == 1 else "%s to %s" % (wd(days[0]), wd(days[-1]))
        return days, total, span, (", mostly %s" % top if top else "")
    if lag_down:
        days, total, span, top = group(lag_down)
        lines.insert(0, "- Ads conversions went DOWN on %d day%s %s called complete (%s), %s in all%s: conversions "
                        "were removed or a conversion action changed. Find out why (change digest) before quoting "
                        "those days." % (len(days), "" if len(days) == 1 else "s", NIGHT, span, fmt(total), top))
    if lag:
        days, total, span, top = group(lag)
        lines.append("- Ads conversions kept landing on %d earlier day%s (%s), +%s in all%s: normal "
                     "conversion lag, so the most recent days' conversions still read low." % (
                         len(days), "" if len(days) == 1 else "s", span, fmt(total), top))
    if len(lines) > 12:
        lines = lines[:12] + ["- +%d more restatement lines in deltas.json" % (len(lines) - 12)]
    return lines


def _delta_phrase(e, metric, day_label_dod, day_label_wow):
    parts = []
    if e["dod_value"] is not None:
        parts.append("vs %s %s (%s)" % (day_label_dod, fmt(e["dod_value"], metric),
                                        fmt_change(e["dod_change"], e["dod_pct"], metric)))
    if e["wow_value"] is not None:
        parts.append("vs %s %s (%s)" % (day_label_wow, fmt(e["wow_value"], metric),
                                        fmt_change(e["wow_change"], e["wow_pct"], metric)))
    return "%s %s%s" % (fmt(e["value"], metric), lab(metric, e["value"]),
                        (", " + ", ".join(parts)) if parts else "")


def _fallback_note(sec, prev_date, what):
    b = sec.get("baseline_shift")
    if b and prev_date and b != prev_date:
        return "- %s baseline is the %s shift: the %s shift saved no %s file." % (what, b, prev_date, what)
    return None


def _source_md(sec, src, metrics, prev_date=None):
    lines = []
    if sec.get("missing"):
        return ["- %s: %s." % (src, sec["missing"])]
    note = _fallback_note(sec, prev_date, src)
    if note:
        lines.append(note)
    if sec.get("baseline_missing"):
        lines.append("- %s: %s, so nothing restated or compared to last night." % (src, sec["baseline_missing"]))
    if sec.get("stale"):
        lines.append("- %s: %s." % (src, sec["stale"]))
    for pre in sec.get("preliminary") or []:
        fill = ""
        for f in sec.get("prior_preliminary_filled") or []:
            m0 = metrics[0]
            pct = f[m0]["pct"]
            if pct is not None:
                fill = " %s preliminary %s read %s %s and reads %s tonight (%s%d%%)%s." % (
                    NIGHTS[0].upper() + NIGHTS[1:], f["weekday"], fmt(f[m0]["before"], m0),
                    lab(m0, f[m0]["before"]), fmt(f[m0]["after"], m0),
                    "+" if pct > 0 else "", round(pct), ", so expect this one to rise too" if pct >= 5 else "")
        lines.append("- %s preliminary %s: %s so far. Quote as preliminary, no trend call.%s" % (
            src, pre["weekday"], ", ".join("%s %s" % (fmt(pre[m], m), lab(m, pre[m])) for m in metrics), fill))
    lc = sec.get("last_complete")
    if lc:
        dl, wl = wd(lc["dod_day"]), wd(lc["wow_day"])
        body = "; ".join(_delta_phrase(lc["total"][m], m, dl, wl) +
                         (" (still landing, no flag)" if lc["total"][m].get("lagging") else "")
                         for m in metrics)
        lines.append("- %s last complete day %s: %s." % (src, lc["weekday"], body))
        if lc.get("dod_preliminary") or lc.get("wow_preliminary"):
            lines.append("  - Comparison day read from a preliminary pull only: treat the change as rough.")
        if lc.get("missing"):
            lines.append("  - Missing: %s." % lc["missing"])
        flags = lc.get("flags") or []
        if flags:
            shown = "; ".join("%s %s %s vs %s (%s, %s)" % (
                f["name"], LABEL.get(f["metric"], f["metric"]), fmt(f["value"], f["metric"]),
                fmt(f["wow_value"], f["metric"]), fmt_change(f["change"], f["pct"], f["metric"]), f["direction"])
                for f in flags[:MD_LINES + 1])
            more = len(flags) - (MD_LINES + 1)
            lines.append("  - Flags vs %s: %s%s" % (wl, shown, "; +%d more in deltas.json" % more if more > 0 else ""))
        else:
            lines.append("  - No flags vs %s (25%%+ same-weekday move)." % wl)
    newly = sec.get("newly_complete_days") or []
    if len(newly) > 1:
        m = metrics[0]
        lines.append("- %s newly complete since last shift: %s." % (src, "; ".join(
            "%s %s%s" % (n["weekday"], fmt(n[m]["value"], m),
                         " (vs %s %s, %s)" % (wd(n["wow_day"]), fmt(n[m]["wow_value"], m),
                                              fmt_change(n[m]["wow_change"], n[m]["wow_pct"], m))
                         if n[m]["wow_value"] is not None else "")
            for n in newly)))
    for c in sec.get("settings_changes") or []:
        lines.append("- Ads setting changed since %s: %s %s %s -> %s. Name who from the change digest "
                     "(data/changes_{STORE}.md), never guess." % (NIGHT, c["campaign"], c["field"], c["before"],
                                                                  c["after"]))
    for c in sec.get("export_changes") or []:
        lines.append("- Ads export change, not a restatement: %s %s." % (c["campaign"], c["change"]))
    return lines


def _crm_md(c, prev_date=None):
    if c.get("missing"):
        return ["- CRM: %s." % c["missing"]]
    lines = []
    note = _fallback_note(c, prev_date, "CRM")
    if note:
        lines.append(note)
    name = c.get("crm") or "CRM"
    if c.get("problem"):
        return ["- CRM (%s): %s" % (name, c["problem"])]
    mtd = c["mtd"]
    mtd_txt = "MTD through %s: %s leads, %s sold" % (wd(c["period_end"]), fmt(mtd.get("leads")), fmt(mtd.get("sold")))
    if c.get("baseline_missing"):
        return ["- CRM (%s): %s. %s; no increment." % (name, c["baseline_missing"], mtd_txt)]
    if c.get("same_coverage"):
        lines.append("- CRM (%s): %s. %s." % (name, c["same_coverage"], mtd_txt))
    elif c.get("increment"):
        inc, span = c["increment"], c["increment_days"]
        parts = ["%s%s %s" % ("+" if (inc.get(k) or 0) >= 0 else "", fmt(inc.get(k), k), lab(k, inc.get(k)))
                 for k in ("leads", "good_leads", "appointments", "shows", "sold") if inc.get(k) is not None]
        per = ""
        if span["days"] > 1 and c.get("increment_per_day", {}).get("leads") is not None:
            per = ", about %s leads a day" % fmt(c["increment_per_day"]["leads"])
        roll = " %s" % c["month_rollover"] if c.get("month_rollover") else ""
        lines.append("- CRM (%s): %s over %s (%d day%s%s). Report this increment, not the MTD. %s.%s" % (
            name, ", ".join(parts), span["label"], span["days"], "" if span["days"] == 1 else "s", per, mtd_txt, roll))
        movers = c.get("by_source_increment") or []
        if movers:
            lines.append("  - Biggest source moves: %s." % "; ".join(
                "%s %s%s" % (m["source"], "+" if m["leads"] > 0 else "", fmt(m["leads"]))
                for m in movers[:MD_LINES]))
        billing = c.get("billing_without_new_leads") or []
        if billing:
            lines.append("  - Cost grew with no new leads: %s." % "; ".join(
                "%s +%s%s" % (b["source"], fmt(b["cost_increment"], "cost"),
                              " (%s)" % b["vendor_status"].replace("-", " ")
                              if b.get("vendor_status") and b["vendor_status"] != "active" else "")
                for b in billing[:MD_LINES + 1]))
    for r in c.get("restatements") or []:
        who = "store total" if r["scope"] == "total" else r["name"]
        lines.insert(0, "- CRM restated: %s %s %s -> %s (%s%s) for days through %s: %s." % (
            who, LABEL.get(r["metric"], r["metric"]), fmt(r["before"], "crm_cost" if r["metric"] == "cost" else None),
            fmt(r["after"], "crm_cost" if r["metric"] == "cost" else None), "+" if r["change"] > 0 else "",
            fmt(r["change"], "crm_cost" if r["metric"] == "cost" else None), wd(r["through"]), r["why"]))
    return lines


def render_md(d):
    global NIGHT, NIGHTS
    if d.get("gap_days") and d["gap_days"] > 1:
        NIGHT, NIGHTS = "the last shift", "the last shift's"
    else:
        NIGHT, NIGHTS = "last night", "last night's"
    L = ["# Deltas: shift %s vs %s" % (d["date"], d["prev_date"] or "none"), ""]
    L.append("Written %s by deltas.py. Restated = the same day moved 10%%+ (and 20+ sessions, 5+ key events, "
             "5+ clicks, $10+, 1+ conversion or lead) since last night's pull. The newest day in every pull is "
             "preliminary: quote it as preliminary and never flag a trend from it. Flags use the last complete "
             "day vs the same weekday last week, 25%%+. A flag is a question, not a finding: check data/health.md "
             "first (a RED store's key events are a measurement problem, not demand), then the change digest."
             % d["generated_at"].replace("T", " ")[:16])
    L[-1] = L[-1].replace("since last night's pull", "since %s pull" % NIGHTS)
    if d.get("gap_days") and d["gap_days"] > 1:
        L.append("")
        L.append("Last shift was %s, %d days ago. The days in between became complete without a shift reading "
                 "them: see each store's 'newly complete' line and the CRM increment span." % (
                     wd(d["prev_date"]), d["gap_days"]))
    if not d["prev_date"]:
        L.append("")
        L.append("No earlier shift folder holds data: nothing to compare against tonight.")
    nre = len([r for r in d["restatements"]])
    L.append("")
    L.append("Tonight: %d restatement line%s, %d flag%s on the last complete day%s." % (
        nre, "" if nre == 1 else "s", len(d["flags"]), "" if len(d["flags"]) == 1 else "s",
        (", missing: " + "; ".join(d["missing"])) if d["missing"] else ""))
    for store, st in d["stores"].items():
        L.append("")
        L.append("## %s" % store)
        restated = []
        for kind, src in (("ga4", "GA4"), ("ads", "Ads")):
            if kind in st and not st[kind].get("missing"):
                restated += _restatement_lines(st[kind], src)
        crm = st.get("crm") or {}
        crm_lines = _crm_md(crm, d["prev_date"]) if crm else []
        crm_restated = [x for x in crm_lines if x.startswith("- CRM restated")]
        L.append("**Restated since %s**" % NIGHT + (" (baselines: %s)" % ", ".join(
            "%s %s" % (src, st[k]["baseline_shift"]) for k, src in (("ga4", "GA4"), ("ads", "Ads"), ("crm", "CRM"))
            if k in st and st[k].get("baseline_shift")) if st else ""))
        L += (restated + crm_restated) or ["- Nothing moved 10%%+ since %s." % NIGHT]
        L.append("**Tonight**")
        body = []
        if "ga4" in st:
            body += _source_md(st["ga4"], "GA4", GA4_METRICS, d["prev_date"])
        if "ads" in st:
            body += _source_md(st["ads"], "Ads", ADS_METRICS, d["prev_date"])
        body += [x for x in crm_lines if not x.startswith("- CRM restated")]
        L += body or ["- No data files for this store tonight."]
    L.append("")
    return "\n".join(L)


def summary_lines(d, jpath, mpath):
    out = ["deltas %s vs %s: %d restatement lines, %d flags, %d missing" % (
        d["date"], d["prev_date"] or "none", len(d["restatements"]), len(d["flags"]), len(d["missing"]))]
    for store, st in d["stores"].items():
        bits = []
        for kind, src in (("ga4", "GA4"), ("ads", "Ads")):
            sec = st.get(kind)
            if not sec:
                continue
            if sec.get("missing"):
                bits.append("%s missing" % src)
                continue
            tot = [r for r in sec.get("restatements", []) if r["scope"] == "total"]
            m0 = GA4_METRICS[0] if kind == "ga4" else ADS_METRICS[0]
            top = [r for r in tot if r["metric"] == m0][:2]
            if top:
                bits.append("%s restated %s" % (src, ", ".join("%s %s %s->%s" % (
                    wd(r["day"]), LABEL[r["metric"]], fmt(r["before"], r["metric"]), fmt(r["after"], r["metric"]))
                    for r in top)))
            elif sec.get("restatements"):
                bits.append("%s %d restated lines" % (src, len(sec["restatements"])))
            pre = sec.get("preliminary") or []
            if pre:
                bits.append("%s preliminary %s" % (src, pre[-1]["weekday"]))
            lc = sec.get("last_complete") or {}
            if lc.get("flags"):
                bits.append("%s %d flag%s on %s" % (src, len(lc["flags"]), "" if len(lc["flags"]) == 1 else "s",
                                                   lc["weekday"]))
        c = st.get("crm") or {}
        if c.get("increment"):
            bits.append("CRM %s%s leads, %s%s sold over %s" % (
                "+" if (c["increment"].get("leads") or 0) >= 0 else "", fmt(c["increment"].get("leads")),
                "+" if (c["increment"].get("sold") or 0) >= 0 else "", fmt(c["increment"].get("sold")),
                c["increment_days"]["label"]))
        if c.get("restatements"):
            bits.append("CRM %d restatements" % len(c["restatements"]))
        out.append("  %s: %s" % (store, "; ".join(bits) or "no data"))
    out.append("wrote %s and %s" % (rel(jpath), rel(mpath)))
    return out


def cmd_run(args):
    if not args.date:
        die("--date YYYY-MM-DD is required")
    date = iso(args.date)
    prev = iso(args.prev_date, "--prev-date") if args.prev_date else None
    if prev and prev >= date:
        die("--prev-date must be before --date")
    if not os.path.isdir(P(date)):
        die("no shift folder %s" % rel(P(date)))
    d = build(date, prev)
    out_dir = args.out or P(date, "data")
    jpath, mpath = os.path.join(out_dir, "deltas.json"), os.path.join(out_dir, "deltas.md")
    save_json(jpath, d)
    save_text(mpath, render_md(d))
    if not args.quiet:
        print("\n".join(summary_lines(d, jpath, mpath)))
    return 0 if d["prev_date"] else 2


# ---------------------------------------------------------------- selftest

def _ga4_file(path, target, pulled, rows, prelim=None):
    d = {"store": "X", "target_date": target, "pulled_at": pulled, "errors": [],
         "channel_daily_last7": [{"date": day.replace("-", ""), "sessionDefaultChannelGroup": ch,
                                  "sessions": s, "engagedSessions": 0, "keyEvents": k}
                                 for day, ch, s, k in rows]}
    if prelim is not None:
        d["target_preliminary"] = prelim
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(d, f)


def _ads_file(path, header, rows):
    cols = ["segments_date", "campaign_id", "campaign_name", "campaign_status", "campaign_advertisingChannelType",
            "campaignBudget_amount", "metrics_impressions", "metrics_clicks", "metrics_cost", "metrics_conversions"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write((header + "\n" if header else "") + json.dumps([cols] + [[str(x) for x in r] for r in rows], indent=0))


def _crm_file(path, start, end, leads, sold, by_source, cost=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"schema": "crm_mtd.v1", "store": "NOI", "crm": "VinSolutions", "period_start": start,
                   "period_end": end, "generated_at": end + "T00:25", "source_kind": "vendor",
                   "headline": {"leads": leads, "sold": sold, "good_leads": None, "appointments": None,
                                "shows": None, "cost": cost, "live_vendor_cost": None},
                   "by_source": [{"source": s, "leads": l, "sold": so, "cost": c} for s, l, so, c in by_source]}, f)


def cmd_selftest(_args):
    global ROOT
    tmp = tempfile.mkdtemp(prefix="deltas-selftest-")
    saved_root = ROOT
    ROOT = tmp
    fails = []

    def check(cond, what):
        if not cond:
            fails.append(what)
        print("  %s %s" % ("ok  " if cond else "FAIL", what))

    try:
        base = P()
        days = ["2026-09-%02d" % i for i in range(10, 26)]

        def rows_for(ds, over=None):
            out = []
            for day in ds:
                org, paid = 200, 400
                if day in (over or {}):
                    org, paid = over[day]
                out += [(day, "Organic Search", org, 10), (day, "Paid Social", paid, 0)]
            return out
        # 9/17 shift (for the same-weekday lookup): days 9/10..9/16, 9/16 preliminary
        _ga4_file(os.path.join(base, "2026-09-17", "data", "ga4_SBMW.json"), "2026-09-16", "2026-09-17T01:01:00",
                  rows_for(days[0:7]))
        # 9/18 shift: 9/11..9/17, so 9/16 is complete there (the 9/17 pull only had it as preliminary)
        _ga4_file(os.path.join(base, "2026-09-18", "data", "ga4_SBMW.json"), "2026-09-17", "2026-09-18T01:01:00",
                  rows_for(days[1:8]))
        # 9/24 shift: 9/17..9/23; 9/23 preliminary and low
        _ga4_file(os.path.join(base, "2026-09-24", "data", "ga4_SBMW.json"), "2026-09-23", "2026-09-24T01:01:00",
                  rows_for(days[7:14], {"2026-09-23": (96, 300)}))
        # 9/25 shift: 9/18..9/24; 9/23 filled in, 9/22 changed (complete day went down), 9/24 preliminary;
        # a rerun in data/rerun/ wins over data/ for the same shift
        _ga4_file(os.path.join(base, "2026-09-25", "data", "ga4_SBMW.json"), "2026-09-24", "2026-09-25T01:01:00",
                  rows_for(days[8:15], {"2026-09-23": (1, 1), "2026-09-24": (50, 100)}))
        _ga4_file(os.path.join(base, "2026-09-25", "data", "rerun", "ga4_SBMW.json"), "2026-09-24",
                  "2026-09-25T01:11:00",
                  rows_for(days[8:15], {"2026-09-23": (234, 400), "2026-09-22": (150, 400),
                                        "2026-09-24": (60, 120)}), prelim=True)
        # Ads: header-less file last night, headered tonight; conversions lag; status change; export change
        hdr = "=== NOI campaign_daily_30d, saved by ledgers.py ads-dump 2026-09-25T01:00:39, export last_run " \
              "2026-09-25 0:08:00 ==="
        _ads_file(os.path.join(base, "2026-09-24", "data", "NOI_campaign_daily_30d.txt"), None,
                  [("2026-09-22", "1", "PMAX", "ENABLED", "PMAX", 82, 100, 40, 50.0, 4),
                   ("2026-09-23", "1", "PMAX", "ENABLED", "PMAX", 82, 100, 30, 40.0, 2),
                   ("2026-09-23", "9", "Old", "PAUSED", "SEARCH", 10, 10, 8, 9.0, 0)])
        os.utime(os.path.join(base, "2026-09-24", "data", "NOI_campaign_daily_30d.txt"),
                 (dt.datetime(2026, 9, 24, 1, 0).timestamp(),) * 2)
        _ads_file(os.path.join(base, "2026-09-25", "data", "NOI_campaign_daily_30d.txt"), hdr,
                  [("2026-09-16", "1", "PMAX", "PAUSED", "PMAX", 90, 100, 20, 30.0, 3),
                   ("2026-09-22", "1", "PMAX", "PAUSED", "PMAX", 90, 100, 40, 50.0, 7),
                   ("2026-09-23", "1", "PMAX", "PAUSED", "PMAX", 90, 100, 41, 60.0, 5),
                   ("2026-09-24", "1", "PMAX", "PAUSED", "PMAX", 90, 100, 5, 9.0, 0)])
        # CRM: 9/24 through 9/23, 9/25 through 9/24 (+ a source that went down)
        _crm_file(os.path.join(base, "2026-09-24", "data", "crm_mtd_NOI.json"), "2026-09-01", "2026-09-23", 535, 55,
                  [("Web", 100, 10, 0), ("ACE", 0, 0, 4000), ("Cargurus", 60, 3, 2250)])
        _crm_file(os.path.join(base, "2026-09-25", "data", "crm_mtd_NOI.json"), "2026-09-01", "2026-09-24", 551, 56,
                  [("Web", 118, 11, 0), ("ACE", 0, 0, 4150), ("Cargurus", 58, 3, 2250)])

        d = build("2026-09-25")
        g = d["stores"]["SBMW"]["ga4"]
        check(d["prev_date"] == "2026-09-24", "default baseline is the newest earlier shift with data")
        check(g["tonight_file"].endswith("rerun/ga4_SBMW.json"), "latest pull inside a shift wins (data/rerun)")
        check(g["preliminary_days"] == ["2026-09-24"] and g["last_complete_day"] == "2026-09-23",
              "newest day preliminary, last complete day is the day before")
        rs = {(r["day"], r["scope"], r["name"], r["metric"]): r for r in g["restatements"]}
        o = rs.get(("2026-09-23", "channel", "Organic Search", "sessions"))
        check(o and o["before"] == 96 and o["after"] == 234 and o["kind"] == "filled in",
              "restatement 96 -> 234 found and marked filled in")
        t = rs.get(("2026-09-23", "total", None, "sessions"))
        check(t and t["before"] == 396 and t["after"] == 634, "store total restatement 396 -> 634")
        c = rs.get(("2026-09-22", "channel", "Organic Search", "sessions"))
        check(c and c["kind"] == "changed" and "DOWN" in c.get("note", ""),
              "complete-day decrease (200 -> 150) marked changed and called out")
        check(("2026-09-22", "channel", "Paid Social", "sessions") not in rs, "unchanged channel not reported")
        lc = g["last_complete"]
        check(lc["day"] == "2026-09-23" and lc["total"]["sessions"]["dod_value"] == 550
              and lc["total"]["sessions"]["wow_value"] == 600, "last complete day: day before and same weekday")
        check(lc["wow_file"] == "outputs/ai-team/2026-09-18/data/ga4_SBMW.json" and not lc["wow_preliminary"],
              "same weekday value comes from the newest pull that holds it as a complete day")
        check(not any(f.get("day") == "2026-09-24" for f in d["flags"]), "no flag computed on the preliminary day")
        check(g["prior_preliminary_filled"][0]["sessions"]["before"] == 396, "last night's preliminary fill measured")
        a = d["stores"]["NOI"]["ads"]
        check(a["preliminary_days"] == ["2026-09-24"], "Ads newest day preliminary from export last_run")
        ars = {(r["day"], r["scope"], r["metric"]): r for r in a["restatements"]}
        check(("2026-09-22", "total", "conversions") in ars and ars[("2026-09-22", "total", "conversions")]["after"] == 7,
              "Ads conversion lag restatement 4 -> 7")
        check(ars[("2026-09-23", "total", "clicks")]["before"] == 30,
              "export change (vanished campaign) kept out of totals: 30 -> 41, not 38 -> 41")
        check(any(x["campaign"] == "Old" for x in a.get("export_changes", [])), "vanished campaign listed as export change")
        check(any(x["field"] == "status" and x["after"] == "PAUSED" for x in a.get("settings_changes", [])),
              "campaign status change detected")
        check(a["last_complete"]["total"]["conversions"]["flag"] is False, "lagging Ads conversions never flagged")
        check(a["last_complete"]["total"]["clicks"]["wow_value"] == 20, "Ads same weekday last week from the 30d file")
        fl = [(f["name"], f["metric"]) for f in a["last_complete"]["flags"]]
        check(("store total", "clicks") in fl and ("PMAX", "clicks") in fl,
              "flags on the store total and on the campaign (41 vs 20 clicks, same weekday)")
        cr = d["stores"]["NOI"]["crm"]
        check(cr["increment"]["leads"] == 16 and cr["increment"]["sold"] == 1, "CRM increment +16 leads, +1 sold")
        check(cr["increment_days"]["days"] == 1, "CRM increment spans one day")
        check(any(r["name"] == "Cargurus" and r["change"] == -2 for r in cr["restatements"]),
              "CRM source that went down is a restatement")
        check(any(b["source"] == "ACE" and b["cost_increment"] == 150 for b in cr.get("billing_without_new_leads", [])),
              "cost with no new leads listed")
        md = render_md(d)
        check(EMDASH not in md and EMDASH not in json.dumps(d), "no em dashes")
        check(md.index("Restated since last night") < md.index("**Tonight**"), "restatements come first in deltas.md")
        # Monday: 9/28 vs 9/25, three days of CRM, newly complete days listed
        _ga4_file(os.path.join(base, "2026-09-28", "data", "ga4_SBMW.json"), "2026-09-27", "2026-09-28T01:05:00",
                  rows_for(["2026-09-%02d" % i for i in range(21, 28)], {"2026-09-24": (234, 500)}))
        _crm_file(os.path.join(base, "2026-09-28", "data", "crm_mtd_NOI.json"), "2026-09-01", "2026-09-27", 625, 70,
                  [("Web", 150, 20, 0), ("ACE", 0, 0, 4500), ("Cargurus", 58, 3, 2250)])
        d2 = build("2026-09-28")
        g2 = d2["stores"]["SBMW"]["ga4"]
        check(d2["gap_days"] == 3, "Monday gap of 3 days noted")
        check([n["day"] for n in g2["newly_complete_days"]] == ["2026-09-24", "2026-09-25", "2026-09-26"],
              "Monday lists Thu, Fri, Sat as newly complete")
        c2 = d2["stores"]["NOI"]["crm"]
        check(c2["increment_days"]["days"] == 3 and c2["increment"]["leads"] == 74 and
              c2["increment_per_day"]["leads"] == 24.7, "CRM Monday increment over 3 days with a per-day rate")
        check(d2["stores"]["NOI"].get("ads", {}).get("missing"), "missing Ads export tonight reported, not guessed")
        # month rollover
        _crm_file(os.path.join(base, "2026-10-02", "data", "crm_mtd_NOI.json"), "2026-10-01", "2026-10-01", 20, 1,
                  [("Web", 5, 1, 0)])
        d3 = build("2026-10-02", "2026-09-28")
        c3 = d3["stores"]["NOI"]["crm"]
        check(c3.get("month_rollover") and c3["increment"]["leads"] == 20 and
              c3.get("uncovered_days") == ["2026-09-28", "2026-09-29", "2026-09-30"],
              "month rollover: increment is the new MTD, uncovered days named")
        # write path
        out = os.path.join(tmp, "out")

        class A(object):
            date, prev_date, quiet = "2026-09-25", None, True
        A.out = out
        rc = cmd_run(A)
        check(rc == 0 and os.path.exists(os.path.join(out, "deltas.json")) and
              os.path.exists(os.path.join(out, "deltas.md")), "run writes deltas.json and deltas.md")
    finally:
        ROOT = saved_root
        shutil.rmtree(tmp, ignore_errors=True)
    print("selftest: %s (%d failed)" % ("PASS" if not fails else "FAIL", len(fails)))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Night-shift deltas: restatements, preliminary day, last complete "
                                             "day vs last week, CRM increment. See the module docstring.")
    ap.add_argument("cmd", nargs="?", default="run", choices=["run", "selftest"])
    ap.add_argument("--date")
    ap.add_argument("--prev-date")
    ap.add_argument("--out")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "selftest":
        return cmd_selftest(args)
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
