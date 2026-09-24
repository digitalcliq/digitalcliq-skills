#!/usr/bin/env python3
"""
generate_report.py — Stage 5: Generate branded DigitalCLIQ Excel compliance report.

Produces a 5-tab Excel workbook:
  1. Executive Summary — logo, scorecard, separate legal/brand severity counts, alert banner
  2. Legal Violations — CA advertising law findings (Tile Blue section treatment)
  3. Brand Violations — OEM brand guideline findings (Digital Blue section treatment)
  4. Evidence Log — full detail of every finding (combined)
  5. Delta Summary — NEW/PERSISTING/RESOLVED breakdown

Styling follows Resources/design-system/Design-System.md: palette tokens only
(Digital Blue / Sky Blue / Tile Blue / Warm Grey / navys / Callout Tint), Dosis for
structure, Roboto Slab for body. Severity/confidence/delta meaning is ALWAYS carried
by explicit text labels (CRITICAL/WARNING/ADVISORY etc.), never by color alone.
Every visible sheet carries the rows 1-2 Digital Blue masthead with the white
knockout logo, white Dosis 14 sheet title, and report date (§4 Excel spec).
"""

import json
import re
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, numbers
)
from openpyxl.utils import get_column_letter

# Try to import image support (requires Pillow)
try:
    from openpyxl.drawing.image import Image as XlImage
    HAS_IMAGE_SUPPORT = True
except ImportError:
    HAS_IMAGE_SUPPORT = False

# Logo path — canonical DigitalCLIQ brand asset location (vault-facts ledger).
# The skill package now lives OUTSIDE the vault (skills-plugin dir), so walking up
# parents no longer lands on the vault. Honor an explicit DIGITALCLIQ_VAULT_ROOT env
# var (vault-facts: "must be given the path explicitly"); fall back to the old
# four-parents derivation only when the env var is unset.
import os as _os
_env_root = _os.environ.get("DIGITALCLIQ_VAULT_ROOT")
_VAULT_ROOT = Path(_env_root).resolve() if _env_root else Path(__file__).resolve().parents[4]
LOGO_PATH = (
    _VAULT_ROOT / "Resources" / "brand-assets"
    / "digital-cliq-logo-solid-1000px-wide.png"
)

# DigitalCLIQ design-system tokens (Resources/design-system/Design-System.md)
CLIQ_NAVY = "10162A"      # Navy Base — dark text, tab accents
CLIQ_BLUE = "405FAB"      # Digital Blue — mastheads, primary fills
CLIQ_SKY = "6B9DD4"       # Sky Blue — accents, "strong/good" treatment
CLIQ_GREY = "949592"      # Warm Grey — muted labels, "weak" treatment
CLIQ_TILE = "2E4780"      # Tile Blue — deep accents, legal section emphasis
CLIQ_LIGHT = "EDF2F9"     # Callout Tint — light fills, alert banners
CLIQ_WHITE = "FFFFFF"
CLIQ_DARK = "070A15"      # Navy Deep
CLIQ_BORDER = "D8E1F0"    # Border blue-grey

# Severity colors — palette treatments only; the TEXT label (CRITICAL/WARNING/
# ADVISORY, written in the cell) always carries the meaning, never the color.
SEV_CRITICAL = CLIQ_TILE   # Tile Blue — deepest emphasis
SEV_WARNING = CLIQ_BLUE    # Digital Blue — emphasis
SEV_ADVISORY = CLIQ_GREY   # Warm Grey — weak/minor

# Legal section colors (Tile Blue distinguishes legal from Digital Blue brand)
LEGAL_ACCENT = CLIQ_TILE       # Deep accent for legal section headers
LEGAL_ACCENT_LIGHT = CLIQ_LIGHT  # Callout Tint for alert banner background

# Delta status colors — labels NEW/PERSISTING/RESOLVED carry the meaning
DELTA_NEW = CLIQ_BLUE        # Digital Blue — emphasis, needs attention
DELTA_PERSISTING = CLIQ_GREY # Warm Grey — lingering/weak
DELTA_RESOLVED = CLIQ_SKY    # Sky Blue — strong/good

# Styles — Dosis carries structure (headings, labels, stats), Roboto Slab carries reading
HEADER_FONT = Font(name="Dosis", size=11, bold=True, color=CLIQ_WHITE)
HEADER_FILL = PatternFill(start_color=CLIQ_BLUE, end_color=CLIQ_BLUE, fill_type="solid")
TITLE_FONT = Font(name="Dosis", size=16, bold=True, color=CLIQ_BLUE)
SUBTITLE_FONT = Font(name="Dosis", size=12, bold=False, color=CLIQ_SKY)
BODY_FONT = Font(name="Roboto Slab", size=10)
BOLD_FONT = Font(name="Roboto Slab", size=10, bold=True)
SMALL_FONT = Font(name="Roboto Slab", size=9, color=CLIQ_GREY)
LINK_FONT = Font(name="Roboto Slab", size=9, color=CLIQ_BLUE, underline="single")

THIN_BORDER = Border(
    left=Side(style="thin", color=CLIQ_BORDER),
    right=Side(style="thin", color=CLIQ_BORDER),
    top=Side(style="thin", color=CLIQ_BORDER),
    bottom=Side(style="thin", color=CLIQ_BORDER),
)

THICK_BORDER = Border(
    left=Side(style="medium", color=CLIQ_BORDER),
    right=Side(style="medium", color=CLIQ_BORDER),
    top=Side(style="medium", color=CLIQ_BORDER),
    bottom=Side(style="medium", color=CLIQ_BORDER),
)

WRAP_ALIGN = Alignment(wrap_text=True, vertical="top")
CENTER_ALIGN = Alignment(horizontal="center", vertical="center")

# Masthead (Design-System §4 Excel spec): rows 1-2 merged Digital Blue band on
# EVERY visible sheet — white knockout logo anchored A1 (~0.35in tall), sheet
# title in white Dosis 14 Bold, report date right side.
MASTHEAD_FILL = PatternFill(start_color=CLIQ_BLUE, end_color=CLIQ_BLUE, fill_type="solid")
MASTHEAD_TITLE_FONT = Font(name="Dosis", size=14, bold=True, color=CLIQ_WHITE)
MASTHEAD_DATE_FONT = Font(name="Dosis", size=10, bold=False, color=CLIQ_WHITE)

# Section header styles
LEGAL_SECTION_FONT = Font(name="Dosis", size=13, bold=True, color=CLIQ_WHITE)
LEGAL_SECTION_FILL = PatternFill(start_color=LEGAL_ACCENT, end_color=LEGAL_ACCENT, fill_type="solid")
BRAND_SECTION_FONT = Font(name="Dosis", size=13, bold=True, color=CLIQ_WHITE)
BRAND_SECTION_FILL = PatternFill(start_color=CLIQ_BLUE, end_color=CLIQ_BLUE, fill_type="solid")
ALERT_FONT = Font(name="Dosis", size=12, bold=True, color=LEGAL_ACCENT)
ALERT_FILL = PatternFill(start_color=LEGAL_ACCENT_LIGHT, end_color=LEGAL_ACCENT_LIGHT, fill_type="solid")


# ── GM-facing text helpers (2026-09-16 QA pass) ──
try:
    from openpyxl.cell.rich_text import CellRichText, TextBlock
    from openpyxl.cell.text import InlineFont
    HAS_RICH_TEXT = True
except ImportError:  # pragma: no cover
    HAS_RICH_TEXT = False

REVIEW_PREFIX_RE = re.compile(r"^\s*\**\s*NEEDS HUMAN REVIEW(?: AND VERIFICATION)?\s*\**\s*:\s*\**\s*", re.I)
REVIEW_LEGEND = "* after a confidence level = confirm by hand before acting"
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"]


LABEL_FONT = Font(name="Dosis", size=10, bold=True, color="10162A")


def _clean_statute(statute):
    """Citation only. Engine research notes (vacatur history, pin-cite provenance)
    ride after ' | ' in the data and stay out of the client workbook."""
    s = (statute or "").split(" | ")[0].strip()
    return s


def _human_dates(text):
    """One date style in client copy: 2026-10-01 and Oct 1, 2026 become October 1, 2026."""
    if not isinstance(text, str) or text.startswith("http"):
        return text
    text = re.sub(r"\b(20\d\d)-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b",
                  lambda m: f"{_MONTHS[int(m.group(2)) - 1]} {int(m.group(3))}, {m.group(1)}", text)
    text = re.sub(r"\bOct\.? (\d{1,2}), (20\d\d)\b", r"October \1, \2", text)
    return text


def _write_recommendation(cell, text, needs_review):
    """Only the review prefix is bold Digital Blue; the body reads as plain body text."""
    # Rich-text cells skip the save-time string scrub, so clean the copy here.
    text = _human_dates(re.sub("\\s*\u2014\\s*", ", ", text or ""))
    cell.font = BODY_FONT
    m = REVIEW_PREFIX_RE.match(text)
    if needs_review and m and HAS_RICH_TEXT:
        body = text[m.end():]
        cell.value = CellRichText(
            TextBlock(InlineFont(rFont="Roboto Slab", sz=10, b=True, color=CLIQ_BLUE), "NEEDS HUMAN REVIEW: "),
            TextBlock(InlineFont(rFont="Roboto Slab", sz=10, color=CLIQ_NAVY), body),
        )
    elif m:
        cell.value = "NEEDS HUMAN REVIEW: " + text[m.end():]
    else:
        cell.value = text


def _source_cell(cell, source):
    """Source is a category, not a severity: text-only, no severity-colored fill."""
    cell.value = "LEGAL" if source == "legal_check" else "BRAND" if source == "brand_check" else source
    cell.font = Font(name="Dosis", size=9, bold=True, color=CLIQ_NAVY)
    cell.alignment = Alignment(horizontal="center", vertical="top")
    cell.border = THIN_BORDER


def _finalize_print(ws, title_row=None, landscape=True):
    """Fit every column on one page width, repeat the header row, top-align data."""
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.sheet_view.showGridLines = False
    if title_row:
        # Repeat only the table header row when a summary block sits above it (2026-09-16 QA).
        ws.print_title_rows = f"{title_row}:{title_row}" if title_row > 6 else f"1:{title_row}"
        for row in ws.iter_rows(min_row=title_row + 1):
            for c in row:
                al = c.alignment
                c.alignment = Alignment(horizontal=al.horizontal, vertical="top", wrap_text=True)
        _fit_row_heights(ws, title_row + 1)


def _fit_row_heights(ws, first_row):
    """Explicit wrapped-row heights so Numbers/Sheets/previews match Excel; capped at
    Excel's 409pt row limit (2026-09-16 QA pass)."""
    import math
    merged = {c for rng in ws.merged_cells.ranges for row in ws.iter_rows(
        min_row=rng.min_row, max_row=rng.max_row, min_col=rng.min_col, max_col=rng.max_col) for c in
        [x.coordinate for x in row]}
    for r in range(first_row, ws.max_row + 1):
        lines = 1
        for c in ws[r]:
            if c.value in (None, "") or c.coordinate in merged:
                continue
            width = ws.column_dimensions[c.column_letter].width or 10
            size = (c.font.sz or 10) if c.font else 10
            chars_per_line = max(1.0, width * 0.95 * 10.0 / size)
            n = sum(max(1, math.ceil(len(part) / chars_per_line)) for part in str(c.value).split("\n"))
            lines = max(lines, n)
        ws.row_dimensions[r].height = min(409, max(18, 14.5 * lines + 4))


def _severity_fill(severity):
    """Return PatternFill for a severity level."""
    colors = {
        "critical": SEV_CRITICAL,
        "warning": SEV_WARNING,
        "advisory": SEV_ADVISORY,
    }
    c = colors.get(severity, CLIQ_GREY)
    return PatternFill(start_color=c, end_color=c, fill_type="solid")


def _severity_font(severity):
    """Return Font for severity badge."""
    return Font(name="Dosis", size=10, bold=True, color=CLIQ_WHITE)


def _delta_fill(status):
    """Return PatternFill for a delta status."""
    colors = {
        "new": DELTA_NEW,
        "persisting": DELTA_PERSISTING,
        "resolved": DELTA_RESOLVED,
        "removed": CLIQ_GREY,
    }
    c = colors.get(status, CLIQ_GREY)
    return PatternFill(start_color=c, end_color=c, fill_type="solid")


def _set_header_row(ws, row, headers, col_widths=None):
    """Apply header styling to a row."""
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=row, column=col_idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER

    if col_widths:
        for col_idx, width in enumerate(col_widths, 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = width


def _write_url_cell(ws, row, col, url):
    """Write a full URL as a clickable hyperlink (blue, underlined)."""
    cell = ws.cell(row=row, column=col)
    if url and url.startswith("http"):
        cell.hyperlink = url
        cell.value = url
        cell.font = LINK_FONT
    else:
        cell.value = url or ""
        cell.font = SMALL_FONT
    cell.alignment = WRAP_ALIGN
    cell.border = THIN_BORDER


def _compute_score(findings):
    """Compute overall compliance score (0-100).

    Scoring (capped deductions to prevent automatic F):
      - Start at 100
      - Each critical finding: -5 points (capped at -40 total)
      - Each warning finding:  -3 points (capped at -18 total)
      - Each advisory finding: -1 point  (capped at -7 total)
      - Floor at 35
    """
    criticals = sum(1 for f in findings if f.get("severity") == "critical")
    warnings = sum(1 for f in findings if f.get("severity") == "warning")
    advisories = sum(1 for f in findings if f.get("severity") == "advisory")

    crit_penalty = min(criticals * 5, 40)
    warn_penalty = min(warnings * 3, 18)
    adv_penalty = min(advisories * 1, 7)

    score = 100 - crit_penalty - warn_penalty - adv_penalty
    return max(35, score)


def _score_grade(score):
    """Convert numeric score to letter grade."""
    if score >= 90:
        return "A"
    elif score >= 75:
        return "B"
    elif score >= 60:
        return "C"
    elif score >= 45:
        return "D"
    else:
        return "F"


def _split_findings(findings):
    """Split findings into legal and brand lists."""
    legal = [f for f in findings if f.get("source") == "legal_check"]
    brand = [f for f in findings if f.get("source") == "brand_check"]
    return legal, brand


def _severity_counts(findings):
    """Return dict of severity counts for a list of findings."""
    return {
        "critical": sum(1 for f in findings if f.get("severity") == "critical"),
        "warning": sum(1 for f in findings if f.get("severity") == "warning"),
        "advisory": sum(1 for f in findings if f.get("severity") == "advisory"),
        "total": len(findings),
    }


def _add_masthead(ws, title, report_date, num_cols, title_start, date_start):
    """Rows 1-2 merged Digital Blue masthead per Design-System §4 Excel spec.

    Paints columns 1..num_cols of rows 1-2 Digital Blue, anchors the WHITE
    knockout logo at A1 (~0.35in tall, true aspect ratio), merges the sheet
    title (white Dosis 14 Bold) from title_start to date_start-1, and merges
    the report date (right-aligned white Dosis 10) from date_start to num_cols.
    title_start must sit clear of the ~110px logo footprint given the sheet's
    column widths. Raises if the logo cannot be embedded — a masthead without
    the logo image is a hard failure, never a fallback.
    """
    # Two 22pt rows ≈ 0.61in band
    ws.row_dimensions[1].height = 22
    ws.row_dimensions[2].height = 22

    ws.merge_cells(start_row=1, start_column=title_start, end_row=2, end_column=date_start - 1)
    title_cell = ws.cell(row=1, column=title_start, value=title)
    title_cell.font = MASTHEAD_TITLE_FONT
    title_cell.alignment = Alignment(horizontal="left", vertical="center")

    ws.merge_cells(start_row=1, start_column=date_start, end_row=2, end_column=num_cols)
    date_cell = ws.cell(row=1, column=date_start, value=report_date)
    date_cell.font = MASTHEAD_DATE_FONT
    date_cell.alignment = Alignment(horizontal="right", vertical="center")

    # Fill AFTER merging — merge_cells resets non-anchor cell styles, so filling
    # first would leave merged masthead cells unpainted.
    for r in (1, 2):
        for c in range(1, num_cols + 1):
            ws.cell(row=r, column=c).fill = MASTHEAD_FILL

    if not HAS_IMAGE_SUPPORT:
        raise RuntimeError(
            "openpyxl image support not available (Pillow missing). "
            "DigitalCLIQ branded reports require the logo to render."
        )
    if not LOGO_PATH.exists():
        raise RuntimeError(
            f"DigitalCLIQ logo not found at: {LOGO_PATH!s}\n"
            f"Canonical path: /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png"
        )
    img = XlImage(str(LOGO_PATH))
    # ~0.35in tall at 96dpi = 34px; preserve true aspect ratio (source 500x154)
    scale = 34 / img.height
    img.height = int(img.height * scale)
    img.width = int(img.width * scale)
    ws.add_image(img, "A1")


def _build_severity_table(ws, start_row, counts, section_type="legal"):
    """Build a severity count mini-table. Returns the next available row."""
    sev_data = [
        ("CRITICAL", counts["critical"], "Immediate Action Required" if section_type == "legal"
            else "Major Brand Infraction"),
        ("WARNING", counts["warning"], "Likely Violation — Needs Review" if section_type == "legal"
            else "Possible Non-Compliance"),
        ("ADVISORY", counts["advisory"], "Recommended Improvement" if section_type == "legal"
            else "Best Practice Suggestion"),
    ]

    for i, (sev_label, count, impact) in enumerate(sev_data):
        row = start_row + i
        sev_key = sev_label.lower()

        sev_cell = ws.cell(row=row, column=3, value=sev_label)
        sev_cell.font = _severity_font(sev_key)
        sev_cell.fill = _severity_fill(sev_key)
        sev_cell.alignment = CENTER_ALIGN
        sev_cell.border = THIN_BORDER

        count_cell = ws.cell(row=row, column=4, value=count)
        count_cell.font = Font(name="Dosis", size=12, bold=True,
                               color=LEGAL_ACCENT if (section_type == "legal" and sev_key == "critical" and count > 0) else CLIQ_NAVY)
        count_cell.alignment = CENTER_ALIGN
        count_cell.border = THIN_BORDER

        ws.cell(row=row, column=5, value=impact).font = BODY_FONT
        ws.cell(row=row, column=5).border = THIN_BORDER

    return start_row + 3


def _build_executive_summary(wb, findings, delta_results, client_name, brand, url, audit_date):
    """Tab 1: Executive Summary with logo, separate legal/brand scorecards, alert banner."""
    ws = wb.active
    ws.title = "Executive Summary"
    ws.sheet_properties.tabColor = CLIQ_NAVY

    # Column widths
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 19
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 14
    ws.column_dimensions["E"].width = 30
    ws.column_dimensions["F"].width = 20
    ws.column_dimensions["G"].width = 5

    # --- MASTHEAD (rows 1-2, Design-System §4) ---
    _add_masthead(
        ws, "DEALERSHIP COMPLIANCE AUDIT", audit_date,
        num_cols=7, title_start=3, date_start=6,
    )

    # --- TITLE BLOCK (below the masthead) ---
    ws.merge_cells("B4:F4")
    subtitle_cell = ws["B4"]
    _brand_in_name = (brand or "").lower() in (client_name or "").lower()
    subtitle_cell.value = f"{client_name} | {audit_date}" if _brand_in_name else f"{client_name} | {brand.upper()} | {audit_date}"
    subtitle_cell.font = SUBTITLE_FONT

    ws.merge_cells("B5:F5")
    url_cell = ws["B5"]
    url_cell.value = url
    url_cell.font = SMALL_FONT

    # --- OVERALL COMPLIANCE SCORE ---
    score = _compute_score(findings)
    grade = _score_grade(score)

    ws["B7"] = "OVERALL COMPLIANCE SCORE"
    ws["B7"].font = Font(name="Dosis", size=12, bold=True, color=CLIQ_NAVY)

    ws["B8"] = score
    ws["B8"].font = Font(name="Dosis", size=36, bold=True, color=CLIQ_SKY)
    ws["B8"].alignment = CENTER_ALIGN
    ws.row_dimensions[8].height = 45

    ws["C8"] = f"/ 100  ({grade})"
    ws["C8"].font = Font(name="Dosis", size=14, color=CLIQ_BLUE)
    ws["C8"].alignment = Alignment(vertical="center")

    # Total finding counts
    legal_findings, brand_findings = _split_findings(findings)
    legal_counts = _severity_counts(legal_findings)
    brand_counts = _severity_counts(brand_findings)

    ws["D8"] = f"Total Findings: {len(findings)}"
    ws["D8"].font = Font(name="Roboto Slab", size=11, color=CLIQ_GREY)
    ws["D8"].alignment = Alignment(vertical="center")

    # =====================================================
    # LEGAL COMPLIANCE SECTION (RED / ALARMING)
    # =====================================================
    row = 10

    # Section header — red banner
    ws.merge_cells(f"B{row}:E{row}")
    legal_header = ws[f"B{row}"]
    legal_header.value = "LEGAL COMPLIANCE — California Advertising Law"
    legal_header.font = BRAND_SECTION_FONT
    legal_header.fill = BRAND_SECTION_FILL
    legal_header.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[row].height = 28

    # Apply fill to all merged cells
    for col in range(2, 6):
        ws.cell(row=row, column=col).fill = BRAND_SECTION_FILL
        ws.cell(row=row, column=col).border = THIN_BORDER

    row += 1

    # Legal count summary line
    ws[f"B{row}"] = f"{legal_counts['total']} legal finding{'' if legal_counts['total'] == 1 else 's'}"
    ws[f"B{row}"].font = Font(name="Roboto Slab", size=10, bold=True, color=CLIQ_NAVY)
    row += 1

    # Severity table headers
    ws.cell(row=row, column=3, value="Severity").font = LABEL_FONT
    ws.cell(row=row, column=3).alignment = CENTER_ALIGN
    ws.cell(row=row, column=4, value="Count").font = LABEL_FONT
    ws.cell(row=row, column=4).alignment = CENTER_ALIGN
    ws.cell(row=row, column=5, value="Impact").font = LABEL_FONT
    row += 1

    # Severity rows for legal
    row = _build_severity_table(ws, row, legal_counts, section_type="legal")

    # ALERT BANNER — if legal criticals > 0
    if legal_counts["critical"] > 0:
        row += 1
        ws.merge_cells(f"B{row}:E{row}")
        alert_cell = ws[f"B{row}"]
        alert_cell.value = f"!! {legal_counts['critical']} LEGAL VIOLATION(S) REQUIRE IMMEDIATE ACTION !!"
        alert_cell.font = Font(name="Dosis", size=12, bold=True, color=LEGAL_ACCENT)
        alert_cell.fill = ALERT_FILL
        alert_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[row].height = 30
        for col in range(2, 6):
            ws.cell(row=row, column=col).fill = ALERT_FILL
            ws.cell(row=row, column=col).border = Border(
                left=Side(style="medium", color=LEGAL_ACCENT),
                right=Side(style="medium", color=LEGAL_ACCENT),
                top=Side(style="medium", color=LEGAL_ACCENT),
                bottom=Side(style="medium", color=LEGAL_ACCENT),
            )

    # =====================================================
    # BRAND COMPLIANCE SECTION (BLUE / CALMER)
    # =====================================================
    row += 2

    # Section header — blue banner
    ws.merge_cells(f"B{row}:E{row}")
    brand_header = ws[f"B{row}"]
    brand_header.value = "BRAND COMPLIANCE — OEM Guidelines"
    brand_header.font = BRAND_SECTION_FONT
    brand_header.fill = BRAND_SECTION_FILL
    brand_header.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[row].height = 28

    for col in range(2, 6):
        ws.cell(row=row, column=col).fill = BRAND_SECTION_FILL
        ws.cell(row=row, column=col).border = THIN_BORDER

    row += 1

    # Brand count summary line
    ws[f"B{row}"] = f"{brand_counts['total']} brand finding{'' if brand_counts['total'] == 1 else 's'}"
    ws[f"B{row}"].font = Font(name="Roboto Slab", size=10, bold=True, color=CLIQ_NAVY)
    row += 1

    # Severity table headers
    ws.cell(row=row, column=3, value="Severity").font = LABEL_FONT
    ws.cell(row=row, column=3).alignment = CENTER_ALIGN
    ws.cell(row=row, column=4, value="Count").font = LABEL_FONT
    ws.cell(row=row, column=4).alignment = CENTER_ALIGN
    ws.cell(row=row, column=5, value="Impact").font = LABEL_FONT
    row += 1

    # Severity rows for brand
    row = _build_severity_table(ws, row, brand_counts, section_type="brand")

    # =====================================================
    # MONTH-OVER-MONTH CHANGES
    # =====================================================
    row += 1

    prior_label = delta_results.get("prior_label")
    ws[f"B{row}"] = f"CHANGES SINCE THE {prior_label.upper()} AUDIT" if prior_label else "CHANGES SINCE THE LAST AUDIT"
    ws[f"B{row}"].font = Font(name="Dosis", size=11, bold=True, color=CLIQ_NAVY)
    row += 1

    counts = delta_results["counts"]
    is_first = delta_results.get("is_first_audit", False)

    if is_first:
        ws[f"B{row}"] = "First audit — no prior month comparison available"
        ws[f"B{row}"].font = SMALL_FONT
        row += 1
    else:
        delta_data = [
            ("NEW Issues", counts["new"], DELTA_NEW),
            ("PERSISTING Issues", counts["persisting"], DELTA_PERSISTING),
            ("RESOLVED Issues", counts["resolved"], DELTA_RESOLVED),
        ]
        if counts.get("removed"):
            delta_data.append(("REMOVED (false positive)", counts["removed"], CLIQ_GREY))

        for label, count, color in delta_data:
            ws.cell(row=row, column=2, value=label).font = BOLD_FONT
            ws.cell(row=row, column=2).border = THIN_BORDER
            ws.cell(row=row, column=2).alignment = Alignment(wrap_text=True, vertical="center")

            count_cell = ws.cell(row=row, column=3, value=count)
            count_cell.font = Font(name="Dosis", size=10, bold=True, color=CLIQ_WHITE)
            count_cell.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
            count_cell.alignment = CENTER_ALIGN
            count_cell.border = THIN_BORDER
            row += 1

    # =====================================================
    # FOOTER
    # =====================================================
    row += 2
    ws[f"B{row}"] = "Prepared by DigitalCLIQ"
    ws[f"B{row}"].font = Font(name="Dosis", size=10, bold=True, italic=True, color=CLIQ_BLUE)
    row += 1
    ws[f"B{row}"] = ("Legal rules: California Vehicle Code, B&P Code §17500 et seq., CARS Act (SB 766), "
                      "CCPA/CPRA, CNCDA Compliance Guide v1.2, FTC Pricing Transparency FAQs, Regulations M and Z")
    ws[f"B{row}"].font = Font(name="Roboto Slab", size=8, italic=True, color=CLIQ_GREY)
    ws.merge_cells(f"B{row}:F{row}")
    ws[f"B{row}"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[row].height = 24
    row += 1
    ws[f"B{row}"] = "This audit is informational only and does not constitute legal advice."
    ws[f"B{row}"].font = Font(name="Roboto Slab", size=8, italic=True, color=CLIQ_GREY)
    _finalize_print(ws, title_row=None, landscape=False)


def _build_findings_tab(wb, all_findings, tab_name, tab_color, source_filter, section_label,
                        audit_date):
    """Build a findings tab filtered by source (legal_check or brand_check)."""
    ws = wb.create_sheet(tab_name)
    ws.sheet_properties.tabColor = tab_color

    findings = [f for f in all_findings if f.get("source") == source_filter]
    is_legal = (source_filter == "legal_check")

    # Masthead rows 1-2 (Design-System §4) — carries the section label as sheet title
    _add_masthead(
        ws, section_label, audit_date,
        num_cols=8, title_start=4, date_start=8,
    )

    # Summary counts row
    counts = _severity_counts(findings)
    count_parts = []
    if counts["critical"] > 0:
        count_parts.append(f"{counts['critical']} Critical")
    if counts["warning"] > 0:
        count_parts.append(f"{counts['warning']} Warning")
    if counts["advisory"] > 0:
        count_parts.append(f"{counts['advisory']} Advisory")

    ws.merge_cells("A3:H3")
    ws["A3"] = (f"{counts['total']} finding{'' if counts['total'] == 1 else 's'}: {', '.join(count_parts)}."
                f"      {REVIEW_LEGEND}")
    ws["A3"].font = Font(name="Roboto Slab", size=10, bold=True,
                         color=LEGAL_ACCENT if (is_legal and counts["critical"] > 0) else CLIQ_NAVY)

    # Alert banner for legal tab with criticals
    data_start_row = 5
    if is_legal and counts["critical"] > 0:
        ws.merge_cells("A4:H4")
        ws["A4"] = f"!! {counts['critical']} LEGAL VIOLATION(S) REQUIRE IMMEDIATE ACTION !!"
        ws["A4"].font = Font(name="Dosis", size=11, bold=True, color=LEGAL_ACCENT)
        ws["A4"].fill = ALERT_FILL
        ws["A4"].alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[4].height = 28
        for col in range(1, 9):
            ws.cell(row=4, column=col).fill = ALERT_FILL
        data_start_row = 6

    # Table headers
    headers = ["#", "Severity", "Confidence", "Rule ID", "Statute", "Title", "Page", "Recommendation"]
    col_widths = [5, 12, 12, 16, 18, 35, 50, 45]
    _set_header_row(ws, data_start_row, headers, col_widths)

    # Sort: critical first, then warning, then advisory
    sev_order = {"critical": 0, "warning": 1, "advisory": 2}
    sorted_findings = sorted(findings, key=lambda f: sev_order.get(f.get("severity", ""), 9))

    for i, finding in enumerate(sorted_findings):
        row = data_start_row + 1 + i
        sev = finding.get("severity", "")
        confidence = finding.get("confidence", "high")
        needs_review = finding.get("needs_human_review", False)

        ws.cell(row=row, column=1, value=i + 1).font = BODY_FONT
        ws.cell(row=row, column=1).alignment = CENTER_ALIGN
        ws.cell(row=row, column=1).border = THIN_BORDER

        sev_cell = ws.cell(row=row, column=2, value=sev.upper())
        sev_cell.font = _severity_font(sev)
        sev_cell.fill = _severity_fill(sev)
        sev_cell.alignment = CENTER_ALIGN
        sev_cell.border = THIN_BORDER

        # Confidence column
        conf_label = confidence.upper()
        if needs_review:
            conf_label += " *"
        conf_cell = ws.cell(row=row, column=3, value=conf_label)
        conf_cell.alignment = CENTER_ALIGN
        conf_cell.border = THIN_BORDER
        # Palette-only confidence coding; the HIGH/MEDIUM/LOW text label carries the meaning
        if confidence == "high":
            conf_cell.font = Font(name="Roboto Slab", size=9, bold=True, color=CLIQ_SKY)
        elif confidence == "medium":
            conf_cell.font = Font(name="Roboto Slab", size=9, bold=True, color=CLIQ_BLUE)
        else:
            conf_cell.font = Font(name="Roboto Slab", size=9, bold=True, color=CLIQ_GREY)

        ws.cell(row=row, column=4, value=finding.get("rule_id", "")).font = BODY_FONT
        ws.cell(row=row, column=4).border = THIN_BORDER
        ws.cell(row=row, column=4).alignment = WRAP_ALIGN

        statute = _clean_statute(finding.get("statute", ""))
        ws.cell(row=row, column=5, value=statute).font = SMALL_FONT
        ws.cell(row=row, column=5).border = THIN_BORDER
        ws.cell(row=row, column=5).alignment = WRAP_ALIGN

        ws.cell(row=row, column=6, value=finding.get("title", "")).font = BODY_FONT
        ws.cell(row=row, column=6).alignment = WRAP_ALIGN
        ws.cell(row=row, column=6).border = THIN_BORDER

        _write_url_cell(ws, row, 7, finding.get("page_url", ""))

        rec_cell = ws.cell(row=row, column=8)
        rec_cell.alignment = WRAP_ALIGN
        rec_cell.border = THIN_BORDER
        _write_recommendation(rec_cell, finding.get("recommendation", ""), needs_review)

    # Freeze header row
    ws.freeze_panes = f"A{data_start_row + 1}"
    _finalize_print(ws, title_row=data_start_row)

    # Auto-filter
    if len(sorted_findings) > 0:
        ws.auto_filter.ref = f"A{data_start_row}:H{data_start_row + len(sorted_findings)}"


def _build_evidence_log(wb, findings, audit_date):
    """Tab 4: Evidence Log — full detail of every finding, grouped by source."""
    ws = wb.create_sheet("Evidence Log")
    ws.sheet_properties.tabColor = CLIQ_BLUE

    # Masthead rows 1-2 (Design-System §4); row 3 spacer, headers row 4
    _add_masthead(
        ws, "EVIDENCE LOG — All Findings", audit_date,
        num_cols=10, title_start=4, date_start=10,
    )
    header_row = 4
    ws["A3"] = REVIEW_LEGEND
    ws["A3"].font = SMALL_FONT

    headers = ["#", "Source", "Severity", "Confidence", "Rule ID", "Statute", "Title",
               "Page URL", "Quote / Evidence", "Recommendation"]
    col_widths = [5, 10, 12, 12, 16, 18, 30, 50, 40, 40]
    _set_header_row(ws, header_row, headers, col_widths)

    # Sort: legal first, then brand; within each group sort by severity
    sev_order = {"critical": 0, "warning": 1, "advisory": 2}
    source_order = {"legal_check": 0, "brand_check": 1}
    sorted_findings = sorted(findings, key=lambda f: (
        source_order.get(f.get("source", ""), 9),
        sev_order.get(f.get("severity", ""), 9),
    ))

    for i, finding in enumerate(sorted_findings):
        row = header_row + 1 + i
        sev = finding.get("severity", "")
        source = finding.get("source", "")
        confidence = finding.get("confidence", "high")
        needs_review = finding.get("needs_human_review", False)

        ws.cell(row=row, column=1, value=i + 1).font = BODY_FONT
        ws.cell(row=row, column=1).alignment = CENTER_ALIGN
        ws.cell(row=row, column=1).border = THIN_BORDER

        _source_cell(ws.cell(row=row, column=2), source)

        sev_cell = ws.cell(row=row, column=3, value=sev.upper())
        sev_cell.font = _severity_font(sev)
        sev_cell.fill = _severity_fill(sev)
        sev_cell.alignment = CENTER_ALIGN
        sev_cell.border = THIN_BORDER

        # Confidence column
        conf_label = confidence.upper()
        if needs_review:
            conf_label += " *"
        conf_cell = ws.cell(row=row, column=4, value=conf_label)
        conf_cell.alignment = CENTER_ALIGN
        conf_cell.border = THIN_BORDER
        # Palette-only confidence coding; the HIGH/MEDIUM/LOW text label carries the meaning
        if confidence == "high":
            conf_cell.font = Font(name="Roboto Slab", size=9, bold=True, color=CLIQ_SKY)
        elif confidence == "medium":
            conf_cell.font = Font(name="Roboto Slab", size=9, bold=True, color=CLIQ_BLUE)
        else:
            conf_cell.font = Font(name="Roboto Slab", size=9, bold=True, color=CLIQ_GREY)

        ws.cell(row=row, column=5, value=finding.get("rule_id", "")).font = BODY_FONT
        ws.cell(row=row, column=5).border = THIN_BORDER

        ws.cell(row=row, column=6, value=_clean_statute(finding.get("statute", ""))).font = SMALL_FONT
        ws.cell(row=row, column=6).border = THIN_BORDER

        ws.cell(row=row, column=7, value=finding.get("title", "")).font = BODY_FONT
        ws.cell(row=row, column=7).alignment = WRAP_ALIGN
        ws.cell(row=row, column=7).border = THIN_BORDER

        _write_url_cell(ws, row, 8, finding.get("page_url", ""))

        ws.cell(row=row, column=9, value=finding.get("quote", "")).font = BODY_FONT
        ws.cell(row=row, column=9).alignment = WRAP_ALIGN
        ws.cell(row=row, column=9).border = THIN_BORDER

        rec_cell = ws.cell(row=row, column=10)
        rec_cell.alignment = WRAP_ALIGN
        rec_cell.border = THIN_BORDER
        _write_recommendation(rec_cell, finding.get("recommendation", ""), needs_review)

    ws.freeze_panes = f"A{header_row + 1}"
    _finalize_print(ws, title_row=header_row)
    if len(findings) > 0:
        ws.auto_filter.ref = f"A{header_row}:J{header_row + len(findings)}"


def _build_delta_summary(wb, delta_results, audit_date):
    """Tab 5: Delta Summary — NEW/PERSISTING/RESOLVED breakdown."""
    ws = wb.create_sheet("Delta Summary")
    ws.sheet_properties.tabColor = DELTA_RESOLVED

    is_first = delta_results.get("is_first_audit", False)
    counts = delta_results["counts"]
    tagged = delta_results.get("tagged_findings", [])
    resolved = delta_results.get("resolved", [])

    # Masthead rows 1-2 (Design-System §4) — carries the sheet title
    prior_label = delta_results.get("prior_label")
    _add_masthead(
        ws, (f"CHANGES SINCE {prior_label.upper()}" if prior_label else "CHANGES SINCE LAST AUDIT"), audit_date,
        num_cols=6, title_start=3, date_start=6,
    )

    if is_first:
        ws["A4"] = "This is the first audit for this client. All findings are classified as NEW."
        ws["A4"].font = BODY_FONT
        ws["A6"] = f"Total NEW findings: {counts['new']}"
        ws["A6"].font = BOLD_FONT
    else:
        # Summary counts
        ws["A4"] = "Status"
        ws["A4"].font = LABEL_FONT
        ws["B4"] = "Count"
        ws["B4"].font = LABEL_FONT

        delta_rows = [
            ("NEW", counts["new"], DELTA_NEW),
            ("PERSISTING", counts["persisting"], DELTA_PERSISTING),
            ("RESOLVED", counts["resolved"], DELTA_RESOLVED),
        ]
        if counts.get("removed"):
            delta_rows.append(("REMOVED", counts["removed"], CLIQ_GREY))

        for i, (label, count, color) in enumerate(delta_rows):
            row = 5 + i
            status_cell = ws.cell(row=row, column=1, value=label)
            status_cell.font = Font(name="Dosis", size=10, bold=True, color=CLIQ_WHITE)
            status_cell.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
            status_cell.alignment = CENTER_ALIGN
            status_cell.border = THIN_BORDER

            ws.cell(row=row, column=2, value=count).font = BOLD_FONT
            ws.cell(row=row, column=2).alignment = CENTER_ALIGN
            ws.cell(row=row, column=2).border = THIN_BORDER

    # Detailed delta table
    start_row = 10 if not is_first else 9
    headers = ["Delta Status", "Source", "Severity", "Rule ID", "Title", "Page URL"]
    col_widths = [15, 10, 12, 16, 35, 50]
    _set_header_row(ws, start_row, headers, col_widths)

    # Combine all items: tagged findings + resolved
    all_items = list(tagged) + list(resolved)

    # Sort: new first, then persisting, then resolved; within each group legal before brand
    delta_order = {"new": 0, "persisting": 1, "resolved": 2, "removed": 3}
    source_order = {"legal_check": 0, "brand_check": 1}
    all_items.sort(key=lambda f: (
        delta_order.get(f.get("delta_status", ""), 9),
        source_order.get(f.get("source", ""), 9),
    ))

    for i, item in enumerate(all_items):
        row = start_row + 1 + i
        status = item.get("delta_status", "")
        sev = item.get("severity", "")
        source = item.get("source", "")

        status_cell = ws.cell(row=row, column=1, value=status.upper())
        status_cell.font = Font(name="Dosis", size=10, bold=True, color=CLIQ_WHITE)
        status_cell.fill = _delta_fill(status)
        status_cell.alignment = CENTER_ALIGN
        status_cell.border = THIN_BORDER

        _source_cell(ws.cell(row=row, column=2), source)

        sev_cell = ws.cell(row=row, column=3)
        if status == "removed":
            sev_cell.value = "N/A"
            sev_cell.font = Font(name="Dosis", size=10, bold=True, color=CLIQ_GREY)
        else:
            sev_cell.value = sev.upper()
            sev_cell.font = _severity_font(sev)
            sev_cell.fill = _severity_fill(sev)
        sev_cell.alignment = CENTER_ALIGN
        sev_cell.border = THIN_BORDER

        ws.cell(row=row, column=4, value=item.get("rule_id", "")).font = BODY_FONT
        ws.cell(row=row, column=4).border = THIN_BORDER
        ws.row_dimensions[row].height = None

        ws.cell(row=row, column=5, value=(item.get("title", "") or "").replace("title ''", "title (blank)")).font = BODY_FONT
        ws.cell(row=row, column=5).alignment = WRAP_ALIGN
        ws.cell(row=row, column=5).border = THIN_BORDER

        _page = item.get("page_url", "") or ""
        _write_url_cell(ws, row, 6, _page if _page.startswith("http") else "Page not recorded in the prior audit")

    ws.freeze_panes = f"A{start_row + 1}"
    _finalize_print(ws, title_row=start_row)
    total_items = len(all_items)
    if total_items > 0:
        ws.auto_filter.ref = f"A{start_row}:F{start_row + total_items}"


def _build_verification_tab(wb, verification_report, audit_date, total_findings=None):
    """Re-Verification tab: how the automated results were double-checked, in plain
    English. Page keys and engine check ids are translated through the optional
    page_label / label fields the auditor adds to verification_report.json."""
    ws = wb.create_sheet("Re-Verification")
    ws.sheet_properties.tabColor = DELTA_RESOLVED
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 44
    ws.column_dimensions["C"].width = 48
    ws.column_dimensions["D"].width = 14
    _add_masthead(
        ws, "RE-VERIFICATION", audit_date,
        num_cols=4, title_start=2, date_start=4,
    )
    vr = verification_report or {}
    summary = vr.get("summary", {}) or {}
    ws["A3"] = "How the automated results were double-checked"
    ws["A3"].font = Font(name="Dosis", size=12, bold=True, color=CLIQ_NAVY)
    ws.merge_cells("A4:D4")
    ws["A4"] = ("Any automated check that could not see a full page was re-checked against a "
                "second copy of that page before anything was reported. Items that still could "
                "not be confirmed are listed at the bottom for a person to verify; they are not "
                "counted as violations.")
    ws["A4"].font = SMALL_FONT
    ws["A4"].alignment = WRAP_ALIGN
    ws.row_dimensions[4].height = 42

    failed = summary.get("failed", 0)
    failed_label = "Automated rule failures"
    if total_findings is not None and total_findings > failed:
        failed_label += f" (the other {total_findings - failed} findings came from analyst review)"
    rows = [
        ("Automated checks run", summary.get("checks_total", 0)),
        ("Passed", summary.get("passed", 0)),
        (failed_label, failed),
        ("Could not be confirmed (listed below)", summary.get("still_unresolved", 0)),
        ("Checks re-run after a second page read", summary.get("reverified", 0)),
        ("Flags withdrawn after the second read", summary.get("false_positives_averted", 0)),
        ("Violations confirmed by the second read", summary.get("violations_confirmed_after_recrawl", 0)),
    ]
    r = 6
    for label, val in rows:
        c = ws.cell(row=r, column=1, value=label)
        c.font = BOLD_FONT
        c.alignment = WRAP_ALIGN
        v = ws.cell(row=r, column=2, value=val)
        v.font = BODY_FONT
        v.alignment = Alignment(horizontal="left", vertical="top")
        r += 1

    outcome_text = {
        "corrected": "Second read captured the full page",
        "no_improvement": "Second read returned no additional text",
    }
    recrawls = vr.get("recrawls", []) or []
    if recrawls:
        r += 1
        for i, h in enumerate(["Page read a second time", "Address", "Result"]):
            c = ws.cell(row=r, column=1 + i, value=h)
            c.font = HEADER_FONT
            c.fill = HEADER_FILL
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        r += 1
        for rc in recrawls:
            ws.cell(row=r, column=1, value=rc.get("page_label") or rc.get("page", "")).font = BODY_FONT
            ws.cell(row=r, column=2, value=rc.get("url", "")).font = SMALL_FONT
            ws.cell(row=r, column=3, value=rc.get("result_plain") or outcome_text.get(rc.get("outcome"), rc.get("outcome", ""))).font = BODY_FONT
            for col in range(1, 4):
                ws.cell(row=r, column=col).alignment = WRAP_ALIGN
            r += 1

    still = vr.get("still_unresolved", []) or []
    if still:
        r += 1
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
        ws.cell(row=r, column=1, value="COULD NOT BE CONFIRMED: needs a person to check, NOT counted as violations").font = ALERT_FONT
        r += 1
        for i, h in enumerate(["What was checked", "Page", "Why it needs a person", ""]):
            c = ws.cell(row=r, column=1 + i, value=h or None)
            c.font = HEADER_FONT
            c.fill = HEADER_FILL
        r += 1
        for su in still:
            ws.cell(row=r, column=1, value=su.get("label") or su.get("check_id", "")).font = BOLD_FONT
            ws.cell(row=r, column=2, value=su.get("page_label") or su.get("page", "")).font = BODY_FONT
            ws.cell(row=r, column=3, value=str(su.get("reason_plain") or su.get("reason", ""))).font = SMALL_FONT
            for col in range(1, 4):
                ws.cell(row=r, column=col).alignment = WRAP_ALIGN
            r += 1

    _finalize_print(ws, title_row=None)
    _fit_row_heights(ws, 6)
    return ws


def build_report(findings, delta_results, client_name, brand, url, output_path,
                 audit_date, verification_report=None):
    """Build the branded compliance audit Excel report.

    Args:
        findings: List of finding dicts (from Stages 1-3)
        delta_results: Dict from delta_engine.compute_delta()
        client_name: Client display name
        brand: Brand name (e.g., "BMW")
        url: Dealership URL
        output_path: Full path for output .xlsx file
        audit_date: Human-readable audit date string
        verification_report: Optional dict from verify_loop.py — adds a
            Re-Verification tab proving false positives were averted.
    """
    wb = Workbook()

    # Every visible sheet carries the rows 1-2 Digital Blue masthead + white
    # logo + white Dosis 14 title + report date (Design-System §4 Excel spec).

    # Tab 1: Executive Summary (masthead + separate legal/brand sections)
    _build_executive_summary(wb, findings, delta_results, client_name, brand, url, audit_date)

    # Tab 2: Legal Violations (Tile Blue treatment)
    _build_findings_tab(
        wb, findings,
        tab_name="Legal Violations",
        tab_color=LEGAL_ACCENT,
        source_filter="legal_check",
        section_label="LEGAL FINDINGS: California Advertising Law",
        audit_date=audit_date,
    )

    # Tab 3: Brand Violations (Digital Blue treatment)
    _build_findings_tab(
        wb, findings,
        tab_name="Brand Violations",
        tab_color=CLIQ_BLUE,
        source_filter="brand_check",
        section_label="BRAND FINDINGS: OEM Guidelines",
        audit_date=audit_date,
    )

    # Tab 4: Evidence Log (all findings combined)
    _build_evidence_log(wb, findings, audit_date)

    # Tab 5: Delta Summary
    _build_delta_summary(wb, delta_results, audit_date)

    # Tab 6: Re-Verification (proof of rigor) — only when a report is provided
    if verification_report:
        _build_verification_tab(wb, verification_report, audit_date, total_findings=len(findings))

    # Save
    # Rule 14 (vault): never ship em dashes. Scrub every string cell at save time so
    # labels, registry titles, and agent-written copy all comply in one place.
    for _ws in wb.worksheets:
        for _row in _ws.iter_rows():
            for _c in _row:
                if isinstance(_c.value, str) and "\u2014" in _c.value:
                    _v = re.sub(r"\s*\u2014\s*", ": ", _c.value, count=1) if re.match(r"^[^\u2014]{1,60}\s\u2014\s", _c.value) else _c.value
                    _c.value = re.sub(r"\s*\u2014\s*", ", ", _v)
                if isinstance(_c.value, str):
                    _c.value = _human_dates(_c.value)
    wb.save(output_path)
    return output_path


if __name__ == "__main__":
    # Quick test with sample data
    sample_findings = [
        {
            "page_url": "https://www.sterlingbmw.com/specials",
            "finding_type": "legal_violation",
            "rule_id": "CA-REGZ-001",
            "title": "Missing Reg Z full disclosure on finance offer",
            "quote": "$499/mo shown without APR, term, or down payment disclosure",
            "severity": "critical",
            "source": "legal_check",
            "statute": "12 CFR §226.24",
            "recommendation": "Add all 5 Reg Z required terms",
        },
        {
            "page_url": "https://www.sterlingbmw.com",
            "finding_type": "brand_violation",
            "rule_id": "BMW-COLOR-001",
            "title": "Non-standard color palette in BMW section",
            "quote": "Hero banner uses #FF6600 orange instead of BMW brand blue",
            "severity": "advisory",
            "source": "brand_check",
            "statute": "",
            "recommendation": "Update hero banner colors to BMW-approved palette",
        },
    ]

    from delta_engine import compute_delta
    delta = compute_delta(sample_findings)

    output = build_report(
        findings=sample_findings,
        delta_results=delta,
        client_name="Sterling BMW",
        brand="BMW",
        url="https://www.sterlingbmw.com",
        output_path="/tmp/test_compliance_report.xlsx",
        audit_date="March 5, 2026",
    )
    print(f"Test report generated: {output}")
