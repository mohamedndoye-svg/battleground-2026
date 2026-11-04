#!/usr/bin/env bash
# Copy the dashboard + latest live data into the gh-pages worktree and push. Called by the poller after a cycle.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PAGES="$ROOT/.pages"                      # gh-pages worktree, created by the workflow
mkdir -p "$PAGES/live" "$PAGES/data"
# Use the newest page and race data from main, so a data refresh pushed mid-night goes live on the next publish
# (the running job's checkout is from when it started). The poller re-reads data/*.json every cycle.
if git -C "$ROOT" fetch -q origin main 2>/dev/null; then
  git -C "$ROOT" checkout -q origin/main -- site/index.html data/races.json data/ga.json data/raw/ga_county_pres2024.json data/calls.json 2>/dev/null || true
fi
cp "$ROOT/site/index.html" "$PAGES/index.html"
cp "$ROOT/data/races.json" "$ROOT/data/ga.json" "$PAGES/"
cp "$ROOT/data/raw/ga_county_pres2024.json" "$PAGES/data/"
cp "$ROOT/site/live/live.json" "$ROOT/site/live/state.json" "$PAGES/live/"
[ -f "$ROOT/site/live/secondary.json" ] && cp "$ROOT/site/live/secondary.json" "$PAGES/live/" || true
[ -f "$ROOT/logs/fetch.jsonl" ] && tail -n 2000 "$ROOT/logs/fetch.jsonl" > "$PAGES/live/fetch-log.jsonl" || true
cd "$PAGES"
git add -A
git diff --cached --quiet && exit 0
git -c user.name="battleground-bot" -c user.email="actions@users.noreply.github.com" commit -q -m "Live results $(date -u +%FT%TZ)"
for i in 1 2 3; do git push -q origin gh-pages && exit 0; sleep $((i*5)); git pull -q --rebase origin gh-pages || true; done
exit 1
