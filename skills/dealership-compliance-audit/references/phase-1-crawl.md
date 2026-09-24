## Phase 1: Crawl & Extract Page Data

> [!important] Crawl on the Claude Browser; cascade, never grind on one method
> Dealer sites are commonly anti-scraper (WAF 403s on server fetch) AND ship heavy
> front-ends (Dealer Inspire / Cars.com VDPs and inventory-search VLPs can hard-hang
> a renderer). Do NOT keep retrying the surface that just failed. Cascade the moment
> a method stalls twice, in THIS order (see "Browser Surface Order" in SKILL.md):
> 1. **Claude Browser** (in-app pane, `mcp__Claude_Browser__*`): the default for every
>    page, no auth, no approval prompt. Open with `preview_start {url}` or
>    `tabs_create` + `navigate`, extract with `javascript_tool`, always with `tabId`.
>    If a page hangs the pane (stops compositing / eval times out), close that tab
>    and retry ONCE in a fresh tab. If it hangs again it will keep hanging: cascade.
> 2. **Server fetch** (`scripts/fallback_crawl.py`): zero-token, uncapped body. Use it
>    on every run for the text-only `finance` page, and as the first fallback for any
>    page the Claude Browser could not render. It 403s on scraper-blocking WAFs.
> 3. **Chrome extension** (`mcp__claude-in-chrome__*`, Drew's real logged-in Chrome):
>    LAST resort, only after tiers 1 and 2 both failed on the same page. Needs a
>    one-time user approval (`list_connected_browsers`, then `select_browser`). If the
>    extension is not connected, do not wait for it: write
>    `{"error": "surface_exhausted"}` for that page and keep the run moving.
> 4. **Lighter/curated pages**: when full inventory-search VLPs and VDPs hang on every
>    surface, the curated specials listings (`/new-vehicles/new-vehicle-specials/`,
>    `/used-vehicles/pre-owned-vehicle-specials/`) carry full per-vehicle pricing + VINs
>    and load reliably; use them for VDP-level pricing and record blocked per-VDP
>    disclaimer extraction as needs-human-review, never as a violation.
>
> The point: try more than one way, every time. A stalled crawl is a signal to switch
> surfaces, not to retry. Chrome is a rescue, not a starting point.

**PARALLEL CRAWL (DEFAULT):** The page types below (homepage, specials, VLP, the
sampled VDPs, used/CPO, finance, privacy policy) are independent, crawl them
concurrently, not in sequence. Launch one foreground Task agent per page type in a
SINGLE message. Each agent creates its OWN Claude Browser tab via
`mcp__Claude_Browser__tabs_create`, keeps the returned `tabId`, and passes that `tabId`
on every `navigate` / `javascript_tool` / `tabs_close` call. Omitting `tabId` acts on
the fronted tab, which during a parallel crawl is another agent's page. Close the tab
when the fragment is written.

**TOKEN DISCIPLINE: agents write fragments to disk, they do NOT return page text.**
Each crawl agent writes its extracted JSON straight to
`/tmp/{safe_client}_page_{pagekey}.json` and returns to the main context ONLY a
one-line status, never the page body. For example:
`specials: ok: 4,210 chars, 6 disclaimers, 3 expand buttons clicked` or
`privacy_policy: error: 404`. The 12K–15K-char excerpts stay on disk where the
Python engine reads them; they must never flow back through the main context. This
is the single biggest token cost in the whole audit, keep it on disk.

A page that blocks or 404s writes `{"page": ..., "error": "<reason>"}` to its
fragment file: the audit proceeds and the gap is recorded as a finding, never
papered over. (Phase 2c stays a SINGLE focused agent by design, do not fan it out;
the token consolidation there is intentional.)

**Server-fetch the text-only pages to save a browser tab.** The `finance` page is
pure text signal (no JS galleries, no expand buttons). Fetch it server-side with zero
browser and zero tokens instead of spending a browser agent on it:
`python3 scripts/fallback_crawl.py --page finance --url <finance_url> --out /tmp/{safe_client}_page_finance.json`.
Keep the Claude Browser for homepage (privacy/forms), specials (expand buttons),
VLP/used (JS inventory), and the sampled VDPs, where structured DOM extraction matters.

This phase uses the Claude Browser to crawl the dealership website and extract structured data from each key page. All data is saved to a single JSON file for the analysis agents.

### Step 1.1: Open the Claude Browser and Navigate to Homepage

```
mcp__Claude_Browser__preview_start {url: <url>}   → opens the pane, returns tabId
   (or, from a parallel crawl agent: mcp__Claude_Browser__tabs_create → tabId,
    then mcp__Claude_Browser__navigate {url, tabId})
mcp__Claude_Browser__computer {action: "wait", duration: 3, tabId}
```

Do NOT call `mcp__claude-in-chrome__tabs_context_mcp` here. The Chrome extension is
tier 3 in the cascade and is opened only after the Claude Browser and the server
fetch have both failed on a specific page.

### Step 1.2: Discover Navigation URLs

Use `mcp__Claude_Browser__javascript_tool` (with the homepage `tabId`) to extract all nav links. This avoids 404 errors from guessing URLs:

```javascript
// Extract all navigation links from the site
Array.from(document.querySelectorAll('nav a, [role="navigation"] a, header a'))
  .map(a => ({ text: a.textContent.trim(), href: a.href }))
  .filter(l => l.href.startsWith(window.location.origin) && l.text.length > 0)
  .reduce((acc, l) => {
    if (!acc.find(x => x.href === l.href)) acc.push(l);
    return acc;
  }, [])
  .slice(0, 50)
```

From the nav links, identify these target pages:
- **specials**: URL containing "special", "offers", "deals", or "lease"
- **new_inventory**: URL containing "new-vehicles", "new-inventory", or "new"
- **used_inventory**: URL containing "used", "pre-owned", or "preowned"
- **cpo**: URL containing "certified", "cpo"
- **finance**: URL containing "finance", "financing", "credit"
- **privacy_policy**: Detected from homepage extraction `privacy.privacy_policy_url` (may be in footer, not nav)

### Step 1.3: Extract Data from Each Page

**CRITICAL: Use `mcp__Claude_Browser__javascript_tool` for ALL page data extraction.** Do NOT use `get_page_text` or `read_page`, these fail on large inventory pages.

For each discovered page: `navigate` (with `tabId`), wait 2 seconds, then run that page type's extraction
JS from `references/page-extraction.md` (one section per page type, each crawl agent
reads ONLY the section for its page type):

- **Homepage**: pricing claims, disclaimers, privacy/footer links, lead-form consent signals
- **VLP (new inventory)**: listing pricing, strike-through/discount claims
- **VDP: RANDOM MULTI-SAMPLE**, sampling rules plus per-vehicle extraction; every sampled VDP gets the full extraction
- **Specials page**: offer tiles, expand-button clicks, disclaimer capture
- **Used/CPO page**: used listing pricing and certification claims
- **Finance page**: text-only signal (may be server-fetched, see the Phase 1 note above)
- **Privacy policy**: CCPA/CPRA signals, GPC disclosure, financial-incentive notice, request methods


### Step 1.4: Save Crawl Data

Assemble all extracted page data into a single JSON object and write to `/tmp/{safe_client}_crawl_data.json`:

```json
{
  "url": "https://www.sterlingbmw.com",
  "brand": "bmw",
  "client": "Sterling BMW",
  "crawl_date": "2026-03-05",
  "vdp_sample_meta": {
    "candidates_found": 28,
    "sampled": [
      {"page_key": "vdp",   "vin": "WBA...ABCD", "url": "https://.../inventory/new-2026-...", "condition": "new"},
      {"page_key": "vdp_2", "vin": "5N1...WXYZ", "url": "https://.../inventory/used-2023-...", "condition": "used"},
      {"page_key": "vdp_3", "vin": "1C4...QRST", "url": "https://.../inventory/new-2026-...", "condition": "new"}
    ]
  },
  "pages": {
    "homepage": { ... },
    "specials": { ... },
    "vlp": { ... },
    "vdp": { ... },
    "vdp_2": { ... },
    "vdp_3": { ... },
    "used": { ... },
    "cpo": { ... },
    "finance": { ... },
    "privacy_policy": { ... }
  }
}
```

Where `safe_client` = client name lowercased with spaces replaced by underscores.
`vdp`, `vdp_2`, `vdp_3`, ... are the randomly-sampled vehicle detail pages; every
per-vehicle check runs against all of them.

**If a page fails to load or returns a 404**, set its value to `{"error": "404", "url": "..."}` and move on. Do NOT retry or guess alternate URLs, use only URLs discovered from the nav in Step 1.2.

---
