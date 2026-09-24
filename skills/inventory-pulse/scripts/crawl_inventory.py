#!/usr/bin/env python3
"""DigitalCLIQ Inventory Pulse: polite, platform-agnostic VDP crawler + extractor.

Two modes:
  1. Fetch mode:   --urls urls.txt --out DIR     (fetch each URL, save HTML, extract)
  2. Extract mode: --html-dir DIR --out DIR      (extract from HTML already saved,
                                                  e.g. pages fetched via a browser fallback)

Extraction is JSON-LD first (schema.org Vehicle/Car/Product), regex fallback second.
All HTML is html.unescape()d before parsing (handles &dollar; entity prices, the
Pixel Motion quirk). Output: <out>/inventory.json rows + <out>/fetch_log.json.

Politeness is a hard rule (2026-07-26 lesson: a 10-worker crawl coincided with a
production site outage): max 3 workers, default 0.7s pacing per worker, circuit
breaker stops the run if the site starts refusing.
Exit codes: 0 ok, 2 = >20% fetch failures (use multi-strategy fallback),
3 = circuit breaker tripped (site down or refusing: STOP, tell Drew).
"""
import argparse, html, json, os, re, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")
PRICE_LABEL_RE = re.compile(
    r"(msrp|retail price|selling price|sale price|internet price|e-?price|our price|final price)"
    r"[^$\d]{0,80}\$?\s*([\d]{2,3}[,.]?\d{3})", re.I)
CALL_FOR_PRICE_RE = re.compile(r"call\s*(us\s*)?for\s*(best\s*)?(price|pricing|availability)", re.I)


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", errors="replace")


def iter_jsonld(page):
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S | re.I):
        raw = m.group(1).strip()
        try:
            data = json.loads(raw)
        except Exception:
            try:
                data = json.loads(re.sub(r",\s*([}\]])", r"\1", raw))
            except Exception:
                continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node); continue
            if not isinstance(node, dict):
                continue
            if "@graph" in node:
                stack.extend(node["@graph"] if isinstance(node["@graph"], list) else [node["@graph"]])
            t = node.get("@type", "")
            types = [t] if isinstance(t, str) else list(t)
            if any(x in ("Vehicle", "Car", "Motorcycle", "Product") for x in types):
                yield node


def num(v):
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return int(round(float(v)))
    s = re.sub(r"[^\d.]", "", str(v))
    try:
        return int(round(float(s))) if s else 0
    except Exception:
        return 0


def extract_vehicle(page_html, url):
    """Return a vehicle row dict or None. JSON-LD first, regex fallback."""
    page = html.unescape(page_html)
    row = {"vin": "", "yr": 0, "make": "", "model": "", "trim": "", "version": "",
           "msrp": 0, "price": 0, "call_for_price": 0, "condition": "",
           "dom_displayed": 0, "vdp_url": url, "extract_method": ""}
    for node in iter_jsonld(page):
        vin = node.get("vehicleIdentificationNumber") or node.get("vin") or ""
        offers = node.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        price = num(offers.get("price")) if isinstance(offers, dict) else 0
        if not (vin or price):
            continue
        row.update({
            "vin": str(vin).strip().upper(),
            "yr": num(node.get("vehicleModelDate") or node.get("modelDate") or node.get("productionDate")),
            "make": (node.get("brand", {}) or {}).get("name", "") if isinstance(node.get("brand"), dict) else str(node.get("brand") or node.get("manufacturer") or ""),
            "model": str(node.get("model") or ""),
            "trim": str(node.get("vehicleConfiguration") or node.get("trim") or ""),
            "price": price,
            "condition": str(node.get("itemCondition") or "").split("/")[-1].replace("Condition", ""),
            "extract_method": "jsonld",
        })
        name = str(node.get("name") or "")
        if name:
            row["version"] = name
            if not row["yr"]:
                ym = re.match(r"(20\d{2})", name)
                if ym:
                    row["yr"] = int(ym.group(1))
        break
    # Regex fallback / enrichment against page text
    if not row["vin"]:
        vm = VIN_RE.search(url) or VIN_RE.search(page)
        if vm:
            row["vin"] = vm.group(1).upper()
            row["extract_method"] = row["extract_method"] or "regex"
    labels = {lbl.lower(): num(val) for lbl, val in PRICE_LABEL_RE.findall(page)}
    for k, v in labels.items():
        if "msrp" in k or "retail" in k:
            row["msrp"] = max(row["msrp"], v)
    if not row["price"]:
        for k, v in labels.items():
            if "msrp" not in k and "retail" not in k:
                row["price"] = v
                row["extract_method"] = row["extract_method"] or "regex"
                break
    if not row["price"] and CALL_FOR_PRICE_RE.search(page):
        row["call_for_price"] = 1
        row["extract_method"] = row["extract_method"] or "regex"
    if not row["msrp"] and row["price"]:
        row["msrp"] = 0  # unknown, never fabricate
    dm = re.search(r"(\d{1,3})\s*days?\s*(on\s*(the\s*)?(lot|market)|in\s*stock)", page, re.I)
    if dm:
        row["dom_displayed"] = int(dm.group(1))
    return row if (row["vin"] or row["price"] or row["call_for_price"]) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls", help="file with one VDP URL per line (fetch mode)")
    ap.add_argument("--html-dir", help="directory of saved .html files (extract mode)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dealer", default="", help="dealer name stamped on every row")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--pace", type=float, default=0.7)
    args = ap.parse_args()
    if args.workers > 4:
        print("Refusing >4 workers (crawl politeness is a hard rule).", file=sys.stderr)
        sys.exit(1)
    os.makedirs(args.out, exist_ok=True)
    html_dir = os.path.join(args.out, "html")
    os.makedirs(html_dir, exist_ok=True)

    rows, log = [], {"fetched": 0, "failed": 0, "extracted": 0, "failures": []}

    if args.html_dir:
        for fn in sorted(os.listdir(args.html_dir)):
            if not fn.endswith(".html"):
                continue
            with open(os.path.join(args.html_dir, fn), encoding="utf-8", errors="replace") as f:
                row = extract_vehicle(f.read(), fn)
            if row:
                row["dealer"] = args.dealer
                rows.append(row)
        log["extracted"] = len(rows)
    else:
        if not args.urls:
            ap.error("need --urls or --html-dir")
        with open(args.urls) as f:
            urls = [u.strip() for u in f if u.strip().startswith("http")]
        consecutive_fail = 0
        stop = False

        def job(i, url):
            time.sleep(args.pace * (i % args.workers))
            try:
                status, body = fetch(url)
                return url, status, body, None
            except Exception as e:
                return url, 0, "", str(e)

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {}
            for i, url in enumerate(urls):
                if stop:
                    break
                futures[ex.submit(job, i, url)] = url
                time.sleep(args.pace / args.workers)
                done = [f for f in list(futures) if f.done()]
                for f in done:
                    url2, status, body, err = f.result()
                    futures.pop(f)
                    if err or status >= 400:
                        log["failed"] += 1
                        consecutive_fail += 1
                        log["failures"].append({"url": url2, "status": status, "err": err or ""})
                        if consecutive_fail >= 10:
                            stop = True
                    else:
                        consecutive_fail = 0
                        log["fetched"] += 1
                        fn = re.sub(r"[^A-Za-z0-9]+", "_", url2)[-120:] + ".html"
                        with open(os.path.join(html_dir, fn), "w", encoding="utf-8") as fh:
                            fh.write(body)
                        row = extract_vehicle(body, url2)
                        if row:
                            row["dealer"] = args.dealer
                            rows.append(row)
            for f in as_completed(list(futures)):
                url2, status, body, err = f.result()
                if err or status >= 400:
                    log["failed"] += 1
                    log["failures"].append({"url": url2, "status": status, "err": err or ""})
                else:
                    log["fetched"] += 1
                    row = extract_vehicle(body, url2)
                    if row:
                        row["dealer"] = args.dealer
                        rows.append(row)
        log["extracted"] = len(rows)
        if stop:
            json.dump(log, open(os.path.join(args.out, "fetch_log.json"), "w"), indent=1)
            print("CIRCUIT BREAKER: 10 consecutive failures. Site may be down or refusing. STOP.", file=sys.stderr)
            sys.exit(3)

    # Dedup by VIN (keep the row with more data)
    by_vin = {}
    for r in rows:
        k = r["vin"] or r["vdp_url"]
        if k not in by_vin or (r["price"] or r["msrp"]) and not (by_vin[k]["price"] or by_vin[k]["msrp"]):
            by_vin[k] = r
    rows = list(by_vin.values())

    json.dump(rows, open(os.path.join(args.out, "inventory.json"), "w"), indent=1)
    json.dump(log, open(os.path.join(args.out, "fetch_log.json"), "w"), indent=1)
    total = log["fetched"] + log["failed"]
    print(f"dealer={args.dealer!r} fetched={log['fetched']} failed={log['failed']} vehicles={len(rows)}")
    if total and log["failed"] / total > 0.2:
        print(">20% fetch failures: run the multi-strategy fallback for the failing pages.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
