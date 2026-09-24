## Step 2: Scrape Brands (Parallel or Sequential)

### 2·0. Browser Pre-flight (MANDATORY, runs ONCE in the main context before any scraping)

The Chrome MCP tools are **deferred**: they must be loaded before use or every call fails with InputValidationError. Run this exact sequence:

1. **Load the tools in ONE batched ToolSearch call:** `select:mcp__claude-in-chrome__list_connected_browsers,mcp__claude-in-chrome__select_browser,mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__get_page_text,mcp__claude-in-chrome__javascript_tool,mcp__claude-in-chrome__find,mcp__claude-in-chrome__computer`. Never load them one at a time, and never call them unloaded.
2. `list_connected_browsers` → pick the browser with `isLocal: true`. If several are local, pick the most recently connected. Call `select_browser` with its deviceId. If NO browser is connected, skip straight to HTTP fallback mode (below) and tell Drew the Claude in Chrome extension isn't connected.
3. `tabs_context_mcp` with `createIfEmpty: true` to get a working tab.
4. **Probe navigation:** navigate that tab to the FIRST dealer URL of the first requested brand, then `get_page_text`. If real page content comes back, the browser path is GO.
5. **If the probe fails** (site-access denied, timeout, empty page): retry ONCE after 5 seconds. If it fails again, do NOT keep hammering the browser and do NOT touch the in-app Browser pane (`mcp__Claude_Browser__*` / preview tools, they require per-origin approval clicks and stall unattended runs; they are not part of this skill). Switch the whole run to **HTTP fallback mode** and note in the final summary that Chrome denied access so Drew can fix the extension's site-access setting (Chrome → Extensions → Claude → Site access → "On all sites").

**HTTP fallback mode** (proven to work on these dealer sites): fetch every page with `curl -sL -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36" <url>` via Bash. Grep the HTML for lease text (`per month`, `/mo`, `due at signing`) and `<img` src URLs, then download the banner images and `Read` the pixels exactly as in 2b, the banner-image pipeline is identical in both modes. Tag offers found this way with `parse_note: "scraped via HTTP fallback"`. The only thing HTTP mode can't do is click "Details" accordions; if a disclaimer is unreachable, note it rather than stalling.

Each brand is a self-contained scraping session. When **multiple brands** are requested, use **parallel mode** to scrape all brands simultaneously. For a **single brand**, use sequential mode (same as before).

### Parallel Mode (2+ brands)

When 2 or more brands are requested, use the orchestrator to prepare per-brand manifests and spawn parallel Task agents:

```bash
python3 "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/monthly-leasing/orchestrate_parallel.py" \
    --roster "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/monthly-leasing/dealer_roster.json" \
    --brands <brand_tokens> \
    --month YYYY-MM
```

The orchestrator outputs JSON with a `brand_manifests` dict. For each brand:
1. Extract the `agent_prompt` from the manifest
2. Spawn a **Task** agent (`subagent_type: "general-purpose"`) with that prompt
3. **Launch all brand agents in a single message** (parallel execution, foreground, NOT background)
4. Each agent scrapes its brand's dealers via browser and returns structured JSON in its response

**After all agents complete:**
1. Parse the JSON code block from each agent's response
2. Write each brand's data to `/tmp/lease_data_{brand_key}_{month}.json` using the Write tool
3. Proceed to Step 3 (merge + report)

**Key constraints:**
- **Run the 2·0 browser pre-flight BEFORE spawning agents.** The main context selects the browser and confirms site access once; agents must NOT call `list_connected_browsers` or `select_browser`. If the pre-flight ended in HTTP fallback mode, tell each agent (append one line to its prompt) to skip the browser entirely and scrape via curl.
- Subagents return their scraped data in their response; the main context writes the per-brand JSON files
- **Each agent MUST first load the Chrome tools with one batched ToolSearch call, then create its own browser tab** via `mcp__claude-in-chrome__tabs_create_mcp`: agents cannot share tabs (the agent prompt from the orchestrator already spells this out)
- **Do NOT use `run_in_background: true`**: use foreground agents so results are returned directly
- **No excessive screenshots**: agents must use `get_page_text` and `javascript_tool` as primary extraction methods, with a maximum of 2 screenshots total per agent to avoid "Request too large" failures
- If an agent fails or returns incomplete data, re-run it individually

### Sequential Mode (1 brand)

For a single brand, skip the orchestrator and scrape directly in the main context.

### 2a. Prepare

Load the brand's dealers and model dictionary from `dealer_roster.json`. Present a short plain-text plan in chat (or TodoWrite) listing only this brand's dealer domains. The 2·0 pre-flight already gave you a selected browser and a working tab; reuse that tab.

### 2b. For Each Dealer

**Visit the homepage FIRST (primary source):**
- Navigate to the dealer URL using `mcp__claude-in-chrome__navigate`
- Wait 3-4 seconds for the page to fully load (dealer sites are heavy)
- Use `mcp__claude-in-chrome__get_page_text` to extract visible text
- Use `mcp__claude-in-chrome__javascript_tool` to search the DOM for lease keywords if needed
- Extract lease offers from the homepage, look for hero sliders, banner tiles, and offer grids
- Record `page_type: "home"` for these offers

**ALWAYS visit the dedicated specials page too, do NOT stop at the homepage.** Most dealers keep their full monthly lease lineup on a dedicated page, NOT in homepage banners. A homepage with no visible offer does not mean the dealer has no specials. This is mandatory on every dealer, every run:
- Use `mcp__claude-in-chrome__find` (or read the nav) for links containing "specials", "monthly specials", "lease specials", "offers", "incentives", or "deals"
- Navigate to it. ALSO directly try these common paths even if no nav link is obvious, dealers hide them: `/monthly-specials`, `/monthly-specials/`, `/specials`, `/new-specials`, `/lease-specials`, `/new-vehicle-specials`, `/offers`, `/offers-incentives/?view=lease-offers`, `/incentives`, `/promotions/new/index.htm`, `/new-new-car-specials.htm`, and per-brand pages like `/specials/jeep.htm`, `/specials/ram.htm`
- Wait 3-4 seconds, extract text with `get_page_text`
- Record `page_type: "specials"` for these offers

**CRITICAL: offers are usually baked into BANNER IMAGES. You MUST read the image pixels, not just the filename or alt text.** Dealer offer banners (.jpg/.png/.webp) carry the payment, term, and due-at-signing as text rendered *inside the image*. `get_page_text` returns nothing for these and the alt text/filename only names the vehicle. Judging an image banner by its filename is the #1 cause of false "zero offers". When a specials page shows vehicle banners but text extraction finds no `$/mo`:
1. Enumerate the banner image URLs with `javascript_tool` (query `document.querySelectorAll('img')`, take `currentSrc`/`src`, strip the `?query`, keep the ones under `/uploads/`, `pictures.dealer.com`, or with vehicle names). Return PATH/URL only (no query strings) to avoid output blocks.
2. Download them with `Bash` (`curl -s -A "Mozilla/5.0" -o file.webp <url>`), convert webp→png if needed (`PIL`), and **`Read` each image to extract the pricing off the banner.** A stacked contact sheet works for a first pass; crop+upscale the disclaimer strip (`PIL`, LANCZOS, 3–5x) to read fine print (term, due-at-signing, mileage, expiration).
3. Record what you read. If the headline payment is legible but the fine print (term/DAS/miles) is not, capture the payment and set `parse_note` to "term/DAS not legible on banner, verify".

> [!warning] Screenshots are often blocked on dealer sites. Many dealer pages (PixelMotion, Dealer.com) never reach `document_idle` because of polling widgets, so `screenshot` and `get_page_text` time out. Do NOT treat that as "no offers". Fall back to `javascript_tool` to enumerate image URLs + DOM text, then download and `Read` the banner images. This always works.

**Extract lease offers from each page:**
- Match models against the model dictionary from `dealer_roster.json`
- Extract: payment ($XXX/mo), term (XX months), due at signing, mileage, expiration
- Capture the full disclaimer text: if hidden behind "Details", "View Offer", or accordion buttons, use `find` to locate and click them. If the disclaimer is inside a banner image, read it off the image.
- Scan disclaimer for info flags (see below)
- **Lease vs Finance:** Many tiles/banners show BOTH a lease payment and a finance APR side by side (e.g. "$418/mo OR 0% APR"). Extract ONLY the lease portion. A banner that shows only "$X off MSRP", "net cost", "sale price", or "X.X% APR" with no monthly lease payment is a PURCHASE offer, skip it (it is not a lease). Banners often say "not applicable on leases", that confirms purchase-only.
- **VIN:** Capture VIN if shown. If no VIN found in the disclaimer, set `parse_note` to "no VIN in disclaimer"

**Rate limiting:** Wait at least 3 seconds between page navigations.

**Per-dealer resilience:** If navigation or text extraction fails twice on a single dealer (denied, timeout, blank), scrape THAT dealer via the HTTP fallback (curl, see 2·0) and move on. Never burn more than 2 browser retries on one dealer, and never mark a dealer failed without trying HTTP mode first.

### 2c. Dealer Verification Checklist

After scraping ALL dealers for this brand, print a verification checklist:

```
### Dealer Verification — [Brand] ([N] dealers)
[x] Dealer Name — N offers
[x] Dealer Name — N offers
[ ] Dealer Name — 0 offers **RE-CHECKING...**
```

**For any dealer with 0 offers, you MUST run the full escalation before recording a zero:**
1. Confirm you actually loaded a dedicated **specials/monthly-specials/lease-specials page**: not just the homepage. If you only checked the homepage, that is NOT a verified result. Try the direct paths and per-brand specials pages listed in 2b.
2. On that specials page, enumerate every **banner image** with `javascript_tool`, download them, and `Read` the pixels to check for a monthly lease payment. Do not conclude "no offers" from filenames/alt text.
3. Use `javascript_tool` to scan the rendered DOM for `lease`, `$`, `/mo`, `per month`, `due at signing` (sanitize output if it gets blocked).

Then classify the dealer:
- **`ok`**: lease offers found (record them).
- **`verified_zero`**: ONLY when you read the actual specials-page content (text AND banner images) and it shows purchase/APR/cash offers with NO monthly lease payment, OR the banners explicitly say "not applicable on leases" / "sale price does not apply to a lease". You must have positively read real offer content to claim this.
- **`needs_human_review`**: when you could NOT positively confirm either way: a specials page wouldn't render, banner images wouldn't load, the page timed out, or you only had the homepage. Put what you tried and what blocked you in the `note`.

**Reality check on the date:** it would be unusual for a CDJR/import dealer to have ZERO lease specials posted past roughly the 5th of the month. If it is mid-to-late month and you are about to record `verified_zero` for a dealer, treat that as a signal you probably missed an image-based specials page, go back and read the banner images first. If after a genuine specials-page + banner-image read you still cannot find a lease, prefer `needs_human_review` over `verified_zero` unless the page explicitly excludes leases.

This verification step is **mandatory**: do not skip it.

### 2d. Write Brand Results

Write the brand's results to a per-brand JSON file:

```
/tmp/lease_data_{brand_key}_{month}.json
```

Example: `/tmp/lease_data_nissan_2026-02.json`

Use this exact structure:
```json
{
  "metadata": {
    "brand": "nissan",
    "brand_display": "Nissan",
    "cap_date": "YYYY-MM-DD",
    "month": "YYYY-MM",
    "run_timestamp": "ISO 8601 timestamp",
    "dealers_in_roster": 7,
    "dealers_scraped": 7,
    "dealers_with_offers": 6,
    "total_offers": 40
  },
  "dealer_status": [
    {
      "name": "Nissan of Irvine",
      "url": "https://www.nissanofirvine.com/",
      "offers_found": 6,
      "status": "ok",
      "note": ""
    },
    {
      "name": "Nissan of Orange",
      "url": "https://www.nissanorange.com/",
      "offers_found": 0,
      "status": "verified_zero",
      "note": "No lease offers on homepage or specials page. Confirmed via re-check."
    }
  ],
  "offers": [
    {
      "brand": "Nissan",
      "dealer_name": "Nissan of Irvine",
      "dealer_url": "https://www.nissanofirvine.com/",
      "source_url": "https://www.nissanofirvine.com/",
      "page_type": "home",
      "yr": 2026,
      "make": "Nissan",
      "model": "Rogue",
      "trim": "SV",
      "msrp": 32500,
      "pmt": 299,
      "term_mo": 36,
      "das": 3999,
      "miles_yr": 10000,
      "sec_dep": "waived",
      "exp": "3/3/2026",
      "vin": "5N1BT3BB4TC123456",
      "is_national": 0,
      "disclaimer_scope": "offer",
      "disclaimer_text": "Full disclaimer here...",
      "info_flags": "ACQ_FEE|TTL",
      "parse_note": "",
      "source_credit": "DigitalCLIQ"
    }
  ]
}
```

**Field rules:**
- Every offer gets `source_credit: "DigitalCLIQ"`
- If a field is unknown, use `0` for numbers, `""` for strings
- `parse_note` should explain issues: "no VIN in disclaimer", "disclaimer truncated", "read from banner image", "term/DAS not legible on banner, verify", "model unclear"
- `status` (per dealer): one of `"ok"`, `"verified_zero"`, or `"needs_human_review"` (see 2c for the rule on which to use)
- `is_national`: set to `1` if the offer appears to be a national/manufacturer offer (identical across dealers)
- `page_type`: `"home"` or `"specials"`
- `disclaimer_scope`: `"offer"` if tied to specific offer, `"page"` if page-wide disclaimer
- **No theme fields**: theme detection is not used
- **No stock number**: only capture VIN
