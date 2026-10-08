#!/usr/bin/env python3
"""Month close for the DigitalCLIQ AI night shift. Standard library only.

Every shift writes a folder outputs/ai-team/YYYY-MM-DD/ (about 2 MB and 35 notes a night). This script turns a
finished month into one summary note that stays in the vault, and moves the month's raw folders into verified
zips outside the vault, so the vault stays small and flat while the month-to-month picture stays readable.

  C = python3 .claude/skills/ai-team/scripts/month_close.py

  C due --date D            JSON {"summary_due": [...], "close_due": [...]} for the shift dated D.
                            summary_due: last month (2026-09 on) when outputs/ai-team/monthly/{M}.md is missing.
                            close_due: every month M (2026-09 on) where D is on or after the 15th of M+1 and
                            the summary is not archived yet, or M's folders still hold files that can leave.
  C summary --month M [--date D] [--out PATH]
                            write outputs/ai-team/monthly/{M}.md: status draft until the month pack is final.
                            Never touches a day folder. An archived summary is kept (its sources left the
                            vault, so a rebuild would lose detail); --out writes a copy anywhere else.
  C plan --month M --date D [--json]
                            what close would do, without doing it: the main zip, the Semrush cache zip, the
                            files that stay in the vault (carries) and why, counts and bytes.
  C close --month M --date D [--apply] [--dry-run] [--force-early]
                            a dry run unless --apply (--dry-run forces one). Refuses (exit 2) before the 15th of
                            M+1 unless --force-early, and always when M is not a past month or is before 2026-09.
                            Months close in order: refuses (exit 2, "close YYYY-MM first") while any month from
                            2026-09 to M-1 lacks archived: true in its summary, because close reaches back to
                            2026-09-01 and would sweep that month's folders into M's zip.
                            With --apply, on the first close of M: ledgers.py month --month M --final and
                            ledgers.py vendor month-end --month M (same --root), then the final summary. Then the
                            zips, verified, then the originals that are not carries are removed, then the summary's
                            "Where the raw files went" is rewritten and archived: true is set. An archived month
                            with nothing left to move is a one-line no-op; a re-run after a partial failure picks
                            up what is left (files already in a verified zip are not zipped twice).
  C selftest                temp fixture vault; never calls the real ledgers.py; touches nothing real.

Global flags (before the subcommand): --root VAULT (default: the vault this script sits in) and
--archive-root DIR (default: $DIGITALCLIQ_ARCHIVE_ROOT, else ~/Desktop/DigitalCLIQ Vault Archive). The archive
root must sit outside the vault and outside ~/Library/CloudStorage.

What leaves at the close of month M: every day folder outputs/ai-team/YYYY-MM-DD/ dated 2026-09-01 to the last day
of M, and the dated folders in outputs/ai-team/vendor-dash/, cars-sbmw/ and gm-notes/ in the same range. Semrush raw
files (data/semrush_*, data/seo_join_*.json, data/value_line.json) go into their own ai-team-{M}-semrush-cache.zip,
pending Drew's ruling on Semrush ToS 3.3 (30-day cache limit). Never anything before 2026-09 (the team started
2026-09-19).

Carries stay in the vault even inside an archived folder (they are also stored in the zip):
  cars_watch.py find_prior     newest data/cars_{STORE}/summary.json with status ok, per store (unbounded glob)
  dash_check.py prior_file     newest data/dashboards.json (unbounded)
  vendor_dash.py saved_ga4     newest valid data/vendor_ppc_ga4_{STORE}.json by shift_date, per store (unbounded)
  vendor_dash.py Hist          per source: the newest vendor-dash/{D}/{source}.json, and the newest one holding an ok
                               read of each window (last_ok and the month-to-date chain look back without limit)
  vendor_dash.py sheet_compare per source: the newest vendor-dash/{D}/{source}.sheet.json
  vault notes                  any file a note links to with a [[wikilink]] or a [markdown](link) (notes in .claude,
                               dot folders, the day folders themselves and outputs/ai-team/monthly/ are not scanned);
                               plain text and backtick mentions are only counted and reported
Each later close re-checks earlier carries: a superseded carry leaves then. It is already in a zip, so it is removed
once that zip's sha256 and the member's sha256 check out, with no second copy made.

Archive layout: {archive root}/{YYYY-MM}/{name}.zip, {name}.manifest.json, ai-team-{M}.close-log.json, and
{archive root}/INDEX.md with one section per zip. Zip members are vault-relative paths, so
unzip -o ZIP -d VAULT puts every file back where it was.

Safe removal: regular files only (symlinks are skipped and reported, never followed, and so is a dated folder whose
path runs through a symlinked folder such as a linked vendor-dash/); sha256, size and mtime per
file; the zip is written to {name}.zip.partial, closed and renamed (an existing zip is never overwritten: -2, -3);
then reopened: testzip clean, every file present exactly once, the sha256 of every member matches. The manifest
(with the zip's own sha256) and the INDEX section are written, and only then are originals removed one at a time,
each re-checked for size and mtime first (a file that changed since it was hashed stays and is reported), then
folders left empty, bottom up. Any failure before removal (the INDEX append included) leaves every original in place
and deletes the new zips, their manifests and any INDEX text this run added.

Laws: never em or en dashes in anything written (replaced on write); never a file in the vault root; never touches
~/Library/CloudStorage.
"""
import argparse
import collections
import contextlib
import datetime as dt
import glob
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.parse
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
ROOT = DEFAULT_ROOT
DEFAULT_ARCHIVE = os.path.join(os.path.expanduser("~"), "Desktop", "DigitalCLIQ Vault Archive")
ARCHIVE = None  # set by main() or the selftest
EMDASH, ENDASH = chr(8212), chr(8211)  # written as chr() so this file never holds one

FIRST_MONTH = "2026-09"     # the team started 2026-09-19; never act on an earlier month
WEEKDAY_FROM = "2026-09-21"  # first scheduled weeknight shift
SATURDAY_FROM = "2026-10-03"  # Saturday shifts (the weekly wrap) from here
CLOSE_DAY = 15              # a month closes on the first shift on or after the 15th of the next month
SIDE_PILES = ("vendor-dash", "cars-sbmw", "gm-notes")
STORES = ("SBMW", "NCBMW", "NOI", "MCP", "ATLAS")
STORE_NAMES = {"SBMW": "Sterling BMW", "NCBMW": "New Century BMW", "NOI": "Nissan of Irvine",
               "MCP": "McPeek Dodge Chrysler Jeep Ram of Anaheim", "ATLAS": "Atlas Shippers International"}
PLAYERS = ("kobe", "shaq", "luka", "worthy", "nick")
SCHEMA = "ai-team-month-close.v1"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SOURCE_RE = re.compile(r"^outputs/ai-team/(?:(?:vendor-dash|cars-sbmw|gm-notes)/)?(\d{4}-\d{2}-\d{2})(?:/|$)")
TS_RE = re.compile(r"\b(1\d{9}\.\d{6})\b")
ASK_RE = re.compile(r"\bA[1-9]\d{0,2}\b(?!-)")
HM = r"(\d{1,2}:\d{2})"
NUMWORDS = {"no": 0, "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
            "eight": 8, "nine": 9, "ten": 10}

PACK_STEP = None    # the selftest replaces the ledgers.py pack step with a stub
AFTER_WRITE = None  # the selftest hook: called with each new zip's path before it is verified


class ArchiveError(Exception):
    pass


# ---------------------------------------------------------------- basics

def die(msg, code=1):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(code)


def AI(*parts):
    return os.path.join(ROOT, "outputs", "ai-team", *parts)


def LP(name):
    return AI("ledgers", name)


def summary_path(month):
    return AI("monthly", "%s.md" % month)


def rel(path):
    try:
        r = os.path.relpath(path, ROOT)
    except ValueError:
        return path
    return r.replace(os.sep, "/")


def scrub(s):
    """Never em or en dashes (Rule 14)."""
    if isinstance(s, str):
        s = re.sub(r"\s*" + EMDASH + r"\s*", " - ", s)
        s = re.sub(r"(\S)" + ENDASH + r"(\S)", r"\1-\2", s)
        return s.replace(ENDASH, "-")
    if isinstance(s, list):
        return [scrub(x) for x in s]
    if isinstance(s, dict):
        return {k: scrub(v) for k, v in s.items()}
    return s


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError):
        return default


def read_text(path):
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(scrub(text))
    os.replace(tmp, path)


def write_json(path, data):
    write_text(path, json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def iso(s, what="--date"):
    try:
        return dt.date.fromisoformat(str(s)).isoformat()
    except ValueError:
        die("%s must be YYYY-MM-DD, got %r" % (what, s), 2)


def month_arg(s):
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", str(s or "")):
        die("--month must be YYYY-MM, got %r" % s, 2)
    return s


def next_month(m):
    y, mo = int(m[:4]), int(m[5:7])
    return "%04d-%02d" % (y + (mo == 12), mo % 12 + 1)


def prev_month(m):
    y, mo = int(m[:4]), int(m[5:7])
    return "%04d-%02d" % (y - (mo == 1), 12 if mo == 1 else mo - 1)


def month_end(m):
    return (dt.date.fromisoformat(next_month(m) + "-01") - dt.timedelta(days=1)).isoformat()


def close_from(m):
    return "%s-%02d" % (next_month(m), CLOSE_DAY)


def months_between(a, b):
    out, m = [], a
    while m <= b:
        out.append(m)
        m = next_month(m)
    return out


def month_label(m):
    return dt.date(int(m[:4]), int(m[5:7]), 1).strftime("%B %Y")


def lab(d):
    x = dt.date.fromisoformat(d)
    return "%s %d/%d" % (x.strftime("%a"), x.month, x.day)


def md(d):
    x = dt.date.fromisoformat(d)
    return "%d/%d" % (x.month, x.day)


def pacific_now():
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("America/Los_Angeles"))
    except Exception:  # no tz database: US rules since 2007
        utc = dt.datetime.now(dt.timezone.utc)
        y = utc.year
        mar = dt.datetime(y, 3, 8, 10, tzinfo=dt.timezone.utc)
        start = mar + dt.timedelta(days=(6 - mar.weekday()) % 7)
        nov = dt.datetime(y, 11, 1, 9, tzinfo=dt.timezone.utc)
        end = nov + dt.timedelta(days=(6 - nov.weekday()) % 7)
        dst = start <= utc < end
        return utc.astimezone(dt.timezone(dt.timedelta(hours=-7 if dst else -8), "PDT" if dst else "PST"))


def stamp():
    now = pacific_now()
    return now.isoformat(timespec="seconds"), "%s %s" % (now.strftime("%Y-%m-%d %H:%M"), now.tzname() or "PT")


def fnum(v):
    if v is None or isinstance(v, bool):
        return "n/a"
    if isinstance(v, float) and not v.is_integer():
        return format(round(v, 2), ",")
    try:
        return format(int(v), ",")
    except (TypeError, ValueError):
        return str(v)


def fmoney(v):
    if v is None or isinstance(v, bool):
        return "n/a"
    try:
        return "$" + format(round(float(v), 2), ",.2f").replace(".00", "")
    except (TypeError, ValueError):
        return str(v)


def fbytes(n):
    n = n or 0
    if n >= 1000000:
        return "%.1f MB" % (n / 1e6)
    if n >= 1000:
        return "%.0f KB" % (n / 1e3)
    return "%d B" % n


def pct(a, b):
    if a is None or not b:
        return ""
    return " (%+.1f%%)" % ((a - b) / float(b) * 100)


def cell(s):
    return str(s).replace("|", "\\|")


def stop(s):
    """End a sentence with one stop, never '..' or '?.'."""
    s = str(s).rstrip()
    return s if s.endswith((".", "?", "!")) else s + "."


def store_link(s):
    s = str(s or "")
    if s.upper() == "ATLAS":
        return "[[Atlas]]"
    if s.upper() in STORES:
        return "[[%s]]" % s.upper()
    if s.upper() == "ALL":
        return "all stores"
    return s


def truthy(v):
    return str(v or "").strip().lower() in ("true", "yes", "1")


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def shell_path(p):
    home = os.path.expanduser("~")
    if p.startswith(home + os.sep):
        return '"$HOME/%s"' % p[len(home) + 1:]
    return '"%s"' % p


def tilde(p):
    home = os.path.expanduser("~")
    return "~" + p[len(home):] if p.startswith(home + os.sep) else p


def inside(path, root):
    rp, rr = os.path.realpath(path), os.path.realpath(root)
    return rp == rr or rp.startswith(rr + os.sep)


def linked_path(path):
    """True when the path or a folder on its way down from the vault root is a symlink, so its real place is not
    where the vault says it is (outputs/ai-team/vendor-dash pointing outside the vault, say)."""
    r = rel(path)
    if r in (".", "") or r.startswith("../") or os.path.isabs(r):
        return True
    return os.path.realpath(path) != os.path.normpath(os.path.join(os.path.realpath(ROOT), *r.split("/")))


def check_archive_root():
    """The archive root must sit outside the vault and outside ~/Library/CloudStorage (a Drive dialog froze a shift)."""
    if inside(ARCHIVE, ROOT):
        die("the archive root %s is inside the vault; it must sit outside it (default %s)" % (ARCHIVE, DEFAULT_ARCHIVE), 2)
    if inside(ARCHIVE, os.path.expanduser("~/Library/CloudStorage")):
        die("the archive root %s is under ~/Library/CloudStorage; never touch it (2026-10-06 freeze)" % ARCHIVE, 2)


def read_frontmatter(path):
    m = re.match(r"^---\n(.*?)\n---\n", read_text(path), re.S)
    out = {}
    if m:
        for line in m.group(1).splitlines():
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


# ---------------------------------------------------------------- folders, files, carries

def dated_dirs(base):
    try:
        names = os.listdir(base)
    except OSError:
        return []
    return sorted(n for n in names if DATE_RE.match(n) and os.path.isdir(os.path.join(base, n)))


def day_folders():
    return dated_dirs(AI())


def source_roots(lo, hi):
    """Absolute paths of every dated folder from lo to hi: day folders first, then the side piles."""
    out = [AI(d) for d in day_folders() if lo <= d <= hi]
    for pile in SIDE_PILES:
        out += [AI(pile, d) for d in dated_dirs(AI(pile)) if lo <= d <= hi]
    return out


def close_roots(month):
    return source_roots(FIRST_MONTH + "-01", month_end(month))


def month_roots(month):
    return source_roots(month + "-01", month_end(month))


def collect(roots):
    """Regular files under the roots, never following a symlink. Symlinks and odd files are skipped and reported."""
    files, skipped = [], []
    for root in roots:
        if os.path.islink(root):
            skipped.append({"path": rel(root) + "/", "reason": "symlinked folder, not followed"})
            continue
        if linked_path(root):
            skipped.append({"path": rel(root) + "/", "reason": "a folder on its path is a symlink, not followed"})
            continue
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            for dn in list(dirnames):
                if os.path.islink(os.path.join(dirpath, dn)):
                    skipped.append({"path": rel(os.path.join(dirpath, dn)) + "/", "reason": "symlinked folder, not followed"})
                    dirnames.remove(dn)
            dirnames.sort()
            for fn in sorted(filenames):
                ap = os.path.join(dirpath, fn)
                try:
                    st = os.lstat(ap)
                except OSError as e:
                    skipped.append({"path": rel(ap), "reason": "cannot stat (%s)" % e.strerror})
                    continue
                if stat.S_ISLNK(st.st_mode):
                    skipped.append({"path": rel(ap), "reason": "symlink, skipped and left in place"})
                    continue
                if not stat.S_ISREG(st.st_mode):
                    skipped.append({"path": rel(ap), "reason": "not a regular file, left in place"})
                    continue
                files.append({"abs": os.path.normpath(ap), "path": rel(ap), "root": rel(root) + "/",
                              "size": st.st_size, "mtime": st.st_mtime, "mtime_ns": st.st_mtime_ns})
    return files, skipped


def is_semrush(path):
    if "/data/" not in "/" + path:
        return False
    b = path.rsplit("/", 1)[-1]
    return b.startswith("semrush_") or (b.startswith("seo_join_") and b.endswith(".json")) or b == "value_line.json"


def _add(out, path, why):
    out.setdefault(os.path.normpath(path), []).append(why)


def carries_cars(out):
    """cars_watch.py find_prior: newest summary.json with status ok per store, across every day folder."""
    by_store = {}
    for p in glob.glob(os.path.join(glob.escape(AI()), "*", "data", "cars_*", "summary.json")):
        parts = p.split(os.sep)
        if DATE_RE.match(parts[-4]):
            by_store.setdefault(parts[-2][5:], []).append((parts[-4], p))
    for store, rows in sorted(by_store.items()):
        for d, p in sorted(rows, reverse=True):
            blob = load_json(p)
            if isinstance(blob, dict) and blob.get("status") == "ok":
                _add(out, p, "cars_watch.py diffs %s's next run against its newest ok CARS summary (%s)" % (store, d))
                break


def carries_dash(out):
    """dash_check.py prior_file: the newest day folder with data/dashboards.json."""
    best = None
    for d in day_folders():
        p = AI(d, "data", "dashboards.json")
        if os.path.isfile(p):
            best = (d, p)
    if best:
        _add(out, best[1], "dash_check.py carries first_seen forward from the newest dashboards.json (%s)" % best[0])


def carries_vendor_ga4(out):
    """vendor_dash.py saved_ga4: the newest valid vendor_ppc_ga4_{STORE}.json by its shift_date, per store."""
    best = {}
    for p in sorted(glob.glob(os.path.join(glob.escape(AI()), "*", "data", "vendor_ppc_ga4_*.json"))):
        store = os.path.basename(p)[len("vendor_ppc_ga4_"):-len(".json")]
        d = load_json(p)
        if not isinstance(d, dict) or not isinstance(d.get("rows"), list) or not d.get("request"):
            continue
        sd = str(d.get("shift_date") or "")
        if sd and (store not in best or sd > best[store][0]):
            best[store] = (sd, p)
    for store, (sd, p) in sorted(best.items()):
        _add(out, p, "vendor_dash.py falls back to the newest saved GA4 read for %s (%s) when tonight's pull fails" % (store, sd))


def carries_vendor_dash(out):
    """vendor_dash.py Hist, last_ok, the month-to-date chain and sheet_compare look back without a limit."""
    base = AI("vendor-dash")
    snaps, sheets = {}, {}
    for d in dated_dirs(base):
        try:
            names = sorted(os.listdir(os.path.join(base, d)))
        except OSError:
            continue
        for fn in names:
            p = os.path.join(base, d, fn)
            if not os.path.isfile(p):
                continue
            if fn.endswith(".sheet.json"):
                sheets.setdefault(fn[:-len(".sheet.json")], []).append((d, p))
            elif fn.endswith(".json"):
                snaps.setdefault(fn[:-len(".json")], []).append((d, p))
    for sid, rows in sorted(snaps.items()):
        d, p = rows[-1]
        _add(out, p, "vendor_dash.py history: newest %s snapshot (%s)" % (sid, d))
        newest = {}
        for d, p in rows:
            blob = load_json(p)
            wins = blob.get("windows") if isinstance(blob, dict) else None
            for w, x in (wins or {}).items():
                if isinstance(x, dict) and x.get("status") == "ok":
                    newest[w] = (d, p)
        for w, (d, p) in sorted(newest.items()):
            _add(out, p, "vendor_dash.py last good %s read for %s (%s)" % (w, sid, d))
    for sid, rows in sorted(sheets.items()):
        d, p = rows[-1]
        _add(out, p, "vendor_dash.py compares tonight's sheet with the newest %s sheet snapshot (%s)" % (sid, d))


WIKI_RE = re.compile(r"!?\[\[([^\[\]\n]+?)\]\]")
MDLINK_RE = re.compile(r"!?\[[^\]\n]*\]\(\s*(<[^>\n]+>|[^)\s]+)(?:\s+\"[^\"\n]*\")?\s*\)")
MENTION_RE = re.compile(r"outputs/ai-team/(?:(?:vendor-dash|cars-sbmw|gm-notes)/)?\d{4}-\d{2}-\d{2}\b")


def note_files():
    """Every .md note outside dot folders (.claude, .obsidian, .git, .trash), the dated archive sources and monthly/."""
    for dirpath, dirnames, filenames in os.walk(ROOT, followlinks=False):
        here = rel(dirpath)
        keep = []
        for d in sorted(dirnames):
            p = d if here in (".", "") else here + "/" + d
            if d.startswith(".") or p == "outputs/ai-team/monthly" or SOURCE_RE.match(p + "/"):
                continue
            keep.append(d)
        dirnames[:] = keep
        for fn in sorted(filenames):
            if fn.endswith(".md"):
                yield os.path.join(dirpath, fn)


def resolve_link(target, note):
    t = urllib.parse.unquote(target.strip().strip("<>"))
    t = t.split("|", 1)[0].split("#", 1)[0].strip()
    if not t or "://" in t or t.startswith(("mailto:", "obsidian:")):
        return None, None
    cands = [os.path.join(ROOT, t.lstrip("/"))] if t.startswith("/") else [os.path.join(ROOT, t),
                                                                          os.path.join(os.path.dirname(note), t)]
    for c in cands:
        c = os.path.normpath(c)
        if not inside(c, ROOT):
            continue
        for x in (c, c + ".md"):
            if os.path.isfile(x) and not os.path.islink(x):
                return x, "file"
        if os.path.isdir(c):
            return c, "folder"
    return None, None


def scan_links(out):
    """Wikilinks and markdown links from vault notes into the dated archive sources. Returns the scan stats."""
    stats = {"notes": 0, "wikilinks": 0, "mdlinks": 0, "folder_links": [], "mentions": 0,
             "mention_notes": collections.Counter()}
    for note in note_files():
        text = read_text(note)
        if "outputs/ai-team/" not in text:
            continue
        stats["notes"] += 1
        spans = []
        for rx, kind in ((WIKI_RE, "wikilinks"), (MDLINK_RE, "mdlinks")):
            for m in rx.finditer(text):
                if "outputs/ai-team/" not in m.group(1):
                    continue
                spans.append((m.start(), m.end()))
                path, what = resolve_link(m.group(1), note)
                if not path or not SOURCE_RE.match(rel(path) + ("/" if what == "folder" else "")):
                    continue
                stats[kind] += 1
                if what == "folder":
                    stats["folder_links"].append("%s -> %s/" % (rel(note), rel(path)))
                else:
                    _add(out, path, "linked from %s" % rel(note))
        for m in MENTION_RE.finditer(text):
            if not any(a <= m.start() < b for a, b in spans):
                stats["mentions"] += 1
                stats["mention_notes"][rel(note)] += 1
    return stats


_CARRY_CACHE = {}


def all_carries():
    """{absolute path: [reasons]} for every carry in the vault right now, plus the link scan stats."""
    if ROOT not in _CARRY_CACHE:
        out = {}
        carries_cars(out)
        carries_dash(out)
        carries_vendor_ga4(out)
        carries_vendor_dash(out)
        stats = scan_links(out)
        _CARRY_CACHE[ROOT] = (out, stats)
    return _CARRY_CACHE[ROOT]


# ---------------------------------------------------------------- archive index (manifests already written)

def manifests(month=None):
    out = []
    for p in glob.glob(os.path.join(glob.escape(ARCHIVE), "*", "ai-team-*.manifest.json")):
        m = load_json(p)
        if not isinstance(m, dict) or m.get("schema") != SCHEMA:
            continue
        if os.path.realpath(m.get("vault_root") or "") != os.path.realpath(ROOT):
            continue
        if month and m.get("month") != month:
            continue
        m["_path"] = p
        m["_zip"] = os.path.join(os.path.dirname(p), m.get("zip") or "")
        out.append(m)
    return sorted(out, key=lambda m: (m.get("created") or "", m.get("kind") != "main", m["_path"]))


def archived_files():
    """{vault path: (manifest entry, manifest)} for files stored in a zip that still exists; newest zip wins."""
    known = {}
    for m in manifests():
        if os.path.isfile(m["_zip"]):
            for e in m.get("files") or []:
                known[e["path"]] = (e, m)
    return known


def month_of(path):
    """YYYY-MM of a dated archive source path (outputs/ai-team/[pile/]YYYY-MM-DD/...), else None."""
    m = SOURCE_RE.match(path or "")
    return m.group(1)[:7] if m else None


def foreign_zips(month):
    """[(manifest, entries)] for zips of OTHER months that still exist and hold files dated in this month: an older
    close swept them up before this month was closed. Those files are archived; this month's own close must not
    rebuild its pack or summary from what is left, or say nothing was archived."""
    out = []
    for m in manifests():
        if m.get("month") == month or not os.path.isfile(m["_zip"]):
            continue
        mine = [e for e in m.get("files") or [] if month_of(e.get("path")) == month]
        if mine:
            out.append((m, mine))
    return out


def taken_line(month, taken):
    return "%s file(s) dated in %s are already in %s (a later close took them from the vault)" % (
        fnum(sum(len(es) for _m, es in taken)), month_label(month), ", ".join(m["zip"] for m, _es in taken))


def unarchived_before(month):
    """The first month from FIRST_MONTH up to the month before this one whose summary is not archived: true."""
    for m in months_between(FIRST_MONTH, prev_month(month)):
        if not truthy(read_frontmatter(summary_path(m)).get("archived")):
            return m
    return None


# ---------------------------------------------------------------- plan

def build_plan(month, roots):
    files, skipped = collect(roots)
    car, stats = all_carries()
    known = archived_files()
    roots = [r for r in roots if not os.path.islink(r) and not linked_path(r)]  # skipped above, never a source path
    plan = {"month": month, "roots": [rel(r) + "/" for r in roots], "main": [], "semrush": [], "reuse": [],
            "carry": [], "skipped": skipped, "links": stats, "files": files}
    for f in files:
        reasons = car.get(f["abs"])
        f["carry"] = "; ".join(reasons) if reasons else None
        f["group"] = "semrush" if is_semrush(f["path"]) else "main"
        prior = known.get(f["path"])
        stored = bool(prior and prior[0].get("size") == f["size"] and prior[0].get("mtime_ns") == f["mtime_ns"])
        if stored:
            f["prior"] = prior
        if f["carry"]:
            plan["carry"].append(f)
            if not stored:
                plan[f["group"]].append(f)
        elif stored:
            plan["reuse"].append(f)
        else:
            plan[f["group"]].append(f)
    return plan


def removable(plan):
    return [f for f in plan["main"] + plan["semrush"] if not f["carry"]] + plan["reuse"]


def zip_base(month, kind):
    return "ai-team-%s" % month if kind == "main" else "ai-team-%s-semrush-cache" % month


def plan_lines(plan, date):
    month = plan["month"]
    L = []
    allowed = date >= close_from(month)
    L.append("plan %s, date %s: close %s from %s." % (month, date, "allowed" if allowed else "NOT allowed until",
                                                      close_from(month)))
    behind = unarchived_before(month)
    if behind:
        L.append("  close refused until %s is closed (its summary is not archived: true); months close in order." % behind)
    days = [r for r in plan["roots"] if SOURCE_RE.match(r) and r.count("/") == 3]
    piles = collections.Counter(r.split("/")[2] for r in plan["roots"] if r not in days)
    L.append("  sources: %d day folder(s)%s%s" % (
        len(days), " (%s to %s)" % (days[0].split("/")[2], days[-1].split("/")[2]) if days else "",
        "".join(", %s %d" % (k, v) for k, v in sorted(piles.items()))))
    for grp, label in (("main", "main zip"), ("semrush", "Semrush cache zip")):
        lst = plan[grp]
        note = " (pending Drew's ruling on Semrush ToS 3.3)" if grp == "semrush" else ""
        L.append("  %s %s.zip: %d file(s), %s%s%s" % (
            label, zip_base(month, "main" if grp == "main" else "semrush"), len(lst), fbytes(sum(f["size"] for f in lst)),
            ", %d of them carries" % sum(1 for f in lst if f["carry"]) if any(f["carry"] for f in lst) else "", note))
    if plan["reuse"]:
        L.append("  already in a verified zip, removed after re-checking that copy: %d file(s), %s"
                 % (len(plan["reuse"]), fbytes(sum(f["size"] for f in plan["reuse"]))))
    rem = removable(plan)
    L.append("  leave the vault after the zips verify: %d file(s), %s" % (len(rem), fbytes(sum(f["size"] for f in rem))))
    L.append("  carries that stay in the vault (also stored in a zip): %d" % len(plan["carry"]))
    for f in plan["carry"]:
        L.append("    %s: %s" % (f["path"], f["carry"]))
    if plan["skipped"]:
        L.append("  skipped and left in place: %d" % len(plan["skipped"]))
        for s in plan["skipped"][:20]:
            L.append("    %s (%s)" % (s["path"], s["reason"]))
    else:
        L.append("  skipped: none (no symlinks or odd files)")
    per = collections.OrderedDict()
    for f in plan["files"]:
        k = f["root"]
        c = per.setdefault(k, {"n": 0, "b": 0, "sem": 0, "carry": 0})
        c["n"] += 1
        c["b"] += f["size"]
        c["sem"] += f["group"] == "semrush"
        c["carry"] += bool(f["carry"])
    if per:
        L.append("  per folder:")
        for k, c in per.items():
            L.append("    %s %d file(s), %s (%d Semrush, %d carr%s)" % (k, c["n"], fbytes(c["b"]), c["sem"], c["carry"],
                                                                        "y" if c["carry"] == 1 else "ies"))
    st = plan["links"]
    L.append("  links from notes into dated folders: %d wikilink(s), %d markdown link(s)%s; plain mentions (not kept, "
             "listed only): %d in %d note(s)%s" % (
                 st["wikilinks"], st["mdlinks"], ", %d to folders (not kept)" % len(st["folder_links"]) if st["folder_links"] else "",
                 st["mentions"], len(st["mention_notes"]),
                 " (most: %s)" % ", ".join("%s %d" % kv for kv in st["mention_notes"].most_common(3)) if st["mentions"] else ""))
    L.append("  archive root: %s" % ARCHIVE)
    return L


def plan_json(plan, date):
    rem = removable(plan)
    behind = unarchived_before(plan["month"])
    return {"month": plan["month"], "date": date, "close_allowed": date >= close_from(plan["month"]) and not behind,
            "close_from": close_from(plan["month"]), "close_first": behind, "archive_root": ARCHIVE, "sources": plan["roots"],
            "main": {"files": len(plan["main"]), "bytes": sum(f["size"] for f in plan["main"])},
            "semrush": {"files": len(plan["semrush"]), "bytes": sum(f["size"] for f in plan["semrush"])},
            "reuse": [f["path"] for f in plan["reuse"]],
            "remove": {"files": len(rem), "bytes": sum(f["size"] for f in rem)},
            "carries": [{"path": f["path"], "why": f["carry"]} for f in plan["carry"]],
            "skipped": plan["skipped"],
            "links": {k: (v if not isinstance(v, collections.Counter) else dict(v)) for k, v in plan["links"].items()}}


# ---------------------------------------------------------------- zips

def unique_name(dest, base):
    name, i = base, 2
    while any(os.path.exists(os.path.join(dest, name + ext)) for ext in (".zip", ".manifest.json")):
        name = "%s-%d" % (base, i)
        i += 1
    return name


def zip_time(mtime):
    t = dt.datetime.fromtimestamp(max(mtime, 315532800))  # zip dates start in 1980
    return (t.year, t.month, t.day, t.hour, t.minute, t.second)


def write_zip(dest, base, files):
    """Write the files to {name}.zip.partial, hashing each one while it is copied; rename when closed."""
    os.makedirs(dest, exist_ok=True)
    name = unique_name(dest, base)
    final = os.path.join(dest, name + ".zip")
    partial = final + ".partial"
    if os.path.exists(partial):
        os.remove(partial)  # left by an earlier crash; it is ours and was never verified
    entries = []
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for f in files:
            st = os.lstat(f["abs"])
            if not stat.S_ISREG(st.st_mode):
                raise ArchiveError("%s is no longer a regular file" % f["path"])
            zi = zipfile.ZipInfo(f["path"], date_time=zip_time(st.st_mtime))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = (st.st_mode & 0xFFFF) << 16
            h, n = hashlib.sha256(), 0
            with open(f["abs"], "rb") as src, zf.open(zi, "w", force_zip64=st.st_size > (1 << 30)) as dst:
                for chunk in iter(lambda: src.read(1 << 20), b""):
                    h.update(chunk)
                    dst.write(chunk)
                    n += len(chunk)
            after = os.lstat(f["abs"])
            changed = n != st.st_size or after.st_mtime_ns != st.st_mtime_ns or after.st_size != st.st_size
            f["size"], f["mtime"], f["mtime_ns"] = st.st_size, st.st_mtime, st.st_mtime_ns
            f["changed"] = changed
            entries.append({"path": f["path"], "size": n, "mtime": st.st_mtime, "mtime_ns": st.st_mtime_ns,
                            "sha256": h.hexdigest(), "carry": f["carry"],
                            "changed_while_reading": changed or None})
    if os.path.exists(final):
        os.remove(partial)
        raise ArchiveError("%s appeared while it was being written; nothing was overwritten" % os.path.basename(final))
    os.replace(partial, final)
    return {"name": name, "path": final, "entries": entries}


def verify_zip(path, entries):
    """None when the zip reads back clean with every file once and every sha256 matching, else the problem."""
    try:
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            if bad is not None:
                return "testzip found a bad member: %s" % bad
            counts = collections.Counter(zf.namelist())
            dup = sorted(n for n, c in counts.items() if c > 1)
            want = {e["path"] for e in entries}
            missing = sorted(want - set(counts))
            extra = sorted(set(counts) - want)
            if dup or missing or extra:
                return "member list does not match (%d duplicate, %d missing, %d extra)" % (len(dup), len(missing), len(extra))
            for e in entries:
                h, n = hashlib.sha256(), 0
                with zf.open(e["path"]) as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h.update(chunk)
                        n += len(chunk)
                if h.hexdigest() != e["sha256"] or n != e["size"]:
                    return "sha256 or size mismatch for %s" % e["path"]
    except Exception as e:  # a corrupt zip raises zlib, BadZipFile or EOF errors
        return "%s: %s" % (type(e).__name__, e)
    return None


def verify_reuse(files):
    """A file already stored in an earlier zip leaves only when that zip still has the sha256 its manifest recorded,
    its member reads back with the file's sha256, and the file itself still hashes the same."""
    ok, redo, zcache = [], [], {}
    for f in files:
        e, m = f["prior"]
        why = None
        try:
            if m["_zip"] not in zcache:
                zcache[m["_zip"]] = sha_file(m["_zip"])
            if zcache[m["_zip"]] != m.get("zip_sha256"):
                why = "%s changed since it was verified" % os.path.basename(m["_zip"])
            else:
                with zipfile.ZipFile(m["_zip"]) as zf:
                    h = hashlib.sha256()
                    with zf.open(e["path"]) as fh:
                        for chunk in iter(lambda: fh.read(1 << 20), b""):
                            h.update(chunk)
                if h.hexdigest() != e["sha256"]:
                    why = "the copy in %s does not match its manifest" % os.path.basename(m["_zip"])
                elif sha_file(f["abs"]) != e["sha256"]:
                    why = "the file no longer matches the copy in %s" % os.path.basename(m["_zip"])
        except Exception as ex:
            why = "could not re-check %s (%s)" % (os.path.basename(m["_zip"]), ex)
        if why:
            f["redo_reason"] = why
            redo.append(f)
        else:
            f["stored_in"] = os.path.basename(m["_zip"])
            ok.append(f)
    return ok, redo


def remove_files(files, roots):
    """Remove one file at a time after re-checking size and mtime. Returns (removed, kept, errors). A file whose real
    place is not its vault path (a symlinked folder on the way) or not under a declared folder is kept."""
    rroots = [os.path.realpath(r) for r in roots if not linked_path(r)]
    removed, kept, errors = [], [], []
    for f in files:
        ap = f["abs"]
        if linked_path(ap) or os.path.normpath(ap) != os.path.normpath(os.path.join(ROOT, *f["path"].split("/"))):
            kept.append("%s (a folder on its path is a symlink, kept)" % f["path"])
            continue
        try:
            st = os.lstat(ap)
        except FileNotFoundError:
            removed.append(f["path"])  # already gone (an earlier partial run)
            continue
        except OSError as e:
            errors.append("%s: %s" % (f["path"], e.strerror))
            continue
        if not stat.S_ISREG(st.st_mode) or st.st_size != f["size"] or st.st_mtime_ns != f["mtime_ns"] or f.get("changed"):
            kept.append("%s (changed since it was hashed, kept)" % f["path"])
            continue
        if not any(os.path.realpath(ap).startswith(r + os.sep) for r in rroots):
            kept.append("%s (outside the declared folders, kept)" % f["path"])
            continue
        try:
            os.remove(ap)
            removed.append(f["path"])
        except OSError as e:
            errors.append("%s: %s" % (f["path"], e.strerror))
    return removed, kept, errors


def remove_empty_dirs(roots):
    n = 0
    for root in roots:
        if os.path.islink(root) or linked_path(root) or not os.path.isdir(root):
            continue
        for dirpath, _dirs, _files in os.walk(root, topdown=False, followlinks=False):
            if os.path.islink(dirpath) or linked_path(dirpath):
                continue
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
                    n += 1
            except OSError:
                pass  # not empty or not ours to remove: left alone
    return n


def manifest_for(kind, month, date, z, sha, nbytes, files, roots, skipped, created):
    restore = "unzip -o %s -d %s" % (shell_path(z["path"]), shell_path(ROOT))
    return {"schema": SCHEMA, "kind": kind, "month": month, "name": z["name"], "zip": z["name"] + ".zip",
            "zip_sha256": sha, "zip_bytes": nbytes, "created": created, "close_date": date,
            "vault_root": ROOT, "source_paths": roots,
            "file_count": len(z["entries"]), "bytes_before": sum(e["size"] for e in z["entries"]), "bytes_after": nbytes,
            "carries": sum(1 for e in z["entries"] if e["carry"]),
            "files": z["entries"], "skipped": skipped,
            "note": ("Semrush raw files kept apart pending Drew's ruling on Semrush ToS 3.3 (30-day cache limit); if he "
                     "rules delete, remove this zip and this manifest." if kind == "semrush-cache" else
                     "AI night-shift day folders for %s; carries are also stored here and stay in the vault." % month_label(month)),
            "restore": restore}


def index_section(man, dest):
    what = ("Semrush raw files from the %s day folders (semrush_*, seo_join_*.json, value_line.json), kept apart "
            "pending Drew's ruling on Semrush ToS 3.3 (30-day cache limit). If he rules delete, remove this zip and its "
            "manifest." % month_label(man["month"]) if man["kind"] == "semrush-cache" else
            "AI night-shift raw folders for %s: briefs, shift logs, player findings, Slack copies and data pulls, plus "
            "the dated vendor-dash, cars-sbmw and gm-notes folders." % month_label(man["month"]))
    days = sorted({p.split("/")[2] for p in man["source_paths"] if p.count("/") == 3})
    one = days[-1] if days else man["month"] + "-01"
    L = ["", "## %s" % man["zip"], "",
         "- Created: %s by month_close.py (vault %s)" % (man["created"], man["vault_root"]),
         "- What: %s" % what,
         "- Source paths: %s" % ", ".join(man["source_paths"]),
         "- Files: %d (%d of them carries that also stay in the vault)" % (man["file_count"], man["carries"]),
         "- Bytes: %s before, %s zipped" % (fnum(man["bytes_before"]), fnum(man["bytes_after"])),
         "- Zip sha256: %s" % man["zip_sha256"],
         "- Manifest: %s/%s.manifest.json" % (os.path.basename(dest), man["name"]),
         "- Restore everything: `%s`" % man["restore"],
         "- Restore one night: `unzip -o %s 'outputs/ai-team/%s/*' -d %s`" % (
             shell_path(os.path.join(dest, man["zip"])), one, shell_path(man["vault_root"])), ""]
    return "\n".join(L)


def index_mark():
    """INDEX.md's size before an append: None when it does not exist yet, -1 when it is not a regular file."""
    try:
        st = os.lstat(os.path.join(ARCHIVE, "INDEX.md"))
    except FileNotFoundError:
        return None
    except OSError:
        return -1
    return st.st_size if stat.S_ISREG(st.st_mode) else -1


def index_undo(mark):
    """Take back a failed run's INDEX sections (truncate to the size before the append, or remove a new INDEX.md)."""
    path = os.path.join(ARCHIVE, "INDEX.md")
    if mark == -1 or os.path.islink(path) or not os.path.isfile(path):
        return
    try:
        if mark is None:
            os.remove(path)
        elif os.path.getsize(path) > mark:
            with open(path, "r+b") as f:
                f.truncate(mark)
    except OSError:
        pass


def append_index(text):
    path = os.path.join(ARCHIVE, "INDEX.md")
    os.makedirs(ARCHIVE, exist_ok=True)
    head = ""
    if not os.path.exists(path):
        head = ("---\ntype: archive-index\ndate: %s\nstatus: active\ntags: [archive, index]\n---\n\n"
                "# DigitalCLIQ Vault Archive index\n\nOne section per zip, oldest first. Zip members are vault-relative "
                "paths, so `unzip -o ZIP -d VAULT` puts every file back where it was. Each zip has a manifest next to it "
                "with the sha256, size and mtime of every file.\n" % pacific_now().date().isoformat())
    with open(path, "a", encoding="utf-8") as f:
        f.write(scrub(head + text))


def archive_month(plan, month, date):
    """Zip, verify, record, then remove. Returns a result dict; result['failed'] is set when nothing was removed."""
    dest = os.path.join(ARCHIVE, month)
    roots = [os.path.join(ROOT, r.rstrip("/")) for r in plan["roots"]]
    res = {"zips": [], "removed": [], "kept": [], "errors": [], "reused": [], "redo": [], "dirs": 0, "failed": None}
    reuse_ok, redo = verify_reuse(plan["reuse"])
    for f in redo:
        plan[f["group"]].append(f)
        res["redo"].append("%s (%s; zipped again)" % (f["path"], f["redo_reason"]))
    created, built = [], []
    created_iso, _ = stamp()
    mark = False  # INDEX.md not touched yet
    try:
        for kind, grp in (("main", "main"), ("semrush-cache", "semrush")):
            files = plan[grp]
            if not files:
                continue
            z = write_zip(dest, zip_base(month, grp), files)
            created.append(z["path"])
            if AFTER_WRITE:
                AFTER_WRITE(z["path"])
            err = verify_zip(z["path"], z["entries"])
            if err:
                raise ArchiveError("%s did not verify: %s" % (os.path.basename(z["path"]), err))
            built.append((kind, z, files, sha_file(z["path"]), os.path.getsize(z["path"])))
        mans = []
        for kind, z, files, sha, nbytes in built:
            man = manifest_for(kind, month, date, z, sha, nbytes, files, plan["roots"], plan["skipped"], created_iso)
            mpath = os.path.join(dest, z["name"] + ".manifest.json")
            write_json(mpath, man)
            created.append(mpath)
            mans.append((mpath, man))
        if mans:  # protocol step 5 ends with the INDEX sections; removal never starts before they are written
            mark = index_mark()
            append_index("".join(index_section(man, dest) for _mpath, man in mans))
    except Exception as e:
        if mark is not False:
            index_undo(mark)
        for p in created:
            for x in (p, p + ".partial", p + ".tmp"):
                if os.path.exists(x):
                    os.remove(x)
        res["failed"] = "%s: %s" % (type(e).__name__, e) if not isinstance(e, ArchiveError) else str(e)
        return res
    for mpath, man in mans:
        res["zips"].append(man)
    go = [f for _k, _z, files, _s, _n in built for f in files if not f["carry"]] + reuse_ok
    removed, kept, errors = remove_files(go, roots)
    res["removed"], res["kept"], res["errors"] = removed, kept, errors
    res["reused"] = [f["path"] for f in reuse_ok if f["path"] in set(removed)]
    res["dirs"] = remove_empty_dirs(roots)
    gone = set(removed)
    for mpath, man in mans:
        mine = {e["path"] for e in man["files"]}
        man["removal"] = {"date": date, "removed": len(mine & gone),
                          "kept_carries": sum(1 for e in man["files"] if e["carry"]),
                          "kept_changed": [k for k in kept if k.split(" (")[0] in mine],
                          "errors": [x for x in errors if x.split(": ")[0] in mine]}
        write_json(mpath, man)
    log_path = os.path.join(dest, "ai-team-%s.close-log.json" % month)
    log = load_json(log_path, None) or {"schema": SCHEMA, "month": month, "runs": []}
    log["runs"].append({"date": date, "created": created_iso, "zips": [m["zip"] for m in res["zips"]],
                        "removed": len(removed), "removed_already_zipped": res["reused"],
                        "zipped_again": res["redo"], "carries_kept": [{"path": f["path"], "why": f["carry"]} for f in plan["carry"]],
                        "kept": kept, "errors": errors, "folders_removed": res["dirs"], "skipped": plan["skipped"]})
    write_json(log_path, log)
    return res


# ---------------------------------------------------------------- the month pack step (ledgers.py)

def pack_counts(pack):
    out = {}
    for s, st in ((pack or {}).get("stores") or {}).items():
        if not isinstance(st, dict):
            continue
        out[s] = tuple(((st.get(k) or {}).get("coverage") or {}).get("count") or 0 for k in ("ga4", "google_ads", "meta")) \
            + (((st.get("crm") or {}).get("coverage") or {}).get("period_end") or "",)
    return out


def pack_is_final(pack):
    return bool(pack) and (pack.get("final") is True or str(pack.get("status") or "").lower() == "final")


def run_pack_step(month):
    """ledgers.py month --month M --final, then vendor month-end, with the same --root. None when the pack is final
    or was rebuilt in this run with no source losing coverage, else the problem (nothing archived then)."""
    if PACK_STEP is not None:
        return PACK_STEP(month)
    led = os.path.join(HERE, "ledgers.py")
    if not os.path.isfile(led):
        return "ledgers.py is not next to month_close.py"
    pj, pm = LP("month-pack-%s.json" % month), LP("month-pack-%s.md" % month)
    before = {p: open(p, "rb").read() for p in (pj, pm) if os.path.exists(p)}
    old = load_json(pj)
    began = dt.datetime.now().replace(microsecond=0).isoformat()

    def run(argv):
        r = subprocess.run([sys.executable, led, "--root", ROOT] + argv, cwd=ROOT, capture_output=True, text=True,
                           timeout=900)
        for line in (r.stdout or "").strip().splitlines()[:8]:
            print("    " + line)
        return r

    r = run(["month", "--month", month, "--final"])
    if r.returncode != 0 and "unrecognized arguments" in (r.stderr or ""):
        print("    (this ledgers.py has no --final yet; ran the plain month rebuild)")
        r = run(["month", "--month", month])
    if r.returncode != 0:
        return "ledgers.py month exited %d: %s" % (r.returncode, (r.stderr or "").strip()[-300:])
    new = load_json(pj)
    if not isinstance(new, dict) or new.get("month") != month:
        return "month-pack-%s.json is missing or unreadable after the rebuild" % month
    drop = []
    oc, nc = pack_counts(old), pack_counts(new)
    for s, o in oc.items():
        n = nc.get(s)
        if n is None or any(a < b for a, b in zip(n[:3], o[:3])) or n[3] < o[3]:
            drop.append("%s %s -> %s" % (s, o, n))
    if drop:
        for p, b in before.items():
            with open(p + ".tmp", "wb") as f:
                f.write(b)
            os.replace(p + ".tmp", p)
        return "the rebuilt pack covers less than the one on file (%s); the old pack was put back" % "; ".join(drop)
    if not pack_is_final(new) and str(new.get("generated_at") or "") < began:
        return "the month pack was neither marked final nor rebuilt in this run (built %s)" % new.get("generated_at")
    r = run(["vendor", "month-end", "--month", month])
    if r.returncode != 0:
        return "ledgers.py vendor month-end exited %d: %s" % (r.returncode, (r.stderr or "").strip()[-300:])
    return None


# ---------------------------------------------------------------- parsing briefs and shift logs

SECTION_RE = re.compile(r"^(#{2,4})\s+(.+?)\s*$")
ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def strip_fm(text):
    return re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.S)


def md_sections(text):
    out, cur = {}, None
    for line in text.splitlines():
        m = SECTION_RE.match(line)
        if m:
            cur = m.group(2).strip().lower()
            out.setdefault(cur, [])
            continue
        if cur is not None:
            out[cur].append(line)
    return out


def section(secs, *names):
    for n in names:
        for k, v in secs.items():
            if k.startswith(n):
                return v
    return []


def md_items(lines):
    """List items (bullets or numbers) with their wrapped lines; a blank line ends an item."""
    items, open_item = [], False
    for line in lines:
        if ITEM_RE.match(line):
            items.append(ITEM_RE.sub("", line, count=1).strip())
            open_item = True
        elif not line.strip() or line.lstrip().startswith(("|", "#")):
            open_item = False
        elif open_item:
            items[-1] += " " + line.strip()
    return items


def first_sentence(s, cap=220):
    s = " ".join(str(s).split())
    m = re.search(r"(?<=[a-z0-9)\]%\"'*])[.!?](?=\s+[A-Z\[*\"(])", s)
    if m and m.end() >= 20:
        s = s[:m.end()]
    if len(s) > cap:
        s = s[:cap].rsplit(" ", 1)[0].rstrip(",;:") + " ..."
    return s


def bold_lead(item, cap=200):
    m = re.match(r"^\*\*(.+?)\*\*", item.strip())
    if m:
        lead = m.group(1).strip().rstrip(".:").strip()
        return lead if len(lead) <= cap else lead[:cap].rsplit(" ", 1)[0] + " ..."
    return first_sentence(item, cap)


def md_table(text, must):
    """(header, rows) of the first pipe table whose header row holds every word in must (lowercase)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.lstrip().startswith("|") and all(w in line.lower() for w in must):
            head = [c.strip() for c in line.strip().strip("|").split("|")]
            rows = []
            for nxt in lines[i + 2:]:
                if not nxt.lstrip().startswith("|"):
                    break
                rows.append([c.strip() for c in nxt.strip().strip("|").split("|")])
            return head, rows
    return None, []


def to_int(s):
    s = str(s or "").replace(",", "").strip().strip("*")
    return int(s) if re.match(r"^\d+$", s) else None


def to_min(hm):
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


def brief_tail(brief, n=8):
    lines = [x for x in brief.splitlines() if x.strip() and not x.lstrip().startswith(("|", "#"))]
    return lines[-n:]


def num_before(text, word):
    m = re.search(r"\b(\d+|%s)\s+%s\b" % ("|".join(NUMWORDS), word), text, re.I)
    if not m:
        return None
    g = m.group(1).lower()
    return int(g) if g.isdigit() else NUMWORDS[g]


def shift_times(log, brief):
    start = end = None
    catch = False
    m = (re.search(r"^\s*-\s*\**Start:?\**\s*" + HM, log, re.M) or re.search(r"Tip-off:\**\s*" + HM, log)
         or re.search(r"\bStart:?\s+" + HM, log))
    if m:
        start = m.group(1)
    ends = re.findall(r"^\s*-\s*\**End:\**\s*" + HM, log, re.M)
    if ends:
        end = ends[-1]
    else:
        m = re.search(r"\bend\s+~?" + HM, log, re.I) or re.search(r"Whistle:\**\s*" + HM, log)
        if m:
            end = m.group(1)
    tail = "\n".join(brief_tail(brief))
    m = re.search(r"Shift(?: ran|:)\s+(?:about\s+)?" + HM + r"\s+to\s+(?:about\s+)?" + HM, tail)
    if m:
        start, end = start or m.group(1), end or m.group(2)
    m = re.search(r"Shift started\s+" + HM, tail)
    if m and not start:
        start = m.group(1)
    m = (re.search(r"^\s*-\s*" + HM + r"(?:\s+[A-Z]{2,4})?\s+Catch-up", log, re.M | re.I)
         or re.search(r"Catch-up started\s+" + HM, brief, re.I))
    if m:
        start, catch = m.group(1), True
    minutes = (to_min(end) - to_min(start)) % 1440 if start and end else None
    if minutes is None:
        m = re.search(r"(\d+)\s*(?:minutes|min)\b", tail) or re.search(r"Minutes:\**\s*(\d+)", log)
        minutes = int(m.group(1)) if m else None
    return start, end, minutes, catch


def huddles_bounces(log, brief):
    h = b = None
    for line in reversed(brief_tail(brief)):
        if re.search(r"huddle", line, re.I):
            h = num_before(line, "huddles?")
            b = num_before(line, "bounces?")
            if h is not None:
                break
    if h is None or b is None:
        for line in log.splitlines():
            if h is None:
                m = re.search(r"Huddles(?: seen)?:?\**\s*\(?(\d+)", line)
                h = int(m.group(1)) if m else num_before(line, "huddles?") if "Final" in line else None
            if b is None:
                m = re.search(r"Bounces:?\**\s*(\d+)", line)
                b = int(m.group(1)) if m else None
    return h, b


def hung_state(log, brief):
    text = log + "\n" + "\n".join(brief_tail(brief))
    for m in re.finditer(r"\b(all five|all 5|\d+)\s+(?:teammates\s+|players\s+)?(?:hung|lost)\b", text, re.I):
        before = text[max(0, m.start() - 14):m.start()].lower()
        if m.group(1) != "0" and not re.search(r"\b(no|none|nobody)\b", before):
            return "yes (%s)" % " ".join(m.group(0).split())
    for m in re.finditer(r"\bfroze\b", text, re.I):
        if not re.search(r"\b(nobody|no one|none)\s*$", text[max(0, m.start() - 12):m.start()].lower()):
            return "froze"
    if re.search(r"\b(none|nobody|no player|no one)\s+(hung|froze|was stuck)\b|\bno hangs?\b", text, re.I):
        return "no"
    return "not logged"


def slack_ts(base, log):
    r = load_json(os.path.join(base, "brief-slack.json"))
    if isinstance(r, dict) and r.get("parent_ts"):
        return str(r["parent_ts"])
    for line in log.splitlines():
        if re.search(r"brief", line, re.I) and re.search(r"post|parent_ts|slack ts|headline ts|slack \d", line, re.I):
            m = TS_RE.search(line)
            if m:
                return m.group(1)
    return None


def usage_table(*texts):
    for t in texts:
        head, rows = md_table(t, ("player", "all tokens"))
        if head:
            return head, rows
    return None, []


def parse_night(day):
    base = AI(day)
    runs = sorted(p for p in glob.glob(os.path.join(glob.escape(base), "run*")) if os.path.isdir(p))
    bp = os.path.join(base, "brief.md")
    if not os.path.isfile(bp):
        alt = [os.path.join(r, "brief.md") for r in runs if os.path.isfile(os.path.join(r, "brief.md"))]
        bp = alt[-1] if alt else None
    brief = strip_fm(read_text(bp)) if bp else ""
    log = read_text(os.path.join(base, "shift-log.md"))
    secs = md_sections(brief)
    n = {"date": day, "brief": rel(bp) if bp else None, "runs": [rel(r) + "/" for r in runs],
         "has_log": bool(log)}
    n["three"] = [bold_lead(i) for i in md_items(section(secs, "the three things", "top 3"))][:3]
    ids, other = [], []
    for it in md_items(section(secs, "needs your call")):
        lead = bold_lead(it, 90)
        found = ASK_RE.findall(lead) or ASK_RE.findall(it)
        if found:
            ids += [x for x in found if x not in ids]
        else:
            other.append(lead)
    n["needs_ids"], n["needs_other"] = ids, other
    n["corrections"] = [first_sentence(i) for i in md_items(section(secs, "corrections"))]
    n["health"] = [first_sentence(i, 180) for i in md_items(section(secs, "measurement health"))]
    wr = [ITEM_RE.sub("", x, count=1).strip() for x in section(secs, "week in review")
          if x.strip() and not x.lstrip().startswith(("|", "#"))]
    n["week_review"] = [first_sentence(x, 200) for x in wr][:8]  # store paragraphs or bullets, one line each
    title = (log.splitlines() or [""])[0] if not log.startswith("---") else next(
        (x for x in log.splitlines() if x.startswith("#")), "")
    n["mode"] = "dry run" if (re.search(r"\(dry-run", title) or re.search(r"^\s*-?\s*\**Mode:?\**\s*`?dry-run", log, re.M)
                              or re.search(r"Mode: dry-run", brief[:800])) else "shift"
    n["start"], n["end"], n["minutes"], n["catch_up"] = shift_times(log, brief)
    n["huddles"], n["bounces"] = huddles_bounces(log, brief)
    n["hung"] = hung_state(log, brief)
    n["slack_ts"] = slack_ts(base, log)
    head, rows = usage_table("\n".join(section(secs, "shift stats")), log,
                             read_text(os.path.join(base, "usage.md")), read_text(os.path.join(base, "data", "usage.md")))
    tokens, names = None, []
    if head:
        low = [h.lower() for h in head]
        col = low.index("all tokens") if "all tokens" in low else None
        vals = []
        for r in rows:
            who = r[0].strip("* ").strip() if r else ""
            v = to_int(r[col]) if col is not None and col < len(r) else None
            if who.lower() == "team":
                tokens = v
                continue
            vals.append(v)
            if who.lower() != "magic" and who:
                names.append(who)
        if tokens is None and vals and all(v is not None for v in vals):
            tokens = sum(vals)
    roster = [x for x in names if x.lower() in PLAYERS]
    if not roster:
        m = re.search(r"Players:\**\s*(.+)", log)
        if m:
            roster = [p.title() for p in PLAYERS if re.search(r"\b%s\b" % p, m.group(1), re.I)]
    n["players"] = roster or names
    n["tokens"] = tokens
    notes = []
    if n["mode"] == "dry run":
        notes.append("dry run")
    if n["hung"].startswith("yes"):
        notes.append("players hung: %s" % n["hung"][5:-1])
    elif n["hung"] == "froze":
        notes.append("the shift froze")
    if n["catch_up"]:
        notes.append("catch-up run from %s" % n["start"])
    if "[tipoff] hard cap" in log:
        notes.append("tipoff.sh closed the session at the hard cap")
    if runs:
        notes.append("extra run folder%s %s" % ("s" if len(runs) > 1 else "", ", ".join(r.split("/")[-2] for r in n["runs"])))
    n["notes"] = notes
    return n


# ---------------------------------------------------------------- ledgers and side reads

def asks_load():
    return [a for a in ((load_json(LP("asks.json"), {}) or {}).get("asks") or []) if isinstance(a, dict)]


def ask_state_at(a, end):
    if str(a.get("first_raised") or "9999") > end:
        return None
    cd = str(a.get("closed_date") or "")
    if a.get("status") in ("closed", "withdrawn") and cd and cd <= end:
        return a["status"]
    pd, pu = str(a.get("parked_date") or ""), str(a.get("park_until") or "")
    if a.get("status") == "parked" and pd and pd <= end and (not pu or pu > end):
        return "parked"
    return "open"


def week_packs(month):
    lo, hi = month + "-01", month_end(month)
    found = {}
    for d in day_folders():
        p = AI(d, "data", "week.json")
        w = load_json(p)
        if not isinstance(w, dict) or not isinstance(w.get("week"), list) or len(w["week"]) != 2:
            continue
        a, b = w["week"]
        if b < lo or a > hi:
            continue
        key = a
        cur = found.get(key)
        if cur is None or (b, w.get("generated_at") or "") > (cur[1]["week"][1], cur[1].get("generated_at") or ""):
            found[key] = (d, w)
    return [found[k] for k in sorted(found)]


def cars_runs(month):
    out = {}
    for d in day_folders():
        if not d.startswith(month):
            continue
        for p in sorted(glob.glob(os.path.join(glob.escape(AI(d)), "data", "cars_*", "summary.json"))):
            s = load_json(p)
            if isinstance(s, dict):
                out.setdefault(s.get("store") or p.split(os.sep)[-2][5:], []).append((d, s))
    return out


# ---------------------------------------------------------------- the summary note

def summary_text(month, date, final, archived, where_lines):
    nights = [parse_night(d) for d in day_folders() if d.startswith(month)]
    pack = load_json(LP("month-pack-%s.json" % month))
    pack = pack if isinstance(pack, dict) else None
    end = month_end(month)
    L = ["---", "type: ai-team-month-summary", "date: %s" % date, "month: %s" % month,
         "status: %s" % ("final" if final else "draft"), "archived: %s" % ("true" if archived else "false"),
         "tags: [ai-team, monthly-summary]", "---", "",
         "# AI team month summary, %s" % month_label(month), "",
         ("What the night shift did in %s, in one note: the month at a glance, the numbers per store, week by week, "
          "night by night, asks and rulings, and where the raw folders went. Nights are listed by shift date, so the "
          "shift on the 1st of the next month (which read this month's last day) sits in next month's note. "
          "Built by `month_close.py` from the briefs, shift logs and ledgers%s." % (
              month_label(month), "" if final else "; this is a draft until the close on or after %s" % close_from(month))), ""]
    L += glance(month, nights, pack, end, date)
    L += numbers(month, pack)
    L += weeks(month, pack, nights)
    L += night_by_night(nights)
    L += asks_section(month, end)
    L += rulings_section(month)
    L += cars_section(month)
    L += ops_section(month, nights, end)
    L += where_lines
    return "\n".join(L).rstrip() + "\n"


def glance(month, nights, pack, end, date):
    L = ["## Month at a glance", ""]
    if nights:
        L.append("- Shifts run: %d (%s)." % (len(nights), ", ".join(
            lab(n["date"]) + (" dry run" if n["mode"] == "dry run" else "") + (" catch-up" if n["catch_up"] else "")
            for n in nights)))
    else:
        L.append("- Shifts run: none in %s." % month_label(month))
    briefs = [n for n in nights if n["brief"]]
    L.append("- Briefs on file: %d, with the Slack thread recorded for %d." % (len(briefs), sum(1 for n in briefs if n["slack_ts"])))
    nob = [lab(n["date"]) for n in nights if not n["brief"]]
    L.append("- Nights with no brief: %s." % (", ".join(nob) if nob else "none"))
    have = {n["date"] for n in nights}
    sched = []
    for d in (dt.date.fromisoformat(month + "-01") + dt.timedelta(days=i) for i in range(31)):
        s = d.isoformat()
        if s[:7] != month or s > date:
            break
        if (d.weekday() < 5 and s >= WEEKDAY_FROM) or (d.weekday() == 5 and s >= SATURDAY_FROM):
            if s not in have:
                sched.append(lab(s))
    L.append("- Scheduled nights with no shift folder: %s." % (", ".join(sched) if sched else "none"))
    asks = asks_load()
    raised = [a for a in asks if str(a.get("first_raised") or "").startswith(month)]
    closed = [a for a in asks if a.get("status") == "closed" and str(a.get("closed_date") or "").startswith(month)]
    wdr = [a for a in asks if a.get("status") == "withdrawn" and str(a.get("closed_date") or "").startswith(month)]
    states = collections.Counter(ask_state_at(a, end) for a in asks)
    L.append("- Asks: %d raised, %d closed (%d with a win), %d withdrawn; %d open and %d parked on %s." % (
        len(raised), len(closed), sum(1 for a in closed if a.get("win")), len(wdr), states["open"], states["parked"], md(end)))
    rul = rulings_in(month)
    L.append("- Drew's rulings added: %d%s." % (len(rul), " (%s)" % ", ".join(r.get("id", "?") for r in rul) if rul else ""))
    mins = sum(n["minutes"] or 0 for n in nights)
    L.append("- Team: %d minutes on the floor, %d huddles, %d bounces, %s tokens (nights with a usage table)." % (
        mins, sum(n["huddles"] or 0 for n in nights), sum(n["bounces"] or 0 for n in nights),
        fnum(sum(n["tokens"] or 0 for n in nights))))
    inc = ["%s: %s" % (lab(n["date"]), "; ".join(n["notes"])) for n in nights if n["notes"]]
    L.append("- Incidents and odd nights: %s." % ("; ".join(inc) if inc else "none"))
    if pack:
        L.append("- Month pack: %s, built %s, through %s. Full pack: [[month-pack-%s]]%s." % (
            "final" if pack_is_final(pack) else "draft", str(pack.get("generated_at") or "?")[:16].replace("T", " "),
            pack.get("through") or "n/a", month,
            ", vendor list: [[vendor-month-end-%s]]" % month if os.path.exists(LP("vendor-month-end-%s.md" % month)) else ""))
    else:
        L.append("- Month pack: none on file yet (`ledgers.py month --month %s`)." % month)
    last = next((n for n in reversed(nights) if n["health"]), None)
    if last:
        L.append("- Measurement health on the last night (%s):" % lab(last["date"]))
        L += ["  - %s" % h for h in last["health"]]
    L.append("")
    return L


def numbers(month, pack):
    L = ["## Numbers by store", ""]
    if not pack:
        return L + ["No month pack on file, so no store numbers yet.", ""]
    st = pack.get("stores") or {}
    L.append("From [[month-pack-%s]] (%s, built %s). A source covers the whole month only when its day count is "
             "complete.%s" % (month, "final" if pack_is_final(pack) else "draft", str(pack.get("generated_at") or "?")[:10],
                              " The team started 2026-09-19 and the nightly GA4 pull reads the last 7 days, so GA4 starts "
                              "mid-month." if month == FIRST_MONTH else ""))
    L.append("")

    def cov(src):
        c = (src or {}).get("coverage") or {}
        if not c.get("count"):
            return "none"
        return "%d of %d (%s to %s)" % (c["count"], c.get("days_in_month") or 0, md(c["first"]), md(c["last"])) \
            if c.get("first") and c.get("last") else str(c.get("count"))

    L += ["Web (GA4)", "",
          "| Store | Days | Sessions | Key events | Clean key events | Organic | AI assistant |",
          "|---|---|---|---|---|---|---|"]
    for s in STORES:
        g = (st.get(s) or {}).get("ga4") or {}
        t = g.get("totals") or {}
        ck = g.get("clean_key_events") or {}
        L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            store_link(s), cov(g), fnum(t.get("sessions")), fnum(t.get("key_events")),
            "%s on %d day%s" % (fnum(sum(v for v in ck.values() if isinstance(v, (int, float)))), len(ck), "" if len(ck) == 1 else "s")
            if ck else "n/a", fnum(t.get("organic_sessions")), fnum(t.get("ai_sessions"))))
    L += ["", "Paid (Google Ads export and the Meta account)", "",
          "| Store | Ads days | Ads cost | Ads clicks | Ads conversions | Meta days | Meta spend | Meta clicks | Landing page views |",
          "|---|---|---|---|---|---|---|---|---|"]
    for s in STORES:
        a = (st.get(s) or {}).get("google_ads") or {}
        m = (st.get(s) or {}).get("meta") or {}
        at, mt = a.get("totals") or {}, m.get("totals") or {}
        has_a = ((a.get("coverage") or {}).get("count") or 0) > 0
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            store_link(s), cov(a), fmoney(at.get("cost")) if has_a else "no export", fnum(at.get("clicks")) if has_a else "n/a",
            fnum(at.get("conversions")) if has_a else "n/a", cov(m), fmoney(mt.get("spend")), fnum(mt.get("clicks")),
            fnum(mt.get("landing_page_views"))))
    L += ["", "CRM (newest month-to-date snapshot)", "",
          "| Store | Period | Leads | Good leads | Appointments | Shows | Sold | Cost |",
          "|---|---|---|---|---|---|---|---|"]
    for s in STORES:
        c = (st.get(s) or {}).get("crm") or {}
        h = c.get("headline") or {}
        cv = c.get("coverage") or {}
        per = "%s to %s%s" % (md(cv["period_start"]), md(cv["period_end"]), ", complete" if cv.get("complete") else "") \
            if cv.get("period_start") and cv.get("period_end") else "no snapshot"
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            store_link(s), per, fnum(h.get("leads")), fnum(h.get("good_leads")), fnum(h.get("appointments")),
            fnum(h.get("shows")), fnum(h.get("sold")), fmoney(h.get("cost"))))
    cav = []
    for s in STORES:
        notes = ((st.get(s) or {}).get("ga4") or {}).get("key_events_notes") or []
        if notes:
            cav.append("- %s key events: %s" % (store_link(s), first_sentence(notes[-1], 240)))
    if cav:
        L += ["", "Key event caveats (the last one on file per store):"] + cav
    L.append("")
    return L


def weeks(month, pack, nights):
    L = ["## Week by week", ""]
    packs = week_packs(month)
    if packs:
        L.append("From the week packs (`ledgers.py week`), which leave with the day folders. Each line is the week "
                 "against the week before on the same weekdays; the newest day in a pack was preliminary.")
        L.append("")
    for d, w in packs:
        a, b = w["week"]
        pa, pb = (w.get("prior_week") or [None, None])[:2]
        L.append("### Week of %s to %s" % (lab(a), lab(b)))
        L.append("Pack from the %s shift%s." % (lab(d), ", prior week %s to %s" % (lab(pa), lab(pb)) if pa and pb else ""))
        L.append("")
        for s, st in (w.get("stores") or {}).items():
            parts = []
            g = (st.get("ga4") or {})
            gw, gp = (g.get("week") or {}), (g.get("prior") or {})
            if gw.get("days"):
                tw, tp = gw.get("totals") or {}, gp.get("totals") or {}
                parts.append("GA4 %d day%s: sessions %s vs %s%s, key events %s vs %s" % (
                    len(gw["days"]), "" if len(gw["days"]) == 1 else "s", fnum(tw.get("sessions")), fnum(tp.get("sessions")),
                    pct(tw.get("sessions"), tp.get("sessions")), fnum(tw.get("key_events")), fnum(tp.get("key_events"))))
            else:
                parts.append("GA4: no pulls")
            aw = ((st.get("google_ads") or {}).get("week") or {})
            if aw.get("days"):
                ap = ((st.get("google_ads") or {}).get("prior") or {}).get("totals") or {}
                parts.append("Ads cost %s vs %s" % (fmoney((aw.get("totals") or {}).get("cost")), fmoney(ap.get("cost"))))
            cw = ((st.get("crm") or {}).get("week") or {})
            if cw.get("total") and cw.get("covers"):
                t = cw["total"]
                parts.append("CRM %s to %s: %s leads, %s appointments, %s shows, %s sold" % (
                    md(cw["covers"][0]), md(cw["covers"][1]), fnum(t.get("leads")), fnum(t.get("appointments")),
                    fnum(t.get("shows")), fnum(t.get("sold"))))
            else:
                parts.append("CRM: no usable snapshots")
            L.append("- %s: %s." % (store_link(s), "; ".join(parts)))
        L.append("")
    sats = [n for n in nights if n["week_review"]]
    for n in sats:
        L.append("Magic's week in review (%s):" % lab(n["date"]))
        L += ["- %s" % x for x in n["week_review"]]
        L.append("")
    if pack:
        L += pack_weeks(month, pack)
    if not packs and not pack:
        L += ["No week packs and no month pack for %s." % month_label(month), ""]
    return L


def pack_weeks(month, pack):
    """Monday to Sunday totals from the month pack's daily rows, clipped to the month."""
    days = [d for d in (dt.date.fromisoformat(month + "-01") + dt.timedelta(days=i) for i in range(31))
            if d.isoformat()[:7] == month]
    wks = collections.OrderedDict()
    for d in days:
        mon = (d - dt.timedelta(days=d.weekday())).isoformat()
        wks.setdefault(mon, []).append(d.isoformat())
    st = pack.get("stores") or {}

    def table(title, src, key, f):
        rows = ["%s, by week (from the month pack's daily rows, Monday to Sunday inside %s; days with data in brackets):"
                % (title, month_label(month)), "", "| Week | " + " | ".join(store_link(s) for s in STORES) + " |",
                "|---|" + "---|" * len(STORES)]
        any_val = False
        for mon, dd in wks.items():
            cells = []
            for s in STORES:
                daily = {r.get("date"): r for r in ((st.get(s) or {}).get(src) or {}).get("daily") or [] if isinstance(r, dict)}
                got = [daily[d].get(key) for d in dd if d in daily and isinstance(daily[d].get(key), (int, float))]
                any_val = any_val or bool(got)
                cells.append("%s (%d)" % (f(sum(got)), len(got)) if got else "n/a")
            rows.append("| %s to %s | %s |" % (md(dd[0]), md(dd[-1]), " | ".join(cells)))
        return rows + [""] if any_val else []

    return table("GA4 sessions", "ga4", "sessions", fnum) + table("Google Ads cost", "google_ads", "cost", fmoney)


def night_by_night(nights):
    L = ["## Night by night", ""]
    if not nights:
        return L + ["No shifts this month.", ""]
    for n in nights:
        L.append("### %s%s" % (lab(n["date"]), " (dry run)" if n["mode"] == "dry run" else ""))
        bits = []
        if n["start"] or n["end"]:
            bits.append("shift %s to %s%s" % (n["start"] or "?", n["end"] or "?",
                                             " (%d min)" % n["minutes"] if n["minutes"] is not None else ""))
        if n["players"] and all(re.match(r"^Player \d+$", x) for x in n["players"]):
            bits.append("%d players (not named in the usage table)" % len(n["players"]))
        elif n["players"]:
            bits.append("players %s" % ", ".join(n["players"]))
        bits.append("%s huddle%s, %s bounce%s" % (fnum(n["huddles"]), "" if n["huddles"] == 1 else "s",
                                                  fnum(n["bounces"]), "" if n["bounces"] == 1 else "s"))
        bits.append("Slack ts %s" % n["slack_ts"] if n["slack_ts"] else "no Slack ts on file")
        head = "; ".join(bits)
        L.append("- %s%s." % (head[:1].upper(), head[1:]))
        if not n["brief"]:
            L.append("- No brief this night.")
        if n["three"]:
            L.append("- The three things:")
            L += ["  %d. %s" % (i + 1, t) for i, t in enumerate(n["three"])]
        if n["needs_ids"] or n["needs_other"]:
            parts = []
            if n["needs_ids"]:
                parts.append(", ".join(n["needs_ids"]))
            if n["needs_other"]:
                parts.append("%s: %s" % ("also" if n["needs_ids"] else "no ask ids yet", "; ".join(n["needs_other"])))
            L.append("- Needs your call: %s" % stop("; ".join(parts)))
        if n["corrections"]:
            L.append("- Corrections: %s" % " ".join(n["corrections"]))
        if n["notes"]:
            L.append("- Notes: %s" % stop("; ".join(n["notes"])))
        if n["brief"]:
            L.append("- Brief: `%s`" % n["brief"])
        L.append("")
    return L


def asks_section(month, end):
    L = ["## Asks", ""]
    asks = asks_load()
    if not asks:
        return L + ["No asks ledger on file.", ""]

    def line(a, extra=""):
        return "- %s %s: %s (owner %s)%s" % (a.get("id"), store_link(a.get("store")), a.get("label") or "", a.get("owner") or "?", extra)

    raised = [a for a in asks if str(a.get("first_raised") or "").startswith(month)]
    L.append("Raised in %s (%d):" % (month_label(month), len(raised)))
    for a in raised:
        now = a.get("status")
        L.append(line(a, ", raised %s, %s%s." % (md(a["first_raised"]), now,
                                               " %s" % md(a["closed_date"]) if a.get("closed_date") and now in ("closed", "withdrawn") else "")))
    closed = [a for a in asks if a.get("status") == "closed" and str(a.get("closed_date") or "").startswith(month)]
    L += ["", "Closed in %s (%d):" % (month_label(month), len(closed))]
    for a in closed:
        L.append(line(a, stop(", closed %s%s" % (md(a["closed_date"]), ". Win: %s" % a["win"] if a.get("win") else ""))))
    wdr = [a for a in asks if a.get("status") == "withdrawn" and str(a.get("closed_date") or "").startswith(month)]
    if wdr:
        L += ["", "Withdrawn in %s (%d):" % (month_label(month), len(wdr))]
        for a in wdr:
            L.append(line(a, stop(", %s: %s" % (md(a["closed_date"]), first_sentence(a.get("withdrawn_reason") or "no reason on file", 160)))))
    op = [a for a in asks if ask_state_at(a, end) in ("open", "parked")]
    L += ["", "Open on %s (%d):" % (md(end), len(op))]
    for a in op:
        n = sum(1 for r in a.get("raised") or [] if str(r) <= end)
        days = (dt.date.fromisoformat(end) - dt.date.fromisoformat(a["first_raised"])).days
        L.append(line(a, ", %s%d day%s open, raised %d time%s." % (
            "parked, " if ask_state_at(a, end) == "parked" else "", days, "" if days == 1 else "s", n, "" if n == 1 else "s")))
    L.append("")
    return L


def rulings_in(month):
    rows = (load_json(LP("rulings.json"), {}) or {}).get("rulings") or []
    return [r for r in rows if isinstance(r, dict) and str(r.get("date") or r.get("added") or "").startswith(month)]


def rulings_section(month):
    L = ["## Drew's rulings added", ""]
    rows = rulings_in(month)
    if not rows:
        return L + ["None in %s." % month_label(month), ""]
    for r in rows:
        lanes = r.get("lane") or []
        L.append("- %s (%s, %s, lanes %s%s): %s" % (
            r.get("id"), md(r["date"]) if r.get("date") else "?", store_link(r.get("store")),
            ", ".join(lanes) if isinstance(lanes, list) else lanes,
            ", expires %s" % r["expires"] if r.get("expires") else "", " ".join(str(r.get("ruling") or "").split())))
    L.append("")
    return L


def cars_section(month):
    runs = cars_runs(month)
    L = ["## CARS watch", ""]
    if not runs:
        return L + ["No CARS web watch runs in %s." % month_label(month), ""]
    L.append("One store a night on the weekday rotation (`cars_watch.py`). Rules are flagged for review, not called "
             "violations.")
    L.append("")
    for store in sorted(runs):
        L.append("%s:" % store_link(store))
        for d, s in runs[store]:
            cr = s.get("crawl") or {}
            cnt = s.get("counts") or {}
            diff = s.get("diff") or {}
            new = [x.get("id") if isinstance(x, dict) else str(x) for x in diff.get("new") or []]
            res = diff.get("resolved") or []
            top = [r for r in s.get("rules") or [] if isinstance(r, dict) and r.get("triage") == "review"][:3]
            mode = str(s.get("mode") or "").split(" ")[0].lower() or "n/a"
            L.append("- %s: %s, %s of %s pages read, %s rule%s for review on %s page%s, %s mode; %s; %s.%s" % (
                lab(d), s.get("status"), fnum(cr.get("ok")), fnum(cr.get("queued")), fnum(cnt.get("review_rules")),
                "" if cnt.get("review_rules") == 1 else "s", fnum(cnt.get("review_pages")),
                "" if cnt.get("review_pages") == 1 else "s", mode,
                "new since the last run: %s" % ", ".join(new) if new else ("first run, no comparison" if not s.get("last_ok_date") else "nothing new"),
                "%d resolved" % len(res),
                " Top: %s." % "; ".join("%s %s (%s page%s)" % (r.get("id"), r.get("label") or "", fnum(r.get("pages_flagged")),
                                                                "" if r.get("pages_flagged") == 1 else "s")
                                        for r in top) if top else ""))
        L.append("")
    return L


def ops_section(month, nights, end):
    L = ["## Team operations", ""]
    if nights:
        L += ["| Night | Start | End | Minutes | Players | Huddles | Bounces | Hung | Team tokens |",
              "|---|---|---|---|---|---|---|---|---|"]
        for n in nights:
            L.append("| %s | %s | %s | %s | %d | %s | %s | %s | %s |" % (
                lab(n["date"]) + (" (dry run)" if n["mode"] == "dry run" else "") + (" (catch-up)" if n["catch_up"] else ""),
                n["start"] or "n/a", n["end"] or "n/a", fnum(n["minutes"]), len(n["players"]), fnum(n["huddles"]),
                fnum(n["bounces"]), cell(n["hung"]), fnum(n["tokens"])))
        L.append("| **Month** | | | %s | | %s | %s | | %s |" % (
            fnum(sum(n["minutes"] or 0 for n in nights)), fnum(sum(n["huddles"] or 0 for n in nights)),
            fnum(sum(n["bounces"] or 0 for n in nights)), fnum(sum(n["tokens"] or 0 for n in nights))))
        L.append("")
    players = (load_json(LP("coaching.json"), {}) or {}).get("players") or {}
    rows = []
    for name in PLAYERS:
        p = players.get(name)
        if not isinstance(p, dict):
            continue
        hist = [h for h in p.get("history") or [] if str(h.get("date") or "").startswith(month)]
        if not hist:
            continue
        b = [x for h in hist for x in h.get("bounces") or [] if isinstance(x, dict)]
        lvl = [x for x in p.get("level_history") or [] if str(x.get("date") or "") <= end]
        rows.append("- %s: %d shift%s coached, %d factual and %d wording bounce%s, %d self-catch%s, level %s on %s." % (
            name.title(), len(hist), "" if len(hist) == 1 else "s", sum(1 for x in b if x.get("factual")),
            sum(1 for x in b if not x.get("factual")), "" if len(b) == 1 else "s",
            sum(int(h.get("self_caught") or 0) for h in hist), "" if sum(int(h.get("self_caught") or 0) for h in hist) == 1 else "es",
            (lvl[-1].get("level") if lvl else p.get("level")) or "n/a", md(end)))
    if rows:
        L += ["Coaching (from coaching.json):"] + rows + [""]
    return L


def where_lines(month, plan=None):
    L = ["## Where the raw files went", ""]
    mans = manifests(month)
    taken = foreign_zips(month)
    if not mans and not taken and plan is None:
        return L + ["Nothing was archived for %s: no raw folders from the month were in the vault at the close." % month_label(month), ""]
    if not mans and not taken:
        L.append("Not archived yet. The day folders stay in the vault until the month closes on the first shift on or "
                 "after %s (`month_close.py close --month %s --date D --apply`)." % (close_from(month), month))
        if plan is not None:
            m, s, rem = plan["main"], plan["semrush"], removable(plan)
            L.append("")
            L.append("If it closed today: %d file(s) (%s) into `ai-team-%s.zip`, %d Semrush file(s) (%s) into "
                     "`ai-team-%s-semrush-cache.zip` pending Drew's ruling on Semrush ToS 3.3, %d file(s) leave the vault "
                     "and %d carr%s stay." % (len(m), fbytes(sum(f["size"] for f in m)), month, len(s),
                                             fbytes(sum(f["size"] for f in s)), month, len(rem), len(plan["carry"]),
                                             "y" if len(plan["carry"]) == 1 else "ies"))
        L.append("")
        return L
    dest = os.path.join(ARCHIVE, month)
    if mans:
        L.append("Archive folder: `%s` (outside the vault). INDEX: `%s`." % (tilde(dest), tilde(os.path.join(ARCHIVE, "INDEX.md"))))
    else:
        L.append("No zip of its own: a later close took the month's files (below). INDEX: `%s`." % tilde(
            os.path.join(ARCHIVE, "INDEX.md")))
    L.append("")
    nights = set()
    for m in mans:
        days = sorted({p.split("/")[2] for p in m.get("source_paths") or [] if p.count("/") == 3})
        nights.update(d for d in days if d.startswith(month))
        rm = m.get("removal") or {}
        L.append("- `%s` (%s, created %s): %s file(s), %s before, %s zipped, sha256 `%s`. Manifest `%s`. %s" % (
            m["zip"], "Semrush cache, pending Drew's ruling on Semrush ToS 3.3" if m.get("kind") == "semrush-cache" else "main",
            str(m.get("created") or "?")[:16].replace("T", " "), fnum(m.get("file_count")), fbytes(m.get("bytes_before")),
            fbytes(m.get("bytes_after")), m.get("zip_sha256"), os.path.basename(m["_path"]),
            "Removed from the vault: %s; kept: %d carr%s%s%s." % (
                fnum(rm.get("removed")), rm.get("kept_carries") or 0, "y" if rm.get("kept_carries") == 1 else "ies",
                ", %d changed since hashing" % len(rm.get("kept_changed") or []) if rm.get("kept_changed") else "",
                ", %d error(s)" % len(rm.get("errors") or []) if rm.get("errors") else "") if rm else "Removal not recorded."))
    for m, mine in taken:
        nights.update({e["path"].split("/")[2] for e in mine} - set(SIDE_PILES))
        L.append("- `%s` (from the %s close, created %s): holds %s file(s) dated in %s (%s), sha256 `%s`. Manifest `%s` "
                 "in `%s`. That later close found them still in the vault and took them with it." % (
                     m["zip"], month_label(m.get("month") or month), str(m.get("created") or "?")[:16].replace("T", " "),
                     fnum(len(mine)), month_label(month), fbytes(sum(e.get("size") or 0 for e in mine)),
                     m.get("zip_sha256"), os.path.basename(m["_path"]), tilde(os.path.dirname(m["_path"]))))
    log = load_json(os.path.join(dest, "ai-team-%s.close-log.json" % month), {}) or {}
    reused = [p for r in log.get("runs") or [] for p in r.get("removed_already_zipped") or []]
    if reused:
        L.append("- Removed later without a second copy (already in a verified zip): %d file(s), for example `%s`." % (
            len(reused), reused[0]))
    if nights:
        L.append("- Nights in the archive: %s." % ", ".join(md(d) for d in sorted(nights)))
    left, skipped = collect(month_roots(month))
    car, _st = all_carries()
    keep = [(f["path"], "; ".join(car.get(f["abs"]) or [])) for f in left]
    L.append("")
    if keep:
        L.append("Still in the vault (%d):" % len(keep))
        for p, why in keep:
            L.append("- `%s`: %s" % (p, why or "not a carry; it leaves at the next close"))
    else:
        L.append("Nothing from %s is left in the vault." % month_label(month))
    if skipped:
        L.append("")
        L.append("Skipped and left in place (never archived, never removed): %s." % "; ".join(
            "`%s` (%s)" % (s["path"], s["reason"]) for s in skipped))
    every = mans + [m for m, _mine in taken]
    main = next((m for m in every if m.get("kind") == "main"), every[0])
    one = sorted(nights)[-1] if nights else month + "-01"
    L += ["", "Restore:",
          "- One night: `unzip -o %s 'outputs/ai-team/%s/*' -d %s` (swap in the date you want)." % (
              shell_path(main["_zip"]), one, shell_path(ROOT))]
    sem = next((m for m in every if m.get("kind") == "semrush-cache"), None)
    if sem:
        L.append("- That night's Semrush files are in the other zip: `unzip -o %s 'outputs/ai-team/%s/*' -d %s`." % (
            shell_path(sem["_zip"]), one, shell_path(ROOT)))
    L += [
          "- Everything in a zip: `unzip -o ZIP -d %s`. Members are vault-relative paths, so files land where they were." % shell_path(ROOT),
          "- Check a zip before trusting it: `shasum -a 256 ZIP` must match the sha256 above.", ""]
    return L


def with_lead(text, lead):
    """Put a one-paragraph note above Month at a glance (once)."""
    if not lead or lead in text:
        return text
    return text.replace("\n## Month at a glance\n", "\n%s\n\n## Month at a glance\n" % lead, 1)


def rewrite_where(month, date, archived, lead=None):
    """Replace the summary's last section and set archived/status/date. Builds the summary if it is missing. The
    body is kept; lead (a later close took the month's files) goes above Month at a glance."""
    path = summary_path(month)
    text = read_text(path)
    new_where = "\n".join(where_lines(month)).rstrip() + "\n"
    if not text:
        text = summary_text(month, date, True, archived, [])
        note = "built from what was left in the vault"
    else:
        note = None
    text = with_lead(text, lead).replace("; this is a draft until the close on or after %s" % close_from(month), "")
    i = text.find("## Where the raw files went")
    body = text[:i].rstrip() + "\n\n" if i >= 0 else text.rstrip() + "\n\n"
    for k, v in (("status", "final"), ("archived", "true" if archived else "false"), ("date", date)):
        body = re.sub(r"(?m)^%s:.*$" % k, "%s: %s" % (k, v), body, count=1) if re.search(r"(?m)^%s:" % k, body) else body
    write_text(path, body + new_where)
    return note


# ---------------------------------------------------------------- commands

def cmd_due(args):
    date = iso(args.date)
    cur = date[:7]
    prev = prev_month(cur)
    summary_due = [prev] if prev >= FIRST_MONTH and not os.path.exists(summary_path(prev)) else []
    close_due = []
    if prev >= FIRST_MONTH:
        check_archive_root()
        for m in months_between(FIRST_MONTH, prev):
            if date < close_from(m):
                continue
            if not truthy(read_frontmatter(summary_path(m)).get("archived")):
                close_due.append(m)
                continue
            if removable(build_plan(m, month_roots(m))):
                close_due.append(m)
    print(json.dumps({"summary_due": summary_due, "close_due": close_due}))
    return 0


def cmd_summary(args):
    month = month_arg(args.month)
    if month < FIRST_MONTH:
        die("%s is before the team started (%s)" % (month, FIRST_MONTH), 2)
    date = iso(args.date) if args.date else pacific_now().date().isoformat()
    out = os.path.abspath(os.path.expanduser(args.out)) if args.out else summary_path(month)
    if not args.out and truthy(read_frontmatter(out).get("archived")):
        print("summary %s: kept %s; the month is archived, so its folders are gone and a rebuild would lose detail. "
              "--out writes a fresh copy elsewhere." % (month, rel(out)))
        return 0
    if args.out and inside(out, AI()) and SOURCE_RE.match(rel(out)):
        die("--out must not point inside a dated folder", 2)
    pack = load_json(LP("month-pack-%s.json" % month))
    final = pack_is_final(pack if isinstance(pack, dict) else None)
    check_archive_root()
    plan = build_plan(month, close_roots(month)) if not manifests(month) else None
    archived = truthy(read_frontmatter(summary_path(month)).get("archived")) and bool(manifests(month))
    text = summary_text(month, date, final, archived, where_lines(month, plan))
    write_text(out, text)
    print("summary %s: wrote %s (%s, %s, %s)." % (month, rel(out) if inside(out, ROOT) else out,
                                                 "final" if final else "draft", "archived" if archived else "not archived",
                                                 fbytes(len(text.encode("utf-8")))))
    return 0


def cmd_plan(args):
    month = month_arg(args.month)
    date = iso(args.date)
    if month < FIRST_MONTH:
        die("%s is before the team started (%s); nothing to plan" % (month, FIRST_MONTH), 2)
    check_archive_root()
    plan = build_plan(month, close_roots(month))
    if args.json:
        print(json.dumps(plan_json(plan, date), indent=1))
    else:
        print("\n".join(plan_lines(plan, date)))
    return 0


def cmd_close(args):
    month, date = month_arg(args.month), iso(args.date)
    if month < FIRST_MONTH:
        print("close %s: refused, the team started in %s." % (month, FIRST_MONTH))
        return 2
    if month >= date[:7]:
        print("close %s: refused, %s is not a past month on %s." % (month, month, date))
        return 2
    if date < close_from(month) and not args.force_early:
        print("close %s: refused, too early. A month closes on the first shift on or after %s (the next month's "
              "readers still look back into it until then); --force-early overrides." % (month, close_from(month)))
        return 2
    behind = unarchived_before(month)
    if behind:
        print("close %s: refused, close %s first. Its summary is not marked archived: true, and this close reaches back "
              "to %s-01, so it would sweep %s's folders into the %s zip. Months close in order." % (
                  month, behind, FIRST_MONTH, month_label(behind), month))
        return 2
    check_archive_root()
    apply = bool(args.apply) and not args.dry_run
    archived = truthy(read_frontmatter(summary_path(month)).get("archived"))
    prior = manifests(month)
    plan = build_plan(month, close_roots(month))
    rem = removable(plan)
    if archived and not rem and not plan["main"] and not plan["semrush"]:
        print("close %s: already archived, nothing left to move (%d carr%s stay in the vault)."
              % (month, len(plan["carry"]), "y" if len(plan["carry"]) == 1 else "ies"))
        return 0
    has_days = any(d.startswith(month) for d in day_folders())
    first = not prior and not archived  # an archived summary means the folders already left once: never rebuild then
    taken = foreign_zips(month)
    diverted = first and bool(taken)  # a later zip took this month's files before its first close (older script)
    if diverted:
        first = False  # what is left is not the whole month: never rebuild the pack or the summary body from it
    if not apply:
        print("\n".join(plan_lines(plan, date)))
        steps = []
        if first and has_days:
            steps.append("ledgers.py month --month %s --final and vendor month-end" % month)
        if first:
            steps.append("write the final summary")
        steps += ["zip and verify", "remove %d file(s)" % len(rem), "rewrite Where the raw files went, archived: true"]
        if diverted:
            print("  month pack and summary body would be kept: %s" % taken_line(month, taken))
        print("DRY RUN: nothing written or removed. With --apply: %s." % "; ".join(steps))
        return 0
    print("close %s on %s%s:" % (month, date, " (forced early)" if date < close_from(month) else ""))
    if first and has_days:
        print("  month pack: ledgers.py month --month %s --final, then vendor month-end" % month)
        err = run_pack_step(month)
        if err:
            print("FAILED before archiving: %s. Nothing archived, nothing removed." % err)
            return 1
    elif diverted:
        print("  month pack and summary body kept: %s" % taken_line(month, taken))
    elif not first:
        print("  month pack and summary body kept: %s already has a zip, so its folders are partly gone" % month)
    lead = ("Note: %s. So the month pack was not rebuilt as final, and anything read from the day folders only covers "
            "what was still in the vault; unzip %s into a scratch folder for the full detail."
            % (taken_line(month, taken), "that zip" if len(taken) == 1 else "those zips")) if diverted else None
    if first or not os.path.exists(summary_path(month)):
        write_text(summary_path(month), with_lead(summary_text(month, date, True, False, where_lines(month, plan)), lead))
        print("  final summary written: %s" % rel(summary_path(month)))
    res = archive_month(plan, month, date)
    if res["failed"]:
        print("FAILED: %s. The new zips, their manifests and any INDEX text from this run were deleted; nothing was "
              "removed from the vault." % res["failed"])
        return 1
    for m in res["zips"]:
        print("  %s: %d file(s), %s before, %s zipped, sha256 %s..., verified" % (
            m["zip"], m["file_count"], fbytes(m["bytes_before"]), fbytes(m["bytes_after"]), m["zip_sha256"][:12]))
    if res["redo"]:
        print("  zipped again (the earlier copy could not be re-checked): %d" % len(res["redo"]))
    if res["reused"]:
        print("  removed without a new copy (already in a verified zip): %d" % len(res["reused"]))
    print("  removed %d file(s) and %d empty folder(s); %d carr%s stay; %d skipped" % (
        len(res["removed"]), res["dirs"], len(plan["carry"]), "y" if len(plan["carry"]) == 1 else "ies", len(plan["skipped"])))
    for k in res["kept"]:
        print("  kept: %s" % k)
    for e in res["errors"]:
        print("  ERROR removing %s" % e)
    note = rewrite_where(month, date, True, lead)
    print("  summary: %s, archived: true%s" % (rel(summary_path(month)), " (%s)" % note if note else ""))
    if res["errors"]:
        print("close %s: archived with %d removal error(s); the files are still in the vault and the next close picks "
              "them up." % (month, len(res["errors"])))
        return 1
    return 0


# ---------------------------------------------------------------- selftest

def cmd_selftest(_args):
    global ROOT, ARCHIVE, PACK_STEP, AFTER_WRITE
    saved = (ROOT, ARCHIVE, PACK_STEP, AFTER_WRITE)
    tmp = tempfile.mkdtemp(prefix="month-close-selftest-")
    ROOT, ARCHIVE = os.path.join(tmp, "vault"), os.path.join(tmp, "archive")
    results = []
    calls = []

    def check(name, cond, detail=""):
        results.append((name, bool(cond), detail))

    def put(relpath, data):
        p = os.path.join(ROOT, relpath)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))
        return p

    def run(argv):
        global ROOT, ARCHIVE
        keep = (ROOT, ARCHIVE)
        _CARRY_CACHE.clear()
        buf = io.StringIO()
        code = 0
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                code = main(argv) or 0
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
            except Exception as e:  # a crash is a failed check, not a crashed selftest
                code = 99
                print("CRASH %s: %s" % (type(e).__name__, e))
        ROOT, ARCHIVE = keep
        _CARRY_CACHE.clear()
        return code, buf.getvalue()

    def tree():
        out = {}
        for base in (os.path.join(ROOT, "outputs"),):
            for dp, _dn, fns in os.walk(base):
                for fn in fns:
                    p = os.path.join(dp, fn)
                    if "/monthly/" in p or "/ledgers/" in p:
                        continue
                    out[rel(p)] = sha_file(p) if not os.path.islink(p) else "link"
        return out

    def zips():
        return sorted(glob.glob(os.path.join(ARCHIVE, "*", "*.zip")))

    def stub(month):
        calls.append(month)
        put("outputs/ai-team/ledgers/month-pack-%s.json" % month, dict(PACK, final=True, generated_at="2026-10-15T01:05:00"))
        return None

    brief_new = """---
type: ai-team-brief
date: 2026-09-21
status: final
tags: [ai-team, brief]
---

## AI Team Brief, Monday 2026-09-21
Morning Drew.

### The three things
1. **[[NOI]]: Gas Models took $1,008 over the weekend for zero conversions.** Friday $380 on 96 clicks.
2. **[[NOI]]: PMAX has been throttled to almost nothing.** Impressions fell.
3. **[[MCP]]: the OEM campaign nearly stopped on Sunday.** Rank, not budget.

### Needs your call
- **NOI ad (A20):** change the Value-Payment line today?
- **Get someone into NOI PMAX.** Not a budget change.

### Corrections
- Yesterday's brief named the wrong page. Value-Payment is a campaign, not a page.

### Measurement health
- [[SBMW]]: AMBER. Service page views counted as conversions. Broken 6 days.

### Shift stats
| Player | Model | On floor | Minutes | All tokens | API calls |
|---|---|---|---|---|---|
| Magic | opus | 01:00 to 01:15 | 15.0 | 1,000,000 | 10 |
| Kobe | sonnet | 01:01 to 01:15 | 14.0 | 500,000 | 5 |
| **Team** | | | | 1,500,000 | 15 |

Shift started 01:00 PDT; brief posted 01:14 PDT, 5 huddles, 2 bounces.
"""
    log_new = """---
type: shift-log
date: 2026-09-21
status: active
tags: [ai-team, shift-log]
---
# Shift log 2026-09-21 (shift, Monday)

- Start: 01:00 PDT (Monday, mode shift)
- 01:14 PDT Brief posted: parent_ts 1790000000.000001, 10 replies.
- 01:15 PDT Final whistle. Players: kobe, shaq, luka, worthy, nick; none hung.
- End: 01:16 PDT
"""
    brief_old = """## AI Team Brief, Tuesday 2026-09-22
Coverage: Mon 2026-09-21. Mode: dry-run.

### Top 3 for Drew
1. **The BMW iX3 lands in six days.** BMW USA says deliveries start September 25.
2. **[[MCP]] New CDJR search is capped by budget every day.** It lost share to budget.

### Needs your call
- **MCP OEM budget raise** (Shaq): yes means more call volume.
"""
    log_old = ("# AI Team shift log, 2026-09-22 (dry-run)\n\n**Tip-off:** 01:00 PDT \u00b7 **Whistle:** 02:35 PDT \u00b7 "
               "**Minutes:** 95\n**Players:** 5 spawned, 5 lost \u00b7 **Huddles:** 0 \u00b7 **Bounces:** 0\n"
               "- Brief: outputs/ai-team/2026-09-22/brief.md, Slack ts 1790100000.000002 (tagged Drew)\n")
    week = {"schema": "week-pack.v1", "shift_date": "2026-10-03", "week": ["2026-09-28", "2026-10-02"],
            "prior_week": ["2026-09-21", "2026-09-25"], "generated_at": "2026-10-03T01:05:10",
            "stores": {"NOI": {"name": "Nissan of Irvine",
                               "ga4": {"week": {"days": ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02"],
                                                "totals": {"sessions": 1311, "key_events": 60}},
                                       "prior": {"days": ["2026-09-21"], "totals": {"sessions": 1410, "key_events": 61}}},
                               "google_ads": {"week": {"days": ["2026-09-28"], "totals": {"cost": 329.34}},
                                              "prior": {"days": ["2026-09-21"], "totals": {"cost": 575.49}}},
                               "crm": {"week": {"total": {"leads": 64, "appointments": 17, "shows": 5, "sold": 9},
                                                "covers": ["2026-09-28", "2026-10-02"]}, "prior": {"total": None}}}}}
    cars_ok = {"store": "NOI", "date": "2026-09-22", "status": "ok", "mode": "READINESS (operative 2026-10-01)",
               "last_ok_date": None, "crawl": {"ok": 10, "queued": 10}, "counts": {"review_rules": 1, "review_pages": 3},
               "diff": {"new": [], "resolved": []},
               "rules": [{"id": "I104", "label": "installed items excluded", "triage": "review", "pages_flagged": 3}]}
    PACK = {"schema": "month-pack.v1", "month": "2026-09", "generated_at": "2026-10-01T01:12:54", "through": "2026-09-30",
            "stores": {"NOI": {"name": "Nissan of Irvine",
                               "ga4": {"coverage": {"count": 2, "days_in_month": 30, "first": "2026-09-20", "last": "2026-09-21"},
                                       "totals": {"sessions": 500, "key_events": 20, "organic_sessions": 100, "ai_sessions": 3},
                                       "clean_key_events": {"2026-09-21": 9}, "key_events_notes": ["2026-09-21: forms only"],
                                       "daily": [{"date": "2026-09-20", "sessions": 200}, {"date": "2026-09-21", "sessions": 300}]},
                               "google_ads": {"coverage": {"count": 1, "days_in_month": 30, "first": "2026-09-21", "last": "2026-09-21"},
                                              "totals": {"cost": 100.5, "clicks": 40, "conversions": 3.0},
                                              "daily": [{"date": "2026-09-21", "cost": 100.5}]},
                               "meta": {"coverage": {"count": 0}, "totals": {"spend": 0.0, "clicks": 0, "landing_page_views": 0}},
                               "crm": {"coverage": {"period_start": "2026-09-01", "period_end": "2026-09-21", "complete": False},
                                       "headline": {"leads": 400, "good_leads": 300, "appointments": 50, "shows": 30, "sold": 40,
                                                    "cost": 1000}}}}}
    try:
        PACK_STEP, AFTER_WRITE = stub, None
        os.makedirs(ROOT)
        put("outputs/ai-team/2026-09-21/brief.md", brief_new)
        put("outputs/ai-team/2026-09-21/shift-log.md", log_new)
        put("outputs/ai-team/2026-09-21/brief-slack.json", {"parent_ts": "1790000000.111111"})
        put("outputs/ai-team/2026-09-21/kobe.md", "# Kobe\nfindings\n")
        put("outputs/ai-team/2026-09-21/data/ga4_NOI.json", {"store": "NOI"})
        put("outputs/ai-team/2026-09-21/data/semrush_kw_NOI.csv", "kw,pos\nnissan,3\n")
        put("outputs/ai-team/2026-09-21/data/seo_join_NOI.json", {"rows": []})
        put("outputs/ai-team/2026-09-21/data/value_line.json", {"v": 1})
        put("outputs/ai-team/2026-09-21/data/seo_join.md", "# join\n")
        put("outputs/ai-team/2026-09-21/data/cars_NOI/summary.json", dict(cars_ok, date="2026-09-21"))
        put("outputs/ai-team/2026-09-21/data/dashboards.json", {"date": "2026-09-21"})
        put("outputs/ai-team/2026-09-21/data/vendor_ppc_ga4_NCBMW.json", {"shift_date": "2026-09-21", "rows": [], "request": {"x": 1}})
        put("outputs/ai-team/2026-09-22/brief.md", brief_old)
        put("outputs/ai-team/2026-09-22/shift-log.md", log_old)
        put("outputs/ai-team/2026-09-22/data/cars_NOI/summary.json", cars_ok)
        put("outputs/ai-team/2026-09-22/data/cars_SBMW/summary.json", dict(cars_ok, store="SBMW"))
        put("outputs/ai-team/2026-09-22/data/notes.txt", "plain\n")
        put("outputs/ai-team/2026-10-03/brief.md", "## AI Team Brief, Saturday 2026-10-03\n")
        put("outputs/ai-team/2026-10-03/data/week.json", week)
        put("outputs/ai-team/2026-10-03/data/cars_SBMW/summary.json", dict(cars_ok, store="SBMW", date="2026-10-03", status="blocked"))
        put("outputs/ai-team/2026-10-03/data/dashboards.json", {"date": "2026-10-03"})
        put("outputs/ai-team/2026-10-03/data/vendor_ppc_ga4_NCBMW.json", {"shift_date": "2026-10-03", "rows": []})
        put("outputs/ai-team/vendor-dash/2026-09-28/ncbmw-nabthat.json",
            {"windows": {"yesterday": {"status": "ok"}, "mtd": {"status": "ok"}}})
        put("outputs/ai-team/vendor-dash/2026-09-28/ncbmw-nabthat.sheet.json", {"months": []})
        put("outputs/ai-team/vendor-dash/2026-09-28/reads.jsonl", "{}\n")
        put("outputs/ai-team/vendor-dash/2026-10-02/ncbmw-nabthat.json",
            {"windows": {"yesterday": {"status": "ok"}, "mtd": {"status": "failed"}}})
        put("outputs/ai-team/vendor-dash/2026-10-02/reads.jsonl", "{}\n")
        put("outputs/ai-team/cars-sbmw/2026-09-28/pages.jsonl", "{}\n")
        put("outputs/ai-team/gm-notes/2026-09-25/NOI.md", "# GM note\n")
        put("outputs/ai-team/topics.json", {"topics": []})
        put("outputs/ai-team/ledgers/month-pack-2026-09.json", PACK)
        put("outputs/ai-team/ledgers/asks.json", {"asks": [
            {"id": "A20", "store": "NOI", "owner": "Drew", "label": "NOI pre-qualified line", "first_raised": "2026-09-21",
             "raised": ["2026-09-21", "2026-09-22"], "status": "closed", "closed_date": "2026-09-30", "win": "Line changed"},
            {"id": "A21", "store": "SBMW", "owner": "Drew", "label": "Constellation spend", "first_raised": "2026-09-21",
             "raised": ["2026-09-21"], "status": "withdrawn", "closed_date": "2026-09-25", "withdrawn_reason": "Ruling R1. Not ours."},
            {"id": "A22", "store": "MCP", "owner": "Drew", "label": "PMax narrowing", "first_raised": "2026-09-22",
             "raised": ["2026-09-22"], "status": "closed", "closed_date": "2026-10-03"},
            {"id": "A30", "store": "NOI", "owner": "Drew", "label": "October Meta", "first_raised": "2026-10-01",
             "raised": ["2026-10-01"], "status": "open"}]})
        put("outputs/ai-team/ledgers/rulings.json", {"rulings": [
            {"id": "R1", "date": "2026-09-19", "store": "SBMW", "lane": ["kobe", "luka"], "ruling": "Not our social until October.",
             "expires": "2026-10-01"},
            {"id": "R9", "date": "2026-10-02", "store": "MCP", "lane": ["shaq"], "ruling": "October ruling."}]})
        put("outputs/ai-team/ledgers/coaching.json", {"players": {"kobe": {"level": "starter", "level_history": [
            {"date": "2026-09-19", "level": "starter"}], "history": [{"date": "2026-09-21", "bounces": [{"cause": "x", "factual": True}],
                                                                       "self_caught": 1}]}}})
        put("Daily/2026-09-22.md", "---\ntype: daily-note\n---\nSee [[outputs/ai-team/2026-09-21/kobe|Kobe]] and "
            "[join](outputs/ai-team/2026-09-21/data/seo_join.md). Full brief: `outputs/ai-team/2026-09-22/brief.md`.\n")
        put(".claude/notes.md", "[[outputs/ai-team/2026-09-22/data/notes.txt]]\n")
        outside = os.path.join(tmp, "outside.txt")
        with open(outside, "w") as f:
            f.write("not in the vault\n")
        os.symlink(outside, os.path.join(ROOT, "outputs/ai-team/2026-09-21/data/link_out.txt"))

        check("month math: December to January", next_month("2026-12") == "2027-01" and prev_month("2027-01") == "2026-12"
              and month_end("2026-12") == "2026-12-31" and close_from("2026-12") == "2027-01-15"
              and month_end("2027-02") == "2027-02-28", (next_month("2026-12"), close_from("2026-12")))
        code, out = run(["--root", ROOT, "--archive-root", ARCHIVE, "due", "--date", "2026-10-01"])
        due = json.loads(out.strip().splitlines()[-1]) if code == 0 else {}
        check("due on the 1st: summary due for last month, nothing to close yet",
              due == {"summary_due": ["2026-09"], "close_due": []}, out)
        before = tree()
        code, out = run(["--root", ROOT, "--archive-root", ARCHIVE, "summary", "--month", "2026-09", "--date", "2026-10-02"])
        s = read_text(summary_path("2026-09"))
        fm = read_frontmatter(summary_path("2026-09"))
        check("summary: written as a draft with the frontmatter", code == 0 and fm.get("type") == "ai-team-month-summary"
              and fm.get("status") == "draft" and fm.get("archived") == "false" and fm.get("month") == "2026-09"
              and "monthly-summary" in fm.get("tags", ""), (code, out, fm))
        check("summary: every section is there", all(h in s for h in (
            "## Month at a glance", "## Numbers by store", "## Week by week", "## Night by night", "## Asks",
            "## Drew's rulings added", "## CARS watch", "## Team operations", "## Where the raw files went")), s[:400])
        check("summary: three things, ask ids and corrections from the new brief format",
              "[[NOI]]: Gas Models took $1,008 over the weekend for zero conversions" in s and "Needs your call: A20" in s
              and "Get someone into NOI PMAX" in s and "Yesterday's brief named the wrong page." in s, s)
        check("summary: the old 'Top 3 for Drew' format and its tip-off/whistle shift log",
              "The BMW iX3 lands in six days" in s and "Tue 9/22 (dry run)" in s and "| 95 |" in s
              and "yes (5 lost)" in s and "1790100000.000002" in s, s)
        check("summary: Slack ts from brief-slack.json, tokens from the Team row, minutes from Start and End",
              "1790000000.111111" in s and "1,500,000" in s and "shift 01:00 to 01:16 (16 min)" in s.lower(), s)
        check("summary: asks, rulings, week pack, CARS, coaching", "A20 [[NOI]]" in s and "Win: Line changed" in s
              and "A21" in s and "R1 (9/19" in s and "R9" not in s and "Week of Mon 9/28 to Fri 10/2" in s
              and "sessions 1,311 vs 1,410" in s and "I104 installed items excluded" in s and "Kobe: 1 shift coached" in s, s)
        check("summary: pack numbers and the not-archived-yet plan", "| [[NOI]] | 2 of 30 (9/20 to 9/21) | 500 |" in s
              and "Not archived yet" in s and "If it closed today" in s, s)
        check("summary: no em or en dash, and no day folder touched", EMDASH not in s and ENDASH not in s and tree() == before)
        code, out = run(["--root", ROOT, "--archive-root", ARCHIVE, "due", "--date", "2026-10-02"])
        check("due after the draft: nothing due", code == 0 and json.loads(out.strip()) == {"summary_due": [], "close_due": []}, out)

        _CARRY_CACHE.clear()
        plan = build_plan("2026-09", close_roots("2026-09"))
        got = sorted(f["path"] for f in plan["carry"])
        want = sorted(["outputs/ai-team/2026-09-21/kobe.md", "outputs/ai-team/2026-09-21/data/seo_join.md",
                       "outputs/ai-team/2026-09-21/data/vendor_ppc_ga4_NCBMW.json",
                       "outputs/ai-team/2026-09-22/data/cars_NOI/summary.json",
                       "outputs/ai-team/2026-09-22/data/cars_SBMW/summary.json",
                       "outputs/ai-team/vendor-dash/2026-09-28/ncbmw-nabthat.json",
                       "outputs/ai-team/vendor-dash/2026-09-28/ncbmw-nabthat.sheet.json"])
        check("carries: newest ok CARS per store (a newer blocked run does not count), newest valid vendor GA4, vendor-dash "
              "window and sheet, wikilink and markdown link; not dashboards (newer in October) or a .claude link",
              got == want, got)
        check("plan: Semrush files in their own zip, the symlink skipped, the backtick mention only counted",
              sorted(f["path"].rsplit("/", 1)[-1] for f in plan["semrush"]) == ["semrush_kw_NOI.csv", "seo_join_NOI.json", "value_line.json"]
              and any("link_out.txt" in x["path"] for x in plan["skipped"]) and plan["links"]["mentions"] >= 1
              and plan["links"]["wikilinks"] == 1 and plan["links"]["mdlinks"] == 1, (plan["skipped"], plan["links"]))

        code, out = run(["--root", ROOT, "--archive-root", ARCHIVE, "close", "--month", "2026-09", "--date", "2026-10-14", "--apply"])
        check("close refuses before the 15th of the next month (exit 2)", code == 2 and "too early" in out, out)
        code, out = run(["--root", ROOT, "--archive-root", ARCHIVE, "close", "--month", "2026-10", "--date", "2026-10-20",
                         "--force-early", "--apply"])
        check("close refuses a month that is not past, even with --force-early", code == 2 and "not a past month" in out, out)
        code, out = run(["--root", ROOT, "--archive-root", ARCHIVE, "close", "--month", "2026-08", "--date", "2026-10-20"])
        check("close refuses a month before the team started", code == 2, out)
        code, out = run(["--root", ROOT, "--archive-root", os.path.join(ROOT, "outputs", "arch"), "plan", "--month", "2026-09",
                         "--date", "2026-10-15"])
        check("an archive root inside the vault is refused", code == 2 and "inside the vault" in out, out)
        before = tree()
        code, out = run(["--root", ROOT, "--archive-root", ARCHIVE, "close", "--month", "2026-09", "--date", "2026-10-15"])
        code2, out2 = run(["--root", ROOT, "--archive-root", ARCHIVE, "close", "--month", "2026-09", "--date", "2026-10-14",
                           "--force-early", "--apply", "--dry-run"])
        check("dry run (the default, and --dry-run with --apply) writes and removes nothing", code == 0 and code2 == 0
              and "DRY RUN" in out and "DRY RUN" in out2 and tree() == before and not zips() and not calls, (out, out2))

        def corrupt(path):
            with open(path, "r+b") as f:
                f.seek(60)
                f.write(b"\x00" * 64)

        AFTER_WRITE = corrupt
        code, out = run(["--root", ROOT, "--archive-root", ARCHIVE, "close", "--month", "2026-09", "--date", "2026-10-15", "--apply"])
        AFTER_WRITE = None
        check("a zip that fails verification is deleted and nothing is removed", code == 1 and "did not verify" in out
              and tree() == before and not zips() and not glob.glob(os.path.join(ARCHIVE, "*", "*.manifest.json")), out)
        check("the pack step is the stub, never the real ledgers.py", calls == ["2026-09"], calls)

        ro = os.path.join(ROOT, "outputs/ai-team/2026-09-22/data")
        os.chmod(ro, 0o555)
        code, out = run(["--root", ROOT, "--archive-root", ARCHIVE, "close", "--month", "2026-09", "--date", "2026-10-15", "--apply"])
        os.chmod(ro, 0o755)
        check("a removal error is reported (exit 1) and the file stays", code == 1 and "ERROR removing" in out
              and os.path.exists(os.path.join(ro, "notes.txt")), out)
        nz = len(zips())
        code, out = run(["--root", ROOT, "--archive-root", ARCHIVE, "close", "--month", "2026-09", "--date", "2026-10-16", "--apply"])
        check("re-run after the partial failure removes what is left without a second zip", code == 0
              and len(zips()) == nz and "already in a verified zip" in out
              and not os.path.exists(os.path.join(ro, "notes.txt")), out)
        left = sorted(rel(os.path.join(dp, fn)) for dp, _d, fns in os.walk(AI()) for fn in fns
                      if re.match(r"^outputs/ai-team/2026-09-\d\d/", rel(os.path.join(dp, fn))))
        check("apply removes the originals and keeps exactly the carries and the skipped symlink",
              left == sorted(want[:5] + ["outputs/ai-team/2026-09-21/data/link_out.txt"]), left)
        check("side piles: September vendor-dash keeps its carries, cars-sbmw and gm-notes folders are gone, October untouched",
              os.path.exists(AI("vendor-dash/2026-09-28/ncbmw-nabthat.json")) and not os.path.exists(AI("vendor-dash/2026-09-28/reads.jsonl"))
              and not os.path.exists(AI("cars-sbmw/2026-09-28")) and not os.path.exists(AI("gm-notes/2026-09-25"))
              and os.path.exists(AI("vendor-dash/2026-10-02/reads.jsonl")) and os.path.exists(AI("2026-10-03/data/week.json"))
              and os.path.exists(outside))
        zs = [os.path.basename(z) for z in zips()]
        check("two zips: main and Semrush cache", zs == ["ai-team-2026-09-semrush-cache.zip", "ai-team-2026-09.zip"], zs)
        with zipfile.ZipFile(os.path.join(ARCHIVE, "2026-09", "ai-team-2026-09-semrush-cache.zip")) as zf:
            sem = sorted(n.rsplit("/", 1)[-1] for n in zf.namelist())
        check("the Semrush zip holds only the Semrush files", sem == ["semrush_kw_NOI.csv", "seo_join_NOI.json", "value_line.json"], sem)
        ex = os.path.join(tmp, "restore")
        ok = True
        for z in zips():
            with zipfile.ZipFile(z) as zf:
                zf.extractall(ex)
        for p, h in before.items():
            if h == "link" or not re.match(r"^outputs/ai-team/(?:[a-z-]+/)?2026-09-", p):
                continue
            q = os.path.join(ex, p)
            ok = ok and os.path.exists(q) and sha_file(q) == h
        check("unzip of both zips gives back every September file byte for byte (vault-relative names)", ok)
        man = load_json(os.path.join(ARCHIVE, "2026-09", "ai-team-2026-09.manifest.json"))
        idx = read_text(os.path.join(ARCHIVE, "INDEX.md"))
        check("manifest and INDEX: zip sha256, counts, restore line", man and man["zip_sha256"] == sha_file(
            os.path.join(ARCHIVE, "2026-09", "ai-team-2026-09.zip")) and man["file_count"] == len(man["files"])
            and "## ai-team-2026-09.zip" in idx and "## ai-team-2026-09-semrush-cache.zip" in idx and "unzip -o" in idx, man and man.get("removal"))
        s = read_text(summary_path("2026-09"))
        fm = read_frontmatter(summary_path("2026-09"))
        check("summary after close: final, archived, the zip listed, the carries listed, the body kept", fm.get("status") == "final"
              and fm.get("archived") == "true" and "`ai-team-2026-09.zip`" in s and "Still in the vault (7)" in s and "link_out.txt" in s
              and "The BMW iX3 lands in six days" in s and s.count("## Where the raw files went") == 1
              and EMDASH not in s, s[-2500:])
        code, out = run(["--root", ROOT, "--archive-root", ARCHIVE, "summary", "--month", "2026-09"])
        check("summary keeps an archived note instead of rebuilding it", code == 0 and "kept" in out
              and read_text(summary_path("2026-09")) == s, out)
        nz = len(zips())
        code, out = run(["--root", ROOT, "--archive-root", ARCHIVE, "close", "--month", "2026-09", "--date", "2026-10-17", "--apply"])
        check("idempotent: a closed month with nothing left is a one-line no-op", code == 0 and len(out.strip().splitlines()) == 1
              and "nothing left" in out and len(zips()) == nz and calls == ["2026-09", "2026-09"], (out, calls))
        put("outputs/ai-team/2026-10-05/data/cars_SBMW/summary.json", dict(cars_ok, store="SBMW", date="2026-10-05"))
        code, out = run(["--root", ROOT, "--archive-root", ARCHIVE, "due", "--date", "2026-10-20"])
        check("a superseded carry makes the month due again", code == 0 and json.loads(out.strip())["close_due"] == ["2026-09"], out)
        code, out = run(["--root", ROOT, "--archive-root", ARCHIVE, "close", "--month", "2026-09", "--date", "2026-10-20", "--apply"])
        check("the superseded carry leaves without a new zip (already stored)", code == 0 and len(zips()) == nz
              and not os.path.exists(AI("2026-09-22/data/cars_SBMW")) and os.path.exists(AI("2026-09-22/data/cars_NOI/summary.json")), out)
        code, out = run(["--root", ROOT, "--archive-root", ARCHIVE, "due", "--date", "2027-01-15"])
        d1 = json.loads(out.strip()) if code == 0 else {}
        code, out2 = run(["--root", ROOT, "--archive-root", ARCHIVE, "due", "--date", "2027-01-14"])
        d2 = json.loads(out2.strip()) if code == 0 else {}
        code3, out3 = run(["--root", ROOT, "--archive-root", ARCHIVE, "close", "--month", "2026-12", "--date", "2027-01-14", "--apply"])
        check("December closes from January 15: due lists 2026-12 on 1/15, not on 1/14, and close refuses on 1/14",
              "2026-12" in d1.get("close_due", []) and d1.get("summary_due") == ["2026-12"] and "2026-12" not in d2.get("close_due", [])
              and "2026-09" not in d1.get("close_due", []) and code3 == 2, (d1, d2, out3))

        # second vault: months close in order, a failed INDEX append, a symlinked side pile
        ROOT, ARCHIVE = os.path.join(tmp, "vault2"), os.path.join(tmp, "archive2")
        A2 = ["--root", ROOT, "--archive-root", ARCHIVE]
        put("outputs/ai-team/2026-09-21/brief.md", brief_new)
        put("outputs/ai-team/2026-09-21/shift-log.md", log_new)
        put("outputs/ai-team/2026-09-21/data/semrush_kw_NOI.csv", "kw,pos\nnissan,3\n")
        put("outputs/ai-team/2026-10-05/brief.md", "## AI Team Brief, Monday 2026-10-05\n")
        put("outputs/ai-team/ledgers/month-pack-2026-09.json", PACK)
        away = os.path.join(tmp, "elsewhere", "vendor-dash")
        for d in ("2026-09-28", "2026-10-02"):
            os.makedirs(os.path.join(away, d))
            with open(os.path.join(away, d, "reads.jsonl"), "w") as f:
                f.write("{}\n")
        os.symlink(away, AI("vendor-dash"))
        run(A2 + ["summary", "--month", "2026-09", "--date", "2026-10-02"])
        before2 = tree()
        code, out = run(A2 + ["close", "--month", "2026-10", "--date", "2026-11-16", "--apply"])
        code2, out2 = run(A2 + ["plan", "--month", "2026-10", "--date", "2026-11-16", "--json"])
        pj = json.loads(out2) if code2 == 0 else {}
        check("months close in order: October refuses (exit 2) while September is not archived, and plan says so",
              code == 2 and "close 2026-09 first" in out and tree() == before2 and not zips()
              and pj.get("close_allowed") is False and pj.get("close_first") == "2026-09", (out, out2[:300]))
        if not os.path.exists(os.path.join(ARCHIVE, "INDEX.md")):
            os.makedirs(os.path.join(ARCHIVE, "INDEX.md"))  # a folder where INDEX.md should be: the append fails
        code, out = run(A2 + ["close", "--month", "2026-09", "--date", "2026-10-15", "--apply"])
        check("an INDEX.md that cannot be written fails the close before removal: zips and manifests deleted, nothing "
              "removed, summary not archived", code == 1 and "FAILED" in out and tree() == before2 and not zips()
              and not glob.glob(os.path.join(ARCHIVE, "*", "*.manifest.json"))
              and read_frontmatter(summary_path("2026-09")).get("archived") == "false", out)
        if os.path.isdir(os.path.join(ARCHIVE, "INDEX.md")):
            os.rmdir(os.path.join(ARCHIVE, "INDEX.md"))
        code, out = run(A2 + ["close", "--month", "2026-09", "--date", "2026-10-15", "--apply"])
        man = load_json(os.path.join(ARCHIVE, "2026-09", "ai-team-2026-09.manifest.json")) or {}
        idx = read_text(os.path.join(ARCHIVE, "INDEX.md"))
        check("a side pile behind a symlinked folder is skipped and reported, never zipped or removed",
              code == 0 and os.path.exists(os.path.join(away, "2026-09-28", "reads.jsonl"))
              and os.path.exists(os.path.join(away, "2026-10-02", "reads.jsonl"))
              and not any("vendor-dash" in e["path"] for e in man.get("files") or [])
              and not any("vendor-dash" in p for p in man.get("source_paths") or [])
              and any(s["path"] == "outputs/ai-team/vendor-dash/2026-09-28/" and "symlink" in s["reason"]
                      for s in man.get("skipped") or [])
              and "1 skipped" in out and not os.path.exists(AI("2026-09-21")), (out, man.get("skipped")))
        check("after the INDEX failure, the next close writes both INDEX sections once",
              idx.count("## ai-team-2026-09.zip") == 1 and idx.count("## ai-team-2026-09-semrush-cache.zip") == 1
              and idx.count("# DigitalCLIQ Vault Archive index") == 1, idx[:400])
        code, out = run(A2 + ["close", "--month", "2026-10", "--date", "2026-11-16"])
        check("once September is archived, October's close is allowed", code == 0 and "DRY RUN" in out, out)
        keep_arch, ARCHIVE = ARCHIVE, os.path.join(tmp, "archive-undo")
        ip = os.path.join(ARCHIVE, "INDEX.md")
        m0 = index_mark()
        append_index("\n## a.zip\n")
        made = os.path.isfile(ip)
        index_undo(m0)
        gone = not os.path.exists(ip)
        with open(ip, "w", encoding="utf-8") as f:
            f.write("# kept\n")
        m1 = index_mark()
        append_index("\n## b.zip\n")
        index_undo(m1)
        check("a failed close takes its INDEX text back out (a new INDEX.md is removed, an older one cut back to size)",
              m0 is None and made and gone and m1 == 7 and read_text(ip) == "# kept\n", (m0, made, gone, m1, read_text(ip)))
        ARCHIVE = keep_arch

        # third vault: an older script's October close already took September's files (diverted first close)
        ROOT, ARCHIVE = os.path.join(tmp, "vault3"), os.path.join(tmp, "archive3")
        A3 = ["--root", ROOT, "--archive-root", ARCHIVE]
        put("outputs/ai-team/2026-09-21/brief.md", brief_new)
        put("outputs/ai-team/2026-09-21/shift-log.md", log_new)
        put("outputs/ai-team/2026-09-22/brief.md", brief_old)
        put("outputs/ai-team/2026-09-22/shift-log.md", log_old)
        put("outputs/ai-team/2026-10-05/brief.md", "## AI Team Brief, Monday 2026-10-05\n")
        put("outputs/ai-team/ledgers/month-pack-2026-09.json", PACK)
        put("Daily/2026-09-23.md", "---\ntype: daily-note\n---\nSee [[outputs/ai-team/2026-09-22/brief|the brief]].\n")
        run(A3 + ["summary", "--month", "2026-09", "--date", "2026-10-02"])
        draft = read_text(summary_path("2026-09"))
        _CARRY_CACHE.clear()
        old = archive_month(build_plan("2026-10", close_roots("2026-10")), "2026-10", "2026-11-16")  # no order guard
        _CARRY_CACHE.clear()
        ncalls = len(calls)
        code, out = run(A3 + ["close", "--month", "2026-09", "--date", "2026-11-17", "--apply"])
        s3 = read_text(summary_path("2026-09"))
        fm3 = read_frontmatter(summary_path("2026-09"))
        check("a month whose files a later zip took keeps its pack and summary body and never says nothing was archived",
              not old["failed"] and code == 0 and len(calls) == ncalls and "summary body kept" in out
              and fm3.get("archived") == "true" and "Gas Models took $1,008" in s3 and "The BMW iX3 lands in six days" in s3
              and "Shifts run: 2" in draft and "Shifts run: 2" in s3 and "Nothing was archived" not in s3
              and "`ai-team-2026-10.zip` (from the October 2026 close" in s3 and s3.count("Note: ") == 1
              and "this is a draft until" not in s3 and "Still in the vault (1)" in s3 and EMDASH not in s3, (out, s3[-1800:]))
        src = open(os.path.abspath(__file__), encoding="utf-8").read()
        check("script source has no em or en dash", EMDASH not in src and ENDASH not in src)
    finally:
        try:
            os.chmod(os.path.join(ROOT, "outputs/ai-team/2026-09-22/data"), 0o755)
        except OSError:
            pass
        ROOT, ARCHIVE, PACK_STEP, AFTER_WRITE = saved
        _CARRY_CACHE.clear()
        shutil.rmtree(tmp, ignore_errors=True)
    bad = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print("%s  %s%s" % ("PASS" if ok else "FAIL", name, "" if ok else "  " + str(detail)[:600]))
    print("selftest: %d/%d passed%s" % (len(results) - len(bad), len(results), "" if not bad else ", %d FAILED" % len(bad)))
    return 1 if bad else 0


# ---------------------------------------------------------------- CLI

def parser():
    ap = argparse.ArgumentParser(description="AI team month close: month summary note, then the month's raw folders "
                                             "into verified zips outside the vault.")
    ap.add_argument("--root", default=DEFAULT_ROOT, help="vault root (default: the vault this script sits in)")
    ap.add_argument("--archive-root", default=None,
                    help="archive folder outside the vault (default: $DIGITALCLIQ_ARCHIVE_ROOT or %s)" % DEFAULT_ARCHIVE)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("due", help="what is due on the shift dated D, as JSON")
    p.add_argument("--date", required=True)
    p.set_defaults(fn=cmd_due)
    p = sub.add_parser("summary", help="write the month summary note")
    p.add_argument("--month", required=True)
    p.add_argument("--date")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_summary)
    p = sub.add_parser("plan", help="what close would do, without doing it")
    p.add_argument("--month", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("close", help="close a month: final pack, final summary, zips, removal (dry run unless --apply)")
    p.add_argument("--month", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--apply", action="store_true", help="really write the zips and remove the originals")
    p.add_argument("--dry-run", action="store_true", help="force a dry run (the default without --apply)")
    p.add_argument("--force-early", action="store_true", help="allow a close before the 15th of the next month")
    p.set_defaults(fn=cmd_close)
    p = sub.add_parser("selftest", help="offline checks in a temp folder; touches nothing real")
    p.set_defaults(fn=cmd_selftest)
    return ap


def main(argv=None):
    global ROOT, ARCHIVE
    args = parser().parse_args(argv)
    ROOT = os.path.abspath(os.path.expanduser(args.root))
    ARCHIVE = os.path.abspath(os.path.expanduser(args.archive_root or os.environ.get("DIGITALCLIQ_ARCHIVE_ROOT")
                                                 or DEFAULT_ARCHIVE))
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
