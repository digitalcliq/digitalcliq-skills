#!/usr/bin/env python3
"""
dealership-forecast validate_skill.py
Tests: CRM detection, parser output schema, vendor rollup, artifact detection,
       tier assignment, NADA projection, detect CLI, build CLI.
"""

import sys
import os
import subprocess
import json
import tempfile
import shutil

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(TESTS_DIR)
SKILLS_ROOT = os.path.dirname(SKILL_DIR)
PROJECT_ROOT = os.path.abspath(os.path.join(SKILLS_ROOT, '..', '..'))
PYTHON = "/usr/bin/python3"

FORECAST_SCRIPT = os.path.join(SKILL_DIR, "dealership_forecast.py")
FIXTURES_DIR = os.path.join(TESTS_DIR, "test_inputs")

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


# Add skill dir to path for imports
sys.path.insert(0, SKILL_DIR)

try:
    import pandas as pd
    from dealership_forecast import (
        detect_crm, parse_momentum, parse_vinsolutions, parse_tekion,
        rollup_vendor, detect_artifacts, assign_tier, NADA, VENDOR_RULES,
        ARTIFACT_KW, CPS_TIERS, CR_TIERS, pnum,
    )
    CAN_IMPORT = True
except ImportError as e:
    CAN_IMPORT = False
    IMPORT_ERR = str(e)


# ── Test 1: CRM Detection ───────────────────────────────────────────
print("\n1. CRM Detection")

if not CAN_IMPORT:
    skip("CRM detection", f"Cannot import: {IMPORT_ERR}")
else:
    crm_fixtures = {
        "momentum_sample.csv": "momentum",
        "vinsolutions_sample.csv": "vinsolutions",
        "tekion_sample.csv": "tekion",
        "dealersocket_sample.csv": "dealersocket",
    }
    for fname, expected_crm in crm_fixtures.items():
        fpath = os.path.join(FIXTURES_DIR, fname)
        if not os.path.exists(fpath):
            skip(f"detect_crm({fname})", "Fixture not found")
            continue
        result = detect_crm(fpath)
        test(f"detect_crm({fname}) = {expected_crm}",
             result["crm"] == expected_crm,
             f"Got: {result['crm']}")


# ── Test 2: Parser Output Schema ────────────────────────────────────
print("\n2. Parser Output Schema")

REQUIRED_FIELDS = [
    "source_name", "good_leads", "total_leads", "bad_leads",
    "duplicate_leads", "sales", "sales_metric", "contact_count",
    "contact_pct", "appt_set", "appt_shown", "cost",
    "gross_profit", "avg_gross",
]

if not CAN_IMPORT:
    skip("Parser output schema", f"Cannot import: {IMPORT_ERR}")
else:
    parsers = {
        "momentum": (parse_momentum, "momentum_sample.csv"),
        "vinsolutions": (parse_vinsolutions, "vinsolutions_sample.csv"),
        "tekion": (parse_tekion, "tekion_sample.csv"),
    }
    for crm_name, (parser_fn, fixture) in parsers.items():
        fpath = os.path.join(FIXTURES_DIR, fixture)
        if not os.path.exists(fpath):
            skip(f"parse_{crm_name} schema", "Fixture not found")
            continue
        rows = parser_fn(fpath)
        test(f"parse_{crm_name} returns list",
             isinstance(rows, list) and len(rows) > 0,
             f"Got: {type(rows).__name__}, len={len(rows) if isinstance(rows, list) else 'N/A'}")
        if rows:
            missing = [f for f in REQUIRED_FIELDS if f not in rows[0]]
            test(f"parse_{crm_name} has all required fields",
                 len(missing) == 0,
                 f"Missing: {missing}")


# ── Test 3: Vendor Rollup ────────────────────────────────────────────
print("\n3. Vendor Rollup")

if not CAN_IMPORT:
    skip("Vendor rollup", f"Cannot import: {IMPORT_ERR}")
else:
    rollup_cases = [
        ("AutoTrader.com", "AutoTrader"),
        ("AutoTrader.com - Phone Lead", "AutoTrader"),
        ("CarGurus", "CarGurus"),
        ("Cars.com Phone", "Cars.com"),
        ("Dealer Website", "Dealer Website"),
        ("e-pricer", "Dealer Website"),
        ("TrueCar", "TrueCar"),
        ("Unknown Source XYZ", "Unknown Source XYZ"),
    ]
    all_correct = True
    failures = []
    for input_name, expected_vendor in rollup_cases:
        result = rollup_vendor(input_name)
        if result != expected_vendor:
            all_correct = False
            failures.append(f"'{input_name}' -> '{result}' (expected '{expected_vendor}')")
    test("Vendor rollup mappings correct",
         all_correct,
         f"Failures: {'; '.join(failures)}")


# ── Test 4: Artifact Detection ───────────────────────────────────────
print("\n4. Artifact Detection")

if not CAN_IMPORT:
    skip("Artifact detection", f"Cannot import: {IMPORT_ERR}")
else:
    # Build test vendor rows
    test_vendors = [
        {"vendor": "Service Dept", "good_leads": 20, "sales": 8, "close_rate": 40.0},
        {"vendor": "Dealer Mgmt Sys", "good_leads": 200, "sales": 35, "close_rate": 17.5},
        {"vendor": "AutoTrader", "good_leads": 80, "sales": 10, "close_rate": 12.5},
        {"vendor": "Previous Customer", "good_leads": 5, "sales": 4, "close_rate": 80.0},
        {"vendor": "Walk-In Traffic", "good_leads": 30, "sales": 8, "close_rate": 26.7},
    ]
    artifacts = detect_artifacts(test_vendors)
    flagged_names = [a["vendor"] for a in artifacts]

    test("Service Dept flagged as artifact",
         "Service Dept" in flagged_names)
    test("Dealer Mgmt Sys flagged as artifact",
         "Dealer Mgmt Sys" in flagged_names)
    test("Previous Customer flagged as artifact",
         "Previous Customer" in flagged_names)
    test("Walk-In Traffic flagged as artifact",
         "Walk-In Traffic" in flagged_names)
    test("AutoTrader NOT flagged as artifact",
         "AutoTrader" not in flagged_names,
         f"Flagged vendors: {flagged_names}")


# ── Test 5: Tier Assignment ──────────────────────────────────────────
print("\n5. Tier Assignment")

if not CAN_IMPORT:
    skip("Tier assignment", f"Cannot import: {IMPORT_ERR}")
else:
    # CPS-based tiers (when cost data available)
    test("CPS < $500 = TIER 1",
         assign_tier(10, 100, 300, True, 10.0)[0] == "TIER 1")
    test("CPS $500-999 = TIER 2",
         assign_tier(10, 100, 750, True, 10.0)[0] == "TIER 2")
    test("CPS $1000-1499 = TIER 3",
         assign_tier(10, 100, 1200, True, 10.0)[0] == "TIER 3")
    test("CPS >= $1500 = TIER 4",
         assign_tier(10, 100, 2000, True, 10.0)[0] == "TIER 4")

    # Close-rate-based tiers (no cost data)
    test("CR >= 8% = TIER 1",
         assign_tier(10, 100, 0, False, 10.0)[0] == "TIER 1")
    test("CR 5-7.99% = TIER 2",
         assign_tier(5, 100, 0, False, 5.0)[0] == "TIER 2")
    test("CR 2-4.99% = TIER 3",
         assign_tier(3, 100, 0, False, 3.0)[0] == "TIER 3")
    test("CR < 2% = TIER 4",
         assign_tier(1, 100, 0, False, 1.0)[0] == "TIER 4")


# ── Test 6: NADA Seasonal Projection ────────────────────────────────
print("\n6. NADA Seasonal Projection")

if not CAN_IMPORT:
    skip("NADA projection", f"Cannot import: {IMPORT_ERR}")
else:
    # Verify NADA indices exist for all 12 months
    test("NADA has 12 months", len(NADA) == 12 and all(m in NADA for m in range(1, 13)))

    # Verify indices sum close to 12.0 (average = 1.0)
    nada_sum = sum(NADA.values())
    test("NADA indices average ~1.0",
         abs(nada_sum - 12.0) < 0.5,
         f"Sum: {nada_sum}")

    # Test projection calculation
    annual_sales = 120
    monthly_avg = annual_sales / 12
    projected = [monthly_avg * NADA[m] for m in range(1, 13)]
    projected_sum = sum(projected)
    test("NADA projection preserves annual total",
         abs(projected_sum - annual_sales) < 5,
         f"Projected sum: {projected_sum}, expected ~{annual_sales}")


# ── Test 7: Detect Mode CLI ─────────────────────────────────────────
print("\n7. Detect Mode CLI")

if not os.path.exists(FORECAST_SCRIPT):
    skip("Detect mode CLI", "dealership_forecast.py not found")
else:
    result = subprocess.run(
        [PYTHON, FORECAST_SCRIPT, "detect", FIXTURES_DIR],
        capture_output=True, text=True, timeout=30,
    )
    test("detect mode exits cleanly",
         result.returncode == 0,
         f"stderr: {result.stderr[:200]}")

    if result.returncode == 0:
        try:
            output = json.loads(result.stdout)
            test("detect mode returns valid JSON with files_found",
                 "files_found" in output or isinstance(output, list),
                 f"Keys: {list(output.keys()) if isinstance(output, dict) else 'list'}")
        except json.JSONDecodeError:
            # Check if it just printed text output
            test("detect mode produces output",
                 len(result.stdout.strip()) > 0,
                 "No output")


# ── Test 8: Build Mode Config Validation ─────────────────────────────
print("\n8. Build Mode Config Validation")

config_fixture = os.path.join(FIXTURES_DIR, "forecast_config_sample.json")
if not os.path.exists(config_fixture):
    skip("Config validation", "Fixture not found")
else:
    with open(config_fixture) as f:
        config = json.load(f)
    required_config_keys = ["dealership", "date_start", "date_end", "crm",
                            "input_files", "output_path"]
    missing = [k for k in required_config_keys if k not in config]
    test("Config has all required keys",
         len(missing) == 0,
         f"Missing: {missing}")
    test("Config crm value is valid",
         config.get("crm") in ["momentum", "vinsolutions", "tekion", "dealersocket"],
         f"Got: {config.get('crm')}")


# ── Test 9: validate_config() Function ──────────────────────────────
print("\n9. validate_config() Function")

if not CAN_IMPORT:
    skip("validate_config()", f"Cannot import: {IMPORT_ERR}")
else:
    try:
        from dealership_forecast import validate_config, validate_parsed_rows, VALID_CRMS

        # 9a. Valid config passes
        config_fixture_path = os.path.join(FIXTURES_DIR, "forecast_config_sample.json")
        if os.path.exists(config_fixture_path):
            with open(config_fixture_path) as f:
                valid_config = json.load(f)
            is_valid, errs = validate_config(valid_config)
            test("Valid config fixture passes validation", is_valid, f"Errors: {errs[:3]}")
        else:
            skip("Valid config fixture", "File not found")

        # 9b. Missing required field
        bad_config = {"crm": "momentum", "input_files": ["test.csv"]}
        is_valid, errs = validate_config(bad_config)
        test("Missing config.dealership detected",
             not is_valid and any("dealership" in e for e in errs),
             f"Errors: {errs[:2]}")

        # 9c. Invalid CRM
        bad_crm_config = {
            "crm": "unknown_crm", "input_files": ["test.csv"],
            "dealership": "Test", "date_start": "2026-01-01",
            "date_end": "2026-01-31", "output_path": "/tmp/test.xlsx"
        }
        is_valid, errs = validate_config(bad_crm_config)
        test("Invalid CRM value detected",
             not is_valid and any("crm" in e.lower() for e in errs),
             f"Errors: {errs[:2]}")

        # 9d. Empty input_files
        bad_files = {
            "crm": "momentum", "input_files": [],
            "dealership": "Test", "date_start": "2026-01-01",
            "date_end": "2026-01-31", "output_path": "/tmp/test.xlsx"
        }
        is_valid, errs = validate_config(bad_files)
        test("Empty input_files detected",
             not is_valid and any("input_files" in e for e in errs),
             f"Errors: {errs[:2]}")

        # 9e. Non-dict config
        is_valid, errs = validate_config("not a dict")
        test("Non-dict config rejected",
             not is_valid and any("Config" in e for e in errs))

        # 9f. Empty dealership string
        bad_empty = {
            "crm": "momentum", "input_files": ["test.csv"],
            "dealership": "", "date_start": "2026-01-01",
            "date_end": "2026-01-31", "output_path": "/tmp/test.xlsx"
        }
        is_valid, errs = validate_config(bad_empty)
        test("Empty dealership string detected",
             not is_valid and any("dealership" in e for e in errs),
             f"Errors: {errs[:2]}")

    except ImportError as e:
        skip("validate_config()", f"Could not import: {e}")


# ── Test 10: validate_parsed_rows() Function ──────────────────────────
print("\n10. validate_parsed_rows() Function")

if not CAN_IMPORT:
    skip("validate_parsed_rows()", f"Cannot import: {IMPORT_ERR}")
else:
    try:
        from dealership_forecast import validate_parsed_rows, make_row

        # 10a. Valid parsed rows
        valid_rows = [
            make_row("AutoTrader", good=50, total=60, sales=5),
            make_row("Dealer Website", good=100, total=120, sales=15),
        ]
        is_valid, errs = validate_parsed_rows(valid_rows)
        test("Valid parsed rows pass", is_valid, f"Errors: {errs[:3]}")

        # 10b. Empty list
        is_valid, errs = validate_parsed_rows([])
        test("Empty parsed rows detected",
             not is_valid and any("empty" in e.lower() for e in errs))

        # 10c. Non-list input
        is_valid, errs = validate_parsed_rows("not a list")
        test("Non-list parsed rows rejected",
             not is_valid and any("list" in e.lower() for e in errs))

        # 10d. Row with empty source_name
        bad_rows = [make_row("", good=10, total=12, sales=1)]
        is_valid, errs = validate_parsed_rows(bad_rows)
        test("Empty source_name detected",
             not is_valid and any("source_name" in e for e in errs),
             f"Errors: {errs[:2]}")

        # 10e. Non-dict row
        is_valid, errs = validate_parsed_rows(["not a dict", "also not"])
        test("Non-dict row rejected",
             not is_valid and any("wrong type" in e.lower() for e in errs))

    except ImportError as e:
        skip("validate_parsed_rows()", f"Could not import: {e}")


# ── Summary ──────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"dealership-forecast: {passed} passed, {failed} failed, {skipped} skipped")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
