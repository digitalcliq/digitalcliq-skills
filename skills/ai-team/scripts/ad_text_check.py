#!/usr/bin/env python3
"""Ad text compliance scan for the ai-team night shift. READ-ONLY, standard library only.

Reads the `ad_text_7d` tab that scripts/ads_export_v2.gs writes into each store's Ads
export Sheet (responsive search ad headlines and descriptions, final URL, status,
campaign, ad group, 7-day delivery) and flags price, payment, APR, lease, "free",
discount / savings, and add-on language against the federal layer first, then the
California layer (Rule 24), citing rule ids from:
  Resources/automotive-guidelines/federal-ad-rules-index.md   (L55 sections, bright lines)
  Resources/automotive-guidelines/ca-cars-act-sb766-index.md  (CARS-ADV / -DIS / -MIS ids)
  Resources/automotive-guidelines/cncda-cars-act-guidance.md  (CARS-ADV-08 onward)
  dealership-compliance-audit rules/ca_hard_rules.json         (CA-* and FTC-* ids)
Every hit is "flagged for review". Nothing here clears an ad, and nothing is changed
in any Ads account.

Usage (from the vault root, one plain command):
  python3 .claude/skills/ai-team/scripts/ad_text_check.py --store NOI --out outputs/ai-team/{date}/data
  python3 .claude/skills/ai-team/scripts/ad_text_check.py --store ALL --out outputs/ai-team/{date}/data
  python3 .claude/skills/ai-team/scripts/ad_text_check.py --store NOI --file dump.json   (gdata.py sheet output, CSV or TSV)
  python3 .claude/skills/ai-team/scripts/ad_text_check.py --selftest

Writes ad_text_{STORE}.json and ad_text_{STORE}.md into --out. Exit 0 ok, 2 when the
tab is missing (v2 not installed) or the export is unreadable.
"""
import argparse
import csv
import datetime as dt
import io
import json
import os
import re
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
VAULT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
DATA_SOURCES = os.path.join(HERE, "..", "references", "data-sources.md")
OPERATIVE = "2026-10-01"
TAB = "ad_text_7d"
# Fallback only; the live source of truth is the Google Ads table in references/data-sources.md.
FALLBACK_SHEETS = {
    "MCP": "1BOTg4rKHz3P99EOGbNBK_ZCoN1YPJHeX6kP58XIqh0c",
    "NOI": "1C9bf6Ede7xbeDzK2gLlQ4L0MoVeQfRoogrFRNx1FN-U",
    "ATLAS": "19l16Y6Sn3817ScpxhsEHRKdW4r-iy0vXNmj_JEnvaPE",
}
CA_STORES = {"MCP", "NOI", "SBMW", "NCBMW", "CHC"}  # California dealers; ATLAS gets federal only

# ------------------------------------------------------------------ rules
# Each rule: id, severity (high | review | info), label, cites (federal first, then California),
# and a test(asset_text, ad_context) -> (hit_text or None, note).

MONEY_BIG = re.compile(r"\$\s?\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\$\s?\d{4,6}\b")
SAVINGS_NEAR = re.compile(r"(save|savings|off|rebate|cash|bonus|below|under|discount|allowance|trade|credit|incentive|"
                          r"toward|towards|up\s+to|due|down|signing|deposit)", re.I)
PAYMENT = re.compile(r"\$\s?\d{2,4}(?:\.\d{2})?\s*(?:/|per|a)\s*(?:mo\b|mos\b|month)|monthly\s+payments?\s+(?:of|from|as\s+low)"
                     r"|payments?\s+(?:as\s+low\s+as|from|of|starting\s+at)\s+\$", re.I)
DOWN = re.compile(r"\$\s?[\d,]+\s*down\b|\d{1,2}\s*%\s*down\b|\b(?:zero|\$0|no\s+money|nothing|0)\s+down\b", re.I)
TERM = re.compile(r"\b(?:for|up\s+to|over)\s+\d{2}\s*(?:months|mos?\.?)\b|\b\d{2}[\s-]*(?:month|mo\.?)\s+(?:term|financing|loan)", re.I)
APR = re.compile(r"\d{1,2}(?:\.\d{1,3})?\s*%\s*(?:apr\b|a\.p\.r\.|annual\s+percentage\s+rate)", re.I)
RATE_NO_APR = re.compile(r"\d{1,2}(?:\.\d{1,3})?\s*%\s*(?:financing|finance|interest|rate)\b", re.I)
OAC = re.compile(r"\bO\.?\s?A\.?\s?C\b\.?")
LEASE_WORD = re.compile(r"\bleas(?:e|es|ing)\b", re.I)
DUE_SIGNING = re.compile(r"due\s+at\s+(?:lease\s+)?signing|sign\s*(?:&|and|n)\s*drive|drive[\s-]*off|\$0\s+due", re.I)
FREE = re.compile(r"(?<![\w-])(free|complimentary|gift|no\s+charge|at\s+no\s+(?:extra\s+)?cost|on\s+us)\b(?!-)", re.I)
FREE_COMPOUND = re.compile(r"(hassle|stress|worry|accident|hands|pressure|haggle|toll|tax|headache|risk|care|duty|"
                           r"smoke|pet|damage|rust|lead|obligation|commitment|spam)[\s-]*$", re.I)
NOMINAL = re.compile(r"\b(?:99\s*cents|\$0?\.99\b|\$1\b(?![,.\d])|one\s+dollar|1\s*cent|a\s+penny)", re.I)
PURCHASE_CTX = re.compile(r"with\s+(?:any|every|each|the|your)?\s*(?:new\s+|used\s+|pre-?owned\s+|vehicle\s+|car\s+)?"
                          r"(?:purchase|lease)|when\s+you\s+(?:buy|lease|purchase)|with\s+(?:every|any|each)\s+(?:new|used|"
                          r"vehicle|car|nissan|bmw|chevy|chevrolet|jeep|ram|dodge|chrysler)|buy\s+(?:a|any|your|one)\b.{0,40}\b"
                          r"(?:get|receive)|purchase\s+required", re.I)
SERVICE_CTX = re.compile(r"oil\s+change|service|inspection|car\s+wash|tire\s+rotation|alignment|diagnostic|multi[\s-]?point|"
                         r"battery|brake|wiper|parts|shuttle|loaner|wi-?fi|coffee|carfax|history\s+report|quote|appraisal|"
                         r"estimate|valuation|test\s+drive|consultation|check[\s-]?up", re.I)
DISC = re.compile(r"\bsave\b|\bsavings?\b|\bdiscount(?:s|ed)?\b|\$[\d,]+\s*off\b|\d{1,2}\s*%\s*off\b|(?:off|below|under)\s+msrp"
                  r"|\brebates?\b|cash\s+back|bonus\s+cash|customer\s+cash|\bup\s+to\s+\$|\bincentives?\b|\bmark\s?downs?\b"
                  r"|\bclearance\b|\bblowout\b|(?<!for\s)\bsale\b|sales?\s+event", re.I)
UP_TO = re.compile(r"\bup\s+to\s+\$", re.I)
CASH_BACK = re.compile(r"cash\s+back|dealer\s+(?:cash|rebate)", re.I)
REBATE = re.compile(r"\brebates?\b|\bincentives?\b|bonus\s+cash|customer\s+cash", re.I)
SALE_EVENT = re.compile(r"(?<!for\s)\bsale\b|sales?\s+event|\bclearance\b|\bblowout\b|\bevent\b", re.I)
INVOICE = re.compile(r"\binvoice\b|dealer\s+cost|wholesale\s+price|below\s+cost|at\s+cost\b", re.I)
PROGRAM = re.compile(r"employee\s+pricing|supplier\s+pricing|costco|truecar|military|first\s+responder|college\s+grad|"
                     r"loyalty|conquest", re.I)
FACTORY_AUTH = re.compile(r"factory[\s-]+authori[sz]ed", re.I)
ADDON = re.compile(r"add[\s-]?ons?\b|dealer[\s-]+(?:installed|added|add)|protection\s+(?:package|plan)|paint\s+protection|ceramic\s+coat"
                   r"|window\s+tint|nitrogen|theft\s+(?:protection|deterrent)|lojack|gps\s+track|market\s+adjust|\bADM\b|"
                   r"additional\s+dealer\s+mark|addendum|accessor(?:y|ies)\s+package|pre-?installed|mark[\s-]?ups?\b", re.I)
NO_ADDON = re.compile(r"\bno\s+(?:dealer\s+)?(?:add[\s-]?ons?|mark[\s-]?ups?|adm|market\s+adjust\w*|addendum|hidden\s+fees)", re.I)
GUAR_CREDIT = re.compile(r"guaranteed\s+(?:credit\s+)?(?:approval|financing|credit)|every(?:one|body)\s+(?:is\s+)?approved|"
                         r"all\s+credit\s+(?:approved|accepted)|no\s+credit\s+check|you'?re\s+approved", re.I)
PREAPPROVED = re.compile(r"\bpre[\s-]?(?:approved|qualified)\b", re.I)
PAYOFF = re.compile(r"pay\s*off\s+your\s+trade|no\s+matter\s+what\s+you\s+owe|guaranteed\s+trade|guaranteed\s+\$[\d,]+\s+for\s+your\s+trade",
                    re.I)
OTD = re.compile(r"out[\s-]+the[\s-]+door", re.I)
STARTING = re.compile(r"(?:starting\s+at|from|as\s+low\s+as|under|only)\s+\$", re.I)
MSRP = re.compile(r"\bmsrp\b", re.I)
EXPIRY = re.compile(r"expir|\bends?\b\s+\d|\boffer\s+ends\b|\bthrough\s+\d|\bthru\s+\d|\buntil\s+\d|\bby\s+\d{1,2}/\d{1,2}|"
                    r"\b(?:1[0-2]|0?[1-9])/(?:[12]\d|3[01]|0?[1-9])(?:/\d{2,4})?\b|"
                    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b", re.I)


def _m(rx, text):
    m = rx.search(text)
    return m.group(0) if m else None


def t_price(text, ctx):
    for m in MONEY_BIG.finditer(text):
        around = text[max(0, m.start() - 14):m.end() + 14]
        if SAVINGS_NEAR.search(around) or PAYMENT.search(text[m.start():m.end() + 14]):
            continue
        return m.group(0), ""
    return None, ""


def t_price_from(text, ctx):
    m = STARTING.search(text)
    if m and MONEY_BIG.search(text[m.start():m.end() + 12]):
        return text[m.start():m.end() + 10].strip(), ""
    return None, ""


def t_msrp(text, ctx):
    return _m(MSRP, text), ""


def t_payment(text, ctx):
    hit = _m(PAYMENT, text)
    if not hit:
        return None, ""
    if ctx["lease"]:
        return None, ""  # handled by the lease rule
    return hit, "not labeled lease or purchase" if not re.search(r"financ|loan|purchase|buy", ctx["all"], re.I) else ""


def t_down(text, ctx):
    return _m(DOWN, text), ""


def t_term(text, ctx):
    return _m(TERM, text), ""


def t_rate_no_apr(text, ctx):
    m = RATE_NO_APR.search(text)
    if m and not re.search(r"apr|annual\s+percentage", text[max(0, m.start() - 10):m.end() + 25], re.I):
        return m.group(0), ""
    return None, ""


def t_apr(text, ctx):
    hit = _m(APR, text)
    if not hit:
        return None, ""
    notes = []
    if not re.search(r"on\s+approved\s+credit|well[\s-]qualified|qualified\s+(buyers|customers)", ctx["all"], re.I):
        notes.append("no credit qualification in any asset")
    if ctx["term"]:
        notes.append("rate plus a term is a Reg Z trigger")
    return hit, "; ".join(notes)


def t_oac(text, ctx):
    return _m(OAC, text), ""


def t_lease(text, ctx):
    if not LEASE_WORD.search(text) and not (ctx["lease"] and (PAYMENT.search(text) or DUE_SIGNING.search(text))):
        return None, ""
    trig = _m(PAYMENT, text) or _m(DUE_SIGNING, text) or _m(DOWN, text) or _m(MONEY_BIG, text)
    if not trig and not (LEASE_WORD.search(text) and (PAYMENT.search(ctx["all"]) or DUE_SIGNING.search(ctx["all"]))):
        return None, ""
    return trig or _m(LEASE_WORD, text), ""


def t_due_zero(text, ctx):
    return _m(re.compile(r"\$0\s+due|zero\s+due|sign\s*(?:&|and|n)\s*drive|\$0\s+down", re.I), text), ""


def _free_hits(text):
    """'free' words that are offers, not compounds like hassle-free or stress free."""
    return [m.group(0) for m in FREE.finditer(text)
            if not FREE_COMPOUND.search(text[max(0, m.start() - 14):m.start()])]


def t_free_purchase(text, ctx):
    hits = _free_hits(text) or ([_m(NOMINAL, text)] if _m(NOMINAL, text) else [])
    if hits and (PURCHASE_CTX.search(text) or PURCHASE_CTX.search(ctx["all"])):
        return hits[0], ""
    return None, ""


def t_free_other(text, ctx):
    hits = _free_hits(text)
    if not hits or PURCHASE_CTX.search(text) or PURCHASE_CTX.search(ctx["all"]):
        return None, ""
    if SERVICE_CTX.search(text):
        return None, ""
    return hits[0], ""


def t_free_service(text, ctx):
    hits = _free_hits(text)
    if hits and SERVICE_CTX.search(text) and not (PURCHASE_CTX.search(text) or PURCHASE_CTX.search(ctx["all"])):
        return hits[0], "service, parts, or no-purchase offer"
    return None, ""


def t_invoice(text, ctx):
    return _m(INVOICE, text), ""


def t_up_to(text, ctx):
    return _m(UP_TO, text), ""


def t_cash_back(text, ctx):
    return _m(CASH_BACK, text), ""


def t_rebate(text, ctx):
    return _m(REBATE, text), ""


def t_discount(text, ctx):
    m = DISC.search(text)
    if not m:
        return None, ""
    if REBATE.search(m.group(0)) or UP_TO.search(m.group(0)) or CASH_BACK.search(m.group(0)) or SALE_EVENT.search(m.group(0)):
        m2 = re.search(r"\bsave\b|\bsavings?\b|\bdiscount|\$[\d,]+\s*off\b|\d{1,2}\s*%\s*off\b|(?:off|below|under)\s+msrp"
                       r"|\bmark\s?downs?\b", text, re.I)
        return (m2.group(0) if m2 else None), ""
    return m.group(0), ""


def t_sale_event(text, ctx):
    hit = _m(SALE_EVENT, text)
    if hit and not ctx["expiry"]:
        return hit, "no dates in any asset"
    return None, ""


def t_program(text, ctx):
    return _m(PROGRAM, text), ""


def t_factory(text, ctx):
    return _m(FACTORY_AUTH, text), ""


def t_no_addon(text, ctx):
    return _m(NO_ADDON, text), ""


def t_addon(text, ctx):
    if NO_ADDON.search(text):
        return None, ""
    return _m(ADDON, text), ""


def t_guar_credit(text, ctx):
    return _m(GUAR_CREDIT, text), ""


def t_preapproved(text, ctx):
    return _m(PREAPPROVED, text), ""


def t_payoff(text, ctx):
    return _m(PAYOFF, text), ""


def t_otd(text, ctx):
    return _m(OTD, text), ""


RULES = [
    # --- price
    ("ATC-PRICE", "review", "vehicle price in ad text",
     "Federal bright line 1 (L55 s.12, s.28): the most prominent price is the all-in price any buyer can pay; FTC-PRICE-001, "
     "FTC-PRICE-002 (doc fee inside), FTC-PRICE-003. CA: CARS-ADV-01/-02 and CA-CARS-001 (total price when a specific vehicle "
     "or monetary amount is advertised), CA-PRICE-001", t_price),
    ("ATC-PRICE-FROM", "review", "'starting at / from / as low as' price",
     "L55 s.31 ('up to' / from claims need substantiation). CA: Veh. Code 11713.1(i) number in stock beside the price "
     "(federal index, California overrides); CARS-ADV-18", t_price_from),
    ("ATC-MSRP", "review", "MSRP in ad text",
     "L55 s.17 (MSRP comparisons scrutinized). CA: CARS-ADV-11, CA-CARS-025 (MSRP only if labeled and no more prominent "
     "than the total price)", t_msrp),
    # --- payment and credit (Reg Z)
    ("ATC-PAYMENT", "review", "monthly payment (Reg Z trigger)",
     "Federal bright line 5 (L55 s.29, Reg Z 12 CFR 226.24): payment amount forces down payment, terms, and APR; "
     "L55 s.7 (clear and conspicuous in the medium). CA: CA-REGZ-001; CA-CARS-003 (total amount payable); "
     "CARS-ADV-02 (monetary amount for a specific vehicle needs its total price)", t_payment),
    ("ATC-DOWN", "review", "down payment term (Reg Z trigger)",
     "L55 s.11, s.29 (down payment amount is a trigger term). CA: CA-REGZ-001; CA-REGZ-004 for zero / no money down "
     "claims", t_down),
    ("ATC-TERM", "review", "number of payments or term (Reg Z trigger)",
     "L55 s.29 (number of payments or period is a trigger term). CA: CA-REGZ-001; CARS-DIS-04 and CA-CARS-004 "
     "when a longer term is sold on a lower payment", t_term),
    ("ATC-RATE-NO-APR", "high", "finance rate not labeled APR",
     "Federal bright line 7 (L55 s.2): a finance rate must be called APR. CA: CA-CARS-010 (no misrepresentation of "
     "financing terms)", t_rate_no_apr),
    ("ATC-APR", "review", "APR offer",
     "L55 s.9 (only credit terms actually available, material conditions such as on approved credit); L55 s.29 when a "
     "term is also stated. CA: CA-REGZ-001, CA-REGZ-002, CA-CARS-010", t_apr),
    ("ATC-OAC", "high", "'OAC' abbreviation",
     "L55 s.9. CA: CA-REGZ-002 (Veh. Code 11713.16(b): 'On Approved Credit' spelled out)", t_oac),
    # --- lease (Reg M)
    ("ATC-LEASE", "review", "lease terms (Reg M trigger)",
     "Federal bright line 6 (L55 s.22, Reg M): say it is a lease, total due at signing, number, amount, and timing of "
     "payments, security deposit; FTC-LEASE-001 (upfront fees inside due at signing). CA: CA-REGM-001, CA-REGM-002 "
     "(plus tax and license); CARS-ADV-17 and CA-CARS-030 (a lease ad that identifies a unit needs that unit's total "
     "price)", t_lease),
    ("ATC-LEASE-ZERO", "review", "$0 due / sign and drive",
     "L55 s.22; FTC-LEASE-001. CA: CA-REGM-003, CA-REGZ-004", t_due_zero),
    # --- free
    ("ATC-FREE-PURCHASE", "high", "'free' tied to a vehicle purchase",
     "Federal bright line 3 (L55 s.18): no free goods or services contingent on a vehicle purchase, including gift, "
     "bonus, and nominal pricing. CA: Veh. Code 11713.1(h) flat ban, below-cost counts as free (federal index, "
     "California overrides)", t_free_purchase),
    ("ATC-FREE", "review", "'free' offer, condition unclear",
     "L55 s.18 (confirm it is not contingent on a vehicle purchase), L55 s.20 (incentives to visit: disclose conditions). "
     "CA: Veh. Code 11713.1(h)", t_free_other),
    ("ATC-FREE-SERVICE", "info", "'free' service, parts, or no-purchase offer",
     "L55 s.18 and s.32 allow free service and parts offers; disclose what it covers and any conditions", t_free_service),
    # --- discount / savings / rebate
    ("ATC-INVOICE", "high", "invoice / dealer cost reference",
     "L55 s.17. CA: Veh. Code 11713.1(n), no invoice, dealer cost, or wholesale references in advertising (federal "
     "index, California overrides)", t_invoice),
    ("ATC-UP-TO", "review", "'up to $' savings or rebate",
     "L55 s.31 ('up to' needs substantiation that buyers actually get it). CA: CARS-ADV-19 and CA-CARS-028 ('up to $X in "
     "rebates' is problematic)", t_up_to),
    ("ATC-CASH-BACK", "review", "cash back / dealer rebate",
     "L55 s.28, s.31. CA: CARS-ADV-19 and CA-CARS-028 (dealer rebates and cash back are not permitted; rebate shown as "
     "a labeled amount, never deducted into the price), CARS-ADV-06", t_cash_back),
    ("ATC-REBATE", "review", "rebate or incentive",
     "Federal bright line 2 (L55 s.28, s.31): discounts not available to everyone stay out of the prominent price; "
     "FTC-PRICE-004. CA: CARS-ADV-06, CARS-ADV-19, CA-CARS-028, CA-DISC-002", t_rebate),
    ("ATC-DISCOUNT", "review", "savings or discount claim",
     "L55 s.17 (former price and MSRP comparisons), s.31 (discounts available to typical buyers). CA: CA-SALE-002 "
     "(Bus. & Prof. 17501 reference price), CA-DISC-002", t_discount),
    ("ATC-SALE-DATES", "review", "sale or event without dates",
     "L55 s.37. CA: CA-SALE-001 (a sale needs defined dates), CARS-ADV-09 and CA-CARS-034 (date every price ad)",
     t_sale_event),
    ("ATC-PROGRAM", "review", "program or group pricing",
     "FTC-PRICE-004 (conditional discounts outside the most prominent price), L55 s.31. CA: CARS-ADV-14, CA-DISC-002",
     t_program),
    ("ATC-FACTORY-AUTH", "review", "'factory authorized' claim",
     "L55 s.31 (only if the factory actually authorized it)", t_factory),
    # --- add-ons
    ("ATC-ADDON", "review", "add-on or installed-product language",
     "FTC-ADDON-001 (optional items presented honestly), L55 s.4 (undisclosed add-ons are bait). CA: CARS-ADV-03 and "
     "CARS-ADV-20 (installed items inside the total price, no pay-or-remove), CA-CARS-029, CA-CARS-002, CA-CARS-011",
     t_addon),
    ("ATC-NO-ADDON-CLAIM", "review", "'no add-ons / no markups / no hidden fees' claim",
     "L55 s.37 (claims must be substantiated), FTC-PRICE-001. CA: CARS-ADV-21 and CA-CARS-036 (no unit may carry an "
     "addendum item outside the total price)", t_no_addon),
    # --- credit and trade guarantees
    ("ATC-GUARANTEED-CREDIT", "high", "guaranteed approval / everyone approved",
     "L55 s.9, s.37. CA: CA-REGZ-003 (everyone financed claims), CA-CARS-010", t_guar_credit),
    ("ATC-PREAPPROVED", "high", "'pre-approved' / 'pre-qualified' claim",
     "L55 s.27 (prescreened offers need the firm-offer standard). CA: CARS-MIS-05 and CA-CARS-014 (misrepresenting "
     "preapproval)", t_preapproved),
    ("ATC-TRADE-PAYOFF", "high", "trade payoff guarantee",
     "Federal bright line 4 (L55 s.36). CA: Veh. Code 11713.1(l) (federal index, California overrides), CA-CARS-021",
     t_payoff),
    ("ATC-OTD", "review", "'out-the-door' price",
     "L55 s.12. CA: CARS-ADV-26 (never label the total price 'out-the-door')", t_otd),
]

AD_LEVEL = [
    ("ATC-NO-EXPIRY", "review", "priced or financed offer with no expiration in any asset",
     "L55 s.39 (expiration date). CA: CARS-ADV-09 and CA-CARS-034 (advertised price is a ceiling for anyone until an "
     "expiration passes; Veh. Code 11713.1(e))"),
    ("ATC-ROTATION", "info", "trigger term in an unpinned asset",
     "L55 s.7, s.21: responsive search ad assets rotate, so a disclosure in another asset may never serve with the "
     "trigger; a space-limited ad that cannot carry the disclosure should not make the claim"),
]
PRICED_RULES = {"ATC-PRICE", "ATC-PRICE-FROM", "ATC-PAYMENT", "ATC-DOWN", "ATC-APR", "ATC-LEASE", "ATC-LEASE-ZERO",
                "ATC-UP-TO", "ATC-CASH-BACK", "ATC-REBATE", "ATC-DISCOUNT", "ATC-RATE-NO-APR"}
TRIGGER_RULES = {"ATC-PAYMENT", "ATC-DOWN", "ATC-TERM", "ATC-APR", "ATC-LEASE", "ATC-LEASE-ZERO"}


# ------------------------------------------------------------------ core

def parse_list(cell):
    if cell is None or cell == "":
        return []
    if isinstance(cell, list):
        return [str(x) for x in cell]
    s = str(cell).strip()
    if s.startswith("["):
        try:
            return [str(x) for x in json.loads(s)]
        except ValueError:
            pass
    return [p.strip() for p in re.split(r"\s*\|\s*|\n", s) if p.strip()]


def rows_to_ads(values):
    if not values:
        return []
    header = [str(h).strip() for h in values[0]]
    ads = []
    for raw in values[1:]:
        r = dict(zip(header, list(raw) + [""] * (len(header) - len(raw))))
        heads = parse_list(r.get("headlines_json") or r.get("headlines"))
        descs = parse_list(r.get("descriptions_json") or r.get("descriptions"))
        pinned = {p.rsplit("=", 1)[0] for p in parse_list(r.get("pinned_json"))}
        try:
            imps = int(float(r.get("impressions_7d") or 0))
        except ValueError:
            imps = 0
        ads.append({
            "campaign": r.get("campaign_name", ""), "campaign_status": r.get("campaign_status", ""),
            "ad_group": r.get("adGroup_name", ""), "ad_id": str(r.get("adGroupAd_ad_id", "")),
            "status": r.get("adGroupAd_status", ""), "approval": r.get("adGroupAd_policySummary_approvalStatus", ""),
            "final_url": r.get("final_url", ""), "impressions_7d": imps,
            "assets": [("headline", t, t in pinned) for t in heads] + [("description", t, t in pinned) for t in descs],
        })
    return ads


def check_ad(ad, california=True):
    texts = [a[1] for a in ad["assets"]]
    all_text = " || ".join(texts)
    ctx = {"all": all_text, "lease": bool(LEASE_WORD.search(all_text)),
           "term": bool(TERM.search(all_text)), "expiry": bool(EXPIRY.search(all_text))}
    hits = []
    for rid, sev, label, cites, test in RULES:
        for kind, text, pinned in ad["assets"]:
            hit, note = test(text, ctx)
            if hit:
                hits.append({"rule": rid, "severity": sev, "label": label, "asset": kind, "pinned": pinned,
                             "text": text, "match": hit, "note": note})
                break  # one hit per rule per ad is enough for review
    fired = {h["rule"] for h in hits}
    if fired & PRICED_RULES and not ctx["expiry"]:
        rid, sev, label, cites = AD_LEVEL[0]
        hits.append({"rule": rid, "severity": sev, "label": label, "asset": "ad", "pinned": False, "text": "",
                     "match": "", "note": ""})
    unpinned = [h for h in hits if h["rule"] in TRIGGER_RULES and not h["pinned"]]
    if unpinned:
        rid, sev, label, cites = AD_LEVEL[1]
        hits.append({"rule": rid, "severity": sev, "label": label, "asset": "ad", "pinned": False, "text": "",
                     "match": unpinned[0]["match"], "note": ""})
    return hits


def cites_for(rid, california):
    table = {r[0]: r[3] for r in RULES}
    table.update({r[0]: r[3] for r in AD_LEVEL})
    c = table.get(rid, "")
    if not california and " CA: " in c:
        c = c.split(" CA: ")[0]
    return c


def scan(ads, store, meta=None, today=None):
    california = store.upper() in CA_STORES
    today = today or dt.date.today().isoformat()
    by_rule = {}
    flagged_ads = 0
    for ad in ads:
        hits = check_ad(ad, california)
        if any(h["severity"] != "info" for h in hits):
            flagged_ads += 1
        for h in hits:
            r = by_rule.setdefault(h["rule"], {"rule": h["rule"], "severity": h["severity"], "label": h["label"],
                                               "cites": cites_for(h["rule"], california), "ads": 0, "served_ads": 0,
                                               "examples": []})
            r["ads"] += 1
            if ad["impressions_7d"] > 0:
                r["served_ads"] += 1
            if len(r["examples"]) < 3 and (h["text"] or not r["examples"]):
                r["examples"].append({"text": h["text"], "match": h["match"], "note": h["note"], "asset": h["asset"],
                                      "pinned": h["pinned"], "campaign": ad["campaign"], "ad_group": ad["ad_group"],
                                      "final_url": ad["final_url"], "ad_id": ad["ad_id"],
                                      "impressions_7d": ad["impressions_7d"]})
    order = {"high": 0, "review": 1, "info": 2}
    rules = sorted(by_rule.values(), key=lambda r: (order[r["severity"]], -r["served_ads"], -r["ads"]))
    return {"store": store.upper(), "date": today, "california": california,
            "cars_mode": "operative" if today >= OPERATIVE else "readiness (operative %s)" % OPERATIVE,
            "export_meta": meta or {}, "ads_scanned": len(ads),
            "ads_served_7d": sum(1 for a in ads if a["impressions_7d"] > 0), "ads_flagged": flagged_ads,
            "rules": rules}


def render(res):
    m = res.get("export_meta") or {}
    lines = ["Ad text check %s: %d enabled RSAs scanned (%d served in the last 7 days), %d flagged for review. "
             "Export last_run %s%s." % (res["store"], res["ads_scanned"], res["ads_served_7d"], res["ads_flagged"],
                                        m.get("last_run", "unknown"), " (STALE)" if m.get("stale") else "")]
    if not res["california"]:
        lines.append("Federal layer only (store outside California).")
    elif res["cars_mode"] != "operative":
        lines.append("CARS Act citations are %s." % res["cars_mode"])
    for r in res["rules"]:
        ex = r["examples"][0] if r["examples"] else {}
        sample = (' e.g. "%s" [%s / %s]' % (ex.get("text", "")[:90], ex.get("campaign", ""), ex.get("ad_group", ""))
                  if ex.get("text") else "")
        lines.append("- %s (%s) %s: %d ad(s), %d served.%s" % (r["rule"], r["severity"], r["label"], r["ads"],
                                                               r["served_ads"], sample))
    if not res["rules"]:
        lines.append("No price, payment, APR, lease, free, discount, or add-on language found.")
    lines.append("Ad text only: landing pages, extensions, and PMax assets are not checked. Automated pattern scan, "
                 "flagged for review, not a legal determination.")
    return "\n".join(lines)


def render_md(res):
    out = ["# Ad text check: %s, %s" % (res["store"], res["date"]), "", render(res), ""]
    for r in res["rules"]:
        out.append("## %s %s (%s)" % (r["rule"], r["label"], r["severity"]))
        out.append("Cites: %s." % r["cites"])
        for ex in r["examples"]:
            if ex.get("text"):
                out.append('- "%s" (%s%s) [%s / %s] %s%s' % (
                    ex["text"], ex["asset"], ", pinned" if ex["pinned"] else "", ex["campaign"], ex["ad_group"],
                    ex["final_url"], ("; " + ex["note"]) if ex["note"] else ""))
        out.append("")
    return "\n".join(out)


# ------------------------------------------------------------------ inputs

def sheet_ids():
    ids = dict(FALLBACK_SHEETS)
    try:
        text = open(DATA_SOURCES).read()
        sec = text.split("## Google Ads", 1)[1].split("\n## ", 1)[0]
        for code, sid in re.findall(r"^\|\s*([A-Z]{2,6})\s*\|\s*[\d-]+\s*\|\s*`([A-Za-z0-9_-]{30,})`", sec, re.M):
            ids[code] = sid
    except Exception:
        pass
    return ids


def read_sheet(sid, rng):
    sys.path.insert(0, HERE)
    import gdata  # noqa: E402  (same folder; never edited here)
    url = "https://sheets.googleapis.com/v4/spreadsheets/%s/values/%s" % (sid, urllib.parse.quote(rng, safe=""))
    return gdata.api(url).get("values", [])


def read_meta(sid):
    try:
        vals = read_sheet(sid, "meta!A1:C40")
    except Exception as e:
        return {"error": str(e)[:200]}
    meta = {"tabs": {}}
    tabs = False
    for row in vals:
        row = list(row) + ["", "", ""]
        if row[0] == "tab":
            tabs = True
            continue
        if tabs and row[0]:
            meta["tabs"][row[0]] = {"rows": row[1], "status": row[2]}
        elif row[0]:
            meta[row[0]] = row[1]
    lr = meta.get("last_run", "")
    try:
        age = (dt.datetime.now() - dt.datetime.strptime(lr, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600
        meta["stale"] = age > 26
    except ValueError:
        meta["stale"] = None
    return meta


def read_file(path):
    raw = open(path).read()
    s = raw.lstrip()
    if s.startswith("["):
        return json.loads(s)
    dialect = "excel-tab" if "\t" in raw.splitlines()[0] else "excel"
    return list(csv.reader(io.StringIO(raw), dialect=dialect))


def run_store(store, args, ids):
    if args.file:
        values, meta = read_file(args.file), {"last_run": "file " + os.path.basename(args.file)}
    else:
        sid = ids.get(store)
        if not sid:
            print("%s: no Ads export Sheet id in references/data-sources.md; no ad text data." % store)
            return 2
        meta = read_meta(sid)
        if meta.get("error"):
            print("%s: export Sheet unreadable (%s); no ad text data." % (store, meta["error"]))
            return 2
        if TAB not in meta.get("tabs", {}):
            print("%s: %s tab not in the export yet (ads_export_v2.gs not installed in this account); "
                  "no ad text data." % (store, TAB))
            return 2
        try:
            values = read_sheet(sid, "%s!A1:Q5000" % TAB)
        except Exception as e:
            print("%s: could not read %s (%s)." % (store, TAB, str(e)[:200]))
            return 2
    ads = rows_to_ads(values)
    res = scan(ads, store, meta, args.date)
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, "ad_text_%s.json" % store), "w") as f:
            json.dump(res, f, indent=1)
        with open(os.path.join(args.out, "ad_text_%s.md" % store), "w") as f:
            f.write(render_md(res))
    print(render(res))
    return 0


# ------------------------------------------------------------------ selftest

SAMPLE = [
    ["campaign_name", "campaign_status", "campaign_advertisingChannelType", "adGroup_name", "adGroup_status",
     "adGroupAd_ad_id", "adGroupAd_status", "adGroupAd_policySummary_approvalStatus", "final_url", "headlines_json",
     "descriptions_json", "pinned_json", "path1", "path2", "impressions_7d", "clicks_7d", "cost_7d"],
    ["Search Rogue", "ENABLED", "SEARCH", "Rogue Lease", "ENABLED", "1", "ENABLED", "APPROVED", "https://x/rogue",
     json.dumps(["Lease a 2026 Rogue $299/mo", "Nissan of Irvine", "Hassle-Free Buying"]),
     json.dumps(["$2,999 due at signing. Free car wash with every new car purchase."]), "[]", "", "", 120, 5, 9.1],
    ["Search Finance", "ENABLED", "SEARCH", "Specials", "ENABLED", "2", "ENABLED", "APPROVED", "https://x/finance",
     json.dumps(["0.9% APR for 60 Months OAC", "1.9% Financing Available", "Save Up To $5,000 Off MSRP"]),
     json.dumps(["Below Invoice Pricing. Guaranteed Approval. Cash Back on Select Models."]), "[]", "", "", 0, 0, 0],
    ["Service", "ENABLED", "SEARCH", "Oil", "ENABLED", "3", "ENABLED", "APPROVED", "https://x/service",
     json.dumps(["Free Multi-Point Inspection", "Book Service Online"]),
     json.dumps(["Stress-free service. Offer expires 10/31/2026."]), "[]", "", "", 40, 2, 3.0],
    ["Brand", "ENABLED", "SEARCH", "Brand", "ENABLED", "4", "ENABLED", "APPROVED", "https://x/",
     json.dumps(["Nissan of Irvine", "Shop New Nissan Inventory", "Cars for Sale in Irvine"]),
     json.dumps(["Visit our showroom on Auto Center Dr."]), "[]", "", "", 500, 60, 40.0],
    ["Search Rogue", "ENABLED", "SEARCH", "Rogue Price", "ENABLED", "5", "ENABLED", "APPROVED", "https://x/rogue-sv",
     json.dumps(["2026 Rogue SV From $29,995", "No Dealer Markups", "Paint Protection Included"]),
     json.dumps(["Price excludes dealer-installed accessories. Rebates included."]),
     json.dumps(["2026 Rogue SV From $29,995=HEADLINE_1"]), "", "", 10, 1, 2.0],
]


def selftest():
    fails = []

    def expect(ad_id, rule, present=True):
        hits = {h["rule"] for h in check_ad(ads_by[ad_id])}
        if (rule in hits) != present:
            fails.append("ad %s: %s expected %s, got %s" % (ad_id, rule, "present" if present else "absent", sorted(hits)))

    ads = rows_to_ads(SAMPLE)
    ads_by = {a["ad_id"]: a for a in ads}
    expect("1", "ATC-LEASE")
    expect("1", "ATC-FREE-PURCHASE")
    expect("1", "ATC-NO-EXPIRY")
    expect("1", "ATC-ROTATION")
    expect("1", "ATC-PAYMENT", False)       # lease payment is handled by the lease rule
    expect("1", "ATC-FREE", False)          # 'Hassle-Free' is not a free offer
    expect("1", "ATC-PRICE", False)         # $2,999 due at signing is a lease term, not a vehicle price
    expect("2", "ATC-APR")
    expect("2", "ATC-TERM")
    expect("2", "ATC-OAC")
    expect("2", "ATC-RATE-NO-APR")
    expect("2", "ATC-UP-TO")
    expect("2", "ATC-MSRP")
    expect("2", "ATC-INVOICE")
    expect("2", "ATC-GUARANTEED-CREDIT")
    expect("2", "ATC-CASH-BACK")
    expect("3", "ATC-FREE-SERVICE")
    expect("3", "ATC-FREE-PURCHASE", False)
    expect("3", "ATC-FREE", False)
    expect("3", "ATC-NO-EXPIRY", False)
    expect("4", "ATC-SALE-DATES", False)    # 'Cars for Sale' is not a sale claim
    expect("4", "ATC-PRICE", False)
    expect("5", "ATC-PRICE-FROM")
    expect("5", "ATC-NO-ADDON-CLAIM")
    expect("5", "ATC-ADDON")
    expect("5", "ATC-REBATE")
    res = scan(ads, "NOI", {"last_run": "2026-09-24 00:10:00"}, "2026-10-02")
    text = render(res) + render_md(res)
    if res["ads_flagged"] != 3:
        fails.append("expected 3 flagged ads (service ad is info only, brand ad clean), got %d" % res["ads_flagged"])
    if "\u2014" in text or "\u2013" in text:
        fails.append("em or en dash in output")
    if re.search(r"\bcompliant\b|\bviolation\b|\bis legal\b|\bcleared\b", text, re.I):
        fails.append("output claims clearance or a violation")
    fed = scan(ads, "ATLAS", {}, "2026-10-02")
    if any("CA:" in r["cites"] or "CARS-" in r["cites"] for r in fed["rules"]):
        fails.append("ATLAS output should carry federal cites only")
    # file round trip: JSON dump (gdata.py sheet output) and CSV
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        pj = os.path.join(tmp, "dump.json")
        json.dump(SAMPLE, open(pj, "w"))
        pc = os.path.join(tmp, "dump.csv")
        csv.writer(open(pc, "w", newline="")).writerows(SAMPLE)
        if len(rows_to_ads(read_file(pj))) != 5 or len(rows_to_ads(read_file(pc))) != 5:
            fails.append("file readers did not return 5 ads")
    if fails:
        print("SELFTEST FAIL (%d):\n- %s" % (len(fails), "\n- ".join(fails)))
        return 1
    print("SELFTEST OK: 26 rule expectations, flagged count, wording, federal-only mode, JSON and CSV readers")
    print(render(res))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", help="NOI, MCP, ATLAS, or ALL (stores with an export Sheet)")
    ap.add_argument("--file", help="local dump of the ad_text_7d tab (gdata.py sheet JSON, CSV, or TSV)")
    ap.add_argument("--out", help="folder for ad_text_{STORE}.json and .md")
    ap.add_argument("--date", help="shift date YYYY-MM-DD (default today)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(selftest())
    if not args.store:
        ap.error("--store is required")
    ids = sheet_ids()
    stores = sorted(ids) if args.store.upper() == "ALL" else [args.store.upper()]
    if args.file and len(stores) > 1:
        ap.error("--file takes one --store")
    codes = [run_store(s, args, ids) for s in stores]
    sys.exit(max(codes) if codes else 0)


if __name__ == "__main__":
    main()
