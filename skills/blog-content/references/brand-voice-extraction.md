# Brand Voice Extraction (for /blog-content)

The whole point of this skill is content that sounds like **the brand**, not like AI and not
like DigitalCLIQ's own voice. Before writing a word, build a short, reusable **voice profile**
by scanning the brand's real footprint, then write every piece to it. The profile ships in the
workbook's "Brand Voice" tab so the client sees exactly what was matched.

> Two voices, kept separate. The **content body** is in the *client's* voice. The **deliverable
> chrome** (cover, contact, the doc footer) is DigitalCLIQ-branded. Never bleed DigitalCLIQ's
> "direct, dry, technical" house voice into a client's piece unless that genuinely is their voice.

## Where to look (scan, don't guess)

Fan out research across the brand's actual surfaces and capture verbatim samples:
1. **Website**: homepage, About, service/product pages, any existing blog. The clearest voice
   signal. Note recurring phrases, taglines, how they describe themselves and the customer.
2. **Current social presence**: Instagram, Facebook, TikTok, LinkedIn, X. Caption tone, emoji
   use, formality, how they talk to followers. (Browser tools / WebSearch.)
3. **Reviews & citations**: Google/Yelp reviews and how the brand responds, press mentions,
   directory listings, third-party write-ups. Shows how customers describe them and the words
   that resonate.
4. **Existing collateral**: brochures, email, ads if available in the vault project folder.
5. **Vault project**: if the client is already a `Projects/<CODE>/` client, read the README and
   any brand notes first; the voice may already be documented.

## What to capture (the voice profile)

Distill into the `brand_voice` object the plan carries:
- **summary**: 2-3 sentences describing the voice in plain terms.
- **tone_attributes**: 4-6 adjectives (e.g. "warm, family-run, reassuring, proud, bilingual").
- **reading_level**: who they talk to and how (e.g. "8th-grade, plain-spoken, no jargon" vs
  "senior/technical").
- **do**: concrete habits to emulate (sentence length, POV, signature phrases, how they address
  the reader, formatting quirks, languages used).
- **dont**: words/tones to avoid (their bannedlist + obvious mismatches).
- **sample_phrases**: 3-6 real phrases pulled from their footprint (their words, quoted), so the
  writing can echo their actual language.
- **sources**: where the voice was read from (URLs / handles), for transparency.

## Matching the voice while writing

- **Mirror, don't impersonate.** Match cadence, vocabulary, formality, and POV. Reuse their real
  terminology for products/services (the words their customers actually search and recognize).
- **Hold the line on quality.** Voice-matching never excuses fluff, vague claims, or weak structure.
  The SEO/AEO discipline in `references/seo-ai-search-playbook.md` still applies fully.
- **Respect the brand's bannedlist and any compliance rules.** For automotive, OEM tone + ad-law
  rules can override brand whimsy (see the automotive note in the SKILL). Honor the global rule:
  **no em dashes**, ever.
- **Keep it human.** First-hand specifics, local detail, and real point of view are what make a
  piece sound like the brand and what make AI engines trust it. Generic = invisible.

## Edge cases

- **Thin footprint (new brand, almost no content):** infer voice from the industry + the owner's
  own words (site copy, any interview), and from the customer they serve. State in the profile
  that the voice is partly inferred, and lean conservative/professional until the client steers.
- **Inconsistent voice across channels:** pick the strongest, most on-brand surface as the anchor
  (usually the website) and note the inconsistency as something the content will help standardize.
- **Multilingual brand (e.g. Atlas serves a Filipino diaspora):** match the language mix they
  actually use; don't force English-only if their audience expects bilingual touches.
