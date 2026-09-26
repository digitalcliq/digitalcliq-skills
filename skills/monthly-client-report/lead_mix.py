#!/usr/bin/env python3
"""
Lead Mix by Category: the executive lead-source rollup for the monthly report.

Reuses score-leads' cross-CRM ingest (Tekion / VinSolutions / Momentum / Focus /
CSV / PDF) and its NADA source-type classifier, so the categories match the
benchmark logic. Buckets every source into: Walk-in/Showroom, Phone, Internet
(1st-party), Website Chat, 3rd-party Marketplace, OEM/Factory, Conquest/Data-list,
Owned/Repeat, and Unknown/Unattributed. Emits JSON the report generator drops in
near the top.

Where score-leads lives:
    SCORE_LEADS_DIR env var if set, otherwise the sibling folder "score-leads"
    next to this skill's folder (skills/monthly-client-report -> skills/score-leads,
    same layout in the runtime and in the repo). Symlinks are resolved first.

Usage:
    python3 lead_mix.py <crm_file.csv|xlsx|xls|pdf>

Prints one JSON object to stdout. On success exits 0. On any failure (bad usage,
missing file, score-leads not importable, unreadable CRM export, no leads parsed)
it still prints {"available": false, "note": ...} to stdout, prints the reason to
stderr, and exits non-zero. A CRM file that was attached but produced no Lead Mix
is a failure to fix, not a section to omit.

Output fields (the generator renders categories[], total_leads, total_sold,
phone_tracked; the rest are for the main loop to review before render):
    total_leads, total_sold   category totals after summary rows are removed
    total_leads_raw           leads summed over every parsed row, summary rows included
    summary_rows_skipped      Total / Totals / Grand Total / Average rows dropped
    totals_check              PASSED or MISMATCH against the export's own Totals row
    categories[]              Category, Leads, % Mix, Sold, Close %
                              (% Mix uses largest-remainder rounding so it sums to 100;
                               Close % reads "Low vol" under MIN_BENCHMARK_LEADS leads)
    low_volume_categories     category labels shown as "Low vol"
    defaulted_sources         sources no pattern matched, so they fell into Internet
                              by default. Review them; never render them as a row.
    phone_tracked             true when any source landed in the Phone bucket
    crm_format, basis         which ingest adapter read the file and its lead basis
"""
import json
import os
import re
import sys

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


def _score_leads_dir():
    """SCORE_LEADS_DIR if set, else the sibling score-leads folder of this skill.

    realpath first so a symlinked skill folder still finds its real sibling; the
    abspath sibling is the fallback for a layout that symlinks each skill folder
    separately."""
    env = os.environ.get("SCORE_LEADS_DIR")
    if env:
        return env
    real = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
                        "score-leads")
    if os.path.isfile(os.path.join(real, "ingest.py")):
        return real
    near = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "score-leads")
    if os.path.isfile(os.path.join(near, "ingest.py")):
        return near
    return real


SL_DIR = _score_leads_dir()

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

# Rows a CRM export adds as a footer. Counting them doubles every lead.
SUMMARY_ROW_NAMES = {"total", "totals", "grand total", "grand totals", "average",
                     "averages", "subtotal", "sub total", "sub-total"}

# Lead basis by ingest format, so the main loop can reconcile against the
# score-leads section on the same basis.
BASIS = {
    "vinsolutions": "Good leads by category",
    "tekion": "Good leads by category",
    "focuscrm": "Prospects by category",
    "momentum": "Leads by category",
    "momentum_lsr": "Leads created by category",
    "native": "Leads by category (as exported)",
    "pdf": "Leads by category (as exported)",
}

# Display-only overrides, checked before score-leads' benchmark classifier.
# They change which Lead Mix row a source lands in, never the NADA benchmark
# category score-leads uses for close-rate grading.
_UNKNOWN_TOKENS = ("ungrouped", "<ungroup", "misc", " ncc", "ncc ", " aec",
                   "unknown", "not specified", "unspecified", "no source")
_UNKNOWN_EXACT = re.compile(r"\(?\s*(none|n/a|na|null|blank|-+)\s*\)?")
_PHONE_TOKENS = ("phone up", "phone-up", "phoneup")
_WALK_IN_TOKENS = ("drive-by", "driveby", "drove-by")


def _norm(source):
    return re.sub(r"\s+", " ", str(source or "").strip().lower())


def is_summary_row(source):
    """True for footer rows like 'Totals' or 'Grand Total:' that repeat the sum."""
    return _norm(source).rstrip(":").strip() in SUMMARY_ROW_NAMES


def classify(source, SL):
    """Return (lead-mix category, defaulted) for one source name.

    defaulted is True when no pattern matched and score-leads' website catch-all
    took it, so the main loop can review what landed in Internet by default."""
    low = _norm(source)
    # Flag unattributed/junk buckets BEFORE the website default swallows them.
    if any(t in low for t in _UNKNOWN_TOKENS) or _UNKNOWN_EXACT.fullmatch(low):
        return "unknown", False
    unattributed = getattr(SL, "is_unattributed_source", None)
    if unattributed and unattributed(source):
        return "unknown", False
    # Phone-ups are calls; score-leads benchmarks them at the walk-in rate, but
    # the mix table must show them as Phone or it claims calls are not tracked.
    if any(t in low for t in _PHONE_TOKENS):
        return "phone", False
    if any(t in low for t in _WALK_IN_TOKENS):
        return "walk_in", False
    cat = SL.classify_benchmark_category(source)
    if cat not in LABELS:
        cat = "website"
    defaulted = False
    if cat == "website":
        patterns = dict(getattr(SL, "BENCHMARK_CATEGORY_PATTERNS", []) or [])
        if "website" in patterns:
            defaulted = not any(p in low for p in patterns["website"])
    return cat, defaulted


def largest_remainder(counts):
    """Whole-number percentages of counts that add to exactly 100.

    Floors every share, then hands the leftover points to the largest remainders
    (ties go to the larger count, then to the earlier position)."""
    total = sum(counts)
    if total <= 0:
        return [0 for _ in counts]
    exact = [c * 100 / total for c in counts]
    floors = [int(x) for x in exact]
    left = 100 - sum(floors)
    order = sorted(range(len(counts)),
                   key=lambda i: (-(exact[i] - floors[i]), -counts[i], i))
    for i in order[:left]:
        floors[i] += 1
    return floors


def build_mix(rows, SL, fmt=None):
    """Roll ingest rows into the Lead Mix payload. Returns (payload, warnings)."""
    min_leads = int(getattr(SL, "MIN_BENCHMARK_LEADS", 10) or 10)
    warnings = []
    cats = {}
    skipped = []
    defaulted = {}
    raw_leads = 0
    for r in rows:
        src = str(r.get("source", "")).strip()
        if not src:
            continue
        leads = int(r.get("leads", 0) or 0)
        sales = int(r.get("sales", 0) or 0)
        raw_leads += leads
        if is_summary_row(src):
            skipped.append({"source": src, "leads": leads, "sold": sales})
            continue
        if leads == 0 and sales == 0:
            continue
        cat, was_default = classify(src, SL)
        d = cats.setdefault(cat, {"leads": 0, "sold": 0})
        d["leads"] += leads
        d["sold"] += sales
        if was_default:
            dd = defaulted.setdefault(src, {"source": src, "leads": 0, "sold": 0})
            dd["leads"] += leads
            dd["sold"] += sales

    tot_l = sum(c["leads"] for c in cats.values())
    tot_s = sum(c["sold"] for c in cats.values())
    if tot_l == 0:
        return None, warnings

    # Reconcile against the export's own Totals row (warn only, never block).
    totals_check = None
    tot_rows = [s for s in skipped if not _norm(s["source"]).startswith("average")]
    if tot_rows:
        grand = [s for s in tot_rows if "grand" in _norm(s["source"])]
        ref = (grand or tot_rows)[-1]
        if ref["leads"] == tot_l and ref["sold"] == tot_s:
            totals_check = f"PASSED leads={tot_l} sold={tot_s}"
        else:
            totals_check = (f"MISMATCH parsed leads={tot_l} sold={tot_s}, "
                            f"'{ref['source']}' row says leads={ref['leads']} sold={ref['sold']}")
            warnings.append("WARN lead_mix: category totals do not match the export's "
                            f"Totals row ({totals_check}). Check the file before render.")

    present = [k for k in ORDER if k in cats]
    pcts = largest_remainder([cats[k]["leads"] for k in present])
    table = []
    low_vol = []
    for k, pct in zip(present, pcts):
        c = cats[k]
        if c["leads"] < min_leads:
            close = "Low vol"
            low_vol.append(LABELS[k])
        elif c["sold"] > c["leads"]:
            # Unattributed DMS sales can outnumber leads; that is not a rate.
            close = "n/a"
            warnings.append(f"WARN lead_mix: {LABELS[k]} has {c['sold']} sold on "
                            f"{c['leads']} leads; Close % shown as n/a.")
        else:
            close = f"{c['sold'] / c['leads'] * 100:.1f}%"
        table.append({
            "Category": LABELS[k],
            "Leads": str(c["leads"]),
            "% Mix": f"{pct}%",
            "Sold": str(c["sold"]),
            "Close %": close,
        })

    dsrc = sorted(defaulted.values(), key=lambda x: (-x["leads"], x["source"].lower()))
    if dsrc:
        names = ", ".join(f"{d['source']} ({d['leads']})" for d in dsrc)
        warnings.append("NOTE lead_mix: no category pattern matched these sources, so "
                        f"they count as Internet (1st-party): {names}. Review before render.")

    out = {
        "available": True,
        "basis": BASIS.get(fmt, "Leads by category"),
        "crm_format": fmt,
        "total_leads": tot_l,
        "total_sold": tot_s,
        "total_leads_raw": raw_leads,
        "summary_rows_skipped": skipped,
        "totals_check": totals_check,
        "categories": table,
        "low_volume_categories": low_vol,
        "min_sample_leads": min_leads,
        "defaulted_sources": dsrc,
        "phone_tracked": "phone" in cats,
    }
    return out, warnings


def _fail(note, code=EXIT_FAIL):
    """Print the unavailable payload to stdout, the reason to stderr, and exit."""
    print(json.dumps({"available": False, "note": note}))
    print(f"ERROR lead_mix: {note}", file=sys.stderr)
    sys.exit(code)


def _load_score_leads():
    """Import score-leads' ingest() and score_leads module from SL_DIR, or exit 1."""
    if not os.path.isfile(os.path.join(SL_DIR, "ingest.py")):
        how = ("SCORE_LEADS_DIR points there" if os.environ.get("SCORE_LEADS_DIR")
               else "expected the sibling score-leads folder next to this skill")
        _fail(f"score-leads not found at {SL_DIR} ({how}). "
              "Set SCORE_LEADS_DIR to the score-leads skill folder and re-run.")
    if SL_DIR not in sys.path:
        sys.path.insert(0, SL_DIR)
    try:
        from ingest import ingest
        import score_leads as SL
    except (Exception, SystemExit) as e:
        _fail(f"score-leads import failed from {SL_DIR}: {type(e).__name__}: {e}")
    return ingest, SL


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        _fail("usage: lead_mix.py <crm_file>", EXIT_USAGE)
    path = argv[0]
    if not os.path.exists(path):
        _fail(f"file not found: {path}")
    ingest, SL = _load_score_leads()
    try:
        rows, meta = ingest(path, rollup=False)
    except Exception as e:
        _fail(f"ingest failed for {os.path.basename(path)}: {e}")

    out, warnings = build_mix(rows, SL, (meta or {}).get("format"))
    for w in warnings:
        print(w, file=sys.stderr)
    if out is None:
        _fail(f"no leads parsed from {os.path.basename(path)}")
    print(json.dumps(out))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
