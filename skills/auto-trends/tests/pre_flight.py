#!/usr/bin/env python3
"""auto-trends pre_flight: validates dependencies and paths.

The vault root comes from env DIGITALCLIQ_VAULT_ROOT (default: Drew's vault),
not from this file's location, so the check works from the installed
skills-plugin copy too. The render engine is Chrome headless --print-to-pdf;
WeasyPrint counts only when AUTO_TRENDS_ENGINE=weasyprint asks for it.
"""

import json
import os
import shutil
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.environ.get("DIGITALCLIQ_VAULT_ROOT",
                              "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ")
FONT_FILES = ["Dosis-Medium.ttf", "Dosis-SemiBold.ttf", "Dosis-Bold.ttf",
              "Dosis-ExtraBold.ttf", "Roboto-Slab-Regular.ttf", "Roboto-Slab-Bold.ttf"]


def run():
    result = {
        "skill": "auto-trends",
        "status": "ok",
        "inbox_scan": None,
        "file_matches": None,
        "errors": [],
        "warnings": [],
    }

    # auto-trends doesn't read from 01_Inbox; it does web searches.
    # Check that the generator scripts exist
    for script in ("generate_trends_report.py", "generate_blog_assets.py", "validate_claims.py"):
        if not os.path.exists(os.path.join(SKILL_DIR, script)):
            result["errors"].append(f"{script} not found in {SKILL_DIR}")

    # Check logos (canonical brand assets paths; the generator needs both)
    for logo_name in ("digital-cliq-logo-solid-1000px-wide.png",
                      "classic-digital-cliq-logo-solid-1000px-wide copy.png"):
        logo_path = os.path.join(PROJECT_ROOT, "Resources", "brand-assets", logo_name)
        if not os.path.exists(logo_path):
            result["errors"].append(f"DigitalCLIQ logo missing at canonical path: {logo_path}")

    # Brand fonts: the generator hard-fails without them (a vault sync has
    # emptied this folder before)
    font_dir = os.path.join(PROJECT_ROOT, "Resources", "brand-assets", "fonts")
    missing_fonts = [f for f in FONT_FILES if not os.path.exists(os.path.join(font_dir, f))]
    if missing_fonts:
        result["errors"].append(f"Brand fonts missing from {font_dir}: {missing_fonts}")

    # Check output directory
    reports_dir = os.path.join(PROJECT_ROOT, "outputs")
    if not os.path.isdir(reports_dir):
        result["warnings"].append(f"Reports directory not found: {reports_dir}")

    # Check the PDF render engine (Design-System pipeline; reportlab is banned
    # for this report). WeasyPrint raises OSError, not ImportError, when its
    # system libraries are missing, so catch everything.
    engine = os.environ.get("AUTO_TRENDS_ENGINE", "chrome").strip().lower() or "chrome"
    renderer_found = False
    if engine == "weasyprint":
        try:
            import weasyprint  # noqa: F401
            renderer_found = True
        except Exception as e:  # noqa: BLE001
            result["errors"].append(f"AUTO_TRENDS_ENGINE=weasyprint but it will not load: {e}")
    else:
        chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if os.path.exists(chrome) or shutil.which("google-chrome") or shutil.which("chromium"):
            renderer_found = True
        else:
            result["errors"].append("No PDF render engine: Chrome not found")
    if renderer_found:
        result["inbox_scan"] = {"total_files": 0, "by_extension": {}, "warnings": []}

    if result["errors"]:
        result["status"] = "errors"
    elif result["warnings"]:
        result["status"] = "warnings"

    return result


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] != "errors" else 1)
