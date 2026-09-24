# SEO + AI-Search Playbook (the strategy brain for /blog-content)

This is how DigitalCLIQ writes blog content that ranks in Google **and** gets cited by
AI answer engines (ChatGPT, Google AI Overviews, Perplexity, Gemini, Copilot). Every
piece is engineered against both targets at once. Read this before topic selection and
keep it open while writing.

## Contents

- [The two jobs, side by side](#the-two-jobs-side-by-side)
- [Step 1: Topic selection (intent first, volume second)](#step-1--topic-selection-intent-first-volume-second)
- [Step 2: Keyword cluster, not a single keyword](#step-2--keyword-cluster-not-a-single-keyword)
- [Step 3: On-page SEO checklist (every piece)](#step-3--on-page-seo-checklist-every-piece)
- [Step 4: AI-Search optimization (AEO / GEO), the differentiator](#step-4--ai-search-optimization-aeo--geo--the-differentiator)
- [Step 5: Quality bar (the writing itself)](#step-5--quality-bar-the-writing-itself)
- [Step 6: Measurement note (put in the brief, not the body)](#step-6--measurement-note-put-in-the-brief-not-the-body)
- [The one-line standard](#the-one-line-standard)

## The two jobs, side by side

| | Classic SEO (Google ranking) | AI Search / AEO-GEO (citation) |
|---|---|---|
| The unit that wins | A page that ranks for a keyword | A passage an engine quotes/synthesizes |
| Optimizes for | Keyword relevance, links, authority, UX | Extractable answers, entities, factual density, source trust |
| Trigger | A typed query | A natural-language question / follow-up |
| Reward | Click | Mention + (often) a linked citation |

You do not choose one. A well-structured answer block that earns AI citations is also
the passage Google lifts into a featured snippet. Build for extraction and you win both.

## Step 1: Topic selection (intent first, volume second)

1. Start from the **business goal** (leads, bookings, foot traffic, quote requests) and
   the customer's real questions, not vanity keywords.
2. Pull demand data: SEMRUSH if the domain/market has it (`references/semrush-playbook.md`),
   otherwise SERP + autocomplete + People-Also-Ask research via WebSearch/WebFetch.
3. For each candidate topic capture: **primary keyword, monthly volume, keyword difficulty
   (KD), and search intent** (informational / commercial / transactional / navigational).
4. **Pick by opportunity, not by volume.** A KD-low, intent-matched, mid-volume keyword the
   site can actually rank for beats a KD-90 head term. Favor topics where the current SERP
   is weak, outdated, thin, or missing the brand's specific angle (the **content gap**).
5. Map each of the 3 pieces to a **funnel stage** so the batch covers ground:
   - **TOFU** (informational): "how / what / why / cost of / guide to", earns reach + AI citations.
   - **MOFU** (commercial): "best / vs / reviews / for [use-case]", comparison, consideration.
   - **BOFU** (transactional / landing): "near me / pricing / book / get a quote", converts.
   A strong default batch is one of each unless the brief says otherwise.

## Step 2: Keyword cluster, not a single keyword

Each piece targets ONE primary keyword plus a **semantic cluster**: 5-15 secondary terms,
synonyms, long-tail variants, and the questions around it. Modern ranking is topic-based,
so depth on the whole cluster beats keyword-stuffing one phrase. Capture the cluster in the
SEO brief and weave it naturally through H2s, the body, and the FAQ.

## Step 3: On-page SEO checklist (every piece)

- **Title tag / meta title:** ≤60 chars, primary keyword near the front, a reason to click.
- **Meta description:** ≤155 chars, keyword + value prop + soft CTA. Not a ranking factor
  directly, but it drives CTR which is.
- **URL slug:** short, hyphenated, keyword-bearing, no stop-word clutter.
- **H1:** one per page, contains the primary keyword, reads like a human wrote it.
- **H2/H3 structure:** descriptive, question-shaped where natural, cluster terms distributed.
  This skeleton is what AI engines and snippet algorithms parse.
- **Intro:** answer the core question in the **first 2-3 sentences** (the inverted pyramid),
  then earn the depth. Don't bury the lede behind a warm-up.
- **Internal links:** 2-5 contextual links to the brand's own money/service pages and related
  posts, with descriptive anchor text. List concrete targets in the brief.
- **External citations:** link 1-3 authoritative sources (stats, standards, .gov/.edu/industry).
  Trust signals matter for both Google and AI engines.
- **Media:** at least one hero image with descriptive, keyword-aware alt text (the Magnific asset).
- **Readability:** short paragraphs, scannable, active voice, no fluff. Honor the brand voice.

## Step 4: AI-Search optimization (AEO / GEO), the differentiator

For each piece, engineer it to be *quoted by an AI engine*:

1. **Answer the question up top, cleanly.** Write a **40-60 word self-contained answer block**
   immediately under the H1 (or under the relevant H2) that fully answers the target question
   without needing the rest of the page. This is the passage engines extract.
2. **One question per section.** Shape H2s as the real questions people ask (mine People-Also-Ask
   and "related searches"). Each section answers its heading in the first sentence, then expands.
3. **Assert entities and facts explicitly.** Name the brand, products, places, people, dates,
   numbers, and definitions in plain declarative sentences. Engines extract facts, not vibes.
   "Atlas Shippers International ships balikbayan boxes from California to the Philippines in
   X-Y weeks" is citable; "we get your stuff there fast" is not.
4. **Be the most complete, current source.** Generative engines favor pages that cover the
   topic comprehensively and look freshly updated. Include a published/updated date.
5. **Structure for machines:** bulleted lists, numbered steps, comparison tables, and a real
   **FAQ section** (each Q an H3, each A 1-3 sentences). Lists and tables get pulled verbatim.
6. **Add schema (structured data).** Recommend the right type per piece and put a ready-to-paste
   note in the brief: `Article`/`BlogPosting` for posts, `FAQPage` for the FAQ block, `HowTo` for
   step content, `LocalBusiness`/`Service`/`Product` for landing pages, `BreadcrumbList` always.
7. **E-E-A-T signals:** show Experience, Expertise, Authoritativeness, Trust, author/brand
   credentials, first-hand specifics, real data, citations, and accurate, current facts. AI
   engines weight source trust heavily when deciding whom to cite.
8. **Quotable stats & definitions:** include at least one original or well-sourced statistic and
   one crisp definition per piece. These are citation magnets.

## Step 5: Quality bar (the writing itself)

- **Match the brand voice** (see `references/brand-voice-extraction.md`). Tone, vocabulary, and
  reading level come from the brand's own footprint, not a generic blog voice.
- **Punchy, 800-1000 words by default.** Tight and scannable: short sentences, short paragraphs,
  strong verbs, no throat-clearing. Cover the cluster, then stop. Reserve 1500-2500 pillar length for
  when the brief explicitly asks for it. Tight beats long, and never pad to hit a count.
- **Original angle.** Don't rewrite page one of Google. Add the brand's specific experience,
  local knowledge, data, or point of view that the current SERP lacks.
- **Accurate & verifiable.** Never invent stats, prices, dates, or claims. For regulated claims
  (automotive pricing/lease/finance, legal, medical, financial), flag for sign-off and use only
  approved numbers: never fabricate. The brand's reputation and AI-trust both depend on this.
- **No fluff, no filler, no clickbait that the body doesn't pay off.** No em dashes (brand rule).

## Step 6: Measurement note (put in the brief, not the body)

Tell the client what to watch per piece: target keyword + rank tracking, impressions/clicks in
Search Console, and presence in AI answers (spot-check the target question in ChatGPT/Perplexity/
AI Overviews after indexing). The SEMRUSH project's Position Tracking can monitor the keyword set.

## The one-line standard

Every piece must be the **clearest, most complete, most trustworthy answer** to a real question
the brand's customer is asking, written in the brand's own voice, structured so both Google and
an AI engine can lift the answer straight off the page.
