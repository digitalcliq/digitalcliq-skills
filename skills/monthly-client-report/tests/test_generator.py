#!/usr/bin/env python3
"""Smoke tests for the monthly report generator: graceful omission, email
guard, metadata guard, em-dash and regional-sourcing warnings, string
insights, and the Chrome render wrapper (timeout, no-PDF, stderr).

Hermetic by default: MCR_CHROME points at a small fake Chrome that writes a
real PDF (one page per HTML page div) with PyMuPDF, so no headless Chrome
launches during tests. Set MCR_TEST_REAL_CHROME=1 to render with the real
Chrome instead. Runs with plain python3 or pytest."""
import atexit
import datetime
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(HERE, "..", "generate_monthly_report.py")
SAMPLE = os.path.join(HERE, "sample_mcp.json")
LOGO = "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png"
EM_DASH = "\u2014"

_FAKE_DIR = tempfile.mkdtemp(prefix="mcr_fake_chrome_")
atexit.register(shutil.rmtree, _FAKE_DIR, True)

# Fake Chrome bodies. Each parses --print-to-pdf=<path> like the real one.
_FAKE_HEAD = f"""#!{sys.executable}
import os, re, sys, time
out = next(a.split("=", 1)[1] for a in sys.argv if a.startswith("--print-to-pdf="))
marker = os.environ.get("MCR_TEST_MARKER")
if marker:
    open(marker, "w").write("launched")
"""
_FAKE_WRITE = """
src = sys.argv[-1]
html = open(src[len("file://"):], encoding="utf-8").read() if src.startswith("file://") else ""
n = max(1, len(re.findall(r'<div class="page ', html)))
import fitz
doc = fitz.open()
for _ in range(n):
    doc.new_page(width=637.5, height=825)
doc.save(out)
"""
FAKES = {
    "ok": _FAKE_HEAD + _FAKE_WRITE,
    "sleep": _FAKE_HEAD + ("import subprocess\n"
                           "kid = subprocess.Popen(['sleep', '60'])\n"
                           "open(os.environ['MCR_TEST_KID'], 'w').write(str(kid.pid))\n"
                           "time.sleep(60)\n"),
    "nothing": _FAKE_HEAD + "sys.exit(0)\n",
    "error": _FAKE_HEAD + ("sys.stderr.write('line one\\nFATAL fake-chrome-"
                           "boom-7731\\n')\nsys.exit(21)\n"),
    "hang_after_write": _FAKE_HEAD + _FAKE_WRITE + "time.sleep(60)\n",
}


def fake(kind):
    path = os.path.join(_FAKE_DIR, f"chrome_{kind}")
    if not os.path.exists(path):
        with open(path, "w") as fh:
            fh.write(FAKES[kind])
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return path


def _env(chrome_kind="ok", **extra):
    env = dict(os.environ)
    if chrome_kind and os.environ.get("MCR_TEST_REAL_CHROME") != "1":
        env["MCR_CHROME"] = fake(chrome_kind)
    env.pop("MCR_STRICT", None)
    env.update({k: str(v) for k, v in extra.items()})
    return env


def run(data, out, chrome_kind="ok", **extra):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        path = f.name
    r = subprocess.run([sys.executable, GEN, path, out, LOGO],
                       capture_output=True, text=True,
                       env=_env(chrome_kind, **extra))
    os.unlink(path)
    return r


def load_gen():
    spec = importlib.util.spec_from_file_location("mcr_gen", GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _out(name):
    return os.path.join(tempfile.gettempdir(), name)


def _meta(**kw):
    m = {"client_name": "Kasama Coffee Collective", "client_code": "KCC",
         "month_label": "May 2026", "city": "", "state": "California",
         "brand": ""}
    m.update(kw)
    return m


# ---------------------------------------------------------------- pipeline
def test_minimal_omission():
    """A sparse client (only metadata + wins) must still render, no crash."""
    data = {
        "metadata": _meta(),
        "exec_summary": "Quiet but steady month for the cafe.",
        "wins": {"items": ["Refreshed the seasonal menu landing page."], "challenges": []},
    }
    out = _out("mcr_test_minimal.pdf")
    r = run(data, out)
    assert r.returncode == 0, f"minimal render failed: {r.stderr}"
    assert os.path.exists(out), "no PDF produced"
    # HTML pipeline: dark cover page + at least one interior page.
    import fitz
    doc = fitz.open(out)
    assert doc.page_count >= 2, f"expected cover + interior, got {doc.page_count} page(s)"
    doc.close()
    assert "WARN" not in r.stderr, f"clean data should not warn: {r.stderr}"
    print("PASS: graceful omission (sparse client renders, cover + interior)")
    os.unlink(out)


def test_sample_builds():
    """tests/sample_mcp.json (new regional schema) builds with exit 0 and
    no warnings."""
    with open(SAMPLE, encoding="utf-8") as fh:
        data = json.load(fh)
    out = _out("mcr_test_sample.pdf")
    r = run(data, out)
    assert r.returncode == 0, f"sample build failed: {r.stderr}"
    assert os.path.getsize(out) > 0
    assert "WARN" not in r.stderr, f"sample should be clean: {r.stderr}"
    print("PASS: sample_mcp.json builds clean (exit 0, no WARN)")
    os.unlink(out)


def test_legacy_regional_still_builds():
    """October safety: the old {stat, value, source} regional shape with
    undated Cox / Edmunds stats must WARN and still build with exit 0."""
    with open(SAMPLE, encoding="utf-8") as fh:
        data = json.load(fh)
    data["regional"]["stats"] = [
        {"stat": "CA new-vehicle registrations (YoY)", "value": "+3.1%", "source": "CNCDA, Q2 2026"},
        {"stat": "Avg transaction price (truck)", "value": "$58,400", "source": "Cox Automotive"},
        {"stat": "CA incentive spend (avg)", "value": "$3,250/unit", "source": "Edmunds"},
    ]
    out = _out("mcr_test_legacy.pdf")
    r = run(data, out)
    assert r.returncode == 0, f"legacy regional must not block: {r.stderr}"
    assert "WARN: regional:" in r.stderr and "Cox" in r.stderr and "Edmunds" in r.stderr, r.stderr
    assert "WARNING(S) on stderr" in r.stdout, r.stdout
    r2 = run(data, out, MCR_STRICT=1)
    assert r2.returncode != 0, "MCR_STRICT=1 should turn the warnings into a fail"
    print("PASS: legacy regional warns, exit 0; MCR_STRICT=1 fails it")
    if os.path.exists(out):
        os.unlink(out)


def test_no_reportlab():
    """The generator must use the design-system HTML pipeline, never
    reportlab, and Chrome is the declared engine (no silent WeasyPrint)."""
    with open(GEN, encoding="utf-8") as f:
        src = f.read()
    assert not re.search(r"^\s*(?:import|from)\s+reportlab", src, re.MULTILINE), \
        "generator still imports reportlab"
    assert not re.search(r"^\s*import\s+weasyprint", src, re.MULTILINE), \
        "generator still tries WeasyPrint first"
    assert "render_pdf" in src and "--print-to-pdf" in src, \
        "HTML render pipeline (Chrome --print-to-pdf) not found in generator"
    assert EM_DASH not in src, "generator source contains an em dash"
    print("PASS: generator is reportlab-free, Chrome is the declared engine")


# ------------------------------------------------------------------ guards
def test_email_guard():
    """gmail address anywhere must hard-fail the render."""
    data = {
        "metadata": {"client_name": "X", "month_label": "May 2026"},
        "exec_summary": "Contact digitalcliq@gmail.com for details.",
    }
    out = _out("mcr_test_guard.pdf")
    r = run(data, out)
    assert r.returncode != 0, "email guard did NOT fire on gmail address"
    assert "gmail" in r.stderr.lower()
    print("PASS: email guard rejects gmail")


def test_missing_metadata():
    data = {"exec_summary": "no metadata"}
    out = _out("mcr_test_nometa.pdf")
    r = run(data, out)
    assert r.returncode != 0, "missing-metadata did not fail"
    print("PASS: missing metadata fails loudly")


def test_bad_metadata_fails_before_chrome():
    """null client_name and blank month_label exit non-zero before Chrome
    ever launches (no generic 'Client' cover)."""
    marker = _out("mcr_test_marker.txt")
    for meta in (_meta(client_name=None), _meta(month_label="  "),
                 _meta(client_name=42)):
        if os.path.exists(marker):
            os.unlink(marker)
        out = _out("mcr_test_badmeta.pdf")
        r = run({"metadata": meta, "exec_summary": "x"}, out,
                MCR_TEST_MARKER=marker)
        assert r.returncode != 0, f"bad metadata {meta} did not fail"
        assert "metadata." in r.stderr, r.stderr
        assert not os.path.exists(marker), "Chrome launched despite bad metadata"
        assert not os.path.exists(out)
    print("PASS: null/blank/non-text client_name or month_label fails before Chrome")


def test_em_dash_warns():
    """An em dash in client copy prints a WARN with its JSON path but the
    build continues (October safety). MCR_STRICT=1 blocks it before Chrome."""
    data = {"metadata": _meta(),
            "exec_summary": f"Traffic rose {EM_DASH} mostly paid search.",
            "wins": {"items": ["Shipped the page."],
                     "challenges": [f"Yelp plan {EM_DASH} service dept."]}}
    out = _out("mcr_test_emdash.pdf")
    r = run(data, out)
    assert r.returncode == 0, f"em dash must warn, not fail: {r.stderr}"
    assert "em dash at $.exec_summary" in r.stderr, r.stderr
    assert "$.wins.challenges[0]" in r.stderr, r.stderr
    assert EM_DASH not in r.stderr, "warning should show [U+2014], not the dash"
    marker = _out("mcr_test_marker2.txt")
    if os.path.exists(marker):
        os.unlink(marker)
    r2 = run(data, out, MCR_STRICT=1, MCR_TEST_MARKER=marker)
    assert r2.returncode != 0, "MCR_STRICT=1 did not block the em dash"
    assert not os.path.exists(marker), "strict fail should come before Chrome"
    # En dash stays legal.
    g = load_gen()
    g._WARNINGS.clear()
    assert g._guard_style({"a": "Jul\u2013Aug"}) == []
    print("PASS: em dash warns with JSON path (exit 0); strict blocks; en dash ok")
    if os.path.exists(out):
        os.unlink(out)


# ---------------------------------------------------------------- insights
def test_string_insights():
    """Plain-string insights, a bare string, and bare-string narrative /
    themes / wins render instead of crashing (or printing one letter per
    line)."""
    g = load_gen()
    html, h = g.insights(["Organic grew 12%", {"text": "Paid held", "type": "success"}, "", None])
    assert "Organic grew 12%" in html and "Paid held" in html and h > 0
    assert html.count('class="callout') == 2, "blank insights must drop out"
    html2, _ = g.insights("Bare string insight")
    assert "Bare string insight" in html2 and html2.count('class="callout') == 1
    with open(SAMPLE, encoding="utf-8") as fh:
        d = json.load(fh)
    d["traffic"]["insights"] = ["Organic grew 12%"]
    d["seo"]["insights"] = "Single bare insight"
    d["reputation"]["themes_positive"] = "fast service"
    d["regional"]["narrative"] = "One narrative sentence."
    d["wins"]["items"] = "One win."
    out = g.build_html(d, LOGO)
    assert "Organic grew 12%" in out and "Single bare insight" in out
    assert "One narrative sentence." in out and "One win." in out
    assert "fast service" in out
    assert '<p class="body">O</p>' not in out, "bare string was iterated per char"
    print("PASS: string / bare-string insights, narrative, themes and wins render")


# ---------------------------------------------------------------- regional
def _stat(**kw):
    s = {"stat": "CA new-vehicle sales H1 (YoY)", "value": "-2.1%",
         "source": "CNCDA California Auto Outlook", "published": "2026-08-15",
         "kind": "actual", "scope": "state",
         "vault_ref": "Market-Read.md#Headline numbers"}
    s.update(kw)
    return s


def test_regional_source_column():
    """(f) Source renders 'source, published' when the source has no date,
    keeps a source that already has one, labels forecasts and segments."""
    g = load_gen()
    rows = g._regional_rows([
        _stat(source="CNCDA", published="2026-07"),
        _stat(source="CNCDA, Q2 2026", published="2026-07-20"),
        _stat(stat="2026 US new-vehicle sales", value="16.0M", kind="forecast",
              source="NADA Market Beat", published="2026-09-04", scope="national"),
        _stat(stat="Avg transaction price, luxury", value="$64,900",
              source="Kelley Blue Book", published="Aug 2026", scope="segment"),
        _stat(source="Cox Automotive", published="Q2 2026"),
        _stat(source="Edmunds", published=None),
        _stat(stat="Avg transaction price (truck)", scope="segment",
              value="16.1M (SAAR)", kind="forecast"),
    ])
    assert rows[0]["Source"] == "CNCDA, Jul 2026", rows[0]
    assert rows[1]["Source"] == "CNCDA, Q2 2026", rows[1]
    assert rows[2]["Value"] == "16.0M (forecast)", rows[2]
    assert rows[2]["Source"] == "NADA Market Beat, Sep 2026", rows[2]
    assert rows[3]["Indicator"] == "Avg transaction price, luxury (segment)", rows[3]
    assert rows[3]["Source"] == "Kelley Blue Book, Aug 2026", rows[3]
    assert rows[4]["Source"] == "Cox Automotive, Q2 2026", rows[4]
    assert rows[5]["Source"] == "Edmunds", rows[5]
    assert rows[6]["Indicator"] == "Avg transaction price (truck, segment)", rows[6]
    assert rows[6]["Value"] == "16.1M (SAAR, forecast)", rows[6]
    html = g.build_html({"metadata": _meta(), "regional": {
        "available": True, "state": "California",
        "stats": [_stat(source="CNCDA", published="2026-07")]}}, LOGO)
    assert "CNCDA, Jul 2026" in html
    assert "Market · Economy" in html and "NADA · Economy" not in html
    print("PASS: Source column prints 'source, published'; forecast/segment labels")


def _vr(g, rg, brand, run_date=datetime.date(2026, 10, 1)):
    g._WARNINGS.clear()
    return g._validate_regional(rg, brand, run_date)


def test_regional_warnings():
    """Plan rank 2 cases (a)-(e), all WARN-only."""
    g = load_gen()
    oct1 = datetime.date(2026, 10, 1)
    # (a) legacy undated Cox / Edmunds stats warn.
    legacy = {"available": True, "stats": [
        {"stat": "Avg transaction price (truck)", "value": "$58,400", "source": "Cox Automotive"},
        {"stat": "CA incentive spend (avg)", "value": "$3,250/unit", "source": "Edmunds"}]}
    w = _vr(g, legacy, "CDJR")
    assert any("stats[0]" in x and "vault_ref or url" in x for x in w), w
    assert any("stats[1]" in x and "published" in x for x in w), w
    # (b) NCBMW August: MyFirstEV advice for a BMW store, no eligibility.
    ncbmw = {"available": True, "stats": [_stat()],
             "narrative": ["California's MyFirstEV rebate adds up to $7,500 "
                           "for first-time EV buyers, a lever for the i4 and iX."]}
    w = _vr(g, ncbmw, "BMW")
    assert any("MyFirstEV" in x or "rebate" in x for x in w), w
    # (c) Same claim with an eligibility object: still warns for BMW, clean
    # for Nissan (NOI).
    elig = {"participants": ["Chevrolet", "Ford", "Hyundai", "Kia", "Nissan"],
            "cap": "$50,000 MSRP", "client_brand_listed": True}
    w = _vr(g, dict(ncbmw, eligibility=elig), "BMW")
    assert any("eligibility" in x for x in w), "BMW must still warn: " + str(w)
    w = _vr(g, dict(ncbmw, eligibility=elig), "Nissan")
    assert w == [], f"Nissan listed with cap should pass: {w}"
    w = _vr(g, dict(ncbmw, eligibility=dict(elig, cap="")), "Nissan")
    assert w, "missing cap must still warn"
    # SKILL.md Agent D record shape (no participants list), as a list.
    rec = [{"program": "MyFirstEV", "client_brand_listed": True,
            "cap": "$50,000 MSRP", "models_checked": ["Leaf", "Ariya"],
            "url": "https://example.com/program", "published": "2026-09-01"}]
    w = _vr(g, dict(ncbmw, eligibility=rec), "Nissan")
    assert w == [], f"SKILL.md eligibility record should pass: {w}"
    w = _vr(g, dict(ncbmw, eligibility=[dict(rec[0], client_brand_listed=False)]), "BMW")
    assert w, "client_brand_listed false must warn"
    w = _vr(g, dict(ncbmw, eligibility=[]), "BMW")
    assert w, "empty eligibility list must warn on a rebate line"
    # (d) An Oct 1 CNCDA H1 stat with a vault_ref passes.
    w = _vr(g, {"available": True, "stats": [_stat(published="H1 2026")]}, "BMW", oct1)
    assert w == [], w
    w = _vr(g, {"available": True, "stats": [_stat()]}, "BMW", oct1)
    assert w == [], w
    # (e) A web stat published 90 days earlier without latest_release warns.
    web = _stat(vault_ref=None, url="https://example.com/report",
                published=(oct1 - datetime.timedelta(days=90)).isoformat())
    w = _vr(g, {"available": True, "stats": [web]}, "BMW", oct1)
    assert any("90 days" in x for x in w), w
    w = _vr(g, {"available": True, "stats": [dict(web, latest_release=True)]}, "BMW", oct1)
    assert w == [], w
    # Forecast wording without kind: forecast warns (house rule).
    w = _vr(g, {"available": True, "stats": [_stat(stat="2026 sales forecast", kind="actual")]}, "BMW")
    assert any("forecast" in x for x in w), w
    w = _vr(g, {"available": True, "stats": [_stat(stat="2026 sales projection", kind=None)]}, "BMW")
    assert any("set kind: forecast" in x for x in w), w
    # CNCDA's actuals publication is named "California Auto Outlook": no warn.
    w = _vr(g, {"available": True, "stats": [_stat(source="CNCDA California Auto Outlook, Jul 20 2026")]}, "BMW")
    assert w == [], w
    print("PASS: regional warnings (a)-(e), eligibility, forecast labeling")


# ------------------------------------------------------------------ Chrome
def _minimal():
    return {"metadata": _meta(), "exec_summary": "Quiet month."}


def test_chrome_timeout():
    out = _out("mcr_test_timeout.pdf")
    if os.path.exists(out):
        os.unlink(out)
    kid_file = _out("mcr_test_kid.txt")
    t0 = time.time()
    r = run(_minimal(), out, chrome_kind="sleep", MCR_CHROME_TIMEOUT=2,
            MCR_TEST_KID=kid_file)
    took = time.time() - t0
    assert r.returncode != 0, "hung Chrome did not fail"
    assert "within 2s" in r.stderr, r.stderr
    assert took < 30, f"timeout did not fire promptly ({took:.0f}s)"
    assert not os.path.exists(out)
    # Chrome's helper child must die with it, not linger as an orphan.
    kid = int(open(kid_file).read())
    os.unlink(kid_file)
    alive = subprocess.run(["ps", "-p", str(kid), "-o", "stat="],
                           capture_output=True, text=True).stdout.strip()
    assert not alive or alive.startswith("Z"), f"Chrome child {kid} survived ({alive})"
    print(f"PASS: hung Chrome and its child are killed at the timeout ({took:.1f}s), clean non-zero exit")


def test_chrome_writes_nothing():
    """Chrome exits 0 without writing: fail, even when last run's PDF sits at
    the output path."""
    out = _out("mcr_test_nothing.pdf")
    with open(out, "wb") as fh:
        fh.write(b"%PDF-1.4 stale from last month\n%%EOF\n")
    before = os.path.getmtime(out)
    r = run(_minimal(), out, chrome_kind="nothing")
    assert r.returncode != 0, "no-PDF Chrome run did not fail"
    assert "wrote no PDF" in r.stderr, r.stderr
    assert os.path.getmtime(out) == before, "stale PDF was touched"
    leftovers = [f for f in os.listdir(os.path.dirname(out)) if f.startswith(".mcr_render_")]
    assert not leftovers, f"temp render files left behind: {leftovers}"
    os.unlink(out)
    print("PASS: Chrome writing nothing fails (stale PDF not passed off as new)")


def test_chrome_error_shows_stderr():
    out = _out("mcr_test_err.pdf")
    r = run(_minimal(), out, chrome_kind="error")
    assert r.returncode != 0
    assert "code 21" in r.stderr and "fake-chrome-boom-7731" in r.stderr, r.stderr
    print("PASS: Chrome error exits non-zero with Chrome's stderr in the message")


def test_chrome_hang_after_complete_pdf():
    """Chrome wrote a complete PDF but never exited: keep it, WARN."""
    out = _out("mcr_test_hang.pdf")
    if os.path.exists(out):
        os.unlink(out)
    r = run(_minimal(), out, chrome_kind="hang_after_write", MCR_CHROME_TIMEOUT=3)
    assert r.returncode == 0, r.stderr
    assert "did not exit within 3s" in r.stderr, r.stderr
    assert os.path.getsize(out) > 0
    os.unlink(out)
    print("PASS: complete PDF from a Chrome that hung on exit is kept, with a WARN")


if __name__ == "__main__":
    test_minimal_omission()
    test_sample_builds()
    test_legacy_regional_still_builds()
    test_email_guard()
    test_missing_metadata()
    test_bad_metadata_fails_before_chrome()
    test_em_dash_warns()
    test_string_insights()
    test_regional_source_column()
    test_regional_warnings()
    test_chrome_timeout()
    test_chrome_writes_nothing()
    test_chrome_error_shows_stderr()
    test_chrome_hang_after_complete_pdf()
    test_no_reportlab()
    print("\nAll generator smoke tests passed.")
