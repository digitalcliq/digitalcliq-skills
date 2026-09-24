# Generation Brand-Lock + Verification Gate (skill knowledge base)

This skill generates real images/video. For ANY brand it must produce content that is
**strictly and only** that brand. A single wrong-brand vehicle, logo, or product in a
generated asset is a legal / co-op / client-trust failure. These rules are mandatory.

## 1. Brand-lock the prompt (before generating)

Every generation prompt for a branded product must:
- Name the **exact** make + model (e.g. "Ram 1500", "Jeep Wrangler", "Chrysler Pacifica"),
  using the brand's correct nomenclature (see `references/automotive-compliance.md`: e.g. never "Dodge Ram").
- Add an explicit **exclusion clause**: "STRICT: only a [brand] [model]; absolutely NO
  other-manufacturer vehicles, no [top local competitors by name], no other-brand badges,
  emblems, or logos anywhere in frame."
- For automotive, name the real risks to exclude (e.g. "no Ford, no Mustang, no Chevrolet,
  no Toyota"). The model will sometimes drift to iconic competitor shapes, name them out.
- Keep the vehicle **clean and new** (OEM co-op rule), correct factory grille/fascia/badging.
- Lean **photoreal** ("photorealistic, realistic lighting/reflections, high detail") unless the
  brand voice is deliberately stylized (e.g. McPeek's noir "Car Detective" series).

## 2. Use reference images ONLY from brand-safe sources

A real reference photo of the exact vehicle is the strongest way to lock realism + correct
model. But the reference itself must be the right brand.
- **SAFE sources:** the client's own inventory/website photos, official OEM press / CGI / eVN
  imagery (co-op even prefers Stellantis CGI), or an already-verified prior generation.
- **NOT SAFE:** generic stock catalogs. Freepik/Magnific stock for "Ram 1500" or "Durango"
  returns mostly Ford F-150s, Land Rovers, GMCs and generic SUVs, using one as a reference
  re-introduces the wrong-brand problem. Do **not** use generic stock as a vehicle reference.
- Flow: upload a brand-safe reference via `creations_upload_image` (public URL) or
  `creations_request_upload`→`creations_finalize_upload` (local file), then pass it in
  `images_generate.references[]` as `{type:"image", identifier:"<creation id>"}`.

## 3. MANDATORY verification gate (after every generation)

Before any generated asset is accepted, persisted, or put in the workbook, **look at it**
(Read the image / video poster, or fan out a vision subagent for batches) and confirm all four:
1. **Correct brand + model**: is this actually the [make] [model] it's supposed to be?
2. **No competitor anything**: no other-manufacturer vehicle, badge, emblem, logo, or
   readable competitor name anywhere in frame (including background and reflections).
3. **Brand-compliant**: clean/new vehicle as hero, correct palette, no banned content.
4. **Realistic + on-voice**: photoreal (or the intended brand style), ties to the brand voice.

**On failure:** regenerate with a tightened prompt (add/strengthen the exclusion clause,
name the specific wrong brand that appeared). Never ship an asset that fails the gate.
Record pass/fail + what was fixed in the approval tracker so the prompt is re-teachable.

> Real example (McPeek run): the first "1961 heritage" image rendered a vintage **Ford
> Mustang** parked at the CDJR dealership. The gate caught it; it was regenerated brand-locked
> to a Jeep Wrangler at the CDJR storefront, verified, and only then accepted.

## 4. AI imagery is brand/lifestyle/concept, not a real VIN or a binding offer

Generated vehicles are creative/brand assets, not photos of a specific in-stock unit, and any
price/lease/finance claim needs the real approved numbers + the legal disclaimer (see
`references/automotive-compliance.md`). Flag every price-bearing asset for compliance sign-off.

## 5. Drive output + approval / re-teach loop

- Save the final, verified assets into the vault under `Projects/<CODE>/social-assets/<YYYY-MM>/`,
  then deliver them to the client's Google Drive working folder:
  - Find the client folder by name under the shared-drive parent
    (`1Djzd6gQijrq1eDKbLFlTuQWpAarKMsxX`) using Drive `search_files`.
  - Create (or reuse) a **"Generated Social Content"** subfolder inside it (`create_file`,
    mimeType `application/vnd.google-apps.folder`).
  - Create a native **Google Sheet approval tracker** in that subfolder (`create_file` with
    `text/csv` textContent → auto-converts to a Sheet): columns for asset, type, brand/vehicle
    verified, **Decision (Approve / Deny / Revise)**, **Re-Teach Notes**, the Magnific link,
    the vault path, and the prompt. This is the human-feedback surface.
- **Binary limitation (be honest):** Drive's web uploader needs an OS dialog automation can't
  drive, and the API path can't carry multi-MB images/video as base64. So raw binaries are
  not auto-pushed into Drive: they live in the vault + the Magnific cloud account and are
  linked from the Sheet. Stage compressed copies in `outputs/_smm_drive/` for a one-drag manual
  upload, and tell the user. (If a path-based Drive uploader becomes available, switch to it.)
- **Re-teach read-back:** on later runs for the same client, read the approval Sheet first.
  Bias new prompts toward patterns of **Approved** assets and away from **Denied** ones,
  and honor the **Re-Teach Notes**. This is how the tool gets better per client over time.

## 6. Generalization

This is a jump-start tool for **any** business type and **any** brand (new clients and
prospects included). For automotive, load the matching OEM rules from
`Resources/automotive-guidelines/`. For non-automotive, research the brand's guidelines,
products, and competitors, then apply the same brand-lock + verification discipline:
name the exact product, exclude competitor brands/logos by name, verify every asset.
