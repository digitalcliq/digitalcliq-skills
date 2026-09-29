#!/bin/zsh
# Tip-off: start the AI team in an INTERACTIVE Claude Code session.
# Agent teams cannot spawn teammates in headless (-p) mode, so this runs a live session in a TTY.
#   ./tipoff.sh                          attended dry run (default)
#   ./tipoff.sh shift                    unattended night shift (auto mode + the allowlist in .claude/settings.json)
# Never use dontAsk for a team: teammates do not inherit it (agent-teams docs), so they fall back to a prompting
# mode and their prompts land in this terminal with nobody to answer. 2026-09-21 lost all five players that way.
#   ./tipoff.sh dry-run "note for Magic" extra words are appended to the /ai-team command so Magic reads them at tip-off
# The session ends on its own: a watchdog closes it two minutes after Magic writes the final whistle
# into the shift log, or at the hard cap (150 minutes), whichever comes first.
MODE="${1:-dry-run}"; shift 2>/dev/null
EXTRA="$*"
VAULT="$HOME/Desktop/DigitalCLIQ Brain HQ"
CAP_MIN=150

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v claude >/dev/null 2>&1; then
  echo "Claude Code CLI not found. See .claude/skills/ai-team/references/setup.md step 0."
  exit 1
fi
cd "$VAULT" || exit 1
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1

# "test" proves the launcher path (launchd -> Terminal -> this script -> claude on PATH) without starting the team.
if [ "$MODE" = "test" ]; then
  echo "[tipoff] launcher path OK at $(date '+%F %T'): vault readable, claude $(claude --version 2>/dev/null | head -1)" | tee -a "$HOME/Library/Logs/digitalcliq-ai-team.log"
  exit 0
fi

case "$MODE" in
  shift) PERM="auto" ;;      # unattended: the classifier approves what the allowlist misses; Magic runs usage.py --hung as the watchdog
  *)     PERM="auto" ;;      # attended: the classifier approves, Drew can answer anything it will not
esac

DATE=$(TZ=America/Los_Angeles date +%F)
LOG="$VAULT/outputs/ai-team/$DATE/shift-log.md"

# --chrome is harmless: shift-settings.json denies every Chrome tool; the Semrush browser fallback lives in the semrush-prepull desktop task.
# Connectors reach teammates only when Magic spawns them on a turn AFTER turn 1 (teammates get the tool list from
# the start of the lead's current turn, and MCP finishes loading a few seconds into turn 1). SKILL.md step 1 handles
# that with a turn break; usage.py --tools checks it right after the spawn (root cause found 2026-09-23).
caffeinate -i claude --model opus --chrome --permission-mode "$PERM" --settings "$VAULT/.claude/skills/ai-team/shift-settings.json" "/ai-team $MODE $EXTRA" &
CLAUDE_PID=$!

(
  START=$(date +%s)
  # A shift log for today may already hold an earlier run's final whistle (two runs in one day),
  # so only a NEW "- End:" line, one more than existed at tip-off, counts as this run finishing.
  END0=0; [ -f "$LOG" ] && END0=$(grep -c "^- End:" "$LOG")
  while kill -0 "$CLAUDE_PID" 2>/dev/null; do
    sleep 60
    NOW=$(date +%s)
    ENDN=0; [ -f "$LOG" ] && ENDN=$(grep -c "^- End:" "$LOG")
    if [ "$ENDN" -gt "$END0" ]; then
      sleep 120; kill -TERM "$CLAUDE_PID" 2>/dev/null; exit 0
    fi
    if [ $(( (NOW - START) / 60 )) -ge "$CAP_MIN" ]; then
      echo "[tipoff] hard cap ${CAP_MIN} min reached, closing the session" >> "$LOG" 2>/dev/null
      kill -TERM "$CLAUDE_PID" 2>/dev/null; exit 0
    fi
  done
) &
WATCHDOG=$!
wait "$CLAUDE_PID"
kill "$WATCHDOG" 2>/dev/null
exit 0
