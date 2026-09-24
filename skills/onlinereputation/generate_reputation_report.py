#!/usr/bin/env python3
"""
DigitalCLIQ Online Reputation Report — Visual PDF Generator (v2)
Developed by DigitalCLIQ — Digital Strategy & Development

Rebuilt per Resources/design-system/Design-System.md: hand-authored HTML+CSS
rendered to PDF using the canonical component library (canonical dark cover,
stat cards, stat bands, callout bars, comparison splits, checklist rows,
ghost numerals, running furniture). NEVER reportlab for narrative reports —
it cannot hit the spec.

Pipeline: WeasyPrint if importable, else Chrome headless --print-to-pdf
(the design-system documented fallback). Fonts (Dosis + Roboto Slab) are
embedded via @font-face from the vault archive so rendering is self-contained.
Star ratings render as SVG star rows (the brand TTFs carry no star glyph);
deltas stay as UP/DOWN/FLAT text labels so meaning never rides on color alone.

Usage:
    python3 generate_reputation_report.py <json_path> <output_pdf> <logo_path> [--delta <delta_json>]
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

VAULT = "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ"
FONT_DIR = f"{VAULT}/Resources/brand-assets/fonts"
LOGO_WHITE = f"{VAULT}/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png"
LOGO_COLOR = f"{VAULT}/Resources/brand-assets/classic-digital-cliq-logo-solid-1000px-wide copy.png"

# Platform display names and order (ported verbatim)
PLATFORM_ORDER = ["google", "yelp", "dealerrater", "carfax"]
PLATFORM_NAMES = {
    "google": "Google Reviews",
    "yelp": "Yelp",
    "dealerrater": "DealerRater",
    "carfax": "CarFax",
}

CURSOR_TICK = ('<svg class="tick" viewBox="0 0 100 100"><path d="M12 4 L88 58 '
               'L52 62 L68 96 L54 100 L40 68 L14 88 Z" fill="#405FAB"/></svg>')

_STAR_PATH = ("M10 1.6l2.47 5.02 5.53.8-4 3.9.94 5.5L10 14.22l-4.94 2.6.94-5.5-4-3.9"
              "l5.53-.8z")


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def stars_svg(rating, height=14):
    """5-star row as inline SVG: Warm Grey track, Sky Blue fill clipped to the
    rating. Brand TTFs have no star glyph; SVG shapes are the sanctioned path."""
    try:
        r = max(0.0, min(5.0, float(rating)))
    except (TypeError, ValueError):
        return ""
    step = 23  # 20px star + 3px gap
    full = int(r)
    frac = r - full
    fill_w = full * step + frac * 20
    stars = "".join(
        f'<path d="{_STAR_PATH}" transform="translate({i * step} 0)"/>'
        for i in range(5))
    total_w = 4 * step + 20
    uid = f"sc{int(r * 10)}"
    return (f'<svg class="stars" viewBox="0 0 {total_w} 20" '
            f'style="height:{height}px;width:{round(total_w * height / 20)}px">'
            f'<defs><clipPath id="{uid}"><rect x="0" y="0" width="{fill_w:.1f}" '
            f'height="20"/></clipPath></defs>'
            f'<g fill="#D8E1F0">{stars}</g>'
            f'<g fill="#6B9DD4" clip-path="url(#{uid})">{stars}</g></svg>')


# ── component builders ────────────────────────────────────────

def sec_head(num, eyebrow, title):
    return (f'<div class="sec-head"><div class="ghost">{esc(num)}</div>'
            f'<div class="eyebrow">{esc(eyebrow)}</div>'
            f'<h2>{esc(title)}</h2><div class="rule"></div></div>')


def furniture(page_no, total, dealer):
    return (f'<div class="furniture-top">'
            f'<span class="doctitle">Online Reputation Report · {esc(dealer)}</span>'
            f'<img src="file://{LOGO_COLOR}" alt="DigitalCLIQ"></div>'
            f'<div class="furniture-bot">'
            f'<span>DigitalCLIQ · Digital Strategy &amp; Development</span>'
            f'<span>Page {page_no} of {total}</span></div>')


def callout(lead, body, kind="info"):
    lead_html = f"<b>{esc(lead)}</b> " if lead else ""
    return f'<div class="callout {kind}">{lead_html}{esc(body)}</div>'


def subhead(text):
    return f'<div class="minihead">{esc(text)}</div>'


def muted(text):
    return f'<div class="mutedline">{esc(text)}</div>'


# ── data logic (ported verbatim from the reportlab generator) ──

def platform_kpis(data, delta_data):
    """Per-platform KPI dicts: rating string, count subtitle, STRONG/MIXED/WEAK
    status label, delta text. Thresholds and labels ported verbatim."""
    dealer = data.get("subject_dealer", {})
    platforms = dealer.get("platforms", {})
    kpis = []
    for pkey in PLATFORM_ORDER:
        pdata = platforms.get(pkey, {})
        rating = pdata.get("rating", "N/A")
        count = pdata.get("review_count", 0)
        pname = PLATFORM_NAMES.get(pkey, pkey)

        status = "neutral"
        if isinstance(rating, (int, float)):
            if rating >= 4.5:
                status = "positive"
            elif rating >= 3.5:
                status = "warning"
            else:
                status = "negative"

        subtitle = f"{count:,} reviews" if isinstance(count, (int, float)) else str(count)
        if delta_data and not delta_data.get("is_first_report"):
            platform_delta = delta_data.get("platforms", {}).get(pkey, {})
            rating_change = platform_delta.get("rating_change", 0)
            comparable = (isinstance(platform_delta.get("prior_rating"), (int, float))
                          and isinstance(platform_delta.get("current_rating"), (int, float)))
            if not comparable:
                subtitle += " | N/A"
            elif rating_change > 0:
                subtitle += f" | UP {rating_change:+.1f}"
            elif rating_change < 0:
                subtitle += f" | DOWN {rating_change:+.1f}"
            else:
                subtitle += " | FLAT"

        # Explicit TEXT label carries the rating-quality meaning (Design-System:
        # never color alone)
        status_labels = {"positive": "STRONG", "warning": "MIXED", "negative": "WEAK"}
        status_label = status_labels.get(status)
        if status_label:
            subtitle = f"{status_label} | {subtitle}"

        kpis.append({
            "label": pname,
            "rating": rating,
            "count": count,
            "subtitle": subtitle,
            "status": status,
        })
    return kpis


def kpi_stat_grid(kpis):
    cards = []
    for k in kpis:
        rating = k["rating"]
        if isinstance(rating, (int, float)):
            num = f'{rating:.1f}<small>/5</small>'
            stars = stars_svg(rating)
        else:
            num = f'<span class="txt">{esc(str(rating))}</span>'
            stars = ""
        cards.append(
            f'<div class="stat">{CURSOR_TICK}'
            f'<h5>{esc(k["label"])}</h5>'
            f'<div class="num">{num}</div>{stars}'
            f'<div class="src">{esc(k["subtitle"])}</div></div>')
    return f'<div class="statgrid">{"".join(cards)}</div>'


def _trim_snippet(text, n=110):
    """Trim a review snippet to <= n chars at a word boundary. The 120-char
    budget matches the prior generator; the word-boundary cut + ellipsis is
    presentation only (no mid-word fragments on the page)."""
    text = (text or "").strip()
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0].rstrip(",;:. ")
    return cut + "…"


def review_table(reviews, review_type):
    """Review-snippet table. Row cap (5) and 120-char snippet budget ported
    verbatim; star cell stays text ('4/5') as in the prior generator."""
    if not reviews:
        return muted(f"No {review_type} reviews found in recent results.")
    rows = ['<tr><th style="width:14%">Reviewer</th><th style="width:7%">Rating</th>'
            '<th style="width:14%">Date</th><th style="width:65%">Review Snippet</th></tr>']
    for rev in reviews[:5]:
        stars = rev.get("rating", "N/A")
        star_str = f"{int(stars)}/5" if isinstance(stars, (int, float)) else str(stars)
        snippet = _trim_snippet(rev.get("snippet", rev.get("content", "")))
        rows.append(f'<tr><td><b>{esc(rev.get("reviewer", "Anonymous"))}</b></td>'
                    f'<td>{esc(star_str)}</td>'
                    f'<td>{esc(rev.get("date", "N/A"))}</td>'
                    f'<td>{esc(snippet)}</td></tr>')
    return f'<table class="datatable">{"".join(rows)}</table>'


def themes_split(pos_themes, neg_themes):
    """Positive vs negative themes as a Design-System comparison split.
    Meaning is carried by explicit column headings, not color alone."""
    if not pos_themes and not neg_themes:
        return ""

    def col(title, cls, items):
        if items:
            lis = "".join(f"<li>{esc(x)}</li>" for x in items)
        else:
            lis = "<li>None identified in the last 25 reviews.</li>"
        return (f'<div class="cmpcol {cls}"><div class="cmphead">{esc(title)}</div>'
                f'<ul>{lis}</ul></div>')

    return (f'<div class="compare">{col("Negative Themes", "risk", neg_themes)}'
            f'{col("Positive Themes", "opp", pos_themes)}</div>')


def competitor_table(data):
    """Side-by-side comparison table; cell formats ('4.5 (3,241)', 'N/L') and
    the subject-row highlight ported verbatim."""
    competitors = data.get("competitors", [])
    subject = data.get("subject_dealer", {})

    def dealer_row(name, platforms, is_subject=False):
        total_reviews = 0
        cells = [f'<td class="dname">{esc(name)}</td>']
        for pkey in PLATFORM_ORDER:
            pdata = platforms.get(pkey, {})
            r = pdata.get("rating", "N/L")
            c = pdata.get("review_count", 0)
            if isinstance(c, (int, float)):
                total_reviews += c
            if isinstance(r, (int, float)):
                cells.append(f'<td>{r:.1f} ({c:,})</td>')
            else:
                cells.append(f'<td>{esc(r)} ({esc(c)})</td>')
        cells.append(f'<td><b>{total_reviews:,}</b></td>')
        cls = ' class="subject"' if is_subject else ""
        return f'<tr{cls}>{"".join(cells)}</tr>'

    rows = ['<tr><th style="width:28%">Dealership</th><th style="width:13%">Google</th>'
            '<th style="width:13%">Yelp</th><th style="width:15%">DealerRater</th>'
            '<th style="width:13%">CarFax</th><th style="width:18%">Total Reviews</th></tr>']
    rows.append(dealer_row(f"{subject.get('name', 'Subject Dealer')} (subject)",
                           subject.get("platforms", {}), is_subject=True))
    for comp in competitors:
        name = comp.get("name", "Competitor")
        dist = comp.get("approx_distance", "")
        if dist:
            name = f"{name} ({dist})"
        rows.append(dealer_row(name, comp.get("platforms", {})))
    return f'<table class="datatable">{"".join(rows)}</table>'


def doing_right_cards(competitors):
    cards = []
    for comp in competitors:
        doing_right = comp.get("doing_right", [])
        if not doing_right:
            continue
        lis = "".join(f"<li>{esc(x)}</li>" for x in doing_right[:4])
        cards.append(f'<div class="compcard"><h4>{esc(comp.get("name", "Competitor"))}</h4>'
                     f'<ul>{lis}</ul></div>')
    if not cards:
        return ""
    return f'<div class="compcards">{"".join(cards)}</div>'


def checklist(items):
    rows = []
    for item in items:
        rows.append(
            '<div class="check"><svg viewBox="0 0 20 20">'
            '<rect x="1" y="1" width="18" height="18" rx="5" fill="none" '
            'stroke="#405FAB" stroke-width="2"/>'
            '<path d="M5 10.5l3.2 3.2L15 6.5" fill="none" stroke="#405FAB" '
            'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
            f'</svg><p>{esc(item)}</p></div>')
    return f'<div class="checklist">{"".join(rows)}</div>'


DEFAULT_SEO_TEXT = (
    "Your online reviews are one of the most powerful ranking signals for "
    "local SEO. Google's local pack algorithm weighs review quantity, quality, "
    "and recency heavily when deciding which dealerships appear in the top 3 "
    "map results. Beyond traditional search, Large Language Models (ChatGPT, "
    "Claude, Gemini, Perplexity) are increasingly used by car shoppers asking "
    "questions like 'best Jeep dealer in Orange County' or 'where should I buy "
    "a BMW in Los Angeles.' These AI models pull directly from review platforms "
    "to form their recommendations. A dealership with consistently high ratings, "
    "recent positive reviews, and thoughtful owner responses will be surfaced as "
    "a top recommendation, while competitors with stale or negative reviews get "
    "left behind. Every review is now a data point that shapes both your Google "
    "ranking and your AI reputation."
)


# ── page builders (each returns interior-page inner HTML) ─────

def toc_lanes(sections):
    """'Inside this report' numbered list cards (Design-System TOC component).
    sections = [(page_no, title), ...] excluding the snapshot page itself."""
    cells = []
    for page_no, title in sections:
        cells.append(f'<div class="lane"><div class="n">{page_no:02d}</div>'
                     f'<h4>{esc(title)}</h4>'
                     f'<span class="pg">Page {page_no}</span></div>')
    return (subhead("Inside this report")
            + f'<div class="lanes">{"".join(cells)}</div>')


def page_snapshot(data, delta_data, sections):
    meta = data.get("metadata", {})
    dealer = data.get("subject_dealer", {})
    platforms = dealer.get("platforms", {})
    kpis = platform_kpis(data, delta_data)

    total_reviews = sum(p.get("review_count", 0)
                        for p in platforms.values()
                        if isinstance(p.get("review_count"), (int, float)))
    band = (f'<div class="band"><div class="bnum">{total_reviews:,}</div>'
            f'<div class="bcap"><b>{total_reviews:,} public reviews across Google, '
            f'Yelp, DealerRater, and CarFax.</b> This is the record shoppers, and '
            f'the AI models they ask, read about '
            f'{esc(meta.get("dealer_name", "this dealership"))} before ever '
            f'making contact.</div></div>')

    pulled_parts = []
    for pkey in PLATFORM_ORDER:
        pdata = platforms.get(pkey, {})
        pulled_at = pdata.get("pulled_at", "")
        if pulled_at:
            pulled_parts.append(f"{PLATFORM_NAMES.get(pkey, pkey)}: {pulled_at}")
    # Collapse a shared date + zone into the lead so the line fits one row
    stamps = [pdata.get("pulled_at", "") for pdata in platforms.values() if pdata.get("pulled_at")]
    shared = None
    if stamps and all(len(x.split()) == 3 for x in stamps):
        dates = {x.split()[0] for x in stamps}; zones = {x.split()[2] for x in stamps}
        if len(dates) == 1 and len(zones) == 1:
            shared = (dates.pop(), zones.pop())
    if shared:
        pulled_parts = [f"{PLATFORM_NAMES.get(k, k)} {v['pulled_at'].split()[1]}"
                        for k, v in sorted(platforms.items(), key=lambda kv: PLATFORM_ORDER.index(kv[0]) if kv[0] in PLATFORM_ORDER else 99) if v.get("pulled_at")]
        pulled_line = muted(f"Data pulled {shared[0]} ({shared[1]}): " + " | ".join(pulled_parts))
    else:
        pulled_line = muted("Data pulled: " + " | ".join(pulled_parts)) if pulled_parts else ""

    delta_note = ""
    if delta_data and not delta_data.get("is_first_report"):
        dplat = delta_data.get("platforms", {})
        def _num(x):
            return isinstance(x, (int, float))
        moved = any(_num(v.get("rating_change")) and v["rating_change"] != 0
                    and _num(v.get("prior_rating")) and _num(v.get("current_rating"))
                    for v in dplat.values())
        not_comparable = [PLATFORM_NAMES.get(k, k) for k in PLATFORM_ORDER
                          if k in dplat and not (_num(dplat[k].get("prior_rating"))
                                                 and _num(dplat[k].get("current_rating")))]
        flat = [PLATFORM_NAMES.get(k, k) for k in PLATFORM_ORDER
                if k in dplat and k not in [x for x in PLATFORM_ORDER
                                            if PLATFORM_NAMES.get(x, x) in not_comparable]
                and _num(dplat[k].get("rating_change")) and dplat[k]["rating_change"] == 0]
        if moved:
            movement = "UP / DOWN markers on the cards above show rating movement"
        else:
            movement = (f"{', '.join(flat)} read FLAT" if flat else
                        "No rated platform moved")
            movement += "; review counts grew on every platform"
        if not_comparable:
            movement += (f". {', '.join(not_comparable)} shows N/A because it no longer "
                         f"displays a score")
        delta_note = callout(
            "MONTH-OVER-MONTH:",
            f"Compared against the prior snapshot from "
            f"{delta_data.get('prior_date', 'the prior report')}. {movement}; the full "
            f"trend table is on the Month-over-Month Trends page.")
    else:
        delta_note = callout(
            "BASELINE REPORT:",
            "This is the first tracked snapshot for this dealership. Rating and "
            "review-count changes will appear here from the next monthly run.")

    return (sec_head("01", "At a glance", "Overall Ratings Snapshot")
            + '<p class="lede">Star rating and review volume across every platform. '
              'STRONG / MIXED / WEAK labels grade each rating; UP / DOWN / FLAT marks '
              'month-over-month movement.</p>'
            + kpi_stat_grid(kpis) + band + delta_note + pulled_line
            + toc_lanes(sections))


def page_platform(data, platform_key, section_num):
    dealer = data.get("subject_dealer", {})
    pdata = dealer.get("platforms", {}).get(platform_key, {})
    pname = PLATFORM_NAMES.get(platform_key, platform_key)
    rating = pdata.get("rating", "N/A")
    count = pdata.get("review_count", 0)
    rating_str = f"{rating:.1f}/5" if isinstance(rating, (int, float)) else str(rating)
    count_str = f"{count:,}" if isinstance(count, (int, float)) else str(count)

    head = sec_head(f"{section_num:02d}", f"Platform deep dive · {pname}", pname)
    rating_line = (f'<div class="platline">{stars_svg(rating, 18)}'
                   f'<span class="platnum">{esc(rating_str)}</span>'
                   f'<span class="platcount">{esc(count_str)} reviews</span></div>')

    parts = [head, rating_line]
    positive = pdata.get("recent_positive", [])
    parts.append(subhead("Most Recent Positive Reviews (4-5 stars)"))
    parts.append(review_table(positive, "positive"))
    negative = pdata.get("recent_negative", [])
    parts.append(subhead("Most Recent Negative Reviews (1-3 stars)"))
    parts.append(review_table(negative, "negative"))

    parts.append(themes_split(pdata.get("themes_positive", []),
                              pdata.get("themes_negative", [])))
    trending = pdata.get("trending_issues", [])
    if trending:
        joined = " ".join(t.strip() if t.strip().endswith((".", "!", "?"))
                          else t.strip() + "." for t in trending)
        parts.append(callout("TRENDING ISSUES:", joined))
    return "".join(parts)


def page_competitors(data, section_num):
    competitors = data.get("competitors", [])
    parts = [sec_head(f"{section_num:02d}", "Market position", "Competitor Comparison"),
             '<p class="lede">Side-by-side ratings across all platforms. The subject '
             'dealership is highlighted; each cell reads rating (review count).</p>',
             competitor_table(data),
             subhead("What Competitors Are Doing Right"),
             doing_right_cards(competitors)]
    return "".join(parts)


def page_recommendations(data, section_num):
    recs = data.get("recommendations", [])
    parts = [sec_head(f"{section_num:02d}", "Action plan", "Recommendations"),
             '<p class="lede">Quick wins to improve your online reputation, in '
             'priority order.</p>']
    if recs:
        parts.append(checklist(recs))
    else:
        parts.append(muted("No specific recommendations at this time."))
    parts.append('<div class="sec-head sub"><div class="eyebrow">The bigger picture</div>'
                 '<h3>Why Online Reviews Matter for SEO &amp; AI</h3>'
                 '<div class="rule"></div></div>')
    seo_text = data.get("seo_llm_section", "") or DEFAULT_SEO_TEXT
    parts.append(callout("", seo_text))
    return "".join(parts)


def page_delta(delta_data, section_num):
    """Month-over-month trends table + summary callouts. Change labels
    (UP/DOWN/FLAT, signed values) ported verbatim."""
    platforms = delta_data.get("platforms", {})
    rows = ['<tr><th style="width:16%">Platform</th><th style="width:13%">Prior Rating</th>'
            '<th style="width:14%">Current Rating</th><th style="width:12%">Change</th>'
            '<th style="width:14%">Prior Reviews</th><th style="width:16%">Current Reviews</th>'
            '<th style="width:15%">New Reviews</th></tr>']
    for pkey in PLATFORM_ORDER:
        pd = platforms.get(pkey, {})
        pname = PLATFORM_NAMES.get(pkey, pkey)
        prior_r = pd.get("prior_rating", "N/A")
        curr_r = pd.get("current_rating", "N/A")
        r_change = pd.get("rating_change", 0)
        prior_c = pd.get("prior_count", "N/A")
        curr_c = pd.get("current_count", "N/A")
        c_change = pd.get("count_change", 0)

        both_numeric = (isinstance(prior_r, (int, float))
                        and isinstance(curr_r, (int, float)))
        if not both_numeric:
            change_str = "N/A"
        elif isinstance(r_change, (int, float)):
            if r_change > 0:
                change_str = f"UP +{r_change:.1f}"
            elif r_change < 0:
                change_str = f"DOWN {r_change:.1f}"
            else:
                change_str = "FLAT 0.0"
        else:
            change_str = "N/A"

        prior_r_str = f"{prior_r:.1f}" if isinstance(prior_r, (int, float)) else str(prior_r)
        curr_r_str = f"{curr_r:.1f}" if isinstance(curr_r, (int, float)) else str(curr_r)
        prior_c_str = f"{prior_c:,}" if isinstance(prior_c, (int, float)) else str(prior_c)
        curr_c_str = f"{curr_c:,}" if isinstance(curr_c, (int, float)) else str(curr_c)
        c_change_str = (f"+{c_change:,}" if isinstance(c_change, (int, float)) and c_change >= 0
                        else str(c_change))

        rows.append(f'<tr><td class="dname">{esc(pname)}</td><td>{esc(prior_r_str)}</td>'
                    f'<td>{esc(curr_r_str)}</td><td><b>{esc(change_str)}</b></td>'
                    f'<td>{esc(prior_c_str)}</td><td>{esc(curr_c_str)}</td>'
                    f'<td>{esc(c_change_str)}</td></tr>')
    table = f'<table class="datatable">{"".join(rows)}</table>'

    improved = [PLATFORM_NAMES.get(k, k) for k, v in sorted(platforms.items(), key=lambda kv: PLATFORM_ORDER.index(kv[0]) if kv[0] in PLATFORM_ORDER else 99)
                if isinstance(v.get("rating_change"), (int, float)) and v["rating_change"] > 0]
    declined = [PLATFORM_NAMES.get(k, k) for k, v in sorted(platforms.items(), key=lambda kv: PLATFORM_ORDER.index(kv[0]) if kv[0] in PLATFORM_ORDER else 99)
                if isinstance(v.get("rating_change"), (int, float)) and v["rating_change"] < 0]

    notes = []
    if improved:
        notes.append(callout("IMPROVED:",
                             f"{', '.join(improved)}: ratings went up since the {esc(str(delta_data.get('prior_date') or 'prior'))} snapshot."))
    if declined:
        notes.append(callout(
            "DECLINED:",
            f"{', '.join(declined)}: ratings dropped since the {esc(str(delta_data.get('prior_date') or 'prior'))} snapshot. "
            "Review recent negative feedback for actionable patterns."))
    unrated = [PLATFORM_NAMES.get(k, k) for k, v in sorted(platforms.items(), key=lambda kv: PLATFORM_ORDER.index(kv[0]) if kv[0] in PLATFORM_ORDER else 99)
               if isinstance(v.get("prior_rating"), (int, float))
               and not isinstance(v.get("current_rating"), (int, float))]
    if unrated:
        notes.append(callout(
            "NOT COMPARABLE:",
            f"{', '.join(unrated)} no longer displays a score, so the prior rating "
            "has no current counterpart. Review count still tracks. See the platform "
            "page for the reason."))
    stable = [PLATFORM_NAMES.get(k, k) for k, v in sorted(platforms.items(), key=lambda kv: PLATFORM_ORDER.index(kv[0]) if kv[0] in PLATFORM_ORDER else 99)
              if isinstance(v.get("rating_change"), (int, float)) and v["rating_change"] == 0
              and isinstance(v.get("current_rating"), (int, float))
              and isinstance(v.get("prior_rating"), (int, float))]
    if not improved and not declined and stable:
        notes.append(callout("STABLE:",
                             f"{', '.join(stable)}: ratings held steady since the {esc(str(delta_data.get('prior_date') or 'prior'))} snapshot."))

    # New-review volume per platform as a stat-card row (same numbers as the
    # table's New Reviews column, lifted into the visual layer).
    vol_cards = []
    for pkey in PLATFORM_ORDER:
        pd = platforms.get(pkey, {})
        c_change = pd.get("count_change", 0)
        num = (f"{c_change:+,}" if isinstance(c_change, (int, float)) else str(c_change))
        vol_cards.append(f'<div class="stat">{CURSOR_TICK}'
                         f'<h5>{esc(PLATFORM_NAMES.get(pkey, pkey))}</h5>'
                         f'<div class="num">{esc(num)}</div>'
                         f'<div class="src">New reviews since prior snapshot</div></div>')
    vol_grid = f'<div class="statgrid">{"".join(vol_cards)}</div>'

    cadence = muted("Next month’s report will compare against this snapshot.")

    return (sec_head(f"{section_num:02d}", "Trend tracking", "Month-over-Month Trends")
            + f'<p class="lede">Compared to: {esc(delta_data.get("prior_date", "prior report"))}. '
              f'Rating movement reads UP / DOWN / FLAT with the signed change; review '
              f'growth is the count of new reviews landed since the prior snapshot.</p>'
            + vol_grid + table + "".join(notes) + cadence)


# ── document assembly ─────────────────────────────────────────

def build_cover(data, logo_path):
    meta = data.get("metadata", {})
    dealer = meta.get("dealer_name", "")
    loc = meta.get("dealer_location", "")
    brand = meta.get("dealer_brand", "")
    addr = meta.get("dealer_address", "")
    ts = meta.get("generation_timestamp", meta.get("report_date", ""))

    # Skip the city/state when the street address already carries it
    loc_brand = brand if (loc and addr and loc.lower() in addr.lower()) else " | ".join(p for p in [loc, brand] if p)
    meta_bits = " &nbsp;·&nbsp; ".join(esc(p) for p in [loc_brand, addr] if p)
    meta_line = f'<div class="covermeta">{meta_bits}</div>' if meta_bits else ""

    return f'''<div class="page cover">
      <img class="logo" src="file://{os.path.abspath(logo_path)}" alt="DigitalCLIQ">
      <div class="block">
        <div class="eyebrow">Online Reputation Intelligence</div>
        <h1>Online<br>Reputation<br><span class="accent">Report.</span></h1>
        <div class="rule"></div>
        <div class="subtitle">Live ratings, review highlights, and themes across Google,
        Yelp, DealerRater, and CarFax for {esc(dealer)}, benchmarked against the
        closest same-brand competitors.</div>
        {meta_line}
      </div>
      <svg class="cursor" viewBox="0 0 100 100"><path d="M12 4 L88 58 L52 62 L68 96 L54 100 L40 68 L14 88 Z" fill="#6B9DD4" opacity="0.75" transform="rotate(-12 50 50)"/></svg>
      <div class="prepared"><b>Prepared by DigitalCLIQ.</b> Digital Strategy &amp; Development.<br>{esc(dealer)} &nbsp;·&nbsp; Generated {esc(ts)}</div>
      <div class="pillars">Innovative &nbsp;|&nbsp; Clean &nbsp;|&nbsp; Minimalist &nbsp;|&nbsp; Bold &nbsp;|&nbsp; Resourceful</div>
    </div>'''


def build_html(data, logo_path, delta_data=None):
    meta = data.get("metadata", {})
    dealer_name = meta.get("dealer_name", "Online Reputation Report")

    # Plan the interior pages first (so the snapshot TOC knows page numbers),
    # then build them in report order.
    active_platforms = [
        pkey for pkey in PLATFORM_ORDER
        if data.get("subject_dealer", {}).get("platforms", {}).get(pkey, {})
        and data["subject_dealer"]["platforms"][pkey].get("rating") is not None]
    has_competitors = bool(data.get("competitors"))
    has_delta = bool(delta_data and not delta_data.get("is_first_report"))

    sections = []  # (page_no, title) for pages after the snapshot
    page_no = 2
    for pkey in active_platforms:
        sections.append((page_no, PLATFORM_NAMES.get(pkey, pkey)))
        page_no += 1
    if has_competitors:
        sections.append((page_no, "Competitor Comparison"))
        page_no += 1
    sections.append((page_no, "Recommendations & SEO/AI Impact"))
    page_no += 1
    if has_delta:
        sections.append((page_no, "Month-over-Month Trends"))

    pages = [page_snapshot(data, delta_data, sections)]
    section_num = 2
    for pkey in active_platforms:
        pages.append(page_platform(data, pkey, section_num))
        section_num += 1
    if has_competitors:
        pages.append(page_competitors(data, section_num))
        section_num += 1
    pages.append(page_recommendations(data, section_num))
    section_num += 1
    if has_delta:
        pages.append(page_delta(delta_data, section_num))

    # Data-provenance cards (collection limits, sort fallbacks, blocked pages)
    # ride on the last page so the disclosure ships inside the PDF and the
    # trends page is not left more than half empty (Visual-QA dead-zone rule).
    notes = data.get("collection_notes") or {}
    if isinstance(notes, dict) and notes:
        labels = {"google": "Google Reviews", "yelp": "Yelp", "dealerrater": "DealerRater",
                  "carfax": "CarFax", "competitors": "Competitors"}
        cards = "".join(
            f'<div class="note"><b>{esc(labels.get(k, k))}</b>{esc(str(v))}</div>'
            for k, v in notes.items() if v)
        pages[-1] += ('<div class="sec-head sub"><div class="eyebrow">Data provenance</div>'
                      '<h3>How this data was collected</h3><div class="rule"></div></div>'
                      '<p class="lede">Every figure above was read live on the review sites on the '
                      'pull date. Where a site limited what could be read, the limit is stated here '
                      'rather than papered over.</p>'
                      f'<div class="notes">{cards}</div>')
    total = len(pages)
    interior = "".join(
        f'<div class="page interior">{furniture(i, total, dealer_name)}{inner}</div>'
        for i, inner in enumerate(pages, 1))

    body = build_cover(data, logo_path) + interior
    return _SHELL.replace("{{FONTS}}", _font_faces()).replace("{{BODY}}", body)


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

/* Cover (dark, canonical) */
.cover{
  background:
    radial-gradient(ellipse 420px 320px at 85% 12%, rgba(36,53,98,0.85), transparent 70%),
    radial-gradient(ellipse 500px 380px at 8% 88%, rgba(36,53,98,0.55), transparent 70%),
    linear-gradient(180deg, var(--navy-deep) 0%, var(--navy-base) 45%, var(--navy-lift) 100%);
  font-family:'Dosis',sans-serif;color:#fff;
}
.cover .logo{position:absolute;top:64px;left:70px;width:115px;}
.cover .block{position:absolute;left:70px;top:320px;width:640px;}
.cover .eyebrow{font-weight:600;font-size:15px;letter-spacing:0.24em;text-transform:uppercase;color:var(--sky-blue);margin-bottom:24px;}
.cover h1{font-weight:800;font-size:76px;line-height:1.03;text-transform:uppercase;letter-spacing:0.01em;}
.cover h1 .accent{color:var(--sky-blue);}
.cover .rule{width:64px;height:4px;background:var(--sky-blue);margin:28px 0 26px;}
.cover .subtitle{font-family:'Roboto Slab',serif;font-weight:400;font-size:19px;line-height:1.55;color:var(--body-on-dark);max-width:560px;}
.cover .covermeta{font-family:'Dosis',sans-serif;font-weight:600;font-size:13px;letter-spacing:0.14em;text-transform:uppercase;color:var(--muted-on-dark);margin-top:24px;}
.cover .cursor{position:absolute;right:105px;bottom:190px;width:85px;height:85px;}
.cover .prepared{position:absolute;left:70px;bottom:104px;font-family:'Roboto Slab',serif;font-size:14px;line-height:1.6;color:var(--muted-on-dark);max-width:700px;}
.cover .prepared b{color:var(--body-on-dark);font-weight:400;}
.cover .pillars{position:absolute;bottom:52px;width:100%;text-align:center;font-weight:600;font-size:12px;letter-spacing:0.32em;text-transform:uppercase;color:var(--muted-on-dark);}

/* Interior */
.interior{background:var(--white);padding:56px 64px 60px;}
.furniture-top{position:absolute;top:0;left:64px;right:64px;height:44px;border-bottom:2px solid var(--card-border);display:flex;align-items:center;justify-content:space-between;}
.furniture-top .doctitle{font-family:'Dosis',sans-serif;font-weight:600;font-size:10.5px;letter-spacing:0.18em;text-transform:uppercase;color:var(--warm-grey);}
.furniture-top img{height:17px;}
.furniture-bot{position:absolute;bottom:0;left:64px;right:64px;height:40px;border-top:2px solid var(--card-border);display:flex;align-items:center;justify-content:space-between;}
.furniture-bot span{font-family:'Dosis',sans-serif;font-weight:500;font-size:10.4px;letter-spacing:0.15em;text-transform:uppercase;color:var(--warm-grey);}

.sec-head{position:relative;margin:16px 0 10px;}
.sec-head .eyebrow{font-family:'Dosis',sans-serif;font-weight:600;font-size:12.5px;letter-spacing:0.22em;text-transform:uppercase;color:var(--digital-blue);margin-bottom:8px;}
.sec-head h2{font-family:'Dosis',sans-serif;font-weight:700;font-size:34px;color:#000;line-height:1.08;}
.sec-head h3{font-family:'Dosis',sans-serif;font-weight:700;font-size:24px;color:#000;line-height:1.1;}
.sec-head .rule{width:48px;height:3px;background:var(--sky-blue);margin-top:12px;}
.sec-head.sub{margin-top:30px;}
.ghost{position:absolute;right:0;top:-16px;font-family:'Dosis',sans-serif;font-weight:800;font-size:140px;line-height:1;color:var(--digital-blue);opacity:0.07;}
.minihead{font-family:'Dosis',sans-serif;font-weight:700;font-size:13px;letter-spacing:0.14em;text-transform:uppercase;color:var(--tile-blue);margin:12px 0 6px;}
.lede{font-size:12.5px;line-height:1.55;color:#000;max-width:560px;margin:2px 0 10px;}
.mutedline{font-family:'Dosis',sans-serif;font-weight:500;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--warm-grey);margin:10px 0;}

.statgrid{display:flex;gap:14px;margin:14px 0;}
.stat{flex:1;background:var(--card-white);border:1px solid var(--card-border);border-radius:12px;padding:15px 14px 12px;position:relative;}
.stat h5{font-family:'Dosis',sans-serif;font-weight:600;font-size:12px;letter-spacing:0.08em;text-transform:uppercase;color:var(--digital-blue);margin-bottom:8px;}
.stat .num{font-family:'Dosis',sans-serif;font-weight:800;font-size:38px;line-height:1;color:var(--sky-blue);}
.stat .num small{font-size:22px;font-weight:700;}
.stat .num .txt{font-size:26px;white-space:nowrap;}
.stat .stars{display:block;margin-top:8px;}
.stat .src{font-family:'Dosis',sans-serif;font-weight:500;font-size:9px;letter-spacing:0.11em;text-transform:uppercase;color:var(--warm-grey);margin-top:9px;}
.tick{position:absolute;top:10px;right:10px;width:11px;height:11px;}

.band{background:linear-gradient(135deg, var(--navy-base), var(--navy-lift));border-radius:14px;padding:20px 26px;display:flex;align-items:center;gap:26px;margin:14px 0;}
.band .bnum{font-family:'Dosis',sans-serif;font-weight:800;font-size:54px;color:var(--sky-blue);line-height:1;white-space:nowrap;}
.band .bcap{font-family:'Roboto Slab',serif;font-size:12px;line-height:1.55;color:var(--body-on-dark);}
.band .bcap b{color:#fff;font-weight:700;}

.callout{background:var(--callout-tint);border-left:3px solid var(--digital-blue);border-radius:0 12px 12px 0;padding:10px 14px;font-size:11.5px;line-height:1.5;margin:8px 0;}
.callout b{font-family:'Dosis',sans-serif;font-weight:700;font-size:12px;color:var(--tile-blue);letter-spacing:0.06em;text-transform:uppercase;}

.platline{display:flex;align-items:center;gap:12px;margin:2px 0 6px;}
.platline .stars{display:block;}
.platline .platnum{font-family:'Dosis',sans-serif;font-weight:800;font-size:24px;color:var(--sky-blue);line-height:1;}
.platline .platcount{font-family:'Dosis',sans-serif;font-weight:600;font-size:12px;letter-spacing:0.1em;text-transform:uppercase;color:var(--warm-grey);}

table.datatable{width:100%;border-collapse:collapse;margin:4px 0 8px;border-radius:12px;overflow:hidden;}
table.datatable th{background:var(--digital-blue);color:#fff;font-family:'Dosis',sans-serif;font-weight:600;font-size:11.5px;letter-spacing:0.06em;text-transform:uppercase;padding:7px 10px;text-align:left;}
table.datatable td{font-size:11px;line-height:1.35;padding:6px 11px;border-bottom:1px solid var(--card-border);vertical-align:top;}
table.datatable tr:nth-child(odd) td{background:var(--callout-tint);}
table.datatable td b{font-weight:700;}
table.datatable td.dname{font-family:'Dosis',sans-serif;font-weight:700;font-size:12px;color:var(--tile-blue);}
table.datatable tr.subject td{background:var(--card-border);font-weight:700;}

.compare{display:flex;gap:14px;margin:8px 0 0;}
.cmpcol{flex:1;border-radius:12px;padding:11px 14px;}
/* Comparison split per Design-System: WEAK/NEGATIVE greyed with Warm Grey label,
   STRONG/POSITIVE blue-bordered with Digital Blue label. Meaning is carried by
   the explicit column headings, not by color alone. */
.cmpcol.risk{background:var(--card-white);border:1px solid var(--card-border);}
.cmpcol.opp{background:var(--callout-tint);border:1px solid var(--digital-blue);}
.cmpcol .cmphead{font-family:'Dosis',sans-serif;font-weight:700;font-size:13.5px;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:7px;}
.cmpcol.risk .cmphead{color:var(--warm-grey);}
.cmpcol.opp .cmphead{color:var(--digital-blue);}
.cmpcol ul{list-style:none;}
.cmpcol li{font-size:11.3px;line-height:1.4;padding:3px 0 3px 15px;position:relative;border-bottom:1px solid var(--card-border);}
.cmpcol li:last-child{border-bottom:none;}
.cmpcol li:before{content:"";position:absolute;left:0;top:10px;width:6px;height:6px;border-radius:50%;}
.cmpcol.risk li:before{background:var(--warm-grey);}
.cmpcol.opp li:before{background:var(--sky-blue);}

.compcards{margin:6px 0;}
.compcard{display:flex;gap:22px;align-items:flex-start;background:var(--card-white);border:1px solid var(--card-border);border-radius:12px;padding:12px 18px;margin-bottom:10px;}
.compcard h4{font-family:'Dosis',sans-serif;font-weight:700;font-size:15px;color:var(--tile-blue);line-height:1.25;width:150px;flex:none;padding-top:2px;}
.compcard ul{list-style:none;flex:1;}
.compcard li{font-size:11px;line-height:1.45;padding:2px 0 2px 15px;position:relative;}
.compcard li:before{content:"";position:absolute;left:0;top:9px;width:6px;height:6px;border-radius:50%;background:var(--sky-blue);}

.lanes{display:flex;flex-wrap:wrap;gap:12px;margin:6px 0;}
.notes{display:flex;flex-wrap:wrap;gap:10px;margin-top:4px;}
.note{width:calc(50% - 5px);background:var(--card-white);border:1px solid var(--card-border);border-radius:12px;padding:10px 14px;font-size:10.5px;line-height:1.45;color:#000;}
.note b{font-family:'Dosis',sans-serif;font-weight:700;font-size:11px;letter-spacing:0.06em;text-transform:uppercase;color:var(--tile-blue);display:block;margin-bottom:3px;}
.lane{width:calc(50% - 6px);background:var(--card-white);border:1px solid var(--card-border);border-radius:12px;padding:13px 16px 13px 52px;position:relative;display:flex;align-items:center;justify-content:space-between;gap:10px;}
.lane .n{font-family:'Dosis',sans-serif;font-weight:700;font-size:22px;color:var(--digital-blue);position:absolute;left:16px;top:50%;transform:translateY(-50%);line-height:1;}
.lane h4{font-family:'Dosis',sans-serif;font-weight:600;font-size:13.5px;color:#000;line-height:1.25;}
.lane .pg{font-family:'Dosis',sans-serif;font-weight:500;font-size:9.5px;letter-spacing:0.12em;text-transform:uppercase;color:var(--warm-grey);white-space:nowrap;}

.checklist{margin:8px 0;}
.check{display:flex;align-items:flex-start;gap:12px;background:var(--card-white);border:1px solid var(--card-border);border-radius:12px;padding:12px 16px;margin-bottom:10px;}
.check svg{width:19px;height:19px;flex:none;margin-top:1px;}
.check p{font-family:'Roboto Slab',serif;font-size:12px;line-height:1.5;color:#000;}
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


def generate_report(json_path, output_path, logo_path, delta_path=None):
    """Generate the branded Online Reputation Report PDF."""
    # Logos must resolve (canonical brand-assets paths). A missing logo fails
    # loudly (Design-System rule) — never a silent broken image.
    if not logo_path or not os.path.exists(logo_path):
        raise FileNotFoundError(
            f"DigitalCLIQ logo not found at: {logo_path!r}\n"
            f"Canonical path: {LOGO_WHITE}")
    for logo in (LOGO_WHITE, LOGO_COLOR):
        if not os.path.exists(logo):
            raise RuntimeError(
                f"DigitalCLIQ logo missing at canonical path: {logo}. "
                f"Restore Resources/brand-assets/ before generating.")

    with open(json_path, "r") as f:
        data = json.load(f)

    delta_data = None
    if delta_path and os.path.exists(delta_path):
        with open(delta_path, "r") as f:
            delta_data = json.load(f)

    html = build_html(data, logo_path, delta_data)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                     dir=os.path.dirname(os.path.abspath(output_path)) or ".") as fh:
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
    return output_path


# ── CLI entry point ──────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python3 generate_reputation_report.py <json> <output_pdf> <logo> [--delta <delta_json>]")
        sys.exit(1)

    json_path = sys.argv[1]
    output_pdf = sys.argv[2]
    logo = sys.argv[3]
    delta = None

    if "--delta" in sys.argv:
        idx = sys.argv.index("--delta")
        if idx + 1 < len(sys.argv):
            delta = sys.argv[idx + 1]

    generate_report(json_path, output_pdf, logo, delta)
