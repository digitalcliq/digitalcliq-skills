#!/usr/bin/env python3
"""
DigitalCLIQ Coffee Report — PDF Generator (v2, design-system pipeline)
Developed by DigitalCLIQ — Digital Strategy & Development

Rebuilt per Resources/design-system/Design-System.md: hand-authored HTML+CSS
rendered to PDF using the canonical component library (canonical dark cover,
stat cards, callout bars, branded tables, section headers with ghost numerals,
running furniture). NEVER reportlab for narrative reports — it cannot hit the
spec.

Pipeline: WeasyPrint if importable, else Chrome headless --print-to-pdf
(the design-system documented fallback). Fonts (Dosis + Roboto Slab) are
embedded via @font-face from the vault archive so rendering is self-contained.

Content is paginated in Python: section blocks carry height estimates and are
packed into fixed 850x1100 pages so every interior page gets running furniture
and nothing overflows. The Visual-QA render gate is still mandatory.

Usage:
    python3 generate_coffee_report.py <json_path> <output_pdf> <logo_path>
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

CURSOR_SVG = ('<svg class="tick" viewBox="0 0 100 100"><path d="M12 4 L88 58 '
              'L52 62 L68 96 L54 100 L40 68 L14 88 Z" fill="#405FAB"/></svg>')


# ── Data Validation ───────────────────────────────────────────

META_SCHEMA = {
    "report_date":           ("str", True),
    "day_name":              ("str", True),
    "generation_timestamp":  ("str", True),
}

GA4_CLIENTS = ["sterling", "nissan", "mcpeek", "new_century"]
NEWS_CATEGORIES = ["economy", "automotive"]

# SEO Pulse covers the three dealers Drew owns SEO for (Semrush).
# Order is the render order in the PDF.
SEO_DEALERS = [
    ("sterling",    "Sterling BMW"),
    ("new_century", "New Century BMW"),
    ("mcpeek",      "McPeek CDJR"),
]

# Lead Pulse (CRM) covers all four active clients.
CRM_DEALERS = [
    ("sterling",    "Sterling BMW"),
    ("new_century", "New Century BMW"),
    ("nissan",      "Nissan of Irvine"),
    ("mcpeek",      "McPeek CDJR"),
]

# Paid Social Pulse (Meta Ads MCP). Only active, queryable ad accounts.
PAID_ACCOUNTS = [
    ("main",   "DigitalCLIQ (Main)"),
    ("mcpeek", "McPeek Dodge"),
]

# Live dashboard snapshots (Apps Script /exec endpoints).
DASHBOARD_STORES = [
    ("ncbmw",  "New Century BMW"),
    ("sbmw",   "Sterling BMW"),
    ("mcpeek", "McPeek CDJR"),
]


def _type_name(expected):
    mapping = {
        "str": "string", "int": "integer", "float": "float",
        "num": "number (int or float)", "list": "list",
        "dict": "dict", "list[dict]": "list of dicts", "bool": "boolean",
    }
    return mapping.get(expected, expected)


def _check_type(value, expected):
    if expected == "str":
        return isinstance(value, str)
    elif expected == "num":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    elif expected == "list":
        return isinstance(value, list)
    elif expected == "dict":
        return isinstance(value, dict)
    elif expected == "bool":
        return isinstance(value, bool)
    return True


def validate_data(data, source_path="<input>"):
    """
    Validate the morning-coffee JSON data before PDF generation.

    Checks:
      1. All required top-level sections exist (metadata, calendar, crm, ga4, google_ads, news)
      2. Data types match template expectations
      3. No empty/null values in required fields
      4. CRM/GA4/Ads sub-keys present; each has 'available' field

    Returns (is_valid, errors) where errors is a list of descriptive strings.
    """
    errors = []

    # ── 1. Top-level structure ────────────────────────────────────
    if not isinstance(data, dict):
        errors.append(
            f"Top-level: expected dict, got {type(data).__name__}\n"
            f"  Expected: {{\"metadata\": {{...}}, \"calendar\": {{...}}, \"crm\": {{...}}, ...}}\n"
            f"  Actual:   {type(data).__name__}"
        )
        return False, errors

    required_top = ["metadata", "calendar", "tasks", "gmail", "ga4", "news"]
    for key in required_top:
        if key not in data:
            errors.append(
                f"Top-level: missing required section '{key}'\n"
                f"  Expected: dict\n"
                f"  Actual:   key not present"
            )

    # ── 2. Metadata ───────────────────────────────────────────────
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        errors.append(
            f"metadata: wrong type\n"
            f"  Expected: dict\n"
            f"  Actual:   {type(metadata).__name__}"
        )
    else:
        for field, (exp_type, required) in META_SCHEMA.items():
            val = metadata.get(field)
            if val is None:
                if required:
                    errors.append(
                        f"metadata.{field}: missing required field\n"
                        f"  Expected: {_type_name(exp_type)}\n"
                        f"  Actual:   not present"
                    )
            elif not _check_type(val, exp_type):
                errors.append(
                    f"metadata.{field}: wrong type\n"
                    f"  Expected: {_type_name(exp_type)}\n"
                    f"  Actual:   {type(val).__name__} = {repr(val)[:80]}"
                )
            elif required and exp_type == "str" and not val:
                errors.append(
                    f"metadata.{field}: required field is empty\n"
                    f"  Expected: non-empty {_type_name(exp_type)}\n"
                    f"  Actual:   \"\""
                )

    # ── 3. Calendar ───────────────────────────────────────────────
    cal = data.get("calendar", {})
    if isinstance(cal, dict):
        for sub in ["today", "tomorrow"]:
            if sub in cal and not isinstance(cal[sub], dict):
                errors.append(
                    f"calendar.{sub}: wrong type\n"
                    f"  Expected: dict\n"
                    f"  Actual:   {type(cal[sub]).__name__}"
                )

    # ── 4. Tasks section (Notion) ─────────────────────────────────
    tasks = data.get("tasks", {})
    if "tasks" in data and not isinstance(tasks, dict):
        errors.append(
            f"tasks: wrong type\n"
            f"  Expected: dict with keys 'connected', 'today', 'tomorrow', 'upcoming'\n"
            f"  Actual:   {type(tasks).__name__}"
        )
    elif isinstance(tasks, dict):
        for bucket in ["today", "tomorrow", "upcoming"]:
            if bucket in tasks and not isinstance(tasks[bucket], list):
                errors.append(
                    f"tasks.{bucket}: wrong type\n"
                    f"  Expected: list of task dicts\n"
                    f"  Actual:   {type(tasks[bucket]).__name__}"
                )

    # ── 5. GA4 section ────────────────────────────────────────────
    ga4 = data.get("ga4", {})
    if isinstance(ga4, dict):
        for client in GA4_CLIENTS:
            if client not in ga4:
                errors.append(
                    f"ga4.{client}: missing required client key\n"
                    f"  Expected: dict with 'available' field\n"
                    f"  Actual:   not present"
                )
            elif isinstance(ga4.get(client), dict) and "available" not in ga4[client]:
                errors.append(
                    f"ga4.{client}.available: missing required field\n"
                    f"  Expected: boolean\n"
                    f"  Actual:   not present"
                )

    # ── 6. Gmail section ──────────────────────────────────────────
    gmail = data.get("gmail", {})
    if "gmail" in data and not isinstance(gmail, dict):
        errors.append(
            f"gmail: wrong type\n"
            f"  Expected: dict with 'connected', 'by_sender', 'highlights'\n"
            f"  Actual:   {type(gmail).__name__}"
        )
    elif isinstance(gmail, dict):
        if "by_sender" in gmail and not isinstance(gmail["by_sender"], list):
            errors.append(
                f"gmail.by_sender: wrong type\n"
                f"  Expected: list of sender dicts\n"
                f"  Actual:   {type(gmail['by_sender']).__name__}"
            )

    # ── 7. News section ───────────────────────────────────────────
    news = data.get("news", {})
    if isinstance(news, dict):
        for cat in NEWS_CATEGORIES:
            if cat not in news:
                errors.append(
                    f"news.{cat}: missing required category\n"
                    f"  Expected: list of headline dicts\n"
                    f"  Actual:   not present"
                )
            elif not isinstance(news.get(cat), list):
                errors.append(
                    f"news.{cat}: wrong type\n"
                    f"  Expected: list\n"
                    f"  Actual:   {type(news[cat]).__name__}"
                )

    # ── Report ────────────────────────────────────────────────────
    if errors:
        shown = errors[:50]
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"VALIDATION FAILED — {source_path}", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        print(f"{len(errors)} error(s) found:\n", file=sys.stderr)
        for i, e in enumerate(shown, 1):
            print(f"  {i}. {e}\n", file=sys.stderr)
        if len(errors) > 50:
            print(f"  ... and {len(errors) - 50} more errors", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)
        return False, errors

    return True, []


# ── Small helpers ─────────────────────────────────────────────

def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def rich(s):
    """Escape data text but keep simple emphasis tags the agents/old pipeline
    used (<b>, <i>) working, mirroring reportlab Paragraph behavior."""
    out = esc(s)
    for tag in ("b", "i"):
        out = out.replace(f"&lt;{tag}&gt;", f"<{tag}>").replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    return out


_TAG_RE = re.compile(r"<[^>]+>")


def _plain_len(html):
    return len(_TAG_RE.sub("", html))


def _fmt_int(val):
    """Format a number with thousands separators; pass through non-numerics."""
    try:
        return f"{int(float(val)):,}"
    except (ValueError, TypeError):
        return str(val) if val not in (None, "") else "—"


def _pretty_date(iso):
    import datetime
    try:
        d = datetime.date.fromisoformat(iso)
        return d.strftime("%B %-d, %Y")
    except Exception:
        return iso


# ── Layout model ──────────────────────────────────────────────
# Interior page: 850x1100, padding 56/64/60. Usable content height budget with
# a safety margin for estimation error:
CONTENT_W = 722          # 850 - 2*64
PAGE_BUDGET = 930

_STATUS_WORDS = {"positive": "GOOD", "negative": "LOW", "warning": "WATCH"}
_STATUS_CLASS = {"positive": "pos", "negative": "neg", "warning": "warn"}


def _lines(text_html, chars_per_line):
    return max(1, math.ceil(_plain_len(text_html) / max(chars_per_line, 8)))


class Block:
    """One layout unit: html + estimated pixel height."""
    __slots__ = ("html", "h")

    def __init__(self, html, h):
        self.html = html
        self.h = h


def merge_blocks(*blocks):
    blocks = [b for b in blocks if b]
    return Block("".join(b.html for b in blocks), sum(b.h for b in blocks))


# ── Component builders (each returns a Block) ────────────────

def kpi_row(kpis, limit=6):
    """Row of compact KPI stat cards. Status carried by palette treatment AND
    an explicit text word (GOOD / LOW / WATCH) — never color alone."""
    kpis = [k for k in kpis if isinstance(k, dict)][:limit]
    if not kpis:
        return None
    n = len(kpis)
    card_w = CONTENT_W / n - 12
    cards = []
    max_lab_lines = 1
    max_val_lines = 1
    for k in kpis:
        status = k.get("status", "neutral")
        word = _STATUS_WORDS.get(status)
        label = str(k.get("label", ""))
        lab = f"{label} · {word}" if word else label
        cls = _STATUS_CLASS.get(status, "neu")
        value = str(k.get("value", ""))
        vcls = " sm" if len(value) > 8 else ""
        max_lab_lines = max(max_lab_lines, _lines(esc(lab), card_w / 5.0))
        # Long values wrap inside the card; budget the extra line(s) or the
        # page overfills and content collides with the footer.
        char_px = 11.0 if vcls else 15.0
        usable_w = max(card_w - 26, 40)
        vlines = min(3, max(1, math.ceil(len(value) * char_px / usable_w)))
        max_val_lines = max(max_val_lines, vlines)
        cards.append(
            f'<div class="kpi">{CURSOR_SVG}'
            f'<div class="num {cls}{vcls}">{esc(value)}</div>'
            f'<div class="lab">{esc(lab)}</div></div>')
    h = 62 + 13 * max_lab_lines + 12 + 26 * (max_val_lines - 1)
    return Block(f'<div class="kpis">{"".join(cards)}</div>', h)


def callout(body_html, kind="info", lead=None):
    """Callout bar (Design-System). kind: info | alert | success. Severity is
    carried by an explicit TEXT label (ALERT / WIN) plus a palette border —
    all kinds share the Callout Tint fill."""
    auto_lead = {"alert": "ALERT:", "success": "WIN:"}.get(kind)
    lead = lead if lead is not None else auto_lead
    lead_html = f"<b>{esc(lead)}</b> " if lead else ""
    cls = {"alert": " alert", "success": " win"}.get(kind, "")
    html = f'<div class="callout{cls}">{lead_html}{body_html}</div>'
    n_lines = _lines(lead_html + body_html, 96)
    return Block(html, 24 + 19 * n_lines + 12)


def insight_block(ins, default_kind="info"):
    """One agent-supplied insight — dict {'text','type'} or plain string."""
    if isinstance(ins, dict):
        return callout(rich(ins.get("text", "")), ins.get("type", default_kind))
    return callout(rich(str(ins)), default_kind)


def data_table(headers, rows, col_pcts=None, cell_html=False):
    """Branded table: Digital Blue header band, alternating Callout Tint rows."""
    n = len(headers)
    if not col_pcts:
        col_pcts = [100.0 / n] * n
    ths = "".join(
        f'<th style="width:{p:.1f}%">{esc(h)}</th>' for h, p in zip(headers, col_pcts))
    trs = [f"<tr>{ths}</tr>"]
    est = 34 + 24  # header + margins
    for row in rows:
        tds = []
        row_lines = 1
        for c, p in zip(row, col_pcts):
            content = c if cell_html else esc(c)
            cpl = (CONTENT_W * p / 100.0 - 20) / 6.3
            row_lines = max(row_lines, _lines(str(content), cpl))
            tds.append(f"<td>{content}</td>")
        trs.append(f"<tr>{''.join(tds)}</tr>")
        est += 16 + 17 * row_lines
    return Block(f'<table class="data">{"".join(trs)}</table>', est)


def pill(label, tone="blue"):
    cls = "pill sky" if tone == "sky" else "pill"
    return Block(f'<div class="{cls}">{esc(label)}</div>', 36)


def muted(text_html):
    return Block(f'<div class="muted">{text_html}</div>',
                 10 + 18 * _lines(text_html, 100))


def cat_label(text):
    return Block(f'<div class="catlab">&#9656; {esc(text)}</div>', 32)


def news_item(item):
    if not isinstance(item, dict):
        return Block(f'<div class="news-item"><div class="hl">{esc(item)}</div></div>', 34)
    headline = item.get("headline", "")
    source = item.get("source", "")
    url = item.get("url", "")
    relevance = item.get("client_relevance", "")
    hl = (f'<a href="{esc(url)}">{esc(headline)}</a>' if url else esc(headline))
    src = esc(source)
    if relevance:
        src += f' &mdash; <i>{esc(relevance)}</i>'
    hl_lines = _lines(esc(headline), 92)
    src_lines = _lines(src, 110)
    return Block(
        f'<div class="news-item"><div class="hl">{hl}</div>'
        f'<div class="nsrc">{src}</div></div>',
        19 * hl_lines + 15 * src_lines + 10)


# ── Section builders ──────────────────────────────────────────
# Each returns a list of Blocks (empty list = skip the section entirely).

def sec_calendar(data):
    cal = data.get("calendar", {})
    blocks = []

    if not cal.get("calendar_connected", True) and not cal.get("today", {}).get("events"):
        blocks.append(callout(
            "Google Calendar is not connected. Calendar events are unavailable today.",
            "alert"))
        return blocks

    def day_table(day, tag_label):
        date = day.get("date", "")
        day_name = day.get("day_name", "")
        sub = f"{tag_label}  ·  {day_name}, {date}" if date else tag_label
        out = [pill(sub)]
        events = day.get("events", [])
        if events:
            rows = [[e.get("time", ""), e.get("name", ""), e.get("location", "")]
                    for e in events]
            out.append(data_table(["Time", "Event", "Location / Notes"], rows,
                                  [18.5, 46.0, 35.5]))
        else:
            out.append(muted("<i>No events scheduled.</i>"))
        # pill stays with its table
        return [merge_blocks(*out[:2])] + out[2:]

    blocks += day_table(cal.get("today", {}), "TODAY")
    blocks += day_table(cal.get("tomorrow", {}), "TOMORROW")

    week_ahead = cal.get("week_ahead", [])
    if week_ahead:
        summary = " | ".join(week_ahead) if isinstance(week_ahead, list) else str(week_ahead)
        blocks.append(callout(esc(summary), "info", lead="WEEK AHEAD:"))
    return blocks


def sec_tasks(data):
    tasks = data.get("tasks", {})
    blocks = []

    if not tasks.get("connected", True):
        blocks.append(callout(rich(tasks.get("note", "Notion tasks unavailable today")), "alert"))
        return blocks

    def bucket(label, items, empty_msg):
        head = pill(label)
        if not items:
            return [merge_blocks(head, muted(f"<i>{esc(empty_msg)}</i>"))]
        rows = []
        for t in items:
            title = esc(t.get("title", ""))
            if t.get("overdue"):
                title = f"<b>[OVERDUE]</b> {title}"
            rows.append([title, esc(t.get("due", "")), esc(t.get("status", "")),
                         esc(t.get("priority", ""))])
        tbl = data_table(["Task", "Due", "Status", "Priority"], rows,
                         [49.0, 15.0, 18.0, 18.0], cell_html=True)
        return [merge_blocks(head, tbl)]

    blocks += bucket("TODAY", tasks.get("today", []), "No tasks due today.")
    blocks += bucket("TOMORROW", tasks.get("tomorrow", []), "No tasks due tomorrow.")

    upcoming = tasks.get("upcoming", [])
    if upcoming:
        summary_bits = []
        for t in upcoming[:8]:
            due = t.get("due", "")
            title = t.get("title", "")
            if title:
                summary_bits.append(f"{title} ({due})" if due else title)
        if summary_bits:
            blocks.append(callout(esc(" | ".join(summary_bits)), "info",
                                  lead="UPCOMING (7 DAYS):"))
    return blocks


def sec_gmail(data):
    gmail = data.get("gmail", {})
    blocks = []

    if not gmail.get("connected", True):
        blocks.append(callout(rich(gmail.get("note", "Gmail not connected today")), "alert"))
        return blocks

    total = gmail.get("total_unread_24h", 0)
    kept = gmail.get("kept", 0)
    dropped = gmail.get("dropped_as_noise", 0)
    senders = gmail.get("by_sender", [])
    row = kpi_row([
        {"label": "Unread (24h)", "value": str(total), "status": "neutral"},
        {"label": "Worth Reading", "value": str(kept),
         "status": "positive" if kept > 0 else "neutral"},
        {"label": "Noise Filtered", "value": str(dropped), "status": "neutral"},
        {"label": "Senders", "value": str(len(senders)), "status": "neutral"},
    ])
    if row:
        blocks.append(row)

    if senders:
        rows = []
        for s in senders[:15]:
            sender_label = esc(s.get("sender", ""))
            if s.get("important"):
                sender_label = f"<b>&#9733; {sender_label}</b>"
            rows.append([sender_label, esc(str(s.get("count", ""))),
                         esc(s.get("top_subject", ""))])
        blocks.append(data_table(["Sender", "#", "Top Subject"], rows,
                                 [34.0, 8.0, 58.0], cell_html=True))

    for ins in gmail.get("highlights", []):
        blocks.append(insight_block(ins))

    if not senders and not gmail.get("highlights"):
        blocks.append(muted("<i>Inbox is quiet — no important unread mail in the last 24 hours.</i>"))
    return blocks


def _dict_table(items, limit, first_col_pct=34.0):
    """Table from a list of dicts whose keys are the headers (CRM sources,
    paid campaigns, GA4 channels)."""
    if not items or not isinstance(items[0], dict):
        return None
    headers = list(items[0].keys())
    rows = [[str(it.get(h, "")) for h in headers] for it in items[:limit]]
    n = len(headers)
    if n > 1:
        pcts = [first_col_pct] + [(100.0 - first_col_pct) / (n - 1)] * (n - 1)
    else:
        pcts = [100.0]
    return data_table(headers, rows, pcts)


def sec_crm(data):
    crm = data.get("crm", {})
    if not crm:
        return None  # section absent entirely
    blocks = []

    dealers = crm.get("dealers", {})
    if not crm.get("available", True) or not any(
        dealers.get(k, {}).get("available", False) for k, _ in CRM_DEALERS
    ):
        blocks.append(callout(rich(crm.get(
            "note", "No CRM data pulled today — all four CRM sessions unavailable")), "alert"))
        return blocks

    # Cross-store strategic read — the CMO Lens
    for ins in crm.get("cmo_lens", []):
        blocks.append(insight_block(ins))

    for key, label in CRM_DEALERS:
        dealer = dealers.get(key, {})
        if not dealer.get("available", False):
            continue
        tag = label + (f"  ·  {dealer['period']}" if dealer.get("period") else "")
        # Pill + KPI row + source table travel as ONE unit so a page break can
        # never strand a table without its store label.
        blocks.append(merge_blocks(
            pill(tag),
            kpi_row(dealer.get("kpis", []), limit=6),
            _dict_table(dealer.get("sources", []), 10)))
        for ins in dealer.get("insights", []):
            blocks.append(insight_block(ins))
    return blocks


def sec_paid(data):
    paid = data.get("paid", {})
    if not paid:
        return None
    blocks = []

    accounts = paid.get("accounts", {})
    if not paid.get("available", True) or not any(
        accounts.get(k, {}).get("available", False) for k, _ in PAID_ACCOUNTS
    ):
        blocks.append(callout(rich(paid.get("note", "Meta Ads data unavailable today")), "alert"))
        return blocks

    for ins in paid.get("insights", []):
        blocks.append(insight_block(ins))

    for key, label in PAID_ACCOUNTS:
        acct = accounts.get(key, {})
        if not acct.get("available", False):
            continue
        tag = label + (f"  ·  {acct['period']}" if acct.get("period") else "")
        # Account pill + KPI row + campaign table travel as one unit (no
        # orphaned tables across page breaks).
        blocks.append(merge_blocks(
            pill(tag),
            kpi_row(acct.get("kpis", []), limit=6),
            _dict_table(acct.get("campaigns", []), 10)))
        for ins in acct.get("insights", []):
            blocks.append(insight_block(ins))
    return blocks


def sec_ga4(data):
    ga4 = data.get("ga4", {})
    blocks = []

    if not any(ga4.get(k, {}).get("available", False) for k in GA4_CLIENTS):
        blocks.append(callout(
            "GA4 unavailable today (Zapier GA4 connection down and Chrome fallback failed)",
            "alert"))
        return blocks

    property_config = [
        ("sterling",    "Sterling BMW",     "blue"),
        ("nissan",      "Nissan of Irvine", "sky"),
        ("mcpeek",      "McPeek CDJR",      "blue"),
        ("new_century", "New Century BMW",  "sky"),
    ]

    for key, label, tone in property_config:
        prop = ga4.get(key, {})
        if not prop.get("available", False):
            note = prop.get("note", f"GA4 data unavailable for {label}")
            blocks.append(merge_blocks(pill(label, tone), muted(f"<i>{esc(note)}</i>")))
            continue

        group = [pill(label, tone)]
        channels = prop.get("channels", [])
        tbl = None
        if channels:
            if isinstance(channels[0], dict):
                headers = list(channels[0].keys())
                rows = [[str(c.get(h, "")) for h in headers] for c in channels]
            elif isinstance(channels[0], list):
                headers = prop.get("channel_headers",
                                   ["Channel", "Sessions", "Share %", "Engaged",
                                    "Eng Rate", "Avg Duration", "Key Events",
                                    "Key Event Rate"])
                rows = channels
            else:
                headers, rows = [], []
            if headers and rows:
                tbl = data_table(headers, rows)
        if tbl:
            group.append(tbl)
        blocks.append(merge_blocks(*group))

        for ins in prop.get("insights", []):
            blocks.append(insight_block(ins))
    return blocks


def sec_dashboards(data):
    dash = data.get("dashboards", {})
    if not dash:
        return None
    blocks = []

    stores = dash.get("stores", {})
    if not dash.get("available", True) or not any(
        stores.get(k, {}).get("available", False) for k, _ in DASHBOARD_STORES
    ):
        blocks.append(callout(rich(dash.get("note", "Dashboard endpoints unreachable today")), "alert"))
        return blocks

    for key, label in DASHBOARD_STORES:
        store = stores.get(key, {})
        if not store.get("available", False):
            continue
        tag = label + (f"  ·  updated {store['updated']}" if store.get("updated") else "")
        group = [pill(tag, "sky")]
        if store.get("stale"):
            group.append(callout(
                rich(store.get("stale_note", "dashboard has not been updated recently")),
                "alert", lead="STALE DATA:"))
        row = kpi_row(store.get("kpis", []), limit=6)
        if row:
            group.append(row)
        blocks.append(merge_blocks(*group))
        for ins in store.get("insights", []):
            blocks.append(insight_block(ins))
    return blocks


def sec_seo(data):
    seo = data.get("seo", {})
    if not seo:
        return None
    blocks = []

    dealers = seo.get("dealers", {})
    if not seo.get("available", True) or not any(
        dealers.get(k, {}).get("available", False) for k, _ in SEO_DEALERS
    ):
        blocks.append(callout(rich(seo.get("note", "Semrush data unavailable today")), "alert"))
        return blocks

    weekly = bool(seo.get("weekly_deep_dive", False))

    for key, label in SEO_DEALERS:
        dealer = dealers.get(key, {})
        if not dealer.get("available", False):
            note = dealer.get("note", f"Semrush data unavailable for {label}")
            blocks.append(merge_blocks(pill(label), muted(f"<i>{esc(note)}</i>")))
            continue

        k = dealer.get("kpis", {})
        kpi_cards = [
            {"label": "Authority Rank", "value": _fmt_int(k.get("authority_rank")), "status": "neutral"},
            {"label": "Organic Keywords", "value": _fmt_int(k.get("organic_keywords")), "status": "neutral"},
            {"label": "Est. Traffic/mo", "value": _fmt_int(k.get("organic_traffic")), "status": "neutral"},
            {"label": "Traffic Value", "value": f"${_fmt_int(k.get('traffic_value'))}", "status": "neutral"},
        ]
        if k.get("audit_health") not in (None, ""):
            try:
                hv = float(str(k.get("audit_health")).rstrip("%"))
                hstatus = "positive" if hv >= 90 else "warning" if hv >= 75 else "negative"
            except (ValueError, TypeError):
                hstatus = "neutral"
            kpi_cards.append({"label": "Site Health", "value": f"{k.get('audit_health')}%",
                              "status": hstatus})

        movers = dealer.get("movers", [])
        movers_tbl = None
        if movers:
            rows = []
            for m in movers[:12]:
                rows.append([m.get("keyword", ""), str(m.get("position", "")),
                             str(m.get("previous", "")), str(m.get("change", "")),
                             _fmt_int(m.get("volume"))])
            movers_tbl = data_table(["Keyword", "Pos", "Prev", "Chg", "Volume"], rows,
                                    [48.0, 11.0, 11.0, 11.0, 19.0])
        # Pill + KPI row + movers table as one unit (no orphaned tables).
        blocks.append(merge_blocks(pill(label), kpi_row(kpi_cards), movers_tbl))

        if weekly:
            wk = dealer.get("weekly", {})
            quick_wins = wk.get("quick_wins", [])
            if quick_wins:
                rows = [[q.get("keyword", ""), str(q.get("position", "")),
                         _fmt_int(q.get("volume")), q.get("url", "")]
                        for q in quick_wins[:8]]
                blocks.append(merge_blocks(
                    cat_label("Quick Wins (page-1, not top-3)"),
                    data_table(["Keyword", "Pos", "Volume", "URL"], rows,
                               [36.0, 10.0, 14.0, 40.0])))
            competitors = wk.get("competitors", [])
            if competitors:
                comp_txt = ", ".join(
                    c if isinstance(c, str) else c.get("domain", "") for c in competitors[:6])
                blocks.append(callout(esc(comp_txt), "info", lead="TOP ORGANIC COMPETITORS:"))
            if wk.get("branded_split"):
                blocks.append(callout(esc(wk["branded_split"]), "info",
                                      lead="BRANDED VS NON-BRANDED:"))
            if wk.get("backlinks"):
                blocks.append(callout(esc(wk["backlinks"]), "info", lead="BACKLINKS:"))

        for ins in dealer.get("insights", []):
            blocks.append(insight_block(ins))
    return blocks


def sec_news(data):
    news = data.get("news", {})
    blocks = []
    categories = [("economy", "US Economy"), ("automotive", "Automotive News")]
    for key, label in categories:
        items = news.get(key, [])
        if not items:
            continue
        first = news_item(items[0])
        blocks.append(merge_blocks(cat_label(label), first))
        for item in items[1:]:
            blocks.append(news_item(item))
    return blocks


# ── Page assembly ─────────────────────────────────────────────

def sec_head(num, eyebrow, title, subtitle=""):
    sub = f'<div class="subline">{esc(subtitle)}</div>' if subtitle else ""
    h = 108 + (20 if subtitle else 0)
    return Block(
        f'<div class="sec-head"><div class="ghost">{esc(num)}</div>'
        f'<div class="eyebrow">{esc(eyebrow)}</div>'
        f'<h2>{esc(title)}</h2>{sub}<div class="rule"></div></div>', h)


def sec_head_cont(title):
    return Block(
        f'<div class="sec-cont"><span>{esc(title)} &middot; continued</span>'
        f'<div class="rule"></div></div>', 52)


def paginate(sections):
    """Pack section blocks into fixed-height pages. Each section opens with a
    full section header; overflow onto a new page gets a compact continuation
    header so furniture and structure never disappear."""
    pages = []
    cur, used = [], 0.0

    def flush():
        nonlocal cur, used
        if cur:
            pages.append(cur)
        cur, used = [], 0.0

    for sec in sections:
        blocks = sec["blocks"]
        if not blocks:
            continue
        head = sec_head(sec["num"], sec["eyebrow"], sec["title"], sec.get("subtitle", ""))
        # A section header must never sit alone at a page bottom: it needs its
        # FULL first block to fit, else the section starts on a fresh page.
        first_h = blocks[0].h if blocks else 0
        if cur and used + head.h + first_h > PAGE_BUDGET:
            flush()
        cur.append(head.html)
        used += head.h
        for i, b in enumerate(blocks):
            if cur and used + b.h > PAGE_BUDGET:
                # Widow control: a tiny tail of a section never gets its own
                # near-empty continuation page. Height estimates run ~10-15%
                # conservative, so a small overrun still fits the real page.
                rem = sum(bb.h for bb in blocks[i:])
                if rem <= 170 and used + rem <= PAGE_BUDGET + 100:
                    for bb in blocks[i:]:
                        cur.append(bb.html)
                        used += bb.h
                    break
                flush()
                cont = sec_head_cont(sec["title"])
                cur.append(cont.html)
                used = cont.h
            cur.append(b.html)
            used += b.h
    flush()
    return pages


def furniture(page_no, total, doc_title):
    # doc_title is built internally and already entity-encoded — never re-escape.
    return (f'<div class="furniture-top">'
            f'<span class="doctitle">{doc_title}</span>'
            f'<img src="file://{LOGO_COLOR}" alt="DigitalCLIQ"></div>'
            f'<div class="furniture-bot">'
            f'<span>DigitalCLIQ &middot; Digital Strategy &amp; Development</span>'
            f'<span>Page {page_no} of {total}</span></div>')


def build_cover(meta, logo_path):
    day_name = meta.get("day_name", "")
    report_date = meta.get("report_date", "")
    date_disp = _pretty_date(report_date)
    holiday = meta.get("holiday_note", "")
    sub = (f"Your daily executive briefing: calendar, tasks, inbox pulse, live CRM "
           f"lead data, paid media, analytics, SEO, and the headlines that matter "
           f"&mdash; everything on one desk for {esc(day_name)}, {esc(date_disp)}.")
    if holiday:
        sub += f" {esc(holiday)}."
    return f'''<div class="page cover">
      <img class="logo" src="file://{logo_path}" alt="DigitalCLIQ">
      <div class="block">
        <div class="eyebrow">Daily Executive Briefing &middot; {esc(day_name)}, {esc(date_disp)}</div>
        <h1>The Coffee<br><span class="accent">Report.</span></h1>
        <div class="rule"></div>
        <div class="subtitle">{sub}</div>
      </div>
      <svg class="cursor" viewBox="0 0 100 100"><path d="M12 4 L88 58 L52 62 L68 96 L54 100 L40 68 L14 88 Z" fill="#000" opacity="0.9" transform="rotate(-12 50 50)"/></svg>
      <div class="prepared"><b>Prepared by DigitalCLIQ.</b> &nbsp;Digital Strategy &amp; Development. &nbsp;Prepared for Drew Moon. &nbsp;{esc(date_disp)}</div>
      <div class="pillars">Innovative &nbsp;|&nbsp; Clean &nbsp;|&nbsp; Minimalist &nbsp;|&nbsp; Bold &nbsp;|&nbsp; Resourceful</div>
    </div>'''


def build_html(data, logo_path):
    meta = data.get("metadata", {})
    date_disp = _pretty_date(meta.get("report_date", ""))
    doc_title = f"Coffee Report &middot; Daily Executive Briefing &middot; {esc(date_disp)}"

    # Section order is the SKILL.md contract:
    # Calendar → Tasks → Gmail → CRM → Paid → GA4 → Dashboards → SEO → News.
    seo = data.get("seo", {})
    weekly = bool(seo.get("weekly_deep_dive", False)) if seo else False
    raw_sections = [
        ("Schedule", "Today's Schedule & Week Ahead", "", sec_calendar(data)),
        ("Notion Tasks", "Task Board — Today & Tomorrow", "", sec_tasks(data)),
        ("Inbox Pulse", "Gmail — Unread, Last 24 Hours", "", sec_gmail(data)),
        ("Lead Pulse — CRM", "Live Dealership Lead Data",
         data.get("crm", {}).get("period", "") if data.get("crm") else "", sec_crm(data)),
        ("Paid Social Pulse", "Meta Ads Performance",
         data.get("paid", {}).get("period", "") if data.get("paid") else "", sec_paid(data)),
        ("Analytics Snapshot", "Live GA4 — Yesterday's Traffic", "", sec_ga4(data)),
        ("Dashboard Cross-Check", "Live Client Dashboards", "", sec_dashboards(data)),
        ("SEO Pulse — Semrush",
         "Weekly Deep-Dive — Rankings, Competitors & Backlinks" if weekly
         else "Organic Visibility & Ranking Movers", "", sec_seo(data)),
        ("Industry Intel", "Today's Headlines", "", sec_news(data)),
    ]

    sections = []
    n = 0
    for eyebrow, title, subtitle, blocks in raw_sections:
        if blocks is None:        # optional section absent from the JSON
            continue
        n += 1
        sections.append({
            "num": f"{n:02d}", "eyebrow": f"{n:02d} · {eyebrow}",
            "title": title, "subtitle": subtitle, "blocks": blocks,
        })

    # Sign-off rides the last section.
    if sections:
        sections[-1]["blocks"].append(Block(
            '<div class="signoff">Generated by Claude &middot; DigitalCLIQ &mdash; '
            'Digital Strategy &amp; Development</div>', 44))

    page_lists = paginate(sections)
    total = len(page_lists)
    interior = []
    for i, chunks in enumerate(page_lists, 1):
        interior.append(f'<div class="page interior">{furniture(i, total, doc_title)}'
                        f'{"".join(chunks)}</div>')

    body = build_cover(meta, logo_path) + "".join(interior)
    return _SHELL.replace("{{FONTS}}", _font_faces()).replace("{{BODY}}", body)


# ── Fonts ─────────────────────────────────────────────────────

def _font_faces():
    faces = [
        ("Dosis", "Dosis-Medium.ttf", 500),
        ("Dosis", "Dosis-SemiBold.ttf", 600),
        ("Dosis", "Dosis-Bold.ttf", 700),
        ("Dosis", "Dosis-ExtraBold.ttf", 800),
        ("Roboto Slab", "Roboto-Slab-Light.ttf", 300),
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

/* Canonical dark cover (Design-System §2 / templates/cover-portrait.html) */
.cover{
  background:
    radial-gradient(ellipse 420px 320px at 85% 12%, rgba(36,53,98,0.85), transparent 70%),
    radial-gradient(ellipse 500px 380px at 8% 88%, rgba(36,53,98,0.55), transparent 70%),
    linear-gradient(180deg, var(--navy-deep) 0%, var(--navy-base) 45%, var(--navy-lift) 100%);
  font-family:'Dosis',sans-serif;color:#fff;
}
.cover .logo{position:absolute;top:64px;left:70px;width:115px;}
.cover .block{position:absolute;left:70px;top:340px;width:640px;}
.cover .eyebrow{font-weight:600;font-size:15px;letter-spacing:0.24em;text-transform:uppercase;color:var(--sky-blue);margin-bottom:26px;}
.cover h1{font-weight:800;font-size:78px;line-height:1.02;text-transform:uppercase;letter-spacing:0.01em;}
.cover h1 .accent{color:var(--sky-blue);}
.cover .rule{width:64px;height:4px;background:var(--sky-blue);margin:30px 0 26px;}
.cover .subtitle{font-family:'Roboto Slab',serif;font-weight:400;font-size:19px;line-height:1.55;color:var(--body-on-dark);max-width:560px;}
.cover .cursor{position:absolute;right:105px;bottom:190px;width:85px;height:85px;}
.cover .prepared{position:absolute;left:70px;bottom:110px;font-family:'Roboto Slab',serif;font-size:14px;color:var(--muted-on-dark);}
.cover .prepared b{color:var(--body-on-dark);font-weight:400;}
.cover .pillars{position:absolute;bottom:52px;width:100%;text-align:center;font-weight:600;font-size:12px;letter-spacing:0.32em;text-transform:uppercase;color:var(--muted-on-dark);}

/* Interior (light) */
.interior{background:var(--white);padding:56px 64px 60px;}
.furniture-top{position:absolute;top:0;left:64px;right:64px;height:44px;border-bottom:2px solid var(--card-border);display:flex;align-items:center;justify-content:space-between;}
.furniture-top .doctitle{font-family:'Dosis',sans-serif;font-weight:600;font-size:10.5px;letter-spacing:0.18em;text-transform:uppercase;color:var(--warm-grey);}
.furniture-top img{height:17px;}
.furniture-bot{position:absolute;bottom:0;left:64px;right:64px;height:40px;border-top:2px solid var(--card-border);display:flex;align-items:center;justify-content:space-between;}
.furniture-bot span{font-family:'Dosis',sans-serif;font-weight:500;font-size:10.4px;letter-spacing:0.15em;text-transform:uppercase;color:var(--warm-grey);}

.sec-head{position:relative;margin:20px 0 14px;}
.sec-head .eyebrow{font-family:'Dosis',sans-serif;font-weight:600;font-size:12.5px;letter-spacing:0.22em;text-transform:uppercase;color:var(--digital-blue);margin-bottom:8px;}
.sec-head h2{font-family:'Dosis',sans-serif;font-weight:700;font-size:30px;color:#000;line-height:1.08;}
.sec-head .subline{font-family:'Roboto Slab',serif;font-size:12px;color:var(--warm-grey);margin-top:6px;}
.sec-head .rule{width:48px;height:3px;background:var(--sky-blue);margin-top:12px;}
.ghost{position:absolute;right:0;top:-14px;font-family:'Dosis',sans-serif;font-weight:800;font-size:130px;line-height:1;color:var(--digital-blue);opacity:0.07;}
.sec-cont{margin:16px 0 12px;}
.sec-cont span{font-family:'Dosis',sans-serif;font-weight:600;font-size:12px;letter-spacing:0.2em;text-transform:uppercase;color:var(--digital-blue);}
.sec-cont .rule{width:48px;height:3px;background:var(--sky-blue);margin-top:8px;}

.pill{display:inline-block;background:var(--digital-blue);color:#fff;font-family:'Dosis',sans-serif;font-weight:600;font-size:11.5px;letter-spacing:0.1em;text-transform:uppercase;padding:5px 14px;border-radius:14px;margin:6px 0 8px;}
.pill.sky{background:var(--tile-blue);}

.kpis{display:flex;gap:12px;margin:8px 0 12px;}
.kpi{flex:1;background:var(--card-white);border:1px solid var(--card-border);border-radius:12px;border-top:3px solid var(--digital-blue);padding:12px 12px 10px;position:relative;}
.kpi .num{font-family:'Dosis',sans-serif;font-weight:800;font-size:27px;line-height:1.1;}
.kpi .num.sm{font-size:20px;}
.kpi .num.pos{color:var(--sky-blue);}
.kpi .num.neg{color:var(--warm-grey);}
.kpi .num.warn{color:var(--warm-grey);}
.kpi .num.neu{color:var(--digital-blue);}
.kpi .lab{font-family:'Dosis',sans-serif;font-weight:600;font-size:9.5px;letter-spacing:0.08em;text-transform:uppercase;color:var(--warm-grey);margin-top:6px;line-height:1.35;}
.tick{position:absolute;top:9px;right:9px;width:10px;height:10px;}

.callout{background:var(--callout-tint);border-left:3px solid var(--digital-blue);border-radius:0 10px 10px 0;padding:11px 15px;font-size:12.5px;line-height:1.5;margin:6px 0 10px;}
.callout b{font-family:'Dosis',sans-serif;font-weight:700;font-size:12.5px;color:var(--tile-blue);letter-spacing:0.06em;text-transform:uppercase;}
.callout.alert{border-left-color:var(--warm-grey);}
.callout.alert b{color:var(--warm-grey);}
.callout.win{border-left-color:var(--sky-blue);}

table.data{width:100%;border-collapse:collapse;margin:6px 0 14px;border-radius:10px;overflow:hidden;}
table.data th{background:var(--digital-blue);color:#fff;font-family:'Dosis',sans-serif;font-weight:600;font-size:11px;letter-spacing:0.06em;text-transform:uppercase;padding:8px 10px;text-align:left;border-bottom:2px solid var(--sky-blue);}
table.data td{font-size:11.5px;line-height:1.45;padding:7px 10px;border-bottom:1px solid var(--card-border);vertical-align:top;}
table.data tr:nth-child(odd) td{background:var(--callout-tint);}
table.data td b{font-weight:700;color:var(--tile-blue);}

.muted{font-size:12px;color:var(--warm-grey);margin:2px 0 8px;line-height:1.5;}
.catlab{font-family:'Dosis',sans-serif;font-weight:700;font-size:12.5px;letter-spacing:0.12em;text-transform:uppercase;color:var(--tile-blue);margin:10px 0 6px;}
.news-item{margin:0 0 10px;}
.news-item .hl{font-family:'Roboto Slab',serif;font-weight:700;font-size:12.5px;line-height:1.45;color:var(--digital-blue);}
.news-item .hl a{color:var(--digital-blue);text-decoration:none;}
.news-item .nsrc{font-family:'Dosis',sans-serif;font-weight:500;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--warm-grey);margin-top:3px;}
.news-item .nsrc i{text-transform:none;letter-spacing:0.02em;font-family:'Roboto Slab',serif;}

.signoff{font-family:'Dosis',sans-serif;font-weight:500;font-size:9.5px;letter-spacing:0.18em;text-transform:uppercase;color:var(--warm-grey);text-align:center;margin-top:22px;}
</style></head><body>
{{BODY}}
</body></html>"""


# ── Rendering ─────────────────────────────────────────────────

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


def build_pdf(json_path, output_path, logo_path):
    with open(json_path, "r") as f:
        data = json.load(f)

    # Validate data before building
    is_valid, val_errors = validate_data(data, source_path=json_path)
    if not is_valid:
        print(f"ERROR: Data validation failed with {len(val_errors)} error(s). Aborting.", file=sys.stderr)
        sys.exit(1)

    # Logos must resolve (Design-System rule: fail loudly, never silently).
    if not logo_path or not os.path.exists(logo_path):
        raise FileNotFoundError(
            f"DigitalCLIQ logo not found at: {logo_path!r}\n"
            f"Canonical path: {LOGO_WHITE}")
    if not os.path.exists(LOGO_COLOR):
        raise RuntimeError(
            f"DigitalCLIQ full-color logo missing at canonical path: {LOGO_COLOR}. "
            f"Restore Resources/brand-assets/ before generating.")

    html = build_html(data, os.path.abspath(logo_path))

    # HTML output mode: if the caller asks for .html, write the document
    # straight out and skip the PDF render entirely.
    if os.path.splitext(output_path)[1].lower() in (".html", ".htm"):
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"HTML generated: {output_path}")
        return

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


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python3 generate_coffee_report.py <json_path> <output_pdf> <logo_path>")
        sys.exit(1)
    build_pdf(sys.argv[1], sys.argv[2], sys.argv[3])
