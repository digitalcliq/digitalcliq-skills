---
name: inventory-pulse
description: DigitalCLIQ Inventory Pulse. Twice-monthly (5th + 20th) competitive intelligence deliverable for a client dealership vs its hardcoded competitive set. Crawls lease specials, finance specials, and new inventory (VIN level) for the client + 3 competitors, snapshots everything date-keyed, diffs vs the prior anchor run (first-seen, payment deltas, delisted VINs, days-on-market), and ships a DigitalCLIQ-branded Google Sheet to the client's folder in the DigitalCLIQ Shared Drive. Clients: SBMW (Sterling BMW), MCP (McPeek's CDJR), NOI (Nissan of Irvine). Use when Drew says /inventory-pulse, "inventory pulse", "run the pulse for [client]", or the scheduled 5th/20th task fires.
argument-hint: <client code(s) or "all"> [YYYY-MM-DD] -- e.g. "mcp", "sbmw noi", "all"
---

> [!important] Pre-flight: load the facts ledger FIRST
> Read `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Context/vault-facts.md` and obey it (output paths, logo rules, client/competitor names). Deliverables stage in vault `outputs/`, then file to `Projects/{CODE}/deliverables/`.

# DigitalCLIQ Inventory Pulse

Reverse-engineered from the Constellation "On-Brand Inventory Report" (teardown in `Skills/inventory-pulse/`), rebuilt as a DigitalCLIQ service. One run = one client market: crawl the client + 3 competitors, extract offers + inventory, diff against history, render the branded workbook, convert to a Google Sheet in the client's Drive folder.

**Architecture (rebuilt 2026-08-15): the main loop ORCHESTRATES, cheap agents CRAWL, scripts do everything deterministic.** The expensive model (Fable) never crawls, never fights a browser, never reads page HTML or inventory JSON. Per-dealer subagents on cheaper models do the crawling and write fragment files; scripts merge, diff, and render; the main loop reads only one-line script summaries and ≤15-line agent summaries, writes the executive layer, and runs the final QA gate. Target: < 25k output tokens in the main loop per client.

## Paths

- `SKILL=/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/inventory-pulse`
- `VAULT=/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ`
- `DATA=<scratchpad>/pulse-run/{CODE}/` per-run working dir (disposable)
- `STATE=$VAULT/Projects/{CODE}/inventory-pulse-state/` persistent: `registry.json` + `snapshots/extract_YYYY-MM-DD.json` (date-keyed, never overwrite a different date's snapshot)
- Config: `$SKILL/config/clients.json` (clients, competitors, models, per-dealer `fetch` mode + platform cache; update as runs learn things)
- Drive (mounted): `~/Library/CloudStorage/GoogleDrive-drewmoon@digitalcliq.com/Shared drives/DigitalCLIQ Shared Drive/Clients/{drive_client_folder}/DigitalCLIQ Inventory Pulse/`

## Environment facts (verified 2026-08-15, re-verify only if something contradicts them)

- `curl` is BLOCKED in the Bash sandbox; python urllib works. No `timeout` CLI; scripts use socket/subprocess timeouts. Never write ad-hoc probe code: `fetch_pages.py --probe` exists.
- Only 3 of 12 dealer sites accept server fetch (mcpeeks.com, nissanofirvine.com, nissanofcostamesa.com). The other 9 are WAF'd (403 on everything incl. sitemaps); nissanorange.com additionally rejects python's TLS. Their `fetch` field in clients.json says `browser`.
- WAF'd sites let a real browser through, and **same-origin in-page `fetch()` returns 200** where server-side fetch 403s. That is the browser strategy: one tab, in-page JS does sitemap + VDP fetching + parsing (`references/browser-extract.js`), only compact rows come back.
- Headless Chrome network fetch HANGS on this machine (even example.com, 2026-08-15). Do not use it as a fetch engine until re-verified.
- Browser surfaces for agents, in order: Chrome MCP against Drew's real Chrome (if Chrome isn't running: `open -a "Google Chrome"`, wait ~8s — allowed on unattended runs), then the Claude Browser pane. 2 consecutive tool timeouts on a surface = abandon it. Only ONE agent may drive browser surfaces at a time.

## Step 1: Parse arguments

Tokens are client codes (case-insensitive): `sbmw`, `mcp` (aliases: mcpeek, mcpeeks), `noi` (alias: nissan), `all` = all three. Optional `YYYY-MM-DD` overrides run date (default today). Unknown token: list valid codes and stop. Multiple clients run sequentially. Run type is derived by the scripts: day <= 12 = anchor, day > 12 = pulse; a late-fired scheduled run is fine, snapshots are date-keyed.

**Model year rule (never hardcode):** track configured models at whatever model years appear in NEW inventory; during changeover keep both years. Never filter to a literal year.

**Sampling rule (Drew, 2026-08-15): inventory is a SAMPLE of 3-4 VDPs per tracked model per dealer** (~12-16 pages/dealer), never an exhaustive crawl. Prefer lowest-priced units where the platform can sort by price. Because of sampling, delist detection runs on a **recheck list**: `scripts/recheck_urls.py --state "$STATE" --dealer "{Name}"` prints the VDPs of already-tracked VINs (cap 40); agents fetch those too, and a 404 there means delisted, not a crawl error. The Min Price Matrix therefore reads "lowest advertised among sampled units"; if a client ever needs a census, raise the cap deliberately.

## Step 2: Fan out dealer agents (per client)

For the client + 3 competitors, spawn one subagent per **server**-mode dealer and one subagent covering ALL **browser**-mode dealers of that client (sequentially inside that agent, because there is one browser). Models: `haiku` for server dealers (mechanical script-driving), `sonnet` for the browser agent (banner reading + platform judgment). Never Fable.

Each agent prompt contains, verbatim: the dealer block(s) from `config/clients.json` (name, url, platform, notes, fetch mode, role), the client's `models` array, the paths `$SKILL`, `$DATA`, `$STATE` (for recheck_urls.py), and the instruction *"Read `$SKILL/references/dealer-agent-brief.md` and follow it exactly. Write `$DATA/{dealer-slug}/fragment.json` (slug = lowercase name, non-alnum → `-`). Reply with only the ≤15-line summary the brief specifies."*

Run server agents in parallel (background), the browser agent alongside them (it is the long pole, ~4-8 min/dealer). Wait for all. Read only their summaries. An agent that died or wrote no fragment: note it, do NOT re-crawl in the main loop; one respawn attempt max, then the dealer is `failed`.

> [!warning] Crawl politeness is a hard rule (a 10-worker crawl coincided with mcpeeks.com going down 2026-07-26). The scripts and JS enforce pacing/breakers; agents are instructed to stop on breaker trips. Never override.

## Step 3: Merge + snapshot + diff + analytics

```bash
python3 "$SKILL/scripts/merge_extract.py" --config "$SKILL/config/clients.json" --client {CODE} \
  --date {date} --data "$DATA" --out "$DATA/extract_{CODE}_{date}.json"
python3 "$SKILL/scripts/snapshot_diff.py" --extract "$DATA/extract_{CODE}_{date}.json" \
  --state "$STATE" --out "$DATA/analysis_{CODE}_{date}.json"
```

merge_extract owns model canonicalization, numeric coercion, VIN dedup, error rollup (exit 1 = the CLIENT dealer failed: still ship, but lead the final message with that). snapshot_diff owns date-keyed snapshots, first-seen registry, deltas vs the correct compare run, delisted VINs (failed crawls never fake delistings), DOM floors, 120-day movement, min-price matrix, effective-cost lease ranking ((DAS + pmt × (term−1)) / term), Summary bullets, and the baseline "data logging began" note. Read only their printed summaries.

## Step 4: Workbook + validation

```bash
python3 "$SKILL/scripts/build_workbook.py" "$DATA/analysis_{CODE}_{date}.json" "$VAULT/outputs"
python3 "$VAULT/.claude/skills/post_flight.py" "$VAULT/outputs/DigitalCLIQ_Inventory_Pulse_{CODE}_{date}.xlsx" --min-sheets 5
```

Tabs: Summary, Lease Offers, Finance Offers, Inventory Movement, Min Price Matrix, VIN Detail, Run Log. post_flight failure: fix the generator, regenerate once, else STOP and show Drew the validator output. Then the render gate + QA gate below.

## Step 5: Google Sheet in the client's Drive folder

1. Copy the validated xlsx to the mounted folder (create the subfolder if missing); poll `ls` until stable, then ~30s.
2. Convert via Chrome (the standing pipeline; Drive MCP cannot convert): find the uploaded xlsx (Drive MCP `search_files`), open its Drive URL in Chrome, File > Save as Google Sheets. Rename the Sheet `DigitalCLIQ Inventory Pulse - {Client display} - YYYY-MM-DD`.
3. Leave the xlsx beside the Sheet (confirm-before-delete rule). File a copy to `$VAULT/Projects/{CODE}/deliverables/`.

## Step 6: Final message to Drew

Per client: run type + compare label, top 3 Summary bullets, NEW/moved offers since last run, delistings, crawl status per dealer (call out anything not `ok` and which surface/mode got the data), **every error hit** (standing rule), QA line, Sheet link + filed paths. One screen.

Cache every discovery (working sitemap path, platform ID, SRP pattern, which surface worked) into `config/clients.json` notes so the next run skips discovery.

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

## Notes

- Rank shading is deliberately NOT green-to-red: Sky Blue = market low, Callout Tint = second, Card White = middle, Warm Grey = highest, rank/market-low always ALSO written as text.
- NCBMW is excluded on purpose (already gets this from Constellation). Never add without Drew.
- **Ship no matter what.** A failed dealer (even the client) never holds the deliverable: mark `failed` in Run Log, exclude from rank denominators (scripts already do), lead the final message with it. Never fight a surface past its time-box; a shipped report with a failed-dealer note beats a dead run.
- Unattended runs: never stall on a browser surface, never ask questions; make the reasonable choice and log it.

## Final QA Gate: deliverable-reviewer agent (MANDATORY, added 2026-08-13)

Runs AFTER the deliverable is generated and post_flight.py passes, BEFORE filing/presenting. post_flight.py is mechanical; this gate is the human-style read.

1. **Write a facts manifest** next to the deliverable in `outputs/`: a JSON list of every number, name, date, and claim that appears in the deliverable, each as `{"value": ..., "label": "where it appears", "source": "tool/file/URL it came from"}`. Build it from data already in context, never re-fetch anything just for the manifest. **Inventory Pulse: generate it with `python3 "$SKILL/scripts/build_manifest.py" <analysis.json> <manifest.json>`** — never hand-build it (a hand-built one missed fields on 2026-08-15 and produced false "unsourced figure" findings).
2. **Spawn the `deliverable-reviewer` agent** (fresh eyes, it did not write the report). Pass in the prompt: the absolute path(s) of the finished deliverable file(s), the manifest path, and any skill-specific checks from this SKILL.md. It renders every page, reads them all, cross-checks figures against the manifest, and reviews tone/copy.
3. **Auto-fix every finding** in the source generator or data (never by hand-editing the output), re-render, and re-run the agent once. Max 2 review passes. If CRITICAL or MAJOR findings remain after pass 2, the ship is BLOCKED: report the remaining findings to Drew verbatim instead of presenting the file as done.
4. The run summary MUST include a **QA line**: what the reviewer caught and what was fixed, or "QA: clean on first pass (N pages read, M figures verified)". Never silently skip the gate; if the agent could not run, say so explicitly in the delivery message.
5. **Inventory Pulse specific**: run this gate on the staging `.xlsx` BEFORE the Google Sheets conversion/upload, the xlsx is what render_check.py can read; never upload an unreviewed file to the client Drive folder.
