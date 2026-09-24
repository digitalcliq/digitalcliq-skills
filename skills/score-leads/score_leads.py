#!/usr/bin/env python3
"""
Lead Source Scoring Engine for Automotive Dealerships
Created by DigitalCLIQ

Reads a CSV of lead source data, scores each source on a 1-10 scale,
assigns tier rankings, and outputs a formatted Excel spreadsheet.

Usage: python3 score_leads.py <input.csv> <output.xlsx> <store_name> <date_range>
"""

import sys
import csv
import os
import json
from datetime import datetime

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.worksheet.properties import PageSetupProperties
    from openpyxl.worksheet.pagebreak import Break
except ImportError:
    print("ERROR: openpyxl not installed. Run: pip3 install openpyxl", file=sys.stderr)
    sys.exit(1)

# DigitalCLIQ branding: design-system tokens (Resources/design-system/Design-System.md).
# WHITE knockout logo on a Digital Blue masthead band, top-left of every sheet.
LOGO_PATH = "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png"
DIGITAL_BLUE = "405FAB"   # masthead / header fills, emphasis
SKY_BLUE = "6B9DD4"       # strong / above-benchmark treatment
WARM_GREY = "949592"      # weak / muted / captions
NAVY_DEEP = "070A15"      # worst-tier / below-benchmark chip (never red)
TILE_BLUE = "2E4780"      # deep accents, section headings
CALLOUT_TINT = "EDF2F9"   # light fills, alternating rows
BORDER_BLUE = "D8E1F0"    # table borders


def _add_brand_logo(ws, anchor_cell="A1", row_span=3, col_span=3, logo_width=160):
    """Place the DigitalCLIQ logo at anchor_cell on a Digital Blue masthead band.
    The cells the logo overlays are filled Digital Blue; the rest of the sheet is untouched."""
    masthead_fill = PatternFill(start_color=DIGITAL_BLUE, end_color=DIGITAL_BLUE, fill_type="solid")
    # Anchor cell is e.g. "A1": derive starting row/col
    from openpyxl.utils.cell import coordinate_from_string, column_index_from_string
    col_letter, start_row = coordinate_from_string(anchor_cell)
    start_col = column_index_from_string(col_letter)
    # Fill the masthead cells with Digital Blue
    for r in range(start_row, start_row + row_span):
        for c in range(start_col, start_col + col_span):
            ws.cell(row=r, column=c).fill = masthead_fill
    # Insert the logo (WHITE knockout on the Digital Blue masthead, top-left)
    if not os.path.exists(LOGO_PATH):
        raise RuntimeError(
            f"DigitalCLIQ logo not found at: {LOGO_PATH!r}\n"
            f"Canonical path: /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png"
        )
    img = XLImage(LOGO_PATH)
    img.width = logo_width
    # Native mark is 500x154; anything else stretches the wordmark.
    img.height = round(logo_width * 154 / 500)
    ws.add_image(img, anchor_cell)
    ws.sheet_view.showGridLines = False



# --- Data Validation ---

REQUIRED_CSV_COLUMNS = [
    "source", "leads", "contact", "contact_pct",
    "appts", "appts_pct", "shows", "shows_pct",
    "sales", "sales_pct",
]

NUMERIC_CSV_COLUMNS = ["leads", "contact", "contact_pct", "appts",
                       "appts_pct", "shows", "shows_pct", "sales", "sales_pct"]


def validate_data(headers, rows, source_path="<input>"):
    """
    Validate CSV lead source data before scoring.

    Checks:
      1. All required columns exist
      2. Data types are parseable (numeric columns are numbers)
      3. No empty/null values in required fields (source, leads, sales)

    Args:
        headers: list of column names from DictReader.fieldnames
        rows: list of dicts from DictReader

    Returns (is_valid, errors) where errors is a list of descriptive strings.
    """
    errors = []

    # ── 1. Required columns ───────────────────────────────────────
    if headers is None:
        errors.append(
            "CSV headers: no headers found\n"
            f"  Expected: {REQUIRED_CSV_COLUMNS}\n"
            "  Actual:   None (empty file?)"
        )
        return False, errors

    missing = [c for c in REQUIRED_CSV_COLUMNS if c not in headers]
    if missing:
        errors.append(
            f"CSV columns: missing required columns\n"
            f"  Expected: {REQUIRED_CSV_COLUMNS}\n"
            f"  Missing:  {missing}\n"
            f"  Actual:   {list(headers)}"
        )

    # ── 2. Data rows ──────────────────────────────────────────────
    if not rows:
        errors.append(
            "CSV data: no data rows found\n"
            "  Expected: at least 1 data row\n"
            "  Actual:   0 rows"
        )
    else:
        for i, row in enumerate(rows):
            # Source name must be non-empty
            source = row.get("source", "").strip()
            if not source:
                errors.append(
                    f"Row {i+1}: 'source' field is empty\n"
                    f"  Expected: non-empty string\n"
                    f"  Actual:   \"\""
                )

            # Numeric columns must be parseable
            for col in NUMERIC_CSV_COLUMNS:
                if col not in headers:
                    continue
                val = row.get(col, "").strip()
                if val == "":
                    continue  # Empty is allowed (defaults to 0)
                cleaned = val.replace("%", "").replace(",", "").strip()
                if cleaned:
                    try:
                        float(cleaned)
                    except ValueError:
                        errors.append(
                            f"Row {i+1} ({source}).{col}: not a valid number\n"
                            f"  Expected: numeric value\n"
                            f"  Actual:   {repr(val)}"
                        )

            # Cap error count
            if len(errors) >= 50:
                break

    # ── Report ────────────────────────────────────────────────────
    if errors:
        shown = errors[:50]
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"VALIDATION FAILED: {source_path}", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        print(f"{len(errors)} error(s) found:\n", file=sys.stderr)
        for idx, e in enumerate(shown, 1):
            print(f"  {idx}. {e}\n", file=sys.stderr)
        if len(errors) > 50:
            print(f"  ... and {len(errors) - 50} more errors", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)
        return False, errors

    return True, []


# --- Scoring Weights ---
WEIGHTS = {
    "sale_rate": 0.40,
    "sales_volume": 0.15,
    "show_rate": 0.20,
    "appt_rate": 0.15,
    "contact_rate": 0.10,
}

# Shown wherever contact figures would appear when the CRM export has no
# contact-made column (e.g. the Momentum "Lead Source Report").
TEKION_CONTACT_NOTE = (
    "Contact # and Contact % come from Tekion's Internet/OEM Leads Engaged metric, which Tekion tracks "
    "for internet and OEM leads only. Walk-in, service, referral, previous-customer and other in-store "
    "sources show 0% because the metric is not measured for them, not because nobody spoke to the customer."
)

CONTACT_NA_NOTE = (
    "Contact rate is not reported in this CRM export, so Contact # and Contact % read n/a. "
    "The 10% contact weight was redistributed across the other four factors in proportion "
    "(Sale Rate 44%, Show Rate 22%, Volume 17%, Appt Rate 17%)."
)

# --- New vs Used Car Adjustment ---
# New car leads naturally close at a lower rate than used car leads because
# used inventory is 1-of-1 (unique VIN, miles, price), creating higher urgency.
# To level the playing field, new car sources get a 1.5x boost on sale rate
# before scoring so they aren't unfairly penalized.
NEW_CAR_SALE_RATE_BOOST = 1.5

# Patterns to identify USED car sources (matched case-insensitively against source name).
# Everything else defaults to NEW.
USED_SOURCE_PATTERNS = [
    "autotrader",
    "carfax",
    "cargurus",
    "cars.com",
]

# --- Credit Application Exclusion ---
# Credit app leads are not true acquisition sources. The customer already came in
# on another source, was told to fill out a credit application during the deal
# process, and then the credit app gets "credit" for the sale. These always show
# near-100% close rates with low volume, which skews the scoring curve.
# They are kept in the report but excluded from scoring and flagged with a disclaimer.
CREDIT_APP_PATTERNS = [
    "credit app",
    "credit application",
    "700 credit",
    "quick qualify",
]

CREDIT_APP_DISCLAIMER = (
    "Credit applications are not an acquisition source. These customers originated "
    "from another lead channel and were re-attributed when they submitted a credit "
    "application during the purchase process. Scoring is not applicable."
)

# --- Unattributed-sale bucket exclusion ---
# Momentum (and other CRMs) report DMS-matched sales that carry no lead source under
# a "Not Specified" style bucket. It is not a lead source: scoring it produces a
# multi-thousand-percent close rate that tops the scorecard. Treated like a credit
# app (kept, shaded, N/A tier, out of the store close rate) with its own note.
UNATTRIBUTED_PATTERNS = [
    "not specified",
    "unspecified",
    "no source",
    "unknown source",
]


def unattributed_disclaimer(rows):
    """Note for the shaded unattributed rows, with this report's counts filled in."""
    rows = [r for r in rows if r.get("is_unattributed")]
    if not rows:
        return None
    names = ", ".join(f"'{r['source']}'" for r in rows)
    sales = sum(r["sales"] for r in rows)
    leads = sum(r["leads"] for r in rows)
    return (f"{names} is the CRM's bucket for DMS sales with no lead source attached "
            f"({sales:,} sales on {leads:,} leads in this window). It is not a lead source, so it is "
            f"excluded from scoring and from the store close rate. Practically, {sales:,} sold units "
            f"cannot be credited to any channel until the source is captured at the lead.")

# --- Tier Definitions ---
# Palette-only tier treatment (Design-System): the explicit A/B/C/D letter in the
# Tier column always carries the meaning; color is treatment, not the signal.
TIERS = [
    (8, "A", "405FAB"),   # A Tier: Digital Blue (top performer)
    (5, "B", "6B9DD4"),   # B Tier: Sky Blue (solid)
    (3, "C", "949592"),   # C Tier: Warm Grey (underperforming)
    (1, "D", "070A15"),   # D Tier: Navy Deep (poor ROI)
]

# ============================================================================
# NADA / Industry Benchmark Layer
# ----------------------------------------------------------------------------
# A SEPARATE absolute benchmark layer that sits ALONGSIDE the relative 1-10
# score (it does not change the score). Each source's actual close rate is
# compared to the NADA/industry benchmark for ITS source-type and the store's
# brand tier (luxury / mainstream / powersports), then flagged Above / At /
# Below. The store's overall close rate is also graded vs the industry blend.
# All benchmark numbers live in reference/nada_benchmarks.json (editable).
# ============================================================================

BENCHMARK_REFERENCE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "reference", "nada_benchmarks.json"
)

# A source must have at least this many leads for a benchmark flag to be
# meaningful. Below this, close rate is statistical noise (1 lead / 1 sale = 100%).
MIN_BENCHMARK_LEADS = 10

# Low-volume sources (fewer than MIN_BENCHMARK_LEADS leads) are an unproven sample,
# so their relative score is capped here: a 1-lead/1-sale source should never
# out-rank a real producer just because its rate is 100%.
LOW_VOL_SCORE_CAP = 5

# How far from benchmark counts as Above / Below (vs At). +/- 10%.
BENCHMARK_BAND = 0.10

# Maps a source name to a benchmark category. First match wins, so order
# matters: most-specific / list-type sources are checked before the website
# catch-all. A source that matches nothing defaults to "website" (internet).
BENCHMARK_CATEGORY_PATTERNS = [
    ("data_list", [
        "financial services", "bmw financial", "fs list", "fs lease",
        "fs loan", "fs warranty", "fs cpo", "fs active", "fs call",
        "fs customer", "owner in market", "current owner", "oem event",
        "events / tour", "tour", "gen m", "driving school", "equity mining",
        "conquest", "mastermind", "black book", "intellafuel", "data list",
        "re-engagement", "reengagement", "warranty exp", "cpo expiration",
        "lease customer intent", "loan customer intent", "back in market",
        "first watch", "hot list", "in market", "inmarketsolution",
    ]),
    # Floor / showroom / geo traffic: benchmarked at the walk-in rate (~25%),
    # checked before owned_equity so "walk-in" etc. don't fall into the 38% bucket.
    ("walk_in", [
        "walk-in", "walk in", "walkin", "showroom", "show room", "desk",
        "phone-up", "phone up", "drove by", "drive by", "drives by",
        "lives in area", "works in area", "floor up", "location",
    ]),
    ("owned_equity", [
        "repeat", "previous customer", "referral", "service drive",
        "service dept", "service referral", "service", "loyalty",
        "be-back", "be back", "equity",
    ]),
    ("phone", ["phone", "call", "click to call", "click-to-call"]),
    ("third_party", [
        "autotrader", "auto trader", "cars.com", "carscom", "cargurus",
        "car gurus", "edmunds", "truecar", "true car", "carfax",
        "third party", "third-party", "3rd party",
    ]),
    # OEM / factory programs. Brand-extensible: add new OEM-program tokens here
    # as new franchises come through (e.g. "shop click drive", "mopar").
    ("oem", ["bmw oem", "bmwusa", "bmw usa", "bmw group", "bmw na", "factory",
             "maco", "oem", "manufacturer", "nissan usa", "nissanusa",
             "choose nissan", "vpp", "nissan@", "usa leads"]),
    ("chat", ["gubagoo", "gobagoo", "podium", "roadster", "chat",
              "virtual retail", "live person", "carnow", "activengage"]),
    ("website", ["website", "dealer website", "apollo", "nabthat",
                 "dealer inspire", "dealer.com", "dealeron", "internet",
                 "web lead", "google", "form", "vdp", "sincro", "fox dealer"]),
]


def load_benchmarks(path=BENCHMARK_REFERENCE_PATH):
    """Load the embedded NADA/industry benchmark reference file.

    Returns the parsed dict, or None if the file is missing/unreadable (the
    skill degrades gracefully to relative-only scoring with a stderr warning).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        print(f"WARNING: benchmark reference not loaded ({e}). "
              f"Falling back to relative-only scoring.", file=sys.stderr)
        return None


def detect_brand_tier(store_name, benchmarks):
    """Detect benchmark tier (luxury / mainstream / powersports) from store name.

    Defaults to 'mainstream' when no franchise keyword matches.
    """
    if not benchmarks:
        return "mainstream"
    tmap = benchmarks.get("brand_tier_map", {})
    name = (store_name or "").lower()
    for tier in ("luxury", "powersports", "mainstream"):
        for kw in tmap.get(tier, []):
            if kw in name:
                return tier
    return "mainstream"


def classify_benchmark_category(source_name):
    """Classify a source into a benchmark category for close-rate comparison."""
    name = (source_name or "").lower()
    for category, patterns in BENCHMARK_CATEGORY_PATTERNS:
        for p in patterns:
            if p in name:
                return category
    return "website"  # default: treat unknown e-commerce leads as internet


def annotate_benchmarks(rows, tier, benchmarks):
    """Attach benchmark fields to each row: category, benchmark rate, and flag.

    Adds (per row): bench_category, bench_rate (fraction or None), bench_flag
    in {"Above", "At", "Below", "Low vol", "N/A"}. Credit apps and data lists
    are not benchmarked (they are not acquisition sources). This does NOT touch
    the relative 1-10 score.
    """
    if not benchmarks:
        for r in rows:
            r["bench_category"] = None
            r["bench_rate"] = None
            r["bench_flag"] = "N/A"
        return rows

    cats = benchmarks["close_rate_benchmarks"]["categories"]

    for r in rows:
        if r["source"].lower() == "totals":
            r["bench_category"] = None
            r["bench_rate"] = None
            r["bench_flag"] = ""
            continue

        if r.get("is_credit_app", False):
            r["bench_category"] = "credit_app"
            r["bench_rate"] = None
            r["bench_flag"] = "N/A"
            continue

        category = classify_benchmark_category(r["source"])
        r["bench_category"] = category
        cdef = cats.get(category, cats["website"])
        bench = cdef.get(tier)
        r["bench_rate"] = bench  # fraction (e.g. 0.10) or None for data lists

        close = (r["sales"] / r["leads"]) if r["leads"] > 0 else r["sales_pct"] / 100.0
        if bench is None:
            r["bench_flag"] = "N/A"
        elif r["leads"] < MIN_BENCHMARK_LEADS:
            r["bench_flag"] = "Low vol"
        elif close >= bench * (1 + BENCHMARK_BAND):
            r["bench_flag"] = "Above"
        elif close <= bench * (1 - BENCHMARK_BAND):
            r["bench_flag"] = "Below"
        else:
            r["bench_flag"] = "At"

    return rows


def compute_store_benchmark(rows, tier, benchmarks):
    """Grade the store's actual close rate against the close rate industry would
    be expected to deliver ON THIS REPORT'S LEAD MIX.

    The expected rate is the lead-weighted average of each acquisition source's
    own source-type benchmark. This auto-adjusts to the report: an internet-only
    e-commerce export is judged against the internet/marketplace/chat blend (low),
    while a full-source scorecard that includes walk-ins and owned equity is held
    to a higher bar. That is fairer than one fixed store number and prevents an
    e-commerce-only report from looking like a failure against a full-store blend.

    Credit apps and OEM/FS data lists are excluded (not inbound buy-leads, and not
    benchmarked). Returns the store close rate, the expected (benchmark) rate, the
    delta in points, a verdict, and counts: or None if unavailable.
    """
    if not benchmarks:
        return None

    def is_acquisition(r):
        if r["source"].lower() == "totals":
            return False
        if r.get("is_credit_app", False):
            return False
        if r.get("bench_category") == "data_list":
            return False
        return r.get("bench_rate") is not None

    data = [r for r in rows if is_acquisition(r)]
    leads = sum(r["leads"] for r in data)
    sales = sum(r["sales"] for r in data)
    excluded = [r for r in rows if r["source"].lower() != "totals" and not is_acquisition(r)]
    excluded_leads = sum(r["leads"] for r in excluded)

    if leads <= 0:
        return None

    store_rate = sales / leads
    # Lead-weighted expected close from each source's own source-type benchmark.
    expected = sum(r["leads"] * r["bench_rate"] for r in data) / leads
    delta_pts = (store_rate - expected) * 100

    if store_rate >= expected * (1 + BENCHMARK_BAND):
        verdict = "Above"
    elif store_rate <= expected * (1 - BENCHMARK_BAND):
        verdict = "Below"
    else:
        verdict = "At"

    return {
        "store_rate": store_rate,
        "benchmark": expected,
        "delta_pts": delta_pts,
        "verdict": verdict,
        "leads": leads,
        "sales": sales,
        "excluded_leads": excluded_leads,
        "source": ("Expected close is the lead-weighted average of each acquisition "
                   "source's NADA source-type benchmark for this tier, so the store is "
                   "judged against its own lead mix, not a fixed blend."),
    }


# Display colors for the benchmark flags: palette treatments only; the flag TEXT
# (Above / At / Below / Low vol / N/A) carries the meaning.
BENCHMARK_FLAG_COLORS = {
    "Above": "6B9DD4",   # Sky Blue = strong
    "At": "405FAB",      # Digital Blue = at benchmark
    "Below": "070A15",   # Navy Deep = below (matches D-tier treatment)
    "Low vol": "949592", # Warm Grey = muted
    "N/A": "949592",     # Warm Grey = muted
    "": "FFFFFF",
}


def classify_source_type(source_name):
    """Classify a lead source as 'New' or 'Used' based on source name patterns.

    Used car sources are 3rd-party marketplace sites (AutoTrader, CARFAX,
    CarGurus, Cars.com). Everything else: dealer website, OEM/factory,
    TrueCar, Costco, trade tools, paid social: defaults to New.
    """
    name_lower = source_name.lower()
    for pattern in USED_SOURCE_PATTERNS:
        if pattern in name_lower:
            return "Used"
    return "New"


def is_credit_app_source(source_name):
    """Check if a source is a credit application (not a true acquisition source)."""
    name_lower = source_name.lower()
    for pattern in CREDIT_APP_PATTERNS:
        if pattern in name_lower:
            return True
    return False


def is_unattributed_source(source_name):
    """Check if a source is the CRM's unattributed-sale bucket (not a lead source)."""
    name_lower = source_name.lower().strip()
    return any(p in name_lower for p in UNATTRIBUTED_PATTERNS)


def parse_float(val):
    """Safely parse a float from a string, stripping % signs."""
    if val is None or val.strip() == "":
        return 0.0
    return float(val.strip().replace("%", ""))


def parse_int(val):
    """Safely parse an int from a string."""
    if val is None or val.strip() == "":
        return 0
    return int(float(val.strip()))


def load_data(csv_path):
    """Load lead source data from CSV and classify each source as New or Used."""
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            source = row["source"].strip()
            rows.append({
                "source": source,
                "source_type": classify_source_type(source),
                "is_credit_app": is_credit_app_source(source) or is_unattributed_source(source),
                "is_unattributed": is_unattributed_source(source),
                "leads": parse_int(row["leads"]),
                "contact": parse_int(row["contact"]),
                "contact_pct": parse_float(row["contact_pct"]),
                "appts": parse_int(row["appts"]),
                "appts_pct": parse_float(row["appts_pct"]),
                "shows": parse_int(row["shows"]),
                "shows_pct": parse_float(row["shows_pct"]),
                "sales": parse_int(row["sales"]),
                "sales_pct": parse_float(row["sales_pct"]),
            })
    return rows


def score_sources(rows, contact_available=True):
    """Score each lead source on a 1-10 scale using weighted composite.

    New car sources receive a 1.5x boost on their sale rate before
    normalization to compensate for the structural disadvantage vs used
    car leads (used inventory is 1-of-1, so close rates are naturally higher).

    Credit application sources are excluded from scoring entirely: they are
    not true acquisition sources and would skew the curve with artificially
    high close rates. They are kept in the output with tier "N/A".
    """
    if not rows:
        return rows

    # No contact column in the export: drop its weight and renormalize the rest.
    weights = dict(WEIGHTS)
    if not contact_available:
        weights["contact_rate"] = 0.0
        tot = sum(weights.values())
        weights = {k: v / tot for k, v in weights.items()}

    # Separate credit app sources: they don't participate in scoring
    scoreable = [r for r in rows if not r.get("is_credit_app", False)]
    credit_apps = [r for r in rows if r.get("is_credit_app", False)]

    # Mark credit apps with N/A score and tier
    for r in credit_apps:
        r["adjusted_sales_pct"] = r["sales_pct"]
        r["score"] = None
        r["tier"] = "N/A"

    # Apply new car boost to sale rate before finding max values
    for r in scoreable:
        if r["source_type"] == "New":
            r["adjusted_sales_pct"] = min(r["sales_pct"] * NEW_CAR_SALE_RATE_BOOST, 100.0)
        else:
            r["adjusted_sales_pct"] = r["sales_pct"]

    # Find max values for relative scoring (using adjusted sale rate, scoreable only)
    max_sale_rate = max((r["adjusted_sales_pct"] for r in scoreable), default=1) or 1
    max_sales_vol = max((r["sales"] for r in scoreable), default=1) or 1
    max_show_rate = max((r["shows_pct"] for r in scoreable), default=1) or 1
    max_appt_rate = max((r["appts_pct"] for r in scoreable), default=1) or 1
    max_contact_rate = max((r["contact_pct"] for r in scoreable), default=1) or 1

    for r in scoreable:
        # Normalize each factor to 0-1 range relative to best in report
        sale_rate_norm = r["adjusted_sales_pct"] / max_sale_rate
        sales_vol_norm = r["sales"] / max_sales_vol
        show_rate_norm = r["shows_pct"] / max_show_rate
        appt_rate_norm = r["appts_pct"] / max_appt_rate
        contact_rate_norm = min(r["contact_pct"], 100.0) / min(max_contact_rate, 100.0) if max_contact_rate > 0 else 0

        # Weighted composite (0-1)
        composite = (
            weights["sale_rate"] * sale_rate_norm
            + weights["sales_volume"] * sales_vol_norm
            + weights["show_rate"] * show_rate_norm
            + weights["appt_rate"] * appt_rate_norm
            + weights["contact_rate"] * contact_rate_norm
        )

        # Map to 1-10 scale (floor of 1, ceiling of 10)
        score = max(1, min(10, round(composite * 10)))

        # Low-volume cap: unproven sample can't out-rank real producers.
        if r["leads"] < MIN_BENCHMARK_LEADS:
            score = min(score, LOW_VOL_SCORE_CAP)
            r["low_vol"] = True
        else:
            r["low_vol"] = False
        r["score"] = score

        # Assign tier
        r["tier"] = "D"
        for threshold, tier_label, _ in TIERS:
            if score >= threshold:
                r["tier"] = tier_label
                break

    # Sort scoreable by score descending, then by sales descending
    scoreable.sort(key=lambda r: (r["score"], r["sales"]), reverse=True)

    # Credit apps go at the bottom, sorted by sales descending
    credit_apps.sort(key=lambda r: r["sales"], reverse=True)

    return scoreable + credit_apps


def get_tier_color(tier):
    """Get hex fill color for a tier."""
    for _, tier_label, color in TIERS:
        if tier == tier_label:
            return color
    return "949592"


def _store_banner(store_bench, tier_label):
    """Build the store self-score banner text + fill color.

    Shared by the Summary tab and the Lead Source Scores tab so the two
    banners can never drift apart."""
    banner_colors = {"Above": SKY_BLUE, "At": DIGITAL_BLUE, "Below": NAVY_DEEP}
    bcolor = banner_colors.get(store_bench["verdict"], DIGITAL_BLUE)
    verb = {"Above": "ABOVE", "At": "AT", "Below": "BELOW"}[store_bench["verdict"]]
    excl = store_bench.get("excluded_leads", 0)
    excl_txt = (f"  |  excludes {excl:,} data-list/credit-app leads" if excl else "")
    text = (
        f"STORE SELF-SCORE:  {store_bench['store_rate']*100:.1f}% close on acquisition leads  "
        f"vs  {store_bench['benchmark']*100:.1f}% {tier_label.lower()} industry expectation for this lead mix  "
        + (f"|  AT expectation ({store_bench['delta_pts']:+.1f} pts)  " if verb == "AT"
           else f"|  {verb} by {abs(store_bench['delta_pts']):.1f} pts  ")
        + 
        f"({store_bench['sales']:,} sales / {store_bench['leads']:,} leads{excl_txt})"
    )
    return text, bcolor


# Legend definitions shared by the Summary tab's "How to read" section.
# Palette treatment only: the letter/flag text carries the meaning.
TIER_LEGEND = [
    ("A", "405FAB", "Top Performer (8-10)"),
    ("B", "6B9DD4", "Solid Source (5-7)"),
    ("C", "949592", "Underperforming (3-4)"),
    ("D", "070A15", "Poor ROI (1-2)"),
    ("N/A", "949592", "Not scored: credit app or unattributed DMS sales, see notes on the Scores tab"),
]

BENCH_LEGEND = [
    ("Above", "6B9DD4", "Closes 10%+ above the NADA industry rate for its source type"),
    ("At", "405FAB", "Within +/-10% of the NADA industry rate for its source type"),
    ("Below", "070A15", "Closes 10%+ below the NADA industry rate - handling/process leak"),
    ("Low vol", "949592", f"Fewer than {MIN_BENCHMARK_LEADS} leads - too small to benchmark reliably"),
    ("N/A", "949592", "Not an acquisition source (data list / credit app) - not benchmarked"),
]

BENCH_NOTE = (
    "Benchmark layer is SEPARATE from the 1-10 score. The score ranks sources relative to each "
    "other in this report; the NADA Bench % / vs Bench columns grade each source's actual close "
    "rate against the national industry rate for its source type and this store's brand tier. "
    "See the NADA Benchmarks tab for every figure and its source."
)


def build_summary_tab(wb, rows, store_name, date_range, tier, store_bench,
                      contact_available=True):
    """Styled Summary tab, FIRST in tab order (Design-System §4).

    Title block, key stats as large Dosis cells with Sky Blue numbers, the
    store self-score banner, tier mix, top sources, and how-to-read notes."""
    ws = wb.create_sheet("Summary", 0)
    ws.sheet_view.showGridLines = False

    tier_label = {"luxury": "Luxury", "mainstream": "Mainstream",
                  "powersports": "Powersports"}.get(tier, "Mainstream")

    # --- Derived stats (display only: no scoring logic here) ---
    totals_row = next((r for r in rows if r["source"].lower() == "totals"), None)
    data_rows = [r for r in rows if r["source"].lower() != "totals"]
    scoreable = [r for r in data_rows if r.get("score") is not None]
    credit = [r for r in data_rows if r.get("is_credit_app")]
    tier_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for r in scoreable:
        if r.get("tier") in tier_counts:
            tier_counts[r["tier"]] += 1
    total_leads = totals_row["leads"] if totals_row else sum(r["leads"] for r in data_rows)
    total_sales = totals_row["sales"] if totals_row else sum(r["sales"] for r in data_rows)
    if store_bench:
        close_rate = store_bench["store_rate"]
        expected_rate = store_bench["benchmark"]
    else:
        close_rate = (total_sales / total_leads) if total_leads else 0
        expected_rate = None
    top_sources = sorted(scoreable, key=lambda r: (r["score"], r["sales"]), reverse=True)[:3]

    # --- Styles ---
    heading_font = Font(name="Dosis", bold=True, size=13, color=TILE_BLUE)
    stat_font = Font(name="Dosis", bold=True, size=26, color=SKY_BLUE)
    stat_label_font = Font(name="Dosis", bold=True, size=9, color=WARM_GREY)
    body_font = Font(name="Roboto Slab", size=10, color="000000")
    note_font = Font(name="Roboto Slab", size=10, color=WARM_GREY)
    chip_font = Font(name="Dosis", bold=True, size=11, color="FFFFFF")
    center = Alignment(horizontal="center", vertical="center")
    left = Alignment(horizontal="left", vertical="center")
    wrap = Alignment(horizontal="left", vertical="top", wrap_text=True)
    tint_fill = PatternFill(start_color=CALLOUT_TINT, end_color=CALLOUT_TINT, fill_type="solid")
    thin_border = Border(
        left=Side(style="thin", color=BORDER_BLUE),
        right=Side(style="thin", color=BORDER_BLUE),
        top=Side(style="thin", color=BORDER_BLUE),
        bottom=Side(style="thin", color=BORDER_BLUE),
    )

    for col, width in zip("ABCDEF", (20, 18, 18, 18, 18, 20)):
        ws.column_dimensions[col].width = width

    # --- Masthead: rows 1-2, Digital Blue fill across used columns, white logo
    #     anchored A1 (~0.35in tall), sheet title white Dosis 14 Bold, date right ---
    _add_brand_logo(ws, anchor_cell="A1", row_span=2, col_span=6, logo_width=136)
    ws.row_dimensions[1].height = 22
    ws.row_dimensions[2].height = 22
    ws.merge_cells("B1:D2")
    ws["B1"] = "Lead Source Scorecard: Summary"
    ws["B1"].font = Font(name="Dosis", bold=True, size=14, color="FFFFFF")
    ws["B1"].alignment = left
    ws.merge_cells("E1:F2")
    ws["E1"] = datetime.now().strftime("%B %d, %Y")
    ws["E1"].font = Font(name="Dosis", bold=True, size=10, color="FFFFFF")
    ws["E1"].alignment = Alignment(horizontal="right", vertical="center")

    ws.row_dimensions[3].height = 8  # spacer

    # --- Title block ---
    ws.merge_cells("A4:F4")
    ws["A4"] = store_name
    ws["A4"].font = Font(name="Dosis", bold=True, size=20, color=DIGITAL_BLUE)
    ws["A4"].alignment = left
    ws.row_dimensions[4].height = 28
    ws.merge_cells("A5:F5")
    ws["A5"] = (f"E-Commerce Lead Source Scorecard  |  {date_range}  |  "
                f"Benchmark tier: {tier_label}  |  Created by DigitalCLIQ")
    ws["A5"].font = Font(name="Roboto Slab", size=10, color=WARM_GREY)
    ws["A5"].alignment = left
    ws.row_dimensions[5].height = 18
    ws.row_dimensions[6].height = 8  # spacer

    # --- Store self-score banner ---
    row = 7
    if store_bench:
        text, bcolor = _store_banner(store_bench, tier_label)
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
        c = ws.cell(row=row, column=1, value=text)
        c.font = Font(name="Dosis", bold=True, size=11, color="FFFFFF")
        c.fill = PatternFill(start_color=bcolor, end_color=bcolor, fill_type="solid")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.row_dimensions[row].height = 34
    else:
        ws.row_dimensions[row].height = 8
    row += 2

    # --- Key stats: large Dosis cells, Sky Blue numbers ---
    ws.cell(row=row, column=1, value="Key Numbers").font = heading_font
    ws.row_dimensions[row].height = 22
    row += 1
    stats = [
        ("SOURCES SCORED", len(scoreable), "0"),
        ("TOTAL LEADS", total_leads, "#,##0"),
        ("TOTAL SALES", total_sales, "#,##0"),
        ("STORE CLOSE RATE", close_rate, "0.0%"),
        ("EXPECTED FOR MIX", expected_rate if expected_rate is not None else "n/a", "0.0%"),
        ("A-TIER SOURCES", tier_counts["A"], "0"),
    ]
    val_row, label_row = row, row + 1
    ws.row_dimensions[val_row].height = 38
    ws.row_dimensions[label_row].height = 16
    for col_idx, (label, value, fmt) in enumerate(stats, 1):
        vc = ws.cell(row=val_row, column=col_idx, value=value)
        vc.font = stat_font
        vc.alignment = center
        vc.fill = tint_fill
        vc.border = thin_border
        if not isinstance(value, str):
            vc.number_format = fmt
        lc = ws.cell(row=label_row, column=col_idx, value=label)
        lc.font = stat_label_font
        lc.alignment = center
        lc.fill = tint_fill
        lc.border = thin_border
    row = label_row + 2

    # --- Tier mix ---
    ws.cell(row=row, column=1, value="Tier Mix").font = heading_font
    ws.row_dimensions[row].height = 22
    row += 1
    chips = [(t, get_tier_color(t), tier_counts[t]) for t in ("A", "B", "C", "D")]
    if credit:
        chips.append(("N/A", "949592", len(credit)))
    for col_idx, (label, color, count) in enumerate(chips, 1):
        c = ws.cell(row=row, column=col_idx, value=f"{label}  ·  {count}")
        c.font = chip_font
        c.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
        c.alignment = center
        c.border = thin_border
    ws.row_dimensions[row].height = 24
    row += 2

    # --- Top sources ---
    if top_sources:
        ws.cell(row=row, column=1, value="Top Sources by Score").font = heading_font
        ws.row_dimensions[row].height = 22
        row += 1
        for r in top_sources:
            chip = ws.cell(row=row, column=1, value=f"{r['score']} / 10")
            tcolor = get_tier_color(r["tier"])
            chip.font = chip_font
            chip.fill = PatternFill(start_color=tcolor, end_color=tcolor, fill_type="solid")
            chip.alignment = center
            chip.border = thin_border
            ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
            nc = ws.cell(row=row, column=2, value=r["source"])
            nc.font = body_font
            nc.alignment = left
            for _bc in (2, 3, 4):
                ws.cell(row=row, column=_bc).border = thin_border
            sc = ws.cell(row=row, column=5, value=f"{r['sales']:,} {'sale' if r['sales'] == 1 else 'sales'} / {r['leads']:,} {'lead' if r['leads'] == 1 else 'leads'}")
            sc.font = body_font
            sc.alignment = center
            sc.border = thin_border
            pc = ws.cell(row=row, column=6, value=r["sales_pct"] / 100)
            pc.number_format = "0.0%"
            pc.font = Font(name="Dosis", bold=True, size=11, color=SKY_BLUE)
            pc.alignment = center
            pc.border = thin_border
            ws.row_dimensions[row].height = 20
            row += 1
        row += 1

    # --- How to read ---
    ws.row_breaks.append(Break(id=row - 1))
    ws.cell(row=row, column=1, value="How to Read This Scorecard").font = heading_font
    ws.row_dimensions[row].height = 22
    row += 1
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
    c = ws.cell(row=row, column=1, value=(
        "The 1-10 score is RELATIVE: each factor is measured against the best performer in this "
        "report, and a 10 requires leading every factor at once. No single source usually does, "
        "so the top score here can sit well below 10. Compare sources against each other, not an absolute scale."
    ))
    c.font = note_font
    c.alignment = wrap
    ws.row_dimensions[row].height = 28
    row += 1

    def legend_block(title, labels):
        nonlocal row
        ws.cell(row=row, column=1, value=title).font = Font(
            name="Dosis", bold=True, size=11, color=TILE_BLUE)
        ws.row_dimensions[row].height = 20
        row += 1
        for label, color, desc in labels:
            chip = ws.cell(row=row, column=1, value=label)
            chip.font = Font(name="Dosis", bold=True, size=10, color="FFFFFF")
            chip.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
            chip.alignment = center
            ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=6)
            dc = ws.cell(row=row, column=2, value=desc)
            dc.font = note_font
            dc.alignment = left
            row += 1

    legend_block("Tier Legend (1-10 relative score)",
                 TIER_LEGEND if credit else [e for e in TIER_LEGEND if e[0] != "N/A"])
    row += 1
    legend_block("vs NADA Benchmark (absolute layer)", BENCH_LEGEND)
    row += 1

    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
    c = ws.cell(row=row, column=1, value=BENCH_NOTE)
    c.font = Font(name="Roboto Slab", size=9, italic=True, color=WARM_GREY)
    c.alignment = wrap
    ws.row_dimensions[row].height = 40
    row += 1
    if not contact_available:
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
        c = ws.cell(row=row, column=1, value=CONTACT_NA_NOTE)
        c.font = Font(name="Roboto Slab", size=9, italic=True, color=WARM_GREY)
        c.alignment = wrap
        ws.row_dimensions[row].height = 40
        row += 1
    row += 1

    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
    fc = ws.cell(row=row, column=1, value="DigitalCLIQ  |  Automotive Digital Marketing")
    fc.font = Font(name="Dosis", bold=True, size=12, color=DIGITAL_BLUE)
    fc.alignment = left

    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)


def _autofit_wrapped_rows(ws):
    """Raise any fixed row height that is too short for its wrapped text.
    Excel never auto-grows a customHeight row, so a wrapped cell with more
    lines than the height allows clips silently. Heights are only raised,
    never shrunk, so deliberate spacing survives."""
    import math
    from openpyxl.utils import get_column_letter

    def col_width(idx):
        dim = ws.column_dimensions.get(get_column_letter(idx))
        return dim.width if (dim and dim.width) else 8.43

    merged = {(rng.min_row, rng.min_col): rng for rng in ws.merged_cells.ranges}
    for row in ws.iter_rows():
        for cell in row:
            if not isinstance(cell.value, str) or not cell.value:
                continue
            if not (cell.alignment and cell.alignment.wrap_text):
                continue
            rng = merged.get((cell.row, cell.column))
            last_col = rng.max_col if rng else cell.column
            width = sum(col_width(c) for c in range(cell.column, last_col + 1))
            font_pt = cell.font.size or 11
            # Excel width units approximate 11pt characters; brand serif runs a
            # touch wide, so estimate conservatively.
            # Roboto Slab / Dosis run ~20% wider than the Calibri width unit;
            # 0.72 keeps the last wrapped line from clipping in LibreOffice and Excel.
            chars_per_line = max(1, int(width * 0.72 * 11 / font_pt))
            lines = sum(math.ceil(max(1, len(seg)) / chars_per_line)
                        for seg in cell.value.split("\n"))
            # Roboto Slab line box is ~1.6x its point size in LibreOffice/Excel.
            needed = lines * font_pt * 1.65 + 8
            rows_spanned = (rng.max_row - rng.min_row + 1) if rng else 1
            per_row = needed / rows_spanned
            for r in range(cell.row, cell.row + rows_spanned):
                dim = ws.row_dimensions[r]
                if dim.height is not None and dim.height < per_row:
                    dim.height = math.ceil(per_row)


def build_excel(rows, output_path, store_name, date_range,
                tier="mainstream", benchmarks=None, store_bench=None,
                contact_available=True, extra_notes=None):
    """Generate a formatted Excel workbook."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Lead Source Scores"

    # --- Styles ---
    header_font = Font(name="Dosis", bold=True, size=11, color="FFFFFF")
    header_fill = PatternFill(start_color="405FAB", end_color="405FAB", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    title_font = Font(name="Dosis", bold=True, size=16, color="FFFFFF")
    subtitle_font = Font(name="Roboto Slab", size=11, color="EDF2F9")
    brand_font = Font(name="Dosis", bold=True, size=11, color="FFFFFF")

    data_font = Font(name="Roboto Slab", size=10)
    data_align_center = Alignment(horizontal="center", vertical="center")
    data_align_left = Alignment(horizontal="left", vertical="center")
    pct_format = "0.0%"
    num_format = "#,##0"

    thin_border = Border(
        left=Side(style="thin", color="D8E1F0"),
        right=Side(style="thin", color="D8E1F0"),
        top=Side(style="thin", color="D8E1F0"),
        bottom=Side(style="thin", color="D8E1F0"),
    )

    score_font = Font(name="Dosis", bold=True, size=12, color="FFFFFF")
    tier_font = Font(name="Dosis", bold=True, size=12, color="FFFFFF")

    # --- DigitalCLIQ Branding (white logo on full-width Digital Blue masthead) ---
    _add_brand_logo(ws, anchor_cell="A1", row_span=3, col_span=15, logo_width=180)
    ws.row_dimensions[1].height = 22
    ws.row_dimensions[2].height = 22
    ws.row_dimensions[3].height = 22

    # --- Title Block (offset right of logo) ---
    ws.merge_cells("D1:O1")
    ws["D1"] = store_name
    ws["D1"].font = title_font
    ws["D1"].alignment = Alignment(horizontal="left", vertical="center")

    ws.merge_cells("D2:O2")
    ws["D2"] = f"E-Commerce Lead Source Scorecard  |  {date_range}"
    ws["D2"].font = subtitle_font
    ws["D2"].alignment = Alignment(horizontal="left", vertical="center")

    ws.merge_cells("D3:O3")
    tier_label = {"luxury": "Luxury", "mainstream": "Mainstream",
                  "powersports": "Powersports"}.get(tier, "Mainstream")
    ws["D3"] = (f"Created by DigitalCLIQ  |  {datetime.now().strftime('%B %d, %Y')}"
                f"  |  Benchmark tier: {tier_label}")
    ws["D3"].font = brand_font
    ws["D3"].alignment = Alignment(horizontal="left", vertical="center")

    # --- Store Self-Score Banner (close rate vs NADA industry blend) ---
    # (Recapped on the Summary tab; shared text/color via _store_banner.)
    if store_bench:
        banner_text, bcolor = _store_banner(store_bench, tier_label)
        ws.merge_cells("A4:O4")
        cell = ws["A4"]
        cell.value = banner_text
        cell.font = Font(name="Dosis", bold=True, size=11, color="FFFFFF")
        cell.fill = PatternFill(start_color=bcolor, end_color=bcolor, fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.row_dimensions[4].height = 32
    else:
        ws.row_dimensions[4].height = 8  # spacer row

    # --- Column Headers ---
    headers = [
        ("Score", 8),
        ("Tier", 7),
        ("Lead Source", 68),
        ("Type", 8),
        ("Leads", 9),
        ("Contact #", 10),
        ("Contact %", 10),
        ("Appts #", 9),
        ("Appts %", 9),
        ("Shows #", 9),
        ("Show %", 9),
        ("Sales #", 9),
        ("Sale %", 9),
        ("NADA Bench %", 13),
        ("vs Bench", 11),
    ]

    header_row = 5
    for col_idx, (label, width) in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col_idx, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    ws.row_dimensions[header_row].height = 28

    # --- Data Rows ---
    # Separate totals row if present
    totals_row = None
    data_rows = []
    for r in rows:
        if r["source"].lower() == "totals":
            totals_row = r
        else:
            data_rows.append(r)

    # --- Styles for credit app rows ---
    credit_app_fill = PatternFill(start_color="EDF2F9", end_color="EDF2F9", fill_type="solid")  # callout tint (muted, non-acquisition rows)
    credit_app_tier_fill = PatternFill(start_color="949592", end_color="949592", fill_type="solid")  # grey
    credit_app_font = Font(name="Roboto Slab", size=10, italic=True, color="949592")
    credit_app_score_font = Font(name="Dosis", bold=True, size=11, color="FFFFFF")

    for row_idx, r in enumerate(data_rows, header_row + 1):
        is_ca = r.get("is_credit_app", False)

        if is_ca:
            tier_color = "949592"  # Warm Grey for credit apps
        else:
            tier_color = get_tier_color(r["tier"])
        tier_fill = PatternFill(start_color=tier_color, end_color=tier_color, fill_type="solid")

        # Type column styling
        type_font_new = Font(name="Dosis", bold=True, size=9, color="405FAB")
        type_font_used = Font(name="Dosis", bold=True, size=9, color="2E4780")

        score_val = "N/A" if is_ca else r["score"]
        tier_val = "N/A" if is_ca else r["tier"]

        bench_rate = r.get("bench_rate")
        bench_flag = r.get("bench_flag", "")

        # A zero-lead row's rates are undefined, not 0% (re-engagement sales with
        # no lead this period); "0.0%" next to real sales reads as an error.
        no_leads = r["leads"] < 1
        values = [
            score_val,
            tier_val,
            r["source"],
            r["source_type"],
            r["leads"],
            "n/a" if not contact_available else r["contact"],
            "n/a" if (no_leads or not contact_available) else r["contact_pct"] / 100,
            r["appts"],
            "n/a" if no_leads else r["appts_pct"] / 100,
            r["shows"],
            r["shows_pct"] / 100 if r["appts"] > 0 else ("n/a" if no_leads else r["shows_pct"] / 100),
            r["sales"],
            "n/a" if no_leads else r["sales_pct"] / 100,
            bench_rate,            # col 14: NADA benchmark close rate (fraction) or None
            bench_flag,            # col 15: vs Bench flag (Above/At/Below/Low vol/N/A)
        ]
        if is_ca:
            # Excluded process rows (credit app / unattributed): a 1550% rate cell reads
            # as an error before the note does, so the rate cells show n/a.
            for k in (8, 10, 12):
                values[k] = "n/a"

        for col_idx, val in enumerate(values, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = credit_app_font if is_ca else data_font
            cell.border = thin_border

            if col_idx == 1:  # Score
                cell.font = credit_app_score_font if is_ca else score_font
                cell.fill = tier_fill
                cell.alignment = data_align_center
                if not is_ca:
                    cell.number_format = "0"
            elif col_idx == 2:  # Tier
                cell.font = credit_app_score_font if is_ca else tier_font
                cell.fill = tier_fill
                cell.alignment = data_align_center
            elif col_idx == 3:  # Source name
                cell.alignment = data_align_left
                if is_ca:
                    cell.font = Font(name="Roboto Slab", size=10, italic=True, color="949592")
            elif col_idx == 4:  # Type (New/Used)
                cell.font = type_font_new if val == "New" else type_font_used
                cell.alignment = data_align_center
            elif col_idx == 14:  # NADA benchmark close rate
                cell.number_format = pct_format
                cell.alignment = data_align_center
            elif col_idx == 15:  # vs Bench flag (colored chip)
                flag_color = BENCHMARK_FLAG_COLORS.get(bench_flag, "FFFFFF")
                cell.alignment = data_align_center
                if bench_flag and bench_flag not in ("",):
                    cell.fill = PatternFill(start_color=flag_color,
                                            end_color=flag_color, fill_type="solid")
                    cell.font = Font(name="Dosis", bold=True, size=9, color="FFFFFF")
                # styled below; skip the credit-app tint override for this chip
                continue
            elif col_idx in (7, 9, 11, 13):  # Percentage columns
                cell.number_format = pct_format
                cell.alignment = data_align_center
            else:  # Number columns
                cell.number_format = num_format
                cell.alignment = data_align_center

            # Apply the callout-tint background to credit app data cells (not the flag chip)
            if is_ca and col_idx >= 3:
                cell.fill = credit_app_fill

        # Alternate row shading (only for non-credit-app rows; skip flag chip col 15)
        if not is_ca and row_idx % 2 == 0:
            for col_idx in range(3, 15):
                ws.cell(row=row_idx, column=col_idx).fill = PatternFill(
                    start_color="EDF2F9", end_color="EDF2F9", fill_type="solid"
                )

    # --- Totals Row ---
    if totals_row:
        totals_idx = header_row + len(data_rows) + 1
        totals_fill = PatternFill(start_color="EDF2F9", end_color="EDF2F9", fill_type="solid")
        totals_font = Font(name="Roboto Slab", bold=True, size=10)

        ws.cell(row=totals_idx, column=1, value="").fill = totals_fill
        ws.cell(row=totals_idx, column=2, value="").fill = totals_fill

        totals_values = [
            None, None, "TOTALS", None,
            totals_row["leads"],
            "n/a" if not contact_available else totals_row["contact"],
            "n/a" if not contact_available else totals_row["contact_pct"] / 100,
            totals_row["appts"], totals_row["appts_pct"] / 100,
            totals_row["shows"], totals_row["shows_pct"] / 100,
            totals_row["sales"], totals_row["sales_pct"] / 100,
            None, None,  # benchmark cols (store-level grade is in the banner)
        ]

        for col_idx, val in enumerate(totals_values, 1):
            if val is None:
                ws.cell(row=totals_idx, column=col_idx).fill = totals_fill
                continue
            cell = ws.cell(row=totals_idx, column=col_idx, value=val)
            cell.font = totals_font
            cell.fill = totals_fill
            cell.border = thin_border
            if col_idx == 3:
                cell.alignment = data_align_left
            elif col_idx in (7, 9, 11, 13):  # Percentage columns (shifted +1)
                cell.number_format = pct_format
                cell.alignment = data_align_center
            else:
                cell.number_format = num_format
                cell.alignment = data_align_center

    # --- Notes under the table ---
    # (Tier + benchmark legends and the how-to-read notes live on the Summary
    # tab; these stay here because they explain the shaded rows / n/a columns above.)
    note_row = header_row + len(data_rows) + (3 if totals_row else 2)
    notes = []
    if any(r.get("is_credit_app", False) and not r.get("is_unattributed", False) for r in data_rows):
        notes.append(f"\u26A0  {CREDIT_APP_DISCLAIMER}")
    ua = unattributed_disclaimer(data_rows)
    if ua:
        notes.append(f"\u26A0  {ua}")
    if not contact_available:
        notes.append(f"\u2139  {CONTACT_NA_NOTE}")
    for extra in (extra_notes or []):
        notes.append(f"\u2139  {extra}")
    for text in notes:
        ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=15)
        cell = ws.cell(row=note_row, column=1, value=text)
        cell.font = Font(name="Roboto Slab", size=9, italic=True, color="949592")
        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        cell.fill = PatternFill(start_color="EDF2F9", end_color="EDF2F9", fill_type="solid")
        ws.row_dimensions[note_row].height = 36
        note_row += 1
    fc = ws.cell(row=note_row + 1, column=1, value="DigitalCLIQ  |  Automotive Digital Marketing")
    fc.font = Font(name="Dosis", bold=True, size=12, color=DIGITAL_BLUE)
    fc.alignment = Alignment(horizontal="left", vertical="center")

    # --- Freeze panes ---
    ws.freeze_panes = "A6"

    # --- Print setup ---
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0

    # --- NADA Benchmarks Tab ---
    if benchmarks:
        build_nada_benchmarks_tab(wb, tier, benchmarks, store_bench)

    # --- Methodology Tab ---
    build_methodology_tab(wb, contact_available=contact_available)

    # --- Summary Tab (created last, inserted FIRST in tab order per §4) ---
    build_summary_tab(wb, rows, store_name, date_range, tier, store_bench,
                      contact_available=contact_available)
    wb.active = 0  # workbook opens on the Summary tab

    for sheet in wb.worksheets:
        _autofit_wrapped_rows(sheet)

    wb.save(output_path)
    print(f"OK:{output_path}")


def build_nada_benchmarks_tab(wb, tier, benchmarks, store_bench):
    """Add a NADA Benchmarks tab showing every benchmark figure and its source.

    This is the reference behind the 'NADA Bench %' / 'vs Bench' columns and the
    store self-score banner. Pulls live from the embedded reference file so it
    always matches what scoring used.
    """
    ws = wb.create_sheet("NADA Benchmarks")

    title_font = Font(name="Dosis", bold=True, size=18, color="FFFFFF")
    brand_font = Font(name="Dosis", bold=True, size=12, color="405FAB")
    masthead_sub_font = Font(name="Dosis", bold=True, size=12, color="FFFFFF")
    heading_font = Font(name="Dosis", bold=True, size=13, color="2E4780")
    body_font = Font(name="Roboto Slab", size=11, color="000000")
    bold_body = Font(name="Roboto Slab", bold=True, size=11, color="000000")
    accent_font = Font(name="Dosis", bold=True, size=11, color="405FAB")
    small_src = Font(name="Roboto Slab", size=9, italic=True, color="949592")

    header_font = Font(name="Dosis", bold=True, size=11, color="FFFFFF")
    header_fill = PatternFill(start_color="405FAB", end_color="405FAB", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    wrap_align = Alignment(horizontal="left", vertical="top", wrap_text=True)
    center_align = Alignment(horizontal="center", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")

    thin_border = Border(
        left=Side(style="thin", color="D8E1F0"),
        right=Side(style="thin", color="D8E1F0"),
        top=Side(style="thin", color="D8E1F0"),
        bottom=Side(style="thin", color="D8E1F0"),
    )

    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 16
    ws.column_dimensions["D"].width = 12
    ws.column_dimensions["E"].width = 58

    tier_label = {"luxury": "Luxury", "mainstream": "Mainstream",
                  "powersports": "Powersports"}.get(tier, "Mainstream")
    # Support strength: palette treatment only; the Strong/Moderate/Estimate text carries it.
    support_color = {"strong": "405FAB", "moderate": "6B9DD4", "estimate": "949592"}

    # --- Branding + title (white logo on full-width Digital Blue masthead) ---
    _add_brand_logo(ws, anchor_cell="A1", row_span=3, col_span=5, logo_width=130)
    ws.row_dimensions[1].height = 22
    ws.row_dimensions[2].height = 22
    ws.row_dimensions[3].height = 22
    ws.merge_cells("B1:E1")
    ws["B1"] = "NADA & Industry Benchmarks"
    ws["B1"].font = title_font
    ws["B1"].alignment = left_align
    ws.merge_cells("B2:E2")
    meta = benchmarks.get("_meta", {})
    ws["B2"] = (f"Benchmark tier applied: {tier_label}   |   Reference version "
                f"{meta.get('version','')}   |   Maintained by DigitalCLIQ")
    ws["B2"].font = masthead_sub_font
    ws["B2"].alignment = left_align
    ws.merge_cells("B3:E3")
    ws["B3"] = datetime.now().strftime("%B %d, %Y")
    ws["B3"].font = Font(name="Dosis", bold=True, size=10, color="FFFFFF")
    ws["B3"].alignment = Alignment(horizontal="right", vertical="center")

    row = 5

    def section_heading(text):
        nonlocal row
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
        ws.cell(row=row, column=1, value=text).font = heading_font
        ws.row_dimensions[row].height = 24
        row += 1

    def table_header(cols):
        nonlocal row
        for ci, label in enumerate(cols, 1):
            c = ws.cell(row=row, column=ci, value=label)
            c.font = header_font
            c.fill = header_fill
            c.alignment = header_align
            c.border = thin_border
        ws.row_dimensions[row].height = 26
        row += 1

    # --- Store self-score recap ---
    if store_bench:
        section_heading("Store Self-Score (close rate vs industry blend)")
        verb = {"Above": "ABOVE", "At": "AT", "Below": "BELOW"}[store_bench["verdict"]]
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
        excl = store_bench.get("excluded_leads", 0)
        excl_txt = (f" {excl:,} data-list/credit-app leads were excluded as non-acquisition "
                    f"leads so they do not deflate the rate." if excl else "")
        c = ws.cell(row=row, column=1, value=(
            f"This store closes {store_bench['store_rate']*100:.1f}% of acquisition leads "
            f"({store_bench['sales']:,} sales / {store_bench['leads']:,} leads) vs a "
            f"{tier_label.lower()} industry expectation of {store_bench['benchmark']*100:.1f}% "
            f"for this report's lead mix. "
            + (f"Within {abs(store_bench['delta_pts']):.1f} points of expectation (At band)." if verb == "AT"
               else f"{verb} by {abs(store_bench['delta_pts']):.1f} points.")
            + f"{excl_txt}"
        ))
        c.font = bold_body
        c.alignment = wrap_align
        ws.row_dimensions[row].height = 32
        row += 1
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
        src_cell = ws.cell(row=row, column=1, value=f"Source: {store_bench.get('source','')}")
        src_cell.font = small_src
        src_cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
        ws.row_dimensions[row].height = 26
        row += 2

    # --- Close-rate benchmarks by source type ---
    section_heading(f"Close-Rate Benchmarks by Source Type ({tier_label} tier)")
    table_header(["Source Type", "Benchmark Close %", "Typical Range", "Support", "Source"])
    cats = benchmarks["close_rate_benchmarks"]["categories"]
    cat_order = ["website", "phone", "walk_in", "third_party", "oem",
                 "owned_equity", "chat", "data_list"]
    for ci, key in enumerate(cat_order):
        cdef = cats.get(key)
        if not cdef:
            continue
        if ci == 4:
            # The table runs past one landscape page; break here and repeat the header.
            ws.row_breaks.append(Break(id=row - 1))
            table_header(["Source Type", "Benchmark Close %", "Typical Range", "Support", "Source"])
        val = cdef.get(tier)
        rng = cdef.get("range", [None, None])
        ws.cell(row=row, column=1, value=cdef.get("label", key)).font = bold_body
        ws.cell(row=row, column=1).alignment = wrap_align
        ws.cell(row=row, column=1).border = thin_border

        vcell = ws.cell(row=row, column=2,
                        value=(val if val is not None else "n/a"))
        vcell.font = accent_font
        vcell.alignment = center_align
        vcell.border = thin_border
        if val is not None:
            vcell.number_format = "0.0%"

        if rng[0] is not None:
            rcell = ws.cell(row=row, column=3, value=f"{rng[0]*100:.0f}%-{rng[1]*100:.0f}%")
        else:
            rcell = ws.cell(row=row, column=3, value="n/a")
        rcell.font = body_font
        rcell.alignment = center_align
        rcell.border = thin_border

        sup = cdef.get("support", "")
        scell = ws.cell(row=row, column=4, value=sup.capitalize())
        scell.font = Font(name="Dosis", bold=True, size=10, color="FFFFFF")
        scell.fill = PatternFill(start_color=support_color.get(sup, "949592"),
                                 end_color=support_color.get(sup, "949592"), fill_type="solid")
        scell.alignment = center_align
        scell.border = thin_border

        srccell = ws.cell(row=row, column=5, value=cdef.get("source", ""))
        srccell.font = body_font
        srccell.alignment = wrap_align
        srccell.border = thin_border
        ws.row_dimensions[row].height = 44
        row += 1
    row += 1

    # --- NADA cost yardsticks ---
    section_heading("NADA Cost & Economics Yardsticks (context)")
    table_header(["Metric", "Value", "", "Support", "Source"])
    cy = benchmarks.get("cost_yardsticks", {})

    def cost_row(label, value_str, support, source):
        nonlocal row
        ws.cell(row=row, column=1, value=label).font = bold_body
        ws.cell(row=row, column=1).alignment = wrap_align
        ws.cell(row=row, column=1).border = thin_border
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
        v = ws.cell(row=row, column=2, value=value_str)
        v.font = accent_font
        v.alignment = center_align
        v.border = thin_border
        ws.cell(row=row, column=3).border = thin_border
        sc = ws.cell(row=row, column=4, value=support.capitalize())
        sc.font = Font(name="Dosis", bold=True, size=10, color="FFFFFF")
        sc.fill = PatternFill(start_color=support_color.get(support, "949592"),
                              end_color=support_color.get(support, "949592"), fill_type="solid")
        sc.alignment = center_align
        sc.border = thin_border
        s = ws.cell(row=row, column=5, value=source)
        s.font = body_font
        s.alignment = wrap_align
        s.border = thin_border
        ws.row_dimensions[row].height = 40
        row += 1

    ad = cy.get("ad_cost_per_new_unit_usd", {})
    if ad:
        cost_row("Advertising cost per new unit", f"${ad.get('value'):,}",
                 ad.get("support", ""), ad.get("source", ""))
    pg = cy.get("ad_pct_of_total_gross", {})
    if pg:
        cost_row("Advertising as % of total gross",
                 f"{pg.get('low')*100:.0f}%-{pg.get('high')*100:.0f}%",
                 pg.get("support", ""), pg.get("source", ""))
    mix = cy.get("ad_channel_mix_2025", {})
    if mix:
        cost_row("Ad channel mix (top 3)",
                 f"SEM {mix.get('sem',0)*100:.0f}% / 3rd-party {mix.get('third_party_listing',0)*100:.0f}% / SEO {mix.get('seo',0)*100:.0f}%",
                 mix.get("support", ""), mix.get("source", ""))
    gp = cy.get("gross_per_unit_usd", {})
    if gp:
        cost_row("Gross per unit (front+back)",
                 f"New ~${gp.get('new_front_plus_back'):,} / Used ~${gp.get('used_front_plus_back'):,}",
                 gp.get("support", ""), gp.get("source", ""))
    np_ = cy.get("avg_new_vehicle_price_usd", {})
    if np_:
        cost_row("Avg new-vehicle retail price", f"${np_.get('value'):,}",
                 np_.get("support", ""), np_.get("source", ""))
    row += 1

    # --- Seasonal indices ---
    si = benchmarks.get("seasonal_indices_nada", {})
    if si:
        ws.row_breaks.append(Break(id=row - 1))
        section_heading("NADA Seasonal Demand Indices (1.00 = avg month)")

        def season_block(keys):
            nonlocal row
            for ci, m in enumerate(keys, 1):
                c = ws.cell(row=row, column=ci, value=m.upper())
                c.font = header_font
                c.fill = header_fill
                c.alignment = center_align
                c.border = thin_border
            row += 1
            for ci, m in enumerate(keys, 1):
                c = ws.cell(row=row, column=ci, value=si.get(m))
                c.font = accent_font
                c.alignment = center_align
                c.border = thin_border
                c.number_format = "0.00"
            row += 1
        season_block(["jan", "feb", "mar", "apr", "may"])
        season_block(["jun", "jul", "aug", "sep", "oct"])
        season_block(["nov", "dec"])
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
        ws.cell(row=row, column=1, value=f"Source: {si.get('source','')}").font = small_src
        row += 2

    # --- Footer ---
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
    ws.cell(row=row, column=1, value=(
        "Support: Strong = NADA primary or multi-source consensus. Moderate = single credible "
        "vendor/advisory source. Estimate = directional only, no single authoritative study. "
        "DigitalCLIQ maintains these figures and refreshes them as new NADA data publishes."
    )).font = small_src
    ws.cell(row=row, column=1).alignment = wrap_align
    ws.row_dimensions[row].height = 34
    row += 2
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
    ws.cell(row=row, column=1, value="DigitalCLIQ  |  Automotive Digital Marketing").font = brand_font

    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)


def build_methodology_tab(wb, contact_available=True):
    """Add a Methodology tab explaining how scores and tiers are calculated."""
    ws = wb.create_sheet("Methodology")

    # --- Styles ---
    title_font = Font(name="Dosis", bold=True, size=18, color="FFFFFF")
    brand_font = Font(name="Dosis", bold=True, size=12, color="405FAB")
    masthead_sub_font = Font(name="Dosis", bold=True, size=12, color="FFFFFF")
    heading_font = Font(name="Dosis", bold=True, size=13, color="2E4780")
    body_font = Font(name="Roboto Slab", size=11, color="000000")
    bold_body = Font(name="Roboto Slab", bold=True, size=11, color="000000")
    accent_font = Font(name="Dosis", bold=True, size=11, color="405FAB")

    header_font = Font(name="Dosis", bold=True, size=11, color="FFFFFF")
    header_fill = PatternFill(start_color="405FAB", end_color="405FAB", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    wrap_align = Alignment(horizontal="left", vertical="top", wrap_text=True)
    center_align = Alignment(horizontal="center", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")

    thin_border = Border(
        left=Side(style="thin", color="D8E1F0"),
        right=Side(style="thin", color="D8E1F0"),
        top=Side(style="thin", color="D8E1F0"),
        bottom=Side(style="thin", color="D8E1F0"),
    )

    # Column widths
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 26
    ws.column_dimensions["C"].width = 55
    ws.column_dimensions["D"].width = 20

    # --- DigitalCLIQ Branding (white logo on full-width Digital Blue masthead) ---
    _add_brand_logo(ws, anchor_cell="A1", row_span=3, col_span=4, logo_width=130)
    ws.row_dimensions[1].height = 22
    ws.row_dimensions[2].height = 22
    ws.row_dimensions[3].height = 22

    # --- Title (offset right of logo) ---
    ws.merge_cells("B1:D1")
    ws["B1"] = "Lead Source Scoring Methodology"
    ws["B1"].font = title_font
    ws["B1"].alignment = Alignment(horizontal="left", vertical="center")

    ws.merge_cells("B2:D2")
    ws["B2"] = "Developed by DigitalCLIQ"
    ws["B2"].font = masthead_sub_font
    ws["B2"].alignment = Alignment(horizontal="left", vertical="center")
    ws.merge_cells("B3:D3")
    ws["B3"] = datetime.now().strftime("%B %d, %Y")
    ws["B3"].font = Font(name="Dosis", bold=True, size=10, color="FFFFFF")
    ws["B3"].alignment = Alignment(horizontal="right", vertical="center")

    row = 4
    ws.row_dimensions[4].height = 8  # spacer

    # --- Overview ---
    row = 4
    ws.merge_cells("A4:D4")
    ws["A4"] = "Overview"
    ws["A4"].font = heading_font
    ws.row_dimensions[4].height = 24

    row = 5
    ws.merge_cells("A5:D5")
    ws["A5"] = (
        ("Each lead source is scored on a 1-10 scale based on four conversion metrics "
         "(contact rate is not reported in this CRM export, so it is not scored). "
         if not contact_available else
         "Each lead source is scored on a 1-10 scale based on five conversion metrics. ") +
        "Scoring is relative: every source is measured against the top performer in the "
        "same report period, so scores reflect how each source compares within this "
        "specific dealership and timeframe."
    )
    ws["A5"].font = body_font
    ws["A5"].alignment = wrap_align
    ws.row_dimensions[5].height = 50

    row = 6
    ws.row_dimensions[6].height = 8  # spacer

    # --- Scoring Factors Table ---
    row = 7
    ws.merge_cells("A7:D7")
    ws["A7"] = "Scoring Factors & Weights"
    ws["A7"].font = heading_font
    ws.row_dimensions[7].height = 24

    row = 8
    factor_headers = ["Factor", "Weight", "What It Measures", "Why It Matters"]
    for col_idx, label in enumerate(factor_headers, 1):
        cell = ws.cell(row=row, column=col_idx, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border
    ws.row_dimensions[row].height = 26

    factors = [
        (
            "Sale Conversion Rate",
            "40%",
            "Percentage of leads that resulted in a vehicle sale (DMS-matched).",
            "The #1 goal is selling cars. Sources that convert to sales deliver the most ROI.",
        ),
        (
            "Appointment Show Rate",
            "20%",
            "Of leads who set an appointment, the percentage that actually showed up.",
            "Shows demonstrate real buying intent. A lead who walks in is far more valuable than one who no-shows.",
        ),
        (
            "Sales Volume",
            "15%",
            "Raw number of closed sales from the source.",
            "Rate alone can be misleading: a source with 1 lead and 1 sale (100%) is less impactful than one with 50 leads and 10 sales (20%).",
        ),
        (
            "Appointment Set Rate",
            "15%",
            "Percentage of leads that set an appointment.",
            "Setting appointments signals customer engagement and purchase consideration.",
        ),
        (
            "Contact Rate",
            "10%",
            "Percentage of leads where contact was successfully made.",
            "Important signal but noisy: high contact rates don't always lead to sales. Weighted lowest.",
        ),
    ]

    if not contact_available:
        applied = {"Sale Conversion Rate": "44%", "Appointment Show Rate": "22%",
                   "Sales Volume": "17%", "Appointment Set Rate": "17%", "Contact Rate": "not scored"}
        factors = [(f, f"{w} base, {applied[f]} here", m,
                    ("Not reported in this CRM export. Its 10% weight was redistributed across the other four factors in proportion."
                     if f == "Contact Rate" else why))
                   for f, w, m, why in factors]

    for i, (factor, weight, measures, why) in enumerate(factors):
        r = row + 1 + i
        ws.cell(row=r, column=1, value=factor).font = bold_body
        ws.cell(row=r, column=1).alignment = left_align
        ws.cell(row=r, column=1).border = thin_border

        ws.cell(row=r, column=2, value=weight).font = accent_font
        ws.cell(row=r, column=2).alignment = center_align
        ws.cell(row=r, column=2).border = thin_border

        ws.cell(row=r, column=3, value=measures).font = body_font
        ws.cell(row=r, column=3).alignment = wrap_align
        ws.cell(row=r, column=3).border = thin_border

        ws.cell(row=r, column=4, value=why).font = body_font
        ws.cell(row=r, column=4).alignment = wrap_align
        ws.cell(row=r, column=4).border = thin_border

        ws.row_dimensions[r].height = 48

        # alternate row shading
        if i % 2 == 1:
            alt_fill = PatternFill(start_color="EDF2F9", end_color="EDF2F9", fill_type="solid")
            for c in range(1, 5):
                ws.cell(row=r, column=c).fill = alt_fill

    row = row + 1 + len(factors)
    ws.row_dimensions[row].height = 8  # spacer
    row += 1

    # --- New vs Used Car Adjustment ---
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    ws.row_breaks.append(Break(id=row - 1))
    ws.cell(row=row, column=1, value="New vs Used Car Adjustment").font = heading_font
    ws.row_dimensions[row].height = 24
    row += 1

    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    ws.cell(row=row, column=1, value=(
        "Used car inventory is unique (1-of-1): each vehicle has a specific VIN, mileage, and price "
        "that cannot be replicated. This creates higher urgency and naturally produces higher close rates "
        "compared to new car leads, where the same model is available across multiple dealers."
    )).font = body_font
    ws.cell(row=row, column=1).alignment = wrap_align
    ws.row_dimensions[row].height = 50
    row += 1

    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    ws.cell(row=row, column=1, value=(
        "To level the playing field, new car lead sources receive a 1.5x boost on their sale conversion "
        "rate before scoring. This prevents new car sources (dealer website, TrueCar, Costco, OEM leads) "
        "from being unfairly penalized when compared against used car marketplace sources (AutoTrader, "
        "CARFAX, CarGurus, Cars.com) that benefit from the 1-of-1 urgency advantage."
    )).font = body_font
    ws.cell(row=row, column=1).alignment = wrap_align
    ws.row_dimensions[row].height = 50
    row += 1

    # New vs Used classification table
    nv_headers = ["Classification", "Boost", "Sources", "Rationale"]
    for col_idx, label in enumerate(nv_headers, 1):
        cell = ws.cell(row=row, column=col_idx, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border
    ws.row_dimensions[row].height = 26
    row += 1

    nv_data = [
        ("New", "1.5x", "Dealer website, OEM/factory, TrueCar, Costco, Meta, trade-in tools, paid social",
         "Lower natural close rate due to commodity inventory across dealers."),
        ("Used", "None", "AutoTrader, CARFAX, CarGurus, Cars.com",
         "Higher natural close rate due to unique 1-of-1 inventory."),
    ]

    for i, (nv_type, boost, sources, rationale) in enumerate(nv_data):
        nv_color = "405FAB" if nv_type == "New" else "2E4780"
        nv_fill = PatternFill(start_color=nv_color, end_color=nv_color, fill_type="solid")

        cell = ws.cell(row=row, column=1, value=nv_type)
        cell.font = Font(name="Dosis", bold=True, size=11, color="FFFFFF")
        cell.fill = nv_fill
        cell.alignment = center_align
        cell.border = thin_border

        ws.cell(row=row, column=2, value=boost).font = accent_font
        ws.cell(row=row, column=2).alignment = center_align
        ws.cell(row=row, column=2).border = thin_border

        ws.cell(row=row, column=3, value=sources).font = body_font
        ws.cell(row=row, column=3).alignment = wrap_align
        ws.cell(row=row, column=3).border = thin_border

        ws.cell(row=row, column=4, value=rationale).font = body_font
        ws.cell(row=row, column=4).alignment = wrap_align
        ws.cell(row=row, column=4).border = thin_border

        ws.row_dimensions[row].height = 40
        row += 1

    ws.row_dimensions[row].height = 8  # spacer
    row += 1

    # --- Credit Application Exclusion ---
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    ws.cell(row=row, column=1, value="Credit Application Exclusion").font = heading_font
    ws.row_dimensions[row].height = 24
    row += 1

    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    ws.cell(row=row, column=1, value=(
        "Credit application leads are excluded from scoring because they are not true acquisition "
        "sources. When a customer walks in or calls from another lead source (e.g., CarGurus, "
        "dealer website, walk-in), the dealership often has them fill out a credit application as "
        "part of the purchase process. The credit app then gets 'credit' for a sale it did not "
        "actually generate."
    )).font = body_font
    ws.cell(row=row, column=1).alignment = wrap_align
    ws.row_dimensions[row].height = 55
    row += 1

    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    ws.cell(row=row, column=1, value=(
        "These sources always show near-100% close rates with low volume, which would artificially "
        "inflate the scoring curve and make real acquisition sources appear worse by comparison. "
        "Credit app sources are kept in the report for completeness but are tagged as 'N/A' (not "
        "scored) and shaded grey when they appear as standalone sources. A credit or pre-qualification sub-product of a "
        "marketplace (for example a CarGurus credit app) rolls into its parent vendor. OEM and finance data lists "
        "(conquest, back-in-market) are scored 1-10 for completeness but are excluded from the store close rate and "
        "are not benchmarked."
    )).font = body_font
    ws.cell(row=row, column=1).alignment = wrap_align
    ws.row_dimensions[row].height = 55
    row += 1

    ws.row_dimensions[row].height = 8  # spacer
    row += 1

    # --- How the Score Is Calculated ---
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    ws.cell(row=row, column=1, value="How the Score Is Calculated").font = heading_font
    ws.row_dimensions[row].height = 24
    row += 1

    steps = [
        (
            "Step 1: Normalize",
            "Each factor is divided by the best value in the report to get a 0-to-1 ratio. "
            "For example, if the top sale rate is 50% and a source has 25%, its normalized sale rate is 0.50."
        ),
        (
            "Step 2: Apply Weights",
            ("Each normalized value is multiplied by its weight, then the factors are added together. "
             "Base formula:\n"
             "  Composite = (Sale Rate x 0.40) + (Show Rate x 0.20) + (Volume x 0.15) + (Appt Rate x 0.15) + (Contact Rate x 0.10)\n"
             "Applied in this report (no contact data):\n"
             "  Composite = (Sale Rate x 0.44) + (Show Rate x 0.22) + (Volume x 0.17) + (Appt Rate x 0.17)")
            if not contact_available else
            ("Each normalized value is multiplied by its weight, then all five are added together:\n"
             "  Composite = (Sale Rate x 0.40) + (Show Rate x 0.20) + (Volume x 0.15) + (Appt Rate x 0.15) + (Contact Rate x 0.10)")
        ),
        (
            "Step 3: Scale to 1-10",
            "The composite (a number between 0 and 1) is multiplied by 10 and rounded to produce "
            "the final score. A floor of 1 is applied so every source receives at least a 1."
        ),
    ]

    for step_title, step_desc in steps:
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
        ws.cell(row=row, column=1, value=step_title).font = bold_body
        ws.cell(row=row, column=1).alignment = left_align
        ws.row_dimensions[row].height = 20
        row += 1

        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
        ws.cell(row=row, column=1, value=step_desc).font = body_font
        ws.cell(row=row, column=1).alignment = wrap_align
        ws.row_dimensions[row].height = 44
        row += 1

    ws.row_dimensions[row].height = 8  # spacer
    row += 1

    # --- Tier Definitions ---
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    ws.row_breaks.append(Break(id=row - 1))
    ws.cell(row=row, column=1, value="Tier Definitions").font = heading_font
    ws.row_dimensions[row].height = 24
    row += 1

    tier_headers = ["Tier", "Score Range", "Classification", "Recommendation"]
    for col_idx, label in enumerate(tier_headers, 1):
        cell = ws.cell(row=row, column=col_idx, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border
    ws.row_dimensions[row].height = 26
    row += 1

    tier_data = [
        ("A", "405FAB", "8 - 10", "Top Performer",
         "Maximize investment. These sources consistently convert leads to sales and deliver strong ROI."),
        ("B", "6B9DD4", "5 - 7", "Solid Source",
         "Maintain and optimize. Good conversion with room for improvement: review appointment follow-up."),
        ("C", "949592", "3 - 4", "Underperforming",
         "Evaluate closely. May need better lead handling or tighter follow-up processes before increasing spend."),
        ("D", "070A15", "1 - 2", "Poor ROI",
         "Consider reducing or reallocating budget. Low conversion across key metrics: investigate root cause."),
    ]

    for i, (tier, color, score_range, classification, recommendation) in enumerate(tier_data):
        tier_fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
        tier_font_style = Font(name="Dosis", bold=True, size=11, color="FFFFFF")

        cell = ws.cell(row=row, column=1, value=tier)
        cell.font = tier_font_style
        cell.fill = tier_fill
        cell.alignment = center_align
        cell.border = thin_border

        ws.cell(row=row, column=2, value=score_range).font = bold_body
        ws.cell(row=row, column=2).alignment = center_align
        ws.cell(row=row, column=2).border = thin_border

        ws.cell(row=row, column=3, value=classification).font = bold_body
        ws.cell(row=row, column=3).alignment = left_align
        ws.cell(row=row, column=3).border = thin_border

        ws.cell(row=row, column=4, value=recommendation).font = body_font
        ws.cell(row=row, column=4).alignment = wrap_align
        ws.cell(row=row, column=4).border = thin_border

        ws.row_dimensions[row].height = 40
        row += 1

    ws.row_dimensions[row].height = 8  # spacer
    row += 1

    # --- NADA Industry Benchmark Layer ---
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    ws.row_breaks.append(Break(id=row - 1))
    ws.cell(row=row, column=1, value="NADA Industry Benchmark Layer").font = heading_font
    ws.row_dimensions[row].height = 24
    row += 1

    bench_paras = [
        ("The 1-10 score is RELATIVE (each source vs the best in this report). The benchmark "
         "layer is ABSOLUTE and separate: it grades each source's actual close rate against the "
         "NADA / national-industry close rate for its source type. The two answer different "
         "questions: 'who is best here?' vs 'are we good by industry standards?'"),
        ("Each source is classified into a type (internet/website, phone, walk-in/showroom, "
         "third-party marketplace, OEM/factory, owned equity, chat). Close rates vary enormously "
         "by type (mainstream examples: walk-ins close ~25%, internet leads ~10%, third-party ~6%; "
         "luxury-tier benchmarks run slightly higher), so each source is "
         "compared only to the benchmark for ITS type, never a single blended number."),
        ("Benchmarks are brand-tier-aware. The store's franchise is detected from its name and "
         "mapped to luxury, mainstream, or powersports; luxury close-rate benchmarks run slightly "
         "higher (luxury brands lead internet-lead effectiveness). The 'vs Bench' column flags "
         "Above (10%+ over), At (within +/-10%), or Below (10%+ under). Sources with fewer than "
         "10 leads are marked 'Low vol' because the rate is statistical noise, and their 1-10 "
         "score is capped at 5 so an unproven sample can't out-rank a real producer."),
        ("The store self-score banner compares the store's actual close rate to the rate industry "
         "would be expected to deliver ON THIS REPORT'S LEAD MIX (a lead-weighted average of each "
         "source's own source-type benchmark), so an internet-only export isn't judged against a "
         "walk-in-inclusive blend. Data lists and credit apps are excluded from that rate. Every "
         "benchmark figure, its support strength, and its source citation are on the NADA Benchmarks "
         "tab, which DigitalCLIQ maintains and refreshes as new NADA data publishes."),
    ]
    for para in bench_paras:
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
        ws.cell(row=row, column=1, value=para).font = body_font
        ws.cell(row=row, column=1).alignment = wrap_align
        ws.row_dimensions[row].height = 56
        row += 1

    ws.row_dimensions[row].height = 8  # spacer
    row += 1

    # --- Important Notes ---
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    ws.cell(row=row, column=1, value="Important Notes").font = heading_font
    ws.row_dimensions[row].height = 24
    row += 1

    notes = [
        "Scores are relative, not absolute. Each factor is normalized against the best performer in this report, and a 10 requires leading every factor at once. No single source usually does, so the top score in a report can sit well below 10. Compare sources against each other, not an absolute scale.",
        "New car sources receive a 1.5x boost on sale conversion rate to account for the structural close-rate disadvantage vs used car sources. The Sale % column shows the actual (unadjusted) rate; the boost is applied internally during scoring only.",
        "Low-volume sources with high rates should be interpreted carefully. One lead that converts is a 100% rate but does not indicate a reliable pattern.",
        "Appointment or sale rates above 100% occur when the CRM logs an appointment or a DMS-matched sale against a source without a matching lead in the period (re-engagement, portfolio or event records). Those rows show the actual figure; the rate is capped at 100% for scoring.",
        "Contact rates above 100% can occur when a lead is contacted multiple times or across multiple channels. These are capped at 100% for scoring purposes.",
        "This methodology is designed for CRM e-commerce lead reports. Results are most meaningful when comparing sources within the same store and time period.",
    ]
    if not contact_available:
        notes = [n for n in notes if not n.startswith("Contact rates above 100%")]
        notes.insert(0, CONTACT_NA_NOTE)

    for note in notes:
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
        ws.cell(row=row, column=1, value=f"\u2022  {note}").font = body_font
        ws.cell(row=row, column=1).alignment = wrap_align
        ws.row_dimensions[row].height = 36
        row += 1

    row += 1
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    ws.cell(row=row, column=1, value="DigitalCLIQ  |  Automotive Digital Marketing").font = brand_font
    ws.cell(row=row, column=1).alignment = Alignment(horizontal="left", vertical="center")

    # --- Print setup ---
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)


def print_summary(rows, store_name, tier, store_bench, output_path, ingest_meta=None,
                  validation=None):
    """Print a compact, low-token summary so the caller never has to open the
    workbook to know what happened. ~7 lines."""
    scoreable = [r for r in rows if r.get("score") is not None and r["source"].lower() != "totals"]
    credit = [r for r in rows if r.get("is_credit_app")]
    tier_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for r in scoreable:
        t = r.get("tier")
        if t in tier_counts:
            tier_counts[t] += 1

    print("SUMMARY")
    print(f"  store: {store_name} ({tier})")
    if ingest_meta:
        roll = "rolled up" if ingest_meta.get("rolled_up") else "per-source"
        print(f"  format: {ingest_meta['format']}  ({ingest_meta['raw_rows']} raw rows -> "
              f"{ingest_meta['sources']} sources, {roll})")
    print(f"  sources scored: {len(scoreable)}"
          + (f"  ({len(credit)} excluded: credit app / unattributed)" if credit else ""))
    if ingest_meta and not ingest_meta.get("contact_available", True):
        print("  contact rate: not in this export (weight redistributed, columns read n/a)")
    if ingest_meta and ingest_meta.get("totals_check"):
        print(f"  totals check vs report: {ingest_meta['totals_check']}")
    if ingest_meta and ingest_meta.get("report_date_range"):
        print(f"  report says: store={ingest_meta.get('report_store')}  range={ingest_meta['report_date_range']}")
    if store_bench:
        print(f"  store self-score: {store_bench['store_rate']*100:.1f}% close on acquisition leads "
              f"vs {store_bench['benchmark']*100:.1f}% expected for mix "
              f"({store_bench['verdict']} by {store_bench['delta_pts']:+.1f} pts)")
    print(f"  tiers: A={tier_counts['A']} B={tier_counts['B']} C={tier_counts['C']} D={tier_counts['D']}")
    if validation is not None:
        if validation.get("passed"):
            print("  validation: PASSED (branding, location, sheets, no placeholders)")
        else:
            print(f"  validation: FAILED: {validation.get('summary', 'see details')}")
    print(f"  output: {output_path}")


def _validate_deliverable(output_path, min_sheets=4):
    """Run the shared post-flight validator on the finished file. Locates
    post_flight.py next to this skill, with a fallback to the canonical vault path.
    Returns the validator result dict, or None if the validator can't be found."""
    skill_dir = os.path.dirname(os.path.abspath(__file__))
    skills_root = os.path.dirname(skill_dir)
    candidates = [
        skills_root,  # sibling post_flight.py (works for either vault skill copy)
        "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills",
    ]
    for root in candidates:
        if os.path.exists(os.path.join(root, "post_flight.py")):
            sys.path.insert(0, root)
            try:
                from post_flight import validate_report
            except ImportError:
                continue
            return validate_report(output_path, min_sheets=min_sheets)
    return None


def _run_pipeline(csv_path, output_path, store_name, date_range, ingest_meta=None,
                  do_validate=True):
    """Shared pipeline: validate -> load -> score -> benchmark -> Excel -> summary."""
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        raw_rows = list(reader)

    is_valid, val_errors = validate_data(headers, raw_rows, source_path=csv_path)
    if not is_valid:
        print(f"ERROR: Data validation failed with {len(val_errors)} error(s). Aborting.", file=sys.stderr)
        sys.exit(1)

    contact_available = (ingest_meta or {}).get("contact_available", True)
    rows = load_data(csv_path)
    rows = score_sources(rows, contact_available=contact_available)

    # --- NADA / industry benchmark layer (separate from the 1-10 score) ---
    benchmarks = load_benchmarks()
    tier = detect_brand_tier(store_name, benchmarks)
    rows = annotate_benchmarks(rows, tier, benchmarks)
    store_bench = compute_store_benchmark(rows, tier, benchmarks)

    extra_notes = []
    if ingest_meta and ingest_meta.get("format") == "tekion" and contact_available:
        extra_notes.append(TEKION_CONTACT_NOTE)
    build_excel(rows, output_path, store_name, date_range,
                tier=tier, benchmarks=benchmarks, store_bench=store_bench,
                contact_available=contact_available, extra_notes=extra_notes)

    # --- Post-flight validation folded into the run (no separate call needed) ---
    validation = None
    if do_validate:
        validation = _validate_deliverable(output_path, min_sheets=4)

    print_summary(rows, store_name, tier, store_bench, output_path, ingest_meta, validation)

    if validation is not None and not validation.get("passed", False):
        print("\n" + validation.get("summary", "post-flight FAILED"), file=sys.stderr)
        sys.exit(2)


def main():
    argv = sys.argv[1:]

    # --- --raw mode: auto-ingest a native CRM export, no pre-normalization needed ---
    if argv and argv[0] == "--raw":
        flags = {a for a in argv if a.startswith("--")}
        pos = [a for a in argv[1:] if not a.startswith("--")]
        if len(pos) < 4:
            print("Usage: python3 score_leads.py --raw <raw.csv|xlsx> <output.xlsx> "
                  "<store_name> <date_range> [--rollup|--no-rollup]", file=sys.stderr)
            sys.exit(1)
        raw_path, output_path, store_name, date_range = pos[0], pos[1], pos[2], pos[3]
        rollup = True if "--rollup" in flags else (False if "--no-rollup" in flags else None)

        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import ingest as _ingest
        try:
            rows, meta = _ingest.ingest(raw_path, rollup=rollup)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        if not rows:
            print("ERROR: no scoreable rows after ingestion (all sources had < 1 lead?).", file=sys.stderr)
            sys.exit(1)

        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), "score_leads_normalized.csv")
        _ingest.write_normalized(rows, tmp)
        _run_pipeline(tmp, output_path, store_name, date_range, ingest_meta=meta,
                      do_validate="--no-validate" not in flags)
        return

    # --- legacy mode: a pre-normalized CSV ---
    flags = {a for a in argv if a.startswith("--")}
    pos = [a for a in argv if not a.startswith("--")]
    if len(pos) < 4:
        print("Usage: python3 score_leads.py <input.csv> <output.xlsx> <store_name> <date_range>\n"
              "   or: python3 score_leads.py --raw <raw.csv|xlsx> <output.xlsx> <store_name> <date_range> "
              "[--rollup|--no-rollup] [--no-validate]",
              file=sys.stderr)
        sys.exit(1)
    _run_pipeline(pos[0], pos[1], pos[2], pos[3], do_validate="--no-validate" not in flags)


if __name__ == "__main__":
    main()
