---
name: blog-content
description: >-
  Researches a brand end-to-end (website, online citations, current social presence, reviews,
  competitors) to capture its voice and vibe, then writes a batch of 3 deeply-researched,
  SEO- and AI-search-optimized pieces of content (blog posts by default, or landing pages) in
  the brand's own tone. Uses live SEMRUSH keyword/competitor data when available (graceful web
  fallback when not), engineers every piece to rank in Google AND get cited by AI answer engines
  (ChatGPT, AI Overviews, Perplexity), generates hero graphics/video LIVE via the Magnific MCP,
  ships each piece as a polished DigitalCLIQ-branded Word doc, and rolls the whole batch into a
  DigitalCLIQ-branded Excel tracker with the SEO + AEO briefs. Use when Drew says /blog-content,
  "write blog content / blogs for [brand]", "build landing pages for [brand]", "blog content".
argument-hint: '"Brand Name" [--type blog|landing] [--count 3] [--generate hero|hero+video|none]'
allowed-tools: mcp__magnific__account_balance, mcp__magnific__simulate_cost, mcp__magnific__images_models_list, mcp__magnific__images_generate, mcp__magnific__video_models_list, mcp__magnific__video_plan, mcp__magnific__video_generate, mcp__magnific__creations_wait, mcp__magnific__creations_get, mcp__magnific__creation_status, mcp__magnific__images_upscale, mcp__magnific__images_relight, mcp__magnific__images_remove_background, mcp__magnific__creations_upload_image, mcp__magnific__creations_request_upload, mcp__magnific__creations_finalize_upload, mcp__781ea802-0e57-4cef-a086-f038da48202d__keyword_research, mcp__781ea802-0e57-4cef-a086-f038da48202d__organic_research, mcp__781ea802-0e57-4cef-a086-f038da48202d__overview_research, mcp__781ea802-0e57-4cef-a086-f038da48202d__backlink_research, mcp__781ea802-0e57-4cef-a086-f038da48202d__siteaudit_research, mcp__781ea802-0e57-4cef-a086-f038da48202d__projects_research, mcp__781ea802-0e57-4cef-a086-f038da48202d__tracking_research, mcp__781ea802-0e57-4cef-a086-f038da48202d__trends_research, mcp__781ea802-0e57-4cef-a086-f038da48202d__url_research, mcp__781ea802-0e57-4cef-a086-f038da48202d__get_report_schema, mcp__781ea802-0e57-4cef-a086-f038da48202d__execute_report, mcp__claude-in-chrome__navigate, mcp__claude-in-chrome__get_page_text, mcp__claude-in-chrome__read_page, mcp__claude-in-chrome__find, mcp__claude-in-chrome__tabs_create_mcp, mcp__claude-in-chrome__tabs_close_mcp, mcp__f2af38f0-679c-499d-bf64-0795855b3613__search_files, mcp__f2af38f0-679c-499d-bf64-0795855b3613__create_file, mcp__f2af38f0-679c-499d-bf64-0795855b3613__get_file_metadata, WebSearch, WebFetch, Bash, Read, Write, Edit, Glob, Grep, Agent, TodoWrite
---

> [!important] Pre-flight: load the facts ledger FIRST
> Before anything else, read `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Context/vault-facts.md` and obey it.
> It is the source of truth for: output location (always the vault `outputs/` folder), the canonical
> working folder, the canonical logo path, and **correct client/competitor names + relationships**
> (e.g. LOGO Cargo is a hostile splinter of Atlas, not a partner; BMW of Buena Park is AutoNation).
> Vault names beat web research. Validate every output path and name against it before writing.

> [!warning] The email rule: non-negotiable
> The only DigitalCLIQ contact address that may appear ANYWHERE in any deliverable is
> **drewmoon@digitalcliq.com**. `digitalcliq@gmail.com` is BANNED. `build_workbook.py` and
> `write_docs.py` both hard-refuse to save if the gmail address appears in the data, do not work
> around it, fix the data.

# Blog Content Engine: DigitalCLIQ

## What this produces

For a single brand, in `outputs/`, a **3-piece content batch** (blog posts by default; landing
pages on request), every piece deeply researched, SEO + AI-search engineered, and written in the
brand's own voice:

1. **One DigitalCLIQ-branded Excel tracker** (`BlogContentPlan_<Brand>_<YYYY-MM-DD>.xlsx`) with:
   Cover · **Content Plan** (the 3 pieces, hero thumbnails, doc links, status) · **SEO & Keyword
   Brief** (cluster, intent, meta, slug, internal links, SERP gap) · **AI Search Brief** (the
   citable answer block, entities, schema, E-E-A-T, why it gets cited) · **Article Outlines** ·
   **Magnific Prompt Library** · **Generated Assets** gallery · **Brand Voice** profile · Contact.
2. **One polished DigitalCLIQ-branded Word doc per piece** (`Blog_<brand>_<slug>.docx`) holding the
   full 1500-2500 word body, the publish pack (meta/slug/schema), the embedded hero image, and an FAQ.
3. **Hero visuals generated live via Magnific**, verified, and saved into the vault.
4. **Drive delivery + a Google Sheet approval/re-teach tracker** (mirrors the social skill).

## Works for ANY brand

Automotive (any OEM), shipping/logistics (e.g. Atlas), retail, services, B2B, or a brand-new
prospect you are pitching. The process is the same; only the research sources and the compliance
rulebook change. For automotive, OEM rules live in `Resources/automotive-guidelines/` and the
brand-lock/ad-law discipline applies. For anything else, research the brand's voice, products,
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

> [!note] How the design system applies to THIS skill
> The per-piece `.docx` files are client-facing article files: the article body stays in the CLIENT's voice, and DigitalCLIQ chrome = the Digital Blue masthead band (white logo) + branded footer. **Known gap:** these article docs use the masthead-band header, not a full canonical cover PNG page (a cover page inside a publish-ready blog doc would pollute the deliverable). The Excel tracker's dark Cover/Contact tabs are built in-code per Design-System §4 (Excel has no HTML-cover path).

## Knowledge base (read on a need-to-know schedule, not all at once)
Load references progressively to keep context lean. Read upfront ONLY the two that govern strategy
+ voice; load the other two at the step that uses them.
- **Upfront (Step 0):** `references/seo-ai-search-playbook.md`, **the strategy brain** (rank in
  Google AND get cited by AI engines: topic selection, keyword clusters, on-page, the citable answer
  block, schema, E-E-A-T, quality bar), and `references/brand-voice-extraction.md` (scan footprint →
  voice profile → match; client voice in the body, DigitalCLIQ branding only on the chrome).
- **At Step 3 only:** `references/semrush-playbook.md`, drive keyword/topic decisions from live
  SEMRUSH MCP data, with an honest web fallback.
- **At Step 5b only, and only if `--generate != none`:** `references/magnific-blog-imagery.md`,
  blog-specific Magnific deltas; points to the canonical cheat-sheet + the mandatory brand-lock gate.
- **At Step 8 only:** `references/plan-contract.md`, the compact `plan.json` schema + author-once
  rule. Read this, never the Python scripts.

## Efficiency (keep token + credit cost low)
- **Author only DATA, never code.** One compact `plan.json` per run: `meta`, `brand_voice`,
  `pieces` (each with `seo`, `aeo`, `outline`, and `body_markdown`), an `assets` registry, and
  `contact`. The two scripts do all rendering and file work.
- **Offload file work to local scripts:** `download_assets.py` (batch download + thumbnails),
  `write_docs.py` (renders the branded .docx per piece, embeds the hero, merges `doc_path` back),
  `build_workbook.py` (builds + validates the tracker). You author URLs + prose once; scripts do the rest.
- **Magnific discipline:** batch all `images_generate` in ONE turn; ONE `creations_wait` per batch;
  2k resolution; `simulate_cost` once before a batch; never `creations_show` (no inline UI here);
  regenerate ONLY when the verification gate fails. Verify assets in ONE batched Read of `_thumb.png`.
  Hero-only by default (3 images for a 3-piece batch).
- **The shape is fan-out → converge, twice.** Two parallel barriers do almost all the work, so a
  3-piece batch finishes in roughly one piece's wall-clock, not three. (1) Research fan-out (Steps
  2-3). (2) Production fan-out (Step 5): one writer Agent per piece authoring its own brief + body,
  while ALL heroes generate in a single Magnific batch concurrently. The orchestrator only locks the
  plan (Step 4) and QCs/assembles (Steps 6, 8), it never writes the bodies itself.
- **Parallelize research** (Steps 2-3): after Step 1, fire ONE parallel Agent batch of three,
  (a) brand voice + reviews + social scan, (b) SEMRUSH keywords + organic/gap + trends, (c) 2-3
  competitor SERP/content analysis. Block once, collect all three, then select topics. Within each
  agent, issue all independent WebSearch/WebFetch/SEMRUSH calls in one parallel turn, not one-by-one.
- **Fail fast on credits:** check Magnific `account_balance` + one `simulate_cost` right after topics
  lock (end of Step 4), BEFORE authoring ~6000 words. Never write the batch then discover no credits.

---

## Process

### Step 0: Pre-flight
Read ONLY: `Context/vault-facts.md`, `Context/brand.md`, `references/seo-ai-search-playbook.md`,
and `references/brand-voice-extraction.md`. (Defer `semrush-playbook.md` to Step 3,
`magnific-blog-imagery.md` to Step 5b, `plan-contract.md` to Step 8: see Knowledge base.)
Parse `$ARGUMENTS`: brand name (required), `--type` (default `blog`), `--count` (default `3`),
`--generate` (default `hero`). Default depth is **punchy, 800-1000 words** per piece: tight, scannable,
every sentence earning its place. Go longer (pillar-grade 1500-2500) only when the brief asks for it.

### Step 1: Identify the brand (PROMPT only if unclear)
If the brand is already a vault project (e.g. Atlas = `Projects/Atlas/`, McPeek = `Projects/MCP/`),
read its README for brand, products, audience, handles, competitors, and any documented voice.
If the business type, customer, or goal is genuinely unclear from research, ask a short set:
what they sell + who buys, is it automotive (which OEM → load that rulebook), the single business
goal these pieces serve (leads / bookings / foot traffic / quote requests), and any must-hit topics.
For automotive, load OEM rules from `Resources/automotive-guidelines/` and never invent prices/terms.

### Steps 2-3: Research, in ONE parallel Agent batch (fan out, then block once)
Fire three Agents concurrently and collect all results before topic selection:
- **(a) Brand + voice**: per `references/brand-voice-extraction.md`, scan the website, current
  social presence, reviews, online citations, and any vault collateral. Return products/services,
  the customer, the local market, and the **voice profile** (`summary`, `tone_attributes`,
  `reading_level`, `do`, `dont`, `sample_phrases`, `sources`). The agent reads that reference; the
  field spec lives there, don't restate it.
- **(b) Keywords + intent (SEMRUSH first)**: the agent reads `references/semrush-playbook.md`, then
  seeds 10-20 topics, runs `keyword_research` (volume/KD/intent/variants), `organic_research` on the
  client + the 2-3 competitors, and `trends_research` if timing matters, all independent calls in
  one parallel turn. If no usable SEMRUSH data, fall back to SERP / autocomplete / People-Also-Ask
  and **set `meta.semrush_used = false`**. Record real numbers; never fabricate. Also harvest the
  PAA questions here so Step 5 doesn't re-run them.
- **(c) Competitor SERP/content gap**: analyze the 2-3 real competitors (correct names + relationships
  per the facts ledger) and what their ranking pages do that the client's don't (the content gap).

### Step 4: Converge + lock the batch plan (orchestrator, on the main thread)
Collect the three research agents' results. Then YOU (the orchestrator) lock the plan so the parallel
engine has everything it needs and the pieces stay consistent:
- Pick the 3 strongest, winnable, gap-filling topics; default to one **TOFU**, one **MOFU**, one
  **BOFU** (override per the brief / `--type`).
- Build a one-paragraph **shared context block** reused verbatim by every writer: the voice profile,
  brand facts + correct competitor names/relationships, the compliance rulebook (automotive OEM if
  applicable), and the global rules (no em dashes; no fabricated stats/prices; flag regulated claims).
- For EACH piece, write a tight **assignment**: type, funnel stage, primary keyword + cluster (with
  metrics), search intent, the target question, the content gap/angle, and internal-link targets
  (including links to the OTHER two pieces in this batch, so they cross-link).
- Draft each piece's **hero prompt** now (from the topic/angle + brand visual identity, the body
  isn't needed), so heroes can generate in parallel with the writing.
- **Fail-fast credit gate:** if `--generate != none`, call Magnific `account_balance` + one
  `simulate_cost` on a sample hero. Confirm headroom and lock the hero count BEFORE the engine runs.

### Step 5: PRODUCE IN PARALLEL (the engine, this is where the speed comes from)
Fire BOTH of these concurrently in one turn, then block once and collect everything:

**5a: one writer Agent per piece (N agents at once).** Each writer gets its self-contained
assignment + the shared context block from Step 4 and returns a single JSON object for that piece:
`{seo, aeo, outline, body_markdown, image_alt}`: i.e. it authors its OWN brief (SEO + AEO + outline)
AND the full body together, since they're one coherent act of writing.
- **Pass the rules in the prompt; do NOT have writers read the references** (avoids N× re-reading the
  playbook). Distill the must-follow rules into each prompt: answer the target question in the first
  2-3 sentences; one question per H2; FAQ as H3s in `outline.faq` (not retyped in the body); assert
  entities/facts plainly; a 40-60 word citable answer block; weave the keyword cluster naturally;
  1-3 cited authoritative sources; **punchy 800-1000 words** by default (short sentences and paragraphs,
  strong verbs, cut throat-clearing and filler); **match the brand voice, not DigitalCLIQ's**; no em
  dashes; flag any regulated claim. Tight beats long. This is the product, so demand genuinely good writing.

**5b: generate ALL heroes in one Magnific batch (concurrent with 5a).** Skip if `--generate none`.
First read `references/magnific-blog-imagery.md` + the canonical brand-lock gate. Then brand-lock each
Step 4 hero prompt (name the subject; explicit no-competitor exclusion clause naming brands/logos to
exclude: e.g. exclude LOGO Cargo for Atlas; 16:9; match the brand's visual identity). Fire ALL
`images_generate` in ONE turn → ONE `creations_wait` → `creations_get` for `url`/`thumbnailUrl`. If
hero videos are requested, batch them too with ONE additional `creations_wait`. Persist each with
`scripts/fetch_asset.py --url <full> --out <vault_path> --thumb-url <thumb> --thumb-out <thumb_path>`
under `Projects/<CODE>/blog-assets/<YYYY-MM>/`.

### Step 6: Converge: QC the pieces + verify the assets (orchestrator)
Now everything is back. Run the convergence pass before assembling anything:
- **Asset verification gate (MANDATORY):** in ONE batched Read of the small `_thumb.png` files,
  confirm each hero is (1) on-brand + correct subject, (2) **NO competitor brand/logo/product anywhere**
  (incl. background + reflections), (3) clean + compliant, (4) realistic + on-voice. **Regenerate any
  failure** with a tightened exclusion clause naming what appeared. Never ship an unverified asset.
- **Cross-piece QC:** confirm the 3 pieces don't overlap/cannibalize, that their internal links point
  at each other + the brand's money pages, that meta titles/slugs are distinct, and that the voice is
  consistent across all three. Fix anything off here, not in a second model-heavy pass.
- Attach each verified hero's `image_alt` (from its writer) into that piece's `seo` brief.

### Step 7: Deliver to the brand's Google Drive + approval Sheet
Mirror the social skill (see the brand-lock reference §5):
- `search_files` the shared-drive parent (`1Djzd6gQijrq1eDKbLFlTuQWpAarKMsxX`) for the brand's folder.
- Create/reuse a **"Generated Blog Content"** subfolder (`create_file`, folder mime).
- Create a native **Google Sheet approval tracker** (`create_file`, `text/csv` → auto-converts):
  piece title, type, target keyword, **Decision (Approve / Revise / Deny)**, **Re-Teach Notes**,
  the doc link, the asset link, the Magnific link, the vault path. This is the human-feedback surface.
- Binaries can't be auto-pushed into Drive (no OS dialog; API can't carry multi-MB base64). Assets +
  docs live in the vault, linked from the Sheet; stage compressed copies in `outputs/_blog_drive/`
  for a one-drag manual upload and tell the user.
- **Re-teach:** on later runs for this brand, read the Sheet first, favor Approved patterns/topics,
  avoid Denied ones, honor the notes.

### Step 8: Assemble + build the deliverables (lean, local)
Read `references/plan-contract.md` (the compact schema + author-once rule, do NOT open the Python).
**Assemble** ONE `plan.json` by dropping each writer's returned JSON straight into `plan['pieces']`
(no re-typing: the FAQ, citable answer block, and outline are authored once by the writer and reused
by both the .docx and the Excel) and adding `meta`, `brand_voice`, `contact`, and the `assets`
registry (each hero's Magnific `src_url`/`src_thumb_url`/`web`/`credits`). Then run, **from the vault
root** so relative paths resolve:
```bash
S=".claude/skills/blog-content/scripts"
python3 "$S/download_assets.py" plan.json "Projects/<CODE>/blog-assets/<YYYY-MM>" <CODE>
python3 "$S/write_docs.py"      plan.json "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs"
python3 "$S/build_workbook.py"  plan.json \
  "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/BlogContentPlan_<Brand>_<YYYY-MM-DD>.xlsx"
```
`write_docs.py` renders one branded .docx per piece and merges `doc_path` back into the plan;
`build_workbook.py` embeds thumbnails, links the docs, hard-refuses the banned email, and validates.

### Step 9: Validate + present
Confirm the workbook and every .docx are in `outputs/`, open, carry the logo, and contain no
placeholder tokens or the gmail address. Then run the **Visual-QA render gate** on the workbook and
every .docx (`python3 Resources/design-system/templates/render_check.py <file>`): visually read every
rendered page/sheet, fix defects in the generator scripts or plan data, re-render until two
consecutive clean passes, and report passes run + defects caught. Tell the operator: the 3 topics chosen (with the keyword +
intent + why each), whether live SEMRUSH data was used, the hero assets generated (and where they
live), the Drive folder + approval Sheet link, and the credits used. Persist durable new facts
(confirmed handles, the voice profile, the keyword targets) to the brand's `Projects/<CODE>/` README
or research folder.

---

## Critical rules
1. **Output** → `outputs/` only. Workbook `BlogContentPlan_<Brand>_<YYYY-MM-DD>.xlsx`; docs `Blog_<brand>_<slug>.docx`.
2. **Assets** → `Projects/<CODE>/blog-assets/<YYYY-MM>/`. Never root, Desktop, or tmp as final home.
3. **Email** → drewmoon@digitalcliq.com only. Never the gmail.
4. **Brand voice in the body, DigitalCLIQ branding only on the chrome** (cover, contact, doc footer).
5. **SEO + AI-search both**: every piece engineered to rank in Google AND be citable by AI engines:
   the answer-up-top block, entity assertions, FAQ, schema, internal links, E-E-A-T.
6. **Honest data**: use live SEMRUSH when available; otherwise label estimates and set `semrush_used=false`. Never fabricate metrics, stats, prices, or dates.
7. **Compliance**: regulated claims (automotive price/lease/finance, legal, medical, financial) need real approved numbers + disclaimer; flag for sign-off, never invent.
8. **Brand-lock + verify**: every generated asset is STRICTLY the brand's; name competitors to exclude; run the Step 6 vision gate on every asset. A wrong-brand logo/product NEVER ships.
9. **Drive delivery**: verified docs + assets → the brand's "Generated Blog Content" Drive folder + a Google Sheet approval/re-teach tracker. Read that Sheet on the next run.
10. **Branding**: logo from the canonical path; fail loudly if missing. **No em dashes**, ever.
11. **Cost discipline**: `simulate_cost` before batch generation; report credits used.


## Final QA Gate: deliverable-reviewer agent (MANDATORY, added 2026-08-13)

Runs AFTER the deliverable is generated and post_flight.py passes, BEFORE filing/presenting. post_flight.py is mechanical; this gate is the human-style read.

1. **Write a facts manifest** next to the deliverable in `outputs/`: a JSON list of every number, name, date, and claim that appears in the deliverable, each as `{"value": ..., "label": "where it appears", "source": "tool/file/URL it came from"}`. Build it from data already in context, never re-fetch anything just for the manifest.
2. **Spawn the `deliverable-reviewer` agent** (fresh eyes, it did not write the report). Pass in the prompt: the absolute path(s) of the finished deliverable file(s), the manifest path, and any skill-specific checks from this SKILL.md. It renders every page, reads them all, cross-checks figures against the manifest, and reviews tone/copy.
3. **Auto-fix every finding** in the source generator or data (never by hand-editing the output), re-render, and re-run the agent once. Max 2 review passes. If CRITICAL or MAJOR findings remain after pass 2, the ship is BLOCKED: report the remaining findings to Drew verbatim instead of presenting the file as done.
4. The run summary MUST include a **QA line**: what the reviewer caught and what was fixed, or "QA: clean on first pass (N pages read, M figures verified)". Never silently skip the gate; if the agent could not run, say so explicitly in the delivery message.
5. **Blog-content specific**: run the gate on EVERY output file, each Word doc AND the Excel tracker, not just the last one generated.
