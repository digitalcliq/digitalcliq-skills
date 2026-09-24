---
name: seo-audit
description: Run a comprehensive SEO audit -- keyword research, on-page analysis, content gaps, technical checks, and competitor comparison. Use when assessing a site's SEO health, when finding keyword opportunities and content gaps competitors own, or when you need a prioritized action plan split into quick wins and strategic investments.
---

<!-- Local vault copy is canonical for DigitalCLIQ; marketing-plugin ships an identical base version. Customize here. -->

# /seo-audit

> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](../../CONNECTORS.md).

Audit a website's SEO health, research keyword opportunities, identify content gaps, and benchmark against competitors. Produces a prioritized action plan a marketer can execute immediately.

## Trigger

User runs `/seo-audit` or asks for an SEO audit, keyword research, content gap analysis, technical SEO check, or competitor SEO comparison.

## Inputs

Gather the following from the user. If not provided, ask before proceeding:

1. **URL or domain** -- the site to audit, or a topic/keyword if running in keyword research mode

2. **Audit type** -- one of:
   - **Full site audit** -- end-to-end SEO review covering all sections below
   - **Keyword research** -- identify keyword opportunities for a topic or domain
   - **Content gap analysis** -- find topics competitors rank for that you don't
   - **Technical SEO check** -- crawlability, speed, structured data, and infrastructure issues
   - **Competitor SEO comparison** -- head-to-head SEO benchmarking against specific competitors

   If not specified, default to **full site audit**.

3. **Target keywords or topics** (optional) -- specific keywords the user is already targeting or wants to rank for

4. **Competitors** (optional) -- domains or companies to compare against. Do NOT simply accept these at face value -- run the Competitor Validation Loop below before committing to research.

## Process

### 0. Competitor Validation Loop (run before any research)

If the user provides competitors, or if you identify them via web search, validate they are actually relevant before investing research time:

1. Pull organic keyword overlap between the user's domain and each proposed competitor using Semrush or web search.
2. If overlap is below 30%, flag it: "Domain X shares only 12% keyword overlap with your site. They may not be your true SEO competitors. Suggested alternatives: [Y, Z]."
3. Replace or add competitors based on user confirmation.
4. Loop until the competitor set reflects actual search competition, not just brand-level awareness.

Researching the wrong competitors produces a useless gap analysis. This check takes minutes and saves hours.

---

### 1. Semrush Intelligence Chain (if Semrush is connected)

Do NOT run each research section independently. Chain each result into the next query -- what you learn in step A shapes what you look for in step B.

**Chain loop:**
```
A. Organic research on domain
      -> identify top-ranking pages by traffic
B. URL research on those top pages
      -> find which specific keywords drive them
C. Competitor keyword gap
      -> find terms competitors rank for that the domain does not
D. Backlink research on competitor pages ranking for gap terms
      -> identify which sites link to competitors for those terms
E. Content gap synthesis
      -> combine B + C to surface the highest-value missing content
```

Run each step, collect the signal, then use it to focus the next step. Stop when you have enough signal on each of the five audit sections, or when additional queries return diminishing new data.

If Semrush is not connected, use web search for each step and note: "For precise volume and difficulty data, connect Semrush via MCP. The audit will auto-populate with ranking data."

---

### 2. Keyword Research

For each keyword opportunity, assess:
- **Primary keywords** -- high-intent terms directly tied to the user's product or service
- **Secondary keywords** -- supporting terms and variations
- **Search volume signals** -- relative demand (high, medium, low) based on available data
- **Keyword difficulty** -- how competitive the term is (easy, moderate, hard)
- **Long-tail opportunities** -- specific, lower-competition phrases with clear intent
- **Question-based keywords** -- "how to", "what is", "why does" queries that mirror People Also Ask
- **Intent classification** -- informational, navigational, commercial, or transactional

---

### 3. On-Page SEO Audit

For each key page (homepage, top landing pages, recent blog posts), evaluate:

- **Title tags** -- present, unique, within 50-60 characters, includes target keyword
- **Meta descriptions** -- present, compelling, within 150-160 characters, includes a call to action
- **H1 tags** -- exactly one per page, includes primary keyword
- **H2/H3 structure** -- logical hierarchy, uses secondary keywords where natural
- **Keyword usage** -- primary keyword appears in the first 100 words, used naturally throughout, not over-stuffed
- **Internal linking** -- pages link to related content, orphan pages identified, anchor text is descriptive
- **Image alt text** -- all images have descriptive alt attributes, keywords included where relevant
- **URL structure** -- clean, readable, includes keywords, no excessive parameters or depth

---

### 4. Content Gap Analysis

Identify what's missing from the user's content strategy:

- **Competitor topic coverage** -- topics and keywords competitors rank for that the user's site does not cover
- **Content freshness** -- pages that haven't been updated in 12+ months and may be losing rankings
- **Thin content** -- pages with insufficient depth to rank (under 300 words for informational queries, lacking substance)
- **Missing content types** -- formats competitors use that the user doesn't (guides, comparison pages, glossaries, tools, templates)
- **Funnel gaps** -- missing content at specific buyer journey stages (awareness, consideration, decision)
- **Topic clusters** -- opportunities to build pillar pages with supporting content

---

### 5. Technical SEO Checklist

Evaluate technical foundations that affect crawlability and rankings:

- **Page speed** -- identify slow-loading pages and likely causes (large images, render-blocking scripts, excessive redirects)
- **Mobile-friendliness** -- responsive design, tap targets, font sizes, viewport configuration
- **Structured data** -- opportunities for schema markup (FAQ, HowTo, Product, Article, Organization, Breadcrumb)
- **Crawlability** -- robots.txt configuration, XML sitemap presence and accuracy, canonical tags, noindex/nofollow usage
- **Broken links** -- internal and external 404s, redirect chains
- **HTTPS** -- secure connection, mixed content issues
- **Core Web Vitals signals** -- LCP, FID/INP, CLS indicators based on observable page behavior
- **Indexation** -- pages that should be indexed but may not be, duplicate content risks

---

### 6. Competitor SEO Comparison

For each validated competitor, compare:

- **Keyword overlap** -- keywords both sites rank for, and where each site ranks higher
- **Keyword gaps** -- terms the competitor ranks for that the user does not
- **Domain authority signals** -- relative site strength based on backlink profiles, referring domains, and content depth
- **Content depth** -- average content length, topic coverage breadth, publishing frequency
- **Backlink profile observations** -- types of sites linking to competitors, link-worthy content they've produced
- **SERP feature ownership** -- which competitor appears in featured snippets, People Also Ask, image packs, or knowledge panels
- **Technical advantages** -- site speed differences, mobile experience, structured data usage

---

### 7. Action Plan Prioritization Loop

Do not output a flat list of recommendations. Run this loop to rank them properly:

1. List all findings from sections 2-6 as candidate action items.
2. Score each on **impact** (high/medium/low) and **effort** (high/medium/low) based on what you know about the site's current state.
3. If impact or effort is ambiguous for any item, surface it to the user: "Is [action] something your team can execute in-house, or would it require dev resources?" Adjust effort score based on answer.
4. Re-rank the list by impact/effort ratio.
5. Split into two tiers for the final output:
   - **Quick Wins** -- high or medium impact, low effort (do this week)
   - **Strategic Investments** -- high impact, high effort (plan for this quarter)
6. Cut anything that is low impact and high effort entirely -- do not include it.

The goal is a list the user can actually act on, not an exhaustive catalog of every issue found.

---

## Output

### Executive Summary

Open with a 3-5 sentence summary of overall SEO health. Highlight:
- The site's biggest strength
- The top 3 priorities that will have the most impact
- An overall assessment: strong foundation, needs work, or critical issues

### Keyword Opportunity Table

| Keyword | Est. Difficulty | Opportunity Score | Current Ranking | Intent | Recommended Content Type |
|---------|----------------|-------------------|-----------------|--------|--------------------------|

Opportunity score: high, medium, or low -- based on the combination of search demand, difficulty, and relevance to the user's business.

Include 15-25 keyword opportunities, sorted by opportunity score.

### On-Page Issues Table

| Page | Issue | Severity | Recommended Fix |
|------|-------|----------|-----------------|

Severity levels:
- **Critical** -- directly hurting rankings or preventing indexation
- **High** -- significant impact on SEO performance
- **Medium** -- best practice violation, moderate impact
- **Low** -- minor optimization opportunity

### Content Gap Recommendations

For each content gap identified, provide:
- **Topic or keyword** to target
- **Why it matters** -- search demand, competitor coverage, funnel stage
- **Recommended format** -- blog post, landing page, guide, comparison page, etc.
- **Priority** -- high, medium, or low
- **Estimated effort** -- quick win (1-2 hours), moderate (half day), substantial (multi-day)

### Technical SEO Checklist

| Check | Status | Details |
|-------|--------|---------|

Status: Pass, Fail, or Warning.

### Competitor Comparison Summary

| Dimension | Your Site | Competitor A | Competitor B | Winner |
|-----------|-----------|--------------|--------------|--------|

Include rows for: keyword count, content depth, publishing frequency, backlink signals, technical score, SERP feature presence.

### Prioritized Action Plan

**Quick Wins (do this week):**
- Actions that take under 2 hours and have immediate impact
- Examples: fix title tags, add meta descriptions, fix broken links, add alt text

**Strategic Investments (plan for this quarter):**
- Actions that require more effort but drive long-term growth
- Examples: build a topic cluster, create a pillar page, launch a link-building campaign, overhaul site structure

For each action item, include:
- What to do (specific and concrete)
- Expected impact (high, medium, low)
- Effort estimate
- Dependencies (if any)

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

## Follow-Up

After presenting the audit, ask:

"Would you like me to:
- Draft content briefs for the top keyword opportunities?
- Create optimized title tags and meta descriptions for your key pages?
- Build a content calendar based on the gap analysis?
- Dive deeper into any specific section of the audit?
- Run this same analysis for a different competitor or domain?"

## Final QA Gate: deliverable-reviewer agent (MANDATORY, added 2026-08-13)

Runs AFTER the deliverable is generated and post_flight.py passes, BEFORE filing/presenting. post_flight.py is mechanical; this gate is the human-style read.

1. **Write a facts manifest** next to the deliverable in `outputs/`: a JSON list of every number, name, date, and claim that appears in the deliverable, each as `{"value": ..., "label": "where it appears", "source": "tool/file/URL it came from"}`. Build it from data already in context, never re-fetch anything just for the manifest.
2. **Spawn the `deliverable-reviewer` agent** (fresh eyes, it did not write the report). Pass in the prompt: the absolute path(s) of the finished deliverable file(s), the manifest path, and any skill-specific checks from this SKILL.md. It renders every page, reads them all, cross-checks figures against the manifest, and reviews tone/copy.
3. **Auto-fix every finding** in the source generator or data (never by hand-editing the output), re-render, and re-run the agent once. Max 2 review passes. If CRITICAL or MAJOR findings remain after pass 2, the ship is BLOCKED: report the remaining findings to Drew verbatim instead of presenting the file as done.
4. The run summary MUST include a **QA line**: what the reviewer caught and what was fixed, or "QA: clean on first pass (N pages read, M figures verified)". Never silently skip the gate; if the agent could not run, say so explicitly in the delivery message.
