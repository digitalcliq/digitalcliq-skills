# DigitalCLIQ Skills

Custom Claude skills built by Drew Moon for DigitalCLIQ, an automotive marketing agency. This repo is the backup and share point for all of them.

## What's here

| Folder | Contents |
|---|---|
| `skills/` | One folder per skill, each with its `SKILL.md` plus scripts, references, and assets. |
| `agents/` | Subagent definitions: the ai-team players (Kobe, Shaq, Luka, Worthy, Nick) and the deliverable-reviewer QA agent. |
| `shared/` | `post_flight.py`, the shared output validator several skills call. |
| `docs/` | Design notes and change logs from the vault's `Skills/` folder. Reference only. |
| `sync.sh` | Re-snapshots every skill from where it actually runs, commits, and pushes. |

## Skills

**Reporting and analytics**
- `auto-trends`: branded PDF automotive market trend report, Southern California default.
- `morning-coffee`: daily executive briefing PDF (calendar, tasks, CRMs, GA4, Meta, Semrush, headlines).
- `compare-weeks`: week-over-week CRM lead comparison with a GA4 overlay, PDF.
- `dealership-forecast-tool`: 3-model lead forecast and budget scenarios, Excel.
- `monthly-client-report`: 2 to 3 page monthly performance PDF per client.

**Compliance and brand**
- `brand-check`: OEM brand guideline review (BMW, Nissan, Stellantis, Chevrolet, Harley-Davidson).
- `dealership-compliance-audit`: monthly website audit covering OEM rules, California ad law, CCPA, ADA, TCPA, FTC. Excel.
- `cars-act-check`: California CARS Act (SB 766) suite with 110 inspection points.
- `mcpeeks-site-watch`: Mon/Fri compliance and health watch for one dealer site, GM-facing Excel.
- `onlinereputation`: Google, Yelp, DealerRater, CarFax reputation PDF against 3 competitors.

**Lead and salesperson scoring**
- `score-leads`: lead source scorecard with NADA close-rate benchmarks, Excel.
- `score-salespeople`: salesperson performance scoring.

**Paid media and inventory**
- `dealership-paid-media-audit`: paid media waste audit across Google, Meta, Microsoft, GA4, Excel.
- `monthly-leasing`: live lease specials by brand, Excel.
- `inventory-pulse`: twice-monthly competitive inventory and offer diff, Google Sheet.

**Content and social**
- `blog-content`: 3 researched SEO and AI-search pieces in a brand's voice, Word docs plus Excel tracker.
- `social-media-manager`: baselines, 30/60/90 plan, generated assets, Excel.

**Operations and team**
- `daily-work-log`: end-of-day sweep of everything done across connected tools into the daily note.
- `nightly-notes`: scheduled evening daily-log task prompt.
- `ai-team`: night-shift analyst team on Claude Code agent teams, briefs Drew in Slack each morning.

**Vault tooling**
- `second-brain-optimizer`: 5-pass audit and tune-up for an Obsidian vault. Also lives in its own repo, `digitalcliq/second-brain-optimizer`.

## Where each skill runs

- Most skills run from the `anthropic-skills` plugin on Drew's Claude account. The live copy sits in `~/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/.../skills/`.
- `ai-team`, `second-brain-optimizer`, and the agents run from the vault's `.claude/` folder.
- `nightly-notes` is a prompt kept in the vault's `Skills/` folder.

A plugin re-sync can overwrite the runtime copy with an older version from the account. After any re-sync, compare the runtime against this repo before running a skill, and restore from here if fixes went missing.

## Keeping the backup current

```bash
~/Desktop/digitalcliq-skills/sync.sh
```

Run it after any skill change. It copies each skill from where it runs, commits only if something changed, and pushes.

## Branches

- `main`: the runtime copies, which are what actually executes.
- `desktop-source`: a 2026-09-23 snapshot of the `~/Desktop/Skills` source copy. It drifted from the runtime in both directions, so it's kept separately rather than merged blind.

Files where `desktop-source` was newer than `main` on 2026-09-23 and need a manual reconcile:
- `auto-trends/generate_trends_report.py`
- `dealership-forecast`: a restructured version with `dealership_forecast.py` and tests
- `monthly-client-report/generate_monthly_report.py`
- `inventory-pulse/scripts/merge_extract.py`
- Shared test harness: `pre_flight.py`, `conftest.py`, `run_all_tests.py`

## Before sharing outside DigitalCLIQ

This repo is private for a reason. Before sharing a skill with someone outside the company, or making the repo public, strip these out:
- `history/` and `runs/` folders, which hold month-over-month audit results for named client dealerships.
- Client configs such as `inventory-pulse/config/clients.json` and `monthly-client-report/reference/client_registry.json`.
- Hardcoded vault paths under `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/`, which won't exist on another machine.

No API keys or tokens are stored in this repo. The ai-team scripts read Slack and Google credentials from `~/.config/digitalcliq-ai-team/` and environment variables.
