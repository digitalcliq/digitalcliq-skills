#!/usr/bin/env python3
"""
Lead Mix by Category — the executive lead-source rollup for the monthly report.

Reuses score-leads' cross-CRM ingest (Tekion / VinSolutions / Momentum / CSV / PDF)
and its NADA source-type classifier, so the categories match the benchmark logic
exactly. Buckets every source into: Walk-in/Showroom, Phone, Internet (1st-party),
Website Chat, 3rd-party Marketplace, OEM/Factory, Conquest/Data-list, Owned/Repeat,
and Unknown/Unattributed. Emits JSON the report generator drops in near the top.

Usage:
    python3 lead_mix.py <crm_file.csv|xlsx|pdf>
Prints one JSON object to stdout. On any failure prints {"available": false, ...}.
"""
import json
import os
import sys

SL_DIR = "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/score-leads"
sys.path.insert(0, SL_DIR)

# Display labels + the order they appear in the report table.
LABELS = {
    "walk_in":      "Walk-in / Showroom Ups",
    "phone":        "Phone / Call-in",
    "website":      "Internet (1st-party)",
    "chat":         "Website Chat",
    "third_party":  "3rd-party Marketplace",
    "oem":          "OEM / Factory",
    "data_list":    "Conquest / Data-list",
    "owned_equity": "Owned / Repeat & Referral",
    "unknown":      "Unknown / Unattributed",
}
ORDER = ["third_party", "website", "data_list", "oem", "walk_in", "phone",
         "chat", "owned_equity", "unknown"]


def _classify(source, SL):
    low = source.lower()
    # Flag unattributed/junk buckets BEFORE the website default swallows them.
    if any(t in low for t in ("ungrouped", "<ungroup", "misc", " ncc", "ncc ",
                              " aec", "unknown")):
        return "unknown"
    return SL.classify_benchmark_category(source)


def main():
    if len(sys.argv) != 2:
        print(json.dumps({"available": False, "note": "usage: lead_mix.py <file>"}))
        return
    path = sys.argv[1]
    if not os.path.exists(path):
        print(json.dumps({"available": False, "note": f"file not found: {path}"}))
        return
    try:
        from ingest import ingest
        import score_leads as SL
        rows, meta = ingest(path, rollup=False)
    except Exception as e:
        print(json.dumps({"available": False, "note": f"ingest failed: {e}"}))
        return

    cats = {}
    for r in rows:
        src = str(r.get("source", "")).strip()
        if not src:
            continue
        leads = int(r.get("leads", 0) or 0)
        sales = int(r.get("sales", 0) or 0)
        if leads == 0 and sales == 0:
            continue
        cat = _classify(src, SL)
        d = cats.setdefault(cat, {"leads": 0, "sold": 0})
        d["leads"] += leads
        d["sold"] += sales

    tot_l = sum(c["leads"] for c in cats.values())
    tot_s = sum(c["sold"] for c in cats.values())
    if tot_l == 0:
        print(json.dumps({"available": False, "note": "no leads parsed"}))
        return

    table = []
    for k in ORDER:
        if k not in cats:
            continue
        c = cats[k]
        pct = c["leads"] / tot_l * 100
        cr = c["sold"] / c["leads"] * 100 if c["leads"] else 0
        table.append({
            "Category": LABELS[k],
            "Leads": str(c["leads"]),
            "% Mix": f"{pct:.0f}%",
            "Sold": str(c["sold"]),
            "Close %": f"{cr:.1f}%",
        })

    out = {
        "available": True,
        "basis": "Good (deduped) leads by category",
        "total_leads": tot_l,
        "total_sold": tot_s,
        "categories": table,
        "phone_tracked": "phone" in cats,
    }
    print(json.dumps(out))


if __name__ == "__main__":
    main()
