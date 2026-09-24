#!/usr/bin/env python3
"""auto-trends pre_flight — validates dependencies and paths."""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from pre_flight import scan_inbox

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_ROOT = os.path.dirname(SKILL_DIR)
PROJECT_ROOT = os.path.abspath(os.path.join(SKILLS_ROOT, '..', '..'))


def run():
    result = {
        "skill": "auto-trends",
        "status": "ok",
        "inbox_scan": None,
        "file_matches": None,
        "errors": [],
        "warnings": [],
    }

    # auto-trends doesn't read from 01_Inbox — it does web searches
    # Check that the PDF generator script exists
    generator = os.path.join(SKILL_DIR, "generate_trends_report.py")
    if not os.path.exists(generator):
        result["errors"].append("generate_trends_report.py not found")

    # Check logo (canonical brand assets path)
    logo_path = os.path.join(
        PROJECT_ROOT, "Resources", "brand-assets",
        "digital-cliq-logo-solid-1000px-wide.png",
    )
    if not os.path.exists(logo_path):
        result["errors"].append(f"DigitalCLIQ logo missing at canonical path: {logo_path}")

    # Check output directory
    reports_dir = os.path.join(PROJECT_ROOT, "outputs")
    if not os.path.isdir(reports_dir):
        result["warnings"].append(f"Reports directory not found: {reports_dir}")

    # Check a PDF render engine (Design-System pipeline: WeasyPrint, else
    # Chrome headless --print-to-pdf; reportlab is banned for this report)
    renderer_found = False
    try:
        import weasyprint  # noqa: F401
        renderer_found = True
    except ImportError:
        pass
    if not renderer_found:
        import shutil
        chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if os.path.exists(chrome) or shutil.which("google-chrome") or shutil.which("chromium"):
            renderer_found = True
    if renderer_found:
        result["inbox_scan"] = {"total_files": 0, "by_extension": {}, "warnings": []}
    else:
        result["errors"].append(
            "No PDF render engine: WeasyPrint not importable and Chrome not found")

    if result["errors"]:
        result["status"] = "errors"
    elif result["warnings"]:
        result["status"] = "warnings"

    return result


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] != "errors" else 1)
