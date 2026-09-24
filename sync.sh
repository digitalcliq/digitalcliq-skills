#!/bin/bash
# Snapshot every DigitalCLIQ custom skill into this repo, commit, and push.
# Usage: ./sync.sh            (snapshot + commit + push if a remote exists)
#        ./sync.sh --no-push  (snapshot + commit only)
set -euo pipefail
REPO="$(cd "$(dirname "$0")" && pwd)"
VAULT="$HOME/Desktop/DigitalCLIQ Brain HQ"
PLUGIN_ROOT="$HOME/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin"
RT="$(find "$PLUGIN_ROOT" -maxdepth 3 -type d -name skills -path '*/skills' | head -1)"
[ -d "$RT/score-leads" ] || { echo "Runtime skills folder not found under $PLUGIN_ROOT"; exit 1; }

# Custom skills that run from the anthropic-skills plugin runtime
PLUGIN_SKILLS=(auto-trends morning-coffee compare-weeks dealership-forecast-tool monthly-client-report
  brand-check dealership-compliance-audit cars-act-check mcpeeks-site-watch onlinereputation
  score-leads score-salespeople dealership-paid-media-audit monthly-leasing inventory-pulse
  blog-content social-media-manager daily-work-log)

EXCL=(--exclude __pycache__ --exclude '*.pyc' --exclude '.DS_Store' --exclude '*.bak' --exclude '*.bak-*' --exclude '.bak-*' --exclude '.path-backup*')
mkdir -p "$REPO/skills" "$REPO/agents" "$REPO/shared" "$REPO/docs"

for s in "${PLUGIN_SKILLS[@]}"; do
  rsync -a --delete "${EXCL[@]}" "$RT/$s/" "$REPO/skills/$s/"
done
rsync -a "$RT/post_flight.py" "$REPO/shared/post_flight.py"

# Vault-hosted skills
rsync -a --delete "${EXCL[@]}" "$VAULT/.claude/skills/ai-team/" "$REPO/skills/ai-team/"
rsync -a --delete "${EXCL[@]}" --exclude .git "$VAULT/Second Brain Optimizer Skill/" "$REPO/skills/second-brain-optimizer/"
mkdir -p "$REPO/skills/nightly-notes"
rsync -a "$VAULT/Skills/nightly-notes/SKILL.md" "$REPO/skills/nightly-notes/SKILL.md"
rsync -a --delete "${EXCL[@]}" "$VAULT/.claude/agents/" "$REPO/agents/"

# Vault design notes and change logs (docs only, not runtime)
rsync -a --delete "${EXCL[@]}" --exclude nightly-notes "$VAULT/Skills/" "$REPO/docs/"

cd "$REPO"
git add -A
if git diff --cached --quiet; then echo "No changes since last backup."; exit 0; fi
git commit -q -m "Skills backup $(date '+%Y-%m-%d %H:%M')"
echo "Committed: $(git log -1 --format='%h %s')"
if [ "${1:-}" != "--no-push" ] && git remote get-url origin >/dev/null 2>&1; then
  git push origin main
fi
