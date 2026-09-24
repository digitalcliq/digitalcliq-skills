"""Auto-generated coaching insights based on metric mismatches.

Operates on the output of scoring_engine.score_all() or score_aggregated().
Computes percentile ranks within the scored cohort and applies rule sets
tailored to which factors are available.
"""
from __future__ import annotations

import statistics


SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _percentile_rank(value: float, all_values: list[float],
                     higher_is_better: bool = True) -> float:
    if not all_values:
        return 0.0
    if len(all_values) == 1:
        return 50.0
    below = sum(1 for v in all_values if (v < value if higher_is_better else v > value))
    equal = sum(1 for v in all_values if v == value)
    return 100.0 * (below + 0.5 * equal) / len(all_values)


def compute_percentile_ranks(scored: dict[str, dict], pipeline: str) -> dict[str, dict]:
    """For each scored salesperson, compute a 0-100 percentile rank per factor."""
    if not scored:
        return {}

    # Common factors
    sale_conv = [s["raw"]["sale_conversion"] for s in scored.values()]
    show_rate = [s["raw"]["show_rate"] for s in scored.values()]
    sales_vol = [s["raw"]["sales_volume"] for s in scored.values()]
    set_rate = [s["raw"]["set_rate"] for s in scored.values()]

    # Aggregated-only factors
    task_comp = [s["raw"].get("task_completion", 0.0) for s in scored.values()]
    activity = [s["raw"].get("activity_per_lead", 0.0) for s in scored.values()]
    call_conn = [s["raw"].get("call_connection", 0.0) for s in scored.values()]
    confirm = [s["raw"].get("confirmation_rate", 0.0) for s in scored.values()]
    overdue = [s["raw"].get("tasks_overdue_count", 0.0) for s in scored.values()]
    video = [s["raw"].get("video_adoption", 0.0) for s in scored.values()]

    response = [s["raw"]["response_time_median_sec"] for s in scored.values()
                if s["raw"].get("response_time_median_sec") is not None]

    ranks: dict[str, dict] = {}
    for sp_id, s in scored.items():
        r = s["raw"]
        rk = {
            "sale_conversion": _percentile_rank(r["sale_conversion"], sale_conv, True),
            "show_rate":       _percentile_rank(r["show_rate"], show_rate, True),
            "sales_volume":    _percentile_rank(r["sales_volume"], sales_vol, True),
            "set_rate":        _percentile_rank(r["set_rate"], set_rate, True),
        }
        if pipeline == "aggregated":
            rk["task_completion"]   = _percentile_rank(r.get("task_completion", 0.0), task_comp, True)
            rk["activity_per_lead"] = _percentile_rank(r.get("activity_per_lead", 0.0), activity, True)
            rk["call_connection"]   = _percentile_rank(r.get("call_connection", 0.0), call_conn, True)
            rk["confirmation_rate"] = _percentile_rank(r.get("confirmation_rate", 0.0), confirm, True)
            rk["video_adoption"]    = _percentile_rank(r.get("video_adoption", 0.0), video, True)
            rk["tasks_overdue"]     = _percentile_rank(r.get("tasks_overdue_count", 0.0), overdue,
                                                       higher_is_better=False)
        else:
            if r.get("response_time_median_sec") is not None and response:
                rk["response_time"] = _percentile_rank(r["response_time_median_sec"], response,
                                                       higher_is_better=False)
            else:
                rk["response_time"] = 0.0
        ranks[sp_id] = rk
    return ranks


def _per_lead_flags(raw: dict, ranks: dict, median_lead_count: float) -> list[dict]:
    flags = []
    if ranks["response_time"] >= 75 and ranks["set_rate"] <= 25:
        flags.append({"severity": "high", "category": "appointment_setting",
                      "message": "Fast response but weak set rate — coach on appointment-setting language and call-to-action."})
    if ranks["set_rate"] >= 75 and ranks["show_rate"] <= 25:
        flags.append({"severity": "high", "category": "confirmation_discipline",
                      "message": "Strong set rate but weak show rate — review confirmation cadence (24hr and 2hr confirms)."})
    if ranks["show_rate"] >= 75 and ranks["sale_conversion"] <= 25:
        flags.append({"severity": "high", "category": "closing_process",
                      "message": "Customers show but don't buy — review desking, presentation, and closing technique."})
    if ranks["response_time"] <= 25 and raw["lead_count"] < median_lead_count * 0.7:
        flags.append({"severity": "medium", "category": "workload",
                      "message": "Slow response with low lead count — may be a workload distribution issue rather than skill."})
    if ranks["sales_volume"] >= 75 and ranks["sale_conversion"] <= 25:
        flags.append({"severity": "medium", "category": "efficiency",
                      "message": "High raw volume but low conversion — relying on lead quantity over quality. Coach lead qualification."})
    weak = [k for k, v in ranks.items() if v <= 25]
    if len(weak) >= 4:
        flags.append({"severity": "high", "category": "performance_review",
                      "message": "Bottom quartile on 4+ factors — escalate for formal performance review."})
    return flags


def _aggregated_flags(raw: dict, ranks: dict, median_lead_count: float) -> list[dict]:
    flags = []

    # CRM data-integrity / role flags (these come first because they invalidate the score)
    if raw.get("calls_out", 0) >= 100 and raw.get("call_connection", 0) == 0.0:
        flags.append({
            "severity": "high",
            "category": "data_integrity",
            "message": (f"{int(raw['calls_out'])} calls placed with 0 logged contacts — verify "
                        "Tekion phone integration is recording connected calls. Score on call connection "
                        "may be unreliable.")
        })

    # Pipeline neglect: lots of leads, zero outbound
    total_outbound = raw.get("calls_out", 0) + raw.get("texts_sent", 0) + raw.get("emails_sent", 0)
    if raw["lead_count"] >= 25 and total_outbound < 20:
        flags.append({
            "severity": "high",
            "category": "pipeline_neglect",
            "message": f"{raw['lead_count']} good leads with only {total_outbound} total outbound touches. Pipeline is going untouched."
        })

    # High close rate on low touch volume → likely repeat/walk-in/floor business
    if (ranks["sale_conversion"] >= 75
            and ranks.get("activity_per_lead", 0) <= 25
            and raw["lead_count"] >= 20):
        flags.append({
            "severity": "medium",
            "category": "attribution_check",
            "message": "High close rate on very low touch volume — closing primarily on repeat / referral / floor traffic. Verify these are leads they actually worked."
        })

    # Task completion below 50%
    if raw.get("task_completion", 1.0) < 0.5 and raw.get("tasks_total", 0) >= 5:
        flags.append({
            "severity": "high",
            "category": "task_discipline",
            "message": f"Task completion {raw['task_completion']*100:.0f}% — leads going stale. Half-or-more of assigned follow-ups not getting done."
        })

    # Strong set rate but weak confirm → show rate at risk
    if ranks.get("set_rate", 0) >= 60 and ranks.get("confirmation_rate", 0) <= 25:
        flags.append({
            "severity": "high",
            "category": "confirmation_discipline",
            "message": "Sets appointments well but confirms poorly — coach the 24hr and 2hr confirm cadence."
        })

    # Strong confirm but weak show → coachable but rarer
    if ranks.get("confirmation_rate", 0) >= 75 and ranks.get("show_rate", 0) <= 25:
        flags.append({
            "severity": "medium",
            "category": "confirmation_quality",
            "message": "Confirms strongly but customers still don't show — review confirm-call script (over-pressuring or wrong contact method)."
        })

    # Process strong but outcome weak
    if (ranks.get("task_completion", 0) >= 75
            and ranks.get("activity_per_lead", 0) >= 75
            and ranks.get("sale_conversion", 0) <= 25):
        flags.append({
            "severity": "high",
            "category": "closing_process",
            "message": "Doing the work but not closing — strong activity, weak conversion. Review desking, presentation, and closing technique."
        })

    # Too many overdue tasks
    if raw.get("tasks_overdue", 0) >= 5:
        flags.append({
            "severity": "medium",
            "category": "task_discipline",
            "message": f"{int(raw['tasks_overdue'])} overdue tasks — backlog forming."
        })

    # Bottom quartile on 4+ factors → performance review
    weak = [k for k, v in ranks.items() if v <= 25]
    if len(weak) >= 4:
        flags.append({
            "severity": "high",
            "category": "performance_review",
            "message": f"Bottom quartile on {len(weak)} factors — escalate for formal performance review."
        })

    return flags


def generate_flags(raw: dict, ranks: dict, median_lead_count: float,
                   pipeline: str = "aggregated") -> list[dict]:
    flags = _aggregated_flags(raw, ranks, median_lead_count) if pipeline == "aggregated" \
            else _per_lead_flags(raw, ranks, median_lead_count)
    flags.sort(key=lambda f: SEVERITY_ORDER.get(f["severity"], 99))
    return flags[:3]  # top 3 (was 2; now 3 since more diagnostics available)


def attach_flags(results: dict) -> None:
    """Mutate `results` by attaching 'flags' to each scored salesperson."""
    scored = results.get("scored", {})
    if not scored:
        return

    pipeline = results.get("pipeline", "per_lead")
    ranks = compute_percentile_ranks(scored, pipeline)
    lead_counts = [s["raw"]["lead_count"] for s in scored.values()]
    median_lead_count = statistics.median(lead_counts) if lead_counts else 0

    for sp_id, s in scored.items():
        s["percentile_ranks"] = ranks[sp_id]
        s["flags"] = generate_flags(s["raw"], ranks[sp_id], median_lead_count, pipeline)
