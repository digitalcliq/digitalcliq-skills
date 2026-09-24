#!/usr/bin/env python3
"""score-leads pre_flight — thin wrapper around shared pre_flight module."""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from pre_flight import preflight_report

SCORE_LEADS_SCHEMA = {
    "type": "list_of_dicts",
    "required_keys": ["source", "leads", "contact", "contact_pct", "appts",
                      "appts_pct", "shows", "shows_pct", "sales", "sales_pct"],
    "key_types": {
        "source": str, "leads": int, "sales": int,
        "contact_pct": float, "appts_pct": float, "shows_pct": float, "sales_pct": float,
    },
}

SCORE_LEADS_RULES = [
    {"label": "CRM Lead Report",
     "keywords": ["sterling", "nissan", "mcpeek", "j star", "jstar"],
     "extensions": [".csv", ".xlsx", ".xls", ".pdf"]},
]

INBOX_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '01_Inbox')


def run():
    return preflight_report(
        inbox_path=os.path.abspath(INBOX_PATH),
        skill_name="score-leads",
        rules=SCORE_LEADS_RULES,
        schema_spec=SCORE_LEADS_SCHEMA,
    )


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] != "errors" else 1)
