#!/bin/bash
# Deploy the 2026-09-26 analytics-skill improvements (branch improve/analytics-2026-09-26)
# to the live skills, the vault, ~/Desktop/Skills, and the auto-trends scheduled prompt.
# Usage: deploy.sh --check   (read-only pre-check)   |   deploy.sh   (deploy)
# Safe by design: it refuses to run if any live file changed since the branch was built.
set -euo pipefail
REPO="$HOME/Desktop/digitalcliq-skills"
BRANCH="improve/analytics-2026-09-26"
BASE="4972946"   # repo commit that matched the live skills when the branch was built
VAULT="$HOME/Desktop/DigitalCLIQ Brain HQ"
RT="$(find "$HOME/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin" -maxdepth 3 -type d -name skills | head -1)"
[ -d "$RT/monthly-client-report" ] || { echo "Runtime skills folder not found"; exit 1; }
EXCL=(--exclude __pycache__ --exclude '*.pyc' --exclude .DS_Store --exclude '*.bak' --exclude '*.bak-*' --exclude '.bak-*' --exclude '.path-backup*')

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
git -C "$REPO" archive "$BRANCH" skills deploy | tar -x -C "$TMP"
mkdir -p "$TMP/base"; git -C "$REPO" archive "$BASE" skills | tar -x -C "$TMP/base"

echo "Checking nothing live changed since $BASE ..."
fail=0
for s in auto-trends monthly-client-report dealership-forecast-tool; do
  diff -rq "${EXCL[@]/--exclude/-x}" "$TMP/base/skills/$s" "$RT/$s" >/dev/null 2>&1 || { echo "  CHANGED since branch was built: runtime $s"; fail=1; }
done
diff -rq -x __pycache__ "$TMP/base/skills/ai-team" "$VAULT/.claude/skills/ai-team" >/dev/null 2>&1 || { echo "  CHANGED since branch was built: vault ai-team"; fail=1; }
( cd / && shasum -a 256 -c "$TMP/deploy/expected-live.sha256" >/dev/null 2>&1 ) || { echo "  CHANGED since branch was built: agents, decision note, or scheduled prompt"; fail=1; }
[ $fail -eq 0 ] || { echo "Stopped. Ask Claude to rebase the branch onto the current live files."; exit 1; }
echo "  all clear"
[ "${1:-}" = "--check" ] && { echo "Check only, nothing deployed."; exit 0; }

for s in auto-trends monthly-client-report dealership-forecast-tool; do
  rsync -a --delete "${EXCL[@]}" "$TMP/skills/$s/" "$RT/$s/"
done
rsync -a "${EXCL[@]}" "$TMP/skills/ai-team/" "$VAULT/.claude/skills/ai-team/"
cp "$TMP/deploy/agents/nick.md" "$TMP/deploy/agents/kobe.md" "$VAULT/.claude/agents/"
cp "$TMP/deploy/decisions/2026-09-16-ai-agent-team.md" "$VAULT/Intelligence/decisions/"
cp "$HOME/.claude/scheduled-tasks/auto-trends-monthly/SKILL.md" "$HOME/.claude/scheduled-tasks/auto-trends-monthly/SKILL.md.before-2026-09-26"
cp "$TMP/deploy/scheduled/auto-trends-monthly.SKILL.md" "$HOME/.claude/scheduled-tasks/auto-trends-monthly/SKILL.md"
for s in auto-trends monthly-client-report; do
  rsync -a --delete "${EXCL[@]}" "$TMP/skills/$s/" "$HOME/Desktop/Skills/skills/$s/"
done

echo "Deployed. Running the test suites from the live folders ..."
( cd "$RT/auto-trends" && AUTO_TRENDS_BUILD_ONLY=1 python3 tests/validate_skill.py --build-only | tail -1 )
( cd "$RT/monthly-client-report" && python3 tests/test_generator.py | tail -1 && python3 tests/test_lead_mix.py | tail -1 && python3 tests/test_ga4_month.py | tail -1 )
( cd "$RT/dealership-forecast-tool" && python3 tests/test_forecast.py | tail -1 )

git -C "$REPO" checkout -q main && git -C "$REPO" merge -q --ff-only "$BRANCH" && git -C "$REPO" push -q origin main
echo "Repo main now matches the live skills and is pushed. Next: re-upload auto-trends, monthly-client-report, dealership-forecast-tool and score-leads in claude.ai Settings > Skills so a plugin re-sync cannot revert them."
