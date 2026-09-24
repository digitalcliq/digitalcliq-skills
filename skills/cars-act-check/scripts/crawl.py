#!/usr/bin/env python3
"""cars-act-check incremental crawler.

Token-slim by design: incremental via content hashing. Only pages whose
body hash changed since the last run (plus new URLs and a rotating 10%
re-verify sample) are re-extracted and re-checked. Model never reads
raw HTML; this script writes compact page extracts to pages.jsonl.

Exit codes: 0 ok, 2 = >20% fetch failures (site up), 3 = circuit breaker
(site down / refusing). Politeness is a hard rule: 3 workers, 0.7s pacing.
"""
import argparse, concurrent.futures, hashlib, json, os, random, re, sys, time
import urllib.request, urllib.error
from html.parser import HTMLParser

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
PACING = 0.7
WORKERS = 3  # NEVER raise above 4 (production-outage lesson, 2026-07-26)

def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()

def discover_sitemaps(domain):
    base = f"https://{domain}".rstrip("/")
    candidates = [f"{base}/sitemap.xml", f"{base}/sitemap_index.xml",
                  f"{base}/inventory-sitemap.xml"]
    try:
        _, robots = fetch(f"{base}/robots.txt")
        candidates = re.findall(rb"(?i)sitemap:\s*(\S+)", robots) and \
            [m.decode() for m in re.findall(rb"(?i)sitemap:\s*(\S+)", robots)] + candidates or candidates
    except Exception:
        pass
    urls, seen = [], set()
    for sm in candidates:
        if sm in seen:
            continue
        seen.add(sm)
        try:
            _, body = fetch(sm)
        except Exception:
            continue
        locs = re.findall(rb"<loc>\s*([^<\s]+)\s*</loc>", body)
        for loc in locs:
            u = loc.decode()
            if u.endswith(".xml") and u not in seen:
                candidates.append(u)
            elif not u.endswith(".xml"):
                urls.append(u)
    # Always include key non-sitemap surfaces
    for path in ["/", "/specials", "/new-specials", "/used-specials",
                 "/lease-specials", "/finance", "/financing", "/espanol"]:
        urls.append(base + path)
    return sorted(set(urls))

class TextExtract(HTMLParser):
    SKIP = {"script", "style", "noscript"}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self.chunks = []
        self.jsonld = []
        self._in_jsonld = False
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script" and a.get("type") == "application/ld+json":
            self._in_jsonld = True
        elif tag in self.SKIP:
            self._skip += 1
    def handle_endtag(self, tag):
        if tag == "script" and self._in_jsonld:
            self._in_jsonld = False
        elif tag in self.SKIP and self._skip:
            self._skip -= 1
    def handle_data(self, data):
        if self._in_jsonld:
            self.jsonld.append(data)
        elif not self._skip:
            t = data.strip()
            if t:
                self.chunks.append(t)

def extract(url, html_bytes):
    html = html_bytes.decode("utf-8", "replace")
    p = TextExtract()
    try:
        p.feed(html)
    except Exception:
        pass
    text = " \n".join(p.chunks)
    vehicles = []
    for blob in p.jsonld:
        try:
            data = json.loads(blob)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            if isinstance(it, dict) and it.get("@type") in ("Vehicle", "Car", "Product"):
                offers = it.get("offers") or {}
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                vehicles.append({
                    "vin": it.get("vehicleIdentificationNumber") or it.get("sku"),
                    "name": it.get("name"),
                    "price": offers.get("price"),
                    "availability": offers.get("availability"),
                    "condition": it.get("itemCondition"),
                })
    return {"url": url, "text": text[:20000], "jsonld_vehicles": vehicles,
            "has_jsonld": bool(vehicles)}

def classify(url):
    u = url.lower()
    if re.search(r"/(inventory|vehicle|vdp)/|/(new|used|certified)[-/].*\d{4}", u):
        return "vdp"
    if re.search(r"special|offers|deals|lease|incentive", u):
        return "specials"
    if re.search(r"finance|financing|credit|pre[-]?approv", u):
        return "finance"
    if re.search(r"search|inventory\b|/new-vehicles|/used-vehicles|/used-cars|/new-cars", u):
        return "srp"
    return "page"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--full", action="store_true", help="ignore hash cache")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.state, exist_ok=True)
    cache_path = os.path.join(args.state, "hashcache.json")
    cache = {}
    if os.path.exists(cache_path) and not args.full:
        cache = json.load(open(cache_path))

    urls = discover_sitemaps(args.domain)
    if not urls:
        print("FATAL: no URLs discovered (no sitemap?)"); sys.exit(3)

    resample = set(random.Random(time.strftime("%Y%W")).sample(
        urls, max(1, len(urls) // 10)))
    fails, down_streak = 0, 0
    pages, new_cache, all_urls_status = [], dict(cache), {}
    lock = __import__("threading").Lock()

    def work(url):
        nonlocal fails, down_streak
        time.sleep(PACING)
        try:
            status, body = fetch(url)
            with lock:
                down_streak = 0
                all_urls_status[url] = status
        except urllib.error.HTTPError as e:
            with lock:
                fails += 1; all_urls_status[url] = e.code
            return
        except Exception:
            with lock:
                fails += 1; down_streak += 1; all_urls_status[url] = 0
            return
        h = hashlib.sha256(body).hexdigest()[:16]
        changed = cache.get(url) != h
        with lock:
            new_cache[url] = h
        if changed or url in resample:
            page = extract(url, body)
            page["type"] = classify(url)
            page["changed"] = changed
            with lock:
                pages.append(page)

    with concurrent.futures.ThreadPoolExecutor(WORKERS) as ex:
        for i, _ in enumerate(ex.map(work, urls)):
            if down_streak >= 8:
                print("CIRCUIT BREAKER: site refusing connections. STOPPING.")
                sys.exit(3)

    with open(os.path.join(args.out, "pages.jsonl"), "w") as f:
        for p in pages:
            f.write(json.dumps(p) + "\n")
    json.dump(new_cache, open(cache_path, "w"))
    json.dump(all_urls_status, open(os.path.join(args.out, "url_status.json"), "w"))
    total, checked = len(urls), len(pages)
    print(f"URLs discovered: {total} | fetched-for-check: {checked} "
          f"({checked*100//max(total,1)}%) | fetch failures: {fails}")
    if fails > total * 0.2:
        print("WARN: >20% fetch failures, see SKILL.md fallback"); sys.exit(2)

if __name__ == "__main__":
    main()
