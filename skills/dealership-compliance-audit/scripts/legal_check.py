#!/usr/bin/env python3
"""
legal_check.py — Stage 3: Legal compliance check reference module.

This module provides rule-loading utilities for Claude to use during Stage 3.
The actual legal analysis is performed by Claude (AI judgment required),
but this module loads and indexes the hard rules and brand guidelines
so Claude can systematically evaluate each rule.

Claude's Stage 3 workflow:
1. Load hard rules via load_hard_rules()
2. Load brand guidelines via load_brand_guidelines()
3. For each rule, evaluate the website content observed in Stage 1
4. For hard rules: binary pass/fail → "critical" findings
5. For judgment criteria: AI assessment → "warning" or "advisory" findings
6. Merge with Stage 2 brand findings into unified findings list
"""

import json
import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
RULES_DIR = SKILL_DIR / "rules"
BRANDS_DIR = SKILL_DIR / "brands"


def load_hard_rules():
    """Load California hard rules from ca_hard_rules.json."""
    rules_path = RULES_DIR / "ca_hard_rules.json"
    with open(rules_path, "r") as f:
        data = json.load(f)
    return data["rules"]


def load_brand_guidelines(brand):
    """Load brand-specific guidelines JSON.

    Args:
        brand: 'bmw', 'nissan', or 'cdjr'
    """
    brand_map = {
        "bmw": "bmw_guidelines.json",
        "nissan": "nissan_guidelines.json",
        "cdjr": "cdjr_guidelines.json",
        "stellantis": "cdjr_guidelines.json",
    }

    filename = brand_map.get(brand.lower())
    if not filename:
        raise ValueError(f"Unknown brand: {brand}. Valid: {list(brand_map.keys())}")

    brand_path = BRANDS_DIR / filename
    if not brand_path.exists():
        return []  # Brand guidelines not yet built

    with open(brand_path, "r") as f:
        data = json.load(f)
    return data.get("checks", [])


def load_judgment_criteria():
    """Load the AI judgment criteria markdown file as text."""
    criteria_path = RULES_DIR / "ca_judgment_criteria.md"
    with open(criteria_path, "r") as f:
        return f.read()


def get_rules_for_page_type(rules, page_type):
    """Filter rules relevant to a specific page type.

    Args:
        rules: List of rule dicts from ca_hard_rules.json
        page_type: 'homepage', 'vlp', 'vdp', 'specials', 'finance', 'lease', 'used', 'cpo', 'general'

    Returns:
        List of rules particularly relevant to that page type.
    """
    # Map page types to relevant rule categories
    page_category_map = {
        "homepage": ["Dealer Identity", "Price Advertising", "Sale / Savings Claims"],
        "vlp": ["Price Advertising", "Vehicle Description", "Vehicle Pictures", "Dealer Identity"],
        "vdp": ["Price Advertising", "Vehicle Description", "Vehicle Pictures", "Dealer Identity",
                 "Disclosures", "New vs Used"],
        "specials": ["Price Advertising", "Sale / Savings Claims", "Disclosures",
                     "Credit / Reg Z", "Lease / Reg M", "Dealer Identity"],
        "finance": ["Credit / Reg Z", "Price Advertising", "Disclosures", "Dealer Identity"],
        "lease": ["Lease / Reg M", "Price Advertising", "Disclosures", "Dealer Identity"],
        "used": ["New vs Used", "Certified Pre-Owned", "Vehicle History",
                 "Price Advertising", "Dealer Identity", "Vehicle Description"],
        "cpo": ["Certified Pre-Owned", "New vs Used", "Vehicle History",
                "Price Advertising", "Dealer Identity"],
        "general": [],  # All rules apply
    }

    relevant_categories = page_category_map.get(page_type, [])

    if not relevant_categories:
        return rules  # Return all rules for unknown page types

    # Always include Dealer Identity for any page
    if "Dealer Identity" not in relevant_categories:
        relevant_categories.append("Dealer Identity")

    return [r for r in rules if r.get("category") in relevant_categories]


def check_text_against_patterns(text, rule):
    """Check if text matches any trigger patterns for a rule.

    Args:
        text: Page text content to check
        rule: Rule dict with 'trigger_patterns' list

    Returns:
        List of matched patterns (empty if no matches)
    """
    matches = []
    patterns = rule.get("trigger_patterns", [])

    if not patterns:
        return matches  # Rule has no text patterns (requires manual review)

    for pattern in patterns:
        try:
            if re.search(pattern, text, re.IGNORECASE):
                matches.append(pattern)
        except re.error:
            # Invalid regex, try as literal
            if pattern.lower() in text.lower():
                matches.append(pattern)

    return matches


def build_rule_checklist(brand):
    """Build a comprehensive checklist combining CA law + brand rules.

    Returns a list of dicts with:
      - rule_id, title, category, description, severity, source_type
    """
    checklist = []

    # Add CA hard rules
    for rule in load_hard_rules():
        checklist.append({
            "rule_id": rule["id"],
            "title": rule["title"],
            "category": rule["category"],
            "description": rule["description"],
            "severity": rule["severity"],
            "source_type": "ca_law",
            "statute": rule.get("statute", ""),
        })

    # Add brand guidelines
    for check in load_brand_guidelines(brand):
        if check.get("website_applicable", True):
            checklist.append({
                "rule_id": check["id"],
                "title": check["title"],
                "category": check["category"],
                "description": check["description"],
                "severity": check["severity"],
                "source_type": "brand_guideline",
                "statute": "",
            })

    return checklist


def print_checklist_summary(brand):
    """Print a summary of all rules that will be checked."""
    checklist = build_rule_checklist(brand)
    ca_count = sum(1 for c in checklist if c["source_type"] == "ca_law")
    brand_count = sum(1 for c in checklist if c["source_type"] == "brand_guideline")

    print(f"\nCompliance Checklist for {brand.upper()}")
    print(f"{'='*50}")
    print(f"CA Law Rules:      {ca_count}")
    print(f"Brand Guidelines:  {brand_count}")
    print(f"Total Checks:      {len(checklist)}")
    print()

    categories = {}
    for c in checklist:
        cat = c["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(c)

    for cat, items in sorted(categories.items()):
        print(f"\n  {cat} ({len(items)} rules)")
        for item in items:
            marker = "LAW" if item["source_type"] == "ca_law" else "OEM"
            print(f"    [{marker}] {item['rule_id']}: {item['title']}")


if __name__ == "__main__":
    import sys
    brand = sys.argv[1] if len(sys.argv) > 1 else "bmw"
    print_checklist_summary(brand)
