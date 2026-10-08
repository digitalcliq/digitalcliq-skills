---
name: dealership-compliance-audit
description: Run a monthly dealership website compliance audit combining OEM brand guidelines + California advertising law + CCPA/CPRA privacy + ADA/Unruh accessibility + TCPA lead-form consent. Randomly spot-checks multiple vehicle detail pages (VDPs) each run. Produces a branded DigitalCLIQ Excel report with findings, severity scoring, re-verification proof, and month-over-month delta tracking. Supports BMW, Nissan, CDJR (Chrysler/Dodge/Jeep/Ram), Chevrolet, and Harley-Davidson (MAP enforcement).
argument-hint: <brand> <url> [--client "Client Name"]
allowed-tools: Read, Write, Glob, Grep, Bash(python3 *), Bash(/opt/homebrew/bin/*), Task, mcp__Claude_Browser__preview_start, mcp__Claude_Browser__tabs_context, mcp__Claude_Browser__tabs_create, mcp__Claude_Browser__tabs_close, mcp__Claude_Browser__tabs_select, mcp__Claude_Browser__navigate, mcp__Claude_Browser__javascript_tool, mcp__Claude_Browser__read_page, mcp__Claude_Browser__get_page_text, mcp__Claude_Browser__find, mcp__Claude_Browser__computer, mcp__Claude_Browser__browser_batch, mcp__Claude_Browser__read_console_messages, mcp__Claude_Browser__read_network_requests, mcp__claude-in-chrome__list_connected_browsers, mcp__claude-in-chrome__select_browser, mcp__claude-in-chrome__tabs_context_mcp, mcp__claude-in-chrome__tabs_create_mcp, mcp__claude-in-chrome__tabs_close_mcp, mcp__claude-in-chrome__navigate, mcp__claude-in-chrome__javascript_tool, mcp__claude-in-chrome__read_page, mcp__claude-in-chrome__get_page_text, mcp__claude-in-chrome__find
---

> [!important] Pre-flight: load the facts ledger FIRST
> Before doing anything else, read `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Context/vault-facts.md` and obey it. It is the source of truth for: output location (always the vault `outputs/` folder, never the Desktop or the input file's directory), the canonical working folder (the vault root, never an old/legacy folder), the DigitalCLIQ Master calendar, the canonical logo path, and correct client/competitor names (e.g. "BMW of Buena Park (AutoNation)" not "Shelly BMW"; LOGO Cargo is a hostile competitor, not an Atlas partner). Validate every output path and every client/competitor name against the ledger before writing. If a fact you need is missing from the ledger, do not guess: check the vault and flag it.

# Dealership Compliance Audit

You are a dealership website compliance auditor for DigitalCLIQ. When invoked, run a full compliance audit on the specified dealership website, checking OEM brand guidelines, California advertising law, and CCPA/CPRA privacy compliance.

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

**Skill-specific severity rule:** severity, confidence, and delta status in the Excel report are color-coded with palette treatments only (Tile Blue = critical/deep emphasis, Digital Blue = warning/emphasis, Warm Grey = advisory/weak, Sky Blue = resolved/strong). The explicit TEXT labels (CRITICAL / WARNING / ADVISORY, HIGH / MEDIUM / LOW, NEW / PERSISTING / RESOLVED) always carry the meaning, never rely on color alone.

**Masthead (retrofitted 2026-07-18):** every visible sheet in `scripts/generate_report.py` carries the rows 1-2 merged Digital Blue masthead per Design-System §4, white knockout logo anchored A1 (~0.35in, true aspect), sheet title in white Dosis 14 Bold, report date right side (`_add_masthead()`). Content, freeze panes, and autofilter ranges on every tab are offset below the masthead.

## How to Use

The first argument is the brand. The second argument is the dealership URL. Optional `--client` flag sets the client name for the report.

Examples:
- `/compliance-audit bmw https://www.sterlingbmw.com --client "Sterling BMW"`
- `/compliance-audit nissan https://www.nissanofirvine.com --client "Nissan of Irvine"`
- `/compliance-audit cdjr https://www.mcpeekcdjr.com --client "McPeek CDJR"`
- `/compliance-audit chevy https://www.covinahillschevy.com --client "Covina Hills Chevy"`
- `/compliance-audit harley https://www.example-hd-dealer.com --client "Example Harley-Davidson"`

Brand aliases:
- **bmw** → BMW AVP guidelines
- **nissan** → Nissan BAP/RMP guidelines
- **cdjr**, **stellantis**, **chrysler**, **dodge**, **jeep**, **ram** → Stellantis/CDJR guidelines
- **chevrolet**, **chevy** → Chevrolet/GM guidelines
- **harley**, **harley-davidson**, **hd** → Harley-Davidson Motorcycle MAP Policy

## Browser Surface Order (mandatory, retooled 2026-09-04)

<!-- browser-surface-block v1 · Claude Browser is the primary crawl surface; Chrome is a fallback only -->

Every live page visit in this skill runs on the **built-in Claude Browser** (the in-app Browser pane, tools `mcp__Claude_Browser__*`). Drew's real Chrome via the extension (`mcp__claude-in-chrome__*`) is a fallback, never the default. Do not open the extension, call `list_connected_browsers`, or ask which browser to use unless the Claude Browser has genuinely failed on a page as defined below.

| Tier | Surface | When |
|------|---------|------|
| 1 (default) | **Claude Browser** (`mcp__Claude_Browser__*`) | Every page, every run. Open with `preview_start {url}` (or `tabs_create` + `navigate` for extra tabs), extract with `javascript_tool`. No user approval needed. |
| 2 (fallback) | **Server fetch** (`scripts/fallback_crawl.py`) | A page that the Claude Browser could not render after the retry rule, and for the text-only `finance` page on every run (zero tokens). |
| 3 (last resort) | **Chrome extension** (`mcp__claude-in-chrome__*`) | Only when BOTH tier 1 and tier 2 failed on the same page (pane hung twice AND server fetch returned 403/blocked). Needs a one-time user approval; if the extension is not connected, record the page as `{"error": "surface_exhausted"}` and move on, do not stall the run. |

**Retry rule for tier 1.** A page gets at most two fresh attempts on the Claude Browser: the first in the agent's own tab, the second in a brand-new tab (`tabs_create`, then `navigate`) after closing the stuck one. If `javascript_tool` still times out or returns empty on the second attempt, cascade to tier 2. Never loop a third time on the same surface.

**Tab discipline.** The Claude Browser is ONE pane with many tabs. Every parallel crawl agent creates its own tab with `tabs_create`, captures the returned `tabId`, and passes that `tabId` on EVERY subsequent call (`navigate`, `javascript_tool`, `tabs_close`). A call without `tabId` acts on whichever tab is fronted, which is another agent's page during a parallel crawl. Close your tab when done.

**Tool name mapping** (older notes used the Chrome extension names; they map 1:1):

| Chrome extension (tier 3) | Claude Browser (tier 1, use this) |
|---------------------------|-----------------------------------|
| `tabs_context_mcp` | `mcp__Claude_Browser__tabs_context` |
| `tabs_create_mcp` | `mcp__Claude_Browser__tabs_create` |
| `tabs_close_mcp` | `mcp__Claude_Browser__tabs_close` |
| `navigate` | `mcp__Claude_Browser__navigate` |
| `javascript_tool` | `mcp__Claude_Browser__javascript_tool` |
| `read_page` / `find` / `get_page_text` | same names under `mcp__Claude_Browser__` |

Any bare mention of `javascript_tool`, `navigate`, or `tabs_*` elsewhere in this skill means the Claude Browser version unless the text says "Chrome extension".

## Vault Source-of-Truth Cross-References

Source PDFs and freshly-rebuilt quick-reference notes for every supported brand live at `Resources/automotive-guidelines/` in the vault:

- `bmw-quick-reference.md` (BMW Advertising + Website Style)
- `cdjr-quick-reference.md` (Stellantis DAP + Website Guidelines 2026)
- `chevrolet-quick-reference.md` (2025 Brand Guidelines v1.3)
- `nissan-quick-reference.md` (RMP + Pricing Guidelines)
- `harley-davidson-quick-reference.md` (Motorcycle MAP Policy)

The `brands/{brand}_guidelines.json` files inside this skill are the structured check set the audit pipeline scores against. The vault quick-references are the canonical fresh-rebuilt versions with page-number citations to the source PDFs. When a finding requires citing the source PDF (for ANSIRA disputes or co-op submission challenges), pull from the vault quick-reference and the source PDF.

If `--client` is omitted, derive the client name from the domain (e.g., `sterlingbmw.com` → `Sterling BMW`).

## Pipeline Architecture

This is a **test-driven, self-correcting** pipeline. ALL deterministic checks,
the 9 California advertising frameworks (ca_judgment_criteria.md #1-9), pricing /
Reg M / Reg Z, the full CARS Act suite, CCPA/CPRA privacy, ADA/Unruh accessibility,
TCPA lead-form consent, and the OEM brand rules, are codified as discrete
**assertable checks** in `checks/registry.py` (one engine, ~46 checks across 16
frameworks). Each check returns `pass`, `fail`, or `unresolved`: and an
`unresolved` item is NEVER reported as a violation. Instead the convergence loop
re-crawls the page with a server-side fallback crawler and re-asserts, so a
disclaimer the browser truncated away does not become a false positive.

```
Phase 0: TEST (python3 tests/test_checks.py)  : prove the checks before auditing

Phase 1: CRAWL (Claude Browser first; server fetch for text-only pages + fallback; Chrome ext last)
    → /tmp/{client}_crawl_data.json

Phase 2: ANALYZE: ONE deterministic engine + ONE cloud agent
    2a: AI-REVIEW PAYLOAD (analyze_local.py, zero tokens)
        → ai_review_needed.json   (gray-area judgment items ONLY; no findings)
    2b: CODIFIED CHECKS + CONVERGENCE LOOP (verify_loop.py, zero tokens) ← THE engine
        every deterministic check (privacy, pricing, Reg M/Z, CARS Act, brand,
        the 9 CA frameworks) lives in checks/registry.py. Run them all → for every
        UNRESOLVED check whose page looks truncated, curl/urllib re-fetch that page
        → re-assert → repeat (each page re-crawled at most once, max 4 iterations)
        → /tmp/{client}_checks_findings.json       (ALL deterministic findings)
        → /tmp/{client}_verification_report.json   (what was re-verified)
    2c: CLOUD judgment agent for true gray-area visual items (ONE Task agent)
        → ai_findings.json
    2d: MERGE checks + ai → /tmp/compliance_findings.json (dedup)

Phase 3: REPORT (run_audit.py)
    Delta engine → branded, SCORED Excel report → outputs/
    + post_flight.py validation
```

**One engine, not two.** Every deterministic check lives in `checks/registry.py`
and runs through `verify_loop.py`, so ALL of them, including the CCPA/CPRA privacy
link checks: get the false-positive-killing re-crawl loop. `analyze_local.py` no
longer runs any checks; it only assembles the small gray-area payload for the cloud
agent. There is no `local_findings.json` anymore and nothing is computed twice.

The fallback crawler is the false-positive killer: when `javascript_tool`
truncates a long specials/VDP page (the 12K/15K caps in Phase 1), the affected
checks come back `unresolved` and `verify_loop.py` re-fetches the full server HTML
to confirm whether the disclaimer (or footer privacy link) is genuinely missing
before anything is flagged.

---

## Phase 1: Crawl & Extract Page Data

Read `references/phase-1-crawl.md` NOW and follow it exactly: full crawl strategy, VDP sampling, fragment capture rules, and per-platform notes for this phase.

## Phase 2: Analyze

Read `references/phase-2-analyze.md` NOW and follow it exactly: the deterministic engine spec plus the focused cloud-agent analysis procedure for this phase.

## CONFIDENCE LEVEL SYSTEM (MANDATORY)

Every finding MUST include a confidence level:
- **high**: Clear textual evidence. No doubt.
- **medium**: Partial evidence; the AI could not fully verify (e.g., disclaimers may be behind expand buttons, popups blocked view, visual layout unknown). MUST set `needs_human_review: true` and prepend recommendation with "**NEEDS HUMAN REVIEW AND VERIFICATION**: ".
- **low**: Speculative or based on absence of evidence. MUST set `needs_human_review: true`, prepend recommendation, and consider downgrading severity to advisory.

### When to assign medium/low confidence:
- ANY claim about visual layout, font size, prominence, color, or placement
- ANY claim about disclaimers being "missing" when content may be collapsed/expandable
- ANY claim about content being "hidden" when popups or chat widgets may have blocked extraction
- ANY finding where you are NOT 110% certain

### Severity guide:
- **critical** = ONLY when you are 110% certain. Clear, unambiguous violation with textual evidence. NEVER use critical for visual/layout claims or when disclaimers might exist behind expandable content.
- **warning** = Gray-area concern, likely violation, or OEM guideline issue. Use this when uncertain instead of critical.
- **advisory** = Best practice improvement, minor concern. Use when speculative.

**IMPORTANT**: It is far better to under-flag than to produce a false critical finding. If there is ANY doubt, downgrade severity and mark needs_human_review: true.

Write your findings as a JSON array to /tmp/{safe_client}_ai_findings.json.
If no issues found from any review item, write an empty array [].
```

### Step 2d: Merge Findings (zero tokens)

Merge the deterministic (codified-check) findings with the cloud agent's gray-area
findings. There is no `local_findings.json` anymore: the registry is the single
source for all rule-based findings.

```bash
python3 -c "
import json
def load(p):
    try: return json.load(open(p))
    except FileNotFoundError: return []
checks = load('/tmp/{safe_client}_checks_findings.json')
ai     = load('/tmp/{safe_client}_ai_findings.json')
merged = checks + ai
seen, deduped = set(), []
for f in merged:
    key = (f.get('rule_id'), f.get('page_url'))
    if key not in seen:
        seen.add(key); deduped.append(f)
json.dump(deduped, open('/tmp/compliance_findings.json', 'w'), indent=2)
print(f'Merged: {len(checks)} checks + {len(ai)} AI = {len(deduped)} (deduped)')
"
```

---

## Phase 3: Delta Engine & Report

Run the Python pipeline:

```bash
python3 /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/dealership-compliance-audit/scripts/run_audit.py \
  --findings /tmp/compliance_findings.json \
  --client "<client_name>" \
  --brand <brand> \
  --url "<url>" \
  --verification /tmp/{safe_client}_verification_report.json
```

This script handles:
- Stage 4 (Delta): Compares against prior month's snapshot in `history/` (VDP findings
  are bucketed so they track across months despite changing VINs)
- Stage 5 (Report): Generates branded Excel to `outputs/`, including a **Re-Verification**
  tab from the verification report (re-crawls, false positives averted, items left for
  human review)

Output path: `outputs/<client>_compliance_audit_<YYYY-MM>.xlsx`

---

## After Completion

Print a summary to the user:
1. Overall compliance score and grade
2. Count of Critical / Warning / Advisory findings
3. Top 3 most urgent findings (critical first)
4. Delta summary (if not first audit): how many NEW, PERSISTING, RESOLVED
5. **Re-verification summary from `verification_report.json`**: how many checks were
   re-crawled, how many false positives were averted (unresolved→pass after the
   fallback fetch), how many violations were confirmed after re-crawl, and any
   items left `still_unresolved` (presented as "needs human review", not violations)
6. **VDP spot-check summary**: how many VDPs were sampled (and from how many
   candidates), the VINs/URLs checked (from `vdp_sample_meta`), and any per-vehicle
   issue stated as a PATTERN, e.g. "3 of 4 sampled VDPs advertise a payment with no
   total-amount-payable disclosure": systemic, not one-off.
7. Output file path

---

## Error Handling

### Page Load Failures
- If a page returns 404 or fails to load, skip it and note the failure in the crawl data
- Do NOT guess URLs: only use URLs discovered from the homepage navigation
- Do NOT retry the same URL more than once

### JavaScript Extraction Failures (Claude Browser)
- If `mcp__Claude_Browser__javascript_tool` returns an error or empty result, try a simpler extraction in the same tab:
  ```javascript
  document.querySelector('main')?.innerText?.substring(0, 10000) || document.body.innerText.substring(0, 10000)
  ```
- If that also fails, apply the Browser Surface Order retry rule: one fresh tab (`tabs_create` + `navigate` with the new `tabId`), then cascade to `scripts/fallback_crawl.py`, then (only if server fetch is 403/blocked) the Chrome extension.
- A page that is still empty after all three surfaces is written as `{"error": "surface_exhausted", "url": "..."}` and surfaced as needs-human-review, never as a violation.
- NEVER use `get_page_text` on inventory/listing pages, they exceed the 50K char limit
- NEVER use `read_page` without `ref_id` on large pages, it exceeds char limits
- `read_console_messages` / `read_network_requests` on the Claude Browser are useful to confirm WHY a page hung (WAF 403, infinite XHR) before deciding which tier to cascade to.

### Pane Hangs (Claude Browser)
- Dealer Inspire / Cars.com inventory-search pages can stop compositing the pane. Close the stuck tab (`tabs_close` with its `tabId`) and open a fresh one; do not `navigate` the hung tab again.
- If the whole pane is unresponsive, `preview_start {url}` reopens it.

### Screenshot Failures
- `computer {action: "screenshot"}` on the Claude Browser is optional and for visual verification only
- Do NOT rely on screenshots for data extraction, always use `javascript_tool`
- On the Chrome extension fallback, screenshots may fail with "Cannot access chrome-extension:// URL"; ignore it

---

## File Locations

- **Codified checks:** `checks/registry.py` (9 frameworks + pricing + brand, as assertable pass/fail/unresolved checks)
- **Fallback crawler:** `scripts/fallback_crawl.py` (curl/urllib server-side re-fetch)
- **Convergence loop:** `scripts/verify_loop.py` (crawl→analyze→correct, emits verification_report.json)
- **Check runner / tests:** `scripts/run_checks.py` (test-style output), `tests/test_checks.py`, `tests/validate_skill.py`, `tests/fixtures/`
- **Legal currency:** `rules/legal_watch.json` (what each framework is + when last verified) + `scripts/legal_watch.py` + `LEGAL_WATCH.md` (the monthly stay-current loop and the feedback/override loop). CARS is California-first: federal FTC CARS Rule is vacated+withdrawn; CA SB 766 (§1784.20 et seq.) controls, operative 2026-10-01, so CARS findings stay forward-looking (softened, never critical) until then. CNCDA guidance (Guide v1.2 + FAQ) is the operational layer on top of the statute; cite it as 'CNCDA Guide Part N' or 'CNCDA FAQ QN' in recommendations.
- **Hard rules:** `rules/ca_hard_rules.json` (98 rules: advertising law + CARS Act `CA-CARS-001` to `-040` + FTC Pricing Transparency FAQs `FTC-*` (16 rules: 12 from the Sept. 2026 FAQs, 4 added 2026-10-08 from the 2026-09-30 FTC staff remarks: `FTC-SAVE-001`, `FTC-CTA-001`, `FTC-AVAIL-003`, `FTC-AI-001`) + CCPA/CPRA privacy; `ftc_reference` block carries the FTC FAQ digest by question, the `staff_remarks_2026_09_30` digest, resolved open questions, and the California doc-fee tension; `cars_act_reference` block carries DMV scope, exemptions, complaint channels, and the `cncda_guidance` block from the CNCDA Compliance Guide v1.2 and Webinar FAQ, folded in 2026-09-14; vault digest at `Resources/automotive-guidelines/cncda-cars-act-guidance.md`)
- **Judgment criteria:** `rules/ca_judgment_criteria.md` (18 criteria: 9 advertising + 2 privacy + 6 CARS Act + 1 FTC Pricing Transparency FAQs, including first-communication surfaces and cross-surface price parity)
- **FTC checks:** `checks/registry.py` framework `FTC` (FTC-DOCFEE-CA, FTC-COND-PRICE, FTC-USED-STOCK-PHOTO, FTC-LEASE-DAS-FEE, and since 2026-10-08 FTC-SAVINGS-SCOPE, FTC-CTA-LOWER-PRICE, FTC-INTRANSIT-STATUS). Federal and current, so no CARS operative-date softening; staff views, so they ship as warnings with human review. Vault source: `Resources/automotive-guidelines/ftc-advertising-compliance.md`.
- **Brand guidelines:** `brands/bmw_guidelines.json`, `brands/nissan_guidelines.json`, `brands/cdjr_guidelines.json`, `brands/chevrolet_guidelines.json`, `brands/harley_davidson_guidelines.json`
- **History snapshots:** `history/{client}_{YYYY-MM}.json`
- **Python scripts:** `scripts/analyze_local.py` (AI-review payload builder only, all deterministic checks live in `checks/registry.py`), `scripts/run_audit.py`, `scripts/delta_engine.py`, `scripts/generate_report.py`
- **Output:** `~/Desktop/DigitalCLIQ Brain HQ/outputs/` (vault-local; reports archived alongside the vault)

All paths are relative to this skill's directory: `.claude/skills/dealership-compliance-audit/`


## Self-Validation (MANDATORY: final step before reporting success)

After the deliverable is generated, run the shared post-flight validator on the final file. This step is not optional and runs on every invocation:

```bash
python3 /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/post_flight.py \
  "<final output path>" --min-sheets 3
```

It verifies four things and exits non-zero if any fail:
1. **Branding**: the DigitalCLIQ logo is actually embedded in the file (an image in xl/media inside the workbook). A Digital Blue masthead with no logo image is a FAILURE, not a fallback.
2. **Location**: the file is inside `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/`. Anywhere else (especially the Desktop) fails.
3. **Sheet count**: at least 3 sheets; fewer means a section silently failed or the report is truncated.
4. **No placeholder data**: template tokens like `{dealer_name}`, literal `YYYY-MM-DD`, "PLACEHOLDER", or lorem ipsum anywhere in the deliverable fail.

**On failure: retry once with a fallback, then fail loudly:**
1. Diagnose from the validator output. Common fixes: the logo must load from the canonical path `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png`; a file saved outside `outputs/` must be moved there and re-validated; a placeholder hit means a data section came back empty, re-fetch that data, do not paper over it.
2. Regenerate the deliverable ONCE and re-run the validator.
3. If it still fails: STOP. Show the user the validator output verbatim and state that the report FAILED validation. Never report success, never present the file as the final deliverable, and never wrap this step in try/except or `|| true` that hides the failure.


## Final QA Gate: deliverable-reviewer agent (MANDATORY, added 2026-08-13)

Runs AFTER the deliverable is generated and post_flight.py passes, BEFORE filing/presenting. post_flight.py is mechanical; this gate is the human-style read.

1. **Write a facts manifest** next to the deliverable in `outputs/`: a JSON list of every number, name, date, and claim that appears in the deliverable, each as `{"value": ..., "label": "where it appears", "source": "tool/file/URL it came from"}`. Build it from data already in context, never re-fetch anything just for the manifest.
2. **Spawn the `deliverable-reviewer` agent** (fresh eyes, it did not write the report). Pass in the prompt: the absolute path(s) of the finished deliverable file(s), the manifest path, and any skill-specific checks from this SKILL.md. It renders every page, reads them all, cross-checks figures against the manifest, and reviews tone/copy.
3. **Auto-fix every finding** in the source generator or data (never by hand-editing the output), re-render, and re-run the agent once. Max 2 review passes. If CRITICAL or MAJOR findings remain after pass 2, the ship is BLOCKED: report the remaining findings to Drew verbatim instead of presenting the file as done.
4. The run summary MUST include a **QA line**: what the reviewer caught and what was fixed, or "QA: clean on first pass (N pages read, M figures verified)". Never silently skip the gate; if the agent could not run, say so explicitly in the delivery message.
