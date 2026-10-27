#!/usr/bin/env bash
# The reviewer, INSIDE the disguised sandbox. It builds, runs, probes and writes
# the report — all here, where running untrusted code is safe. Launched by
# reviewer.sh with: the run dir at /run, the pipeline at /pipeline, Basecamp at
# /opt/basecamp, --network bridge, --hostname/--cap-add for the disguise, and
# the env GATEWAY_URL + REVIEW_TOKEN so pi can reach the model through the host
# gateway (the Venice key never enters here).
set -uo pipefail
REVIEW_MODEL=${REVIEW_MODEL:-deepseek-v4-1-flash-1017}
B=/run/behaviour; mkdir -p "$B" /run/media
/usr/local/sbin/disguise.sh /usr/local/sbin/profiles.json "$B/disguise.json" >/dev/null 2>&1 || true
/usr/local/sbin/bait.sh /root "$B/bait.json" >/dev/null 2>&1 || true
python3 /pipeline/dns_sink.py "$B/dns.log" & SINK=$!

# The reviewer's desktop: a screen, Basecamp and a recorder (see desk.sh).
ln -sf /pipeline/desk.sh /usr/local/bin/desk

# pi points at the host gateway; the key stays on the host, calls carry the token.
GW="${GATEWAY_URL:-http://host.containers.internal:${GATEWAY_PORT}}"
if ! curl -s -m3 -o /dev/null "$GW/" 2>/dev/null; then
  g=$(ip route 2>/dev/null | awk '/default/{print $3; exit}')
  [ -n "$g" ] && GW="http://$g:${GATEWAY_PORT}"
fi
export HOME=/root
mkdir -p /root/.pi/agent
cat > /root/.pi/agent/models.json <<JSON
{"providers":{"venice":{"baseUrl":"${GW}","api":"openai-completions","apiKey":"${REVIEW_TOKEN}",
 "models":[{"id":"${REVIEW_MODEL}","name":"DeepSeek","contextWindow":1000000,"maxTokens":131072}]}}}
JSON

# The whole reviewer session is straced: its builds, its probes and anything the
# module does when the reviewer runs it all land in one capture.
cd /run/src 2>/dev/null || { echo '{"error":"no source"}' > "$B/summary.json"; kill $SINK 2>/dev/null; exit 0; }
# A hard cap on the review's time (the proposal's promise); a run that hits
# it is published with what it has and says so.
MAX_MIN=${REVIEW_MAX_MIN:-150}
strace -f -qq -e trace=openat,open,connect,execve,unlinkat,unlink,rename -e signal=none -s 300 -o "$B/strace.log" \
  timeout --kill-after=60 "${MAX_MIN}m" pi --model "venice/${REVIEW_MODEL}" -p "$(cat /pipeline/reviewer-prompt.md)" \
  > /run/logs/session.txt 2>&1
rc=$?
[ "$rc" = 124 ] && echo "The review hit its ${MAX_MIN}-minute limit and was stopped; what it found by then is below." > /run/logs/timed-out.txt
# pi wrote report.md/report.json into /run/src; move them up to the run root.
for f in report.md report.json; do [ -f "/run/src/$f" ] && cp "/run/src/$f" "/run/$f"; done
cp /run/logs/session.txt /run/session.log 2>/dev/null || true

# Finalise the video whatever the reviewer did, then keep only real evidence:
# a screenshot of a black screen or a video of nothing is not shown.
desk stop >/dev/null 2>&1 || true
for f in /run/media/*.png; do
  [ -f "$f" ] || continue
  colours=$(convert "$f" -format %k info: 2>/dev/null || echo 0)
  [ "${colours:-0}" -lt 16 ] && rm -f "$f"
done
mp4=$(stat -c%s /run/media/session.mp4 2>/dev/null || echo 0)
if [ "$mp4" -gt 0 ] && ! ffprobe -v error -show_entries format=duration -of csv=p=0 /run/media/session.mp4 >/dev/null 2>&1; then
  rm -f /run/media/session.mp4
fi
if ! ls /run/media/*.png /run/media/session.mp4 >/dev/null 2>&1; then
  { echo "No screenshot or video: the reviewer did not get Basecamp to show the module."
    echo "Last lines of basecamp.log:"; echo; tail -8 /run/media/basecamp.log 2>/dev/null; } > /run/media/GUI-did-not-run.txt
fi

kill $SINK 2>/dev/null
mkdir -p "$B"
python3 /pipeline/analyse.py "$B" > "$B/summary.json" 2>"$B/analyse.err" || echo '{"error":"analyse"}' > "$B/summary.json"
echo "sandboxed review: done"
