"""CRM-agnostic scoring engine for salesperson performance.

Two pipelines:

  1. Per-lead pipeline (score_all):
     Operates on list[Lead] from a lead-level CRM export with timestamps.
     Used when the CRM provides per-lead activity (Tekion lead+activity export,
     VINSolutions export). Computes response time and lead-level attribution.

  2. Aggregated pipeline (score_aggregated):
     Operates on list[SalespersonSummary] from a pre-rolled Tekion 'User
     Activity Report - By Sales Rep'. Adds 6 process/effort factors that the
     per-lead pipeline can't see. No response time (not in the report).

Both produce the same result shape so the Excel builder can render either.
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SKILL_ROOT = _HERE.parent
sys.path.insert(0, str(_SKILL_ROOT))

from schemas.normalized_lead import Lead, ActivityType  # noqa: E402
from schemas.salesperson_summary import SalespersonSummary  # noqa: E402


# ── Weights ───────────────────────────────────────────────────────────

PER_LEAD_WEIGHTS = {
    "sale_conversion": 0.40,
    "show_rate": 0.20,
    "sales_volume": 0.15,
    "set_rate": 0.15,
    "response_time": 0.10,
}

AGGREGATED_WEIGHTS = {
    "sale_conversion":    0.25,
    "set_rate":           0.12,
    "show_rate":          0.12,
    "sales_volume":       0.10,
    "task_completion":    0.10,
    "activity_per_lead":  0.08,
    "call_connection":    0.08,
    "confirmation_rate":  0.08,
    "tasks_overdue":      0.04,  # inverse-normalized
    "video_adoption":     0.03,
}

MIN_LEAD_VOLUME = 25
DEFAULT_PERIOD_DAYS = 30


# ── Per-lead pipeline (unchanged) ─────────────────────────────────────

def filter_period(leads: list[Lead], days: int = DEFAULT_PERIOD_DAYS,
                  end_date: datetime | None = None) -> list[Lead]:
    end_date = end_date or datetime.now()
    cutoff = end_date - timedelta(days=days)
    return [l for l in leads if cutoff <= l.created_timestamp <= end_date]


def exclude_credit_apps(leads: list[Lead]) -> list[Lead]:
    return [l for l in leads if not l.is_credit_app]


def attribute_leads_to_salespeople(leads: list[Lead]) -> dict[str, dict]:
    buckets: dict[str, dict] = {}

    def ensure(sp_id: str) -> dict:
        if sp_id not in buckets:
            buckets[sp_id] = {
                "leads_owned_at_creation": [],
                "appointments_set": [],
                "deals_closed": [],
            }
        return buckets[sp_id]

    for lead in leads:
        if not lead.assignment_history:
            continue
        initial_owner = lead.initial_owner
        if initial_owner:
            ensure(initial_owner)["leads_owned_at_creation"].append(lead)
        if lead.appointment and lead.appointment.set_by_salesperson_id:
            ensure(lead.appointment.set_by_salesperson_id)["appointments_set"].append(lead)
        if lead.deal and lead.deal.sold_timestamp and lead.deal.salesperson_id:
            ensure(lead.deal.salesperson_id)["deals_closed"].append(lead)

    return buckets


def _first_response_seconds(lead: Lead) -> float | None:
    candidates = [
        a.timestamp for a in lead.activities
        if a.type in (ActivityType.OUTBOUND_CALL,
                       ActivityType.OUTBOUND_TEXT,
                       ActivityType.OUTBOUND_EMAIL)
        and not a.is_auto_response
        and a.timestamp >= lead.created_timestamp
    ]
    if not candidates:
        return None
    return (min(candidates) - lead.created_timestamp).total_seconds()


def compute_raw_metrics(buckets: dict[str, dict]) -> dict[str, dict]:
    metrics: dict[str, dict] = {}
    for sp_id, b in buckets.items():
        leads_owned = b["leads_owned_at_creation"]
        appts_set = b["appointments_set"]
        deals = b["deals_closed"]

        lead_count = len(leads_owned)
        deal_count = len(deals)
        appt_count = len(appts_set)
        showed_count = sum(
            1 for l in appts_set
            if l.appointment and l.appointment.status == "showed"
        )
        response_times = [s for s in (_first_response_seconds(l) for l in leads_owned) if s is not None]
        median_response_sec = statistics.median(response_times) if response_times else None

        metrics[sp_id] = {
            "lead_count": lead_count,
            "appointments_set_count": appt_count,
            "showed_count": showed_count,
            "deal_count": deal_count,
            "response_count": len(response_times),
            "sale_conversion": (deal_count / lead_count) if lead_count else 0.0,
            "show_rate": (showed_count / appt_count) if appt_count else 0.0,
            "sales_volume": float(deal_count),
            "set_rate": (appt_count / lead_count) if lead_count else 0.0,
            "response_time_median_sec": median_response_sec,
        }
    return metrics


def normalize_per_lead(metrics: dict[str, dict]) -> dict[str, dict]:
    if not metrics:
        return {}
    top_sale_conv = max(m["sale_conversion"] for m in metrics.values())
    top_show = max(m["show_rate"] for m in metrics.values())
    top_volume = max(m["sales_volume"] for m in metrics.values())
    top_set = max(m["set_rate"] for m in metrics.values())
    response_medians = [m["response_time_median_sec"] for m in metrics.values()
                        if m["response_time_median_sec"] is not None]
    fastest_response = min(response_medians) if response_medians else None

    normalized: dict[str, dict] = {}
    for sp_id, m in metrics.items():
        n = {
            "sale_conversion": (m["sale_conversion"] / top_sale_conv) if top_sale_conv else 0.0,
            "show_rate": (m["show_rate"] / top_show) if top_show else 0.0,
            "sales_volume": (m["sales_volume"] / top_volume) if top_volume else 0.0,
            "set_rate": (m["set_rate"] / top_set) if top_set else 0.0,
        }
        if fastest_response and m["response_time_median_sec"]:
            n["response_time"] = fastest_response / m["response_time_median_sec"]
        else:
            n["response_time"] = 0.0
        normalized[sp_id] = {k: min(v, 1.0) for k, v in n.items()}
    return normalized


def compute_composite(n: dict, weights: dict) -> int:
    """Weighted sum × 10, floor of 1, rounded."""
    composite = sum(n.get(k, 0.0) * w for k, w in weights.items())
    return max(round(composite * 10), 1)


def assign_tier(score: int) -> str:
    if score >= 8:
        return "A"
    if score >= 5:
        return "B"
    if score >= 3:
        return "C"
    return "D"


def score_all(leads: list[Lead], *,
              period_days: int = DEFAULT_PERIOD_DAYS,
              end_date: datetime | None = None,
              min_volume: int = MIN_LEAD_VOLUME) -> dict:
    """Per-lead pipeline. Returns the standard result shape."""
    end_date = end_date or datetime.now()
    period_leads = exclude_credit_apps(filter_period(leads, days=period_days, end_date=end_date))
    buckets = attribute_leads_to_salespeople(period_leads)
    raw = compute_raw_metrics(buckets)

    eligible = {sp: m for sp, m in raw.items() if m["lead_count"] >= min_volume}
    normalized = normalize_per_lead(eligible)

    scored: dict[str, dict] = {}
    for sp_id, n in normalized.items():
        score = compute_composite(n, PER_LEAD_WEIGHTS)
        scored[sp_id] = {
            "score": score,
            "tier": assign_tier(score),
            "raw": raw[sp_id],
            "normalized": n,
            "contribution": {k: round(n[k] * PER_LEAD_WEIGHTS[k] * 10, 2) for k in PER_LEAD_WEIGHTS},
        }

    not_scored = {
        sp_id: {"lead_count": m["lead_count"],
                "reason": f"Below {min_volume}-lead minimum"}
        for sp_id, m in raw.items() if m["lead_count"] < min_volume
    }

    return {
        "pipeline": "per_lead",
        "weights": PER_LEAD_WEIGHTS,
        "scored": scored,
        "not_scored": not_scored,
        "metrics": raw,
        "bdc": {},
        "other_bucket": None,
        "placeholders": {},
        "period": {
            "days": period_days,
            "end_date": end_date.isoformat(),
            "start_date": (end_date - timedelta(days=period_days)).isoformat(),
        },
        "leads_in_period": period_leads,
        "summaries_in_period": [],
        "totals_row": None,
    }


# ── Aggregated pipeline ──────────────────────────────────────────────

def classify_summary(s: SalespersonSummary,
                     exclude_names: set[str] | None = None) -> tuple[str, str]:
    """Decide whether a summary row is a salesperson, BDC, placeholder, or 'other'.

    Returns (role, reason).
    """
    exclude_names = exclude_names or set()
    name_norm = s.name.strip().lower()

    if name_norm in {n.lower() for n in exclude_names}:
        return ("placeholder", "explicitly excluded by --exclude")

    if name_norm in {"other", "unassigned"}:
        return ("other_bucket", "unattributed-lead bucket from Tekion")

    if name_norm in {"house deal", "house", "floor"}:
        return ("placeholder", "Tekion accounting placeholder, not a user")

    if s.name.upper() == s.name and "JEROME" in s.name.upper():
        # Heuristic for duplicate full-name rows that mirror a normal-cased account.
        return ("placeholder", "duplicate user account (full-uppercase name)")

    # Mostly-inactive placeholder accounts
    if s.good_leads == 0 and s.total_tasks < 10 and s.sold == 0:
        return ("placeholder", "no leads, near-zero tasks, no sales")

    # BDC / appt coordinator pattern: tons of task work, few or no owned leads
    if s.total_tasks >= 100 and s.good_leads < 5:
        return ("bdc", f"{s.total_tasks} tasks on {s.good_leads} owned leads")
    if s.good_leads > 0 and s.tasks_per_lead > 30:
        return ("bdc", f"tasks/lead ratio {s.tasks_per_lead:.1f} (>30 threshold)")

    return ("salesperson", "")


def _inverse_normalize_overdue(values: list[float]) -> dict[int, float]:
    """For 'fewer is better' metrics: 1.0 = best, 0.0 = worst.

    Returns by index into the original list.
    """
    if not values:
        return {}
    worst = max(values)
    if worst == 0:
        return {i: 1.0 for i in range(len(values))}
    return {i: 1.0 - (v / worst) for i, v in enumerate(values)}


def _compute_aggregated_raw(s: SalespersonSummary) -> dict:
    return {
        "lead_count": s.good_leads,
        "sale_count": s.sold,
        "sale_conversion": s.sale_conversion(),
        "set_rate": s.set_rate(),
        "show_rate": s.show_rate(),
        "sales_volume": float(s.sold),
        "task_completion": s.task_completion(),
        "activity_per_lead": s.touches_per_lead,
        "call_connection": s.call_connection(),
        "confirmation_rate": s.confirmation_rate(),
        "tasks_overdue_count": float(s.tasks_overdue),
        "video_adoption": s.video_adoption(),
        # Raw counts useful for the scorecard / coaching flags
        "tasks_total": s.total_tasks,
        "tasks_completed": s.completed_tasks,
        "tasks_overdue": s.tasks_overdue,
        "calls_out": s.calls_out,
        "calls_contacted": s.calls_out_contacted,
        "texts_sent": s.texts_sent,
        "emails_sent": s.emails_sent,
        "videos_sent": s.videos_sent,
        "video_sent_leads": s.video_sent_leads,
        "appts_created": s.appointments_created,
        "appts_scheduled": s.appointments_scheduled,
        "appts_confirmed": s.appointments_confirmed,
        "appts_shown": s.appointments_shown,
    }


def _normalize_aggregated(per_sp_raw: dict[str, dict]) -> dict[str, dict]:
    if not per_sp_raw:
        return {}

    # Higher-is-better factors → divide by top performer
    higher_better = ["sale_conversion", "set_rate", "show_rate", "sales_volume",
                     "task_completion", "activity_per_lead", "call_connection",
                     "confirmation_rate", "video_adoption"]
    tops = {k: max(m[k] for m in per_sp_raw.values()) for k in higher_better}

    # Lower-is-better: tasks_overdue
    sp_ids = list(per_sp_raw.keys())
    overdue_values = [per_sp_raw[sp]["tasks_overdue_count"] for sp in sp_ids]
    overdue_norm_by_idx = _inverse_normalize_overdue(overdue_values)

    normalized: dict[str, dict] = {}
    for idx, sp_id in enumerate(sp_ids):
        m = per_sp_raw[sp_id]
        n = {}
        for k in higher_better:
            top = tops[k]
            n[k] = (m[k] / top) if top else 0.0
        n["tasks_overdue"] = overdue_norm_by_idx.get(idx, 1.0)
        normalized[sp_id] = {k: min(v, 1.0) for k, v in n.items()}
    return normalized


def score_aggregated(summaries: list[SalespersonSummary], *,
                     totals_row: SalespersonSummary | None = None,
                     period_days: int = DEFAULT_PERIOD_DAYS,
                     end_date: datetime | None = None,
                     min_volume: int = MIN_LEAD_VOLUME,
                     exclude_names: list[str] | None = None) -> dict:
    """Aggregated pipeline. Returns the standard result shape.

    Auto-classifies each summary into salesperson / bdc / other_bucket /
    placeholder, scores salespeople on the 10-factor methodology, and surfaces
    BDC and the unattributed 'Other' bucket separately.
    """
    end_date = end_date or datetime.now()
    exclude_set = set(exclude_names or [])

    salespeople: list[SalespersonSummary] = []
    bdc: list[SalespersonSummary] = []
    other_bucket: SalespersonSummary | None = None
    placeholders: list[SalespersonSummary] = []

    for s in summaries:
        role, reason = classify_summary(s, exclude_set)
        s.role = role
        s.role_reason = reason
        if role == "salesperson":
            salespeople.append(s)
        elif role == "bdc":
            bdc.append(s)
        elif role == "other_bucket":
            other_bucket = s
        else:
            placeholders.append(s)

    raw = {s.name: _compute_aggregated_raw(s) for s in salespeople}
    eligible = {sp: m for sp, m in raw.items() if m["lead_count"] >= min_volume}
    normalized = _normalize_aggregated(eligible)

    scored: dict[str, dict] = {}
    for sp_id, n in normalized.items():
        score = compute_composite(n, AGGREGATED_WEIGHTS)
        scored[sp_id] = {
            "score": score,
            "tier": assign_tier(score),
            "raw": raw[sp_id],
            "normalized": n,
            "contribution": {k: round(n[k] * AGGREGATED_WEIGHTS[k] * 10, 2) for k in AGGREGATED_WEIGHTS},
        }

    not_scored = {
        sp_id: {"lead_count": m["lead_count"],
                "reason": f"Below {min_volume}-lead minimum"}
        for sp_id, m in raw.items() if m["lead_count"] < min_volume
    }

    return {
        "pipeline": "aggregated",
        "weights": AGGREGATED_WEIGHTS,
        "scored": scored,
        "not_scored": not_scored,
        "metrics": raw,
        "bdc": {s.name: _compute_aggregated_raw(s) | {"role_reason": s.role_reason} for s in bdc},
        "other_bucket": (_compute_aggregated_raw(other_bucket) if other_bucket else None),
        "placeholders": {s.name: s.role_reason for s in placeholders},
        "period": {
            "days": period_days,
            "end_date": end_date.isoformat(),
            "start_date": (end_date - timedelta(days=period_days)).isoformat(),
        },
        "leads_in_period": [],
        "summaries_in_period": salespeople + bdc + ([other_bucket] if other_bucket else []),
        "totals_row": (_compute_aggregated_raw(totals_row) if totals_row else None),
    }


# ── CLI entry point ───────────────────────────────────────────────────

def _main():
    p = argparse.ArgumentParser(description="Score salespeople from a CRM export.")
    p.add_argument("--crm", choices=["tekion", "vinsolutions"], default="tekion")

    # Per-lead path
    p.add_argument("--tekion-leads", help="Path to Tekion lead-level export CSV")
    p.add_argument("--tekion-activities", help="Path to Tekion activity-log CSV (optional)")

    # Aggregated path
    p.add_argument("--tekion-user-activity",
                   help="Path to Tekion 'User Activity Report - By Sales Rep' CSV (aggregated)")

    p.add_argument("--vinsolutions-export", help="Path to VINSolutions export (not yet supported)")

    p.add_argument("--store", required=True, help="Dealership name (e.g., 'McPeek CDJR')")
    p.add_argument("--period-days", type=int, default=DEFAULT_PERIOD_DAYS)
    p.add_argument("--min-volume", type=int, default=MIN_LEAD_VOLUME)
    p.add_argument("--end-date", help="ISO date; defaults to today")
    p.add_argument("--exclude", action="append", default=[],
                   help="Names to treat as placeholders (repeat flag for multiple)")
    p.add_argument("--output",
                   help=("Output XLSX path. Defaults to "
                         "'DigitalCLIQ/outputs/<Store>_Salesperson_Scores_<YYYY-MM-DD>.xlsx'"))
    args = p.parse_args()

    end_date = datetime.fromisoformat(args.end_date) if args.end_date else datetime.now()

    # Decide which pipeline to run
    if args.tekion_user_activity:
        from scripts.parse_tekion_user_activity import parse_tekion_user_activity
        parsed = parse_tekion_user_activity(args.tekion_user_activity)
        results = score_aggregated(
            parsed["salespeople"],
            totals_row=parsed["totals"],
            period_days=args.period_days,
            end_date=end_date,
            min_volume=args.min_volume,
            exclude_names=args.exclude,
        )
    elif args.crm == "tekion":
        if not args.tekion_leads:
            p.error("Provide --tekion-leads (per-lead path) or --tekion-user-activity (aggregated path)")
        from scripts.parse_tekion import parse_tekion
        leads = parse_tekion(args.tekion_leads, activity_csv_path=args.tekion_activities)
        results = score_all(leads,
                            period_days=args.period_days,
                            end_date=end_date,
                            min_volume=args.min_volume)
    else:
        from scripts.parse_vinsolutions import parse_vinsolutions
        parse_vinsolutions(args.vinsolutions_export)
        return  # never reached; parse_vinsolutions raises

    from scripts.coaching_flags import attach_flags
    attach_flags(results)

    from scripts.excel_builder import build_workbook
    if args.output:
        output_path = args.output
    else:
        outputs_dir = os.path.expanduser("~/Desktop/DigitalCLIQ Brain HQ/outputs")
        os.makedirs(outputs_dir, exist_ok=True)
        safe_store = args.store.replace(" ", "_").replace("/", "_")
        output_path = os.path.join(
            outputs_dir,
            f"{safe_store}_Salesperson_Scores_{end_date.strftime('%Y-%m-%d')}.xlsx",
        )

    period_label = f"Trailing {args.period_days} days ending {end_date.strftime('%b %-d, %Y')}"
    build_workbook(results, store_name=args.store, period_label=period_label,
                   output_path=output_path)

    n_scored = len(results["scored"])
    n_not_scored = len(results["not_scored"])
    n_bdc = len(results["bdc"])
    extra = f", {n_bdc} BDC" if n_bdc else ""
    extra += ", +Other bucket" if results.get("other_bucket") else ""
    print(f"OK: {output_path}  ({n_scored} scored, {n_not_scored} below minimum{extra})")


if __name__ == "__main__":
    _main()
