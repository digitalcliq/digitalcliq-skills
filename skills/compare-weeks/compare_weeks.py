#!/usr/bin/env python3
"""
Compare Weeks — Weekly CRM Lead Comparison PDF Generator (v2, HTML pipeline)
Developed by DigitalCLIQ — Digital Strategy & Development

Rebuilt per Resources/design-system/Design-System.md: hand-authored HTML+CSS
rendered to PDF using the canonical component library (canonical dark cover,
stat cards, callout bars, branded tables, numbered list cards, ghost numerals,
running furniture). NEVER reportlab for narrative reports — it cannot hit the
spec (Design-System §4).

Pipeline: WeasyPrint if importable, else Chrome headless --print-to-pdf
(the design-system documented fallback). Fonts (Dosis + Roboto Slab) are
embedded via @font-face from the vault archive so rendering is self-contained.
Missing fonts or logos fail LOUDLY — never a silent substitution.

Interface (unchanged from v1):
    python3 compare_weeks.py <analysis.json>     # or JSON on stdin
Data keys: dealership, week1_label, week2_label, week1_short, week2_short,
kpis, summary_bullets, key_movers, mover_insights, ga4_channels,
ga4_landing_pages, ga4_insights, bdc_metrics, bdc_insights, concerns,
recommendations, full_comparison, output_path (default outputs/comparison.pdf).
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from math import ceil

VAULT = "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ"
FONT_DIR = f"{VAULT}/Resources/brand-assets/fonts"
LOGO_WHITE = f"{VAULT}/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png"
LOGO_COLOR = f"{VAULT}/Resources/brand-assets/classic-digital-cliq-logo-solid-1000px-wide copy.png"

# Usable content height per interior page (850x1100 page, minus padding and
# running furniture). Deliberately conservative: an extra page beats overflow.
PAGE_BUDGET = 905
CONTENT_W = 722  # 850 - 2x64 padding

CURSOR_SVG = ('<svg class="tick" viewBox="0 0 100 100"><path d="M12 4 L88 58 '
              'L52 62 L68 96 L54 100 L40 68 L14 88 Z" fill="#405FAB"/></svg>')


# ── text helpers ──────────────────────────────────────────────
def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def rich(s):
    """Escape, but allow simple <b>/<i> emphasis that analysis text may carry
    (v1's reportlab Paragraph parsed these too — parity)."""
    out = esc(s)
    for tag in ("b", "i"):
        out = out.replace(f"&lt;{tag}&gt;", f"<{tag}>").replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    return out


def est_lines(text, chars_per_line):
    return max(1, ceil(len(str(text)) / max(chars_per_line, 8)))


# ── component builders (Design-System library) ────────────────
def sec_head(num, eyebrow, title):
    return (f'<div class="sec-head"><div class="ghost">{esc(num)}</div>'
            f'<div class="eyebrow">{esc(eyebrow)}</div>'
            f'<h2>{esc(title)}</h2><div class="rule"></div></div>')


def kpi_cards(kpis):
    """Stat cards: Dosis ExtraBold number in Sky Blue, label caption, delta
    line. Palette-only status coding: Sky Blue = up/strong, Warm Grey =
    down/flat. The delta TEXT (+/-) carries the meaning; color reinforces."""
    cards = []
    for k in kpis:
        direction = k.get("direction", "flat")
        cls = "up" if direction == "up" else "down" if direction == "down" else "flat"
        cards.append(
            f'<div class="stat">{CURSOR_SVG}'
            f'<div class="num">{esc(k.get("value", ""))}</div>'
            f'<div class="cap">{esc(k.get("label", ""))}</div>'
            f'<div class="delta {cls}">{esc(k.get("delta", ""))}</div></div>')
    return f'<div class="statgrid">{"".join(cards)}</div>'


def checklist(items):
    rows = "".join(
        f'<div class="check"><span class="glyph">&#10003;</span>'
        f'<span class="txt">{rich(t)}</span></div>' for t in items)
    return f'<div class="checks">{rows}</div>'


INSIGHT_KINDS = {
    # kind: (css class, TEXT label — the label carries the meaning, not color)
    "info": ("info", ""),
    "success": ("success", "WIN: "),
    "alert": ("alert", "ALERT: "),
    "warning": ("warning", "WATCH: "),
}


def insight_box(text, kind="info"):
    cls, label = INSIGHT_KINDS.get(kind, INSIGHT_KINDS["info"])
    body = rich(text)
    if label and not str(text).lstrip().upper().startswith(label.rstrip(": ")):
        body = f"<b>{label}</b>{body}"
    return f'<div class="callout {cls}">{body}</div>'


def minihead(text):
    return f'<div class="minihead">{esc(text)}</div>'


def table_html(headers, widths, rows, continued=False):
    total = sum(widths)
    cols = "".join(f'<col style="width:{w / total * 100:.1f}%">' for w in widths)
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = []
    for r in rows:
        cells = "".join(f"<td>{rich(c)}</td>" for c in r)
        body.append(f"<tr>{cells}</tr>")
    cont = ('<div class="continued">&#8618; table continued</div>' if continued else "")
    return (f'{cont}<table class="data"><colgroup>{cols}</colgroup>'
            f'<tr>{head}</tr>{"".join(body)}</table>')


def furniture(dealership, page_no, total):
    return (f'<div class="furniture-top">'
            f'<span class="doctitle">Weekly Lead Comparison &middot; {esc(dealership)}</span>'
            f'<img src="file://{LOGO_COLOR}" alt="DigitalCLIQ"></div>'
            f'<div class="furniture-bot">'
            f'<span>DigitalCLIQ &middot; Digital Strategy &amp; Development</span>'
            f'<span>Page {page_no} of {total}</span></div>')


# ── height estimation ─────────────────────────────────────────
def h_callout(text):
    return 30 + est_lines(text, 90) * 19 + 12


def h_check(text):
    return 12 + est_lines(text, 84) * 18


def h_numcard(text):
    return 30 + est_lines(text, 82) * 18


def row_height(row, widths):
    total = sum(widths)
    lines = 1
    for cell, w in zip(row, widths):
        cap = int((w / total) * CONTENT_W / 6.2)  # ~11px font avg glyph width
        lines = max(lines, est_lines(cell, cap))
    return 14 + lines * 15


# ── flow paginator ────────────────────────────────────────────
class Paginator:
    """Greedy top-down flow of estimated-height blocks into fixed-height
    interior pages, so dynamic table sizes can never overflow the page box."""

    def __init__(self):
        self.pages = [[]]
        self.used = 0

    def newpage(self):
        if self.pages[-1]:
            self.pages.append([])
            self.used = 0

    def add(self, html, h, keep_with=0):
        """Add a block. keep_with = min height of the following content that
        must share the page (prevents orphaned section headers)."""
        if self.used + h + keep_with > PAGE_BUDGET and self.pages[-1]:
            self.newpage()
        self.pages[-1].append(html)
        self.used += h

    def add_table(self, headers, widths, rows, title=None):
        """Add a branded table, splitting rows across pages when needed."""
        first = True
        remaining = list(rows)
        while remaining:
            overhead = 36 + 16 + (30 if (title and first) else 0) + (0 if first else 22)
            avail = PAGE_BUDGET - self.used
            chunk, h_acc = [], overhead
            for r in remaining:
                rh = row_height(r, widths)
                if h_acc + rh > avail:
                    break
                h_acc += rh
                chunk.append(r)
            # Not enough room for a meaningful chunk: start a fresh page.
            if len(chunk) < min(3, len(remaining)) and self.pages[-1] and self.used > 0:
                self.newpage()
                continue
            if not chunk:  # single pathological row taller than a page: clamp
                chunk = remaining[:1]
                h_acc = PAGE_BUDGET
            html = ""
            if title and first:
                html += minihead(title)
            html += table_html(headers, widths, chunk, continued=not first)
            self.pages[-1].append(html)
            self.used += h_acc
            remaining = remaining[len(chunk):]
            first = False


# ── report assembly ───────────────────────────────────────────
def build_html(data):
    dealership = data["dealership"]
    week1_label = data["week1_label"]
    week2_label = data["week2_label"]
    w1 = data.get("week1_short", "Wk 1")
    w2 = data.get("week2_short", "Wk 2")
    report_date = datetime.now().strftime("%B %d, %Y")

    pg = Paginator()
    sec_n = 0

    def section(eyebrow, title, first_block_h=140):
        nonlocal sec_n
        sec_n += 1
        pg.add(sec_head(f"{sec_n:02d}", eyebrow, title), 125, keep_with=first_block_h)

    # 01 · Executive Summary
    section("Week-over-week headline metrics", "Executive Summary", 170)
    kpis = data.get("kpis", [])
    if kpis:
        pg.add(kpi_cards(kpis), 165 * ceil(len(kpis) / 4))
    bullets = data.get("summary_bullets", [])
    if bullets:
        pg.add(checklist(bullets), sum(h_check(b) for b in bullets) + 14)

    # 02 · Key Movers
    section(f"Lead sources with the biggest changes, {w1} vs {w2}", "Key Movers")
    if data.get("key_movers"):
        headers = ["Source", f"{w1} Leads", f"{w2} Leads", "Change",
                   f"{w1} Sold", f"{w2} Sold", "Notes"]
        widths = [1.6, 0.65, 0.65, 0.6, 0.6, 0.6, 2.6]
        pg.add_table(headers, widths, data["key_movers"])
    for ins in data.get("mover_insights", []):
        pg.add(insight_box(ins["text"], ins.get("type", "info")), h_callout(ins["text"]))

    # 03 · GA4 Website Analytics
    section("Traffic & engagement for the comparison period", "GA4 Website Analytics")
    if data.get("ga4_channels"):
        headers = ["Channel", "Sessions", "% Share", "Engaged", "Eng Rate",
                   "Avg Time", "Key Events"]
        widths = [1.2, 0.8, 0.7, 0.8, 0.7, 0.7, 0.8]
        pg.add_table(headers, widths, data["ga4_channels"])
    if data.get("ga4_landing_pages"):
        headers = ["Landing Page", "Sessions", "Avg Time", "Key Events", "Key Event Rate"]
        widths = [2.5, 0.9, 0.9, 1.0, 1.0]
        pg.add_table(headers, widths, data["ga4_landing_pages"], title="Top Landing Pages")
    for ins in data.get("ga4_insights", []):
        pg.add(insight_box(ins["text"], ins.get("type", "info")), h_callout(ins["text"]))

    # 04 · BDC Performance
    section("Outreach and response metrics comparison", "BDC Performance")
    if data.get("bdc_metrics"):
        headers = ["Metric", w1, w2, "Change"]
        widths = [2.5, 1.5, 1.5, 1.3]
        pg.add_table(headers, widths, data["bdc_metrics"])
    for ins in data.get("bdc_insights", []):
        pg.add(insight_box(ins["text"], ins.get("type", "info")), h_callout(ins["text"]))

    # 05 · Concerns & Red Flags (optional, parity with v1)
    if data.get("concerns"):
        section("Items requiring immediate attention", "Concerns & Red Flags")
        for c in data["concerns"]:
            pg.add(insight_box(c, "alert"), h_callout(c))

    # 06 · Strategic Recommendations
    section("Suggested next steps based on the data", "Strategic Recommendations")
    for i, rec in enumerate(data.get("recommendations", []), 1):
        pg.add(f'<div class="numcard"><div class="n">{i}</div><p>{rich(rec)}</p></div>',
               h_numcard(rec))

    # Appendix · Full Source Comparison (optional, always on a fresh page — v1 parity)
    if data.get("full_comparison"):
        pg.newpage()
        sec_n += 1
        pg.add(sec_head("A", "Appendix · every lead source side by side",
                        "Full Source Comparison"), 125, keep_with=140)
        headers = ["Type", "Source", f"{w1} Total", f"{w2} Total",
                   f"{w1} Good", f"{w2} Good", f"{w1} Sold", f"{w2} Sold"]
        widths = [0.9, 2.0, 0.65, 0.65, 0.65, 0.65, 0.6, 0.6]
        pg.add_table(headers, widths, data["full_comparison"])
        pg.add(f'<div class="srcline">Source: {esc(dealership)} CRM weekly lead exports '
               f'&middot; {esc(week1_label)} and {esc(week2_label)}</div>', 30)

    # ── wrap interior pages with running furniture ────────────
    total_pages = len(pg.pages)
    interiors = []
    for i, blocks in enumerate(pg.pages, 1):
        interiors.append(f'<div class="page interior">'
                         f'{furniture(dealership, i, total_pages)}'
                         f'{"".join(blocks)}</div>')

    # ── canonical cover (Design-System §2 / templates/cover-portrait.html) ──
    cover = f'''<div class="page cover">
      <img class="logo" src="file://{LOGO_WHITE}" alt="DigitalCLIQ">
      <div class="block">
        <div class="eyebrow">Weekly CRM Lead Intelligence</div>
        <h1>Weekly Lead<br>Comparison<br><span class="accent">Report.</span></h1>
        <div class="rule"></div>
        <div class="subtitle">{esc(dealership)} week over week: {esc(week1_label)} versus
        {esc(week2_label)}, with GA4 website analytics layered in to show what changed,
        why, and what to do next.</div>
      </div>
      <svg class="cursor" viewBox="0 0 100 100"><path d="M12 4 L88 58 L52 62 L68 96 L54 100 L40 68 L14 88 Z" fill="#000" opacity="0.9" transform="rotate(-12 50 50)"/></svg>
      <div class="prepared"><b>Prepared by DigitalCLIQ.</b> &nbsp;Digital Strategy &amp; Development. &nbsp;{esc(dealership)}. &nbsp;{esc(report_date)}</div>
      <div class="pillars">Innovative &nbsp;|&nbsp; Clean &nbsp;|&nbsp; Minimalist &nbsp;|&nbsp; Bold &nbsp;|&nbsp; Resourceful</div>
    </div>'''

    body = cover + "".join(interiors)
    return _SHELL.replace("{{FONTS}}", _font_faces()).replace("{{BODY}}", body)


def _font_faces():
    faces = [
        ("Dosis", "Dosis-Regular.ttf", 400),
        ("Dosis", "Dosis-Medium.ttf", 500),
        ("Dosis", "Dosis-SemiBold.ttf", 600),
        ("Dosis", "Dosis-Bold.ttf", 700),
        ("Dosis", "Dosis-ExtraBold.ttf", 800),
        ("Roboto Slab", "Roboto-Slab-Regular.ttf", 400),
        ("Roboto Slab", "Roboto-Slab-Bold.ttf", 700),
    ]
    out = []
    for fam, fname, weight in faces:
        path = f"{FONT_DIR}/{fname}"
        if not os.path.exists(path):
            raise RuntimeError(
                f"Brand font missing: {path!r}. Install from "
                f"Resources/brand-assets/fonts/ before generating. "
                f"Falling back to Helvetica/Arial is a Visual-QA FAIL.")
        out.append(f"@font-face{{font-family:'{fam}';src:url('file://{path}');"
                   f"font-weight:{weight};font-style:normal;}}")
    return "\n".join(out)


_SHELL = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
@page { size: 850px 1100px; margin: 0; }
{{FONTS}}
:root{
  --digital-blue:#405FAB; --sky-blue:#6B9DD4; --warm-grey:#949592; --white:#FFFFFF;
  --navy-deep:#070A15; --navy-base:#10162A; --navy-lift:#151E37; --card-navy:#131B30;
  --orb-glow:#243562; --border-blue:rgba(107,157,212,0.22); --body-on-dark:#C9D5EA; --muted-on-dark:#8FA0C0;
  --callout-tint:#EDF2F9; --card-white:#FBFBFD; --card-border:#D8E1F0; --tile-blue:#2E4780;
}
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:'Roboto Slab',serif;color:#000;-webkit-print-color-adjust:exact;print-color-adjust:exact;}
.page{width:850px;height:1100px;position:relative;overflow:hidden;page-break-after:always;}
.page:last-child{page-break-after:auto;}

/* Canonical dark cover (Design-System §2) */
.cover{
  background:
    radial-gradient(ellipse 420px 320px at 85% 12%, rgba(36,53,98,0.85), transparent 70%),
    radial-gradient(ellipse 500px 380px at 8% 88%, rgba(36,53,98,0.55), transparent 70%),
    linear-gradient(180deg, var(--navy-deep) 0%, var(--navy-base) 45%, var(--navy-lift) 100%);
  font-family:'Dosis',sans-serif;color:#fff;
}
.cover .logo{position:absolute;top:64px;left:70px;width:115px;}
.cover .block{position:absolute;left:70px;top:330px;width:640px;}
.cover .eyebrow{font-weight:600;font-size:15px;letter-spacing:0.24em;text-transform:uppercase;color:var(--sky-blue);margin-bottom:24px;}
.cover h1{font-weight:800;font-size:74px;line-height:1.03;text-transform:uppercase;letter-spacing:0.01em;}
.cover h1 .accent{color:var(--sky-blue);}
.cover .rule{width:64px;height:4px;background:var(--sky-blue);margin:28px 0 26px;}
.cover .subtitle{font-family:'Roboto Slab',serif;font-weight:400;font-size:19px;line-height:1.55;color:var(--body-on-dark);max-width:560px;}
.cover .cursor{position:absolute;right:105px;bottom:190px;width:85px;height:85px;}
.cover .prepared{position:absolute;left:70px;bottom:110px;font-family:'Roboto Slab',serif;font-size:14px;color:var(--muted-on-dark);max-width:710px;}
.cover .prepared b{color:var(--body-on-dark);font-weight:400;}
.cover .pillars{position:absolute;bottom:52px;width:100%;text-align:center;font-weight:600;font-size:12px;letter-spacing:0.32em;text-transform:uppercase;color:var(--muted-on-dark);}

/* Interior pages (light) + running furniture */
.interior{background:var(--white);padding:60px 64px 60px;}
.furniture-top{position:absolute;top:0;left:64px;right:64px;height:44px;border-bottom:2px solid var(--card-border);display:flex;align-items:center;justify-content:space-between;}
.furniture-top .doctitle{font-family:'Dosis',sans-serif;font-weight:600;font-size:10.5px;letter-spacing:0.18em;text-transform:uppercase;color:var(--warm-grey);}
.furniture-top img{height:17px;}
.furniture-bot{position:absolute;bottom:0;left:64px;right:64px;height:40px;border-top:2px solid var(--card-border);display:flex;align-items:center;justify-content:space-between;}
.furniture-bot span{font-family:'Dosis',sans-serif;font-weight:500;font-size:10.4px;letter-spacing:0.15em;text-transform:uppercase;color:var(--warm-grey);}

/* Section header: eyebrow / H2 / accent rule / ghost numeral */
.sec-head{position:relative;margin:20px 0 16px;}
.sec-head .eyebrow{font-family:'Dosis',sans-serif;font-weight:600;font-size:12.5px;letter-spacing:0.2em;text-transform:uppercase;color:var(--digital-blue);margin-bottom:8px;}
.sec-head h2{font-family:'Dosis',sans-serif;font-weight:700;font-size:33px;color:#000;line-height:1.08;}
.sec-head .rule{width:48px;height:3px;background:var(--sky-blue);margin-top:12px;}
.ghost{position:absolute;right:0;top:-14px;font-family:'Dosis',sans-serif;font-weight:800;font-size:135px;line-height:1;color:var(--digital-blue);opacity:0.07;}
.minihead{font-family:'Dosis',sans-serif;font-weight:700;font-size:13px;letter-spacing:0.14em;text-transform:uppercase;color:var(--tile-blue);margin:10px 0 4px;}
.continued{font-family:'Dosis',sans-serif;font-weight:600;font-size:10px;letter-spacing:0.16em;text-transform:uppercase;color:var(--warm-grey);margin:6px 0 2px;}
.srcline{font-family:'Dosis',sans-serif;font-weight:500;font-size:10px;letter-spacing:0.15em;text-transform:uppercase;color:var(--warm-grey);margin:4px 0 0 2px;}

/* Stat cards */
.statgrid{display:flex;flex-wrap:wrap;gap:14px;margin:16px 0;}
.stat{flex:1 1 calc(25% - 11px);min-width:150px;background:var(--card-white);border:1px solid var(--card-border);border-radius:12px;padding:15px 14px 12px;position:relative;}
.stat .num{font-family:'Dosis',sans-serif;font-weight:800;font-size:36px;line-height:1;color:var(--sky-blue);}
.stat .cap{font-size:11px;line-height:1.4;margin-top:7px;color:#000;}
.stat .delta{font-family:'Dosis',sans-serif;font-weight:700;font-size:13px;margin-top:7px;letter-spacing:0.04em;}
.stat .delta.up{color:var(--sky-blue);}
.stat .delta.down,.stat .delta.flat{color:var(--warm-grey);}
.tick{position:absolute;top:10px;right:10px;width:11px;height:11px;}

/* Checklist rows */
.checks{margin:6px 0 10px;}
.check{display:flex;gap:10px;align-items:flex-start;padding:5px 0;}
.check .glyph{flex:0 0 18px;height:18px;border-radius:5px;background:var(--digital-blue);color:#fff;font-size:11px;line-height:18px;text-align:center;font-family:'Dosis',sans-serif;font-weight:700;margin-top:1px;}
.check .txt{font-size:12px;line-height:1.5;color:#000;}

/* Branded data tables */
table.data{width:100%;border-collapse:collapse;margin:12px 0;border-radius:12px;overflow:hidden;table-layout:fixed;}
table.data th{background:var(--digital-blue);color:#fff;font-family:'Dosis',sans-serif;font-weight:600;font-size:11px;letter-spacing:0.05em;text-transform:uppercase;padding:8px 9px;text-align:left;}
table.data td{font-size:11px;line-height:1.35;padding:7px 9px;border-bottom:1px solid var(--card-border);vertical-align:top;overflow-wrap:break-word;}
table.data tr:nth-child(odd) td{background:var(--callout-tint);}
table.data td b{font-family:'Dosis',sans-serif;font-weight:700;color:var(--tile-blue);}

/* Callout bars — severity carried by TEXT labels; palette-only borders */
.callout{border-radius:0 12px 12px 0;padding:12px 16px;font-size:12px;line-height:1.55;margin:10px 0;}
.callout b{font-family:'Dosis',sans-serif;font-weight:700;font-size:12px;letter-spacing:0.06em;text-transform:uppercase;}
.callout.info{background:var(--callout-tint);border-left:3px solid var(--digital-blue);}
.callout.info b{color:var(--tile-blue);}
.callout.success{background:var(--callout-tint);border-left:3px solid var(--sky-blue);}
.callout.success b{color:var(--digital-blue);}
.callout.alert,.callout.warning{background:var(--card-white);border-left:3px solid var(--warm-grey);border-top:1px solid var(--card-border);border-right:1px solid var(--card-border);border-bottom:1px solid var(--card-border);}
.callout.alert b,.callout.warning b{color:var(--warm-grey);}

/* Numbered list cards (recommendations) */
.numcard{display:flex;gap:14px;align-items:flex-start;background:var(--card-white);border:1px solid var(--card-border);border-radius:12px;padding:12px 16px;margin:8px 0;}
.numcard .n{font-family:'Dosis',sans-serif;font-weight:700;font-size:22px;color:var(--digital-blue);line-height:1;min-width:26px;}
.numcard p{font-size:12px;line-height:1.5;color:#000;padding-top:3px;}
</style></head><body>
{{BODY}}
</body></html>"""


def render_pdf(html_path, output_path):
    """WeasyPrint if available, else Chrome headless --print-to-pdf
    (Design-System §4 sanctioned fallback)."""
    try:
        import weasyprint  # noqa
        weasyprint.HTML(filename=html_path).write_pdf(output_path)
        return "weasyprint"
    except Exception:
        pass
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if not os.path.exists(chrome):
        chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        raise RuntimeError("No PDF renderer: WeasyPrint not importable and Chrome not found.")
    subprocess.run([
        chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
        "--run-all-compositor-stages-before-draw", "--virtual-time-budget=3000",
        f"--print-to-pdf={output_path}", f"file://{html_path}",
    ], check=True, capture_output=True)
    return "chrome"


def build_report(data, output_path):
    """Main report builder. data is a dict with all analysis results.
    Same signature as v1 — the SKILL.md workflow is unchanged."""
    # Logos must resolve from the canonical brand-assets paths. A missing logo
    # fails loudly (Design-System rule) — never a silent broken image.
    for logo in (LOGO_WHITE, LOGO_COLOR):
        if not os.path.exists(logo):
            raise RuntimeError(
                f"DigitalCLIQ logo not found at canonical path: {logo!r}. "
                f"Restore Resources/brand-assets/ before generating. "
                f"A report without the logo is a Visual-QA FAIL.")
    html = build_html(data)
    out_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(out_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                     dir=out_dir) as fh:
        fh.write(html)
        html_path = fh.name
    try:
        engine = render_pdf(html_path, output_path)
        print(f"Rendered via {engine}")
    finally:
        try:
            os.unlink(html_path)
        except OSError:
            pass
    return output_path


if __name__ == "__main__":
    # Read JSON data from stdin or file argument (unchanged interface)
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r") as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    output = data.get("output_path", "outputs/comparison.pdf")
    result = build_report(data, output)
    print(f"PDF generated: {result}")
