#!/usr/bin/env bash
# Stop the running review: its whole process group and its sandboxes. By the
# pid review.sh recorded, never by pattern: a pkill -f naming the review
# matches the shell running the stop as well (2026-10-28).
set -u
STATE=/home/reviewer/.review
if [ -s "$STATE/pid" ] && kill -0 "$(cat "$STATE/pid")" 2>/dev/null; then
  pg=$(ps -o pgid= -p "$(cat "$STATE/pid")" | tr -d ' ')
  [ -n "$pg" ] && kill -TERM -- "-$pg" 2>/dev/null
fi
for c in $(podman ps -q --filter ancestor=localhost/open-reviewer:latest); do podman kill "$c" >/dev/null; done
# Whatever else still holds the review lock: podman's slirp4netns inherits
# review.sh's lock descriptor and outlives a stopped review, so every next
# review found one "already running" and the queue marked eleven jobs done
# in a minute (2026-10-30).
sleep 1
fuser -k "$STATE/lock" >/dev/null 2>&1
podman ps -q --filter ancestor=localhost/open-reviewer:latest | grep -q . && echo "a sandbox is still running" || echo "stopped"
