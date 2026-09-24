"""
audit_engine.py — Paid media waste audit engine for automotive dealerships.

Applies waste detection rules against normalized campaign data:
  1. Zero-conversion spend zones
  2. Low VDP-to-lead outliers
  3. High-spend / low-return campaigns
  4. Search term bleed (irrelevant queries)
  5. Geo waste (spend outside market radius)
  6. Device/hour waste (disproportionate ratios)
  7. Funnel misallocation detection

Also computes:
  - Funnel stage allocation vs. recommended ranges
  - Per-source performance summaries
  - Executive summary metrics
  - Suggestions for discussion (tone-controlled)
"""

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from classify_funnel import (
    classify_campaign,
    STAGE_ALLOCATION_RANGES,
    STAGE_PRIMARY_KPIS,
)

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = SKILL_DIR / "config"


def _load_thresholds() -> dict:
    with open(CONFIG_DIR / "waste_thresholds.json") as f:
        return json.load(f)


def _load_benchmarks() -> dict:
    with open(CONFIG_DIR / "ltv_benchmarks.json") as f:
        return json.load(f)


def _detect_brand_tier(client_name: str, benchmarks: dict) -> str:
    """Detect brand tier from client name."""
    name_lower = client_name.lower()
    for tier_key, tier_data in benchmarks["tiers"].items():
        for brand in tier_data.get("brands", []):
            if brand in name_lower:
                return tier_key
    return "mainstream_import"  # safe default


# -----------------------------------------------------------------------
# Waste audit rules
# -----------------------------------------------------------------------

def audit_zero_conversion_spend(rows: list[dict], thresholds: dict) -> list[dict]:
    """Rule 1: Flag campaigns with spend above threshold but zero conversions."""
    cfg = thresholds["zero_conversion_spend"]
    findings = []

    # Aggregate by campaign
    campaigns = defaultdict(lambda: {
        "spend": 0, "form_fills": 0, "phone_calls": 0,
        "chat_leads": 0, "leads_total": 0, "vdp_views": 0,
        "impressions": 0, "clicks": 0, "source": "",
    })
    for r in rows:
        key = r.get("campaign", "Unknown")
        campaigns[key]["spend"] += r.get("spend", 0)
        campaigns[key]["form_fills"] += r.get("form_fills", 0)
        campaigns[key]["phone_calls"] += r.get("phone_calls", 0)
        campaigns[key]["chat_leads"] += r.get("chat_leads", 0)
        campaigns[key]["leads_total"] += r.get("leads_total", 0)
        campaigns[key]["vdp_views"] += r.get("vdp_views", 0)
        campaigns[key]["impressions"] += r.get("impressions", 0)
        campaigns[key]["clicks"] += r.get("clicks", 0)
        campaigns[key]["source"] = r.get("source_platform", "")

    for camp_name, data in campaigns.items():
        if data["leads_total"] > 0:
            continue

        source = data["source"]
        if "social" in source or "meta" in source:
            threshold = cfg["social_threshold_usd"]
        elif "display" in source or "pmax" in camp_name.lower() or "performance max" in camp_name.lower():
            threshold = cfg["display_pmax_threshold_usd"]
        else:
            threshold = cfg["search_threshold_usd"]

        if data["spend"] >= threshold:
            findings.append({
                "rule": "zero_conversion_spend",
                "severity": "high" if data["spend"] >= threshold * 2 else "medium",
                "campaign": camp_name,
                "spend": round(data["spend"], 2),
                "threshold": threshold,
                "impressions": data["impressions"],
                "clicks": data["clicks"],
                "vdp_views": data["vdp_views"],
                "leads": 0,
                "observation": (
                    f"'{camp_name}' spent ${data['spend']:,.2f} with zero "
                    f"form fills, calls, or leads over the period."
                ),
                "waste_amount": round(data["spend"], 2),
            })

    return findings


def audit_low_vdp_to_lead(rows: list[dict], thresholds: dict, brand_tier: str) -> list[dict]:
    """Rule 2: Flag campaigns driving VDP traffic with low lead conversion."""
    cfg = thresholds["low_vdp_to_lead"]
    tier_threshold = cfg.get(f"{brand_tier}_threshold_pct",
                              cfg.get("mainstream_threshold_pct", 1.5))
    min_vdps = cfg["min_vdp_views"]
    findings = []

    campaigns = defaultdict(lambda: {"vdp_views": 0, "leads_total": 0, "spend": 0})
    for r in rows:
        key = r.get("campaign", "Unknown")
        campaigns[key]["vdp_views"] += r.get("vdp_views", 0)
        campaigns[key]["leads_total"] += r.get("leads_total", 0)
        campaigns[key]["spend"] += r.get("spend", 0)

    for camp_name, data in campaigns.items():
        if data["vdp_views"] < min_vdps:
            continue
        lead_rate = (data["leads_total"] / data["vdp_views"] * 100) if data["vdp_views"] > 0 else 0
        if lead_rate < tier_threshold:
            findings.append({
                "rule": "low_vdp_to_lead",
                "severity": "medium",
                "campaign": camp_name,
                "spend": round(data["spend"], 2),
                "vdp_views": data["vdp_views"],
                "leads": data["leads_total"],
                "vdp_to_lead_pct": round(lead_rate, 2),
                "threshold_pct": tier_threshold,
                "observation": (
                    f"'{camp_name}' drove {data['vdp_views']} VDP views "
                    f"but only {lead_rate:.1f}% converted to leads "
                    f"(threshold: {tier_threshold}%)."
                ),
                "waste_amount": 0,  # not directly quantifiable
            })

    return findings


def audit_high_spend_low_return(rows: list[dict], thresholds: dict) -> list[dict]:
    """Rule 3: Flag campaigns in top 20% spend but bottom 30% performance."""
    cfg = thresholds["high_spend_low_return"]
    findings = []

    campaigns = defaultdict(lambda: {"spend": 0, "leads_total": 0, "clicks": 0})
    for r in rows:
        key = r.get("campaign", "Unknown")
        campaigns[key]["spend"] += r.get("spend", 0)
        campaigns[key]["leads_total"] += r.get("leads_total", 0)
        campaigns[key]["clicks"] += r.get("clicks", 0)

    if len(campaigns) < 5:
        return findings  # not enough campaigns to compare

    sorted_by_spend = sorted(campaigns.items(), key=lambda x: x[1]["spend"], reverse=True)
    top_spend_cutoff = int(len(sorted_by_spend) * (cfg["spend_percentile_top"] / 100))
    top_spenders = dict(sorted_by_spend[:max(top_spend_cutoff, 1)])

    # Rank all by performance (CPL — lower is better, handle zero leads)
    for k, v in campaigns.items():
        v["cpl"] = v["spend"] / v["leads_total"] if v["leads_total"] > 0 else float("inf")

    sorted_by_perf = sorted(campaigns.items(), key=lambda x: x[1]["cpl"], reverse=True)
    bottom_perf_cutoff = int(len(sorted_by_perf) * (cfg["performance_percentile_bottom"] / 100))
    bottom_performers = dict(sorted_by_perf[:max(bottom_perf_cutoff, 1)])

    for camp_name in top_spenders:
        if camp_name in bottom_performers and campaigns[camp_name]["spend"] >= cfg["min_spend_usd"]:
            data = campaigns[camp_name]
            cpl = data["cpl"]
            cpl_str = f"${cpl:,.2f}" if cpl < float("inf") else "no leads"
            findings.append({
                "rule": "high_spend_low_return",
                "severity": "high",
                "campaign": camp_name,
                "spend": round(data["spend"], 2),
                "leads": data["leads_total"],
                "cpl": round(cpl, 2) if cpl < float("inf") else None,
                "observation": (
                    f"'{camp_name}' is in the top {cfg['spend_percentile_top']}% of spend "
                    f"(${data['spend']:,.2f}) but bottom {cfg['performance_percentile_bottom']}% "
                    f"on CPL ({cpl_str})."
                ),
                "waste_amount": 0,
            })

    return findings


def audit_search_term_bleed(rows: list[dict], thresholds: dict) -> list[dict]:
    """Rule 4: Flag irrelevant search terms consuming budget."""
    cfg = thresholds["search_term_bleed"]
    findings = []
    irrelevant_pats = cfg["irrelevant_patterns"]

    term_spend = defaultdict(lambda: {"spend": 0, "impressions": 0, "clicks": 0})
    for r in rows:
        term = r.get("search_term", "").strip()
        if not term:
            continue
        # Use original pre-dedup values if available (search terms that were
        # zeroed out to prevent double-counting with campaign-level data)
        term_spend[term]["spend"] += r.get("_original_spend", r.get("spend", 0))
        term_spend[term]["impressions"] += r.get("_original_impressions", r.get("impressions", 0))
        term_spend[term]["clicks"] += r.get("_original_clicks", r.get("clicks", 0))

    flagged = []
    for term, data in term_spend.items():
        if data["impressions"] < cfg["min_impressions"]:
            continue
        term_lower = term.lower()
        for pat in irrelevant_pats:
            if pat.lower() in term_lower:
                flagged.append({
                    "term": term,
                    "spend": data["spend"],
                    "impressions": data["impressions"],
                    "clicks": data["clicks"],
                    "matched_pattern": pat,
                })
                break

    # Sort by spend descending, take top N
    flagged.sort(key=lambda x: x["spend"], reverse=True)
    total_waste = sum(f["spend"] for f in flagged)

    if flagged:
        findings.append({
            "rule": "search_term_bleed",
            "severity": "medium" if total_waste > 100 else "low",
            "flagged_terms": flagged[:cfg["top_n_irrelevant"]],
            "total_irrelevant_spend": round(total_waste, 2),
            "count": len(flagged),
            "observation": (
                f"Found {len(flagged)} potentially irrelevant search terms "
                f"consuming ${total_waste:,.2f} in spend."
            ),
            "waste_amount": round(total_waste, 2),
        })

    return findings


def audit_geo_waste(rows: list[dict], thresholds: dict) -> list[dict]:
    """Rule 5: Flag spend outside primary market radius with no conversions."""
    # NOTE: Geo analysis requires location data in the export.
    # Many standard exports don't include granular geo.
    # This rule will fire only if geo_location data is present.
    cfg = thresholds["geo_waste"]
    findings = []

    geo_spend = defaultdict(lambda: {"spend": 0, "leads_total": 0, "clicks": 0})
    has_geo = False
    for r in rows:
        geo = r.get("geo_location", "").strip()
        if not geo:
            continue
        has_geo = True
        geo_spend[geo]["spend"] += r.get("spend", 0)
        geo_spend[geo]["leads_total"] += r.get("leads_total", 0)
        geo_spend[geo]["clicks"] += r.get("clicks", 0)

    if not has_geo:
        return findings

    # Flag locations with spend above threshold but zero leads
    zero_lead_geos = []
    for geo, data in geo_spend.items():
        if data["leads_total"] == 0 and data["spend"] >= cfg["min_spend_outside_market_usd"]:
            zero_lead_geos.append({
                "location": geo,
                "spend": round(data["spend"], 2),
                "clicks": data["clicks"],
            })

    if zero_lead_geos:
        total_waste = sum(g["spend"] for g in zero_lead_geos)
        zero_lead_geos.sort(key=lambda x: x["spend"], reverse=True)
        findings.append({
            "rule": "geo_waste",
            "severity": "medium",
            "flagged_locations": zero_lead_geos[:20],
            "total_geo_waste": round(total_waste, 2),
            "count": len(zero_lead_geos),
            "observation": (
                f"Found {len(zero_lead_geos)} geographic areas with "
                f"${total_waste:,.2f} in spend and zero leads."
            ),
            "waste_amount": round(total_waste, 2),
        })

    return findings


def audit_device_hour(rows: list[dict], thresholds: dict) -> list[dict]:
    """Rule 6: Flag devices/hours with disproportionate spend-to-conversion ratios."""
    cfg = thresholds["device_hour_waste"]
    findings = []

    # Device analysis
    device_data = defaultdict(lambda: {"spend": 0, "leads_total": 0})
    hour_data = defaultdict(lambda: {"spend": 0, "leads_total": 0})

    for r in rows:
        device = r.get("device", "").strip()
        hour = r.get("hour_of_day", "").strip()
        if device:
            device_data[device]["spend"] += r.get("spend", 0)
            device_data[device]["leads_total"] += r.get("leads_total", 0)
        if hour:
            hour_data[hour]["spend"] += r.get("spend", 0)
            hour_data[hour]["leads_total"] += r.get("leads_total", 0)

    # Check devices
    total_spend = sum(d["spend"] for d in device_data.values())
    total_leads = sum(d["leads_total"] for d in device_data.values())
    if total_spend > 0 and total_leads > 0:
        avg_ratio = total_spend / total_leads
        for device, data in device_data.items():
            if data["spend"] < cfg["min_spend_usd"]:
                continue
            device_ratio = data["spend"] / data["leads_total"] if data["leads_total"] > 0 else float("inf")
            if device_ratio > avg_ratio * cfg["spend_to_conversion_ratio_threshold"]:
                findings.append({
                    "rule": "device_waste",
                    "severity": "low",
                    "device": device,
                    "spend": round(data["spend"], 2),
                    "leads": data["leads_total"],
                    "cpl": round(device_ratio, 2) if device_ratio < float("inf") else None,
                    "avg_cpl": round(avg_ratio, 2),
                    "observation": (
                        f"Device '{device}' has a CPL of "
                        f"${device_ratio:,.2f}" if device_ratio < float("inf")
                        else f"Device '{device}' has ${data['spend']:,.2f} spend with no leads"
                    ) + f" vs. average CPL ${avg_ratio:,.2f}.",
                    "waste_amount": 0,
                })

    return findings


# -----------------------------------------------------------------------
# Funnel allocation analysis
# -----------------------------------------------------------------------

def compute_funnel_allocation(rows: list[dict]) -> dict:
    """Classify all rows by funnel stage and compute allocation percentages."""
    stage_totals = defaultdict(lambda: {
        "spend": 0, "impressions": 0, "clicks": 0,
        "leads_total": 0, "vdp_views": 0, "campaigns": set(),
        "misallocated_count": 0,
    })
    total_spend = 0

    for r in rows:
        result = classify_campaign(
            r.get("campaign", ""),
            r.get("ad_group", ""),
            r.get("keyword", ""),
            r.get("search_term", ""),
        )
        stage = result["stage"]
        r["_funnel_stage"] = stage  # annotate row for downstream use

        stage_totals[stage]["spend"] += r.get("spend", 0)
        stage_totals[stage]["impressions"] += r.get("impressions", 0)
        stage_totals[stage]["clicks"] += r.get("clicks", 0)
        stage_totals[stage]["leads_total"] += r.get("leads_total", 0)
        stage_totals[stage]["vdp_views"] += r.get("vdp_views", 0)
        stage_totals[stage]["campaigns"].add(r.get("campaign", ""))
        if result["misallocated"]:
            stage_totals[stage]["misallocated_count"] += 1
        total_spend += r.get("spend", 0)

    # Compute percentages and add recommended ranges
    allocation = {}
    for stage, data in stage_totals.items():
        pct = (data["spend"] / total_spend * 100) if total_spend > 0 else 0
        rec = STAGE_ALLOCATION_RANGES.get(stage, {})
        allocation[stage] = {
            "spend": round(data["spend"], 2),
            "spend_pct": round(pct, 1),
            "recommended_min_pct": rec.get("min_pct", 0),
            "recommended_max_pct": rec.get("max_pct", 100),
            "impressions": data["impressions"],
            "clicks": data["clicks"],
            "leads": data["leads_total"],
            "vdp_views": data["vdp_views"],
            "campaign_count": len(data["campaigns"]),
            "misallocated_count": data["misallocated_count"],
            "within_range": rec.get("min_pct", 0) <= pct <= rec.get("max_pct", 100),
            "notes": rec.get("notes", ""),
        }

    return {"stages": allocation, "total_spend": round(total_spend, 2)}


# -----------------------------------------------------------------------
# Source performance summary
# -----------------------------------------------------------------------

def compute_source_performance(rows: list[dict]) -> list[dict]:
    """Aggregate performance by source platform."""
    sources = defaultdict(lambda: {
        "spend": 0, "impressions": 0, "clicks": 0,
        "leads_total": 0, "form_fills": 0, "phone_calls": 0,
        "vdp_views": 0, "srp_views": 0, "direction_clicks": 0,
        "chat_leads": 0, "row_count": 0,
    })

    for r in rows:
        src = r.get("source_platform", "unknown")
        for k in sources[src]:
            if k == "row_count":
                sources[src][k] += 1
            else:
                sources[src][k] += r.get(k, 0)

    result = []
    for src, data in sources.items():
        cpl = data["spend"] / data["leads_total"] if data["leads_total"] > 0 else None
        ctr = data["clicks"] / data["impressions"] * 100 if data["impressions"] > 0 else None
        result.append({
            "source": src,
            "spend": round(data["spend"], 2),
            "impressions": data["impressions"],
            "clicks": data["clicks"],
            "ctr_pct": round(ctr, 2) if ctr else None,
            "leads_total": data["leads_total"],
            "form_fills": data["form_fills"],
            "phone_calls": data["phone_calls"],
            "vdp_views": data["vdp_views"],
            "cpl": round(cpl, 2) if cpl else None,
            "row_count": data["row_count"],
        })

    result.sort(key=lambda x: x["spend"], reverse=True)
    return result


# -----------------------------------------------------------------------
# Executive summary
# -----------------------------------------------------------------------

def compute_executive_summary(
    rows: list[dict],
    findings: list[dict],
    funnel_alloc: dict,
    benchmarks: dict,
    brand_tier: str,
) -> dict:
    """Compute top-level summary metrics."""
    total_spend = sum(r.get("spend", 0) for r in rows)
    total_leads = sum(r.get("leads_total", 0) for r in rows)
    total_clicks = sum(r.get("clicks", 0) for r in rows)
    total_impressions = sum(r.get("impressions", 0) for r in rows)
    total_vdp = sum(r.get("vdp_views", 0) for r in rows)

    cpl = total_spend / total_leads if total_leads > 0 else None
    ctr = total_clicks / total_impressions * 100 if total_impressions > 0 else None

    # Estimated waste from findings
    total_waste = sum(f.get("waste_amount", 0) for f in findings)
    waste_pct = (total_waste / total_spend * 100) if total_spend > 0 else 0

    # Tier benchmarks
    tier_data = benchmarks["tiers"].get(brand_tier, {})
    benchmark_cpl = tier_data.get("defensible_cpl_ceiling")
    benchmark_cac = tier_data.get("defensible_cac_ceiling")

    # Top 3 opportunity areas (highest waste_amount findings)
    sorted_findings = sorted(findings, key=lambda x: x.get("waste_amount", 0), reverse=True)
    top_opportunities = []
    for f in sorted_findings[:3]:
        if f.get("waste_amount", 0) > 0 or f.get("severity") in ("high", "medium"):
            top_opportunities.append(f.get("observation", ""))

    return {
        "total_spend": round(total_spend, 2),
        "total_leads": total_leads,
        "total_clicks": total_clicks,
        "total_impressions": total_impressions,
        "total_vdp_views": total_vdp,
        "cpl": round(cpl, 2) if cpl else None,
        "ctr_pct": round(ctr, 2) if ctr else None,
        "estimated_waste_usd": round(total_waste, 2),
        "estimated_waste_pct": round(waste_pct, 1),
        "finding_count": len(findings),
        "high_severity_count": sum(1 for f in findings if f.get("severity") == "high"),
        "medium_severity_count": sum(1 for f in findings if f.get("severity") == "medium"),
        "brand_tier": brand_tier,
        "tier_label": tier_data.get("label", ""),
        "benchmark_cpl_ceiling": benchmark_cpl,
        "benchmark_cac_ceiling": benchmark_cac,
        "cpl_vs_benchmark": (
            "above" if cpl and benchmark_cpl and cpl > benchmark_cpl
            else "within" if cpl and benchmark_cpl
            else "n/a"
        ),
        "top_opportunities": top_opportunities,
    }


# -----------------------------------------------------------------------
# Suggestions generator (tone-controlled)
# -----------------------------------------------------------------------

SUGGESTION_DISCLAIMER = (
    "These are starting points for discussion, not recommendations to execute. "
    "Every lead source has nuance that requires human judgment and dealership context."
)


def generate_suggestions(
    findings: list[dict],
    funnel_alloc: dict,
    exec_summary: dict,
    benchmarks: dict,
    brand_tier: str,
) -> list[dict]:
    """Generate discussion-framed suggestions from audit findings."""
    suggestions = []

    # From waste findings
    for f in findings:
        rule = f.get("rule", "")

        if rule == "zero_conversion_spend":
            suggestions.append({
                "observation": f["observation"],
                "worth_discussing": (
                    f"Consider whether '{f['campaign']}' should be paused, "
                    f"restructured, or given different conversion actions to track."
                ),
                "context_needed": (
                    "Are there offline conversions (showroom ups, phone calls to "
                    "the main line) this campaign might be driving that aren't tracked?"
                ),
                "potential_risk": (
                    "Pausing a brand campaign could cede impression share to competitors. "
                    "Pausing a conquest campaign may be fine if the audience isn't converting."
                ),
                "priority": "high" if f["severity"] == "high" else "medium",
            })

        elif rule == "high_spend_low_return":
            suggestions.append({
                "observation": f["observation"],
                "worth_discussing": (
                    "Review campaign structure, keyword match types, and landing pages. "
                    "Is the spend going to broad match terms that don't convert?"
                ),
                "context_needed": (
                    "Does this campaign serve a brand-protection or awareness purpose "
                    "that isn't captured in lead metrics?"
                ),
                "potential_risk": (
                    "Cutting spend on a high-visibility campaign without understanding "
                    "its full attribution window could impact downstream conversions."
                ),
                "priority": "high",
            })

        elif rule == "search_term_bleed":
            suggestions.append({
                "observation": f["observation"],
                "worth_discussing": (
                    "Review the flagged search terms and add negatives where appropriate. "
                    "Consider tightening match types on broad match campaigns."
                ),
                "context_needed": (
                    "Is the current agency or ad manager actively managing negative "
                    "keyword lists? How frequently are search term reports reviewed?"
                ),
                "potential_risk": (
                    "Over-aggressive negative keywords could block legitimate long-tail "
                    "queries. Review individually before bulk-adding."
                ),
                "priority": "medium",
            })

        elif rule == "low_vdp_to_lead":
            suggestions.append({
                "observation": f["observation"],
                "worth_discussing": (
                    "The VDP pages are getting traffic but visitors aren't converting. "
                    "Worth reviewing VDP page experience, CTA placement, and form friction."
                ),
                "context_needed": (
                    "Is the website platform (Dealer.com, DealerOn, etc.) providing "
                    "a good mobile VDP experience? Are chat and text-to-buy available?"
                ),
                "potential_risk": (
                    "Low VDP-to-lead could be a website issue, not an ad issue. "
                    "Changing ad strategy won't fix a broken landing page."
                ),
                "priority": "medium",
            })

        elif rule == "geo_waste":
            suggestions.append({
                "observation": f["observation"],
                "worth_discussing": (
                    "Review geo targeting settings. Are campaigns using radius targeting "
                    "or are they set to 'presence or interest' which can leak outside market?"
                ),
                "context_needed": (
                    "Are there secondary markets the dealer intentionally targets? "
                    "Some dealers pull from a wide radius for specific models."
                ),
                "potential_risk": (
                    "Tightening geo too aggressively could miss customers who live "
                    "outside the radius but work nearby."
                ),
                "priority": "medium",
            })

    # Funnel allocation suggestions
    stages = funnel_alloc.get("stages", {})
    for stage, data in stages.items():
        if not data["within_range"]:
            direction = "over" if data["spend_pct"] > data["recommended_max_pct"] else "under"
            suggestions.append({
                "observation": (
                    f"Funnel stage '{stage}' is at {data['spend_pct']}% of spend "
                    f"(industry typical: {data['recommended_min_pct']}-{data['recommended_max_pct']}%)."
                ),
                "worth_discussing": (
                    f"This stage appears {direction}-allocated relative to industry norms. "
                    f"Worth reviewing whether the current mix matches the dealership's priorities."
                ),
                "context_needed": (
                    "Allocation norms are averages — a dealer in a conquest-heavy market "
                    "may intentionally over-index on brand/conquest."
                ),
                "potential_risk": (
                    "Shifting budget between funnel stages takes time to show results. "
                    "Don't expect immediate ROI changes."
                ),
                "priority": "low",
            })

    suggestions.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x["priority"], 3))
    return suggestions


# -----------------------------------------------------------------------
# Delta tracking
# -----------------------------------------------------------------------

def compute_delta(current: dict, prior_path: Optional[str]) -> Optional[dict]:
    """Compare current run against a prior period run."""
    if not prior_path or not Path(prior_path).exists():
        return None

    with open(prior_path) as f:
        prior = json.load(f)

    prior_summary = prior.get("executive_summary", {})
    current_summary = current.get("executive_summary", {})

    delta = {}
    metrics = [
        "total_spend", "total_leads", "cpl", "total_clicks",
        "total_impressions", "total_vdp_views", "estimated_waste_usd",
        "estimated_waste_pct", "finding_count",
    ]
    for m in metrics:
        curr_val = current_summary.get(m, 0) or 0
        prior_val = prior_summary.get(m, 0) or 0
        change = curr_val - prior_val
        pct_change = (change / prior_val * 100) if prior_val != 0 else None
        delta[m] = {
            "current": curr_val,
            "prior": prior_val,
            "change": round(change, 2),
            "pct_change": round(pct_change, 1) if pct_change is not None else None,
        }

    return delta


def save_run(audit_result: dict, client_slug: str, period: str):
    """Save audit result for future delta comparison."""
    runs_dir = SKILL_DIR / "runs"
    runs_dir.mkdir(exist_ok=True)
    out_path = runs_dir / f"{client_slug}_{period}.json"
    with open(out_path, "w") as f:
        json.dump(audit_result, f, indent=2, default=str)
    print(f"[Delta] Saved run snapshot: {out_path}")
    return str(out_path)


def find_prior_run(client_slug: str, period: str) -> Optional[str]:
    """Find the most recent prior run for delta comparison."""
    runs_dir = SKILL_DIR / "runs"
    if not runs_dir.exists():
        return None

    # Find files matching client slug, exclude current period
    prior_files = sorted(
        [f for f in runs_dir.glob(f"{client_slug}_*.json")
         if period not in f.name],
        reverse=True,
    )
    return str(prior_files[0]) if prior_files else None


# -----------------------------------------------------------------------
# Main orchestrator
# -----------------------------------------------------------------------

def run_audit(
    rows: list[dict],
    client_name: str,
    period: str,
    compare_prior: bool = False,
) -> dict:
    """
    Run the full waste audit pipeline on normalized data.

    Returns a dict with all audit results suitable for report generation.
    """
    thresholds = _load_thresholds()
    benchmarks = _load_benchmarks()
    brand_tier = _detect_brand_tier(client_name, benchmarks)
    client_slug = client_name.lower().replace(" ", "_").replace("'", "")

    print(f"\n[Audit] Client: {client_name}")
    print(f"[Audit] Period: {period}")
    print(f"[Audit] Brand tier: {brand_tier} ({benchmarks['tiers'][brand_tier]['label']})")
    print(f"[Audit] Rows to analyze: {len(rows)}")

    # 1. Classify funnel stages
    funnel_alloc = compute_funnel_allocation(rows)
    print(f"[Audit] Funnel allocation computed across {len(funnel_alloc['stages'])} stages")

    # 2. Run waste audit rules
    findings = []
    findings.extend(audit_zero_conversion_spend(rows, thresholds))
    findings.extend(audit_low_vdp_to_lead(rows, thresholds, brand_tier))
    findings.extend(audit_high_spend_low_return(rows, thresholds))
    findings.extend(audit_search_term_bleed(rows, thresholds))
    findings.extend(audit_geo_waste(rows, thresholds))
    findings.extend(audit_device_hour(rows, thresholds))
    print(f"[Audit] Waste rules generated {len(findings)} findings")

    # 3. Source performance
    source_perf = compute_source_performance(rows)
    print(f"[Audit] Source performance computed for {len(source_perf)} platforms")

    # 4. Executive summary
    exec_summary = compute_executive_summary(
        rows, findings, funnel_alloc, benchmarks, brand_tier
    )

    # 5. Suggestions
    suggestions = generate_suggestions(
        findings, funnel_alloc, exec_summary, benchmarks, brand_tier
    )
    print(f"[Audit] Generated {len(suggestions)} discussion suggestions")

    # 6. Assemble result
    result = {
        "client": client_name,
        "period": period,
        "brand_tier": brand_tier,
        "audit_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "executive_summary": exec_summary,
        "findings": findings,
        "funnel_allocation": funnel_alloc,
        "source_performance": source_perf,
        "suggestions": suggestions,
        "benchmarks_used": {
            "tier": brand_tier,
            "tier_label": benchmarks["tiers"][brand_tier]["label"],
            "source": benchmarks["_metadata"]["sources"],
            "last_updated": benchmarks["_metadata"]["last_updated"],
        },
        "suggestion_disclaimer": SUGGESTION_DISCLAIMER,
        "row_count": len(rows),
    }

    # 7. Delta comparison
    if compare_prior:
        prior_path = find_prior_run(client_slug, period)
        delta = compute_delta(result, prior_path)
        result["delta"] = delta
        if delta:
            print(f"[Audit] Delta computed against prior period")
        else:
            print(f"[Audit] No prior period found for delta comparison")

    # 8. Save run
    save_run(result, client_slug, period)

    return result
