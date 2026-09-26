#!/usr/bin/env python3
"""Render a Friday GM note (Drew-editable markdown) to a one-page DigitalCLIQ PDF.

Spec: .claude/skills/ai-team/references/gm-note-template.md
Design: Resources/design-system/Design-System.md (PDF: HTML + CSS, Chrome headless
print-to-pdf fallback because WeasyPrint cannot load gobject/pango on this Mac).

  python3 .claude/skills/ai-team/scripts/gm_note.py outputs/ai-team/gm-notes/2026-09-25/NOI.md
  add --keep-html to leave the intermediate HTML next to the PDF (debugging only)

Reads {CODE}.md, writes {CODE}.pdf beside it. Only these H2 sections render, in this order:
Opening, What we watched, What we caught, The one number that moved, What we need from you,
Sign-off. Every other H2 (for example "For Drew") and every %%comment%% is never rendered.

Gates (non-zero exit, nothing half-shipped):
  2  content: em dash, placeholder, over the word cap, wrong item counts, ask with no addressee
  3  a dollar figure, percentage, or large number in the note is missing from {CODE}.facts.json
  4  render: Chrome failed, logo missing, more than one page, or a font other than Dosis / Roboto Slab
Standard library plus PyMuPDF (fitz). Runs from the vault root.
"""
import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

VAULT = "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# WHITE knockout mark: only on the Digital Blue masthead band (vault-facts, Branding).
LOGO_WHITE = os.path.join(VAULT, "Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png")

WORD_CAP_HARD = 360   # the renderer refuses above this
WORD_CAP_SOFT = 330   # the template's target; above this prints a warning
SECTIONS = {
    "opening": "opening",
    "what we watched": "watched",
    "what we caught": "caught",
    "the one number": "number",
    "what we need from you": "asks",
    "sign-off": "signoff",
    "sign off": "signoff",
}
PLACEHOLDERS = re.compile(r"\{\{?[A-Za-z_ ]+\}?\}|\bTK\b|\bXX\b|\bTODO\b|\bTBD\b|lorem ipsum|YYYY", re.I)


def die(code, msg):
    print(f"GM-NOTE FAILED ({code}): {msg}", file=sys.stderr)
    sys.exit(code)


def parse_frontmatter(text):
    meta = {}
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end == -1:
            die(2, "frontmatter opened but never closed")
        for line in text[3:end].splitlines():
            m = re.match(r"^([A-Za-z_]+):\s*(.*)$", line.strip())
            if m:
                meta[m.group(1).lower()] = m.group(2).strip().strip('"')
        text = text[end + 4:]
    return meta, text


def split_sections(body):
    body = re.sub(r"%%.*?%%", "", body, flags=re.S)  # Obsidian comments never render
    out, cur = {}, None
    for line in body.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            head = m.group(1).lower()
            cur = next((v for k, v in SECTIONS.items() if head.startswith(k)), None)
            if cur:
                out[cur] = []
            continue
        if re.match(r"^#\s", line):
            cur = None
            continue
        if cur:
            out[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def inline(s):
    s = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", s)
    s = re.sub(r"\[\[([^\]]+)\]\]", r"\1", s)
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    # keep "Sept 15" and "top 3" on one line
    s = re.sub(r"\b(Jan|Feb|Mar|Apr|May|June|July|Aug|Sept|Oct|Nov|Dec)\.? (\d)", r"\1&nbsp;\2", s)
    s = re.sub(r"\b(top|of) (\d)", r"\1&nbsp;\2", s)
    # never split a hyphenated word such as "mid-August" across lines
    s = re.sub(r"\b([A-Za-z]+-[A-Za-z]+)\b", r'<span style="white-space:nowrap">\1</span>', s)
    return s


def paragraphs(block):
    return [" ".join(p.split()) for p in re.split(r"\n\s*\n", block) if p.strip()]


def parse_caught(block):
    items = []
    for line in block.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^\d+[.)]\s+(.*)$", s)
        if m:
            items.append({"text": m.group(1), "source": ""})
        elif items and s.lower().startswith("source:"):
            items[-1]["source"] = s.split(":", 1)[1].strip()
        elif items:
            items[-1]["text"] += " " + s
    return items


def parse_asks(block):
    items = []
    for line in block.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("- ") or s.startswith("* "):
            items.append(s[2:].strip())
        elif items:
            items[-1] += " " + s
        else:
            items.append(s)
    return items


def parse_number(block):
    num = {"number": "", "caption": "", "source": "", "label": "The one number that moved"}
    for line in block.splitlines():
        m = re.match(r"^\s*(number|caption|source|label):\s*(.+)$", line, re.I)
        if m:
            num[m.group(1).lower()] = m.group(2).strip()
    return num


def words(s):
    return len(re.findall(r"[A-Za-z0-9$%][A-Za-z0-9$%,.'/-]*", s))


def fmt_date(iso):
    try:
        d = dt.date.fromisoformat(iso)
        return d.strftime("%B ") + str(d.day) + d.strftime(", %Y")
    except ValueError:
        return iso


def figures(text):
    """Dollar amounts, percentages, and numbers that are 32+ or carry a comma or decimal.
    Small bare integers (days of the month, counts like 'top 3') are left to the reviewer."""
    found = set()
    for m in re.finditer(r"\$?\d[\d,]*(?:\.\d+)?%?", text):
        tok = m.group(0).rstrip(",.")
        core = tok.replace("$", "").replace("%", "").replace(",", "")
        try:
            val = float(core)
        except ValueError:
            continue
        if 2020 <= val <= 2035 and "$" not in tok and "%" not in tok and "," not in tok:
            continue  # a year
        if tok.startswith("$") or tok.endswith("%") or "," in tok or "." in core or val >= 32:
            found.add(tok)
    return found


def norm(tok):
    return tok.replace(",", "").replace("$", "").rstrip("%")


def validate(meta, sec, caught, asks, num, facts_path):
    problems = []
    for key in ("opening", "watched", "caught", "number", "asks", "signoff"):
        if not sec.get(key):
            problems.append(f"missing section: {key}")
    if not 1 <= len(caught) <= 3:
        problems.append(f"What we caught needs 1 to 3 items, found {len(caught)}")
    if len(asks) > 3:
        problems.append(f"What we need from you allows 3 asks at most, found {len(asks)}")
    for a in asks:
        if not (re.match(r"^\*\*[^*]+,[^*]+:\*\*", a) or a.lower().startswith("nothing needed")):
            problems.append(f"ask must open with **Name, Role:** from the store README: {a[:60]}")
    for c in caught:
        if not c["text"].startswith("**"):
            problems.append(f"caught item must open with a **bold headline**: {c['text'][:60]}")
        if not c["source"]:
            problems.append(f"caught item has no Source: line: {c['text'][:60]}")
    if not (num["number"] and num["caption"] and num["source"]):
        problems.append("The one number needs Number:, Caption:, and Source: lines")
    for k in ("store", "to", "date", "week"):
        if not meta.get(k):
            problems.append(f"frontmatter missing {k}:")

    client = "\n".join([sec.get("opening", ""), sec.get("watched", ""),
                        " ".join(c["text"] + " " + c["source"] for c in caught),
                        num["number"], num["caption"], num["source"], " ".join(asks),
                        sec.get("signoff", ""), meta.get("week", ""), meta.get("title", "")])
    if chr(0x2014) in client or " -- " in client:
        problems.append("em dash found (Rule 14)")
    ph = PLACEHOLDERS.search(client)
    if ph:
        problems.append(f"placeholder text: {ph.group(0)}")
    body_words = words("\n".join([sec.get("opening", ""), sec.get("watched", ""),
                                  " ".join(c["text"] for c in caught), num["caption"],
                                  " ".join(asks), sec.get("signoff", "")]))
    if body_words > WORD_CAP_HARD:
        problems.append(f"{body_words} words, cap is {WORD_CAP_HARD} (target {WORD_CAP_SOFT})")
    if problems:
        die(2, "\n  " + "\n  ".join(problems))
    if body_words > WORD_CAP_SOFT:
        print(f"warning: {body_words} words, target is {WORD_CAP_SOFT}", file=sys.stderr)

    if os.path.exists(facts_path):
        with open(facts_path) as f:
            manifest = json.load(f)
        known = set()
        for fact in manifest.get("facts", []):
            for tok in figures(str(fact.get("value", "")) + " " + str(fact.get("display", ""))):
                known.add(norm(tok))
        missing = sorted(t for t in figures(client) if norm(t) not in known)
        if missing:
            die(3, "figures not in " + os.path.basename(facts_path) + ": " + ", ".join(missing))
        print(f"facts: every figure in the note is in {os.path.basename(facts_path)}")
    else:
        print(f"warning: no facts manifest at {facts_path}; write it before the reviewer runs",
              file=sys.stderr)
    return body_words


CSS = """
@page { size: 8.5in 11in; margin: 0; }
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { background: #FFFFFF; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: 'Roboto Slab', Georgia, serif; color: #000000; }
/* min-height, not height: a note that runs long grows onto a second PDF page, which check_pdf
   refuses, instead of being clipped or squeezing the masthead (seen 2026-09-23). Only x is clipped,
   for the decorative orb. */
.page { width: 8.5in; min-height: 10.99in; position: relative; overflow-x: clip;
        display: flex; flex-direction: column; background: #FFFFFF; }
.page > * { flex-shrink: 0; }
/* Tint orb sits beside the title, clear of every line of body text (Design-System motif 5). */
.orb { position: absolute; top: 0.6in; right: -2.2in; width: 4in; height: 1.8in; z-index: 0;
       background: radial-gradient(ellipse at center, rgba(107,157,212,0.12), rgba(107,157,212,0) 68%); }
.mast { position: relative; z-index: 1; height: 0.6in; background: #405FAB; display: flex;
        align-items: center; justify-content: space-between; padding: 0 0.75in; }
.mast img { height: 0.35in; width: auto; display: block; }
.mast .label { font-family: 'Dosis'; font-weight: 600; font-size: 8pt; letter-spacing: 0.22em;
               text-transform: uppercase; color: #FFFFFF; }
.body { position: relative; z-index: 1; padding: 0.32in 0.75in 0 0.75in; }
.eyebrow { font-family: 'Dosis'; font-weight: 600; font-size: 9pt; letter-spacing: 0.22em;
           text-transform: uppercase; color: #405FAB; }
h1 { font-family: 'Dosis'; font-weight: 700; font-size: 25pt; line-height: 1.08; color: #000000;
     margin-top: 6px; }
.rule { width: 48px; height: 3px; background: #6B9DD4; margin: 11px 0 11px; }
.lede { font-size: 10.2pt; line-height: 1.58; color: #000000; }
.watched { margin-top: 12px; background: #EDF2F9; border-radius: 10px; padding: 9px 14px;
           display: flex; gap: 14px; align-items: baseline; }
.watched .tag { font-family: 'Dosis'; font-weight: 600; font-size: 7.5pt; letter-spacing: 0.2em;
                text-transform: uppercase; color: #405FAB; white-space: nowrap; }
.watched p { font-size: 9.5pt; line-height: 1.5; }
.section { font-family: 'Dosis'; font-weight: 600; font-size: 12.5pt; color: #405FAB;
           margin: 14px 0 7px; letter-spacing: 0.01em; }
.card { position: relative; background: #FBFBFD; border: 1px solid #D8E1F0; border-radius: 12px;
        padding: 9px 14px 9px 12px; display: grid; grid-template-columns: 30px 1fr;
        margin-bottom: 7px; break-inside: avoid; }
.card .n { font-family: 'Dosis'; font-weight: 700; font-size: 17pt; line-height: 1; color: #405FAB;
           padding-top: 1px; }
.card p { font-size: 9.6pt; line-height: 1.5; }
.card strong { font-weight: 700; color: #000000; }
.src { font-family: 'Dosis'; font-weight: 500; font-size: 7pt; letter-spacing: 0.15em;
       text-transform: uppercase; color: #949592; margin-top: 4px; }
.stat { position: relative; overflow: hidden; margin-top: 12px; border-radius: 14px;
        background: linear-gradient(135deg, #070A15 0%, #10162A 55%, #151E37 100%);
        padding: 16px 24px 15px 24px; display: grid; grid-template-columns: auto 1fr;
        column-gap: 24px; align-items: center; break-inside: avoid; }
.stat .glow { position: absolute; right: -200px; top: -110px; width: 300px; height: 220px;
              background: radial-gradient(ellipse at center, rgba(36,53,98,0.95), rgba(36,53,98,0) 70%); }
.stat .big { position: relative; font-family: 'Dosis'; font-weight: 800; font-size: 56pt; line-height: 0.9;
             color: #6B9DD4; }
.stat .big.long { font-size: 46pt; }
.stat .txt { position: relative; }
.stat .eb { font-family: 'Dosis'; font-weight: 600; font-size: 8pt; letter-spacing: 0.22em;
            text-transform: uppercase; color: #6B9DD4; margin-bottom: 5px; }
.stat .cap { font-size: 10pt; line-height: 1.5; color: #C9D5EA; max-width: 4.3in; }
.stat .src { color: #8FA0C0; margin-top: 6px; }
.stat svg { position: absolute; top: 12px; right: 14px; width: 22px; height: 22px; }
.ask { background: #EDF2F9; border-left: 3px solid #405FAB; border-radius: 0 10px 10px 0;
       padding: 10px 16px; margin-bottom: 7px; font-size: 10pt; line-height: 1.55; break-inside: avoid; }
.ask strong { color: #000000; }
.signoff { margin-top: 12px; font-size: 10pt; line-height: 1.55; }
.signoff .name { font-family: 'Dosis'; font-weight: 600; font-size: 11pt; color: #000000; }
/* padding-top keeps the sign-off off the footer rule when the page runs full */
.foot { margin-top: auto; padding: 16px 0.75in 0.3in 0.75in; position: relative; z-index: 1; }
.foot .row { border-top: 1px solid #D8E1F0; padding-top: 8px; display: flex; justify-content: space-between;
             font-family: 'Dosis'; font-weight: 500; font-size: 7.5pt; letter-spacing: 0.15em;
             text-transform: uppercase; color: #949592; }
.pillars { margin-top: 9px; text-align: center; font-family: 'Dosis'; font-weight: 600; font-size: 7pt;
           letter-spacing: 0.3em; text-transform: uppercase; color: #949592; }
"""

CURSOR = ('<svg viewBox="0 0 100 100"><path d="M12 4 L88 58 L52 62 L68 96 L54 100 L40 68 L14 88 Z" '
          'fill="#6B9DD4" opacity="0.75" transform="rotate(-12 50 50)"/></svg>')


def build_html(meta, sec, caught, asks, num):
    store = meta["store"]
    date_txt = fmt_date(meta["date"])
    title = meta.get("title") or f"This week at {store}"
    lede = "".join(f"<p>{inline(p)}</p>" for p in paragraphs(sec["opening"]))
    watched = " ".join(paragraphs(sec["watched"]))
    cards = "".join(
        f'<div class="card"><div class="n">{i}</div><div><p>{inline(c["text"])}</p>'
        f'<div class="src">{inline(c["source"])}</div></div></div>'
        for i, c in enumerate(caught, 1))
    ask_html = "".join(f'<div class="ask">{inline(a)}</div>' for a in asks)
    sign = paragraphs(sec["signoff"])
    sign_html = "".join(
        f'<p class="name">{inline(p)}</p>' if i == len(sign) - 1 else f"<p>{inline(p)}</p>"
        for i, p in enumerate(sign))
    logo_src = "file://" + LOGO_WHITE.replace(" ", "%20")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>{html.escape(store)} Friday note</title>
<style>{CSS}</style></head><body><div class="page">
<div class="orb"></div>
<div class="mast"><img src="{logo_src}" alt="DigitalCLIQ"><div class="label">Friday note &nbsp;&middot;&nbsp; {html.escape(date_txt)}</div></div>
<div class="body">
  <div class="eyebrow">{html.escape(store)} &nbsp;&middot;&nbsp; {html.escape(meta["week"])}</div>
  <h1>{inline(title)}</h1>
  <div class="rule"></div>
  <div class="lede">{lede}</div>
  <div class="watched"><div class="tag">What we watched</div><p>{inline(watched)}</p></div>
  <div class="section">What we caught</div>
  {cards}
  <div class="stat"><div class="glow"></div>{CURSOR}
    <div class="big{' long' if len(num['number']) > 3 else ''}">{inline(num["number"])}</div>
    <div class="txt"><div class="eb">{inline(num["label"])}</div><div class="cap">{inline(num["caption"])}</div>
    <div class="src">{inline(num["source"])}</div></div></div>
  <div class="section">What we need from you</div>
  {ask_html}
  <div class="signoff">{sign_html}</div>
</div>
<div class="foot"><div class="row"><span>DigitalCLIQ &nbsp;&middot;&nbsp; Digital Strategy &amp; Development</span>
<span>Prepared for {html.escape(store)} &nbsp;&middot;&nbsp; {html.escape(date_txt)}</span></div>
<div class="pillars">Innovative &nbsp;|&nbsp; Clean &nbsp;|&nbsp; Minimalist &nbsp;|&nbsp; Bold &nbsp;|&nbsp; Resourceful</div></div>
</div></body></html>"""


def render_pdf(html_text, pdf_path, keep_html):
    if not os.path.exists(LOGO_WHITE):
        die(4, f"logo missing: {LOGO_WHITE}")
    if not os.path.exists(CHROME):
        die(4, f"Chrome not found at {CHROME}")
    tmp = tempfile.mkdtemp(prefix="gmnote-")
    html_path = os.path.join(tmp, "note.html")
    with open(html_path, "w") as f:
        f.write(html_text)
    # Same flags as the working cars-act-check generator. A --user-data-dir flag hung Chrome
    # past 120s on 2026-09-23; without it the print takes about 2 seconds.
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--no-margins",
           f"--print-to-pdf={pdf_path}", "--virtual-time-budget=4000", "file://" + html_path]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        die(4, "Chrome print-to-pdf timed out after 120s")
    if keep_html:
        shutil.copy(html_path, os.path.splitext(pdf_path)[0] + ".html")
    shutil.rmtree(tmp, ignore_errors=True)
    if p.returncode != 0 or not os.path.exists(pdf_path):
        die(4, f"Chrome print-to-pdf failed: {p.stderr.strip()[:300]}")


def check_pdf(pdf_path):
    import fitz
    doc = fitz.open(pdf_path)
    pages = doc.page_count
    fonts, images = set(), 0
    for page in doc:
        for f in page.get_fonts(full=True):
            fonts.add(f[3].split("+")[-1])
        images += len(page.get_images(full=True))
    doc.close()
    bad = sorted(f for f in fonts if not re.match(r"^(Dosis|RobotoSlab|Roboto-Slab|Roboto Slab)", f))
    if pages != 1:
        die(4, f"{pages} pages; a GM note is one page. Cut words, then re-render.")
    if bad:
        die(4, f"fonts other than Dosis / Roboto Slab embedded: {', '.join(bad)}")
    if images < 1:
        die(4, "no image embedded; the logo did not load")
    return pages, sorted(fonts)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    keep_html = "--keep-html" in sys.argv
    if len(args) != 1 or not args[0].endswith(".md"):
        print(__doc__)
        sys.exit(1)
    md_path = os.path.abspath(args[0])
    with open(md_path) as f:
        meta, body = parse_frontmatter(f.read())
    sec = split_sections(body)
    caught = parse_caught(sec.get("caught", ""))
    asks = parse_asks(sec.get("asks", ""))
    num = parse_number(sec.get("number", ""))
    stem = os.path.splitext(md_path)[0]
    n_words = validate(meta, sec, caught, asks, num, stem + ".facts.json")
    pdf_path = stem + ".pdf"
    render_pdf(build_html(meta, sec, caught, asks, num), pdf_path, keep_html)
    pages, fonts = check_pdf(pdf_path)
    print(f"ok: {pdf_path}")
    print(f"  {n_words} words, {pages} page, fonts {', '.join(fonts)}")
    print("  next: post_flight.py, render_check.py (read the PNG), then the deliverable-reviewer agent")


if __name__ == "__main__":
    main()
