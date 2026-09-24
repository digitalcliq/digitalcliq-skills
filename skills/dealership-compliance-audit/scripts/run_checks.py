#!/usr/bin/env python3
"""
run_checks.py — test-style runner for the codified checks.

Prints every check grouped by framework as PASS / FAIL / UNRESOLVED, so a run
reads like a test report. With --verify it runs the full crawl→analyze→correct
loop first (re-crawling truncated pages) and then prints which checks were
re-verified and how many false positives the fallback averted.

  python3 run_checks.py --crawl /tmp/sterling_bmw_crawl_data.json --brand bmw --verify

Python 3.9+, stdlib only.
"""

import sys
import json
import argparse
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR))
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from checks import registry          # noqa: E402

GLYPH = {"pass": "PASS", "fail": "FAIL", "unresolved": "UNRESOLVED"}
FRAMEWORK_ORDER = ["PRICING", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "BRAND"]


def _print_results(results):
    groups = {}
    for r in results:
        groups.setdefault(r.framework, []).append(r)
    order = [f for f in FRAMEWORK_ORDER if f in groups] + \
            [f for f in groups if f not in FRAMEWORK_ORDER]
    for fw in order:
        rs = groups[fw]
        title = rs[0].framework_title
        print("\n%s — %s" % (fw, title))
        for r in sorted(rs, key=lambda x: (x.status, x.check_id)):
            tag = GLYPH[r.status]
            rv = " (re-verified)" if r.reverified else ""
            sev = (" [%s]" % r.severity) if r.severity else ""
            print("  [%-10s]%s %s/%s%s — %s" % (tag, sev, r.check_id, r.page, rv, r.evidence[:120]))


def main():
    ap = argparse.ArgumentParser(description="Run codified compliance checks (test-style output)")
    ap.add_argument("--crawl", required=True)
    ap.add_argument("--brand", required=True)
    ap.add_argument("--brand-rules", default=None)
    ap.add_argument("--verify", action="store_true",
                    help="run the crawl→analyze→correct loop (fallback re-crawl) first")
    args = ap.parse_args()

    brand_rules = json.load(open(args.brand_rules)) if args.brand_rules else {}

    if args.verify:
        import verify_loop
        final, findings, report = verify_loop.run(args.crawl, args.brand, args.brand_rules)
        _print_results(final)
        s = report["summary"]
        print("\n" + "=" * 64)
        print("VERIFY LOOP: %d iterations, %d re-verified, "
              "%d false positives averted, %d confirmed after re-crawl"
              % (report["iterations"], s["reverified"],
                 s["false_positives_averted"], s["violations_confirmed_after_recrawl"]))
        if report["transitions"]:
            print("\nRe-verifications:")
            for t in report["transitions"]:
                print("  %s/%s: %s(%s) → %s(%s) — %s"
                      % (t["check_id"], t["page"], t["from_status"], t["from_confidence"],
                         t["to_status"], t["to_confidence"], t["note"]))
        print("=" * 64)
    else:
        crawl = json.load(open(args.crawl))
        results = registry.run_checks(crawl, brand=args.brand, brand_rules=brand_rules)
        _print_results(results)

    # always print the bottom-line counts
    if not args.verify:
        n_pass = sum(1 for r in results if r.status == "pass")
        n_fail = sum(1 for r in results if r.status == "fail")
        n_unres = sum(1 for r in results if r.status == "unresolved")
        print("\n%d pass | %d fail | %d unresolved" % (n_pass, n_fail, n_unres))


if __name__ == "__main__":
    main()
