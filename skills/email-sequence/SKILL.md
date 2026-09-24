---
name: email-sequence
description: Design and draft multi-email sequences with full copy, timing, branching logic, exit conditions, and performance benchmarks. Use when building onboarding, lead nurture, re-engagement, win-back, or product launch flows, when you need a complete drip campaign with A/B test suggestions, or when mapping a sequence end-to-end with a flow diagram.
---

<!-- Local vault copy is canonical for DigitalCLIQ; marketing-plugin ships an identical base version. Customize here. -->

# Email Sequence

> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](../../CONNECTORS.md).

Design and draft complete email sequences with full copy, timing, branching logic, and performance benchmarks for any lifecycle or campaign use case.

## Trigger

User runs `/email-sequence` or asks to create, design, build, or draft an email sequence, drip campaign, nurture flow, or onboarding series.

## Inputs

Gather the following from the user. If not provided, ask before proceeding:

1. **Sequence type** -- one of:
   - Onboarding
   - Lead nurture
   - Re-engagement
   - Product launch
   - Event follow-up
   - Upgrade/upsell
   - Win-back
   - Educational drip

2. **Goal** -- what the sequence should achieve (e.g., activate new users, convert leads to customers, reduce churn, drive event attendance, upsell to a higher tier)

3. **Audience** -- who receives this sequence, what stage they are at, and any relevant segmentation details (role, industry, behavior triggers, lifecycle stage)

4. **Number of emails** (optional) -- if not specified, recommend a count based on the sequence type using the templates below

5. **Timing/cadence preferences** (optional) -- desired spacing between emails

6. **Brand voice** -- if configured in local settings, apply automatically. If not configured, ask: "Do you have brand voice guidelines I should follow? If not, I'll use a clear, conversational professional tone."

7. **Additional context** (optional):
   - Specific offers, discounts, or incentives to include
   - CTAs or landing pages to link to
   - Content assets available (blog posts, case studies, videos, guides)
   - Product features to highlight

---

## Process

### 1. Sequence Strategy

Before drafting any emails, define the overall sequence architecture:

- **Narrative arc** -- what story does this sequence tell? What is the emotional and logical progression from first to last?
- **Journey mapping** -- map each email to a stage of the buyer or user journey
- **Escalation logic** -- how does intensity, urgency, or value build across emails?
- **Success definition** -- what action signals that the sequence has done its job?

---

### 2. Subject Line Optimization Loop

Do not draft one subject line per email and move on. For each email in the sequence:

1. Generate 3 subject line options using different approaches:
   - Curiosity-based ("What most dealerships miss about their May numbers")
   - Benefit-driven ("3 ways to cut your cost per lead before Q3")
   - Urgency/social proof ("47 dealers did this last quarter")

2. Score each option against these criteria:
   - Under 50 characters (mobile preview safe)
   - Does NOT repeat the preview text
   - Creates a specific reason to open (not generic)
   - Aligns with the email's position in the sequence (not too salesy too early)

3. Flag any subject line that scores poorly on 2+ criteria and generate a replacement.

4. Lock in the winning option for each email before drafting body copy. Subject lines shape the body -- draft order matters.

---

### 3. Individual Email Design

For each email in the sequence:

#### Subject Line
Selected from the optimization loop above (top-scored option, with 2 alternates for A/B testing).

#### Preview Text
- 40-90 characters that complement (not repeat) the subject line
- Should add context or intrigue that increases open likelihood

#### Email Purpose
One sentence explaining why this email exists and what it moves the recipient toward.

#### Body Copy
- Full draft ready to use
- Clear hierarchy: hook, body, CTA
- Short paragraphs (2-3 sentences max)
- Scannable with bold key phrases where appropriate
- Personalization tokens where relevant (first name, company name, product used)

#### Primary CTA
- Button text and destination
- One primary CTA per email

#### Timing
- Days after the trigger event or after the previous email
- Note if timing should adjust based on engagement

#### Segment/Condition Notes
- Who receives this email vs. who skips it
- Behavioral or attribute-based conditions

---

### 4. Branch Path Validation Loop

After drafting all emails and defining branching logic, walk every path end-to-end before finalizing:

```
For each branch path in the sequence:
  1. Simulate a recipient following that path from trigger to exit
  2. Check narrative coherence: does the story make sense to someone
     who only received emails on this path?
  3. Check for dead ends: does every path reach an exit condition
     or a defined next step?
  4. Check for gaps in urgency: does escalation build logically,
     or does a branch jump from low-pressure to hard close?
  5. If any path fails a check, revise the affected email(s)
     and re-walk that path
```

Example failure this loop catches: a re-engagement sequence where the "opened but didn't click" branch skips directly from Email 2 to Email 4, losing the soft ask in Email 3 that the narrative depends on.

Flag any path where:
- The jump in tone between consecutive emails is more than one level (e.g., educational to hard close with no transition)
- A recipient could exit the sequence without ever seeing the primary CTA
- The timing between two emails on the same path is less than 24 hours (unless intentionally urgent)

---

### 5. Sequence Logic

Define the flow control for the sequence:

- **Branching conditions** -- alternate paths based on engagement:
  - "If opened email 2 but did not click CTA, send email 2b (softer re-ask) instead of email 3"
  - "If clicked CTA in email 1, skip email 2 and go directly to email 3"
- **Exit conditions** -- when a recipient converts, remove them from the sequence
- **Re-entry rules** -- can someone re-enter the sequence? Under what conditions?
- **Suppression rules** -- do not send if the recipient is in another active sequence, has unsubscribed, or has contacted support in the last 48 hours

---

### 6. Performance Benchmarks

Provide expected benchmarks based on the sequence type:

| Metric | Onboarding | Lead Nurture | Re-engagement | Win-back |
|--------|-----------|--------------|---------------|----------|
| Open rate | 50-70% | 20-30% | 15-25% | 15-20% |
| Click-through rate | 10-20% | 3-7% | 2-5% | 2-4% |
| Conversion rate | 15-30% | 2-5% | 3-8% | 1-3% |
| Unsubscribe rate | <0.5% | <0.5% | 1-2% | 1-3% |

---

## Sequence Type Templates

**Onboarding (5-7 emails over 14-21 days):**
Welcome and set expectations -- Quick win to demonstrate value -- Core feature deep dive -- Advanced feature or integration -- Social proof and community -- Check-in and feedback request -- Upgrade prompt or next steps

**Lead Nurture (4-6 emails over 3-4 weeks):**
Value-first educational content -- Pain point identification -- Solution positioning with proof -- Social proof and results -- Soft CTA (trial, demo, resource) -- Direct CTA (buy, book, sign up)

**Re-engagement (3-4 emails over 10-14 days):**
"We miss you" with a compelling reason to return -- Value reminder highlighting what they are missing -- Incentive or exclusive offer -- Last chance with clear deadline

**Win-back (3-5 emails over 30 days):**
Friendly check-in asking what went wrong -- What is new since they left -- Special offer or incentive to return -- Feedback request -- Final goodbye with door open

**Product Launch (4-6 emails over 2-3 weeks):**
Teaser or pre-announcement -- Launch announcement with full details -- Feature spotlight or use case -- Social proof and early results -- Limited-time offer or bonus -- Last chance or reminder

**Event Follow-up (3-4 emails over 7-10 days):**
Thank you with key takeaways or recordings -- Resource roundup from the event -- Related offer or next step -- Feedback survey

**Upgrade/Upsell (3-5 emails over 2-3 weeks):**
Usage milestone or success celebration -- Feature gap or limitation they are hitting -- Upgrade benefits with proof -- Limited-time incentive -- Direct comparison of plans

**Educational Drip (5-8 emails over 4-6 weeks):**
Introduction and what they will learn -- Lesson 1: foundational concept -- Lesson 2: intermediate concept -- Lesson 3: advanced concept -- Practical application or exercise -- Resource roundup -- Graduation and next steps

---

## Tool Integration

### If email marketing is connected (e.g., Klaviyo, Mailchimp, Customer.io)
- Reference how to set up the sequence as a flow or automation in the platform
- Note any platform-specific features to use (smart send time, conditional splits, A/B testing)
- Map the branching logic to the platform's visual flow builder concepts

### If marketing automation or CRM is connected (e.g., HubSpot, Marketo)
- Reference lead scoring data to inform segmentation and exit conditions
- Use lifecycle stage data to tailor messaging per segment

### If no tools are connected
- Deliver all email content in copy-paste-ready format
- Include a setup checklist:
  1. Create the automation or flow
  2. Set the enrollment trigger
  3. Add each email with the specified delays
  4. Configure branching and exit conditions
  5. Set up tracking for the recommended metrics

---

## Output

### Sequence Overview Table

| # | Subject Line | Purpose | Timing | Primary CTA | Condition |
|---|-------------|---------|--------|-------------|-----------|

### Full Email Drafts
Each email with subject line options (from the optimization loop), preview text, purpose, body copy, CTA, timing, and segment notes.

### Sequence Flow Diagram

```
[Trigger] --> Email 1 (Day 0)
                |
          Opened? --Yes--> Email 2 (Day 3)
                |              |
                No        Clicked CTA? --Yes--> [EXIT: Converted]
                |              |
                v              No
          Email 1b (Day 2)     |
                |              v
                +--------> Email 3 (Day 7)
                               |
                               v
                          Email 4 (Day 10)
                               |
                          [EXIT: Sequence complete]
```

### Branching Logic Notes
Summary of all conditions, exits, and suppressions.

### Branch Path Validation Results
For each path walked in the validation loop:
- Path description (e.g., "opened E1, clicked E2, did not click E3")
- Narrative coherence: pass/fail with notes
- Dead ends: pass/fail
- Escalation logic: pass/fail
- Any emails revised as a result

### A/B Test Suggestions
- 2-3 recommended tests (subject lines, CTA text, send time, email length)
- What to test, how to split, how to measure

### Metrics to Track
- Primary conversion metric for the sequence
- Per-email: open rate, CTR, unsubscribe rate
- Sequence-level: overall conversion rate, time to conversion, drop-off points

---

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

## After the Sequence

Ask: "Would you like me to:
- Revise the copy or tone for any specific email?
- Add a branching path for a specific scenario?
- Create a variation of this sequence for a different audience segment?
- Draft the A/B test variants for the subject lines?
- Build a companion sequence (e.g., a post-purchase follow-up)?"

## Final QA Gate: deliverable-reviewer agent (MANDATORY, added 2026-08-13)

Runs AFTER the deliverable is generated and post_flight.py passes, BEFORE filing/presenting. post_flight.py is mechanical; this gate is the human-style read.

1. **Write a facts manifest** next to the deliverable in `outputs/`: a JSON list of every number, name, date, and claim that appears in the deliverable, each as `{"value": ..., "label": "where it appears", "source": "tool/file/URL it came from"}`. Build it from data already in context, never re-fetch anything just for the manifest.
2. **Spawn the `deliverable-reviewer` agent** (fresh eyes, it did not write the report). Pass in the prompt: the absolute path(s) of the finished deliverable file(s), the manifest path, and any skill-specific checks from this SKILL.md. It renders every page, reads them all, cross-checks figures against the manifest, and reviews tone/copy.
3. **Auto-fix every finding** in the source generator or data (never by hand-editing the output), re-render, and re-run the agent once. Max 2 review passes. If CRITICAL or MAJOR findings remain after pass 2, the ship is BLOCKED: report the remaining findings to Drew verbatim instead of presenting the file as done.
4. The run summary MUST include a **QA line**: what the reviewer caught and what was fixed, or "QA: clean on first pass (N pages read, M figures verified)". Never silently skip the gate; if the agent could not run, say so explicitly in the delivery message.
