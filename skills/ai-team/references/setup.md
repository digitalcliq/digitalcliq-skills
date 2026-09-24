# Setup: the parts only Drew can do

About an hour total. Claude never types passwords, tokens, or consent clicks, so these are yours. Secrets live in `~/.config/digitalcliq-ai-team/`, outside the vault, never in a note or a prompt. That folder was created 2026-09-17; if it is ever missing, recreate it first:

```bash
mkdir -p ~/.config/digitalcliq-ai-team && chmod 700 ~/.config/digitalcliq-ai-team
```

## 0. Install the Claude Code CLI (5 min)

Agent teams only runs in the terminal CLI, and this Mac only has the desktop app.

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Then open a new Terminal window, run `claude`, and sign in with the same Claude Max account. Type `/exit` when you see the prompt.

## 1. Slack app (15 min)

1. https://api.slack.com/apps > Create New App > From scratch. Name: `AI Team`. Workspace: DigitalCLIQ.
2. OAuth & Permissions > Bot Token Scopes, add: `chat:write`, `chat:write.customize`, `channels:history`.
3. Install to Workspace. Copy the Bot User OAuth Token (starts `xoxb-`).
4. Save it yourself:

```bash
printf 'SLACK_BOT_TOKEN=%s\n' "PASTE-TOKEN-HERE" > ~/.config/digitalcliq-ai-team/slack.env && chmod 600 ~/.config/digitalcliq-ai-team/slack.env
```

5. In Slack, in `#ai-team`: `/invite @AI Team`.
6. Optional, 2 minutes, gives each player a jersey avatar: Slack > Customize workspace > Emoji > Add, upload the five PNGs in `.claude/skills/ai-team/assets/avatars/` with these exact names: `magic32`, `kobe24`, `shaq34`, `worthy42`, `nick9`.
7. Test:

```bash
cd ~/Desktop/"DigitalCLIQ Brain HQ" && python3 .claude/skills/ai-team/scripts/slack.py check
```

One app posts as all five players for the dry run. Five separate apps (each with its own @mention) can come later if you want them.

## 2. Google access for GA4, Sheets, Drive (20 min)

Use the Google account that holds the GA4 access (`drewmoon@digitalcliq.com`). Read-only scopes.

1. https://console.cloud.google.com > create a project, name it `digitalcliq-ai-team`.
2. APIs & Services > Library: enable **Google Analytics Data API**, **Google Sheets API**, **Google Drive API**.
3. APIs & Services > OAuth consent screen. User type: **Internal** if it is offered (Workspace account). If only External is offered, choose it, add yourself as a test user, then press **Publish app** so the login does not expire every 7 days. You will see an "unverified app" warning at sign-in; that is expected for a private tool.
4. Credentials > Create credentials > OAuth client ID > Application type **Desktop app**. Download the JSON and move it:

```bash
mv ~/Downloads/client_secret_*.json ~/.config/digitalcliq-ai-team/google_client.json && chmod 600 ~/.config/digitalcliq-ai-team/google_client.json
```

5. Sign in once (a browser tab opens, approve the three read-only permissions):

```bash
cd ~/Desktop/"DigitalCLIQ Brain HQ" && python3 .claude/skills/ai-team/scripts/gdata.py auth
```

6. Confirm all five properties answer:

```bash
cd ~/Desktop/"DigitalCLIQ Brain HQ" && python3 .claude/skills/ai-team/scripts/gdata.py status
```

## 3. Google Ads export script (15 min per account, MCP first)

1. Google Ads (MCP account) > Tools > Bulk actions > Scripts > + New script.
2. Paste all of `.claude/skills/ai-team/scripts/ads_export.gs`. Set `STORE_CODE`. Leave `SPREADSHEET_URL` blank.
3. Authorize, then **Preview**. The log prints `NEW SHEET ... https://docs.google.com/spreadsheets/d/...`.
4. Paste that URL into `SPREADSHEET_URL`, Save, Run once, then set Frequency: Daily, 12 AM.
5. Give Claude the Sheet URL (it goes into `references/data-sources.md`). The script only reads the account and writes that Sheet. It cannot change campaigns.
6. Repeat for NOI and Atlas when you have the CIDs handy. Those two CIDs are not in the vault yet.

## 4. CRM reports by email (no fetching, ever)

The team reads the `Morning_CRM` label in your Gmail. Each CRM has to email its report to `drewmoon@digitalcliq.com` on a schedule, and your Gmail filter has to label it. One-time setup per store, then it runs itself:

1. **Enable the Gmail API, then grant the permission** (added 2026-09-17). In https://console.cloud.google.com, project `digitalcliq-ai-team`, APIs & Services > Library > search "Gmail API" > Enable. Then re-run the login (browser opens once, approve the four read-only permissions):

```bash
cd ~/Desktop/"DigitalCLIQ Brain HQ" && python3 .claude/skills/ai-team/scripts/gdata.py auth
```

2. **SBMW (MomentumCRM):** done 2026-09-17, lands between midnight and 1:00am.
3. **NOI (VinSolutions):** done 2026-09-17, sender `reportscheduler@motosnap.com`, test received.
4. **MCP (Tekion):** Drew's login cannot schedule reports. One ask, once: have the store's Tekion admin schedule the daily lead report to `drew.moon@mcpeekcdjr.com` (Tekion often limits recipients to the dealership domain), then set a forwarding rule in that mailbox to `drewmoon@digitalcliq.com` and add the sender to the filter. Until then: export once a week on the Thursday visit and drop it in `CRM Drop/MCP`. Nick backfills the week.
5. **NCBMW (FOCUS):** no scheduling rights and a CAPTCHA on every pull, so an agent can never do it. One ask, once: the store's FOCUS admin or Reynolds support schedules the daily lead and sales report to your email. Until then Nick works from the BMW NA "Lead Conversion MTD" and RDR emails plus the Constellation weekly, and you drop a FOCUS export in `CRM Drop/NCBMW` when you can, roughly weekly. Never a nightly job.
6. **Tighten the filter:** it currently catches unrelated threads (a "RYAN ASK" CPA thread landed under it on 9/15). Match on sender addresses, not words.

Rule: no store ever holds up the shift. A missing report is reported as "no data since {date}" and the brief still ships when the team is done, 3:00am at the latest. A store with nothing dropped is reported as "no data", which is a fine result for a dry run.

## 5. Tip-off

```bash
~/Desktop/"DigitalCLIQ Brain HQ"/.claude/skills/ai-team/scripts/tipoff.sh
```

This opens Magic in a live Claude Code session in dry-run mode. Approve permission prompts as they come; Magic logs each one so they can be pre-approved before the first unattended night. Shift+Down cycles through the players so you can watch each one work. Watch `#ai-team` for the huddles. Note your Max usage percentage before and after.
