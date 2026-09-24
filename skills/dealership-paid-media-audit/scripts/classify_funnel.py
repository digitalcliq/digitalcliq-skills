"""
classify_funnel.py — Automotive funnel stage classifier for paid media campaigns.

Classifies campaigns/keywords/ad sets into one of four funnel stages:
  - brand_conquest: OEM brand terms, model names, competitor conquest
  - inventory_vdp:  Model + trim, year, "for sale near me", VIN-level
  - consideration:  "best SUV under 40k", comparison searches
  - service_fixedops: Oil change, recall, service, parts

Also detects misallocated spend (e.g., brand keywords in a consideration campaign).
"""

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

# Brand / model terms (OEM brand searches, model-specific)
BRAND_PATTERNS = [
    # OEM brand names
    r"\b(nissan|toyota|honda|ford|chevrolet|chevy|ram|jeep|dodge|chrysler|"
    r"bmw|mercedes|audi|lexus|porsche|hyundai|kia|mazda|subaru|volkswagen|"
    r"vw|gmc|buick|cadillac|lincoln|acura|infiniti|volvo|genesis|"
    r"land rover|mitsubishi|fiat)\b",
    # Common model names
    r"\b(rogue|altima|sentra|frontier|pathfinder|murano|armada|kicks|versa|leaf|"
    r"camry|corolla|rav4|highlander|tacoma|tundra|4runner|"
    r"civic|accord|cr-v|hr-v|pilot|odyssey|"
    r"f-150|f150|bronco|explorer|escape|maverick|ranger|mustang|"
    r"silverado|equinox|traverse|blazer|tahoe|suburban|colorado|"
    r"1500|2500|3500|wrangler|grand cherokee|cherokee|gladiator|compass|"
    r"charger|durango|challenger|pacifica|"
    r"3 series|5 series|x3|x5|x1|x7|"
    r"elantra|tucson|santa fe|palisade|ioniq|"
    r"sportage|telluride|forte|seltos|ev6|"
    r"cx-5|cx-50|cx-90|mazda3|"
    r"outback|forester|crosstrek|impreza|"
    r"tiguan|jetta|atlas|taos|id.4)\b",
    # Conquest patterns
    r"\b(vs|versus|compare|comparison|competitor|alternative|switch from|"
    r"better than|instead of)\b",
]

# Inventory / VDP-level patterns (high purchase intent)
INVENTORY_PATTERNS = [
    r"\b(for sale|in stock|inventory|near me|dealer|dealership|"
    r"price|pricing|cost|msrp|lease|finance|"
    r"new \d{4}|used \d{4}|pre-owned|certified|cpo|"
    r"test drive|schedule|appointment|"
    r"vin|stock number|stk#|"
    r"trim|sport|limited|platinum|pro|sr|sv|sl|"
    r"4x4|4wd|awd|2wd|"
    r"buy|purchase|get a|shop)\b",
    r"\b\d{4}\s+(nissan|toyota|honda|ford|chevy|ram|jeep|bmw)\b",
]

# Consideration / research patterns (mid-funnel)
CONSIDERATION_PATTERNS = [
    r"\b(best|top|review|reviews|rating|ratings|reliable|reliability|"
    r"safest|safety|fuel economy|mpg|gas mileage|"
    r"comparison|compare|vs\.|versus|"
    r"suv under|truck under|car under|sedan under|"
    r"family|commuter|towing|off-road|"
    r"what is|which is|how much|should i|"
    r"electric|hybrid|ev|phev|plug-in|"
    r"lease deals|best deals|incentives|rebates|"
    r"3 row|third row|cargo space|"
    r"affordable|budget|cheap|value)\b",
]

# Service / Fixed Ops patterns
SERVICE_PATTERNS = [
    r"\b(oil change|tire rotation|brake|brakes|transmission|"
    r"service|maintenance|repair|warranty|recall|"
    r"parts|accessories|oem parts|genuine parts|"
    r"appointment|schedule service|book service|"
    r"check engine|battery|alignment|inspection|"
    r"body shop|collision|paint|detail|"
    r"filter|fluid|coolant|spark plug|"
    r"miles service|k service|30k|60k|90k)\b",
]


def _matches_any(text: str, patterns: list[str]) -> int:
    """Return count of pattern matches in text."""
    count = 0
    for pat in patterns:
        count += len(re.findall(pat, text, re.IGNORECASE))
    return count


def classify_campaign(
    campaign_name: str,
    ad_group: str = "",
    keyword: str = "",
    search_term: str = "",
) -> dict:
    """
    Classify a campaign/keyword/ad into a funnel stage.

    Returns dict with:
      - stage: brand_conquest | inventory_vdp | consideration | service_fixedops
      - confidence: high | medium | low
      - signals: list of matched patterns
      - misallocated: bool (True if keyword stage doesn't match campaign stage)
    """
    # Combine all text signals, prioritizing keyword > search_term > ad_group > campaign
    all_text = f"{keyword} {search_term} {ad_group} {campaign_name}".lower().strip()
    keyword_text = f"{keyword} {search_term}".lower().strip()
    campaign_text = campaign_name.lower().strip()

    scores = {
        "brand_conquest": _matches_any(all_text, BRAND_PATTERNS),
        "inventory_vdp": _matches_any(all_text, INVENTORY_PATTERNS),
        "consideration": _matches_any(all_text, CONSIDERATION_PATTERNS),
        "service_fixedops": _matches_any(all_text, SERVICE_PATTERNS),
    }

    # Determine primary stage from highest score
    if max(scores.values()) == 0:
        stage = "brand_conquest"  # default fallback for unclassifiable
        confidence = "low"
    else:
        stage = max(scores, key=scores.get)
        total = sum(scores.values())
        ratio = scores[stage] / total if total > 0 else 0
        if ratio > 0.7:
            confidence = "high"
        elif ratio > 0.4:
            confidence = "medium"
        else:
            confidence = "low"

    # Collect signal evidence
    signals = []
    for pat_list, label in [
        (BRAND_PATTERNS, "brand"),
        (INVENTORY_PATTERNS, "inventory"),
        (CONSIDERATION_PATTERNS, "consideration"),
        (SERVICE_PATTERNS, "service"),
    ]:
        for pat in pat_list:
            found = re.findall(pat, all_text, re.IGNORECASE)
            if found:
                signals.extend([f"{label}:{m}" for m in found[:3]])

    # Misallocation detection: keyword stage vs campaign name stage
    misallocated = False
    misallocation_detail = ""
    if keyword_text.strip():
        kw_scores = {
            "brand_conquest": _matches_any(keyword_text, BRAND_PATTERNS),
            "inventory_vdp": _matches_any(keyword_text, INVENTORY_PATTERNS),
            "consideration": _matches_any(keyword_text, CONSIDERATION_PATTERNS),
            "service_fixedops": _matches_any(keyword_text, SERVICE_PATTERNS),
        }
        camp_scores = {
            "brand_conquest": _matches_any(campaign_text, BRAND_PATTERNS),
            "inventory_vdp": _matches_any(campaign_text, INVENTORY_PATTERNS),
            "consideration": _matches_any(campaign_text, CONSIDERATION_PATTERNS),
            "service_fixedops": _matches_any(campaign_text, SERVICE_PATTERNS),
        }
        kw_stage = max(kw_scores, key=kw_scores.get) if max(kw_scores.values()) > 0 else None
        camp_stage = max(camp_scores, key=camp_scores.get) if max(camp_scores.values()) > 0 else None
        if kw_stage and camp_stage and kw_stage != camp_stage:
            misallocated = True
            misallocation_detail = (
                f"Keyword signals '{kw_stage}' but campaign "
                f"structure suggests '{camp_stage}'"
            )

    return {
        "stage": stage,
        "confidence": confidence,
        "scores": scores,
        "signals": signals[:10],
        "misallocated": misallocated,
        "misallocation_detail": misallocation_detail,
    }


# Primary KPI mapping per funnel stage
STAGE_PRIMARY_KPIS = {
    "brand_conquest": ["impression_share", "cpl", "clicks"],
    "inventory_vdp": ["vdp_to_lead_ratio", "cpl", "vdp_views"],
    "consideration": ["srp_views", "engagement_depth", "sessions"],
    "service_fixedops": ["phone_calls", "form_fills", "appointments"],
}

# Recommended allocation ranges (% of total spend) — industry typical
STAGE_ALLOCATION_RANGES = {
    "brand_conquest": {"min_pct": 15, "max_pct": 30, "notes": "Protect brand terms. Low CPC, high conversion."},
    "inventory_vdp": {"min_pct": 35, "max_pct": 55, "notes": "Highest intent. Drive VDP traffic and leads."},
    "consideration": {"min_pct": 10, "max_pct": 25, "notes": "Top-of-funnel. Longer attribution window."},
    "service_fixedops": {"min_pct": 5, "max_pct": 15, "notes": "Fixed ops drives retention and LTV."},
}


if __name__ == "__main__":
    # Quick test
    tests = [
        ("Brand - Nissan", "Nissan Rogue", "nissan rogue near me", ""),
        ("Conquest - Toyota", "vs Toyota", "nissan rogue vs toyota rav4", ""),
        ("Service - Oil Change", "Oil Change", "oil change near me", ""),
        ("Generic PMax", "", "", "best suv under 40k"),
        ("New Inventory", "2026 Rogue", "2026 nissan rogue sv for sale", ""),
    ]
    for camp, ag, kw, st in tests:
        result = classify_campaign(camp, ag, kw, st)
        print(f"  {camp:30s} → {result['stage']:20s} ({result['confidence']}) "
              f"{'⚠️ MISALLOCATED' if result['misallocated'] else ''}")
