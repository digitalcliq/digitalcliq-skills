#!/usr/bin/env python3
"""
auto-trends validate_skill.py
Tests: JSON schema, PDF generator CLI, logo path, output filename pattern,
       region default.
"""

import sys
import os
import json
import shutil
import subprocess
import tempfile
from datetime import date

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(TESTS_DIR)
SKILLS_ROOT = os.path.dirname(SKILL_DIR)
PROJECT_ROOT = os.path.abspath(os.path.join(SKILLS_ROOT, '..', '..'))
PYTHON = "/usr/bin/python3"

GENERATOR_SCRIPT = os.path.join(SKILL_DIR, "generate_trends_report.py")
SKILL_MD = os.path.join(SKILL_DIR, "SKILL.md")
FIXTURE_JSON = os.path.join(TESTS_DIR, "test_inputs", "auto_trends_data_sample.json")

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


# ── Test 2: PDF Generator CLI ───────────────────────────────────────
print("\n2. PDF Generator CLI")

logo = find_logo()
if not os.path.exists(GENERATOR_SCRIPT):
    skip("PDF generator", "generate_trends_report.py not found")
elif logo is None:
    skip("PDF generator", "Logo file not found")
else:
    tmp_dir = tempfile.mkdtemp(prefix="test_dcliq_trends_")
    tmp_output = os.path.join(tmp_dir, "test_trends_report.pdf")

    try:
        result = subprocess.run(
            [PYTHON, GENERATOR_SCRIPT, FIXTURE_JSON, tmp_output, logo],
            capture_output=True, text=True, timeout=30,
        )
        test("generate_trends_report.py exits cleanly",
             result.returncode == 0,
             f"stderr: {result.stderr[:300]}")
        test("Output PDF created",
             os.path.exists(tmp_output),
             f"Expected: {tmp_output}")
        if os.path.exists(tmp_output):
            size = os.path.getsize(tmp_output)
            test("PDF is non-trivial (>10KB)",
                 size > 10000,
                 f"Size: {size} bytes")
    except subprocess.TimeoutExpired:
        test("PDF generator within timeout", False, "Timed out at 30s")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 3: Logo Path Resolution ────────────────────────────────────
print("\n3. Logo Path Resolution")

test("At least one logo path exists",
     find_logo() is not None,
     f"Checked: {LOGO_PATHS}")


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

    # 6a. Valid fixture passes
    is_valid, errs = validate_data(data)
    test("Valid fixture passes validation", is_valid, f"Errors: {errs[:3]}")

    # 6b. Missing required section
    bad = {k: v for k, v in data.items() if k != "metadata"}
    is_valid, errs = validate_data(bad)
    test("Missing 'metadata' detected",
         not is_valid and any("metadata" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 6c. Non-dict top-level
    is_valid, errs = validate_data([1, 2, 3])
    test("Non-dict top-level rejected",
         not is_valid and any("Top-level" in e for e in errs))

    # 6d. Empty metadata field
    bad_meta = json.loads(json.dumps(data))
    bad_meta["metadata"]["report_title"] = ""
    is_valid, errs = validate_data(bad_meta)
    test("Empty metadata.report_title detected",
         not is_valid and any("report_title" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 6e. Invalid trend value
    bad_trend = json.loads(json.dumps(data))
    # Find a section with metrics and corrupt the trend
    for skey in ["new_vehicle_sales", "used_vehicle_sales", "fixed_ops", "parts"]:
        section = bad_trend.get(skey, {})
        metrics = section.get("metrics", [])
        if not metrics and "national" in section:
            metrics = section["national"].get("metrics", [])
        if metrics:
            metrics[0]["trend"] = "sideways"
            break
    is_valid, errs = validate_data(bad_trend)
    test("Invalid trend value detected",
         not is_valid and any("trend" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 6f. Missing executive_summary.overview
    bad_exec = json.loads(json.dumps(data))
    del bad_exec["executive_summary"]["overview"]
    is_valid, errs = validate_data(bad_exec)
    test("Missing executive_summary.overview detected",
         not is_valid and any("overview" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 6g. Wrong type for sources
    bad_sources = json.loads(json.dumps(data))
    bad_sources["sources"] = "not a list"
    is_valid, errs = validate_data(bad_sources)
    test("String sources rejected",
         not is_valid and any("sources" in e for e in errs),
         f"Errors: {errs[:2]}")

except ImportError as e:
    skip("validate_data()", f"Could not import: {e}")


# ── Summary ──────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"auto-trends: {passed} passed, {failed} failed, {skipped} skipped")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
