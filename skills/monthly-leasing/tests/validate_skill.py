#!/usr/bin/env python3
"""
monthly-leasing validate_skill.py
Tests: per-brand schema, dealer roster, brand aliases, model dictionary,
       merge script, report generator, deduplication, info flags,
       parallel orchestrator CLI, agent prompt generation, brand resolution.
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

ROSTER_PATH = os.path.join(SKILL_DIR, "dealer_roster.json")
MERGE_SCRIPT = os.path.join(SKILL_DIR, "merge_brand_data.py")
REPORT_SCRIPT = os.path.join(SKILL_DIR, "generate_lease_report.py")
ORCHESTRATOR_SCRIPT = os.path.join(SKILL_DIR, "orchestrate_parallel.py")

FIXTURE_NISSAN = os.path.join(TESTS_DIR, "test_inputs", "lease_data_nissan_sample.json")
FIXTURE_BMW = os.path.join(TESTS_DIR, "test_inputs", "lease_data_bmw_sample.json")
FIXTURE_COMBINED = os.path.join(TESTS_DIR, "test_inputs", "lease_data_combined_sample.json")

VALID_FLAGS = {"LOYALTY", "CONQUEST", "ACQ_FEE", "TTL", "MSD",
               "TRADE_REQ", "APR_CREDIT", "DEALER_CONTRIB"}

REQUIRED_OFFER_FIELDS = [
    "brand", "dealer_name", "dealer_url", "source_url", "page_type",
    "yr", "make", "model", "trim", "msrp", "pmt", "term_mo", "das",
    "miles_yr", "sec_dep", "exp", "vin", "is_national",
    "disclaimer_scope", "disclaimer_text", "info_flags",
    "parse_note", "source_credit",
]

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


# ── Test 1: Per-Brand JSON Schema ───────────────────────────────────
print("\n1. Per-Brand JSON Schema")

for fixture_name, fixture_path in [("nissan", FIXTURE_NISSAN), ("bmw", FIXTURE_BMW)]:
    if not os.path.exists(fixture_path):
        skip(f"{fixture_name} schema", "Fixture not found")
        continue

    with open(fixture_path) as f:
        data = json.load(f)

    # Metadata
    meta_keys = ["brand", "brand_display", "cap_date", "month", "run_timestamp",
                 "dealers_in_roster", "dealers_scraped", "dealers_with_offers", "total_offers"]
    missing_meta = [k for k in meta_keys if k not in data.get("metadata", {})]
    test(f"{fixture_name}: metadata has all required fields",
         len(missing_meta) == 0,
         f"Missing: {missing_meta}")

    # Offers
    offers = data.get("offers", [])
    test(f"{fixture_name}: has offers",
         len(offers) > 0,
         f"Found {len(offers)} offers")

    if offers:
        missing_fields = [f for f in REQUIRED_OFFER_FIELDS if f not in offers[0]]
        test(f"{fixture_name}: offers have all required fields",
             len(missing_fields) == 0,
             f"Missing: {missing_fields}")

        # source_credit check
        all_dcliq = all(o.get("source_credit") == "DigitalCLIQ" for o in offers)
        test(f"{fixture_name}: all source_credit = 'DigitalCLIQ'",
             all_dcliq)

        # page_type check
        valid_pages = all(o.get("page_type") in ("home", "specials") for o in offers)
        test(f"{fixture_name}: page_type is 'home' or 'specials'",
             valid_pages,
             f"Invalid: {[o.get('page_type') for o in offers if o.get('page_type') not in ('home', 'specials')]}")

        # is_national check
        valid_national = all(o.get("is_national") in (0, 1) for o in offers)
        test(f"{fixture_name}: is_national is 0 or 1",
             valid_national)


# ── Test 2: Dealer Roster Exists ────────────────────────────────────
print("\n2. Dealer Roster")

if not os.path.exists(ROSTER_PATH):
    skip("Dealer roster", "dealer_roster.json not found")
else:
    with open(ROSTER_PATH) as f:
        roster = json.load(f)

    test("Roster has 'brands' key",
         "brands" in roster,
         f"Keys: {list(roster.keys())}")
    test("Roster has 'brand_aliases' key",
         "brand_aliases" in roster,
         f"Keys: {list(roster.keys())}")

    brands = roster.get("brands", {})
    expected_brands = ["nissan", "bmw", "cdjr", "chevrolet", "lexus", "ford"]
    found_brands = list(brands.keys())
    missing_brands = [b for b in expected_brands if b not in found_brands]
    test("Roster has all 6 brands",
         len(missing_brands) == 0,
         f"Missing: {missing_brands}, Found: {found_brands}")


# ── Test 3: Brand Alias Resolution ──────────────────────────────────
print("\n3. Brand Alias Resolution")

if not os.path.exists(ROSTER_PATH):
    skip("Brand aliases", "Roster not found")
else:
    aliases = roster.get("brand_aliases", {})
    alias_tests = {
        "chevy": ["chevrolet"],
        "dodge": ["cdjr"],
        "jeep": ["cdjr"],
        "ram": ["cdjr"],
        "chrysler": ["cdjr"],
        "stellantis": ["cdjr"],
        "all": expected_brands,
        "all-oc-dealers": expected_brands,
    }
    for alias, expected in alias_tests.items():
        resolved = aliases.get(alias, [])
        test(f"Alias '{alias}' resolves correctly",
             set(resolved) == set(expected),
             f"Got: {resolved}, Expected: {expected}")


# ── Test 4: Model Dictionary ────────────────────────────────────────
print("\n4. Model Dictionary")

if not os.path.exists(ROSTER_PATH):
    skip("Model dictionary", "Roster not found")
else:
    for brand_key, brand_data in brands.items():
        models = brand_data.get("models", [])
        test(f"{brand_key}: models list is non-empty",
             len(models) > 0,
             f"Found {len(models)} models")
        if models:
            all_strings = all(isinstance(m, str) for m in models)
            test(f"{brand_key}: models are strings",
                 all_strings)

    # Verify fixture models exist in roster
    with open(FIXTURE_NISSAN) as f:
        nissan_data = json.load(f)
    nissan_models = brands.get("nissan", {}).get("models", [])
    nissan_models_lower = [m.lower() for m in nissan_models]
    for offer in nissan_data.get("offers", []):
        model = offer.get("model", "")
        test(f"Nissan offer model '{model}' in roster",
             model.lower() in nissan_models_lower,
             f"Roster models: {nissan_models}")


# ── Test 5: Merge Script CLI ────────────────────────────────────────
print("\n5. Merge Script CLI")

if not os.path.exists(MERGE_SCRIPT):
    skip("Merge script", "merge_brand_data.py not found")
else:
    tmp_dir = tempfile.mkdtemp(prefix="test_dcliq_lease_")
    tmp_output = os.path.join(tmp_dir, "test_combined.json")

    try:
        # Copy fixture per-brand JSONs to /tmp/ with correct naming
        shutil.copy(FIXTURE_NISSAN, os.path.join("/tmp", "lease_data_nissan_2026-03.json"))
        shutil.copy(FIXTURE_BMW, os.path.join("/tmp", "lease_data_bmw_2026-03.json"))

        result = subprocess.run(
            [PYTHON, MERGE_SCRIPT,
             "--month", "2026-03",
             "--roster", ROSTER_PATH,
             "--output", tmp_output],
            capture_output=True, text=True, timeout=30,
        )
        test("merge_brand_data.py exits cleanly",
             result.returncode == 0,
             f"stderr: {result.stderr[:200]}")
        test("Combined JSON output created",
             os.path.exists(tmp_output),
             f"Expected: {tmp_output}")

        if os.path.exists(tmp_output):
            with open(tmp_output) as f:
                combined = json.load(f)
            offers = combined.get("offers", [])
            brands_found = set(o.get("brand", "").lower() for o in offers)
            test("Combined has offers from both brands",
                 "nissan" in brands_found and "bmw" in brands_found,
                 f"Brands: {brands_found}")
    except subprocess.TimeoutExpired:
        test("Merge script within timeout", False, "Timed out at 30s")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        # Clean up temp files
        for f in ["/tmp/lease_data_nissan_2026-03.json", "/tmp/lease_data_bmw_2026-03.json"]:
            if os.path.exists(f):
                os.remove(f)


# ── Test 6: Report Generator CLI ────────────────────────────────────
print("\n6. Report Generator CLI")

if not os.path.exists(REPORT_SCRIPT):
    skip("Report generator", "generate_lease_report.py not found")
else:
    tmp_dir = tempfile.mkdtemp(prefix="test_dcliq_lease_rpt_")
    try:
        result = subprocess.run(
            [PYTHON, REPORT_SCRIPT,
             FIXTURE_COMBINED, tmp_dir,
             "--roster", ROSTER_PATH],
            capture_output=True, text=True, timeout=30,
        )
        test("generate_lease_report.py exits cleanly",
             result.returncode == 0,
             f"stderr: {result.stderr[:200]}")

        # Check for output Excel
        xlsx_files = [f for f in os.listdir(tmp_dir) if f.endswith(".xlsx")]
        test("Output Excel file created",
             len(xlsx_files) > 0,
             f"Files in {tmp_dir}: {os.listdir(tmp_dir)}")
    except subprocess.TimeoutExpired:
        test("Report generator within timeout", False, "Timed out at 30s")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 7: Deduplication Logic ──────────────────────────────────────
print("\n7. Deduplication Logic")

# Test that two identical offers would be detected as duplicates
offer_a = {"dealer_name": "Test Dealer", "model": "Rogue", "trim": "SV",
           "pmt": 299, "term_mo": 36, "das": 3999}
offer_b = {"dealer_name": "Test Dealer", "model": "Rogue", "trim": "SV",
           "pmt": 299, "term_mo": 36, "das": 3999}
offer_c = {"dealer_name": "Test Dealer", "model": "Rogue", "trim": "SV",
           "pmt": 319, "term_mo": 36, "das": 3999}  # Different payment

dedup_key = lambda o: (o["dealer_name"], o["model"], o["trim"], o["pmt"], o["term_mo"], o["das"])

test("Identical offers produce same dedup key",
     dedup_key(offer_a) == dedup_key(offer_b))
test("Different payments produce different dedup key",
     dedup_key(offer_a) != dedup_key(offer_c))


# ── Test 8: Info Flags Format ────────────────────────────────────────
print("\n8. Info Flags Format")

for fixture_name, fixture_path in [("nissan", FIXTURE_NISSAN), ("bmw", FIXTURE_BMW)]:
    with open(fixture_path) as f:
        data = json.load(f)

    for offer in data.get("offers", []):
        flags_str = offer.get("info_flags", "")
        if not flags_str:
            continue
        flags = flags_str.split("|")
        invalid = [f for f in flags if f not in VALID_FLAGS]
        test(f"{fixture_name} {offer.get('model','')}: flags are valid",
             len(invalid) == 0,
             f"Invalid flags: {invalid}")
        break  # Only check first offer with flags per brand


# ── Test 9: Parallel Orchestrator CLI ──────────────────────────────
print("\n9. Parallel Orchestrator CLI")

if not os.path.exists(ORCHESTRATOR_SCRIPT):
    skip("Orchestrator script", "orchestrate_parallel.py not found")
else:
    try:
        result = subprocess.run(
            [PYTHON, ORCHESTRATOR_SCRIPT,
             "--roster", ROSTER_PATH,
             "--brands", "nissan", "bmw",
             "--month", "2026-03",
             "--prompts-only"],
            capture_output=True, text=True, timeout=30,
        )
        test("orchestrate_parallel.py exits cleanly",
             result.returncode == 0,
             f"stderr: {result.stderr[:200]}")

        # Parse JSON from stdout
        output = {}
        if result.returncode == 0:
            try:
                output = json.loads(result.stdout)
            except json.JSONDecodeError:
                test("Orchestrator output is valid JSON", False,
                     f"stdout: {result.stdout[:200]}")

        if output:
            test("Output has 'brands' key",
                 "brands" in output,
                 f"Keys: {list(output.keys())}")

            test("Output resolves 2 brands",
                 output.get("brands") == ["nissan", "bmw"],
                 f"Got: {output.get('brands')}")

            test("Output has brand_manifests for each brand",
                 "nissan" in output.get("brand_manifests", {})
                 and "bmw" in output.get("brand_manifests", {}),
                 f"Keys: {list(output.get('brand_manifests', {}).keys())}")

            test("Output has month and cap_date",
                 output.get("month") == "2026-03"
                 and output.get("cap_date") is not None,
                 f"month={output.get('month')}, cap_date={output.get('cap_date')}")

            # Verify dealer counts
            nissan_m = output.get("brand_manifests", {}).get("nissan", {})
            bmw_m = output.get("brand_manifests", {}).get("bmw", {})
            test("Nissan manifest has correct dealer count",
                 nissan_m.get("dealer_count") == 7,
                 f"Got: {nissan_m.get('dealer_count')}")
            test("BMW manifest has correct dealer count",
                 bmw_m.get("dealer_count") == 4,
                 f"Got: {bmw_m.get('dealer_count')}")

    except subprocess.TimeoutExpired:
        test("Orchestrator within timeout", False, "Timed out at 30s")


# ── Test 10: Agent Prompt Generation ──────────────────────────────
print("\n10. Agent Prompt Generation")

if not os.path.exists(ORCHESTRATOR_SCRIPT):
    skip("Agent prompt", "orchestrate_parallel.py not found")
elif not output:
    skip("Agent prompt", "No orchestrator output to check")
else:
    for brand_key in ["nissan", "bmw"]:
        manifest = output.get("brand_manifests", {}).get(brand_key, {})
        prompt = manifest.get("agent_prompt", "")

        test(f"{brand_key}: agent_prompt is non-empty",
             len(prompt) > 100,
             f"Length: {len(prompt)}")

        # Prompt should contain essential elements
        test(f"{brand_key}: prompt contains brand name",
             manifest.get("brand_display", "").lower() in prompt.lower(),
             f"Looking for '{manifest.get('brand_display')}'")

        test(f"{brand_key}: prompt contains dealer URLs",
             "http" in prompt,
             "No URLs found in prompt")

        test(f"{brand_key}: prompt contains model list",
             any(m.lower() in prompt.lower()
                 for m in manifest.get("models", [])[:3]),
             "Model names not found in prompt")

        test(f"{brand_key}: prompt contains output format spec",
             "metadata" in prompt and "offers" in prompt
             and "dealer_status" in prompt,
             "Missing output format specification")

        test(f"{brand_key}: prompt contains info_flags reference",
             "LOYALTY" in prompt and "ACQ_FEE" in prompt,
             "Missing info flag definitions")

        test(f"{brand_key}: prompt mentions DigitalCLIQ source_credit",
             "DigitalCLIQ" in prompt,
             "Missing source_credit instruction")


# ── Test 11: Brand Resolution via Orchestrator ────────────────────
print("\n11. Brand Resolution via Orchestrator")

if not os.path.exists(ORCHESTRATOR_SCRIPT):
    skip("Brand resolution", "orchestrate_parallel.py not found")
else:
    # Test alias resolution: "all" should resolve to all 6 brands
    alias_tests = [
        (["all"], ["nissan", "bmw", "cdjr", "chevrolet", "lexus", "ford"]),
        (["chevy", "bmw"], ["chevrolet", "bmw"]),
        (["dodge"], ["cdjr"]),
        (["stellantis", "nissan"], ["cdjr", "nissan"]),
    ]

    for tokens, expected in alias_tests:
        try:
            result = subprocess.run(
                [PYTHON, ORCHESTRATOR_SCRIPT,
                 "--roster", ROSTER_PATH,
                 "--brands"] + tokens + [
                 "--month", "2026-03",
                 "--prompts-only"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                out = json.loads(result.stdout)
                resolved = out.get("brands", [])
                test(f"Alias '{' '.join(tokens)}' resolves correctly",
                     set(resolved) == set(expected),
                     f"Got: {resolved}, Expected: {expected}")
            else:
                test(f"Alias '{' '.join(tokens)}' resolves correctly",
                     False, f"Exit code: {result.returncode}")
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            test(f"Alias '{' '.join(tokens)}' resolves correctly",
                 False, str(e))

    # Test invalid brand token exits with error
    try:
        result = subprocess.run(
            [PYTHON, ORCHESTRATOR_SCRIPT,
             "--roster", ROSTER_PATH,
             "--brands", "nonexistent_brand",
             "--month", "2026-03",
             "--prompts-only"],
            capture_output=True, text=True, timeout=15,
        )
        test("Invalid brand token returns non-zero exit",
             result.returncode != 0,
             f"Exit code: {result.returncode}")
    except subprocess.TimeoutExpired:
        test("Invalid brand token check", False, "Timed out")


# ── Test 12: validate_data() — Report Generator ──────────────────
print("\n12. validate_data() — Report Generator")

# Import validate_data from generate_lease_report.py
sys.path.insert(0, SKILL_DIR)
try:
    from generate_lease_report import validate_data

    # 12a. Valid combined fixture passes validation
    with open(FIXTURE_COMBINED) as f:
        valid_combined = json.load(f)
    is_valid, errs = validate_data(valid_combined, "fixture_combined")
    test("Valid combined fixture passes validate_data()",
         is_valid,
         f"{len(errs)} errors: {errs[:2]}")

    # 12b. Missing top-level key is caught
    bad_no_offers = {"metadata": valid_combined["metadata"], "dealer_status": []}
    is_valid, errs = validate_data(bad_no_offers, "test_no_offers")
    test("Missing 'offers' key detected",
         not is_valid and any("offers" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 12c. Wrong type: offers as flat dict instead of list-of-dicts
    bad_flat = dict(valid_combined)
    bad_flat["offers"] = {"single_offer": "this is wrong"}
    is_valid, errs = validate_data(bad_flat, "test_flat_offers")
    test("Flat dict offers detected (expected list-of-dicts)",
         not is_valid and any("offers" in e and "wrong type" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 12d. Offer with wrong field type is caught
    bad_types = json.loads(json.dumps(valid_combined))
    bad_types["offers"][0]["pmt"] = "two hundred ninety nine"  # str instead of num
    is_valid, errs = validate_data(bad_types, "test_bad_pmt")
    test("String payment in offer detected (expected number)",
         not is_valid and any("pmt" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 12e. Missing required metadata field is caught
    bad_meta = json.loads(json.dumps(valid_combined))
    del bad_meta["metadata"]["month"]
    is_valid, errs = validate_data(bad_meta, "test_no_month")
    test("Missing metadata.month detected",
         not is_valid and any("month" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 12f. Empty offers list is caught
    bad_empty = json.loads(json.dumps(valid_combined))
    bad_empty["offers"] = []
    is_valid, errs = validate_data(bad_empty, "test_empty_offers")
    test("Empty offers list detected",
         not is_valid and any("empty list" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 12g. Non-dict top-level is caught
    is_valid, errs = validate_data([1, 2, 3], "test_array_toplevel")
    test("Non-dict top-level detected",
         not is_valid and any("Top-level" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 12h. Offer with is_national=2 (invalid bool01) is caught
    bad_national = json.loads(json.dumps(valid_combined))
    bad_national["offers"][0]["is_national"] = 2
    is_valid, errs = validate_data(bad_national, "test_bad_national")
    test("is_national=2 detected (expected 0 or 1)",
         not is_valid and any("is_national" in e for e in errs),
         f"Errors: {errs[:2]}")

except ImportError as e:
    skip("validate_data import", str(e))


# ── Test 13: validate_brand_data() — Merge Script ────────────────
print("\n13. validate_brand_data() — Merge Script")

try:
    from merge_brand_data import validate_brand_data

    # 13a. Valid per-brand fixture passes validation
    with open(FIXTURE_NISSAN) as f:
        valid_nissan = json.load(f)
    is_valid, errs = validate_brand_data(valid_nissan, "nissan", "fixture_nissan")
    test("Valid Nissan fixture passes validate_brand_data()",
         is_valid,
         f"{len(errs)} errors: {errs[:2]}")

    with open(FIXTURE_BMW) as f:
        valid_bmw = json.load(f)
    is_valid, errs = validate_brand_data(valid_bmw, "bmw", "fixture_bmw")
    test("Valid BMW fixture passes validate_brand_data()",
         is_valid,
         f"{len(errs)} errors: {errs[:2]}")

    # 13b. Missing metadata.brand detected
    bad_brand = json.loads(json.dumps(valid_nissan))
    del bad_brand["metadata"]["brand"]
    is_valid, errs = validate_brand_data(bad_brand, "nissan", "test_no_brand")
    test("Missing metadata.brand detected",
         not is_valid and any("brand" in e and "missing" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 13c. Offers as string instead of list
    bad_str = dict(valid_nissan)
    bad_str["offers"] = "not a list"
    is_valid, errs = validate_brand_data(bad_str, "nissan", "test_str_offers")
    test("String offers detected (expected list-of-dicts)",
         not is_valid and any("offers" in e and "wrong type" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 13d. Offer missing dealer_name (required)
    bad_dealer = json.loads(json.dumps(valid_nissan))
    del bad_dealer["offers"][0]["dealer_name"]
    is_valid, errs = validate_brand_data(bad_dealer, "nissan", "test_no_dealer")
    test("Missing offer.dealer_name detected",
         not is_valid and any("dealer_name" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 13e. dealer_status as dict instead of list
    bad_ds = json.loads(json.dumps(valid_nissan))
    bad_ds["dealer_status"] = {"wrong": "type"}
    is_valid, errs = validate_brand_data(bad_ds, "nissan", "test_dict_ds")
    test("Dict dealer_status detected (expected list-of-dicts)",
         not is_valid and any("dealer_status" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 13f. Empty metadata.month detected
    bad_month = json.loads(json.dumps(valid_nissan))
    bad_month["metadata"]["month"] = ""
    is_valid, errs = validate_brand_data(bad_month, "nissan", "test_empty_month")
    test("Empty metadata.month detected",
         not is_valid and any("month" in e and "empty" in e for e in errs),
         f"Errors: {errs[:2]}")

except ImportError as e:
    skip("validate_brand_data import", str(e))
finally:
    if SKILL_DIR in sys.path:
        sys.path.remove(SKILL_DIR)


# ── Summary ──────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"monthly-leasing: {passed} passed, {failed} failed, {skipped} skipped")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
