#!/usr/bin/env python3
"""
run_audit.py — Main orchestrator for the dealership compliance audit pipeline.

This script is called by Claude AFTER Stages 1-3 are complete (those are AI-driven).
It orchestrates Stages 4-5:
  Stage 4: Delta engine (compare current vs. last month)
  Stage 5: Generate branded Excel report

Usage (called by Claude):
  python3 run_audit.py --findings /tmp/findings.json --client "Sterling BMW" --brand bmw

The findings JSON is produced by Claude in Stages 1-3 and saved to a temp file.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Resolve paths relative to the skill directory
SKILL_DIR = Path(__file__).resolve().parent.parent
HISTORY_DIR = SKILL_DIR / "history"
# Canonical vault outputs folder (vault-facts ledger + CLAUDE.md Rule 18).
# The skill package now lives OUTSIDE the vault (skills-plugin dir), so walking up
# parents no longer lands on the vault. Honor an explicit DIGITALCLIQ_VAULT_ROOT env
# var (vault-facts: "must be given the path explicitly"); fall back to the old
# three-parents derivation only when the env var is unset.
_env_root = os.environ.get("DIGITALCLIQ_VAULT_ROOT")
VAULT_ROOT = Path(_env_root).resolve() if _env_root else SKILL_DIR.parent.parent.parent
OUTPUTS_DIR = VAULT_ROOT / "outputs"
SCRIPTS_DIR = SKILL_DIR / "scripts"

# Ensure dirs exist
HISTORY_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)


def _strip_markdown(text):
    """Excel renders no Markdown, so raw ``**bold**`` markers print literally in
    cells and read as an unfinished template. Strip them from every text field and
    normalize the long ``**NEEDS HUMAN REVIEW AND VERIFICATION**`` disclaimer prefix
    to a plain, colon-terminated label so the meaning still carries in text."""
    if not isinstance(text, str):
        return text
    import re
    # Normalize the standard human-review disclaimer prefix (with or without the
    # trailing em-dash/colon the registry emits) to a compact plain-text label.
    text = re.sub(
        r"\*\*\s*NEEDS HUMAN REVIEW(?: AND VERIFICATION)?\s*\*\*\s*[—:-]*\s*",
        "NEEDS HUMAN REVIEW: ",
        text,
    )
    # Remove any remaining bold/italic Markdown markers.
    text = text.replace("**", "").replace("__", "")
    return text


def load_findings(findings_path):
    """Load the structured findings JSON produced by Claude (Stages 1-3)."""
    with open(findings_path, "r") as f:
        findings = json.load(f)
    text_fields = ("title", "quote", "evidence", "recommendation", "statute")
    for fnd in findings:
        if not isinstance(fnd, dict):
            continue
        for k in text_fields:
            if k in fnd:
                fnd[k] = _strip_markdown(fnd[k])
    return findings


def backfill_brand_citations(findings, brand):
    """Give every brand finding a real guideline citation in its `statute` field.

    The cloud judgment agent is told statute may be an empty string for brand
    rules, which left the Statute column blank on the Brand Violations tab. That
    citation is exactly what a co-op / ANSIRA dispute needs, so resolve each
    brand rule_id back to its entry in brands/{brand}_guidelines.json.
    """
    rules_path = SKILL_DIR / "brands" / f"{brand.lower()}_guidelines.json"
    if not rules_path.exists():
        return findings
    with open(rules_path, "r") as f:
        g = json.load(f)
    program = g.get("program") or g.get("source") or ""
    by_id = {c.get("id"): c for c in g.get("checks", []) if c.get("id")}

    filled = 0
    for fnd in findings:
        if fnd.get("source") != "brand_check" or (fnd.get("statute") or "").strip():
            continue
        rule = by_id.get(fnd.get("rule_id"))
        if rule:
            fnd["statute"] = f"{program} — {rule.get('category','')}: {rule.get('title','')}".strip(" —:")
        elif program:
            fnd["statute"] = program
        filled += 1
    if filled:
        print(f"[Pipeline] Backfilled guideline citations on {filled} brand finding(s)")
    return findings


def run_delta(findings, client_name):
    """Run Stage 4: Delta engine."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    from delta_engine import compute_delta

    now = datetime.now()
    # Snapshots are keyed by full DATE, not month. Two audits in the same calendar
    # month used to collide: the second run overwrote the first run's snapshot AND
    # skipped it as a baseline (month_str < current_month is False for the same
    # month), silently diffing against the month before instead. Date keys sort
    # correctly against legacy YYYY-MM names ("2026-05" < "2026-07-24").
    current_key = now.strftime("%Y-%m-%d")

    # Find the most recent prior snapshot
    safe_client = client_name.lower().replace(" ", "_")
    prior_snapshot = None
    prior_path = None

    # Look for most recent snapshot taken strictly before this run
    history_files = sorted(HISTORY_DIR.glob(f"{safe_client}_*.json"), reverse=True)
    for hf in history_files:
        month_str = hf.stem.replace(f"{safe_client}_", "")
        if month_str < current_key:
            with open(hf, "r") as f:
                prior_snapshot = json.load(f)
            prior_path = str(hf)
            break

    # Compute delta
    delta_results = compute_delta(findings, prior_snapshot)

    # Save current snapshot for the next run's comparison
    snapshot_path = HISTORY_DIR / f"{safe_client}_{current_key}.json"
    with open(snapshot_path, "w") as f:
        json.dump(findings, f, indent=2)

    print(f"[Stage 4] Delta computed. Prior snapshot: {prior_path or 'None (first audit)'}")
    print(f"[Stage 4] Snapshot saved: {snapshot_path}")
    print(f"[Stage 4] NEW: {delta_results['counts']['new']}, "
          f"PERSISTING: {delta_results['counts']['persisting']}, "
          f"RESOLVED: {delta_results['counts']['resolved']}")

    return delta_results


def run_report(findings, delta_results, client_name, brand, url, verification_report=None):
    """Run Stage 5: Generate branded Excel report."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    from generate_report import build_report

    now = datetime.now()
    current_month = now.strftime("%Y-%m")
    safe_client = client_name.lower().replace(" ", "_")
    output_path = OUTPUTS_DIR / f"{safe_client}_compliance_audit_{current_month}.xlsx"

    build_report(
        findings=findings,
        delta_results=delta_results,
        client_name=client_name,
        brand=brand.upper(),
        url=url,
        output_path=str(output_path),
        audit_date=now.strftime("%B %d, %Y"),
        verification_report=verification_report,
    )

    print(f"[Stage 5] Report generated: {output_path}")
    return str(output_path)


def main():
    parser = argparse.ArgumentParser(description="Dealership Compliance Audit — Stages 4-5")
    parser.add_argument("--findings", required=True, help="Path to findings JSON from Stages 1-3")
    parser.add_argument("--client", required=True, help="Client name (e.g., 'Sterling BMW')")
    parser.add_argument("--brand", required=True, help="Brand: bmw, nissan, cdjr")
    parser.add_argument("--url", default="", help="Dealership URL (for report header)")
    parser.add_argument("--verification", default=None,
                        help="Optional path to verify_loop's verification_report.json (adds Re-Verification tab)")
    args = parser.parse_args()

    # Load findings
    findings = load_findings(args.findings)
    print(f"[Pipeline] Loaded {len(findings)} findings for {args.client}")
    findings = backfill_brand_citations(findings, args.brand)

    verification_report = None
    if args.verification and os.path.exists(args.verification):
        with open(args.verification) as f:
            verification_report = json.load(f)
        print(f"[Pipeline] Loaded verification report: {args.verification}")

    # Stage 4: Delta
    delta_results = run_delta(findings, args.client)

    # Stage 5: Report
    output_path = run_report(findings, delta_results, args.client, args.brand, args.url,
                             verification_report=verification_report)

    print(f"\n[Pipeline] Audit complete. Report: {output_path}")
    return output_path


if __name__ == "__main__":
    main()
