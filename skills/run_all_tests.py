#!/usr/bin/env python3
"""
DigitalCLIQ Skill Test Suite — Master Runner

Usage:
    python3 run_all_tests.py                  # run everything
    python3 run_all_tests.py score-leads      # run one skill
    python3 run_all_tests.py --preflight      # preflight only
    python3 run_all_tests.py --validate       # validation only
"""

import os
import sys
import subprocess
import json
import time

SKILLS_ROOT = os.path.dirname(os.path.abspath(__file__))
PYTHON = "/usr/bin/python3"

SKILL_NAMES = [
    "score-leads",
    "dealership-forecast",
    "brand-check",
    "dealership-compliance-audit",
    "morning-coffee",
    "auto-trends",
    "monthly-leasing",
]


def run_script(script_path):
    """Run a Python script and capture results. Returns (return_code, stdout, stderr)."""
    try:
        result = subprocess.run(
            [PYTHON, script_path],
            capture_output=True, text=True, timeout=120,
            cwd=os.path.dirname(script_path),
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT after 120 seconds"
    except Exception as e:
        return -1, "", str(e)


def parse_validate_output(stdout):
    """Parse validate_skill.py output for pass/fail/skip counts."""
    passed = stdout.count("[PASS]")
    failed = stdout.count("[FAIL]")
    skipped = stdout.count("[SKIP]")
    total = passed + failed + skipped
    return passed, failed, skipped, total


def parse_preflight_output(stdout):
    """Parse pre_flight.py output."""
    try:
        data = json.loads(stdout)
        errs = len(data.get("errors", []))
        warns = len(data.get("warnings", []))
        checks = 1 + (1 if data.get("file_matches") else 0) + (1 if data.get("inbox_scan") else 0)
        passed = checks - (1 if errs else 0)
        return passed, 1 if errs else 0, 0, checks, warns
    except (json.JSONDecodeError, TypeError):
        # Fallback: look for PASS/FAIL strings
        passed = stdout.count("PASS") + stdout.count("ok")
        failed = stdout.count("FAIL") + stdout.count("error")
        return max(passed, 1), failed, 0, max(passed + failed, 1), 0


def main():
    args = sys.argv[1:]
    run_preflight = True
    run_validate = True
    skills_to_run = []

    for arg in args:
        if arg == "--preflight":
            run_validate = False
        elif arg == "--validate":
            run_preflight = False
        elif arg in SKILL_NAMES:
            skills_to_run.append(arg)
        else:
            print(f"Unknown argument: {arg}")
            print(f"Available skills: {', '.join(SKILL_NAMES)}")
            sys.exit(1)

    if not skills_to_run:
        skills_to_run = SKILL_NAMES

    # Header
    print()
    print("=" * 68)
    print("  DigitalCLIQ Skill Test Results")
    print("=" * 68)
    print(f"  {'Skill':<24} {'Preflight':<14} {'Validate':<14} {'Status'}")
    print("-" * 68)

    total_ok = 0
    total_warn = 0
    total_fail = 0
    all_output = []

    for skill in skills_to_run:
        skill_dir = os.path.join(SKILLS_ROOT, skill, "tests")
        preflight_script = os.path.join(skill_dir, "pre_flight.py")
        validate_script = os.path.join(skill_dir, "validate_skill.py")

        pf_str = "---"
        val_str = "---"
        status = "OK"
        has_fail = False
        has_warn = False

        # Run preflight
        if run_preflight and os.path.exists(preflight_script):
            rc, out, err = run_script(preflight_script)
            all_output.append(f"\n--- {skill} preflight ---\n{out}")
            if err.strip():
                all_output.append(f"  STDERR: {err.strip()}")
            p, f, s, t, w = parse_preflight_output(out)
            if f > 0 or rc != 0:
                pf_str = f"FAIL ({p}/{t})"
                has_fail = True
            elif w > 0:
                pf_str = f"WARN ({p}/{t})"
                has_warn = True
            else:
                pf_str = f"PASS ({p}/{t})"

        # Run validate
        if run_validate and os.path.exists(validate_script):
            rc, out, err = run_script(validate_script)
            all_output.append(f"\n--- {skill} validate ---\n{out}")
            if err.strip():
                all_output.append(f"  STDERR: {err.strip()}")
            p, f, s, t = parse_validate_output(out)
            if f > 0 or rc != 0:
                val_str = f"FAIL ({p}/{t})"
                has_fail = True
            elif s > 0:
                val_str = f"WARN ({p}/{t})"
                has_warn = True
            else:
                val_str = f"PASS ({p}/{t})"

        if has_fail:
            status = "FAIL"
            total_fail += 1
        elif has_warn:
            status = "WARN"
            total_warn += 1
        else:
            total_ok += 1

        emoji = {"OK": "\u2705", "WARN": "\u26a0\ufe0f ", "FAIL": "\u274c"}
        print(f"  {skill:<24} {pf_str:<14} {val_str:<14} {emoji.get(status, '')} {status}")

    # Footer
    print("-" * 68)
    total = len(skills_to_run)
    print(f"  Total: {total} skills, {total_ok} OK, {total_warn} WARN, {total_fail} FAIL")
    print("=" * 68)

    # Print detailed output if there were failures
    if total_fail > 0:
        print("\n\nDETAILED OUTPUT:")
        for line in all_output:
            print(line)

    # Exit code
    if total_fail > 0:
        sys.exit(1)
    elif total_warn > 0:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
