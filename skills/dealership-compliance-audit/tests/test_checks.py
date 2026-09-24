#!/usr/bin/env python3
"""
test_checks.py — test-driven proof that the codified pipeline works.

Covers:
  1. Registry codifies all 9 frameworks + PRICING + BRAND.
  2. A clean (compliant) crawl produces zero critical violations and the
     positive checks PASS.
  3. A violations crawl FAILS the expected checks at the expected severities.
  4. Truncation → fallback re-verify: an unresolved item caused by a truncated
     page is corrected by the fallback crawler and flips to PASS — proving the
     pipeline does NOT emit the false positive.
  5. Honesty: when the fallback cannot fetch the page, the item stays UNRESOLVED
     and human-review, and is NEVER promoted to a violation.

Run: python3 tests/test_checks.py     (exit 0 = all pass)
Stdlib only; monkeypatches the network so it runs offline.
"""

import os
import sys
import json
import copy

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(TESTS_DIR)
FIXTURES = os.path.join(TESTS_DIR, "fixtures")
sys.path.insert(0, SKILL_DIR)
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))

from checks import registry          # noqa: E402
import fallback_crawl                 # noqa: E402
import verify_loop                    # noqa: E402

passed = 0
failed = 0


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        print("  [PASS] %s" % name)
        passed += 1
    else:
        print("  [FAIL] %s  -- %s" % (name, detail))
        failed += 1


def load(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def by_id(results):
    """Map check_id -> result (last wins; fine for these fixtures)."""
    return {r.check_id: r for r in results}


# ── 1. Registry coverage ─────────────────────────────────────
print("\n1. Registry codifies all 9 frameworks + pricing + brand")
summary = registry.registry_summary()
frameworks = set(row["framework"] for row in summary)
for fw in ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "PRICING", "BRAND"]:
    test("framework %s codified" % fw, fw in frameworks,
         "frameworks present: %s" % sorted(frameworks))
test("registry has >= 15 checks", len(summary) >= 15, "got %d" % len(summary))


# ── 2. Clean crawl → no critical violations ──────────────────
print("\n2. Clean (compliant) crawl passes")
clean = load("clean_crawl.json")
clean_results = registry.run_checks(clean, brand="bmw")
clean_by = by_id(clean_results)
crit_fails = [r for r in clean_results if r.status == "fail" and r.severity == "critical"]
test("no critical violations on clean site", len(crit_fails) == 0,
     "critical fails: %s" % [r.check_id for r in crit_fails])
all_fails = [r.check_id for r in clean_results if r.status == "fail"]
test("ZERO false positives on a clean compliant site", len(all_fails) == 0,
     "unexpected fails: %s" % all_fails)
test("lease Reg M passes (all terms present)",
     clean_by.get("PRICING-LEASE-REGM") and clean_by["PRICING-LEASE-REGM"].status == "pass")
test("sale-with-dates passes",
     clean_by.get("F5-SALE-HAS-DATES") and clean_by["F5-SALE-HAS-DATES"].status == "pass")
test("MPG-with-EPA passes",
     clean_by.get("F9-MPG-EPA") and clean_by["F9-MPG-EPA"].status == "pass")
test("priced specials page has disclaimer (pass)",
     clean_by.get("F1-PRICE-HAS-DISCLAIMER") and clean_by["F1-PRICE-HAS-DISCLAIMER"].status == "pass")


# ── 3. Violations crawl → expected failures ──────────────────
print("\n3. Violations crawl fails the right checks")
viol = load("violations_crawl.json")
viol_results = registry.run_checks(viol, brand="bmw")
viol_by = by_id(viol_results)

expect_fail = {
    "PRICING-EVERYONE-FINANCED": "critical",
    "F5-SALE-HAS-DATES": "warning",
    "F9-MPG-EPA": "warning",
    "F2-SUPERLATIVE-SUBSTANTIATED": "warning",
    "F3-PAYMENT-HAS-CONTEXT": "warning",
    "F4-REBATE-QUALIFICATION": "warning",
    "F7-DUE-AT-SIGNING": "warning",
    "PRICING-OAC-SPELLED": "advisory",
    "BRAND-EXCLUSIVITY": "warning",
}
for cid, sev in expect_fail.items():
    r = viol_by.get(cid)
    test("%s fails (%s)" % (cid, sev),
         r is not None and r.status == "fail" and r.severity == sev,
         "got %s" % (None if not r else str((r.status, r.severity))))

# the everyone-financed finding must be high confidence (no human-review hedge)
test("everyone-financed is high confidence",
     viol_by["PRICING-EVERYONE-FINANCED"].confidence == "high")


# ── 4. Truncation → fallback re-verify flips a false positive ─
print("\n4. Truncated page → fallback re-crawl averts the false positive")

# Build a crawl whose specials page is truncated at the 12000-char browser cap,
# with a lease offer but NO disclaimer captured. Off the truncated data the
# disclaimer/Reg-M/due-at-signing checks are UNRESOLVED (not failed).
filler = ("the all new model offers premium features and a refined driving "
          "experience for discerning buyers ") * 200
truncated_text = ("2026 BMW 330i lease for $499/mo for 36 months. " + filler)[:12000]
trunc = {
    "url": "https://www.trunc-bmw.com", "brand": "bmw", "client": "Trunc BMW",
    "crawl_date": "2026-06-23",
    "pages": {
        "specials": {
            "url": "https://www.trunc-bmw.com/specials",
            "title": "Specials",
            "text_excerpt": truncated_text,
            "lease_payments": ["$499/mo"],
            "lease_terms": ["36 months"],
            "has_lease_offers": True,
            "disclaimers": [],
            "disclaimer_buttons_clicked": 4,
        }
    },
}

base = registry.run_checks(copy.deepcopy(trunc), brand="bmw")
base_by = by_id(base)
test("specials page detected as truncated",
     registry.is_truncated("specials", trunc["pages"]["specials"]))
test("disclaimer check is UNRESOLVED on truncated data (not a false fail)",
     base_by.get("F1-PRICE-HAS-DISCLAIMER") and base_by["F1-PRICE-HAS-DISCLAIMER"].status == "unresolved",
     "got %s" % (base_by.get("F1-PRICE-HAS-DISCLAIMER") and base_by["F1-PRICE-HAS-DISCLAIMER"].status))
test("lease Reg M is UNRESOLVED on truncated data (not a false fail)",
     base_by.get("PRICING-LEASE-REGM") and base_by["PRICING-LEASE-REGM"].status == "unresolved")

# Monkeypatch the network: the fallback fetch returns the FULL page, including the
# disclaimer the browser truncated away.
full_disclaimer = ("Lease for $499/mo for 36 months. $4,999 due at signing. "
                   "10,000 miles per year, $0.25 per excess mile. Capitalized cost "
                   "$42,000, residual value applies. On approved credit. "
                   "Not all customers will qualify.")
full_text = truncated_text + "\n" + full_disclaimer + (" full server side body content" * 200)


def fake_recrawl_ok(page_key, url, timeout=20):
    return {
        "url": url, "title": "Specials",
        "text_excerpt": full_text, "page_text_excerpt": full_text,
        "disclaimers": [full_disclaimer],
        "lease_payments": ["$499/mo"], "lease_terms": ["36 months"],
        "has_lease_offers": True, "source": "fallback_crawl",
        "char_count": len(full_text),
    }


orig_recrawl = fallback_crawl.recrawl
fallback_crawl.recrawl = fake_recrawl_ok
tmp = os.path.join(FIXTURES, "_trunc_tmp.json")
try:
    with open(tmp, "w") as f:
        json.dump(trunc, f)
    final, findings, report = verify_loop.run(tmp, "bmw")
finally:
    fallback_crawl.recrawl = orig_recrawl
    if os.path.exists(tmp):
        os.remove(tmp)

final_by = by_id(final)
test("disclaimer check flipped UNRESOLVED → PASS after re-crawl",
     final_by.get("F1-PRICE-HAS-DISCLAIMER") and final_by["F1-PRICE-HAS-DISCLAIMER"].status == "pass",
     "got %s" % (final_by.get("F1-PRICE-HAS-DISCLAIMER") and final_by["F1-PRICE-HAS-DISCLAIMER"].status))
test("lease Reg M flipped UNRESOLVED → PASS after re-crawl",
     final_by.get("PRICING-LEASE-REGM") and final_by["PRICING-LEASE-REGM"].status == "pass")
test("report counts >= 1 false positive averted",
     report["summary"]["false_positives_averted"] >= 1,
     "got %d" % report["summary"]["false_positives_averted"])
test("re-verified checks are marked reverified",
     final_by["F1-PRICE-HAS-DISCLAIMER"].reverified is True)
fail_ids = {f["rule_id"] for f in findings} | {f["title"] for f in findings}
test("NO false-positive disclaimer finding emitted",
     not any("F1-PRICE-HAS-DISCLAIMER" in f["title"] for f in findings),
     "findings: %s" % [f["title"] for f in findings])


# ── 5. Honesty: fallback fails → stays unresolved, never a violation ─
print("\n5. Fallback fetch fails → item stays UNRESOLVED, never false-flagged")


def fake_recrawl_error(page_key, url, timeout=20):
    return {"error": "http_403", "url": url, "source": "fallback_crawl"}


fallback_crawl.recrawl = fake_recrawl_error
try:
    tmp = os.path.join(FIXTURES, "_trunc_tmp2.json")
    with open(tmp, "w") as f:
        json.dump(trunc, f)
    final2, findings2, report2 = verify_loop.run(tmp, "bmw")
finally:
    fallback_crawl.recrawl = orig_recrawl
    if os.path.exists(os.path.join(FIXTURES, "_trunc_tmp2.json")):
        os.remove(os.path.join(FIXTURES, "_trunc_tmp2.json"))

final2_by = by_id(final2)
test("disclaimer check stays UNRESOLVED when fallback fails",
     final2_by.get("F1-PRICE-HAS-DISCLAIMER") and final2_by["F1-PRICE-HAS-DISCLAIMER"].status == "unresolved")
test("no violation emitted from a failed re-crawl",
     not any("F1-PRICE-HAS-DISCLAIMER" in f["title"] for f in findings2))
test("zero false positives averted (nothing corrected)",
     report2["summary"]["false_positives_averted"] == 0)
test("recrawl outcome recorded as error (gap, not silent)",
     any(rc["outcome"] == "error" for rc in report2["recrawls"]))


# ── 6. Merged engine: ported checks (privacy, CARS, fees, brand) fire ─
print("\n6. Merged registry runs privacy + CARS + fee + brand checks (single engine)")
kitchen = {
    "url": "https://www.bad-cdjr.com", "brand": "cdjr", "client": "Bad CDJR",
    "crawl_date": "2026-06-28",
    "pages": {
        "homepage": {
            "url": "https://www.bad-cdjr.com", "title": "Best Jeep Deals",
            "dealer_name": "Bad CDJR of Anaheim",
            "text_excerpt": "We are the #1 dealer in town. FCA approved. Government endorsed "
                            "program. New Grand Jeep Cherokee in stock. $0 down today!",
            "disclaimers": [],
            "privacy": {"has_privacy_policy_link": False, "has_do_not_sell_link": False,
                        "has_limit_sensitive_link": False,
                        "lead_forms_have_privacy_notice": [{"has_privacy_link": False,
                                                            "fields": ["name", "email", "phone"]}]},
        },
        "specials": {
            "url": "https://www.bad-cdjr.com/specials", "title": "Specials",
            "text_excerpt": "Lease the Jeep for $299/mo. Plus dealer fee. Payments as low as "
                            "$199. Exp 12/31/2022.",
            "lease_payments": ["$299/mo"], "lease_terms": [], "has_lease_offers": True,
            "disclaimers": [], "disclaimer_buttons_clicked": 0,
        },
        "finance": {
            "url": "https://www.bad-cdjr.com/finance", "title": "Finance",
            "text_excerpt": "You're approved instantly! Service contract and GAP waiver "
                            "available. All sales final, you waive your right to cancel.",
            "disclaimers": [],
        },
        "used": {
            "url": "https://www.bad-cdjr.com/used", "title": "Inventory",
            "page_text_excerpt": "All sales final, no returns. Electric vehicle special with "
                                 "free oil change package included.",
            "has_cpo_section": False, "disclaimers": [],
        },
        "privacy_policy": {
            "url": "https://www.bad-cdjr.com/privacy", "title": "Privacy",
            "text_excerpt": "We collect information. Contact privacy@bad-cdjr.com.",
            "ccpa_cpra_content": {k: False for k in (
                "has_right_to_know", "has_right_to_delete", "has_right_to_opt_out",
                "has_right_to_correct", "has_right_to_limit_sensitive",
                "has_categories_collected", "has_third_party_disclosure",
                "has_sources_of_pi", "has_purposes", "has_retention_periods",
                "has_sell_share_disclosure", "has_gpc_disclosure")},
        },
    },
}
kitchen["pages"]["privacy_policy"]["ccpa_cpra_content"]["request_method_count"] = 1
ks_res = registry.run_checks(kitchen, brand="cdjr")
ks_fail = {r.check_id for r in ks_res if r.status == "fail"}
for cid in ["PRIV-001", "PRIV-002", "PRIV-004", "PRIV-005", "PRIV-006", "PRIV-008",
            "CA-CARS-002", "CA-CARS-009", "CA-CARS-013", "CA-CARS-014", "CA-CARS-020",
            "CA-PRICE-002", "CA-REGZ-004", "CA-DEALER-001", "CA-DISC-EXP",
            "BRAND-FCA-NAME", "BRAND-MODEL-ORDER"]:
    test("merged check %s fires" % cid, cid in ks_fail,
         "fails were: %s" % sorted(ks_fail))

# CARS posture: federal rule vacated → CA framing; pre-operative (today < 2026-10-01)
# softens severity so nothing CARS ships as a critical, and the federal note is attached.
ks_cars = [r for r in ks_res if r.framework == "CARS" and r.status == "fail"]
test("CARS findings carry the federal-vacated / CA-controls note",
     ks_cars and all(registry.CARS_FED_NOTE in (r.statute or "") for r in ks_cars))
test("pre-operative CARS findings are not criticals (forward-looking)",
     not registry._cars_operative() and all(r.severity != "critical" for r in ks_cars),
     "severities: %s" % [(r.check_id, r.severity) for r in ks_cars])
test("CARS recommendation flags it as a California (not federal) requirement",
     all("CALIFORNIA requirement" in (r.recommendation or "").upper() or
         "California" in (r.recommendation or "") for r in ks_cars))

# privacy checks must NOT fire when the crawl never captured a privacy object
no_priv = {"url": "x", "pages": {"homepage": {"url": "x", "title": "T",
           "text_excerpt": "hello world"}}}
np_res = registry.run_checks(no_priv, brand="bmw")
test("privacy checks silent when no privacy object captured",
     not any(r.check_id.startswith("PRIV-") and r.status == "fail" for r in np_res))

# a missing privacy link on a TRUNCATED homepage is unresolved, not a false critical
trunc_hp = {"url": "x", "pages": {"homepage": {
    "url": "x", "title": "T", "text_excerpt": "x" * 15000,
    "privacy": {"has_privacy_policy_link": False, "has_do_not_sell_link": False}}}}
th_res = {r.check_id: r for r in registry.run_checks(trunc_hp, brand="bmw")}
test("PRIV-001 is UNRESOLVED (not critical) on a truncated homepage",
     th_res.get("PRIV-001") and th_res["PRIV-001"].status == "unresolved")


# ── 7. Multi-VDP fan-out + delta bucketing ───────────────────
print("\n7. Random multi-VDP: checks fan out, delta buckets across VINs")
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))
import delta_engine  # noqa: E402


def _vdp(n):
    return {"url": "https://d.com/inventory/vin%d" % n, "title": "Car %d" % n,
            "text_excerpt": "2026 model gets 40 MPG highway. Stock %d." % n,
            "prices_found": ["$40,000"], "disclaimers": []}


vdp_crawl = {"url": "https://d.com", "pages": {
    "vdp": _vdp(1), "vdp_2": _vdp(2), "vdp_3": _vdp(3),
    "homepage": {"url": "https://d.com", "title": "D", "text_excerpt": "hi"}}}
vdp_res = registry.run_checks(vdp_crawl, brand="bmw")
f9_pages = sorted(r.page for r in vdp_res if r.check_id == "F9-MPG-EPA" and r.status == "fail")
test("F9 fans out to all 3 sampled VDPs", f9_pages == ["vdp", "vdp_2", "vdp_3"],
     "got %s" % f9_pages)
m1 = registry.results_to_findings([r for r in vdp_res if r.status == "fail"])

# next month: same 3 VDP slots, different VINs
vdp_crawl2 = {"url": "https://d.com", "pages": {
    "vdp": _vdp(7), "vdp_2": _vdp(8), "vdp_3": _vdp(9),
    "homepage": {"url": "https://d.com", "title": "D", "text_excerpt": "hi"}}}
m2 = registry.results_to_findings([r for r in registry.run_checks(vdp_crawl2, brand="bmw") if r.status == "fail"])
d = delta_engine.compute_delta(m2, m1)
test("VDP findings PERSIST across months despite new VINs (no churn)",
     d["counts"]["new"] == 0 and d["counts"]["resolved"] == 0 and d["counts"]["persisting"] > 0,
     "counts: %s" % d["counts"])
test("all VDP F9 findings collapse to ONE delta bucket",
     len({delta_engine._finding_key(f) for f in m2 if f["rule_id"] == "CA-FUEL-001"}) == 1)


# ── 8. ADA/Unruh + TCPA lawsuit-vector checks ────────────────
print("\n8. ADA/Unruh accessibility + TCPA lead-form consent")
ada_crawl = {"url": "https://d.com", "pages": {"homepage": {
    "url": "https://d.com", "title": "D BMW", "text_excerpt": "welcome",
    "accessibility": {"images_total": 20, "images_missing_alt": 12, "inputs_total": 6,
                      "inputs_missing_label": 3, "has_lang_attr": False, "has_skip_nav": False},
    "privacy": {"has_privacy_policy_link": True, "has_do_not_sell_link": True,
                "lead_forms_have_privacy_notice": [
                    {"has_phone": True, "has_tcpa_consent": False, "has_privacy_link": True,
                     "fields": ["name", "phone"]}]}}}}
ada_fail = {r.check_id for r in registry.run_checks(ada_crawl, brand="bmw") if r.status == "fail"}
for cid in ["ADA-ALT-TEXT", "ADA-FORM-LABELS", "ADA-LANG-SKIPNAV", "TCPA-CONSENT"]:
    test("lawsuit-vector check %s fires" % cid, cid in ada_fail, "fails: %s" % sorted(ada_fail))
test("ADA/Unruh codified as a framework", "ADA" in {row["framework"] for row in registry.registry_summary()})
test("TCPA codified as a framework", "TCPA" in {row["framework"] for row in registry.registry_summary()})

# silent when the crawl never captured accessibility/phone data (no false positives)
quiet = {"url": "x", "pages": {"homepage": {"url": "x", "title": "t", "text_excerpt": "hi",
         "privacy": {"has_privacy_policy_link": True, "has_do_not_sell_link": True}}}}
quiet_fail = {r.check_id for r in registry.run_checks(quiet, brand="bmw") if r.status == "fail"}
test("ADA/TCPA silent without captured data",
     not any(c in quiet_fail for c in ("ADA-ALT-TEXT", "ADA-FORM-LABELS", "ADA-LANG-SKIPNAV", "TCPA-CONSENT")))


# ── 9. Fallback crawler captures <title> inside <head> ───────
print("\n9. Fallback re-crawl captures <title> (head is skipped for text, not title)")

served_html = (
    "<!doctype html><html lang=\"en\"><head>"
    "<meta charset=\"utf-8\">"
    "<title>New Century BMW | New &amp; Used BMW Dealer in Alhambra, CA</title>"
    "<script>var x = 'do not extract me';</script>"
    "<style>.h{display:none}</style>"
    "</head><body>"
    "<h1>Welcome to New Century BMW</h1>"
    "<p>Shop new and certified pre-owned BMW models.</p>"
    "</body></html>"
)
extracted = fallback_crawl.extract("homepage", "https://www.newcenturybmw.com", served_html)
test("fallback extract() yields a NON-EMPTY title",
     extracted["title"] != "", "got title=%r" % extracted["title"])
test("title text is the real <title>, not the head <script>/<style>",
     "New Century BMW" in extracted["title"]
     and "do not extract me" not in extracted["title"]
     and "display:none" not in extracted["title"],
     "got title=%r" % extracted["title"])
test("HTML entities in the title are unescaped",
     "New & Used" in extracted["title"], "got title=%r" % extracted["title"])
test("body text still extracted (skip logic intact)",
     "certified pre-owned" in extracted["text_excerpt"].lower()
     and "do not extract me" not in extracted["text_excerpt"])

# The captured title must flow through the title-based checks as a PASS,
# not the false positives the empty-title bug produced during the 2026-07
# Nissan of Irvine audit (false CRITICAL CA-DEALER-001 + false BRAND advisories).
served_crawl = {
    "url": "https://www.newcenturybmw.com", "brand": "bmw",
    "client": "New Century BMW", "crawl_date": "2026-07-09",
    "pages": {
        "homepage": {
            "url": "https://www.newcenturybmw.com",
            "title": extracted["title"],
            "dealer_name": "New Century BMW",
            "text_excerpt": extracted["text_excerpt"],
            "privacy": {"has_privacy_policy_link": True, "has_do_not_sell_link": True},
        }
    },
}
served_by = by_id(registry.run_checks(served_crawl, brand="bmw"))
_cad = served_by.get("CA-DEALER-001")
test("CA-DEALER-001 PASSES when dealer name is in the captured title (no false CRITICAL)",
     _cad and _cad.status == "pass",
     "got %r" % (_cad and (_cad.status, _cad.severity),))
_bit = served_by.get("BRAND-IN-TITLE")
test("BRAND-IN-TITLE PASSES when the brand is in the captured title (no false advisory)",
     _bit and _bit.status == "pass",
     "got %r" % (_bit and _bit.status,))

# Guard the bug directly: an empty title (the old behavior) WOULD have failed both.
empty_title_crawl = copy.deepcopy(served_crawl)
empty_title_crawl["pages"]["homepage"]["title"] = ""
empty_by = by_id(registry.run_checks(empty_title_crawl, brand="bmw"))
test("sanity: empty title WOULD false-fail CA-DEALER-001 (proves the test bites)",
     empty_by.get("CA-DEALER-001") and empty_by["CA-DEALER-001"].status == "fail")


# ── 10. McPeek 2026-08-06 regressions: hostname dealer_name + short "Privacy" anchor ─
print("\n10. McPeek regressions (hostname dealer_name, short 'Privacy' footer anchor)")
import re  # noqa: E402

# (a) dealer_name captured as the hostname → CA-DEALER-001 must be UNRESOLVED with
# human review, never the false CRITICAL the 2026-08-06 run shipped.
mcp_crawl = {
    "url": "https://www.mcpeeks.com", "brand": "cdjr", "client": "McPeek CDJR",
    "crawl_date": "2026-08-06",
    "pages": {"homepage": {
        "url": "https://www.mcpeeks.com",
        "title": "McPeek's Chrysler Dodge Jeep Ram Dealer | Anaheim, CA",
        "dealer_name": "www.mcpeeks.com",
        "text_excerpt": "Welcome to our Anaheim dealership."}}}
_mc = by_id(registry.run_checks(mcp_crawl, brand="cdjr")).get("CA-DEALER-001")
test("hostname dealer_name → CA-DEALER-001 UNRESOLVED, not a critical fail",
     _mc is not None and _mc.status == "unresolved" and _mc.severity != "critical",
     "got %r" % (_mc and (_mc.status, _mc.severity),))
test("hostname dealer_name is flagged for human review",
     _mc is not None and _mc.needs_human_review is True)

bare = copy.deepcopy(mcp_crawl)
bare["pages"]["homepage"]["dealer_name"] = "mcpeeks.com"
_mc2 = by_id(registry.run_checks(bare, brand="cdjr")).get("CA-DEALER-001")
test("bare-domain dealer_name (no www.) also treated as missing → UNRESOLVED",
     _mc2 is not None and _mc2.status == "unresolved")

real = copy.deepcopy(mcp_crawl)
real["pages"]["homepage"]["dealer_name"] = "McPeek's Chrysler Dodge Jeep Ram"
_mc3 = by_id(registry.run_checks(real, brand="cdjr")).get("CA-DEALER-001")
test("sanity: real dealer name in title still PASSES",
     _mc3 is not None and _mc3.status == "pass",
     "got %r" % (_mc3 and (_mc3.status, _mc3.severity),))

# (b) Short "Privacy" footer anchor must set has_privacy_policy_link true.
# The extraction runs as browser JS (references/page-extraction.md); no JS runtime is
# available offline, so we lint the spec for the fixed logic AND exercise a faithful
# Python mirror of its predicate against the real McPeek footer.
with open(os.path.join(SKILL_DIR, "references", "page-extraction.md")) as f:
    spec = f.read()
home_spec = spec.split("## Homepage Extraction JS")[1].split("## VLP")[0]
test("spec: dealer_name never derived from location.hostname",
     "location.hostname" not in home_spec)
test("spec: dealer_name cascade includes og:site_name, schema.org AutoDealer, logo alt",
     "og:site_name" in home_spec and "AutoDealer" in home_spec and "logoAlt" in home_spec)
test("spec: privacy link detection matches href, not just link text",
     "linkHref" in home_spec and re.search(r"privacyLink\s*=", home_spec) is not None
     and not re.search(r"privacyLink\s*=\s*linkSource\.find\(a => /privacy\\s\*policy/i\.test\(a\.textContent\)\);", home_spec))


def _js_privacy_link(anchors):
    """Python mirror of the privacyLink predicate in the Homepage Extraction JS."""
    for a in anchors:
        if re.search(r"privacy\s*policy", a["text"], re.I):
            return a
    for a in anchors:
        if re.search(r"privacy", a["text"], re.I) and \
           not re.search(r"choices|opt[\s-]*out|do\s*not\s*(sell|share)", a["text"], re.I):
            return a
    for a in anchors:
        if re.search(r"privacy", a["href"], re.I) and \
           not re.search(r"choices|opt[\s-]*out|do-?not-?(sell|share)", a["href"], re.I):
            return a
    return None


mcpeek_footer = [
    {"text": "Sitemap", "href": "https://www.mcpeeks.com/sitemap/"},
    {"text": "Privacy", "href": "https://www.mcpeeks.com/privacy/"},
    {"text": "Contact Us", "href": "https://www.mcpeeks.com/contact/"},
]
_pl = _js_privacy_link(mcpeek_footer)
test("short 'Privacy' anchor → has_privacy_policy_link true (McPeek footer)",
     _pl is not None and _pl["href"] == "https://www.mcpeeks.com/privacy/",
     "got %r" % (_pl,))
test("href-only match works (anchor text without the word 'privacy')",
     _js_privacy_link([{"text": "Your Rights", "href": "/privacy/"}]) is not None)
test("CPRA opt-out link is NOT mistaken for the policy link",
     _js_privacy_link([{"text": "Your Privacy Choices", "href": "/privacy-choices/"}]) is None)
test("policy link preferred when both policy and opt-out links exist",
     (_js_privacy_link([{"text": "Your Privacy Choices", "href": "/privacy-choices/"},
                        {"text": "Privacy", "href": "/privacy/"}]) or {}).get("href") == "/privacy/")

# (c) cascade guard: with the link detected, PRIV-004 must not fire even if a lead
# form itself lacks a privacy link (site-wide mechanism satisfies notice-at-collection).
cascade = {"url": "https://www.mcpeeks.com", "pages": {"homepage": {
    "url": "https://www.mcpeeks.com", "title": "McPeek's CDJR",
    "text_excerpt": "hi",
    "privacy": {"has_privacy_policy_link": True, "has_do_not_sell_link": False,
                "lead_forms_have_privacy_notice": [{"has_privacy_link": False,
                                                    "fields": ["name", "email", "phone"]}]}}}}
_p4 = by_id(registry.run_checks(cascade, brand="cdjr")).get("PRIV-004")
test("PRIV-004 does not fire once the privacy-policy link is detected",
     _p4 is None or _p4.status != "fail", "got %r" % (_p4 and _p4.status,))


# ── FTC Pricing Transparency FAQs (Sept. 2026) checks ──────────
print("\nFTC Pricing Transparency FAQs checks fire on violations and stay quiet on clean text")
def _ftc_site(pages):
    return {"url": "https://www.ftc-test.com", "brand": "cdjr", "client": "FTC Test", "crawl_date": "2026-09-16",
            "pages": {k: dict({"url": "https://www.ftc-test.com/" + k, "title": k, "disclaimers": []}, **v) for k, v in pages.items()}}
_ftc_bad = registry.run_checks(_ftc_site({
    "vdp": {"text_excerpt": "Total Price $40,000. Plus government fees and taxes, any finance charges, any dealer document processing charge, any electronic filing charge, and any emission testing charge. Sale price includes $1,500 dealer financing bonus."},
    "used": {"page_text_excerpt": "2019 Honda Civic $18,995. Stock photo shown, for illustration purposes only."},
    "specials": {"text_excerpt": "Lease for $399/mo for 36 months. $3,999 due at signing plus $85 doc fee. Plus tax and license."},
}), brand="cdjr")
_ftc_fail = {r.check_id: r for r in _ftc_bad if r.status == "fail"}
for cid in ["FTC-DOCFEE-CA", "FTC-COND-PRICE", "FTC-USED-STOCK-PHOTO", "FTC-LEASE-DAS-FEE"]:
    test("FTC check %s fires" % cid, cid in _ftc_fail, "fails were: %s" % sorted(_ftc_fail))
test("FTC findings are never criticals (staff views, human review)",
     all(r.severity != "critical" for r in _ftc_bad if r.framework == "FTC" and r.status == "fail"))
test("FTC findings cite the FAQ question",
     all("Pricing Transparency FAQs" in (r.statute or "") for r in _ftc_bad if r.framework == "FTC" and r.status == "fail"))
_ftc_ok = registry.run_checks(_ftc_site({
    "vdp": {"text_excerpt": "Price including document processing charge $40,085. Total Price $40,000. Document processing charge (not a governmental fee) $85. Plus government fees and taxes, any finance charges, any dealer document processing charge, any electronic filing charge, and any emission testing charge. Price available to all buyers. Military rebate $500 available separately to qualified buyers."},
    "used": {"page_text_excerpt": "2019 Honda Civic $18,995. Photos of the actual vehicle."},
    "specials": {"text_excerpt": "Lease for $399/mo for 36 months. $3,999 due at signing includes doc fee. Plus tax and license."},
}), brand="cdjr")
_ftc_ok_fail = sorted(r.check_id for r in _ftc_ok if r.status == "fail" and r.framework == "FTC")
test("FTC checks quiet on compliant FTC-style copy", not _ftc_ok_fail, "fired: %s" % _ftc_ok_fail)


# ── Summary ──────────────────────────────────────────────────
print("\n" + "=" * 56)
print("test_checks: %d passed, %d failed" % (passed, failed))
print("=" * 56)
sys.exit(0 if failed == 0 else 1)
