---
name: nightly-notes
description: Nightly Sweep of what I did during the day
---

Sweep everything Drew Moon did today and log it into his Obsidian vault, one daily note **plus** per-client context-log entries.

## Vault access, READ THIS FIRST

**The vault is LOCAL, on the Desktop.** Target root: `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/`

> [!danger] Google Drive is NOT the vault
> A mirror of the vault exists in Google Drive. It is for **backup and sharing with others only**. NEVER write the daily note, a context log, or any vault file to Google Drive. Do not go looking there when the local path is giving you trouble, it is not a fallback, it is a different thing that happens to look similar. Content read back from Drive also arrives with mangled markdown escaping, so it is not even a reliable read source. Read and write the local vault, always.

### Choosing the write path

**Step 1, Is a human present?** If this is an interactive session (Drew is talking to you), and the file tools report "outside this session's connected folders", **call `request_cowork_directory` with `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ` immediately.** Drew approves it and you get full Read/Write/Edit access. This is the correct, fastest path whenever he is there. Do not hunt for workarounds while he is sitting waiting.

**Step 2, Unattended scheduled run?** Then and *only* then does the no-prompt rule apply: do NOT call `request_cowork_directory`, because nobody is present to approve it and the call aborts the run (this caused the silent failures Jul 31, Aug 14, 2026). Use the bash sandbox mount instead:

1. Compose the finished note with the Write tool into your session outputs folder as `YYYY-MM-DD.md`.
2. In bash the vault mounts at `/sessions/<session-name>/mnt/DigitalCLIQ Brain HQ/`. Discover the name with `ls /sessions/`. **Confirm the mount actually exists**, `ls "/sessions/<name>/mnt/"`, before assuming it does. It is not present in every run.
3. Check for an existing note: `cat ".../Daily/YYYY-MM-DD.md"`. If it exists, merge it into your copy first.
4. Ship with `cp`, verify with `ls -la`.

> [!warning] Do not test the macOS path with bash
> `ls /Users/drewmoon/Desktop/...` inside the bash sandbox **always fails**, the sandbox is a separate Linux filesystem that can never see the Mac's Desktop. A failure there proves nothing about whether the file tools can reach the vault. To test the real path, use the **Read tool** on it. Getting this backwards produced a false "vault unreachable" report on 2026-08-26.

Only if the file tools fail, a human is not present, AND the bash mount is absent: save to the outputs folder, say so explicitly at the top of your report, and continue. Never abort the sweep over a path problem.

Vault history: de-nested and renamed 2026-08-16. Root is `DigitalCLIQ Brain HQ` directly on the Desktop. The old `/Users/drewmoon/Desktop/DigitalCLIQ Brain/DigitalCLIQ Brain` path is gone.

## What to sweep

Drew's email is drewmoon@digitalcliq.com. Cover:

- **Gmail**, sent and received. Sent mail is the best signal of what he actually did.
- **Google Calendar**, where he was, which client he visited.
- **Slack**, the client channel matching today's calendar visit, plus #mcpeek-cdjr, #new-century-bmw, and any channel he posted in. Always check **#mileage**.
- **Mileage**, log the odometer number he posted in #mileage, plus miles driven between the DigitalCLIQ office (5857 Pine Ave, Chino Hills) and wherever he went. Give a round-trip estimate. If no odometer was posted and the day's meetings were remote, say so plainly rather than estimating.
- **Apple Notes**, anything new or edited. If a meeting note was created but left empty, **flag it loudly**, that meeting is unrecorded and the detail is decaying.
- **Google Drive**, new files or updates (as a *signal of work done*, never as a write target).
- **Notion**, new or changed tasks.
- Anything done inside Claude/Cowork today, including scheduled-skill runs and their deliverables.

## What to write

**Two things every run:**

### 1. The daily note, `Daily/YYYY-MM-DD.md`

```yaml
---
type: daily-note
date: YYYY-MM-DD
status: active
tags: [daily-note, {client codes touched}]
generated-by: nightly-notes
---
```

Then `# Dayname, Month D, YYYY`, a `## Where you were` section, `## Mileage` if applicable, **one `##` section per client** using the client's name and code (MCP, SBMW, NCBMW, NOI, CHC, Atlas, PAG, LPA, CBH), and a short `## Open at end of day` list. CDHD (Chuck Deluxe Harley-Davidson) is a former client since 2026-09-23: no CDHD section; only log emails about its two open offboarding items (the Google Ads account billing Drew's card, and check #28005) under Drew's admin notes until they close.

- **One note per date.** If it already exists, APPEND, never create a second file, never overwrite existing content. Another skill's run may have written to it earlier the same day; preserve that verbatim.
- Keep it under ~8KB. Quick list up top, 2 to 3 line per-client summaries. Deep detail goes in the context log, wikilinked from the daily rather than duplicated.
- Use `[[wikilinks]]` for people, companies, and vendors.
- Include real names, times, dollar amounts, ticket/case numbers, and VINs exactly as they appear.
- Frontmatter must include status: active and a tags list that starts with daily-note, followed by the lowercase code of every client touched that day (mcp, sbmw, ncbmw, noi, chc, atlas, pag, lpa, cbh). When appending to a note that already exists, add status or tags if they're missing, and add any new client codes to tags. Never remove existing frontmatter fields.
- No em dashes or en dashes anywhere in the daily note, context logs, Notion tasks, or the run report. Use commas, colons, or " to " for ranges.

### 2. Per-client context logs, `Projects/{CODE}/context-log.md`

Every client touched today gets an entry in its own running context log. This is where the depth lives and what feeds the monthly report.

- **Newest entry at top**, under the current `### {Month} {Year}` heading. Use a `### YYYY-MM-DD · title` heading for each entry, never `##`. Never remove old entries.
- Prospect-stage work stays in the root `Daily/` note only (Drew corrected 2026-08-17): no project folder, no roster code, no context log until Drew says the prospect signed. `Projects/_Prospects/` was retired 2026-08-30.
- Check before writing: another skill's run may already have logged today's entry (the `cars-act-check` skill writes its own). Do not duplicate it.
- Lead each entry with `**Daily log:** [[Daily/YYYY-MM-DD]]` and any deliverable wikilink.

Close the daily note with:
`<span style="background-color:#405FAB; color:#FFFFFF; padding:2px 8px; border-radius:3px; font-size:0.85em;">🤖 Logged by Cowork.</span>`

## Tasks

If anything in the day should become a task, create it in the Notion `💼 TASKS` database, assigned to the right client via the `Client` property, **due the following week** unless a specific date was stated. Query existing open tasks first to avoid duplicates.

## Goal

Drew works; you document. Good enough that at the end of the week he can read back what he did and pull client wins out of it. Not exhaustive, but genuinely complete, nothing important missing.
