#!/usr/bin/env python3
"""morning-coffee pre_flight — thin wrapper around shared pre_flight module."""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from pre_flight import preflight_report

COFFEE_RULES = [
    {"label": "Sterling BMW / MomentumCRM",
     "keywords": ["sterling"], "extensions": [".csv", ".xlsx", ".pdf"]},
    {"label": "McPeek CDJR / Tekion",
     "keywords": ["mcpeek"], "extensions": [".csv", ".xlsx"]},
    {"label": "Nissan of Irvine / VinSolutions",
     "keywords": ["nissan"], "extensions": [".csv", ".xlsx"]},
]

INBOX_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '01_Inbox')


def run():
    return preflight_report(
        inbox_path=os.path.abspath(INBOX_PATH),
        skill_name="morning-coffee",
        rules=COFFEE_RULES,
    )


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] != "errors" else 1)
