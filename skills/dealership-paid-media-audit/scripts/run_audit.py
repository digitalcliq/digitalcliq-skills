#!/usr/bin/env python3
"""
run_audit.py — Main CLI entry point for the paid media waste audit.

Usage:
  python3 run_audit.py \
    --client "Nissan of Irvine" \
    --source googleads \
    --file /path/to/export.csv \
    --period 2026-03 \
    [--compare-prior]

Multiple sources can be specified:
  python3 run_audit.py \
    --client "Nissan of Irvine" \
    --source googleads --file /path/to/google.csv \
    --source metaads --file /path/to/meta.csv \
    --period 2026-03
"""

import argparse
import sys
from pathlib import Path

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from collections import defaultdict
from ingest import ingest
from audit_engine import run_audit
from report_builder import generate_report


def deduplicate_rows(rows: list) -> list:
    """
    Handle overlapping campaign-level and search-term-level data from the same
    platform (e.g., Google Ads campaign report + search terms report).

    Strategy:
    - Campaign-level rows are the SOURCE OF TRUTH for spend, conversions,
      impressions, and clicks. They go into the audit for funnel allocation,
      waste rules, and executive summary.
    - Search-term rows are kept ONLY for search term bleed analysis (Rule 4).
      Their spend/clicks/impressions are zeroed out to prevent double-counting,
      but the search_term text + match type are preserved.
    - Removed/paused campaigns with $0 spend are filtered out entirely.
    - GA4/other-platform rows pass through untouched.
    """
    # Separate by platform
    by_platform = defaultdict(lambda: {"campaign": [], "search_term": [], "page": []})
    for r in rows:
        platform = r.get("source_platform", "unknown")
        row_type = r.get("_row_type", "campaign")
        by_platform[platform][row_type].append(r)

    # Ad platforms where campaign-level dedup makes sense
    AD_PLATFORMS = {"google_ads", "meta_ads", "microsoft_ads"}

    deduped = []
    for platform, groups in by_platform.items():
        campaign_rows = groups["campaign"]
        search_term_rows = groups["search_term"]
        page_rows = groups["page"]

        # Only filter removed/paused $0 campaigns for ad platforms
        if platform in AD_PLATFORMS:
            active_campaigns = [
                r for r in campaign_rows
                if r.get("spend", 0) > 0 or r.get("impressions", 0) > 0
            ]
            removed_count = len(campaign_rows) - len(active_campaigns)
            if removed_count > 0:
                print(f"[Dedup] Filtered {removed_count} removed/paused $0 campaigns from {platform}")
        else:
            active_campaigns = campaign_rows

        # If we have BOTH campaign-level and search-term rows from the same
        # ad platform, zero out spend on search terms to prevent double-counting
        if platform in AD_PLATFORMS and active_campaigns and search_term_rows:
            print(f"[Dedup] {platform}: {len(active_campaigns)} campaign rows + "
                  f"{len(search_term_rows)} search term rows detected")
            print(f"[Dedup] Using campaign-level data for spend/conversions, "
                  f"search terms for bleed analysis only")

            for r in search_term_rows:
                # Preserve search term text for bleed detection but zero out
                # metrics that would double-count with campaign-level data
                r["_original_spend"] = r.get("spend", 0)
                r["_original_clicks"] = r.get("clicks", 0)
                r["_original_impressions"] = r.get("impressions", 0)
                r["spend"] = 0
                r["clicks"] = 0
                r["impressions"] = 0
                r["_deduped"] = True

            deduped.extend(active_campaigns)
            deduped.extend(search_term_rows)
        else:
            # No overlap — pass everything through
            deduped.extend(active_campaigns if active_campaigns else campaign_rows)
            deduped.extend(search_term_rows)

        deduped.extend(page_rows)

    print(f"[Dedup] Final row count: {len(deduped)} (from {len(rows)} raw)")
    return deduped


def main():
    parser = argparse.ArgumentParser(
        description="DigitalCLIQ Paid Media Waste Audit"
    )
    parser.add_argument("--client", required=True, help="Client/dealership name")
    parser.add_argument("--period", required=True, help="Report period (YYYY-MM)")
    parser.add_argument(
        "--source", action="append", required=True,
        help="Source type (googleads, metaads, microsoftads, ga4, thirdparty, oem, crm)"
    )
    parser.add_argument(
        "--file", action="append", required=True,
        help="Input file path (one per --source flag, in matching order)"
    )
    parser.add_argument(
        "--compare-prior", action="store_true", default=False,
        help="Compare against prior period run for delta tracking"
    )
    parser.add_argument(
        "--output", default=None,
        help="Override output file path"
    )

    args = parser.parse_args()

    if len(args.source) != len(args.file):
        print("ERROR: Must provide one --file for each --source flag.")
        sys.exit(1)

    # Ingest all sources
    all_rows = []
    for source, filepath in zip(args.source, args.file):
        print(f"\n{'='*60}")
        print(f"  Ingesting: {source} from {filepath}")
        print(f"{'='*60}")
        rows = ingest(source, filepath)
        all_rows.extend(rows)

    if not all_rows:
        print("ERROR: No data ingested from any source. Check file paths and formats.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Total rows ingested: {len(all_rows)}")
    print(f"{'='*60}")

    # --- Deduplicate overlapping campaign + search term data ---
    all_rows = deduplicate_rows(all_rows)

    # Run audit
    audit_result = run_audit(
        rows=all_rows,
        client_name=args.client,
        period=args.period,
        compare_prior=args.compare_prior,
    )

    # Generate report
    output_path = generate_report(
        audit=audit_result,
        raw_rows=all_rows,
        output_path=args.output,
    )

    # Print summary
    es = audit_result["executive_summary"]
    print(f"\n{'='*60}")
    print(f"  AUDIT COMPLETE — {args.client}")
    print(f"{'='*60}")
    print(f"  Total Spend:      ${es['total_spend']:,.2f}")
    print(f"  Total Leads:      {es['total_leads']:,}")
    print(f"  CPL:              {'${:,.2f}'.format(es['cpl']) if es['cpl'] else 'N/A'}")
    print(f"  Est. Waste:       ${es['estimated_waste_usd']:,.2f} ({es['estimated_waste_pct']:.1f}%)")
    print(f"  Findings:         {es['finding_count']} ({es['high_severity_count']} high, {es['medium_severity_count']} medium)")
    print(f"  Suggestions:      {len(audit_result['suggestions'])}")
    print(f"  Report:           {output_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
