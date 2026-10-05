#!/usr/bin/env bash
# Commit and push data/*.json after a scan, safely when another scan (the HTTP tier or the browser tier) pushed
# first. Instead of a `git pull --rebase` that cannot combine the files, this run's copies are saved, the latest
# main is checked out and the two are merged by scripts/merge_state.py. If the push is rejected (a third scan
# won the race) it starts over with the newer main.
set -euo pipefail

FILES="data/seen_items.json data/price_history.json data/alert_budget.json"
OURS="$(mktemp -d)"
for f in $FILES; do cp "$f" "$OURS/" 2>/dev/null || true; done

git config user.name "cyberday-hunter"
git config user.email "actions@users.noreply.github.com"

for attempt in 1 2 3 4 5 6; do
  git fetch --quiet origin main
  git checkout --quiet --force -B state-sync origin/main
  python scripts/merge_state.py "$OURS"
  git add $FILES
  if git diff --cached --quiet; then
    echo "State unchanged after merging; nothing to commit."
    exit 0
  fi
  git commit --quiet -m "chore: update seen items and price history"
  if git push --quiet origin HEAD:main; then
    echo "State pushed (attempt $attempt)."
    exit 0
  fi
  echo "Push rejected (attempt $attempt): another scan pushed first, merging again."
  sleep $((RANDOM % 8 + 3))
done
echo "Could not push the state after 6 attempts." >&2
exit 1
