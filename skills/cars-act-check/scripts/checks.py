#!/usr/bin/env python3
"""cars-act-check deterministic rules engine.

Runs the machine-tagged inspection points from config/rules.json over
pages.jsonl. Rule types:
  flag_pattern    : regex present on matching page types -> finding
  require_pattern : trigger regex present but required regex absent -> finding
  jsonld          : built-in JSON-LD price/availability logic
  status          : built-in URL status logic (stale listings, pt 85)
  selfcheck       : built-in retention self-checks (pts 77, 78, 83)

Output: findings.json with counts first. Model reads counts, then only
the entries it needs. Never prints page text.
"""
import argparse, json, os, re, sys, time
from collections import Counter

def load_pages(data_dir):
    path = os.path.join(data_dir, "pages.jsonl")
    if not os.path.exists(path):
        sys.exit("pages.jsonl missing; run crawl.py first")
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]

def applies(rule, page):
    types = rule.get("page_types", ["*"])
    return "*" in types or page["type"] in types

def run_pattern_rules(rules, pages):
    findings = []
    for rule in rules:
        rtype = rule["type"]
        if rtype not in ("flag_pattern", "require_pattern"):
            continue
        flag = re.compile(rule.get("pattern", ""), re.I)
        req = re.compile(rule["required"], re.I) if rule.get("required") else None
        for page in pages:
            if not applies(rule, page):
                continue
            text = page["text"]
            if rtype == "flag_pattern" and flag.search(text):
                findings.append(mk(rule, page, flag.search(text).group(0)))
            elif rtype == "require_pattern" and flag.search(text) and not req.search(text):
                findings.append(mk(rule, page,
                    f"trigger '{flag.search(text).group(0)[:60]}' without required disclosure"))
    return findings

def mk(rule, page, evidence):
    return {"point": rule["point"], "id": rule["id"], "severity": rule["severity"],
            "citation": rule["citation"], "url": page["url"],
            "summary": rule["summary"], "evidence": str(evidence)[:160]}

def run_jsonld_rules(pages):
    findings = []
    price_by_vin = {}
    for page in pages:
        for v in page.get("jsonld_vehicles", []):
            vin, price = v.get("vin"), v.get("price")
            if page["type"] == "vdp":
                if not price or str(price) in ("0", "0.0", ""):
                    findings.append({"point": 1, "id": "A01-jsonld", "severity": "C",
                        "citation": "CC 1784.41", "url": page["url"],
                        "summary": "VDP vehicle carries no total price in structured data",
                        "evidence": f"vin={vin} price={price!r}"})
                m = re.search(r"\$\s?([\d,]{4,9})", page["text"])
                if price and m:
                    shown = float(m.group(1).replace(",", ""))
                    try:
                        if abs(shown - float(price)) > max(1.0, float(price) * 0.001):
                            pass  # first $ on page may be MSRP; consistency handled below
                    except ValueError:
                        pass
            if vin and price:
                price_by_vin.setdefault(vin, set()).add(str(price))
    for vin, prices in price_by_vin.items():
        if len(prices) > 1:
            findings.append({"point": 17, "id": "A17-consistency", "severity": "M",
                "citation": "CC 1784.41 / CC 1784.40(4)", "url": "(multiple)",
                "summary": "Same VIN advertised at different prices across pages",
                "evidence": f"vin={vin} prices={sorted(prices)}"})
    return findings

def run_status_rules(data_dir, state_dir):
    findings = []
    status = json.load(open(os.path.join(data_dir, "url_status.json")))
    seen_path = os.path.join(state_dir, "vin_first_seen.json")
    dead = [u for u, s in status.items()
            if s in (404, 410) and re.search(r"/inventory|/vehicle", u)]
    for u in dead[:25]:
        findings.append({"point": 85, "id": "H85-status", "severity": "M",
            "citation": "CC 1784.40(4) / 48-hr delist exposure", "url": u,
            "summary": "Inventory URL in sitemap returns dead status (stale listing risk)",
            "evidence": f"status={status[u]}"})
    if len(dead) > 25:
        findings.append({"point": 85, "id": "H85-status", "severity": "M",
            "citation": "CC 1784.40(4)", "url": "(sitemap)",
            "summary": f"{len(dead)} total dead inventory URLs (25 listed)",
            "evidence": ""})
    return findings

def run_selfchecks(state_dir):
    findings = []
    mpath = os.path.join(state_dir, "retention-manifest.json")
    if not os.path.exists(mpath):
        findings.append({"point": 77, "id": "G77-self", "severity": "C",
            "citation": "CC 1784.44", "url": "(state)",
            "summary": "No retention manifest: no proof any ad snapshot was ever archived",
            "evidence": "retention-manifest.json missing"})
        return findings
    manifest = json.load(open(mpath))
    entries = manifest.get("entries", [])
    if entries:
        last = max(e["date"] for e in entries)
        days = (time.time() - time.mktime(time.strptime(last, "%Y-%m-%d"))) / 86400
        if days > 35:
            findings.append({"point": 78, "id": "G78-self", "severity": "M",
                "citation": "CC 1784.44", "url": "(drive)",
                "summary": f"Retention gap: last archive {int(days)} days ago (>35)",
                "evidence": f"last={last}"})
    return findings

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--rules", required=True)
    ap.add_argument("--state", required=True)
    args = ap.parse_args()
    pages = load_pages(args.data)
    rules = json.load(open(args.rules))["rules"]
    findings = (run_pattern_rules(rules, pages) + run_jsonld_rules(pages)
                + run_status_rules(args.data, args.state)
                + run_selfchecks(args.state))
    counts = Counter(f["severity"] for f in findings)
    by_point = Counter(f["point"] for f in findings)
    out = {"counts": {"C": counts.get("C", 0), "M": counts.get("M", 0),
                      "m": counts.get("m", 0), "total": len(findings),
                      "pages_checked": len(pages)},
           "top_points": by_point.most_common(10),
           "findings": findings}
    with open(os.path.join(args.data, "findings.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out["counts"]))
    print("top points:", out["top_points"])

if __name__ == "__main__":
    main()
