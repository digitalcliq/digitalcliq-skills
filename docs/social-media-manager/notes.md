---
type: skill-notes
skill: social-media-manager
status: active
created: 2026-06-24
tags: [skill, social, magnific, content]
---

Vault-side design notes for the **social-media-manager** skill. Runtime lives at
`.claude/skills/social-media-manager/` (SKILL.md + scripts + references). Built by [[Drew Moon]] on 2026-06-24.

## What it is

An AI social media manager for **any** client or prospect, automotive or not. It researches the brand
(voice, style, guidelines, competitors), pulls live follower/engagement baselines across Instagram, TikTok,
YouTube, X/Threads, and Facebook **or** LinkedIn (it swaps the platform mix to fit the business type),
builds a deeply-reasoned 30/60/90-day plan to **2x followers + interactions** on current-year (2026)
algorithm mechanics, **generates the hero photos and videos live via the [[Magnific]] MCP**, and ships a
DigitalCLIQ-branded Excel workbook. Email rule is hard-enforced: only `drewmoon@digitalcliq.com` ever appears.

## Architecture (lean by design)

- **SKILL.md**, orchestration playbook: pre-flight facts ledger, identify business, research, live baselines,
  honest 2x targets, 90-day calendar, prompt engineering, live generation, **brand-lock verification gate**,
  Drive delivery + approval/re-teach loop, build + validate.
- **references/**, `2026-platform-playbook.md` (strategy brain), `playbook-data.json` (the reusable per-platform
  mechanics merged into every workbook), `generation-brand-lock.md` (no-competitor rule + verification gate +
  brand-safe references), `automotive-compliance.md` (OEM + CA ad law; points at [[Resources/automotive-guidelines/README|Automotive Guidelines]]),
  `magnific-cheatsheet.md` (models + image→video flow).
- **scripts/**, `build_workbook.py` (renders the branded Excel; auto-derives the prompt library, gallery,
  calendar wiring, and playbook from a compact plan; validates), `download_assets.py` (batch download +
  thumbnails + merges paths back into the plan), `fetch_asset.py` (single-asset helper).

## Efficiency principles

Each run authors only **client-specific data** (`plan.json`), never code. The reusable playbook lives in
`playbook-data.json`; all file work (download, thumbnails, build, validate) is offloaded to local scripts.
Magnific discipline: batch generation in one turn, one `creations_wait` per batch, 2k not 4k, regenerate only
when the verification gate fails, verify via small thumbnails in one batched read. This replaced an earlier
pattern that authored a ~35KB bespoke build script per client.

## The verification gate (why it exists)

Generation will sometimes render the wrong brand. Real catches: a **Ford Mustang** in a CDJR heritage image
(McPeek run) and a fabricated **"Altitude Marketing Agency"** logo (DigitalCLIQ run). Every asset is now looked
at before it ships; wrong-brand/competitor content is regenerated, never delivered. Never use generic stock as
a vehicle reference (it's full of competitor cars), only client inventory or official OEM CGI.

## Runs so far

- **McPeek (CDJR)**, first live run; 10 hero assets; `outputs/SocialMediaPlan_McPeek_2026-06-24.xlsx`.
- **DigitalCLIQ (agency, non-auto)**, generalization test; founder-led LinkedIn strategy; 8 assets.
- **New Century BMW**, `outputs/SocialMediaPlan_NewCenturyBMW_2026-06-24.xlsx`.

Related: magnific social skill, [[Resources/automotive-guidelines/README|Automotive Guidelines]], [[Context/brand|brand]].
