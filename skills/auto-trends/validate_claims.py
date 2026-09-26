#!/usr/bin/env python3
"""
auto-trends claims check.

Every number a GM sees on the hero bands, the headline stats and the stat cards
must carry a named source, a link, a publication date, a data period and an
actual-vs-forecast kind. Nothing else in the pipeline can tell "August 2026
data" from "an August article published in 2025": post_flight passed the 9/5
edition that shipped a year-old ATP ($49,077, published 2025-09-10) as August
2026, and a J.D. Power forecast as an actual.

MODE: WARN-ONLY for the October 2026 run. Problems print to stderr and the exit
code is 0. `--strict` (or env AUTO_TRENDS_CLAIMS=strict) exits 1 while any
ERROR-class problem remains; flip the default once an edition ships clean.

ERROR class (hard-fail candidates, hero bands + headline stats + metric cards):
  - missing source, url or published (a placeholder such as "https://..." or
    "YYYY-MM-DD" counts as missing)
  - published later than metadata.generation_date
  - kind=actual published before its period ended (the wrong year or a
    forecast); YTD / MTD / partial-period tokens pass
  - kind=actual published before its period even began
WARNING class:
  - missing period or kind, unknown kind, unparseable dates
  - no kind and published before the period began (forecast or wrong year?)
  - kind=actual on a half-year period that has not ended (use YTD if partial)
  - staleness: monthly period > 120 days old, quarterly or half > 200, annual
    exempt, no period > 200
  - forecast wording without kind=forecast, and kind=forecast printed with no
    forecast wording
  - 'record' / 'peak' / 'high' next to a number with no as-of date in the
    overview, throughline, key trends and risks
INFO: prose figures with no structured claim (add them to the facts manifest).

Usage:
  python3 validate_claims.py <data.json> [--strict] [--facts OUT.facts.json]
  python3 validate_claims.py --blog-html <Auto_Trends_Report_..._blog.html>

The --blog-html mode is the deterministic stand-in for the blog render gate on
unattended runs: every JSON-LD block parses, no em dashes, no placeholders. It
is also warn-only (exit 0) unless --strict is passed.
"""

import calendar
import datetime as _dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

REQUIRED_SECTIONS = ["metadata", "executive_summary", "new_vehicle_sales",
                     "used_vehicle_sales", "fixed_ops", "parts",
                     "strategic_outlook", "sources"]
REQUIRED_META = ["report_title", "region", "generation_date"]
TRENDS = {"up", "down", "flat"}
KINDS = {"actual", "forecast", "estimate", "market-implied"}
FORECASTY_KINDS = {"forecast", "market-implied", "estimate"}

STALE_DAYS = {"day": 120, "month": 120, "quarter": 200, "half": 200,
              "year": None, "ytd": 200, None: 200}

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
MONTHS["sept"] = 9
_MONTH_RE = "|".join(sorted((re.escape(k) for k in MONTHS), key=len, reverse=True))

EM_DASH = "\u2014"
# a real host, so a schema placeholder such as "https://..." does not pass
_URL_RE = re.compile(r"https?://[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?:[/:?#]\S*)?$")


# ── date helpers ──────────────────────────────────────────────────────────
def _last_day(y, m):
    return _dt.date(y, m, calendar.monthrange(y, m)[1])


def parse_published(value):
    """'YYYY-MM-DD' | 'YYYY-MM' | 'YYYY' -> (earliest, latest) dates, or None.
    A month-only value is read generously: its first day for the 'not after
    generation date' check, its last day for the 'not before period end'
    check, so imprecision never manufactures an error."""
    s = str(value or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            d = _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
        return d, d
    m = re.fullmatch(r"(\d{4})-(\d{2})", s)
    if m and 1 <= int(m.group(2)) <= 12:
        y, mo = int(m.group(1)), int(m.group(2))
        return _dt.date(y, mo, 1), _last_day(y, mo)
    m = re.fullmatch(r"(\d{4})", s)
    if m:
        y = int(s)
        return _dt.date(y, 1, 1), _dt.date(y, 12, 31)
    return None


_PARTIAL_RE = re.compile(r"\b(ytd|mtd|qtd|ttm|to[- ]date|partial|through|thru|"
                         r"mid-month|month-to-date|year-to-date)\b", re.I)


def parse_period(value):
    """Data period -> {'start', 'end', 'grain', 'partial'} or None.
    Forms: YYYY-MM-DD, YYYY-MM, YYYY-Qn, YYYY-Hn, YYYY, YTD / YYYY-YTD, plus
    'Qn YYYY', 'Hn YYYY' and 'Month YYYY'. Any YTD/partial marker sets partial."""
    s = str(value or "").strip()
    if not s:
        return None
    partial = bool(_PARTIAL_RE.search(s))
    core = _PARTIAL_RE.sub("", s).strip(" -,:")
    out = None
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", core)
    if m:
        try:
            d = _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            out = {"start": d, "end": d, "grain": "day"}
        except ValueError:
            return None
    if out is None:
        m = re.fullmatch(r"(\d{4})-(\d{2})", core)
        if m and 1 <= int(m.group(2)) <= 12:
            y, mo = int(m.group(1)), int(m.group(2))
            out = {"start": _dt.date(y, mo, 1), "end": _last_day(y, mo), "grain": "month"}
    if out is None:
        m = (re.fullmatch(r"(\d{4})\s*-?\s*Q([1-4])", core, re.I)
             or re.fullmatch(r"Q([1-4])\s*-?\s*(\d{4})", core, re.I))
        if m:
            a, b = m.group(1), m.group(2)
            y, q = (int(a), int(b)) if len(a) == 4 else (int(b), int(a))
            out = {"start": _dt.date(y, 3 * q - 2, 1), "end": _last_day(y, 3 * q),
                   "grain": "quarter"}
    if out is None:
        m = (re.fullmatch(r"(\d{4})\s*-?\s*H([12])", core, re.I)
             or re.fullmatch(r"H([12])\s*-?\s*(\d{4})", core, re.I))
        if m:
            a, b = m.group(1), m.group(2)
            y, h = (int(a), int(b)) if len(a) == 4 else (int(b), int(a))
            out = {"start": _dt.date(y, 6 * h - 5, 1), "end": _last_day(y, 6 * h),
                   "grain": "half"}
    if out is None:
        m = re.fullmatch(rf"({_MONTH_RE})\.?\s+(\d{{4}})", core, re.I)
        if m:
            y, mo = int(m.group(2)), MONTHS[m.group(1).lower()]
            out = {"start": _dt.date(y, mo, 1), "end": _last_day(y, mo), "grain": "month"}
    if out is None:
        m = re.fullmatch(r"(\d{4})", core)
        if m:
            y = int(core)
            out = {"start": _dt.date(y, 1, 1), "end": _dt.date(y, 12, 31), "grain": "year"}
    if out is None and partial and not core:
        # bare "YTD": the year is unknown, so only the partial flag is usable
        out = {"start": None, "end": None, "grain": "ytd"}
    if out is None:
        return None
    if partial:
        out["partial"] = True
        if out["grain"] == "year":
            out["grain"] = "ytd"
    else:
        out["partial"] = False
    return out


def infer_published_from_citation(text):
    """Best-effort publication date from a trailing citation such as
    'Kelley Blue Book, August 11 2026' or 'Cox Automotive, August 2026'. Only
    day and month forms count: 'Q2 2026' and a bare year name a data period,
    not a publication date."""
    t = str(text or "").strip().rstrip(".) ")
    m = re.search(rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})$", t, re.I)
    if m:
        try:
            return _dt.date(int(m.group(3)), MONTHS[m.group(1).lower()],
                            int(m.group(2))).isoformat()
        except ValueError:
            return None
    m = re.search(rf"\b({_MONTH_RE})\.?\s+(\d{{4}})$", t, re.I)
    if m:
        return f"{int(m.group(2)):04d}-{MONTHS[m.group(1).lower()]:02d}"
    return None


# ── claim collection ──────────────────────────────────────────────────────
def _d(x):
    return x if isinstance(x, dict) else {}


def _citation(detail):
    """Trailing citation off a metric detail, using the generator's own parser
    so the check and the stat card agree on what the source line is."""
    try:
        from generate_trends_report import extract_src
    except Exception:  # generator missing or broken: fall back to parenthetical
        m = re.search(r"\(([^()]+)\)\s*\.?\s*$", str(detail or "").strip())
        return m.group(1).strip() if m else ""
    return extract_src(detail or "")[1]


def _first_sentence(text, n=90):
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    m = re.search(r"(?<![A-Z])[.!?]\s", t)
    if m:
        t = t[:m.start()]
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "..."


def collect_claims(data):
    """Every structured claim the PDF prints (plus metrics the blog and archive
    carry), in page order. `page` is the PDF page (cover = 1) or None."""
    claims = []

    def add(cid, obj, page, where, label, text_for_cite, kind_of):
        if not isinstance(obj, dict):
            return
        value = str(obj.get("value", "")).strip()
        if not value:
            return
        src = str(obj.get("source") or "").strip()
        cite = _citation(text_for_cite) if text_for_cite else ""
        # Body text minus citations, so a publisher name ("CNCDA California
        # Auto Outlook") never reads as forecast wording.
        body = str(obj.get("detail") or obj.get("caption") or "")
        if cite:
            body = body.replace(cite, " ")
        body = re.sub(r"\([^()]*\)", " ", body)
        claims.append({
            "id": cid,
            "kind_of_claim": kind_of,
            "page": page,
            "where": where,
            "value": value,
            "label": str(label or "").strip(),
            "source": src or cite,
            "citation_in_text": cite,
            "url": str(obj.get("url") or "").strip(),
            "published": str(obj.get("published") or "").strip(),
            "period": str(obj.get("period") or "").strip(),
            "kind": str(obj.get("kind") or "").strip().lower(),
            "text": " ".join(str(obj.get(k, "")) for k in ("label", "caption", "detail")),
            # what the reader actually sees next to the number
            "printed": (value + " " + str(obj.get("caption", ""))) if kind_of == "hero"
                       else (value + " " + str(obj.get("label", ""))),
            # label plus the opening sentence of the detail or caption: enough to
            # spot a forecast without tripping on context sentences
            "lead": " ".join([value, str(obj.get("label", "")), _first_sentence(body, 400)]),
        })

    ex = _d(data.get("executive_summary"))
    hero = ex.get("hero")
    if isinstance(hero, dict):
        add("executive_summary.hero", hero, 2, "p2 exec hero band",
            _first_sentence(hero.get("caption")), hero.get("caption"), "hero")
    for i, st in enumerate(ex.get("headline_stats") or []):
        add(f"executive_summary.headline_stats[{i}]", st, 2 if i < 4 else None,
            "p2 exec headline stat" if i < 4 else "not printed (over 4)",
            _d(st).get("label"), None, "headline_stat")

    def metrics(path, mets, page, limit, where):
        for i, m in enumerate(mets or []):
            if not isinstance(m, dict):
                continue
            on_page = page if (page and i < limit) else None
            add(f"{path}[{i}]", m, on_page,
                where if on_page else "blog and archive only",
                m.get("label"), m.get("detail"), "metric")

    nv = _d(data.get("new_vehicle_sales"))
    metrics("new_vehicle_sales.national.metrics",
            _d(nv.get("national")).get("metrics"), 3, 4, "p3 new vehicle stat card")
    metrics("new_vehicle_sales.regional.metrics",
            _d(nv.get("regional")).get("metrics"), None, 0, "")
    uv = _d(data.get("used_vehicle_sales"))
    metrics("used_vehicle_sales.metrics", uv.get("metrics"), 4, 8, "p4 used vehicle stat card")
    metrics("used_vehicle_sales.regional.metrics",
            _d(uv.get("regional")).get("metrics"), 4, 4, "p4 used regional stat card")
    fo = _d(data.get("fixed_ops"))
    if isinstance(fo.get("hero"), dict):
        add("fixed_ops.hero", fo["hero"], 5, "p5 fixed ops hero band",
            _first_sentence(fo["hero"].get("caption")), fo["hero"].get("caption"), "hero")
    metrics("fixed_ops.metrics", fo.get("metrics"), 5, 4, "p5 fixed ops stat card")
    pt = _d(data.get("parts"))
    metrics("parts.metrics", pt.get("metrics"), 6, 8, "p6 parts stat card")
    return claims


# ── checks ────────────────────────────────────────────────────────────────
def check_structure(data):
    """Shape errors that break the generator or leave a page empty."""
    errs = []
    if not isinstance(data, dict):
        return ["Top-level JSON must be an object"]
    for s in REQUIRED_SECTIONS:
        if s not in data:
            errs.append(f"Missing required section: {s}")
    meta = data.get("metadata")
    if isinstance(meta, dict):
        for k in REQUIRED_META:
            if not str(meta.get(k, "")).strip():
                errs.append(f"metadata.{k} is empty")
        gd = str(meta.get("generation_date", "")).strip()
        if gd and parse_published(gd) is None:
            errs.append(f"metadata.generation_date is not YYYY-MM-DD: {gd!r}")
    elif "metadata" in data:
        errs.append("metadata must be an object")
    ex = data.get("executive_summary")
    if isinstance(ex, dict):
        if not str(ex.get("overview", "")).strip():
            errs.append("executive_summary.overview is missing or empty")
    elif "executive_summary" in data:
        errs.append("executive_summary must be an object")
    if "sources" in data and not isinstance(data.get("sources"), list):
        errs.append("sources must be a list of strings")
    for key in ("new_vehicle_sales", "used_vehicle_sales", "fixed_ops", "parts"):
        sec = data.get(key)
        if not isinstance(sec, dict):
            continue
        groups = [("metrics", sec.get("metrics"))]
        for sub in ("national", "regional"):
            if isinstance(sec.get(sub), dict):
                groups.append((f"{sub}.metrics", sec[sub].get("metrics")))
        for gname, mets in groups:
            for i, m in enumerate(mets or []):
                if not isinstance(m, dict):
                    errs.append(f"{key}.{gname}[{i}] is not an object")
                    continue
                t = m.get("trend")
                if t is not None and t not in TRENDS:
                    errs.append(f"{key}.{gname}[{i}] trend must be up/down/flat, got {t!r}")
    return errs


_FORECAST_WORDS = re.compile(r"\b(forecast|forecasts|projected|projection|projects|"
                             r"expected to|outlook|odds|will reach|estimate[sd]?)\b", re.I)
_RECORD_RE = re.compile(r"\brecord\b|\bpeak(?:ed|s)?\b|\bhighest\b|\blowest\b|"
                        r"\b(?:all-time|new|decade|multi-year|\d+-(?:year|month)|"
                        r"\d+ (?:year|month)|year|month)[- ]high\b", re.I)
_DATE_TOKEN = re.compile(rf"\b(?:19|20)\d{{2}}\b|\bas of\b|\bQ[1-4]\b|\b(?:{_MONTH_RE})\b",
                         re.I)
_NUM_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?\s?(?:%|percent|[MBK]\b|million|billion|"
                     r"basis points|bps|days|years)?", re.I)


def _figures(text):
    """Meaningful figures in a prose string: money, percents, unit-bearing or
    decimal numbers. Years and small bare counts are skipped."""
    out = []
    for m in _NUM_RE.finditer(str(text or "")):
        tok = m.group(0).strip()
        core = re.sub(r"[^\d.]", "", tok)
        if not core or core == ".":
            continue
        has_unit = bool(re.search(r"[$%MBK]|million|billion|percent|basis|bps|days|years",
                                  tok, re.I))
        if re.fullmatch(r"(19|20)\d{2}", core) and not has_unit:
            continue
        if not has_unit and "." not in core and "," not in tok and len(core) < 3:
            continue
        out.append(tok)
    return out


def _core(tok):
    return re.sub(r"[^\d.]", "", tok).rstrip(".")


def _sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9$])", str(text or "")) if s.strip()]


def validate_claims(data, today=None):
    """Run every check. Returns a dict:
    {"errors": [...], "warnings": [...], "unmatched_prose": [...], "claims": [...]}.
    Never raises on bad content; structure errors are included in errors."""
    errors, warnings = [], []
    struct = check_structure(data)
    errors.extend(struct)
    if not isinstance(data, dict):
        return {"errors": errors, "warnings": warnings, "unmatched_prose": [], "claims": []}

    meta = _d(data.get("metadata"))
    gen = parse_published(meta.get("generation_date", ""))
    gen_date = gen[0] if gen else (today or _dt.date.today())

    claims = collect_claims(data)
    for c in claims:
        tag = f"{c['id']} ({c['value']})"
        if not c["source"]:
            errors.append(f"{tag}: no named source (end the detail with "
                          f"'(Publisher, Month YYYY)' and fill source)")
        if not _URL_RE.match(c["url"]):
            errors.append(f"{tag}: no url to the page the figure came from")
        pub = parse_published(c["published"]) if c["published"] else None
        inferred = None
        if not c["published"]:
            inferred = infer_published_from_citation(c["citation_in_text"] or c["source"])
            hint = f" (citation text suggests {inferred})" if inferred else ""
            errors.append(f"{tag}: no published date{hint}; add published: YYYY-MM-DD")
            pub = parse_published(inferred) if inferred else None
        elif pub is None:
            errors.append(f"{tag}: published {c['published']!r} is not a date (YYYY-MM-DD)")

        per = parse_period(c["period"]) if c["period"] else None
        if not c["period"]:
            warnings.append(f"{tag}: no period (YYYY-MM | YYYY-Qn | YYYY-Hn | YYYY | YTD)")
        elif per is None:
            warnings.append(f"{tag}: period {c['period']!r} is not a recognized form")
        kind = c["kind"]
        if not kind:
            warnings.append(f"{tag}: no kind (actual | forecast | estimate | market-implied)")
        elif kind not in KINDS:
            warnings.append(f"{tag}: unknown kind {kind!r}")

        if pub:
            earliest, latest = pub
            if earliest > gen_date:
                errors.append(f"{tag}: published {earliest.isoformat()} is after the "
                              f"report date {gen_date.isoformat()}")
            if per and per.get("start") and latest < per["start"] and kind not in FORECASTY_KINDS:
                # A forecast may predate its period; an actual never can.
                msg = (f"{tag}: published {latest.isoformat()} before its period "
                       f"{c['period']} even began: the wrong year, or a forecast "
                       f"(then set kind=forecast)")
                (errors if kind == "actual" else warnings).append(msg)
            elif (per and kind == "actual" and per.get("end") and not per["partial"]
                  and latest < per["end"]):
                msg = (f"{tag}: kind=actual but published {latest.isoformat()} before "
                       f"period {c['period']} ended: the wrong year or a forecast")
                # A half-year actual can be a first-half-to-date read; that is a
                # labeling slip (use YTD), not a wrong-year figure.
                (warnings if per["grain"] == "half" else errors).append(msg)
            limit = STALE_DAYS.get(per["grain"] if per else None, 200)
            if limit is not None and (gen_date - latest).days > limit:
                warnings.append(f"{tag}: published {latest.isoformat()}, "
                                f"{(gen_date - latest).days} days before the report "
                                f"(limit {limit} for this period type); refresh it or "
                                f"say in the copy which month the data is")

        fw = _FORECAST_WORDS.search(c["lead"])
        if fw and kind not in FORECASTY_KINDS:
            warnings.append(f"{tag}: reads like a forecast or estimate "
                            f"('{fw.group(0)}') but kind is {kind or 'missing'}")
        if kind in ("forecast", "market-implied") and not _FORECAST_WORDS.search(c["printed"]):
            warnings.append(f"{tag}: kind={kind} but nothing where it prints says "
                            f"forecast / projected / odds; label it as a forecast")

    # 'record' / 'peak' / 'high' in prose with no as-of date
    ex = _d(data.get("executive_summary"))
    so = _d(data.get("strategic_outlook"))
    prose_fields = [("executive_summary.overview", ex.get("overview")),
                    ("executive_summary.throughline", ex.get("throughline"))]
    prose_fields += [(f"executive_summary.key_trends[{i}]", t)
                     for i, t in enumerate(ex.get("key_trends") or [])]
    prose_fields += [(f"strategic_outlook.risks[{i}]", t)
                     for i, t in enumerate(so.get("risks") or [])]
    for where, text in prose_fields:
        for sent in _sentences(text):
            if _RECORD_RE.search(sent) and _figures(sent) and not _DATE_TOKEN.search(sent):
                warnings.append(f"{where}: '{_RECORD_RE.search(sent).group(0)}' claim with "
                                f"a number and no as-of date: \"{sent.strip()[:140]}\"")

    # prose figures with no structured claim behind them
    claim_cores = set()
    for c in claims:
        for tok in _figures(c["value"] + " " + c["text"]):
            claim_cores.add(_core(tok))
    unmatched = []
    seen = set()
    for where, text in _prose_everywhere(data):
        for tok in _figures(text):
            core = _core(tok)
            if core and core not in claim_cores and (where, core) not in seen:
                seen.add((where, core))
                unmatched.append({"where": where, "figure": tok})

    return {"errors": errors, "warnings": warnings, "unmatched_prose": unmatched,
            "claims": claims}


def _prose_everywhere(data):
    ex = _d(data.get("executive_summary"))
    out = [("executive_summary.overview", ex.get("overview")),
           ("executive_summary.throughline", ex.get("throughline"))]
    out += [(f"executive_summary.key_trends[{i}]", t)
            for i, t in enumerate(ex.get("key_trends") or [])]
    for key in ("new_vehicle_sales", "used_vehicle_sales", "fixed_ops", "parts"):
        sec = _d(data.get(key))
        for f in ("summary", "outlook_6mo", "outlook_12mo", "ev_readiness",
                  "technician_market", "oem_vs_aftermarket", "ev_impact"):
            if sec.get(f):
                out.append((f"{key}.{f}", sec[f]))
        for sub in ("national", "regional"):
            if isinstance(sec.get(sub), dict) and sec[sub].get("summary"):
                out.append((f"{key}.{sub}.summary", sec[sub]["summary"]))
        for i, h in enumerate(sec.get("oem_highlights") or []):
            if isinstance(h, dict):
                out.append((f"{key}.oem_highlights[{i}]", h.get("detail")))
    so = _d(data.get("strategic_outlook"))
    for f in ("short_term", "medium_term", "risks", "opportunities"):
        out += [(f"strategic_outlook.{f}[{i}]", t) for i, t in enumerate(so.get(f) or [])]
    return out


def validate_data(data, today=None):
    """(is_valid, errors): structure errors plus the ERROR-class claim problems.
    Warnings are not failures. Kept for tests/validate_skill.py."""
    rep = validate_claims(data, today=today)
    return (not rep["errors"], rep["errors"])


# ── facts manifest ────────────────────────────────────────────────────────
def facts_manifest(data, report=None):
    """The reviewer's manifest, built from the structured claims instead of by
    hand: one entry per hero, headline stat and metric card."""
    rep = report or validate_claims(data)
    out = []
    for c in rep["claims"]:
        label = f"{c['where']}: {c['label']}" if c["label"] else c["where"]
        out.append({
            "id": c["id"], "value": c["value"], "label": label,
            "source": c["source"], "url": c["url"], "published": c["published"],
            "period": c["period"], "kind": c["kind"], "page": c["page"],
            "origin": "generator",
        })
    return out


def write_facts(data, out_path, report=None):
    """Write <stem>.facts.json. Entries a person or agent appended by hand (any
    entry whose origin is not 'generator', e.g. prose-only figures) survive a
    re-render; generator entries are rebuilt from the data every time."""
    keep = []
    if os.path.exists(out_path):
        try:
            with open(out_path) as f:
                prior = json.load(f)
            if isinstance(prior, list):
                keep = [e for e in prior
                        if isinstance(e, dict) and e.get("origin") != "generator"]
        except Exception:
            keep = []
    entries = facts_manifest(data, report) + keep
    with open(out_path, "w") as f:
        json.dump(entries, f, indent=1, ensure_ascii=False)
    return out_path


# ── report formatting ─────────────────────────────────────────────────────
def format_report(rep, max_unmatched=40):
    lines = []
    n_claims = len(rep["claims"])
    if not rep["errors"] and not rep["warnings"]:
        lines.append(f"claims check: CLEAN ({n_claims} claims)")
    else:
        lines.append(f"claims check: {len(rep['errors'])} error(s), "
                     f"{len(rep['warnings'])} warning(s) across {n_claims} claims")
    for e in rep["errors"]:
        lines.append(f"  ERROR  {e}")
    for w in rep["warnings"]:
        lines.append(f"  WARN   {w}")
    um = rep.get("unmatched_prose") or []
    if um:
        lines.append(f"  INFO   {len(um)} prose figure(s) with no structured claim; add each "
                     f"to the facts manifest by hand (origin: prose):")
        for u in um[:max_unmatched]:
            lines.append(f"           {u['where']}: {u['figure']}")
        if len(um) > max_unmatched:
            lines.append(f"           ... and {len(um) - max_unmatched} more")
    return "\n".join(lines)


def strict_mode():
    return os.environ.get("AUTO_TRENDS_CLAIMS", "").strip().lower() == "strict"


# ── blog pre-check (unattended stand-in for the HTML visual gate) ─────────
_PLACEHOLDERS = [(r"\{[a-z_]+\}", 0), (r"\{\{", 0), (r"YYYY-MM-DD", 0),
                 (r"\bPLACEHOLDER\b", 0), (r"lorem ipsum", re.I), (r"\bTODO\b", 0),
                 (r"\bTBD\b", 0), (r"\bsee row\b", re.I)]


def check_blog_html(path):
    """Deterministic checks a script can make without a browser: every JSON-LD
    block parses, no em dashes, no placeholder tokens. Returns problems."""
    problems = []
    with open(path, encoding="utf-8") as f:
        html = f.read()
    blocks = re.findall(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>",
                        html, re.S | re.I)
    if not blocks:
        problems.append("no JSON-LD block found (expected Article and FAQPage)")
    for i, b in enumerate(blocks):
        try:
            json.loads(b)
        except Exception as e:
            problems.append(f"JSON-LD block {i + 1} does not parse: {e}")
    n = html.count(EM_DASH)
    if n:
        problems.append(f"{n} em dash(es) in the blog HTML (house rule: none)")
    for pat, flags in _PLACEHOLDERS:
        hits = re.findall(pat, html, flags)
        if hits:
            problems.append(f"placeholder token {hits[0]!r} appears {len(hits)} time(s)")
    return problems


# ── CLI ───────────────────────────────────────────────────────────────────
def main(argv):
    strict = "--strict" in argv or strict_mode()
    args = [a for a in argv if a != "--strict"]
    if args[:1] == ["--blog-html"] and len(args) >= 2:
        problems = check_blog_html(args[1])
        if problems:
            print(f"blog pre-check: {len(problems)} problem(s) in {args[1]}", file=sys.stderr)
            for p in problems:
                print(f"  WARN   {p}", file=sys.stderr)
        else:
            print(f"blog pre-check: CLEAN ({args[1]})", file=sys.stderr)
        return 1 if (strict and problems) else 0
    facts_out = None
    if "--facts" in args:
        i = args.index("--facts")
        if i + 1 >= len(args):
            print("--facts needs an output path", file=sys.stderr)
            return 2
        facts_out = args[i + 1]
        args = args[:i] + args[i + 2:]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    with open(args[0]) as f:
        data = json.load(f)
    rep = validate_claims(data)
    print(format_report(rep), file=sys.stderr)
    if facts_out:
        write_facts(data, facts_out, rep)
        print(f"facts manifest: {facts_out}", file=sys.stderr)
    if rep["errors"] and not strict:
        print("claims check is WARN-ONLY this cycle: fix the data (research the "
              "missing field, correct period/kind) and re-run; exit 0.", file=sys.stderr)
    return 1 if (strict and rep["errors"]) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
