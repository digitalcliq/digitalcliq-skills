#!/usr/bin/env python3
"""dealership-forecast pre_flight — thin wrapper around shared pre_flight module."""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from pre_flight import preflight_report

FORECAST_RULES = [
    {"label": "Sterling BMW / MomentumCRM",
     "keywords": ["sterling"], "extensions": [".csv", ".xlsx"]},
    {"label": "Nissan of Irvine / VinSolutions",
     "keywords": ["nissan"], "extensions": [".csv", ".xlsx"]},
    {"label": "McPeek CDJR / Tekion",
     "keywords": ["mcpeek"], "extensions": [".csv", ".xlsx"]},
    {"label": "J Star / DealerSocket",
     "keywords": ["j star", "jstar", "j_star"], "extensions": [".csv", ".xlsx"]},
]

INBOX_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '01_Inbox')


def run():
    return preflight_report(
        inbox_path=os.path.abspath(INBOX_PATH),
        skill_name="dealership-forecast",
        rules=FORECAST_RULES,
    )


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] != "errors" else 1)
