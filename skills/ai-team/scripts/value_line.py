#!/usr/bin/env python3
"""Monthly AI-search and SEO value line per store for the DigitalCLIQ AI team. Standard library only.

  python3 .claude/skills/ai-team/scripts/value_line.py --date 2026-10-05
  python3 .claude/skills/ai-team/scripts/value_line.py --date 2026-10-05 --data outputs/ai-team/2026-10-05/data
  python3 .claude/skills/ai-team/scripts/value_line.py selftest

Once a month (first Monday, after the monthly Semrush rank history pull) every store gets two
sentences a GM or owner can read (Rule 23):
  1. Search value: what the store's unpaid (organic) Google traffic would cost if it were bought as
     paid clicks. This is Semrush's organic traffic cost estimate, labeled as a Semrush estimate
     with its "as of" month, plus the month-over-month direction when the file holds the month before.
  2. AI visibility: visits from AI assistants measured by GA4 over the last 28 days, by engine,
     plus the keywords where Semrush shows the store's own page cited in a Google AI Overview
     (Semrush "Position type" = AI overview).
Semrush numbers are estimates and GA4 numbers are measured; both sentences say which is which.

Reads DIR (default outputs/ai-team/{date}/data, relative to the vault root where the shift runs):
  semrush_rank_history*.json  the one with the newest month in DIR; if DIR has none and DIR is the
                              standard outputs/ai-team/{date}/data layout, the nearest earlier shift
                              folder up to 30 days back. Shapes: Magic's {"columns", "stores": {S:
                              {"domain", "rows": [[...]]}}}, the older {"stores": {S: {"months":
                              [{...}]}}}, or raw execute_report text per store ({"stores": {S: {"data": "..."}}}).
  semrush_kw_{STORE}.csv      newest within 7 days (same rules as seo_join.py), else the
                              semrush_organic_positions.md section for that store
  ga4_{STORE}.json            ai_engine_referrals_last28 (session totals by engine)
  ga4_organic_{STORE}.json    ai_referrals_by_landing_last28 (top AI landing pages; totals fallback)

Writes DIR/value_line.json (every figure with its source file, section, and date) and
DIR/value_line.md (a paste-ready "For the brief" block, then per store the two sentences, the
numbers behind them, what was not available, and notes). Prints what was missing.

Rules baked in:
  - MCP's AI-referral key events are invalid (a tracking double-fire): MCP gets sessions only, and
    its key events are never written to either file (WITHHOLD_KEY_EVENTS).
  - A figure dated more than 12 months before --date is dropped from the sentences.
  - Semrush ToS 3.3 limits caching to a month, so the lookback stops at 30 days; past that the
    line reports the rank history as missing and Worthy re-pulls it (the monthly pull runs first).
  - The keyword pull is Semrush's top rows by traffic, so the sentence names its scope ("of the 32
    top searches in Semrush's current list"); "no AI Overview" means none in that list, never none at all.
  - The rank history's ai_overview_keywords column is carried in the numbers only: what Semrush
    counts there is unverified, so it never reaches a sentence.

--competitors (design note, NOT implemented): a later version adds three competitors per store as
a prospect teaser (their unpaid search traffic value and AI Overview citations next to the store's).
Cost: about 4,800 Semrush units per run: 12 competitor domains (three each for SBMW, NCBMW, NOI,
MCP; Atlas is monitored only) x about 400 units (resource_rank_history with the extra columns,
about 300, plus a 10-row resource_organic AI overview check, 100). That is roughly a tenth of the
~50,000 monthly units, so it needs Drew's go and its own line in the unit budget in
references/data-sources.md before it is built. Competitor names come from Context/vault-facts.md,
never guessed, and a prospect-facing version still passes Magic's compliance gate.
"""
import argparse
import collections
import datetime as dt
import glob
import json
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from seo_join import (SEMRUSH_MD, bucket, load_json, parse_semrush_md,  # noqa: E402
                      parse_semrush_text, recent_file, split_url, ts_date)

STORES = ["SBMW", "NCBMW", "NOI", "MCP", "ATLAS"]
NAMES = {"SBMW": "Sterling BMW", "NCBMW": "New Century BMW", "NOI": "Nissan of Irvine",
         "MCP": "McPeek's CDJR of Anaheim", "ATLAS": "Atlas Shippers"}
DOMAINS = {"SBMW": "sterlingbmw.com", "NCBMW": "newcenturybmw.com", "NOI": "nissanofirvine.com",
           "MCP": "mcpeeks.com", "ATLAS": "atlasshippers.com"}
# Mirrors the brand-term list in references/data-sources.md; used only to word the scope.
BRAND_TERMS = {"SBMW": ("sterling", "stearling"), "NCBMW": ("century", "centry"),
               "NOI": ("nissan of irvine", "nissanofirvine"), "MCP": ("mcpeek",), "ATLAS": ("atlas",)}
WITHHOLD_KEY_EVENTS = {
    "MCP": "MCP's AI-referral key events are invalid (tracking double-fire), so only sessions are shown.",
}

RANK_GLOB = "semrush_rank_history*.json"
RANK_LOOKBACK_DAYS = 30  # Semrush ToS 3.3: no cached Semrush data older than a month
TOS_CACHE_DAYS = 30
MAX_AGE_DAYS = 365
MOM_MIN_DAYS, MOM_MAX_DAYS = 20, 45
FLAT_PCT = 2.0
VISITS_FLAT_PCT = 5.0
LOW_ENGAGED_SHARE = 0.25
LOW_ENGAGED_MIN = 20
KW_IN_SENTENCE = 3
TOP_PAGES = 3

ENGINES = [(r"chatgpt|openai", "ChatGPT"), (r"perplexity", "Perplexity"), (r"gemini|bard", "Gemini"),
           (r"copilot", "Copilot"), (r"claude|anthropic", "Claude"), (r"you\.com", "You.com"),
           (r"phind", "Phind"), (r"poe\.com", "Poe"), (r"meta\.ai", "Meta AI"),
           (r"deepseek", "DeepSeek"), (r"grok", "Grok")]
ENGINES = [(re.compile(rx, re.I), name) for rx, name in ENGINES]

RH_FIELDS = {
    "date": ("date", "dt"),
    "organic_cost": ("organic_cost_usd_est", "organic_cost_usd", "organic_cost", "organic cost", "oc"),
    "organic_traffic": ("organic_traffic_est", "organic_traffic", "organic traffic", "ot"),
    "organic_keywords": ("organic_keywords", "organic keywords", "or"),
    "ai_overview_keywords": ("ai_overview_keywords",),
}


# ---------------------------------------------------------------- small helpers

def parse_day(v):
    """date from 2026-08-15, 20260815, or Unix seconds; None otherwise."""
    if v is None:
        return None
    s = str(v).strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return dt.date.fromisoformat(s)
        if re.fullmatch(r"\d{8}", s):
            return dt.date(int(s[:4]), int(s[4:6]), int(s[6:]))
        if re.fullmatch(r"\d{9,11}", s):
            return dt.datetime.fromtimestamp(int(s), dt.timezone.utc).date()
    except (ValueError, OverflowError, OSError):
        return None
    return None


def fmt_int(n):
    return "{:,}".format(int(n))


def approx(n):
    """Visit counts in sentences: nearest 100 from 1,000 up, nearest 10 from 100 up."""
    n = int(n)
    if n >= 1000:
        return int(round(n / 100.0) * 100)
    if n >= 100:
        return int(round(n / 10.0) * 10)
    return n


def fmt_day(d):
    return "%s %d, %d" % (d.strftime("%b"), d.day, d.year)


def fmt_range(a, b):
    if a == b:
        return fmt_day(a)
    if a.year == b.year:
        return "%s %d to %s" % (a.strftime("%b"), a.day, fmt_day(b))
    return "%s to %s" % (fmt_day(a), fmt_day(b))


def fmt_month(d):
    return "%s %d" % (d.strftime("%B"), d.year)


def too_old(d, run_day):
    return d is None or (run_day - d).days > MAX_AGE_DAYS


def engine_of(source):
    s = (source or "").strip()
    for rx, name in ENGINES:
        if rx.search(s):
            return name
    return s or "unknown"


# ---------------------------------------------------------------- Semrush rank history

def _norm_row(d):
    low = {str(k).strip().lower(): v for k, v in d.items()}
    got = {}
    for field, names in RH_FIELDS.items():
        for n in names:
            if n in low:
                got[field] = low[n]
                break
    day = parse_day(got.get("date"))
    if not day:
        return None
    row = {"date": day.isoformat()}
    for field in ("organic_cost", "organic_traffic", "organic_keywords", "ai_overview_keywords"):
        v = got.get(field)
        try:
            row[field] = None if v in (None, "", "-") else int(round(float(v)))
        except (TypeError, ValueError):
            row[field] = None
    return row


def _rows_from_text(text):
    text = (text or "").strip()
    if text.startswith("{"):
        try:
            env = json.loads(text)
        except ValueError:
            return []
        text = env.get("data") if isinstance(env.get("data"), str) else ""
    lines = [ln for ln in text.splitlines() if ";" in ln]
    if len(lines) < 2:
        return []
    hdr = [h.strip() for h in lines[0].split(";")]
    return [dict(zip(hdr, ln.split(";"))) for ln in lines[1:]]


def parse_rank_history(obj):
    """{STORE: {"domain", "rows" newest first}} from any of the supported shapes."""
    if not isinstance(obj, dict):
        return {}
    stores = obj.get("stores")
    if not isinstance(stores, dict):
        stores = {k: v for k, v in obj.items() if re.fullmatch(r"[A-Z0-9]{2,8}", str(k))}
    cols = obj.get("columns")
    out = {}
    for code, v in stores.items():
        raw, domain = [], None
        if isinstance(v, dict):
            domain = v.get("domain")
            items = v.get("rows") if v.get("rows") is not None else v.get("months")
            if items is None and isinstance(v.get("data"), str):
                raw = _rows_from_text(v["data"])
            for it in items or []:
                if isinstance(it, dict):
                    raw.append(it)
                elif isinstance(it, (list, tuple)) and cols:
                    raw.append(dict(zip(cols, it)))
        elif isinstance(v, str):
            raw = _rows_from_text(v)
        elif isinstance(v, list):
            raw = [x for x in v if isinstance(x, dict)]
        rows = sorted((r for r in (_norm_row(x) for x in raw) if r), key=lambda r: r["date"], reverse=True)
        if rows:
            out[str(code).upper()] = {"domain": domain, "rows": rows,
                                      "note": v.get("note") if isinstance(v, dict) else None}
    return out


def _best_rank_file(folder):
    best = None
    for path in sorted(glob.glob(os.path.join(folder, RANK_GLOB))):
        obj = load_json(path)
        parsed = parse_rank_history(obj)
        if not parsed:
            continue
        newest = max(s["rows"][0]["date"] for s in parsed.values())
        key = (newest, os.path.getmtime(path))
        if best is None or key > best[0]:
            best = (key, path, obj, parsed)
    return best


def find_rank_history(data_dir, date):
    """(path, raw object, parsed, days back) or None."""
    b = _best_rank_file(data_dir)
    if b:
        return b[1], b[2], b[3], 0
    root = os.path.dirname(os.path.dirname(os.path.normpath(data_dir)))
    if os.path.normpath(data_dir) != os.path.normpath(os.path.join(root, date, "data")):
        return None
    day = dt.date.fromisoformat(date)
    for back in range(1, RANK_LOOKBACK_DAYS + 1):
        folder = os.path.join(root, (day - dt.timedelta(days=back)).isoformat(), "data")
        if os.path.isdir(folder):
            b = _best_rank_file(folder)
            if b:
                return b[1], b[2], b[3], back
    return None


# ---------------------------------------------------------------- per store pieces

def search_value(store, rh, run_day):
    """Sentence 1 inputs from the parsed rank history."""
    res = {"ok": False, "current": None, "previous": None, "change_usd": None, "change_pct": None,
           "traffic_change_pct": None, "diverged": False, "missing": None, "notes": []}
    if rh is None:
        res["missing"] = "no Semrush rank history file within %d days" % RANK_LOOKBACK_DAYS
        return res
    st = rh["parsed"].get(store)
    if not st:
        res["missing"] = "no %s section in %s" % (store, rh["path"])
        return res
    if st.get("note"):
        res["notes"].append("Rank history note from the pull: " + st["note"])
    rows = st["rows"]
    cur = rows[0]
    cur_day = parse_day(cur["date"])
    if too_old(cur_day, run_day):
        res["missing"] = "newest Semrush month is %s, more than 12 months before %s" % (cur["date"], run_day)
        return res
    if cur.get("organic_cost") is None:
        res["missing"] = "rank history row %s has no organic traffic cost" % cur["date"]
        return res
    res["ok"], res["current"] = True, cur
    if len(rows) > 1:
        prev = rows[1]
        gap = (cur_day - parse_day(prev["date"])).days
        if MOM_MIN_DAYS <= gap <= MOM_MAX_DAYS and prev.get("organic_cost") is not None:
            res["previous"] = prev
            res["change_usd"] = cur["organic_cost"] - prev["organic_cost"]
            if prev["organic_cost"]:
                res["change_pct"] = round(100.0 * res["change_usd"] / prev["organic_cost"], 1)
            t0, t1 = prev.get("organic_traffic"), cur.get("organic_traffic")
            if res["change_pct"] is not None and t0 and t1 is not None:
                tpct = 100.0 * (t1 - t0) / t0
                res["traffic_change_pct"] = round(tpct, 1)
                if abs(res["change_pct"] - tpct) >= 20:
                    res["diverged"] = True
                    res["notes"].append(
                        "Estimated value moved %+.0f%% while estimated visits moved %+.0f%%, so the change is "
                        "Semrush's click-price mix, not more traffic." % (res["change_pct"], tpct))
        else:
            res["notes"].append("No month-over-month: the next row is %s." % prev["date"])
    else:
        res["notes"].append("No month-over-month: the file holds one month.")
    return res


def sentence_search_value(domain, sv):
    if not sv["ok"]:
        return "Semrush's estimate of what the unpaid Google search traffic to %s is worth is not available this month." % domain
    cur = sv["current"]
    month = fmt_month(parse_day(cur["date"]))
    cost = cur["organic_cost"]
    if not cost:
        return ("Semrush shows no estimated paid-click value for unpaid Google search traffic to %s as of %s "
                "(a Semrush estimate)." % (domain, month))
    visits = ""
    if cur.get("organic_traffic"):
        visits = " (about %s visits a month)" % fmt_int(approx(cur["organic_traffic"]))
    s = ("Semrush estimates the unpaid Google search traffic to %s%s would cost about $%s a month "
         "if bought as paid ad clicks, as of %s" % (domain, visits, fmt_int(cost), month))
    prev = sv["previous"]
    if prev is not None:
        pd = parse_day(prev["date"])
        pm = pd.strftime("%B") if pd.year == parse_day(cur["date"]).year else fmt_month(pd)
        p = prev["organic_cost"]
        if not p:
            s += ", up from $0 in %s" % pm
        elif abs(sv["change_pct"]) < FLAT_PCT:
            s += ", about flat from $%s in %s" % (fmt_int(p), pm)
        else:
            s += ", %s %d%% from $%s in %s" % ("up" if sv["change_pct"] > 0 else "down",
                                              int(round(abs(sv["change_pct"]))), fmt_int(p), pm)
            if sv["diverged"]:
                t = sv["traffic_change_pct"]
                s += " while estimated visits %s" % ("held about flat" if abs(t) < VISITS_FLAT_PCT else
                                                     "went %s %d%%" % ("up" if t > 0 else "down", int(round(abs(t)))))
    return s + "."


def load_keywords(store, data_dir, date, md_rows, md_path):
    csv_path = recent_file(data_dir, date, "semrush_kw_%s.csv" % store)
    problem = "missing"
    if os.path.exists(csv_path):
        with open(csv_path, encoding="utf-8", errors="replace") as f:
            rows, note = parse_semrush_text(f.read())
        if rows:
            return rows, csv_path, None
        problem = "has 0 rows (%s)" % (note or "empty")
    if store in md_rows and md_rows[store]:
        return md_rows[store], md_path, None
    return None, None, "semrush_kw_%s.csv %s and no %s section in %s" % (store, problem, store, SEMRUSH_MD)


def ai_overview(store, rows, source, run_day):
    """Keywords where Semrush shows the store's own page in a Google AI Overview."""
    domain = DOMAINS.get(store)
    if not domain:
        hosts = collections.Counter(split_url(r["url"])[0] for r in rows if r["url"])
        domain = hosts.most_common(1)[0][0] if hosts else ""
    def own(url):
        host = split_url(url)[0]
        return not domain or host == domain or host.endswith("." + domain)

    kept, dropped = [], 0
    for r in rows:
        if not own(r["url"]):
            continue
        d = parse_day(ts_date(r["timestamp"])) if r["timestamp"] else None
        if d is not None and too_old(d, run_day):
            dropped += 1
            continue
        kept.append((r, d))
    universe = {r["keyword"] for r, _ in kept}
    brand = BRAND_TERMS.get(store, ())
    non_brand = bool(universe) and not any(t in k.lower() for k in universe for t in brand)
    days = [d for _, d in kept if d]
    by_kw = collections.OrderedDict()
    for r, d in kept:
        if r["position_type"].strip().lower() != "ai overview":
            continue
        k = by_kw.setdefault(r["keyword"], {"keyword": r["keyword"], "position": r["position"],
                                            "volume": r["volume"], "urls": [], "as_of": None})
        if r["position"] and (not k["position"] or r["position"] < k["position"]):
            k["position"] = r["position"]
        k["volume"] = max(k["volume"], r["volume"])
        if r["url"] not in k["urls"]:
            k["urls"].append(r["url"])
        if d and (k["as_of"] is None or d.isoformat() > k["as_of"]):
            k["as_of"] = d.isoformat()
    kws = sorted(by_kw.values(), key=lambda k: (-k["volume"], k["keyword"]))
    return {"ok": True, "source": source, "domain": domain, "keywords": kws,
            "universe": len(universe), "non_brand": non_brand, "rows": len(kept),
            "dropped_older_than_12_months": dropped,
            "data_dates": [min(days).isoformat(), max(days).isoformat()] if days else None}


def ga4_ai(store, data_dir, run_day):
    """Sentence 2 GA4 inputs: AI-assistant sessions by engine plus top landing pages."""
    res = {"ok": False, "missing": [], "notes": []}
    withhold = store in WITHHOLD_KEY_EVENTS
    main_path = os.path.join(data_dir, "ga4_%s.json" % store)
    org_path = os.path.join(data_dir, "ga4_organic_%s.json" % store)
    main, org = load_json(main_path), load_json(org_path)
    rows, src, section, target, window = None, None, None, None, None
    if main is not None and main.get("ai_engine_referrals_last28") is not None:
        rows, src, section = main["ai_engine_referrals_last28"], main_path, "ai_engine_referrals_last28"
        target = parse_day(main.get("target_date"))
        res["pulled_at"] = main.get("pulled_at")
        if target:
            window = [target - dt.timedelta(days=27), target]
    elif org is not None and org.get("ai_referrals_by_landing_last28") is not None:
        rows, src, section = org["ai_referrals_by_landing_last28"], org_path, "ai_referrals_by_landing_last28"
        target = parse_day(org.get("target_date"))
        w = (org.get("organic_windows") or {}).get("last28")
        if w:
            window = [parse_day(w[0]), parse_day(w[1])]
        elif target:
            window = [target - dt.timedelta(days=27), target]
        res["notes"].append("Totals summed from ga4_organic_%s.json by landing page (ga4_%s.json had no "
                            "ai_engine_referrals_last28)." % (store, store))
    else:
        for path, obj, sec in ((main_path, main, "ai_engine_referrals_last28"),
                               (org_path, org, "ai_referrals_by_landing_last28")):
            if obj is None:
                res["missing"].append("%s not found" % os.path.basename(path))
            else:
                errs = [e for e in obj.get("errors") or [] if sec in str(e)]
                res["missing"].append("%s:%s %s" % (os.path.basename(path), sec,
                                                    ("errored: " + errs[0][:120]) if errs else "absent"))
        return res
    if not window or not window[0] or too_old(window[1], run_day):
        res["missing"].append("GA4 window missing or more than 12 months old in %s" % os.path.basename(src))
        return res
    eng = collections.OrderedDict()
    for r in rows:
        name = engine_of(r.get("sessionSource"))
        e = eng.setdefault(name, {"engine": name, "sessions": 0, "engaged_sessions": 0, "key_events": 0,
                                  "sources": []})
        e["sessions"] += int(r.get("sessions") or 0)
        e["engaged_sessions"] += int(r.get("engagedSessions") or 0)
        e["key_events"] += int(r.get("keyEvents") or 0)
        if r.get("sessionSource") not in e["sources"]:
            e["sources"].append(r.get("sessionSource"))
    engines = sorted(eng.values(), key=lambda e: (-e["sessions"], e["engine"]))
    total = sum(e["sessions"] for e in engines)
    engaged = sum(e["engaged_sessions"] for e in engines)
    if withhold:
        for e in engines:
            e["key_events"] = None
        res["key_events_withheld"] = WITHHOLD_KEY_EVENTS[store]
    res.update({"ok": True, "source": src, "section": section, "target_date": target.isoformat() if target else None,
                "window": [window[0].isoformat(), window[1].isoformat()], "total_sessions": total,
                "engaged_sessions": engaged, "key_events": None if withhold else sum(e["key_events"] for e in engines),
                "engines": engines})
    if total >= LOW_ENGAGED_MIN and engaged < LOW_ENGAGED_SHARE * total:
        res["notes"].append("Only %d of %d AI-assistant sessions were engaged sessions, so treat the count with care."
                            % (engaged, total))
    # Top landing pages from the organic file (same 28-day window when both come from one gdata.py run).
    landing = org.get("ai_referrals_by_landing_last28") if org else None
    if landing is not None:
        pages = collections.OrderedDict()
        for r in landing:
            _, path, _ = split_url(r.get("landingPage"))
            key, _ = bucket(path)
            if key == "(not set)":
                continue
            p = pages.setdefault(key, {"page": key, "sessions": 0, "key_events": 0})
            p["sessions"] += int(r.get("sessions") or 0)
            p["key_events"] += int(r.get("keyEvents") or 0)
        top = sorted(pages.values(), key=lambda p: (-p["sessions"], p["page"]))[:TOP_PAGES]
        for p in top:
            if withhold:
                p.pop("key_events")
        res["top_pages"] = top
        res["top_pages_source"] = org_path
        by_landing_total = sum(int(r.get("sessions") or 0) for r in landing)
        if section == "ai_engine_referrals_last28" and by_landing_total != total:
            res["notes"].append("The by-landing-page pull sums to %d sessions against %d by source (GA4 row "
                                "limits or a different pull time); the by-source total is the one used."
                                % (by_landing_total, total))
        if org.get("target_date") and target and org.get("target_date") != target.isoformat():
            res["notes"].append("ga4_organic_%s.json covers a different target date (%s)." % (store, org.get("target_date")))
    else:
        res["top_pages"] = None
    return res


def sentence_ai(domain, ga, aio):
    if ga["ok"]:
        win = fmt_range(parse_day(ga["window"][0]), parse_day(ga["window"][1]))
        n = ga["total_sessions"]
        if n == 0:
            p1 = ("Google Analytics measured no visits to the site from AI assistants such as ChatGPT or Gemini "
                  "in the last 28 days (%s)" % win)
        else:
            eng = ", ".join("%s %s" % (e["engine"], fmt_int(e["sessions"])) for e in ga["engines"] if e["sessions"])
            p1 = ("Google Analytics measured %s visit%s to the site from AI assistants in the last 28 days (%s: %s)"
                  % (fmt_int(n), "" if n == 1 else "s", win, eng))
    else:
        p1 = "Google Analytics visits to the site from AI assistants are not available this month"
    if aio and aio["ok"] and aio["universe"]:
        scope = "the %d top %ssearch%s Semrush lists for the site" % (
            aio["universe"], "non-brand " if aio["non_brand"] else "", "" if aio["universe"] == 1 else "es")
        kws = aio["keywords"]
        if kws:
            dates = sorted(k["as_of"] for k in kws if k["as_of"])
            asof = fmt_range(parse_day(dates[0]), parse_day(dates[-1])) if dates else "an undated pull"
            shown = ", ".join('"%s"' % k["keyword"] for k in kws[:KW_IN_SENTENCE])
            if len(kws) > KW_IN_SENTENCE:
                shown += " and %d more" % (len(kws) - KW_IN_SENTENCE)
            p2 = ("Semrush shows the site cited in a Google AI Overview for %d of %s (%s, as of %s)"
                  % (len(kws), scope, shown, asof))
        else:
            d = aio["data_dates"]
            asof = fmt_range(parse_day(d[0]), parse_day(d[1])) if d else "an undated pull"
            p2 = "Semrush shows no Google AI Overview citing the site among %s (as of %s)" % (scope, asof)
    else:
        p2 = "Semrush AI Overview data is not available this month"
    return "%s, and %s." % (p1, p2)


# ---------------------------------------------------------------- assembly

def build_store(store, data_dir, date, rh, md_rows, md_path):
    run_day = dt.date.fromisoformat(date)
    domain = DOMAINS.get(store) or ((rh or {}).get("parsed", {}).get(store, {}).get("domain")) or store.lower()
    sv = search_value(store, rh, run_day)
    kw_rows, kw_src, kw_problem = load_keywords(store, data_dir, date, md_rows, md_path)
    aio = ai_overview(store, kw_rows, kw_src, run_day) if kw_rows else {"ok": False, "missing": kw_problem}
    ga = ga4_ai(store, data_dir, run_day)

    not_available, notes = [], []
    if not sv["ok"]:
        not_available.append("Search value: " + sv["missing"])
    notes += sv["notes"]
    if rh and rh.get("caution"):
        notes.append(rh["caution"])
    if not aio["ok"]:
        not_available.append("AI Overview keywords: " + aio["missing"])
    elif aio["dropped_older_than_12_months"]:
        notes.append("%d Semrush keyword row(s) older than 12 months were dropped." % aio["dropped_older_than_12_months"])
    if not ga["ok"]:
        not_available.append("GA4 AI-assistant sessions: " + "; ".join(ga["missing"]))
    notes += ga["notes"]

    numbers = {"search_value": None, "ai_sessions": None, "ai_overview": None}
    if sv["ok"]:
        cur, prev = sv["current"], sv["previous"]
        numbers["search_value"] = {
            "kind": "Semrush estimate", "source": rh["path"], "report": "resource_rank_history",
            "pulled_at": rh.get("pulled_at"), "as_of": cur["date"],
            "organic_cost_usd": cur["organic_cost"], "organic_traffic": cur.get("organic_traffic"),
            "organic_keywords": cur.get("organic_keywords"),
            "ai_overview_keywords_unverified": cur.get("ai_overview_keywords"),
            "previous": ({"as_of": prev["date"], "organic_cost_usd": prev["organic_cost"],
                          "organic_traffic": prev.get("organic_traffic")} if prev else None),
            "change_usd": sv["change_usd"], "change_pct": sv["change_pct"]}
    if ga["ok"]:
        numbers["ai_sessions"] = {k: ga.get(k) for k in (
            "source", "section", "target_date", "window", "pulled_at", "total_sessions", "engaged_sessions",
            "key_events", "engines", "top_pages", "top_pages_source")}
        numbers["ai_sessions"]["kind"] = "GA4 measured"
        if ga.get("key_events_withheld"):
            numbers["ai_sessions"]["key_events_withheld"] = ga["key_events_withheld"]
    if aio["ok"]:
        numbers["ai_overview"] = {k: aio[k] for k in ("source", "domain", "keywords", "universe", "non_brand",
                                                      "rows", "data_dates")}
        numbers["ai_overview"]["kind"] = "Semrush data (model of Google results)"
    return {"store": store, "name": NAMES.get(store, store), "domain": domain,
            "sentences": {"search_value": sentence_search_value(domain, sv),
                          "ai_visibility": sentence_ai(domain, ga, aio)},
            "numbers": numbers, "not_available": not_available, "notes": notes}


def md_store(s):
    n = s["numbers"]
    out = ["## %s, %s (%s)" % (s["store"], s["name"], s["domain"]), "",
           "**Search value.** " + s["sentences"]["search_value"], "",
           "**AI visibility.** " + s["sentences"]["ai_visibility"], "", "Numbers behind it:"]
    sv = n["search_value"]
    if sv:
        line = "- Semrush organic traffic cost (estimate): $%s a month as of %s" % (fmt_int(sv["organic_cost_usd"]), sv["as_of"])
        if sv["previous"]:
            p = sv["previous"]
            line += "; $%s as of %s (%s$%s, %s)" % (
                fmt_int(p["organic_cost_usd"]), p["as_of"], "+" if sv["change_usd"] >= 0 else "-",
                fmt_int(abs(sv["change_usd"])), ("%+.1f%%" % sv["change_pct"]) if sv["change_pct"] is not None else "from $0")
        line += ". Source: %s, resource_rank_history, pulled %s." % (sv["source"], sv["pulled_at"] or "(pull time not recorded)")
        out.append(line)
        if sv["organic_traffic"] is not None:
            t = "- Semrush organic traffic (estimate): %s visits a month as of %s" % (fmt_int(sv["organic_traffic"]), sv["as_of"])
            if sv["previous"] and sv["previous"].get("organic_traffic") is not None:
                t += " (%s as of %s)" % (fmt_int(sv["previous"]["organic_traffic"]), sv["previous"]["as_of"])
            if sv["organic_keywords"] is not None:
                t += "; %s organic keywords" % fmt_int(sv["organic_keywords"])
            out.append(t + ". Same file.")
        if sv["ai_overview_keywords_unverified"] is not None:
            out.append("- Semrush rank history `ai_overview_keywords`: %s as of %s. What this column counts is "
                       "unverified, so it stays out of the sentences." % (fmt_int(sv["ai_overview_keywords_unverified"]), sv["as_of"]))
    ai = n["ai_sessions"]
    if ai:
        parts = []
        for e in ai["engines"]:
            extra = "%d engaged" % e["engaged_sessions"]
            if e["key_events"] is not None:
                extra += ", %d key event%s" % (e["key_events"], "" if e["key_events"] == 1 else "s")
            parts.append("%s %d (%s; source %s)" % (e["engine"], e["sessions"], extra, " + ".join(map(str, e["sources"]))))
        line = "- GA4 AI-assistant sessions (measured), %s to %s: %s total" % (ai["window"][0], ai["window"][1], fmt_int(ai["total_sessions"]))
        line += (": " + "; ".join(parts)) if parts else ""
        line += ". Source: %s `%s`, target date %s%s." % (ai["source"], ai["section"], ai["target_date"],
                                                          (", pulled " + ai["pulled_at"]) if ai.get("pulled_at") else "")
        out.append(line)
        if ai.get("key_events_withheld"):
            out.append("- Key events withheld: " + ai["key_events_withheld"])
        if ai.get("top_pages"):
            pg = ", ".join("%s %d%s" % (p["page"], p["sessions"], (" (%d key event%s)" % (
                p["key_events"], "" if p["key_events"] == 1 else "s")) if "key_events" in p else "")
                           for p in ai["top_pages"])
            out.append("- Top AI landing pages (GA4 measured, same window): %s. Source: %s `ai_referrals_by_landing_last28`." % (pg, ai["top_pages_source"]))
    ao = n["ai_overview"]
    if ao:
        if ao["keywords"]:
            kl = "; ".join('"%s" pos %s, volume %s, %s, as of %s' % (k["keyword"], k["position"], fmt_int(k["volume"]),
                                                                      " and ".join(k["urls"]), k["as_of"]) for k in ao["keywords"])
        else:
            kl = "none"
        dd = ao["data_dates"]
        out.append("- Semrush AI Overview citations of %s: %s. Scope: %d distinct %skeywords in %s (%d rows, dated %s to %s)." % (
            ao["domain"], kl, ao["universe"], "non-brand " if ao["non_brand"] else "", ao["source"], ao["rows"],
            dd[0] if dd else "?", dd[1] if dd else "?"))
    out.append("")
    out.append("Not available: " + ("; ".join(s["not_available"]) if s["not_available"] else "nothing, all inputs present."))
    for note in s["notes"]:
        out.append("Note: " + note)
    out.append("")
    return out


def run(date, data_dir):
    rh_found = find_rank_history(data_dir, date)
    rh = None
    if rh_found:
        path, obj, parsed, back = rh_found
        pulled = str(obj.get("pulled_at") or "")
        pulled_day = parse_day(pulled[:10]) if pulled else None
        run_day = dt.date.fromisoformat(date)
        age = (run_day - pulled_day).days if pulled_day else back
        rh = {"path": path, "parsed": parsed, "pulled_at": obj.get("pulled_at"), "folder_days_back": back,
              "age_days": age, "caution": None}
        if age > TOS_CACHE_DAYS:
            rh["caution"] = ("The rank history was pulled %d days before this run; Semrush ToS 3.3 limits caching to a "
                             "month, so re-pull it before quoting." % age)
    md_path = recent_file(data_dir, date, SEMRUSH_MD)
    md_rows = parse_semrush_md(md_path) if os.path.exists(md_path) else {}
    stores = [build_store(s, data_dir, date, rh, md_rows, md_path) for s in STORES]
    result = {"date": date, "generated_by": "value_line.py", "data_dir": data_dir,
              "rank_history": ({k: rh[k] for k in ("path", "pulled_at", "folder_days_back", "age_days", "caution")}
                               if rh else None),
              "stores": stores}
    md = ["# Value line, %s" % date, "",
          "Once a month, two sentences per store for a GM or owner. Semrush figures are estimates from Semrush's "
          "model of Google results; Google Analytics (GA4) figures are measured visits. Sources and dates for every "
          "figure sit under each store. GA4 key events are whatever each property marks as a key event; check "
          "[[Intelligence/processes/ga4-conversion-integrity]] before calling any of them leads, and never quote MCP's.",
          "", "## For the brief", ""]
    for s in stores:
        md.append("- **[[%s]]** %s %s" % (s["store"], s["sentences"]["search_value"], s["sentences"]["ai_visibility"]))
    md.append("")
    for s in stores:
        md += md_store(s)
    json_out = os.path.join(data_dir, "value_line.json")
    md_out = os.path.join(data_dir, "value_line.md")
    with open(json_out, "w") as f:
        json.dump(result, f, indent=1)
    with open(md_out, "w") as f:
        f.write("\n".join(md).rstrip() + "\n")
    return result, [json_out, md_out]


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        sys.exit(selftest())
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", required=True, help="shift date YYYY-MM-DD (names the default data folder)")
    p.add_argument("--data", help="data folder (default outputs/ai-team/{date}/data)")
    args = p.parse_args()
    try:
        dt.date.fromisoformat(args.date)
    except ValueError:
        print("ERROR: --date must be YYYY-MM-DD", file=sys.stderr)
        sys.exit(1)
    data_dir = args.data or os.path.join("outputs", "ai-team", args.date, "data")
    if not os.path.isdir(data_dir):
        print("ERROR: data folder not found: %s" % data_dir, file=sys.stderr)
        sys.exit(1)
    result, written = run(args.date, data_dir)
    rh = result["rank_history"]
    print("value_line %s  data=%s" % (args.date, data_dir))
    print("Rank history: %s" % ("%s (pulled %s, %d day%s old)" % (rh["path"], rh["pulled_at"], rh["age_days"],
                                                                     "" if rh["age_days"] == 1 else "s") if rh
                                else "none within %d days" % RANK_LOOKBACK_DAYS))
    if rh and rh["caution"]:
        print("  CAUTION: " + rh["caution"])
    print("Not available:")
    gaps = False
    for s in result["stores"]:
        for g in s["not_available"]:
            gaps = True
            print("  %-6s %s" % (s["store"], g))
    if not gaps:
        print("  none")
    print("Wrote:")
    for w in written:
        print("  " + w)


# ---------------------------------------------------------------- selftest

def selftest():
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))

    tmp = tempfile.mkdtemp(prefix="value_line_selftest_")
    try:
        root = os.path.join(tmp, "ai-team")
        today, old = "2026-10-05", "2026-09-07"  # 28 days apart: inside the 30-day lookback and the ToS month
        d_today, d_old = os.path.join(root, today, "data"), os.path.join(root, old, "data")
        os.makedirs(d_today)
        os.makedirs(d_old)
        cols = ["date", "semrush_rank", "organic_keywords", "pos_1_3", "pos_4_10", "organic_traffic_est",
                "organic_cost_usd_est", "ai_overview_keywords", "local_pack_keywords"]
        rh = {"pulled_at": "2026-09-07 ~01:02 PDT", "columns": cols, "stores": {
            "SBMW": {"domain": "sterlingbmw.com", "rows": [
                ["2026-08-15", 1, 959, 0, 0, 12668, 16350, 268, 0], ["2026-07-15", 1, 990, 0, 0, 12052, 15897, 241, 0]]},
            "NOI": {"domain": "nissanofirvine.com", "rows": [
                ["2026-08-15", 1, 2644, 0, 0, 7209, 14079, 1084, 0], ["2026-07-15", 1, 2424, 0, 0, 7584, 14261, 913, 0]]},
            "MCP": {"domain": "mcpeeks.com", "note": "Near-zero in spring 2026.",
                    "rows": [["2026-08-15", 1, 2311, 0, 0, 4716, 13648, 1014, 0]]},
            "ATLAS": {"domain": "atlasshippers.com", "rows": [
                ["2026-08-15", 1, 1374, 0, 0, 6805, 16236, 813, 0], ["2026-07-15", 1, 1482, 0, 0, 6848, 9108, 679, 0]]}}}
        with open(os.path.join(d_old, "semrush_rank_history.json"), "w") as f:
            json.dump(rh, f)
        with open(os.path.join(d_today, "ga4_SBMW.json"), "w") as f:
            json.dump({"target_date": "2026-10-04", "ai_engine_referrals_last28": [
                {"sessionSource": "chatgpt.com", "sessions": 118, "engagedSessions": 75, "keyEvents": 4},
                {"sessionSource": "gemini.google.com", "sessions": 5, "engagedSessions": 3, "keyEvents": 0},
                {"sessionSource": "gemini", "sessions": 1, "engagedSessions": 1, "keyEvents": 0}], "errors": []}, f)
        with open(os.path.join(d_today, "ga4_MCP.json"), "w") as f:
            json.dump({"target_date": "2026-10-04", "ai_engine_referrals_last28": [
                {"sessionSource": "chatgpt.com", "sessions": 58, "engagedSessions": 52, "keyEvents": 261}], "errors": []}, f)
        with open(os.path.join(d_today, "ga4_organic_MCP.json"), "w") as f:
            json.dump({"target_date": "2026-10-04", "ai_referrals_by_landing_last28": [
                {"sessionSource": "chatgpt.com", "landingPage": "/", "sessions": 58, "engagedSessions": 52,
                 "keyEvents": 133}]}, f)
        with open(os.path.join(d_today, "ga4_NOI.json"), "w") as f:
            json.dump({"target_date": "2026-10-04", "ai_engine_referrals_last28": [
                {"sessionSource": "chatgpt.com", "sessions": 43, "engagedSessions": 3, "keyEvents": 4}], "errors": []}, f)
        hdr = "Keyword;Position;Previous Position;Search Volume;Url;Traffic;Position type;Timestamp"
        new_ts, old_ts = 1789423423, 1727000000  # 2026-09-14 and 2024-09-22
        md = ["# test", "", "## SBMW, sterlingbmw.com", "", "```", hdr,
              "sterling bmw;1;1;4400;https://www.sterlingbmw.com/;3520;Organic;%d" % new_ts,
              "oc bmw dealers;1;1;140;https://www.sterlingbmw.com/;27;AI overview;%d" % new_ts,
              "bmw lease deals;2;2;900;https://www.othersite.com/;10;AI overview;%d" % new_ts,
              "bmw x5 2024;1;1;900;https://www.sterlingbmw.com/x5;10;AI overview;%d" % old_ts,
              "```", "", "## MCP, mcpeeks.com", "", "```", hdr,
              "mcpeeks;1;1;320;https://www.mcpeeks.com/;256;Organic;%d" % new_ts, "```", ""]
        with open(os.path.join(d_today, SEMRUSH_MD), "w") as f:
            f.write("\n".join(md))

        result, written = run(today, d_today)
        by = {s["store"]: s for s in result["stores"]}
        s1, s2 = by["SBMW"]["sentences"]["search_value"], by["SBMW"]["sentences"]["ai_visibility"]
        check("rank history found 28 days back", result["rank_history"] and result["rank_history"]["folder_days_back"] == 28)
        check("no ToS caution inside 30 days", result["rank_history"] and not result["rank_history"]["caution"])
        check("SBMW value $16,350 as of August 2026", "$16,350" in s1 and "as of August 2026" in s1)
        check("SBMW labeled Semrush estimate", s1.startswith("Semrush estimates"))
        check("SBMW MoM up 3% from $15,897", "up 3% from $15,897 in July." in s1)
        check("SBMW visits rounded", "about 12,700 visits a month" in s1)
        check("NOI MoM about flat", "about flat from $14,261 in July." in by["NOI"]["sentences"]["search_value"])
        check("MCP single month, no MoM", "July" not in by["MCP"]["sentences"]["search_value"])
        check("SBMW GA4 total and engines", "124 visits" in s2 and "ChatGPT 118, Gemini 6" in s2)
        check("SBMW GA4 window", "Sep 7 to Oct 4, 2026" in s2)
        check("SBMW measured wording", s2.startswith("Google Analytics measured"))
        check("SBMW AIO own keyword", '"oc bmw dealers"' in s2 and "1 of the 2 top searches" in s2)
        check("SBMW AIO other host excluded", "bmw lease deals" not in s2)
        check("SBMW AIO row older than 12 months dropped", "bmw x5 2024" not in s2)
        check("SBMW brand scope not non-brand", "non-brand" not in s2)
        check("NOI low-engagement note", any("3 of 43" in n for n in by["NOI"]["notes"]))
        mcp_blob = json.dumps(by["MCP"])
        md_text = open(written[1]).read()
        mcp_md = md_text.split("## MCP,")[1].split("\n## ")[0]
        check("MCP key events never in JSON", "261" not in mcp_blob and "133" not in mcp_blob)
        check("MCP key events never in md", "261" not in mcp_md and "133" not in mcp_md and "key events)" not in mcp_md)
        check("MCP key events withheld stated", "withheld" in mcp_md)
        check("MCP sessions shown", "58 visits" in by["MCP"]["sentences"]["ai_visibility"])
        check("MCP no AIO in list", "no Google AI Overview citing the site among the 1 top search Semrush lists" in by["MCP"]["sentences"]["ai_visibility"])
        at = by["ATLAS"]
        check("ATLAS value rise on flat visits said", "up 78% from $9,108 in July while estimated visits held about flat"
              in at["sentences"]["search_value"])
        check("ATLAS GA4 and keywords missing, still listed", len(at["not_available"]) == 2)
        check("MCP pull note carried", any("Near-zero in spring 2026." in n for n in by["MCP"]["notes"]))
        check("SBMW no divergence clause", "estimated visits" not in s1)
        check("NCBMW keyword data not available", "not available" in by["NCBMW"]["sentences"]["ai_visibility"])
        check("no em or en dashes in outputs", all(ch not in md_text + json.dumps(result, ensure_ascii=False)
                                                    for ch in (chr(0x2014), chr(0x2013))))
        # Beyond the lookback: nothing found, sentence says not available.
        far = os.path.join(root, "2026-10-08", "data")
        os.makedirs(far)
        r2, _ = run("2026-10-08", far)
        check("37 days back is outside the lookback", r2["rank_history"] is None and
              "not available" in r2["stores"][0]["sentences"]["search_value"])
        # A rank history month more than 12 months old never reaches a sentence.
        parsed = parse_rank_history(rh)
        sv = search_value("SBMW", {"path": "x", "parsed": parsed}, dt.date(2027, 9, 20))
        check("13-month-old month dropped", not sv["ok"] and "12 months" in sv["missing"])
        # Other shapes: the older "months" dicts and raw semicolon text.
        p_months = parse_rank_history({"stores": {"NOI": {"months": [
            {"date": "20260715", "organic_cost_usd": 14261, "organic_traffic": 7584},
            {"date": "20260815", "organic_cost_usd": 14079, "organic_traffic": 7209}]}}})
        check("months shape parsed newest first", p_months["NOI"]["rows"][0] == {
            "date": "2026-08-15", "organic_cost": 14079, "organic_traffic": 7209, "organic_keywords": None,
            "ai_overview_keywords": None})
        p_text = parse_rank_history({"stores": {"MCP": {"data": "Date;Organic Keywords;Organic Traffic;Organic Cost\n"
                                                                 "20260815;2311;4716;13648\n20260715;2270;4349;10974"}}})
        check("semicolon text parsed", p_text["MCP"]["rows"][1]["organic_cost"] == 10974)
        check("engine names", [engine_of(x) for x in ("chatgpt.com/", "gemini", "perplexity.ai", "copilot.com", "foo.ai")]
              == ["ChatGPT", "Gemini", "Perplexity", "Copilot", "foo.ai"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    bad = [n for n, ok in checks if not ok]
    for n in bad:
        print("FAIL " + n)
    print("selftest %s: %d of %d checks passed" % ("OK" if not bad else "FAILED", len(checks) - len(bad), len(checks)))
    return 1 if bad else 0


if __name__ == "__main__":
    main()
