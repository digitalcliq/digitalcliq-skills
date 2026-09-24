#!/usr/bin/env python3
"""
DigitalCLIQ — Shared Pre-Flight Module
Auto-scans 01_Inbox, fuzzy-matches filenames, normalizes KPI formats, logs corrections.

Import from any skill's tests/pre_flight.py:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
    from pre_flight import preflight_report
"""

import os
import re
import json
import csv
from collections import defaultdict

# ---------------------------------------------------------------------------
# Default CRM-to-client matching rules
# ---------------------------------------------------------------------------
DEFAULT_CRM_RULES = [
    {"label": "Sterling BMW / MomentumCRM",
     "keywords": ["sterling"],
     "extensions": [".csv", ".xlsx", ".xls", ".pdf"]},
    {"label": "Nissan of Irvine / VinSolutions",
     "keywords": ["nissan"],
     "extensions": [".csv", ".xlsx", ".xls"]},
    {"label": "McPeek CDJR / Tekion",
     "keywords": ["mcpeek"],
     "extensions": [".csv", ".xlsx", ".xls"]},
    {"label": "J Star / DealerSocket",
     "keywords": ["j star", "jstar", "j_star"],
     "extensions": [".csv", ".xlsx", ".xls"]},
]

# Column name synonyms across CRM systems
COLUMN_SYNONYMS = {
    "source": ["source", "lead_provider", "lead source group", "source name",
               "marketingchannel", "source type (consolidated)"],
    "leads": ["leads", "total_leads", "total leads", "good leads",
              "total good leads", "marketingchannelnewprospects"],
    "sales": ["sales", "total_sales", "sold from leads", "sold in time period",
              "sold in timeframe", "marketingchannelsold"],
    "contact": ["contact", "internet actual contact", "marketingchannelcontacted"],
    "contact_pct": ["contact_pct", "contact %", "internet actual contact %",
                    "internet/oem leads engaged %"],
    "appts": ["appts", "appts set", "appointments scheduled"],
    "appts_pct": ["appts_pct", "appts set %", "appointments scheduled %"],
    "shows": ["shows", "appts shown", "appointments shown"],
    "shows_pct": ["shows_pct", "appts shown %", "appointments scheduled shown %"],
    "sales_pct": ["sales_pct", "sale %", "sold from leads %", "sold in time period %"],
}


# ---------------------------------------------------------------------------
# 1. Inbox Scanner
# ---------------------------------------------------------------------------
def scan_inbox(inbox_path):
    """
    Scan a folder and return a manifest of all files by extension.

    Returns dict with:
        inbox_path, total_files, by_extension, all_files, warnings
    """
    result = {
        "inbox_path": inbox_path,
        "total_files": 0,
        "by_extension": defaultdict(list),
        "all_files": [],
        "warnings": [],
    }

    if not os.path.isdir(inbox_path):
        result["warnings"].append(f"Inbox path does not exist: {inbox_path}")
        return result

    for name in sorted(os.listdir(inbox_path)):
        # Skip hidden and temp files
        if name.startswith(".") or name.startswith("~") or name.startswith("._"):
            continue

        full = os.path.join(inbox_path, name)
        if not os.path.isfile(full):
            continue

        ext = os.path.splitext(name)[1].lower()
        size = os.path.getsize(full)

        entry = {"name": name, "path": full, "ext": ext, "size_bytes": size}
        result["all_files"].append(entry)
        result["by_extension"][ext].append(entry)
        result["total_files"] += 1

        if size == 0:
            result["warnings"].append(f"Empty file: {name}")
        elif size > 50 * 1024 * 1024:
            result["warnings"].append(f"Very large file (>50MB): {name} ({size:,} bytes)")

    # Convert defaultdict to regular dict for JSON serialization
    result["by_extension"] = dict(result["by_extension"])
    return result


# ---------------------------------------------------------------------------
# 2. Fuzzy File Matcher
# ---------------------------------------------------------------------------
def fuzzy_match_files(inbox_manifest, rules=None):
    """
    Match files in inbox to expected client/CRM mappings via case-insensitive
    substring matching.

    Returns dict with:
        matches, unmatched_files, unmatched_rules, corrections
    """
    if rules is None:
        rules = DEFAULT_CRM_RULES

    result = {
        "matches": {},
        "unmatched_files": [],
        "unmatched_rules": [],
        "corrections": [],
    }

    matched_files = set()

    for rule in rules:
        label = rule["label"]
        keywords = rule["keywords"]
        extensions = rule.get("extensions", [".csv", ".xlsx", ".xls", ".pdf"])
        result["matches"][label] = []

        for f in inbox_manifest.get("all_files", []):
            name_lower = f["name"].lower()
            # Also match with underscores/hyphens replaced by spaces
            name_normalized = name_lower.replace("_", " ").replace("-", " ")

            ext = f["ext"].lower()
            if ext not in extensions:
                continue

            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower in name_lower or kw_lower in name_normalized:
                    result["matches"][label].append({
                        "file": f["name"],
                        "path": f["path"],
                        "match_keyword": kw,
                    })
                    matched_files.add(f["name"])
                    break

        if not result["matches"][label]:
            result["unmatched_rules"].append(label)

    # Find files that didn't match any rule
    for f in inbox_manifest.get("all_files", []):
        if f["name"] not in matched_files:
            result["unmatched_files"].append(f["name"])

    return result


# ---------------------------------------------------------------------------
# 3. KPI Normalizer
# ---------------------------------------------------------------------------
def _parse_number(val):
    """Parse a number from various formats: $1,234, 85.7%, ($3,385.22), etc."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)

    s = str(val).strip()
    if s == "" or s == "-" or s.lower() == "n/a":
        return 0.0

    # Handle parenthetical negatives: ($3,385.22)
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]
    elif s.startswith("-"):
        negative = True
        s = s[1:]

    # Strip currency, commas, percent, whitespace
    s = s.replace("$", "").replace(",", "").replace("%", "").strip()

    try:
        result = float(s)
        return -result if negative else result
    except (ValueError, TypeError):
        return 0.0


def normalize_kpis(data, expected_schema=None):
    """
    Detect whether KPI data is flat dict or list-of-dicts, normalize values.

    Returns dict with:
        normalized, original_format, corrections, missing_fields, extra_fields
    """
    result = {
        "normalized": None,
        "original_format": "unknown",
        "corrections": [],
        "missing_fields": [],
        "extra_fields": [],
    }

    if expected_schema is None:
        expected_schema = {"type": "list_of_dicts", "required_keys": []}

    expected_type = expected_schema.get("type", "list_of_dicts")
    required_keys = expected_schema.get("required_keys", [])
    key_types = expected_schema.get("key_types", {})

    # Detect format
    if isinstance(data, list):
        result["original_format"] = "list_of_dicts"
        rows = data
    elif isinstance(data, dict):
        if expected_type == "list_of_dicts":
            # Convert flat dict to single-row list
            result["original_format"] = "flat"
            result["corrections"].append({
                "field": "_format",
                "issue": "converted_flat_dict_to_list",
                "original": "dict",
                "corrected": "list_of_dicts",
            })
            rows = [data]
        else:
            result["original_format"] = "flat"
            rows = [data]
    else:
        result["original_format"] = str(type(data).__name__)
        result["normalized"] = data
        return result

    # Normalize each row
    normalized_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        new_row = {}
        row_keys = set()
        for k, v in row.items():
            row_keys.add(k)
            # Check if value needs number parsing
            if k in key_types and key_types[k] in (int, float):
                parsed = _parse_number(v)
                if str(v).strip() != str(parsed) and v != parsed:
                    result["corrections"].append({
                        "field": k,
                        "issue": "parsed_number",
                        "original": str(v),
                        "corrected": parsed,
                    })
                new_row[k] = int(parsed) if key_types[k] == int else parsed
            else:
                new_row[k] = v
        normalized_rows.append(new_row)

        # Check for missing/extra fields (only on first row)
        if not result["missing_fields"] and not result["extra_fields"]:
            for rk in required_keys:
                if rk not in row_keys:
                    result["missing_fields"].append(rk)
            expected_all = set(required_keys)
            for ek in row_keys:
                if expected_all and ek not in expected_all:
                    result["extra_fields"].append(ek)

    if expected_type == "list_of_dicts":
        result["normalized"] = normalized_rows
    else:
        result["normalized"] = normalized_rows[0] if normalized_rows else {}

    return result


# ---------------------------------------------------------------------------
# 4. Schema Validator
# ---------------------------------------------------------------------------
def validate_schema(data, schema_spec):
    """
    Validate data against a schema specification.

    schema_spec keys:
        type: "dict" | "list_of_dicts"
        required_keys: list of required field names
        optional_keys: list of optional field names
        key_types: dict mapping field name -> expected type
        constraints: dict mapping field name -> {"min": N, "max": N}

    Returns dict with: valid, errors, warnings
    """
    result = {"valid": True, "errors": [], "warnings": []}

    expected_type = schema_spec.get("type", "dict")
    required_keys = schema_spec.get("required_keys", [])
    key_types = schema_spec.get("key_types", {})
    constraints = schema_spec.get("constraints", {})

    if expected_type == "list_of_dicts":
        if not isinstance(data, list):
            result["valid"] = False
            result["errors"].append(f"Expected list, got {type(data).__name__}")
            return result
        if len(data) == 0:
            result["warnings"].append("Empty list")
            return result
        # Validate first row as representative
        rows_to_check = [data[0]]
    elif expected_type == "dict":
        if not isinstance(data, dict):
            result["valid"] = False
            result["errors"].append(f"Expected dict, got {type(data).__name__}")
            return result
        rows_to_check = [data]
    else:
        rows_to_check = [data] if isinstance(data, dict) else data[:1]

    for row in rows_to_check:
        if not isinstance(row, dict):
            result["valid"] = False
            result["errors"].append(f"Expected dict row, got {type(row).__name__}")
            continue

        # Required keys
        for rk in required_keys:
            if rk not in row:
                result["valid"] = False
                result["errors"].append(f"Missing required key: '{rk}'")

        # Type checks
        for field, expected in key_types.items():
            if field in row and row[field] is not None:
                if not isinstance(row[field], expected):
                    result["warnings"].append(
                        f"Field '{field}': expected {expected.__name__}, "
                        f"got {type(row[field]).__name__}"
                    )

        # Constraint checks
        for field, cons in constraints.items():
            if field in row and isinstance(row[field], (int, float)):
                if "min" in cons and row[field] < cons["min"]:
                    result["warnings"].append(
                        f"Field '{field}': value {row[field]} below min {cons['min']}"
                    )
                if "max" in cons and row[field] > cons["max"]:
                    result["warnings"].append(
                        f"Field '{field}': value {row[field]} above max {cons['max']}"
                    )

    return result


# ---------------------------------------------------------------------------
# 5. Preflight Report
# ---------------------------------------------------------------------------
def preflight_report(inbox_path, skill_name, rules=None, schema_spec=None):
    """
    Run full preflight for a skill: scan inbox, match files, validate schema if
    data is provided.

    Returns consolidated status dict.
    """
    report = {
        "skill": skill_name,
        "status": "ok",
        "inbox_scan": None,
        "file_matches": None,
        "schema_validation": None,
        "corrections_made": [],
        "errors": [],
        "warnings": [],
    }

    # Scan inbox
    scan = scan_inbox(inbox_path)
    report["inbox_scan"] = {
        "total_files": scan["total_files"],
        "by_extension": {k: len(v) for k, v in scan["by_extension"].items()},
        "warnings": scan["warnings"],
    }
    report["warnings"].extend(scan["warnings"])

    # Match files
    matches = fuzzy_match_files(scan, rules)
    report["file_matches"] = {
        "matched_rules": {k: len(v) for k, v in matches["matches"].items()},
        "unmatched_files": matches["unmatched_files"],
        "unmatched_rules": matches["unmatched_rules"],
    }
    if matches["unmatched_rules"]:
        report["warnings"].append(
            f"No files found for: {', '.join(matches['unmatched_rules'])}"
        )

    # Set overall status
    if report["errors"]:
        report["status"] = "errors"
    elif report["warnings"]:
        report["status"] = "warnings"

    return report


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    inbox = sys.argv[1] if len(sys.argv) > 1 else "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/01_Inbox"
    skill = sys.argv[2] if len(sys.argv) > 2 else "generic"
    report = preflight_report(inbox, skill)
    print(json.dumps(report, indent=2))
