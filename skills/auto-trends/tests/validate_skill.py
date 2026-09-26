#!/usr/bin/env python3
"""
auto-trends validate_skill.py
Tests: JSON schema, PDF generator (or build_html only), logo path, output
filename pattern, region default, validate_data()/claims check, render_pdf
failure handling, SKILL.md script paths.

Usage:
    python3 tests/validate_skill.py              # full: test 2 renders a PDF via Chrome
    python3 tests/validate_skill.py --build-only # no Chrome: test 2 runs build_html only

--build-only (or env AUTO_TRENDS_BUILD_ONLY=1) is the mode for unattended and
scratch runs: Drew does not want background headless-Chrome renders. The vault
root comes from env DIGITALCLIQ_VAULT_ROOT so the suite also runs from the
installed skills-plugin copy, whose folder is not inside the vault.
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(TESTS_DIR)
PROJECT_ROOT = os.environ.get("DIGITALCLIQ_VAULT_ROOT",
                              "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ")
PYTHON = sys.executable or "/usr/bin/python3"
BUILD_ONLY = ("--build-only" in sys.argv
              or os.environ.get("AUTO_TRENDS_BUILD_ONLY", "").strip() in ("1", "true", "yes"))

GENERATOR_SCRIPT = os.path.join(SKILL_DIR, "generate_trends_report.py")
CLAIMS_SCRIPT = os.path.join(SKILL_DIR, "validate_claims.py")
SKILL_MD = os.path.join(SKILL_DIR, "SKILL.md")
FIXTURE_JSON = os.path.join(TESTS_DIR, "test_inputs", "auto_trends_data_sample.json")
CLAIMS_FIXTURE_JSON = os.path.join(TESTS_DIR, "test_inputs", "auto_trends_data_claims_sample.json")

LOGO_PATH = os.path.join(
    PROJECT_ROOT, "Resources", "brand-assets",
    "digital-cliq-logo-solid-1000px-wide.png",
)
LOGO_PATHS = [LOGO_PATH]  # back-compat for callers iterating

passed = 0
failed = 0
skipped = 0


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  [PASS] {name}")
        passed += 1
    else:
        print(f"  [FAIL] {name}  -- {detail}")
        failed += 1


def skip(name, reason=""):
    global skipped
    print(f"  [SKIP] {name}  -- {reason}")
    skipped += 1


def find_logo():
    for p in LOGO_PATHS:
        if os.path.exists(p):
            return p
    return None


def load_generator():
    spec = importlib.util.spec_from_file_location("gtr_under_test", GENERATOR_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


print(f"auto-trends validate_skill ({'build-only, no Chrome' if BUILD_ONLY else 'full'}; "
      f"vault root {PROJECT_ROOT})")

# ── Test 1: Intermediate JSON Schema ────────────────────────────────
print("\n1. Intermediate JSON Schema")

with open(FIXTURE_JSON) as f:
    data = json.load(f)

required_sections = ["metadata", "executive_summary", "new_vehicle_sales",
                     "used_vehicle_sales", "fixed_ops", "parts",
                     "strategic_outlook", "sources"]
missing = [s for s in required_sections if s not in data]
test("All required sections present",
     len(missing) == 0,
     f"Missing: {missing}")

# Validate metrics arrays
for section_key in ["new_vehicle_sales", "used_vehicle_sales", "fixed_ops", "parts"]:
    section = data.get(section_key, {})
    # Find metrics arrays (could be at top level or nested under "national")
    metrics = section.get("metrics", [])
    if not metrics and "national" in section:
        metrics = section["national"].get("metrics", [])

    if metrics:
        for m in metrics:
            has_required = all(k in m for k in ["label", "value", "trend"])
            test(f"{section_key}: metric has label/value/trend",
                 has_required,
                 f"Keys: {list(m.keys())}")
            if "trend" in m:
                test(f"{section_key}: trend is up/down/flat",
                     m["trend"] in ("up", "down", "flat"),
                     f"Got: {m['trend']}")
            break  # Only need to check first metric per section

# Sources
test("Sources list is non-empty",
     len(data.get("sources", [])) >= 1,
     f"Found {len(data.get('sources', []))} sources")

# Executive summary
exec_sum = data.get("executive_summary", {})
test("Executive summary has overview",
     "overview" in exec_sum and len(exec_sum.get("overview", "")) > 20)
test("Executive summary has key_trends",
     "key_trends" in exec_sum and len(exec_sum.get("key_trends", [])) >= 2)


# ── Test 2: PDF Generator ───────────────────────────────────────────
logo = find_logo()
if BUILD_ONLY:
    print("\n2. PDF Generator (build_html only, no Chrome)")
    try:
        gen = load_generator()
        for fx in (FIXTURE_JSON, CLAIMS_FIXTURE_JSON):
            with open(fx) as f:
                d = json.load(f)
            h = gen.build_html(d)
            tag = os.path.basename(fx)
            n_pages = h.count('class="page')
            test(f"{tag}: build_html emits 9 pages", n_pages == 9, f"pages: {n_pages}")
            test(f"{tag}: fonts embedded via @font-face", h.count("@font-face") >= 6)
            imgs = re.findall(r'src="file://([^"]+)"', h)
            test(f"{tag}: every referenced logo exists",
                 imgs and all(os.path.exists(p) for p in imgs),
                 [p for p in imgs if not os.path.exists(p)][:2])
            test(f"{tag}: strategic page carries both 6- and 12-month lanes",
                 "Near-term moves" in h and "Medium-term positioning" in h)
            # A stat-card source slot holds a real citation or nothing, never
            # the caption cut to fit.
            srcs = re.findall(r'<div class="src">(.*?)</div>', h)
            details = []
            for sk in ("new_vehicle_sales", "used_vehicle_sales", "fixed_ops", "parts"):
                sec = d.get(sk, {})
                for m in (sec.get("metrics", []) + sec.get("national", {}).get("metrics", [])
                          + sec.get("regional", {}).get("metrics", [])):
                    details.append(gen.extract_src(m.get("detail", ""))[0].upper())
            leaked = [s for s in srcs if s and any(c and c.startswith(s.upper()) for c in details)]
            test(f"{tag}: no caption text in a source slot", not leaked, leaked[:3])
    except Exception as e:  # noqa: BLE001
        test("build_html runs", False, f"{type(e).__name__}: {e}")
else:
    print("\n2. PDF Generator CLI (renders via Chrome)")
    if not os.path.exists(GENERATOR_SCRIPT):
        skip("PDF generator", "generate_trends_report.py not found")
    elif logo is None:
        skip("PDF generator", "Logo file not found")
    else:
        tmp_dir = tempfile.mkdtemp(prefix="test_dcliq_trends_")
        tmp_output = os.path.join(tmp_dir, "test_trends_report.pdf")

        try:
            result = subprocess.run(
                [PYTHON, GENERATOR_SCRIPT, CLAIMS_FIXTURE_JSON, tmp_output, logo],
                capture_output=True, text=True, timeout=240,
            )
            test("generate_trends_report.py exits cleanly",
                 result.returncode == 0,
                 f"stderr: {result.stderr[-300:]}")
            test("Output PDF created",
                 os.path.exists(tmp_output),
                 f"Expected: {tmp_output}")
            if os.path.exists(tmp_output):
                size = os.path.getsize(tmp_output)
                test("PDF is non-trivial (>10KB)",
                     size > 10000,
                     f"Size: {size} bytes")
            test("facts manifest written next to the PDF",
                 os.path.exists(os.path.join(tmp_dir, "test_trends_report.facts.json")))
        except subprocess.TimeoutExpired:
            test("PDF generator within timeout", False, "Timed out at 240s")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 3: Logo Path Resolution ────────────────────────────────────
print("\n3. Logo Path Resolution")

test("At least one logo path exists",
     find_logo() is not None,
     f"Checked: {LOGO_PATHS} (set DIGITALCLIQ_VAULT_ROOT if the vault moved)")


# ── Test 4: Output Filename Pattern ──────────────────────────────────
print("\n4. Output Filename Pattern")

today = date.today().strftime("%Y-%m-%d")
expected_name = f"Auto_Trends_Report_{today}.pdf"
test("Filename follows pattern",
     expected_name.startswith("Auto_Trends_Report_") and expected_name.endswith(".pdf"))
test("Filename contains today's date", today in expected_name)

# Check output directory exists
reports_dir = os.path.join(PROJECT_ROOT, "outputs")
test("outputs directory exists",
     os.path.isdir(reports_dir),
     f"Expected: {reports_dir}")


# ── Test 5: Region Default ──────────────────────────────────────────
print("\n5. Region Default")

if not os.path.exists(SKILL_MD):
    skip("Region default", "SKILL.md not found")
else:
    with open(SKILL_MD) as f:
        skill_content = f.read()
    test("Default region is Southern California",
         "southern california" in skill_content.lower(),
         "Default region not documented as Southern California")


# ── Test 6: validate_data() Function ──────────────────────────────────
print("\n6. validate_data() Function")

sys.path.insert(0, SKILL_DIR)
try:
    from generate_trends_report import validate_data
    import validate_claims as vc

    with open(CLAIMS_FIXTURE_JSON) as f:
        cdata = json.load(f)

    # 6a. Valid fixture passes
    is_valid, errs = validate_data(cdata)
    test("Valid (claims) fixture passes validation", is_valid, f"Errors: {errs[:3]}")

    # 6b. Missing required section
    bad = {k: v for k, v in cdata.items() if k != "metadata"}
    is_valid, errs = validate_data(bad)
    test("Missing 'metadata' detected",
         not is_valid and any("metadata" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 6c. Non-dict top-level
    is_valid, errs = validate_data([1, 2, 3])
    test("Non-dict top-level rejected",
         not is_valid and any("Top-level" in e for e in errs))

    # 6d. Empty metadata field
    bad_meta = json.loads(json.dumps(cdata))
    bad_meta["metadata"]["report_title"] = ""
    is_valid, errs = validate_data(bad_meta)
    test("Empty metadata.report_title detected",
         not is_valid and any("report_title" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 6e. Invalid trend value
    bad_trend = json.loads(json.dumps(cdata))
    bad_trend["new_vehicle_sales"]["national"]["metrics"][0]["trend"] = "sideways"
    is_valid, errs = validate_data(bad_trend)
    test("Invalid trend value detected",
         not is_valid and any("trend" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 6f. Missing executive_summary.overview
    bad_exec = json.loads(json.dumps(cdata))
    del bad_exec["executive_summary"]["overview"]
    is_valid, errs = validate_data(bad_exec)
    test("Missing executive_summary.overview detected",
         not is_valid and any("overview" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 6g. Wrong type for sources
    bad_sources = json.loads(json.dumps(cdata))
    bad_sources["sources"] = "not a list"
    is_valid, errs = validate_data(bad_sources)
    test("String sources rejected",
         not is_valid and any("sources" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 6h. Legacy fixture (no source/url/published) reports missing sources
    is_valid, errs = validate_data(data)
    test("Legacy fixture flags missing sources",
         not is_valid and any("no named source" in e for e in errs),
         f"Errors: {errs[:2]}")

    def one(metric, gen="2026-09-05"):
        d = json.loads(json.dumps(cdata))
        d["metadata"]["generation_date"] = gen
        d["executive_summary"].pop("hero", None)
        d["executive_summary"]["headline_stats"] = []
        d["fixed_ops"].pop("hero", None)
        for sk in ("used_vehicle_sales", "fixed_ops", "parts"):
            d[sk]["metrics"] = []
            d[sk].get("regional", {}).pop("metrics", None)
        d["new_vehicle_sales"]["regional"]["metrics"] = []
        d["new_vehicle_sales"]["national"]["metrics"] = [metric]
        return vc.validate_claims(d)

    url = "https://example.com/t"
    # 6i. The 9/5 case: an August 2025 article printed as August 2026 data
    rep = one({"label": "Avg transaction price", "value": "$49,077", "trend": "up",
               "detail": "August (Kelley Blue Book, September 2025).", "source": "KBB",
               "url": url, "published": "2025-09-10", "period": "2026-08", "kind": "actual"})
    test("Year-stale actual ($49,077, published 2025-09-10 for 2026-08) fails",
         any("before its period" in e for e in rep["errors"]), rep["errors"][:2])
    # 6j. A forecast tagged actual, published inside its own period
    rep = one({"label": "Hybrid share", "value": "17.5%", "trend": "up",
               "detail": "August (J.D. Power, August 27 2026).", "source": "J.D. Power",
               "url": url, "published": "2026-08-27", "period": "2026-08", "kind": "actual"})
    test("Actual published before its period ended fails",
         any("ended" in e for e in rep["errors"]), rep["errors"][:2])
    # 6k. YTD actual and an annual figure pass
    rep = one({"label": "CA registrations YTD", "value": "864,848", "trend": "down",
               "detail": "Through June (CNCDA, July 20 2026).", "source": "CNCDA",
               "url": url, "published": "2026-07-20", "period": "2026-YTD", "kind": "actual"})
    test("YTD actual passes", not rep["errors"], rep["errors"][:2])
    rep = one({"label": "Fixed ops gross per store", "value": "$6.1M", "trend": "up",
               "detail": "Full year (NADA Data 2026, April 2026).", "source": "NADA",
               "url": url, "published": "2026-04-15", "period": "2025", "kind": "actual"})
    test("Annual actual passes with no staleness warning",
         not rep["errors"] and not any("days before" in w for w in rep["warnings"]),
         rep["errors"][:2] + rep["warnings"][:2])
    # 6l. Facts manifest built from claims
    facts = vc.facts_manifest(cdata)
    test("Facts manifest covers both heroes and every card, each with a url",
         {"executive_summary.hero", "fixed_ops.hero"} <= {f["id"] for f in facts}
         and all(f["url"].startswith("http") for f in facts)
         and "see row" not in json.dumps(facts), len(facts))

except ImportError as e:
    skip("validate_data()", f"Could not import: {e}")


# ── Test 7: validate_claims.py CLI is warn-only unless --strict ──────
print("\n7. validate_claims.py CLI")

if not os.path.exists(CLAIMS_SCRIPT):
    skip("validate_claims.py CLI", "validate_claims.py not found")
else:
    r = subprocess.run([PYTHON, CLAIMS_SCRIPT, FIXTURE_JSON], capture_output=True, text=True)
    test("Warn-only: exit 0 on a fixture with errors", r.returncode == 0,
         f"rc={r.returncode} {r.stderr[-200:]}")
    test("Warn-only: problems printed to stderr", "ERROR" in r.stderr, r.stderr[:200])
    r = subprocess.run([PYTHON, CLAIMS_SCRIPT, FIXTURE_JSON, "--strict"],
                       capture_output=True, text=True)
    test("--strict: exit 1 on errors", r.returncode == 1, f"rc={r.returncode}")
    r = subprocess.run([PYTHON, CLAIMS_SCRIPT, CLAIMS_FIXTURE_JSON, "--strict"],
                       capture_output=True, text=True)
    test("--strict: exit 0 on the clean claims fixture", r.returncode == 0,
         f"rc={r.returncode} {r.stderr[-300:]}")


# ── Test 8: render_pdf failure handling (no Chrome launched) ─────────
print("\n8. render_pdf failure handling")

try:
    gen8 = load_generator()
    real_run = subprocess.run

    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd=a[0], timeout=k.get("timeout"),
                                        stderr=b"hung on virtual time budget")

    seen = {}

    def _record_and_timeout(*a, **k):
        seen["timeout"] = k.get("timeout")
        return _timeout(*a, **k)

    gen8.subprocess.run = _record_and_timeout
    saved_engine = os.environ.pop("AUTO_TRENDS_ENGINE", None)
    try:
        try:
            gen8.render_pdf("/nonexistent.html", os.path.join(tempfile.gettempdir(), "x.pdf"))
            test("Chrome timeout raises RuntimeError", False, "no exception")
        except RuntimeError as e:
            test("Chrome timeout raises RuntimeError naming the engine and stderr",
                 "engine: chrome" in str(e) and "hung on virtual time budget" in str(e), str(e))
        test("Chrome call carries a timeout", seen.get("timeout") == gen8.CHROME_TIMEOUT,
             seen.get("timeout"))
    finally:
        gen8.subprocess.run = real_run
        if saved_engine is not None:
            os.environ["AUTO_TRENDS_ENGINE"] = saved_engine
except Exception as e:  # noqa: BLE001
    test("render_pdf failure handling", False, f"{type(e).__name__}: {e}")


# ── Test 9: SKILL.md script paths resolve ────────────────────────────
print("\n9. SKILL.md script paths")

if not os.path.exists(SKILL_MD):
    skip("SKILL.md paths", "SKILL.md not found")
else:
    with open(SKILL_MD) as f:
        md = f.read()
    refs = sorted(set(re.findall(r'\$\{CLAUDE_SKILL_DIR\}/([\w./-]+)', md)))
    test("SKILL.md references its scripts via ${CLAUDE_SKILL_DIR}", bool(refs))
    missing_refs = [r for r in refs if not os.path.exists(os.path.join(SKILL_DIR, r))]
    test("Every ${CLAUDE_SKILL_DIR}/ path exists in the skill folder", not missing_refs,
         missing_refs)
    test("No dead vault .claude/skills/auto-trends path",
         ".claude/skills/auto-trends" not in md)
    test("No bare $SKILL_DIR", not re.search(r"\$SKILL_DIR\b|\$\{SKILL_DIR\}", md))
    pf = [ln for ln in md.splitlines() if "post_flight.py" in ln and "python3" in ln]
    test("post_flight command double-quotes the vault path",
         pf and all('"/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/post_flight.py"'
                    in ln for ln in pf), pf)
    test("No em dashes in SKILL.md", "\u2014" not in md)


# ── Summary ──────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"auto-trends: {passed} passed, {failed} failed, {skipped} skipped")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
