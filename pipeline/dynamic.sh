#!/usr/bin/env bash
# Runs INSIDE the disguised sandbox (launched by review.sh with --hostname,
# --cap-add SYS_ADMIN, a run dir at /run and the pipeline at /pipeline). It
# dresses the box, plants bait, then runs the module's install/build under full
# instrumentation with a DNS sinkhole, records the GUI if Basecamp is present,
# and grades the result against the bait.
set -uo pipefail
B=/run/behaviour; mkdir -p "$B" /run/media
/usr/local/sbin/disguise.sh /usr/local/sbin/profiles.json "$B/disguise.json" >/dev/null 2>&1 || true
/usr/local/sbin/bait.sh /root "$B/bait.json" >/dev/null 2>&1 || true

python3 /pipeline/dns_sink.py "$B/dns.log" & SINK=$!
echo "nameserver 127.0.0.1" > /etc/resolv.conf 2>/dev/null || true
sleep 1

if command -v Xvfb >/dev/null 2>&1; then
  Xvfb :99 -screen 0 1600x1000x24 >/dev/null 2>&1 & export DISPLAY=:99; sleep 2
  command -v ffmpeg >/dev/null 2>&1 && ffmpeg -nostdin -loglevel error -f x11grab -video_size 1600x1000 -i :99 -t 120 /run/media/session.mp4 >/dev/null 2>&1 & FF=${!:-}
fi

cd /run/src 2>/dev/null || { echo '{"error":"no source"}' > "$B/summary.json"; exit 0; }
# Shift the clock forward so time-delayed behaviour still fires.
strace -f -qq -e trace=openat,open,connect,execve,unlinkat,unlink,rename -e signal=none -s 300 -o "$B/strace.log" \
  faketime '+3 days' bash -c '
    if [ -f package.json ]; then npm install 2>&1 | tail -40; fi
    if [ -f metadata.json ]; then echo "module: $(jq -r .name metadata.json 2>/dev/null)"; fi
    true' > "$B/build.out" 2>&1 || true

# Basecamp GUI (best effort): install the module into a user-dir and open it.
if [ -x /opt/basecamp/Basecamp.AppImage ] && [ -f /run/src/metadata.json ]; then
  U=/root/bc; mkdir -p "$U/plugins"; cp -r /run/src "$U/plugins/$(jq -r .name /run/src/metadata.json 2>/dev/null || echo mod)" 2>/dev/null
  ( QT_QPA_PLATFORM=xcb /opt/basecamp/Basecamp.AppImage --user-dir "$U" >/run/media/basecamp.log 2>&1 ) & BC=$!
  sleep 25; command -v import >/dev/null 2>&1 && DISPLAY=:99 import -window root /run/media/basecamp.png 2>/dev/null
  kill $BC 2>/dev/null
fi

sleep 1; [ -n "${FF:-}" ] && kill $FF 2>/dev/null; kill $SINK 2>/dev/null
mkdir -p "$B"
python3 /pipeline/analyse.py "$B" > "$B/summary.json" 2>"$B/analyse.err" || echo '{"error":"analyse failed"}' > "$B/summary.json"
echo "dynamic: done"
