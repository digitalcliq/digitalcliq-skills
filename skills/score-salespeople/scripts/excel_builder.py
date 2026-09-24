"""DigitalCLIQ-branded Excel output for salesperson scorecards.

Renders the result dict produced by scoring_engine.score_all() (per-lead) or
scoring_engine.score_aggregated() (aggregated). Picks the appropriate scorecard
and factor-detail layouts based on results["pipeline"].

Tabs:
  1. Summary                     (styled first tab: key stats, how-to-read)
  2. Methodology
  3. Salesperson Scorecard
  4. Factor Detail
  5. Coaching Flags
  6. BDC / Non-Sales Roles       (aggregated path only)
  7. Other Bucket (Unattributed) (aggregated path, if present)
  8. Not Scored
  9. Raw Data

Design-System §4: every visible sheet carries the rows 1-2 Digital Blue
masthead (white knockout logo anchored A1, sheet title in white Dosis 14
Bold, report date right side). Data content starts below the masthead:
header rows at HEADER_ROW, body at DATA_START_ROW.
"""
from __future__ import annotations

import os
from pathlib import Path

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


# DigitalCLIQ design-system tokens (Resources/design-system/Design-System.md)
PRIMARY_BLUE = "405FAB"   # Digital Blue
SKY_BLUE = "6B9DD4"       # Sky Blue accent
LIGHT_BLUE = "EDF2F9"     # Callout Tint
ALT_ROW = "EDF2F9"        # Callout Tint alternating rows
RICH_BLACK = "000000"     # Rich Black body text
WARM_GREY = "949592"      # Warm Grey muted / weak
BORDER_BLUE = "D8E1F0"    # Card/table borders
# Tier fills are palette treatments only; the A/B/C/D letter in the cell is
# the explicit text label that carries the meaning.
TIER_FILL = {
    "A": PRIMARY_BLUE,   # Digital Blue — emphasis / top tier
    "B": SKY_BLUE,       # Sky Blue — strong
    "C": LIGHT_BLUE,     # Callout Tint — soft / needs work
    "D": WARM_GREY,      # Warm Grey — weak
}
TIER_TEXT = {
    "A": "FFFFFF",
    "B": "FFFFFF",
    "C": RICH_BLACK,
    "D": "FFFFFF",
}
# Severity text in the adjacent cell carries the meaning; fills are palette tints.
SEVERITY_FILL = {
    "high": WARM_GREY,
    "medium": BORDER_BLUE,
    "low": LIGHT_BLUE,
}

# Canonical WHITE knockout logo — used on the Digital Blue masthead only.
_LOGO_PATH = Path(
    "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/"
    "digital-cliq-logo-solid-1000px-wide.png"
)
_LOGO_SRC_W, _LOGO_SRC_H = 500, 154  # source PNG pixel dimensions

# Design-System §4 layout: rows 1-2 masthead on every visible sheet,
# header row directly below it, data below that.
MASTHEAD_ROWS = 2
HEADER_ROW = MASTHEAD_ROWS + 1   # 3
DATA_START_ROW = HEADER_ROW + 1  # 4


# ── Style helpers ─────────────────────────────────────────────────────

# Dosis carries structure (headers, titles, labels); Roboto Slab carries reading (body).
def _header_font():    return Font(name="Dosis", size=10, bold=True, color="FFFFFF")
def _body_font(b=False): return Font(name="Roboto Slab", size=10, bold=b, color=RICH_BLACK)
def _muted_font():     return Font(name="Roboto Slab", size=9, italic=True, color=WARM_GREY)
def _title_font():     return Font(name="Dosis", size=18, bold=True, color=RICH_BLACK)
def _section_font():   return Font(name="Dosis", size=12, bold=True, color=PRIMARY_BLUE)
def _header_fill():    return PatternFill("solid", fgColor=PRIMARY_BLUE)
def _alt_fill():       return PatternFill("solid", fgColor=ALT_ROW)


def _border():
    s = Side(style="thin", color=BORDER_BLUE)
    return Border(left=s, right=s, top=s, bottom=s)


def _fmt_pct(v, none_str="—"):
    if v is None: return none_str
    return f"{v * 100:.1f}%"


def _fmt_pct_or_dash(v, denom):
    if not denom: return "—"
    return f"{v * 100:.1f}%"


def _fmt_seconds(s):
    if s is None: return "—"
    if s < 60:    return f"{s:.0f}s"
    if s < 3600:  return f"{s/60:.1f}m"
    return f"{s/3600:.1f}h"


# ── Masthead (Design-System §4: every visible sheet) ─────────────────

def _col_px(width) -> int:
    """Approximate rendered pixel width of a column from its char width."""
    if not width:
        return 64  # Excel default (~8.43 chars)
    return int(width * 7 + 5)


def _add_masthead(ws, title: str, period_label: str, col_widths: list[float]):
    """Rows 1-2 Digital Blue masthead: WHITE knockout logo anchored A1
    (~0.35in tall, true aspect), sheet title white Dosis 14 Bold, report
    date right side. Extends past narrow data ranges so the band always
    has room for logo + title + date."""
    if not _LOGO_PATH.exists():
        raise FileNotFoundError(
            f"DigitalCLIQ logo not found at the canonical path: {_LOGO_PATH!s}\n"
            "Restore Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png. "
            "Never ship without the logo."
        )

    px = [_col_px(w) for w in col_widths]

    # First column whose left edge clears the logo (+ small gutter).
    title_start, left = None, 0
    for i, w in enumerate(px, start=1):
        if left >= 130:
            title_start = i
            break
        left += w
    while title_start is None:
        px.append(64)
        if left >= 130:
            title_start = len(px)
        else:
            left += px[-1]

    # Extend the band with default-width columns until the rightmost run
    # gives ~240px for the date AND the title region keeps ~300px.
    while True:
        ncols = len(px)
        acc, date_start = 0, None
        for i in range(ncols, title_start, -1):
            acc += px[i - 1]
            date_start = i
            if acc >= 240:
                break
        if date_start is not None and acc >= 240:
            title_w = sum(px[title_start - 1:date_start - 1])
            if title_w >= 300:
                break
        px.append(64)
    ncols = len(px)

    fill = PatternFill("solid", fgColor=PRIMARY_BLUE)
    for r in range(1, MASTHEAD_ROWS + 1):
        ws.row_dimensions[r].height = 20  # 2 x 20pt band
        for c in range(1, ncols + 1):
            ws.cell(row=r, column=c).fill = fill

    img = XLImage(str(_LOGO_PATH))
    img.height = 34  # ~0.35in at 96dpi
    img.width = round(34 * _LOGO_SRC_W / _LOGO_SRC_H)  # keep true aspect ratio
    ws.add_image(img, "A1")

    tc = ws.cell(row=1, column=title_start, value=title)
    tc.font = Font(name="Dosis", size=14, bold=True, color="FFFFFF")
    tc.alignment = Alignment(horizontal="left", vertical="center")
    ws.merge_cells(start_row=1, start_column=title_start,
                   end_row=MASTHEAD_ROWS, end_column=date_start - 1)

    dc = ws.cell(row=1, column=date_start, value=period_label)
    dc.font = Font(name="Dosis", size=10, bold=True, color="FFFFFF")
    dc.alignment = Alignment(horizontal="right", vertical="center")
    ws.merge_cells(start_row=1, start_column=date_start,
                   end_row=MASTHEAD_ROWS, end_column=ncols)


# ── Tab: Summary (styled first tab, Design-System §4) ─────────────────

_SUMMARY_WIDTHS = [18.0] * 6


def _summary_stats(results: dict) -> dict:
    scored = results.get("scored", {})
    pipeline = results.get("pipeline", "per_lead")
    sold_key = "sale_count" if pipeline == "aggregated" else "deal_count"
    n_scored = len(scored)
    team_sold = sum(s["raw"].get(sold_key, 0) or 0 for s in scored.values())
    if float(team_sold).is_integer():
        team_sold = int(team_sold)
    total_leads = int(sum(s["raw"].get("lead_count", 0) or 0 for s in scored.values()))
    avg_score = (sum(s["score"] for s in scored.values()) / n_scored) if n_scored else 0.0
    a_tier = sum(1 for s in scored.values() if s["tier"] == "A")
    n_flags = sum(len(s.get("flags", [])) for s in scored.values())
    top = max(scored.items(), key=lambda kv: kv[1]["score"]) if scored else None
    return {
        "n_scored": n_scored, "team_sold": team_sold, "total_leads": total_leads,
        "avg_score": round(avg_score, 1), "a_tier": a_tier, "n_flags": n_flags,
        "top": top,
    }


def _put_stat(ws, label_row: int, col: int, label: str, value):
    """One key stat: small Dosis label over a large Sky Blue Dosis number.
    Spans two columns (col, col+1)."""
    lc = ws.cell(row=label_row, column=col, value=label.upper())
    lc.font = Font(name="Dosis", size=10, bold=True, color=PRIMARY_BLUE)
    lc.alignment = Alignment(horizontal="left", vertical="bottom")
    ws.merge_cells(start_row=label_row, start_column=col,
                   end_row=label_row, end_column=col + 1)
    vc = ws.cell(row=label_row + 1, column=col, value=value)
    vc.font = Font(name="Dosis", size=26, bold=True, color=SKY_BLUE)
    vc.alignment = Alignment(horizontal="left", vertical="center")
    if isinstance(value, float):
        vc.number_format = "0.0"
    ws.merge_cells(start_row=label_row + 1, start_column=col,
                   end_row=label_row + 1, end_column=col + 1)


def _build_summary(wb: Workbook, results: dict, store_name: str, period_label: str):
    ws = wb.create_sheet("Summary")
    for i, w in enumerate(_SUMMARY_WIDTHS, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    _add_masthead(ws, "Salesperson Scorecard Summary", period_label, _SUMMARY_WIDTHS)

    pipeline = results.get("pipeline", "per_lead")
    stats = _summary_stats(results)

    ws["A4"] = store_name
    ws["A4"].font = _title_font()
    ws.merge_cells("A4:F4")
    src = ("Aggregated Tekion User Activity Report" if pipeline == "aggregated"
           else "Per-lead export with activity log")
    ws["A5"] = f"Salesperson performance scorecard · {period_label} · {src}"
    ws["A5"].font = _muted_font()
    ws.merge_cells("A5:F5")

    ws["A7"] = "Key numbers"
    ws["A7"].font = _section_font()
    ws.merge_cells("A7:F7")

    for row in (9, 12):
        ws.row_dimensions[row].height = 34
    _put_stat(ws, 8, 1, "Salespeople scored", stats["n_scored"])
    _put_stat(ws, 8, 3, "Leads worked (scored reps)", stats["total_leads"])
    _put_stat(ws, 8, 5, "Team sold", stats["team_sold"])
    _put_stat(ws, 11, 1, "Average score", float(stats["avg_score"]))
    _put_stat(ws, 11, 3, "A-tier performers", stats["a_tier"])
    _put_stat(ws, 11, 5, "Coaching flags", stats["n_flags"])

    r = 14
    if stats["top"]:
        name, s = stats["top"]
        tc = ws.cell(row=r, column=1,
                     value=f"Top performer: {name} scored {s['score']} (Tier {s['tier']}).")
        tc.font = _body_font(b=True)
        tc.fill = PatternFill("solid", fgColor=LIGHT_BLUE)
        tc.alignment = Alignment(vertical="center", indent=1)
        for c in range(2, 7):
            ws.cell(row=r, column=c).fill = PatternFill("solid", fgColor=LIGHT_BLUE)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
        ws.row_dimensions[r].height = 24
        r += 2

    ws.cell(row=r, column=1, value="How to read this workbook").font = _section_font()
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
    r += 1

    guide = [
        ("Methodology", "Factor weights, tier definitions, and score interpretation."),
        ("Salesperson Scorecard", "The headline ranking: composite 1-10 score, tier, and core rates per rep."),
        ("Factor Detail", "Every factor's raw value, normalized value, and weighted contribution."),
        ("Coaching Flags", "Rep-level coaching notes, ordered by severity."),
    ]
    if results.get("bdc"):
        guide.append(("BDC and Non-Sales", "BDC / coordinator roles, reported on their own metrics, not the rep rubric."))
    if results.get("other_bucket"):
        guide.append(("Other (Unattributed)", "Leads never assigned to a salesperson; a routing-rule problem to review."))
    guide += [
        ("Not Scored", "Reps below the minimum lead volume, plus filtered placeholder accounts."),
        ("Raw Data", "The underlying rows the scores were computed from."),
    ]
    for tab, desc in guide:
        ws.cell(row=r, column=1, value=tab).font = _body_font(b=True)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
        dcell = ws.cell(row=r, column=3, value=desc)
        dcell.font = _body_font()
        dcell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=6)
        r += 1

    scale = ws.cell(row=r + 1, column=1,
                    value="Scale: 1-10 composite, normalized to the top performer this period. "
                          "Tiers: A 8-10 · B 5-7 · C 3-4 · D 1-2.")
    scale.font = _muted_font()
    scale.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=r + 1, start_column=1, end_row=r + 1, end_column=6)


# ── Tab: Methodology ──────────────────────────────────────────────────

_METHODOLOGY_WIDTHS = [28.0, 90.0]


def _build_methodology(wb: Workbook, results: dict, store_name: str, period_label: str):
    ws = wb.create_sheet("Methodology")
    ws.column_dimensions["A"].width = _METHODOLOGY_WIDTHS[0]
    ws.column_dimensions["B"].width = _METHODOLOGY_WIDTHS[1]

    _add_masthead(ws, "Methodology", period_label, _METHODOLOGY_WIDTHS)

    ws["A4"] = store_name
    ws["A4"].font = Font(name="Dosis", size=14, bold=True, color=PRIMARY_BLUE)
    ws.merge_cells("A4:B4")

    pipeline = results.get("pipeline", "per_lead")
    pipeline_label = ("Aggregated Tekion User Activity Report"
                      if pipeline == "aggregated"
                      else "Per-lead export with activity log")
    ws["A5"] = f"{period_label} · Data source: {pipeline_label}"
    ws["A5"].font = _muted_font()
    ws.merge_cells("A5:B5")

    ws["A7"] = "Methodology"
    ws["A7"].font = _section_font()
    ws.merge_cells("A7:B7")

    if pipeline == "aggregated":
        rows = [
            ("Scale", "1-10 composite, normalized to top performer in this period."),
            ("Tiers", "A: 8-10  |  B: 5-7  |  C: 3-4  |  D: 1-2"),
            ("Sale Conversion (25%)", "Sold ÷ Good Leads."),
            ("Appointment Set Rate (12%)", "Appointments Scheduled ÷ Good Leads."),
            ("Appointment Show Rate (12%)", "Appointments Shown ÷ Appointments Scheduled."),
            ("Sales Volume (10%)", "Raw Sold count (split deals shown as .5)."),
            ("Task Completion (10%)", "Completed Tasks ÷ Total Tasks. Pipeline discipline."),
            ("Activity per Lead (8%)", "(Calls + Texts + Emails) ÷ Good Leads."),
            ("Call Connection (8%)", "Calls Out Contacted ÷ Total Calls Out. Phone QUALITY, not volume."),
            ("Appt Confirmation Rate (8%)", "Appointments Confirmed ÷ Scheduled. Best predictor of show rate."),
            ("Tasks Overdue (4%)", "Inverse-normalized; fewer overdue = higher score."),
            ("Video Adoption (3%)", "Video Sent Leads ÷ Good Leads."),
            ("Minimum volume", "Salespeople below 25 leads in the period are not scored."),
            ("Role classification", "BDC and unattributed-lead bucket auto-detected and surfaced on separate tabs."),
            ("Response time", "Not in the User Activity Report. Use the per-lead export path to include it."),
        ]
    else:
        rows = [
            ("Scale", "1-10 composite, normalized to top performer in this period."),
            ("Tiers", "A: 8-10  |  B: 5-7  |  C: 3-4  |  D: 1-2"),
            ("Sale Conversion (40%)", "Deals closed ÷ leads owned at creation."),
            ("Appointment Show Rate (20%)", "Appointments shown ÷ appointments set by this rep."),
            ("Sales Volume (15%)", "Raw count of deals closed in the period."),
            ("Appointment Set Rate (15%)", "Appointments set ÷ leads owned at creation."),
            ("Response Time (10%)", "Median first-response time, inverse-normalized to fastest rep."),
            ("Minimum volume", "Salespeople below 25 leads in the period are not scored."),
            ("Credit apps", "Excluded from all denominators."),
            ("Auto-responses", "Excluded from response-time calculation."),
        ]

    r = 8
    for label, value in rows:
        ws[f"A{r}"] = label
        ws[f"A{r}"].font = _body_font(b=True)
        ws[f"A{r}"].alignment = Alignment(vertical="top")
        ws[f"B{r}"] = value
        ws[f"B{r}"].font = _body_font()
        ws[f"B{r}"].alignment = Alignment(wrap_text=True, vertical="top")
        r += 1

    ws[f"A{r+1}"] = "Score interpretation"
    ws[f"A{r+1}"].font = _section_font()
    ws.merge_cells(f"A{r+1}:B{r+1}")
    interp = [
        ("A (8-10)", "Top performer. Role-model territory; consider for mentor or lead-share priority."),
        ("B (5-7)",  "Solid contributor. Coach on lowest-weighted factor to push to A."),
        ("C (3-4)",  "Underperforming. Run the coaching flags and follow up within 30 days."),
        ("D (1-2)",  "Not pulling weight on multiple factors. Performance plan candidate."),
    ]
    rr = r + 2
    for label, value in interp:
        ws[f"A{rr}"] = label
        ws[f"A{rr}"].font = _body_font(b=True)
        ws[f"B{rr}"] = value
        ws[f"B{rr}"].font = _body_font()
        rr += 1


# ── Tab: Salesperson Scorecard ────────────────────────────────────────

def _scorecard_headers(pipeline: str) -> tuple[list[str], list[int]]:
    if pipeline == "aggregated":
        headers = ["Rank", "Salesperson", "Score", "Tier",
                   "Leads", "Sold", "Sale %", "Set %", "Show %",
                   "Confirm %", "TskCmp %", "Conn %", "Touches/Lead",
                   "Overdue", "Top Flag"]
        widths = [6, 22, 7, 6, 7, 6, 8, 8, 8, 9, 9, 8, 14, 9, 55]
        return headers, widths
    headers = ["Rank", "Salesperson", "Score", "Tier",
               "Leads", "Sales", "Sale %", "Set %", "Show %",
               "Median Response", "Top Flag"]
    widths = [6, 24, 8, 6, 8, 8, 9, 9, 9, 18, 60]
    return headers, widths


def _build_scorecard(wb: Workbook, results: dict, period_label: str):
    ws = wb.create_sheet("Salesperson Scorecard")
    pipeline = results.get("pipeline", "per_lead")
    headers, widths = _scorecard_headers(pipeline)
    _add_masthead(ws, "Salesperson Scorecard", period_label, widths)
    _write_header_row(ws, headers)

    scored = results.get("scored", {})
    ranked = sorted(scored.items(), key=lambda kv: kv[1]["score"], reverse=True)

    for i, (sp_id, s) in enumerate(ranked, start=1):
        raw = s["raw"]
        flags = s.get("flags", [])
        top_flag = flags[0]["message"] if flags else ""

        if pipeline == "aggregated":
            row = [
                i, sp_id, s["score"], s["tier"],
                int(raw["lead_count"]),
                raw["sale_count"],
                _fmt_pct(raw["sale_conversion"]),
                _fmt_pct(raw["set_rate"]),
                _fmt_pct_or_dash(raw["show_rate"], raw.get("appts_scheduled", 0)),
                _fmt_pct_or_dash(raw["confirmation_rate"], raw.get("appts_scheduled", 0)),
                _fmt_pct_or_dash(raw["task_completion"], raw.get("tasks_total", 0)),
                _fmt_pct_or_dash(raw["call_connection"], raw.get("calls_out", 0)),
                f"{raw['activity_per_lead']:.1f}",
                int(raw.get("tasks_overdue", 0)),
                top_flag,
            ]
            tier_col = 4
        else:
            row = [
                i, sp_id, s["score"], s["tier"],
                raw["lead_count"], int(raw["deal_count"]),
                _fmt_pct(raw["sale_conversion"]),
                _fmt_pct(raw["set_rate"]),
                _fmt_pct(raw["show_rate"]),
                _fmt_seconds(raw["response_time_median_sec"]),
                top_flag,
            ]
            tier_col = 4

        _write_body_row(ws, i + HEADER_ROW, row)
        tier_cell = ws.cell(row=i + HEADER_ROW, column=tier_col)
        # Fill is a palette treatment; the tier LETTER in the cell is the label.
        tier_cell.fill = PatternFill("solid", fgColor=TIER_FILL.get(s["tier"], WARM_GREY))
        tier_cell.font = Font(name="Dosis", size=10, bold=True,
                              color=TIER_TEXT.get(s["tier"], "FFFFFF"))
        tier_cell.alignment = Alignment(horizontal="center")

    for col, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = w
    ws.freeze_panes = f"A{DATA_START_ROW}"


# ── Tab: Factor Detail ────────────────────────────────────────────────

def _build_factor_detail(wb: Workbook, results: dict, period_label: str):
    ws = wb.create_sheet("Factor Detail")
    pipeline = results.get("pipeline", "per_lead")

    if pipeline == "aggregated":
        factors = [
            ("sale_conversion",   "Sale Conv",     "pct"),
            ("set_rate",          "Set Rate",      "pct"),
            ("show_rate",         "Show Rate",     "pct"),
            ("sales_volume",      "Sales Vol",     "int"),
            ("task_completion",   "Task Cmp",      "pct"),
            ("activity_per_lead", "Touches/Lead",  "float"),
            ("call_connection",   "Call Conn",     "pct"),
            ("confirmation_rate", "Confirm",       "pct"),
            ("tasks_overdue",     "Overdue (inv)", "skip"),
            ("video_adoption",    "Video Adopt",   "pct"),
        ]
    else:
        factors = [
            ("sale_conversion", "Sale Conv",  "pct"),
            ("show_rate",       "Show Rate",  "pct"),
            ("sales_volume",    "Sales Vol",  "int"),
            ("set_rate",        "Set Rate",   "pct"),
            ("response_time",   "Response",   "skip"),
        ]

    headers = ["Salesperson", "Score", "Tier"]
    for _, label, _ in factors:
        headers += [f"{label} (raw)", f"{label} (norm)", f"{label} contrib"]
    widths = [22, 7, 6] + [12, 12, 12] * len(factors)
    _add_masthead(ws, "Factor Detail", period_label, widths)
    _write_header_row(ws, headers)

    scored = results.get("scored", {})
    ranked = sorted(scored.items(), key=lambda kv: kv[1]["score"], reverse=True)

    for i, (sp_id, s) in enumerate(ranked, start=1):
        raw = s["raw"]; n = s["normalized"]; c = s["contribution"]
        row = [sp_id, s["score"], s["tier"]]
        for key, _, kind in factors:
            if key == "response_time":
                raw_v = _fmt_seconds(raw.get("response_time_median_sec"))
            elif key == "tasks_overdue":
                raw_v = int(raw.get("tasks_overdue", 0))
            elif kind == "pct":
                raw_v = _fmt_pct(raw.get(key, 0.0))
            elif kind == "int":
                raw_v = int(raw.get(key, 0))
            else:
                raw_v = f"{raw.get(key, 0.0):.2f}"
            row += [raw_v, f"{n.get(key, 0.0):.2f}", c.get(key, 0.0)]
        _write_body_row(ws, i + HEADER_ROW, row)

    for col, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = w
    ws.freeze_panes = f"B{DATA_START_ROW}"


# ── Tab: Coaching Flags ───────────────────────────────────────────────

def _build_coaching_flags(wb: Workbook, results: dict, period_label: str):
    ws = wb.create_sheet("Coaching Flags")
    headers = ["Salesperson", "Score", "Tier", "Severity", "Category", "Coaching Note"]
    widths = [22, 7, 6, 10, 22, 80]
    _add_masthead(ws, "Coaching Flags", period_label, widths)
    _write_header_row(ws, headers)

    scored = results.get("scored", {})
    ranked = sorted(scored.items(), key=lambda kv: kv[1]["score"], reverse=True)

    r = DATA_START_ROW
    any_flags = False
    for sp_id, s in ranked:
        for f in s.get("flags", []):
            any_flags = True
            row = [sp_id, s["score"], s["tier"], f["severity"], f["category"], f["message"]]
            _write_body_row(ws, r, row)
            sev_cell = ws.cell(row=r, column=4)
            sev_cell.fill = PatternFill("solid", fgColor=SEVERITY_FILL.get(f["severity"], "FFFFFF"))
            sev_cell.alignment = Alignment(horizontal="center")
            r += 1

    if not any_flags:
        ws.cell(row=DATA_START_ROW, column=1,
                value="No coaching flags triggered this period.").font = _muted_font()
        ws.merge_cells(start_row=DATA_START_ROW, start_column=1,
                       end_row=DATA_START_ROW, end_column=len(headers))

    for col, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = w
    ws.freeze_panes = f"A{DATA_START_ROW}"


# ── Tab: BDC / Non-Sales Roles ────────────────────────────────────────

def _build_bdc(wb: Workbook, results: dict, period_label: str):
    bdc = results.get("bdc", {})
    if not bdc:
        return
    ws = wb.create_sheet("BDC and Non-Sales")
    headers = ["Name", "Detected as", "Leads", "Tasks", "Cmp %", "Calls", "Conn %",
               "Texts", "Emails", "Appts Created", "Confirmed", "Shown", "Sold (split)"]
    widths = [22, 38, 7, 9, 9, 7, 9, 8, 8, 14, 10, 8, 12]
    _add_masthead(ws, "BDC and Non-Sales Roles", period_label, widths)
    _write_header_row(ws, headers)

    for i, (name, m) in enumerate(bdc.items(), start=1):
        row = [
            name,
            m.get("role_reason", "BDC / appt coordinator"),
            int(m["lead_count"]),
            int(m.get("tasks_total", 0)),
            _fmt_pct_or_dash(m.get("task_completion", 0.0), m.get("tasks_total", 0)),
            int(m.get("calls_out", 0)),
            _fmt_pct_or_dash(m.get("call_connection", 0.0), m.get("calls_out", 0)),
            int(m.get("texts_sent", 0)),
            int(m.get("emails_sent", 0)),
            int(m.get("appts_created", 0)),
            int(m.get("appts_confirmed", 0)),
            int(m.get("appts_shown", 0)),
            m.get("sale_count", 0),
        ]
        _write_body_row(ws, i + HEADER_ROW, row)

    note = ("Not scored against the salesperson rubric — different role. "
            "Their CORE metrics are task completion, appts created, calls, and confirm rate.")
    ws.cell(row=ws.max_row + 2, column=1, value=note).font = _muted_font()
    ws.merge_cells(start_row=ws.max_row, start_column=1, end_row=ws.max_row, end_column=len(headers))

    for col, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = w
    ws.freeze_panes = f"A{DATA_START_ROW}"


# ── Tab: Other Bucket (unattributed) ──────────────────────────────────

def _build_other_bucket(wb: Workbook, results: dict, period_label: str):
    ob = results.get("other_bucket")
    totals = results.get("totals_row")
    if not ob:
        return
    ws = wb.create_sheet("Other (Unattributed)")
    widths = [36.0, 16.0]
    ws.column_dimensions["A"].width = widths[0]
    ws.column_dimensions["B"].width = widths[1]

    _add_masthead(ws, "Other (Unattributed)", period_label, widths)

    ws["A4"] = 'Unattributed-lead bucket — "Other" row from Tekion'
    ws["A4"].font = _title_font()
    ws.merge_cells("A4:B4")

    pct_of_total = ""
    if totals and totals.get("lead_count"):
        pct_of_total = f"  ({ob['lead_count'] / totals['lead_count'] * 100:.1f}% of all leads)"

    ws["A6"] = f"Leads in this bucket: {int(ob['lead_count'])}{pct_of_total}"
    ws["A6"].font = _body_font(b=True)
    ws.merge_cells("A6:B6")

    ws["A7"] = ("These are leads that came into the CRM without being assigned to a salesperson. "
                "They appear in the dealership's lead funnel but no one is working them. "
                "This is its own problem worth investigating — review the Tekion lead-routing rules.")
    ws["A7"].font = _muted_font()
    ws["A7"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells("A7:B7")
    ws.row_dimensions[7].height = 50

    rows = [
        ("Total tasks logged", int(ob.get("tasks_total", 0))),
        ("Tasks completed", int(ob.get("tasks_completed", 0))),
        ("Calls out", int(ob.get("calls_out", 0))),
        ("Texts sent", int(ob.get("texts_sent", 0))),
        ("Emails sent", int(ob.get("emails_sent", 0))),
        ("Appointments created", int(ob.get("appts_created", 0))),
        ("Appointments scheduled", int(ob.get("appts_scheduled", 0))),
        ("Appointments shown", int(ob.get("appts_shown", 0))),
        ("Sold", ob.get("sale_count", 0)),
    ]
    r = 9
    for label, value in rows:
        ws[f"A{r}"] = label
        ws[f"A{r}"].font = _body_font(b=True)
        ws[f"B{r}"] = value
        ws[f"B{r}"].font = _body_font()
        r += 1


# ── Tab: Not Scored ───────────────────────────────────────────────────

def _build_not_scored(wb: Workbook, results: dict, period_label: str):
    ws = wb.create_sheet("Not Scored")
    headers = ["Salesperson", "Lead Count", "Reason"]
    widths = [24, 12, 50]
    _add_masthead(ws, "Not Scored", period_label, widths)
    _write_header_row(ws, headers)

    rows = sorted(results.get("not_scored", {}).items(),
                  key=lambda kv: kv[1]["lead_count"], reverse=True)
    if not rows:
        ws.cell(row=DATA_START_ROW, column=1,
                value="All salespeople met the minimum volume threshold.").font = _muted_font()
        ws.merge_cells(start_row=DATA_START_ROW, start_column=1,
                       end_row=DATA_START_ROW, end_column=len(headers))
    else:
        for i, (sp_id, info) in enumerate(rows, start=1):
            _write_body_row(ws, i + HEADER_ROW, [sp_id, info["lead_count"], info["reason"]])

    placeholders = results.get("placeholders", {})
    if placeholders:
        start_r = ws.max_row + 2
        ws.cell(row=start_r, column=1,
                value="Filtered (placeholder / inactive accounts):").font = _section_font()
        ws.merge_cells(start_row=start_r, start_column=1, end_row=start_r, end_column=3)
        for j, (name, reason) in enumerate(placeholders.items(), start=1):
            r = start_r + j
            ws.cell(row=r, column=1, value=name).font = _body_font()
            ws.cell(row=r, column=2, value="—").font = _muted_font()
            ws.cell(row=r, column=3, value=reason).font = _muted_font()

    for col, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = w
    ws.freeze_panes = f"A{DATA_START_ROW}"


# ── Tab: Raw Data ─────────────────────────────────────────────────────

def _build_raw_data(wb: Workbook, results: dict, period_label: str):
    pipeline = results.get("pipeline", "per_lead")
    ws = wb.create_sheet("Raw Data")

    if pipeline == "aggregated":
        headers = ["Name", "Role", "Good Leads", "Total Tasks", "Completed",
                   "Cmp %", "Overdue", "Calls Out", "Contacted", "Conn %",
                   "Texts", "Emails", "Videos", "Video Leads",
                   "Appts Created", "Scheduled", "Confirmed", "Shown",
                   "Sold"]
        widths = [22, 13, 9, 10, 10, 9, 8, 9, 10, 8, 7, 8, 8, 11, 13, 11, 11, 9, 7]
        _add_masthead(ws, "Raw Data", period_label, widths)
        _write_header_row(ws, headers)
        summaries = results.get("summaries_in_period", [])
        # Include totals row too for reference
        for i, s in enumerate(summaries, start=1):
            cmp_pct = (s.completed_tasks / s.total_tasks) if s.total_tasks else 0
            conn = (s.calls_out_contacted / s.calls_out) if s.calls_out else 0
            row = [
                s.name, s.role,
                int(s.good_leads), int(s.total_tasks), int(s.completed_tasks),
                _fmt_pct_or_dash(cmp_pct, s.total_tasks), int(s.tasks_overdue),
                int(s.calls_out), int(s.calls_out_contacted),
                _fmt_pct_or_dash(conn, s.calls_out),
                int(s.texts_sent), int(s.emails_sent),
                int(s.videos_sent), int(s.video_sent_leads),
                int(s.appointments_created), int(s.appointments_scheduled),
                int(s.appointments_confirmed), int(s.appointments_shown),
                s.sold,
            ]
            _write_body_row(ws, i + HEADER_ROW, row)
    else:
        headers = ["Lead ID", "Created", "Source", "Is Credit App",
                   "Initial Owner", "Final Owner", "Appt Set By", "Appt Status",
                   "Test Drive", "Sold By", "Sold Timestamp", "Vehicle Type",
                   "Gross", "First Response (s)", "Activity Count"]
        widths = [14, 18, 22, 12, 18, 18, 18, 14, 11, 18, 18, 12, 10, 16, 14]
        _add_masthead(ws, "Raw Data", period_label, widths)
        _write_header_row(ws, headers)
        leads = results.get("leads_in_period", [])
        from schemas.normalized_lead import ActivityType as AT
        for i, lead in enumerate(leads, start=1):
            appt = lead.appointment
            deal = lead.deal
            candidates = [
                a.timestamp for a in lead.activities
                if a.type in (AT.OUTBOUND_CALL, AT.OUTBOUND_TEXT, AT.OUTBOUND_EMAIL)
                and not a.is_auto_response
                and a.timestamp >= lead.created_timestamp
            ]
            first_resp = (min(candidates) - lead.created_timestamp).total_seconds() if candidates else None
            row = [
                lead.lead_id,
                lead.created_timestamp.isoformat(timespec="minutes"),
                lead.source,
                "Y" if lead.is_credit_app else "",
                lead.initial_owner, lead.final_owner,
                appt.set_by_salesperson_id if appt else "",
                appt.status if appt else "",
                "Y" if lead.test_drive_taken else "",
                deal.salesperson_id if deal else "",
                deal.sold_timestamp.isoformat(timespec="minutes") if (deal and deal.sold_timestamp) else "",
                deal.vehicle_type if deal else "",
                deal.gross if (deal and deal.gross is not None) else "",
                f"{first_resp:.0f}" if first_resp is not None else "",
                len(lead.activities),
            ]
            _write_body_row(ws, i + HEADER_ROW, row)

    for col, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = w
    ws.freeze_panes = f"A{DATA_START_ROW}"


# ── Row helpers ───────────────────────────────────────────────────────

def _write_header_row(ws, headers):
    """Table header row directly below the masthead (row HEADER_ROW)."""
    ws.row_dimensions[HEADER_ROW].height = 28
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=HEADER_ROW, column=col, value=h)
        c.font = _header_font()
        c.fill = _header_fill()
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = _border()


def _write_body_row(ws, row_idx: int, values: list):
    fill = _alt_fill() if row_idx % 2 == 0 else None
    for col, v in enumerate(values, 1):
        c = ws.cell(row=row_idx, column=col, value=v)
        c.font = _body_font()
        c.alignment = Alignment(vertical="center",
                                wrap_text=isinstance(v, str) and len(str(v)) > 30)
        c.border = _border()
        if fill:
            c.fill = fill


# ── Public API ───────────────────────────────────────────────────────

def build_workbook(results: dict, *, store_name: str, period_label: str,
                   output_path: str) -> str:
    wb = Workbook()
    wb.remove(wb.active)

    _build_summary(wb, results, store_name, period_label)
    _build_methodology(wb, results, store_name, period_label)
    _build_scorecard(wb, results, period_label)
    _build_factor_detail(wb, results, period_label)
    _build_coaching_flags(wb, results, period_label)
    _build_bdc(wb, results, period_label)
    _build_other_bucket(wb, results, period_label)
    _build_not_scored(wb, results, period_label)
    _build_raw_data(wb, results, period_label)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    wb.save(output_path)
    return output_path
