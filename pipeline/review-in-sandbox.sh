#!/usr/bin/env bash
# The reviewer, INSIDE the disguised sandbox. It builds, runs, probes and writes
# the report — all here, where running untrusted code is safe. Launched by
# reviewer.sh with: the run dir at /run, the pipeline at /pipeline, Basecamp at
# /opt/basecamp, --network bridge, --hostname/--cap-add for the disguise, and
# the env GATEWAY_URL + REVIEW_TOKEN so pi can reach the model through the host
# gateway (the Venice key never enters here).
set -uo pipefail
REVIEW_MODEL=${REVIEW_MODEL:-deepseek-v4-1-flash-1017}
# The tokens go into pi's models.json, not into the environment of what the
# reviewer runs. (Root in the sandbox can still read /proc/1/environ; the
# gateway's hard cap is what holds whatever is read.)
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

# Nothing runs in a sandbox that fails its own checks.
if ! bash /pipeline/sandbox-check.sh "$GW" "$B/sandbox-check.txt" >/dev/null; then
  { echo "The sandbox failed its own checks, so no review was run:"; grep FAIL "$B/sandbox-check.txt"; } > /run/logs/sandbox-check-failed.txt
  kill $SINK 2>/dev/null; exit 0
fi

# The whole reviewer session is straced: its builds, its probes and anything the
# module does when the reviewer runs it all land in one capture.
cd /run/src 2>/dev/null || { echo '{"error":"no source"}' > "$B/summary.json"; kill $SINK 2>/dev/null; exit 0; }
# A hard cap on the review's time (the proposal's promise); a run that hits
# it is published with what it has and says so.
MAX_MIN=${REVIEW_MAX_MIN:-150}
# The reviewer's clock (desk time). Run 4 never knew it had a limit, tested
# until it was cut off and wrote nothing.
echo "$(date +%s) $MAX_MIN" > /run/logs/clock
strace -f -qq -e trace=openat,open,connect,execve,unlinkat,unlink,rename -e signal=none -s 300 -o "$B/strace.log" \
  timeout --kill-after=60 "${MAX_MIN}m" env -u REPORT_TOKEN -u REVIEW_TOKEN pi --model "venice/${REVIEW_MODEL}" -p "Your instructions are in /pipeline/reviewer-prompt.md. Read all of it first, then do what it says." \
  > /run/logs/session.txt 2>&1 &
ST=$!
# Wait for the reviewer, not for strace: strace -f waits for everything it
# traces, and Basecamp, the screen and the recorder that pi started outlive
# it. Forumer's fourth run hit its cap at 22:05 and sat there all night.
for _ in $(seq 1 20); do TO=$(pgrep -P "$ST" -x timeout); [ -n "$TO" ] && break; sleep 0.5; done
while [ -n "${TO:-}" ] && kill -0 "$TO" 2>/dev/null; do sleep 5; done
desk stop >/dev/null 2>&1 || true
for p in $(ps -eo pid= | tr -d ' '); do
  case "$p" in 1|"$$"|"$SINK"|"$ST") ;; *) kill -9 "$p" 2>/dev/null ;; esac
done
wait "$ST"; rc=$?
echo "$rc" > /run/logs/reviewer.rc
[ "$rc" = 124 ] && echo "The review hit its ${MAX_MIN}-minute limit and was stopped." > /run/logs/timed-out.txt

# Stopped by the clock, the budget or a crash, while the model still works:
# the same reviewer, in the same conversation, finishes the report and runs
# nothing more, on the report's own share of the budget. Forumer's fourth run
# tested for 150 minutes and never wrote a line, though told to write as it
# went; a draft written early misses what came after it.
if [ "$rc" != 0 ] && [ ! -s /run/logs/inference-failed.txt ]; then
  sed -i "s/\"apiKey\":\"${REVIEW_TOKEN}\"/\"apiKey\":\"${REPORT_TOKEN:-$REVIEW_TOKEN}\"/" /root/.pi/agent/models.json
  why="time"; [ -s /run/logs/budget-spent-testing.txt ] && why="budget"
  timeout --kill-after=30 25m pi --continue --model "venice/${REVIEW_MODEL}" -p "Your testing ${why} is used up: run no more tests, probes or desk commands. Finish /run/src/report.md and /run/src/report.json now (write them if they don't exist), in the exact format given in /pipeline/reviewer-prompt.md, from everything you found and ran in this session: the probes in /run/probes and their results, and the screenshots in /run/media (list them in What I ran). Mark what you did not finish as not tested. Then stop." \
    > /run/logs/report-pass.txt 2>&1
  [ -s /run/src/report.md ] && echo "Testing was stopped by its ${why} limit (exit $rc); the reviewer then finished its report from its session, testing nothing more." > /run/logs/written-after.txt
fi

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
if ! ls /run/media/*.png >/dev/null 2>&1 && [ ! -f /run/media/session.mp4 ]; then
  { echo "No screenshot or video: the reviewer did not get Basecamp to show the module."
    echo "Last lines of basecamp.log:"; echo; tail -8 /run/media/basecamp.log 2>/dev/null; } > /run/media/GUI-did-not-run.txt
fi

kill $SINK 2>/dev/null
mkdir -p "$B"
python3 /pipeline/analyse.py "$B" > "$B/summary.json" 2>"$B/analyse.err" || echo '{"error":"analyse"}' > "$B/summary.json"
echo "sandboxed review: done"
