#!/usr/bin/env python3
"""
delta_engine.py — Stage 4: Month-over-month delta comparison.

Compares current audit findings against the previous month's snapshot
to classify each finding as NEW, PERSISTING, or RESOLVED.

Matching logic: Two findings are considered the "same" if they share
the same rule_id AND page_url (same rule violation on same page).
"""

import json
import re
from pathlib import Path
from urllib.parse import urlparse

# A vehicle detail page URL embeds the VIN/stock number, which changes every
# month as inventory turns over. Matching VDP findings on the raw URL would make
# every VDP issue churn NEW→RESOLVED forever. We bucket them to a per-site,
# per-page-type key so "VDPs are missing the finance disclosure" tracks as one
# persisting issue across months even though the specific cars differ.
_VDP_PAGE_RE = re.compile(r"^vdp(?:_\d+)?$")
_VDP_URL_RE = re.compile(
    r"/(?:inventory|vehicle|vehicledetails|vdp|auto|cars?)/|[A-HJ-NPR-Z0-9]{17}", re.I)


def _is_vdp(finding):
    page = (finding.get("page") or "").strip()
    if page and _VDP_PAGE_RE.match(page):
        return True
    # Fallback for prior snapshots written before findings carried `page`.
    if not page:
        return bool(_VDP_URL_RE.search(finding.get("page_url", "")))
    return False


def _finding_key(finding):
    """Stable cross-month key. VDP findings collapse to a per-site VDP bucket."""
    rule_id = finding.get("rule_id", "").strip()
    page_url = finding.get("page_url", "").strip().rstrip("/")
    if _is_vdp(finding):
        netloc = urlparse(page_url).netloc or page_url
        return f"{rule_id}|{netloc}|#vdp"
    return f"{rule_id}|{page_url}"


def compute_delta(current_findings, prior_findings=None):
    """Compare current findings against prior month's findings.

    Args:
        current_findings: List of finding dicts from this month's audit
        prior_findings: List of finding dicts from last month's audit (None if first audit)

    Returns:
        Dict with:
          - tagged_findings: current findings with 'delta_status' added ('new' or 'persisting')
          - resolved: prior findings no longer present ('resolved')
          - counts: {'new': N, 'persisting': N, 'resolved': N}
          - is_first_audit: bool
    """
    if prior_findings is None:
        # First audit — everything is NEW
        tagged = []
        for f in current_findings:
            fc = dict(f)
            fc["delta_status"] = "new"
            tagged.append(fc)

        return {
            "tagged_findings": tagged,
            "resolved": [],
            "counts": {
                "new": len(tagged),
                "persisting": 0,
                "resolved": 0,
            },
            "is_first_audit": True,
        }

    # Build lookup from prior findings
    prior_keys = {}
    for f in prior_findings:
        key = _finding_key(f)
        prior_keys[key] = f

    # Tag current findings
    tagged = []
    current_keys = set()
    for f in current_findings:
        fc = dict(f)
        key = _finding_key(f)
        current_keys.add(key)

        if key in prior_keys:
            fc["delta_status"] = "persisting"
            # Carry forward the prior month's finding for reference
            fc["prior_severity"] = prior_keys[key].get("severity", "")
        else:
            fc["delta_status"] = "new"

        tagged.append(fc)

    # Second pass (2026-09-16, McPeek run): judgment findings (AI-*) are one issue
    # class per rule_id, and older snapshots stored non-URL locations such as
    # "specials page (URL not captured in crawl)". Exact-key matching then showed the
    # same issue as both NEW and RESOLVED. Pair leftovers by rule_id for AI-* rules,
    # or when the prior location is not a real URL.
    unmatched_prior = {k: f for k, f in prior_keys.items() if k not in current_keys}
    for fc in tagged:
        if fc["delta_status"] != "new":
            continue
        rid = fc.get("rule_id", "")
        for pk, pf in list(unmatched_prior.items()):
            if pf.get("rule_id") != rid:
                continue
            prior_url = (pf.get("page_url") or "").strip()
            if rid.startswith("AI-") or not prior_url.startswith("http"):
                fc["delta_status"] = "persisting"
                fc["prior_severity"] = pf.get("severity", "")
                del unmatched_prior[pk]
                break

    # Find resolved issues (in prior but not in current)
    resolved = []
    for key, f in unmatched_prior.items():
        fc = dict(f)
        fc["delta_status"] = "resolved"
        resolved.append(fc)

    counts = {
        "new": sum(1 for f in tagged if f["delta_status"] == "new"),
        "persisting": sum(1 for f in tagged if f["delta_status"] == "persisting"),
        "resolved": len(resolved),
    }

    return {
        "tagged_findings": tagged,
        "resolved": resolved,
        "counts": counts,
        "is_first_audit": False,
    }


def load_prior_snapshot(history_dir, client_name, current_month):
    """Find and load the most recent prior snapshot for a client.

    Args:
        history_dir: Path to the history/ directory
        client_name: Client name (will be normalized)
        current_month: This run's snapshot key to exclude. Prefer a full date
            'YYYY-MM-DD' so two audits in the same calendar month compare against
            each other instead of skipping back a month. Legacy 'YYYY-MM' keys
            still sort correctly against dated ones.

    Returns:
        (findings_list, snapshot_path) or (None, None) if no prior snapshot
    """
    history_dir = Path(history_dir)
    safe_client = client_name.lower().replace(" ", "_")

    history_files = sorted(history_dir.glob(f"{safe_client}_*.json"), reverse=True)

    for hf in history_files:
        month_str = hf.stem.replace(f"{safe_client}_", "")
        if month_str < current_month:
            with open(hf, "r") as f:
                return json.load(f), str(hf)

    return None, None


def save_snapshot(findings, history_dir, client_name, month):
    """Save current findings as a monthly snapshot.

    Args:
        findings: List of finding dicts (without delta_status)
        history_dir: Path to the history/ directory
        client_name: Client name
        month: Month string 'YYYY-MM'

    Returns:
        Path to saved snapshot file
    """
    history_dir = Path(history_dir)
    history_dir.mkdir(exist_ok=True)

    safe_client = client_name.lower().replace(" ", "_")
    snapshot_path = history_dir / f"{safe_client}_{month}.json"

    # Strip delta_status before saving (raw findings only)
    clean = []
    for f in findings:
        fc = dict(f)
        fc.pop("delta_status", None)
        fc.pop("prior_severity", None)
        clean.append(fc)

    with open(snapshot_path, "w") as f:
        json.dump(clean, f, indent=2)

    return str(snapshot_path)


if __name__ == "__main__":
    # Quick test
    prior = [
        {"rule_id": "CA-PRICE-001", "page_url": "https://example.com/specials", "severity": "critical", "title": "Missing total price"},
        {"rule_id": "CA-DEALER-001", "page_url": "https://example.com/about", "severity": "critical", "title": "Missing dealer name"},
    ]
    current = [
        {"rule_id": "CA-PRICE-001", "page_url": "https://example.com/specials", "severity": "critical", "title": "Missing total price"},
        {"rule_id": "CA-REGZ-001", "page_url": "https://example.com/finance", "severity": "critical", "title": "Missing Reg Z disclosures"},
    ]

    result = compute_delta(current, prior)
    print(f"NEW: {result['counts']['new']}")
    print(f"PERSISTING: {result['counts']['persisting']}")
    print(f"RESOLVED: {result['counts']['resolved']}")

    for f in result["tagged_findings"]:
        print(f"  [{f['delta_status'].upper()}] {f['rule_id']}: {f['title']}")
    for f in result["resolved"]:
        print(f"  [RESOLVED] {f['rule_id']}: {f['title']}")
