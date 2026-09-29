> [!warning] Retired 2026-09-28 (Drew: "I don't need Friday GM notes... I am paying attention so if they ask I can tell them or get it myself"). Nothing in the shift reads or runs this file or `scripts/gm_note.py` any more; both are kept only as history.

# Friday GM note template (Magic drafts, Drew edits and sends)

GMs never see what the team catches overnight. Every Friday the shift drafts one page per store for the store's GM: what we watched this week, what we caught, the one number that moved, and what we need from the store. [[Drew Moon]] edits and sends every note himself. Nothing goes out automatically: no Slack post to the store, no email, no Drive share. Approved by Drew 2026-09-23. Worked example: `outputs/ai-team/gm-notes/2026-09-25/NOI.md` and `NOI.pdf`.

## Who gets one

Every dealership with a GM, GSM, or owner in `Projects/{CODE}/README.md` "Key contacts": [[MCP]], [[NOI]], [[SBMW]], [[NCBMW]]; plus [[CHC]]'s CARS Act note to Johnny Han (section below). [[Atlas]] is not a dealership and gets none. Read the README before naming anyone (contacts are per client; two clients have a Frank). If the README lists no GM, GSM, or owner, address the note to "the GM" and say so in the Drew block. A store with no claim that passes the rules below gets no note that week; say so in the brief instead of padding one.

## CHC: the CARS Act note to Johnny Han (Drew, 2026-09-23)

[[CHC]] (Covina Hills Chevy) also gets a Friday note, built only from Thursday night's CARS web watch (`outputs/ai-team/{thursday}/data/cars_CHC/summary.md` and `run.json`), addressed to [[Johnny Han]] per `Projects/CHC/README.md`. We do not see CHC's analytics, ads, or CRM (our scope there is banner design), so the note is only about the public website. Same structure and renderer as the other notes, with these differences:
- **What we watched:** the public pages of the site the watch fetched, and the date.
- **What we caught:** up to three `review` findings, each with the exact wording quoted from the page, one URL, and the requirement in plain words (for example "the advertised price has to include everything except tax, license, and government fees"). Always "flagged for review", never "violation" or "non-compliant"; we are not giving legal advice.
- **The one number that moved:** the number of vehicle pages carrying the top flagged wording, with the scan date as its source.
- **What we need from you:** whether their website vendor can adjust the flagged wording before the CARS Act takes effect on October 1, and an offer to walk through the list with them. No price and no pitch in the note; Drew's goal is to grow the relationship, and a useful, accurate list is the pitch.
- **Claim rule for this note:** the two-shift rule does not apply (the site is scanned weekly); instead every quoted wording must appear verbatim in `run.json` from Thursday's scan, and Magic re-fetches one flagged URL tonight to confirm it is still live before the note is drafted. A finding the watch marked as a known false positive never appears.

## Structure (fixed order, one page, markdown that `scripts/gm_note.py` renders)

```
---
type: gm-note
date: {Friday, YYYY-MM-DD}
status: draft
project: {CODE}
store: {store name as the README writes it}
to: {GM name from the README}
to_role: {role from the README}
week: Week of {Mon abbrev} {d} to {d}, {yyyy}
title: This week at {store}
tags: [ai-team, gm-note, {store-slug}]
---

%% one-line note to Drew: draft, not sent, render command %%

## Opening
{GM first name}, {one or two sentences, 35 words max}.

## What we watched
{The lanes that had live data this week and the dates, 40 words max.}

## What we caught
1. **{Headline in plain words.}** {Evidence with numbers and date ranges. What it means for the store or what we are doing.}
   Source: {source in plain words}, {date range}
2. ...

## The one number that moved
Number: {the figure}
Caption: {what it measures and what it moved from, 30 words max}
Source: {source}, {window}

## What we need from you
- **{Name}, {Role}:** {the ask, 45 words max}

## Sign-off
{Optional one line.}

Drew Moon, DigitalCLIQ

## For Drew (not rendered, not sent)
{Compliance line, addressee line, claim ledger, held back list. See below.}
```

Limits the renderer enforces: 1 to 3 caught items, each with a bold headline and a `Source:` line; at most 3 asks, each opening `**Name, Role:**` (or the line "Nothing needed from you this week."); client-facing body 330 words target, 360 hard cap; one page exactly; no em dash; no placeholder text. Each caught item stays at or under 60 words. Only the six sections above render; the Drew block and `%% %%` comments never reach the PDF.

## Where candidates come from

- The week's briefs and findings files, Monday's shift folder through tonight's (the Friday shift covers Thursday; the note covers last Friday through Thursday).
- `outputs/ai-team/ledgers/asks.json`: the store's asks with `needs_store: true`, status `open`, raised on two or more shifts, become "What we need from you". If a request draft already exists in `outputs/ai-team/asks/requests/`, reuse its wording so the store never sees two versions. Asks `closed` this week with a `win` are caught-item candidates. `withdrawn` asks, and their numbers, never appear.
- `outputs/ai-team/ledgers/health-state.json`: no claim is built on a measure that is `open` at severity red for that store (MCP website conversions, for example). Health items themselves stay out of the note unless Drew asks.
- `outputs/ai-team/ledgers/crm-corrections.json`: apply before quoting any `crm_mtd_*.json` figure.

## Claim rules (Magic applies them; the reviewer checks them)

1. **Two shifts.** A claim goes in only if it appeared in at least two shift folders inside the note's week (findings file or brief) and no later shift contradicted it. Being quoted in one brief is one shift. A data file carried forward from an earlier shift is not a second shift: the claim needs a second check (a new pull, or a player re-deriving it). A claim first raised by the Friday shift waits for next week's note. (The NOI sample first led with top-3 rankings 52 to 77; only 9/22 had checked it, and the reviewer caught it.)
2. **Verified at source.** Magic re-opens the source file the findings cite (`data/*.json`, the Ads export tab, the CRM snapshot JSON) and recomputes every number in the note. The note uses the newest figure that exists on disk. A figure that lives only in a findings file, because its source report was not kept, does not go in the note; the ledger says so.
3. **Withdrawn claims never appear**, and neither does any number that came from them. Before drafting, search the week's briefs and findings for corrections ("we had that wrong", "withdrawn", "corrected", "not a", "turned out", "Could not verify"). Known examples: [[NOI]] "46 dollars a day at risk" on three Meta campaigns (they were finished boosted posts, corrected 9/23); [[NOI]] Gas Models "spent and returned nothing" (26 calls its conversion setting did not count, corrected 9/22); [[NCBMW]] "CRM feeds stopped" (a bug in the team's own script).
4. **Every number carries its date range in words** ("Sept 1 to 21", "Sept 16 to 22"), and the sentence stays inside that range ("no leads in that window", not "no leads this month"). Month-to-date figures say so. Monthly estimates (Semrush) say "as of mid-August" in the caption itself, not only in the source line.
5. **Aggregates only.** No customer names, phone numbers, VINs, deal numbers, salesperson names, Ads customer ids, Meta account or campaign ids.
6. **Out of the note:** open questions, anything under "Could not verify", single-shift claims, radar items, unverified trade press, benchmarks without one named source (the team quoted NOI website close rate against both 10% and 12% in one week; neither went in).
7. **Our own campaign problems** (a campaign Google stopped serving, a setting we got wrong) go in only after there is a cause and a fix under way, and only if Drew keeps them. Until then they sit in the Drew block under Held back.
8. **Internal stays internal:** no player names (Magic, Kobe, Shaq, Luka, Worthy, Nick), no tool names a GM would not use (GA4, PMax, key events, UTM, GTM), no tracking breaks or fixes unless Drew asks (vault-facts), no vendor gripes, no other client.
9. **Asks go to the role that can act**, named from the README: GM or owner for vendor contracts, budgets, and approvals; the store's specials contact for offers; the store's CRM, website, or GA4 admin by role when the README has no name. Never a sales-floor person (Rule 23). Every ask says what happens either way.
10. **The one number** is the single most meaningful verified change. Prefer something that moved inside the note's week; if nothing did, use the strongest verified trend and state its window. It must pass rules 1 to 4 like any claim.

## Tone rules

- DigitalCLIQ's own voice (`Context/brand.md`): direct, confident, dry over warm, senior, data-backed, no fluff. A teammate to the dealership: "we", "your store", "your website leads".
- GM level (Rule 23): money, sales, leads, vendors, reputation, decisions. No sales-floor coaching, nobody named negatively.
- Lead with the point, number second, then what it means or what we are doing. Plain words: "website visits" not sessions, "your website analytics" not GA4, "Google's top 3" not pos 1-3. Gloss any term a GM might not use, once.
- Honest both ways: bad news in plain words with the next step; good news without taking credit the data cannot prove.
- A move the team recommended but Drew has not approved is written as a recommendation ("Our recommendation: ..."), never as done or decided.
- Say only what the measure shows. A GA4 count tied to one campaign is "your website analytics tied 58 visits to it", not every visit the site had. Never quote seconds on site (GA4 logs single-page sessions as 0 seconds); non-engaged sessions "left within seconds". A headline like "strongest source" must survive the small sources: when Referral closes at 50% on 14 leads, lead with sales counts, not close rate.
- Numbers in the store's own systems that Drew has called stale (the NOI VinSolutions cost page) are "logged in" or "shows in" that system, not "spent".
- Never "cheap", "fast", "turn key". Never em dashes (Rule 14). No exclamation marks.

## Compliance line (required in every Drew block)

Any offer, price, payment, lease term, APR, rebate, savings claim, or ad copy that appears in a note, including anything Drew adds while editing, gets checked before Drew sends: federal first (`Resources/automotive-guidelines/federal-ad-rules-index.md`), then California (`ca-cars-act-sb766-index.md`, and `cncda-cars-act-guidance.md` for operating questions), then the store's OEM file (`nissan-quick-reference.md` for NOI, `bmw-quick-reference.md` for SBMW and NCBMW, `cdjr-quick-reference.md` for MCP; the Stellantis Marketing Covenant is not in the vault, say so). Stricter wins (Rule 24). The Drew block carries one of:

- `Compliance: no offer, price, payment, lease term, or ad copy is quoted; nothing to gate. If you add any, run federal, then California CARS Act, then {OEM file} before sending.`
- `Compliance: {what was quoted}. Checked federal ({sections}), California ({sections}), {OEM file}: {pass | change needed: what}.`

## The Drew block

Four parts, in this order, so Drew can edit in two minutes:
1. **Compliance** line, as above.
2. **Addressee**: who, from which README line, and who else was considered.
3. **Claim ledger**: per claim, the shifts it held on (with that shift's figure), the source file and field it was re-checked against, and any caveat Drew told the team.
4. **Held back, and why**: every candidate that failed a rule (withdrawn, one shift, our own open problem, internal), one line each, so Drew can pull one back in knowingly.

## Render and QA

1. `python3 .claude/skills/ai-team/scripts/gm_note.py outputs/ai-team/gm-notes/{date}/{CODE}.md` writes `{CODE}.pdf` beside it: Digital Blue masthead with the WHITE logo, numbered caught cards, a dark stat band for the one number, the ask as a callout, footer and pillars strip. It refuses (non-zero exit) on an em dash, a placeholder, too many words or items, an ask with no addressee, a figure missing from `{CODE}.facts.json`, more than one page, a font other than Dosis or Roboto Slab, or a missing logo. Cut words, never shrink type, when it runs long.
2. `{CODE}.facts.json` beside the note: every figure, name, and date with its source file, field, date range, and the shifts it held on (see the NOI example).
3. `python3 .claude/skills/post_flight.py outputs/ai-team/gm-notes/{date}/{CODE}.pdf --min-pages 1`.
4. `python3 Resources/design-system/templates/render_check.py outputs/ai-team/gm-notes/{date}/{CODE}.pdf`, then read the PNG against `Resources/design-system/Visual-QA.md` until two reads in a row need no fix (Rule 17).
5. Spawn the `deliverable-reviewer` agent with the PDF, the manifest, and this file's claim rules as its skill checklist (Rule 22). Fix in the `.md` or the generator, never the PDF; re-render; max two reviewer passes. Anything still CRITICAL or MAJOR goes to Drew verbatim in the brief and that note is marked "not ready".
6. After Drew sends, he files the PDF to `Projects/{CODE}/deliverables/` (Rule 18). Magic never files or sends it.
