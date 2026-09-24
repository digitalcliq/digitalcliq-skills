# Folder indexes and system files

Each `## FILE:` block below is written verbatim to its path during Phase A.

## FILE: Context/CLAUDE.md

# Context

Stable facts about the GM, the store, and the world around it. One file per subject, updated in place, never duplicated.

- `gm-profile.md`: how the GM works. Read at session start, always. The tuning file.
- `store.md`: the rooftop, the franchise, the targets, the numbers.
- `people.md`: managers and staff.
- `stack.md`: DMS, CRM, website, tools.
- `vendors.md`: agencies, ad spend, co-op.
- `market.md`: the market and comp set overview.
- `oem.md`: factory programs, incentives, allocation.
- `digitalcliq.md`: who built this system. Do not edit.

New stable fact = update the matching file. New subject = new file here, added to the routing table in root CLAUDE.md.

## FILE: Daily/CLAUDE.md

# Daily

The GM's running journal. One file per day: `YYYY-MM-DD.md`, frontmatter `type: daily-note`. Floor notes, meeting notes, numbers check-ins, decisions in motion. Append to today's note, never create a second file for the same day.

## FILE: Departments/CLAUDE.md

# Departments

One folder per department that exists at the store. Each `README.md` records who runs it, how the GM wants it structured and run, and current focus. Department process detail goes here, not in Daily notes.

## FILE: Intelligence/CLAUDE.md

# Intelligence

- `competitors/`: one file per comp-set store. Update when new intel lands.
- `meetings/`: recurring meeting agendas and formats (manager meeting, save-a-deal).
- `decisions/`: decisions made, the options considered, and why. One file per decision.
- `archive/`: anything stale but worth keeping.

## FILE: Projects/CLAUDE.md

# Projects

One folder per active initiative, `README.md` as the index (overview, status, owner, next steps). Create subfolders only when content justifies them. Completed projects move to `Intelligence/archive/`.

## FILE: Resources/CLAUDE.md

# Resources

Reusable material: checklists, templates, word tracks, frameworks. Nothing time-sensitive lives here.

## FILE: Tasks/CLAUDE.md

# Tasks

`Tasks.md` is the single task board. Open items at top, done items move down with a date. Never track tasks anywhere else in the vault.

## FILE: Tasks/Tasks.md

---
type: task-board
status: active
tags: [tasks, operations]
---

## Open

## Waiting On

## Done

## FILE: .claudeignore

.obsidian/
.git/
.DS_Store

## FILE: .gitignore

.DS_Store
.obsidian/workspace.json
.obsidian/workspace-mobile.json
