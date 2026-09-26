#!/usr/bin/env python3
"""Tests for lead_mix.py: score-leads path resolution, loud failure, and the
Lead Mix math (summary rows, phone-ups, small samples, % Mix = 100).

Run:  python3 tests/test_lead_mix.py        (plain script, exits 1 on any failure)
      python3 -m pytest tests/test_lead_mix.py
Needs the sibling skills/score-leads folder (same layout in the repo and runtime).
Writes nothing outside a temp dir.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
LEAD_MIX = os.path.join(SKILL_DIR, "lead_mix.py")
SL_DIR = os.path.join(os.path.dirname(SKILL_DIR), "score-leads")
SL_SAMPLE = os.path.join(SL_DIR, "tests", "test_inputs", "score_leads_sample.csv")
SL_MOMENTUM_RAW = os.path.join(SL_DIR, "tests", "test_inputs", "momentum_raw_sample.csv")
EDGE = os.path.join(HERE, "test_inputs", "lead_mix_edge.csv")
EM_DASH = chr(0x2014)  # house rule: never in generated copy


def _env(**extra):
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "SCORE_LEADS_DIR")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(extra)
    return env


def run_lead_mix(crm_file, script=LEAD_MIX, **env):
    """Run lead_mix.py from cwd / with no PYTHONPATH, like a real skill run."""
    r = subprocess.run([sys.executable, script, crm_file], cwd="/",
                       capture_output=True, text=True, env=_env(**env))
    try:
        payload = json.loads(r.stdout)
    except ValueError:
        payload = None
    return r, payload


def _modules():
    """Import lead_mix and score_leads in-process for the unit-level checks."""
    for p in (SKILL_DIR, SL_DIR):
        if p not in sys.path:
            sys.path.insert(0, p)
    import lead_mix
    import score_leads
    return lead_mix, score_leads


def _row(source, leads, sales):
    return {"source": source, "leads": leads, "sales": sales}


def _mix_sum(payload):
    return sum(int(c["% Mix"].rstrip("%")) for c in payload["categories"])


def _cat(payload, label):
    for c in payload["categories"]:
        if c["Category"] == label:
            return c
    return None


# ---------------------------------------------------------------- path + exits

def test_sample_runs_from_root_without_pythonpath():
    """The sibling score-leads is found from cwd / and the Totals row is skipped."""
    r, d = run_lead_mix(SL_SAMPLE)
    assert r.returncode == 0, f"exit {r.returncode}: {r.stderr}"
    assert d and d["available"] is True, d
    assert d["total_leads"] == 450 and d["total_sold"] == 43, \
        f"Totals row double-counted: {d['total_leads']}/{d['total_sold']}"
    assert d["total_leads_raw"] == 900, d["total_leads_raw"]
    assert d["totals_check"].startswith("PASSED"), d["totals_check"]
    assert _mix_sum(d) == 100
    assert "Costco Auto" in [s["source"] for s in d["defaulted_sources"]]
    print("PASS: sample from cwd / -> 450 leads / 43 sold, Totals skipped")


def test_missing_score_leads_exits_nonzero():
    """No sibling folder and no SCORE_LEADS_DIR: loud failure, not a silent drop."""
    with tempfile.TemporaryDirectory() as tmp:
        lonely = os.path.join(tmp, "monthly-client-report")
        os.makedirs(lonely)
        shutil.copy(LEAD_MIX, lonely)
        r, d = run_lead_mix(SL_SAMPLE, script=os.path.join(lonely, "lead_mix.py"))
    assert r.returncode != 0, "missing score-leads must exit non-zero"
    assert d == {"available": False, "note": d["note"]}, d
    assert "score-leads not found" in r.stderr, r.stderr
    print("PASS: missing score-leads -> exit", r.returncode, "with stderr reason")


def test_bad_env_override_exits_nonzero():
    r, d = run_lead_mix(SL_SAMPLE, SCORE_LEADS_DIR="/nonexistent/score-leads")
    assert r.returncode != 0 and d["available"] is False
    assert "SCORE_LEADS_DIR" in r.stderr
    print("PASS: wrong SCORE_LEADS_DIR -> exit non-zero, no silent fallback")


def test_env_override_works():
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(LEAD_MIX, tmp)
        r, d = run_lead_mix(SL_SAMPLE, script=os.path.join(tmp, "lead_mix.py"),
                            SCORE_LEADS_DIR=SL_DIR)
    assert r.returncode == 0 and d["available"] is True, r.stderr
    print("PASS: SCORE_LEADS_DIR override imports score-leads")


def test_symlinked_skill_folder():
    """A symlinked skill folder still resolves its real sibling score-leads."""
    with tempfile.TemporaryDirectory() as tmp:
        link = os.path.join(tmp, "monthly-client-report")
        os.symlink(SKILL_DIR, link)
        r, d = run_lead_mix(SL_SAMPLE, script=os.path.join(link, "lead_mix.py"))
    assert r.returncode == 0 and d["available"] is True, r.stderr
    print("PASS: symlinked skill folder still imports score-leads")


def test_unrecognized_export_exits_nonzero():
    r, d = run_lead_mix(SL_MOMENTUM_RAW)
    assert r.returncode != 0, "an unreadable CRM export must not exit 0"
    assert d["available"] is False and "ingest failed" in d["note"]
    assert "ERROR lead_mix" in r.stderr
    print("PASS: unrecognized CRM export -> exit non-zero")


def test_usage_and_missing_file():
    r = subprocess.run([sys.executable, LEAD_MIX], cwd="/", capture_output=True,
                       text=True, env=_env())
    assert r.returncode == 2, r.returncode
    r, d = run_lead_mix("/nonexistent/crm.csv")
    assert r.returncode == 1 and d["available"] is False
    print("PASS: usage -> exit 2, missing file -> exit 1")


# ---------------------------------------------------------------- math

def test_edge_fixture():
    """Totals row, Phone Up, Drive-By, Not Specified, a 1-lead category, Costco."""
    r, d = run_lead_mix(EDGE)
    assert r.returncode == 0, r.stderr
    # Total equals the export's own Totals row (430 leads / 85 sold).
    assert (d["total_leads"], d["total_sold"]) == (430, 85), d
    assert d["totals_check"] == "PASSED leads=430 sold=85", d["totals_check"]
    assert d["summary_rows_skipped"] == [{"source": "Totals", "leads": 430, "sold": 85}]
    # Phone-ups are phone, so the "calls are not tracked" note must not fire.
    phone = _cat(d, "Phone / Call-in")
    assert phone and phone["Leads"] == "60", phone
    assert d["phone_tracked"] is True
    # Drive-By joins Walk-In (40 + 12).
    assert _cat(d, "Walk-in / Showroom Ups")["Leads"] == "52"
    # Not Specified is unattributed, not Internet.
    unknown = _cat(d, "Unknown / Unattributed")
    assert unknown and unknown["Leads"] == "2" and unknown["Sold"] == "31", unknown
    assert _cat(d, "Internet (1st-party)")["Leads"] == "170"  # Dealer Website + Costco
    # 1-lead categories read Low vol, never 100.0%.
    assert _cat(d, "Website Chat")["Close %"] == "Low vol"
    assert unknown["Close %"] == "Low vol"
    assert set(d["low_volume_categories"]) == {"Website Chat", "Unknown / Unattributed"}
    assert _mix_sum(d) == 100, [c["% Mix"] for c in d["categories"]]
    assert [s["source"] for s in d["defaulted_sources"]] == ["Costco Auto"]
    # The generator renders categories[] with the first row's keys as headers.
    assert all(list(c.keys()) == ["Category", "Leads", "% Mix", "Sold", "Close %"]
               for c in d["categories"])
    assert EM_DASH not in r.stdout
    print("PASS: edge fixture (Totals, Phone Up, Drive-By, Not Specified, Low vol, 100%)")


def test_classify_overrides():
    lm, SL = _modules()
    cases = {
        "Phone Up": "phone", "PHONE-UP": "phone", "Phone Ups": "phone",
        "Drive-By": "walk_in", "drive by": "walk_in", "Walk-In": "walk_in",
        "Not Specified": "unknown", "None": "unknown", "N/A": "unknown",
        "(blank)": "unknown", "Ungrouped": "unknown",
        "AutoTrader.com": "third_party", "Dealer Website": "website",
        "Gubagoo Chat": "chat", "BMW USA": "oem",
    }
    for src, want in cases.items():
        got, _ = lm.classify(src, SL)
        assert got == want, f"{src!r}: got {got}, want {want}"
    # The benchmark classifier itself is untouched: phone-ups still grade at the
    # walk-in rate in score-leads.
    assert SL.classify_benchmark_category("Phone Up") == "walk_in"
    assert lm.classify("Costco Auto", SL) == ("website", True)
    assert lm.classify("Dealer Website", SL) == ("website", False)
    assert lm.classify("Nonesuch Motors", SL)[0] != "unknown"
    for s in ("Totals", "TOTAL", "Grand Total:", "Average", " totals "):
        assert lm.is_summary_row(s), s
    for s in ("Total Auto Sales", "Totally Cars", "Dealer Website"):
        assert not lm.is_summary_row(s), s
    print("PASS: display overrides (phone-up, drive-by, unknowns) + summary rows")


def test_largest_remainder():
    lm, _ = _modules()
    for counts in ([1, 1, 1], [5] * 6, [225, 150, 125, 3], [1], [999, 1],
                   [170, 145, 60, 52, 2, 1], [7, 0, 3]):
        pcts = lm.largest_remainder(counts)
        assert sum(pcts) == 100, (counts, pcts)
        assert all(p >= 0 for p in pcts)
    # Six equal shares round to 17% each with plain rounding (102%).
    assert sum(round(5 / 30 * 100) for _ in range(6)) == 102
    assert lm.largest_remainder([1, 1, 1]) == [34, 33, 33]
    assert lm.largest_remainder([0, 0]) == [0, 0]
    print("PASS: largest-remainder % Mix always totals 100")


def test_totals_mismatch_warns_not_fails():
    lm, SL = _modules()
    rows = [_row("Dealer Website", 100, 10), _row("CarGurus", 50, 5),
            _row("Totals", 160, 15)]
    out, warns = lm.build_mix(rows, SL, "native")
    assert out["available"] is True and out["total_leads"] == 150
    assert out["totals_check"].startswith("MISMATCH"), out["totals_check"]
    assert any("Totals row" in w for w in warns), warns
    print("PASS: Totals mismatch -> WARN on stderr, payload still available")


def test_sold_over_leads_is_not_a_rate():
    lm, SL = _modules()
    rows = [_row("Dealer Website", 100, 10), _row("Not Specified", 12, 40)]
    out, warns = lm.build_mix(rows, SL, "native")
    unknown = _cat(out, "Unknown / Unattributed")
    assert unknown["Close %"] == "n/a", unknown
    assert any("n/a" in w for w in warns)
    print("PASS: sold > leads shows n/a, not a 333% close rate")


def test_average_row_not_used_as_totals():
    lm, SL = _modules()
    rows = [_row("Dealer Website", 100, 10), _row("CarGurus", 50, 5),
            _row("Average", 75, 8), _row("Total", 150, 15)]
    out, warns = lm.build_mix(rows, SL, "native")
    assert out["total_leads"] == 150
    assert out["totals_check"] == "PASSED leads=150 sold=15", out["totals_check"]
    assert not warns or all("Totals row" not in w for w in warns)
    print("PASS: Average row skipped and never used as the Totals reference")


TESTS = [
    test_sample_runs_from_root_without_pythonpath,
    test_missing_score_leads_exits_nonzero,
    test_bad_env_override_exits_nonzero,
    test_env_override_works,
    test_symlinked_skill_folder,
    test_unrecognized_export_exits_nonzero,
    test_usage_and_missing_file,
    test_edge_fixture,
    test_classify_overrides,
    test_largest_remainder,
    test_totals_mismatch_warns_not_fails,
    test_sold_over_leads_is_not_a_rate,
    test_average_row_not_used_as_totals,
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
