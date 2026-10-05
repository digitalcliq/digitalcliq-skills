#!/usr/bin/env python3
"""DigitalCLIQ Inventory Pulse: snapshot store + diff + analytics engine.

Input:  one extraction JSON (this run's crawl, schema in SKILL.md).
State:  Projects/{CODE}/inventory-pulse-state/  (date-keyed snapshots + registry.json).
Output: analysis JSON that build_workbook.py renders 1:1. All derivations happen
here so the workbook builder stays dumb.

Longitudinal rules:
- Run type: day of month <= anchor_day_max (12) = "anchor", else "pulse".
- Anchor runs compare to the PRIOR month's anchor; pulse runs compare to THIS
  month's anchor; fallback = latest earlier snapshot; none = baseline run.
- A VIN in the registry that is missing from this run is marked delisted ONLY if its
  vehicle page was actually re-checked this run AND its dealer's crawl status is "ok"
  or "partial". Failed crawls never fake delistings. ("ok" alone silently dropped 13
  confirmed delistings whose dealer was partial only on the OFFERS half, QA 2026-09-20.)
- DOM = displayed DOM if the site shows one, else days since our first_seen. If
  first_seen equals the dealer's first-ever crawl date, DOM is a floor (">=N").
- Effective monthly lease cost = (DAS + pmt * (term - 1)) / term. Unknown DAS
  falls back to pmt and flags DAS_UNKNOWN. Rankings use effective cost.
- Never fabricate: unknown numbers stay 0 and are rendered as "?".
"""
import argparse, json, os, re, shutil
from datetime import date, datetime

MOVEMENT_WINDOW_DAYS = 120
ANCHOR_DAY_MAX = 12


def d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def days_between(a, b):
    return abs((d(b) - d(a)).days)


def eff_monthly(pmt, das, term):
    if pmt and das and term:
        return int(round((das + pmt * (term - 1)) / term))
    return pmt or 0


# Drivetrain and body-style words drift in and out of a site's trim string between
# runs ("SV" one run, "SV FWD" the next) for the SAME offer at the SAME payment.
# Keying on the raw trim made all five Nissan of Costa Mesa leases read as pulled
# AND newly launched in one run (QA 2026-09-06). Cab styles are NOT stripped: on a
# truck they identify a genuinely different configuration.
_TRIM_NOISE = re.compile(
    r"\b(fwd|awd|rwd|2wd|4wd|4x4|4x2|sedan|hatchback|wagon|suv|"
    r"sport utility vehicles?|sport utility)\b", re.I)


_MILES_TOTAL = re.compile(r"over\s+([\d,]{4,})\s*miles", re.I)
_MILES_YEAR = re.compile(r"([\d,]{4,})\s*miles?\s*(?:per|/|a)\s*(?:year|yr)", re.I)


def derive_miles_yr(o):
    """Recover the annual mileage allowance from the disclaimer when the extractor
    only found a TERM TOTAL.

    Dealers write "$0.25/mile over 32,500 miles" on a 39-month lease, which is
    10,000 mi/yr. Leaving it blank made the report claim rivals "publish no mileage
    allowance" while the run's own capture disproved it, and it flattered the client
    whose own lease was capped 2,500 mi/yr lower (QA 2026-09-06).
    """
    term = o.get("term_mo") or 0
    if o.get("miles_yr"):
        # A stored allowance far above any plausible annual cap is a TERM TOTAL that
        # an earlier run filed in the annual field (Long Beach BMW: 32,500 over 39
        # months = 10,000 mi/yr). Publishing 32,500 mi/yr would be absurd on its face.
        if o["miles_yr"] > 20000 and term:
            return int(round(o["miles_yr"] / (term / 12.0) / 250.0) * 250), True
        return o["miles_yr"], False
    text = f"{o.get('disclaimer_text','')} {o.get('offer_text','')}"
    m = _MILES_YEAR.search(text)
    if m:
        return int(m.group(1).replace(",", "")), True
    m = _MILES_TOTAL.search(text)
    if m and term:
        total = int(m.group(1).replace(",", ""))
        return int(round(total / (term / 12.0) / 250.0) * 250), True
    return 0, False


def _re_stk(flags):
    m = re.search(r"Stk\.?\s*#?\s*([A-Z0-9-]+)", str(flags or ""), re.I)
    return f"Stk. {m.group(1)} " if m else ""


def join_names(names):
    names = list(names)
    if len(names) <= 1:
        return names[0] if names else ""
    return ", ".join(names[:-1]) + " and " + names[-1]


def depluralize(t):
    """Render '4 offer(s)' as '4 offers' / '1 offer' at the source, so the workbook
    and the QA manifest quote the same string."""
    def fix(m):
        n, mid, word = m.group(1), m.group(2), m.group(3)
        try:
            one = abs(float(n.replace(",", ""))) == 1
        except ValueError:
            one = False
        return f"{n}{mid}{word}" if one else f"{n}{mid}{word}s"
    t = re.sub(r"(\b[\d,]+)(\s+(?:[A-Za-z][\w/-]*\s+){0,2})([A-Za-z][\w/-]*?)\(s\)",
               fix, str(t or ""))
    return re.sub(r"([A-Za-z][\w/-]*?)\(s\)", r"\1s", t)


def norm_trim(t):
    t = _TRIM_NOISE.sub(" ", str(t or "")).lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)      # R/T == RT, 4-Door == 4 door
    return re.sub(r"\s+", " ", t).strip()


_ZERO_APR = re.compile(r"\b0(?:\.0+)?\s*%\s*(?:apr|financing|interest)?", re.I)


def apr_published_zero(o):
    """True when apr==0 means a genuine 0% offer rather than 'unknown'."""
    if o.get("apr"):
        return False
    blob = " ".join(str(o.get(f, "")) for f in
                    ("conditions", "offer_text", "parse_note", "disclaimer_text"))
    return bool(_ZERO_APR.search(blob))


_UNIVERSAL = re.compile(r"universal|all buyers|not a conditional program|no qualification", re.I)


def effective_payment_type(o):
    """A rebate the store applies to every unit is NOT a conditional payment.
    Typing it conditional while the row's own flag text says "universal ... not a
    conditional program" contradicted itself on screen and inflated the headline
    conditional count (QA gate 2026-09-20)."""
    declared = (o.get("payment_type") or "").lower()
    if declared != "conditional":
        return declared or "clean"
    rebates = [str(x) for x in (o.get("rebates_included") or [])]
    if rebates:
        # Every listed rebate must be marked universal. One qualification-gated
        # rebate in the stack is enough to keep the payment conditional.
        return "clean" if all(_UNIVERSAL.search(x) for x in rebates) else "conditional"
    blob = " ".join(str(o.get(f, "")) for f in ("flags", "parse_note", "disclaimer_text"))
    return "clean" if _UNIVERSAL.search(blob) else "conditional"


def offer_key(o, kind):
    return f"{kind}|{o['dealer']}|{o.get('model','')}|{norm_trim(o.get('trim',''))}|{o.get('yr',0)}"


def offer_figkey(o, kind):
    """Trim-free identity: same store, model, year, and the SAME advertised figures.

    Dealer sites relabel trims between runs without changing the deal ('' -> 'SV',
    'SL' -> 'SR', 'SV' -> 'SV FWD'). Keyed on trim alone those read as one offer
    pulled and a different one launched, which told a GM his own live offer had
    been taken down (QA 2026-09-06). Identical figures on the same model/year are
    the same offer no matter what the trim string says.
    """
    figs = (f"{o.get('pmt',0)}|{o.get('apr',0)}|{o.get('term_mo',0)}|{o.get('das',0)}")
    return f"{kind}|{o['dealer']}|{o.get('model','')}|{o.get('yr',0)}|{figs}"


def offer_figkey_loose(o, kind):
    """Loosest identity: same store/model/year and the same headline payment and term.

    A run can mis-split down payment vs due-at-signing (Nissan of Orange 2026-09-04
    recorded das=7350/down=0 for what this run reads as down=7350/das=9100). That
    made an unchanged $139/24mo lease look pulled AND newly launched. Payment plus
    term is enough to recognise it; the DAS difference is a capture correction, not
    a new deal.
    """
    return (f"{kind}|{o['dealer']}|{o.get('model','')}|{o.get('yr',0)}|"
            f"{o.get('pmt',0)}|{o.get('apr',0)}|{o.get('term_mo',0)}")


def load_json(p, default):
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return default


def pick_compare_run(runs, run_date):
    """runs: list of {date, type} sorted asc, excluding today. See module doc."""
    today = d(run_date)
    earlier = [r for r in runs if d(r["date"]) < today]
    if not earlier:
        return None
    this_anchor = [r for r in earlier if d(r["date"]).month == today.month
                   and d(r["date"]).year == today.year and r["type"] == "anchor"]
    if today.day <= ANCHOR_DAY_MAX:
        prev = [r for r in earlier if (d(r["date"]).year, d(r["date"]).month) < (today.year, today.month)]
        prev_anchor = [r for r in prev if r["type"] == "anchor"]
        # Month-over-month is the intent, but only a prior-month ANCHOR earns the
        # right to beat a more recent run. Without one, use the latest earlier run:
        # comparing to something staler than what we already have manufactures
        # false "new"/"first capture" labels and hides pulled offers.
        pool = prev_anchor or earlier
    else:
        pool = this_anchor or earlier
    return pool[-1]


def delta_row(cur, prev_val, unit="$"):
    if prev_val is None:
        return "new", 0, "new this period"
    if not cur or not prev_val:
        return "same", 0, "no change"
    diff = cur - prev_val
    if abs(diff) < (1 if unit == "$" else 0.01):
        return "same", 0, "no change"
    arrow = "▲" if diff > 0 else "▼"
    if unit == "$":
        return ("up" if diff > 0 else "down"), diff, f"{arrow} {'+' if diff>0 else '-'}${abs(diff):,.0f}/mo"
    return ("up" if diff > 0 else "down"), diff, f"{arrow} {'+' if diff>0 else '-'}{abs(diff):.2f} pts"


def rank_fills(groups):
    """groups: dict key -> list of (idx, value). Returns idx -> (rank, group_size)."""
    out = {}
    for _, members in groups.items():
        valid = sorted([m for m in members if m[1]], key=lambda x: x[1])
        for rank, (idx, _) in enumerate(valid, 1):
            out[idx] = (rank, len(valid))
        for idx, v in members:
            if not v:
                out[idx] = (0, len(valid))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--recheck-dir", default="",
                    help="run DATA dir holding {dealer-slug}/recheck.txt. Inventory is a "
                         "SAMPLE, so only VINs whose VDP was actually re-fetched this run "
                         "are eligible to be marked delisted.")
    args = ap.parse_args()

    ex = load_json(args.extract, None)
    if not ex:
        raise SystemExit(f"extract file missing/empty: {args.extract}")
    meta_in = ex["meta"]
    run_date = meta_in["run_date"]
    code = meta_in["client_code"]
    run_type = "anchor" if d(run_date).day <= ANCHOR_DAY_MAX else "pulse"

    os.makedirs(os.path.join(args.state, "snapshots"), exist_ok=True)
    reg_path = os.path.join(args.state, "registry.json")
    reg = load_json(reg_path, {"created": run_date, "dealer_first_crawl": {},
                               "offer_registry": {}, "vin_registry": {}, "runs": []})
    baseline = len(reg["runs"]) == 0

    # One-time key migration: offer_key now normalizes the trim, so entries written
    # under raw-trim keys would look brand new and stamp First Seen with today's
    # date on offers that have been running for weeks (QA 2026-09-06).
    if not reg.get("offer_key_schema"):
        migrated = {}
        for k, v in reg.get("offer_registry", {}).items():
            parts = k.split("|")
            if len(parts) == 5:
                parts[3] = norm_trim(parts[3])
                nk = "|".join(parts)
            else:
                nk = k
            if nk in migrated:   # two raw trims collapsed to one: keep the older
                if v.get("first_seen", "9999") < migrated[nk].get("first_seen", "9999"):
                    migrated[nk]["first_seen"] = v["first_seen"]
                migrated[nk].setdefault("history", []).extend(v.get("history", []))
            else:
                migrated[nk] = v
        for v in migrated.values():
            seen_h, hist = set(), []
            for h in sorted(v.get("history", []), key=lambda x: x.get("date", "")):
                if h.get("date") in seen_h:
                    continue
                seen_h.add(h.get("date")); hist.append(h)
            v["history"] = hist
        reg["offer_registry"] = migrated
        reg["offer_key_schema"] = "norm_trim_v1"
    dealer_status = {dl["name"]: dl.get("status", "failed") for dl in ex["dealers"]}
    client_name = ex["meta"].get("client_name") or next(
        (dl["name"] for dl in ex["dealers"] if dl.get("role") == "client"), "")

    for dl in ex["dealers"]:
        reg["dealer_first_crawl"].setdefault(dl["name"], run_date)

    # ---- rechecked URL set -------------------------------------------------
    # Delist detection is only valid for VINs whose VDP was actually fetched this
    # run. Inventory is sampled and the recheck list is capped, so "VIN absent from
    # this run" does NOT mean the vehicle is gone (bug found by the QA gate
    # 2026-09-06: 95 of Sterling BMW's 138 registry VINs were falsely reported
    # delisted from a 43-unit sample). No recheck list for a dealer => nothing of
    # that dealer's is delist-eligible.
    rechecked_urls = set()
    if args.recheck_dir and os.path.isdir(args.recheck_dir):
        for slug in os.listdir(args.recheck_dir):
            rc = os.path.join(args.recheck_dir, slug, "recheck.txt")
            if not os.path.exists(rc):
                continue
            for line in open(rc):
                u = line.strip().rstrip("/").lower()
                if u:
                    rechecked_urls.add(u)

    # ---- compare run selection --------------------------------------------
    cmp_run = pick_compare_run(reg["runs"], run_date)
    cmp_offers = {}
    # A compare run that captured ZERO offers cannot make this run's offers "new":
    # there was nothing to be new against (QA gate 2026-09-06 saw 18 offers all
    # labelled "new this period" against a snapshot that held no offers at all).
    cmp_counts = {"lease": 0, "fin": 0}
    cmp_by_fig = {}
    cmp_by_loose = {}
    if cmp_run:
        snap = load_json(os.path.join(args.state, "snapshots", f"extract_{cmp_run['date']}.json"), {})
        for kind, lst in (("lease", snap.get("lease_offers", [])), ("fin", snap.get("finance_offers", []))):
            cmp_counts[kind] = len(lst)
            for o in lst:
                cmp_offers[offer_key(o, kind)] = o
                cmp_by_fig.setdefault(offer_figkey(o, kind), o)
                cmp_by_loose.setdefault(offer_figkey_loose(o, kind), o)

    # ---- VIN registry update ----------------------------------------------
    seen_vins = set()
    for v in ex.get("inventory", []):
        vin = v.get("vin", "")
        if not vin:
            continue
        seen_vins.add(vin)
        entry = reg["vin_registry"].setdefault(vin, {"first_seen": run_date, "delisted_on": None})
        entry.update({"last_seen": run_date, "dealer": v["dealer"], "yr": v.get("yr", 0),
                      "make": v.get("make", ""), "model": v.get("model", ""),
                      "trim": v.get("trim", ""), "version": v.get("version", ""),
                      "msrp": v.get("msrp", 0), "price": v.get("price", 0),
                      "dom_displayed": v.get("dom_displayed", 0),
                      "vdp_url": v.get("vdp_url", "") or entry.get("vdp_url", "")})
        entry["delisted_on"] = None  # re-listed VINs come back alive
    delist_eligible = 0
    for vin, entry in reg["vin_registry"].items():
        if vin in seen_vins or entry.get("delisted_on"):
            continue
        vurl = (entry.get("vdp_url", "") or "").rstrip("/").lower()
        # Only a VIN we actually re-fetched this run can be called delisted.
        if not vurl or vurl not in rechecked_urls:
            continue
        delist_eligible += 1
        if (dealer_status.get(entry.get("dealer", ""), "failed") in ("ok", "partial")
                and entry.get("last_seen", run_date) != run_date):
            entry["delisted_on"] = run_date
            entry["dom_at_delist"] = entry.get("dom_displayed") or days_between(entry["first_seen"], run_date)
            # No site-published DOM means we only know how long WE watched it.
            entry["dom_inferred"] = 0 if entry.get("dom_displayed") else 1

    # ---- offer registry + lease rows --------------------------------------
    def dom_of(entry):
        disp = entry.get("dom_displayed", 0)
        if disp:
            return disp, ""
        dlr = entry.get("dealer", "")
        floor = reg["dealer_first_crawl"].get(dlr, run_date) == entry["first_seen"] and not baseline
        n = days_between(entry["first_seen"], run_date)
        return n, (">=" if floor or baseline else "")

    # A prior offer matched EXACTLY (same trim) by one current offer cannot also be
    # the figure-fallback "prior" of a different trim. Crevier BMW 2026-10-05: the
    # new 330i xDrive at $479 borrowed last run's 330i Sedan $479 and printed
    # "no change" while the 330i itself had moved to $459 (QA gate).
    _claimed = {offer_key(o, kk) for kk, src in (("lease", "lease_offers"), ("fin", "finance_offers"))
                for o in ex.get(src, []) if offer_key(o, kk) in cmp_offers}

    def _fallback(o, kk):
        if offer_key(o, kk) in cmp_offers:
            return cmp_offers[offer_key(o, kk)]
        for cand in (cmp_by_fig.get(offer_figkey(o, kk)), cmp_by_loose.get(offer_figkey_loose(o, kk))):
            if cand and offer_key(cand, kk) not in _claimed:
                return cand
        return None

    lease_rows, groups = [], {}
    for i, o in enumerate(ex.get("lease_offers", [])):
        k = offer_key(o, "lease")
        rentry = reg["offer_registry"].setdefault(k, {"first_seen": run_date, "history": []})
        # It was live on the compare run, so it cannot have been first seen today.
        if rentry["first_seen"] == run_date and cmp_run and _fallback(o, "lease"):
            rentry["first_seen"] = cmp_run["date"]
        rentry["last_seen"] = run_date
        rentry["history"] = [h for h in rentry["history"] if h.get("date") != run_date]
        rentry["history"].append({"date": run_date, "pmt": o.get("pmt", 0),
                                  "das": o.get("das", 0), "term_mo": o.get("term_mo", 0)})
        prev = _fallback(o, "lease")
        dtype, damt, dlabel = delta_row(o.get("pmt", 0), prev.get("pmt", 0) if prev else None)
        if not cmp_run or not cmp_counts["lease"]:
            dlabel = "first capture"  # nothing existed to be "new" against
        elif not prev and cmp_run and rentry["first_seen"] < cmp_run["date"]:
            # Seen before the compare run, absent on it, back now: "new" next to an
            # older First Seen date contradicted itself (QA gate 2026-10-05).
            dlabel = f"returned (not published {cmp_run['date']})"
        # If this offer is flagged as a banner/fine-print mismatch and the prior run
        # recorded the BANNER number, the difference is a basis correction on our side,
        # not the dealer moving its price (QA 2026-09-06).
        if (prev and dtype in ("up", "down")
                and "mismatch" in str(o.get("flags", "")).lower()
                and str(prev.get("pmt", "")) in str(o.get("parse_note", ""))):
            dtype, damt = "same", 0
            dlabel = "no change (basis, see Flags)"
        if dtype in ("up", "down") and abs(damt) < 5:
            dtype, damt, dlabel = "same", 0, "no change (rounding)"
        # A payment move across a different term, or "no change" while due at
        # signing moved, is not like-for-like (QA gate 2026-10-05, NOI).
        if prev:
            _nt = []
            if prev.get("term_mo") and o.get("term_mo") and prev["term_mo"] != o["term_mo"]:
                _nt.append(f"term was {prev['term_mo']} mo")
            _pdas = prev.get("das") or 0
            if "basis" in str(o.get("flags", "")).lower():
                # This run records CASH due; the prior run recorded a rebate-inclusive
                # total. Compare like for like using the prior run's own cash figure.
                _m = re.search(r"\$([\d,]+)\s+(?:cash\s+)?due at (?:lease\s+)?signing",
                               str(prev.get("offer_text", "")) + " " + str(prev.get("disclaimer_text", "")), re.I)
                _pdas = int(_m.group(1).replace(",", "")) if _m else 0
            if _pdas and o.get("das") and abs(_pdas - o["das"]) >= 100:
                _dd = o["das"] - _pdas
                _nt.append(f"due at signing {'+' if _dd > 0 else '-'}${abs(_dd):,}")
            _pmi = derive_miles_yr(prev)[0]
            if _pmi and o.get("miles_yr") and _pmi != o["miles_yr"]:
                _nt.append(f"mileage was {_pmi:,}/yr")
            if _nt:
                dlabel += " (" + "; ".join(_nt) + ")"
        else:
            _my_prev = next((c for c in cmp_offers.values()
                             if c.get("dealer") == o.get("dealer") and c.get("model") == o.get("model")
                             and norm_trim(c.get("trim")) == norm_trim(o.get("trim"))
                             and c.get("yr", 0) and o.get("yr", 0) and c.get("yr") != o.get("yr")
                             and c.get("pmt")), None)
            if _my_prev and cmp_run and cmp_counts["lease"]:
                dlabel = (f"new model year (replaces {_my_prev.get('yr')} offer at "
                          f"${_my_prev.get('pmt', 0):,}/{_my_prev.get('term_mo', 0)} mo)")
        eff = eff_monthly(o.get("pmt", 0), o.get("das", 0), o.get("term_mo", 0))
        # Honesty layer, enforced here rather than trusted from the crawl: if the
        # payment names rebates, it is conditional whatever the fragment claimed.
        _my, _my_derived = derive_miles_yr(o)
        if not _my and prev:
            _my, _my_derived = derive_miles_yr(prev)
            if not _my and prev.get("miles_yr"):
                _pm, _term = prev["miles_yr"], (prev.get("term_mo") or o.get("term_mo") or 0)
                # a stored value far above a plausible annual cap is a TERM TOTAL
                if _pm > 20000 and _term:
                    _my = int(round(_pm / (_term / 12.0) / 250.0) * 250)
                else:
                    _my = _pm
                _my_derived = True
        if _my and not o.get("miles_yr"):
            # Distinguish "read off THIS run's fine print" from "carried forward from
            # the prior run". Labelling a carried-forward figure as fine print asserted
            # a number that is nowhere on the page this run (QA gate 2026-09-20).
            _from_prev = not derive_miles_yr(o)[0]
            o = {**o, "miles_yr": _my,
                 "miles_yr_derived": 0 if _from_prev else 1,
                 "miles_yr_carried": 1 if _from_prev else 0}
        if o.get("rebates_included") and o.get("payment_type") != "conditional":
            o = {**o, "payment_type": "conditional"}
        # Re-read a "conditional" label against the row's own evidence: a rebate the
        # store applies to every unit is not a qualification hurdle.
        _eff = effective_payment_type(o)
        if _eff != (o.get("payment_type") or "").lower():
            o = {**o, "payment_type": _eff}
        # An offer with no monthly payment is not a lease; "clean" would read as an
        # endorsement of a payment that does not exist.
        if not o.get("pmt"):
            o = {**o, "payment_type": "not a lease"}
        flags = [f for f in str(o.get("flags", "")).split("|") if f]
        if o.get("pmt") and not o.get("das"):
            flags.append("DAS_UNKNOWN")
        if o.get("miles_yr") and o["miles_yr"] < 10000:
            flags.append("LOW_MILEAGE")
        for _rb in (o.get("rebates_included") or [])[:3]:
            flags.append("REQUIRES: " + str(_rb).replace("_", " ").strip())
        row = {**o, "is_client": 1 if o["dealer"] == client_name else 0,
               "first_seen": rentry["first_seen"], "eff_mo": eff,
               "delta_type": dtype, "delta_amt": damt, "delta_label": dlabel,
               "flags": "|".join(sorted(set(flags))),
               "prev": ({"pmt": prev.get("pmt", 0), "term_mo": prev.get("term_mo", 0),
                         "das": prev.get("das", 0), "msrp": prev.get("msrp", 0),
                         "offer_text": prev.get("offer_text", "")} if prev else None)}
        lease_rows.append(row)
        groups.setdefault((o.get("model", ""), norm_trim(o.get("trim", "")), o.get("yr", 0)), []).append((i, eff))
    ranks = rank_fills(groups)
    # group_size counts OFFERS in the model/trim/yr group; a single dealer can
    # publish several. Client-facing prose must never call that a dealer count,
    # so carry the distinct-dealer tally alongside it.
    group_dealers = {}
    for gk, members in groups.items():
        group_dealers[gk] = len({lease_rows[i].get("dealer", "") for i, _ in members})
    for i, row in enumerate(lease_rows):
        row["rank"], row["group_size"] = ranks.get(i, (0, 0))
        row["dealers_in_group"] = group_dealers.get(
            (row.get("model", ""), norm_trim(row.get("trim", "")), row.get("yr", 0)), 0)
    lease_rows.sort(key=lambda r: (r.get("model", ""), r.get("trim", ""), r.get("eff_mo") or 10**9))

    fin_rows, fgroups = [], {}
    for i, o in enumerate(ex.get("finance_offers", [])):
        k = offer_key(o, "fin")
        rentry = reg["offer_registry"].setdefault(k, {"first_seen": run_date, "history": []})
        if rentry["first_seen"] == run_date and cmp_run and _fallback(o, "fin"):
            rentry["first_seen"] = cmp_run["date"]
        rentry["last_seen"] = run_date
        rentry["history"] = [h for h in rentry["history"] if h.get("date") != run_date]
        rentry["history"].append({"date": run_date, "apr": o.get("apr", 0), "term_mo": o.get("term_mo", 0)})
        prev = _fallback(o, "fin")
        dtype, damt, dlabel = delta_row(o.get("apr", 0), prev.get("apr", 0) if prev else None, unit="pts")
        if not cmp_run or not cmp_counts["fin"]:
            dlabel = "first capture"
        # A run can carry apr=0.0 but lose the note proving it means 0%. If the SAME
        # offer was documented as a published 0% on the compare run, that stands:
        # rendering the client's own 0% APR as "unknown" deletes their strongest
        # finance fact (QA 2026-09-06).
        _zero = apr_published_zero(o)
        _zero_src = ""
        if prev and _zero and not prev.get("apr") and not apr_published_zero(prev):
            dlabel = "0% APR first confirmed this run"
        if not _zero and not o.get("apr") and prev and apr_published_zero(prev):
            _zero, _zero_src = True, (cmp_run["date"] if cmp_run else "")
        fin_rows.append({**o, "apr_zero": 1 if _zero else 0, "apr_zero_src": _zero_src,
                         "is_client": 1 if o["dealer"] == client_name else 0,
                         "first_seen": rentry["first_seen"], "delta_type": dtype,
                         "delta_amt": damt, "delta_label": dlabel,
                         "prev": ({"apr": prev.get("apr", 0), "term_mo": prev.get("term_mo", 0),
                                   "msrp": prev.get("msrp", 0),
                                   "apr_zero": 1 if apr_published_zero(prev) else 0}
                                  if prev else None)})
        _rankval = o.get("apr", 0) or (0.001 if _zero else 0)
        fgroups.setdefault((o.get("model", ""), norm_trim(o.get("trim", "")), o.get("yr", 0)), []).append((i, _rankval))
    franks = rank_fills(fgroups)
    for i, row in enumerate(fin_rows):
        row["rank"], row["group_size"] = franks.get(i, (0, 0))
        if any(w in str(row.get("model", "")).lower() for w in ("select", "all ")) or row.get("model") == "All":
            row["rank"], row["group_size"] = 0, 0   # unnamed models: not comparable
    fin_rows.sort(key=lambda r: (r.get("model", ""), r.get("trim", ""), r.get("apr") or 99))

    # ---- pulled offers (were live on the compare run, gone now) -----------
    seen_lease_keys = {offer_key(o, "lease") for o in ex.get("lease_offers", [])}
    seen_fin_keys = {offer_key(o, "fin") for o in ex.get("finance_offers", [])}
    # An offer that merely moved between the lease and finance buckets (a purchase
    # discount read as one or the other between runs) is NOT pulled. Match on the
    # vehicle identity across both buckets before calling anything gone.
    seen_idents = {"lease": {k.split("|", 1)[1] for k in seen_lease_keys},
                   "fin": {k.split("|", 1)[1] for k in seen_fin_keys}}
    seen_figs = ({offer_figkey(o, "lease") for o in ex.get("lease_offers", [])} |
                 {offer_figkey(o, "fin") for o in ex.get("finance_offers", [])} |
                 {offer_figkey_loose(o, "lease") for o in ex.get("lease_offers", [])} |
                 {offer_figkey_loose(o, "fin") for o in ex.get("finance_offers", [])})
    # A blanket finance headline this run ("0.9% on select models", no model named)
    # may still cover a model-specific APR seen last run at the same dealer: that is
    # unverified, never "pulled" (2026-10-05, Long Beach BMW).
    blanket_fin = {(o.get("dealer", ""), float(o.get("apr") or 0))
                   for o in ex.get("finance_offers", [])
                   if any(w in str(o.get("model", "")).lower() for w in ("select", "all ", "all-"))}
    pulled_offers = []
    for k, o in cmp_offers.items():
        is_fin = k.startswith("fin|")
        kind = "finance" if is_fin else "lease"
        if k in (seen_fin_keys if is_fin else seen_lease_keys):
            continue
        # Same figures still on the site under a different trim label: relabelled,
        # not pulled.
        _kk = "fin" if is_fin else "lease"
        if offer_figkey(o, _kk) in seen_figs or offer_figkey_loose(o, _kk) in seen_figs:
            continue
        ident = k.split("|", 1)[1]
        other, other_pfx = ("lease", "lease") if is_fin else ("fin", "fin")
        # Moved buckets rather than pulled: it shows up in the OTHER bucket now and
        # was not already in that other bucket on the compare run. A dealer that ran
        # both a lease AND a finance offer, and dropped only one, is a real pull.
        if ident in seen_idents[other] and f"{other_pfx}|{ident}" not in cmp_offers:
            continue
        dlr = o.get("dealer", "")
        # A dealer we could not read this run may still be publishing it: only call
        # an offer pulled when that dealer's crawl succeeded.
        if dealer_status.get(dlr, "failed") != "ok":
            continue
        # If we cannot state what the offer WAS, we cannot meaningfully say it was
        # pulled: those entries are trim/bucket normalization artifacts, not news.
        if not o.get("pmt") and not o.get("apr"):
            continue
        # Model-year changeover: the same store/model/trim is advertised this run
        # under a newer year. That is a replacement, shown on the live row, not a pull.
        if any(c.get("dealer") == dlr and c.get("model") == o.get("model")
               and norm_trim(c.get("trim")) == norm_trim(o.get("trim"))
               and (c.get("yr") or 0) > (o.get("yr") or 0)
               for c in ex.get("finance_offers" if is_fin else "lease_offers", [])):
            continue
        if is_fin and (dlr, float(o.get("apr") or 0)) in blanket_fin:
            continue
        pulled_offers.append({
            "kind": kind, "dealer": dlr, "is_client": 1 if dlr == client_name else 0,
            "model": o.get("model", ""), "trim": o.get("trim", ""), "yr": o.get("yr", 0),
            "pmt": o.get("pmt", 0), "apr": o.get("apr", 0), "term_mo": o.get("term_mo", 0),
            "das": o.get("das", 0), "last_seen": cmp_run["date"] if cmp_run else "",
            "offer_text": o.get("offer_text", "")})
    pulled_offers.sort(key=lambda r: (-r["is_client"], r["dealer"], r["model"]))

    # ---- movement (delisted within window) --------------------------------
    horizon = d(run_date).toordinal() - MOVEMENT_WINDOW_DAYS
    mov_groups = {}
    for vin, e in reg["vin_registry"].items():
        if not e.get("delisted_on") or d(e["delisted_on"]).toordinal() < horizon:
            continue
        gk = (e.get("yr", 0), e.get("make", ""), e.get("model", ""), e.get("trim", "") or e.get("version", ""), e.get("msrp", 0), e.get("dealer", ""))
        mov_groups.setdefault(gk, [[], False, 0])
        mov_groups[gk][0].append(e.get("dom_at_delist", 0))
        if e.get("dom_inferred"):
            mov_groups[gk][1] = True
        if e["delisted_on"] == run_date:
            mov_groups[gk][2] += 1
    movement_rows = [{"yr": yr, "make": mk, "model": md, "trim": tr, "msrp": ms,
                      "delisted": len(doms), "avg_dom": int(round(sum(doms) / len(doms))) if any(doms) else 0,
                      "dom_note": ">=" if inferred else "",
                      "this_run": this_run,
                      "dealer": dl, "is_client": 1 if dl == client_name else 0}
                     for (yr, mk, md, tr, ms, dl), (doms, inferred, this_run) in mov_groups.items()]
    movement_rows.sort(key=lambda r: -r["delisted"])
    tracking_days = days_between(reg["created"], run_date)
    if tracking_days >= MOVEMENT_WINDOW_DAYS:
        movement_note = ""
        movement_window_label = f"Delisted ({MOVEMENT_WINDOW_DAYS}d)"
    else:
        movement_note = (f"Data logging began {reg['created']}. This view reflects {tracking_days} days of "
                         f"DigitalCLIQ tracking so far; the full {MOVEMENT_WINDOW_DAYS}-day movement picture "
                         f"completes as twice-monthly snapshots accumulate.")
        # Never label the column 120d when only tracking_days of history exist.
        movement_window_label = f"Delisted (since {reg['created']}, {tracking_days}d)"
    # Delist detection only covers VINs actually re-fetched this run (see the
    # recheck gate above). Say so, so nobody reads a small number as "nothing moved".
    by_dealer = {}
    for e in reg["vin_registry"].values():
        if (e.get("vdp_url", "") or "").rstrip("/").lower() in rechecked_urls:
            by_dealer[e.get("dealer", "")] = by_dealer.get(e.get("dealer", ""), 0) + 1
    n_rechecked = sum(by_dealer.values())
    n_gone = sum(1 for e in reg["vin_registry"].values() if e.get("delisted_on") == run_date)
    # A dealer "losing" most of its rechecked stock in one cycle is almost always a
    # crawl that skipped writing rows for still-live units, not a real sell-down.
    # Surface it loudly rather than publishing phantom delistings (QA 2026-09-20).
    for _dl, _n_rc in by_dealer.items():
        _n_gone_dl = sum(1 for e in reg["vin_registry"].values()
                         if e.get("dealer") == _dl and e.get("delisted_on") == run_date)
        if _n_rc >= 5 and _n_gone_dl >= 0.6 * _n_rc:
            ex.setdefault("errors", []).append(
                f"DATA-QUALITY WARNING: {_dl} shows {_n_gone_dl} of {_n_rc} re-checked units "
                f"delisted in one cycle. Verify the crawl emitted rows for units still in "
                f"stock before treating this as real movement.")
    not_checked = [dl["name"] for dl in ex["dealers"] if not by_dealer.get(dl["name"])]
    if rechecked_urls:
        who = "; ".join(f"{k} {v}" for k, v in sorted(by_dealer.items(), key=lambda x: -x[1]))
        _gone_by = {}
        for _e in reg["vin_registry"].values():
            if _e.get("delisted_on") == run_date:
                _gone_by[_e.get("dealer", "")] = _gone_by.get(_e.get("dealer", ""), 0) + 1
        _gone_who = "; ".join(f"{k} {_gone_by.get(k, 0)}" for k in sorted(by_dealer))
        _win_units = sum(len(v[0]) for v in mov_groups.values())
        delist_basis = (f"Basis: {n_rechecked} previously tracked vehicle page(s) were re-checked this run "
                        f"({who}); {n_gone} were gone this run ({_gone_who}). Sampled units that were not "
                        f"re-checked are not counted either way, so this is a floor, not a full count of "
                        f"what sold. The table below covers the whole {tracking_days}-day tracking window "
                        f"and totals {_win_units} unit(s): {n_gone} left this run and "
                        f"{_win_units - n_gone} on earlier runs. The 'This run' column separates them.")
        if not _win_units:
            delist_basis = (f"Basis: {n_rechecked} previously tracked vehicle page(s) were re-checked this run "
                            f"({who}). None of those units has left the website this run or earlier in the "
                            f"{tracking_days}-day tracking window. Sampled units that were not re-checked are "
                            f"not counted either way.")
        _soft = [e for e in (ex.get("errors") or []) if "redirect" in str(e).lower()]
        if _soft and n_gone:
            # "Some" invited the reader to assume the rest were hard 404s. When every
            # delisting in the table is redirect-inferred, say so (QA gate 2026-09-20).
            # Name the stores: "that store" lost its referent when jargon was scrubbed.
            _named = join_names([k for k in sorted(_gone_by) if _gone_by[k]]) or "one store"
            delist_basis += (f" Delistings at {_named} were inferred from vehicle pages that now "
                             "send visitors to a search results page instead of the vehicle; that "
                             "signal is strong but is not a confirmed sale. See the Run Log.")
        if n_gone and "send visitors to" not in delist_basis:
            delist_basis += (" Gone means the vehicle's page now redirects to a listing page or no "
                             "longer exists: the unit left the website, which is not a confirmed sale.")
        if not_checked:
            delist_basis += (" No vehicle page was re-checked for " + join_names(not_checked) +
                             ", so this run says nothing about movement at "
                             + ("that store." if len(not_checked) == 1 else "those stores."))
    else:
        delist_basis = ("No previously tracked vehicle pages were re-checked this run, so no delistings "
                        "are claimed. Delist tracking needs stored vehicle-page URLs from a prior run.")

    # ---- min price matrix + VIN detail ------------------------------------
    dealer_order = [client_name] + [dl["name"] for dl in ex["dealers"] if dl["name"] != client_name]
    # A store is "MSRP only" when EVERY sampled unit it has is at sticker: that is a
    # gated-price site. A store that discounts anywhere is not, even if one model
    # happens to sit at sticker (QA 2026-09-06).
    msrp_only_dealers = set()
    for dl in dealer_order:
        mine = [v for v in ex.get("inventory", []) if v.get("dealer") == dl and v.get("price")]
        if len(mine) >= 3 and all(v.get("msrp") and v["price"] == v["msrp"] for v in mine):
            msrp_only_dealers.add(dl)
    inv_by_group = {}
    vin_rows = []
    for v in ex.get("inventory", []):
        # matrix groups at MODEL level (trim naming differs per dealer and
        # would fragment the comparison into single-dealer groups)
        gk = (v.get("model", ""), "", v.get("yr", 0))
        inv_by_group.setdefault(gk, []).append(v)
        e = reg["vin_registry"].get(v.get("vin", ""), {"first_seen": run_date, "dealer": v["dealer"], "dom_displayed": v.get("dom_displayed", 0)})
        domn, domflag = dom_of(e)
        price, msrp = v.get("price", 0), v.get("msrp", 0)
        vin_rows.append({"model": v.get("model", ""), "trim": v.get("trim", ""), "version": v.get("version", ""),
                         "yr": v.get("yr", 0), "vin": v.get("vin", ""), "msrp": msrp, "price": price,
                         "delta": (price - msrp) if price and msrp else None,
                         "call_for_price": v.get("call_for_price", 0), "dom": domn, "dom_note": domflag,
                         "dealer": v["dealer"], "is_client": 1 if v["dealer"] == client_name else 0})
    vin_rows.sort(key=lambda r: (r["model"], r["trim"], r["yr"], r["price"] or r["msrp"] or 10**9))

    matrix_rows = []
    for (model, trim, yr), vehicles in sorted(inv_by_group.items()):
        cells, vals = {}, []
        for dl in dealer_order:
            mine = [v for v in vehicles if v["dealer"] == dl]
            # Matrix reflects ADVERTISED price only. MSRP (sticker) is never a
            # substitute: a unit with price 0 is price-hidden (CFP/unknown), not
            # "advertised at MSRP". Using MSRP here misreports hidden prices as public.
            priced = [v for v in mine if v.get("price")]
            # A store showing price == MSRP on every sampled unit is not "expensive":
            # its real number is behind a lead form. Ranking it as highest is a
            # materially unfair comparison (QA 2026-09-06, Nissan of Costa Mesa).
            msrp_only = dl in msrp_only_dealers
            cfp_only = bool(mine) and not priced and any(v.get("call_for_price") for v in mine)
            if priced:
                low = min(p.get("price") for p in priced)
                at_min = [p for p in priced if p.get("price") == low]
                doms, dom_floor, dom_unknown = [], False, 0
                for p in mine:
                    e = reg["vin_registry"].get(p.get("vin", ""))
                    if not e:
                        dom_unknown += 1
                        continue
                    dv, dnote = dom_of(e)
                    if not dv:
                        dom_unknown += 1
                        continue
                    doms.append(dv)
                    if dnote:
                        dom_floor = True
                cells[dl] = {"min_price": low, "n_at_min": len(at_min), "n_stock": len(mine),
                             "age_min": min(doms) if doms else 0, "age_max": max(doms) if doms else 0,
                             "age_note": ">=" if dom_floor else "", "age_unknown": dom_unknown,
                             "cfp_only": 0, "msrp_only": 1 if msrp_only else 0}
                if not msrp_only:
                    vals.append((dl, low))   # excluded from rank, still displayed
            else:
                cells[dl] = {"min_price": 0, "n_at_min": 0, "n_stock": len(mine),
                             "age_min": 0, "age_max": 0, "age_note": "", "age_unknown": len(mine),
                             "cfp_only": 1 if cfp_only else 0}
        for rank, (dl, _) in enumerate(sorted(vals, key=lambda x: x[1]), 1):
            cells[dl]["rank"] = rank
        low_dl = min(vals, key=lambda x: x[1]) if vals else None
        matrix_rows.append({"model": model, "trim": trim, "yr": yr, "cells": cells,
                            "market_low_dealer": low_dl[0] if low_dl else "",
                            "market_low_price": low_dl[1] if low_dl else 0})

    # ---- summary bullets ---------------------------------------------------
    bullets = []
    client_lease = [r for r in lease_rows if r["is_client"] and r["rank"]]
    if client_lease:
        wins = [r for r in client_lease if r["rank"] == 1]
        # Denominator is DISTINCT model/trim/yr groups, never the raw offer count:
        # the client can publish many VIN-level payments inside one group, which
        # would understate its win rate (QA gate 2026-09-06 saw "2 of 11" for a
        # store that actually led 2 of its 2 groups).
        def _grp(rs):
            return {(r.get("model", ""), r.get("trim", ""), r.get("yr", 0)) for r in rs}
        n_win_grp, n_all_grp = len(_grp(wins)), len(_grp(client_lease))
        _cg = _grp([r for r in client_lease if r.get("dealers_in_group", 0) > 1])
        _wg = _grp([r for r in wins if r.get("dealers_in_group", 0) > 1])
        if _cg:
            bullets.append(f"Advertises the lowest effective lease payment on {len(_wg)} of "
                           f"{len(_cg)} model/trim group(s) where a rival published a comparable offer.")
        else:
            bullets.append(f"{client_name} published lease offers on {n_all_grp} model/trim(s) this run and "
                           f"no rival published a comparable offer on the same model, trim and year, so no "
                           f"head-to-head lease ranking is possible this run.")
        # A stock-numbered offer is ONE vehicle, not a model-wide program. Saying so
        # only on the Lease tab let the Summary read as a program (QA gate 2026-10-05).
        _single = [r for r in client_lease if "single-unit" in str(r.get("flags", "")).lower()]
        if _single:
            _desc = "; ".join(
                f"{r['model']} {r['trim']} {_re_stk(r.get('flags', ''))}(${r['pmt']:,}/mo, {r['term_mo']} mo, "
                f"${r.get('das', 0):,} due at signing, effective ${r.get('eff_mo', 0):,}/mo)" for r in _single)
            bullets.append(f"{client_name}'s published lease specials are single-vehicle offers tied to one "
                           f"stock number each, not model-wide programs: {_desc}.")
        worst_pool = [r for r in client_lease if r["rank"] > 1 and r.get("dealers_in_group", 0) > 1]
        contested = [w for w in wins if w.get("dealers_in_group", 0) > 1]
        if contested:
            w = max(contested, key=lambda r: r["dealers_in_group"])
            n_d = w["dealers_in_group"]
            # Never present the client's own win as universally available: if the
            # payment stacks rebates or caps mileage, say so in the bullet itself.
            quals = []
            if w.get("payment_type") == "conditional":
                quals.append("conditional payment, stacked rebates not all buyers qualify for")
            if w.get("miles_yr"):
                quals.append(f"{w['miles_yr']:,} mi/yr")
            _rivals_unknown = [x for x in lease_rows
                               if not x["is_client"] and x.get("rank")
                               and (x["model"], norm_trim(x["trim"]), x.get("yr", 0))
                               == (w["model"], norm_trim(w["trim"]), w.get("yr", 0))
                               and not x.get("miles_yr")]
            _rivals_known = sorted({x["miles_yr"] for x in lease_rows
                                    if not x["is_client"] and x.get("rank") and x.get("miles_yr")
                                    and (x["model"], norm_trim(x["trim"]), x.get("yr", 0))
                                    == (w["model"], norm_trim(w["trim"]), w.get("yr", 0))})
            # Only hedge when the allowances actually DIFFER or a rival publishes none.
            _same_allow = (_rivals_known == [w["miles_yr"]] and not _rivals_unknown
                           and not w.get("miles_yr_carried"))
            if w.get("miles_yr") and (_rivals_unknown or _rivals_known) and not _same_allow:
                bits = []
                if _rivals_known:
                    bits.append("rival allowance " +
                                "/".join(f"{v:,}" for v in _rivals_known) + " mi/yr")
                if _rivals_unknown:
                    _n = len(_rivals_unknown)
                    bits.append(f"{_n} rival offer{'' if _n == 1 else 's'} "
                                f"{'publishes' if _n == 1 else 'publish'} no capturable "
                                f"mileage allowance")
                quals.append("; ".join(bits) + ", so the comparison is not mileage-adjusted")
            if "stale_offer_date" in str(w.get("flags", "")).lower():
                quals.append("the offer's published end date has already passed but it is still "
                             "displayed on the site; renew or remove it")
            if w.get("miles_src"):
                quals = [q.replace(f"{w['miles_yr']:,} mi/yr", f"{w['miles_yr']:,} mi/yr {w['miles_src']}", 1)
                         for q in quals]
            qual = f" ({'; '.join(quals)})" if quals else ""
            bullets.append(f"Strongest lease position: {w['model']} {w['trim']} at ${w['pmt']:,}/mo "
                           f"(effective ${w['eff_mo']:,}/mo), lowest of the {n_d} dealers advertising it{qual}.")
        elif wins and "single-unit" not in str(wins[0].get("flags", "")).lower():
            # A single-vehicle offer is already stated (with its effective $/mo) in
            # the single-unit bullet; repeating it read as a duplicate (QA 2026-10-05).
            w = wins[0]
            _incomplete = [d for d, s in dealer_status.items() if s != "ok"]
            _cav = ("" if not _incomplete else
                    f" Coverage was incomplete at {len(_incomplete)} of {len(dealer_status)} stores, so this "
                    f"is the only offer captured, not proof that rivals publish none.")
            _stale = "stale_offer_date" in str(w.get("flags", "")).lower()
            _exp = (" The published end date on this offer has already passed; re-verify before quoting it."
                    if _stale else "")
            bullets.append(f"{w['model']} {w['trim']}: the only lease captured on this model and trim "
                           f"(${w['pmt']:,}/mo, effective ${w['eff_mo']:,}/mo).{_cav}{_exp}")
        if worst_pool:
            gap_row, gap = None, 0
            for r in worst_pool:
                lows = [x["eff_mo"] for x in lease_rows if not x["is_client"] and x["rank"] == 1
                        and (x["model"], norm_trim(x["trim"]), x.get("yr", 0))
                        == (r["model"], norm_trim(r["trim"]), r.get("yr", 0))]
                if lows and r["eff_mo"] - lows[0] > gap:
                    gap, gap_row = r["eff_mo"] - lows[0], r
            if gap_row:
                _win = next((x for x in lease_rows if not x["is_client"] and x["rank"] == 1
                             and (x["model"], norm_trim(x["trim"]), x.get("yr", 0))
                             == (gap_row["model"], norm_trim(gap_row["trim"]), gap_row.get("yr", 0))), None)
                _basis = ""
                if _win:
                    _d = []
                    if _win.get("term_mo") and gap_row.get("term_mo") and _win["term_mo"] != gap_row["term_mo"]:
                        _d.append(f"{gap_row['term_mo']}mo vs their {_win['term_mo']}mo")
                    if _win.get("miles_yr") and gap_row.get("miles_yr") and _win["miles_yr"] != gap_row["miles_yr"]:
                        _src = f" ({gap_row['miles_src']})" if gap_row.get("miles_src") else ""
                        _d.append(f"{gap_row['miles_yr']:,}{_src} vs their {_win['miles_yr']:,} mi/yr")
                    if _d:
                        _basis = (" Not like-for-like: " + "; ".join(_d) +
                                  ", so the gap is a term/mileage difference as well as a price one.")
                bullets.append(f"Biggest lease gap to close: {gap_row['model']} {gap_row['trim']}, "
                               f"${gap:,.0f}/mo effective above the market low." + _basis)
    elif not baseline:
        client_any = [r for r in lease_rows if r["is_client"]]
        comp_pmt = [r for r in lease_rows if not r["is_client"] and r.get("pmt")]
        if client_any:
            bullets.append(
                f"{client_name} publishes {len(client_any)} advertised offer(s) this run, but none is a "
                f"monthly lease payment (they are purchase discounts / cash offers), so it cannot be "
                f"ranked against the {len(comp_pmt)} competitor lease payment(s) in this set. "
                f"A shopper comparing monthly payments online sees competitors and not {client_name}.")
        else:
            _cdl = next((dl for dl in (ex.get("dealers") or []) if dl.get("name") == client_name), {})
            _cn = str(_cdl.get("notes", "")).lower()
            if "updating" in _cn:
                # Same statement the Lease tab and Run Log carry (QA gate 2026-10-05).
                bullets.append(f"{client_name}'s lease specials page said the store is currently updating its "
                               f"specials when checked on {run_date}, so no lease offers were published at that "
                               f"time; competitors are advertising {len(comp_pmt)} lease payment(s).")
            else:
                bullets.append(f"No lease specials were captured for {client_name} this run; competitors are "
                               f"advertising {len(comp_pmt)} lease payment(s). Worth a check of the store's "
                               f"specials page.")
    _mm = [r for r in lease_rows if r["is_client"] and "banner_das_mismatch" in str(r.get("flags", ""))]
    if _mm:
        _parts = []
        for r in _mm:
            _m = re.search(r"banner shows (\$[\d,]+).*?fine print says (\$[\d,]+)", str(r.get("flags", "")))
            _parts.append(f"{r['model']} {r['trim']}" + (f" (banner {_m.group(1)}, fine print {_m.group(2)})" if _m else ""))
        bullets.insert(0, "Compliance: " + client_name + "'s lease banners show a different due-at-signing "
                       "amount than their own fine print on " + "; ".join(_parts) + ". Under federal "
                       "advertising rules the headline and the disclosure must agree; correct the banners. "
                       "This report uses the fine-print figure.")
    # only CONTESTED groups (2+ dealers with sampled prices) count as wins;
    # "lowest of 1" would overstate the position to the client
    contested_mat = [m for m in matrix_rows if m["cells"].get(client_name, {}).get("rank")
                     and sum(1 for c in m["cells"].values() if c.get("min_price")) >= 2]
    if contested_mat:
        low_n = sum(1 for m in contested_mat if m["cells"][client_name]["rank"] == 1)
        # "comparably priced" contradicted the matrix's own NOT LIKE-FOR-LIKE note,
        # where the cheapest sampled unit is often a different trim (QA 2026-09-20).
        bullets.append(f"{client_name} holds the lowest advertised price among sampled in-stock units "
                       f"on {low_n} of {len(contested_mat)} model group(s) where 2 or more dealers "
                       f"had priced stock. Groups are by model, so one can span different trims: "
                       f"see the Min Price Matrix note.")
    cfp = {}
    for r in vin_rows:
        cfp.setdefault(r["dealer"], [0, 0])
        cfp[r["dealer"]][1] += 1
        if r["call_for_price"] and not r["price"]:
            cfp[r["dealer"]][0] += 1
    hiders = {dl: (h, t) for dl, (h, t) in cfp.items() if t >= 5 and h / t >= 0.25 and dl != client_name}
    for dl, (h, t) in sorted(hiders.items(), key=lambda x: -x[1][0] / x[1][1])[:2]:
        bullets.append(f"{dl} hides pricing (Call for Price) on {h} of {t} comparable tracked units ({h/t:.0%}).")
    if pulled_offers:
        _cl = [r for r in pulled_offers if r["is_client"]]
        _msg = (f"{len(pulled_offers)} advertised offer(s) live on {cmp_run['date']} are no longer "
                f"published this run")
        if _cl:
            _msg += (", including " + str(len(_cl)) + f" of {client_name}'s own ("
                     + "; ".join((f"{r['model']} {r['trim']}".strip() +
                                  (f" ${r['pmt']:,}/mo" if r.get("pmt") else "")) for r in _cl[:3]) + ")")
        _tabs = sorted({("Finance" if x["kind"] == "finance" else "Lease") for x in pulled_offers})
        # Only a store that published NOTHING of that kind this run gets the
        # "empty / updating page" line; Tustin still had 4 leases (QA 2026-10-05).
        _has = {(o.get("dealer"), "lease") for o in ex.get("lease_offers", [])} | \
               {(o.get("dealer"), "finance") for o in ex.get("finance_offers", [])}
        _refresh = sorted({x["dealer"] for x in pulled_offers
                           if (x["dealer"], x["kind"]) not in _has and any(("updating" in str(dl.get("notes", "")).lower()
                                   or "verified_zero" in str(dl.get("notes", "")).lower())
                                  and dl.get("name") == x["dealer"]
                                  for dl in (ex.get("dealers") or []))})
        _upd = [d for d in _refresh if any(dl.get("name") == d and "updating" in str(dl.get("notes", "")).lower()
                                             for dl in (ex.get("dealers") or []))]
        _emp = [d for d in _refresh if d not in _upd]
        _rtxt = ""
        if _upd:
            _rtxt += f" {join_names(_upd)}: the specials page said it was being updated when checked on {run_date}."
        if _emp:
            _rtxt += (f" {join_names(_emp)}: the specials page showed no lease or finance offers on tracked "
                      f"models when checked on {run_date}.")
        if _rtxt:
            _rtxt += " DigitalCLIQ will recheck next run."
        bullets.append(_msg + ". They are listed at the foot of the "
                       + " and ".join(_tabs) + " tab" + ("s" if len(_tabs) > 1 else "") + "." + _rtxt)

    # Conditionality is a market-wide condition, not a competitor characteristic.
    # Reporting only the competitors' share while the client is 100% conditional
    # misleads a GM (QA gate 2026-09-06).
    cond_all = [r for r in lease_rows if r.get("payment_type") == "conditional"]
    if cond_all:
        cond_client = [r for r in cond_all if r["is_client"]]
        n_client_offers = sum(1 for r in lease_rows if r["is_client"])
        n_pmt = sum(1 for r in lease_rows if r.get("pmt"))
        parts = [f"{len(cond_all)} of {n_pmt} advertised lease payments in this set are "
                 f"CONDITIONAL (stacked rebates not all buyers qualify for)"]
        n_client_pmt = sum(1 for r in lease_rows if r["is_client"] and r.get("pmt"))
        if n_client_pmt:
            parts.append(f"including {sum(1 for r in cond_client if r.get('pmt'))} of "
                         f"{client_name}'s {n_client_pmt}")
        bullets.append(", ".join(parts) + ". The Type column on the Lease tab marks each one.")
    if baseline:
        bullets.append(f"Baseline run: DigitalCLIQ began logging this market {run_date}. "
                       f"Movement, days-on-market, and change-tracking activate from the next run.")

    # ---- persist + emit ----------------------------------------------------
    reg["runs"].append({"date": run_date, "type": run_type})
    reg["runs"] = sorted({r["date"]: r for r in reg["runs"]}.values(), key=lambda r: r["date"])
    shutil.copyfile(args.extract, os.path.join(args.state, "snapshots", f"extract_{run_date}.json"))
    with open(reg_path, "w") as f:
        json.dump(reg, f, indent=1)

    sample_depth = {}
    for r in vin_rows:
        sample_depth.setdefault(r["dealer"], {}).setdefault(r.get("model", ""), 0)
        sample_depth[r["dealer"]][r.get("model", "")] += 1

    bullets = [depluralize(b) for b in bullets]
    delist_basis = depluralize(delist_basis)
    movement_note = depluralize(movement_note)

    analysis = {
        "meta": {**meta_in, "client_name": client_name, "run_type": run_type,
                 "sample_depth": sample_depth,
                 "compare_date": cmp_run["date"] if cmp_run else None,
                 "compare_label": (f"vs {cmp_run['date']} ({cmp_run['type']})" if cmp_run else "baseline run"),
                 "baseline": baseline, "tracking_since": reg["created"],
                 "dealer_order": dealer_order,
                 "dealers": ex["dealers"],
                 "model_years": sorted({r.get("yr", 0) for r in vin_rows if r.get("yr")}),
                 "generated": datetime.now().isoformat(timespec="seconds")},
        "summary_bullets": bullets,
        "lease_rows": lease_rows,
        "finance_rows": fin_rows,
        "movement_rows": movement_rows,
        "pulled_offers": pulled_offers,
        "movement_note": movement_note,
        "movement_window_label": movement_window_label,
        "offers_first_capture": {"lease": not cmp_counts["lease"], "finance": not cmp_counts["fin"],
                                 "compare_date": cmp_run["date"] if cmp_run else None},
        "delist_basis": delist_basis,
        "matrix_rows": matrix_rows,
        "vin_rows": vin_rows,
        "errors": ex.get("errors", []),
    }
    with open(args.out, "w") as f:
        json.dump(analysis, f, indent=1)
    print(f"analysis written: {args.out}  run_type={run_type} compare={analysis['meta']['compare_label']} "
          f"lease={len(lease_rows)} fin={len(fin_rows)} vins={len(vin_rows)} delisted_rows={len(movement_rows)}")


if __name__ == "__main__":
    main()
