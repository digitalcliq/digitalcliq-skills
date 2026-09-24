---
name: social-media-manager
description: >-
  Acts as an AI social media manager for a client. Researches the client's brand
  (voice, style, guidelines — and for automotive pulls OEM rules from the vault),
  pulls live follower/engagement baselines across Instagram, TikTok, YouTube,
  X/Threads, and Facebook, then builds a 30/60/90-day game plan to 2x followers
  and interactions with a deeply-reasoned content calendar. Every asset gets a
  paste-ready generation prompt, and hero assets are generated LIVE via the
  Magnific MCP, saved into the vault, and embedded + linked in a DigitalCLIQ-branded
  Excel workbook. Built on 2026 platform mechanics (no hashtag crutch). Use when
  Drew says /social-media-manager, "build a social plan/calendar for [client]",
  "grow [client]'s socials", or "social media manager".
argument-hint: '"Client Name" [platforms] [--generate hero|first30|all|none]'
allowed-tools: mcp__magnific__account_balance, mcp__magnific__simulate_cost, mcp__magnific__images_models_list, mcp__magnific__images_generate, mcp__magnific__video_models_list, mcp__magnific__video_plan, mcp__magnific__video_generate, mcp__magnific__creations_wait, mcp__magnific__creations_get, mcp__magnific__creations_show, mcp__magnific__creation_status, mcp__magnific__images_upscale, mcp__magnific__images_relight, mcp__claude-in-chrome__navigate, mcp__claude-in-chrome__get_page_text, mcp__claude-in-chrome__read_page, mcp__claude-in-chrome__javascript_tool, mcp__claude-in-chrome__find, mcp__claude-in-chrome__tabs_create_mcp, mcp__claude-in-chrome__tabs_close_mcp, WebSearch, WebFetch, Bash, Read, Write, Edit, Glob, Grep, Agent, TodoWrite
---

> [!important] Pre-flight: load the facts ledger FIRST
> Before anything else, read `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Context/vault-facts.md` and obey it.
> It is the source of truth for: output location (always the vault `outputs/` folder), the canonical
> working folder, the DigitalCLIQ Master calendar, the canonical logo path, and correct client/competitor
> names. Validate every output path and name against it before writing.

> [!warning] The email rule: non-negotiable
> The only DigitalCLIQ contact address that may appear ANYWHERE in any deliverable is
> **drewmoon@digitalcliq.com**. `digitalcliq@gmail.com` is BANNED. `build_workbook.py` will hard-refuse
> to save if the gmail address appears in the data, do not work around it, fix the data.

# Social Media Manager: DigitalCLIQ

## What this produces

A single DigitalCLIQ-branded **Excel workbook** in `outputs/` with:
1. **Cover**: client, goal, how to read it.
2. **Growth Scoreboard**: live baseline → 30/60/90 targets → the 2x line, per platform.
3. **2026 Playbook**: per-platform ranking signals + formats (no hashtag crutch).
4. **90-Day Calendar**: every post: campaign, format, hook, caption direction, **generation prompt**, KPI, an **embedded asset thumbnail**, and a **clickable link** to the generated file.
5. **Campaign Deep-Dives**: the thinking behind each major campaign.
6. **Magnific Prompt Library**: paste-ready prompts + exact model/settings + Claude/Gemini/Sora fallbacks.
7. **Generated Assets**: the real photos/videos generated via Magnific, saved to the vault, linked.
8. **Contact**: the DigitalCLIQ point of contact (drewmoon@digitalcliq.com only).

Hero assets are generated **live via the Magnific MCP** and dropped into the vault.

## Works for ANY client

This is a jump-start tool for **any business type and any brand**: automotive (any OEM), retail,
services, B2B, a brand-new prospect you're pitching. The process below is the same; only the
research sources and compliance rulebook change. For automotive, the OEM rules already live in
`Resources/automotive-guidelines/`. For anything else, research the brand's voice, products,
guidelines, and competitors, then apply the same brand-lock + verification discipline.

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

> [!note] Whose brand goes where
> The design-system block above governs the **DigitalCLIQ deliverable**: the Excel workbook (`build_workbook.py` implements the §4 Excel spec. Digital Blue mastheads, Dosis/Roboto Slab, palette-only tints, white knockout logo). The **generated social creative** (Magnific images/video, captions, prompts) follows the **CLIENT's** brand and OEM rules per `references/generation-brand-lock.md` and `references/automotive-compliance.md`, never put DigitalCLIQ branding on client-facing social assets.

## Knowledge base (read these)
- `references/2026-platform-playbook.md`: the 2026 growth mechanics for all 5 platforms + content pillars + best-in-class accounts. **This is the strategy brain.**
- `references/generation-brand-lock.md`: **MANDATORY.** Brand-lock prompting, the no-competitor rule, the verification gate, brand-safe references, and the Drive + approval/re-teach loop.
- `references/automotive-compliance.md`: OEM brand + CA ad-law rules (CDJR/BMW/Nissan/Chevy/Harley) and where the vault rulebooks live.
- `references/magnific-cheatsheet.md`: Magnific models, the image→video flow, and the generate→vault→workbook pipeline.
- `references/playbook-data.json`: the reusable 2026 playbook for all 6 platforms. `build_workbook.py` merges it automatically; **do not re-author platform mechanics per run.**

## Efficiency (do this: it keeps token + credit cost low)
- **Author only client-specific DATA**, never code. One compact `plan.json` per run: `meta`, `scoreboard`,
  `calendar` (rows reference assets via `"asset_id"`), `campaigns`, `contact`, `playbook_platforms`
  (a list of keys into `playbook-data.json`), and an `assets` registry. The builder auto-derives the
  prompt library, the generated-assets gallery, the calendar thumbnails, and the playbook tab. No bespoke
  build script, no re-authored playbook, no per-asset boilerplate.
- **Offload all file work to local scripts**: `download_assets.py` (batch download + thumbnails + merges
  paths back into the plan) then `build_workbook.py` (builds + validates). You write URLs into the plan
  once; the scripts do the rest.
- **Magnific discipline:** batch all `images_generate` calls in ONE turn; ONE `creations_wait` per batch;
  2k resolution (not 4k); `simulate_cost` once if at all (image ~75, gpt-2 ~195, video ~1.9k credits);
  never `creations_show` (no inline UI); regenerate ONLY when the verification gate fails. Verify all
  assets in ONE batched Read of the small `_thumb.png` files. Generate hero-only by default.

---

## Process

### Step 0: Pre-flight
Read `Context/vault-facts.md`, `Context/brand.md`, and this skill's three reference files.
Parse `$ARGUMENTS`: client name, optional platform list (default IG, TikTok, YouTube, X/Threads, Facebook),
and `--generate` mode (default `hero`).

### Step 1: Identify the business (PROMPT if unclear)
Determine what kind of business this is. If the client is already a vault project (e.g. McPeek = `Projects/MCP/`),
read its README for brand, contacts, handles, and connector IDs. If the business type, brand, or target
customer is not obvious, **ask the operator** a short set of questions:
- What does the business sell, and who is the customer?
- Is it automotive? If so, which OEM/brand? (→ load the matching `references/automotive-compliance.md` rulebook)
- What is the brand voice, and are there brand guidelines/assets to honor?
- What is the single business goal these socials serve (leads, foot traffic, bookings, awareness)?

For **automotive**, you already know where the resources live, load the OEM guideline set from
`Resources/automotive-guidelines/` and apply `references/automotive-compliance.md`. Never invent prices or terms.

### Step 2: Research the client + competitors
Use WebSearch + WebFetch (and browser tools) to capture: brand voice from existing posts/site, products/
inventory focus, local market, and 2-3 direct competitors with what they do well on social. For a multi-
client research load, fan out parallel Agents. Confirm the client's actual handles on every target platform.

### Step 3: Pull live baselines (browser)
For each platform, get the current **follower count** and a recent **engagement read** (avg likes+comments+
shares+saves on the last ~9-12 posts → engagement rate). Use the Chrome browser tools on the public profile;
fall back to WebSearch snippets / public sources if a profile is JS-rendered or blocked. **Record a confidence
level for every number** and the pull date. If a platform account does not exist, mark it a **launch lane**
(the plan becomes "0 → launch target", not a 2x).

### Step 4: Set the 2x targets (be honest)
Apply `references/2026-platform-playbook.md` benchmarks. Doubling is realistic from a **small base**
(under ~3-5k) or with a TikTok breakout; for large established pages, reset to +15-30% followers and **2x
interactions** (interactions are controllable and double faster). Build the Scoreboard: baseline → Day 30 →
Day 60 → Day 90 (2x) followers, plus the 2x-interactions line, plus each platform's primary growth levers.
TikTok-led + Reels/Shorts + near-daily cadence is the engine.

### Step 5: Build the 90-day calendar + campaigns
Sequence the 8 content pillars across three 30-day sprints (0-30 establish + launch missing channels,
30-60 scale winners, 60-90 compound + collabs). For each row: week, phase, target date, platform, campaign,
format, hook/concept, caption direction (with the 2026 lever it pulls, sends/saves/replies/watch-time),
KPI, status. Write **Campaign Deep-Dives** explaining the big idea and why it works in 2026. Any price/lease
claim → mark "Compliance sign-off required", never invent numbers.

### Step 6: Prompt-engineer every asset
For each visual, write a paste-ready **primary Magnific prompt** with the exact model + settings, plus
short **fallbacks** for Claude, Gemini/Nano Banana, and Sora/Veo. Use `references/magnific-cheatsheet.md`
for model choice (Nano Banana Pro for vehicle/brand fidelity, gpt-2 for text/promo graphics, Recraft for
fast photoreal; Seedance 2.0 / Kling for video). Respect the OEM palette + nomenclature rules.

### Step 7: GENERATE hero assets live (Magnific MCP)
**Read `references/generation-brand-lock.md` first.** Per `--generate` (default `hero` = ~8-12 flagship assets):
1. `account_balance` → confirm headroom. `simulate_cost` a sample image + video first.
2. **Brand-lock every prompt:** name the exact make/model, add the explicit no-competitor exclusion
   clause (name the brands to exclude), keep it clean/new/photoreal. Optionally feed a **brand-safe**
   reference image (client inventory or OEM CGI. NEVER generic stock, which is full of competitor cars).
3. Fire `images_generate` calls (one per distinct hero prompt; several per turn). `creations_wait` →
   `creations_get` for `url` + `thumbnailUrl`. (Seedance video can false-trigger moderation; fall back to Kling.)
4. For hero video: `video_generate` with `keyframes.start` = the hero image's creation identifier
   (animate the still), add `cameraMotion` + `withSoundEffects`. Wait + get.
5. Persist each with `scripts/fetch_asset.py --url <full> --out <vault_path> --thumb-url <thumb> --thumb-out <thumb_path>`
   under `Projects/<CODE>/social-assets/<YYYY-MM>/`.

### Step 7.5: VERIFY every asset (MANDATORY GATE, do not skip)
Look at each generated asset (Read the image / video poster) and confirm: (1) correct brand + model,
(2) **NO competitor vehicle / badge / logo / name anywhere**, (3) brand-compliant + clean, (4) realistic
+ on-voice. **Regenerate any that fail** with a tightened exclusion clause naming the wrong brand that
appeared. Never accept or ship an unverified asset. Record pass/fail + the fix for the re-teach loop.
Generated vehicles are brand/concept imagery, not a real VIN or binding offer; flag price-bearing assets for compliance.

### Step 7.6: Deliver to the client's Google Drive + approval Sheet
- `search_files` the shared-drive parent (`1Djzd6gQijrq1eDKbLFlTuQWpAarKMsxX`) for the client's folder by name.
- Create/reuse a **"Generated Social Content"** subfolder (`create_file`, folder mime).
- Create a native **Google Sheet approval tracker** in it (`create_file`, `text/csv` textContent →
  auto-converts): asset, type, brand/vehicle verified, **Decision (Approve/Deny/Revise)**, **Re-Teach
  Notes**, Magnific link, vault path, prompt. This is the human-feedback + re-teach surface.
- Binaries can't be auto-pushed into Drive (Drive's uploader needs an OS dialog; the API can't carry
  multi-MB base64). Assets live in the vault + Magnific cloud, linked from the Sheet; stage compressed
  copies in `outputs/_smm_drive/` for a one-drag manual upload and tell the user.
- **Re-teach:** on later runs for this client, read the Sheet first, favor Approved patterns, avoid
  Denied ones, honor the notes.

### Step 8: Build the workbook (lean, local)
Author ONE compact `plan.json` (data only: see the Efficiency section + the contract in
`scripts/build_workbook.py`). Put each asset's Magnific `src_url`/`src_thumb_url`/`web`/`credits` straight
into `plan['assets']`. Then two local calls do everything (download + thumbnails + auto-derive + build + validate):
```bash
S=".claude/skills/social-media-manager/scripts"
python3 "$S/download_assets.py" plan.json "Projects/<CODE>/social-assets/<YYYY-MM>" <CODE>
python3 "$S/build_workbook.py" plan.json \
  "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/SocialMediaPlan_<Client>_<YYYY-MM-DD>.xlsx"
```
`build_workbook.py` embeds thumbnails, links assets, hard-refuses the banned email, and prints a validation
result (in outputs/, branded, no placeholders). Run from the vault root so relative asset paths resolve.

### Step 9: Validate + present
Confirm the file is in `outputs/`, opens, has the logo, and contains no placeholder tokens or the gmail
address. Then run the Visual-QA render gate from the design-system block (item 7): render, visually read
every tab, fix in `build_workbook.py` or the plan data, repeat to two consecutive clean passes. Tell the operator: the scoreboard headline (baseline → 2x per platform), the launch lanes,
the hero assets generated (with where they live in the vault), and the credits used. Persist any durable
new facts (confirmed handles, baselines) to the client's `Projects/<CODE>/` README.

---

## Critical rules
1. **Output** → `outputs/` only. Filename `SocialMediaPlan_<Client>_<YYYY-MM-DD>.xlsx`.
2. **Assets** → `Projects/<CODE>/social-assets/<YYYY-MM>/` in the vault. Never root, Desktop, or tmp as final home.
3. **Email** → drewmoon@digitalcliq.com only. Never the gmail.
4. **2026 only**: strategy must reflect current-year mechanics; hashtags are not the plan.
5. **Honesty on 2x**: never promise a 2x that the base/benchmarks don't support; set the controllable interactions-2x as the floor.
6. **Compliance**: automotive price/lease/finance claims need real approved numbers + disclaimer; flag for sign-off, never invent.
7. **Brand-lock + verify**: every generated asset is STRICTLY the client's brand. Name competitors to exclude in the prompt, and run the Step 7.5 vision gate on every asset. A wrong-brand vehicle/logo NEVER ships. Never use generic stock as a vehicle reference.
8. **Drive delivery**: verified assets → the client's "Generated Social Content" Drive folder + a Google Sheet approval/re-teach tracker. Read that Sheet on the next run to improve prompts.
9. **Branding**: logo from the canonical path; fail loudly if missing.
10. **Cost discipline**: `simulate_cost` before batch generation; report credits used.


## Final QA Gate: deliverable-reviewer agent (MANDATORY, added 2026-08-13)

Runs AFTER the deliverable is generated and post_flight.py passes, BEFORE filing/presenting. post_flight.py is mechanical; this gate is the human-style read.

1. **Write a facts manifest** next to the deliverable in `outputs/`: a JSON list of every number, name, date, and claim that appears in the deliverable, each as `{"value": ..., "label": "where it appears", "source": "tool/file/URL it came from"}`. Build it from data already in context, never re-fetch anything just for the manifest.
2. **Spawn the `deliverable-reviewer` agent** (fresh eyes, it did not write the report). Pass in the prompt: the absolute path(s) of the finished deliverable file(s), the manifest path, and any skill-specific checks from this SKILL.md. It renders every page, reads them all, cross-checks figures against the manifest, and reviews tone/copy.
3. **Auto-fix every finding** in the source generator or data (never by hand-editing the output), re-render, and re-run the agent once. Max 2 review passes. If CRITICAL or MAJOR findings remain after pass 2, the ship is BLOCKED: report the remaining findings to Drew verbatim instead of presenting the file as done.
4. The run summary MUST include a **QA line**: what the reviewer caught and what was fixed, or "QA: clean on first pass (N pages read, M figures verified)". Never silently skip the gate; if the agent could not run, say so explicitly in the delivery message.
