#!/usr/bin/env python3
"""
verify_loop.py — crawl → analyze → correct convergence engine.

The loop that makes the audit trustworthy:

  1. Run every codified check (checks/registry.py) over the crawl data.
  2. Collect checks that came back `unresolved` AND carry `needs_data`
     (i.e. the answer is undecidable only because the browser truncated the page).
  3. Re-fetch exactly those pages with the curl/urllib fallback crawler
     (scripts/fallback_crawl.py), which returns full, uncapped server text.
  4. Re-run ONLY those checks against the corrected data.
  5. Repeat until nothing is left to re-crawl, no status changed, or max
     iterations. Every page is re-crawled at most once.

Output:
  * findings JSON (status==fail only) — feeds run_audit.py / the Excel report.
  * verification_report JSON — exactly which checks were re-verified, what flipped,
    and how many false positives the fallback averted.

A check is NEVER promoted to a violation off truncated data. Unresolved items that
cannot be corrected (fetch failed, JS-rendered SPA) stay unresolved + human-review,
never silently failed and never silently passed.

Python 3.9+, stdlib only.
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR))
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from checks import registry          # noqa: E402
import fallback_crawl                 # noqa: E402

MAX_ITERATIONS = 4


def _load(path):
    with open(path) as f:
        return json.load(f)


def _merge_page(original, refetched):
    """Overlay full-text fallback fields onto the original page.

    Returns (merged_page, outcome). Outcome is one of:
      'corrected'    — fallback gave real, fuller text; use it.
      'error'        — fetch failed; keep original, record gap.
      'js_suspected' — server HTML too thin (SPA); keep original, flag human review.
    """
    if not refetched or refetched.get("error"):
        return original, "error"
    if refetched.get("js_rendered_suspected"):
        return original, "js_suspected"
    # Accept the fallback only if it actually produced MORE usable signal than the
    # truncated browser capture: either more text, or disclaimer blocks the browser
    # never captured. Recovering the disclaimer is the whole point even if the raw
    # text is shorter than the browser's padded/expanded DOM dump.
    orig_len = len(original.get("text_excerpt", "") or "")
    new_len = len(refetched.get("text_excerpt", "") or "")
    recovered_disclaimers = bool(refetched.get("disclaimers")) and not original.get("disclaimers")
    if new_len <= orig_len and not recovered_disclaimers:
        return original, "no_improvement"
    merged = dict(original)
    for k in ("text_excerpt", "page_text_excerpt", "disclaimers", "prices_found",
              "lease_payments", "lease_terms", "has_lease_offers", "has_cpo_section",
              "has_carfax", "char_count"):
        if k in refetched:
            merged[k] = refetched[k]
    merged["source"] = "browser+fallback"
    return merged, "corrected"


def run(crawl_path, brand, brand_rules_path=None, verbose=True):
    crawl = _load(crawl_path)
    brand_rules = _load(brand_rules_path) if brand_rules_path else {}
    pages = crawl.setdefault("pages", {})

    transitions = []
    recrawls = []
    recrawled_pages = set()

    # Iteration 0 — full registry
    results = registry.run_checks(crawl, brand=brand, brand_rules=brand_rules)
    by_key = {(r.check_id, r.page): r for r in results}

    iterations = 0
    while iterations < MAX_ITERATIONS:
        iterations += 1
        # Which unresolved checks can a re-crawl actually fix?
        todo = [r for r in by_key.values()
                if r.status == "unresolved" and r.needs_data
                and r.needs_data.get("page") not in recrawled_pages
                and r.needs_data.get("url")]
        if not todo:
            break

        # Unique pages to re-fetch this round
        pages_to_fetch = {}
        for r in todo:
            nd = r.needs_data
            pages_to_fetch[nd["page"]] = nd["url"]

        # Re-fetch the pages concurrently — they are independent network calls and
        # urllib is blocking I/O, so threads cut wall-clock to the slowest page.
        if verbose:
            for page_key, url in pages_to_fetch.items():
                print("[verify] iteration %d: fallback re-crawl '%s' → %s"
                      % (iterations, page_key, url))
        fetched = {}
        if len(pages_to_fetch) == 1:
            (pk0, url0), = pages_to_fetch.items()
            fetched[pk0] = fallback_crawl.recrawl(pk0, url0)
        else:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(8, len(pages_to_fetch))) as ex:
                futs = {ex.submit(fallback_crawl.recrawl, pk, url): pk
                        for pk, url in pages_to_fetch.items()}
                for fut in futs:
                    fetched[futs[fut]] = fut.result()

        affected_check_ids = set()
        for page_key, url in pages_to_fetch.items():
            refetched = fetched[page_key]
            merged, outcome = _merge_page(pages.get(page_key, {}), refetched)
            pages[page_key] = merged
            recrawled_pages.add(page_key)
            recrawls.append({
                "iteration": iterations, "page": page_key, "url": url,
                "outcome": outcome, "char_count": refetched.get("char_count"),
                "error": refetched.get("error"),
            })
            # every check that was unresolved on this page should be re-run
            for r in todo:
                if r.needs_data.get("page") == page_key:
                    affected_check_ids.add(r.check_id)

        # Re-run ONLY the affected checks against corrected data
        rerun = registry.run_checks(crawl, brand=brand, brand_rules=brand_rules,
                                    only_check_ids=affected_check_ids)
        rerun_by_key = {(r.check_id, r.page): r for r in rerun}

        for key, new_r in rerun_by_key.items():
            old_r = by_key.get(key)
            if not old_r:
                by_key[key] = new_r
                continue
            if (new_r.status, new_r.confidence) != (old_r.status, old_r.confidence):
                new_r.reverified = True
                # find why it could not be corrected, if it stayed unresolved
                note = ""
                if new_r.status == "unresolved":
                    page_outcomes = [rc["outcome"] for rc in recrawls
                                     if rc["page"] == new_r.page]
                    note = "could not correct (%s)" % (page_outcomes[-1] if page_outcomes else "no recrawl")
                transitions.append({
                    "check_id": key[0], "page": key[1],
                    "from_status": old_r.status, "from_confidence": old_r.confidence,
                    "to_status": new_r.status, "to_confidence": new_r.confidence,
                    "note": note or "corrected via fallback re-crawl",
                })
                by_key[key] = new_r
            else:
                # unchanged but mark we tried, so it is not retried forever
                by_key[key].reverified = True

    final = list(by_key.values())

    # Summaries
    def count(status):
        return sum(1 for r in final if r.status == status)

    fp_averted = sum(1 for t in transitions
                     if t["from_status"] == "unresolved" and t["to_status"] == "pass")
    confirmed = sum(1 for t in transitions
                    if t["from_status"] == "unresolved" and t["to_status"] == "fail")
    still_unresolved = [
        {"check_id": r.check_id, "page": r.page, "reason": (r.needs_data or {}).get("reason", r.evidence)}
        for r in final if r.status == "unresolved"]

    report = {
        "client": crawl.get("client", ""),
        "brand": brand,
        "url": crawl.get("url", ""),
        "generated": datetime.now().isoformat(timespec="seconds"),
        "iterations": iterations,
        "recrawls": recrawls,
        "transitions": transitions,
        "still_unresolved": still_unresolved,
        "summary": {
            "checks_total": len(final),
            "passed": count("pass"),
            "failed": count("fail"),
            "unresolved": count("unresolved"),
            "reverified": sum(1 for r in final if r.reverified),
            "false_positives_averted": fp_averted,
            "violations_confirmed_after_recrawl": confirmed,
            "still_unresolved": len(still_unresolved),
        },
    }
    findings = registry.results_to_findings(final)
    return final, findings, report


def main():
    ap = argparse.ArgumentParser(description="Crawl→analyze→correct convergence loop")
    ap.add_argument("--crawl", required=True)
    ap.add_argument("--brand", required=True)
    ap.add_argument("--brand-rules", default=None)
    ap.add_argument("--out-findings", default=None)
    ap.add_argument("--out-report", default=None)
    args = ap.parse_args()

    stem = Path(args.crawl).stem.replace("_crawl_data", "")
    out_findings = args.out_findings or "/tmp/%s_checks_findings.json" % stem
    out_report = args.out_report or "/tmp/%s_verification_report.json" % stem

    final, findings, report = run(args.crawl, args.brand, args.brand_rules)

    with open(out_findings, "w") as f:
        json.dump(findings, f, indent=2)
    with open(out_report, "w") as f:
        json.dump(report, f, indent=2)

    s = report["summary"]
    print("\n[verify] iterations: %d" % report["iterations"])
    print("[verify] checks: %d total | %d pass | %d fail | %d unresolved"
          % (s["checks_total"], s["passed"], s["failed"], s["unresolved"]))
    print("[verify] re-verified: %d | false positives averted: %d | confirmed after re-crawl: %d"
          % (s["reverified"], s["false_positives_averted"], s["violations_confirmed_after_recrawl"]))
    print("[verify] findings → %s" % out_findings)
    print("[verify] report   → %s" % out_report)


if __name__ == "__main__":
    main()
