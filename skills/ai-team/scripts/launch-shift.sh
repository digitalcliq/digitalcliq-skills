#!/bin/zsh
# Launcher for launchd: opens Terminal.app and runs tipoff.sh in it, because the team needs a real TTY.
# Mode comes from ~/.config/digitalcliq-ai-team/next-mode if that file exists (one-shot override, deleted
# after reading, e.g. "dry-run Nick: NOI data only"), otherwise "shift".
VAULT="$HOME/Desktop/DigitalCLIQ Brain HQ"
CFG="$HOME/.config/digitalcliq-ai-team"
TIPOFF="$VAULT/.claude/skills/ai-team/scripts/tipoff.sh"
MODE="shift"
if [ -f "$CFG/next-mode" ]; then
  MODE=$(cat "$CFG/next-mode"); rm -f "$CFG/next-mode"
fi
mkdir -p "$HOME/Library/Logs"
echo "$(date '+%F %T') launch: $MODE" >> "$HOME/Library/Logs/digitalcliq-ai-team.log"
# Weekday guard in case the calendar entry is ever widened: shift mode runs Mon to Fri only.
DOW=$(TZ=America/Los_Angeles date +%u)
if [ "$MODE" = "shift" ] && [ "$DOW" -gt 5 ]; then
  echo "$(date '+%F %T') weekend, skipped" >> "$HOME/Library/Logs/digitalcliq-ai-team.log"; exit 0
fi
CMD="zsh '$TIPOFF' $MODE"
/usr/bin/osascript <<APPLESCRIPT
tell application "Terminal"
  activate
  do script "$CMD"
end tell
APPLESCRIPT
