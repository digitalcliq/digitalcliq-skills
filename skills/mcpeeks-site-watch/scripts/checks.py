#!/usr/bin/env python3
"""Deterministic compliance + data-accuracy checks over inventory.json.

Covers checks C01-C13, C21, C22-C24 (CNCDA CARS Act additions, 2026-09-14), and C25 (FTC in-transit status, 2026-10-08) from the dealer-principal list (see SKILL.md).
Reads inventory.json + state (first-seen dates, approved vendors, disclaimer
template, optional lease programs). Emits findings.json — the ONLY file the
model needs to read afterwards.

Usage:
  python3 checks.py --data DATA_DIR --skill SKILL_DIR --state STATE_DIR
"""
import argparse, datetime, json, os, re, sys

SEV_COMPLIANCE, SEV_DATA, SEV_HYGIENE = "compliance", "data_accuracy", "hygiene"
# Veh. Code 11713.1(c)(2) statutory fee sentence, required verbatim on every page
# that displays a vehicle price (CNCDA CARS Act Guide v1.2, Part 2).
PLUS_DISCLOSURE_VERBATIM = ("plus government fees and taxes, any finance charges, any dealer document "
                            "processing charge, any electronic filing charge, and any emission testing charge")
TODAY = datetime.date.today()


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def finding(check, severity, url, summary, vin=None, detail=None):
    return {"check": check, "severity": severity, "url": url, "vin": vin,
            "summary": summary, "detail": detail}


def norm_words(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).split()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--skill", required=True)
    ap.add_argument("--state", required=True)
    args = ap.parse_args()

    inv = load(os.path.join(args.data, "inventory.json"), None)
    if not inv:
        print("FATAL: no inventory.json", file=sys.stderr); sys.exit(1)
    vehicles = inv["vehicles"]

    first_seen = load(os.path.join(args.state, "first_seen.json"), {})
    approved = set()
    try:
        with open(os.path.join(args.skill, "config", "approved_vendors.txt")) as f:
            approved = {l.strip().lower() for l in f if l.strip() and not l.startswith("#")}
    except Exception:
        pass
    template = ""
    try:
        with open(os.path.join(args.skill, "config", "fee_disclaimer_template.txt")) as f:
            template = f.read().strip()
    except Exception:
        pass
    if template.startswith("PASTE"):
        template = ""
    lease_programs = load(os.path.join(args.skill, "config", "lease_programs.json"), {})

    F = []
    for v in vehicles:
        url, vin = v["url"], v.get("vin")
        cond = v.get("condition", "")
        labels = v.get("price_labels", {})
        rebate_total = sum(r["amount"] for r in v.get("rebates", []))
        selling = labels.get("Selling Price") or v.get("jsonld_price")
        msrp = labels.get("Msrp") or labels.get("MSRP".title())

        # C06 — no price / Call for Price (never allowed).
        # Fires when no pricing-box labels parsed AND the feed price is not
        # rendered anywhere on the page (classic RAM 4500/5500 chassis-cab gap).
        if v.get("call_for_price") or (not labels and not v.get("price_displayed")):
            F.append(finding("C06", SEV_COMPLIANCE, url,
                "No price displayed on page ('Call for Price' pattern)"
                + (" — explicit 'Call for Price' text" if v.get("call_for_price") else ""),
                vin, f"labels={labels} feed_price={v.get('jsonld_price')} "
                     f"rendered={v.get('price_displayed')}"))

        # C01 — pre-rebate selling price must be displayed (taxable price, CA ad law)
        if cond == "NEW" and rebate_total > 0 and selling:
            pre_rebate = selling + rebate_total
            displayed = set(labels.values())
            shows_pre = any(a and abs(a - pre_rebate) < 1 for a in displayed)
            if not shows_pre:
                F.append(finding("C01", SEV_COMPLIANCE, url,
                    f"Pre-rebate selling price ${pre_rebate:,.0f} NOT displayed "
                    f"(shows only post-rebate ${selling:,.0f}; rebates ${rebate_total:,.0f})",
                    vin, f"labels={labels} rebates={v['rebates']}"))

        # C02 — doc fee excluded from advertised price
        if v.get("doc_fee_excluded_language"):
            F.append(finding("C02", SEV_COMPLIANCE, url,
                "Advertised price excludes doc fee ('plus doc fee' language found)", vin,
                v.get("disclaimer_text", "")[:300]))

        # C04 — required fee disclaimer present (verbatim Plus Disclosure, VC 11713.1(c)(2))
        disc = v.get("disclaimer_text", "")
        if not disc:
            F.append(finding("C04", SEV_COMPLIANCE, url,
                "Fee disclaimer language missing from VDP", vin))
        elif not template and PLUS_DISCLOSURE_VERBATIM not in re.sub(r"\s+", " ", disc.lower()):
            F.append(finding("C04", SEV_COMPLIANCE, url,
                "Fee disclaimer is not the verbatim statutory sentence (abbreviated or reworded)",
                vin, disc[:400]))
        elif template:
            tw, dw = set(norm_words(template)), set(norm_words(disc))
            overlap = len(tw & dw) / max(1, len(tw))
            if overlap < 0.7:
                F.append(finding("C04", SEV_COMPLIANCE, url,
                    f"Fee disclaimer deviates from approved template ({overlap:.0%} word overlap)",
                    vin, disc[:400]))

        # C05 — payment shown without finance disclosure
        if v.get("payments") and not re.search(
                r"(APR|on approved credit|OAC|with approved credit|amount financed|financ)",
                v.get("payment_text", ""), re.I):
            F.append(finding("C05", SEV_COMPLIANCE, url,
                "Payment displayed without finance disclosure language", vin,
                v.get("payment_text", "")[:300]))

        # C22 — installed items excluded from the advertised price (CARS Act, CNCDA)
        if v.get("installed_excluded_language"):
            F.append(finding("C22", SEV_COMPLIANCE, url,
                "Installed equipment excluded from the advertised price (pay-or-remove wording)", vin,
                v.get("disclaimer_text", "")[:300]))

        # C23 — repealed two-day cancellation option wording (CARS Act, CNCDA)
        if v.get("repealed_option_language"):
            F.append(finding("C23", SEV_COMPLIANCE, url,
                "Repealed two-day cancellation option / $40,000 wording still on the page", vin))

        # C24 — MSRP shown as the price / 'MSRP is not the selling price' (CARS Act, CNCDA)
        if v.get("msrp_not_price_language") or (msrp and not selling and cond == "NEW"):
            F.append(finding("C24", SEV_COMPLIANCE, url,
                "MSRP presented as the price or 'MSRP is not the selling price' wording", vin,
                f"labels={labels}"))

        # C25 — in-transit status (FTC FAQ Q10; FTC staff remarks 2026-09-30, added 2026-10-08)
        if v.get("in_transit_language") and v.get("unbuilt_language"):
            F.append(finding("C25", SEV_COMPLIANCE, url,
                "Unit labeled in transit but also described as in production / not yet built", vin,
                v.get("disclaimer_text", "")[:200]))
        elif v.get("in_transit_language") and not v.get("arrival_language"):
            F.append(finding("C25", SEV_DATA, url,
                "In-transit unit shows no arrival information", vin))

        # C07 — used price without expiration disclaimer
        if cond == "USED" and (selling or msrp) and not v.get("price_expiration"):
            F.append(finding("C07", SEV_COMPLIANCE, url,
                "Used price shown with no price-expiration disclaimer", vin))

        # C08a — summary vs disclaimer mismatch (due-at-signing / payment figures)
        das = v.get("due_at_signing", [])
        if das and disc:
            disc_amounts = [float(x.replace(",", "")) for x in
                            re.findall(r"\$\s*([\d,]+\.\d{2}|[\d,]{4,})", disc)]
            for d in das:
                near = [a for a in disc_amounts if d and abs(a - d) / d < 0.15 and abs(a - d) > 1]
                if near and not any(abs(a - d) <= 1 for a in disc_amounts):
                    F.append(finding("C08", SEV_COMPLIANCE, url,
                        f"Due-at-signing mismatch: summary ${d:,.0f} vs disclaimer ${near[0]:,.2f}",
                        vin, disc[:400]))
        # C08b — absurdly long disclaimer (~40+ lines ≈ 35+ sentences)
        if v.get("disclaimer_line_est", 0) >= 35:
            F.append(finding("C08", SEV_HYGIENE, url,
                f"Disclaimer is extremely long (~{v['disclaimer_line_est']} sentences)", vin))

        # C09 — recompute lease payment when program data exists for this model
        key = f"{v.get('model_year')} {v.get('make')} {v.get('model')}".strip()
        prog = lease_programs.get(key)
        if prog and v.get("payments") and msrp:
            mf, res_pct, term = prog["money_factor"], prog["residual_pct"], prog["term"]
            cap = selling or msrp
            residual = msrp * res_pct
            base = (cap - residual) / term + (cap + residual) * mf
            shown = v["payments"][0]
            if abs(shown - base) > max(20, base * 0.03):
                F.append(finding("C09", SEV_DATA, url,
                    f"Lease payment variance: shown ${shown:,.0f} vs computed base ${base:,.0f} "
                    f"(mf={mf}, residual={res_pct:.0%}, {term}mo)", vin))

        # C10 — current-model new vehicle with no lease payment
        if cond == "NEW" and v.get("model_year") and int(v["model_year"]) >= TODAY.year \
                and not (v.get("has_lease_mention") and v.get("payments")):
            F.append(finding("C10", SEV_DATA, url,
                "Current-model new vehicle shows no lease payment (the payment feed may have dropped this trim)", vin))

        # C11 — aged inventory at MSRP / bogus savings
        fs = first_seen.get(vin) if vin else None
        age = (TODAY - datetime.date.fromisoformat(fs)).days if fs else None
        discount = labels.get("Mcpeeks Discount") or labels.get("Dealer Discount") or 0
        savings = labels.get("Total Savings") or 0
        if age and age > 90 and msrp and selling and selling >= msrp and cond == "NEW":
            F.append(finding("C11", SEV_DATA, url,
                f"Aged unit ({age}d tracked) still at/above MSRP with no discount", vin,
                f"msrp={msrp} selling={selling}"))
        if msrp and selling and savings and abs((msrp - selling) - (savings)) > max(50, 0.02 * msrp) \
                and abs((msrp - selling) - (discount + rebate_total)) > max(50, 0.02 * msrp):
            F.append(finding("C11", SEV_DATA, url,
                f"Savings math inconsistent: MSRP ${msrp:,.0f} − selling ${selling:,.0f} "
                f"≠ advertised savings ${savings:,.0f}", vin, f"labels={labels}"))

        # C12 — missing / placeholder photos
        if v.get("image_count", 0) <= 2:
            F.append(finding("C12", SEV_DATA, url,
                f"Few or no unit photos ({v.get('image_count', 0)} found)", vin))
        if v.get("placeholder_images"):
            F.append(finding("C12", SEV_DATA, url,
                "Vendor 'Image Coming Soon' graphic instead of a real photo", vin, str(v["placeholder_images"][:2])))

        # C13 — missing 360/spin media
        if not v.get("has_spin"):
            F.append(finding("C13", SEV_DATA, url,
                "No Impel/SpinCar 360 media detected", vin))

    # C15 — third-party script inventory (site-wide, incl. static pages)
    all_domains = {}
    for v in vehicles:
        for d in v.get("script_domains", []):
            all_domains[d] = all_domains.get(d, 0) + 1
    for p, pd in inv.get("pages", {}).items():
        for d in pd.get("script_domains", []):
            all_domains[d] = all_domains.get(d, 0) + 1
    unknown = sorted(d for d in all_domains
                     if approved and not any(a in d for a in approved))
    if unknown:
        F.append(finding("C15", SEV_HYGIENE, "site-wide",
            f"{len(unknown)} outside script {'domain' if len(unknown) == 1 else 'domains'} not on the approved-vendor list",
            None, ", ".join(unknown[:25])))
    prev_domains = set(load(os.path.join(args.state, "script_domains.json"), []))
    new_domains = sorted(set(all_domains) - prev_domains) if prev_domains else []
    if new_domains:
        F.append(finding("C15", SEV_HYGIENE, "site-wide",
            f"Script domains first seen this run: {', '.join(new_domains[:15])}"))
    gtm_ids = set()
    for p, pd in inv.get("pages", {}).items():
        gtm_ids |= set(re.findall(r"GTM-[A-Z0-9]{4,10}", pd.get("text", "")))
    if len(gtm_ids) > 1:
        F.append(finding("C15", SEV_HYGIENE, "site-wide",
            f"Multiple GTM containers detected: {sorted(gtm_ids)}"))

    # C21 — generic-number check: pages showing only one number
    dept_pages = {"/service": "Service", "/parts": "Parts", "/contact-us": "Contact"}
    all_site_phones = {}
    for p, pd in inv.get("pages", {}).items():
        for ph in pd.get("phones", []):
            all_site_phones.setdefault(ph, []).append(p)
        if p in dept_pages and len(pd.get("phones", [])) <= 1:
            F.append(finding("C21", SEV_HYGIENE, p,
                f"{dept_pages[p]} page shows {len(pd.get('phones', []))} phone numbers, "
                "verify department routing vs single generic number",
                None, str(pd.get("phones"))))
    for junk in ("123-456-7890", "999-999-9999", "000-000-0000"):
        if junk in all_site_phones:
            F.append(finding("C21", SEV_DATA, str(all_site_phones[junk]),
                f"Dummy phone number {junk} visible on page"))

    # update first_seen state
    for v in vehicles:
        if v.get("vin") and v["vin"] not in first_seen:
            first_seen[v["vin"]] = TODAY.isoformat()
    os.makedirs(args.state, exist_ok=True)
    with open(os.path.join(args.state, "first_seen.json"), "w") as f:
        json.dump(first_seen, f, indent=0)
    with open(os.path.join(args.state, "script_domains.json"), "w") as f:
        json.dump(sorted(all_domains), f)

    # summary + spot-check queue (what the model may look at)
    by_check = {}
    for x in F:
        by_check.setdefault(x["check"], []).append(x)
    out = {"generated": TODAY.isoformat(), "total_findings": len(F),
           "counts": {k: len(v) for k, v in sorted(by_check.items())},
           "phones_sitewide": {k: v for k, v in sorted(all_site_phones.items())},
           "vehicle_count": len(vehicles),
           "findings": F}
    with open(os.path.join(args.data, "findings.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out["counts"], indent=0))
    print(f"{len(F)} findings across {len(vehicles)} vehicles -> findings.json")


if __name__ == "__main__":
    main()
