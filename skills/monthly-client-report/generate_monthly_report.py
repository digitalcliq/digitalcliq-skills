#!/usr/bin/env python3
"""
DigitalCLIQ Monthly Client Report generator.

JSON -> branded PDF via the canonical design-system pipeline: hand-authored
HTML + CSS (Resources/design-system/Design-System.md tokens + component
library) rendered by WeasyPrint when importable, else Chrome headless
--print-to-pdf (the documented fallback). Never reportlab: it cannot hit
the spec.

Layout: canonical dark cover (cover-portrait.html recipe) + tight 2-3 light
interior pages with running furniture, section headers (eyebrow / H2 /
accent rule / ghost numeral), stat cards, callout bars, comparison columns,
and checklist rows. Sections render in order and gracefully OMIT when a
block is missing or flagged available:false — no empty boxes.

Usage:
    python3 generate_monthly_report.py <data.json> <out.pdf> <logo.png>

Brand: Digital Blue #405FAB, Sky Blue #6B9DD4, Navy Deep/Base/Lift
#070A15/#10162A/#151E37, Warm Grey #949592, Callout Tint #EDF2F9, borders
#D8E1F0, white. Dosis for structure, Roboto Slab for reading. WHITE logo on
dark only, FULL-COLOR logo on light only. Status meaning is always carried
by explicit text (deltas, verdicts, labels); color is a palette treatment
only (Sky Blue family = strong, Warm Grey = weak, Digital Blue = emphasis).
Only drewmoon@digitalcliq.com may appear; gmail is banned.
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

VAULT = "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ"
FONT_DIR = f"{VAULT}/Resources/brand-assets/fonts"
LOGO_WHITE = f"{VAULT}/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png"
LOGO_COLOR = f"{VAULT}/Resources/brand-assets/classic-digital-cliq-logo-solid-1000px-wide copy.png"

CURSOR_TICK = ('<svg class="tick" viewBox="0 0 100 100"><path d="M12 4 L88 58 '
               'L52 62 L68 96 L54 100 L40 68 L14 88 Z" fill="#405FAB"/></svg>')
CURSOR_BIG = ('<svg class="cursor" viewBox="0 0 100 100"><path d="M12 4 L88 58 '
              'L52 62 L68 96 L54 100 L40 68 L14 88 Z" fill="#000" opacity="0.9" '
              'transform="rotate(-12 50 50)"/></svg>')

# Palette-only status treatments (CSS class names). The MEANING is always
# carried by explicit text (delta strings, NADA verdicts, insight copy).
STATUS_CLASS = {
    "positive": "st-strong", "success": "st-strong",
    "negative": "st-weak", "warning": "st-weak", "alert": "st-weak",
    "info": "st-emph", "neutral": "st-neutral",
}

# Layout estimation constants (px, on the fixed 850x1100 page). Calibrated
# against measured Chrome renders of the sample data; keep slightly
# conservative so a page never overflows its fixed 1100px frame.
PAGE_CAP = 995          # usable content height per interior page
CPL_FULL = 108          # ~chars per line, full-width body text
CPL_HALF = 46           # ~chars per line, half-column body text
LINE_H = 17
SHEAD_H = 58            # section header (single-line title)


def _fail(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _guard_email(blob):
    """Hard rule: gmail must never appear in a deliverable."""
    if "digitalcliq@gmail.com" in json.dumps(blob).lower():
        _fail("digitalcliq@gmail.com found in report data. Only "
              "drewmoon@digitalcliq.com may appear in deliverables.")


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def rich(s):
    """Escape, then re-allow the inline tags the JSON insights use."""
    out = esc(s)
    for tag in ("b", "i", "br"):
        out = out.replace(f"&lt;{tag}&gt;", f"<{tag}>")
        out = out.replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    out = out.replace("&lt;br/&gt;", "<br>")
    return out


def _plain(s):
    return re.sub(r"<[^>]+>", "", str(s))


def _est_lines(text, cpl):
    return max(1, math.ceil(len(_plain(text)) / cpl))


# ---------- fonts (hard error when missing — never substitute) ----------
def _font_faces():
    faces = [
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
            _fail(f"DigitalCLIQ brand font missing: {path}. Install from the "
                  "vault archive before generating (vault-facts: never "
                  "substitute fonts).")
        out.append(f"@font-face{{font-family:'{fam}';src:url('file://{path}');"
                   f"font-weight:{weight};font-style:normal;}}")
    return "\n".join(out)


# ---------- component builders (Design-System §3) ----------
def sec_head(num, eyebrow, title, half=False):
    html = (f'<div class="shead"><div class="ghost">{esc(num)}</div>'
            f'<div class="eyebrow">{esc(eyebrow)}</div>'
            f'<h2>{esc(title)}</h2><div class="rule"></div></div>')
    per_line = 26 if half else 55
    h = SHEAD_H + (math.ceil(len(title) / per_line) - 1) * 28
    return html, h


def kpi_row(kpis, limit=5):
    """kpis: [{label, value, sub, status}] -> row of stat cards."""
    kpis = (kpis or [])[:limit]
    if not kpis:
        return "", 0
    cards = []
    for k in kpis:
        sub = k.get("sub", "")
        cls = STATUS_CLASS.get(k.get("status", "neutral"), "st-neutral")
        sub_html = f'<div class="s {cls}">{esc(sub)}</div>' if sub else ""
        cards.append(f'<div class="kpi">{CURSOR_TICK}'
                     f'<div class="v">{esc(k.get("value", ""))}</div>'
                     f'<div class="l">{esc(k.get("label", ""))}</div>'
                     f'{sub_html}</div>')
    return f'<div class="kpis">{"".join(cards)}</div>', 88


def data_table(rows, half=False):
    """rows: list of dicts. First dict's keys = headers (ported verbatim)."""
    if not rows:
        return "", 0
    headers = list(rows[0].keys())
    n = len(headers)
    ths = []
    for i, h in enumerate(headers):
        w = ""
        if n > 2 and i == 0:
            w = ' style="width:30%"'
        ths.append(f"<th{w}>{esc(h)}</th>")
    trs = [f'<tr>{"".join(ths)}</tr>']
    for r in rows:
        tds = []
        for i, h in enumerate(headers):
            cell = esc(r.get(h, ""))
            if i == 0:
                cell = f"<b>{cell}</b>"
            tds.append(f"<td>{cell}</td>")
        trs.append(f'<tr>{"".join(tds)}</tr>')
    cls = "tbl half" if half else "tbl"
    row_h = 46 if half else 25  # narrow columns wrap to 2-3 lines
    return (f'<table class="{cls}">{"".join(trs)}</table>',
            25 + row_h * len(rows) + 8)


def callout(text, ctype="info", cpl=CPL_FULL):
    cls = STATUS_CLASS.get(ctype, "st-emph")
    html = f'<div class="callout {cls}">{rich(text)}</div>'
    return html, _est_lines(text, cpl - 6) * LINE_H + 27


def insights(items, cpl=CPL_FULL):
    """items: [{text, type}] -> stacked callout bars."""
    html, h = "", 0
    for it in items or []:
        c, ch = callout(it.get("text", ""), it.get("type", "info"), cpl)
        html += c
        h += ch
    return html, h


def body_line(text, bold_lead=None, cpl=CPL_FULL):
    lead = f"<b>{esc(bold_lead)}</b> " if bold_lead else ""
    html = f'<p class="body">{lead}{rich(text)}</p>'
    return html, _est_lines((bold_lead or "") + str(text), cpl) * LINE_H + 8


# ---------- section builders (data logic ported from the legacy build) ----------
def build_exec(d, num):
    m = d["metadata"]
    loc = ", ".join([x for x in [m.get("city"), m.get("state")] if x])
    bits = [x for x in [m.get("brand"), loc] if x]
    meta = "  ·  ".join(bits) if bits else "Monthly Performance Report"
    html = (f'<div class="shead"><div class="ghost">{num}</div>'
            f'<div class="eyebrow">Monthly Performance Report · {esc(m.get("month_label", ""))}</div>'
            f'<h2>{esc(m.get("client_name", "Client"))}</h2>'
            f'<div class="metaline">{esc(meta)}</div><div class="rule"></div></div>')
    h = 88 + (math.ceil(len(m.get("client_name", "Client")) / 55) - 1) * 28
    if d.get("exec_summary"):
        c, ch = callout(d["exec_summary"], "info")
        html += c
        h += ch
    return html, h


def build_lead_mix(d, num):
    lm = d.get("lead_mix")
    if not lm or not lm.get("available"):
        return None
    html, h = sec_head(num, "CRM · Executive Rollup", "Lead Mix by Category")
    note = (f"{lm.get('total_leads', '?')} good leads across "
            f"{len(lm.get('categories', []))} source categories, "
            f"{lm.get('total_sold', '?')} sold.")
    if lm.get("phone_tracked") is False:
        note += (" Phone-ups are not tracked as a lead source in this CRM "
                 "export, so calls are not counted here.")
    bl, bh = body_line(note)
    html += bl
    h += bh
    t, th = data_table(lm.get("categories"))
    html += t
    h += th
    ins, ih = insights(lm.get("insights"))
    html += ins
    h += ih
    return html, h


def build_traffic(d, num):
    t = d.get("traffic")
    if not t or not t.get("available"):
        return None
    html, h = sec_head(num, "GA4 · Website", "Website Traffic")
    k, kh = kpi_row(t.get("kpis"))
    html += k
    h += kh
    tb, th = data_table(t.get("channels"))
    html += tb
    h += th
    if t.get("social_referral"):
        bl, bh = body_line(t["social_referral"], "Social referral traffic:")
        html += bl
        h += bh
    ins, ih = insights(t.get("insights"))
    html += ins
    h += ih
    return html, h


def build_paid(d, num):
    p = d.get("paid")
    if not p or not p.get("available"):
        return None
    html, h = sec_head(num, "Google Ads · Meta", "Paid Media")
    k, kh = kpi_row(p.get("kpis"))
    html += k
    h += kh
    tb, th = data_table(p.get("sources"))
    html += tb
    h += th
    ins, ih = insights(p.get("insights"))
    html += ins
    h += ih
    return html, h


def build_seo(d, num):
    s = d.get("seo")
    if not s or not s.get("available"):
        return None
    html, h = sec_head(num, "SEMRUSH · Organic", "Search / SEO")
    k, kh = kpi_row(s.get("kpis"))
    html += k
    h += kh
    tb, th = data_table(s.get("movers"))
    html += tb
    h += th
    ins, ih = insights(s.get("insights"))
    html += ins
    h += ih
    return html, h


def build_leads(d, num):
    l = d.get("leads")
    if not l or not l.get("available"):
        return None
    html, h = sec_head(num, "CRM · NADA Benchmark", "Leads & NADA Benchmark")
    if l.get("summary"):
        bl, bh = body_line(l["summary"])
        html += bl
        h += bh
    k, kh = kpi_row(l.get("kpis"))
    html += k
    h += kh
    nada = l.get("nada")
    if nada:
        verdict = nada.get("verdict", "")
        text = (f"<b>NADA close-rate benchmark:</b> store at "
                f"<b>{esc(nada.get('store_close_rate', '-'))}</b> vs "
                f"<b>{esc(nada.get('benchmark', '-'))}</b> expected. {esc(verdict)}")
        cls = STATUS_CLASS.get(nada.get("status", "info"), "st-emph")
        html += f'<div class="callout {cls}">{text}</div>'
        h += _est_lines(_plain(text), CPL_FULL - 6) * LINE_H + 27
    tb, th = data_table(l.get("sources"))
    html += tb
    h += th
    ins, ih = insights(l.get("insights"))
    html += ins
    h += ih
    return html, h


def _reputation_col(r, num):
    html, h = sec_head(num, "Google · Yelp", "Online Reputation", half=True)
    plats = r.get("platforms") or []
    if plats:
        kpis = []
        for p in plats:
            delta = p.get("delta", "")
            status = "positive" if str(delta).startswith("+") else (
                "negative" if str(delta).startswith("-") else "neutral")
            kpis.append({
                "label": f"{p.get('name', '')} ({p.get('reviews', '-')} rev)",
                "value": f"{p.get('rating', '-')}★",
                "sub": delta, "status": status,
            })
        k, kh = kpi_row(kpis, limit=3)
        html += k
        h += kh
    pos = r.get("themes_positive") or []
    neg = r.get("themes_negative") or []
    if pos:
        bl, bh = body_line("; ".join(pos), "What customers praise:", cpl=CPL_HALF)
        html += bl
        h += bh
    if neg:
        bl, bh = body_line("; ".join(neg), "Recurring complaints:", cpl=CPL_HALF)
        html += bl
        h += bh
    ins, ih = insights(r.get("insights"), cpl=CPL_HALF)
    html += ins
    h += ih
    return html, h


def _regional_col(rg, num):
    html, h = sec_head(num, "NADA · Economy",
                       f"Market Context: {rg.get('state', 'Region')}", half=True)
    if rg.get("headline"):
        _, bh = body_line(rg["headline"], cpl=CPL_HALF)
        html += f'<p class="body"><b>{esc(rg["headline"])}</b></p>'
        h += bh
    stats = rg.get("stats")
    if stats:
        rows = [{"Indicator": s.get("stat", ""), "Value": s.get("value", ""),
                 "Source": s.get("source", "")} for s in stats]
        t, th = data_table(rows, half=True)
        html += t
        h += th
    for n in rg.get("narrative", []) or []:
        bl, bh = body_line(n, cpl=CPL_HALF)
        html += bl
        h += bh
    return html, h


def build_rep_regional(d, next_num):
    """Reputation + regional, half-width comparison columns when both exist."""
    r = d.get("reputation")
    rg = d.get("regional")
    r_ok = bool(r and r.get("available"))
    rg_ok = bool(rg and rg.get("available"))
    if not r_ok and not rg_ok:
        return None, next_num
    if r_ok and rg_ok:
        c1, h1 = _reputation_col(r, f"{next_num:02d}")
        c2, h2 = _regional_col(rg, f"{next_num + 1:02d}")
        html = (f'<div class="cols"><div class="col">{c1}</div>'
                f'<div class="col">{c2}</div></div>')
        return (html, max(h1, h2) + 8), next_num + 2
    if r_ok:
        return _reputation_col(r, f"{next_num:02d}"), next_num + 1
    return _regional_col(rg, f"{next_num:02d}"), next_num + 1


def build_wins(d, num):
    w = d.get("wins")
    if not w:
        return None
    items = w.get("items") or []
    challenges = w.get("challenges") or []
    if not items and not challenges:
        return None
    client = d["metadata"].get("client_name", "Client")
    html, h = sec_head(num, "From the vault",
                       f"DigitalCLIQ & {client}: Wins This Month")

    def check_rows(entries):
        """Height: pairs of cards, each row as tall as its longest text."""
        rows_h = 0
        for i in range(0, len(entries), 2):
            pair = entries[i:i + 2]
            lines = max(_est_lines(x, 50) for x in pair)
            rows_h += lines * 16 + 22
        return rows_h + 8

    if items:
        rows = "".join(
            f'<div class="check"><span class="tickbox">✓</span>'
            f'<span>{esc(it)}</span></div>' for it in items)
        html += f'<div class="checkgrid">{rows}</div>'
        h += check_rows(items)
    if challenges:
        html += '<div class="minihead">In flight / next up</div>'
        h += 28
        rows = "".join(
            f'<div class="check next"><span class="tickbox arrow">→</span>'
            f'<span>{esc(ch)}</span></div>' for ch in challenges)
        html += f'<div class="checkgrid">{rows}</div>'
        h += check_rows(challenges)
    return html, h


# ---------- pages ----------
def build_cover(d, logo_path):
    m = d["metadata"]
    client = m.get("client_name", "Client")
    month = m.get("month_label", "")
    loc = ", ".join([x for x in [m.get("city"), m.get("state")] if x])
    bits = [x for x in [m.get("brand"), loc] if x]
    sub_lead = " · ".join(bits)
    # Name only the sections this build actually contains. Claiming coverage
    # the report does not have is a defect the render gate catches.
    present = []
    for key, label in (("lead_mix", "lead mix"), ("traffic", "website traffic"),
                       ("paid", "paid media"), ("seo", "search"),
                       ("leads", "leads"), ("reputation", "reputation"),
                       ("regional", "market context")):
        sec = d.get(key)
        if sec and sec.get("available"):
            present.append(label)
    if len(present) > 1:
        covered = ", ".join(present[:-1]) + " and " + present[-1]
    elif present:
        covered = present[0]
    else:
        covered = "the month"
    subtitle = ((f"{sub_lead}. " if sub_lead else "") +
                f"How {client} performed across {covered} in {month}, "
                f"and what DigitalCLIQ is doing next.")
    return f'''<div class="page cover">
  <img class="logo" src="file://{logo_path}" alt="DigitalCLIQ">
  <div class="block">
    <div class="c-eyebrow">DigitalCLIQ Client Report · {esc(month)}</div>
    <h1>Monthly<br>Performance<br><span class="accent">Report.</span></h1>
    <div class="c-rule"></div>
    <div class="subtitle">{esc(subtitle)}</div>
  </div>
  {CURSOR_BIG}
  <div class="prepared"><b>Prepared by DigitalCLIQ.</b> &nbsp;Digital Strategy &amp; Development.
  &nbsp;{esc(client)}. &nbsp;{esc(month)}.</div>
  <div class="pillars">Innovative &nbsp;|&nbsp; Clean &nbsp;|&nbsp; Minimalist &nbsp;|&nbsp; Bold &nbsp;|&nbsp; Resourceful</div>
</div>'''


def furniture(doc_title, page_no, total):
    return (f'<div class="furniture-top">'
            f'<span class="doctitle">{esc(doc_title)}</span>'
            f'<img src="file://{LOGO_COLOR}" alt="DigitalCLIQ"></div>'
            f'<div class="furniture-bot">'
            f'<span>DigitalCLIQ · Digital Strategy &amp; Development</span>'
            f'<span>Page {page_no} of {total}</span></div>')


def paginate(blocks, cap=PAGE_CAP):
    pages, cur, h = [], [], 0
    for html, bh in blocks:
        if cur and h + bh > cap:
            pages.append(cur)
            cur, h = [], 0
        cur.append(html)
        h += bh
    if cur:
        pages.append(cur)
    return pages


def build_html(d, logo_path):
    m = d["metadata"]
    blocks = []
    num = 1
    blocks.append(build_exec(d, f"{num:02d}"))
    num += 1
    for builder in (build_lead_mix, build_traffic, build_paid, build_seo,
                    build_leads):
        b = builder(d, f"{num:02d}")
        if b:
            blocks.append(b)
            num += 1
    b, num = build_rep_regional(d, num)
    if b:
        blocks.append(b)
    b = build_wins(d, f"{num:02d}")
    if b:
        blocks.append(b)

    pages = paginate(blocks)
    doc_title = (f"Monthly Performance Report · "
                 f"{m.get('client_name', 'Client')} · {m.get('month_label', '')}")
    total = len(pages)
    interior = "".join(
        f'<div class="page interior">{furniture(doc_title, i, total)}'
        f'{"".join(p)}</div>'
        for i, p in enumerate(pages, 1))
    body = build_cover(d, logo_path) + interior
    title = f"Monthly Report · {m.get('client_name', '')}"
    return (_SHELL.replace("{{FONTS}}", _font_faces())
                  .replace("{{TITLE}}", esc(title))
                  .replace("{{BODY}}", body))


_SHELL = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{{TITLE}}</title><style>
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

/* ---- Canonical cover (cover-portrait.html recipe) ---- */
.cover{
  background:
    radial-gradient(ellipse 420px 320px at 85% 12%, rgba(36,53,98,0.85), transparent 70%),
    radial-gradient(ellipse 500px 380px at 8% 88%, rgba(36,53,98,0.55), transparent 70%),
    linear-gradient(180deg, var(--navy-deep) 0%, #0C1222 45%, var(--navy-lift) 100%);
  font-family:'Dosis',sans-serif;color:#fff;
}
.cover .logo{position:absolute;top:64px;left:70px;width:115px;}
.cover .block{position:absolute;left:70px;top:330px;width:640px;}
.cover .c-eyebrow{font-weight:600;font-size:15px;letter-spacing:0.24em;text-transform:uppercase;color:var(--sky-blue);margin-bottom:26px;}
.cover h1{font-weight:800;font-size:78px;line-height:1.02;text-transform:uppercase;letter-spacing:0.01em;}
.cover h1 .accent{color:var(--sky-blue);}
.cover .c-rule{width:64px;height:4px;background:var(--sky-blue);margin:30px 0 26px;}
.cover .subtitle{font-family:'Roboto Slab',serif;font-weight:400;font-size:18px;line-height:1.55;color:var(--body-on-dark);max-width:560px;}
.cover .cursor{position:absolute;right:105px;bottom:190px;width:85px;height:85px;}
.cover .prepared{position:absolute;left:70px;bottom:110px;right:90px;font-family:'Roboto Slab',serif;font-size:14px;line-height:1.5;color:var(--muted-on-dark);}
.cover .prepared b{color:var(--body-on-dark);font-weight:400;}
.cover .pillars{position:absolute;bottom:52px;width:100%;text-align:center;font-weight:600;font-size:12px;letter-spacing:0.32em;text-transform:uppercase;color:var(--muted-on-dark);}

/* ---- Interior (light) ---- */
.interior{background:var(--white);padding:50px 64px 54px;}
.furniture-top{position:absolute;top:0;left:64px;right:64px;height:42px;border-bottom:2px solid var(--card-border);display:flex;align-items:center;justify-content:space-between;}
.furniture-top .doctitle{font-family:'Dosis',sans-serif;font-weight:600;font-size:10px;letter-spacing:0.16em;text-transform:uppercase;color:var(--warm-grey);}
.furniture-top img{height:17px;}
.furniture-bot{position:absolute;bottom:0;left:64px;right:64px;height:38px;border-top:2px solid var(--card-border);display:flex;align-items:center;justify-content:space-between;}
.furniture-bot span{font-family:'Dosis',sans-serif;font-weight:500;font-size:10.4px;letter-spacing:0.15em;text-transform:uppercase;color:var(--warm-grey);}

.shead{position:relative;margin:10px 0 8px;}
.shead .eyebrow{font-family:'Dosis',sans-serif;font-weight:600;font-size:11px;letter-spacing:0.22em;text-transform:uppercase;color:var(--digital-blue);margin-bottom:4px;}
.shead h2{font-family:'Dosis',sans-serif;font-weight:700;font-size:24px;color:#000;line-height:1.1;padding-right:80px;}
.shead .metaline{font-family:'Dosis',sans-serif;font-weight:500;font-size:12.5px;letter-spacing:0.06em;color:var(--warm-grey);margin-top:4px;}
.shead .rule{width:48px;height:3px;background:var(--sky-blue);margin-top:9px;}
.ghost{position:absolute;right:0;top:-10px;font-family:'Dosis',sans-serif;font-weight:800;font-size:84px;line-height:1;color:var(--digital-blue);opacity:0.07;}
.minihead{font-family:'Dosis',sans-serif;font-weight:700;font-size:12px;letter-spacing:0.14em;text-transform:uppercase;color:var(--tile-blue);margin:10px 0 4px;}

.kpis{display:flex;gap:12px;margin:7px 0;}
.kpi{flex:1;background:var(--card-white);border:1px solid var(--card-border);border-radius:12px;padding:9px 10px 8px;position:relative;text-align:center;}
.kpi .v{font-family:'Dosis',sans-serif;font-weight:800;font-size:25px;line-height:1.05;color:var(--sky-blue);}
.kpi .l{font-family:'Dosis',sans-serif;font-weight:500;font-size:9px;letter-spacing:0.13em;text-transform:uppercase;color:var(--warm-grey);margin-top:5px;}
.kpi .s{font-family:'Dosis',sans-serif;font-weight:600;font-size:11px;margin-top:3px;}
.tick{position:absolute;top:8px;right:8px;width:10px;height:10px;}

.st-strong{color:var(--sky-blue);}
.st-weak{color:var(--warm-grey);}
.st-emph{color:var(--digital-blue);}
.st-neutral{color:var(--navy-base);}

table.tbl{width:100%;border-collapse:collapse;margin:8px 0;border-radius:12px;overflow:hidden;}
table.tbl th{background:var(--digital-blue);color:#fff;font-family:'Dosis',sans-serif;font-weight:600;font-size:11px;letter-spacing:0.06em;text-transform:uppercase;padding:6px 10px;text-align:left;}
table.tbl td{font-size:11px;line-height:1.35;padding:4px 10px;border-bottom:1px solid var(--card-border);vertical-align:top;}
table.tbl tr:nth-child(odd) td{background:var(--callout-tint);}
table.tbl td b{font-family:'Dosis',sans-serif;font-weight:700;font-size:12px;color:var(--tile-blue);}
table.tbl.half th{font-size:10px;padding:6px 8px;}
table.tbl.half td{font-size:10.5px;padding:5px 8px;}

.callout{background:var(--callout-tint);border-left:3px solid var(--digital-blue);border-radius:0 12px 12px 0;padding:9px 13px;font-size:11.5px;line-height:1.42;margin:6px 0;}
.callout b{font-family:'Dosis',sans-serif;font-weight:700;font-size:12px;color:var(--tile-blue);letter-spacing:0.04em;}
.callout.st-strong{border-left-color:var(--sky-blue);}
.callout.st-weak{border-left-color:var(--warm-grey);}
.callout.st-neutral{border-left-color:var(--navy-base);}

p.body{font-size:11.5px;line-height:1.45;margin:5px 0;color:#000;}
p.body b{font-family:'Dosis',sans-serif;font-weight:700;font-size:11.5px;color:var(--tile-blue);}

/* Comparison split: two half-width columns */
.cols{display:flex;gap:20px;margin:0;align-items:flex-start;}
.col{flex:1;min-width:0;}
.col .shead h2{font-size:19px;padding-right:56px;}
.col .ghost{font-size:60px;top:-4px;}
.col .kpi .v{font-size:22px;}
.col .kpi .l{font-size:8px;}

/* Checklist rows (wins) */
.checkgrid{display:flex;flex-wrap:wrap;gap:10px;margin:8px 0;}
.check{width:calc(50% - 5px);display:flex;gap:10px;align-items:flex-start;background:var(--card-white);border:1px solid var(--card-border);border-radius:10px;padding:8px 11px;font-size:11.3px;line-height:1.42;}
.check .tickbox{flex:0 0 auto;width:18px;height:18px;border-radius:5px;background:var(--digital-blue);color:#fff;font-family:'Dosis',sans-serif;font-weight:700;font-size:12px;line-height:18px;text-align:center;margin-top:1px;}
.check.next{background:var(--callout-tint);}
.check .tickbox.arrow{background:var(--tile-blue);}
</style></head><body>
{{BODY}}
</body></html>"""


# ---------- rendering (WeasyPrint -> Chrome headless fallback) ----------
def render_pdf(html_path, output_path):
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
        _fail("No PDF renderer: WeasyPrint not importable and Chrome not found.")
    subprocess.run([
        chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
        "--run-all-compositor-stages-before-draw", "--virtual-time-budget=3000",
        f"--print-to-pdf={output_path}", f"file://{html_path}",
    ], check=True, capture_output=True)
    return "chrome"


def main():
    if len(sys.argv) != 4:
        _fail("usage: generate_monthly_report.py <data.json> <out.pdf> <logo.png>")
    data_path, out_path, logo_path = sys.argv[1:4]
    if not os.path.exists(logo_path):
        _fail(f"logo not found: {logo_path}")
    # Interior furniture uses the full-color logo on white — canonical path
    # only, and a missing logo fails loudly (Design-System rule).
    if not os.path.exists(LOGO_COLOR):
        _fail(f"DigitalCLIQ color logo missing at canonical path: {LOGO_COLOR}. "
              "Restore Resources/brand-assets/ before generating.")
    with open(data_path) as f:
        d = json.load(f)
    _guard_email(d)
    if "metadata" not in d:
        _fail("data json missing 'metadata'")

    html = build_html(d, os.path.abspath(logo_path))
    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                     dir=out_dir) as fh:
        fh.write(html)
        html_path = fh.name
    try:
        engine = render_pdf(html_path, os.path.abspath(out_path))
        print(f"PDF generated via {engine}")
        print(f"OK wrote {out_path}")
    finally:
        try:
            os.unlink(html_path)
        except OSError:
            pass


if __name__ == "__main__":
    main()
