#!/usr/bin/env python3
"""
fallback_crawl.py — server-side (curl/urllib) re-crawler.

When the browser JS extraction truncates a page or a check comes back
`unresolved`, this module re-fetches the raw server HTML and re-extracts using
the SAME field schema the browser JS produced. Because it pulls the full
response body (no 12K/15K browser cap), it resolves the single biggest source of
false positives: a disclaimer that was really there but got cut off.

Honesty rules:
  * Network failure / 4xx-5xx → return {"error": ...} so the gap is RECORDED,
    never silently resolved.
  * If the server HTML is suspiciously short (a JS-rendered SPA that ships almost
    no server markup), set `js_rendered_suspected: True`. The verify loop then
    keeps the item as needs_human_review instead of false-resolving it.

Python 3.9+, stdlib only (urllib, html.parser, re).
"""

import re
import json
import argparse
import urllib.request
import urllib.error
from html.parser import HTMLParser

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
JS_RENDER_MIN_CHARS = 1200  # below this, server HTML is too thin to trust

PRICE_RE = re.compile(r"\$[\d,]{3,}(?:\.\d{2})?(?:\s*(?:/mo|per\s*month))?", re.I)
PAYMENT_RE = re.compile(r"\$[\d,]+\s*(?:/mo|per\s*month|a\s*month)", re.I)
TERM_RE = re.compile(r"\d+\s*months?", re.I)
DISCLAIMER_HINT = re.compile(
    r"capitalized\s+cost|due\s+at\s+signing|lease\s+(?:payment|end)|monthly\s+payment|"
    r"mileage|disposition|acquisition\s+fee|residual|on\s+approved\s+credit|"
    r"not\s+all\s+customers|see\s+dealer|plus\s+(?:tax|government)|excludes?\s+tax|"
    r"apr|security\s+deposit|expires?|ends?\s+\w+\s+\d", re.I)


class _TextExtractor(HTMLParser):
    """Collect visible text and candidate disclaimer blocks from raw HTML."""
    SKIP = {"script", "style", "noscript", "svg", "head"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.chunks = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in ("p", "div", "li", "br", "section", "span", "td"):
            self.chunks.append("\n")

    def handle_data(self, data):
        # Title lives inside <head>, which is in SKIP — capture it BEFORE the
        # skip-depth guard, or every server-crawled page gets title == "".
        if self._in_title:
            self.title += data
            return
        if self._skip_depth > 0:
            return
        t = data.strip()
        if t:
            self.chunks.append(t + " ")

    def text(self):
        raw = "".join(self.chunks)
        # collapse runs of whitespace but keep paragraph breaks
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n\s*\n+", "\n", raw)
        return raw.strip()


def fetch_html(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "text/html,application/xhtml+xml"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        body = resp.read()
    return body.decode(charset, errors="replace")


def _disclaimer_lines(text):
    out = []
    for line in text.split("\n"):
        line = line.strip()
        if len(line) > 30 and DISCLAIMER_HINT.search(line):
            out.append(line[:800])
    # de-dup, keep order
    seen, uniq = set(), []
    for d in out:
        if d not in seen:
            seen.add(d)
            uniq.append(d)
    return uniq[:20]


def extract(page_key, url, html):
    """Re-extract a page into the browser-JS field schema (full, uncapped)."""
    parser = _TextExtractor()
    parser.feed(html)
    text = parser.text()
    title = parser.title.strip()

    page = {
        "url": url,
        "title": title,
        "text_excerpt": text,            # NOT capped — this is the point
        "page_text_excerpt": text,
        "disclaimers": _disclaimer_lines(text),
        "prices_found": list(dict.fromkeys(PRICE_RE.findall(text)))[:20],
        "lease_payments": list(dict.fromkeys(PAYMENT_RE.findall(text)))[:10],
        "lease_terms": list(dict.fromkeys(TERM_RE.findall(text)))[:10],
        "has_lease_offers": bool(re.search(r"\blease\b|\bper\s*month\b|/mo", text, re.I)),
        "has_cpo_section": bool(re.search(r"certified\s+pre-?owned|\bcpo\b", text, re.I)),
        "has_carfax": bool(re.search(r"carfax|autocheck", text, re.I)),
        "source": "fallback_crawl",
        "char_count": len(text),
    }
    if len(text) < JS_RENDER_MIN_CHARS:
        page["js_rendered_suspected"] = True
    return page


def recrawl(page_key, url, timeout=20):
    """Fetch + extract one page. On any failure, return an error dict (recorded gap)."""
    if not url:
        return {"error": "no_url_for_fallback", "source": "fallback_crawl"}
    try:
        html = fetch_html(url, timeout=timeout)
    except urllib.error.HTTPError as e:
        return {"error": "http_%s" % e.code, "url": url, "source": "fallback_crawl"}
    except urllib.error.URLError as e:
        return {"error": "url_error:%s" % e.reason, "url": url, "source": "fallback_crawl"}
    except Exception as e:  # timeout, ssl, decode, etc.
        return {"error": "fetch_failed:%s" % e, "url": url, "source": "fallback_crawl"}
    return extract(page_key, url, html)


def main():
    ap = argparse.ArgumentParser(description="Server-side fallback re-crawler")
    ap.add_argument("--url", required=True)
    ap.add_argument("--page", default="homepage")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    page = recrawl(args.page, args.url)
    out = json.dumps(page, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out)
        print("wrote", args.out, "(%d chars text)" % page.get("char_count", 0))
    else:
        print(out[:2000])


if __name__ == "__main__":
    main()
