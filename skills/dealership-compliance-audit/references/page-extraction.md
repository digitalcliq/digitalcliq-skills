# Page Extraction Specs (Phase 1, Step 1.3)

Per-page-type extraction instructions and JS snippets for the dealership-compliance-audit
crawl agents. Read ONLY the sections for page types discovered in Step 1.2. Each crawl
agent writes its extracted JSON to `/tmp/{safe_client}_page_{pagekey}.json` and returns a
one-line status (never the page body) per the Phase 1 token-discipline rule in SKILL.md.

**CRITICAL: Use `mcp__Claude_Browser__javascript_tool` for ALL page data extraction.**
Do NOT use `get_page_text` or `read_page`: these fail on large inventory pages.
For each page: `mcp__Claude_Browser__navigate` to it in YOUR tab (pass `tabId`), wait
2 seconds, then run the extraction JS below in the same tab. The Claude Browser is the
only surface these snippets are written for; the Chrome extension is a last-resort
fallback per the Browser Surface Order in SKILL.md, and the JS is identical there.

## Contents

1. [Homepage Extraction JS](#homepage-extraction-js)
2. [VLP (Vehicle Listing Page) Extraction JS](#vlp-vehicle-listing-page-extraction-js)
3. [VDP (Vehicle Detail Page): RANDOM MULTI-SAMPLE](#vdp-vehicle-detail-page--random-multi-sample)
4. [Specials Page Extraction JS](#specials-page-extraction-js)
5. [Used/CPO Page Extraction JS](#usedcpo-page-extraction-js)
6. [Finance Page Extraction JS](#finance-page-extraction-js)
7. [Privacy Policy Page Extraction JS](#privacy-policy-page-extraction-js)

## Homepage Extraction JS:
```javascript
(function() {
  const main = document.querySelector('main') || document.body;
  const text = main.innerText.substring(0, 15000);
  const disclaimers = Array.from(document.querySelectorAll('[class*="disclaim"], [class*="legal"], [class*="fine-print"], details, [class*="tooltip"]'))
    .map(el => el.innerText.trim()).filter(t => t.length > 20);
  const prices = text.match(/\$[\d,]+(?:\.\d{2})?(?:\/mo)?/g) || [];
  const leaseTerms = text.match(/\d+\s*months?/gi) || [];

  // --- Dealer name (2026-08 fix: McPeek run captured the hostname) ---
  // Cascade: og:site_name → schema.org AutoDealer name → logo alt → dealer-name class →
  // first title segment. NEVER the page hostname, and reject any candidate that looks
  // like one (og:site_name on some platforms is just the domain).
  const schemaDealerName = (function() {
    for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
      try {
        const data = JSON.parse(s.textContent);
        const nodes = [].concat(data, data['@graph'] || []);
        for (const n of nodes) {
          if (n && /AutoDealer|AutomotiveBusiness|LocalBusiness|Organization/i.test(String(n['@type'] || '')) && n.name) return n.name;
        }
      } catch (e) {}
    }
    return '';
  })();
  const logoAlt = (document.querySelector('img[class*="logo" i], [class*="logo" i] img[alt], header img[alt]')?.getAttribute('alt') || '');
  const looksLikeHostname = s => /(?:^|\s)www\.|\.(?:com|net|org|us|biz|info)\b/i.test((s || '').trim());
  const dealerName = [
    document.querySelector('meta[property="og:site_name"]')?.content,
    schemaDealerName,
    logoAlt,
    document.querySelector('[class*="dealer-name"]')?.textContent,
    document.title.split('|')[0]
  ].map(c => (c || '').trim()).find(c => c.length > 2 && !looksLikeHostname(c)) || '';

  // --- CCPA/CPRA privacy link detection ---
  const allLinks = Array.from(document.querySelectorAll('a'));
  const footerLinks = Array.from(document.querySelectorAll('footer a, [class*="footer"] a, [id*="footer"] a'));
  const linkSource = footerLinks.length > 0 ? footerLinks : allLinks;

  // 2026-08 fix: McPeek's footer anchor is just "Privacy" (href /privacy/): requiring the
  // literal text "privacy policy" read false and cascaded into a false-critical PRIV-004.
  // Match plain "Privacy" text and href*="privacy" too, but never mistake the CPRA opt-out
  // link ("Your Privacy Choices" / "Do Not Sell") for the policy link.
  const linkHref = a => a.getAttribute('href') || '';
  const privacyLink =
    linkSource.find(a => /privacy\s*policy/i.test(a.textContent)) ||
    linkSource.find(a => /privacy/i.test(a.textContent) && !/choices|opt[\s-]*out|do\s*not\s*(sell|share)/i.test(a.textContent)) ||
    linkSource.find(a => /privacy/i.test(linkHref(a)) && !/choices|opt[\s-]*out|do-?not-?(sell|share)/i.test(linkHref(a)));
  const doNotSellLink = allLinks.find(a => /do\s*not\s*sell|do\s*not\s*share|opt[\s-]*out/i.test(a.textContent));
  const limitSensitiveLink = allLinks.find(a => /limit.*sensitive|sensitive.*information/i.test(a.textContent));
  const cookieBanner = document.querySelector('[class*="cookie"], [id*="cookie"], [class*="consent"], [id*="consent"], [class*="gdpr"]');

  // Lead form detection (for notice-at-collection check)
  const leadForms = Array.from(document.querySelectorAll('form')).filter(f => {
    const t = (f.innerText || '').toLowerCase();
    return /name|email|phone|zip|contact|price|offer|trade/i.test(t);
  });

  return JSON.stringify({
    title: document.title,
    url: window.location.href,
    dealer_name: dealerName,
    text_excerpt: text,
    disclaimers: disclaimers.slice(0, 10),
    prices_found: [...new Set(prices)].slice(0, 20),
    lease_terms: [...new Set(leaseTerms)],
    has_chat_widget: !!document.querySelector('[class*="chat"], [id*="chat"], [class*="livechat"]'),
    has_popup: !!document.querySelector('[class*="popup"], [class*="modal"][style*="display: block"], [class*="overlay"]:not([style*="display: none"])'),
    nav_links: Array.from(document.querySelectorAll('nav a')).map(a => ({text: a.textContent.trim(), href: a.href})).filter(l => l.text.length > 0).slice(0, 30),
    // CCPA/CPRA privacy data
    privacy: {
      has_privacy_policy_link: !!privacyLink,
      privacy_policy_url: privacyLink?.href || null,
      privacy_policy_link_text: privacyLink?.textContent?.trim() || null,
      has_do_not_sell_link: !!doNotSellLink,
      do_not_sell_url: doNotSellLink?.href || null,
      do_not_sell_link_text: doNotSellLink?.textContent?.trim() || null,
      has_limit_sensitive_link: !!limitSensitiveLink,
      limit_sensitive_url: limitSensitiveLink?.href || null,
      limit_sensitive_link_text: limitSensitiveLink?.textContent?.trim() || null,
      has_cookie_consent_banner: !!cookieBanner,
      cookie_banner_text: cookieBanner?.innerText?.substring(0, 500) || null,
      lead_forms_count: leadForms.length,
      lead_forms_have_privacy_notice: leadForms.map(f => ({
        action: f.action || 'unknown',
        has_privacy_link: /privacy/i.test(f.innerHTML),
        has_notice_at_collection: /categories.*collected|information.*collect|we collect/i.test(f.innerText || ''),
        // TCPA: does the form capture a phone number, and is there call/text consent language?
        has_phone: !!f.querySelector('input[type="tel"], input[name*="phone" i], input[placeholder*="phone" i], input[id*="phone" i]'),
        has_tcpa_consent: /consent to receive|autodialed|auto-dialed|automated (?:calls|texts|technology)|message (?:and|&) data rates|msg (?:and|&) data|recurring (?:messages|texts)|text messages|by submitting.*(?:agree|consent)|prerecorded|opt[\s-]*out/i.test(f.innerText || ''),
        fields: Array.from(f.querySelectorAll('input, select, textarea')).map(i => i.name || i.placeholder || i.type).filter(Boolean).slice(0, 10)
      })).slice(0, 5)
    },
    // --- ADA / Unruh accessibility snapshot (heuristic; confirms easy wins only) ---
    accessibility: (function() {
      const imgs = Array.from(document.querySelectorAll('img'));
      const decorative = i => i.getAttribute('role') === 'presentation' || i.getAttribute('aria-hidden') === 'true';
      const missingAlt = imgs.filter(i => !decorative(i) && !(i.getAttribute('alt') || '').trim());
      const fields = Array.from(document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]), select, textarea'));
      const labeled = i => {
        if ((i.getAttribute('aria-label') || '').trim() || i.getAttribute('aria-labelledby') || (i.getAttribute('title') || '').trim()) return true;
        if (i.id && document.querySelector('label[for="' + (window.CSS && CSS.escape ? CSS.escape(i.id) : i.id) + '"]')) return true;
        return !!i.closest('label');
      };
      const unlabeled = fields.filter(i => !labeled(i));
      return {
        images_total: imgs.length,
        images_missing_alt: missingAlt.length,
        inputs_total: fields.length,
        inputs_missing_label: unlabeled.length,
        has_lang_attr: !!(document.documentElement.getAttribute('lang') || '').trim(),
        has_skip_nav: !!Array.from(document.querySelectorAll('a[href^="#"]')).find(a => /skip\s+(?:to|navigation|main|content)/i.test(a.textContent || ''))
      };
    })()
  });
})()
```

## VLP (Vehicle Listing Page) Extraction JS:
```javascript
(function() {
  // Find vehicle cards: most dealer platforms use article, .vehicle-card, or similar containers
  const cards = document.querySelectorAll('[class*="vehicle-card"], [class*="inventory-item"], [class*="listing"], article[class*="vehicle"]');
  const vehicles = [];
  // If no cards found, try links with vehicle-like URLs
  const vehicleLinks = cards.length > 0 ? [] :
    Array.from(document.querySelectorAll('a[href*="/inventory/"], a[href*="/vehicle/"]'))
    .filter(a => a.querySelector('img'));

  const sources = cards.length > 0 ? cards : vehicleLinks;
  const sample = Array.from(sources).slice(0, 5);

  sample.forEach(el => {
    const text = el.innerText || el.textContent;
    const link = el.tagName === 'A' ? el.href : el.querySelector('a')?.href || '';
    const img = el.querySelector('img');
    vehicles.push({
      text: text.substring(0, 500),
      link: link,
      has_image: !!img,
      has_price: /\$[\d,]+/.test(text),
      has_vin: /vin/i.test(text),
      has_stock: /stock|stk/i.test(text),
      has_msrp_label: /msrp/i.test(text)
    });
  });

  const main = document.querySelector('main') || document.body;
  const fullText = main.innerText;
  const disclaimers = Array.from(document.querySelectorAll('[class*="disclaim"], [class*="legal"], [class*="fine-print"]'))
    .map(el => el.innerText.trim()).filter(t => t.length > 20);

  return JSON.stringify({
    title: document.title,
    url: window.location.href,
    total_vehicles_text: fullText.match(/(\d+)\s*(?:new|vehicles?|results?|found)/i)?.[0] || '',
    sample_listings: vehicles,
    has_filters: !!document.querySelector('[class*="filter"], select, [class*="facet"]'),
    disclaimers: disclaimers.slice(0, 5),
    page_text_excerpt: fullText.substring(0, 5000)
  });
})()
```

## VDP (Vehicle Detail Page): RANDOM MULTI-SAMPLE:

Do NOT audit a single hand-picked car. VDP problems are systemic (a missing
finance disclosure or an MSRP with no disclaimer is usually present on every
vehicle), and per-vehicle pricing is exactly what FTC and CA DMV/BAR examiners
spot-check. Sample **3 to 5 random VDPs spread across new AND used inventory**:

1. Collect candidate vehicle URLs from BOTH the VLP `sample_listings` and the
   used-page listings (any `a[href*="/inventory/"]`, `/vehicle/`, `/vehicledetails/`).
2. Pick 3-5 at random across new + used. Use real randomness (e.g.
   `Math.random()`), do not always take the first ones, and **rotate** so a
   month-over-month run covers different VINs.
3. Store them as their own page keys: the first is `vdp`, the rest are `vdp_2`,
   `vdp_3`, ... The engine fans every per-vehicle check across all of them and the
   delta engine buckets them so they track as one issue across months.
4. Record the chosen VINs/URLs in `vdp_sample_meta` (see schema below) so the run
   is reproducible and you can prove exactly which cars were checked.

Run this extractor on EACH sampled VDP and write each result to its own page key.

```javascript
(function() {
  const main = document.querySelector('main') || document.body;
  const text = main.innerText;
  const prices = text.match(/\$[\d,]+(?:\.\d{2})?/g) || [];
  const vin = text.match(/VIN[:\s]*([A-HJ-NPR-Z0-9]{17})/i);
  const stock = text.match(/Stock[:\s#]*(\w+)/i);
  const disclaimers = Array.from(document.querySelectorAll('[class*="disclaim"], [class*="legal"], [class*="fine-print"], [class*="footnote"]'))
    .map(el => el.innerText.trim()).filter(t => t.length > 20);

  return JSON.stringify({
    title: document.title,
    url: window.location.href,
    vin: vin ? vin[1] : null,
    stock_number: stock ? stock[1] : null,
    prices_found: [...new Set(prices)].slice(0, 10),
    has_msrp_label: /msrp/i.test(text),
    has_selling_price: /selling\s*price|internet\s*price|our\s*price|dealer\s*price/i.test(text),
    has_photos: document.querySelectorAll('[class*="gallery"] img, [class*="photo"] img, [class*="media"] img').length,
    has_equipment_list: /standard|optional|equipment|features/i.test(text),
    disclaimers: disclaimers.slice(0, 10),
    text_excerpt: text.substring(0, 8000)
  });
})()
```

## Specials Page Extraction JS:
**NOTE:** Many dealer sites hide lease disclaimers behind click-to-expand buttons (`[+DISCLAIMER]`, "See Details", etc.). This JS clicks ALL expand/toggle buttons first, waits 1 second for content to appear, then extracts. Use the text_excerpt (12K chars) to capture all content, plus a content-pattern search for Reg M disclosures:
```javascript
(async function() {
  // Step 1: Click all disclaimer/expand/toggle buttons to reveal hidden content
  let clickedCount = 0;

  // CSS selector targets for expandable buttons
  const expandBtns = document.querySelectorAll(
    'button[class*="disclaim"], button[class*="expand"], button[class*="toggle"], ' +
    'a[class*="disclaim"], a[class*="expand"], a[class*="toggle"], ' +
    '[class*="accordion"] button, [class*="collapse"] button, ' +
    'details > summary, [role="button"][aria-expanded="false"]'
  );
  expandBtns.forEach(btn => { try { btn.click(); clickedCount++; } catch(e) {} });

  // Text-content matching for buttons with disclaimer/details labels
  document.querySelectorAll('button, a, [role="button"], span[onclick], div[onclick]').forEach(el => {
    const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
    if (txt.length < 60 && /disclaimer|see details|show details|view details|more info|\+\s*details|expand|read more|terms/i.test(txt)) {
      try { el.click(); clickedCount++; } catch(e) {}
    }
  });

  // Step 2: Wait 1 second for expanded content to render
  await new Promise(r => setTimeout(r, 1000));

  // Step 3: Extract with expanded content now visible
  const main = document.querySelector('main') || document.body;
  const text = main.innerText;
  // CSS-class disclaimers (broadened selectors for expanded content)
  const cssDisclaimers = Array.from(document.querySelectorAll(
    '[class*="disclaim"], [class*="legal"], [class*="fine-print"], ' +
    'details[open], [class*="footnote"], [class*="terms"]'
  )).map(el => el.innerText.trim()).filter(t => t.length > 20);
  // Content-pattern disclaimers (catches inline Reg M disclosures + mileage terms)
  const allEls = document.querySelectorAll('p, div, span');
  const contentDisclaimers = [];
  allEls.forEach(el => {
    const t = el.innerText?.trim();
    if (t && t.length > 100 && t.length < 3000 &&
        /capitalized cost|due at signing|lease payment|monthly.*payment.*based|mileage.*charge|disposition fee|miles per year|excess mile/i.test(t)) {
      contentDisclaimers.push(t.substring(0, 800));
    }
  });
  const allDisclaimers = [...new Set([...cssDisclaimers, ...contentDisclaimers])];

  return JSON.stringify({
    title: document.title,
    url: window.location.href,
    has_lease_offers: /lease|per\s*month|\$\d+\/mo/i.test(text),
    has_finance_offers: /finance|apr|interest/i.test(text),
    lease_payments: (text.match(/\$[\d,]+\s*(?:\/mo|per\s*month)/gi) || []).slice(0, 10),
    lease_terms: (text.match(/\d+\s*months?/gi) || []).slice(0, 10),
    disclaimers: allDisclaimers.slice(0, 15),
    disclaimer_buttons_clicked: clickedCount,
    text_excerpt: text.substring(0, 12000)
  });
})()
```

## Used/CPO Page Extraction JS:
```javascript
(function() {
  const main = document.querySelector('main') || document.body;
  const text = main.innerText;
  // Check first 3 vehicle cards for used/certified labeling
  const cards = document.querySelectorAll('[class*="vehicle-card"], [class*="inventory-item"], [class*="listing"]');
  const sampleCards = Array.from(cards).slice(0, 3).map(el => ({
    text: (el.innerText || el.textContent).substring(0, 500),
    has_used_label: /used|pre-?owned|previously\s*owned/i.test(el.innerText),
    has_certified_label: /certified/i.test(el.innerText),
    has_vin: /vin/i.test(el.innerText),
    has_price: /\$[\d,]+/.test(el.innerText),
    has_mileage: /mile|mileage|odometer/i.test(el.innerText)
  }));

  // If no cards found, try link-based detection
  const vehicleLinks = cards.length === 0 ?
    Array.from(document.querySelectorAll('a[href*="/inventory/"]')).slice(0, 3).map(a => ({
      text: (a.innerText || a.textContent).substring(0, 500),
      href: a.href,
      has_used_label: /used|pre-?owned/i.test(a.innerText),
      has_certified_label: /certified/i.test(a.innerText)
    })) : [];

  return JSON.stringify({
    title: document.title,
    url: window.location.href,
    sample_listings: sampleCards.length > 0 ? sampleCards : vehicleLinks,
    has_cpo_section: /certified\s*pre-?owned|cpo/i.test(text),
    has_carfax: /carfax|autocheck/i.test(text),
    page_text_excerpt: text.substring(0, 5000)
  });
})()
```

## Finance Page Extraction JS:
```javascript
(function() {
  const main = document.querySelector('main') || document.body;
  const text = main.innerText;
  return JSON.stringify({
    title: document.title,
    url: window.location.href,
    has_credit_trigger_terms: /\$\d+\s*(?:\/mo|per\s*month)|apr|interest\s*rate|down\s*payment|\d+\s*months?/i.test(text),
    has_everyone_financed: /everyone\s*financed|no\s*credit\s*rejected|guaranteed\s*(?:credit|financing)/i.test(text),
    has_oac: /\bOAC\b|O\.A\.C/i.test(text),
    text_excerpt: text.substring(0, 5000)
  });
})()
```

## Privacy Policy Page Extraction JS:
**Navigate to the privacy policy URL captured in the homepage extraction** (`privacy.privacy_policy_url`). If no privacy policy URL was found, skip this page and record `{"error": "no_privacy_policy_link_found"}`.

```javascript
(function() {
  const main = document.querySelector('main') || document.body;
  const text = main.innerText;

  // Check for required CCPA/CPRA content sections
  const hasRightToKnow = /right to know|right to request|access your/i.test(text);
  const hasRightToDelete = /right to delete|request deletion|delete your/i.test(text);
  const hasRightToOptOut = /right to opt[\s-]*out|do not sell|opt out of sale/i.test(text);
  const hasRightToCorrect = /right to correct|request correction/i.test(text);
  const hasRightToLimit = /right to limit|limit.*sensitive|sensitive personal/i.test(text);
  const hasCategoriesCollected = /categories.*(?:personal information|we collect|information.*collect)/i.test(text);
  const hasThirdParties = /third part(?:y|ies)|share.*with|disclose.*to/i.test(text);
  const hasSources = /sources.*(?:information|data|personal)|where.*collect/i.test(text);
  const hasPurposes = /purpose|business.*purpose|why we collect|how we use/i.test(text);
  const hasRetention = /retention|how long|retain.*data|keep.*information/i.test(text);
  const hasSellShare = /sell.*personal|share.*personal|do not sell|we.*(?:sell|share)/i.test(text);
  const hasGPC = /global privacy control|GPC|opt[\s-]*out.*signal|browser.*signal/i.test(text);
  const hasFinancialIncentive = /financial incentive|incentive program|value of.*data|data.*value/i.test(text);
  const hasContactMethods = /toll[\s-]*free|1-800|1-888|email.*privacy|privacy@|submit.*request|request form/i.test(text);
  const hasUpdateDate = text.match(/(?:last\s*updated|effective\s*date|updated|revised)[:\s]*(\w+\s*\d{1,2},?\s*\d{4}|\d{1,2}\/\d{1,2}\/\d{4}|\d{4}-\d{2}-\d{2})/i);

  // Count request submission methods
  const methods = [];
  if (/toll[\s-]*free|1-8\d{2}/i.test(text)) methods.push('toll-free phone');
  if (/email.*privacy|privacy@|privacy.*email/i.test(text)) methods.push('email');
  if (/request.*form|online.*form|web.*form|submit.*request/i.test(text)) methods.push('web form');
  if (/mail.*address|postal|p\.?o\.?\s*box/i.test(text)) methods.push('postal mail');

  return JSON.stringify({
    title: document.title,
    url: window.location.href,
    last_updated: hasUpdateDate ? hasUpdateDate[1] : null,
    ccpa_cpra_content: {
      has_right_to_know: hasRightToKnow,
      has_right_to_delete: hasRightToDelete,
      has_right_to_opt_out: hasRightToOptOut,
      has_right_to_correct: hasRightToCorrect,
      has_right_to_limit_sensitive: hasRightToLimit,
      has_categories_collected: hasCategoriesCollected,
      has_third_party_disclosure: hasThirdParties,
      has_sources_of_pi: hasSources,
      has_purposes: hasPurposes,
      has_retention_periods: hasRetention,
      has_sell_share_disclosure: hasSellShare,
      has_gpc_disclosure: hasGPC,
      has_financial_incentive_notice: hasFinancialIncentive,
      request_submission_methods: methods,
      request_method_count: methods.length
    },
    text_excerpt: text.substring(0, 8000)
  });
})()
```
