#!/usr/bin/env python3
"""
DigitalCLIQ Skill Tests — Shared Constants
Paths, CRM mappings, and brand aliases used across all test files.
"""

import os

PROJECT_ROOT = "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ"
SKILLS_ROOT = os.path.join(PROJECT_ROOT, ".claude", "skills")
INBOX_PATH = os.path.join(PROJECT_ROOT, "01_Inbox")
OUTPUTS_PATH = os.path.join(PROJECT_ROOT, "outputs")
REPORTS_PATH = os.path.join(PROJECT_ROOT, "outputs")
PYTHON = "/usr/bin/python3"
PDFTOTEXT = "/opt/homebrew/bin/pdftotext"

# DigitalCLIQ branding — canonical logo lives in Resources/brand-assets
LOGO_PATH = os.path.join(
    PROJECT_ROOT, "Resources", "brand-assets",
    "digital-cliq-logo-solid-1000px-wide.png",
)
# Kept as a list for backward compatibility with test helpers that iterate
LOGO_PATHS = [LOGO_PATH]

CRM_CLIENT_MAP = {
    "momentum":    {"client": "Sterling BMW",      "keywords": ["sterling"]},
    "vinsolutions": {"client": "Nissan of Irvine", "keywords": ["nissan"]},
    "tekion":      {"client": "McPeek CDJR",       "keywords": ["mcpeek"]},
    "dealersocket": {"client": "J Star CDJR",      "keywords": ["j star", "jstar", "j_star"]},
}

BRAND_ALIASES = {
    "bmw": "bmw",
    "nissan": "nissan",
    "stellantis": "stellantis",
    "cdjr": "stellantis",
    "chrysler": "stellantis",
    "dodge": "stellantis",
    "jeep": "stellantis",
    "ram": "stellantis",
    "fiat": "stellantis",
}

SKILL_NAMES = [
    "score-leads",
    "dealership-forecast",
    "brand-check",
    "morning-coffee",
    "auto-trends",
    "monthly-leasing",
]


def find_logo():
    """Return the first existing logo path, or None."""
    for p in LOGO_PATHS:
        if os.path.exists(p):
            return p
    return None
