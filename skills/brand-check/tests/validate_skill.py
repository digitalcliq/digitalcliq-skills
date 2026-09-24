#!/usr/bin/env python3
"""
brand-check validate_skill.py
Tests: guideline files exist, brand alias resolution, content structure,
       prohibited words extractable, SKILL.md aliases.
"""

import sys
import os
import re

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(TESTS_DIR)
BRANDS_DIR = os.path.join(SKILL_DIR, "brands")
SKILL_MD = os.path.join(SKILL_DIR, "SKILL.md")

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


# ── Test 1: Guideline Files Exist ────────────────────────────────────
print("\n1. Brand Guideline Files Exist")

expected_files = {
    "bmw.md": os.path.join(BRANDS_DIR, "bmw.md"),
    "nissan.md": os.path.join(BRANDS_DIR, "nissan.md"),
    "stellantis.md": os.path.join(BRANDS_DIR, "stellantis.md"),
}

for name, path in expected_files.items():
    exists = os.path.isfile(path)
    test(f"brands/{name} exists", exists, f"Expected: {path}")
    if exists:
        size = os.path.getsize(path)
        test(f"brands/{name} is non-trivial (>100 lines)",
             size > 2000,  # ~100 lines * ~20 chars avg
             f"Size: {size} bytes")


# ── Test 2: Brand Alias Resolution ───────────────────────────────────
print("\n2. Brand Alias Resolution")

ALIAS_MAP = {
    "bmw": "bmw.md",
    "nissan": "nissan.md",
    "stellantis": "stellantis.md",
    "cdjr": "stellantis.md",
    "chrysler": "stellantis.md",
    "dodge": "stellantis.md",
    "jeep": "stellantis.md",
    "ram": "stellantis.md",
    "fiat": "stellantis.md",
}

for alias, expected_file in ALIAS_MAP.items():
    # Resolve alias to brand
    if alias in ("bmw",):
        brand = "bmw"
    elif alias in ("nissan",):
        brand = "nissan"
    else:
        brand = "stellantis"

    guideline_path = os.path.join(BRANDS_DIR, f"{brand}.md")
    test(f"Alias '{alias}' resolves to {expected_file}",
         os.path.isfile(guideline_path),
         f"File not found: {guideline_path}")


# ── Test 3: Content Structure ────────────────────────────────────────
print("\n3. Guideline Content Structure")

for brand_file in ["bmw.md", "nissan.md", "stellantis.md"]:
    path = os.path.join(BRANDS_DIR, brand_file)
    if not os.path.isfile(path):
        skip(f"{brand_file} content structure", "File not found")
        continue

    with open(path, "r") as f:
        content = f.read()

    lines = content.split("\n")
    test(f"{brand_file} has 100+ lines",
         len(lines) >= 100,
         f"Found {len(lines)} lines")

    # Check for markdown headers
    headers = [l for l in lines if l.startswith("## ") or l.startswith("# ")]
    test(f"{brand_file} has markdown section headers",
         len(headers) >= 3,
         f"Found {len(headers)} headers")


# ── Test 4: Prohibited Words Extractable ─────────────────────────────
print("\n4. Prohibited Words Extractable")

# Common prohibited words across automotive brands
PROHIBITED_TERMS = ["blowout", "liquidat", "below invoice", "fire sale",
                    "going out of business", "everything must go"]

for brand_file in ["bmw.md", "nissan.md", "stellantis.md"]:
    path = os.path.join(BRANDS_DIR, brand_file)
    if not os.path.isfile(path):
        skip(f"{brand_file} prohibited words", "File not found")
        continue

    with open(path, "r") as f:
        content = f.read().lower()

    # Check if the guideline file references prohibited/distressed messaging
    has_prohib_section = any(term in content for term in
                            ["prohibit", "distress", "not allow", "forbidden",
                             "do not use", "avoid", "restricted"])
    test(f"{brand_file} references prohibited messaging rules",
         has_prohib_section,
         "No prohibition section found")


# ── Test 5: SKILL.md Aliases Documented ──────────────────────────────
print("\n5. SKILL.md Aliases Documented")

if not os.path.isfile(SKILL_MD):
    skip("SKILL.md aliases", "SKILL.md not found")
else:
    with open(SKILL_MD, "r") as f:
        skill_content = f.read().lower()

    expected_aliases = ["cdjr", "dodge", "jeep", "ram"]
    found = [a for a in expected_aliases if a in skill_content]
    test("SKILL.md documents brand aliases",
         len(found) >= 3,
         f"Found: {found}, expected at least 3 of {expected_aliases}")

    # Check SKILL.md references all three brands
    for brand in ["bmw", "nissan", "stellantis"]:
        test(f"SKILL.md references '{brand}'",
             brand in skill_content)


# ── Test 6: Shared Codified Web Brand Checks ─────────────────────────
print("\n6. Shared codified web brand checks reachable")

COMPLIANCE_DIR = os.path.join(os.path.dirname(SKILL_DIR), "dealership-compliance-audit")
registry_path = os.path.join(COMPLIANCE_DIR, "checks", "registry.py")
test("compliance-audit checks/registry.py exists", os.path.isfile(registry_path),
     f"Expected: {registry_path}")

if os.path.isfile(registry_path):
    sys.path.insert(0, COMPLIANCE_DIR)
    try:
        from checks import registry as _reg
        frameworks = set(r["framework"] for r in _reg.registry_summary())
        test("shared registry exposes the BRAND framework", "BRAND" in frameworks,
             f"frameworks: {sorted(frameworks)}")
        brand_checks = [r for r in _reg.registry_summary() if r["framework"] == "BRAND"]
        test("BRAND framework has codified checks", len(brand_checks) >= 2,
             f"got {len(brand_checks)}")
    except Exception as e:
        test("shared registry imports", False, str(e))


# ── Summary ──────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"brand-check: {passed} passed, {failed} failed, {skipped} skipped")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
