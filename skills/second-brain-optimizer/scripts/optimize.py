#!/usr/bin/env python3
"""DigitalCLIQ Second Brain Optimizer scanner.

Subcommands:
  scan    inventory + mechanical (P2) + link-graph (P3) findings + metrics
  fix     apply mechanical fixes (em dashes, duplicate H1) with backups
  score   print the health score for whatever phase files exist
  report  render the branded HTML dashboard from state files

All deterministic work lives here so agent tokens go only to judgment.
"""
import argparse
import difflib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

SKIP_DIRS = {".git", ".obsidian", ".trash", "node_modules", "dist", "build",
             ".claude", "__pycache__"}
EMDASH, ENDASH = "—", "–"
DASH_RE = re.compile("[" + EMDASH + ENDASH + "]")
PROT_RE = re.compile(r"(`[^`]*`|\[\[[^\]]+\]\]|https?://\S+|!\[[^\]]*\]\([^)]*\)|\[[^\]]*\]\([^)]+\))")
WIKILINK_RE = re.compile(r"\[\[([^\]\|#\\]+)\\?(?:#[^\]\|]*)?\\?(?:\|[^\]]*)?\]\]")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
STALE_DAYS = 180

DEFAULT_ROLES = {
    "context": ("context", "curated"), "daily": ("daily", "session"),
    "departments": ("departments", "curated"), "projects": ("projects", "curated"),
    "resources": ("resources", "curated"), "tasks": ("tasks", "meta"),
    "team": ("team", "curated"), "skills": ("skills", "meta"),
    "onboarding": ("onboarding", "curated"), "intelligence": ("intelligence", "curated"),
}
SUBROLES = {"intelligence/decisions": ("decisions", "curated"),
            "intelligence/archive": ("archive", "archive"),
            "intelligence/meetings": ("meetings", "session"),
            "intelligence/competitors": ("competitors", "curated")}


def load_roles(state: Path):
    p = state / "roles.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {}


def classify(rel: Path, roles_cfg):
    parts = [p.lower() for p in rel.parts]
    if rel.name.lower() in ("claude.md",) or rel.name == "SKILL.md":
        return ("instruction", "meta")
    if not rel.parent.parts:
        return ("root", "meta")
    folders = roles_cfg.get("folders", {})
    # explicit config wins, longest path first
    key = "/".join(rel.parent.parts)
    for k in sorted(folders, key=len, reverse=True):
        if key.lower().startswith(k.lower()):
            f = folders[k]
            return (f.get("role", "note"), f.get("layer", "curated"))
    two = "/".join(parts[:2])
    if two in SUBROLES:
        return SUBROLES[two]
    if parts[0] in DEFAULT_ROLES:
        return DEFAULT_ROLES[parts[0]]
    if re.match(r"\d{4}-\d{2}-\d{2}", rel.stem):
        return ("daily", "session")
    return ("note", "curated")


def walk_md(root: Path, extra_skips):
    skips = {s.strip("/").lower() for s in (extra_skips or [])}
    out = []
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root)
        parts_l = [x.lower() for x in rel.parts[:-1]]
        if any(x in SKIP_DIRS for x in parts_l):
            continue
        rel_l = "/".join(parts_l)
        if any(rel_l == s or rel_l.startswith(s + "/") for s in skips):
            continue
        out.append(rel)
    return out


def split_frontmatter(lines):
    if lines and lines[0].strip() == "---":
        for i in range(1, min(len(lines), 60)):
            if lines[i].strip() == "---":
                return lines[1:i], i + 1
    return [], 0


def fm_status_tags(fm_lines):
    has_status = any(re.match(r"^status:\s*\S", l) for l in fm_lines)
    tags = 0
    for i, l in enumerate(fm_lines):
        m = re.match(r"^tags:\s*\[(.*)\]", l)
        if m:
            tags = len([t for t in m.group(1).split(",") if t.strip()])
            break
        if re.match(r"^tags:\s*$", l):
            j = i + 1
            while j < len(fm_lines) and re.match(r"^\s*-\s+\S", fm_lines[j]):
                tags += 1
                j += 1
            break
    return has_status, tags


def analyze(root: Path, rel: Path, roles_cfg):
    p = root / rel
    try:
        text = p.read_text(errors="replace")
    except Exception:
        return None
    lines = text.splitlines()
    fm, body_start = split_frontmatter(lines)
    has_status, tag_count = fm_status_tags(fm)
    role, layer = classify(rel, roles_cfg)
    info = {"path": str(rel), "role": role, "layer": layer,
            "bytes": p.stat().st_size, "mtime": p.stat().st_mtime,
            "has_fm": bool(fm), "has_status": has_status, "tags": tag_count,
            "headers": [], "links": [], "emdash_lines": [], "dup_h1": None}
    in_fence = False
    first_content = None
    for n, line in enumerate(lines[body_start:], start=body_start + 1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if first_content is None and line.strip():
            first_content = (n, line)
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            info["headers"].append([n, len(m.group(1)), m.group(2)[:80]])
        for lm in WIKILINK_RE.finditer(re.sub(r"`[^`]*`", "", line)):
            info["links"].append(lm.group(1).strip())
        clean = PROT_RE.sub("", line)
        cnt = len(DASH_RE.findall(clean))
        if cnt:
            info["emdash_lines"].append([n, cnt, line.strip()[:100]])
    if first_content:
        n, line = first_content
        m = re.match(r"^#\s+(.*)", line)
        if m:
            slug = re.sub(r"[^a-z0-9]", "", m.group(1).lower())
            fslug = re.sub(r"[^a-z0-9]", "", rel.stem.lower())
            if slug and slug == fslug:
                info["dup_h1"] = n
    return info


def build_findings(root, inv, roles_cfg):
    findings, counter = [], {}

    def add(check, path, line, sev, excerpt, fix_kind, draft, data=None):
        counter[check] = counter.get(check, 0) + 1
        findings.append({"id": "%s-%03d" % (check, counter[check]),
                         "pass": check.split(".")[0], "check": check,
                         "path": path, "line": line, "severity": sev,
                         "excerpt": excerpt, "data": data or {},
                         "fix": {"kind": fix_kind, "draft": draft},
                         "fix_status": None})

    stem_index = {}
    for f in inv:
        stem_index.setdefault(Path(f["path"]).stem.lower(), []).append(f["path"])
    inbound = {}
    for f in inv:
        for t in f["links"]:
            k = Path(t).stem.lower() if "/" in t else t.lower()
            inbound[k] = inbound.get(k, 0) + 1
        # CLAUDE.md routing tables reference files by backtick path; count those as inbound
        if Path(f["path"]).name == "CLAUDE.md":
            try:
                txt = (root / f["path"]).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                txt = ""
            for m in re.finditer(r"`([^`\s]+\.md)`", txt):
                k = Path(m.group(1)).stem.lower()
                inbound[k] = inbound.get(k, 0) + 1
    now = datetime.now().timestamp()
    index_names = {"readme.md", "index.md", "plot.md", "claude.md", "skill.md"}
    red_ok = roles_cfg.get("red_links_intentional", False)
    dead = {}

    for f in inv:
        rel, role, layer = f["path"], f["role"], f["layer"]
        if f["emdash_lines"]:
            total = sum(c for _, c, _ in f["emdash_lines"])
            add("P2.1", rel, f["emdash_lines"][0][0], "warn",
                "%d em/en dashes on %d lines" % (total, len(f["emdash_lines"])),
                "mechanical", "replace with comma/colon (digit ranges get hyphens)",
                {"lines": f["emdash_lines"][:20], "count": total})
        if f["dup_h1"]:
            add("P2.2", rel, f["dup_h1"], "warn", "H1 duplicates filename",
                "mechanical", "remove the H1 line")
        if layer != "meta" and not (f["has_fm"] and f["has_status"] and f["tags"] >= 2):
            missing = []
            if not f["has_fm"]:
                missing.append("frontmatter block")
            else:
                if not f["has_status"]:
                    missing.append("status")
                if f["tags"] < 2:
                    missing.append("2+ tags")
            add("P2.3", rel, 1, "warn", "missing " + ", ".join(missing),
                "add_frontmatter", "agent drafts real values from content")
        kb = f["bytes"] / 1024
        if kb > 100:
            add("P2.4", rel, 1, "fail", "%.0fKB, over the 100KB hard budget" % kb,
                "rewrite", "split at H2 boundaries or archive")
        elif layer != "session":
            limit = 10 if (role in ("context", "decisions", "instruction")) else 50
            if kb > limit:
                add("P2.4", rel, 1, "warn", "%.0fKB, over the %dKB budget for %s" % (kb, limit, role),
                    "rewrite", "split at H2 boundaries or trim")
        if layer == "curated" and (now - f["mtime"]) > STALE_DAYS * 86400:
            add("P2.5", rel, 1, "info", "untouched %d days" % int((now - f["mtime"]) / 86400),
                "rewrite", "P4.3 verifies whether content is actually stale")
        for t in f["links"]:
            tl = t.lower()
            if tl in stem_index or "/" in t and Path(t).stem.lower() in stem_index:
                continue
            if "/" in t and ((root / (t + ".md")).exists() or (root / t).exists()):
                continue  # path link into a skipped folder (archive, outputs) that exists on disk
            d = dead.setdefault(tl, {"target": t, "refs": set()})
            d["refs"].add(rel)
        if (layer == "curated" and Path(rel).name.lower() not in index_names
                and inbound.get(Path(rel).stem.lower(), 0) == 0):
            add("P3.2", rel, 1, "info", "no inbound wikilinks", "repoint_link",
                "link from folder index or a related note, or archive")

    # one P3.1 finding per unique unresolved target, aggregated across the vault
    for tl in sorted(dead, key=lambda k: -len(dead[k]["refs"])):
        d = dead[tl]
        n = len(d["refs"])
        sugg = difflib.get_close_matches(tl, list(stem_index.keys()), n=3, cutoff=0.8)
        if sugg:
            sev, draft = "warn", "likely rename; repoint to: " + ", ".join(sugg)
        elif n >= 20:
            sev, draft = "warn", "%d files reference it; create the page" % n
        else:
            sev = "info" if red_ok else "warn"
            draft = "intentional placeholder (%d refs); page at 20+ or repoint" % n if red_ok \
                else "repoint or create (%d refs)" % n
        refs = sorted(d["refs"])
        add("P3.1", refs[0], 1, sev, "unresolved [[%s]] in %d files" % (d["target"], n),
            "repoint_link", draft,
            {"target": d["target"], "ref_count": n, "refs": refs[:15], "suggestions": sugg})
    return findings


def metrics_from(inv, findings):
    per_role = {}
    for f in inv:
        r = per_role.setdefault(f["role"], {"files": 0, "bytes": 0, "emdash": 0, "fm_ok": 0})
        r["files"] += 1
        r["bytes"] += f["bytes"]
        r["emdash"] += sum(c for _, c, _ in f["emdash_lines"])
        if f["has_fm"] and f["has_status"] and f["tags"] >= 2:
            r["fm_ok"] += 1
    tot = {"files": len(inv), "bytes": sum(f["bytes"] for f in inv),
           "tokens_est": sum(f["bytes"] for f in inv) // 4,
           "emdash": sum(r["emdash"] for r in per_role.values()),
           "fm_pct": round(100.0 * sum(r["fm_ok"] for r in per_role.values()) / max(1, len(inv)), 1),
           "dead_links": sum(1 for x in findings if x["check"] == "P3.1"),
           "orphans": sum(1 for x in findings if x["check"] == "P3.2")}
    return {"total": tot, "per_role": per_role,
            "generated": datetime.now(timezone.utc).isoformat()}


def compute_score(findings, ignore_status=False):
    ded = {}
    for f in findings:
        if f["pass"] in ("P4", "P5"):
            continue
        if not ignore_status and f.get("fix_status") == "applied":
            continue
        d = ded.setdefault(f["pass"], 0)
        ded[f["pass"]] = d + (5 if f["severity"] == "fail" else 1 if f["severity"] == "warn" else 0)
    return max(0, 100 - sum(min(v, 25) for v in ded.values()))


def score_label(s):
    return ("Well-tuned" if s >= 90 else "Visible drift" if s >= 70
            else "Bloat is hurting" if s >= 50 else "Vault rot")


# ---------- fix ----------

def fix_segment(seg):
    seg = re.sub(r"(?<=\d)\s*[" + EMDASH + ENDASH + r"]\s*(?=\d)", "-", seg)
    seg = re.sub(r"(?<=[0-9A-Za-z])[" + EMDASH + ENDASH + r"](?=[0-9A-Za-z])", " to ", seg)
    seg = re.sub(r"\s*[" + EMDASH + ENDASH + r"]+\s*", ", ", seg)
    return seg


def fix_line(line):
    parts = PROT_RE.split(line)
    out = []
    for i, part in enumerate(parts):
        out.append(part if i % 2 else fix_segment(part))
    line = "".join(out)
    line = re.sub(r",\s+([,.;:!?])", r"\1", line)
    return re.sub(r",\s*$", ".", line)


def apply_fixes(root, state, do_emdash, do_h1):
    findings = json.loads((state / "findings-scan.json").read_text())
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bdir = state / "backups" / stamp
    touched, results = set(), {}
    for f in findings:
        if f["check"] == "P2.1" and do_emdash or f["check"] == "P2.2" and do_h1:
            touched.add(f["path"])
    for rel in sorted(touched):
        p = root / rel
        if not p.exists():
            continue
        dst = bdir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
        lines = p.read_text(errors="replace").splitlines()
        fm, body_start = split_frontmatter(lines)
        dup = next((f for f in findings if f["check"] == "P2.2" and f["path"] == rel), None)
        out, in_fence, removed = [], False, 0
        for n, line in enumerate(lines, start=1):
            if do_h1 and dup and n == dup["line"]:
                removed = 1
                continue
            if removed == 1 and not line.strip():
                removed = 2
                continue
            if FENCE_RE.match(line):
                in_fence = not in_fence
                out.append(line)
                continue
            if do_emdash and not in_fence and n > (body_start or 0):
                out.append(fix_line(line))
            else:
                out.append(line)
        p.write_text("\n".join(out) + ("\n" if lines and not lines[-1] else "\n"))
        results[rel] = "fixed"
    print(json.dumps({"fixed": len(results), "backup": str(bdir)}, indent=2))


# ---------- report ----------

def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


PASS_NAMES = {"P1": "Instruction Layer", "P2": "Mechanical Hygiene",
              "P3": "Link Graph", "P4": "Reflection", "P5": "Architecture"}


def render_report(state, out_path, root):
    tpl = (Path(__file__).parent.parent / "references" / "report-template.html").read_text()
    scan = json.loads((state / "findings-scan.json").read_text())
    agent_p = state / "findings-agent.json"
    agent = json.loads(agent_p.read_text()) if agent_p.exists() else []
    findings = scan + agent
    mb = json.loads((state / "metrics-before.json").read_text())
    ma_p = state / "metrics-after.json"
    ma = json.loads(ma_p.read_text()) if ma_p.exists() else mb
    after_p = state / "findings-scan-after.json"
    after_scan = json.loads(after_p.read_text()) if after_p.exists() else scan
    open_agent = [f for f in agent if f.get("fix_status") != "applied"]
    sb, sa = compute_score(scan + agent, ignore_status=True), compute_score(after_scan + open_agent)
    arch_p = state / "arch-read.md"
    arch = arch_p.read_text() if arch_p.exists() else ""
    arch_html = "".join("<p>%s</p>" % esc(x) for x in arch.split("\n\n") if x.strip())

    def tile(label, b, a):
        return ('<div class="tile"><div class="num">%s <span class="arrow">&rarr;</span> %s</div>'
                '<div class="lbl">%s</div></div>' % (esc(b), esc(a), esc(label)))

    t, ta = mb["total"], ma["total"]
    tiles = "".join([
        tile("Files audited", t["files"], ta["files"]),
        tile("Tokens (est.)", "{:,}".format(t["tokens_est"]), "{:,}".format(ta["tokens_est"])),
        tile("Em dashes", t["emdash"], ta["emdash"]),
        tile("Frontmatter complete", "%s%%" % t["fm_pct"], "%s%%" % ta["fm_pct"]),
        tile("Dead wikilinks", t["dead_links"], ta["dead_links"]),
        tile("Orphans", t["orphans"], ta["orphans"])])

    rows, cards = [], []
    for pk in ("P1", "P2", "P3", "P4", "P5"):
        fs = [f for f in findings if f["pass"] == pk]
        st = {}
        for f in fs:
            st[f.get("fix_status") or "open"] = st.get(f.get("fix_status") or "open", 0) + 1
        rows.append("<tr><td>%s %s</td><td>%d</td><td>%d</td><td>%d</td>"
                    "<td>%d</td><td>%d</td><td>%d</td></tr>" % (
                        pk, PASS_NAMES[pk], len(fs),
                        sum(1 for f in fs if f["severity"] == "fail"),
                        sum(1 for f in fs if f["severity"] == "warn"),
                        st.get("applied", 0), st.get("saved_to_plan", 0),
                        st.get("declined", 0) + st.get("failed", 0)))
        shown = fs[:25]
        cc = []
        for f in shown:
            pill = f.get("fix_status") or "open"
            cc.append('<div class="card"><span class="pill %s">%s</span>'
                      '<span class="pill sev-%s">%s</span> <b>%s</b> '
                      '<span class="path">%s:%s</span><div class="ex">%s</div>%s</div>' % (
                          pill, esc(pill.replace("_", " ")), f["severity"], f["severity"],
                          esc(f["check"]), esc(f["path"]), f.get("line", ""),
                          esc(f.get("excerpt", "")),
                          '<div class="rs">%s</div>' % esc(f["reasoning"]) if f.get("reasoning") else ""))
        more = ("<p class='more'>and %d more in the JSON sidecar</p>" % (len(fs) - 25)) if len(fs) > 25 else ""
        cards.append('<section><h2>%s %s</h2>%s%s</section>' % (
            pk, PASS_NAMES[pk], "".join(cc) or "<p class='clean'>Clean. No findings.</p>", more))

    html = (tpl.replace("{{VAULT_NAME}}", esc(Path(root).resolve().name))
            .replace("{{DATE}}", datetime.now().strftime("%Y-%m-%d"))
            .replace("{{SCORE_BEFORE}}", str(sb)).replace("{{SCORE_AFTER}}", str(sa))
            .replace("{{SCORE_LABEL_BEFORE}}", score_label(sb))
            .replace("{{SCORE_LABEL_AFTER}}", score_label(sa))
            .replace("{{TILES}}", tiles).replace("{{ARCH_READ}}", arch_html)
            .replace("{{PASS_ROWS}}", "".join(rows))
            .replace("{{FINDINGS}}", "".join(cards)))
    if "{{" in html:
        sys.exit("unfilled placeholder in report; refusing to save")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    out.with_suffix(".json").write_text(json.dumps(findings, indent=1))
    print(json.dumps({"report": str(out), "json": str(out.with_suffix('.json')),
                      "score_before": sb, "score_after": sa}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["scan", "fix", "score", "report"])
    ap.add_argument("--root", default=".")
    ap.add_argument("--state", default=".claude/optimizer")
    ap.add_argument("--skip", action="append", default=[])
    ap.add_argument("--phase", choices=["before", "after"], default="before")
    ap.add_argument("--emdash", action="store_true")
    ap.add_argument("--h1", action="store_true")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    root, state = Path(a.root), Path(a.root) / a.state if not Path(a.state).is_absolute() else Path(a.state)
    state.mkdir(parents=True, exist_ok=True)
    roles_cfg = load_roles(state)

    if a.cmd == "scan":
        inv = [x for x in (analyze(root, rel, roles_cfg) for rel in walk_md(root, a.skip)) if x]
        findings = build_findings(root, inv, roles_cfg)
        met = metrics_from(inv, findings)
        suffix = "-after" if a.phase == "after" else ""
        (state / ("findings-scan%s.json" % suffix)).write_text(json.dumps(findings, indent=1))
        (state / ("metrics-%s.json" % ("after" if a.phase == "after" else "before"))).write_text(json.dumps(met, indent=1))
        if a.phase == "before":
            (state / "inventory.json").write_text(json.dumps(inv, indent=1))
        by_check = {}
        for f in findings:
            by_check[f["check"]] = by_check.get(f["check"], 0) + 1
        print(json.dumps({"phase": a.phase, "files": len(inv),
                          "tokens_est": met["total"]["tokens_est"],
                          "findings": len(findings), "by_check": by_check,
                          "score": compute_score(findings)}, indent=2))
    elif a.cmd == "fix":
        apply_fixes(root, state, a.emdash, a.h1)
    elif a.cmd == "score":
        scan = json.loads((state / "findings-scan.json").read_text())
        agent_p = state / "findings-agent.json"
        agent = json.loads(agent_p.read_text()) if agent_p.exists() else []
        print(json.dumps({"score": compute_score(scan + agent),
                          "label": score_label(compute_score(scan + agent))}))
    elif a.cmd == "report":
        if not a.out:
            sys.exit("--out required")
        render_report(state, a.out, root)


if __name__ == "__main__":
    main()
