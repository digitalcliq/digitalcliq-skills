---
type: skill-notes
date: 2026-09-04
project: MCP
status: active
tags: [skill, mcpeeks-site-watch, excel, design-system, gm-deliverable]
---

Design notes and change log for the [[mcpeeks-site-watch]] skill (twice-weekly [[mcpeeks.com]] compliance, accuracy and health watch for [[McPeek Chrysler Dodge RAM of Anaheim|McPeek's CDJR of Anaheim]]). Runtime package lives in the anthropic-skills plugin folder (`skills/mcpeeks-site-watch/`); the scheduled Mon/Fri stub is `~/.claude/scheduled-tasks/mcpeeks-site-watch/SKILL.md`. Catalog entry: [[Skills/README]].

## 2026-09-04: PDF replaced by a GM-facing Excel workbook

[[Drew Moon]] asked for the deliverable to become an Excel spreadsheet that a dealership General Manager can follow, with DigitalCLIQ branding. The prior PDF was a 20-page severity-grouped VIN list (see `Projects/MCP/deliverables/McPeeks_Site_Watch_2026-09-02.pdf`); readable by Drew, not by [[Stewart Benjamin]].

> [!info] What changed in the package
> - `scripts/check_catalog.py` (new): GM-language table for all 21 checks: plain name, what we check, why it matters to the store, who fixes it (Pixel Motion, ComplyAuto + GTM admin, inventory manager, desking, domains/IT, phone admin), and the recommended fix. Every wording change for the workbook happens here.
> - `scripts/report.py` (rewritten): merges findings + browser pass + sitehealth, diffs against the prior snapshot, and now explains every change: NEW split into "new arrival" vs "new issue on an already-listed vehicle"; RESOLVED split into "fixed on the page" vs "vehicle no longer listed (sold)". Emits `report.json` (workbook input) and `run_summary.md` (the only file the model reads). Snapshot now also stores phones and VINs.
> - `scripts/build_workbook.py` (new): openpyxl workbook to the Design-System Excel spec (Digital Blue masthead + white logo every sheet, Dosis/Roboto Slab, palette-only status coding with text labels, landscape fit-to-width print setup, print titles, footer). Tabs: Summary, Fix List, Scorecard, Legal & Pricing, Inventory Accuracy, Site Health, Phone Checklist, What Changed. Writes the `.facts.json` manifest for the Rule 22 QA gate automatically. Refuses to build without the model-written `exec_summary.txt`.
> - `scripts/checks.py`: C12/C21 finding text reworded (the word the post-flight validator treats as unfilled template text is gone).
> - SKILL.md: audience block (GM + owner, Rule 23), Phase 3 rewritten around report.py > exec summary > build_workbook.py > post_flight > render gate > QA gate > Drive `.xlsx` > `Projects/MCP/deliverables/`. Vault paths updated from the frozen nested vault to HQ.

Render gate on a reconstructed 2026-09-02 dataset: pass 1 caught four defects (Summary spilling to a second mostly-blank page, footer colliding with the last table row, ampersand swallowed by Excel header codes, a 13-page "What Changed" tab listing 423 sold-vehicle resolutions one per row); all fixed in the generator; pass 2 clean across 17 pages. post_flight: 4/4 pass, 8 sheets, logo embedded.

Known gaps carried forward (unchanged today): Lighthouse needs Node on the reporting Mac; C12 stock-graphic detection should key on the 16,586-byte hero image, not URL patterns; `domains.txt` holds 6 of ~50 domains; `fee_disclaimer_template.txt` and `lease_programs.json` still need Drew's input. Browser-surface preference (Claude Browser first) not yet applied to this skill's Phase 2 wording.

## 2026-09-14: CNCDA CARS Act guidance folded in (C22 to C24, C01 to C07 rewording)

[[Drew Moon]] supplied the [[CNCDA]] CARS Act Compliance Guide v1.2 (2026-08-07) and Webinar FAQ (2026-08-31), now filed in `Resources/automotive-guidelines/` and digested in [[Resources/automotive-guidelines/cncda-cars-act-guidance|the CNCDA guidance note]].

> [!info] What changed in the package
> - `scripts/check_catalog.py`: C01 (rebates) now states the CARS Act no-rebate-deduction rule and CNCDA's Total Price / Factory Rebate / Net Cost pattern; C02 (doc fee) explains the FTC-versus-California tension and CNCDA's dual presentation as the fix; C03 adds the MSRP-no-more-prominent rule; C04 now checks the Veh. Code 11713.1(c)(2) sentence verbatim; C05 adds the CARS total-price and total-of-payments duties; C06 cites Civ. Code 1784.41(a)(1) and treats price-gating CTAs as Call for Price; C07 explains the 11713.1(e) ceiling rule. Three new checks: **C22** installed equipment excluded from the price (pay-or-remove wording), **C23** repealed two-day cancellation option or $40,000 wording, **C24** MSRP shown as the price or "MSRP is not the selling price".
> - `scripts/crawl.py`: three new per-vehicle flags (`installed_excluded_language`, `repealed_option_language`, `msrp_not_price_language`).
> - `scripts/checks.py`: C22 to C24 emitted; C04 falls back to a verbatim check of the statutory sentence when `fee_disclaimer_template.txt` is still unfilled.
> - SKILL.md: 24 checks. Workbook and report scripts pick the new IDs up from the catalog without changes (verified by import and a two-vehicle smoke run).

Runtime and the `~/Desktop/Skills/skills/mcpeeks-site-watch` source were synced from the runtime copy (the source had been behind since the 2026-09-04 workbook build). Still open from 2026-09-04: `fee_disclaimer_template.txt` and `lease_programs.json` need Drew's input; until the template is filled, C04 enforces the verbatim statutory sentence.
