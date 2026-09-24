#!/usr/bin/env python3
"""
morning-coffee validate_skill.py
Tests: JSON schema, CRM file pattern matching, PDF generator CLI, logo path,
       graceful missing data.
"""

import sys
import os
import json
import shutil
import subprocess
import tempfile

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(TESTS_DIR)
SKILLS_ROOT = os.path.dirname(SKILL_DIR)
PROJECT_ROOT = os.path.abspath(os.path.join(SKILLS_ROOT, '..', '..'))
PYTHON = "/usr/bin/python3"

GENERATOR_SCRIPT = os.path.join(SKILL_DIR, "generate_coffee_report.py")
FIXTURE_JSON = os.path.join(TESTS_DIR, "test_inputs", "coffee_report_data_sample.json")

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

# Top-level keys
required_top = ["metadata", "calendar", "crm", "ga4", "google_ads", "news"]
missing_top = [k for k in required_top if k not in data]
test("All required top-level keys present",
     len(missing_top) == 0,
     f"Missing: {missing_top}")

# Metadata
meta_keys = ["report_date", "day_name", "generation_timestamp"]
missing_meta = [k for k in meta_keys if k not in data.get("metadata", {})]
test("Metadata has required fields",
     len(missing_meta) == 0,
     f"Missing: {missing_meta}")

# CRM sub-keys
crm_clients = ["mcpeek", "sterling", "nissan"]
crm = data.get("crm", {})
missing_crm = [c for c in crm_clients if c not in crm]
test("CRM section has all 3 clients",
     len(missing_crm) == 0,
     f"Missing: {missing_crm}")

# Each CRM entry must have "available" field
for client in crm_clients:
    if client in crm:
        test(f"CRM {client} has 'available' field",
             "available" in crm[client],
             f"Keys: {list(crm[client].keys())}")

# GA4 sub-keys
ga4_clients = ["sterling", "nissan", "mcpeek"]
ga4 = data.get("ga4", {})
missing_ga4 = [c for c in ga4_clients if c not in ga4]
test("GA4 section has all 3 clients",
     len(missing_ga4) == 0,
     f"Missing: {missing_ga4}")

# Google Ads sub-keys
ads_clients = ["mcpeek", "nissan"]
ads = data.get("google_ads", {})
missing_ads = [c for c in ads_clients if c not in ads]
test("Google Ads section has 2 clients",
     len(missing_ads) == 0,
     f"Missing: {missing_ads}")

# News categories
news_categories = ["automotive", "ai_tech", "marketing", "economy"]
news = data.get("news", {})
missing_news = [c for c in news_categories if c not in news]
test("News section has all 4 categories",
     len(missing_news) == 0,
     f"Missing: {missing_news}")


# ── Test 2: CRM File Pattern Matching ───────────────────────────────
print("\n2. CRM File Pattern Matching")

PATTERN_MAP = {
    "Sterling BMW Lead Report February.csv": "sterling",
    "sterling_data.csv": "sterling",
    "McPeek CDJR Tekion Export.csv": "mcpeek",
    "Nissan of Irvine VinSolutions.csv": "nissan",
}

for filename, expected_keyword in PATTERN_MAP.items():
    matches = expected_keyword.lower() in filename.lower()
    test(f"'{filename}' matches keyword '{expected_keyword}'", matches)


# ── Test 3: PDF Generator CLI ───────────────────────────────────────
print("\n3. PDF Generator CLI")

logo = find_logo()
if not os.path.exists(GENERATOR_SCRIPT):
    skip("PDF generator", "generate_coffee_report.py not found")
elif logo is None:
    skip("PDF generator", "Logo file not found")
else:
    tmp_dir = tempfile.mkdtemp(prefix="test_dcliq_coffee_")
    tmp_output = os.path.join(tmp_dir, "test_coffee_report.pdf")

    try:
        result = subprocess.run(
            [PYTHON, GENERATOR_SCRIPT, FIXTURE_JSON, tmp_output, logo],
            capture_output=True, text=True, timeout=30,
        )
        test("generate_coffee_report.py exits cleanly",
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
        test("PDF generator completes within timeout", False, "Timed out at 30s")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 4: Logo Path Resolution ────────────────────────────────────
print("\n4. Logo Path Resolution")

logo_found = find_logo()
test("At least one logo path exists",
     logo_found is not None,
     f"Checked: {LOGO_PATHS}")


# ── Test 5: Graceful Missing Data ────────────────────────────────────
print("\n5. Graceful Missing Data")

# CRM entries with available: false should have a "note" field
for client in crm_clients:
    entry = crm.get(client, {})
    if not entry.get("available", True):
        test(f"CRM {client} (unavailable) has 'note' field",
             "note" in entry,
             f"Keys: {list(entry.keys())}")

# Verify the fixture has at least one available and one unavailable CRM
available_count = sum(1 for c in crm_clients if crm.get(c, {}).get("available"))
unavailable_count = sum(1 for c in crm_clients if not crm.get(c, {}).get("available"))
test("Fixture has mix of available/unavailable CRM data",
     available_count >= 1 and unavailable_count >= 1,
     f"Available: {available_count}, Unavailable: {unavailable_count}")


# ── Test 6: validate_data() Function ──────────────────────────────────
print("\n6. validate_data() Function")

sys.path.insert(0, SKILL_DIR)
try:
    from generate_coffee_report import validate_data

    # 6a. Valid fixture passes
    is_valid, errs = validate_data(data)
    test("Valid fixture passes validation", is_valid, f"Errors: {errs[:3]}")

    # 6b. Missing top-level section
    bad = {k: v for k, v in data.items() if k != "tasks"}
    is_valid, errs = validate_data(bad)
    test("Missing 'tasks' section detected",
         not is_valid and any("tasks" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 6c. Non-dict top-level
    is_valid, errs = validate_data("just a string")
    test("Non-dict top-level rejected",
         not is_valid and any("Top-level" in e for e in errs))

    # 6d. Missing CRM client
    bad_ga4 = json.loads(json.dumps(data))
    del bad_ga4["ga4"]["mcpeek"]
    is_valid, errs = validate_data(bad_ga4)
    test("Missing ga4.mcpeek detected",
         not is_valid and any("mcpeek" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 6e. Missing metadata.report_date
    bad_meta = json.loads(json.dumps(data))
    del bad_meta["metadata"]["report_date"]
    is_valid, errs = validate_data(bad_meta)
    test("Missing metadata.report_date detected",
         not is_valid and any("report_date" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 6f. Missing news category
    bad_news = json.loads(json.dumps(data))
    del bad_news["news"]["automotive"]
    is_valid, errs = validate_data(bad_news)
    test("Missing news.automotive detected",
         not is_valid and any("automotive" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 6g. Missing GA4 client
    bad_ga4 = json.loads(json.dumps(data))
    del bad_ga4["ga4"]["sterling"]
    is_valid, errs = validate_data(bad_ga4)
    test("Missing ga4.sterling detected",
         not is_valid and any("sterling" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 6h. Missing CRM 'available' field
    bad_avail = json.loads(json.dumps(data))
    del bad_avail["ga4"]["sterling"]["available"]
    is_valid, errs = validate_data(bad_avail)
    test("Missing ga4.sterling.available detected",
         not is_valid and any("available" in e for e in errs),
         f"Errors: {errs[:2]}")

except ImportError as e:
    skip("validate_data()", f"Could not import: {e}")


# ── Summary ──────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"morning-coffee: {passed} passed, {failed} failed, {skipped} skipped")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
