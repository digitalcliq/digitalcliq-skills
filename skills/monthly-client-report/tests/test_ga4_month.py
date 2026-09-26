#!/usr/bin/env python3
"""Tests for ga4_month.py: generator shape, lead-class events, the Measurement
Health gate, tag-change handling, the date gate, and every failure exit.

Run:  python3 tests/test_ga4_month.py        (plain script, exits 1 on any failure)
      python3 -m pytest tests/test_ga4_month.py
Offline by default: a fake gdata module (a small day-by-day GA4 simulator,
written to a temp dir) stands in for the ai-team one, so nothing touches the
network, Drew's token, or the vault.

Live check (read-only GA4 pulls on Drew's token, about 20 seconds):
      MCR_GA4_LIVE=1 python3 tests/test_ga4_month.py
It asserts the figures verified on 2026-09-26: SBMW Aug 36,403 sessions and
394 lead events with no MoM, SBMW Jul 37,135, NCBMW Jul 17,370 (the filed July
report), NCBMW Aug 17,077 and 247 not held back, MCP Aug 139 lead events with
the page views excluded, and SBMW's 'ig' source counted as Instagram.
"""
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
SCRIPT = os.path.join(SKILL_DIR, "ga4_month.py")
SAMPLE = os.path.join(HERE, "sample_mcp.json")
VAULT = os.environ.get("DIGITALCLIQ_VAULT_ROOT") or os.path.expanduser("~/Desktop/DigitalCLIQ Brain HQ")
EM_DASH = chr(0x2014)  # house rule: never in generated copy

# Same classes and order as the ai-team measurement-rules.json (version 2026-09-23).
RULES = {
    "version": "test",
    "event_classes": {
        "page_view": "page_?view|pageview|screen_view|view_item|_visit$|^visit_|(^|[_ ])(vdp|vlp|srp)([_ ]|$)"
                     "|about[_ ]?us|website visits",
        "lead": "submit|submission|lead|call|phone|chat|sms|text_?us|appointment|contact_us|order|purchase|"
                "credit|trade|store visit",
        "soft": "engagement|start|scroll|click|view|open|video|download|subscri|direction|hover|impression|menu",
    },
    "rules": [
        {"id": "LANDING_PAGE_LOAD_TRIGGER", "gm": "A page on the site records a lead the moment someone "
                                                  "opens it, before they fill anything in."},
        {"id": "DUPLICATE_LEAD_EVENTS", "gm": "One web form appears to be counted twice under two names."},
    ],
}

FAKE_GDATA = r'''
"""Fake ai-team gdata for ga4_month tests: a tiny day-by-day GA4 simulator."""
import datetime as dt
import json
import os
import sys

GA4_PROPERTIES = {"SBMW": "297584513", "NCBMW": "487046736", "NOI": "277100567",
                  "MCP": "321466006", "ATLAS": "408152419"}
KEY_EVENTS_ONLY = {"filter": {"fieldName": "keyEvents"}}
PACIFIC = None
S = json.load(open(os.environ["FAKE_GA4_SCENARIO"]))


def die(msg, code=1):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(code)


def _days(start, end):
    d, e = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    while d <= e:
        yield d
        d += dt.timedelta(days=1)


def _active(spec, d):
    s, e = spec.get("start"), spec.get("end")
    return (not s or d >= dt.date.fromisoformat(s)) and (not e or d <= dt.date.fromisoformat(e))


def ga4_report(store, start, end, dims, metrics, limit=1000, dim_filter=None, order_metric=None,
               metric_filter=None):
    if S.get("auth_fail"):
        die("not authorized yet. Drew runs: python3 gdata.py auth")
    if S.get("http_error"):
        raise RuntimeError(S["http_error"])
    out = {}
    missing = set(S.get("missing_days", []))

    def add(key, vals):
        row = out.setdefault(key, {})
        for k, v in vals.items():
            row[k] = row.get(k, 0) + v

    for d in _days(start, end):
        if d.isoformat() in missing:
            continue
        ctx = {"date": d.strftime("%Y%m%d")}
        if "eventName" in dims:
            for ev in S.get("events", []):
                if _active(ev, d):
                    ctx2 = dict(ctx, eventName=ev["name"], sessionDefaultChannelGroup=ev.get("channel", "Direct"))
                    add(tuple(ctx2[x] for x in dims), {"keyEvents": ev["per_day"]})
        elif "sessionSource" in dims:
            for so in S.get("social", []):
                ctx2 = dict(ctx, sessionSource=so["source"], sessionDefaultChannelGroup=so["channel"])
                add(tuple(ctx2[x] for x in dims), {"sessions": so["per_day"]})
        else:
            for ch, v in S.get("channels", {}).items():
                ctx2 = dict(ctx, sessionDefaultChannelGroup=ch)
                add(tuple(ctx2[x] for x in dims), {"sessions": v["sessions"], "engagedSessions": v["engaged"]})
    rows = []
    for key, vals in out.items():
        r = dict(zip(dims, key))
        r.update({m: vals.get(m, 0) for m in metrics})
        rows.append(r)
    return rows
'''

AUG_CHANNELS = {"Paid Social": {"sessions": 400, "engaged": 20}, "Direct": {"sessions": 230, "engaged": 80},
                "Organic Search": {"sessions": 230, "engaged": 160}, "Referral": {"sessions": 100, "engaged": 50},
                "Paid Search": {"sessions": 60, "engaged": 40}, "Email": {"sessions": 20, "engaged": 1},
                "Organic Social": {"sessions": 10, "engaged": 2}, "AI Assistant": {"sessions": 4, "engaged": 3}}
SOCIAL = [{"source": "facebook", "channel": "Paid Social", "per_day": 400},
          {"source": "facebook.com", "channel": "Organic Social", "per_day": 8},
          {"source": "ig", "channel": "Organic Social", "per_day": 1},
          {"source": "ig", "channel": "Paid Social", "per_day": 2},
          {"source": "l.instagram.com", "channel": "Organic Social", "per_day": 1}]


def scenario(**kw):
    s = {"channels": AUG_CHANNELS, "social": SOCIAL,
         "events": [{"name": "form_submit", "per_day": 4, "channel": "Organic Search"},
                    {"name": "asc_click_to_call", "per_day": 2, "channel": "Paid Search"},
                    {"name": "schedule_service_page_view", "per_day": 30, "channel": "Organic Search"},
                    {"name": "asc_form_engagement", "per_day": 5, "channel": "Direct"}]}
    s.update(kw)
    return s


class Run:
    def __init__(self, rc, out, err):
        self.rc, self.out, self.err = rc, out, err
        self.data = json.loads(out) if rc == 0 and out.strip() else None


def run(args, scen=None, health=None, registry=None, rules=RULES, scripts_dir=None):
    tmp = tempfile.mkdtemp(prefix="ga4m_test_")
    try:
        scripts = scripts_dir or os.path.join(tmp, "ai-team", "scripts")
        if scripts_dir is None:
            os.makedirs(scripts)
            with open(os.path.join(scripts, "gdata.py"), "w") as f:
                f.write(FAKE_GDATA)
        with open(os.path.join(tmp, "scenario.json"), "w") as f:
            json.dump(scen or scenario(), f)
        rules_path = os.path.join(tmp, "rules.json")
        with open(rules_path, "w") as f:
            json.dump(rules, f)
        health_path = os.path.join(tmp, "health.json")
        with open(health_path, "w") as f:
            json.dump(health if health is not None else {"nights": {}, "open": {}}, f)
        cmd = [sys.executable, SCRIPT, "--rules", rules_path, "--health-state", health_path] + list(args)
        if registry is not None:
            reg_path = os.path.join(tmp, "registry.json")
            with open(reg_path, "w") as f:
                json.dump(registry, f)
            cmd += ["--registry", reg_path]
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH",)}
        env.update({"AI_TEAM_SCRIPTS": scripts, "FAKE_GA4_SCENARIO": os.path.join(tmp, "scenario.json"),
                    "DIGITALCLIQ_VAULT_ROOT": tmp, "PYTHONDONTWRITEBYTECODE": "1"})
        r = subprocess.run(cmd, cwd="/", capture_output=True, text=True, env=env)
        return Run(r.returncode, r.stdout, r.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def kpi(data, prefix):
    return next((k for k in data["kpis"] if k["label"].startswith(prefix)), None)


def night(store, **rules):
    base = {"_ga4": "ok", "KEY_EVENT_RATE_HIGH": "clean", "NON_LEAD_KEY_EVENTS": "clean",
            "DUPLICATE_LEAD_EVENTS": "clean", "LANDING_PAGE_LOAD_TRIGGER": "clean"}
    base.update(rules)
    return {store: base}


# ---------------------------------------------------------------- tests

def test_full_month_generator_shape():
    r = run(["--store", "SBMW", "--month", "2026-08", "--today", "2026-09-26"])
    assert r.rc == 0, r.err
    d = r.data
    for key in ("available", "kpis", "channels", "social_referral", "insights", "source", "manifest"):
        assert key in d, key
    assert d["available"] is True
    per_day = sum(v["sessions"] for v in AUG_CHANNELS.values())
    assert kpi(d, "Total Sessions")["value"] == f"{per_day * 31:,}"
    assert kpi(d, "Total Sessions")["sub"] == f"vs July: +0.0% ({per_day * 31:,})"
    assert re.fullmatch(r"GA4 Data API property p297584513, 2026-08-01 to 2026-08-31, pulled \S+", d["source"])
    assert "SOURCE: GA4 Data API property p297584513" in r.err
    # Every channel row has the same keys (the generator takes headers from the first row).
    heads = {tuple(row) for row in d["channels"]}
    assert heads == {("Channel", "Sessions", "Share", "Eng Rate", "Lead Events")}, heads
    assert len(d["channels"]) == 6 and d["channels"][-1]["Channel"] == "All other (3)"
    assert d["channels"][0] == {"Channel": "Paid Social", "Sessions": "12,400", "Share": "38.0%",
                                "Eng Rate": "5.0%", "Lead Events": "0"}
    assert kpi(d, "Top Channel")["sub"] == "Paid Social"
    for m in d["manifest"]:
        assert set(m) == {"value", "label", "source"}, m
        assert m["source"].startswith(("GA4 Data API", "health-state")), m
    assert EM_DASH not in r.out
    assert d["ga4_month"]["days_present"] == 31 and d["ga4_month"]["complete"] is True
    print("PASS: full month prints the generator's traffic shape plus source and manifest")


def test_lead_class_only_excludes_page_views_and_soft():
    r = run(["--store", "SBMW", "--month", "2026-08", "--today", "2026-09-26"])
    assert r.rc == 0, r.err
    lead = kpi(r.data, "Lead Events (form, call, chat)")
    assert lead["value"] == f"{(4 + 2) * 31:,}", lead           # form_submit + asc_click_to_call only
    assert lead["sub"] == "vs July: +0% (186)", lead
    le = r.data["ga4_month"]["lead_events"]
    assert le["excluded_key_events_by_class"] == {"page_view": 930, "soft": 155}
    col = sum(int(row["Lead Events"].replace(",", "")) for row in r.data["channels"])
    assert col == 186, col
    assert "Key Events" not in json.dumps(r.data["channels"])
    print("PASS: lead KPI and column count lead-class events only (page views and form starts excluded)")


def test_tag_change_prints_count_without_mom():
    scen = scenario()
    scen["events"].append({"name": "generate_lead", "per_day": 4, "start": "2026-07-14",
                           "channel": "Organic Search"})
    r = run(["--store", "SBMW", "--month", "2026-08", "--today", "2026-09-26"], scen)
    assert r.rc == 0, r.err
    lead = kpi(r.data, "Lead Events")
    assert lead["value"] == f"{(4 + 2 + 4) * 31:,}" and lead["sub"] == "tracking changed, see CRM", lead
    le = r.data["ga4_month"]["lead_events"]
    assert le["mom_pct"] is None
    assert [(c["event"], c["change"], c["date"]) for c in le["tag_changes"]] == \
        [("generate_lead", "started", "2026-07-14")]
    ins = " ".join(i["text"] for i in r.data["insights"])
    assert "began counting on Jul 14" in ins and "CRM leads" in ins and "generate_lead" not in ins
    # form_submit and generate_lead now match in total and in every channel: warn, never dedupe.
    assert "form_submit and generate_lead both total 124" in r.err
    print("PASS: a lead tag that starts mid-window drops the MoM and points to CRM leads")


def test_tag_change_ignores_sparse_and_ramping_events():
    sys.path.insert(0, SKILL_DIR)
    try:
        import ga4_month as g
    finally:
        sys.path.pop(0)
    start, end = dt.date(2026, 7, 1), dt.date(2026, 8, 31)

    def series(first, last, per_day, every=1):
        d, out, i = first, {}, 0
        while d <= last:
            if i % every == 0:
                out[d.strftime("%Y%m%d")] = per_day(d)
            d += dt.timedelta(days=1)
            i += 1
        return out
    daily = {
        "big_steady": series(start, end, lambda d: 5),
        # Sparse burst, about 1% of the window (NCBMW asc_comm_submission_parts shape).
        "sparse": series(dt.date(2026, 7, 7), dt.date(2026, 7, 19), lambda d: 1, every=2),
        # Low in the first weeks, ramps late (NCBMW asc_form_submission shape).
        "ramp": series(dt.date(2026, 7, 4), end, lambda d: 1 if d < dt.date(2026, 8, 15) else 6, every=1),
    }
    assert g.tag_changes(daily, start, end) == [], g.tag_changes(daily, start, end)
    daily["renamed"] = series(start, dt.date(2026, 8, 10), lambda d: 3)
    got = g.tag_changes(daily, start, end)
    assert [(c["event"], c["change"], c["date"]) for c in got] == [("renamed", "stopped", "2026-08-10")], got
    print("PASS: tag-change detector ignores sparse bursts and late ramps, catches a real stop")


def test_health_gate_holds_back_leads():
    health = {"nights": {"2026-09-20": night("ATLAS", LANDING_PAGE_LOAD_TRIGGER=[
        "red", "/contact records a lead on page load, 234 on 196 visits (Sep 12 to 18)"])}, "open": {}}
    r = run(["--store", "ATLAS", "--month", "2026-09", "--today", "2026-09-26", "--allow-partial"],
            health=health)
    assert r.rc == 0, r.err
    d = r.data
    assert kpi(d, "Lead Events") is None
    assert all("Lead Events" not in row for row in d["channels"])
    assert d["ga4_month"]["lead_events"]["suppressed"] is True
    assert any(i["text"].startswith("<b>Website lead count held back:</b> A page on the site records")
               for i in d["insights"])
    assert any(m["value"] == "held back" and "LANDING_PAGE_LOAD_TRIGGER" in m["source"] for m in d["manifest"])
    print("PASS: LANDING_PAGE_LOAD_TRIGGER inside the month holds the lead KPI and column back")


def test_health_gate_ignores_non_gating_rules_and_other_months():
    health = {"nights": {
        "2026-08-20": night("MCP", KEY_EVENT_RATE_HIGH=["red", "x"], NON_LEAD_KEY_EVENTS=["red", "y"]),
        "2026-09-20": night("MCP", DUPLICATE_LEAD_EVENTS=["amber", "z"]),   # next month: not August
        "2026-08-02": night("SBMW", DUPLICATE_LEAD_EVENTS=["amber", "other store"]),
    }, "open": {}}
    r = run(["--store", "MCP", "--month", "2026-08", "--today", "2026-09-26"], health=health)
    assert r.rc == 0, r.err
    le = r.data["ga4_month"]["lead_events"]
    assert le["suppressed"] is False and le["health_covered"] is True
    assert kpi(r.data, "Lead Events")["sub"].startswith("vs July:")
    print("PASS: KEY_EVENT_RATE_HIGH / NON_LEAD_KEY_EVENTS, other months and other stores never gate")


def test_prior_month_gate_drops_mom_only():
    health = {"nights": {"2026-07-20": night("SBMW", DUPLICATE_LEAD_EVENTS=["amber", "pair"])}, "open": {}}
    r = run(["--store", "SBMW", "--month", "2026-08", "--today", "2026-09-26"], health=health)
    assert r.rc == 0, r.err
    lead = kpi(r.data, "Lead Events")
    assert lead is not None and lead["sub"] == "tracking changed, see CRM"
    assert "no MoM" not in json.dumps(r.data["kpis"])
    assert "Measurement Health nights for SBMW in Aug 1-31" in r.err   # August itself not covered: warn
    print("PASS: a gating rule in the prior month keeps the count and drops only the MoM")


def test_date_gate():
    for today, rc in (("2026-10-01", 3), ("2026-10-02", 3), ("2026-10-03", 0)):
        r = run(["--store", "SBMW", "--month", "2026-09", "--today", today])
        assert r.rc == rc, (today, r.rc, r.err)
        if rc == 3:
            assert "DATE GATE" in r.err and "2026-10-03" in r.err and "--allow-partial" in r.err
            assert r.out == ""
    r = run(["--store", "SBMW", "--today", "2026-10-03"])
    assert r.rc == 0 and r.data["ga4_month"]["month"] == "2026-09", r.err
    r = run(["--store", "SBMW", "--month", "2026-11", "--today", "2026-10-03"])
    assert r.rc == 3 and "has not started" in r.err
    print("PASS: date gate refuses Sep on Oct 1 and Oct 2, passes Oct 3; --month defaults to last month")


def test_allow_partial_relabels_true_range():
    r = run(["--store", "SBMW", "--month", "2026-08", "--today", "2026-09-02", "--allow-partial"])
    assert r.rc == 0, r.err
    s = kpi(r.data, "Total Sessions")
    assert s["label"] == "Total Sessions, Aug 1-30", s
    assert s["sub"].startswith("vs Jul 1-30: ") and s["sub"].endswith("Aug 31 still processing"), s
    g = r.data["ga4_month"]
    assert (g["end"], g["prior_end"], g["complete"]) == ("2026-08-30", "2026-07-30", False)
    assert "2026-08-01 to 2026-08-30" in r.data["source"]
    assert any("Partial month" in i["text"] for i in r.data["insights"])
    r = run(["--store", "SBMW", "--month", "2026-10", "--today", "2026-10-02", "--allow-partial"])
    assert r.rc == 3 and "no day of October 2026 is final yet" in r.err
    print("PASS: --allow-partial reports Aug 1-30 as 'Aug 31 still processing' against Jul 1-30")


def test_short_month_compares_full_prior_month():
    r = run(["--store", "SBMW", "--month", "2026-02", "--today", "2026-03-10"])
    assert r.rc == 0, r.err
    g = r.data["ga4_month"]
    assert (g["prior_start"], g["prior_end"], g["prior_label"]) == ("2026-01-01", "2026-01-31", "January")
    print("PASS: a complete February compares with all of January")


def test_social_line_counts_ig_and_fb():
    r = run(["--store", "SBMW", "--month", "2026-08", "--today", "2026-09-26"])
    assert r.rc == 0, r.err
    soc = r.data["ga4_month"]["social"]
    assert soc["unpaid"] == {"Facebook": 248, "Instagram": 62} and soc["paid"] == {"Facebook": 12400, "Instagram": 62}
    line = r.data["social_referral"]
    assert line.startswith("Unpaid social posts and links brought 310 sessions") and "Instagram 62" in line
    assert "Paid social ads brought 12,462 more" in line
    print("PASS: social line counts 'ig' as Instagram and splits paid from unpaid")


def test_last_day_and_missing_days_warn_only():
    r = run(["--store", "SBMW", "--month", "2026-08", "--today", "2026-09-26"],
            scenario(missing_days=["2026-08-31", "2026-08-15"]))
    assert r.rc == 0, r.err
    assert "only 29 of 31 days in Aug 1-31 have sessions" in r.err
    assert "last day 2026-08-31 has 0 sessions" in r.err
    print("PASS: missing days and a low last day warn on stderr and still exit 0")


def test_auth_failure_exits_4():
    r = run(["--store", "SBMW", "--month", "2026-08", "--today", "2026-09-26"], scenario(auth_fail=True))
    assert r.rc == 4 and r.out == "", (r.rc, r.out)
    assert "not authorized yet" in r.err and "AUTH FAILURE" in r.err and "gdata.py\" auth" in r.err
    r = run(["--store", "SBMW", "--month", "2026-08", "--today", "2026-09-26"],
            scenario(http_error="HTTP 403 from https://analyticsdata.googleapis.com/x: PERMISSION_DENIED"))
    assert r.rc == 4 and "AUTH FAILURE" in r.err
    r = run(["--store", "SBMW", "--month", "2026-08", "--today", "2026-09-26"],
            scenario(http_error="HTTP 500 from https://analyticsdata.googleapis.com/x: backend"))
    assert r.rc == 6 and "API ERROR" in r.err
    r = run(["--store", "SBMW", "--month", "2026-08", "--today", "2026-09-26"],
            scripts_dir=os.path.join(tempfile.gettempdir(), "no_such_ai_team_scripts"))
    assert r.rc == 4 and "gdata.py not found" in r.err
    print("PASS: auth failures exit 4 with a clear message; other API errors exit 6")


def test_property_and_registry_errors():
    with open(os.path.join(SKILL_DIR, "reference", "client_registry.json")) as f:
        reg = json.load(f)
    bad = json.loads(json.dumps(reg))
    for c in bad["clients"]:
        if c["code"] == "NOI":
            c["ga4_property"] = "297560496"
    r = run(["--store", "NOI", "--month", "2026-08", "--today", "2026-09-26"], registry=bad)
    assert r.rc == 5 and "PROPERTY MISMATCH" in r.err and "297560496" in r.err and "277100567" in r.err
    r = run(["--store", "CHC", "--month", "2026-08", "--today", "2026-09-26"])
    assert r.rc == 5 and "omit the Traffic section" in r.err
    r = run(["--store", "KCC", "--month", "2026-08", "--today", "2026-09-26"])
    assert r.rc == 5 and "PROPERTY MISMATCH" in r.err
    r = run(["--store", "ZZZ", "--month", "2026-08", "--today", "2026-09-26"])
    assert r.rc == 2 and "not in the client registry" in r.err
    r = run(["--store", "atlas", "--month", "2026-08", "--today", "2026-09-26"])
    assert r.rc == 0 and r.data["ga4_month"]["property"] == "p408152419", r.err
    r = run(["--store", "SBMW", "--month", "2026-8"])
    assert r.rc == 2
    print("PASS: property mismatch, no property, unknown store and bad month exit non-zero")


def test_generator_renders_helper_output():
    """The printed block drops into the merged JSON and builds HTML (no PDF render, no Chrome)."""
    fonts = os.path.join(VAULT, "Resources", "brand-assets", "fonts")
    if not os.path.isdir(fonts):
        print("SKIP: brand fonts not found, generator HTML build not checked")
        return
    sys.path.insert(0, SKILL_DIR)
    try:
        import generate_monthly_report as gen
    finally:
        sys.path.pop(0)
    logo = os.path.join(VAULT, "Resources", "brand-assets", "digital-cliq-logo-solid-1000px-wide.png")
    with open(SAMPLE) as f:
        base = json.load(f)
    health = {"nights": {"2026-09-20": night("ATLAS", LANDING_PAGE_LOAD_TRIGGER=["red", "x"])}, "open": {}}
    for args, h in ((["--store", "SBMW", "--month", "2026-08", "--today", "2026-09-26"], None),
                    (["--store", "ATLAS", "--month", "2026-09", "--today", "2026-09-26", "--allow-partial"], health)):
        r = run(args, health=h)
        assert r.rc == 0, r.err
        data = json.loads(json.dumps(base))
        data["traffic"] = r.data
        html = gen.build_html(data, logo)
        assert "Website Traffic" in html and "Total Sessions" in html
        assert ("Lead Events" in html) == (h is None)
    print("PASS: generator builds the report HTML from the helper's traffic block")


def test_live_ga4_matches_verified_figures():
    if os.environ.get("MCR_GA4_LIVE") != "1":
        print("SKIP: live GA4 check (set MCR_GA4_LIVE=1 to run read-only pulls on Drew's token)")
        return
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    def live(store, month):
        r = subprocess.run([sys.executable, SCRIPT, "--store", store, "--month", month],
                           cwd="/", capture_output=True, text=True, env=env)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)["ga4_month"]
    g = live("SBMW", "2026-08")
    assert (g["sessions"], g["prior_sessions"], g["days_present"]) == (36403, 37135, 31), g["sessions"]
    assert g["lead_events"]["count"] == 394 and g["lead_events"]["mom_pct"] is None
    assert g["social"]["paid"].get("Instagram") == 24 and g["social"]["unpaid"].get("Instagram") == 46
    assert live("SBMW", "2026-07")["sessions"] == 37135
    g = live("NCBMW", "2026-07")
    assert (g["sessions"], g["prior_sessions"]) == (17370, 13707)
    g = live("NCBMW", "2026-08")
    assert g["sessions"] == 17077 and g["lead_events"]["count"] == 247 and not g["lead_events"]["suppressed"]
    g = live("MCP", "2026-08")
    assert g["lead_events"]["count"] == 139 and g["lead_events"]["excluded_key_events_by_class"]["page_view"] > 20000
    print("PASS: live GA4 pulls match the figures verified on 2026-09-26")


TESTS = [
    test_full_month_generator_shape,
    test_lead_class_only_excludes_page_views_and_soft,
    test_tag_change_prints_count_without_mom,
    test_tag_change_ignores_sparse_and_ramping_events,
    test_health_gate_holds_back_leads,
    test_health_gate_ignores_non_gating_rules_and_other_months,
    test_prior_month_gate_drops_mom_only,
    test_date_gate,
    test_allow_partial_relabels_true_range,
    test_short_month_compares_full_prior_month,
    test_social_line_counts_ig_and_fb,
    test_last_day_and_missing_days_warn_only,
    test_auth_failure_exits_4,
    test_property_and_registry_errors,
    test_generator_renders_helper_output,
    test_live_ga4_matches_verified_figures,
]


if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t()
        except Exception as e:  # report every test, not just the first crash
            failed += 1
            print(f"FAIL: {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)
