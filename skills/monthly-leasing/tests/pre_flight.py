#!/usr/bin/env python3
"""monthly-leasing pre_flight — validates roster and scripts exist."""

import sys
import os
import json

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run():
    result = {
        "skill": "monthly-leasing",
        "status": "ok",
        "inbox_scan": {"total_files": 0, "by_extension": {}, "warnings": []},
        "file_matches": None,
        "errors": [],
        "warnings": [],
    }

    # Check required files
    required_files = {
        "dealer_roster.json": os.path.join(SKILL_DIR, "dealer_roster.json"),
        "merge_brand_data.py": os.path.join(SKILL_DIR, "merge_brand_data.py"),
        "generate_lease_report.py": os.path.join(SKILL_DIR, "generate_lease_report.py"),
    }

    for name, path in required_files.items():
        if not os.path.exists(path):
            result["errors"].append(f"{name} not found at {path}")

    # Validate roster is valid JSON
    roster_path = required_files["dealer_roster.json"]
    if os.path.exists(roster_path):
        try:
            with open(roster_path) as f:
                roster = json.load(f)
            if "brands" not in roster:
                result["warnings"].append("dealer_roster.json missing 'brands' key")
        except json.JSONDecodeError as e:
            result["errors"].append(f"dealer_roster.json invalid JSON: {e}")

    # Check openpyxl
    try:
        import openpyxl
    except ImportError:
        result["errors"].append("openpyxl not installed")

    if result["errors"]:
        result["status"] = "errors"
    elif result["warnings"]:
        result["status"] = "warnings"

    return result


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] != "errors" else 1)
