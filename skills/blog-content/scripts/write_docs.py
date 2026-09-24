"""DigitalCLIQ Blog Content Engine — branded Word-doc builder (one per piece).

Renders the full written body of each blog post / landing page into a polished,
DigitalCLIQ-branded .docx: logo header, title, a publish pack (meta title, meta
description, slug, primary keyword, schema), the article body (markdown-lite),
an embedded hero image, an FAQ block, and a contact footer. Writes each file to
outputs/ and merges the resulting `doc_path` back into the plan JSON so
build_workbook.py can link to it.

The plan supplies, per piece:
  pieces[i].body_markdown   # the full article, markdown-lite (#, ##, ###, -, 1., **bold**)
  pieces[i].seo             # meta_title, meta_description, url_slug, primary_keyword, schema_type
  pieces[i].outline.faq     # [{q, a}]  (rendered as an FAQ section if not already in body)
  pieces[i].asset_id        # -> plan.assets[*].file  (hero image embedded)

Usage:
    python3 write_docs.py <plan.json> <outputs_dir>
e.g. python3 write_docs.py plan.json /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import docx  # noqa
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-docx"])

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor, Inches
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

# DigitalCLIQ design tokens (Resources/design-system/Design-System.md)
DIGITAL_BLUE = RGBColor(0x40, 0x5F, 0xAB)
SKY_BLUE = RGBColor(0x6B, 0x9D, 0xD4)
TILE_BLUE = RGBColor(0x2E, 0x47, 0x80)
INK = RGBColor(0x00, 0x00, 0x00)   # light-theme body = Rich Black (legacy #0D1B2A retired)
WARM_GREY = RGBColor(0x94, 0x95, 0x92)
BLACK = RGBColor(0x00, 0x00, 0x00)
CALLOUT_TINT_HEX = "EDF2F9"        # callout fills
DIGITAL_BLUE_HEX = "405FAB"        # masthead band fill

HEAD_FONT = "Dosis"        # brand sans (primary)
BODY_FONT = "Roboto Slab"  # brand serif (secondary) — readable for long-form
LOGO_PATH = Path("/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/"
                 "digital-cliq-logo-solid-1000px-wide.png")
APPROVED_EMAIL = "drewmoon@digitalcliq.com"
BANNED_EMAIL = "digitalcliq@gmail.com"

BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _set_base_style(doc):
    st = doc.styles["Normal"]
    st.font.name = BODY_FONT
    st.font.size = Pt(11)
    st.font.color.rgb = INK
    rpr = st.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), BODY_FONT)
    rfonts.set(qn("w:hAnsi"), BODY_FONT)


def _runs_with_bold(paragraph, text, *, color=INK, size=11, base_bold=False, font=BODY_FONT):
    """Add text to a paragraph, honoring **bold** inline markers."""
    pos = 0
    for m in BOLD_RE.finditer(text):
        if m.start() > pos:
            r = paragraph.add_run(text[pos:m.start()])
            r.font.name, r.font.size, r.font.color.rgb, r.bold = font, Pt(size), color, base_bold
        r = paragraph.add_run(m.group(1))
        r.font.name, r.font.size, r.font.color.rgb, r.bold = font, Pt(size), color, True
        pos = m.end()
    if pos < len(text):
        r = paragraph.add_run(text[pos:])
        r.font.name, r.font.size, r.font.color.rgb, r.bold = font, Pt(size), color, base_bold


def _shade_cell(cell, hex_fill):
    """Solid-fill a table cell (design-system tints; python-docx has no API for this)."""
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), hex_fill)
    cell._tc.get_or_add_tcPr().append(shd)


def _heading(doc, text, level):
    # Design-System Word spec: H1 Dosis 20pt Digital Blue, H2 Dosis 14pt Tile Blue,
    # H3 Dosis 12pt Digital Blue.
    sizes = {1: 20, 2: 14, 3: 12}
    colors = {1: DIGITAL_BLUE, 2: TILE_BLUE, 3: DIGITAL_BLUE}
    p = doc.add_paragraph()
    p.space_before = Pt(10)
    r = p.add_run(text)
    r.bold = True
    r.font.name = HEAD_FONT
    r.font.size = Pt(sizes.get(level, 13))
    r.font.color.rgb = colors.get(level, DIGITAL_BLUE)
    p.paragraph_format.space_before = Pt(14 if level <= 2 else 8)
    p.paragraph_format.space_after = Pt(4)
    return p


def _render_markdown(doc, md):
    """Markdown-lite → Word. Supports #, ##, ### headings, -/* bullets, 1. ordered,
    blank-line paragraphs, and **bold** inline. H1 inside the body is skipped (the
    title is already rendered)."""
    lines = md.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        h = re.match(r"^(#{1,4})\s+(.*)$", line)
        if h:
            lvl = len(h.group(1))
            if lvl == 1:
                # body H1 duplicates the title; demote to H2 for safety
                lvl = 2
            _heading(doc, h.group(2).strip(), lvl)
            i += 1
            continue
        mb = re.match(r"^[-*]\s+(.*)$", line)
        if mb:
            p = doc.add_paragraph(style="List Bullet")
            _runs_with_bold(p, mb.group(1).strip())
            i += 1
            continue
        mo = re.match(r"^\d+[.)]\s+(.*)$", line)
        if mo:
            p = doc.add_paragraph(style="List Number")
            _runs_with_bold(p, mo.group(1).strip())
            i += 1
            continue
        # paragraph: gather until blank line
        buf = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,4}\s|[-*]\s|\d+[.)]\s)", lines[i]):
            buf.append(lines[i].rstrip())
            i += 1
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(8)
        _runs_with_bold(p, " ".join(buf))


def _publish_pack(doc, seo, piece):
    """A boxed SEO publish pack at the top — the editor's checklist."""
    pk = seo.get("primary_keyword", "")
    pk = pk.get("term", "") if isinstance(pk, dict) else pk
    rows = [
        ("Type", piece.get("type", "Blog")),
        ("Primary keyword", pk),
        ("Meta title", seo.get("meta_title", "")),
        ("Meta description", seo.get("meta_description", "")),
        ("URL slug", seo.get("url_slug", "")),
        ("Schema", seo.get("schema_type", "Article")),
        ("Word target", str(piece.get("word_count_target", ""))),
    ]
    rows = [(k, v) for k, v in rows if v]
    # Rendered as a Callout-Tint box (design-system callout treatment), not a
    # theme-colored Word table style (theme accents leak off-palette colors).
    table = doc.add_table(rows=len(rows), cols=2)
    table.autofit = True
    for ri, (k, v) in enumerate(rows):
        c0, c1 = table.rows[ri].cells
        _shade_cell(c0, CALLOUT_TINT_HEX)
        _shade_cell(c1, CALLOUT_TINT_HEX)
        c0.width = Inches(1.6)
        p0 = c0.paragraphs[0]
        r0 = p0.add_run(k)
        r0.bold = True
        r0.font.name = HEAD_FONT
        r0.font.size = Pt(9)
        r0.font.color.rgb = DIGITAL_BLUE
        p1 = c1.paragraphs[0]
        r1 = p1.add_run(str(v))
        r1.font.name = BODY_FONT
        r1.font.size = Pt(9)
        r1.font.color.rgb = INK
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def _faq(doc, faq):
    if not faq:
        return
    _heading(doc, "Frequently Asked Questions", 2)
    for item in faq:
        q = item.get("q", "")
        a = item.get("a", "")
        if not q:
            continue
        pq = doc.add_paragraph()
        pq.paragraph_format.space_before = Pt(6)
        rq = pq.add_run(q)
        rq.bold = True
        rq.font.name = HEAD_FONT
        rq.font.size = Pt(12)
        rq.font.color.rgb = INK
        if a:
            pa = doc.add_paragraph()
            pa.paragraph_format.space_after = Pt(6)
            _runs_with_bold(pa, a)


def _footer(doc, contact):
    doc.add_paragraph().paragraph_format.space_before = Pt(12)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("Produced by DigitalCLIQ — Digital Strategy & Development")
    r.font.name = HEAD_FONT
    r.font.size = Pt(9)
    r.bold = True
    r.font.color.rgb = DIGITAL_BLUE
    email = contact.get("email", APPROVED_EMAIL) if contact else APPROVED_EMAIL
    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r2 = p2.add_run(f"{email}  •  digitalcliq.com")
    r2.font.name = BODY_FONT
    r2.font.size = Pt(8)
    r2.font.color.rgb = WARM_GREY


def _slugify(s):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (s or "piece")).strip("-").lower()
    return s[:60] or "piece"


def build_doc(piece, plan, outputs_dir, client):
    seo = piece.get("seo", {})
    contact = plan.get("contact", {})
    doc = Document()
    _set_base_style(doc)

    # Digital Blue masthead band with the WHITE knockout logo (Design-System Word
    # spec: ~0.6in band, white logo ~0.35in tall, left-aligned). The white logo must
    # NEVER sit on the bare white page — it disappears. Missing logo fails loudly.
    if not LOGO_PATH.exists():
        raise FileNotFoundError(
            f"DigitalCLIQ logo not found at canonical path: {LOGO_PATH}. "
            "Fix the path; do not ship without branding.")
    band = doc.add_table(rows=1, cols=1)
    band.autofit = False
    bcell = band.rows[0].cells[0]
    bcell.width = Inches(6.5)
    _shade_cell(bcell, DIGITAL_BLUE_HEX)
    bp = bcell.paragraphs[0]
    bp.alignment = WD_ALIGN_PARAGRAPH.LEFT
    bp.paragraph_format.space_before = Pt(6)
    bp.paragraph_format.space_after = Pt(6)
    bp.add_run().add_picture(str(LOGO_PATH), height=Inches(0.35))
    doc.add_paragraph().paragraph_format.space_after = Pt(2)

    # Eyebrow + title
    eb = doc.add_paragraph()
    er = eb.add_run(f"{client}  ·  {piece.get('type', 'Blog')}  ·  {piece.get('funnel_stage', '')}".strip(" ·"))
    er.font.name = HEAD_FONT
    er.font.size = Pt(10)
    er.font.color.rgb = DIGITAL_BLUE  # eyebrow = Digital Blue on light backgrounds
    er.bold = True

    title = piece.get("outline", {}).get("h1") or piece.get("title", "Untitled")
    tp = doc.add_paragraph()
    tr = tp.add_run(title)
    tr.bold = True
    tr.font.name = HEAD_FONT
    tr.font.size = Pt(26)
    tr.font.color.rgb = DIGITAL_BLUE
    tp.paragraph_format.space_after = Pt(8)

    _publish_pack(doc, seo, piece)

    # Hero image
    aid = piece.get("asset_id")
    amap = {a["id"]: a for a in plan.get("assets", [])}
    hero = amap.get(aid, {}) if aid else {}
    hero_file = hero.get("file")
    # Word can't embed WebP (raises UnrecognizedImageError); stick to PNG/JPEG.
    if hero_file and os.path.exists(hero_file) and os.path.splitext(hero_file)[1].lower() in (".png", ".jpg", ".jpeg"):
        ip = doc.add_paragraph()
        ip.alignment = WD_ALIGN_PARAGRAPH.CENTER
        try:
            ip.add_run().add_picture(hero_file, width=Inches(6.2))
        except Exception:
            pass

    # Body
    body = piece.get("body_markdown", "")
    if BANNED_EMAIL in body.lower():
        raise ValueError(f"REFUSED: banned email in body of '{title}'. Use {APPROVED_EMAIL}.")
    _render_markdown(doc, body)

    # FAQ (only if the body didn't already include an FAQ *heading*)
    if not re.search(r"(?mi)^#{1,4}\s.*frequently asked", body):
        _faq(doc, piece.get("outline", {}).get("faq", []))

    _footer(doc, contact)

    # Include the piece id in the filename so two pieces that share a url_slug
    # (or a truncated title slug) never silently overwrite each other.
    slug = seo.get("url_slug") or _slugify(title)
    pid = str(piece.get("id", "")).strip()
    suffix = f"_{_slugify(pid)}" if pid else ""
    fname = f"Blog_{_slugify(client)}_{_slugify(slug)}{suffix}.docx"
    out = os.path.join(outputs_dir, fname)
    os.makedirs(outputs_dir, exist_ok=True)
    doc.save(out)
    return out


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 write_docs.py <plan.json> <outputs_dir>")
        sys.exit(2)
    plan_path, outputs_dir = sys.argv[1], sys.argv[2]
    with open(plan_path, encoding="utf-8") as fh:
        plan = json.load(fh)
    client = plan.get("meta", {}).get("client", "Client")

    written = 0
    for piece in plan.get("pieces", []):
        if not piece.get("body_markdown"):
            print(f"  skip (no body): {piece.get('title', piece.get('id'))}")
            continue
        out = build_doc(piece, plan, outputs_dir, client)
        piece["doc_path"] = out
        written += 1
        print(f"  doc -> {out}")

    with open(plan_path, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=1)
    print(f"wrote {written} doc(s); plan updated with doc_path: {plan_path}")


if __name__ == "__main__":
    main()
