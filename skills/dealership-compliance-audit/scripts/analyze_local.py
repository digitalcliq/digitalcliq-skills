#!/usr/bin/env python3
"""
analyze_local.py — AI-review payload builder.

The deterministic compliance checks (privacy, pricing, Reg M/Z, CARS Act,
brand identity, the 9 CA frameworks) ALL live in `checks/registry.py` now and
run through `verify_loop.py`, which gives every one of them the false-positive-
killing re-crawl loop. This script no longer duplicates any of that.

Its single remaining job: read the crawl data and emit a small, filtered
payload of genuine GRAY-AREA items (prominence/visual judgment, rebate stacking,
sale substantiation, financial-incentive gating, CARS-Act add-on presentation,
and the visual brand rules) for the ONE cloud judgment agent. Keeping this
payload tiny is what keeps the audit's token cost down.

Zero cloud API calls. Python 3.9+, stdlib only.
"""

import argparse
import json
import re
from pathlib import Path


# ── Helpers ──────────────────────────────────────────────────

def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


def safe_get(data, *keys, default=None):
    """Safely traverse nested dicts/lists."""
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key, default)
        elif isinstance(current, list) and isinstance(key, int) and key < len(current):
            current = current[key]
        else:
            return default
        if current is None:
            return default
    return current


def get_page_text(page_data):
    """Combine all searchable text from a page data dict."""
    parts = []
    for key in ("text_excerpt", "page_text_excerpt"):
        if page_data.get(key):
            parts.append(page_data[key])
    for d in page_data.get("disclaimers", []):
        if isinstance(d, str):
            parts.append(d)
    return "\n".join(parts)


def iter_pages(crawl_data):
    """Yield (page_key, page_data, combined_text) for all valid pages."""
    for page_key, page_data in crawl_data.get("pages", {}).items():
        if not page_data or page_data.get("error"):
            continue
        combined = get_page_text(page_data)
        if combined:
            yield page_key, page_data, combined


# ── AI Review Items Builder ──────────────────────────────────

def build_ai_review_items(crawl_data, brand, brand_rules):
    """Build filtered payload for the single AI judgment agent."""
    pages = crawl_data.get("pages", {})
    items = []

    # 1. Clear & conspicuous + disclaimer adequacy + payment advertising
    for pk in ("specials", "homepage"):
        pd = pages.get(pk, {})
        if not pd or pd.get("error"):
            continue
        disclaimers = pd.get("disclaimers", [])
        if disclaimers or pd.get("has_lease_offers", False):
            items.append({
                "review_type": "clear_and_conspicuous",
                "judgment_criteria": [1, 3, 6],
                "page_key": pk,
                "page_url": pd.get("url", ""),
                "context": f"Page has {len(disclaimers)} disclaimers. Evaluate clarity, prominence, and payment disclosure adequacy.",
                "disclaimers": disclaimers[:10],
                "prices": pd.get("prices_found", []) or pd.get("lease_payments", []),
                "text_first_2000": (pd.get("text_excerpt", "") or "")[:2000],
            })

    # 2. Rebate stacking
    rebate_pat = re.compile(r'(?:rebate|incentive|bonus\s*cash|conquest|loyalty|military|college\s*grad|trade\s*assist)', re.I)
    for pk in ("specials", "homepage", "vdp"):
        pd = pages.get(pk, {})
        if not pd or pd.get("error"):
            continue
        text = get_page_text(pd)
        mentions = rebate_pat.findall(text)
        if len(set(m.lower() for m in mentions)) >= 2:
            items.append({
                "review_type": "rebate_stacking",
                "judgment_criteria": [4],
                "page_key": pk,
                "page_url": pd.get("url", ""),
                "context": f"Multiple rebate types found ({len(set(mentions))} unique). Evaluate stacking disclosure.",
                "rebate_terms": list(set(m.lower() for m in mentions)),
                "text_first_3000": text[:3000],
            })

    # 3. Sale/savings language
    sale_pat = re.compile(r'\b(?:sale|clearance|blowout|liquidation|save\s*\$|savings|off\s*MSRP)\b', re.I)
    for pk, pd, text in iter_pages(crawl_data):
        if sale_pat.search(text):
            items.append({
                "review_type": "sale_savings",
                "judgment_criteria": [5],
                "page_key": pk,
                "page_url": pd.get("url", ""),
                "context": "Sale/savings language found. Evaluate dates, reference prices, substantiation.",
                "text_first_2000": text[:2000],
            })

    # 4. Lease due-at-signing accuracy
    for pk in ("specials", "homepage"):
        pd = pages.get(pk, {})
        if not pd or pd.get("error"):
            continue
        text = get_page_text(pd)
        if re.search(r'due\s*at\s*(?:signing|lease)', text, re.I):
            items.append({
                "review_type": "lease_due_at_signing",
                "judgment_criteria": [7],
                "page_key": pk,
                "page_url": pd.get("url", ""),
                "context": "Lease due-at-signing language found. Evaluate accuracy and prominence.",
                "disclaimers": pd.get("disclaimers", [])[:10],
                "text_first_3000": text[:3000],
            })

    # 5. Vehicle condition claims
    cond_pat = re.compile(r'\b(?:clean\s*title|no\s*accidents?|like\s*new|pristine|excellent\s*condition|perfect\s*condition)\b', re.I)
    for pk in ("used", "vdp"):
        pd = pages.get(pk, {})
        if not pd or pd.get("error"):
            continue
        text = get_page_text(pd)
        if cond_pat.search(text):
            items.append({
                "review_type": "vehicle_condition",
                "judgment_criteria": [8],
                "page_key": pk,
                "page_url": pd.get("url", ""),
                "context": "Vehicle condition claims found. Evaluate substantiation.",
                "text_first_2000": text[:2000],
            })

    # 6. Financial incentive / data-for-price (CCPA)
    price_gate = re.compile(r'(?:get\s*(?:your\s*)?(?:e[\s-]?price|internet\s*price)|unlock\s*price|submit.*?price|see\s*price)', re.I)
    hp = pages.get("homepage", {})
    if hp and not hp.get("error"):
        text = get_page_text(hp)
        lead_forms = safe_get(hp, "privacy", "lead_forms_have_privacy_notice", default=[])
        if price_gate.search(text) or lead_forms:
            items.append({
                "review_type": "financial_incentive",
                "judgment_criteria": [11],
                "page_key": "homepage",
                "page_url": hp.get("url", ""),
                "context": f"Site has {len(lead_forms)} lead form(s). Evaluate pricing gated behind PI submission (CCPA financial incentive).",
                "lead_forms": lead_forms,
                "has_price_gating": bool(price_gate.search(text)),
                "text_first_2000": text[:2000],
            })

    # 7. CARS Act — add-on presentation & cancellation disclosure (judgment criteria 12-15)
    used_pd = pages.get("used", {})
    if used_pd and not used_pd.get("error"):
        used_text = get_page_text(used_pd)
        items.append({
            "review_type": "cars_act_cancellation",
            "judgment_criteria": [13, 15],
            "page_key": "used",
            "page_url": used_pd.get("url", ""),
            "context": "CARS Act (SB 766, operative Oct 1, 2026): Evaluate whether used vehicle pages "
                       "reference the 3-day cancellation right, and whether any terms/policies conflict "
                       "with or attempt to waive CARS Act consumer protections.",
            "text_first_3000": used_text[:3000],
        })

    addon_review_pat = re.compile(
        r'\b(?:protection\s*package|service\s*contract|GAP|gap\s*waiver|'
        r'extended\s*warranty|nitrogen|paint\s*protection|theft\s*deterrent|'
        r'maintenance\s*plan|surface\s*protection)\b',
        re.IGNORECASE
    )
    for pk in ("specials", "homepage", "finance", "vdp"):
        pd = pages.get(pk, {})
        if not pd or pd.get("error"):
            continue
        text = get_page_text(pd)
        if addon_review_pat.search(text):
            items.append({
                "review_type": "cars_act_addons",
                "judgment_criteria": [12],
                "page_key": pk,
                "page_url": pd.get("url", ""),
                "context": "CARS Act (SB 766, operative Oct 1, 2026): Evaluate whether add-on products "
                           "are presented as optional with clear 'not required' disclosure, or if the "
                           "presentation implies they are mandatory. Also check for valueless add-ons "
                           "(e.g., oil changes on EVs).",
                "text_first_3000": text[:3000],
            })
            break  # one review item is sufficient

    # 7b. FTC Pricing Transparency FAQs, Sept. 2026 (judgment criterion 18).
    # Prominence and placement cannot be judged from regex, so every priced
    # inventory surface goes to the judgment agent once.
    ftc_amount_pat = re.compile(r'\$\s?\d[\d,]{2,}', re.I)
    ftc_signal_pat = re.compile(
        r'msrp|you\s*save|your\s*price|price\s*you.?ll|rebate|discount|incentive|financ|'
        r'in[\s-]*transit|arriving|in\s*production|off[\s-]*site|stock\s*(?:photo|image)|'
        r'representative\s*(?:photo|image)|illustration|doc(?:ument)?\s*(?:processing\s*)?(?:fee|charge)|due\s*at\s*signing',
        re.I)
    for pk, pd, text in iter_pages(crawl_data):
        if not (pk.startswith("vdp") or pk in ("vlp", "specials", "used", "cpo", "homepage")):
            continue
        if not ftc_amount_pat.search(text):
            continue
        signals = sorted({m.lower() for m in ftc_signal_pat.findall(text)})
        items.append({
            "review_type": "ftc_pricing_transparency",
            "judgment_criteria": [18],
            "page_key": pk,
            "page_url": pd.get("url", ""),
            "context": "FTC Pricing Transparency FAQs (Sept. 2026, staff views, federal and current): is the "
                       "all-in price the most prominent amount by size AND placement; are conditional discounts "
                       "outside it; doc fee inside it at the highest amount (California: DPC-inclusive price most "
                       "prominent); due-at-signing includes upfront fees; not-on-lot units labeled; used listings "
                       "use actual photos. Cite FAQ question numbers.",
            "signals": signals[:15],
            "disclaimers": pd.get("disclaimers", [])[:10],
            "text_first_3000": text[:3000],
        })

    # 8. Visual/contextual brand assessments (non-automatable)
    brand_checks = brand_rules.get("checks", [])
    auto_categories = {"certified pre-owned"}  # handled by the registry
    remaining_ids = [
        c["id"] for c in brand_checks
        if c.get("category", "").lower() not in auto_categories
    ]
    if remaining_ids:
        page_excerpts = {}
        for pk, pd in pages.items():
            if not pd or pd.get("error"):
                continue
            page_excerpts[pk] = {
                "url": pd.get("url", ""),
                "title": pd.get("title", ""),
                "text_first_1500": (pd.get("text_excerpt", "") or
                                     pd.get("page_text_excerpt", "") or "")[:1500],
                "disclaimers": pd.get("disclaimers", [])[:5],
            }
        items.append({
            "review_type": "brand_visual_contextual",
            "judgment_criteria": "brand_guidelines",
            "brand": brand,
            "brand_rule_ids": sorted(remaining_ids),
            "context": f"Evaluate {len(remaining_ids)} brand rules requiring visual/contextual judgment. "
                       "Skip rules already covered by the registry (FCA naming, Fiat branding, CPO page, "
                       "brand in titles, model name order, GM Financial attribution).",
            "page_excerpts": page_excerpts,
        })

    return items


# ── Main ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AI-review payload builder (deterministic checks live in checks/registry.py)"
    )
    parser.add_argument("--crawl", required=True, help="Path to crawl data JSON")
    parser.add_argument("--brand", required=True, help="Brand: bmw, nissan, cdjr, chevrolet, harley")
    parser.add_argument("--rules", required=False, help="(unused; kept for CLI compatibility)")
    parser.add_argument("--brand-rules", required=True, help="Path to brand guidelines JSON")
    parser.add_argument("--out-ai-review", default=None, help="Output: AI review items JSON")
    args = parser.parse_args()

    crawl_stem = Path(args.crawl).stem
    client_prefix = crawl_stem.replace("_crawl_data", "")
    if not args.out_ai_review:
        args.out_ai_review = f"/tmp/{client_prefix}_ai_review_needed.json"

    crawl_data = load_json(args.crawl)
    brand_rules = load_json(args.brand_rules)

    page_count = len([k for k, v in crawl_data.get("pages", {}).items()
                       if v and not (isinstance(v, dict) and v.get("error"))])
    print(f"[Local] Loaded crawl data: {page_count} valid pages")
    print(f"[Local] Loaded {len(brand_rules.get('checks', []))} brand checks")

    ai_items = build_ai_review_items(crawl_data, args.brand, brand_rules)
    print(f"[Local] AI review items: {len(ai_items)} items for cloud evaluation")

    with open(args.out_ai_review, "w") as f:
        json.dump({
            "client": crawl_data.get("client", ""),
            "brand": args.brand,
            "url": crawl_data.get("url", ""),
            "crawl_date": crawl_data.get("crawl_date", ""),
            "note": "Deterministic findings come from verify_loop.py (checks/registry.py). "
                    "These are gray-area judgment items only.",
            "items": ai_items,
        }, f, indent=2)
    print(f"[Local] Wrote AI review → {args.out_ai_review}")


if __name__ == "__main__":
    main()
