---
type: decision
status: open
date: 2026-09-16
owner: Drew Moon
department: Marketing
tags: [decision, ai-agents, agent-team, google-ads, ga4, seo, automation]
---

## Question

How does [[DigitalCLIQ]] run a five-player AI team (Lakers nicknames) that works overnight on paid search, analytics, and SEO/GEO/AEO for the active stores, talks in Slack, and hands [[Drew Moon]] a verified brief every morning, at $0 new spend?

## Context

Planned with Drew on 2026-09-16. Planned 2026-09-16; first build landed 2026-09-17 (see Build Status at the bottom). Clients in scope: [[MCP]], [[NOI]], [[SBMW]], [[NCBMW]], plus [[Atlas]] (Google Ads running through end of 2026, small budget). Drew wants work done while he sleeps, watched mainly in Slack `#ai-team` (channel id `C0C2745RULV`, created 2026-09-16), and usage kept to roughly 10% of his Max 20x plan per day. The team will eventually live on Drew's always-on Mac mini.

## Options Considered

- **Google Ads data:** Zapier (rejected, paid, built for conversion sync not audits), browser login (rejected, Google 2FA breaks unattended runs, and the built-in browser does not exist in terminal agent teams), Google Ads Scripts to Google Sheets (chosen, $0), Google Ads API + Google Ads MCP (later, $0, needs MCC + developer token approval).
- **SEO data:** Google Search Console (preferred long term, but access is not in place for the stores and takes days to get, parked), Semrush API daily (rejected, credit limits), Semrush scheduled weekly email reports into Gmail (chosen, zero API credits).
- **Team format:** Claude Code agent teams (chosen) vs separate desktop sessions vs one lead with plain subagents. Drew re-confirmed agent teams on 2026-09-17: the players must be able to talk to each other directly (GA4 sees a paid drop and asks the Ads player; Ads looks great but the CRM shows no web leads, so they work out traffic quality together). Plain subagents only report to the lead, so they were rejected.

## Decision

> [!important] Core decision
> Five players on Claude Code agent teams, Opus lead with Sonnet workers, $0 new spend, no browser work, data through scripts and drops, players huddle directly with each other, and only Magic talks to [[Drew Moon]].

**Roster** (Lakers):

| Player | Model | Role |
|---|---|---|
| Magic (#32) | Opus 5 | Lead / point guard. Assigns work, verifies every claim against source, bounces bad work, runs the compliance gate, writes the morning brief. Only agent that talks to Drew. |
| Kobe (#24) | Sonnet 5 | GA4 for MCP, NOI, SBMW, NCBMW, Atlas. Traffic health, engagement, source contribution, click paths, AI-engine referrals. Feeds Shaq (paid) and Worthy (organic). |
| Shaq (#34) | Sonnet 5 | Google Ads for NOI, MCP, Atlas. Diagnoses and recommends. Builds or changes only on Drew's explicit "go", executed the following night. |
| Nick Van Exel (#9) | Sonnet 5 | CRM for NOI, SBMW, NCBMW, MCP. Closes the loop from click to lead to sale. Detail below. |
| Worthy (#42) | Sonnet 5 | SEO/GEO/AEO for MCP, NOI, SBMW, NCBMW (Atlas monitored, no weekly content). Two pieces per automotive store per month via the `blog-content` skill (8/month, roughly 2/week across all stores). Quality over volume: deep, detailed, fully researched pieces. Changed from 2/store/week on 2026-09-16 per Drew. Also runs the Future Rank Radar (below). |

**Nick Van Exel (#9), CRM, fifth starter (role talked through 2026-09-16):** closes the loop from click to lead to sale. Ads, GA4, and SEO only matter if they become CRM leads. Stores and CRMs: [[NOI]] VinSolutions, [[SBMW]] MomentumCRM, [[NCBMW]] Reynolds & Reynolds FOCUS, [[MCP]] Tekion. [[Atlas]] out of scope (no CRM visibility). Daily reports during the week, covering leads, appointments, shows, sold, lead source, model.
- **Watch list:** lead source swings (vs trailing 4-week average), third-party vendor ROI (cost per lead, cost per sale), models not generating leads, models generating leads over and over (demand signal handed to Shaq for campaigns and Worthy for content), website form and call counts (Kobe) reconciled against CRM leads to catch leaks, cost per sale per Google Ads campaign (Shaq), organic lead contribution (Worthy), per-store lead source mapping table, NADA close-rate benchmarks via `score-leads` / `compare-weeks` logic. Manager-level framing only (Rule 23).
  - 2026-09-26 correction: close-rate benchmarks come from `score-leads` `reference/nada_benchmarks.json` (`close_rate_benchmarks`); `compare-weeks` has no benchmark logic.
- **Spend data (Drive, DigitalCLIQ files):** `Sterling BMW 2026 Marketing Budget` (`1S3JeQUkHrXsVLJEvWojYtT8e5-cNRJWbBPgqHqRDjho`), `New Century BMW 2026 Marketing Budget` (`1SPV5x_LjuwHQqERWYlwC08I2Pn0hRM5plzlQNRsHO1c`), `McPeek Dodge 2026 Marketing Budget` (`1Qd4CwwHsiE-hAEYuW-1IR0KHgJ-xFUQEuBMctj3Q3xk`). Ignore `Copy of Sterling BMW 2026 Marketing Budget`. No NOI budget sheet found yet. Prior ROI work: `New_Century_BMW_Lead_ROI_July_2026`, `DigitalCLIQ_SBMW_3rd_Party_Lead_ROI_2026-07-22`.
- **Email reports ($0):** a free Google Apps Script in Drew's Gmail saves CRM report attachments from labeled emails into per-client Drive folders around midnight; Nick reads them via Drive. Replaces the Zapier attachment step.
- **FOCUS hurdle (NCBMW):** Drew has access but no scheduling rights, and pulling a report requires a CAPTCHA, so no agent can pull it (agents never solve CAPTCHAs). Path: ask the store's FOCUS admin or Reynolds support to schedule a daily lead/sales report email to Drew; check whether Mastermind can send it. Until then, manual drop (below).
- **Manual fail-safe (any store):** Drew drops the export (CSV, XLSX, or PDF) into a Drive `CRM Drop/{store}` folder from laptop or phone, or forwards it to himself under the CRM report label. Next shift picks it up and backfills missed days. Nick tracks last-report-received per store; a missing or reformatted report is called out in the brief as "no data since {date}", never estimated or guessed.
- **PII rule:** CRM exports hold customer names, phones, emails. Slack `#ai-team` gets aggregates only, never customer-level data. Raw exports stay in Drive / client folders.

**Magic as the rulebook (defense):** Magic owns brand guidelines, federal and California ad law (CARS Act), and the Stellantis Covenant for every automotive store.
- **Current rule homes (4, drift risk):** vault `Resources/automotive-guidelines/` (PDFs + quick references), the `brand-check` skill (`brands/*.md`), the `dealership-compliance-audit` skill (`brands/*_guidelines.json` for BMW, Nissan, CDJR, Chevrolet, HD), and `cars-act-check` (`config/rules.json`). The skill copies live inside the Claude app's plugin folder and can be overwritten on update. Build step: make the vault folder the single master and have skills read from it.
- **Factory doc intake:** Drew drops OEM PDFs or slides in Slack (DM Magic or `#ai-team`) or `01_Inbox/factory/`. Magic reads it next shift, posts a Factory Update (what changed, effective date, which stores, old vs new), and briefs each player on what it means for them: Shaq (ad copy, co-op, bidding rules), Worthy (content claims, model facts, radar), Nick (incentive-driven lead mix), Kobe (landing pages and tracking). Magic drafts the rulebook change; Drew approves before it becomes the rule, because a wrong rule silently breaks every compliance check. Source PDF filed to `Resources/automotive-guidelines/`. Order of authority unchanged: federal, then California, then OEM, stricter wins.

**Future Rank Radar (Worthy, weekly):** scout topics that barely get searched today but will get pushed hard later, and stake a claim early. Drew's example: BMW's Neue Klasse platform, little content and low search volume now, heavy OEM push coming. Sources: OEM press rooms and product roadmaps, auto trade news, free Google Trends, Semrush keywords with low but rising volume, and thin or missing AI-engine answers. Each idea carries: store fit, the evidence it is coming, a why-now, expected timing, and current competition. Kept in a running backlog in the vault, reviewed in Friday's wrap. Magic verifies every factual claim (launch dates, availability, specs) against an OEM or primary source before it reaches Drew. Drew picks which radar ideas become one of a store's two monthly pieces. Pieces on unreleased vehicles never imply availability, pricing, or delivery dates the OEM has not announced (federal and CA ad rules).

**Compliance gate (Magic, every automotive store):** federal FTC Act / Reg Z / Reg M first, then California (CARS Act SB 766, effective 2026-10-01, plus CA ad law), then the store's OEM rules: BMW for SBMW and NCBMW, Nissan for NOI, the Stellantis Marketing Covenant for MCP (not filed in the vault as of 2026-09-17; until Drew drops it, MCP reviews use `Resources/automotive-guidelines/cdjr-quick-reference.md` and say the covenant was not checked). Atlas gets general FTC truth-in-advertising review. Rule 24. (The original plan also cited a Rule 25; `Context/rules.md` has no Rule 25 as of 2026-09-17.)

**Schedule:** Mac mini launches the team (an interactive Claude Code session, because agent teams cannot spawn teammates in headless `-p` mode) at 1:00am Pacific, Mon to Fri, hard stop 5:00am. Brief posted to `#ai-team` by 5:00am with Drew tagged, and appended to root `Daily/`.

> [!note] Amended 2026-09-19 ([[Drew Moon]], during the first dry run)
> The shift runs as long as the work takes and not a minute longer: it ends when the brief posts, hard cap 120 minutes from the 1:00am tip-off, so the brief lands by 3:00am at the latest. Roster grows to five players with Luka Doncic (#77) on Meta Ads through the read-only slice of the Meta Ads connector. Slack posts must read like a teammate talking ("Talk like a teammate" in the huddle protocol); the first dry run's channel was a data dump Drew could not follow. The Mon to Fri launcher is not scheduled until Drew reads the dry-run brief and says so. Monday covers Fri to Sun. Monday also = Semrush weekly review. Content: about 2 pieces a week across the 4 stores, each store getting one piece every other week.

**Data paths ($0):** Google Ads Scripts write nightly data to Sheets, read via Drive. GA4 Data API. Semrush weekly emails into Gmail. Search Console added per store as access lands.

**Approved Ads changes:** Drew says "go" in Slack. Next night Shaq writes the approved change to an "Approved Changes" sheet; an executor Ads Script applies it with guardrails (preview first, capped budget moves, full log), and Shaq confirms in change history the night after. New campaign builds use Ads Scripts bulk upload or wait for the API.

**Slack identity:** for the dry run, ONE free Slack app (`AI Team`, scopes `chat:write`, `chat:write.customize`, `channels:history`) posts as each of the five players with its own display name and jersey avatar. Target state if Drew wants real @mentions: five free Slack apps (Magic, Kobe, Shaq, Worthy, Nick), each a real bot user with its own name, avatar, and @mention, posting with bot tokens instead of Drew's connector. Bot users are not billable seats. Avatars use jersey numbers in purple and gold, not player photos.

**Second watch mode:** live terminal split panes on the Mac mini, viewable from the laptop over Screen Sharing or SSH. Vault keeps the permanent log.

**Tasks:** team proposes Notion tasks in the brief, never creates them (machine-created tasks rule).

## Reasoning

$0 path per Drew ("I dont want to pay for anything I dont already pay for"). Scripts and email reports remove browser work, which is the main breakage and token risk for unattended runs. Sonnet workers with an Opus lead keep usage down while keeping the skeptic strong. Overnight run keeps work off Drew's day and out of weekday peak hours, when Anthropic has tightened session limits and capacity is tightest.

## Consequences

- **Token risk:** content dropped to 8 pieces/month, so Worthy can spend more research depth per piece and still stay inside ~10%/day. Pilot week measures usage. Depth is not the place to cut.
- **Agent teams is experimental** in Claude Code; pilot before trusting.
- **Unattended runs need a pre-approved tool allowlist** or the run stalls on a permission prompt at 1am.
- **Mac mini shares Drew's Max usage pool** with daytime work.
- **Open items:** Atlas Google Ads CID and login, Semrush projects for all 5 domains, Semrush plan supports scheduled email reports, Search Console access per store, Slack app creation (Drew installs).
- **Rollout (revised 2026-09-17):** Phase 0 access (Drew's setup steps), Phase 1 one ATTENDED dry run of the full five-player team on the laptop (Drew's call, replaces solo-agent testing), tweak, Phase 2 first unattended night, Phase 3 Mac mini pilot week, Phase 4 Google Ads API.

> [!warning] Known risks
> Agent teams is experimental and cannot run headless, so the 1:00am launch must open a live terminal session. There is no documented token or time cap for a team; the 5:00am kill and per-player scope limits are the only brakes. Google OAuth logins on an External app in Testing status expire every 7 days (use Internal, or publish the app). The Google Ads export script is untested until Drew's first Preview run.

## Build Status (2026-09-17)

Readiness check on Drew's laptop found: no Claude Code CLI installed (desktop app only), no tmux or Homebrew, no GA4 API credentials (GA4 had been reaching Claude through Zapier), only the [[MCP]] Google Ads CID on file ([[NOI]] and [[Atlas]] CIDs missing), and `#ai-team` is a public channel.

Built the same day, all under `.claude/skills/ai-team/` with notes at [[Skills/ai-team/notes]]:
- `SKILL.md`: Magic's playbook, `/ai-team dry-run` and `/ai-team shift`.
- `.claude/agents/kobe.md`, `shaq.md`, `worthy.md`, `nick.md`: player definitions, Sonnet.
- `references/huddle-protocol.md`: mandatory player-to-player triggers, the three-way traffic-quality huddle (Shaq, Kobe, Nick), three round trips then escalate, every huddle mirrored to a Slack thread.
- `scripts/gdata.py`: one read-only Google login for GA4, Sheets, and Drive, standard library only. `ga4-nightly` pre-computes channel flags (target day vs trailing 4-week same-weekday average) so the players spend tokens on judgment, not pulling.
- `scripts/slack.py`: posts as each player, reads Drew's replies, refuses any text that looks like a customer phone or email.
- `scripts/ads_export.gs`: read-only Google Ads Script to Sheets.
- `scripts/tipoff.sh`: interactive launcher. `references/setup.md`: Drew's hands-on steps.
- [[Intelligence/market/future-rank-radar]]: radar backlog.

Dry-run scope: Kobe all five GA4 properties, Shaq only stores with an export Sheet, Nick whatever is in `CRM Drop/`, Worthy organic check plus radar plus topic briefs (no full piece), Magic verifies, gates, briefs to Slack and `Daily/`. Deferred: Gmail Apps Script for CRM emails, Semrush weekly emails, Approved Changes executor, rulebook consolidation, factory doc intake, Mac mini, Google Ads API.

