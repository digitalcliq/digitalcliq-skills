#!/bin/zsh
# Daytime login keep-alive for the night shift (Drew, 2026-10-19: never lose a morning to an expired login again).
# launchd runs this at 12 PM and 8 PM every day (com.digitalcliq.claude-auth-check). A tiny headless call uses the
# terminal CLI login, which refreshes it so it does not go stale between shifts. If the call fails, Drew gets a Slack
# tag and a Mac notification while he is awake, hours before the 1 AM tip-off, instead of a dead shift.
VAULT="$HOME/Desktop/DigitalCLIQ Brain HQ"
LOGF="$HOME/Library/Logs/digitalcliq-ai-team.log"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$VAULT" || exit 1

OUT=$(claude -p "Reply with just: ok" --model haiku --max-turns 1 2>&1 | tail -1)
if print -r -- "$OUT" | grep -qi '^ok'; then
  echo "$(date '+%F %T') [auth-check] login ok, refreshed" >> "$LOGF"
  exit 0
fi

# One retry after a minute in case it was a network blip, so Drew is not pinged for nothing.
sleep 60
OUT=$(claude -p "Reply with just: ok" --model haiku --max-turns 1 2>&1 | tail -1)
if print -r -- "$OUT" | grep -qi '^ok'; then
  echo "$(date '+%F %T') [auth-check] login ok on retry" >> "$LOGF"
  exit 0
fi

echo "$(date '+%F %T') [auth-check] FAILED: $OUT" >> "$LOGF"
MSG="Heads up before tonight's shift: the Claude login on the Mac mini is not working. Open the Terminal app, run claude auth login, click Authorize in the browser. Takes a minute and the 1 AM shift runs normally."
python3 "$VAULT/.claude/skills/ai-team/scripts/slack.py" post --as magic --tag-drew --text "$MSG" >/dev/null 2>&1
osascript -e "display notification \"Claude login is not working. Run claude auth login in Terminal before tonight's shift.\" with title \"AI team\"" 2>/dev/null
exit 1
