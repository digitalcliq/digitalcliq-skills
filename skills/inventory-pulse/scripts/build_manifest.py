#!/usr/bin/env python3
"""DigitalCLIQ Inventory Pulse: facts manifest for the deliverable-reviewer QA gate.

Generates the manifest deterministically from the analysis JSON so every field
the workbook renders is covered (a hand-built manifest missed lease/finance
MSRPs and trims on 2026-08-15 and the reviewer flagged them as unsourced).

Usage: build_manifest.py <analysis.json> <out_manifest.json>
"""
import json, sys

a = json.load(open(sys.argv[1]))
m = []


def add(v, l, s):
    m.append({"value": v, "label": l, "source": s})


meta = a["meta"]
add(meta["run_date"], "report date, mastheads", "run parameter")
add(meta["compare_label"], "Summary compare label", "snapshot_diff.py")
add(meta["client_name"], "client name throughout", "config/clients.json")
add(", ".join(meta.get("models_tracked", [])), "Summary models line", "config/clients.json")
add(", ".join(str(y) for y in meta.get("model_years", [])), "Summary model years line", "VDP extraction")
add(meta["tracking_since"], "Summary tracking-since stat", "state registry")
for b in a["summary_bullets"]:
    add(b, "Summary bullet", "snapshot_diff.py analytics")
for d in meta["dealers"]:
    add(f"{d['name']}: {d['status']} via {d['crawl_method']}, {d['pages_crawled']} pages, notes: {d.get('notes','')}",
        "Run Log row", "dealer agent fragment")
for r in a["lease_rows"]:
    add(f"{r['dealer']} {r['model']} trim '{r.get('trim','')}' MY {r.get('yr',0)} ${r['pmt']}/mo "
        f"{r['term_mo']}mo down ${r.get('down',0)} DAS ${r['das']} {r.get('miles_yr',0)}mi/yr "
        f"msrp ${r.get('msrp',0)} eff ${r['eff_mo']} rank {r['rank']}/{r['group_size']} "
        f"{r.get('payment_type','')} flags [{r.get('flags','')}] vs-prior '{r['delta_label']}' "
        f"offer: {r.get('offer_text','')[:160]}",
        "Lease Offers row (all rendered fields)",
        "dealer agent read of specials page/banner; eff+rank+delta from snapshot_diff.py")
for r in a["finance_rows"]:
    add(f"{r['dealer']} {r['model']} trim '{r.get('trim','')}' MY {r.get('yr',0)} apr {r.get('apr',0)} "
        f"term {r.get('term_mo',0)} msrp ${r.get('msrp',0)} vs-prior '{r['delta_label']}' "
        f"conditions: {r.get('conditions','')[:160]}",
        "Finance Offers row (all rendered fields; an unpublished APR renders as ?)", "dealer agent")
add(len(a["vin_rows"]), "VIN Detail row count", "merged fragments (sampled 3-4/model/dealer)")
for r in a["vin_rows"]:
    add(f"{r['dealer']} {r['vin']} {r['yr']} {r['model']} trim '{r.get('trim','')}' "
        f"version '{r.get('version','')}' msrp {r['msrp']} price {r['price']} cfp {r['call_for_price']} "
        f"dom {r['dom_note']}{r['dom']}",
        "VIN Detail row", "dealer vehicle listing (an unpublished value renders as ?)")
for r in a["matrix_rows"]:
    cells = "; ".join(f"{dl}: min {c.get('min_price',0)} rank {c.get('rank',0)} stock {c.get('n_stock',0)}"
                      for dl, c in r["cells"].items())
    add(f"{r['model']}/{r['yr']}: market low {r['market_low_dealer']} ${r['market_low_price']} | {cells}",
        "Min Price Matrix row (lowest among SAMPLED units, model-level)", "snapshot_diff.py from sampled inventory")
for r in a["movement_rows"]:
    add(f"{r['dealer']} {r['yr']} {r['make']} {r['model']} delisted {r['delisted']} avg_dom {r['avg_dom']}",
        "Inventory Movement row", "snapshot_diff.py vin registry")
if a.get("movement_note"):
    add(a["movement_note"], "Inventory Movement / Summary note", "snapshot_diff.py baseline logic")
for e in a.get("errors", []):
    add(e, "Run Log error", "dealer agent")

json.dump(m, open(sys.argv[2], "w"), indent=1)
print(f"manifest entries: {len(m)}")
