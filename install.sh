#!/bin/zsh
# Mac side only: dashboard mirror and Apply Bridge. Discovery runs in GitHub Actions.
set -e
ROOT="$HOME/madeline-jobs"
cd "$ROOT"
[ -d .venv ] || /opt/homebrew/bin/python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
(cd bridge && npm install --silent && npx playwright install chromium)
AGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$AGENTS"
cp launchd/com.stefantseklidis.madeline-jobs.plist "$AGENTS/"
launchctl bootout "gui/$(id -u)/com.stefantseklidis.madeline-jobs" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$AGENTS/com.stefantseklidis.madeline-jobs.plist"
echo "Mac dashboard: http://127.0.0.1:8787"
