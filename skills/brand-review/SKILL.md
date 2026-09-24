---
name: brand-review
description: Reviews content against a specified brand's voice, style guide, and messaging pillars, flagging deviations by severity with specific before/after fixes. Use when checking a draft before it ships, when auditing copy for voice consistency and terminology, or when screening for unsubstantiated claims, missing disclaimers, and other legal flags.
---

<!-- Local vault copy is canonical for DigitalCLIQ; marketing-plugin ships an identical base version. Customize here. -->

# Brand Review

> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](../../CONNECTORS.md).

Review marketing content against brand voice, style guidelines, and messaging standards. Flag deviations and provide specific improvement suggestions.

## Trigger

User runs `/brand-review` or asks to review, check, or audit content against brand guidelines.

## Inputs

1. **Content to review** -- accept content in any of these forms:
   - Pasted directly into the conversation
   - A file path or knowledge base reference (e.g. Notion page, shared doc)
   - A URL to a published page
   - Multiple pieces for batch review

2. **Brand guidelines source** (determined automatically):
   - If a brand style guide is configured in local settings, use it automatically
   - If not configured, ask: "Do you have a brand style guide or voice guidelines I should review against? You can paste them, share a file, or describe your brand voice. Otherwise, I'll do a general review for clarity, consistency, and professionalism."

## Review and Revision Loop

The core of this skill is a loop, not a one-pass review. Do not stop after the first review and ask if the user wants revisions -- run the loop automatically.

```
Pass 1: Review content against brand guidelines
         -> Surface all HIGH and MEDIUM severity findings
         -> Apply fixes to produce a revised draft

Pass 2: Re-review the revised draft
         -> Check if HIGH severity issues are resolved
         -> Check if any new issues were introduced by the revisions
         -> Surface any remaining HIGH or MEDIUM issues

Pass N: Repeat until no HIGH or MEDIUM findings remain
         -> Stop when only LOW findings remain (style preferences, minor polish)
         -> Present final clean draft + summary of what changed
```

Show the user each pass as it completes so they can follow along. Do not run more than 3 passes without checking in -- after 3 passes with unresolved issues, surface the remaining problems and ask the user to clarify intent rather than continuing to loop.

---

## Review Process

### With Brand Guidelines Configured

Evaluate the content against each of these dimensions:

#### Voice and Tone
- Does the content match the defined brand voice attributes?
- Is the tone appropriate for the content type and audience?
- Are there shifts in voice that feel inconsistent?
- Flag specific sentences or phrases that deviate with an explanation of why

#### Terminology and Language
- Are preferred brand terms used correctly?
- Are any "avoid" terms or phrases present?
- Is jargon level appropriate for the target audience?
- Are product names, feature names, and branded terms used correctly (capitalization, formatting)?

#### Messaging Pillars
- Does the content align with defined messaging pillars or value propositions?
- Are claims consistent with approved messaging?
- Is the content reinforcing or contradicting brand positioning?

#### Style Guide Compliance
- Grammar and punctuation per style guide (Oxford comma, title case vs. sentence case)
- Formatting conventions (headers, lists, emphasis)
- Number formatting, date formatting
- Acronym usage (defined on first use?)

### Without Brand Guidelines (Generic Review)

#### Clarity
- Is the main message clear within the first paragraph?
- Are sentences concise and easy to understand?
- Is the structure logical and easy to follow?
- Are there ambiguous statements or unclear references?

#### Consistency
- Is the tone consistent throughout?
- Are terms used consistently (no switching between synonyms for the same concept)?
- Is formatting consistent (headers, lists, capitalization)?

#### Professionalism
- Is the content free of typos, grammatical errors, and awkward phrasing?
- Is the tone appropriate for the intended audience?
- Are claims supported or substantiated?

### Legal and Compliance Flags (Always Checked, Every Pass)

Regardless of whether brand guidelines are configured, flag:
- **Unsubstantiated claims** -- superlatives ("best", "fastest", "only") without evidence or qualification
- **Missing disclaimers** -- financial claims, health claims, or guarantees that may need legal disclaimers
- **Comparative claims** -- comparisons to competitors that could be challenged
- **Regulatory language** -- content that may need compliance review (financial services, healthcare, etc.)
- **Testimonial issues** -- quotes or endorsements without attribution or disclosure

Legal flags do NOT get auto-fixed in the revision loop. Surface them separately and let the user resolve them. The loop only auto-applies voice, tone, terminology, and style fixes.

---

## Cross-Piece Consistency Check (on batch reviews or follow-up)

If the user is reviewing more than one piece, or if other published content from this brand is available:

1. After reviewing the submitted piece, ask: "Do you have other published content from this brand you'd like me to check for consistency? For example, a previous blog post, an email, or a landing page."
2. If yes, scan the additional pieces for tone and terminology drift vs. the piece just reviewed.
3. Flag cross-piece inconsistencies separately: "This email uses 'clients' throughout, but the blog post uses 'customers.' Pick one and standardize."

This surfaces brand drift that single-piece review cannot catch.

---

## Brand Voice Reference

Use these frameworks to evaluate content against brand standards or to help the user document their brand voice.

### Brand Voice Documentation Framework

A complete brand voice document should cover:

1. **Brand Personality** -- Define the brand as if it were a person.
2. **Voice Attributes** -- 3-5 attributes defining how the brand communicates, each with what it means, what it does NOT mean, and an example.
3. **Audience Awareness** -- Who the brand speaks to, what they care about, their expertise level.
4. **Core Messaging Pillars** -- 3-5 key themes, their hierarchy, and how each connects to audience needs.
5. **Tone Spectrum** -- How the voice adapts across contexts while remaining consistent.
6. **Style Rules** -- Grammar, formatting, and language rules.
7. **Terminology** -- Preferred and avoided terms.

### Voice Attribute Spectrums

| Spectrum | One End | Other End |
|----------|---------|-----------|
| Formality | Formal, institutional | Casual, conversational |
| Authority | Expert, authoritative | Peer-level, collaborative |
| Emotion | Warm, empathetic | Direct, matter-of-fact |
| Complexity | Technical, precise | Simple, accessible |
| Energy | Bold, energetic | Calm, measured |
| Humor | Playful, witty | Serious, earnest |
| Innovation | Cutting-edge, forward-looking | Established, proven |

For each attribute, document:

**[Attribute name]**
- **We are**: [what this means in practice]
- **We are not**: [common misinterpretation to avoid]
- **This sounds like**: [example sentence demonstrating the attribute]
- **This does NOT sound like**: [example sentence violating the attribute]

### Tone by Channel

| Channel | Tone Adaptation |
|---------|----------------|
| Blog | Informative, conversational, educational |
| Social media (LinkedIn) | Professional, thought-provoking, concise |
| Social media (Twitter/X) | Punchy, direct, sometimes witty |
| Email marketing | Personal, helpful, action-oriented |
| Sales collateral | Confident, benefit-driven, specific |
| Support/Help docs | Clear, patient, step-by-step |
| Press release | Formal, factual, newsworthy |

### Tone by Situation

| Situation | Tone Adaptation |
|-----------|----------------|
| Product launch | Excited, confident, forward-looking |
| Incident or outage | Transparent, empathetic, accountable |
| Customer success story | Celebratory, specific, crediting the customer |
| Thought leadership | Authoritative, nuanced, evidence-based |
| Bad news (price increase, deprecation) | Honest, respectful, solution-oriented |

---

## Output Format

### Per-Pass Summary

After each pass in the review loop, show:

**Pass [N] -- [X] issues found / [Y] resolved from prior pass**

| Issue | Location | Severity | Fix Applied |
|-------|----------|----------|-------------|

### Revised Draft

After fixes are applied, show the revised version clearly labeled: **Revised Draft (Pass N)**

### Final Output (when loop completes)

**Clean draft** with all HIGH and MEDIUM issues resolved.

**Change summary**: brief list of what changed across all passes.

**Remaining LOW-severity notes**: style preferences and minor polish items the user can choose to apply or ignore.

**Legal/Compliance Flags**: listed separately -- these require user judgment, not auto-fix.

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

## After Review

If any issues required more than 2 passes to resolve, ask: "Would you like me to document these recurring patterns in a brand voice reference so future content avoids them from the start?"

## Final QA Gate: deliverable-reviewer agent (MANDATORY, added 2026-08-13)

Runs AFTER the deliverable is generated and post_flight.py passes, BEFORE filing/presenting. post_flight.py is mechanical; this gate is the human-style read.

1. **Write a facts manifest** next to the deliverable in `outputs/`: a JSON list of every number, name, date, and claim that appears in the deliverable, each as `{"value": ..., "label": "where it appears", "source": "tool/file/URL it came from"}`. Build it from data already in context, never re-fetch anything just for the manifest.
2. **Spawn the `deliverable-reviewer` agent** (fresh eyes, it did not write the report). Pass in the prompt: the absolute path(s) of the finished deliverable file(s), the manifest path, and any skill-specific checks from this SKILL.md. It renders every page, reads them all, cross-checks figures against the manifest, and reviews tone/copy.
3. **Auto-fix every finding** in the source generator or data (never by hand-editing the output), re-render, and re-run the agent once. Max 2 review passes. If CRITICAL or MAJOR findings remain after pass 2, the ship is BLOCKED: report the remaining findings to Drew verbatim instead of presenting the file as done.
4. The run summary MUST include a **QA line**: what the reviewer caught and what was fixed, or "QA: clean on first pass (N pages read, M figures verified)". Never silently skip the gate; if the agent could not run, say so explicitly in the delivery message.
