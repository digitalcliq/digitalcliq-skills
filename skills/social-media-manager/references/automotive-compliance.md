# Automotive Brand & Ad Compliance (skill knowledge base)

When the business is an automotive dealer, every caption, graphic, and generation
prompt must pass brand + legal compliance BEFORE it ships. The vault already holds
the source rulebooks: load them, don't guess.

## Where the resources live (vault)
- `Resources/automotive-guidelines/CDJR_Brand_Guidelines_2026.pdf`: Stellantis Dealer Accelerate (DAP) Tier III co-op rulebook.
- `Resources/automotive-guidelines/CDJR_Website Guidelines_Final2026.pdf`: visual identity (logos, palettes, typography, CTAs).
- `Resources/automotive-guidelines/cdjr-quick-reference.md`: page-cited extraction of both PDFs. **Start here.**
- `Resources/automotive-guidelines/README.md`: index of all OEM guideline sets (BMW, Nissan, Chevrolet, Harley also present).
- Cross-check the `/brand-check` skill (`.claude/skills/brand-check/brands/`) for BMW, Nissan, Stellantis, Chevrolet, Harley.

Other OEMs in the vault: BMW, Nissan, Chevrolet, Harley-Davidson. For a non-CDJR auto
client, load that brand's guideline set the same way.

## CDJR (Chrysler / Dodge / Jeep / Ram), hard rules
**Nomenclature (hard fails if wrong):**
- Always **"Ram 1500"** (Ram 2500/3500, ProMaster). **NEVER "Dodge Ram"** or Dodge logo on a Ram. Ram is a standalone brand.
- Full model names: **Jeep Wrangler / Jeep Grand Cherokee / Jeep Compass / Jeep Gladiator**; **Dodge Charger / Challenger / Durango / Hornet**; **Chrysler Pacifica / Voyager**.
- Never lock a brand logo into a headline or into a model-name logotype.

**Co-op content rules:**
- Keep ≥75% of creative on **NEW** vehicles; CPOV ≤25% (separated + CPOV logo), parts/service ≤10%.
- **Never** include used/pre-owned in a new-vehicle co-op post (voids the claim).
- One marque's palette per asset: do not mix marque palettes.
- Clean vehicle as the hero, ideally Stellantis CGI/eVN imagery; never dirty/snow/debris, never vehicle-not-hero.

**Banned distress words (void co-op):** Bailout, Blowout, Liquidation, Wholesale, Distress, Factory Outlet, Factory Authorized, Factory/Manufacturer Challenged, Below/Under Invoice, Buy One Get One.

**Never reference:** recalls, safety actions/inspections, TSBs, parts availability, or any authorized/required repair. Never name another FCA US dealer or imply preferential standing. No religious/racial/political overtones or profane/harassing language. No PII in claim docs.

**Per-marque palettes (one per asset):**
- **Ram**: Ram Black #0E0E0E, White, **Stinger Yellow #F2CB05** (capable/rugged/tow-haul).
- **Dodge**: Black #000000, White, Grey #999999, **Dodge Red #ED0500** (muscle/performance/attitude).
- **Jeep**: Diamond Black #000000, Bright White, Silver Zynith #EAEAEA, Baltic Grey #3E3E3E (adventure/freedom/outdoors).
- **Chrysler**: Deep Blue #0F293D, Mid Blue #063E77, Pale Grey #E6EAE5, Sky #C3D7EE, Accent Red #ED5656 (refined/premium/family).

## Legal disclaimers (lease / finance / price offers)
Offers are the **dealer's legal responsibility**: Stellantis does NOT pre-review for legal compliance.
Any payment/price post must carry the required disclosure: term, due-at-signing, expiration,
"+ tax, title, license", doc/dealer fees, lender-approval/qualification language, per FTC Reg Z/Reg M
and **California DMV / Vehicle Code** advertising law. Label MSRP exactly as "MSRP" from the daily
Stellantis inventory file. Show discount stacks with conditional incentives listed BELOW the stack.

> **Generation guardrail:** AI-generated vehicle imagery is for **brand / lifestyle / concept** use,
> not to represent a specific real VIN or a binding offer. Any post that states a price, payment, or
> term needs the real, current, approved numbers + the legal disclaimer added before publishing, flag
> every such row as "needs dealer/compliance sign-off." Pre-approval is available at tier3adcoop.com.

## California CARS Act (SB 766, operative 2026-10-01): every priced or vehicle-specific post

Source of truth: `Resources/automotive-guidelines/ca-cars-act-sb766-index.md` (statute) and
`Resources/automotive-guidelines/cncda-cars-act-guidance.md` (CNCDA Compliance Guide v1.2 and
Webinar FAQ, the dealer-association read). A social post is a dealer advertisement, and so is a
salesperson's post on a personal account (CNCDA FAQ Q20). Hard rules for any California dealer:

- **Identified unit means total price.** If the post names a stock number or VIN, or shows a
  photo of an identified vehicle, or states any payment, due-at-signing, APR, or dollar amount for
  it, the vehicle's **total price** must be in the post (Civ. Code §1784.41(a)). Lease posts too
  (CNCDA FAQ Q19). Total price includes every installed accessory and any markup and is never
  reduced by a rebate. Never write "Call for price", "DM for price", or "See price".
- **Model-level posts are safe.** "New 2026 Wranglers starting at $32,000, 5 at this price" with no
  identified unit is outside the total-price trigger but must carry the number available next to
  the price (Veh. Code §11713.1(i)). The first written reply to a commenter or DM that quotes any
  figure for a unit then triggers the total price for that unit; route those replies to the CRM.
- **MSRP is not a price.** Label it "MSRP" and never show it bigger than the total price. No
  "MSRP, not the selling price" captions.
- **Rebate stack order:** Total Price, then "Factory Rebate" as a dollar amount, then "Net Cost".
  The after-rebate figure is never called a price. No dealer cash back, no "up to $X in rebates".
- **Fee sentence verbatim** on any priced post that links to or functions as a price display:
  "Plus government fees and taxes, any finance charges, any dealer document processing charge,
  any electronic filing charge, and any emission testing charge."
- **Identify the unit** by model, model-year, and VIN or license number; a stock number alone is
  not sufficient (Veh. Code §11713.1(a)). Date the offer (the advertised price is a ceiling for
  anyone while the unit is unsold).
- **Never** "pre-approved", "guaranteed approval", government-styled framing, "out-the-door"
  labels, or "free" anything tied to a vehicle purchase (Veh. Code §11713.1(h)).
- **Sold units** come down within 48 hours across every platform; a boosted post on a sold unit is
  an availability misrepresentation (Civ. Code §1784.40(d)).
- **Payment posts** still need the Reg Z / Reg M trigger-term disclosures and OAC language.

Every row in the calendar that carries a price, payment, or identified unit is flagged
"Compliance sign-off required" and routed through `/brand-check` (its California CARS Act overlay)
before it ships.

## Workflow
1. Load `cdjr-quick-reference.md` (or the matching OEM file) first.
2. Draft captions/graphics within the rules above.
3. For any price/lease/finance claim or identified unit: apply the CARS Act block above, mark the calendar row **"Compliance sign-off required"**, and never invent numbers.
4. Optionally route final creative through `/brand-check` before delivery.
