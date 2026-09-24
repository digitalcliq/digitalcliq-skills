#!/usr/bin/env python3
"""
validate_skill.py — entrypoint for the shared test runner (run_all_tests.py).

Structural checks on the test-driven pipeline, then runs the full codified-check
suite (test_checks.py) and forwards its PASS/FAIL lines.
"""

import os
import sys
import subprocess

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, SKILL_DIR)
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))

passed = 0
failed = 0


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        print("  [PASS] %s" % name)
        passed += 1
    else:
        print("  [FAIL] %s  -- %s" % (name, detail))
        failed += 1


# ── 1. Pipeline files present ────────────────────────────────
print("\n1. Test-driven pipeline files exist")
for rel in ["checks/registry.py", "checks/__init__.py",
            "scripts/fallback_crawl.py", "scripts/verify_loop.py",
            "scripts/run_checks.py", "tests/test_checks.py",
            "tests/fixtures/clean_crawl.json", "tests/fixtures/violations_crawl.json"]:
    test("%s exists" % rel, os.path.isfile(os.path.join(SKILL_DIR, rel)),
         "missing: %s" % rel)


# ── 2. Registry codifies all frameworks ──────────────────────
print("\n2. Registry codifies 9 frameworks + pricing + brand")
try:
    from checks import registry
    frameworks = set(r["framework"] for r in registry.registry_summary())
    for fw in ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "PRICING", "BRAND"]:
        test("framework %s codified" % fw, fw in frameworks)
except Exception as e:
    test("registry imports", False, str(e))


# ── 3. Fallback + verify modules import ──────────────────────
print("\n3. Fallback crawler and verify loop import")
try:
    import fallback_crawl  # noqa: F401
    import verify_loop      # noqa: F401
    test("fallback_crawl + verify_loop import", True)
except Exception as e:
    test("fallback_crawl + verify_loop import", False, str(e))


# ── 4. Full codified-check suite ─────────────────────────────
print("\n4. Codified-check suite (tests/test_checks.py)")
proc = subprocess.run([sys.executable, os.path.join(TESTS_DIR, "test_checks.py")],
                      capture_output=True, text=True)
sub_pass = proc.stdout.count("[PASS]")
sub_fail = proc.stdout.count("[FAIL]")
test("test_checks.py suite passes (%d checks)" % sub_pass, proc.returncode == 0,
     "%d sub-failures; last lines:\n%s" % (sub_fail, "\n".join(proc.stdout.splitlines()[-4:])))


# ── Summary ──────────────────────────────────────────────────
print("\n" + "=" * 56)
print("dealership-compliance-audit: %d passed, %d failed" % (passed, failed))
print("=" * 56)
sys.exit(0 if failed == 0 else 1)
