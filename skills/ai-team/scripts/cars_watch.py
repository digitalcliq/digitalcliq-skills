#!/usr/bin/env python3
"""CARS Act website watch for the ai-team night shift. READ-ONLY, standard library only.

One store per run. Fetches the store's public website pages over plain HTTPS with the
cars-act-check skill's own crawler functions (same Chrome UA, 3 workers, 0.7 s pacing,
circuit breaker), runs that skill's machine rules (config/rules.json) plus two watch
rules, triages known false positives, collapses page-level hits into template-level
findings, diffs against the store's previous watch run, and prints a short summary.

It never edits the cars-act-check plugin, never writes to Projects/{CODE}/cars-act-state/
(the full /cars-act-check skill owns that), never uploads, posts, or alerts.
Wording rule: findings are "flagged for review", never "compliant" or "violation".

Usage (from the vault root, one plain command):
  python3 .claude/skills/ai-team/scripts/cars_watch.py --rotation
  python3 .claude/skills/ai-team/scripts/cars_watch.py --store NOI [--date 2026-09-23]
  python3 .claude/skills/ai-team/scripts/cars_watch.py --store SBMW --pages-file PATH   (browser extracts)
  python3 .claude/skills/ai-team/scripts/cars_watch.py --selftest

Options: --max-pages 400 (URL cap, key pages first), --budget-min 8 (wall clock for the
fetch phase, so one Bash call stays under 10 minutes), --vault-root (default: this
script's vault; also exported as DIGITALCLIQ_VAULT_ROOT), --skill-dir (default: newest
skills-plugin runtime copy of cars-act-check, then ~/Desktop/Skills source).

Output: outputs/ai-team/{date}/data/cars_{STORE}/ with run.json, url_status.json,
findings.json (raw), summary.json, summary.md.
Exit: 0 ok or nothing scheduled, 2 blocked / no usable pages, 3 circuit breaker, 1 error.
"""
import argparse
import concurrent.futures
import datetime as dt
import glob
import importlib.util
import json
import os
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
from collections import Counter

try:
    from zoneinfo import ZoneInfo
    PACIFIC = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover
    PACIFIC = None

OPERATIVE = "2026-10-01"

# Domains: SBMW, NCBMW, NOI from each client README's GA4 stream URL; CHC from
# Projects/CHC/context-log.md (the CHC README does not list a domain yet).
STORES = {
    "SBMW": "www.sterlingbmw.com",
    "NCBMW": "www.newcenturybmw.com",
    "NOI": "www.nissanofirvine.com",
    "CHC": "www.covinahillschevrolet.com",
}
# isoweekday of the shift date -> store. MCP is covered by mcpeeks-site-watch (Mon/Fri).
# SBMW returned Cloudflare 403 to plain HTTP on 2026-09-23; Monday's run then costs
# about ten refused requests and reports "blocked" until a browser run or an allowlist.
ROTATION = {1: "SBMW", 2: "NCBMW", 3: "NOI", 4: "CHC"}

KEY_PATHS = ["/", "/specials", "/new-specials", "/used-specials",
             "/lease-specials", "/finance", "/financing", "/espanol"]

# cars-act-check point id -> (vault rule ids, compliance-audit rule ids, short label)
RULE_MAP = {
    "A01-jsonld": ("CARS-ADV-01", "CA-CARS-001", "no total price in VDP structured data"),
    "A03": ("CARS-ADV-01", "CA-CARS-001", "call-for-price instead of a total price"),
    "A10": ("CARS-ADV-01", "CA-CARS-001", "vehicle-specific special without a labeled total price"),
    "A11": ("CARS-ADV-17", "CA-CARS-030", "payment or lease offer for an identified unit without its total price"),
    "A13": ("CARS-ADV-09", "CA-CARS-034", "offer without an expiration date"),
    "A14": ("CARS-ADV-13", "CA-PRICE-004", "single-vehicle offer without VIN or license"),
    "A17-consistency": ("CARS-ADV-13", "CA-CARS-033", "same VIN at different prices"),
    "B21": ("CARS-MIS-05", "CA-CARS-014", "financing guarantee claim"),
    "B22": ("L55 s.36", "CA-CARS-021", "trade-in guarantee claim"),
    "B24": ("L55 s.22", "CA-REGM-001", "payment offer not labeled lease or purchase"),
    "B27": ("CARS-MIS", "CA-CARS-010", "non-refundable deposit claim"),
    "B28": ("CARS-MIS-05", "CA-CARS-014", "approval-outcome promise"),
    "B31": ("CARS-MIS", "CA-CARS-010", "repossession claim"),
    "D43": ("CARS-DIS-02", "CA-CARS-003", "monthly payment without total amount paid"),
    "D44": ("CARS-DIS-04", "CA-CARS-004", "72 to 96 month term without extended-term disclosure"),
    "D46": ("L55 s.9", "CA-REGZ-002", "APR offer without credit qualification language"),
    "D47": ("L55 s.22", "CA-REGM-001", "lease payment without due-at-signing or mileage terms"),
    "D49": ("L55 s.9", "CA-REGZ-001", "0% financing without eligibility disclosure"),
    "D51": ("L55 s.37", "CA-SALE-002", "price or payment match claim"),
    "E53": ("CARS-DIS-01", "CA-CARS-002", "add-on marketed without optional-status statement"),
    "E55": ("CARS-ADD-01", "CA-CARS-015", "oil change marketed for an EV"),
    "E56": ("CARS-ADD-01", "CA-CARS-015", "nitrogen product without purity claim"),
    "F65": ("CARS-CAN", "CA-CARS-039", "pre-CARS 'no cooling-off' or repealed two-day option copy"),
    "F67": ("CARS-CAN-06", "CA-CARS-009", "3-day cancellation sold as a paid product"),
    "F68": ("CARS-CAN-03", "CA-CARS-007", "restocking fee without statutory limits"),
    "F72": ("CARS-CAN-06", "CA-CARS-020", "language waiving the cancellation right"),
    "G84": ("CARS-REC-01", "CA-CARS-019", "no written complaint intake path"),
    "H85-status": ("CARS-MIS-04", "CA-CARS-012", "dead inventory URL still in sitemap"),
    "H92": ("CARS-ADV-01", "CA-CARS-001", "possible $0-priced vehicle card"),
    "H97": ("CARS-ADV-26", "CA-DISC-004", "doc fee referenced without a stated amount"),
    "H100": ("CARS-MIS", "CA-CARS-040", "CARS Act described on site"),
    "I101": ("CARS-ADV-10", "CA-CARS-027", "price shown without the verbatim Plus Disclosure"),
    "I102": ("CARS-ADV-11", "CA-CARS-025", "MSRP in place of the total price"),
    "I103": ("CARS-ADV-12", "CA-CARS-026", "price gated behind a CTA"),
    "I104": ("CARS-ADV-20", "CA-CARS-029", "installed items excluded from the advertised price"),
    "I105": ("CARS-ADV-21", "CA-CARS-036", "addendum used for optional or $0 products"),
    "I106": ("CARS-ADV-19", "CA-CARS-028", "rebate presentation to verify"),
    "I107": ("CARS-ADD-05", "CA-CARS-038", "pre-installed device or product structure"),
    "I108": ("CARS-ADV-09", "CA-CARS-034", "priced offer with no expiration date"),
    "I109": ("CARS-ADV-14", "CA-CARS-033", "program or member pricing"),
    "I110": ("CARS-ADV-26", "CA-CARS-001", "'out-the-door' price label"),
    "W01": ("CARS-ADV-06", "CA-CARS-028 / FTC-PRICE-004", "advertised price says it includes rebates"),
    "W02": ("CARS-ADV-12", "CA-CARS-026", "price CTA on a vehicle page (verify the total price is shown first)"),
}

# Watch-only rules, same shape as config/rules.json entries (added 2026-09-23 after the NOI test).
WATCH_RULES = [
    {"point": 0, "id": "W01", "type": "flag_pattern", "severity": "C", "page_types": ["vdp", "srp", "specials"],
     "citation": "CC 1784.31(j)(3); CNCDA CARS-ADV-06; FTC Pricing FAQs Q5",
     "summary": "Advertised price is described as including rebates (no rebate may be deducted from total price)",
     "pattern": r"price\s+(includes?|reflects?)\s+[^.]{0,60}\b(rebates?|incentives?|customer\s+cash|bonus\s+cash)"},
    {"point": 0, "id": "W02", "type": "flag_pattern", "severity": "m", "page_types": ["vdp"],
     "citation": "CC 1784.41(a)(1); CNCDA CARS-ADV-12",
     "summary": "Price CTA on a vehicle page; fails only if the total price is not already displayed there",
     "pattern": r"(unlock|reveal|get)\s+(your|our|the)\s+(best\s+)?(price|e-?price)|get\s+e-?price"},
]

CHALLENGE_RE = re.compile(rb"<title>\s*(Just a moment|Attention Required|Access Denied|Pardon Our Interruption|"
                          rb"Request unsuccessful)", re.I)
BLOCK_CODES = (401, 403, 429, 503)


# ------------------------------------------------------------------ setup helpers

def pacific_today():
    now = dt.datetime.now(PACIFIC) if PACIFIC else dt.datetime.now()
    return now.date().isoformat()


def default_vault_root():
    env = os.environ.get("DIGITALCLIQ_VAULT_ROOT")
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", "..", ".."))


def find_skill_dir(explicit=None):
    cands = [explicit] if explicit else []
    runtime = glob.glob(os.path.expanduser(
        "~/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/*/*/skills/cars-act-check"))
    cands += sorted(runtime, key=os.path.getmtime, reverse=True)
    cands.append(os.path.expanduser("~/Desktop/Skills/skills/cars-act-check"))
    for c in cands:
        if c and os.path.isfile(os.path.join(c, "scripts", "crawl.py")) \
                and os.path.isfile(os.path.join(c, "scripts", "checks.py")) \
                and os.path.isfile(os.path.join(c, "config", "rules.json")):
            return c
    raise SystemExit("cars-act-check skill not found (looked in skills-plugin runtime and ~/Desktop/Skills)")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def host_of(url):
    h = (urllib.parse.urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


# ------------------------------------------------------------------ crawl

def prioritize(C, urls, domain, cap, seed):
    """Key surfaces, then every specials/finance/SRP URL, then a seeded sample split
    between VDPs and other pages. Order matters: a budget cut drops the tail."""
    base = "https://" + domain.rstrip("/")
    dom = host_of(base)
    urls = [u for u in urls if host_of(u) == dom]
    present = set(urls)
    key = [base + p for p in KEY_PATHS if base + p in present]
    key_set = set(key)
    rest = [u for u in urls if u not in key_set]
    kinds = {u: C.classify(u) for u in rest}
    prio = [u for u in rest if kinds[u] in ("specials", "finance", "srp")]
    vdp = [u for u in rest if kinds[u] == "vdp"]
    other = [u for u in rest if kinds[u] not in ("specials", "finance", "srp", "vdp")]
    rng = random.Random(seed)
    rng.shuffle(vdp)
    rng.shuffle(other)
    tail = []
    for i in range(max(len(vdp), len(other))):  # interleave so a cut keeps both kinds
        if i < len(vdp):
            tail.append(vdp[i])
        if i < len(other):
            tail.append(other[i])
    ordered = key + prio + tail
    return ordered[:cap] if cap else ordered


def crawl(C, domain, max_pages, budget_s, seed):
    t0 = time.time()
    urls = C.discover_sitemaps(domain)
    discovered = len(urls)
    ordered = prioritize(C, urls, domain, max_pages, seed)
    deadline = t0 + budget_s
    lock = threading.Lock()
    st = {"status": {}, "pages": [], "blocked": 0, "errors": 0, "not_found": 0,
          "skipped": 0, "down_streak": 0, "block_streak": 0, "stop": None}

    def work(url):
        if st["stop"] or time.time() > deadline:
            with lock:
                st["skipped"] += 1
            return
        time.sleep(C.PACING)
        try:
            code, body = C.fetch(url)
        except urllib.error.HTTPError as e:
            with lock:
                st["status"][url] = e.code
                if e.code in BLOCK_CODES:
                    st["blocked"] += 1
                    st["block_streak"] += 1
                    if st["block_streak"] >= 10 and not st["pages"]:
                        st["stop"] = "waf_blocked"
                elif e.code in (404, 410):
                    st["not_found"] += 1
                else:
                    st["errors"] += 1
            return
        except Exception:
            with lock:
                st["status"][url] = 0
                st["errors"] += 1
                st["down_streak"] += 1
                if st["down_streak"] >= 8:
                    st["stop"] = "circuit_breaker"
            return
        if len(body) < 60000 and CHALLENGE_RE.search(body[:5000]):
            with lock:
                st["status"][url] = "challenge"
                st["blocked"] += 1
                st["block_streak"] += 1
                if st["block_streak"] >= 10 and not st["pages"]:
                    st["stop"] = "waf_blocked"
            return
        page = C.extract(url, body)
        page["type"] = C.classify(url)
        page["changed"] = True
        with lock:
            st["status"][url] = code
            st["down_streak"] = 0
            st["block_streak"] = 0
            st["pages"].append(page)

    workers = min(int(getattr(C, "WORKERS", 3)), 4)  # never above 4 (2026-07-26 outage lesson)
    with concurrent.futures.ThreadPoolExecutor(workers) as ex:
        list(ex.map(work, ordered))
    return {"discovered": discovered, "queued": len(ordered), "seconds": round(time.time() - t0, 1),
            "ok": len(st["pages"]), "blocked": st["blocked"], "not_found": st["not_found"],
            "errors": st["errors"], "skipped_budget": st["skipped"], "stop": st["stop"],
            "status": st["status"], "pages": st["pages"]}


# ------------------------------------------------------------------ checks + triage

def run_checks(CK, rules, pages, data_dir):
    findings = CK.run_pattern_rules(rules + WATCH_RULES, pages) + CK.run_jsonld_rules(pages)
    if os.path.exists(os.path.join(data_dir, "url_status.json")):
        findings += CK.run_status_rules(data_dir, data_dir)
    # run_selfchecks is skipped on purpose: the retention manifest belongs to the full skill.
    return findings


def trigger_text(evidence):
    m = re.match(r"trigger '(.*)' without required disclosure", evidence or "", re.S)
    return (m.group(1) if m else (evidence or "")).strip()


FP_E53 = re.compile(r"\bno\s+(add[\s-]*ons?|accessories|products)\b[^.]{0,200}\b(is|are)\s+required", re.I)
FP_CALC = re.compile(r"(12|24|36)\s+Months?\s+(24|36|48)\s+Months?\s+(36|48|60)\s+Months?", re.I)
FP_A10 = re.compile(r"^(vin|stk|stock)\s*#?\s*(miles|mileage|number|stock|model|exterior|interior|color|engine|"
                    r"transmission|drivetrain|body|trim|details)\b", re.I)


def triage(f, text_by_url, domain):
    """Returns (label, note). Labels: review, likely_false_positive, off_domain."""
    rid, ev, url = f.get("id", ""), f.get("evidence", ""), f.get("url", "")
    trig = trigger_text(ev)
    text = text_by_url.get(url, "")
    if url.startswith("http") and host_of(url) != host_of("https://" + domain):
        return "off_domain", "URL is not on the store's domain"
    if rid == "F65" and re.fullmatch(r"\$\s?[\d,]+", trig):
        return "likely_false_positive", "F65 matched a bare dollar amount (known since 2026-09-19)"
    if rid == "E53" and FP_E53.search(text):
        return "likely_false_positive", "page states no add-on is required, in wording the rule does not match"
    if rid == "D44" and FP_CALC.search(text):
        return "likely_false_positive", "term option in a payment calculator dropdown (consumer-adjusted tool estimate)"
    if rid == "E55" and re.search(r"avoid|no\s+(more\s+)?oil|never\s+need|don'?t\s+need", ev, re.I):
        return "likely_false_positive", "copy says EVs do not need oil changes"
    if rid == "A10" and FP_A10.match(trig):
        return "likely_false_positive", "matched a template label ('VIN' next to a field name), not a VIN"
    return "review", ""


def norm_evidence(ev):
    t = trigger_text(ev).lower()
    t = re.sub(r"\d", "#", t)
    return re.sub(r"\s+", " ", t)[:70]


def snippet(text, needle, width=140):
    if not text or not needle:
        return ""
    i = text.lower().find(needle.lower()[:40])
    if i < 0:
        return ""
    return re.sub(r"\s+", " ", text[max(0, i - width):i + len(needle) + width]).strip()


def collapse(findings, pages, domain):
    text_by_url = {p["url"]: p.get("text", "") for p in pages}
    type_by_url = {p["url"]: p["type"] for p in pages}
    checked_by_type = Counter(p["type"] for p in pages)
    rules = {}
    for f in findings:
        label, note = triage(f, text_by_url, domain)
        f["triage"], f["triage_note"] = label, note
        r = rules.setdefault(f["id"], {
            "id": f["id"], "point": f.get("point"), "severity": f.get("severity"),
            "summary": f.get("summary"), "citation": f.get("citation"),
            "vault_ids": RULE_MAP.get(f["id"], ("", "", ""))[0],
            "audit_ids": RULE_MAP.get(f["id"], ("", "", ""))[1],
            "label": RULE_MAP.get(f["id"], ("", "", f.get("summary", "")))[2],
            "review_urls": set(), "aside_urls": set(), "by_triage": Counter(), "templates": {},
            "page_types": Counter()})
        url = f.get("url")
        (r["review_urls"] if label == "review" else r["aside_urls"]).add(url)
        r["by_triage"][label] += 1
        if label == "review":
            r["page_types"][type_by_url.get(url, "?")] += 1
        key = (norm_evidence(f.get("evidence", "")), label)
        t = r["templates"].get(key)
        if t is None:
            t = r["templates"][key] = {"evidence": key[0], "triage": label, "note": note, "pages": 0,
                                       "example_url": url,
                                       "snippet": snippet(text_by_url.get(url, ""), trigger_text(f.get("evidence", "")))}
        t["pages"] += 1
    out = []
    for r in rules.values():
        r["triage"] = "review" if r["review_urls"] else r["by_triage"].most_common(1)[0][0]
        r["pages_flagged"] = len(r["review_urls"]) if r["review_urls"] else len(r["aside_urls"])
        r["pages_set_aside"] = len(r["aside_urls"] - r["review_urls"])
        del r["review_urls"], r["aside_urls"]
        r["page_types"] = dict(r["page_types"])
        r["by_triage"] = dict(r["by_triage"])
        r["templates"] = sorted(r["templates"].values(),
                                key=lambda t: (t["triage"] != "review", -t["pages"]))[:6]
        out.append(r)
    sev = {"C": 0, "M": 1, "m": 2}
    out.sort(key=lambda r: (r["triage"] != "review", sev.get(r["severity"], 3), -r["pages_flagged"]))
    return out, dict(checked_by_type)


def find_prior(vault, store, date):
    """Newest earlier watch run for this store that fetched pages (blocked runs are skipped)."""
    paths = glob.glob(os.path.join(vault, "outputs", "ai-team", "*", "data", "cars_%s" % store, "summary.json"))
    dated = sorted(((p.split(os.sep)[-4], p) for p in paths), reverse=True)
    for d, p in dated:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) or d >= date:
            continue
        try:
            blob = json.load(open(p))
        except Exception:
            continue
        if blob.get("status") == "ok":
            return blob
    return None


def diff(rules, prior):
    if not prior:
        for r in rules:
            r["vs_last"] = "first run"
        return {"prior_date": None, "new": [], "resolved": []}
    old = {r["id"]: r for r in prior.get("rules", []) if r.get("triage") == "review"}
    now = {r["id"]: r for r in rules if r["triage"] == "review"}
    for r in rules:
        if r["triage"] != "review":
            r["vs_last"] = ""
            continue
        o = old.get(r["id"])
        if not o:
            r["vs_last"] = "NEW"
            continue
        old_t = {t["evidence"] for t in o.get("templates", []) if t.get("triage", "review") == "review"}
        new_t = [t for t in r["templates"] if t["triage"] == "review" and t["evidence"] not in old_t]
        r["vs_last"] = "RECURRING" + (" (new wording: %d)" % len(new_t) if new_t else "")
    resolved = [{"id": k, "label": v.get("label"), "pages_flagged": v.get("pages_flagged")}
                for k, v in old.items() if k not in now]
    return {"prior_date": prior.get("date"), "new": [k for k in now if k not in old], "resolved": resolved}


# ------------------------------------------------------------------ report

def mode_for(date):
    return ("ENFORCEMENT (operative %s)" % OPERATIVE) if date >= OPERATIVE else \
        ("READINESS (operative %s; items are gaps to close before then)" % OPERATIVE)


def render(summary):
    s = summary
    c = s["crawl"]
    lines = []
    head = "CARS watch %s %s, %s." % (s["store"], s["date"], mode_for(s["date"]))
    lines.append(head)
    if s["status"] != "ok":
        since = ("since %s" % s["last_ok_date"]) if s.get("last_ok_date") else "from any watch run yet"
        lines.append("No usable pages: %s. No CARS web data for %s %s." % (s["status_note"], s["store"], since))
        return "\n".join(lines)
    lines.append("%d of %d discovered URLs queued, %d fetched OK in %.1f min; %d blocked, %d not found, %d errors, "
                 "%d skipped for time." % (c["queued"], c["discovered"], c["ok"], c["seconds"] / 60.0, c["blocked"],
                                           c["not_found"], c["errors"], c["skipped_budget"]))
    rev = [r for r in s["rules"] if r["triage"] == "review"]
    fp = [r for r in s["rules"] if r["triage"] != "review"]
    if rev:
        lines.append("Flagged for review (rule, pages, rule ids, vs last run):")
        for r in rev:
            n_t = len([t for t in r["templates"] if t["triage"] == "review"])
            aside = (", %d more set aside" % r["pages_set_aside"]) if r.get("pages_set_aside") else ""
            lines.append("- %s %s: %d page(s), %d wording(s)%s; %s / %s; %s" % (
                r["id"], r["label"], r["pages_flagged"], n_t, aside, r["vault_ids"] or "-", r["audit_ids"] or "-",
                r.get("vs_last") or ""))
    else:
        lines.append("Nothing flagged for review by the machine rules.")
    if fp:
        lines.append("Set aside as likely false positives: " + ", ".join(
            "%s %d" % (r["id"], r["pages_flagged"]) for r in fp) + ".")
    d = s["diff"]
    if d.get("prior_date"):
        lines.append("Since %s: %d new rule(s) flagged, %d resolved%s." % (
            d["prior_date"], len(d["new"]), len(d["resolved"]),
            (" (" + ", ".join(x["id"] for x in d["resolved"]) + ")") if d["resolved"] else ""))
    if c.get("source"):
        lines.append("Source: page text captured outside the crawl (%s); JSON-LD and dead-URL checks do not run. "
                     "Automated pattern scan, flagged for review, not a legal determination." % os.path.basename(
                         str(c["source"])))
    else:
        lines.append("Server HTML only: script-injected text, images, and chat widgets are not seen. "
                     "Automated pattern scan, flagged for review, not a legal determination.")
    return "\n".join(lines)


def render_md(summary):
    out = ["# CARS watch: %s, %s" % (summary["store"], summary["date"]), "", render(summary), ""]
    for r in summary.get("rules", []):
        if r["triage"] != "review":
            continue
        out.append("## %s %s" % (r["id"], r["label"]))
        out.append("Cite: %s. Rule ids: %s / %s. Pages: %d %s." % (
            r["citation"], r["vault_ids"] or "-", r["audit_ids"] or "-", r["pages_flagged"],
            json.dumps(r["page_types"])))
        for t in r["templates"]:
            if t["triage"] != "review":
                continue
            out.append("- %d page(s), e.g. %s" % (t["pages"], t["example_url"]))
            if t["snippet"]:
                out.append("  - \"%s\"" % t["snippet"][:320].replace('"', "'"))
        out.append("")
    return "\n".join(out)


# ------------------------------------------------------------------ main

def run(args):
    vault = os.path.abspath(args.vault_root or default_vault_root())
    os.environ["DIGITALCLIQ_VAULT_ROOT"] = vault
    date = args.date or pacific_today()
    store = args.store
    if args.rotation:
        wd = dt.date.fromisoformat(date).isoweekday()
        store = ROTATION.get(wd)
        if not store:
            print("CARS watch: no store on the rotation for %s (rotation: %s). Nothing to do." % (
                date, ", ".join("%s=%s" % (["", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][k], v)
                                for k, v in sorted(ROTATION.items()))))
            return 0
    store = (store or "").upper()
    if store not in STORES:
        raise SystemExit("unknown store %r; one of %s (MCP is covered by mcpeeks-site-watch)" % (store, sorted(STORES)))
    domain = args.domain or STORES[store]
    skill = find_skill_dir(args.skill_dir)
    C = load_module("cars_crawl", os.path.join(skill, "scripts", "crawl.py"))
    CK = load_module("cars_checks", os.path.join(skill, "scripts", "checks.py"))
    rules = json.load(open(os.path.join(skill, "config", "rules.json")))["rules"]

    out_dir = args.out or os.path.join(vault, "outputs", "ai-team", date, "data", "cars_%s" % store)
    os.makedirs(out_dir, exist_ok=True)
    started = time.time()

    # The SBMW browser task (Mondays 12:15 AM) writes today's run here before the 1 AM shift; a plain
    # crawl of a Cloudflare-blocked site must not overwrite it with a "blocked" result.
    today_summary = os.path.join(out_dir, "summary.json")
    if not args.pages_file and os.path.exists(today_summary):
        try:
            existing = json.load(open(today_summary))
        except Exception:
            existing = {}
        if existing.get("status") == "ok" and (existing.get("crawl") or {}).get("source"):
            print("A browser run for %s already landed today (%s); not re-crawling." % (
                store, existing["crawl"]["source"]))
            print(render(existing))
            print("Files: %s" % os.path.relpath(out_dir, vault))
            return 0

    if args.pages_file:
        pages = [json.loads(l) for l in open(args.pages_file) if l.strip()]
        for p in pages:
            p.setdefault("type", C.classify(p.get("url", "")))
            p.setdefault("jsonld_vehicles", [])
            p.setdefault("text", "")
        cr = {"discovered": len(pages), "queued": len(pages), "seconds": 0.0, "ok": len(pages), "blocked": 0,
              "not_found": 0, "errors": 0, "skipped_budget": 0, "stop": None, "status": {}, "source": args.pages_file}
    else:
        cr = crawl(C, domain, args.max_pages, args.budget_min * 60, seed="%s-%s" % (store, date))
        pages = cr.pop("pages")
    status_map = cr.pop("status", {})

    status, note = "ok", ""
    if cr.get("stop") == "circuit_breaker":
        status, note = "circuit_breaker", "site stopped answering (8 connection failures in a row); crawl stopped"
    elif not pages:
        status = "blocked" if cr["blocked"] else "no_pages"
        note = ("plain HTTP refused (%d blocked responses, WAF or bot wall); needs a browser run or an allowlist"
                % cr["blocked"]) if cr["blocked"] else "no pages fetched"
    elif cr["blocked"] > max(5, 0.2 * cr["queued"]):
        note = "partial block: %d of %d requests refused" % (cr["blocked"], cr["queued"])

    write_dir = out_dir
    existing = os.path.join(out_dir, "summary.json")
    if status != "ok" and os.path.exists(existing):
        try:
            if json.load(open(existing)).get("status") == "ok":
                write_dir = os.path.join(out_dir, "blocked_attempt")  # never overwrite a usable same-day run
                os.makedirs(write_dir, exist_ok=True)
        except Exception:
            pass
    json.dump(status_map, open(os.path.join(write_dir, "url_status.json"), "w"), indent=0)

    rules_out, checked = [], {}
    findings = []
    if status == "ok":
        findings = run_checks(CK, rules, pages, out_dir)
        rules_out, checked = collapse(findings, pages, domain)
    prior = find_prior(vault, store, date)
    d = diff(rules_out, prior) if status == "ok" else {"prior_date": prior.get("date") if prior else None,
                                                      "new": [], "resolved": []}
    summary = {"store": store, "domain": domain, "date": date, "mode": mode_for(date), "status": status,
               "status_note": note, "last_ok_date": prior.get("date") if prior else None,
               "skill_dir": skill, "crawl": cr, "pages_checked_by_type": checked,
               "rules": rules_out, "diff": d,
               "counts": {"review_rules": sum(1 for r in rules_out if r["triage"] == "review"),
                          "review_pages": len({f["url"] for f in findings if f.get("triage") == "review"}),
                          "raw_findings": len(findings)},
               "elapsed_seconds": round(time.time() - started, 1)}
    json.dump({"findings": findings}, open(os.path.join(write_dir, "findings.json"), "w"), indent=0)
    json.dump(summary, open(os.path.join(write_dir, "summary.json"), "w"), indent=1)
    json.dump({k: summary[k] for k in ("store", "domain", "date", "status", "status_note", "crawl",
                                       "elapsed_seconds", "skill_dir")},
              open(os.path.join(write_dir, "run.json"), "w"), indent=1)
    open(os.path.join(write_dir, "summary.md"), "w").write(render_md(summary))
    print(render(summary))
    if status != "ok":
        # A browser-sourced run (--pages-file, e.g. the SBMW scheduled task) may have landed
        # since the last shift; show it so the brief still has a current read.
        tomorrow = (dt.date.fromisoformat(date) + dt.timedelta(days=1)).isoformat()
        latest = find_prior(vault, store, tomorrow)
        if latest and (dt.date.fromisoformat(date) - dt.date.fromisoformat(latest["date"])).days <= 7:
            src = latest.get("crawl", {}).get("source")
            print("\nNewest usable run (%s%s):" % (latest["date"], ", browser pages" if src else ""))
            print(render(latest))
    print("Files: %s" % os.path.relpath(write_dir, vault))
    return {"ok": 0, "blocked": 2, "no_pages": 2, "circuit_breaker": 3}[status]


# ------------------------------------------------------------------ selftest

def selftest(args):
    import tempfile
    skill = find_skill_dir(args.skill_dir)
    C = load_module("cars_crawl", os.path.join(skill, "scripts", "crawl.py"))
    CK = load_module("cars_checks", os.path.join(skill, "scripts", "checks.py"))
    rules = json.load(open(os.path.join(skill, "config", "rules.json")))["rules"]
    dom = "www.example-nissan.com"
    base = "https://" + dom
    vdp_text = ("New 2026 Nissan Rogue SV VIN 5N1BT3BA2TC886814 Sale Price $31,495 Unlock Your Price "
                "Price includes Nissan to Customer Rebates. Price does not include dealer or vendor added equipment, "
                "accessories, or products. Doc Fee applies. No add-ons, accessories, service contracts, GAP, or theft "
                "protection are required at the advertised price. Loan Term Months 12 Months 24 Months 36 Months "
                "48 Months 60 Months 72 Months 84 Months. Used vehicles over $40,000 excluded.")
    pages = [
        {"url": base + "/inventory/new-2026-nissan-rogue-sv-5n1bt3ba2tc886814/", "type": "vdp", "text": vdp_text,
         "jsonld_vehicles": [], "has_jsonld": False},
        {"url": base + "/inventory/new-2026-nissan-rogue-sv-5n1bt3ba2tc886999/", "type": "vdp",
         "text": vdp_text.replace("31,495", "32,100"), "jsonld_vehicles": [], "has_jsonld": False},
        {"url": base + "/about/", "type": "page", "text": "EV owners avoid the costs that come with oil changes.",
         "jsonld_vehicles": [], "has_jsonld": False},
    ]
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        json.dump({pages[0]["url"]: 200}, open(os.path.join(tmp, "url_status.json"), "w"))
        findings = run_checks(CK, rules, pages, tmp)
        rules_out, _ = collapse(findings, pages, dom)
        by = {r["id"]: r for r in rules_out}
        check(by.get("I104", {}).get("triage") == "review", "I104 installed-items exclusion should be review")
        check(by.get("W01", {}).get("triage") == "review", "W01 rebate-in-price should be review")
        check(by.get("E53", {}).get("triage") == "likely_false_positive", "E53 should be set aside (no add-on required)")
        check(by.get("D44", {}).get("triage") == "likely_false_positive", "D44 calculator dropdown should be set aside")
        check("F65" not in by or by["F65"]["triage"] == "likely_false_positive", "F65 $40,000 should be set aside")
        check("E55" not in by or by["E55"]["triage"] == "likely_false_positive", "E55 'avoid oil change' set aside")
        check(by.get("I104", {}).get("pages_flagged") == 2 and len(by["I104"]["templates"]) == 1,
              "I104 should collapse two pages into one wording")
        prior = {"date": "2026-09-16", "status": "ok", "rules": [
            {"id": "I104", "triage": "review", "templates": [{"evidence": by["I104"]["templates"][0]["evidence"]}]},
            {"id": "A03", "triage": "review", "label": "call-for-price", "pages_flagged": 3, "templates": []}]}
        d = diff(rules_out, prior)
        check(by["I104"]["vs_last"] == "RECURRING", "I104 should be RECURRING vs prior")
        check(by["W01"]["vs_last"] == "NEW", "W01 should be NEW vs prior")
        check([x["id"] for x in d["resolved"]] == ["A03"], "A03 should be resolved")
        summ = {"store": "TEST", "date": "2026-10-02", "status": "ok", "status_note": "", "crawl": {
            "queued": 3, "discovered": 3, "ok": 3, "seconds": 1.0, "blocked": 0, "not_found": 0, "errors": 0,
            "skipped_budget": 0}, "rules": rules_out, "diff": d}
        text = render(summ) + render_md(summ)
        check("ENFORCEMENT" in text, "mode should flip to ENFORCEMENT on/after 2026-10-01")
        check("\u2014" not in text and "\u2013" not in text, "no em or en dashes in output")
        check(not re.search(r"\bcompliant\b|\bis legal\b|\bviolation\b", text, re.I),
              "output must not claim legal clearance or a violation")
    urls = [base + p for p in ("/", "/specials", "/finance")] + \
           [base + "/inventory/new-2026-nissan-x-%05d/" % i for i in range(40)] + \
           [base + "/page-%d/" % i for i in range(40)] + ["https://shop.other.com/x"]
    order = prioritize(C, urls, dom, 20, "seed")
    check(order[:3] == [base + "/", base + "/specials", base + "/finance"], "key pages first")
    check(len(order) == 20 and "https://shop.other.com/x" not in order, "cap and same-domain filter")
    check(any("/inventory/" in u for u in order) and any("/page-" in u for u in order), "cut keeps VDPs and pages")
    check(CHALLENGE_RE.search(b"<html><title>Just a moment...</title>") is not None, "challenge page detected")
    check(CHALLENGE_RE.search(b"<html><title>New Nissan Rogue</title>") is None, "normal page not a challenge")
    if fails:
        print("SELFTEST FAIL (%d):\n- %s" % (len(fails), "\n- ".join(fails)))
        return 1
    print("SELFTEST OK: triage, collapse, diff, mode, wording, prioritize, challenge detection (skill: %s)" % skill)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", help="SBMW, NCBMW, NOI, or CHC")
    ap.add_argument("--rotation", action="store_true", help="pick the store from the weekday rotation")
    ap.add_argument("--date", help="shift date YYYY-MM-DD (default today Pacific)")
    ap.add_argument("--domain", help="override the store domain")
    ap.add_argument("--max-pages", type=int, default=400)
    ap.add_argument("--budget-min", type=float, default=8.0)
    ap.add_argument("--pages-file", help="pages.jsonl built elsewhere (e.g. browser extracts); skips the crawl")
    ap.add_argument("--out", help="output dir (default outputs/ai-team/{date}/data/cars_{STORE})")
    ap.add_argument("--vault-root")
    ap.add_argument("--skill-dir")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(selftest(args))
    if not args.store and not args.rotation:
        ap.error("--store or --rotation is required")
    sys.exit(run(args))


if __name__ == "__main__":
    main()
