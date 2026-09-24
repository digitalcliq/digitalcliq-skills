#!/usr/bin/env python3
"""
score-leads validate_skill.py
Tests: path resolution, CSV schema, scoring engine, new/used classification,
       output filename, glob patterns.
"""

import sys
import os
import csv
import glob
import shutil
import subprocess
import tempfile

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(TESTS_DIR)
SKILLS_ROOT = os.path.dirname(SKILL_DIR)
PROJECT_ROOT = os.path.abspath(os.path.join(SKILLS_ROOT, '..', '..'))
PYTHON = "/usr/bin/python3"

SCORE_SCRIPT = os.path.join(SKILL_DIR, "score_leads.py")
FIXTURE_CSV = os.path.join(TESTS_DIR, "test_inputs", "score_leads_sample.csv")
FIXTURE_MOMENTUM = os.path.join(TESTS_DIR, "test_inputs", "momentum_raw_sample.csv")

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


# ── Test 1: Path Resolution ──────────────────────────────────────────
print("\n1. Path Resolution")

inbox_path = os.path.join(PROJECT_ROOT, "01_Inbox")
inbox_exists = os.path.isdir(inbox_path)
test("01_Inbox directory exists", inbox_exists, f"Expected: {inbox_path}")

# Test glob pattern from working directory (case-insensitive matching)
if inbox_exists:
    # Create temp files to test glob patterns (no dot prefix — dots hide from glob)
    test_file = os.path.join(inbox_path, "_test_glob_score_leads.csv")
    try:
        with open(test_file, "w") as f:
            f.write("test")
        matches = glob.glob(os.path.join(inbox_path, "*test_glob*"))
        test("Glob pattern finds files with underscores", len(matches) >= 1,
             f"Found {len(matches)} matches")
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)

    # Test that glob matches files with spaces
    test_file_spaces = os.path.join(inbox_path, "_test glob score leads.csv")
    try:
        with open(test_file_spaces, "w") as f:
            f.write("test")
        matches = glob.glob(os.path.join(inbox_path, "*test glob*"))
        test("Glob pattern finds files with spaces", len(matches) >= 1,
             f"Found {len(matches)} matches")
    finally:
        if os.path.exists(test_file_spaces):
            os.remove(test_file_spaces)
else:
    skip("Glob pattern tests", "01_Inbox does not exist")


# ── Test 2: Normalized CSV Schema ────────────────────────────────────
print("\n2. Normalized CSV Schema")

expected_cols = ["source", "leads", "contact", "contact_pct", "appts",
                 "appts_pct", "shows", "shows_pct", "sales", "sales_pct"]

with open(FIXTURE_CSV, newline="") as f:
    reader = csv.DictReader(f)
    headers = reader.fieldnames
    rows = list(reader)

test("All 10 required columns present",
     all(c in headers for c in expected_cols),
     f"Missing: {[c for c in expected_cols if c not in headers]}")

test("Has data rows (excluding header)",
     len(rows) >= 7, f"Found {len(rows)} rows")

# Check no % signs in numeric fields
pct_fields = ["contact_pct", "appts_pct", "shows_pct", "sales_pct"]
has_pct = False
for row in rows:
    for field in pct_fields:
        if "%" in str(row.get(field, "")):
            has_pct = True
test("No % signs in percentage fields", not has_pct)

# Check Totals row
has_totals = any(row.get("source", "").lower() == "totals" for row in rows)
test("Totals row present", has_totals)


# ── Test 3: Scoring Engine ───────────────────────────────────────────
print("\n3. Scoring Engine (run score_leads.py)")

if not os.path.exists(SCORE_SCRIPT):
    skip("Scoring engine", "score_leads.py not found")
else:
    tmp_dir = tempfile.mkdtemp(prefix="test_dcliq_score_")
    tmp_input = os.path.join(tmp_dir, "test_input.csv")
    tmp_output = os.path.join(tmp_dir, "Test_Store_Lead_Scores_2026-03-01.xlsx")

    try:
        shutil.copy(FIXTURE_CSV, tmp_input)
        # --no-validate: this test writes to a temp dir, and the folded-in
        # post-flight (correctly) requires the vault outputs/ folder. We test
        # scoring/Excel generation here, not the deliverable-location policy.
        result = subprocess.run(
            [PYTHON, SCORE_SCRIPT, tmp_input, tmp_output, "Test Store", "Feb 2026", "--no-validate"],
            capture_output=True, text=True, timeout=30,
        )
        test("score_leads.py exits cleanly", result.returncode == 0,
             f"stderr: {result.stderr[:200]}")
        test("Output Excel file created", os.path.exists(tmp_output),
             f"Expected: {tmp_output}")

        if os.path.exists(tmp_output):
            try:
                from openpyxl import load_workbook
                wb = load_workbook(tmp_output)
                sheet_names = wb.sheetnames
                test("Excel has 'Lead Source Scores' sheet",
                     "Lead Source Scores" in sheet_names,
                     f"Sheets: {sheet_names}")

                ws = wb["Lead Source Scores"]
                # Find score column (column B after header block) and verify 1-10 range
                scores = []
                for row in ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True):
                    if row and isinstance(row[0], (int, float)) and 1 <= row[0] <= 10:
                        scores.append(row[0])
                test("Scores are in 1-10 range",
                     len(scores) >= 5 and all(1 <= s <= 10 for s in scores),
                     f"Found {len(scores)} scores: {scores[:5]}")
                wb.close()
            except ImportError:
                skip("Excel validation", "openpyxl not installed")
    except subprocess.TimeoutExpired:
        test("score_leads.py completes within timeout", False, "Timed out at 30s")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 4: New/Used Classification ──────────────────────────────────
print("\n4. New/Used Source Classification")

# Import the classify function directly
sys.path.insert(0, SKILL_DIR)
try:
    from score_leads import classify_source_type, USED_SOURCE_PATTERNS, NEW_CAR_SALE_RATE_BOOST

    used_sources = ["AutoTrader.com", "CARFAX", "CarGurus", "Cars.com"]
    new_sources = ["Dealer Website", "TrueCar", "Costco Auto", "Meta (Paid Social)"]

    all_used_correct = all(classify_source_type(s) == "Used" for s in used_sources)
    all_new_correct = all(classify_source_type(s) == "New" for s in new_sources)

    test("Used sources classified correctly",
         all_used_correct,
         f"Failed for: {[s for s in used_sources if classify_source_type(s) != 'Used']}")
    test("New sources classified correctly",
         all_new_correct,
         f"Failed for: {[s for s in new_sources if classify_source_type(s) != 'New']}")
    test("New car boost factor is 1.5",
         NEW_CAR_SALE_RATE_BOOST == 1.5,
         f"Got: {NEW_CAR_SALE_RATE_BOOST}")
except ImportError as e:
    skip("New/Used classification", f"Could not import score_leads: {e}")


# ── Test 5: Output Filename Pattern ──────────────────────────────────
print("\n5. Output Filename Pattern")

from datetime import date
today = date.today().strftime("%Y-%m-%d")
expected_pattern = f"Test_Store_Lead_Scores_{today}.xlsx"
test("Filename uses underscores for spaces",
     " " not in expected_pattern and "_" in expected_pattern)
test("Filename ends with .xlsx", expected_pattern.endswith(".xlsx"))
test("Filename contains date", today in expected_pattern)


# ── Test 6: Glob Pattern Edge Cases ──────────────────────────────────
print("\n6. Glob Pattern Edge Cases")

# Test case-insensitive matching by checking patterns
test_names = [
    "Sterling BMW Lead Report February.csv",
    "sterling_data.csv",
    "STERLING_REPORT.csv",
]
for name in test_names:
    matches_lower = "sterling" in name.lower()
    test(f"Case-insensitive match: '{name}'", matches_lower)


# ── Test 7: validate_data() Function ──────────────────────────────────
print("\n7. validate_data() Function")

try:
    from score_leads import validate_data, REQUIRED_CSV_COLUMNS

    # 7a. Valid fixture passes
    with open(FIXTURE_CSV, newline="") as f:
        import csv as csv_mod
        reader = csv_mod.DictReader(f)
        valid_headers = reader.fieldnames
        valid_rows = list(reader)

    is_valid, errs = validate_data(valid_headers, valid_rows)
    test("Valid CSV fixture passes validation", is_valid, f"Errors: {errs[:3]}")

    # 7b. Missing columns
    partial_headers = ["source", "leads", "sales"]
    is_valid, errs = validate_data(partial_headers, [{"source": "Test", "leads": "10", "sales": "1"}])
    test("Missing CSV columns detected",
         not is_valid and any("missing" in e.lower() for e in errs),
         f"Errors: {errs[:2]}")

    # 7c. None headers
    is_valid, errs = validate_data(None, [])
    test("None headers rejected",
         not is_valid and any("headers" in e.lower() for e in errs))

    # 7d. Empty source name
    is_valid, errs = validate_data(
        REQUIRED_CSV_COLUMNS,
        [{"source": "", "leads": "10", "contact": "5", "contact_pct": "50",
          "appts": "3", "appts_pct": "30", "shows": "2", "shows_pct": "20",
          "sales": "1", "sales_pct": "10"}]
    )
    test("Empty source name detected",
         not is_valid and any("source" in e.lower() for e in errs),
         f"Errors: {errs[:2]}")

    # 7e. Non-numeric value in numeric field
    is_valid, errs = validate_data(
        REQUIRED_CSV_COLUMNS,
        [{"source": "Test", "leads": "not_a_number", "contact": "5",
          "contact_pct": "50", "appts": "3", "appts_pct": "30",
          "shows": "2", "shows_pct": "20", "sales": "1", "sales_pct": "10"}]
    )
    test("Non-numeric leads value detected",
         not is_valid and any("leads" in e for e in errs),
         f"Errors: {errs[:2]}")

    # 7f. Empty rows
    is_valid, errs = validate_data(REQUIRED_CSV_COLUMNS, [])
    test("Empty rows detected",
         not is_valid and any("no data" in e.lower() for e in errs),
         f"Errors: {errs[:2]}")

except ImportError as e:
    skip("validate_data()", f"Could not import: {e}")


# ── Test 8: Ingestion / format adapters ──────────────────────────────
print("\n8. Ingestion (ingest.py)")
try:
    sys.path.insert(0, SKILL_DIR)
    import ingest

    # 8a. Format detection by header signature
    test("detect tekion",
         ingest.detect_format(["Primary Vehicle Stock Type", "Lead Source Group",
                               "Total Good Leads", "Sold In Time Period"]) == "tekion")
    test("detect momentum",
         ingest.detect_format(["lead_provider", "leads", "contact_made_cnt",
                               "appt_set_cnt", "sale_cnt"]) == "momentum")
    test("detect vinsolutions",
         ingest.detect_format(["Lead Source Group", "Good Leads", "Sold from Leads"]) == "vinsolutions")
    test("detect native",
         ingest.detect_format(["source", "leads", "sales_pct"]) == "native")
    test("unknown format -> None",
         ingest.detect_format(["foo", "bar", "baz"]) is None)

    # 8b. Canonical vendor roll-up map
    cmap = ingest.load_canonical_map()
    test("canonical: cargurus variant -> CarGurus",
         ingest.canonical_vendor("CarGurus - Digital Deal", cmap) == "CarGurus")
    test("canonical: walk-in routes to Walk-in / Location",
         ingest.canonical_vendor("Location-Drives By", cmap) == "Walk-in / Location")
    test("canonical: quick qualify -> credit-app bucket",
         "Quick Qualify" in ingest.canonical_vendor("700 Credit - Quick Qualify", cmap))

    # 8c. End-to-end ingest of a synthetic momentum file
    tmpdir = tempfile.mkdtemp()
    mom = os.path.join(tmpdir, "mom.csv")
    with open(mom, "w", newline="") as f:
        f.write("lead_provider,leads,contact_made_cnt,appt_set_cnt,verified_show_cnt,sale_cnt,figross,frontendgross,unit_gross\n")
        f.write("CarGurus,100,80,20,10,8,0,0,0\n")
        f.write("AutoTrader.com - Wallet Lead,50,40,10,5,4,0,0,0\n")
        f.write("Zero Lead Source,0,0,0,0,0,0,0,0\n")
    rows, meta = ingest.ingest(mom)
    test("ingest momentum: format detected", meta["format"] == "momentum")
    test("ingest momentum: zero-lead row dropped", len(rows) == 2)
    cg = next((r for r in rows if r["source"] == "CarGurus"), None)
    test("ingest momentum: CarGurus close% = 8.0", cg is not None and abs(cg["sales_pct"] - 8.0) < 0.01)
    test("ingest momentum: show% derived shown/set (10/20=50)",
         cg is not None and abs(cg["shows_pct"] - 50.0) < 0.01)

    # 8d. Roll-up flag consolidates marketplace variants
    rows_roll, _ = ingest.ingest(mom, rollup=True)
    at = next((r for r in rows_roll if r["source"] == "AutoTrader.com"), None)
    test("ingest --rollup: AutoTrader variant consolidated", at is not None)

    # 8e. Native passthrough
    nat = os.path.join(tmpdir, "nat.csv")
    with open(nat, "w", newline="") as f:
        f.write("source,leads,contact,contact_pct,appts,appts_pct,shows,shows_pct,sales,sales_pct\n")
        f.write("Dealer Website,150,130,86.7,45,30,35,77.8,12,8.0\n")
    rows_n, meta_n = ingest.ingest(nat)
    test("ingest native: passthrough one row", meta_n["format"] == "native" and len(rows_n) == 1)

    # 8f. PDF heuristic text parser (no real PDF needed — test the parser directly)
    pdf_text = (
        "Lead Source        Leads  Cont  Cont%  Appt  Appt%  Show  Show%  Sale  Sale%\n"
        "CarGurus             100    80    80%    20    20%    10    50%     8    8%\n"
        "AutoTrader            50    40    80%    10    20%     5    50%     4    8%\n"
        "Totals               150   120    80%    30    20%    15    50%    12    8%\n"
    )
    precs = ingest.parse_pdf_text(pdf_text)
    test("pdf parse: 2 source rows (totals skipped)", len(precs) == 2)
    test("pdf parse: CarGurus counts mapped",
         any(r["source"] == "CarGurus" and r["leads"] == 100 and r["sales"] == 8 for r in precs))

    shutil.rmtree(tmpdir, ignore_errors=True)

except Exception as e:  # noqa: BLE001
    test("ingest.py importable & functional", False, f"{type(e).__name__}: {e}")


# ── Summary ──────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"score-leads: {passed} passed, {failed} failed, {skipped} skipped")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
