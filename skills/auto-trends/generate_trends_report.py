#!/usr/bin/env python3
"""
Automotive Market Trend Report — Visual PDF Generator (v2)
Developed by DigitalCLIQ — Digital Strategy & Development

Rebuilt per Resources/design-system/Design-System.md: hand-authored HTML+CSS
rendered to PDF, using the canonical component library (stat cards, stat bands,
callout bars, icon/numbered lanes, comparison cards, ghost numerals, running
furniture). NEVER reportlab for narrative reports — it cannot hit the spec and
produces the wall-of-text output Drew has repeatedly flagged.

Pipeline: WeasyPrint if importable, else Chrome headless --print-to-pdf
(the design-system documented fallback). Fonts (Dosis + Roboto Slab) are
embedded via @font-face from the vault archive so rendering is self-contained.

Usage:
    python3 generate_trends_report.py <json_path> <output_pdf> [logo_path]
"""

import json
import os
import re
import sys
import shutil
import subprocess
import tempfile

VAULT = "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ"
FONT_DIR = f"{VAULT}/Resources/brand-assets/fonts"
LOGO_WHITE = f"{VAULT}/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png"
LOGO_COLOR = f"{VAULT}/Resources/brand-assets/classic-digital-cliq-logo-solid-1000px-wide copy.png"

CURSOR_SVG = ('<svg class="tick" viewBox="0 0 100 100"><path d="M12 4 L88 58 '
              'L52 62 L68 96 L54 100 L40 68 L14 88 Z" fill="#405FAB"/></svg>')


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def extract_src(detail):
    """Pull the trailing (Source) citation off a metric detail for the stat
    card's source line; return (caption_without_source, SOURCE)."""
    if not detail:
        return "", ""
    m = re.search(r"\(([^()]+)\)\s*\.?\s*$", detail.strip())
    if m:
        src = m.group(1).strip()
        cap = detail[:m.start()].strip().rstrip(",;. ")
        return cap, src
    return detail.strip(), ""


def num_class(value):
    """Pick a size class so a long stat value stays on ONE line. Wrapping is
    what knocked card labels out of alignment across a row."""
    n = len(str(value))
    if n > 12:
        return "num xs"
    if n > 8:
        return "num sm"
    return "num"


def stat_card(value, label, src_line):
    src_html = f'<div class="src">{esc(src_line)}</div>' if src_line else ""
    return (f'<div class="stat">{CURSOR_SVG}'
            f'<div class="{num_class(value)}">{esc(value)}</div>'
            f'<div class="cap">{esc(label)}</div>{src_html}</div>')


def stat_grid(metrics, limit=4):
    cards = []
    for m in metrics[:limit]:
        cap, src = extract_src(m.get("detail", ""))
        # prefer the label as the caption, keep the extracted source line
        cards.append(stat_card(m.get("value", ""), m.get("label", ""), src or cap[:60]))
    return f'<div class="statgrid">{"".join(cards)}</div>'


def callout(lead, body):
    lead_html = f"<b>{esc(lead)}</b> " if lead else ""
    return f'<div class="callout">{lead_html}{esc(body)}</div>'


def phase_cards(pairs):
    cards = []
    for title, body in pairs:
        cards.append(f'<div class="phase"><h5>{esc(title)}</h5>'
                     f'<p>{esc(body)}</p></div>')
    return f'<div class="phases">{"".join(cards)}</div>'


def sec_head(num, eyebrow, title):
    return (f'<div class="sec-head"><div class="ghost">{esc(num)}</div>'
            f'<div class="eyebrow">{esc(eyebrow)}</div>'
            f'<h2>{esc(title)}</h2><div class="rule"></div></div>')


def furniture(page_no, total, region="Southern California"):
    return (f'<div class="furniture-top">'
            f'<span class="doctitle">Automotive Market Trend Report · {esc(region)}</span>'
            f'<img src="file://{LOGO_COLOR}" alt="DigitalCLIQ"></div>'
            f'<div class="furniture-bot">'
            f'<span>DigitalCLIQ · Digital Strategy &amp; Development</span>'
            f'<span>Page {page_no} of {total}</span></div>')


def oem_table(highlights, period_label="Current-period read", limit=6, detail_chars=210):
    """Brand read table. Row count and per-row length are capped because an
    unbounded table pushed the regional callout off the bottom of the page and
    over the footer."""
    rows = ['<tr><th style="width:20%">Brand</th>'
            f'<th style="width:80%">{esc(period_label)}</th></tr>']
    for h in highlights[:limit]:
        rows.append(f'<tr><td><b>{esc(h.get("brand",""))}</b></td>'
                    f'<td>{esc(_trim(h.get("detail",""), detail_chars))}</td></tr>')
    return f'<table class="providers">{"".join(rows)}</table>'


def lanes(items):
    cells = []
    for i, (head, body) in enumerate(items, 1):
        body_html = f'<p>{esc(body)}</p>' if body and body.strip() else ""
        cells.append(f'<div class="lane"><div class="n">{i}</div>'
                     f'<h4>{esc(head)}</h4>{body_html}</div>')
    return f'<div class="lanes">{"".join(cells)}</div>'


_DANGLING = {"to", "from", "on", "in", "of", "at", "by", "for", "with", "an",
             "a", "the", "and", "or", "against", "around", "into", "as",
             "that", "your", "its", "their", "is", "are", "be"}


def split_lead(text):
    """Split a 'Lead-in: rest' strategic bullet into a head and a NON-repeating
    body for a lane card. The body never restates the head."""
    def cap(s):
        s = s.strip()
        return s[:1].upper() + s[1:] if s else s

    text = (text or "").strip()
    for sep in [": ", " — ", " - "]:
        if sep in text:
            head, body = text.split(sep, 1)
            head = head.strip()
            if len(head) <= 95:
                return head, cap(body)
    # Prefer a real sentence boundary. Cutting on a fixed word count produced
    # headings that ended on a preposition ("...from monthly payment to") with
    # the body resuming mid-clause.
    m = re.search(r"(?<![A-Z])\.\s+(?=[A-Z0-9$])", text)
    if m and m.start() <= 95:
        return text[:m.start()].strip(), cap(text[m.end():])
    # No delimiter and no usable sentence break: take a short head, body is the
    # REMAINDER only. When there is no remainder the body stays EMPTY. Falling
    # back to the full text here is what produced lane cards whose paragraph
    # restated their own heading.
    words = text.split()
    if len(words) <= 10:          # short enough to stand alone as the heading
        return text.rstrip("."), ""
    head_words = words[:6]
    # Never end a heading on a dangling function word.
    while len(head_words) > 3 and head_words[-1].lower().rstrip(".,") in _DANGLING:
        head_words.pop()
    head = " ".join(head_words).rstrip(".,")
    body = " ".join(words[len(head_words):]).strip()
    return head, cap(body)


def compare_columns(risks, opps, item_chars=250):
    # Untrimmed items overflowed the column past the page bottom and printed
    # over the footer, so each bullet is capped at a sentence boundary.
    def col(title, cls, items):
        lis = "".join(f'<li>{esc(_trim(x, item_chars))}</li>' for x in items[:4])
        return (f'<div class="cmpcol {cls}"><div class="cmphead">{esc(title)}</div>'
                f'<ul>{lis}</ul></div>')
    return (f'<div class="compare">{col("Risks to Monitor", "risk", risks)}'
            f'{col("Opportunities to Pursue", "opp", opps)}</div>')


def build_html(data):
    meta = data["metadata"]
    region = meta["region"]
    gen_date = meta["generation_date"]
    date_disp = _pretty_date(gen_date)

    nv = data["new_vehicle_sales"]
    uv = data["used_vehicle_sales"]
    fo = data["fixed_ops"]
    pt = data["parts"]
    so = data["strategic_outlook"]
    ex = data["executive_summary"]

    nv_metrics = nv.get("national", {}).get("metrics", [])
    nv_regional = nv.get("regional", {}).get("metrics", [])

    total_pages = 7  # interior pages numbered 1..7; cover + who-we-are unnumbered

    # ---- Page 2: Executive Summary ----
    # Hero band, headline stats and throughline all come from the JSON. NOTHING
    # on this page may be hardcoded: this report reruns monthly and a frozen
    # number here would ship stale data under a real source citation.
    band_exec = _hero_band(ex.get("hero"), ex.get("overview", ""), nv_metrics)
    exec_grid = _exec_stat_grid(ex.get("headline_stats"), data)
    thesis = callout("THE THROUGHLINE:",
                     _trim(ex.get("throughline") or ex.get("overview", ""), 340))
    # top 3 implications as lanes
    # Four lanes, not three: an odd count left half the bottom row of this page
    # empty.
    imp = [split_lead(x) for x in so.get("short_term", [])[:2]] + \
          [split_lead(x) for x in so.get("medium_term", [])[:2]]
    exec_lanes = lanes(imp)

    page_exec = (f'<div class="page interior">{furniture(1, total_pages, region)}'
                 f'{sec_head("00", "At a glance", "Executive Summary")}'
                 f'{band_exec}{exec_grid}{thesis}{exec_lanes}</div>')

    # ---- Page 3: New Vehicle ----
    nv_out = phase_cards([
        ("6-Month Outlook", _trim(nv.get("outlook_6mo", ""), 420)),
        ("12-Month Outlook", _trim(nv.get("outlook_12mo", ""), 420)),
    ])
    nv_region_call = callout(f"{region.upper()}:",
                             _trim(nv.get("regional", {}).get("summary", ""), 460))
    page_nv = (f'<div class="page interior">{furniture(2, total_pages, region)}'
               f'{sec_head("01", "Part 01 · New Vehicle Sales", _headline(nv, "New vehicle sales"))}'
               f'{stat_grid(nv_metrics, 4)}'
               f'{oem_table(nv.get("oem_highlights", []), meta.get("oem_period_label", f"{_period(meta)} read"))}'
               f'{nv_region_call}{nv_out}</div>')

    # ---- Page 4: Used Vehicle ----
    # Shorter than the other sections: this page also carries the regional
    # callout and a regional stat row, so a 420-char outlook ran into the footer.
    uv_out = phase_cards([
        ("6-Month Outlook", _trim(uv.get("outlook_6mo", ""), 300)),
        ("12-Month Outlook", _trim(uv.get("outlook_12mo", ""), 300)),
    ])
    uv_call = callout("THE TWO-SIDED STORY:", _trim(uv.get("summary", ""), 460))
    # The regional block was researched every run and never rendered, which is
    # why this page came out roughly a third empty below the outlook cards.
    uv_reg = uv.get("regional", {})
    uv_region_call = (callout(f"{region.upper()}:", _trim(uv_reg.get("summary", ""), 370))
                      if uv_reg.get("summary") else "")
    uv_region_grid = (stat_grid(uv_reg.get("metrics", []), 4)
                      if uv_reg.get("metrics") else "")
    page_uv = (f'<div class="page interior">{furniture(3, total_pages, region)}'
               f'{sec_head("02", "Part 02 · Used Vehicle Sales", _headline(uv, "Used vehicle sales"))}'
               f'{stat_grid(uv.get("metrics", []), 4)}'
               f'{uv_call}'
               f'{stat_grid(uv.get("metrics", [])[4:8], 4) if len(uv.get("metrics", [])) > 4 else ""}'
               f'{uv_region_call}{uv_region_grid}'
               f'{uv_out}</div>')

    # ---- Page 5: Fixed Ops ----
    fo_metrics = fo.get("metrics", [])
    # Data-driven hero band. If the JSON carries no fixed-ops hero, the band is
    # omitted rather than filled with last month's numbers.
    band_fo = _hero_band(fo.get("hero"), "", [], required=True)
    fo_call = callout("THE BINDING CONSTRAINT:", _trim(fo.get("technician_market", ""), 460))
    # ev_readiness was researched every run and then dropped on the floor, which
    # is also why this page rendered bottom-light.
    fo_ev = (callout("EV SERVICE READINESS:", _trim(fo.get("ev_readiness", ""), 430))
             if fo.get("ev_readiness") else "")
    page_fo = (f'<div class="page interior">{furniture(4, total_pages, region)}'
               f'{sec_head("03", "Part 03 · Service & Fixed Operations", _headline(fo, "Service and fixed operations"))}'
               f'{stat_grid(fo_metrics, 4)}'
               f'{band_fo}{fo_call}{fo_ev}'
               f'{phase_cards([("6-Month Outlook", _trim(fo.get("outlook_6mo", ""), 380)), ("12-Month Outlook", _trim(fo.get("outlook_12mo", ""), 380))])}</div>')

    # ---- Page 6: Parts ----
    pt_call = callout("OEM VS. AFTERMARKET:", _trim(pt.get("oem_vs_aftermarket", ""), 470))
    pt_ev = callout("EV IMPACT:", _trim(pt.get("ev_impact", ""), 470))
    page_pt = (f'<div class="page interior">{furniture(5, total_pages, region)}'
               f'{sec_head("04", "Part 04 · Parts", _headline(pt, "Parts"))}'
               f'{stat_grid(pt.get("metrics", []), 4)}'
               # Second row of metrics: researched every run, previously dropped,
               # leaving roughly 30% of this page dead below the outlook cards.
               f'{stat_grid(pt.get("metrics", [])[4:8], 4) if len(pt.get("metrics", [])) > 4 else ""}'
               f'{pt_call}{pt_ev}'
               f'{phase_cards([("6-Month Outlook", _trim(pt.get("outlook_6mo", ""), 380)), ("12-Month Outlook", _trim(pt.get("outlook_12mo", ""), 380))])}</div>')

    # ---- Page 7: Strategic Outlook ----
    short_lanes = lanes([split_lead(x) for x in so.get("short_term", [])[:4]])
    cmp_cols = compare_columns(so.get("risks", []), so.get("opportunities", []))
    page_so = (f'<div class="page interior">{furniture(6, total_pages, region)}'
               f'{sec_head("05", "Part 05 · Strategic Outlook", "What DigitalCLIQ does with this")}'
               f'<div class="minihead">Near-term moves (next 6 months)</div>'
               f'{short_lanes}{cmp_cols}</div>')

    # ---- Page 8: Sources ----
    src_items = "".join(f'<li>{esc(s)}</li>' for s in data.get("sources", []))
    page_src = (f'<div class="page interior">{furniture(7, total_pages, region)}'
                f'{sec_head("06", "Appendix", "Sources")}'
                f'<ol class="sources">{src_items}</ol></div>')

    # ---- Page 9: Who We Are (dark bookend) ----
    page_who = f'''<div class="page whopage">
      <img class="logo" src="file://{LOGO_WHITE}" alt="DigitalCLIQ">
      <div class="whoblock">
        <div class="eyebrow">Who we are</div>
        <h1>Strategy that<br><span class="accent">sells cars.</span></h1>
        <div class="rule"></div>
        <p class="whocopy">DigitalCLIQ is a Southern California digital marketing agency built for
        automotive retail. We pair sharp strategy with hands-on execution across paid media, SEO,
        reputation, analytics, and creative, so dealerships sell more cars and own their markets.
        This report is part of how we keep our partners ahead of where the market is going.</p>
        <div class="contactcard">
          <div class="cname">Drew Moon</div>
          <div class="crole">Founder · DigitalCLIQ</div>
          <div class="cmail">drewmoon@digitalcliq.com</div>
        </div>
      </div>
      <svg class="cursor" viewBox="0 0 100 100"><path d="M12 4 L88 58 L52 62 L68 96 L54 100 L40 68 L14 88 Z" fill="#000" opacity="0.9" transform="rotate(-12 50 50)"/></svg>
      <div class="pillars">Innovative &nbsp;|&nbsp; Clean &nbsp;|&nbsp; Minimalist &nbsp;|&nbsp; Bold &nbsp;|&nbsp; Resourceful</div>
    </div>'''

    # ---- Cover ----
    cover = f'''<div class="page cover">
      <img class="logo" src="file://{LOGO_WHITE}" alt="DigitalCLIQ">
      <div class="block">
        <div class="eyebrow">Automotive Market Intelligence · {esc(region)}</div>
        <h1>Automotive<br>Market Trend<br><span class="accent">Report.</span></h1>
        <div class="rule"></div>
        <div class="subtitle">New and used vehicle sales, service and fixed operations, and parts:
        where the {esc(region)} market sits in {esc(_period(meta))}, and where it is heading over the next 6 and 12 months.</div>
      </div>
      <svg class="cursor" viewBox="0 0 100 100"><path d="M12 4 L88 58 L52 62 L68 96 L54 100 L40 68 L14 88 Z" fill="#000" opacity="0.9" transform="rotate(-12 50 50)"/></svg>
      <div class="prepared"><b>Prepared by DigitalCLIQ.</b> &nbsp;Digital Strategy &amp; Development. &nbsp;{esc(date_disp)}</div>
      <div class="pillars">Innovative &nbsp;|&nbsp; Clean &nbsp;|&nbsp; Minimalist &nbsp;|&nbsp; Bold &nbsp;|&nbsp; Resourceful</div>
    </div>'''

    body = (cover + page_exec + page_nv + page_uv + page_fo + page_pt +
            page_so + page_src + page_who)
    return _SHELL.replace("{{FONTS}}", _font_faces()).replace("{{BODY}}", body)


# ── helpers ───────────────────────────────────────────────────
def _mk_metric(value, label, src):
    return (f'<div class="stat">{CURSOR_SVG}<div class="{num_class(value)}">{value}</div>'
            f'<div class="cap">{label}</div><div class="src">{src}</div></div>')


def _period(meta):
    """Human period label for the cover and table headers, e.g. 'July 2026'.
    Taken from metadata.period_label when supplied, otherwise derived from the
    generation date. Never hardcoded."""
    if meta.get("period_label"):
        return meta["period_label"]
    import datetime
    try:
        return datetime.date.fromisoformat(meta.get("generation_date", "")).strftime("%B %Y")
    except Exception:
        return "the current period"


def _headline(section, fallback):
    """Section page headline. Comes from the JSON so the editorial angle tracks
    the month's actual data instead of repeating a frozen phrase."""
    return section.get("headline") or section.get("section_title") or fallback


def _hero_band(hero, fallback_text, fallback_metrics, required=False):
    """Dark stat band built from data. `hero` is {"value": ..., "caption": ...}.
    With no hero and no usable fallback the band is omitted entirely: shipping
    an empty band beats shipping last month's number."""
    value, caption = "", ""
    if isinstance(hero, dict):
        value = str(hero.get("value", "")).strip()
        caption = str(hero.get("caption", "")).strip()
    if not value and not required and fallback_metrics:
        m = _find_metric(fallback_metrics, "forecast") or fallback_metrics[0]
        value = str(m.get("value", "")).strip()
        caption = fallback_text or str(m.get("detail", "")).strip()
    if not value:
        return ""
    # Bold the first sentence, run the rest plain. Split only on a real sentence
    # end: a bare ". " also matches abbreviations like "The U.S. market".
    m = re.search(r"(?<![A-Z])\.\s+(?=[A-Z])", caption)
    if m and m.start() >= 25:
        lead, rest = caption[:m.start()], caption[m.end():]
        cap_html = f"<b>{esc(lead.strip())}.</b> {esc(rest.strip())}"
    else:
        cap_html = f"<b>{esc(caption)}</b>"
    return (f'<div class="band"><div class="num">{esc(value)}</div>'
            f'<div class="cap">{cap_html}</div></div>')


def _exec_stat_grid(headline_stats, data):
    """Four cross-section headline stats. Prefers an explicit
    executive_summary.headline_stats list; otherwise pulls the lead metric from
    each of the four sections so the page always reflects THIS month's data."""
    cards = []
    if headline_stats:
        for s in headline_stats[:4]:
            cards.append(_mk_metric(esc(s.get("value", "")), esc(s.get("label", "")),
                                    esc(s.get("source", "")).upper()))
    else:
        for key in ("new_vehicle_sales", "used_vehicle_sales", "fixed_ops", "parts"):
            sec = data.get(key, {})
            mets = sec.get("national", {}).get("metrics", []) or sec.get("metrics", [])
            if not mets:
                continue
            m = mets[0]
            cap, src = extract_src(m.get("detail", ""))
            cards.append(_mk_metric(esc(m.get("value", "")), esc(m.get("label", "")),
                                    esc(src or cap[:60]).upper()))
    if not cards:
        return ""
    return f'<div class="statgrid">{"".join(cards)}</div>'


def _find_metric(metrics, keyword):
    for m in metrics:
        if keyword.lower() in m.get("label", "").lower():
            return m
    return None


def _trim(text, n):
    """Trim to <= n chars, preferring a clean sentence boundary so cards never
    end mid-clause (e.g. 'over half of.')."""
    text = (text or "").strip()
    if len(text) <= n:
        return text
    window = text[:n]
    # Last real sentence end. A bare ". " also matches abbreviations, which is
    # how a callout ended on "...held 56.3 percent of the U.S." Require the
    # period NOT to follow a capital and to be followed by a capital.
    end = -1
    # A sentence may legitimately begin with a figure ("$3,500 instant...",
    # "29.6 percent of..."). Restricting the lookahead to [A-Z] hid those
    # boundaries and forced a mid-clause word cut instead.
    for m in re.finditer(r"(?<![A-Z])[.!?]\s+(?=[A-Z0-9$])", window):
        end = m.start()
    # Prefer ending on a complete sentence even if that costs some length. A
    # word-boundary cut silently changes meaning ("step-down on Canada" when the
    # source said "Canada and Mexico"), which is worse than a shorter card.
    if end >= int(n * 0.40):
        return window[:end + 1].strip()
    cut = window.rsplit(" ", 1)[0].rstrip(",;:. ")
    # avoid ending on a dangling open parenthesis
    if cut.count("(") > cut.count(")"):
        cut = cut[:cut.rfind("(")].rstrip(",;:. ")
    # avoid ending on a conjunction/preposition ("...and over half of.")
    _DANGLE = {"and", "or", "but", "with", "of", "to", "for", "at", "in", "on",
               "the", "a", "an", "that", "which", "while", "as", "by", "from",
               "is", "are", "was", "were", "than", "into", "over", "under"}
    parts = cut.split()
    while parts and parts[-1].lower().strip(",;:") in _DANGLE:
        parts.pop()
    cut = " ".join(parts).rstrip(",;:. ")
    return cut + "." if cut else ""


def _pretty_date(iso):
    import datetime
    try:
        d = datetime.date.fromisoformat(iso)
        return d.strftime("%B %-d, %Y")
    except Exception:
        return iso


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
            raise RuntimeError(
                f"DigitalCLIQ brand font missing: {path}. Install from the vault "
                f"archive before generating (vault-facts: never substitute fonts).")
        out.append(f"@font-face{{font-family:'{fam}';src:url('file://{path}');"
                   f"font-weight:{weight};font-style:normal;}}")
    return "\n".join(out)


_SHELL = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
/* US Letter, per Design-System per-format spec. 816x1056px @96dpi = 8.5x11in
   exactly, so the file prints and previews as a standard page. */
@page { size: 8.5in 11in; margin: 0; }
{{FONTS}}
:root{
  --digital-blue:#405FAB; --sky-blue:#6B9DD4; --warm-grey:#949592; --white:#FFFFFF;
  --navy-deep:#070A15; --navy-base:#10162A; --navy-lift:#151E37; --card-navy:#131B30;
  --orb-glow:#243562; --border-blue:rgba(107,157,212,0.22); --body-on-dark:#C9D5EA; --muted-on-dark:#8FA0C0;
  --callout-tint:#EDF2F9; --card-white:#FBFBFD; --card-border:#D8E1F0; --tile-blue:#2E4780;
}
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:'Roboto Slab',serif;color:#000;-webkit-print-color-adjust:exact;print-color-adjust:exact;}
.page{width:816px;height:1056px;position:relative;overflow:hidden;page-break-after:always;}
.page:last-child{page-break-after:auto;}

/* Cover + Who (dark) */
.cover,.whopage{
  background:
    radial-gradient(ellipse 420px 320px at 85% 12%, rgba(36,53,98,0.85), transparent 70%),
    radial-gradient(ellipse 500px 380px at 8% 88%, rgba(36,53,98,0.55), transparent 70%),
    linear-gradient(180deg, var(--navy-deep) 0%, var(--navy-base) 45%, var(--navy-lift) 100%);
  font-family:'Dosis',sans-serif;color:#fff;
}
.cover .logo,.whopage .logo{position:absolute;top:64px;left:70px;width:115px;}
.cover .block,.whopage .whoblock{position:absolute;left:70px;top:330px;width:640px;}
.cover .eyebrow,.whopage .eyebrow{font-weight:600;font-size:15px;letter-spacing:0.24em;text-transform:uppercase;color:var(--sky-blue);margin-bottom:24px;}
.cover h1,.whopage h1{font-weight:800;font-size:74px;line-height:1.03;text-transform:uppercase;letter-spacing:0.01em;}
.cover h1 .accent,.whopage h1 .accent{color:var(--sky-blue);}
.cover .rule,.whopage .rule{width:64px;height:4px;background:var(--sky-blue);margin:28px 0 26px;}
.cover .subtitle{font-family:'Roboto Slab',serif;font-weight:400;font-size:19px;line-height:1.55;color:var(--body-on-dark);max-width:560px;}
.cover .cursor,.whopage .cursor{position:absolute;right:105px;bottom:190px;width:85px;height:85px;}
.cover .prepared{position:absolute;left:70px;bottom:110px;font-family:'Roboto Slab',serif;font-size:14px;color:var(--muted-on-dark);}
.cover .prepared b{color:var(--body-on-dark);font-weight:400;}
.cover .pillars,.whopage .pillars{position:absolute;bottom:52px;width:100%;text-align:center;font-weight:600;font-size:12px;letter-spacing:0.32em;text-transform:uppercase;color:var(--muted-on-dark);}

.whopage .whocopy{font-family:'Roboto Slab',serif;font-weight:400;font-size:16px;line-height:1.7;color:var(--body-on-dark);max-width:600px;margin-bottom:34px;}
.whopage .contactcard{background:var(--card-navy);border:1px solid var(--border-blue);border-radius:14px;padding:22px 26px;display:inline-block;min-width:340px;}
.whopage .cname{font-family:'Dosis',sans-serif;font-weight:800;font-size:30px;color:#fff;line-height:1;}
.whopage .crole{font-family:'Dosis',sans-serif;font-weight:500;font-size:12px;letter-spacing:0.18em;text-transform:uppercase;color:var(--muted-on-dark);margin:8px 0 12px;}
.whopage .cmail{font-family:'Dosis',sans-serif;font-weight:700;font-size:18px;color:var(--sky-blue);}

/* Interior */
.interior{background:var(--white);padding:56px 64px 60px;}
.furniture-top{position:absolute;top:0;left:64px;right:64px;height:44px;border-bottom:2px solid var(--card-border);display:flex;align-items:center;justify-content:space-between;}
.furniture-top .doctitle{font-family:'Dosis',sans-serif;font-weight:600;font-size:10.5px;letter-spacing:0.18em;text-transform:uppercase;color:var(--warm-grey);}
.furniture-top img{height:17px;}
.furniture-bot{position:absolute;bottom:0;left:64px;right:64px;height:40px;border-top:2px solid var(--card-border);display:flex;align-items:center;justify-content:space-between;}
.furniture-bot span{font-family:'Dosis',sans-serif;font-weight:500;font-size:10.4px;letter-spacing:0.15em;text-transform:uppercase;color:var(--warm-grey);}

.sec-head{position:relative;margin:22px 0 18px;}
.sec-head .eyebrow{font-family:'Dosis',sans-serif;font-weight:600;font-size:12.5px;letter-spacing:0.22em;text-transform:uppercase;color:var(--digital-blue);margin-bottom:8px;}
.sec-head h2{font-family:'Dosis',sans-serif;font-weight:700;font-size:34px;color:#000;line-height:1.08;max-width:76%;position:relative;z-index:1;}
.sec-head .rule{width:48px;height:3px;background:var(--sky-blue);margin-top:12px;}
.ghost{position:absolute;right:0;top:-16px;font-family:'Dosis',sans-serif;font-weight:800;font-size:140px;line-height:1;color:var(--digital-blue);opacity:0.07;z-index:0;}
.minihead{font-family:'Dosis',sans-serif;font-weight:700;font-size:13px;letter-spacing:0.14em;text-transform:uppercase;color:var(--tile-blue);margin:6px 0 2px;}

.statgrid{display:flex;gap:14px;margin:16px 0;}
.stat{flex:1;background:var(--card-white);border:1px solid var(--card-border);border-radius:12px;padding:15px 14px 12px;position:relative;}
.stat .num{font-family:'Dosis',sans-serif;font-weight:800;font-size:38px;line-height:1;color:var(--sky-blue);white-space:nowrap;}
/* Long values (e.g. "$551 vs $494") used to wrap to a second line, which pushed
   that card's label below its neighbours' and broke the grid baseline. Shrink
   to fit on one line instead of wrapping. */
.stat .num.sm{font-size:27px;}
.stat .num.xs{font-size:21px;}
.stat .num small{font-size:24px;}
.stat .cap{font-size:11.5px;line-height:1.4;margin-top:7px;color:#000;}
.stat .src{font-family:'Dosis',sans-serif;font-weight:500;font-size:9px;letter-spacing:0.13em;text-transform:uppercase;color:var(--warm-grey);margin-top:7px;}
.tick{position:absolute;top:10px;right:10px;width:11px;height:11px;}

table.providers{width:100%;border-collapse:collapse;margin:14px 0 14px;border-radius:12px;overflow:hidden;}
table.providers th{background:var(--digital-blue);color:#fff;font-family:'Dosis',sans-serif;font-weight:600;font-size:12px;letter-spacing:0.06em;text-transform:uppercase;padding:9px 12px;text-align:left;}
table.providers td{font-size:12px;line-height:1.4;padding:9px 12px;border-bottom:1px solid var(--card-border);vertical-align:top;}
table.providers tr:nth-child(even) td{background:var(--callout-tint);}
table.providers td b{font-family:'Dosis',sans-serif;font-weight:700;font-size:13px;color:var(--tile-blue);}

.callout{background:var(--callout-tint);border-left:3px solid var(--digital-blue);border-radius:0 12px 12px 0;padding:13px 16px;font-size:12.5px;line-height:1.55;margin:12px 0;}
.callout b{font-family:'Dosis',sans-serif;font-weight:700;font-size:12.5px;color:var(--tile-blue);letter-spacing:0.06em;text-transform:uppercase;}

.lanes{display:flex;flex-wrap:wrap;gap:14px;margin:14px 0;}
.lane{width:calc(50% - 7px);background:var(--card-white);border:1px solid var(--card-border);border-radius:12px;padding:14px 16px 14px 48px;position:relative;}
.lane .n{font-family:'Dosis',sans-serif;font-weight:700;font-size:24px;color:var(--digital-blue);position:absolute;left:16px;top:15px;line-height:1;}
.lane h4{font-family:'Dosis',sans-serif;font-weight:600;font-size:14.5px;color:var(--tile-blue);margin-bottom:5px;padding-top:2px;}
.lane p{font-size:11.3px;line-height:1.48;color:#000;}

.phases{display:flex;gap:14px;margin:12px 0;}
.phase{flex:1;border:1px solid var(--card-border);border-radius:12px;padding:12px 14px;background:#fff;}
.phase h5{font-family:'Dosis',sans-serif;font-weight:700;font-size:12px;letter-spacing:0.14em;text-transform:uppercase;color:var(--digital-blue);margin-bottom:6px;}
.phase p{font-size:11px;line-height:1.5;color:#000;}

.band{background:linear-gradient(135deg, var(--navy-base), var(--navy-lift));border-radius:14px;padding:18px 26px;display:flex;align-items:center;gap:26px;margin:12px 0;}
.band .num{font-family:'Dosis',sans-serif;font-weight:800;font-size:56px;color:var(--sky-blue);line-height:1;white-space:nowrap;}
.band .cap{font-family:'Roboto Slab',serif;font-size:12px;line-height:1.55;color:var(--body-on-dark);}
.band .cap b{color:#fff;font-weight:700;}

.compare{display:flex;gap:14px;margin-top:14px;}
.cmpcol{flex:1;border-radius:12px;padding:14px 16px;}
/* Comparison split per Design-System: WEAK/RISK greyed with Warm Grey label,
   STRONG/OPPORTUNITY blue-bordered with Digital Blue label. Meaning is carried
   by the explicit column headings, not by color alone. */
.cmpcol.risk{background:var(--card-white);border:1px solid var(--card-border);}
.cmpcol.opp{background:var(--callout-tint);border:1px solid var(--digital-blue);}
.cmpcol .cmphead{font-family:'Dosis',sans-serif;font-weight:700;font-size:14px;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:8px;}
.cmpcol.risk .cmphead{color:var(--warm-grey);}
.cmpcol.opp .cmphead{color:var(--digital-blue);}
.cmpcol ul{list-style:none;}
.cmpcol li{font-size:11.5px;line-height:1.5;padding:5px 0 5px 16px;position:relative;border-bottom:1px solid var(--card-border);}
.cmpcol li:last-child{border-bottom:none;}
.cmpcol li:before{content:"";position:absolute;left:0;top:11px;width:6px;height:6px;border-radius:50%;}
.cmpcol.risk li:before{background:var(--warm-grey);}
.cmpcol.opp li:before{background:var(--sky-blue);}

ol.sources{margin:8px 0 0 20px;column-count:2;column-gap:26px;}
ol.sources li{break-inside:avoid;}
/* Sized so a full source list (50+ entries) clears the footer in two columns.
   At 12px/1.6 the tail of the list printed over the running footer. */
ol.sources li{font-family:'Roboto Slab',serif;font-size:10.5px;line-height:1.5;color:#000;padding:2px 0;}
</style></head><body>
{{BODY}}
</body></html>"""


def render_pdf(html_path, output_path):
    """WeasyPrint if available, else Chrome headless --print-to-pdf."""
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


def build_pdf(json_path, output_path, logo_path=None):
    # Logos must resolve from the canonical brand-assets paths. A missing logo
    # fails loudly (Design-System rule) — never a silent broken image.
    for logo in (LOGO_WHITE, LOGO_COLOR):
        if not os.path.exists(logo):
            raise RuntimeError(
                f"DigitalCLIQ logo missing at canonical path: {logo}. "
                f"Restore Resources/brand-assets/ before generating.")
    with open(json_path) as f:
        data = json.load(f)
    html = build_html(data)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                     dir=os.path.dirname(output_path) or ".") as fh:
        fh.write(html)
        html_path = fh.name
    try:
        engine = render_pdf(html_path, output_path)
        print(f"PDF generated via {engine}: {output_path}")
    finally:
        try:
            os.unlink(html_path)
        except OSError:
            pass


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 generate_trends_report.py <json_path> <output_pdf> [logo_path]")
        sys.exit(1)
    build_pdf(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
