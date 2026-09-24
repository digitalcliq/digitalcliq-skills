#!/usr/bin/env python3
"""brand-check pre_flight — validates brand guideline files exist."""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from pre_flight import preflight_report

BRAND_CHECK_RULES = [
    {"label": "Brand Guidelines",
     "keywords": ["bmw", "nissan", "stellantis"],
     "extensions": [".md"]},
]

# brand-check reads from brands/ dir, not 01_Inbox
BRANDS_DIR = os.path.join(os.path.dirname(__file__), '..', 'brands')


def run():
    result = preflight_report(
        inbox_path=os.path.abspath(BRANDS_DIR),
        skill_name="brand-check",
        rules=BRAND_CHECK_RULES,
    )
    return result


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] != "errors" else 1)
