#!/usr/bin/env python3
"""
parse_brand_check.py — Stage 2: Parse brand-check narrative into structured findings.

This module provides the schema and helper functions for Claude to use when
converting its /brand-check narrative output into structured JSON findings.

Claude performs the actual parsing (it generated the narrative, so it can
structure it). This module defines the output format and validation.
"""

import json
from datetime import datetime

# Valid severity levels
SEVERITIES = {"critical", "warning", "advisory"}

# Valid finding sources
SOURCES = {"brand_check", "legal_check"}

# Finding schema
FINDING_SCHEMA = {
    "page_url": str,        # URL of the page where the issue was found
    "finding_type": str,    # "brand_violation", "legal_violation", "legal_warning", "legal_advisory"
    "rule_id": str,         # Rule ID from brand guidelines or ca_hard_rules (e.g., "BMW-LOGO-001", "CA-PRICE-001")
    "title": str,           # Short description of the finding
    "quote": str,           # Specific text/element from the page that triggered the finding
    "severity": str,        # "critical", "warning", or "advisory"
    "source": str,          # "brand_check" or "legal_check"
    "statute": str,         # Legal citation if applicable (e.g., "VC §11713.1(e)")
    "recommendation": str,  # Recommended fix
}


def validate_finding(finding):
    """Validate a single finding dict against the schema."""
    errors = []

    # Required fields
    for field in ["page_url", "finding_type", "rule_id", "title", "severity", "source"]:
        if field not in finding:
            errors.append(f"Missing required field: {field}")
        elif not isinstance(finding[field], str) or not finding[field].strip():
            errors.append(f"Field '{field}' must be a non-empty string")

    # Severity validation
    if finding.get("severity") and finding["severity"] not in SEVERITIES:
        errors.append(f"Invalid severity '{finding['severity']}'. Must be one of: {SEVERITIES}")

    # Source validation
    if finding.get("source") and finding["source"] not in SOURCES:
        errors.append(f"Invalid source '{finding['source']}'. Must be one of: {SOURCES}")

    return errors


def validate_findings(findings):
    """Validate a list of findings. Returns (is_valid, errors_list)."""
    if not isinstance(findings, list):
        return False, ["Findings must be a list"]

    all_errors = []
    for i, finding in enumerate(findings):
        errors = validate_finding(finding)
        if errors:
            all_errors.extend([f"Finding [{i}]: {e}" for e in errors])

    return len(all_errors) == 0, all_errors


def create_finding(page_url, finding_type, rule_id, title, severity,
                   source="brand_check", quote="", statute="", recommendation=""):
    """Helper to create a properly formatted finding dict."""
    return {
        "page_url": page_url,
        "finding_type": finding_type,
        "rule_id": rule_id,
        "title": title,
        "quote": quote,
        "severity": severity,
        "source": source,
        "statute": statute,
        "recommendation": recommendation,
    }


def save_findings(findings, output_path):
    """Save findings list to JSON file."""
    is_valid, errors = validate_findings(findings)
    if not is_valid:
        raise ValueError(f"Invalid findings:\n" + "\n".join(errors))

    with open(output_path, "w") as f:
        json.dump(findings, f, indent=2)

    return output_path


def load_findings(input_path):
    """Load and validate findings from JSON file."""
    with open(input_path, "r") as f:
        findings = json.load(f)

    is_valid, errors = validate_findings(findings)
    if not is_valid:
        raise ValueError(f"Invalid findings in {input_path}:\n" + "\n".join(errors))

    return findings


def summary_stats(findings):
    """Return summary counts by severity and source."""
    stats = {
        "total": len(findings),
        "by_severity": {"critical": 0, "warning": 0, "advisory": 0},
        "by_source": {"brand_check": 0, "legal_check": 0},
    }
    for f in findings:
        sev = f.get("severity", "")
        src = f.get("source", "")
        if sev in stats["by_severity"]:
            stats["by_severity"][sev] += 1
        if src in stats["by_source"]:
            stats["by_source"][src] += 1
    return stats
