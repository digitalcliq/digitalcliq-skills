---
name: daily-work-log
description: >-
  End-of-day work-log sweep for Drew. Captures everything Drew actually did today
  across every connected surface (Cowork/Claude sessions including code and the
  Chrome plugin, Gmail sent + replies handled, Google Calendar events, Notion pages
  and tasks, Google Drive files, Slack messages, Apple Notes, and new files written
  to the vault), analyzes each item, routes it to the client it pertains to, and
  writes two things: a master "everything I did today" entry in the root Daily note,
  and per-client running-context updates in Projects/{CODE}/. Preserves any notes Drew
  typed himself. Structured so weekly and monthly accomplishment rollups are trivial.
  Use when Drew says /daily-work-log, "log my day", "what did I do today",
  "end of day log", "update my daily notes", or when run on a schedule each evening.
argument-hint: '[YYYY-MM-DD] (defaults to today, America/Los_Angeles)'
---

> [!important] Pre-flight: load the ledger and routing table FIRST
> 1. Read `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Context/vault-facts.md` and obey it (output location, canonical names, the email rule).
> 2. Read `references/client-routing.md` in this skill folder. It is how you attribute activity to clients.
> 3. Read the root `CLAUDE.md` for vault rules (Obsidian syntax, no em dashes, file routing).

> [!warning] Autonomous run
> This skill usually runs unattended on a schedule. Never wait for input. Make sensible
> defaults, do the work, and write the result. If a connector is missing or errors, note it
> in the run and keep going. Do not fail the whole run because one source is unavailable.

# Daily Work Log: DigitalCLIQ

The job: reconstruct Drew's day from every tool you are plugged into, then persist it so nothing he worked on is forgotten. Output is vault notes, not a client deliverable.

## 0. Setup

- Vault root: `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ`. If it is not mounted, request access to that exact path. In bash it appears under the session mount; use absolute paths.
- Determine the target date. Use the argument if given, else today in `America/Los_Angeles` (`TZ=America/Los_Angeles date +%F` via bash). Call it `DATE`.
- The master note is `Daily/DATE.md`. Read it if it exists. It may already contain Drew's hand-typed visit notes or operator content. You will PRESERVE all of it and add to it, never overwrite.

## 1. Sweep every source (fan out)

Gather Drew's OWN actions for DATE. Where a connector has the right tools, use them. Prefer running independent reads in parallel (a subagent per source is ideal for speed). For each source, capture concrete outcomes, not raw dumps.

| Surface | What to pull |
|---|---|
| Cowork / Claude sessions | `session_info` `list_sessions` then `read_transcript` on the ones active on DATE. This is the core "what I did with Claude" layer: code written, files generated, Chrome-plugin work, research, analyses. Summarize the outcome and any deliverable path. Only include DATE; ignore older sessions even if they sit near the top. |
| Gmail | Search `in:sent after:DATE before:DATE+1` for what Drew sent, plus notable threads he handled (look at the same threads for inbound he resolved). Capture recipient, subject, and the decision or action. Use the connected Gmail tools. |
| Google Calendar | List events on DATE: meetings attended, calls, anything he created or moved. Note attendees and the client. |
| Notion | Find pages created or edited on DATE and TASKS he created or completed. Search recent activity and the `💼 TASKS` database. Capture task titles, status changes, and any page he authored. |
| Google Drive | Recent or modified files on DATE that Drew added or edited. Capture name, folder, and what it is. |
| Slack | Messages Drew sent on DATE in client or internal channels. Capture the channel, the gist, and any decision. |
| Apple Notes | Notes created or modified on DATE. These are often Drew's raw, hand-typed visit notes. Treat them as primary source: fold their substance into the right client and the master note. |
| New vault files | `find` files written on DATE (bash `-newermt "DATE 00:00" ! -newermt "DATE+1 00:00"`), especially under `outputs/` and `Projects/`. New deliverables count as work done. |

If a source returns nothing or is not connected, record one line ("Slack: no activity / not connected") and move on.

## 2. Analyze and route

For every captured item, attribute it to a client using `references/client-routing.md` (email domain, store name, key person, project code, web domain). Group the day into buckets:

- One bucket per client with activity (MCP, NCBMW, SBMW, NOI, CDHD, Atlas, FFLOW, etc.)
- **Internal / DigitalCLIQ** for agency ops, tooling, hiring, the vault itself.
- **Personal** for anything not work. Never route personal content into a client file.

Disambiguate carefully (see routing rules: domain beats a loose first-name match). When two clients genuinely share an item, log it under both. When unsure, put it in Internal and flag it rather than guessing.

## 3. Write the master daily note (`Daily/DATE.md`)

This is Drew's "everything I did today" record and the spine of the weekly/monthly rollup.

- If the file does not exist, create it with the vault's daily-note frontmatter:
  ```
  ---
  type: daily-note
  date: DATE
  status: active
  tags: [daily, log, <client-codes-touched>, <themes>]
  ---
  ```
- **Preserve** everything already in the file (Drew's typed notes, operator content, the McPeek plan, etc.). Add to it; never delete or rewrite his words.
- Near the top (after any existing intro, before detail sections) maintain a concise quick-list for rollups:
  ```
  ## Accomplishments (quick list)
  - [Client] one-line outcome
  - [Internal] one-line outcome
  ```
  Keep each bullet to a single, scannable result. This is what weekly/monthly rollups harvest.
- Then add or extend detail sections, one `## ` per workstream, in the vault's prose voice. Use `[[wikilinks]]` for every person, client, project, and note. Cross-link client work to its `Projects/{CODE}` file and any visit note.
- Idempotent: if you have logged this day before, update in place and do not duplicate entries. Match on outcome, not exact wording.
- Keep the existing closing footer span if present; if creating the note, end with:
  `<span style="background-color:#405FAB; color:#FFFFFF; padding:2px 8px; border-radius:3px; font-size:0.85em;">🤖 DigitalCLIQ Daily Work Log. DATE</span>`

## 4. Route into client files

For each client bucket with real activity, update `Projects/{CODE}/README.md`:

- Add the day's items to the **Running Context Log** (newest entry at the top, do not delete old entries), following the existing entry format: a dated `### ` header, a `**Daily log:** [[Daily/DATE]]` link, a `**What happened:**` block, and `**Open carry-ins for next visit:**` if any.
- If the day included an on-site visit for that client, also create `Projects/{CODE}/visit-notes/DATE.md` using the vault's visit-note frontmatter and section style, then link it from the running-context entry. (Drew visits MCP, SBMW, and NCBMW weekly, so those are the usual visit clients.)
- Move any newly surfaced open items into that client's **Open Items (Persistent)** table, and add wins/challenges to the **Monthly Wins / Challenges Log** when material.
- Dedupe against what is already in the file. If the operator or an earlier run already logged it, do not repeat it.

Only touch a client file when there is genuine activity for that client that day. No filler.

## 5. Close out

- Report a short summary to the run: which clients got entries, how many items logged, anything that needs Drew's eye (ambiguous attribution, an unfinished deliverable, a flagged compliance item).
- If nothing meaningful happened on DATE, write a one-line "Quiet day, nothing logged" entry and stop. Do not invent activity.

## Weekly / monthly rollup (how this pays off)

Because every day carries an `## Accomplishments (quick list)`, a rollup is a concatenation:

> "Read the `## Accomplishments (quick list)` from every `Daily/` note in [date range] and write a DigitalCLIQ weekly accomplishments summary grouped by client, with wins and open items. Audience: internal review."

Swap the range for a month to get the monthly. The per-client Running Context Logs already feed the monthly client report prompt documented in each `Projects/{CODE}/README.md`.

## Hard rules

- Never use em dashes. Use periods, commas, colons, or restructure.
- Obsidian-native syntax only: `[[wikilinks]]` for every entity, callouts sparingly, tags in frontmatter.
- Only `drewmoon@digitalcliq.com` may appear as Drew's contact. `digitalcliq@gmail.com` is banned.
- Never create files in the vault root. Daily notes go in `Daily/`, client work in `Projects/{CODE}/`, generated deliverables in `outputs/`.
- Preserve Drew's hand-typed notes verbatim in substance. You are adding context, not editing his voice.
- Keep it client-ready and unsweetened: direct, specific names, specific outcomes. No motivational filler, no emojis.
- Be idempotent. Re-running for the same day refreshes, it does not duplicate.
