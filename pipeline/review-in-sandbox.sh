#!/usr/bin/env bash
# The reviewer, INSIDE the disguised sandbox. It builds, runs, probes and writes
# the report — all here, where running untrusted code is safe. Launched by
# reviewer.sh with: the run dir at /run, the pipeline at /pipeline, Basecamp at
# /opt/basecamp, --network bridge, --hostname and SYS_ADMIN for the disguise,
# NET_ADMIN for the firewall, and GATEWAY_URL + the tokens so pi can reach the
# model through the host gateway (the Venice key never enters here).
#
# Three kinds of process run here. Root keeps the instruments: the disguise,
# the bait, the DNS sink, the recording proxies and the firewall that sends
# the users' web traffic to them, strace, the screen and its recorder; what
# they write goes where neither user can. The reviewer (pi) runs as ondra.
# The module, and whatever untrusted thing the reviewer runs (builds,
# scripts, Basecamp with the module in it), runs as pavel, the laptop's
# owner, through as-module: ondra may act as pavel, pavel may do nothing as
# ondra, so the module can't touch the report or the probes. Before
# 2026-10-28 all of it was root, and the module could have rewritten the
# record that judges it (open-review's own review, FR-2/FR-14).
set -uo pipefail
REVIEW_MODEL=${REVIEW_MODEL:-deepseek-v4-1-flash-1017}
U=ondra; UH=/home/ondra          # the reviewer
M=pavel; MH=/home/pavel          # the module
B=/run/behaviour; REC=/run/rec
mkdir -p "$B" /run/logs "$REC" /run/media /run/probes /run/desk /run/modlog
# The reviewer's places (the module can read them, to build, not write them),
# the module's log place, and nothing else of /run.
chown -R "$U:$U" /run/src /run/media /run/probes /run/desk
chown "$M:$M" /run/modlog
chmod 755 "$B" /run/logs "$REC" /run/src /run/media /run/probes /run/modlog
chmod 700 /run/desk

HOME_DIR="$MH" /usr/local/sbin/disguise.sh /usr/local/sbin/profiles.json "$B/disguise.json" >/dev/null 2>&1 || true
/usr/local/sbin/bait.sh "$MH" "$B/bait.json" >/dev/null 2>&1 || true
chmod 644 /tmp/disguise.env 2>/dev/null
ln -sf /pipeline/as-module.sh /usr/local/bin/as-module

# Every lookup goes through the sink, which logs it and answers (FR-3).
python3 /pipeline/dns_sink.py "$B/dns.log" & SINK=$!
sleep 1; echo "nameserver 127.0.0.1" > /etc/resolv.conf

# The recording proxies: each user's HTTP and HTTPS goes through its own,
# decrypted with a certificate authority the sandbox trusts, and every
# request is logged, so the record says whether the module or the reviewer
# made it. Root's own traffic (the proxies', the sink's) is not redirected.
proxy() {  # proxy <port> <log name>
  mitmdump --mode transparent --listen-host 127.0.0.1 --listen-port "$1" --showhost -q \
    --set confdir=/root/.mitmproxy --set block_global=false \
    -s /pipeline/proxy_log.py --set review_log="$B/$2.jsonl" -w "$B/$2.mitm" > "$B/$2.out" 2>&1 &
}
proxy 8080 proxy; PROXY=$!
for _ in $(seq 1 30); do [ -s /root/.mitmproxy/mitmproxy-ca-cert.pem ] && break; sleep 0.5; done
cp /root/.mitmproxy/mitmproxy-ca-cert.pem /usr/local/share/ca-certificates/review-proxy.crt
update-ca-certificates >/dev/null 2>&1
proxy 8081 proxy-reviewer; PROXY2=$!
sleep 1
for ipt in iptables ip6tables; do
  $ipt -t nat -A OUTPUT -p tcp -m owner --uid-owner "$M" -m multiport --dports 80,443 \
    -j REDIRECT --to-ports 8080 2>/dev/null
  $ipt -t nat -A OUTPUT -p tcp -m owner --uid-owner "$U" -m multiport --dports 80,443 \
    -j REDIRECT --to-ports 8081 2>/dev/null
done

# The screen and its recorder are root's, so the recording can't be replaced
# by what it records; desk, run by the user, puts Basecamp on it.
read -r W H < <(jq -r '(.resolution // "1920x1200") | split("x") | "\(.[0]) \(.[1])"' "$B/disguise.json" 2>/dev/null || echo "1920 1200")
Xvfb :99 -screen 0 "${W}x${H}x24" -nolisten tcp >/dev/null 2>&1 & XVFB=$!
sleep 2
ffmpeg -nostdin -loglevel error -f x11grab -framerate 4 -video_size "${W}x${H}" -i :99 \
  -c:v libx264 -preset veryfast -crf 32 -pix_fmt yuv420p -movflags +faststart "$REC/session.mp4" \
  >/dev/null 2>"$REC/ffmpeg.err" & RECORDER=$!
# Basecamp unpacked once, by root: the module can't change the app it runs in.
mkdir -p /opt/bc && (cd /opt/bc && /opt/basecamp/Basecamp.AppImage --appimage-extract >/dev/null 2>&1)
ln -sf /pipeline/desk.sh /usr/local/bin/desk

# pi points at the host gateway; the key stays on the host, calls carry the token.
GW="${GATEWAY_URL:-http://host.containers.internal:${GATEWAY_PORT}}"
if ! curl -s -m3 -o /dev/null "$GW/" 2>/dev/null; then
  g=$(ip route 2>/dev/null | awk '/default/{print $3; exit}')
  [ -n "$g" ] && GW="http://$g:${GATEWAY_PORT}"
fi
mkdir -p "$UH/.pi/agent"
cat > "$UH/.pi/agent/models.json" <<JSON
{"providers":{"venice":{"baseUrl":"${GW}","api":"openai-completions","apiKey":"${REVIEW_TOKEN}",
 "models":[{"id":"${REVIEW_MODEL}","name":"DeepSeek","contextWindow":1000000,"maxTokens":131072}]}}}
JSON
chown -R "$U:$U" "$UH/.pi"

# The published package and its dependencies are installed before the
# reviewer starts, as the module's user and untraced: unpacking them is our
# code, not the module's, and under strace delivery_module's 98 MB took about
# five minutes of every review (2026-10-28).
for l in /run/lgx/*.lgx; do
  [ -f "$l" ] && runuser -u "$M" -- env HOME="$MH" bash /pipeline/desk.sh _install "$l" > /run/logs/preinstall.txt 2>&1
done

# The broker that runs things as the module's user for the reviewer
# (as-module). Started here for the self-check; again under strace below.
python3 /pipeline/module_broker.py /run/desk/module.sock & BROKER=$!
for _ in $(seq 1 20); do [ -S /run/desk/module.sock ] && break; sleep 0.25; done

# Nothing runs in a sandbox that fails its own checks.
if ! bash /pipeline/sandbox-check.sh "$GW" "$B/sandbox-check.txt" >/dev/null; then
  { echo "The sandbox failed its own checks, so no review was run:"; grep FAIL "$B/sandbox-check.txt"; } > /run/logs/sandbox-check-failed.txt
  kill $SINK $PROXY $PROXY2 $RECORDER $XVFB $BROKER 2>/dev/null; exit 0
fi
kill $BROKER 2>/dev/null; wait $BROKER 2>/dev/null; rm -f /run/desk/module.sock

# As the user: a desktop session's environment (the disguise's), the proxy's
# authority for Node too, and no tokens (they are in pi's models.json; the
# gateway's hard cap is what holds whatever is read from there).
as_user() {
  runuser -u "$U" -- env -i HOME="$UH" USER="$U" LOGNAME="$U" SHELL=/bin/bash \
    PATH=/usr/local/bin:/usr/bin:/bin DISPLAY=:99 LANG=en_US.UTF-8 TERM=xterm \
    NODE_EXTRA_CA_CERTS=/usr/local/share/ca-certificates/review-proxy.crt \
    $(grep -E '^[A-Z_]+=' /tmp/disguise.env 2>/dev/null | grep -v '^HOSTNAME=' | tr '\n' ' ') "$@"
}

# The whole reviewer session is straced: its builds, its probes and anything the
# module does when the reviewer runs it all land in one capture.
cd /run/src 2>/dev/null || { echo '{"error":"no source"}' > "$B/summary.json"; kill $SINK $PROXY $PROXY2 $RECORDER $XVFB 2>/dev/null; exit 0; }
# A hard cap on the review's time (the proposal's promise); a run that hits
# it is published with what it has and says so.
MAX_MIN=${REVIEW_MAX_MIN:-150}
# The reviewer's clock (desk time). Run 4 never knew it had a limit, tested
# until it was cut off and wrote nothing.
echo "$(date +%s) $MAX_MIN" > /run/logs/clock
strace -f -qq -e trace=openat,open,connect,execve,unlinkat,unlink,rename -e signal=none -s 300 -o "$B/strace.log" \
  bash -c "python3 /pipeline/module_broker.py /run/desk/module.sock & echo \$! > /run/rec/broker.pid; for i in \$(seq 1 40); do [ -S /run/desk/module.sock ] && break; sleep 0.25; done; $(declare -f as_user); U=$U UH=$UH; as_user timeout --kill-after=60 ${MAX_MIN}m pi --model venice/${REVIEW_MODEL} -p 'Your instructions are in /pipeline/reviewer-prompt.md. Read all of it first, then do what it says.'" \
  > /run/logs/session.txt 2>&1 &
ST=$!
# Wait for the reviewer, not for strace: strace -f waits for everything it
# traces, and Basecamp and whatever else pi started outlive it. Forumer's
# fourth run hit its cap at 22:05 and sat there all night.
for _ in $(seq 1 40); do TO=$(pgrep -u "$U" -x timeout | head -1); [ -n "$TO" ] && break; sleep 0.5; done
while [ -n "${TO:-}" ] && kill -0 "$TO" 2>/dev/null; do sleep 5; done
# Everything either user still runs ends here, and the broker; the
# instruments keep going.
pkill -9 -u "$U" 2>/dev/null; pkill -9 -u "$M" 2>/dev/null
kill "$(cat /run/rec/broker.pid 2>/dev/null)" 2>/dev/null; sleep 1
wait "$ST"; rc=$?
echo "$rc" > /run/logs/reviewer.rc
[ "$rc" = 124 ] && echo "The review hit its ${MAX_MIN}-minute limit and was stopped." > /run/logs/timed-out.txt

# Stopped by the clock, the budget or a crash, while the model still works:
# the same reviewer, in the same conversation, finishes the report and runs
# nothing more, on the report's own share of the budget. Forumer's fourth run
# tested for 150 minutes and never wrote a line, though told to write as it
# went; a draft written early misses what came after it.
if [ "$rc" != 0 ] && [ ! -s /run/logs/inference-failed.txt ]; then
  sed -i "s/\"apiKey\":\"${REVIEW_TOKEN}\"/\"apiKey\":\"${REPORT_TOKEN:-$REVIEW_TOKEN}\"/" "$UH/.pi/agent/models.json"
  why="time"; [ -s /run/logs/budget-spent-testing.txt ] && why="budget"
  as_user timeout --kill-after=30 25m pi --continue --model "venice/${REVIEW_MODEL}" -p "Your testing ${why} is used up: run no more tests, probes or desk commands. Finish /run/src/report.md and /run/src/report.json now (write them if they don't exist), in the exact format given in /pipeline/reviewer-prompt.md, from everything you found and ran in this session: the probes in /run/probes and their results, and the screenshots in /run/media (list them in What I ran). Mark what you did not finish as not tested. Then stop." \
    > /run/logs/report-pass.txt 2>&1
  pkill -9 -u "$U" 2>/dev/null; pkill -9 -u "$M" 2>/dev/null
  [ -s /run/src/report.md ] && echo "Testing was stopped by its ${why} limit (exit $rc); the reviewer then finished its report from its session, testing nothing more." > /run/logs/written-after.txt
fi

# pi wrote report.md/report.json into /run/src; copy them up to the run root.
for f in report.md report.json; do [ -f "/run/src/$f" ] && [ ! -L "/run/src/$f" ] && cp "/run/src/$f" "/run/$f"; done
cp /run/logs/session.txt /run/session.log 2>/dev/null || true

# The instruments stop. The recorder writes its index on SIGINT; killed
# harder, the mp4 won't play.
kill -INT $RECORDER 2>/dev/null
for _ in $(seq 1 60); do kill -0 $RECORDER 2>/dev/null || break; sleep 0.5; done
kill -9 $RECORDER $XVFB 2>/dev/null; kill $PROXY $PROXY2 2>/dev/null; sleep 1; kill $SINK 2>/dev/null
# Basecamp's log is the module's: it ran as pavel. Published with the media.
cp /run/modlog/basecamp.log /run/media/basecamp.log 2>/dev/null

# Keep only real evidence: a screenshot of an empty screen or a video of
# nothing is not shown. The video moves in now that no user process is left.
for f in /run/media/*.png; do
  [ -f "$f" ] && [ ! -L "$f" ] || { rm -f "$f"; continue; }
  colours=$(convert "$f" -format %k info: 2>/dev/null || echo 0)
  [ "${colours:-0}" -lt 16 ] && rm -f "$f"
done
rm -f /run/media/session.mp4
if ffprobe -v error -show_entries format=duration -of csv=p=0 "$REC/session.mp4" >/dev/null 2>&1 \
   && ls /run/media/*.png >/dev/null 2>&1; then
  cp "$REC/session.mp4" /run/media/session.mp4
fi
if ! ls /run/media/*.png >/dev/null 2>&1; then
  { echo "No screenshot or video: the reviewer did not get Basecamp to show the module."
    echo "Last lines of basecamp.log:"; echo; tail -8 /run/media/basecamp.log 2>/dev/null; } > /run/media/GUI-did-not-run.txt
fi

python3 /pipeline/analyse.py "$B" "${GW#http://}" > "$B/summary.json" 2>"$B/analyse.err" || echo '{"error":"analyse"}' > "$B/summary.json"
echo "sandboxed review: done"
