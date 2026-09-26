#!/usr/bin/env python3
"""GA4 month pull for /monthly-client-report. Standard library only.

Pulls one month of GA4 for a client from the Google Analytics Data API through
the ai-team gdata module (Drew's read-only OAuth token, no browser) and prints
the `traffic` block that generate_monthly_report.py renders.

Usage:
    python3 ga4_month.py --store SBMW [--month 2026-08] [--allow-partial] [--out FILE]

    --month          YYYY-MM, default the previous calendar month (Pacific time).
    --allow-partial  Run before the month is final. The range stops at the last
                     final day and the KPI label names the true range, for
                     example "Aug 1-30" with "Aug 31 still processing".
    --max-channels   Rows in the channel table, default 6 (the smallest channels
                     roll into one "All other" row).
    --out FILE       Also write the JSON to FILE.
    --today DATE     Pretend today is DATE (tests and dry runs of the date gate).
    --registry, --rules, --health-state   Override the default file paths.

stdout is the `traffic` JSON, ready to drop into the merged report JSON as-is:
    available, kpis, channels, social_referral, insights   (what the generator reads)
    source      "GA4 Data API property p{id}, {start} to {end}, pulled {timestamp}"
    manifest    [{value, label, source}] entries for the Step 5 facts manifest
    notes       plain-language warnings for Drew's run summary (never rendered)
    ga4_month   the raw numbers behind every figure (never rendered)
The generator ignores the last four keys. The source line and every warning
also go to stderr.

What it reports, and why:
- Sessions and MoM come from the dimensionless total, never from summed rows.
  Channel shares are channel-table sessions over that same total.
- Raw key events are NOT reported. GA4 key events at 4 of 5 stores are mostly
  page views (MCP Aug 2026: 22,541 of 22,718). The KPI is "Lead Events (form,
  call, chat)": key events whose name falls in the 'lead' class of the ai-team
  measurement-rules.json, classified in the same order as health.py
  (page_view, then lead, then soft).
- The lead KPI is held back when LANDING_PAGE_LOAD_TRIGGER or
  DUPLICATE_LEAD_EVENTS was amber or red on a Measurement Health night whose
  evaluated day (the night minus one) falls inside the reported range
  (outputs/ai-team/ledgers/health-state.json). KEY_EVENT_RATE_HIGH and
  NON_LEAD_KEY_EVENTS do not gate it, since the class filter already drops
  those events.
- No dedupe heuristic. When a lead tag starts or stops firing inside either
  month, or a gating rule fired in the prior month, the count prints with no
  MoM % and points to CRM leads.
- Social sessions are sessionSource matching facebook, instagram, youtube or
  tiktok, plus the exact sources ig and fb, split into paid and unpaid by the
  session's default channel group.

Date gate: GA4 finalizes a day about two days after it ends, so a day counts
as final once three calendar days have started after it (Aug 31 is final on
Sep 3). A month is complete on the 3rd of the next month. Before that the
script refuses unless --allow-partial is passed. A last day below half of its
4-week same-weekday average prints a warning only.

Exit codes (message on stderr, nothing on stdout):
    0  ok
    2  USAGE: bad --month or --today, unknown store
    3  DATE GATE: month not final yet (wait for the 3rd or pass --allow-partial)
    4  AUTH FAILURE: gdata missing, not authorized yet, or token expired or
       revoked (Drew re-runs gdata.py auth; the browser path is the fallback)
    5  PROPERTY MISMATCH or CONFIG: registry and gdata disagree on the GA4
       property, the store has no GA4 property, or measurement-rules.json is
       missing
    6  API ERROR: GA4 answered with a non-auth error, the network failed, or
       the month came back empty (retry once, then tell Drew)

gdata is imported from $AI_TEAM_SCRIPTS, else
<vault>/.claude/skills/ai-team/scripts, where <vault> is
$DIGITALCLIQ_VAULT_ROOT or ~/Desktop/DigitalCLIQ Brain HQ.
"""
import argparse
import calendar
import datetime as dt
import importlib
import json
import os
import re
import sys

try:
    from zoneinfo import ZoneInfo
    PACIFIC = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover
    PACIFIC = None

HERE = os.path.dirname(os.path.abspath(__file__))
VAULT = os.environ.get("DIGITALCLIQ_VAULT_ROOT") or os.path.expanduser("~/Desktop/DigitalCLIQ Brain HQ")
AI_TEAM_SCRIPTS = os.environ.get("AI_TEAM_SCRIPTS") or os.path.join(VAULT, ".claude", "skills", "ai-team", "scripts")
REGISTRY = os.path.join(HERE, "reference", "client_registry.json")
RULES = os.path.join(os.path.dirname(os.path.abspath(AI_TEAM_SCRIPTS)), "references", "measurement-rules.json")
HEALTH_STATE = os.path.join(VAULT, "outputs", "ai-team", "ledgers", "health-state.json")

EXIT_USAGE, EXIT_DATE_GATE, EXIT_AUTH, EXIT_CONFIG, EXIT_API = 2, 3, 4, 5, 6

# A day is final once this many calendar days have started after it:
# Aug 31 + 3 = Sep 3, so the August report can run on the 3rd.
FINAL_AFTER_DAYS = 3
# Rules that make the lead-event count itself wrong (the class filter cannot fix them).
GATING_RULES = ("LANDING_PAGE_LOAD_TRIGGER", "DUPLICATE_LEAD_EVENTS")
# Tag-change detection: an event counts as started (or stopped) when it is
# silent for a stretch in which its own active daily rate would have produced
# at least TAG_CHANGE_EXPECTED_MIN events. Sporadic low-volume events never trip it.
TAG_CHANGE_MIN_EVENTS = 5
TAG_CHANGE_EXPECTED_MIN = 5.0
# Only events carrying at least this share of the window's lead events are checked:
# a sparse event (NCBMW asc_comm_submission_parts, 1-2%) fires in bursts and cannot
# move the MoM enough to matter.
TAG_CHANGE_MIN_SHARE = 0.05
# The expected count in a silent stretch uses the event's rate over the 14 days next to it,
# so a later ramp (NCBMW asc_form_submission in September) cannot fake an earlier start.
TAG_CHANGE_EDGE_DAYS = 14
DUPLICATE_PAIR_MIN = 10
WEEKDAY_RATIO_WARN = 0.5
SOCIAL_SOURCE_REGEX = "facebook|instagram|youtube|tiktok|^ig$|^fb$"
SOCIAL_PLATFORMS = (("Facebook", r"facebook|^fb$"), ("Instagram", r"instagram|^ig$"),
                    ("YouTube", r"youtube"), ("TikTok", r"tiktok"))
KEY_EVENTS_ONLY = {"filter": {"fieldName": "keyEvents",
                              "numericFilter": {"operation": "GREATER_THAN", "value": {"doubleValue": 0}}}}
LEAD_LABEL = "Lead Events (form, call, chat)"
EM_DASH = "\u2014"

WARNINGS = []


def warn(msg):
    WARNINGS.append(msg)
    print("WARN: " + msg, file=sys.stderr)


def note(notes, msg):
    notes.append(msg)
    print("NOTE: " + msg, file=sys.stderr)


def fail(code, kind, msg):
    print("ga4_month: %s: %s" % (kind, msg), file=sys.stderr)
    sys.exit(code)


def n(x):
    return f"{int(x):,}"


# ---------------------------------------------------------------- dates

def parse_month(s):
    m = re.fullmatch(r"(\d{4})-(\d{2})", s or "")
    if not m or not 1 <= int(m.group(2)) <= 12:
        fail(EXIT_USAGE, "USAGE", "--month must be YYYY-MM, got %r" % s)
    return int(m.group(1)), int(m.group(2))


def month_bounds(y, m):
    return dt.date(y, m, 1), dt.date(y, m, calendar.monthrange(y, m)[1])


def prev_month(y, m):
    return (y - 1, 12) if m == 1 else (y, m - 1)


def short_range(a, b):
    """'Aug 1-31', 'Aug 31', or 'Jul 30-Aug 2'."""
    if a == b:
        return "%s %d" % (calendar.month_abbr[a.month], a.day)
    if (a.year, a.month) == (b.year, b.month):
        return "%s %d-%d" % (calendar.month_abbr[a.month], a.day, b.day)
    return "%s %d-%s %d" % (calendar.month_abbr[a.month], a.day, calendar.month_abbr[b.month], b.day)


def resolve_range(y, m, today, allow_partial):
    """The date range to report, or a DATE GATE refusal (exit 3)."""
    first, last = month_bounds(y, m)
    last_final = today - dt.timedelta(days=FINAL_AFTER_DAYS)
    month_name = "%s %d" % (calendar.month_name[m], y)
    gate_day = last + dt.timedelta(days=FINAL_AFTER_DAYS)
    if first >= today:
        fail(EXIT_DATE_GATE, "DATE GATE", "%s has not started or has no data yet (today is %s)."
             % (month_name, today.isoformat()))
    if last <= last_final:
        return {"start": first, "end": last, "complete": True,
                "range_label": short_range(first, last), "pending_label": ""}
    if not allow_partial:
        fail(EXIT_DATE_GATE, "DATE GATE",
             "%s is not final in GA4 until %s. GA4 finalizes each day about two days after it ends, so "
             "today (%s) the last final day is %s. Re-run on or after %s for the full month, or pass "
             "--allow-partial to report %s labeled as a partial month."
             % (month_name, gate_day.isoformat(), today.isoformat(), last_final.isoformat(),
                gate_day.isoformat(),
                short_range(first, last_final) if last_final >= first else "nothing yet"))
    if last_final < first:
        fail(EXIT_DATE_GATE, "DATE GATE",
             "no day of %s is final yet (today is %s); the first partial run is possible on %s."
             % (month_name, today.isoformat(), (first + dt.timedelta(days=FINAL_AFTER_DAYS)).isoformat()))
    pending_start = last_final + dt.timedelta(days=1)
    pending = ("%s still processing" % short_range(pending_start, last)) if last < today else "month in progress"
    return {"start": first, "end": last_final, "complete": False,
            "range_label": short_range(first, last_final), "pending_label": pending}


# ---------------------------------------------------------------- config

def load_json(path, what, required=True):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        if required:
            fail(EXIT_CONFIG, "CONFIG", "cannot read %s at %s: %s" % (what, path, e))
        warn("cannot read %s at %s (%s); the lead-event gate is not applied." % (what, path, e))
        return None


def find_client(registry, store):
    for c in registry.get("clients", []):
        if str(c.get("code", "")).upper() == store.upper():
            return c
    codes = ", ".join(str(c.get("code", "")) for c in registry.get("clients", []))
    fail(EXIT_USAGE, "USAGE", "store %s is not in the client registry. Known codes: %s" % (store, codes))


def import_gdata():
    if not os.path.isfile(os.path.join(AI_TEAM_SCRIPTS, "gdata.py")):
        fail(EXIT_AUTH, "AUTH FAILURE",
             "ai-team gdata.py not found in %s (set AI_TEAM_SCRIPTS). The GA4 API path is unavailable; "
             "use the browser fallback in SKILL.md." % AI_TEAM_SCRIPTS)
    sys.path.insert(0, AI_TEAM_SCRIPTS)
    sys.dont_write_bytecode = True  # never leave a __pycache__ in the vault's ai-team folder
    try:
        return importlib.import_module("gdata")
    finally:
        sys.path.pop(0)


def event_classifier(rules):
    ec = (rules or {}).get("event_classes") or {}
    missing = [k for k in ("page_view", "lead", "soft") if not ec.get(k)]
    if missing:
        fail(EXIT_CONFIG, "CONFIG", "measurement-rules.json has no event_classes %s" % ", ".join(missing))
    rx = {k: re.compile(ec[k], re.I) for k in ("page_view", "lead", "soft")}

    def cls(name):
        for k in ("page_view", "lead", "soft"):
            if rx[k].search(name or ""):
                return k
        return "other"
    return cls


# ---------------------------------------------------------------- GA4 calls

class Puller:
    def __init__(self, gdata, store):
        self.g = gdata
        self.store = store

    def __call__(self, start, end, dims, metrics, **kw):
        kw.setdefault("limit", 10000)
        try:
            return self.g.ga4_report(self.store, start.isoformat(), end.isoformat(), dims, metrics, **kw) or []
        except SystemExit as e:  # gdata.die(): not authorized yet, bad client file, token refresh refused
            fail(EXIT_AUTH, "AUTH FAILURE",
                 "gdata could not get a GA4 token (its ERROR line is above, exit %s). Drew re-runs "
                 "python3 \"%s/gdata.py\" auth in a terminal; until then use the browser fallback."
                 % (e.code, AI_TEAM_SCRIPTS))
        except RuntimeError as e:
            text = str(e)
            if re.search(r"HTTP (401|403)\b", text):
                fail(EXIT_AUTH, "AUTH FAILURE",
                     "GA4 refused the token for %s: %s. Drew re-runs gdata.py auth, or checks this login "
                     "still has access to the property." % (self.store, text[:300]))
            fail(EXIT_API, "API ERROR", "GA4 Data API call failed for %s: %s. Retry once, then tell Drew."
                 % (self.store, text[:300]))
        except OSError as e:  # URLError, timeouts
            fail(EXIT_API, "API ERROR", "network error calling the GA4 Data API: %s. Retry once, then "
                 "tell Drew." % e)


def ymd(d):
    return d.strftime("%Y%m%d")


# ---------------------------------------------------------------- analysis

def health_hits(state, store, start, end):
    """Gating-rule findings on nights whose evaluated day (night - 1) is in [start, end].
    Returns (hits, covered): covered is False when no night evaluated this store in the range."""
    hits, covered = [], False
    for night, stores in sorted(((state or {}).get("nights") or {}).items()):
        try:
            evaluated = dt.date.fromisoformat(night) - dt.timedelta(days=1)
        except ValueError:
            continue
        s = (stores or {}).get(store)
        if not s or not start <= evaluated <= end:
            continue
        covered = True
        for rule in GATING_RULES:
            v = s.get(rule)
            sev, text = None, ""
            if isinstance(v, (list, tuple)) and v:
                sev, text = str(v[0]), (str(v[1]) if len(v) > 1 else "")
            elif isinstance(v, dict):
                sev, text = str(v.get("severity", "")), str(v.get("finding", ""))
            if sev in ("red", "amber"):
                hits.append({"night": night, "rule": rule, "severity": sev, "finding": text})
    return hits, covered


def tag_changes(daily, window_start, window_end):
    """daily: {event: {YYYYMMDD: count}} over the window. Returns starts and stops."""
    out = []
    window_total = sum(sum(days.values()) for days in daily.values())
    for ev, days in sorted(daily.items()):
        fired = sorted(d for d, c in days.items() if c > 0)
        n_total = sum(days.values())
        if not fired or n_total < TAG_CHANGE_MIN_EVENTS or n_total < TAG_CHANGE_MIN_SHARE * window_total:
            continue
        first = dt.datetime.strptime(fired[0], "%Y%m%d").date()
        last = dt.datetime.strptime(fired[-1], "%Y%m%d").date()
        span = (last - first).days + 1
        edge = min(TAG_CHANGE_EDGE_DAYS, span)

        def local_rate(a, b):  # events per day inside [a, b], the stretch next to the gap
            return sum(c for d, c in days.items() if ymd(a) <= d <= ymd(b)) / float(edge)
        gap_before = (first - window_start).days
        gap_after = (window_end - last).days
        if gap_before > 0:
            exp = local_rate(first, first + dt.timedelta(days=edge - 1)) * gap_before
            if exp >= TAG_CHANGE_EXPECTED_MIN:
                out.append({"event": ev, "change": "started", "date": first.isoformat(),
                            "silent_days": gap_before, "expected_in_gap": round(exp, 1)})
        if gap_after > 0:
            exp = local_rate(last - dt.timedelta(days=edge - 1), last) * gap_after
            if exp >= TAG_CHANGE_EXPECTED_MIN:
                out.append({"event": ev, "change": "stopped", "date": last.isoformat(),
                            "silent_days": gap_after, "expected_in_gap": round(exp, 1)})
    return out


def social_split(rows):
    """sessionSource x sessionDefaultChannelGroup x sessions -> (unpaid, paid) sessions per platform."""
    unpaid, paid = {}, {}
    for r in rows or []:
        src = str(r.get("sessionSource") or "")
        platform = next((name for name, rx in SOCIAL_PLATFORMS if re.search(rx, src, re.I)), None)
        if not platform:
            continue
        bucket = paid if re.match(r"paid", str(r.get("sessionDefaultChannelGroup") or ""), re.I) else unpaid
        bucket[platform] = bucket.get(platform, 0) + int(r.get("sessions") or 0)
    return unpaid, paid


def weekday_check(daily_sessions, end):
    """Warn (never fail) when the last day is below half its 4-week same-weekday average."""
    last = daily_sessions.get(ymd(end), 0)
    prior = [daily_sessions.get(ymd(end - dt.timedelta(days=7 * i)), 0) for i in range(1, 5)]
    avg = sum(prior) / 4.0
    ratio = (last / avg) if avg else None
    if ratio is not None and ratio < WEEKDAY_RATIO_WARN:
        warn("last day %s has %s sessions, %d%% of its 4-week same-weekday average (%.0f). It may still be "
             "processing or tracking may have dropped; check before quoting the month."
             % (end.isoformat(), n(last), round(ratio * 100), avg))
    return {"date": end.isoformat(), "sessions": last, "same_weekday_avg_4wk": round(avg, 1),
            "ratio": None if ratio is None else round(ratio, 3)}


# ---------------------------------------------------------------- formatting

def pct(part, whole, dp=1):
    return "%.*f%%" % (dp, 100.0 * part / whole) if whole else "n/a"


def mom(cur, prev):
    return None if not prev else (cur - prev) * 100.0 / prev


def status_for(delta, band):
    if delta is None:
        return "neutral"
    return "positive" if delta >= band else ("negative" if delta <= -band else "neutral")


def join_platforms(counts):
    return ", ".join("%s %s" % (k, n(v)) for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))


def scrub(obj):
    """House rule: no em dashes in anything this script writes."""
    if isinstance(obj, str):
        return obj.replace(EM_DASH, ", ")
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()}
    return obj


def tracking_insight(changes, p_hits, month_name, leads, prior_label):
    """One GM-level sentence on why the lead count has no MoM. No event names."""
    started = [c for c in changes if c["change"] == "started"]
    stopped = [c for c in changes if c["change"] == "stopped"]
    day = lambda c: dt.date.fromisoformat(c["date"])
    if started and stopped:
        a, b = sorted((day(started[0]), day(stopped[0])))
        what = "the site's lead tags changed around %s" % short_range(a, b)
    elif started:
        what = "a new lead tag began counting on %s" % short_range(day(started[0]), day(started[0]))
    elif stopped:
        what = "a lead tag stopped counting after %s" % short_range(day(stopped[0]), day(stopped[0]))
    else:
        what = "website lead tracking had a known fault in %s" % prior_label
    return ("<b>Website lead tracking changed:</b> %s, so %s's %s website lead events are not compared "
            "with %s. CRM leads are the trend to use." % (what, month_name, n(leads), prior_label))


# ---------------------------------------------------------------- main build

def build(args):
    now = dt.datetime.now(PACIFIC) if PACIFIC else dt.datetime.now().astimezone()
    today = dt.date.fromisoformat(args.today) if args.today else now.date()
    y, m = parse_month(args.month) if args.month else prev_month(today.year, today.month)

    # 1. Date gate first: it needs no token and no network.
    rng = resolve_range(y, m, today, args.allow_partial)
    start, end = rng["start"], rng["end"]
    py, pm = prev_month(y, m)
    p_first, p_last = month_bounds(py, pm)
    p_end = p_last if rng["complete"] else min(p_last, p_first + (end - start))
    month_name = calendar.month_name[m]
    prior_label = calendar.month_name[pm] if rng["complete"] else short_range(p_first, p_end)

    # 2. Client and property check.
    client = find_client(load_json(args.registry, "client registry"), args.store)
    store = str(client["code"]).upper()
    if str(client.get("status", "")).lower().startswith("inactive"):
        warn("%s is marked %r in the registry; Step 0 should not be building its report."
             % (client["code"], client.get("status")))
    reg_prop = str(client.get("ga4_property") or "").strip()
    if not reg_prop:
        fail(EXIT_CONFIG, "CONFIG", "%s has no ga4_property in the client registry: omit the Traffic section."
             % client["code"])
    gdata = import_gdata()
    g_prop = str((getattr(gdata, "GA4_PROPERTIES", {}) or {}).get(store) or "").strip()
    if not g_prop:
        fail(EXIT_CONFIG, "PROPERTY MISMATCH",
             "the registry lists GA4 property %s for %s but gdata.GA4_PROPERTIES has no %s entry. Add it to "
             "gdata.py and Context/connector-ids.md together, or use the browser fallback."
             % (reg_prop, client["code"], store))
    if reg_prop != g_prop:
        fail(EXIT_CONFIG, "PROPERTY MISMATCH",
             "registry says p%s for %s but gdata.GA4_PROPERTIES says p%s. Stop and ask Drew which is right "
             "(Context/connector-ids.md is the source of truth); never pick one." % (reg_prop, store, g_prop))

    # 3. Rules and health ledger.
    rules = load_json(args.rules, "measurement-rules.json")
    cls = event_classifier(rules)
    rules_version = rules.get("version", "?")
    gm_text = {r.get("id"): r.get("gm", "") for r in rules.get("rules", []) if isinstance(r, dict)}
    state = load_json(args.health_state, "health-state.json", required=False) or {}

    # 4. Pull (about ten small Data API calls, around 2 seconds in total).
    q = Puller(gdata, store)
    base = ["sessions", "engagedSessions"]
    key_only = getattr(gdata, "KEY_EVENTS_ONLY", KEY_EVENTS_ONLY)
    soc_filter = {"filter": {"fieldName": "sessionSource", "stringFilter": {
        "matchType": "PARTIAL_REGEXP", "value": SOCIAL_SOURCE_REGEX, "caseSensitive": False}}}
    cur_tot = (q(start, end, [], base) or [{}])[0]
    pri_tot = (q(p_first, p_end, [], base) or [{}])[0]
    ch_rows = q(start, end, ["sessionDefaultChannelGroup"], base, order_metric="sessions")
    ch_prior = q(p_first, p_end, ["sessionDefaultChannelGroup"], base, order_metric="sessions")
    daily_rows = q(start - dt.timedelta(days=28), end, ["date"], ["sessions"])
    ev_daily_rows = q(p_first, end, ["date", "eventName"], ["keyEvents"], metric_filter=key_only)
    ev_ch_rows = q(start, end, ["sessionDefaultChannelGroup", "eventName"], ["keyEvents"], metric_filter=key_only)
    soc_rows = q(start, end, ["sessionSource", "sessionDefaultChannelGroup"], ["sessions"],
                 dim_filter=soc_filter, order_metric="sessions")
    soc_prior = q(p_first, p_end, ["sessionSource", "sessionDefaultChannelGroup"], ["sessions"],
                  dim_filter=soc_filter, order_metric="sessions")

    pulled = now.isoformat(timespec="seconds")
    prop = "p%s" % g_prop
    source = "GA4 Data API property %s, %s to %s, pulled %s" % (prop, start.isoformat(), end.isoformat(), pulled)
    prior_source = "GA4 Data API property %s, %s to %s, pulled %s" % (
        prop, p_first.isoformat(), p_end.isoformat(), pulled)
    both = "%s; %s" % (source, prior_source)
    print("SOURCE: " + source, file=sys.stderr)
    notes, manifest = [], []

    def fact(value, label, src=source):
        manifest.append({"value": value, "label": label, "source": src})

    # 5. Sessions and engagement from the dimensionless totals.
    sessions, p_sessions = int(cur_tot.get("sessions") or 0), int(pri_tot.get("sessions") or 0)
    engaged, p_engaged = int(cur_tot.get("engagedSessions") or 0), int(pri_tot.get("engagedSessions") or 0)
    if not sessions:
        fail(EXIT_API, "API ERROR", "GA4 returned 0 sessions for %s %s to %s. Check the property before "
             "reporting." % (store, start.isoformat(), end.isoformat()))
    s_mom = mom(sessions, p_sessions)
    eng = engaged * 100.0 / sessions
    p_eng = p_engaged * 100.0 / p_sessions if p_sessions else None
    eng_delta = None if p_eng is None else eng - p_eng

    daily = {r.get("date"): int(r.get("sessions") or 0) for r in daily_rows}
    n_days = (end - start).days + 1
    present = sum(1 for i in range(n_days) if daily.get(ymd(start + dt.timedelta(days=i)), 0) > 0)
    if present < n_days:
        warn("only %d of %d days in %s have sessions; GA4 is missing days." % (present, n_days, rng["range_label"]))
    last_day = weekday_check(daily, end)

    # 6. Lead-class events.
    ev_daily, class_totals, by_event, p_by_event = {}, {}, {}, {}
    for r in ev_daily_rows:
        name, day, c_n = r.get("eventName") or "", r.get("date") or "", int(r.get("keyEvents") or 0)
        d = dt.datetime.strptime(day, "%Y%m%d").date()
        c = cls(name)
        if start <= d <= end:
            class_totals[c] = class_totals.get(c, 0) + c_n
        if c != "lead":
            continue
        per_day = ev_daily.setdefault(name, {})
        per_day[day] = per_day.get(day, 0) + c_n
        if start <= d <= end:
            by_event[name] = by_event.get(name, 0) + c_n
        elif p_first <= d <= p_end:
            p_by_event[name] = p_by_event.get(name, 0) + c_n
    leads, p_leads = sum(by_event.values()), sum(p_by_event.values())
    changes = tag_changes(ev_daily, p_first, end)
    for c in changes:
        c["month"] = "report" if dt.date.fromisoformat(c["date"]) >= start else "prior"
    hits, covered = health_hits(state, store, start, end)
    p_hits, p_covered = health_hits(state, store, p_first, p_end)
    suppressed = bool(hits)
    if state and not covered:
        warn("health-state.json has no Measurement Health nights for %s in %s, so the lead-event gate (%s) "
             "could not be applied to this month." % (store, rng["range_label"], ", ".join(GATING_RULES)))
    nights = sorted((state.get("nights") or {}).keys())
    for rule, info in ((state.get("open") or {}).get(store) or {}).items():
        if rule in GATING_RULES and not suppressed and nights and info.get("first_seen") == nights[0] \
                and nights[0] > end.isoformat():
            warn("%s has been open for %s since the health ledger began on %s, so it may predate %s. Check "
                 "before quoting lead events." % (rule, store, nights[0], rng["range_label"]))
    # Same total AND the same count in every channel, as health.py's DUPLICATE_LEAD_EVENTS requires.
    ev_by_ch = {}
    for r in ev_ch_rows:
        name = r.get("eventName") or ""
        if cls(name) == "lead":
            ch = r.get("sessionDefaultChannelGroup") or "(not set)"
            ev_by_ch.setdefault(name, {})[ch] = ev_by_ch.get(name, {}).get(ch, 0) + int(r.get("keyEvents") or 0)
    names = sorted(by_event)
    pairs = [(a, b, by_event[a]) for i, a in enumerate(names) for b in names[i + 1:]
             if by_event[a] == by_event[b] >= DUPLICATE_PAIR_MIN and ev_by_ch.get(a) == ev_by_ch.get(b)]
    for a, b, c_n in pairs:
        warn("%s and %s both total %s in %s with the same count in every channel; one form may fire two "
             "tags. The count is not deduped; quote CRM leads if the health ledger confirms a duplicate."
             % (a, b, n(c_n), rng["range_label"]))
    no_mom = []
    if changes:
        no_mom.append("lead tag change: " + "; ".join("%s %s %s" % (c["event"], c["change"], c["date"])
                                                      for c in changes))
    if p_hits:
        no_mom.append("gating rule fired in %s: %s" % (prior_label, ", ".join(sorted({h["rule"] for h in p_hits}))))
    if not p_leads:
        no_mom.append("no lead events in %s" % prior_label)
    lead_mom = None if (suppressed or no_mom) else mom(leads, p_leads)

    # 7. KPI cards.
    kpis = []
    # Stat-card subs are 11px in a ~160px card: keep them to one line where possible.
    if s_mom is None:
        s_sub = "no %s data" % prior_label
    elif rng["complete"]:
        s_sub = "vs %s: %+.1f%% (%s)" % (prior_label, s_mom, n(p_sessions))
    else:
        s_sub = "vs %s: %+.1f%% · %s" % (prior_label, s_mom, rng["pending_label"])
    kpis.append({"label": "Total Sessions" if rng["complete"] else "Total Sessions, %s" % rng["range_label"],
                 "value": n(sessions), "sub": s_sub, "status": status_for(s_mom, 1.0)})
    fact(n(sessions), "total sessions %s (traffic KPI)" % rng["range_label"])
    fact(n(p_sessions), "prior-period sessions %s" % short_range(p_first, p_end), prior_source)
    if s_mom is not None:
        fact("%+.1f%%" % s_mom, "sessions MoM vs %s" % prior_label, both)
    kpis.append({"label": "Engagement Rate", "value": "%.1f%%" % eng,
                 "sub": ("vs %s: %+.1f pts" % (prior_label, eng_delta)) if eng_delta is not None else "",
                 "status": status_for(eng_delta, 0.5)})
    fact("%.1f%%" % eng, "engagement rate %s (engagedSessions %s / sessions %s)"
         % (rng["range_label"], n(engaged), n(sessions)))
    if eng_delta is not None:
        fact("%+.1f pts" % eng_delta, "engagement rate change vs %s (%.1f%%)" % (prior_label, p_eng), both)

    ev_list = ", ".join("%s %s" % (k, n(v)) for k, v in sorted(by_event.items(), key=lambda kv: -kv[1]))
    lead_src = "%s; keyEvents by eventName, 'lead' class of measurement-rules.json v%s (%s)" % (
        source, rules_version, ev_list or "none")
    lead_src_short = "%s; lead class of measurement-rules.json v%s" % (source, rules_version)
    if suppressed:
        rule_ids = sorted({h["rule"] for h in hits})
        hit_nights = sorted({h["night"] for h in hits})
        note(notes, "Lead events held back: %s amber or red on health nights %s (latest: %s). Use CRM leads."
             % (", ".join(rule_ids), ", ".join(hit_nights), hits[-1]["finding"]))
        fact("held back", "website lead events %s" % rng["range_label"],
             "health-state.json nights %s: %s" % (", ".join(hit_nights), ", ".join(rule_ids)))
    else:
        if lead_mom is not None:
            l_sub, l_status = "vs %s: %+.0f%% (%s)" % (prior_label, lead_mom, n(p_leads)), status_for(lead_mom, 5.0)
        elif changes or p_hits:
            l_sub, l_status = "tracking changed, see CRM", "neutral"
        else:
            l_sub, l_status = "no %s baseline" % prior_label, "neutral"
        kpis.append({"label": LEAD_LABEL, "value": n(leads), "sub": l_sub, "status": l_status})
        fact(n(leads), "website lead events (form, call, chat) %s" % rng["range_label"], lead_src)
        if lead_mom is not None:
            fact("%+.0f%%" % lead_mom, "lead events MoM vs %s (%s)" % (prior_label, n(p_leads)),
                 "%s; %s" % (lead_src, prior_source))
        else:
            note(notes, "Lead events shown without MoM: %s." % "; ".join(no_mom))
    excluded = {k: v for k, v in class_totals.items() if k != "lead"}
    if excluded:
        notes.append("Not counted as leads in %s: %s key events (classes from measurement-rules.json)."
                     % (rng["range_label"], ", ".join("%s %s" % (n(v), k) for k, v in
                                                      sorted(excluded.items(), key=lambda kv: -kv[1]))))

    # 8. Channel table: shares over the dimensionless total, lead events per channel.
    ch_leads = {}
    for r in ev_ch_rows:
        if cls(r.get("eventName") or "") == "lead":
            ch = r.get("sessionDefaultChannelGroup") or "(not set)"
            ch_leads[ch] = ch_leads.get(ch, 0) + int(r.get("keyEvents") or 0)
    ch_rows = sorted(ch_rows, key=lambda r: -int(r.get("sessions") or 0))
    keep = ch_rows if len(ch_rows) <= args.max_channels else ch_rows[:args.max_channels - 1]
    rest = ch_rows[len(keep):]
    table = []

    def row(name, s, e, c_leads):
        out = {"Channel": name, "Sessions": n(s), "Share": pct(s, sessions), "Eng Rate": pct(e, s)}
        if not suppressed:
            out["Lead Events"] = n(c_leads)
        return out

    for r in keep:
        name = r.get("sessionDefaultChannelGroup") or "(not set)"
        s, e = int(r.get("sessions") or 0), int(r.get("engagedSessions") or 0)
        table.append(row(name, s, e, ch_leads.get(name, 0)))
        fact("%s / %s / %s eng%s" % (n(s), pct(s, sessions), pct(e, s),
                                     "" if suppressed else " / %s lead events" % n(ch_leads.get(name, 0))),
             "%s channel row" % name, source if suppressed else lead_src_short)
    if rest:
        rest_names = [r.get("sessionDefaultChannelGroup") or "(not set)" for r in rest]
        s = sum(int(r.get("sessions") or 0) for r in rest)
        e = sum(int(r.get("engagedSessions") or 0) for r in rest)
        label = "All other (%d)" % len(rest)
        table.append(row(label, s, e, sum(ch_leads.get(x, 0) for x in rest_names)))
        fact("%s / %s" % (n(s), pct(s, sessions)), "%s channel row: %s" % (label, ", ".join(rest_names)))
    ch_sum = sum(int(r.get("sessions") or 0) for r in ch_rows)
    if ch_sum != sessions:
        notes.append("Channel rows sum to %s vs the %s total (GA4 estimates distinct sessions per row); "
                     "shares use the total, as the KPI does." % (n(ch_sum), n(sessions)))
    if ch_rows:
        tname = ch_rows[0].get("sessionDefaultChannelGroup") or "(not set)"
        ts = int(ch_rows[0].get("sessions") or 0)
        kpis.append({"label": "Top Channel", "value": pct(ts, sessions), "sub": tname, "status": "neutral"})
        fact("%s (%s sessions)" % (pct(ts, sessions), n(ts)), "top channel %s" % tname)

    # 9. Social line.
    unpaid, paid = social_split(soc_rows)
    p_unpaid, _ = social_split(soc_prior)
    u_tot, pd_tot, pu_tot = sum(unpaid.values()), sum(paid.values()), sum(p_unpaid.values())
    if u_tot or pd_tot:
        parts = [("Unpaid social posts and links brought %s sessions, %s of the site (%s %s): %s."
                  % (n(u_tot), pct(u_tot, sessions), prior_label, n(pu_tot), join_platforms(unpaid)))
                 if u_tot else "No unpaid social sessions (%s %s)." % (prior_label, n(pu_tot))]
        if pd_tot:
            parts.append("Paid social ads brought %s more: %s." % (n(pd_tot), join_platforms(paid)))
        social_line = " ".join(parts)
    else:
        social_line = "No sessions from Facebook, Instagram, YouTube or TikTok in %s." % rng["range_label"]
    fact(social_line, "social referral line", "%s; sessionSource matching %s" % (source, SOCIAL_SOURCE_REGEX))

    # 10. Insights: only the tracking facts a GM needs. The main loop writes the rest.
    insights = []
    if suppressed:
        why = gm_text.get(sorted({h["rule"] for h in hits})[0]) or ""
        if not why or "{" in why:
            why = "Website lead tracking has a known fault this month."
        insights.append({"type": "info", "text": "<b>Website lead count held back:</b> %s Use CRM leads for "
                         "%s's lead count." % (why.rstrip(), month_name)})
    elif changes or p_hits:
        insights.append({"type": "info", "text": tracking_insight(changes, p_hits, month_name, leads, prior_label)})
    if not rng["complete"]:
        insights.append({"type": "info", "text": "<b>Partial month:</b> GA4 figures cover %s; %s."
                         % (rng["range_label"], rng["pending_label"])})

    return scrub({
        "available": True,
        "kpis": kpis,
        "channels": table,
        "social_referral": social_line,
        "insights": insights,
        "source": source,
        "manifest": manifest,
        "notes": WARNINGS + notes,
        "ga4_month": {
            "store": store, "property": prop, "month": "%04d-%02d" % (y, m),
            "start": start.isoformat(), "end": end.isoformat(), "complete": rng["complete"],
            "range_label": rng["range_label"], "pending_label": rng["pending_label"],
            "prior_start": p_first.isoformat(), "prior_end": p_end.isoformat(), "prior_label": prior_label,
            "today": today.isoformat(), "pulled_at": pulled,
            "days_present": present, "days_in_range": n_days, "last_day_check": last_day,
            "sessions": sessions, "prior_sessions": p_sessions,
            "sessions_mom_pct": None if s_mom is None else round(s_mom, 2),
            "engaged_sessions": engaged, "prior_engaged_sessions": p_engaged,
            "engagement_rate_pct": round(eng, 2),
            "prior_engagement_rate_pct": None if p_eng is None else round(p_eng, 2),
            "channels": ch_rows, "prior_channels": ch_prior,
            "lead_events": {
                "count": leads, "prior_count": p_leads, "by_event": by_event, "prior_by_event": p_by_event,
                "by_channel": ch_leads, "mom_pct": None if lead_mom is None else round(lead_mom, 1),
                "suppressed": suppressed, "health_hits": hits, "prior_health_hits": p_hits,
                "health_covered": covered, "prior_health_covered": p_covered,
                "tag_changes": changes, "no_mom_reasons": no_mom,
                "possible_duplicate_pairs": [list(p) for p in pairs],
                "excluded_key_events_by_class": excluded, "rules_version": rules_version,
            },
            "social": {"unpaid": unpaid, "paid": paid, "prior_unpaid": p_unpaid},
        },
    })


def main(argv=None):
    ap = argparse.ArgumentParser(description="GA4 month pull for /monthly-client-report (prints the traffic JSON).")
    ap.add_argument("--store", required=True, help="client code from the registry, e.g. SBMW or ATLAS")
    ap.add_argument("--month", help="YYYY-MM, default the previous calendar month")
    ap.add_argument("--allow-partial", action="store_true", help="report the final days of an unfinished month")
    ap.add_argument("--max-channels", type=int, default=6, help="channel table rows, default 6")
    ap.add_argument("--out", help="also write the JSON here")
    ap.add_argument("--today", help="YYYY-MM-DD, pretend today is this date (tests, date-gate dry runs)")
    ap.add_argument("--registry", default=REGISTRY)
    ap.add_argument("--rules", default=RULES)
    ap.add_argument("--health-state", default=HEALTH_STATE)
    args = ap.parse_args(argv)
    if args.today:
        try:
            dt.date.fromisoformat(args.today)
        except ValueError:
            fail(EXIT_USAGE, "USAGE", "--today must be YYYY-MM-DD, got %r" % args.today)
    if args.max_channels < 2:
        fail(EXIT_USAGE, "USAGE", "--max-channels must be 2 or more")
    text = json.dumps(build(args), indent=1, ensure_ascii=False)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
