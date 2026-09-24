---
name: onlinereputation
description: >-
  Pulls live online reputation data (Google, Yelp, DealerRater, CarFax) for an
  automotive dealership and 3 closest same-brand competitors, then generates a
  branded DigitalCLIQ PDF with ratings, review highlights, themes, competitor
  comparison, recommendations, SEO/LLM impact, and month-over-month delta tracking.
  Use when Drew says /onlinereputation, "reputation report", "review report", or
  asks how a dealership's online reviews or ratings look.
argument-hint: '"Dealer Name" "City, State"'
allowed-tools: mcp__claude-in-chrome__navigate, mcp__claude-in-chrome__get_page_text, mcp__claude-in-chrome__read_page, mcp__claude-in-chrome__javascript_tool, mcp__claude-in-chrome__computer, mcp__claude-in-chrome__find, mcp__claude-in-chrome__tabs_create_mcp, mcp__claude-in-chrome__tabs_close_mcp, mcp__claude-in-chrome__tabs_context_mcp, WebSearch, WebFetch, Bash, Read, Write, Edit, Glob, Grep, Agent, TodoWrite
---

> [!important] Pre-flight: load the facts ledger FIRST
> Before doing anything else, read `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Context/vault-facts.md` and obey it. It is the source of truth for: output location (always the vault `outputs/` folder, never the Desktop or the input file's directory), the canonical working folder (the vault root, never an old/legacy folder), the DigitalCLIQ Master calendar, the canonical logo path, and correct client/competitor names (e.g. "BMW of Buena Park (AutoNation)" not "Shelly BMW"; LOGO Cargo is a hostile competitor, not an Atlas partner). Validate every output path and every client/competitor name against the ledger before writing. If a fact you need is missing from the ledger, do not guess: check the vault and flag it.

# Online Reputation Report: DigitalCLIQ

## Overview

This skill collects live online review data for an automotive dealership and its
3 closest same-brand competitors across **Google Reviews, Yelp, DealerRater, and
CarFax**. It produces a branded DigitalCLIQ PDF report with:

- Overall ratings & review counts per platform
- Last 5 positive (4-5 ★) and last 5 negative (1-3 ★) reviews per platform
- Common themes / trends from the last 25 reviews
- Side-by-side competitor comparison table
- What competitors are doing right (from their 10 most recent reviews)
- Quick-bullet recommendations
- SEO & LLM impact section (standard on every report)
- Month-over-month delta tracking (rating & review count changes)

## DigitalCLIQ Design System (mandatory)

<!-- design-system-block v1 · do not edit per-skill · source: Resources/design-system/ -->

Every file this skill ships (PDF, DOCX, XLSX, PPTX, HTML) is built to `Resources/design-system/Design-System.md` and must pass the `Resources/design-system/Visual-QA.md` render gate before it is declared done. This section overrides any conflicting styling instruction elsewhere in this skill.

1. **Read first.** `Resources/design-system/Design-System.md` plus the Branding and render-gate sections of `Context/vault-facts.md`, before generating anything.
2. **Palette.** Digital Blue `#405FAB`, Sky Blue `#6B9DD4`, Warm Grey `#949592`, dark navys `#070A15` / `#10162A` / `#151E37` / Card Navy `#131B30`, Callout Tint `#EDF2F9`, Card White `#FBFBFD`, Tile Blue `#2E4780`, borders `#D8E1F0`. No color outside the Design-System token table. Tier/score/status coding uses palette treatments only (Sky Blue family = strong, Warm Grey = weak, Digital Blue = emphasis) with explicit text labels carrying the meaning. OEM brand colors inside client-specific charts are the only exception. Never legacy `#0D1B2A`-era navys, never default chart rainbows (red/orange/green).
3. **Fonts.** Dosis carries structure (headings, stats, labels), Roboto Slab carries reading (body). Confirm they resolve before generating (`system_profiler SPFontsDataType | grep -ci dosis` > 0); install from `Resources/brand-assets/fonts/` if missing. Arial/Calibri/Helvetica in output = FAIL.
4. **Logo.** WHITE knockout `Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png` on blue/dark backgrounds ONLY; FULL-COLOR `Resources/brand-assets/classic-digital-cliq-logo-solid-1000px-wide copy.png` on white/light ONLY. Default header = Digital Blue masthead band (~0.6in) with the white logo (~0.35in tall) left-aligned. A missing logo fails loudly, never silently.
5. **Cover.** The canonical cover comes from `Resources/design-system/templates/` (`cover-portrait.html` for documents, `cover-16x9.html` for decks). Never hand-build a cover per file.
6. **Visual-first.** Build pages from the Design-System component library: stat cards, stat bands, callout bars, icon tiles, numbered list cards, comparison splits, ghost numerals, running furniture. A wall-of-text page is a DEFECT. Max ~55% of any page as body text.
7. **Render gate.** `python3 Resources/design-system/templates/render_check.py <file>`, then visually READ every rendered page against the Visual-QA checklist. Fix in the generator, re-render, repeat until two consecutive fully-clean passes. Report passes run and defects caught to Drew.
8. **Staging.** Deliverables land in `outputs/` first, then file to the owning client's `Projects/{CODE}/deliverables/` (creative to `social-assets/` / `blog-assets/`). Never the Desktop, never next to the input file.

## Invocation

```
/onlinereputation "Dealer Name" "City, State"
```

**Examples:**
```
/onlinereputation "McPeek Dodge Chrysler Jeep Ram" "Anaheim, CA"
/onlinereputation "Sterling BMW" "Newport Beach, CA"
/onlinereputation "Nissan of Irvine" "Irvine, CA"
```

Arguments are passed via `$ARGUMENTS`. Parse the dealer name (first quoted string)
and location (second quoted string).

---

## Process

### Step 0: Parse Arguments

No pip installs needed. The PDF generator is an HTML + CSS pipeline per Design-System §4: it renders via WeasyPrint when importable and falls back to Chrome headless `--print-to-pdf` automatically (the sanctioned path on this machine). Brand fonts are embedded via `@font-face` from `Resources/brand-assets/fonts/`; a missing font or logo fails loudly.

Parse `$ARGUMENTS` to extract:
- `dealer_name`: the dealership name (first quoted string)
- `dealer_location`: city/state (second quoted string)

### Step 1: Identify the Dealer & Brand

Use **WebSearch** to search: `"{dealer_name}" {dealer_location} dealership`

From results, identify:
- The dealer's **brand** (e.g., CDJR, BMW, Nissan, Chevrolet, Ford, etc.)
- The dealer's **full address** (street, city, state, zip)

### Step 2: Find 3 Closest Same-Brand Competitors

Use **WebSearch**: `{brand} dealership near {dealer_location}` or
`{brand} dealers closest to {dealer_name} {dealer_location}`

Identify the **3 closest same-brand dealerships** by geographic distance.
Record their names and approximate locations.

### Step 3: Collect Review Data (Browser)

**PARALLEL COLLECTION (DEFAULT: never collect sequentially):** Launch one foreground Task agent per dealer (subject + 3 competitors = 4 agents) in a SINGLE message. Each agent:

- Creates its OWN browser tab via `tabs_create_mcp` as its first action and passes that tabId on every call, never act on another agent's tab
- Collects all 4 platforms (3a–3d below) for its one dealer
- Pivots to the WebSearch/WebFetch fallbacks ON ITS OWN the moment a page blocks, a reviews tab won't open, or a load stalls past ~10 seconds, one blocked platform never halts the run; record what was blocked and how it was recovered
- Returns structured JSON in its final message: `{"dealer": ..., "google": {...}, "yelp": {...}, "dealerrater": {...}, "carfax": {...}, "blocked_platforms": [...]}`

The main context never scrapes. It merges the 4 JSON payloads and proceeds to Step 4. Sequential dealer-by-dealer collection is the failure mode that caused 20-minute runs and stream idle timeouts, do not fall back to it. The sub-steps below are the per-agent playbook.

For **each dealer** (subject + 3 competitors), collect data from all 4 platforms.
Use browser tools to navigate to each review site.

#### 3a. Google Reviews

1. Navigate to Google Maps search: `{dealer_name} {city} {state}`
2. Extract: **overall star rating**, **total review count**
3. Read through the reviews to capture:
   - The **last 25 reviews** (content, star rating, date, reviewer name)
   - From those, identify the **last 5 negative** (≤3 stars) and **last 5 positive** (4-5 stars)

**IMPORTANT:** Google Reviews are the most critical platform. Take extra care to
get accurate ratings and review counts. Use `javascript_tool` if needed to extract
structured data from the page.

#### 3b. Yelp

1. Navigate to: `https://www.yelp.com/search?find_desc={dealer_name}&find_loc={city}+{state}`
   or search Yelp directly for the dealer
2. Click into the dealer's Yelp page
3. Extract: **overall star rating**, **total review count**
4. Read the **last 25 reviews**: capture content, star rating, date
5. Identify last 5 negative (≤3 stars) and last 5 positive (4-5 stars)

#### 3c. DealerRater

1. Navigate to: `https://www.dealerrater.com/` and search for the dealer,
   OR use WebSearch to find the DealerRater page directly:
   `site:dealerrater.com "{dealer_name}" {city}`
2. Extract: **overall star rating**, **total review count**
3. Read the **last 25 reviews**: capture content, star rating, date
4. Identify last 5 negative (≤3 stars) and last 5 positive (4-5 stars)

#### 3d. CarFax Dealer Reviews

1. Use WebSearch: `site:carfax.com/Reviews "{dealer_name}" {city}`
   OR navigate to `https://www.carfax.com/Reviews` and search
2. Extract: **overall star rating**, **total review count**
3. Read the **last 25 reviews**: capture content, star rating, date
4. Identify last 5 negative (≤3 stars) and last 5 positive (4-5 stars)

**NOTE:** For competitors, you only need: overall rating, review count per platform,
and the 10 most recent reviews (for the "what competitors do right" analysis).
The full 25-review deep dive + negative/positive splits are only for the **subject dealer**.

### Step 4: Analyze Themes

For the **subject dealer**, analyze the last 25 reviews on each platform and identify:
- **Common positive themes** (e.g., "great service department", "no-pressure sales")
- **Common negative themes** (e.g., "long wait times", "poor communication")
- **Trending issues**: anything appearing in 3+ recent reviews that signals a pattern

For **competitors**, scan their 10 most recent reviews and note:
- What they're doing right that earns positive reviews

### Step 5: Build Intermediate JSON

Write all collected data to `/tmp/reputation_report_data.json`:

```json
{
  "metadata": {
    "report_date": "2026-03-27",
    "generation_timestamp": "2026-03-27 08:45:00 PST",
    "dealer_name": "McPeek Dodge Chrysler Jeep Ram",
    "dealer_location": "Anaheim, CA",
    "dealer_brand": "CDJR",
    "dealer_address": "1221 S Auto Center Dr, Anaheim, CA 92802"
  },
  "subject_dealer": {
    "name": "McPeek Dodge Chrysler Jeep Ram",
    "platforms": {
      "google": {
        "rating": 4.5,
        "review_count": 3241,
        "pulled_at": "2026-03-27 08:30:00 PST",
        "recent_positive": [
          {"reviewer": "John D.", "rating": 5, "date": "2026-03-20", "snippet": "..."}
        ],
        "recent_negative": [
          {"reviewer": "Jane S.", "rating": 2, "date": "2026-03-18", "snippet": "..."}
        ],
        "themes_positive": ["friendly staff", "fast service"],
        "themes_negative": ["long wait times"],
        "trending_issues": ["Multiple mentions of parts delays in last 2 weeks"]
      },
      "yelp": { "..." : "same structure" },
      "dealerrater": { "..." : "same structure" },
      "carfax": { "..." : "same structure" }
    }
  },
  "competitors": [
    {
      "name": "Competitor Dealer 1",
      "location": "City, ST",
      "approx_distance": "3.2 miles",
      "platforms": {
        "google": { "rating": 4.3, "review_count": 1800, "pulled_at": "..." },
        "yelp": { "rating": 3.5, "review_count": 120, "pulled_at": "..." },
        "dealerrater": { "rating": 4.7, "review_count": 950, "pulled_at": "..." },
        "carfax": { "rating": 4.4, "review_count": 600, "pulled_at": "..." }
      },
      "doing_right": ["Consistently praised for transparent pricing", "Quick follow-up"]
    }
  ],
  "seo_llm_section": "Your online reviews are one of the most powerful ranking signals for local SEO. Google's local pack algorithm weighs review quantity, quality, and recency heavily when deciding which dealerships appear in the top 3 map results. Beyond traditional search, Large Language Models (ChatGPT, Claude, Gemini, Perplexity) are increasingly used by car shoppers asking questions like 'best Jeep dealer in Orange County' or 'where should I buy a BMW in Los Angeles.' These AI models pull directly from review platforms to form their recommendations. A dealership with consistently high ratings, recent positive reviews, and thoughtful owner responses will be surfaced as a top recommendation — while competitors with stale or negative reviews get left behind. Every review is now a data point that shapes both your Google ranking and your AI reputation.",
  "recommendations": [
    "Respond to every Google review within 24 hours — positive and negative",
    "Ask satisfied service customers to leave a review on Google and Yelp before they leave",
    "Address the recurring 'long wait time' theme by communicating estimated service times upfront",
    "Claim and optimize your CarFax dealer page if not already done",
    "Flag negative DealerRater reviews for internal follow-up and post a professional public response"
  ]
}
```

### Step 6: Delta Tracking

Run delta tracking to compare current ratings against prior snapshots:

```bash
python3 "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/onlinereputation/delta_engine.py" \
  /tmp/reputation_report_data.json \
  "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/onlinereputation/history" \
  --output /tmp/reputation_delta.json
```

The delta engine will:
1. Load the most recent prior snapshot for this dealer
2. Compute rating changes and review count changes per platform
3. Tag each metric as improved / declined / stable
4. Save current snapshot for future comparison
5. Write delta results to `/tmp/reputation_delta.json`

### Step 7: Generate PDF

```bash
python3 "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/onlinereputation/generate_reputation_report.py" \
  /tmp/reputation_report_data.json \
  "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/OnlineReputation_{safe_dealer_name}_{date}.pdf" \
  "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png" \
  --delta /tmp/reputation_delta.json
```

### Step 7.5: Render Gate (MANDATORY)

Run the Visual-QA render gate on the generated PDF before anything else:

```bash
python3 /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/design-system/templates/render_check.py \
  "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/OnlineReputation_{safe_dealer_name}_{date}.pdf"
```

Visually READ every rendered page against `Resources/design-system/Visual-QA.md`: Dosis headings, Roboto Slab body, canonical dark cover (gradient, glow orbs, white logo, cursor glyph, pillars strip), color logo in the interior running furniture, on-palette colors only, no text overflow, no wall-of-text pages. Fix defects in the generator (never the output), regenerate, re-render. Done = two consecutive fully-clean passes. Report passes run and defects caught to Drew.

### Step 8: Present Results

Tell the user:
- PDF location in `outputs/`
- Quick summary: overall ratings, biggest strengths, areas to improve
- Whether this is a first report or includes delta data from prior run
- Remind them the SEO/LLM section is included for client education

---

## PDF Structure (Page Layout)

Read `references/pdf-structure.md` for the full page-by-page layout spec before rendering.

## Critical Rules

1. **Timestamps**: Show `pulled_at` timestamps next to each platform's data AND
   the report generation timestamp on page 1. DigitalCLIQ gets credit with
   "Prepared by DigitalCLIQ: Digital Strategy & Development" on page 1.

2. **Review classification**: Negative = 1-3 stars. Positive = 4-5 stars. No exceptions.

3. **Competitor data is lighter**: Only pull rating + count + last 10 reviews for
   competitors. The full 25-review deep dive is only for the subject dealer.

4. **Browser patience**: Review sites can be slow. If a page doesn't load, retry
   once. If a platform has no listing for a dealer, record as "Not Listed" with
   0 rating and 0 reviews.

5. **Output**: Always to `outputs/` folder. Filename format:
   `OnlineReputation_{DealerName}_{YYYY-MM-DD}.pdf` (spaces replaced with underscores)

6. **Delta**: History snapshots saved to the skill's `history/` folder.
   Filename: `{safe_dealer_name}_{YYYY-MM}.json`

7. **SEO/LLM section**: Include on EVERY report. This is educational and should
   be consistent messaging to reinforce the importance of online reviews.


## Self-Validation (MANDATORY: final step before reporting success)

After the deliverable is generated, run the shared post-flight validator on the final file. This step is not optional and runs on every invocation:

```bash
python3 /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/post_flight.py \
  "<final output path>" --min-pages 5
```

It verifies four things and exits non-zero if any fail:
1. **Branding**: the DigitalCLIQ logo is actually embedded in the file (image objects present on every PDF page). A black tile with no logo image is a FAILURE, not a fallback.
2. **Location**: the file is inside `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/`. Anywhere else (especially the Desktop) fails.
3. **Page count**: at least 5 pages; fewer means a section silently failed or the report is truncated.
4. **No placeholder data**: template tokens like `{dealer_name}`, literal `YYYY-MM-DD`, "PLACEHOLDER", or lorem ipsum anywhere in the deliverable fail.

**On failure: retry once with a fallback, then fail loudly:**
1. Diagnose from the validator output. Common fixes: the logo must load from the canonical path `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png`; a file saved outside `outputs/` must be moved there and re-validated; a placeholder hit means a data section came back empty, re-fetch that data, do not paper over it.
2. Regenerate the deliverable ONCE and re-run the validator.
3. If it still fails: STOP. Show the user the validator output verbatim and state that the report FAILED validation. Never report success, never present the file as the final deliverable, and never wrap this step in try/except or `|| true` that hides the failure.


## Final QA Gate: deliverable-reviewer agent (MANDATORY, added 2026-08-13)

Runs AFTER the deliverable is generated and post_flight.py passes, BEFORE filing/presenting. post_flight.py is mechanical; this gate is the human-style read.

1. **Write a facts manifest** next to the deliverable in `outputs/`: a JSON list of every number, name, date, and claim that appears in the deliverable, each as `{"value": ..., "label": "where it appears", "source": "tool/file/URL it came from"}`. Build it from data already in context, never re-fetch anything just for the manifest.
2. **Spawn the `deliverable-reviewer` agent** (fresh eyes, it did not write the report). Pass in the prompt: the absolute path(s) of the finished deliverable file(s), the manifest path, and any skill-specific checks from this SKILL.md. It renders every page, reads them all, cross-checks figures against the manifest, and reviews tone/copy.
3. **Auto-fix every finding** in the source generator or data (never by hand-editing the output), re-render, and re-run the agent once. Max 2 review passes. If CRITICAL or MAJOR findings remain after pass 2, the ship is BLOCKED: report the remaining findings to Drew verbatim instead of presenting the file as done.
4. The run summary MUST include a **QA line**: what the reviewer caught and what was fixed, or "QA: clean on first pass (N pages read, M figures verified)". Never silently skip the gate; if the agent could not run, say so explicitly in the delivery message.
