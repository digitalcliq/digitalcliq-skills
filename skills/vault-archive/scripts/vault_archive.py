#!/usr/bin/env python3
"""Vault archive for the DigitalCLIQ HQ vault. Standard library only. Built 2026-10-07.

Moves old files out of the Obsidian vault into verified zips in an archive folder that sits
outside the vault, and removes the originals only after the zip has proved itself.

  A = python3 .claude/skills/vault-archive/scripts/vault_archive.py

  A plan --list FILE [--batch B] [--out REPORT.md] [--json-out FILE] [--no-readers] [--recent-days 7]
        read-only. Checks every listed path (exists, inside the vault, not protected, not Read-denied)
        and reports size, file count, .md count, inbound wikilinks / embeds / markdown links from other
        notes (Obsidian also resolves [[name]] by file name), backtick and plain-text mentions, code and
        prompt readers, files changed in the last 7 days, and whether any .fuse_hidden file is open (lsof)
  A apply --list FILE --name NAME --month YYYY-MM [--batch B] [--note T] [--apply]
        dry run by default: collects and hashes, writes nothing. --apply runs the safe removal protocol
  A selftest
        offline checks in a temp folder, touches nothing real

Global flags (before the subcommand):
  --root DIR           vault root. Default: the vault this script is installed in (HERE/../../../..)
  --archive-root DIR   default: env DIGITALCLIQ_ARCHIVE_ROOT, else ~/Desktop/DigitalCLIQ Vault Archive.
                       Refused when it sits inside the vault or under ~/Library/CloudStorage.
  --include-denied     also handle paths the vault's .claude/settings.json denies Claude from reading
                       (Read(...) rules). Drew passes this himself in Terminal; a Claude session never does.

List FILE
  Plain text: one vault-relative path per line, '#' starts a comment. A file inside a client
  deliverables folder may leave only as a proven duplicate, so it names its twin:
      Projects/NCBMW/deliverables/a_2026-07-29.xlsx  dup: Projects/NCBMW/deliverables/a_2026-07.xlsx
  JSON: a list of {"path", "batch", "category", "reason", "evidence", "duplicate_of"} (the sweep plan
  format in outputs/vault-archive/). --batch keeps one batch; apply needs --batch when the list has more.

Safe removal protocol (apply --apply). There is no Time Machine, so the zip becomes the only copy.
  1 collect regular files only. Symlinks are skipped and reported, never followed. Nothing outside the
    listed paths is touched.
  2 record sha256, size and mtime of every file
  3 write {name}.zip.partial in {archive root}/{YYYY-MM}/, close it, rename it to {name}.zip. An
    existing zip is never overwritten: the name becomes {name}-2.zip, -3, ...
  4 reopen the zip: testzip() finds nothing, every file is in it exactly once, and the sha256 of every
    decompressed member matches step 2
  5 write {name}.manifest.json (with the zip's own sha256) and append a section to {archive root}/INDEX.md
  6 only then remove the originals one at a time, re-checking size and mtime first (a file that changed
    since hashing stays and is reported), then remove the folders inside listed folders that are empty,
    bottom-up. A non-empty folder is never removed.
  7 print a summary
  Any failure before step 6 leaves every original where it was. A zip that fails step 4 is renamed
  {name}.zip.failed so nobody mistakes it for a good one.

Restore: unzip -o "{archive root}/{YYYY-MM}/{name}.zip" -d "{vault root}"
  Zip members are vault-relative POSIX paths, so the files land back where they were.

Laws: never an em dash or en dash in anything this writes; never delete before the zip verifies; never
follow a symlink; never write inside the vault (the archive root must be outside it).
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
import re
import shutil
import stat
import glob
import subprocess
import sys
import tempfile
import time
import zipfile
from urllib.parse import unquote

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
DEFAULT_ARCHIVE = os.path.join(os.path.expanduser("~"), "Desktop", "DigitalCLIQ Vault Archive")
CLOUD_STORAGE = os.path.join(os.path.expanduser("~"), "Library", "CloudStorage")
ROOT = DEFAULT_ROOT
ARCHIVE_ROOT = None          # resolved in main(); the selftest sets its own
INCLUDE_DENIED = False
EMDASH, ENDASH = chr(8212), chr(8211)  # written as chr() so this file never holds one
RECENT_DAYS = 7
CHUNK = 1 << 20
TEXT_LIMIT = 2 * 1024 * 1024  # readers scan skips files bigger than this

# Never archived. Prefixes are vault-relative and compared case-insensitively (APFS ignores case).
PROTECTED_PREFIXES = (
    "Context/", ".obsidian/", "Team/", ".claude/skills/", ".claude/agents/",
    "outputs/ai-team/",                 # month_close.py owns it
    "outputs/context-log-redesign/", "outputs/KrystalKlear/", "outputs/_qa/",
    "outputs/ncbmw-dropfolder-ingest/", "outputs/bmw-digest-generator/",
    "Second Brain Optimizer Skill/", "Automotive Intelligence Skill/",
    "Resources/brand-assets/", "Resources/automotive-guidelines/",
)
DELIVERABLES = "client deliverables folder (only a proven byte-identical duplicate may leave)"
# Pre-edit copies the optimizer keeps. A CLAUDE.md or README.md in here is a backup copy, not a live file.
COPY_ZONES = (".claude/optimizer/backups/", ".claude/optimizer/runs/")
# Notes in these folders describe archive runs; their path mentions are not readers.
SELF_DIRS = ("outputs/vault-archive/",)
GENERIC_NAMES = {"readme.md", "claude.md", "skill.md", "index.html", "index.md", "run.sh", "data.py",
                 "notes.md", "tasks.md", "summary.md", "summary.json", "findings.json", "run.json",
                 "manifest.json", "settings.json", "package.json", "build.sh", "code.gs", ".ds_store"}
READER_DIRS = (
    ".claude/skills",                                             # inside the vault
    "~/.claude/scheduled-tasks",
    "~/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/*/*/skills",
    "~/Desktop/Skills",
    "~/Desktop/digitalcliq-skills",
    "~/Claude/Scheduled",
)
READER_SKIP_DIRS = {".git", "__pycache__", "node_modules", "backups", ".venv"}

_HOOKS = {}  # the selftest plants faults here: after_hash, after_zip, before_remove


def _hook(name, *args):
    fn = _HOOKS.get(name)
    if fn:
        fn(*args)


# ---------------------------------------------------------------- small helpers

def clean(text):
    """No em or en dashes in anything this script writes."""
    return str(text).replace(EMDASH, "-").replace(ENDASH, "-")


def die(msg, code=2):
    print(clean(msg), file=sys.stderr)
    sys.exit(code)


def rel_of(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def ab_of(rel):
    return os.path.join(ROOT, *rel.split("/"))


def plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def human(n):
    n = int(n or 0)
    if n >= 1024 * 1024:
        return "%s B (%.1f MB)" % (format(n, ","), n / 1048576.0)
    if n >= 1024:
        return "%s B (%.0f KB)" % (format(n, ","), n / 1024.0)
    return "%s B" % format(n, ",")


def now_local():
    return dt.datetime.now().astimezone()


def stamp(ts=None):
    t = dt.datetime.fromtimestamp(ts).astimezone() if ts else now_local()
    return t.strftime("%Y-%m-%d %H:%M ") + (t.tzname() or "")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def inside(child, parent):
    """True when child (a real path) is parent or below it."""
    parent = parent.rstrip(os.sep)
    return child == parent or child.startswith(parent + os.sep)


def under(rel, item):
    """Vault-relative: rel is item or below it."""
    rl, il = rel.lower(), item.lower()
    return rl == il or rl.startswith(il + "/")


def is_obsidian_md(rel):
    """A .md Obsidian indexes: not inside a dot folder."""
    return rel.lower().endswith(".md") and not any(p.startswith(".") for p in rel.split("/")[:-1])


def write_atomic(path, text):
    """Write text to path.partial (refusing an existing one), then rename. Never overwrites path.
    JSON goes through json.dumps with ensure_ascii, so file names stay exact and no dash character lands."""
    if os.path.lexists(path):
        raise OSError("refusing to overwrite " + path)
    part = path + ".partial"
    fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(part, path)


# ---------------------------------------------------------------- protection and Read-deny rules

def protected_reason(rel, item_rel=None, item_is_dir=False):
    """Why a vault-relative path may not leave, or None. item_rel / item_is_dir describe the listed item
    that holds rel: a folder's README.md index may leave only together with the folder it indexes."""
    low = rel.lower()
    parts = low.split("/")
    name = parts[-1]
    if len(parts) == 1:
        return "vault root entry (list a path inside a folder)"
    for p in PROTECTED_PREFIXES:
        pl = p.lower()
        if low == pl.rstrip("/") or low.startswith(pl):
            return "protected folder " + p
    if ".git" in parts:
        return "git repository"
    copy = low.startswith(COPY_ZONES)
    if name == "claude.md" and not copy:
        return "CLAUDE.md"
    if name == "readme.md" and not copy:
        folder = "/".join(parts[:-1])
        il = (item_rel or "").lower()
        if not (item_is_dir and il and (folder == il or folder.startswith(il + "/"))):
            return "folder README.md index"
    if re.match(r"^\.claude/settings[^/]*\.json$", low):
        return "Claude settings"
    if parts[0] == "daily" and len(parts) == 2 and name.endswith(".md"):
        # A raw daily may leave only once its month archive Daily/YYYY-MM.md exists (monthly-daily-rollup).
        m = re.match(r"^(\d{4}-\d{2})-\d{2}\.md$", name)
        if not (m and os.path.isfile(os.path.join(ROOT, "Daily", m.group(1) + ".md"))):
            return "Daily note (a raw daily leaves only after its month archive Daily/YYYY-MM.md exists)"
    if name.endswith(".bak-0926"):
        return "context-log .bak-0926 (holds September entries pending restore)"
    if parts[0] == "projects":
        if name.startswith("context-log") and name.endswith(".md"):
            return "client context log"
        if "cars-act-state" in parts[1:]:
            return "CARS Act state (legal retention)"
        if "deliverables" in parts[1:]:
            return DELIVERABLES
    if parts[0] == "outputs" and "dashboard" in parts[1]:
        return "dashboard source (outputs/*dashboard*)"
    return None


def glob_re(pat):
    """Claude Code Read(...) glob to a regex over vault-relative paths."""
    p = pat[2:] if pat.startswith("./") else pat.lstrip("/")
    out, i = "", 0
    while i < len(p):
        if p.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif p.startswith("**", i):
            out += ".*"
            i += 2
        elif p[i] == "*":
            out += "[^/]*"
            i += 1
        elif p[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(p[i])
            i += 1
    return re.compile("^" + out + "$", re.I)


def load_deny(root):
    pats = []
    for fn in ("settings.json", "settings.local.json"):
        try:
            with open(os.path.join(root, ".claude", fn), encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        for rule in (d.get("permissions") or {}).get("deny") or []:
            m = re.match(r"^Read\((.+)\)$", str(rule).strip())
            if m and not m.group(1).startswith(("~", "//")):
                pats.append((m.group(1), glob_re(m.group(1))))
    return pats


DENY = []


def denied(rel):
    """The Read(...) rule that covers this file, or None."""
    if INCLUDE_DENIED:
        return None
    for raw, rx in DENY:
        if rx.match(rel):
            return raw
    return None


def subtree_denied(rel_dir):
    """The rule that covers everything under this folder (so it is never even listed), or None."""
    if INCLUDE_DENIED:
        return None
    probe = rel_dir.rstrip("/") + "/x"
    for raw, rx in DENY:
        if raw.endswith("/**") and rx.match(probe):
            return raw
    return None


# ---------------------------------------------------------------- list files

def norm_rel(raw):
    """(vault-relative POSIX path, None) or (None, why)."""
    s = raw.strip().replace("\\", "/")
    if not s:
        return None, "empty path"
    if s.startswith("/"):
        ab = os.path.normpath(s)
        if not inside(ab, os.path.normpath(ROOT)):
            return None, "outside the vault root"
        s = os.path.relpath(ab, ROOT).replace(os.sep, "/")
    while s.startswith("./"):
        s = s[2:]
    s = s.rstrip("/")
    if not s or s == "." or any(p in ("", ".", "..") for p in s.split("/")):
        return None, "not a clean vault-relative path"
    return s, None


def load_list(path, batch=None):
    """Items: [{"path", "raw", "batch", "category", "reason", "evidence", "duplicate_of", "error"}]."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as e:
        die("cannot read list %s: %s" % (path, e))
    items = []
    if path.lower().endswith(".json"):
        try:
            data = json.loads(text)
        except ValueError as e:
            die("list %s is not valid JSON: %s" % (path, e))
        if isinstance(data, dict):
            data = data.get("items") or []
        for e in data:
            if not isinstance(e, dict) or "path" not in e:
                die("every JSON list entry needs a path: %r" % (e,))
            items.append(dict(e, raw=e["path"]))
    else:
        for line in text.splitlines():
            if line.lstrip().startswith("#"):
                continue
            line = re.sub(r"\s+#\s.*$", "", line).strip()
            if not line:
                continue
            dup = None
            m = re.match(r"^(.*?)\s+dup:\s*(.+)$", line)
            if m:
                line, dup = m.group(1).strip(), m.group(2).strip()
            items.append({"path": line, "raw": line, "duplicate_of": dup})
    batches = sorted({str(i.get("batch") or "") for i in items})
    if batch:
        items = [i for i in items if str(i.get("batch") or "") == batch]
        if not items:
            die("no items in batch %r (batches: %s)" % (batch, ", ".join(b for b in batches if b) or "none"))
    for i in items:
        i["path"], i["error"] = norm_rel(i["raw"])
        if i.get("duplicate_of"):
            i["duplicate_of"], err = norm_rel(i["duplicate_of"])
            if err and not i["error"]:
                i["error"] = "duplicate_of: " + err
    return items, batches


# ---------------------------------------------------------------- collect (protocol step 1)

def collect(rel):
    """Walk one listed path without following symlinks.
    Returns {kind, files, symlinks, other, dirs, empty_dirs, denied_files, denied_dirs}."""
    res = {"kind": None, "files": [], "symlinks": [], "other": [], "dirs": [], "empty_dirs": [],
           "denied_files": [], "denied_dirs": []}
    ab = ab_of(rel)
    st = os.lstat(ab)
    if stat.S_ISLNK(st.st_mode):
        res["kind"] = "symlink"
        res["symlinks"].append(rel)
        return res
    if stat.S_ISREG(st.st_mode):
        res["kind"] = "file"
        res["files"].append(rel)
        if denied(rel):
            res["denied_files"].append(rel)
        return res
    if not stat.S_ISDIR(st.st_mode):
        res["kind"] = "other"
        res["other"].append(rel)
        return res
    res["kind"] = "dir"
    if subtree_denied(rel):
        res["denied_dirs"].append(rel)
        return res
    for dirpath, dirnames, filenames in os.walk(ab, topdown=True, followlinks=False):
        drel = rel_of(dirpath)
        res["dirs"].append(drel)
        keep = []
        for d in sorted(dirnames):
            dab = os.path.join(dirpath, d)
            drl = drel + "/" + d
            if os.path.islink(dab):
                res["symlinks"].append(drl)
            elif subtree_denied(drl):
                res["denied_dirs"].append(drl)
            else:
                keep.append(d)
        dirnames[:] = keep
        if not keep and not filenames:
            res["empty_dirs"].append(drel)
        for f in sorted(filenames):
            frl = drel + "/" + f
            mode = os.lstat(os.path.join(dirpath, f)).st_mode
            if stat.S_ISLNK(mode):
                res["symlinks"].append(frl)
            elif stat.S_ISREG(mode):
                res["files"].append(frl)
                if denied(frl):
                    res["denied_files"].append(frl)
            else:
                res["other"].append(frl)
    return res


def check_item(item, listed):
    """Validate one list item. Adds status ('ok' or 'refused'), problems, and the collect() result."""
    item["problems"], item["notes"] = [], []
    item["status"] = "refused"
    rel = item["path"]
    if item.get("error"):
        item["problems"].append(item["error"])
        return item
    real_root = os.path.realpath(ROOT)
    parent_real = os.path.realpath(os.path.dirname(ab_of(rel)))
    parts = rel.split("/")
    linked = [("/".join(parts[:i])) for i in range(1, len(parts)) if os.path.islink(ab_of("/".join(parts[:i])))]
    if linked or not inside(parent_real, real_root):
        item["problems"].append("a folder on its path is a symlink (%s); symlinks are never followed"
                                % (linked[0] if linked else "resolves outside the vault"))
        return item
    if not os.path.lexists(ab_of(rel)):
        item["problems"].append("does not exist")
        return item
    others = [o for o in listed if o is not rel and o != rel]
    for o in others:
        if under(rel, o) or under(o, rel):
            item["problems"].append("overlaps another listed path: " + o)
    res = collect(rel)
    item["collect"] = res
    is_dir = res["kind"] == "dir"
    if res["kind"] == "symlink":
        item["problems"].append("is a symlink (skipped, never followed)")
    if res["kind"] == "other":
        item["problems"].append("not a regular file or folder")
    reasons = set()
    for path in [rel] + res["files"] + res["symlinks"] + res["other"] + res["dirs"][1:]:
        why = protected_reason(path, rel, is_dir)
        if why == DELIVERABLES and path == rel and res["kind"] == "file" and item.get("duplicate_of"):
            continue  # judged by the duplicate proof below
        if why:
            reasons.add("%s: %s" % (why, path) if path != rel else why)
    if reasons:
        item["problems"].append("protected (" + "; ".join(sorted(reasons)[:6])
                                + (" and %d more" % (len(reasons) - 6) if len(reasons) > 6 else "") + ")")
    if res["denied_dirs"] or res["denied_files"]:
        rules = sorted({denied(p) or subtree_denied(p) or "" for p in res["denied_files"] + res["denied_dirs"]})
        item["problems"].append("Read-denied for Claude by .claude/settings.json (%s); Drew runs this one with "
                                "--include-denied" % ", ".join(r for r in rules if r))
    if item.get("duplicate_of") and res["kind"] == "file" and not item["problems"]:
        ok, detail = dup_proof(rel, item["duplicate_of"], listed)
        item["dup_detail"] = detail
        if not ok:
            item["problems"].append("duplicate proof failed: " + detail)
    if not item["problems"]:
        item["status"] = "ok"
    return item


def dup_proof(rel, twin, listed):
    """(ok, detail): twin is a regular file that stays in the vault and is byte-identical to rel."""
    if any(under(twin, o) for o in listed):
        return False, "the twin %s is itself listed to leave" % twin
    tab = ab_of(twin)
    if not os.path.lexists(tab):
        return False, "the twin %s does not exist" % twin
    if not stat.S_ISREG(os.lstat(tab).st_mode):
        return False, "the twin %s is not a regular file" % twin
    if denied(twin) or denied(rel):
        return False, "Read-denied, cannot hash"
    if os.path.getsize(tab) != os.path.getsize(ab_of(rel)):
        return False, "sizes differ"
    a, b = sha256_file(ab_of(rel)), sha256_file(tab)
    if a != b:
        return False, "sha256 differs (%s vs %s)" % (a[:12], b[:12])
    return True, "sha256 %s identical to %s" % (a, twin)


# ---------------------------------------------------------------- inbound links and mentions (plan)

WIKI_RE = re.compile(r"(!?)\[\[([^\[\]\n]+?)\]\]")
MDLINK_RE = re.compile(r"(!?)\[[^\]\n]*\]\(\s*(<[^>\n]+>|[^)\s]+)(?:\s+\"[^\"\n]*\")?\s*\)")
CODE_RE = re.compile(r"`[^`\n]+`")
EXT_RE = re.compile(r"^\.[a-z0-9]{1,5}$")


def item_needles(it, limit=None):
    """Strings whose appearance in a note or a script points at this item: its own path, the path of every
    file in it, and a file name when it is specific enough (a listed file's name of 10+ characters; inside a
    listed folder only names of 12+ characters that hold a digit, so 'inventory.json' is not a match)."""
    c = it.get("collect") or {}
    files = c.get("files", [])[:limit] if limit else c.get("files", [])
    out = {it["path"].lower()}
    for f in files:
        out.add(f.lower())
        base = f.rsplit("/", 1)[-1].lower()
        if base in GENERIC_NAMES:
            continue
        if c.get("kind") == "file" and len(base) >= 10:
            out.add(base)
        elif len(base) >= 12 and re.search(r"\d", base):
            out.add(base)
    return out


def vault_notes_and_index():
    """Every file Obsidian can see (no dot folders, no Read-denied subtrees) and the .md notes among them."""
    index, notes, skipped = [], [], []
    for dirpath, dirnames, filenames in os.walk(ROOT, topdown=True, followlinks=False):
        drel = rel_of(dirpath)
        drel = "" if drel == "." else drel
        keep = []
        for d in sorted(dirnames):
            drl = (drel + "/" + d) if drel else d
            if d.startswith(".") or os.path.islink(os.path.join(dirpath, d)):
                continue
            if subtree_denied(drl):
                skipped.append(drl)
                continue
            keep.append(d)
        dirnames[:] = keep
        for f in filenames:
            frl = (drel + "/" + f) if drel else f
            index.append(frl)
            if f.lower().endswith(".md") and not denied(frl):
                notes.append(frl)
    return index, notes, skipped


def link_candidates(target):
    t = target.replace("\\|", "|").split("|")[0]
    t = re.split(r"[#^]", t)[0].strip().replace("\\", "/").lstrip("/")
    if not t:
        return []
    tl = t.lower()
    ext = os.path.splitext(tl)[1]
    cands = [tl]
    if not (EXT_RE.match(ext) and ext != ".md") and not tl.endswith(".md"):
        cands = [tl + ".md", tl]
    return cands


def resolve_wiki(target, by_path, by_name):
    """Every vault file a [[target]] can resolve to (path match, path suffix, or file name)."""
    hits = set()
    for c in link_candidates(target):
        if "/" in c:
            if c in by_path:
                hits.add(by_path[c])
            else:
                hits.update(p for pl, p in by_path.items() if pl.endswith("/" + c))
        else:
            hits.update(by_name.get(c, ()))
        if hits:
            break
    return hits


def resolve_md(target, src_rel, by_path):
    t = target.strip("<>").split("#")[0].split("?")[0]
    if not t or re.match(r"^[a-z][a-z0-9+.-]*:", t, re.I):
        return set()
    t = unquote(t).replace("\\", "/")
    hits = set()
    for base in (os.path.dirname(src_rel), ""):
        cand = os.path.normpath(os.path.join(base, t.lstrip("/"))).replace(os.sep, "/").lower()
        if cand in ("", ".") or cand.startswith("../"):
            continue
        if cand in by_path:
            hits.add(by_path[cand])
        elif t.endswith("/"):  # an explicit folder link
            hits.update(p for pl, p in by_path.items() if pl.startswith(cand + "/"))
        if hits:
            break
    return hits


def scan_links(items):
    """Fill item['links'] and item['mentions'] from every other note in the vault."""
    index, notes, skipped = vault_notes_and_index()
    live = [i for i in items if i["status"] == "ok" or i.get("collect")]
    known = set(index)
    for it in live:  # files under dot folders still count as link targets when listed
        index.extend(f for f in it.get("collect", {}).get("files", []) if f not in known)
    by_path = {p.lower(): p for p in index}
    by_name = {}
    for p in index:
        by_name.setdefault(p.rsplit("/", 1)[-1].lower(), set()).add(p)
    owner = {}
    for it in live:
        for f in it.get("collect", {}).get("files", []):
            owner[f] = it
        it["links"], it["mentions"] = [], []
    needles = {}
    for it in live:
        for n in item_needles(it):
            needles.setdefault(n, set()).add(id(it))
    by_id = {id(it): it for it in live}
    rx = re.compile("|".join(re.escape(n) for n in sorted(needles, key=len, reverse=True))) if needles else None

    def owning(path):
        it = owner.get(path)
        if it:
            return it
        for x in live:
            if under(path, x["path"]):
                return x
        return None

    for src in notes:
        if any(src.lower().startswith(s) for s in SELF_DIRS):
            continue
        src_item = owning(src)
        try:
            with open(ab_of(src), encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        for n, line in enumerate(lines, 1):
            spans = []
            for m in WIKI_RE.finditer(line):
                spans.append(m.span())
                for hit in resolve_wiki(m.group(2), by_path, by_name):
                    it = owning(hit)
                    if it and it is not src_item:
                        others = sorted(by_name.get(hit.rsplit("/", 1)[-1].lower(), set()) - {hit})
                        stay = [o for o in others if not owning(o)] if "/" not in m.group(2).split("|")[0] else []
                        it["links"].append({"from": src, "line": n, "kind": "embed" if m.group(1) else "wikilink",
                                            "text": clean(m.group(0))[:160], "resolves_to": hit,
                                            "also_leaving": bool(src_item), "ambiguous_with": stay[:3]})
            for m in MDLINK_RE.finditer(line):
                spans.append(m.span())
                for hit in resolve_md(m.group(2), src, by_path):
                    it = owning(hit)
                    if it and it is not src_item:
                        it["links"].append({"from": src, "line": n, "kind": "md-embed" if m.group(1) else "md-link",
                                            "text": clean(m.group(0))[:160], "resolves_to": hit,
                                            "also_leaving": bool(src_item), "ambiguous_with": []})
            if not rx:
                continue
            low = line.lower()
            code = [m.span() for m in CODE_RE.finditer(line)]
            for m in rx.finditer(low):
                if any(a <= m.start() < b for a, b in spans):
                    continue
                kind = "backtick" if any(a <= m.start() < b for a, b in code) else "text"
                for iid in needles.get(m.group(0), ()):
                    it = by_id[iid]
                    if it is src_item:
                        continue
                    if it["mentions"] and it["mentions"][-1]["from"] == src and it["mentions"][-1]["line"] == n:
                        continue
                    it["mentions"].append({"from": src, "line": n, "kind": kind, "match": m.group(0),
                                           "also_leaving": bool(src_item)})
    return {"notes_scanned": len(notes), "files_indexed": len(index), "denied_subtrees_skipped": skipped}


def expand_reader_dirs():
    out = []
    for d in READER_DIRS:
        if d.startswith("~"):
            out.extend(sorted(glob.glob(os.path.expanduser(d))))
        else:
            out.append(os.path.join(ROOT, d))
    return [d for d in out if os.path.isdir(d) and not inside(os.path.realpath(d), os.path.realpath(CLOUD_STORAGE))]


def scan_readers(items):
    """Code and prompt files (skills, scheduled tasks, plugin runtime, Desktop sources) naming an item."""
    live = [i for i in items if i.get("collect")]
    needles = {}
    for it in live:
        it["readers"] = []
        for n in item_needles(it, limit=400):
            needles.setdefault(n, set()).add(id(it))
    if not needles:
        return {"dirs": [], "files_scanned": 0}
    by_id = {id(it): it for it in live}
    rx = re.compile("|".join(re.escape(n) for n in sorted(needles, key=len, reverse=True)))
    dirs = expand_reader_dirs()
    seen, scanned = set(), 0
    home = os.path.expanduser("~")
    for top in dirs:
        for dirpath, dirnames, filenames in os.walk(top, topdown=True, followlinks=False):
            dirnames[:] = [d for d in dirnames if d not in READER_SKIP_DIRS
                           and not os.path.islink(os.path.join(dirpath, d))]
            for f in filenames:
                p = os.path.join(dirpath, f)
                real = os.path.realpath(p)
                if real in seen or os.path.islink(p):
                    continue
                seen.add(real)
                try:
                    if os.path.getsize(p) > TEXT_LIMIT:
                        continue
                    with open(p, "rb") as fh:
                        raw = fh.read()
                except OSError:
                    continue
                if b"\0" in raw[:4096]:
                    continue
                scanned += 1
                text = raw.decode("utf-8", "replace").lower()
                if not rx.search(text):
                    continue
                for n, line in enumerate(text.splitlines(), 1):
                    for m in rx.finditer(line):
                        for iid in needles[m.group(0)]:
                            it = by_id[iid]
                            shown = p.replace(home, "~", 1)
                            if len(it["readers"]) < 40 and not any(r["file"] == shown and r["line"] == n for r in it["readers"]):
                                it["readers"].append({"file": shown, "line": n, "match": m.group(0)})
    return {"dirs": [d.replace(home, "~", 1) for d in dirs], "files_scanned": scanned}


def lsof_open(abs_paths):
    """{path: True/False}, or None when lsof is missing or fails."""
    if not abs_paths:
        return {}
    exe = shutil.which("lsof") or "/usr/sbin/lsof"
    if not os.path.exists(exe):
        return None
    try:
        r = subprocess.run([exe, "-Fn", "--"] + list(abs_paths), capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    opened = {line[1:] for line in r.stdout.splitlines() if line.startswith("n")}
    return {p: (p in opened or os.path.realpath(p) in opened) for p in abs_paths}


def is_fuse(rel):
    return rel.rsplit("/", 1)[-1].startswith(".fuse_hidden")


# ---------------------------------------------------------------- plan

def describe(it, recent_days):
    res = it.get("collect") or {}
    files = res.get("files", [])
    sizes, recent = 0, []
    cutoff = time.time() - recent_days * 86400
    for f in files:
        st = os.lstat(ab_of(f))
        sizes += st.st_size
        if st.st_mtime >= cutoff:
            recent.append({"path": f, "mtime": stamp(st.st_mtime)})
    it["file_count"] = len(files)
    it["bytes"] = sizes
    it["md_count"] = sum(1 for f in files if f.lower().endswith(".md"))
    it["md_obsidian"] = sum(1 for f in files if is_obsidian_md(f))
    it["recent"] = recent
    fuse = [f for f in files if is_fuse(f)]
    if fuse:
        state = lsof_open([ab_of(f) for f in fuse])
        it["fuse_open"] = None if state is None else sorted(rel_of(p) for p, o in state.items() if o)
        it["fuse_count"] = len(fuse)


def cmd_plan(a):
    items, batches = load_list(a.list, a.batch)
    listed = [i["path"] for i in items if i["path"]]
    for it in items:
        check_item(it, listed)
        if it.get("collect"):
            describe(it, a.recent_days)
    scan = scan_links(items)
    readers = scan_readers(items) if not a.no_readers else {"dirs": [], "files_scanned": 0, "skipped": True}
    report = plan_markdown(items, a, scan, readers)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(clean(report))
    if a.json_out:
        slim = []
        for it in items:
            d = {k: v for k, v in it.items() if k != "collect"}
            c = it.get("collect") or {}
            d["files"] = c.get("files", [])
            d["symlinks"] = c.get("symlinks", [])
            d["denied_dirs"] = c.get("denied_dirs", [])
            d["denied_files"] = c.get("denied_files", [])
            d["empty_dirs"] = c.get("empty_dirs", [])
            slim.append(d)
        with open(a.json_out, "w", encoding="utf-8") as fh:
            fh.write((json.dumps({"generated": stamp(), "root": ROOT, "list": os.path.abspath(a.list),
                                       "batch": a.batch, "scan": scan, "readers": readers, "items": slim},
                                      indent=1)))
    ok = [i for i in items if i["status"] == "ok"]
    print("plan: %d items, %d ok, %d refused; %d files, %s; %d .md leave Obsidian; %d links would go dead; "
          "%d with edits in the last %d days%s" % (
              len(items), len(ok), len(items) - len(ok), sum(i.get("file_count", 0) for i in ok),
              human(sum(i.get("bytes", 0) for i in ok)), sum(i.get("md_obsidian", 0) for i in ok),
              sum(dead_links(i) for i in ok), sum(1 for i in ok if i.get("recent")), a.recent_days,
              (", report " + a.out) if a.out else ""))
    for it in items:
        if it["status"] != "ok":
            print(clean("  refused %s: %s" % (it["raw"], "; ".join(it["problems"]))))


def plan_markdown(items, a, scan, readers):
    today = dt.date.today().isoformat()
    groups = {}
    for it in items:
        groups.setdefault(str(it.get("batch") or "list"), []).append(it)
    L = ["---", "type: vault-archive-plan", "date: %s" % today, "status: draft",
         "tags: [vault-archive, archive-plan, cleanup]", "---", "",
         "# Vault archive plan, %s" % today, "",
         "Read-only check by `vault_archive.py plan` (nothing was moved, zipped or deleted).", "",
         "- Vault: `%s`" % ROOT,
         "- List: `%s`%s" % (a.list, (" (batch %s)" % a.batch) if a.batch else ""),
         "- Notes scanned for inbound links: %d (dot folders skipped, as Obsidian does)" % scan["notes_scanned"],
         ]
    if scan["denied_subtrees_skipped"]:
        L.append("- Not scanned (Read-denied for Claude): " + ", ".join("`%s`" % s for s in scan["denied_subtrees_skipped"]))
    if readers.get("skipped"):
        L.append("- Readers scan: skipped (--no-readers)")
    else:
        L.append("- Readers scanned: %d text files in %s" % (readers["files_scanned"], ", ".join(
            "`%s`" % d for d in readers["dirs"])))
    L += ["", "## Totals per batch", "",
          "| Batch | Items ok | Refused | Files | Bytes | .md leaving Obsidian | Links that would go dead | Items with recent edits |",
          "|---|---|---|---|---|---|---|---|"]
    for g, its in groups.items():
        ok = [i for i in its if i["status"] == "ok"]
        L.append("| %s | %d | %d | %d | %s | %d | %d | %d |" % (
            g, len(ok), len(its) - len(ok), sum(i.get("file_count", 0) for i in ok),
            human(sum(i.get("bytes", 0) for i in ok)), sum(i.get("md_obsidian", 0) for i in ok),
            sum(dead_links(i) for i in ok), sum(1 for i in ok if i.get("recent"))))
    L += ["", "Per item below: extra lines appear only for links, mentions, code or prompt readers, recent edits, "
          "symlinks or open files. No extra line means none were found."]
    for g, its in groups.items():
        L += ["", "## Batch: %s" % g, ""]
        for it in its:
            L += item_lines(it, a.recent_days)
    return "\n".join(clean(x) for x in L) + "\n"


def dead_links(it):
    return sum(1 for l in it.get("links") or [] if not l["ambiguous_with"] and not l["also_leaving"])


def item_lines(it, recent_days):
    head = "- `%s`" % it["raw"]
    if it.get("category"):
        head += " (%s)" % it["category"]
    if it["status"] != "ok":
        out = [head + ": **refused**. " + "; ".join(it["problems"])]
    else:
        out = [head + ": ok. %s, %s%s." % (
            plural(it["file_count"], "file"), human(it["bytes"]),
            (", %d .md (%d indexed by Obsidian)" % (it["md_count"], it["md_obsidian"])) if it["md_count"] else "")]
    if it.get("reason"):
        out.append("  - Why it can leave: " + it["reason"])
    if it.get("dup_detail"):
        out.append("  - Duplicate proof: " + it["dup_detail"])
    c = it.get("collect") or {}
    if c.get("symlinks"):
        out.append("  - Symlinks skipped: " + ", ".join("`%s`" % s for s in c["symlinks"][:5]))
    if c.get("empty_dirs"):
        out.append("  - Empty folders inside: %d" % len(c["empty_dirs"]))
    if "fuse_open" in it:
        fo = it["fuse_open"]
        out.append("  - .fuse_hidden files: %d, open now: %s" % (
            it["fuse_count"], "unknown (lsof failed)" if fo is None else (", ".join(fo) if fo else "none (lsof)")))
    if it.get("recent"):
        out.append("  - Changed in the last %d days: " % recent_days + ", ".join(
            "`%s` %s" % (r["path"], r["mtime"]) for r in it["recent"][:5])
            + (" and %d more" % (len(it["recent"]) - 5) if len(it["recent"]) > 5 else ""))
    links = it.get("links") or []
    dead = [l for l in links if not l["ambiguous_with"] and not l["also_leaving"]]
    soft = [l for l in links if l not in dead]
    if dead:
        out.append("  - Inbound links that go dead unless repointed first (%d):" % len(dead))
        for l in dead[:8]:
            out.append("    - `%s:%d` %s `%s`" % (l["from"], l["line"], l["kind"], l["text"].replace("`", "'")))
        if len(dead) > 8:
            out.append("    - and %d more" % (len(dead) - 8))
    soft = [l for l in soft if l["resolves_to"].rsplit("/", 1)[-1].lower() not in GENERIC_NAMES]
    for l in soft[:4]:
        why = ("the linking note leaves in this list too" if l["also_leaving"] else
               "a file with the same name stays at `%s`, so the link resolves there afterwards" % l["ambiguous_with"][0])
        out.append("  - Link that keeps working: `%s:%d` `%s` (%s)" % (l["from"], l["line"], l["text"].replace("`", "'"), why))
    ments = it.get("mentions") or []
    if ments:
        bt = sum(1 for m in ments if m["kind"] == "backtick")
        out.append("  - Mentions (text only, nothing breaks): %d backtick, %d plain: %s" % (
            bt, len(ments) - bt, ", ".join("`%s:%d`" % (m["from"], m["line"]) for m in ments[:5])
            + (" and %d more" % (len(ments) - 5) if len(ments) > 5 else "")))
    rd = it.get("readers") or []
    if rd:
        out.append("  - Named in code or prompts (%d): %s" % (len(rd), ", ".join(
            "`%s:%d`" % (r["file"], r["line"]) for r in rd[:5]) + (" and more" if len(rd) > 5 else "")))
    return out


# ---------------------------------------------------------------- apply (the safe removal protocol)

def check_archive_root(arch):
    real = os.path.realpath(arch)
    if inside(real, os.path.realpath(ROOT)) or inside(os.path.realpath(ROOT), real):
        die("archive root %s overlaps the vault %s; it must sit outside the vault" % (arch, ROOT))
    if inside(real, os.path.realpath(CLOUD_STORAGE)):
        die("archive root %s is under ~/Library/CloudStorage, which is off limits" % arch)
    return real


def pick_name(month_dir, name):
    n = 1
    while True:
        base = name if n == 1 else "%s-%d" % (name, n)
        if not any(os.path.lexists(os.path.join(month_dir, base + s))
                   for s in (".zip", ".zip.partial", ".zip.failed", ".manifest.json", ".manifest.json.partial")):
            return base
        n += 1


def zip_time(ts):
    t = time.localtime(ts)[:6]
    return t if t[0] >= 1980 else (1980, 1, 1, 0, 0, 0)


def hash_records(files):
    """Protocol step 2. A file that changes while being hashed stops the run."""
    recs = []
    for f in files:
        ab = ab_of(f)
        st1 = os.lstat(ab)
        digest = sha256_file(ab)
        st2 = os.lstat(ab)
        if (st1.st_size, st1.st_mtime_ns) != (st2.st_size, st2.st_mtime_ns):
            raise RuntimeError("%s changed while it was being hashed" % f)
        recs.append({"path": f, "size": st2.st_size, "mtime": stamp(st2.st_mtime), "mtime_ns": st2.st_mtime_ns,
                     "mode": stat.S_IMODE(st2.st_mode), "sha256": digest})
    return recs


def write_zip(partial, recs):
    """Protocol step 3 (first half): stream every file into a new .partial; refuses an existing one."""
    fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "wb") as fh:
        zf = zipfile.ZipFile(fh, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True)
        for r in recs:
            zi = zipfile.ZipInfo(r["path"], date_time=zip_time(r["mtime_ns"] / 1e9))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = ((stat.S_IFREG | r["mode"]) & 0xFFFF) << 16
            with open(ab_of(r["path"]), "rb") as src, zf.open(zi, "w", force_zip64=True) as dst:
                shutil.copyfileobj(src, dst, CHUNK)
        zf.close()
        fh.flush()
        os.fsync(fh.fileno())


def verify_zip(path, recs):
    """Protocol step 4. (ok, why)."""
    try:
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            if bad is not None:
                return False, "testzip() reports a bad member: %s" % bad
            names = zf.namelist()
            want = {r["path"]: r for r in recs}
            counts = {}
            for n in names:
                counts[n] = counts.get(n, 0) + 1
            dupes = [n for n, c in counts.items() if c > 1]
            if dupes:
                return False, "members appear more than once: %s" % ", ".join(dupes[:3])
            missing = sorted(set(want) - set(names))
            extra = sorted(set(names) - set(want))
            if missing or extra:
                return False, "member list differs from the manifest (missing %s, extra %s)" % (missing[:3], extra[:3])
            for n in names:
                h = hashlib.sha256()
                size = 0
                with zf.open(n) as fh:
                    for block in iter(lambda: fh.read(CHUNK), b""):
                        h.update(block)
                        size += len(block)
                if size != want[n]["size"] or h.hexdigest() != want[n]["sha256"]:
                    return False, "%s in the zip does not match the original (sha256 or size)" % n
    except Exception as e:  # BadZipFile, zlib.error (a bad deflate stream), EOFError, OSError: all a failed verify
        return False, "cannot read the zip back: %s: %s" % (type(e).__name__, e)
    return True, "%d members, every sha256 matches" % len(names)


def append_index(arch, manifest, note):
    path = os.path.join(arch, "INDEX.md")
    zip_rel = "%s/%s" % (manifest["month"], manifest["zip"])
    srcs = manifest["sources"]
    lines = []
    if not os.path.exists(path):
        lines += ["# DigitalCLIQ Vault Archive index", "",
                  "One section per zip, oldest first. Each zip holds vault-relative paths, so the restore line "
                  "puts files back exactly where they were in the vault.", ""]
    lines += ["## %s" % zip_rel, "",
              "- Created: %s by vault_archive.py apply" % manifest["created"],
              "- What: %s" % note,
              "- Source paths (%d): %s" % (len(srcs), ", ".join("`%s`" % s for s in srcs)),
              "- Files: %d. Bytes before: %s. Zip: %s." % (manifest["file_count"], format(manifest["bytes_before"], ","),
                                                          format(manifest["zip_bytes"], ",")),
              "- Zip sha256: `%s`" % manifest["zip_sha256"],
              "- Manifest: `%s/%s`" % (manifest["month"], manifest["manifest"]),
              "- Restore everything: `unzip -o \"%s\" -d \"%s\"`" % (manifest["zip_path"], manifest["vault_root"]),
              "- Restore one file: `unzip -o \"%s\" \"<vault-relative path>\" -d \"%s\"`" % (
                  manifest["zip_path"], manifest["vault_root"])]
    if manifest.get("skipped_symlinks"):
        lines.append("- Symlinks skipped (left in the vault): " + ", ".join("`%s`" % s for s in manifest["skipped_symlinks"]))
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(clean("\n".join(lines)) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def append_index_line(arch, text):
    with open(os.path.join(arch, "INDEX.md"), "a", encoding="utf-8") as fh:
        fh.write(clean(text) + "\n\n")


def cmd_apply(a):
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", a.name or ""):
        die("--name must be letters, digits, dot, dash or underscore (no slashes): %r" % a.name)
    if a.name.lower().endswith(".zip"):
        die("--name is the base name, without .zip")
    try:
        dt.date.fromisoformat(a.month + "-01")
        assert re.match(r"^\d{4}-\d{2}$", a.month)
    except (ValueError, AssertionError, TypeError):
        die("--month must be YYYY-MM: %r" % a.month)
    arch = check_archive_root(ARCHIVE_ROOT)
    items, batches = load_list(a.list, a.batch)
    if a.list.lower().endswith(".json") and not a.batch and len([b for b in batches if b]) > 1:
        die("this list holds %d batches (%s); apply one at a time with --batch" % (
            len(batches), ", ".join(batches)))
    if not items:
        die("the list is empty")
    listed = [i["path"] for i in items if i["path"]]
    for it in items:
        check_item(it, listed)
    bad = [i for i in items if i["status"] != "ok"]
    if bad:
        for it in bad:
            print(clean("refused %s: %s" % (it["raw"], "; ".join(it["problems"]))), file=sys.stderr)
        die("apply stopped: %d of %d listed paths refused. Nothing was written or removed." % (len(bad), len(items)))

    # 1 collect
    files, symlinks, other, dir_items, empty_dirs = [], [], [], [], []
    for it in items:
        c = it["collect"]
        files += c["files"]
        symlinks += c["symlinks"]
        other += c["other"]
        empty_dirs += c["empty_dirs"]
        if c["kind"] == "dir":
            dir_items.append(it)
    if len(set(files)) != len(files):
        die("a file is listed twice. Nothing was written or removed.")
    if not files:
        die("no regular files to archive (symlinks skipped: %d). Nothing was written." % len(symlinks))
    # 2 hash
    try:
        recs = hash_records(files)
    except (OSError, RuntimeError) as e:
        die("hashing stopped: %s. Nothing was written or removed." % e)
    _hook("after_hash", recs)
    twins = {}
    for it in items:
        if it.get("duplicate_of"):
            ok, detail = dup_proof(it["path"], it["duplicate_of"], listed)
            if not ok:
                die("duplicate proof for %s failed at hashing time: %s. Nothing was written." % (it["path"], detail))
            twins[it["path"]] = it["duplicate_of"]
    total = sum(r["size"] for r in recs)
    month_dir = os.path.join(arch, a.month)
    base = pick_name(month_dir, a.name) if os.path.isdir(month_dir) else a.name
    note = clean(a.note or ", ".join(sorted({str(i.get("category") or "") for i in items if i.get("category")}))
                 or "listed paths")
    print("%s: %d files, %s, from %d listed paths; %d symlinks skipped%s" % (
        "apply" if a.apply else "dry run", len(recs), human(total), len(items), len(symlinks),
        (", %d other entries skipped" % len(other)) if other else ""))
    print("  zip: %s" % os.path.join(month_dir, base + ".zip"))
    if not a.apply:
        for s in symlinks:
            print("  symlink skipped: " + s)
        print("dry run: nothing written, nothing removed. Add --apply to archive and remove.")
        return 0

    # 3 write the zip
    os.makedirs(month_dir, exist_ok=True)
    base = pick_name(month_dir, a.name)
    partial = os.path.join(month_dir, base + ".zip.partial")
    final = os.path.join(month_dir, base + ".zip")
    try:
        write_zip(partial, recs)
        if os.path.lexists(final):
            raise OSError("%s appeared while writing; not overwriting it" % final)
        os.replace(partial, final)
    except (OSError, zipfile.LargeZipFile, RuntimeError) as e:
        die("writing the zip failed: %s. Originals untouched; the .partial (if any) is left for a look." % e, 3)
    _hook("after_zip", final)
    # 4 verify
    ok, why = verify_zip(final, recs)
    if not ok:
        failed = final + ".failed"
        os.replace(final, failed)
        die("verify failed: %s. Originals untouched. The bad zip is kept as %s." % (why, failed), 3)
    print("  verified: " + why)
    # 5 manifest and INDEX.md
    zip_sha = sha256_file(final)
    manifest = {
        "name": base, "zip": base + ".zip", "manifest": base + ".manifest.json", "zip_path": final,
        "zip_sha256": zip_sha, "zip_bytes": os.path.getsize(final), "month": a.month, "created": stamp(),
        "vault_root": ROOT, "what": note, "sources": [i["path"] for i in items],
        "duplicates": twins, "file_count": len(recs), "bytes_before": total,
        "files": recs, "skipped_symlinks": symlinks, "skipped_other": other, "empty_dirs": empty_dirs,
        "restore": "unzip -o \"%s\" -d \"%s\"" % (final, ROOT),
        "tool": "vault_archive.py apply",
    }
    try:
        write_atomic(os.path.join(month_dir, base + ".manifest.json"), json.dumps(manifest, indent=1))
        append_index(arch, manifest, note)
    except OSError as e:
        die("writing the manifest or INDEX.md failed: %s. Originals untouched; the verified zip stays at %s." % (e, final), 3)
    print("  manifest: %s" % os.path.join(month_dir, base + ".manifest.json"))
    _hook("before_remove", recs)

    # 6 remove originals, then empty folders inside listed folders
    removed, kept = [], []
    fuse_paths = [ab_of(r["path"]) for r in recs if is_fuse(r["path"])]
    fuse_state = lsof_open(fuse_paths)
    if fuse_state is None:
        fuse_state = {p: "unknown" for p in fuse_paths}
    for r in recs:
        ab = ab_of(r["path"])
        try:
            st = os.lstat(ab)
        except OSError:
            kept.append((r["path"], "gone before removal"))
            continue
        if not stat.S_ISREG(st.st_mode):
            kept.append((r["path"], "no longer a regular file"))
            continue
        if (st.st_size, st.st_mtime_ns) != (r["size"], r["mtime_ns"]):
            kept.append((r["path"], "changed since hashing (size or mtime)"))
            continue
        if fuse_state.get(ab):
            kept.append((r["path"], "open in another process (lsof)" if fuse_state[ab] is True
                         else "lsof could not say whether it is open"))
            continue
        twin = twins.get(r["path"])
        if twin:
            tab = ab_of(twin)
            try:
                same = stat.S_ISREG(os.lstat(tab).st_mode) and sha256_file(tab) == r["sha256"]
            except OSError:
                same = False
            if not same:
                kept.append((r["path"], "its twin %s is gone or no longer identical" % twin))
                continue
        try:
            os.remove(ab)
            removed.append(r["path"])
        except OSError as e:
            kept.append((r["path"], "remove failed: %s" % e))
    dirs_removed, dirs_left = [], []
    for it in dir_items:
        for d in reversed(it["collect"]["dirs"]):
            dab = ab_of(d)
            if os.path.islink(dab) or not os.path.isdir(dab):
                continue
            try:
                if os.listdir(dab):
                    dirs_left.append(d)
                    continue
                os.rmdir(dab)
                dirs_removed.append(d)
            except OSError:
                dirs_left.append(d)
    # 7 summary
    append_index_line(arch, "- Removed from the vault %s: %d of %d files, %d folders; kept %d%s." % (
        stamp(), len(removed), len(recs), len(dirs_removed), len(kept),
        (" (" + "; ".join("%s: %s" % k for k in kept[:5]) + ")") if kept else ""))
    print("removed %d of %d files and %d empty folders; kept %d; zip %s (%s, sha256 %s)" % (
        len(removed), len(recs), len(dirs_removed), len(kept), final, human(manifest["zip_bytes"]), zip_sha[:16]))
    for path, why in kept:
        print(clean("  kept %s: %s" % (path, why)))
    for d in dirs_left:
        print("  folder left (not empty): " + d)
    for s in symlinks:
        print("  symlink skipped: " + s)
    return 0


# ---------------------------------------------------------------- selftest

def cmd_selftest(_args):
    global ROOT, ARCHIVE_ROOT, INCLUDE_DENIED, DENY
    saved = (ROOT, ARCHIVE_ROOT, INCLUDE_DENIED, DENY)
    tmp = tempfile.mkdtemp(prefix="vault-archive-selftest-")
    results = []

    def check(name, cond, detail=""):
        results.append((name, bool(cond), detail))

    import contextlib

    def run(fn, **kw):
        """(exit code, stdout+stderr) of one command, never raising."""
        buf = io.StringIO()
        code = 0
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                code = fn(argparse.Namespace(**kw)) or 0
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        return code, buf.getvalue()

    def put(rel, text="x", mtime=None):
        p = os.path.join(ROOT, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        if mtime:
            os.utime(p, (mtime, mtime))
        return p

    def write_list(name, lines):
        p = os.path.join(tmp, name)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        return p

    def zips():
        out = []
        for dp, _dn, fn in os.walk(ARCHIVE_ROOT):
            out += [os.path.join(dp, f) for f in fn if ".zip" in f]
        return sorted(out)

    def ap(lst, name, apply=True, batch=None):
        return run(cmd_apply, list=lst, batch=batch, name=name, month="2026-09", note=None, apply=apply)

    try:
        ROOT = os.path.join(tmp, "vault")
        ARCHIVE_ROOT = os.path.join(tmp, "archive")
        INCLUDE_DENIED = False
        old = time.time() - 40 * 86400
        body = "line of staging text that compresses well\n" * 200
        put(".claude/settings.json", json.dumps({"permissions": {"deny": ["Read(./Secret/**)", "Read(**/*.mp3)"]}}))
        DENY = load_deny(ROOT)
        put("Context/rules.md", "# rules\n", old)
        put("Daily/2026-09-01.md", "# day\n", old)
        put("Daily/2026-08-15.md", "# day\n", old)
        put("Daily/2026-08.md", "# month archive\n", old)
        put("outputs/old/a.md", "# a\n" + body, old)
        put("outputs/old/sub/b.json", '{"b": 1}\n' + body, old)
        os.makedirs(os.path.join(ROOT, "outputs", "old", "sub", "empty"))
        put("outputs/old/README.md", "# index of old\n", old)
        put("outputs/loose_report_2026-09-18.csv", "a,b\n1,2\n" + body, old)
        put("outputs/keep.md", "# keep me\n", old)
        put("outputs/ai-team/2026-09-01/brief.md", "# brief\n", old)
        put("outputs/withclaude/CLAUDE.md", "# rules\n", old)
        put("outputs/withclaude/x.md", "# x\n", old)
        put("outputs/voice.mp3", "not really audio", old)
        put("Secret/s.md", "# secret\n", old)
        put("Projects/X/deliverables/a_2026-07-29.xlsx", "same bytes", old)
        put("Projects/X/deliverables/a_2026-07.xlsx", "same bytes", old)
        put("Projects/X/deliverables/c.xlsx", "other bytes", old)
        put("Projects/X/context-log.md", "# log\n", old)
        put(".claude/optimizer/backups/20260801-000000/Daily/CLAUDE.md", "# copy\n", old)
        put(".claude/optimizer/backups/20260801-000000/Projects/X/context-log.md", "# copy\n", old)
        os.symlink(os.path.join(ROOT, "Context", "rules.md"), os.path.join(ROOT, "outputs", "old", "link_out.md"))
        os.symlink(os.path.join(ROOT, "Context"), os.path.join(ROOT, "outputs", "old", "linkdir"))
        put("Notes/linker.md", "See [[a]] and ![[outputs/old/sub/b.json]] and [csv](../outputs/loose_report_2026-09-18.csv)"
                               " and `outputs/old/a.md` and plain outputs/keep.md\n")
        put("Notes/fresh.md", "# fresh\n")
        put("outputs/old/dupname.md", "# leaving copy\n", old)
        put("Elsewhere/dupname.md", "# staying copy\n", old)
        put("Notes/linker2.md", "Also [[dupname]].\n")
        put("outputs/realdir/x.md", "# x\n", old)
        os.symlink(os.path.join(ROOT, "outputs", "realdir"), os.path.join(ROOT, "outputs", "linkparent"))
        rules_sha = sha256_file(os.path.join(ROOT, "Context", "rules.md"))

        # plan
        lst = write_list("plan.txt", ["outputs/old", "outputs/loose_report_2026-09-18.csv", "Context/rules.md",
                                      "outputs/ai-team/2026-09-01", "Daily/2026-09-01.md", "outputs/withclaude", "Daily/2026-08-15.md",
                                      "Secret/s.md", "outputs/voice.mp3", "../etc/passwd", "/etc/hosts",
                                      "Projects/X/deliverables/a_2026-07-29.xlsx  dup: Projects/X/deliverables/a_2026-07.xlsx",
                                      "Projects/X/deliverables/c.xlsx  dup: Projects/X/deliverables/a_2026-07.xlsx",
                                      "Notes/fresh.md", "Notes/missing.md", "outputs/linkparent/x.md",
                                      ".claude/optimizer/backups/20260801-000000"])
        out_md, out_js = os.path.join(tmp, "plan.md"), os.path.join(tmp, "plan.json")
        code, o = run(cmd_plan, list=lst, batch=None, out=out_md, json_out=out_js, no_readers=True, recent_days=7)
        js = json.load(open(out_js, encoding="utf-8"))
        st = {i["raw"].split("  dup:")[0]: i for i in js["items"]}
        check("plan exits 0 and writes both reports", code == 0 and os.path.exists(out_md), o)
        check("plan: plain staging folder and file are ok",
              st["outputs/old"]["status"] == "ok" and st["outputs/loose_report_2026-09-18.csv"]["status"] == "ok", o)
        check("plan: protected paths refused (Context, ai-team, Daily note, CLAUDE.md inside a folder)",
              all(st[p]["status"] == "refused" for p in ("Context/rules.md", "outputs/ai-team/2026-09-01",
                                                          "Daily/2026-09-01.md", "outputs/withclaude")))
        check("plan: a raw daily is ok once its month archive exists, the month archive itself stays refused",
              st["Daily/2026-08-15.md"]["status"] == "ok" and protected_reason("Daily/2026-08.md") is not None)
        check("plan: a folder's own README.md may leave with the folder", "README" not in " ".join(st["outputs/old"]["problems"]))
        check("plan: Read-denied paths refused without --include-denied",
              st["Secret/s.md"]["status"] == "refused" and st["outputs/voice.mp3"]["status"] == "refused"
              and "Read-denied" in " ".join(st["Secret/s.md"]["problems"]))
        check("plan: paths outside the vault refused",
              st["../etc/passwd"]["status"] == "refused" and st["/etc/hosts"]["status"] == "refused")
        check("plan: proven duplicate in deliverables ok, different bytes refused",
              st["Projects/X/deliverables/a_2026-07-29.xlsx"]["status"] == "ok"
              and st["Projects/X/deliverables/c.xlsx"]["status"] == "refused",
              [st[k]["problems"] for k in st if k.startswith("Projects")])
        code, o = run(cmd_plan, list=write_list("deliv.txt", [
            "Projects/X/deliverables/a_2026-07.xlsx",
            "Projects/X/deliverables/a_2026-07-29.xlsx  dup: Projects/X/deliverables/a_2026-07.xlsx"]),
            batch=None, out=None, json_out=None, no_readers=True, recent_days=7)
        check("plan: deliverable without a twin refused, and a twin that also leaves voids the proof",
              "0 ok, 2 refused" in o and "itself listed to leave" in o, o)
        check("plan: missing path refused", st["Notes/missing.md"]["status"] == "refused")
        check("plan: an optimizer backup set may leave with its CLAUDE.md and context-log copies",
              st[".claude/optimizer/backups/20260801-000000"]["status"] == "ok"
              and st[".claude/optimizer/backups/20260801-000000"]["md_obsidian"] == 0,
              st[".claude/optimizer/backups/20260801-000000"]["problems"])
        check("plan: a path through a symlinked folder refused",
              st["outputs/linkparent/x.md"]["status"] == "refused" and "symlink" in " ".join(st["outputs/linkparent/x.md"]["problems"]))
        old_links = st["outputs/old"]["links"]
        check("plan: wikilink by file name and embed by path found",
              {l["kind"] for l in old_links} == {"wikilink", "embed"}, old_links)
        check("plan: a link whose file name also exists outside the list is not counted as going dead",
              dead_links(st["outputs/old"]) == 2 and any(l["ambiguous_with"] == ["Elsewhere/dupname.md"] for l in old_links),
              old_links)
        check("plan: markdown link found", any(l["kind"] == "md-link" for l in st["outputs/loose_report_2026-09-18.csv"]["links"]))
        check("plan: backtick mention reported separately",
              any(m["kind"] == "backtick" for m in st["outputs/old"]["mentions"]), st["outputs/old"]["mentions"])
        check("plan: symlinks reported, not followed",
              sorted(st["outputs/old"]["symlinks"]) == ["outputs/old/link_out.md", "outputs/old/linkdir"]
              and not any("Context" in f for f in st["outputs/old"]["files"]), st["outputs/old"])
        check("plan: a file changed today is flagged recent", st["Notes/fresh.md"]["recent"] and not st["outputs/old"]["recent"])
        check("plan: counts .md leaving Obsidian", st["outputs/old"]["md_obsidian"] == 3, st["outputs/old"]["md_obsidian"])
        check("plan wrote nothing to the archive", not os.path.exists(ARCHIVE_ROOT))

        # dry run
        good = write_list("good.txt", ["outputs/old", "outputs/loose_report_2026-09-18.csv",
                                       "Projects/X/deliverables/a_2026-07-29.xlsx  dup: Projects/X/deliverables/a_2026-07.xlsx"])
        before = {p: sha256_file(os.path.join(ROOT, *p.split("/"))) for p in
                  ("outputs/old/a.md", "outputs/old/sub/b.json", "outputs/loose_report_2026-09-18.csv")}
        code, o = ap(good, "sweep-test", apply=False)
        check("dry run exits 0, removes nothing, writes nothing",
              code == 0 and all(os.path.exists(os.path.join(ROOT, *p.split("/"))) for p in before)
              and not os.path.exists(ARCHIVE_ROOT), o)

        # protected refused by apply
        code, o = ap(write_list("prot.txt", ["outputs/loose_report_2026-09-18.csv", "Context/rules.md"]), "prot")
        check("apply refuses a list with a protected path and writes nothing",
              code != 0 and not os.path.exists(ARCHIVE_ROOT)
              and os.path.exists(os.path.join(ROOT, "outputs", "loose_report_2026-09-18.csv")), o)

        # corrupted zip: flip bytes in the first member's data after the zip is written
        def corrupt(path):
            with zipfile.ZipFile(path) as zf:
                zi = max(zf.infolist(), key=lambda z: z.compress_size)
            with open(path, "r+b") as fh:
                fh.seek(zi.header_offset + 26)
                n, e = (int.from_bytes(fh.read(2), "little") for _ in range(2))
                fh.seek(zi.header_offset + 30 + n + e + zi.compress_size // 2)
                chunk = fh.read(8)
                fh.seek(-len(chunk), 1)
                fh.write(bytes(b ^ 0xFF for b in chunk))
        _HOOKS["after_zip"] = corrupt
        code, o = ap(good, "sweep-test")
        _HOOKS.clear()
        check("corrupted zip: apply fails, removes nothing, no manifest, zip renamed .failed",
              code != 0 and all(os.path.exists(os.path.join(ROOT, *p.split("/"))) for p in before)
              and not any(z.endswith(".manifest.json") for z in zips())
              and any(z.endswith(".zip.failed") for z in zips())
              and not os.path.exists(os.path.join(ARCHIVE_ROOT, "INDEX.md")), o)

        # a bad deflate stream raises zlib.error (not BadZipFile): still a clean verify failure, exit 3
        def bad_block(path):
            with zipfile.ZipFile(path) as zf:
                zi = max(zf.infolist(), key=lambda z: z.compress_size)
            with open(path, "r+b") as fh:
                fh.seek(zi.header_offset + 26)
                n, e = (int.from_bytes(fh.read(2), "little") for _ in range(2))
                fh.seek(zi.header_offset + 30 + n + e)
                fh.write(b"\x07")  # BFINAL=1, BTYPE=11 (reserved): an invalid deflate block
        nfailed = sum(z.endswith(".zip.failed") for z in zips())
        _HOOKS["after_zip"] = bad_block
        code, o = ap(good, "sweep-test")
        _HOOKS.clear()
        check("bad deflate block (zlib.error): apply exits 3, removes nothing, no manifest, zip renamed .failed",
              code == 3 and "verify failed" in o and all(os.path.exists(os.path.join(ROOT, *p.split("/"))) for p in before)
              and not any(z.endswith(".manifest.json") or z.endswith(".zip") for z in zips())
              and sum(z.endswith(".zip.failed") for z in zips()) == nfailed + 1
              and not os.path.exists(os.path.join(ARCHIVE_ROOT, "INDEX.md")), o)

        # a source file changed between hashing and zipping: verify catches it
        def touch_after_hash(_recs):
            with open(os.path.join(ROOT, "outputs", "old", "a.md"), "a", encoding="utf-8") as fh:
                fh.write("late edit\n")
        _HOOKS["after_hash"] = touch_after_hash
        code, o = ap(good, "sweep-test")
        _HOOKS.clear()
        check("file edited after hashing: verify fails, nothing removed",
              code != 0 and all(os.path.exists(os.path.join(ROOT, *p.split("/"))) for p in before), o)
        before["outputs/old/a.md"] = sha256_file(os.path.join(ROOT, "outputs", "old", "a.md"))

        # existing zip name is never overwritten
        month_dir = os.path.join(ARCHIVE_ROOT, "2026-09")
        os.makedirs(month_dir, exist_ok=True)
        with open(os.path.join(month_dir, "sweep-test.zip"), "wb") as fh:
            fh.write(b"an older archive that must survive")
        old_zip_sha = sha256_file(os.path.join(month_dir, "sweep-test.zip"))

        # changed after the manifest, before removal: that file stays; a twin that changes keeps its duplicate
        def touch_csv(_recs):
            p = os.path.join(ROOT, "outputs", "loose_report_2026-09-18.csv")
            os.utime(p, (time.time(), time.time()))
            with open(os.path.join(ROOT, "Projects", "X", "deliverables", "a_2026-07.xlsx"), "w") as fh:
                fh.write("SAME bytes")
        _HOOKS["before_remove"] = touch_csv
        code, o = ap(good, "sweep-test")
        _HOOKS.clear()
        newzip = [z for z in zips() if z.endswith(".zip") and "sweep-test-" in os.path.basename(z)]
        check("existing zip name not overwritten: new zip gets a -N suffix, old bytes intact",
              code == 0 and newzip and sha256_file(os.path.join(month_dir, "sweep-test.zip")) == old_zip_sha, (o, zips()))
        man = json.load(open(newzip[0].replace(".zip", ".manifest.json"), encoding="utf-8")) if newzip else {}
        check("apply removes the originals and keeps the file that changed after hashing",
              not os.path.exists(os.path.join(ROOT, "outputs", "old", "a.md"))
              and not os.path.exists(os.path.join(ROOT, "outputs", "old", "sub"))
              and os.path.exists(os.path.join(ROOT, "Projects", "X", "deliverables", "a_2026-07-29.xlsx"))
              and "no longer identical" in o
              and os.path.exists(os.path.join(ROOT, "Projects", "X", "deliverables", "a_2026-07.xlsx"))
              and os.path.exists(os.path.join(ROOT, "outputs", "loose_report_2026-09-18.csv"))
              and "changed since hashing" in o, o)
        check("symlinks skipped: left in place, targets untouched, folder holding them kept",
              os.path.islink(os.path.join(ROOT, "outputs", "old", "link_out.md"))
              and os.path.islink(os.path.join(ROOT, "outputs", "old", "linkdir"))
              and sha256_file(os.path.join(ROOT, "Context", "rules.md")) == rules_sha
              and os.path.isdir(os.path.join(ROOT, "Context")) and man.get("skipped_symlinks"), o)
        check("a sibling that was not listed survives", os.path.exists(os.path.join(ROOT, "outputs", "keep.md")))
        check("manifest holds the zip sha256 and every file",
              man and man["zip_sha256"] == sha256_file(newzip[0]) and man["file_count"] == 6
              and "outputs/old/sub/empty" in man["empty_dirs"], man.get("file_count"))
        idx = open(os.path.join(ARCHIVE_ROOT, "INDEX.md"), encoding="utf-8").read() if os.path.exists(
            os.path.join(ARCHIVE_ROOT, "INDEX.md")) else ""
        check("INDEX.md has one section for the zip with restore line and removal line",
              idx.count("## 2026-09/") == 1 and "unzip -o" in idx and "Removed from the vault" in idx, idx[:400])
        restore = os.path.join(tmp, "restore")
        if newzip:
            with zipfile.ZipFile(newzip[0]) as zf:
                zf.extractall(restore)
        check("restore from the zip gives back the exact bytes at vault-relative paths",
              all(os.path.exists(os.path.join(restore, *p.split("/")))
                  and sha256_file(os.path.join(restore, *p.split("/"))) == h for p, h in before.items()))

        # JSON sweep list with several batches needs --batch
        jl = os.path.join(tmp, "sweep.json")
        with open(jl, "w", encoding="utf-8") as fh:
            json.dump([{"path": "outputs/keep.md", "batch": "one", "category": "t", "reason": "r", "evidence": "e"},
                       {"path": "Notes/fresh.md", "batch": "two", "category": "t", "reason": "r", "evidence": "e"}], fh)
        code, o = ap(jl, "multi")
        check("JSON list with two batches needs --batch", code != 0 and os.path.exists(os.path.join(ROOT, "outputs", "keep.md")), o)
        code, o = ap(jl, "multi", apply=False, batch="one")
        check("--batch picks one batch", code == 0 and "1 files" in o, o)

        # archive root inside the vault is refused
        saved_arch = ARCHIVE_ROOT
        ARCHIVE_ROOT = os.path.join(ROOT, "outputs", "archive-here")
        code, o = ap(jl, "inside", batch="one")
        ARCHIVE_ROOT = saved_arch
        check("archive root inside the vault refused", code != 0 and not os.path.exists(os.path.join(ROOT, "outputs", "archive-here")), o)

        # --include-denied lets Drew handle a Read-denied path
        INCLUDE_DENIED = True
        code, o = run(cmd_plan, list=write_list("den.txt", ["Secret/s.md"]), batch=None, out=None, json_out=None,
                      no_readers=True, recent_days=7)
        INCLUDE_DENIED = False
        check("--include-denied plans a Read-denied path", code == 0 and "1 ok" in o, o)

        src = open(os.path.abspath(__file__), encoding="utf-8").read()
        check("script source has no em dash or en dash", EMDASH not in src and ENDASH not in src)
        check("written files hold no em dash", EMDASH not in idx and EMDASH not in open(out_md, encoding="utf-8").read())
    finally:
        ROOT, ARCHIVE_ROOT, INCLUDE_DENIED, DENY = saved
        _HOOKS.clear()
        shutil.rmtree(tmp, ignore_errors=True)
    bad = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print("%s  %s%s" % ("PASS" if ok else "FAIL", name, "" if ok else "  " + str(detail)[:600]))
    print("selftest: %d/%d passed%s" % (len(results) - len(bad), len(results), "" if not bad else ", %d FAILED" % len(bad)))
    sys.exit(1 if bad else 0)


# ---------------------------------------------------------------- CLI

def main():
    global ROOT, ARCHIVE_ROOT, INCLUDE_DENIED, DENY
    ap = argparse.ArgumentParser(description="Archive old vault files into verified off-vault zips.")
    ap.add_argument("--root", default=DEFAULT_ROOT, help="vault root (default: the vault this script lives in)")
    ap.add_argument("--archive-root", default=None,
                    help="default: $DIGITALCLIQ_ARCHIVE_ROOT, else ~/Desktop/DigitalCLIQ Vault Archive")
    ap.add_argument("--include-denied", action="store_true",
                    help="also handle paths .claude/settings.json Read-denies (Drew runs this himself)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="read-only report on a list of paths")
    p.add_argument("--list", required=True)
    p.add_argument("--batch")
    p.add_argument("--out", help="write the markdown report here")
    p.add_argument("--json-out", help="write the full results as JSON here")
    p.add_argument("--no-readers", action="store_true", help="skip the code and prompt readers scan")
    p.add_argument("--recent-days", type=int, default=RECENT_DAYS)
    p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("apply", help="archive and remove (dry run unless --apply)")
    p.add_argument("--list", required=True)
    p.add_argument("--batch")
    p.add_argument("--name", required=True, help="zip base name, e.g. vault-sweep-2026-10-outputs-staging")
    p.add_argument("--month", required=True, help="archive folder month, YYYY-MM")
    p.add_argument("--note", help="what this zip holds, for INDEX.md")
    p.add_argument("--apply", action="store_true", help="really archive and remove")
    p.set_defaults(fn=cmd_apply)
    p = sub.add_parser("selftest", help="offline checks in a temp folder")
    p.set_defaults(fn=cmd_selftest)
    a = ap.parse_args()
    ROOT = os.path.abspath(os.path.expanduser(a.root))
    ARCHIVE_ROOT = os.path.abspath(os.path.expanduser(
        a.archive_root or os.environ.get("DIGITALCLIQ_ARCHIVE_ROOT") or DEFAULT_ARCHIVE))
    INCLUDE_DENIED = a.include_denied
    DENY = load_deny(ROOT)
    if a.cmd != "selftest" and not os.path.isdir(ROOT):
        die("vault root %s is not a folder" % ROOT)
    sys.exit(a.fn(a) or 0)


if __name__ == "__main__":
    main()
