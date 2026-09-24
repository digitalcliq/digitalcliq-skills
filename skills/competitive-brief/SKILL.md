---
name: competitive-brief
description: Research competitors and generate a positioning and messaging comparison with content gaps, opportunities, and threats. Use when building sales battlecards, when finding positioning gaps and messaging angles competitors haven't claimed, or when a competitor makes a move and you need to assess the impact.
---

<!-- Local vault copy is canonical for DigitalCLIQ; marketing-plugin ships an identical base version. Customize here. -->

# Competitive Brief

> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](../../CONNECTORS.md).

Research competitors and generate a structured competitive analysis comparing positioning, messaging, content strategy, and market presence.

## Trigger

User runs `/competitive-brief` or asks for a competitive analysis, competitor research, or market comparison.

## Inputs

Gather the following from the user:

1. **Competitor name(s)** -- one or more competitors to analyze (required)

2. **Your company/product context** (optional but recommended):
   - What you sell and to whom
   - Your positioning or value proposition
   - Key differentiators you want to highlight

3. **Focus areas** (optional -- if not specified, cover all):
   - Messaging and positioning
   - Product and feature comparison
   - Content and thought leadership strategy
   - Recent announcements and news
   - Pricing and packaging (if publicly available)
   - Market presence and audience

## Process

### Step 0: Competitor Discovery Loop

Before researching, validate and expand the competitor set. Users often name brand-level competitors, not their actual search and market competitors.

1. Start with whoever the user named.
2. For each named competitor, research who THEY compete with -- check their positioning language, who they mention, who review sites compare them against, who appears alongside them in search results for shared keywords.
3. Surface 2-3 additional competitors the user may not have considered: "Based on keyword overlap and market positioning, you may also want to include [X] and [Y]. Want me to add them?"
4. User confirms the final competitor set.
5. Begin research only after the set is locked.

This loop typically surfaces the competitor the user forgot about -- the one winning deals they don't know they're losing to.

---

### Step 1: Source Expansion Loop

For each competitor, research using a layered approach where each source informs what to look for next. Do not run all sources in parallel and treat them equally -- let findings compound.

**Layer 1 -- Primary positioning (always run first):**
- Homepage messaging, tagline, value proposition
- Product pages and feature emphasis
- About page and company narrative
- Pricing page (if public)

**Layer 2 -- Strategic signals (run after Layer 1, informed by what you found):**
- Recent press releases and announcements (last 6 months)
- Job postings: what are they hiring for? New product lines, new markets, and new technologies show up in job posts 3-6 months before they appear publicly.
- Blog and content themes: what problems are they positioning themselves to solve?

**Layer 3 -- Third-party intelligence (run after Layer 2, focus on gaps Layer 1-2 revealed):**
- G2, Capterra, or TrustRadius reviews: what do customers praise and complain about?
- If Layer 1 reveals they claim a specific strength, check Layer 3 to see if customers actually validate it or contradict it.
- News coverage for context on funding, partnerships, and strategic direction.

At the end of each layer, note what new angles emerged that should be probed in the next layer. A competitor claiming "easiest onboarding in the industry" on their homepage gets tested against G2 reviews for onboarding complaints -- that's a loop, not parallel research.

---

### Step 2: Intelligence Freshness Check (on re-runs)

If a prior competitive brief exists for this competitor, before conducting new research:

1. Note the date of the prior brief.
2. Scan for any competitor announcements, funding rounds, product launches, or leadership changes since that date.
3. Flag what is stale: "The prior brief from [date] predates their Series B announcement and new enterprise tier launch. These sections need refreshing: [pricing, product positioning, recent news]."
4. Research only the stale sections, then merge with the current brief.

This prevents re-researching everything from scratch while ensuring the brief reflects current reality.

---

### Step 3: Build Competitor Profiles

For each competitor:

#### Company Overview
- What they do (one-sentence positioning)
- Target audience
- Company size/stage indicators (funding, employee count if available)
- Key recent developments

#### Messaging Analysis
- Primary tagline or headline
- Core value proposition
- Key messaging themes (3-5)
- Tone and voice characterization
- How they describe the problem they solve

#### Product/Solution Positioning
- How they categorize their product
- Key features they emphasize
- Claimed differentiators
- Pricing approach (if publicly available)

#### Content Strategy
- Blog frequency and topics
- Content types produced (ebooks, webinars, case studies, tools)
- Social media presence and engagement approach
- Thought leadership themes
- SEO strategy observations (what terms they appear to target)

#### Strengths
- What they do well
- Where their messaging resonates
- Competitive advantages

#### Weaknesses
- Gaps in their messaging or positioning
- Areas where they are vulnerable
- Customer complaints or criticism themes (from reviews)

---

### Step 4: Competitive Brief Structure

#### 1. Executive Summary
- 2-3 sentence overview of the competitive landscape
- Key takeaway: your biggest opportunity and biggest threat

#### 2. Competitor Profiles
(Built in Step 3 above)

#### 3. Messaging Comparison Matrix

| Dimension | Your Company | Competitor A | Competitor B |
|-----------|-------------|--------------|--------------|
| Primary tagline | ... | ... | ... |
| Target buyer | ... | ... | ... |
| Key differentiator | ... | ... | ... |
| Tone/voice | ... | ... | ... |
| Core value prop | ... | ... | ... |

#### 4. Content Gap Analysis
- Topics your competitors cover that you do not (or vice versa)
- Content formats they use that you could adopt
- Keywords or themes they own vs. opportunities they have missed

#### 5. Opportunities
- Positioning gaps you can exploit
- Messaging angles your competitors have not claimed
- Audience segments they are underserving
- Content or channel opportunities

#### 6. Threats
- Areas where competitors are strong and you are vulnerable
- Trends that favor their positioning
- Recent moves that could shift the market

#### 7. Recommended Actions
- 3-5 specific, actionable recommendations based on the analysis
- Quick wins (things you can act on this week)
- Strategic moves (longer-term positioning or content investments)

---

## Analysis Frameworks

### Value Proposition Comparison

For each competitor, document:
- **Promise**: what they promise the customer will achieve
- **Evidence**: how they prove the promise (data, testimonials, demos)
- **Mechanism**: how their product delivers on the promise
- **Uniqueness**: what they claim only they can do

### Narrative Analysis

Identify each competitor's story arc:
- **Villain**: what problem or enemy they position against
- **Hero**: who is the hero in their story
- **Transformation**: what before/after do they promise?
- **Stakes**: what happens if you do not act?

### Battlecard Creation

A competitive battlecard is a one-page reference for sales and marketing teams. Include:

**Header**
- Competitor name, last updated date, competitive win rate (if tracked)

**Quick Overview**
- What they do (one sentence), target customer, pricing model summary, key recent developments

**Their Pitch**
- How they describe themselves, primary tagline, top 3 claimed differentiators

**Strengths (Be Honest)**
- Where they genuinely compete well, what customers like (from reviews), features where they lead

**Weaknesses**
- Consistent customer complaints, technical limitations, gaps in offering

**Our Differentiators**
- 3-5 specific ways your product or approach differs, why each matters, proof

**Objection Handling**
| If the prospect says... | Respond with... |
|------------------------|----------------|
| "[Competitor] does X too" | "Here is how our approach differs..." |
| "[Competitor] is cheaper" | "Here is what that price difference gets you..." |

**Landmines to Set**
Questions to ask prospects early that highlight competitor weaknesses.

**Win/Loss Themes**
- Common reasons deals are won or lost against this competitor
- What types of prospects favor them vs. you

---

## Output

Present the full competitive brief with clear formatting. Note the date of the research so the user knows freshness of the data.

After the brief, ask:

"Would you like me to:
- Create a battlecard for your sales team based on this analysis?
- Draft messaging that exploits the positioning gaps identified?
- Dive deeper into any specific competitor?
- Set up a competitive monitoring plan?"

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

## Final QA Gate: deliverable-reviewer agent (MANDATORY, added 2026-08-13)

Runs AFTER the deliverable is generated and post_flight.py passes, BEFORE filing/presenting. post_flight.py is mechanical; this gate is the human-style read.

1. **Write a facts manifest** next to the deliverable in `outputs/`: a JSON list of every number, name, date, and claim that appears in the deliverable, each as `{"value": ..., "label": "where it appears", "source": "tool/file/URL it came from"}`. Build it from data already in context, never re-fetch anything just for the manifest.
2. **Spawn the `deliverable-reviewer` agent** (fresh eyes, it did not write the report). Pass in the prompt: the absolute path(s) of the finished deliverable file(s), the manifest path, and any skill-specific checks from this SKILL.md. It renders every page, reads them all, cross-checks figures against the manifest, and reviews tone/copy.
3. **Auto-fix every finding** in the source generator or data (never by hand-editing the output), re-render, and re-run the agent once. Max 2 review passes. If CRITICAL or MAJOR findings remain after pass 2, the ship is BLOCKED: report the remaining findings to Drew verbatim instead of presenting the file as done.
4. The run summary MUST include a **QA line**: what the reviewer caught and what was fixed, or "QA: clean on first pass (N pages read, M figures verified)". Never silently skip the gate; if the agent could not run, say so explicitly in the delivery message.
