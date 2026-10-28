#!/usr/bin/env bash
# Host orchestrator for the sandboxed reviewer. Starts the token-protected
# logging gateway (the Venice key stays here), launches ONE disguised sandbox
# cage that runs review-in-sandbox.sh (the reviewer builds/runs/probes inside),
# streams the live view, and collects the report.
set -uo pipefail
RUN=$1; HERE=$(cd "$(dirname "$0")" && pwd)
IMG=localhost/open-reviewer:latest
BASECAMP=/home/reviewer/sandbox/Basecamp.AppImage
slug=$(basename "$RUN"); DEST=/srv/reviews/$slug
export VENICE_INFERENCE_KEY=$(grep -oP 'VENICE_INFERENCE_KEY=\K.*' /home/reviewer/.pi/agent/.env)
# The provider: Venice (DIEM) by default; REVIEW_PROVIDER=openrouter with a
# ":free" model for the free-model trial (its key in the same .env).
REVIEW_PROVIDER=${REVIEW_PROVIDER:-venice}
if [ "$REVIEW_PROVIDER" = openrouter ]; then
  export GATEWAY_UPSTREAM=https://openrouter.ai/api/v1/chat/completions
  export PROVIDER_KEY=$(grep -oP 'OPENROUTER_API_KEY=\K.*' /home/reviewer/.pi/agent/.env)
  [ -n "$PROVIDER_KEY" ] || { echo "no OPENROUTER_API_KEY in ~/.pi/agent/.env"; exit 1; }
  export REVIEW_MAX_OUT=${REVIEW_MAX_OUT:-32768}   # free models refuse Venice's 131072
fi
export REVIEW_RUN=$RUN GATEWAY_BIND=0.0.0.0
# The model is a setting: deepseek-v4-1-flash-uncensored failed every request
# from 17:38 UTC on 2026-10-27 while its siblings answered.
export REVIEW_MODEL=${REVIEW_MODEL:-deepseek-v4-1-flash-1017}
mkdir -p "$RUN/logs"; echo "$REVIEW_PROVIDER/$REVIEW_MODEL" > "$RUN/logs/model"
# Which sandbox image did the review: not pinned yet (FR-13), so at least named.
podman image inspect --format '{{.Id}}' "$IMG" > "$RUN/logs/image" 2>/dev/null
cat "$HERE/.commit" > "$RUN/logs/pipeline-commit" 2>/dev/null   # which pipeline (40-pipeline.sh)
PORT=$(python3 -c "import socket;s=socket.socket();s.bind(('0.0.0.0',0));print(s.getsockname()[1]);s.close()")
TOKEN=$(python3 -c "import secrets;print(secrets.token_hex(16))")
REPORT=$(python3 -c "import secrets;print(secrets.token_hex(16))")
export GATEWAY_PORT=$PORT REVIEW_TOKEN=$TOKEN REPORT_TOKEN=$REPORT REVIEW_BUDGET=${REVIEW_BUDGET:-1.0}
[ "$REVIEW_PROVIDER" = venice ] && python3 "$HERE/balance.py" "$RUN/logs/balance-start.json"
python3 "$HERE/gateway.py" & GW=$!
for i in $(seq 1 30); do curl -s -m1 -o /dev/null "http://127.0.0.1:$PORT/" && break; kill -0 $GW 2>/dev/null || { echo "gateway died"; exit 1; }; sleep 0.5; done
( while kill -0 $GW 2>/dev/null; do "$HERE/render.py" "$RUN" "$DEST" "$slug" live >/dev/null 2>&1; sleep 3; done ) & LV=$!
BC_MNT=(); [ -x "$BASECAMP" ] && BC_MNT=(-v "$BASECAMP:/opt/basecamp/Basecamp.AppImage:ro")
# For testing a host's setup without a model (host/test): a stand-in for pi.
[ -n "${REVIEW_TEST_PI:-}" ] && BC_MNT+=(-v "$REVIEW_TEST_PI:/usr/local/bin/pi:ro")
# The sandbox's own limits (the review's, then 25 minutes for the write-up)
# come first; this is the backstop, by name, since a TERM to podman run is
# passed to bash as PID 1, which ignores it: "timeout 2400" did nothing at
# all (FR-6, 2026-10-28).
NAME=review-$slug-$$
# Its own output closed and its sleep ended with it: a sleep left holding
# the pipe kept review.sh waiting after the review ended (2026-10-28).
( exec >/dev/null 2>&1 </dev/null
  sleep $(( (${REVIEW_MAX_MIN:-150}+40)*60 )) & s=$!; trap 'kill $s; exit' TERM
  wait $s; podman kill "$NAME" ) & BACKSTOP=$!
podman run --rm --name "$NAME" --hostname dell-xps --cap-add SYS_ADMIN --cap-add NET_ADMIN --network bridge \
  -e GATEWAY_PORT="$PORT" -e GATEWAY_URL="http://host.containers.internal:$PORT" -e REVIEW_TOKEN="$TOKEN" -e REPORT_TOKEN="$REPORT" -e REVIEW_MAX_MIN="${REVIEW_MAX_MIN:-150}" -e REVIEW_MODEL="$REVIEW_MODEL" -e REVIEW_MAX_OUT="${REVIEW_MAX_OUT:-131072}" \
  -v "$RUN:/run:z" -v "$HERE:/pipeline:ro" "${BC_MNT[@]}" "$IMG" \
  bash /pipeline/review-in-sandbox.sh 2>&1 | tail -6
kill $BACKSTOP 2>/dev/null
kill $GW $LV 2>/dev/null; sleep 1
# Venice settles a streamed reply after it ends; give the last one a moment.
[ "$REVIEW_PROVIDER" = venice ] && { sleep 20; python3 "$HERE/balance.py" "$RUN/logs/balance-end.json"; }
[ -f "$RUN/report.md" ] && echo "report written ($(wc -l < "$RUN/report.md") lines)" || echo "no report.md produced"
