#!/usr/bin/env python3
"""
Automotive Market Trend Report — blog + distribution assets
Developed by DigitalCLIQ — Digital Strategy & Development

Reads the SAME research JSON the PDF is built from and emits the companion
assets for the monthly publishing cycle:

  1. <stem>_blog.html      Paste-ready Squarespace article body + JSON-LD.
  2. <stem>_publishing-kit.md   SEO fields, LinkedIn post copy, email copy,
                                and the step-by-step publish checklist.

Design intent: the BLOG POST is the canonical asset, not the PDF. HTML is what
ranks in Google and what AI answer engines (ChatGPT, Perplexity, AI Overviews)
can actually cite. The PDF is the download and the LinkedIn native document.

Usage:
    python3 generate_blog_assets.py <json_path> <output_dir> [pdf_filename]
"""

import json
import os
import re
import sys

VAULT = "/Users/drewmoon/Desktop/DigitalCLIQ Brain/DigitalCLIQ Brain"
ARCHIVE_DIR = f"{VAULT}/Intelligence/market/auto-trends"

BLUE = "#405FAB"
SKY = "#6B9DD4"
GREY = "#949592"
TINT = "#EDF2F9"
BORDER = "#D8E1F0"
SANS = "'Dosis', sans-serif"
SERIF = "'Roboto Slab', Georgia, serif"


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)


def _period(meta):
    if meta.get("period_label"):
        return meta["period_label"]
    import datetime
    try:
        return datetime.date.fromisoformat(
            meta.get("generation_date", "")).strftime("%B %Y")
    except Exception:
        return "the current period"


def _sections(data):
    """The four content sections in report order."""
    return [
        ("new_vehicle_sales", "new vehicle sales"),
        ("used_vehicle_sales", "used vehicle sales"),
        ("fixed_ops", "service and fixed operations"),
        ("parts", "parts"),
    ]


def _metrics(sec):
    return sec.get("national", {}).get("metrics", []) or sec.get("metrics", [])


def _all_metrics(data):
    out = []
    for key, _ in _sections(data):
        for m in _metrics(data.get(key, {})):
            out.append((key, m))
    return out


# ── blog article ──────────────────────────────────────────────
def _key_numbers_table(data):
    """Numbers table high on the page. Answer engines lift tables verbatim, so
    this is the single highest-value block for AI citation."""
    stats = data.get("executive_summary", {}).get("headline_stats") or []
    rows = []
    if stats:
        for s in stats:
            rows.append((s.get("value", ""), s.get("label", ""), s.get("source", "")))
    else:
        for key, m in _all_metrics(data)[:6]:
            detail = m.get("detail", "")
            src = ""
            mt = re.search(r"\(([^()]+)\)\s*\.?\s*$", detail.strip())
            if mt:
                src = mt.group(1).strip()
            rows.append((m.get("value", ""), m.get("label", ""), src))
    if not rows:
        return ""
    # Drop the Source column entirely when nothing populates it. An empty column
    # reads as a broken table, which is worse than three tidy columns.
    has_src = any(s for _, _, s in rows)
    cell = f'padding:10px 12px;border-bottom:1px solid {BORDER};'
    head = f'text-align:left;padding:10px 12px;background:{BLUE};color:#fff;font-family:{SANS};'
    trs = "".join(
        f'<tr>'
        f'<td style="{cell}font-family:{SANS};font-weight:700;color:{BLUE};white-space:nowrap;">{esc(v)}</td>'
        f'<td style="{cell}">{esc(l)}</td>'
        + (f'<td style="{cell}color:{GREY};font-size:0.85em;">{esc(s)}</td>' if has_src else "")
        + '</tr>' for v, l, s in rows)
    src_th = f'<th style="{head}">Source</th>' if has_src else ""
    return (
        f'<h2 id="key-numbers">The numbers at a glance</h2>\n'
        f'<table style="width:100%;border-collapse:collapse;margin:18px 0;font-family:{SERIF};font-size:0.95em;">\n'
        f'<thead><tr>'
        f'<th style="{head}">Figure</th>'
        f'<th style="{head}">What it measures</th>'
        f'{src_th}'
        f'</tr></thead>\n<tbody>{trs}</tbody></table>\n')


def _section_html(sec, label, region):
    """One content section. H2 is phrased as a question because that is the
    shape answer engines match against user prompts."""
    title = sec.get("headline") or sec.get("section_title") or label.title()
    q = f"What is happening in {label}?"
    parts = [f'<h2 id="{slugify(label)}">{esc(q)}</h2>']
    if sec.get("headline") or sec.get("section_title"):
        parts.append(f'<p><strong>{esc(title)}.</strong> {esc(sec.get("summary", ""))}</p>')
    elif sec.get("summary"):
        parts.append(f'<p>{esc(sec["summary"])}</p>')

    mets = _metrics(sec)
    if mets:
        lis = []
        for m in mets[:6]:
            detail = (m.get("detail", "") or "").strip()
            lis.append(
                f'<li style="margin:8px 0;"><strong>{esc(m.get("label",""))}: '
                f'{esc(m.get("value",""))}.</strong> {esc(detail)}</li>')
        parts.append(f'<ul style="padding-left:20px;">{"".join(lis)}</ul>')

    reg = sec.get("regional", {})
    if reg.get("summary"):
        parts.append(
            f'<blockquote style="margin:18px 0;padding:14px 18px;background:{TINT};'
            f'border-left:3px solid {BLUE};border-radius:0 10px 10px 0;">'
            f'<strong style="font-family:{SANS};color:{BLUE};text-transform:uppercase;'
            f'letter-spacing:0.06em;font-size:0.85em;">{esc(region)}:</strong> '
            f'{esc(reg["summary"])}</blockquote>')

    for extra in ("ev_readiness", "technician_market", "oem_vs_aftermarket", "ev_impact"):
        if sec.get(extra):
            parts.append(f'<p>{esc(sec[extra])}</p>')

    o6, o12 = sec.get("outlook_6mo", ""), sec.get("outlook_12mo", "")
    if o6 or o12:
        parts.append(f'<h3>Outlook for {esc(label)}</h3>')
        if o6:
            parts.append(f'<p><strong>Next 6 months.</strong> {esc(o6)}</p>')
        if o12:
            parts.append(f'<p><strong>Next 12 months.</strong> {esc(o12)}</p>')
    return "\n".join(parts)


def _faq(data, region, period):
    """FAQPage JSON-LD needs visible on-page Q&A to be legitimate. These pull
    from real report content, never invented."""
    ex = data.get("executive_summary", {})
    so = data.get("strategic_outlook", {})
    qs = []
    if ex.get("overview"):
        qs.append((f"How is the {region} automotive market performing in {period}?",
                   ex["overview"]))
    if ex.get("throughline"):
        qs.append(("What is the single biggest factor driving the market right now?",
                   ex["throughline"]))
    nv = data.get("new_vehicle_sales", {})
    if nv.get("outlook_12mo"):
        qs.append(("What is the 12-month outlook for new vehicle sales?",
                   nv["outlook_12mo"]))
    fo = data.get("fixed_ops", {})
    if fo.get("outlook_6mo"):
        qs.append(("What is the outlook for dealership service and fixed operations?",
                   fo["outlook_6mo"]))
    if so.get("risks"):
        qs.append(("What are the biggest risks for dealers to monitor?",
                   " ".join(so["risks"][:3])))
    return qs


def _jsonld(data, region, period, title, description, canonical_url):
    meta = data.get("metadata", {})
    date = meta.get("generation_date", "")
    article = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": description,
        "datePublished": date,
        "dateModified": date,
        "author": {"@type": "Organization", "name": "DigitalCLIQ",
                   "url": "https://www.digitalcliq.com"},
        "publisher": {"@type": "Organization", "name": "DigitalCLIQ",
                      "url": "https://www.digitalcliq.com"},
        "about": [region, "automotive retail", "dealership marketing"],
        "citation": data.get("sources", []),
    }
    if canonical_url:
        article["mainEntityOfPage"] = {"@type": "WebPage", "@id": canonical_url}

    faq = _faq(data, region, period)
    blocks = [json.dumps(article, indent=2)]
    if faq:
        blocks.append(json.dumps({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q,
                 "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faq],
        }, indent=2))
    return "\n".join(
        f'<script type="application/ld+json">\n{b}\n</script>' for b in blocks)


def build_blog_html(data, pdf_filename=None, canonical_url=""):
    meta = data.get("metadata", {})
    region = meta.get("region", "Southern California")
    period = _period(meta)
    ex = data.get("executive_summary", {})

    title = f"{region} Automotive Market Trends: {period}"
    description = _clip(ex.get("overview", ""), 155)

    body = [f'<h1>{esc(title)}</h1>']
    body.append(
        f'<p style="font-size:1.12em;line-height:1.6;color:#333;">'
        f'{esc(ex.get("overview", ""))}</p>')
    body.append(
        f'<p style="color:{GREY};font-size:0.9em;">Published {esc(period)} by '
        f'<strong>DigitalCLIQ</strong>. New and used vehicle sales, service and fixed '
        f'operations, and parts, with 6 and 12 month outlooks for {esc(region)}. '
        f'Every figure below is sourced and dated.</p>')

    body.append(_key_numbers_table(data))

    if ex.get("throughline"):
        body.append(
            f'<h2 id="throughline">The throughline</h2>\n'
            f'<p>{esc(ex["throughline"])}</p>')

    if ex.get("key_trends"):
        lis = "".join(f'<li style="margin:6px 0;">{esc(t)}</li>'
                      for t in ex["key_trends"])
        body.append(f'<h2 id="key-trends">Key trends this month</h2>\n'
                    f'<ul style="padding-left:20px;">{lis}</ul>')

    for key, label in _sections(data):
        if data.get(key):
            body.append(_section_html(data[key], label, region))

    so = data.get("strategic_outlook", {})
    if so:
        body.append('<h2 id="what-to-do">What should a dealer do about it?</h2>')
        for heading, items in (("Next 6 months", so.get("short_term", [])),
                               ("Next 12 months", so.get("medium_term", [])),
                               ("Risks to monitor", so.get("risks", [])),
                               ("Opportunities to pursue", so.get("opportunities", []))):
            if items:
                lis = "".join(f'<li style="margin:6px 0;">{esc(i)}</li>' for i in items)
                body.append(f'<h3>{esc(heading)}</h3>'
                            f'<ul style="padding-left:20px;">{lis}</ul>')

    faq = _faq(data, region, period)
    if faq:
        body.append('<h2 id="faq">Frequently asked questions</h2>')
        for q, a in faq:
            body.append(f'<h3>{esc(q)}</h3><p>{esc(a)}</p>')

    if data.get("sources"):
        lis = "".join(f'<li style="margin:4px 0;">{esc(s)}</li>'
                      for s in data["sources"])
        body.append(f'<h2 id="sources">Sources</h2>'
                    f'<ol style="padding-left:20px;color:#444;font-size:0.92em;">{lis}</ol>')

    if pdf_filename:
        body.append(
            f'<p style="margin:26px 0;padding:18px 20px;background:{TINT};'
            f'border-radius:12px;border:1px solid {BORDER};">'
            f'<strong style="font-family:{SANS};color:{BLUE};">Get the full report.</strong> '
            f'The complete {esc(period)} {esc(region)} market report is available as a '
            f'designed PDF. <a href="REPLACE_WITH_SQUARESPACE_FILE_URL">Download it here</a>.</p>')

    body.append(
        f'<p style="margin-top:30px;color:#444;">DigitalCLIQ is a {esc(region)} digital '
        f'marketing agency built for automotive retail. We pair strategy with execution '
        f'across paid media, SEO, reputation, analytics, and creative. '
        f'<a href="https://www.digitalcliq.com">Talk to us</a>.</p>')

    article_html = "\n\n".join(b for b in body if b)
    jsonld = _jsonld(data, region, period, title, description, canonical_url)

    return f"""<!-- ============================================================
     DigitalCLIQ · {title}
     PASTE-READY SQUARESPACE ARTICLE BODY

     HOW TO USE
     1. Squarespace blog post > add a Code Block.
     2. Paste everything between BEGIN ARTICLE and END ARTICLE.
     3. Paste the JSON-LD block into Settings > Advanced > Page Header
        Code Injection (or a second Code Block at the foot of the post).
     4. Replace REPLACE_WITH_SQUARESPACE_FILE_URL with the uploaded PDF link.
     SEO fields are in the companion publishing kit.
     ============================================================ -->

<!-- BEGIN ARTICLE -->
<style>
/* Scoped so it cannot leak into the rest of the Squarespace template.
   Dosis carries structure, Roboto Slab carries reading, per the DigitalCLIQ
   Design System. Both fall back gracefully if the theme lacks them. */
.dcliq-article {{ font-family:{SERIF}; line-height:1.65; color:#111; max-width:760px; }}
.dcliq-article h1, .dcliq-article h2, .dcliq-article h3 {{
  font-family:{SANS}; font-weight:700; line-height:1.15; color:#111; }}
.dcliq-article h1 {{ font-size:2.1em; margin:0 0 .5em; }}
.dcliq-article h2 {{ font-size:1.5em; margin:1.6em 0 .5em; color:{BLUE}; }}
.dcliq-article h3 {{ font-size:1.15em; margin:1.3em 0 .4em; }}
.dcliq-article a {{ color:{BLUE}; }}
.dcliq-article table {{ display:block; overflow-x:auto; }}
@media (max-width:600px) {{ .dcliq-article h1 {{ font-size:1.6em; }} }}
</style>
<div class="dcliq-article">
{article_html}
</div>
<!-- END ARTICLE -->

<!-- BEGIN JSON-LD (structured data for Google + AI answer engines) -->
{jsonld}
<!-- END JSON-LD -->
"""


def _clip(text, n):
    text = (text or "").strip().replace("\n", " ")
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0].rstrip(",;:.") + "."


# ── LinkedIn + email ──────────────────────────────────────────
def build_linkedin_post(data):
    """Drafts the LinkedIn copy in DigitalCLIQ voice: direct, data-backed, dry,
    no fluff, no em dashes. Native document post, link in the first comment,
    because LinkedIn throttles outbound links in the post body."""
    meta = data.get("metadata", {})
    region = meta.get("region", "Southern California")
    period = _period(meta)
    ex = data.get("executive_summary", {})

    stats = ex.get("headline_stats") or []
    if not stats:
        stats = [{"value": m.get("value", ""), "label": m.get("label", ""),
                  "source": ""} for _, m in _all_metrics(data)[:4]]

    lines = []
    hook = _clip(ex.get("throughline") or ex.get("overview", ""), 180)
    lines.append(hook)
    lines.append("")
    lines.append(f"Here is where the {region} market actually sits in {period}:")
    lines.append("")
    for s in stats[:4]:
        src = f" ({s['source']})" if s.get("source") else ""
        lines.append(f"› {s.get('value','')} {s.get('label','')}{src}")
    lines.append("")

    so = data.get("strategic_outlook", {})
    if so.get("short_term"):
        lines.append("What that means for the next two quarters:")
        for item in so["short_term"][:3]:
            lines.append(f"› {item}")
        lines.append("")

    lines.append(f"Full breakdown in the document below. New and used, fixed ops, "
                 f"and parts, with 6 and 12 month outlooks. Every number sourced "
                 f"and dated, so you can check the work.")
    lines.append("")
    lines.append("Written for the GMs who want this research without doing it themselves.")
    lines.append("")
    lines.append("#automotive #dealership #cardealers #fixedops #automotivemarketing")

    post = "\n".join(lines)
    comment = (f"Full {period} report with sources and the 6 and 12 month outlooks: "
               f"[BLOG POST URL]")
    return post, comment


def build_email(data):
    meta = data.get("metadata", {})
    region = meta.get("region", "Southern California")
    period = _period(meta)
    ex = data.get("executive_summary", {})
    subject = f"{region} auto market, {period}: what changed"
    body = f"""Hi {{first_name}},

Our {period} {region} market report is out.

{_clip(ex.get('overview', ''), 320)}

The short version:

"""
    for t in (ex.get("key_trends") or [])[:4]:
        body += f"  . {t}\n"
    body += f"""
Full report here: [BLOG POST URL]

New and used vehicle sales, service and fixed operations, and parts, with 6 and
12 month outlooks. Every figure is sourced and dated.

If you want the read on what this means for your store specifically, reply and
we will walk it through.

Drew Moon
Founder, DigitalCLIQ
drewmoon@digitalcliq.com
"""
    return subject, body


def build_publishing_kit(data, pdf_filename, blog_filename):
    meta = data.get("metadata", {})
    region = meta.get("region", "Southern California")
    period = _period(meta)
    ex = data.get("executive_summary", {})
    title = f"{region} Automotive Market Trends: {period}"
    slug = slugify(f"{region}-auto-market-trends-{period}")
    desc = _clip(ex.get("overview", ""), 155)

    post, comment = build_linkedin_post(data)
    subject, email_body = build_email(data)

    kws = [f"{region.lower()} auto market", f"{region.lower()} car sales {period.split()[-1]}",
           "dealership fixed operations trends", "used car prices",
           "automotive market outlook", "new vehicle SAAR"]

    return f"""---
type: publishing-kit
date: {meta.get('generation_date', '')}
project: DigitalCLIQ
status: ready-to-publish
tags: [auto-trends, content, distribution]
---

Publishing kit for the {period} [[DigitalCLIQ]] Automotive Market Trend Report.
Deliverables: `{pdf_filename}` (PDF) and `{blog_filename}` (blog HTML).

> [!important] Publish order
> Blog post FIRST, so the canonical URL exists. Then LinkedIn, then email. The
> blog post is the asset that ranks and that AI answer engines cite. The PDF is
> the download and the LinkedIn native document.

## 1. Squarespace blog post

| Field | Value |
|---|---|
| Title | {title} |
| URL slug | {slug} |
| Meta description | {desc} |
| Excerpt | {_clip(ex.get('overview', ''), 200)} |
| Tags | Automotive, Market Research, Dealership, {region} |
| Category | Market Intelligence |
| OG image | Page 2 of the PDF exported as PNG |

**Steps**
1. New blog post, set the title and slug above.
2. Add a Code Block. Paste everything between `BEGIN ARTICLE` and `END ARTICLE` from `{blog_filename}`.
3. Upload `{pdf_filename}` via a text-block file link. Copy the resulting `/s/...pdf` URL.
4. Replace `REPLACE_WITH_SQUARESPACE_FILE_URL` in the post with that URL.
5. Paste the JSON-LD block into Settings > Advanced > Page Header Code Injection.
6. Set the meta description and excerpt. Publish.

**Target keywords:** {", ".join(kws)}

## 2. LinkedIn

Post the PDF as a NATIVE DOCUMENT, not a link. LinkedIn suppresses reach on
posts with outbound links in the body, so the blog URL goes in the first comment.

**Post copy**

```
{post}
```

**First comment (post immediately after publishing)**

```
{comment}
```

## 3. Email

**Subject:** {subject}

```
{email_body}
```

## Checklist

- [ ] Blog post published, canonical URL captured
- [ ] PDF uploaded to Squarespace, download link swapped into the post
- [ ] JSON-LD injected and validated (search.google.com/test/rich-results)
- [ ] LinkedIn document post live, blog URL in first comment
- [ ] Email sent
- [ ] Research JSON archived to `Intelligence/market/auto-trends/`
"""


# ── entry point ───────────────────────────────────────────────
def _fmt_metric_rows(metrics):
    rows = []
    for m in metrics:
        detail = (m.get("detail", "") or "").strip()
        src = ""
        mt = re.search(r"\(([^()]+)\)\s*\.?\s*$", detail)
        if mt:
            src = mt.group(1).strip()
            detail = detail[:mt.start()].strip().rstrip(",;. ")
        rows.append(f"| {m.get('label','')} | **{m.get('value','')}** | {detail} | {src} |")
    return rows


def build_market_read(data):
    """The rolling canonical market note. Overwritten every run so it is ALWAYS
    the current read. This is the file other skills and sessions are pointed at,
    because a raw JSON archive is invisible to Obsidian search and wikilinks."""
    meta = data.get("metadata", {})
    region = meta.get("region", "Southern California")
    period = _period(meta)
    date = meta.get("generation_date", "")
    ex = data.get("executive_summary", {})

    L = []
    L.append("---")
    L.append("type: market-read")
    L.append("status: active")
    L.append(f"updated: {date}")
    L.append(f"period: {period}")
    L.append(f"region: {region}")
    L.append("tags: [market, automotive, auto-trends, source-of-truth]")
    L.append("---")
    L.append("")
    L.append(f"The current [[DigitalCLIQ]] read on the {region} automotive market, "
             f"as of **{period}**. Regenerated by the `auto-trends` skill on the 5th "
             f"of every month, so this file is always the latest published figures. "
             f"Every number below carries its source and period.")
    L.append("")
    L.append("> [!important] Use this before researching the market yourself")
    L.append("> Any skill or session that needs automotive market context (regional "
             "sales direction, used values, fixed-ops benchmarks, parts trends) reads "
             "THIS file first. Only go research the market live if the `updated` date "
             "above is more than one month stale, or if you need a figure not covered "
             "here. Cite the source shown, never this file alone.")
    L.append("")

    if ex.get("throughline"):
        L.append("## The current throughline")
        L.append("")
        L.append(ex["throughline"])
        L.append("")

    stats = ex.get("headline_stats") or []
    if stats:
        L.append("## Headline numbers")
        L.append("")
        L.append("| Figure | What it measures | Source |")
        L.append("|---|---|---|")
        for s in stats:
            L.append(f"| **{s.get('value','')}** | {s.get('label','')} | {s.get('source','')} |")
        L.append("")

    reg = data.get("new_vehicle_sales", {}).get("regional", {})
    L.append(f"## {region} specifics")
    L.append("")
    if reg.get("summary"):
        L.append(reg["summary"])
        L.append("")
    reg_metrics = reg.get("metrics", [])
    if reg_metrics:
        L.append("| Submarket / metric | Value | Detail | Source |")
        L.append("|---|---|---|---|")
        L.extend(_fmt_metric_rows(reg_metrics))
        L.append("")

    L.append("## By department")
    L.append("")
    for key, label in _sections(data):
        sec = data.get(key, {})
        mets = _metrics(sec)
        if not mets:
            continue
        head = sec.get("headline") or sec.get("section_title") or label.title()
        L.append(f"### {label.title()}: {head}")
        L.append("")
        L.append("| Metric | Value | Detail | Source |")
        L.append("|---|---|---|---|")
        L.extend(_fmt_metric_rows(mets))
        L.append("")
        if sec.get("outlook_6mo"):
            L.append(f"**Next 6 months.** {sec['outlook_6mo']}")
            L.append("")

    so = data.get("strategic_outlook", {})
    if so.get("risks"):
        L.append("## Risks on the board")
        L.append("")
        for r in so["risks"]:
            L.append(f"- {r}")
        L.append("")
    if so.get("opportunities"):
        L.append("## Open opportunities")
        L.append("")
        for o in so["opportunities"]:
            L.append(f"- {o}")
        L.append("")

    stamp = date[:7] if len(date) >= 7 else "unknown"
    L.append("## Provenance")
    L.append("")
    L.append(f"Generated from `{stamp}.json` in this folder, which holds the full "
             f"research payload including every outlook paragraph and all "
             f"{len(data.get('sources', []))} sources. Month-by-month history and "
             f"deltas: [[Intelligence/market/auto-trends/README|the archive index]]. "
             f"Category-level context that changes slowly lives in [[Context/market]].")
    L.append("")
    L.append("### Sources this period")
    L.append("")
    for s in data.get("sources", []):
        L.append(f"- {s}")
    L.append("")
    return "\n".join(L)


def build_archive_index(archive_dir):
    """Index every archived month with its headline numbers so the trend is
    readable at a glance. Rebuilt from the archives themselves, so it can never
    drift from what is actually on disk."""
    months = sorted([f[:-5] for f in os.listdir(archive_dir)
                     if f.endswith(".json")], reverse=True)
    L = []
    L.append("---")
    L.append("type: index")
    L.append("status: active")
    L.append("tags: [market, automotive, auto-trends, archive]")
    L.append("---")
    L.append("")
    L.append("Month-by-month archive of the [[DigitalCLIQ]] automotive market trend "
             "research. The `auto-trends` skill writes one payload here per run and "
             "reads the most recent one before researching, so each month is a delta "
             "against the last rather than a fresh start.")
    L.append("")
    L.append("> [!tip] Looking for the current read?")
    L.append("> Use [[Intelligence/market/auto-trends/Market-Read|Market-Read]]. It is "
             "always the latest month in readable form. The JSON files here are the "
             "raw payloads behind it.")
    L.append("")
    L.append("## Headline trend by month")
    L.append("")
    L.append("| Month | Throughline | Headline figures |")
    L.append("|---|---|---|")
    for mo in months:
        try:
            with open(os.path.join(archive_dir, f"{mo}.json")) as f:
                d = json.load(f)
        except Exception:
            continue
        ex = d.get("executive_summary", {})
        tl = _clip(ex.get("throughline") or ex.get("overview", ""), 150)
        figs = " · ".join(
            f"{s.get('value','')} {s.get('label','')}"
            for s in (ex.get("headline_stats") or [])[:3])
        L.append(f"| `{mo}` | {tl} | {_clip(figs, 220)} |")
    L.append("")
    L.append(f"{len(months)} month(s) archived. "
             f"Deltas become meaningful from the second month onward.")
    L.append("")
    return "\n".join(L)


def archive_json(data, json_path):
    """Archive the run so next month can diff against it. This is what makes
    the report a series with month-over-month deltas instead of a standalone."""
    meta = data.get("metadata", {})
    date = meta.get("generation_date", "")
    stamp = date[:7] if len(date) >= 7 else "unknown"
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    dest = f"{ARCHIVE_DIR}/{stamp}.json"
    with open(dest, "w") as f:
        json.dump(data, f, indent=2)
    return dest


def main(json_path, out_dir, pdf_filename=None):
    with open(json_path) as f:
        data = json.load(f)
    meta = data.get("metadata", {})
    date = meta.get("generation_date", "")
    stem = f"Auto_Trends_Report_{date}"
    pdf_filename = pdf_filename or f"{stem}.pdf"
    blog_filename = f"{stem}_blog.html"

    os.makedirs(out_dir, exist_ok=True)

    blog_path = os.path.join(out_dir, blog_filename)
    with open(blog_path, "w") as f:
        f.write(build_blog_html(data, pdf_filename))

    kit_path = os.path.join(out_dir, f"{stem}_publishing-kit.md")
    with open(kit_path, "w") as f:
        f.write(build_publishing_kit(data, pdf_filename, blog_filename))

    archived = archive_json(data, json_path)

    # Refresh the vault-facing notes. These are what other skills and Obsidian
    # search can actually see; the JSON alone is invisible to both.
    read_path = os.path.join(ARCHIVE_DIR, "Market-Read.md")
    with open(read_path, "w") as f:
        f.write(build_market_read(data))
    index_path = os.path.join(ARCHIVE_DIR, "README.md")
    with open(index_path, "w") as f:
        f.write(build_archive_index(ARCHIVE_DIR))

    print(f"Blog HTML:      {blog_path}")
    print(f"Publishing kit: {kit_path}")
    print(f"Archived JSON:  {archived}")
    print(f"Market read:    {read_path}")
    print(f"Archive index:  {index_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 generate_blog_assets.py <json_path> <output_dir> [pdf_filename]")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
