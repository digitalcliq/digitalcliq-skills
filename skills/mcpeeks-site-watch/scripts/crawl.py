#!/usr/bin/env python3
"""Sitemap-driven crawl of mcpeeks.com (Pixel Motion platform).

Fetches every VDP in inventory-sitemap.xml plus key static pages, extracts a
compact per-vehicle record (JSON-LD Vehicle + pricing box text + disclaimer +
payment text + media/script markers), and writes ONE inventory.json. Raw HTML
is discarded after extraction — nothing model-sized ever needs to be read.

Usage:
  python3 crawl.py --out DATA_DIR [--limit N] [--workers 3] [--delay 0.7]

POLITENESS IS MANDATORY. On 2026-07-26 a 10-worker full crawl coincided with
the origin (a single DigitalOcean box) refusing all connections — production
outage. Defaults are now 3 workers + 0.7s jittered delay per request
(~15-20 min for the full lot; that's fine, the run is unattended). A circuit
breaker aborts the whole crawl after 8 consecutive connection failures —
NEVER keep hitting a struggling server. Do not raise workers above 4.

Exit codes: 0 ok, 2 = failure rate >20% (escalate per multi-strategy fallback),
3 = circuit breaker tripped (site down/blocking — STOP, wait, alert Drew).
"""
import argparse, concurrent.futures, gzip, io, json, os, re, sys, time
import html as _ent
import urllib.request, urllib.error

BASE = "https://www.mcpeeks.com"
UA = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
      "Accept-Encoding": "gzip"}

KEY_PAGES = ["/", "/inventory/new", "/inventory/used", "/finance",
             "/contact-us", "/privacy-policy", "/service", "/parts"]

TRACKER_HINTS = re.compile(
    r"(googletagmanager|google-analytics|doubleclick|facebook|connect\.fb|tiktok|"
    r"clarity\.ms|foureyes|fullstory|hotjar|callrail|calltrackingmetrics|"
    r"spincar|impel|complyauto|adroll|criteo|bing|snapchat|pinterest)", re.I)

PLACEHOLDER_IMG = re.compile(
    r"(no[-_]?image|coming[-_]?soon|placeholder|default[-_]?vehicle|image[-_]?unavailable|"
    r"stock[-_]?photo|awaiting)", re.I)


def fetch(url, timeout=30, retries=2):
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.GzipFile(fileobj=io.BytesIO(body)).read()
                return r.status, r.geturl(), body.decode("utf-8", "replace")
        except Exception as e:
            if attempt == retries:
                return 0, url, f"ERROR: {e}"
            time.sleep(1.5 * (attempt + 1))


def strip_tags(html):
    html = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    html = _ent.unescape(html.replace("&colon;", ":"))  # &dollar; &minus; etc.
    html = html.replace("−", "-")  # unicode minus -> hyphen
    return re.sub(r"\s+", " ", html)


def window(text, needle, before=400, after=1600, flags=re.I):
    m = re.search(needle, text, flags)
    if not m:
        return ""
    return text[max(0, m.start() - before): m.end() + after]


def parse_money(s):
    try:
        return float(s.replace(",", "").replace("$", ""))
    except Exception:
        return None


def extract_vdp(url, html):
    rec = {"url": url}
    # --- JSON-LD Vehicle ---
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            d = json.loads(m.group(1))
        except Exception:
            continue
        if d.get("@type") == "Vehicle":
            offers = d.get("offers") or {}
            rec.update({
                "name": d.get("name"), "vin": d.get("vehicleIdentificationNumber"),
                "condition": (d.get("state_of_vehicle") or "").upper(),
                "model_year": d.get("modelDate"), "make": d.get("manufacturer"),
                "model": d.get("model"),
                "jsonld_price": offers.get("price"),
                "hero_image": d.get("image"),
                "description": (d.get("description") or "")[:1200],
            })
    text = strip_tags(html)

    # is the sticker price actually rendered anywhere on the page?
    jp = rec.get("jsonld_price")
    rec["price_displayed"] = bool(jp) and f"{jp:,.0f}" in text

    # --- pricing box: pick the MSRP/Selling Price window with the most $ signs
    # (avoids latching onto nav/footer mentions on pages with no pricing box) ---
    pbox, best = "", -1
    for m in re.finditer(r"(MSRP|Selling Price)", text, re.I):
        w = text[max(0, m.start() - 600): m.end() + 1800]
        score = w.count("$")
        if score > best:
            pbox, best = w, score
    rec["price_text"] = pbox[:2200]
    labels = {}
    for lm in re.finditer(
            r"(MSRP|McPeeks? Discount|Dealer Discount|Total Savings|Selling Price|"
            r"Sale Price|Net Price|Final Price|Market Value|Your Price|Internet Price)"
            r"\s*:?\s*[-+−]?\s*\$\s*([\d,]+)", pbox, re.I):
        labels.setdefault(lm.group(1).title(), parse_money(lm.group(2)))
    rec["price_labels"] = labels

    # --- rebates itemized in description/page ("$1000 - 2026 National Retail Bonus Cash . Exp. 08/03/2026") ---
    rebate_src = (rec.get("description") or "") + " " + window(text, r"Price includes", after=1200)
    rebates = []
    for rm in re.finditer(r"\$\s*([\d,]+)\s*[-–]\s*([^.$]{4,80}?)(?:\.\s*Exp\.?\s*([\d/]+))?(?=\s*\$|\s*$|\.)",
                          rebate_src):
        amt = parse_money(rm.group(1))
        if amt and amt >= 100:
            rebates.append({"amount": amt, "name": rm.group(2).strip()[:60], "exp": rm.group(3)})
    # dedupe
    seen = set(); rec["rebates"] = [r for r in rebates
                                    if not (k := (r["amount"], r["name"])) in seen and not seen.add(k)]

    # --- disclaimer text (CA fee disclaimer neighborhood) ---
    rec["disclaimer_text"] = window(text, r"government fees", before=300, after=2500)[:3000]
    rec["disclaimer_line_est"] = rec["disclaimer_text"].count(". ")  # sentence count proxy

    # --- payment text (lease/finance) ---
    pay = window(text, r"(/\s*mo\b|per month|due at signing|A month|/mo\.)", before=500, after=1500)
    rec["payment_text"] = pay[:2000]
    rec["payments"] = [parse_money(x) for x in re.findall(r"\$\s*([\d,]+(?:\.\d{2})?)\s*(?:/\s*mo|per month|A month)", text, re.I)][:4]
    rec["due_at_signing"] = [parse_money(x) for x in re.findall(r"\$\s*([\d,]+(?:\.\d{2})?)\s*(?:due at signing|due at lease signing)", text, re.I)][:4]
    rec["has_lease_mention"] = bool(re.search(r"\blease\b", pay, re.I))

    # --- media ---
    imgs = re.findall(r'https?://[^\s"\']+\.(?:jpg|jpeg|png|webp)', html, re.I)
    veh_imgs = [i for i in imgs if re.search(r"pixelmotion|inventoryphotos|photos?\.", i, re.I)] or imgs
    rec["image_count"] = len(set(veh_imgs))
    rec["placeholder_images"] = sorted({i for i in imgs if PLACEHOLDER_IMG.search(i)})[:5]
    rec["has_spin"] = bool(re.search(r"spincar|impel|spin360|data-spin", html, re.I))

    # --- scripts + phones + call-for-price ---
    rec["script_domains"] = sorted({re.sub(r"^www\.", "", m.group(1)).lower()
        for m in re.finditer(r'<script[^>]+src=["\']https?://([^/"\']+)', html, re.I)})
    rec["phones"] = sorted({f"{a}-{b}-{c}" for a, b, c in
        re.findall(r"\(?(\d{3})\)?[-. ](\d{3})[-. ](\d{4})", text)})
    rec["call_for_price"] = bool(re.search(r"call for (?:price|pricing)|contact (?:us )?for price", text, re.I))
    rec["price_expiration"] = bool(re.search(
        r"(price[sd]?\s+(?:is|are)?\s*(?:good|valid)|offer\s+(?:expires|good)|"
        r"end of business day|expires? at close of business)", text, re.I))
    rec["doc_fee_excluded_language"] = bool(re.search(
        r"(plus|excludes?|does not include)[^.]{0,120}(document(?:ation)? (?:processing )?(?:charge|fee)|doc fee)",
        text, re.I))
    # CNCDA CARS Act guidance flags (added 2026-09-14): C22 installed items excluded
    # from the price, C23 repealed two-day option wording, C24 MSRP-as-price wording.
    rec["installed_excluded_language"] = bool(re.search(
        r"(excludes?|does not include|not included in (?:the )?price)[^.]{0,80}"
        r"(dealer[\s-]*(?:installed|added)|installed (?:accessor|option|equipment|item|product)|accessor(?:y|ies)|add[\s-]*ons?|protection (?:package|product)|appearance package)"
        r"|(?:removed|remove) at (?:the )?customer'?s? (?:option|request)|purchased for an additional (?:cost|charge)"
        r"|does not apply to vehicles with dealer[\s-]*(?:added|installed)|pay or remove", text, re.I))
    rec["repealed_option_language"] = bool(re.search(
        r"contract cancellation option|cancellation option agreement|(?:two|2)[\s-]*day (?:contract )?(?:cancel|return)"
        r"|72[\s-]*hour (?:return|cancel|option)|\$\s?40,000|no cooling[\s-]*off period unless", text, re.I))
    rec["msrp_not_price_language"] = bool(re.search(
        r"msrp (?:is )?not (?:the )?(?:selling|advertised|sale|dealer'?s?|actual) price|price shown is (?:the )?msrp|msrp only\b",
        text, re.I))
    # FTC FAQ Q10 + FTC staff remarks 2026-09-30 (added 2026-10-08): C25 in-transit status.
    # "in transit" means already shipped; an unbuilt unit must carry its real status.
    rec["in_transit_language"] = bool(re.search(r"in[\s-]*transit|arriving soon|coming soon", text, re.I))
    rec["unbuilt_language"] = bool(re.search(
        r"in production|not yet (?:built|shipped|produced)|being built|factory[\s-]*order|build[\s-]*to[\s-]*order"
        r"|scheduled for production|awaiting production", text, re.I))
    rec["arrival_language"] = bool(re.search(
        r"(?:estimated|expected|est\.?)\s+(?:arrival|delivery)|\beta\b|arriv(?:es|ing) (?:on|by|in|the week)", text, re.I))
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--delay", type=float, default=0.7)
    args = ap.parse_args()
    args.workers = min(args.workers, 4)  # hard cap — see docstring
    os.makedirs(args.out, exist_ok=True)

    st, _, sm = fetch(BASE + "/inventory-sitemap.xml")
    if st != 200:
        print(f"FATAL: inventory sitemap HTTP {st}", file=sys.stderr); sys.exit(2)
    vdp_urls = sorted({u for u in re.findall(r"<loc>([^<]+)</loc>", sm)
                       if "/inventory/display/" in u})
    if args.limit:
        vdp_urls = vdp_urls[:args.limit]
    print(f"{len(vdp_urls)} VDPs to crawl")

    records, failures = [], []
    consec_fails = [0]  # circuit breaker across workers
    breaker = [False]

    def work(u):
        if breaker[0]:
            return ("skip", u, None)
        time.sleep(args.delay * (0.6 + 0.8 * (hash(u) % 100) / 100))  # jittered pacing
        s, final, body = fetch(u)
        if s != 200:
            consec_fails[0] += 1
            if s == 0 and consec_fails[0] >= 8:
                breaker[0] = True
            return ("fail", u, s)
        consec_fails[0] = 0
        return ("ok", u, extract_vdp(final, body))

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, res in enumerate(ex.map(work, vdp_urls)):
            if res[0] == "ok":
                records.append(res[2])
            elif res[0] == "fail":
                failures.append({"url": res[1], "status": res[2]})
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{len(vdp_urls)}", flush=True)
    if breaker[0]:
        print("CIRCUIT BREAKER: 8+ consecutive connection failures — site down or "
              "blocking. Crawl aborted; do NOT retry immediately.", file=sys.stderr)
        sys.exit(3)

    # key static pages: keep stripped text + script inventory only
    pages = {}
    for p in KEY_PAGES:
        s, final, body = fetch(BASE + p)
        if s == 200:
            pages[p] = {
                "final_url": final,
                "text": strip_tags(body)[:6000],
                "script_domains": sorted({re.sub(r"^www\.", "", m.group(1)).lower()
                    for m in re.finditer(r'<script[^>]+src=["\']https?://([^/"\']+)', body, re.I)}),
                "phones": sorted({f"{a}-{b}-{c}" for a, b, c in
                    re.findall(r"\(?(\d{3})\)?[-. ](\d{3})[-. ](\d{4})", strip_tags(body))}),
                "trackers_in_html": sorted(set(TRACKER_HINTS.findall(body))),
            }
        else:
            failures.append({"url": BASE + p, "status": s})

    out = {"crawled_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "vdp_count": len(records), "failures": failures,
           "vehicles": records, "pages": pages}
    with open(os.path.join(args.out, "inventory.json"), "w") as f:
        json.dump(out, f, indent=1)
    fail_rate = len(failures) / max(1, len(vdp_urls) + len(KEY_PAGES))
    print(f"done: {len(records)} records, {len(failures)} failures ({fail_rate:.0%})")
    if fail_rate > 0.2:
        print("HIGH FAILURE RATE — escalate to browser-based crawl (see SKILL.md fallback)", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
