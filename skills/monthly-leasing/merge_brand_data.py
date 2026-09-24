#!/usr/bin/env python3
"""
DigitalCLIQ — Merge Per-Brand Lease Data
Reads per-brand JSON files from /tmp/, validates, deduplicates,
and produces a single combined JSON for report generation.

Usage:
    python3 merge_brand_data.py --month 2026-02 \
        --roster /path/to/dealer_roster.json \
        --output /tmp/lease_data_combined_2026-02.json
"""

import argparse
import glob
import json
import os
import sys
from datetime import datetime


def load_roster(roster_path):
    """Load dealer_roster.json and return the parsed dict."""
    with open(roster_path, "r") as f:
        return json.load(f)


def find_brand_files(month, brands=None):
    """
    Scan /tmp/ for lease_data_{brand}_{month}.json files.
    Returns {brand_key: file_path} for each found file.
    If brands is specified, only look for those brands.
    """
    pattern = f"/tmp/lease_data_*_{month}.json"
    found = {}
    for path in glob.glob(pattern):
        filename = os.path.basename(path)
        # Extract brand key from filename: lease_data_{brand}_{month}.json
        prefix = "lease_data_"
        suffix = f"_{month}.json"
        if filename.startswith(prefix) and filename.endswith(suffix):
            brand_key = filename[len(prefix):-len(suffix)]
            # Skip the combined file
            if brand_key == "combined":
                continue
            if brands is None or brand_key in brands:
                found[brand_key] = path
    return found


# ── Per-Brand Data Validation ─────────────────────────────────────

BRAND_META_SCHEMA = {
    "brand":              ("str",  True),
    "brand_display":      ("str",  True),
    "cap_date":           ("str",  True),
    "month":              ("str",  True),
    "run_timestamp":      ("str",  True),
    "dealers_in_roster":  ("num",  False),
    "dealers_scraped":    ("num",  False),
    "dealers_with_offers":("num",  False),
    "total_offers":       ("num",  False),
}

BRAND_OFFER_REQUIRED = {
    "brand":       "str",
    "dealer_name": "str",
    "dealer_url":  "str",
    "pmt":         "num",
}

BRAND_OFFER_ALL = {
    "brand": "str", "dealer_name": "str", "dealer_url": "str",
    "source_url": "str", "page_type": "str", "yr": "num", "make": "str",
    "model": "str", "trim": "str", "msrp": "num", "pmt": "num",
    "term_mo": "num", "das": "num", "miles_yr": "num", "sec_dep": "str",
    "exp": "str", "vin": "str", "is_national": "bool01",
    "disclaimer_scope": "str", "disclaimer_text": "str",
    "info_flags": "str", "parse_note": "str", "source_credit": "str",
}

DEALER_STATUS_SCHEMA = {
    "name":          ("str",  True),
    "url":           ("str",  True),
    "offers_found":  ("num",  False),
    "status":        ("str",  False),
}


def _type_name(expected):
    """Human-readable type label."""
    mapping = {
        "str": "string", "int": "integer", "float": "float",
        "num": "number (int or float)", "list": "list",
        "dict": "dict", "list[dict]": "list of dicts", "bool01": "0 or 1",
    }
    return mapping.get(expected, expected)


def _check_type(value, expected):
    """Check if value matches the expected type spec."""
    if expected == "str":
        return isinstance(value, str)
    elif expected == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    elif expected == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    elif expected == "num":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    elif expected == "list":
        return isinstance(value, list)
    elif expected == "dict":
        return isinstance(value, dict)
    elif expected == "list[dict]":
        return isinstance(value, list) and all(isinstance(i, dict) for i in value)
    elif expected == "bool01":
        return value in (0, 1)
    return True


def validate_brand_data(data, brand_key, source_path="<input>"):
    """
    Validate a per-brand lease data JSON before merging.

    Checks:
      1. All required top-level and nested fields exist
      2. Data types match expectations (list-of-dicts vs flat dict)
      3. No empty/null values in required fields

    Returns (is_valid, errors) where errors is a list of descriptive strings.
    Prints a clear error report showing expected vs actual format on failure.
    """
    errors = []

    # ── 1. Top-level structure ────────────────────────────────────
    if not isinstance(data, dict):
        errors.append(
            f"Top-level: expected dict, got {type(data).__name__}\n"
            f"  Expected: {{\"metadata\": {{...}}, \"offers\": [...], \"dealer_status\": [...]}}\n"
            f"  Actual:   {type(data).__name__}"
        )
        return False, errors

    for key, expected_type in [("metadata", "dict"), ("offers", "list[dict]")]:
        val = data.get(key)
        if val is None:
            errors.append(
                f"Top-level: missing required key '{key}'\n"
                f"  Expected: {_type_name(expected_type)}\n"
                f"  Actual:   key not present"
            )
        elif not _check_type(val, expected_type):
            actual = type(val).__name__
            if isinstance(val, list) and val and not isinstance(val[0], dict):
                actual = f"list of {type(val[0]).__name__}"
            errors.append(
                f"Top-level key '{key}': wrong type\n"
                f"  Expected: {_type_name(expected_type)}\n"
                f"  Actual:   {actual}"
            )

    # dealer_status is expected but optional
    ds_val = data.get("dealer_status")
    if ds_val is not None and not _check_type(ds_val, "list[dict]"):
        actual = type(ds_val).__name__
        if isinstance(ds_val, list) and ds_val and not isinstance(ds_val[0], dict):
            actual = f"list of {type(ds_val[0]).__name__}"
        errors.append(
            f"Top-level key 'dealer_status': wrong type\n"
            f"  Expected: {_type_name('list[dict]')}\n"
            f"  Actual:   {actual}"
        )

    # ── 2. Metadata fields ────────────────────────────────────────
    metadata = data.get("metadata", {})
    if isinstance(metadata, dict):
        for field, (exp_type, required) in BRAND_META_SCHEMA.items():
            val = metadata.get(field)
            if val is None:
                if required:
                    errors.append(
                        f"metadata.{field}: missing required field\n"
                        f"  Expected: {_type_name(exp_type)}\n"
                        f"  Actual:   not present"
                    )
            elif not _check_type(val, exp_type):
                errors.append(
                    f"metadata.{field}: wrong type\n"
                    f"  Expected: {_type_name(exp_type)}\n"
                    f"  Actual:   {type(val).__name__} = {repr(val)[:80]}"
                )
            elif required and exp_type == "str" and not val:
                errors.append(
                    f"metadata.{field}: required field is empty\n"
                    f"  Expected: non-empty {_type_name(exp_type)}\n"
                    f"  Actual:   \"\""
                )

    # ── 3. Offers validation ──────────────────────────────────────
    offers = data.get("offers", [])
    if isinstance(offers, list):
        for i, offer in enumerate(offers):
            if not isinstance(offer, dict):
                errors.append(
                    f"offers[{i}]: wrong type\n"
                    f"  Expected: dict\n"
                    f"  Actual:   {type(offer).__name__}"
                )
                continue

            # Required fields must exist and be non-null
            for field, exp_type in BRAND_OFFER_REQUIRED.items():
                val = offer.get(field)
                if val is None:
                    errors.append(
                        f"offers[{i}].{field}: missing required field\n"
                        f"  Expected: {_type_name(exp_type)} (non-null)\n"
                        f"  Actual:   not present\n"
                        f"  Offer:    {offer.get('dealer_name', '?')} / {offer.get('model', '?')}"
                    )
                elif not _check_type(val, exp_type):
                    errors.append(
                        f"offers[{i}].{field}: wrong type\n"
                        f"  Expected: {_type_name(exp_type)}\n"
                        f"  Actual:   {type(val).__name__} = {repr(val)[:60]}\n"
                        f"  Offer:    {offer.get('dealer_name', '?')} / {offer.get('model', '?')}"
                    )

            # Type checks on all known fields
            for field, exp_type in BRAND_OFFER_ALL.items():
                val = offer.get(field)
                if val is not None and not _check_type(val, exp_type):
                    errors.append(
                        f"offers[{i}].{field}: wrong type\n"
                        f"  Expected: {_type_name(exp_type)}\n"
                        f"  Actual:   {type(val).__name__} = {repr(val)[:60]}\n"
                        f"  Offer:    {offer.get('dealer_name', '?')} / {offer.get('model', '?')}"
                    )

            if len(errors) > 50:
                errors.append(f"... (stopped checking at offer {i}, too many errors)")
                break

    # ── 4. Dealer status validation ───────────────────────────────
    dealer_status = data.get("dealer_status", [])
    if isinstance(dealer_status, list):
        for i, ds in enumerate(dealer_status):
            if not isinstance(ds, dict):
                errors.append(
                    f"dealer_status[{i}]: wrong type\n"
                    f"  Expected: dict\n"
                    f"  Actual:   {type(ds).__name__}"
                )
                continue
            for field, (exp_type, required) in DEALER_STATUS_SCHEMA.items():
                val = ds.get(field)
                if val is None and required:
                    errors.append(
                        f"dealer_status[{i}].{field}: missing required field\n"
                        f"  Expected: {_type_name(exp_type)}\n"
                        f"  Actual:   not present"
                    )

    # ── Report ────────────────────────────────────────────────────
    is_valid = len(errors) == 0

    if not is_valid:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"VALIDATION FAILED — {brand_key} — {source_path}", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        print(f"{len(errors)} error(s) found:\n", file=sys.stderr)
        for i, err in enumerate(errors, 1):
            print(f"  {i}. {err}\n", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)

    return is_valid, errors


def validate_offer(offer, valid_models=None):
    """
    Validate a single offer dict.
    - Ensure required fields exist
    - Fill defaults for missing optional fields
    - Flag missing VIN in parse_note
    Returns (cleaned_offer, list_of_warnings)
    """
    warnings = []
    o = dict(offer)

    # Required fields
    for field in ("brand", "dealer_name", "dealer_url", "pmt"):
        if not o.get(field):
            warnings.append(f"missing required field: {field}")

    # Validate model against dictionary if provided
    if valid_models and o.get("model"):
        model = o["model"]
        if model not in valid_models:
            # Try case-insensitive match
            match = next((m for m in valid_models if m.lower() == model.lower()), None)
            if match:
                o["model"] = match
            else:
                warnings.append(f"model '{model}' not in dictionary")

    # Numeric defaults
    for field in ("yr", "msrp", "pmt", "term_mo", "das", "miles_yr"):
        if o.get(field) is None:
            o[field] = 0

    # String defaults
    for field in ("make", "model", "trim", "sec_dep", "exp", "vin",
                   "disclaimer_scope", "disclaimer_text", "info_flags",
                   "parse_note", "source_credit", "page_type", "source_url"):
        if o.get(field) is None:
            o[field] = ""

    # Flag missing VIN
    if not o.get("vin"):
        existing_note = o.get("parse_note", "")
        if "no VIN" not in existing_note:
            if existing_note:
                o["parse_note"] = existing_note + "; no VIN in disclaimer"
            else:
                o["parse_note"] = "no VIN in disclaimer"

    # Default values
    o.setdefault("is_national", 0)
    o.setdefault("source_credit", "DigitalCLIQ")

    return o, warnings


def deduplicate_offers(offers):
    """
    Remove duplicate offers. A duplicate is defined by:
      (dealer_url, model, trim, pmt, term_mo, das)
    When duplicates exist, keep the one with:
      1. Longer disclaimer_text
      2. More info_flags
      3. page_type == 'specials' over 'home'
    """
    seen = {}
    for offer in offers:
        key = (
            offer.get("dealer_url", ""),
            offer.get("model", ""),
            offer.get("trim", ""),
            offer.get("pmt", 0),
            offer.get("term_mo", 0),
            offer.get("das", 0),
        )

        if key not in seen:
            seen[key] = offer
        else:
            existing = seen[key]
            # Score each: longer disclaimer + more flags + specials page preferred
            def score(o):
                s = len(o.get("disclaimer_text", ""))
                s += len(o.get("info_flags", "").split("|")) * 10
                if o.get("page_type") == "specials":
                    s += 5
                return s

            if score(offer) > score(existing):
                seen[key] = offer

    return list(seen.values())


def merge_brand_data(month, roster_path, output_path, brands=None):
    """
    Main merge function:
    1. Load roster
    2. Find brand files
    3. Load each brand file, validate offers
    4. Combine all offers
    5. Deduplicate
    6. Build combined metadata
    7. Write combined JSON
    """
    roster = load_roster(roster_path)
    brand_files = find_brand_files(month, brands)

    if not brand_files:
        print(f"No per-brand JSON files found for month {month} in /tmp/")
        print(f"Expected pattern: /tmp/lease_data_{{brand}}_{month}.json")
        sys.exit(1)

    all_offers = []
    all_dealer_status = []
    brand_runs = {}
    total_dealers = 0
    total_warnings = 0
    cap_date = datetime.now().strftime("%Y-%m-%d")

    # Process each brand file
    for brand_key in sorted(brand_files.keys()):
        filepath = brand_files[brand_key]
        print(f"Loading {brand_key}: {filepath}")

        with open(filepath, "r") as f:
            data = json.load(f)

        # Validate per-brand data before merging
        is_valid, val_errors = validate_brand_data(data, brand_key, filepath)
        if not is_valid:
            print(f"  WARNING: {brand_key} data has {len(val_errors)} validation issue(s) — proceeding with best effort")

        meta = data.get("metadata", {})
        offers = data.get("offers", [])
        dealer_status = data.get("dealer_status", [])

        # Get valid models for this brand
        brand_info = roster.get("brands", {}).get(brand_key, {})
        valid_models = brand_info.get("models", [])

        # Validate each offer
        validated_offers = []
        for offer in offers:
            cleaned, warnings = validate_offer(offer, valid_models)
            validated_offers.append(cleaned)
            total_warnings += len(warnings)
            for w in warnings:
                print(f"  WARNING [{brand_key}]: {w} — {cleaned.get('dealer_name', '?')} {cleaned.get('model', '?')}")

        all_offers.extend(validated_offers)
        all_dealer_status.extend(dealer_status)

        # Track per-brand run info
        brand_runs[brand_key] = {
            "run_timestamp": meta.get("run_timestamp", ""),
            "dealers": meta.get("dealers_scraped", meta.get("dealers_in_roster", 0)),
            "dealers_with_offers": meta.get("dealers_with_offers", 0),
            "offers": len(validated_offers),
        }
        total_dealers += meta.get("dealers_scraped", meta.get("dealers_in_roster", 0))

        # Use most recent cap_date
        if meta.get("cap_date"):
            cap_date = meta["cap_date"]

    # Deduplicate across all brands
    before_dedup = len(all_offers)
    all_offers = deduplicate_offers(all_offers)
    after_dedup = len(all_offers)

    if before_dedup != after_dedup:
        print(f"Deduplicated: {before_dedup} -> {after_dedup} offers ({before_dedup - after_dedup} removed)")

    # Build combined output
    combined = {
        "metadata": {
            "cap_date": cap_date,
            "month": month,
            "run_timestamp": datetime.now().astimezone().isoformat(),
            "total_dealers": total_dealers,
            "total_offers": len(all_offers),
            "brands_included": sorted(brand_files.keys()),
            "brand_runs": brand_runs,
        },
        "dealer_status": all_dealer_status,
        "offers": all_offers,
    }

    with open(output_path, "w") as f:
        json.dump(combined, f, indent=2)

    print(f"\nMerge complete: {output_path}")
    print(f"  Brands: {', '.join(sorted(brand_files.keys()))}")
    print(f"  Dealers: {total_dealers}")
    print(f"  Offers: {len(all_offers)}")
    if total_warnings:
        print(f"  Warnings: {total_warnings}")


def main():
    parser = argparse.ArgumentParser(description="Merge per-brand lease data files")
    parser.add_argument("--month", required=True, help="Month in YYYY-MM format")
    parser.add_argument("--roster", required=True, help="Path to dealer_roster.json")
    parser.add_argument("--output", required=True, help="Output path for combined JSON")
    parser.add_argument("--brands", nargs="*", help="Only include these brands (default: all found)")
    args = parser.parse_args()

    merge_brand_data(args.month, args.roster, args.output, args.brands)


if __name__ == "__main__":
    main()
