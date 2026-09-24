#!/usr/bin/env python3
"""DigitalCLIQ Inventory Pulse: merge per-dealer agent fragments into the
run's extract JSON (schema in SKILL.md). Deterministic so the model never
assembles or reads inventory JSON in context.

Each dealer agent writes  <data>/<dealer-slug>/fragment.json:
  {"dealer": {name, role, url, platform, crawl_method, status, pages_crawled, notes},
   "lease_offers": [...], "finance_offers": [...], "inventory": [...], "errors": [...]}
Inventory rows may come from crawl_inventory.py (copy inventory.json rows into
"inventory") or from the browser extractor (same row shape).

This script:
  - normalizes every inventory row's model to the config's canonical model
    string via the match lists (rows matching no tracked model are dropped),
  - coerces numeric fields, dedups VINs per dealer, uppercases VINs,
  - stamps dealer name on every row, assembles meta, rolls up errors,
  - writes extract_{CODE}_{date}.json and prints a per-dealer summary.

Usage: merge_extract.py --config clients.json --client MCP --date 2026-08-20 \
                        --data <scratchpad>/pulse-run/MCP --out extract_MCP_2026-08-20.json
Exit 1 if the CLIENT dealer has no fragment (competitors may be missing).
"""
import argparse, json, os, re, sys


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def num(v):
    if v is None: return 0
    if isinstance(v, (int, float)): return int(round(float(v)))
    s = re.sub(r"[^\d.]", "", str(v))
    try: return int(round(float(s))) if s else 0
    except Exception: return 0


PLAUSIBLE_MIN, PLAUSIBLE_MAX = 5000, 250000


def sane_amount(v):
    """New-vehicle MSRP/price plausibility guard: regex extraction can glue
    adjacent numbers together (e.g. a $383,382 'MSRP' on a $53K Ram). Out of
    range -> 0, which renders as '?' (never fabricate)."""
    v = num(v)
    return v if PLAUSIBLE_MIN <= v <= PLAUSIBLE_MAX else 0


def clean_trim(trim, model="", make=""):
    """Strip condition words, the repeated model/make prefix, and noisy
    whitespace from platform trim strings like 'New  1500 Big Horn Crew Cab'."""
    t = re.sub(r"^\s*(new|used|certified(\s+pre-?owned)?)\b\s*", "", str(trim), flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()
    for prefix in (f"{make} {model}", model, make):
        if prefix and t.lower().startswith(prefix.lower() + " "):
            t = t[len(prefix):].strip()
    return t


EXPIRY_RE = re.compile(r"(?:offer\s+)?(?:ends?|expires?|exp\.?)[\s:]*?(\d{1,2}/\d{1,2}/\d{4})", re.I)


def expired_flag(o, run_date):
    """Return True if the offer's own text carries an end date before run_date."""
    hay = " ".join(str(o.get(k, "")) for k in ("offer_text", "disclaimer_text", "conditions", "parse_note"))
    m = EXPIRY_RE.search(hay)
    if not m:
        return False
    try:
        mm, dd, yyyy = m.group(1).split("/")
        return f"{yyyy}-{int(mm):02d}-{int(dd):02d}" < run_date
    except Exception:
        return False


def canon_model(row, models):
    """Return canonical config model string, or None if untracked."""
    hay = " ".join(str(row.get(k, "")) for k in ("model", "version", "trim", "vdp_url")).lower()
    for m in models:
        if any(pat.lower() in hay for pat in m["match"]):
            if m.get("make") and row.get("make") and m["make"].lower() not in str(row["make"]).lower() \
               and m["make"].lower() not in hay:
                continue
            return m["model"], m.get("make", "")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--client", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    cfg = json.load(open(args.config))["clients"][args.client.upper()]
    dealers_cfg = [dict(cfg["client_dealer"], role="client")] + \
                  [dict(c, role="competitor") for c in cfg["competitors"]]
    models = cfg["models"]

    out = {"meta": {"client_code": args.client.upper(), "client_name": cfg["display"],
                    "run_date": args.date, "brand": cfg["brand"],
                    "models_tracked": [m["model"] for m in models]},
           "dealers": [], "lease_offers": [], "finance_offers": [], "inventory": [], "errors": []}
    lines, client_ok = [], False

    for dc in dealers_cfg:
        sl = slug(dc["name"])
        fp = os.path.join(args.data, sl, "fragment.json")
        if not os.path.exists(fp):
            out["dealers"].append({"name": dc["name"], "role": dc["role"], "url": dc["url"],
                                   "platform": dc.get("platform", ""), "crawl_method": "",
                                   "status": "failed", "pages_crawled": 0,
                                   "notes": "no fragment written by dealer agent"})
            out["errors"].append(f"{dc['name']}: no fragment.json at {fp}")
            lines.append(f"{dc['name']:32} FAILED (no fragment)")
            continue
        try:
            frag = json.load(open(fp))
        except Exception as e:
            out["dealers"].append({"name": dc["name"], "role": dc["role"], "url": dc["url"],
                                   "platform": dc.get("platform", ""), "crawl_method": "",
                                   "status": "failed", "pages_crawled": 0, "notes": f"fragment unreadable: {e}"})
            out["errors"].append(f"{dc['name']}: fragment.json unreadable: {e}")
            lines.append(f"{dc['name']:32} FAILED (bad fragment)")
            continue

        d = frag.get("dealer", {})
        # curly braces in free-text notes read as template placeholders downstream
        # (post_flight no_placeholders check); neutralize them at merge time
        drow = {"name": dc["name"], "role": dc["role"], "url": dc["url"],
                "platform": d.get("platform") or dc.get("platform", ""),
                "crawl_method": d.get("crawl_method", ""), "status": d.get("status", "partial"),
                "pages_crawled": num(d.get("pages_crawled")),
                "notes": str(d.get("notes", "")).replace("{", "(").replace("}", ")")}
        out["dealers"].append(drow)
        if dc["role"] == "client" and drow["status"] in ("ok", "partial"):
            client_ok = True

        kept = dropped = 0
        seen_vins = set()
        for r in frag.get("inventory", []):
            cm = canon_model(r, models)
            if not cm:
                dropped += 1; continue
            vin = str(r.get("vin", "")).strip().upper()
            if vin and vin in seen_vins:
                continue
            if vin: seen_vins.add(vin)
            make = str(r.get("make") or cm[1])
            msrp, price = sane_amount(r.get("msrp")), sane_amount(r.get("price"))
            if msrp and price and msrp > 2.5 * price:
                msrp = 0  # gross MSRP/price disagreement = extraction artifact
            out["inventory"].append({"dealer": dc["name"], "vin": vin, "yr": num(r.get("yr")),
                                     "make": make, "model": cm[0],
                                     "trim": clean_trim(r.get("trim", ""), cm[0], make),
                                     "version": re.sub(r"\s+", " ", str(r.get("version", ""))).strip(),
                                     "msrp": msrp, "price": price,
                                     "call_for_price": 1 if r.get("call_for_price") else 0,
                                     "dom_displayed": num(r.get("dom_displayed")),
                                     "vdp_url": str(r.get("vdp_url", ""))})
            kept += 1

        for kind, target in (("lease_offers", out["lease_offers"]), ("finance_offers", out["finance_offers"])):
            for o in frag.get(kind, []):
                o = dict(o); o["dealer"] = dc["name"]
                cm = canon_model(o, models)
                if cm: o["model"] = cm[0]
                for f in ("pmt", "term_mo", "das", "down", "miles_yr", "yr"):
                    if f in o: o[f] = num(o[f])
                if "msrp" in o: o["msrp"] = sane_amount(o["msrp"])
                if kind == "finance_offers" and "apr" in o:
                    try: o["apr"] = float(o["apr"] or 0)
                    except Exception: o["apr"] = 0.0
                if expired_flag(o, args.date):
                    if kind == "lease_offers":
                        o["flags"] = "|".join(x for x in [str(o.get("flags", "")), "EXPIRED_AT_CAPTURE"] if x)
                    else:
                        o["conditions"] = (str(o.get("conditions", "")) + " [expired at capture]").strip()
                target.append(o)

        for e in frag.get("errors", []):
            out["errors"].append(f"{dc['name']}: {e}".replace("{", "(").replace("}", ")"))
        lines.append(f"{dc['name']:32} {drow['status']:8} vins={kept} dropped_untracked={dropped} "
                     f"lease={len(frag.get('lease_offers', []))} fin={len(frag.get('finance_offers', []))} "
                     f"via={drow['crawl_method']}")

    json.dump(out, open(args.out, "w"), indent=1)
    print("\n".join(lines))
    print(f"TOTAL vins={len(out['inventory'])} lease={len(out['lease_offers'])} "
          f"fin={len(out['finance_offers'])} errors={len(out['errors'])} -> {args.out}")
    if not client_ok:
        print("CLIENT DEALER CRAWL FAILED: report ships only if Drew's rules say so; flag loudly.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
