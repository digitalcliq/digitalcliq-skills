#!/usr/bin/env python3
"""Measurement Health board for the DigitalCLIQ AI team. Standard library only.

  python3 .claude/skills/ai-team/scripts/health.py --date 2026-09-24
  python3 .claude/skills/ai-team/scripts/health.py --backtest --from 2026-09-19 --to 2026-09-23
  python3 .claude/skills/ai-team/scripts/health.py --backtest --from 2026-09-19 --to 2026-09-23 --write-state
  python3 .claude/skills/ai-team/scripts/health.py selftest

One red, amber, or green per store for tracking integrity, with a days-broken counter, so broken
numbers stay out of the brief and client reports. Every rule, threshold, and "what to do" line lives
in references/measurement-rules.json; this script only evaluates them.

Nightly (--date D) reads outputs/ai-team/D/data/ (then D/run*/data/):
  ga4_{STORE}.json             gdata.py ga4-nightly (required; a store without it is NO DATA)
  ga4_organic_{STORE}.json     gdata.py ga4-nightly since 2026-09-23 (the two organic rules)
  {STORE}_ads_meta.json        the Ads export meta tab (last_run, tab status)
  {STORE}_conversions_by_action_7d.txt|.json   Shaq's dump in any format, or this script's own read
When D is today (Pacific) and an Ads file is missing, the script reads those two tabs itself, read
only, with gdata.py's Google token, and saves them to data/ (skip with --no-pull). A past date never
reads anything live. Missing inputs are listed, never guessed.

Writes data/health.json and data/health.md (the 5-line board first, then details) and records the
night in outputs/ai-team/ledgers/health-state.json. The ledger keeps every night's per-rule result
and is rebuilt from them on each run (first_seen, last_seen, days_broken, cleared_on), so re-running
a date replaces that night and never double counts.

--backtest evaluates every shift folder from --from to --to in date order into a scratch ledger
and prints each night's board. Per-night health files go to --out (default: a temp folder), never
into the past shift folders. --write-state merges those nights into the real ledger.

Options: --data DIR (read and write another folder), --state PATH (another ledger), --rules PATH,
--no-pull, --out DIR (backtest output).
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import sys
import tempfile
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
SHIFTS = os.path.join(ROOT, "outputs", "ai-team")
RULES_PATH = os.path.abspath(os.path.join(HERE, "..", "references", "measurement-rules.json"))
STATE_PATH = os.path.join(SHIFTS, "ledgers", "health-state.json")
EM_DASH = chr(0x2014)  # never written anywhere; outputs replace it with a hyphen
SEV_RANK = {"red": 0, "amber": 1}
COLOR_WORD = {"red": "RED", "amber": "AMBER", "green": "GREEN", "grey": "GREY", "no_data": "NO DATA"}

try:
    from zoneinfo import ZoneInfo
    PACIFIC = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover
    PACIFIC = None


# ---------------------------------------------------------------- small helpers

def pacific_today():
    return (dt.datetime.now(PACIFIC) if PACIFIC else dt.datetime.now()).date()


def d_of(s):
    return dt.date.fromisoformat(s)


def fmt_day(d):
    return "%s %d" % (d.strftime("%b"), d.day)


def fmt_range(a, b):
    if a.month == b.month:
        return "%s to %d" % (fmt_day(a), b.day)
    return "%s to %s" % (fmt_day(a), fmt_day(b))


def pct(x):
    if x is None:
        return "n/a"
    v = x * 100.0
    return ("%.0f%%" % v) if v >= 10 else ("%.1f%%" % v)


def num(x):
    return "{:,}".format(int(round(x)))


def clean_text(s):
    return str(s).replace(EM_DASH, "-")


class SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def fill(template, fields):
    return clean_text(template.format_map(SafeDict(fields)))


def load_json_loose(path):
    """JSON, or a text dump whose first lines are a header before the JSON (Shaq's 9/19 format)."""
    with open(path) as f:
        text = f.read()
    starts = [i for i in (text.find("["), text.find("{")) if i >= 0]
    if not starts:
        raise ValueError("no JSON in %s" % path)
    return json.loads(text[min(starts):])


def find_input(dirs, names):
    for d in dirs:
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    return None


def rel(p):
    try:
        r = os.path.relpath(p, ROOT)
    except ValueError:
        return p
    return os.path.abspath(p) if r.startswith("..") else r


# ---------------------------------------------------------------- rules and classes

def load_rules(path=None):
    with open(path or RULES_PATH) as f:
        cfg = json.load(f)
    ec = cfg["event_classes"]
    cfg["_re"] = {k: re.compile(ec[k], re.I) for k in ("page_view", "lead", "soft", "gbp_campaign", "paid_campaign")}
    cfg["_order"] = {r["id"]: i for i, r in enumerate(cfg["rules"])}
    return cfg


def event_class(cfg, name):
    rx = cfg["_re"]
    if rx["page_view"].search(name):
        return "page_view"
    if rx["lead"].search(name):
        return "lead"
    if rx["soft"].search(name):
        return "soft"
    return "other"


def plain_label(cfg, name):
    """GM words for a non-lead event: page views, form starts, clicks, or soft actions."""
    c, n = event_class(cfg, name), name.lower()
    if c == "page_view":
        return "page views"
    if re.search(r"form.*(engagement|start)|(engagement|start).*form", n):
        return "form starts"
    if "click" in n:
        return "clicks"
    return "soft actions"


# ---------------------------------------------------------------- loading a night

def ads_sheets(cfg):
    return {k: v for k, v in cfg["inputs"]["ads_export_sheets"].items() if k != "source"}


def meta_from_rows(rows):
    kv, tabs, in_tabs = {}, [], False
    for r in rows or []:
        if not r:
            continue
        if len(r) >= 3 and str(r[0]).strip() == "tab" and str(r[2]).strip() == "status":
            in_tabs = True
            continue
        if in_tabs and len(r) >= 3:
            tabs.append({"tab": r[0], "rows": r[1], "status": r[2]})
        elif len(r) >= 2:
            kv[str(r[0]).strip()] = str(r[1]).strip()
    return kv, tabs


def pull_ads_tabs(store, sheet_id, data_dir, want_meta, want_conv):
    """Read the Ads export tabs through gdata.py's token. Read only. Returns (written paths, errors)."""
    written, errors = [], []
    try:
        sys.path.insert(0, HERE)
        import gdata  # noqa: E402  (same folder, standard library only)
    except Exception as e:  # pragma: no cover
        return written, ["cannot import gdata.py: %s" % e]
    jobs = []
    if want_meta:
        jobs.append(("meta!A1:F60", "%s_ads_meta.json" % store))
    if want_conv:
        jobs.append(("conversions_by_action_7d!A1:D500", "%s_conversions_by_action_7d.json" % store))
    for rng, name in jobs:
        try:
            url = "https://sheets.googleapis.com/v4/spreadsheets/%s/values/%s" % (
                sheet_id, urllib.parse.quote(rng, safe=""))
            res = gdata.api(url)
            pack = {"store": store, "range": rng, "source": "health.py read of the Ads export Sheet",
                    "pulled_at": dt.datetime.now().isoformat(timespec="seconds"), "rows": res.get("values", [])}
            p = os.path.join(data_dir, name)
            with open(p, "w") as f:
                json.dump(pack, f, indent=0)
            written.append(p)
        except BaseException as e:  # gdata.die raises SystemExit; never let it end the board
            msg = " ".join(str(e).split())[:160] if str(e) else type(e).__name__
            errors.append("%s %s tab: %s" % (store, rng.split("!")[0], msg))
    return written, errors


def load_night(cfg, date, data_dir=None, pull=False):
    shift = os.path.join(SHIFTS, date)
    if data_dir:
        dirs = [data_dir]
    else:
        dirs = [os.path.join(shift, "data")] + sorted(glob.glob(os.path.join(shift, "run*", "data")), reverse=True)
    out_dir = dirs[0]
    night = {"date": date, "dirs": dirs, "out_dir": out_dir, "stores": {}, "pull_notes": []}
    sheets = ads_sheets(cfg)
    for st in cfg["stores"]:
        s = {"store": st, "inputs": {}, "load_errors": []}
        lo = st.lower()

        def grab(key, names, loader=None):
            p = find_input(dirs, names)
            if not p:
                return None
            try:
                v = (loader or load_json_loose)(p)
                s["inputs"][key] = rel(p)
                s.setdefault("_paths", {})[key] = p
                return v
            except Exception as e:
                s["load_errors"].append("%s: %s" % (rel(p), e))
                return None

        s["ga4"] = grab("ga4", ["ga4_%s.json" % st])
        s["organic"] = grab("ga4_organic", ["ga4_organic_%s.json" % st])
        if st in sheets:
            meta_names = ["%s_ads_meta.json" % st, "%s_meta.json" % st, "%s_meta.txt" % st, "%s_meta.json" % lo]
            conv_names = ["%s_conversions_by_action_7d.json" % st, "%s_conversions_by_action_7d.txt" % st,
                          "%s_conversions_by_action_7d.json" % lo, "%s_conversions_by_action_7d.txt" % lo]
            if pull and os.path.isdir(out_dir):
                need_meta = not find_input(dirs, meta_names)
                need_conv = not find_input(dirs, conv_names)
                if need_meta or need_conv:
                    w, errs = pull_ads_tabs(st, sheets[st], out_dir, need_meta, need_conv)
                    night["pull_notes"] += ["saved %s" % rel(p) for p in w] + ["FAILED " + e for e in errs]
            s["ads_meta_raw"] = grab("ads_meta", meta_names)
            if s["ads_meta_raw"] is not None:
                p = s["_paths"]["ads_meta"]
                s["ads_meta_file_mtime"] = dt.datetime.fromtimestamp(os.path.getmtime(p)).isoformat(timespec="seconds")
            s["ads_conv_raw"] = grab("ads_conversions", conv_names)
        night["stores"][st] = s
    return night


# ---------------------------------------------------------------- evaluation

def res_fire(sev, fields, **extra):
    r = {"status": sev, "fields": fields}
    r.update(extra)
    return r


def res_clean(note=None, **extra):
    r = {"status": "clean"}
    if note:
        r["note"] = note
    r.update(extra)
    return r


def res_nc(reason):
    return {"status": "unchecked", "reason": reason}


def res_na(reason):
    return {"status": "n/a", "reason": reason}


class Env:
    def __init__(self, cfg, date, s):
        self.cfg, self.date, self.s, self.store = cfg, date, s, s["store"]
        g = s.get("ga4") or {}
        self.g = g
        self.T = d_of(g["target_date"]) if g.get("target_date") else None
        if self.T:
            self.window = fmt_range(self.T - dt.timedelta(days=6), self.T)
            self.tday = "%s %s" % (self.T.strftime("%a"), fmt_day(self.T))
        else:
            self.window = self.tday = "unknown dates"

    def sec(self, key):
        if not self.g:
            return None, "no ga4_%s.json" % self.store
        v = self.g.get(key)
        if v is None:
            errs = [e for e in (self.g.get("errors") or []) if str(e).startswith(key)]
            return None, "section %s %s" % (key, ("errored: " + errs[0][:120]) if errs else "not in the file")
        return v, None

    def events_last7(self):
        rows, err = self.sec("key_events_by_channel_last7")
        if err:
            return None, None, err
        tot, by_ch = {}, {}
        for r in rows:
            k = r.get("keyEvents") or 0
            if k <= 0:
                continue
            e = r.get("eventName") or "(unknown)"
            tot[e] = tot.get(e, 0) + k
            by_ch.setdefault(e, {})[r.get("sessionDefaultChannelGroup") or "(unknown)"] = k
        return tot, by_ch, None


def chk_ke_rate_high(env, rule):
    p = rule["params"]
    daily, err = env.sec("channel_daily_last7")
    if err:
        return res_nc(err)
    s7 = sum(r.get("sessions") or 0 for r in daily)
    k7 = sum(r.get("keyEvents") or 0 for r in daily)
    if s7 <= 0:
        return res_nc("no sessions in channel_daily_last7")
    tkey = env.T.strftime("%Y%m%d") if env.T else ""
    st = sum(r.get("sessions") or 0 for r in daily if r.get("date") == tkey)
    kt = sum(r.get("keyEvents") or 0 for r in daily if r.get("date") == tkey)
    rate7, rate_t = k7 / s7, (kt / st if st else None)
    f = {"rate7": pct(rate7), "k7": num(k7), "s7": num(s7), "kt": num(kt), "st": num(st),
         "rate_t": pct(rate_t), "window": env.window, "tday": env.tday}
    vals = {"rate_7d": round(rate7, 4), "rate_target_day": round(rate_t, 4) if rate_t is not None else None}
    if s7 >= p["min_sessions_7d"] and rate7 > p["red_rate_7d"]:
        return res_fire("red", f, value=vals)
    if rate_t is not None and st >= p["min_sessions_target_day"] and rate_t > p["red_rate_target_day"]:
        return res_fire("red", f, value=vals)
    if s7 >= p["min_sessions_7d"] and rate7 > p["amber_rate_7d"]:
        return res_fire("amber", f, value=vals)
    return res_clean(value=vals)


def chk_ke_collapse(env, rule):
    p, cfg = rule["params"], env.cfg
    findings, sev, vals, ran = [], None, {}, False

    def worse(a, b):
        if a is None:
            return b
        if b is None:
            return a
        return a if SEV_RANK[a] <= SEV_RANK[b] else b

    daily, err = env.sec("channel_daily_last7")
    base = (cfg.get("baselines") or {}).get(env.store)
    if base and not err:
        s7 = sum(r.get("sessions") or 0 for r in daily)
        k7 = sum(r.get("keyEvents") or 0 for r in daily)
        if s7 > 0:
            ran = True
            rate7, b = k7 / s7, base["key_event_rate_7d"]
            vals.update({"rate_7d": round(rate7, 4), "baseline": b})
            s = None
            if rate7 < b * p["red_fraction_of_baseline"]:
                s = "red"
            elif rate7 < b * p["amber_fraction_of_baseline"]:
                s = "amber"
            if s:
                sev = worse(sev, s)
                findings.append("%s of visits vs a %s baseline before %s, %s on %s (%s)" % (
                    pct(rate7), pct(b), fmt_day(d_of(base["since"])), num(k7), num(s7), env.window))
    kl, e1 = env.sec("key_events_by_channel_last7")
    kp, e2 = env.sec("key_events_by_channel_prior7")
    sl, e3 = env.sec("source_medium_last7")
    sp, e4 = env.sec("source_medium_prior7")
    wow_err = e1 or e2 or e3 or e4
    if not wow_err:
        lead_l = sum(r.get("keyEvents") or 0 for r in kl if event_class(cfg, r.get("eventName") or "") == "lead")
        lead_p = sum(r.get("keyEvents") or 0 for r in kp if event_class(cfg, r.get("eventName") or "") == "lead")
        ss_l = sum(r.get("sessions") or 0 for r in sl)
        ss_p = sum(r.get("sessions") or 0 for r in sp)
        vals.update({"lead_events_last7": lead_l, "lead_events_prior7": lead_p})
        if lead_p >= p["min_prior_lead_events"] and ss_l > 0 and ss_p > 0:
            ran = True
            rl, rp = lead_l / ss_l, lead_p / ss_p
            drop = 1.0 - rl / rp
            vals["lead_rate_drop_wow"] = round(drop, 3)
            s = None
            if drop >= p["red_drop_wow"]:
                s = "red"
            elif drop >= p["amber_drop_wow"]:
                s = "amber"
            if s:
                sev = worse(sev, s)
                findings.append("lead events per visit down %s week over week, %d vs %d" % (pct(drop), lead_l, lead_p))
        elif not ran:
            ran = True  # checked: too few prior lead events to judge a drop, no baseline on file
            vals["note"] = "prior week had %d lead events, under the %d floor" % (lead_p, p["min_prior_lead_events"])
    if not ran:
        return res_nc(err or wow_err or "nothing to compare")
    if sev:
        return res_fire(sev, {"finding": findings[0], "finding_all": "; ".join(findings), "window": env.window}, value=vals)
    return res_clean(value=vals)


def chk_non_lead_key_events(env, rule):
    p, cfg = rule["params"], env.cfg
    tot, _by, err = env.events_last7()
    if err:
        return res_nc(err)
    total = sum(tot.values())
    if total <= 0:
        return res_clean("no key events in the window")
    cls = {e: event_class(cfg, e) for e in tot}
    non = {e: k for e, k in tot.items() if cls[e] in ("page_view", "soft")}
    lead = {e: k for e, k in tot.items() if cls[e] == "lead"}
    other = {e: k for e, k in tot.items() if cls[e] == "other"}
    n_non = sum(non.values())
    share = n_non / total
    vals = {"non_lead_share": round(share, 3), "total": total, "non_lead": n_non, "lead": sum(lead.values())}
    if n_non < p["min_non_lead_events"] or share < p["amber_share"]:
        return res_clean(value=vals)
    top = sorted(non.items(), key=lambda kv: -kv[1])
    top_e = top[0][0]
    labels = []
    for e, _k in top:
        lb = plain_label(cfg, e)
        if lb not in labels:
            labels.append(lb)
    lead_total = sum(lead.values())
    infl = (total / lead_total) if lead_total else None
    f = {"share": pct(share), "total": num(total), "window": env.window,
         "top_plain": "%s (%s)" % (plain_label(cfg, top_e).capitalize(), top_e),
         "class_plain": " and ".join(labels[:2]),
         "inflation": ("%.0f times" % infl if infl >= 10 else "%.1f times" % infl) if infl else "many times",
         "non_lead_events": ", ".join("%s %s" % (e, num(k)) for e, k in top[:6]) + (" and %d more" % (len(top) - 6) if len(top) > 6 else ""),
         "lead_events": (", ".join("%s %s" % (e, num(k)) for e, k in sorted(lead.items(), key=lambda kv: -kv[1]))
                         or "no lead-class events (none to fall back on)"),
         "other_events": ", ".join(sorted(other)) or "none"}
    sev = "red" if share >= p["red_share"] else "amber"
    return res_fire(sev, f, value=vals)


def chk_duplicate_lead_events(env, rule):
    p, cfg = rule["params"], env.cfg
    tot, by, err = env.events_last7()
    if err:
        return res_nc(err)
    cands = sorted(e for e, k in tot.items() if k >= p["min_total"] and event_class(cfg, e) in ("lead", "other"))
    pairs = []
    for i, a in enumerate(cands):
        for b in cands[i + 1:]:
            if tot[a] == tot[b] and (not p.get("require_channel_match", True) or by[a] == by[b]):
                pairs.append((a, b, tot[a], len(by[a])))
    if not pairs:
        return res_clean()
    f = {"pairs": "; ".join("%s and %s, %s each across %d channels" % (a, b, num(n), c) for a, b, n, c in pairs),
         "window": env.window}
    return res_fire("amber", f, value={"pairs": [[a, b, n] for a, b, n, _ in pairs]})


def chk_landing_page_load_trigger(env, rule):
    p, cfg = rule["params"], env.cfg
    lp, err = env.sec("landing_pages_last7")
    if err:
        return res_nc(err)
    flagged = []
    for r in lp:
        s, k, eng = r.get("sessions") or 0, r.get("keyEvents") or 0, r.get("engagementRate") or 0
        if s < p["min_sessions"]:
            continue
        if (k >= s and eng >= p["min_engagement"]) or k >= p["multi_fire_ratio"] * s:
            flagged.append(r)
    if not flagged:
        return res_clean()
    pages = {}
    for r in flagged:
        path = (r.get("landingPagePlusQueryString") or "(unknown)").split("?")[0] or "/"
        e = pages.setdefault(path, {"ke": 0, "sessions": 0})
        e["ke"] += r.get("keyEvents") or 0
        e["sessions"] += r.get("sessions") or 0
    order = sorted(pages.items(), key=lambda kv: -kv[1]["ke"])
    fke = sum(v["ke"] for v in pages.values())
    fs = sum(v["sessions"] for v in pages.values())
    tot, _by, err2 = env.events_last7()
    store_ke = sum(tot.values()) if tot else None
    share = (fke / store_ke) if store_ke else None
    non_share, top_non = 0.0, None
    if tot:
        non = {e: k for e, k in tot.items() if event_class(cfg, e) in ("page_view", "soft")}
        non_share = sum(non.values()) / max(sum(tot.values()), 1)
        top_non = max(non.items(), key=lambda kv: kv[1])[0] if non else None
    page = order[0][0] + ((" and %d more page%s" % (len(order) - 1, "s" if len(order) > 2 else "")) if len(order) > 1 else "")
    f = {"page": page, "ke": num(fke), "sessions": num(fs), "window": env.window, "share": pct(share)}
    vals = {"pages": {k: v for k, v in order}, "share_of_store_key_events": round(share, 3) if share is not None else None}
    if non_share >= p["explained_by_non_lead_share"]:
        return res_clean("%s (%s on %s visits) is explained by %s, already under NON_LEAD_KEY_EVENTS; this rule "
                         "re-checks the page once that is fixed" % (page, num(fke), num(fs), top_non or "non-lead events"), value=vals)
    if share is not None and share >= p["red_share_of_key_events"]:
        return res_fire("red", f, value=vals)
    return res_fire("amber", f, value=vals)


def _organic_rows(env):
    org = env.s.get("organic")
    if org is None:
        return None, None, "no ga4_organic_%s.json; gdata.py ga4-nightly writes it since 2026-09-23" % env.store
    rows = org.get("organic_landing_last28")
    if rows is None:
        return None, None, "organic_landing_last28 missing or errored in ga4_organic_%s.json" % env.store
    w = (org.get("organic_windows") or {}).get("last28")
    window = fmt_range(d_of(w[0]), d_of(w[1])) if w else "last 28 days"
    return rows, window, None


def chk_notset_organic_landing(env, rule):
    p = rule["params"]
    rows, window, err = _organic_rows(env)
    if err:
        return res_nc(err)
    total = sum(r.get("sessions") or 0 for r in rows)
    ns = sum(r.get("sessions") or 0 for r in rows if (r.get("landingPage") or r.get("landingPagePlusQueryString")) == "(not set)")
    if total <= 0:
        return res_clean("no organic sessions")
    share = ns / total
    vals = {"notset": ns, "total": total, "share": round(share, 3)}
    if share >= p["amber_share"] and ns >= p["min_sessions"]:
        return res_fire("amber", {"share": pct(share), "notset": num(ns), "total": num(total), "window": window}, value=vals)
    return res_clean(value=vals)


def chk_paid_campaign_in_organic(env, rule):
    p, rx = rule["params"], env.cfg["_re"]
    rows, window, err = _organic_rows(env)
    if err:
        return res_nc(err)
    total = sum(r.get("sessions") or 0 for r in rows)
    camps = {}
    for r in rows:
        c = r.get("sessionCampaignName") or ""
        if c and not rx["gbp_campaign"].search(c) and rx["paid_campaign"].search(c):
            camps[c] = camps.get(c, 0) + (r.get("sessions") or 0)
    ps = sum(camps.values())
    share = ps / total if total else 0.0
    vals = {"campaigns": camps, "share": round(share, 3)}
    if ps >= p["min_sessions"] and share >= p["min_share"]:
        f = {"campaigns": ", ".join("%s (%s)" % (c, num(n)) for c, n in sorted(camps.items(), key=lambda kv: -kv[1])),
             "sessions": num(ps), "share": pct(share), "window": window}
        return res_fire("amber", f, value=vals)
    return res_clean(value=vals)


def _conv_rows(raw):
    rows = raw.get("rows") if isinstance(raw, dict) else raw
    if not rows or not isinstance(rows, list):
        return None
    head = [str(h) for h in rows[0]]
    try:
        ia = head.index("segments_conversionActionName")
        ic = head.index("metrics_conversions")
    except ValueError:
        return None
    out = {}
    for r in rows[1:]:
        if len(r) <= max(ia, ic):
            continue
        try:
            v = float(r[ic])
        except (TypeError, ValueError):
            continue
        out[r[ia]] = out.get(r[ia], 0.0) + v
    return out


def chk_ads_non_lead_conversions(env, rule):
    p, cfg = rule["params"], env.cfg
    if env.store not in ads_sheets(cfg):
        return res_na("no Google Ads export for %s" % env.store)
    raw = env.s.get("ads_conv_raw")
    if raw is None:
        return res_nc("no %s_conversions_by_action_7d file in the shift folder" % env.store)
    acts = _conv_rows(raw)
    if acts is None:
        return res_nc("conversions_by_action_7d file has no header row it can read")
    total = sum(acts.values())
    if total < p["min_conversions"]:
        return res_clean("%.1f primary conversions, under the %d floor" % (total, p["min_conversions"]))
    non = {a: v for a, v in acts.items() if v > 0 and event_class(cfg, a) != "lead"}
    share = sum(non.values()) / total
    vals = {"non_lead_share": round(share, 3), "total": round(total, 1), "actions": {a: round(v, 1) for a, v in acts.items() if v}}
    sev = "red" if share >= p["red_share"] else ("amber" if share >= p["amber_share"] else None)
    if not sev:
        return res_clean(value=vals)
    top = sorted(non.items(), key=lambda kv: -kv[1])
    meta = _meta(env)
    window = "Ads, last 7 days of the export"
    if meta and meta[0]:
        try:
            lr = dt.datetime.strptime(meta[0], "%Y-%m-%d %H:%M:%S").date()
            window = "Ads, 7 days to %s" % fmt_day(lr - dt.timedelta(days=1))
        except ValueError:
            pass
    f = {"top_action": "'%s'" % top[0][0], "share": pct(share), "total": num(total), "window": window,
         "non_lead_actions": ", ".join("'%s' (%s)" % (a, num(v)) for a, v in top)}
    return res_fire(sev, f, value=vals)


def _meta(env):
    raw = env.s.get("ads_meta_raw")
    if raw is None:
        return None
    rows = raw.get("rows") if isinstance(raw, dict) else raw
    kv, tabs = meta_from_rows(rows)
    ref = raw.get("pulled_at") if isinstance(raw, dict) else None
    return kv.get("last_run"), tabs, ref or env.s.get("ads_meta_file_mtime")


def chk_ads_export_stale(env, rule):
    p = rule["params"]
    if env.store not in ads_sheets(env.cfg):
        return res_na("no Google Ads export for %s" % env.store)
    m = _meta(env)
    if m is None:
        return res_nc("no %s_ads_meta.json in the shift folder; health.py reads the meta tab only when run on the shift date" % env.store)
    last_run, tabs, ref = m
    if not last_run or not ref:
        return res_nc("meta tab has no last_run")
    try:
        lr = dt.datetime.strptime(last_run, "%Y-%m-%d %H:%M:%S")
        rf = dt.datetime.fromisoformat(ref).replace(tzinfo=None)
    except ValueError as e:
        return res_nc("cannot read last_run %r: %s" % (last_run, e))
    age = (rf - lr).total_seconds() / 3600.0
    bad = [t for t in tabs if str(t.get("status")).strip().lower() != "ok"]
    vals = {"last_run": last_run, "read_at": ref, "age_hours": round(age, 1), "bad_tabs": bad}
    f = {"last_run": last_run, "age_h": "%.0f" % age,
         "tab_note": ("; tab errors: " + ", ".join("%s %s" % (t["tab"], t["status"]) for t in bad)) if bad else ""}
    if age > p["red_hours"]:
        return res_fire("red", f, value=vals)
    if age > p["amber_hours"] or bad:
        return res_fire("amber", f, value=vals)
    return res_clean(value=vals)


def chk_ga4_pull_stale(env, rule):
    p = rule["params"]
    if not env.g:
        return res_nc("no ga4_%s.json" % env.store)
    if not env.T:
        return res_fire("amber", {"finding": "no target_date in the file"})
    lag = (d_of(env.date) - env.T).days
    errs = [str(e) for e in (env.g.get("errors") or [])]
    probs = []
    if lag > p["max_lag_days"]:
        probs.append("target date %s is %d days before the shift" % (env.T.isoformat(), lag))
    if errs:
        probs.append("errors: " + "; ".join(e[:100] for e in errs[:3]))
    if probs:
        return res_fire("amber", {"finding": "; ".join(probs)}, value={"lag_days": lag, "errors": errs})
    return res_clean(value={"lag_days": lag})


CHECKS = {
    "ke_rate_high": chk_ke_rate_high,
    "ke_collapse": chk_ke_collapse,
    "non_lead_key_events": chk_non_lead_key_events,
    "duplicate_lead_events": chk_duplicate_lead_events,
    "landing_page_load_trigger": chk_landing_page_load_trigger,
    "notset_organic_landing": chk_notset_organic_landing,
    "paid_campaign_in_organic": chk_paid_campaign_in_organic,
    "ads_non_lead_conversions": chk_ads_non_lead_conversions,
    "ads_export_stale": chk_ads_export_stale,
    "ga4_pull_stale": chk_ga4_pull_stale,
}


def evaluate_night(cfg, night):
    out = {}
    for st in cfg["stores"]:
        s = night["stores"][st]
        env = Env(cfg, night["date"], s)
        res = {}
        for rule in cfg["rules"]:
            if s.get("ga4") is None and rule["check"] not in ("ads_non_lead_conversions", "ads_export_stale"):
                res[rule["id"]] = res_nc("no ga4_%s.json" % st)
                continue
            try:
                r = CHECKS[rule["check"]](env, rule)
            except Exception as e:  # a bad row never takes the board down; it is reported
                r = res_nc("check failed: %s: %s" % (type(e).__name__, e))
            if r["status"] in SEV_RANK:
                r["board"] = fill(rule["board"], r["fields"])
                r["detail"] = fill(rule.get("detail") or rule["board"], r["fields"])
                r["gm"] = fill(rule["gm"], r["fields"])
                r["tech"] = fill(rule["tech"], dict(r["fields"], store=st))
            res[rule["id"]] = r
        out[st] = {"ga4": s.get("ga4") is not None, "results": res, "env": env}
    return out


# ---------------------------------------------------------------- ledger

def empty_state():
    return {"about": "Measurement Health ledger written by scripts/health.py. 'nights' holds every "
                     "evaluated night; 'open' and 'cleared' are rebuilt from it on each run.",
            "nights": {}, "open": {}, "cleared": []}


def load_state(path):
    if path and os.path.exists(path):
        with open(path) as f:
            st = json.load(f)
        st.setdefault("nights", {})
        return st
    return empty_state()


def compact_night(evald):
    night = {}
    for st, e in evald.items():
        row = {"_ga4": "ok" if e["ga4"] else "missing"}
        for rid, r in e["results"].items():
            row[rid] = [r["status"], r.get("board", "")] if r["status"] in SEV_RANK else r["status"]
        night[st] = row
    return night


def known_since(cfg, store, rid, date, cleared_keys):
    if (store, rid) in cleared_keys:
        return None
    for c in cfg.get("open_cases") or []:
        if c["store"] == store and rid in c["rules"] and c["since"] <= date:
            return c
    return None


def derive(cfg, state):
    n_clear = cfg["state"]["clear_after_clean_nights"]
    open_, cleared, cleared_keys = {}, [], set()
    for date in sorted(state["nights"]):
        for store, row in sorted(state["nights"][date].items()):
            for rid, val in row.items():
                if rid.startswith("_"):
                    continue
                status, finding = (val[0], val[1]) if isinstance(val, list) else (val, "")
                key = (store, rid)
                if status in SEV_RANK:
                    e = open_.get(key)
                    if e is None:
                        e = {"first_seen": date, "nights_seen": 0}
                        c = known_since(cfg, store, rid, date, cleared_keys)
                        if c and c["since"] < date:
                            e["known_since"] = c["since"]
                            e["known_since_note"] = "%s %s per %s" % (c.get("qualifier", ""), c["since"], c["source"].split(":")[0])
                        open_[key] = e
                    e.update({"last_seen": date, "severity": status, "clean_streak": 0, "last_finding": finding})
                    e["nights_seen"] += 1
                    e.pop("first_clean", None)
                elif status == "clean" and key in open_:
                    e = open_[key]
                    e["clean_streak"] = e.get("clean_streak", 0) + 1
                    e.setdefault("first_clean", date)
                    if e["clean_streak"] >= n_clear:
                        done = dict(e, store=store, rule=rid, cleared_on=e["first_clean"], confirmed_on=date)
                        cleared.append(done)
                        cleared_keys.add(key)
                        del open_[key]
    for e in list(open_.values()) + cleared:
        start = min(e["first_seen"], e.get("known_since", e["first_seen"]))
        e["days_broken"] = (d_of(e["last_seen"]) - d_of(start)).days + 1
    state["open"] = {}
    for (store, rid), e in sorted(open_.items()):
        state["open"].setdefault(store, {})[rid] = e
    state["cleared"] = cleared
    state["rules_version"] = cfg.get("version")
    state["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
    return state


def save_state(state, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, path)


def last_ga4_date(state, store, before):
    ds = [d for d, n in state["nights"].items() if d < before and (n.get(store) or {}).get("_ga4") == "ok"]
    return max(ds) if ds else None


# ---------------------------------------------------------------- board

def days_words(e):
    n = e["days_broken"]
    s = "%d day%s" % (n, "" if n == 1 else "s")
    if e.get("known_since"):
        s += " (since %s per the SOP, first scripted %s)" % (fmt_day(d_of(e["known_since"])), fmt_day(d_of(e["first_seen"])))
    elif n == 1:
        s += " (new tonight)"
    return s


def build_board(cfg, date, evald, state, night, pull_notes):
    order = cfg["_order"]
    rules_by_id = {r["id"]: r for r in cfg["rules"]}
    stores, board, missing = {}, [], []
    for st in cfg["stores"]:
        e = evald[st]
        res = e["results"]
        led = (state["open"].get(st) or {})
        issues = []
        for rid, r in res.items():
            L = led.get(rid) or {}
            if r["status"] in SEV_RANK:
                issues.append({"rule": rid, "severity": r["status"], "carried": False, "finding": r["board"],
                               "detail": r["detail"], "gm": r["gm"], "tech": r["tech"],
                               "blocks": rules_by_id[rid].get("blocks", []), "value": r.get("value"),
                               "first_seen": L.get("first_seen"), "known_since": L.get("known_since"),
                               "days_broken": L.get("days_broken"), "days_words": days_words(L) if L else ""})
            elif r["status"] == "unchecked" and L:
                # Open in the ledger but not re-checkable tonight: it stays open (missing input never clears),
                # shown with its last finding and date, never as tonight's number.
                rule = rules_by_id[rid]
                note = "last seen %s, not re-checked tonight (%s)" % (fmt_day(d_of(L["last_seen"])), r["reason"])
                issues.append({"rule": rid, "severity": L["severity"], "carried": True, "finding": L.get("last_finding", ""),
                               "detail": "%s. %s" % (L.get("last_finding", "").rstrip("."), note[0].upper() + note[1:]),
                               "gm": fill(rule["gm"], {}), "tech": "Not re-checked tonight (%s). The fix on the %s board still applies." % (
                                   r["reason"], L["last_seen"]),
                               "blocks": rule.get("blocks", []), "value": None, "first_seen": L.get("first_seen"),
                               "known_since": L.get("known_since"), "days_broken": L.get("days_broken"),
                               "days_words": days_words(L)})
        issues.sort(key=lambda i: (SEV_RANK[i["severity"]], i["carried"], order[i["rule"]]))
        unchecked = [{"rule": rid, "reason": r["reason"]} for rid, r in res.items() if r["status"] == "unchecked"]
        na = [{"rule": rid, "reason": r["reason"]} for rid, r in res.items() if r["status"] == "n/a"]
        clearing = [{"rule": rid, "clean_nights": L.get("clean_streak"), "needed": cfg["state"]["clear_after_clean_nights"]}
                    for rid, L in led.items() if res.get(rid, {}).get("status") == "clean" and L.get("clean_streak")]
        cleared_tonight = [{"rule": c["rule"], "cleared_on": c["cleared_on"], "days_broken": c["days_broken"]}
                           for c in state["cleared"] if c["store"] == st and c.get("confirmed_on") == date]
        core_unchecked = [u for u in unchecked if rules_by_id[u["rule"]].get("core")]
        if not e["ga4"]:
            color = "no_data"
            last = last_ga4_date(state, st, date)
            top = "no ga4_%s.json tonight; no GA4 data since %s" % (st, last or "before this ledger began")
            days = ""
        elif issues:
            i0 = issues[0]
            color, days = i0["severity"], i0["days_words"]
            top = i0["finding"].rstrip(".") + ((" (last seen %s, not re-checked tonight)" % fmt_day(d_of(led[i0["rule"]]["last_seen"])))
                                               if i0["carried"] else "")
        elif core_unchecked:
            color, top, days = "grey", "not fully checked: " + ", ".join(u["rule"] for u in core_unchecked), ""
        else:
            color, top, days = "green", "no integrity rule tripped", ""
        blocked = sorted(set(b for i in issues if i["severity"] == "red" for b in i["blocks"]))
        stores[st] = {"color": color, "top_issue": top, "days_broken": issues[0]["days_broken"] if issues else None,
                      "blocked_tonight": blocked, "issues": issues, "clearing": clearing,
                      "cleared_recently": cleared_tonight, "unchecked": unchecked, "not_applicable": na,
                      "inputs": night["stores"][st]["inputs"], "load_errors": night["stores"][st]["load_errors"]}
        board.append({"store": st, "color": COLOR_WORD[color], "top_rule": issues[0]["rule"] if issues else None,
                      "top_issue": top, "days_broken": stores[st]["days_broken"], "days_words": days})
        for u in unchecked:
            missing.append("%s %s: %s" % (st, u["rule"], u["reason"]))
    envs = [evald[s]["env"] for s in cfg["stores"] if evald[s]["env"].T]
    T = max(e.T for e in envs) if envs else None
    return {"date": date, "ga4_target_date": T.isoformat() if T else None,
            "window_7d": [(T - dt.timedelta(days=6)).isoformat(), T.isoformat()] if T else None,
            "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
            "rules_file": rel(RULES_PATH), "rules_version": cfg.get("version"),
            "colors": {k: v for k, v in cfg["colors"].items()},
            "board": board, "stores": stores, "missing_inputs": missing, "live_reads": pull_notes}


def board_lines(h):
    out = []
    for b in h["board"]:
        line = "%s: %s. %s." % (b["store"], b["color"], b["top_issue"].rstrip("."))
        if b["days_words"]:
            line += " Broken %s." % b["days_words"]
        out.append(clean_text(line))
    return out


def render_md(h):
    T = d_of(h["ga4_target_date"]) if h["ga4_target_date"] else None
    L = ["# Measurement health, shift %s" % h["date"], ""]
    if T:
        L.append("GA4 through %s %s; 7-day window %s. Red: the numbers it names stay out of the brief and every "
                 "client-facing claim. Amber: quote only what the detail allows, never the raw total." % (
                     T.strftime("%a"), fmt_day(T), fmt_range(T - dt.timedelta(days=6), T)))
    else:
        L.append("No GA4 file for any store tonight.")
    L.append("")
    L += board_lines(h)
    L += ["", "## Details", ""]
    for st, s in h["stores"].items():
        L.append("### %s, %s" % (st, COLOR_WORD[s["color"]]))
        if s["blocked_tonight"]:
            L.append("Blocked tonight: %s." % ", ".join(s["blocked_tonight"]))
        for i in s["issues"]:
            L.append("- **%s %s**%s, %s. %s." % (i["severity"].upper(), i["rule"], " (carried)" if i["carried"] else "",
                                                 i["days_words"], i["detail"].rstrip(".")))
            L.append("  - For the GM: %s" % i["gm"])
            L.append("  - Fix: %s" % i["tech"])
        for c in s["clearing"]:
            L.append("- Clearing: %s clean %d of %d nights." % (c["rule"], c["clean_nights"], c["needed"]))
        if not s["issues"] and not s["clearing"] and s["color"] == "green":
            L.append("- Clean on every rule that ran.")
        if s["unchecked"]:
            L.append("- Not checked: " + "; ".join("%s (%s)" % (u["rule"], u["reason"]) for u in s["unchecked"]) + ".")
        if s["load_errors"]:
            L.append("- Unreadable input: " + "; ".join(s["load_errors"]) + ".")
        L.append("")
    if h["live_reads"]:
        L += ["## Live reads tonight", ""] + ["- " + n for n in h["live_reads"]] + [""]
    L.append("Rules: %s (version %s). Ledger: %s." % (h["rules_file"], h["rules_version"], rel(STATE_PATH)))
    return clean_text("\n".join(L)) + "\n"


def write_outputs(h, out_dir, stem="health"):
    os.makedirs(out_dir, exist_ok=True)
    pj, pm = os.path.join(out_dir, stem + ".json"), os.path.join(out_dir, stem + ".md")
    with open(pj, "w") as f:
        json.dump(h, f, indent=1)
    with open(pm, "w") as f:
        f.write(render_md(h))
    return pj, pm


def run_night(cfg, date, state, data_dir=None, pull=False):
    night = load_night(cfg, date, data_dir, pull)
    evald = evaluate_night(cfg, night)
    state["nights"][date] = compact_night(evald)
    derive(cfg, state)
    return build_board(cfg, date, evald, state, night, night["pull_notes"]), night


# ---------------------------------------------------------------- commands

def cmd_night(args, cfg):
    date = args.date
    d_of(date)
    data_dir = os.path.abspath(args.data) if args.data else None
    folder = data_dir or os.path.join(SHIFTS, date, "data")
    if not os.path.isdir(folder):
        print("ERROR: no data folder %s. Run gdata.py ga4-nightly first." % rel(folder))
        return 1
    pull = (not args.no_pull) and d_of(date) == pacific_today()
    state_path = os.path.abspath(args.state) if args.state else STATE_PATH
    state = load_state(state_path)
    h, night = run_night(cfg, date, state, data_dir, pull)
    pj, pm = write_outputs(h, night["out_dir"])
    save_state(state, state_path)
    print("\n".join(board_lines(h)))
    print()
    print("Wrote %s and %s. Ledger %s." % (rel(pj), rel(pm), rel(state_path)))
    for n in h["live_reads"]:
        print("Ads export read (read only): " + n)
    if h["missing_inputs"]:
        print("Not checked tonight (%d): %s" % (len(h["missing_inputs"]), "; ".join(h["missing_inputs"])))
    return 0


def cmd_backtest(args, cfg):
    a, b = d_of(args.from_), d_of(args.to)
    if b < a:
        print("ERROR: --to is before --from")
        return 1
    out_dir = os.path.abspath(args.out) if args.out else os.path.join(tempfile.gettempdir(), "digitalcliq-health-backtest")
    scratch_state = os.path.join(out_dir, "health-state.backtest.json")
    state = empty_state()
    ran, skipped, md = [], [], ["# Measurement health back-test, %s to %s" % (a.isoformat(), b.isoformat()), ""]
    d = a
    while d <= b:
        ds = d.isoformat()
        if not glob.glob(os.path.join(SHIFTS, ds, "data", "ga4_*.json")):
            skipped.append(ds)
        else:
            h, _night = run_night(cfg, ds, state, None, False)
            write_outputs(h, out_dir, "health_%s" % ds)
            lines = board_lines(h)
            print("== %s (GA4 through %s)" % (ds, h["ga4_target_date"]))
            print("\n".join(lines))
            print()
            md += ["## %s (GA4 through %s)" % (ds, h["ga4_target_date"]), ""] + lines + [""]
            ran.append(ds)
        d += dt.timedelta(days=1)
    save_state(state, scratch_state)
    with open(os.path.join(out_dir, "backtest.md"), "w") as f:
        f.write(clean_text("\n".join(md)) + "\n")
    print("Nights evaluated: %s. No shift folder with GA4 data: %s." % (", ".join(ran) or "none", ", ".join(skipped) or "none"))
    print("Scratch ledger %s; per-night boards in %s." % (scratch_state, out_dir))
    if args.write_state:
        state_path = os.path.abspath(args.state) if args.state else STATE_PATH
        real = load_state(state_path)
        for ds in list(real["nights"]):
            if a.isoformat() <= ds <= b.isoformat():
                del real["nights"][ds]
        real["nights"].update(state["nights"])
        derive(cfg, real)
        save_state(real, state_path)
        print("Merged %d nights into %s." % (len(ran), rel(state_path)))
    return 0


# ---------------------------------------------------------------- selftest

def _pack(store, target, daily, events, events_prior=None, landing=None, sm_last=None, sm_prior=None):
    return {"store": store, "target_date": target, "errors": [], "channel_daily_last7": daily,
            "key_events_by_channel_last7": events, "key_events_by_channel_prior7": events_prior or events,
            "landing_pages_last7": landing or [], "source_medium_last7": sm_last or [{"sessions": 1000, "keyEvents": 0}],
            "source_medium_prior7": sm_prior or [{"sessions": 1000, "keyEvents": 0}]}


def _daily(target, sessions_per_day, ke_per_day):
    T = d_of(target)
    return [{"date": (T - dt.timedelta(days=i)).strftime("%Y%m%d"), "sessionDefaultChannelGroup": "Direct",
             "sessions": sessions_per_day, "engagedSessions": sessions_per_day // 2, "keyEvents": ke_per_day} for i in range(7)]


def _ev(name, ch, k):
    return {"eventName": name, "sessionDefaultChannelGroup": ch, "keyEvents": k}


def cmd_selftest(cfg):
    import shutil
    ok, fails = [0], []

    def check(cond, label):
        if cond:
            ok[0] += 1
        else:
            fails.append(label)

    # rules file sanity
    need = ("id", "check", "description", "reads", "params", "severity", "blocks", "why", "board", "gm", "tech")
    for r in cfg["rules"]:
        for k in need:
            check(k in r, "rule %s has %s" % (r.get("id"), k))
        check(r["check"] in CHECKS, "rule %s check implemented" % r.get("id"))
    with open(RULES_PATH) as f:
        check(EM_DASH not in f.read(), "no em dash in measurement-rules.json")
    with open(os.path.abspath(__file__)) as f:
        check(EM_DASH not in f.read(), "no em dash in health.py")
    for n, c in (("new_VLP_visit", "page_view"), ("schedule_service_page_view", "page_view"), ("About Us", "page_view"),
                 ("asc_form_engagement", "soft"), ("asc_click_to_call", "lead"), ("generate_lead", "lead"),
                 ("form_submit", "lead"), ("Store visits", "lead"), ("Local actions - Directions", "soft"),
                 ("all_forms_pixel_web", "other"), ("Calls from ads", "lead"), ("new_vdp", "page_view")):
        check(event_class(cfg, n) == c, "class of %s is %s (got %s)" % (n, c, event_class(cfg, n)))

    tmp = tempfile.mkdtemp(prefix="health-selftest-")
    T = "2026-09-22"
    stores = cfg["stores"]
    base_events = [_ev("form_submit", "Direct", 20), _ev("asc_click_to_call", "Organic Search", 10)]
    packs = {s: _pack(s, T, _daily(T, 200, 5), base_events) for s in stores}
    # MCP-like: page views as key events, far above sessions
    packs["MCP"] = _pack("MCP", T, _daily(T, 150, 480), [_ev("new_VLP_visit", "Organic Search", 3000), _ev("form_submit", "Direct", 20)],
                         landing=[{"landingPagePlusQueryString": "/", "sessionDefaultChannelGroup": "Organic Search",
                                   "sessions": 245, "engagementRate": 0.9, "keyEvents": 1118}])
    # SBMW-like: a page view dominating, a double-tagged form, schedule page firing on load
    packs["SBMW"] = _pack("SBMW", T, _daily(T, 1300, 55), [
        _ev("schedule_service_page_view", "Direct", 290), _ev("form_submit", "Direct", 25), _ev("generate_lead", "Direct", 25),
        _ev("form_submit", "Organic Search", 15), _ev("generate_lead", "Organic Search", 15), _ev("lead_submitted", "Direct", 21)],
        landing=[{"landingPagePlusQueryString": "/service/schedule-service/", "sessionDefaultChannelGroup": "Direct",
                  "sessions": 33, "engagementRate": 1, "keyEvents": 72}])
    # ATLAS-like: the only lead event fires on page load on /contact
    packs["ATLAS"] = _pack("ATLAS", T, _daily(T, 500, 37), [_ev("generate_lead", "Organic Search", 262)],
                           landing=[{"landingPagePlusQueryString": "/contact", "sessionDefaultChannelGroup": "Organic Search",
                                     "sessions": 130, "engagementRate": 1, "keyEvents": 155},
                                    {"landingPagePlusQueryString": "/contact", "sessionDefaultChannelGroup": "Direct",
                                     "sessions": 37, "engagementRate": 1, "keyEvents": 37}])
    # NCBMW-like: collapsed against the documented baseline
    packs["NCBMW"] = _pack("NCBMW", T, _daily(T, 460, 8), [_ev("asc_form_submission", "Paid Search", 54)])
    organic = {"NCBMW": {"store": "NCBMW", "organic_windows": {"last28": ["2026-08-26", T]}, "organic_landing_last28": [
        {"landingPage": "(not set)", "sessionCampaignName": "(organic)", "sessions": 403},
        {"landingPage": "/", "sessionCampaignName": "(organic)", "sessions": 1100},
        {"landingPage": "/inventory", "sessionCampaignName": "constellation_2026_bmwwr_vla", "sessions": 553},
        {"landingPage": "/", "sessionCampaignName": "googlemybusiness", "sessions": 458}]},
        "MCP": {"store": "MCP", "organic_windows": {"last28": ["2026-08-26", T]}, "organic_landing_last28": [
            {"landingPage": "/", "sessionCampaignName": "listings", "sessions": 689},
            {"landingPage": "/", "sessionCampaignName": "(organic)", "sessions": 920}]}}
    conv = [["campaign_name", "segments_conversionActionName", "metrics_conversions", "metrics_allConversions"]]
    ads = {"ATLAS": conv + [["Atlas Search Campaign", "About Us", "33", "33"]],
           "MCP": conv + [["c", "Calls from ads", "53", "54"], ["c", "Local actions - Directions", "23", "47"]],
           "NOI": conv + [["c", "Calls from ads", "47", "73"], ["c", "Store visits", "14.7", "29.7"]]}
    meta = {"MCP": ("2026-09-23 0:52:34", "2026-09-23T01:10:00", "ok"),
            "NOI": ("2026-09-21 23:00:00", "2026-09-23T01:10:00", "ok"),     # 26.2 hours: amber
            "ATLAS": ("2026-09-19 12:00:00", "2026-09-23T01:10:00", "ok")}  # 85 hours: red

    def write_night(date, which=None):
        d = os.path.join(tmp, date, "data")
        os.makedirs(d, exist_ok=True)
        for s in stores:
            if which is not None and s not in which:
                continue
            p = dict(packs[s], target_date=(d_of(date) - dt.timedelta(days=1)).isoformat())
            p["channel_daily_last7"] = _daily(p["target_date"], p["channel_daily_last7"][0]["sessions"],
                                              p["channel_daily_last7"][0]["keyEvents"])
            with open(os.path.join(d, "ga4_%s.json" % s), "w") as f:
                json.dump(p, f)
            if s in organic:
                with open(os.path.join(d, "ga4_organic_%s.json" % s), "w") as f:
                    json.dump(organic[s], f)
            if s in ads:
                with open(os.path.join(d, "%s_conversions_by_action_7d.txt" % s), "w") as f:
                    f.write("=== %s conversions_by_action_7d ===\n" % s + json.dumps(ads[s]))
                lr, ref, status = meta[s]
                with open(os.path.join(d, "%s_ads_meta.json" % s), "w") as f:
                    json.dump({"pulled_at": ref, "rows": [["store", s], ["last_run", lr], [], ["tab", "rows", "status"],
                                                          ["campaign_daily_30d", "26", status]]}, f)
        return d

    d1 = write_night("2026-09-23")
    state = empty_state()
    h, _ = run_night(cfg, "2026-09-23", state, d1, False)
    S = h["stores"]
    fired = {st: {i["rule"]: i["severity"] for i in S[st]["issues"]} for st in stores}
    check(S["MCP"]["color"] == "red" and fired["MCP"].get("KEY_EVENT_RATE_HIGH") == "red", "MCP red on key-event rate")
    check(fired["MCP"].get("NON_LEAD_KEY_EVENTS") == "red", "MCP non-lead share red at 99%")
    check(fired["SBMW"].get("NON_LEAD_KEY_EVENTS") == "amber", "SBMW page view amber")
    check(fired["SBMW"].get("DUPLICATE_LEAD_EVENTS") == "amber", "SBMW double-tagged form amber")
    check("LANDING_PAGE_LOAD_TRIGGER" not in fired["SBMW"], "SBMW schedule page explained by its page-view event, not double counted")
    check("LANDING_PAGE_LOAD_TRIGGER" not in fired["MCP"], "MCP home page explained by its page-view events, not double counted")
    check(S["SBMW"]["color"] == "amber", "SBMW amber overall")
    check(fired["ATLAS"].get("LANDING_PAGE_LOAD_TRIGGER") == "red", "ATLAS /contact page-load trigger red")
    check(fired["ATLAS"].get("ADS_NON_LEAD_CONVERSIONS") == "red", "ATLAS About Us Ads conversion red")
    check(fired["ATLAS"].get("ADS_EXPORT_STALE") == "red", "ATLAS 85-hour export red")
    check(fired["NOI"].get("ADS_EXPORT_STALE") == "amber", "NOI 26.2-hour export amber")
    check("ADS_EXPORT_STALE" not in fired["MCP"] and "ADS_NON_LEAD_CONVERSIONS" not in fired["MCP"], "MCP Ads clean")
    check(fired["NCBMW"].get("KEY_EVENT_COLLAPSE") == "red", "NCBMW collapse red against baseline")
    check(fired["NCBMW"].get("NOTSET_ORGANIC_LANDING") == "amber", "NCBMW (not set) organic amber")
    check(fired["NCBMW"].get("PAID_CAMPAIGN_IN_ORGANIC") == "amber", "NCBMW VLA in organic amber")
    check("PAID_CAMPAIGN_IN_ORGANIC" not in fired["MCP"], "MCP listings (GBP) not treated as paid")
    check(not [r for r in fired["NOI"] if r != "ADS_EXPORT_STALE"], "NOI clean apart from the stale export")
    check(state["open"]["MCP"]["KEY_EVENT_RATE_HIGH"]["known_since"] == "2026-08-30", "MCP seeded from the SOP open case")
    check(state["open"]["MCP"]["KEY_EVENT_RATE_HIGH"]["days_broken"] == 25, "MCP days broken from 8/30 to 9/23 is 25")
    check(state["open"]["SBMW"]["NON_LEAD_KEY_EVENTS"]["days_broken"] == 1, "new issue counts 1 day")
    md = render_md(h)
    top = md.split("\n\n")[2].split("\n")
    check(len(top) == 5 and all(ln.split(":")[0] in stores for ln in top), "board block is exactly 5 store lines")
    check(EM_DASH not in md, "no em dash in health.md")

    # a WoW collapse on a store with no baseline
    ww = _pack("NOI", T, _daily(T, 200, 2), [_ev("form_submit", "Direct", 10)], events_prior=[_ev("form_submit", "Direct", 60)],
               sm_last=[{"sessions": 1400}], sm_prior=[{"sessions": 1400}])
    r = chk_ke_collapse(Env(cfg, "2026-09-23", {"store": "NOI", "ga4": ww}), [x for x in cfg["rules"] if x["id"] == "KEY_EVENT_COLLAPSE"][0])
    check(r["status"] == "red", "week-over-week lead collapse red without a baseline")

    # ledger: second night keeps counting; clean nights clear after two; a missing night changes nothing
    packs["SBMW"] = _pack("SBMW", T, _daily(T, 1300, 20), [_ev("form_submit", "Direct", 25), _ev("lead_submitted", "Direct", 21)])
    d2 = write_night("2026-09-24")
    run_night(cfg, "2026-09-24", state, d2, False)
    e = state["open"]["SBMW"]["NON_LEAD_KEY_EVENTS"]
    check(e["clean_streak"] == 1 and e["first_clean"] == "2026-09-24", "SBMW clean one night, still open")
    run_night(cfg, "2026-09-24", state, d2, False)
    check(state["open"]["SBMW"]["NON_LEAD_KEY_EVENTS"]["clean_streak"] == 1, "re-running a night does not double count")
    d3 = write_night("2026-09-25", which=[s for s in stores if s != "SBMW"])
    h3, _ = run_night(cfg, "2026-09-25", state, d3, False)
    check(h3["stores"]["SBMW"]["color"] == "no_data", "store without a GA4 file is NO DATA")
    check("2026-09-24" in h3["stores"]["SBMW"]["top_issue"], "NO DATA names the last date with data")
    check("NON_LEAD_KEY_EVENTS" in state["open"]["SBMW"], "missing night does not clear")
    atlas3 = [i for i in h3["stores"]["ATLAS"]["issues"] if i["rule"] == "ADS_NON_LEAD_CONVERSIONS"]
    check(bool(atlas3) and not atlas3[0]["carried"], "ATLAS Ads rule fired fresh on 9/25")
    for s_ in ("ATLAS",):
        os.remove(os.path.join(tmp, "2026-09-25", "data", "%s_conversions_by_action_7d.txt" % s_))
    h3b, _ = run_night(cfg, "2026-09-25", state, d3, False)
    atlas3 = [i for i in h3b["stores"]["ATLAS"]["issues"] if i["rule"] == "ADS_NON_LEAD_CONVERSIONS"]
    check(bool(atlas3) and atlas3[0]["carried"] and atlas3[0]["severity"] == "red",
          "missing Ads file carries the open red forward, marked carried")
    check("Google Ads conversions" in h3b["stores"]["ATLAS"]["blocked_tonight"], "carried red still blocks its numbers")
    d4 = write_night("2026-09-26")
    run_night(cfg, "2026-09-26", state, d4, False)
    cl = [c for c in state["cleared"] if c["store"] == "SBMW" and c["rule"] == "NON_LEAD_KEY_EVENTS"]
    check(bool(cl) and cl[0]["cleared_on"] == "2026-09-24" and cl[0]["days_broken"] == 1, "cleared after two clean nights, cleared_on = first clean")
    check(state["open"]["MCP"]["KEY_EVENT_RATE_HIGH"]["days_broken"] == 28, "MCP keeps counting across nights (28 on 9/26)")
    shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print("selftest: %d passed, %d FAILED" % (ok[0], len(fails)))
        for f_ in fails:
            print("  FAIL " + f_)
        return 1
    print("selftest: %d checks passed" % ok[0])
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", nargs="?", choices=["selftest"])
    ap.add_argument("--date")
    ap.add_argument("--backtest", action="store_true")
    ap.add_argument("--from", dest="from_")
    ap.add_argument("--to")
    ap.add_argument("--write-state", action="store_true")
    ap.add_argument("--data")
    ap.add_argument("--state")
    ap.add_argument("--rules")
    ap.add_argument("--out")
    ap.add_argument("--no-pull", action="store_true")
    args = ap.parse_args()
    cfg = load_rules(args.rules)
    if args.mode == "selftest":
        return cmd_selftest(cfg)
    if args.backtest:
        if not (args.from_ and args.to):
            ap.error("--backtest needs --from and --to")
        return cmd_backtest(args, cfg)
    if not args.date:
        ap.error("give --date YYYY-MM-DD, --backtest --from D --to D, or selftest")
    return cmd_night(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
