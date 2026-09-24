#!/usr/bin/env python3
"""DigitalCLIQ Inventory Pulse: server-side page fetcher + site prober.

Use this instead of writing ad-hoc probe/fetch code in-session.
curl is blocked in the Bash sandbox and the `timeout` CLI is not installed;
this script uses urllib with hard socket timeouts, which works.

Modes:
  --probe URL            quick verdict: can this site be server-fetched, and
                         which sitemap paths exist? Prints one JSON line.
  --urls FILE --out DIR  fetch each URL (sequential, 0.7s pacing, circuit
                         breaker), save HTML to DIR/html/. Prints one summary
                         line. Exit 3 = circuit breaker (site refusing).

Politeness is a hard rule: sequential, 0.7s between requests, breaker at 8
consecutive failures. (2026-07-26 lesson: an impolite crawl coincided with a
production site outage.)
"""
import argparse, json, os, re, socket, sys, time, urllib.request, urllib.error

UA = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
      "Accept-Language": "en-US"}
SITEMAP_PATHS = ["/inventory-sitemap.xml", "/sitemap.xml", "/sitemap_index.xml", "/dealer-sitemap.xml"]


def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace"), ""
    except urllib.error.HTTPError as e:
        return e.code, "", f"HTTP {e.code}"
    except Exception as e:
        return 0, "", f"{type(e).__name__}: {str(e)[:80]}"


def probe(base):
    base = base.rstrip("/")
    out = {"url": base, "server_fetch": False, "home_status": 0, "sitemaps": [], "errors": []}
    status, body, err = get(base + "/", timeout=15)
    out["home_status"] = status
    if err and status == 0:
        out["errors"].append(err)
    out["server_fetch"] = status == 200 and len(body) > 5000
    if out["server_fetch"]:
        for p in SITEMAP_PATHS:
            time.sleep(0.7)
            s, b, _ = get(base + p, timeout=15)
            if s == 200 and ("<urlset" in b or "<sitemapindex" in b):
                out["sitemaps"].append({"path": p, "urls": len(re.findall(r"<loc>", b))})
    print(json.dumps(out))
    return 0


def fetch_batch(urls_file, out_dir, pace, cap):
    os.makedirs(os.path.join(out_dir, "html"), exist_ok=True)
    with open(urls_file) as f:
        urls = [u.strip() for u in f if u.strip().startswith("http")][:cap]
    fetched = failed = consecutive = 0
    failures = []
    for url in urls:
        status, body, err = get(url)
        if err or status >= 400 or not body:
            failed += 1
            consecutive += 1
            failures.append({"url": url, "status": status, "err": err})
            if consecutive >= 8:
                json.dump({"fetched": fetched, "failed": failed, "failures": failures},
                          open(os.path.join(out_dir, "fetch_log.json"), "w"), indent=1)
                print("CIRCUIT BREAKER: 8 consecutive failures. STOP requests to this site.", file=sys.stderr)
                sys.exit(3)
        else:
            consecutive = 0
            fetched += 1
            fn = re.sub(r"[^A-Za-z0-9]+", "_", url)[-120:] + ".html"
            with open(os.path.join(out_dir, "html", fn), "w", encoding="utf-8") as fh:
                fh.write(body)
        time.sleep(pace)
    json.dump({"fetched": fetched, "failed": failed, "failures": failures},
              open(os.path.join(out_dir, "fetch_log.json"), "w"), indent=1)
    print(f"fetched={fetched} failed={failed} saved_to={out_dir}/html")
    return 0


def main():
    socket.setdefaulttimeout(25)
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", help="base site URL: print server-fetch verdict JSON")
    ap.add_argument("--urls", help="file of URLs to fetch")
    ap.add_argument("--out", help="output dir for fetch mode")
    ap.add_argument("--pace", type=float, default=0.7)
    ap.add_argument("--cap", type=int, default=160)
    args = ap.parse_args()
    if args.probe:
        sys.exit(probe(args.probe))
    if args.urls and args.out:
        sys.exit(fetch_batch(args.urls, args.out, args.pace, args.cap))
    ap.error("need --probe URL, or --urls FILE --out DIR")


if __name__ == "__main__":
    main()
