"""
report_builder.py — Branded DigitalCLIQ Excel report for paid media waste audits.

Generates a 10-tab workbook:
  1. Cover / Read Me
  2. Executive Summary
  3. Waste Audit
  4. Funnel Allocation
  5. Source Performance
  6. Vendor/Lead Provider ROI
  7. Funnel KPI Detail
  8. Suggestions for Discussion
  9. Delta vs. Prior Period (optional)
  10. Raw Data
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.styles import (
    Alignment, Border, Font, PatternFill, Side, numbers,
)
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XlImage

# -----------------------------------------------------------------------
# Brand constants — DigitalCLIQ design-system tokens
# (Resources/design-system/Design-System.md; palette-only, no off-token colors)
# -----------------------------------------------------------------------
BRAND_BLUE = "405FAB"        # Digital Blue
SKY_BLUE = "6B9DD4"          # Sky Blue — strong / positive treatment
WARM_GREY = "949592"         # Warm Grey — weak / negative treatment
TILE_BLUE = "2E4780"         # Tile Blue — deep accent
CALLOUT_TINT = "EDF2F9"      # Callout Tint — light fill / alternating rows
BORDER_BLUE = "D8E1F0"       # Border token

BRAND_BLUE_FILL = PatternFill(start_color=BRAND_BLUE, end_color=BRAND_BLUE, fill_type="solid")
LIGHT_BLUE_FILL = PatternFill(start_color=CALLOUT_TINT, end_color=CALLOUT_TINT, fill_type="solid")
WHITE_FILL = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
LIGHT_GRAY_FILL = PatternFill(start_color=CALLOUT_TINT, end_color=CALLOUT_TINT, fill_type="solid")
# Status treatments (palette-only; explicit text labels carry the meaning):
# Sky Blue = strong/good, border-tint = watch/medium, Warm Grey = weak/bad.
GREEN_FILL = PatternFill(start_color=SKY_BLUE, end_color=SKY_BLUE, fill_type="solid")
YELLOW_FILL = PatternFill(start_color=BORDER_BLUE, end_color=BORDER_BLUE, fill_type="solid")
RED_FILL = PatternFill(start_color=WARM_GREY, end_color=WARM_GREY, fill_type="solid")

# Dosis carries structure (headings, labels); Roboto Slab carries reading (body).
HEADER_FONT = Font(name="Dosis", size=11, bold=True, color="FFFFFF")
TITLE_FONT = Font(name="Dosis", size=16, bold=True, color=BRAND_BLUE)
SUBTITLE_FONT = Font(name="Dosis", size=12, bold=True, color=BRAND_BLUE)
BODY_FONT = Font(name="Roboto Slab", size=10, color="10162A")
BOLD_FONT = Font(name="Roboto Slab", size=10, bold=True, color="10162A")
SMALL_FONT = Font(name="Roboto Slab", size=9, color=WARM_GREY)

THIN_BORDER = Border(
    left=Side(style="thin", color=BORDER_BLUE),
    right=Side(style="thin", color=BORDER_BLUE),
    top=Side(style="thin", color=BORDER_BLUE),
    bottom=Side(style="thin", color=BORDER_BLUE),
)

LOGO_PATH = (
    Path.home() / "Desktop" / "DigitalCLIQ" / "Resources" / "brand-assets"
    / "digital-cliq-logo-solid-1000px-wide.png"
)

OUTPUT_DIR = Path.home() / "Desktop" / "DigitalCLIQ" / "outputs"


MASTHEAD_TITLE_FONT = Font(name="Dosis", size=14, bold=True, color="FFFFFF")
MASTHEAD_DATE_FONT = Font(name="Dosis", size=10, bold=True, color="FFFFFF")


def _add_masthead(ws, title: str, report_date: str, ncols: int):
    """Design-System §4 masthead on rows 1-2 of a sheet.

    Digital Blue fill spanning the sheet's used columns, WHITE knockout logo
    anchored A1 (~0.35in tall, true aspect ratio), sheet title in white
    Dosis 14 Bold, report date on the right side. Fails loudly if the logo
    is missing. Content on every sheet starts at row 3 or below.
    """
    ncols = max(ncols, 6)
    for r in (1, 2):
        for c in range(1, ncols + 1):
            ws.cell(row=r, column=c).fill = BRAND_BLUE_FILL
        ws.row_dimensions[r].height = 22  # 2 x 22pt ≈ 0.6in band

    # Title: merged block clear of the logo (cols A-B), stops short of the date block.
    ws.merge_cells(start_row=1, start_column=3, end_row=2, end_column=ncols - 2)
    t = ws.cell(row=1, column=3, value=title)
    t.font = MASTHEAD_TITLE_FONT
    t.alignment = Alignment(horizontal="left", vertical="center")

    # Report date: right side of the band.
    ws.merge_cells(start_row=1, start_column=ncols - 1, end_row=2, end_column=ncols)
    d = ws.cell(row=1, column=ncols - 1, value=report_date)
    d.font = MASTHEAD_DATE_FONT
    d.alignment = Alignment(horizontal="right", vertical="center")

    if not LOGO_PATH.exists():
        raise FileNotFoundError(
            f"DigitalCLIQ logo not found at: {LOGO_PATH!s}\n"
            f"Canonical path: /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png"
        )
    img = XlImage(str(LOGO_PATH))
    target_h = 34  # ~0.35in at 96dpi
    scale = target_h / img.height
    img.height = target_h
    img.width = int(img.width * scale)
    ws.add_image(img, "A1")


def _write_header_row(ws, row: int, headers: list[str], col_start: int = 1):
    """Write a branded header row."""
    for i, header in enumerate(headers, start=col_start):
        cell = ws.cell(row=row, column=i, value=header)
        cell.font = HEADER_FONT
        cell.fill = BRAND_BLUE_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER


def _write_data_row(ws, row: int, values: list, col_start: int = 1, alt_shade: bool = False):
    """Write a data row with optional alternating shade."""
    fill = LIGHT_GRAY_FILL if alt_shade else WHITE_FILL
    for i, val in enumerate(values, start=col_start):
        cell = ws.cell(row=row, column=i, value=val)
        cell.font = BODY_FONT
        cell.fill = fill
        cell.border = THIN_BORDER
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        # Auto-format currency
        if isinstance(val, (int, float)):
            if val > 100:
                cell.number_format = '#,##0'
            elif 0 < val < 1:
                cell.number_format = '0.0%'
            else:
                cell.number_format = '#,##0.00'


def _severity_fill(severity: str) -> PatternFill:
    """Return fill color for severity level."""
    return {"high": RED_FILL, "medium": YELLOW_FILL, "low": GREEN_FILL}.get(
        severity, WHITE_FILL
    )


def _auto_width(ws, min_width: int = 12, max_width: int = 45):
    """Auto-fit column widths based on content."""
    for col in ws.columns:
        max_len = min_width
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.value:
                max_len = max(max_len, min(len(str(cell.value)), max_width))
        ws.column_dimensions[col_letter].width = max_len + 2


# -----------------------------------------------------------------------
# Tab builders
# -----------------------------------------------------------------------

def _build_cover(wb, audit: dict):
    """Tab 1: Cover / Read Me."""
    ws = wb.active
    ws.title = "Cover"
    ws.sheet_properties.tabColor = BRAND_BLUE

    # Rows 1-2 Digital Blue masthead: white logo, white Dosis 14 title, date right
    _add_masthead(ws, "Paid Media Waste Audit", audit["audit_date"], ncols=6)

    # Title area below masthead
    ws.row_dimensions[4].height = 8  # spacer
    ws.merge_cells("A5:F5")
    c = ws.cell(row=5, column=1, value="Paid Media Waste Audit")
    c.font = TITLE_FONT

    ws.merge_cells("A6:F6")
    c = ws.cell(row=6, column=1, value=audit["client"])
    c.font = SUBTITLE_FONT

    ws.row_dimensions[8].height = 8  # spacer

    info = [
        ("Period:", audit["period"]),
        ("Audit Date:", audit["audit_date"]),
        ("Brand Tier:", audit["benchmarks_used"]["tier_label"]),
        ("Data Sources:", ", ".join(
            s["source"] for s in audit.get("source_performance", [])
        ) or "See source tabs"),
        ("Total Rows Analyzed:", audit["row_count"]),
    ]
    row = 9
    for label, val in info:
        ws.cell(row=row, column=1, value=label).font = BOLD_FONT
        ws.cell(row=row, column=2, value=val).font = BODY_FONT
        row += 1

    row += 1
    ws.merge_cells(f"A{row}:F{row}")
    ws.cell(row=row, column=1, value="About This Report").font = SUBTITLE_FONT
    row += 1

    about_text = (
        "This report identifies potential areas of paid media waste across your "
        "digital advertising channels. It uses automotive-specific KPIs — VDP views, "
        "form fills, phone calls, cost per lead — rather than generic ROAS metrics.\n\n"
        "All suggestions are starting points for your GM/GSM discussion, not directives. "
        "Every lead source has nuance that the data alone cannot capture."
    )
    ws.merge_cells(f"A{row}:F{row + 3}")
    c = ws.cell(row=row, column=1, value=about_text)
    c.font = BODY_FONT
    c.alignment = Alignment(wrap_text=True, vertical="top")
    row += 5

    # Benchmark sources
    ws.merge_cells(f"A{row}:F{row}")
    ws.cell(row=row, column=1, value="Benchmark Sources").font = SUBTITLE_FONT
    row += 1
    for src in audit["benchmarks_used"].get("source", []):
        ws.cell(row=row, column=1, value=f"  - {src}").font = SMALL_FONT
        row += 1
    ws.cell(row=row, column=1,
            value=f"  Last updated: {audit['benchmarks_used']['last_updated']}").font = SMALL_FONT
    row += 2

    # Disclaimer
    ws.merge_cells(f"A{row}:F{row + 1}")
    c = ws.cell(row=row, column=1, value=audit.get("suggestion_disclaimer", ""))
    c.font = Font(name="Roboto Slab", size=9, italic=True, color=WARM_GREY)
    c.alignment = Alignment(wrap_text=True)

    _auto_width(ws)


def _build_executive_summary(wb, audit: dict):
    """Tab 2: Executive Summary."""
    ws = wb.create_sheet("Executive Summary")
    ws.sheet_properties.tabColor = BRAND_BLUE

    _add_masthead(ws, "Executive Summary", audit["audit_date"], ncols=6)

    es = audit["executive_summary"]
    metrics = [
        ("Total Spend", f"${es['total_spend']:,.2f}"),
        ("Total Leads", f"{es['total_leads']:,}"),
        ("Cost Per Lead (CPL)", f"${es['cpl']:,.2f}" if es["cpl"] else "N/A"),
        ("CTR", f"{es['ctr_pct']:.2f}%" if es["ctr_pct"] else "N/A"),
        ("Total VDP Views", f"{es['total_vdp_views']:,}"),
        ("", ""),
        ("Estimated Waste", f"${es['estimated_waste_usd']:,.2f}"),
        ("Estimated Waste %", f"{es['estimated_waste_pct']:.1f}%"),
        ("Total Findings", str(es["finding_count"])),
        ("High Severity", str(es["high_severity_count"])),
        ("Medium Severity", str(es["medium_severity_count"])),
        ("", ""),
        ("Brand Tier", es["tier_label"]),
        ("Benchmark CPL Ceiling", f"${es['benchmark_cpl_ceiling']}" if es["benchmark_cpl_ceiling"] else "N/A"),
        ("CPL vs. Benchmark", es["cpl_vs_benchmark"]),
    ]

    row = 4  # row 3 = spacer below masthead
    for label, val in metrics:
        if not label:
            row += 1
            continue
        ws.cell(row=row, column=1, value=label).font = BOLD_FONT
        c = ws.cell(row=row, column=2, value=val)
        c.font = BODY_FONT
        if "waste" in label.lower() and es.get("estimated_waste_usd", 0) > 0:
            c.fill = YELLOW_FILL
        if label == "CPL vs. Benchmark" and val == "above":
            c.fill = RED_FILL
        row += 1

    # Top opportunities
    row += 1
    ws.merge_cells(f"A{row}:D{row}")
    ws.cell(row=row, column=1, value="Top Discussion Topics").font = SUBTITLE_FONT
    row += 1
    for i, opp in enumerate(es.get("top_opportunities", []), 1):
        ws.merge_cells(f"A{row}:D{row}")
        ws.cell(row=row, column=1, value=f"{i}. {opp}").font = BODY_FONT
        ws.cell(row=row, column=1).alignment = Alignment(wrap_text=True)
        row += 1

    _auto_width(ws)


def _build_waste_audit(wb, audit: dict):
    """Tab 3: Waste Audit — line-by-line flagged items."""
    ws = wb.create_sheet("Waste Audit")
    ws.sheet_properties.tabColor = WARM_GREY

    _add_masthead(ws, "Waste Audit Findings", audit["audit_date"], ncols=7)

    headers = ["Rule", "Severity", "Campaign / Item", "Spend", "Leads", "Observation", "Waste $"]
    _write_header_row(ws, 4, headers)
    ws.freeze_panes = "A5"

    row = 5
    for i, f in enumerate(audit.get("findings", [])):
        campaign = f.get("campaign", f.get("device", ""))
        if f.get("rule") == "search_term_bleed":
            campaign = f"Search terms ({f.get('count', 0)} flagged)"

        values = [
            f.get("rule", ""),
            f.get("severity", ""),
            campaign,
            f.get("spend", 0),
            f.get("leads", f.get("leads_total", "")),
            f.get("observation", ""),
            f.get("waste_amount", 0),
        ]
        _write_data_row(ws, row, values, alt_shade=(i % 2 == 1))
        # Color-code severity
        ws.cell(row=row, column=2).fill = _severity_fill(f.get("severity", ""))
        row += 1

    # Summary row
    total_waste = sum(f.get("waste_amount", 0) for f in audit.get("findings", []))
    row += 1
    ws.cell(row=row, column=1, value="TOTAL IDENTIFIED WASTE").font = BOLD_FONT
    ws.cell(row=row, column=7, value=total_waste).font = BOLD_FONT
    ws.cell(row=row, column=7).number_format = '$#,##0.00'

    _auto_width(ws)


def _build_funnel_allocation(wb, audit: dict):
    """Tab 4: Funnel Allocation — spend by stage vs. recommended."""
    ws = wb.create_sheet("Funnel Allocation")
    ws.sheet_properties.tabColor = BRAND_BLUE

    _add_masthead(ws, "Funnel Stage Allocation", audit["audit_date"], ncols=8)
    ws.merge_cells("A3:H3")
    ws.cell(row=3, column=1,
            value="Recommended ranges are industry-typical, not prescriptive.").font = SMALL_FONT

    headers = ["Stage", "Spend", "% of Total", "Rec. Min %", "Rec. Max %",
               "Within Range?", "Campaigns", "Notes"]
    _write_header_row(ws, 5, headers)
    ws.freeze_panes = "A6"

    row = 6
    stages = audit.get("funnel_allocation", {}).get("stages", {})
    for i, (stage, data) in enumerate(stages.items()):
        within = "Yes" if data["within_range"] else "No"
        values = [
            stage, data["spend"], data["spend_pct"],
            data["recommended_min_pct"], data["recommended_max_pct"],
            within, data["campaign_count"], data["notes"],
        ]
        _write_data_row(ws, row, values, alt_shade=(i % 2 == 1))
        ws.cell(row=row, column=2).number_format = '$#,##0.00'
        ws.cell(row=row, column=3).number_format = '0.0"%"'
        fill = GREEN_FILL if data["within_range"] else YELLOW_FILL
        ws.cell(row=row, column=6).fill = fill
        row += 1

    # Total row
    total = audit.get("funnel_allocation", {}).get("total_spend", 0)
    row += 1
    ws.cell(row=row, column=1, value="TOTAL").font = BOLD_FONT
    ws.cell(row=row, column=2, value=total).font = BOLD_FONT
    ws.cell(row=row, column=2).number_format = '$#,##0.00'
    ws.cell(row=row, column=3, value=100).font = BOLD_FONT

    _auto_width(ws)


def _build_source_performance(wb, audit: dict):
    """Tab 5: Source Performance — per-platform breakdown."""
    ws = wb.create_sheet("Source Performance")
    ws.sheet_properties.tabColor = BRAND_BLUE

    _add_masthead(ws, "Performance by Source Platform", audit["audit_date"], ncols=10)

    headers = ["Source", "Spend", "Impressions", "Clicks", "CTR %",
               "Leads", "Form Fills", "Phone Calls", "VDP Views", "CPL"]
    _write_header_row(ws, 4, headers)
    ws.freeze_panes = "A5"

    row = 5
    for i, s in enumerate(audit.get("source_performance", [])):
        values = [
            s["source"], s["spend"], s["impressions"], s["clicks"],
            s["ctr_pct"], s["leads_total"], s["form_fills"],
            s["phone_calls"], s["vdp_views"], s["cpl"],
        ]
        _write_data_row(ws, row, values, alt_shade=(i % 2 == 1))
        ws.cell(row=row, column=2).number_format = '$#,##0.00'
        ws.cell(row=row, column=10).number_format = '$#,##0.00'
        row += 1

    _auto_width(ws)


def _build_vendor_roi(wb, audit: dict):
    """Tab 6: Vendor/Lead Provider ROI — CPL and performance by vendor."""
    ws = wb.create_sheet("Vendor ROI")
    ws.sheet_properties.tabColor = BRAND_BLUE

    _add_masthead(ws, "Vendor / Lead Provider ROI", audit["audit_date"], ncols=8)
    ws.merge_cells("A3:H3")
    ws.cell(row=3, column=1,
            value="Note: CPL comparisons between providers require nuance. "
                  "A higher-CPL source may produce better quality leads.").font = SMALL_FONT

    # Same data as source performance but framed differently
    headers = ["Vendor", "Spend", "Total Leads", "CPL", "Form Fills",
               "Phone Calls", "VDP Views", "Efficiency Notes"]
    _write_header_row(ws, 5, headers)
    ws.freeze_panes = "A6"

    row = 6
    bench = audit.get("executive_summary", {})
    bench_cpl = bench.get("benchmark_cpl_ceiling")

    for i, s in enumerate(audit.get("source_performance", [])):
        cpl = s.get("cpl")
        note = ""
        if cpl and bench_cpl:
            if cpl <= bench_cpl * 0.7:
                note = "Well below CPL ceiling"
            elif cpl <= bench_cpl:
                note = "Within benchmark range"
            else:
                note = "Above CPL ceiling — worth reviewing"

        values = [
            s["source"], s["spend"], s["leads_total"], cpl,
            s["form_fills"], s["phone_calls"], s["vdp_views"], note,
        ]
        _write_data_row(ws, row, values, alt_shade=(i % 2 == 1))
        ws.cell(row=row, column=2).number_format = '$#,##0.00'
        if cpl:
            ws.cell(row=row, column=4).number_format = '$#,##0.00'
        row += 1

    _auto_width(ws)


def _build_funnel_kpi_detail(wb, audit: dict):
    """Tab 7: Funnel KPI Detail — automotive-specific engagement metrics."""
    ws = wb.create_sheet("Funnel KPI Detail")
    ws.sheet_properties.tabColor = BRAND_BLUE

    _add_masthead(ws, "Funnel KPI Detail by Stage", audit["audit_date"], ncols=8)

    headers = ["Stage", "VDP Views", "SRP Views", "Form Fills", "Phone Calls",
               "Direction Clicks", "VDP-to-Lead %", "Primary KPIs"]
    _write_header_row(ws, 4, headers)
    ws.freeze_panes = "A5"

    row = 5
    stages = audit.get("funnel_allocation", {}).get("stages", {})
    from classify_funnel import STAGE_PRIMARY_KPIS

    for i, (stage, data) in enumerate(stages.items()):
        vdp = data.get("vdp_views", 0)
        leads = data.get("leads", 0)
        vdp_to_lead = (leads / vdp * 100) if vdp > 0 else 0
        primary_kpis = ", ".join(STAGE_PRIMARY_KPIS.get(stage, []))

        values = [
            stage, vdp, 0, leads, 0, 0,
            round(vdp_to_lead, 2), primary_kpis,
        ]
        _write_data_row(ws, row, values, alt_shade=(i % 2 == 1))
        row += 1

    _auto_width(ws)


def _build_suggestions(wb, audit: dict):
    """Tab 8: Suggestions for Discussion — tone-controlled output."""
    ws = wb.create_sheet("Suggestions")
    ws.sheet_properties.tabColor = SKY_BLUE

    _add_masthead(ws, "Suggestions for Discussion", audit["audit_date"], ncols=5)

    # Disclaimer header
    ws.merge_cells("A3:E4")
    c = ws.cell(row=3, column=1, value=audit.get("suggestion_disclaimer", ""))
    c.font = Font(name="Roboto Slab", size=10, italic=True, color="10162A")
    c.fill = LIGHT_BLUE_FILL
    c.alignment = Alignment(wrap_text=True, vertical="center")

    headers = ["Observation", "Worth Discussing", "Context Needed Before Deciding",
               "Potential Risk", "Priority"]
    _write_header_row(ws, 6, headers)
    ws.freeze_panes = "A7"

    row = 7
    for i, s in enumerate(audit.get("suggestions", [])):
        values = [
            s.get("observation", ""),
            s.get("worth_discussing", ""),
            s.get("context_needed", ""),
            s.get("potential_risk", ""),
            s.get("priority", ""),
        ]
        _write_data_row(ws, row, values, alt_shade=(i % 2 == 1))
        # Color-code priority
        priority = s.get("priority", "")
        ws.cell(row=row, column=5).fill = _severity_fill(priority)
        row += 1

    # Set wider columns for text-heavy tab
    for col in ["A", "B", "C", "D"]:
        ws.column_dimensions[col].width = 45
    ws.column_dimensions["E"].width = 12


def _build_delta(wb, audit: dict):
    """Tab 9: Delta vs. Prior Period (only if data present)."""
    delta = audit.get("delta")
    if not delta:
        return

    ws = wb.create_sheet("Delta vs. Prior")
    ws.sheet_properties.tabColor = TILE_BLUE

    _add_masthead(ws, "Month-over-Month Delta", audit["audit_date"], ncols=5)

    headers = ["Metric", "Current", "Prior", "Change", "% Change"]
    _write_header_row(ws, 4, headers)
    ws.freeze_panes = "A5"

    row = 5
    nice_names = {
        "total_spend": "Total Spend",
        "total_leads": "Total Leads",
        "cpl": "Cost Per Lead",
        "total_clicks": "Total Clicks",
        "total_impressions": "Total Impressions",
        "total_vdp_views": "Total VDP Views",
        "estimated_waste_usd": "Estimated Waste $",
        "estimated_waste_pct": "Estimated Waste %",
        "finding_count": "Findings Count",
    }

    for metric, data in delta.items():
        name = nice_names.get(metric, metric)
        pct = f"{data['pct_change']:+.1f}%" if data["pct_change"] is not None else "N/A"
        values = [name, data["current"], data["prior"], data["change"], pct]
        _write_data_row(ws, row, values, alt_shade=((row - 5) % 2 == 1))

        # Color-code change direction
        change = data.get("change", 0)
        # For waste and CPL, decrease is good (green), increase is bad (red)
        if metric in ("estimated_waste_usd", "estimated_waste_pct", "cpl", "finding_count"):
            if change < 0:
                ws.cell(row=row, column=4).fill = GREEN_FILL
            elif change > 0:
                ws.cell(row=row, column=4).fill = RED_FILL
        else:
            # For leads, clicks etc., increase is good
            if change > 0:
                ws.cell(row=row, column=4).fill = GREEN_FILL
            elif change < 0:
                ws.cell(row=row, column=4).fill = RED_FILL

        row += 1

    _auto_width(ws)


def _build_raw_data(wb, audit: dict, raw_rows: list[dict]):
    """Tab 10: Raw Data — cleaned source data for auditability."""
    ws = wb.create_sheet("Raw Data")
    ws.sheet_properties.tabColor = WARM_GREY

    # Get all unique keys across all rows (skip internal keys)
    all_keys = []
    seen = set()
    for r in raw_rows:
        for k in r.keys():
            if k not in seen and not k.startswith("_"):
                all_keys.append(k)
                seen.add(k)

    _add_masthead(ws, "Raw Ingested Data", audit["audit_date"], ncols=max(len(all_keys), 5))

    if not raw_rows:
        ws.cell(row=4, column=1, value="No raw data available.").font = BODY_FONT
        return

    _write_header_row(ws, 4, all_keys)
    ws.freeze_panes = "A5"

    max_rows = min(len(raw_rows), 5000)  # cap at 5000 rows
    for i in range(max_rows):
        values = [raw_rows[i].get(k, "") for k in all_keys]
        _write_data_row(ws, 5 + i, values, alt_shade=(i % 2 == 1))

    if len(raw_rows) > 5000:
        ws.cell(row=5005, column=1,
                value=f"... {len(raw_rows) - 5000} additional rows truncated").font = SMALL_FONT

    _auto_width(ws)


# -----------------------------------------------------------------------
# Main entry point
# -----------------------------------------------------------------------

def generate_report(
    audit: dict,
    raw_rows: list[dict],
    output_path: Optional[str] = None,
) -> str:
    """
    Generate the full branded Excel workbook.

    Args:
        audit: Complete audit result dict from audit_engine.run_audit()
        raw_rows: Normalized row data for the Raw Data tab
        output_path: Optional override for output file path

    Returns:
        Path to the generated Excel file
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not output_path:
        client_slug = audit["client"].lower().replace(" ", "_").replace("'", "")
        period = audit["period"]
        output_path = str(OUTPUT_DIR / f"{client_slug}_paid-media-audit_{period}.xlsx")

    wb = openpyxl.Workbook()

    print(f"[Report] Building workbook for {audit['client']}...")

    _build_cover(wb, audit)
    _build_executive_summary(wb, audit)
    _build_waste_audit(wb, audit)
    _build_funnel_allocation(wb, audit)
    _build_source_performance(wb, audit)
    _build_vendor_roi(wb, audit)
    _build_funnel_kpi_detail(wb, audit)
    _build_suggestions(wb, audit)
    _build_delta(wb, audit)
    _build_raw_data(wb, audit, raw_rows)

    wb.save(output_path)
    print(f"[Report] Saved: {output_path}")
    return output_path
