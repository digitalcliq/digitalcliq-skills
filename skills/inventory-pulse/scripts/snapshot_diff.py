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
- A VIN in the registry that is missing from this run is marked delisted ONLY if
  its dealer's crawl status is "ok" this run. Failed crawls never fake delistings.
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


def loose_prev(cmp_offers, o, kind):
    """Match a prior offer on dealer+model+year when the trim STRING changed.

    2026-08-25: Puente Hills' Ram 1500 lease was unchanged at $369 but the site's trim
    text went from "Big Horn Crew Cab 4x4 5'7\" Box 4WD" to "Big Horn Crew Cab 4x4",
    which split one offer into two and labelled a carried-over offer "new this period".
    Only accept the fallback when exactly one prior offer fits, so we never guess.
    """
    want = (kind, o.get("dealer", ""), str(o.get("model", "")).lower(), o.get("yr", 0))
    hits = [v for k2, v in cmp_offers.items()
            if k2.split("|")[0] == kind and v.get("dealer") == o.get("dealer")
            and str(v.get("model", "")).lower() == want[2] and v.get("yr", 0) == want[3]]
    return hits[0] if len(hits) == 1 else None


def offer_key(o, kind):
    return f"{kind}|{o['dealer']}|{o.get('model','')}|{o.get('trim','')}|{o.get('yr',0)}"


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
        pool = prev_anchor or prev or earlier
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


def rank_fills(groups, zero_is_valid=False):
    """groups: dict key -> list of (idx, value). Returns idx -> (rank, group_size).

    zero_is_valid: for APR, 0.0 is a real (and the best) rate, so it must rank.
    For a lease payment, 0 means "unknown" and must not rank.
    """
    out = {}
    for _, members in groups.items():
        keep = (lambda v: v is not None) if zero_is_valid else (lambda v: bool(v))
        valid = sorted([m for m in members if keep(m[1])], key=lambda x: x[1])
        for rank, (idx, _) in enumerate(valid, 1):
            out[idx] = (rank, len(valid))
        ranked = {idx for idx, _ in valid}
        for idx, v in members:
            if idx not in ranked:
                out[idx] = (0, len(valid))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--out", required=True)
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
    dealer_status = {dl["name"]: dl.get("status", "failed") for dl in ex["dealers"]}
    client_name = ex["meta"].get("client_name") or next(
        (dl["name"] for dl in ex["dealers"] if dl.get("role") == "client"), "")

    for dl in ex["dealers"]:
        reg["dealer_first_crawl"].setdefault(dl["name"], run_date)

    # ---- compare run selection --------------------------------------------
    cmp_run = pick_compare_run(reg["runs"], run_date)
    cmp_offers = {}
    if cmp_run:
        snap = load_json(os.path.join(args.state, "snapshots", f"extract_{cmp_run['date']}.json"), {})
        for kind, lst in (("lease", snap.get("lease_offers", [])), ("fin", snap.get("finance_offers", []))):
            for o in lst:
                cmp_offers[offer_key(o, kind)] = o

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
    for vin, entry in reg["vin_registry"].items():
        if vin in seen_vins or entry.get("delisted_on"):
            continue
        # Inventory is SAMPLED, so "VIN absent this run" does NOT mean delisted: it usually
        # means this run's sample picked different units. A VIN may only be called delisted if
        # it was actually RECHECKABLE, i.e. we stored its VDP url and could re-fetch it.
        # (2026-08-25: the 2026-08-15 baseline stored no vdp_url for the three MCP competitors,
        # so absence there produced 10 phantom "sold" rows. Never ship inferred delistings.)
        if not entry.get("vdp_url"):
            continue
        if dealer_status.get(entry.get("dealer", ""), "failed") == "ok" and entry.get("last_seen", run_date) != run_date:
            entry["delisted_on"] = run_date
            entry["dom_at_delist"] = entry.get("dom_displayed") or days_between(entry["first_seen"], run_date)

    # ---- offer registry + lease rows --------------------------------------
    def dom_of(entry):
        disp = entry.get("dom_displayed", 0)
        if disp:
            return disp, ""
        dlr = entry.get("dealer", "")
        floor = reg["dealer_first_crawl"].get(dlr, run_date) == entry["first_seen"] and not baseline
        n = days_between(entry["first_seen"], run_date)
        return n, (">=" if floor or baseline else "")

    lease_rows, groups = [], {}
    for i, o in enumerate(ex.get("lease_offers", [])):
        k = offer_key(o, "lease")
        rentry = reg["offer_registry"].setdefault(k, {"first_seen": run_date, "history": []})
        rentry["last_seen"] = run_date
        rentry["history"].append({"date": run_date, "pmt": o.get("pmt", 0),
                                  "das": o.get("das", 0), "term_mo": o.get("term_mo", 0)})
        prev = cmp_offers.get(k) or loose_prev(cmp_offers, o, "lease")
        dtype, damt, dlabel = delta_row(o.get("pmt", 0), prev.get("pmt", 0) if prev else None)
        if not cmp_run:
            dlabel = "first capture"  # baseline: nothing existed to be "new" against
        eff = eff_monthly(o.get("pmt", 0), o.get("das", 0), o.get("term_mo", 0))
        flags = [f for f in str(o.get("flags", "")).split("|") if f]
        if o.get("pmt") and not o.get("das"):
            flags.append("cash due not published")
        if o.get("miles_yr") and o["miles_yr"] < 10000:
            flags.append("5,000 mi/yr" if o["miles_yr"] <= 5000 else f"{o['miles_yr']:,} mi/yr")
        row = {**o, "is_client": 1 if o["dealer"] == client_name else 0,
               "first_seen": rentry["first_seen"], "eff_mo": eff,
               "delta_type": dtype, "delta_amt": damt, "delta_label": dlabel,
               "flags": "|".join(sorted(set(flags))),
               "prev": ({"pmt": prev.get("pmt", 0), "term_mo": prev.get("term_mo", 0),
                         "das": prev.get("das", 0), "msrp": prev.get("msrp", 0),
                         "offer_text": prev.get("offer_text", "")} if prev else None)}
        lease_rows.append(row)
        groups.setdefault((o.get("model", ""), o.get("yr", 0)), []).append((i, eff))
    ranks = rank_fills(groups)
    for i, row in enumerate(lease_rows):
        row["rank"], row["group_size"] = ranks.get(i, (0, 0))
    lease_rows.sort(key=lambda r: (r.get("model", ""), r.get("trim", ""), r.get("eff_mo") or 10**9))

    fin_rows, fgroups = [], {}
    for i, o in enumerate(ex.get("finance_offers", [])):
        k = offer_key(o, "fin")
        rentry = reg["offer_registry"].setdefault(k, {"first_seen": run_date, "history": []})
        rentry["last_seen"] = run_date
        rentry["history"].append({"date": run_date, "apr": o.get("apr", 0), "term_mo": o.get("term_mo", 0)})
        prev = cmp_offers.get(k) or loose_prev(cmp_offers, o, "fin")
        dtype, damt, dlabel = delta_row(o.get("apr", 0), prev.get("apr", 0) if prev else None, unit="pts")
        if not cmp_run:
            dlabel = "first capture"
        _apr = o.get("apr", None)
        _apr = None if _apr in ("", None) else float(_apr)
        # 0.0 is BOTH "a genuine 0% APR" and the schema's "no APR published" sentinel.
        # Only treat a zero as real when the offer's own words advertise a zero rate,
        # otherwise a cash/rebate offer renders as "0.00% APR", which is fabrication.
        _txt = " ".join(str(o.get(_f, "")) for _f in ("conditions", "parse_note", "offer_text"))
        _zero_advertised = bool(re.search(r"\b0(?:\.0+)?\s*%\s*APR|\bzero\s+percent\b", _txt, re.I))
        _real = _apr is not None and (_apr > 0 or _zero_advertised)
        fin_rows.append({**o, "is_client": 1 if o["dealer"] == client_name else 0,
                         "first_seen": rentry["first_seen"], "delta_type": dtype,
                         "delta_amt": damt, "delta_label": dlabel,
                         "apr_published": 1 if _real else 0,
                         "prev": ({"apr": prev.get("apr", 0), "term_mo": prev.get("term_mo", 0),
                                   "msrp": prev.get("msrp", 0)} if prev else None)})
        fgroups.setdefault((o.get("model", ""), o.get("yr", 0)), []).append(
            (i, _apr if _real else None))
    franks = rank_fills(fgroups, zero_is_valid=True)
    for i, row in enumerate(fin_rows):
        row["rank"], row["group_size"] = franks.get(i, (0, 0))
    fin_rows.sort(key=lambda r: (r.get("model", ""), r.get("trim", ""),
                                 r["apr"] if r.get("apr") is not None and r.get("rank") else 99))

    # ---- movement (delisted within window) --------------------------------
    horizon = d(run_date).toordinal() - MOVEMENT_WINDOW_DAYS
    mov_groups = {}
    for vin, e in reg["vin_registry"].items():
        if not e.get("delisted_on") or d(e["delisted_on"]).toordinal() < horizon:
            continue
        gk = (e.get("yr", 0), e.get("make", ""), e.get("model", ""), e.get("trim", "") or e.get("version", ""), e.get("msrp", 0), e.get("dealer", ""))
        mov_groups.setdefault(gk, []).append(e.get("dom_at_delist", 0))
    movement_rows = [{"yr": yr, "make": mk, "model": md, "trim": tr, "msrp": ms,
                      "delisted": len(doms), "avg_dom": int(round(sum(doms) / len(doms))) if any(doms) else 0,
                      "dealer": dl, "is_client": 1 if dl == client_name else 0}
                     for (yr, mk, md, tr, ms, dl), doms in mov_groups.items()]
    movement_rows.sort(key=lambda r: -r["delisted"])
    tracking_days = days_between(reg["created"], run_date)
    if tracking_days >= MOVEMENT_WINDOW_DAYS:
        movement_note = ""
    else:
        movement_note = (f"Data logging began {reg['created']}. This view reflects {tracking_days} days of "
                         f"DigitalCLIQ tracking so far; the full {MOVEMENT_WINDOW_DAYS}-day movement picture "
                         f"completes as twice-monthly snapshots accumulate.")

    # ---- min price matrix + VIN detail ------------------------------------
    dealer_order = [client_name] + [dl["name"] for dl in ex["dealers"] if dl["name"] != client_name]
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
            priced = [v for v in mine if (v.get("price") or v.get("msrp"))]
            cfp_only = bool(mine) and not priced and any(v.get("call_for_price") for v in mine)
            if priced:
                low = min(p.get("price") or p.get("msrp") for p in priced)
                at_min = [p for p in priced if (p.get("price") or p.get("msrp")) == low]
                doms = []
                for p in mine:
                    e = reg["vin_registry"].get(p.get("vin", ""))
                    if e:
                        doms.append(dom_of(e)[0])
                cells[dl] = {"min_price": low, "n_at_min": len(at_min), "n_stock": len(mine),
                             "age_min": min(doms) if doms else 0, "age_max": max(doms) if doms else 0,
                             "cfp_only": 0}
                vals.append((dl, low))
            else:
                cells[dl] = {"min_price": 0, "n_at_min": 0, "n_stock": len(mine),
                             "age_min": 0, "age_max": 0, "cfp_only": 1 if cfp_only else 0}
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
        bullets.append(f"Advertises the lowest effective lease payment on {len(wins)} of "
                       f"{len(client_lease)} model/trims where {client_name} has a published offer.")
        worst_pool = [r for r in client_lease if r["rank"] > 1 and r["group_size"] > 1]
        contested = [w for w in wins if w["group_size"] > 1]
        if contested:
            w = max(contested, key=lambda r: r["group_size"])
            bullets.append(f"Strongest lease position: {w['model']} {w['trim']} at ${w['pmt']:,}/mo "
                           f"(effective ${w['eff_mo']:,}/mo), lowest of {w['group_size']} dealers advertising.")
        elif wins:
            w = wins[0]
            bullets.append(f"{w['model']} {w['trim']}: only dealer in the set advertising a lease "
                           f"(${w['pmt']:,}/mo, effective ${w['eff_mo']:,}/mo). Uncontested position.")
        if worst_pool:
            gap_row, gap = None, 0
            for r in worst_pool:
                lows = [x["eff_mo"] for x in lease_rows if not x["is_client"] and x["rank"] == 1
                        and (x["model"], x["trim"], x.get("yr", 0)) == (r["model"], r["trim"], r.get("yr", 0))]
                if lows and r["eff_mo"] - lows[0] > gap:
                    gap, gap_row = r["eff_mo"] - lows[0], r
            if gap_row:
                bullets.append(f"Biggest lease gap to close: {gap_row['model']} {gap_row['trim']}, "
                               f"${gap:,.0f}/mo effective above the market low.")
    elif not baseline:
        bullets.append(f"No published lease specials found for {client_name} this run; competitors are advertising. Verify on site.")
    # only CONTESTED groups (2+ dealers with sampled prices) count as wins;
    # "lowest of 1" would overstate the position to the client
    contested_mat = [m for m in matrix_rows if m["cells"].get(client_name, {}).get("rank")
                     and sum(1 for c in m["cells"].values() if c.get("min_price")) >= 2]
    if contested_mat:
        low_n = sum(1 for m in contested_mat if m["cells"][client_name]["rank"] == 1)
        bullets.append(f"Lowest advertised price among sampled in-stock units on {low_n} of "
                       f"{len(contested_mat)} model groups where 2+ dealers were comparable.")
    cfp = {}
    for r in vin_rows:
        cfp.setdefault(r["dealer"], [0, 0])
        cfp[r["dealer"]][1] += 1
        if r["call_for_price"] and not r["price"]:
            cfp[r["dealer"]][0] += 1
    hiders = {dl: (h, t) for dl, (h, t) in cfp.items() if t >= 5 and h / t >= 0.25 and dl != client_name}
    for dl, (h, t) in sorted(hiders.items(), key=lambda x: -x[1][0] / x[1][1])[:2]:
        bullets.append(f"{dl} hides pricing (Call for Price) on {h} of {t} comparable tracked units ({h/t:.0%}).")
    conditional = [r for r in lease_rows if not r["is_client"] and r.get("payment_type") == "conditional" and r["rank"] == 1]
    if conditional:
        bullets.append(f"{len(conditional)} of the competitor market-low lease payments are conditional or unverified: "
                       f"either they stack rebates a typical buyer may not qualify for, or their fine print could not "
                       f"be read. The Lease tab shows which is which.")
    if baseline:
        bullets.append(f"Baseline run: DigitalCLIQ began logging this market {run_date}. "
                       f"Movement, days-on-market, and change-tracking activate from the next run.")

    # ---- persist + emit ----------------------------------------------------
    reg["runs"].append({"date": run_date, "type": run_type})
    reg["runs"] = sorted({r["date"]: r for r in reg["runs"]}.values(), key=lambda r: r["date"])
    shutil.copyfile(args.extract, os.path.join(args.state, "snapshots", f"extract_{run_date}.json"))
    with open(reg_path, "w") as f:
        json.dump(reg, f, indent=1)

    analysis = {
        "meta": {**meta_in, "client_name": client_name, "run_type": run_type,
                 "compare_date": cmp_run["date"] if cmp_run else None,
                 "compare_label": (f"vs {cmp_run['date']} ({cmp_run['type']})" if cmp_run else "baseline run"),
                 "baseline": baseline, "tracking_since": reg["created"],
                 "tracking_days": tracking_days,
                 "dealer_order": dealer_order,
                 "dealers": ex["dealers"],
                 "model_years": sorted({r.get("yr", 0) for r in vin_rows if r.get("yr")}),
                 "generated": datetime.now().isoformat(timespec="seconds")},
        "summary_bullets": bullets,
        "lease_rows": lease_rows,
        "finance_rows": fin_rows,
        "movement_rows": movement_rows,
        "movement_note": movement_note,
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
