#!/usr/bin/env python3
"""Site health: SSL validity (every domain + www variant), redirect chains,
and Google Lighthouse scores. Pure CLI — zero model tokens.

Usage:
  python3 sitehealth.py --skill SKILL_DIR --data DATA_DIR [--skip-lighthouse]
"""
import argparse, datetime, json, os, socket, ssl, subprocess, sys, urllib.request

CANONICAL = "www.mcpeeks.com"
LH_PAGES = ["https://www.mcpeeks.com/",
            "https://www.mcpeeks.com/inventory/new",
            None]  # third slot filled with a live VDP from inventory.json


def ssl_check(host):
    out = {"host": host}
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=12) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as s:
                cert = s.getpeercert()
        exp = datetime.datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
        out.update(valid=True, expires=exp.strftime("%Y-%m-%d"),
                   days_left=(exp - datetime.datetime.utcnow()).days,
                   issuer=dict(x[0] for x in cert.get("issuer", ())).get("organizationName"))
        if out["days_left"] < 21:
            out["flag"] = f"expires in {out['days_left']} days"
    except ssl.SSLCertVerificationError as e:
        out.update(valid=False, flag=f"SSL INVALID: {e.verify_message if hasattr(e, 'verify_message') else e}")
    except Exception as e:
        out.update(valid=False, flag=f"unreachable: {type(e).__name__} {e}")
    return out


def redirect_chain(domain, max_hops=6):
    url, chain = f"https://{domain}/", []
    seen = set()
    for _ in range(max_hops):
        if url in seen:
            chain.append("LOOP"); break
        seen.add(url)
        req = urllib.request.Request(url, method="HEAD",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh) Chrome/126.0"})
        try:
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *a, **k): return None
            opener = urllib.request.build_opener(NoRedirect)
            with opener.open(req, timeout=15) as r:
                chain.append(f"{r.status} {url}")
                return {"domain": domain, "chain": chain, "final": url,
                        "hops": len(chain) - 1,
                        "ok": CANONICAL in url,
                        "flag": None if CANONICAL in url and len(chain) <= 3
                                else ("wrong destination" if CANONICAL not in url
                                      else f"long chain ({len(chain)-1} hops)")}
        except urllib.error.HTTPError as e:
            if e.status in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                loc = e.headers["Location"]
                if loc.startswith("/"):
                    loc = url.rstrip("/") + loc
                chain.append(f"{e.status} {url} ->")
                url = loc
                continue
            return {"domain": domain, "chain": chain + [f"{e.status} {url}"],
                    "final": url, "ok": False, "flag": f"HTTP {e.status}"}
        except Exception as e:
            return {"domain": domain, "chain": chain, "final": url, "ok": False,
                    "flag": f"DEAD END: {type(e).__name__}"}
    return {"domain": domain, "chain": chain, "final": url, "ok": False,
            "flag": "redirect chain too long / loop"}


def lighthouse(url):
    try:
        r = subprocess.run(
            ["npx", "--yes", "lighthouse", url, "--output=json", "--quiet",
             "--chrome-flags=--headless=new --no-sandbox",
             "--only-categories=performance,accessibility,best-practices,seo"],
            capture_output=True, text=True, timeout=300)
        data = json.loads(r.stdout[r.stdout.index("{"):]) if "{" in r.stdout else None
        if not data:
            return {"url": url, "error": (r.stderr or "no output")[-300:]}
        cats = data.get("categories", {})
        return {"url": url,
                **{k: round((v.get("score") or 0) * 100) for k, v in cats.items()},
                "lcp_s": round(data["audits"]["largest-contentful-paint"]["numericValue"] / 1000, 1)
                         if "largest-contentful-paint" in data.get("audits", {}) else None}
    except Exception as e:
        return {"url": url, "error": f"{type(e).__name__}: {e}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--skip-lighthouse", action="store_true")
    args = ap.parse_args()

    domains = []
    with open(os.path.join(args.skill, "config", "domains.txt")) as f:
        for line in f:
            d = line.strip().lower()
            if d and not d.startswith("#"):
                domains.append(d)
                if not d.startswith("www."):
                    domains.append("www." + d)
    domains = list(dict.fromkeys(domains))

    print(f"SSL + redirects for {len(domains)} hosts...")
    ssl_results = [ssl_check(d) for d in domains]
    redir_results = [redirect_chain(d) for d in domains]

    lh_results = []
    if not args.skip_lighthouse:
        pages = list(LH_PAGES)
        try:
            inv = json.load(open(os.path.join(args.data, "inventory.json")))
            pages[2] = inv["vehicles"][0]["url"]
        except Exception:
            pages = [p for p in pages if p]
        for p in pages:
            if p:
                print(f"lighthouse: {p}")
                lh_results.append(lighthouse(p))

    out = {"ssl": ssl_results, "redirects": redir_results, "lighthouse": lh_results,
           "flags": [r for r in ssl_results + redir_results if r.get("flag")]}
    with open(os.path.join(args.data, "sitehealth.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(f"{len(out['flags'])} site-health flags -> sitehealth.json")


if __name__ == "__main__":
    main()
