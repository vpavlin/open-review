#!/usr/bin/env bash
# The report stage: the pi reviewer reads the evidence and writes report.md /
# report.json. It talks to Venice through the logging gateway (the key never
# leaves the host; every call is logged and streamed to the live view).
set -uo pipefail
RUN=$1; REPO=$2; COMMIT=$3; HERE=$(cd "$(dirname "$0")" && pwd)
slug=$(basename "$RUN"); DEST=/srv/reviews/$slug
export VENICE_INFERENCE_KEY=$(grep -oP 'VENICE_INFERENCE_KEY=\K.*' /home/reviewer/.pi/agent/.env)
export REVIEW_RUN=$RUN
PORT=$(python3 -c "import socket;s=socket.socket();s.bind((\"127.0.0.1\",0));print(s.getsockname()[1]);s.close()")
export GATEWAY_PORT=$PORT
python3 "$HERE/gateway.py" & GW=$!
for i in $(seq 1 30); do curl -s -m1 -o /dev/null "http://127.0.0.1:$PORT/" && break; kill -0 $GW 2>/dev/null || { echo "gateway died"; exit 1; }; sleep 0.5; done
mkdir -p "$RUN/.pi/agent"
cat > "$RUN/.pi/agent/models.json" <<JSON
{"providers":{"venice":{"baseUrl":"http://127.0.0.1:$PORT","api":"openai-completions","apiKey":"local",
 "models":[{"id":"deepseek-v4-1-flash-uncensored","name":"DeepSeek","contextWindow":1000000,"maxTokens":131072}]}}}
JSON
( while kill -0 $GW 2>/dev/null; do "$HERE/render.py" "$RUN" "$DEST" "$slug" live >/dev/null 2>&1; sleep 3; done ) & LV=$!
cd "$RUN"
timeout 900 env HOME="$RUN" /home/reviewer/.local/bin/pi --model venice/deepseek-v4-1-flash-uncensored \
  -p "$(cat "$HERE/reviewer-prompt.md")" > "$RUN/logs/session.txt" 2>&1 || true
cp "$RUN/logs/session.txt" "$RUN/session.log" 2>/dev/null || true
kill $GW $LV 2>/dev/null; sleep 1
[ -f "$RUN/report.md" ] && echo "report written ($(wc -l < "$RUN/report.md") lines)" || echo "no report.md produced"
