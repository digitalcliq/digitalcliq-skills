"""
ingest.py — Unified ingest module for all paid media source types.

Parses source-specific CSV/Excel exports and normalizes them to the internal schema.
Each source type has its own parse function that handles column mapping and cleanup.

Supported sources: googleads, metaads, microsoftads, ga4, thirdparty, oem, crm (stub)
"""

import csv
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = SKILL_DIR / "config"


def _load_column_mappings() -> dict:
    with open(CONFIG_DIR / "column_mappings.json") as f:
        return json.load(f)


def _read_file(filepath: str) -> list[dict]:
    """Read CSV or Excel file into list of dicts."""
    fp = Path(filepath)
    if not fp.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    if fp.suffix.lower() in (".xlsx", ".xls"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(str(fp), read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            wb.close()
            if len(rows) < 2:
                return []
            headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(rows[0])]
            return [dict(zip(headers, row)) for row in rows[1:]]
        except ImportError:
            print("[WARN] openpyxl not installed. Trying CSV fallback.")
            raise
    else:
        # CSV — handle Google Ads exports that have summary rows at top
        with open(str(fp), "r", encoding="utf-8-sig") as f:
            content = f.read()

        # Google Ads exports sometimes have metadata rows before the header
        lines = content.strip().split("\n")
        header_idx = 0
        for i, line in enumerate(lines):
            # Find the first line that looks like a real CSV header:
            # must have 3+ commas (multiple columns) AND contain common column names.
            # This avoids matching metadata lines like "Campaign report" or date ranges.
            comma_count = line.count(",")
            if comma_count >= 3 and any(kw in line.lower() for kw in [
                "impressions", "clicks", "cost", "spend", "sessions",
                "campaign status", "campaign,", "search term,",
                "impr.", "ctr", "avg. cpc",
            ]):
                header_idx = i
                break

        clean_content = "\n".join(lines[header_idx:])
        # Remove summary/total rows at the bottom
        clean_lines = []
        for line in clean_content.split("\n"):
            if line.strip().lower().startswith("total"):
                break
            clean_lines.append(line)

        reader = csv.DictReader(clean_lines)
        return [dict(row) for row in reader]


def _map_columns(rows: list[dict], source: str) -> list[dict]:
    """Map source-specific column names to internal schema using config."""
    mappings = _load_column_mappings()
    source_map = mappings.get(source, {})

    if not source_map:
        print(f"[WARN] No column mappings found for source '{source}'. Using raw columns.")
        return rows

    # Build reverse lookup: source_column_name -> internal_field
    reverse_map = {}
    for internal_field, aliases in source_map.items():
        if internal_field.startswith("_"):
            continue
        if isinstance(aliases, list):
            for alias in aliases:
                reverse_map[alias.lower().strip()] = internal_field

    mapped_rows = []
    for row in rows:
        mapped = {}
        for col, val in row.items():
            if col is None:
                continue
            col_clean = col.strip()
            internal = reverse_map.get(col_clean.lower())
            if internal:
                mapped[internal] = val
            else:
                # Keep unmapped columns with prefix
                mapped[f"_raw_{col_clean}"] = val
        mapped_rows.append(mapped)

    return mapped_rows


def _clean_numeric(val) -> float:
    """Convert a value to float, handling currency symbols, commas, percentages."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s or s in ("--", "N/A", "n/a", "null", ""):
        return 0.0
    # Remove currency symbols and commas
    s = re.sub(r"[\$,]", "", s)
    # Handle percentages
    if s.endswith("%"):
        s = s[:-1]
        try:
            return float(s) / 100.0
        except ValueError:
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _normalize_row(row: dict, source_platform: str, row_type_override: str = None) -> dict:
    """Normalize a mapped row: clean numerics, add source_platform, set defaults."""
    numeric_fields = [
        "spend", "impressions", "clicks", "ctr", "avg_cpc",
        "vdp_views", "srp_views", "form_fills", "phone_calls",
        "direction_clicks", "chat_leads", "leads_total", "sales",
        "cpl", "cps", "conv_rate", "bounce_rate",
        "sessions", "engaged_sessions", "avg_session_duration",
        "conversions", "conv_value", "reach", "frequency",
        "impression_share", "quality_score",
        "coop_reimbursement",
    ]
    normalized = {}
    for k, v in row.items():
        if k in numeric_fields:
            normalized[k] = _clean_numeric(v)
        else:
            normalized[k] = str(v).strip() if v is not None else ""

    normalized["source_platform"] = source_platform

    # Compute leads_total if not set
    if normalized.get("leads_total", 0) == 0:
        component_total = (
            normalized.get("form_fills", 0)
            + normalized.get("phone_calls", 0)
            + normalized.get("chat_leads", 0)
        )
        if component_total > 0:
            normalized["leads_total"] = component_total
        elif normalized.get("conversions", 0) > 0:
            # Fall back to Google Ads "Conversions" when individual lead
            # components aren't broken out (campaign-level exports).
            normalized["leads_total"] = normalized["conversions"]

    # Detect row type: campaign-level vs search-term-level
    if row_type_override:
        normalized["_row_type"] = row_type_override
    else:
        has_search_term = bool(normalized.get("search_term", "").strip())
        has_campaign = bool(normalized.get("campaign", "").strip())
        if has_search_term:
            normalized["_row_type"] = "search_term"
        elif has_campaign:
            normalized["_row_type"] = "campaign"
        else:
            normalized["_row_type"] = "page"

    # Compute CPL if spend and leads available
    if normalized.get("spend", 0) > 0 and normalized.get("leads_total", 0) > 0:
        normalized["cpl"] = round(
            normalized["spend"] / normalized["leads_total"], 2
        )

    return normalized


# ---------------------------------------------------------------------------
# Source-specific ingest functions
# ---------------------------------------------------------------------------

def ingest_googleads(filepath: str) -> list[dict]:
    """Parse Google Ads UI CSV export."""
    rows = _read_file(filepath)
    mapped = _map_columns(rows, "googleads")
    normalized = [_normalize_row(r, "google_ads") for r in mapped]
    print(f"[Ingest] Google Ads: {len(normalized)} rows from {filepath}")
    return normalized


def ingest_metaads(filepath: str) -> list[dict]:
    """Parse Meta Ads Manager CSV export."""
    rows = _read_file(filepath)
    mapped = _map_columns(rows, "metaads")
    normalized = [_normalize_row(r, "meta_ads") for r in mapped]
    print(f"[Ingest] Meta Ads: {len(normalized)} rows from {filepath}")
    return normalized


def ingest_microsoftads(filepath: str) -> list[dict]:
    """Parse Microsoft/Bing Ads CSV export."""
    rows = _read_file(filepath)
    mapped = _map_columns(rows, "microsoftads")
    normalized = [_normalize_row(r, "microsoft_ads") for r in mapped]
    print(f"[Ingest] Microsoft Ads: {len(normalized)} rows from {filepath}")
    return normalized


def ingest_ga4(filepath: str) -> list[dict]:
    """
    Parse GA4 Explore export (Landing Page + Source/Medium + Events).

    Handles TWO export formats:
      A) Session-level: one row per landing page + source/medium (aggregated)
      B) Event-level: one row per landing page + source/medium + event name + date
         → This function aggregates event-level data up to page + source level,
           pivoting event names into automotive KPI columns.

    Expected columns (at minimum):
      - Landing page (or Landing page + query string)
      - Session source / medium (or Session source + Session medium)
      - Sessions
    """
    rows = _read_file(filepath)

    if not rows:
        raise ValueError("GA4 export file is empty.")

    # Filter out grand total / summary rows
    rows = [r for r in rows if not any(
        str(v).lower().strip() == "grand total" for v in r.values()
    )]

    first_row_keys = {k.lower().strip() for k in rows[0].keys() if k is not None}
    required_patterns = [
        ("landing page", ["landing page", "landing page + query string",
                          "page path", "page path + query string"]),
        ("source/medium", ["session source / medium", "session source/medium",
                           "source / medium", "source/medium",
                           "session source"]),
        ("sessions", ["sessions"]),
    ]

    missing = []
    for label, aliases in required_patterns:
        found = any(a.lower() in first_row_keys for a in aliases)
        if not found:
            missing.append(label)

    if missing:
        raise ValueError(
            f"GA4 export is missing required columns: {', '.join(missing)}.\n"
            f"Expected a Landing Page + Source/Medium + Events Explore export.\n"
            f"Columns found: {sorted(rows[0].keys())}\n\n"
            f"To create the right GA4 export:\n"
            f"  1. Open GA4 > Explore > create Free Form report\n"
            f"  2. Rows: Landing page, Session source/medium\n"
            f"  3. Values: Sessions, Engaged sessions, Event count, "
            f"Conversions/Key events\n"
            f"  4. Add any VDP/form/call events as metrics\n"
            f"  5. Export as CSV"
        )

    # Detect if this is event-level data (has Event name column)
    has_event_col = any(
        k.lower().strip() in ("event name", "event_name")
        for k in rows[0].keys()
    )

    if has_event_col:
        # --- Event-level aggregation ---
        # Find the actual column names
        lp_col = next(k for k in rows[0].keys()
                       if k.lower().strip() in ("landing page", "landing page + query string",
                                                  "page path", "page path + query string"))
        sm_col = next(k for k in rows[0].keys()
                       if k.lower().strip() in ("session source / medium",
                                                  "session source/medium",
                                                  "source / medium"))
        ev_col = next(k for k in rows[0].keys()
                       if k.lower().strip() in ("event name", "event_name"))

        # Event-to-KPI mapping for automotive
        VDP_EVENTS = {"vehicle_detail_view", "view_item", "asc_click_inventory_detail",
                      "asc_click_inventorydetail"}
        SRP_EVENTS = {"vehicle_search_results", "view_item_list",
                      "asc_click_inventory_listing", "asc_click_inventorylisting",
                      "asc_click_inventory_search"}
        FORM_EVENTS = {"generate_lead", "form_submit", "form_submission",
                       "asc_form_submission", "asc_form_submission_sales",
                       "contact_form_submit"}
        CALL_EVENTS = {"click_to_call", "phone_call", "asc_click_phonecall",
                       "asc_click_phone"}
        DIRECTION_EVENTS = {"get_directions", "click_to_directions",
                            "asc_click_directions"}
        PAGEVIEW_EVENTS = {"page_view"}
        SESSION_EVENTS = {"session_start"}

        # Aggregate by landing page + source/medium
        agg = {}
        for r in rows:
            lp = str(r.get(lp_col, "")).strip()
            sm = str(r.get(sm_col, "")).strip()
            event = str(r.get(ev_col, "")).strip().lower()
            key = (lp, sm)

            if key not in agg:
                agg[key] = {
                    "landing_page": lp,
                    "source_medium": sm,
                    "sessions": 0,
                    "engaged_sessions": 0,
                    "page_views": 0,
                    "vdp_views": 0,
                    "srp_views": 0,
                    "form_fills": 0,
                    "phone_calls": 0,
                    "direction_clicks": 0,
                    "conversions": 0,
                    "bounce_rate_sum": 0.0,
                    "bounce_rate_count": 0,
                    "event_count": 0,
                    "active_users": 0,
                }

            sessions = _clean_numeric(r.get("Sessions", 0))
            engaged = _clean_numeric(r.get("Engaged sessions", 0))
            evt_count = _clean_numeric(r.get("Event count", 0))
            key_events = _clean_numeric(r.get("Key events", 0))
            active = _clean_numeric(r.get("Active users", 0))
            bounce = _clean_numeric(r.get("Bounce rate", 0))

            agg[key]["event_count"] += evt_count
            agg[key]["conversions"] += key_events

            # Only count sessions from session_start events to avoid double-counting
            if event in SESSION_EVENTS:
                agg[key]["sessions"] += sessions
                agg[key]["engaged_sessions"] += engaged
                agg[key]["active_users"] = max(agg[key]["active_users"], active)
                if bounce > 0:
                    agg[key]["bounce_rate_sum"] += bounce * sessions
                    agg[key]["bounce_rate_count"] += sessions

            if event in PAGEVIEW_EVENTS:
                agg[key]["page_views"] += evt_count

            if event in VDP_EVENTS:
                agg[key]["vdp_views"] += evt_count
            elif event in SRP_EVENTS:
                agg[key]["srp_views"] += evt_count
            elif event in FORM_EVENTS:
                agg[key]["form_fills"] += evt_count
            elif event in CALL_EVENTS:
                agg[key]["phone_calls"] += evt_count
            elif event in DIRECTION_EVENTS:
                agg[key]["direction_clicks"] += evt_count

        # Convert aggregated data to rows
        aggregated_rows = []
        for key, data in agg.items():
            bounce_avg = (data["bounce_rate_sum"] / data["bounce_rate_count"]
                          if data["bounce_rate_count"] > 0 else 0)
            row = {
                "landing_page": data["landing_page"],
                "source_medium": data["source_medium"],
                "sessions": data["sessions"],
                "engaged_sessions": data["engaged_sessions"],
                "vdp_views": data["vdp_views"],
                "srp_views": data["srp_views"],
                "form_fills": data["form_fills"],
                "phone_calls": data["phone_calls"],
                "direction_clicks": data["direction_clicks"],
                "conversions": data["conversions"],
                "bounce_rate": round(bounce_avg, 4),
                "page_views": data["page_views"],
                "active_users": data["active_users"],
                "event_count": data["event_count"],
            }
            aggregated_rows.append(row)

        # Derive campaign from source/medium for funnel classification
        for r in aggregated_rows:
            sm = r.get("source_medium", "")
            lp = r.get("landing_page", "")
            # Use source/medium as the "campaign" for classification
            r["campaign"] = sm
            # Try to extract source and medium separately
            if " / " in sm:
                parts = sm.split(" / ", 1)
                r["_raw_source"] = parts[0]
                r["_raw_medium"] = parts[1]

        normalized = [_normalize_row(r, "ga4", row_type_override="page") for r in aggregated_rows]
        print(f"[Ingest] GA4 (event-level → aggregated): {len(rows)} raw events "
              f"→ {len(normalized)} page+source rows from {filepath}")

        # Print event summary
        event_counts = {}
        for r in rows:
            ev = str(r.get(ev_col, "")).strip().lower()
            event_counts[ev] = event_counts.get(ev, 0) + 1
        top_events = sorted(event_counts.items(), key=lambda x: x[1], reverse=True)[:15]
        print(f"[Ingest] Top events: {', '.join(f'{e}({c})' for e, c in top_events)}")

        return normalized

    else:
        # --- Session-level data (already aggregated) ---
        mapped = _map_columns(rows, "ga4")
        normalized = [_normalize_row(r, "ga4", row_type_override="page") for r in mapped]
        print(f"[Ingest] GA4 (session-level): {len(normalized)} rows from {filepath}")
        return normalized


def ingest_thirdparty(filepath: str) -> list[dict]:
    """
    Parse third-party vendor report (Dealer.com, Sincro, AutoTrader, Cars.com, etc.).
    Uses best-effort column mapping from config.
    """
    rows = _read_file(filepath)
    mapped = _map_columns(rows, "thirdparty")

    # If no columns mapped, warn user
    mapped_fields = set()
    for r in mapped[:1]:
        mapped_fields = {k for k in r.keys() if not k.startswith("_raw_")}
    if len(mapped_fields) < 3:
        print(
            f"[WARN] Only {len(mapped_fields)} columns auto-mapped for third-party file.\n"
            f"       Raw columns: {sorted(rows[0].keys()) if rows else 'none'}\n"
            f"       You may need to update config/column_mappings.json for this vendor."
        )

    normalized = [_normalize_row(r, "third_party") for r in mapped]
    print(f"[Ingest] Third-party: {len(normalized)} rows from {filepath}")
    return normalized


def ingest_oem(filepath: str) -> list[dict]:
    """Parse OEM co-op reporting export (NNAnet, Stellantis, BMW CenterNet)."""
    rows = _read_file(filepath)
    mapped = _map_columns(rows, "oem")
    normalized = [_normalize_row(r, "oem_coop") for r in mapped]
    print(f"[Ingest] OEM co-op: {len(normalized)} rows from {filepath}")
    return normalized


def ingest_crm(filepath: str) -> list[dict]:
    """
    STUB — CRM lead/sale export for closing the loop on CPS and PVR.

    Cross-source matching (CRM leads to ad campaigns) is not yet implemented.
    This function ingests and normalizes the CRM data, but does NOT perform
    attribution matching. That methodology needs further discussion.

    When implemented, this will support:
      - VinSolutions, Elead/CDK, DealerSocket exports
      - Waterfall join: UTM > phone number > timestamp proximity
      - Confidence tagging per match (utm_exact, phone_match, time_proximity)
    """
    print(
        "\n" + "=" * 70 + "\n"
        "  CRM SOURCE — INGESTED BUT NOT CROSS-MATCHED\n"
        "  \n"
        "  The CRM data has been loaded, but cross-source matching\n"
        "  (linking CRM leads/sales back to ad campaigns for CPS/PVR)\n"
        "  is not yet implemented. This requires discussion on:\n"
        "    - Join key methodology (UTM vs phone vs timestamp)\n"
        "    - Handling walk-in traffic attribution\n"
        "    - Confidence thresholds for fuzzy matches\n"
        "  \n"
        "  CRM data will appear in the Raw Data tab but will NOT\n"
        "  feed into CPS or PVR calculations yet.\n"
        + "=" * 70 + "\n"
    )
    rows = _read_file(filepath)
    # Basic normalization without cross-matching
    normalized = []
    for row in rows:
        clean = {}
        for k, v in row.items():
            clean[k.strip().lower().replace(" ", "_")] = str(v).strip() if v else ""
        clean["source_platform"] = "crm"
        clean["_crm_unmatched"] = True
        normalized.append(clean)

    print(f"[Ingest] CRM (raw, unmatched): {len(normalized)} rows from {filepath}")
    return normalized


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

INGEST_MAP = {
    "googleads": ingest_googleads,
    "metaads": ingest_metaads,
    "microsoftads": ingest_microsoftads,
    "ga4": ingest_ga4,
    "thirdparty": ingest_thirdparty,
    "oem": ingest_oem,
    "crm": ingest_crm,
}


def ingest(source: str, filepath: str) -> list[dict]:
    """Dispatch to the appropriate ingest function."""
    fn = INGEST_MAP.get(source.lower())
    if not fn:
        raise ValueError(
            f"Unknown source type '{source}'. "
            f"Supported: {', '.join(INGEST_MAP.keys())}"
        )
    return fn(filepath)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 ingest.py <source> <filepath>")
        print(f"Sources: {', '.join(INGEST_MAP.keys())}")
        sys.exit(1)

    source_type = sys.argv[1]
    file_path = sys.argv[2]
    data = ingest(source_type, file_path)
    print(f"\nIngested {len(data)} rows. Sample fields: {list(data[0].keys())[:10]}")
