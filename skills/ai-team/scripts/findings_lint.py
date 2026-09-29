#!/usr/bin/env python3
"""Findings pre-check for the DigitalCLIQ AI team. Standard library only.

  python3 .claude/skills/ai-team/scripts/findings_lint.py --player shaq --date 2026-09-28
  python3 .claude/skills/ai-team/scripts/findings_lint.py --player all --date 2026-09-28 --out outputs/ai-team/2026-09-28/data/lint.md
  python3 .claude/skills/ai-team/scripts/findings_lint.py --player kobe --date 2026-09-28 --target-date 2026-09-26
  python3 .claude/skills/ai-team/scripts/findings_lint.py --player worthy --date 2026-09-28 --file outputs/ai-team/2026-09-28/draft.md
  python3 .claude/skills/ai-team/scripts/findings_lint.py selftest

A player runs it on outputs/ai-team/{date}/{player}.md before telling Magic the file is ready, and
fixes or explains every warning. It catches the mechanical misses Magic kept bouncing (9/22 to 9/28):
wrong weekday next to a date, placeholders left in, em dashes, a cited data file that is not on
disk, numbers from a RED store, "settled" on an ask that is still open, a subject Drew already ruled
on raised as new, the newest (incomplete) day quoted without "preliminary", pulls that were read
live but never saved to the vault, and NabThat dashboard boxes or dollars quoted as NabThat's own.
It is a warn-only gate: it never edits the findings file.

Output: one line per warning,
  WARN outputs/ai-team/2026-09-28/shaq.md:27 [rule] what is wrong | fix: what to do
then "lint: N warnings". Exit 0 when clean, 1 when there are warnings, 2 on a usage error (file
or folder missing). --out PATH also writes the report (.json gives a JSON list, anything else the
same text). --player all lints every findings file in the shift folder.

Inputs it reads (all optional except the findings file; a missing one skips its rule and prints a
NOTE line, never a warning):
  .claude/agents/{player}.md             ## Output section: the required headings
  outputs/ai-team/{date}/data/health.json  RED stores and the numbers they block
  outputs/ai-team/ledgers/rulings.json   Drew's standing rulings
  outputs/ai-team/ledgers/settled.json   {"settled":[{"id","store","lane","subject","keywords",
                                          "settled_on","finding","reopen_if"}]}
  outputs/ai-team/ledgers/asks.json      ask status on the shift date
  outputs/ai-team/{earlier date}/{player}.md   last shift's headlines (repeat check)

Target date: --target-date, default the day before --date. At 1 AM that day is incomplete (GA4
fills in for 24 to 48 hours, Ads conversions backfill, Meta results restate), so a claim about its
numbers must say preliminary. With a --target-date older than yesterday the rule is skipped.

Rules (24 warning names; name: what it flags):
  heading-missing / heading-empty / heading-order   the agent file's Output headings; Report to
      Magic is the last section before Sources; Sources must list something
  placeholder        [PENDING], TODO, TBD, FIXME, {curly placeholders} outside file paths, XX
  em-dash            U+2014 anywhere
  weekday-mismatch   "Friday 9/24", "Sun-Mon (9/21-22)", "9/24 (Wed)" where the calendar disagrees
  date-future        a date after the shift date, unless worded as a deadline ("before 10/1")
  date-old           an explicit-year date more than 45 days old outside Radar, Sources, topics
  prelim-missing     a number for the target date (yesterday) with no "preliminary" wording: every
      Headlines and Report to Magic line on its own (they get copied into the brief); the body is
      covered by one line that says the newest day is preliminary, else one warning lists the lines.
      Shaq and Luka only for lagging metrics (conversions, results, leads, CPA), Nick only on GA4
      lines, Worthy only on GA4 numbers (a Semrush snapshot date is not a GA4 day)
  ruling-repeat      a subject an active rulings.json ruling covers, raised without citing it
      (a ruling dated the shift date counts only if its Slack ts is before 1 AM)
  settled-repeat     a settled.json item (settled before the shift date, lane includes the player)
      in Headlines or Report to Magic with nothing changed, or in the body without its id or a
      "settled check" (one warning per item, listing the lines)
  red-number         a number a RED store's health.json "blocks" list covers, given without the
      caveat (RED, inflated, page view, clean subset, ...)
  ask-status         "settled/closed" on an ask open on the shift date, "still open" on one that
      was already closed, or an ask id asks.json does not have
  path-missing       a cited data/ path (brace lists and {STORE} expanded) that is not on disk
  source-not-saved   a Sources line with no saved file behind it (console output, ad hoc pull,
      Sheet tab read live, URL with no saved copy); Drew 2026-09-28: every pull is a local file
  absence-unsourced  "not indexed", "no ... exists", "nobody", "first in market", "zero results"
      with no saved file cited on the line
  headline-conflict  the same store, metric and window with different numbers in Headlines and in
      Report to Magic
  repeat-headline    a headline that says the same thing as last shift's headline (40% or more of
      the same words) or calls itself a repeat ("seventh straight night", "no change", "same story
      as"), with no delta named
  no-date-range      a headline number with no date or window next to it
  account-id         an Ads customer id or Meta account id outside Sources
  actor-missing      (Shaq, Luka) an account change with nobody named as who made it
  coming-up-missing  (shifts from 2026-09-29) Report to Magic has no "coming up" line
  vendor-site-boxes  a line naming NabThat with sessions, visits, engagement rate, form submissions,
      forms or asc_form_submission, unless it says whole website / whole site / site-wide / entire
      site / all channels / not NabThat, or is a credit split line (estimat, untagged, split,
      credited). NabThat's dashboard boxes are the whole website in GA4, not NabThat's traffic
  vendor-implied-cost  a line naming NabThat with a dollar amount and spend / spent / spending /
      cost, unless it says implied, clicks x, sheet, fee(s), cap, budget, invoice, per credited,
      per key event or per lead. The dashboard has no Cost box: its dollars are implied
      (clicks x avg CPC)

Explaining a warning instead of fixing it: put an Obsidian comment on the flagged line (hidden in
reading view, never read by the rules), with the rule name and a real reason (8+ characters):
  ... 9/27 spent $14.53 ... %%lint-ok prelim-missing: spend is final at 1 AM, conversions not quoted%%
A missing-heading warning (line 1) can be waived from any line. Waived warnings print as WAIVED
lines with the reason, are not counted, and Magic judges each one. A rule name written with
underscores (vendor_site_boxes) waives the same as the hyphen form.

selftest builds a synthetic vault in a temp folder, lints a dirty file (every rule must fire), a
clean one (no warnings) and a line-by-line vendor fixture (each vendor rule's hits, exemptions,
skipped sections and waivers), and exits 0 on pass.
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)
PLAYERS = ("kobe", "shaq", "luka", "worthy", "nick")
ALL_STORES = ["SBMW", "NCBMW", "NOI", "MCP", "ATLAS"]
PLAYER_STORES = {
    "kobe": ALL_STORES, "worthy": ALL_STORES, "luka": ALL_STORES,
    "shaq": ["MCP", "NOI", "ATLAS", "NCBMW"], "nick": ["SBMW", "NOI"],
}
STORE_RES = [
    ("SBMW", re.compile(r"\bSBMW\b|\bSterling\b", re.I)),
    ("NCBMW", re.compile(r"\bNCBMW\b|\bNew Century\b", re.I)),
    ("NOI", re.compile(r"\bNOI\b|\bNissan of Irvine\b", re.I)),
    ("MCP", re.compile(r"\bMCP\b|\bMcPeek", re.I)),
    ("ATLAS", re.compile(r"\bATLAS\b", re.I)),
    ("CHC", re.compile(r"\bCHC\b|\bCovina Hills\b", re.I)),
]
OLD_DAYS = 45
COMING_UP_FROM = dt.date(2026, 9, 29)
FALLBACK_HEADINGS = {
    "kobe": ["Measurement health", "Headlines", "By store", "Huddles", "Data gaps", "Report to Magic", "Sources"],
    "shaq": ["Headlines", "By store", "Vendor PPC (NCBMW)", "Recommendations", "Huddles", "Data gaps", "Report to Magic",
             "Sources"],
    "luka": ["Headlines", "By store", "Recommendations", "Huddles", "Data gaps", "Report to Magic", "Sources"],
    "worthy": ["Headlines", "By store", "GA4 match", "Topic proposals", "Content", "Huddles", "Data gaps",
               "Report to Magic", "Sources"],
    "nick": ["Report freshness", "Headlines", "By store", "Web-to-CRM reconciliation", "Huddles", "Source mapping",
             "Data gaps", "Report to Magic", "Sources"],
}
# Sections whose job is citing old material; date-old and several claim rules skip them.
REFERENCE_SECTIONS = ("sources", "radar", "topic proposals", "content", "source mapping", "value line")
ADS_TABS = ("campaign_daily_30d", "conversions_by_action_7d", "change_events_14d", "search_terms_7d",
            "keywords_7d", "adgroup_7d", "ads_policy_issues", "ad_text_7d")
DATA_PREFIX = (r"(?:ga4_organic_|ga4_|gsc_|meta_|crm_mtd_|crm_|semrush_|seo_join|ad_text_|ads_|sources_|health|"
               r"dashboards|value_line|ask_answers|deltas|changes_|kobe_|shaq_|luka_|worthy_|nick_|magic_|"
               r"(?:SBMW|NCBMW|NOI|MCP|ATLAS|CHC)_)")

# ---------------------------------------------------------------- dates
WD_NAMES = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
WD_FULL = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10,
          "nov": 11, "dec": 12}
WD = r"(?:Mon(?:day)?|Tue(?:s(?:day)?)?|Wed(?:s|nesday)?|Thu(?:r(?:s(?:day)?)?)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)\b"
ISO = r"20\d\d-[01]\d-[0-3]\d"
MD = r"(?<![\d/.$,])(?:1[0-2]|0?[1-9])/(?:3[01]|[12]\d|0?[1-9])(?:/(?:20)?\d\d)?(?![\d/%])"
MOND = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
        r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+(?:3[01]|[12]\d|0?[1-9])(?:st|nd|rd|th)?(?:,?\s+20\d\d)?(?!\d)")
ORD = r"(?:3[01]|[12]\d|0?[1-9])(?:st|nd|rd|th)\b"
DASHES = r"(?:-|" + EN_DASH + r"|\bto\b|\bthrough\b|\bthru\b)"
DATE_TOKEN = rf"(?:{ISO}|{MD}|{MOND})"
RE_DATE_ANY = re.compile(rf"(?P<tok>{ISO}|{MD}|{MOND})")
RE_WD_SINGLE = re.compile(rf"(?P<wd>{WD})(?:'s)?,?\s+(?:the\s+)?\(?\s*(?P<dt>{ISO}|{MD}|{MOND}|{ORD})")
RE_DT_WD = re.compile(rf"(?P<dt>{ISO}|{MD}|{MOND})\s*\(\s*(?P<wd>{WD})\s*\)")
RE_WD_RANGE = re.compile(rf"(?P<wd1>{WD})\s*{DASHES}\s*(?P<wd2>{WD}),?\s*\(?\s*(?P<d1>{DATE_TOKEN})\s*{DASHES}\s*"
                         rf"(?P<d2>{DATE_TOKEN}|(?:3[01]|[12]\d|0?[1-9])(?!\d))")
RE_DT_RANGE_WD = re.compile(rf"(?P<d1>{DATE_TOKEN})\s*{DASHES}\s*(?P<d2>{DATE_TOKEN}|(?:3[01]|[12]\d|0?[1-9])(?!\d))"
                            rf"\s*\(\s*(?P<wd1>{WD})\s*{DASHES}\s*(?P<wd2>{WD})\s*\)")
RE_WD_WORD = re.compile(rf"\b(?P<wd>{WD})")


def wd_index(name):
    return WD_NAMES[name[:3].lower()]


def parse_date(tok, shift, month_hint=None):
    """One date token to a date, or None. M/D without a year takes the shift's year (or the year
    before when that would land more than 120 days after the shift)."""
    tok = tok.strip()
    m = re.fullmatch(r"(20\d\d)-(\d\d)-(\d\d)", tok)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", tok)
    if m:
        mo, d, y = int(m.group(1)), int(m.group(2)), m.group(3)
        return _mk(mo, d, (int(y) + (2000 if len(y) == 2 else 0)) if y else None, shift)
    m = re.fullmatch(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(20\d\d))?", tok)
    if m and m.group(1).lower() in MONTHS:
        return _mk(MONTHS[m.group(1).lower()], int(m.group(2)), int(m.group(3)) if m.group(3) else None, shift)
    m = re.fullmatch(r"(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?", tok)
    if m:
        d = int(m.group(1))
        if month_hint:
            return _mk(month_hint[1], d, month_hint[0], shift)
        y, mo = shift.year, shift.month
        if d > shift.day:
            mo -= 1
            if mo == 0:
                y, mo = y - 1, 12
        return _mk(mo, d, y, shift)
    return None


def _mk(mo, d, y, shift):
    try:
        if y:
            return dt.date(y, mo, d)
        cand = dt.date(shift.year, mo, d)
        if cand > shift + dt.timedelta(days=120):
            cand = dt.date(shift.year - 1, mo, d)
        return cand
    except ValueError:
        return None


def has_explicit_year(tok):
    return bool(re.search(r"20\d\d", tok)) or bool(re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2,4}", tok.strip()))


def pd(d):
    return "%s %s" % (WD_FULL[d.weekday()], d.isoformat())


# ---------------------------------------------------------------- text helpers
RE_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\[(*`\"'$])")
RE_NUM = re.compile(r"(?<![\w.])[-+]?\$?\d[\d,]*(?:\.\d+)?%?(?![\w])")
RE_MASKS = [
    re.compile(r"\b\d{9,}\.\d+\b"),                                   # Slack ts
    re.compile(r"\b\d{7,}\b"),                                        # long ids
    re.compile(r"\b\d{3}-\d{3}-\d{4}\b"),                             # customer ids, phones
    re.compile(rf"{ISO}"),
    re.compile(rf"{MOND}(?:\s*{DASHES}\s*\d{{1,2}}\b)?"),
    re.compile(rf"{MD}(?:\s*-\s*\d{{1,2}}\b)?"),
    re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:[ap]\.?m\.?)?", re.I),
    re.compile(r"\b\d{1,2}\s*(?:am|pm)\b", re.I),
    re.compile(r"\b(?:19|20)\d\d\b"),                                 # years, model years
    re.compile(r"\b[ATRVS]\d{1,3}\b"),                                # ask, topic, ruling, vendor, settled ids
    re.compile(r"\b[A-Za-z]+\d+[A-Za-z\d]*\b"),                       # X5, iX3, ga4, 30d, T0456
    re.compile(r"\b[A-Za-z]+-\d+\b"),                                  # rung-1, Area-33
    re.compile(r"\b\d+-(?:day|week|month|night|hour|minute|year)s?\b", re.I),  # 7-day, 4-week
    re.compile(r"\b\d+[A-Za-z]+\d*\b"),                               # 7d, 28d, 3rd
    re.compile(r"\b\d+\s*(?:to\s*\d+\s*)?(?:hours?|hrs?|minutes?|mins?|days?|nights?|weeks?|months?|years?|"
               r"round trips?|shifts?|calls? (?:per|a) (?:night|shift)|units? cap)\b", re.I),
    re.compile(r"\b(?:top|headline|rung|step|section|rule|rules|page|round|position|pos\.?|row|rows|tier|area|"
               r"line|lines|v|#|no\.)\s*\d+(?:\s*(?:and|or|to|-)\s*\d+)?\b", re.I),
    re.compile(r"#\d+"),
]


def mask_numbers(text):
    for rx in RE_MASKS:
        text = rx.sub(" ", text)
    return text


def metric_numbers(text):
    return RE_NUM.findall(mask_numbers(text))


def sentences(line):
    out, pos = [], 0
    for m in RE_SENT.finditer(line):
        out.append((pos, line[pos:m.start()]))
        pos = m.end()
    out.append((pos, line[pos:]))
    return out


def stores_in(text):
    """[(pos, store)] for every store mention, in order."""
    hits = []
    for code, rx in STORE_RES:
        for m in rx.finditer(text):
            hits.append((m.start(), code))
    hits.sort()
    return hits


def store_before(text, pos, default=None):
    best = default
    for p, code in stores_in(text):
        if p <= pos:
            best = code
    return best


def norm_heading(h):
    return re.sub(r"[^a-z0-9]+", " ", h.lower()).strip()


# ---------------------------------------------------------------- the document
class Doc:
    def __init__(self, path, text):
        self.path = path
        self.raw = text.split("\n")
        # Obsidian %%comments%% (lint waivers) are hidden in the vault, so the rules never read them
        self.lines = [re.sub(r"%%.*?%%", lambda m: " " * len(m.group(0)), l) for l in self.raw]
        self.meta = []          # per line: {"h2", "store", "code", "fm"}
        self.h2 = []            # [(line_no, title)]
        h2, h3_store, code, fm = None, None, False, False
        for i, line in enumerate(self.lines):
            n = i + 1
            if i == 0 and line.strip() == "---":
                fm = True
                self.meta.append({"h2": None, "store": None, "code": False, "fm": True})
                continue
            if fm:
                if line.strip() == "---":
                    fm = False
                self.meta.append({"h2": None, "store": None, "code": False, "fm": True})
                continue
            if line.lstrip().startswith("```"):
                code = not code
                self.meta.append({"h2": h2, "store": h3_store, "code": True, "fm": False})
                continue
            if not code and re.match(r"^##\s+\S", line) and not line.startswith("###"):
                h2 = line.lstrip("#").strip()
                h3_store = None
                self.h2.append((n, h2))
            elif not code and re.match(r"^#\s+\S", line):
                h2, h3_store = None, None
            elif not code and line.startswith("###"):
                hits = stores_in(line)
                h3_store = hits[0][1] if len(set(c for _, c in hits)) == 1 else None
            line_store = h3_store
            lead = re.match(r"^\s*(?:[-*]|\d+\.)?\s*\*\*([^*]{1,60})\*\*", line)
            if lead:
                hits = stores_in(lead.group(1))
                if hits:
                    line_store = hits[0][1]
            self.meta.append({"h2": h2, "store": line_store, "code": code, "fm": False})

    def section_of(self, n):
        h = self.meta[n - 1]["h2"]
        return norm_heading(h) if h else ""

    def in_section(self, n, *names):
        sec = self.section_of(n)
        return any(sec.startswith(norm_heading(x)) for x in names)

    def section_lines(self, name):
        """[(line_no, text)] of the first ## section whose title starts with name."""
        key = norm_heading(name)
        out, inside = [], False
        for i, line in enumerate(self.lines):
            if self.meta[i]["fm"]:
                continue
            if re.match(r"^##\s+\S", line) and not line.startswith("###"):
                if inside:
                    break
                inside = norm_heading(line.lstrip("#").strip()).startswith(key)
                continue
            if re.match(r"^#\s+\S", line) and inside:
                break
            if inside:
                out.append((i + 1, line))
        return out

    def body(self):
        for i, line in enumerate(self.lines):
            if not self.meta[i]["fm"]:
                yield i + 1, line


# ---------------------------------------------------------------- context
class Ctx:
    def __init__(self, root, date, player, path, target=None):
        self.root = root
        self.date = date
        self.player = player
        self.path = path
        self.rel = os.path.relpath(path, root)
        self.shifts = os.path.join(root, "outputs", "ai-team")
        self.shift_dir = os.path.join(self.shifts, date.isoformat())
        self.data_dir = os.path.join(self.shift_dir, "data")
        self.target = target or (date - dt.timedelta(days=1))
        self.warnings = []
        self.notes = []
        self._index = None
        self._text_cache = None
        self.waived = []

    def warn(self, n, rule, msg, fix):
        self.warnings.append({"file": self.rel, "line": n, "rule": rule, "msg": msg, "fix": fix})

    def note(self, msg):
        self.notes.append(msg)

    # data/ index: file name -> [paths] under tonight's data (all depths)
    def data_index(self):
        if self._index is None:
            self._index = {}
            for base, _dirs, files in os.walk(self.data_dir):
                for f in files:
                    self._index.setdefault(f, []).append(os.path.join(base, f))
        return self._index

    def data_texts(self):
        """Text of small .md/.txt/.json files in tonight's data/ (for 'is this URL saved')."""
        if self._text_cache is None:
            parts = []
            for name, paths in self.data_index().items():
                if not name.endswith((".md", ".txt", ".json", ".csv", ".html")):
                    continue
                if name.startswith("lint"):
                    continue      # our own --out report quotes Sources lines; it is not a saved copy of them
                for p in paths:
                    try:
                        if os.path.getsize(p) <= 3000000:
                            with open(p, encoding="utf-8", errors="replace") as fh:
                                parts.append(name + "\n" + fh.read())
                    except OSError:
                        pass
            self._text_cache = "\n".join(parts).lower()
        return self._text_cache

    def load_json(self, *parts):
        p = os.path.join(self.root, *parts)
        if not os.path.exists(p):
            return None
        try:
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError) as e:
            self.note("could not read %s: %s" % (os.path.relpath(p, self.root), e))
            return None


# ---------------------------------------------------------------- rules
def rule_headings(doc, ctx):
    req = required_headings(ctx)
    present = [(n, norm_heading(t)) for n, t in doc.h2]
    found = {}
    for name in req:
        key = norm_heading(name)
        for n, t in present:
            if t.startswith(key):
                found[name] = n
                break
        else:
            why = ("ad_text_check.py wrote data/ad_text_*.json tonight" if name == "Ad text" and ctx.player == "shaq"
                   else "required by .claude/agents/%s.md Output" % ctx.player)
            ctx.warn(1, "heading-missing", "no '## %s' section (%s)" % (name, why),
                     "add it; if there is nothing tonight, write one line saying so and why")
    for name, n in found.items():
        body = [l for _, l in doc.section_lines(name) if l.strip() and not l.strip().startswith("<!--")]
        if not body:
            ctx.warn(n, "heading-empty", "'## %s' has nothing under it" % name,
                     "fill it, or write one line saying there is nothing tonight and why")
    rtm = found.get("Report to Magic")
    if rtm:
        after = [name for name, n in found.items() if n > rtm and name not in ("Sources", "Report to Magic")]
        if after:
            ctx.warn(rtm, "heading-order", "Report to Magic must be the last section before Sources; after it: %s" %
                     ", ".join(after), "move Report to Magic down, directly above Sources")
        src = found.get("Sources")
        if src and src < rtm:
            ctx.warn(src, "heading-order", "Sources sits above Report to Magic", "Sources is the last section")


def required_headings(ctx):
    path = os.path.join(ctx.root, ".claude", "agents", ctx.player + ".md")
    req = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        m = re.search(r"^## Output\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
        if m:
            for line in m.group(1).splitlines():
                b = re.match(r"^\s*-\s*`##\s+([^`]+)`(.*)$", line)
                if not b:
                    continue
                name, rest = b.group(1).strip(), b.group(2).lower()
                if "first monday of the month" in rest and not (ctx.date.weekday() == 0 and ctx.date.day <= 7):
                    continue
                if re.search(r"\(monday\)", rest) and ctx.date.weekday() != 0:
                    continue
                req.append(name)
    if not req:
        ctx.note("no Output section read from .claude/agents/%s.md; using the built-in heading list" % ctx.player)
        req = list(FALLBACK_HEADINGS.get(ctx.player, []))
    if ctx.player == "shaq" and "Ad text" not in req and glob.glob(os.path.join(ctx.data_dir, "ad_text_*.json")):
        req.insert(1, "Ad text")
    return req


RE_PLACEHOLDERS = [
    (re.compile(r"\[(?:PENDING|TBD|TODO|TK|FIXME|FILL[^\]]*|INSERT[^\]]*|X{2,}|\?+)\]", re.I), "bracketed placeholder"),
    (re.compile(r"\b(?:TODO|TBD|FIXME|PENDING|TKTK)\b"), "placeholder word"),
    (re.compile(r"(?<![A-Za-z0-9])\$?X{2,}(?:[.,]X+)*%?(?![A-Za-z0-9])"), "XX placeholder"),
    (re.compile(r"\?\?+"), "?? placeholder"),
    (re.compile(r"lorem ipsum", re.I), "filler text"),
]
RE_CURLY = re.compile(r"\{[A-Za-z_][A-Za-z0-9_ .-]*\}")


def rule_placeholders(doc, ctx):
    for n, line in doc.body():
        if doc.meta[n - 1]["code"]:
            continue
        hits, taken = [], []
        for rx, label in RE_PLACEHOLDERS:
            for m in rx.finditer(line):
                if any(a <= m.start() < b for a, b in taken):
                    continue      # PENDING inside [PENDING] is one miss, not two
                taken.append(m.span())
                hits.append((m.group(0), label))
        spans = [m.span() for m in re.finditer(r"`[^`]*`", line)]
        for m in RE_CURLY.finditer(line):
            s, e = m.span()
            if any(a <= s and e <= b for a, b in spans):
                continue
            before = line[s - 1] if s > 0 else " "
            after = line[e] if e < len(line) else " "
            if re.match(r"[\w/.\-*]", before) or re.match(r"[\w/.\-*]", after):
                continue      # a path shorthand like ga4_{STORE}.json
            hits.append((m.group(0), "curly placeholder"))
        for tok, label in hits:
            ctx.warn(n, "placeholder", "%s left in: %s" % (label, tok),
                     "replace it with the real value, or say plainly what is missing and why")


def rule_em_dash(doc, ctx):
    for i, line in enumerate(doc.raw):
        if EM_DASH in line:
            ctx.warn(i + 1, "em-dash", "em dash at column %d" % (line.index(EM_DASH) + 1),
                     "rewrite with a comma, colon, period or parentheses (never an em dash)")


def rule_weekdays(doc, ctx):
    shift = ctx.date
    for n, line in doc.body():
        taken = []

        def free(s, e):
            return not any(a < e and s < b for a, b in taken)

        for rx in (RE_WD_RANGE, RE_DT_RANGE_WD):
            for m in rx.finditer(line):
                d1 = parse_date(m.group("d1"), shift)
                if not d1:
                    continue
                d2tok = m.group("d2")
                if re.fullmatch(r"\d{1,2}", d2tok):
                    d2 = parse_date(d2tok, shift, month_hint=(d1.year, d1.month))
                else:
                    d2 = parse_date(d2tok, shift)
                taken.append(m.span())
                bad = []
                if d1 and wd_index(m.group("wd1")) != d1.weekday():
                    bad.append("%s is %s" % (d1.strftime("%-m/%-d"), WD_FULL[d1.weekday()]))
                if d2 and wd_index(m.group("wd2")) != d2.weekday():
                    bad.append("%s is %s" % (d2.strftime("%-m/%-d"), WD_FULL[d2.weekday()]))
                if bad:
                    ctx.warn(n, "weekday-mismatch", "'%s': %s" % (m.group(0).strip(), "; ".join(bad)),
                             "fix the weekday or the date against the calendar (tonight, %s, is a %s)" %
                             (shift.isoformat(), WD_FULL[shift.weekday()]))
        for rx in (RE_WD_SINGLE, RE_DT_WD):
            for m in rx.finditer(line):
                if not free(*m.span()):
                    continue
                d = parse_date(m.group("dt"), shift)
                if not d:
                    continue
                taken.append(m.span())
                if wd_index(m.group("wd")) != d.weekday():
                    ctx.warn(n, "weekday-mismatch", "'%s' but %s is a %s" % (m.group(0).strip(), d.isoformat(),
                                                                            WD_FULL[d.weekday()]),
                             "fix the weekday or the date against the calendar (tonight, %s, is a %s)" %
                             (shift.isoformat(), WD_FULL[shift.weekday()]))


FUTURE_OK = re.compile(r"\b(?:before|by|until|till|effective|from|starting|starts?|due|deadline|expir\w*|takes? effect|"
                       r"next|scheduled|will|on[- ]sale|launch\w*|arriv\w*|coming|goes live|kicks? in|plan\w*|"
                       r"park\w*|reopen\w*|after|in effect|ahead of|through|thru|window|ends?|closes?|upcoming|"
                       r"expected|estimated|slated|set for|targeted|eta|valid|offer|expires?|runs?|renew\w*|"
                       r"cars act|sb ?766|law|remind\w*|check again|follow[- ]up|revisit|pace|exhaust\w*|around|project\w*|"
                       r"forecast\w*|expect\w*|would|should|could|likely|estimat\w*|tomorrow|later|this week|"
                       r"next week|at (?:the )?(?:store|mcpeek)|visit\w*|meeting|call with)\b", re.I)
FUTURE_POST = re.compile(r"\W{0,3}(?:deadline|onwards?|forward|and after|and beyond|go-live|cutoff|launch|"
                         r"on-sale|effective|start)", re.I)
OLD_OK = re.compile(r"\b(?:since|first|dated|published|release[sd]?|posted|ended|began|begun|started|launch\w*|"
                    r"preview\w*|seeded|originally|history|historical|baseline|prior[- ]year|last year|year[- ]ago|"
                    r"year[- ]over[- ]year|yoy|"
                    r"entry|drafted|flights?|model year|back to|dateline|press|announce\w*|newsroom|article|"
                    r"reported|trade|source[sd]?|filed|decision|decided|built|created|opened|installed|as far back|"
                    r"hasn'?t|has not|not since|last (?:seen|updated|changed|ran|run|fired|active|used|spent|touched)|fired|"
                    r"stale|old|as of)\b", re.I)


def rule_date_window(doc, ctx):
    shift = ctx.date
    for n, line in doc.body():
        if doc.meta[n - 1]["code"]:
            continue
        ref_section = doc.in_section(n, *REFERENCE_SECTIONS)
        for s0, sent in sentences(line):
            named = [q.span() for q in re.finditer(r"[\"\u201c][^\"\u201d]*[\"\u201d]|\[[^\]]*\]", sent)]
            for m in RE_DATE_ANY.finditer(sent):
                if any(a <= m.start() < b for a, b in named):
                    continue      # a date inside a quoted or bracketed name ("[6/13/2026] Promoting ...")
                tok = m.group("tok")
                d = parse_date(tok, shift)
                if not d:
                    continue
                pre = sent[max(0, m.start() - 70):m.start()]
                if d > shift:
                    if FUTURE_OK.search(pre) or FUTURE_POST.match(sent[m.end():m.end() + 30]):
                        continue
                    ctx.warn(n, "date-future", "%s is after tonight's shift date %s" % (tok, shift.isoformat()),
                             "check the year and month; a deadline reads 'before/by %s'" % tok)
                elif (shift - d).days > OLD_DAYS and has_explicit_year(tok) and not ref_section:
                    if OLD_OK.search(sent):
                        continue
                    ctx.warn(n, "date-old", "%s is %d days before the shift; is that the right year, and is the "
                             "number still current?" % (tok, (shift - d).days),
                             "fix the year, or say it is old ('as of %s') and why it still matters" % tok)


PRELIM = re.compile(r"prelim|partial|incomplete|not final|not yet final|still (?:filling|coming in|landing|settling|"
                    r"processing|restating)|fill(?:s|ing|ed)? in|restat|backfill|early read|\b1 ?am\b|provisional|"
                    r"in progress|\blag\b|\blagg(?:ed|ing)\b|may (?:rise|change|move|restate|fill|climb)|will (?:rise|change|move|"
                    r"restate|fill|climb)|finali[sz]|not settled|open day|half[- ]day|still open for", re.I)
GA4_CONTEXT = re.compile(r"\bGA4\b|key[- ]events?|sessions?", re.I)
# Ads and Meta spend, clicks and impressions are close to final at 1 AM; conversions and results keep
# backfilling (MCP PMax 9/23 went 0 to 5 between exports), so only those need the preliminary label.
LAGGING = re.compile(r"conv|results?\b|\bleads?\b|\bCPA\b|cost per|ROAS|purchases?|key[- ]events?|form (?:fills?|submits?)",
                     re.I)
RE_ZERO = re.compile(r"\b(?:zero|no) (?:sessions?|key events?|conversions?|leads?|clicks?|results?|visits?)\b", re.I)


def target_spans(sent, tgt, shift, wd_full):
    """Character spans in the sentence that name the target day as a single day."""
    out = []
    for m in RE_DATE_ANY.finditer(sent):
        d = parse_date(m.group("tok"), shift)
        if d != tgt:
            continue
        pre = sent[max(0, m.start() - 26):m.start()]
        if re.search(rf"(?:{DASHES}|MTD|month to date|through)\s*(?:{WD},?\s*)?\(?\s*$", pre, re.I):
            continue       # end of a range: a multi-day window, not the one day
        out.append(m.span())
    for m in RE_WD_WORD.finditer(sent):
        if wd_index(m.group("wd")) != tgt.weekday():
            continue
        pre = sent[max(0, m.start() - 12):m.start()]
        post = sent[m.end():m.end() + 24]
        if re.search(rf"{DASHES}\s*$", pre) or re.match(rf"\s*{DASHES}", post):
            continue       # part of a weekday range
        if re.match(rf"\s+\d{{1,2}}\s*{DASHES}\s*\d{{1,2}}\b", post):
            continue       # "Sun 21-27": a date range, not the one day
        if re.match(r"(?:'s)?,?\s+(?:the\s+)?\(?\s*(?:%s|%s|%s|%s)" % (ISO, MD, MOND, ORD), post):
            continue       # a dated weekday is judged by its date
        if re.search(r"\b(?:last|previous|prior|each|every)\s+$", pre, re.I):
            continue       # "last Sunday", "every Sunday" ("a normal Sunday" still compares the newest day)
        if re.search(r"'s\s+$", pre) or re.match(r"(?:'s)?\s+(?:GA4\s+|nightly\s+|\d+-day\s+|last-?7\s+)?(?:flag|pull|"
                                                   r"file|shift|brief|export|run|report|post|huddle|note|read|"
                                                   r"window)\b", post, re.I):
            continue       # "Kobe's Monday flag", "Monday's pull": the pull, not the day's numbers
        out.append(m.span())
    for m in re.finditer(r"\byesterday\b", sent, re.I):
        out.append(m.span())
    return out


def prelim_declared(doc, ctx):
    """A line anywhere (outside Sources) that names the target day and calls it preliminary."""
    wd_full = WD_FULL[ctx.target.weekday()]
    for n, line in doc.body():
        if doc.in_section(n, "sources"):
            continue
        if PRELIM.search(line) and (target_spans(line, ctx.target, ctx.date, wd_full) or
                                    re.search(r"newest day|latest day|last day", line, re.I)):
            return True
    return False


def rule_prelim(doc, ctx):
    """Headlines and Report to Magic lines (they get copied into the brief) need 'preliminary' on every
    claim about the newest day. The body is covered by one line saying the newest day is preliminary;
    without it, one warning lists the body lines."""
    if ctx.target != ctx.date - dt.timedelta(days=1):
        ctx.note("target date %s is not yesterday; prelim-missing skipped" % ctx.target.isoformat())
        return
    tgt = ctx.target
    wd_full = WD_FULL[tgt.weekday()]
    declared = prelim_declared(doc, ctx)
    body = []
    for n, line in doc.body():
        if doc.meta[n - 1]["code"] or line.lstrip().startswith("#"):
            continue
        if doc.in_section(n, "sources", "data gaps", "report freshness", "measurement health", "source mapping",
                          "radar", "topic proposals", "content"):
            continue
        brief_facing = doc.in_section(n, "headlines", "report to magic")
        if declared and not brief_facing:
            continue
        if ctx.player == "nick" and not GA4_CONTEXT.search(line):
            continue
        hit = False
        sents = sentences(line)
        for i, (s0, sent) in enumerate(sents):
            spans = target_spans(sent, tgt, ctx.date, wd_full)
            nxt = sents[i + 1][1] if i + 1 < len(sents) else ""
            if not spans or PRELIM.search(sent) or PRELIM.search(nxt[:160]):
                continue
            for a, b in spans:
                win = sent[max(0, a - 80):b + 80]
                if not (metric_numbers(win) or RE_ZERO.search(win)):
                    continue
                if ctx.player in ("shaq", "luka") and not LAGGING.search(win):
                    continue
                if ctx.player == "worthy" and not GA4_CONTEXT.search(win):
                    continue      # a Semrush snapshot date is not a GA4 day
                hit = True
                break
            if hit:
                break
        if not hit:
            continue
        if brief_facing:
            ctx.warn(n, "prelim-missing", "%s line gives numbers for %s (the newest day, incomplete at 1 AM) "
                     "without 'preliminary'" % (doc.meta[n - 1]["h2"], pd(tgt)),
                     "say 'preliminary' on this line and lean on the last complete day; data/deltas.md shows how "
                     "much yesterday restated")
        else:
            body.append(n)
    if body:
        more = " (also lines %s)" % ", ".join(str(x) for x in body[1:10]) if len(body) > 1 else ""
        ctx.warn(body[0], "prelim-missing", "numbers for %s (the newest day, incomplete at 1 AM) and nowhere does "
                 "the file say it is preliminary%s" % (pd(tgt), more),
                 "add one line under the title: '%s numbers are preliminary (GA4 fills in for 24 to 48 hours, Ads "
                 "conversions backfill)', and check data/deltas.md before calling a drop" % pd(tgt))


ACK = re.compile(r"\bR\d+\b|\bS\d+\b|ruling|ruled|per drew|drew(?:'s)? (?:call|rule|ruling|said|told|answer\w*|"
                 r"decided|decision)|ignor\w*|exclud\w*|not (?:ours|raising|re-?rais\w*|counted)|settled|"
                 r"already (?:answered|closed|known|decided)|carry-?over|carried|standing|no change|unchanged|"
                 r"withdrawn|inactive|off the table|known|as before|same as (?:last|friday|thursday|before)|dead[- ]vendor|"
                 r"live[- ]vendor|not live|not active", re.I)
REOPEN = re.compile(r"reopen|re-open|changed|new (?:tonight|since)|first time|moved|no longer|now (?:shows|reads|is)|"
                    r"broke|came back|returned", re.I)
STOP_KW = set("""drew digitalcliq until ignore ignored the not do does and for with from this that their they them
its it's is are was were be been being have has had will would should could any all our ours us we you your
next month moving forward just raise again page cost costs source sources store stores active updated correctly
while stale october november december september january february march april may june july august monday
tuesday wednesday thursday friday saturday sunday meta's""".split())


def derive_keywords(text):
    """Distinctive capitalized names in a ruling (vendors, products), minus store names and filler."""
    kws = []
    for m in re.finditer(r"[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*", text):
        phrase = m.group(0)
        if stores_in(phrase):
            continue
        words = [w for w in phrase.split() if w.lower() not in STOP_KW]
        if not words:
            continue
        kw = " ".join(words)
        if len(kw) >= 3 and kw not in kws:
            kws.append(kw)
    return kws


def _kw_norm(text):
    return re.sub(r"[\s_\-]+", " ", text.lower())


def kw_hits(kws, text):
    """Keywords found in the text; spaces, hyphens and underscores are interchangeable (branch_locator
    matches branch-locator)."""
    low = _kw_norm(text)
    return [k for k in kws if re.search(r"(?<![a-z0-9])" + re.escape(_kw_norm(k)) + r"(?![a-z0-9])", low)]


def non_store_kws(kws):
    return [k for k in kws if not (stores_in(k) and len(k.split()) <= 2)]


def lane_ok(lane, player):
    if lane is None:
        return True
    if isinstance(lane, str):
        lane = [x.strip() for x in re.split(r"[,\s]+", lane) if x.strip()]
    lane = [x.lower() for x in lane]
    return not lane or "all" in lane or player in lane


def line_stores(doc, n, line):
    s = {c for _, c in stores_in(line)}
    if not s and doc.meta[n - 1]["store"]:
        s = {doc.meta[n - 1]["store"]}
    return s


def shift_start_epoch(date):
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/Los_Angeles")
    except Exception:  # pragma: no cover
        tz = None
    start = dt.datetime(date.year, date.month, date.day, 1, 0, tzinfo=tz)
    return start.timestamp()


def active_rulings(ctx):
    data = ctx.load_json("outputs", "ai-team", "ledgers", "rulings.json")
    if data is None:
        ctx.note("no outputs/ai-team/ledgers/rulings.json; ruling-repeat skipped")
        return []
    out = []
    for r in data.get("rulings", []) if isinstance(data, dict) else data:
        try:
            rd = dt.date.fromisoformat(str(r.get("date") or r.get("added"))[:10])
        except ValueError:
            continue
        if rd > ctx.date:
            continue
        if rd == ctx.date:
            ts = r.get("slack_ts")
            try:
                if not ts or float(ts) >= shift_start_epoch(ctx.date):
                    continue      # ruled after tonight's 1 AM start: the team could not know
            except ValueError:
                continue
        exp = r.get("expires")
        if exp:
            try:
                if ctx.date >= dt.date.fromisoformat(str(exp)[:10]):
                    continue
            except ValueError:
                pass
        if not lane_ok(r.get("lane"), ctx.player):
            continue
        kws = non_store_kws(r.get("keywords") or derive_keywords(r.get("ruling", "")))
        out.append({"id": r.get("id", "R?"), "store": (r.get("store") or "").upper(), "kws": kws,
                    "asks": r.get("applies_to_asks") or [], "text": r.get("ruling", "")})
    return out


def settled_items(ctx):
    data = ctx.load_json("outputs", "ai-team", "ledgers", "settled.json")
    if data is None:
        ctx.note("no outputs/ai-team/ledgers/settled.json yet; settled-repeat skipped")
        return []
    items = data.get("settled", []) if isinstance(data, dict) else data
    out = []
    for s in items:
        if str(s.get("status", "settled")).lower() in ("reopened", "open", "retired"):
            continue
        on = s.get("settled_on")
        try:
            if on and dt.date.fromisoformat(str(on)[:10]) >= ctx.date:
                continue
        except ValueError:
            pass
        if not lane_ok(s.get("lane"), ctx.player):
            continue
        kws = non_store_kws(s.get("keywords") or derive_keywords(s.get("subject", "")))
        if not kws:
            continue
        out.append({"id": s.get("id", "S?"), "store": (s.get("store") or "").upper(), "kws": kws,
                    "subject": s.get("subject", ""), "reopen_if": s.get("reopen_if", "")})
    return out


def rule_rulings_settled(doc, ctx):
    rulings = active_rulings(ctx)
    settled = settled_items(ctx)
    if not rulings and not settled:
        return
    body_hits = {}
    for n, line in doc.body():
        if doc.meta[n - 1]["code"] or doc.in_section(n, "sources") or not line.strip():
            continue
        if doc.in_section(n, "report freshness", "measurement health", "data gaps"):
            continue      # the tables and gap lists name every store every night by design
        stores = line_stores(doc, n, line)
        for r in rulings:
            if r["store"] and r["store"] not in ("ALL", "") and stores and r["store"] not in stores:
                continue
            ask_hit = [a for a in r["asks"] if re.search(r"\b%s\b" % re.escape(a), line)]
            hits = kw_hits(r["kws"], line)
            need = min(2, len(r["kws"])) if r["kws"] else 99
            if not ask_hit and len(hits) < need:
                continue
            if r["store"] not in ("ALL", "") and not stores:
                continue
            if ACK.search(line):
                continue
            what = ", ".join(ask_hit + hits)
            ctx.warn(n, "ruling-repeat", "Drew's ruling %s already covers this (%s): %s" % (r["id"], what,
                                                                                           r["text"][:110]),
                     "drop it, or cite '%s' and say what is new that the ruling does not cover" % r["id"])
        for s in settled:
            if s["store"] not in ("ALL", "") and (not stores or s["store"] not in stores):
                continue
            hits = kw_hits(s["kws"], line)
            if len(hits) < min(2, len(s["kws"])):
                continue
            if doc.in_section(n, "headlines", "report to magic"):
                if not REOPEN.search(line):
                    ctx.warn(n, "settled-repeat", "settled item %s (%s) in %s with nothing changed" %
                             (s["id"], s["subject"][:70], doc.meta[n - 1]["h2"]),
                             "take it out of %s; log a one-line 'settled check %s: no change' in By store, or say "
                             "what changed (reopen if: %s)" % (doc.meta[n - 1]["h2"], s["id"],
                                                               (s["reopen_if"] or "see settled.json")[:90]))
            elif not ACK.search(line) and not REOPEN.search(line):
                body_hits.setdefault(s["id"], (s, []))[1].append(n)
    for sid, (s, lines_) in body_hits.items():
        more = " (also lines %s)" % ", ".join(str(x) for x in lines_[1:8]) if len(lines_) > 1 else ""
        ctx.warn(lines_[0], "settled-repeat", "reads as new, but settled item %s covers it (%s)%s" %
                 (sid, s["subject"][:70], more),
                 "write it once as 'settled check %s: no change' (cite the id), or say what changed" % sid)


RED_CAVEAT = re.compile(r"\bRED\b|inflat|unreliab|not reliable|isn'?t reliable|can'?t be (?:used|trusted|quoted)|"
                        r"cannot be (?:used|trusted|quoted)|broken|\bbreak\b|collaps|junk|page[- ]?views?|"
                        r"page[- ]visit|not (?:a )?(?:real )?leads?\b|not real|do(?:n'?t| not) (?:quote|use|read|trust)|"
                        r"not usable|unusable|health board|tracking (?:issue|problem|break|gap)|double[- ]?(?:fir|count)|"
                        r"measurement (?:issue|problem)|on (?:page )?load|lead[- ]on[- ]load|blocked|not evidence|"
                        r"can'?t tell|\bclean\b|mislabel|misconfig|\bsoft\b|directions|store visits|secondary|"
                        r"not a lead|wrong tonight|bogus|garbage|noise|overcount|undercount|over-count|under-count|known (?:issue|case|"
                        r"break|problem)|open case|can'?t be read|unreadable|not trustworthy", re.I)


def red_blocks(ctx):
    h = ctx.load_json("outputs", "ai-team", ctx.date.isoformat(), "data", "health.json")
    if h is None:
        ctx.note("no data/health.json tonight; red-number skipped")
        return {}
    out = {}
    for store, s in (h.get("stores") or {}).items():
        if str(s.get("color", "")).lower() != "red":
            continue
        blocks, clean = [], []
        for i in s.get("issues", []):
            if str(i.get("severity", "")).lower() == "red":
                blocks += i.get("blocks") or []
            q = re.search(r"quote only (.*?)(?:,? deduped|\. |$)", i.get("tech", "") or "")
            if q:
                clean += re.findall(r"[a-z][a-z_]+[a-z]", q.group(1))
        blocks += s.get("blocked_tonight") or []
        if blocks:
            out[store.upper()] = {"blocks": sorted(set(blocks)), "clean": sorted(set(clean))}
    return out


def block_regex(block, player):
    b = block.lower()
    if "key event" in b or ("ga4" in b and "conversion" in b):
        if player in ("kobe", "worthy"):
            return re.compile(r"key[- ]?events?|keyEvents|\bconversions?\b|conv\. rate", re.I), "GA4"
        return re.compile(r"key[- ]?events?|keyEvents|GA4 conversions?", re.I), "GA4"
    if "ads conversion" in b or ("google ads" in b and "conversion" in b):
        if player == "shaq":
            return re.compile(r"\bconversions?\b|\bconv\b|\bCPA\b|cost per conversion", re.I), "Ads"
        return re.compile(r"(?:Google )?Ads conversions?|\bconversions? in (?:Google )?Ads", re.I), "Ads"
    words = [w for w in re.findall(r"[a-z]{4,}", b) if w not in ("numbers", "google")]
    if not words:
        return None, None
    return re.compile("|".join(re.escape(w) for w in words), re.I), block


def subject_store(doc, n, line, sent, s0, pos):
    """The store a metric belongs to: the nearest store named before it in its sentence, else the
    section's store (### heading or bold lead), else the first store the line names."""
    st = store_before(sent, pos, None)
    if st:
        return st
    if doc.meta[n - 1]["store"]:
        return doc.meta[n - 1]["store"]
    hits = stores_in(line)
    return hits[0][1] if hits else None


def rule_red_numbers(doc, ctx):
    reds = red_blocks(ctx)
    if not reds:
        return
    for n, line in doc.body():
        if doc.meta[n - 1]["code"] or line.lstrip().startswith("#"):
            continue
        if doc.in_section(n, "sources", "data gaps", "measurement health"):
            continue
        if RED_CAVEAT.search(line):
            continue      # the line already says the number is broken
        flagged = set()
        for s0, sent in sentences(line):
            for store, info in reds.items():
                if store in flagged or any(c in line for c in info["clean"]):
                    continue
                for block in info["blocks"]:
                    rx, _label = block_regex(block, ctx.player)
                    if rx is None or store in flagged:
                        continue
                    for m in rx.finditer(sent):
                        if subject_store(doc, n, line, sent, s0, m.start()) != store:
                            continue
                        win = sent[max(0, m.start() - 35):m.end() + 25]
                        if not metric_numbers(win):
                            continue
                        ctx.warn(n, "red-number", "%s is RED tonight and health.json blocks '%s', but this line "
                                 "uses a number for it as evidence" % (store, block),
                                 "drop the number, or quote only the clean subset health.md names and say the "
                                 "total is wrong (RED)")
                        flagged.add(store)
                        break


RE_ASK_ID = re.compile(r"(?<![\w-])A(\d{1,3})(?![\w-])")
SETTLED_WORD = re.compile(r"\b(?:settled|settles|settle|closed|closes|close[sd]? out|resolved|resolves|withdrawn|"
                          r"no longer open|done)\b", re.I)
OPEN_WORD = re.compile(r"\b(?:still open|remains open|stays open|open ask|keep(?:s|ing)? it open|confirmed, still open)\b",
                       re.I)
NEGATION = re.compile(r"(?:not|n't|never|un|isn't|aren't|wasn't|keep|use)\s*(?:yet\s+)?['\"]?$", re.I)


def ask_states(ctx):
    data = ctx.load_json("outputs", "ai-team", "ledgers", "asks.json")
    if data is None:
        ctx.note("no outputs/ai-team/ledgers/asks.json; ask-status skipped")
        return None
    asks = data.get("asks", []) if isinstance(data, dict) else data
    out = {}
    for a in asks:
        aid = a.get("id")
        if not aid:
            continue
        st = str(a.get("status", "open")).lower()
        closed = a.get("closed_date")
        first = a.get("first_raised")
        try:
            closed_d = dt.date.fromisoformat(str(closed)[:10]) if closed else None
        except ValueError:
            closed_d = None
        try:
            first_d = dt.date.fromisoformat(str(first)[:10]) if first else None
        except ValueError:
            first_d = None
        if st in ("closed", "withdrawn") and closed_d and closed_d > ctx.date:
            st_then = "open"      # settled after tonight's shift: open when the player wrote
        elif st in ("closed", "withdrawn") and closed_d == ctx.date:
            st_then = "same-day"  # settled on the shift date: could be before or after the file; no warning
        else:
            st_then = st
        out[aid] = {"status": st_then, "now": st, "closed": closed_d, "first": first_d}
    return out


def rule_ask_status(doc, ctx):
    states = ask_states(ctx)
    if states is None:
        return
    for n, line in doc.body():
        if doc.meta[n - 1]["code"] or doc.in_section(n, "sources"):
            continue
        for s0, sent in sentences(line):
            for m in RE_ASK_ID.finditer(sent):
                aid = "A" + m.group(1)
                st = states.get(aid)
                if st is None:
                    ctx.warn(n, "ask-status", "%s is not in asks.json" % aid,
                             "check the id with 'ledgers.py asks list'; a new ask gets its id from Magic")
                    continue
                win_s, win_e = max(0, m.start() - 70), min(len(sent), m.end() + 70)
                win = sent[win_s:win_e]
                if st["status"] in ("open", "parked"):
                    for w in SETTLED_WORD.finditer(win):
                        pre = win[max(0, w.start() - 14):w.start()]
                        if NEGATION.search(pre) or re.search(r"half|part", win[w.start():w.end() + 20], re.I):
                            if re.search(r"half|part", win[w.start():w.end() + 20], re.I):
                                ctx.warn(n, "ask-status", "'%s' on %s, which asks.json still shows open" %
                                         (w.group(0), aid), "say 'confirmed, still open' (or what narrowed); "
                                         "only Drew's answer or the data Magic records closes an ask")
                                break
                            continue
                        ctx.warn(n, "ask-status", "'%s' on %s, which asks.json still shows %s" %
                                 (w.group(0), aid, st["status"]),
                                 "say 'confirmed, still open' (or what changed); 'settled' is only for asks "
                                 "Drew closed")
                        break
                elif st["status"] in ("closed", "withdrawn"):
                    if OPEN_WORD.search(win):
                        ctx.warn(n, "ask-status", "%s reads as open, but asks.json shows it %s on %s" %
                                 (aid, st["status"], st["closed"] or "an earlier date"),
                                 "drop it, or say it is %s and what changed if you are reopening it" % st["status"])


RE_PATH_DATED = re.compile(r"(?<![\w/])((?:outputs/ai-team/)?(\d{4}-\d{2}-\d{2})/data(?:/(?:[\w.\-*]|\{[^}\s]*\})+)*/?)")
RE_PATH_REL = re.compile(r"(?<![\w/.\-])(data(?:/(?:[\w.\-*]|\{[^}\s]*\})+)+)")
RE_PATH_VAULT = re.compile(r"(?<![\w/.\-])((?:outputs|Projects|Intelligence|Resources|Context|Daily|Skills|Team|"
                           r"Departments|\.claude)/(?:[\w.\-*/]|\{[^}\s]*\})*?(?:[\w\-*]|\{[^}\s]*\})\.\w{2,5})(?![\w/])")
# a file named on a line that says it is missing or not wanted is not a citation
PATH_NEG = re.compile(r"(?:not (?:yet )?(?:authori[sz]ed|connected|available|pulled|saved|run|there)|missing|"
                      r"no (?:fresh |such )?(?:file|data)|don'?t have|do not have|without|never (?:ran|pulled|saved)|"
                      r"until|once|will (?:appear|land|be)|isn'?t there|does not exist|doesn'?t exist|no fresh)", re.I)
CARRY = re.compile(r"last night|prior[- ](?:night|shift)|previous (?:night|shift)|yesterday'?s|carried|carry|"
                   r"fallback|fall back|fell back|reused|re-used|\d+-day-old|older|earlier|friday'?s|thursday'?s|"
                   r"from (?:the )?\d\d-\d\d", re.I)
RE_BARE = re.compile(r"(?<![\w/.\-{])(" + DATA_PREFIX + r"(?:[\w.\-*]|\{[^}\s]*\})*\.(?:json|md|csv|txt|jsonl))\b")
RE_WIKI = re.compile(r"\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]")


def expand(token, stores):
    m = re.search(r"\{([^{}]*)\}", token)
    if not m:
        return [token]
    inner = m.group(1)
    if "," in inner:
        opts = [o.strip() for o in inner.split(",")]
    elif inner.strip().upper() in ("STORE", "STORES"):
        opts = list(stores)
    else:
        opts = ["*"]
    out = []
    for o in opts:
        out += expand(token[:m.start()] + o + token[m.end():], stores)
    return out


def exists(path):
    if "*" in path:
        return bool(glob.glob(path, recursive=True))
    return os.path.exists(path)


def clean_tok(t):
    return t.rstrip(".,:;)`'\"")


def prior_data_dirs(ctx, days=7):
    out = []
    for d in range(1, days + 1):
        p = os.path.join(ctx.shifts, (ctx.date - dt.timedelta(days=d)).isoformat(), "data")
        if os.path.isdir(p):
            out.append(p)
    return out


def negated(line, s, e):
    """True when the words around a file name say it is missing or not wanted (not a citation)."""
    return bool(PATH_NEG.search(line[max(0, s - 40):s]) or PATH_NEG.search(line[e:e + 45]))


def cited_files(doc, ctx, n, line):
    """[(token, [missing concrete paths], found_any)] for every file citation on the line. A missing path
    that exists in an earlier night's data/ is reported with that path and a note to cite it dated."""
    out = []
    stores = PLAYER_STORES.get(ctx.player, ALL_STORES)
    spans = []
    last_dir = None

    def add(tok, paths, m):
        miss = [p for p in paths if not exists(p)]
        if miss and negated(line, *m.span()):
            return
        out.append((tok, miss, len(miss) < len(paths)))

    for m in RE_PATH_DATED.finditer(line):
        tok = clean_tok(m.group(1))
        spans.append(m.span())
        rel = tok if tok.startswith("outputs/") else "outputs/ai-team/" + tok
        add(tok, [os.path.join(ctx.root, p) for p in expand(rel, stores)], m)
        last_dir = os.path.dirname(os.path.join(ctx.root, rel)) if "." in os.path.basename(rel) else \
            os.path.join(ctx.root, rel)
    for m in RE_PATH_REL.finditer(line):
        if any(a <= m.start() < b for a, b in spans):
            continue
        tok = clean_tok(m.group(1))
        spans.append(m.span())
        paths = [os.path.join(ctx.shift_dir, p) for p in expand(tok, stores)]
        add(tok, paths, m)
        last_dir = os.path.dirname(paths[0]) if paths else last_dir
    for m in RE_PATH_VAULT.finditer(line):
        if any(a <= m.start() < b for a, b in spans):
            continue
        tok = clean_tok(m.group(1))
        spans.append(m.span())
        pat = tok.replace("/.../", "/**/")
        add(tok, [os.path.join(ctx.root, p) for p in expand(pat, stores)], m)
    for m in RE_BARE.finditer(line):
        if any(a <= m.start() < b for a, b in spans):
            continue
        tok = clean_tok(m.group(1))
        dirs = []
        if last_dir:
            dirs.append(last_dir)
        dirs.append(ctx.data_dir)
        for dm in re.finditer(r"\b(20\d\d-\d\d-\d\d)\b", line):
            dirs.append(os.path.join(ctx.shifts, dm.group(1), "data"))
        if CARRY.search(line):
            dirs += prior_data_dirs(ctx)
        miss_all, found_any = [], False
        for concrete in expand(tok, stores):
            if any(exists(os.path.join(d, concrete)) for d in dirs) or \
                    exists(os.path.join(ctx.data_dir, "**", concrete)):
                found_any = True
                continue
            older = [d for d in prior_data_dirs(ctx) if exists(os.path.join(d, concrete))]
            miss_all.append(os.path.join(older[0], concrete) + OLDER_NOTE if older
                            else os.path.join(ctx.data_dir, concrete))
        if miss_all and negated(line, *m.span()):
            continue
        out.append((tok, miss_all, found_any))
    for m in RE_WIKI.finditer(line):
        target = m.group(1).strip()
        if "/" not in target:
            continue
        p = os.path.join(ctx.root, target if target.endswith(".md") else target + ".md")
        out.append((target, [] if os.path.exists(p) else [p], os.path.exists(p)))
    return out


OLDER_NOTE = " (only in an earlier night's data; cite that dated path)"


def rule_paths(doc, ctx):
    for n, line in doc.body():
        for tok, miss, _any in cited_files(doc, ctx, n, line):
            if not miss:
                continue
            rels = [os.path.relpath(p.replace(OLDER_NOTE, ""), ctx.root) + (OLDER_NOTE if OLDER_NOTE in p else "")
                    for p in miss[:4]]
            ctx.warn(n, "path-missing", "cited '%s' but not on disk: %s%s" % (tok, ", ".join(rels),
                                                                            " ..." if len(miss) > 4 else ""),
                     "Write the printed result to that path (never > redirection), or fix the path")


SOURCE_LIKE = re.compile(r"sheet|\btab\b|tabs|tool|mcp__|webfetch|websearch|https?://|www\.|\.com\b|pull|pulled|report|"
                         r"export|email|mail|console|ad hoc|ad-hoc|gdata|drive-ls|mail-ls|\.py\b|\.json|\.md\b|\.csv|"
                         r"\.xlsx|\.pdf|\.txt|toolsearch|newsroom|press\.|fetched|read directly|searched|api", re.I)
UNSAVED_WORDS = re.compile(r"console output|ad hoc|ad-hoc|read directly|read live|webfetch|websearch|not saved|"
                           r"in (?:the|my) session|on screen", re.I)


def tab_saved(ctx, tab, stores_on_line):
    if tab == "ad_text_7d":
        return bool(glob.glob(os.path.join(ctx.data_dir, "**", "ad_text_*.json"), recursive=True))
    cands = stores_on_line or PLAYER_STORES.get(ctx.player, ALL_STORES)
    for st in cands:
        if glob.glob(os.path.join(ctx.data_dir, "**", "%s_%s.*" % (st, tab)), recursive=True):
            return True
    return bool(glob.glob(os.path.join(ctx.data_dir, "**", "*%s*" % tab), recursive=True))


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def url_saved(ctx, line):
    """True when a URL or article title on the line is found in a saved file under tonight's data/
    (a sources_*.md copy, a saved release .txt), False when it is not, None when the line has neither."""
    urls = re.findall(r"(?:https?://)?(?:[\w-]+\.)+(?:com|org|gov|net|io|co)(?:/[^\s,)`'\"]*)?", line)
    titles = [t for t in re.findall(r"[\"\u201c]([^\"\u201d]{12,})[\"\u201d]", line)]
    if not urls and not titles:
        return None
    texts = ctx.data_texts()
    if not texts:
        return False
    names = " ".join(ctx.data_index().keys()).lower()
    for u in urls:
        u2 = re.sub(r"^https?://", "", u).rstrip("/.").lower()
        if len(u2) > 12 and "/" in u2 and u2 in texts:
            return True
        for tok in re.findall(r"[A-Za-z0-9_]*\d[A-Za-z0-9_]{6,}", u):
            if tok.lower() in names or tok.lower() in texts:
                return True
    for t in titles:
        t2 = t.strip(" ,.").lower()
        if len(t2) >= 12 and (t2[:60] in texts or slug(t2)[:50] in texts):
            return True
    return False


TOOL_NOTE = re.compile(r"toolsearch|usage\.py --tools|not loaded|tools? (?:did not|didn't) load|connector caveat", re.I)
SAVED_TO = re.compile(r"saved (?:to|as|in|at)\s+`?((?:outputs/|data/)[^\s`,;)]+)", re.I)


def rule_sources_saved(doc, ctx):
    for n, line in doc.section_lines("Sources"):
        if not line.strip() or not SOURCE_LIKE.search(line) or TOOL_NOTE.search(line):
            continue
        if re.search(r"\bslack\b", line, re.I) and re.search(r"\bts\b|\d{10}\.\d{6}", line) and \
                not re.search(r"sheet|tool|mcp__|pull", line, re.I):
            continue          # a pointer to a Slack message, not a data pull
        stores_line = [c for _, c in stores_in(line)]
        tabs = [t for t in ADS_TABS if re.search(r"(?<![\w])%s(?![\w])" % t, line)]
        unsaved_tabs = [t for t in tabs if not tab_saved(ctx, t, stores_line)]
        if unsaved_tabs:
            ctx.warn(n, "source-not-saved", "Ads tabs read live but not saved to data/: %s" % ", ".join(unsaved_tabs),
                     "cite the saved copy (campaign_daily_30d: ledgers.py ads-dump; change_events_14d: changes.py "
                     "writes data/{STORE}_change_events_14d.txt); for a tab with no saver yet (gdata.py sheet only "
                     "prints), tell Magic which tab, and until it has one waive the line with "
                     "%%lint-ok source-not-saved: no saver for that tab yet%%")
            continue
        files = cited_files(doc, ctx, n, line)
        saved = bool(tabs) or any(found for _t, _m, found in files) or bool(url_saved(ctx, line))
        live_words = UNSAVED_WORDS.search(line)
        if live_words:
            st = SAVED_TO.search(line)
            if st and exists(os.path.join(ctx.shift_dir if st.group(1).startswith("data/") else ctx.root,
                                          clean_tok(st.group(1)))):
                continue
            saved = False
        if saved:
            continue
        if ctx.player == "nick" and re.search(r"\.(?:xlsx|pdf)\b|email", line, re.I):
            fix = ("cite tonight's data/crm_mtd_{STORE}.json that holds these aggregates (file names only, never "
                   "raw PII in the vault)")
        elif re.search(r"https?://|www\.|\.com\b|\.co\b|newsroom", line, re.I):
            fix = "save the page text with its URL and date to data/sources_{topic}.md and cite that file"
        else:
            fix = ("Write the printed result to outputs/ai-team/%s/data/{lane}_{what}_{STORE}.json (never > redirection), "
                   "then cite that path" % ctx.date.isoformat())
        why = ("'%s' is not a saved file" % live_words.group(0)) if live_words else "no saved file behind it"
        ctx.warn(n, "source-not-saved", "%s: %s" % (why, line.strip().lstrip("- ")[:80]), fix)


ABSENCE = [
    re.compile(r"\bnot (?:yet )?indexed\b", re.I),
    re.compile(r"\b(?:isn'?t|is not|hasn'?t|has not|wasn'?t|was not|haven'?t|have not)(?: been| yet)? indexed\b", re.I),
    re.compile(r"\bno\s+(?:[\w'-]+\s+){0,4}(?:exists?|found)\b(?!\s+yet)", re.I),
    re.compile(r"\b(?:doesn'?t|does not|don'?t|do not|didn'?t|did not)\s+exist\b", re.I),
    re.compile(r"\b(?:nobody|no one)(?: else)? (?:ranks?|is (?:ranking|writing|covering|running|offering|selling|"
               r"advertising|bidding)|has (?:written|covered|published|indexed|ranked)|covers|owns|offers|sells|writes|"
               r"answers|mentions|advertises|bids|targets|publishes|else)\b", re.I),
    re.compile(r"\bfirst\b[^.;]{0,50}\bin (?:the )?market\b", re.I),
    re.compile(r"\b(?:zero|no) (?:search )?results\b", re.I),
    re.compile(r"\bonly (?:store|dealer(?:ship)?) (?:in|to|that)\b", re.I),
]


def rule_absence(doc, ctx):
    for n, line in doc.body():
        if doc.meta[n - 1]["code"] or line.lstrip().startswith("#"):
            continue
        if doc.in_section(n, "sources", "data gaps", "report freshness"):
            continue
        hit = None
        quoted = [q.span() for q in re.finditer(r"[\"\u201c][^\"\u201d]*[\"\u201d]", line)]
        for rx in ABSENCE:
            for m in rx.finditer(line):
                if any(a <= m.start() < b for a, b in quoted):
                    continue
                if re.search(r"(?:not that|isn'?t that|rather than|instead of)\W*(?:\w+\W+){0,4}$",
                             line[max(0, m.start() - 40):m.start()], re.I):
                    continue
                hit = m.group(0)
                break
            if hit:
                break
        if not hit:
            continue
        if re.search(r"no data since", line, re.I):
            continue
        files = cited_files(doc, ctx, n, line)
        if any(found and ("data/" in t or re.match(DATA_PREFIX, os.path.basename(t))) for t, _m, found in files):
            continue
        stores_line = [c for _, c in stores_in(line)]
        if any(re.search(r"(?<![\w])%s(?![\w])" % t, line) and tab_saved(ctx, t, stores_line) for t in ADS_TABS):
            continue
        ctx.warn(n, "absence-unsourced", "absence claim '%s' with no saved file cited" % hit,
                 "cite the saved query that came back empty (data/...), or soften it to what you actually checked")


UNIT_WORDS = (r"sessions?|leads?|clicks?|conversions?|calls?|impressions?|sold|appointments?|appts?|prospects?|"
              r"key[- ]events?|visits?|units?|keywords?|referrals?")
RE_FACT = re.compile(r"(?<![\w.$/-])(\$?\d[\d,]*(?:\.\d+)?)(%?)\s+(?:(?:real|total|new|organic|paid|web|website|good|"
                     r"engaged|clean|more|fewer|ads?|google|crm|ga4|phone|form)\s+){0,2}(" + UNIT_WORDS + r")\b", re.I)
RE_SPEND = re.compile(r"\b(?:spent|spend|spending|cost)\s+(?:of\s+|was\s+|is\s+|about\s+|roughly\s+)?"
                      r"(\$\d[\d,]*(?:\.\d+)?)|(\$\d[\d,]*(?:\.\d+)?)\s+(?:spent|in spend|of spend)\b", re.I)
RANGE_TOK = [
    (re.compile(r"\b(?:last|past|trailing)\s+7\b|\b7[- ]?(?:d|day)s?\b|\bweek\b|\bweekly\b", re.I), "7d"),
    (re.compile(r"\b(?:last|past|trailing)\s+28\b|\b28[- ]?(?:d|day)s?\b", re.I), "28d"),
    (re.compile(r"\b(?:last|past|trailing)\s+30\b|\b30[- ]?(?:d|day)s?\b", re.I), "30d"),
    (re.compile(r"\b14[- ]?(?:d|day)s?\b", re.I), "14d"),
    (re.compile(r"\bMTD\b|month to date", re.I), "mtd"),
    (re.compile(r"\bweekend\b", re.I), "weekend"),
]


def label_before(sent, pos):
    """Up to four content words just before a number: what the number is about."""
    words = [w for w in re.findall(r"[a-z][a-z'-]+", sent[max(0, pos - 60):pos].lower()) if w not in STOP_SIM]
    return frozenset(words[-4:])


def facts(doc, ctx, lines):
    out = []
    for n, line in lines:
        for s0, sent in sentences(line):
            keys = set()
            for rx, k in RANGE_TOK:
                if rx.search(sent):
                    keys.add(k)
            for m in RE_DATE_ANY.finditer(sent):
                d = parse_date(m.group("tok"), ctx.date)
                if d:
                    keys.add(d.isoformat())
            if not keys:
                continue
            for m in RE_SPEND.finditer(sent):
                amt = m.group(1) or m.group(2)
                st = store_before(sent, m.start(), None) or doc.meta[n - 1]["store"]
                if not st:
                    continue
                try:
                    val = float(amt.replace("$", "").replace(",", ""))
                except ValueError:
                    continue
                out.append((st, "$spend", frozenset(keys), val, n, m.group(0), label_before(sent, m.start())))
            for m in RE_FACT.finditer(sent):
                unit = m.group(3).lower().replace("-", " ")
                unit = {"appts": "appointment", "appt": "appointment"}.get(unit, unit).rstrip("s")
                st = store_before(sent, m.start(), None) or doc.meta[n - 1]["store"]
                if not st:
                    continue
                try:
                    val = float(m.group(1).replace("$", "").replace(",", ""))
                except ValueError:
                    continue
                out.append((st, unit + m.group(2), frozenset(keys), val, n, m.group(0), label_before(sent, m.start())))
    return out


def rule_headline_conflict(doc, ctx):
    head = facts(doc, ctx, doc.section_lines("Headlines"))
    rep_ = facts(doc, ctx, doc.section_lines("Report to Magic"))
    if not head or not rep_:
        return
    for st, unit, keys, val, n, txt, lab in rep_:
        same = [h for h in head if h[0] == st and h[1] == unit and h[2] == keys]
        if not same or any(h[3] == val for h in same):
            continue
        close = [h for h in same if lab and h[6] and len(lab & h[6]) >= min(2, len(lab), len(h[6]))]
        if not close:
            continue
        h = close[0]
        ctx.warn(n, "headline-conflict", "%s %s (%s): Headlines line %d says '%s', Report to Magic says '%s'" %
                 (st, unit, ", ".join(sorted(keys)), h[4], h[5], txt),
                 "make both say the verified number, or name the different windows")


STOP_SIM = set("""the a an and or of to in on at for with from by is are was were be been it its this that these those
as vs not no but so than then into over under after before about per our his her their they them we you your all any
each only just still also now tonight night shift same one two three four five store stores""".split())
DELTA = re.compile(r"up from|down from|\bwas \$?\d|\bfrom \$?\d[\d,.]*%? to \$?\d|\+\d|since (?:last night|friday|"
                   r"thursday|yesterday|\d)|vs\.? last night|from last night|filled in|backfill|restat|changed|"
                   r"new tonight|first time|no longer|reversed|jumped|dropped|fell|rose|climbed|grew|"
                   r"correction|corrected|\b(?:is|are|has|have) now\b|\d[\d.,]*%?\s+to\s+\$?\d", re.I)


def sim_tokens(text):
    t = re.sub(r"[*`_\[\]()]", " ", text.lower())
    return {w for w in re.findall(r"[a-z][a-z'-]{2,}|\d[\d,.]*%?", t) if w not in STOP_SIM}


def prior_findings(ctx):
    best = None
    for d in range(1, 8):
        day = ctx.date - dt.timedelta(days=d)
        p = os.path.join(ctx.shifts, day.isoformat(), ctx.player + ".md")
        if os.path.exists(p):
            best = (day, p)
            break
    return best


REPEAT_WORDS = re.compile(r"\b(?:second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|\d+(?:st|nd|rd|th))\s+"
                          r"(?:straight\s+|consecutive\s+|dark\s+|shift\s+)*(?:nights?|shifts?|mornings?|days?)\b|"
                          r"\b(?:two|three|four|five|six|seven|\d+)(?:-plus)?\s+(?:nights|shifts|mornings|days)\s+running\b|"
                          r"same (?:gap|story|pattern|finding|read) as|\bno change\b|nothing (?:new|to report)|"
                          r"still (?:dark|holding|the same)|same as (?:last night|friday|thursday|yesterday)", re.I)


def rule_repeat_headline(doc, ctx, threshold=0.4):
    prev = prior_findings(ctx)
    pheads, pday = [], None
    if prev:
        pday, ppath = prev
        with open(ppath, encoding="utf-8", errors="replace") as fh:
            pdoc = Doc(ppath, fh.read())
        pheads = [(n, l, sim_tokens(l)) for n, l in pdoc.section_lines("Headlines") if l.strip()]
    else:
        ctx.note("no earlier %s.md in the last 7 days; repeat-headline compares wording only" % ctx.player)
    for n, line in doc.section_lines("Headlines"):
        if not line.strip() or DELTA.search(line):
            continue
        rw = REPEAT_WORDS.search(line)
        if rw:
            ctx.warn(n, "repeat-headline", "the headline says itself it is a repeat ('%s')" % rw.group(0),
                     "a repeat is not a headline: log it as a one-line carryover or 'settled check' in By store, "
                     "and keep Headlines for what changed since last night")
            continue
        cur = sim_tokens(line)
        if len(cur) < 6:
            continue
        best, bn = 0.0, None
        for pn, pl, pt in pheads:
            if len(pt) < 6:
                continue
            j = len(cur & pt) / float(len(cur | pt))
            if j > best:
                best, bn = j, pn
        if best >= threshold:
            ctx.warn(n, "repeat-headline", "says what %s's headline (line %d) said, %.0f%% the same words, with no "
                     "change named" % (pday.isoformat(), bn, best * 100),
                     "lead with what changed since last night (the delta), or move it to a one-line carryover "
                     "outside Headlines")


RANGE_ANY = re.compile(r"\b(?:\d+[- ]?(?:d|day|days|night|nights|week|weeks|month|months)\b|last ?\d+|prior ?\d+|"
                       r"l7\b|last night|this week|last week|this morning|MTD|YTD|"
                       r"month|week|weekend|tonight|yesterday|overnight|since|through|thru|daily|/day|a day|per day|"
                       r"a night|per night|lifetime|today|hour|hourly)", re.I)


def rule_date_range(doc, ctx):
    for n, line in doc.section_lines("Headlines"):
        if not line.strip() or not metric_numbers(line):
            continue
        if RANGE_ANY.search(line) or RE_DATE_ANY.search(line) or RE_WD_WORD.search(line):
            continue
        t, w0 = ctx.target, ctx.target - dt.timedelta(days=6)
        ctx.warn(n, "no-date-range", "headline number with no date or window",
                 "add the window next to the number (%s, last 7 days %s to %s, MTD through %s)" %
                 (t.strftime("%-m/%-d"), w0.strftime("%-m/%-d"), t.strftime("%-m/%-d"), t.strftime("%-m/%-d")))


RE_ACCOUNT = re.compile(r"(?:\bCID\b|customer id|account id|ad account|ads account|account)\D{0,12}"
                        r"(\d{3}-\d{3}-\d{4}|\d{9,16})|\bact_\d{6,}", re.I)


def rule_account_ids(doc, ctx):
    for n, line in doc.body():
        if doc.in_section(n, "sources"):
            continue
        m = RE_ACCOUNT.search(line)
        if m:
            shown = m.group(0).strip()[:40]
            hide = len(re.findall(r"\d", shown)) - 4   # the warning gets pasted into bounces: last four digits only
            out = []
            for ch in shown:
                if ch.isdigit() and hide > 0:
                    out.append("x")
                    hide -= 1
                else:
                    out.append(ch)
            shown = "".join(out)
            ctx.warn(n, "account-id", "account id in the findings: %s" % shown,
                     "name the store instead (Slack and the brief never carry Ads customer ids or Meta account ids)")


CHANGE_VERB = re.compile(r"\b(?:[Pp]aused|[Uu]npaused|[Rr]e-?enabled|[Ee]nabled|turned (?:on|off)|[Ss]witched|"
                         r"[Rr]aised|[Ll]owered|[Ee]dited|[Rr]emoved|[Aa]dded|set (?:a|the|it|to)|[Cc]hanged|"
                         r"[Uu]pdated|[Ss]wapped|[Aa]pplied|[Cc]ut (?:the|it|its)|[Ii]ncreased (?:the|it|its)|"
                         r"[Dd]ecreased (?:the|it|its)|[Rr]eplaced|[Rr]estarted|[Rr]esumed|[Ss]topped)\b")
CHANGE_OBJ = re.compile(r"\b(?:budget|bid|bidding|target cpa|tcpa|troas|target roas|geo|location|negative|keyword|"
                        r"ad group|asset|network|audience|conversion goal|conversion action|campaign|ad set|creative|"
                        r"placement|schedule|ad copy|headline|RSA|PMax|Performance Max)s?\b", re.I)
ACTOR = re.compile(r"\bDrew\b|auto-?appl|recommendation|\bGoogle\b|\bMeta\b|script|\bstore\b|\bGM\b|agency|vendor|"
                   r"\buser\b|login|someone|unknown|actor|\bby [A-Z][a-z]+|\bRon\b|Constellation|client type|"
                   r"clientType|mobile app|web client|userEmail|the dealer|DigitalCLIQ|\bwe\b|\bI\b|\bhe\b|\bshe\b|"
                   r"\bthey\b|himself|herself|nobody touched|no change|no changes|unchanged|automated rule|\bperson\b|"
                   r"changes_[A-Z]+|changes\.json", re.I)
STATE_BEFORE = re.compile(r"(?:\b(?:the|a|an|its|their|his|her|already|still|stays|stayed|remains|remained|now|"
                          r"currently|remain|any|every|each|only|both|all|two|three|four|five|six|of|is|are|was|"
                          r"were|been|being)|\d)\s+$", re.I)
STATE_AFTER = re.compile(r"\s+(?:campaigns?|ad groups?|ads?\b|keywords?|ad sets?|budgets?|assets?|lines?|posts?|"
                         r"status|since|all|the whole|throughout|across)", re.I)


def rule_actor(doc, ctx):
    if ctx.player not in ("shaq", "luka"):
        return
    for n, line in doc.body():
        if doc.meta[n - 1]["code"] or line.lstrip().startswith("#"):
            continue
        if doc.in_section(n, "sources", "data gaps", "recommendations", "ad text"):
            continue
        if ACTOR.search(line):
            continue
        for s0, sent in sentences(line):
            bare = re.sub(r"\([^)]*\)", " ", sent)          # metadata in parentheses is not a change event
            if re.search(r"\b(?:should|could|would|recommend|suggest|propose|needs? (?:drew'?s )?go|if |whether|"
                         r"to be|asks?|consider|want|plan)\b", bare, re.I):
                continue
            hit = None
            for v in CHANGE_VERB.finditer(bare):
                if v.group(0).isupper():
                    continue      # PAUSED, ENABLED: a status value, not an edit
                if STATE_BEFORE.search(bare[max(0, v.start() - 14):v.start()]) and \
                        not re.search(r"\b(?:was|were|been|got)\s+$", bare[max(0, v.start() - 8):v.start()]):
                    continue      # "the paused campaign", "two enabled campaigns"
                if STATE_AFTER.match(bare[v.end():v.end() + 20]):
                    continue
                if re.search(r"\b(?:no|not|never|without|nothing|n't)\b[^.]{0,20}$", bare[max(0, v.start() - 24):v.start()]):
                    continue
                hit = v
                break
            if not hit or not CHANGE_OBJ.search(bare):
                continue
            ctx.warn(n, "actor-missing", "an account change ('%s') with nobody named as who made it" % hit.group(0),
                     "name the actor from the change log (data/changes_{STORE}.md): Drew, Drew applying a Google "
                     "recommendation, Google auto-apply, a script, or the named person; never guess")
            break


def rule_coming_up(doc, ctx):
    if ctx.date < COMING_UP_FROM:
        return
    lines = doc.section_lines("Report to Magic")
    if not lines:
        return
    if not any(re.search(r"coming up|looking ahead|ahead:|next \d+ days|watch for", l, re.I) for _, l in lines):
        n = lines[0][0] - 1
        ctx.warn(n, "coming-up-missing", "Report to Magic has no 'coming up' line",
                 "end it with at least one 'Coming up:' line (a risk building, a deadline, a pattern starting) "
                 "with its evidence")


# NCBMW vendor paid search (verified 2026-09-28). NabThat's shared Data Studio dashboard shows the WHOLE
# website's GA4 Sessions, Engagement rate and keyEvents:asc_form_submission (Sep 1 to 27: dashboard 13,275
# sessions, GA4 13,011 across all channels, 6,762 from Paid Search), and it has no Cost box, so any dollar
# read off it is implied (clicks x avg CPC). The legitimate NabThat traffic line is the credit split
# estimate in data/vendor_ppc_NCBMW.md. Both rules read whole lines, like red-number's caveat check.
VENDOR = re.compile(r"nabthat", re.I)
VENDOR_SITE_METRIC = re.compile(r"\bsessions?\b|\bvisits?\b|engagement rate|\bform submissions?\b|\bforms\b|"
                                r"asc_form_submission", re.I)
VENDOR_SITE_OK = re.compile(r"\b(?:whole|entire) (?:web ?)?site\b|\bsite-?wide\b|all channels|not \[*nabthat|"
                            r"estimat|untagged|split|credited", re.I)
VENDOR_DOLLAR = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?(?:[kKmM]\b)?")
VENDOR_SPEND = re.compile(r"\bspen(?:d|t|ding)\b|\bcosts?\b", re.I)
VENDOR_COST_OK = re.compile(r"implied|clicks\s*(?:x|×)\s|sheet|\bfees?\b|\bcaps?\b|budget|invoice|"
                            r"per credited|per key[- ]?events?|per lead", re.I)


def vendor_lines(doc):
    """Lines naming NabThat, minus frontmatter, code, headings, Sources and Data gaps."""
    for n, line in doc.body():
        if doc.meta[n - 1]["code"] or line.lstrip().startswith("#"):
            continue
        if doc.in_section(n, "sources", "data gaps"):
            continue
        if VENDOR.search(line):
            yield n, line


def rule_vendor_site_boxes(doc, ctx):
    for n, line in vendor_lines(doc):
        m = VENDOR_SITE_METRIC.search(line)
        if not m or VENDOR_SITE_OK.search(line):
            continue
        ctx.warn(n, "vendor-site-boxes", "NabThat line quotes '%s': the dashboard's Sessions, Engagement rate and "
                 "form submission boxes are the whole website in GA4, not NabThat's traffic" % m.group(0),
                 "say these dashboard boxes are the whole website, or cite the credit split estimate from "
                 "vendor_ppc_NCBMW.md (\"about X% of GA4's untagged paid visits are NabThat's (range A to B), "
                 "estimated\")")


def rule_vendor_implied_cost(doc, ctx):
    for n, line in vendor_lines(doc):
        d = VENDOR_DOLLAR.search(line)
        if not d or not VENDOR_SPEND.search(line) or VENDOR_COST_OK.search(line):
            continue
        ctx.warn(n, "vendor-implied-cost", "NabThat %s given as spend or cost with no source named (the dashboard "
                 "has no Cost box)" % d.group(0),
                 "dashboard dollars are \"implied (clicks x avg CPC)\"; the monthly sheet's actual spend should "
                 "name the sheet")


RULES = [rule_headings, rule_placeholders, rule_em_dash, rule_weekdays, rule_date_window, rule_prelim,
         rule_rulings_settled, rule_red_numbers, rule_ask_status, rule_paths, rule_sources_saved, rule_absence,
         rule_headline_conflict, rule_repeat_headline, rule_date_range, rule_account_ids, rule_actor,
         rule_coming_up, rule_vendor_site_boxes, rule_vendor_implied_cost]


def lint_file(root, date, player, path, target=None):
    ctx = Ctx(root, date, player, path, target)
    with open(path, encoding="utf-8", errors="replace") as fh:
        doc = Doc(path, fh.read())
    for rule in RULES:
        try:
            rule(doc, ctx)
        except Exception as e:  # a rule bug must never block a player
            ctx.note("rule %s crashed: %s: %s" % (rule.__name__, type(e).__name__, e))
    seen, uniq = set(), []
    for w in ctx.warnings:
        k = (w["line"], w["rule"], w["msg"])
        if k not in seen:
            seen.add(k)
            uniq.append(w)
    uniq.sort(key=lambda w: (w["line"], w["rule"]))
    # "Explain" a warning with an Obsidian comment on the flagged line (hidden in reading view):
    #   %%lint-ok prelim-missing: Friday's number, not the newest day%%
    # A warning anchored on line 1 (a missing heading) can be waived from any line. The reason must
    # be real words (8+ characters); Magic reads every WAIVED line.
    waivers = {}
    for i, line in enumerate(doc.raw):
        for m in RE_WAIVER.finditer(line):
            reason = m.group(2).strip()
            if len(reason) < 8:
                continue
            for r in re.split(r"[,\s]+", m.group(1).strip()):
                if not r:
                    continue
                r = r.replace("_", "-")      # vendor_site_boxes waives vendor-site-boxes
                waivers.setdefault((i + 1, r), reason)
                waivers.setdefault(("any", r), reason)
    kept, waived = [], []
    for w in uniq:
        reason = waivers.get((w["line"], w["rule"])) or (waivers.get(("any", w["rule"])) if w["line"] == 1 else None)
        if reason:
            w = dict(w, waived=reason)
            waived.append(w)
        else:
            kept.append(w)
    ctx.warnings = kept
    ctx.waived = waived
    return ctx


RE_WAIVER = re.compile(r"%%\s*lint-ok\s+([a-z][a-z_\-, ]*?)\s*:\s*(.+?)%%")


def fmt(w):
    return "WARN %s:%d [%s] %s | fix: %s" % (w["file"], w["line"], w["rule"], w["msg"], w["fix"])


def run(args):
    root = os.path.abspath(args.root or DEFAULT_ROOT)
    try:
        date = dt.date.fromisoformat(args.date)
        target = dt.date.fromisoformat(args.target_date) if args.target_date else None
    except ValueError as e:
        print("bad date: %s" % e)
        return 2
    players = list(PLAYERS) if args.player == "all" else [args.player]
    if args.file and len(players) != 1:
        print("--file needs one --player")
        return 2
    results = []
    for p in players:
        path = args.file or os.path.join(root, "outputs", "ai-team", date.isoformat(), p + ".md")
        if not os.path.isabs(path):
            path = os.path.join(root, path)
        if not os.path.exists(path):
            if args.player == "all":
                continue
            print("no findings file at %s" % os.path.relpath(path, root))
            return 2
        results.append(lint_file(root, date, p, path, target))
    if not results:
        print("no findings files in outputs/ai-team/%s/" % date.isoformat())
        return 2
    out_lines, total, js, waived_total = [], 0, [], 0
    for ctx in results:
        for w in ctx.warnings:
            out_lines.append(fmt(w))
            js.append(w)
        for w in ctx.waived:
            out_lines.append("WAIVED %s:%d [%s] %s | reason: %s" % (w["file"], w["line"], w["rule"], w["msg"],
                                                                    w["waived"]))
            js.append(w)
            waived_total += 1
        for nline in ctx.notes:
            out_lines.append("NOTE %s: %s" % (ctx.rel, nline))
        if len(results) > 1:
            out_lines.append("%s: %d warnings%s" % (ctx.rel, len(ctx.warnings),
                                                    ", %d waived" % len(ctx.waived) if ctx.waived else ""))
        total += len(ctx.warnings)
    out_lines.append("lint: %d warnings%s" % (total, ", %d waived" % waived_total if waived_total else ""))
    text = "\n".join(out_lines)
    print(text)
    if args.out:
        op = args.out if os.path.isabs(args.out) else os.path.join(root, args.out)
        os.makedirs(os.path.dirname(op) or ".", exist_ok=True)
        with open(op, "w", encoding="utf-8") as fh:
            if op.endswith(".json"):
                json.dump({"date": date.isoformat(), "warnings": js, "total": total, "waived": waived_total,
                           "notes": [n for c in results for n in c.notes]}, fh, indent=1)
            else:
                fh.write(text + "\n")
    return 1 if total else 0


# ---------------------------------------------------------------- selftest
AGENT_SHAQ = """# Shaq

## Output
Write `outputs/ai-team/{date}/shaq.md`:
- `## Headlines` three to five lines with numbers
- `## By store` pacing
- `## Recommendations` each one
- `## Huddles` per the protocol
- `## Data gaps`
- `## Report to Magic` the last thing you write
- `## Sources` Sheet id, tab, and range behind every number
"""

CLEAN = """# Shaq, Google Ads, 2026-09-29 shift (Tuesday, target date Monday 2026-09-28)

## Headlines

- MCP PMax spent $412.10 over the last 7 days (9/22 to 9/28) for 14 Calls from ads, per `data/MCP_campaign_daily_30d.txt`; Monday 9/28 alone is preliminary at $38.20.
- NOI Value-Payment lost 62% of impression share to budget on Sunday 9/27 (`data/NOI_campaign_daily_30d.txt`).

## Ad text

- NOI: 1 ad flagged for review (ATC-PREAPPROVED), still live, needs Drew's go before 10/1.

## By store

### MCP
Drew raised the PMax budget to $150 on Thursday 9/24 at 1:34pm (change log, `data/MCP_change_events_14d.json`). Coming week: the target CPA auto-apply (A1, confirmed, still open) is the thing to watch.

### ATLAS
Atlas Ads counts page views as conversions (RED on the health board), so no conversion number is used here.

## Recommendations

1. Turn off auto-apply on MCP. Evidence: `data/MCP_change_events_14d.json`. Needs Drew's go.

## Huddles

None tonight.

## Data gaps

- Search Console is not connected yet.

## Report to Magic

Working: MCP Search calls are real. Not working: auto-apply keeps editing MCP (A1, confirmed, still open). Suggestion: turn it off. Source: `data/MCP_change_events_14d.json`.
Coming up: the CARS Act starts 10/1 and NOI's pre-qualify line is still live (`data/ad_text_NOI.json`).

## Sources

- `outputs/ai-team/2026-09-29/data/MCP_campaign_daily_30d.txt` (ads-dump, export last_run 2026-09-29 0:52)
- `outputs/ai-team/2026-09-29/data/NOI_campaign_daily_30d.txt`
- `data/MCP_change_events_14d.json` (saved tonight with gdata.py sheet --out)
- `data/ad_text_NOI.json` (ad_text_check.py)
"""

DIRTY = """# Shaq, Google Ads, 2026-09-29 shift

## Headlines

- MCP PMax spent $412.10 over the last 7 days for 14 Calls from ads.
- NOI Value-Payment spent $88.00 on 9/28 with 9 conversions.
- Atlas logged 36 conversions in the last 7 days, a strong week.
- Rogue Hybrid content is first in market for this store and not indexed anywhere.
- The Costco and Pownder costs at NOI are up again this week, $1,200 over 7 days.
- MCP spend of $500 per the huddle. TODO confirm.
- MCP Search campaigns pulled real Calls from ads over the trailing week, all counted in the primary column.
- Search volume held.

## By store

### MCP
On Friday 9/24 the PMax budget was raised to $150. The ask A1 is settled now. A12 remains open. See A99 too.
Status: [PENDING] and {player} still to fill """ + EM_DASH + """ sorry.
The bmwblog piece is dated 2026-12-16. MCP spend on 2025-01-05 was $400. CID 346-925-5700.
Cited `data/MCP_search_terms_7d.json` and `outputs/ai-team/2026-09-29/data/semrush_pt_{SBMW,NOI}.json`.
The Sun-Mon (9/21-22) trend held.
The auto-bid thing is covered in settled item S1 and the Tekion export is still missing, nothing new there.
MCP Tekion export missing again, 0 CRM rows for 9 nights.
NabThat drove 13,275 sessions Sep 1 to 27 on its dashboard.
NabThat spent $4,120 Sep 1 to 27.

## Recommendations

## Huddles

None.

## Report to Magic

Working: MCP PMax spent $512.00 over the last 7 days for 14 Calls from ads.

## Data gaps

- none

## Sources

- Console output of the ad hoc gdata.py sheet pull
- `search_terms_7d`, MCP Sheet id, read directly tonight
"""

PRIOR_HEAD = """# Shaq, 2026-09-28

## Headlines

- MCP Search campaigns pulled real Calls from ads over the trailing week, all counted in the primary column.
"""

# Vendor rules, line by line: (line, rules that must WARN on it, rules that must be WAIVED on it).
# Every other line must raise neither vendor rule.
VS, VC = "vendor-site-boxes", "vendor-implied-cost"
VENDOR_FIXTURE = [
    ("# Shaq, vendor rules fixture", (), ()),
    ("", (), ()),
    ("## Vendor PPC (NCBMW)", (), ()),
    ("", (), ()),
    # vendor-site-boxes fires: one line per metric word
    ("- NabThat's dashboard shows 13,275 sessions Sep 1 to 27.", (VS,), ()),
    ("- NabThat visits climbed 4% day over day.", (VS,), ()),
    ("- NabThat engagement rate held at 61% Sep 1 to 27.", (VS,), ()),
    ("- [[NabThat]] drove 70 form submissions Sep 1 to 27.", (VS,), ()),
    ("- NabThat forms: 70 Sep 1 to 27.", (VS,), ()),
    ("- NABTHAT keyEvents:asc_form_submission read 70 Sep 1 to 27.", (VS,), ()),
    # vendor-site-boxes exemptions: one line per phrase
    ("- The Sessions box on NabThat's dashboard (13,275) is the whole website in GA4.", (), ()),
    ("- NabThat's dashboard sessions (13,275) cover the whole site.", (), ()),
    ("- NabThat's dashboard sessions (13,275) are site-wide.", (), ()),
    ("- NabThat's dashboard engagement rate is sitewide.", (), ()),
    ("- NabThat's dashboard form submissions (70) are the entire site.", (), ()),
    ("- NabThat's dashboard sessions (13,275) match GA4 all channels (13,011).", (), ()),
    ("- The dashboard's 13,275 sessions are not NabThat's traffic.", (), ()),
    ("- About 70% of GA4's paid visits are NabThat's (range 64 to 74), estimated.", (), ()),
    ("- NabThat owns most of GA4's untagged paid sessions.", (), ()),
    ("- NabThat's share of paid visits comes from the three-way split.", (), ()),
    ("- NabThat credited visits: about 4,700 of 6,762 Sep 1 to 27.", (), ()),
    ("- About 70% of GA4's untagged paid visits are NabThat's (range 64 to 74), estimated.", (), ()),
    # vendor-implied-cost fires: one line per spend word
    ("- NabThat spent $4,120 Sep 1 to 27.", (VC,), ()),
    ("- NabThat spend is $4,120 MTD.", (VC,), ()),
    ("- NabThat is spending $150 a day.", (VC,), ()),
    ("- NabThat's cost was $152.40 on 9/27.", (VC,), ()),
    # vendor-implied-cost exemptions: one line per phrase
    ("- NabThat implied spend $4,120 Sep 1 to 27.", (), ()),
    ("- NabThat spend $4,120 Sep 1 to 27 (clicks x avg CPC).", (), ()),
    ("- NabThat spent $26,300 in August per its monthly sheet.", (), ()),
    ("- NabThat spend $4,120 MTD plus its 15% fee.", (), ()),
    ("- NabThat spent $30,458 in August including fees.", (), ()),
    ("- NabThat spend is pacing to $31,000 against the $28,000 cap.", (), ()),
    ("- NabThat spend of $4,120 MTD is 15% of budget.", (), ()),
    ("- NabThat's August invoice shows $30,458 spent.", (), ()),
    ("- NabThat cost $12.10 per credited visit Sep 1 to 27.", (), ()),
    ("- NabThat cost $210 per key event Sep 1 to 27.", (), ()),
    ("- NabThat cost $310 per lead Sep 1 to 27.", (), ()),
    # neither fires: no NabThat, no dollar, no spend word, or metric words other than the boxes
    ("- The dashboard read 13,275 sessions and $4,120 spent.", (), ()),
    ("- NabThat spent more than planned.", (), ()),
    ("- NabThat's dashboard shows 1,204 clicks worth $4,120 Sep 1 to 27.", (), ()),
    # both fire on one line
    ("- NabThat drove 13,275 sessions on $4,120 spent.", (VS, VC), ()),
    # waived, hyphen and underscore spellings
    ("- NabThat drove 13,275 sessions. %%lint-ok vendor-site-boxes: quoting the vendor's own email claim%%",
     (), (VS,)),
    ("- NabThat spent $4,120. %%lint-ok vendor_implied_cost: the vendor's email states this figure%%",
     (), (VC,)),
    ("", (), ()),
    # skipped: a heading, a code block, Data gaps, Sources
    ("### NabThat sessions and $4,120 spent", (), ()),
    ("```", (), ()),
    ("NabThat sessions 13,275, spent $4,120", (), ()),
    ("```", (), ()),
    ("", (), ()),
    ("## Data gaps", (), ()),
    ("", (), ()),
    ("- NabThat's sessions box did not load, so the $4,120 spent is unchecked.", (), ()),
    ("", (), ()),
    ("## Sources", (), ()),
    ("", (), ()),
    ("- `data/vendor_ppc_NCBMW.md`: NabThat dashboard 13,275 sessions, $4,120 spent.", (), ()),
]


def selftest():
    fails = []
    with tempfile.TemporaryDirectory() as root:
        def w(rel, text):
            p = os.path.join(root, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(text)
            return p

        w(".claude/agents/shaq.md", AGENT_SHAQ)
        day = "outputs/ai-team/2026-09-29"
        for f in ("MCP_campaign_daily_30d.txt", "NOI_campaign_daily_30d.txt", "MCP_change_events_14d.json",
                  "ad_text_NOI.json", "semrush_pt_SBMW.json"):
            w("%s/data/%s" % (day, f), "{}")
        w("%s/data/health.json" % day, json.dumps({"stores": {
            "ATLAS": {"color": "red", "issues": [{"rule": "ADS_NON_LEAD_CONVERSIONS", "severity": "red",
                                                  "blocks": ["Google Ads conversions"], "tech": ""}],
                      "blocked_tonight": ["Google Ads conversions"]},
            "NOI": {"color": "amber", "issues": []}}}))
        w("outputs/ai-team/ledgers/rulings.json", json.dumps({"rulings": [
            {"id": "R2", "date": "2026-09-19", "store": "NOI", "lane": ["shaq", "nick"],
             "ruling": "Pownder, Radio and Costco are not active NOI sources; ignore their costs.",
             "applies_to_asks": [], "expires": None}]}))
        w("outputs/ai-team/ledgers/settled.json", json.dumps({"settled": [
            {"id": "S1", "store": "MCP", "lane": ["shaq", "nick"], "subject": "MCP has no Tekion CRM export",
             "keywords": ["Tekion", "export"], "settled_on": "2026-09-24", "finding": "no MCP CRM data",
             "reopen_if": "a Tekion file lands"}]}))
        w("outputs/ai-team/ledgers/asks.json", json.dumps({"asks": [
            {"id": "A1", "status": "open", "first_raised": "2026-09-19", "closed_date": None},
            {"id": "A12", "status": "closed", "first_raised": "2026-09-19", "closed_date": "2026-09-24"}]}))
        w("outputs/ai-team/2026-09-28/shaq.md", PRIOR_HEAD)
        clean = w("%s/shaq.md" % day, CLEAN)
        dirty = w("%s/draft-dirty.md" % day, DIRTY)
        date = dt.date(2026, 9, 29)

        c = lint_file(root, date, "shaq", clean)
        if c.warnings:
            fails.append("clean file raised %d warnings:\n  %s" % (len(c.warnings),
                                                                  "\n  ".join(fmt(x) for x in c.warnings)))
        d = lint_file(root, date, "shaq", dirty)
        got = {x["rule"] for x in d.warnings}
        want = {"heading-missing", "heading-empty", "heading-order", "placeholder", "em-dash", "weekday-mismatch",
                "date-future", "date-old", "prelim-missing", "ruling-repeat", "settled-repeat", "red-number",
                "ask-status", "path-missing", "source-not-saved", "absence-unsourced", "headline-conflict",
                "repeat-headline", "no-date-range", "account-id", "actor-missing", "coming-up-missing", VS, VC}
        for r in sorted(want - got):
            fails.append("dirty file did not trigger %s" % r)
        for note in c.notes + d.notes:
            if "crashed" in note:
                fails.append(note)
        # specific checks
        msgs = "\n".join(fmt(x) for x in d.warnings)
        for needle in ("A1", "A12", "A99", "semrush_pt_NOI.json", "9/24", "Sun-Mon"):
            if needle not in msgs:
                fails.append("expected a warning mentioning %s" % needle)

        # CLI: --player all with --out, exit code 1 with warnings, JSON out
        class A:
            pass
        a = A()
        a.root, a.date, a.target_date, a.player, a.file = root, "2026-09-29", None, "all", None
        a.out = os.path.join(root, "lint.json")
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = run(a)
        if rc != 0:
            fails.append("--player all on the clean shift folder exited %d:\n%s" % (rc, buf.getvalue()))
        try:
            with open(a.out) as fh:
                if json.load(fh)["total"] != 0:
                    fails.append("JSON out total should be 0")
        except (OSError, ValueError, KeyError) as e:
            fails.append("JSON out unreadable: %s" % e)
        a.player, a.file, a.out = "shaq", dirty, None
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = run(a)
        if rc != 1 or not buf.getvalue().rstrip().endswith("warnings"):
            fails.append("dirty file should exit 1 and end with 'lint: N warnings' (rc %d)" % rc)
        # a waiver on the flagged line turns a warning into a WAIVED line (not counted)
        with open(dirty, encoding="utf-8") as fh:
            dtext = fh.read()
        wtext = dtext.replace("- Search volume held.", "- Search volume held. %%lint-ok no-date-range: fixture line%%")
        wtext = wtext.replace("The Sun-Mon (9/21-22) trend held.",
                              "The Sun-Mon (9/21-22) trend held. %%lint-ok weekday-mismatch: quoting the bad draft%%")
        wpath = w("%s/draft-waived.md" % day, wtext)
        wv = lint_file(root, date, "shaq", wpath)
        if len(wv.waived) != 1 or len(wv.warnings) != len(d.warnings) - 1:
            fails.append("waiver: expected 1 waived (weekday-mismatch) and one fewer warning, got %d waived, %d "
                         "warnings" % (len(wv.waived), len(wv.warnings)))
        # vendor rules, line by line: each hit, each exemption, the skipped sections, both waiver spellings
        vpath = w("%s/draft-vendor.md" % day, "\n".join(t for t, _w, _v in VENDOR_FIXTURE) + "\n")
        vd = lint_file(root, date, "shaq", vpath)
        vcases = 0
        for i, (text, want_w, want_v) in enumerate(VENDOR_FIXTURE):
            n = i + 1
            got_w = {x["rule"] for x in vd.warnings if x["line"] == n and x["rule"] in (VS, VC)}
            got_v = {x["rule"] for x in vd.waived if x["line"] == n and x["rule"] in (VS, VC)}
            if got_w != set(want_w) or got_v != set(want_v):
                fails.append("vendor line %d: want warn %s waived %s, got warn %s waived %s: %s" %
                             (n, sorted(want_w), sorted(want_v), sorted(got_w), sorted(got_v), text[:70]))
            if text.strip():
                vcases += 1
        for note in vd.notes:
            if "crashed" in note:
                fails.append(note)
        # weekday helper sanity
        s = dt.date(2026, 9, 28)
        if parse_date("9/27", s) != dt.date(2026, 9, 27) or parse_date("Sep 27", s) != dt.date(2026, 9, 27) \
                or parse_date("the 25th", s) != dt.date(2026, 9, 25) or parse_date("12/28", dt.date(2027, 1, 3)) \
                != dt.date(2026, 12, 28):
            fails.append("parse_date sanity failed")
    if fails:
        print("selftest FAILED")
        for f in fails:
            print(" - " + f)
        return 1
    print("selftest passed: clean file 0 warnings; dirty file tripped all %d rules (%d warnings); vendor fixture "
          "%d lines as expected" % (len(want), len(d.warnings), vcases))
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        return selftest()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--player", required=True, choices=list(PLAYERS) + ["all"])
    ap.add_argument("--date", required=True, help="shift date YYYY-MM-DD")
    ap.add_argument("--target-date", help="the day the numbers cover (default: the day before --date)")
    ap.add_argument("--file", help="lint this file instead of outputs/ai-team/{date}/{player}.md")
    ap.add_argument("--out", help="also write the report here (.json for JSON)")
    ap.add_argument("--root", help="vault root (default: four levels above this script)")
    return run(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())
