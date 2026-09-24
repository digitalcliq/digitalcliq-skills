# Magnific for Blog Imagery (for /blog-content)

Generates the **hero image** (and optional short hero video) per piece, saved to the vault, linked
in the workbook, and embedded in the Word doc. Full Magnific mechanics (models, image→video flow,
generate→vault→workbook pipeline) and the **mandatory** brand-lock + verification gate are the social
skill's canonical docs: both apply in full, read them there, don't duplicate (paths from vault root):
- `.claude/skills/social-media-manager/references/magnific-cheatsheet.md`
- `.claude/skills/social-media-manager/references/generation-brand-lock.md`

Below are only the blog-specific deltas.

## Blog-specific deltas

- **Aspect ratio:** blog/landing hero = **16:9** (or 1.91:1 for OG/social share). Inline supporting
  images 4:3 or 1:1. Not the 9:16 vertical the social skill defaults to.
- **Default scope:** one verified **hero image per piece** (3 heroes for the standard 3-piece batch).
  Generate a short 16:9 hero **video** only when `--generate hero+video` or the piece clearly warrants
  motion (e.g. a landing-page header). Keep credit use low; `simulate_cost` before any batch.
- **Model choice for blogs:**
  - Photoreal lifestyle/product/location hero → **Nano Banana Pro** (`imagen-nano-banana-2`), with a
    brand-safe reference photo when fidelity to a real product/place/vehicle matters.
  - Header graphic with **readable on-image text** (stat, title card, concept diagram) → **gpt-2**.
  - Fast concept draft before a final → **Recraft V4.1** (`recraft-v4-1`).
- **Alt text is part of the asset.** Every generated image gets descriptive, keyword-aware **alt text**
  written into the piece's SEO brief (accessibility + image SEO). The Magnific prompt is not the alt text.
- **On-voice, on-brand:** the image must match the brand's visual identity and the article's angle, and
  pass the same verification gate: correct brand, **no competitor brand/logo/product anywhere**, clean,
  realistic, on-voice. For DigitalCLIQ's own deliverable chrome use the brand palette; for the client's
  hero imagery match the *client's* visual identity.

## Storage

Blog assets save under the client's project folder:
`Projects/<CODE>/blog-assets/<YYYY-MM>/<asset_id>-<slug>.<ext>` (+ `_thumb.png`).
For a brand-new prospect with no project code yet, use a short slug folder
`Projects/<slug>/blog-assets/<YYYY-MM>/`. Never the vault root, Desktop, or `tmp/` as a final home.
