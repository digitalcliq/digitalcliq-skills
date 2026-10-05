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

_VAULT_ROOT = os.environ.get("DIGITALCLIQ_VAULT_ROOT", "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ")
LOGO_PATH = os.path.join(_VAULT_ROOT, "Resources", "brand-assets", "digital-cliq-logo-solid-1000px-wide.png")
# Fallback to the old walk-up layout only if the vault path is missing (kept for portability):
if not os.path.exists(LOGO_PATH):
    LOGO_PATH = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
        "..", "..", "..", "..", "Resources", "brand-assets", "digital-cliq-logo-solid-1000px-wide.png"))

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


def apr_text(row):
    """0.0 means "unknown" in the fragment schema, but a 0% APR is a real and
    highly material offer. Trust the published conditions text to tell them apart
    (QA 2026-09-06: a competitor's 0% APR rendered as "no APR published")."""
    apr = row.get("apr") or 0
    if apr:
        return f"{apr:.2f}%"
    if row.get("apr_zero"):
        return "0%"
    blob = " ".join(str(row.get(f, "")) for f in
                    ("conditions", "offer_text", "parse_note", "disclaimer_text"))
    return "0%" if _re.search(r"\b0(?:\.0+)?\s*%", blob) else "?"


def depluralize(t):
    """Turn '4 offer(s)' into '4 offers' / '1 offer'. A DigitalCLIQ deliverable does
    not ship '(s)' to a dealer principal (QA 2026-09-06)."""
    def fix(m):
        n, sp, word = m.group(1), m.group(2), m.group(3)
        try:
            one = abs(float(n.replace(",", ""))) == 1
        except ValueError:
            one = False
        return f"{n}{sp}{word}" if one else f"{n}{sp}{word}s"
    # allow up to two words between the count and the pluralized noun
    t = _re.sub(r"(\b[\d,]+)(\s+(?:[A-Za-z][\w/-]*\s+){0,2})([A-Za-z][\w/-]*?)\(s\)",
                fix, str(t or ""))
    return _re.sub(r"([A-Za-z][\w/-]*?)\(s\)", r"\1s", t)


import re as _re2


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
    # A group of one has no market to lead. Shading "1 of 1" Sky Blue reads as a
    # competitive win the data does not support (QA gate 2026-09-06).
    if not rank:
        return rank_mid_fill
    if size <= 1: return rank_mid_fill
    if rank == 1: return rank1_fill
    if rank == size: return rank_last_fill
    if rank == 2: return rank2_fill
    return rank_mid_fill


def rank_font(rank, size):
    # Warm Grey #949592 under white text renders at ~3:1 and washes out. Dark navy
    # on Warm Grey is on-palette and readable.
    return Font(name="Roboto Slab", size=10, bold=(rank == 1 and size > 1),
                color=DARK_NAVY)


def delta_font(dt):
    return {"up": delta_up_font, "down": delta_down_font, "new": delta_down_font}.get(dt, delta_same_font)


def legend_cell(ws, row_idx, text, col_count, height=30, autofit_chars=152):
    # A fixed height silently clips long legends (the VIN tab lost its >=/?/CFP key
    # mid-sentence, QA gate pass 2). Grow the row to fit the wrapped text.
    if text:
        # +1 line of headroom: the chars-per-line estimate runs optimistic for
        # Roboto Slab, and the VIN legend lost its last line by ~5pt (QA 2026-10-05).
        height = max(height, 13 * (2 + len(str(text)) // autofit_chars) + 8)
    return _legend_cell_impl(ws, row_idx, text, col_count, height)


def _legend_cell_impl(ws, row_idx, text, col_count, height=30):
    """Full-width explainer row that wraps instead of clipping at the print edge."""
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=col_count)
    c = ws.cell(row=row_idx, column=1, value=depluralize(text) if isinstance(text, str) else text)
    c.font = note_font; c.alignment = left
    ws.row_dimensions[row_idx].height = height
    return c


def style_dealer_cell(cell, is_client):
    if is_client:
        cell.fill = brand_fill; cell.font = client_font
    else:
        cell.font = body_font
    cell.border = border; cell.alignment = left


_MONEY_RE = _re2.compile(r"^\$(\d[\d,]*)$")
_SIGNED_RE = _re2.compile(r"^([+-])\$(\d[\d,]*)$")
_PCT_RE = _re2.compile(r"^(\d+(?:\.\d+)?)%$")


def body_cell(ws, r, c, v, align=left, font=None):
    """Money and percentages must land as NUMBERS with a number format. Writing them
    as pre-formatted text makes Adv. Price sort lexicographically and nothing sum,
    which is the main thing anyone does with a pricing workbook (QA gate 2026-09-20)."""
    fmt = None
    if isinstance(v, str):
        m = _MONEY_RE.match(v)
        if m:
            v, fmt = int(m.group(1).replace(",", "")), "$#,##0"
        else:
            m = _SIGNED_RE.match(v)
            if m:
                v = int(m.group(2).replace(",", "")) * (-1 if m.group(1) == "-" else 1)
                fmt = '+$#,##0;-$#,##0;"$0"'
            else:
                m = _PCT_RE.match(v)
                if m:
                    v, fmt = float(m.group(1)) / 100.0, "0.0%"
    cell = ws.cell(row=r, column=c, value=depluralize(v) if isinstance(v, str) else v)
    if fmt:
        cell.number_format = fmt
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
    stats = [("Run type", m["run_type"].upper()),
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
        tag = "CLIENT" if dl.get("role") == "client" else "competitor"
        status = dl.get("status", "?")
        cell = ws.cell(row=r, column=1, value=f"{dl['name']}  ({tag}, website review: {'complete' if status == 'ok' else status})")
        cell.font = body_bold if dl.get("role") == "client" else body_font
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
        r += 1
    r += 1
    ws.cell(row=r, column=1, value="Pricing summary").font = label_font
    r += 1
    for b in a["summary_bullets"]:
        b = depluralize(b)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
        cell = ws.cell(row=r, column=1, value=f"•  {b}")
        cell.font = body_font; cell.alignment = left
        ws.row_dimensions[r].height = 15 * max(1, -(-len(b) // 92))
        r += 1
    if a.get("movement_note"):
        r += 1
        ws.merge_cells(start_row=r, start_column=1, end_row=r + 1, end_column=8)
        cell = ws.cell(row=r, column=1, value=a["movement_note"])
        cell.font = note_font; cell.fill = alt_fill; cell.alignment = left
        r += 2
    r += 1
    _METHOD = (
        "Method: a review of each dealer's published website offers and a sample of new inventory "
        f"({sample_depth_text(a)}). Unknown values show as ?. Rankings use effective monthly "
        "cost ((due at signing + remaining payments) / term), not the advertised teaser payment. Conditional "
        "payments (stacked, non-universal rebates) are labeled. Prepared by DigitalCLIQ.")
    # Excel does not auto-fit merged cells: size the block to the wrapped text or the
    # closing disclosure silently disappears (QA MAJOR 10).
    _lines = max(3, 1 + len(_METHOD) // 108)
    ws.merge_cells(start_row=r, start_column=1, end_row=r + _lines - 1, end_column=8)
    mc = ws.cell(row=r, column=1, value=_METHOD)
    mc.font = note_font; mc.alignment = left
    for _i in range(_lines):
        ws.row_dimensions[r + _i].height = 14


def build_lease(ws, a):
    rows = a["lease_rows"]
    headers = ["Dealer", "Model", "Trim", "MY", "First Seen", "$/mo", "Vs Prior", "Eff $/mo", "Rank",
               "Term", "Down", "Miles/Yr", "DAS", "MSRP", "Type", "Flags", "Offer (as published)",
               "Prior $/mo", "Prior Offer"]
    widths = [22, 12, 18, 6, 11, 9, 46, 9, 7, 6, 9, 34, 9, 10, 11, 26, 46, 9, 40]
    add_masthead(ws, "Lease Offers: this period vs prior", a["meta"]["run_date"], len(headers))
    legend_cell(ws, 3, (
        "Effective $/mo is shaded by rank within each model/trim (Sky Blue = market low, Warm Grey = highest). "
        "Rank column carries the position in text. Rank counts individual advertised units, not dealers: "
        "a store publishing several VIN-level payments occupies several ranks. "
        "Your rows show a Digital Blue dealer cell. "
        + (("First capture of offers; no offers were recorded on the compare run, so Vs Prior is not yet meaningful. ")
           if (a.get("offers_first_capture") or {}).get("lease") else "")
        + coverage_caveat(a, "lease") + " "
        + (("Note: one or more stores label their NEW-vehicle lease offers 'Pre-Owned' in the site "
            "template; offer copy is recorded exactly as published. ")
           if any("pre-owned" in (dl.get("notes", "") or "").lower() or
                  "preowned" in (dl.get("notes", "") or "").lower()
                  for dl in a["meta"]["dealers"]) else "")
        + f"Comparison: {a['meta']['compare_label']}."), len(headers), height=58)
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
        body_cell(ws, r, 9, f"{row['rank']} of {row['group_size']}" if row["rank"] else "?", center)
        body_cell(ws, r, 10, row.get("term_mo") or "?", center)
        body_cell(ws, r, 11, money(row.get("down", 0)) if row.get("down") else "?", right)
        _mi = (f"{row['miles_yr']:,}"
               + (" (from fine print)" if row.get("miles_yr_derived") else "")
               + (" (carried from prior run, not published this run)"
                  if row.get("miles_yr_carried") else "")
               + (f" ({row['miles_src']})" if row.get("miles_src") else "")
               if row.get("miles_yr") else "?")
        body_cell(ws, r, 12, _mi, right)
        body_cell(ws, r, 13, money(row.get("das", 0)), right)
        body_cell(ws, r, 14, money(row.get("msrp", 0)), right)
        body_cell(ws, r, 15, row.get("payment_type", "") or "?", center,
                  body_bold if row.get("payment_type") == "conditional" else body_font)
        body_cell(ws, r, 16, flags_text(row.get("flags", "")))
        body_cell(ws, r, 17, offer_sentence(row))
        prev = row.get("prev")
        body_cell(ws, r, 18, money(prev["pmt"]) if prev else "-", right)
        body_cell(ws, r, 19, (prev.get("offer_text") or offer_sentence(prev)) if prev else "-")
        # row height keyed to the widest wrapped text: offer col wraps ~40 chars/line
        prev_len = len(prev.get("offer_text") or "") if prev else 0
        lines = 1 + max(len(offer_sentence(row)), prev_len) // 40
        lines = max(lines, 1 + len(flags_text(row.get("flags", ""))) // 16, 1 + len(row.get("trim", "")) // 16)
        ws.row_dimensions[r].height = max(28, 14 * lines + 4)
        r += 1
    if not rows:
        ws.cell(row=5, column=1, value="No published lease offers captured this run. See Run Log for crawl status.").font = note_font
        r = 6
    pulled_block(ws, a, "lease", r, len(headers))


def pulled_block(ws, a, kind, r, col_count):
    """Offers that were live on the compare run and are gone now. Dropping them
    silently flattered the client, whose own two offers had disappeared (QA pass 2)."""
    rows = [x for x in (a.get("pulled_offers") or []) if x.get("kind") == kind]
    if not rows:
        return r
    r += 1
    ws.cell(row=r, column=1, value=f"Pulled since {a['meta'].get('compare_date') or 'the prior run'} "
                                  f"(published then, not published now)").font = label_font
    r += 1
    _key = "lease_rows" if kind == "lease" else "finance_rows"
    _has = {r.get("dealer") for r in a.get(_key, [])}
    _ref = sorted({x["dealer"] for x in rows
                   if x["dealer"] not in _has and any(dl.get("name") == x["dealer"] and (_updating_stub(dl.get("notes", "") or "", kind)
                          or _claims_confirmed_zero(dl.get("notes", "") or "", kind))
                          for dl in a["meta"]["dealers"])})
    _upd = [d for d in _ref if any(dl.get("name") == d and _updating_stub(dl.get("notes", "") or "", kind)
                                   for dl in a["meta"]["dealers"])]
    _emp = [d for d in _ref if d not in _upd]
    _txt = ""
    if _upd:
        _txt += f"{_join(_upd)}: the specials page said it was being updated when checked on {a['meta']['run_date']}. "
    if _emp:
        _txt += (f"{_join(_emp)}: the specials page showed no lease or finance offers on tracked models "
                 f"when checked on {a['meta']['run_date']}. ")
    if _ref:
        ws.cell(row=r, column=1, value=(_txt + "DigitalCLIQ will recheck next run.")).font = body_font
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=col_count)
        r += 1
    for x in rows:
        who = x["dealer"] + (" (you)" if x["is_client"] else "")
        what = f"{x.get('yr') or ''} {x.get('model','')} {x.get('trim','')}".strip()
        if kind == "lease" and x.get("pmt"):
            fig = f"was ${x['pmt']:,}/mo"
            if x.get("term_mo"):
                fig += f" / {x['term_mo']} mo"
            if x.get("das"):
                fig += f", {money(x['das'])} due at signing"
        elif kind == "finance" and x.get("apr"):
            fig = f"was {x['apr']:.2f}% APR" + (f" / {x['term_mo']} mo" if x.get("term_mo") else "")
        else:
            fig = "figure not published"
        if _re.search(r"loyalty|conquest|military|bonus cash|qualified buyers|returning lessee",
                      str(x.get("offer_text", "")), _re.I):
            fig += " (conditional: required a loyalty or qualifying credit)"
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=col_count)
        c = ws.cell(row=r, column=1, value=depluralize(f"•  {who}, {what}: {fig}."))
        c.font = body_bold if x["is_client"] else body_font
        c.alignment = left
        r += 1
    return r


def build_finance(ws, a):
    rows = a["finance_rows"]
    headers = ["Dealer", "Model", "Trim", "MY", "First Seen", "APR", "Vs Prior", "Rank", "Term", "MSRP",
               "Conditions", "Prior APR", "Prior Term"]
    widths = [22, 12, 10, 6, 11, 8, 15, 7, 8, 11, 44, 9, 9]
    add_masthead(ws, "Finance Offers: this period vs prior", a["meta"]["run_date"], len(headers))
    legend_cell(ws, 3, (
        "APR shaded by rank within each model/trim (Sky Blue = lowest). ? = no APR published "
        "(e.g. a cash/rebate offer, see Conditions). "
        + (("First capture of finance offers; no finance offers were recorded on the compare run. ")
           if (a.get("offers_first_capture") or {}).get("finance") else "")
        + coverage_caveat(a, "finance") + " "
        + f"Comparison: {a['meta']['compare_label']}."), len(headers), height=58)
    header_row(ws, 4, headers, widths)
    r = 5
    for row in rows:
        style_dealer_cell(ws.cell(row=r, column=1, value=row["dealer"]), row["is_client"])
        body_cell(ws, r, 2, row.get("model", ""))
        body_cell(ws, r, 3, row.get("trim", ""))
        body_cell(ws, r, 4, row.get("yr") or "?", center)
        body_cell(ws, r, 5, row.get("first_seen", ""), center)
        ac = body_cell(ws, r, 6, apr_text(row), right,
                       rank_font(row["rank"], row["group_size"]))
        ac.fill = rank_fill(row["rank"], row["group_size"])
        body_cell(ws, r, 7, row["delta_label"], center, delta_font(row["delta_type"]))
        body_cell(ws, r, 8, f"{row['rank']} of {row['group_size']}" if row["rank"] else "?", center)
        body_cell(ws, r, 9, f"{row['term_mo']} mos" if row.get("term_mo") else "?", center)
        body_cell(ws, r, 10, money(row.get("msrp", 0)), right)
        _cond = row.get("conditions", "") or ""
        if row.get("apr_zero_src"):
            _cond = (_cond + " " if _cond else "") + \
                    f"(0% rate as published on {row['apr_zero_src']}; this run captured the offer "
            _cond += "but not the rate text.)"
        body_cell(ws, r, 11, client_text(_cond))
        prev = row.get("prev")
        body_cell(ws, r, 12, (apr_text(prev) if prev else "-"), right)
        body_cell(ws, r, 13, f"{prev['term_mo']} mos" if prev and prev.get("term_mo") else "-", center)
        # Conditions run to 300+ chars in a wrapped column. With no explicit height
        # every non-Excel renderer clips the material terms away (QA gate 2026-09-20).
        ws.row_dimensions[r].height = max(28, 14 * (1 + len(_cond) // 44) + 4)
        r += 1
    if not rows:
        ws.cell(row=5, column=1, value="No published finance/APR specials captured this run.").font = note_font
        r = 6
    pulled_block(ws, a, "finance", r, len(headers))


def build_movement(ws, a):
    headers = ["Year", "Make", "Model", "Trim", "MSRP",
               a.get("movement_window_label") or "Delisted",
               "This run", "Avg DOM", "Dealer"]
    widths = [7, 10, 14, 20, 11, 14, 9, 9, 24]
    # Title must fit its merged span at 14pt Dosis or it clips mid-phrase (QA MAJOR 9).
    add_masthead(ws, "Inventory Movement", a["meta"]["run_date"], len(headers))
    legend_cell(ws, 3, (
        "Units DigitalCLIQ observed leaving each dealer's website (delisted = sold or pulled), grouped by "
        "year/make/model/trim/MSRP, sorted by units moved. The Delisted column counts the whole tracking "
        "window; the This run column counts only what left since the previous report, so the two differ "
        "wherever units left on an earlier run. Avg DOM = average days on market at delist."), len(headers))
    r = 4
    for _txt in (a.get("movement_note"), a.get("delist_basis")):
        if not _txt:
            continue
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(headers))
        cell = ws.cell(row=r, column=1, value=_txt)
        cell.font = body_bold; cell.fill = alt_fill; cell.alignment = left
        ws.row_dimensions[r].height = max(28, 14 * (1 + len(_txt) // 110) + 10)
        r += 1
    header_row(ws, r, headers, widths)
    # The Delisted header carries the tracking window and wraps to 3 lines at
    # width 14; the default 30pt row cut the window off (QA2 MAJOR 8).
    ws.row_dimensions[r].height = max(30, 14 * (1 + max(
        len(str(h)) // w for h, w in zip(headers, widths))) + 10)
    # This tab's header row floats (0-2 caveat rows above it); tell main() where it is.
    ws._dcq_header_row = r
    r += 1
    if not a["movement_rows"]:
        for _c in range(1, len(headers) + 1):
            body_cell(ws, r, _c, "" if _c > 1 else
                      "No delistings observed yet in the tracking window.", left, note_font).fill = alt_fill
    for row in a["movement_rows"]:
        body_cell(ws, r, 1, row["yr"] or "?", center)
        body_cell(ws, r, 2, row["make"])
        body_cell(ws, r, 3, row["model"])
        body_cell(ws, r, 4, row["trim"])
        body_cell(ws, r, 5, money(row["msrp"]), right)
        body_cell(ws, r, 6, row["delisted"], center, body_bold)
        # Separate what left THIS run from what left earlier in the window, or the
        # table appears to contradict the basis line above it (QA 2026-09-20).
        body_cell(ws, r, 7, row.get("this_run", 0), center,
                  body_bold if row.get("this_run") else body_font)
        body_cell(ws, r, 8, (f"{row.get('dom_note','')}{row['avg_dom']}" if row["avg_dom"] else "?"), center)
        style_dealer_cell(ws.cell(row=r, column=9, value=row["dealer"]), row["is_client"])
        r += 1
    if not a["movement_rows"]:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(headers))
        ws.cell(row=r, column=1, value="No delistings observed yet in the tracking window.").font = note_font


def _join_names(names):
    names = list(names)
    if len(names) <= 1:
        return names[0] if names else ""
    return ", ".join(names[:-1]) + " and " + names[-1]


def _net_price_dealers(a, tol=3):
    """Dealers whose sampled units nearly all share one negative MSRP delta are
    publishing a net-of-rebate price. Name them so the rank is not read as
    like-for-like against stores quoting an advertised price."""
    from collections import Counter, defaultdict
    per = defaultdict(list)
    for v in a.get("vin_rows", []):
        if v.get("price") and v.get("msrp"):
            per[v.get("dealer", "")].append(v["price"] - v["msrp"])
    out = []
    for dl, deltas in per.items():
        neg = [x for x in deltas if x < 0]
        if len(deltas) >= 4 and len(neg) == len(deltas) and len(Counter(neg)) <= tol:
            out.append(dl)
    # A store whose own crawl note says the shown price is net of manufacturer cash
    # is net-priced whatever its deltas look like (QA 2026-10-05, Nissan of Tustin).
    for dl in a["meta"].get("dealers", []):
        if (_re.search(r"net price|after nissan|net of", str(dl.get("notes", "")), _re.I)
                and dl.get("name") in per and dl.get("name") not in out):
            out.append(dl.get("name"))
    return sorted(out)


def _net_price_note(a):
    dls = _net_price_dealers(a)
    if not dls:
        return ""
    return ("PRICE BASIS: " + _join_names(dls) + " quote prices NET of manufacturer cash (shown by "
            "the store's own price label or by the same negative MSRP differences repeating across its "
            "stock), not a pre-rebate advertised price. "
            "Those minimums and ranks are therefore NOT like-for-like against stores that "
            "publish a pre-rebate advertised price, and the market low can flip once the "
            "rebate is added back. Verify before quoting. ")


def _mixed_trim_note(a):
    """Rows group at MODEL level, so a row can rank an xDrive against an sDrive.
    Name those models rather than letting the rank read as like-for-like (QA MAJOR 5)."""
    best = {}
    for v in a.get("vin_rows", []):
        p = v.get("price") or 0
        if not p:
            continue
        k = (v.get("model", ""), v.get("dealer", ""))
        if k not in best or p < best[k][0]:
            best[k] = (p, (v.get("trim") or "").strip())
    spans = []
    for model in sorted({m for m, _ in best}):
        trims = {t for (m, _), (_, t) in best.items() if m == model and t}
        if len(trims) > 1:
            spans.append(f"{model} ({', '.join(sorted(trims))})")
    if not spans:
        return ""
    return ("NOT LIKE-FOR-LIKE: rows group by model, and on " + "; ".join(spans) +
            " the cheapest sampled unit is a different trim or drivetrain at different stores, "
            "so those prices and ranks are not a direct comparison.")


def build_matrix(ws, a):
    dealers = a["meta"]["dealer_order"]
    n = len(dealers)
    # Matrix groups at MODEL level, so a Trim column is empty on every row by design.
    _st = {d.get("name", ""): d.get("status", "ok") for d in a["meta"].get("dealers", [])}
    headers = ["Model", "MY"]
    for dl in dealers:
        # Rank is read here, not on the Run Log: mark an incomplete crawl in place.
        _mark = "" if _st.get(dl, "ok") == "ok" else f" ({_st.get(dl)} crawl)"
        headers += [f"{dl}: Min Price{_mark}", "# @ Min", "Age (DOM)"]
    headers += ["Market Low"]
    widths = [15, 6] + [22, 8, 26] * n + [32]
    add_masthead(ws, "Minimum Advertised Price by model", a["meta"]["run_date"], len(headers))
    legend_cell(ws, 3, (
        "Lowest advertised price among SAMPLED in-stock units per model/model-year "
        f"({sample_depth_text(a)}). This is a sample, not full stock. "
        "Sky Blue = market low, Warm Grey = highest. The (n) after each price is that dealer's RANK "
        "among the stores stocking that model; the next column, # @ Min, is how many of its units sit "
        "at that price. The Market Low column names the winning dealer. "
        "CFP = dealer stocks the model but hides pricing (Call for Price). "
        "Age (DOM) is the span of days on market across that dealer's SAMPLED stock, not the age of the "
        "minimum-priced unit; a trailing + means the unit predates DigitalCLIQ tracking so the true age "
        "is at least that. "
        "\"MSRP only\" = every sampled unit is listed at sticker because that store puts its actual "
        "selling price behind a lead form; it is shown for reference and is NOT ranked, since ranking "
        "it would misread an unpublished price as an expensive one. Client is the first dealer group. "
        + ("A dealer marked partial crawl was only partly reachable this run, so its minimum and its "
           "rank are provisional. " if any(v != "ok" for v in _st.values()) else "")
        + _net_price_note(a) + _mixed_trim_note(a)),
        len(headers))
    header_row(ws, 4, headers, widths)
    r = 5
    for row in a["matrix_rows"]:
        body_cell(ws, r, 1, row["model"], left, body_bold)
        body_cell(ws, r, 2, row["yr"] or "?", center)
        c = 3
        ranked = [d2 for d2 in dealers if row["cells"].get(d2, {}).get("rank")]
        for dl in dealers:
            cell = row["cells"].get(dl, {})
            rank = cell.get("rank", 0)
            if cell.get("cfp_only"):
                pc = body_cell(ws, r, c, f"CFP ({cell.get('n_stock',0)} in stock)", center, body_bold)
                pc.fill = rank_last_fill; pc.font = white_body
            elif cell.get("msrp_only"):
                pc = body_cell(ws, r, c, f"{money(cell['min_price'])} MSRP only", right, body_font)
                pc.fill = rank_mid_fill      # unranked: not comparable, not "highest"
            elif cell.get("min_price"):
                pc = body_cell(ws, r, c, f"{money(cell['min_price'])}  ({rank})", right,
                               rank_font(rank, len(ranked)))
                pc.fill = rank_fill(rank, len(ranked))
            else:
                body_cell(ws, r, c, "-", center)
            body_cell(ws, r, c + 1, cell.get("n_at_min", 0) or "-", center)
            am, ax = cell.get("age_min", 0), cell.get("age_max", 0)
            floor = "+" if cell.get("age_note") else ""     # 12+ reads better than >=12
            if am:
                age_txt = f"{am} to {ax}{floor}" if ax and ax != am else f"{am}{floor}"
                if cell.get("age_unknown"):
                    age_txt += ", some unknown"
            else:
                age_txt = "unknown" if cell.get("n_stock") else "-"
            body_cell(ws, r, c + 2, age_txt, center)
            c += 3
        _n_ranked = len(ranked)
        body_cell(ws, r, c, (f"{row['market_low_dealer']}  {money(row['market_low_price'])}"
                             if row["market_low_dealer"] and _n_ranked > 1
                             else (f"{row['market_low_dealer']}, only store with a sampled unit" if _n_ranked == 1 else "-")),
                  left, body_bold)
        r += 1


def _markup_outlier_note(a):
    """When a store's stock mostly repeats one Price vs MSRP figure, name the units
    that carry a different one so a GM is not left guessing (QA 2026-10-05:
    Sterling BMW +$1,044 on most units, +$2,044 on its X5 M models)."""
    from collections import Counter
    out = []
    by = {}
    for v in a.get("vin_rows", []):
        if v.get("price") and v.get("msrp"):
            by.setdefault(v.get("dealer", ""), []).append(v)
    for dl, vs in by.items():
        c = Counter(int(v["price"] - v["msrp"]) for v in vs)
        mode, n = c.most_common(1)[0]
        if mode <= 0 or n < 5 or n < 0.6 * len(vs):
            continue
        odd = [v for v in vs if int(v["price"] - v["msrp"]) != mode]
        if not odd or len(odd) > 6:
            continue
        figs = Counter(int(v["price"] - v["msrp"]) for v in odd)
        desc = "; ".join(
            f"{k:+,} on {cnt} unit(s) ("
            + ", ".join(sorted({f"{v.get('model','')} {v.get('trim','')}".strip()
                                for v in odd if int(v['price'] - v['msrp']) == k})) + ")"
            for k, cnt in figs.items()).replace("+", "+$").replace("-", "-$", 1)
        out.append(f"{dl}: most sampled units show +${mode:,}; the exceptions are {desc}.")
    return (" ".join(out) + " ") if out else ""


def _unconfirmed_msrp_note(a):
    """A store whose own pages disagree on MSRP gets the caveat where the numbers
    sit, not only in the Run Log (QA gate 2026-10-05, Puente Hills CJDR)."""
    bad = sorted({str(e).split(":", 1)[0] for e in (a.get("errors") or [])
                  if "msrp" in str(e).lower() and _re.search(r"unreliable|unconfirmed|do(?:es)? not match|vs ", str(e), _re.I)
                  and ":" in str(e)})
    if not bad:
        return ""
    return (f"{_join(bad)}: sticker (MSRP) figures on some vehicle pages did not match the store's own "
            f"specials page this run, so their MSRP and Price vs MSRP figures are approximate. ")


def build_vins(ws, a):
    # A styled header over 67 blank cells reads as missing data. Drop the column
    # entirely when no row carries a value (QA2 MAJOR 11).
    _has_version = any((v.get("version") or "").strip() for v in a.get("vin_rows", []))
    headers = ["Model", "Trim"] + (["Version"] if _has_version else []) + \
              ["MY", "VIN", "MSRP", "Adv. Price", "Price vs MSRP", "DOM", "Dealer"]
    widths = [13, 18] + ([30] if _has_version else []) + [6, 22, 11, 11, 12, 9, 24]
    add_masthead(ws, "Per-VIN pricing: client vs competitors", a["meta"]["run_date"], len(headers))
    legend_cell(ws, 3, (
        f"Sampled tracked units ({sample_depth_text(a)}). Price vs MSRP = advertised price minus MSRP. "
        "A figure repeating identically across a dealer's whole stock is a fixed amount the store adds "
        "on every unit when POSITIVE (for example a destination, documentation or add-on charge; "
        "check the vehicle page for what it covers), and a universal rebate already deducted when NEGATIVE. It is not a "
        "per-unit pricing decision, and stores do not all define MSRP the same way (some include "
        "destination), so compare these figures with care. "
        + _net_price_note(a) + _unconfirmed_msrp_note(a) + _markup_outlier_note(a) +
        "DOM prefixed >= means the unit was already on the lot when DigitalCLIQ tracking began; "
        "? = not yet derivable (first capture). CFP = Call for Price."), len(headers))
    header_row(ws, 4, headers, widths)
    r = 5
    for row in a["vin_rows"]:
        body_cell(ws, r, 1, row["model"], left, body_bold if row["is_client"] else body_font)
        _trim = (row["trim"] or "").strip()
        body_cell(ws, r, 2, _trim or "?")
        _c = 3
        if _has_version:
            body_cell(ws, r, _c, row["version"]); _c += 1
        # ~13 chars per wrapped line in an 18-wide column, and Roboto Slab 10pt
        # needs ~14pt per line. Pass 1 undershot and clipped the last line.
        if len(_trim) > 13:
            ws.row_dimensions[r].height = max(ws.row_dimensions[r].height or 15,
                                              14 * (1 + len(_trim) // 13) + 6)
        body_cell(ws, r, _c, row["yr"] or "?", center); _c += 1
        body_cell(ws, r, _c, row["vin"], center); _c += 1
        body_cell(ws, r, _c, money(row["msrp"]), right); _c += 1
        body_cell(ws, r, _c, "CFP" if (row["call_for_price"] and not row["price"]) else money(row["price"]), right); _c += 1
        dv = row["delta"]
        dc = body_cell(ws, r, _c, ("$0" if dv == 0 else f"{'+' if dv>0 else '-'}${abs(dv):,.0f}") if dv is not None else "?",
                       right, delta_up_font if (dv or 0) > 0 else (delta_down_font if (dv or 0) < 0 else body_font)); _c += 1
        body_cell(ws, r, _c, f"{row['dom_note']}{row['dom']}" if row["dom"] else "?", center); _c += 1
        style_dealer_cell(ws.cell(row=r, column=_c, value=row["dealer"]), row["is_client"])
        if row["is_client"]:
            for c in range(1, _c):
                if ws.cell(row=r, column=c).fill.start_color.rgb in (None, "00000000"):
                    ws.cell(row=r, column=c).fill = alt_fill
        r += 1


import re as _re
_JARGON = ("claude browser", "javascript_tool", "chrome extension", "browser-jsfetch",
    "browser-srp", "jsfetch", "iife", "promise", "recheck_urls", "browser-extract", "snippet",
    "vinre", "get_page_text", "sitemap", "waf", "403", "tlsv", "tls handshake", "cascade",
    "the pane", "browser pane", "disposed frame", "unawaited", "top-level await", "cache this",
    "skill maintainer", "caching note", "skill cache", "urllib", "circuit breaker", "fragment.json",
    "cookie shell", "soft-block", "soft block", "user agent", "recommend updating skill",
    "for skill maintainer", "discovery for skill", "case-sensitive", "regex", "vdp", "json-ld",
    "call_for_price", "http", "parse", "await", "async", "extract", "redirect", "false-positive",
    "false positive", "landing page", "surface", "worked once", " dom ", "recheck")
_REPL = {"verified_zero": "confirmed none published", "needs_human_review": "needs manual review",
    "cfp": "call-for-price"}
# Replace internal vocabulary with client words. Deleting a token mid-sentence leaves a
# dangling article ("rendering the  --"), which a GM reads as a broken report (QA gate 2026-09-20).
_PLAIN = {r"\bVDPs\b": "vehicle pages", r"\bVDP\b": "vehicle page", r"\bjson-ld\b": "structured page data",
    r"\bprice-regex\b": "price reader", r"\bregex\b": "text matching",
    r"\bparser\b": "reader", r"\bparsed\b": "read", r"\bparse\b": "read",
    r"\bhitOf\(\)\s*(sitemap\s*)?matcher": "the sitemap matcher",
    r"\bhitOf\(\)": "the sitemap matcher",
    r"\brecheck_urls\.py returned 0 rows": "no previously tracked vehicle pages exist yet",
    r"\brecheck_urls\.py\b": "the re-check list",
    r"\bRECHECK vehicle page urls \(from state\)": "previously tracked vehicle pages",
    r"\bclients\.json\b": "the client configuration", r"\bfragment\.json\b": "the run file",
    r"\bin time-box\b|\bwithin time-box\b|\bin the time-box\b": "in the time available",
    r"\btime-box\b": "time available", r"\bfrom state\b": "from prior runs",
    r"\breturned 0 rows\b": "had no entries", r"\bjsonld\b|\bjson_ld\b": "structured page data",
    r"\bcall_for_price\b": "call-for-price", r"\bsee dealer\.notes\b": "see the dealer note above",
    r"\bis an search results page": "is a search results page",
    r"\btext matching-extracted\b": "text matching picked up", r"\bmsrp\b": "MSRP",
    r"\bSRP\b": "search results page", r"\bbanner[ _]das[ _]mismatch\b": "Due at signing mismatch",
    r"\brecheck VINs soft-redirected to /used-vehicles/ \(confirmed gone\)":
        "previously listed vehicles are no longer on the website (their pages now send visitors to used inventory)",
    r"\bsoft-redirected\b": "now send visitors elsewhere",
    r"\bLease banner cards\b": "Lease offer banners", r"\bnot distinguished\b": "could not be told apart",
    r"\bOffer modal disclaimers\b": "Offer pop-up disclaimers",
    r"/promotions/new/bmw-promotions\.htm empty body\b": "specials page was blank",
    r"\bempty body\b": "blank page",
    r"\babridged in fragment \(full text on source page\)": "shortened here; full text is on the store's specials page",
    r"\bin fragment\b": "in this report",
    r"\bcached html\b": "the saved copy of the page",
    r"\bthe server agent's\b": "an earlier pass of this report's",
    r"\bthis agent\b|\bthe delist engine\b": "this report",
    r"\bminimum-viable rows\b": "records with no price captured",
    r"\bWAF[- ]blocked\b": "blocked by the site's bot protection",
    r"\bpre-generated by the re-check list\b": "taken from prior runs",
    r"\bbrowser-search results page\b": "the live search results page"}
_FLAG_LABELS = {"DAS_UNKNOWN": "Due-at-signing not published", "LOW_MILEAGE": "Low mileage allowance",
    "price_text_mismatch": "Banner and disclaimer disagree", "disclaimer_not_captured": "Disclaimer not captured",
    "PAST_END_DATE": "Offer end date has passed"}

def flags_text(raw):
    """Pipe-delimited flag codes render as 'LOW_MILEAGEIprice_text_mismatch' in Excel.
    Emit comma-separated human labels instead (QA gate 2026-09-06)."""
    def label(f):
        if f in _FLAG_LABELS:
            return _FLAG_LABELS[f]
        if f.upper() == f and "_" in f:          # SCREAMING_CASE token
            f = f.replace("_", " ").capitalize()
        else:
            f = f.replace("_", " ")
            f = f[:1].upper() + f[1:]            # keep interior case: "West BC", not "west bc"
        f = _re.sub(r"(?i)^banner das mismatch", "Due at signing mismatch", f)
        f = _re.sub(r"(?i)^stale offer date", "Expired offer", f)
        # strip trailing internal program codes (e.g. "... Bonus Cash WELTM")
        return _re.sub(r"\s+[A-Z0-9]{4,}$", "", f).strip()
    parts = [f for f in str(raw or "").split("|") if f.strip()]
    return ", ".join(label(f) for f in parts)

def sample_depth_text(a):
    """State the ACTUAL sample depth. A flat '3-4 per model per dealer' was false for
    the client store, which is sampled far deeper (QA gate 2026-09-06)."""
    depth = (a.get("meta", {}) or {}).get("sample_depth") or {}
    if not depth:
        return "sample depth varies by dealer"
    per = []
    for dl, models in depth.items():
        if not models:
            continue
        lo, hi = min(models.values()), max(models.values())
        per.append(f"{dl} {lo}" if lo == hi else f"{dl} {lo}-{hi}")
    return "units per tracked model: " + "; ".join(per) if per else "sample depth varies by dealer"


def _claims_confirmed_zero(raw, kind):
    """True only for a POSITIVE verified-zero claim scoped to this offer type.

    A plain substring test is negation-blind: crawl notes routinely say
    "NOT claiming verified_zero", which the old test read as a confirmed zero and
    printed to the GM "no published offers, confirmed on site" for a page that
    never rendered (QA gate pass 2, 2026-09-06).
    """
    NEG = _re.compile(r"\b(?:not|never|cannot|can't|couldn't|could not|unable|un)\b[^.]*?"
                      r"(?:verified_zero|confirmed none)")
    for sent in _re.split(r"[.;|]", raw or ""):
        t = sent.lower()
        if "verified_zero" not in t and "confirmed none" not in t:
            continue
        if NEG.search(t):
            continue          # explicit negation: this is NOT a confirmed zero
        other = "finance" if kind == "lease" else "lease"
        if other in t and kind not in t:
            continue          # the claim is scoped to the other offer type
        return True
    return False


def _mentions_unread(raw, kind):
    """A needs-review note counts against THIS offer type only when it is either
    unscoped or explicitly about this type."""
    for sent in _re.split(r"[.;|]", raw or ""):
        t = sent.lower()
        if not any(k in t for k in ("needs_human_review", "needs manual review",
                                    "not claiming verified_zero", "could not confirm")):
            continue
        other = "finance" if kind == "lease" else "lease"
        if other in t and kind not in t:
            continue
        return True
    return False


def _updating_stub(raw, kind):
    """True when the store's own specials page said it is being updated. That is a
    third state, neither a verified zero nor an unread page, and the tabs must all
    say the same thing about it (QA gate 2026-10-05: one tab said 'confirmed on
    site', another 'not positively confirmed')."""
    for sent in _re.split(r"[.;|]", raw or ""):
        t = sent.lower()
        if "updating" not in t:
            continue
        other = "finance" if kind == "lease" else "lease"
        if other in t and kind not in t:
            continue
        return True
    return False


def _updating_sentence(name, word, a):
    return (f"{name}: the store's specials page said it is currently updating its offers when "
            f"checked on {a['meta']['run_date']}; no {word} offers were published at the time of this check.")


def _dealer_coverage(a, kind):
    """Dealers whose lease/finance coverage is UNVERIFIED this run, vs those whose
    zero was positively confirmed. Silence about an unread page reads to a GM as
    'this dealer publishes nothing' (QA gate 2026-09-06)."""
    unverified, confirmed, partial = [], [], []
    key = "lease_rows" if kind == "lease" else "finance_rows"
    for dl in a["meta"]["dealers"]:
        name = dl.get("name", "")
        n = sum(1 for r in a.get(key, []) if r.get("dealer") == name)
        raw = (dl.get("notes", "") or "")
        if dl.get("status") == "failed":
            unverified.append(name)
        elif n > 0:
            # Rows captured, but a partial crawl means more may exist unread. This is
            # a DIFFERENT statement from "nothing captured" and needs its own sentence.
            if dl.get("status") == "partial" and _mentions_unread(raw, kind):
                partial.append(name)
            continue
        elif _updating_stub(raw, kind):
            confirmed.append(name)          # worded via _updating_sentence below
        elif _claims_confirmed_zero(raw, kind):
            confirmed.append(name)
        else:
            unverified.append(name)       # zero rows and no positive confirmation
    return unverified, confirmed, partial


def _join(names):
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def coverage_caveat(a, kind):
    word = "lease" if kind == "lease" else "finance"
    unv, conf, part = _dealer_coverage(a, kind)
    bits = []
    if part:
        bits.append(f"COVERAGE: {_join(part)} could only be read in part this run, so the "
                    f"{word} offers shown for them are what we could reach, not necessarily all "
                    f"they publish.")
    if unv:
        bits.append(f"{'Also, no' if part else 'COVERAGE: no'} {word} offers were captured for "
                    f"{_join(unv)} this run, and their absence was NOT positively confirmed on site. "
                    f"Treat those blanks as unverified, not as proof the store publishes nothing.")
    _upd = {dl.get("name", ""): dl for dl in a["meta"]["dealers"]
            if _updating_stub(dl.get("notes", "") or "", kind)}
    for n in [c for c in conf if c in _upd]:
        bits.append(_updating_sentence(n, word, a))
    conf = [c for c in conf if c not in _upd]
    if conf:
        bits.append(f"{_join(conf)}: no published {word} offers, confirmed on site.")
    return " ".join(bits)


def client_note(text):
    """Strip crawl/tool/code jargon from a dealer note so the Run Log reads for a GM."""
    if not text:
        return ""
    parts = _re.split(r'(?<=[.;])\s+|\s+\|\s+', str(text))
    keep = [p.strip() for p in parts if not any(j in p.lower() for j in _JARGON)]
    out = " ".join(x for x in keep if x)
    for k, v in _REPL.items():
        out = _re.sub(k, v, out, flags=_re.I)
    return _re.sub(r'\s{2,}', ' ', out).strip(" .;|")

def client_text(t):
    """Plain-language pass for free text shown to the client (offer conditions).
    needs_human_review was reaching the Finance tab verbatim."""
    out = str(t or "")
    for _p, _r in _PLAIN.items():
        out = _re.sub(_p, _r, out, flags=_re.I)
    for _p, _r in _REPL.items():
        out = _re.sub(_p, _r, out, flags=_re.I)
    out = _re.sub(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+){1,}\b",
                  lambda m: m.group(0).replace("_", " "), out)
    return _re.sub(r"\s{2,}", " ", out).strip()


def client_method(mth):
    m = (mth or "").lower()
    if "recheck" in m:
        return "Website re-check"
    return "Website review"

def _hedged(p):
    # "Dealer.com (confirmed, not Dealer Inspire as previously suspected)" is a
    # CONFIRMED platform. Matching a bare "suspected" anywhere printed it as
    # "(unconfirmed)", contradicting the same sheet's own note (QA MAJOR 6).
    s = (p or "").lower()
    if "unconfirmed" in s:
        return True
    if "confirmed" in s:
        return False
    return "suspected" in s or "?" in s


def client_platform(p):
    base = (p or "").split("(")[0].strip()
    if not base or base.lower() in ("unknown", "unknown-dom", "n/a"):
        return "Not identified"
    if any(j in base.lower() for j in _JARGON):
        return "Not identified"
    # Keep the hedge: the source said "suspected", the sheet must not say it flatly.
    return base + " (unconfirmed)" if _hedged(p) else base

def dealer_status_note(a, dl):
    """A short, GM-facing status derived from structured data, not from crawl logs."""
    name = dl.get("name", "")
    veh = sum(1 for v in a.get("vin_rows", []) if v.get("dealer") == name)
    lease = sum(1 for r in a.get("lease_rows", []) if r.get("dealer") == name)
    fin = sum(1 for r in a.get("finance_rows", []) if r.get("dealer") == name)
    stmap = {"ok": "Website reviewed", "partial": "Website partly reviewed", "failed": "Website could not be read"}
    st = dl.get("status", "ok")
    n_pmt = sum(1 for r in a.get("lease_rows", []) if r.get("dealer") == name and r.get("pmt"))
    _lease_txt = (f"{lease} advertised offer(s) ({n_pmt} monthly lease payment(s))"
                  if lease != n_pmt else f"{lease} lease offer(s)")
    parts = [f"{stmap.get(st, st.title())}: {veh} unit(s) sampled, {_lease_txt} "
             f"and {fin} finance offer(s) captured."]
    raw = (dl.get("notes", "") or "").lower()
    # Distinguish a CONFIRMED zero from an unread page, per offer type. Rendering
    # both as "0 captured" erases the difference a GM needs (QA gate 2026-09-06).
    for label, n in (("lease", lease), ("finance", fin)):
        confirmed_zero = _claims_confirmed_zero(dl.get("notes", "") or "", label)
        unread = _mentions_unread(dl.get("notes", "") or "", label) or st == "partial"
        if n == 0 and _updating_stub(dl.get("notes", "") or "", label):
            _s = _updating_sentence("This store", label, a).replace("This store: the", "The")
            _both = (label == "finance" and lease == 0
                     and _updating_stub(dl.get("notes", "") or "", "lease"))
            if _both:
                # One page, one sentence: lease and finance share it (QA 2026-10-05).
                parts[-1] = parts[-1].replace("no lease offers", "no lease or finance offers")
            else:
                parts.append(_s)
        elif n == 0 and confirmed_zero and not unread:
            parts.append(f"No published {label} offers, confirmed on site.")
        elif n == 0:
            # Zero rows with no positive confirmation is NOT a confirmed zero.
            parts.append(f"No {label} offers were captured for this store this run, and their absence "
                         f"was not positively confirmed on site; treat as unverified, not as zero.")
    if "pre-owned" in raw or "preowned" in raw:
        parts.append("Note: this site labels its new-vehicle lease offers 'Pre-Owned'; "
                     "recorded exactly as published.")
    myrows = [r for r in a.get("lease_rows", []) + a.get("finance_rows", []) if r.get("dealer") == name]
    fl = " ".join((r.get("flags", "") or "") for r in myrows).lower()
    tail = []
    if "past" in fl or "aug31" in fl or "expired" in fl:
        tail.append("an advertised offer shows an expired (past) end date")
    if "mismatch" in fl or " vs " in fl:
        _mm = [r for r in myrows if "mismatch" in (r.get("flags", "") or "").lower()]
        _blob = " ".join(str(r.get("parse_note", "")) for r in _mm)
        _f = []
        if _re.search(r"due at signing|\bdas\b", _blob, _re.I):
            _f.append("the due-at-signing amount")
        if _re.search(r"/mo|per month|payment", _blob, _re.I):
            _f.append("the monthly payment")
        _field = " and ".join(_f) if _f else "the advertised figure"
        _who = "; ".join(f"{r.get('model','')} {r.get('trim','')}".strip() for r in _mm[:3])
        _recorded_headline = bool(_re.search(r"recorded\s+(headline|banner)", _blob, _re.I))
        _carry = ("this report carries the HEADLINE figure; the fine print on that unit reads lower, "
                  "so treat the advertised payment as unconfirmed"
                  if _recorded_headline else
                  "this report uses the fine-print figure; the headline and the fine print must agree, "
                  "so the banner needs correcting")
        tail.append(f"a banner headline and its fine print disagree on {_field}" +
                    (f" ({_who}): {_carry}" if _who else ""))
    if tail:
        parts.append("Flag: " + "; ".join(tail) + ".")
    return " ".join(parts)

def build_runlog(ws, a):
    m = a["meta"]
    headers = ["Dealer", "Role", "Platform", "Review Method", "Status", "Pages Read", "Notes"]
    widths = [24, 11, 18, 22, 12, 8, 60]
    add_masthead(ws, "Run Log", m["run_date"], len(headers))
    header_row(ws, 4, headers, widths)
    r = 5
    for dl in m["dealers"]:
        style_dealer_cell(ws.cell(row=r, column=1, value=dl["name"]), 1 if dl.get("role") == "client" else 0)
        body_cell(ws, r, 2, dl.get("role", ""))
        body_cell(ws, r, 3, client_platform(dl.get("platform", "")))
        body_cell(ws, r, 4, client_method(dl.get("crawl_method", "")))
        body_cell(ws, r, 5, dl.get("status", ""), center,
                  body_bold if dl.get("status") != "ok" else body_font)
        body_cell(ws, r, 6, dl.get("pages_crawled", 0), center)
        _note = dealer_status_note(a, dl)
        body_cell(ws, r, 7, _note)
        ws.row_dimensions[r].height = max(16, 14 * (2 + len(_note) // 58))
        r += 1
    r += 1
    ws.cell(row=r, column=1, value="Errors this run").font = label_font
    r += 1
    # Raw crawl errors are internal engineering hiccups (browser/tool/parse mechanics), not
    # client data-quality issues. Drop any that reference internal machinery wholesale; real
    # coverage/verification issues are already carried per-dealer in the Notes column.
    _raw_errs = [str(e) for e in (a.get("errors") or [])]
    # Data-quality notes are for the client even if they mention machinery; only pure
    # tooling chatter is dropped. Printing "None" while silently discarding a sourced
    # data-quality warning is worse than printing it awkwardly (QA 2026-09-06).
    _KEEP = ("msrp", "price", "offer", "disclaim", "delist", "identical", "data-quality",
             "data quality", "trim", "banner", "specials", "lease", "finance", "apr",
             "still listed", "still live", "confirmed", "vin", "inventory")
    _errs, _dropped = [], 0
    for e in _raw_errs:
        low = e.lower()
        if any(j in low for j in _JARGON) and not any(k in low for k in _KEEP):
            _dropped += 1
            continue
        cleaned = e
        # Agents label each error with a snake_case key, often AFTER the dealer name
        # ("Nissan of Irvine: recheck_reconciliation: ..."). Strip the key wherever it
        # sits, plus file names and raw query strings (QA gate 2026-09-20, pass 2).
        cleaned = _re.sub(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+){1,}\s*:\s*", "", cleaned)
        # Only internal artefacts. A dealer page name like "wrangler-inventory.htm" is
        # meaningful to a GM, and stripping it left an empty quoted string.
        cleaned = _re.sub(r"\s*\b[\w./-]+\.(?:json|py|js|xml)\b", "", cleaned)
        cleaned = _re.sub(r"\s*/\S*\?\S+", "", cleaned)
        for _pat, _rep in _PLAIN.items():
            cleaned = _re.sub(_pat, _rep, cleaned, flags=_re.I)
        # Drop ONLY clauses that are pure internal upkeep. Deleting a whole sentence
        # because it mentions a tool destroyed a real competitor APR finding and left
        # dangling subjects behind (QA pass 2, 2026-09-20). Keep the fact, cut the ticket.
        cleaned = _re.sub(r"[^.;]*\b(?:recommend(?:ing|s|ed)?|suggest(?:ing|s|ed)?)\b[^.;]*[.;]?",
                          "", cleaned, flags=_re.I)
        cleaned = _re.sub(r"\s*\((?:for |note for )?(?:the )?skill maintainer[^)]*\)", "", cleaned, flags=_re.I)
        for k, v in _REPL.items():
            cleaned = _re.sub(k, v, cleaned, flags=_re.I)
        cleaned = _re.sub(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+){1,}\b",
                          lambda m: m.group(0).replace("_", " "), cleaned)
        cleaned = _re.sub(r"\ban (?=[bcdfghjklmnpqrstvwxyz])", "a ", cleaned)
        cleaned = _re.sub(r"\ba (?=[aeiou])", "an ", cleaned)
        cleaned = _re.sub(r"\s{2,}", " ", cleaned)
        cleaned = _re.sub(r"\s+([.;,])", r"\1", cleaned).strip(" .;|,-")
        # A bullet glyph with no sentence after it reads as a broken report.
        if len(cleaned) < 12:
            _dropped += 1
            continue
        _errs.append(cleaned + "." if not cleaned.endswith(".") else cleaned)
    if not _errs:
        _errs = ([f"No client-facing data issues. {_dropped} internal crawl note(s) omitted."]
                 if _dropped else ["None"])
    for e in _errs:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(headers))
        ec = ws.cell(row=r, column=1, value=depluralize(f"•  {e}"))
        ec.font = body_font; ec.alignment = left
        ws.row_dimensions[r].height = max(16, 14 * (1 + len(e) // 120) + 8)
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
    # Fit every sheet to one page wide so PDF export / render gate never splits
    # columns across pages (the source of 30-page renders for 7 tabs)
    from openpyxl.worksheet.properties import PageSetupProperties
    for ws in wb.worksheets:
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
        # Every data tab puts its header on row 4. Repeat it on printed pages and
        # freeze it on screen, so a grid of numbers is never label-less (QA gate).
        if ws.title != "Summary":
            _hr = getattr(ws, "_dcq_header_row", 4)
            ws.print_title_rows = f"{_hr}:{_hr}"
            ws.freeze_panes = f"A{_hr + 1}"
    out = os.path.join(out_dir, f"DigitalCLIQ_Inventory_Pulse_{m['client_code']}_{m['run_date']}.xlsx")
    wb.save(out)
    print(out)


if __name__ == "__main__":
    main()
