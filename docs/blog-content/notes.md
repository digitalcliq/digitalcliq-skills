---
type: skill-notes
skill: blog-content
status: active
created: 2026-06-26
tags: [skill, content, blog, seo, aeo, magnific]
---

Vault-side design notes for the **blog-content** skill. Runtime lives at
`.claude/skills/blog-content/` (SKILL.md + scripts + references). Built by [[Drew Moon]] on 2026-06-26,
modeled on [[Skills/social-media-manager/notes|social-media-manager]].

## What it is

A blog + landing-page content engine for **any** brand or prospect. Given just a brand name (e.g.
[[Atlas Shippers International]]), it researches the business end-to-end (website, online citations,
current social presence, reviews, competitors), distills a reusable **voice profile**, then writes a
batch of **3 deeply-researched pieces** (blog posts by default, landing pages on request) in the
brand's own tone. Every piece is engineered for **both** Google ranking **and** AI-answer citation
(AEO/GEO): an answer-up-top block, asserted entities/facts, FAQ, schema, internal links, E-E-A-T.
Keyword + competitor decisions are driven by **live [[Semrush]] MCP data** when available, with an
honest web/SERP fallback when not. Hero visuals are generated live via the [[Magnific]] MCP behind the
brand-lock verification gate. Email rule is hard-enforced: only `drewmoon@digitalcliq.com` ever appears.

## What it ships (to `outputs/`)

- **One DigitalCLIQ-branded Excel tracker**, Cover, Content Plan (hero thumbs + doc links + status),
  SEO & Keyword Brief, AI Search Brief, Article Outlines, Magnific Prompt Library, Generated Assets, Brand Voice, Contact.
- **One polished DigitalCLIQ-branded Word doc per piece**, full 1500-2500 word body, publish pack
  (meta/slug/schema), embedded hero image, FAQ, contact footer.
- **Hero assets** saved to `Projects/<CODE>/blog-assets/<YYYY-MM>/`.
- **Drive delivery + a Google Sheet approval/re-teach tracker** ("Generated Blog Content" folder).

The body is the client's voice; only the deliverable chrome (cover, contact, footer) is DigitalCLIQ-branded.

## Architecture (lean by design)

- **SKILL.md**, orchestration playbook: pre-flight facts ledger, identify brand, brand-voice research,
  SEMRUSH keyword/intent research, topic selection across the funnel, per-piece SEO + AEO briefs, the
  writing, live Magnific generation, the **brand-lock verification gate**, Drive delivery + approval/re-teach, build + validate.
- **references/**, `seo-ai-search-playbook.md` (the strategy brain: rank + get cited), `semrush-playbook.md`
  (drive decisions from live MCP data, with fallback), `brand-voice-extraction.md` (scan footprint → voice
  profile → match), `magnific-blog-imagery.md` (blog-specific deltas; points at the social skill's canonical
  Magnific cheat-sheet + brand-lock gate, single source of truth, not duplicated), `plan-contract.md`
  (compact `plan.json` schema + author-once rule, so the runtime never opens the ~600-line builder).
- **scripts/**, `build_workbook.py` (renders the branded Excel tracker; auto-derives the prompt library +
  gallery from a compact plan; validates), `write_docs.py` (renders one branded `.docx` per piece, embeds the
  hero, merges `doc_path` back into the plan), `download_assets.py` + `fetch_asset.py` (reused as-is from the social skill).

## Efficiency principles

Each run authors only **brand-specific data** (`plan.json`, `meta`, `brand_voice`, `pieces` with `seo`/`aeo`/
`outline`/`body_markdown`, `assets`, `contact`), never code. All file work (download, thumbnails, doc build,
workbook build, validate) is offloaded to the three local scripts. Magnific discipline mirrors the social skill:
batch generation in one turn, one `creations_wait`, 2k not 4k, regenerate only on a failed verification gate,
verify via small thumbnails in one batched read. Hero-only by default (3 images per 3-piece batch).

**Architecture is fan-out → converge, twice, so a 3-piece batch runs in ~one piece's wall-clock.**
(1) Research fan-out (Steps 2-3): 3 agents (voice / keywords / competitors), block once. (2) Production
fan-out (Step 5): one **writer agent per piece** authors its own SEO+AEO brief + full body and returns a
JSON object, while **all heroes generate in a single Magnific batch concurrently**. The orchestrator only
locks the plan (Step 4: topics, a shared context block reused by every writer, per-piece assignments,
hero-prompt drafts, credit gate), then QCs + verifies + assembles (Steps 6, 8). Writers get the rules
distilled into their prompt and do NOT read the references (avoids N× playbook reads). This is the design
for doing client/pitch batches fast. Built this way 2026-06-26.

Audited for token + run efficiency 2026-06-26 (3 parallel review agents). Key designs that came out of it:
**progressive disclosure**, Step 0 reads only the facts ledger, brand, SEO brain, and voice reference;
`semrush-playbook` loads at Step 3, `magnific-blog-imagery` only at Step 7 when `--generate != none`,
`plan-contract` only at Step 8 (the runtime never opens the big Python). **Parallel research**, Steps 2-3
fan out to ONE batch of 3 agents (voice / keywords / competitors), block once. **Fail-fast credits**, `account_balance` + `simulate_cost` moved to end of Step 4, before authoring ~6000 words. **Author-once**, FAQ / answer block / outline live once in `plan.json`; the .docx reuses them. Code fixes: slug-collision
filename guard, WebP dropped from the docx embed path, heading-anchored FAQ de-dup, hero-thumb fallback.

## The SEO + AI-search angle (why it exists)

Modern content has two jobs: rank in Google and get **quoted by AI engines** (ChatGPT, AI Overviews,
Perplexity, Gemini). The skill engineers both at once, a clean 40-60 word answer block per question,
explicit entity/fact assertion, lists/tables/FAQ for extraction, schema recommendations, and E-E-A-T
signals. The same structure that earns an AI citation is what Google lifts into a featured snippet.

## Relationship to social-media-manager

Same DNA: brand research → strategy → live Magnific generation behind the verification gate → branded
deliverable → Drive approval/re-teach loop. It reuses the social skill's asset scripts and references the
canonical Magnific + brand-lock docs rather than copying them. Where social builds a 90-day posting calendar,
this builds long-form, search-optimized written assets.

Related: magnific social skill, semrush projects, [[Context/brand|brand]], [[Context/vault-facts|facts ledger]].
