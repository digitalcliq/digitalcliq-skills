#!/usr/bin/env python3
"""
delta_engine.py — Online Reputation month-over-month delta tracking.

Compares current reputation ratings/counts against the previous month's snapshot
to compute changes per platform (Google, Yelp, DealerRater, CarFax).

Usage:
    python3 delta_engine.py <current_json> <history_dir> [--output <delta_json>]

The current JSON must have the structure produced by the SKILL.md data collection
step, with metadata.dealer_name and subject_dealer.platforms.{google,yelp,...}.

History snapshots are saved as {safe_dealer_name}_{YYYY-MM}.json in history_dir.
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime


def _safe_name(name):
    """Normalize dealer name to a filesystem-safe string."""
    # Apostrophes and other punctuation become underscores so "McPeek's" maps
    # to the existing mcpeek_s_* history files (fixed 2026-09-14: the raw
    # apostrophe silently orphaned six months of snapshots).
    return re.sub(r"[^a-z0-9]+", "_", name.lower().strip())


def load_prior_snapshot(history_dir, dealer_name, current_month):
    """Find and load the most recent prior snapshot for a dealer.

    Args:
        history_dir: Path to the history/ directory
        dealer_name: Dealer name (will be normalized)
        current_month: Current month string 'YYYY-MM' to exclude

    Returns:
        (snapshot_dict, snapshot_path) or (None, None) if no prior snapshot
    """
    history_dir = Path(history_dir)
    safe_name = _safe_name(dealer_name)

    if not history_dir.exists():
        return None, None

    history_files = sorted(history_dir.glob(f"{safe_name}_*.json"), reverse=True)

    for hf in history_files:
        month_str = hf.stem.replace(f"{safe_name}_", "")
        if month_str < current_month:
            with open(hf, "r") as f:
                return json.load(f), str(hf)

    return None, None


def save_snapshot(data, history_dir, dealer_name, month):
    """Save current ratings as a monthly snapshot.

    Args:
        data: The full report data dict
        history_dir: Path to the history/ directory
        dealer_name: Dealer name
        month: Month string 'YYYY-MM'

    Returns:
        Path to saved snapshot file
    """
    history_dir = Path(history_dir)
    history_dir.mkdir(parents=True, exist_ok=True)

    safe_name = _safe_name(dealer_name)
    snapshot_path = history_dir / f"{safe_name}_{month}.json"

    # Extract just the ratings and counts for snapshot
    platforms = data.get("subject_dealer", {}).get("platforms", {})
    snapshot = {
        "dealer_name": dealer_name,
        "month": month,
        "snapshot_date": data.get("metadata", {}).get("report_date", ""),
        "platforms": {}
    }

    for pkey, pdata in platforms.items():
        snapshot["platforms"][pkey] = {
            "rating": pdata.get("rating"),
            "review_count": pdata.get("review_count"),
        }

    with open(snapshot_path, "w") as f:
        json.dump(snapshot, f, indent=2)

    return str(snapshot_path)


def compute_delta(current_data, prior_snapshot=None):
    """Compare current ratings against prior snapshot.

    Args:
        current_data: Full report data dict
        prior_snapshot: Prior month's snapshot dict (None if first report)

    Returns:
        Dict with per-platform deltas and summary
    """
    current_platforms = current_data.get("subject_dealer", {}).get("platforms", {})

    if prior_snapshot is None:
        # First report — no delta
        result = {
            "is_first_report": True,
            "prior_date": None,
            "platforms": {}
        }
        for pkey, pdata in current_platforms.items():
            result["platforms"][pkey] = {
                "current_rating": pdata.get("rating"),
                "current_count": pdata.get("review_count"),
                "prior_rating": None,
                "prior_count": None,
                "rating_change": 0,
                "count_change": 0,
                "status": "new"
            }
        return result

    prior_platforms = prior_snapshot.get("platforms", {})
    prior_date = prior_snapshot.get("snapshot_date", prior_snapshot.get("month", "unknown"))

    result = {
        "is_first_report": False,
        "prior_date": prior_date,
        "platforms": {}
    }

    all_keys = set(list(current_platforms.keys()) + list(prior_platforms.keys()))

    for pkey in all_keys:
        curr = current_platforms.get(pkey, {})
        prior = prior_platforms.get(pkey, {})

        curr_rating = curr.get("rating")
        prior_rating = prior.get("rating")
        curr_count = curr.get("review_count", 0)
        prior_count = prior.get("review_count", 0)

        # Compute changes
        rating_change = 0
        if isinstance(curr_rating, (int, float)) and isinstance(prior_rating, (int, float)):
            rating_change = round(curr_rating - prior_rating, 2)

        count_change = 0
        if isinstance(curr_count, (int, float)) and isinstance(prior_count, (int, float)):
            count_change = int(curr_count - prior_count)

        # Determine status
        if rating_change > 0:
            status = "improved"
        elif rating_change < 0:
            status = "declined"
        else:
            status = "stable"

        result["platforms"][pkey] = {
            "current_rating": curr_rating,
            "current_count": curr_count,
            "prior_rating": prior_rating,
            "prior_count": prior_count,
            "rating_change": rating_change,
            "count_change": count_change,
            "status": status,
        }

    return result


def run(current_json_path, history_dir, output_path=None):
    """Full delta pipeline: load prior, compute delta, save snapshot, write output."""

    with open(current_json_path, "r") as f:
        current_data = json.load(f)

    dealer_name = current_data.get("metadata", {}).get("dealer_name", "unknown_dealer")
    report_date = current_data.get("metadata", {}).get("report_date", "")

    # Determine current month
    if report_date:
        current_month = report_date[:7]  # YYYY-MM
    else:
        current_month = datetime.now().strftime("%Y-%m")

    # Load prior snapshot
    prior_snapshot, prior_path = load_prior_snapshot(history_dir, dealer_name, current_month)

    if prior_path:
        print(f"Prior snapshot found: {prior_path}")
    else:
        print(f"No prior snapshot found — this is the first report for '{dealer_name}'")

    # Compute delta
    delta = compute_delta(current_data, prior_snapshot)

    # Save current snapshot
    snapshot_path = save_snapshot(current_data, history_dir, dealer_name, current_month)
    print(f"Snapshot saved: {snapshot_path}")

    # Write delta output
    if output_path:
        with open(output_path, "w") as f:
            json.dump(delta, f, indent=2)
        print(f"Delta written: {output_path}")

    return delta


# ── CLI entry point ──────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 delta_engine.py <current_json> <history_dir> [--output <delta_json>]")
        sys.exit(1)

    current_json = sys.argv[1]
    history = sys.argv[2]
    output = None

    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output = sys.argv[idx + 1]

    run(current_json, history, output)
