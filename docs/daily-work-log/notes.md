---
type: skill-notes
skill: daily-work-log
status: active
tags: [skills, automation, daily-log, reporting]
created: 2026-06-25
---

Design notes and change log for the [[Skills/README|daily-work-log]] skill. Runtime source of truth: `.claude/skills/daily-work-log/SKILL.md`.

## What it does

End-of-day sweep that reconstructs [[Drew Moon]]'s full day from every connected surface and persists it to the vault. Two outputs every run:

1. A master "everything I did today" entry in the root `Daily/DATE.md` note, with an `## Accomplishments (quick list)` block at the top for painless weekly and monthly rollups.
2. Per-client running-context updates in `Projects/{CODE}/README.md` (and a `visit-notes/DATE.md` when the day included an on-site visit), so work lands in the client file it belongs to.

## Capture surfaces

Cowork/Claude sessions (`session_info`, including code and Chrome-plugin work), Gmail sent + handled, Google Calendar, [[Notion]] pages and the `💼 TASKS` database, Google Drive, Slack, Apple Notes (Drew's raw typed visit notes), and new files written to the vault. Missing or disconnected sources degrade gracefully, the run never hard-fails on one source.

## Routing

`references/client-routing.md` maps activity to a client by email domain, store name, key person, project code, or web domain. Vendors and OEM contacts attach to the client they serve, not their own company (Lamar and Shift Digital are the canonical examples). Personal content never enters a client file. Keep the routing table in sync with `Projects/*/README.md` frontmatter as the roster changes.

## Why it exists

Drew works across a dozen clients in a day and asked to stop losing track of what he touched. The daily master note is the spine, the per-client routing keeps each `Projects/{CODE}` file current for the end-of-month client report, and the quick-list makes weekly accomplishments a concatenation rather than a memory exercise.

## Schedule

Runs unattended weekdays at 7:00 PM local via the scheduled task `daily-work-log-evening`. If the machine is asleep or the app is closed at 7, the run fires on next app launch rather than being skipped. Built to be idempotent: re-running a given day refreshes in place and does not duplicate entries.

## Open ideas

- Companion weekly rollup task (Friday evening) that harvests the week's quick-lists into a DigitalCLIQ weekly accomplishments summary, and a monthly variant on the 1st.
- Confirm key people and email domains for the lighter accounts (CHC, CCT, DKD, MFK, RAVE, TGN) so routing for them is as tight as the dealerships.
- Optional: push the day's per-client summary into each client's Notion page, not just the vault.
