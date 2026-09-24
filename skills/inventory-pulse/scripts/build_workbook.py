#!/usr/bin/env python3
"""DigitalCLIQ Inventory Pulse: branded workbook builder.

Renders the analysis JSON from snapshot_diff.py into the deliverable XLSX.
Tabs: Summary, Lease Offers, Finance Offers, Inventory Movement,
Min Price Matrix, VIN Detail, Run Log.

Design-System notes (Resources/design-system/Design-System.md is law):
- Rows 1-2 Digital Blue masthead + white knockout logo on every visible sheet.
- Rank coding uses PALETTE treatments only, never red/green heat: rank 1 =
  Sky Blue fill (strong), rank 2 = Callout Tint, middle = Card White,
  last = Warm Grey (weak), and the MEANING is always carried by text too
  (rank shown in the cell, market-low dealer named in its own column).
- Client rows: dealer cell gets Digital Blue fill + white bold Dosis.
- Fonts: Dosis structure, Roboto Slab body.

Usage: build_workbook.py <analysis.json> <out_dir>
"""
import json, os, sys
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XlImage

BRAND_BG = "405FAB"; BRAND_FG = "FFFFFF"; ALT_ROW = "EDF2F9"
BORDER_COLOR = "D8E1F0"; ACCENT_BG = "6B9DD4"; TILE_BLUE = "2E4780"
WARM_GREY = "949592"; CARD_WHITE = "FBFBFD"; DARK_NAVY = "10162A"

def _find_logo():
    """Resolve the WHITE knockout mark. The skill dir has moved before (2026-08-25),
    so try the vault explicitly, then a path relative to this script, then $DCQ_VAULT.
    Never silently fall back to no logo: the caller raises if this returns None."""
    name = "digital-cliq-logo-solid-1000px-wide.png"
    cands = []
    env = os.environ.get("DCQ_VAULT")
    if env:
        cands.append(os.path.join(env, "Resources", "brand-assets", name))
    cands.append(os.path.join("/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ",
                              "Resources", "brand-assets", name))
    here = os.path.dirname(os.path.abspath(__file__))
    for up in (4, 5, 3):
        cands.append(os.path.normpath(os.path.join(here, *([".."] * up),
                                                   "Resources", "brand-assets", name)))
    for c in cands:
        if os.path.exists(c):
            return c
    return cands[1]  # report the canonical vault path in the error


LOGO_PATH = _find_logo()

brand_fill = PatternFill("solid", start_color=BRAND_BG)
alt_fill = PatternFill("solid", start_color=ALT_ROW)
rank1_fill = PatternFill("solid", start_color=ACCENT_BG)
rank2_fill = PatternFill("solid", start_color=ALT_ROW)
rank_mid_fill = PatternFill("solid", start_color=CARD_WHITE)
rank_last_fill = PatternFill("solid", start_color=WARM_GREY)

brand_font = Font(name="Dosis", bold=True, size=14, color=BRAND_FG)
header_font = Font(name="Dosis", bold=True, size=10, color=BRAND_FG)
body_font = Font(name="Roboto Slab", size=10)
body_bold = Font(name="Roboto Slab", size=10, bold=True)
client_font = Font(name="Dosis", bold=True, size=10, color=BRAND_FG)
note_font = Font(name="Roboto Slab", size=10, color=BRAND_BG)
label_font = Font(name="Dosis", bold=True, size=11, color=TILE_BLUE)
stat_font = Font(name="Dosis", bold=True, size=22, color=ACCENT_BG)
delta_up_font = Font(name="Roboto Slab", size=9, color=WARM_GREY, bold=True)     # worse
delta_down_font = Font(name="Roboto Slab", size=9, color=TILE_BLUE, bold=True)   # better
delta_same_font = Font(name="Roboto Slab", size=9, color=WARM_GREY)
white_body = Font(name="Roboto Slab", size=10, color=BRAND_FG)

thin = Side(style="thin", color=BORDER_COLOR)
border = Border(left=thin, right=thin, top=thin, bottom=thin)
center = Alignment(horizontal="center", vertical="center", wrap_text=False)
left = Alignment(horizontal="left", vertical="center", wrap_text=True)
right = Alignment(horizontal="right", vertical="center")


NOTE_CLIP = 1000


def clip(t, n=NOTE_CLIP):
    """Run Log notes/errors are operational prose. The full text is preserved in the
    date-keyed state snapshot; the sheet shows a scannable head so one long note
    cannot blow the row to 200+px and leave a dead zone (Visual-QA render gate)."""
    t = str(t or "")
    return t if len(t) <= n else t[:n - 1].rstrip() + "\u2026"


def row_h(text, per_line, cap=260):
    return min(cap, max(16, 14 * (1 + len(str(text)) // per_line)))


def money(v):
    return f"${v:,.0f}" if v else "?"


def add_masthead(ws, title, report_date, col_count):
    col_count = max(col_count, 6)
    ws.sheet_view.showGridLines = False
    title_end = max(4, col_count - 2)
    ws.merge_cells(start_row=1, start_column=3, end_row=2, end_column=title_end)
    t = ws.cell(row=1, column=3); t.value = title; t.font = brand_font; t.alignment = center
    ws.merge_cells(start_row=1, start_column=col_count - 1, end_row=2, end_column=col_count)
    dc = ws.cell(row=1, column=col_count - 1); dc.value = report_date
    dc.font = Font(name="Dosis", bold=True, size=10, color=BRAND_FG); dc.alignment = right
    for r in (1, 2):
        for c in range(1, col_count + 1):
            ws.cell(row=r, column=c).fill = brand_fill
        ws.row_dimensions[r].height = 22
    if not os.path.exists(LOGO_PATH):
        raise RuntimeError(f"DigitalCLIQ logo not found: {LOGO_PATH}")
    img = XlImage(LOGO_PATH)
    aspect = img.width / img.height if img.height else 1.0
    img.height = 34; img.width = int(round(34 * aspect))
    ws.add_image(img, "A1")


def freeze_and_filter(ws, header_row_idx=4, last_col=None, autofilter=False):
    """Design-System: keep the header row on screen; long tabs lose it otherwise."""
    ws.freeze_panes = ws.cell(row=header_row_idx + 1, column=1)
    if autofilter and last_col and ws.max_row > header_row_idx:
        ws.auto_filter.ref = f"A{header_row_idx}:{get_column_letter(last_col)}{ws.max_row}"


def header_row(ws, r, headers, widths=None):
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=r, column=c, value=h)
        cell.font = header_font; cell.fill = brand_fill; cell.border = border
        # wrap so long headers (dealer-name columns) show on two lines instead of clipping
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        if widths:
            ws.column_dimensions[get_column_letter(c)].width = widths[c - 1]
    ws.row_dimensions[r].height = 30


def rank_fill(rank, size):
    # A group of ONE is not a market low, it is the only offer. Shading it Sky Blue
    # told the reader the most expensive lease in the book was the cheapest.
    if not rank or size <= 1:
        return rank_mid_fill
    if rank == 1: return rank1_fill
    if size <= 1: return rank_mid_fill
    if rank == size: return rank_last_fill
    if rank == 2: return rank2_fill
    return rank_mid_fill


def rank_font(rank, size):
    # Navy ink on every rank fill: white on Warm Grey measures ~2.9:1 contrast
    return Font(name="Roboto Slab", size=10, bold=(rank == 1), color=DARK_NAVY)


def delta_font(dt):
    return {"up": delta_up_font, "down": delta_down_font, "new": delta_down_font}.get(dt, delta_same_font)


def legend_cell(ws, row_idx, text, col_count, height=30, chars_per_line=150):
    """Full-width explainer row. Excel does NOT auto-fit merged cells, so a long
    legend silently clips unless we size it ourselves: allot ~14pt per wrapped
    line across the merged width and never go below the caller's height."""
    lines = max(1, -(-len(str(text)) // chars_per_line))
    need = max(height, 14 * lines)
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=col_count)
    c = ws.cell(row=row_idx, column=1, value=text)
    c.font = note_font; c.alignment = left
    ws.row_dimensions[row_idx].height = need
    return c


def style_dealer_cell(cell, is_client):
    if is_client:
        cell.fill = brand_fill; cell.font = client_font
    else:
        cell.font = body_font
    cell.border = border; cell.alignment = left


def body_cell(ws, r, c, v, align=left, font=None):
    cell = ws.cell(row=r, column=c, value=v)
    cell.font = font or body_font; cell.border = border; cell.alignment = align
    return cell


def offer_sentence(o):
    if o.get("offer_text"):
        return o["offer_text"]
    pmt = money(o.get("pmt", 0)); term = o.get("term_mo") or "?"
    down = money(o.get("down", 0)) if o.get("down") else "?"
    miles = f"{o['miles_yr']:,}" if o.get("miles_yr") else "?"
    das = money(o.get("das", 0))
    return f"{pmt}/mo for {term} mos, {down} down, {miles} mi/yr ({das} due at signing)"


def build_summary(ws, a):
    m = a["meta"]
    add_masthead(ws, "DigitalCLIQ Inventory Pulse", m["run_date"], 8)
    for c, w in enumerate([22, 16, 16, 16, 16, 16, 16, 18], 1):
        ws.column_dimensions[get_column_letter(c)].width = w
    r = 4
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
    c = ws.cell(row=r, column=1, value=m["client_name"])
    c.font = Font(name="Dosis", bold=True, size=24, color=TILE_BLUE); c.alignment = left
    ws.row_dimensions[r].height = 34  # 24pt Dosis clips at the default row height
    r += 1
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
    sub = ws.cell(row=r, column=1, value=(
        f"Competitive lease, finance, and inventory intelligence  |  {m['brand']}  |  "
        f"Models: {', '.join(m.get('models_tracked', []))}  |  "
        f"Model years in market: {', '.join(str(y) for y in m.get('model_years', [])) or 'resolving'}"))
    sub.font = note_font; sub.alignment = left
    r += 2
    stats = [("Run type", m["run_type"].title()),
             ("Compared against", m["compare_label"]),
             ("Tracking since", m["tracking_since"]),
             ("Dealers in set", str(len(m["dealer_order"])))]
    for i, (lbl, val) in enumerate(stats):
        col = 1 + i * 2
        ws.cell(row=r, column=col, value=lbl).font = label_font
        ws.cell(row=r + 1, column=col, value=val).font = Font(name="Dosis", bold=True, size=14, color=ACCENT_BG)
    r += 3
    ws.cell(row=r, column=1, value="Competitive set").font = label_font
    r += 1
    for dl in a["meta"]["dealers"]:
        tag = "client" if dl.get("role") == "client" else "competitor"
        status = dl.get("status", "?")
        cell = ws.cell(row=r, column=1, value=f"{dl['name']}  ({tag}, crawl: {status})")
        cell.font = body_bold if dl.get("role") == "client" else body_font
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
        r += 1
    r += 1
    ws.cell(row=r, column=1, value="Pricing summary").font = label_font
    r += 1
    _bullets = a["summary_bullets"]
    if a.get("movement_note"):
        _bullets = [b for b in _bullets if not b.startswith("Baseline run: DigitalCLIQ began logging")]
    for b in _bullets:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
        cell = ws.cell(row=r, column=1, value=f"•  {b}")
        cell.font = body_font; cell.alignment = left
        ws.row_dimensions[r].height = max(16, 14 * (1 + len(b) // 110))
        r += 1
    if a.get("movement_note"):
        r += 1
        _n = a["movement_note"]
        _rows = max(2, -(-len(_n) // 130))
        ws.merge_cells(start_row=r, start_column=1, end_row=r + _rows - 1, end_column=8)
        cell = ws.cell(row=r, column=1, value=_n)
        cell.font = note_font; cell.fill = alt_fill; cell.alignment = left
        ws.row_dimensions[r].height = max(15, 14 * _rows)
        r += _rows
    r += 1
    _method_rows = 5
    ws.merge_cells(start_row=r, start_column=1, end_row=r + _method_rows - 1, end_column=8)
    ws.row_dimensions[r].height = 16 * _method_rows
    mc = ws.cell(row=r, column=1, value=(
        "Method: live read of each dealer's published website offers and of their new inventory. Inventory depth "
        "is not equal across dealers; the per-dealer unit counts are on the Min Price Matrix and VIN Detail tabs. "
        "Where a dealer was sampled rather than read in full, its minimum is a floor and the true low could sit "
        "below the sample. Unknown values show as ?. Rankings use effective monthly "
        "cost ((due at signing + remaining payments) / term), not the advertised teaser payment. Conditional "
        "payments (stacked, non-universal rebates) are labeled. Prepared by DigitalCLIQ."))
    mc.font = note_font; mc.alignment = left


def build_lease(ws, a):
    rows = a["lease_rows"]
    headers = ["Dealer", "Model", "Trim", "MY", "First Seen", "$/mo", "Vs Prior", "Eff $/mo", "Rank",
               "Term", "Down", "Miles/Yr", "DAS", "MSRP", "Type", "Flags", "Offer (as published)",
               "Prior $/mo", "Prior Offer"]
    widths = [22, 12, 18, 6, 11, 9, 12, 9, 7, 6, 9, 9, 9, 10, 11, 18, 46, 9, 40]
    add_masthead(ws, "Lease Offers: this period vs prior", a["meta"]["run_date"], len(headers))
    legend_cell(ws, 3, (
        "Rows for models outside the tracked set are included where a dealer advertises them, as market context. "
        "The Flags column is written in plain language: 'cash due not published' means the effective cost and rank "
        "for that row are provisional; a mileage flag marks a lease under 10,000 miles a year; 'banner vs disclaimer "
        "conflict' and 'two due-at-signing figures' mean the advertised terms and the dealer's own legal copy disagree. "
        "Effective $/mo is shaded by rank across dealers within each model and model-year (Sky Blue = market low, "
        "Warm Grey = highest). Where only one dealer advertises that model the row reads 'only offer' and is not "
        "shaded, because a single offer has no market position. "
        "Rank column carries the position in text. Your rows show a Digital Blue dealer cell. "
        f"Comparison: {a['meta']['compare_label']}."), len(headers))
    header_row(ws, 4, headers, widths)
    r = 5
    for row in rows:
        style_dealer_cell(ws.cell(row=r, column=1, value=row["dealer"]), row["is_client"])
        body_cell(ws, r, 2, row.get("model", ""))
        body_cell(ws, r, 3, row.get("trim", ""))
        body_cell(ws, r, 4, row.get("yr") or "?", center)
        body_cell(ws, r, 5, row.get("first_seen", ""), center)
        body_cell(ws, r, 6, money(row.get("pmt", 0)), right, body_bold)
        body_cell(ws, r, 7, row["delta_label"], center, delta_font(row["delta_type"]))
        ec = body_cell(ws, r, 8, money(row.get("eff_mo", 0)), right,
                       rank_font(row["rank"], row["group_size"]))
        ec.fill = rank_fill(row["rank"], row["group_size"])
        _prov = "cash due not published" in str(row.get("flags", ""))
        body_cell(ws, r, 9, ((("only offer" if row["group_size"] <= 1
                               else f"{row['rank']} of {row['group_size']}")
                              + (" (provisional)" if _prov else ""))
                             if row["rank"] else "?"), center)
        body_cell(ws, r, 10, row.get("term_mo") or "?", center)
        body_cell(ws, r, 11, money(row.get("down", 0)) if row.get("down") else "?", right)
        body_cell(ws, r, 12, f"{row['miles_yr']:,}" if row.get("miles_yr") else "?", right)
        body_cell(ws, r, 13, money(row.get("das", 0)), right)
        body_cell(ws, r, 14, money(row.get("msrp", 0)), right)
        body_cell(ws, r, 15, row.get("payment_type", "") or "?", center,
                  body_bold if row.get("payment_type") == "conditional" else body_font)
        body_cell(ws, r, 16, row.get("flags", ""))
        body_cell(ws, r, 17, offer_sentence(row))
        prev = row.get("prev")
        body_cell(ws, r, 18, money(prev["pmt"]) if prev else "-", right)
        body_cell(ws, r, 19, (prev.get("offer_text") or offer_sentence(prev)) if prev else "-")
        # row height keyed to the widest wrapped text: offer col wraps ~40 chars/line
        prev_len = len(prev.get("offer_text") or "") if prev else 0
        lines = 1 + max(len(offer_sentence(row)), prev_len) // 40
        lines = max(lines, 1 + len(row.get("flags", "")) // 16, 1 + len(row.get("trim", "")) // 16)
        ws.row_dimensions[r].height = min(150, max(28, 14 * lines + 4))
        r += 1
    if not rows:
        ws.cell(row=5, column=1, value="No published lease offers captured this run. See Run Log for crawl status.").font = note_font


def build_finance(ws, a):
    rows = a["finance_rows"]
    headers = ["Dealer", "Model", "Trim", "MY", "First Seen", "APR", "Vs Prior", "Rank", "Term", "MSRP",
               "Conditions", "Prior APR", "Prior Term"]
    widths = [22, 12, 10, 6, 11, 8, 12, 7, 8, 11, 44, 9, 9]
    add_masthead(ws, "Finance Offers: this period vs prior", a["meta"]["run_date"], len(headers))
    legend_cell(ws, 3, (
        "APR shaded by rank across dealers within each model and model-year (Sky Blue = lowest); a lone offer reads "
        "'only offer' and is not shaded. A genuine advertised 0.00% is shown as "
        "0.00% and ranks lowest. ? = no APR published, which is the case for a cash or rebate offer; read the "
        "Conditions column for what that offer actually is. "
        + ("Only the client published a finance offer in this set this run. "
           if rows and len({x["dealer"] for x in rows}) == 1 and rows[0].get("is_client") else "")
        + f"Comparison: {a['meta']['compare_label']}."), len(headers))
    header_row(ws, 4, headers, widths)
    r = 5
    for row in rows:
        style_dealer_cell(ws.cell(row=r, column=1, value=row["dealer"]), row["is_client"])
        body_cell(ws, r, 2, row.get("model", ""))
        body_cell(ws, r, 3, row.get("trim", ""))
        body_cell(ws, r, 4, row.get("yr") or "?", center)
        body_cell(ws, r, 5, row.get("first_seen", ""), center)
        _apr_pub = row.get("apr_published")
        ac = body_cell(ws, r, 6, f"{row['apr']:.2f}%" if _apr_pub else "?", right,
                       rank_font(row["rank"], row["group_size"]))
        ac.fill = rank_fill(row["rank"], row["group_size"])
        body_cell(ws, r, 7, row["delta_label"], center, delta_font(row["delta_type"]))
        body_cell(ws, r, 8, ("only offer" if row["rank"] and row["group_size"] <= 1
                             else (f"{row['rank']} of {row['group_size']}" if row["rank"] else "?")), center)
        body_cell(ws, r, 9, f"{row['term_mo']} mos" if row.get("term_mo") else "?", center)
        body_cell(ws, r, 10, money(row.get("msrp", 0)), right)
        body_cell(ws, r, 11, row.get("conditions", ""))
        # Conditions wraps in a ~44-char column and the dealer/model cells wrap too;
        # without an explicit height Excel leaves these at one line and silently clips.
        _lines = max(1 + len(str(row.get("conditions", ""))) // 44,
                     1 + len(str(row.get("dealer", ""))) // 22,
                     1 + len(str(row.get("model", ""))) // 12)
        ws.row_dimensions[r].height = min(210, max(28, 14 * _lines + 4))
        prev = row.get("prev")
        body_cell(ws, r, 12, f"{prev['apr']:.2f}%" if prev and prev.get("apr") else "-", right)
        body_cell(ws, r, 13, f"{prev['term_mo']} mos" if prev and prev.get("term_mo") else "-", center)
        r += 1
    if not rows:
        ws.cell(row=5, column=1, value="No published finance/APR specials captured this run.").font = note_font


def build_movement(ws, a):
    _days = a["meta"].get("tracking_days")
    headers = ["Year", "Make", "Model", "Trim", "MSRP",
               f"Delisted ({_days}d)" if _days else "Delisted (120d)", "Avg DOM", "Dealer"]
    widths = [7, 10, 14, 20, 11, 14, 9, 24]
    add_masthead(ws, "Inventory Movement: what sold, where, at what price", a["meta"]["run_date"], len(headers))
    legend_cell(ws, 3, (
        "Units DigitalCLIQ observed leaving each dealer's website (delisted = sold or pulled), grouped by "
        "year/make/model/trim/MSRP, sorted by units moved. Avg DOM = average days on market at delist."), len(headers))
    r = 4
    if a.get("movement_note"):
        _n = a["movement_note"]
        _rows = max(1, -(-len(_n) // 150))
        ws.merge_cells(start_row=r, start_column=1, end_row=r + _rows - 1, end_column=len(headers))
        cell = ws.cell(row=r, column=1, value=_n)
        cell.font = body_bold; cell.fill = alt_fill; cell.alignment = left
        ws.row_dimensions[r].height = max(28, 14 * _rows)
        r += _rows
    header_row(ws, r, headers, widths)
    r += 1
    for row in a["movement_rows"]:
        body_cell(ws, r, 1, row["yr"] or "?", center)
        body_cell(ws, r, 2, row["make"])
        body_cell(ws, r, 3, row["model"])
        body_cell(ws, r, 4, row["trim"])
        body_cell(ws, r, 5, money(row["msrp"]), right)
        body_cell(ws, r, 6, row["delisted"], center, body_bold)
        body_cell(ws, r, 7, row["avg_dom"] or "?", center)
        style_dealer_cell(ws.cell(row=r, column=8, value=row["dealer"]), row["is_client"])
        r += 1
    if not a["movement_rows"]:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(headers))
        ws.cell(row=r, column=1, value="No delistings observed yet in the tracking window.").font = note_font


def build_matrix(ws, a):
    dealers = a["meta"]["dealer_order"]
    n = len(dealers)
    failed = {d["name"] for d in a["meta"]["dealers"] if d.get("status") == "failed"}
    show_trim = any((row.get("trim") or "").strip() for row in a["matrix_rows"])
    headers = ["Model", "Trim", "MY"] if show_trim else ["Model", "MY"]
    for dl in dealers:
        headers += [f"{dl}: Min Price", "# @ Min", "Age (DOM)"]
    headers += ["Market Low"]
    widths = ([13, 10, 6] if show_trim else [13, 6]) + [20, 7, 10] * n + [24]
    add_masthead(ws, "Minimum Advertised Price by model", a["meta"]["run_date"], len(headers))
    units = {}
    for v in a["vin_rows"]:
        units[v["dealer"]] = units.get(v["dealer"], 0) + 1
    counts = ", ".join(f"{d['name']} {units.get(d['name'], 0)}"
                       for d in a["meta"]["dealers"] if d.get("status") != "failed")
    legend_cell(ws, 3, (
        "Lowest advertised price per model/model-year. The number in parentheses after each price is that dealer's rank "
        "in the set (1 = market low); the separate '# @ Min' column is how many units sit at that price. "
        "Sky Blue = market low, Warm Grey = highest, and the Market Low column names the winning dealer in text. "
        "Depth is not equal, so read the ranks with that in mind. Units read this run: " + counts + ". "
        "Where a dealer was sampled rather than read in full, its minimum is a floor, not a confirmed market position: "
        "the true low could sit below the sample. The Run Log records how each dealer was read. "
        "? = sampled but no price published. 'not in sample' = no unit of this model-year was drawn for this dealer, "
        "which is not a claim that the dealer has none. 'no data (crawl failed)' = the site could not be read this run, which is "
        "not the same as carrying none."),
        len(headers))
    header_row(ws, 4, headers, widths)
    r = 5
    for row in a["matrix_rows"]:
        body_cell(ws, r, 1, row["model"], left, body_bold)
        if show_trim:
            body_cell(ws, r, 2, row["trim"])
        body_cell(ws, r, 3 if show_trim else 2, row["yr"] or "?", center)
        c = 4 if show_trim else 3
        ranked = [d2 for d2 in dealers if row["cells"].get(d2, {}).get("rank")]
        for dl in dealers:
            cell = row["cells"].get(dl, {})
            rank = cell.get("rank", 0)
            if dl in failed:
                # deliberately NOT Warm Grey: that token means "highest price" in this sheet
                fc = body_cell(ws, r, c, "no data (crawl failed)", center, body_bold)
                fc.font = note_font
                body_cell(ws, r, c + 1, "n/a", center)
                body_cell(ws, r, c + 2, "n/a", center)
                c += 3
                continue
            if cell.get("cfp_only"):
                pc = body_cell(ws, r, c, f"CFP ({cell.get('n_stock',0)} in stock)", center, body_bold)
                pc.fill = rank_last_fill; pc.font = white_body
            elif cell.get("min_price"):
                pc = body_cell(ws, r, c, f"{money(cell['min_price'])}  ({rank})", right,
                               rank_font(rank, len(ranked)))
                pc.fill = rank_fill(rank, len(ranked))
            elif cell.get("n_stock"):
                body_cell(ws, r, c, "?", center)
            else:
                body_cell(ws, r, c, "not in sample", center)
            body_cell(ws, r, c + 1, cell.get("n_at_min", 0) or "?", center)
            am, ax = cell.get("age_min", 0), cell.get("age_max", 0)
            # age 0 means "no days-on-market derivable yet", never "zero days on the lot"
            if ax and ax != am:
                age = f"{am or '?'}-{ax}"
            else:
                age = str(am) if am else "?"
            body_cell(ws, r, c + 2, age, center)
            c += 3
        body_cell(ws, r, c, (f"{row['market_low_dealer']}  {money(row['market_low_price'])}"
                             if row["market_low_dealer"] else "-"), left, body_bold)
        r += 1


def build_vins(ws, a):
    headers = ["Model", "Trim", "Version", "MY", "VIN", "MSRP", "Adv. Price", "Disc/Markup",
               "DOM", "Dealer"]
    widths = [13, 26, 38, 6, 22, 11, 11, 12, 9, 24]
    add_masthead(ws, "Per-VIN pricing: client vs competitors", a["meta"]["run_date"], len(headers))
    per = {}
    for v in a["vin_rows"]:
        per[v["dealer"]] = per.get(v["dealer"], 0) + 1
    comp = ", ".join(f"{k} {n}" for k, n in sorted(per.items(), key=lambda x: -x[1]))
    has_floor = any(v.get("dom_note") for v in a["vin_rows"])
    legend_cell(ws, 3, (
        "Tracked new units read this run, by dealer: " + comp + ". Depth is not equal between dealers. "
        "Where a dealer was sampled rather than read in full, its minimum is a floor and the true low could sit "
        "below the sample. Disc/Markup = advertised price minus MSRP; a "
        "positive number means the unit is advertised above MSRP. "
        + ("DOM prefixed >= means the unit was already on the lot when DigitalCLIQ tracking began. " if has_floor else "")
        + "? = not yet derivable (first capture)."
        + (" CFP = Call for Price." if any(v.get("call_for_price") for v in a["vin_rows"]) else "")), len(headers))
    header_row(ws, 4, headers, widths)
    r = 5
    for row in a["vin_rows"]:
        body_cell(ws, r, 1, row["model"], left, body_bold if row["is_client"] else body_font)
        body_cell(ws, r, 2, row["trim"])
        body_cell(ws, r, 3, row["version"])
        body_cell(ws, r, 4, row["yr"] or "?", center)
        body_cell(ws, r, 5, row["vin"], center)
        body_cell(ws, r, 6, money(row["msrp"]), right)
        body_cell(ws, r, 7, "CFP" if (row["call_for_price"] and not row["price"]) else money(row["price"]), right)
        dv = row["delta"]
        dc = body_cell(ws, r, 8, ("$0" if dv == 0 else f"{'+' if dv>0 else '-'}${abs(dv):,.0f}") if dv is not None else "?",
                       right, delta_up_font if (dv or 0) > 0 else (delta_down_font if (dv or 0) < 0 else body_font))
        body_cell(ws, r, 9, f"{row['dom_note']}{row['dom']}" if row["dom"] else "?", center)
        style_dealer_cell(ws.cell(row=r, column=10, value=row["dealer"]), row["is_client"])
        if row["is_client"]:
            for c in range(1, 10):
                if ws.cell(row=r, column=c).fill.start_color.rgb in (None, "00000000"):
                    ws.cell(row=r, column=c).fill = alt_fill
        r += 1


def build_runlog(ws, a):
    m = a["meta"]
    headers = ["Dealer", "Role", "Platform", "Crawl Method", "Status", "Pages", "Notes"]
    widths = [24, 11, 18, 22, 12, 8, 60]
    add_masthead(ws, "Run Log", m["run_date"], len(headers))
    header_row(ws, 4, headers, widths)
    r = 5
    for dl in m["dealers"]:
        style_dealer_cell(ws.cell(row=r, column=1, value=dl["name"]), 1 if dl.get("role") == "client" else 0)
        body_cell(ws, r, 2, dl.get("role", ""))
        body_cell(ws, r, 3, dl.get("platform", ""))
        body_cell(ws, r, 4, dl.get("crawl_method", ""))
        body_cell(ws, r, 5, dl.get("status", ""), center,
                  body_bold if dl.get("status") != "ok" else body_font)
        body_cell(ws, r, 6, dl.get("pages_crawled", 0), center)
        body_cell(ws, r, 7, clip(dl.get("notes", "")))
        ws.row_dimensions[r].height = row_h(clip(dl.get("notes", "")), 58)
        r += 1
    r += 1
    ws.cell(row=r, column=1, value="Errors this run").font = label_font
    r += 1
    for e in (a.get("errors") or ["none"]):
        e = clip(e)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(headers))
        ec = ws.cell(row=r, column=1, value=f"•  {e}")
        ec.font = body_font; ec.alignment = left
        ws.row_dimensions[r].height = row_h(clip(e), 120)
        r += 1
    r += 1
    legend_cell(ws, r, (
        f"Run {m['run_date']} ({m['run_type']}), compared {m['compare_label']}, tracking since "
        f"{m['tracking_since']}. Generated {m['generated']} by DigitalCLIQ Inventory Pulse."), len(headers))


def main():
    analysis_path, out_dir = sys.argv[1], sys.argv[2]
    with open(analysis_path) as f:
        a = json.load(f)
    m = a["meta"]
    wb = Workbook()
    ws = wb.active; ws.title = "Summary"; build_summary(ws, a)
    build_lease(wb.create_sheet("Lease Offers"), a)
    build_finance(wb.create_sheet("Finance Offers"), a)
    build_movement(wb.create_sheet("Inventory Movement"), a)
    build_matrix(wb.create_sheet("Min Price Matrix"), a)
    build_vins(wb.create_sheet("VIN Detail"), a)
    build_runlog(wb.create_sheet("Run Log"), a)
    # Freeze the header row on every data tab (Design-System), autofilter the long one
    for name in ("Lease Offers", "Finance Offers", "Inventory Movement", "Min Price Matrix",
                 "VIN Detail", "Run Log"):
        sh = wb[name]
        hdr = next((c.row for c in sh["A"] if c.value == "Dealer" or c.value == "Model"
                    or c.value == "Year"), 4)
        freeze_and_filter(sh, header_row_idx=hdr, last_col=sh.max_column,
                          autofilter=(name == "VIN Detail"))
    # Fit every sheet to one page wide so PDF export / render gate never splits
    # columns across pages (the source of 30-page renders for 7 tabs)
    from openpyxl.worksheet.properties import PageSetupProperties
    for ws in wb.worksheets:
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    out = os.path.join(out_dir, f"DigitalCLIQ_Inventory_Pulse_{m['client_code']}_{m['run_date']}.xlsx")
    wb.save(out)
    print(out)


if __name__ == "__main__":
    main()
