---
type: index
status: active
tags: [skills, catalog, automation]
updated: 2026-09-23
---

Vault-facing catalog and docs for [[Drew Moon]]'s custom Claude skills. **Runtime location: the `anthropic-skills` plugin on Drew's Claude account** (skills are invoked as `/{skill-name}` from any session in this vault). The one exception is `second-brain-optimizer`, which is locally hosted at `.claude/skills/second-brain-optimizer/` (with the shared `post_flight.py` beside it). The old claim that 22 skills live under a vault `.claude/skills/` folder is retired: that was true through July 2026, but the runtime set moved to the plugin when the vault was renamed to `DigitalCLIQ Brain HQ` on 2026-08-16 (see [[Context/vault-facts]]).

> [!tip] How to invoke
> Type `/{skill-name}` in any Claude Code session running from this vault, or describe the task in natural language and the skill will trigger if the description matches.

## Where skill content lives

Skill material lives in five places, each with one role. Do not let copies drift (the `.agents/skills` mirror had to be archived 2026-07-13 for exactly that).

| Location | Role |
|---|---|
| Root `Automotive Intelligence Skill/` and `Second Brain Optimizer Skill/` (git repo) | Editable source of truth for those skill packages. Edit here, then sync to the installed plugin copies. |
| `anthropic-skills` plugin (Drew's Claude account) + `.claude/skills/second-brain-optimizer/` | Installed runtime. What actually executes when a `/{skill}` fires. |
| `Skills/{skill-name}/` (this folder) | Vault-facing docs: catalogs, design notes, change logs, examples. Never runtime code. |
| `~/Desktop/digitalcliq-skills` (git repo, private GitHub target `digitalcliq/digitalcliq-skills`) | Backup and share point for all 21 custom skills plus agents. `main` = runtime snapshot, `desktop-source` = 2026-09-23 snapshot of `~/Desktop/Skills`. Refresh with `sync.sh` after any skill change. |
| Zip snapshots (`Skills.zip`, `outputs/second-brain-optimizer.zip`) | Disposable point-in-time backups, archived 2026-08-30. Never edit or restore from them without checking the live copies first. |

## Local doc folders

The seven subfolders that actually exist here, each holding design notes and change logs for its skill:

- [[Skills/ai-team/notes|ai-team]]: the AI night-shift team (Magic lead, Kobe GA4, Shaq Google Ads, Worthy SEO/GEO/AEO, Nick CRM) on Claude Code agent teams. Locally hosted at `.claude/skills/ai-team/` with player definitions in `.claude/agents/`. Triggers: `/ai-team dry-run`, `/ai-team shift`, "run the team", "tip off". Started from the terminal by `scripts/tipoff.sh`, not from the desktop app.
- [[Skills/blog-content/notes|blog-content]]: blog + landing-page engine for any brand; voice research, SEO/AEO engineering, Magnific heroes, branded Word docs + Excel tracker.
- [[Skills/daily-work-log/notes|daily-work-log]]: end-of-day sweep across every connected surface into the root Daily note + per-client context logs.
- [[Skills/mcpeeks-site-watch/notes|mcpeeks-site-watch]]: twice-weekly mcpeeks.com compliance/accuracy/health watch; GM-facing branded Excel workbook since 2026-09-04 (Summary, Fix List, Scorecard, detail tabs, Phone Checklist, What Changed).
- [[Skills/monthly-client-report/notes|monthly-client-report]]: branded monthly performance PDF per client (GA4, paid, Semrush, CRM vs NADA, reputation, wins).
- [[Skills/nightly-notes/SKILL|nightly-notes]]: the scheduled evening daily-log task (v2 prompt at [[Resources/prompts/nightly-daily-log-prompt-v2-2026-07-24|nightly-daily-log-prompt-v2]], mileage reconstruction included). Holds a `SKILL.md` rather than `notes.md`.
- [[Skills/social-media-manager/notes|social-media-manager]]: AI social manager; live baselines, 30/60/90 2x plan, Magnific assets behind the brand-lock gate, branded Excel.

## Plugin skill catalog

Runtime skills shipping via the `anthropic-skills` plugin (no local `Skills/` folder; listed as plain names on purpose, there is nothing to wikilink to):

### Reporting and analytics
auto-trends, morning-coffee, compare-weeks, dealership-forecast-tool, explain-usage

### Compliance and brand
brand-check, dealership-compliance-audit, cars-act-check, mcpeeks-site-watch, onlinereputation

### Lead and salesperson scoring
score-leads, score-salespeople

### Paid media and inventory
dealership-paid-media-audit, monthly-leasing, inventory-pulse

### Content and social
blog-content, social-media-manager

### Operations and logging
daily-work-log, morning, schedule, consolidate-memory

### Vault and OS tooling
os-optimizer, os-operator, os-setup, os-mcp, skill-creator, setup-cowork

### Document engines
docx, pdf, pptx, xlsx

Locally hosted: **second-brain-optimizer** (`.claude/skills/second-brain-optimizer/`; source of truth in the root `Second Brain Optimizer Skill/` git repo, per the "Where skill content lives" table above).

The `marketing` plugin adds generic marketing skills (brand-review, campaign-plan, competitive-brief, content-creation, draft-content, email-sequence, performance-report, seo-audit); several of its connectors are unauthorized, which says nothing about the primary Notion connection (root Rule 21).

## Cross-Links

These skills depend on canonical vault content:

- **[[Resources/automotive-guidelines/README|Automotive Guidelines]]**, source of truth for OEM brand rules. `brand-check`, `dealership-compliance-audit`, `dealership-paid-media-audit` reference these.
- **[[Context/vault-facts|vault-facts]]**, the mandatory skill pre-flight ledger: output paths, calendar, logo rules, client/competitor names.
- **[[Context/brand|brand]]**, DigitalCLIQ's own voice + visual identity; [[Resources/design-system/README|design-system]] is the mandatory render gate (root Rule 17).
- **[[Projects/README|Projects roster]]**, active client list. Use these client names + folder paths when running per-client skills.
- **[[Context/infrastructure|infrastructure]]**, tool stack plus the live scheduled-task table.

## History

- 2026-06-05: original 11 skills migrated into the vault runtime folder; frontmatter fixed on `dealership-paid-media-audit`.
- 2026-07-23: full runtime set consolidated into the Brain vault `.claude/skills/`.
- 2026-07-31: duplicate-registration symlink deleted; single location confirmed.
- 2026-08-16: vault renamed to `DigitalCLIQ Brain HQ`; skills moved OFF the vault onto Drew's Claude account (anthropic-skills plugin) because the app had protected the old nested `.claude/skills` path. Detail in [[Context/vault-facts]].
- 2026-08-28: `second-brain-optimizer` built; vault git repo = source, plugin + `.claude/skills` copies installed.
- 2026-08-30: this catalog rewritten to match the plugin-era reality; zip snapshots archived.
- 2026-09-04: `mcpeeks-site-watch` deliverable moved from PDF to a GM-facing Excel workbook; notes folder added.
- 2026-09-14: CNCDA CARS Act Compliance Guide v1.2 and Webinar FAQ folded into every compliance skill: `dealership-compliance-audit` (rules `CA-CARS-025` to `-040`, five new deterministic checks, judgment criteria 16 and 17, legal watch), `cars-act-check` (110 inspection points, corrected citations, rewritten law and first-communication references, policy and training templates), `mcpeeks-site-watch` (24 checks), `brand-check` (California CARS Act overlay), `social-media-manager` (CARS block). Vault source: [[Resources/automotive-guidelines/cncda-cars-act-guidance]]. A `cars-act-check` source copy now exists under `~/Desktop/Skills/skills/`.

- 2026-09-23: all 21 custom skills backed up to a new git repo at `~/Desktop/digitalcliq-skills` with a `sync.sh` refresh script. Runtime copies on `main`, the drifted `~/Desktop/Skills` copy on `desktop-source`. The vault `.claude/skills/synced/` folder is a stale account download (dead Brain/Brain paths, missing fixes), never restore from it.
## Open Items

- Workshop whether to consolidate `brand-check` + `dealership-compliance-audit` into one super-audit, or keep them split. (Any resulting work item goes to [[Notion]] TASKS, root Rule 11.)
