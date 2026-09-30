#!/usr/bin/env python3
"""Client dashboard check for the DigitalCLIQ AI team. Standard library only, read only.

  python3 .claude/skills/ai-team/scripts/dash_check.py outputs/ai-team/2026-09-28
  python3 .claude/skills/ai-team/scripts/dash_check.py outputs/ai-team/2026-09-28 --in-dir DIR
  python3 .claude/skills/ai-team/scripts/dash_check.py --selftest

The three client dashboards (SBMW, NCBMW, McPeek) are Apps Script web apps whose /exec endpoint
returns the dashboard's current JSON. The store's GM sees exactly what that JSON says, so this
reads it the way the page does: one plain HTTPS GET per store (urllib follows Apps Script's 302),
no login, no browser, nothing written to any Sheet. Endpoints are listed in
references/data-sources.md under "Client dashboards" and in DASHBOARDS below; change both together.

Signals, per store (clients.<key> in the payload):
  RED    crmSource says the CRM tab is empty, or carries a "CHECK:" note
  RED    pace.leads.mtd is 0 after day 3 of the month
  RED    a CRM headline card label (kpiCards) names a month before the last closed month
  RED    a paid vendor block (ppc.<vendor>.month) names a month before the last closed month, except a
         vendor in the store's ppc_due_day (SBMW's Pixel Motion, which reports a month about mid-month):
         there the month before the last closed month passes through that day of the month
  AMBER  an SEO headline card label names a month before the last closed month
  AMBER  the SEO months (months[-1], else the client-level seoMonth) end before the last closed
         month, or the SEO section has no months at all (a pending build)
  AMBER  the top-level `updated` is more than 3 days old ("Sep 25, 6:23 AM" or "Sep 25, 2026")
Not flagged on purpose: the gross "estimate" wording (by design, per the dashboard operating guide)
and the top-level seoMonth (blank on all three by design).

Writes {shift folder}/data/dashboards.json and nothing else: per store a status (RED, AMBER,
GREEN, or NO DATA), every issue with its fix and first_seen (carried from the newest earlier
shift folder's dashboards.json), a ready "Missing tonight" line, and the fields for one aging ask.
--in-dir reads saved payloads ({key}.json, for example sbmw.json) instead of the network.

Exit 0 when every dashboard answered (whatever the colors), 2 when one or more did not answer
(the file is still written and says which), 1 on a usage error.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

try:
    from zoneinfo import ZoneInfo
    PACIFIC = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover
    PACIFIC = None

# Store code -> dashboard. Source: morning-coffee references/sources.md "Live dashboard endpoints";
# mirrored in ai-team references/data-sources.md "Client dashboards".
# Optional per store: ppc_fix (vendor key -> fix text, %(month)s = the last closed month's name) replaces the
# default "load the report" fix; ppc_due_day (vendor key -> day of month) is the PPC_OLD_MONTH grace below.
# SBMW v2 (2026-09-29): the Sterling BMW Loader fills the Sheet from the nightly Momentum KPI Summary email, Pixel
# Motion's co-op email and CRM Drop/SBMW, and logs every file in the Sheet's Ingest Log tab. Pixel Motion emails a
# month's co-op files about the 15th of the next month, matching the feed's ppc.pixel.dueBy (the 20th, Code.gs D21).
# If the Sterling dashboard ever sets its optional DASH_KEY script property, its /exec answers {"error": "not
# authorized"} and SBMW reads NO DATA every night: this script would then need to add ?key= to that URL, with the
# key read from outside the vault (~/.config/digitalcliq-ai-team/), never written here. Not built while the key is off.
DASHBOARDS = {
    "SBMW": {"key": "sbmw", "name": "Sterling BMW", "sheet": "1Ki2RjJUc4AN4A-ZFgqNLQpENDySVjgULR4xG6UTSpCU",
             "url": "https://script.google.com/macros/s/AKfycbxVJugSl93A9egpeeXymBMEzBv6M5yWMxs-Prn-VEP-MM0"
                    "ragBhWDP0xdKXDlAl_ijgJQ/exec",
             "crm_fix": "check the Ingest Log tab in the SBMW dashboard Sheet: the nightly Momentum KPI Summary email "
                        "or a file in CRM Drop/SBMW did not load (to fill a gap, drop a KPI Summary for the 1st "
                        "through yesterday, Showed Appt All, in CRM Drop/SBMW)",
             "ppc_fix": {"pixel": "check the Ingest Log tab in the SBMW dashboard Sheet for Pixel Motion's \"Sterling "
                                  "BMW Coop Files %(month)s\" email; it was due by the 20th, so if it has not "
                                  "arrived, ask Pixel Motion for it"},
             "ppc_due_day": {"pixel": 20}},
    "NCBMW": {"key": "ncbmw", "name": "New Century BMW", "sheet": "1JJcHIC1253Dtpp50OGIRhgNCw-g-DqRgkETIJa8okAE",
              "url": "https://script.google.com/macros/s/AKfycbwdi91LD8vFv5A3PDCJQ4BIm4TWkzDWei49G_dCf0fnxfMuc"
                     "DHORapSKtLcnoQ9aMpyWA/exec",
              "crm_fix": "load the current Focus export into the NCBMW dashboard Sheet"},
    "MCP": {"key": "mcpeek", "name": "McPeek CDJR", "sheet": "12vhp5FyujzOpCVcIspPszmhbLxy3FwnsjJ4UxKbFXpA",
            "url": "https://script.google.com/macros/s/AKfycbxswEKhEK-Sr98XkVe_mmFs8SqyQlsaGfzNXIAfuH2EatF"
                   "JixHtUnX3nfhyqFoKPRjl/exec",
            "crm_fix": "load the latest Tekion lead-source export into the McPeek dashboard Sheet"},
}

# Card sources that are search data, not CRM or paid data: a stale month there is AMBER, not RED.
SEO_SOURCES = {"SEMRUSH", "GA4", "GSC", "SEO", "SEARCH CONSOLE"}
UPDATED_MAX_DAYS = 3
MTD_GRACE_DAYS = 3
LEVELS = {"GREEN": 0, "AMBER": 1, "RED": 2}
MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september",
     "october", "november", "december"])}
MONTH_RE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|"
                      r"December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\b\.?(?:,?\s+(\d{4})\b)?")
JS_DATE_RE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2})\s+(\d{4})\b")
ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
UPDATED_RE = re.compile(r"^\s*([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s*(?:(\d{4})\b|(\d{1,2}):(\d{2})\s*([AaPp][Mm])?)?")


def pacific_today():
    return (dt.datetime.now(PACIFIC) if PACIFIC else dt.datetime.now()).date()


def month_num(name):
    n = (name or "").strip().lower().rstrip(".")
    for full, i in MONTHS.items():
        if n == full or (len(n) >= 3 and full.startswith(n)):
            return i
    return None


def resolve(mon, year, ref):
    """(year, month) for a month name; without a year, the latest one not after ref's month."""
    if year:
        return (int(year), mon)
    return (ref.year, mon) if mon <= ref.month else (ref.year - 1, mon)


def month_in(text, ref):
    """First month named in text as (year, month), or None."""
    if not text:
        return None
    m = JS_DATE_RE.search(text)  # 'Mon Jun 01 2026 00:00:00 GMT-0700 (...)'
    if m:
        return (int(m.group(3)), month_num(m.group(1)))
    m = ISO_RE.search(text)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    m = MONTH_RE.search(text)
    if m:
        return resolve(month_num(m.group(1)), m.group(2), ref)
    return None


def ym_label(ym):
    return dt.date(ym[0], ym[1], 1).strftime("%b %Y")


def month_end(ym):
    y, m = ym
    nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
    return nxt - dt.timedelta(days=1)


def prev_month(d):
    first = d.replace(day=1)
    last = first - dt.timedelta(days=1)
    return (last.year, last.month)


def parse_updated(text, ref):
    """'Sep 25, 6:23 AM' (no year: the latest such date not after ref) or 'Sep 25, 2026' -> date."""
    m = UPDATED_RE.match(str(text or ""))
    if not m:
        return None
    mon = month_num(m.group(1))
    if not mon:
        return None
    day = int(m.group(2))
    try:
        if m.group(3):
            return dt.date(int(m.group(3)), mon, day)
        d = dt.date(ref.year, mon, day)
        return d if d <= ref + dt.timedelta(days=1) else dt.date(ref.year - 1, mon, day)
    except ValueError:
        return None


def clean(text):
    """Dashboard text as a plain string, dashes normalized (house rule: no em dashes in anything we write)."""
    return str(text or "").replace("\u2014", "-").replace("\u2013", "-").strip()


def issue(level, rule, key, text, fix, **extra):
    out = {"level": level, "rule": rule, "key": key, "text": text, "fix": fix}
    out.update(extra)
    return out


def evaluate(store, payload, ref):
    """Rules for one store's payload. Returns (issues, notes, snapshot)."""
    cfg = DASHBOARDS[store]
    k = cfg["key"]
    issues, notes = [], []
    closed = prev_month(ref)
    c = ((payload or {}).get("clients") or {}).get(k)
    if not isinstance(c, dict):
        raise ValueError("payload has no clients.%s block" % k)
    crm_fix = cfg["crm_fix"]
    seo_fix = ("finish the SEO build (the first Semrush pull) in the %s dashboard Sheet" % store
               if not c.get("months") else "refresh the SEO months in the %s dashboard Sheet from Semrush" % store)

    # 1. CRM source says the tab is empty or asks for a check.
    crm_src = clean(payload.get("crmSource"))
    if "empty" in crm_src.lower() or "CHECK:" in crm_src:
        why = ("CRM tab is empty" if "empty" in crm_src.lower()
               else "CRM source carries a check note (\"%s\")" % crm_src[crm_src.find("CHECK:"):][:80])
        issues.append(issue("RED", "CRM_EMPTY", "crm_empty", why, crm_fix))

    # 2. Zero leads month to date after the grace days.
    pace = c.get("pace") or {}
    mtd = ((pace.get("leads") or {}).get("mtd")) if isinstance(pace, dict) else None
    if mtd is None:
        notes.append("no pace.leads.mtd in the payload")
    elif ref.day > MTD_GRACE_DAYS and float(mtd or 0) == 0:
        issues.append(issue("RED", "MTD_ZERO", "mtd_zero", "0 leads month to date on %s %d" % (ref.strftime("%b"), ref.day),
                            crm_fix))

    # 3. Headline cards naming an old month. CRM and paid cards RED, SEO cards AMBER.
    old_crm = {}
    for card in c.get("kpiCards") or []:
        label = clean(card.get("label"))
        ym = month_in(label, ref)
        if not ym or ym >= closed:
            continue
        src = str(card.get("src") or "").upper()
        shown = "%s %s" % (label, card.get("val")) if card.get("val") not in (None, "", "\u2014", "--") else label
        if src in SEO_SOURCES:
            issues.append(issue("AMBER", "KPI_SEO_OLD_MONTH", "kpi_seo:%s" % label,
                                "the \"%s\" card still shows %s" % (label, ym_label(ym)),
                                "refresh the Semrush snapshot behind the \"%s\" card in the %s dashboard Sheet"
                                % (label, store), month=ym_label(ym)))
        else:
            old_crm.setdefault(ym, []).append(shown)
    for ym, cards in sorted(old_crm.items()):
        issues.append(issue("RED", "KPI_OLD_MONTH", "kpi:%04d-%02d" % ym,
                            "headline cards still show %s (%s)" % (ym_label(ym), ", ".join(cards)), crm_fix,
                            month=ym_label(ym)))

    # 4. Paid vendor blocks naming an old month. A vendor in ppc_due_day reports the last closed month by that
    #    day, so until then the month before it is current (Pixel Motion: August stays current through Oct 20).
    ppc = c.get("ppc") or {}
    closed_name = dt.date(closed[0], closed[1], 1).strftime("%B")
    if isinstance(ppc, dict):
        for vk, v in sorted(ppc.items()):
            if not isinstance(v, dict):
                continue
            raw = str(v.get("month") or "")
            ym = month_in(raw, ref)
            if raw and not ym:
                notes.append("ppc.%s.month unreadable: %r" % (vk, raw))
            due_day = (cfg.get("ppc_due_day") or {}).get(vk)
            if (ym and due_day and ym == prev_month(dt.date(closed[0], closed[1], 1))
                    and ref.day <= due_day):
                notes.append("ppc.%s.month %s not flagged: the %s report is due by %s %d"
                             % (vk, ym_label(ym), closed_name, ref.strftime("%b"), due_day))
                continue
            if ym and ym < closed:
                vname = clean(v.get("name") or vk)
                vshort = vname.split(" (")[0]
                fix = (cfg.get("ppc_fix") or {}).get(vk)
                issues.append(issue("RED", "PPC_OLD_MONTH", "ppc:%s" % vk,
                                    "%s still shows %s" % (vname, ym_label(ym)),
                                    fix % {"month": closed_name} if fix else
                                    "load the %s %s report into the %s dashboard Sheet"
                                    % (closed_name, vshort, store),
                                    month=ym_label(ym)))

    # 5. SEO months: months[-1], else the client-level seoMonth (never the top-level one).
    months = c.get("months") or []
    seo_ym = month_in(str(months[-1]), ref) if months else month_in(str(c.get("seoMonth") or ""), ref)
    if seo_ym is None:
        issues.append(issue("AMBER", "SEO_EMPTY", "seo_empty", "no SEO months yet (pending build)",
                            seo_fix))
    elif seo_ym < closed:
        age = (ref - month_end(seo_ym)).days
        issues.append(issue("AMBER", "SEO_OLD_MONTH", "seo_old", "SEO months stop at %s, %d days past that month's end"
                            % (ym_label(seo_ym), age), seo_fix, month=ym_label(seo_ym), age_days=age))

    # 6. Top-level refresh stamp.
    upd_raw = payload.get("updated")
    upd = parse_updated(upd_raw, ref)
    upd_age = (ref - upd).days if upd else None
    if upd is None:
        notes.append("top-level updated unreadable: %r" % (upd_raw,))
    elif upd_age > UPDATED_MAX_DAYS:
        issues.append(issue("AMBER", "UPDATED_OLD", "updated_old", "last refreshed %s, %d days ago" % (upd_raw, upd_age),
                            "open the %s dashboard Sheet and check why it has not refreshed since %s"
                            % (store, upd_raw), age_days=upd_age))

    snapshot = {"updated": upd_raw, "updated_age_days": upd_age, "crmSource": crm_src[:200],
                "period": payload.get("period"), "leads_mtd": mtd,
                "kpi_labels": [str(x.get("label")) for x in c.get("kpiCards") or []],
                "seo_last_month": ym_label(seo_ym) if seo_ym else None,
                "ppc_months": {vk: v.get("month") for vk, v in ppc.items() if isinstance(v, dict)}
                if isinstance(ppc, dict) else {}}
    return issues, notes, snapshot


def fetch(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "DigitalCLIQ-ai-team-dash-check/1.0",
                                               "Accept": "application/json"})
    last = None
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
                status = getattr(r, "status", 200)
            try:
                return status, json.loads(body.decode("utf-8"))
            except ValueError:
                snippet = body[:80].decode("utf-8", "replace").replace("\n", " ")
                raise RuntimeError("HTTP %s but not JSON (starts %r); the web app may need re-deploying "
                                   "with access set to Anyone" % (status, snippet))
        except (urllib.error.URLError, OSError, RuntimeError) as e:
            last = e
            if attempt == 1 and not isinstance(e, RuntimeError):
                time.sleep(3)
                continue
            break
    if isinstance(last, urllib.error.HTTPError):
        raise RuntimeError("HTTP %s %s" % (last.code, last.reason))
    raise RuntimeError(str(getattr(last, "reason", None) or last))


def prior_file(shift_dir, date):
    """Newest earlier shift folder's data/dashboards.json, for first_seen carry-forward."""
    parent = os.path.dirname(os.path.abspath(shift_dir))
    best = None
    try:
        names = os.listdir(parent)
    except OSError:
        return None
    for n in names:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", n) and n < date.isoformat():
            p = os.path.join(parent, n, "data", "dashboards.json")
            if os.path.isfile(p) and (best is None or n > best[0]):
                best = (n, p)
    if not best:
        return None
    try:
        with open(best[1]) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def brief_line(store, st):
    if st["status"] == "NO DATA":
        since = ("no dashboard data since %s" % st["last_answered"] if st.get("last_answered")
                 else "no dashboard data tonight")
        return "%s dashboard: %s (%s). Fix: open the dashboard link and check it loads." % (
            store, since, st["error"])
    iss = sorted(st["issues"], key=lambda i: -LEVELS[i["level"]])
    fixes = []
    for i in iss:
        if i["fix"] not in fixes:
            fixes.append(i["fix"])
    days = max(i["days_open"] for i in iss)
    open_txt = "first seen tonight" if days == 0 else "open %d days" % days
    what = "; ".join(i["text"] for i in iss).rstrip(".")
    return "%s dashboard: %s, %s. %s. Fix: %s." % (
        store, st["status"], open_txt, what[:1].upper() + what[1:], "; then ".join(fixes[:3]))


def ask_fields(store, st, date):
    iss = sorted(st["issues"], key=lambda i: -LEVELS[i["level"]])
    return {"store": store, "owner": "Drew", "label": "%s client dashboard stale" % store,
            "ask": iss[0]["fix"][0].upper() + iss[0]["fix"][1:],
            "evidence": "; ".join(i["text"] for i in iss)[:300] + " (dash_check.py, data/dashboards.json %s)"
            % date.isoformat(),
            "if_skipped": "the %s GM keeps seeing these numbers on the live dashboard" % store,
            "done_when": "dash_check.py shows %s GREEN, or AMBER with no RED" % store
            if st["status"] == "RED" else "dash_check.py shows %s GREEN" % store,
            "source": "dash_check.py %s" % date.isoformat()}


def run(shift_dir, date, in_dir=None, timeout=30, stores=None):
    prior = prior_file(shift_dir, date) or {}
    prior_first, prior_ok = {}, {}
    for s, v in (prior.get("stores") or {}).items():
        for i in v.get("issues") or []:
            prior_first[(s, i.get("key"))] = i.get("first_seen")
        for key, first in (v.get("carried_first_seen") or {}).items():  # a NO DATA night keeps the chain
            prior_first.setdefault((s, key), first)
        prior_ok[s] = v.get("last_answered")
    out = {"schema": "dashboards.v1", "date": date.isoformat(),
           "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
           "source": "files: %s" % in_dir if in_dir else "live GET of each /exec endpoint",
           "month": "%04d-%02d" % (date.year, date.month), "last_closed_month": "%04d-%02d" % prev_month(date),
           "prior_file_date": prior.get("date"), "stores": {}, "brief_lines": [], "asks": []}
    failed = 0
    for store in stores or DASHBOARDS:
        cfg = DASHBOARDS[store]
        st = {"key": cfg["key"], "name": cfg["name"], "sheet_id": cfg["sheet"], "status": "GREEN",
              "issues": [], "notes": []}
        try:
            if in_dir:
                with open(os.path.join(in_dir, "%s.json" % cfg["key"])) as f:
                    payload, st["http"] = json.load(f), None
            else:
                st["http"], payload = fetch(cfg["url"], timeout)
            issues, notes, snap = evaluate(store, payload, date)
        except Exception as e:  # never guess: a store that did not answer is NO DATA
            failed += 1
            st.update({"status": "NO DATA", "error": str(e)[:200], "last_answered": prior_ok.get(store),
                       "carried_first_seen": {k: f for (s_, k), f in prior_first.items() if s_ == store}})
            out["stores"][store] = st
            out["brief_lines"].append(brief_line(store, st))
            continue
        for i in issues:
            i["first_seen"] = prior_first.get((store, i["key"])) or date.isoformat()
            i["days_open"] = (date - dt.date.fromisoformat(i["first_seen"])).days
        st.update({"issues": issues, "notes": notes, "snapshot": snap, "last_answered": date.isoformat()})
        if issues:
            st["status"] = max((i["level"] for i in issues), key=lambda lv: LEVELS[lv])
            out["brief_lines"].append(brief_line(store, st))
            out["asks"].append(ask_fields(store, st, date))
        out["stores"][store] = st
    data_dir = os.path.join(shift_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, "dashboards.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    return out, path, failed


# ---------------------------------------------------------------- selftest

def selftest():
    ref = dt.date(2026, 9, 26)
    assert parse_updated("Sep 25, 6:23 AM", ref) == dt.date(2026, 9, 25)
    assert parse_updated("Sep 25, 2026", ref) == dt.date(2026, 9, 25)
    assert parse_updated("Dec 30, 9:00 PM", dt.date(2027, 1, 2)) == dt.date(2026, 12, 30)
    assert parse_updated("Sep 20, 2026", ref) == dt.date(2026, 9, 20)
    assert parse_updated("garbage", ref) is None
    assert month_in("Leads (Jun)", ref) == (2026, 6)
    assert month_in("Organic Sessions (Sep MTD)", ref) == (2026, 9)
    assert month_in("Marketing spend", ref) is None
    assert month_in("Jun 2026", ref) == (2026, 6) and month_in("August", ref) == (2026, 8)
    assert month_in("Dec", dt.date(2027, 1, 5)) == (2026, 12)
    assert month_in("Mon Jun 01 2026 00:00:00 GMT-0700 (Pacific Daylight Time)", ref) == (2026, 6)

    def pay(store, **kw):
        c = {"kpiCards": [{"label": "Leads (MTD)", "val": "770", "src": "FOCUS"}], "months": ["Jul", "Aug"],
             "pace": {"leads": {"mtd": 770}}, "ppc": {"v": {"name": "Vendor (Paid Search)", "month": "August"}}}
        top = {"updated": "Sep 25, 6:23 AM", "crmSource": "google-sheet v11 (focus detailed: 770 leads / 80 sold)"}
        for key, val in kw.items():
            (top if key in ("updated", "crmSource") else c)[key] = val
        top["clients"] = {DASHBOARDS[store]["key"]: c}
        return top

    lv = lambda iss: sorted((i["rule"], i["level"]) for i in iss)
    assert evaluate("NCBMW", pay("NCBMW"), ref)[0] == [], "clean payload must be clean"
    iss = evaluate("SBMW", pay("SBMW", crmSource="google-sheet v1 (CRM tab empty - paste ...)",
                               kpiCards=[{"label": "Leads (Jun)", "val": "1,124", "src": "MOMENTUM"},
                                         {"label": "Tracked Keywords (Jun)", "val": "1", "src": "SEMRUSH"}],
                               pace={"leads": {"mtd": 0}}, months=[],
                               ppc={"pixel": {"name": "Pixel Motion (Paid Search)", "month": "Jun 2026"}},
                               updated="Sep 20, 2026"), ref)[0]
    assert lv(iss) == sorted([("CRM_EMPTY", "RED"), ("MTD_ZERO", "RED"), ("KPI_OLD_MONTH", "RED"),
                              ("KPI_SEO_OLD_MONTH", "AMBER"), ("PPC_OLD_MONTH", "RED"), ("SEO_EMPTY", "AMBER"),
                              ("UPDATED_OLD", "AMBER")]), lv(iss)
    # Day 3 grace: 0 MTD on the 3rd is not flagged; last closed month is fine on the 1st.
    assert evaluate("NCBMW", pay("NCBMW", pace={"leads": {"mtd": 0}}, updated="Sep 2, 2026"), dt.date(2026, 9, 3))[0] == []
    oct1 = evaluate("NCBMW", pay("NCBMW", kpiCards=[{"label": "Leads (Sep)", "src": "FOCUS"}], months=["Sep"],
                                 updated="Sep 30, 2026", ppc={"v": {"name": "V", "month": "September"}}),
                    dt.date(2026, 10, 1))[0]
    assert oct1 == [], oct1
    assert lv(evaluate("MCP", pay("MCP", months=["May", "Jun"]), ref)[0]) == [("SEO_OLD_MONTH", "AMBER")]
    assert lv(evaluate("MCP", pay("MCP", months=[], seoMonth="Mon Jun 01 2026 00:00:00 GMT-0700"), ref)[0]) == [
        ("SEO_OLD_MONTH", "AMBER")]
    assert lv(evaluate("NCBMW", pay("NCBMW", crmSource="v2 CHECK: header moved"), ref)[0]) == [("CRM_EMPTY", "RED")]
    # SBMW Pixel Motion grace: August is current through Oct 20 (September's report is due then), RED from Oct 21;
    # two months behind is RED at once; the same block at NCBMW or MCP has no grace.
    px = lambda store, month, day: pay(store, months=["Aug", "Sep"], updated="Oct %d, 2026" % day,
                                       ppc={"pixel": {"name": "Pixel Motion (Paid Search)", "month": month}})
    for day in (1, 6, 20):
        iss, notes, _ = evaluate("SBMW", px("SBMW", "Aug 2026", day), dt.date(2026, 10, day))
        assert iss == [] and any("not flagged" in n and "due by Oct 20" in n for n in notes), (day, iss, notes)
    iss = evaluate("SBMW", px("SBMW", "Aug 2026", 21), dt.date(2026, 10, 21))[0]
    assert lv(iss) == [("PPC_OLD_MONTH", "RED")] and "Coop Files September" in iss[0]["fix"], iss
    assert "load the" not in iss[0]["fix"] and "%(" not in iss[0]["fix"], iss[0]["fix"]
    assert lv(evaluate("SBMW", px("SBMW", "Jul 2026", 6), dt.date(2026, 10, 6))[0]) == [("PPC_OLD_MONTH", "RED")]
    assert evaluate("SBMW", px("SBMW", "Sep 2026", 25), dt.date(2026, 10, 25))[0] == []
    for store in ("NCBMW", "MCP"):
        iss = evaluate(store, px(store, "Aug 2026", 6), dt.date(2026, 10, 6))[0]
        assert lv(iss) == [("PPC_OLD_MONTH", "RED")] and iss[0]["fix"].startswith("load the September Pixel Motion"), iss
    # SBMW CRM fix points at the loader's Ingest Log, not a paste.
    iss = evaluate("SBMW", pay("SBMW", crmSource="momentum kpi: CHECK: no KPI Summary"), ref)[0]
    assert lv(iss) == [("CRM_EMPTY", "RED")] and "Ingest Log" in iss[0]["fix"] and "paste" not in iss[0]["fix"], iss
    print("selftest: all checks passed")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("shift", nargs="?", help="shift folder, e.g. outputs/ai-team/2026-09-28")
    ap.add_argument("--date", help="YYYY-MM-DD (default: the shift folder's name, else today Pacific)")
    ap.add_argument("--in-dir", help="read saved payloads {key}.json from here instead of the network")
    ap.add_argument("--store", action="append", choices=sorted(DASHBOARDS), help="limit to a store (repeatable)")
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.shift:
        ap.error("give the shift folder, e.g. outputs/ai-team/2026-09-28")
    base = os.path.basename(os.path.normpath(a.shift))
    try:
        date = dt.date.fromisoformat(a.date or (base if re.fullmatch(r"\d{4}-\d{2}-\d{2}", base)
                                                else pacific_today().isoformat()))
    except ValueError:
        ap.error("--date must be YYYY-MM-DD")
    out, path, failed = run(a.shift, date, a.in_dir, a.timeout, a.store)
    for store, st in out["stores"].items():
        if st["status"] == "NO DATA":
            print("%s: NO DATA. %s" % (store, st["error"]))
        else:
            top = sorted(st["issues"], key=lambda i: -LEVELS[i["level"]])
            first = (top[0]["text"][:1].upper() + top[0]["text"][1:]) if top else ""
            more = " (+%d more)" % (len(top) - 1) if len(top) > 1 else ""
            print("%s: %s. %s" % (store, st["status"], (first + more + ".") if top else "Nothing stale."))
    if out["brief_lines"]:
        print("\nFor Missing tonight:")
        for line in out["brief_lines"]:
            print("- " + line)
    print("\nWrote %s." % path)
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
