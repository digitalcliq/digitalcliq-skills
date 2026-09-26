#!/usr/bin/env python3
"""GA4 x Semrush (x Search Console) organic join for the DigitalCLIQ AI team. Standard library only.

  python3 .claude/skills/ai-team/scripts/seo_join.py --date 2026-09-23
  python3 .claude/skills/ai-team/scripts/seo_join.py --date 2026-09-23 --data outputs/ai-team/2026-09-23/data

Reads DIR (default outputs/ai-team/{date}/data, relative to the vault root where the shift runs):
  ga4_organic_{STORE}.json    gdata.py ga4-nightly (falls back to ga4_{STORE}.json): organic_landing_last28, organic_landing_prior28,
                              organic_landing_events_last28, ai_referrals_by_landing_last28
  semrush_kw_{STORE}.csv      raw execute_report text (semicolon rows with the header line; the JSON
                              envelope with a "data" field also works)
  semrush_organic_positions.md  fallback for any store without a csv: "## STORE, domain" sections,
                              each with one fenced block of the same semicolon rows
  gsc_{STORE}.json            optional, gdata.py gsc-nightly

Writes DIR/seo_join_{STORE}.json (every joined row and every flag) and DIR/seo_join.md
(per store: top rows and at most 5 flags). Prints the missing inputs every run.

Join key per store: URL path, lowercased, without scheme, "www.", query string, fragment, and
trailing slash (root stays "/"). A utm_campaign of googlemybusiness, scgooglemybusiness, or listings
(GA4 also uses gmb, gbp, google_my_business) puts the row on surface "gbp"; any other tagged campaign
that GA4 files under Organic Search goes to surface "tagged"; the rest is "web". Every vehicle detail
page collapses into "[vdp]" and every search results page into "[srp new|used|cpo|all]".

Semrush "Position type" decides what counts: Local pack and Knowledge panel rows are the same keyword
on another SERP surface, so they never count toward estimated organic traffic.

Flags:
  EST_NO_TRAFFIC  Semrush est monthly traffic x 28/30 >= 30 and GA4 organic last 28 days < 25% of it.
                  Sub-tag when gsc_{STORE}.json exists: GSC_AGREES (GSC clicks also < 25%),
                  GSC_DISAGREES (GSC sees the clicks, so GA4 is missing them), GSC_NO_ROW.
  GA4_WIN_NO_KW   >= 20 GA4 organic sessions (web surface) and no keyword for that URL in the
                  Semrush pull. BRAND when the path is "/", else LONG_TAIL. The pull is top rows by
                  traffic only, so this means "not in this pull", never "Semrush has nothing".
  MOVE_MATCH      a keyword moved >= 3 positions on volume >= 500 and GA4 organic sessions moved
                  >= 25% last 28 vs prior 28 (20-session floor). ALIGNED or DIVERGED.
  AEO_PROOF       >= 5 AI-engine referral sessions on a page. AIO_CONFIRMED when Semrush has an
                  AI overview row for that URL, else AI_REFERRALS_ONLY (NO_SEMRUSH without data).
  LEAD_LEAK       >= 30 GA4 organic sessions and 0 key events.
"""
import argparse
import collections
import datetime as dt
import json
import os
import re
import sys
import urllib.parse

STORES = ["SBMW", "NCBMW", "NOI", "MCP", "ATLAS"]
SEMRUSH_MD = "semrush_organic_positions.md"

NOT_SET = "(not set)"
SURFACE_ONLY_TYPES = {"local pack", "knowledge panel"}  # never organic traffic
AI_OVERVIEW_TYPE = "ai overview"
GBP_RE = re.compile(r"^(sc)?(googlemybusiness|google[_-]my[_-]business|gmb|gbp|listings?)")
GA4_WEB_CAMPAIGNS = {"", "(organic)", "(referral)", "(not set)", "(direct)"}

# Vehicle detail pages: a VIN (17 chars, no I/O/Q, last 4 numeric) as its own path token, or a
# platform VDP route. Search results pages: inventory-style first path segment without a VIN.
VIN_RE = re.compile(r"(?<![a-z0-9])[a-hj-npr-z0-9]{13}[0-9]{4}(?![a-z0-9])")
VDP_MARKERS = ("/viewdetails/", "/vehicle-details/", "/vehicledetails/", "/inventory/display/", "/vdp/")
SRP_ROOTS = {"inventory", "new-vehicles", "used-vehicles", "new-inventory", "used-inventory",
             "searchnew", "searchused", "searchall", "new-cars", "used-cars", "pre-owned",
             "pre-owned-vehicles", "certified-pre-owned", "certified-pre-owned-vehicles", "cpo",
             "new", "used", "certified"}
# Key event names that are page visits, not leads (seen on MCP: new_VDP_visit, used_vlp).
VISIT_EVENT_RE = re.compile(r"visit|(^|_)(vdp|vlp|srp)($|_)|page_view", re.I)

EST_MIN_28D = 30.0
EST_GA4_SHARE = 0.25
WIN_MIN_SESSIONS = 20
MOVE_MIN_POSITIONS = 3
MOVE_MIN_VOLUME = 500
MOVE_MIN_PCT = 25.0
MOVE_SESSION_FLOOR = 20
AEO_MIN_SESSIONS = 5
LEAK_MIN_SESSIONS = 30
MD_TOP_ROWS = 10
MD_MAX_FLAGS = 5
FLAG_ORDER = ["LEAD_LEAK", "EST_NO_TRAFFIC", "MOVE_MATCH", "AEO_PROOF", "GA4_WIN_NO_KW"]

SEM_COLUMNS = {
    "keyword": ("keyword", "ph"),
    "position": ("position", "po"),
    "previous_position": ("previous position", "pp"),
    "position_difference": ("position difference", "pd"),
    "volume": ("search volume", "nq"),
    "url": ("url", "ur"),
    "traffic": ("traffic", "tr"),
    "position_type": ("position type",),
    "timestamp": ("timestamp", "ts"),
}


# ---------------------------------------------------------------- URL handling

def split_url(raw):
    """(host without www., normalized path, lowercased query dict) for a URL or a GA4 landing path."""
    s = (raw or "").strip()
    if not s or s.lower() in (NOT_SET, "(not provided)", "(other)"):
        return "", NOT_SET, {}
    if s.startswith("//"):
        s = "http:" + s
    if "://" not in s and not s.startswith("/") and "." in s.split("/")[0]:
        s = "http://" + s
    if "://" in s:
        parts = urllib.parse.urlsplit(s)
        host = parts.netloc.lower().split("@")[-1].split(":")[0]
        path, query = parts.path, parts.query
    else:
        host = ""
        path, _, query = s.partition("?")
        path = path.partition("#")[0]
        query = query.partition("#")[0]
    if host.startswith("www."):
        host = host[4:]
    q = {k.lower(): v.lower() for k, v in urllib.parse.parse_qsl(query, keep_blank_values=True)}
    path = re.sub(r"/{2,}", "/", urllib.parse.unquote(path).lower())
    if not path.startswith("/"):
        path = "/" + path
    return host, path.rstrip("/") or "/", q


def bucket(path):
    """(join key, page_type) with VDPs and SRPs collapsed."""
    if path == NOT_SET:
        return NOT_SET, "not_set"
    if path == "/":
        return "/", "home"
    slashed = path + "/"
    if VIN_RE.search(path) or any(m in slashed for m in VDP_MARKERS):
        return "[vdp]", "vdp"
    first = path.strip("/").split("/")[0].split(".")[0]
    if first in SRP_ROOTS:
        tokens = set(re.split(r"[/\-_+.]", path))
        if tokens & {"certified", "cpo"}:
            cond = "cpo"
        elif "used" in tokens or "searchused" in tokens or {"pre", "owned"} <= tokens or "preowned" in tokens:
            cond = "used"
        elif "new" in tokens or "searchnew" in tokens:
            cond = "new"
        else:
            cond = "all"
        return "[srp %s]" % cond, "srp"
    return path, "page"


def campaign_surface(campaign, web_values=GA4_WEB_CAMPAIGNS):
    c = (campaign or "").strip().lower()
    if c in web_values:
        return "web"
    if GBP_RE.match(c):
        return "gbp"
    return "tagged"


# ---------------------------------------------------------------- Semrush parsing

def _num(v, kind=int):
    v = (v or "").strip()
    if v in ("", "-", "n/a"):
        return 0
    try:
        return kind(float(v)) if kind is int else float(v)
    except ValueError:
        return 0


def parse_semrush_text(text):
    """Rows from execute_report output. Returns (rows, note). Handles the JSON envelope, error text,
    and plain semicolon text with Semrush display-name (or export-code) headers."""
    text = (text or "").strip()
    if text.startswith("{"):
        try:
            env = json.loads(text)
        except ValueError:
            return [], "unparseable JSON"
        if isinstance(env.get("data"), str):
            text = env["data"].strip()
        else:
            return [], "no csv data in envelope: %s" % str(env.get("message") or env.get("code") or env)[:120]
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return [], "empty"
    hdr_i = None
    for i, ln in enumerate(lines):
        first = ln.split(";")[0].strip().lower()
        if ";" in ln and first in SEM_COLUMNS["keyword"]:
            hdr_i = i
            break
    if hdr_i is None:
        return [], "no header line (%s)" % lines[0][:80]
    header = [h.strip().lower() for h in lines[hdr_i].split(";")]
    idx = {}
    for field, names in SEM_COLUMNS.items():
        for n in names:
            if n in header:
                idx[field] = header.index(n)
                break
    if "keyword" not in idx or "url" not in idx:
        return [], "header lacks Keyword or Url"
    rows, bad = [], 0
    for ln in lines[hdr_i + 1:]:
        f = ln.split(";")
        if len(f) != len(header):
            bad += 1
            continue
        get = lambda k: f[idx[k]] if k in idx else ""
        pos, prev = _num(get("position")), _num(get("previous_position"))
        diff = _num(get("position_difference")) if "position_difference" in idx else (prev - pos if prev and pos else 0)
        rows.append({
            "keyword": get("keyword").strip(),
            "position": pos,
            "previous_position": prev,
            "position_difference": diff,
            "volume": _num(get("volume")),
            "url": get("url").strip(),
            "traffic": _num(get("traffic"), float),
            "position_type": (get("position_type") or "Organic").strip(),
            "timestamp": _num(get("timestamp")),
        })
    return rows, ("%d malformed line(s) skipped" % bad) if bad else ""


def parse_semrush_md(path):
    """{STORE: rows} from the lead's markdown file ("## SBMW, sterlingbmw.com" plus one fenced block)."""
    out, store, block = {}, None, None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("## "):
                m = re.match(r"##\s+([A-Za-z0-9]+)", line)
                store = m.group(1).upper() if m else None
                continue
            if line.strip().startswith("```"):
                if block is None:
                    block = []
                else:
                    if store:
                        out.setdefault(store, []).extend(parse_semrush_text("\n".join(block))[0])
                    block = None
                continue
            if block is not None:
                block.append(line.rstrip("\n"))
    return out


def ts_date(ts):
    try:
        return dt.datetime.fromtimestamp(int(ts)).date().isoformat() if ts else None
    except (ValueError, OSError, OverflowError):
        return None


# ---------------------------------------------------------------- join

def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def new_row(key, surface, ptype):
    return {"key": key, "surface": surface, "page_type": ptype, "example_paths": collections.Counter(),
            "ga4_sessions_last28": 0, "ga4_engaged_last28": 0, "ga4_key_events_last28": 0,
            "ga4_sessions_prior28": 0, "ga4_key_events_prior28": 0, "ga4_change_pct": None,
            "ga4_campaigns": collections.Counter(), "key_events_by_name": {},
            "ai_sessions_last28": 0, "ai_engaged_last28": 0, "ai_key_events_last28": 0,
            "ai_sources": collections.Counter(),
            "semrush_keywords": 0, "semrush_organic_keywords": 0, "semrush_est_monthly": 0.0,
            "semrush_est_28d": 0.0, "semrush_surface_only_traffic": 0.0, "semrush_ai_overview": False,
            "semrush_best_position": None, "semrush_top": [], "semrush_moves": [], "_kw": [],
            "gsc_clicks_last28": None, "gsc_impressions_last28": None, "gsc_clicks_prior28": None,
            "gsc_position_last28": None, "gsc_top_queries": [], "flags": []}


def pct(a, b):
    return None if not b else round((a - b) / float(b) * 100.0, 1)


LOOKBACK_DAYS = 7  # Semrush keyword pulls are weekly (Monday); weekday runs reuse the latest one


def recent_file(data_dir, date, name):
    """Newest copy of `name` in this shift's data folder or up to LOOKBACK_DAYS earlier shift folders.
    Only looks back when data_dir is the standard outputs/ai-team/{date}/data layout."""
    here = os.path.join(data_dir, name)
    if os.path.exists(here) or not date:
        return here
    root = os.path.dirname(os.path.dirname(os.path.normpath(data_dir)))
    if os.path.normpath(data_dir) != os.path.normpath(os.path.join(root, date, "data")):
        return here
    day = dt.date.fromisoformat(date)
    for back in range(1, LOOKBACK_DAYS + 1):
        cand = os.path.join(root, (day - dt.timedelta(days=back)).isoformat(), "data", name)
        if os.path.exists(cand):
            return cand
    return here


def join_store(store, data_dir, md_rows, date=None):
    missing, notes = [], []
    inputs = {"ga4": None, "semrush": None, "gsc": None}
    rows = {}

    def row(key, surface, ptype):
        if (key, surface) not in rows:
            rows[(key, surface)] = new_row(key, surface, ptype)
        return rows[(key, surface)]

    # ---- GA4
    # gdata.py ga4-nightly writes the organic sections to ga4_organic_{STORE}.json (2026-09-23);
    # files pulled earlier the same day kept them inside ga4_{STORE}.json.
    ga4_path = os.path.join(data_dir, "ga4_organic_%s.json" % store)
    if not os.path.exists(ga4_path):
        ga4_path = os.path.join(data_dir, "ga4_%s.json" % store)
    ga = load_json(ga4_path)
    ga_ok = {}
    if ga is None:
        missing.append("ga4_%s.json" % store)
    else:
        inputs["ga4"] = {"path": ga4_path, "target_date": ga.get("target_date"),
                         "windows": ga.get("organic_windows")}
        for sec in ("organic_landing_last28", "organic_landing_prior28",
                    "organic_landing_events_last28", "ai_referrals_by_landing_last28"):
            if sec not in ga:
                missing.append("ga4_%s.json:%s (rerun gdata.py ga4-nightly)" % (store, sec))
            elif ga.get(sec) is None:
                missing.append("ga4_%s.json:%s (pull errored, see its errors list)" % (store, sec))
            else:
                ga_ok[sec] = ga[sec]
    not_set_sessions = 0
    for sec, suffix in (("organic_landing_last28", "last28"), ("organic_landing_prior28", "prior28")):
        for r in ga_ok.get(sec) or []:
            _, path, _ = split_url(r.get("landingPage"))
            key, ptype = bucket(path)
            camp = r.get("sessionCampaignName") or ""
            rw = row(key, campaign_surface(camp), ptype)
            s = int(r.get("sessions") or 0)
            rw["ga4_sessions_" + suffix] += s
            rw["ga4_key_events_" + suffix] += int(r.get("keyEvents") or 0)
            if suffix == "last28":
                rw["ga4_engaged_last28"] += int(r.get("engagedSessions") or 0)
                rw["example_paths"][path] += s
                if camp.lower() not in GA4_WEB_CAMPAIGNS:
                    rw["ga4_campaigns"][camp] += s
                if key == NOT_SET:
                    not_set_sessions += s
        if len(ga_ok.get(sec) or []) >= 500:
            notes.append("GA4 %s hit the 500-row cap, so the long tail is cut." % sec)
    events_by_key = collections.defaultdict(collections.Counter)
    for r in ga_ok.get("organic_landing_events_last28") or []:
        _, path, _ = split_url(r.get("landingPage"))
        events_by_key[bucket(path)[0]][r.get("eventName") or "?"] += int(r.get("keyEvents") or 0)
    for r in ga_ok.get("ai_referrals_by_landing_last28") or []:
        _, path, _ = split_url(r.get("landingPage"))
        key, ptype = bucket(path)
        rw = row(key, "web", ptype)
        s = int(r.get("sessions") or 0)
        rw["ai_sessions_last28"] += s
        rw["ai_engaged_last28"] += int(r.get("engagedSessions") or 0)
        rw["ai_key_events_last28"] += int(r.get("keyEvents") or 0)
        rw["ai_sources"][r.get("sessionSource") or "?"] += s

    # ---- Semrush
    csv_path = recent_file(data_dir, date, "semrush_kw_%s.csv" % store)
    sem, csv_problem = None, "missing"
    if os.path.exists(csv_path):
        with open(csv_path, encoding="utf-8", errors="replace") as f:
            sem, note = parse_semrush_text(f.read())
        if sem:
            inputs["semrush"] = {"source": csv_path, "rows": len(sem)}
            if note:
                notes.append("Semrush csv: " + note)
        else:
            sem, csv_problem = None, "has 0 rows: %s" % (note or "empty")
    if sem is None:
        if store in md_rows:
            sem = md_rows[store]
            inputs["semrush"] = {"source": os.path.join(data_dir, SEMRUSH_MD), "rows": len(sem)}
            missing.append("semrush_kw_%s.csv %s (used %s)" % (store, csv_problem, SEMRUSH_MD))
        else:
            missing.append("semrush_kw_%s.csv %s (and no %s section in %s)" % (store, csv_problem, store, SEMRUSH_MD))
    if sem:
        stamps = [r["timestamp"] for r in sem if r["timestamp"]]
        inputs["semrush"]["oldest"] = ts_date(min(stamps)) if stamps else None
        inputs["semrush"]["newest"] = ts_date(max(stamps)) if stamps else None
        hosts = collections.Counter(split_url(r["url"])[0] for r in sem if r["url"])
        main_host = hosts.most_common(1)[0][0] if hosts else ""
        for r in sem:
            host, path, q = split_url(r["url"])
            key, ptype = bucket(path)
            if host and main_host and host != main_host:
                key, ptype = host + path, "other_host"
            surface = campaign_surface(q.get("utm_campaign", ""), web_values={""})
            rw = row(key, surface, ptype)
            rw["example_paths"][path] += 0
            rw["_kw"].append(r)
    semrush_loaded = bool(sem)  # a csv that parsed to zero rows proves nothing about keywords

    # ---- GSC (optional)
    gsc_path = os.path.join(data_dir, "gsc_%s.json" % store)
    gsc = load_json(gsc_path)
    if gsc is None:
        missing.append("gsc_%s.json (optional)" % store)
    else:
        inputs["gsc"] = {"path": gsc_path, "windows": gsc.get("windows"), "site_url": gsc.get("site_url")}
        for sec, suffix in (("pages_last28", "last28"), ("pages_prior28", "prior28")):
            if gsc.get(sec) is None:
                missing.append("gsc_%s.json:%s" % (store, sec))
            for r in gsc.get(sec) or []:
                host, path, q = split_url(r.get("page"))
                key, ptype = bucket(path)
                rw = row(key, campaign_surface(q.get("utm_campaign", ""), web_values={""}), ptype)
                rw["gsc_clicks_" + suffix] = (rw["gsc_clicks_" + suffix] or 0) + int(r.get("clicks") or 0)
                if suffix == "last28":
                    imp = int(r.get("impressions") or 0)
                    rw["gsc_impressions_last28"] = (rw["gsc_impressions_last28"] or 0) + imp
                    rw["_gsc_pos_w"] = rw.get("_gsc_pos_w", 0.0) + float(r.get("position") or 0) * imp
        queries = collections.defaultdict(list)
        for r in gsc.get("page_query_last28") or []:
            host, path, q = split_url(r.get("page"))
            key, _ = bucket(path)
            queries[(key, campaign_surface(q.get("utm_campaign", ""), web_values={""}))].append(r)
        for k, qs in queries.items():
            if k in rows:
                qs.sort(key=lambda r: -int(r.get("clicks") or 0))
                rows[k]["gsc_top_queries"] = [{"query": r.get("query"), "clicks": r.get("clicks"),
                                               "impressions": r.get("impressions"),
                                               "position": r.get("position")} for r in qs[:5]]

    # ---- per row rollups
    for (key, surface), rw in rows.items():
        rw["ga4_change_pct"] = pct(rw["ga4_sessions_last28"], rw["ga4_sessions_prior28"])
        rw["key_events_by_name"] = dict(events_by_key.get(key, collections.Counter()).most_common(8))
        if rw.get("_gsc_pos_w") and rw["gsc_impressions_last28"]:
            rw["gsc_position_last28"] = round(rw.pop("_gsc_pos_w") / rw["gsc_impressions_last28"], 1)
        rw.pop("_gsc_pos_w", None)
        kws = rw.pop("_kw")
        if kws:
            organic = [k for k in kws if k["position_type"].lower() not in SURFACE_ONLY_TYPES]
            rw["semrush_keywords"] = len({k["keyword"] for k in kws})
            rw["semrush_organic_keywords"] = len({k["keyword"] for k in organic})
            rw["semrush_est_monthly"] = round(sum(k["traffic"] for k in organic), 1)
            rw["semrush_est_28d"] = round(rw["semrush_est_monthly"] * 28 / 30.0, 1)
            rw["semrush_surface_only_traffic"] = round(sum(k["traffic"] for k in kws) - rw["semrush_est_monthly"], 1)
            rw["semrush_ai_overview"] = any(k["position_type"].lower() == AI_OVERVIEW_TYPE for k in kws)
            ranked = [k["position"] for k in organic if k["position"]]
            rw["semrush_best_position"] = min(ranked) if ranked else None
            top = sorted(kws, key=lambda k: -k["traffic"])[:5]
            rw["semrush_top"] = [{"keyword": k["keyword"], "position": k["position"],
                                  "previous_position": k["previous_position"], "volume": k["volume"],
                                  "traffic": k["traffic"], "type": k["position_type"],
                                  "as_of": ts_date(k["timestamp"])} for k in top]
            seen, moves = set(), []
            for k in sorted(organic, key=lambda k: -k["volume"]):
                if k["keyword"] in seen or not (k["position"] and k["previous_position"]):
                    continue
                if abs(k["previous_position"] - k["position"]) >= MOVE_MIN_POSITIONS and k["volume"] >= MOVE_MIN_VOLUME:
                    seen.add(k["keyword"])
                    moves.append({"keyword": k["keyword"], "from": k["previous_position"], "to": k["position"],
                                  "volume": k["volume"], "as_of": ts_date(k["timestamp"])})
            rw["semrush_moves"] = moves
        rw["example_paths"] = [p for p, _ in rw["example_paths"].most_common(3)]
        rw["ga4_campaigns"] = dict(rw["ga4_campaigns"].most_common(5))
        rw["ai_sources"] = dict(rw["ai_sources"].most_common(5))

    # ---- flags
    flags = []
    for (key, surface), rw in rows.items():
        if key == NOT_SET:
            continue
        s, prior = rw["ga4_sessions_last28"], rw["ga4_sessions_prior28"]

        def add(name, sub, score, detail):
            label = name + (":" + sub if sub else "")
            rw["flags"].append(label)
            flags.append({"flag": name, "sub": sub, "label": label, "key": key, "surface": surface,
                          "page_type": rw["page_type"], "score": round(score, 1), "detail": detail})

        est = rw["semrush_est_28d"]
        if ga_ok.get("organic_landing_last28") is not None and est >= EST_MIN_28D and s < EST_GA4_SHARE * est:
            sub, gsc_txt = None, ""
            if gsc is not None:
                clicks = rw["gsc_clicks_last28"]
                if clicks is None:
                    sub, gsc_txt = "GSC_NO_ROW", " Page not in the GSC pull."
                elif clicks < EST_GA4_SHARE * est:
                    sub, gsc_txt = "GSC_AGREES", " GSC shows %d clicks, so the estimate is high, not the tracking." % clicks
                else:
                    sub, gsc_txt = "GSC_DISAGREES", " GSC shows %d clicks, so GA4 is missing organic sessions." % clicks
            top = rw["semrush_top"][0] if rw["semrush_top"] else {}
            add("EST_NO_TRAFFIC", sub, est - s,
                "Semrush estimates %.0f organic visits per 28 days from %d keyword(s) (top \"%s\" pos %s, vol %s); "
                "GA4 shows %d organic sessions (%.0f%% of the estimate).%s"
                % (est, rw["semrush_organic_keywords"], top.get("keyword", "?"), top.get("position", "?"),
                   top.get("volume", "?"), s, 100.0 * s / est, gsc_txt))
        if semrush_loaded and surface == "web" and s >= WIN_MIN_SESSIONS and rw["semrush_keywords"] == 0:
            add("GA4_WIN_NO_KW", "BRAND" if key == "/" else "LONG_TAIL", s,
                "%d GA4 organic sessions last 28 days, %d key events; no keyword for this URL in the Semrush pull."
                % (s, rw["ga4_key_events_last28"]))
        if rw["semrush_moves"] and max(s, prior) >= MOVE_SESSION_FLOOR and s != prior:
            change = pct(s, prior)
            if change is None or abs(change) >= MOVE_MIN_PCT:
                net = sum((m["from"] - m["to"]) * m["volume"] for m in rw["semrush_moves"])
                aligned = (net > 0) == (s > prior)
                m = rw["semrush_moves"][0]
                add("MOVE_MATCH", "ALIGNED" if aligned else "DIVERGED", abs(s - prior) * (1 if aligned else 2),
                    "\"%s\" (vol %d) moved %d to %d%s; GA4 organic %d to %d (%s)."
                    % (m["keyword"], m["volume"], m["from"], m["to"],
                       (" plus %d more keyword(s)" % (len(rw["semrush_moves"]) - 1)) if len(rw["semrush_moves"]) > 1 else "",
                       prior, s, ("%+.0f%%" % change) if change is not None else "new"))
        if rw["ai_sessions_last28"] >= AEO_MIN_SESSIONS:
            if not semrush_loaded:
                sub = "NO_SEMRUSH"
            else:
                sub = "AIO_CONFIRMED" if any(r2["semrush_ai_overview"] for (k2, _), r2 in rows.items() if k2 == key) \
                    else "AI_REFERRALS_ONLY"
            srcs = ", ".join("%s %d" % kv for kv in rw["ai_sources"].items())
            add("AEO_PROOF", sub, rw["ai_sessions_last28"] * 5,
                "%d AI-engine referral sessions (%s), %d key events.%s"
                % (rw["ai_sessions_last28"], srcs, rw["ai_key_events_last28"],
                   " Semrush also shows an AI Overview citation for this URL." if sub == "AIO_CONFIRMED" else ""))
        if s >= LEAK_MIN_SESSIONS and rw["ga4_key_events_last28"] == 0:
            add("LEAD_LEAK", None, s, "%d organic sessions last 28 days (%d engaged) and 0 key events."
                % (s, rw["ga4_engaged_last28"]))
    flags.sort(key=lambda f: (FLAG_ORDER.index(f["flag"]), -f["score"]))

    # ---- data notes
    if not_set_sessions:
        notes.append("%d organic sessions landed on (not set); left out of every flag." % not_set_sessions)
    tagged = collections.Counter()
    for (key, surface), rw in rows.items():
        if surface == "tagged":
            for c, n in rw["ga4_campaigns"].items():
                tagged[c] += n
    if tagged:
        notes.append("GA4 files these tagged campaigns under Organic Search (surface \"tagged\", not web or GBP): "
                     + ", ".join("%s %d" % kv for kv in tagged.most_common(3)) + ".")
    ev_total = sum(sum(c.values()) for c in events_by_key.values())
    ev_visit = sum(n for c in events_by_key.values() for e, n in c.items() if VISIT_EVENT_RE.search(e))
    if ev_total and ev_visit > ev_total / 2.0:
        top_visit = collections.Counter()
        for c in events_by_key.values():
            for e, n in c.items():
                if VISIT_EVENT_RE.search(e):
                    top_visit[e] += n
        notes.append("%d%% of organic key events are page-visit events (%s), so LEAD_LEAK undercounts here."
                     % (round(100.0 * ev_visit / ev_total), ", ".join("%s %d" % kv for kv in top_visit.most_common(3))))

    out_rows = sorted(rows.values(), key=lambda r: -(r["ga4_sessions_last28"] + r["semrush_est_28d"]))
    return {"store": store, "inputs": inputs, "missing": missing, "notes": notes,
            "flag_counts": dict(collections.Counter(f["flag"] for f in flags)),
            "flags": flags, "rows": out_rows}


def pick_flags(flags, n=MD_MAX_FLAGS):
    """Best flag of each type first (in FLAG_ORDER), then the highest scores left."""
    picked = []
    for name in FLAG_ORDER:
        best = [f for f in flags if f["flag"] == name]
        if best:
            picked.append(max(best, key=lambda f: f["score"]))
    rest = sorted([f for f in flags if f not in picked], key=lambda f: -f["score"])
    return (picked + rest)[:n]


# ---------------------------------------------------------------- output

def fmt_pct(v):
    return "new" if v is None else "%+.0f%%" % v


def md_store(res):
    lines = ["## %s" % res["store"], ""]
    sem = res["inputs"]["semrush"]
    gsc = res["inputs"]["gsc"]
    src = []
    if sem:
        src.append("Semrush: %s, %d rows, keyword dates %s to %s" % (
            os.path.basename(sem["source"]), sem["rows"], sem.get("oldest") or "?", sem.get("newest") or "?"))
    else:
        src.append("Semrush: none")
    src.append("GSC: %s" % ("%s" % gsc["site_url"] if gsc else "none"))
    lines.append("Inputs: " + "; ".join(src) + ".")
    if res["missing"]:
        lines.append("Missing: " + "; ".join(res["missing"]) + ".")
    for n in res["notes"]:
        lines.append("Note: " + n)
    lines.append("")
    top = [r for r in res["rows"] if r["key"] != NOT_SET][:MD_TOP_ROWS]
    if top:
        hdr = "| Page | Surface | GA4 organic 28d | vs prior 28d | Key events | AI referrals | Semrush kw | Semrush est 28d | Best pos |"
        sep = "|---|---|---:|---:|---:|---:|---:|---:|---:|"
        if gsc:
            hdr += " GSC clicks |"
            sep += "---:|"
        lines += [hdr, sep]
        for r in top:
            line = "| %s | %s | %d | %s | %d | %d | %d | %.0f | %s |" % (
                r["key"].replace("|", "/"), r["surface"], r["ga4_sessions_last28"],
                fmt_pct(r["ga4_change_pct"]) if r["ga4_sessions_prior28"] or r["ga4_sessions_last28"] else "",
                r["ga4_key_events_last28"], r["ai_sessions_last28"], r["semrush_keywords"],
                r["semrush_est_28d"], r["semrush_best_position"] or "")
            if gsc:
                line += " %s |" % ("" if r["gsc_clicks_last28"] is None else r["gsc_clicks_last28"])
            lines.append(line)
        lines.append("")
    shown = pick_flags(res["flags"])
    if shown:
        lines.append("Flags (%d total, top %d shown; all of them in seo_join_%s.json):" % (
            len(res["flags"]), len(shown), res["store"]))
        for f in shown:
            lines.append("- **%s** `%s` (%s): %s" % (f["label"], f["key"], f["surface"], f["detail"]))
    else:
        lines.append("Flags: none.")
    lines.append("")
    return lines


def main():
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

    md_path = recent_file(data_dir, args.date, SEMRUSH_MD)
    md_rows = parse_semrush_md(md_path) if os.path.exists(md_path) else {}
    names = os.listdir(data_dir)
    found = set()
    for fn in names:
        m = re.match(r"(?:ga4_organic|ga4|gsc|semrush_kw)_([A-Za-z0-9]+)\.(?:json|csv)$", fn)
        if m:
            found.add(m.group(1).upper())
    stores = STORES + sorted((found | set(md_rows)) - set(STORES))

    md_src = md_path if os.path.exists(md_path) else None
    results = [join_store(s, data_dir, md_rows, args.date) for s in stores]
    if md_src and os.path.dirname(md_src) != os.path.normpath(data_dir):
        for r in results:
            src = (r["inputs"].get("semrush") or {}).get("source", "")
            if src.endswith(SEMRUSH_MD):
                r["inputs"]["semrush"]["source"] = md_src
    results = [r for r in results if any(r["inputs"].values()) or r["store"] in found]
    if not results:
        print("ERROR: no ga4_*.json, semrush_kw_*.csv, %s, or gsc_*.json in %s" % (SEMRUSH_MD, data_dir),
              file=sys.stderr)
        sys.exit(1)

    written = []
    for res in results:
        res["date"] = args.date
        path = os.path.join(data_dir, "seo_join_%s.json" % res["store"])
        with open(path, "w") as f:
            json.dump(res, f, indent=1)
        written.append(path)

    windows = next((r["inputs"]["ga4"]["windows"] for r in results
                    if r["inputs"]["ga4"] and r["inputs"]["ga4"].get("windows")), None)
    md = ["# SEO join: GA4 x Semrush, %s" % args.date, ""]
    if windows:
        md.append("GA4 organic (Organic Search minus AI engine sources): %s to %s vs %s to %s." % (
            windows["last28"][0], windows["last28"][1], windows["prior28"][0], windows["prior28"][1]))
    md += ["Semrush est is monthly traffic x 28/30 from Organic and AI overview rows only; Local pack and "
           "Knowledge panel rows never count. The Semrush pull is top rows by traffic, so \"no keyword\" "
           "means not in this pull. VDPs collapse to [vdp], search pages to [srp ...].", ""]
    for res in results:
        md += md_store(res)
    md_out = os.path.join(data_dir, "seo_join.md")
    with open(md_out, "w") as f:
        f.write("\n".join(md).rstrip() + "\n")
    written.append(md_out)

    print("seo_join %s  data=%s" % (args.date, data_dir))
    print("Missing inputs:")
    any_missing = False
    for res in results:
        if res["missing"]:
            any_missing = True
            print("  %-6s %s" % (res["store"], "; ".join(res["missing"])))
    if not any_missing:
        print("  none")
    skipped = [s for s in stores if s not in {r["store"] for r in results}]
    if skipped:
        print("  no input at all, skipped: %s" % ", ".join(skipped))
    print("Flags:")
    for res in results:
        counts = ", ".join("%s %d" % (k, res["flag_counts"][k]) for k in FLAG_ORDER if k in res["flag_counts"])
        print("  %-6s %s" % (res["store"], counts or "none"))
    print("Wrote:")
    for w in written:
        print("  " + w)


if __name__ == "__main__":
    main()
