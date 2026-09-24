---
name: campaign-plan
description: Generate a full campaign brief with objectives, audience, messaging, channel strategy, content calendar, and success metrics. Use when planning a product launch, lead-gen push, or awareness campaign, when you need a week-by-week content calendar with dependencies, or when translating a marketing goal into a structured, executable plan.
---

<!-- Local vault copy is canonical for DigitalCLIQ; marketing-plugin ships an identical base version. Customize here. -->

# Campaign Plan

> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](../../CONNECTORS.md).

Generate a comprehensive marketing campaign brief with objectives, audience, messaging, channel strategy, content calendar, and success metrics.

## Trigger

User runs `/campaign-plan` or asks to plan, design, or build a marketing campaign.

## Inputs

Gather the following from the user. If not provided, ask before proceeding:

1. **Campaign goal** -- the primary objective (e.g., drive signups, increase awareness, launch a product, generate leads, re-engage churned users)

2. **Target audience** -- who the campaign is aimed at (demographics, roles, industries, pain points, buying stage)

3. **Timeline** -- campaign duration and any fixed dates (launch date, event date, seasonal deadline)

4. **Budget range** -- approximate budget or budget tier (optional; if not provided, generate a channel-agnostic plan and note where budget allocation would matter)

5. **Additional context** (optional):
   - Product or service being promoted
   - Key differentiators or value propositions
   - Previous campaign performance or learnings
   - Brand guidelines or constraints
   - Geographic focus

---

## Pre-Planning Loops

Run these two loops before building the brief. They take minutes and prevent wasted planning time.

### Loop 1: Competitive Channel Check

Before recommending channels, check what competitors are currently running:

1. Search the Meta Ad Library and any available Semrush data for competitor ad activity on proposed channels.
2. Identify where they are active and what messaging they are using.
3. Adjust channel and messaging recommendations to differentiate -- do not recommend the same channel with the same angle if competitors already own it.
4. If a proposed channel is saturated by competitors with similar positioning, flag it: "Competitors A and B are both running heavy Facebook lead gen campaigns with price-focused messaging. Recommend shifting angle to [differentiated approach] or testing Google Search as an alternative where their presence is weaker."

### Loop 2: Budget Optimization Loop (if budget is provided)

A flat percentage allocation is a starting point, not a finished plan. Run this loop:

1. Propose an initial channel allocation based on the campaign goal and audience.
2. Estimate projected ROI per channel using any available historical CPL, ROAS, or conversion data (from prior campaigns, connected analytics, or industry benchmarks).
3. Compare total projected output (leads, conversions, reach) against the campaign goal.
4. If the projection falls short of the goal: identify the highest-ROI channel and shift budget toward it, reducing spend on the lowest-ROI channel.
5. Re-project and compare again.
6. Repeat until the allocation either meets the goal or the user needs to adjust the goal given the budget.

If no historical data is available, use industry benchmarks and note the assumption clearly. If budget is not provided, skip this loop and note which channels would benefit most from it.

---

## Campaign Brief Structure

### 1. Campaign Overview
- Campaign name suggestion
- One-sentence campaign summary
- Primary objective with a specific, measurable goal
- Secondary objectives (if applicable)

### 2. Target Audience
- Primary audience segment with description
- Secondary audience segment (if applicable)
- Audience pain points and motivations
- Where they spend time (channels, communities, publications)
- Buying stage alignment (awareness, consideration, decision)

### 3. Key Messages
- Core campaign message (one sentence)
- 3-4 supporting messages tailored to audience pain points
- Message variations by channel (if different tones are needed)
- Proof points or evidence to support each message
- **Differentiation check**: confirm each message angle is not already being used by a top competitor (from Loop 1)

### 4. Channel Strategy
Recommend channels based on audience, goal, and competitive landscape (Loop 1). For each channel, include:
- Why this channel fits the audience and objective
- Content format recommendations
- Estimated effort level (low, medium, high)
- Budget allocation (from Loop 2 if budget provided)
- Competitive context: are competitors active here and how will you differentiate?

Consider channels from:
- Owned: blog, email, website, social media profiles
- Earned: PR, influencer partnerships, guest posts, community engagement
- Paid: search ads, social ads, display, sponsored content, events

### 5. Content Calendar
Create a week-by-week (or day-by-day for short campaigns) content calendar:
- What content to produce each week
- Which channel each piece targets
- Key milestones and deadlines
- Dependencies between pieces (e.g., "landing page must be live before paid ads launch")

| Week | Content Piece | Channel | Owner/Notes | Status |
|------|--------------|---------|-------------|--------|

### 6. Content Pieces Needed
List every content asset required for the campaign:
- Asset name and type (blog post, email, social post, ad creative, landing page, etc.)
- Brief description of what it should contain
- Priority (must-have vs. nice-to-have)
- Suggested timeline for creation

### 7. Success Metrics
Define KPIs aligned to the campaign objective:
- Primary KPI with target number
- Secondary KPIs (3-5)
- How each metric will be tracked
- Reporting cadence recommendation

### 8. Budget Allocation (if budget provided)
Output from Loop 2:
- Breakdown by channel or activity (optimized, not flat percentage)
- Projected output per channel (leads, conversions, reach)
- Total projected output vs. goal
- Production costs vs. distribution costs
- Contingency recommendation (typically 10-15%)

### 9. Risks and Mitigations
- 2-3 potential risks (timeline, audience mismatch, channel underperformance)
- Mitigation strategy for each

### 10. Next Steps
- Immediate action items to kick off the campaign
- Stakeholder approvals needed
- Key decision points

---

## Planning Reference

### Campaign Framework: Objective, Audience, Message, Channel, Measure

#### Objective
Good objectives are SMART: Specific, Measurable, Achievable, Relevant, Time-bound.

Example: "Generate 200 marketing qualified leads from mid-market SaaS companies in North America within 6 weeks of campaign launch."

#### Audience
Create a brief audience profile:
> "[Role] at [company type] who is struggling with [pain point] and looking for [desired outcome]. They typically discover solutions through [channels] and care most about [priorities]."

#### Message
Message hierarchy:
1. Why should I care? (addresses the pain point or opportunity)
2. What is the solution? (positions your offering)
3. Why you? (differentiates from alternatives)
4. What should I do? (call to action)

#### Channel Selection Criteria
- Where does your target audience spend time?
- What is the buying stage you are targeting?
- What is your budget?
- What has worked in the past?
- Where are competitors NOT yet active? (from Loop 1)

### Budget Allocation Framework

Starting framework (adjust based on Loop 2 optimization):

| Category | Starting % | Examples |
|----------|-----------|----------|
| Paid acquisition | 30-40% | Search ads, social ads, display |
| Content production | 20-30% | Blog, video, design, ebooks |
| Events and sponsorships | 10-20% | Conferences, webinars, meetups |
| Tools and technology | 10-15% | Analytics, automation, CRM |
| Testing and experimentation | 5-10% | New channels, A/B tests, pilots |

### Success Metrics by Campaign Type

#### Lead Generation Campaign
| Metric | What It Measures |
|--------|-----------------|
| Total leads | Volume of new contacts |
| Marketing qualified leads (MQLs) | Leads meeting quality threshold |
| Cost per lead (CPL) | Efficiency of spend |
| Lead-to-MQL conversion rate | Quality of leads generated |
| Pipeline influenced | Revenue opportunity created |

#### Awareness Campaign
| Metric | What It Measures |
|--------|-----------------|
| Reach/Impressions | How many people saw the campaign |
| Brand mention volume | Increase in brand conversations |
| Share of voice | Your mentions vs. competitors |
| Direct traffic | People coming to your site unprompted |

#### Product Launch Campaign
| Metric | What It Measures |
|--------|-----------------|
| Signups or trials | Adoption of new product |
| Activation rate | Users who complete key first action |
| Media coverage | Earned media hits |
| Feature adoption | Usage of specific launched features |

---

## Output

Present the full campaign brief with clear headings and formatting. After the brief, ask:

"Would you like me to:
- Dive deeper into any section?
- Draft specific content pieces from the calendar?
- Create a competitive analysis to inform the messaging?
- Adjust the plan for a different budget or timeline?"

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
