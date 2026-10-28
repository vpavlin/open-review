#!/usr/bin/env bash
# The intake session (host/intake): created if missing, its model and what
# it is for set, on this user's shrooms-agent. Run by host/40-pipeline.sh.
set -euo pipefail
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
S=$XDG_RUNTIME_DIR/shrooms-agent/agent.sock
for _ in $(seq 1 30); do [ -S "$S" ] && break; sleep 1; done
api() { curl -sf --unix-socket "$S" "$@"; }
if ! api http://x/v1/sessions | grep -q '"name":"open-review"'; then
  api -X POST http://x/v1/sessions -H 'Content-Type: application/json' \
    -d "{\"name\":\"open-review\",\"dir\":\"$HOME/intake\",\"harness\":\"pi\"}" >/dev/null
fi
api -X PATCH http://x/v1/sessions/open-review -H 'Content-Type: application/json' -d '{
  "model": "venice/deepseek-v4-1-flash-1017",
  "skills": [{"name": "reviews", "description": "queues adversarial reviews of Logos Basecamp modules"}],
  "responsibilities": ["open-review intake: queues module reviews, reports where they stand"]}' >/dev/null
api http://x/v1/sessions | python3 -c 'import json,sys; print("open-review session:", [s["state"] for s in json.load(sys.stdin)["sessions"] if s["name"]=="open-review"])'
