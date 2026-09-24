#!/usr/bin/env python3
"""
registry.py — Codified, assertable compliance checks.

Turns the 9 California advertising frameworks (ca_judgment_criteria.md #1-9),
the pricing/Reg M/Reg Z hard rules, and the OEM brand-guideline rules into a
single registry of discrete CHECKS. Each check is a pure function over crawl
data that returns one or more CheckResult objects.

Design contract (this is what makes the pipeline test-driven AND false-positive
resistant):

  status:
    "pass"       — the rule is satisfied, with textual evidence.
    "fail"       — the rule is violated, with an exact quote as evidence.
    "unresolved" — the check could NOT be decided from the data on hand.
                   This is NOT a violation. It carries `needs_data` describing
                   which page must be re-fetched. The verify loop re-crawls that
                   page (curl/urllib fallback) and re-runs the check. Reporting an
                   unresolved item as a violation is exactly the false positive we
                   refuse to emit.

  confidence: high | medium | low
    Visual/layout judgments (font size, prominence, contrast) can never be
    "high" from text alone — those resolve to medium + needs_human_review, never
    a critical. The only path to a high-confidence fail is exact textual evidence.

Python 3.9+, stdlib only.
"""

import re
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Callable

# Browser-JS extraction caps from SKILL.md. A page whose excerpt length lands at
# (cap - SLACK) was almost certainly truncated mid-content — the #1 source of
# "disclaimer missing" false positives. Such pages drive the fallback re-crawl.
PAGE_CAPS = {
    "homepage": 15000,
    "specials": 12000,
    "vdp": 8000,
    "privacy_policy": 8000,
    "vlp": 5000,
    "used": 5000,
    "cpo": 5000,
    "finance": 5000,
}
TRUNCATION_SLACK = 200


@dataclass
class CheckResult:
    check_id: str
    framework: str            # F1..F9, PRICING, BRAND
    framework_title: str
    page: str
    status: str               # pass | fail | unresolved
    confidence: str           # high | medium | low
    evidence: str = ""
    severity: str = ""        # critical | warning | advisory (set when fail)
    rule_id: str = ""         # statute or brand-rule linkage
    statute: str = ""
    recommendation: str = ""
    needs_human_review: bool = False
    needs_data: Optional[dict] = None   # {"page","url","reason"} → re-crawl target
    reverified: bool = False            # set True by the verify loop after re-fetch
    page_url: str = ""                  # url of the page this result is about

    def to_dict(self):
        return asdict(self)


# ── extraction helpers ───────────────────────────────────────

def _excerpt(page):
    for k in ("text_excerpt", "page_text_excerpt"):
        if page.get(k):
            return page[k]
    return ""


def _all_text(page):
    parts = []
    for k in ("text_excerpt", "page_text_excerpt"):
        if page.get(k):
            parts.append(page[k])
    for d in page.get("disclaimers", []) or []:
        if isinstance(d, str):
            parts.append(d)
    return "\n".join(parts)


def _disclaimer_text(page):
    return "\n".join(d for d in (page.get("disclaimers") or []) if isinstance(d, str))


def is_truncated(page_key, page):
    """True if this page's excerpt looks cut off at the browser cap."""
    if not page or page.get("error"):
        return False
    cap = PAGE_CAPS.get(page_key)
    if not cap:
        return False
    ex = _excerpt(page)
    if not ex:
        return False
    if len(ex) >= cap - TRUNCATION_SLACK:
        return True
    # ended mid-sentence with no terminal punctuation is also suspect
    if len(ex) > 1000 and ex[-1] not in ".!?)”\"' \n\t":
        return True
    return False


def _need(page_key, page, reason):
    return {"page": page_key, "url": page.get("url", ""), "reason": reason}


def _short(text, n=180):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:n]


# ── the registry ─────────────────────────────────────────────
# Each entry: (check_id, framework, framework_title, page_keys, fn)
# fn(page_key, page, ctx) -> Optional[CheckResult]   (None == not applicable)
_REGISTRY: List[tuple] = []


def check(check_id, framework, framework_title, pages):
    def deco(fn):
        _REGISTRY.append((check_id, framework, framework_title, pages, fn))
        return fn
    return deco


# ══════════════════════════════════════════════════════════════
# PRICING — total price, doc fee, Reg M lease, Reg Z finance, OAC
# ══════════════════════════════════════════════════════════════

PRICE_RE = re.compile(r"\$[\d,]{3,}")
PAYMENT_RE = re.compile(r"\$[\d,]+\s*(?:/mo|per\s*month|a\s*month|monthly)", re.I)


@check("PRICING-EVERYONE-FINANCED", "PRICING", "Pricing / Credit Advertising",
       ["finance", "specials", "homepage"])
def _everyone_financed(page_key, page, ctx):
    text = _all_text(page)
    m = re.search(r"everyone\s+(?:is\s+)?financed|guaranteed\s+(?:credit|financing|approval)"
                  r"|no\s+credit\s+(?:rejected|refused|turned\s+down)|bad\s+credit\s+no\s+problem",
                  text, re.I)
    if m:
        return CheckResult(
            check_id="PRICING-EVERYONE-FINANCED", framework="PRICING",
            framework_title="Pricing / Credit Advertising", page=page_key,
            status="fail", confidence="high", severity="critical",
            rule_id="CA-CREDIT-002", statute="VC §11713; B&P §17500",
            evidence=_short(m.group(0)),
            recommendation="Remove guaranteed-credit / everyone-financed language; "
                           "it is a per se deceptive credit claim under CA law.")
    return None


@check("PRICING-OAC-SPELLED", "PRICING", "Pricing / Credit Advertising",
       ["finance", "specials"])
def _oac(page_key, page, ctx):
    text = _all_text(page)
    if re.search(r"\bO\.?A\.?C\.?\b", text) and not re.search(r"on\s+approved\s+credit", text, re.I):
        return CheckResult(
            check_id="PRICING-OAC-SPELLED", framework="PRICING",
            framework_title="Pricing / Credit Advertising", page=page_key,
            status="fail", confidence="high", severity="advisory",
            rule_id="CA-CREDIT-004", statute="VC §11713.1",
            evidence="'OAC' abbreviation used without 'on approved credit' spelled out",
            recommendation="Spell out 'on approved credit' at least once; abbreviation alone is not a clear disclosure.")
    return None


@check("PRICING-LEASE-REGM", "PRICING", "Pricing / Reg M Lease Disclosure",
       ["specials", "homepage"])
def _lease_regm(page_key, page, ctx):
    text = _all_text(page)
    has_lease = page.get("has_lease_offers") or bool(PAYMENT_RE.search(text)) or re.search(r"\blease\b", text, re.I)
    if not has_lease:
        return None
    required = {
        "term (months)": r"\d+\s*month",
        "due at signing": r"due\s+at\s+signing|due\s+at\s+lease\s+signing|cash\s+due",
        "amount/payment": r"\$[\d,]+",
        "mileage allowance": r"mile|mileage",
        "capitalized cost / residual": r"capitalized\s+cost|cap\s+cost|residual",
    }
    missing = [name for name, pat in required.items() if not re.search(pat, text, re.I)]
    if not missing:
        return CheckResult(
            check_id="PRICING-LEASE-REGM", framework="PRICING",
            framework_title="Pricing / Reg M Lease Disclosure", page=page_key,
            status="pass", confidence="high",
            rule_id="CA-LEASE-001", statute="Reg M 12 CFR 1013; VC §11713.16",
            evidence="Lease offer carries term, due-at-signing, payment, mileage and cap-cost/residual terms.")
    # missing terms — but if the page is truncated the terms may be in the cut tail
    if is_truncated(page_key, page):
        return CheckResult(
            check_id="PRICING-LEASE-REGM", framework="PRICING",
            framework_title="Pricing / Reg M Lease Disclosure", page=page_key,
            status="unresolved", confidence="low",
            rule_id="CA-LEASE-001", statute="Reg M 12 CFR 1013",
            evidence="Lease terms appear incomplete (" + ", ".join(missing) + ") but page text is truncated.",
            needs_data=_need(page_key, page, "specials excerpt truncated; missing lease terms may be in cut tail or behind expand"),
            needs_human_review=True)
    sev = "warning" if len(missing) >= 3 else "advisory"
    return CheckResult(
        check_id="PRICING-LEASE-REGM", framework="PRICING",
        framework_title="Pricing / Reg M Lease Disclosure", page=page_key,
        status="fail", confidence="high", severity=sev,
        rule_id="CA-LEASE-001", statute="Reg M 12 CFR 1013; VC §11713.16",
        evidence="Lease offer is missing required term(s): " + ", ".join(missing),
        recommendation="Add the missing Reg M lease disclosures clear-and-conspicuous near the payment.")


@check("PRICING-FINANCE-REGZ", "PRICING", "Pricing / Reg Z Finance Disclosure",
       ["finance", "specials", "homepage", "vdp"])
def _finance_regz(page_key, page, ctx):
    text = _all_text(page)
    # Reg Z triggers on FINANCE context only. A bare "36 months" belongs to a lease
    # (Reg M) and must not trip this check — that was a real false positive.
    triggers = re.search(r"\bAPR\b|\$[\d,]+\s*down\b|finance\s+(?:for|at|your)|"
                         r"as\s+low\s+as\s+[\d.]+\s*%|\d+\s*month.{0,30}\bAPR\b", text, re.I)
    if not triggers:
        return None
    has_apr = re.search(r"\bAPR\b|annual\s+percentage\s+rate", text, re.I)
    has_terms = re.search(r"\d+\s*month|\d+\s*mo\b", text, re.I)
    if has_apr and has_terms:
        return CheckResult(
            check_id="PRICING-FINANCE-REGZ", framework="PRICING",
            framework_title="Pricing / Reg Z Finance Disclosure", page=page_key,
            status="pass", confidence="high",
            rule_id="CA-CREDIT-001", statute="Reg Z 12 CFR 1026.24",
            evidence="Finance offer states APR and term.")
    if is_truncated(page_key, page):
        return CheckResult(
            check_id="PRICING-FINANCE-REGZ", framework="PRICING",
            framework_title="Pricing / Reg Z Finance Disclosure", page=page_key,
            status="unresolved", confidence="low",
            rule_id="CA-CREDIT-001", statute="Reg Z 12 CFR 1026.24",
            evidence="Finance trigger terms present but APR/term not both found; page truncated.",
            needs_data=_need(page_key, page, "finance excerpt truncated; APR/term may be in cut tail"),
            needs_human_review=True)
    return CheckResult(
        check_id="PRICING-FINANCE-REGZ", framework="PRICING",
        framework_title="Pricing / Reg Z Finance Disclosure", page=page_key,
        status="fail", confidence="high", severity="warning",
        rule_id="CA-CREDIT-001", statute="Reg Z 12 CFR 1026.24",
        evidence="Finance trigger term used without both APR and term disclosed.",
        recommendation="When advertising a finance trigger (down payment, term, 'as low as'), disclose APR and term together.")


# ══════════════════════════════════════════════════════════════
# F1 — Clear and Conspicuous
# ══════════════════════════════════════════════════════════════

@check("F1-PRICE-HAS-DISCLAIMER", "F1", "Clear and Conspicuous", ["specials", "vdp"])
def _f1_disclaimer_present(page_key, page, ctx):
    text = _excerpt(page)
    prices = bool(PRICE_RE.search(text)) or bool(page.get("prices_found")) or bool(page.get("lease_payments"))
    if not prices:
        return None
    disc = _disclaimer_text(page)
    if disc.strip():
        return CheckResult(
            check_id="F1-PRICE-HAS-DISCLAIMER", framework="F1",
            framework_title="Clear and Conspicuous", page=page_key,
            status="pass", confidence="medium",
            rule_id="CA-DISC-001", statute="VC §11713.16(i)",
            evidence="Price/payment claim has an associated disclaimer block (visual prominence still needs human eyes).",
            needs_human_review=True)
    # No disclaimer text captured. If truncated/expandable, this is the classic
    # false-positive trap — defer to fallback re-crawl instead of flagging.
    if is_truncated(page_key, page) or page.get("disclaimer_buttons_clicked"):
        return CheckResult(
            check_id="F1-PRICE-HAS-DISCLAIMER", framework="F1",
            framework_title="Clear and Conspicuous", page=page_key,
            status="unresolved", confidence="low",
            rule_id="CA-DISC-001", statute="VC §11713.16(i)",
            evidence="Priced page shows no disclaimer text, but content was truncated or behind expand buttons.",
            needs_data=_need(page_key, page, "re-fetch full HTML to confirm whether a disclaimer actually exists"),
            needs_human_review=True)
    return CheckResult(
        check_id="F1-PRICE-HAS-DISCLAIMER", framework="F1",
        framework_title="Clear and Conspicuous", page=page_key,
        status="fail", confidence="high", severity="warning",
        rule_id="CA-DISC-001", statute="VC §11713.16(i)",
        evidence="Advertised price/payment on this page with no qualifying disclaimer found anywhere in the page.",
        recommendation="Add a clear-and-conspicuous disclaimer adjacent to the advertised price/payment.")


# ══════════════════════════════════════════════════════════════
# F2 — Puffery vs Factual Claims
# ══════════════════════════════════════════════════════════════

# Marketing superlatives that imply a measurable, substantiable claim. Kept
# tight to dealer-advertising tropes so ordinary English ("best way to reach us",
# "most current information") does not trip it. Merged from the former
# analyze_local.py CA-COMPARE-001 coverage so the registry is the single source.
SUPERLATIVE_RE = re.compile(
    r"#\s*1\b|\bnumber\s+one\b|\bno\.?\s*1\b"
    r"|\b(?:the\s+)?(?:lowest|best)\s+price|\bbest\s+(?:deal|value|offer|selection|service)"
    r"|\b(?:the\s+)?most\s+(?:affordable|competitive|trusted|reliable)"
    r"|\bhighest[\s-]*(?:rated|volume)|\btop[\s-]*rated"
    r"|\b(?:the\s+)?(?:leading|largest|biggest)\s+(?:dealer|dealership|volume|inventory|selection)"
    r"|\blargest\b|\bguaranteed\s+(?:lowest|best)|\bunbeatable\b", re.I)


@check("F2-SUPERLATIVE-SUBSTANTIATED", "F2", "Puffery vs Factual Claims",
       ["homepage", "specials"])
def _f2_superlative(page_key, page, ctx):
    text = _all_text(page)
    m = SUPERLATIVE_RE.search(text)
    if not m:
        return None
    window = text[max(0, m.start() - 160): m.end() + 160]
    if re.search(r"based\s+on|according\s+to|source[:\s]|per\s+\w+\s+data|as\s+rated\s+by", window, re.I):
        return CheckResult(
            check_id="F2-SUPERLATIVE-SUBSTANTIATED", framework="F2",
            framework_title="Puffery vs Factual Claims", page=page_key,
            status="pass", confidence="high", rule_id="CA-COMP-001",
            statute="B&P §17508",
            evidence="Factual superlative '%s' carries a substantiation/source reference." % _short(m.group(0), 40))
    return CheckResult(
        check_id="F2-SUPERLATIVE-SUBSTANTIATED", framework="F2",
        framework_title="Puffery vs Factual Claims", page=page_key,
        status="fail", confidence="high", severity="warning",
        rule_id="CA-COMP-001", statute="B&P §17508",
        evidence="Measurable claim '%s' with no visible substantiation/source." % _short(m.group(0), 40),
        recommendation="Cite the source/basis for the ranking claim, or change to non-factual puffery.")


# ══════════════════════════════════════════════════════════════
# F3 — Payment Advertising Adequacy
# ══════════════════════════════════════════════════════════════

@check("F3-PAYMENT-HAS-CONTEXT", "F3", "Payment Advertising Adequacy", ["specials"])
def _f3_payment_context(page_key, page, ctx):
    text = _all_text(page)
    payments = page.get("lease_payments") or PAYMENT_RE.findall(text)
    if not payments:
        return None
    has_term = bool(page.get("lease_terms")) or bool(re.search(r"\d+\s*month", text, re.I))
    if has_term:
        return CheckResult(
            check_id="F3-PAYMENT-HAS-CONTEXT", framework="F3",
            framework_title="Payment Advertising Adequacy", page=page_key,
            status="pass", confidence="high", rule_id="CA-LEASE-002",
            statute="VC §11713.16",
            evidence="Advertised payment is shown with a term.")
    if is_truncated(page_key, page):
        return CheckResult(
            check_id="F3-PAYMENT-HAS-CONTEXT", framework="F3",
            framework_title="Payment Advertising Adequacy", page=page_key,
            status="unresolved", confidence="low", rule_id="CA-LEASE-002",
            statute="VC §11713.16",
            evidence="Payment shown without a term, but page truncated.",
            needs_data=_need(page_key, page, "term may be in truncated tail"),
            needs_human_review=True)
    return CheckResult(
        check_id="F3-PAYMENT-HAS-CONTEXT", framework="F3",
        framework_title="Payment Advertising Adequacy", page=page_key,
        status="fail", confidence="high", severity="warning",
        rule_id="CA-LEASE-002", statute="VC §11713.16",
        evidence="Monthly payment advertised with no term/conditions identified.",
        recommendation="Show the lease/finance term and conditions adjacent to each advertised payment.")


# ══════════════════════════════════════════════════════════════
# F4 — Rebate Stacking Disclosure
# ══════════════════════════════════════════════════════════════

REBATE_RE = re.compile(r"loyalty|conquest|military|first\s+responder|college\s+grad|recent\s+grad"
                       r"|lease\s+loyalty|owner\s+loyalty|costco|friends\s+&?\s+family", re.I)


@check("F4-REBATE-QUALIFICATION", "F4", "Rebate Stacking Disclosure", ["specials"])
def _f4_rebate(page_key, page, ctx):
    text = _all_text(page)
    rebates = set(m.group(0).lower() for m in REBATE_RE.finditer(text))
    if len(rebates) < 2:
        return None
    if re.search(r"not\s+all\s+(?:customers|buyers)\s+(?:will\s+)?qualify|see\s+dealer\s+for\s+details"
                 r"|cannot\s+be\s+combined|may\s+not\s+qualify|select\s+customers", text, re.I):
        return CheckResult(
            check_id="F4-REBATE-QUALIFICATION", framework="F4",
            framework_title="Rebate Stacking Disclosure", page=page_key,
            status="pass", confidence="high", rule_id="CA-PRICE-004",
            statute="VC §11713.1",
            evidence="Stacked rebates (%s) carry qualification language." % _short(", ".join(sorted(rebates)), 80))
    if is_truncated(page_key, page):
        return CheckResult(
            check_id="F4-REBATE-QUALIFICATION", framework="F4",
            framework_title="Rebate Stacking Disclosure", page=page_key,
            status="unresolved", confidence="low", rule_id="CA-PRICE-004",
            statute="VC §11713.1",
            evidence="Multiple rebates with no qualification text, but page truncated.",
            needs_data=_need(page_key, page, "rebate qualification text may be in truncated tail"),
            needs_human_review=True)
    return CheckResult(
        check_id="F4-REBATE-QUALIFICATION", framework="F4",
        framework_title="Rebate Stacking Disclosure", page=page_key,
        status="fail", confidence="high", severity="warning",
        rule_id="CA-PRICE-004", statute="VC §11713.1",
        evidence="Multiple stacked rebates (%s) with no 'not all customers qualify' disclosure." % _short(", ".join(sorted(rebates)), 80),
        recommendation="Disclose that not all customers qualify for every rebate and state which are mutually exclusive.")


# ══════════════════════════════════════════════════════════════
# F5 — Sale / Savings Substantiation
# ══════════════════════════════════════════════════════════════

SALE_RE = re.compile(r"\bsale\b|clearance|blowout|\bevent\b|markdown|liquidation", re.I)
DATE_RE = re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}"
                     r"|\d{1,2}/\d{1,2}(?:/\d{2,4})?|through\s+\w+\s+\d{1,2}|ends?\s+\w+\s+\d{1,2}"
                     r"|expires?\s+\d", re.I)


@check("F5-SALE-HAS-DATES", "F5", "Sale / Savings Substantiation", ["specials", "homepage"])
def _f5_sale_dates(page_key, page, ctx):
    text = _all_text(page)
    m = SALE_RE.search(text)
    if not m:
        return None
    if DATE_RE.search(text):
        return CheckResult(
            check_id="F5-SALE-HAS-DATES", framework="F5",
            framework_title="Sale / Savings Substantiation", page=page_key,
            status="pass", confidence="high", rule_id="CA-SALE-001",
            statute="B&P §17501",
            evidence="Sale/event language carries a visible date range.")
    return CheckResult(
        check_id="F5-SALE-HAS-DATES", framework="F5",
        framework_title="Sale / Savings Substantiation", page=page_key,
        status="fail", confidence="high", severity="warning",
        rule_id="CA-SALE-001", statute="B&P §17501",
        evidence="'%s' language with no start/end date (perpetual-sale risk)." % _short(m.group(0), 30),
        recommendation="Add genuine start/end dates to sale/savings claims; perpetual sales imply no real prior price.")


# ══════════════════════════════════════════════════════════════
# F6 — Digital Disclaimer Adequacy (asterisk linkage)
# ══════════════════════════════════════════════════════════════

@check("F6-ASTERISK-LINKED", "F6", "Digital Disclaimer Adequacy", ["specials", "homepage"])
def _f6_asterisk(page_key, page, ctx):
    text = _excerpt(page)
    if "*" not in text and "†" not in text:
        return None
    if not (PRICE_RE.search(text) or PAYMENT_RE.search(text)):
        return None
    disc = _disclaimer_text(page)
    if "*" in disc or re.search(r"see\s+dealer|details\s+apply|disclaimer", disc, re.I):
        return CheckResult(
            check_id="F6-ASTERISK-LINKED", framework="F6",
            framework_title="Digital Disclaimer Adequacy", page=page_key,
            status="pass", confidence="medium", rule_id="CA-DISC-002",
            statute="VC §11713.16(i)",
            evidence="Asterisk/footnote marker has a corresponding disclaimer block.",
            needs_human_review=True)
    if is_truncated(page_key, page) or page.get("disclaimer_buttons_clicked"):
        return CheckResult(
            check_id="F6-ASTERISK-LINKED", framework="F6",
            framework_title="Digital Disclaimer Adequacy", page=page_key,
            status="unresolved", confidence="low", rule_id="CA-DISC-002",
            statute="VC §11713.16(i)",
            evidence="Asterisk marker present but matching footnote not captured; content truncated/expandable.",
            needs_data=_need(page_key, page, "re-fetch to locate the footnote the asterisk points to"),
            needs_human_review=True)
    return CheckResult(
        check_id="F6-ASTERISK-LINKED", framework="F6",
        framework_title="Digital Disclaimer Adequacy", page=page_key,
        status="fail", confidence="medium", severity="warning",
        rule_id="CA-DISC-002", statute="VC §11713.16(i)",
        evidence="Asterisk/footnote marker on a priced claim with no corresponding disclosure found.",
        recommendation="Ensure every asterisk resolves to a readable, nearby disclosure.",
        needs_human_review=True)


# ══════════════════════════════════════════════════════════════
# F7 — Lease "Due at Signing" Accuracy
# ══════════════════════════════════════════════════════════════

@check("F7-DUE-AT-SIGNING", "F7", "Lease Due-at-Signing Accuracy", ["specials"])
def _f7_das(page_key, page, ctx):
    text = _all_text(page)
    has_lease = page.get("has_lease_offers") or bool(PAYMENT_RE.search(text)) or re.search(r"\blease\b", text, re.I)
    if not has_lease:
        return None
    zero_das = re.search(r"\$0\s+due\s+at\s+signing|zero\s+due\s+at\s+signing|nothing\s+due\s+at\s+signing", text, re.I)
    other_fees = re.search(r"acquisition\s+fee|first\s+(?:month'?s?\s+)?payment|security\s+deposit|cap(?:italized)?\s+cost\s+reduction", text, re.I)
    if zero_das and other_fees:
        return CheckResult(
            check_id="F7-DUE-AT-SIGNING", framework="F7",
            framework_title="Lease Due-at-Signing Accuracy", page=page_key,
            status="fail", confidence="high", severity="warning",
            rule_id="CA-LEASE-003", statute="Reg M 12 CFR 1013.4",
            evidence="'$0 due at signing' contradicted by fees/first-payment language on the same page.",
            recommendation="If acquisition fee, first payment, or cap-cost reduction is due, do not advertise $0 due at signing.")
    if re.search(r"due\s+at\s+signing|cash\s+due\s+at\s+(?:signing|lease)", text, re.I):
        return CheckResult(
            check_id="F7-DUE-AT-SIGNING", framework="F7",
            framework_title="Lease Due-at-Signing Accuracy", page=page_key,
            status="pass", confidence="high", rule_id="CA-LEASE-003",
            statute="Reg M 12 CFR 1013.4",
            evidence="Lease offer discloses a due-at-signing amount.")
    if is_truncated(page_key, page):
        return CheckResult(
            check_id="F7-DUE-AT-SIGNING", framework="F7",
            framework_title="Lease Due-at-Signing Accuracy", page=page_key,
            status="unresolved", confidence="low", rule_id="CA-LEASE-003",
            statute="Reg M 12 CFR 1013.4",
            evidence="No due-at-signing amount found, but page truncated.",
            needs_data=_need(page_key, page, "due-at-signing may be in truncated tail"),
            needs_human_review=True)
    return CheckResult(
        check_id="F7-DUE-AT-SIGNING", framework="F7",
        framework_title="Lease Due-at-Signing Accuracy", page=page_key,
        status="fail", confidence="high", severity="warning",
        rule_id="CA-LEASE-003", statute="Reg M 12 CFR 1013.4",
        evidence="Lease offer with no due-at-signing amount disclosed.",
        recommendation="Disclose total due at signing with equal prominence to the monthly payment.")


# ══════════════════════════════════════════════════════════════
# F8 — Vehicle History / Condition Representations
# ══════════════════════════════════════════════════════════════

CONDITION_RE = re.compile(r"no\s+accidents?|clean\s+title|like\s+new|pristine|mint\s+condition|accident[\s-]free", re.I)


@check("F8-CONDITION-SUBSTANTIATED", "F8", "Vehicle History / Condition", ["used", "cpo", "vdp"])
def _f8_condition(page_key, page, ctx):
    text = _all_text(page)
    m = CONDITION_RE.search(text)
    if not m:
        return None
    if re.search(r"carfax|autocheck|vehicle\s+history\s+report|per\s+report|see\s+report", text, re.I):
        return CheckResult(
            check_id="F8-CONDITION-SUBSTANTIATED", framework="F8",
            framework_title="Vehicle History / Condition", page=page_key,
            status="pass", confidence="high", rule_id="CA-VHIST-001",
            statute="B&P §17531",
            evidence="Condition claim '%s' is tied to a history-report reference." % _short(m.group(0), 30))
    return CheckResult(
        check_id="F8-CONDITION-SUBSTANTIATED", framework="F8",
        framework_title="Vehicle History / Condition", page=page_key,
        status="fail", confidence="medium", severity="advisory",
        rule_id="CA-VHIST-001", statute="B&P §17531",
        evidence="Condition claim '%s' with no Carfax/history-report substantiation found." % _short(m.group(0), 30),
        recommendation="Tie 'no accidents'/'clean title' claims to a referenced vehicle-history report.",
        needs_human_review=True)


# ══════════════════════════════════════════════════════════════
# F9 — Environmental / Fuel Economy Claims
# ══════════════════════════════════════════════════════════════

MPG_RE = re.compile(r"\d+\s*mpg|\d+\s*miles?\s+per\s+gallon|\d+\s*mile\s+range|\bmpge\b|\d+\s*mi\s+range", re.I)


@check("F9-MPG-EPA", "F9", "Environmental / Fuel Economy", ["vdp", "specials", "homepage"])
def _f9_mpg(page_key, page, ctx):
    text = _all_text(page)
    m = MPG_RE.search(text)
    if not m:
        return None
    if re.search(r"\bEPA\b|epa[\s-]*estimat|epa[\s-]*rated", text, re.I):
        return CheckResult(
            check_id="F9-MPG-EPA", framework="F9",
            framework_title="Environmental / Fuel Economy", page=page_key,
            status="pass", confidence="high", rule_id="CA-FUEL-001",
            statute="16 CFR 259",
            evidence="MPG/range claim '%s' references EPA estimate." % _short(m.group(0), 30))
    return CheckResult(
        check_id="F9-MPG-EPA", framework="F9",
        framework_title="Environmental / Fuel Economy", page=page_key,
        status="fail", confidence="high", severity="warning",
        rule_id="CA-FUEL-001", statute="16 CFR 259",
        evidence="MPG/range claim '%s' without EPA-estimate qualifier." % _short(m.group(0), 30),
        recommendation="Qualify fuel-economy/range claims as EPA-estimated.")


# ══════════════════════════════════════════════════════════════
# BRAND — OEM guideline checks (driven by brands/{brand}_guidelines.json)
# ══════════════════════════════════════════════════════════════

@check("BRAND-IN-TITLE", "BRAND", "OEM Brand Guidelines", ["homepage"])
def _brand_in_title(page_key, page, ctx):
    brand = (ctx.get("brand") or "").lower()
    label = {"bmw": "BMW", "nissan": "Nissan", "cdjr": "Chrysler/Dodge/Jeep/Ram",
             "chevrolet": "Chevrolet", "chevy": "Chevrolet", "harley": "Harley-Davidson"}.get(brand)
    if not label:
        return None
    title = (page.get("title") or "")
    needle = "harley" if brand == "harley" else (brand if brand in ("bmw", "nissan", "chevrolet") else None)
    if brand in ("cdjr",):
        present = bool(re.search(r"chrysler|dodge|jeep|ram|cdjr", title, re.I))
    elif needle:
        present = needle in title.lower()
    else:
        present = True
    if present:
        return CheckResult(
            check_id="BRAND-IN-TITLE", framework="BRAND",
            framework_title="OEM Brand Guidelines", page=page_key,
            status="pass", confidence="high",
            rule_id=ctx.get("brand_rule_ids", {}).get("title", "BRAND-WEB-TITLE"),
            evidence="Brand name appears in the homepage <title>.")
    return CheckResult(
        check_id="BRAND-IN-TITLE", framework="BRAND",
        framework_title="OEM Brand Guidelines", page=page_key,
        status="fail", confidence="high", severity="advisory",
        rule_id=ctx.get("brand_rule_ids", {}).get("title", "BRAND-WEB-TITLE"),
        evidence="Homepage <title> '%s' does not contain the %s brand name." % (_short(title, 60), label),
        recommendation="Include the OEM brand name in the homepage title per OEM website guidelines.")


@check("BRAND-CPO-PAGE", "BRAND", "OEM Brand Guidelines", ["used", "cpo", "homepage"])
def _brand_cpo(page_key, page, ctx):
    # Only assert on the page that is supposed to host CPO content
    if page_key not in ("cpo", "used"):
        return None
    text = _all_text(page)
    if re.search(r"certified\s+pre-?owned|\bcpo\b", text, re.I) or page.get("has_cpo_section"):
        return CheckResult(
            check_id="BRAND-CPO-PAGE", framework="BRAND",
            framework_title="OEM Brand Guidelines", page=page_key,
            status="pass", confidence="high",
            rule_id=ctx.get("brand_rule_ids", {}).get("cpo", "BRAND-CPO-001"),
            evidence="Certified Pre-Owned program content present.")
    return CheckResult(
        check_id="BRAND-CPO-PAGE", framework="BRAND",
        framework_title="OEM Brand Guidelines", page=page_key,
        status="unresolved", confidence="low",
        rule_id=ctx.get("brand_rule_ids", {}).get("cpo", "BRAND-CPO-001"),
        evidence="No CPO content found on the used/cpo page captured.",
        needs_data=_need(page_key, page, "confirm whether a CPO section exists by re-fetching"),
        needs_human_review=True)


@check("BRAND-EXCLUSIVITY", "BRAND", "OEM Brand Guidelines", ["homepage"])
def _brand_exclusivity(page_key, page, ctx):
    brand = (ctx.get("brand") or "").lower()
    text = _all_text(page)
    competitors = {
        "bmw": r"mercedes|audi|lexus|acura|infiniti",
        "nissan": r"toyota|honda|mazda|hyundai|kia",
        "cdjr": r"ford|chevrolet|toyota|gmc",
        "chevrolet": r"ford|ram|gmc|toyota",
        "harley": r"indian\s+motorcycle|honda|yamaha|kawasaki|ducati",
    }.get(brand)
    if not competitors:
        return None
    m = re.search(competitors, text, re.I)
    if not m:
        return CheckResult(
            check_id="BRAND-EXCLUSIVITY", framework="BRAND",
            framework_title="OEM Brand Guidelines", page=page_key,
            status="pass", confidence="medium",
            rule_id=ctx.get("brand_rule_ids", {}).get("exclusivity", "BRAND-EXCL-001"),
            evidence="No competing-brand references found on the homepage text.",
            needs_human_review=True)
    return CheckResult(
        check_id="BRAND-EXCLUSIVITY", framework="BRAND",
        framework_title="OEM Brand Guidelines", page=page_key,
        status="fail", confidence="medium", severity="warning",
        rule_id=ctx.get("brand_rule_ids", {}).get("exclusivity", "BRAND-EXCL-001"),
        evidence="Competing brand '%s' referenced on a co-op homepage (exclusivity risk)." % _short(m.group(0), 30),
        recommendation="Remove competing-brand references from co-op-funded brand pages.",
        needs_human_review=True)


# ══════════════════════════════════════════════════════════════
# PRIVACY — CCPA / CPRA  (ported from analyze_local.py; now re-crawl aware)
# ══════════════════════════════════════════════════════════════
# These run only when the crawl actually captured the structured `privacy`
# object. Absence of that object means "not extracted", NOT "no link" — so we
# return None rather than emit a false critical. Where a required link is not
# found we also text-search the page (so a fallback re-crawl that recovers the
# full footer can flip the result to pass instead of shipping a false positive).

def _has_signal(privacy, flag_key, page_text, text_pat):
    return bool(privacy.get(flag_key)) or bool(re.search(text_pat, page_text, re.I))


@check("PRIV-001", "PRIVACY", "CCPA/CPRA Privacy", ["homepage"])
def _priv_policy_link(page_key, page, ctx):
    privacy = page.get("privacy")
    if not isinstance(privacy, dict):
        return None
    text = _all_text(page)
    if _has_signal(privacy, "has_privacy_policy_link", text, r"privacy\s*policy"):
        return CheckResult("PRIV-001", "PRIVACY", "CCPA/CPRA Privacy", page_key,
                           status="pass", confidence="high", rule_id="CA-PRIV-001",
                           statute="Cal. Civ. Code §1798.130(a)(5)",
                           evidence="Privacy Policy link present.")
    if is_truncated(page_key, page):
        return CheckResult("PRIV-001", "PRIVACY", "CCPA/CPRA Privacy", page_key,
                           status="unresolved", confidence="low", rule_id="CA-PRIV-001",
                           statute="Cal. Civ. Code §1798.130(a)(5)",
                           evidence="No Privacy Policy link captured, but homepage was truncated.",
                           needs_data=_need(page_key, page, "re-fetch full homepage/footer to confirm Privacy Policy link"),
                           needs_human_review=True)
    return CheckResult("PRIV-001", "PRIVACY", "CCPA/CPRA Privacy", page_key,
                       status="fail", confidence="high", severity="critical",
                       rule_id="CA-PRIV-001", statute="Cal. Civ. Code §1798.130(a)(5), CCPA/CPRA",
                       evidence="No Privacy Policy link found in homepage footer or navigation.",
                       recommendation="Add a clearly visible 'Privacy Policy' link to the website footer, accessible from every page.")


@check("PRIV-002", "PRIVACY", "CCPA/CPRA Privacy", ["homepage"])
def _priv_do_not_sell(page_key, page, ctx):
    privacy = page.get("privacy")
    if not isinstance(privacy, dict):
        return None
    text = _all_text(page)
    if _has_signal(privacy, "has_do_not_sell_link", text, r"do\s*not\s*sell|do\s*not\s*share|opt[\s-]*out\s+of\s+(?:sale|sharing)"):
        return CheckResult("PRIV-002", "PRIVACY", "CCPA/CPRA Privacy", page_key,
                           status="pass", confidence="high", rule_id="CA-PRIV-002",
                           statute="Cal. Civ. Code §1798.135(a)",
                           evidence="'Do Not Sell or Share' opt-out link present.")
    if is_truncated(page_key, page):
        return CheckResult("PRIV-002", "PRIVACY", "CCPA/CPRA Privacy", page_key,
                           status="unresolved", confidence="low", rule_id="CA-PRIV-002",
                           statute="Cal. Civ. Code §1798.135(a)",
                           evidence="No 'Do Not Sell or Share' link captured, but homepage was truncated.",
                           needs_data=_need(page_key, page, "re-fetch full homepage/footer to confirm Do-Not-Sell link"),
                           needs_human_review=True)
    return CheckResult("PRIV-002", "PRIVACY", "CCPA/CPRA Privacy", page_key,
                       status="fail", confidence="high", severity="critical",
                       rule_id="CA-PRIV-002", statute="Cal. Civ. Code §1798.135(a), CPRA",
                       evidence="No 'Do Not Sell or Share My Personal Information' link found on homepage.",
                       recommendation="Add a clear and conspicuous 'Do Not Sell or Share My Personal Information' link. "
                                      "Dealer sites using tracking pixels, Google Analytics, or remarketing tags are 'sharing' PI under CPRA.")


@check("PRIV-004", "PRIVACY", "CCPA/CPRA Privacy", ["homepage"])
def _priv_notice_at_collection(page_key, page, ctx):
    privacy = page.get("privacy")
    if not isinstance(privacy, dict):
        return None
    # A site-wide opt-out / privacy-policy mechanism satisfies notice-at-collection.
    site_mechanism = (privacy.get("has_do_not_sell_link") or privacy.get("has_privacy_policy_link")
                      or privacy.get("has_limit_sensitive_link"))
    if site_mechanism:
        return None
    forms = privacy.get("lead_forms_have_privacy_notice", []) or []
    bad = [f for f in forms if not f.get("has_privacy_link")]
    if not bad:
        return None
    f0 = bad[0]
    fields = ", ".join(f0.get("fields", [])[:5]) or "unknown fields"
    return CheckResult("PRIV-004", "PRIVACY", "CCPA/CPRA Privacy", page_key,
                       status="fail", confidence="medium", severity="critical",
                       rule_id="CA-PRIV-004", statute="Cal. Civ. Code §1798.100(a), CCPA/CPRA",
                       evidence="Lead form collecting (%s) has no privacy link or notice at collection." % fields,
                       recommendation="Add a privacy policy link and notice at collection to lead forms describing what PI is collected and why.",
                       needs_human_review=True)


@check("PRIV-005", "PRIVACY", "CCPA/CPRA Privacy", ["privacy_policy"])
def _priv_policy_content(page_key, page, ctx):
    ccpa = page.get("ccpa_cpra_content")
    if not isinstance(ccpa, dict):
        return None
    required = [
        ("has_right_to_know", "right to know"),
        ("has_right_to_delete", "right to delete"),
        ("has_right_to_opt_out", "right to opt-out"),
        ("has_right_to_correct", "right to correct"),
        ("has_right_to_limit_sensitive", "right to limit sensitive PI"),
        ("has_categories_collected", "categories of PI collected"),
        ("has_third_party_disclosure", "third-party disclosures"),
        ("has_sources_of_pi", "sources of PI"),
        ("has_purposes", "purposes of collection"),
        ("has_retention_periods", "retention periods"),
        ("has_sell_share_disclosure", "sell/share disclosure"),
    ]
    missing = [label for key, label in required if not ccpa.get(key)]
    if not missing:
        return CheckResult("PRIV-005", "PRIVACY", "CCPA/CPRA Privacy", page_key,
                           status="pass", confidence="medium", rule_id="CA-PRIV-005",
                           statute="Cal. Civ. Code §1798.130(a)(5)",
                           evidence="Privacy policy contains all checked CCPA/CPRA content sections.",
                           needs_human_review=True)
    if is_truncated(page_key, page):
        return CheckResult("PRIV-005", "PRIVACY", "CCPA/CPRA Privacy", page_key,
                           status="unresolved", confidence="low", rule_id="CA-PRIV-005",
                           statute="Cal. Civ. Code §1798.130(a)(5)",
                           evidence="Privacy policy appears to miss %d section(s) but the page was truncated." % len(missing),
                           needs_data=_need(page_key, page, "re-fetch full privacy policy text to confirm missing sections"),
                           needs_human_review=True)
    sev = "warning" if len(missing) >= 3 else "advisory"
    return CheckResult("PRIV-005", "PRIVACY", "CCPA/CPRA Privacy", page_key,
                       status="fail", confidence="medium", severity=sev,
                       rule_id="CA-PRIV-005", statute="Cal. Civ. Code §1798.130(a)(5), CCPA/CPRA",
                       evidence="Privacy policy missing %d section(s): %s" % (len(missing), ", ".join(missing)),
                       recommendation="Add the missing CCPA/CPRA sections to the privacy policy: %s." % ", ".join(missing),
                       needs_human_review=True)


@check("PRIV-006", "PRIVACY", "CCPA/CPRA Privacy", ["privacy_policy"])
def _priv_request_methods(page_key, page, ctx):
    ccpa = page.get("ccpa_cpra_content")
    if not isinstance(ccpa, dict):
        return None
    n = ccpa.get("request_method_count", 0)
    if n >= 2:
        return CheckResult("PRIV-006", "PRIVACY", "CCPA/CPRA Privacy", page_key,
                           status="pass", confidence="high", rule_id="CA-PRIV-006",
                           statute="Cal. Civ. Code §1798.130(a)(1)",
                           evidence="Two or more consumer-request submission methods provided.")
    methods = ccpa.get("request_submission_methods", [])
    return CheckResult("PRIV-006", "PRIVACY", "CCPA/CPRA Privacy", page_key,
                       status="fail", confidence="high", severity="warning",
                       rule_id="CA-PRIV-006", statute="Cal. Civ. Code §1798.130(a)(1), CCPA/CPRA",
                       evidence="Only %d request method(s) found: %s" % (n, ", ".join(methods) if methods else "none"),
                       recommendation="Provide at least two methods for consumer privacy requests (e.g., toll-free phone plus email or web form).")


@check("PRIV-008", "PRIVACY", "CCPA/CPRA Privacy", ["privacy_policy"])
def _priv_gpc(page_key, page, ctx):
    ccpa = page.get("ccpa_cpra_content")
    if not isinstance(ccpa, dict):
        return None
    if ccpa.get("has_gpc_disclosure"):
        return CheckResult("PRIV-008", "PRIVACY", "CCPA/CPRA Privacy", page_key,
                           status="pass", confidence="high", rule_id="CA-PRIV-008",
                           statute="Cal. Civ. Code §1798.135(e); 11 CCR §7025",
                           evidence="Global Privacy Control (GPC) disclosure present.")
    return CheckResult("PRIV-008", "PRIVACY", "CCPA/CPRA Privacy", page_key,
                       status="fail", confidence="high", severity="warning",
                       rule_id="CA-PRIV-008", statute="Cal. Civ. Code §1798.135(e), CPRA; 11 CCR §7025",
                       evidence="Privacy policy does not mention Global Privacy Control or browser opt-out signals.",
                       recommendation="Disclose whether and how the business honors Global Privacy Control (GPC) browser signals.")


# ══════════════════════════════════════════════════════════════
# DISCLOSURE / PRICING extras (ported; single source of truth)
# ══════════════════════════════════════════════════════════════

def _valid_pages(crawl_data):
    # Iterates every captured page, including the extra sampled VDPs which are
    # stored as their own page keys (vdp, vdp_2, vdp_3, ...).
    for pk, pd in (crawl_data.get("pages", {}) or {}).items():
        if pd and isinstance(pd, dict) and not pd.get("error"):
            yield pk, pd


VDP_KEY_RE = re.compile(r"^vdp(?:_\d+)?$")


def _vdp_keys(pages):
    """All page keys that are vehicle detail pages: vdp, vdp_2, vdp_3, ..."""
    return sorted(k for k in pages if VDP_KEY_RE.match(k))


PLUS_FEE_RE = re.compile(
    r"plus\s+(?:doc(?:ument(?:ary|ation)?)?\.?\s*(?:fee|charge|prep)|dealer\s*fee|accessories|"
    r"add[\s-]*ons|protection|appearance|nitrogen|anti[\s-]*theft|paint[\s-]*(?:seal|protect)|"
    r"market\s*adjust|dealer\s*(?:mark[\s-]*up|add))", re.I)


@check("CA-PRICE-002", "PRICING", "Fee Disclosure", ["__crawl__"])
def _plus_nonexempt_fee(page_key, crawl, ctx):
    for pk, pd in _valid_pages(crawl):
        m = PLUS_FEE_RE.search(_all_text(pd))
        if m:
            return CheckResult("CA-PRICE-002", "PRICING", "Fee Disclosure", pk,
                               status="fail", confidence="high", severity="critical",
                               rule_id="CA-PRICE-002", statute="VC §11713.1(e); FTC Act §5, FTC Pricing Transparency FAQs Q2 (Sept. 2026)",
                               evidence="'%s' adds a non-exempt fee on top of advertised price (%s)." % (_short(m.group(0), 60), pk),
                               recommendation="Roll dealer-imposed fees, add-ons, and markups into the advertised price. California (VC §11713.1) excludes only taxes, government fees, and the capped document processing, electronic filing, and emission testing charges; the FTC (Pricing Transparency FAQs Q2, Q6, Sept. 2026) goes further and expects every dealer-imposed or passed-through charge, including the doc fee, inside the most prominent price.",
                               page_url=pd.get("url", ""))
    return None


DOC_FEE_EXCL_RE = re.compile(
    r"(?:doc(?:ument(?:ary|ation)?)?\.?\s*(?:fee|charge|prep)\s*(?:are\s*)?(?:additional|extra|not\s*included|excluded|are\s*extra))"
    r"|(?:(?:do(?:es)?|prices?\s*do(?:es)?)\s*not\s*include\s*(?:[^.]{0,150}?)(?:doc(?:ument(?:ary|ation)?)?\s*fee))", re.I)


@check("CA-DISC-004", "DISCLOSURE", "Advertised-Price Integrity", ["__crawl__"])
def _doc_fee_excluded(page_key, crawl, ctx):
    for pk, pd in _valid_pages(crawl):
        m = DOC_FEE_EXCL_RE.search(_all_text(pd))
        if m:
            return CheckResult("CA-DISC-004", "DISCLOSURE", "Advertised-Price Integrity", pk,
                               status="fail", confidence="high", severity="warning",
                               rule_id="CA-DISC-004", statute="FTC Act §5; FTC Pricing Transparency FAQs Q6, Q7 (Sept. 2026); VC §11713.1 (state disclosure)",
                               evidence="Disclaimer on %s states doc fees are excluded from the advertised price: \"%s\"" % (pk, _short(m.group(0), 120)),
                               recommendation="FTC staff (Pricing Transparency FAQs Q6, Sept. 2026) say the full mandatory doc fee must be inside the advertised price, at the highest amount any buyer is charged, and state doc-fee disclosures are added on top (Q7). California law lets the capped document processing charge sit outside the CARS Act total price, so for a California store make the price including the doc fee the most prominent figure and keep the state total price and Plus Disclosure beneath it. Confirm the presentation with counsel.",
                               page_url=pd.get("url", ""))
    return None


ZERO_DOWN_RE = re.compile(r"\$0\s*down|zero\s*down|no\s*(?:money\s*)?down(?:payment)?|nothing\s*down|\b0\s*down\b", re.I)
FINANCING_CTX_RE = re.compile(r"apr|financing|approved\s*credit|per\s*\$1[,.]?000\s*borrowed|monthly\s*payment", re.I)


@check("CA-REGZ-004", "PRICING", "Zero-Down Advertising", ["__crawl__"])
def _zero_down(page_key, crawl, ctx):
    for pk, pd in _valid_pages(crawl):
        text = _all_text(pd)
        for m in ZERO_DOWN_RE.finditer(text):
            window = text[max(0, m.start() - 150): m.end() + 150]
            if FINANCING_CTX_RE.search(window):
                continue  # legitimate Reg Z financing term, covered by PRICING-FINANCE-REGZ
            return CheckResult("CA-REGZ-004", "PRICING", "Zero-Down Advertising", pk,
                               status="fail", confidence="high", severity="critical",
                               rule_id="CA-REGZ-004", statute="VC §11713(k), §11713.16(g)",
                               evidence="'%s' on %s (deceptive zero-down headline)." % (_short(m.group(0), 30), pk),
                               recommendation="'Zero down' is prohibited unless absolutely no payment of any kind (including tax/license) is required before delivery.",
                               page_url=pd.get("url", ""))
    return None


PLUS_TAX_LICENSE_RE = re.compile(
    r"plus\s*tax\s*(?:and|&|,)\s*(?:title\s*(?:,|and|&)\s*)?(?:license|tag)"
    r"|tax\s*,\s*title\s*,?\s*(?:and\s*)?license|title\s*,\s*tax\s*,?\s*(?:and\s*)?license"
    r"|(?:tax|license|registration)\s*(?:not\s*included|excluded|additional|extra|are\s*extra)", re.I)


@check("CA-REGM-002", "PRICING", "Lease Tax/License Disclosure", ["specials", "homepage"])
def _lease_plus_tax_license(page_key, page, ctx):
    text = _all_text(page)
    has_lease = page.get("has_lease_offers") or bool(re.search(r"\blease\b", text, re.I))
    if not has_lease:
        return None
    if PLUS_TAX_LICENSE_RE.search(text):
        return CheckResult("CA-REGM-002", "PRICING", "Lease Tax/License Disclosure", page_key,
                           status="pass", confidence="high", rule_id="CA-REGM-002",
                           statute="Cal. Civ. Code §2985.71(b)(3)",
                           evidence="Lease ad discloses 'plus tax and license' (or equivalent).")
    if is_truncated(page_key, page):
        return CheckResult("CA-REGM-002", "PRICING", "Lease Tax/License Disclosure", page_key,
                           status="unresolved", confidence="low", rule_id="CA-REGM-002",
                           statute="Cal. Civ. Code §2985.71(b)(3)",
                           evidence="Lease ad with no 'plus tax and license' captured, but page truncated/expandable.",
                           needs_data=_need(page_key, page, "re-fetch to confirm tax/license disclosure"),
                           needs_human_review=True)
    return CheckResult("CA-REGM-002", "PRICING", "Lease Tax/License Disclosure", page_key,
                       status="fail", confidence="high", severity="warning",
                       rule_id="CA-REGM-002", statute="Cal. Civ. Code §2985.71(b)(3)",
                       evidence="Lease offer on %s without a 'plus tax and license' statement." % page_key,
                       recommendation="Add a 'plus tax and license' statement to all lease ads.")


EXPIRED_DATE_RE = re.compile(r"[Ee]xp(?:ires?|iration)?[\s:]*(\d{1,2}/\d{1,2}/\d{4})")


@check("CA-DISC-EXP", "DISCLOSURE", "Stale Disclaimer Date", ["__crawl__"])
def _expired_dates(page_key, crawl, ctx):
    from datetime import datetime
    for pk, pd in _valid_pages(crawl):
        for m in EXPIRED_DATE_RE.finditer(_all_text(pd)):
            try:
                exp = datetime.strptime(m.group(1), "%m/%d/%Y")
            except ValueError:
                continue
            if exp < datetime(2024, 1, 1):
                yrs = (datetime(2026, 6, 28) - exp).days // 365
                return CheckResult("CA-DISC-EXP", "DISCLOSURE", "Stale Disclaimer Date", pk,
                                   status="fail", confidence="high", severity="warning",
                                   rule_id="CA-DISC-001", statute="VC §11713.16(i); 13 CCR §260",
                                   evidence="Disclaimer on %s carries expiration '%s' (~%d years stale)." % (pk, m.group(1), yrs),
                                   recommendation="Remove or update expired disclaimer dates; stale disclaimers signal weak compliance oversight to regulators.",
                                   page_url=pd.get("url", ""))
    return None


# ══════════════════════════════════════════════════════════════
# CARS ACT — federal vs. California posture
# ──────────────────────────────────────────────────────────────
# The FEDERAL FTC CARS Rule (16 CFR Part 463) was VACATED by the U.S. 5th Circuit
# in Jan 2025, so it is NOT federally enforceable. Almost all of our dealers are in
# California, where the controlling authority is California consumer/advertising law
# and the CARS-style protections phase in on the operative date below. Until that
# date these are forward-looking "get ready" findings, so we surface them ONE NOTCH
# SOFTER and never as criticals; on/after the operative date they auto-escalate to
# their intended severity. This posture is applied in ONE place (_apply_cars_posture,
# called at the end of run_checks) so every CARS check stays consistent.
#
# 2026-09-14: CNCDA's Compliance Guide v1.2 and Webinar FAQ were folded in. New
# deterministic checks below: CA-CARS-025 (MSRP substituted for total price),
# CA-CARS-026 (price gated behind a CTA), CA-CARS-027 (Plus Disclosure altered),
# CA-CARS-029 (installed items excluded / pay-or-remove), CA-CARS-039 (repealed
# two-day option language). Rule text lives in rules/ca_hard_rules.json; the
# vault digest is Resources/automotive-guidelines/cncda-cars-act-guidance.md.
# ══════════════════════════════════════════════════════════════

from datetime import date as _date

CARS_CA_OPERATIVE = _date(2026, 10, 1)
# Authoritative basis attached to every CARS finding. Verified 2026-06-28 (see
# rules/legal_watch.json). The federal rule is dead; California is what controls.
CARS_FED_NOTE = ("CALIFORNIA controls: CARS Act (SB 766, Cal. Civ. Code §1784.20 et seq.), "
                 "operative Oct 1, 2026. The federal FTC CARS Rule (16 CFR Part 463) was "
                 "VACATED by the 5th Circuit (Jan 2025) and formally WITHDRAWN from the CFR "
                 "(Fed. Reg. Feb 2026), not enforceable; FTC Section 5 still applies. "
                 "Pin-cites verified against the chaptered statute (leginfo) 2026-06-28; "
                 "CNCDA Compliance Guide v1.2 (2026-08-07) and Webinar FAQ (2026-08-31) "
                 "folded in 2026-09-14.")


def _cars_operative():
    try:
        return _date.today() >= CARS_CA_OPERATIVE
    except Exception:
        return False


def _apply_cars_posture(results):
    """Re-ground every CARS finding in California reality (see banner above).

    Idempotent: guarded by CARS_FED_NOTE so re-runs (verify loop) don't stack."""
    operative = _cars_operative()
    soften = {"critical": "warning", "warning": "advisory", "advisory": "advisory"}
    for r in results:
        if r.framework != "CARS" or r.status != "fail":
            continue
        if CARS_FED_NOTE in (r.statute or ""):
            continue  # already adjusted
        if not operative:
            r.severity = soften.get(r.severity or "warning", "advisory")
            r.recommendation = ("California's CARS-style requirement is not operative "
                                "until Oct 1, 2026 — fix now to be ready. This is a "
                                "CALIFORNIA requirement, not a federal one. ") + (r.recommendation or "")
        r.statute = ((r.statute or "") + " | " + CARS_FED_NOTE).strip(" |")
    return results


# ══════════════════════════════════════════════════════════════
# CARS ACT — California consumer-protection checks
# ══════════════════════════════════════════════════════════════

ADDON_RE = re.compile(
    r"\b(?:protection\s*package|appearance\s*package|(?:paint|surface|fabric|interior)\s*protection|"
    r"(?:theft|anti[\s-]*theft)\s*deterrent|nitrogen\s*(?:tire|fill)|(?:GAP|gap)\s*(?:waiver|agreement|coverage|insurance)|"
    r"service\s*contract|extended\s*warranty|maintenance\s*(?:plan|package)|(?:window|vin)\s*etch(?:ing)?|"
    r"(?:key|tire)\s*(?:replacement|protection)|(?:dent|ding)\s*(?:protection|repair)|(?:road\s*hazard|wheel)\s*protection)\b", re.I)
NOT_REQUIRED_RE = re.compile(
    r"(?:not\s*required|optional|not\s*mandatory|may\s*(?:choose|decline|opt[\s-]*out)|"
    r"you\s*(?:do\s*not\s*(?:need|have)\s*to|are\s*not\s*required)|(?:can|may)\s*be\s*(?:declined|removed))", re.I)


@check("CA-CARS-002", "CARS", "CARS Act Add-On Disclosure", ["__crawl__"])
def _cars_addon(page_key, crawl, ctx):
    for pk, pd in _valid_pages(crawl):
        text = _all_text(pd)
        hits = ADDON_RE.findall(text)
        if hits and not NOT_REQUIRED_RE.search(text):
            uniq = list({h.lower() for h in hits})[:4]
            return CheckResult("CA-CARS-002", "CARS", "CARS Act Add-On Disclosure", pk,
                               status="fail", confidence="medium", severity="warning",
                               rule_id="CA-CARS-002", statute="Cal. Civ. Code §1784.41(b) (CARS Act, SB 766)",
                               evidence="Add-ons on %s (%s) with no 'not required'/'optional' disclosure." % (pk, ", ".join(uniq)),
                               recommendation="Under the CARS Act (operative Oct 1, 2026) add-on products must carry a clear, conspicuous written disclosure that they are NOT required for purchase or lease.",
                               needs_human_review=True, page_url=pd.get("url", ""))
    return None


WAIVER_RE = re.compile(r"(?:waive|relinquish|forfeit|give\s*up|surrender)\s*(?:your\s*)?(?:right|cancellation|refund|return)", re.I)


@check("CA-CARS-020", "CARS", "CARS Act Rights Waiver", ["__crawl__"])
def _cars_waiver(page_key, crawl, ctx):
    for pk, pd in _valid_pages(crawl):
        m = WAIVER_RE.search(_all_text(pd))
        if m:
            return CheckResult("CA-CARS-020", "CARS", "CARS Act Rights Waiver", pk,
                               status="fail", confidence="high", severity="critical",
                               rule_id="CA-CARS-020", statute="Cal. Civ. Code §1784.21 (CARS Act, SB 766)",
                               evidence="'%s' on %s — consumer waivers of CARS Act rights are void." % (_short(m.group(0), 40), pk),
                               recommendation="Remove any language requiring consumers to waive CARS Act rights; such waivers are unenforceable under §1784.22.",
                               page_url=pd.get("url", ""))
    return None


GOV_AFFIL_RE = re.compile(
    r"(?:government[\s-]*(?:approved|endorsed|backed|certified|sponsored|program|funded))"
    r"|(?:(?:state|federal|county)\s*(?:approved|endorsed|certified|sponsored)\s*(?:dealer|program))"
    r"|(?:official\s*(?:government|state|federal)\s*(?:dealer|program|partner))", re.I)


@check("CA-CARS-013", "CARS", "CARS Act Government Affiliation", ["__crawl__"])
def _cars_gov(page_key, crawl, ctx):
    for pk, pd in _valid_pages(crawl):
        m = GOV_AFFIL_RE.search(_all_text(pd))
        if m:
            return CheckResult("CA-CARS-013", "CARS", "CARS Act Government Affiliation", pk,
                               status="fail", confidence="medium", severity="warning",
                               rule_id="CA-CARS-013", statute="Cal. Civ. Code §1784.40(j) (CARS Act, SB 766)",
                               evidence="'%s' on %s may imply government affiliation/endorsement." % (_short(m.group(0), 40), pk),
                               recommendation="Remove language implying government affiliation unless a genuine, substantiable relationship exists.",
                               needs_human_review=True, page_url=pd.get("url", ""))
    return None


PREAPPROVAL_RE = re.compile(
    r"(?:you(?:'re| are)\s*(?:pre[\s-]*)?approved)|(?:instant\s*(?:approval|financing))|(?:100%\s*(?:approval|financing))", re.I)


PRICE_REMEDY_RE = re.compile(
    r"(?:prices?\s*(?:are\s*)?subject\s*to\s*change\s*without\s*notice)"
    r"|(?:(?:dealer|we)\s*(?:is|are|will)\s*not\s*(?:liable|responsible|bound)\s*(?:for|by)\s*(?:any\s*)?(?:pricing|price|typographical|listing)\s*(?:errors?|mistakes?))"
    r"|(?:(?:if|when|should)\s*we\s*(?:can(?:'|no)?t|cannot|do\s*not|don't)\s*honor)"
    r"|(?:(?:sole|only)\s*(?:remedy|obligation|recourse))", re.I)


@check("CA-CARS-023", "CARS", "CARS Act Price-Remedy Representation", ["__crawl__"])
def _cars_price_remedy(page_key, crawl, ctx):
    """DMV summary item: no misrepresenting the remedy when the advertised price
    is not honored (Civ. Code 1784.40(i)). Deterministic scope is narrow on purpose:
    only disclaimer language that limits or waives the consumer's recourse."""
    for pk, pd in _valid_pages(crawl):
        m = PRICE_REMEDY_RE.search(_all_text(pd))
        if m:
            return CheckResult("CA-CARS-023", "CARS", "CARS Act Price-Remedy Representation", pk,
                               status="fail", confidence="medium", severity="warning",
                               rule_id="CA-CARS-023", statute="Cal. Civ. Code §1784.40(i) (CARS Act, SB 766)",
                               evidence="'%s' on %s may misstate or limit the consumer's remedy when an advertised price is not honored." % (_short(m.group(0), 50), pk),
                               recommendation="Disclaimers may not misrepresent what a consumer can do if the advertised total price is not honored. Remove 'sole remedy' / 'not bound by pricing errors' style language or have counsel rewrite it to match the CARS Act and Veh. Code 11713(c) withdrawal rules.",
                               needs_human_review=True, page_url=pd.get("url", ""))
    return None


@check("CA-CARS-014", "CARS", "CARS Act Preapproval Claims", ["finance", "homepage", "specials"])
def _cars_preapproval(page_key, page, ctx):
    m = PREAPPROVAL_RE.search(_all_text(page))
    if not m:
        return None
    return CheckResult("CA-CARS-014", "CARS", "CARS Act Preapproval Claims", page_key,
                       status="fail", confidence="high", severity="warning",
                       rule_id="CA-CARS-014", statute="Cal. Civ. Code §1784.40(e) (CARS Act, SB 766)",
                       evidence="'%s' on %s may misrepresent preapproval status." % (_short(m.group(0), 40), page_key),
                       recommendation="Do not state or imply a consumer is preapproved/instantly approved unless every applicant is genuinely approved regardless of credit.")


PAYMENT_AMT_RE = re.compile(r"\$\d[\d,]*\s*(?:/\s*mo|per\s*month|/month|monthly)", re.I)
TOTAL_PAYABLE_RE = re.compile(
    r"total\s*(?:of\s*)?(?:all\s*)?payments?\s*(?:of\s*|:?\s*|=\s*)\$|total\s*(?:amount\s*)?(?:paid|payable|due\s*over|cost\s*over)"
    r"|total\s*(?:lease\s*)?cost|you\s*will\s*(?:have\s*)?paid?\s*(?:a\s*)?total", re.I)


@check("CA-CARS-003", "CARS", "CARS Act Total-Payable Disclosure", ["specials", "homepage", "vlp", "vdp"])
def _cars_total_payable(page_key, page, ctx):
    text = _all_text(page)
    if not PAYMENT_AMT_RE.search(text):
        return None
    if TOTAL_PAYABLE_RE.search(text):
        return CheckResult("CA-CARS-003", "CARS", "CARS Act Total-Payable Disclosure", page_key,
                           status="pass", confidence="high", rule_id="CA-CARS-003",
                           statute="Cal. Civ. Code §1784.41(c)(1) (CARS Act, SB 766)",
                           evidence="Monthly payment shown with a total-amount-payable disclosure.")
    if is_truncated(page_key, page):
        return CheckResult("CA-CARS-003", "CARS", "CARS Act Total-Payable Disclosure", page_key,
                           status="unresolved", confidence="low", rule_id="CA-CARS-003",
                           statute="Cal. Civ. Code §1784.41(c)(1) (CARS Act, SB 766)",
                           evidence="Monthly payment with no total-payable captured, but page truncated/expandable.",
                           needs_data=_need(page_key, page, "re-fetch to confirm total-amount-payable disclosure"),
                           needs_human_review=True)
    return CheckResult("CA-CARS-003", "CARS", "CARS Act Total-Payable Disclosure", page_key,
                       status="fail", confidence="high", severity="warning",
                       rule_id="CA-CARS-003", statute="Cal. Civ. Code §1784.41(c)(1) (CARS Act, SB 766)",
                       evidence="Monthly payment advertised on %s without the total amount payable over the term." % page_key,
                       recommendation="Under the CARS Act (operative Oct 1, 2026) any written monthly-payment representation must also disclose the total the consumer will have paid after all scheduled payments, plus any assumed down payment or trade value. CNCDA: an ad for an identified unit that states a payment also needs that unit's total price; the safest practice is total price only, payments reserved for desked terms.")


LOWER_PAYMENT_RE = re.compile(
    r"(?:lower|reduce|decrease|cut)\s*(?:your\s*)?(?:monthly\s*)?payment|(?:affordable|low)\s*monthly\s*payment|payments?\s*as\s*low\s*as", re.I)
EXTENDED_TERM_WARN_RE = re.compile(
    r"(?:lower\s*(?:monthly\s*)?payments?\s*(?:often|may|can|will)\s*increase\s*(?:the\s*)?total)"
    r"|(?:extend(?:ed|ing)\s*(?:the\s*)?(?:loan\s*)?term\s*(?:may|will|can)\s*increase)"
    r"|(?:(?:longer|extended)\s*term.*?(?:more|higher|increase).*?total)", re.I)
CALC_RE = re.compile(r"payment\s*calculator|estimate\s*(?:your\s*)?payment|adjust\s*(?:your\s*)?payment", re.I)


@check("CA-CARS-004", "CARS", "CARS Act Extended-Term Warning", ["specials", "homepage", "finance"])
def _cars_lower_payment(page_key, page, ctx):
    text = _all_text(page)
    if not LOWER_PAYMENT_RE.search(text) or EXTENDED_TERM_WARN_RE.search(text):
        return None
    if CALC_RE.search(text):
        return None  # interactive payment calculators are exempt
    return CheckResult("CA-CARS-004", "CARS", "CARS Act Extended-Term Warning", page_key,
                       status="fail", confidence="medium", severity="warning",
                       rule_id="CA-CARS-004", statute="Cal. Civ. Code §1784.41(d) (CARS Act, SB 766)",
                       evidence="Lower-payment messaging on %s without an extended-term cost warning." % page_key,
                       recommendation="Any written comparison that highlights lower monthly payments must disclose that lower monthly payments often increase the total amount paid over the term (Civ. Code 1784.41(d)). A consumer-adjusted payment calculator is exempt; a dealer-sent message through the tool is not.",
                       needs_human_review=True)


ANTI_CANCEL_RE = re.compile(
    r"\ball\s*sales?\s*(?:are\s*)?final\b|\bno\s*returns?\b|\bno\s*cancellations?\b|\bnon[\s-]*refundable\b|\bas[\s-]*is.*?no\s*(?:return|cancel)", re.I)


@check("CA-CARS-009", "CARS", "CARS Act Cancellation Right", ["used", "cpo"])
def _cars_anti_cancel(page_key, page, ctx):
    m = ANTI_CANCEL_RE.search(_all_text(page))
    if not m:
        return None
    return CheckResult("CA-CARS-009", "CARS", "CARS Act Cancellation Right", page_key,
                       status="fail", confidence="high", severity="critical",
                       rule_id="CA-CARS-009", statute="Cal. Civ. Code §1784.43(a)(1) (CARS Act, SB 766)",
                       evidence="'%s' on %s conflicts with the CARS Act 3-day cancellation right (used ≤$50K)." % (_short(m.group(0), 40), page_key),
                       recommendation="Remove 'all sales final'/'no returns' language from used pages. The CARS Act (operative Oct 1, 2026) grants a free 3-day cancellation right on used vehicles $50,000 or less (purchase price or capitalized cost), measured from execution of the agreement. Per CNCDA, better terms may be offered but must then appear in the cancellation disclosure and signage.")


EV_RE = re.compile(r"\b(?:electric\s*vehicle|EV|battery\s*electric|BEV|all[\s-]*electric|zero[\s-]*emission)\b", re.I)
OIL_CHANGE_RE = re.compile(r"\b(?:oil\s*change|oil\s*service|lube\s*service|oil\s*filter)\b", re.I)


@check("CA-CARS-015", "CARS", "CARS Act Valueless Add-On", ["__crawl__"])
def _cars_ev_oil(page_key, crawl, ctx):
    ev_pages = [pk for pk, pd in _valid_pages(crawl)
                if EV_RE.search(_all_text(pd)) and OIL_CHANGE_RE.search(_all_text(pd))]
    if not ev_pages:
        return None
    return CheckResult("CA-CARS-015", "CARS", "CARS Act Valueless Add-On", ev_pages[0],
                       status="fail", confidence="medium", severity="warning",
                       rule_id="CA-CARS-015", statute="Cal. Civ. Code §1784.42(a)(5) (CARS Act, SB 766)",
                       evidence="Oil-change/lube service offered alongside EVs on: %s" % ", ".join(ev_pages),
                       recommendation="Do not charge for oil changes on electric vehicles; the CARS Act treats it as a valueless add-on.",
                       needs_human_review=True, page_url=crawl.get("url", ""))


# ── CNCDA guidance checks (added 2026-09-14) ──────────────────

MSRP_SUBSTITUTE_RE = re.compile(
    r"(?:msrp\s+(?:is\s+)?not\s+(?:the\s+)?(?:selling|advertised|sale|dealer'?s?|actual)\s+price)"
    r"|(?:price\s+shown\s+is\s+(?:the\s+)?msrp)"
    r"|(?:msrp\s+only\b)"
    r"|(?:manufacturer'?s?\s+suggested\s+retail\s+price\s+(?:is\s+)?not\s+(?:the\s+)?(?:selling|advertised|sale)\s+price)", re.I)


@check("CA-CARS-025", "CARS", "CARS Act MSRP Substituted for Total Price", ["__crawl__"])
def _cars_msrp_substitute(page_key, crawl, ctx):
    """CNCDA Guide Part 2 / Appendix D Ex. 3: MSRP with a 'not the selling price'
    disclaimer does not satisfy the Act; the dealer's total price must appear and
    MSRP may be no more prominent than it."""
    for pk, pd in _valid_pages(crawl):
        m = MSRP_SUBSTITUTE_RE.search(_all_text(pd))
        if m:
            return CheckResult("CA-CARS-025", "CARS", "CARS Act MSRP Substituted for Total Price", pk,
                               status="fail", confidence="high", severity="critical",
                               rule_id="CA-CARS-025", statute="Cal. Civ. Code §1784.41(a), §1784.31(j) (CARS Act, SB 766)",
                               evidence="'%s' on %s: MSRP is being presented in place of the dealer's total price." % (_short(m.group(0), 60), pk),
                               recommendation="Show the dealer's total price (including installed items and any markup) as the prominent figure on every specific-vehicle page. MSRP may stay only if labeled as the manufacturer's suggested retail price and displayed no more prominently than the total price. 'MSRP, not the selling price' disclaimers do not satisfy the CARS Act (CNCDA Guide Part 2, FAQ Q4).",
                               page_url=pd.get("url", ""))
    return None


PRICE_GATE_RE = re.compile(
    r"(?:(?:get|see|unlock|reveal|click|request|check|view)\s+(?:here\s+)?(?:for\s+|your\s+|our\s+|the\s+|my\s+)?"
    r"(?:e-?price|internet\s+price|best\s+price|sale\s+price|special\s+price|price|pricing|payments?)\b)"
    r"|(?:(?:unlock|reveal)\s+(?:savings|pricing|discount))"
    r"|(?:scan\s+(?:the\s+)?(?:qr|code)\s+for\s+(?:price|pricing))"
    r"|(?:price\s+available\s+(?:upon|on)\s+request)", re.I)


@check("CA-CARS-026", "CARS", "CARS Act Price Gated Behind CTA", ["vdp", "vlp", "specials"])
def _cars_price_gate(page_key, page, ctx):
    """CNCDA FAQ Q10: a CTA that stands in place of the price on a specific-vehicle
    page is the online version of 'call for price'. Fires only when the page has a
    price CTA and NO dollar price at all, so a 'Get ePrice' button next to a
    displayed total price does not trip it."""
    text = _all_text(page)
    m = PRICE_GATE_RE.search(text)
    if not m or PRICE_RE.search(text):
        return None
    if is_truncated(page_key, page):
        return CheckResult("CA-CARS-026", "CARS", "CARS Act Price Gated Behind CTA", page_key,
                           status="unresolved", confidence="low", rule_id="CA-CARS-026",
                           statute="Cal. Civ. Code §1784.41(a)(1) (CARS Act, SB 766)",
                           evidence="Price CTA '%s' with no dollar price captured, but page truncated." % _short(m.group(0), 40),
                           needs_data=_need(page_key, page, "re-fetch to confirm whether a total price is displayed"),
                           needs_human_review=True)
    return CheckResult("CA-CARS-026", "CARS", "CARS Act Price Gated Behind CTA", page_key,
                       status="fail", confidence="medium", severity="critical",
                       rule_id="CA-CARS-026", statute="Cal. Civ. Code §1784.41(a)(1) (CARS Act, SB 766)",
                       evidence="'%s' on %s with no displayed price: the total price sits behind a click, form, login, or scan." % (_short(m.group(0), 40), page_key),
                       recommendation="Display the vehicle's total price on the page itself. A CTA that leads to more detail is fine once the price is shown; gating the price behind a click, lead form, or login is the online version of 'call for price' (CNCDA FAQ Q10). The FTC has also said price information should not sit behind a link.",
                       needs_human_review=True)


PLUS_DISCLOSURE_VERBATIM = ("plus government fees and taxes, any finance charges, any dealer document "
                            "processing charge, any electronic filing charge, and any emission testing charge")
PLUS_ABBREV_RE = re.compile(
    r"(?:plus\s+(?:government|gov'?t\.?)\s+fees)|(?:plus\s+tax(?:es)?\b)|(?:\+\s*tax)|(?:plus\s+(?:applicable\s+)?fees)"
    r"|(?:plus\s+ttl\b)|(?:plus\s+t\s*&\s*l\b)|(?:plus\s+tax,?\s+title)", re.I)


@check("CA-CARS-027", "CARS", "CARS Act Plus Disclosure Altered", ["vdp"])
def _cars_plus_disclosure(page_key, page, ctx):
    """CNCDA Guide Part 2: the Veh. Code 11713.1(c)(2) Plus Disclosure stays required
    on every web page displaying a vehicle price, verbatim, no abbreviations. Fires
    only when an abbreviated/altered "plus ..." fee phrase is present; absence of
    any disclaimer is F1-PRICE-HAS-DISCLAIMER's job, and "excludes tax, title,
    license" style wording is left to CA-PRICE-002 / human review (kept out so a
    clean fixture with that wording does not trip a CARS finding). Scoped to VDPs,
    where a vehicle price is displayed; lease specials carry Reg M totals with
    "plus tax and license" wording that is not a price display."""
    text = _all_text(page)
    if not PRICE_RE.search(text):
        return None
    norm = re.sub(r"\s+", " ", text.lower())
    if PLUS_DISCLOSURE_VERBATIM in norm:
        return None
    m = PLUS_ABBREV_RE.search(text)
    if not m:
        return None
    return CheckResult("CA-CARS-027", "CARS", "CARS Act Plus Disclosure Altered", page_key,
                       status="fail", confidence="medium", severity="warning",
                       rule_id="CA-CARS-027", statute="Cal. Veh. Code §11713.1(c)(2); Cal. Civ. Code §1784.41(f)",
                       evidence="'%s' on %s instead of the verbatim statutory Plus Disclosure." % (_short(m.group(0), 40), page_key),
                       recommendation="Use the statutory sentence verbatim, with no abbreviations, on every page that displays a vehicle price: 'Plus government fees and taxes, any finance charges, any dealer document processing charge, any electronic filing charge, and any emission testing charge.' If the document processing charge is already inside the advertised price, drop that reference so the disclosure is not misleading (CNCDA Guide Part 2).",
                       needs_human_review=True)


INSTALLED_EXCLUDED_RE = re.compile(
    r"(?:(?:excludes?|does\s+not\s+include|not\s+included\s+in\s+(?:the\s+)?price)[^.]{0,80}"
    r"(?:dealer[\s-]*(?:installed|added)|installed\s+(?:accessor|option|equipment|item|product)|accessor(?:y|ies)|add[\s-]*ons?|protection\s+(?:package|product)|appearance\s+package))"
    r"|(?:(?:removed|remove)\s+at\s+(?:the\s+)?customer'?s?\s+(?:option|request))"
    r"|(?:purchased\s+for\s+an\s+additional\s+(?:cost|charge))"
    r"|(?:does\s+not\s+apply\s+to\s+vehicles\s+with\s+dealer[\s-]*(?:added|installed))"
    r"|(?:plus\s+(?:dealer[\s-]*)?(?:installed|added)\s+(?:accessor|option|equipment))"
    r"|(?:pay\s+or\s+remove)", re.I)


@check("CA-CARS-029", "CARS", "CARS Act Installed Items Excluded From Price", ["__crawl__"])
def _cars_installed_excluded(page_key, crawl, ctx):
    """CNCDA Guide Part 2 'Superseded practices': excluding an installed item from a
    specific vehicle's price, even as pay-or-remove, is unlawful from 2026-10-01."""
    for pk, pd in _valid_pages(crawl):
        m = INSTALLED_EXCLUDED_RE.search(_all_text(pd))
        if m:
            return CheckResult("CA-CARS-029", "CARS", "CARS Act Installed Items Excluded From Price", pk,
                               status="fail", confidence="high", severity="critical",
                               rule_id="CA-CARS-029", statute="Cal. Civ. Code §1784.31(j)(2), §1784.41(a)(1) (CARS Act, SB 766)",
                               evidence="'%s' on %s excludes installed equipment from the advertised price." % (_short(m.group(0), 60), pk),
                               recommendation="Fold every item physically installed on the vehicle at the time of the ad into the advertised total price. 'May be purchased for an additional cost or removed at the customer's option' (pay-or-remove) and 'price excludes dealer-installed accessories' no longer work for an identified unit; the class-ad accessory disclaimer survives only where no specific vehicle is identified (CNCDA Guide Part 2, Appendix D Example 1). The dealer need not remove or discount an item a customer refuses.",
                               page_url=pd.get("url", ""))
    return None


REPEALED_OPTION_RE = re.compile(
    r"(?:contract\s+cancellation\s+option)|(?:cancellation\s+option\s+agreement)"
    r"|(?:(?:two|2)[\s-]*day\s+(?:contract\s+)?(?:cancel|return))|(?:72[\s-]*hour\s+(?:return|cancel|option))"
    r"|(?:\$\s?40,000)|(?:(?:purchase|buy)\s+(?:a|the|your)\s+(?:cancellation|return)\s+option)"
    r"|(?:no\s+cooling[\s-]*off\s+period\s+unless)", re.I)


@check("CA-CARS-039", "CARS", "CARS Act Repealed Cancellation-Option Language", ["__crawl__"])
def _cars_repealed_option(page_key, crawl, ctx):
    """CNCDA FAQ Q56/Q57: the paid two-day option (Veh. Code 11713.21) is repealed on
    2026-10-01; any copy describing it, a 72-hour purchased option, or the $40,000
    threshold misstates the customer's rights."""
    for pk, pd in _valid_pages(crawl):
        m = REPEALED_OPTION_RE.search(_all_text(pd))
        if m:
            return CheckResult("CA-CARS-039", "CARS", "CARS Act Repealed Cancellation-Option Language", pk,
                               status="fail", confidence="high", severity="critical",
                               rule_id="CA-CARS-039", statute="Cal. Veh. Code §11713.21 (repealed 2026-10-01); Cal. Civ. Code §1784.43(b), (j) (CARS Act, SB 766)",
                               evidence="'%s' on %s describes the repealed paid contract cancellation option." % (_short(m.group(0), 50), pk),
                               recommendation="Replace with the current rule: a free 3-day right to cancel on used vehicles $50,000 or less, documented on the separate '3-Day Right to Cancel Used Car Purchase or Lease' disclosure. The two-day purchased option, the $40,000 threshold, and 'no cooling-off unless you obtain a contract cancellation option' describe repealed law (CNCDA FAQ Q56, Q57). Any more generous store policy belongs in that disclosure and the signage.",
                               page_url=pd.get("url", ""))
    return None


# ══════════════════════════════════════════════════════════════
# NEW/USED labeling + Dealer identity
# ══════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════
# FTC PRICING TRANSPARENCY FAQs (FTC staff, September 2026)
# ══════════════════════════════════════════════════════════════
# Federal, current (no operative date, no CARS posture softening). Staff views, not
# binding, so text-evident findings ship as warnings with human review. Source:
# https://www.ftc.gov/business-guidance/resources/automobile-industry-pricing-transparency-faqs
# Context and California tension: ftc_reference in rules/ca_hard_rules.json.

FTC_FAQ = "FTC Act §5; FTC Automobile Industry Pricing Transparency FAQs (Sept. 2026)"

CA_PLUS_DPC_RE = re.compile(r"(?:plus|excludes?|not\s*including)[^.]{0,160}document\s*processing\s*charge", re.I)
DPC_INCLUSIVE_RE = re.compile(
    r"price\s*including\s*(?:the\s*)?(?:dealer\s*)?doc(?:ument)?(?:ation)?\s*(?:processing\s*)?(?:fee|charge)"
    r"|includes?\s*(?:the\s*|all\s*|any\s*)?(?:dealer\s*)?doc(?:ument)?(?:ation)?\s*(?:processing\s*)?(?:fee|charge)"
    r"|(?:doc(?:ument)?\s*(?:processing\s*)?(?:fee|charge)|all\s*dealer\s*fees)\s*(?:is\s*|are\s*)?included", re.I)


@check("FTC-DOCFEE-CA", "FTC", "FTC Pricing Transparency", ["vdp", "vlp", "specials"])
def _ftc_ca_dpc(page_key, page, ctx):
    """FAQ Q6/Q7: doc fee inside the most prominent price. A California page carrying
    the state Plus Disclosure (DPC excluded) with no DPC-inclusive price shown."""
    text = _all_text(page)
    m = CA_PLUS_DPC_RE.search(text)
    if not m or DPC_INCLUSIVE_RE.search(text):
        return None
    return CheckResult("FTC-DOCFEE-CA", "FTC", "FTC Pricing Transparency", page_key,
                       status="fail", confidence="medium", severity="warning",
                       rule_id="FTC-PRICE-002", statute=FTC_FAQ + " Q6, Q7",
                       evidence="'%s' on %s excludes the document processing charge and no price including it was captured." % (_short(m.group(0), 80), page_key),
                       recommendation="NEEDS HUMAN REVIEW AND VERIFICATION: the price including the doc fee may sit in a widget the crawl missed. FTC staff say the full doc fee belongs inside the most prominent price (Q6) and state doc-fee disclosures are additive (Q7). California lets the document processing charge sit outside the CARS Act total price, so show a 'Price including document processing charge' as the most prominent figure, with the total price and Plus Disclosure beneath it. Confirm with counsel.",
                       needs_human_review=True, page_url=page.get("url", ""))


COND_PRICE_RE = re.compile(
    r"(?:price|pricing)\b[^.]{0,80}?\b(?:includes?|reflects?|after|less)\b[^.]{0,60}?"
    r"(?:financ\w*\s*(?:bonus|cash|incentive|discount|rebate|allowance)|dealer[\s-]*(?:arranged\s*)?financ\w*|"
    r"(?:military|first[\s-]*responder|college(?:\s*grad(?:uate)?)?|loyalty|conquest|trade[\s-]*in\s*(?:assist\w*|bonus))\s*(?:rebate|discount|cash|bonus|incentive|program|offer)?)"
    r"|(?:price|pricing)\s*(?:requires|assumes|is\s*(?:contingent|conditional|based)\s*on)\s*[^.]{0,60}?financ\w*", re.I)


@check("FTC-COND-PRICE", "FTC", "FTC Pricing Transparency", ["specials", "vdp", "vlp", "homepage"])
def _ftc_conditional_price(page_key, page, ctx):
    """FAQ Q5/Q9: a finance-conditioned or group-limited discount inside the headline price."""
    m = COND_PRICE_RE.search(_all_text(page))
    if not m:
        return None
    return CheckResult("FTC-COND-PRICE", "FTC", "FTC Pricing Transparency", page_key,
                       status="fail", confidence="medium", severity="warning",
                       rule_id="FTC-PRICE-004", statute=FTC_FAQ + " Q5, Q9",
                       evidence="'%s' on %s suggests the advertised price already deducts a conditional discount." % (_short(m.group(0), 90), page_key),
                       recommendation="Make the most prominent price the one any buyer pays using any financing. Show first-responder, military, loyalty, conquest, or dealer-financing discounts beside that price with their terms, never inside it (FTC FAQs Q5, Q9). California adds net-cost labeling rules (CA-CARS-028).",
                       needs_human_review=True, page_url=page.get("url", ""))


STOCK_PHOTO_RE = re.compile(
    r"stock\s*(?:photo|image|picture)s?|representative\s*(?:photo|image|picture)s?|for\s*illustration(?:\s*purposes)?(?:\s*only)?"
    r"|(?:photos?|images?|pictures?)\s*(?:may|might)\s*not\s*(?:reflect|represent|be\s*(?:of\s*)?the\s*actual)", re.I)


@check("FTC-USED-STOCK-PHOTO", "FTC", "FTC Pricing Transparency", ["used", "cpo"])
def _ftc_used_stock_photo(page_key, page, ctx):
    """FAQ Q11: used-vehicle shoppers reasonably expect the photo to be the exact car."""
    m = STOCK_PHOTO_RE.search(_all_text(page))
    if not m:
        return None
    return CheckResult("FTC-USED-STOCK-PHOTO", "FTC", "FTC Pricing Transparency", page_key,
                       status="fail", confidence="medium", severity="warning",
                       rule_id="FTC-PIC-001", statute=FTC_FAQ + " Q11; VC §11713(s)",
                       evidence="'%s' on %s: stock or representative imagery on used-vehicle inventory." % (_short(m.group(0), 60), page_key),
                       recommendation="Replace stock or representative images on used and CPO listings with photos of the actual vehicle. FTC staff say used-car shoppers reasonably expect the photo to be the exact car (Q11). Confirm whether the language is a site-wide boilerplate or applies to specific units.",
                       needs_human_review=True, page_url=page.get("url", ""))


LEASE_DAS_FEE_RE = re.compile(
    r"due\s*at\s*(?:lease\s*)?signing[^.]{0,100}?(?:plus|excludes?|excluding|does\s*not\s*include|not\s*including)[^.]{0,60}?"
    r"(?:doc(?:ument(?:ary|ation)?)?\.?\s*(?:processing\s*)?(?:fee|charge)|processing\s*(?:fee|charge)|dealer\s*(?:fee|charge)s?)", re.I)


@check("FTC-LEASE-DAS-FEE", "FTC", "FTC Pricing Transparency", ["specials", "homepage", "vdp"])
def _ftc_lease_das_fee(page_key, page, ctx):
    """FAQ Q8: upfront processing fees belong inside an advertised due-at-signing total."""
    m = LEASE_DAS_FEE_RE.search(_all_text(page))
    if not m:
        return None
    return CheckResult("FTC-LEASE-DAS-FEE", "FTC", "FTC Pricing Transparency", page_key,
                       status="fail", confidence="high", severity="warning",
                       rule_id="FTC-LEASE-001", statute=FTC_FAQ + " Q8; Reg M 12 CFR 1013.7",
                       evidence="'%s' on %s: due-at-signing total excludes an upfront fee." % (_short(m.group(0), 100), page_key),
                       recommendation="Include every doc, processing, or dealer fee due upfront in the advertised amount due at signing (FTC FAQ Q8). Reg M disclosures still apply.",
                       page_url=page.get("url", ""))


@check("CA-NEWUSED-001", "DISCLOSURE", "Used Vehicle Labeling", ["used"])
def _used_label(page_key, page, ctx):
    title_url = (page.get("title", "") + " " + page.get("url", ""))
    if re.search(r"used|pre-?owned|previously\s*owned", title_url, re.I):
        return None  # page-level "Used" context is sufficient
    for i, listing in enumerate(page.get("sample_listings", []) or []):
        if not listing.get("has_used_label", False):
            return CheckResult("CA-NEWUSED-001", "DISCLOSURE", "Used Vehicle Labeling", page_key,
                               status="fail", confidence="medium", severity="warning",
                               rule_id="CA-NEWUSED-001", statute="VC §11713.16(a)",
                               evidence="Used listing #%d not labeled 'Used'/'Pre-Owned' and page title does not indicate used." % (i + 1),
                               recommendation="Label all used vehicles with 'Used', 'Pre-Owned', or similar.",
                               needs_human_review=True)
    return None


def _looks_like_hostname(name):
    """A captured dealer_name like 'www.mcpeeks.com' is extraction junk, not a name."""
    return bool(re.search(r"(?:^|\s)www\.|\.(?:com|net|org|us|biz|info)\b", name, re.I))


@check("CA-DEALER-001", "DISCLOSURE", "Dealer Identification", ["homepage"])
def _dealer_name_in_title(page_key, page, ctx):
    dealer = (page.get("dealer_name") or "").strip()
    if len(dealer) <= 2:
        return None
    if _looks_like_hostname(dealer):
        # 2026-08-06 McPeek run: extractor captured 'www.mcpeeks.com' and this check
        # shipped a false CRITICAL against a title that plainly named the dealer.
        # A hostname is a missing dealer_name, not evidence of a violation.
        return CheckResult("CA-DEALER-001", "DISCLOSURE", "Dealer Identification", page_key,
                           status="unresolved", confidence="low", rule_id="CA-DEALER-001",
                           statute="VC §11713.1(a); 13 CCR §260.00",
                           evidence="Captured dealer_name '%s' looks like a hostname, not a dealer name; "
                                    "the extractor missed the real name so the title check cannot run." % dealer,
                           recommendation="Re-extract the dealer name (og:site_name, schema.org AutoDealer, "
                                          "logo alt text) and confirm it appears in the homepage title.",
                           needs_human_review=True, page_url=page.get("url", ""))
    title = (page.get("title") or "").lower()
    dn = dealer.lower()
    parts = [p for p in dn.split() if len(p) > 3]
    found = dn in title or (parts and any(p in title for p in parts[:2]))
    if found:
        return CheckResult("CA-DEALER-001", "DISCLOSURE", "Dealer Identification", page_key,
                           status="pass", confidence="high", rule_id="CA-DEALER-001",
                           statute="VC §11713.1(a); 13 CCR §260.00",
                           evidence="Dealer name appears in the homepage title.")
    return CheckResult("CA-DEALER-001", "DISCLOSURE", "Dealer Identification", page_key,
                       status="fail", confidence="high", severity="critical",
                       rule_id="CA-DEALER-001", statute="VC §11713.1(a); 13 CCR §260.00",
                       evidence="Homepage title '%s' does not contain dealer name '%s'." % (_short(page.get("title", ""), 60), dealer),
                       recommendation="Ensure the dealer legal/DBA name appears in the homepage title.")


# ══════════════════════════════════════════════════════════════
# BRAND identity (ported automatable OEM checks)
# ══════════════════════════════════════════════════════════════

@check("BRAND-FCA-NAME", "BRAND", "OEM Brand Guidelines", ["__crawl__"])
def _brand_fca_name(page_key, crawl, ctx):
    if (ctx.get("brand") or "").lower() not in ("cdjr", "stellantis"):
        return None
    pat = re.compile(r"\bFCA\b|Fiat\s*Chrysler\s*Automobile", re.I)
    for pk, pd in _valid_pages(crawl):
        if pat.search(_all_text(pd)):
            return CheckResult("BRAND-FCA-NAME", "BRAND", "OEM Brand Guidelines", pk,
                               status="fail", confidence="high", severity="warning",
                               rule_id="STEL-DISC-001",
                               evidence="Outdated corporate name (FCA / Fiat Chrysler) on %s." % pk,
                               recommendation="Update 'FCA' / 'Fiat Chrysler Automobiles' to 'Stellantis'.",
                               page_url=pd.get("url", ""))
    return None


@check("BRAND-FIAT", "BRAND", "OEM Brand Guidelines", ["__crawl__"])
def _brand_fiat(page_key, crawl, ctx):
    if (ctx.get("brand") or "").lower() not in ("cdjr", "stellantis"):
        return None
    pat = re.compile(r"\bFiat\b(?!\s*Chrysler)", re.I)
    pages = [pk for pk, pd in _valid_pages(crawl) if pat.search(pd.get("title", ""))]
    if not pages:
        return None
    return CheckResult("BRAND-FIAT", "BRAND", "OEM Brand Guidelines", pages[0],
                       status="fail", confidence="medium", severity="warning",
                       rule_id="STEL-LOGO-002",
                       evidence="'Fiat' in page titles on: %s" % ", ".join(pages),
                       recommendation="Remove 'Fiat' from titles/dealer-name references if the store holds no Fiat franchise.",
                       needs_human_review=True, page_url=crawl.get("url", ""))


@check("BRAND-GM-FINANCIAL", "BRAND", "OEM Brand Guidelines", ["specials", "finance"])
def _brand_gm_financial(page_key, page, ctx):
    if (ctx.get("brand") or "").lower() not in ("chevrolet", "chevy"):
        return None
    text = _all_text(page)
    if not re.search(r"lease|finance|apr|month", text[:3000], re.I):
        return None
    if re.search(r"GM\s*Financial|General\s*Motors\s*Financial", text, re.I):
        return CheckResult("BRAND-GM-FINANCIAL", "BRAND", "OEM Brand Guidelines", page_key,
                           status="pass", confidence="medium", rule_id="CHEVY-PRICE-002",
                           evidence="GM Financial attribution present on offer page.")
    return CheckResult("BRAND-GM-FINANCIAL", "BRAND", "OEM Brand Guidelines", page_key,
                       status="fail", confidence="medium", severity="warning",
                       rule_id="CHEVY-PRICE-002",
                       evidence="Lease/finance offers on %s without GM Financial attribution." % page_key,
                       recommendation="Attribute lease/finance offers through GM Financial.",
                       needs_human_review=True)


@check("BRAND-SUBPAGE-TITLE", "BRAND", "OEM Brand Guidelines", ["vlp", "specials"])
def _brand_subpage_title(page_key, page, ctx):
    brand = (ctx.get("brand") or "").lower()
    names = {"bmw": ["BMW"], "nissan": ["Nissan"], "cdjr": ["Chrysler", "Dodge", "Jeep", "Ram"],
             "stellantis": ["Chrysler", "Dodge", "Jeep", "Ram"], "chevrolet": ["Chevrolet", "Chevy"],
             "chevy": ["Chevrolet", "Chevy"], "harley": ["Harley"]}.get(brand)
    if not names:
        return None
    title = page.get("title", "")
    if any(n.lower() in title.lower() for n in names):
        return CheckResult("BRAND-SUBPAGE-TITLE", "BRAND", "OEM Brand Guidelines", page_key,
                           status="pass", confidence="high",
                           rule_id=ctx.get("brand_rule_ids", {}).get("title", "BRAND-WEB-TITLE"),
                           evidence="Brand name present in %s page title." % page_key)
    return CheckResult("BRAND-SUBPAGE-TITLE", "BRAND", "OEM Brand Guidelines", page_key,
                       status="fail", confidence="high", severity="advisory",
                       rule_id=ctx.get("brand_rule_ids", {}).get("title", "BRAND-WEB-TITLE"),
                       evidence="%s page title '%s' has no brand name (%s)." % (page_key.upper(), _short(title, 50), "/".join(names)),
                       recommendation="Include the brand name in the %s page title." % page_key)


@check("BRAND-MODEL-ORDER", "BRAND", "OEM Brand Guidelines", ["__crawl__"])
def _brand_model_order(page_key, crawl, ctx):
    if (ctx.get("brand") or "").lower() not in ("cdjr", "stellantis"):
        return None
    pat = re.compile(r"Grand\s+Jeep\s+Cherokee|New\s+Grand\s+Jeep|Grand\s+Dodge\s+|Grand\s+Ram\s+|Grand\s+Chrysler\s+", re.I)
    for pk, pd in _valid_pages(crawl):
        title = pd.get("title", "")
        if pat.search(title) or pat.search(_excerpt(pd)[:1000]):
            return CheckResult("BRAND-MODEL-ORDER", "BRAND", "OEM Brand Guidelines", pk,
                               status="fail", confidence="high", severity="warning",
                               rule_id="STEL-WEB-002",
                               evidence="Incorrect model word order on %s (title='%s')." % (pk, _short(title, 50)),
                               recommendation="Use official Stellantis naming: make first, then model (e.g., 'Jeep Grand Cherokee').",
                               page_url=pd.get("url", ""))
    return None


# ══════════════════════════════════════════════════════════════
# ADA / UNRUH — website accessibility (the #1 dealer website lawsuit vector
# in California; Unruh Civil Rights Act statutory damages start at $4,000 each).
# Automated a11y is heuristic, so these are advisory/warning + human-review, never
# critical. They run only when the crawl captured an `accessibility` object.
# ══════════════════════════════════════════════════════════════

@check("ADA-ALT-TEXT", "ADA", "Accessibility (ADA/Unruh)", ["homepage"])
def _ada_alt_text(page_key, page, ctx):
    a = page.get("accessibility")
    if not isinstance(a, dict):
        return None
    total = a.get("images_total", 0) or 0
    missing = a.get("images_missing_alt", 0) or 0
    if total < 5:
        return None  # too few images to judge meaningfully
    ratio = missing / total if total else 0
    if missing == 0:
        return CheckResult("ADA-ALT-TEXT", "ADA", "Accessibility (ADA/Unruh)", page_key,
                           status="pass", confidence="medium", rule_id="ADA-IMG-ALT",
                           statute="ADA Title III; Cal. Civ. Code §51 (Unruh); WCAG 2.1 1.1.1",
                           evidence="All %d homepage images carry alt text." % total,
                           needs_human_review=True)
    if missing < 3 and ratio < 0.15:
        return None
    sev = "warning" if ratio >= 0.3 or missing >= 10 else "advisory"
    return CheckResult("ADA-ALT-TEXT", "ADA", "Accessibility (ADA/Unruh)", page_key,
                       status="fail", confidence="medium", severity=sev,
                       rule_id="ADA-IMG-ALT",
                       statute="ADA Title III; Cal. Civ. Code §51 (Unruh); WCAG 2.1 1.1.1",
                       evidence="%d of %d homepage images missing alt text." % (missing, total),
                       recommendation="Add descriptive alt text to images. Missing alt text is the most "
                                      "commonly cited issue in serial ADA/Unruh dealer-website suits.",
                       needs_human_review=True)


@check("ADA-FORM-LABELS", "ADA", "Accessibility (ADA/Unruh)", ["homepage"])
def _ada_form_labels(page_key, page, ctx):
    a = page.get("accessibility")
    if not isinstance(a, dict):
        return None
    inputs = a.get("inputs_total", 0) or 0
    unlabeled = a.get("inputs_missing_label", 0) or 0
    if inputs == 0 or unlabeled == 0:
        return None
    return CheckResult("ADA-FORM-LABELS", "ADA", "Accessibility (ADA/Unruh)", page_key,
                       status="fail", confidence="medium", severity="warning",
                       rule_id="ADA-FORM-LABEL",
                       statute="ADA Title III; Cal. Civ. Code §51 (Unruh); WCAG 2.1 1.3.1/4.1.2",
                       evidence="%d of %d form fields have no associated label/aria-label." % (unlabeled, inputs),
                       recommendation="Give every input a programmatic label (<label for>, aria-label, or aria-labelledby). "
                                      "Unlabeled lead-form fields are a frequent ADA/Unruh claim.",
                       needs_human_review=True)


@check("ADA-LANG-SKIPNAV", "ADA", "Accessibility (ADA/Unruh)", ["homepage"])
def _ada_lang_skipnav(page_key, page, ctx):
    a = page.get("accessibility")
    if not isinstance(a, dict):
        return None
    gaps = []
    if a.get("has_lang_attr") is False:
        gaps.append("no <html lang> attribute (WCAG 3.1.1)")
    if a.get("has_skip_nav") is False:
        gaps.append("no skip-to-content link (WCAG 2.4.1)")
    if not gaps:
        return None
    return CheckResult("ADA-LANG-SKIPNAV", "ADA", "Accessibility (ADA/Unruh)", page_key,
                       status="fail", confidence="high", severity="advisory",
                       rule_id="ADA-STRUCTURE",
                       statute="ADA Title III; Cal. Civ. Code §51 (Unruh); WCAG 2.1",
                       evidence="Homepage structure gaps: " + "; ".join(gaps) + ".",
                       recommendation="Add a valid <html lang> attribute and a skip-to-main-content link. "
                                      "Both are quick fixes that close easy ADA/Unruh exposure.")


# ══════════════════════════════════════════════════════════════
# TCPA — lead-form consent for calls/texts. A phone-capturing lead form with no
# prior-express-written-consent disclosure is a clean per-contact damages claim.
# ══════════════════════════════════════════════════════════════

@check("TCPA-CONSENT", "TCPA", "TCPA Lead-Form Consent", ["homepage"])
def _tcpa_consent(page_key, page, ctx):
    privacy = page.get("privacy")
    if not isinstance(privacy, dict):
        return None
    forms = privacy.get("lead_forms_have_privacy_notice", []) or []
    phone_forms = [f for f in forms if f.get("has_phone")]
    if not phone_forms:
        return None
    missing = [f for f in phone_forms if not f.get("has_tcpa_consent")]
    if not missing:
        return CheckResult("TCPA-CONSENT", "TCPA", "TCPA Lead-Form Consent", page_key,
                           status="pass", confidence="medium", rule_id="TCPA-CONSENT",
                           statute="47 U.S.C. §227; 47 CFR 64.1200",
                           evidence="Phone-capturing lead form(s) carry call/text consent language.",
                           needs_human_review=True)
    return CheckResult("TCPA-CONSENT", "TCPA", "TCPA Lead-Form Consent", page_key,
                       status="fail", confidence="medium", severity="warning",
                       rule_id="TCPA-CONSENT", statute="47 U.S.C. §227; 47 CFR 64.1200",
                       evidence="%d lead form(s) collect a phone number with no call/text consent disclosure." % len(missing),
                       recommendation="Add prior-express-written-consent language next to the phone field "
                                      "(consent to autodialed/prerecorded calls and texts, message/data rates, opt-out, "
                                      "and that consent is not a condition of purchase).",
                       needs_human_review=True)


# ── runner ───────────────────────────────────────────────────

def run_checks(crawl_data, brand="", brand_rules=None, only_check_ids=None):
    """Run the full registry over crawl_data. Returns List[CheckResult].

    only_check_ids: if given, run just those checks (used by the verify loop to
    re-run exactly the checks that were unresolved, after a re-crawl)."""
    ctx = {
        "brand": brand,
        "brand_rules": brand_rules or {},
        "brand_rule_ids": _brand_rule_ids(brand_rules),
    }
    pages = crawl_data.get("pages", {})
    results = []
    for check_id, framework, ftitle, page_keys, fn in _REGISTRY:
        if only_check_ids and check_id not in only_check_ids:
            continue
        for pk in page_keys:
            # "__crawl__" is a site-wide scope: the check runs ONCE and inspects
            # the whole crawl itself (used for "flag once across all pages" checks
            # like waiver/add-on/zero-down language). The fn receives the full
            # crawl_data in place of a single page and sets its own page/page_url.
            if pk == "__crawl__":
                target_keys = ["__crawl__"]
            elif pk == "vdp":
                # Fan every VDP check across ALL randomly-sampled VDPs (vdp, vdp_2,
                # vdp_3, ...) so a systemic per-vehicle issue (missing finance
                # disclosure, MSRP w/o disclaimer) is caught across the lot, not
                # just on one car. Each sampled VDP keeps its own page key so the
                # verify loop can re-crawl and de-dup them independently.
                target_keys = _vdp_keys(pages) or ["vdp"]
            else:
                target_keys = [pk]
            for tk in target_keys:
                if tk == "__crawl__":
                    page = crawl_data
                else:
                    page = pages.get(tk)
                    if not page or (isinstance(page, dict) and page.get("error")):
                        continue
                try:
                    res = fn(tk, page, ctx)
                except Exception as e:  # a check bug must never crash the audit
                    res = CheckResult(
                        check_id=check_id, framework=framework, framework_title=ftitle,
                        page=tk, status="unresolved", confidence="low",
                        evidence="check error: %s" % e, needs_human_review=True)
                # A check may return None, a single CheckResult, or a list of them.
                for r in (res if isinstance(res, list) else [res]):
                    if not r:
                        continue
                    if not r.page_url and tk != "__crawl__":
                        r.page_url = page.get("url", "") if isinstance(page, dict) else ""
                    results.append(r)
    _apply_cars_posture(results)
    return results


def _brand_rule_ids(brand_rules):
    """Best-effort map of semantic slots → real rule ids from the guidelines JSON."""
    out = {}
    if not brand_rules:
        return out
    for c in brand_rules.get("checks", []):
        cat = (c.get("category") or "").lower()
        cid = c.get("id", "")
        if "cpo" in cid.lower() or "certified" in (c.get("title", "").lower()):
            out.setdefault("cpo", cid)
        if "title" in (c.get("title", "").lower()) or "web" in cid.lower():
            out.setdefault("title", cid)
        if "exclus" in (c.get("title", "").lower()) or "exclus" in cat:
            out.setdefault("exclusivity", cid)
    return out


def registry_summary():
    """List every codified check, for documentation/tests."""
    rows = []
    for check_id, framework, ftitle, pages, _ in _REGISTRY:
        rows.append({"check_id": check_id, "framework": framework,
                     "framework_title": ftitle, "pages": list(pages)})
    return rows


HUMAN_REVIEW_PREFIX = (
    "**NEEDS HUMAN REVIEW AND VERIFICATION** — The automated audit could not fully "
    "verify this finding (e.g., due to popups, collapsed content, or visual layout). "
    "Please visually double-check this item. ")


# Findings = the subset of results that are actual violations (status == fail).
def results_to_findings(results):
    findings = []
    for r in results:
        if r.status != "fail":
            continue
        rec = r.recommendation or ""
        if r.needs_human_review and not rec.startswith("**NEEDS HUMAN REVIEW"):
            rec = HUMAN_REVIEW_PREFIX + rec
        findings.append({
            "page_url": r.page_url or (r.needs_data["url"] if r.needs_data else ""),
            "page": r.page,
            "finding_type": "brand_violation" if r.framework == "BRAND" else "legal_violation",
            "rule_id": r.rule_id or r.check_id,
            "title": r.framework_title + " — " + r.check_id,
            "quote": r.evidence,
            "severity": r.severity or "advisory",
            "source": "brand_check" if r.framework == "BRAND" else "legal_check",
            "statute": r.statute,
            "recommendation": rec,
            "confidence": r.confidence,
            "needs_human_review": r.needs_human_review,
            "reverified": r.reverified,
        })
    return findings
