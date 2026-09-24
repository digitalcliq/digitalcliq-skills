#!/usr/bin/env python3
"""
DigitalCLIQ — Parallel Lease Scraping Orchestrator

Generates per-brand scraping manifests and agent prompts for parallel
Task agent execution. Each agent scrapes one brand independently on the
built-in Claude Browser (own tab; curl is the fallback, the Chrome extension
the last resort), returns structured JSON, and the main context writes files
and runs merge + report.

Usage:
    python3 orchestrate_parallel.py \
        --roster /path/to/dealer_roster.json \
        --brands nissan bmw cdjr \
        --month 2026-03

    # Resolve aliases:
    python3 orchestrate_parallel.py \
        --roster /path/to/dealer_roster.json \
        --brands all \
        --month 2026-03

Output:
    Prints JSON to stdout with:
    - resolved brand list
    - per-brand agent prompts (ready to pass to Task tool)
    - per-brand manifest data (dealers, models)
"""

import argparse
import json
import os
import sys
import textwrap
from datetime import datetime


def load_roster(roster_path):
    """Load dealer_roster.json."""
    with open(roster_path, "r") as f:
        return json.load(f)


def resolve_brands(tokens, roster):
    """
    Resolve brand tokens against aliases and brand keys.
    Returns deduplicated, ordered list of brand keys.
    """
    aliases = roster.get("brand_aliases", {})
    brands_dict = roster.get("brands", {})
    resolved = []
    errors = []

    for token in tokens:
        t = token.lower().strip()
        if t in aliases:
            resolved.extend(aliases[t])
        elif t in brands_dict:
            resolved.append(t)
        else:
            errors.append(t)

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for b in resolved:
        if b not in seen:
            seen.add(b)
            deduped.append(b)

    return deduped, errors


def build_manifest(brand_key, roster, month, cap_date):
    """Build a scraping manifest for one brand."""
    brand_info = roster["brands"][brand_key]
    return {
        "brand_key": brand_key,
        "brand_display": brand_info["display_name"],
        "make": brand_info["make"],
        "month": month,
        "cap_date": cap_date,
        "models": brand_info["models"],
        "dealers": brand_info["dealers"],
        "dealer_count": len(brand_info["dealers"]),
        "output_path": f"/tmp/lease_data_{brand_key}_{month}.json",
    }


def build_agent_prompt(manifest):
    """
    Generate a self-contained scraping prompt for a Task agent.
    The agent uses the Claude Browser MCP tools (mcp__Claude_Browser__*)
    to scrape all dealers for one brand and returns the results as JSON
    in its response. Surface order per SKILL.md "Browser Surface Order":
    Claude Browser -> curl -> Chrome extension.
    """
    brand = manifest["brand_display"]
    brand_key = manifest["brand_key"]
    make = manifest["make"]
    month = manifest["month"]
    cap_date = manifest["cap_date"]
    models = manifest["models"]
    dealers = manifest["dealers"]

    dealer_lines = "\n".join(
        f"  {i+1}. {d['name']} — {d['url']}"
        for i, d in enumerate(dealers)
    )
    model_csv = ", ".join(models)

    # Info flag definitions
    info_flags_block = textwrap.dedent("""\
        LOYALTY — mentions loyalty
        CONQUEST — mentions conquest
        ACQ_FEE — acquisition fee
        TTL — tax, title, license
        MSD — multiple security deposits
        TRADE_REQ — trade required
        APR_CREDIT — on approved credit / tiered credit
        DEALER_CONTRIB — dealer contribution""")

    prompt = textwrap.dedent(f"""\
        You are scraping lease specials for **{brand}** dealers. This is one brand
        in a parallel multi-brand scrape. Your job: visit each dealer's website,
        extract new vehicle LEASE offers, and return ALL results as a single JSON
        object at the end of your response.

        ## CRITICAL: Browser surface = the built-in Claude Browser
        All page visits run on the in-app **Claude Browser** (tools named
        `mcp__Claude_Browser__*`). Drew's real Chrome via the extension
        (`mcp__claude-in-chrome__*`) is the LAST resort, never the default.
        Do NOT call `mcp__claude-in-chrome__list_connected_browsers`,
        `select_browser`, or any `mcp__claude-in-chrome__*` tool unless the
        cascade below reaches tier 3.

        **FIRST**, create YOUR OWN dedicated tab:
        `mcp__Claude_Browser__tabs_create` -> returns a `tabId`. Pass that
        `tabId` on EVERY call you make (`navigate`, `get_page_text`,
        `javascript_tool`, `find`, `computer`, `tabs_close`). The pane is
        shared with the other brand agents; a call without `tabId` lands on
        someone else's page. Do NOT reuse tabs from other agents. Close your
        tab (`tabs_close {{tabId}}`) when you are done.
        (If the `mcp__Claude_Browser__*` tools show as deferred, load them in
        ONE batched ToolSearch call:
        `select:mcp__Claude_Browser__tabs_context,mcp__Claude_Browser__tabs_create,mcp__Claude_Browser__tabs_close,mcp__Claude_Browser__navigate,mcp__Claude_Browser__get_page_text,mcp__Claude_Browser__javascript_tool,mcp__Claude_Browser__find,mcp__Claude_Browser__computer`.)

        ## CASCADE (per dealer, never stall on one surface)
        Tier 1, Claude Browser: two attempts max per dealer. First in your
        tab; if it hangs or returns empty, close that tab, `tabs_create` a
        fresh one, `navigate` again with the NEW tabId. If the second attempt
        also fails, cascade. Never loop a third time.

        Tier 2, direct HTTP mode (proven on these dealer sites):
        - Fetch pages with `Bash`:
          `curl -sL -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36" <url>`
        - Grep the HTML for lease text (`$XXX ... per month`, `/mo`,
          `due at signing`) and for `<img` src URLs on specials pages.
        - Download the banner images with curl and `Read` the pixels exactly
          as described below. The banner-image pipeline is identical in both
          modes.
        - Note `"parse_note": "scraped via HTTP fallback"` on offers found
          this way, and mention the mode switch in the dealer_status note.

        Tier 3, Chrome extension (`mcp__claude-in-chrome__*`): ONLY if tier 1
        hung twice AND tier 2 curl returned 403/blocked/empty for the SAME
        dealer. Load its tools in one ToolSearch call, `list_connected_browsers`
        -> the `isLocal: true` browser -> `select_browser`, then
        `tabs_create_mcp` and work in that tab. Two attempts max. If no
        extension is connected, mark the dealer `needs_human_review` with
        note `surface_exhausted` and move on. Never end with zero data
        because a surface would not cooperate.

        ## CRITICAL: Read banner images, don't screenshot the page
        Dealer offers are almost always rendered as text INSIDE banner images
        (.jpg/.png/.webp). `get_page_text` returns nothing for these and the
        filename/alt text only names the vehicle. A browser `screenshot` is often
        BLOCKED on dealer sites (the page never reaches document_idle). So:
        - Use `get_page_text` and `javascript_tool` for any real page text.
        - When a specials page shows vehicle banners but no `$/mo` text,
          enumerate the banner image URLs with `javascript_tool`
          (`document.querySelectorAll('img')`, take src/currentSrc, strip the
          `?query`, keep ones under `/uploads/`, `pictures.dealer.com`, or with
          vehicle names — return PATH/URL only to avoid output blocks).
        - Then DOWNLOAD them with `Bash` (`curl -s -A "Mozilla/5.0" -o f.webp <url>`),
          convert webp→png with PIL if needed, and `Read` each image to read the
          payment/term/DAS off the banner. Crop+upscale the fine-print strip
          (PIL, LANCZOS 3-5x) for term/DAS/mileage/expiration.
        - Do NOT rely on browser screenshots. Reading downloaded images always works.

        ## Brand Details
        - Brand key: `{brand_key}`
        - Display name: `{brand}`
        - Make: `{make}`
        - Month: `{month}`
        - Cap date: `{cap_date}`
        - Model dictionary: {model_csv}

        ## Dealers to Scrape
        {dealer_lines}

        ## Scraping Protocol

        For EACH dealer:

        1. **Homepage first** — navigate to the dealer URL, wait 3-4 seconds for
           the page to load (dealer sites are heavy). Use `get_page_text` to
           extract visible text. Use `javascript_tool` to search for lease
           keywords if needed. Extract any lease offers. Record `page_type: "home"`.

        2. **ALWAYS visit a dedicated specials page too — never stop at the
           homepage.** The full monthly lease lineup almost always lives on a
           specials page, not in homepage banners. Look for nav links containing
           "specials", "monthly specials", "lease specials", "offers",
           "incentives", or "deals". ALSO directly try these paths even with no
           obvious nav link: `/monthly-specials/`, `/specials`, `/new-specials`,
           `/lease-specials`, `/new-vehicle-specials`, `/offers`,
           `/offers-incentives/?view=lease-offers`, `/incentives`,
           `/promotions/new/index.htm`, `/new-new-car-specials.htm`, and per-brand
           pages like `/specials/jeep.htm`, `/specials/ram.htm`. Read banner
           images on these pages (see above). Record `page_type: "specials"`.

        3. **Lease vs Finance** — many tiles/banners show BOTH lease and finance
           side by side (e.g. "$418/mo OR 0% APR"). Extract ONLY the lease portion.
           A banner showing only "$X off MSRP", "net cost", "sale price", or
           "X.X% APR" with no monthly lease payment is a PURCHASE offer — skip it.
           Banners that say "not applicable on leases" confirm purchase-only.

        4. **Disclaimers** — capture the full disclaimer text. If hidden behind
           "Details", "View Offer", or accordion buttons, click to expand them.
           Scan disclaimers for info flags (see below).

        5. **Model matching** — always match against the model dictionary above
           before recording. If a model name doesn't match, use the closest match
           or note the issue.

        6. **Wait 3+ seconds** between page navigations (rate limiting).

        ## Dealer Verification Checklist

        After scraping ALL {len(dealers)} dealers, re-verify any dealer that had
        0 offers BEFORE recording a zero:
        - Confirm you actually loaded a dedicated specials/monthly-specials page,
          not just the homepage. If you only saw the homepage, that is not verified.
        - Enumerate the specials-page banner images, download them, and `Read` the
          pixels for a monthly lease payment. Do not judge by filename/alt text.
        - Then classify:
          - `ok` — lease offers found.
          - `verified_zero` — ONLY if you read the actual specials content (text +
            banner images) and it shows purchase/APR/cash with NO monthly lease
            payment, or banners explicitly say "not applicable on leases".
          - `needs_human_review` — if you could not confirm either way (page would
            not render, images would not load, only homepage available). Put what
            you tried and what blocked you in `note`.
        - Date reality check: past ~the 5th of the month, a dealer with ZERO lease
          specials is rare. If you are about to record `verified_zero` mid/late
          month, you probably missed an image-based specials page — go read the
          banner images first. Prefer `needs_human_review` over `verified_zero`
          unless the page explicitly excludes leases.

        ## Info Flags (scan disclaimers)
        {info_flags_block}

        Record as pipe-delimited: e.g. `ACQ_FEE|TTL|LOYALTY`

        ## Output Format

        IMPORTANT: At the end of your response, output a JSON code block with
        EXACTLY this structure. The JSON must be inside a ```json fenced block
        so it can be parsed:

        ```json
        {{{{
          "metadata": {{{{
            "brand": "{brand_key}",
            "brand_display": "{brand}",
            "cap_date": "{cap_date}",
            "month": "{month}",
            "run_timestamp": "<ISO 8601 timestamp when you finish>",
            "dealers_in_roster": {len(dealers)},
            "dealers_scraped": <number you actually visited>,
            "dealers_with_offers": <number that had >= 1 offer>,
            "total_offers": <total offer count>
          }}}},
          "dealer_status": [
            {{{{
              "name": "<dealer name>",
              "url": "<dealer url>",
              "offers_found": <count>,
              "status": "ok" or "verified_zero" or "needs_human_review",
              "note": "<any notes>"
            }}}}
          ],
          "offers": [
            {{{{
              "brand": "{brand}",
              "dealer_name": "<name>",
              "dealer_url": "<url>",
              "source_url": "<page url where offer was found>",
              "page_type": "home" or "specials",
              "yr": <model year int>,
              "make": "{make}",
              "model": "<from model dictionary>",
              "trim": "<trim or empty string>",
              "msrp": <int or 0>,
              "pmt": <monthly payment int>,
              "term_mo": <term months int>,
              "das": <due at signing int>,
              "miles_yr": <annual miles int>,
              "sec_dep": "<waived or amount or empty>",
              "exp": "<M/D/YYYY or empty>",
              "vin": "<VIN or empty>",
              "is_national": <0 or 1>,
              "disclaimer_scope": "offer" or "page",
              "disclaimer_text": "<full disclaimer>",
              "info_flags": "<PIPE|DELIMITED|FLAGS>",
              "parse_note": "<issues or empty>",
              "source_credit": "DigitalCLIQ"
            }}}}
          ]
        }}}}
        ```

        ## Field Defaults
        - Unknown numbers: use `0`
        - Unknown strings: use `""`
        - Every offer: `source_credit` = `"DigitalCLIQ"`
        - `parse_note`: explain issues ("no VIN in disclaimer", "image only offer", "model unclear")
        - `is_national`: `1` if manufacturer/national offer, `0` otherwise

        ## Exclusions
        Skip: used vehicles, service coupons, finance-only offers, APR-only offers.

        ## Final Notes
        - Use `get_page_text` and `javascript_tool` as primary extraction methods;
          for image banners, download with `Bash` curl and `Read` the pixels.
        - Browser screenshots are often blocked on dealer sites — don't depend on
          them, and never treat a blocked screenshot/timeout as "no offers".
        - Always check a dedicated specials page, not just the homepage.
        - Be patient with page loads (3-4 seconds)
        - No fabrication — if you can't extract a field, use defaults and note it.
          If a banner's headline payment is legible but fine print isn't, capture
          the payment and note "term/DAS not legible on banner — verify".
        - The JSON code block at the end is CRITICAL — it will be parsed programmatically
        """)

    return prompt.strip()


def main():
    parser = argparse.ArgumentParser(
        description="Generate parallel lease scraping manifests and agent prompts"
    )
    parser.add_argument("--roster", required=True, help="Path to dealer_roster.json")
    parser.add_argument("--brands", nargs="+", required=True,
                        help="Brand tokens (keys or aliases like 'all', 'chevy')")
    parser.add_argument("--month", default=None,
                        help="Month YYYY-MM (default: current month)")
    parser.add_argument("--prompts-only", action="store_true",
                        help="Output only the agent prompts (no manifest files)")
    args = parser.parse_args()

    if args.month is None:
        args.month = datetime.now().strftime("%Y-%m")

    roster = load_roster(args.roster)
    brand_keys, errors = resolve_brands(args.brands, roster)

    if errors:
        valid = list(roster.get("brands", {}).keys())
        valid_aliases = list(roster.get("brand_aliases", {}).keys())
        print(f"ERROR: Unrecognized brand tokens: {errors}", file=sys.stderr)
        print(f"Valid brands: {valid}", file=sys.stderr)
        print(f"Valid aliases: {valid_aliases}", file=sys.stderr)
        sys.exit(1)

    if not brand_keys:
        print("ERROR: No brands resolved from input tokens.", file=sys.stderr)
        sys.exit(1)

    cap_date = datetime.now().strftime("%Y-%m-%d")

    # Build per-brand manifests and prompts
    output = {
        "month": args.month,
        "cap_date": cap_date,
        "brands": brand_keys,
        "total_dealers": 0,
        "brand_manifests": {},
    }

    for bk in brand_keys:
        manifest = build_manifest(bk, roster, args.month, cap_date)
        prompt = build_agent_prompt(manifest)

        output["brand_manifests"][bk] = {
            "brand_display": manifest["brand_display"],
            "dealer_count": manifest["dealer_count"],
            "output_path": manifest["output_path"],
            "models": manifest["models"],
            "dealers": manifest["dealers"],
            "agent_prompt": prompt,
        }
        output["total_dealers"] += manifest["dealer_count"]

        # Write manifest file to /tmp/ for reference
        if not args.prompts_only:
            manifest_path = f"/tmp/lease_manifest_{bk}_{args.month}.json"
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)

    # Print summary to stderr
    print(f"\nParallel Lease Scrape — {args.month}", file=sys.stderr)
    print(f"Brands: {', '.join(bk.upper() if bk == 'cdjr' else bk.capitalize() for bk in brand_keys)}", file=sys.stderr)
    print(f"Total dealers: {output['total_dealers']}", file=sys.stderr)
    for bk in brand_keys:
        m = output["brand_manifests"][bk]
        print(f"  {m['brand_display']}: {m['dealer_count']} dealers", file=sys.stderr)
    print(f"\nReady for parallel Task agent dispatch.", file=sys.stderr)

    # Output full JSON to stdout (for Claude to parse)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
