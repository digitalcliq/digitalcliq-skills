---
type: skill-notes
date: 2026-09-26
status: active
tags: [skills, auto-trends, design-notes, change-log]
---

Change log and design notes for the `auto-trends` skill ([[DigitalCLIQ]] monthly Southern California market report). Runtime code lives in the skills-plugin runtime; `~/Desktop/Skills` and `~/Desktop/digitalcliq-skills` mirror it (all three md5-identical as of 2026-09-26). The scheduled prompt is `~/.claude/scheduled-tasks/auto-trends-monthly/SKILL.md`.

## 2026-09-26 audit (read-only, no code changed)

A nine-agent audit covered the generator, the pipeline, output quality, the release calendar, and token cost. It ran three redesign angles and an adversarial critic. Full result: `~/.claude/projects/-Users-drewmoon-Desktop-DigitalCLIQ-Brain-HQ/de738d9a-175e-4e7e-8a31-d257b0418f45/subagents/workflows/wf_c417c595-abb/journal.jsonl`.

**Baseline (2026-09-09 run):** about 1.21M tokens and 105 min in total.
- Research: 551k tokens across 5 lanes and 183 tool calls, with overlapping pulls of Cox fixed ops, CNCDA and Manheim.
- Main loop: about 460k tokens, including 55 page-image reads at about 2.5-2.8k tokens each.
- Reviewer: 200k tokens over 2 passes.

**Verified gaps still open in today's code:**
- `generate_trends_report.py:247` assigns `nv_regional` and never uses it. All 6 SoCal new-vehicle metrics are researched and never printed, and `validate_claims.py` hard-codes the matching limit of 0.
- The used-vehicle "SOUTHERN CALIFORNIA" row can print national proxies. There is no `geo` gate.
- About 30 length budgets live only in code, and the schema never states them. On 9/9, 36% of the written callout and outlook prose was cut at render (8,483 characters written, 5,390 printed). `_trim` drops the last sentence, which is where caveats sit.
- The researched `trend` field (37 of 43 stats) is never rendered, and there is no month-over-month view. The exec lanes reprint strategic items 1-2.
- `generate_blog_assets.archive_json` opens the month file in `"w"` mode with no existence check, which is how the 9/9 run overwrote the 9/5 edition. `Market-Read.md` and `README.md` are rewritten the same way.
- The archives (2026-07/08/09) carry no `url`, `published` or `period` on any of their 43 stat objects. October has to become the structured baseline; period-checked month-over-month comparisons start in November.
- GM/Chevrolet is never researched, although CHC is a client.
- `allowed-tools` lacks WebFetch and any `curl`/`mkdir`/`diff`/`cp`.
- The PDF's embedded title is the temp filename (`tmphmsa6nt1.html`).
- The September PDF never mentions the CARS Act (effective 2026-10-01), and pricing, payment and tax recommendations carry no Rule 24 line.

**Release calendar finding:** the 5th has fresh data for about 5 of 13 monthly series. KBB/Cox ATP lands on the 7th business day, Cox inventory on the 10th-14th, and CPI Oct 14 / Nov 10 / Dec 10. The 15th has about 11 of 13; CA EDD and Fitch come later. Two-stage option: a Market-Read flash on the 2nd business day, then the full report on the 15th. Remaining 2026 FOMC dates: Oct 27-28 and Dec 8-9.

**Decisions pending [[Drew Moon]]:**
- Run day, or the two-stage pattern.
- Light cover per [[Design-System]] §2.
- A Rule 17 amendment if a pixel-identical re-render is to count as the confirm pass.
- A 10th page if the what-moved table, the SoCal grid and the scorecard are all added.
- Market-Read format. `monthly-client-report` cites its section headings and its Source column, so any change has to migrate that skill too.
