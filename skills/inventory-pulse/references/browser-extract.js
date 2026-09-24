/* DigitalCLIQ Inventory Pulse: in-page extractor for WAF'd dealer sites.
 *
 * Run these snippets via mcp__Claude_Browser__javascript_tool (pass tabId; the
 * Chrome extension's javascript_tool is the fallback only) in a tab that is ALREADY on the
 * dealer's own domain (same-origin fetch passes the WAF where server-side
 * Python gets 403). Never pull raw HTML back into the conversation: all
 * parsing happens in the page; only compact JSON rows come back.
 *
 * The JS tool has a ~30s timeout, so work in batches:
 *   1. Run SNIPPET A once (installs window.__pulse helpers, fetches sitemap,
 *      returns the filtered VDP URL list COUNT + first few samples).
 *   2. Run SNIPPET B repeatedly: __pulseBatch(15) processes the next 15 URLs
 *      (~400ms pacing) and returns {done, remaining, rows:[...новые]}.
 *      Keep calling until done=true. Cap total at 150 URLs.
 *
 * SNIPPET A -- paste with MATCHES replaced (lowercase substrings from
 * config match lists, e.g. ["x3","x5","330i","m340i","3 series"]) and
 * RECHECK replaced with the output of recheck_urls.py (or [] on baseline).
 * Inventory is SAMPLED: PER_MODEL (4) VDPs per matched model, plus the
 * recheck URLs so delist detection stays honest.

(async () => {
  const MATCHES = ["REPLACE_ME"];
  const RECHECK = [];
  const PER_MODEL = 4;
  const paths = ["/inventory-sitemap.xml","/sitemap.xml","/sitemap_index.xml","/dealer-sitemap.xml"];
  let urls = [];
  for (const p of paths) {
    try {
      const r = await fetch(p); if (!r.ok) continue;
      let t = await r.text();
      if (t.includes("<sitemapindex")) {
        const subs = [...t.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m=>m[1])
          .filter(u=>/invent|vehicle|vdp/i.test(u)).slice(0,3);
        t = "";
        for (const s of subs) { try { const r2 = await fetch(s); if (r2.ok) t += await r2.text(); } catch(e){} }
      }
      urls = [...t.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m=>m[1]);
      if (urls.length) break;
    } catch(e){}
  }
  const isNew = u => !/\/(used|preowned|pre-owned|certified|cpo)\b/i.test(u);
  const hitOf = u => MATCHES.find(m => u.toLowerCase().includes(m.replace(/ /g,"-")) || u.toLowerCase().includes(m.replace(/ /g,"")));
  const perModel = {};
  for (const u of new Set(urls.filter(isNew))) {
    const m = hitOf(u); if (!m) continue;
    (perModel[m] ||= []);
    if (perModel[m].length < PER_MODEL) perModel[m].push(u);
  }
  window.__pulseUrls = [...new Set([...Object.values(perModel).flat(), ...RECHECK])];
  window.__pulseRows = []; window.__pulseIdx = 0; window.__pulseFails = 0;
  return {sitemap_urls: urls.length, vdp_sampled: window.__pulseUrls.length,
          per_model: Object.fromEntries(Object.entries(perModel).map(([k,v])=>[k,v.length])),
          sample: window.__pulseUrls.slice(0,4)};
})()

 * If vdp_matched is 0, the sitemap has no VDPs: fall back to reading the SRP
 * DOM directly (SNIPPET C) after navigating to the new-inventory search page.
 *
 * SNIPPET B -- run repeatedly until done:

(async () => {
  const BATCH = 15, PACE = 400;
  const priceRe = /(msrp|retail price|selling price|sale price|internet price|e-?price|our price|final price)[^$\d]{0,80}\$?\s*([\d]{2,3}[,.]?\d{3})/gi;
  const vinRe = /\b([A-HJ-NPR-Z0-9]{17})\b/;
  const out = [];
  const parse = (html, url) => {
    const doc = new DOMParser().parseFromString(html, "text/html");
    const row = {vin:"",yr:0,make:"",model:"",trim:"",version:"",msrp:0,price:0,call_for_price:0,vdp_url:url,extract_method:""};
    for (const s of doc.querySelectorAll('script[type*="ld+json"]')) {
      let d; try { d = JSON.parse(s.textContent); } catch(e){ continue; }
      const stack = Array.isArray(d) ? [...d] : [d];
      while (stack.length) {
        const n = stack.pop();
        if (Array.isArray(n)) { stack.push(...n); continue; }
        if (!n || typeof n !== "object") continue;
        if (n["@graph"]) stack.push(...[].concat(n["@graph"]));
        const t = [].concat(n["@type"]||[]);
        if (t.some(x=>["Vehicle","Car","Product"].includes(x))) {
          const of = [].concat(n.offers||[])[0]||{};
          row.vin = String(n.vehicleIdentificationNumber||n.vin||"").toUpperCase();
          row.yr = parseInt(n.vehicleModelDate||n.modelDate||0)||0;
          row.make = typeof n.brand==="object" ? (n.brand?.name||"") : String(n.brand||n.manufacturer||"");
          row.model = String(n.model||""); row.trim = String(n.vehicleConfiguration||n.trim||"");
          row.price = Math.round(parseFloat(String(of.price||"0").replace(/[^\d.]/g,""))||0);
          row.version = String(n.name||"");
          if (!row.yr) { const m = row.version.match(/(20\d\d)/); if (m) row.yr = +m[1]; }
          row.extract_method = "jsonld";
        }
      }
    }
    const text = doc.body ? doc.body.textContent : html;
    if (!row.vin) { const m = vinRe.exec(url) || vinRe.exec(text); if (m) { row.vin = m[1].toUpperCase(); row.extract_method ||= "regex"; } }
    for (const m of text.matchAll(priceRe)) {
      const val = Math.round(parseFloat(m[2].replace(/,/g,""))||0);
      if (/msrp|retail/i.test(m[1])) row.msrp = Math.max(row.msrp, val);
      else if (!row.price) { row.price = val; row.extract_method ||= "regex"; }
    }
    if (!row.price && /call\s*(us\s*)?for\s*(best\s*)?(price|pricing)/i.test(text)) row.call_for_price = 1;
    return (row.vin||row.price||row.call_for_price) ? row : null;
  };
  while (window.__pulseIdx < window.__pulseUrls.length && out.length < BATCH) {
    const u = window.__pulseUrls[window.__pulseIdx++];
    try {
      const r = await fetch(u);
      if (r.ok) { const row = parse(await r.text(), u); if (row) { window.__pulseRows.push(row); out.push(row); } window.__pulseFails = 0; }
      else if (++window.__pulseFails >= 8) return {error:"circuit breaker: 8 consecutive fetch failures, STOP"};
    } catch(e) { if (++window.__pulseFails >= 8) return {error:"circuit breaker"}; }
    await new Promise(res=>setTimeout(res, PACE));
  }
  return {done: window.__pulseIdx >= window.__pulseUrls.length,
          remaining: window.__pulseUrls.length - window.__pulseIdx,
          total_rows: window.__pulseRows.length, rows: out};
})()

 * SNIPPET C -- SRP fallback (navigate the tab to the new-inventory page for
 * one model first; repeat per model / per pagination page). Reads vehicle
 * cards straight from the live DOM; platforms differ, so selectors are
 * best-effort. Review what comes back and adapt if empty:

(() => {
  const cards = document.querySelectorAll('[class*="vehicle-card"],[class*="inventory-listing"],[class*="srp-vehicle"],[data-vin],li[class*="vehicle"]');
  const vinRe = /\b([A-HJ-NPR-Z0-9]{17})\b/;
  const rows = [];
  cards.forEach(c => {
    const text = c.textContent || "";
    const vin = (c.getAttribute("data-vin") || (vinRe.exec(c.innerHTML)||[])[1] || "").toUpperCase();
    const prices = [...text.matchAll(/\$\s?([\d]{2,3},\d{3})/g)].map(m=>+m[1].replace(/,/g,""));
    const title = (c.querySelector("h2,h3,[class*='title']")?.textContent||"").trim().replace(/\s+/g," ");
    const yr = +(title.match(/(20\d\d)/)||[0,0])[1];
    const a = c.querySelector("a[href*='inventory'],a[href*='vehicle'],a[href*='new']");
    if (vin || prices.length) rows.push({vin, yr, version: title,
      price: prices.length ? Math.min(...prices) : 0, msrp: prices.length > 1 ? Math.max(...prices) : 0,
      call_for_price: /call.{0,20}price/i.test(text) ? 1 : 0,
      vdp_url: a ? a.href : location.href, extract_method: "srp-dom"});
  });
  return {cards: cards.length, rows};
})()
*/
