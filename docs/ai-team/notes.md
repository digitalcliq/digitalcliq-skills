---
type: skill-notes
date: 2026-09-17
department: Marketing
status: active
tags: [skill, ai-team, agent-teams, automation, slack]
---

Design notes and change log for the [[ai-team]] skill, [[DigitalCLIQ]]'s AI night-shift team: Magic (#32, lead, Opus), Kobe (#24, GA4), Shaq (#34, Google Ads), Worthy (#42, SEO/GEO/AEO), Nick Van Exel (#9, CRM), all workers on Sonnet. Decision record: [[Intelligence/decisions/2026-09-16-ai-agent-team]]. Catalog entry: [[Skills/README]]. Runtime is locally hosted at `.claude/skills/ai-team/`; player definitions live in `.claude/agents/`.

## Design choices that are easy to undo by accident

- **Agent teams, not subagents.** [[Drew Moon]] was explicit on 2026-09-17: the players have to talk to each other. Plain subagents only report to the lead. The skill refuses to fall back.
- **Slack is the floor.** Drew's rule, 2026-09-17: he monitors the team in `#ai-team`, so every player-to-player message, every Magic assignment and bounce, and each player's checkpoints are posted to Slack FIRST, in full, and only then sent through agent-teams messaging, which is just the buzzer that wakes the teammate. Slack cannot be the transport itself: a player would have to poll the channel, which burns usage and adds lag. Enforcement is by instruction plus Magic's off-channel audit at the final whistle, not by code, so check the first dry run's threads against the findings files.
- **CRM data comes from the `Morning_CRM` Gmail label, not from Drew.** Drew's rule, 2026-09-17: he will not fetch files for the team or he becomes the bottleneck. Each CRM emails its scheduled report to Drew, the filter labels it, and `gdata.py mail-ls` / `mail-get` read it with the same Google login (gmail.readonly scope added). Inbox audit that day: SBMW MomentumCRM nightly PDF is live but stopped after 9/12; NCBMW has BMW NA lead-conversion emails, no FOCUS export; NOI (VinSolutions) and MCP (Tekion) have nothing scheduled yet; the label filter also catches unrelated threads. The Drive `CRM Drop` folder stays as the fallback only.
- **Interactive launch.** Agent teams cannot spawn teammates in headless `-p` mode, so `scripts/tipoff.sh` opens a live `claude` session with `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`. It does not run from the desktop app or a desktop scheduled task.
- **No connectors in the data path.** GA4, Sheets, and Drive all go through `scripts/gdata.py` with one read-only Google login, because claude.ai connectors in the terminal CLI are not documented and a browser breaks unattended runs.
- **Secrets outside the vault.** `~/.config/digitalcliq-ai-team/` holds `slack.env`, `google_client.json`, `google_token.json`. CRM downloads go to `~/.cache/digitalcliq-ai-team/crm/` and are purged at the final whistle.
- **Scripts do the arithmetic.** `ga4-nightly` computes channel flags (25% move vs the trailing 4-week same-weekday average, 20-session floor) so tokens go to judgment.
- **Slack PII guard.** `slack.py` refuses text that looks like a phone number or email. It will also refuse a Google Ads CID, which is intended.
- **One Slack app, five voices.** `chat:write.customize` sets the name and jersey emoji per post. Avatars are in `assets/avatars/`.

## 2026-09-17: first build

Built for a one-day attended dry run. Untested until Drew finishes `references/setup.md`: the Google login, the Slack token, and the Ads export script (its first Preview run in the Ads UI is the test). Offline tests passed for flag math, the PII guard, and the Slack markdown conversion.

Open items: [[NOI]] and [[Atlas]] Google Ads CIDs and export Sheet ids (table in `references/data-sources.md`), the Stellantis Marketing Covenant is not filed in `Resources/automotive-guidelines/`, no NOI budget sheet, Search Console access, Gmail Apps Script for CRM report emails, Approved Changes executor, 1:00am launcher and 5:00am kill for the Mac mini, permission allowlist to be finished from the dry run's shift log.

## 2026-09-19: first dry run, and three changes from Drew mid-run

The first attended dry run tipped off about 8:55 AM Pacific from `tipoff.sh dry-run` in a terminal tab (Cowork session was not started with agent teams, so it could not host the team itself). Pre-flight fixes the same morning: Google Ads exports installed on [[MCP]], [[NOI]], and [[Atlas]] and moved to `Shared Drive / Internal / Ads Exports`; the night-shift Google token re-consented with the Gmail scope it never had; the Gmail API enabled on the Cloud project. `mail-ls` then returned NOI VinSolutions (9/17 to 9/19) and SBMW MomentumCRM (9/18).

Drew's changes while it ran, all applied for the next run:

- **Talk like a teammate.** The channel read as a data dump. New section at the top of `references/huddle-protocol.md`, a rewritten `references/brief-template.md` in Magic's voice, and Magic now bounces a dump the same as a wrong number. Tables and raw numbers live in the findings files; Slack gets the point, two to five lines, three numbers max.
- **Luka Doncic (#77), Meta Ads.** `.claude/agents/luka.md`, a "Meta Ads (Luka)" lane in `references/data-sources.md`, a sixth voice in `slack.py` (`:basketball:`, `luka77.png`), Luka in every teammate line and huddle trigger. Data path is the claude.ai Meta Ads connector, which `claude mcp list` shows connected in the CLI. Guardrail: `.claude/settings.json` no longer denies the whole Meta server; it denies the 39 tools that can create, update, delete, activate, boost, or upload, by name. First live read is on the next run; if the CLI session cannot reach the connector, Luka reports "no data" and the fallback is a `gdata.py`-style script on a Meta system-user token.
- **The clock.** No more 1:00am to 5:00am. The shift ends when the brief posts, hard cap 120 minutes from the 1:00am tip-off. `SKILL.md`, `setup.md`, and the decision record carry the amendment. Nothing is scheduled until Drew reads the dry-run brief.

Still open: SBMW MomentumCRM email skipped 9/19 (Drew is checking whether it only sends weekdays); NCBMW and MCP CRM feeds; the Mon to Fri launcher; the permission allowlist from this dry run's shift log; custom jersey emoji not yet uploaded to Slack.

## 2026-09-19, afternoon: five more changes from Drew after reading the brief

- **Semrush did not reach Worthy.** Docs say teammates load MCP servers from project and user settings; claude.ai connectors are undocumented for teammates and did not propagate on 9/19. Fix: `semrush` and `meta-ads` registered as user-scope MCP servers (`claude mcp add --scope user`, HTTP transport). Drew authenticates both once with `/mcp` in the next tipoff session. Players run a ToolSearch before calling a connector missing (tools are deferred). Fallback ladder for Semrush in `references/data-sources.md`, last rung is Magic reading semrush.com in Drew's signed-in Chrome (`tipoff.sh` now passes `--chrome`), read only, never a credential. Teammates cannot drive Chrome, so the browser rung is Magic's alone.
- **Luka on the (MAIN) account.** Confirmed from the desktop session: `(MAIN)932166720307788`, business Digitalcliq, active and queryable. The `mcpeek ads` account (McPeek Dodge business) is also visible and stays out of scope. The 39 write-tool denies now cover both server names (`mcp__ead459fc…__` and `mcp__meta-ads__`). Number 77 is right (he kept it with the Lakers). Icon: Slovenia flag (`:flag-si:`), avatar `luka77.png` is the tricolor with 77. The Nike L7 mark is a trademark, so it stays off the Slack app.
- **Nick is CRM only.** New section at the top of `nick.md`: no GA4, Ads, Meta, or SEO pulls, ever; web numbers come from Kobe in a huddle; thin data means freshness, gaps, source mapping, dupes, and the exact report ask that would fill each gap. On 9/19 he had been running GA4 event pulls with Kobe, which is off-lane.
- **Report to Magic.** Every player ends with `## Report to Magic` (working, not working, one suggestion per problem, a source when they can name one) and posts it in three lines to `#ai-team`. The brief gained **Action items** (owner, action, evidence, cost of skipping, approval state), **What the players say**, and **Shift stats**.
- **Time and tokens.** New `scripts/usage.py` reads the lead and teammate transcripts and prints minutes and tokens per player (`--md` for the brief). On the 9/19 dry run: 12 to 16 minutes per player, 93.2M tokens all-in, of which 90.5M were prompt-cache reads and 2.35M fresh input; Shaq was the heaviest (27.9M), Worthy the lightest (11.9M). Caveat from the docs: transcript format is internal and can change between releases, so if the script breaks after an update, fall back to `/usage` in the session.

## 2026-09-19, late morning: the 1:00am launcher is built and armed

Drew's call: fully automated, "if I had employees I wouldn't need to wake up to let them into a building." Built and tested the same morning:

- **launchd job** `~/Library/LaunchAgents/com.digitalcliq.ai-team.plist`, Mon to Fri 1:00am, runs `~/.config/digitalcliq-ai-team/launch-shift.sh`. The launcher has to live outside the Desktop: launchd's shell cannot read the vault (macOS shields Desktop from background processes), so the launcher opens Terminal.app with osascript and Terminal runs `tipoff.sh` from the vault. The vault copy `scripts/launch-shift.sh` is the source; re-copy it to the config folder after any edit.
- **One-shot override** `~/.config/digitalcliq-ai-team/next-mode`: if present, its contents replace `shift` (for example `dry-run Nick: NOI only`, or `test`) and the file is deleted on read. `test` mode proves the path without starting the team; the 10:34 kickstart logged "launcher path OK".
- **tipoff.sh** now runs the session with `--permission-mode dontAsk` in shift mode (never stalls; anything off the allowlist is denied and shows in the shift log) and `auto` in dry-run; passes `--chrome`; appends extra words to the `/ai-team` command so Magic gets Drew's instructions; and a watchdog closes the session two minutes after the shift log's final whistle or at a 150 minute cap.
- **Allowlist** in `.claude/settings.json` (39 rules: the scripts, python3, read-only shell, Read, ToolSearch, Write and Edit under `outputs/`, `Daily/`, `Intelligence/market/`, the team tools, and the Semrush and Meta servers with the 94 denies still on top). The classifier would not let Claude edit its own permissions or a LaunchAgent, so Drew ran the copy and the plist repoint himself.
- Log: `~/Library/Logs/digitalcliq-ai-team.log`. Disarm: `launchctl bootout gui/$(id -u)/com.digitalcliq.ai-team`. Re-arm: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.digitalcliq.ai-team.plist`.

First armed slot: Monday 2026-09-21 1:00am, shift mode, Monday scope (Fri to Sun). Second attended dry run (six voices, Nick on NOI CRM only, Luka's first read) started 10:33am the same day.

Bug caught 10:40am the same day: the tipoff watchdog looked for any final whistle in today's shift log, found the morning run's, and closed the second dry run before it started. Fixed: it now counts `- End:` lines at tip-off and only closes the session when a new one appears. Two runs on one date also share `outputs/ai-team/{date}/`, so a second run is told to write under `run2/`.

Semrush server URL, 10:55am: `https://mcp.semrush.com/claude/v1/mcp` is claude.ai's private path and only authenticates through claude.ai's connector page, so the user-scope copy could never sign in. Replaced with Semrush's standard endpoint `https://mcp.semrush.com/v1/mcp` (OAuth with dynamic client registration, authorization server oauth.semrush.com), which `/mcp` authenticates in a browser like Meta. Meta's `https://mcp.facebook.com/ads` worked as-is.

## 2026-09-21: first real shift, all five players hung (root cause found)

The first unattended `tipoff.sh shift` at 1:00am lost all five players within a minute of spawn. [[Magic]] ran every lane alone and still shipped the brief at 02:08, so the fallback holds, but there was no team.

**What happened.** Shift mode launches the lead with `--permission-mode dontAsk`. Teammates inherit the lead's permission mode except dontAsk, which the agent-teams docs say they do not inherit, and a teammate's permission prompts are routed to the lead's terminal for a human to answer. Each player therefore ran in a prompting mode, and the first tool call the allowlist did not auto-approve raised a prompt in a terminal nobody was at. That call is logged as a tool_use with no tool_result, and the player sits at `running` indefinitely. The frozen calls: Kobe, Nick, Shaq and Worthy on compound Bash chains (`&&`, a pipe, a multi-line script), Luka on the `Monitor` tool. The lead got instant denials for the same command shapes, which is why Magic kept moving while the players froze.

**Why we are sure.** The 9/19 dry runs under `auto` mode: 0 orphaned tool calls across roughly 1,500. The 9/21 shift: every player orphaned exactly one call, 5 to 45 seconds after spawn, after finishing its pre-reads. Magic's "pre-read stall" hypothesis in the shift log is retired.

**Applied 2026-09-21 on [[Drew Moon]]'s go (the same day, later session):**
1. `scripts/tipoff.sh` shift mode now launches with `auto`, the mode both dry runs used, not `dontAsk`. The deny list in `.claude/settings.json` still blocks every Meta write tool in either mode.
2. `usage.py --hung 5` is the new watchdog (last API call per player, exit 1 if any is idle 5+ minutes; also fixes the player-name regex that printed "Player 1..5" in the shift stats). SKILL.md step 3 tells Magic to run it every 5 minutes, TaskStop and respawn once, and take the lane on a second hang or with under 30 minutes left.
3. Every player definition in `.claude/agents/` carries a "Tool discipline" section (one plain command per Bash call, no chains, pipes, redirection, multi-line shell, Monitor or loops), and SKILL.md step 2 repeats it in the spawn prompt.
4. Bug report drafted at `outputs/ai-team/2026-09-21/feedback-claude-code.md` for Drew to paste into `/feedback` in a terminal session (not sendable from the desktop app). Untested until the next run: whether `auto` mode ever prompts a teammate; the watchdog is the safety net if it does.

Evidence lives in the session transcript `458d3175`, subagent files under `~/.claude/projects/…/458d3175-…/subagents/`.

## 2026-09-23: why Worthy never had Semrush (root cause, verified from transcripts)

[[Drew Moon]] asked why Worthy has failed on Semrush all week. Multi-agent audit of all five shift sessions, adversarially checked.

**Root cause: players get the tool list Magic had when his current turn started.** `tipoff.sh` submits `/ai-team shift` as turn 1; MCP servers (claude.ai Semrush, meta-ads, claude-in-chrome) connect 4 to 9 seconds into that turn, and Magic spawns the players in the same turn, so every player starts with 13 built-in deferred tools and zero MCP tools. Proof: Worthy and Luka had 13 tools on 9/19 dry, 9/21, 9/22 and 9/23, and 269 (14 of them `mcp__claude_ai_Semrush__*`) on 9/19 run2, the only night the players were spawned in a second turn (after Drew's `/mcp` and "go"). Same logic in Claude Code 2.1.278 and 2.1.280 (`rootToolSurface` is captured at turn start and handed to in-process teammates).

**Not the cause:** the unauthenticated user-scope `semrush` server. The user-scope `meta-ads` server is authenticated and connected in Magic's session every night and still never reached Luka. Magic's 9/23 shift log names the wrong cause.

**Second problem: wrong tool names.** In the Terminal CLI the working connector is `mcp__claude_ai_Semrush__*`. `data-sources.md` tells players to search `mcp__semrush__*`, and `.claude/settings.json` allows `mcp__781ea802…__*` (the desktop app's name) and `mcp__semrush__*`, neither of which matches. On 9/19 run2 Worthy had the 14 tools and missed them because he searched the wrong prefix.

**Integrity note:** 9/23 `worthy.md` cites a ToolSearch (`select:mcp__semrush__domain_overview,…`) that his transcript never ran; his only searches were WebSearch/WebFetch and SendMessage. The conclusion (no Semrush) was right, the cited evidence was copied from his 9/22 file. Magic's verify pass checks numbers against data files, not claims about tool calls. Other nights' cited checks match real calls.

**Other facts found the same day:**
- `usage.py` double counts: transcripts write one record per content block with the same usage repeated. Worthy 9/23 reads 7.57M tokens in the brief, 4.68M deduplicated by message id; the team is closer to 60M a night than 100M.
- Semrush plan reads as Pro or One Starter (403 on history reports), which carries a 50,000 MCP unit pool a month. Nightly pulls ran about 1,600 to 2,980 units, roughly 65,000 over a month of shifts, which is why the pool ran dry 8/13, 9/07 and 9/14. Rank history is monthly data and should be pulled monthly.
- Semrush projects exist for all five domains; Position Tracking is on for SBMW, NCBMW, NOI and Atlas, not MCP. Organic Traffic Insights (the GA4 link) and SEO Ideas are web-UI only.
- Semrush ToS (updated 2026-08-25) 3.3(p) bars scraping and 3.3(r) bars feeding Semrush output into an LLM except through Semrush's official integrations, so a browser read of semrush.com is not a safe nightly path; the MCP connector is.
- The Claude desktop Browser pane does not exist in the 1am Terminal session.
- No content piece has shipped: every piece waits on Drew's topic pick, the ask sits at the bottom of a long brief, the one assigned piece (9/21 NOI Rogue e-POWER) was cut when Worthy hung, and `blog-content` cannot run inside a teammate. Worthy's NCBMW Neue Klasse topics overlap the 9/14 pillar page from the NCBMW weekly SEO run.
- `~/.claude/skills/ai-team/` (the copy the shift actually loads) and the vault `.claude/skills/ai-team/` are separate identical folders; any edit goes to both.

Fix not yet applied; waiting on Drew's go.
