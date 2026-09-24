---
type: index
status: active
tags: [skills, catalog, automation]
updated: 2026-08-14
---

24 custom skills. Runtime location: **`~/Desktop/DigitalCLIQ Brain/DigitalCLIQ Brain/.claude/skills/{name}/SKILL.md`** (the Brain vault, home base). This is the one and only place skills live. All auto-load when Claude Code is invoked with cwd at the Brain vault root. (Original 11 migrated from `Claude Work/.claude/skills/` on 2026-06-05; the rest added June and July 2026; the full runtime set migrated from the old Desktop `DigitalCLIQ/.claude/skills/` into the Brain vault on 2026-07-23, since the Brain runtime folder had been empty and no `/skill` would fire from home.)

> [!tip] How to invoke
> Type `/{skill-name}` in any Claude Code session running from this vault, or describe the task in natural language and the skill will trigger if the description matches.

## Catalog

### Reporting & Analytics

| Skill | What it does | Default inputs |
|---|---|---|
| **[[Skills/auto-trends\|auto-trends]]** | Branded PDF automotive market trend report. New/used sales, service/fixed ops, parts trends with 6-month and 12-month outlooks. Default region: Southern California. | Optional region argument |
| **[[Skills/morning-coffee\|morning-coffee]]** | Daily executive briefing PDF for Drew. Calendar + [[Notion]] tasks + Gmail unread + live GA4 for all client dealerships + US economic + Automotive News headlines. Fans out work to 8 parallel subagents. Target: under 3 minutes. | None, runs for today |
| **[[Skills/compare-weeks\|compare-weeks]]** | Two weekly CRM lead reports side-by-side, with live GA4 overlay. Branded PDF showing what changed, why, what to do next. | Auto-detects 2 CSVs in `01_Inbox` |
| **[[Skills/dealership-forecast\|dealership-forecast]]** | Forecasting + budget optimization. CRM lead data + marketing budgets → 3-model ensemble forecast → branded Excel with vendor ROI, reallocation strategy, scenario planning. | Path to data folder |
| **inventory-pulse** | Twice-monthly (5th + 20th) competitive intel: lease/finance specials + VIN-level new inventory for client vs 3 competitors, diffed vs prior anchor run, shipped as branded Google Sheet. Clients: SBMW, MCP, NOI. Design teardown: [[Skills/inventory-pulse/Constellation-teardown\|Constellation teardown]] | Client code |
| **mcpeeks-site-watch** | Twice-weekly (Mon/Fri) compliance + accuracy + health watch for mcpeeks.com: sitemap crawl of ~390 VDPs, 21 dealer-principal checks, week-over-week diff, dated PDF to the McPeek's Drive folder. | Scheduled, or /mcpeeks-site-watch |

### Compliance & Brand

| Skill | What it does | Coverage |
|---|---|---|
| **[[Skills/brand-check\|brand-check]]** | Analyze text, graphics, images, or web pages for OEM brand compliance. Use before any creative ships. | BMW, Nissan, Stellantis (Chrysler, Dodge, Jeep, Ram). Cross-links to [[Resources/automotive-guidelines/README\|Automotive Guidelines]]. |
| **[[Skills/dealership-compliance-audit\|dealership-compliance-audit]]** | Monthly website compliance audit combining OEM brand guidelines + California advertising law + CCPA/CPRA. Excel report with severity scoring + month-over-month delta. | BMW, Nissan, CDJR, Chevrolet |
| **[[Skills/onlinereputation\|onlinereputation]]** | Live online reputation report for a dealership + 3 closest same-brand competitors. Pulls Google, Yelp, DealerRater, CarFax. Branded PDF with themes, recommendations, SEO/LLM impact, MoM delta. | One dealer name + city |

### Lead & Salesperson Scoring

| Skill | What it does | Output |
|---|---|---|
| **[[Skills/score-leads\|score-leads]]** | Score and rank lead sources from CRM e-commerce reports. 1-10 score + A/B/C/D tier. | Branded Excel scorecard. Accepts PDF, CSV, Excel input. |
| **[[Skills/score-salespeople\|score-salespeople]]** | Same methodology applied to individual salespeople. Composite 1-10 score + tier + per-rep coaching flags. | Branded Excel scorecard |

### Paid Media

| Skill | What it does | Output |
|---|---|---|
| **[[Skills/dealership-paid-media-audit\|dealership-paid-media-audit]]** | Paid media waste audit. Spend across Google Ads, Meta, Microsoft, GA4, third-party vendors, OEM co-op. Benchmarks against NADA/brand-tier LTV. Suggestions for the GM/GSM discussion. | Branded Excel workbook |
| **[[Skills/monthly-leasing\|monthly-leasing]]** | Live browser scrape of dealership websites. Extract new vehicle lease specials by brand. Per-brand Excel tabs. | Branded Excel report |

### Social & Content

| Skill | What it does | Output |
|---|---|---|
| **[[Skills/social-media-manager\|social-media-manager]]** | AI social media manager for ANY client/brand (automotive or not). Researches the brand, pulls live follower/engagement baselines across IG, TikTok, YouTube, X/Threads, Facebook/LinkedIn, builds a 30/60/90-day plan to 2x followers + interactions on 2026 mechanics (no hashtag crutch), generates hero photos/videos live via the [[Magnific]] MCP behind a brand-lock verification gate, and ships a branded Excel. Added 2026-06-24. See [[Skills/social-media-manager/notes\|design notes]]. | Branded Excel workbook + generated assets in `Projects/{code}/social-assets/` |
| **[[Skills/blog-content/notes\|blog-content]]** | Blog + landing-page engine for ANY brand. Researches the business end-to-end (site, citations, socials, reviews, competitors), distills a voice profile, and writes a batch of 3 deeply-researched pieces in the brand's own tone, each engineered to rank in Google AND get cited by AI engines (AEO/GEO). Uses live [[Semrush]] keyword/competitor data (web fallback when none), generates hero visuals live via the [[Magnific]] MCP behind the brand-lock gate, ships one branded Word doc per piece plus a branded Excel SEO/AEO tracker, and mirrors the Drive approval/re-teach loop. Added 2026-06-26. See [[Skills/blog-content/notes\|design notes]]. | Branded Excel tracker + one Word doc per piece in `outputs/`; assets in `Projects/{code}/blog-assets/` |

### Operations & Logging

| Skill | What it does | Output |
|---|---|---|
| **[[Skills/daily-work-log\|daily-work-log]]** | End-of-day sweep across every connected surface (Claude/Cowork sessions incl. code + Chrome plugin, Gmail, Calendar, [[Notion]], Drive, Slack, Apple Notes, new vault files). Analyzes and routes each item to the client it pertains to, writes a master "everything I did today" Daily note with an accomplishments quick-list for weekly/monthly rollups, and updates per-client running-context logs. Runs unattended weekdays 7pm. Added 2026-06-25. See [[Skills/daily-work-log/notes\|design notes]]. | Root `Daily/DATE.md` + `Projects/{code}/` running-context updates |

### Client Reporting & Strategy (added 2026-07-03)

| Skill | What it does | Output |
|---|---|---|
| **[[Skills/monthly-client-report\|monthly-client-report]]** | Branded monthly performance report for a client. Pulls the PREVIOUS month's GA4 traffic (incl. social referral), Google/Meta paid media, [[Semrush]] SEO, CRM lead data scored against NADA close rates, Google + Yelp reputation, and regional NADA/economic data. Surfaces "DigitalCLIQ & {client} wins this month" from vault visit notes, self-reviews, and files to the client folder. See [[Skills/monthly-client-report/notes\|design notes]]. | Tight 2-3 page branded PDF in `Projects/{code}/deliverables/` |
| **[[Skills/seo-audit\|seo-audit]]** | Comprehensive SEO audit: keyword research, on-page analysis, content gaps, technical checks, competitor comparison. Prioritized action plan split into quick wins and strategic investments. | Audit report |
| **[[Skills/performance-report\|performance-report]]** | Marketing performance report: key metrics, trend analysis, wins and misses, prioritized optimization recommendations. For campaign wraps and weekly/monthly/quarterly channel summaries. | Executive-summary report |
| **[[Skills/brand-review\|brand-review]]** | Review content against a brand's voice, style guide, and messaging pillars, flagging deviations by severity with before/after fixes. Screens for unsubstantiated claims and missing disclaimers. | Severity-ranked review |
| **[[Skills/competitive-brief\|competitive-brief]]** | Competitor research: positioning and messaging comparison with content gaps, opportunities, and threats. For battlecards and unclaimed-angle hunting. | Positioning brief |
| **[[Skills/campaign-plan\|campaign-plan]]** | Full campaign brief: objectives, audience, messaging, channel strategy, week-by-week content calendar with dependencies, success metrics. | Campaign brief |
| **[[Skills/email-sequence\|email-sequence]]** | Multi-email sequence design with full copy, timing, branching logic, exit conditions, and performance benchmarks. Onboarding, nurture, re-engagement, win-back, launch flows. | Sequence + flow map |

## Cross-Links

These skills depend on canonical vault content:

- **[[Resources/automotive-guidelines/README|Automotive Guidelines]]**, source of truth for OEM brand rules. `brand-check`, `dealership-compliance-audit`, `dealership-paid-media-audit` should reference these.
- **[[Context/brand|brand]]**, DigitalCLIQ's own voice + visual identity. `morning-coffee` and any report-generating skill should render in this style.
- **[[Projects/README|Projects roster]]**, active client list. Use these client names + folder paths when running per-client skills.
- **[[Context/infrastructure|infrastructure]]**, what tools the agency uses. Helps skills know which CRM, ad platform, etc. is in scope for a given client.

## Maintenance

- The migration on 2026-06-05 added YAML frontmatter to `dealership-paid-media-audit/SKILL.md` (was missing, would have failed to auto-load). All other skills had proper frontmatter.
- Support scripts copied alongside the skills: `.claude/skills/conftest.py`, `pre_flight.py`, `run_all_tests.py`. These are test infrastructure, not skills.
- **One location, no duplicates.** Runtime home is the Brain vault and nowhere else: `~/Desktop/DigitalCLIQ Brain/DigitalCLIQ Brain/.claude/skills/`. 22 skill folders plus four shared helpers (`post_flight.py`, `pre_flight.py`, `conftest.py`, `run_all_tests.py`) that individual skills call.
- **Start sessions at the vault root**, `~/Desktop/DigitalCLIQ Brain/DigitalCLIQ Brain`, not the outer wrapper. Then every skill registers exactly once and is invoked plainly as `/{name}`.
- From 2026-07-22 to 2026-07-31 the outer wrapper carried a `skills -> ../DigitalCLIQ Brain/.claude/skills` **symlink**. It was never a second copy (one set of files, two paths), but it made every skill register twice: once unscoped from the working directory and again as `DigitalCLIQ Brain:{name}` from the discovered nested folder. Drew asked for a single location, so the symlink was deleted 2026-07-31 and `settings.local.json` (34 permission rules) was copied into the vault `.claude/` first so starting there loses nothing. If the duplicate listing ever returns, look for a re-created symlink.
- On 2026-07-23 the runtime set was copied here from the old Desktop `DigitalCLIQ/.claude/skills/` (the Brain runtime folder had been empty, so no `/skill` fired from home). Those copies were left as a backup, not deleted.
- Skills register at session start, so a fresh session in the Brain vault is required after adding or migrating a skill.

## Open Items

- Build `compliance-check` skill referenced in [[Team/digitalcliq/Profiles/drew-moon/task-list/Tasks|Drew's tasks]]. Note: `brand-check` and `dealership-compliance-audit` already cover most of that scope. Confirm whether a separate `compliance-check` skill is needed or if those two cover it.
- Workshop whether to consolidate `brand-check` + `dealership-compliance-audit` into one super-audit, or keep them split.
