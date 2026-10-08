#!/usr/bin/env python3
"""McPeek's Site Watch: DigitalCLIQ-branded Excel deliverable for the GM.

Reads DATA/report.json (from report.py) plus the model-written
DATA/exec_summary.txt and writes

  OUT/McPeeks_Site_Watch_<date>.xlsx        the deliverable
  OUT/McPeeks_Site_Watch_<date>.facts.json  facts manifest for the QA gate

Audience: the dealership General Manager and owner. Every tab answers a GM
question in plain English before it shows any data:
  Summary            where the store stands, in one screen
  Fix List           what to fix, why it matters, who fixes it, how
  Scorecard          all 25 checks, this run vs last, pass / watch / action
  Legal & Pricing    per-vehicle detail for the legal items
  Inventory Accuracy per-vehicle detail for photo / payment / pricing-data items
  Site Health        scripts, consent, SSL, redirects, page speed
  Phone Checklist    the numbers a person must test-call
  What Changed       new vs resolved since the previous run, with the reason

Design-System (Resources/design-system/Design-System.md) is law: Digital Blue
masthead + white knockout logo on every sheet, Dosis for structure, Roboto Slab
for reading, palette-only status coding with the meaning always in text.

Usage:
  build_workbook.py --data DATA_DIR --out OUT_DIR [--summary DATA/exec_summary.txt]
                    [--logo PATH] [--prepared-for "Name, Title"]
"""
import argparse, datetime, json, math, os, re, sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XlImage
from openpyxl.worksheet.properties import PageSetupProperties

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_catalog import (CATALOG, CHECK_IDS, AREA_ORDER, AREA_LEGAL, AREA_ACCURACY,
                           AREA_HEALTH, AREA_PHONE)

# ---- palette (Design-System tokens only) ----
DIGITAL_BLUE = "405FAB"; SKY_BLUE = "6B9DD4"; WARM_GREY = "949592"; WHITE = "FFFFFF"
NAVY_BASE = "10162A"; CARD_NAVY = "131B30"; TILE_BLUE = "2E4780"
CALLOUT = "EDF2F9"; CARD_WHITE = "FBFBFD"; BORDER = "D8E1F0"; BLACK = "000000"

VAULT = "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ"
DEFAULT_LOGO = os.path.join(VAULT, "Resources", "brand-assets", "digital-cliq-logo-solid-1000px-wide.png")

fill = lambda hexv: PatternFill("solid", start_color=hexv)
F_BRAND = fill(DIGITAL_BLUE); F_TILE = fill(TILE_BLUE); F_SKY = fill(SKY_BLUE)
F_CALLOUT = fill(CALLOUT); F_CARD = fill(CARD_WHITE); F_GREY = fill(WARM_GREY); F_WHITE = fill(WHITE)

thin = Side(style="thin", color=BORDER)
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
white_side = Side(style="medium", color=WHITE)
TILE_BOX = Border(left=white_side, right=white_side, top=white_side, bottom=white_side)

def font(name="Roboto Slab", size=10, bold=False, color=BLACK, italic=False, underline=None):
    return Font(name=name, size=size, bold=bold, color=color, italic=italic, underline=underline)

DOSIS = "Dosis"; SLAB = "Roboto Slab"
LEFT = Alignment(horizontal="left", vertical="top", wrap_text=True)
LEFT_MID = Alignment(horizontal="left", vertical="center", wrap_text=True)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
RIGHT = Alignment(horizontal="right", vertical="center")

STATUS_STYLE = {   # palette treatments only; the label text carries the meaning
    "ACTION NEEDED": (F_BRAND, font(DOSIS, 10, True, WHITE)),
    "ACTION": (F_BRAND, font(DOSIS, 10, True, WHITE)),
    "WATCH": (F_SKY, font(DOSIS, 10, True, WHITE)),
    "MANUAL CHECK": (F_SKY, font(DOSIS, 10, True, WHITE)),
    "MANUAL": (F_SKY, font(DOSIS, 10, True, WHITE)),
    "CLEAR": (F_CALLOUT, font(DOSIS, 10, True, TILE_BLUE)),
    "NOT RUN": (F_CALLOUT, font(DOSIS, 10, True, WARM_GREY)),
    "NEW": (F_BRAND, font(DOSIS, 9, True, WHITE)),
    "PERSISTING": (F_CALLOUT, font(DOSIS, 9, True, TILE_BLUE)),
    "BASELINE": (F_CALLOUT, font(DOSIS, 9, True, TILE_BLUE)),
}


def plural(n, w):
    return w if n == 1 else w + "s"


def pretty_date(iso):
    if not iso:
        return "none (first run)"
    d = datetime.date.fromisoformat(iso)
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def lines_needed(text, width_chars):
    """Rough line count for a wrapped cell: Roboto Slab 10 fits ~1.05 chars per width unit."""
    if not text:
        return 1
    n = 0
    for para in str(text).split("\n"):
        n += max(1, math.ceil(len(para) / max(8, width_chars * 0.92)))
    return n


def set_widths(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def masthead(ws, title, date_text, ncols, logo):
    ws.sheet_view.showGridLines = False
    ncols = max(ncols, 6)
    for r in (1, 2):
        for c in range(1, ncols + 1):
            ws.cell(row=r, column=c).fill = F_BRAND
        ws.row_dimensions[r].height = 22
    ws.merge_cells(start_row=1, start_column=3, end_row=2, end_column=ncols - 2)
    t = ws.cell(row=1, column=3, value=title)
    t.font = font(DOSIS, 14, True, WHITE); t.alignment = LEFT_MID
    ws.merge_cells(start_row=1, start_column=ncols - 1, end_row=2, end_column=ncols)
    d = ws.cell(row=1, column=ncols - 1, value=date_text)
    d.font = font(DOSIS, 10, True, WHITE); d.alignment = RIGHT
    if not os.path.exists(logo):
        raise RuntimeError(f"DigitalCLIQ white logo not found: {logo}")
    img = XlImage(logo)
    aspect = img.width / img.height if img.height else 3.2
    img.height = 34; img.width = int(round(34 * aspect))
    ws.add_image(img, "A1")
    # column A must be wide enough that the logo never overlaps the title
    need = img.width / 6.5 + 1
    if (ws.column_dimensions["A"].width or 8) < need:
        ws.column_dimensions["A"].width = need
    if (ws.column_dimensions["B"].width or 8) + (ws.column_dimensions["A"].width or 8) < need + 2:
        ws.column_dimensions["B"].width = max(ws.column_dimensions["B"].width or 8, 8)


def print_setup(ws, header_row=None, landscape=True, one_page=False):
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_LETTER
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1 if one_page else 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.page_margins.top = 0.5; ws.page_margins.bottom = 0.7
    ws.page_margins.header = 0.3; ws.page_margins.footer = 0.3
    ws.print_options.horizontalCentered = True
    if header_row:
        ws.print_title_rows = f"1:{header_row}"
    ws.oddFooter.left.text = "DigitalCLIQ · Digital Strategy && Development"
    ws.oddFooter.left.font = "Dosis,Regular"; ws.oddFooter.left.size = 8
    ws.oddFooter.right.text = "Page &P of &N"
    ws.oddFooter.right.font = "Dosis,Regular"; ws.oddFooter.right.size = 8


def eyebrow(ws, r, text, ncols, height=18):
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncols)
    c = ws.cell(row=r, column=1, value=text.upper())
    c.font = font(DOSIS, 9, True, DIGITAL_BLUE); c.alignment = LEFT_MID
    ws.row_dimensions[r].height = height
    # accent rule under the eyebrow
    for col in range(1, ncols + 1):
        ws.cell(row=r, column=col).border = Border(bottom=Side(style="medium", color=SKY_BLUE))


def para(ws, r, text, ncols, total_width, fnt=None, fill_=None, height=None, align=LEFT):
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncols)
    c = ws.cell(row=r, column=1, value=text)
    c.font = fnt or font(SLAB, 10); c.alignment = align
    if fill_:
        for col in range(1, ncols + 1):
            ws.cell(row=r, column=col).fill = fill_
    ws.row_dimensions[r].height = height or max(16, 14.5 * lines_needed(text, total_width))
    return c


def header(ws, r, labels, start_col=1, height=30):
    for i, h in enumerate(labels):
        c = ws.cell(row=r, column=start_col + i, value=h)
        c.font = font(DOSIS, 10, True, WHITE); c.fill = F_BRAND; c.border = BOX; c.alignment = CENTER
    ws.row_dimensions[r].height = height


def cell(ws, r, c, v, fnt=None, fill_=None, align=LEFT, border=BOX, fmt=None):
    x = ws.cell(row=r, column=c, value=v)
    x.font = fnt or font(SLAB, 10); x.alignment = align; x.border = border
    if fill_:
        x.fill = fill_
    if fmt:
        x.number_format = fmt
    return x


def status_cell(ws, r, c, label):
    f, fn = STATUS_STYLE.get(label, (F_CALLOUT, font(DOSIS, 10, True, TILE_BLUE)))
    return cell(ws, r, c, label, fn, f, CENTER)


def link_cell(ws, r, c, url, text="Open page"):
    real = bool(url) and str(url).startswith("http")
    x = cell(ws, r, c, text if real else "", font(SLAB, 9, False, DIGITAL_BLUE, underline="single"), None, CENTER)
    if real:
        x.hyperlink = url
    return x


def zebra(i):
    return F_WHITE if i % 2 == 0 else F_CALLOUT


def row_height_for(ws, r, texts_and_widths, minimum=18):
    lines = max(lines_needed(t, w) for t, w in texts_and_widths) if texts_and_widths else 1
    ws.row_dimensions[r].height = max(minimum, 14 * lines + 4)


# ======================================================================
# Sheets
# ======================================================================

def sheet_summary(wb, R, summary_text, logo, prepared_for):
    ws = wb.active; ws.title = "Summary"; ws.sheet_properties.tabColor = DIGITAL_BLUE
    widths = [18, 22, 22, 22, 22, 22, 18, 18]; N = len(widths); TW = sum(widths)
    set_widths(ws, widths)
    m = R["meta"]
    masthead(ws, "McPeek's CDJR of Anaheim  ·  Website Watch", pretty_date(m["date"]), N, logo)

    r = 4
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=N)
    c = ws.cell(row=r, column=1, value="DIGITALCLIQ WEBSITE WATCH  ·  MCPEEKS.COM  ·  TWICE-WEEKLY COMPLIANCE, ACCURACY AND HEALTH MONITORING")
    c.font = font(DOSIS, 9, True, DIGITAL_BLUE); c.alignment = LEFT_MID; ws.row_dimensions[r].height = 16
    r = 5
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=N)
    c = ws.cell(row=r, column=1, value="Website Compliance & Accuracy Report")
    c.font = font(DOSIS, 24, True, NAVY_BASE); c.alignment = LEFT_MID; ws.row_dimensions[r].height = 36
    r = 6
    sub = (f"Prepared for {prepared_for}   ·   Run date {pretty_date(m['date'])}   ·   "
           f"Compared with the {pretty_date(m['prev_date'])} run   ·   "
           f"{m['vehicle_count']} vehicle pages checked plus the home, search, service, parts and contact pages")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=N)
    c = ws.cell(row=r, column=1, value=sub); c.font = font(SLAB, 10, False, WARM_GREY); c.alignment = LEFT_MID
    ws.row_dimensions[r].height = 30

    # ---- stat band ----
    ac = R["area_counts"]
    tiles = [("LEGAL & PRICING ITEMS", ac.get(AREA_LEGAL, 0), "open across vehicle and site pages"),
             ("INVENTORY ACCURACY ITEMS", ac.get(AREA_ACCURACY, 0), "photos, payments, pricing data"),
             ("SITE HEALTH & PRIVACY ITEMS", ac.get(AREA_HEALTH, 0), "scripts, consent, SSL, domains"),
             ("NEW SINCE LAST RUN", m["new"], "first run: everything is new" if m["baseline"] else "items not flagged last run"),
             ("RESOLVED SINCE LAST RUN", m["resolved"], "no longer detected")]
    r = 8
    for i, (label, val, note) in enumerate(tiles):
        col = 2 + i
        a = ws.cell(row=r, column=col, value=label); a.font = font(DOSIS, 9, True, WHITE); a.fill = F_BRAND; a.alignment = CENTER; a.border = TILE_BOX
        b = ws.cell(row=r + 1, column=col, value=val); b.font = font(DOSIS, 30, True, WHITE); b.fill = F_TILE; b.alignment = CENTER; b.border = TILE_BOX
        d = ws.cell(row=r + 2, column=col, value=note); d.font = font(SLAB, 8, False, WARM_GREY); d.fill = F_CALLOUT; d.alignment = CENTER; d.border = TILE_BOX
    ws.row_dimensions[r].height = 24; ws.row_dimensions[r + 1].height = 46; ws.row_dimensions[r + 2].height = 18

    # ---- where the store stands ----
    r = 12; eyebrow(ws, r, "Where the store stands", N)
    r = 13
    header(ws, r, ["Area", "Status", "Open items"], 1)
    ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=N)
    header(ws, r, ["What it means"], 4)
    for i, a in enumerate(R["area_status"]):
        r += 1
        cell(ws, r, 1, a["area"], font(DOSIS, 11, True, TILE_BLUE), zebra(i), LEFT_MID)
        status_cell(ws, r, 2, a["status"])
        cell(ws, r, 3, a["open"], font(DOSIS, 14, True, NAVY_BASE), zebra(i), CENTER)
        ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=N)
        cell(ws, r, 4, a["meaning"], font(SLAB, 10), zebra(i), LEFT_MID)
        for col in range(5, N + 1):
            ws.cell(row=r, column=col).border = BOX; ws.cell(row=r, column=col).fill = zebra(i)
        row_height_for(ws, r, [(a["meaning"], sum(widths[3:]))], 24)

    # ---- executive summary ----
    r += 2; eyebrow(ws, r, "Executive summary", N)
    r += 1
    para(ws, r, summary_text, N, TW - 6, font(SLAB, 10.5), F_CALLOUT, align=LEFT)
    ws.row_dimensions[r].height = max(60, 15.5 * lines_needed(summary_text, TW - 8) + 12)
    for col in range(1, N + 1):
        ws.cell(row=r, column=col).border = Border(left=Side(style="thick", color=DIGITAL_BLUE) if col == 1 else None)

    # ---- top fixes ----
    r += 2; eyebrow(ws, r, "Top fixes this week", N)
    r += 1
    header(ws, r, ["#"], 1)
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4); header(ws, r, ["What to fix"], 2)
    ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=6); header(ws, r, ["Who fixes it"], 5)
    header(ws, r, ["Vehicles", "Vs last run"], 7)
    top = R["fix_list"][:3]
    for i, fx in enumerate(top):
        r += 1
        cell(ws, r, 1, fx["priority"], font(DOSIS, 16, True, DIGITAL_BLUE), zebra(i), CENTER)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
        txt = f"{fx['name']}. {fx['fix']}"
        cell(ws, r, 2, txt, font(SLAB, 10), zebra(i), LEFT_MID)
        ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=6)
        cell(ws, r, 5, fx["owner"], font(DOSIS, 11, True, TILE_BLUE), zebra(i), LEFT_MID)
        cell(ws, r, 7, fx["count"], font(DOSIS, 14, True, NAVY_BASE), zebra(i), CENTER)
        cell(ws, r, 8, fx["trend"], font(SLAB, 9), zebra(i), CENTER)
        for col in (3, 4, 6):
            ws.cell(row=r, column=col).border = BOX; ws.cell(row=r, column=col).fill = zebra(i)
        row_height_for(ws, r, [(txt, sum(widths[1:4])), (fx["owner"], sum(widths[4:6]))], 30)

    # ---- how to read ----
    r += 2; eyebrow(ws, r, "How to read this workbook", N)
    guide = [
        ("Fix List", "The action plan. One row per problem type, ranked. Says what we found, why it matters, who fixes it, and the fix. Start here."),
        ("Scorecard", f"All {len(CHECK_IDS)} checks with this run's count against last run's, so you can see what is trending the right way."),
        ("Legal & Pricing", "Every vehicle behind the legal items, with VIN, the dollar figures, and a link to the page."),
        ("Inventory Accuracy", "Every vehicle with a photo, payment, or pricing-data problem. Hand this tab to the inventory manager."),
        ("Site Health", "Scripts, cookies, consent, SSL and domain redirects, plus page-speed scores when captured."),
        ("Phone Checklist", "The numbers on the site that a person must test-call. Columns are left blank for whoever makes the calls."),
        ("What Changed", "Everything new since the previous run and everything that cleared, with the reason it cleared (fixed vs sold)."),
        ("Status labels", "ACTION NEEDED = legal exposure or a large accuracy gap. WATCH = worth a look, not urgent. CLEAR = nothing flagged. NOT RUN = not measured this run. "
                          "NEW = not flagged last run. PERSISTING = flagged last run too."),
    ]
    for i, (tab, desc) in enumerate(guide):
        r += 1
        cell(ws, r, 1, tab, font(DOSIS, 10, True, TILE_BLUE), zebra(i), LEFT_MID)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=N)
        cell(ws, r, 2, desc, font(SLAB, 9.5), zebra(i), LEFT_MID)
        for col in range(3, N + 1):
            ws.cell(row=r, column=col).border = BOX; ws.cell(row=r, column=col).fill = zebra(i)
        row_height_for(ws, r, [(desc, TW - widths[0])], 18)

    r += 2
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=N)
    c = ws.cell(row=r, column=1, value="DigitalCLIQ  ·  Digital Strategy & Development  ·  Questions on this report: Drew Moon, DigitalCLIQ")
    c.font = font(DOSIS, 8, True, WARM_GREY); c.alignment = LEFT_MID
    print_setup(ws, landscape=True, one_page=True)
    return ws


def sheet_fix_list(wb, R, logo):
    ws = wb.create_sheet("Fix List"); ws.sheet_properties.tabColor = DIGITAL_BLUE
    widths = [5, 16, 32, 8, 13, 44, 20, 44, 28, 16]; N = len(widths)
    set_widths(ws, widths)
    masthead(ws, "Fix List  ·  what to fix, why, who, how", pretty_date(R["meta"]["date"]), N, logo)
    para(ws, 3, "Ranked action plan. Legal items come first regardless of count because they carry regulatory exposure; "
                "within an area, the bigger risk ranks higher. 'Vehicles' is how many pages are affected this run. "
                "Most fixes are template or feed changes, so one fix usually clears every vehicle in the row.",
         N, sum(widths), font(SLAB, 9.5, False, TILE_BLUE), F_CALLOUT)
    hdr = 4
    header(ws, hdr, ["#", "Area", "What we found", "Vehicles", "Vs last run", "Why it matters to the store",
                     "Who fixes it", "Recommended fix", "Example vehicle", "Where to look"])
    r = hdr
    for i, fx in enumerate(R["fix_list"]):
        r += 1; z = zebra(i)
        cell(ws, r, 1, fx["priority"], font(DOSIS, 14, True, DIGITAL_BLUE), z, CENTER)
        cell(ws, r, 2, fx["area"], font(DOSIS, 10, True, TILE_BLUE), z, LEFT_MID)
        cell(ws, r, 3, f"{fx['check']}  ·  {fx['name']}", font(SLAB, 10, True), z, LEFT_MID)
        cell(ws, r, 4, fx["count"], font(DOSIS, 14, True, NAVY_BASE), z, CENTER)
        cell(ws, r, 5, fx["trend"], font(SLAB, 9), z, CENTER)
        cell(ws, r, 6, fx["why"], font(SLAB, 9.5), z, LEFT_MID)
        cell(ws, r, 7, fx["owner"], font(DOSIS, 10, True, TILE_BLUE), z, LEFT_MID)
        cell(ws, r, 8, fx["fix"], font(SLAB, 9.5), z, LEFT_MID)
        cell(ws, r, 9, fx["example"], font(SLAB, 9), z, LEFT_MID)
        tab = {AREA_LEGAL: "Legal & Pricing", AREA_ACCURACY: "Inventory Accuracy",
               AREA_HEALTH: "Site Health", AREA_PHONE: "Phone Checklist"}[fx["area"]]
        cell(ws, r, 10, f"{tab} tab", font(SLAB, 9, False, DIGITAL_BLUE), z, CENTER)
        row_height_for(ws, r, [(fx["why"], widths[5]), (fx["fix"], widths[7]), (fx["name"], widths[2]),
                               (fx["example"], widths[8])], 40)
    if not R["fix_list"]:
        r += 1
        para(ws, r, "Nothing to fix this run. Every check came back clear.", N, sum(widths))
    ws.freeze_panes = ws.cell(row=hdr + 1, column=1)
    ws.auto_filter.ref = f"A{hdr}:{get_column_letter(N)}{max(r, hdr + 1)}"
    print_setup(ws, header_row=hdr)
    return ws


def sheet_scorecard(wb, R, logo):
    ws = wb.create_sheet("Scorecard"); ws.sheet_properties.tabColor = SKY_BLUE
    widths = [7, 17, 34, 58, 9, 9, 11, 15, 26]; N = len(widths)
    set_widths(ws, widths)
    masthead(ws, f"Scorecard  ·  all {len(CHECK_IDS)} checks, this run vs last", pretty_date(R["meta"]["date"]), N, logo)
    para(ws, 3, "Every check we run, including the ones that passed. ACTION = legal item with findings. "
                "WATCH = accuracy or health item with findings. CLEAR = nothing flagged. NOT RUN = not measured this run. "
                "MANUAL = needs a person (test calls). Change is this run minus last run; negative is good.",
         N, sum(widths), font(SLAB, 9.5, False, TILE_BLUE), F_CALLOUT)
    hdr = 4
    header(ws, hdr, ["Check", "Area", "What it is called", "What we check", "This run", "Last run", "Change", "Status", "Who fixes it"])
    counts, prev = R["counts"], R["prev_counts"]
    r = hdr
    for i, cid in enumerate(CHECK_IDS):
        cat = CATALOG[cid]; r += 1; z = zebra(i)
        n, p = counts.get(cid, 0), prev.get(cid, 0)
        if cid == "C20":
            status, n_disp, p_disp, chg = "MANUAL", "see tab", "", ""
        elif cid == "C14" and not R.get("lighthouse"):
            status, n_disp, p_disp, chg = "NOT RUN", "", "", ""
        else:
            status = "CLEAR" if n == 0 else ("ACTION" if cat["area"] == AREA_LEGAL else "WATCH")
            n_disp, p_disp = n, (p if not R["meta"]["baseline"] else "")
            chg = "" if R["meta"]["baseline"] else (n - p)
        cell(ws, r, 1, cid, font(DOSIS, 11, True, DIGITAL_BLUE), z, CENTER)
        cell(ws, r, 2, cat["area"], font(DOSIS, 10, True, TILE_BLUE), z, LEFT_MID)
        cell(ws, r, 3, cat["name"], font(SLAB, 10, True), z, LEFT_MID)
        cell(ws, r, 4, cat["what"], font(SLAB, 9.5), z, LEFT_MID)
        cell(ws, r, 5, n_disp, font(DOSIS, 13, True, NAVY_BASE), z, CENTER)
        cell(ws, r, 6, p_disp, font(DOSIS, 11, False, WARM_GREY), z, CENTER)
        c7 = cell(ws, r, 7, chg, font(DOSIS, 11, True, TILE_BLUE if isinstance(chg, int) and chg <= 0 else WARM_GREY), z, CENTER)
        if isinstance(chg, int):
            (c7 if c7 is not None else ws.cell(row=r, column=7)).number_format = "+0;-0;0"
        status_cell(ws, r, 8, status)
        cell(ws, r, 9, cat["owner"], font(SLAB, 9), z, LEFT_MID)
        row_height_for(ws, r, [(cat["what"], widths[3]), (cat["name"], widths[2])], 30)
    ws.freeze_panes = ws.cell(row=hdr + 1, column=1)
    print_setup(ws, header_row=hdr)
    return ws


def detail_sheet(wb, title, tab_title, intro, rows, R, logo, tab_color=SKY_BLUE):
    ws = wb.create_sheet(tab_title); ws.sheet_properties.tabColor = tab_color
    widths = [7, 30, 24, 9, 19, 62, 12, 34, 11]; N = len(widths)
    set_widths(ws, widths)
    masthead(ws, title, pretty_date(R["meta"]["date"]), N, logo)
    para(ws, 3, intro, N, sum(widths), font(SLAB, 9.5, False, TILE_BLUE), F_CALLOUT)
    hdr = 4
    header(ws, hdr, ["Check", "Issue", "Vehicle / page", "Type", "VIN", "What we found", "Status", "Status note", "Page"])
    r = hdr
    rows = sorted(rows, key=lambda f: (-CATALOG.get(f["check"], {}).get("weight", 0), f["check"],
                                       f["vehicle"]["label"], f.get("vin") or ""))
    for i, f in enumerate(rows):
        r += 1; z = zebra(i)
        cat = CATALOG.get(f["check"], {})
        veh = f["vehicle"]["label"] or (f.get("url") or "").replace("https://", "")
        cell(ws, r, 1, f["check"], font(DOSIS, 11, True, DIGITAL_BLUE), z, CENTER)
        cell(ws, r, 2, cat.get("name", f["check"]), font(SLAB, 9.5, True), z, LEFT_MID)
        cell(ws, r, 3, veh, font(SLAB, 9.5), z, LEFT_MID)
        cell(ws, r, 4, f["vehicle"]["condition"], font(SLAB, 9.5), z, CENTER)
        cell(ws, r, 5, f.get("vin") or "", font(SLAB, 9), z, CENTER)
        found = f["summary"]
        cell(ws, r, 6, found, font(SLAB, 9.5), z, LEFT_MID)
        status_cell(ws, r, 7, f["status"])
        cell(ws, r, 8, f.get("status_note", ""), font(SLAB, 9, False, WARM_GREY), z, LEFT_MID)
        link_cell(ws, r, 9, f.get("url"))
        row_height_for(ws, r, [(found, widths[5]), (veh, widths[2]), (cat.get("name", ""), widths[1])], 20)
    if not rows:
        r += 1
        para(ws, r, "Nothing flagged in this area this run.", N, sum(widths), font(SLAB, 10, True, TILE_BLUE))
    ws.freeze_panes = ws.cell(row=hdr + 1, column=1)
    if rows:
        ws.auto_filter.ref = f"A{hdr}:{get_column_letter(N)}{r}"
    print_setup(ws, header_row=hdr)
    return ws, r


def sheet_site_health(wb, R, logo):
    rows = [f for f in R["findings"] if f["area"] == AREA_HEALTH]
    ws, r = detail_sheet(wb, "Site Health  ·  scripts, consent, SSL, domains, speed", "Site Health",
                         "Site-wide items rather than per-vehicle items. Each row names the page or domain it applies to. "
                         "Page-speed scores appear below the findings when they were captured this run.",
                         rows, R, logo)
    r += 2
    N = 9
    eyebrow(ws, r, "Page speed (Google Lighthouse, 0 to 100, higher is better)", N)
    lh = R.get("lighthouse", [])
    if not lh:
        r += 1
        para(ws, r, "Page-speed scores were not captured this run. Nothing on the site is implied by that; "
                    "the scores return with the next run.",
             N, 208, font(SLAB, 9.5, False, WARM_GREY))
        return ws
    r += 1
    header(ws, r, ["Page", "", "Performance", "Last run", "SEO", "Accessibility", "Best practices", "Largest paint (s)", ""])
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
    for i, row in enumerate(lh):
        r += 1; z = zebra(i)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
        cell(ws, r, 1, row["url"].replace("https://", ""), font(SLAB, 9.5), z, LEFT_MID)
        ws.cell(row=r, column=2).border = BOX; ws.cell(row=r, column=2).fill = z
        if "error" in row:
            ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=9)
            cell(ws, r, 3, f"Could not measure: {row['error']}", font(SLAB, 9, False, WARM_GREY), z, LEFT_MID)
            continue
        cell(ws, r, 3, row.get("performance"), font(DOSIS, 13, True, NAVY_BASE), z, CENTER)
        cell(ws, r, 4, row.get("prev_performance") if row.get("prev_performance") is not None else "", font(DOSIS, 11, False, WARM_GREY), z, CENTER)
        cell(ws, r, 5, row.get("seo"), font(DOSIS, 11, False, NAVY_BASE), z, CENTER)
        cell(ws, r, 6, row.get("accessibility"), font(DOSIS, 11, False, NAVY_BASE), z, CENTER)
        cell(ws, r, 7, row.get("best-practices"), font(DOSIS, 11, False, NAVY_BASE), z, CENTER)
        cell(ws, r, 8, row.get("lcp_s"), font(SLAB, 10), z, CENTER, fmt="0.0")
        cell(ws, r, 9, "", None, z, CENTER)
    return ws


def likely_department(pages):
    pages = [str(p) for p in pages]
    if len(pages) >= 5:
        return "Main line (site-wide)"
    if any(p.startswith("/service") for p in pages):
        return "Service"
    if any(p.startswith("/parts") for p in pages):
        return "Parts"
    if any(p.startswith("/inventory/used") for p in pages) and any(p.startswith("/inventory/new") for p in pages):
        return "Sales (new and used)"
    if any(p.startswith("/inventory/used") for p in pages):
        return "Used sales"
    if any(p.startswith("/inventory") for p in pages):
        return "New sales"
    if any(p.startswith("/finance") for p in pages):
        return "Finance"
    return "Check on call"


def sheet_phones(wb, R, logo):
    ws = wb.create_sheet("Phone Checklist"); ws.sheet_properties.tabColor = SKY_BLUE
    widths = [17, 44, 18, 18, 14, 12, 22, 22, 34]; N = len(widths)
    set_widths(ws, widths)
    masthead(ws, "Phone Checklist  ·  numbers that need a test call", pretty_date(R["meta"]["date"]), N, logo)
    para(ws, 3, "Software cannot verify where a phone number rings. Every number published on mcpeeks.com is listed here; "
                "call each one, confirm it reaches the right department with the right greeting, and note the result. "
                "Numbers that appeared or moved since the last run are marked so they get called first. "
                "Numbers burned into photos or graphics are not detectable and are not listed.",
         N, sum(widths), font(SLAB, 9.5, False, TILE_BLUE), F_CALLOUT)
    hdr = 4
    header(ws, hdr, ["Number", "Where it appears on the site", "Likely department", "Vs last run", "Called by", "Date",
                     "Reached the right department?", "Greeting / whisper OK?", "Notes"])
    r = hdr
    phones = R.get("phones", [])
    for i, p in enumerate(phones):
        r += 1; z = zebra(i)
        cell(ws, r, 1, p["number"], font(DOSIS, 12, True, NAVY_BASE), z, CENTER)
        pages = ", ".join(str(x) for x in p["pages"])
        cell(ws, r, 2, pages, font(SLAB, 9.5), z, LEFT_MID)
        cell(ws, r, 3, likely_department(p["pages"]), font(DOSIS, 10, True, TILE_BLUE), z, CENTER)
        chg = p["change"]
        st = "NEW" if chg.startswith("NEW") or chg.startswith("REMOVED") or chg == "Pages changed" else "PERSISTING"
        fl, fn = STATUS_STYLE[st]
        cell(ws, r, 4, chg, fn, fl, CENTER)
        for col in range(5, N + 1):
            cell(ws, r, col, "", font(SLAB, 10), F_CARD, LEFT_MID)
        row_height_for(ws, r, [(pages, widths[1])], 24)
    if not phones:
        r += 1
        para(ws, r, "No phone numbers were extracted this run; check the crawl.", N, sum(widths))
    r += 2
    eyebrow(ws, r, "Site-wide phone findings from this run", N)
    items = [f for f in R["findings"] if f["area"] == AREA_PHONE]
    if not items:
        r += 1
        para(ws, r, "No generic or dummy numbers detected on the department pages.", N, sum(widths), font(SLAB, 9.5, True, TILE_BLUE))
    for i, f in enumerate(items):
        r += 1
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=N)
        cell(ws, r, 1, f"{f['check']}  ·  {f['url']}: {f['summary']}", font(SLAB, 9.5), zebra(i), LEFT_MID)
        row_height_for(ws, r, [(f["summary"], sum(widths))], 18)
    ws.freeze_panes = ws.cell(row=hdr + 1, column=1)
    print_setup(ws, header_row=hdr)
    return ws


def sheet_changes(wb, R, logo):
    ws = wb.create_sheet("What Changed"); ws.sheet_properties.tabColor = SKY_BLUE
    widths = [7, 30, 26, 19, 60, 34, 11]; N = len(widths)
    set_widths(ws, widths)
    m = R["meta"]
    masthead(ws, "What Changed  ·  since the previous run", pretty_date(m["date"]), N, logo)
    if m["baseline"]:
        para(ws, 3, "This is the first run, so there is no previous run to compare against. Every finding is a baseline. "
                    "From the next run on, this tab lists what is new and what cleared.", N, sum(widths),
             font(SLAB, 10, False, TILE_BLUE), F_CALLOUT)
        print_setup(ws); return ws
    nb, rb = m.get("new_by_reason", {}), m.get("resolved_by_reason", {})
    REASON_PLURAL = {
        "New issue on a vehicle that was already listed": "new issues on vehicles that were already listed",
        "New arrival on the lot": "new arrivals on the lot",
        "New since last run": "new since last run",
        "Fixed on the page (vehicle still listed)": "fixed on the page (vehicle still listed)",
        "Vehicle no longer listed (sold or delisted)": "vehicles no longer listed (sold or delisted)",
        "No longer detected": "no longer detected",
    }
    def reason(k, v):
        return REASON_PLURAL.get(k, k.lower()) if v != 1 else k.lower()
    intro = (f"Compared with the {pretty_date(m['prev_date'])} run. {m['new']} new {plural(m['new'], 'item')}: " +
             ("; ".join(f"{v} {reason(k, v)}" for k, v in nb.items()) or "none") +
             f". {m['resolved']} resolved {plural(m['resolved'], 'item')}: " +
             ("; ".join(f"{v} {reason(k, v)}" for k, v in rb.items()) or "none") +
             ". 'Vehicle no longer listed' means the unit sold or came off the site, so the item cleared by turnover, not by a fix.")
    para(ws, 3, intro, N, sum(widths), font(SLAB, 9.5, False, TILE_BLUE), F_CALLOUT)

    r = 5; eyebrow(ws, r, f"New this run ({m['new']})", N)
    r += 1; hdr = r
    header(ws, r, ["Check", "Issue", "Vehicle / page", "VIN", "What we found", "Why it is new", "Page"])
    new_rows = sorted([f for f in R["findings"] if f["status"] == "NEW"],
                      key=lambda f: (-CATALOG.get(f["check"], {}).get("weight", 0), f["check"], f["vehicle"]["label"]))
    for i, f in enumerate(new_rows):
        r += 1; z = zebra(i)
        cell(ws, r, 1, f["check"], font(DOSIS, 11, True, DIGITAL_BLUE), z, CENTER)
        cell(ws, r, 2, CATALOG.get(f["check"], {}).get("name", f["check"]), font(SLAB, 9.5, True), z, LEFT_MID)
        cell(ws, r, 3, f["vehicle"]["label"] or (f.get("url") or "").replace("https://", ""), font(SLAB, 9.5), z, LEFT_MID)
        cell(ws, r, 4, f.get("vin") or "", font(SLAB, 9), z, CENTER)
        cell(ws, r, 5, f["summary"], font(SLAB, 9.5), z, LEFT_MID)
        cell(ws, r, 6, f.get("status_note", ""), font(SLAB, 9, False, WARM_GREY), z, LEFT_MID)
        link_cell(ws, r, 7, f.get("url"))
        row_height_for(ws, r, [(f["summary"], widths[4])], 20)
    if not new_rows:
        r += 1; para(ws, r, "Nothing new since the previous run.", N, sum(widths), font(SLAB, 10, True, TILE_BLUE))

    r += 2; eyebrow(ws, r, f"Resolved since last run ({m['resolved']})", N)
    turnover = [x for x in R["resolved"] if x["reason"].startswith("Vehicle")]
    listed = [x for x in R["resolved"] if not x["reason"].startswith("Vehicle")]
    if turnover:
        r += 1
        para(ws, r, f"{len(turnover)} {plural(len(turnover), 'item')} cleared because the vehicle sold or came off the site. These are not fixes, "
                    "so they are summarized by check instead of listed one by one.", N, sum(widths),
             font(SLAB, 9.5, False, WARM_GREY))
        r += 1
        header(ws, r, ["Check", "Issue", "Vehicles that turned over", "", "", "", ""])
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)
        ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=7)
        by = {}
        for x in turnover:
            by[x["check"]] = by.get(x["check"], 0) + 1
        for i, (chk, n) in enumerate(sorted(by.items(), key=lambda t: -t[1])):
            r += 1; z = zebra(i)
            cell(ws, r, 1, chk, font(DOSIS, 11, True, DIGITAL_BLUE), z, CENTER)
            cell(ws, r, 2, CATALOG.get(chk, {}).get("name", chk), font(SLAB, 9.5, True), z, LEFT_MID)
            ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)
            cell(ws, r, 3, n, font(DOSIS, 13, True, NAVY_BASE), z, CENTER)
            ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=7)
            cell(ws, r, 5, "", None, z, LEFT_MID)
            for col in (4, 6, 7):
                ws.cell(row=r, column=col).border = BOX; ws.cell(row=r, column=col).fill = z
            row_height_for(ws, r, [(CATALOG.get(chk, {}).get("name", chk), widths[1])], 20)
    r += 2
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=N)
    c = ws.cell(row=r, column=1, value=f"FIXED ON THE PAGE OR NO LONGER DETECTED ({len(listed)})")
    c.font = font(DOSIS, 9, True, DIGITAL_BLUE); c.alignment = LEFT_MID
    r += 1
    header(ws, r, ["Check", "Issue", "VIN / page", "", "Why it cleared", "", ""])
    ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)
    ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=7)
    res = sorted(listed, key=lambda x: (not x["reason"].startswith("Fixed"), x["check"], x["ref"]))
    for i, x in enumerate(res):
        r += 1; z = zebra(i)
        cell(ws, r, 1, x["check"], font(DOSIS, 11, True, DIGITAL_BLUE), z, CENTER)
        cell(ws, r, 2, x["name"], font(SLAB, 9.5, True), z, LEFT_MID)
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)
        cell(ws, r, 3, x["ref"], font(SLAB, 9), z, LEFT_MID); ws.cell(row=r, column=4).border = BOX; ws.cell(row=r, column=4).fill = z
        ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=7)
        fixed = x["reason"].startswith("Fixed")
        cell(ws, r, 5, x["reason"], font(SLAB, 9.5, fixed, TILE_BLUE if fixed else WARM_GREY), z, LEFT_MID)
        for col in (6, 7):
            ws.cell(row=r, column=col).border = BOX; ws.cell(row=r, column=col).fill = z
        row_height_for(ws, r, [(x["name"], widths[1]), (x["ref"], widths[2] + widths[3])], 20)
    if not res:
        r += 1; para(ws, r, "Nothing was fixed in place since the previous run.", N, sum(widths), font(SLAB, 10, True, TILE_BLUE))
    ws.freeze_panes = ws.cell(row=hdr + 1, column=1)
    print_setup(ws, header_row=hdr)
    return ws


# ======================================================================

def facts_manifest(R, summary_text, out_path, xlsx_path, prepared_for=""):
    m = R["meta"]
    facts = [
        {"value": m["date"], "label": "Run date (masthead, Summary subline)", "source": "report.py --date / findings.json generated"},
        {"value": m["prev_date"], "label": "Previous run date (Summary subline, What Changed intro)", "source": "site-watch-state/snapshot.json (prior)"},
        {"value": m["vehicle_count"], "label": "Vehicle pages checked (Summary subline)", "source": "findings.json vehicle_count (crawl.py)"},
        {"value": m["total"], "label": "Total findings", "source": "report.json findings length"},
        {"value": m["new"], "label": "NEW since last run tile", "source": "report.json meta.new (finding keys diff)"},
        {"value": m["resolved"], "label": "RESOLVED since last run tile", "source": "report.json meta.resolved (finding keys diff)"},
    ]
    for a, n in R["area_counts"].items():
        facts.append({"value": n, "label": f"Summary tile / area status: {a}", "source": "report.json area_counts"})
    for cid in CHECK_IDS:
        facts.append({"value": R["counts"].get(cid, 0), "label": f"Scorecard this run: {cid}", "source": "report.json counts"})
        facts.append({"value": R["prev_counts"].get(cid, 0), "label": f"Scorecard last run: {cid}", "source": "prior snapshot.json counts"})
    for fx in R["fix_list"]:
        facts.append({"value": fx["count"], "label": f"Fix List row {fx['priority']} vehicles: {fx['check']}", "source": "report.json fix_list"})
        facts.append({"value": fx["example"], "label": f"Fix List row {fx['priority']} example", "source": "first VIN-bearing finding for the check"})
    for p in R.get("phones", []):
        facts.append({"value": p["number"], "label": "Phone Checklist number", "source": "findings.json phones_sitewide (crawl of static pages)"})
    facts.append({"value": prepared_for, "label": "Prepared for (Summary subline)", "source": "--prepared-for / Projects/MCP/README.md Key contacts"})
    for owner in sorted({c["owner"] for c in CATALOG.values()}):
        facts.append({"value": owner, "label": "Fix owner (Fix List, Scorecard, Summary top fixes)", "source": "check_catalog.py owner field; vendors per Projects/MCP/README.md"})
    for k, v in m.get("new_by_reason", {}).items():
        facts.append({"value": v, "label": f"What Changed intro, new by reason: {k}", "source": "report.json meta.new_by_reason (first_seen.json + finding keys diff)"})
    for k, v in m.get("resolved_by_reason", {}).items():
        facts.append({"value": v, "label": f"What Changed intro, resolved by reason: {k}", "source": "report.json meta.resolved_by_reason (finding keys diff + inventory.json)"})
    turnover = {}
    for r in R.get("resolved", []):
        if r["reason"].startswith("Vehicle no longer listed"):
            turnover[r["check"]] = turnover.get(r["check"], 0) + 1
    for cid, n in sorted(turnover.items()):
        facts.append({"value": n, "label": f"What Changed turnover table: {cid}", "source": "report.json resolved (reason = vehicle no longer listed)"})
    for f_ in R.get("findings", []):
        if f_["check"] in ("C15", "C16", "C17", "C03") and not f_.get("vin"):
            for num in re.findall(r"\b\d{1,3}\b", f_.get("summary") or ""):
                facts.append({"value": int(num), "label": f"Site-wide finding figure ({f_['check']} {f_.get('url')})", "source": "findings.json (checks.py script_domains) or browser_findings.json (model browser pass, Phase 2)"})
    for num in re.findall(r"\$?[\d,]+(?:\.\d+)?%?", summary_text):
        if len(num.strip("$,%")) >= 2:
            facts.append({"value": num, "label": "Figure in the executive summary", "source": "exec_summary.txt written by the model from run_summary.md; verify against report.json"})
    with open(out_path, "w") as f:
        json.dump({"deliverable": xlsx_path, "facts": facts}, f, indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--summary", default=None, help="exec_summary.txt (default DATA/exec_summary.txt)")
    ap.add_argument("--logo", default=DEFAULT_LOGO)
    ap.add_argument("--prepared-for", default="Stewart Benjamin, General Manager")
    args = ap.parse_args()

    R = json.load(open(os.path.join(args.data, "report.json")))
    sp = args.summary or os.path.join(args.data, "exec_summary.txt")
    if not os.path.exists(sp):
        print(f"FATAL: executive summary missing at {sp}. Write it (5-8 sentences, GM voice) from run_summary.md first.",
              file=sys.stderr); sys.exit(1)
    summary_text = open(sp).read().strip().replace("—", "-")
    if len(summary_text) < 200:
        print("FATAL: executive summary is too short to ship.", file=sys.stderr); sys.exit(1)

    wb = Workbook()
    sheet_summary(wb, R, summary_text, args.logo, args.prepared_for)
    sheet_fix_list(wb, R, args.logo)
    sheet_scorecard(wb, R, args.logo)
    detail_sheet(wb, "Legal & Pricing  ·  every vehicle behind the legal items", "Legal & Pricing",
                 "One row per vehicle page with a pricing, disclosure, or consent problem. Filter by Check to work one issue at a time. "
                 "'Page' opens the live vehicle page. Status NEW means it was not flagged on the previous run.",
                 [f for f in R["findings"] if f["area"] == AREA_LEGAL], R, args.logo, DIGITAL_BLUE)
    detail_sheet(wb, "Inventory Accuracy  ·  photos, payments, pricing data", "Inventory Accuracy",
                 "Per-vehicle items that cost leads rather than create legal exposure: missing or stock photos, missing lease payments, "
                 "savings math, spin media. Hand this tab to the inventory manager; the Fix List says who owns each item.",
                 [f for f in R["findings"] if f["area"] == AREA_ACCURACY], R, args.logo)
    sheet_site_health(wb, R, args.logo)
    sheet_phones(wb, R, args.logo)
    sheet_changes(wb, R, args.logo)

    os.makedirs(args.out, exist_ok=True)
    stem = f"McPeeks_Site_Watch_{R['meta']['date']}"
    xlsx = os.path.join(args.out, stem + ".xlsx")
    wb.save(xlsx)
    facts_manifest(R, summary_text, os.path.join(args.out, stem + ".facts.json"), xlsx, args.prepared_for)
    print(xlsx)
    print(os.path.join(args.out, stem + ".facts.json"))


if __name__ == "__main__":
    main()
