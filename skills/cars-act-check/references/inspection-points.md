# 110 Inspection Points: CARS Act Exposure Map for a Dealership Website + Ads

Method: `machine` = checks.py rule (regex/DOM/JSON-LD, tagged in config/rules.json). `agent` = Agent B browser judgment (on the Claude Browser, `mcp__Claude_Browser__*`; Chrome extension is the last-resort fallback per SKILL.md) or Agent C ad review. Severity: **C**ritical (direct statutory violation, enforcement bait), **M**ajor (likely violation or missing required disclosure), **m**inor (hygiene/consistency risk). Citations abbreviate Cal. Civ. Code (CC) and Veh. Code (VC); CC 1784.41 holds the disclosures (total price, first communication, payments, add-on optionality), CC 1784.42 the add-on benefit and 10-day payment rules, CC 1784.40 the thirteen misrepresentation categories (letters (a) to (m), CNCDA numbers them 1 to 13). Points 101 to 110 were added 2026-09-14 from the CNCDA Compliance Guide v1.2 and Webinar FAQ; cite as "CNCDA Guide Part N" or "CNCDA FAQ QN". In READINESS mode, report severities unchanged but label as gaps.

## A. Total price in vehicle advertising (CC 1784.41) (pts 1-18)

| # | Point | Method | Sev |
|---|-------|--------|-----|
| 1 | Every VDP displays a total price (not "Call for Price") | machine | C |
| 2 | Every SRP tile showing a specific vehicle shows total price | machine | C |
| 3 | "Call for Price" / "Contact us for price" / "See dealer for price" anywhere on inventory (CNCDA: also fails) | machine | C |
| 4 | Price shown equals JSON-LD offers.price (no teaser mismatch) | machine | M |
| 5 | Advertised price excludes only the VC 11713.1(e) items (taxes, registration, tire fee, certificate fees, finance charges, doc fee, electronic filing, emission testing); includes every installed item and any markup; never reduced by a rebate | agent | C |
| 6 | No rebate of any kind deducted from the total price (CC 1784.31(j)(3)); rebates shown as "Factory Rebate" dollar amounts under the total price with the after-rebate figure labeled "net cost", never "price"; no dealer cash back, no "up to $X", no conflicting stacks | agent | C |
| 7 | Rebate-qualified price carries adjacent qualification language | agent | M |
| 8 | Largest/boldest price on VDP is the total price; MSRP labeled and no more prominent; no "MSRP, not the selling price" disclaimer (CNCDA Guide Part 2) | agent | C |
| 9 | Homepage banners with a specific vehicle + amount show total price | agent | C |
| 10 | Specials pages: every vehicle-specific offer shows total price | machine | C |
| 11 | Lease or payment specials that identify a unit (stock #, VIN, photo) show that unit's total price, not payment only (CNCDA FAQ Q19); class offers identified only by MSRP/model are outside this point | machine | C |
| 12 | Finance specials with APR/term for a specific vehicle include total price | machine | M |
| 13 | Expiration date present on priced offers; the advertised price is a ceiling for anyone while the unit is unsold (VC 11713.1(e); CNCDA "date your offers") | machine | M |
| 14 | Single-vehicle offers list the distinguishing VIN portion or the license number; a stock number alone is not sufficient (VC 11713.1(a); CNCDA Appendix A) | machine | M |
| 15 | Strikethrough "was" prices reflect an actual prior price (no fake discounts) | agent | M |
| 16 | Dealer-installed items included in the total price (itemization optional in the ad, required on the new-vehicle supplemental sticker above MSRP, VC 11713.1(q)); no "pay or remove" or "excludes dealer-installed" wording on an identified unit | agent | C |
| 17 | Price consistent between SRP tile, VDP, and JSON-LD for the same VIN | machine | M |
| 18 | Pre-installed products on every unit are inside the price and not presented as optional, "free", or pay-to-activate; hybrid products carry a real base warranty (CNCDA Guide Part 4, FAQ Q46 to Q48) | agent | C |

## B. Prohibited misrepresentations (CC 1784.40) (pts 19-33)

| # | Point | Method | Sev |
|---|-------|--------|-----|
| 19 | Advertised vehicle actually in inventory feed (availability) | machine | C |
| 20 | Sold/unavailable vehicles delisted within 48 hours | machine | C |
| 21 | "Guaranteed financing" / "everyone approved" claims | machine | C |
| 22 | "Guaranteed trade value" or similar guarantee claims | machine | M |
| 23 | Government affiliation implications (seals, "DMV approved", flag/agency imagery) | agent | C |
| 24 | Sale vs lease clearly distinguished in every offer block | machine | M |
| 25 | Payment ads state whether figures are purchase or lease | machine | M |
| 26 | Down payment / trade application described accurately in offers | agent | M |
| 27 | No claims that deposits/trades are non-refundable pre-contract | machine | M |
| 28 | Financing-approval language doesn't promise outcomes ("you're approved!") | machine | M |
| 29 | No misstatements about buyer remedies if advertised price not honored | agent | m |
| 30 | Export/out-of-state restriction language accurate if present | agent | m |
| 31 | Repossession-related claims (e.g. "we can't repo if...") absent/accurate | machine | m |
| 32 | "Free" offers genuinely free (no cost recouped elsewhere), VC 11713.1 | agent | M |
| 33 | Chat widget scripted answers don't misstate price, availability, or terms | agent | M |

## C. First written communication (CC 1784.41(a)(3)) (pts 34-42)

| # | Point | Method | Sev |
|---|-------|--------|-----|
| 34 | Lead-form autoresponder either merges the total price or is a bare administrative receipt with no vehicle reference, marketing, or credit invitation (CNCDA FAQ Q23) | agent | C |
| 35 | CRM first-touch email templates carry the total price merge field | agent | C |
| 36 | First-touch SMS templates carry the total price; SMS opt-in and consent messages carry consent language only (CNCDA FAQ Q24) | agent | C |
| 37 | Chat-to-lead handoff transcripts preserved to CRM (retention chain) | agent | M |
| 38 | Trade/down-payment application language present when those are referenced | agent | M |
| 39 | Website "get e-price" flows return the actual total price in the message body, not a bait step or a link-only reply (CNCDA FAQ Q26) | agent | C |
| 40 | Digital retailing tool shows the total of payments and assumed consideration next to any payment, and dealer-sent messages through it carry the full disclosures (CNCDA FAQ Q27, Q40) | agent | C |
| 41 | No first-touch template quotes payments without total-amount disclosure | agent | C |
| 42 | Templates exist per lead source (form, chat, phone-to-text, 3rd party, broker); AI chat states the total price on the next substantive reply after a unit is named (CNCDA FAQ Q25, Q36) | agent | M |

## D. Monthly payment and financing disclosures (CC 1784.41(c), (d)) (pts 43-52)

| # | Point | Method | Sev |
|---|-------|--------|-----|
| 43 | Payment displayed anywhere → total amount to be paid disclosed | machine | C |
| 44 | Extended-term payment comparisons disclose the longer term | machine | C |
| 45 | Payment calculators output total-of-payments and assumed consideration, not payment only (consumer use is exempt, but CNCDA recommends configuring it anyway, FAQ Q40) | agent | M |
| 46 | APR quoted with required conditions (OAC language present) | machine | M |
| 47 | Lease payments show due-at-signing, term, mileage, disposition basics | machine | M |
| 48 | Lease disclaimer math internally consistent (payment × term + DAS ≈ stated totals) | machine | M |
| 49 | "0% financing" offers disclose eligibility/credit qualification | machine | M |
| 50 | Balloon/deferred payment structures fully disclosed | agent | M |
| 51 | Payment-match or "we'll beat your payment" claims qualified | machine | m |
| 52 | Financing terms in banners match the linked VDP/specials detail | agent | M |

## E. Add-on products (CC 1784.41(b), CC 1784.42) (pts 53-64)

| # | Point | Method | Sev |
|---|-------|--------|-----|
| 53 | Add-on/protection pages state products are optional | machine | C |
| 54 | Accessory/protection pricing pages state the vehicle can be bought without them | machine | C |
| 55 | No prohibited add-ons advertised: EV oil changes | machine | C |
| 56 | No nitrogen tire product without 95% purity basis | machine | M |
| 57 | No cat-converter marking marketed for EVs/vehicles without converters; marking itself is a benefit (VC 24020), a bundled theft-reimbursement benefit is an insurance question (CNCDA FAQ Q49) | machine | M |
| 58 | GAP marketing references ASFA-compliant terms | agent | M |
| 59 | Service contract marketing doesn't cover void-by-preexisting-condition products | agent | M |
| 60 | Surface protection claims don't void factory paint warranty | agent | m |
| 61 | F&I menu pages (if public) show optional status per product | agent | M |
| 62 | Spanish-language add-on disclosures exist if site negotiates in Spanish (CC 1632) | agent | M |
| 63 | Pre-loaded accessories ("all vehicles equipped with...") are inside the total price; a device deactivated when the customer declines fails the benefit test (CNCDA FAQ Q47) | agent | C |
| 64 | Digital retailing add-on step defaults to NOT pre-selected | agent | C |

## F. Three-day right to cancel (CC 1784.43) (pts 65-76)

| # | Point | Method | Sev |
|---|-------|--------|-----|
| 65 | Old "California has no cooling-off period" copy, the repealed two-day purchased option, 72-hour option, or $40,000 threshold removed (CNCDA FAQ Q56, Q57) | machine | C |
| 66 | Used-vehicle pages ≤ $50k (purchase price or capitalized cost) reference the 3-day right accurately: period from execution, closed-day extension, fee out of the refund first (post 10/1) | machine | M |
| 67 | No language selling the right to cancel as a paid product | machine | C |
| 68 | Restocking fee described within 1.5% / $200 floor / $600 cap | machine | M |
| 69 | Mileage limits stated accurately (400-mile window, $1/mile over 250, $150 cap) | machine | M |
| 70 | Return policy page (if any) consistent with statute; any more generous store policy also appears in the cancellation disclosure and signage (CNCDA FAQ Q55) | agent | M |
| 71 | FAQ/chat answers about returns match statutory terms | agent | M |
| 72 | No disclaimers waiving the right (rights are non-waivable, CC 1784.20 et seq.) | machine | C |
| 73 | Trade-in return obligations not contradicted on trade pages | agent | m |
| 74 | Contract sample/e-sign flows include statutory cooling-off notice verbatim | agent | C |
| 75 | Separate 3-day disclosure document exists in the deal pack (ask client, record answer) | agent | M |
| 76 | Showroom signage plan updated: 36-point physical notice in each sales office and cubicle where written terms are discussed and each contract room, Reynolds stock (flag for client confirmation, can't verify remotely) | agent | m |

## G. Recordkeeping and retention (CC 1784.44) (pts 77-84)

| # | Point | Method | Sev |
|---|-------|--------|-----|
| 77 | This run's ad/page snapshot archived to Drive (self-check) | machine | C |
| 78 | Retention manifest shows unbroken monthly coverage | machine | M |
| 79 | First-communication templates archived with version dates | agent | M |
| 80 | CRM retention settings hold comms ≥ 2 years, inbound and outbound, exportable by customer and stock number; migration export rule in place (ask client once, record) | agent | M |
| 81 | Text/SMS platform archives price communications; written policy routes personal phones through a CRM-managed app (CNCDA FAQ Q33) | agent | M |
| 82 | Chat transcripts retained and exportable | agent | M |
| 83 | Prior snapshots ≥ 24 months never pruned (self-check) | machine | M |
| 84 | Complaint intake path exists on site (contact route that can be logged) | machine | m |

## H. Site surfaces and operational exposure (pts 85-100)

| # | Point | Method | Sev |
|---|-------|--------|-----|
| 85 | Sitemap inventory URLs all resolve 200 (stale listing risk) | machine | M |
| 86 | 3rd-party listing profiles (Cars.com/CarGurus/Autotrader/Edmunds/TrueCar) and OEM locator show the same total price as the site; program discounts shown separately under it; scraped or OEM-controlled discrepancies documented with a written correction request (CNCDA FAQ Q12 to Q15) | agent | M |
| 87 | Meta ad creatives with vehicle + amount include total price or land on it in one click | agent | C |
| 88 | Google ad copy with payments/prices matches landing page totals | agent | C |
| 89 | Craigslist/marketplace posts (if used) carry compliant pricing | agent | m |
| 90 | Email blast templates (marketing) include total price for featured vehicles | agent | M |
| 91 | Social posts featuring an identified unit or a payment, including employee personal accounts, include the total price and Vehicle Code disclosures; written social media policy exists (CNCDA FAQ Q20) | agent | M |
| 92 | Site search results pages don't render price-free vehicle cards | machine | m |
| 93 | Mobile rendering keeps disclosures visible (not clipped/hidden) | agent | M |
| 94 | Disclaimer text not styled illegibly (tiny/low-contrast) | agent | M |
| 95 | Disclaimers load without JS dependence (crawlable = archivable) | machine | m |
| 96 | 404/expired specials redirect cleanly (no zombie offers cached) | machine | m |
| 97 | Doc fee stated consistently sitewide at the legal cap ($85 with a DMV partner agreement, $70 otherwise); if shown per the FTC posture, as "not a governmental fee" with a DPC-inclusive price, never "out-the-door" | machine | M |
| 98 | OEM co-op offer language matches brand program rules (overlay via brand-check skill) | agent | m |
| 99 | Sold-unit "similar vehicles" widgets don't display dead offers with prices | machine | m |
| 100 | Footer/legal page references CARS Act rights accurately (post 10/1) | machine | m |

## I. CNCDA guidance addendum (pts 101-110, added 2026-09-14)

| # | Point | Method | Sev |
|---|-------|--------|-----|
| 101 | Statutory Plus Disclosure appears verbatim, no abbreviations, on every page displaying a vehicle price (VC 11713.1(c)(2); CNCDA Guide Part 2); doc-fee reference dropped only where the doc fee is inside the price | machine | M |
| 102 | No "MSRP is not the selling price" / "price shown is MSRP" / MSRP-only presentation for a specific vehicle (CC 1784.41(a); CNCDA Appendix D Ex. 3, FAQ Q4) | machine | C |
| 103 | No price CTA ("See price and payments", "Unlock savings", "Get ePrice", QR-scan-for-price) standing in place of the total price on a specific-vehicle page (CNCDA FAQ Q6, Q10) | machine | C |
| 104 | No installed-item exclusion or pay-or-remove wording on an identified unit ("excludes dealer-installed accessories", "may be purchased for an additional cost or removed at the customer's option", "does not apply to vehicles with dealer-added options") (CC 1784.31(j)(2); CNCDA Appendix D Ex. 1) | machine | C |
| 105 | Addendum or supplemental sticker used only for installed equipment, every item in the total price, no $0 optional-products addendum, never on a used vehicle, mark-up labeled on new units above MSRP (VC 11713.1(q); CNCDA FAQ Q3, Q5, Q21) | machine | M |
| 106 | Rebate presentation follows Total Price / Factory Rebate / Net Cost; no dealer cash back, "up to" rebates, or conflicting stacks; group-limited eligibility adjacent (CNCDA Appendix D Ex. 2) | machine | M |
| 107 | Pre-installed device and hybrid product structures reviewed: physical component in the price with a real base warranty, upgrade optional, hardware not "free" when recovered through a subscription, no deactivate-on-decline, penetration monitored (CNCDA Guide Part 4, FAQ Q46 to Q48) | machine | M |
| 108 | Every priced offer carries an expiration date so the ceiling rule (VC 11713.1(e)) has an end; CRM templates dated the same way | machine | M |
| 109 | Program or member pricing (TrueCar, Costco Auto Program) shown as a separate conditional discount under the same total price, not as a lower vehicle price (CC 1784.41(f); CNCDA FAQ Q12) | machine | m |
| 110 | No "out-the-door" label on any figure that excludes taxes and government fees; where the store adopts the FTC posture, the DPC line reads "not a governmental fee" and the DPC-inclusive price gets equal prominence (CNCDA Appendix D federal panels) | machine | M |

Agent-only items CNCDA raised that fold into existing points rather than new ones: class ads with "starting at" need the quantity disclosure adjacent to the price and VINs when four or fewer units (pt 14 and pt 5); the digital retailing tool's opening price must match the VDP (pt 40, pt 86); multi-pencil worksheets and F&I menus carry the optionality statement at first written presentation, the OPD documents it at signing (pt 61); the Failure Notice, Acknowledgment, and Cancellation Disclosure are audited on a recurring basis at the store (pt 75, ask-client item); vendor readiness letters and OEM written notices for preselected vendors (pt 80, ask-client item).

## Severity handling

- **C**: above-the-fold in the report and in the final message to Drew. Same-day fix framing in ENFORCEMENT mode.
- **M**: fix-this-week framing, grouped by page template so one CMS fix clears many findings.
- **m**: appendix, tracked for trend only.

Points marked "ask client" become a standing questionnaire section in the report until answered; answers persist in `$STATE/client-answers.json` and stop re-asking.
