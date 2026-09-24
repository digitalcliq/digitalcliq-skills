#!/usr/bin/env python3
"""
DigitalCLIQ Lease Specials Report Generator
Reads a combined lease data JSON and produces a branded .xlsx workbook.
Tab order (Design-System §4): styled Summary first, then per-brand tabs,
Dealers, Run Log, README. Every visible sheet carries the rows 1-2
Digital Blue masthead with the white logo, white Dosis 14 title, and date.

Usage:
    python3 generate_lease_report.py <json_path> <output_dir> --roster <roster_path>

Output:
    <output_dir>/DigitalCLIQ_Lease_Tracker_YYYY-MM.xlsx
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
    from openpyxl.utils import get_column_letter
    from openpyxl.drawing.image import Image as XlImage
except ImportError:
    print("Installing openpyxl...")
    os.system(f"{sys.executable} -m pip install openpyxl -q")
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
    from openpyxl.utils import get_column_letter
    from openpyxl.drawing.image import Image as XlImage

# ── Brand colors (DigitalCLIQ design-system tokens — Resources/design-system/Design-System.md) ──
BRAND_BG = "405FAB"      # Digital Blue — mastheads, primary fills
BRAND_FG = "FFFFFF"      # White
HEADER_BG = "405FAB"     # Digital Blue — header rows (per Design-System §4 Excel spec)
HEADER_FG = "FFFFFF"     # White
ALT_ROW = "EDF2F9"       # Callout Tint — alternating body rows
BORDER_COLOR = "D8E1F0"  # Border blue-grey — thin cell borders
ACCENT_BG = "6B9DD4"     # Sky Blue — accent only
TILE_BLUE = "2E4780"     # Tile Blue — deep accents (summary labels)

# Brand tab order
BRAND_TAB_ORDER = ["Nissan", "BMW", "CDJR", "Chevrolet", "Lexus", "Ford"]

# Logo path — canonical DigitalCLIQ brand asset location
# Script is at .claude/skills/monthly-leasing/ → need ../../.. to reach project root
LOGO_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..",
    "Resources", "brand-assets",
    "digital-cliq-logo-solid-1000px-wide.png",
)

# ── Styles ───────────────────────────────────────────────────────
brand_fill = PatternFill(start_color=BRAND_BG, end_color=BRAND_BG, fill_type="solid")
header_fill = PatternFill(start_color=HEADER_BG, end_color=HEADER_BG, fill_type="solid")
alt_fill = PatternFill(start_color=ALT_ROW, end_color=ALT_ROW, fill_type="solid")
accent_fill = PatternFill(start_color=ACCENT_BG, end_color=ACCENT_BG, fill_type="solid")

# Fonts per Design-System: Dosis carries structure (titles, headers, labels),
# Roboto Slab carries reading (body cells).
brand_font = Font(name="Dosis", bold=True, size=14, color=BRAND_FG)
header_font = Font(name="Dosis", bold=True, size=10, color=HEADER_FG)
body_font = Font(name="Roboto Slab", size=10)
title_font = Font(name="Dosis", bold=True, size=16, color=BRAND_FG)
note_font = Font(name="Roboto Slab", size=10, color=BRAND_BG)
summary_label_font = Font(name="Dosis", bold=True, size=11, color=TILE_BLUE)
summary_value_font = Font(name="Roboto Slab", size=11)
summary_total_font = Font(name="Dosis", bold=True, size=11, color=BRAND_FG)

thin_border = Border(
    left=Side(style="thin", color=BORDER_COLOR),
    right=Side(style="thin", color=BORDER_COLOR),
    top=Side(style="thin", color=BORDER_COLOR),
    bottom=Side(style="thin", color=BORDER_COLOR),
)

center_align = Alignment(horizontal="center", vertical="center", wrap_text=False)
left_align = Alignment(horizontal="left", vertical="center", wrap_text=True)
right_align = Alignment(horizontal="right", vertical="center", wrap_text=False)

# ── Column config for brand offer tabs ───────────────────────────
LEASE_COLUMNS = [
    ("cap_date",          "Cap Date",       12),
    ("month",             "Month",          10),
    ("brand",             "Brand",          10),
    ("dealer_name",       "Dealer",         22),
    ("dealer_url",        "Dealer URL",     30),
    ("source_url",        "Source URL",     30),
    ("page_type",         "Page",           10),
    ("yr",                "Year",            7),
    ("make",              "Make",           10),
    ("model",             "Model",          15),
    ("trim",              "Trim",           12),
    ("msrp",              "MSRP",           10),
    ("pmt",               "Payment",         9),
    ("term_mo",           "Term",            7),
    ("das",               "DAS",            10),
    ("miles_yr",          "Miles/Yr",       10),
    ("sec_dep",           "Sec Dep",        10),
    ("exp",               "Expires",        12),
    ("vin",               "VIN",            20),
    ("is_national",       "Natl",            6),
    ("disclaimer_scope",  "Disc Scope",     10),
    ("disclaimer_text",   "Disclaimer",     45),
    ("info_flags",        "Info Flags",     16),
    ("parse_note",        "Notes",          20),
    ("pmt_to_msrp",       "Pmt/MSRP",       9),
    ("das_to_msrp",       "DAS/MSRP",       9),
    ("source_credit",     "Credit",         12),
    ("run_id",            "Run ID",         12),
]


# ── Data Validation ───────────────────────────────────────────────

# Schema spec: {field_name: (expected_type, required)}
# Types: "str", "int", "float", "num" (int|float), "list", "dict", "list[dict]", "bool01"
COMBINED_META_SCHEMA = {
    "month":            ("str",   True),
    "cap_date":         ("str",   True),
    "run_timestamp":    ("str",   True),
    "total_dealers":    ("num",   True),
    "total_offers":     ("num",   True),
    "brands_included":  ("list",  True),
    "brand_runs":       ("dict",  False),
}

BRAND_RUN_SCHEMA = {
    "run_timestamp":      ("str", False),
    "dealers":            ("num", True),
    "dealers_with_offers":("num", True),
    "offers":             ("num", True),
}

OFFER_REQUIRED_FIELDS = {
    "brand":            "str",
    "dealer_name":      "str",
    "dealer_url":       "str",
    "pmt":              "num",
}

OFFER_ALL_FIELDS = {
    "brand": "str", "dealer_name": "str", "dealer_url": "str",
    "source_url": "str", "page_type": "str", "yr": "num", "make": "str",
    "model": "str", "trim": "str", "msrp": "num", "pmt": "num",
    "term_mo": "num", "das": "num", "miles_yr": "num", "sec_dep": "str",
    "exp": "str", "vin": "str", "is_national": "bool01",
    "disclaimer_scope": "str", "disclaimer_text": "str",
    "info_flags": "str", "parse_note": "str", "source_credit": "str",
}

DEALER_STATUS_SCHEMA = {
    "name":          ("str",  True),
    "url":           ("str",  True),
    "offers_found":  ("num",  False),
    "status":        ("str",  False),
}


def _type_name(expected):
    """Human-readable type label."""
    mapping = {
        "str": "string", "int": "integer", "float": "float",
        "num": "number (int or float)", "list": "list",
        "dict": "dict", "list[dict]": "list of dicts", "bool01": "0 or 1",
    }
    return mapping.get(expected, expected)


def _check_type(value, expected):
    """Check if value matches the expected type spec."""
    if expected == "str":
        return isinstance(value, str)
    elif expected == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    elif expected == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    elif expected == "num":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    elif expected == "list":
        return isinstance(value, list)
    elif expected == "dict":
        return isinstance(value, dict)
    elif expected == "list[dict]":
        return isinstance(value, list) and all(isinstance(i, dict) for i in value)
    elif expected == "bool01":
        return value in (0, 1)
    return True


def validate_data(data, source_path="<input>"):
    """
    Validate the combined lease data JSON before report generation.

    Checks:
      1. All required top-level and nested fields exist
      2. Data types match template expectations (list-of-dicts vs flat dict)
      3. No empty/null values in required fields

    Returns (is_valid, errors) where errors is a list of descriptive strings.
    Prints a clear error report showing expected vs actual format on failure.
    """
    errors = []

    # ── 1. Top-level structure ────────────────────────────────────
    if not isinstance(data, dict):
        errors.append(
            f"Top-level: expected dict, got {type(data).__name__}\n"
            f"  Expected: {{\"metadata\": {{...}}, \"offers\": [...], \"dealer_status\": [...]}}\n"
            f"  Actual:   {type(data).__name__}"
        )
        return False, errors

    # Check top-level keys
    for key, expected_type in [("metadata", "dict"), ("offers", "list[dict]"), ("dealer_status", "list[dict]")]:
        val = data.get(key)
        if val is None:
            errors.append(
                f"Top-level: missing required key '{key}'\n"
                f"  Expected: {_type_name(expected_type)}\n"
                f"  Actual:   key not present"
            )
        elif not _check_type(val, expected_type):
            actual = type(val).__name__
            if isinstance(val, list) and val and not isinstance(val[0], dict):
                actual = f"list of {type(val[0]).__name__}"
            errors.append(
                f"Top-level key '{key}': wrong type\n"
                f"  Expected: {_type_name(expected_type)}\n"
                f"  Actual:   {actual}"
            )

    # ── 2. Metadata fields ────────────────────────────────────────
    metadata = data.get("metadata", {})
    if isinstance(metadata, dict):
        for field, (exp_type, required) in COMBINED_META_SCHEMA.items():
            val = metadata.get(field)
            if val is None:
                if required:
                    errors.append(
                        f"metadata.{field}: missing required field\n"
                        f"  Expected: {_type_name(exp_type)}\n"
                        f"  Actual:   not present"
                    )
            elif not _check_type(val, exp_type):
                errors.append(
                    f"metadata.{field}: wrong type\n"
                    f"  Expected: {_type_name(exp_type)}\n"
                    f"  Actual:   {type(val).__name__} = {repr(val)[:80]}"
                )
            elif required and exp_type == "str" and not val:
                errors.append(
                    f"metadata.{field}: required field is empty\n"
                    f"  Expected: non-empty {_type_name(exp_type)}\n"
                    f"  Actual:   \"\""
                )

        # Validate brand_runs sub-structure
        brand_runs = metadata.get("brand_runs", {})
        if isinstance(brand_runs, dict):
            for brand_key, run_info in brand_runs.items():
                if not isinstance(run_info, dict):
                    errors.append(
                        f"metadata.brand_runs.{brand_key}: wrong type\n"
                        f"  Expected: dict with keys {list(BRAND_RUN_SCHEMA.keys())}\n"
                        f"  Actual:   {type(run_info).__name__}"
                    )
                    continue
                for field, (exp_type, required) in BRAND_RUN_SCHEMA.items():
                    val = run_info.get(field)
                    if val is None and required:
                        errors.append(
                            f"metadata.brand_runs.{brand_key}.{field}: missing required field\n"
                            f"  Expected: {_type_name(exp_type)}\n"
                            f"  Actual:   not present"
                        )
                    elif val is not None and not _check_type(val, exp_type):
                        errors.append(
                            f"metadata.brand_runs.{brand_key}.{field}: wrong type\n"
                            f"  Expected: {_type_name(exp_type)}\n"
                            f"  Actual:   {type(val).__name__} = {repr(val)[:80]}"
                        )

    # ── 3. Offers validation ──────────────────────────────────────
    offers = data.get("offers", [])
    if isinstance(offers, list):
        if not offers:
            errors.append(
                "offers: empty list — no lease offers to generate report from\n"
                "  Expected: list with 1+ offer dicts\n"
                "  Actual:   []"
            )
        for i, offer in enumerate(offers):
            if not isinstance(offer, dict):
                errors.append(
                    f"offers[{i}]: wrong type\n"
                    f"  Expected: dict\n"
                    f"  Actual:   {type(offer).__name__}"
                )
                continue

            # Required fields must exist and be non-null
            for field, exp_type in OFFER_REQUIRED_FIELDS.items():
                val = offer.get(field)
                if val is None:
                    errors.append(
                        f"offers[{i}].{field}: missing required field\n"
                        f"  Expected: {_type_name(exp_type)} (non-null)\n"
                        f"  Actual:   not present\n"
                        f"  Offer:    {offer.get('dealer_name', '?')} / {offer.get('model', '?')}"
                    )
                elif exp_type == "str" and not isinstance(val, str):
                    errors.append(
                        f"offers[{i}].{field}: wrong type\n"
                        f"  Expected: {_type_name(exp_type)}\n"
                        f"  Actual:   {type(val).__name__} = {repr(val)[:60]}\n"
                        f"  Offer:    {offer.get('dealer_name', '?')} / {offer.get('model', '?')}"
                    )
                elif exp_type == "num" and not isinstance(val, (int, float)):
                    errors.append(
                        f"offers[{i}].{field}: wrong type\n"
                        f"  Expected: {_type_name(exp_type)}\n"
                        f"  Actual:   {type(val).__name__} = {repr(val)[:60]}\n"
                        f"  Offer:    {offer.get('dealer_name', '?')} / {offer.get('model', '?')}"
                    )

            # Type checks on all fields (non-required can be present but wrong type)
            for field, exp_type in OFFER_ALL_FIELDS.items():
                val = offer.get(field)
                if val is not None and not _check_type(val, exp_type):
                    errors.append(
                        f"offers[{i}].{field}: wrong type\n"
                        f"  Expected: {_type_name(exp_type)}\n"
                        f"  Actual:   {type(val).__name__} = {repr(val)[:60]}\n"
                        f"  Offer:    {offer.get('dealer_name', '?')} / {offer.get('model', '?')}"
                    )

            # Cap detailed per-offer errors at first 10 offers to avoid flood
            if len(errors) > 50:
                errors.append(f"... (stopped checking at offer {i}, too many errors)")
                break

    # ── 4. Dealer status validation ───────────────────────────────
    dealer_status = data.get("dealer_status", [])
    if isinstance(dealer_status, list):
        for i, ds in enumerate(dealer_status):
            if not isinstance(ds, dict):
                errors.append(
                    f"dealer_status[{i}]: wrong type\n"
                    f"  Expected: dict\n"
                    f"  Actual:   {type(ds).__name__}"
                )
                continue
            for field, (exp_type, required) in DEALER_STATUS_SCHEMA.items():
                val = ds.get(field)
                if val is None and required:
                    errors.append(
                        f"dealer_status[{i}].{field}: missing required field\n"
                        f"  Expected: {_type_name(exp_type)}\n"
                        f"  Actual:   not present"
                    )

    # ── Report ────────────────────────────────────────────────────
    is_valid = len(errors) == 0

    if not is_valid:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"VALIDATION FAILED — {source_path}", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        print(f"{len(errors)} error(s) found:\n", file=sys.stderr)
        for i, err in enumerate(errors, 1):
            print(f"  {i}. {err}\n", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)

    return is_valid, errors


def calculate_derived(offer, cap_date, month, run_id):
    """Add calculated columns and defaults to an offer dict."""
    o = dict(offer)
    o.setdefault("cap_date", cap_date)
    o.setdefault("month", month)
    o.setdefault("run_id", run_id)
    o.setdefault("source_credit", "DigitalCLIQ")

    pmt = o.get("pmt") or 0
    msrp = o.get("msrp") or 0
    das = o.get("das") or 0

    o["pmt_to_msrp"] = round(pmt / msrp, 4) if msrp > 0 else 0
    o["das_to_msrp"] = round(das / msrp, 4) if msrp > 0 else 0

    return o


def add_masthead(ws, title, report_date, col_count):
    """Design-System §4 Excel masthead on rows 1-2 of a visible sheet:
    Digital Blue fill spanning the sheet's used columns, WHITE knockout logo
    anchored A1 (~0.35in tall, true aspect ratio), sheet title in white
    Dosis 14 Bold, report date on the right side."""
    col_count = max(col_count, 6)

    # No default grid look (Design-System §4): thin token borders only
    ws.sheet_view.showGridLines = False

    # Sheet title: white Dosis 14 Bold, merged across rows 1-2
    title_end = max(4, col_count - 2)
    ws.merge_cells(start_row=1, start_column=3, end_row=2, end_column=title_end)
    tcell = ws.cell(row=1, column=3)
    tcell.value = title
    tcell.font = brand_font  # Dosis 14 Bold white
    tcell.alignment = center_align

    # Report date: right side of the band, merged across rows 1-2
    ws.merge_cells(start_row=1, start_column=col_count - 1, end_row=2, end_column=col_count)
    dcell = ws.cell(row=1, column=col_count - 1)
    dcell.value = report_date
    dcell.font = Font(name="Dosis", bold=True, size=10, color=BRAND_FG)
    dcell.alignment = right_align

    # Digital Blue fill across the whole band, AFTER merging so covered
    # cells keep the fill too (merge_cells strips styles from covered cells)
    for r in (1, 2):
        for c in range(1, col_count + 1):
            ws.cell(row=r, column=c).fill = brand_fill
        ws.row_dimensions[r].height = 22  # 2 x 22pt band (~0.6in)

    # White knockout logo anchored A1, ~0.35in tall (34px @96dpi), true aspect
    logo_resolved = os.path.normpath(LOGO_PATH)
    if not os.path.exists(logo_resolved):
        raise RuntimeError(
            f"DigitalCLIQ logo not found at: {logo_resolved!r}\n"
            f"Canonical path: /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png"
        )
    img = XlImage(logo_resolved)
    aspect = img.width / img.height if img.height else 1.0
    img.height = 34
    img.width = int(round(34 * aspect))
    ws.add_image(img, "A1")
    return True


def build_readme(ws, metadata, report_date):
    """Build the README tab with DigitalCLIQ branding and logo."""
    ws.column_dimensions["A"].width = 80
    for col, w in (("B", 12), ("C", 12), ("D", 12), ("E", 12), ("F", 14)):
        ws.column_dimensions[col].width = w

    # Rows 1-2: Design-System masthead (blue band + white logo + title + date)
    add_masthead(ws, "Competitive Lease Tracker", report_date, 6)

    ws["A4"] = "Developed by DigitalCLIQ"
    ws["A4"].font = Font(name="Dosis", bold=True, size=12, color=BRAND_BG)

    ws["A5"] = "Digital Strategy & Development"
    ws["A5"].font = Font(name="Dosis", italic=True, size=10, color=ACCENT_BG)

    ws["A7"] = "Automated monthly capture of new vehicle lease specials from Southern California dealerships."
    ws["A7"].font = body_font

    brands = metadata.get("brands_included", [])
    brand_names = ", ".join(b.upper() if b == "cdjr" else b.capitalize() for b in brands)
    ws["A8"] = f"Brands covered: {brand_names}"
    ws["A8"].font = body_font

    ws["A9"] = "Each brand has its own tab. See the Summary tab (first tab) for a cross-brand overview."
    ws["A9"].font = body_font

    ws["A11"] = "Data refreshed monthly. Do not manually edit the offer tabs."
    ws["A11"].font = note_font


def build_summary_tab(ws, brand_data, metadata, report_date):
    """Build the styled Summary tab (first worksheet): masthead, key stats as
    large Dosis cells with Sky Blue numbers, how-to-read notes, then the
    cross-brand summary table."""
    col_count = 10

    headers = [
        ("Brand",           14),
        ("Dealers",          9),
        ("w/ Offers",        9),
        ("Offers",           8),
        ("Avg Pmt",         10),
        ("Min Pmt",         10),
        ("Max Pmt",         10),
        ("Avg DAS",         10),
        ("Models",           8),
        ("Last Run",        14),
    ]
    for i, (label, width) in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = width

    # Rows 1-2: Design-System masthead
    add_masthead(ws, "Competitive Lease Tracker  --  Summary", report_date, col_count)

    # ── Compute per-brand rows + totals first (stats band needs totals) ──
    brand_runs = metadata.get("brand_runs", {})
    rows_data = []
    totals = {"dealers": 0, "with_offers": 0, "offers": 0, "all_pmts": [], "all_das": [], "models": set()}

    for brand_display in BRAND_TAB_ORDER:
        brand_key = brand_display.lower()
        offers = brand_data.get(brand_display, [])
        if not offers and brand_key not in brand_runs:
            continue

        run_info = brand_runs.get(brand_key, {})
        n_dealers = run_info.get("dealers", 0)
        n_with_offers = run_info.get("dealers_with_offers", 0)
        n_offers = len(offers)

        pmts = [o.get("pmt", 0) for o in offers if o.get("pmt", 0) > 0]
        das_vals = [o.get("das", 0) for o in offers if o.get("das", 0) > 0]
        models = set(o.get("model", "") for o in offers if o.get("model"))

        avg_pmt = round(sum(pmts) / len(pmts)) if pmts else 0
        min_pmt = min(pmts) if pmts else 0
        max_pmt = max(pmts) if pmts else 0
        avg_das = round(sum(das_vals) / len(das_vals)) if das_vals else 0
        last_run = run_info.get("run_timestamp", "")[:10]

        rows_data.append([brand_display, n_dealers, n_with_offers, n_offers,
                          f"${avg_pmt:,}" if avg_pmt else "-",
                          f"${min_pmt:,}" if min_pmt else "-",
                          f"${max_pmt:,}" if max_pmt else "-",
                          f"${avg_das:,}" if avg_das else "-",
                          len(models), last_run])

        totals["dealers"] += n_dealers
        totals["with_offers"] += n_with_offers
        totals["offers"] += n_offers
        totals["all_pmts"].extend(pmts)
        totals["all_das"].extend(das_vals)
        totals["models"].update(models)

    all_pmts = totals["all_pmts"]
    all_das = totals["all_das"]
    total_avg_pmt = round(sum(all_pmts) / len(all_pmts)) if all_pmts else 0
    total_min_pmt = min(all_pmts) if all_pmts else 0
    total_max_pmt = max(all_pmts) if all_pmts else 0
    total_avg_das = round(sum(all_das) / len(all_das)) if all_das else 0

    # ── Rows 4-5: key stats band, large Dosis cells with Sky Blue numbers ──
    stat_value_font = Font(name="Dosis", bold=True, size=22, color=ACCENT_BG)
    stats = [
        ("BRANDS",          str(len(rows_data))),
        ("DEALERS TRACKED", str(totals["dealers"])),
        ("LEASE OFFERS",    str(totals["offers"])),
        ("AVG PAYMENT",     f"${total_avg_pmt:,}" if total_avg_pmt else "-"),
        ("LOWEST PAYMENT",  f"${total_min_pmt:,}" if total_min_pmt else "-"),
    ]
    for i, (label, value) in enumerate(stats):
        c1 = 1 + i * 2
        c2 = c1 + 1
        ws.merge_cells(start_row=4, start_column=c1, end_row=4, end_column=c2)
        lcell = ws.cell(row=4, column=c1, value=label)
        lcell.font = summary_label_font
        lcell.alignment = center_align
        ws.merge_cells(start_row=5, start_column=c1, end_row=5, end_column=c2)
        vcell = ws.cell(row=5, column=c1, value=value)
        vcell.font = stat_value_font
        vcell.alignment = center_align
    ws.row_dimensions[4].height = 16
    ws.row_dimensions[5].height = 32

    # ── Row 7: how-to-read note on Callout Tint ──
    ws.merge_cells(start_row=7, start_column=1, end_row=7, end_column=col_count)
    note_cell = ws.cell(
        row=7, column=1,
        value=("How to read: each row below is one brand. Payments are advertised monthly lease "
               "payments; DAS = due at signing. Full offer detail lives on each brand's tab; "
               "dealer coverage and scrape status on the Dealers tab."),
    )
    note_cell.font = note_font
    note_cell.alignment = left_align
    for c in range(1, col_count + 1):
        ws.cell(row=7, column=c).fill = alt_fill
    ws.row_dimensions[7].height = 28

    # ── Row 9: table headers; data from row 10 ──
    header_row = 9
    for i, (label, width) in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=i, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = thin_border
    ws.row_dimensions[header_row].height = 22
    ws.freeze_panes = "A10"

    row = header_row + 1
    for values in rows_data:
        is_alt = ((row - header_row) % 2 == 0)
        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.font = body_font
            cell.border = thin_border
            cell.alignment = center_align
            if is_alt:
                cell.fill = alt_fill
        row += 1

    # Totals row
    total_values = [
        "TOTALS", totals["dealers"], totals["with_offers"], totals["offers"],
        f"${total_avg_pmt:,}" if total_avg_pmt else "-",
        f"${total_min_pmt:,}" if total_min_pmt else "-",
        f"${total_max_pmt:,}" if total_max_pmt else "-",
        f"${total_avg_das:,}" if total_avg_das else "-",
        len(totals["models"]), "",
    ]

    for col, val in enumerate(total_values, 1):
        cell = ws.cell(row=row, column=col, value=val)
        cell.font = summary_total_font
        cell.fill = brand_fill
        cell.border = thin_border
        cell.alignment = center_align


def build_brand_tab(ws, brand_display, offers, cap_date, month, run_id):
    """Build a single brand tab with offer data."""
    col_count = len(LEASE_COLUMNS)

    # Sort offers by dealer_name, then model
    offers = sorted(offers, key=lambda o: (o.get("dealer_name", ""), o.get("model", "")))

    # Column widths first, then rows 1-2 Design-System masthead
    for i, (key, label, width) in enumerate(LEASE_COLUMNS, 1):
        ws.column_dimensions[get_column_letter(i)].width = width
    add_masthead(ws, f"{brand_display} Lease Tracker", cap_date, col_count)

    # Headers (row 3, below the masthead)
    header_row = 3
    for i, (key, label, width) in enumerate(LEASE_COLUMNS, 1):
        cell = ws.cell(row=header_row, column=i, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = thin_border
    ws.row_dimensions[header_row].height = 22

    ws.freeze_panes = "A4"
    last_row = header_row + max(len(offers), 1)
    ws.auto_filter.ref = f"A{header_row}:{get_column_letter(col_count)}{last_row}"

    # Data rows (start row 4)
    for row_idx, offer in enumerate(offers, header_row + 1):
        o = calculate_derived(offer, cap_date, month, run_id)
        is_alt = ((row_idx - header_row) % 2 == 0)

        for col_idx, (key, label, width) in enumerate(LEASE_COLUMNS, 1):
            val = o.get(key, "")
            if val is None:
                val = ""
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = body_font
            cell.border = thin_border
            cell.alignment = left_align
            if is_alt:
                cell.fill = alt_fill


def build_dealers(ws, dealer_status, roster, report_date):
    """Build the Dealers tab grouped by brand with status info."""
    headers = [
        ("Brand",    10),
        ("Dealer",   26),
        ("Website",  36),
        ("County",   14),
        ("State",     8),
        ("Offers",    8),
        ("Status",   14),
        ("Notes",    30),
    ]

    for i, (label, width) in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = width

    # Rows 1-2: Design-System masthead
    add_masthead(ws, "Dealer Coverage & Status", report_date, len(headers))

    header_row = 3
    for i, (label, width) in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=i, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = thin_border
    ws.row_dimensions[header_row].height = 22
    ws.freeze_panes = "A4"

    # Build a lookup from dealer_status
    status_lookup = {}
    for ds in dealer_status:
        key = ds.get("url", ds.get("dealer_url", ""))
        status_lookup[key] = ds

    row = header_row + 1
    brands = roster.get("brands", {})
    for brand_display in BRAND_TAB_ORDER:
        brand_key = brand_display.lower()
        brand_info = brands.get(brand_key, {})
        dealers = brand_info.get("dealers", [])

        for dealer in dealers:
            url = dealer.get("url", "")
            ds = status_lookup.get(url, {})

            values = [
                brand_display,
                dealer.get("name", ""),
                url,
                dealer.get("county", ""),
                dealer.get("state", ""),
                ds.get("offers_found", ""),
                ds.get("status", ""),
                ds.get("note", ""),
            ]

            is_alt = ((row - header_row) % 2 == 0)
            for col, val in enumerate(values, 1):
                cell = ws.cell(row=row, column=col, value=val)
                cell.font = body_font
                cell.border = thin_border
                if is_alt:
                    cell.fill = alt_fill

            row += 1


def build_run_log(ws, metadata, report_date):
    """Build the Run Log tab with one row per brand run."""
    headers = [
        ("Brand",      12),
        ("Run ID",     14),
        ("Timestamp",  22),
        ("Status",     10),
        ("Dealers",    10),
        ("Offers",     10),
    ]

    for i, (label, width) in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = width

    # Rows 1-2: Design-System masthead
    add_masthead(ws, "Run Log", report_date, len(headers))

    header_row = 3
    for i, (label, width) in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=i, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = thin_border
    ws.row_dimensions[header_row].height = 22
    ws.freeze_panes = "A4"

    brand_runs = metadata.get("brand_runs", {})
    row = header_row + 1
    for brand_display in BRAND_TAB_ORDER:
        brand_key = brand_display.lower()
        if brand_key not in brand_runs:
            continue

        info = brand_runs[brand_key]
        ts = info.get("run_timestamp", "")
        run_id = ts[:10].replace("-", "") if ts else ""

        values = [
            brand_display,
            run_id,
            ts,
            "complete",
            info.get("dealers", 0),
            info.get("offers", 0),
        ]

        is_alt = ((row - header_row) % 2 == 0)
        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.font = body_font
            cell.border = thin_border
            if is_alt:
                cell.fill = alt_fill

        row += 1


def main():
    parser = argparse.ArgumentParser(description="Generate DigitalCLIQ lease report")
    parser.add_argument("json_path", help="Path to combined lease data JSON")
    parser.add_argument("output_dir", help="Directory to write the Excel file")
    parser.add_argument("--roster", required=True, help="Path to dealer_roster.json")
    args = parser.parse_args()

    with open(args.json_path, "r") as f:
        data = json.load(f)

    # Validate data before rendering
    is_valid, val_errors = validate_data(data, args.json_path)
    if not is_valid:
        print(f"ERROR: Input data failed validation with {len(val_errors)} error(s).", file=sys.stderr)
        print("Fix the data and re-run. See error details above.", file=sys.stderr)
        sys.exit(1)

    with open(args.roster, "r") as f:
        roster = json.load(f)

    metadata = data.get("metadata", {})
    offers = data.get("offers", [])
    dealer_status = data.get("dealer_status", [])
    cap_date = metadata.get("cap_date", datetime.now().strftime("%Y-%m-%d"))
    month = metadata.get("month", datetime.now().strftime("%Y-%m"))
    run_id = metadata.get("run_timestamp", datetime.now().isoformat())[:10].replace("-", "")

    # Group offers by brand display name
    brand_data = defaultdict(list)
    for offer in offers:
        brand = offer.get("brand", "")
        # Normalize to display name
        display = brand
        for bkey, binfo in roster.get("brands", {}).items():
            if binfo.get("display_name", "").lower() == brand.lower() or bkey == brand.lower():
                display = binfo["display_name"]
                break
        brand_data[display].append(offer)

    # Add grouped dealer status to metadata for summary tab
    metadata["dealer_status_grouped"] = {}
    for ds in dealer_status:
        brand = ds.get("brand", "")
        metadata["dealer_status_grouped"].setdefault(brand, []).append(ds)

    # Build workbook — styled Summary is the FIRST worksheet (Design-System §4)
    wb = Workbook()

    # Summary tab (first)
    ws_summary = wb.active
    ws_summary.title = "Summary"
    build_summary_tab(ws_summary, brand_data, metadata, cap_date)

    # Per-brand tabs
    for brand_display in BRAND_TAB_ORDER:
        if brand_display in brand_data and brand_data[brand_display]:
            ws = wb.create_sheet(brand_display)
            build_brand_tab(ws, brand_display, brand_data[brand_display],
                           cap_date, month, run_id)

    # Dealers tab
    ws_dealers = wb.create_sheet("Dealers")
    build_dealers(ws_dealers, dealer_status, roster, cap_date)

    # Run Log tab
    ws_log = wb.create_sheet("Run Log")
    build_run_log(ws_log, metadata, cap_date)

    # README tab (last)
    ws_readme = wb.create_sheet("README")
    build_readme(ws_readme, metadata, cap_date)

    # Save
    os.makedirs(args.output_dir, exist_ok=True)
    filename = f"DigitalCLIQ_Lease_Tracker_{month}.xlsx"
    output_path = os.path.join(args.output_dir, filename)
    wb.save(output_path)
    print(f"Report saved: {output_path}")
    print(f"Total offers: {len(offers)}")
    print(f"Brand tabs: {', '.join(b for b in BRAND_TAB_ORDER if b in brand_data)}")


if __name__ == "__main__":
    main()
