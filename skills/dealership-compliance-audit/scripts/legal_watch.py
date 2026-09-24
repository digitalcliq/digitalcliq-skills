#!/usr/bin/env python3
"""
legal_watch.py — the "stay current" engine for the compliance audit.

The frameworks this audit enforces (CA CARS Act, CA advertising law, CCPA/CPRA,
ADA/Unruh, TCPA, and the vacated federal CARS Rule) change. This tool tracks what
we believe each one to be and when we last verified it (rules/legal_watch.json),
tells the monthly legal-watch agent what is overdue for re-checking, and DIFFS a
fresh sourced research pass against the baseline so a material change (a rule
reinstated, amended, a new operative date, new CCPA regs) gets surfaced instead of
silently going stale.

Typical loop (run monthly by a scheduled agent — see LEGAL_WATCH.md):
  1. python3 legal_watch.py --due 30           # what needs re-verifying?
  2. <agent researches those frameworks, writes findings JSON keyed by id>
  3. python3 legal_watch.py --diff findings.json   # what materially changed?
  4. python3 legal_watch.py --update findings.json # stamp last_verified + new status

Python 3.9+, stdlib only.
"""

import argparse
import json
from datetime import date
from pathlib import Path

BASELINE = Path(__file__).resolve().parent.parent / "rules" / "legal_watch.json"


def _load(path=BASELINE):
    with open(path) as f:
        return json.load(f)


def _today():
    return date.today()


def _parse(d):
    try:
        return date.fromisoformat(d)
    except (ValueError, TypeError):
        return None


def due(baseline, days=30):
    """Frameworks whose last_verified is older than `days` (or never verified)."""
    out = []
    for fw in baseline.get("frameworks", []):
        lv = _parse(fw.get("last_verified"))
        age = (_today() - lv).days if lv else 10 ** 6
        if age > days:
            out.append({"id": fw["id"], "name": fw["name"],
                        "last_verified": fw.get("last_verified"), "age_days": age})
    return out


def diff(baseline, findings):
    """Compare a fresh research pass (dict keyed by framework id) to the baseline.

    findings: {id: {"status": str, "effective_date": str|null, "sources": [...]}}
    Returns a list of material changes (status or effective_date moved).
    """
    by_id = {fw["id"]: fw for fw in baseline.get("frameworks", [])}
    changes = []
    for fid, new in findings.items():
        old = by_id.get(fid)
        if not old:
            changes.append({"id": fid, "kind": "new_framework", "new": new})
            continue
        for field in ("status", "effective_date"):
            o, n = old.get(field), new.get(field)
            if n is not None and str(o) != str(n):
                changes.append({"id": fid, "kind": "changed", "field": field,
                                "from": o, "to": n})
    return changes


def update(baseline, findings, today=None):
    """Apply fresh findings into the baseline: bump last_verified + status/sources."""
    today = today or _today().isoformat()
    by_id = {fw["id"]: fw for fw in baseline.get("frameworks", [])}
    for fid, new in findings.items():
        fw = by_id.get(fid)
        if not fw:
            continue
        for field in ("status", "effective_date", "watch"):
            if new.get(field) is not None:
                fw[field] = new[field]
        for s in new.get("sources", []) or []:
            if s not in fw.setdefault("sources", []):
                fw["sources"].append(s)
        fw["last_verified"] = today
    baseline["last_full_review"] = today
    return baseline


def main():
    ap = argparse.ArgumentParser(description="Legal-currency watch for the compliance audit")
    ap.add_argument("--baseline", default=str(BASELINE))
    ap.add_argument("--due", type=int, metavar="DAYS", help="list frameworks older than DAYS")
    ap.add_argument("--diff", metavar="FINDINGS_JSON", help="diff a research pass against the baseline")
    ap.add_argument("--update", metavar="FINDINGS_JSON", help="apply a research pass into the baseline")
    args = ap.parse_args()

    baseline = _load(Path(args.baseline))

    if args.due is not None:
        rows = due(baseline, args.due)
        if not rows:
            print("[legal-watch] all frameworks verified within %d days." % args.due)
        for r in rows:
            print("[legal-watch] DUE: %s (%s) — last verified %s (%d days ago)"
                  % (r["id"], r["name"], r["last_verified"], r["age_days"]))
        return

    if args.diff:
        findings = json.load(open(args.diff))
        changes = diff(baseline, findings)
        if not changes:
            print("[legal-watch] no material changes vs baseline.")
        for c in changes:
            if c["kind"] == "new_framework":
                print("[legal-watch] NEW framework in findings: %s" % c["id"])
            else:
                print("[legal-watch] CHANGED %s.%s: %r → %r" % (c["id"], c["field"], c["from"], c["to"]))
        return

    if args.update:
        findings = json.load(open(args.update))
        baseline = update(baseline, findings)
        with open(args.baseline, "w") as f:
            json.dump(baseline, f, indent=2, ensure_ascii=False)
        print("[legal-watch] baseline updated and re-stamped: %s" % args.baseline)
        return

    # Default: print a currency summary.
    print("Legal-currency baseline — last full review: %s" % baseline.get("last_full_review"))
    for fw in baseline.get("frameworks", []):
        print("  %-10s last_verified %s — %s" % (fw["id"], fw.get("last_verified"), fw["status"][:80]))


if __name__ == "__main__":
    main()
