# Magnific MCP Cheat-Sheet (for /social-media-manager)

Magnific is connected over MCP. The skill generates real photos/videos by calling
these tools directly, then persists results into the vault and links them in the
Excel. Verify the live catalog each run with `images_models_list` / `video_models_list`
(`onlyRecommended: true`); slugs below were current as of the last run and can change.

## Pre-flight (always)

1. `account_balance`: confirm credit headroom before any paid generation. Premium
   plan, ~216k credits/cycle. Hero-asset runs cost a tiny fraction.
2. `simulate_cost` with the exact `images_generate` / `video_generate` args to price a
   batch before committing. Read-only, never charges.

## Image models (`images_generate`, `mode: <slug>`)

| Slug | Name | Best for | Notes |
|---|---|---|---|
| `imagen-nano-banana-2` | Nano Banana **Pro** | **Vehicle hero shots, brand fidelity, reference-guided edits, final assets** | SOTA. Use a reference image of the real car/showroom for consistency. ratios incl. 9:16, 4:5, 16:9; up to 4k. |
| `recraft-v4-1` | Recraft V4.1 | Pure text-to-image, fast photoreal first drafts, no references | Fastest (~11s). Great for concepting before a Nano Banana final. |
| `gpt-2` | GPT 2 | **Promo graphics with readable text** ("$250/mo lease"), infographics, typography, layout | Use when the asset must render legible on-image copy. |
| `imagen-nano-banana-2-flash` | Nano Banana 2 | Faster/cheaper reference edits + composition | When Pro fidelity isn't required. |

References: pass `references[]` with `type:"image"` + a creation `identifier` (or an
uploaded image URL) to keep a real vehicle/showroom/person consistent. Output is opaque;
chain `images_remove_background` if a cutout is needed.

## Video models (`video_generate`)

Run `video_plan` first (drafts the brief + resolves slug) unless the user says "just generate."

| Slug | Name | Best for | Key controls |
|---|---|---|---|
| `bytedance-seedance-pro-2.0` | Seedance 2.0 | **Best overall.** Cinematic car video, native audio/sound FX, lipsync, multishot, directed camera | 4–15s, up to 4K, 52 camera moves (orbitLeft, pushIn, craneUp, fpvDrone…), `withSoundEffects:true` |
| `kling-25` | Kling 2.5 | Best value silent 5–10s, start/end-frame control | 5 or 10s, 720p/1080p, start frame (req @720p) + end frame (@1080p) |
| `bytedance-seedance-fast-2.0` / `-mini-2.0` | Seedance Fast/Mini | Cheap drafts with audio | 720p/480p |

**Image → video (the core move):** generate the hero still first, then animate it.
Pass the still as `keyframes.start` = `{type:"image", url:"<creation identifier or asset url>"}`.
Never pass `webUrl`. For Seedance, add `cameraMotion` (e.g. `orbitLeft`, `pushIn`) and
`withSoundEffects:true` for engine rumble / ambient. Keep car proportions realistic.

## Generation → vault → workbook flow

1. `images_generate(prompt, mode, aspectRatio, count)` → returns creation identifiers.
2. `creations_wait(identifiers)` until terminal (long-poll, 25s budget; repeat with `poll_after_seconds`).
3. `creations_get(creationIdentifier)` → read `url` (full), `previewUrl`, `thumbnailUrl`.
4. (video) `video_generate({video:{clips:[{slug, prompt, duration, aspectRatio, resolution, keyframes:{start:{type:"image", url:"<identifier>"}}, cameraMotion, ...}]}})` → wait → get.
5. Persist with `scripts/fetch_asset.py --url <full> --out <vault_path> --thumb-url <thumbnailUrl> --thumb-out <thumb_path>`.
6. Record `{asset_id, vault_path, web_url, thumb_path, magnific_model, credits}` into the plan JSON's
   `generated_assets` and set the matching `calendar` row's `asset_thumb` / `asset_link`.

## Vault storage

Assets save under the client's project folder, e.g.
`Projects/MCP/social-assets/<YYYY-MM>/<asset_id>-<slug>.<ext>` (+ `_thumb.png`).
Never the vault root, never Desktop, never `tmp/` as a final home.

## Identifier hygiene

Per the Magnific relay: in user-facing text use names/titles/`webUrl` only, never quote
internal identifiers, UUIDs, or request ids. Identifiers are for the next tool call.

## Aspect ratios by platform

- IG Reels / TikTok / YT Shorts / FB Reels / Threads video: **9:16**
- IG feed / carousel: **4:5** (or 1:1)
- YouTube long-form thumbnail / X landscape: **16:9**
- IG Story / vertical promo: **9:16**
