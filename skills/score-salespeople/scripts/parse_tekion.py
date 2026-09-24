"""Tekion CSV adapter — translates Tekion exports into list[Lead].

STATUS: v1 STUB. Column names below are best-guesses based on common Tekion
report exports. Drew needs to validate against a real McPeek export and
adjust the COLUMN_MAP + parsing logic accordingly.

Tekion typically splits lead data and activity data into two files:
  - Lead export: one row per lead with status fields
  - Activity log: one row per touch (call, text, email)

This parser accepts both and joins on lead_id.
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SKILL_ROOT = _HERE.parent
sys.path.insert(0, str(_SKILL_ROOT))

from schemas.normalized_lead import (  # noqa: E402
    Activity, ActivityType, Appointment, Deal, Lead,
)


# ── Column mapping (CONFIRM against real Tekion export) ──────────────

LEAD_COLUMN_MAP = {
    # canonical_name: [list of acceptable Tekion column header strings]
    "lead_id":           ["Lead ID", "Lead Number", "LeadId", "ID"],
    "created":           ["Lead Created Date", "Created On", "Created Date"],
    "source":            ["Lead Source", "Source", "Source Name"],
    "lead_type":         ["Lead Type", "Type", "Form Type"],

    "assigned_to":       ["Assigned To", "Owner", "Current Owner", "Salesperson"],
    "assignment_date":   ["Assignment Date", "Assigned On", "Assigned Date"],

    "appt_date":         ["Appointment Date", "Appt Date", "Scheduled For"],
    "appt_status":       ["Appointment Status", "Appt Status"],
    "appt_set_by":       ["Appointment Set By", "Appt Set By", "Set By"],
    "appt_set_date":     ["Appointment Set Date", "Appt Set On", "Set On"],
    "appt_show_date":    ["Appointment Show Date", "Show Date", "Showed On"],

    "sale_date":         ["Sale Date", "Delivered Date", "Sold Date"],
    "sold_by":           ["Sold By", "Deal Salesperson", "Closer"],
    "vehicle_condition": ["New/Used", "Stock Type", "Vehicle Type", "Condition"],
    "gross":             ["Total Gross", "Front Gross", "Gross Profit", "Gross"],

    "test_drive":        ["Test Drive", "Test Drove", "Test-Drive Taken"],
    "test_drive_date":   ["Test Drive Date", "Test Drive Timestamp"],
}

ACTIVITY_COLUMN_MAP = {
    "lead_id":         ["Lead ID", "Lead Number", "LeadId"],
    "timestamp":       ["Activity Date", "Activity Timestamp", "Date/Time", "Timestamp"],
    "activity_type":   ["Activity Type", "Type", "Communication Type"],
    "direction":       ["Direction", "Inbound/Outbound"],
    "salesperson":     ["Salesperson", "Performed By", "User"],
    "is_auto":         ["Is Auto-Generated", "Auto", "System Generated"],
}


# ── Helpers ──────────────────────────────────────────────────────────

def _resolve_column(row: dict, candidates: list[str]) -> str | None:
    for name in candidates:
        if name in row and row[name] not in (None, ""):
            return name
    return None


def _get(row: dict, candidates: list[str], default=""):
    name = _resolve_column(row, candidates)
    return row[name] if name else default


def _parse_dt(s: str) -> datetime | None:
    """Try a few common date formats Tekion may use. Extend as needed."""
    if not s:
        return None
    s = s.strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parse_bool(v) -> bool:
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in {"1", "true", "t", "yes", "y"}


def _classify_activity_type(activity_type_str: str, direction_str: str) -> ActivityType | None:
    """Map Tekion's activity_type + direction to our ActivityType enum."""
    if not activity_type_str:
        return None
    t = activity_type_str.lower()
    d = (direction_str or "").lower()

    is_inbound = "inbound" in d or "in" == d.strip()
    is_outbound = "outbound" in d or "out" == d.strip()

    if "call" in t or "phone" in t:
        return ActivityType.INBOUND_CALL if is_inbound else ActivityType.OUTBOUND_CALL
    if "text" in t or "sms" in t:
        return ActivityType.INBOUND_TEXT if is_inbound else ActivityType.OUTBOUND_TEXT
    if "email" in t or "mail" in t:
        return ActivityType.INBOUND_EMAIL if is_inbound else ActivityType.OUTBOUND_EMAIL
    # Default to outbound text if we can't classify but direction is set
    if is_outbound:
        return ActivityType.OUTBOUND_TEXT
    if is_inbound:
        return ActivityType.INBOUND_TEXT
    return None


def _normalize_appt_status(s: str) -> str:
    """Map Tekion's appointment status strings to our canonical Literal values."""
    if not s:
        return "set"
    s_lower = s.lower().strip()
    if "no" in s_lower and "show" in s_lower:
        return "no_show"
    if "cancel" in s_lower:
        return "cancelled"
    if "show" in s_lower or "shown" in s_lower or "arrived" in s_lower:
        return "showed"
    if "confirm" in s_lower:
        return "confirmed"
    return "set"


def _normalize_vehicle_type(s: str) -> str:
    if s and "used" in s.lower():
        return "used"
    return "new"


def _to_float(s) -> float | None:
    if s in (None, ""):
        return None
    try:
        return float(str(s).replace("$", "").replace(",", ""))
    except (ValueError, TypeError):
        return None


# ── Public API ────────────────────────────────────────────────────────

def parse_tekion(lead_csv_path: str, activity_csv_path: str | None = None) -> list[Lead]:
    """Parse Tekion exports into a list of normalized Lead objects.

    Args:
        lead_csv_path:     Path to Tekion lead export CSV.
        activity_csv_path: Optional path to Tekion activity-log CSV. If
                           provided, activities are joined onto leads by ID.

    Returns:
        list[Lead] ready to feed into scoring_engine.score_all().
    """
    leads_by_id: dict[str, Lead] = {}

    # ── Pass 1: leads ────────────────────────────────────────────────
    with open(lead_csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            lead_id = str(_get(raw, LEAD_COLUMN_MAP["lead_id"])).strip()
            if not lead_id:
                continue
            created = _parse_dt(str(_get(raw, LEAD_COLUMN_MAP["created"])))
            if not created:
                # If we can't parse the creation time, skip — every metric needs it.
                continue

            source = str(_get(raw, LEAD_COLUMN_MAP["source"]))
            lead_type = str(_get(raw, LEAD_COLUMN_MAP["lead_type"])).lower()
            is_credit_app = "credit" in lead_type or "finance app" in lead_type

            assigned_to = str(_get(raw, LEAD_COLUMN_MAP["assigned_to"])).strip()
            assignment_date = _parse_dt(str(_get(raw, LEAD_COLUMN_MAP["assignment_date"]))) or created
            assignment_history = [(assignment_date, assigned_to)] if assigned_to else []

            # Appointment (if present)
            appt_date = _parse_dt(str(_get(raw, LEAD_COLUMN_MAP["appt_date"])))
            appt_set_date = _parse_dt(str(_get(raw, LEAD_COLUMN_MAP["appt_set_date"])))
            appt_set_by = str(_get(raw, LEAD_COLUMN_MAP["appt_set_by"])).strip()
            appt_status_raw = str(_get(raw, LEAD_COLUMN_MAP["appt_status"]))
            appt_show_date = _parse_dt(str(_get(raw, LEAD_COLUMN_MAP["appt_show_date"])))

            appointment = None
            if appt_date or appt_set_by:
                appointment = Appointment(
                    set_timestamp=appt_set_date or appt_date or created,
                    set_by_salesperson_id=appt_set_by or assigned_to,
                    scheduled_for=appt_date or appt_set_date or created,
                    status=_normalize_appt_status(appt_status_raw),
                    show_timestamp=appt_show_date,
                )

            # Deal (if present)
            sale_date = _parse_dt(str(_get(raw, LEAD_COLUMN_MAP["sale_date"])))
            sold_by = str(_get(raw, LEAD_COLUMN_MAP["sold_by"])).strip()
            deal = None
            if sale_date or sold_by:
                deal = Deal(
                    salesperson_id=sold_by or assigned_to,
                    vehicle_type=_normalize_vehicle_type(str(_get(raw, LEAD_COLUMN_MAP["vehicle_condition"]))),
                    sold_timestamp=sale_date,
                    written_timestamp=None,
                    gross=_to_float(_get(raw, LEAD_COLUMN_MAP["gross"])),
                )

            test_drive_flag = _parse_bool(_get(raw, LEAD_COLUMN_MAP["test_drive"]))
            test_drive_date = _parse_dt(str(_get(raw, LEAD_COLUMN_MAP["test_drive_date"])))

            leads_by_id[lead_id] = Lead(
                lead_id=lead_id,
                created_timestamp=created,
                source=source,
                is_credit_app=is_credit_app,
                assignment_history=assignment_history,
                test_drive_taken=test_drive_flag or (test_drive_date is not None),
                test_drive_timestamp=test_drive_date,
                appointment=appointment,
                deal=deal,
                activities=[],
            )

    # ── Pass 2: activities (optional) ────────────────────────────────
    if activity_csv_path:
        with open(activity_csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for raw in reader:
                lead_id = str(_get(raw, ACTIVITY_COLUMN_MAP["lead_id"])).strip()
                if lead_id not in leads_by_id:
                    continue
                ts = _parse_dt(str(_get(raw, ACTIVITY_COLUMN_MAP["timestamp"])))
                if not ts:
                    continue
                atype = _classify_activity_type(
                    str(_get(raw, ACTIVITY_COLUMN_MAP["activity_type"])),
                    str(_get(raw, ACTIVITY_COLUMN_MAP["direction"])),
                )
                if not atype:
                    continue
                sp = str(_get(raw, ACTIVITY_COLUMN_MAP["salesperson"])).strip()
                is_auto = _parse_bool(_get(raw, ACTIVITY_COLUMN_MAP["is_auto"]))
                leads_by_id[lead_id].activities.append(
                    Activity(timestamp=ts, type=atype, salesperson_id=sp, is_auto_response=is_auto)
                )

    # Sort activities per lead by timestamp
    for lead in leads_by_id.values():
        lead.activities.sort(key=lambda a: a.timestamp)

    return list(leads_by_id.values())
