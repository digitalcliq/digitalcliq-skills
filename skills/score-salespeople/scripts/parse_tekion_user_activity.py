"""Tekion 'User Activity Report - By Sales Rep' adapter.

This is the aggregated/summary report shape (one row per salesperson, totals
computed by Tekion). Use this when lead-level exports aren't available.

The report typically includes a totals row at the top (empty Salesperson
column) and may include an 'Other' bucket for unattributed leads. Both are
returned to the caller so they can be surfaced separately rather than scored.

Column name candidates are tolerant — Tekion column headers vary slightly
across exports. Extend the candidate lists if a real export has different
names.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SKILL_ROOT = _HERE.parent
sys.path.insert(0, str(_SKILL_ROOT))

from schemas.salesperson_summary import SalespersonSummary  # noqa: E402


COLUMN_MAP = {
    "name":           ["Salesperson", "User", "Sales Rep", "Name"],
    "good_leads":     ["Total Good Leads", "Good Leads"],
    "total_tasks":    ["Total Tasks", "Tasks"],
    "completed_tasks": ["Completed Tasks"],
    "active_tasks":   ["Active Tasks"],
    "overdue":        ["Tasks Overdue", "Overdue Tasks"],
    "calls_out":      ["Total Calls Out", "Calls Out", "Outbound Calls"],
    "calls_contacted": ["Calls Out Contacted", "Calls Contacted", "Connected Calls"],
    "texts":          ["User Texts Sent", "Texts Sent", "Outbound Texts"],
    "emails":         ["User Emails Sent", "Emails Sent", "Outbound Emails"],
    "videos_sent":    ["Videos Sent"],
    "video_leads":    ["Video Sent Leads", "Leads Receiving Video"],
    "appts_created":  ["Appointments Created", "Appts Created"],
    "appts_scheduled": ["Appointments Scheduled", "Appts Scheduled"],
    "appts_confirmed": ["Appointments Confirmed", "Appts Confirmed"],
    "appts_shown":    ["Appointments Scheduled Shown", "Appointments Shown", "Appts Shown"],
    "sold":           ["Sold In Time Period", "Sold", "Sales"],
}


def _resolve(row: dict, candidates: list[str]) -> str | None:
    for name in candidates:
        if name in row and row[name] not in (None, ""):
            return name
    return None


def _get(row: dict, key: str) -> str:
    name = _resolve(row, COLUMN_MAP[key])
    return row[name] if name else ""


def _num(s) -> float:
    if s in (None, ""):
        return 0.0
    s = str(s).replace(",", "").replace("%", "").replace("$", "").strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_tekion_user_activity(csv_path: str) -> dict:
    """Parse a Tekion User Activity Report.

    Returns:
        {
          "totals":          SalespersonSummary | None  (the first totals row),
          "salespeople":     list[SalespersonSummary]   (everyone else, unclassified),
        }

    Classification (salesperson vs BDC vs placeholder vs other_bucket) happens
    later in the scoring engine, not here.
    """
    totals: SalespersonSummary | None = None
    salespeople: list[SalespersonSummary] = []

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for raw_row in reader:
            name = str(_get(raw_row, "name")).strip()

            summary = SalespersonSummary(
                name=name,
                good_leads=int(_num(_get(raw_row, "good_leads"))),
                appointments_created=int(_num(_get(raw_row, "appts_created"))),
                appointments_scheduled=int(_num(_get(raw_row, "appts_scheduled"))),
                appointments_confirmed=int(_num(_get(raw_row, "appts_confirmed"))),
                appointments_shown=int(_num(_get(raw_row, "appts_shown"))),
                sold=_num(_get(raw_row, "sold")),
                total_tasks=int(_num(_get(raw_row, "total_tasks"))),
                completed_tasks=int(_num(_get(raw_row, "completed_tasks"))),
                active_tasks=int(_num(_get(raw_row, "active_tasks"))),
                tasks_overdue=int(_num(_get(raw_row, "overdue"))),
                calls_out=int(_num(_get(raw_row, "calls_out"))),
                calls_out_contacted=int(_num(_get(raw_row, "calls_contacted"))),
                texts_sent=int(_num(_get(raw_row, "texts"))),
                emails_sent=int(_num(_get(raw_row, "emails"))),
                videos_sent=int(_num(_get(raw_row, "videos_sent"))),
                video_sent_leads=int(_num(_get(raw_row, "video_leads"))),
            )

            if not name:
                # Empty Salesperson cell = the totals row
                if totals is None:
                    summary.name = "TOTALS"
                    summary.role = "placeholder"
                    summary.role_reason = "aggregate totals row"
                    totals = summary
                continue

            salespeople.append(summary)

    return {"totals": totals, "salespeople": salespeople}
