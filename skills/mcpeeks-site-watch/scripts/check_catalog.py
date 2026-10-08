#!/usr/bin/env python3
"""GM-language catalog for the 25 McPeek's Site Watch checks (C22 to C24 added 2026-09-14 from the CNCDA CARS Act Compliance Guide v1.2 and Webinar FAQ; C25 and the FTC wording in C02, C03, C06, C12, C22 added 2026-10-08 from the FTC Pricing Transparency FAQs of September 2026 and the FTC staff remarks of 2026-09-30).

Shared by report.py (run summary) and build_workbook.py (Excel deliverable).
Every entry is written for a dealership General Manager, not a developer:
what we look at, why it matters to the store, who fixes it, and the fix.

Wording rule: never use the word "placeholder" anywhere in this file. The
shared post_flight.py validator treats that word as unfilled template text
and fails the workbook.
"""

# Area labels are the three buckets a GM cares about, plus the manual bucket.
AREA_LEGAL = "Legal & Pricing"
AREA_ACCURACY = "Inventory Accuracy"
AREA_HEALTH = "Site Health & Privacy"
AREA_PHONE = "Phones"

SEVERITY_TO_AREA = {
    "compliance": AREA_LEGAL,
    "data_accuracy": AREA_ACCURACY,
    "hygiene": AREA_HEALTH,
    "contact": AREA_PHONE,
}
AREA_ORDER = [AREA_LEGAL, AREA_ACCURACY, AREA_HEALTH, AREA_PHONE]

# Fix owners. Keep these names stable; they appear in the "Who fixes it" column.
OWNER_SITE = "Pixel Motion (website vendor)"
OWNER_CONSENT = "ComplyAuto + tag manager admin"
OWNER_INVENTORY = "Inventory manager / photo vendor"
OWNER_DESKING = "Desking / F&I manager"
OWNER_DOMAINS = "Domain registrar / IT"
OWNER_PHONES = "Dealer phone admin (CallRevu)"
OWNER_DCLIQ = "DigitalCLIQ"

CATALOG = {
    "C01": dict(
        name="Rebates subtracted from the advertised price",
        area=AREA_LEGAL, weight=100,
        what="New-vehicle pages that show only the price after factory rebates, with no pre-rebate selling price on the page.",
        why="California taxes and regulates the pre-rebate price, and from October 1, 2026 the CARS Act says the advertised total price may not be reduced by any rebate at all (Civ. Code 1784.31(j)(3)). CNCDA's compliant pattern is Total Price, then Factory Rebate as a dollar amount, then a figure labeled Net Cost, never Price. The FTC adds that a rebate not every buyer qualifies for cannot be deducted from the most prominent price. This is the single largest legal exposure on the site and the first thing a DMV investigator or plaintiff attorney looks for.",
        owner=OWNER_SITE,
        fix="Change the VDP pricing box template so the pre-rebate Total Price is the prominent figure, each rebate itemized underneath as a specific dollar amount with its qualification and expiration, and the after-rebate figure labeled Net Cost. Never use dealer cash back, up-to rebate ranges, or stacked rebates a buyer cannot combine. One template change fixes every vehicle at once.",
    ),
    "C02": dict(
        name="Doc fee excluded from the advertised price",
        area=AREA_LEGAL, weight=95,
        what="Disclaimer language that says the advertised price is 'plus doc fee' or similar.",
        why="The FTC's written Pricing Transparency FAQs (September 2026, Q6 and Q7) say the most prominent advertised price must include the full doc fee, at the highest amount any buyer is charged; the FTC's own example is a $40,000 car with an $85 doc fee advertised as $40,085, and state doc-fee rules do not change that. FTC staff added on September 30, 2026 that the electronic filing and emission testing charges follow the same test: if the state does not require the customer to pay them but the store does, they belong in the price too. California law and the CARS Act keep all three outside the total price, so the two rules pull apart here. CNCDA's answer is to show both: the Total Price, the doc fee on its own line marked not a governmental fee, and a price including the doc fee, never labeled out-the-door. The FTC enforces this now, with no grace period, and sent warning letters to 97 dealer groups in March 2026 on exactly this pattern.",
        owner=OWNER_SITE,
        fix="Replace the 'plus doc fee' wording with CNCDA's dual presentation on every VDP: Total Price, then Document processing charge (not a governmental fee), then Price including document processing charge, with that last figure the biggest price on the page (the FTC asks for most prominent, not merely equal). Fold the electronic filing and emission testing charges into that inclusive figure as well, or absorb them. If the store folds the doc fee into the advertised price instead, drop the doc fee reference from the fee disclaimer so it is not misleading.",
    ),
    "C03": dict(
        name="All-in price is not the biggest number on the page",
        area=AREA_LEGAL, weight=90,
        what="Whether the largest, boldest price on the vehicle page is the all-in selling price, or an MSRP / post-rebate teaser instead.",
        why="Regulators judge prominence by what the shopper sees first. The FTC's September 2026 FAQs (Q4 and Q5) say every page that states any amount, search results included, must show the actual price as the most prominent figure, and that placement counts as much as font size: a smaller MSRP or savings number sitting where the eye lands first defeats a larger price, and labels like 'the price you'll get' next to both numbers are confusing. A big teaser price with the real price in small type is the classic drip-pricing pattern the FTC targets. The CARS Act adds that MSRP may appear only if it is labeled as MSRP and shown no more prominently than the dealer's total price; MSRP-only pricing and an MSRP figure with a not-the-selling-price disclaimer both fail (CNCDA Guide Part 2).",
        owner=OWNER_SITE,
        fix="Adjust the VDP and search-results price styling so the all-in selling price renders largest, boldest, and first in the price block; MSRP, savings, payments, and conditional prices render smaller and below it, each with a plain label.",
    ),
    "C04": dict(
        name="Required fee disclaimer missing or changed",
        area=AREA_LEGAL, weight=85,
        what="Whether each vehicle page carries the statutory fee disclaimer word for word: Plus government fees and taxes, any finance charges, any dealer document processing charge, any electronic filing charge, and any emission testing charge.",
        why="Vehicle Code 11713.1(c)(2) requires this exact sentence, with no abbreviations, on every web page that displays a vehicle price, and CNCDA confirms it survives the CARS Act unchanged. A missing, shortened, or reworded disclaimer removes the store's defense that fees were disclosed.",
        owner=OWNER_SITE,
        fix="Restore the statutory sentence verbatim in the VDP template. If the store decides to fold the doc fee into the advertised price, remove the doc fee reference from the sentence so it is not misleading. Give DigitalCLIQ the exact approved wording so future runs check it word for word.",
    ),
    "C05": dict(
        name="Payment shown without finance terms",
        area=AREA_LEGAL, weight=85,
        what="A monthly payment on the page with no APR, term, or down payment disclosure next to it.",
        why="A payment amount is a Regulation Z trigger term. Showing it without the full credit terms is a federal violation on its own. From October 1, 2026 the CARS Act also requires the vehicle's total price on any page that states a payment for an identified unit, and the total the customer will have paid after all scheduled payments whenever a payment is put in writing during negotiation (Civ. Code 1784.41(a)(2), (c)).",
        owner=OWNER_SITE,
        fix="Attach the APR, term, and down-payment disclosure to every payment figure, keep the vehicle's total price on the same page, and show the total of payments and any assumed down payment or trade value next to the payment, or remove the payment from the page.",
    ),
    "C06": dict(
        name="'Call for Price' or no price on the page",
        area=AREA_LEGAL, weight=92,
        what="Vehicle pages that show no price at all, or the words 'Call for Price'.",
        why="From October 1, 2026 the CARS Act requires the total price in any advertisement that references a specific vehicle (Civ. Code 1784.41(a)(1)); CNCDA says Contact Dealer for Price fails and a button that stands in place of the price (See Price, Unlock Savings, Get ePrice) is the online version of Call for Price. FTC staff said on September 30, 2026 that a Get My Price or Call for Price button may sit beside a displayed price, but only if it does not suggest a lower price is waiting when it is not, and does not hide or contradict the price shown. Store policy is never to list a vehicle without a price, and unpriced units are dropped by Google Vehicle Ads and the listing sites, so they cost leads as well as risk.",
        owner=OWNER_INVENTORY,
        fix="Price the unit in the DMS feed, or pull it from the live site until it is priced and photographed.",
    ),
    "C07": dict(
        name="Used price with no expiration date",
        area=AREA_LEGAL, weight=70,
        what="Used-vehicle prices that carry no price-expiration language.",
        why="Vehicle Code 11713.1(e) makes the advertised price a ceiling: while the unit is unsold the store must sell at or below it to anyone, whether or not they saw the ad, unless the ad carried an expiration date that has passed. CNCDA tells dealers to date every price ad and every CRM template. Without a date, a shopper can demand last month's price on a unit that has since been repriced.",
        owner=OWNER_SITE,
        fix="Add the standard 'price valid through' or 'expires' line to the used-vehicle disclaimer template.",
    ),
    "C08": dict(
        name="Disclaimer does not match the offer, or is far too long",
        area=AREA_LEGAL, weight=75,
        what="Due-at-signing or payment figures in the disclaimer that disagree with the summary box, and disclaimers so long nobody can read them.",
        why="A disclaimer that contradicts the offer is worse than none: it proves the store published two different deals. Unreadably long fine print gets no credit as disclosure.",
        owner=OWNER_DESKING,
        fix="Reconcile the special's summary figures and disclaimer, then trim the disclaimer to the elements the law requires.",
    ),
    "C09": dict(
        name="Lease payment does not match the program math",
        area=AREA_ACCURACY, weight=65,
        what="The advertised lease payment recomputed against the current money factor, residual, and term for that model.",
        why="A payment that cannot be desked is a bait-and-switch complaint waiting to happen, and it wastes the sales floor's time on deals that fall apart.",
        owner=OWNER_DESKING,
        fix="Update the payment on the special, or send DigitalCLIQ the current program sheet so the check uses this month's numbers.",
    ),
    "C10": dict(
        name="Current-model new vehicle with no lease payment",
        area=AREA_ACCURACY, weight=55,
        what="New current-model-year units whose page shows no lease payment at all.",
        why="Shoppers on lease-heavy CDJR models filter by payment. A unit with no payment is invisible to them, so this is lost lead volume, not a legal issue.",
        owner=OWNER_SITE,
        fix="Confirm the payment feed maps to every current-model trim; where a trim has no program, show the finance payment instead.",
    ),
    "C11": dict(
        name="Aged unit still at MSRP, or savings math wrong",
        area=AREA_ACCURACY, weight=60,
        what="New units on the site more than 90 days with no discount, and pages where MSRP minus selling price does not equal the advertised savings.",
        why="Aged inventory at sticker signals nobody is managing the page, and wrong savings math is an easy false-advertising claim.",
        owner=OWNER_DESKING,
        fix="Reprice aged units, and fix the savings line in the feed so it equals discount plus rebates.",
    ),
    "C12": dict(
        name="Photo missing, stock 'Image Coming Soon' graphic, or wrong vehicle",
        area=AREA_ACCURACY, weight=58,
        what="Pages with two or fewer photos, the vendor's 'Image Coming Soon' graphic, or a hero photo that does not match the year, make, model, and color.",
        why="Units without real photos convert at a fraction of the rate and get suppressed by the listing sites. A wrong photo invites a misrepresentation complaint, and the FTC's September 2026 FAQs (Q11) say a stock or representative photo is acceptable only on a new or in-transit unit that truly matches in make, model, condition, and equipment; used-car shoppers expect the photo to be the exact car, so a stock image on a used listing is a deception risk on its own.",
        owner=OWNER_INVENTORY,
        fix="Shoot and upload photos for every flagged VIN, and pull units that cannot be photographed this week from the live feed.",
    ),
    "C13": dict(
        name="No 360 / spin media",
        area=AREA_ACCURACY, weight=30,
        what="Vehicle pages with no Impel / SpinCar 360 media.",
        why="The store pays for the spin product; units without it are paid-for coverage not being used.",
        owner=OWNER_INVENTORY,
        fix="Confirm the spin capture schedule covers every new arrival within its first week on the lot.",
    ),
    "C14": dict(
        name="Page speed regressed",
        area=AREA_HEALTH, weight=40,
        what="Google Lighthouse scores for the home page, a search page, and a vehicle page, compared with the previous run.",
        why="Slow pages lose mobile shoppers before the price loads and drag down Google Ads quality scores, which raises cost per click.",
        owner=OWNER_SITE,
        fix="Send the regressed page and score to Pixel Motion; the usual causes are an added tag or an unoptimized hero image.",
    ),
    "C15": dict(
        name="Unapproved or new third-party scripts",
        area=AREA_HEALTH, weight=50,
        what="Every outside script loading on the site, compared with the approved vendor list and the previous run.",
        why="Each unknown script is a vendor you may be paying for without knowing it, a privacy exposure, and a page-speed cost. Terminated vendors still loading means shoppers are still being tracked by someone you fired.",
        owner=OWNER_CONSENT,
        fix="Remove any tag for a vendor the store no longer uses, and approve or reject each new vendor so the list stays current.",
    ),
    "C16": dict(
        name="Cookie count growing",
        area=AREA_HEALTH, weight=25,
        what="How many cookies the site sets on a first visit, compared with the previous run.",
        why="A rising cookie count usually means a new tracker was added without review, which is how consent problems start.",
        owner=OWNER_CONSENT,
        fix="Identify the new cookies' owners and confirm each is disclosed in the privacy policy and gated by the consent banner.",
    ),
    "C17": dict(
        name="Trackers firing before the visitor consents",
        area=AREA_LEGAL, weight=88,
        what="Advertising and analytics trackers that load before anyone clicks the ComplyAuto consent banner.",
        why="California's Invasion of Privacy Act (CIPA) suits against dealers are built on exactly this: tracking a visitor before consent. These suits are filed against dealers regularly, and the exposure grows with every tag that fires early.",
        owner=OWNER_CONSENT,
        fix="Turn on ComplyAuto pre-consent tag blocking (or Google Consent Mode v2 defaulted to denied) so every tag waits for the visitor's choice.",
    ),
    "C18": dict(
        name="SSL certificate invalid or expiring",
        area=AREA_HEALTH, weight=45,
        what="The security certificate on every owned domain.",
        why="A bad certificate shows shoppers a full-screen browser warning and stops the page from loading; it looks like the store's site has been hacked.",
        owner=OWNER_DOMAINS,
        fix="Renew or install a valid certificate on the flagged domain, or point the domain at the main site so it inherits the working one.",
    ),
    "C19": dict(
        name="Owned domain not redirecting to mcpeeks.com",
        area=AREA_HEALTH, weight=42,
        what="Every domain the store owns, checked for a clean redirect to www.mcpeeks.com.",
        why="A dead or misrouted domain wastes the traffic it still gets from old ads, signage, and search results.",
        owner=OWNER_DOMAINS,
        fix="Set a permanent (301) redirect from the flagged domain to https://www.mcpeeks.com/.",
    ),
    "C20": dict(
        name="Phone numbers route to the right department",
        area=AREA_PHONE, weight=35,
        what="Every phone number published on the site. This check cannot be automated; the Phone Checklist tab lists each number for a manual test call.",
        why="A sales call that lands in service, or a whisper message before connect, is a lost lead the store paid to generate.",
        owner=OWNER_PHONES,
        fix="Call each number on the checklist, confirm the department and greeting, and correct any misrouted line in the call-tracking platform.",
    ),
    "C21": dict(
        name="Generic or dummy phone number on the page",
        area=AREA_PHONE, weight=48,
        what="Department pages that show a single generic number instead of a department line, and any obviously fake number such as 123-456-7890.",
        why="Shoppers who reach a switchboard instead of the department hang up, and a fake number on a live page is a credibility problem.",
        owner=OWNER_SITE,
        fix="Publish the department-specific tracking number on the Service, Parts, and Contact pages and remove any test numbers.",
    ),
    "C22": dict(
        name="Installed equipment excluded from the advertised price",
        area=AREA_LEGAL, weight=94,
        what="Disclaimer or pricing wording that keeps dealer-installed items out of the advertised price: excludes dealer-installed accessories, may be purchased for an additional cost or removed at the customer's option, does not apply to vehicles with dealer-added options.",
        why="From October 1, 2026 the CARS Act total price must include every item installed on the vehicle at the time of the ad (Civ. Code 1784.31(j)(2)). CNCDA calls pay-or-remove the practice the law was written to end, and the FTC's March 2026 letters targeted the same pattern; the FTC's September 2026 FAQs (Q9) add that a store may not call an installed item optional unless the customer can really decline it and buy at the advertised price, and may not imply an installed option cannot be removed. This is the highest-dollar exposure on the list because it adds hundreds or thousands per deal.",
        owner=OWNER_SITE,
        fix="Fold every installed accessory and protection product into the advertised total price in the feed and on the VDP, remove the exclusion wording from the disclaimer template, and list installed items by name as included in the price. Customer-ordered accessories installed after the sale go on a due bill instead and do not touch the advertised price.",
    ),
    "C23": dict(
        name="Repealed two-day cancellation option wording still on the site",
        area=AREA_LEGAL, weight=80,
        what="Any page, FAQ, or contract sample that still describes the paid two-day contract cancellation option, a 72-hour purchased option, a $40,000 threshold, or no cooling-off period unless you buy an option.",
        why="Vehicle Code 11713.21 is repealed on October 1, 2026 and replaced by a free three-day right to cancel on used vehicles priced $50,000 or less. CNCDA says the old form and wording may not be used after that date even by a store that already gives free returns, and copy describing the old option misstates the customer's rights.",
        owner=OWNER_SITE,
        fix="Replace the old wording with the current rule: a free 3-day right to cancel on used vehicles $50,000 or less, measured from contract signing, with the restocking fee deducted from the refund. Any more generous store policy belongs in the 3-Day Right to Cancel disclosure and the showroom signage, not just the website.",
    ),
    "C24": dict(
        name="MSRP shown as the price, or 'MSRP is not the selling price' wording",
        area=AREA_LEGAL, weight=89,
        what="Vehicle pages where MSRP is the only figure or the biggest figure, or where a disclaimer says the price shown is MSRP and not the selling price.",
        why="From October 1, 2026 the dealer's total price must appear in every ad for a specific vehicle, and CNCDA is explicit that MSRP-only advertising and an MSRP figure with a not-the-selling-price disclaimer both fail (Civ. Code 1784.41(a), CNCDA Guide Part 2). MSRP may stay only when it is labeled MSRP and shown no more prominently than the total price.",
        owner=OWNER_SITE,
        fix="Make the dealer's total price the prominent figure on every VDP, keep MSRP labeled and smaller, and delete any wording that presents MSRP as a stand-in for the selling price.",
    ),
    "C25": dict(
        name="In-transit unit mislabeled or missing an arrival date",
        area=AREA_LEGAL, weight=72,
        what="Vehicle pages that say in transit (or arriving soon) while also describing the unit as in production, not yet built, or a factory order, and in-transit pages that give no arrival information at all.",
        why="The FTC's September 2026 FAQs (Q10) allow a unit that is not on the lot to be advertised only if the page plainly says so, and FTC staff added on September 30, 2026 that shoppers read in transit as already on its way: a car that has not been built or shipped has to be described by its real status, any arrival date has to match what the store actually knows, and the unit must be available for purchase when it lands rather than already sold to someone else's paid order. A shopper who drives in for an in-transit unit that does not exist yet is the exact bait complaint the FTC says it will pursue.",
        owner=OWNER_INVENTORY,
        fix="Use in transit only for units the carrier has picked up, with the arrival information the store can support; label everything earlier as in production or factory order with an honest timeline; and pull any in-transit unit that is already committed to a sold order from the live feed.",
    ),
}

# Short titles for the Scorecard "Check" column (same order as CATALOG).
CHECK_IDS = sorted(CATALOG)


def area_for(finding):
    """Area bucket for a finding: the check's home area, unless the finding
    carries a stricter severity (e.g. a C08 hygiene-length item stays Health)."""
    sev = finding.get("severity")
    check = finding.get("check")
    if check in CATALOG and sev == "compliance":
        return AREA_LEGAL
    if check in CATALOG and sev in (None, ""):
        return CATALOG[check]["area"]
    return SEVERITY_TO_AREA.get(sev, CATALOG.get(check, {}).get("area", AREA_HEALTH))


def clean_text(s):
    """Reword crawler output for the GM audience and keep post_flight happy."""
    if not s:
        return s
    s = str(s)
    swaps = [
        ("Placeholder/stock image detected", "Vendor 'Image Coming Soon' graphic instead of a real photo"),
        ("Placeholder phone number", "Dummy phone number"),
        ("placeholder", "stock graphic"),
        ("Placeholder", "Stock graphic"),
        (" — ", ". "), ("—", "-"),
    ]
    for a, b in swaps:
        s = s.replace(a, b)
    return s
