#!/usr/bin/env python3
"""Numbers gate for dealership-forecast-tool deliverables (DigitalCLIQ).

Standard library plus openpyxl only, so it runs on the Mac's Python 3.9 and in
Cowork. It never writes to the workbook. The only file it can write is the
<deliverable>.forecast.json sidecar, and only with --write-sidecar on a pass.

Subcommands
  facts       FACTS.json        Pre-build checks on the facts dict. Run before
                                the workbook is written. Exit 1 lists failures.
  tiers       FACTS.json        Print the Tier, Rating, Note, row order and CUT
                                order the Vendor ROI and Reallocation tabs must
                                show (rules in references/roi_methodology.md).
  elasticity  FACTS.json        Log-log spend-to-leads regression over the
                                facts history: slope, r, p, SE, n, 95% CI and
                                the label the workbook must use.
  audit       FACTS.json        Model Confidence Check and sanity rows. Exit 3
                                when Drew must confirm before the build.
  check       WORKBOOK.xlsx [--facts FACTS.json] [--write-sidecar]
                                After recalc: recompute every formula, check
                                TOTAL rows (text or date month labels, any
                                case), the History {YEAR} TOTAL rows (against
                                facts.history_totals with --facts), tiers,
                                sort order, baselines, labels, '(net)', em
                                dashes and required tabs.

Exit codes: 0 pass, 1 failures found, 2 usage error or unreadable input,
3 Drew's confirmation needed (audit only).

Tier cut-offs ($500 / $1,000 / $1,500 cost per sale) and the $1,500 zero-sale
review floor are DigitalCLIQ planning assumptions, not published benchmarks.
"""

from __future__ import print_function

import argparse
import datetime
import json
import math
import os
import re
import sys
from decimal import Decimal, ROUND_HALF_UP

EM_DASH = "\u2014"

# ------------------------------------------------------------------ tier rules

TIER_CUTS = ((500, "TIER 1", "STAR"), (1000, "TIER 2", "GOOD"), (1500, "TIER 3", "AVG"))
REVIEW_FLOOR = 1500  # a paid line at or above this with leads and 0 sales is TIER 4
RATING_FOR = {"TIER 1": "STAR", "TIER 2": "GOOD", "TIER 3": "AVG", "TIER 4": "REVIEW",
              "UNMEASURED": "UNMEASURED", "NO SALES YET": "NO SALES YET",
              "NO SPEND": "NO SPEND"}
ARTIFACT_RE = re.compile(r"credit|walk|referral|repeat|dms|service|showroom", re.I)


def tier_rule(spend, leads, sales, table_has_cost=True):
    """Return (tier, rating, note, cps). cps is None when no cost per sale exists.

    tier is None when the table carries no cost at all (close-rate-only mode is
    not graded here).
    """
    spend = float(spend or 0)
    leads = float(leads or 0)
    sales = float(sales or 0)
    if spend <= 0:
        if table_has_cost:
            return "NO SPEND", "NO SPEND", "", None
        return None, None, "no spend in table", None
    if leads <= 0:
        return "UNMEASURED", "UNMEASURED", "No CRM leads", None
    if sales <= 0:
        if spend >= REVIEW_FLOOR:
            return "TIER 4", "REVIEW", "0 sales on ${:,.0f}".format(spend), None
        return "NO SALES YET", "NO SALES YET", "", None
    cps = spend / sales
    for cut, tier, rating in TIER_CUTS:
        if cps < cut:
            return tier, rating, "", cps
    return "TIER 4", "REVIEW", "", cps


_TIER_KEY_RE = re.compile(r"TIER\s*([1-4])|UNMEASURED|NO SALES YET|NO SPEND", re.I)
_RATING_KEY_RE = re.compile(r"STAR|GOOD|AVG|REVIEW|UNMEASURED|NO SALES YET|NO SPEND", re.I)


def norm_tier(v):
    if v is None:
        return None
    m = _TIER_KEY_RE.search(str(v))
    if not m:
        return None
    if m.group(1):
        return "TIER " + m.group(1)
    return m.group(0).upper()


def norm_rating(v):
    if v is None:
        return None
    m = _RATING_KEY_RE.search(str(v))
    return m.group(0).upper() if m else None


def order_ok(cps_list):
    """Numeric cost-per-sale rows ascending, then every row without one."""
    seen_blank = False
    last = None
    for c in cps_list:
        if c is None:
            seen_blank = True
            continue
        if seen_blank:
            return False
        if last is not None and c < last - 1e-9:
            return False
        last = c
    return True


def cut_order(vendors):
    """Rows for the CUT list, in the order they must be listed."""
    zero_sale, tier4, unmeasured = [], [], []
    for v in vendors:
        tier, _r, _n, cps = tier_rule(v.get("spend"), v.get("leads"), v.get("sales"))
        if tier == "TIER 4" and cps is None:
            zero_sale.append(v)
        elif tier == "TIER 4":
            tier4.append((cps, v))
        elif tier == "UNMEASURED":
            unmeasured.append(v)
    zero_sale.sort(key=lambda v: -float(v.get("spend") or 0))
    tier4.sort(key=lambda t: -t[0])
    unmeasured.sort(key=lambda v: -float(v.get("spend") or 0))
    return zero_sale + [v for _c, v in tier4] + unmeasured


# ----------------------------------------------------------------- statistics

def _betacf(a, b, x):
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < 1e-300:
        d = 1e-300
    d = 1.0 / d
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1e-300 if abs(d) < 1e-300 else d
        c = 1.0 + aa / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1e-300 if abs(d) < 1e-300 else d
        c = 1.0 + aa / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < 3e-14:
            break
    return h


def _betai(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lb = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    bt = math.exp(lb + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def t_cdf(t, df):
    x = df / (df + t * t)
    tail = 0.5 * _betai(df / 2.0, 0.5, x)
    return 1.0 - tail if t >= 0 else tail


def t_ppf(q, df):
    lo, hi = -200.0, 200.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if t_cdf(mid, df) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def ols(xs, ys):
    n = len(xs)
    if n < 3:
        raise ValueError("need at least 3 points")
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0:
        raise ValueError("spend never changes, slope undefined")
    slope = sxy / sxx
    intercept = my - slope * mx
    r = sxy / math.sqrt(sxx * syy) if syy > 0 else 0.0
    df = n - 2
    rss = max(syy - slope * sxy, 0.0)
    se = math.sqrt(rss / df / sxx) if df > 0 else float("nan")
    if se > 0:
        t = slope / se
        p = 2.0 * (1.0 - t_cdf(abs(t), df))
    else:
        p = 0.0
    tc = t_ppf(0.975, df)
    return {"slope": slope, "intercept": intercept, "r": r, "p": p, "se": se,
            "n": n, "ci95": [slope - tc * se, slope + tc * se]}


def elasticity_label(p):
    return "Estimated" if p < 0.05 else "Estimated, not statistically significant"


def elasticity_from_history(history):
    xs, ys = [], []
    for row in history:
        s, l = row.get("spend"), row.get("leads")
        if s and l and s > 0 and l > 0:
            xs.append(math.log(s))
            ys.append(math.log(l))
    res = ols(xs, ys)
    res["label"] = elasticity_label(res["p"])
    return res


# ------------------------------------------------------------------ utilities

# Honest disclaimers ("not measured", "no sales elasticity", "not a confidence
# interval") are removed before the label patterns run. The up-to-3 words between
# the negator and the keyword never cross sentence or clause punctuation: a '.'
# counts only inside a word or number ("12.5%"), so "Weights not tuned. 80% CI"
# keeps its "80% CI" claim.
NEGATED_RE = re.compile(
    r"\b(?:not|no|never|isn't|is\s+not|rather\s+than|instead\s+of)\s+(?:an?\s+|the\s+|any\s+)?"
    r"(?:(?:[\w%+/-]|\.(?=\w))+\s+){0,3}?(?:confidence\s+interval|statistical\s+interval|interval|measured|"
    r"sales\s+elasticity|elasticity\s+\(sales\)|CI|NADA(?:\s+(?:index|seasonal|data))?)\b", re.I)


def strip_negated(text):
    return NEGATED_RE.sub(" ", text or "")


def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def close(a, b, abs_tol=0.5, rel_tol=0.0):
    if a is None or b is None:
        return False
    return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b)))


def fmt(v):
    if isinstance(v, float) and v.is_integer():
        return "{:,.0f}".format(v)
    if isinstance(v, float):
        return "{:,.4g}".format(v)
    return repr(v)


class Report(object):
    def __init__(self):
        self.fails, self.warns, self.infos = [], [], []

    def fail(self, msg):
        self.fails.append(msg)

    def warn(self, msg):
        self.warns.append(msg)

    def info(self, msg):
        self.infos.append(msg)

    def emit(self, title):
        print(title)
        for m in self.infos:
            print("  INFO  " + m)
        for m in self.warns:
            print("  WARN  " + m, file=sys.stderr)
        for m in self.fails:
            print("  FAIL  " + m)
        status = "FAILED" if self.fails else "PASSED"
        print("RESULT: {} ({} fail, {} warn)".format(status, len(self.fails), len(self.warns)))
        return 1 if self.fails else 0


def load_facts(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (IOError, OSError, ValueError) as exc:
        print("cannot read facts file {}: {}".format(path, exc), file=sys.stderr)
        sys.exit(2)


def _year_of(month):
    return str(month)[:4]


def history_by_year(history):
    out = {}
    for row in history:
        y = _year_of(row.get("month", ""))
        out.setdefault(y, []).append(row)
    return out


# ---------------------------------------------------------------- facts check

REQUIRED_DEFS = ("crm", "report_name", "lead_definition_column", "close_rate_basis", "data_window")
MONTH_RE = re.compile(r"^(?:19|20)\d{2}-(?:0[1-9]|1[0-2])$")


def check_facts(f, rep):
    client = f.get("client") or {}
    for k in ("code", "name"):
        if not client.get(k):
            rep.fail("facts.client.{} is empty".format(k))
    defs = f.get("definitions") or {}
    for k in REQUIRED_DEFS:
        if not defs.get(k):
            rep.fail("facts.definitions.{} is empty (the lead definition must be recorded)".format(k))
    if "excluded_sources" not in defs:
        rep.fail("facts.definitions.excluded_sources is missing (use [] when nothing is excluded)")
    win = defs.get("data_window") or {}
    if isinstance(win, dict) and not (win.get("start") and win.get("end")):
        rep.fail("facts.definitions.data_window needs start and end")

    history = f.get("history") or []
    if not history:
        rep.fail("facts.history is empty")

    # 1. every subtotal equals the sum of its rows
    totals = f.get("history_totals") or {}
    by_year = history_by_year(history)
    for year, tot in sorted(totals.items()):
        rows = by_year.get(str(year), [])
        if not rows:
            rep.fail("history_totals[{}] has no monthly rows".format(year))
            continue
        for key, val in sorted(tot.items()):
            s = sum(float(r.get(key) or 0) for r in rows)
            if not close(s, _num(val), 0.5):
                rep.fail("history_totals[{}].{} = {} but its {} monthly rows sum to {}".format(
                    year, key, fmt(_num(val)), len(rows), fmt(s)))
    for sub in f.get("subtotals") or []:
        parts = sub.get("parts") or []
        for key, val in sorted((sub.get("total") or {}).items()):
            s = sum(float(p.get(key) or 0) for p in parts)
            if not close(s, _num(val), 0.5):
                rep.fail("subtotal '{}'.{} = {} but its rows sum to {}".format(
                    sub.get("label", "?"), key, fmt(_num(val)), fmt(s)))

    # 2. tiers, ratings and sort order
    vendors = f.get("vendors") or []
    has_cost = any(float(v.get("spend") or 0) > 0 for v in vendors)
    cps_seq = []
    for v in vendors:
        tier, rating, note, cps = tier_rule(v.get("spend"), v.get("leads"), v.get("sales"), has_cost)
        cps_seq.append(cps)
        if tier is None:
            continue
        if norm_tier(v.get("tier")) != tier:
            rep.fail("vendor '{}' tier {!r}, rule says {} (spend {}, leads {}, sales {})".format(
                v.get("vendor"), v.get("tier"), tier, fmt(float(v.get("spend") or 0)),
                fmt(float(v.get("leads") or 0)), fmt(float(v.get("sales") or 0))))
        if v.get("rating") is not None and norm_rating(v.get("rating")) != rating:
            rep.fail("vendor '{}' rating {!r}, rule says {}".format(v.get("vendor"), v.get("rating"), rating))
    if vendors and not has_cost:
        rep.warn("no vendor carries spend; cost-per-sale tiers not applied (close-rate-only table)")
    if vendors and has_cost and not order_ok(cps_seq):
        rep.fail("vendors are not sorted by cost per sale (ascending, rows without one last)")

    # 3. excluded sources never in included rows
    excluded = set(s.strip().lower() for s in defs.get("excluded_sources") or [])
    for s in f.get("sources") or []:
        if s.get("included") and str(s.get("name", "")).strip().lower() in excluded:
            rep.fail("source '{}' is excluded in definitions but marked included".format(s.get("name")))
    for v in vendors:
        for s in v.get("sources") or []:
            if str(s).strip().lower() in excluded:
                rep.fail("excluded source '{}' is rolled into vendor '{}'".format(s, v.get("vendor")))

    # 4. high-close sources that look operational
    for s in f.get("sources") or []:
        if not s.get("included"):
            continue
        leads = float(s.get("leads") or 0)
        good = leads - float(s.get("dups") or 0) - float(s.get("invalid") or 0)
        denom = good if good > 0 else leads
        if denom <= 0:
            continue
        cr = float(s.get("sales") or 0) / denom
        name = str(s.get("name", ""))
        if cr > 0.20 and ARTIFACT_RE.search(name) and not s.get("confirmed_by_drew"):
            rep.fail("source '{}' closes at {:.1%} and its name looks operational; confirm with Drew "
                     "(set confirmed_by_drew) or exclude it".format(name, cr))

    # 5. pooled CTR and CPC
    ads = f.get("ads")
    if ads:
        months = ads.get("monthly") or []
        clicks = sum(float(m.get("clicks") or 0) for m in months)
        impr = sum(float(m.get("impressions") or 0) for m in months)
        cost = sum(float(m.get("cost") or 0) for m in months)
        if ads.get("ctr") is not None and impr > 0 and not close(float(ads["ctr"]), clicks / impr, 1e-6, 0.005):
            rep.fail("ads.ctr {} is not pooled total clicks / total impressions ({:.4%})".format(ads["ctr"], clicks / impr))
        if ads.get("cpc") is not None and clicks > 0 and not close(float(ads["cpc"]), cost / clicks, 0.005, 0.005):
            rep.fail("ads.cpc {} is not pooled total cost / total clicks ({:.2f})".format(ads["cpc"], cost / clicks))

    # 6. '(net)' only with a co-op row
    labels = f.get("labels") or {}
    coop = f.get("coop") or {}
    if labels.get("net_used") and not coop.get("present"):
        rep.fail("labels.net_used is true but no co-op row exists; spend is gross, drop '(net)'")

    # 7. models, ensemble and title
    models = f.get("models") or {}
    ran = list(models.get("ran") or [])
    fc = f.get("forecast") or {}
    base = [float(x) for x in fc.get("baseline") or []]
    if not base:
        rep.fail("facts.forecast.baseline is empty")
    fmonths = list(fc.get("months") or [])
    if len(fmonths) != len(base):
        rep.fail("facts.forecast.months has {} entries for {} baseline month(s); list every forecast month "
                 "as YYYY-MM".format(len(fmonths), len(base)))
    bad_months = [str(m) for m in fmonths if not MONTH_RE.match(str(m))]
    if bad_months:
        rep.fail("facts.forecast.months not in YYYY-MM form: {}".format(", ".join(bad_months[:5])))
    if not ran:
        rep.fail("facts.models.ran is empty: list only the models that produced numbers")
    weights = models.get("weights") or {}
    monthly = models.get("monthly") or {}
    if ran:
        wsum = sum(float(weights.get(m, 0)) for m in ran)
        if not close(wsum, 1.0, 0.01):
            rep.fail("weights of the models that ran sum to {:.3f}, not 1".format(wsum))
        extra = [m for m in weights if m not in ran and float(weights.get(m) or 0) > 0]
        if extra:
            rep.fail("weights given to models that did not run: {}".format(", ".join(extra)))
        missing = [m for m in ran if len(monthly.get(m) or []) < len(base)]
        if missing:
            rep.fail("per-model monthly values missing for: {}".format(", ".join(missing)))
        elif base:
            for i, b in enumerate(base):
                ens = sum(float(weights.get(m, 0)) * float(monthly[m][i]) for m in ran)
                if not close(ens, b, 1.0, 0.005):
                    rep.fail("forecast month {} baseline {} but weighted models give {:.1f}".format(
                        i + 1, fmt(b), ens))
                    break
    title = str(labels.get("forecast_title") or "")
    if re.search(r"3[- ]model", title, re.I) and len(ran) != 3:
        rep.fail("forecast title says 3-model but {} model(s) ran: {}".format(len(ran), ", ".join(ran) or "none"))
    if re.search(r"NADA", strip_negated(title + " " + str(labels.get("forecast_subtitle") or ""))):
        rep.fail("forecast title or subtitle names NADA; the seasonal indices are a DigitalCLIQ estimate")

    # 8. planning range
    method = str(fc.get("interval_method") or "")
    if not method:
        rep.fail("facts.forecast.interval_method is empty")
    if re.search(r"confidence|\bCI\b", strip_negated(method), re.I) and re.search(r"fixed", method, re.I):
        rep.fail("interval_method calls a fixed range a confidence interval")
    low, high = fc.get("low") or [], fc.get("high") or []
    if len(low) != len(base) or len(high) != len(base):
        rep.fail("forecast low/high must have one value per forecast month")
    elif re.search(r"fixed", method, re.I):
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", method)
        hw = float(m.group(1)) / 100 if m else 0.12
        for i, b in enumerate(base):
            if not (close(float(low[i]), b * (1 - hw), 1.0) and close(float(high[i]), b * (1 + hw), 1.0)):
                rep.fail("month {} planning range {}..{} is not baseline +/-{:.0%}".format(
                    i + 1, fmt(float(low[i])), fmt(float(high[i])), hw))
                break

    # 9. elasticity recomputed from history
    el = (f.get("elasticity") or {})
    lead_el = el.get("leads") or {}
    if history:
        try:
            got = elasticity_from_history(history)
        except ValueError as exc:
            rep.warn("elasticity not recomputable: {}".format(exc))
            got = None
        if got is not None:
            if lead_el.get("slope") is None or not close(float(lead_el["slope"]), got["slope"], 0.005):
                rep.fail("elasticity slope {} but history gives {:.3f}".format(lead_el.get("slope"), got["slope"]))
            if lead_el.get("p") is None or not close(float(lead_el["p"]), got["p"], 0.02):
                rep.fail("elasticity p {} but history gives {:.3f}".format(lead_el.get("p"), got["p"]))
            for k in ("r", "se", "n", "ci95"):
                if lead_el.get(k) in (None, "", []):
                    rep.fail("elasticity.leads.{} missing (record slope, r, p, se, n, ci95)".format(k))
            want = got["label"]
            if str(el.get("label") or "") != want:
                rep.fail("elasticity label {!r}, must be {!r} (p = {:.3f})".format(el.get("label"), want, got["p"]))
    if re.search(r"measured", strip_negated(json.dumps(el)), re.I):
        rep.fail("elasticity is labelled 'measured'; it is an estimate")

    # 10. scenarios: one baseline, sales from close rate
    sc = f.get("scenarios") or {}
    es, sp = sc.get("executive_summary") or {}, sc.get("scenario_planner") or {}
    for key in ("baseline", "+25%", "-15%"):
        a, b = es.get(key) or {}, sp.get(key) or {}
        for metric in ("leads", "sales"):
            if a.get(metric) is None or b.get(metric) is None:
                rep.fail("scenarios.{}.{} missing on Executive Summary or Scenario Planner".format(key, metric))
            elif not close(float(a[metric]), float(b[metric]), 1.0, 0.001):
                rep.fail("{} {}: Executive Summary {} vs Scenario Planner {} (different baselines)".format(
                    key, metric, fmt(float(a[metric])), fmt(float(b[metric]))))
    bl = f.get("baseline") or {}
    if bl.get("leads") and bl.get("sales") is not None:
        ratio = float(bl["sales"]) / float(bl["leads"])
        for key in ("baseline", "+25%", "-15%"):
            row = sp.get(key) or {}
            if row.get("leads") is not None and row.get("sales") is not None:
                want = float(row["leads"]) * ratio
                if not close(float(row["sales"]), want, 1.0):
                    rep.fail("{} projected sales {} but leads x baseline close rate gives {:.0f}".format(
                        key, fmt(float(row["sales"])), want))
    if base and bl.get("leads") is not None and not close(sum(base), float(bl["leads"]), 6.0, 0.005):
        rep.fail("baseline.leads {} does not match the forecast total {}".format(fmt(float(bl["leads"])), fmt(sum(base))))

    # 11. model audit confirmations
    prompts = audit_prompts(f, Report())
    conf = f.get("confirmations") or {}
    for kind, text in prompts:
        if not conf.get(kind):
            rep.fail("model audit needs Drew's yes ({}): {}".format(kind, text))

    # 12. reviewer manifest
    man = f.get("manifest")
    if not isinstance(man, list) or not man:
        rep.fail("facts.manifest is empty: list every client-facing figure as {value, label, source}")
    else:
        bad = [i for i, m in enumerate(man) if not isinstance(m, dict) or not m.get("source") or "value" not in m]
        if bad:
            rep.fail("manifest entries without value or source at index {}".format(", ".join(map(str, bad[:10]))))
    return rep


# ---------------------------------------------------------------- model audit

def audit_prompts(f, rep):
    """Return [(kind, prompt)] for anything Drew must confirm. Fills rep with the table."""
    prompts = []
    fc = f.get("forecast") or {}
    base = [float(x) for x in fc.get("baseline") or []]
    months = list(fc.get("months") or [])
    history = f.get("history") or []
    if not base:
        rep.fail("no forecast baseline to audit")
        return prompts
    ens = sum(base)
    rep.info("Ensemble total over {} forecast month(s): {:,.0f}".format(len(base), ens))

    hist = {}
    for row in history:
        hist[str(row.get("month"))] = float(row.get("leads") or 0)
    cal = [m[5:7] for m in months] if months and all(len(str(m)) >= 7 for m in months) else None

    def same_months(year):
        if not cal:
            return None
        vals = [hist.get("{}-{}".format(year, mm)) for mm in cal]
        if any(v is None for v in vals):
            return None
        return sum(vals)

    years = sorted(set(_year_of(m) for m in hist), reverse=True)
    last_y = next((y for y in years if same_months(y) is not None), None)
    last_tot = same_months(last_y) if last_y else None
    prior_y = next((y for y in years if last_y and y < last_y and same_months(y) is not None), None)
    prior_tot = same_months(prior_y) if prior_y else None

    change = None
    if last_tot:
        change = ens / last_tot - 1
        rep.info("Same months, {} actual: {:,.0f}  ensemble {:+.1%}".format(last_y, last_tot, change))
        if abs(change) > 0.10:
            prompts.append(("sanity", "forecast is {:+.1%} vs {} actual ({:,.0f} vs {:,.0f})".format(
                change, last_y, ens, last_tot)))
    else:
        rep.warn("no complete prior year for the forecast months; last-year sanity row skipped")
    if hist:
        flat = sum(hist.values()) / len(hist) * len(base)
        fchange = ens / flat - 1 if flat else 0
        rep.info("Flat average ({} months of history) x {}: {:,.0f}  ensemble {:+.1%}".format(
            len(hist), len(base), flat, fchange))
        if abs(fchange) > 0.10:
            prompts.append(("sanity", "forecast is {:+.1%} vs the flat average ({:,.0f} vs {:,.0f})".format(
                fchange, ens, flat)))
    if last_tot and prior_tot:
        yoy = last_tot / prior_tot - 1
        rep.info("Last actual change, {} vs {}: {:+.1%}".format(last_y, prior_y, yoy))
        if change is not None and abs(change) > 0.05 and (yoy > 0) != (change > 0) and abs(yoy) > 0.005:
            prompts.append(("sanity", "forecast reverses direction: {:+.1%} after a {:+.1%} year ({:,.0f} vs {:,.0f} in {})".format(
                change, yoy, ens, last_tot, last_y)))

    models = f.get("models") or {}
    monthly = models.get("monthly") or {}
    ran = list(models.get("ran") or monthly.keys())
    if not monthly:
        rep.warn("no per-model monthly values in facts; Model Confidence Check skipped")
    for m in ran:
        vals = monthly.get(m)
        if not vals:
            continue
        tot = sum(float(x) for x in vals[:len(base)])
        dev = tot / ens - 1 if ens else 0
        rep.info("Model {:<16} {:,.0f}  {:+.1%} vs ensemble".format(m, tot, dev))
        if abs(dev) > 0.20:
            prompts.append(("divergence", "{} is forecasting {:.0%} {} the ensemble. This usually means it "
                            "detected a trend the other models do not see. Options: (a) accept current "
                            "weights, (b) adjust weights, (c) investigate the driver.".format(
                                m, abs(dev), "above" if dev > 0 else "below")))
    # de-duplicate sanity prompts into one question
    out, sanity = [], [p for k, p in prompts if k == "sanity"]
    if sanity:
        out.append(("sanity", "; ".join(sanity) + ". Show Drew the sanity rows and get a yes before building."))
    out.extend((k, p) for k, p in prompts if k == "divergence")
    return out


# ---------------------------------------------------------- formula evaluator

class XlError(object):
    def __init__(self, code):
        self.code = code

    def __eq__(self, other):
        return isinstance(other, XlError) and other.code == self.code

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return self.code


class Unsupported(Exception):
    pass


ERROR_CODES = ("#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#N/A", "#NUM!", "#NULL!")

_TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<str>"(?:[^"]|"")*")
  | (?P<func>[A-Za-z_][A-Za-z0-9_.]*(?=\s*\())
  | (?P<ref>(?:(?:'(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_.]*)!)?\$?[A-Za-z]{1,3}\$?\d+(?::\$?[A-Za-z]{1,3}\$?\d+)?)
  | (?P<num>(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)
  | (?P<bool>TRUE|FALSE)
  | (?P<err>\#DIV/0!|\#VALUE!|\#REF!|\#NAME\?|\#N/A|\#NUM!|\#NULL!)
  | (?P<op><>|<=|>=|[-+*/^&=<>%(),;])
""", re.X)


def tokenize(src):
    pos, out = 0, []
    while pos < len(src):
        m = _TOKEN_RE.match(src, pos)
        if not m:
            raise Unsupported("cannot parse at {!r}".format(src[pos:pos + 12]))
        pos = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        out.append((kind, m.group(kind)))
    return out


def col_to_idx(col):
    n = 0
    for ch in col.upper():
        n = n * 26 + (ord(ch) - 64)
    return n


def idx_to_col(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


_CELL_RE = re.compile(r"\$?([A-Za-z]{1,3})\$?(\d+)")


def split_ref(ref, default_sheet):
    sheet = default_sheet
    if "!" in ref:
        sheet, ref = ref.rsplit("!", 1)
        if sheet.startswith("'"):
            sheet = sheet[1:-1].replace("''", "'")
    parts = ref.split(":")
    cells = []
    for p in parts:
        m = _CELL_RE.fullmatch(p)
        cells.append((col_to_idx(m.group(1)), int(m.group(2))))
    return sheet, cells


class Range(object):
    def __init__(self, rows):
        self.rows = rows  # list of lists

    def flat(self):
        for r in self.rows:
            for v in r:
                yield v


class Parser(object):
    def __init__(self, tokens):
        self.t = tokens
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self, val=None):
        tok = self.peek()
        if val is not None and tok[1] != val:
            raise Unsupported("expected {!r}, got {!r}".format(val, tok[1]))
        self.i += 1
        return tok

    def parse(self):
        node = self.comparison()
        if self.i != len(self.t):
            raise Unsupported("trailing tokens")
        return node

    def comparison(self):
        node = self.concat()
        while self.peek()[1] in ("=", "<>", "<", ">", "<=", ">="):
            op = self.take()[1]
            node = ("cmp", op, node, self.concat())
        return node

    def concat(self):
        node = self.additive()
        while self.peek()[1] == "&":
            self.take()
            node = ("cat", node, self.additive())
        return node

    def additive(self):
        node = self.term()
        while self.peek()[1] in ("+", "-"):
            op = self.take()[1]
            node = ("bin", op, node, self.term())
        return node

    def term(self):
        node = self.power()
        while self.peek()[1] in ("*", "/"):
            op = self.take()[1]
            node = ("bin", op, node, self.power())
        return node

    def power(self):
        node = self.unary()
        while self.peek()[1] == "^":
            self.take()
            node = ("bin", "^", node, self.unary())
        return node

    def unary(self):
        if self.peek()[1] in ("-", "+"):
            op = self.take()[1]
            node = self.unary()
            return ("neg", node) if op == "-" else node
        node = self.primary()
        while self.peek()[1] == "%":
            self.take()
            node = ("bin", "/", node, ("num", 100.0))
        return node

    def primary(self):
        kind, val = self.peek()
        if kind == "num":
            self.take()
            return ("num", float(val))
        if kind == "str":
            self.take()
            return ("str", val[1:-1].replace('""', '"'))
        if kind == "bool":
            self.take()
            return ("bool", val == "TRUE")
        if kind == "err":
            self.take()
            return ("err", val)
        if kind == "ref":
            self.take()
            return ("ref", val)
        if kind == "func":
            self.take()
            self.take("(")
            args = []
            if self.peek()[1] != ")":
                while True:
                    if self.peek()[1] in (",", ";", ")"):
                        args.append(("blank",))
                    else:
                        args.append(self.comparison())
                    if self.peek()[1] in (",", ";"):
                        self.take()
                        continue
                    break
            self.take(")")
            return ("func", val.upper(), args)
        if val == "(":
            self.take()
            node = self.comparison()
            self.take(")")
            return node
        raise Unsupported("unexpected token {!r}".format(val))


def _round_half_up(x, nd):
    q = Decimal(1).scaleb(-int(nd))
    d = Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP)
    return float(d)


class Evaluator(object):
    def __init__(self, wb):
        self.wb = wb
        self.cache = {}
        self.stack = set()
        self.titles = {ws.title.lower(): ws.title for ws in wb.worksheets}

    def raw(self, sheet, col, row):
        real = self.titles.get(sheet.lower())
        if real is None:
            return XlError("#REF!")
        return self.wb[real].cell(row=row, column=col).value

    def value(self, sheet, col, row):
        key = (sheet.lower(), col, row)
        if key in self.cache:
            return self.cache[key]
        v = self.raw(sheet, col, row)
        if isinstance(v, str) and v.startswith("="):
            if key in self.stack:
                raise Unsupported("circular reference at {}!{}{}".format(sheet, idx_to_col(col), row))
            self.stack.add(key)
            try:
                v = self.formula(v, sheet)
            finally:
                self.stack.discard(key)
        elif v is not None and not isinstance(v, (int, float, str, bool)):
            if hasattr(v, "text"):  # ArrayFormula or similar
                raise Unsupported("array formula")
            v = str(v)
        if isinstance(v, int) and not isinstance(v, bool):
            v = float(v)
        self.cache[key] = v
        return v

    def formula(self, text, sheet):
        node = Parser(tokenize(text[1:])).parse()
        v = self.ev(node, sheet)
        if isinstance(v, Range):
            vals = list(v.flat())
            v = vals[0] if len(vals) == 1 else XlError("#VALUE!")
        return v

    # ---- coercion helpers
    def to_num(self, v):
        if isinstance(v, XlError):
            return v
        if v is None:
            return 0.0
        if isinstance(v, bool):
            return 1.0 if v else 0.0
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v.replace(",", ""))
            except ValueError:
                return XlError("#VALUE!")
        if isinstance(v, Range):
            vals = list(v.flat())
            return self.to_num(vals[0]) if len(vals) == 1 else XlError("#VALUE!")
        return XlError("#VALUE!")

    def to_bool(self, v):
        if isinstance(v, XlError):
            return v
        if isinstance(v, str):
            if v.upper() in ("TRUE", "FALSE"):
                return v.upper() == "TRUE"
            return XlError("#VALUE!")
        n = self.to_num(v)
        return n if isinstance(n, XlError) else n != 0

    def to_str(self, v):
        if isinstance(v, XlError):
            return v
        if v is None:
            return ""
        if isinstance(v, bool):
            return "TRUE" if v else "FALSE"
        if isinstance(v, float):
            return str(int(v)) if v.is_integer() else repr(v)
        return str(v)

    def scalar(self, v):
        if isinstance(v, Range):
            vals = list(v.flat())
            return vals[0] if len(vals) == 1 else XlError("#VALUE!")
        return v

    # ---- evaluation
    def ev(self, node, sheet):
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind == "str":
            return node[1]
        if kind == "bool":
            return node[1]
        if kind == "err":
            return XlError(node[1])
        if kind == "blank":
            return None
        if kind == "ref":
            sh, cells = split_ref(node[1], sheet)
            if len(cells) == 1:
                c, r = cells[0]
                return self.value(sh, c, r)
            (c1, r1), (c2, r2) = cells
            rows = []
            for r in range(min(r1, r2), max(r1, r2) + 1):
                rows.append([self.value(sh, c, r) for c in range(min(c1, c2), max(c1, c2) + 1)])
            return Range(rows)
        if kind == "neg":
            v = self.to_num(self.scalar(self.ev(node[1], sheet)))
            return v if isinstance(v, XlError) else -v
        if kind == "bin":
            op = node[1]
            a = self.to_num(self.scalar(self.ev(node[2], sheet)))
            b = self.to_num(self.scalar(self.ev(node[3], sheet)))
            for x in (a, b):
                if isinstance(x, XlError):
                    return x
            if op == "+":
                return a + b
            if op == "-":
                return a - b
            if op == "*":
                return a * b
            if op == "/":
                return XlError("#DIV/0!") if b == 0 else a / b
            if op == "^":
                try:
                    return float(a ** b)
                except (OverflowError, ValueError, ZeroDivisionError):
                    return XlError("#NUM!")
        if kind == "cat":
            a = self.to_str(self.scalar(self.ev(node[1], sheet)))
            b = self.to_str(self.scalar(self.ev(node[2], sheet)))
            for x in (a, b):
                if isinstance(x, XlError):
                    return x
            return a + b
        if kind == "cmp":
            a = self.scalar(self.ev(node[2], sheet))
            b = self.scalar(self.ev(node[3], sheet))
            for x in (a, b):
                if isinstance(x, XlError):
                    return x
            return self.compare(node[1], a, b)
        if kind == "func":
            return self.call(node[1], node[2], sheet)
        raise Unsupported("node " + kind)

    @staticmethod
    def _rank(v):
        if v is None:
            return (0, 0.0)
        if isinstance(v, bool):
            return (2, 1.0 if v else 0.0)
        if isinstance(v, (int, float)):
            return (0, float(v))
        return (1, str(v).lower())

    def compare(self, op, a, b):
        if a is None and isinstance(b, str):
            a = ""
        if b is None and isinstance(a, str):
            b = ""
        ra, rb = self._rank(a), self._rank(b)
        if op == "=":
            return ra == rb
        if op == "<>":
            return ra != rb
        if op == "<":
            return ra < rb
        if op == ">":
            return ra > rb
        if op == "<=":
            return ra <= rb
        if op == ">=":
            return ra >= rb
        raise Unsupported(op)

    def _nums(self, args, sheet):
        out = []
        for a in args:
            v = self.ev(a, sheet)
            if isinstance(v, Range):
                for x in v.flat():
                    if isinstance(x, XlError):
                        return x
                    if isinstance(x, (int, float)) and not isinstance(x, bool):
                        out.append(float(x))
            else:
                n = self.to_num(v)
                if isinstance(n, XlError):
                    return n
                out.append(n)
        return out

    def _criteria(self, crit):
        if isinstance(crit, (int, float)) and not isinstance(crit, bool):
            return lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and float(x) == float(crit)
        s = str(crit)
        m = re.match(r"^(<>|<=|>=|=|<|>)?(.*)$", s)
        op, rhs = m.group(1) or "=", m.group(2)
        try:
            rv = float(rhs)
        except ValueError:
            rv = rhs
        def test(x):
            if x is None and rv == "" and op in ("=",):
                return True
            if isinstance(rv, float):
                if not isinstance(x, (int, float)) or isinstance(x, bool):
                    return op == "<>"
                return self.compare(op, float(x), rv)
            return self.compare(op, "" if x is None else str(x).lower(), str(rv).lower())
        return test

    def call(self, name, args, sheet):
        if name == "IF":
            cond = self.to_bool(self.scalar(self.ev(args[0], sheet)))
            if isinstance(cond, XlError):
                return cond
            if cond:
                return self.scalar(self.ev(args[1], sheet)) if len(args) > 1 else True
            return self.scalar(self.ev(args[2], sheet)) if len(args) > 2 else False
        if name == "IFERROR":
            v = self.scalar(self.ev(args[0], sheet))
            return self.scalar(self.ev(args[1], sheet)) if isinstance(v, XlError) else v
        if name in ("SUM", "AVERAGE", "MIN", "MAX", "COUNT"):
            nums = self._nums(args, sheet)
            if isinstance(nums, XlError):
                return nums
            if name == "SUM":
                return float(sum(nums))
            if name == "COUNT":
                return float(len(nums))
            if not nums:
                return XlError("#DIV/0!") if name == "AVERAGE" else 0.0
            return {"AVERAGE": sum(nums) / len(nums), "MIN": min(nums), "MAX": max(nums)}[name]
        if name in ("ROUND", "ROUNDUP", "ROUNDDOWN"):
            x = self.to_num(self.scalar(self.ev(args[0], sheet)))
            nd = self.to_num(self.scalar(self.ev(args[1], sheet))) if len(args) > 1 else 0.0
            for v in (x, nd):
                if isinstance(v, XlError):
                    return v
            if name == "ROUND":
                return _round_half_up(x, nd)
            f = 10 ** int(nd)
            if name == "ROUNDUP":
                return math.copysign(math.ceil(abs(x) * f - 1e-12) / f, x)
            return math.copysign(math.floor(abs(x) * f + 1e-12) / f, x)
        if name == "ABS":
            x = self.to_num(self.scalar(self.ev(args[0], sheet)))
            return x if isinstance(x, XlError) else abs(x)
        if name in ("AND", "OR"):
            vals = []
            for a in args:
                v = self.ev(a, sheet)
                for x in (v.flat() if isinstance(v, Range) else [v]):
                    b = self.to_bool(x)
                    if isinstance(b, XlError):
                        return b
                    vals.append(b)
            return all(vals) if name == "AND" else any(vals)
        if name == "NOT":
            b = self.to_bool(self.scalar(self.ev(args[0], sheet)))
            return b if isinstance(b, XlError) else (not b)
        if name == "ISNUMBER":
            v = self.scalar(self.ev(args[0], sheet))
            return isinstance(v, (int, float)) and not isinstance(v, bool)
        if name == "ISBLANK":
            return self.scalar(self.ev(args[0], sheet)) is None
        if name == "ISERROR":
            return isinstance(self.scalar(self.ev(args[0], sheet)), XlError)
        if name in ("COUNTIF", "SUMIF"):
            rng = self.ev(args[0], sheet)
            crit = self.scalar(self.ev(args[1], sheet))
            if not isinstance(rng, Range):
                rng = Range([[rng]])
            test = self._criteria(crit)
            if name == "COUNTIF":
                return float(sum(1 for x in rng.flat() if test(x)))
            srng = self.ev(args[2], sheet) if len(args) > 2 else rng
            if not isinstance(srng, Range):
                srng = Range([[srng]])
            total = 0.0
            for x, y in zip(rng.flat(), srng.flat()):
                if test(x) and isinstance(y, (int, float)) and not isinstance(y, bool):
                    total += float(y)
            return total
        if name == "COUNTA":
            n = 0
            for a in args:
                v = self.ev(a, sheet)
                n += sum(1 for x in (v.flat() if isinstance(v, Range) else [v]) if x not in (None, ""))
            return float(n)
        if name in ("CONCATENATE", "CONCAT"):
            parts = []
            for a in args:
                s = self.to_str(self.scalar(self.ev(a, sheet)))
                if isinstance(s, XlError):
                    return s
                parts.append(s)
            return "".join(parts)
        if name == "TEXT":
            x = self.scalar(self.ev(args[0], sheet))
            f = self.to_str(self.scalar(self.ev(args[1], sheet)))
            n = self.to_num(x)
            if isinstance(n, XlError):
                return n
            return _text_format(n, f)
        if name == "INDEX":
            rng = self.ev(args[0], sheet)
            r = int(self.to_num(self.scalar(self.ev(args[1], sheet))))
            c = int(self.to_num(self.scalar(self.ev(args[2], sheet)))) if len(args) > 2 else 1
            if not isinstance(rng, Range):
                return rng
            if len(rng.rows) == 1 and len(args) == 2:
                r, c = 1, r
            try:
                return rng.rows[r - 1][c - 1]
            except IndexError:
                return XlError("#REF!")
        if name == "MATCH":
            look = self.scalar(self.ev(args[0], sheet))
            rng = self.ev(args[1], sheet)
            mode = self.to_num(self.scalar(self.ev(args[2], sheet))) if len(args) > 2 else 1.0
            if mode != 0:
                raise Unsupported("MATCH without exact mode")
            for i, x in enumerate(rng.flat() if isinstance(rng, Range) else [rng]):
                if self.compare("=", x, look):
                    return float(i + 1)
            return XlError("#N/A")
        raise Unsupported("function " + name)


def _text_format(n, f):
    pct = f.endswith("%")
    val = n * 100 if pct else n
    core = f.rstrip("%")
    prefix = "$" if core.startswith("$") else ""
    core = core.lstrip("$")
    dec = len(core.split(".")[1]) if "." in core else 0
    comma = "," in core
    if not re.fullmatch(r"[#0,]*0(?:\.0+)?", core):
        raise Unsupported("TEXT format " + f)
    body = ("{:,.%df}" if comma else "{:.%df}") % dec
    s = body.format(abs(_round_half_up(val, dec)))
    sign = "-" if val < 0 else ""
    return sign + prefix + s + ("%" if pct else "")


def same(a, b):
    """Compare an evaluated value with a cached one."""
    if isinstance(b, str) and b in ERROR_CODES:
        b = XlError(b)
    if isinstance(a, XlError) or isinstance(b, XlError):
        return a == b
    if a in (None, "") and b in (None, ""):
        return True
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b) and type(a) == type(b)
    na, nb = _num(a), _num(b)
    if na is not None and nb is not None:
        return abs(na - nb) <= 1e-6 * max(1.0, abs(na), abs(nb))
    return str(a) == str(b)


# -------------------------------------------------------------- workbook check

REQUIRED_TABS = (
    ("Executive Summary", r"executive summary"),
    ("Monthly History", r"history"),
    ("Vendor ROI", r"vendor roi"),
    ("Forecast", r"forecast"),
    ("Scenario Planner", r"scenario"),
    ("Budget Detail", r"budget detail"),
    ("All Providers", r"all providers"),
    ("Reallocation Strategy", r"realloc"),
)
# Case-insensitive so a "2024 Total" row is still checked; the spec wants capitals
# and total_rows() warns when a TOTAL label is not in capitals. A trailing colon
# ("TOTAL:", "2025 TOTAL:") is still a TOTAL row.
TOTAL_LABEL_RE = re.compile(r"^(?:.*\s)?TOTALS?\s*:?$", re.I)
YEAR_TOTAL_RE = re.compile(r"^((?:19|20)\d{2})\s+TOTALS?\s*:?$", re.I)
COOP_RE = re.compile(r"\bco[\s-]?op\b", re.I)
ANNUAL_HEAD_RE = re.compile(r"\s*(annual( total)?|total)\s*", re.I)
YEAR_ACTUAL_RE = re.compile(r"\b((?:19|20)\d{2})\s+Actual\b", re.I)
EXEMPT_ROW_RE = re.compile(r"yoy|change|\bvs\b|growth", re.I)
# Columns whose TOTAL cell is blank or a ratio of the TOTAL cells, never a sum.
# A '%' right after a digit ("Planning Low (-12%)", "+25% Budget") is a scenario
# name, not a percentage column, so those columns stay additive.
NON_ADDITIVE_HEAD_RE = re.compile(
    r"index|prior|rate|share|elastic|cost\s*/|cost per|\bper\b|\bcp[lsc]\b|\bctr\b|yoy|growth|"
    r"(?:^|[^\d\s])\s*%|%\s*(?:change|of)\b|tier|rating|note|status|rationale|action", re.I)
REF_TOKEN_RE = re.compile(r"(?:(?:'(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_.]*)!)?\$?([A-Za-z]{1,3})\$?\d+")


def find_sheet(wb, pattern):
    for ws in wb.worksheets:
        if re.search(pattern, ws.title, re.I):
            return ws
    return None


def addr(ws, row, col):
    return "'{}'!{}{}".format(ws.title, idx_to_col(col), row)


def label_of(ws, row):
    """Text (or date) label of a row from columns A to C.

    A real Excel date in the Month column is a row label: pandas and openpyxl
    generators often write months as datetimes, and treating them as blank
    would let a typed TOTAL past the gate.
    """
    for c in range(1, min(ws.max_column, 3) + 1):
        v = ws.cell(row=row, column=c).value
        if isinstance(v, str) and v.strip() and not v.startswith("="):
            return v.strip()
        if isinstance(v, (datetime.date, datetime.datetime)):
            return v.strftime("%Y-%m-%d")
    return ""


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def is_formula(v):
    return isinstance(v, str) and v.startswith("=")


class WorkbookCheck(object):
    def __init__(self, path, facts, rep, strict_labels):
        import openpyxl  # imported here so facts/audit/tiers run without it
        self.path = path
        self.facts = facts
        self.rep = rep
        self.strict = strict_labels
        self.wb = openpyxl.load_workbook(path, data_only=False)
        self.cached = openpyxl.load_workbook(path, data_only=True)
        self.ev = Evaluator(self.wb)

    def val(self, ws, row, col):
        try:
            return self.ev.value(ws.title, col, row)
        except Unsupported:
            cv = self.cached[ws.title].cell(row=row, column=col).value
            return cv

    def num(self, ws, row, col):
        return _num(self.val(ws, row, col))

    def label_issue(self, msg):
        (self.rep.fail if self.strict else self.rep.warn)(msg)

    # -- checks
    def run(self):
        self.required_tabs()
        self.recompute_all()
        self.total_rows()
        self.history_total_rows()
        self.total_columns()
        self.actual_columns()
        self.exec_vs_history()
        self.budget_vs_history()
        self.vendor_roi()
        self.baselines()
        self.reallocation()
        self.net_labels()
        self.em_dashes()
        self.labels()
        if self.facts is not None:
            self.against_facts()

    def required_tabs(self):
        for name, pat in REQUIRED_TABS:
            if find_sheet(self.wb, pat) is None:
                self.rep.fail("required tab missing: {}".format(name))

    def recompute_all(self):
        checked = unchecked = errors = mismatched = has_cache = 0
        bad = []
        unsup = {}
        for ws in self.wb.worksheets:
            cws = self.cached[ws.title]
            for row in ws.iter_rows():
                for cell in row:
                    if not is_formula(cell.value):
                        continue
                    try:
                        mine = self.ev.value(ws.title, cell.column, cell.row)
                    except Unsupported as exc:
                        unchecked += 1
                        unsup.setdefault(str(exc), addr(ws, cell.row, cell.column))
                        continue
                    checked += 1
                    cached = cws.cell(row=cell.row, column=cell.column).value
                    if cached is not None:
                        has_cache += 1
                    if isinstance(mine, XlError):
                        errors += 1
                        bad.append("{} {} -> {}".format(addr(ws, cell.row, cell.column), cell.value, mine.code))
                    elif cached is not None and not same(mine, cached):
                        mismatched += 1
                        bad.append("{} cached {!r}, recomputed {!r}".format(
                            addr(ws, cell.row, cell.column), cached, mine))
        self.rep.info("recomputed {} formula cells ({} could not be evaluated here)".format(checked, unchecked))
        if errors:
            self.rep.fail("{} formula cell(s) evaluate to an Excel error: {}".format(errors, "; ".join(bad[:8])))
        if mismatched:
            self.rep.fail("{} formula cell(s) disagree with their saved values (recalc not run, or stale): {}".format(
                mismatched, "; ".join([b for b in bad if "cached" in b][:8])))
        if checked and not has_cache:
            self.rep.warn("no saved formula values: run the xlsx skill's recalc.py before this check")
        if unsup:
            self.rep.warn("formulas this checker cannot evaluate (check them by hand): " + "; ".join(
                "{} at {}".format(k, v) for k, v in list(unsup.items())[:5]))

    def _row_has_data(self, ws, r):
        return any(_is_number(ws.cell(row=r, column=c).value) or is_formula(ws.cell(row=r, column=c).value)
                   for c in range(2, ws.max_column + 1))

    def _row_blank(self, ws, r):
        """A spacer row: no text or date label in A to C and no number or formula in any column."""
        if label_of(ws, r):
            return False
        return not any(_is_number(ws.cell(row=r, column=c).value) or is_formula(ws.cell(row=r, column=c).value)
                       for c in range(1, ws.max_column + 1))

    def _skip_blank_up(self, ws, r):
        """First row at or above r that is not a blank spacer row (0 when there is none)."""
        while r >= 1 and self._row_blank(ws, r):
            r -= 1
        return r

    def _block_rows(self, ws, total_row):
        """Detail rows of a TOTAL row: the labelled data rows directly above it.

        Blank spacer rows between the TOTAL row and its details are stepped over,
        so a spaced TOTAL is still checked cell by cell.
        """
        rows = []
        r = self._skip_blank_up(ws, total_row - 1)
        while r >= 1:
            lab = label_of(ws, r)
            if not lab or TOTAL_LABEL_RE.match(lab):
                break
            if not self._row_has_data(ws, r):
                break
            rows.append(r)
            r -= 1
        return sorted(rows)

    def _column_head(self, ws, first_row, c):
        for hr in range(first_row - 1, 0, -1):
            hv = ws.cell(row=hr, column=c).value
            if isinstance(hv, str) and not is_formula(hv):
                return hv
        return ""

    def total_rows(self):
        for ws in self.wb.worksheets:
            for r in range(1, ws.max_row + 1):
                lab = label_of(ws, r)
                if not lab or not TOTAL_LABEL_RE.match(lab):
                    continue
                if lab != lab.upper():
                    self.rep.warn("{} TOTAL label {!r} is not in capitals (spec: 'TOTAL' or '{{YEAR}} TOTAL')".format(
                        addr(ws, r, 1), lab))
                block = self._block_rows(ws, r)
                if block:
                    for c in range(2, ws.max_column + 1):
                        self._check_total_cell(ws, r, c, block)
                    continue
                # No detail rows directly above (after any spacer rows). Never skip the
                # row: a grand total under other TOTAL rows must add them up, and a
                # typed number in any TOTAL cell fails.
                parts = self._total_parts(ws, r)
                above = self._skip_blank_up(ws, r - 1)
                if not parts and above >= 1 and self._row_has_data(ws, above) and not label_of(ws, above):
                    self.rep.fail("{} TOTAL row: row {} above it holds numbers but has no text or date label in "
                                  "columns A to C, so the total cannot be tied to its detail rows; label every "
                                  "detail row".format(addr(ws, r, 1), above))
                for c in range(2, ws.max_column + 1):
                    self._check_grand_total_cell(ws, r, c, parts)

    def _total_parts(self, ws, r):
        """TOTAL rows a grand total at row r adds up: the chain of TOTAL rows directly
        above it (spacer rows allowed), each one's own detail block stepped over."""
        parts = []
        x = self._skip_blank_up(ws, r - 1)
        while x >= 1 and TOTAL_LABEL_RE.match(label_of(ws, x)):
            parts.append(x)
            blk = self._block_rows(ws, x)
            if not blk:
                break
            x = self._skip_blank_up(ws, blk[0] - 1)
        return sorted(parts)

    def _check_grand_total_cell(self, ws, r, c, parts):
        """A TOTAL cell with no detail rows of its own (a grand total, or an orphan)."""
        tv = ws.cell(row=r, column=c).value
        where = addr(ws, r, c)
        vals = [self.num(ws, p, c) for p in parts]
        known = bool(parts) and all(v is not None for v in vals)
        first = (self._block_rows(ws, parts[0]) or [parts[0]])[0] if parts else r
        head = self._column_head(ws, first, c)
        non_additive = bool(parts) and bool(NON_ADDITIVE_HEAD_RE.search(head))
        additive = known and not non_additive
        expect = sum(vals) if known else None
        rows_txt = ", ".join(str(p) for p in parts)
        if _is_number(tv):
            if tv == 0 and not (additive and expect):
                self.rep.warn("{} is a typed 0 in a TOTAL row; use a formula".format(where))
                return
            msg = "{} is a typed number {} in a TOTAL row".format(where, fmt(float(tv)))
            if additive:
                msg += "; it must add the TOTAL rows above it (rows {}), which come to {}".format(rows_txt, fmt(expect))
            elif non_additive:
                msg += " of the non-additive column {!r}; leave it blank or derive it with a formula".format(head)
            elif parts:
                msg += " under the TOTAL rows {}; it must be a formula over them".format(rows_txt)
            else:
                msg += " with no detail rows above it; TOTAL cells are formulas over labelled detail rows"
            self.rep.fail(msg)
            return
        if not additive or not is_formula(tv):
            return
        got = self.num(ws, r, c)
        if got is not None and not close(got, expect, 0.5, 1e-9):
            self.rep.fail("{} = {} but the TOTAL rows above it (rows {}) add up to {}".format(
                where, fmt(got), rows_txt, fmt(expect)))

    def _check_total_cell(self, ws, r, c, block):
        details = [ws.cell(row=x, column=c).value for x in block]
        literal = [v for v in details if _is_number(v)]
        formulas = [v for v in details if is_formula(v)]
        tv = ws.cell(row=r, column=c).value
        where = addr(ws, r, c)
        span = "{0}{1}:{0}{2}".format(idx_to_col(c), block[0], block[-1])
        if not literal and not formulas:
            if _is_number(tv) and tv != 0:
                self.rep.fail("{} is a typed number {} in a TOTAL row, but rows {}-{} of that column are "
                              "empty".format(where, fmt(float(tv)), block[0], block[-1]))
            elif _is_number(tv):
                self.rep.warn("{} is a typed 0 in a TOTAL row over an empty column; use =SUM({})".format(where, span))
            return
        head = self._column_head(ws, block[0], c)
        additive = not NON_ADDITIVE_HEAD_RE.search(head)
        detail_nums = [self.num(ws, x, c) for x in block]
        if not literal:
            # formula-only column: additive only when its details evaluate to numbers
            additive = additive and any(v is not None for v in detail_nums)
        expect = sum(float(v or 0) for v in detail_nums)
        if _is_number(tv):
            if additive:
                msg = "{} is a typed number {} in a TOTAL row; it must be =SUM({})".format(where, fmt(float(tv)), span)
                if not close(float(tv), expect, 0.5):
                    msg += " and the rows sum to {}".format(fmt(expect))
            else:
                msg = ("{} is a typed number {} in a TOTAL row of the non-additive column {!r}; leave it blank "
                       "or derive it from the TOTAL cells with a formula".format(where, fmt(float(tv)), head))
            self.rep.fail(msg)
            return
        if not additive:
            return  # ratio, index or text column: blank or a ratio formula is fine
        if tv is None:
            if literal:
                self.rep.warn("{} is blank but rows {}-{} hold numbers (sum {})".format(
                    where, block[0], block[-1], fmt(expect)))
            return
        if not is_formula(tv):
            return
        m = re.fullmatch(r"=\s*SUM\(\s*\$?([A-Z]+)\$?(\d+)\s*:\s*\$?([A-Z]+)\$?(\d+)\s*\)", tv.upper())
        if m:
            c1, r1, c2, r2 = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
            # the range may run on through blank spacer rows (block[-1] < r2 < r), never short of them
            if c1 != idx_to_col(c) or c2 != idx_to_col(c) or r1 != block[0] or not block[-1] <= r2 < r:
                self.rep.fail("{} is {} but its detail rows are {}".format(where, tv, span))
                return
        got = self.num(ws, r, c)
        if got is None:
            return
        # a plain SUM must match exactly; another formula (e.g. =ROUND(D17*0.88,0))
        # may differ from the sum of rounded rows by half a unit per row
        tol = 0.5 if (m or literal) else 0.5 * len(block) + 0.5
        if not close(got, expect, tol, 1e-9):
            self.rep.fail("{} = {} but rows {}-{} sum to {}".format(
                where, fmt(got), block[0], block[-1], fmt(expect)))

    def total_columns(self):
        for ws in self.wb.worksheets:
            for hr in range(1, min(ws.max_row, 12) + 1):
                for c in range(2, ws.max_column + 1):
                    h = ws.cell(row=hr, column=c).value
                    if not (isinstance(h, str) and ANNUAL_HEAD_RE.fullmatch(h)):
                        continue
                    for r in range(hr + 1, ws.max_row + 1):
                        nums = [x for x in range(1, c) if isinstance(ws.cell(row=r, column=x).value, (int, float))]
                        if not nums:
                            continue
                        tv = ws.cell(row=r, column=c).value
                        expect = sum(float(self.num(ws, r, x) or 0) for x in nums)
                        where = addr(ws, r, c)
                        if isinstance(tv, (int, float)) and not isinstance(tv, bool):
                            self.rep.fail("{} is a typed number {}; the row total must be a SUM formula".format(
                                where, fmt(float(tv))))
                        elif is_formula(tv):
                            got = self.num(ws, r, c)
                            if got is not None and not close(got, expect, 0.5, 1e-9):
                                self.rep.fail("{} = {} but the row sums to {}".format(where, fmt(got), fmt(expect)))

    def actual_columns(self):
        for ws in self.wb.worksheets:
            for hr in range(1, min(ws.max_row, 15) + 1):
                for c in range(1, ws.max_column + 1):
                    h = ws.cell(row=hr, column=c).value
                    if not (isinstance(h, str) and YEAR_ACTUAL_RE.search(h)):
                        continue
                    col = idx_to_col(c)
                    for r in range(hr + 1, ws.max_row + 1):
                        v = ws.cell(row=r, column=c).value
                        if not is_formula(v):
                            continue
                        if EXEMPT_ROW_RE.search(label_of(ws, r)):
                            continue
                        refs = set(m.group(1).upper() for m in REF_TOKEN_RE.finditer(v[1:]) if "!" not in m.group(0))
                        others = sorted(x for x in refs if x != col)
                        if others:
                            self.rep.fail("{} {} sits in the '{}' column but reads column {}".format(
                                addr(ws, r, c), v, h, ", ".join(others)))

    def _history_totals(self):
        ws = find_sheet(self.wb, r"history")
        if ws is None:
            return None, {}
        hdr = {}
        for hr in range(1, min(ws.max_row, 15) + 1):
            cells = {c: ws.cell(row=hr, column=c).value for c in range(1, ws.max_column + 1)}
            texts = {c: v.lower() for c, v in cells.items() if isinstance(v, str)}
            if any("spend" in t for t in texts.values()) and any("lead" in t for t in texts.values()):
                hdr = texts
                break
        totals = {}
        for r in range(1, ws.max_row + 1):
            m = YEAR_TOTAL_RE.match(label_of(ws, r))
            if m:
                totals[m.group(1)] = r
        return ws, {"hdr": hdr, "rows": totals}

    @staticmethod
    def _hist_col(hdr, kind):
        """Column of a History metric from the lower-cased header texts."""
        ratio = r"cost|rate|per |/|share|%"
        for c in sorted(hdr):
            h = hdr[c]
            if re.search(ratio, h):
                continue
            if kind == "spend" and "spend" in h:
                return c
            if kind == "leads" and "lead" in h and not re.search(r"unique|good|dup|invalid", h):
                return c
            if kind == "sales" and re.search(r"\bsales?\b", h):
                return c
            if kind == "dups" and "dup" in h:
                return c
            if kind == "invalid" and "invalid" in h:
                return c
            if kind == "unique" and "unique" in h:
                return c
        return None

    def history_total_rows(self):
        """The History tab must carry a '{YEAR} TOTAL' row per year (spec, Tab 2)."""
        hs, info = self._history_totals()
        if hs is None:
            return
        if not info.get("rows"):
            self.rep.fail("'{}' has no '{{YEAR}} TOTAL' row (e.g. '2025 TOTAL'); every year of history needs "
                          "one, as =SUM() of its months".format(hs.title))
        if not info.get("hdr"):
            self.rep.warn("'{}' header row with Spend and Leads not found in the first 15 rows; History totals "
                          "not cross-checked".format(hs.title))

    def exec_vs_history(self):
        es = find_sheet(self.wb, r"executive summary")
        hs, info = self._history_totals()
        if es is None or hs is None or not info.get("rows"):
            return

        def hist_col(kind):
            return self._hist_col(info["hdr"], kind)
        literal_cells = []
        for hr in range(1, min(es.max_row, 20) + 1):
            for c in range(1, es.max_column + 1):
                h = es.cell(row=hr, column=c).value
                m = YEAR_ACTUAL_RE.search(h) if isinstance(h, str) else None
                if not m or m.group(1) not in info["rows"]:
                    continue
                trow = info["rows"][m.group(1)]
                for r in range(hr + 1, es.max_row + 1):
                    lab = label_of(es, r).lower()
                    if not lab or re.search(r"cost|rate|change|per ", lab):
                        continue
                    kind = ("spend" if "spend" in lab else "sales" if re.search(r"\bsales?\b", lab)
                            else "leads" if "lead" in lab and not re.search(r"good|unique|dup", lab) else None)
                    hc = hist_col(kind) if kind else None
                    if not hc:
                        continue
                    ev = self.num(es, r, c)
                    hv = self.num(hs, trow, hc)
                    if ev is None or hv is None:
                        continue
                    raw = es.cell(row=r, column=c).value
                    if not close(ev, hv, 0.5):
                        self.rep.fail("{} {} = {} but {} total is {}".format(
                            addr(es, r, c), label_of(es, r), fmt(ev), addr(hs, trow, hc), fmt(hv)))
                    elif not is_formula(raw):
                        literal_cells.append("{} (={})".format(addr(es, r, c), addr(hs, trow, hc)))
        if literal_cells:
            self.rep.warn("Executive Summary KPIs typed as numbers; reference the history totals instead: "
                          + ", ".join(literal_cells))

    @staticmethod
    def _budget_year(ws):
        """Year of a Budget Detail tab: from the tab name, else from a title cell naming the budget."""
        m = re.search(r"\b((?:19|20)\d{2})\b", ws.title)
        if m:
            return m.group(1)
        for r in range(1, min(ws.max_row, 3) + 1):
            for c in range(1, ws.max_column + 1):
                v = ws.cell(row=r, column=c).value
                if isinstance(v, str) and re.search(r"budget", v, re.I):
                    m = re.search(r"\b((?:19|20)\d{2})\b", v)
                    if m:
                        return m.group(1)
        return None

    def budget_vs_history(self):
        """Budget Detail TOTAL (Annual Total column) = History '{YEAR} TOTAL' spend (spec, Tab 6).

        A budget that drops or double-counts a vendor line fails here. Under --facts it
        is also compared with facts.history_totals[year].spend. A missing TOTAL row or
        header only warns; the detail rows are then summed and still tied out.
        """
        bd = find_sheet(self.wb, r"budget detail")
        if bd is None:
            return
        year = self._budget_year(bd)
        if year is None:
            self.rep.warn("'{}': no year in the tab name or title, so its spend is not tied to the History "
                          "tab".format(bd.title))
            return
        hr = col = None
        for r in range(1, min(bd.max_row, 12) + 1):
            for c in range(2, bd.max_column + 1):
                h = bd.cell(row=r, column=c).value
                if isinstance(h, str) and ANNUAL_HEAD_RE.fullmatch(h):
                    hr, col = r, c
                    break
            if hr:
                break
        if hr is None:
            self.rep.warn("'{}' has no 'Annual Total' column header in the first 12 rows; its spend is not tied "
                          "to the History tab".format(bd.title))
            return
        trow, detail = None, []
        for r in range(hr + 1, bd.max_row + 1):
            lab = label_of(bd, r)
            if lab and TOTAL_LABEL_RE.match(lab):
                trow = r
                break
            text = " ".join(v for v in (bd.cell(row=r, column=c).value for c in (1, 2, 3)) if isinstance(v, str))
            if lab and not COOP_RE.search(text) and self._row_has_data(bd, r):
                detail.append(r)
        L = idx_to_col(col)
        if trow is not None:
            got = self.num(bd, trow, col)
            what = "{} (Budget Detail TOTAL)".format(addr(bd, trow, col))
        else:
            self.rep.warn("'{}' has no TOTAL row (spec: a TOTAL row with =SUM() for every month and the annual "
                          "column); tying the sum of its detail rows to the History spend instead".format(bd.title))
            if not detail:
                return
            vals = [self.num(bd, r, col) for r in detail]
            got = sum(v for v in vals if v is not None) if any(v is not None for v in vals) else None
            what = "the sum of '{}'!{}{}:{}{}".format(bd.title, L, detail[0], L, detail[-1])
        if got is None:
            return  # a blank or text TOTAL cell is reported by total_rows()
        hs, info = self._history_totals()
        hrow = (info.get("rows") or {}).get(year)
        scol = self._hist_col(info.get("hdr") or {}, "spend") if hs is not None else None
        if hs is not None and (hrow is None or scol is None):
            self.rep.warn("'{}' has no '{} TOTAL' spend cell, so '{}' is not tied to it".format(
                hs.title, year, bd.title))
        elif hs is not None:
            hv = self.num(hs, hrow, scol)
            if hv is not None and not close(got, hv, 1.0):
                self.rep.fail("{} = {} but {} {} TOTAL spend = {}; the budget drops or double-counts a line, or the "
                              "History spend is off".format(what, fmt(got), addr(hs, hrow, scol), year, fmt(hv)))
        if self.facts is not None:
            want = _num(((self.facts.get("history_totals") or {}).get(year) or {}).get("spend"))
            if want is not None and not close(got, want, 1.0):
                self.rep.fail("{} = {} but facts.history_totals[{}].spend = {}".format(what, fmt(got), year, fmt(want)))

    def _vendor_layout(self, ws):
        for hr in range(1, min(ws.max_row, 15) + 1):
            cols = {}
            for c in range(1, ws.max_column + 1):
                h = ws.cell(row=hr, column=c).value
                if not isinstance(h, str):
                    continue
                s = h.strip().lower()
                if s in ("vendor", "vendor / source", "provider", "vendor name"):
                    cols["vendor"] = c
                elif "spend" in s and "share" not in s:
                    cols.setdefault("spend", c)
                elif re.search(r"cost\s*/\s*sale|cost per sale|\bcps\b", s):
                    cols["cps"] = c
                elif re.search(r"cost\s*/\s*lead|cost per lead|\bcpl\b", s):
                    cols["cpl"] = c
                elif "lead" in s and "share" not in s and "cost" not in s:
                    cols.setdefault("leads", c)
                elif "sale" in s and "cost" not in s:
                    cols.setdefault("sales", c)
                elif s.startswith("tier"):
                    cols["tier"] = c
                elif s.startswith("rating"):
                    cols["rating"] = c
            if "vendor" in cols and "spend" in cols:
                return hr, cols
        return None, {}

    def vendor_roi(self):
        ws = find_sheet(self.wb, r"vendor roi")
        if ws is None:
            return
        hr, cols = self._vendor_layout(ws)
        if hr is None:
            self.rep.fail("'{}' has no header row with Vendor and Spend columns".format(ws.title))
            return
        for need in ("leads", "sales"):
            if need not in cols:
                self.rep.fail("'{}' has no {} column".format(ws.title, need))
                return
        if "tier" not in cols:
            self.rep.fail("'{}' has no Tier column (tier must sit beside the rating)".format(ws.title))
        rows = []
        r = hr + 1
        while r <= ws.max_row:
            name = ws.cell(row=r, column=cols["vendor"]).value
            if name is None or (isinstance(name, str) and (not name.strip() or TOTAL_LABEL_RE.match(name.strip()))):
                break
            rows.append(r)
            r += 1
        data = []
        for r in rows:
            data.append((r, self.num(ws, r, cols["spend"]) or 0.0, self.num(ws, r, cols["leads"]) or 0.0,
                         self.num(ws, r, cols["sales"]) or 0.0))
        has_cost = any(d[1] > 0 for d in data)
        cps_seq, cpl_seq = [], []
        for r, spend, leads, sales in data:
            tier, rating, _note, cps = tier_rule(spend, leads, sales, has_cost)
            cps_seq.append(cps)
            cpl_seq.append(spend / leads if leads else None)
            if tier is None:
                continue
            cps_txt = "${:,.0f}".format(cps) if cps is not None else "no CPS"
            if "tier" in cols:
                got = norm_tier(self.val(ws, r, cols["tier"]))
                if got != tier:
                    self.rep.fail("{} tier {!r}, rule says {} ({}, {})".format(
                        addr(ws, r, cols["tier"]), self.val(ws, r, cols["tier"]), tier,
                        ws.cell(row=r, column=cols["vendor"]).value, cps_txt))
            if "rating" in cols:
                got = norm_rating(self.val(ws, r, cols["rating"]))
                if got != rating:
                    self.rep.fail("{} rating {!r}, rule says {} ({}, {})".format(
                        addr(ws, r, cols["rating"]), self.val(ws, r, cols["rating"]), rating,
                        ws.cell(row=r, column=cols["vendor"]).value, cps_txt))
            if "cps" in cols:
                cv = self.val(ws, r, cols["cps"])
                if cps is None and isinstance(cv, (int, float)) and not isinstance(cv, bool):
                    self.rep.fail("{} shows a cost per sale {} for a row with no sales; show '-'".format(
                        addr(ws, r, cols["cps"]), fmt(float(cv))))
                if isinstance(cv, XlError):
                    self.rep.fail("{} cost per sale is {}".format(addr(ws, r, cols["cps"]), cv.code))
        if has_cost and not order_ok(cps_seq):
            hint = ""
            if order_ok(cpl_seq):
                hint = " (they are in cost-per-lead order)"
            self.rep.fail("'{}' rows {}-{} are not sorted by cost per sale{}".format(
                ws.title, rows[0] if rows else "?", rows[-1] if rows else "?", hint))
        self.vendor_rows = [(ws.cell(row=r, column=cols["vendor"]).value, s, l, sa) for r, s, l, sa in data]

    def _scenario_cols(self, ws, need_status_quo=False):
        for hr in range(1, min(ws.max_row, 25) + 1):
            m = {}
            for c in range(1, ws.max_column + 1):
                h = ws.cell(row=hr, column=c).value
                if not isinstance(h, str):
                    continue
                if "+25%" in h:
                    m["+25%"] = c
                elif "-15%" in h or "\u221215%" in h:
                    m["-15%"] = c
                elif re.search(r"status quo|baseline", h, re.I):
                    m.setdefault("baseline", c)
            if "+25%" in m and "-15%" in m and "baseline" in m:
                return hr, m
        return None, {}

    def _row_by_label(self, ws, start, pattern, exclude=r"cost|rate|change|per |%"):
        for r in range(start + 1, ws.max_row + 1):
            lab = label_of(ws, r)
            if re.search(pattern, lab, re.I) and not re.search(exclude, lab, re.I):
                return r
        return None

    def baselines(self):
        es = find_sheet(self.wb, r"executive summary")
        sp = find_sheet(self.wb, r"scenario")
        fc = find_sheet(self.wb, r"forecast")
        if es is None or sp is None:
            return
        ehr, ecols = self._scenario_cols(es)
        shr, scols = self._scenario_cols(sp)
        if ehr is None or shr is None:
            self.rep.warn("could not locate the baseline/+25%/-15% columns on Executive Summary and Scenario Planner")
            return
        pairs = (("leads", self._row_by_label(es, ehr, r"lead", r"cost|rate|change|per |%|sales|good|unique|dup"),
                  self._row_by_label(sp, shr, r"^projected leads", r"$^")),
                 ("sales", self._row_by_label(es, ehr, r"sales"), self._row_by_label(sp, shr, r"^projected sales", r"$^")))
        for metric, er, sr in pairs:
            if er is None or sr is None:
                self.rep.warn("could not locate the {} rows for the baseline cross-check".format(metric))
                continue
            for key in ("baseline", "+25%", "-15%"):
                a, b = self.num(es, er, ecols[key]), self.num(sp, sr, scols[key])
                if a is None or b is None:
                    continue
                if not close(a, b, 1.0, 0.001):
                    self.rep.fail("{} {}: {} = {} but {} = {} (the two tabs use different baselines)".format(
                        key, metric, addr(es, er, ecols[key]), fmt(a), addr(sp, sr, scols[key]), fmt(b)))
        if fc is None:
            return
        fhr, fcols = self._scenario_cols(fc)
        er = pairs[0][1]
        if fhr is None or er is None:
            return
        tr = None
        for r in range(fhr + 1, fc.max_row + 1):
            if TOTAL_LABEL_RE.match(label_of(fc, r) or ""):
                tr = r
                break
        if tr is None:
            return
        for key in ("baseline", "+25%", "-15%"):
            a, b = self.num(es, er, ecols[key]), self.num(fc, tr, fcols[key])
            if a is None or b is None:
                continue
            if not close(a, b, 6.0, 0.005):
                self.rep.fail("{} leads: {} = {} but the forecast total {} = {}".format(
                    key, addr(es, er, ecols[key]), fmt(a), addr(fc, tr, fcols[key]), fmt(b)))

    def reallocation(self):
        ws = find_sheet(self.wb, r"realloc")
        if ws is None:
            return
        for hr in range(1, ws.max_row + 1):
            cur = prop = None
            for c in range(1, ws.max_column + 1):
                h = ws.cell(row=hr, column=c).value
                if isinstance(h, str) and re.fullmatch(r"\s*current( spend)?\s*", h, re.I):
                    cur = c
                if isinstance(h, str) and re.fullmatch(r"\s*proposed( spend)?\s*", h, re.I):
                    prop = c
            if not (cur and prop):
                continue
            for r in range(hr + 1, ws.max_row + 1):
                if TOTAL_LABEL_RE.match(label_of(ws, r) or ""):
                    a, b = self.num(ws, r, cur), self.num(ws, r, prop)
                    if a is not None and b is not None and not close(a, b, 1.0):
                        self.rep.fail("{} current {} vs proposed {}: the reallocation is not budget neutral".format(
                            addr(ws, r, prop), fmt(a), fmt(b)))
                    break
            return

    def _strings(self):
        for ws in self.wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    v = cell.value
                    if isinstance(v, str):
                        yield ws, cell, v

    def net_labels(self):
        net = [addr(ws, c.row, c.column) for ws, c, v in self._strings() if "(net)" in v.lower()]
        coop = [1 for ws, c, v in self._strings() if re.search(r"\bco[\s-]?op\b", v, re.I) and "(net)" not in v.lower()]
        if net and not coop:
            self.rep.fail("'(net)' label with no co-op row anywhere; spend is gross: " + ", ".join(net))

    def em_dashes(self):
        hits = [addr(ws, c.row, c.column) for ws, c, v in self._strings() if EM_DASH in v]
        hits += ["tab name '{}'".format(ws.title) for ws in self.wb.worksheets if EM_DASH in ws.title]
        if hits:
            self.rep.fail("{} cell(s) contain an em dash (house rule): {}{}".format(
                len(hits), ", ".join(hits[:10]), " ..." if len(hits) > 10 else ""))

    def labels(self):
        ci, meas, nada, sales_el = [], [], [], []
        for ws, c, raw in self._strings():
            v = strip_negated(raw)
            a = addr(ws, c.row, c.column)
            on_forecast = re.search(r"forecast", ws.title, re.I) is not None
            # "(80%)" counts only on a band header ("Lower (80%)"), never on model
            # weights ("Prophet (25%)") or the planning columns ("Planning Low (-12%)")
            band_head = (re.search(r"\b(low|high|lower|upper|bound|band|range|interval)\b", v, re.I)
                         and not re.search(r"planning", v, re.I) and re.search(r"\(\s*\d{2}\s*%\s*\)", v))
            if re.search(r"\b80\s*%\s*(CI|conf)", v, re.I) or (on_forecast and (band_head or re.search(
                    r"\b\d{2}\s*%\s*(CI|conf)|confidence interval", v, re.I))):
                ci.append(a)
            if re.search(r"\bmeasured\b", v, re.I) and re.search(r"elastic", v, re.I):
                meas.append(a)
            if re.search(r"NADA\s+(index|seasonal)", v, re.I):
                nada.append(a)
            if re.search(r"elastic", v, re.I) and re.search(r"\(sales\)|sales elastic", v, re.I):
                sales_el.append(a)
        if ci:
            self.label_issue("a fixed +/-12% band is labelled as a statistical interval; use 'Planning Low/High' "
                             "and 'Planning range, not a statistical interval.': " + ", ".join(ci))
        if meas:
            self.label_issue("elasticity labelled 'Measured'; it is 'Estimated' (with p): " + ", ".join(meas))
        if nada:
            self.label_issue("seasonal indices labelled NADA with no named source; use 'Seasonal prior "
                             "(DigitalCLIQ estimate)': " + ", ".join(nada))
        if sales_el:
            self.label_issue("sales elasticity row present; project sales as projected leads x baseline close "
                             "rate: " + ", ".join(sales_el))
        es = find_sheet(self.wb, r"executive summary")
        if es is not None:
            found = any(isinstance(es.cell(row=r, column=c).value, str)
                        and es.cell(row=r, column=c).value.strip().lower().startswith("lead definition:")
                        for r in range(1, es.max_row + 1) for c in range(1, es.max_column + 1))
            if not found:
                self.label_issue("Executive Summary has no 'Lead definition: <report> <column>; excludes "
                                 "<sources>; data <start> to <end>.' line")

    def against_facts(self):
        f = self.facts
        models = f.get("models") or {}
        ran = list(models.get("ran") or [])
        claims = [addr(ws, c.row, c.column) for ws, c, v in self._strings() if re.search(r"3[- ]model", v, re.I)]
        if claims and len(ran) != 3:
            self.rep.fail("workbook says 3-model at {} but facts list {} model(s): {}".format(
                ", ".join(claims), len(ran), ", ".join(ran)))
        defs = f.get("definitions") or {}
        es = find_sheet(self.wb, r"executive summary")
        if es is not None:
            line = None
            for r in range(1, es.max_row + 1):
                for c in range(1, es.max_column + 1):
                    v = es.cell(row=r, column=c).value
                    if isinstance(v, str) and v.strip().lower().startswith("lead definition:"):
                        line = v
            if line:
                for k in ("report_name", "lead_definition_column"):
                    if defs.get(k) and str(defs[k]).lower() not in line.lower():
                        self.rep.fail("Executive Summary lead definition line does not name the facts {} {!r}".format(
                            k, defs[k]))
        self._history_totals_vs_facts()
        fc = find_sheet(self.wb, r"forecast")
        base = [float(x) for x in (f.get("forecast") or {}).get("baseline") or []]
        if fc is not None and base:
            hr, cols = self._scenario_cols(fc)
            if hr is not None:
                vals = []
                for r in range(hr + 1, hr + 1 + len(base)):
                    vals.append(self.num(fc, r, cols["baseline"]))
                for i, (a, b) in enumerate(zip(vals, base)):
                    if a is None or not close(a, b, 1.0):
                        self.rep.fail("{} baseline {} but facts month {} is {}".format(
                            addr(fc, hr + 1 + i, cols["baseline"]), a, i + 1, fmt(b)))
                        break
        vend = {str(v.get("vendor")).strip().lower(): v for v in f.get("vendors") or []}
        for name, spend, leads, sales in getattr(self, "vendor_rows", []):
            fv = vend.get(str(name).strip().lower())
            if fv is None:
                self.rep.fail("Vendor ROI row '{}' is not in facts.vendors".format(name))
                continue
            for k, got in (("spend", spend), ("leads", leads), ("sales", sales)):
                if not close(got, float(fv.get(k) or 0), 0.5):
                    self.rep.fail("Vendor ROI '{}' {} {} but facts say {}".format(name, k, fmt(got), fv.get(k)))
        excluded = set(s.strip().lower() for s in defs.get("excluded_sources") or [])
        for name, _s, _l, _sa in getattr(self, "vendor_rows", []):
            if str(name).strip().lower() in excluded:
                self.rep.fail("excluded source '{}' appears as a Vendor ROI row".format(name))

    def _history_totals_vs_facts(self):
        """Each History '{YEAR} TOTAL' row must equal facts.history_totals for that year."""
        totals = self.facts.get("history_totals") or {}
        if not totals:
            return
        hs, info = self._history_totals()
        if hs is None:
            return
        rows, hdr = info.get("rows") or {}, info.get("hdr") or {}
        for year in sorted(totals):
            trow = rows.get(str(year))
            if trow is None:
                self.rep.fail("facts.history_totals has {} but '{}' has no '{} TOTAL' row".format(
                    year, hs.title, year))
                continue
            for key in sorted(totals[year]):
                want = _num(totals[year][key])
                col = self._hist_col(hdr, key)
                if want is None or col is None:
                    continue
                got = self.num(hs, trow, col)
                if got is None:
                    self.rep.fail("{} {} TOTAL {} is blank or not a number; facts say {}".format(
                        addr(hs, trow, col), year, key, fmt(want)))
                elif not close(got, want, 0.5):
                    self.rep.fail("{} {} TOTAL {} = {} but facts.history_totals say {}".format(
                        addr(hs, trow, col), year, key, fmt(got), fmt(want)))


def sidecar(facts, xlsx_path):
    f = facts
    defs = f.get("definitions") or {}
    fc = f.get("forecast") or {}
    el = f.get("elasticity") or {}
    lead_el = el.get("leads") or {}
    models = f.get("models") or {}
    stem = xlsx_path[:-5] if xlsx_path.lower().endswith(".xlsx") else xlsx_path
    out = {
        "schema": "forecast-sidecar/1",
        "workbook": os.path.basename(xlsx_path),
        "written": datetime.date.today().isoformat(),
        "client_code": (f.get("client") or {}).get("code"),
        "client_name": (f.get("client") or {}).get("name"),
        "crm": defs.get("crm"),
        "report_name": defs.get("report_name"),
        "lead_definition_column": defs.get("lead_definition_column"),
        "close_rate_basis": defs.get("close_rate_basis"),
        "excluded_sources": defs.get("excluded_sources"),
        "data_window": defs.get("data_window"),
        "months": fc.get("months"),
        "baseline": fc.get("baseline"),
        "low": fc.get("low"),
        "high": fc.get("high"),
        "interval_method": fc.get("interval_method"),
        "elasticity": {"slope": lead_el.get("slope"), "p": lead_el.get("p"), "n": lead_el.get("n"),
                       "label": el.get("label")},
        "models": {"ran": models.get("ran"), "weights": models.get("weights")},
        "verify": "PASSED",
    }
    empty = [k for k, v in out.items() if v in (None, "", {}, []) and k != "excluded_sources"]
    if out["excluded_sources"] is None:
        empty.append("excluded_sources")
    # nested values count too: an elasticity dict of Nones is not a saved definition
    for k in ("slope", "p", "n", "label"):
        if out["elasticity"].get(k) in (None, ""):
            empty.append("elasticity." + k)
    if not out["models"].get("ran"):
        empty.append("models.ran")
    win = out.get("data_window")
    if isinstance(win, dict) and not (win.get("start") and win.get("end")):
        empty.append("data_window.start/end")
    path = stem + ".forecast.json"
    return path, out, empty


# ------------------------------------------------------------------------ CLI

def cmd_facts(a):
    rep = check_facts(load_facts(a.facts), Report())
    return rep.emit("FACTS CHECK: " + a.facts)


def cmd_tiers(a):
    f = load_facts(a.facts)
    vendors = f.get("vendors") or []
    has_cost = any(float(v.get("spend") or 0) > 0 for v in vendors)
    rows = []
    for v in vendors:
        tier, rating, note, cps = tier_rule(v.get("spend"), v.get("leads"), v.get("sales"), has_cost)
        rows.append((cps, v, tier, rating, note))
    rows.sort(key=lambda t: (t[0] is None, t[0] if t[0] is not None else 0))
    print("VENDOR ROI ORDER (cost per sale ascending, rows without one last)")
    print("  {:<32} {:>10} {:>7} {:>6} {:>9}  {:<13} {:<13} {}".format(
        "Vendor", "Spend", "Leads", "Sales", "CPS", "Tier", "Rating", "Note"))
    for cps, v, tier, rating, note in rows:
        print("  {:<32} {:>10,.0f} {:>7,.0f} {:>6,.0f} {:>9}  {:<13} {:<13} {}".format(
            str(v.get("vendor"))[:32], float(v.get("spend") or 0), float(v.get("leads") or 0),
            float(v.get("sales") or 0), "-" if cps is None else "${:,.0f}".format(cps),
            tier or "(no cost)", rating or "", note))
    cut = cut_order(vendors)
    print("CUT LIST ORDER (paid lines with leads and 0 sales first, then TIER 4 worst first, then UNMEASURED)")
    for i, v in enumerate(cut, 1):
        print("  {}. {}".format(i, v.get("vendor")))
    if not cut:
        print("  (none)")
    return 0


def cmd_elasticity(a):
    f = load_facts(a.facts)
    try:
        res = elasticity_from_history(f.get("history") or [])
    except ValueError as exc:
        print("elasticity not computable: {}".format(exc), file=sys.stderr)
        return 2
    print("ELASTICITY (log leads on log spend, {} months)".format(res["n"]))
    print("  slope {:.3f}  r {:.2f}  p {:.3f}  SE {:.3f}  95% CI {:.2f} to {:.2f}".format(
        res["slope"], res["r"], res["p"], res["se"], res["ci95"][0], res["ci95"][1]))
    print("  label: {}".format(res["label"]))
    lead = {k: round(res[k], 4) if isinstance(res[k], float) else res[k] for k in ("slope", "r", "p", "se", "n")}
    lead["ci95"] = [round(res["ci95"][0], 4), round(res["ci95"][1], 4)]
    print("  facts: " + json.dumps({"leads": lead, "label": res["label"]}))
    return 0


def cmd_audit(a):
    f = load_facts(a.facts)
    rep = Report()
    prompts = audit_prompts(f, rep)
    conf = f.get("confirmations") or {}
    code = rep.emit("MODEL AUDIT: " + a.facts)
    if code:
        return code
    pending = [(k, p) for k, p in prompts if not conf.get(k)]
    for k, p in prompts:
        if conf.get(k):
            print("  CONFIRMED ({}): {}".format(k, conf.get(k)))
    if pending:
        print("CONFIRM WITH DREW BEFORE BUILDING:")
        for k, p in pending:
            print("  - [{}] {}".format(k, p))
        print("Record his answer in facts.confirmations.{} and re-run.".format(
            " / ".join(sorted(set(k for k, _ in pending)))))
        return 3
    print("AUDIT: no confirmation needed" if not prompts else "AUDIT: all prompts confirmed")
    return 0


def cmd_check(a):
    if not os.path.isfile(a.workbook):
        print("no such workbook: " + a.workbook, file=sys.stderr)
        return 2
    facts = load_facts(a.facts) if a.facts else None
    rep = Report()
    if facts is not None:
        check_facts(facts, rep)
    try:
        wc = WorkbookCheck(a.workbook, facts, rep, strict_labels=facts is not None)
    except Exception as exc:  # unreadable workbook: loud, not silent
        print("cannot open workbook {}: {}".format(a.workbook, exc), file=sys.stderr)
        return 2
    wc.run()
    code = rep.emit("WORKBOOK CHECK: " + a.workbook)
    if a.write_sidecar:
        if facts is None:
            print("--write-sidecar needs --facts", file=sys.stderr)
            return 2
        if code:
            print("sidecar NOT written: fix the failures first")
            return code
        path, data, empty = sidecar(facts, a.workbook)
        if empty:
            print("sidecar NOT written: empty keys " + ", ".join(empty))
            return 1
        with open(path, "w") as fh:
            json.dump(data, fh, indent=2)
        print("SIDECAR: " + path)
    return code


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd")
    for name in ("facts", "tiers", "elasticity", "audit"):
        s = sub.add_parser(name)
        s.add_argument("facts")
    s = sub.add_parser("check")
    s.add_argument("workbook")
    s.add_argument("--facts")
    s.add_argument("--write-sidecar", action="store_true")
    a = p.parse_args(argv)
    if not a.cmd:
        p.print_help()
        return 2
    return {"facts": cmd_facts, "tiers": cmd_tiers, "elasticity": cmd_elasticity,
            "audit": cmd_audit, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
