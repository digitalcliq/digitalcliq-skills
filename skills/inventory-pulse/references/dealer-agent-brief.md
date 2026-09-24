# Dealer Agent Brief (Inventory Pulse)

You are a crawl agent for ONE dealer (or a short list of browser-mode dealers, handled one at a time). Your entire deliverable is `fragment.json` per dealer plus a short summary. You are cheap by design: stay mechanical, keep output tiny.

Your task prompt gives you: dealer name/url/platform/role, the tracked models with their `match` lists, your `$DATA/{dealer-slug}/` output dir, `$SKILL` path, and your fetch mode (`server` or `browser`).

## Hard rules

- **Politeness**: sequential requests, ~0.7s pacing (scripts/JS enforce it). Circuit breaker (8 consecutive failures) = STOP all requests to that site, mark dealer `failed`, record the error, move on.
- **Never read raw page HTML or full inventory JSON into your context.** Scripts and in-page JS parse; you read one-line summaries and small JSON returns only.
- **Time-box**: max ~8 minutes per dealer, max 2 attempts per surface. A stuck surface (2 consecutive tool timeouts) = abandon that surface, cascade or fail the dealer. Never loop on a dead surface.
- **Never fabricate.** Unknown numbers stay 0/"". `errors` gets every error verbatim enough to act on.
- **Inventory is a SAMPLE, not a census (Drew, 2026-08-15): 3-4 VDPs per tracked model per dealer** (~12-16 pages). Prefer the lowest-priced units when the platform lets you sort (SRP `sort=price` etc.); otherwise take the first 3-4 per model. PLUS the recheck list (below), cap 40.
- **Recheck list**: your prompt includes (or you generate with `python3 "$SKILL/scripts/recheck_urls.py" --state "$STATE" --dealer "{Name}"`) the VDP URLs of VINs already tracked for this dealer. Fetch them too. A 404/no-parse on a RECHECK url is DATA (the vehicle is gone → delist), not a crawl error: don't retry it, don't count it toward failure judgment, note the count.
- **WRITE A ROW FOR EVERY RECHECK VIN THAT IS STILL LIVE.** The delist engine infers "VIN absent from your `inventory` array = delisted". If you confirm a rechecked vehicle is still on the site but do not emit an inventory row for it, the report tells the client that car SOLD. On 2026-09-20 this published 11 phantom delistings for a competitor the agent had explicitly verified as fully in stock. Emit the row even when you captured no price: `{"vin":..., "vdp_url":..., "price":0}` means "present, price not captured", which is true and safe. Only a VIN you positively confirmed GONE may be left out. A VIN whose status you could not establish gets NO row and an explicit error naming it.
- **Environment facts** (verified 2026-08-15): `curl` is blocked in the Bash sandbox, use `python3` urllib (the scripts do). No `timeout` CLI. Headless Chrome network fetch HANGS on this machine, do not use it. WAF'd sites 403 all server fetch but allow same-origin in-page `fetch()`.

## Inventory: server mode

1. `python3 "$SKILL/scripts/fetch_pages.py" --probe <url>` if the platform notes don't already say what works.
2. Get VDP URLs from the sitemap (fetch it with fetch_pages.py --urls mode or a small python one-liner), filter to NEW vehicles matching the `match` lists, keep 3-4 per model, append the recheck URLs, write `vdp_urls.txt`.
3. `python3 "$SKILL/scripts/crawl_inventory.py" --urls vdp_urls.txt --out "$DATA/{slug}" --dealer "{Name}"` — read only its one-line summary. Exit 2 = retry failing pages once via next strategy; exit 3 = circuit breaker, dealer `failed`.
4. Copy the rows from `$DATA/{slug}/inventory.json` into the fragment via a python one-liner (never through your context).

## Inventory: browser mode (WAF'd sites)

Use ONE browser tab on the dealer's domain; extraction happens in-page via `$SKILL/references/browser-extract.js`:

1. Surface order (retooled 2026-09-04): **Claude Browser pane** first (`mcp__Claude_Browser__*`: `tabs_create` → keep the `tabId` → `navigate {url, tabId}` → `javascript_tool {text, tabId}`; if the tools show as deferred, load them in ONE ToolSearch call: `select:mcp__Claude_Browser__tabs_context,mcp__Claude_Browser__tabs_create,mcp__Claude_Browser__tabs_close,mcp__Claude_Browser__navigate,mcp__Claude_Browser__javascript_tool,mcp__Claude_Browser__computer,mcp__Claude_Browser__read_network_requests`) → **Chrome extension** last (`mcp__claude-in-chrome__*` / Control_Chrome; if Chrome isn't running: `open -a "Google Chrome"`, wait ~8s; load its tools in ONE ToolSearch call only when you actually reach this tier). Pass `tabId` on EVERY Claude Browser call. 2 failed attempts on a surface = next surface; a fresh tab (`tabs_close` the stuck one, `tabs_create` a new one) counts as the second attempt. If the extension is not connected, mark the dealer `failed` with error `surface_exhausted`; never open the extension while tier 1 is still working.
2. Navigate to the dealer homepage in your tab (fresh tab per dealer, close it when done). Run SNIPPET A (fill MATCHES from the match lists). If `vdp_matched` is 0, navigate to the new-inventory SRP per model and use SNIPPET C per page instead.
3. Run SNIPPET B repeatedly until `done:true` (each call returns only compact rows). If it returns a circuit-breaker error, stop, mark `failed`.
4. Write the accumulated rows to the fragment (paste the small rows JSON into a Write; it is compact, ~100 bytes/row).

## Specials (lease + finance), both modes

1. Check the homepage AND dedicated specials pages: `/monthly-specials`, `/specials`, `/lease-specials`, `/offers`, per-brand pages (e.g. `/specials/jeep.htm`). Server mode: fetch with fetch_pages.py and read saved HTML *snippets* via grep, not whole files. Browser mode: navigate and read the page.
2. **Offers live inside banner images.** Never judge a banner by filename or alt text. Browser mode: screenshot each banner (advance carousels), zoom on disclaimers. Server mode: download image files (urllib) and Read them. Read the pixels.
3. Capture: model, trim, yr, payment, term, DAS ("due at signing"), down, miles/yr, MSRP if shown, the full offer text, and the FULL disclaimer text. Finance: APR, term, conditions.
4. **Honesty layer** (all brands, mandatory for CDJR): Call-for-Price → `call_for_price: 1`, price 0, never a number. Payment baking in non-universal rebates (Chrysler Capital bonus, returning lessee, military, conquest) → `payment_type: "conditional"` + `rebates_included` list; else `"clean"`. Unknown DAS stays 0 (the analytics flag it).
5. Zero offers found → only claim `verified_zero` in the dealer note after positively reading the specials page content including banners; otherwise note `needs_human_review`.

## Output: `$DATA/{dealer-slug}/fragment.json`

```json
{"dealer": {"name": "", "platform": "", "crawl_method": "sitemap+server|srp+server|browser-jsfetch|browser-srp",
            "status": "ok|partial|failed", "pages_crawled": 0,
            "notes": "verified_zero / needs_human_review / discoveries worth caching"},
 "lease_offers": [{"model":"","trim":"","yr":0,"pmt":0,"term_mo":0,"das":0,"down":0,"miles_yr":0,"msrp":0,
                   "payment_type":"clean|conditional","rebates_included":[],"flags":"",
                   "offer_text":"","disclaimer_text":"","source_url":"","parse_note":""}],
 "finance_offers": [{"model":"","trim":"","yr":0,"apr":0.0,"term_mo":0,"msrp":0,"conditions":"","source_url":"","parse_note":""}],
 "inventory": [{"vin":"","yr":0,"make":"","model":"","trim":"","version":"","msrp":0,"price":0,
                "call_for_price":0,"dom_displayed":0}],
 "errors": ["every error, verbatim enough to act on"]}
```

Status: `ok` = inventory AND specials both captured; `partial` = one of the two; `failed` = neither. Don't over-normalize model names, the merge script does canonical matching.

## Final message (your ONLY conversational output, ≤15 lines)

Dealer name, status, crawl_method, vehicles found, lease/finance offer counts, zero-offer verification state, every error, and any platform/URL discovery worth caching in clients.json. Nothing else — no tables, no row dumps.
