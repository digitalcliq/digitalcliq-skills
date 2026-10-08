---
type: skill-notes
date: 2026-09-21
status: active
tags: [skill, score-leads, excel, design-system, gm-deliverable]
---

Change log and design notes for the [[score-leads]] skill (CRM lead-source scorecard, 1 to 10 relative score plus NADA benchmark layer, DigitalCLIQ-branded Excel). Catalog entry: [[Skills/README]].

> [!warning] Runtime is the only copy
> `score_leads.py`, `ingest.py`, `reference/` and `references/` live only in the anthropic-skills plugin folder (`skills/score-leads/`). The `.claude/skills/score-leads/` path quoted in SKILL.md's fast-path command does not exist, and there is no `~/Desktop/Skills/score-leads` source. A plugin re-sync reverts every fix below; check `grep -c PageSetupProperties score_leads.py` (expect 5) before a run.

## 2026-09-21: print fit-to-page and wrapped-row heights fixed

First run on a [[Tekion]] Lead Source Report for [[McPeek Chrysler Dodge RAM of Anaheim|MCP]]. Ingest auto-detected the format (160 raw rows, rolled up to 21 canonical vendors) and post-flight passed first try. The render gate did not.

- **Every tab printed across two pages sideways.** All four sheet builders set `fitToWidth = 1` and then `sheet_properties.pageSetUpPr = None`, which is the flag that activates fit-to-width. Replaced with `PageSetupProperties(fitToPage=True)` (import added inside the openpyxl try block). 18 pages became 9.
- **Last wrapped line clipped in long cells** on the NADA Benchmarks and Methodology tabs. `_autofit_wrapped_rows` estimated Roboto Slab as if it were Calibri: width factor 0.95 to 0.72, line box 1.35 to 1.65 times the point size, padding 4 to 8. Six render passes to two consecutive clean reads (11 pages final).
- Backup of the pre-fix generator sits beside it as `score_leads.py.bak-2026-09-21`.

Observed on this export: Tekion's CSV carries no date range, so the period label was set to `Tekion export 2026-09-21`; Drew supplies the real period when re-running. A corrupted byte in one source name (`Brand Site � Share with Dealer`) parses fine under `utf-8-sig`.

## 2026-09-21: Tekion roll-up put the store's own website in "Other / Ungrouped"

The fresh-eyes reviewer caught it on the same McPeek run: Tekion labels the plain dealer-site lead source by domain (`McPeekCDJR.com`, group `McPeekCDJR.com`), and no roll-up rule matched it, so 23 leads and 5 sales landed in the fallback bucket and the Summary ranked "Other / Ungrouped" second. Fixed in `reference/canonical_vendors.json`: Dealer Website now also matches `mcpeekcdjr`, `mcpeeks.com`, `sterlingbmw`, `newcenturybmw`, `nissanofirvine`, `dealer site`; a new OEM / Brand Site rule (`e-shop`, `eshop`, `brand site`) sits ahead of the Dealer Website catch-all so Stellantis eShop and brand-site forms grade against the OEM benchmark. Dealer Website went from 41 / 6 to 59 / 11; Other / Ungrouped fell to 4 / 0. Any new client domain needs its own token in that list before the first run.

Other generator changes from the same review, all in `score_leads.py`: Tekion runs get a footnote under the Scores table explaining that Contact % is Tekion's Internet/OEM Leads Engaged metric and reads 0% for walk-in, service and referral rows because it is not measured; manual page breaks before "How to Read This Scorecard", "New vs Used Car Adjustment", "Tier Definitions" and the seasonal indices; the Summary tier legend drops its N/A row when nothing is N/A-tiered; the self-score banner reads "AT expectation (-0.2 pts)" instead of "AT by 0.2 pts"; Scores tab footer line; full borders on the merged Top Sources cell. `nada_benchmarks.json`: "BMW Financial Services lists" generalized to OEM financial-services lists so a CDJR store never sees another brand named. Another Code session was editing the same generator in parallel (unattributed-sale bucket, jargon rewrites); both sets of edits coexist, patch with exact-string asserts.

Later the same evening, reviewer passes 3 and 4 added: the full OEM / Brand Site rule (with `e-shop`, `eshop`, `brand site`, `oem website`) now sits ahead of Dealer Website so `OEM Website (Dodge.com, Jeep.com, etc)` no longer matches the generic `website` token; `lease maturity` merges into Email / Campaign; the close-rate benchmark table repeats its header after a manual break at the fifth row; the credit-application methodology text now describes what the roll-up actually does; the NADA self-score sentence reads "Within X points of expectation (At band)"; Top Sources pluralizes "1 sale"; source notes are Roboto Slab. Still open as minor polish: the seasonal-index grid inherits the benchmark column widths (MAY and OCT render wide), the Yardsticks header cell B is not merged across B:C, Methodology column D is narrow, and Top Sources shows a low-volume row without a marker. Runtime copied to `~/Desktop/Skills/skills/score-leads/` (previous files in `.bak-2026-09-21/`).

## 2026-10-08: Momentum Executive Snapshot adapter (all-channel scorecard for Sterling BMW)

Drew dropped `sterlingbmwleadslastmonth.xls` for [[Sterling BMW]] (September 2026). It was not the Lead Source Report the 2026-09-21 adapter reads; it was Momentum's **Executive Snapshot**: three printed pages, one block per prospect channel (Internet, Inbound, Showroom, Showroom UST, Lease Retention, OEM, Outbound, Service, Parts, Appraisal, Financial), each with Created Prospects, Appointments Scheduled, Shows, DMS Sold to Created Prospects, and a block-level Total Sales. The fast path refused it ("Unrecognized CRM format", 33 blank headers). Added `_parse_momentum_snapshot` to `ingest.py` (format id `momentum_snap`) rather than hand-normalizing.

Decisions baked into the adapter and scorer, all explained in notes on the Summary and Scores tabs:

- **Sales = the block's Total Sales**, not the same-month cohort figure. The report's own Totals row sums Total Sales (145), so the parse reconciles against it (leads minus UST 1,263, appointments 211, shows 116, DMS Sold 145; the run aborts on a mismatch). The cohort view would have shown Lease Retention at 2 sales instead of 14. Cohort sales (109) are listed per channel in a note.
- **Showroom reports appointments and shows as "N / A"** (walk-ins do not set appointments). New per-row `funnel_na` flag: `_row_weights` drops those two factors and renormalizes (Sale Rate 73%, Volume 27% once contact is also out), the four cells read `n/a`, and `funnel_na_note` explains it. Without this Showroom scored zero on 39% of its weight.
- **Benchmark classification for channel names**: `inbound` grades as phone; `retention` and `outbound` as data lists (store-initiated lease-maturity and call lists, so N/A and out of the store self-score); `parts` as owned equity. Appraisal and Financial fall to the internet default and are low volume anyway.
- **Subtitle** is now a `report_label` argument (`All-Channel Lead Scorecard` for this format, `E-Commerce Lead Source Scorecard` otherwise); the old string was hardcoded in two places.
- `build_summary_tab` now takes `extra_notes`, so format notes appear on the Summary tab as well as the Scores tab.

Run result: 11 channels, store close 10.8% on 1,190 acquisition leads vs 15.8% expected for the mix (Below by 4.9 pts), tiers B4 C4 D3. Backups beside the generator as `*.bak-2026-10-08`. Still runtime-only (see the warning above); `~/Desktop/digitalcliq-skills/sync.sh` after the run so the GitHub backup carries the adapter.
